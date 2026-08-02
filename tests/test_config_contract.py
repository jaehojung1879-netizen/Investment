import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_kelly_config_has_one_live_sampling_and_cost_contract():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["kellyPortfolio"]
    assert "expectedReturnShrinkagePrior" not in cfg
    assert "minEffectiveObservations" not in cfg
    assert "minNonOverlappingDates" not in cfg
    assert "costHaircut" not in cfg
    assert cfg["minEffectiveDates"] > 0 and cfg["minUniqueDates"] > 0
    assert cfg["activation"]["minPaperDays"] == 252
    assert cfg["currency"] == {
        "baseCurrency": "KRW", "fxReturnsIncluded": False, "fxHedged": False,
    }
    for region in ("KR", "US"):
        assert {"commissionBps", "sellTaxBps", "spreadBps", "assumedTurnoverPct",
                "rebalanceDays", "expectedTradeNotionalKrw"} <= set(cfg["transactionCosts"][region])


def test_every_kelly_config_key_is_connected_to_implementation_or_metadata():
    source = (ROOT / "pipeline" / "kelly_portfolio.py").read_text(encoding="utf-8")
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["kellyPortfolio"]
    ignored_structural = {"activation", "regimeMultipliers", "transactionCosts", "currency"}
    for key in set(cfg) - ignored_structural:
        assert key in source, f"unused Kelly config key: {key}"
