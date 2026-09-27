"""Raw DART rows into `DART_RAW_FILINGS_V1`-shaped records, by IFRS element as well as label.

THE ONE CHANGE, AND THE EVIDENCE FOR IT. `dart_fundamentals.match_account`
accepts a row only when its label is on a short alias list. The four accounts
the v4 accounting features read -- net income, operating cash flow, total
assets, total liabilities -- are additionally accepted here when the row's
`account_id` is the IFRS element those same accounts carry when the label
DID match. Measured on the sealed store (`kr-accounting-coverage-audit.json`,
`accountIdsUnderExactLabelMatch`): of 2,700 label-matched `당기순이익` rows,
every IS/CIS row but 16 carries `ifrs-full_ProfitLoss`/`ifrs_ProfitLoss` (the
16 carry DART's "-표준계정코드 미사용-", no standard element); of 3,900
`영업활동현금흐름` rows all but 22 carry `...CashFlowsFromUsedInOperating
Activities`; of 4,357 `자산총계` and 4,355 `부채총계` rows all but 2 and 1
carry `...Assets`/`...Liabilities`. An element id is the filer's own
statement of WHAT a line is; a label is how they chose to word it. Matching
on the element is therefore not a looser rule than the alias list -- it is
the definition the alias list was approximating. Which labels the element
rule actually admits is published by the rebuild
(`scripts/build_kr_canonical_filings.py`) from DART's raw rows, for review,
before any snapshot built from it is frozen.

WHAT IS NEVER MAPPED. Only the exact element ids above. `ProfitLoss
AttributableToOwnersOfParent` is a different element (profit attributable to
the parent) and is never taken as net income; `CashFlowsFromUsedIn
Operations` (cash generated before interest and tax, a subtotal) is never
taken as operating cash flow; no substring, prefix or fuzzy rule exists.

WHICH STATEMENT, AND WHICH ROW. Net income is taken from IS, then CIS, then
CF, never from SCE, where a row is one equity COMPONENT of the change and
`account_detail` names which. The element rule applies in IS and CIS only: a
CF profit line carries DART's own `dart_ProfitLossForStatementOfCashFlows`
(66 of the 94 CF matches in the sealed store), not `ProfitLoss`, so CF is
reached only through the unchanged exact label, as before. Levels come from
BS, operating cash flow from CF. Inside the first statement that has a
candidate, candidates that disagree on their amounts make the account
AMBIGUOUS and it is left out -- coverage is cheaper than a wrong denominator.
Every choice is recorded on the record under `canonicalization`.

OTHER ACCOUNTS ARE LEGACY, UNCHANGED. Revenue, operating income, equity and
capex are built by `dart_fundamentals.build_record` itself, called, not
re-implemented; the v4 features do not read them and this module does not
re-decide them.

NOTHING HERE READS A PRICE, A RETURN OR A LABEL.
"""
from __future__ import annotations

from . import dart_fundamentals as DF

CONTRACT = "DART_CANONICAL_FILINGS_V2"
LEGACY_EXACT_LABEL = "LEGACY_EXACT_LABEL"
IFRS_ELEMENT_ID = "IFRS_ELEMENT_ID"
AMBIGUOUS = "AMBIGUOUS"

ELEMENT_RULES: dict[str, dict] = {
    "당기순이익": {"statements": ("IS", "CIS", "CF"), "elementStatements": ("IS", "CIS"),
                "elementIds": ("ifrs-full_ProfitLoss", "ifrs_ProfitLoss")},
    "영업활동현금흐름": {"statements": ("CF",),
                   "elementIds": ("ifrs-full_CashFlowsFromUsedInOperatingActivities",
                                  "ifrs_CashFlowsFromUsedInOperatingActivities")},
    "자산총계": {"statements": ("BS",), "elementIds": ("ifrs-full_Assets", "ifrs_Assets")},
    "부채총계": {"statements": ("BS",), "elementIds": ("ifrs-full_Liabilities", "ifrs_Liabilities")},
}
# `account_detail` on a non-SCE row is "-" or absent; anything else names a
# component (an equity column, a segment) and is not the account's total.
TOTAL_DETAIL = ("", "-", None)


