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


def load_absent(store: Path) -> dict[str, dict]:
    """Filings DART has said do not exist, by id.

    Kept beside the shards rather than inside them: an absence is not a filing
    and must never reach `FundamentalStore`, which would read it as a record
    with no accounts.
    """
    path = store / "absent.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return raw if isinstance(raw, dict) else {}


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


def fetch_shares(key: str, corp: str, year: int, code: str) -> tuple[float | None, str]:
    """Shares outstanding as stated in one filing's 주식총수 현황.

    A second endpoint, because the statement endpoint does not carry it — and
    without it every per-share numerator, and so the entire value sleeve, stays
    dark. Collected per filing rather than once a year: buybacks and issuance
    move the count, and a per-share figure standing on last January's count is
    wrong by however much the company did in between.
    """
    payload, error = call(DF.SHARE_ENDPOINT + ".json", {
        "crtfc_key": key, "corp_code": corp,
        "bsns_year": str(year), "reprt_code": code})
    if payload is None:
        return None, error or "REQUEST_FAILED"
    status = str(payload.get("status"))
    if status != "000":
        return None, status
    # A company can file several classes of stock. Ordinary shares are what a
    # price quotes, so the largest ordinary line is taken and preferred shares
    # are left out rather than summed into a denominator the price never had.
    best = None
    for row in payload.get("list") or []:
        kind = str(row.get("se") or "")
        if "우선주" in kind:
            continue
        count = DF.share_count(row)
        if count and (best is None or count > best):
            best = count
    return best, ("000" if best else "013")


