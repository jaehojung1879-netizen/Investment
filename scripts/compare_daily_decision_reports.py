"""Compare two local Portfolio D report.json files without modifying either."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.daily_decision_delta import compare  # noqa: E402

MAX_FILE_BYTES = 4 * 1024 * 1024


def read_report(path):
    file = Path(path)
    if file.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("REPORT_SIZE_LIMIT")
    with file.open(encoding="utf-8") as source:
        return json.load(source, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path, help="earlier generated report.json")
    parser.add_argument("--after", required=True, type=Path, help="later generated report.json")
    args = parser.parse_args(argv)
    try:
        result = compare(read_report(args.before), read_report(args.after))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
