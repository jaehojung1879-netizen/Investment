"""kr-alpha-atlas Phase B: the bars layer, the point-in-time matrix, the readiness arithmetic and the weekly dry run, on SYNTHETIC inputs.

A passing test here proves the code does what it says on invented data. It does not prove any real dataset is ready: that is `docs/results/kr-alpha-atlas-phase-b-readiness.json`,
produced by a real run and checked for consistency (not recomputed) in the last tests of this file.
"""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_alpha_atlas_bars as B
from pipeline import kr_alpha_atlas_catalogue as C
from pipeline import kr_alpha_atlas_dry_run as DR
from pipeline import kr_alpha_atlas_inputs as AI
from pipeline import kr_alpha_atlas_matrix as M
from pipeline import kr_alpha_atlas_readiness as RD
from pipeline import kr_alpha_atlas_registry as AR
from pipeline import kr_alpha_atlas_report as RP
from pipeline import kr_alpha_tournament_features as TF
from pipeline import liquidity_attention as LA
from pipeline import regional_alpha_features as RAF
from pipeline import replay_calendar as RC

ROOT = Path(__file__).resolve().parents[1]
CAL = RC.sessions("2013-01-01", "2028-12-31", "KR")
REGISTRY = AR.load()


# --------------------------------------------------------------------------- #
# synthetic bars
# --------------------------------------------------------------------------- #
def make_rows(seed=1, n=420, start="2019-01-02", shares=1e7, split_at=None, split_ratio=5, share_lag=0, suspend=(), unexplained_at=None):
    """As-traded KRX-style bars for one ticker on consecutive KR sessions."""
    rng = np.random.RandomState(seed)
    days = CAL[CAL >= pd.Timestamp(start)][:n]
    price, close = 10000.0, []
    for i in range(n):
        price *= math.exp(rng.normal(0, 0.012))
        close.append(price)
    out = []
    for i, d in enumerate(days):
        c = close[i]
        vol = float(np.exp(rng.normal(11.5, 0.3)))
        sh = shares
        if split_at is not None and i >= split_at:
            c, vol = c / split_ratio, vol * split_ratio
        if split_at is not None and i >= split_at + share_lag:
            sh = shares * split_ratio
        if unexplained_at is not None and i >= unexplained_at:
            c = c * 2.6
        high, low = c * 1.01, c * 0.99
        if i in suspend:
            out.append({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 0.0, "ListedShares": sh, "Date": d})
        else:
            out.append({"Open": c, "High": high, "Low": low, "Close": c, "Volume": vol, "ListedShares": sh, "Date": d})
    return pd.DataFrame(out).set_index("Date")


def bars_of(frame, ticker="X.KS"):
    return B.TickerBars(ticker, frame, CAL)


def same(a, b, tol=1e-9):
    return a == pytest.approx(b, rel=tol, abs=tol)


# --------------------------------------------------------------------------- #
# bars layer
# --------------------------------------------------------------------------- #
def test_every_catalogued_feature_is_registered_and_names_an_existing_function():
    import importlib
    ids = {f["featureId"] for f in REGISTRY["features"]}
    assert set(C.CATALOGUE) <= ids
    for fid, spec in C.CATALOGUE.items():
        for ref in spec["reuses"]:
            module, _, name = ref.rpartition(".")
            assert hasattr(importlib.import_module("pipeline." + module), name), (fid, ref)


def test_features_do_not_depend_on_anything_after_the_signal_session():
    frame = make_rows(seed=3, n=400)
    full = bars_of(frame)
    for k in (130, 220, 330):
        date = frame.index[k]
        cut = bars_of(frame.iloc[:k + 1])
        a, ra = full.features_at(date)
        b, rb = cut.features_at(date)
        assert a.keys() == b.keys() and ra == rb
        for f in a:
            assert same(a[f], b[f]), f


def test_a_confirmed_split_does_not_manufacture_a_volume_or_liquidity_shock():
    control = bars_of(make_rows(seed=4, n=420))
    split = bars_of(make_rows(seed=4, n=420, split_at=200, split_ratio=5))
    assert [e["ratio"] for e in split.events] == [5.0] and split.events[0]["confirmedOn"] == split.events[0]["date"]
    for k in (203, 240, 300, 380):                 # windows that straddle the split, and windows entirely after it
        date = control.span[k]
        a, _ = control.features_at(date)
        b, rb = split.features_at(date)
        for f in a:
            assert f in b, (k, f, rb.get(f))
            assert same(a[f], b[f], 1e-7), (k, f)


def test_a_split_confirmed_only_by_a_late_share_update_is_masked_not_adjusted_with_later_knowledge():
    lagged = bars_of(make_rows(seed=4, n=420, split_at=200, split_ratio=5, share_lag=25))
    event = lagged.events[0]
    assert event["confirmedOn"] > event["date"]
    early = lagged.span[210]                       # price move known, share count not yet moved
    values, reasons = lagged.features_at(early)
    assert "D02_logVolumeShock60" not in values and reasons["D02_logVolumeShock60"] == "UNCONFIRMED_CORPORATE_ACTION_IN_WINDOW"
    after = lagged.span[lagged.span.get_loc(event["confirmedOn"]) + 5]
    v2, r2 = lagged.features_at(after)
    control, _ = bars_of(make_rows(seed=4, n=420)).features_at(after)
    assert same(v2["D02_logVolumeShock60"], control["D02_logVolumeShock60"], 1e-7)
    assert r2["D05_turnoverToMarketCap60"] == "STALE_SHARE_COUNT_IN_WINDOW"   # the stale-share sessions are still inside the 60-session turnover window


