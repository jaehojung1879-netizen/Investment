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
import prospective as PR  # noqa: E402


def _diff(a, b, path="", out=None):
    """Up to 20 differing paths, so a failing reproduction names what moved instead of dumping both trees."""
    out = [] if out is None else out
    if len(out) >= 20:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in {'fresh' if k in a else 'committed'}")
            else:
                _diff(a[k], b[k], f"{path}/{k}", out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            _diff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(f"{path}: fresh {str(a)[:80]!r} != committed {str(b)[:80]!r}")
    return out


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
    assert out["X"] == {"grade": "E4", "blocks": ["PIT_UNSAFE"], "decisionEligible": False, "track": "C_WATCHLIST_ONLY"}
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


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d["facts"].append({"field": "unobservedFutureReturnPct", "value": 999, "source": {"availableFrom": "2000-01-01"}}),
     "FACT_FIELD_NOT_ALLOWED"),
    (lambda d: d["facts"].append({"value": 1.0, "source": {"availableFrom": "2000-01-01"}}), "FACT_FIELD_NOT_ALLOWED"),
    (lambda d: d["facts"].append(dict(d["facts"][0])), "FACT_FIELD_DUPLICATED"),
    (lambda d: d["facts"][0].update(value=float("nan")), "FACT_VALUE_NOT_A_FINITE_NUMBER"),
    (lambda d: d["facts"][0].update(value=float("inf")), "FACT_VALUE_NOT_A_FINITE_NUMBER"),
    (lambda d: d["facts"][0].update(value="0.65"), "FACT_VALUE_NOT_A_FINITE_NUMBER"),
    (lambda d: d["facts"][0].update(value=None), "FACT_VALUE_NOT_A_FINITE_NUMBER"),
    (lambda d: d["facts"][0].update(value=True), "FACT_VALUE_NOT_A_FINITE_NUMBER"),
    (lambda d: d.update(facts=[]), "FACTS_MISSING"),
])
def test_an_unobserved_or_malformed_fact_is_refused(built, mutate, code):
    """#334 review G14: a number with no census source must never pass, whatever field name it carries."""
    d = copy.deepcopy(built["dossiers"][0])
    mutate(d)
    with pytest.raises(C.ContractError, match=code):
        C.validate_dossier(d, "E1", _census_rows(d["region"]))


def test_an_allowed_fact_missing_from_the_source_row_is_refused(built):
    d = copy.deepcopy(built["dossiers"][0])
    rows = _census_rows(d["region"])
    rows[d["ticker"]] = {k: v for k, v in rows[d["ticker"]].items() if k != "momentum12_2"}
    with pytest.raises(C.ContractError, match="FACT_FIELD_NOT_IN_SOURCE_ROW"):
        C.validate_dossier(d, "E1", rows)


def test_every_committed_and_published_fact_is_sourced():
    """census -> dossiers -> desk: every fact on the page is an allowed field equal to its census row value."""
    desk = json.loads((ROOT / "research" / "decision_desk_v1" / "desk.json").read_text())
    published = desk["evidenceFirst"]["dossiers"]["dossiers"]
    assert published == json.loads((HERE / "results" / "b3-dossiers.json").read_text())["dossiers"]
    for d in published:
        rows = _census_rows(d["region"])
        C.validate_dossier(d, d["nominatingEvidence"]["grade"], rows)
        assert {f["field"] for f in d["facts"]} == set(C.FACT_FIELDS)


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
    committed = json.loads(B3.CENSUS.read_text())
    assert not _diff(res, committed), _diff(res, committed)


# ----------------------------------------------------------------------------- integrity / definitions
INTEG = json.loads((HERE / "results" / "data-integrity.json").read_text())


def test_profitability_definitions_never_call_b1_a_reproduction():
    defs = {d["id"]: d for d in INTEG["definitions"]}
    assert defs["NM_GPA"]["buildable"] == "NO" and defs["FF_OP"]["buildable"] == "PARTIAL"
    assert "NOT a reproduction" in defs["B1_ROE"]["gap"]
    for g in ("KR", "US"):
        cmp_ = INTEG["regions"][g]["b1v2DryRun"]["rankingComparison"]
        assert cmp_["oiToBookEquity"]["n"] >= 50 and 0 < cmp_["oiToBookEquity"]["spearmanWithRoe"] < 1


