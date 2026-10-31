"""Recover two unused DART balance-sheet inputs, without prices or outcomes.

Comparative columns in a later filing are deliberately never read. These
features use two separately published annual statements, not a fitted mix of
the existing quality/value/momentum scores. They are candidates, not alpha.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re

CONCEPTS = {
    "receivables": (("dart_ShortTermTradeReceivable", "ifrs-full_CurrentTradeReceivables"), "BS"),
    "inventory": (("ifrs-full_Inventories", "ifrs_Inventories"), "BS"),
    "sales": (("ifrs-full_Revenue", "ifrs_Revenue"), "FLOW"),
}
SIGNALS = ("collection_discipline", "inventory_discipline")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("INVALID_DATE")
    return date.fromisoformat(value)


def record_issues(record, as_of):
    issues = []
    try:
        visible = day(record.get("availableFrom"))
        if visible >= day(as_of):
            issues.append("NOT_YET_PUBLIC")  # same-day times are not preserved
    except (ValueError, TypeError):
        issues.append("INVALID_PUBLIC_DATE")
        visible = None
    receipts = record.get("receiptNos", [])
    if (not isinstance(receipts, list) or len(receipts) != 1
            or not isinstance(receipts[0], str) or not re.fullmatch(r"\d{14}", receipts[0])
            or visible is None or receipts[0][:8] != visible.strftime("%Y%m%d")
            or record.get("mixedReceipts") is not False):
        issues.append("UNRESOLVED_RECEIPT")
    if (not re.fullmatch(r"\d{6}\.KS", str(record.get("ticker", "")))
            or record.get("stockCode") != str(record.get("ticker", ""))[:6]
            or not re.fullmatch(r"\d{8}", str(record.get("corpCode", "")))
            or record.get("identityBasis") != "EXACT_STOCK_CODE"):
        issues.append("IDENTITY_UNRESOLVED")
    if record.get("contract") != "DART_RAW_STATEMENT_ROWS_V1":
        issues.append("WRONG_RAW_CONTRACT")
    if record.get("reportCode") != "11011" or type(record.get("fiscalYear")) is not int:
        issues.append("NOT_ANNUAL")
    if record.get("fsDiv") not in ("CFS", "OFS"):
        issues.append("STATEMENT_BASIS_UNRESOLVED")
    return issues


def matching_rows(record, field):
    concepts, statement = CONCEPTS[field]
    return [r for r in record.get("rows", []) if r.get("account_id") in concepts
            and r.get("sj_div") in (("IS", "CIS") if statement == "FLOW" else (statement,))]


def amount(record, field):
    """Exact concepts only; never equate trade+other receivables with trade AR.

    Duplicate rows, even agreeing duplicates, require context resolution.
    No label fallback, summing components, currency conversion or zero fill.
    """
    matches = matching_rows(record, field)
    if not matches:
        return None, "MISSING_CONCEPT:" + field
    if len(matches) != 1:
        return None, "AMBIGUOUS_CONCEPT:" + field
    row = matches[0]
    if row.get("currency") != "KRW" or row.get("account_detail") != "-":
        return None, "UNIT_OR_DIMENSION_UNRESOLVED:" + field
    receipts = record.get("receiptNos")
    if (not isinstance(receipts, list) or row.get("rcept_no") not in receipts
            or row.get("corp_code") != record.get("corpCode")
            or str(row.get("bsns_year")) != str(record.get("fiscalYear"))
            or row.get("reprt_code") != "11011"):
        return None, "ROW_PROVENANCE_MISMATCH:" + field
    text = str(row.get("thstrm_amount", ""))
    # OpenDART raw numeric strings are unscaled KRW, not displayed millions.
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        return None, "INVALID_AMOUNT:" + field
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None, "INVALID_AMOUNT:" + field
    if not value.is_finite() or value < 0 or (field == "sales" and value <= 0):
        return None, "NONPOSITIVE_OR_INVALID_BASE:" + field
    return value, None


def annual_pair(current, previous, as_of):
    """Higher = less balance-sheet build per unit of annual sales.

    S_AR = AR(prev)/sales(prev) - AR(now)/sales(now); inventory analogously.
    Receivable / sales and inventory / sales are intensity proxies, not DSO
    or inventory days (COGS is unavailable). Changes can reflect M&A, disposal,
    factoring or write-downs. Source qualification must separately admit those.
    """
    day(as_of)
    issues = {"CURRENT:" + x for x in record_issues(current, as_of)}
    issues.update("PREVIOUS:" + x for x in record_issues(previous, as_of))
    if (current.get("ticker") != previous.get("ticker")
            or current.get("corpCode") != previous.get("corpCode")):
        issues.add("ISSUER_CHANGED")
    if current.get("fsDiv") != previous.get("fsDiv"):
        issues.add("STATEMENT_BASIS_CHANGED")
    cy, py = current.get("fiscalYear"), previous.get("fiscalYear")
    if type(cy) is not int or type(py) is not int or cy != py + 1:
        issues.add("NONCONSECUTIVE_ANNUALS")
    out = {"asOf": as_of, "ticker": current.get("ticker"), "fiscalYear": cy,
           "filingDigests": [digest(previous), digest(current)], "signals": {},
           "status": "INPUT_CANDIDATE_ONLY_NOT_SOURCE_ADMITTED"}
    for signal, field in zip(SIGNALS, ("receivables", "inventory")):
        reasons = set(issues)
        values = []
        for label, record in (("CURRENT", current), ("PREVIOUS", previous)):
            vals = {}
            for key in ("sales", field):
                vals[key], reason = amount(record, key)
                if reason:
                    reasons.add(label + ":" + reason)
            values.append(vals)
        # Both names can be read, but their cross-version equivalence is NOT
        # assumed. Taxonomy migrations lose that pair until separately proven.
        for key in ("sales", field):
            old, new = matching_rows(previous, key), matching_rows(current, key)
            if len(old) == len(new) == 1 and old[0]["account_id"] != new[0]["account_id"]:
                reasons.add("CONCEPT_BASIS_CHANGED:" + key)
        value = None
        if not reasons:
            now, prior = values
            value = float(prior[field] / prior["sales"] - now[field] / now["sales"])
            if not math.isfinite(value):
                value = None
                reasons.add("NONFINITE_RATIO")
        out["signals"][signal] = {"value": value, "reasons": sorted(reasons)}
    return out


def visible_pair(records, ticker, as_of, max_age_days=550):
    """Select by fiscal year, not most recently delivered stale report.

    Ambiguous versions of either required fiscal year abstain. A later vintage
    never silently replaces a missing original; historical amendment fidelity
    is a separate admission blocker even when these input checks pass.
    """
    stamp = day(as_of)
    visible = []
    for r in records:
        if r.get("ticker") != ticker or r.get("reportCode") != "11011":
            continue
        try:
            if day(r.get("availableFrom")) < stamp:
                visible.append(r)
        except ValueError:
            raise ValueError("UNRESOLVED_FILING_VISIBILITY") from None
    if not visible:
        raise ValueError("NO_VISIBLE_ANNUAL")
    by_year = {}
    for r in visible:
        if type(r.get("fiscalYear")) is not int:
            raise ValueError("INVALID_FISCAL_YEAR")
        by_year.setdefault(r["fiscalYear"], []).append(r)
    year = max(by_year)
    if len(by_year[year]) != 1 or len(by_year.get(year - 1, [])) != 1:
        raise ValueError("MISSING_OR_AMBIGUOUS_ANNUAL_PAIR")
    current, previous = by_year[year][0], by_year[year - 1][0]
    # Receipt age alone would make a newly filed, years-old report look fresh.
    if (stamp - date(year, 12, 31)).days > max_age_days:
        raise ValueError("STALE_FISCAL_PERIOD")
    return annual_pair(current, previous, as_of)