def test_a_price_move_no_split_ratio_explains_is_missing_not_filled():
    bars = bars_of(make_rows(seed=5, n=420, unexplained_at=250))
    values, reasons = bars.features_at(bars.span[260])
    assert reasons["E01_amihudIlliquidity60"] == "UNEXPLAINED_PRICE_MOVE_IN_WINDOW" and "E01_amihudIlliquidity60" not in values


def test_a_suspension_is_not_a_session_and_is_never_filled():
    bars = bars_of(make_rows(seed=6, n=300, suspend=(150, 151, 152)))
    date = bars.span[160]
    values, reasons = bars.features_at(date)
    assert reasons["D02_logVolumeShock60"] == "GAP_OR_SUSPENSION_IN_WINDOW" and reasons["E01_amihudIlliquidity60"] == "GAP_OR_SUSPENSION_IN_WINDOW"
    assert values["E07_suspensionStaleRisk"] == 3.0 and values["E04_tradabilityGuard20"] == 17.0
    later, _ = bars.features_at(bars.span[150 + 62])
    assert "D02_logVolumeShock60" in later                       # 60 clean sessions after the halt
    assert bars.quote(bars.span[151]) is None                    # a halted session has no quote, not a carried one


def test_volume_traded_value_and_turnover_are_three_different_quantities():
    base = make_rows(seed=7, n=300)
    doubled_shares, doubled_volume = base.copy(), base.copy()
    doubled_shares["ListedShares"] *= 2
    doubled_volume["Volume"] *= 2
    a, b, c = (bars_of(f).features_at(base.index[250])[0] for f in (base, doubled_shares, doubled_volume))
    assert same(b["D05_turnoverToMarketCap60"], a["D05_turnoverToMarketCap60"] / 2)      # turnover is volume over shares
    assert same(b["E03_capacityMedianTradedValue60"], a["E03_capacityMedianTradedValue60"])  # traded value ignores the share count
    assert same(c["E03_capacityMedianTradedValue60"], 2 * a["E03_capacityMedianTradedValue60"])
    assert same(c["D02_logVolumeShock60"], a["D02_logVolumeShock60"])                        # a shock is a ratio: a constant volume scale cancels
    assert c["D05_turnoverToMarketCap60"] == pytest.approx(2 * a["D05_turnoverToMarketCap60"])


def test_the_vectorised_features_equal_the_sealed_and_production_functions():
    frame = make_rows(seed=8, n=300)
    bars = bars_of(frame)
    k = 250
    date = frame.index[k]
    values, _ = bars.features_at(date)
    close = frame["Close"].to_numpy(float)
    tv = (frame["Close"] * frame["Volume"]).to_numpy(float)
    assert same(values["E01_amihudIlliquidity60"], TF.amihud(close[k - 60:k + 1], tv[k - 59:k + 1]))
    trailing = [{"volume": float(frame["Volume"].iloc[i]), "tradingValue": float(tv[i])} for i in range(k - 59, k + 1)]
    sealed = TF.liquidity_features(trailing, 1e12)["logVolumeShock5_60"]
    assert same(values["D03_tradingValueShock5_60"], sealed)
    assert same(values["D01_volumeSurge5_60"], float(LA.volume_ratio(frame["Volume"], 5, 60).iloc[k]))
    assert same(values["D02_logVolumeShock60"], float(LA.log_volume_shock(frame["Volume"], 60).iloc[k]))


def test_corwin_schultz_matches_the_published_formula_and_is_never_negative():
    high, low = pd.Series([102.0, 103.0]), pd.Series([100.0, 101.0])
    beta = math.log(102 / 100) ** 2 + math.log(103 / 101) ** 2
    gamma = math.log(103 / 100) ** 2
    k = 3 - 2 * math.sqrt(2)
    alpha = (math.sqrt(2 * beta) - math.sqrt(beta)) / k - math.sqrt(gamma / k)
    expected = max(0.0, 2 * (math.exp(alpha) - 1) / (1 + math.exp(alpha)))
    assert same(float(B.corwin_schultz(high, low, 1).iloc[1]), expected)
    flat = B.corwin_schultz(pd.Series([100.0] * 30), pd.Series([100.0] * 30), 20)
    assert (flat.dropna() == 0.0).all()


# --------------------------------------------------------------------------- #
# a synthetic world for the matrix
# --------------------------------------------------------------------------- #
LABELS = {"A": "1차철강제조업", "B": "가전제품및정보통신장비소매업"}
CROSSWALK = {"mapping": {"1차철강제조업": "BASIC_MATERIALS", "가전제품및정보통신장비소매업": "CONSUMER_RETAIL_SERVICES"}}
SIGNAL = "2020-12-18"
SNAPSHOT = "2020-12-01"


def filing(ticker, year, code, available, scale):
    cum = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}[code]
    amt = lambda v: {"amounts": {"thstrm_amount": v, "thstrm_add_amount": v}}  # noqa: E731
    def flow(v, st):
        if code == "11011" or st == "CF":
            return {"statement": st, "amounts": {"thstrm_amount": v}}      # annual, and every cash-flow report, state ONE column: the period's cumulative figure
        return {"statement": st, "amounts": {"thstrm_amount": v / cum, "thstrm_add_amount": v}}
    return {"id": f"{ticker}:{year}:{code}", "ticker": ticker, "fiscalYear": year, "reportCode": code, "availableFrom": available,
            "receiptNos": [available.replace("-", "") + "001"], "fsDiv": "CFS", "currency": "KRW",
            "accounts": {"자산총계": dict(amt(1000.0 * scale), statement="BS"), "부채총계": dict(amt(400.0 * scale), statement="BS"), "자본총계": dict(amt(600.0 * scale), statement="BS"),
                         "당기순이익": flow(60.0 * scale * cum / 4, "CIS"), "매출액": flow(500.0 * scale * cum / 4, "CIS"), "영업이익": flow(90.0 * scale * cum / 4, "CIS"),
                         "영업활동현금흐름": flow(80.0 * scale * cum / 4, "CF"), "유형자산의취득": flow(30.0 * scale * cum / 4, "CF")}}


