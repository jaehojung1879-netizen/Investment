"""Outcome-free WID filing-date/evidence inventory; default opens no sources."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import winner_inflection_admission as A  # noqa: E402
from pipeline import winner_inflection_filing_review as F  # noqa: E402
from scripts import inspect_experiment_sources as S  # noqa: E402


def inspect(root):
    root = Path(root)
    spec = json.loads((root / A.SPEC_PATH).read_bytes())
    if spec["sourceCommit"] != S.SOURCE_COMMIT or spec["metadataCommit"] != S.CODE_BASE:
        raise ValueError("SOURCE_COMMIT_OUTSIDE_FIXED_REUSE_SCOPE")
    source = S.Sources(root)
    rows = [r for year in range(2011, spec["sourceWindow"]["lastFilingFiscalYear"] + 1)
            for r in source.rows(f"ledger/fundamentals/us/finnhub-{year}.jsonl.gz")]
    accepted, withheld = F.reviewed_filings(rows)
    review_dir = root / "docs/winner-inflection-discovery/admission-review-v2"
    review = json.loads((review_dir / "review.json").read_bytes())
    citations = [citation for claim in review["claims"].values() for citation in claim.get("citations", [])]
    report_sha = A.file_sha(review_dir / "source-audit.json")
    return {"schema": "WID_FULL_FILING_DATE_AND_EVIDENCE_AUDIT_V3",
        "status": "BLOCKED", "sourceCommit": S.SOURCE_COMMIT, "metadataCommit": S.CODE_BASE,
        "inspectorSha256": A.file_sha(Path(__file__)),
        "executionModuleSha256": A.file_sha(root / "pipeline/winner_inflection_execution.py"),
        "widAdapterSha256": A.file_sha(root / "pipeline/winner_inflection_filing_review.py"),
        "filings": {"records": len(rows), "tickers": len({r["ticker"] for r in rows}),
                    "bothDatesFullyValid": len(accepted), "withheld": withheld,
                    "differentReviewedDays": sum(F.reviewed_public_day(r["availableFrom"]) != F.reviewed_public_day(r["acceptedDate"]) for r in accepted)},
        "v2Evidence": {"committedReportSha256": report_sha,
                       "allCitationsPinCommittedReport": bool(citations) and all(c["sha256"] == report_sha for c in citations),
                       "locallyByteVerified": bool(citations) and all(A.citation_verified(c) for c in citations),
                       "portableFromGitAlone": False,
                       "limitation": "Absolute external evidence references need explicit authorized materialization. Local availability never implies clean-environment availability; admission remains BLOCKED without exact bytes."},
        "sourceReceipts": source.receipts, "quoteReads": 0, "outcomeReads": 0,
        "modelFits": 0, "sourceMaterialization": False, "executionAuthorization": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args(argv)
    report = inspect(ROOT) if args.inspect else {"status": "PLAN_ONLY", "sourceReads": 0}
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
