"""Rebuild KR filings from the raw DART row store, and publish the evidence for every mapping.

Reads `DART_RAW_STATEMENT_ROWS_V1` shards (`scripts/collect_dart_raw_statements.py`)
and writes `DART_RAW_FILINGS_V1`-shaped records (`pipeline.dart_canonical_accounts`)
under the same `dart-YYYY.jsonl.gz` names the sealed feature path already reads,
into a SEPARATE directory. It never writes into `ledger/fundamentals/kr`, whose
28 blobs are the sealed v4 execution input.

The report it writes is the review surface for the one mapping change: for each
of the four gate accounts, every (statement, label, account id) combination the
IFRS element rule admitted that the exact-label rule would not have, with how
many filings carry it; every AMBIGUOUS resolution; and, for filings the legacy
store also holds, whether the served receipt number changed (an amendment
served since) and whether any label-matched amount disagrees.

Outcome-free: reads DART rows only.

Usage:
    python scripts/build_kr_canonical_filings.py <raw-store> <output-dir>
        [--legacy-dir ledger/fundamentals/kr]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import dart_canonical_accounts as C  # noqa: E402
from pipeline import dart_fundamentals as DF  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402


def build(raw_dir: Path, output: Path, legacy_dir: Path | None = None) -> dict:
    legacy = {}
    if legacy_dir is not None:
        for path in sorted(legacy_dir.glob("dart-*.jsonl.gz")):
            for row in HS.read_jsonl(path):
                legacy[row["id"]] = row
    by_year: dict[int, list[dict]] = {}
    refused: Counter = Counter()
    admitted: dict[str, Counter] = {a: Counter() for a in C.ELEMENT_RULES}
    rules: dict[str, Counter] = {a: Counter() for a in C.ELEMENT_RULES}
    receipt_changed = amount_disagrees = compared = 0
    for path in sorted(raw_dir.glob("raw-*.jsonl.gz")):
        for raw in HS.read_jsonl(path):
            record, reason = C.canonical_record(raw)
            if record is None:
                refused[reason] += 1
                continue
            by_year.setdefault(record["fiscalYear"], []).append(record)
            for account, how in record["canonicalization"]["accounts"].items():
                rules[account][f"{how.get('rule')}|{how.get('statement')}"] += 1
                if how.get("rule") == C.IFRS_ELEMENT_ID:
                    admitted[account][(how["statement"], how["label"], how["accountId"])] += 1
            old = legacy.get(record["id"])
            if old is not None:
                compared += 1
                receipt_changed += old.get("receiptNos") != record["receiptNos"]
                for account, how in record["canonicalization"]["accounts"].items():
                    before = (old.get("accounts") or {}).get(account)
                    if (how.get("rule") == C.LEGACY_EXACT_LABEL and before
                            and before.get("statement") == how["statement"]
                            and before.get("amounts") != record["accounts"][account]["amounts"]):
                        amount_disagrees += 1
    output.mkdir(parents=True, exist_ok=True)
    for year, rows in sorted(by_year.items()):
        HS.write_shard(DF.shard_path(output, year), rows)
    report = {
        "contract": C.CONTRACT,
        "records": sum(len(v) for v in by_year.values()),
        "refused": dict(refused),
        "resolutionRuleByAccount": {a: dict(sorted(c.items())) for a, c in rules.items()},
        "admittedOnlyByElementId": {
            a: [{"statement": s, "label": label, "accountId": aid, "filings": n}
                for (s, label, aid), n in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))]
            for a, c in admitted.items()},
        "comparedWithLegacyStore": {"filings": compared, "receiptNumbersChanged": receipt_changed,
                                    "labelMatchedAmountsDisagreeing": amount_disagrees},
    }
    (output / "canonicalization-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--legacy-dir", type=Path)
    args = parser.parse_args(argv)
    if args.output_dir.resolve() == (args.legacy_dir.resolve() if args.legacy_dir else None):
        raise ValueError("REFUSING_TO_WRITE_INTO_THE_SEALED_LEGACY_STORE")
    if args.output_dir.resolve().name == "kr" and args.output_dir.resolve().parent.name == "fundamentals":
        raise ValueError("REFUSING_TO_WRITE_INTO_THE_SEALED_LEGACY_STORE")
    report = build(args.raw_dir, args.output_dir, args.legacy_dir)
    print(json.dumps({k: report[k] for k in ("records", "refused", "resolutionRuleByAccount",
                                             "comparedWithLegacyStore")}, ensure_ascii=False, indent=1))
    for account, rows in report["admittedOnlyByElementId"].items():
        for row in rows[:15]:
            print(f"  {account} <- {row['statement']} {row['label']} {row['accountId']} x{row['filings']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
