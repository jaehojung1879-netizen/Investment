"""kr-alpha-atlas registry: the committed registry validates, the map is rendered from it, and every registry rule refuses the defect it exists for."""
from __future__ import annotations

import copy
import json

import pytest

from pipeline import kr_alpha_atlas_registry as A

REG = A.load()


def _mutate(fn):
    reg = copy.deepcopy(REG)
    fn(reg)
    return reg


def _feature(reg, fid):
    return next(f for f in reg["features"] if f["featureId"] == fid)


def test_committed_registry_validates_and_covers_all_ten_families():
    assert A.validate(REG)
    s = A.summary(REG)
    assert sorted(s["byFamily"]) == list("ABCDEFGHIJ") and all(v["features"] > 0 for v in s["byFamily"].values())
    assert s["features"] == len(REG["features"]) == sum(s["readiness"].values()) == sum(s["priorEvidence"].values())


def test_the_information_map_is_rendered_from_the_registry():
    assert (A.ROOT / A.MAP_PATH).read_text(encoding="utf-8") == A.render_map(REG)


def test_prior_study_references_resolve_to_the_sealed_verdicts():
    root = A.ROOT
    overlay = json.loads((root / REG["priorStudies"]["kr-model-overlay-portfolio-v1"]["resultPath"]).read_text())
    assert overlay["state"] == REG["priorStudies"]["kr-model-overlay-portfolio-v1"]["verdict"] == "DEVELOPMENT_REJECT"
    tournament = json.loads((root / REG["priorStudies"]["kr-alpha-discovery-tournament-v1"]["resultPath"]).read_text())
    assert tournament["verdict"]["verdict"] == REG["priorStudies"]["kr-alpha-discovery-tournament-v1"]["verdict"]
    v5 = json.loads((root / REG["priorStudies"]["alpha-opportunity-model-v5"]["resultPath"]).read_text())
    assert v5["overallStatus"] == REG["priorStudies"]["alpha-opportunity-model-v5"]["verdict"]
    market = json.loads((root / REG["priorStudies"]["kr-market-risk-model-v1"]["resultPath"]).read_text())
    assert market["decision"]["developmentNomination"] == REG["priorStudies"]["kr-market-risk-model-v1"]["verdict"]
    assert "NO_MODEL_EVIDENCE" in (root / REG["priorStudies"]["regional-alpha-model-v1"]["resultPath"]).read_text()


def test_h2_is_one_candidate_signal_family_not_the_program():
    h2 = _feature(REG, "B08_valueBusinessConfirmation")
    assert "CANDIDATE_SIGNAL_FAMILY" in h2["nextAction"] and h2["existingImplementation"] == ["pipeline/kr_alpha_signal_v2.py"]
    assert h2["existingResearchStatus"] != "UNTESTED"          # its fields entered the rejected overlay as fitted products
    assert any("B08_valueBusinessConfirmation" in i["features"] for i in REG["levelThreeInteractions"])


def test_blocked_information_blocks_its_interaction():
    statuses = A.summary(REG)["interactions"]
    assert statuses["X4_priceLeadershipByInvestorAccumulation"] == "BLOCKED"
    assert A.interaction_status(REG, REG["levelThreeInteractions"][3]) == ("BLOCKED", ["G01_foreignNetBuying"])


