"""kr-selection-challenger-v2-accounting — LIVE prospective recorder (paper only; no order, no production weight).

    python scripts/record_kr_selection_challenger_v2.py record   <site-data.json> <ledger-dir>
    python scripts/record_kr_selection_challenger_v2.py outcomes <ledger-dir>
    python scripts/record_kr_selection_challenger_v2.py assess   <ledger-dir>

``scripts/update_ledger.py`` calls ``run_all`` after v1's recorder. ``<ledger-dir>`` is the signal-history ``ledger/`` directory: the canonical DART
store is read from ``fundamentals/kr-canonical-v2`` inside it and this study writes only ``research-strategies/<study>/``. The rules for when a
receipt is written are v1's (a finished weekly decision session, inside its receipt window, after the registered merge); additionally a run
whose vendor download priced fewer than half of the names writes nothing, so a later run in the same window can retry. Status files follow
v1's contract: one per step plus an aggregate, so a later step never hides an earlier refusal.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import kr_selection_challenger_v2 as C  # noqa: E402
from pipeline import prospective_receipt_core as CORE  # noqa: E402
from scripts import record_kr_selection_challenger as V1S  # noqa: E402

RECEIPTS, OUTCOMES, ASSESSMENT, STATUS = V1S.RECEIPTS, V1S.OUTCOMES, V1S.ASSESSMENT, V1S.STATUS
QUIET = V1S.QUIET


def study_dir(ledger_dir: Path) -> Path:
    return Path(ledger_dir) / "research-strategies" / C.STUDY


def _status(directory: Path, **fields) -> None:
    """v1's status contract for this study: each step owns ``publication-status.<action>.json`` and ``publication-status.json`` is the
    aggregate rebuilt from all of them, so a later step never overwrites an earlier step's refusal or failure."""
    action = fields["action"]
    payload = {"schema": "KR_SELECTION_CHALLENGER_STATUS_V2", "studyId": C.STUDY, "runId": os.environ.get("GITHUB_RUN_ID"),
               "attemptedAt": str(CORE.system_utc_now().isoformat()), "productionEffect": "NONE", **fields}
    directory.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    (directory / f"publication-status.{action}.json").write_text(text, encoding="utf-8")
    steps = {name: json.loads((directory / f"publication-status.{name}.json").read_text(encoding="utf-8"))
             for name in V1S.STEPS if (directory / f"publication-status.{name}.json").exists()}
    failed = sorted(n for n, v in steps.items() if v.get("status") in V1S.FAILED)
    record_step = steps.get("record", {})
    aggregate = {"schema": "KR_SELECTION_CHALLENGER_STATUS_V2", "studyId": C.STUDY, "productionEffect": "NONE",
                 "runId": os.environ.get("GITHUB_RUN_ID"), "attemptedAt": payload["attemptedAt"],
                 "status": "STEP_FAILED" if failed else "OK", "failedSteps": failed,
                 "signalRecordState": record_step.get("status", "NOT_ATTEMPTED"), "signalRecordReason": record_step.get("reason"),
                 "steps": steps}
    (directory / STATUS).write_text(json.dumps(aggregate, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(text, end="")


def _universe(site: dict) -> list[str]:
    rows = (((site.get("longTerm") or {}).get("regions") or {}).get("KR") or {}).get("validationCrossSection") or []
    return sorted({r.get("ticker") for r in rows if isinstance(r.get("ticker"), str) and C.V1.TICKER.match(r["ticker"])})


def record(site_path: Path, ledger_dir: Path) -> int:
    raw = site_path.read_bytes()
    site = json.loads(raw)
    spec = C.load_spec()
    directory = study_dir(ledger_dir)
    try:
        now = CORE.system_utc_now()
        # Every refusal that needs no data comes first, so a run that cannot record downloads nothing.
        session = C.V1.signal_session(site)
        if any(r["signalDate"] == session for r in C.read_receipts(directory / RECEIPTS, pathway=C.LIVE)):
            raise ValueError("RECEIPT_ALREADY_EXISTS: " + session)
        merged = C.merged_at_from_git()
        CORE.check_timing(signal_date=session, created_at_utc=now, now_utc=now, merged_at_utc=merged)
        accounting, store = C.load_accounting(ledger_dir)
        from pipeline.datafeed import fetch_prices
        start = str((pd.Timestamp(session) - pd.Timedelta(days=150)).date())
        frames = fetch_prices(_universe(site), start, **C.LIQUIDITY_FETCH)   # as-traded close: see liquidity_evidence
        receipt = C.build_receipt(site, hashlib.sha256(raw).hexdigest(), pathway=C.LIVE, created_at_utc=now, now_utc=now,
                                  merged_at_utc=merged, code_identity=C.live_code_identity(spec), spec=spec,
                                  spec_digest=C.spec_sha256(), accounting=accounting, store_identity=store, frames=frames)
        C.append_receipt(directory / RECEIPTS, receipt, pathway=C.LIVE)
    except ValueError as exc:
        reason = str(exc)
        quiet = any(reason.startswith(code) for code in QUIET)
        _status(directory, action="record", status="SKIPPED" if quiet else "REFUSED", reason=reason,
                siteGeneratedAt=site.get("generatedAt"))
        return 0 if quiet else 1
    books = {b: [s["ticker"] for s in receipt["books"][b]["slots"]] for b in C.BOOKS}
    _status(directory, action="record", status="RECORDED", signalDate=receipt["signalDate"], executionDate=receipt["executionDate"],
            receiptSha256=receipt["receiptSha256"], books=books, readiness=receipt["readiness"]["ready"],
            liquidity=receipt["liquidityDiagnostics"]["summary"],
            accountingNewestAvailableFrom=receipt["accountingStore"]["newestAvailableFrom"])
    return 0


def outcomes(ledger_dir: Path) -> int:
    from pipeline.datafeed import fetch_prices

    directory = study_dir(ledger_dir)
    receipts = C.read_receipts(directory / RECEIPTS, pathway=C.LIVE)
    path = directory / OUTCOMES
    existing = C.read_outcomes(path, pathway=C.LIVE)
    graded = {(o["receiptSha256"], o["horizonSessions"]) for o in existing}
    now = CORE.system_utc_now()
    due = [(r, h) for r in receipts for h in r["horizonsSessions"]
           if (r["receiptSha256"], h) not in graded and CORE.has_matured(r["executionDate"], h, now)]
    if not due:
        _status(directory, action="outcomes", status="NOTHING_MATURED", receipts=len(receipts), graded=len(existing))
        return 0
    tickers = sorted({C.BENCHMARK} | {s["ticker"] for r, _ in due for b in C.BOOKS for s in r["books"][b]["slots"]})
    frames = fetch_prices(tickers, min(r["executionDate"] for r, _ in due))
    written, deferred = [], []
    with path.open("ab") as stream:
        for receipt, horizon in sorted(due, key=lambda x: (x[0]["signalDate"], x[1])):
            row = C.build_outcome(receipt, horizon=horizon, frames=frames, now_utc=now, pathway=C.LIVE)
            if row["resolution"] == "DEFERRED":   # a later run regrades it from a fresh download; nothing is written now
                deferred.append([receipt["signalDate"], horizon, row["unresolved"], row["retryUntilSession"]])
                continue
            C.validate_outcome(row, pathway=C.LIVE)
            stream.write(CORE.canonical(row) + b"\n")
            written.append([receipt["signalDate"], horizon, row["status"], row["resolution"]])
    _status(directory, action="outcomes", status="GRADED" if not deferred else ("PARTIALLY_DEFERRED" if written else "DEFERRED"),
            written=written, deferred=deferred, vendorFrames=len(frames))
    return 0


def assess(ledger_dir: Path) -> int:
    spec = C.load_spec()
    directory = study_dir(ledger_dir)
    receipts = C.read_receipts(directory / RECEIPTS, pathway=C.LIVE)
    graded = C.read_outcomes(directory / OUTCOMES, pathway=C.LIVE)
    risk = spec["assessment"]["primary"]["riskPath"]
    paths = None
    if len(receipts) > risk["endReceipt"]:
        from pipeline.datafeed import fetch_prices

        names = sorted({C.BENCHMARK} | {s["ticker"] for r in receipts[:risk["endReceipt"]] for b in C.BOOKS
                                        for s in r["books"][b]["slots"]})
        frames = fetch_prices(names, receipts[0]["executionDate"])
        paths = {book: C.V1.paper_path(receipts, frames, book, every=risk["rebalanceEveryReceipts"], end_receipt=risk["endReceipt"])
                 for book in (*C.BOOKS, "CTRL_ETF")}
    report = C.assess(receipts, graded, spec, path_metrics=paths)
    report["riskPaths"] = paths
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ASSESSMENT).write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    _status(directory, action="assess", status="ASSESSED",
            verdicts={b: v["verdict"] for b, v in report["challengers"].items()}, receipts=len(receipts))
    return 0


def run_all(site_path: Path, ledger_dir: Path) -> int:
    """record, then outcomes, then assess; each runs even if an earlier one failed, and a step that raised is persisted as EXCEPTION.
    Called by scripts/update_ledger.py."""
    codes = []
    for name, step in zip(V1S.STEPS, (lambda: record(site_path, ledger_dir), lambda: outcomes(ledger_dir), lambda: assess(ledger_dir))):
        try:
            codes.append(step())
        except Exception as exc:  # noqa: BLE001 - one step's failure is reported, not fatal to the next
            print(f"kr-selection-challenger-v2 step failed: {type(exc).__name__}: {exc}")
            _status(study_dir(ledger_dir), action=name, status="EXCEPTION", error=f"{type(exc).__name__}: {exc}")
            codes.append(1)
    return max(codes)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 3 and argv[0] == "record":
        return record(Path(argv[1]), Path(argv[2]))
    if len(argv) == 2 and argv[0] in ("outcomes", "assess"):
        return (outcomes if argv[0] == "outcomes" else assess)(Path(argv[1]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
