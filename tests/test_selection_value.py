"""What each layer of the construction is worth, and whose ranking a null tested.

Two separate guarantees live here. The ladder's arithmetic must actually
decompose (a split that does not add back up is worse than no split), and a
permutation null must say which selector it permuted — the report published one
unlabelled null computed from the champion's conviction score, and the promotion
gate read it whatever selector a promotion concerned.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from pipeline import portfolio_validation as PV
from pipeline import provenance as prov_mod
from pipeline import selection_value as SV
from pipeline import validate as V

ROOT = Path(__file__).resolve().parents[1]


def _rows(book, bench, *, weights=None, terminal=None):
    """Minimal block rows: one return pair per block, optional held weights."""
    out = []
    for index, (b, m) in enumerate(zip(book, bench)):
        row = {"date": f"2020-{index + 1:02d}-01", "endDate": f"2020-{index + 2:02d}-01",
               "grossReturn": b, "benchmarkReturn": m,
               "weights": (weights[index] if weights else {"A": 1.0})}
        if terminal:
            row["terminalWeights"] = terminal[index]
        out.append(row)
    return out


# --------------------------------------------------------------------------- #
# decompose_edge
# --------------------------------------------------------------------------- #
def test_edge_split_adds_back_to_the_geometric_gap():
    """The whole point of the split is that the parts reconstruct the total."""
    rng = np.random.default_rng(5)
    book = rng.normal(0.01, 0.03, 60)
    bench = rng.normal(0.01, 0.05, 60)
    split = SV.decompose_edge(_rows(book, bench), years=5.0)

    assert split["available"]
    assert (split["arithmeticSelectionEdgePp"] + split["compoundingEdgePp"]
            == pytest.approx(split["geometricGrossEdgePp"], abs=1e-9))


def test_a_less_volatile_book_earns_a_positive_compounding_term_without_picking():
    """This is the defect the split exists to expose.

    Both paths have the SAME arithmetic mean, so no name was picked better. The
    book is simply less dispersed, so it loses less to variance drag and ends
    richer. Reported as a single CAGR gap that reads as stock-selection skill —
    and on the published calibrated challenger it is 88% of the headline edge.
    """
    steady = [0.02] * 40
    choppy = [0.12, -0.08] * 20          # identical mean, far more dispersed
    assert np.mean(steady) == pytest.approx(np.mean(choppy))

    split = SV.decompose_edge(_rows(steady, choppy), years=10.0)
    assert split["arithmeticSelectionEdgePp"] == pytest.approx(0.0, abs=1e-9)
    assert split["compoundingEdgePp"] > 0
    assert split["geometricGrossEdgePp"] > 0
    assert split["blockSdRatio"] < 1.0


def test_edge_split_is_unavailable_rather_than_zero_without_blocks():
    assert SV.decompose_edge([], years=5.0)["available"] is False
    assert SV.decompose_edge(_rows([0.01], [0.01]), years=0)["available"] is False


# --------------------------------------------------------------------------- #
# decompose_turnover
# --------------------------------------------------------------------------- #
def test_turnover_split_separates_replacing_a_name_from_retargeting_a_weight():
    """They have opposite remedies, so one number for both answers nothing.

    Block 2 retargets the same two names; block 3 swaps one name out. A no-
    retarget band removes the first at no change in what is held; only holding
    different names removes the second.
    """
    weights = [{"A": 0.5, "B": 0.5}, {"A": 0.7, "B": 0.3}, {"A": 0.7, "C": 0.3}]
    rows = _rows([0.0] * 3, [0.0] * 3, weights=weights, terminal=weights)
    split = SV.decompose_turnover(rows)

    assert split["rebalances"] == 2
    # Block 2: |0.7-0.5| + |0.3-0.5| = 0.4 one-way 0.2, all retargeting.
    # Block 3: B (0.3) out, C (0.3) in -> one-way 0.3, all name replacement.
    assert split["fromWeightRetargetPct"] == pytest.approx(10.0)
    assert split["fromNameReplacementPct"] == pytest.approx(15.0)
    assert split["averageOneWayTurnoverPct"] == pytest.approx(25.0)
    assert split["nameReplacementSharePct"] == pytest.approx(60.0)


def test_turnover_split_measures_against_the_drifted_book_not_the_entry_weights():
    """Carrying a drifted position costs nothing, so drift is not turnover."""
    entry = [{"A": 0.5, "B": 0.5}, {"A": 0.6, "B": 0.4}]
    drifted = [{"A": 0.6, "B": 0.4}, {"A": 0.6, "B": 0.4}]
    rows = _rows([0.0, 0.0], [0.0, 0.0], weights=entry, terminal=drifted)
    split = SV.decompose_turnover(rows)

    # Block 2 re-enters at exactly where block 1 drifted to: nothing traded.
    assert split["averageOneWayTurnoverPct"] == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# broad_config
# --------------------------------------------------------------------------- #
def test_broad_config_opens_name_counts_and_leaves_every_risk_cap_alone():
    """Holding more names must not become a way of holding more risk."""
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["kellyPortfolio"]
    broad = SV.broad_config(cfg, pool_size=24, tilt_range=SV.TILT_OFF)

    assert broad["selection"]["targetNames"] == 24
    assert broad["selection"]["maxNamesPerSector"] == 24
    assert broad["selection"]["maxNamesPerRegion"] == 24
    for cap in ("maxPositionWeight", "maxSectorWeight", "maxThemeWeight", "minCashPct"):
        assert broad[cap] == cfg[cap], cap


def test_tilt_off_is_the_absence_of_the_tilt_not_a_fitted_value():
    """A ladder rung that tuned its own knob would not be an ablation."""
    assert SV.TILT_OFF == 0.0
    broad = SV.broad_config({"selection": {}}, pool_size=10, tilt_range=SV.TILT_OFF)
    assert broad["selection"]["convictionTiltRange"] == 0.0


# --------------------------------------------------------------------------- #
# eligibility_rows
# --------------------------------------------------------------------------- #
def test_eligibility_excludes_on_facts_about_the_name_never_on_a_score():
    """Same split `selection_null` draws: a score decision is not eligibility."""
    cfg = {"watchWeightMultiplier": 0.5, "waitForPullbackWeightMultiplier": 0.25}
    candidates = [
        {"ticker": "OK", "region": "US", "longTermResearchView": "POSITIVE",
         "entryState": "ACCUMULATE_GRADUALLY", "risk": {"downsideVolPct": 20.0},
         "alphaPercentile": 10.0},
        {"ticker": "AVOIDED", "region": "US", "longTermResearchView": "POSITIVE",
         "entryState": "AVOID", "risk": {"downsideVolPct": 20.0}},
        {"ticker": "NORISK", "region": "US", "longTermResearchView": "POSITIVE",
         "entryState": "ACCUMULATE_GRADUALLY", "risk": {}},
    ]
    rows = {row["ticker"]: row for row in SV.eligibility_rows(candidates, cfg)}

    # A low alpha percentile is a score opinion and never excludes here.
    assert rows["OK"]["eligible"] is True
    assert rows["AVOIDED"]["exclusionCodes"] == ["ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING"]
    assert rows["NORISK"]["exclusionCodes"] == ["DOWNSIDE_RISK_UNAVAILABLE"]
    # With no ranking supplied every score ties, so nothing leaks an ordering.
    assert {row["score"] for row in rows.values()} == {0.0}


# --------------------------------------------------------------------------- #
# The null names its selector
# --------------------------------------------------------------------------- #
def test_selection_null_stamps_the_selector_on_an_unavailable_result_too():
    """An unlabelled null is what let the gate read the wrong selector's verdict."""
    blob = PV.selection_null({}, {}, [], [], cfg_pf={}, horizon=21, draws=2,
                             selector=PV.CHALLENGER)
    assert blob["available"] is False
    assert blob["selector"] == PV.CHALLENGER


