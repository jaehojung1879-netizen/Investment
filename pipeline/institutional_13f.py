"""SEC Form 13F snapshots for a small, explicit manager watchlist.

This is a disclosure reader, not an investment signal.  A 13F reports selected
US-listed long securities as of a quarter end and may be filed up to 45 days
later.  It does not reveal cash, shorts, most derivatives, private assets, or
trades made after the report date.  The output therefore always carries both
the report date and filing date and never calls a disclosed position "current".
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import REPO_ROOT


REGISTRY_PATH = REPO_ROOT / "data" / "institutional_managers.json"
SEC_DATA = "https://data.sec.gov"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_USER_AGENT = (
    "InvestmentResearchDashboard/1.0 "
    "https://github.com/jaehojung1879-netizen/Investment"
)


def _request(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT),
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def _fetch_json(url: str) -> dict:
    return json.loads(_request(url).decode("utf-8"))


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(node: ET.Element, name: str) -> str | None:
    wanted = name.lower()
    for child in node.iter():
        if _local(child.tag) == wanted and child.text:
            return child.text.strip()
    return None


def _number(value: str | None) -> float:
    try:
        return float((value or "0").replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def parse_information_table(raw: bytes) -> list[dict]:
    """Parse both modern namespaced and older namespace-free 13F XML."""
    root = ET.fromstring(raw)
    rows: list[dict] = []
    for node in root.iter():
        if _local(node.tag) != "infotable":
            continue
        issuer = _child_text(node, "nameOfIssuer")
        cusip = _child_text(node, "cusip")
        if not issuer or not cusip:
            continue
        rows.append({
            "issuer": issuer,
            "titleClass": _child_text(node, "titleOfClass") or "—",
            "cusip": cusip,
            "valueUsd": round(_number(_child_text(node, "value"))),
            "shares": round(_number(_child_text(node, "sshPrnamt"))),
            "shareType": _child_text(node, "sshPrnamtType") or "SH",
            "putCall": (_child_text(node, "putCall") or "").upper() or None,
        })
    return rows


def _recent_13f_filings(submissions: dict) -> list[dict]:
    recent = ((submissions.get("filings") or {}).get("recent") or {})
    keys = ("form", "accessionNumber", "filingDate", "reportDate", "primaryDocument")
    count = min((len(recent.get(k) or []) for k in keys), default=0)
    candidates = []
    for i in range(count):
        form = recent["form"][i]
        if form not in {"13F-HR", "13F-HR/A"}:
            continue
        candidates.append({k: recent[k][i] for k in keys})

    # An amendment supersedes the original for the same quarter.  The SEC feed
    # is normally newest first, but sorting makes that contract explicit.
    candidates.sort(key=lambda x: (x["reportDate"], x["filingDate"]), reverse=True)
    unique = []
    seen_reports = set()
    for row in candidates:
        if row["reportDate"] in seen_reports:
            continue
        seen_reports.add(row["reportDate"])
        unique.append(row)
    return unique[:2]


def _information_table_url(cik: str, filing: dict, fetch_json: Callable[[str], dict]) -> str:
    cik_plain = str(int(cik))
    accession_plain = filing["accessionNumber"].replace("-", "")
    base = f"{SEC_ARCHIVES}/{cik_plain}/{accession_plain}"
    index = fetch_json(f"{base}/index.json")
    items = ((index.get("directory") or {}).get("item") or [])
    xml = [
        item.get("name") for item in items
        if str(item.get("name") or "").lower().endswith(".xml")
        and str(item.get("name") or "").lower() != "primary_doc.xml"
        and ("information table" in str(item.get("type") or "").lower()
             or "info" in str(item.get("name") or "").lower()
             or "form13f" in str(item.get("name") or "").lower())
    ]
    # Some filers (notably Berkshire) use a numeric information-table file
    # name and SEC's index reports every attachment as text.gif.  A 13F-HR
    # filing has one cover XML plus one information-table XML, so the remaining
    # non-cover XML is the deterministic fallback.
    if not xml:
        xml = [
            item.get("name") for item in items
            if str(item.get("name") or "").lower().endswith(".xml")
            and str(item.get("name") or "").lower() != "primary_doc.xml"
        ]
    if not xml:
        raise ValueError("SEC filing has no information-table XML")
    return f"{base}/{xml[0]}"


def _position_key(row: dict) -> tuple[str, str, str]:
    return (row["cusip"], row.get("putCall") or "", row.get("titleClass") or "")


def _aggregate(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = _position_key(row)
        if key not in grouped:
            grouped[key] = dict(row)
        else:
            grouped[key]["valueUsd"] += row["valueUsd"]
            grouped[key]["shares"] += row["shares"]
    return sorted(grouped.values(), key=lambda x: x["valueUsd"], reverse=True)


def _changes(current: list[dict], previous: list[dict]) -> dict:
    now = {_position_key(x): x for x in current}
    before = {_position_key(x): x for x in previous}
    out = {"new": [], "increased": [], "decreased": [], "exited": []}
    for key in sorted(set(now) | set(before)):
        cur, prev = now.get(key), before.get(key)
        template = cur or prev
        item = {
            "issuer": template["issuer"], "titleClass": template["titleClass"],
            "putCall": template.get("putCall"),
            "currentShares": cur["shares"] if cur else 0,
            "previousShares": prev["shares"] if prev else 0,
            "currentValueUsd": cur["valueUsd"] if cur else 0,
            "previousValueUsd": prev["valueUsd"] if prev else 0,
        }
        if cur and not prev:
            bucket = "new"
        elif prev and not cur:
            bucket = "exited"
        elif item["currentShares"] > item["previousShares"] * 1.005:
            bucket = "increased"
        elif item["currentShares"] < item["previousShares"] * 0.995:
            bucket = "decreased"
        else:
            continue
        base = item["previousShares"]
        item["shareChangePct"] = None if base == 0 else round(
            (item["currentShares"] / base - 1) * 100, 1
        )
        out[bucket].append(item)
    for bucket in out:
        out[bucket] = sorted(
            out[bucket],
            key=lambda x: max(x["currentValueUsd"], x["previousValueUsd"]),
            reverse=True,
        )[:8]
    return out


def _build_manager(manager: dict, fetch_json=_fetch_json, fetch_bytes=_request) -> dict:
    cik = manager["cik"].zfill(10)
    submissions = fetch_json(f"{SEC_DATA}/submissions/CIK{cik}.json")
    filings = _recent_13f_filings(submissions)
    if not filings:
        raise ValueError("no recent 13F-HR filing")

    parsed = []
    for filing in filings:
        table_url = _information_table_url(cik, filing, fetch_json)
        rows = _aggregate(parse_information_table(fetch_bytes(table_url)))
        parsed.append((filing, rows, table_url))
        time.sleep(0.12)  # stay comfortably below SEC's fair-access ceiling

    current_filing, current, _ = parsed[0]
    previous_filing, previous = (parsed[1][0], parsed[1][1]) if len(parsed) > 1 else ({}, [])
    total = sum(x["valueUsd"] for x in current)
    for row in current:
        row["portfolioWeightPct"] = round(row["valueUsd"] / total * 100, 2) if total else 0.0
    accession_plain = current_filing["accessionNumber"].replace("-", "")
    filing_url = (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_plain}/"
        f"{current_filing['primaryDocument']}"
    )
    return {
        **manager,
        "status": "AVAILABLE",
        "reportDate": current_filing["reportDate"],
        "filingDate": current_filing["filingDate"],
        "previousReportDate": previous_filing.get("reportDate"),
        "filingUrl": filing_url,
        "totalValueUsd": round(total),
        "positionCount": len(current),
        "top5WeightPct": round(sum(x["portfolioWeightPct"] for x in current[:5]), 1),
        "topHoldings": current[:10],
        "changes": _changes(current, previous) if previous else None,
    }


def build(registry_path: str | Path = REGISTRY_PATH) -> dict:
    managers = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    output = []
    for manager in managers:
        try:
            output.append(_build_manager(manager))
        except Exception as exc:
            output.append({
                **manager, "status": "UNAVAILABLE", "error": type(exc).__name__,
                "noteKo": "SEC 원문을 불러오지 못해 이전 수치를 대신 표시하지 않습니다.",
            })
    available = [m for m in output if m.get("status") == "AVAILABLE"]
    latest_report = max((m["reportDate"] for m in available), default=None)
    for manager in available:
        manager["reportRecency"] = (
            "LATEST_TRACKED_QUARTER" if manager["reportDate"] == latest_report
            else "OLDER_LAST_AVAILABLE"
        )
    return {
        "source": "SEC EDGAR Form 13F-HR",
        "sourceUrl": "https://www.sec.gov/edgar/search/",
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "status": "AVAILABLE" if available else "UNAVAILABLE",
        "availableCount": len(available),
        "managerCount": len(output),
        "latestReportDate": latest_report,
        "laggedManagerCount": sum(m.get("reportRecency") == "OLDER_LAST_AVAILABLE" for m in available),
        "managers": output,
        "methodKo": (
            "분기말 보유 주식 수를 직전 분기와 비교합니다. 금액 변화는 주가 영향이 섞이므로 "
            "매수·매도 판정에 쓰지 않습니다."
        ),
        "limitationKo": (
            "13F는 분기말 기준이며 통상 최대 45일 뒤 공개됩니다. 미국 보고대상 롱 포지션 중심이라 "
            "현금·공매도·비상장·일부 해외자산과 공개 후 거래는 보이지 않습니다."
        ),
    }
