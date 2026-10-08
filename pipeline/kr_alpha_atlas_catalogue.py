"""kr-alpha-atlas Phase B — which registry features this change computes, from which existing code, and with what definition.

The registry (`research_specs/kr-alpha-atlas-registry-v1.json`) says what each feature MEANS. This catalogue says what the code COMPUTES, so the two can
be compared by a test and a reader can see every place an implemented definition is narrower than the registry text. A definition written here is
fixed by this change, before any outcome has been read; nothing in it was chosen by looking at a return.

`reuses` names the existing function that produces the number. Where this change adds arithmetic of its own it says so (`adds`), and where the
implemented definition differs from the registry's wording it says how (`deviation`). A feature the registry lists but that is not here is reported by
the readiness report with its registry status and the reason it was not computed.
"""
from __future__ import annotations

CONTRACT = "KR_ALPHA_ATLAS_CATALOGUE_V1"

# group -> where the number comes from
BARS, PRICE, SEALED_VQ, ACCOUNTING, INDUSTRY, CONTEXT, TEMPORAL, B08, CALENDAR = (
    "KRX_BARS_AS_TRADED", "REPLAY_PRICE_PAST_ONLY", "SEALED_VALUE_QUALITY_CATALYST", "DART_PIT_ACCOUNTING", "PIT_INDUSTRY_COHORT", "DATE_LEVEL_CONTEXT",
    "OWN_PAST_ROWS", "KR_ALPHA_SIGNAL_V2", "DATED_CALENDAR")


def _f(group, definition, reuses, window=None, deviation=None, adds=None, state=False):
    return {"group": group, "definition": definition, "reuses": list(reuses), "windowSessions": window, "deviationFromRegistryText": deviation,
            "addsArithmetic": adds, "categorical": state}


