"""Daily KOSPI bars from KRX, for the names FinanceDataReader cannot serve.

WHAT THIS CLOSES. `collect_krx_universe_snapshots.py` established that 139 of
the 260 names ever in the Korean top-120 universe have left it — 38 to 41% of
every cross-section from 2013 to 2017. Membership alone does not restore them:
`UniverseHistory.snapshot` keeps only what the price panel can serve, and
`unvouched` counts a described-but-unpriceable name exactly as it counts an
unknown one. FinanceDataReader was measured serving 34.55% of delisted Korean
names, so membership on its own would take KR unvouched from 100% to roughly
25% and stop there.

`sto/stk_bydd_trd` — the endpoint that answered the membership question, under
the same subscribed key — lists what TRADED on a date, so a name that delisted
in 2014 is in the 2013 responses like any other. Its rows carry
`TDD_OPNPRC/HGPRC/LWPRC/CLSPRC`, `ACC_TRDVOL` and `LIST_SHRS`.

WHAT IT COSTS. One call per weekday. 2013-01-01 to today is about 3,570
weekdays, roughly 24 minutes at the default pacing, and the days the exchange
was shut answer with no rows and are marked done — a fact about the calendar,
which will not change on a retry. Weekends are never asked at all.

WHAT IT WRITES, AND THE ONE POLICY IT APPLIES. Raw as-traded bars under
`<store>/krx-prices-YYYY.jsonl.gz`, one row per issue per session, carrying
what KRX printed. No adjustment is done here; `krx_prices.to_vendor_basis` and
the sealed `price_adjustment` path do that, so a change of method is a
re-derivation rather than 3,570 calls.

The single collector-side decision is WHICH TICKERS to keep, and it is a
storage bound rather than a judgement: the endpoint answers with the whole
exchange, about 930 issues, and a decade of that at daily grain would be
hundreds of megabytes in a branch that has to stay clonable. The membership
shards name the only tickers that can ever enter the cross-section, so those
are what is kept. `--all-issues` turns the filter off; the call count is
identical either way.

Usage:
    KRX_API_KEY=... python scripts/collect_krx_daily_prices.py <store>
        --universe <membership shard dir>
        [--start 2013-01-01] [--end today]
        [--max-calls 4000] [--max-minutes 300] [--pace 0.4] [--all-issues]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import historical_store as HS  # noqa: E402
from pipeline import krx_prices as KP  # noqa: E402
from pipeline import krx_universe as KU  # noqa: E402

from collect_krx_universe_snapshots import (AUTH_HEADER, DEFAULT_BASE,  # noqa: E402,F401
                                            ENDPOINT, Refused, call)

DONE_NAME = "krx-prices-done.json"


def universe_tickers(store: Path) -> set[str]:
    """Every ticker the membership shards ever describe.

    Read from the shards rather than from `universe-history.json`, so the price
    collection stays in step with the membership collection without depending
    on a build having run in between.
    """
    tickers: set[str] = set()
    for path in sorted(store.glob("krx-universe-*.jsonl.gz")):
        for row in HS.read_jsonl(path):
            ticker = row.get("ticker")
            if ticker:
                tickers.add(ticker)
    return tickers


def load_done(store: Path) -> set[str]:
    path = store / DONE_NAME
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return set()
    return {str(d) for d in raw} if isinstance(raw, list) else set()


def save_done(store: Path, done: set[str]) -> None:
    (store / DONE_NAME).write_text(
        json.dumps(sorted(done), indent=0) + "\n", encoding="utf-8")


def collect(store: Path, targets: list[str], *, auth_key: str, base: str,
            keep: set[str] | None, max_calls: int, max_minutes: float,
            pace: float, log=print) -> dict:
    store.mkdir(parents=True, exist_ok=True)
    done = load_done(store)
    pending = [d for d in targets if d not in done]

    shards: dict[int, list[dict]] = {}
    for path in sorted(store.glob("krx-prices-*.jsonl.gz")):
        try:
            year = int(path.stem.split("-")[-1].split(".")[0])
        except ValueError:
            continue
        shards[year] = HS.read_jsonl(path)

    log(f"수집 대상 {len(targets)}거래일(후보) · 이미 완료 "
        f"{len(targets) - len(pending)}일 · 남은 {len(pending)}일")
    log(f"이번 예산 {max_calls}콜 / {max_minutes}분 · 간격 {pace}s · "
        f"유지 종목 {'전체' if keep is None else len(keep)}\n")

    started = time.monotonic()
    calls = 0
    fresh: dict[int, list[dict]] = {}
    sessions: list[str] = []
    closed: list[str] = []
    bars_written = 0
    stopped: str | None = None

    for requested in pending:
        if calls >= max_calls:
            stopped = f"콜 예산 {max_calls} 소진"
            break
        if (time.monotonic() - started) / 60.0 >= max_minutes:
            stopped = f"시간 예산 {max_minutes}분 소진"
            break
        if pace and calls:
            time.sleep(pace)
        try:
            payload = call(base, ENDPOINT,
                           {"basDd": requested.replace("-", "")}, auth_key)
        except Refused as exc:
            # The service, not the market. Nothing is marked done, so the next
            # run asks this day again instead of recording a refusal as a
            # holiday and never returning to it.
            log(f"  {requested}: 거절됨 — {exc}")
            stopped = f"{requested}에서 거절: {exc}"
            break
        calls += 1
        bars, error = KP.parse_bars(payload)
        if error:
            log(f"  {requested}: 응답을 읽을 수 없음 — {error}")
            stopped = f"{requested}: {error}"
            break
        if not bars:
            closed.append(requested)
            done.add(requested)
            continue

        served = KU.served_date(payload, requested)
        rows = KP.bar_rows(served, bars, keep)
        fresh.setdefault(KP.shard_year(served), []).extend(rows)
        bars_written += len(rows)
        done.add(requested)
        sessions.append(served)
        if len(sessions) % 250 == 0 or len(sessions) == 1:
            log(f"  {served}: {len(rows)}종목 "
                f"(누적 {len(sessions)}세션, {calls}콜, {bars_written}행)")

    written: list[str] = []
    for year, rows in sorted(fresh.items()):
        merged = shards.get(year, []) + rows
        path = store / f"krx-prices-{year}.jsonl.gz"
        if HS.write_shard(path, merged):
            written.append(path.name)
    save_done(store, done)

    remaining = len([d for d in targets if d not in done])
    log(f"\n{len(sessions)}세션 · {bars_written}행 · {calls}콜 · 휴장 "
        f"{len(closed)}일 · 샤드 {len(written)}개 기록 · 남은 {remaining}일")
    if stopped:
        log(f"중단: {stopped}")
    return {"sessions": sessions, "bars": bars_written, "calls": calls,
            "closed": closed, "written": written, "remaining": remaining,
            "stopped": stopped}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store")
    parser.add_argument("--universe", default=None,
                        help="멤버십 샤드 디렉터리 — 어떤 티커를 남길지 여기서 읽는다")
    parser.add_argument("--all-issues", action="store_true",
                        help="필터를 끄고 거래소 전체를 기록 (용량이 크게 늘어난다)")
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--max-calls", type=int, default=4000)
    parser.add_argument("--max-minutes", type=float, default=300.0)
    parser.add_argument("--pace", type=float, default=0.4)
    parser.add_argument("--base", default=DEFAULT_BASE)
    args = parser.parse_args(argv)

    auth_key = (os.environ.get("KRX_API_KEY") or "").strip()
    if not auth_key:
        print("KRX_API_KEY가 없습니다. 키 없이 수집하면 서비스 거절을 "
              "'휴장'으로 기록하게 되므로 중단합니다.")
        return 2

    keep: set[str] | None = None
    if not args.all_issues:
        if not args.universe:
            print("--universe 또는 --all-issues 중 하나가 필요합니다. 필터 없이 "
                  "기본 실행하면 거래소 전체를 10년치 쌓게 됩니다.")
            return 2
        keep = universe_tickers(Path(args.universe))
        if not keep:
            print(f"{args.universe}에 멤버십 샤드가 없습니다. 멤버십을 먼저 "
                  f"수집하거나 --all-issues를 쓰십시오.")
            return 2

    end = args.end or dt.date.today().isoformat()
    targets = KP.calendar_days(args.start, end)
    result = collect(Path(args.store), targets, auth_key=auth_key,
                     base=args.base, keep=keep, max_calls=args.max_calls,
                     max_minutes=args.max_minutes, pace=args.pace)
    return 1 if result["stopped"] and not result["sessions"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
