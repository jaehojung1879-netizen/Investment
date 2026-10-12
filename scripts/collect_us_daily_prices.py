"""Isolated US daily collector; no Git writes or scheduled-job activation.

Example: python scripts/collect_us_daily_prices.py /tmp/us-daily-observations
The output contains prices/us/<version> and universe/us/<version>. Production
signal-history and this checkout are rejected as direct destinations.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import collector_outcomes as CO  # noqa: E402
from pipeline import us_daily_market_data as D  # noqa: E402
from pipeline import us_daily_market_sources as S  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="Isolated ledger root outside the checkout")
    parser.add_argument("--session", action="append", help="Completed US session; at most the latest seven")
    parser.add_argument("--max-calls", type=int, default=600)
    parser.add_argument("--max-minutes", type=float, default=15)
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--recheck", action="store_true", help="Reacquire bounded existing observations to detect revisions")
    args = parser.parse_args(argv)
    try:
        # Validate the destination BEFORE even acquiring sources.
        store = D.ObservationStore(args.output)
        response = S.current_sp500()
        now = datetime.now(timezone.utc).isoformat()
        result = D.collect(args.output, response, S.yahoo_daily, now=now,
                           target_dates=args.session, max_calls=args.max_calls,
                           batch_size=args.batch_size, max_seconds=args.max_minutes*60, recheck=args.recheck)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if result["collectionComplete"] else 1
    except D.Refused as exc:
        result = {"schema": "US_DAILY_COLLECTION_REFUSAL_V1", "version": D.VERSION,
                  "sourceKind": D.LIVE, "availableFrom": S.now_utc(), "status": "REFUSED",
                  "collectionComplete": False, "outcome": exc.outcome, "code": exc.code,
                  "sourceMessage": str(exc), "expectedConstituentSecurityCount": None, "benchmarkStatus": "NOT_MEASURED",
                  "totalReturnComputed": False, "pitCompleteHistoricalUniverse": False}
        # A refusal remains visible even before a membership snapshot exists.
        if 'store' in locals() and exc.code != 'CONCURRENT_COLLECTION':
            with store.locked():
                store.save_manifest(result)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 1 if exc.outcome in CO.REFUSAL_OUTCOMES else 2


if __name__ == "__main__":
    raise SystemExit(main())
