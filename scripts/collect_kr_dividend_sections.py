"""Collect DART `alotMatter.json` (배당에 관한 사항) rows for the 22 KR
terminated securities `alpha-opportunity-model-v3`'s survivorship audit
found without dividend lineage, PLUS a real, deterministically-selected
continuing-name sample for cross-validation.

WHY A SEPARATE SCRIPT FROM `collect_kr_corporate_actions.py`. That script
collects `list.json` — a different endpoint, a different shard, a different
resumable state, and (before this run) a different confidence tier
(`alotMatter.json` was CANDIDATE_UNCONFIRMED). `kr-corporate-action-
collection.yml`'s own `probe` job already exercised `alotMatter.json` live
and reported `status=000` with real rows for its continuing-name sample —
see `docs/kr-terminal-action-reconstruction-v2.md` for the run this script
promotes from that probe. This is a SEPARATE job in the SAME workflow file
(extending it, never a second parallel workflow), reusing that workflow's
own `signal-history` checkout, `corpCode.xml` directory fetch pattern and
identity resolver.

WHAT THIS COLLECTS AND WHY THE CONTINUING SAMPLE. `alotMatter.json`
(`bsns_year`, `reprt_code=11011` -- the annual/사업보고서 filing) for every
year 2013 through the current year, for:
  1. every one of the 22 terminated securities whose DART identity resolves
     (`kr_corporate_action_events.resolve_historical_dart_identity`, the
     SAME resolver `collect_kr_corporate_actions.py` uses — never a second
     path), and
  2. a deterministic, real-universe continuing-name pool
     (`kr_continuing_dividend_sample.select_continuing_sample`, drawn from
     THIS SAME `signal-history` checkout's own `ledger/universe/kr` shards,
     never a second hand-picked list) — needed because a 5-name cross-
     validation control cannot characterize a full-endpoint agreement rate.

`se` (DART's own row-category label) IS KEPT RAW. This script never decides
what a `se` value means; `kr_corporate_action_events.build_dividend_section_
row` already refuses to interpret it, for the same reason
`dart_ownership_events.py`'s `report_tp` handling does (workflow-hygiene
invariants v2.25) — a category is translated from a live-observed value, or
not at all.

KNOWN LIMITATION, PUBLISHED RATHER THAN SILENTLY MISSING. Only `reprt_code=
11011` (annual) is collected. An interim/quarterly dividend decision
(increasingly common at large KR issuers since roughly 2022) filed under a
different report code is NOT captured by this pass — a genuine scope limit,
not a claim of full dividend-decision coverage. See the accompanying doc.

RESUMABLE, HARD-CEILINGED, FAILS CLOSED — same discipline as `collect_kr_
corporate_actions.py`: the call budget is checked before every single
`alotMatter.json` call (one call = one ticker-year), a ticker's state is
never marked complete until every year in range has been attempted, and a
budget-exhausted ticker resumes from wherever it stopped rather than
re-querying years already collected.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import collector_outcomes as CO  # noqa: E402
from pipeline import dart_ownership_universe as DOU  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402
from pipeline import kr_continuing_dividend_sample as SAMPLE  # noqa: E402
from pipeline import kr_corporate_action_events as KCA  # noqa: E402

BASE = "https://opendart.fss.or.kr/api"
PACE_SECONDS = 0.3
STATE_CONTRACT = "KR_DIVIDEND_SECTION_FETCH_STATE_V1"
RAW_CONTRACT = "KR_CORPORATE_ACTION_DIVIDEND_SECTION_V1"
REPRT_CODE_ANNUAL = "11011"
FIRST_YEAR = 2013

# 47 tickers (22 terminated + 25 continuing) x up to 14 annual calls each --
# a conservative, not a guaranteed, budget, the same discipline
# `collect_kr_corporate_actions.DEFAULT_MAX_CALLS`'s own comment states.
DEFAULT_MAX_CALLS = 700
DEFAULT_MAX_MINUTES = 45


class Refused(RuntimeError):
    pass


class CallBudgetExhausted(RuntimeError):
    """Raised BEFORE the call that would exceed `--max-calls`, never after."""


def call(path: str, params: dict, timeout: int = 30) -> dict:
    url = f"{BASE}/{path}?" + "&".join(f"{k}={v}" for k, v in params.items())
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise Refused(f"HTTP {exc.code}") from exc
    except Exception as exc:  # pragma: no cover - network dependent
        raise Refused(f"{type(exc).__name__}: {exc}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise Refused(f"non-JSON response ({len(raw)} bytes)") from exc


def corp_code_directory(key: str) -> list[dict]:
    try:
        with urllib.request.urlopen(f"{BASE}/corpCode.xml?crtfc_key={key}",
                                    timeout=120) as response:
            return DOU.parse_corp_code_zip(response.read())
    except Exception as exc:  # pragma: no cover - network dependent
        raise Refused(f"corp_code.xml: {exc}") from exc


def load_state(store: Path) -> dict:
    path = store / "dividend-fetch-state.json"
    if not path.exists():
        return {"contract": STATE_CONTRACT, "rawContract": RAW_CONTRACT, "tickers": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raw = {}
    if raw.get("contract") != STATE_CONTRACT or raw.get("rawContract") != RAW_CONTRACT:
        return {"contract": STATE_CONTRACT, "rawContract": RAW_CONTRACT, "tickers": {}}
    raw.setdefault("tickers", {})
    return raw


def save_state(store: Path, state: dict) -> None:
    (store / "dividend-fetch-state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def load_universe_rows(universe_root: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(universe_root.glob("krx-universe-*.jsonl.gz")):
        rows.extend(HS.read_jsonl(path))
    return rows


def target_tickers(inventory_path: Path, universe_root: Path,
                   sample_size: int) -> list[tuple[str, str | None]]:
    """(code, krxName) pairs: the 22 terminated securities plus a real,
    deterministic continuing-name pool -- never a hardcoded list on either
    side.
    """
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    terminated = {row["code"].removesuffix(".KS"): row.get("krxName")
                 for row in inventory["securities"]}
    rows = load_universe_rows(universe_root) if universe_root.exists() else []
    pool = SAMPLE.select_continuing_sample(
        rows, terminated_codes=set(terminated), sample_size=sample_size)
    continuing = {p["code"]: p["name"] for p in pool}
    merged = {**terminated, **continuing}
    return sorted(merged.items())


def years_in_range(as_of_year: int | None = None) -> list[int]:
    end = as_of_year or time.gmtime().tm_year
    return list(range(FIRST_YEAR, end + 1))


def run(store: Path, *, key: str, inventory_path: Path, universe_root: Path,
       max_calls: int, max_minutes: int, sample_size: int = SAMPLE.DEFAULT_SAMPLE_SIZE,
       call_fn=call, directory_fn=corp_code_directory) -> dict:
    store.mkdir(parents=True, exist_ok=True)
    tickers = target_tickers(inventory_path, universe_root, sample_size)
    directory = directory_fn(key)
    if not directory:
        raise Refused("corp_code directory was empty")

    state = load_state(store)
    ticker_states = state["tickers"]
    existing_path = store / "kr-dividend-sections.jsonl.gz"
    existing = HS.read_jsonl(existing_path) if existing_path.exists() else []

    years = years_in_range()
    deadline = time.monotonic() + max_minutes * 60
    call_counter = {"n": 0}
    written = 0
    stop_reason = "WORK_LIST_EXHAUSTED"
    new_rows: list[dict] = []

    def checked_call(path: str, params: dict) -> dict:
        if call_counter["n"] >= max_calls:
            raise CallBudgetExhausted(
                f"{max_calls} call(s) already made; the next call was refused before it ran")
        call_counter["n"] += 1
        return call_fn(path, params)

    try:
        for ticker, krx_name in tickers:
            if time.monotonic() >= deadline:
                stop_reason = "TIME_BUDGET_SPENT"
                break
            entry = ticker_states.get(ticker, {})
            if entry.get("status") == "SUCCESS":
                continue
            code = ticker.removesuffix(".KS")

            identity = KCA.resolve_historical_dart_identity(code, krx_name, directory)
            if identity["status"] != KCA.RESOLVED:
                ticker_states[ticker] = {"status": "NO_DART_IDENTITY",
                                         "basis": identity["basis"],
                                         "provenance": identity["provenance"],
                                         "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
                continue
            corp_code = identity["corpCode"]

            years_done = set(entry.get("yearsCompleted", []))
            ticker_rows: list[dict] = []
            budget_ran_out = False
            for year in years:
                if year in years_done:
                    continue
                if time.monotonic() >= deadline:
                    stop_reason = "TIME_BUDGET_SPENT"
                    budget_ran_out = True
                    break
                try:
                    payload = checked_call("alotMatter.json", {
                        "crtfc_key": key, "corp_code": corp_code,
                        "bsns_year": str(year), "reprt_code": REPRT_CODE_ANNUAL})
                except CallBudgetExhausted:
                    stop_reason = "CALL_BUDGET_SPENT"
                    budget_ran_out = True
                    break
                status = str(payload.get("status") or "")
                rows = payload.get("list") or []
                if status == KCA.NO_DATA_STATUS or not isinstance(rows, list):
                    years_done.add(year)
                    continue
                for row in rows:
                    record, _reason = KCA.build_dividend_section_row(
                        row, ticker=ticker, collected_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"))
                    if record is not None:
                        record["bsnsYear"] = year
                        ticker_rows.append(record)
                years_done.add(year)
                time.sleep(PACE_SECONDS)

            new_rows.extend(ticker_rows)
            written += len(ticker_rows)
            if budget_ran_out:
                # Left in whatever partial state it reached -- never
                # SUCCESS -- so the next run resumes from the first
                # not-yet-attempted year rather than re-querying years
                # already collected.
                ticker_states[ticker] = {"status": "PARTIAL", "corpCode": corp_code,
                                         "identityBasis": identity["basis"],
                                         "yearsCompleted": sorted(years_done),
                                         "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
                break
            ticker_states[ticker] = {"status": "SUCCESS", "corpCode": corp_code,
                                     "identityBasis": identity["basis"],
                                     "yearsCompleted": sorted(years_done),
                                     "rowsCollected": len(ticker_rows),
                                     "queriedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
    except Refused as exc:
        stop_reason = f"REFUSED: {exc}"

    calls = call_counter["n"]
    merged = {row["id"]: row for row in [*existing, *new_rows]}
    changed = HS.write_shard(existing_path, list(merged.values()))
    save_state(store, state)

    tickers_requested = len(tickers)
    tickers_succeeded = sum(row.get("status") == "SUCCESS" for row in ticker_states.values())
    tickers_no_identity = sum(
        row.get("status") == "NO_DART_IDENTITY" for row in ticker_states.values())
    tickers_partial = sum(row.get("status") == "PARTIAL" for row in ticker_states.values())
    tickers_remaining = tickers_requested - tickers_succeeded - tickers_no_identity - tickers_partial
    full_work_list_exhausted = stop_reason == "WORK_LIST_EXHAUSTED"
    dataset_complete = full_work_list_exhausted and tickers_remaining == 0 and tickers_partial == 0

    outcome = CO.run_outcome(stop_reason=stop_reason, calls=calls, written=written)
    return {
        "contract": RAW_CONTRACT, "stopReason": stop_reason, "outcome": outcome,
        "calls": calls, "callBudget": max_calls, "written": written, "shardChanged": changed,
        "totalDividendRows": len(merged),
        "tickersRequested": tickers_requested,
        "tickersSucceeded": tickers_succeeded,
        "tickersWithNoDartIdentity": tickers_no_identity,
        "tickersPartial": tickers_partial,
        "tickersRemaining": tickers_remaining,
        "fullWorkListExhausted": full_work_list_exhausted,
        "datasetComplete": dataset_complete,
        "operatorMessage": (
            "All requested tickers reached a terminal state (collected, "
            "identity-unresolved, or fully year-complete)." if dataset_complete else
            f"INCOMPLETE: {tickers_remaining + tickers_partial} of {tickers_requested} "
            f"ticker(s) not fully collected this run (stopped: {stop_reason}). Resumable "
            "partial progress -- re-run this workflow with the same --inventory to "
            "continue from where it stopped."),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir")
    parser.add_argument(
        "--inventory", type=Path,
        default=ROOT / "docs/results/kr-termination-inventory.json")
    parser.add_argument(
        "--universe-root", type=Path,
        help="Directory holding krx-universe-*.jsonl.gz (the signal-history "
            "checkout's ledger/universe/kr). If absent, the continuing-name "
            "cross-validation sample is empty and only the 22 terminated "
            "securities are collected.")
    parser.add_argument("--sample-size", type=int, default=SAMPLE.DEFAULT_SAMPLE_SIZE)
    parser.add_argument(
        "--max-calls", type=int, default=DEFAULT_MAX_CALLS,
        help="Hard ceiling on alotMatter.json calls THIS RUN may make, checked before "
            "every call (one call = one ticker-year) -- a call budget, not a ticker "
            "count. If the run stops with tickers remaining, it is resumable.")
    parser.add_argument("--max-minutes", type=int, default=DEFAULT_MAX_MINUTES)
    args = parser.parse_args(argv)

    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        print("ERROR: DART_API_KEY not in the environment.")
        return 1

    universe_root = args.universe_root or (args.store_dir and Path(args.store_dir).parent / "universe/kr")
    try:
        report = run(Path(args.store_dir), key=key, inventory_path=args.inventory,
                    universe_root=Path(universe_root), max_calls=args.max_calls,
                    max_minutes=args.max_minutes, sample_size=args.sample_size)
    except Refused as exc:
        print(f"REFUSED before any progress: {exc}")
        report = {"outcome": CO.classify_refusal(str(exc)), "calls": 0, "written": 0,
                  "datasetComplete": False,
                  "operatorMessage": "No progress was made this run; re-run once the "
                                     "refusal's cause is resolved."}

    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    print(f"\n{report.get('operatorMessage', '')}")
    if CO.is_reportable_failure(report["outcome"], written=report["written"]):
        print(f"\nFAIL: {report['outcome']} with zero rows written this run.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
