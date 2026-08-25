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
    probability = cfg["probabilityCalibration"]
    assert probability["requiredForKelly"] is True
    assert 0 < probability["selectionFraction"] < 1
    assert probability["minAuditDates"] > probability["minConditionDates"]
    assert probability["maxBrier"] <= 0.255 and probability["maxEce"] <= 0.10
    assert probability["integrity"] == {
        "minPitCoverage": 0.60,
        "requireHistoricalUniverse": True,
        "requirePointInTimeFundamentals": True,
        "requireVintageMacroForConditionalProbability": True,
    }


def test_every_kelly_config_key_is_connected_to_implementation_or_metadata():
    # The kellyPortfolio block is read by the live sizer and by the historical
    # validation that replays it, so both count as "connected". The point of the
    # check is that no key is dead, not that one file owns them all.
    source = "".join(
        (ROOT / "pipeline" / name).read_text(encoding="utf-8")
        for name in ("kelly_portfolio.py", "portfolio_validation.py"))
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["kellyPortfolio"]
    ignored_structural = {"activation", "regimeMultipliers", "transactionCosts", "currency"}
    for key in set(cfg) - ignored_structural:
        if key.startswith("_"):
            continue                      # documentation, as the test name allows
        assert key in source, f"unused Kelly config key: {key}"
    for key in cfg["selection"]:
        assert key in source, f"unused selection config key: {key}"


def test_portfolio_is_configured_to_concentrate_not_to_mirror_the_candidate_list():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    kelly, longterm = cfg["kellyPortfolio"], cfg["longterm"]
    selection = kelly["selection"]
    assert 3 <= selection["targetNames"] <= 5
    assert selection["minNames"] <= selection["targetNames"]
    assert kelly["maxNames"] <= longterm["maxNames"], "the book must be narrower than the research sleeve"
    # A 5-name book under a 10% name cap could never be fully invested; the
    # caps have to be sized for the concentration that is actually intended.
    assert kelly["maxPositionWeight"] * selection["targetNames"] >= 1.0 - kelly["minCashPct"] / 100
    assert kelly["maxSectorWeight"] >= kelly["maxPositionWeight"]
    assert selection["maxNamesPerSector"] < selection["targetNames"]
