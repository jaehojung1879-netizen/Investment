"""The committed weekly-passive-first-v1 replay and its path accounting."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import run_weekly_passive_first_replay as R

ROOT = Path(__file__).resolve().parent.parent
RESULT = ROOT / "docs/weekly-decision/weekly-passive-first-v1-replay.json"
SPEC = ROOT / "docs/weekly-decision/weekly-passive-first-v1.json"


def _row(date, end, weights, daily, terminal, region="KR"):
    return {"date": date, "endDate": end, "weights": weights,
            "regionByTicker": {t: region for t in weights},
            "terminalRegionByTicker": {t: region for t in terminal},
            "terminalWeights": terminal, "dailyDates": [date, end], "dailyGrossNav": daily,
            "grossReturn": daily[-1] - 1, "benchmarkReturn": 0.0}


def test_account_charges_dated_costs_and_chains_blocks():
    bench = {"069500.KS"}
    rows = [_row("2018-01-02", "2018-02-01", {"069500.KS": 1.0}, [1.0, 1.10], {"069500.KS": 1.0}),
            _row("2018-02-01", "2018-03-02", {"A": 0.15, "069500.KS": 0.85}, [1.0, 1.0],
                 {"A": 0.15, "069500.KS": 0.85})]
    path = R.account(rows, bench)
    buy_etf = R.W.trade_cost_fraction("KR", "2018-01-02", is_benchmark=True, side="buy")
    assert path["costs"][0] == pytest.approx(buy_etf)
    sell_etf = R.W.trade_cost_fraction("KR", "2018-02-01", is_benchmark=True, side="sell")
    buy_stock = R.W.trade_cost_fraction("KR", "2018-02-01", is_benchmark=False, side="buy")
    assert path["costs"][1] == pytest.approx(0.15 * (sell_etf + buy_stock))
    assert path["dates"] == ["2018-01-02", "2018-02-01", "2018-03-02"]
    assert path["nav"][-1] == pytest.approx((1 - buy_etf) * 1.10 * (1 - path["costs"][1]))
    assert path["nameTrades"] == 1 and path["names"] == [0, 1]


def test_account_refuses_a_trade_without_a_region():
    rows = [_row("2018-01-02", "2018-02-01", {"X": 1.0}, [1.0, 1.0], {"X": 1.0})]
    rows[0]["regionByTicker"] = {}
    rows[0]["terminalRegionByTicker"] = {}
    with pytest.raises(ValueError):
        R.account(rows, {"069500.KS"})


def test_guard_refuses_overwrite_and_ledger_paths(tmp_path):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    with pytest.raises(ValueError):
        R._guard(ledger / "x.json", ledger)
    existing = tmp_path / "out.json"
    existing.write_text("{}")
    with pytest.raises(FileExistsError):
        R._guard(existing, ledger)


def test_committed_result_matches_the_frozen_spec_and_is_labelled():
    result = json.loads(RESULT.read_text())
    assert result["specSha256"] == hashlib.sha256(SPEC.read_bytes()).hexdigest()
    assert result["evidenceClass"] == "POST_OUTCOME_EXPOSED_EXPLORATORY_PORTFOLIO_REPLAY"
    assert result["promotionEligible"] is False and result["liveValidated"] is False
    assert result["calendar"]["cadence"] == "21_SESSION_ANCHORS_NOT_WEEKLY"
    kr, us = result["regions"]["KR"], result["regions"]["US"]
    assert kr["headlineEligible"] is True and us["headlineEligible"] is False
    assert us["status"] == "SURVIVORSHIP_BIASED_PARTIAL"
    assert kr["benchmarkDefinition"] == "BENCHMARK_DEFINITION_REPLAY_V16_NOT_RECONCILED"
    for region in (kr, us):
        p0, p1 = region["paths"]["P0"], region["paths"]["P1"]
        assert p0["available"] and p1["available"]
        assert p1["startDate"] == p0["startDate"] and p1["endDate"] == p0["endDate"]
        assert p1["benchmarkCagrPct"] == p0["cagrPct"]
        assert len(region["decisions"]) == result["calendar"]["blocks"] == 155
        assert all(d["stockCount"] <= 5 for d in region["decisions"])