@pytest.mark.parametrize("mutation,code", [
    # a prior rejected study is never mislabelled as untested
    (lambda r: _feature(r, "B08_valueBusinessConfirmation").update(existingResearchStatus="UNTESTED", priorEvidenceReference=[]),
     "PRIOR_STUDY_NOT_CITED_BY_FEATURE|TESTED_FEATURE_LABELLED_UNTESTED"),
    (lambda r: _feature(r, "C13_fundamentalAcceleration").update(existingResearchStatus="UNTESTED"), "UNTESTED_FEATURE_CITES_PRIOR_EVIDENCE"),
    # missing point-in-time data cannot silently become a valid feature
    (lambda r: _feature(r, "I03_krTermSpread").update(readinessStatus="READY", blockingReason=None), "NON_PIT_FEATURE_MARKED_USABLE"),
    (lambda r: _feature(r, "G01_foreignNetBuying").update(readinessStatus="READY", blockingReason=None), "NON_PIT_FEATURE_MARKED_USABLE"),
    (lambda r: _feature(r, "B04_freeCashFlowYield").update(blockingReason=None), "BLOCKING_REASON_REQUIRED"),
    # readiness is not evidence and evidence is not a verdict
    (lambda r: _feature(r, "A01_return1d").update(nextAction="promote the WINNER"), "VERDICT_VOCABULARY_IN_REGISTRY"),
    (lambda r: _feature(r, "A03_return21d").update(readinessStatus="ALREADY_TESTED"), "ALREADY_TESTED_WITHOUT_AN_INDIVIDUAL_MEASUREMENT"),
    (lambda r: _feature(r, "A01_return1d").update(existingResearchStatus="PRIOR_POSITIVE_DEVELOPMENT"), "PRIOR_EVIDENCE_WITHOUT_REFERENCE"),
    # an OHLCV proxy is never investor flow
    (lambda r: _feature(r, "D11_accumulationDistributionProxy").update(family="G", featureId="G10_accumulationProxy"), "FAMILY_SOURCE_CLASS_MISMATCH"),
    # a cost or eligibility quantity never enters an alpha model
    (lambda r: r["levelTwoBaselines"]["B3_VOLUME_LIQUIDITY"].append("E03_capacityMedianTradedValue60"), "BASELINE_MEMBER_NOT_A_USABLE_MODEL_FEATURE"),
    (lambda r: r["levelTwoBaselines"]["B4_COMBINED_SIMPLE"].append("G01_foreignNetBuying"), "BASELINE_MEMBER_NOT_A_USABLE_MODEL_FEATURE"),
    # horizons are declared per family, not searched per feature
    (lambda r: _feature(r, "B01_bookToMarket").update(primaryHorizon=21), "FEATURE_HORIZON_NOT_REGISTERED_FOR_ITS_FAMILY"),
    (lambda r: r["levelThreeInteractions"].append(dict(r["levelThreeInteractions"][0], interactionId="X7")), "TOO_MANY_INTERACTIONS"),
    (lambda r: _feature(r, "A01_return1d").update(existingImplementation=["pipeline/does_not_exist.py"]), "IMPLEMENTATION_PATH_MISSING"),
    (lambda r: r["priorStudies"]["kr-factor-anatomy-v1"].update(resultPath="docs/results/missing.json"), "PRIOR_STUDY_RESULT_MISSING"),
    (lambda r: r["features"].append(copy.deepcopy(r["features"][0])), "DUPLICATE_FEATURE"),
    (lambda r: r["features"].__setitem__(slice(None), [f for f in r["features"] if f["family"] != "J"]), "FAMILY_WITHOUT_FEATURES"),
    (lambda r: r["multipleTesting"].update(declaredBeforeOutcomes=False), "MULTIPLE_TESTING_NOT_DECLARED"),
])
def test_every_registry_rule_refuses_its_defect(mutation, code):
    with pytest.raises(ValueError, match=code):
        A.validate(_mutate(mutation))


def test_registry_module_reads_no_outcome_and_is_not_imported_by_production():
    import ast
    tree = ast.parse((A.ROOT / "pipeline/kr_alpha_atlas_registry.py").read_text())
    local = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level for a in n.names}
    assert local == set()
    for prod in ("pipeline/build.py", "pipeline/longterm.py", "pipeline/kelly_portfolio.py", "pipeline/validate.py"):
        assert "kr_alpha_atlas" not in (A.ROOT / prod).read_text() and "kr_alpha_signal_v2" not in (A.ROOT / prod).read_text()


def test_executive_summary_and_roadmap_quote_the_registry_counts():
    import re
    s = A.summary(REG)
    summary = (A.ROOT / "docs/kr-alpha-atlas-executive-summary-ko.md").read_text(encoding="utf-8")
    quoted = {m.group(1): int(m.group(2)) for m in re.finditer(r"^\| ([A-Z_]+) \| (\d+) \|", summary, re.M)}
    assert quoted == s["readiness"]
    assert "(%d개 특성)" % s["features"] in summary
    assert "%d features in ten families" % s["features"] in (A.ROOT / "docs/kr-alpha-atlas-execution-roadmap.md").read_text(encoding="utf-8")