def test_drop_sides_add_up_to_stage_four():
    census = json.loads(B3.CENSUS.read_text())
    for g in ("KR", "US"):
        st = census["regions"][g]["funnel"][4]
        sides = INTEG["regions"][g]["dropSides"]
        assert sum(sides["bySide"].values()) == sum(st["dropped"].values())
        for reason, n in st["dropped"].items():
            assert sum(sides["byReason"][reason].values()) == n
    assert INTEG["regions"]["KR"]["dropSides"]["byReason"]["NO_PIT_FILING"] == {"NOT_COLLECTED_BY_PIPELINE": 121}


def test_stale_share_counts_invalidate_per_share_facts_only():
    flagged = INTEG["regions"]["US"]["shareCounts"]["flagged"]
    assert "GOOGL" in flagged and flagged["GOOGL"]["lastShareCountAsFiled"] < "2022-07-15"  # before the 20:1 split
    dos = {d["ticker"]: d for d in json.loads((HERE / "results" / "b3-dossiers.json").read_text())["dossiers"]}
    wdc = {f["field"]: f for f in dos["WDC"]["facts"]}
    assert wdc["bookToPrice"]["invalid"] == "SHARE_COUNT_CARRIED_FORWARD_OVER_15_MONTHS"
    assert "invalid" not in wdc["roe"]


def test_dossier_facts_carry_each_fields_own_filing():
    for d in json.loads((HERE / "results" / "b3-dossiers.json").read_text())["dossiers"]:
        src = INTEG["regions"][d["region"]]["periods"]["byTicker"][d["ticker"]]
        for f in d["facts"]:
            if f["field"] in ("roe", "operatingMargin", "debtToEquity"):
                assert f["source"]["reportDate"] == src[f["field"]]["reportDate"]
        assert d["mixedReportPeriods"] == (len({v["reportDate"] for v in src.values()}) > 1)


def test_opm_rule_impact_is_reported_not_hidden():
    kr = INTEG["regions"]["KR"]["opmRule"]
    assert kr["addedAfterInspection"] and kr["verdict"] == "CHANGES_B1"
    assert kr["removed"]["402340.KS"]["wouldEnterDeepReview"] is True
    assert INTEG["regions"]["US"]["opmRule"]["verdict"] == "NO_CHANGE_TO_B1_DEEP_REVIEW"


# ----------------------------------------------------------------------------- prospective protocol
PROTO, PROTO_SHA = PR.protocol()


def test_industry_cap_and_weights():
    ind = {"A": "X", "B": "X", "C": "X", "D": "Y", "E": PR.UNCLASSIFIED, "F": PR.UNCLASSIFIED, "G": PR.UNCLASSIFIED, "H": "Z"}
    sel = PR.select_b1(list("ABCDEFGH"), ind, 5, 2)
    assert sel["selected"] == ["A", "B", "D", "E", "F"]
    assert sel["skipped"] == [{"ticker": "C", "reason": "INDUSTRY_CAP X"}]
    w = PR.weights(sel["selected"], "KR", 0.1)
    assert w["069500.KS"] == 0.5 and abs(sum(w.values()) - 1) < 1e-12
    assert PR.weights([], "US", 0.1) == {"SPY": 1.0}  # zero names is a valid cohort


