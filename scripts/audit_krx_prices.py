"""What the collected KRX bars say, before a generation is spent on them.

THE FAILURE THIS LOOKS FOR, AND THE ONE IT ALREADY CAUGHT. KRX quotes the price
that printed; `price_adjustment.to_total_return` expects a split-adjusted frame
and multiplies each session by the splits that follow. `krx_prices` bridges the
two, and a missed split leaves every earlier session off by its ratio — fifty,
for Samsung Electronics in 2018. That does not raise, does not look malformed,
and reads as a spectacular decade of momentum rather than as a bug.

Run #3 is why this script exists rather than being a nicety. It collected 3,364
sessions and this audit refused them: 302 "splits" at ratios like x1.12113, and
345 leftover moves up to +3,300%. Three defects, all in the derivation and none
in the collection — suspended sessions kept as flat bars, a relative tolerance
that admitted every small share issuance, and capital reductions no share count
describes. The bars were fine; what read them was not.

WHAT IT REPORTS NOW. The same adjustment the replay would do, then the leftover
extremes SPLIT BY WHAT EXPLAINS THEM, because three of the four categories are
real returns and lumping them together is what made the first report unreadable:

    across a halt      the gap is months; a large move there is cumulative
    정리매매            the limit is lifted before a delisting, on purpose
    unexplained        a capital reduction or a re-listing — refused
    (within the limit) what the limit is for

and then the number that decides whether the path is worth finishing: of the
names that left the universe, how many come out clean.

This reads and reports. It writes nothing and decides nothing.

Usage:  python scripts/audit_krx_prices.py <store> [--universe <dir>] [--limit 20]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import historical_store as HS  # noqa: E402
from pipeline import krx_prices as KP  # noqa: E402
from pipeline import krx_universe as KU  # noqa: E402


def membership(universe: Path | None, size: int, configured: list[str]):
    """(departed, current) tickers, or (set(), set()) with no membership shards."""
    if not universe:
        return set(), set()
    rows: list[dict] = []
    for path in sorted(Path(universe).glob("krx-universe-*.jsonl.gz")):
        rows.extend(HS.read_jsonl(path))
    if not rows:
        return set(), set()
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_universe_history import memberships_from_snapshots

    memberships = memberships_from_snapshots(
        KU.snapshots_from_rows(rows, size, configured), "KR")
    return ({t for t, r in memberships.items() if r["delisted"]},
            {t for t, r in memberships.items() if not r["delisted"]})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store")
    parser.add_argument("--universe", default=None,
                        help="멤버십 샤드 — 떠난 종목의 커버리지를 재려면 필요")
    parser.add_argument("--config", default=str(ROOT / "config.json"))
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
    tickers = {str(r.get("ticker")) for r in rows if r.get("ticker")}
    halted = sum(1 for r in rows if not (r.get("volume") or 0))
    print(f"{len(rows):,}행 · {len(tickers)}종목 · {len(dates)}세션 "
          f"{dates[0]} .. {dates[-1]}")
    print(f"거래량 0 (거래정지 중 이월된 종가): {halted:,}행 "
          f"({100.0 * halted / len(rows):.1f}%) — 세션에서 제외\n")

    panel, refused = KP.panel_from_rows(rows)
    splits: list[tuple[str, str, float]] = []
    for ticker, frame in panel.items():
        from pipeline.price_adjustment import SPLIT

        ratios = frame[SPLIT]
        for date, ratio in ratios[ratios != 1.0].items():
            splits.append((ticker, str(date)[:10], float(ratio)))

    print(f"사용 가능 {len(panel)}종목 · 거부 {len(refused)}종목 "
          f"({100.0 * len(panel) / max(len(panel) + len(refused), 1):.1f}% 통과)")
    print(f"검출된 분할 {len(splits)}건")
    for ticker, date, ratio in sorted(splits, key=lambda s: s[1])[:args.limit]:
        kind = "액면분할" if ratio > 1 else "액면병합"
        print(f"  {date}  {ticker:<12} {kind} x{ratio:g}")
    if len(splits) > args.limit:
        print(f"  ... 외 {len(splits) - args.limit}건")

    # The headline: what the adjustment could not account for, by name and date.
    # Every one of these is a ticker the panel does NOT carry, so the cost of
    # each is a measured gap rather than a fabricated return.
    total = sum(len(v) for v in refused.values())
    print(f"\n설명되지 않는 변동 {total}건 · {len(refused)}종목 (패널에서 제외)")
    worst = sorted(((t, m) for t, v in refused.items() for m in v),
                   key=lambda pair: -abs(pair[1]["movePct"]))
    for ticker, move in worst[:args.limit]:
        print(f"  {move['date']}  {ticker:<12} {move['movePct']:+9.2f}% "
              f"(간격 {move['gapDays']}일)")
    if len(worst) > args.limit:
        print(f"  ... 외 {len(worst) - args.limit}건")
    if not refused:
        print("  없음 — 검출되지 않은 기업행위의 지문이 남아 있지 않습니다.")

    departed, current = membership(
        args.universe,
        _configured_size(Path(args.config)), _configured_kr(Path(args.config)))
    if departed:
        print("\n멤버십 대비 — 이 작업이 사는 것")
        for label, names in (("떠난 종목", departed), ("현재 종목", current)):
            served = names & tickers
            clean = served - set(refused)
            print(f"  {label:<10} {len(names):>4}종목 · KRX 서빙 {len(served):>4} "
                  f"({100.0 * len(served) / len(names):5.1f}%) · 깨끗 {len(clean):>4} "
                  f"({100.0 * len(clean) / len(names):5.1f}%)")
        print("  비교: FinanceDataReader 상장폐지 커버리지 34.55% (기존 측정)")
    return 0


def _configured_size(path: Path, fallback: int = 120) -> int:
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_universe_history import configured_universe_size

    return configured_universe_size(path, fallback)


def _configured_kr(path: Path) -> list[str]:
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_universe_history import configured_kr

    return configured_kr(path)


if __name__ == "__main__":
    raise SystemExit(main())
