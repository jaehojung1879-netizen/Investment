"""Reacquire pinned public GitHub candidate CSVs from an observed audit plan.

Manual only. No paid sources, schedule, provider fallback, outcome or publication.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import us_departed_price_recovery as R  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--source', choices=sorted(R.BASIS), default='A')
    parser.add_argument('--budget', type=int, default=175)
    args = parser.parse_args(argv)
    stage = args.stage.resolve()
    if stage.is_relative_to(ROOT) or any((p / '.git' / 'HEAD').exists() for p in [stage, *stage.parents]):
        raise ValueError('STAGING_MUST_BE_OUTSIDE_REPOSITORY_CHECKOUTS')
    if stage.exists() and any(stage.iterdir()):
        raise ValueError('REQUIRE_FRESH_ISOLATED_STAGING')
    if not 1 <= args.budget <= 500: raise ValueError('REQUEST_BUDGET_OUT_OF_BOUNDS')
    plan = json.loads(args.plan.read_bytes())
    if plan['version'] != R.VERSION: raise ValueError('WRONG_ACQUISITION_CONTRACT')
    ids = {r['auditIdentifier'] for r in plan['inventory']}
    urls = [{'ticker': r['ticker'], 'source': r['source'], 'url': r['url'], 'expectedSha256': r['sha256']}
            for r in plan['acquisition'] if r['source'] == args.source and r.get('status') == 200 and r['ticker'] in ids]
    def fetch(url):
        with requests.get(url, timeout=(10, 25), stream=True) as response:
            chunks, total = [], 0
            for chunk in response.iter_content(65536):
                total += len(chunk)
                if total > 5 * 1024 * 1024: raise ValueError('PER_FILE_BYTE_BUDGET')
                chunks.append(chunk)
            return response.status_code, b''.join(chunks)
    started = time.monotonic()
    records = R.acquire(urls, stage, fetch=fetch, budget=args.budget,
                        now=lambda: datetime.now(timezone.utc).isoformat())
    print(json.dumps({'requests': len(records), 'elapsedSeconds': round(time.monotonic() - started, 2),
                      'successfulImmutableObjects': sum(r.get('status') == 200 and not r.get('revisionMismatch') for r in records),
                      'productionPublication': False}))
    return 0 if all(r.get('status') == 200 and not r.get('revisionMismatch') for r in records) else 1


if __name__ == '__main__':
    raise SystemExit(main())
