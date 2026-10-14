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


INTEGRATION = ROOT / "docs/us-readiness/us-factor-integration-readiness-v1.json"


def _integration_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("integration_audit", ROOT / "scripts/audit_us_factor_integration_readiness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_integration_groups_cover_every_inventory_factor_exactly_once():
    module = _integration_script()
    ids = [f["id"] for f in load(INVENTORY)["factors"]]
    grouped = [fid for g in module.GROUPS.values() for fid in g["ids"]]
    assert sorted(grouped) == sorted(ids) and len(grouped) == len(set(grouped))
    for g in module.GROUPS.values():
        assert set(g["needs"]) <= set(module.REQUIREMENTS)


def test_integration_report_admits_nothing_and_every_return_reading_needs_terminal_and_lineage():
    report = load(INTEGRATION)
    assert report["candidatePricesAdmitted"] is False and report["pr241FilesModified"] is False
    assert report["readsReturns"] is False and report["authorizes"] == "NOTHING"
    assert {"TERMINAL_CONSIDERATION", "SPLIT_DIVIDEND_LINEAGE", "HISTORICAL_SECURITY_IDENTITY"} <= set(report["labelRequirements"])
    for row in report["factorMatrix"]:
        assert row["researchResumable"] != "YES"
        if row["featureRequires"]:
            assert row["labelRequires"] == report["labelRequirements"]
    headline = report["pr241Evidence"]["headline"]
    assert headline["recoveredMembershipSessions"] == 186910 and headline["missingMembershipSessionsBefore"] == 256402
    basis = report["requirementStatus"]["SPLIT_DIVIDEND_LINEAGE"]["measured"]["coveredIdentifiersByBasis"]
    assert sum(v["identifiers"] for v in basis["byBasis"].values()) == basis["identifiers"] == 175
    assert basis["sessionLevelBasisCounts"].startswith("UNMEASURED")
    # only the sanitized #241 head is referenced: no superseded commit, raw archive or observation panel
    assert report["pr241Evidence"]["commit"] == "1e016bd9a4ff746a9b69958624182c6287301f51"
    text = INTEGRATION.read_text()
    assert "a6da327f" not in text and "observations-" not in text and "raw-0fa0" not in text


def test_roadmap_blocks_any_forward_return_reading_until_admission():
    rm = load(ROADMAP)
    gate = rm["datasetAdmissionGate"]
    assert [c["id"][:3] for c in gate["checks"]] == ["AD%d" % i for i in range(1, 9)]
    assert "never PROSPECTIVE" in gate["result"] and "never PROMOTION_ELIGIBLE" in gate["result"]
    mf1 = next(e for e in rm["experiments"] if e["id"] == "US-MF-1")
    assert mf1["forwardReturnReadingBlockedUntil"][0].startswith("datasetAdmissionGate")
    assert "B1" in mf1["exactTestAfterAdmission"] and "B2" in mf1["exactTestAfterAdmission"]
    assert rm["evidenceTiers"]["rule"].startswith("a repaired historical panel is never described as unseen")
    assert rm["nextImplementationTask"]["startsAfter"].startswith("#241 is merged")
