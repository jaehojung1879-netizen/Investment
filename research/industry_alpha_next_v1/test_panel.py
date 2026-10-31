"""Panel assembly invariants on invented securities only."""
import numpy as np
import pandas as pd
import pytest

from pipeline import kr_industry_anatomy as I
from pipeline import kr_industry_anatomy_execution as IE
from pipeline import replay_calendar as RC
from research.industry_alpha_next_v1 import panel as P
from research.industry_alpha_next_v1 import study as S

DAYS = RC.sessions("2013-01-01", "2016-12-31", "KR")
DATE = "2015-06-30"


def syn_prices(seed=0, tickers=None):
    rng = np.random.default_rng(seed)
    tickers = tickers or [f"{i:06d}.KS" for i in range(12)] + [S.BENCHMARK]
    out = {}
    for t in tickers:
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(DAYS))))
        out[t] = pd.DataFrame({"Close": close, "Volume": 1000.0}, index=DAYS)
    return out


def cohort_for(members, caps):
    membership = pd.DataFrame({"date": DATE, "ticker": members, "industry": "G", "membershipStatus": "CURRENT_KRX_KIND_ANCHOR"})
    capframe = pd.DataFrame({"date": DATE, "ticker": members, "marketCap": caps})
    return I.build_cohorts(membership, capframe)[(DATE, "G")]


def test_minimum_members_is_the_sealed_anatomy_value():
    assert S.MIN_MEMBERS == I.MIN_MEMBERS and S.MIN_INDUSTRIES_PER_DATE == I.MIN_CROSS_SECTION


def test_monthly_signal_is_the_last_weekly_date_of_each_month():
    weekly = {"2015-01-02": ["a"], "2015-01-30": ["b"], "2015-02-06": ["c"], "2015-02-27": ["d"]}
    assert P.monthly_signals(weekly) == {"2015-01-30": ["b"], "2015-02-27": ["d"]}


def test_leaders_are_the_signal_date_cap_top_fifth_and_both_sides_need_two():
    members = [f"{i:06d}.KS" for i in range(10)]
    leaders, laggards = P.leader_split(cohort_for(members, [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]))
    assert leaders == ["000000.KS", "000001.KS"] and len(laggards) == 8
    assert P.leader_split(cohort_for(members[:5], [5, 4, 3, 2, 1])) is None   # ceil(1.0) = 1 leader < 2
    missing = cohort_for(members, [10, 9, 8, 7, 6, 5, 4, 3, 2, np.nan])
    assert missing["capWeights"] is None and P.leader_split(missing) is None


def test_features_are_invariant_to_any_price_after_the_signal():
    prices = syn_prices()
    names = [f"{i:06d}.KS" for i in range(12)]
    cohort = cohort_for(names, list(range(12, 0, -1)))
    a = P.diffusion_features(cohort, IE.past_features(prices, names, DAYS, DATE))[0]
    poisoned = {t: f.copy() for t, f in prices.items()}
    for f in poisoned.values():
        f.loc[f.index > pd.Timestamp(DATE), "Close"] *= 50.0
    b = P.diffusion_features(cohort, IE.past_features(poisoned, names, DAYS, DATE))[0]
    assert a == pytest.approx(b, nan_ok=True) and np.isfinite(a["LEADER_GAP_63"])


def test_a_missing_trailing_value_is_missing_not_zero():
    names = [f"{i:06d}.KS" for i in range(10)]
    cohort = cohort_for(names, list(range(10, 0, -1)))
    past = {t: {"trail63": 0.1, "trail126": 0.1, "aboveMA126": 1.0, "bench126": 0.0} for t in names}
    past[names[-1]]["trail63"] = np.nan
    out, _ = P.diffusion_features(cohort, past)
    assert np.isnan(out["LEADER_GAP_63"]) and np.isfinite(out["LAGGARD_MOM_126"])


def test_market_context_reads_only_the_closes_it_is_given():
    close = np.linspace(100, 120, 253)
    m = P.market_context(close)
    assert m["MKT_RET_126"] == pytest.approx(close[-1] / close[-127] - 1) and m["MKT_ABOVE_SMA200"] == 1.0
    assert np.isnan(P.market_context(close[:50])["MKT_RET_126"])


def test_targets_need_a_permit_and_never_renormalise_the_laggard_basket():
    names = [f"{i:06d}.KS" for i in range(10)]
    cohort = cohort_for(names, list(range(10, 0, -1)))
    cohorts = {(DATE, "G"): cohort}
    splits = {(DATE, "G"): {"leaders": names[:2], "laggards": names[2:]}}
    fwd = {(DATE, 126): {t: (0.1, 0.02, "MATURED") for t in names}}
    with pytest.raises(PermissionError):
        P.industry_and_laggard_targets(cohorts, splits, fwd, 126, None)
    ok = P.industry_and_laggard_targets(cohorts, splits, fwd, 126, P.synthetic_permit())
    assert ok.laggardRelative.iloc[0] == pytest.approx(0.08) and ok.cwRelative.iloc[0] == pytest.approx(0.08)
    fwd[(DATE, 126)][names[-1]] = (np.nan, 0.02, "UNRESOLVED_TERMINAL_OR_DISTRIBUTION_EVIDENCE")
    bad = P.industry_and_laggard_targets(cohorts, splits, fwd, 126, P.synthetic_permit())
    assert bad.laggardRelative.iloc[0] is None and bad.cwRelative.iloc[0] is None
    assert bad.laggardStatus.iloc[0].startswith("UNRESOLVED") and bad.cwStatus.iloc[0].startswith("UNRESOLVED")


def test_exposure_audit_counts_who_the_classified_cohorts_leave_out():
    membership = pd.DataFrame({"date": DATE, "ticker": ["a", "b", "c", "d"],
                               "industry": ["G", None, "G", None], "membershipStatus": "x"})
    caps = {(DATE, "a"): 1.0, (DATE, "b"): 3.0, (DATE, "c"): 1.0, (DATE, "d"): 5.0}
    row = P.exposure_audit(membership, caps, terminal={"d"}).iloc[0]
    assert row.unclassified == 2 and row.unclassifiedCapShare == pytest.approx(0.8)
    assert row.terminalLater == 1 and row.terminalLaterClassified == 0 and row.terminalLaterCapShare == pytest.approx(0.5)
    assert row.eligibleIndustries == 0      # 2 classified members < MIN_MEMBERS


def test_intended_blocks_hold_only_eligible_cohorts():
    names = [f"{i:06d}.KS" for i in range(6)]
    blocks = P.intended_blocks({(DATE, "G"): cohort_for(names, [1] * 6), (DATE, "H"): {"status": "INELIGIBLE", "members": ["x"]}})
    assert list(blocks) == [f"{DATE}|G"] and blocks[f"{DATE}|G"] == tuple(names)