def make_world(extra=None):
    tickers = ["T%02d.KS" % i for i in range(1, 13)]
    days = CAL[CAL >= pd.Timestamp("2019-01-02")][:520]
    rng = np.random.RandomState(11)
    prices, bars, accounting, shares, intervals = {}, {}, {}, {}, {}
    bench_close = 100000.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.008, len(days))))
    prices["069500.KS"] = pd.DataFrame({"Close": bench_close}, index=days)
    for i, t in enumerate(tickers):
        rows = make_rows(seed=20 + i, n=520, start="2019-01-02", shares=1e7 * (1 + i))
        bars[t] = B.TickerBars(t, rows, CAL)
        prices[t] = pd.DataFrame({"Close": rows["Close"].to_numpy(float)}, index=days)
        scale = 1.0 + i / 3
        accounting[t] = [filing(t, 2018, "11011", "2019-03-20", scale), filing(t, 2018, "11013", "2018-05-15", scale), filing(t, 2019, "11013", "2019-05-15", scale),
                         filing(t, 2019, "11011", "2020-03-20", scale), filing(t, 2020, "11013", "2020-05-15", scale), filing(t, 2020, "11012", "2020-08-14", scale),
                         filing(t, 2018, "11012", "2018-08-14", scale), filing(t, 2019, "11012", "2019-08-14", scale)]
        shares[t] = {(2018, "11011"): 1e7 * (1 + i), (2019, "11011"): 1e7 * (1 + i) * 1.01, (2019, "11012"): 1e7 * (1 + i) * 1.01, (2020, "11012"): 1e7 * (1 + i) * 1.03,
                     (2018, "11012"): 1e7 * (1 + i), (2020, "11013"): 1e7 * (1 + i) * 1.02, (2019, "11013"): 1e7 * (1 + i) * 1.0}
        intervals[t] = [{"start": None, "end": None, "label": LABELS["A" if i < 6 else "B"], "reconstruction_status": "CURRENT_KRX_KIND_ANCHOR", "status": "ANCHOR"}]
    world = dict(accounting=accounting, shares=shares, prices=prices, bars=bars, industry=(intervals, CROSSWALK, {}), calendar=CAL,
                 names={t: "회사%d" % i for i, t in enumerate(tickers)}, identity={"sha256": "0" * 64},
                 memberships=RAF.MembershipSnapshots([{"date": SNAPSHOT, "members": tickers}]), universe_rows={})
    world.update(extra or {})
    return AI.MatrixInputs(**world)


@pytest.fixture(scope="module")
def world():
    return make_world()


@pytest.fixture(scope="module")
def matrix(world):
    return M.build_matrix(world, [SIGNAL], {})


def cell(matrix, ticker, feature):
    i = matrix.rows.index[(matrix.rows.ticker == ticker) & (matrix.rows.date == SIGNAL)][0]
    return matrix.values.at[i, feature], matrix.reasons.at[i, feature]


def test_the_matrix_has_one_row_per_pit_member_and_every_missing_cell_has_a_reason(matrix):
    assert len(matrix.rows) == 12 and matrix.rows.pitSnapshotDate.eq(SNAPSHOT).all()
    assert set(matrix.values.columns) == set(C.CATALOGUE)
    missing = matrix.values.isna() & matrix.reasons.eq("")
    assert not missing.any().any() and not matrix.reasons.eq("REASON_NOT_RECORDED").any().any()
    assert set(matrix.reasons.stack().unique()) - {""} <= set(M.REASONS)


def test_the_reason_audit_passes_on_a_built_matrix_and_catches_a_hole(matrix):
    assert RD.reason_checks(matrix)["pass"]
    hole = M.Matrix(matrix.rows, matrix.values.copy(), matrix.reasons.copy(), matrix.available, matrix.date_context, matrix.identity)
    hole.values.iloc[0, 0] = float("nan")
    hole.reasons.iloc[0, 0] = ""
    assert not RD.reason_checks(hole)["pass"]


def test_the_matrix_is_deterministic_and_independent_of_row_order(world, matrix):
    again = M.build_matrix(world, [SIGNAL], {})
    assert again.digest() == matrix.digest()
    reversed_world = make_world()
    reversed_world.memberships = RAF.MembershipSnapshots([{"date": SNAPSHOT, "members": sorted(world.memberships.snapshots[0]["members"], reverse=True)}])
    assert M.build_matrix(reversed_world, [SIGNAL], {}).digest() == matrix.digest()


def test_a_value_computed_from_the_full_inputs_equals_the_one_computed_after_deleting_the_future(world, matrix):
    cut = pd.Timestamp(SIGNAL)
    truncated = make_world()
    truncated.prices = {t: f[f.index <= cut] for t, f in world.prices.items()}
    truncated.bars = {t: B.TickerBars(t, _bars_frame(b, cut), CAL) for t, b in world.bars.items()}
    truncated.accounting = {t: [r for r in rows if r["availableFrom"] <= SIGNAL] for t, rows in world.accounting.items()}
    other = M.build_matrix(truncated, [SIGNAL], {})
    assert other.digest() == matrix.digest()


def _bars_frame(bars, cut):
    frame = bars.asts.copy()
    frame.columns = ["Close", "Volume", "ListedShares"]
    frame["Open"], frame["High"], frame["Low"] = frame["Close"], frame["Close"] * 1.01, frame["Close"] * 0.99
    return frame[frame.index <= cut].dropna(subset=["Close"])


