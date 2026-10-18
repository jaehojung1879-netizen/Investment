"""Extend #247 census with WP2 identity coverage; default preview opens no data.

--inspect reads pinned LOCAL Git inputs only. Price values are immediately
projected to presence, filings to public-date/CIK metadata. No collection,
outcome store, result file, lock, training or production import is used.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import rp1_us_universe as U  # noqa: E402
from scripts import inspect_experiment_sources as S  # noqa: E402

SPEC = "docs/research-program/specs/rp1-wp2-us-universe-v1.json"
SPEC_DIGEST = "d61199584fac4599f6ab9efe08d79f7fc7489478773b67616984f41ed4a9963d"
EVIDENCE = "research_specs/alpha-opportunity-model-v3-us-identity-evidence.json.gz"
CODE = ("scripts/rp1_us_universe.py", "scripts/rp1_inspect_us_universe.py")
HELPERS = ("scripts/inspect_experiment_sources.py", "pipeline/experiment_workbench.py",
           "pipeline/alpha_opportunity_v3_identity.py", "pipeline/us_capital_allocation_coverage.py",
           "pipeline/us_cash_profitability.py", "pipeline/regional_alpha_features.py", "pipeline/replay_calendar.py")
HISTORICAL_CODE_COMMIT = "8b43d6ee55829b4db57a3b65cdb345b3523329d7"
LAYOUT = "docs/research-program/specs/rp1-wp2-code-layout-v1.json"


def historical_code(root, path):
    return subprocess.check_output(["git", "cat-file", "blob", HISTORICAL_CODE_COMMIT + ":" + path],
        cwd=root, env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})


def verify_historical_code(report, root=ROOT):
    """A frozen report pins the code THAT RAN, not its later file location.

    Keep every historical hash, require unchanged live helpers, and prove the
    relocated reader differs ONLY by equivalent absolute pipeline imports.
    This is separation from production, never a weaker import guard.
    """
    root = Path(root)
    layout = json.loads((root / LAYOUT).read_bytes())
    if layout["historicalCodeCommit"] != HISTORICAL_CODE_COMMIT or layout["scientificChange"] is not False:
        raise ValueError("HISTORICAL_CODE_COMMIT_CHANGED")
    result_path = "docs/research-program/results/rp1-wp2-us-universe-v1.json"
    for path, field in ((SPEC, "frozenSpecFileSha256"), (result_path, "frozenMeasurementSha256")):
        original_hash = hashlib.sha256(historical_code(root, path)).hexdigest()
        if hashlib.sha256((root / path).read_bytes()).hexdigest() != original_hash or layout[field] != original_hash:
            raise ValueError("FROZEN_WP2_ARTIFACT_CHANGED:" + path)
    if json.loads((root / result_path).read_bytes()) != report:
        raise ValueError("FOREIGN_MEASUREMENT_METADATA")
    for path, expected in report["codeHashes"].items():
        raw = historical_code(root, path)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("HISTORICAL_CODE_BYTES_CHANGED:" + path)
        if path not in {"pipeline/rp1_us_universe.py", "scripts/rp1_inspect_us_universe.py"}:
            if hashlib.sha256((root / path).read_bytes()).hexdigest() != expected:
                raise ValueError("WP2_LIVE_HELPER_CHANGED:" + path)
    original = ast.parse(historical_code(root, "pipeline/rp1_us_universe.py"))
    for node in ast.walk(original):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None:
            node.level, node.module = 0, "pipeline"
    moved = root / "scripts/rp1_us_universe.py"
    if (root / "pipeline/rp1_us_universe.py").exists():
        raise ValueError("RESEARCH_READER_STILL_IN_PRODUCTION_DIRECTORY")
    if ast.dump(original, include_attributes=False) != ast.dump(ast.parse(moved.read_bytes()), include_attributes=False):
        raise ValueError("RELOCATED_RESEARCH_LOGIC_CHANGED")
    if hashlib.sha256(moved.read_bytes()).hexdigest() != layout["relocatedModuleSha256"]:
        raise ValueError("RELOCATED_CODE_VERSION_CHANGED")
    old_cli = ast.parse(historical_code(root, "scripts/rp1_inspect_us_universe.py"))
    new_cli = ast.parse((root / "scripts/rp1_inspect_us_universe.py").read_bytes())
    for name in ("Sources", "validate_spec", "inspect"):
        old = next(n for n in old_cli.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == name)
        new = next(n for n in new_cli.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == name)
        if ast.dump(old, include_attributes=False) != ast.dump(new, include_attributes=False):
            raise ValueError("WP2_CENSUS_OR_SOURCE_POLICY_CHANGED:" + name)
    return layout


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
    if args.inspect:
        frozen = json.loads((ROOT / "docs/research-program/results/rp1-wp2-us-universe-v1.json").read_bytes())
        layout = verify_historical_code(frozen, ROOT)
        report = inspect(args.repo, json.loads((ROOT / SPEC).read_bytes()))
        report["implementationLayout"] = layout
    else:
        report = {"program": U.VERSION, "status": "PREVIEW_ONLY", "sourceReads": 0, "historicalExecutionAuthorized": False}
    print(json.dumps(report, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
