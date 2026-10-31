"""Repository-only recovery for the 22 terminated KR securities, and the DART request list for the 16 in the window.

Additive to `kr22_recovery` (whose inventory is reused, never rebuilt). It adds three things, all from bytes the
repository already holds, and reads no price, return, label or outcome:

1. EXECUTION EVIDENCE FROM AN INDEPENDENT DATED SOURCE. A stock-for-stock merger or exchange must issue the documented
   number of successor shares. The KRX monthly universe snapshots (`signal-history@4ea107ed`, the study's own pinned
   universe, blob-checked by `inputs.load_universe`) record every successor's listed share count by date. A jump in the
   successor's count across the effective date that EQUALS the filing's stated new-share count is evidence the exchange
   happened, from a source other than the filer. Share counts are not returns.
2. SUCCESSOR IDENTITY where the corporate-action book left it blank: the unique KRX security whose listed shares rose by
   the documented new-share count across the effective date.
3. A REQUEST LIST for the 16 securities with study-window membership: DART corp code, the fiscal years whose own
   periodic filing must state the security's industry, the annual-report receipt numbers the repository's DART raw
   store already holds (`signal-history@d646a69`), the failed terminal receipts to retry, and what else is missing.

Nothing here admits an industry, changes a v4 interval, or edits a sealed foundation file. Every status is a candidate
for review; the counts are reported against all 22 securities.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path

from . import inputs as IN
from . import kr22_recovery as K

DART_RAW_COMMIT = "d646a69cfc8befdf2b2ad26179c486c13d1faebd"     # last signal-history commit touching kr-raw / kr-corporate-actions
DART_RAW_YEARS = range(2015, 2027)
FETCH_STATE = "ledger/kr-corporate-actions/document-fetch-state.json"
EXACT = "EXACT_COUNT_RECONCILED"
ADJUSTED = "RECONCILED_WITHIN_DOCUMENTED_APPRAISAL_ADJUSTMENT"
PARTIAL = "ISSUANCE_OBSERVED_COUNT_NOT_IN_RETAINED_DOCUMENTS"
ADJUSTMENT_TOLERANCE = 0.001        # filings say the final count changes by shares bought back under appraisal rights
COUNT_PATTERN = re.compile(r"(?:합병)?신주의 종류와 수\(주\)\s*\|\s*보통주식\s*\|\s*([\d,]+)")
ISSUE_PATTERN = re.compile(r"발행할 예정주식수는 기명식 보통주식\s*([\d,]+)\s*주")


def documented_new_shares(code, src):
    """The new-share count stated in the security's own retained terminal filings (one value, or None)."""
    found = set()
    for doc in src["retainedTerminalDocuments"]:
        if doc["ticker"] != code:
            continue
        text = K.clean_document(" ".join(m.get("text", "") for m in doc["members"]))
        for pattern in (COUNT_PATTERN, ISSUE_PATTERN):
            found |= {int(x.replace(",", "")) for x in pattern.findall(text)}
    return found.pop() if len(found) == 1 else (None if not found else sorted(found))


def share_jump(snaps, ticker, effective):
    """(date before, shares before, date after, shares after) around the effective date, from monthly snapshots."""
    dates = [d for d in snaps.dates if snaps.by_date[d].get(ticker)]
    before = [d for d in dates if d < effective]
    after = [d for d in dates if d > effective]
    b = (before[-1], float(snaps.by_date[before[-1]][ticker]["listedShares"])) if before else (None, 0.0)
    # The new shares list some days after the effective date: take the first snapshot whose count moved, within 3.
    for d in after[:3]:
        a = float(snaps.by_date[d][ticker]["listedShares"])
        if a != b[1]:
            return b[0], b[1], d, a
    return b[0], b[1], (after[0] if after else None), (float(snaps.by_date[after[0]][ticker]["listedShares"]) if after else None)


def resolve_successor(snaps, effective, count):
    """The unique KRX security whose listed shares rose by the documented count (within tolerance) across the date."""
    hits = []
    for ticker in {t for d in snaps.dates for t in snaps.by_date[d]}:
        _, b, _, a = share_jump(snaps, ticker, effective)
        if a is not None and count and abs((a - b) - count) <= ADJUSTMENT_TOLERANCE * count:
            hits.append(ticker)
    return hits[0] if len(hits) == 1 else None