def test_a_filing_becomes_visible_the_day_after_its_receipt_not_on_it():
    inputs = make_world()
    for r in inputs.accounting["T01.KS"]:
        if r["id"] == "T01.KS:2020:11012":
            r["availableFrom"] = SIGNAL
            r["receiptNos"] = [SIGNAL.replace("-", "") + "001"]
    same_day = M.build_matrix(inputs, [SIGNAL], {})
    v, _ = cell(same_day, "T01.KS", "C03_operatingMargin")
    j = same_day.available.at[same_day.rows.index[same_day.rows.ticker == "T01.KS"][0], "C03_operatingMargin"]
    assert j == "2020-05-15"                      # the half-year filing dated on the signal date is NOT used; the Q1 filing is
    assert not math.isnan(v)


def test_filing_based_cells_are_never_available_on_or_after_the_signal_date(matrix):
    assert RD.pit_checks(matrix)["pass"]
    broken = M.Matrix(matrix.rows.copy(), matrix.values, matrix.reasons, matrix.available.copy(), matrix.date_context, matrix.identity)
    broken.available.iloc[0, 0] = SIGNAL
    assert not RD.pit_checks(broken)["pass"]


def test_industry_membership_follows_the_dated_interval_not_todays_label():
    inputs = make_world()
    ivs = inputs.industry[0]["T01.KS"]
    ivs[0].update(end="2020-12-10")
    ivs.append({"start": "2020-12-10", "end": None, "label": LABELS["B"], "reconstruction_status": "CURRENT_KRX_KIND_ANCHOR", "status": "ANCHOR"})
    m = M.build_matrix(inputs, [SIGNAL], {})
    row = m.rows[m.rows.ticker == "T01.KS"].iloc[0]
    assert row.industry == "CONSUMER_RETAIL_SERVICES"
    earlier = M.build_matrix(inputs, ["2020-12-04"], {})
    assert earlier.rows[earlier.rows.ticker == "T01.KS"].iloc[0].industry == "BASIC_MATERIALS"


def test_the_cost_capacity_and_eligibility_columns_are_not_alpha_candidates():
    roles = {f["featureId"]: f["role"] for f in REGISTRY["features"]}
    for fid in ("E03_capacityMedianTradedValue60", "E04_tradabilityGuard20", "E05_highLowSpreadProxy", "E07_suspensionStaleRisk", "F05_maxDrawdown252"):
        assert roles[fid] != "ALPHA_CANDIDATE"
    report = RD.build_features_report(_synthetic_matrix(), REGISTRY, "2026-09-14")
    eligible = [r["featureId"] for r in report.values() if r["measuredStatus"] == "MEASURED_READY" and r["role"] == "ALPHA_CANDIDATE"]
    assert not set(eligible) & {"E03_capacityMedianTradedValue60", "E04_tradabilityGuard20", "E05_highLowSpreadProxy", "E07_suspensionStaleRisk", "F05_maxDrawdown252"}


def test_blocked_and_unsafe_features_are_never_columns_and_stay_blocked():
    registry = {f["featureId"]: f for f in REGISTRY["features"]}
    for fid, f in registry.items():
        if f["readinessStatus"] in ("SOURCE_BLOCKED", "PIT_UNSAFE", "NOT_FEASIBLE"):
            assert fid not in C.CATALOGUE, fid
    report = RD.build_features_report(_synthetic_matrix(), REGISTRY, "2026-09-14")
    assert report["G01_foreignNetBuying"]["measuredStatus"] == "NOT_COMPUTED_SOURCE_BLOCKED"
    assert report["I03_krTermSpread"]["measuredStatus"] == "NOT_COMPUTED_PIT_UNSAFE"
    assert report["J06_searchAttention"]["measuredStatus"] == "NOT_COMPUTED_NOT_FEASIBLE"
    assert report["F08_bookConcentration"]["measuredStatus"] == "NOT_A_MATRIX_COLUMN"
    assert report["D11_accumulationDistributionProxy"]["family"] == "D"          # the OHLCV proxy stays in the volume family, never investor flow


# --------------------------------------------------------------------------- #
# readiness arithmetic
# --------------------------------------------------------------------------- #
def _synthetic_matrix(n_dates=80, n_names=60, coverage=None, seed=0):
    """A hand-built matrix: `coverage[feature]` is the share of cells measured; everything not named is fully measured."""
    rng = np.random.RandomState(seed)
    days = [str(d.date()) for d in CAL[(CAL >= "2018-01-02") & (CAL <= "2020-12-31")]][::5][:n_dates]
    rows = pd.DataFrame([{"date": d, "ticker": "N%02d.KS" % j, "pitSnapshotDate": "2017-12-01", "industry": "IND%d" % (j % 6), "industryMembershipStatus": "OK",
                          "industryEligible": True, "liquidityTier": ("LOW", "MID", "HIGH")[j % 3], "isPreferredShare": False, "tradableAtSignal": True,
                          "b08State": "NOT_CHEAP", "b08Confirmed": float(j % 2), "filingAvailableFrom": "2017-11-01"} for d in days for j in range(n_names)])
    values = pd.DataFrame({f: rng.normal(size=len(rows)) for f in C.CATALOGUE})
    values["I01_kospiTrendVolState"] = np.where(rows.date.str[:7] < "2019-06", 1.0, 0.7)
    values["J05_shortSellingRegime"] = 0.0
    reasons = pd.DataFrame("", index=rows.index, columns=values.columns)
    for f, share in (coverage or {}).items():
        mask = rng.uniform(size=len(rows)) > share
        values.loc[mask, f] = np.nan
        reasons.loc[mask, f] = "INPUT_NOT_STATED_OR_UNDEFINED_RATIO"
    available = pd.DataFrame(None, index=rows.index, columns=values.columns, dtype=object)
    return M.Matrix(rows, values, reasons, available, pd.DataFrame({"date": days, "trendAdverse": False, "volAdverse": False, "industriesEligible": 8, "industriesWithRelMom": 8, "breadthMeasured": 50}), {"sha256": "x"})


