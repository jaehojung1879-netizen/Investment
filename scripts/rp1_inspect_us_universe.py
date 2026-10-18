"""Extend #247 census with WP2 identity coverage; default preview opens no data.

--inspect reads pinned LOCAL Git inputs only. Price values are immediately
projected to presence, filings to public-date/CIK metadata. No collection,
outcome store, result file, lock, training or production import is used.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import rp1_us_universe as U  # noqa: E402
from scripts import inspect_experiment_sources as S  # noqa: E402

SPEC = "docs/research-program/specs/rp1-wp2-us-universe-v1.json"
SPEC_DIGEST = "d61199584fac4599f6ab9efe08d79f7fc7489478773b67616984f41ed4a9963d"
EVIDENCE = "research_specs/alpha-opportunity-model-v3-us-identity-evidence.json.gz"
CODE = ("pipeline/rp1_us_universe.py", "scripts/rp1_inspect_us_universe.py")
HELPERS = ("scripts/inspect_experiment_sources.py", "pipeline/experiment_workbench.py",
           "pipeline/alpha_opportunity_v3_identity.py", "pipeline/us_capital_allocation_coverage.py",
           "pipeline/us_cash_profitability.py", "pipeline/regional_alpha_features.py", "pipeline/replay_calendar.py")


class Sources(S.Sources):
    """The unchanged census reader plus ONE pinned identity-evidence blob."""
    def blob(self, commit, path):
        if commit == S.CODE_BASE and path == EVIDENCE:
            raw = subprocess.check_output(["git", "cat-file", "blob", f"{commit}:{path}"], cwd=self.repo,
                env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})
            self.receipts[commit + ":" + path] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            return raw
        return super().blob(commit, path)


def validate_spec(spec):
    if (S.RI.digest(spec) != SPEC_DIGEST or spec["id"] != U.VERSION or spec["years"] != list(range(2013, 2026))
        or spec["threshold"] != {"numerator": 1, "denominator": 2, "everyYearRequired": True, "tieBreak": "R-a"}
        or spec["denominator"] != "ALL_STRICT_PRIOR_SP500_SNAPSHOT_MEMBER_DAYS_BEFORE_EXCLUSIONS"
        or not spec["pricePresenceOnly"] or spec["historicalExecutionAuthorized"]):
        raise ValueError("WP2_CONTRACT_CHANGED")


def inspect(repo, spec):
    validate_spec(spec)
    source = Sources(repo)
    manifest = json.loads(source.blob(S.SOURCE_COMMIT, S.MANIFEST))
    if S.RI.digest({k: v for k, v in manifest.items() if k != "sha256"}) != S.MANIFEST_SHA:
        raise ValueError("REPLAY_MANIFEST_CHANGED")
    source.allowed_objects = {ref for name, refs in manifest["components"].items() if name.startswith("price/20") for ref in refs}
    prices = defaultdict(set)
    for name, refs in sorted(manifest["components"].items()):
        if name.startswith("price/20"):
            for ref in refs:
                U.presence(source.component(ref), manifest["through"], prices)
    print("Price-presence projection loaded; no price path retained", file=sys.stderr)
    members = source.json(S.MEMBERS)["snapshots"]
    sectors = source.json(S.SECTORS)["snapshots"]
    evidence = source.json(EVIDENCE)
    if evidence["pinnedMembershipSha256"] != source.receipts[S.CODE_BASE + ":" + S.MEMBERS]["sha256"]:
        raise ValueError("IDENTITY_EVIDENCE_FOR_DIFFERENT_MEMBERSHIP")
    fields = set(spec["financialProjection"])
    metadata = []
    for year in range(2011, 2028):
        metadata.extend({k: v for k, v in row.items() if k in fields}
                        for row in source.rows(f"ledger/fundamentals/us/finnhub-{year}.jsonl.gz"))
    calendar = S.RC.sessions("2013-01-01", "2026-01-10", "US")
    days = [str(d.date()) for d in calendar if d.year in spec["years"]]
    weekly = [str(d.date()) for d in calendar.to_series().groupby(calendar.to_period("W")).max()
              if d.year in spec["years"]]
    daily = U.measure(members, sectors, evidence, prices, metadata, days, spec, through=manifest["through"])
    print("Daily population census complete; checking weekly compatibility", file=sys.stderr)
    compatibility = U.measure(members, sectors, evidence, prices, metadata, weekly, spec, through=manifest["through"])
    selected = daily["selection"]["selectedRule"]
    report = {"program": U.VERSION, "status": "OUTCOME_BLIND_POPULATION_MEASUREMENT",
        "contract": S.W.VERSION, "sourceCommit": S.SOURCE_COMMIT, "metadataCommit": S.CODE_BASE,
        "through": manifest["through"], "manifestSha256": S.MANIFEST_SHA,
        "specSha256": S.RI.digest(spec), "codeHashes": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in CODE + HELPERS},
        "primaryGrid": spec["primaryGrid"], "denominator": spec["denominator"], "threshold": spec["threshold"],
        "daily": daily, "weeklyCompatibility": {k: compatibility[k] for k in ("byYear", "selection", "sampleIdentity")},
        "studyA": {"wp2Decision": daily["selection"]["decision"], "a0Entry": "POPULATION_GATE_OPEN" if selected else "PROSPECTIVE_ONLY",
            "a0Passed": False, "a1Authorized": False, "identityStatus": ("PROVISIONAL" if selected == "R-b" else
                "CIK_MATCHED_PRICE_ID_STILL_UNVERIFIED" if selected else "UNRESOLVED"),
            "wp5Prerequisites": ["consume exact WP2 spec/source/sample IDs and known-conflict holds",
                "visible filing_prefix inputs, A-H1/H2/H3 measurement and fixed industry mapping",
                "60% measurability, prevalence/name-count/distinctness gates",
                "WP1 synthetic calibration for chosen horizon and MDE; no WP1 file modified",
                "no label access; WP0 and separate owner approval remain prerequisites to A1"]},
        "limitations": ["Historical S&P500 Git observations are not effective membership dates; no interpolation or current-universe replacement.",
            "CIK agreement verifies issuer consistency with filings, not the price vendor security identity or share-class rights.",
            "R-b admission counts provisional ticker joins, never VERIFIED_SECURITY. Known conflicts remain in full denominator.",
            "R-a reuses retrospective source-backed rename audit, not historical release evidence; no new price splice.",
            "Exited index names and absent prices do not prove delisting, zero payout, or verified terminal economics.",
            "Positive price presence is not sufficient trading liquidity or financial-feature measurability; WP5 must measure these separately.",
            "No new source acquisition, licensing grant, outcomes, ranking, fitted model or production promotion."],
        "accessCounters": {"outcomeReads": 0, "forwardPriceReads": 0, "labelReads": 0, "modelFits": 0, "locksCreated": 0},
        "historicalExecutionAuthorized": False, "sources": dict(sorted(source.receipts.items()))}
    U.scan_output(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    # Preview must not even read the spec, source repository or results.
    report = inspect(args.repo, json.loads((ROOT / SPEC).read_bytes())) if args.inspect else {
        "program": U.VERSION, "status": "PREVIEW_ONLY", "sourceReads": 0, "historicalExecutionAuthorized": False}
    print(json.dumps(report, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
