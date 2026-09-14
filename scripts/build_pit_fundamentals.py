"""Raw filings into the PIT fundamentals file the replay reads.

This is the step that makes a collection usable. The collectors store what the
vendor said; `dart_derive` and `finnhub_derive` turn it into what
`longterm.score_cross_section` reads; this walks a store and writes the
`PIT_FUNDAMENTALS_V1` JSONL that `FundamentalStore.from_jsonl` loads.

ONE SCRIPT, TWO REGIONS. The Korean and US stores hold different vendors under
different account names, but the file they produce is the same contract and the
consumer cannot tell them apart. `--region` picks which store is being read;
everything after the derivation is shared, including the coverage report that
keeps "we collected fundamentals" from being read as "the value sleeve works".

No network. It reads the store and writes a file, so a derivation found wrong is
re-run in seconds rather than re-fetched over fourteen hours.

WHAT IT WILL AND WILL NOT PRODUCE. Quality — ROE, margins, leverage, growth —
comes out of the statements alone. Value needs a share count. In Korea the
statement endpoint does not carry one at all, so `epsTtm`, `bookValuePerShare`
and `fcfPerShare` appear only where the separate share pass has run; in the US
the filings state it themselves 74.7% of the time and the rest is carried
forward from the nearest earlier filing.

Usage:
    python scripts/build_pit_fundamentals.py <store-dir> [--region kr|us]
        [--output pit-fundamentals-<region>.jsonl]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import dart_derive as DD  # noqa: E402
from pipeline import finnhub_derive as FD  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402

# Which shards a region's store holds, and which derivation reads them. The
# pairing is here rather than at the call site so a region cannot be given one
# vendor's shards and the other vendor's account names.
REGIONS = {"kr": "dart-*.jsonl.gz", "us": "finnhub-*.jsonl.gz"}


def load_filings(store: Path, pattern: str = REGIONS["kr"]) -> dict[str, list[dict]]:
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(store.glob(pattern)):
        for row in HS.read_jsonl(path):
            if row.get("ticker"):
                by_ticker[row["ticker"]].append(row)
    return by_ticker


def load_shares(store: Path) -> dict[str, dict[tuple[int, str], float]]:
    """Share counts by ticker and filing, where the share pass has run."""
    path = store / "shares.jsonl.gz"
    out: dict[str, dict[tuple[int, str], float]] = defaultdict(dict)
    for row in HS.read_jsonl(path):
        shares = row.get("sharesOutstanding")
        if row.get("ticker") and shares:
            out[row["ticker"]][(int(row["fiscalYear"]), str(row["reportCode"]))] = float(shares)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir")
    parser.add_argument("--region", choices=sorted(REGIONS), default="kr")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    output = args.output or f"pit-fundamentals-{args.region}.jsonl"
    store = Path(args.store_dir)
    filings = load_filings(store, REGIONS[args.region])
    # The US filings state their own share count; Korea needs the separate pass.
    shares = load_shares(store) if args.region == "kr" else {}
    if not filings:
        # Not an error. The collection runs on its own schedule, and a replay
        # that fails because the fundamentals have not arrived yet would be a
        # daily red build over a file nobody promised for today.
        print(f"{store} 에 수집된 공시가 없습니다 — PIT 파일 없이 진행합니다.")
        return 0
    print(f"[{args.region}] 공시 {sum(len(v) for v in filings.values()):,}건 "
          f"· {len(filings)}종목")
    if args.region == "kr":
        print(f"주식수 {sum(len(v) for v in shares.values()):,}건 · {len(shares)}종목")

    derive = DD if args.region == "kr" else FD
    rows: list[dict] = []
    for ticker, records in sorted(filings.items()):
        rows.extend(DD.build_for_ticker(records, shares.get(ticker))
                    if args.region == "kr" else FD.build_for_ticker(records))

    Path(output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8")

    report = derive.coverage(rows)
    print(f"\n=== PIT 레코드 {report['rows']:,}건 ===")
    print("  팩터 입력 커버리지")
    for key, pct in report["fieldCoveragePct"].items():
        print(f"    {key:<20} {pct:>6.1f}%")
    print(f"\n  TTM 산출 방식 {report['netIncomeBasis']}")
    print(f"  주식수 산출 방식 {report['sharesBasis']}")
    print(f"  퀄리티 슬리브  {'가능' if report['qualityComplete'] else '불가'}")
    print(f"  밸류 슬리브    {'가능' if report['valueComplete'] else '불가 — 주식수 필요'}")
    print(f"\nwrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