def test_coverage_is_measured_over_the_stated_denominator_and_by_stratum():
    m = _synthetic_matrix(coverage={"C02_returnOnEquity": 0.5})
    cov = RD.feature_coverage(m, "C02_returnOnEquity", [126, 252], "2026-09-14")
    assert cov["eligibleObservations"] == len(m.rows) and cov["measuredObservations"] == int(m.values["C02_returnOnEquity"].notna().sum())
    assert cov["coveragePct"] == pytest.approx(100.0 * m.values["C02_returnOnEquity"].notna().mean(), abs=1e-4)
    assert sum(v["total"] for v in cov["coverageByYear"].values()) == len(m.rows)
    assert sum(v["total"] for v in cov["coverageByIndustry"].values()) == len(m.rows)
    assert sum(v["total"] for v in cov["coverageByLiquidityTier"].values()) == len(m.rows)
    assert sum(cov["missingness"].values()) == len(m.rows) - cov["measuredObservations"]
    assert cov["horizonUsability"]["H126"]["lastMaturableSignalDate"] is not None


def test_two_features_each_measured_on_seventy_percent_are_not_jointly_measured_on_seventy_percent():
    m = _synthetic_matrix(n_names=200, coverage={"B01_bookToMarket": 0.7, "C05_ocfToAssets": 0.7})
    joint = RD.overlap_matrix(m, ["B01_bookToMarket", "C05_ocfToAssets"])["jointCoverage"]
    assert joint[0][0] == pytest.approx(0.7, abs=0.03) and joint[1][1] == pytest.approx(0.7, abs=0.03)
    assert joint[0][1] == pytest.approx(0.49, abs=0.04) and joint[0][1] < 0.6


def test_a_feature_below_the_coverage_floor_is_not_ready_and_a_short_one_is_not_usable():
    m = _synthetic_matrix(coverage={"C03_operatingMargin": 0.4, "C04_profitMargin": 0.9})
    report = RD.build_features_report(m, REGISTRY, "2026-09-14")
    assert report["C03_operatingMargin"]["measuredStatus"] == "MEASURED_BELOW_COVERAGE_FLOOR"
    assert report["C04_profitMargin"]["measuredStatus"] == "MEASURED_READY"
    few = _synthetic_matrix(n_dates=40)
    assert RD.build_features_report(few, REGISTRY, "2026-09-14")["C04_profitMargin"]["measuredStatus"] == "MEASURED_BELOW_COVERAGE_FLOOR"      # 40 dates < 52


def test_the_six_interactions_are_classified_and_x4_stays_source_blocked():
    m = _synthetic_matrix(n_dates=90)
    result = RD.interaction_readiness(m, REGISTRY, {})
    assert set(result) == {i["interactionId"] for i in REGISTRY["levelThreeInteractions"]} and len(result) == 6
    assert result["X4_priceLeadershipByInvestorAccumulation"]["status"] == "SOURCE_BLOCKED"
    assert all(v["status"] in RD.INTERACTION_STATUSES for v in result.values())
    assert result["X5_volatilityByLiquidity"]["status"] == "READY"
    thin = RD.interaction_readiness(_synthetic_matrix(n_dates=90, coverage={"E01_amihudIlliquidity60": 0.2}), REGISTRY, {})
    assert thin["X5_volatilityByLiquidity"]["status"] == "INSUFFICIENT_COVERAGE"


def test_fewer_than_two_ready_families_selects_the_registered_blocked_path():
    m = _synthetic_matrix(coverage={f: 0.0 for f in C.CATALOGUE if not f.startswith(("D", "J05", "I01"))})
    families = RD.family_summary(RD.build_features_report(m, REGISTRY, "2026-09-14"), REGISTRY)
    verdict = RD.recommendation(families)
    assert verdict["verdict"] == "REGISTERED_BLOCKED_PATH" and verdict["familiesWithUsableReadyFeature"] == ["D"]
    full = RD.recommendation(RD.family_summary(RD.build_features_report(_synthetic_matrix(), REGISTRY, "2026-09-14"), REGISTRY))
    assert full["verdict"] == "PROCEED_TO_PHASE_C_PREREGISTRATION"


def test_the_last_maturable_signal_date_is_a_calendar_fact():
    dates = [str(d.date()) for d in CAL[(CAL >= "2026-01-02") & (CAL <= "2026-09-14")]]
    h21 = RD.last_maturable_signal_date(dates, 21, "2026-09-14")
    h126 = RD.last_maturable_signal_date(dates, 126, "2026-09-14")
    assert h21 > h126 and h126 is not None
    sessions = RC.sessions("2013-01-01", "2026-09-14", "KR")
    assert len(sessions) - 1 - (sessions.get_loc(pd.Timestamp(h126)) + 1) >= 126


# --------------------------------------------------------------------------- #
# no label, no outcome, no model, no forward price
# --------------------------------------------------------------------------- #
SPIED = (("pipeline.alpha_opportunity_v2_evaluation", "target_from_sessions"), ("pipeline.alpha_opportunity_v2_evaluation", "attach_labels"),
         ("pipeline.historical_outcomes", "horizon_frame"), ("pipeline.kr_alpha_tournament_models", "fit_ridge"), ("pipeline.kr_alpha_tournament_study", "build_labels"),
         ("pipeline.kr_alpha_tournament_walkforward", "run_process"), ("pipeline.kr_model_portfolio_execution", "build_labels"),
         ("pipeline.alpha_opportunity_v5_execution", "build_labels"), ("pipeline.kelly_portfolio", "select_portfolio_by_scores"))


