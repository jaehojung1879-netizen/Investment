"""kr-selection-challenger-v2-accounting — LIVE prospective recorder (paper only; no order, no production weight).

    python scripts/record_kr_selection_challenger_v2.py record   <site-data.json> <ledger-dir>
    python scripts/record_kr_selection_challenger_v2.py outcomes <ledger-dir>
    python scripts/record_kr_selection_challenger_v2.py assess   <ledger-dir>

``scripts/update_ledger.py`` calls ``run_all`` after v1's recorder. ``<ledger-dir>`` is the signal-history ``ledger/`` directory: the canonical DART
store is read from ``fundamentals/kr-canonical-v2`` inside it and this study writes only ``research-strategies/<study>/``. The rules for when a
receipt is written are v1's (a finished weekly decision session, inside its receipt window, after the registered merge); additionally a run
whose vendor download priced fewer than half of the names writes nothing, so a later run in the same window can retry.
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
    payload = {"schema": "KR_SELECTION_CHALLENGER_STATUS_V1", "studyId": C.STUDY, "runId": os.environ.get("GITHUB_RUN_ID"),
               "attemptedAt": str(CORE.system_utc_now().isoformat()), "productionEffect": "NONE", **fields}
    directory.mkdir(parents=True, exist_ok=True)
    (directory / STATUS).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


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
        frames = fetch_prices(_universe(site), start)
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
    written = []
    with path.open("ab") as stream:
        for receipt, horizon in sorted(due, key=lambda x: (x[0]["signalDate"], x[1])):
            row = C.build_outcome(receipt, horizon=horizon, frames=frames, now_utc=now, pathway=C.LIVE)
            stream.write(CORE.canonical(row) + b"\n")
            written.append([receipt["signalDate"], horizon, row["status"]])
    _status(directory, action="outcomes", status="GRADED", written=written)
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
    """record, then outcomes, then assess; each runs even if an earlier one failed. Called by scripts/update_ledger.py."""
    codes = []
    for step in (lambda: record(site_path, ledger_dir), lambda: outcomes(ledger_dir), lambda: assess(ledger_dir)):
        try:
            codes.append(step())
        except Exception as exc:  # noqa: BLE001 - one step's failure is reported, not fatal to the next
            print(f"kr-selection-challenger-v2 step failed: {type(exc).__name__}: {exc}")
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
