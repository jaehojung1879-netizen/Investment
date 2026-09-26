"""Apply `alpha_opportunity_v4_eligibility`'s policy to the real, already-
sealed KR terminated-security evidence. Input-only: reads two committed JSON
artifacts and writes a third. No price, return, label, IC or model is
touched anywhere in this script.

Usage:
    python scripts/audit_alpha_opportunity_v4_kr_eligibility.py \
        --reconstruction docs/results/kr-terminal-action-reconstruction-v2.json \
        --survivorship-audit docs/results/alpha-opportunity-model-v3-survivorship-audit.json \
        --output docs/results/alpha-opportunity-model-v4-eligibility-policy.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_v4_eligibility as ELIG  # noqa: E402
from pipeline.alpha_opportunity_spec import canonical  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconstruction", type=Path, required=True)
    parser.add_argument("--survivorship-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    reconstruction = json.loads(args.reconstruction.read_text(encoding="utf-8"))
    audit = json.loads(args.survivorship_audit.read_text(encoding="utf-8"))
    kr_terminations = audit["krTerminations"]

    def _relative(path: Path) -> str:
        # Reported relative to the repo root so the artifact is byte-identical
        # whatever cwd or absolute/relative form the caller invoked with.
        try:
            return str(path.resolve().relative_to(ROOT))
        except ValueError:
            return str(path)

    completeness_by_code = {row["code"]: row["completeness"] for row in reconstruction["securities"]}
    verdicts = ELIG.bulk_security_verdicts(kr_terminations=kr_terminations,
                                           completeness_by_code=completeness_by_code)
    by_reason: dict[str, int] = {}
    for v in verdicts:
        by_reason[v["reasonCode"] or v["status"]] = by_reason.get(v["reasonCode"] or v["status"], 0) + 1

    report = {
        "contract": "ALPHA_OPPORTUNITY_V4_KR_ELIGIBILITY_POLICY_RESULT_V1",
        "policyModule": "pipeline/alpha_opportunity_v4_eligibility.py",
        "policyContract": ELIG.CONTRACT,
        "inputs": {
            "reconstructionPath": _relative(args.reconstruction),
            "reconstructionFoundationStatus": reconstruction.get("foundationStatus"),
            "survivorshipAuditPath": _relative(args.survivorship_audit),
        },
        "securitiesEvaluated": len(verdicts),
        "eligibleTodaySecurityLevel": sum(1 for v in verdicts if v["status"] == ELIG.ELIGIBLE),
        "ineligibleTodaySecurityLevel": sum(1 for v in verdicts if v["status"] == ELIG.INELIGIBLE),
        "conditionallyEligiblePendingTotalReturnSeriesBuild": sum(
            1 for v in verdicts
            if v["status"] == "CONDITIONALLY_ELIGIBLE_PENDING_TOTAL_RETURN_SERIES_BUILD"),
        "reasonCounts": by_reason,
        "verdicts": verdicts,
        "note": ("A security read here as INELIGIBLE or CONDITIONALLY_ELIGIBLE has no forward "
                 "return, IC, label or model computed anywhere by this script. This is a "
                 "metadata-only application of a predeclared policy to already-sealed "
                 "completeness evidence."),
        "historicalOutcomesComputed": False,
        "labelsConstructed": False,
        "modelsTrained": False,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(report) + b"\n")
    print(json.dumps({"written": str(args.output), "securitiesEvaluated": len(verdicts),
                      "reasonCounts": by_reason}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