def test_building_the_matrix_and_the_dry_run_touch_no_label_outcome_or_model_entry_point(monkeypatch, world):
    import importlib
    hits = []
    for module, name in SPIED:
        mod = importlib.import_module(module)
        monkeypatch.setattr(mod, name, lambda *a, _n=name, **k: hits.append(_n))
    from pipeline import kr_alpha_signal_v2_receipts as R
    for name in ("build_live_receipt", "append_live_receipt", "build_live_outcome_record"):
        monkeypatch.setattr(R, name, lambda *a, _n=name, **k: hits.append(_n))
    counters = {}
    M.build_matrix(world, [SIGNAL], counters)
    DR.run(world, now_utc="2020-12-18T10:00:00Z", signal_date=SIGNAL, replay_of_instant=True)
    assert hits == [] and counters["featureRowsBuilt"] == 12


def test_the_new_modules_import_no_label_outcome_or_model_module():
    allowed = {"kr_alpha_atlas_bars", "kr_alpha_atlas_catalogue", "kr_alpha_atlas_inputs", "kr_alpha_atlas_matrix", "kr_alpha_atlas_readiness", "kr_alpha_atlas_feasibility",
               "kr_alpha_atlas_report", "kr_alpha_atlas_dry_run", "kr_alpha_atlas_registry", "accounting_quality", "alpha_opportunity_features", "dart_derive", "historical_store",
               "kr_alpha_signal_v2", "kr_alpha_signal_v2_receipts", "kr_alpha_tournament", "kr_alpha_tournament_features", "kr_factor_anatomy", "kr_industry_anatomy",
               "kr_industry_anatomy_execution", "kr_market_risk_overlay", "kr_model_portfolio_execution", "kr_model_raw_snapshot", "kr_repaired_accounting_snapshot",
               "kr_short_selling", "kr_stock_within_industry_anatomy", "kr_value_quality_catalyst", "krx_prices", "liquidity_attention", "longterm", "price_adjustment",
               "prospective_receipt_core", "replay_calendar", "kr_continuing_dividend_sample", "regional_alpha_features"}
    for name in ("bars", "catalogue", "inputs", "matrix", "readiness", "feasibility", "report", "dry_run"):
        tree = ast.parse((ROOT / f"pipeline/kr_alpha_atlas_{name}.py").read_text())
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 1 and n.module is None for a in n.names}
        imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 1 and n.module}
        assert imported <= allowed, (name, sorted(imported - allowed))


def test_registry_statuses_are_unchanged_by_this_change():
    summary = AR.summary(REGISTRY)
    assert summary["features"] == 106 and summary["readiness"]["READY"] == 25 and summary["readiness"]["SOURCE_BLOCKED"] == 7


# --------------------------------------------------------------------------- #
# weekly dry run
# --------------------------------------------------------------------------- #
def test_the_signal_session_is_the_latest_weekly_decision_session_with_a_final_close():
    assert str(DR.latest_signal_session("2020-12-18T08:59:00Z").date()) == "2020-12-11"      # Friday's close is not final until 09:00 UTC
    assert str(DR.latest_signal_session("2020-12-18T09:00:00Z").date()) == "2020-12-18"
    assert str(DR.latest_signal_session("2020-12-22T03:00:00Z").date()) == "2020-12-18"      # mid-week: still the previous Friday
    with pytest.raises(ValueError):
        DR.latest_signal_session("2020-12-18T09:00:00")                                      # a naive timestamp is refused


def test_the_dry_run_is_never_actionable(world):
    out = DR.run(world, now_utc="2020-12-18T10:00:00Z", replay_of_instant=True)
    assert out["state"] in DR.STATES and out["signalSession"] == SIGNAL and out["authorization"] == "NOT_REGISTERED"
    assert out["clock"] == "EXPLICIT_REPLAY_OF_A_PAST_INSTANT" and out["evidenceClass"] == "DRY_RUN_NOT_A_RECEIPT"
    DR.assert_not_actionable(out)
    assert out["h2Decision"]["status"] in ("NOT_READY", "BLOCKED")
    with pytest.raises(ValueError):
        DR.assert_not_actionable({"portfolio": {"weights": {}}})
    assert "weights" not in json.dumps(out).lower()


def test_the_dry_run_is_blocked_without_a_pit_membership_snapshot_or_a_signal_session(world):
    empty = make_world()
    empty.memberships = RAF.MembershipSnapshots([{"date": "2021-01-04", "members": ["T01.KS"]}])
    blocked = DR.run(empty, now_utc="2020-12-18T10:00:00Z", signal_date=SIGNAL, replay_of_instant=True)
    assert blocked["state"] == "BLOCKED" and "NO_PIT_MEMBERSHIP_SNAPSHOT_STRICTLY_OLDER_THAN_THE_SIGNAL_DATE" in blocked["blockers"]
    early = DR.run(world, now_utc="2020-12-18T05:00:00Z", signal_date=SIGNAL, replay_of_instant=True)
    assert early["state"] == "BLOCKED" and "SIGNAL_SESSION_CLOSE_NOT_FINAL_AT_THE_CLOCK" in early["blockers"]


def test_the_dry_run_uses_no_registered_authorization():
    from pipeline import kr_alpha_signal_v2_receipts as R
    assert R.REGISTERED_AUTHORIZATION is None
    tree = ast.parse((ROOT / "pipeline/kr_alpha_atlas_dry_run.py").read_text())
    uses = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "REGISTERED_AUTHORIZATION"]
    compared = {id(c.left) for c in ast.walk(tree) if isinstance(c, ast.Compare) and all(isinstance(o, ast.Is) for o in c.ops)}
    assert uses and all(id(u) in compared for u in uses)       # the module only ever asks "is it None?"; it never reads or passes an authorization


