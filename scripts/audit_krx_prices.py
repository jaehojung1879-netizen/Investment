"""What the collected KRX bars say, before a generation is spent on them.

THE FAILURE THIS LOOKS FOR. KRX quotes the price that printed;
`price_adjustment.to_total_return` expects a split-adjusted frame and
multiplies each session by the splits that follow it. `krx_prices` bridges the
two, and if it misses a split, every session before it is off by the split
ratio — fifty, for Samsung Electronics in 2018. That does not raise, does not
look malformed, and reads as a spectacular decade of momentum rather than as a
bug. Sealed into a generation it would be discovered, at best, by someone
wondering why one Korean name dominates every ranking.

An undetected split leaves a fingerprint the adjusted series cannot hide: a
single-session return near -98%, or near +4,900% for a consolidation. So this
adjusts the panel exactly as the replay would and reports the extremes that
survive. A clean run has nothing beyond what Korean equities actually do — the
daily price limit is ±30%, so anything past that is a corporate action, not a
market.

It also reports the splits that WERE detected, by name and date, because a
detection that fires on a rights issue is the opposite error and is just as
invisible in the aggregate.

This reads and reports. It writes nothing and decides nothing.

Usage:  python scripts/audit_krx_prices.py <store> [--limit 20]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import historical_store as HS  # noqa: E402
from pipeline import krx_prices as KP  # noqa: E402

# KRX's daily price limit. A single-session move beyond it is a corporate
# action the adjustment did not account for, not a market outcome.
DAILY_LIMIT_PCT = 30.0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)

    store = Path(args.store)
    rows: list[dict] = []
    for path in sorted(store.glob("krx-prices-*.jsonl.gz")):
        rows.extend(HS.read_jsonl(path))
    if not rows:
        print(f"{store}에 시세 샤드가 없습니다.")
        return 0

    dates = sorted({str(r.get("date")) for r in rows if r.get("date")})
    tickers = sorted({str(r.get("ticker")) for r in rows if r.get("ticker")})
    print(f"{len(rows):,}행 · {len(tickers)}종목 · {len(dates)}세션 "
          f"{dates[0]} .. {dates[-1]}")

    from pipeline.price_adjustment import to_total_return

    panel = KP.panel_from_rows(rows)
    splits: list[tuple[str, str, float]] = []
    extremes: list[tuple[float, str, str]] = []
    adjusted = 0
    for ticker, frame in panel.items():
        rebased, events = to_total_return(frame)
        if rebased is None or len(rebased) < 2:
            continue
        adjusted += 1
        for event in events:
            if "split" in event:
                splits.append((ticker, event["date"], event["split"]))
        returns = rebased["Close"].pct_change().dropna()
        for date, value in returns.items():
            move = float(value) * 100.0
            if abs(move) > DAILY_LIMIT_PCT:
                extremes.append((move, ticker, str(date)[:10]))

    print(f"\n조정 통과 {adjusted}종목 · 검출된 분할 {len(splits)}건")
    for ticker, date, ratio in sorted(splits, key=lambda s: s[1])[:args.limit]:
        kind = "액면분할" if ratio > 1 else "액면병합"
        print(f"  {date}  {ticker:<12} {kind} x{ratio:g}")
    if len(splits) > args.limit:
        print(f"  ... 외 {len(splits) - args.limit}건")

    # The headline. Zero is the expected answer; anything here is a corporate
    # action the share counts did not describe, and it is named so it can be
    # looked at rather than summarised away.
    print(f"\n일일 제한({DAILY_LIMIT_PCT:g}%)을 넘는 잔여 변동: {len(extremes)}건")
    for move, ticker, date in sorted(extremes, key=lambda e: -abs(e[0]))[:args.limit]:
        print(f"  {date}  {ticker:<12} {move:+.2f}%")
    if len(extremes) > args.limit:
        print(f"  ... 외 {len(extremes) - args.limit}건")
    if not extremes:
        print("  없음 — 검출되지 않은 분할의 지문이 남아 있지 않습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
