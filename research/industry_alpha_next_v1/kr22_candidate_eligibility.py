"""Candidate (not adopted) KR22 eligibility under three explicitly named proposals, beside the unchanged frozen gates.

SOURCE AND CALENDAR ONLY. No price, return, label value or outcome is read. Every frozen gate in
`kr22-source-recovery.json` is reported as it is; the candidate columns say what WOULD change if a named proposal
were approved by independent audit and the owner. Nothing here enters `data/kr-terminal-corporate-actions.json` or
any foundation file.

Proposals evaluated (all OPEN, none approved):
  A  table-form KSIC statement in the issuer's own periodic filing (012510; `industry-admission-rule-proposal.md`).
  B' a stated 4-digit KSIC code whose 3-digit parent is corroborated by a public government-institute linkage table
     (산업연구원 ISTANS-KSIC, 9th and 10th editions) in place of the Statistics Korea codebook, which this environment
     could not reach (042670 C2924 -> C292).
  E  ex-date semantics: a dividend whose record date is stated in the filing is admissible for a label when the label's
     inclusion of that dividend is identical for every ex-date from the record session back two sessions (T+1..T+3
     settlement conventions). The frozen rule admits only a DIRECT ex-date; E never derives one, it proves the label
     does not depend on which one it is.
  T  terminal economics: complete when every MATERIALLY_BLOCKING amendment of the security is verified on the original
     (`kr22-real-data-verification.json`), the common-share ratio is the repository's human-reviewed value, the
     acquirer's own 증권발행실적보고서(합병등) states the effective date and no cash consideration, and its issuer header
     is the acquirer (`kr22-terminal-execution-evidence.json`).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from pipeline import replay_calendar as RC

from . import kr22_recovery as K

HERE = Path(__file__).resolve().parent
REPORT = HERE / "kr22-candidate-eligibility.json"
EX_DATE_LAG_SESSIONS = (0, 1, 2)
HORIZONS = (126, 252)
INDUSTRY_A = ("012510.KS",)
INDUSTRY_B_PRIME = ("042670.KS",)


def _days():
    return pd.DatetimeIndex(RC.sessions("2012-12-01", "2027-12-31", "KR"))


def ex_date_candidates(record_date, days):
    """The record session (last session on or before the stated record date) and the two sessions before it."""
    rd = pd.Timestamp(record_date)
    i = int(days.searchsorted(rd, side="right")) - 1
    return [days[i - k] for k in EX_DATE_LAG_SESSIONS if i - k >= 0]


def label_windows(code, src, last_trading, days, horizon):
    """(entry, exit) sessions of every in-window month-end label that ends before the last trading date."""
    month_end = pd.Series(days, index=days).groupby(days.to_period("M")).max()
    last = pd.Timestamp(last_trading) if last_trading else None
    out = []
    for month in K._window_months(code, src):
        signal = month_end.get(pd.Period(month, "M"))
        if signal is None:
            continue
        entry = int(days.searchsorted(signal, side="right"))
        exit_ = entry + horizon
        if exit_ < len(days) and (last is None or days[exit_] < last):
            out.append((days[entry], days[exit_]))
    return out


def ex_date_invariance(events, windows, days):
    """Count labels whose dividend inclusion would change with the ex-date choice. A dividend is earned by a holding
    from the entry close to the exit close iff entry < ex-date <= exit."""
    ambiguous = 0
    for entry, exit_ in windows:
        for record in events:
            inclusion = {entry < c <= exit_ for c in ex_date_candidates(record, days)}
            ambiguous += len(inclusion) > 1
    return ambiguous


def build(root=K.ROOT):
    verification = json.loads((HERE / "kr22-real-data-verification.json").read_text())
    execution = json.loads((HERE / "kr22-terminal-execution-evidence.json").read_text())
    recovery = json.loads((HERE / "kr22-source-recovery.json").read_text())
    rec = {s["code"]: s for s in json.loads((HERE / "kr22-recovery.json").read_text())["securities"]}
    src = K.load(root)[0]
    days = _days()
    in_window = sorted(q["code"] for q in recovery["requests"])
    events = {}
    for r in verification["dividend"]:
        if r["stage3Identity"] == "VERIFIED" and r["stage4"]["recordDate"]:
            events.setdefault(r["ticker"], []).append(r["stage4"]["recordDate"])
    mb_ok = set(verification["summary"]["terminal"]["securitiesWithEveryMateriallyBlockingAmendmentVerified"])
    executed = {r["oldSecurity"]: r for r in execution["rows"]
                if r["executionReport"]["issuerHeaderIsAcquirer"] and r["effectiveDate"]
                and r["reviewedRatio"]["commonShareRatio"]}
    rows = []
    for s in recovery["securities"]:
        code, frozen = s["code"], s["gatesAfter"]
        last = rec[code].get("lastTradingDate")
        complete_frozen = frozen["terminalConsiderationResolved"] and frozen["executionConfirmed"]
        complete_t = complete_frozen or (code in mb_ok and (code in executed or frozen["executionConfirmed"]))
        labels = {h: label_windows(code, src, last, days, h) for h in HORIZONS}
        crossing = {h: rec[code]["labelWindowCrossesTermination"]["H%d" % h] or 0 for h in HORIZONS}
        has_events = code in events
        ambiguous = {h: ex_date_invariance(events.get(code, []), labels[h], days) for h in HORIZONS}
        ex_e = has_events and all(v == 0 for v in ambiguous.values())
        industry = "A" if code in INDUSTRY_A else ("B_PRIME" if code in INDUSTRY_B_PRIME else None)
        terminal_needed = any(crossing.values())
        rows.append({"code": code, "inStudyWindow": code in in_window, "frozenGates": frozen,
                     "terminalEconomicsComplete": {"frozen": bool(complete_frozen), "candidateT": bool(complete_t)},
                     "dividendEventsVerified": len(events.get(code, [])), "exDateAmbiguousLabels": ambiguous,
                     "exDateCandidateE": bool(ex_e), "industryCandidate": industry,
                     "nonCrossingLabels": {h: len(labels[h]) for h in HORIZONS}, "crossingLabels": crossing,
                     "totalReturnLabelCandidate": {
                         "A_E": industry == "A" and ex_e and (not terminal_needed or complete_t),
                         "A_Bprime_E": industry in ("A", "B_PRIME") and ex_e and (not terminal_needed or complete_t)}})
    eligible = {k: [r["code"] for r in rows if r["totalReturnLabelCandidate"][k]] for k in ("A_E", "A_Bprime_E")}

    def member_months(codes, h):
        return sum(r["nonCrossingLabels"][h] + (r["crossingLabels"][h] if r["terminalEconomicsComplete"]["candidateT"] else 0)
                   for r in rows if r["code"] in codes)
    complete_frozen = [r["code"] for r in rows if r["terminalEconomicsComplete"]["frozen"]]
    complete_t = [r["code"] for r in rows if r["terminalEconomicsComplete"]["candidateT"]]
    crossing_cov = {f"H{h}": {"total": sum(r["crossingLabels"][h] for r in rows),
                              "frozen": sum(r["crossingLabels"][h] for r in rows if r["code"] in complete_frozen),
                              "candidateT": sum(r["crossingLabels"][h] for r in rows if r["code"] in complete_t)} for h in HORIZONS}
    all_labels = {h: sum(r["nonCrossingLabels"][h] for r in rows if r["dividendEventsVerified"]) for h in HORIZONS}
    summary = {
        "denominator": len(rows), "inStudyWindow": len(in_window),
        "studyWindowTop120MemberMonths": sum(len(K._window_months(c, src)) for c in src["top120"]["securities"]),
        "terminated22StudyWindowMemberMonths": sum(rec[r["code"]]["studyWindowMemberMonths"] for r in rows),
        "industryEligible": {"frozen": 0, "candidateA": len(INDUSTRY_A), "candidateA_Bprime": len(INDUSTRY_A + INDUSTRY_B_PRIME)},
        "terminalEconomicsComplete": {"frozen": len(complete_frozen), "candidateT": len(complete_t), "securities": complete_t},
        "crossingLabelsWithCompleteTerminalEconomics": crossing_cov,
        "exDate": {"frozen": 0, "candidateE": sum(r["exDateCandidateE"] for r in rows),
                   "ambiguousLabels": {f"H{h}": sum(r["exDateAmbiguousLabels"][h] for r in rows) for h in HORIZONS},
                   "labelsChecked": {f"H{h}": all_labels[h] for h in HORIZONS},
                   "securitiesWithoutVerifiedDividendDecision": sorted(c for c in in_window if c not in events)},
        "totalReturnLabelEligible": {"frozen": 0, "candidateA_E": len(eligible["A_E"]), "candidateA_Bprime_E": len(eligible["A_Bprime_E"]),
                                     "securities": eligible},
        "eligibleMemberMonths": {"frozen": {"H126": 0, "H252": 0},
                                 "candidateA_E": {f"H{h}": member_months(eligible["A_E"], h) for h in HORIZONS},
                                 "candidateA_Bprime_E": {f"H{h}": member_months(eligible["A_Bprime_E"], h) for h in HORIZONS}}}
    return {"contract": "KR22_CANDIDATE_ELIGIBILITY_V1", "evidenceClass": "CANDIDATE_UNDER_OPEN_PROPOSALS_NOT_ADOPTED",
            "historicalOutcomesRead": 0, "pricesRead": 0, "proposals": ["A", "B_PRIME", "E", "T"], "frozenGatesChanged": False,
            "summary": summary, "securities": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output", default=str(REPORT))
    args = ap.parse_args(argv)
    out = build()
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(json.dumps(out["summary"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
