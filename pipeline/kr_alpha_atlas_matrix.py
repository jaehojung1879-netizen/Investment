"""kr-alpha-atlas Phase B — one point-in-time feature matrix at the grain (signal_date, ticker), outcome-blind.

READS: PIT Top120 membership (snapshot strictly older than the signal date), KRX bars, replay-v16 closes, DART filings visible before the signal date,
the v4 industry reconstruction. NEVER READS: a label, a forward price, a return after the signal date, a model prediction. A test replaces every outcome /
label / training entry point with a spy that raises and requires zero hits; another truncates the inputs at the signal date and requires the same row.

ONE DEFINITION PER FEATURE. Every number comes from the function named in `kr_alpha_atlas_catalogue` (the sealed or production one), so the historical
matrix and the weekly dry run (`kr_alpha_atlas_dry_run`) cannot drift apart. This module orchestrates and adds no economic formula that the catalogue does
not list under `addsArithmetic`.

WHAT A CELL CARRIES. `values[feature]` (a float, or NaN), `reasons[feature]` (why a NaN is a NaN, from a closed vocabulary), and for filing-based
features `available[feature]` (the receipt date that made the figure visible). A price- or bar-based value is available at the signal session itself.
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pandas as pd

from . import accounting_quality as AQ
from . import alpha_opportunity_features as AOF
from . import dart_derive as DD
from . import kr_alpha_atlas_bars as B
from . import kr_alpha_atlas_catalogue as C
from . import kr_alpha_signal_v2 as S2
from . import kr_alpha_tournament as T
from . import kr_alpha_tournament_features as TF
from . import kr_factor_anatomy as FA
from . import kr_industry_anatomy as I
from . import kr_industry_anatomy_execution as IE
from . import kr_market_risk_overlay as O
from . import kr_short_selling as KSS
from . import kr_stock_within_industry_anatomy as S
from . import kr_value_quality_catalyst as VQ
from . import longterm

CONTRACT = "KR_ALPHA_ATLAS_MATRIX_V1"
BENCHMARK = T.BENCHMARK
MEGA_CAPS = ("005930.KS", "000660.KS")
FILING_RECENT_SESSIONS = 5
STAGE = VQ.STAGE
PRICE_WINDOW = 253                      # closes needed for the longest price feature (252 returns)

REASONS = B.MISSING_REASONS + (
    "NO_PRICE_PANEL", "INSUFFICIENT_PRICE_HISTORY", "NON_FINITE_PRICE_IN_WINDOW", "BENCHMARK_WINDOW_UNAVAILABLE",
    "NO_VISIBLE_FILING", "UNKNOWN_OR_MIXED_STATEMENT_BASIS", "MARKET_CAP_UNAVAILABLE", "INPUT_NOT_STATED_OR_UNDEFINED_RATIO",
    "NO_PRIOR_PERIOD_FILING", "INDUSTRY_UNCLASSIFIED", "INDUSTRY_COHORT_BELOW_MINIMUM", "INDUSTRY_COHORT_MEMBER_MISSING_INPUT",
    "INSUFFICIENT_INDUSTRIES", "NO_MEASURED_NAME", "INSUFFICIENT_OWN_HISTORY", "S2_INELIGIBLE", "CONFIRMATION_UNMEASURED", "MISSING_VALUE_INPUT",
    "MARKET_STATE_DATA_INSUFFICIENT", "INSUFFICIENT_PEERS_WITH_VALUE", "REASON_NOT_RECORDED")


# --------------------------------------------------------------------------- #
# Market view over the bars, in the shape the sealed feature code reads
# --------------------------------------------------------------------------- #
class BarsMarket:
    """`at(ticker, date)` and `trailing(ticker, date, lookback)` — the two methods `kr_value_quality_catalyst.feature_at` calls on a market store."""

    def __init__(self, bars):
        self.bars = bars

    def at(self, ticker, date):
        bars = self.bars.get(ticker)
        return bars.quote(date) if bars is not None else None

    def trailing(self, ticker, date, lookback=60):
        bars = self.bars.get(ticker)
        if bars is None:
            return [None] * lookback
        return bars.trailing(date, lookback)


# --------------------------------------------------------------------------- #
# Price-window features (replay close, past-only)
# --------------------------------------------------------------------------- #
def window_closes(frame, days, pos, length):
    if frame is None or "Close" not in frame or pos - length + 1 < 0:
        return None
    return pd.to_numeric(frame["Close"].reindex(days[pos - length + 1:pos + 1]), errors="coerce").to_numpy(float)


def _ok(a, n):
    return a is not None and len(a) >= n and np.isfinite(a[-n:]).all() and (a[-n:] > 0).all()


def price_features(close, bench):
    """Registry A/F values from the closes of the sessions ENDING AT the signal session (oldest first, last element = signal close)."""
    out = dict.fromkeys(("A01_return1d", "A02_return5d", "A03_return21d", "A04_return63d", "A06_return252d", "A08_momentum6", "A10_residualMomentum126",
                         "A11_distance52wHigh", "A12_momentumPersistence", "A13_momentumAcceleration21", "A14_ma200Distance", "F01_totalVolatility63",
                         "F03_beta252", "F04_idiosyncraticVol", "F05_maxDrawdown252", "F06_crashExposure", "F07_benchmarkCorrelation252"))
    close = None if close is None else np.asarray(close, float)
    bench = None if bench is None else np.asarray(bench, float)
    if close is None:
        return out
    if _ok(close, 2):
        out["A01_return1d"] = float(close[-1] / close[-2] - 1.0)
    if _ok(close, 6):
        out["A02_return5d"] = float(close[-1] / close[-6] - 1.0)
    if _ok(close, 253):
        out["A06_return252d"] = float(close[-1] / close[-253] - 1.0)
    if _ok(close, 126):
        out["A08_momentum6"] = longterm.momentum_6m(pd.Series(close[-126:]))
    if _ok(close, 43):
        out["A13_momentumAcceleration21"] = float((close[-1] / close[-22] - 1.0) - (close[-22] / close[-43] - 1.0))
    derived = TF.derived_price_features(close, bench if bench is not None else [])
    out.update({"A03_return21d": derived["ret21"], "A04_return63d": derived["ret63"], "A11_distance52wHigh": derived["dist252High"],
                "A14_ma200Distance": derived["ma200Distance"], "F01_totalVolatility63": derived["vol63"], "F03_beta252": derived["beta252"],
                "F05_maxDrawdown252": derived["maxDrawdown252"]})
    if _ok(close, 253) and _ok(bench, 253):
        r = np.diff(close[-253:]) / close[-253:-1]
        b = np.diff(bench[-253:]) / bench[-253:-1]
        if derived["beta252"] is not None and _ok(close, 127) and _ok(bench, 127):
            out["A10_residualMomentum126"] = float((close[-1] / close[-127] - 1.0) - derived["beta252"] * (bench[-1] / bench[-127] - 1.0))
        wins = [(close[-1 - 21 * k] / close[-22 - 21 * k] - 1.0) - (bench[-1 - 21 * k] / bench[-22 - 21 * k] - 1.0) for k in range(12)]
        out["A12_momentumPersistence"] = float(np.mean([w > 0 for w in wins]))
        var_b = float(np.var(b, ddof=1))
        if var_b > 0:
            beta = float(np.cov(r, b, ddof=1)[0, 1] / var_b)
            resid = r - (r.mean() - beta * b.mean()) - beta * b
            out["F04_idiosyncraticVol"] = float(np.std(resid, ddof=2) * math.sqrt(252))
            sd_r = float(np.std(r, ddof=1))
            if sd_r > 0:
                out["F07_benchmarkCorrelation252"] = float(np.corrcoef(r, b)[0, 1])
            down = b < 0
            if int(down.sum()) >= 30 and float(np.var(b[down], ddof=1)) > 0:
                out["F06_crashExposure"] = float(np.cov(r[down], b[down], ddof=1)[0, 1] / np.var(b[down], ddof=1))
    return out


def _price_reason(frame, days, pos, bench_ok, window):
    if frame is None:
        return "NO_PRICE_PANEL"
    if pos - window + 1 < 0 or frame.index.min() > days[pos - window + 1]:
        return "INSUFFICIENT_PRICE_HISTORY"
    return "NON_FINITE_PRICE_IN_WINDOW" if bench_ok else "BENCHMARK_WINDOW_UNAVAILABLE"


# --------------------------------------------------------------------------- #
# Accounting features (DART, receipt-dated, visible strictly before the signal date)
# --------------------------------------------------------------------------- #
def _compatible(index, keys):
    return VQ._compatible(index, keys)


def _basis_reason(index, keys):
    if any(k not in index for k in keys):
        return "NO_PRIOR_PERIOD_FILING"
    return None if _compatible(index, keys) else "UNKNOWN_OR_MIXED_STATEMENT_BASIS"


def _ttm_keys(year, stage):
    return [(year, stage)] if stage == DD.ANNUAL else [(year, stage), (year - 1, DD.ANNUAL), (year - 1, stage)]


def accounting_features(records, shares_by_key, signal_date, market_cap, days):
    """({feature: value}, {feature: reason}, {feature: availableFrom}, info) for one ticker on one signal date.

    Reuses `accounting_quality.derive_kr_fields` and `dart_derive.derive_fields` on the filings visible BEFORE the signal date (never a whole-history derive
    followed by a filter). A field whose own inputs span a consolidated/separate mix is dropped, not blended."""
    values, reasons, available = {}, {}, {}
    names = ("B04_freeCashFlowYield", "C02_returnOnEquity", "C03_operatingMargin", "C04_profitMargin", "C06_cashConversion", "C09_assetGrowth",
             "C10_liabilityGrowth", "C11_shareDilution", "C12_profitabilityPersistence", "C15_capexIntensity", "J01_periodicFilingEvent")
    visible = AOF.visible_filings(records or [], signal_date, "KR")
    index = DD.index_filings(visible)
    if not index:
        return values, dict.fromkeys(names, "NO_VISIBLE_FILING"), available, {"status": "NO_VISIBLE_FILING"}
    year, stage = max(index, key=lambda k: (k[0], STAGE[k[1]]))
    current = index[(year, stage)]
    stamp = current["availableFrom"]
    info = {"status": "VISIBLE", "availableFrom": stamp, "period": [year, stage], "basis": current.get("fsDiv")}
    days_since = int(((pd.Timestamp(signal_date) - pd.Timestamp(stamp)).days))
    since = int(days.searchsorted(pd.Timestamp(signal_date), side="right") - days.searchsorted(pd.Timestamp(stamp), side="left")) - 1
    values["J01_periodicFilingEvent"] = 1.0 if since <= FILING_RECENT_SESSIONS else 0.0
    available["J01_periodicFilingEvent"] = stamp
    info["daysSinceFiling"] = days_since
    info["sessionsSinceFiling"] = since
    own_ok = _compatible(index, [(year, stage)])
    if not own_ok:
        reasons.update(dict.fromkeys([n for n in names if n != "J01_periodicFilingEvent"], "UNKNOWN_OR_MIXED_STATEMENT_BASIS"))
        return values, reasons, available, info

    def put(name, value, keys, why="INPUT_NOT_STATED_OR_UNDEFINED_RATIO"):
        basis = _basis_reason(index, keys)
        if basis:
            reasons[name] = basis
        elif value is None or not math.isfinite(value):
            reasons[name] = why
        else:
            values[name] = float(value)
            available[name] = stamp

    shares, _ = DD.carried_shares(shares_by_key, year, stage)
    prior_shares, _ = DD.carried_shares(shares_by_key, year - 1, stage) if shares_by_key else (None, None)
    quality, _ = AQ.derive_kr_fields(index, year, stage, shares, prior_shares)
    base, _ = DD.derive_fields(index, year, stage, None)
    ttm = _ttm_keys(year, stage)
    growth = [(year, stage), (year - 1, stage)]
    ok = _basis_reason(index, ttm) is None
    ni = DD.trailing_twelve_months(index, year, stage, "당기순이익")[0] if ok else None
    revenue = DD.trailing_twelve_months(index, year, stage, "매출액")[0] if ok else None
    ocf = DD.trailing_twelve_months(index, year, stage, "영업활동현금흐름")[0] if ok else None
    capex = DD.trailing_twelve_months(index, year, stage, "유형자산의취득")[0] if ok else None
    put("C02_returnOnEquity", base.get("roe"), ttm)
    put("C03_operatingMargin", base.get("operatingMargin"), ttm)
    put("C04_profitMargin", base.get("profitMargin"), ttm)
    put("C06_cashConversion", quality.get("ocfToNetIncomePct") if ni is not None and ni > 0 else None, ttm)
    put("C09_assetGrowth", quality.get("assetGrowthPct"), growth)
    put("C10_liabilityGrowth", quality.get("debtGrowthPct"), growth)
    put("C11_shareDilution", quality.get("shareCountChangePct"), growth)
    put("C15_capexIntensity", quality.get("capexIntensityPct") if revenue is not None and revenue > 0 else None, ttm)
    fcf = (ocf - abs(capex)) if ocf is not None and capex is not None else None
    put("B04_freeCashFlowYield", fcf / market_cap if fcf is not None and market_cap and market_cap > 1 else None, ttm,
        "MARKET_CAP_UNAVAILABLE" if not market_cap or market_cap <= 1 else "INPUT_NOT_STATED_OR_UNDEFINED_RATIO")
    margins = []
    for key in sorted(index, key=lambda k: (k[0], STAGE[k[1]]))[-4:]:
        if _compatible(index, [key]) and index[key].get("fsDiv") == current.get("fsDiv"):
            f, _ = DD.derive_fields(index, key[0], key[1], None)
            if f.get("operatingMargin") is not None:
                margins.append((index[key]["availableFrom"], f["operatingMargin"]))
    stab = AQ.operating_margin_stability(margins, 4)
    if stab["stabilityPct"] is not None:
        values["C12_profitabilityPersistence"] = float(stab["stabilityPct"])
        available["C12_profitabilityPersistence"] = stamp
    else:
        reasons["C12_profitabilityPersistence"] = "NO_PRIOR_PERIOD_FILING"
    for n in names:
        if n not in values and n not in reasons:
            reasons[n] = "INPUT_NOT_STATED_OR_UNDEFINED_RATIO"
    return values, reasons, available, info


# --------------------------------------------------------------------------- #
# The matrix
# --------------------------------------------------------------------------- #
class Matrix:
    def __init__(self, rows, values, reasons, available, date_context, identity):
        self.rows, self.values, self.reasons, self.available = rows, values, reasons, available
        self.date_context, self.identity = date_context, identity

    def digest(self):
        """Canonical digest of every cell, independent of row order: values rounded to 12 significant digits."""
        h = hashlib.sha256()
        order = self.rows.sort_values(["date", "ticker"]).index
        h.update(json.dumps(sorted(self.values.columns)).encode())
        for col in sorted(self.values.columns):
            h.update(col.encode())
            h.update(json.dumps([None if not np.isfinite(v) else float(f"{v:.12g}") for v in self.values.loc[order, col].to_numpy(float)]).encode())
            h.update(json.dumps(self.reasons.loc[order, col].fillna("").tolist()).encode())
        h.update(json.dumps(self.rows.loc[order, ["date", "ticker", "industry", "liquidityTier"]].astype(str).values.tolist()).encode())
        return h.hexdigest()


def liquidity_tiers(values):
    """Tercile of E03 (median KRW traded value) across the members of one date; UNKNOWN where E03 is missing. Cross-sectional on the date only."""
    x = pd.Series(values, dtype=float)
    ok = x.notna()
    tier = pd.Series("UNKNOWN", index=x.index, dtype=object)
    if ok.sum() >= 3:
        pct = x[ok].rank(pct=True, method="average")
        tier[ok] = np.where(pct <= 1 / 3, "LOW", np.where(pct <= 2 / 3, "MID", "HIGH"))
    return tier


def _spearman(a, b):
    rank = FA.spearman(np.asarray(a, float), np.asarray(b, float))
    return float(rank) if np.isfinite(rank) else None


def build_matrix(inputs, dates, counters=None):
    """The matrix over `dates`. `counters` is incremented at the feature-build call sites; a test reads it beside its spies."""
    counters = counters if counters is not None else {}
    counters["matrixBuilds"] = counters.get("matrixBuilds", 0) + 1
    days = inputs.calendar
    bench = inputs.prices.get(BENCHMARK)
    market = BarsMarket(inputs.bars)
    intervals, crosswalk, ends = inputs.industry
    schedule, caps = {}, {}
    for date in dates:
        snapshot = inputs.memberships.on(date)
        if snapshot is None:
            continue
        schedule[date] = list(snapshot["members"])
        for t in schedule[date]:
            quote = market.at(t, date)
            caps[(date, t)] = quote["marketCap"] if quote else np.nan
    membership = I.membership_table(schedule, intervals, crosswalk, ends)
    cap_frame = pd.DataFrame([{"date": d, "ticker": t, "marketCap": v} for (d, t), v in caps.items()], columns=["date", "ticker", "marketCap"])
    cohorts = I.build_cohorts(membership, cap_frame)
    stock_cohorts = S.build_cohorts(membership)
    status_of = {(r.date, r.ticker): r.membershipStatus for r in membership.itertuples()}
    industry_of = {(r.date, r.ticker): r.industry for r in membership.itertuples() if isinstance(r.industry, str)}

    rows, vals, reas, avails, ctx = [], [], [], [], []
    h01_by_date = {}
    for date in sorted(schedule):
        members = schedule[date]
        pos = days.searchsorted(pd.Timestamp(date), side="right") - 1
        bench_win = window_closes(bench, days, pos, PRICE_WINDOW)
        bench_ok = bench_win is not None and np.isfinite(bench_win).all()
        state = O.state_at(bench, date)
        per, per_reason, per_avail, vq_rows = {}, {}, {}, {}
        for t in members:
            counters["featureRowsBuilt"] = counters.get("featureRowsBuilt", 0) + 1
            v, r, a = {}, {}, {}
            bars = inputs.bars.get(t)
            bv, br = bars.features_at(date) if bars is not None else ({}, dict.fromkeys(B.BARS_FEATURES, "NO_QUOTE_AT_SIGNAL"))
            v.update(bv)
            r.update(br)
            frame = inputs.prices.get(t)
            close = window_closes(frame, days, pos, PRICE_WINDOW)
            pf = price_features(close, bench_win if bench_ok else None)
            causes = {}

            def cause_for(window, _bars=bars, _date=date):
                if window not in causes:
                    causes[window] = _bars.basis_cause(_date, window) if _bars is not None else None
                return causes[window]
            for name, value in pf.items():
                window = C.CATALOGUE[name]["windowSessions"] or PRICE_WINDOW
                if cause_for(window):
                    r[name] = cause_for(window)
                elif value is None or not np.isfinite(value):
                    r[name] = _price_reason(frame, days, pos, bench_ok, window)
                else:
                    v[name] = float(value)
            vq = VQ.feature_at(t, date, inputs.accounting.get(t, []), market, frame, bench)
            vq_rows[t] = vq
            prov = vq["accountingProvenance"]
            quote_present = vq["marketValuePresent"]
            mapping = {"A05_relative126": "relative126", "A07_momentum12_1": "momentum121", "B01_bookToMarket": "bookToMarketProxy",
                       "B02_earningsYield": "earningsYieldProxy", "B03_ocfYield": "ocfYieldProxy", "C01_returnOnAssets": "netIncomeToAssets",
                       "C05_ocfToAssets": "ocfToAssets", "C07_negativeAccruals": "negativeAccrualsToAssets", "C14_ocfImprovement": "ocfImprovementToAssets",
                       "E02_logAdv60": "logAdv60", "F02_downsideVol126": "downsideVol126"}
            for name, key in mapping.items():
                value = vq.get(key)
                if name in ("A05_relative126", "A07_momentum12_1", "F02_downsideVol126") and cause_for(C.CATALOGUE[name]["windowSessions"]):
                    r[name] = cause_for(C.CATALOGUE[name]["windowSessions"])
                elif value is None or not np.isfinite(value):
                    if name in ("A05_relative126", "A07_momentum12_1", "F02_downsideVol126"):
                        r[name] = _price_reason(frame, days, pos, bench_ok, C.CATALOGUE[name]["windowSessions"])
                    elif name == "E02_logAdv60":
                        r[name] = br.get("E03_capacityMedianTradedValue60", "NON_POSITIVE_DENOMINATOR_OR_DEGENERATE")
                    elif prov["status"] != "VISIBLE":
                        r[name] = prov["status"]
                    else:
                        r[name] = "MARKET_CAP_UNAVAILABLE" if (not quote_present and name in ("B01_bookToMarket", "B02_earningsYield", "B03_ocfYield")) \
                            else "INPUT_NOT_STATED_OR_UNDEFINED_RATIO"
                else:
                    v[name] = float(value)
                    if name.startswith(("B0", "C0", "C1")) and prov.get("availableFrom"):
                        a[name] = prov["availableFrom"]
            if "C07_negativeAccruals" in v:
                v["C08_netIncomeMinusOcf"] = -v["C07_negativeAccruals"]
                a["C08_netIncomeMinusOcf"] = a.get("C07_negativeAccruals")
            else:
                r["C08_netIncomeMinusOcf"] = r.get("C07_negativeAccruals", "INPUT_NOT_STATED_OR_UNDEFINED_RATIO")
            av, ar, aa, info = accounting_features(inputs.accounting.get(t, []), inputs.shares.get(t), date, caps.get((date, t)), days)
            v.update(av)
            r.update(ar)
            a.update(aa)
            v["J05_shortSellingRegime"] = float((KSS.REGIME_NORMAL, KSS.REGIME_BANNED_COVID, KSS.REGIME_BANNED_STRUCTURAL).index(KSS.regime_label(date)))
            per[t], per_reason[t], per_avail[t] = v, r, a
            per_avail[t]["_filing"] = info.get("availableFrom")

        # ---- date-level cross-sectional features ------------------------------------------------------------------------------------------------- #
        eligible = {ind: c for (d, ind), c in cohorts.items() if d == date and c["status"] == "ELIGIBLE"}
        past = IE.past_features(inputs.prices, members, days, date)
        panel = {t: {k: vq_rows[t].get(k) for k in (*I.FUNDAMENTAL_COLUMNS, "logAdv60")} for t in members}
        ind_values = {ind: I.industry_features(c, past, panel) for ind, c in sorted(eligible.items())}
        trail = {t: past.get(t, {}).get("trail126", np.nan) for t in members}
        cap_of = {t: caps.get((date, t), np.nan) for t in members}
        eligible_rows = []
        for t in members:
            ind = industry_of.get((date, t))
            v, r = per[t], per_reason[t]
            if ind is None:
                for n in ("A09_industryRelativeMomentum126", "B05_industryRelativeValue", "H01_industryRelMom126", "H02_industryRelMom63",
                          "H03_industryBreadthAboveMA126", "H04_withinIndustryDispersion126", "H06_industryConcentrationTop1", "H08_equalVsCapWeightIndustry",
                          "H11_industryEarningsContext", "H12_industryValuationContext"):
                    r[n] = "INDUSTRY_UNCLASSIFIED"
            elif ind not in eligible:
                for n in ("A09_industryRelativeMomentum126", "B05_industryRelativeValue", "H01_industryRelMom126", "H02_industryRelMom63",
                          "H03_industryBreadthAboveMA126", "H04_withinIndustryDispersion126", "H06_industryConcentrationTop1", "H08_equalVsCapWeightIndustry",
                          "H11_industryEarningsContext", "H12_industryValuationContext"):
                    r[n] = "INDUSTRY_COHORT_BELOW_MINIMUM"
            else:
                feats = ind_values[ind]
                for name, key in (("H01_industryRelMom126", "REL_MOM_126"), ("H02_industryRelMom63", "REL_MOM_63"), ("H03_industryBreadthAboveMA126", "BREADTH_ABOVE_MA_126"),
                                  ("H04_withinIndustryDispersion126", "CONSTITUENT_DISPERSION_126"), ("H06_industryConcentrationTop1", "TOP1_CAP_SHARE"),
                                  ("H11_industryEarningsContext", "MEDIAN_earningsYieldProxy"), ("H12_industryValuationContext", "MEDIAN_bookToMarketProxy")):
                    value = feats.get(key, np.nan)
                    if np.isfinite(value):
                        v[name] = float(value)
                    else:
                        r[name] = "INDUSTRY_COHORT_MEMBER_MISSING_INPUT"
                c = eligible[ind]
                t126 = np.array([past.get(m, {}).get("trail126", np.nan) for m in c["members"]], float)
                if c["capWeights"] is not None and np.isfinite(t126).all():
                    cw = math.fsum(c["capWeights"][m] * past[m]["trail126"] for m in c["members"])
                    v["H08_equalVsCapWeightIndustry"] = float(np.mean(t126) - cw)
                else:
                    r["H08_equalVsCapWeightIndustry"] = "INDUSTRY_COHORT_MEMBER_MISSING_INPUT"
                peers = S.peers_of(stock_cohorts.get((date, ind)), t)
                loo = TF.loo_industry_momentum(t, peers, trail, cap_of) if peers else None
                if loo is not None:
                    v["A09_industryRelativeMomentum126"] = float(loo)
                else:
                    r["A09_industryRelativeMomentum126"] = "INDUSTRY_COHORT_MEMBER_MISSING_INPUT"
                eligible_rows.append({"date": date, "industry": ind, "ticker": t, "bookToMarketProxy": vq_rows[t].get("bookToMarketProxy", np.nan)})
        if eligible_rows:
            ranked = S.within_industry_percentiles(pd.DataFrame(eligible_rows), columns=("bookToMarketProxy",))
            for row in ranked.itertuples():
                if np.isfinite(row.wi_bookToMarketProxy):
                    per[row.ticker]["B05_industryRelativeValue"] = float(row.wi_bookToMarketProxy)
        for t in members:
            if "B05_industryRelativeValue" not in per[t] and "B05_industryRelativeValue" not in per_reason[t]:
                per_reason[t]["B05_industryRelativeValue"] = ("INDUSTRY_COHORT_MEMBER_MISSING_INPUT" if "B01_bookToMarket" not in per[t] else "INSUFFICIENT_PEERS_WITH_VALUE")

        # ---- context: industries, breadth, concentration, market state --------------------------------------------------------------------------- #
        h01 = {ind: f["REL_MOM_126"] for ind, f in ind_values.items() if np.isfinite(f.get("REL_MOM_126", np.nan))}
        h01_by_date[date] = h01
        dispersion = float(np.std(list(h01.values()), ddof=0)) if len(h01) >= I.MIN_CROSS_SECTION else None
        a14 = [per[t].get("A14_ma200Distance") for t in members]
        measured = [x for x in a14 if x is not None]
        breadth = float(np.mean([x > 0 for x in measured])) if measured else None
        cap_finite = {t: c for t, c in cap_of.items() if np.isfinite(c) and c > 0}
        top2 = (sum(cap_finite.get(m, 0.0) for m in MEGA_CAPS) / sum(cap_finite.values())) if cap_finite and all(m in cap_finite for m in MEGA_CAPS) else None
        multiplier = state.get("riskMultiplier")
        ctx.append({"date": date, "members": len(members), "breadthMeasured": len(measured), "breadthUniverse": len(members), "industriesEligible": len(eligible),
                    "industriesWithRelMom": len(h01), "capMeasured": len(cap_finite), "marketStateStatus": state.get("status"),
                    "regime": KSS.regime_label(date), "trendAdverse": state.get("trendAdverse"), "volAdverse": state.get("volAdverse")})
        for t in members:
            v, r = per[t], per_reason[t]
            if dispersion is not None:
                v["H05_crossIndustryDispersion"] = dispersion
            else:
                r["H05_crossIndustryDispersion"] = "INSUFFICIENT_INDUSTRIES"
            if breadth is not None:
                v["H09_marketBreadth"] = breadth
            else:
                r["H09_marketBreadth"] = "NO_MEASURED_NAME"
            if top2 is not None:
                v["H10_marketConcentrationTop2"] = float(top2)
            else:
                r["H10_marketConcentrationTop2"] = "MARKET_CAP_UNAVAILABLE"
            if multiplier is not None:
                v["I01_kospiTrendVolState"] = float(multiplier)
            else:
                r["I01_kospiTrendVolState"] = "MARKET_STATE_DATA_INSUFFICIENT"

        # ---- B08: the sealed H2 contract, fed the same fields ------------------------------------------------------------------------------------- #
        s2_rows = []
        for t in members:
            v = per[t]
            s2_rows.append({"ticker": t, "industry": industry_of.get((date, t)), "isPreferredShare": inputs.is_preferred(t),
                            "priceAsOf": date if market.at(t, date) else None,
                            "positiveVolumeSessions20": int(v["E04_tradabilityGuard20"]) if "E04_tradabilityGuard20" in v else None,
                            "medianTradedValue60Krw": v.get("E03_capacityMedianTradedValue60"),
                            "fundamentalsAvailableFrom": per_avail[t].get("_filing"),
                            "bookToMarketProxy": v.get("B01_bookToMarket"), "earningsYieldProxy": v.get("B02_earningsYield"),
                            "netIncomeToAssets": v.get("C01_returnOnAssets"), "ocfToAssets": v.get("C05_ocfToAssets"),
                            "ocfImprovementToAssets": v.get("C14_ocfImprovement"), "relative126": v.get("A05_relative126"),
                            "downsideVol126": v.get("F02_downsideVol126"), "maxDrawdown252": v.get("F05_maxDrawdown252")})
        s2 = {rec["ticker"]: rec for rec in S2.cross_section(s2_rows, date)}
        for t in members:
            rec = s2[t]
            per[t]["_B08_state"] = rec["state"]
            flags = rec.get("confirmationFlags") or {}
            confirmed = all(flags.values()) if flags and len(flags) == len(S2.CONFIRMATION_FIELDS) else None
            if rec["state"] == "INELIGIBLE":
                per_reason[t]["B08_valueBusinessConfirmation"] = "S2_INELIGIBLE"
            elif rec["state"] == "MISSING_VALUE_INPUT":
                per_reason[t]["B08_valueBusinessConfirmation"] = "MISSING_VALUE_INPUT"
            elif rec["valuePercentile"] is None or flags is None or len(flags) != len(S2.CONFIRMATION_FIELDS) or not all(v is not None for v in flags.values()):
                per_reason[t]["B08_valueBusinessConfirmation"] = "CONFIRMATION_UNMEASURED"
            else:
                per[t]["B08_valueBusinessConfirmation"] = float(rec["valuePercentile"])
                per[t]["_B08_confirmed"] = 1.0 if confirmed else 0.0

        tiers = liquidity_tiers({t: per[t].get("E03_capacityMedianTradedValue60", np.nan) for t in members})
        for t in members:
            rows.append({"date": date, "ticker": t, "pitSnapshotDate": inputs.memberships.on(date)["date"], "industry": industry_of.get((date, t)),
                         "industryMembershipStatus": status_of.get((date, t)), "industryEligible": industry_of.get((date, t)) in eligible,
                         "liquidityTier": tiers[t], "isPreferredShare": inputs.is_preferred(t), "tradableAtSignal": bool(market.at(t, date)),
                         "b08State": per[t].get("_B08_state"), "b08Confirmed": per[t].get("_B08_confirmed", np.nan),
                         "filingAvailableFrom": per_avail[t].get("_filing")})
            vals.append(per[t])
            reas.append(per_reason[t])
            avails.append({k: x for k, x in per_avail[t].items() if not k.startswith("_")})

    rows_df = pd.DataFrame(rows)
    ids = [f for f in C.CATALOGUE]
    values = pd.DataFrame([{k: row.get(k, np.nan) for k in ids} for row in vals], index=rows_df.index).astype(float)
    reasons = pd.DataFrame([{k: ("" if np.isfinite(vals[i].get(k, np.nan)) else row.get(k, "REASON_NOT_RECORDED")) for k in ids} for i, row in enumerate(reas)],
                           index=rows_df.index)
    available = pd.DataFrame([{k: row.get(k) for k in ids} for row in avails], index=rows_df.index)
    context = pd.DataFrame(ctx)
    matrix = Matrix(rows_df, values, reasons, available, context, inputs.identity)
    matrix = add_temporal_features(matrix, days, h01_by_date)
    return matrix


def add_temporal_features(matrix, days, h01_by_date):
    """B06, B07 and H07 read ONLY the ticker's (or the market's) own earlier matrix rows."""
    rows, values, reasons = matrix.rows, matrix.values, matrix.reasons
    order = rows.sort_values(["ticker", "date"])
    position = {d: int(days.searchsorted(pd.Timestamp(d), side="left")) for d in rows.date.unique()}
    for ticker, group in order.groupby("ticker", sort=True):
        idx, dates = list(group.index), list(group.date)
        b01 = values.loc[idx, "B01_bookToMarket"].to_numpy(float)
        for k, i in enumerate(idx):
            history = b01[max(0, k - 156):k]
            finite = history[np.isfinite(history) & (history > 0)]
            if np.isfinite(b01[k]) and b01[k] > 0 and len(finite) >= 104:
                values.at[i, "B06_ownHistoryValuation"] = float(math.log(b01[k] / float(np.median(finite))))
            else:
                reasons.at[i, "B06_ownHistoryValuation"] = "INSUFFICIENT_OWN_HISTORY" if len(finite) < 104 else "INPUT_NOT_STATED_OR_UNDEFINED_RATIO"
            target = position[dates[k]] - 126
            j = next((m for m in range(k - 1, -1, -1) if position[dates[m]] <= target), None)
            if j is not None and np.isfinite(b01[k]) and b01[k] > 0 and np.isfinite(b01[j]) and b01[j] > 0:
                values.at[i, "B07_valuationChange126"] = float(math.log(b01[k] / b01[j]))
            else:
                reasons.at[i, "B07_valuationChange126"] = "INSUFFICIENT_OWN_HISTORY" if j is None else "INPUT_NOT_STATED_OR_UNDEFINED_RATIO"
    grid = sorted(h01_by_date)
    h07 = {}
    for k, date in enumerate(grid):
        if k < 4:
            continue
        now, then = h01_by_date[date], h01_by_date[grid[k - 4]]
        common = sorted(set(now) & set(then))
        if len(common) >= I.MIN_CROSS_SECTION:
            h07[date] = _spearman([now[c] for c in common], [then[c] for c in common])
    for i, date in rows.date.items():
        if h07.get(date) is not None:
            values.at[i, "H07_leadershipPersistence"] = h07[date]
        else:
            reasons.at[i, "H07_leadershipPersistence"] = "INSUFFICIENT_INDUSTRIES"
    for col in values.columns:
        mask = values[col].notna()
        reasons.loc[mask, col] = ""
    return matrix