def collect_shares(key: str, codes: dict, store: Path,
                   max_calls: int, deadline: float) -> int:
    """The share pass. Same budget discipline, its own work list and file.

    Takes what is left of the run's budget rather than a fresh one, so a run
    that finishes the statements early spends the remainder here instead of
    stopping with hours unused.
    """
    path = store / "shares.jsonl.gz"
    held = HS.read_jsonl(path)
    have = {(str(r["ticker"]), int(r["fiscalYear"]), str(r["reportCode"])) for r in held}
    # Only filings we actually hold need a share count; asking for one against
    # a filing that does not exist spends the budget on the answer we already
    # recorded as an absence.
    filings = []
    for shard in sorted(store.glob("dart-*.jsonl.gz")):
        for row in HS.read_jsonl(shard):
            keyed = (str(row["ticker"]), int(row["fiscalYear"]), str(row["reportCode"]))
            if keyed not in have:
                filings.append(keyed)
    filings.sort()
    print(f"주식수 대상 {len(filings):,}건 (보유 공시 기준) · "
          f"이미 확보 {len(have):,}건\n")

    collected_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    fresh, calls = [], 0
    statuses: Counter = Counter()
    for ticker, year, code in filings:
        if calls >= max_calls or time.time() >= deadline:
            break
        corp = codes.get(ticker.split(".")[0])
        if not corp:
            continue
        shares, status = fetch_shares(key, corp, year, code)
        calls += 1
        statuses[status] += 1
        if status in DF.FATAL_STATUSES:
            print(f"중단: {DF.describe_status(status)}")
            break
        if status == DF.QUOTA_STATUS:
            print(f"중단: {DF.describe_status(status)} — 다음 실행이 이어받습니다.")
            break
        if shares:
            fresh.append({"id": DF.share_record_id(ticker, year, code),
                          "ticker": ticker, "fiscalYear": year, "reportCode": code,
                          "sharesOutstanding": shares, "collectedAt": collected_at,
                          "source": f"DART:{DF.SHARE_ENDPOINT}"})
        time.sleep(PACE_SECONDS)
        if calls % 100 == 0:
            print(f"  {calls}콜 · 확보 {len(fresh)}")

    if fresh:
        HS.write_shard(path, held + fresh)
    print(f"\n=== 주식수 ===\n  호출 {calls} · 확보 {len(fresh)}건 · "
          f"누적 {len(have) + len(fresh):,}건")
    print(f"  상태 {dict(statuses)}")
    print(f"  남음 {len(filings) - len(fresh):,}건")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir")
    parser.add_argument("--target", choices=("auto", "statements", "shares"),
                        default="auto",
                        help="auto=재무제표를 끝내고 남은 예산으로 주식수까지, "
                             "statements=재무제표만, shares=주식수만")
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

    years = list(range(max(args.from_year, DF.FIRST_SERVED_YEAR), args.to_year + 1))
    run_deadline = time.time() + args.max_minutes * 60
    if args.target == "shares":
        return collect_shares(key, codes, store, args.max_calls, run_deadline)

    existing_ids, shards = load_existing(store)
    absent = load_absent(store)
    today = time.strftime("%Y-%m-%d", time.gmtime())
    settled = DF.settled_absences(absent, today)
    pending = DF.work_list(kr, years, existing_ids, absent_ids=settled)
    before = DF.progress(len(existing_ids), len(pending), len(settled))
    print(f"진행률 {before['collected']:,} 수집 + {before['absent']:,} 부재확정 "
          f"/ {before['total']:,} ({before['completePct']}%) · 남음 {before['pending']:,}")
    if len(absent) > len(settled):
        print(f"  부재 {len(absent) - len(settled):,}건은 마감 전이라 다시 확인합니다")
    print(f"  이번 예산 {args.max_calls}콜 / {args.max_minutes}분\n")

    deadline = run_deadline
    collected_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    fresh: dict[int, list[dict]] = {}
    calls = 0
    refused: Counter = Counter()
    statuses: Counter = Counter()
    fs_used: Counter = Counter()
    fields_seen: Counter = Counter()
    stop_reason = "WORK_LIST_EXHAUSTED"
    # `refused["NO_CORP_CODE"]` alone is a call count across years and report
    # codes, not a ticker list — 144 refusals could be one stuck name or forty.
    # Without the identity there is nothing to look up on DART's own site, so
    # every run just repeats the same unreadable number.
    no_corp_code_tickers: set[str] = set()

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
            no_corp_code_tickers.add(ticker)
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

        # Split by report code and statement, because the pooled count cannot
        # answer the question the next step turns on. The first run reported
        # `thstrm_add_amount` on 12% of rows, which tells you nothing about
        # WHICH rows — and whether a Q3 revenue figure is three months or nine
        # is exactly what a TTM is built from.
        for row in rows:
            statement = str(row.get("sj_div") or "?")
            for field in DF.AMOUNT_FIELDS:
                if row.get(field) not in (None, ""):
                    fields_seen[f"{DF.REPORT_CODES.get(code, code)}|{statement}|{field}"] += 1

        record, reason = DF.build_record(
            ticker=ticker, stock_code=ticker.split(".")[0], corp_code=corp,
            fiscal_year=year, report_code=code, rows=rows,
            fs_div=fs_div, collected_at=collected_at)
        if record is None:
            refused[reason] += 1
            # Remember that DART answered "no such filing". Without this the
            # work list never shrinks by an absence and every future run
            # re-asks the same thousand filings that do not exist — which is
            # what the first two runs did, 950 calls of 1,500 apiece.
            if reason == "EMPTY_RESPONSE":
                absent[DF.record_id(ticker, year, code)] = {
                    "fiscalYear": year, "reportCode": code, "ticker": ticker,
                    "status": status, "checkedAt": collected_at,
                    "dueBy": DF.filing_deadline(year, code),
                }
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

    (store / "absent.json").write_text(
        json.dumps(absent, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8")

    total_ids = existing_ids | {r["id"] for rows in fresh.values() for r in rows}
    settled_after = DF.settled_absences(absent, today)
    remaining = DF.work_list(kr, years, total_ids, absent_ids=settled_after)
    after = DF.progress(len(total_ids), len(remaining), len(settled_after))

    manifest = {
        "contract": "DART_RAW_FILINGS_V1",
        "updatedAt": collected_at,
        "universeSize": len(kr),
        "years": [years[0], years[-1]] if years else None,
        "firstServedYear": DF.FIRST_SERVED_YEAR,
        "progress": after,
        "absences": {
            "recorded": len(absent),
            "settled": len(settled_after),
            "awaitingDeadline": len(absent) - len(settled_after),
        },
        "thisRun": {
            "calls": calls, "recordsWritten": written, "shardsChanged": changed,
            "stopReason": stop_reason,
            "statuses": dict(statuses), "refused": dict(refused),
            # The tickers behind `refused["NO_CORP_CODE"]`, so the number is
            # something a person can act on rather than only watch.
            "noCorpCodeTickers": sorted(no_corp_code_tickers),
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
    if no_corp_code_tickers:
        print(f"  corp_code 없음 ({len(no_corp_code_tickers)}종목): "
              f"{', '.join(sorted(no_corp_code_tickers))}")
    if fs_used:
        print(f"  재무제표 구분 {dict(fs_used)}  (CFS=연결 · OFS=별도)")
    if fields_seen:
        print(f"  금액 컬럼    {dict(fields_seen)}")
    print(f"\n진행률 {after['collected']:,} 수집 + {after['absent']:,} 부재확정 "
          f"/ {after['total']:,} ({after['completePct']}%)")
    if remaining:
        print(f"  남은 {len(remaining):,}건 — 이 예산으로 약 "
              f"{-(-len(remaining) // max(1, args.max_calls))}회 더 실행하면 완료")
    else:
        print("  재무제표 백필 완료")

    # The share pass is not a second thing to remember to run. Once the
    # statements are in hand a scheduled run would otherwise spend its budget
    # discovering there is nothing to fetch, while the value sleeve stays dark
    # for want of a share count — so the remainder of this run goes there.
    if args.target == "auto":
        left = args.max_calls - calls
        if left > 0 and time.time() < run_deadline:
            print(f"\n남은 예산 {left}콜을 주식수 수집에 씁니다.\n")
            return collect_shares(key, codes, store, left, run_deadline)
        print("\n예산을 다 썼습니다. 다음 실행이 주식수를 이어받습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
