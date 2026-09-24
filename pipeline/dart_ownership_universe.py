"""Point-in-time Korean issuer universe for DART ownership collection.

The ownership endpoint is keyed by DART ``corp_code`` while the replay's
historical universe is keyed by securities.  This module is the explicit,
deterministic bridge between the two identities.  It never fuzzy-matches a
name: a security is resolved by an exact stock code first, then by a unique
exact company-name match.  Everything else remains an unresolved row.

The authoritative membership source is the accumulated
``ledger/universe-history.json`` on ``signal-history``.  KRX monthly snapshot
rows supply the company names that file intentionally does not carry.  One
issuer may therefore own several historical security identities after ticker
changes; collection happens once per issuer, not once per ticker spelling.
"""
from __future__ import annotations

import io
import json
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from . import historical_store as HS

CONTRACT = "KR_OWNERSHIP_COLLECTION_UNIVERSE_V1"
UNIVERSE_NAME = "KR_OWNERSHIP_COLLECTION_UNIVERSE"


def exact_name(value) -> str:
    """Unicode/outer-whitespace normalization, never a fuzzy company match."""
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def parse_corp_code_zip(blob: bytes) -> list[dict]:
    """DART ``corpCode.xml`` ZIP to a complete issuer directory.

    Rows with no current stock code are retained.  They are precisely the rows
    needed to resolve a delisted historical security by an exact former name.
    """
    if blob[:2] != b"PK":
        raise ValueError("corp_code response was not a ZIP archive")
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        xml = archive.read(archive.namelist()[0])
    rows = []
    for item in ET.fromstring(xml).iter("list"):
        corp_code = (item.findtext("corp_code") or "").strip()
        if not corp_code:
            continue
        rows.append({
            "corpCode": corp_code,
            "corpName": exact_name(item.findtext("corp_name")),
            "stockCode": (item.findtext("stock_code") or "").strip(),
            "modifyDate": (item.findtext("modify_date") or "").strip() or None,
        })
    return sorted(rows, key=lambda row: row["corpCode"])


def load_memberships(path: str | Path) -> dict[str, dict]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("historical membership source must be an object")
    return {str(ticker): dict(row) for ticker, row in raw.items()
            if isinstance(row, dict) and row.get("region") == "KR"}


def load_krx_rows(root: str | Path) -> list[dict]:
    rows = []
    for path in sorted(Path(root).glob("krx-universe-*.jsonl.gz")):
        rows.extend(HS.read_jsonl(path))
    return rows


def security_records(memberships: dict[str, dict], krx_rows: list[dict],
                     current_tickers: list[str]) -> list[dict]:
    """One deterministic record per historical security identity."""
    names: dict[str, set[str]] = {}
    dates: dict[str, list[str]] = {}
    snapshots: dict[str, int] = {}
    for row in krx_rows:
        ticker = str(row.get("ticker") or "")
        if not ticker:
            continue
        name = exact_name(row.get("name"))
        if name:
            names.setdefault(ticker, set()).add(name)
        if row.get("date"):
            dates.setdefault(ticker, []).append(str(row["date"]))
        snapshots[ticker] = snapshots.get(ticker, 0) + 1

    current = set(current_tickers)
    tickers = sorted(set(memberships) | current)
    out = []
    for ticker in tickers:
        membership = memberships.get(ticker) or {}
        observed = sorted(set(dates.get(ticker) or []))
        out.append({
            "securityId": f"KRX:{ticker}",
            "ticker": ticker,
            "stockCode": ticker.split(".")[0],
            "names": sorted(names.get(ticker) or []),
            "listed": membership.get("listed") or (observed[0] if observed else None),
            "delisted": membership.get("delisted"),
            "firstSnapshot": observed[0] if observed else None,
            "lastSnapshot": observed[-1] if observed else None,
            "snapshotCount": snapshots.get(ticker, 0),
            "currentUniverse": ticker in current,
            "membershipProvenance": (
                "signal-history:ledger/universe-history.json"
                if ticker in memberships else "CURRENT_UNIVERSE_ONLY"),
        })
    return out