def execution_evidence(row, action, src, snaps):
    t = row["terminal"]
    ratio = action.get("successorSharesPerOldShare")
    if t["actionType"] not in ("MERGER_STOCK", "SHARE_EXCHANGE", "SHARE_TRANSFER") or not ratio:
        return {"status": "NOT_APPLICABLE_NO_DOCUMENTED_STOCK_RATIO"}
    effective = action.get("effectiveDate")
    count = documented_new_shares(row["code"], src)
    successor = action.get("successorSecurity")
    resolved_here = False
    if not successor and isinstance(count, int):
        successor, resolved_here = resolve_successor(snaps, effective, count), True
    if not successor or not effective:
        return {"status": "SUCCESSOR_OR_EFFECTIVE_DATE_UNRESOLVED", "documentedNewShares": count}
    db, b, da, a = share_jump(snaps, successor, effective)
    if a is None:
        return {"status": "NO_SNAPSHOT_AFTER_EFFECTIVE_DATE", "successor": successor}
    jump = a - b
    out = {"successor": successor, "successorResolvedHere": resolved_here and bool(successor),
           "successorNewListing": db is None,
           "effectiveDate": effective, "snapshotBefore": db, "sharesBefore": b, "snapshotAfter": da,
           "sharesAfter": a, "observedIncrease": jump, "documentedNewShares": count, "ratio": ratio,
           "impliedOldSharesExchanged": jump / ratio if ratio else None}
    if isinstance(count, int) and jump == count:
        out["status"] = EXACT
    elif isinstance(count, int) and count and abs(jump - count) <= ADJUSTMENT_TOLERANCE * count:
        out["status"] = ADJUSTED
        out["relativeGap"] = (jump - count) / count
    elif count is None and jump > 0:
        out["status"] = PARTIAL
    else:
        out["status"] = "CONTRADICTED_OR_UNRECONCILED"
    return out


def load_dart_raw(root=IN.ROOT):
    paths = [f"ledger/fundamentals/kr-raw/raw-{y}.jsonl.gz" for y in DART_RAW_YEARS] + [FETCH_STATE]
    blobs = IN.git_blobs(DART_RAW_COMMIT, paths, root)
    rows = []
    for p in paths[:-1]:
        rows.extend(json.loads(x) for x in gzip.decompress(blobs[p]).decode().splitlines() if x.strip())
    return rows, json.loads(blobs[FETCH_STATE]), {p: IN.blob_sha1(b) for p, b in blobs.items()}


def request_row(row, src, dart_rows, fetch_state, evidence, gates):
    code = row["code"]
    months = sorted(d[:7] for d in src["top120"]["securities"].get(code, {}).get("observedTop120Dates", [])
                    if K.STUDY_WINDOW[0] <= d[:7] <= K.STUDY_WINDOW[1])
    # The latest annual report visible at a month-M signal of year Y is FY Y-1 (after its filing) or FY Y-2 (before).
    years = list(range(int(months[0][:4]) - 2, int(months[-1][:4]))) if months else []
    corp = next((s.get("dartCorpCode") for s in src["reconstruction"]["securities"] if s["code"] == code), None)
    annual = {r["fiscalYear"]: (r.get("receiptNos") or [None])[0] for r in dart_rows
              if r.get("ticker") == code and r.get("reportCode") == "11011" and r.get("corpCode") == corp}
    failed = sorted(k for k, v in fetch_state["receipts"].items() if v.get("ticker") == code and v.get("status") != "SUCCESS")
    held = {y: annual[y] for y in years if y in annual}
    missing_years = [y for y in years if y not in annual]
    needs = [need for gate, need in (("industryAdmitted", "OWN_PERIODIC_FILING_INDUSTRY_STATEMENT_PER_FISCAL_YEAR"),
                                     ("terminalConsiderationResolved", "FINAL_CONSIDERATION_TERMS"),
                                     ("executionConfirmed", "EXECUTION_CONFIRMATION_DOCUMENT"),
                                     ("exDateSemanticsResolved", "SEALED_DATED_EX_DATE_RULE_WITH_SOURCE"))
             if not gates[gate]]
    if evidence["status"] == PARTIAL:
        needs.append("DOCUMENTED_NEW_SHARE_COUNT_TO_RECONCILE_OBSERVED_ISSUANCE")
    return {"code": code, "name": row["name"], "dartCorpCode": corp, "studyWindowMemberMonths": len(months),
            "labelWindowCrossesTermination": row["labelWindowCrossesTermination"],
            "industryFiscalYearsNeeded": years,
            "annualReportReceiptsHeldInRepository": held,
            "fiscalYearsNeedingListJsonQuery": missing_years,
            "listJsonQuery": ({"corp_code": corp, "bgn_de": f"{years[0]}0101", "end_de": f"{years[-1] + 1}1231",
                               "pblntf_detail_ty": "A001"} if missing_years and corp else None),
            "failedTerminalReceiptsToRetry": failed,
            "needs": needs}


def gates_after(row, evidence):
    g = dict(K.gates(row))
    g["executionConfirmed"] = g["executionConfirmed"] or evidence["status"] in (EXACT, ADJUSTED)
    if evidence.get("successorResolvedHere") and evidence["status"] in (EXACT, ADJUSTED):
        g["terminalConsiderationResolved"] = True      # ratio documented; its only blocker was the unresolved successor
    return g


