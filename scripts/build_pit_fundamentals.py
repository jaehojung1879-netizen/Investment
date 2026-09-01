"""Raw DART filings into the PIT fundamentals file the replay reads.

This is the step that makes the collection usable. `dart_fundamentals` stores
what DART said; `pipeline.dart_derive` turns it into what
`longterm.score_cross_section` reads; this walks the store and writes the
`PIT_FUNDAMENTALS_V1` JSONL that `FundamentalStore.from_jsonl` loads.

No network. It reads the store and writes a file, so a derivation found wrong is
re-run in seconds rather than re-fetched over fourteen hours.

WHAT IT WILL AND WILL NOT PRODUCE. Quality — ROE, margins, leverage, growth —
comes out of the statements alone. Value needs a share count, which the
statement endpoint does not carry, so `epsTtm`, `bookValuePerShare` and
`fcfPerShare` appear only where the share pass has run. The coverage report says
which, because "we collected fundamentals" must not be read as "the value sleeve
works".

Usage:
    python scripts/build_pit_fundamentals.py <store-dir> --output pit-kr.jsonl
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
from pipeline import historical_store as HS  # noqa: E402


def load_filings(store: Path) -> dict[str, list[dict]]:
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(store.glob("dart-*.jsonl.gz")):
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
    parser.add_argument("--output", default="pit-fundamentals-kr.jsonl")
    args = parser.parse_args(argv)

    store = Path(args.store_dir)
    filings = load_filings(store)
    shares = load_shares(store)
    if not filings:
        # Not an error. The collection runs on its own schedule, and a replay
        # that fails because the fundamentals have not arrived yet would be a
        # daily red build over a file nobody promised for today.
        print(f"{store} 에 수집된 공시가 없습니다 — PIT 파일 없이 진행합니다.")
        return 0
    print(f"공시 {sum(len(v) for v in filings.values()):,}건 · {len(filings)}종목")
    print(f"주식수 {sum(len(v) for v in shares.values()):,}건 · {len(shares)}종목")

    rows: list[dict] = []
    for ticker, records in sorted(filings.items()):
        rows.extend(DD.build_for_ticker(records, shares.get(ticker)))

    Path(args.output).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8")

    report = DD.coverage(rows)
    print(f"\n=== PIT 레코드 {report['rows']:,}건 ===")
    print("  팩터 입력 커버리지")
    for key, pct in report["fieldCoveragePct"].items():
        print(f"    {key:<20} {pct:>6.1f}%")
    print(f"\n  TTM 산출 방식 {report['netIncomeBasis']}")
    print(f"  퀄리티 슬리브  {'가능' if report['qualityComplete'] else '불가'}")
    print(f"  밸류 슬리브    {'가능' if report['valueComplete'] else '불가 — 주식수 필요'}")
    print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
