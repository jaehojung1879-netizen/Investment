"""Collect Korean 5%-rule ownership events from DART, one budgeted slice per run.

WHY THIS IS CHEAPER THAN THE STATEMENT COLLECTOR. `majorstock.json` takes only
`corp_code` — no fiscal year, no report code, no `fs_div` fallback — and
answers with a company's ENTIRE disclosed ownership-event history in one call.
So the backfill's call count is the size of the universe, not the universe
times years times report codes: ~120 names against `dart_fundamentals`'s
~5,280 statement calls.

RESUMPTION IS THEREFORE PER-COMPANY, NOT PER-COMPANY-PER-PERIOD. A company
already fetched this run (or a prior one) is skipped outright; there is no
partial state to resume within one company's history, since one call returns
all of it.

Usage:
    python scripts/collect_dart_ownership_events.py <store-dir>
        [--universe-size 120] [--max-calls 200] [--max-minutes 60]
    DART_API_KEY must be in the environment.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import dart_fundamentals as DF  # noqa: E402
from pipeline import dart_ownership_events as DOE  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402
from pipeline import universe as universe_mod  # noqa: E402
from pipeline.config import load_config  # noqa: E402

BASE = "https://opendart.fss.or.kr/api"
PACE_SECONDS = 0.2


def call(path: str, params: dict, timeout: int = 30) -> tuple[dict | None, str]:
    url = f"{BASE}/{path}?" + "&".join(f"{k}={v}" for k, v in params.items())
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), ""
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except ValueError:
        return None, "non-JSON response"
    except Exception as exc:  # pragma: no cover - network dependent
        return None, f"{type(exc).__name__}: {exc}"


def corp_code_map(key: str) -> dict[str, str]:
    """Identical to `collect_dart_fundamentals.corp_code_map` — reused logic,
    kept as its own small copy here so this collector has no import-time
    dependency on that script module (scripts are not a package)."""
    try:
        with urllib.request.urlopen(f"{BASE}/corpCode.xml?crtfc_key={key}",
                                    timeout=120) as response:
            blob = response.read()
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"ERROR: corp_code 목록을 받지 못했습니다 — {exc}")
        return {}
    if blob[:2] != b"PK":
        print("ERROR: corp_code 응답이 ZIP이 아닙니다")
        return {}
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        xml = archive.read(archive.namelist()[0])
    out: dict[str, str] = {}
    for item in ET.fromstring(xml).iter("list"):
        stock = (item.findtext("stock_code") or "").strip()
        corp = (item.findtext("corp_code") or "").strip()
        if stock and corp:
            out[stock] = corp
    return out


def load_fetched(store: Path) -> set[str]:
    path = store / "fetched.json"
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return set()
    return {str(t) for t in raw} if isinstance(raw, list) else set()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir")
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
    universe, _ = universe_mod.resolve(cfg)
    kr = sorted(universe.get("KR") or [])
    if not kr:
        print("ERROR: KR 유니버스를 확보하지 못했습니다.")
        return 1

    codes = corp_code_map(key)
    if not codes:
        return 1

    fetched = load_fetched(store)
    existing: dict[int, list[dict]] = {}
    for path in sorted(store.glob("dart-ownership-*.jsonl.gz")):
        try:
            year = int(path.stem.split("-")[-1].split(".")[0])
        except ValueError:
            continue
        existing[year] = HS.read_jsonl(path)

    pending = [t for t in kr if t not in fetched]
    print(f"KR 유니버스 {len(kr)}종목 · 이미 완료 {len(fetched)} · 남은 {len(pending)}")

    deadline = time.time() + args.max_minutes * 60
    collected_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    calls, written = 0, 0
    fresh: dict[int, list[dict]] = {}
    refused = 0
    stop_reason = "WORK_LIST_EXHAUSTED"

    for ticker in pending:
        if calls >= args.max_calls:
            stop_reason = "CALL_BUDGET_SPENT"
            break
        if time.time() >= deadline:
            stop_reason = "TIME_BUDGET_SPENT"
            break
        stock_code = ticker.split(".")[0]
        corp = codes.get(stock_code)
        if not corp:
            fetched.add(ticker)
            continue
        payload, error = call("majorstock.json", {"crtfc_key": key, "corp_code": corp})
        calls += 1
        fetched.add(ticker)
        if payload is None:
            print(f"  {ticker}: 요청 실패 — {error}")
            continue
        status = str(payload.get("status"))
        if status in DF.FATAL_STATUSES:
            print(f"중단: {DF.describe_status(status)} — 재시도해도 같습니다.")
            stop_reason = f"FATAL_{status}"
            fetched.discard(ticker)
            break
        if status == DF.QUOTA_STATUS:
            print(f"중단: {DF.describe_status(status)} — 다음 실행이 이어받습니다.")
            stop_reason = "DAILY_QUOTA"
            fetched.discard(ticker)
            break
        rows = payload.get("list") or []
        for row in rows:
            event, reason = DOE.build_event(row, ticker=ticker, collected_at=collected_at)
            if event is None:
                refused += 1
                continue
            year = DOE.record_year(event)
            if year is None:
                refused += 1
                continue
            fresh.setdefault(year, []).append(event)
        time.sleep(PACE_SECONDS)
        if calls % 50 == 0:
            print(f"  {calls}콜 · 이벤트 {sum(len(v) for v in fresh.values())}")

    changed = 0
    for year, rows in sorted(fresh.items()):
        merged = existing.get(year, []) + rows
        path = DOE.shard_path(store, year)
        if HS.write_shard(path, merged):
            changed += 1
        written += len(rows)

    (store / "fetched.json").write_text(json.dumps(sorted(fetched), indent=0) + "\n",
                                        encoding="utf-8")

    manifest = {
        "contract": "DART_OWNERSHIP_EVENTS_RAW_V1",
        "updatedAt": collected_at,
        "universeSize": len(kr),
        "thisRun": {"calls": calls, "eventsWritten": written, "shardsChanged": changed,
                    "stopReason": stop_reason, "refused": refused},
        "companiesFetched": len(fetched), "companiesRemaining": len(kr) - len(fetched),
    }
    (store / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n=== 이번 실행 ===\n  호출 {calls} · 이벤트 {written}건 · 샤드 {changed}개 변경 · "
          f"종료 사유 {stop_reason}\n  남은 회사 {len(kr) - len(fetched)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
