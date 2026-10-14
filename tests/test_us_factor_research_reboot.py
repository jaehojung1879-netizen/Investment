"""US factor research reboot v1: the committed inventory and roadmap.

Pinned here:
  * both files are reproduced byte for byte by the builder from committed evidence (no hand-typed measurement);
  * every reference is pinned by the SHA-256 of the file it was read from;
  * every factor carries every inventory field, and statuses come from the declared vocabularies only;
  * a factor with no derivation never claims a measured coverage;
  * nothing is authorized, nothing is registered, the recovery verdict is not assumed, and at most three experiments are proposed;
  * neither file carries a score, weight, pick, holding, expected return or tier for any stock.
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "docs/us-readiness/us-factor-inventory-v1.json"
ROADMAP = ROOT / "docs/us-readiness/us-multifactor-research-roadmap-v1.json"
BUILDER = ROOT / "scripts/build_us_factor_research_reboot.py"

FIELDS = {"id", "family", "name", "formula", "units", "directionConvention", "codePath", "dataSource", "publiclyObservableFrom", "pitRequirements",
          "corporateActionAndShareCountDependencies", "sectorApplicability", "availability", "measuredCoverage", "missingReasonCodes",
          "adjustedPriceDependency", "departedSecurityDependency", "identityRisk", "outcomeExposure", "economicMechanism", "majorConfounders",
          "measuredRedundancy", "uniqueVariation", "feasibility"}
FORBIDDEN_KEYS = {"expectedReturn", "expectedExcessReturn", "weight", "weights", "targetWeight", "pick", "picks", "holdings", "position", "positions",
                  "recommendation", "recommendations", "tier", "radarTier", "entryState", "score", "scores", "liveValidated"}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from keys(v)


def test_committed_files_are_reproduced_by_the_builder():
    run = subprocess.run([sys.executable, str(BUILDER), "--check"], cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


def test_references_are_pinned_by_content_hash():
    for doc in (load(INVENTORY), load(ROADMAP)):
        for ref in doc["references"].values():
            assert hashlib.sha256((ROOT / ref["path"]).read_bytes()).hexdigest() == ref["sha256"], ref["path"]


def test_every_factor_is_complete_and_uses_the_declared_vocabularies():
    inv = load(INVENTORY)
    availability = set(inv["categories"]["availability"])
    exposure = set(inv["categories"]["outcomeExposure"])
    ids = [f["id"] for f in inv["factors"]]
    assert len(ids) == len(set(ids))
    families = {f["family"] for f in inv["factors"]}
    assert len(families) == 8                                     # the A-H candidate taxonomy, no more
    for f in inv["factors"]:
        assert set(f) == FIELDS, f["id"]
        assert f["availability"]["historical"] in availability, f["id"]
        assert f["outcomeExposure"]["status"] in exposure, f["id"]
        if f["codePath"] == "NOT_IMPLEMENTED":
            assert not ({"nonFinancial", "allSectors"} & set(f["measuredCoverage"])), f["id"]   # inputs may be measured; the feature is not
            assert f["availability"]["historical"] != "SURVIVOR_CONDITIONED", f["id"]
    assert not any(f["outcomeExposure"]["status"] == "PROSPECTIVELY_VALIDATED" for f in inv["factors"])


def test_measured_numbers_carry_their_source_and_denominator():
    inv = load(INVENTORY)
    for f in inv["factors"]:
        for value in f["measuredCoverage"].values():
            if isinstance(value, dict) and "value" in value:
                assert value["source"].startswith("docs/") and value["denominator"], f["id"]
        if f["uniqueVariation"]:
            assert f["uniqueVariation"]["source"] == "docs/us-readiness/us-factor-unique-variation-v1.json"


def test_roadmap_authorizes_nothing_and_assumes_no_recovery():
    rm = load(ROADMAP)
    assert rm["authorization"] == "NOT_AUTHORIZED" and rm["authorizes"] == "NOTHING"
    assert rm["status"] == "PROPOSED_NOT_REGISTERED" and rm["productionEffect"] == "NONE"
    assert rm["dependsOn"]["codexDepartedPriceRecovery"]["assumedVerdict"] is None
    assert set(rm["dataQualityGate"]["routing"]) == {"FULL", "PARTIAL", "INSUFFICIENT"}
    assert 1 <= len(rm["experiments"]) <= 3
    assert [e["priority"] for e in rm["experiments"]] == [1, 2, 3]
    assert all(e["ownerAuthorizationRequired"] for e in rm["experiments"])
    assert rm["researchBudget"]["primaryClaimsTotal"] == len(rm["experiments"])


def test_no_stock_level_decision_output_anywhere():
    for doc in (load(INVENTORY), load(ROADMAP)):
        assert not (set(keys(doc)) & FORBIDDEN_KEYS)
        assert doc.get("readsReturns") is False


def test_builder_reads_no_price_return_or_model_module():
    tree = ast.parse(BUILDER.read_text())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imported <= {"__future__", "argparse", "hashlib", "json", "sys", "pathlib"}