def build(root=IN.ROOT):
    base = K.build(root)
    src, _ = K.load(root)
    snaps = IN.load_universe(root)
    dart_rows, fetch_state, dart_hashes = load_dart_raw(root)
    actions = {a["oldSecurity"]: a for a in src["corporateActions"]["actions"]}
    out_rows, requests = [], []
    for row in base["securities"]:
        ev = execution_evidence(row, actions[row["code"]], src, snaps)
        before, after = K.gates(row), gates_after(row, ev)
        out_rows.append({"code": row["code"], "name": row["name"], "studyWindowMemberMonths": row["studyWindowMemberMonths"],
                         "executionEvidence": ev, "gatesBefore": before, "gatesAfter": after})
        if row["studyWindowMemberMonths"] > 0:
            requests.append(request_row(row, src, dart_rows, fetch_state, ev, after))

    def count(key, which, pred=lambda r: True):
        return sum(1 for r in out_rows if r[which][key] and pred(r))

    terminal_complete = lambda r, w: r[w]["terminalConsiderationResolved"] and r[w]["executionConfirmed"]
    by = {r["code"]: r for r in base["securities"]}
    crossing = {h: {w: sum(by[r["code"]]["labelWindowCrossesTermination"][h] or 0 for r in out_rows if terminal_complete(r, w))
                    for w in ("gatesBefore", "gatesAfter")} for h in ("H126", "H252")}
    statuses = {}
    for r in out_rows:
        statuses[r["executionEvidence"]["status"]] = statuses.get(r["executionEvidence"]["status"], 0) + 1
    summary = {
        "denominator": len(out_rows),
        "executionEvidenceStatus": dict(sorted(statuses.items())),
        "executionConfirmed": {"before": count("executionConfirmed", "gatesBefore"),
                               "after": count("executionConfirmed", "gatesAfter")},
        "terminalConsiderationResolved": {"before": count("terminalConsiderationResolved", "gatesBefore"),
                                          "after": count("terminalConsiderationResolved", "gatesAfter")},
        "terminalEconomicsComplete": {"before": sum(terminal_complete(r, "gatesBefore") for r in out_rows),
                                      "after": sum(terminal_complete(r, "gatesAfter") for r in out_rows),
                                      "afterIncludingPartialIssuanceEvidence": sum(
                                          terminal_complete(r, "gatesAfter") or (
                                              r["gatesAfter"]["terminalConsiderationResolved"]
                                              and r["executionEvidence"]["status"] == PARTIAL) for r in out_rows)},
        "crossingMemberMonthsWithCompleteTerminalEconomics": crossing,
        "industryAdmitted": {"before": count("industryAdmitted", "gatesBefore"), "after": count("industryAdmitted", "gatesAfter")},
        "exDateSemanticsResolved": {"before": count("exDateSemanticsResolved", "gatesBefore"),
                                    "after": count("exDateSemanticsResolved", "gatesAfter")},
        "eligibleForIndustryTotalReturnLabel": {"before": sum(all(r["gatesBefore"].values()) for r in out_rows),
                                                "after": sum(all(r["gatesAfter"].values()) for r in out_rows)},
        "inWindowSecurities": len(requests),
        "inWindowWithAnnualReceiptsHeld": sum(bool(q["annualReportReceiptsHeldInRepository"]) for q in requests),
        "annualReceiptsHeld": sum(len(q["annualReportReceiptsHeldInRepository"]) for q in requests),
        "fiscalYearsNeedingListJsonQuery": sum(len(q["fiscalYearsNeedingListJsonQuery"]) for q in requests),
        "failedTerminalReceiptsToRetryInWindow": sum(len(q["failedTerminalReceiptsToRetry"]) for q in requests),
    }
    return {"schema": "KR22_SOURCE_RECOVERY_V1", "evidenceClass": "SOURCE_RECOVERY_NO_OUTCOME",
            "historicalOutcomesRead": 0, "pricesRead": 0, "networkUsed": False,
            "inputs": {"kr22Inventory": base["inputs"], "universeCommit": IN.S.INPUT_POLICY["signalHistoryCommit"],
                       "dartRawCommit": DART_RAW_COMMIT, "dartRawBlobSha1": dart_hashes},
            "rules": {"exact": EXACT, "adjusted": ADJUSTED, "partial": PARTIAL, "adjustmentTolerance": ADJUSTMENT_TOLERANCE,
                      "admissionNote": "Execution evidence is a candidate for review; no foundation file is edited."},
            "summary": summary, "securities": out_rows, "requests": requests}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output")
    args = ap.parse_args(argv)
    text = json.dumps(build(), indent=1, sort_keys=True, ensure_ascii=False, default=float)
    if args.output:
        Path(args.output).write_text(text + "\n")
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