def _unique_index(directory: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in directory:
        value = exact_name(row.get(key))
        if value:
            out.setdefault(value, []).append(row)
    return out


def _resolve_security(security: dict, by_stock: dict, by_name: dict) -> tuple[dict | None, dict]:
    stock_candidates = by_stock.get(security["stockCode"], [])
    stock_codes = sorted({row["corpCode"] for row in stock_candidates})
    if len(stock_codes) == 1:
        row = next(row for row in stock_candidates if row["corpCode"] == stock_codes[0])
        return row, {"method": "DART_STOCK_CODE_EXACT", "matchedValue": security["stockCode"]}
    if len(stock_codes) > 1:
        return None, {"reason": "AMBIGUOUS_STOCK_CODE", "candidateCorpCodes": stock_codes}

    name_candidates = []
    for name in security["names"]:
        name_candidates.extend(by_name.get(exact_name(name), []))
    name_codes = sorted({row["corpCode"] for row in name_candidates})
    if len(name_codes) == 1:
        row = next(row for row in name_candidates if row["corpCode"] == name_codes[0])
        matched = sorted(name for name in security["names"]
                         if any(candidate["corpCode"] == row["corpCode"]
                                for candidate in by_name.get(exact_name(name), [])))
        return row, {"method": "DART_CORP_NAME_EXACT_UNIQUE", "matchedValue": matched[0]}
    if len(name_codes) > 1:
        return None, {"reason": "AMBIGUOUS_CORP_NAME", "candidateCorpCodes": name_codes}
    return None, {"reason": "NO_EXACT_DART_IDENTITY", "candidateCorpCodes": []}


def build_collection_universe(*, memberships: dict[str, dict], krx_rows: list[dict],
                              current_tickers: list[str], dart_directory: list[dict]) -> dict:
    """Union historical securities, then collapse only proven issuer identities."""
    securities = security_records(memberships, krx_rows, current_tickers)
    by_stock = _unique_index(dart_directory, "stockCode")
    by_name = _unique_index(dart_directory, "corpName")
    issuers: dict[str, dict] = {}
    unresolved = []

    for security in securities:
        issuer, provenance = _resolve_security(security, by_stock, by_name)
        if issuer is None:
            unresolved.append({**security, "mapping": provenance})
            continue
        corp_code = issuer["corpCode"]
        entry = issuers.setdefault(corp_code, {
            "issuerId": f"DART:{corp_code}",
            "corpCode": corp_code,
            "corpName": issuer.get("corpName") or None,
            "securities": [],
            "mappingProvenance": [],
        })
        entry["securities"].append(security)
        entry["mappingProvenance"].append({
            "securityId": security["securityId"], **provenance,
            "source": "DART:corpCode.xml",
        })

    issuer_rows = []
    for corp_code, issuer in sorted(issuers.items()):
        issuer["securities"] = sorted(issuer["securities"], key=lambda row: row["ticker"])
        issuer["mappingProvenance"] = sorted(
            issuer["mappingProvenance"], key=lambda row: row["securityId"])
        issuer["currentUniverse"] = any(row["currentUniverse"] for row in issuer["securities"])
        issuer["historicalOnly"] = not issuer["currentUniverse"]
        issuer_rows.append(issuer)

    all_dates = [date for security in securities
                 for date in (security.get("listed"), security.get("delisted")) if date]
    return {
        "contract": CONTRACT,
        "name": UNIVERSE_NAME,
        "identityGrain": "DART_CORP_CODE_ISSUER",
        "membershipSource": "signal-history:ledger/universe-history.json",
        "nameSource": "signal-history:ledger/universe/kr/krx-universe-*.jsonl.gz",
        "supportedPeriod": {
            "start": min(all_dates) if all_dates else None,
            "end": max(all_dates) if all_dates else None,
        },
        "securityCount": len(securities),
        "currentUniverseSecurityCount": sum(row["currentUniverse"] for row in securities),
        "historicalOnlySecurityCount": sum(not row["currentUniverse"] for row in securities),
        "issuerCount": len(issuer_rows),
        "currentUniverseIssuerCount": sum(row["currentUniverse"] for row in issuer_rows),
        "historicalOnlyIssuerCount": sum(row["historicalOnly"] for row in issuer_rows),
        "successfullyMappedDartCorpCodes": len(issuer_rows),
        "unresolvedIdentityCount": len(unresolved),
        "issuers": issuer_rows,
        "unresolved": sorted(unresolved, key=lambda row: row["ticker"]),
    }


def ticker_at(securities: list[dict], available_from: str) -> str | None:
    """Security identity valid when the filing became public, if unique."""
    active = []
    for row in securities:
        listed = row.get("listed")
        delisted = row.get("delisted")
        if (not listed or listed <= available_from) and (not delisted or available_from < delisted):
            active.append(row["ticker"])
    if len(active) == 1:
        return active[0]
    current = [row["ticker"] for row in securities if row.get("currentUniverse")]
    return current[0] if len(current) == 1 else None