# --------------------------------------------------------------------------- #
# the committed Phase B outputs (produced by a real run; here only checked for consistency, never recomputed)
# --------------------------------------------------------------------------- #
RESULTS = ROOT / "docs/results"
COMMITTED = {k: RESULTS / v for k, v in {"readiness": "kr-alpha-atlas-phase-b-readiness.json", "manifest": "kr-alpha-atlas-phase-b-phase-c-manifest.json",
                                           "sources": "kr-alpha-atlas-phase-b-source-feasibility.json", "dryRun": "kr-alpha-atlas-phase-b-weekly-dry-run-example.json"}.items()}


@pytest.fixture(scope="module")
def committed():
    if not all(p.exists() for p in COMMITTED.values()):
        pytest.skip("Phase B outputs not generated yet")
    return {k: json.loads(p.read_text()) for k, p in COMMITTED.items()}


def test_the_committed_outputs_are_canonical_and_the_summary_is_rendered_from_them(committed):
    import subprocess
    import sys
    done = subprocess.run([sys.executable, str(ROOT / "scripts/build_kr_alpha_atlas_phase_b.py"), "--check"], capture_output=True, text=True, cwd=ROOT)
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_manifest_agrees_with_the_report_and_the_registry(committed):
    report, manifest = committed["readiness"], committed["manifest"]
    assert report["evidenceClass"] == "OUTCOME_BLIND_DATA_READINESS" and report["outcomeAccess"] == "NONE"
    assert manifest["identity"]["registrySha256"] == RD.file_sha256(ROOT / RP.REGISTRY_PATH)
    assert manifest["identity"]["matrixDigest"] == report["identity"]["matrixDigest"]
    ready = {k for k, r in report["features"].items() if r["measuredStatus"] == "MEASURED_READY"}
    assert {e["featureId"] for e in manifest["eligibleFeatures"]} <= ready
    roles = {f["featureId"]: f for f in REGISTRY["features"]}
    for e in manifest["eligibleFeatures"]:
        assert roles[e["featureId"]]["role"] == "ALPHA_CANDIDATE" and roles[e["featureId"]]["readinessStatus"] != "ALREADY_TESTED"
    assert manifest["recommendation"] == report["recommendation"]
    assert set(report["interactions"]) == {i["interactionId"] for i in REGISTRY["levelThreeInteractions"]}
    assert report["interactions"]["X4_priceLeadershipByInvestorAccumulation"]["status"] == "SOURCE_BLOCKED"
    assert len(report["features"]) == 106 and report["pitChecks"]["pass"]
    assert report["counters"]["labelsBuilt"] == 0 and report["counters"]["modelsFitted"] == 0 and report["counters"]["forwardPriceReads"] == 0


def test_the_committed_dry_run_is_not_ready_or_blocked_and_carries_no_actionable_key(committed):
    dry = committed["dryRun"]
    assert dry["state"] in DR.STATES and dry["evidenceClass"] == "DRY_RUN_NOT_A_RECEIPT" and dry["authorization"] == "NOT_REGISTERED"
    DR.assert_not_actionable(dry)


# --------------------------------------------------------------------------- #
# report assembly, source register and universe feasibility on synthetic inputs
# --------------------------------------------------------------------------- #
FAKE_FACTS = dict(universe={"verdict": {"status": "BROADER_UNIVERSE_NOT_READY_KEEP_TOP120", "reason": "synthetic", "reason_ko": "합성"}, "_tradingValueBasis": B.TRADING_VALUE_BASIS_PROXY, "byYear": {},
                            "acquisitionEstimate": {"extraTickersNeedingDartCollection": 0, "callsUpperBound": 0, "runsUpperBound": 0}},
                  termination={"inventoriedSecurities": 22}, benchmark={"symbol": "069500.KS", "reconciliationStatus": "BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED"})
FLOW = {"updatedAt": "2026-09-24T06:23:26Z", "thisRun": {"calls": 0, "recordsWritten": 0, "stopReason": "REFUSED: HTTP 400: b'LOGOUT'"}, "remainingPairs": 10}
OWN = {"earliestObservedEventDate": "2024-09-24", "latestObservedEventDate": "2026-09-23", "eventCount": 100, "companiesQueried": 254,
       "endpointSemantics": {"pitAvailabilityRule": "DART_RECEIPT_DATE_NOT_TRANSACTION_OR_REFERENCE_DATE", "noRowsMeaning": "NO_ROWS_RETURNED_BY_BOUNDED_ENDPOINT_NOT_PROOF_OF_NO_HISTORICAL_FILINGS"}}
POLICY = json.loads((ROOT / "data/bok-policy-rates.json").read_text())


def test_the_source_register_keeps_blocked_sources_blocked_and_repeats_no_probe():
    from pipeline import kr_alpha_atlas_feasibility as FE
    reg = FE.source_register(REGISTRY, OWN, FLOW, POLICY, "2026-09-14")
    assert "NONE was repeated" in reg["decision"]
    by = {tuple(s["features"]): s for s in reg["sources"]}
    flow = next(s for s in reg["sources"] if "G01_foreignNetBuying" in s["features"])
    assert flow["status"] == "SOURCE_BLOCKED" and "OHLCV accumulation proxy (D11) for investor-type flow" in " ".join(flow["doNotDo"])
    assert flow["optionalOneReprobe"]["inputs"] == {"probe": "kr-investor-flow", "args": ""}
    assert any("G08_shortSellingVolume" in s["features"] and s["status"] == "SOURCE_BLOCKED" for s in reg["sources"])
    assert next(s for s in reg["sources"] if "G06_largeHolderAccumulation" in s["features"])["status"] == "PIT_SAFE_BUT_HISTORY_TOO_SHORT"
    assert by
    covered = {f for s in reg["sources"] for f in s["features"]}
    for f in REGISTRY["features"]:
        if f["readinessStatus"] in ("SOURCE_BLOCKED", "PIT_UNSAFE", "NOT_FEASIBLE"):
            assert f["featureId"] in covered, f["featureId"]


