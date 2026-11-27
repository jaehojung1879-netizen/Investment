"""Regression checks: do not convert statements or balance levels into predictions."""
import json

import pytest

from research.narrative_intelligence import investor_mechanisms as im


def fixture():
    return json.loads(im.PILOT.read_text(encoding="utf-8"))


def test_pilot():
    result = im.diagnostics(fixture())
    assert result["sources"] == 8
    assert result["claims"] == 14
    assert [r["net_equity_sales"] for r in result["flows"]] == [-34266, 24169, 134122]
    assert [r["gross_cash_plus_tbill"] for r in result["balances"]] == [163887, 330805]
    assert result["forecast_scoreable_claims"] == 0
    assert not result["motive_identified"]


def test_no_horizon_invented():
    data = fixture()
    data["claims"][0]["forecast_horizon"] = "6 months"
    with pytest.raises(ValueError, match="UNADMITTED_FORECAST"):
        im.diagnostics(data)


def test_source_attribution():
    data = fixture()
    data["claims"][0]["actor"] = "Oaktree portfolio"
    with pytest.raises(ValueError, match="ATTRIBUTION"):
        im.diagnostics(data)


def test_no_scope_mix():
    data = fixture()
    data["behavior"]["balance_scope"] = "FULL_PORTFOLIO_WEIGHT"
    with pytest.raises(ValueError, match="BEHAVIOR_SCOPE"):
        im.diagnostics(data)


def test_same_author_not_same_asset():
    data = fixture()
    data["claims"][3]["asset"] = "CREDIT"
    with pytest.raises(ValueError, match="NOT_COMPARABLE"):
        im.diagnostics(data)


def test_no_lookahead_behavior():
    data = fixture()
    data["behavior"]["flows"][0]["year"] = 2025
    with pytest.raises(ValueError, match="YEAR_OR_DUPLICATE"):
        im.diagnostics(data)
