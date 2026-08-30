"""Collect Korean point-in-time fundamentals from DART, one budgeted slice per run.

WHY IN SLICES. The probe measured ~9.4 seconds per DART call. The Korean
universe is 120 names over 2015-2025 at four reports a year — 5,280 calls, or
about fourteen hours. A GitHub job stops at six. So this run takes a budget,
fetches until it is spent, writes what it got, and the next run resumes. The
first backfill is a few days of unattended runs; after that a quarter's new
filings are minutes.

WHAT IT WRITES. Raw filings, under ``ledger/fundamentals/kr/dart-YYYY.jsonl.gz``
on the same ``signal-history`` branch the ledger lives on, sharded by fiscal
year and byte-deterministic so an unchanged shard is not re-committed. Deriving
factor inputs is a separate step: a derivation found wrong must be fixable
without spending fourteen hours again.

WHAT IT REFUSES. A filing with no receipt date is not stored. Point-in-time is
the whole reason this data is being collected, and a row that cannot say when it
became visible would sit in the store looking like coverage while being unusable.

FIELD INVENTORY. The first run reports which amount columns DART actually
returned, because the next step — turning accounts into ROE and per-share
numerators — hinges on the difference between the period column and the
year-to-date one, and that is a question to answer from the data rather than
from memory.

Usage:
    python scripts/collect_dart_fundamentals.py <store-dir>
        [--universe-size 120] [--from-year 2015] [--to-year 2025]
        [--max-calls 1500] [--max-minutes 240]
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
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import dart_fundamentals as DF  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402
from pipeline import universe as universe_mod  # noqa: E402
from pipeline.config import load_config  # noqa: E402

BASE = "https://opendart.fss.or.kr/api"
# Between calls. The probe measured ~9.4s of round trip, so this adds little to
# the wall clock and keeps a burst from looking like abuse.
PACE_SECONDS = 0.2


def call(path: str, params: dict, timeout: int = 40) -> tuple[dict | None, str]:
    url = f"{BASE}/{path}?" + "&".join(f"{k}={v}" for k, v in params.items())
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), ""
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except ValueError:
        return None, "non-JSON response"
    except Exception as exc:                          # pragma: no cover - network
        return None, f"{type(exc).__name__}: {exc}"


def corp_code_map(key: str) -> dict[str, str]:
    """stock code -> DART corp code. Every statement call is keyed by the latter."""
    try:
        with urllib.request.urlopen(f"{BASE}/corpCode.xml?crtfc_key={key}",
                                    timeout=120) as response:
            blob = response.read()
    except Exception as exc:                          # pragma: no cover - network
        print(f"ERROR: corp_code 목록을 받지 못했습니다 — {exc}")
        return {}
    if blob[:2] != b"PK":
        print("ERROR: corp_code 응답이 ZIP이 아닙니다 (키 또는 한도 확인 필요)")
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


def load_existing(store: Path) -> tuple[set[str], dict[int, list[dict]]]:
    """Everything already collected, by shard. Ids drive the skip."""
    ids: set[str] = set()
    shards: dict[int, list[dict]] = {}
    for path in sorted(store.glob("dart-*.jsonl.gz")):
        try:
            year = int(path.stem.split("-")[1].split(".")[0])
        except (IndexError, ValueError):
            continue
        rows = HS.read_jsonl(path)
        shards[year] = rows
        ids.update(str(row.get("id")) for row in rows if row.get("id"))
    return ids, shards


def fetch_one(key: str, corp: str, year: int, code: str) -> tuple[list[dict], str, str]:
    """Statement rows for one filing, consolidated where it exists.

    A company with no subsidiaries files no consolidated statement, and DART
    answers 013 rather than an error. Falling back to the separate statement is
    the only way to cover those names — and which one answered is returned, so
    the record can say so instead of leaving two definitions mixed in one book.
    """
    for fs_div in (DF.FS_CONSOLIDATED, DF.FS_SEPARATE):
        payload, error = call("fnlttSinglAcntAll.json", {
            "crtfc_key": key, "corp_code": corp, "bsns_year": str(year),
            "reprt_code": code, "fs_div": fs_div})
        if payload is None:
            return [], fs_div, error or "REQUEST_FAILED"
        status = str(payload.get("status"))
        if status in DF.FATAL_STATUSES or status == DF.QUOTA_STATUS:
            return [], fs_div, status
        rows = payload.get("list") or []
        if status == "000" and rows:
            return rows, fs_div, "000"
    return [], DF.FS_SEPARATE, "013"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir")
    parser.add_argument("--universe-size", type=int, default=None)
    parser.add_argument("--from-year", type=int, default=DF.FIRST_SERVED_YEAR)
    parser.add_argument("--to-year", type=int, default=time.gmtime().tm_year)
    parser.add_argument("--max-calls", type=int, default=1500)
    parser.add_argument("--max-minutes", type=int, default=240)
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
    print(f"KR 유니버스 {len(kr)}종목")

    codes = corp_code_map(key)
    if not codes:
        return 1
    print(f"corp_code 매핑 {len(codes):,}개")

    existing_ids, shards = load_existing(store)
    years = list(range(max(args.from_year, DF.FIRST_SERVED_YEAR), args.to_year + 1))
    pending = DF.work_list(kr, years, existing_ids)
    before = DF.progress(len(existing_ids), len(pending))
    print(f"진행률 {before['collected']:,}/{before['total']:,} "
          f"({before['completePct']}%) · 이번 예산 {args.max_calls}콜 / "
          f"{args.max_minutes}분\n")

    deadline = time.time() + args.max_minutes * 60
    collected_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    fresh: dict[int, list[dict]] = {}
    calls = 0
    refused: Counter = Counter()
    statuses: Counter = Counter()
    fs_used: Counter = Counter()
    fields_seen: Counter = Counter()
    stop_reason = "WORK_LIST_EXHAUSTED"

    for ticker, year, code in pending:
        if calls >= args.max_calls:
            stop_reason = "CALL_BUDGET_SPENT"
            break
        if time.time() >= deadline:
            stop_reason = "TIME_BUDGET_SPENT"
            break
        corp = codes.get(ticker.split(".")[0])
        if not corp:
            refused["NO_CORP_CODE"] += 1
            continue

        rows, fs_div, status = fetch_one(key, corp, year, code)
        calls += 1
        statuses[status] += 1
        if status in DF.FATAL_STATUSES:
            print(f"중단: {DF.describe_status(status)} — 재시도해도 같습니다.")
            stop_reason = f"FATAL_{status}"
            break
        if status == DF.QUOTA_STATUS:
            print(f"중단: {DF.describe_status(status)} — 다음 실행이 이어받습니다.")
            stop_reason = "DAILY_QUOTA"
            break

        for row in rows:
            for field in DF.AMOUNT_FIELDS:
                if row.get(field) not in (None, ""):
                    fields_seen[field] += 1

        record, reason = DF.build_record(
            ticker=ticker, stock_code=ticker.split(".")[0], corp_code=corp,
            fiscal_year=year, report_code=code, rows=rows,
            fs_div=fs_div, collected_at=collected_at)
        if record is None:
            refused[reason] += 1
            continue
        fs_used[fs_div] += 1
        fresh.setdefault(year, []).append(record)
        time.sleep(PACE_SECONDS)

        if calls % 100 == 0:
            done = sum(len(v) for v in fresh.values())
            print(f"  {calls}콜 · 수집 {done} · 거부 {sum(refused.values())}")

    # --- write ------------------------------------------------------------- #
    written = 0
    changed = 0
    for year, rows in sorted(fresh.items()):
        merged = shards.get(year, []) + rows
        path = DF.shard_path(store, year)
        if HS.write_shard(path, merged):
            changed += 1
        written += len(rows)

    total_ids = existing_ids | {r["id"] for rows in fresh.values() for r in rows}
    remaining = DF.work_list(kr, years, total_ids)
    after = DF.progress(len(total_ids), len(remaining))

    manifest = {
        "contract": "DART_RAW_FILINGS_V1",
        "updatedAt": collected_at,
        "universeSize": len(kr),
        "years": [years[0], years[-1]] if years else None,
        "firstServedYear": DF.FIRST_SERVED_YEAR,
        "progress": after,
        "thisRun": {
            "calls": calls, "recordsWritten": written, "shardsChanged": changed,
            "stopReason": stop_reason,
            "statuses": dict(statuses), "refused": dict(refused),
            "fsDiv": dict(fs_used),
            # Which amount columns DART actually returned. The next step turns
            # these into TTM figures, and the period column and the
            # year-to-date one give different answers — so this is measured
            # here rather than assumed there.
            "amountFieldsSeen": dict(fields_seen),
        },
    }
    (store / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n=== 이번 실행 ===")
    print(f"  호출        {calls}")
    print(f"  수집        {written}건 · 샤드 {changed}개 변경")
    print(f"  종료 사유    {stop_reason}")
    if refused:
        print(f"  거부        {dict(refused)}")
    if fs_used:
        print(f"  재무제표 구분 {dict(fs_used)}  (CFS=연결 · OFS=별도)")
    if fields_seen:
        print(f"  금액 컬럼    {dict(fields_seen)}")
    print(f"\n진행률 {after['collected']:,}/{after['total']:,} ({after['completePct']}%)")
    if remaining:
        rate = calls / max(1, args.max_calls)
        print(f"  남은 {len(remaining):,}건 — 이 예산으로 약 "
              f"{-(-len(remaining) // max(1, args.max_calls))}회 더 실행하면 완료")
    else:
        print("  백필 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
