"""Outcome-free bounded collection of exact KRX daily capitalization and turnover.

No universe/label/model evaluation. Required dates are computed by the existing
KR calendar. No moving a missing signal to a date that happens to be served.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import kr_market_value as MV  # noqa: E402
from pipeline import replay_calendar as RC  # noqa: E402
from scripts.collect_krx_universe_snapshots import call, DEFAULT_BASE, ENDPOINT  # noqa: E402


def collect(directory, dates, *, key, max_calls=400, pace=.4, fetch=call):
    directory = Path(directory)
    count = 0
    for date in sorted(set(dates)):
        if (directory / (date + ".json")).exists():
            continue
        if count >= max_calls:
            break
        payload = fetch(DEFAULT_BASE, ENDPOINT, {"basDd": date.replace("-", "")}, key)
        count += 1
        records = MV.parse_market_values(payload, date)
        if not records:
            raise ValueError("EXPECTED_KRX_SESSION_EMPTY: " + date)
        # Invalid individual securities are retained as a named source failure;
        # never silently dropped from an apparently complete day.
        MV.write_day(directory, date, records)
        if pace:
            time.sleep(pace)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--end", default="2026-09-14")
    parser.add_argument("--max-calls", type=int, default=400)
    args = parser.parse_args()
    key = os.environ.get("KRX_API_KEY")
    if not key:
        parser.error("KRX_API_KEY_REQUIRED; no fabricated cache")
    print({"calls": collect(args.directory, [str(d.date()) for d in RC.sessions(args.start, args.end, "KR")],
                            key=key, max_calls=args.max_calls)})


if __name__ == "__main__":
    main()
