"""Merge the raw-statement canonicalization and the original-XBRL store into one candidate.

Both sources write `DART_RAW_FILINGS_V1`-shaped records
(`pipeline.dart_canonical_accounts.canonical_record` and
`pipeline.dart_xbrl_statements.canonical_record_from_xbrl`), keyed the same
way (`ticker:fiscalYear:reportCode`), so the sealed feature path reads either
unchanged. This script never edits either source directory; it writes a
THIRD, merged directory, and raises rather than silently picking a side if
the two sources ever disagree about the same filing -- they should never
describe the same one (`kr-xbrl-original` covers only fiscal-2015 Q1/H1/Q3;
`kr-canonical-v2` covers every filing the raw-statement collector reached),
so a collision is a signal something upstream changed scope, not a case to
merge through.

Usage:
    python scripts/merge_kr_candidate_snapshot.py <output-dir>
        --canonical-dir <kr-canonical-v2> [--xbrl-dir <kr-xbrl-original>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import dart_fundamentals as DF  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402


def merge(output: Path, canonical_dir: Path, xbrl_dir: Path | None) -> dict:
    by_year: dict[int, dict[str, dict]] = {}
    sources: dict[str, str] = {}
    for path in sorted(canonical_dir.glob("dart-*.jsonl.gz")):
        for row in HS.read_jsonl(path):
            by_year.setdefault(row["fiscalYear"], {})[row["id"]] = row
            sources[row["id"]] = "canonical-v2"
    if xbrl_dir is not None:
        for path in sorted(xbrl_dir.glob("dart-xbrl-*.jsonl.gz")):
            for row in HS.read_jsonl(path):
                if row["id"] in sources:
                    raise ValueError(
                        f"CANDIDATE_SOURCE_COLLISION: {row['id']} is described by both "
                        f"{sources[row['id']]} and the original-XBRL store")
                by_year.setdefault(row["fiscalYear"], {})[row["id"]] = row
                sources[row["id"]] = "xbrl-original"
    output.mkdir(parents=True, exist_ok=True)
    for year, rows in sorted(by_year.items()):
        HS.write_shard(DF.shard_path(output, year), list(rows.values()))
    report = {"records": len(sources), "bySource": {}}
    for source in set(sources.values()):
        report["bySource"][source] = sum(1 for s in sources.values() if s == source)
    (output / "merge-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--canonical-dir", type=Path, required=True)
    parser.add_argument("--xbrl-dir", type=Path)
    args = parser.parse_args(argv)
    report = merge(args.output_dir, args.canonical_dir, args.xbrl_dir)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
