"""Synthetic tests for entry-state-role-etf-residual-v1. No real ledger, price or outcome is read here."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline import entry_state_role_etf_residual as S

ROOT = Path(__file__).resolve().parent.parent


def test_frozen_spec_file_matches_module():
    frozen = json.loads((ROOT / S.SPEC_PATH).read_text())
    assert frozen["spec"] == S.spec()
    assert frozen["specSha256"] == S.spec_sha256()
    assert frozen["spec"]["promotionEligible"] is False


def test_regional_config_does_not_inherit_legacy_counts():
    cfg_pf = {"minCashPct": 15, "selection": {"targetNames": 5, "minNames": 3, "maxNamesPerRegion": 3,
                                                "maxNamesPerSector": 2}, "regionCaps": {"KR": 0.65, "US": 0.65}}
    for n in (1, 5, 10):
        cfg = S.regional_config(cfg_pf, "KR", n)
        assert cfg["selection"]["targetNames"] == n
        assert cfg["selection"]["maxNamesPerRegion"] == n
        assert cfg["selection"]["minNames"] == 0
        assert cfg["regionCaps"] == {"KR": 1.0}
    assert cfg_pf["selection"]["minNames"] == 3          # the caller's legacy config is not mutated


def test_ten_names_are_allowed_in_the_grid():
    assert 10 in S.SCENARIO_NAME_COUNTS and 0 in S.SCENARIO_NAME_COUNTS
    assert S.PRIMARY_NAME_COUNT_LABEL == "LEGACY_TARGET_SCENARIO_NOT_AN_OPTIMUM"


def _rows():
    def row(t, state, mult, score_core, sector):
        return {"ticker": t, "region": "KR", "sector": sector, "eligible": True, "exclusionCodes": [],
                "entryState": state, "entryStateMultiplier": mult, "score": score_core * mult,
                "convictionScore": score_core * mult, "downsideVolPct": 20.0, "alphaPercentile": 95,
                "risk": {"downsideVol": 0.2}}
    return [row("000001.KS", "WATCH", 0.5, 3.0, "A"), row("000002.KS", "ACCUMULATE", 1.0, 2.0, "B"),
            row("000003.KS", "ACCUMULATE", 1.0, 1.0, "C")]


def test_both_rungs_get_identical_budget_and_selector():
    cfg = S.regional_config({"minCashPct": 15, "maxPositionWeight": 0.6,
                             "selection": {"maxNamesPerSector": 2, "convictionTiltRange": 1.0}}, "KR", 1)
    rows = _rows()
    in_rank = S.decide(S.ENTRY_IN_RANK, rows, rows, None, cfg)
    at_weight = S.decide(S.ENTRY_AT_WEIGHT, rows, rows, None, cfg)
    assert in_rank["appliedMinCashPct"] == at_weight["appliedMinCashPct"]
    assert list(in_rank["weights"]) == ["000002.KS"]          # WATCH name's halved score loses the single slot
    assert list(at_weight["weights"]) == ["000001.KS"]        # alpha-only rank picks it, weight then halved
    assert at_weight["weights"]["000001.KS"] == pytest.approx(in_rank["weights"]["000002.KS"] * 0.5)
    assert at_weight["throttledWeight"] == pytest.approx(at_weight["weights"]["000001.KS"])
    assert S.decide(S.ENTRY_IN_RANK, rows, rows, None, S.regional_config(cfg, "KR", 0))["weights"] == {}


def test_residual_goes_to_etf_not_cash():
    target = S._residual_target({"000001.KS": 0.3}, "ETF", "069500.KS")
    assert target == pytest.approx({"000001.KS": 0.3, "069500.KS": 0.7})
    assert sum(S._residual_target({"000001.KS": 0.3}, "CASH", "069500.KS").values()) == pytest.approx(0.3)
    with pytest.raises(ValueError):
        S._residual_target({"a": 0.7, "b": 0.4}, "ETF", "069500.KS")


def test_cost_is_charged_once_per_leg_with_etf_rates():
    legs, cost = S.trade_legs({"069500.KS": 1.0}, {"069500.KS": 0.6, "000001.KS": 0.4}, "KR", "2024-03-04",
                              {"069500.KS"})
    by = {leg["ticker"]: leg for leg in legs}
    assert by["069500.KS"]["side"] == "sell" and by["069500.KS"]["instrument"] == "ETF"
    assert by["000001.KS"]["side"] == "buy" and by["000001.KS"]["instrument"] == "STOCK"
    assert cost == pytest.approx(sum(leg["costFraction"] for leg in legs))
    # KR stock sell pays the transaction tax, the ETF sell does not
    _, stock_sell = S.trade_legs({"000001.KS": 0.4}, {}, "KR", "2024-03-04", {"069500.KS"})
    _, etf_sell = S.trade_legs({"069500.KS": 0.4}, {}, "KR", "2024-03-04", {"069500.KS"})
    assert stock_sell > etf_sell
    assert S.trade_legs({"x": 0.5}, {"x": 0.5}, "KR", "2024-03-04", set()) == ([], 0.0)


def test_net_already_charged_refuses_another_cost():
    with pytest.raises(S.AdditionalCostRefused):
        S.refuse_additional_cost({"strategyId": "KR:ENTRY_AT_WEIGHT:N5:ETF", "costBasis": S.NET_ALREADY_CHARGED})
    S.refuse_additional_cost({"strategyId": "KR:ETF_ONLY", "costBasis": S.NO_COST})


class FakeValuation:
    """Two names and an ETF; a name absent from `prices` makes the block unvaluable."""
    through = "2030-01-01"

    def __init__(self, growth, missing=()):
        self.growth, self.missing = growth, set(missing)

    def window(self, decision, block):
        if any(t in self.missing for t in decision["weights"]):
            return None, {"status": "INCOMPLETE", "reasons": ["MISSING_PRICE_SESSION"]}
        g = {t: w * self.growth.get(t, 1.0) for t, w in decision["weights"].items()}
        total = sum(g.values()) + (1 - sum(decision["weights"].values()))
        return {"dailyDates": [block["date"], block["endDate"]], "dailyGrossNav": [1.0, total],
                "terminalWeights": {t: v / total for t, v in g.items()}}, {"status": "COMPLETE"}


CAL = [{"date": f"2020-0{i}-01", "endDate": f"2020-0{i + 1}-01", "signalDate": f"2020-0{i}-01"} for i in range(1, 8)]


def test_passive_path_carries_nav_and_never_trades():
    path = S.run_path(rung="PASSIVE", region="KR", n=0, residual="ETF", contexts={}, calibrator=None, calendar=CAL,
                      cfg_pf={}, valuation=FakeValuation({"069500.KS": 1.01}), fixed_target={"069500.KS": 1.0})
    assert path["status"] == "COMPLETE"
    assert all(b["legs"] == [] for b in path["blocks"])
    assert path["blocks"][-1]["navEnd"] == pytest.approx(1.01 ** 7)
    dates = [d for d, _ in path["daily"]]
    assert len(dates) == len(set(dates)) == 8                 # no duplicated rebalance session, no principal reset


def test_unvaluable_block_stops_the_path_instead_of_filling():
    path = S.run_path(rung="PASSIVE", region="KR", n=0, residual="ETF", contexts={}, calibrator=None, calendar=CAL,
                      cfg_pf={}, valuation=FakeValuation({}, missing={"069500.KS"}), fixed_target={"069500.KS": 1.0})
    assert path["status"] == "INPUT_UNAVAILABLE" and path["blocks"] == []
    assert S.path_metrics(path, path)["available"] is False
    assert S.horizon_windows(path, path, 126, 7)["available"] is False


def test_horizon_windows_report_pending_not_zero():
    etf = S.run_path(rung="PASSIVE", region="KR", n=0, residual="ETF", contexts={}, calibrator=None, calendar=CAL,
                     cfg_pf={}, valuation=FakeValuation({"069500.KS": 1.0}), fixed_target={"069500.KS": 1.0})
    h126 = S.horizon_windows(etf, etf, 126, len(CAL))
    assert h126["maturedAnchors"] == 2 and h126["pendingAnchorsNotMatured"] == 5
    h252 = S.horizon_windows(etf, etf, 252, len(CAL))
    assert h252["available"] is False and h252["status"] == "PENDING_NOT_MATURED"


def test_paired_difference_identical_paths_is_zero():
    etf = S.run_path(rung="PASSIVE", region="KR", n=0, residual="ETF", contexts={}, calibrator=None, calendar=CAL,
                     cfg_pf={}, valuation=FakeValuation({"069500.KS": 1.02}), fixed_target={"069500.KS": 1.0})
    diff = S.paired_difference(etf, etf)
    assert diff["pointEstimatePp"] == 0 and diff["ci95Pp"] == [0, 0]


def test_nav_rows_carry_the_contract_fields():
    etf = S.run_path(rung="PASSIVE", region="KR", n=0, residual="ETF", contexts={}, calibrator=None, calendar=CAL[:1],
                     cfg_pf={}, valuation=FakeValuation({"069500.KS": 1.0}), fixed_target={"069500.KS": 1.0},
                     strategy_id="KR:ETF_ONLY:069500.KS")
    rows = S.nav_rows(etf, currency="KRW", cost_basis=S.NO_COST, source={"sourceCommit": "abc", "inputSha256": "d"})
    for key in ("region", "strategyId", "currency", "frequency", "returnBasis", "costBasis", "evidenceClass",
                "sourceCommit", "inputSha256", "date", "nav"):
        assert key in rows[0]
    assert pd.Timestamp(rows[0]["date"]) and rows[0]["evidenceClass"] == S.EVIDENCE_CLASS


def test_committed_result_matches_frozen_spec_and_nav_contract():
    import csv
    import gzip
    run = ROOT / "research/entry_state_role_etf_residual_v1"
    result = json.loads((run / "result.json").read_text())
    assert result["spec"] == S.spec() and result["source"]["specSha256"] == S.spec_sha256()
    assert result["promotionEligible"] is False and result["evidenceClass"] == S.EVIDENCE_CLASS
    with gzip.open(run / "nav-daily.csv.gz", "rt") as stream:
        rows = list(csv.DictReader(stream))
    ids = {r["strategyId"] for r in rows}
    assert {"KR:ETF_ONLY:069500.KS", "US:ETF_ONLY:SPY", "US:SEPARATE_COMPARISON:QQQ",
            "KR:ENTRY_AT_WEIGHT:N5:ETF", "US:ENTRY_IN_RANK:N5:ETF"} <= ids
    for row in rows[:5] + rows[-5:]:
        assert row["currency"] in ("KRW", "USD") and row["frequency"] == "DAILY"
        if row["costBasis"] == S.NET_ALREADY_CHARGED:
            with pytest.raises(S.AdditionalCostRefused):
                S.refuse_additional_cost(row)
    for region in ("KR", "US"):
        for n in ("N1", "N2", "N3", "N4", "N5", "N10"):
            for residual in S.RESIDUALS:
                for rung in S.RUNGS:
                    assert result["regions"][region]["scenarios"][n][residual][rung]["metrics"]["available"] is True


def test_moved_spec_is_byte_identical_to_the_frozen_commit():
    import hashlib
    import subprocess
    record = json.loads((ROOT / "research/entry_state_role_etf_residual_v1/SPEC_PROVENANCE.json").read_text())
    current = (ROOT / S.SPEC_PATH).read_bytes()
    assert hashlib.sha256(current).hexdigest() == record["fileBytesSha256"]
    assert json.loads(current)["specSha256"] == record["specSha256Field"] == S.spec_sha256()
    try:
        frozen = subprocess.run(["git", "show", f"{record['frozenAtCommit']}:{record['frozenAtPath']}"], cwd=ROOT,
                                capture_output=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("frozen commit not in this checkout's history")
    assert frozen == current
