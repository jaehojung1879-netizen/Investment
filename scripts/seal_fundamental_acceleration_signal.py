"""Prospectively seal today's fundamental-acceleration reading.

Reads a candidate list (one row per ticker with `ticker`, `region`,
`sector`, and `factorPercentiles.quality`) and the live PIT fundamentals
files, computes the acceleration reading and cross-sectional composite for
exactly one as-of date, and appends immutable seal records to an
append-only JSONL store via `pipeline.fundamental_acceleration_seal`.

This is NOT part of the daily production build and changes no production
output. It is the prospective half of
`docs/challenger-2-fundamental-acceleration-v1-design.md`'s validation
plan: sealed now, scored only once each record's 126-trading-day horizon
matures against realised benchmark-relative returns, on some FUTURE
research module this script does not build.

WHERE THE CANDIDATE LIST COMES FROM
------------------------------------
The candidate list is passed as a JSONL file, one object per candidate,
shaped like a signal record's own identifying fields:
`{"ticker": ..., "region": "KR"|"US", "sector": ..., "factorPercentiles":
{"quality": <0-100 | null>}}`. The natural source is the live long-term
opportunity scan's own candidate universe (the same ~20-30 names per
region `longterm.score_cross_section` already ranks); wiring an extraction
step from that live output into this script's candidate-list input is left
to the workflow that invokes it, not decided here, so this script has no
coupling to `build.py`'s internal shape and can be tested and run entirely
standalone.

This first live invocation -- which fixes `PROSPECTIVE_START_DATE` for the
eventual confirmatory study -- happens after this PR merges and a
scheduled run executes with real `DART_API_KEY`/`FINNHUB_API_KEY` secrets;
neither is configured in this development sandbox.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import fundamental_acceleration_seal as SEAL   # noqa: E402
from pipeline import pit_data                                # noqa: E402


def _load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", help="JSONL: ticker/region/sector/factorPercentiles.quality")
    parser.add_argument("--pit-fundamentals", nargs="+", required=True,
                        help="One or more PIT fundamentals JSONL files (e.g. live pit-kr.jsonl pit-us.jsonl)")
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD, the sealing date")
    parser.add_argument("--seal-store", required=True,
                        help="Append-only JSONL to write sealed records into")
    args = parser.parse_args(argv)

    candidates = _load_jsonl(args.candidates)
    print(f"{len(candidates)} candidates loaded", flush=True)

    store = pit_data.FundamentalStore.from_many(args.pit_fundamentals)
    print(f"fundamentals store: {len(store)} filings across {len(store.tickers())} tickers, "
         f"diagnostics={store.diagnostics}", flush=True)

    rows = SEAL.build_candidate_rows(candidates, store, args.as_of)
    scored = SEAL.score_candidate_rows(rows)
    records = SEAL.seal_records(scored, args.as_of)

    sufficient = sum(1 for r in records if r["dataSufficient"])
    print(f"{len(records)} candidates read, {sufficient} data-sufficient "
         f"({sufficient / len(records) * 100:.1f}%)" if records else "0 candidates", flush=True)

    count = SEAL.append_seal(Path(args.seal_store), records)
    print(f"sealed {count} new records to {args.seal_store} for as-of {args.as_of}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
