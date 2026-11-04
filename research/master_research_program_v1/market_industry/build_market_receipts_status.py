"""Operational status of market-state prospective receipts (KR and US). Outcome-free.

    git fetch --depth=1 --filter=blob:none origin signal-history
    python -m research.master_research_program_v1.market_industry.build_market_receipts_status --commit <signal-history sha>

Reads from the pinned ``signal-history`` commit ONLY: the file listing and, for receipt ledgers, the DATE fields of each row
(``signalDate``, ``executionDate``, ``createdAtUtc``) and the presence (never the value) of state keys. No state value, return,
price, label or outcome is read or printed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TODAY = "2026-11-03"
STALL_DAYS = 14   # more than one missed weekly decision session
HORIZONS = (63, 126, 252)

KR_MARKET_STUDIES = {
    "rp1-b-h1-state-v1": {
        "kind": "MARKET_STATE_RECEIPT", "writer": "scripts/record_rp1_b_h1_state.py (hook in scripts/update_ledger.py)",
        "spec": "docs/research-program/specs/rp1-b-h1-state-v1.json", "fieldsPresenceChecked": ["state.fast"],
        "candidateCoverage": {"C0": "DERIVABLE: C0 reads FAST only and the receipt stores the sealed FAST state",
                              "C1": "NOT_DERIVABLE: SLOW (10y-3m re-steepening) and TRANSITION (VIX level) are not recorded"},
    },
}
KR_CONTRACTS_WITHOUT_WRITER = {
    "kr-market-risk-model-v1": {"module": "pipeline/kr_market_risk_model_receipts.py",
                                "note": "receipt contract for all C0-C3 multipliers is designed and tested; no script writes it and no ledger exists"},
    "rp1-c-kr-risk-state-receipt-preview-v1": {"module": "pipeline/rp1_c_risk_state_receipt.py",
                                               "note": "PREVIEW only: evidenceClass PROSPECTIVE_PAPER_PREVIEW, ledgerWritten false by construction"},
    "kr-integrated-alpha-portfolio-v1": {"module": "pipeline/kr_integrated_alpha_portfolio_receipts.py",
                                         "note": "receipt contract (C0/C1-scaled books) exists; no writer script, no ledger"},
}
US_EXPECTED = {
    "C1d-PROSPECTIVE-RECEIPTS-US": {"source": "docs/research-program/07-market-industry-stock-portfolio-hierarchy-ko.md sec 2.1 (listed only)",
                                    "stateMachine": "pipeline/rp1_c1_us_exposure.py (layer_states / decision_schedule with market='US')",
                                    "note": "named as a follow-up candidate; no module, spec, writer or ledger exists"},
}
NOT_MARKET_STATE = {
    "weekly-decisions": {"path": "ledger/weekly-decisions/receipts.jsonl", "why": "weekly-passive-first-v1 stock-vs-ETF decisions; no exposure "
                         "state or multiplier (US index 100% throughout)"},
    "current-champion-decisions-v1": {"path": "ledger/research-strategies/current-champion-decisions-v1/receipts.jsonl",
                                      "why": "stock-selection champion paper observations; not a market exposure state"},
}


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def rows(commit, path):
    text = git("show", f"{commit}:{path}")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _has(row, dotted):
    cur = row
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def maturities(execution_date):
    from pipeline import kr_market_risk_anatomy as M
    import pandas as pd
    sessions = M.kr_sessions(execution_date, "2028-12-31")
    i = sessions.get_loc(pd.Timestamp(execution_date))
    return {f"H{h}": str(sessions[i + h].date()) for h in HORIZONS}


def next_weekly_session(after):
    from pipeline import prospective_receipt_core as P
    import pandas as pd
    day = pd.Timestamp(after)
    for _ in range(20):
        day = P.next_kr_session(day)
        if P.is_weekly_decision_session(day):
            return str(day.date())
    return None


def classify(last_signal, today=TODAY):
    if last_signal is None:
        return "MISSING"
    return "RECORDING" if (date.fromisoformat(today) - date.fromisoformat(last_signal)).days <= STALL_DAYS else "STALLED"


def study_status(commit, study, meta):
    base = f"ledger/research-strategies/{study}/"
    listing = [p for p in git("ls-tree", "-r", "--name-only", commit, base).splitlines() if p]
    out = {"studyId": study, **meta, "ledgerPath": "signal-history " + base, "filesPresent": sorted(Path(p).name for p in listing)}
    if base + "receipts.jsonl" not in listing:
        out.update({"receipts": 0, "status": "MISSING"})
        return out
    recs = rows(commit, base + "receipts.jsonl")
    signals = sorted(r["signalDate"] for r in recs)
    out.update({
        "receipts": len(recs), "firstSignalDate": signals[0] if signals else None, "lastSignalDate": signals[-1] if signals else None,
        "lastWriteUtc": max(r["createdAtUtc"] for r in recs) if recs else None,
        "evidenceClasses": sorted({r.get("evidenceClass") for r in recs}),
        "fieldsPresentInEveryRow": {f: all(_has(r, f) for r in recs) for f in meta.get("fieldsPresenceChecked", [])},
        "status": classify(signals[-1] if signals else None),
    })
    if recs:
        first_exec = min(r["executionDate"] for r in recs)
        out["firstExecutionDate"] = first_exec
        out["firstMaturitySessions"] = maturities(first_exec)
        out["nextExpectedSignalDate"] = next_weekly_session(signals[-1])
    if base + "publication-status.json" in listing:
        st = json.loads(git("show", f"{commit}:{base}publication-status.json"))
        out["lastStatusRun"] = {"attemptedAt": st.get("attemptedAt"), "runId": st.get("runId"), "status": st.get("status"),
                                "record": st.get("signalRecordState"), "recordReason": st.get("signalRecordReason"),
                                "outcomes": (st.get("steps", {}).get("outcomes") or {}).get("status")}
    return out


def build(commit):
    head = git("log", "-1", "--format=%H %cI", commit).split()
    tree = git("ls-tree", "-r", "--name-only", commit, "ledger/").splitlines()
    search = ("market-risk", "risk-state", "rp1-c", "exposure", "c1d", "overlay", "integrated-alpha", "market-timing")
    matches = sorted(p for p in tree if any(s in p.lower() for s in search) and not p.startswith("ledger/replay-inputs/"))
    kr = [study_status(commit, s, m) for s, m in KR_MARKET_STUDIES.items()]
    not_state = {}
    for name, meta in NOT_MARKET_STATE.items():
        recs = rows(commit, meta["path"]) if meta["path"] in tree else []
        dates = sorted(str(r.get("asOfDate")) for r in recs)
        not_state[name] = {**meta, "receipts": len(recs), "firstAsOf": dates[0] if dates else None, "lastAsOf": dates[-1] if dates else None}
    return {
        "schema": "MARKET_RECEIPTS_STATUS_V1", "outcomeFree": True, "stateValuesRead": False, "today": TODAY,
        "signalHistory": {"commit": head[0], "committedAt": head[1], "fetch": "git fetch --depth=1 --filter=blob:none origin signal-history"},
        "statusRule": f"RECORDING = last receipt signal date within {STALL_DAYS} days of today; STALLED = receipts exist but older; "
                      "MISSING = no ledger on signal-history",
        "pathsMatchingMarketPatterns": matches,
        "KR": {"ledgers": kr, "contractsWithoutWriter": {k: {**v, "status": "MISSING"} for k, v in KR_CONTRACTS_WITHOUT_WRITER.items()},
               "candidateStatus": {"C0": "RECORDING_INDIRECTLY via rp1-b-h1-state-v1 state.fast (the exposure itself is not stored)",
                                   "C1": "MISSING: no SLOW/TRANSITION recording path"}},
        "US": {"ledgers": [], "expected": {k: {**v, "status": "MISSING"} for k, v in US_EXPECTED.items()},
               "candidateStatus": {"C0": "MISSING", "C1": "MISSING"}},
        "notMarketStateReceipts": not_state,
        "missingRecordingPaths": [
            "KR C1-C3: SLOW and TRANSITION layer states (and the resulting multipliers) are not recorded; kr_market_risk_model_receipts has no writer",
            "KR C0: the multiplier is derivable from B-H1's FAST but no receipt stores the executed exposure or the 069500.KS execution",
            "US C0-C3: no state recorder, no ledger (C1d-PROSPECTIVE-RECEIPTS-US is listed only)",
        ],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--out", type=Path, default=HERE / "market_receipts_status.json")
    a = ap.parse_args(argv)
    payload = build(a.commit)
    a.out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(a.out)


if __name__ == "__main__":
    main()
