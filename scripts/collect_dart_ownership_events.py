"""Incrementally collect DART ownership events for the historical KR universe.

The work list is the union of point-in-time KR memberships, resolved to DART
issuer identity. State is per issuer and raw-data contract, so ticker changes
cannot cause duplicate calls and a completed issuer is not called again until
an explicit contract refresh. ``majorstock.json`` has no date parameter; a
successful bounded response is not proof that an issuer had no older filings.
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

from pipeline import dart_fundamentals as DF  # noqa: E402
from pipeline import dart_ownership_events as DOE  # noqa: E402
from pipeline import dart_ownership_universe as DOU  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402
from pipeline import universe as universe_mod  # noqa: E402
from pipeline.config import load_config  # noqa: E402

BASE = "https://opendart.fss.or.kr/api"
PACE_SECONDS = 0.2
STATE_CONTRACT = "DART_OWNERSHIP_FETCH_STATE_V2"
COMPLETE_STATUSES = {"SUCCESS", "NO_ROWS_RETURNED_BY_MAJORSTOCK"}


def call(path: str, params: dict, timeout: int = 30) -> tuple[dict | None, str]:
    url = f"{BASE}/{path}?" + "&".join(f"{key}={value}" for key, value in params.items())
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), ""
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except ValueError:
        return None, "non-JSON response"
    except Exception as exc:  # pragma: no cover - network dependent
        return None, f"{type(exc).__name__}: {exc}"


def corp_code_directory(key: str) -> list[dict]:
    try:
        with urllib.request.urlopen(f"{BASE}/corpCode.xml?crtfc_key={key}",
                                    timeout=120) as response:
            return DOU.parse_corp_code_zip(response.read())
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"ERROR: corp_code 목록을 받지 못했습니다 — {exc}")
        return []


def load_state(store: Path) -> dict:
    path = store / "fetch-state.json"
    if not path.exists():
        return {"contract": STATE_CONTRACT, "rawContract": DOE.RAW_CONTRACT, "issuers": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raw = {}
    if raw.get("contract") != STATE_CONTRACT or raw.get("rawContract") != DOE.RAW_CONTRACT:
        # A contract change is the defined refresh rule. Old observations stay
        # in shards and may be enriched, never replaced.
        return {"contract": STATE_CONTRACT, "rawContract": DOE.RAW_CONTRACT,
                "issuers": {}, "previousContract": raw.get("rawContract")}
    raw.setdefault("issuers", {})
    return raw


def load_shards(store: Path) -> dict[int, list[dict]]:
    out = {}
    for path in sorted(store.glob("dart-ownership-*.jsonl.gz")):
        try:
            year = int(path.name.removeprefix("dart-ownership-").split(".")[0])
        except ValueError:
            continue
        out[year] = HS.read_jsonl(path)
    return out


def build_manifest(*, universe: dict, state: dict, shards: dict[int, list[dict]],
                   updated_at: str, this_run: dict) -> dict:
    events = [row for year in sorted(shards) for row in shards[year]]
    dates = sorted(str(row.get("availableFrom")) for row in events if row.get("availableFrom"))
    issuer_states = state.get("issuers") or {}
    complete = {corp for corp, row in issuer_states.items()
                if row.get("status") in COMPLETE_STATUSES}
    return {
        "contract": DOE.RAW_CONTRACT,
        "schemaVersion": DOE.SCHEMA_VERSION,
        "updatedAt": updated_at,
        "historicalUniverseSecurityCount": universe["securityCount"],
        "historicalUniverseIssuerCount": universe["issuerCount"],
        "currentUniverseSecurityCount": universe["currentUniverseSecurityCount"],
        "currentUniverseIssuerCount": universe["currentUniverseIssuerCount"],
        "historicalOnlySecurityCount": universe["historicalOnlySecurityCount"],
        "historicalOnlyIssuerCount": universe["historicalOnlyIssuerCount"],
        "successfullyMappedDartCorpCodes": universe["successfullyMappedDartCorpCodes"],
        "unresolvedIdentityCount": universe["unresolvedIdentityCount"],
        "companiesQueried": sum(bool(row.get("queriedAt") or row.get("lastAttemptAt"))
                                for row in issuer_states.values()),
        "successfullyQueriedCompanies": len(complete),
        "companiesRemaining": max(0, universe["issuerCount"] - len(complete)),
        "apiErrors": sum(row.get("status") == "ERROR" for row in issuer_states.values()),
        "apiRefusals": sum(row.get("dartStatus") in DF.FATAL_STATUSES
                           for row in issuer_states.values()),
        "dartUnavailableOrNoRecords": sum(
            row.get("status") == "NO_ROWS_RETURNED_BY_MAJORSTOCK"
            for row in issuer_states.values()),
        "eventCount": len(events),
        "earliestObservedEventDate": dates[0] if dates else None,
        "latestObservedEventDate": dates[-1] if dates else None,
        "shardCoverage": [str(year) for year in sorted(shards)],
        "endpointSemantics": {
            "endpoint": "majorstock.json",
            "requestDateBoundsSupported": False,
            "noRowsMeaning": "NO_ROWS_RETURNED_BY_BOUNDED_ENDPOINT_NOT_PROOF_OF_NO_HISTORICAL_FILINGS",
            "pitAvailabilityField": "availableFrom",
            "pitAvailabilityRule": "DART_RECEIPT_DATE_NOT_TRANSACTION_OR_REFERENCE_DATE",
        },
        "thisRun": this_run,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir")
    parser.add_argument("--membership-history", required=True)
    parser.add_argument("--krx-universe-dir", required=True)
    parser.add_argument("--universe-size", type=int, default=None)
    parser.add_argument("--max-calls", type=int, default=200)
    parser.add_argument("--max-minutes", type=int, default=60)
    args = parser.parse_args(argv)
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        print("ERROR: DART_API_KEY not in the environment.")
        return 1

    store = Path(args.store_dir)
    store.mkdir(parents=True, exist_ok=True)
    cfg, _ = load_config()
    if args.universe_size:
        cfg.longterm["universeSize"] = args.universe_size
    current, _ = universe_mod.resolve(cfg)
    current_kr = sorted(current.get("KR") or [])
    memberships = DOU.load_memberships(args.membership_history)
    directory = corp_code_directory(key)
    if not directory:
        return 1
    collection_universe = DOU.build_collection_universe(
        memberships=memberships, krx_rows=DOU.load_krx_rows(args.krx_universe_dir),
        current_tickers=current_kr, dart_directory=directory)
    state = load_state(store)
    issuer_states = state["issuers"]
    pending = [issuer for issuer in collection_universe["issuers"]
               if issuer_states.get(issuer["corpCode"], {}).get("status") not in COMPLETE_STATUSES]
    print(f"KR 역사 유니버스 {collection_universe['securityCount']}증권 / "
          f"{collection_universe['issuerCount']}발행사 · 미해결 "
          f"{collection_universe['unresolvedIdentityCount']} · 남은 {len(pending)}")

    existing = load_shards(store)
    fresh: dict[int, list[dict]] = {}
    deadline = time.time() + args.max_minutes * 60
    collected_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    calls = refused = errors = api_refusals = 0
    stop_reason = "WORK_LIST_EXHAUSTED"
    for issuer in pending:
        if calls >= args.max_calls:
            stop_reason = "CALL_BUDGET_SPENT"
            break
        if time.time() >= deadline:
            stop_reason = "TIME_BUDGET_SPENT"
            break
        corp = issuer["corpCode"]
        payload, error = call("majorstock.json", {"crtfc_key": key, "corp_code": corp})
        calls += 1
        if payload is None:
            issuer_states[corp] = {"status": "ERROR", "error": error,
                                   "lastAttemptAt": collected_at}
            errors += 1
            continue
        status = str(payload.get("status"))
        if status in DF.FATAL_STATUSES or status == DF.QUOTA_STATUS:
            stop_reason = "DAILY_QUOTA" if status == DF.QUOTA_STATUS else f"FATAL_{status}"
            if status in DF.FATAL_STATUSES:
                issuer_states[corp] = {"status": "ERROR", "dartStatus": status,
                                       "lastAttemptAt": collected_at}
                api_refusals += 1
            break
        if status not in {"000", "013"}:
            issuer_states[corp] = {"status": "ERROR", "dartStatus": status,
                                   "lastAttemptAt": collected_at}
            errors += 1
            continue
        rows = payload.get("list") or []
        accepted = 0
        for row in rows:
            available = DF.receipt_date(row.get("rcept_no"))
            ticker = DOU.ticker_at(issuer["securities"], available or "")
            event, _ = DOE.build_event(row, ticker=ticker, issuer_id=issuer["issuerId"],
                                       collected_at=collected_at)
            if event is None or DOE.record_year(event) is None:
                refused += 1
                continue
            fresh.setdefault(DOE.record_year(event), []).append(event)
            accepted += 1
        issuer_states[corp] = {
            "status": "SUCCESS" if status == "000" else "NO_ROWS_RETURNED_BY_MAJORSTOCK",
            "queriedAt": collected_at, "dartStatus": status,
            "rowsReturned": len(rows), "eventsAccepted": accepted,
            "rawContract": DOE.RAW_CONTRACT,
        }
        time.sleep(PACE_SECONDS)

    changed = written = 0
    final_shards = {}
    for year in sorted(set(existing) | set(fresh)):
        rows = DOE.merge_events(existing.get(year, []), fresh.get(year, []))
        final_shards[year] = rows
        if HS.write_shard(DOE.shard_path(store, year), rows):
            changed += 1
        written += len(fresh.get(year, []))
    state["updatedAt"] = collected_at
    (store / "fetch-state.json").write_text(
        json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (store / "collection-universe.json").write_text(
        json.dumps(collection_universe, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    this_run = {"calls": calls, "eventsObserved": written, "shardsChanged": changed,
                "stopReason": stop_reason, "refused": refused, "apiErrors": errors,
                "apiRefusals": api_refusals}
    manifest = build_manifest(universe=collection_universe, state=state, shards=final_shards,
                              updated_at=collected_at, this_run=this_run)
    (store / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(f"호출 {calls} · 관측 이벤트 {written} · 샤드 {changed}개 변경 · "
          f"종료 {stop_reason} · 남은 회사 {manifest['companiesRemaining']}")
    return 0 if not stop_reason.startswith("FATAL_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
