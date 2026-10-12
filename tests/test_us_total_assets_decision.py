"""The committed total-assets plan, sample and decision are what the code produces, say what they claim, and claim nothing live."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from pipeline import us_total_assets_decision as D  # noqa: E402
import probe_us_total_assets_sources as P  # noqa: E402

DECISION = ROOT / "docs/us-readiness/us-total-assets-source-decision-v1.json"
PLAN = ROOT / "docs/us-readiness/us-total-assets-source-probe-plan-v1.json"
DOC = ROOT / "docs/us-total-assets-source-rescue-ko.md"


def test_committed_decision_is_exactly_what_the_module_builds_and_it_validates():
    decision = D.build()
    assert D.validate(decision) == []
    assert json.loads(DECISION.read_text(encoding="utf-8")) == json.loads(json.dumps(decision))


def test_committed_plan_is_exactly_the_keyless_plan_for_the_sealed_sample():
    report = P.run(P.load_sample(), list(P.SOURCES), 0, contact=None, env={})
    assert json.loads(PLAN.read_text(encoding="utf-8")) == json.loads(json.dumps(report))
    assert report["sources"]["sec"]["plannedRequests"] and all(v["verdict"] == "PENDING_OWNER_DISPATCH" for v in report["sources"].values())
    assert "observedAt" not in report, "a plan carries no wall-clock value, so it can be re-derived byte for byte"


def test_exactly_one_primary_and_one_fallback_and_the_ranking_is_total():
    rec = D.RECOMMENDATION
    assert (rec["primary"]["route"], rec["fallback"]["route"]) == ("B", "E") and D.RANKING == ["B", "A", "E", "C", "D"]
    assert {r["id"] for r in D.ROUTES} == set("ABCDE")


def test_validate_refuses_an_untested_route_described_as_accessible_or_a_live_claim():
    decision = json.loads(json.dumps(D.build()))
    decision["routes"][3]["testedAccessibility"]["status"] = "ACCESSIBLE"
    decision["routes"][1]["testedAccessibility"]["thisPullRequest"] = "TESTED: 200"
    decision["routes"][2]["totalAssetsCoverage"]["measuredForSample"] = "32 of 32"
    problems = D.validate(decision)
    assert any("UNTESTED_ROUTE_DESCRIBED_AS_ACCESSIBLE" in p for p in problems)
    assert any("A_LIVE_RESULT_IS_CLAIMED" in p for p in problems)
    assert any("SAMPLE_COVERAGE_CLAIMED_WITHOUT_A_RUN" in p for p in problems)
    same = json.loads(json.dumps(D.build()))
    same["recommendation"]["fallback"]["route"] = "B"
    assert "PRIMARY_AND_FALLBACK_MUST_BE_TWO_DIFFERENT_ROUTES" in D.validate(same)


def test_massive_sunset_endpoint_and_unmeasured_claims_are_stated():
    text = json.dumps(D.build(), ensure_ascii=False)
    assert "/vX/reference/financials" in text and "never used" in text
    assert "LATEST filing" in text
    assert all(r["totalAssetsCoverage"]["measuredForSample"] == "NOT_TESTED" for r in D.ROUTES)


def test_korean_report_carries_the_required_sections_and_never_claims_a_live_result():
    doc = DOC.read_text(encoding="utf-8")
    for needle in ("실제 요청은 한 건도 실행하지 않았다", "EXACT_ACCESSION", "RECENTLY_MISSING", "HISTORICAL_EARLIEST", "secBlockCleared", "sec_contact",
                   "total-assets-source-probe", "LIVE_WITHHELD_NOT_MAIN_DISPATCH", "주 경로: B", "보조 경로: E", "소유자가 승인할 것", "NOT_TESTED",
                   "/vX/reference/financials", "38250579358", "하지 않은 것"):
        assert needle in doc, needle
    for forbidden in ("SEC 차단이 해소되었", "SEC block has disappeared", "접근 가능함을 확인"):
        assert forbidden not in doc