def test_ai_can_only_remove_names_and_needs_reasons():
    assert PR.ai_filter(["A", "B"], None)["status"] == "NO_RECORD"
    ok = PR.ai_filter(["A", "B"], {"A": {"decision": "KEEP"}, "B": {"decision": "EXCLUDE", "reasons": ["낮은 이익 지속성", "업황 정점"]}})
    assert ok["selected"] == ["A"] and list(ok["excluded"]) == ["B"]
    for bad, code in (({"A": {"decision": "KEEP"}, "B": {"decision": "KEEP"}, "Z": {"decision": "KEEP"}}, "AI_MAY_NOT_ADD_NAMES"),
                      ({"A": {"decision": "KEEP"}}, "AI_REVIEW_INCOMPLETE"),
                      ({"A": {"decision": "KEEP"}, "B": {"decision": "EXCLUDE", "reasons": ["하나"]}}, "AI_EXCLUDE_NEEDS_TWO_REASONS"),
                      ({"A": {"decision": "KEEP"}, "B": {"decision": "EXCLUDE", "reasons": ["ROE 30%", "x"]}}, "NUMBER_IN_AI_REASON")):
        with pytest.raises(PR.ProtocolError, match=code):
            PR.ai_filter(["A", "B"], bad)


def test_dry_run_arms_share_one_basis_and_are_never_recorded():
    dry = json.loads((HERE / "results" / "prospective-dry-run.json").read_text())
    assert dry == json.loads(json.dumps(PR.dry_run(), ensure_ascii=False, sort_keys=True))
    assert dry["protocolSha256"] == PROTO_SHA and dry["activation"].startswith("ACTIVATION_BLOCKED")
    for g, v in dry["regions"].items():
        assert set(v["arms"]) == {"ETF100", "B1_ROE", "PRODUCTION", "B1_PLUS_AI"}
        assert v["common"]["label"] == "DRY_RUN_NOT_A_COHORT"
        assert v["arms"]["B1_PLUS_AI"]["status"] == "NO_RECORD"  # no review written under this protocol
        assert v["arms"]["B1_ROE"]["recordLabel"] == "UNVERIFIED_PROSPECTIVE_VIRTUAL"
        assert len(v["arms"]["B1_ROE"]["selection"]["selected"]) <= PROTO["portfolio"]["maxNames"]
    assert not (HERE / "dry-run").exists()  # nothing written to a ledger


def test_activation_requires_owner_file_and_resolved_gates(tmp_path):
    with pytest.raises(PR.ProtocolError, match="OWNER_APPROVAL_FILE_MISSING"):
        PR.assert_activation_allowed(tmp_path / "none.json")
    f = tmp_path / "approval.json"
    f.write_text(json.dumps({"protocolSha256": PROTO_SHA}))
    with pytest.raises(PR.ProtocolError, match="GATE_OPEN CI_GREEN"):
        PR.assert_activation_allowed(f)


def test_grade_tracks_separate_participation_from_approval():
    out = C.validate_grades(_j("evidence-grades.json"))
    assert {k for k, v in out.items() if v["track"] == "B_PROSPECTIVE_VIRTUAL"} == {"ACADEMIC_PROFITABILITY_US", "ACADEMIC_PROFITABILITY_KR"}
    assert not any(v["track"] == "A_VERIFIED_STRATEGY" for v in out.values())
    assert out["DESK_B2_2026_11"]["track"] == "C_WATCHLIST_ONLY"
    assert all(not v["decisionEligible"] for k, v in out.items() if v["track"] == "B_PROSPECTIVE_VIRTUAL")


@pytest.mark.skipif(not _signal_commit_available(), reason="pinned signal-history commit not fetched in this clone")
def test_production_receipt_is_read_by_decision_date():
    r = PR.production_receipt(json.loads(B3.CENSUS.read_text())["signalHistoryCommit"], "KR", "2026-11-06")
    assert r["weights"] == {"069500.KS": 1.0} and r["receiptId"].endswith("KR|2026-11-06")
    with pytest.raises(PR.ProtocolError, match="NO_UNIQUE_FINAL_WEEKLY_RECEIPT"):
        PR.production_receipt(json.loads(B3.CENSUS.read_text())["signalHistoryCommit"], "KR", "2026-11-07")


@pytest.mark.skipif(not _signal_commit_available(), reason="pinned signal-history commit not fetched in this clone")
def test_integrity_audit_reproduces_and_matches_the_committed_census():
    import integrity as IG
    fresh = json.loads(json.dumps(IG._round(IG.run()), ensure_ascii=False, sort_keys=True))
    assert not _diff(fresh, INTEG), _diff(fresh, INTEG)