def test_selection_null_defaults_to_the_champion_and_says_which_score_it_used():
    blob = PV.selection_null({}, {}, [], [], cfg_pf={}, horizon=21, draws=2)
    assert blob["selector"] == PV.CHAMPION
    assert blob["scoreSource"] == "PRODUCTION_CONVICTION_SCORE"

    injected = PV.selection_null({}, {}, [], [], cfg_pf={}, horizon=21, draws=2,
                                 selector=PV.CHALLENGER, score_fn=lambda c, d: [])
    assert injected["scoreSource"] == "INJECTED_SELECTOR_SCORE"


# --------------------------------------------------------------------------- #
# The promotion gate matches the null to the selector being promoted
# --------------------------------------------------------------------------- #
def _payload(**historical) -> dict:
    return {
        "portfolioName": "t",
        "meta": {"modelsTrained": 1, "coveragePct": 100, "coverageFloor": 95},
        "generatedAt": "2026-01-02T00:00:00Z", "core": [], "screened": [],
        "tradeIdeas": {"KR": [], "US": []}, "runMode": "paperTrading",
        "dataMode": "live", "schemaVersion": prov_mod.SCHEMA_VERSION,
        "modelVersion": prov_mod.MODEL_VERSION,
        "provenance": {"schemaVersion": prov_mod.SCHEMA_VERSION,
                       "modelVersion": prov_mod.MODEL_VERSION,
                       "runMode": "paperTrading", "marketAsOf": "2026-01-02",
                       "dataMode": "live"},
        "marketDataHealth": {"missingCritical": [], "staleCritical": []},
        "recommendationsBlocked": False,
        "historicalValidation": {
            "evidenceClass": "HISTORICAL_OOS", "available": True,
            "benchmarkCoverageGate": {"eligible": True},
            "contractValidation": {"eligible": True},
            "pipelineHealth": {"status": "OK", "blocksEvidence": False,
                               "recordsInOtherGenerations": 0},
            "dataIntegrity": {"integrityGate": {"eligible": True}},
            **historical,
        },
    }


