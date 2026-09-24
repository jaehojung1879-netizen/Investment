"""CUSIP / issuer-name -> ticker identity resolution for 13F holdings rows.

RESEARCH-ONLY, network-free by construction: every function here is a pure
transform over data the caller already fetched, exactly the split
``dart_fundamentals.receipt_date`` and ``scripts/probe_sec_fundamentals.
parse_companyfacts`` already use between "fetch" and "parse" — so this
module is unit-testable without a network call and is never itself the thing
that decides whether SEC is reachable.

WHY THERE IS NO FREE, OFFICIAL, BULK CUSIP -> TICKER MAP. SEC's own
``company_tickers.json`` maps CIK <-> ticker, never CUSIP; CUSIP is a
proprietary identifier administered by CUSIP Global Services, and no SEC or
other free-government source publishes a bulk CUSIP -> ticker/CIK crosswalk.
This is a structural gap, not a collection gap this module can close by
trying harder — a real solution is either a licensed CUSIP master (a cost
this data-foundation task is not authorized to incur) or a caller-supplied
mapping built some other way. This module is deliberately built to ACCEPT
such a mapping (``cusip_map``) rather than assume one; with none supplied,
every row resolves by name or is left ``UNRESOLVED``, and both facts are
reported rather than guessed past.

WHY A NAME MATCH IS NEVER TREATED AS CERTAIN. ``company_tickers.json``
records TODAY's legal name and ticker. A 13F row's ``issuer`` name is what
the filer wrote for a report date that may be over a decade in the past —
the issuer may have since merged, renamed, delisted, or been re-ticked. A
name match is therefore always ``NAME_FUZZY_MATCH`` with a stated
``pointInTimeRisk``, never promoted to ``EXACT_CUSIP_MATCH``, and even an
``EXACT_CUSIP_MATCH`` carries a risk flag unless the caller declares its
``cusip_map`` itself point-in-time-aware.

CONFIDENCE LEVELS: ``EXACT_CUSIP_MATCH``, ``NAME_FUZZY_MATCH``,
``UNRESOLVED``. Every resolved row keeps ALL THREE fields
(``resolvedTicker``, ``identityConfidence``, ``identityPointInTimeRisk``);
every unresolved row is ALSO listed in a separate queue rather than dropped,
so an incomplete identity layer is visible and reviewable rather than
silently shrinking the dataset.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

EXACT_CUSIP_MATCH = "EXACT_CUSIP_MATCH"
NAME_FUZZY_MATCH = "NAME_FUZZY_MATCH"
UNRESOLVED = "UNRESOLVED"
CONFIDENCE_LEVELS = (EXACT_CUSIP_MATCH, NAME_FUZZY_MATCH, UNRESOLVED)

RISK_NONE = "NONE"
RISK_MAP_NOT_KNOWN_PIT = "MAP_IS_NOT_KNOWN_POINT_IN_TIME"
RISK_NAME_INDEX_IS_CURRENT = "NAME_INDEX_IS_CURRENT_NOT_AS_OF_REPORT_DATE"

# Corporate-suffix tokens stripped repeatedly (an issuer string can carry
# more than one, e.g. "XYZ HOLDINGS INC"). This is a deterministic key
# builder, never a spell-checker: two names that normalize the same are
# treated as the same issuer, two that do not are never coerced together.
_SUFFIXES = (
    " INCORPORATED", " INC", " CORPORATION", " CORP", " COMPANY", " CO",
    " LIMITED", " LTD", " HOLDINGS", " HLDGS", " GROUP", " TRUST", " PLC",
    " LLC", " L L C", " L P", " LP", " CLASS A", " CLASS B", " CLASS C",
    " CL A", " CL B", " CL C", " COM NEW", " COM", " NEW", " DEL", " SA", " AG",
)
_PUNCT = re.compile(r"[^A-Z0-9 ]+")
_SPACES = re.compile(r"\s+")


def normalize_issuer_name(name: str | None) -> str:
    """A deterministic matching key: upper-case, punctuation stripped, common
    corporate suffixes stripped repeatedly until none remain."""
    text = " " + _SPACES.sub(" ", _PUNCT.sub(" ", (name or "").upper())).strip() + " "
    changed = True
    while changed:
        changed = False
        for suffix in _SUFFIXES:
            padded = suffix + " "
            if text.endswith(padded):
                text = text[: -len(padded)] + " "
                changed = True
    return text.strip()


@dataclass(frozen=True)
class IdentityMatch:
    cusip: str | None
    issuerNameAsFiled: str | None
    ticker: str | None
    confidence: str
    matchedNormalizedName: str | None = None
    pointInTimeRisk: str = RISK_NONE


def build_name_index(company_tickers_payload: dict) -> dict[str, str]:
    """SEC ``company_tickers.json`` rows -> {normalized name: ticker}.

    A normalized name shared by more than one CIK (two tickers whose legal
    names collapse to the same key) is dropped from the index entirely
    rather than resolved to either one — an ambiguous name is not a match.
    """
    counts: dict[str, int] = {}
    tickers: dict[str, str] = {}
    for row in (company_tickers_payload or {}).values():
        key = normalize_issuer_name(str(row.get("title") or ""))
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        tickers[key] = str(row.get("ticker") or "").upper()
    return {key: ticker for key, ticker in tickers.items() if counts[key] == 1 and ticker}


def resolve_one(cusip: str | None, issuer_name: str | None, *,
                cusip_map: dict[str, str] | None = None,
                cusip_map_is_point_in_time: bool = False,
                name_index: dict[str, str] | None = None) -> IdentityMatch:
    """One row's identity, in priority order: exact CUSIP, then normalized
    name, else UNRESOLVED. Never guesses past either tier."""
    cusip_map = cusip_map or {}
    if cusip and cusip in cusip_map and cusip_map[cusip]:
        return IdentityMatch(
            cusip, issuer_name, cusip_map[cusip], EXACT_CUSIP_MATCH,
            pointInTimeRisk=RISK_NONE if cusip_map_is_point_in_time else RISK_MAP_NOT_KNOWN_PIT)
    if name_index:
        key = normalize_issuer_name(issuer_name)
        hit = name_index.get(key) if key else None
        if hit:
            return IdentityMatch(cusip, issuer_name, hit, NAME_FUZZY_MATCH,
                                  matchedNormalizedName=key, pointInTimeRisk=RISK_NAME_INDEX_IS_CURRENT)
    return IdentityMatch(cusip, issuer_name, None, UNRESOLVED)


def resolve_rows(rows: list[dict], *, cusip_map: dict[str, str] | None = None,
                 cusip_map_is_point_in_time: bool = False,
                 name_index: dict[str, str] | None = None) -> tuple[list[dict], list[dict]]:
    """Every 13F row gets an identity block attached; every UNRESOLVED row is
    ALSO returned in its own queue, never silently dropped from the first list.
    """
    resolved: list[dict] = []
    unresolved: list[dict] = []
    for row in rows:
        cusip = row.get("CUSIP") or row.get("cusip")
        issuer = row.get("issuer")
        match = resolve_one(cusip, issuer, cusip_map=cusip_map,
                            cusip_map_is_point_in_time=cusip_map_is_point_in_time,
                            name_index=name_index)
        out = dict(row)
        out["resolvedTicker"] = match.ticker
        out["identityConfidence"] = match.confidence
        out["identityPointInTimeRisk"] = match.pointInTimeRisk
        resolved.append(out)
        if match.confidence == UNRESOLVED:
            unresolved.append({
                "cusip": cusip, "issuer": issuer,
                "managerCIK": row.get("managerCIK"), "reportDate": row.get("reportDate"),
                "accessionNumber": row.get("accessionNumber"),
            })
    return resolved, unresolved