CATALOGUE = {
    # ---- A: price, momentum, reversal (replay-v16 Close: split-continuous, forward-accumulated total return; past-only windows ending at T) ---- #
    "A01_return1d": _f(PRICE, "Close[T] / Close[T-1] - 1", [], 2, adds="one division"),
    "A02_return5d": _f(PRICE, "Close[T] / Close[T-5] - 1", [], 6, adds="one division"),
    "A03_return21d": _f(PRICE, "Close[T] / Close[T-21] - 1", ["kr_alpha_tournament_features.derived_price_features"], 22),
    "A04_return63d": _f(PRICE, "Close[T] / Close[T-63] - 1", ["kr_alpha_tournament_features.derived_price_features"], 64),
    "A05_relative126": _f(SEALED_VQ, "stock 126-session return minus 069500.KS 126-session return", ["kr_value_quality_catalyst.feature_at"], 127),
    "A06_return252d": _f(PRICE, "Close[T] / Close[T-252] - 1", [], 253, adds="one division"),
    "A07_momentum12_1": _f(SEALED_VQ, "Close[T-21] / Close[T-252] - 1", ["kr_value_quality_catalyst.feature_at"], 253),
    "A08_momentum6": _f(PRICE, "production momentum_6m: Close[T] / Close[T-125] - 1", ["longterm.momentum_6m"], 126),
    "A09_industryRelativeMomentum126": _f(INDUSTRY, "stock trailing-126 return minus the cap-weighted trailing-126 return of its industry PEERS (stock excluded)",
                                          ["kr_alpha_tournament_features.loo_industry_momentum"], 127),
    "A10_residualMomentum126": _f(PRICE, "stock 126-session return minus beta252 x 069500.KS 126-session return (beta over the 252 sessions ending at T)",
                                  ["kr_alpha_tournament_features.derived_price_features"], 253, adds="one subtraction",
                                  deviation="market residual only; the registry text also names an industry component, which would need a daily cohort return series this matrix does not carry"),
    "A11_distance52wHigh": _f(PRICE, "Close[T] / max(Close over 252 sessions) - 1", ["kr_alpha_tournament_features.derived_price_features"], 252),
    "A12_momentumPersistence": _f(PRICE, "share of the last 12 non-overlapping 21-session windows whose stock return exceeded 069500.KS", [], 253,
                                  adds="12 window comparisons"),
    "A13_momentumAcceleration21": _f(PRICE, "21-session return ending T minus the 21-session return ending T-21", [], 43, adds="one subtraction"),
    "A14_ma200Distance": _f(PRICE, "Close[T] / mean(Close, 200) - 1", ["kr_alpha_tournament_features.derived_price_features"], 200),
    # ---- B: value ---- #
    "B01_bookToMarket": _f(SEALED_VQ, "(assets - liabilities) / market cap, whole-entity numerators over the issue's cap", ["kr_value_quality_catalyst.feature_at"]),
    "B02_earningsYield": _f(SEALED_VQ, "TTM net income / market cap", ["kr_value_quality_catalyst.feature_at"]),
    "B03_ocfYield": _f(SEALED_VQ, "TTM operating cash flow / market cap", ["kr_value_quality_catalyst.feature_at"]),
    "B04_freeCashFlowYield": _f(ACCOUNTING, "(TTM operating cash flow - |TTM capex|) / market cap", ["dart_derive.trailing_twelve_months"], adds="one division"),
    "B05_industryRelativeValue": _f(INDUSTRY, "within-industry percentile of B01 among the finite members of the date x industry cohort",
                                    ["kr_stock_within_industry_anatomy.within_industry_percentiles"]),
    "B06_ownHistoryValuation": _f(TEMPORAL, "ln(B01 now / median of the ticker's own B01 over the previous 156 weekly rows), at least 104 finite rows", [],
                                  adds="a median over the ticker's own earlier matrix rows"),
    "B07_valuationChange126": _f(TEMPORAL, "ln(B01 now / B01 on the signal date 126 sessions earlier)", [], 127, adds="one log ratio"),
    "B08_valueBusinessConfirmation": _f(B08, "H2: cheap within industry (top tercile of the mean of two within-industry value percentiles) AND net income, OCF and OCF improvement all positive; "
                                             "stored as the value percentile, with the confirmation flag beside it",
                                        ["kr_alpha_signal_v2.cross_section"], state=True),
    # ---- C: profitability and accounting quality ---- #
    "C01_returnOnAssets": _f(SEALED_VQ, "TTM net income / assets", ["kr_value_quality_catalyst.feature_at"]),
    "C02_returnOnEquity": _f(ACCOUNTING, "TTM net income / equity, undefined (missing) on non-positive equity", ["dart_derive.derive_fields"]),
    "C03_operatingMargin": _f(ACCOUNTING, "TTM operating income / TTM revenue", ["dart_derive.derive_fields"]),
    "C04_profitMargin": _f(ACCOUNTING, "TTM net income / TTM revenue", ["dart_derive.derive_fields"]),
    "C05_ocfToAssets": _f(SEALED_VQ, "TTM operating cash flow / assets", ["kr_value_quality_catalyst.feature_at"]),
    "C06_cashConversion": _f(ACCOUNTING, "TTM operating cash flow / TTM net income, ONLY where net income is positive", ["accounting_quality.derive_kr_fields"],
                             adds="a positive-denominator guard: a cash-conversion ratio on a loss has no economic reading"),
    "C07_negativeAccruals": _f(SEALED_VQ, "(TTM OCF - TTM net income) / assets", ["kr_value_quality_catalyst.feature_at"]),
    "C08_netIncomeMinusOcf": _f(SEALED_VQ, "the sign-flipped C07: reported once, as an alias", ["kr_value_quality_catalyst.feature_at"], adds="a sign flip"),
    "C09_assetGrowth": _f(ACCOUNTING, "assets over assets at the same report stage one year earlier, minus 1 (prior must be positive)", ["accounting_quality.derive_kr_fields"]),
    "C10_liabilityGrowth": _f(ACCOUNTING, "liabilities over liabilities at the same stage a year earlier, minus 1 (prior must be positive)", ["accounting_quality.derive_kr_fields"]),
    "C11_shareDilution": _f(ACCOUNTING, "DART share count (net of treasury, as filed or carried forward from an EARLIER filing) over the same stage a year earlier, minus 1",
                            ["accounting_quality.derive_kr_fields", "dart_derive.carried_shares"]),
    "C12_profitabilityPersistence": _f(ACCOUNTING, "standard deviation of the operating margin over the ticker's last 4 visible same-basis filings (lower is steadier)",
                                       ["accounting_quality.operating_margin_stability", "dart_derive.derive_fields"]),
    "C14_ocfImprovement": _f(SEALED_VQ, "(TTM OCF - prior-year TTM OCF) / assets", ["kr_value_quality_catalyst.feature_at"]),
    "C15_capexIntensity": _f(ACCOUNTING, "TTM capex / TTM revenue, revenue positive", ["accounting_quality.derive_kr_fields"]),
    # ---- D: volume and trading activity (KRX bars, as traded; volume split-continuous, traded value split-invariant) ---- #
    "D01_volumeSurge5_60": _f(BARS, "mean volume over 5 sessions / mean volume over 60 sessions (raw ratio)", ["liquidity_attention.volume_ratio"], 60),
    "D02_logVolumeShock60": _f(BARS, "ln(volume[T] / mean volume over 60 sessions): magnitude-preserving", ["liquidity_attention.log_volume_shock"], 60),
    "D03_tradingValueShock5_60": _f(BARS, "ln(mean traded value over 5 sessions / mean over 60)", ["kr_alpha_tournament_features.liquidity_features"], 60,
                                    adds="vectorised rolling means, tested equal to the sealed function"),
    "D04_shockPersistence5d": _f(BARS, "number of the last 5 sessions whose log volume shock exceeded 1.0", ["liquidity_attention.shock_persistence"], 64),
    "D05_turnoverToMarketCap60": _f(BARS, "mean over 60 sessions of volume / listed shares, in percent", ["liquidity_attention.turnover"], 60,
                                    adds="a 60-session mean of the daily turnover"),
    "D06_priceVolumeDivergence": _f(BARS, "20-session rolling correlation of the volume z-score with the same-day return", ["liquidity_attention.volume_price_divergence"], 80),
    "D07_volumePriceAlignment": _f(BARS, "log volume shock signed by the day's own price direction, at T", ["liquidity_attention.volume_price_alignment"], 61),
    "D08_abnormalVolumeUpClose": _f(BARS, "days in the last 21 sessions with a log volume shock above 1.0 AND a close in the top fifth of the day's range",
                                    ["liquidity_attention.close_near_high_after_shock"], 80, adds="a 21-session count of a daily indicator that is never a false 0"),
    "D09_abnormalVolumeDownClose": _f(BARS, "as D08 with a close in the bottom fifth of the range", ["liquidity_attention.close_near_low_after_shock"], 80,
                                      adds="a 21-session count of a daily indicator that is never a false 0"),
    "D10_liquidityAcceleration": _f(BARS, "ln(mean traded value over 20 sessions / mean over 120)", [], 120, adds="one log ratio"),
    "D11_accumulationDistributionProxy": _f(BARS, "sum of (2 x close-location - 1) x volume over 20 sessions / sum of volume: an OHLCV PROXY, not investor flow",
                                            ["liquidity_attention.close_location_value"], 20, adds="a volume-weighted mean of the close location"),
    # ---- E: liquidity and microstructure ---- #
    "E01_amihudIlliquidity60": _f(BARS, "ln of the mean over 60 sessions of |return| / KRW traded value (split-adjusted return, as-traded traded value)",
                                  ["liquidity_attention.amihud_illiquidity_proxy"], 61),
    "E02_logAdv60": _f(SEALED_VQ, "log1p(mean KRW traded value over 60 sessions)", ["kr_value_quality_catalyst.feature_at"], 60),
    "E03_capacityMedianTradedValue60": _f(BARS, "median KRW traded value over 60 sessions (a capacity constraint, never an alpha input)", [], 60, adds="a rolling median"),
    "E04_tradabilityGuard20": _f(BARS, "number of the last 20 sessions with positive volume (eligibility only)", [], 20, adds="a count"),
    "E05_highLowSpreadProxy": _f(BARS, "Corwin-Schultz high-low spread estimate averaged over 20 sessions (a COST proxy, never alpha)", [], 21, adds="the published estimator"),
    "E06_volatilityConditionalOnVolume": _f(BARS, "abnormal true range (vs its 20-session mean) x the 5/60 volume ratio", ["liquidity_attention.range_times_volume"], 80),
    "E07_suspensionStaleRisk": _f(BARS, "number of the last 20 sessions inside the ticker's listed span without a traded row (eligibility only)", [], 20, adds="a count"),
    # ---- F: risk ---- #
    "F01_totalVolatility63": _f(PRICE, "annualised standard deviation of 63 daily returns", ["kr_alpha_tournament_features.derived_price_features"], 64),
    "F02_downsideVol126": _f(SEALED_VQ, "annualised semideviation about zero over 126 sessions", ["kr_value_quality_catalyst.feature_at"], 127),
    "F03_beta252": _f(PRICE, "OLS beta to 069500.KS over 252 daily returns", ["kr_alpha_tournament_features.derived_price_features"], 253),
    "F04_idiosyncraticVol": _f(PRICE, "annualised standard deviation of the residual of the stock's daily return on 069500.KS over 252 returns", [], 253,
                               adds="an OLS residual standard deviation",
                               deviation="market residual only; the registry text also names an industry factor (see A10)"),
    "F05_maxDrawdown252": _f(PRICE, "minimum of Close / running maximum - 1 over 252 sessions", ["kr_alpha_tournament_features.derived_price_features"], 252),
    "F06_crashExposure": _f(PRICE, "downside beta: OLS beta to 069500.KS on the sessions when 069500.KS fell, at least 30 such sessions in 252", [], 253,
                            adds="a conditional OLS beta"),
    "F07_benchmarkCorrelation252": _f(PRICE, "correlation of daily returns with 069500.KS over 252 returns", [], 253, adds="a correlation"),
    # ---- H: industry and cross-sectional structure ---- #
    "H01_industryRelMom126": _f(INDUSTRY, "cap-weighted industry trailing-126 return minus 069500.KS", ["kr_industry_anatomy.industry_features"], 127),
    "H02_industryRelMom63": _f(INDUSTRY, "as H01 over 63 sessions", ["kr_industry_anatomy.industry_features"], 64),
    "H03_industryBreadthAboveMA126": _f(INDUSTRY, "share of the industry's members above their 126-session mean", ["kr_industry_anatomy.industry_features"], 127),
    "H04_withinIndustryDispersion126": _f(INDUSTRY, "dispersion of the members' trailing-126 returns", ["kr_industry_anatomy.industry_features"], 127),
    "H05_crossIndustryDispersion": _f(CONTEXT, "standard deviation of H01 across the eligible industries on the date", ["kr_industry_anatomy.industry_features"], 127,
                                      adds="one standard deviation per date"),
    "H06_industryConcentrationTop1": _f(INDUSTRY, "largest member's share of its industry cohort's cap", ["kr_industry_anatomy.industry_features"]),
    "H07_leadershipPersistence": _f(TEMPORAL, "Spearman rank correlation of the industries' H01 on the date and four signal dates earlier, at least 8 common industries", [],
                                    adds="one rank correlation per date"),
    "H08_equalVsCapWeightIndustry": _f(INDUSTRY, "equal-weight minus cap-weight trailing-126 return of the industry's members", ["kr_industry_anatomy.industry_features"], 127,
                                       adds="an equal-weight mean beside the sealed cap-weighted one"),
    "H09_marketBreadth": _f(CONTEXT, "share of measured PIT Top120 names above their 200-session mean; measured names and the universe size are published with it",
                            ["kr_alpha_tournament_features.derived_price_features"], 200, adds="a share with its denominator"),
    "H10_marketConcentrationTop2": _f(CONTEXT, "Samsung Electronics + SK Hynix cap over the cap of the PIT Top120 names with a market cap that day", [], adds="a share"),
    "H11_industryEarningsContext": _f(INDUSTRY, "median earnings yield of the industry cohort", ["kr_industry_anatomy.industry_features"]),
    "H12_industryValuationContext": _f(INDUSTRY, "median book-to-market of the industry cohort", ["kr_industry_anatomy.industry_features"]),
    # ---- I, J ---- #
    "I01_kospiTrendVolState": _f(CONTEXT, "the sealed market-risk overlay's multiplier on 069500.KS: 1.0 / 0.7 / 0.4 from the 200-session trend and 63-session volatility",
                                 ["kr_market_risk_overlay.state_at"], 201),
    "J01_periodicFilingEvent": _f(ACCOUNTING, "1 if the latest visible DART filing became visible within the last 5 KR sessions, else 0; days since that visibility alongside",
                                  ["alpha_opportunity_features.visible_filings"], adds="a session count between two dates"),
    "J05_shortSellingRegime": _f(CALENDAR, "0 normal, 1 COVID ban, 2 structural ban: a dated regulatory calendar", ["kr_short_selling.regime_label"],
                                 adds="an ordinal code"),
}

# Features whose number is computed by this change only because a registered Level-2 baseline or Level-3 interaction needs it, or because the sealed
# function that produces a neighbour returns it for free. They are ALREADY_TESTED in the registry: this change reads no outcome for them and does not
# re-run any study. Everything else ALREADY_TESTED in the registry is reported as referenced.
COMPUTED_FOR_BASELINES = ("A05_relative126", "A07_momentum12_1", "A09_industryRelativeMomentum126", "B01_bookToMarket", "B02_earningsYield",
                          "B05_industryRelativeValue", "C01_returnOnAssets", "C05_ocfToAssets", "E02_logAdv60", "H01_industryRelMom126", "I01_kospiTrendVolState")

# Registry features the matrix does not carry as a column, and the stated reason (the readiness report prints these verbatim).
NOT_A_MATRIX_COLUMN = {
    "F08_bookConcentration": "PORTFOLIO_LAYER_ONLY: a property of a 0-5 name book, not of a name on a date",
}


def implemented_ids():
    return sorted(CATALOGUE)
