"""Outcome-blind US source-readiness audit (us-source-readiness-v1).

    python scripts/audit_us_source_readiness.py <ledger/fundamentals/us> --output <json>

Reads only filing metadata and which concepts each filing states. No price,
return, label or model output is read.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import us_source_readiness as U  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = U.build_report(Path(args.store_dir))
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                 encoding="utf-8")
    store = report["pitStore"]
    print(f"{store['tickers']} tickers, {store['filings']} filings -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
