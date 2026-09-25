"""Collect DART corporate-action disclosure-index rows for the 22 KR
terminated securities `alpha-opportunity-model-v3`'s survivorship audit
found without dividend or terminal-value lineage.

WHAT THIS COLLECTS. Only the CONFIRMED half of `kr_corporate_action_events
.py`: `list.json` (DS001) disclosure-index rows matching a known
corporate-action family keyword, for each of the 22 tickers named in
`docs/results/kr-termination-inventory.json` — never a hardcoded list, the
same discipline the inventory itself follows. This is a READING LIST, not a
resolved terminal-action book: nothing this script writes assigns a
`terminationType` to any security. A human reviews the matched disclosures
and, only from their actual content, produces entries for
`data/kr-terminal-corporate-actions.json` (see `pipeline
.kr_terminal_corporate_actions.py`).

WHY NOT `alotMatter.json` TOO. It is still CANDIDATE, PENDING A LIVE PROBE
(`scripts/probe_kr_corporate_actions.py`) — see that module's docstring.
Collecting from an unconfirmed endpoint into the permanent ledger is exactly
the risk the probe/collect split exists to avoid everywhere else in this
repository.

STATE AND SHARDING mirror `collect_dart_ownership_events.py`: resumable via
a per-ticker fetch-state file keyed by this script's own raw contract, and
shards are written with `historical_store.write_shard` (sorted,
deduplicated, byte-deterministic).

FAILS CLOSED. `pipeline.collector_outcomes.run_outcome` classifies this
run; a refusal that produced zero rows exits non-zero, so a source refusal
can never look like a completed collection — the exact defect the
workflow-hygiene invariants (v2.25) record and fix for the KR investor-flow
and short-selling collectors.
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
from pipeline import kr_corporate_action_events as KCA  # noqa: E402

BASE = "https://opendart.fss.or.kr/api"
PACE_SECONDS = 0.3
STATE_CONTRACT = "KR_CORPORATE_ACTION_DISCLOSURE_FETCH_STATE_V1"
RAW_CONTRACT = "KR_CORPORATE_ACTION_DISCLOSURE_INDEX_V1"


class Refused(RuntimeError):
    pass


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
    path = store / "fetch-state.json"
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
    (store / "fetch-state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def load_terminated_codes(inventory_path: Path) -> list[str]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    return sorted({row["code"] for row in inventory["securities"]})


def run(store: Path, *, key: str, inventory_path: Path, max_calls: int,
       max_minutes: int, call_fn=call, directory_fn=corp_code_directory) -> dict:
    store.mkdir(parents=True, exist_ok=True)
    tickers = load_terminated_codes(inventory_path)
    directory = directory_fn(key)
    if not directory:
        raise Refused("corp_code directory was empty")
    by_stock: dict[str, str] = {}
    for row in directory:
        by_stock.setdefault(row["stockCode"], row["corpCode"])

    state = load_state(store)
    ticker_states = state["tickers"]
    shard: dict[str, list[dict]] = {}
    for path in sorted(store.glob("kr-corporate-actions-disclosures.jsonl.gz")):
        shard["all"] = HS.read_jsonl(path)
    existing = shard.get("all", [])

    deadline = time.monotonic() + max_minutes * 60
    calls = 0
    written = 0
    stop_reason = "WORK_LIST_EXHAUSTED"
    new_rows: list[dict] = []
    try:
        for ticker in tickers:
            if calls >= max_calls:
                stop_reason = "CALL_BUDGET_SPENT"
                break
            if time.monotonic() >= deadline:
                stop_reason = "TIME_BUDGET_SPENT"
                break
            code = ticker.removesuffix(".KS")
            if ticker_states.get(ticker, {}).get("status") == "SUCCESS":
                continue
            corp_code = by_stock.get(code)
            if not corp_code:
                ticker_states[ticker] = {"status": "NO_DART_IDENTITY",
                                         "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
                continue
            payload = call_fn("list.json", {
                "crtfc_key": key, "corp_code": corp_code, "bgn_de": "20130101",
                "end_de": time.strftime("%Y%m%d", time.gmtime()),
                "page_count": "100", "sort": "date", "sort_mth": "asc"})
            calls += 1
            rows, error = KCA.filing_index_rows(payload)
            if error:
                raise Refused(error)
            candidates = KCA.candidate_disclosures(rows, ticker=ticker)
            new_rows.extend(candidates)
            written += len(candidates)
            ticker_states[ticker] = {"status": "SUCCESS", "corpCode": corp_code,
                                     "matchedDisclosures": len(candidates),
                                     "queriedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
            time.sleep(PACE_SECONDS)
    except Refused as exc:
        stop_reason = f"REFUSED: {exc}"

    merged = {row["receiptNo"]: row for row in [*existing, *new_rows]}
    changed = HS.write_shard(store / "kr-corporate-actions-disclosures.jsonl.gz",
                             list(merged.values()))
    save_state(store, state)

    outcome = CO.run_outcome(stop_reason=stop_reason, calls=calls, written=written)
    return {
        "contract": RAW_CONTRACT, "stopReason": stop_reason, "outcome": outcome,
        "calls": calls, "written": written, "shardChanged": changed,
        "totalDisclosures": len(merged),
        "tickersRequested": len(tickers),
        "tickersSucceeded": sum(row.get("status") == "SUCCESS" for row in ticker_states.values()),
        "tickersWithNoDartIdentity": sum(
            row.get("status") == "NO_DART_IDENTITY" for row in ticker_states.values()),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir")
    parser.add_argument(
        "--inventory", type=Path,
        default=ROOT / "docs/results/kr-termination-inventory.json")
    parser.add_argument("--max-calls", type=int, default=30)
    parser.add_argument("--max-minutes", type=int, default=30)
    args = parser.parse_args(argv)

    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        print("ERROR: DART_API_KEY not in the environment.")
        return 1

    try:
        report = run(Path(args.store_dir), key=key, inventory_path=args.inventory,
                    max_calls=args.max_calls, max_minutes=args.max_minutes)
    except Refused as exc:
        print(f"REFUSED before any progress: {exc}")
        report = {"outcome": CO.classify_refusal(str(exc)), "calls": 0, "written": 0}

    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    if CO.is_reportable_failure(report["outcome"], written=report["written"]):
        print(f"\nFAIL: {report['outcome']} with zero rows written this run.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
