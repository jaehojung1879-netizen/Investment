
import pytest

from pipeline import benchmark_alpha as BA
from pipeline import portfolio_validation as PV
from scripts import run_benchmark_alpha_replay as RUN


class _Calibration:
    def __init__(self, value=2.0):
        self.value = value

    def expected(self, region, percentile):
        return {"expectedExcessReturnPct": self.value,
                "returnBasis": "GROSS_EXCESS_RETURN"}


def _candidate(ticker="A", region="US"):
    return {"ticker": ticker, "region": region, "sector": "Tech",
            "alphaPercentile": 90, "longTermResearchView": "POSITIVE",
            "evidenceCoverage": 1.0, "risk": {"downsideVolPct": 20},
            "entryState": "ENTER", "entry": {"entryState": "ENTER"}}


def test_realistic_cost_policy_uses_the_rate_effective_on_the_trade_date():
    cfg = BA.cost_config({})
    assert PV._dated_cost_policy(cfg["transactionCosts"]["KR"], "2018-12-31")["sellTaxBps"] == 30
    assert PV._dated_cost_policy(cfg["transactionCosts"]["KR"], "2024-06-01")["sellTaxBps"] == 18
    assert PV._dated_cost_policy(cfg["transactionCosts"]["KR"], "2026-06-01")["sellTaxBps"] == 20


def test_round_trip_crosses_one_full_spread_not_two():
    cfg = BA.cost_config({})
    # 2 * 5bp commissions + 6bp full spread + 0.3bp sell levy.
    assert BA._round_trip_cost_pct("US", "2024-01-01", cfg) == pytest.approx(0.163)


def test_incumbency_credit_changes_ordering_but_not_positive_alpha_gate():
    cfg = BA.cost_config({})
    new, held = BA.challenger_scores(
        [_candidate("NEW"), _candidate("HELD")], _Calibration(2.0), cfg,
        as_of="2024-01-01", incumbents={"HELD"})
    assert held["eligible"] and new["eligible"]
    assert held["score"] > new["score"]
    assert held["retentionCreditPct"] == pytest.approx(held["estimatedRoundTripCostPct"])

    bad = BA.challenger_scores(
        [_candidate("HELD")], _Calibration(0.10), cfg,
        as_of="2024-01-01", incumbents={"HELD"})[0]
    assert not bad["eligible"]
    assert "EXPECTED_NET_BENCHMARK_ALPHA_NOT_POSITIVE" in bad["exclusionCodes"]


def test_quarterly_rule_holds_drifted_weights_between_decisions(monkeypatch):
    candidates = [_candidate("A")]
    contexts = {d: (candidates, {}) for d in ("2024-01-01", "2024-02-01", "2024-04-01")}
    monkeypatch.setattr(BA, "_contexts", lambda signals, cfg: contexts)

    class FakeCalibration:
        def __init__(self, *args, **kwargs):
            pass
        def advance(self, date):
            pass
        def expected(self, region, percentile):
            return {"expectedExcessReturnPct": 2.0, "returnBasis": "GROSS_EXCESS_RETURN"}

    monkeypatch.setattr(PV, "ExpandingBucketCalibration", FakeCalibration)
    monkeypatch.setattr(PV, "_path_metrics", lambda *args, **kwargs: {"available": True})

    class FakeValuation:
        through = "2024-05-01"
        def window(self, decision, block):
            # A small drift makes it observable whether February re-targeted.
            terminal = {ticker: weight * 0.99 for ticker, weight in decision["weights"].items()}
            row = {**decision, "date": block["date"], "endDate": block["endDate"],
                   "terminalWeights": terminal,
                   "terminalRegionByTicker": dict(decision["regionByTicker"])}
            return row, {"status": "COMPLETE"}

    calendar = [
        {"date": "2024-01-01", "endDate": "2024-02-01", "signalDate": "2024-01-01"},
        {"date": "2024-02-01", "endDate": "2024-04-01", "signalDate": "2024-02-01"},
        {"date": "2024-04-01", "endDate": "2024-05-01", "signalDate": "2024-04-01"},
    ]
    cfg = {"horizonDays": 126, "minCashPct": 10, "maxPositionWeight": 1,
           "maxSectorWeight": 1, "regionCaps": {"US": 1},
           "selection": {"targetNames": 1, "minNames": 1,
                         "maxNamesPerSector": 1, "maxNamesPerRegion": 1}}
    result = BA.run_challenger([], [], cfg_lt={}, cfg_pf=cfg,
                               calendar=calendar, valuation=FakeValuation())
    jan, feb, apr = result["decisions"]
    assert jan["rebalanceDecision"] is True
    assert feb["rebalanceDecision"] is False
    assert apr["rebalanceDecision"] is True
    assert feb["weights"] == result["rows"][0]["terminalWeights"]


def test_freeze_manifest_never_promotes_the_challenger():
    manifest = BA.freeze_manifest()
    assert manifest["status"] == "CHALLENGER"
    assert manifest["promotionEligible"] is False
    assert manifest["liveValidated"] is False


def test_report_summary_keeps_cost_and_turnover_diagnostics():
    summary = RUN._summary_fields({
        "cagrPct": 8.0,
        "benchmarkCagrPct": 9.5,
        "grossCagrPct": 9.0,
        "costDragCagrPp": 1.0,
        "annualOneWayTurnoverX": 2.5,
        "mddPct": -20.0,
    })
    assert summary["grossBenchmarkGapPp"] == pytest.approx(-0.5)
    assert summary["annualOneWayTurnoverX"] == pytest.approx(2.5)
    assert summary["calmar"] == pytest.approx(0.4)


def test_decision_audit_is_quarterly_and_retains_cost_evidence():
    decisions = [
        {"date": "2024-01-02", "signalDate": "2024-01-02",
         "rebalanceDecision": True, "selectedTickers": ["A"],
         "weights": {"A": 0.4}, "valuationStatus": "COMPLETE",
         "topScores": [{"ticker": "A", "region": "US", "sector": "Tech",
                         "score": 1.0, "estimatedRoundTripCostPct": 0.163,
                         "expectedNetBenchmarkExcessPct": 1.2,
                         "irrelevantBulkField": "drop"}]},
        {"date": "2024-02-01", "signalDate": "2024-02-01",
         "rebalanceDecision": False, "selectedTickers": ["A"],
         "weights": {"A": 0.39}, "valuationStatus": "COMPLETE",
         "topScores": []},
    ]
    audit = RUN._compact_decisions(decisions)
    assert len(audit) == 1
    assert audit[0]["date"] == "2024-01-02"
    assert audit[0]["topScores"][0]["estimatedRoundTripCostPct"] == pytest.approx(0.163)
    assert "irrelevantBulkField" not in audit[0]["topScores"][0]
