"""US alpha Phase 3: the candidate cash-profitability definition, the power planning figures, and the readiness/protocol files.

Pinned here:
  * a filing is visible only STRICTLY after max(availableFrom, acceptedDate) — same rule PR #224 verified;
  * TTM is the sealed `finnhub_derive` rollforward, never an annualisation, and a broken chain is a reason code, never zero;
  * a share count is never carried BACKWARD from a later filing, and a split between count and observation withholds size;
  * the power table reads only the variance side of the committed four-factor report;
  * the committed readiness report and protocol proposal stay outcome-blind and authorize nothing;
  * no Phase 3 module imports an outcome, label, model or production-decision module.
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import finnhub_fundamentals as FF                # noqa: E402
from pipeline import us_alpha_phase3_power as POWER            # noqa: E402
from pipeline import us_cash_profitability as CP               # noqa: E402

DAYS = {FF.Q1: 90, FF.Q2: 181, FF.Q3: 273, FF.FY: 365}
END = {FF.Q1: "03-31", FF.Q2: "06-30", FF.Q3: "09-30", FF.FY: "12-31"}


def filing(year, stage, *, ni=None, ocf=None, oi=None, assets=None, shares=None, available=None, accepted=None):
    def money(c, v):
        return [] if v is None else [{"concept": "us-gaap_" + c, "unit": "usd", "value": v, "label": c}]
    ic = money("NetIncomeLoss", ni) + money("OperatingIncomeLoss", oi)
    if shares is not None:
        ic.append({"concept": "us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding", "unit": "shares", "value": shares,
                   "label": "shares"})
    return {"id": "X-%d-%s" % (year, stage), "ticker": "X", "fiscalYear": year, "form": "10-K" if stage == FF.FY else "10-Q",
            "periodDays": DAYS[stage], "periodEnd": "%d-%s" % (year, END[stage]),
            "availableFrom": available or "%d-%s" % (year + (1 if stage == FF.FY else 0),
                                                       {FF.Q1: "05-10", FF.Q2: "08-10", FF.Q3: "11-10", FF.FY: "02-20"}[stage]),
            "acceptedDate": accepted, "source": "finnhub/financials-reported",
            "statements": {"ic": ic, "bs": money("Assets", assets), "cf": money("NetCashProvidedByUsedInOperatingActivities", ocf)}}


def chain():
    """FY2020 annual, Q1 2020 and Q1 2021: enough for a Q1 2021 rollforward."""
    return [filing(2020, FF.FY, ni=100.0, ocf=150.0, oi=130.0, assets=1000.0, shares=10.0),
            filing(2020, FF.Q1, ni=20.0, ocf=30.0, oi=25.0, assets=950.0, shares=10.0),
            filing(2021, FF.Q1, ni=30.0, ocf=50.0, oi=35.0, assets=1100.0, shares=11.0)]


def test_cash_profitability_is_the_sealed_rollforward_over_current_assets():
    out = CP.features_as_of(chain(), "2021-06-01")
    ocf_ttm = 150.0 - 30.0 + 50.0
    ni_ttm = 100.0 - 20.0 + 30.0
    assert out["cashOperatingProfitability"] == pytest.approx(ocf_ttm / 1100.0)
    assert out["accrualsToAssets"] == pytest.approx((ni_ttm - ocf_ttm) / 1100.0)
    assert out["operatingProfitabilityToAssets"] == pytest.approx((130.0 - 25.0 + 35.0) / 1100.0)
    assert out["reportEnd"] == "2021-03-31" and out["sharesForProxy"] == 11.0 and out["sharesBasis"] == CP.SHARES_AS_FILED


def test_visibility_is_strictly_after_the_later_of_available_and_accepted():
    records = chain()
    records[-1]["acceptedDate"] = "2021-05-20 16:00:00"          # accepted after availableFrom: the later date governs
    assert CP.features_as_of(records, "2021-05-20")["reportEnd"] == "2020-12-31"
    assert CP.features_as_of(records, "2021-05-21")["reportEnd"] == "2021-03-31"


def test_a_future_filing_cannot_change_an_earlier_reading():
    early = CP.features_as_of(chain(), "2021-04-01")
    later = chain() + [filing(2021, FF.Q2, ni=1e9, ocf=-1e9, oi=1e9, assets=1.0, shares=1.0)]
    assert CP.features_as_of(later, "2021-04-01") == early


def test_broken_chain_and_bad_denominators_are_reasons_never_zero():
    records = chain()[:1] + chain()[2:]                       # Q1 2020 missing: no rollforward
    out = CP.features_as_of(records, "2021-06-01")
    assert out["cashOperatingProfitability"] is None and out["state"]["cashOperatingProfitability"] == CP.OCF_TTM_INCOMPLETE
    assert out["state"]["accrualsToAssets"] == CP.OCF_TTM_INCOMPLETE
    neg = chain()
    neg[-1]["statements"]["bs"][0]["value"] = -5.0
    out = CP.features_as_of(neg, "2021-06-01")
    assert out["cashOperatingProfitability"] is None and out["state"]["cashOperatingProfitability"] == CP.ASSETS_NON_POSITIVE
    assert CP.features_as_of([], "2021-06-01")["state"]["cashOperatingProfitability"] == CP.NO_VISIBLE_FILING


def test_stale_report_withholds_every_feature():
    out = CP.features_as_of(chain(), "2021-12-31")              # Q1 2021 ended 275 days earlier
    assert out["cashOperatingProfitability"] is None
    assert set(out["state"].values()) == {CP.REPORT_STALE}


def test_share_count_is_carried_forward_only_from_an_earlier_filing():
    records = chain()
    records[-1]["statements"]["ic"] = [e for e in records[-1]["statements"]["ic"] if "Shares" not in e["concept"]]
    out = CP.features_as_of(records, "2021-06-01")
    assert out["sharesForProxy"] == 10.0 and out["sharesBasis"] == CP.SHARES_CARRIED_FORWARD
    only_later = [filing(2021, FF.Q1, ni=1.0, ocf=1.0, oi=1.0, assets=10.0),
                  filing(2021, FF.Q2, ni=1.0, ocf=1.0, oi=1.0, assets=10.0, shares=99.0)]
    out = CP.features_as_of(only_later, "2021-06-01")       # Q2 is not yet visible, and could never be used backward
    assert out["sharesForProxy"] is None and out["state"]["sharesForProxy"] == CP.SHARES_NOT_STATED


def test_market_cap_proxy_withholds_across_a_split():
    assert CP.market_cap_proxy(10.0, 5.0, "2021-05-11", "2021-06-01") == (50.0, CP.AVAILABLE)
    assert CP.market_cap_proxy(10.0, 5.0, "2021-05-11", "2021-06-01", ["2021-05-20"]) == (None, CP.SPLIT_BETWEEN)
    assert CP.market_cap_proxy(None, 5.0, "2021-05-11", "2021-06-01")[1] == CP.SHARES_NOT_STATED
    assert CP.market_cap_proxy(10.0, float("nan"), "2021-05-11", "2021-06-01")[1] == CP.NO_PRICE


# --------------------------------------------------------------------------- #
# Power planning reads variance only
# --------------------------------------------------------------------------- #
def test_power_table_scales_with_the_square_root_of_time_and_ignores_the_mean():
    report = json.loads(POWER.REPORT.read_text())
    base = POWER.planning_table(report)
    flipped = json.loads(json.dumps(report))
    for table in [flipped["primaryTable"], *flipped["secondaryHorizonTables"].values()]:
        for sleeve in POWER.SLEEVES:
            us = table[sleeve]["byRegion"]["US"]
            us["mean"] = -us["mean"]
            lo, hi = us["ci95"]
            us["ci95"] = [-hi, -lo]                              # same width, opposite sign
    assert POWER.planning_table(flipped) == base
    h = base["byHorizonSessions"]["126"]["minimumDetectableMeanIc"]
    assert h["3y"] / h["5y"] == pytest.approx((5 / 3) ** 0.5, rel=1e-2)
    assert base["byHorizonSessions"]["126"]["minimumDetectableMeanIc"]["5y"] > \
        base["independenceBasedPhase2ForComparison"]["330 names, 12 H126 windows (6 years)"]


# --------------------------------------------------------------------------- #
# Committed outputs
# --------------------------------------------------------------------------- #
READINESS = ROOT / "docs/us-readiness/us-alpha-phase3-readiness-v1.json"
PROTOCOL = ROOT / "docs/us-readiness/us-cash-profitability-study-protocol-v1.json"


def test_committed_readiness_is_outcome_blind_and_carries_the_power_table():
    report = json.loads(READINESS.read_text())
    assert report["readsReturns"] is False and report["readsLabels"] is False and report["forwardPricesRead"] is False
    assert report["fitsModels"] is False and report["featureStatus"] == "CANDIDATE_NOT_REGISTERED"
    assert report["powerPlanning"] == POWER.planning_table()
    assert report["sampling"]["dates"] == 55


def test_protocol_proposal_authorizes_nothing_and_matches_the_feature_contract():
    proposal = json.loads(PROTOCOL.read_text())
    assert proposal["status"] == "PROPOSED_NOT_REGISTERED" and proposal["authorizes"] == "NOTHING"
    assert proposal["registered"] is False and proposal["promotionEligible"] is False and proposal["productionEffect"] == "NONE"
    assert proposal["features"]["contract"] == CP.CONTRACT
    assert proposal["primaryClaim"]["horizonSessions"] == 63 and len([proposal["primaryClaim"]]) == 1


def test_phase3_code_imports_no_outcome_label_model_or_production_decision_module():
    forbidden = ("outcome", "label", "replay_valuation", "kelly_portfolio", "weekly_publish", "current_champion",
                 "historical_outcomes", "portfolio_validation", "selection_null", "us_capital_allocation_evaluation")
    for relative in ("pipeline/us_cash_profitability.py", "pipeline/us_alpha_phase3_power.py",
                     "scripts/audit_us_alpha_phase3_readiness.py"):
        tree = ast.parse((ROOT / relative).read_text())
        names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        names += [(n.module or "") + "." + a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names]
        assert not [n for n in names if any(f in n for f in forbidden)], relative


def test_protected_files_are_untouched():
    """Files this task must not modify keep the bytes they had on main 8a1256f."""
    pinned = {"pipeline/us_capital_allocation_policy.py": "65a5dbe33f0f09bd618ac988e0c690f6c75afb44bf29101efe0579697dc75046"}
    for relative, digest in pinned.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
