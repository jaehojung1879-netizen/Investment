"""Connect the entry-state shadow ledger (#304) to economic-path-readout-v1 (#305) on real inputs. Write-once.

    python scripts/run_entry_state_shadow_readout_connection.py --signal-history <sha> --config-commit <sha> --out <new dir>

Three evidence classes are produced and never pooled:
  PROSPECTIVE_PAPER-shape  the real published weekly decision on signal-history, recorded by the writer's own clock into a
                           ledger copy inside --out (NOT signal-history: no live receipt is created by this script), then
                           advanced with a live vendor fetch. A fill is only ever made at a final session after recording.
  HISTORICAL_DEVELOPMENT   the committed entry-state-role-etf-residual-v1 NAV read through the readout core.
  SYNTHETIC                a fixed two-week invented path through the same envelope and core (contract check only).
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from pipeline import entry_state_shadow_ledger as L                     # noqa: E402
from research.economic_path_readout_v1.core import compare             # noqa: E402
import record_entry_state_shadow as R                                   # noqa: E402

SOURCES = ("ledger/research-strategies/current-champion-decisions-v1/latest.json", "ledger/weekly-decisions/latest.json")
HIST = "research/entry_state_role_etf_residual_v1/"


def git(*args) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True).stdout


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slim(summary: dict) -> dict:
    """The readout's own fields that a reader needs; nothing recomputed."""
    full = summary["scopes"]["FULL"]
    keep = ("cagrPct", "cumulativeReturnPct", "observedMddPct", "observations", "from", "through")
    return {"pairedCalendar": summary["pairedCalendar"], "dailyMdd": summary["dailyMdd"],
            "candidate": {k: (full["candidate"] or {}).get(k) for k in keep},
            "benchmark": {k: (full["benchmark"] or {}).get(k) for k in keep},
            "cagrGapPp": full["cagrGapPp"], "observedPathVerdict": full["observedPathVerdict"],
            "windows": {k: ({"measured": v.get("measuredWindows"), "meanExcessPp": v.get("meanExcessReturnPp"),
                             "statusCounts": v.get("statusCounts")} if "measuredWindows" in v else v)
                        for k, v in full["windows"].items()},
            "costBasisMatches": summary["costBasisMatches"], "economicBasisMatches": summary["economicBasisMatches"],
            "excessLabel": summary["excessLabel"], "investmentConclusion": summary["investmentConclusion"]}


def real_input(out: Path, signal_history: str, config_commit: str) -> dict:
    src = out / "inputs"
    src.mkdir(parents=True)
    pins = {}
    for path in SOURCES:
        data = git("show", f"{signal_history}:{path}")
        (src / Path(path).name.replace("latest", Path(path).parent.name)).write_bytes(data)
        pins[path] = {"blob": git("rev-parse", f"{signal_history}:{path}").decode().strip(), "sha256": sha(data)}
    config = git("show", f"{config_commit}:config.json")
    (src / "config.json").write_bytes(config)
    pins["config.json"] = {"commit": config_commit, "sha256": sha(config)}
    ledger = out / "ledger"
    code = R.run(src / "current-champion-decisions-v1.json", src / "weekly-decisions.json", src / "config.json", ledger,
                 offline=False, source_commit=signal_history, config_commit=config_commit)
    status = json.loads((ledger / "publication-status.json").read_text())
    decisions = [json.loads(s) for s in (ledger / "decisions.jsonl").read_text().splitlines()]
    try:
        pair = L.readout_input(ledger, "KR:CURRENT_POLICY", status["atUtc"][:10])
        readout = slim(compare(pair["candidate"], pair["benchmark"], pair["asOfDate"])[0])
    except ValueError as exc:
        readout = {"status": "NOT_YET_POSSIBLE", "reason": str(exc)}
    # Same adapter the accounting used: does the vendor serve the exact signal-session origin, and through when?
    close = R.live_closes(ledger)
    origin_check = {t: {"origin": o, "originQuoteServed": close(t, o) is not None,
                        "publishedThrough": close.quote_through.get(t)}
                    for t, o in sorted(close.valuation_origins.items())}
    return {"evidenceClass": "PROSPECTIVE_PAPER_SHAPE_REAL_INPUT_NOT_A_SIGNAL_HISTORY_RECEIPT", "exitCode": code,
            "signalHistoryCommit": signal_history, "sourcePins": pins,
            "recordedAtUtc": decisions[0]["recordedAtUtc"],
            "executionSessions": sorted({(d["region"], d["executionSession"]) for d in decisions}),
            "decisionReport": status["report"]["decisions"], "accounting": status["report"].get("accounting"),
            "statusReport": status["report"]["readout"], "readout": readout, "originQuoteCheck": origin_check,
            "ledgerFileSha256": {n: sha((ledger / n).read_bytes()) for n in L.FILES if (ledger / n).exists()}}


