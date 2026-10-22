"""kr-selection-challenger-v1 — LIVE prospective recorder (paper only; no order, no production weight).

    python scripts/record_kr_selection_challenger.py record   <site-data.json> <study-dir>
    python scripts/record_kr_selection_challenger.py outcomes <study-dir>
    python scripts/record_kr_selection_challenger.py assess   <study-dir>

``scripts/update_ledger.py`` (the paper-ledger step of ledger.yml) calls ``run_all`` after its own work. ``record`` appends one receipt for the KR weekly decision session the artifact speaks for, if this run is inside that session's receipt
window (after its 18:00 KST finality, before the next open). Any other run writes nothing and says why; a later run in the same window
finds the receipt already recorded. ``outcomes`` grades every receipt whose horizon has matured and is not yet graded, from a fresh vendor
download. ``assess`` applies the registered rule. Each writes ``publication-status.<action>.json`` and the aggregate ``publication-status.json`` beside the ledgers; the exit code is 0 unless the
recorder itself failed.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import kr_selection_challenger as C  # noqa: E402
from pipeline import prospective_receipt_core as CORE  # noqa: E402

RECEIPTS, OUTCOMES, ASSESSMENT, STATUS = "receipts.jsonl", "outcomes.jsonl", "assessment.json", "publication-status.json"
# A refusal that only means "not this run's turn" is not a failure.
QUIET = ("NOT_A_WEEKLY_DECISION_SESSION", "RECEIPT_CREATED_AFTER_EXECUTION_OPEN_BACKDATED", "RECEIPT_CREATED_BEFORE_SIGNAL_CLOSE",
         "ARTIFACT_NOT_BUILT_ON_A_FINAL_SESSION", "RECEIPT_ALREADY_EXISTS", "SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY",
         "SIGNAL_BEFORE_REGISTERED_FLOOR")


STEPS = ("record", "outcomes", "assess")
FAILED = ("REFUSED", "EXCEPTION")


def _status(directory: Path, **fields) -> None:
    """One file per step plus an aggregate. A later step can never overwrite an earlier step's refusal or failure: each
    step owns ``publication-status.<action>.json`` and ``publication-status.json`` is rebuilt from all of them."""
    action = fields["action"]
    payload = {"schema": "KR_SELECTION_CHALLENGER_STATUS_V2", "studyId": C.STUDY, "runId": os.environ.get("GITHUB_RUN_ID"),
               "attemptedAt": str(CORE.system_utc_now().isoformat()), "productionEffect": "NONE", **fields}
    directory.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    (directory / f"publication-status.{action}.json").write_text(text, encoding="utf-8")
    steps = {}
    for name in STEPS:
        path = directory / f"publication-status.{name}.json"
        if path.exists():
            steps[name] = json.loads(path.read_text(encoding="utf-8"))
    failed = sorted(n for n, v in steps.items() if v.get("status") in FAILED)
    record_step = steps.get("record", {})
    aggregate = {"schema": "KR_SELECTION_CHALLENGER_STATUS_V2", "studyId": C.STUDY, "productionEffect": "NONE",
                 "runId": os.environ.get("GITHUB_RUN_ID"), "attemptedAt": payload["attemptedAt"],
                 "status": "STEP_FAILED" if failed else "OK", "failedSteps": failed,
                 "signalRecordState": record_step.get("status", "NOT_ATTEMPTED"), "signalRecordReason": record_step.get("reason"),
                 "steps": steps}
    (directory / STATUS).write_text(json.dumps(aggregate, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(text, end="")


def record(site_path: Path, directory: Path) -> int:
    raw = site_path.read_bytes()
    site = json.loads(raw)
    spec = C.load_spec()
    try:
        now = CORE.system_utc_now()
        receipt = C.build_receipt(site, hashlib.sha256(raw).hexdigest(), pathway=C.LIVE, created_at_utc=now, now_utc=now,
                                  merged_at_utc=C.merged_at_from_git(), code_identity=C.live_code_identity(spec), spec=spec,
                                  spec_digest=C.spec_sha256())
        C.append_receipt(directory / RECEIPTS, receipt, pathway=C.LIVE)
    except ValueError as exc:
        reason = str(exc)
        quiet = any(reason.startswith(code) for code in QUIET)
        _status(directory, action="record", status="SKIPPED" if quiet else "REFUSED", reason=reason,
                siteGeneratedAt=site.get("generatedAt"))
        return 0 if quiet else 1
    books = {b: [s["ticker"] for s in receipt["books"][b]["slots"]] for b in C.BOOKS}
    _status(directory, action="record", status="RECORDED", signalDate=receipt["signalDate"], executionDate=receipt["executionDate"],
            receiptSha256=receipt["receiptSha256"], books=books)
    return 0


def outcomes(directory: Path) -> int:
    from pipeline.datafeed import fetch_prices

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
    start = min(r["executionDate"] for r, _ in due)
    frames = fetch_prices(tickers, start)
    written = []
    with path.open("ab") as stream:
        for receipt, horizon in sorted(due, key=lambda x: (x[0]["signalDate"], x[1])):
            row = C.build_outcome(receipt, horizon=horizon, frames=frames, now_utc=now, pathway=C.LIVE)
            stream.write(CORE.canonical(row) + b"\n")
            written.append([receipt["signalDate"], horizon, row["status"]])
    _status(directory, action="outcomes", status="GRADED", written=written)
    return 0


def assess(directory: Path) -> int:
    spec = C.load_spec()
    receipts = C.read_receipts(directory / RECEIPTS, pathway=C.LIVE)
    graded = C.read_outcomes(directory / OUTCOMES, pathway=C.LIVE)
    risk = spec["assessment"]["primary"]["riskPath"]
    paths = None
    if len(receipts) > risk["endReceipt"]:
        from pipeline.datafeed import fetch_prices

        names = sorted({C.BENCHMARK} | {s["ticker"] for r in receipts[:risk["endReceipt"]] for b in C.BOOKS
                                        for s in r["books"][b]["slots"]})
        frames = fetch_prices(names, receipts[0]["executionDate"])
        paths = {book: C.paper_path(receipts, frames, book, every=risk["rebalanceEveryReceipts"], end_receipt=risk["endReceipt"])
                 for book in (*C.BOOKS, "CTRL_ETF")}
    report = C.assess(receipts, graded, spec, path_metrics=paths)
    report["riskPaths"] = paths
    (directory / ASSESSMENT).write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    _status(directory, action="assess", status="ASSESSED",
            verdicts={b: v["verdict"] for b, v in report["challengers"].items()}, receipts=len(receipts))
    return 0


def run_all(site_path: Path, directory: Path) -> int:
    """record, then outcomes, then assess; each runs even if an earlier one failed. Called by scripts/update_ledger.py."""
    codes = []
    for name, step in zip(STEPS, (lambda: record(site_path, directory), lambda: outcomes(directory), lambda: assess(directory))):
        try:
            codes.append(step())
        except Exception as exc:  # noqa: BLE001 - one step's failure is reported, not fatal to the next
            print(f"kr-selection-challenger step failed: {type(exc).__name__}: {exc}")
            _status(directory, action=name, status="EXCEPTION", error=f"{type(exc).__name__}: {exc}")
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
