"""Turning a rank into a number: alpha percentile -> expected excess return.

``alpha``, ``rawAlpha`` and ``alphaPercentile`` are cross-sectional *ranks*. They
have never been expected returns and this module does not change that. What it
does is ask the historical out-of-sample ledger an empirical question:

    When this model, run without seeing the future, put a name in the 90-95th
    alpha percentile in Korea, what did that name actually do against KOSPI 200
    over the next 126 sessions?

The answer is a measured distribution, not a transformation of the score. If the
ledger has no answer for a bucket, the bucket has no expected return — it is not
interpolated from the score.

FOUR THINGS THAT WOULD MAKE THAT NUMBER A LIE, AND WHAT IS DONE ABOUT THEM
--------------------------------------------------------------------------
*Hundreds of names on one day are not hundreds of independent facts.* Every
date's cross-section collapses to a single observation before anything is
averaged (``kelly_portfolio._clustered_date_returns``).

*Overlapping 126-day windows are autocorrelated.* Daily-sampled forward returns
behave like an MA(h-1) process, so the standard error uses a Bartlett-kernel
Newey-West estimator with lag = horizon-1, and the resulting effective sample
size — not the row count — drives shrinkage.

*A thin bucket will show a spectacular mean by luck.* Estimates shrink toward
zero as ``eff / (eff + prior_strength)``, so a 3-date bucket contributes almost
nothing regardless of how good it looks.

*Buckets can come out non-monotone by noise.* Weighted isotonic regression
repairs the ordering rather than shipping a calibration that says the 80-90th
percentile beats the 95-100th — but only once ordering has been *established*.
Isotonic regression is a monotone fit; run on five noisy points it will always
return a tidy ladder, so running it unconditionally converts "this score does
not order returns" into "this score orders returns cleanly". It is therefore
gated on ``_ordering_evidence`` and never allowed to manufacture a ladder.

*A bucket's excess return over the benchmark is not the model's edge.* This is
the defect that matters most and the one that is easiest to miss. ``excessReturn``
is measured against a regional benchmark, so it contains two very different
things added together:

    excess(bucket) = (universe - benchmark) + (bucket - universe)
                     \_______  ________/    \________  _______/
                             \/                      \/
                     universe carry            alpha spread
                     beta / size / composition  what the RANKING did

Only the second term is evidence about the selection function. The first is
what every name in the replay universe did against the index — an equal-weight
versus cap-weight tilt, a small-cap premium, a decade that happened to be kind
to the constituents that survived into the universe list. It is large: on the
2013-2021 fixture the universe carry is +2.4%/126D in KR and +6.0%/126D in US,
which is most or all of what the raw bucket table reports as "alpha".

Publishing the level as the expected return capitalises that carry into a Kelly
fraction, and it is precisely the component with no reason to persist and no
connection to the ranking. So the level stays published for transparency and
the *spread* is what leaves this module as the expected excess return.

And the whole result is then discounted, because backtest evidence is not live
evidence — see ``evidence_weight``.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import kelly_portfolio as KP
from . import pit_data
from . import probability_calibration as probability_mod
from .historical_outcomes import horizon_frame

DEFAULT_BUCKETS = (0, 60, 80, 90, 95, 100)

# Why 0.6 and not 1.0, and not 0.
#
# A historical replay is genuinely out-of-sample in time: on 2019-05-15 the
# engine could not see 2019-05-16. That is worth a great deal and is why the
# weight is not near zero.
#
# But it is not worth as much as prospective paper evidence, for a reason no
# amount of care inside the replay can fix: the *model specification itself* was
# chosen by people who already lived through 2019. Factor choice, sleeve
# weights, the entry-state ladder and the risk metrics were all authored with
# hindsight about which decade happened. Prospective evidence is the only kind
# free of that, so it anchors at 1.0 and history anchors below it.
#
# 0.6 sits mid-range in the 0.5-0.8 band: high enough that a decade of clean OOS
# history dominates an empty prospective ledger (which is the entire point of
# this work), low enough that a year of real prospective evidence can overtake
# it. Every known defect then multiplies it further down.
HISTORICAL_BASE_WEIGHT = 0.6
PROSPECTIVE_WEIGHT = 1.0
MIN_HISTORICAL_WEIGHT = 0.15

# Ordering evidence threshold.
#
# The question is not "is the top bucket's return significantly positive" — in a
# rising universe it always is. It is "does a higher alpha rank earn more than a
# lower one", which is a spread and is answered by a HAC t-statistic on the
# top-minus-bottom series or on the per-date rank IC.
#
# The threshold is calibrated by simulation, not taken from a table, because the
# statistic is a HAC mean over overlapping windows and its finite-sample size is
# not the textbook one. Simulating the null directly — a cross-section with a
# common market factor, 126-day forward returns sampled weekly, and an alpha rank
# that is pure noise — gives the realised rejection rate of this exact gate:
#
#     threshold      n=200 dates    n=374 dates
#     t >= 1.64          7.6%            6.4%
#     t >= 1.96          5.0%            3.6%
#     t >= 2.30          2.8%            2.0%
#
# 1.96 lands closest to an honest 5%. It matters that the statistic is a SPREAD:
# the common market factor cancels between the top and bottom buckets, which is
# what keeps the estimator well behaved. The same test on a bucket's *level*
# over-rejects at 15-25% however the bandwidth is set, which is one more reason
# the level is not what this module publishes as an expected return.
DEFAULT_MIN_ORDERING_T = 1.96

# Ordering cannot be established from a handful of independent windows however
# large the t-statistic looks. A decade of weekly 126-day cross-sections carries
# an HAC-effective sample in the tens, and below this there is nothing to test.
DEFAULT_MIN_ORDERING_EFFECTIVE_DATES = 12

# A date needs a real cross-section before a rank correlation on it means
# anything; below this the IC is dominated by the few names that happen to exist.
MIN_NAMES_FOR_RANK_IC = 8

# Discount factors applied multiplicatively. Each is a named, checkable defect.
PENALTY = {
    "survivorship_unresolved": 0.80,
    "macro_revised_history": 0.95,
    "fundamentals_not_point_in_time": 0.90,
    "regime_concentration": 0.85,
    "sector_concentration": 0.90,
    "fold_instability": 0.70,
    "low_pit_coverage": 0.75,
}


def _bucket_label(lo, hi) -> str:
    return f"{lo:g}-{hi:g}"


def _summary_stats(values: pd.Series, horizon: int) -> dict:
    """Median and hit ratio over all dates; drawdown and CVaR over a
    non-overlapping subsample.

    Daily- or weekly-sampled 126-day forward returns overlap heavily. Averaging
    them is fine — overlap inflates the variance of the estimate, not the
    estimate. Chaining them into an equity curve is not fine: the same market
    move gets compounded dozens of times and the resulting drawdown is an
    artifact of the sampling, not of the strategy.
    """
    if not len(values):
        return {"median": None, "hitRatio": None, "mdd": None, "cvar95": None,
                "nonOverlappingDates": 0}
    arr = values.to_numpy(dtype=float)
    thinned: list[float] = []
    chosen: list[pd.Timestamp] = []
    for stamp, value in values.items():
        if not chosen or stamp >= chosen[-1] + pd.offsets.BDay(horizon):
            chosen.append(stamp)
            thinned.append(float(value))
    mdd = cvar = None
    if len(thinned) >= 3:
        block = np.asarray(thinned, dtype=float)
        equity = np.cumprod(1.0 + block)
        drawdown = equity / np.maximum.accumulate(equity) - 1.0
        tail_n = max(1, int(math.ceil(len(block) * 0.05)))
        mdd = round(float(np.min(drawdown)), 6)
        cvar = round(float(np.mean(np.sort(block)[:tail_n])), 6)
    return {
        "median": round(float(np.median(arr)), 6),
        "hitRatio": round(float(np.mean(arr > 0)), 4),
        "mdd": mdd,
        "cvar95": cvar,
        "nonOverlappingDates": len(thinned),
    }


def _universe_baseline(region_frame: pd.DataFrame, horizon: int) -> dict:
    """Per-date cross-sectional mean excess of the WHOLE region universe.

    This is the part of a bucket's excess return that the selection function did
    not produce. On a date when every name in the replay cross-section beat the
    index by 6%, a bucket that also beat it by 6% demonstrated nothing about the
    ranking, and a Kelly fraction sized on that 6% is sized on a beta and
    composition tilt that the alpha model neither predicted nor controls.
    """
    gross = region_frame.groupby("date")["excessReturn"].mean().dropna().sort_index()
    net_raw = region_frame.groupby("date")["costAdjustedExcessReturn"].mean().dropna().sort_index()
    net = net_raw if len(net_raw) else gross
    stats = KP._newey_west_stats(gross, horizon) if len(gross) else None
    return {
        "grossSeries": gross,
        "netSeries": net,
        "meanExcessPct": round(float(stats["mean"]) * 100, 3) if stats else None,
        "standardErrorPct": (round(float(stats["se"]) * 100, 4)
                             if stats and stats.get("se") is not None else None),
        "effectiveDates": int(stats["effectiveDates"]) if stats else 0,
        "uniqueDates": int(stats["uniqueDates"]) if stats else 0,
        "shareOfDatesPositive": round(float((gross > 0).mean()), 4) if len(gross) else None,
        "meaningKo": ("재현 유니버스 전체가 벤치마크 대비 낸 초과수익입니다. 선정 모델의 성과가 "
                      "아니라 유니버스 구성·베타·기간 효과이며, 기대수익에서 분리합니다."),
    }


def _rank_ic_series(region_frame: pd.DataFrame,
                    min_names: int = MIN_NAMES_FOR_RANK_IC) -> pd.Series:
    """Per-date Spearman correlation between alpha rank and realised excess."""
    rows: dict = {}
    for date, group in region_frame.groupby("date", sort=True):
        pair = group[["alphaPercentile", "excessReturn"]].dropna()
        if len(pair) < min_names or pair["alphaPercentile"].nunique() < 3:
            continue
        ic = pair["alphaPercentile"].corr(pair["excessReturn"], method="spearman")
        if pd.notna(ic):
            rows[pd.Timestamp(date)] = float(ic)
    return pd.Series(rows, dtype=float).sort_index()


def _t_stat(stats: dict | None) -> float | None:
    if not stats or not stats.get("se"):
        return None
    return float(stats["mean"]) / float(stats["se"])


def _ordering_evidence(region_frame: pd.DataFrame, horizon: int, *,
                       min_t: float = DEFAULT_MIN_ORDERING_T,
                       min_effective_dates: int = DEFAULT_MIN_ORDERING_EFFECTIVE_DATES) -> dict:
    """Did a higher alpha RANK actually earn more than a lower one?

    Two independent readings of the same question, both HAC-corrected on the
    date-clustered series:

    * top bucket minus bottom bucket, per date — the spread the ladder claims;
    * mean per-date rank IC — whether the whole ordering, not just the extremes,
      lines up with realised returns.

    Ordering is established when either statistic clears ``min_t`` *and* the
    other agrees in sign. One significant reading with the other pointing the
    opposite way is a subsample artefact, not an ordering.
    """
    labels = sorted(region_frame["bucket"].dropna().unique(),
                    key=lambda b: float(b.split("-")[0]))
    top_bottom_stats = None
    if len(labels) >= 2:
        hi = region_frame[region_frame["bucket"] == labels[-1]].groupby("date")["excessReturn"].mean()
        lo = region_frame[region_frame["bucket"] == labels[0]].groupby("date")["excessReturn"].mean()
        spread = (hi - lo).dropna().sort_index()
        if len(spread):
            top_bottom_stats = KP._newey_west_stats(spread, horizon)

    ic_series = _rank_ic_series(region_frame)
    ic_stats = KP._newey_west_stats(ic_series, horizon) if len(ic_series) else None

    t_spread = _t_stat(top_bottom_stats)
    t_ic = _t_stat(ic_stats)
    mean_spread = float(top_bottom_stats["mean"]) if top_bottom_stats else None
    mean_ic = float(ic_stats["mean"]) if ic_stats else None

    spread_eff = int(top_bottom_stats["effectiveDates"]) if top_bottom_stats else 0
    ic_eff = int(ic_stats["effectiveDates"]) if ic_stats else 0

    by_spread = bool(t_spread is not None and t_spread >= min_t
                     and spread_eff >= min_effective_dates
                     and (mean_ic is None or mean_ic > 0))
    by_ic = bool(t_ic is not None and t_ic >= min_t
                 and ic_eff >= min_effective_dates
                 and (mean_spread is None or mean_spread > 0))
    established = bool(by_spread or by_ic)
    enough_sample = bool(max(spread_eff, ic_eff) >= min_effective_dates)

    if len(labels) < 2:
        reason = "SINGLE_BUCKET_NO_ORDERING_TESTABLE"
    elif established:
        reason = "TOP_MINUS_BOTTOM_SIGNIFICANT" if by_spread else "RANK_IC_SIGNIFICANT"
    elif not enough_sample:
        reason = "INSUFFICIENT_EFFECTIVE_DATES_TO_TEST_ORDERING"
    else:
        reason = "ORDERING_NOT_DISTINGUISHABLE_FROM_NOISE"

    return {
        "established": established,
        "reason": reason,
        "minTStat": float(min_t),
        "minEffectiveDates": int(min_effective_dates),
        "topMinusBottomPct": round(mean_spread * 100, 3) if mean_spread is not None else None,
        "topMinusBottomTStat": round(t_spread, 3) if t_spread is not None else None,
        "topMinusBottomEffectiveDates": (int(top_bottom_stats["effectiveDates"])
                                         if top_bottom_stats else 0),
        "topBucket": labels[-1] if labels else None,
        "bottomBucket": labels[0] if len(labels) >= 2 else None,
        "meanRankIC": round(mean_ic, 5) if mean_ic is not None else None,
        "rankICTStat": round(t_ic, 3) if t_ic is not None else None,
        "rankICDates": int(len(ic_series)),
        "rankICEffectiveDates": int(ic_stats["effectiveDates"]) if ic_stats else 0,
        "policyKo": ("순위가 수익을 정렬했다는 증거가 없으면 버킷 사다리를 발표하지 않고 "
                      "Kelly 기대수익으로도 쓰지 않습니다. 등온회귀는 언제나 단조 결과를 만들기 "
                      "때문에, 정렬 증거 없이 돌리면 잡음이 사다리로 보입니다."),
    }


def _fold_stability(frame: pd.DataFrame, folds: int = 4) -> dict:
    """Does the bucket's edge survive being cut into time slices?

    An edge concentrated in one lucky window is a different animal from one that
    shows up in every slice, even if both have the same full-sample mean. Sign
    agreement across slices is the cheapest honest test of that.
    """
    dates = sorted(frame["date"].unique())
    if len(dates) < folds * 2:
        return {"folds": 0, "signAgreement": None, "stable": None, "sliceMeans": []}
    chunks = np.array_split(np.array(dates), folds)
    means = []
    for chunk in chunks:
        subset = frame[frame["date"].isin(set(chunk))]
        if subset.empty:
            continue
        means.append(float(subset.groupby("date")["value"].mean().mean()))
    if not means:
        return {"folds": 0, "signAgreement": None, "stable": None, "sliceMeans": []}
    overall = float(np.mean(means))
    agree = float(np.mean([np.sign(m) == np.sign(overall) for m in means])) if overall else 0.0
    return {
        "folds": len(means),
        "signAgreement": round(agree, 3),
        "stable": bool(agree >= 0.75),
        "sliceMeans": [round(m, 6) for m in means],
    }


def _concentration(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame or frame[column].isna().all():
        return None
    counts = frame[column].fillna("UNKNOWN").value_counts(normalize=True)
    return float(counts.iloc[0]) if len(counts) else None


def evidence_weight(*, pit_coverage: float | None, survivorship_risk: str,
                    macro_pit_status: str, fundamentals_pit: bool,
                    regime_share: float | None, sector_share: float | None,
                    fold_stable: bool | None, effective_dates: int,
                    min_effective_dates: int) -> dict:
    """How much a historical bucket's estimate is allowed to count.

    Starts at ``HISTORICAL_BASE_WEIGHT`` and multiplies down for each defect
    that is actually present. The applied penalties are returned alongside the
    number so the dashboard can show *why* history is being discounted rather
    than presenting a bare coefficient.
    """
    weight = HISTORICAL_BASE_WEIGHT
    applied: list[str] = []

    coverage = float(pit_coverage or 0.0)
    if coverage < pit_data.MIN_CALIBRATION_COVERAGE:
        weight *= PENALTY["low_pit_coverage"]
        applied.append("low_pit_coverage")
    else:
        # Partial credit between the floor and full coverage.
        weight *= min(1.0, 0.85 + 0.15 * coverage)

    if survivorship_risk not in {"LOW"}:
        weight *= PENALTY["survivorship_unresolved"]
        applied.append("survivorship_unresolved")
    if macro_pit_status == pit_data.REVISED_HISTORY:
        weight *= PENALTY["macro_revised_history"]
        applied.append("macro_revised_history")
    if not fundamentals_pit:
        weight *= PENALTY["fundamentals_not_point_in_time"]
        applied.append("fundamentals_not_point_in_time")
    if regime_share is not None and regime_share > 0.6:
        weight *= PENALTY["regime_concentration"]
        applied.append("regime_concentration")
    if sector_share is not None and sector_share > 0.5:
        weight *= PENALTY["sector_concentration"]
        applied.append("sector_concentration")
    if fold_stable is False:
        weight *= PENALTY["fold_instability"]
        applied.append("fold_instability")

    # Small samples are already shrunk toward zero in the estimate itself; the
    # weight penalty here is about how much the *estimate* should move Kelly.
    if effective_dates < min_effective_dates:
        weight *= max(0.3, effective_dates / max(min_effective_dates, 1))
        applied.append("small_effective_sample")

    return {
        "weight": round(max(MIN_HISTORICAL_WEIGHT, min(HISTORICAL_BASE_WEIGHT, weight)), 4),
        "baseWeight": HISTORICAL_BASE_WEIGHT,
        "penaltiesApplied": applied,
        "rationaleKo": ("과거 OOS는 시점상 진짜 out-of-sample이지만 모델 설계 자체가 그 시기를 "
                        "겪은 뒤에 만들어졌으므로 실시간 증거보다 낮은 가중치를 부여합니다."),
    }


def calibrate(outcomes: list[dict], *, horizon: int = 126,
              buckets=DEFAULT_BUCKETS, cfg: dict | None = None,
              diagnostics: dict | None = None,
              cost_adjusted: bool = True,
              require_pit: bool = True) -> dict:
    """Region x alpha-bucket calibration from historical OOS outcomes."""
    cfg = cfg or {}
    diagnostics = diagnostics or {}
    edges = [float(x) for x in buckets]
    min_eff = int(cfg.get("minEffectiveDates", 30))
    prior_strength = float(cfg.get("shrinkagePriorStrength", min_eff))

    frame = horizon_frame(outcomes, horizon, cost_adjusted=False)
    excluded_low_pit = 0
    if require_pit and len(frame):
        before = len(frame)
        frame = frame[frame["usableForCalibration"]]
        excluded_low_pit = before - len(frame)
    if not len(frame):
        return {
            "horizonDays": horizon, "available": False,
            "reason": "no_matured_historical_outcomes_with_sufficient_pit_quality",
            "excludedLowPitObservations": excluded_low_pit,
            "regions": {}, "buckets": list(edges),
        }

    frame = frame.copy()
    frame["bucket"] = [
        _bucket_label(*b) if (b := KP._bucket(v, edges)) else None
        for v in frame["alphaPercentile"]
    ]
    frame = frame.dropna(subset=["bucket"])

    survivorship = diagnostics.get("survivorshipRisk", "HIGH")
    macro_status = diagnostics.get("macroPitStatus", pit_data.REVISED_HISTORY)
    fundamentals_pit = bool(diagnostics.get("fundamentalsPit"))

    min_ordering_t = float(cfg.get("minOrderingTStat", DEFAULT_MIN_ORDERING_T))
    min_ordering_dates = int(cfg.get("minOrderingEffectiveDates",
                                     DEFAULT_MIN_ORDERING_EFFECTIVE_DATES))

    regions: dict[str, dict] = {}
    for region in sorted(frame["region"].unique()):
        region_frame = frame[frame["region"] == region]
        # Measured once per region, before any bucket is scored: the carry every
        # bucket inherits for free, and whether the ranking ordered anything.
        universe = _universe_baseline(region_frame, horizon)
        ordering = _ordering_evidence(region_frame, horizon, min_t=min_ordering_t,
                                      min_effective_dates=min_ordering_dates)
        universe_gross = universe["grossSeries"]
        universe_net = universe["netSeries"]
        rows: list[dict] = []
        for bucket in sorted(region_frame["bucket"].unique(), key=lambda b: float(b.split("-")[0])):
            subset = region_frame[region_frame["bucket"] == bucket]
            if subset.empty:
                continue
            gross = subset.groupby("date")["excessReturn"].mean().dropna().sort_index()
            net = subset.groupby("date")["costAdjustedExcessReturn"].mean().dropna().sort_index()
            if not len(gross):
                continue
            stats = KP._newey_west_stats(gross, horizon)
            net_stats = KP._newey_west_stats(net, horizon) if len(net) else stats
            summary = _summary_stats(gross, horizon)

            # The attributable component: what this bucket did ABOVE the universe
            # it was drawn from, date by date. Subtracting per date (not mean from
            # mean) keeps the clustering and lets the HAC estimator see the series
            # the estimate actually rests on.
            spread_gross = (gross - universe_gross).dropna().sort_index()
            spread_net = (net - universe_net).dropna().sort_index() if len(net) else spread_gross
            spread_stats = KP._newey_west_stats(spread_gross, horizon) if len(spread_gross) else None
            spread_net_stats = (KP._newey_west_stats(spread_net, horizon)
                                if len(spread_net) else spread_stats)

            # Shrinkage rides on the effective sample of the SPREAD, because the
            # spread is what is being estimated. A bucket whose level is precise
            # only because the whole universe moved together has no more
            # information about the ranking than its spread series carries.
            eff = int(spread_stats["effectiveDates"]) if spread_stats else 0
            level_eff = int(stats["effectiveDates"])
            shrink = eff / (eff + prior_strength) if eff else 0.0
            level_mean = float(net_stats["mean"] if cost_adjusted and len(net) else stats["mean"])
            base_mean = float(
                (spread_net_stats if cost_adjusted and len(net) else spread_stats)["mean"]
            ) if spread_stats else 0.0
            shrunk = base_mean * shrink
            se = spread_stats.get("se") if spread_stats else None
            level_se = stats.get("se")
            # Fold stability is asked of the attributable spread, not the level:
            # a level that is stable only because the universe rose in every fold
            # is not a stable edge.
            stability_frame = subset.assign(
                value=subset["excessReturn"]
                - subset["date"].map(universe_gross).astype(float))
            stability = _fold_stability(stability_frame)
            regime_share = _concentration(subset, "macroRegime")
            sector_share = _concentration(subset, "sector")
            coverage = float(subset["pitCoverage"].mean()) if len(subset) else 0.0
            weight = evidence_weight(
                pit_coverage=coverage, survivorship_risk=survivorship,
                macro_pit_status=macro_status, fundamentals_pit=fundamentals_pit,
                regime_share=regime_share, sector_share=sector_share,
                fold_stable=stability.get("stable"), effective_dates=eff,
                min_effective_dates=min_eff,
            )
            spread_t = _t_stat(spread_stats)
            rows.append({
                "bucket": bucket,
                "observations": int(len(subset)),
                "uniqueSignalDates": int(stats["uniqueDates"]),
                "effectiveDates": eff,
                "hacLag": int(stats["hacLag"]),
                # --- level: what the bucket did vs the BENCHMARK (transparency) ---
                "meanExcessReturnPct": round(float(stats["mean"]) * 100, 3),
                "costAdjustedMeanExcessReturnPct": (round(float(net_stats["mean"]) * 100, 3)
                                                     if len(net) else None),
                "levelExpectedExcessReturnPct": round(level_mean * 100, 3),
                "levelStandardErrorPct": (round(float(level_se) * 100, 4)
                                          if level_se is not None else None),
                "levelEffectiveDates": level_eff,
                # --- attribution: level = universe carry + alpha spread ---
                "universeBaselineExcessPct": universe["meanExcessPct"],
                "spreadVsUniversePct": (round(float(spread_stats["mean"]) * 100, 3)
                                        if spread_stats else None),
                "costAdjustedSpreadVsUniversePct": (round(float(spread_net_stats["mean"]) * 100, 3)
                                                     if spread_net_stats else None),
                "spreadStandardErrorPct": (round(float(spread_stats["se"]) * 100, 4)
                                           if spread_stats and spread_stats.get("se") is not None
                                           else None),
                "spreadTStat": round(spread_t, 3) if spread_t is not None else None,
                "spreadPositiveHitRatio": (round(float((spread_gross > 0).mean()), 4)
                                           if len(spread_gross) else None),
                "attributableSharePct": (round(abs(base_mean) / abs(level_mean) * 100, 1)
                                         if level_mean else None),
                # --- what leaves this module as an expected return ---
                "expectedReturnBasis": "ALPHA_SPREAD_VS_REPLAY_UNIVERSE",
                "shrunkExpectedExcessReturnPct": round(shrunk * 100, 3),
                "shrinkageFactor": round(shrink, 4),
                "standardErrorPct": round(float(se) * 100, 4) if se is not None else None,
                "confidenceIntervalPct": ([round((base_mean - 1.96 * se) * shrink * 100, 3),
                                            round((base_mean + 1.96 * se) * shrink * 100, 3)]
                                           if se is not None else None),
                "positiveHitRatio": summary["hitRatio"],
                "medianExcessReturnPct": round((summary["median"] or 0) * 100, 3),
                "mddPct": round(summary["mdd"] * 100, 3) if summary["mdd"] is not None else None,
                "cvar95Pct": round(summary["cvar95"] * 100, 3) if summary["cvar95"] is not None else None,
                "nonOverlappingDates": summary["nonOverlappingDates"],
                "meanPitCoverage": round(coverage, 4),
                "topRegimeSharePct": round(regime_share * 100, 1) if regime_share is not None else None,
                "topSectorSharePct": round(sector_share * 100, 1) if sector_share is not None else None,
                "foldStability": stability,
                "evidenceWeight": weight["weight"],
                "evidenceWeightDetail": weight,
                # Two independent requirements, and both are about the SPREAD.
                # Enough effective spread dates to estimate anything, and
                # region-level evidence that the ranking orders returns at all.
                # A bucket in a region whose ordering is noise is not a weak
                # prior — it is not a prior.
                "usable": bool(eff >= min_eff and ordering["established"]),
                "unusableReason": (None if (eff >= min_eff and ordering["established"])
                                   else ("ORDERING_NOT_ESTABLISHED" if eff >= min_eff
                                         else "INSUFFICIENT_EFFECTIVE_SPREAD_DATES")),
            })
        if not rows:
            continue
        rows = _repair_monotonicity(rows, ordering_established=ordering["established"])
        regions[region] = {
            "buckets": rows,
            "observations": int(len(region_frame)),
            "uniqueDates": int(region_frame["date"].nunique()),
            "usableBuckets": sum(1 for r in rows if r["usable"]),
            "universeBaseline": {k: v for k, v in universe.items()
                                 if not k.endswith("Series")},
            "ordering": ordering,
            "attributionKo": ("버킷의 벤치마크 대비 초과수익은 '유니버스 캐리 + 알파 스프레드'입니다. "
                              "기대수익으로는 선정 모델이 만든 알파 스프레드만 사용합니다."),
        }

    probability_cfg = cfg.get("probabilityCalibration") or {}
    probability = probability_mod.calibrate(
        outcomes, horizon=horizon, buckets=edges,
        cfg=probability_cfg, require_pit=require_pit)
    integrity_cfg = probability_cfg.get("integrity") or {}
    conditional_macro_used = any(
        blob.get("selectedVariant") == "MACRO"
        for blob in (probability.get("regions") or {}).values())
    integrity_checks = {
        "pitCoverage": (integrity_cfg.get("minPitCoverage") is None
                        or float(diagnostics.get("meanPitCoverage") or 0.0)
                        >= float(integrity_cfg["minPitCoverage"])),
        "historicalUniverse": (not integrity_cfg.get("requireHistoricalUniverse", False)
                               or diagnostics.get("survivorshipRisk") == "LOW"),
        "pointInTimeFundamentals": (
            not integrity_cfg.get("requirePointInTimeFundamentals", False)
            or bool(diagnostics.get("fundamentalsPit"))),
        "vintageMacroForConditionalProbability": (
            not conditional_macro_used
            or not integrity_cfg.get("requireVintageMacroForConditionalProbability", False)
            or diagnostics.get("macroPitStatus") not in {pit_data.REVISED_HISTORY, None}),
    }
    integrity_gate = {
        "eligible": bool(all(integrity_checks.values())),
        "checks": integrity_checks,
        "failures": [key for key, passed in integrity_checks.items() if not passed],
        "policyKo": ("확률 성능과 별도로 과거 구성종목·발표시점 재무·조건부 거시 vintage가 "
                     "운영 모델과 같은지를 검사합니다. 데이터가 없으면 할인만 하지 않고 Kelly를 차단합니다."),
    }
    probability["integrityGate"] = integrity_gate
    statistical_eligible = bool((probability.get("reliabilityGate") or {}).get("eligible"))
    probability.setdefault("reliabilityGate", {})["statisticalEligible"] = statistical_eligible
    probability["reliabilityGate"]["eligible"] = bool(
        statistical_eligible and integrity_gate["eligible"])
    if not integrity_gate["eligible"]:
        probability["reliabilityGate"].setdefault("failures", []).append("dataIntegrity")
    return {
        "horizonDays": horizon,
        "available": bool(regions),
        "method": ("UNIVERSE_RELATIVE_ALPHA_SPREAD_DATE_CLUSTERED_NEWEY_WEST_HAC"
                   "_WITH_ORDERING_GATED_ISOTONIC_REPAIR"),
        "expectedReturnBasis": "ALPHA_SPREAD_VS_REPLAY_UNIVERSE",
        "minOrderingTStat": min_ordering_t,
        "evidenceClass": "HISTORICAL_OOS",
        "costAdjusted": bool(cost_adjusted),
        "buckets": list(edges),
        "excludedLowPitObservations": excluded_low_pit,
        "regions": regions,
        "orderingEstablishedRegions": sorted(
            r for r, blob in regions.items()
            if (blob.get("ordering") or {}).get("established")),
        "probabilityCalibration": probability,
        "notAForecastKo": ("알파 백분위는 순위이며, 여기 수치는 과거 같은 순위 구간에서 실제로 "
                            "관측된 초과수익 분포입니다. 미래 수익 보장이 아닙니다."),
        "attributionKo": ("벤치마크 대비 초과수익에서 유니버스 전체가 벤치마크 대비 낸 부분을 "
                           "먼저 빼고, 남은 알파 스프레드만 기대수익으로 씁니다. 유니버스 캐리는 "
                           "선정 모델의 성과가 아니므로 Kelly 비중으로 환산하지 않습니다."),
    }


def _repair_monotonicity(rows: list[dict], *,
                         ordering_established: bool = True) -> list[dict]:
    """Force a non-decreasing bucket ladder, and say when repair was needed.

    Only when ordering has been established. Isotonic regression is a monotone
    fit: given five noisy numbers it returns a tidy ladder every time, so running
    it before the ordering test would launder "this ranking does not order
    returns" into a clean rising staircase — the single most misleading thing
    this module could publish.
    """
    if not ordering_established:
        for row in rows:
            row["preIsotonicExpectedExcessReturnPct"] = row["shrunkExpectedExcessReturnPct"]
            row["calibratedExpectedExcessReturnPct"] = row["shrunkExpectedExcessReturnPct"]
            row["monotonicityWarning"] = "ORDERING_NOT_ESTABLISHED_NO_LADDER_PUBLISHED"
            row["isotonicAdjustmentPct"] = 0.0
        return rows
    usable = [r for r in rows if r["usable"]]
    if len(usable) < 2:
        for row in rows:
            row["monotonicityWarning"] = None
            row["calibratedExpectedExcessReturnPct"] = row["shrunkExpectedExcessReturnPct"]
            row["isotonicAdjustmentPct"] = 0.0
        return rows
    values = [r["shrunkExpectedExcessReturnPct"] for r in usable]
    weights = [max(1, int(r["effectiveDates"])) for r in usable]
    repaired = KP._isotonic_non_decreasing(values, weights)
    violated = any(abs(a - b) > 1e-9 for a, b in zip(values, repaired))
    lookup = {r["bucket"]: v for r, v in zip(usable, repaired)}
    for row in rows:
        row["preIsotonicExpectedExcessReturnPct"] = row["shrunkExpectedExcessReturnPct"]
        row["calibratedExpectedExcessReturnPct"] = round(
            lookup.get(row["bucket"], row["shrunkExpectedExcessReturnPct"]), 3)
        # How far the fit had to move this bucket. A large adjustment means the
        # measured ladder disagreed with the published one and is worth seeing.
        row["isotonicAdjustmentPct"] = round(
            row["calibratedExpectedExcessReturnPct"]
            - row["preIsotonicExpectedExcessReturnPct"], 3)
        row["monotonicityWarning"] = "BUCKET_MONOTONICITY_REPAIRED" if violated else None
    return rows


def lookup_bucket(calibration: dict, region: str, alpha_percentile: float | None) -> dict | None:
    """The calibrated row a live candidate falls into, or None."""
    if not calibration or not calibration.get("available") or alpha_percentile is None:
        return None
    region_blob = (calibration.get("regions") or {}).get(region)
    if not region_blob:
        return None
    edges = [float(x) for x in calibration.get("buckets") or DEFAULT_BUCKETS]
    target = KP._bucket(float(alpha_percentile), edges)
    if not target:
        return None
    label = _bucket_label(*target)
    for row in region_blob.get("buckets", []):
        if row["bucket"] == label:
            return row
    return None


# --------------------------------------------------------------------------- #
# Regime interaction — researched, not switched on by default
# --------------------------------------------------------------------------- #
REGIME_SIGNIFICANCE_Z = 1.96
REGIME_MIN_EFFECTIVE_DATES = 15


def regime_interaction(outcomes: list[dict], *, horizon: int = 126,
                       buckets=DEFAULT_BUCKETS, cfg: dict | None = None,
                       require_pit: bool = True) -> dict:
    """Does the alpha bucket's payoff depend on the macro regime?

    Region x bucket is the BASE calibration and stays the base. Splitting it
    again by regime is tempting and usually wrong: five buckets x two regions x
    five regimes is fifty cells carved out of one dataset, and most of them will
    show a large "effect" made entirely of noise.

    So this function is a diagnostic, not a second calibration. Each cell is
    shrunk toward its region x bucket parent by ``eff / (eff + parent_strength)``
    — hierarchical shrinkage, so a thin cell simply reports the parent — and the
    interaction is marked significant only when the gap clears roughly two
    standard errors AND the cell has enough effective dates to be worth reading.

    ``activate`` is the field a caller should gate on. It is true only when at
    least one cell in that region is genuinely significant; until then the base
    calibration is the whole story and this output is research.
    """
    cfg = cfg or {}
    min_eff = int(cfg.get("minEffectiveDates", 30))
    parent_strength = float(cfg.get("regimeShrinkageStrength", min_eff))
    edges = [float(x) for x in buckets]

    frame = horizon_frame(outcomes, horizon)
    if require_pit and len(frame):
        frame = frame[frame["usableForCalibration"]]
    if not len(frame) or "macroRegime" not in frame:
        return {"available": False, "reason": "no_usable_outcomes", "regions": {},
                "activate": False}
    frame = frame.copy()
    frame["bucket"] = [
        _bucket_label(*b) if (b := KP._bucket(v, edges)) else None
        for v in frame["alphaPercentile"]
    ]
    frame = frame.dropna(subset=["bucket", "macroRegime"])
    if not len(frame):
        return {"available": False, "reason": "no_macro_regime_labels_in_ledger",
                "regions": {}, "activate": False,
                "noteKo": "매크로 데이터 없이 재현한 구간은 국면 라벨이 없어 상호작용을 볼 수 없습니다."}

    regions: dict[str, dict] = {}
    any_significant = False
    for region in sorted(frame["region"].unique()):
        region_frame = frame[frame["region"] == region]
        cells: list[dict] = []
        for bucket in sorted(region_frame["bucket"].unique(),
                             key=lambda b: float(b.split("-")[0])):
            bucket_frame = region_frame[region_frame["bucket"] == bucket]
            parent_series = bucket_frame.groupby("date")["excessReturn"].mean().dropna()
            if not len(parent_series):
                continue
            parent = KP._newey_west_stats(parent_series, horizon)
            for regime in sorted(bucket_frame["macroRegime"].dropna().unique()):
                cell_frame = bucket_frame[bucket_frame["macroRegime"] == regime]
                series = cell_frame.groupby("date")["excessReturn"].mean().dropna()
                if len(series) < 3:
                    continue
                stats = KP._newey_west_stats(series, horizon)
                eff = int(stats["effectiveDates"])
                weight = eff / (eff + parent_strength) if eff else 0.0
                shrunk = weight * float(stats["mean"]) + (1 - weight) * float(parent["mean"])
                gap = float(stats["mean"]) - float(parent["mean"])
                se = stats.get("se")
                z = (gap / se) if se else None
                significant = bool(
                    z is not None and abs(z) >= REGIME_SIGNIFICANCE_Z
                    and eff >= REGIME_MIN_EFFECTIVE_DATES)
                any_significant = any_significant or significant
                cells.append({
                    "bucket": bucket, "regime": regime,
                    "observations": int(len(cell_frame)),
                    "effectiveDates": eff,
                    "rawMeanExcessPct": round(float(stats["mean"]) * 100, 3),
                    "parentMeanExcessPct": round(float(parent["mean"]) * 100, 3),
                    "shrunkMeanExcessPct": round(shrunk * 100, 3),
                    "shrinkageTowardParent": round(1 - weight, 4),
                    "gapVsParentPct": round(gap * 100, 3),
                    "zScore": round(z, 3) if z is not None else None,
                    "significant": significant,
                })
        if cells:
            regions[region] = {"cells": cells,
                               "significantCells": sum(1 for c in cells if c["significant"])}
    return {
        "available": bool(regions),
        "method": "HIERARCHICAL_SHRINKAGE_TOWARD_REGION_ALPHA_BUCKET",
        "regions": regions,
        # The gate. Base calibration stays authoritative until this is true.
        "activate": bool(any_significant),
        "minEffectiveDates": REGIME_MIN_EFFECTIVE_DATES,
        "significanceZ": REGIME_SIGNIFICANCE_Z,
        "policyKo": ("지역 x 알파버킷을 기본 calibration으로 유지하고, 국면 상호작용은 "
                      "OOS에서 유의미할 때만 추가합니다. 표본이 얇은 셀은 상위 버킷 값으로 "
                      "수축되어 사실상 기본값을 보고합니다."),
    }