def historical(head: str) -> dict:
    files = {p: (ROOT / HIST / p).read_bytes() for p in ("nav-daily.csv.gz", "result.json", "spec.json")}
    committed = git("log", "-1", "--format=%H", "--", HIST + "nav-daily.csv.gz").decode().strip()
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(files["nav-daily.csv.gz"]).decode())))
    study = json.loads(files["result.json"])["studyId"]

    def envelope(sid, instrument=None):
        mine = [r for r in rows if r["strategyId"] == sid]
        r = mine[0]
        return {"region": r["region"], "strategyId": sid, "studyId": study, "currency": r["currency"],
                "frequency": "DAILY", "returnBasis": r["returnBasis"],
                # Explicit: the ETF-only line never trades, so its already-charged cost is zero. Raw label kept.
                "costBasis": "NET_ALREADY_CHARGED", "originalCostBasis": r["costBasis"],
                "evidenceClass": r["evidenceClass"], "sourceCommit": committed,
                "hashes": {p: sha(b) for p, b in files.items()},
                "samplingMeaning": "KRX_UNION_NYSE_OBSERVATION_GRID_NOT_REGIONAL_SESSIONS",
                **({"instrument": instrument} if instrument else {}),
                "nav": [[x["date"], float(x["nav"])] for x in mine]}

    pairs = {"KR:N5:IN_RANK vs 069500.KS": ("KR:ENTRY_IN_RANK:N5:ETF", "KR:ETF_ONLY:069500.KS", "069500.KS"),
             "KR:N5:AT_WEIGHT vs 069500.KS": ("KR:ENTRY_AT_WEIGHT:N5:ETF", "KR:ETF_ONLY:069500.KS", "069500.KS"),
             "US:N5:IN_RANK vs SPY": ("US:ENTRY_IN_RANK:N5:ETF", "US:ETF_ONLY:SPY", "SPY"),
             "US:N5:AT_WEIGHT vs SPY": ("US:ENTRY_AT_WEIGHT:N5:ETF", "US:ETF_ONLY:SPY", "SPY"),
             "US:N5:AT_WEIGHT vs QQQ (separate)": ("US:ENTRY_AT_WEIGHT:N5:ETF", "US:SEPARATE_COMPARISON:QQQ", "QQQ")}
    out = {}
    for label, (cand, bench, instrument) in pairs.items():
        summary, _ = compare(envelope(cand), envelope(bench, instrument), "2026-11-01")
        out[label] = slim(summary)
    return {"evidenceClass": "HISTORICAL_DEVELOPMENT", "readAtHead": head, "fileCommittedAt": committed,
            "fileSha256": {p: sha(b) for p, b in files.items()},
            "selection": "the frozen primary N=5 (legacy target, not an optimum) for both rungs; no other N read",
            "notes": ["Not a rename of the #305 fixed-head claude-connection.json (head d3783d00, KR in-rank only); a "
                      "separate read at this head, adding the at-weight rung, US vs SPY and QQQ separately.",
                      "The grid is KRX-union-NYSE observations, so the readout reports H126/H252 UNAVAILABLE."],
            "pairs": out}


def synthetic(out: Path) -> dict:
    from datetime import datetime, timezone
    sys.path.insert(0, str(ROOT / "tests"))
    from test_entry_state_shadow_ledger import SUNDAY, observation
    ledger = out / "synthetic-ledger"
    L.append_decisions(ledger, L.decision_receipts(observation(), recorded_at=SUNDAY, code={"commit": "synthetic"},
                                                   observation_sha256="synthetic"))
    days = L.region_sessions("KR", "2026-10-30", "2026-11-13")
    frames = {t: pd.DataFrame({"Close": [100 * s ** i for i in range(len(days))]}, index=pd.to_datetime(days))
              for t, s in (("000001.KS", 1.01), ("069500.KS", 1.005))}
    close = L.anchored_closes(frames, {"000001.KS": days[0], "069500.KS": days[0]}, [])
    now = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
    first = L.advance(ledger, now=now, close_of=close, through=days[-1])
    rerun = L.advance(ledger, now=now, close_of=close, through=days[-1])
    pair = L.readout_input(ledger, "KR:N1:IN_RANK", "2026-11-14")
    return {"evidenceClass": "SYNTHETIC", "firstRun": first, "rerun": rerun,
            "readout": slim(compare(pair["candidate"], pair["benchmark"], pair["asOfDate"])[0])}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-history", required=True)
    parser.add_argument("--config-commit", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(f"refusing to overwrite {args.out}")
    head = git("rev-parse", "HEAD").decode().strip()
    code = {rel: sha((ROOT / rel).read_bytes()) for rel in
            ("pipeline/entry_state_shadow_ledger.py", "scripts/record_entry_state_shadow.py",
             "scripts/entry_state_shadow_observation.mjs", "scripts/run_entry_state_shadow_readout_connection.py",
             "research/economic_path_readout_v1/core.py")}
    result = {"connection": "entry-state-shadow -> economic-path-readout-v1", "version": "readout-connection-v2",
              "codeHead": head, "codeSha256": code,
              "realInput": real_input(args.out, args.signal_history, args.config_commit),
              "historical": historical(head), "synthetic": synthetic(args.out),
              "promotionEligible": False, "liveValidated": False, "productionChanged": False,
              "ordersPlaced": 0}
    (args.out / "connection.json").write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False,
                                                         allow_nan=False, default=list) + "\n")
    print(json.dumps({"realInput": result["realInput"]["readout"], "accounting": result["realInput"]["accounting"],
                      "historicalPairs": {k: v["cagrGapPp"] for k, v in result["historical"]["pairs"].items()}},
                     indent=1, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