def test_report_assembly_and_the_korean_summary_on_a_synthetic_matrix():
    from pipeline import kr_alpha_atlas_feasibility as FE
    sources = FE.source_register(REGISTRY, OWN, FLOW, POLICY, "2026-09-14")
    report, manifest = RP.assemble(_synthetic_matrix(n_dates=90), REGISTRY, cutoff="2026-09-14", sources=sources, **FAKE_FACTS)
    assert report["evidenceClass"] == "OUTCOME_BLIND_DATA_READINESS" and len(report["features"]) == 106
    assert manifest["recommendation"]["verdict"] == "PROCEED_TO_PHASE_C_PREREGISTRATION"
    assert {e["featureId"] for e in manifest["eligibleFeatures"]} and "E03_capacityMedianTradedValue60" not in {e["featureId"] for e in manifest["eligibleFeatures"]}
    assert manifest["constructionAndEligibilityFeatures"]["E03_capacityMedianTradedValue60"] == "COST_CAPACITY"
    assert any(x["featureId"] == "G01_foreignNetBuying" for x in manifest["excludedFeatures"])
    assert [h["id"] for h in manifest["humanTriggeredAcquisition"]][0] == "OFFICIAL_TRADED_VALUE_RERUN"
    text = RP.render_summary_ko(report, manifest, FAKE_FACTS["universe"], sources)
    assert "## 한눈에 보기" in text and "## 6개 상호작용" in text and "kr-investor-flow" in text and str(len(report["features"])) in text
    assert RP.render_summary_ko(report, manifest, FAKE_FACTS["universe"], sources) == text


def test_universe_feasibility_counts_qualified_names_outside_the_top120_without_adding_any(monkeypatch):
    from pipeline import kr_alpha_atlas_feasibility as FE
    inputs = make_world()
    inputs.memberships = RAF.MembershipSnapshots([{"date": "2019-01-01", "members": ["T%02d.KS" % i for i in range(1, 13)]}])
    days = [str(d.date()) for d in CAL[(CAL >= "2019-01-02")][:520]]
    rows = []
    for i in range(30):
        big = i < 20                                             # 20 liquid names, 10 illiquid
        for d in days:
            rows.append({"date": d, "ticker": ("T%02d.KS" % (i + 1)) if i < 12 else "Z%02d.KS" % i, "close": 10000.0, "volume": 1e6 if big else 1e3, "listedShares": 1e7})
    monkeypatch.setattr(FE, "_ledger_frame", lambda repo, commit: pd.DataFrame(rows))
    out = FE.universe_feasibility(inputs, ROOT, "x", "2020-12-31", {"securities": [{"code": "Z15.KS"}]})
    assert out["scope"].startswith("FEASIBILITY_ONLY")
    year = out["byYear"]["2020"]
    assert year["meanQualifiedNames"] == 20.0 and year["meanTop120"] == 12.0 and year["meanQualifiedOutsideTop120"] == 8.0
    assert out["qualifiedTickersEverOutsideTop120"] == 8 and out["qualifiedTickersWithoutAnyDartRecordOutsideTop120"] == 8
    assert out["verdict"]["status"] == "BROADER_UNIVERSE_NOT_READY_KEEP_TOP120"
    assert out["acquisitionEstimate"]["status"] == "ESTIMATE_FROM_COLLECTOR_STRUCTURE_NOT_A_MEASUREMENT"


def test_a_ready_that_barely_clears_the_floor_is_reported_thin_and_complete_case_coverage_is_published():
    m = _synthetic_matrix(n_dates=90, coverage={"C02_returnOnEquity": 0.63, "B01_bookToMarket": 0.8, "C05_ocfToAssets": 0.8})
    report = RD.build_features_report(m, REGISTRY, "2026-09-14")
    assert report["C02_returnOnEquity"]["measuredStatus"] == "MEASURED_READY" and report["C02_returnOnEquity"]["thinOverFloor"]
    assert not report["D01_volumeSurge5_60"]["thinOverFloor"]
    baselines = RD.baseline_readiness(REGISTRY, report, m)
    assert baselines["B1_VALUE_PROFITABILITY"]["status"] == "READY"            # every member usable; missingness indicators carry the rest
    assert baselines["B1_VALUE_PROFITABILITY"]["completeCaseCoverageWithinCommonRangePct"] == pytest.approx(64.0, abs=3.0)   # 0.8 x 0.8 of the names


def test_b08_is_measured_on_the_h2_contracts_own_eligible_names_and_the_all_member_figure_is_published():
    m = _synthetic_matrix(n_dates=90)
    ineligible = (m.rows.index % 3 == 0)
    m.rows.loc[ineligible, "b08State"] = "INELIGIBLE"
    m.values.loc[ineligible, "B08_valueBusinessConfirmation"] = float("nan")
    m.reasons.loc[ineligible, "B08_valueBusinessConfirmation"] = "S2_INELIGIBLE"
    cov = RD.feature_coverage(m, "B08_valueBusinessConfirmation", [126, 252], "2026-09-14")
    assert cov["coveragePct"] == 100.0 and cov["eligibleObservations"] == int((~ineligible).sum())
    assert cov["coverageAllMemberRowsPct"] == pytest.approx(100.0 * (~ineligible).mean(), abs=0.01)
    assert "definitional" in cov["denominator"] or "does not itself exclude" in cov["denominator"]
    plain = RD.feature_coverage(m, "C04_profitMargin", [126, 252], "2026-09-14")
    assert plain["eligibleObservations"] == len(m.rows) and "coverageAllMemberRowsPct" not in plain