def _amounts(row: dict) -> dict:
    out = {}
    for field in DF.AMOUNT_FIELDS:
        if row.get(field) is not None:
            value = DF.parse_amount(row.get(field))
            if value is not None:
                out[field] = value
    return out


def resolve_account(rows: list[dict], account: str) -> tuple[dict | None, dict]:
    """(entry, provenance) for one ELEMENT_RULES account, or (None, why)."""
    rule = ELEMENT_RULES[account]
    aliases = {DF.normalize_account(a) for a in DF.WANTED_ACCOUNTS[account]}
    for statement in rule["statements"]:
        candidates = []
        for row in rows:
            if str(row.get("sj_div")) != statement or row.get("account_detail") not in TOTAL_DETAIL:
                continue
            by_label = DF.normalize_account(row.get("account_nm")) in aliases
            by_element = (statement in rule.get("elementStatements", rule["statements"])
                          and str(row.get("account_id")) in rule["elementIds"])
            if not (by_label or by_element):
                continue
            amounts = _amounts(row)
            if amounts:
                candidates.append((row, amounts, LEGACY_EXACT_LABEL if by_label else IFRS_ELEMENT_ID))
        if not candidates:
            continue
        if any(c[1] != candidates[0][1] for c in candidates[1:]):
            return None, {"rule": AMBIGUOUS, "statement": statement, "candidates": len(candidates)}
        row, amounts, how = candidates[0]
        entry = {"amounts": amounts, "accountId": row.get("account_id"),
                 "statement": row.get("sj_div"), "label": row.get("account_nm")}
        return entry, {"rule": how, "statement": statement, "label": row.get("account_nm"),
                       "accountId": row.get("account_id"), "candidates": len(candidates)}
    return None, {"rule": None}


def canonical_record(raw: dict) -> tuple[dict | None, str]:
    """One `DART_RAW_FILINGS_V1`-shaped record from one `DART_RAW_STATEMENT_ROWS_V1` record.

    The envelope (id, receipt date, receipt numbers, CFS/OFS) follows
    `dart_fundamentals.build_record` field for field, so `dart_derive`,
    `accounting_quality` and `alpha_opportunity_features` read it unchanged.
    """
    rows = raw.get("rows") or []
    if not rows:
        return None, "EMPTY_RESPONSE"
    receipts = {DF.receipt_date(r.get("rcept_no")) for r in rows} - {None}
    if not receipts:
        return None, "NO_RECEIPT_DATE"
    legacy, _ = DF.build_record(
        ticker=raw["ticker"], stock_code=raw["stockCode"], corp_code=raw["corpCode"],
        fiscal_year=raw["fiscalYear"], report_code=raw["reportCode"], rows=rows,
        fs_div=raw["fsDiv"], collected_at=raw["collectedAt"])
    accounts = {k: v for k, v in ((legacy or {}).get("accounts") or {}).items()
                if k not in ELEMENT_RULES}
    provenance = {}
    for account in ELEMENT_RULES:
        entry, how = resolve_account(rows, account)
        provenance[account] = how
        if entry is not None:
            accounts[account] = entry
    if not accounts:
        return None, "NO_WANTED_ACCOUNTS"
    return {
        "id": DF.record_id(raw["ticker"], raw["fiscalYear"], raw["reportCode"]),
        "ticker": raw["ticker"], "stockCode": raw["stockCode"], "corpCode": raw["corpCode"],
        "fiscalYear": int(raw["fiscalYear"]), "reportCode": raw["reportCode"],
        "reportName": DF.REPORT_CODES.get(raw["reportCode"], raw["reportCode"]),
        "availableFrom": min(receipts),
        "receiptNos": sorted({str(r.get("rcept_no")) for r in rows if r.get("rcept_no")}),
        "fsDiv": raw["fsDiv"],
        "accounts": accounts, "accountsFound": len(accounts),
        "accountsWanted": len(DF.WANTED_ACCOUNTS),
        "currency": "KRW",
        "source": f"DART:fnlttSinglAcntAll:{raw['fsDiv']}",
        "collectedAt": raw["collectedAt"],
        "canonicalization": {"contract": CONTRACT, "accounts": provenance,
                             "rawRecordId": raw["id"]},
    }, ""
