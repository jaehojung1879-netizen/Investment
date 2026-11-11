"""Evidence-first v2: grades, path mapping, B3 dossier contract and reproducibility of the frozen results."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import academic_path as AP  # noqa: E402
import b3_dossiers as B3  # noqa: E402
import contract as C  # noqa: E402


def _j(name):
    return json.loads((HERE / name).read_text())


# ----------------------------------------------------------------------------- grades
def test_grade_matrix_is_valid_and_nothing_is_decision_eligible():
    out = C.validate_grades(_j("evidence-grades.json"))
    eligible = [k for k, v in out.items() if v["decisionEligible"] and v["grade"] != "BENCHMARK"]
    assert eligible == []
    assert out["ETF_BASELINES"]["grade"] == "BENCHMARK"
    assert out["DESK_B2_2026_11"]["blocks"] == ["PIT_CONTAMINATED"]
    assert max(v["grade"] for v in out.values() if v["grade"] != "BENCHMARK") <= "E1"


def test_grade_is_sequential_and_a_famous_paper_cannot_skip_a_level():
    item = {"id": "X", "criteria": {"E1": {"met": True, "ref": "paper"}, "E2": {"met": False, "ref": "r"},
                                    "E3": {"met": True, "ref": "r"}}}
    assert C.compute_grade(item) == "E1"
    with pytest.raises(C.ContractError, match="GRADE_SKIPS_A_LEVEL"):
        C.validate_grades({"items": [item]})


def test_e5_needs_owner_approval_and_criteria_need_evidence():
    crit = {lvl: {"met": True, "ref": "r"} for lvl in C.LEVELS}
    with pytest.raises(C.ContractError, match="E5_WITHOUT_OWNER_APPROVAL"):
        C.validate_grades({"items": [{"id": "X", "criteria": crit}]})
    with pytest.raises(C.ContractError, match="CRITERION_WITHOUT_EVIDENCE"):
        C.validate_grades({"items": [{"id": "Y", "criteria": {"E1": {"met": True}}}]})


def test_blocked_item_is_never_decision_eligible_and_unknown_blocks_are_refused():
    crit = {lvl: {"met": True, "ref": "r"} for lvl in C.LEVELS[:4]}
    out = C.validate_grades({"items": [{"id": "X", "criteria": crit, "blocks": ["PIT_UNSAFE"]}]})
    assert out["X"] == {"grade": "E4", "blocks": ["PIT_UNSAFE"], "decisionEligible": False}
    with pytest.raises(C.ContractError, match="UNKNOWN_BLOCK"):
        C.validate_grades({"items": [{"id": "Z", "criteria": {}, "blocks": ["LOOKS_FINE"]}]})


# ----------------------------------------------------------------------------- paths
def test_v3_mapping_labels_legacy_ledger_rows_without_rewriting_them():
    ledger = ROOT / "research" / "decision_desk_v1" / "dry-run" / "ledger.jsonl"
    before = ledger.read_bytes()
    rows = [json.loads(x) for x in before.decode().splitlines() if x.strip()]
    labelled = {C.v3_path(r) for r in rows if "path" in r}
    assert labelled <= set(C.V3_PATHS) and "v3.B1" not in labelled
    assert ledger.read_bytes() == before
    assert C.v3_path({"path": "B1"}) == "v3.B2" and C.v3_path({"path": "B2"}) == "v3.B3"


# ----------------------------------------------------------------------------- B3 contract
@pytest.fixture(scope="module")
def built():
    return B3.build()


def _census_rows(region):
    reg = json.loads(B3.CENSUS.read_text())["regions"][region]
    return {r["ticker"]: r for r in reg["b1"]["topQuintile"]}


def test_committed_dossiers_equal_a_fresh_build(built):
    assert json.loads((HERE / "results" / "b3-dossiers.json").read_text()) == built
    assert len(built["dossiers"]) == 10
    assert {d["status"] for d in built["dossiers"]} == {"HOLD_FOR_RESEARCH"}
    assert {d["nominatingEvidence"]["grade"] for d in built["dossiers"]} == {"E1"}


def test_a_digit_in_ai_text_is_refused(built):
    d = copy.deepcopy(built["dossiers"][0])
    d["interpretation"] = ["ROE가 약 65%로 높다"]
    with pytest.raises(C.ContractError, match="NUMBER_IN_AI_TEXT"):
        C.validate_dossier(d, "E1", _census_rows(d["region"]))


def test_a_fact_that_differs_from_the_census_is_refused(built):
    d = copy.deepcopy(built["dossiers"][0])
    d["facts"][0]["value"] = d["facts"][0]["value"] + 0.01
    with pytest.raises(C.ContractError, match="FACT_DIFFERS_FROM_SOURCE"):
        C.validate_dossier(d, "E1", _census_rows(d["region"]))


def test_a_fact_published_after_the_cutoff_is_refused(built):
    d = copy.deepcopy(built["dossiers"][0])
    d["facts"][0]["source"] = dict(d["facts"][0]["source"], availableFrom="2027-01-01")
    with pytest.raises(C.ContractError, match="FACT_NOT_PUBLIC_AT_CUTOFF"):
        C.validate_dossier(d, "E1", _census_rows(d["region"]))


def test_status_cannot_exceed_the_nominating_grade_and_forecast_fields_are_refused(built):
    d = copy.deepcopy(built["dossiers"][0])
    d["status"] = "PROSPECTIVE_CANDIDATE"
    with pytest.raises(C.ContractError, match="STATUS_ABOVE_EVIDENCE"):
        C.validate_dossier(d, "E1", _census_rows(d["region"]))
    C.validate_dossier(d, "E2", _census_rows(d["region"]))
    d2 = copy.deepcopy(built["dossiers"][0])
    d2["targetPrice"] = "높음"
    with pytest.raises(C.ContractError, match="FORBIDDEN_FIELD"):
        C.validate_dossier(d2, "E1", _census_rows(d2["region"]))


def test_a_name_no_screen_nominated_is_refused(built):
    d = copy.deepcopy(built["dossiers"][0])
    d["ticker"] = "009150.KS"
    with pytest.raises(C.ContractError, match="NOT_NOMINATED_BY_A_QUANT_SCREEN"):
        C.validate_dossier(d, "E1", _census_rows("KR"))


def test_counter_arguments_are_required(built):
    d = copy.deepcopy(built["dossiers"][0])
    d["counterArguments"] = d["counterArguments"][:1]
    with pytest.raises(C.ContractError, match="NEEDS_COUNTER_ARGUMENTS"):
        C.validate_dossier(d, "E1", _census_rows(d["region"]))


def test_samsung_electro_mechanics_is_not_backfilled():
    text = (HERE / "ai-dossiers-2026-11.json").read_text()
    assert "009150" not in text and "삼성전기" not in text


# ----------------------------------------------------------------------------- reproducibility
def test_academic_path_reproduces_from_the_frozen_french_files():
    res = AP._round(AP.run())
    committed = json.loads((HERE / "results" / "academic-path.json").read_text())
    assert res == committed
    assert committed["verdict"] == "WEAK_OR_ABSENT_AFTER_PUBLICATION"
    assert not any(committed["significantAtBonferroni"].values())


def test_census_funnel_is_internally_consistent():
    census = json.loads(B3.CENSUS.read_text())
    for region, reg in census["regions"].items():
        f = reg["funnel"]
        for prev, cur in zip(f[:4], f[1:5]):  # stages 1-4 are sequential drops with reasons
            assert prev["remaining"] - sum(cur["dropped"].values()) == cur["remaining"], (region, cur["stage"])
        assert f[6]["remaining"] >= len(reg["b1"]["topQuintile"]) >= len(reg["b1"]["deepReview"])
        assert f[7]["remaining"] == len(reg["b1"]["deepReview"]) <= 5
        assert f[8]["remaining"] == 0


def _signal_commit_available() -> bool:
    import census as CE
    return subprocess.run(["git", "cat-file", "-e", f"{CE.SIGNAL_COMMIT}^{{commit}}"], cwd=ROOT,
                          capture_output=True).returncode == 0


@pytest.mark.skipif(not _signal_commit_available(), reason="pinned signal-history commit not fetched in this clone")
def test_census_reproduces_from_the_pinned_signal_history_commit():
    import census as CE
    res = json.loads(json.dumps(CE.run(), ensure_ascii=False, sort_keys=True, default=float))
    assert res == json.loads(B3.CENSUS.read_text())
