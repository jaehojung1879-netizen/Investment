"""Collect original fiscal-2015 KR quarterly filings via `fnlttXbrl.xml`.

WHY THIS IS A SEPARATE COLLECTOR, NEVER PART OF `collect_dart_raw_statements
.py`'s ORDINARY WORK LIST. The live probe (GitHub Actions run 36300578100,
`docs/kr-accounting-coverage-repair-v1.md` §3) measured `fnlttSinglAcntAll`
answering 013 for fiscal-2015 Q1/H1/Q3 on 24 of 24 real attempts across 8
tickers -- a genuine source absence for THAT endpoint. `list.json`, over the
SAME tickers and period, listed the original filings with real receipt
numbers, and `fnlttXbrl.xml` served a real ZIP for 6 of 8 sampled 2015 Q3
packages. Two different endpoints, two different historical depths; this
collector owns the one the ordinary work list cannot reach.

WHAT IS STORED, AND WHAT IS NOT. Every record is append-only, keyed by
ticker x fiscal year x report code, exactly `dart_raw_statements`'s
discipline. `availableFrom` is the ORIGINAL filing's own receipt date from
`list.json` -- never today's collection date, and never a later amendment's
receipt (`dart_xbrl_originals.select_original_filing` refuses to select one).
The served ZIP's raw bytes are NOT committed: only their SHA-256, each
entry's name and SHA-256, and the four gate accounts' CANDIDATE_UNCONFIRMED
extracted values (`dart_xbrl_statements.canonical_record_from_xbrl`) are. A
`--dump-dir` writes the raw ZIPs locally (never committed) for a human to
open directly.

EVERY OUTCOME IS RECORDED, NEVER JUST "SERVED" OR "NOT SERVED".
`dart_xbrl_originals.CLASSIFICATIONS` -- `NO_ORIGINAL_FILING_INDEX`,
`ORIGINAL_NOT_LISTED_ONLY_AMENDMENT`, `AMBIGUOUS_REPORT_MATCH`,
`XBRL_ZIP_SERVED`, `FILE_NOT_AVAILABLE_014`, `REQUEST_ERROR` -- are each a
different fact, kept in the fetch-state file rather than collapsed into a
binary success/failure.

Usage:
    python scripts/collect_dart_xbrl_originals.py <store-dir> --universe-dir <ledger/universe/kr>
        [--max-calls 1500] [--max-minutes 300] [--dump-dir <local-only-dir>]
    DART_API_KEY must be in the environment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import collector_outcomes as CO  # noqa: E402
from pipeline import dart_xbrl_originals as XO  # noqa: E402
from pipeline import dart_xbrl_statements as XS  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402
from pipeline import kr_corporate_action_events as KCA  # noqa: E402
from scripts import collect_dart_raw_statements as C  # noqa: E402

STAGES = ("11013", "11012", "11014")
CONTRACT = "DART_XBRL_ORIGINAL_STORE_V1"

# `LIST_JSON_ERROR` is this collector's own request-layer classification (a
# `list.json` call that raised or returned no rows for a reason other than a
# genuine empty index); it is not one of `dart_xbrl_originals.CLASSIFICATIONS`
# because that module never makes the `list.json` call itself.
LIST_JSON_ERROR = "LIST_JSON_ERROR"

# A request/network failure is never evidence the filing doesn't exist -- the
# same rule `dart_raw_statements.SOURCE_ABSENCE_STATUSES` already enforces one
# level down. Only `XO.REQUEST_ERROR` (an unparseable, non-ZIP `fnlttXbrl.xml`
# response) and `LIST_JSON_ERROR` are transient in this sense: every other
# classification is either a served ZIP or a fact `list.json` itself stated
# (no matching filing, only an amendment, an ambiguous match, or DART's own
# confirmed 014 "file does not exist" envelope for the exact original receipt).
RETRYABLE_CLASSIFICATIONS = frozenset({LIST_JSON_ERROR, XO.REQUEST_ERROR})


def record_id(ticker: str, stage: str) -> str:
    return f"xbrl2015:{ticker}:{stage}"


def _needs_fetch(rid: str, state: dict) -> bool:
    """True if `rid` has never been checked, or was last checked with a retryable outcome."""
    row = state.get(rid)
    return row is None or row["classification"] in RETRYABLE_CLASSIFICATIONS


def load_state(store: Path) -> dict:
    path = store / "fetch-state.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def save_state(store: Path, state: dict) -> None:
    (store / "fetch-state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def collect(store: Path, key: str, universe: dict, budget: "C.Budget", *,
           directory_fn=C.corp_directory, dump_dir: Path | None = None) -> dict:
    store.mkdir(parents=True, exist_ok=True)
    identities = C.resolve_all(universe, directory_fn(key))
    resolved = {t: i for t, i in identities.items() if i["status"] == KCA.RESOLVED}
    state = load_state(store)
    records = HS.read_jsonl(store / "dart-xbrl-2015.jsonl.gz")
    by_id = {r["id"]: r for r in records}

    pending = [(ticker, stage) for ticker in sorted(resolved) for stage in STAGES
              if _needs_fetch(record_id(ticker, stage), state)]
    collected_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stop_reason, written = "WORK_LIST_EXHAUSTED", 0

    for ticker, stage in pending:
        rid = record_id(ticker, stage)
        identity = resolved[ticker]
        try:
            periodic, list_error = C.periodic_reports_via_list_json(key, identity["corpCode"], budget)
        except C.CallBudgetExhausted:
            stop_reason = "CALL_BUDGET_SPENT"
            break
        except TimeoutError:
            stop_reason = "TIME_BUDGET_SPENT"
            break
        if list_error:
            state[rid] = {"ticker": ticker, "stage": stage, "classification": LIST_JSON_ERROR,
                         "detail": list_error, "checkedAt": collected_at}
            continue
        row, selection = XO.select_original_filing(periodic, stage)
        if row is None:
            state[rid] = {"ticker": ticker, "stage": stage, "classification": selection,
                         "checkedAt": collected_at}
            continue
        try:
            body, error = C.fetch_original_xbrl(key, row["rceptNo"], stage, budget)
        except C.CallBudgetExhausted:
            stop_reason = "CALL_BUDGET_SPENT"
            break
        except TimeoutError:
            stop_reason = "TIME_BUDGET_SPENT"
            break
        if body is None:
            state[rid] = {"ticker": ticker, "stage": stage, "classification": XO.REQUEST_ERROR,
                         "detail": error, "originalReceiptNo": row["rceptNo"], "checkedAt": collected_at}
            continue
        classification, envelope = XO.classify_xbrl_response(body)
        base_state = {"ticker": ticker, "stage": stage, "classification": classification,
                     "originalReceiptNo": row["rceptNo"], "originalReceiptDate":
                     f"{row['rceptDt'][:4]}-{row['rceptDt'][4:6]}-{row['rceptDt'][6:8]}"
                     if row.get("rceptDt") else None, "checkedAt": collected_at}
        if classification != XO.XBRL_ZIP_SERVED:
            state[rid] = {**base_state, "errorEnvelope": envelope}
            continue
        entries, unzip_error = XS.unzip_entries(body)
        zip_sha256 = hashlib.sha256(body).hexdigest()
        if dump_dir is not None:
            dump_dir.mkdir(parents=True, exist_ok=True)
            (dump_dir / f"{ticker}-{stage}-{row['rceptNo']}.zip").write_bytes(body)
        record, provenance = XS.canonical_record_from_xbrl(
            ticker=ticker, stock_code=ticker.split(".")[0], corp_code=identity["corpCode"],
            fiscal_year=2015, report_code=stage, entries=entries,
            original_receipt_no=row["rceptNo"], original_receipt_date=base_state["originalReceiptDate"],
            zip_sha256=zip_sha256, collected_at=collected_at)
        state[rid] = {**base_state, "unzipError": unzip_error, "zipSha256": zip_sha256,
                     "entryNames": [name for name, _ in entries],
                     "accountsRecovered": sorted(k for k, v in provenance.items()
                                                 if v.get("status") == XS.RESOLVED),
                     "accountProvenance": provenance}
        if record is not None:
            by_id[record["id"]] = record
            written += 1

    for path_name, rows in (("dart-xbrl-2015.jsonl.gz", list(by_id.values())),):
        HS.write_shard(store / path_name, rows)
    save_state(store, state)

    remaining = [(t, s) for t in sorted(resolved) for s in STAGES if _needs_fetch(record_id(t, s), state)]
    classifications = {}
    for row in state.values():
        classifications[row["classification"]] = classifications.get(row["classification"], 0) + 1
    outcome = CO.run_outcome(stop_reason=stop_reason, calls=budget.calls, written=written)
    manifest = {
        "contract": CONTRACT, "updatedAt": collected_at,
        "resolvedIssuers": len(resolved), "recordsStored": len(by_id),
        "checked": len(state), "remaining": len(remaining), "datasetComplete": not remaining,
        "classifications": classifications,
        "thisRun": {"calls": budget.calls, "written": written, "stopReason": stop_reason,
                    "outcome": outcome},
    }
    (store / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir", type=Path)
    parser.add_argument("--universe-dir", type=Path, required=True)
    parser.add_argument("--max-calls", type=int, default=1500)
    parser.add_argument("--max-minutes", type=int, default=300)
    parser.add_argument("--dump-dir", type=Path,
                        help="also write raw served ZIPs here (never committed)")
    args = parser.parse_args(argv)
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        print("ERROR: DART_API_KEY not in the environment.")
        return 1
    universe = C.pit_universe(args.universe_dir)
    if not universe:
        print("ERROR: no KR universe snapshots under", args.universe_dir)
        return 1
    budget = C.Budget(args.max_calls, args.max_minutes)
    try:
        directory = C.corp_directory(key)
    except (C.Refused, ValueError) as exc:
        print(f"ERROR: corpCode.xml not served -- {exc}")
        return 2
    manifest = collect(args.store_dir, key, universe, budget, directory_fn=lambda _: directory,
                       dump_dir=args.dump_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=1))
    if CO.is_reportable_failure(manifest["thisRun"]["outcome"], written=manifest["thisRun"]["written"]):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