def _errors(tmp_path, payload) -> list[str]:
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return V.validate(str(path), production=False)


def test_a_promotion_backed_by_another_selectors_null_is_refused(tmp_path):
    """The exact hole: BEATS_RANDOM about the champion, promoting the challenger.

    The two selectors do not rank alike — on replay-v16 the champion's
    arithmetic selection edge is -1.589pp/yr against the challenger's +0.040pp —
    so the champion clearing its null says nothing about the challenger.
    """
    payload = _payload(portfolioReplay={
        "selectionNull": {"selector": PV.CHAMPION,
                          "overall": {"verdict": "BEATS_RANDOM"}},
        "promotionEvidence": {"promotionEligible": True,
                              "promotedSelector": PV.CHALLENGER,
                              "humanApprovalRequired": False},
    })
    errors = _errors(tmp_path, payload)
    assert "selection_null_describes_a_different_selector" in errors
    # The verdict itself was BEATS_RANDOM, so the older check cannot catch this.
    assert "selector_promotion_without_selection_null_support" not in errors


def test_a_promotion_backed_by_its_own_selectors_null_passes_the_match(tmp_path):
    payload = _payload(portfolioReplay={
        "selectionNull": {"selector": PV.CHALLENGER,
                          "overall": {"verdict": "BEATS_RANDOM"}},
        "promotionEvidence": {"promotionEligible": True,
                              "promotedSelector": PV.CHALLENGER,
                              "humanApprovalRequired": False},
    })
    errors = _errors(tmp_path, payload)
    assert "selection_null_describes_a_different_selector" not in errors
    assert "selector_promotion_without_selection_null_support" not in errors


def test_an_unlabelled_null_cannot_support_a_promotion(tmp_path):
    """Every published null before this change carried no selector at all."""
    payload = _payload(portfolioReplay={
        "selectionNull": {"overall": {"verdict": "BEATS_RANDOM"}},
        "promotionEvidence": {"promotionEligible": True,
                              "promotedSelector": PV.CHALLENGER,
                              "humanApprovalRequired": False},
    })
    assert "selection_null_describes_a_different_selector" in _errors(tmp_path, payload)


def test_the_match_is_not_demanded_while_nothing_is_being_promoted(tmp_path):
    """`promotionEligible` is hardcoded False today; the gate must stay quiet."""
    payload = _payload(portfolioReplay={
        "selectionNull": {"selector": PV.CHAMPION,
                          "overall": {"verdict": "INDISTINGUISHABLE_FROM_RANDOM"}},
        "promotionEvidence": {"promotionEligible": False, "humanApprovalRequired": True,
                              "promotedSelector": PV.CHALLENGER},
    })
    errors = _errors(tmp_path, payload)
    assert "selection_null_describes_a_different_selector" not in errors
    assert "selector_promotion_without_selection_null_support" not in errors


def test_the_replay_names_the_selector_a_promotion_would_move(tmp_path):
    """Without this field the validator has nothing to match the null against."""
    assert PV.CHALLENGER != PV.CHAMPION
    payload = _payload(portfolioReplay={
        "selectionNull": {"selector": PV.CHALLENGER,
                          "overall": {"verdict": "BEATS_RANDOM"}},
        "promotionEvidence": {"promotionEligible": True, "humanApprovalRequired": False},
    })
    assert "selection_null_describes_a_different_selector" in _errors(tmp_path, payload)
