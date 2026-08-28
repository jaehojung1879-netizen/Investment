"""Honest validation of alpha ranking and the final concentrated portfolio.

This module does not invent a model.  It consumes immutable replay signals and
their matured outcomes, calls the production research selection and portfolio
allocation functions, and publishes what can and cannot be concluded.

The current historical ledger is price-sleeve only.  Therefore portfolio
replay is explicitly labelled ``PRICE_SLEEVES_ONLY_AUDIT_PROXY`` and can never
promote Kelly or a selector.  A full-fidelity claim becomes possible only when
publication-aware fundamentals and historical constituents are supplied.
"""
from __future__ import annotations

from collections import defaultdict
import math

import numpy as np
import pandas as pd

from . import historical_calibration as HC
from . import historical_outcomes as HO
from . import kelly_portfolio as KP
from . import longterm as LT
from . import selection_null as SN
from . import pit_data


REPORT_VERSION = "portfolio-validation-v2"
CHAMPION = KP.SELECTION_METHOD
CHALLENGER = "CALIBRATED_EXPECTED_RETURN_PER_DOWNSIDE_RISK"
HORIZONS = (21, 63, 126, 252)
# The path statistics are reported on the 21-day rebalance grid: it yields the
# most non-overlapping blocks, so it is the only horizon where a difference has
# any chance of clearing its own sampling error.
HEADLINE_HORIZON = 21
PRICE_SLEEVES = ("momentum", "lowvol")
FULL_SLEEVES = ("momentum", "value", "quality", "lowvol")


def _finite(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _r(value, digits=4):
    out = _finite(value)
    return round(out, digits) if out is not None else None


def _bucket(value, edges):
    pair = KP._bucket(_finite(value), [float(x) for x in edges])
    return f"{pair[0]:g}-{pair[1]:g}" if pair else None


def _non_overlapping_count(dates, horizon: int) -> int:
    chosen: list[pd.Timestamp] = []
    for date in sorted(pd.Timestamp(d).normalize() for d in set(dates)):
        if not chosen or date >= chosen[-1] + pd.offsets.BDay(horizon):
            chosen.append(date)
    return len(chosen)


def _nw_summary(series: pd.Series, horizon: int) -> dict:
    series = series.dropna().sort_index()
    if not len(series):
        return {"mean": None, "median": None, "std": None, "ir": None,
                "positiveRate": None, "ci95": None, "uniqueDates": 0,
                "effectiveIndependentDates": 0, "hacLag": horizon - 1}
    stats = KP._newey_west_stats(series, horizon)
    mean = float(series.mean())
    std = float(series.std(ddof=1)) if len(series) > 1 else None
    se = stats.get("se")
    return {
        "mean": _r(mean, 6),
        "median": _r(series.median(), 6),
        "std": _r(std, 6),
        "ir": _r(mean / std, 4) if std and std > 0 else None,
        "positiveRate": _r((series > 0).mean(), 4),
        "ci95": ([_r(mean - 1.96 * se, 6), _r(mean + 1.96 * se, 6)]
                 if se is not None else None),
        "uniqueDates": int(series.index.nunique()),
        "effectiveIndependentDates": _non_overlapping_count(series.index, horizon),
        "hacLag": int(stats.get("hacLag") or horizon - 1),
    }


def _generation_filter(rows: list[dict], *, replay_version: str | None,
                       model_version: str | None) -> tuple[list[dict], int]:
    kept = []
    rejected = 0
    for row in rows:
        if replay_version and row.get("replayVersion") != replay_version:
            rejected += 1
            continue
        if model_version and row.get("modelVersion") != model_version:
            rejected += 1
            continue
        kept.append(row)
    return kept, rejected


def _joined_frame(signals: list[dict], outcomes: list[dict], horizon: int) -> pd.DataFrame:
    factors = {row.get("id"): row.get("factorPercentiles") or {} for row in signals}
    frame = HO.horizon_frame(outcomes, horizon, cost_adjusted=False)
    if frame.empty:
        return frame
    if "id" in frame:
        frame = frame.copy()
        for sleeve in FULL_SLEEVES:
            frame[sleeve] = [
                _finite((factors.get(identifier) or {}).get(sleeve))
                for identifier in frame["id"]
            ]
            frame[sleeve] = pd.to_numeric(frame[sleeve], errors="coerce")
        # These are the configured live weights renormalized over the sleeves
        # named by the diagnostic, not a new factor or a post-hoc formula.
        frame["priceComposite"] = frame["momentum"] * .6 + frame["lowvol"] * .4
        frame["fullComposite"] = (frame["momentum"] * .30 + frame["value"] * .25
                                  + frame["quality"] * .25 + frame["lowvol"] * .20)
    return frame


def _date_spread(frame: pd.DataFrame, high, low, value="excessReturn") -> pd.Series:
    rows = []
    for date, group in frame.groupby("date", sort=True):
        hi = group.loc[high(group), value].dropna()
        lo = group.loc[low(group), value].dropna()
        if len(hi) and len(lo):
            rows.append((pd.Timestamp(date), float(hi.mean() - lo.mean())))
    return pd.Series(dict(rows), dtype=float).sort_index()


def _rolling(series: pd.Series, years: int) -> list[dict]:
    series = series.dropna().sort_index()
    if not len(series):
        return []
    out = []
    for stamp in series.index:
        window = series.loc[(series.index > stamp - pd.DateOffset(years=years))
                            & (series.index <= stamp)]
        if len(window) >= max(8, years * 8):
            out.append({"date": stamp.strftime("%Y-%m-%d"), "value": _r(window.mean(), 6)})
    # Monthly points keep the UI artifact compact without changing the window.
    compact = {}
    for row in out:
        compact[row["date"][:7]] = row
    return list(compact.values())


def _bucket_diagnostics(frame: pd.DataFrame, horizon: int, edges) -> tuple[list[dict], dict]:
    work = frame.copy()
    work["bucket"] = [_bucket(v, edges) for v in work["alphaPercentile"]]
    work = work.dropna(subset=["bucket"])

    # The carry every bucket inherits for free. Without it this table reads as
    # "even the bottom 60% beats the benchmark by 2%", which is true and says
    # nothing about the ranking — see historical_calibration for the argument.
    universe_gross = work.groupby("date")["excessReturn"].mean().sort_index()
    universe_net = work.groupby("date")["costAdjustedExcessReturn"].mean().sort_index()
    carry_gross = float(universe_gross.mean()) if len(universe_gross) else None
    carry_net = float(universe_net.mean()) if len(universe_net) else None

    rows = []
    for label in [f"{float(edges[i]):g}-{float(edges[i + 1]):g}"
                  for i in range(len(edges) - 1)]:
        cell = work[work["bucket"] == label]
        gross = cell.groupby("date")["excessReturn"].mean().sort_index()
        net = cell.groupby("date")["costAdjustedExcessReturn"].mean().sort_index()
        spread_gross = (gross - universe_gross).dropna().sort_index()
        spread_net = (net - universe_net).dropna().sort_index()
        raw = cell["excessReturn"].dropna()
        up = raw[raw > 0]
        down = raw[raw <= 0]
        tail_n = max(1, int(math.ceil(len(raw) * .05))) if len(raw) else 0
        rows.append({
            "bucket": label,
            "observations": int(len(cell)),
            "uniqueDates": int(gross.index.nunique()),
            "effectiveIndependentDates": _non_overlapping_count(gross.index, horizon),
            "meanGrossExcessPct": _r(gross.mean() * 100, 3) if len(gross) else None,
            "medianGrossExcessPct": _r(raw.median() * 100, 3) if len(raw) else None,
            "meanCostAdjustedExcessPct": _r(net.mean() * 100, 3) if len(net) else None,
            "universeCarryPct": _r((carry_net if carry_net is not None else carry_gross) * 100, 3)
                                 if (carry_net is not None or carry_gross is not None) else None,
            "spreadVsUniversePct": (_r(spread_gross.mean() * 100, 3)
                                    if len(spread_gross) else None),
            "costAdjustedSpreadVsUniversePct": (_r(spread_net.mean() * 100, 3)
                                                if len(spread_net) else None),
            "spreadHitRatePct": (_r((spread_gross > 0).mean() * 100, 2)
                                 if len(spread_gross) else None),
            "hitRatePct": _r((raw > 0).mean() * 100, 2) if len(raw) else None,
            "averageUpsidePct": _r(up.mean() * 100, 3) if len(up) else None,
            "averageDownsidePct": _r(abs(down.mean()) * 100, 3) if len(down) else None,
            "payoffRatio": (_r(up.mean() / abs(down.mean()), 4)
                            if len(up) and len(down) and down.mean() else None),
            "worstDecilePct": _r(raw.quantile(.1) * 100, 3) if len(raw) else None,
            "cvar95Pct": (_r(raw.nsmallest(tail_n).mean() * 100, 3)
                          if tail_n else None),
            "hacLag": horizon - 1,
        })
    valid = [row for row in rows if row["meanGrossExcessPct"] is not None]
    means = [row["meanGrossExcessPct"] for row in valid]
    medians = [row["medianGrossExcessPct"] for row in valid]

    def mono(values):
        if len(values) < 2:
            return None
        return _r(sum(b >= a for a, b in zip(values, values[1:])) / (len(values) - 1), 3)

    bucket_rank_corr = (pd.Series(range(len(means))).corr(pd.Series(means), method="spearman")
                        if len(means) >= 2 else None)
    top_bottom = _date_spread(work, lambda g: g.alphaPercentile >= 95,
                              lambda g: g.alphaPercentile < 50)
    decile = _date_spread(work, lambda g: g.alphaPercentile >= 90,
                          lambda g: g.alphaPercentile < 10)
    top_summary = _nw_summary(top_bottom, horizon)
    decile_summary = _nw_summary(decile, horizon)
    monotonicity = {
        "meanScore": mono(means),
        "medianScore": mono(medians),
        "bucketRankSpearman": _r(bucket_rank_corr, 4),
        "status": ("PASS" if mono(means) == 1.0 and mono(medians) == 1.0
                   else "WEAK" if (mono(means) or 0) >= .5 else "FAIL"),
        "top5MinusBottom50Pct": _r((top_summary.get("mean") or 0) * 100, 3),
        "top5MinusBottom50Ci95Pct": ([ _r(v * 100, 3) for v in top_summary["ci95"]]
                                      if top_summary.get("ci95") else None),
        "topDecileMinusBottomDecilePct": _r((decile_summary.get("mean") or 0) * 100, 3),
        "topDecileMinusBottomDecileCi95Pct": ([ _r(v * 100, 3) for v in decile_summary["ci95"]]
                                               if decile_summary.get("ci95") else None),
        "universeCarryPct": _r((carry_net if carry_net is not None else carry_gross) * 100, 3)
                             if (carry_net is not None or carry_gross is not None) else None,
        "plainLanguageKo": ("전체 bucket이 단조 증가하지 않으면 최상위 bucket의 양(+) 스프레드와 "
                            "전체 ranking alpha의 유효성을 같은 주장으로 표현하지 않습니다."),
        "attributionKo": ("'평균 초과'는 벤치마크 대비 값이라 유니버스 캐리를 포함합니다. "
                           "선정 모델의 기여는 '유니버스 대비' 열이며, 최상위−최하위 스프레드처럼 "
                           "캐리가 상쇄되는 지표만 순위의 유효성을 말해줍니다."),
    }
    monotonicity["_topBottomSeries"] = top_bottom
    return rows, monotonicity


# Every weight in the live composite is positive, so the blend assumes a
# positive sign for every sleeve it carries. A sleeve whose regional rank IC
# confidence interval sits entirely on the far side of zero is therefore not
# "weak evidence" — it is evidence against a weight production is already
# paying for, and it stays invisible if only the blended composite is reported.
#
# This is deliberately a detector and not a corrector. The replay it reads is
# survivorship-affected on 100% of observations and carries no point-in-time
# fundamentals, so refitting FACTOR_WEIGHTS on the same sample that surfaced
# the contradiction would be exactly the model shopping the rest of this module
# refuses to do. It reports; a human decides.
SIGN_MIN_INDEPENDENT_DATES = 12
SIGN_PERSISTENCE_HORIZONS = 2


def _sleeve_sign_consistency(factor_attr: dict) -> dict:
    """Flag sleeves whose historical rank IC contradicts their live sign."""
    grouped: dict[str, dict] = {}
    for key, sleeves in factor_attr.items():
        region, _, horizon = key.partition(":")
        if not horizon.isdigit():
            continue
        for sleeve in PRICE_SLEEVES:
            row = sleeves.get(sleeve)
            if not row or not row.get("claimEligible"):
                continue
            ic = row.get("rankIC") or {}
            ci = ic.get("ci95")
            effective = int(ic.get("effectiveIndependentDates") or 0)
            bucket = grouped.setdefault(f"{region}:{sleeve}", {
                "region": region,
                "sleeve": sleeve,
                "liveWeight": _r(LT.FACTOR_WEIGHTS.get(sleeve), 4),
                "assumedSign": 1,
                "contradictedHorizons": [],
                "consistentHorizons": [],
                "inconclusiveHorizons": [],
                "evidence": [],
            })
            bucket["evidence"].append({
                "horizonDays": int(horizon),
                "rankICMean": ic.get("mean"),
                "ci95": ci,
                "positiveRate": ic.get("positiveRate"),
                "effectiveIndependentDates": effective,
            })
            if ci is None or None in ci or effective < SIGN_MIN_INDEPENDENT_DATES:
                bucket["inconclusiveHorizons"].append(int(horizon))
            elif ci[1] < 0:
                bucket["contradictedHorizons"].append(int(horizon))
            elif ci[0] > 0:
                bucket["consistentHorizons"].append(int(horizon))
            else:
                bucket["inconclusiveHorizons"].append(int(horizon))

    contradicted = []
    for key, bucket in grouped.items():
        for field in ("contradictedHorizons", "consistentHorizons", "inconclusiveHorizons"):
            bucket[field].sort()
        bucket["evidence"].sort(key=lambda row: row["horizonDays"])
        persistent = len(bucket["contradictedHorizons"]) >= SIGN_PERSISTENCE_HORIZONS
        bucket["persistent"] = persistent
        if persistent:
            bucket["status"] = "CONTRADICTED"
            contradicted.append(key)
        elif bucket["contradictedHorizons"]:
            bucket["status"] = "CONTRADICTED_AT_SINGLE_HORIZON"
        elif bucket["consistentHorizons"]:
            bucket["status"] = "CONSISTENT"
        else:
            bucket["status"] = "INCONCLUSIVE"
    return {
        "assumedSignPolicy": "ALL_LIVE_COMPOSITE_WEIGHTS_POSITIVE_SO_EVERY_SLEEVE_ASSUMES_POSITIVE_SIGN",
        "actionPolicy": "REPORT_ONLY_NEVER_REWEIGHT_ON_THIS_SAMPLE",
        "assessedSleeves": list(PRICE_SLEEVES),
        "liveWeights": {sleeve: _r(LT.FACTOR_WEIGHTS.get(sleeve), 4) for sleeve in PRICE_SLEEVES},
        "minIndependentDates": SIGN_MIN_INDEPENDENT_DATES,
        "persistenceThresholdHorizons": SIGN_PERSISTENCE_HORIZONS,
        "byRegionSleeve": dict(sorted(grouped.items())),
        "contradicted": sorted(contradicted),
        "status": "CONTRADICTED" if contradicted else "NO_CONTRADICTION_DETECTED",
        "interpretationKo": (
            "라이브 합성은 모든 슬리브에 양(+)의 가중치를 주므로 각 슬리브의 가정 부호는 +입니다. "
            "어떤 지역·슬리브의 rank IC 95% 구간이 두 개 이상 horizon에서 0보다 완전히 아래에 있으면, "
            "그 슬리브는 실전에서 부여받은 가중치와 반대 방향의 증거를 갖고 있다는 뜻입니다. "
            "이 표본은 생존편향이 해소되지 않았고 시점별 재무가 없으므로, 이 신호는 가중치 재적합의 "
            "근거가 아니라 사람이 판단해야 할 보고 항목입니다."),
    }


def alpha_diagnostics(signals: list[dict], outcomes: list[dict], *,
                      edges=(0, 60, 80, 90, 95, 100),
                      pit_fundamentals: bool = False) -> dict:
    """Region-separated Rank IC, bucket monotonicity and sleeve attribution."""
    regions: dict[str, dict] = {}
    factor_attr: dict[str, dict] = {}
    for horizon in HORIZONS:
        frame = _joined_frame(signals, outcomes, horizon)
        if frame.empty:
            continue
        for region in sorted(frame["region"].dropna().unique()):
            part = frame[frame["region"] == region].copy()
            ic_rows = []
            for date, group in part.groupby("date", sort=True):
                usable = group.dropna(subset=["alphaPercentile", "excessReturn"])
                if len(usable) >= 5:
                    ic_rows.append((pd.Timestamp(date), float(
                        usable["alphaPercentile"].corr(usable["excessReturn"], method="spearman"))))
            ic = pd.Series(dict(ic_rows), dtype=float).dropna().sort_index()
            buckets, monotonicity = _bucket_diagnostics(part, horizon, edges)
            top_bottom = monotonicity.pop("_topBottomSeries")
            key = f"{region}:{horizon}"
            regions[key] = {
                "region": region, "horizonDays": horizon,
                "rankIC": _nw_summary(ic, horizon),
                "buckets": buckets,
                "monotonicity": monotonicity,
                "rolling3YRankIC": _rolling(ic, 3),
                "rolling5YRankIC": _rolling(ic, 5),
                "rolling3YTopBottomSpread": _rolling(top_bottom, 3),
                "rolling5YTopBottomSpread": _rolling(top_bottom, 5),
            }
            sleeve_rows = {}
            for sleeve in (*PRICE_SLEEVES, "priceComposite", "fullComposite"):
                series = []
                if sleeve not in part:
                    continue
                for date, group in part.groupby("date", sort=True):
                    usable = group.dropna(subset=[sleeve, "excessReturn"])
                    if len(usable) >= 5:
                        series.append((pd.Timestamp(date), float(
                            usable[sleeve].corr(usable["excessReturn"], method="spearman"))))
                values = pd.Series(dict(series), dtype=float)
                sleeve_rows[sleeve] = {
                    "availableObservations": int(part[sleeve].notna().sum()),
                    "rankIC": _nw_summary(values, horizon),
                    "claimEligible": bool(
                        part[sleeve].notna().any()
                        and (sleeve != "fullComposite" or pit_fundamentals)),
                    "withheldReason": (
                        "PIT_FUNDAMENTALS_REQUIRED_FOR_FULL_LIVE_COMPOSITE"
                        if sleeve == "fullComposite" and not pit_fundamentals else None),
                }
            factor_attr[key] = sleeve_rows
    return {
        "regions": regions,
        "factorAttribution": factor_attr,
        "sleeveSignConsistency": _sleeve_sign_consistency(factor_attr),
        "poolingPolicy": "DATE_X_REGION_ONLY; KR_US_NEVER_POOLED",
        "effectiveSamplePolicy": "RAW_N_WITH_UNIQUE_DATES_EFFECTIVE_INDEPENDENT_DATES_AND_HAC_LAG",
        "fullCompositePolicy": "FULL_LIVE_COMPOSITE_ONLY_WHEN_PIT_FUNDAMENTALS_EXIST",
    }


class ExpandingBucketCalibration:
    """Maturity-aware bucket means for the historical challenger.

    Events enter the state only when ``outcomeEndDate <= replayDate``. Values
    are already date-clustered, so one large cross-section is one observation.
    """

    def __init__(self, outcomes: list[dict], *, horizon=126,
                 edges=(0, 60, 80, 90, 95, 100), prior_strength=30,
                 min_dates=20):
        self.edges = tuple(float(value) for value in edges)
        frame = HO.horizon_frame(outcomes, horizon, cost_adjusted=False)
        if len(frame):
            frame = frame.dropna(subset=["outcomeEndDate", "alphaPercentile"])
            frame = frame.copy()
            frame["bucket"] = [_bucket(v, edges) for v in frame["alphaPercentile"]]
            grouped = (frame.groupby(["outcomeEndDate", "date", "region", "bucket"], dropna=True)
                       ["costAdjustedExcessReturn"].mean().reset_index())
            self.events = grouped.sort_values(["outcomeEndDate", "date", "region", "bucket"])
        else:
            self.events = pd.DataFrame()
        self.pointer = 0
        self.values: dict[tuple[str, str], list[tuple[pd.Timestamp, float]]] = defaultdict(list)
        self.prior_strength = float(prior_strength)
        self.min_dates = int(min_dates)
        self.horizon = int(horizon)

    def advance(self, as_of) -> None:
        cutoff = pd.Timestamp(as_of).normalize()
        while self.pointer < len(self.events):
            row = self.events.iloc[self.pointer]
            if pd.Timestamp(row["outcomeEndDate"]).normalize() > cutoff:
                break
            self.values[(row["region"], row["bucket"])].append(
                (pd.Timestamp(row["date"]).normalize(), float(row["costAdjustedExcessReturn"])))
            self.pointer += 1

    def expected(self, region: str, alpha_percentile) -> dict | None:
        label = _bucket(alpha_percentile, self.edges)
        rows = self.values.get((region, label), [])
        if len(rows) < self.min_dates:
            return None
        series = pd.Series({date: value for date, value in rows}, dtype=float).sort_index()
        eff = _non_overlapping_count(series.index, self.horizon)
        shrink = eff / (eff + self.prior_strength) if eff else 0.0
        return {
            "bucket": label,
            "expectedExcessReturnPct": _r(series.mean() * shrink * 100, 4),
            "rawMeanExcessReturnPct": _r(series.mean() * 100, 4),
            "uniqueDates": int(series.index.nunique()),
            "effectiveIndependentDates": eff,
            "shrinkageFactor": _r(shrink, 4),
            "labelAvailabilityPolicy": "OUTCOME_END_DATE_LTE_REPLAY_DATE",
        }


def _candidate(signal: dict, *, price_proxy: bool) -> dict:
    factors = signal.get("factorPercentiles") or {}
    price_ready = all(factors.get(key) is not None for key in PRICE_SLEEVES)
    alpha = _finite(signal.get("alphaPercentile"))
    proxy_eligible = bool(price_proxy and price_ready)
    view = ("POSITIVE" if proxy_eligible and alpha is not None and alpha >= 66
            else signal.get("longTermResearchView"))
    return {
        "ticker": signal.get("ticker"), "region": signal.get("region"),
        "sector": signal.get("sector") or "Unclassified",
        "alpha": signal.get("alpha"), "alphaPercentile": alpha,
        "longTermResearchView": view,
        "dataInsufficient": (not proxy_eligible if price_proxy
                             else bool(signal.get("dataInsufficient"))),
        "valueTrap": bool(signal.get("valueTrap")),
        "evidenceCoverage": ((signal.get("features") or {}).get("evidenceCoverage")
                             or (signal.get("pit") or {}).get("pitCoverage") or 0),
        "factorPercentiles": factors,
        "sleevesAvailable": [key for key in FULL_SLEEVES if factors.get(key) is not None],
        "sleevesWithheld": [key for key in FULL_SLEEVES if factors.get(key) is None],
        "factorCoverage": sum(factors.get(key) is not None for key in FULL_SLEEVES) / 4,
        "sourceQuality": (signal.get("pit") or {}).get("pitQuality"),
        "pitAvailability": (signal.get("pit") or {}).get("sourceStatus") or {},
        "risk": signal.get("risk") or {},
        "entryState": signal.get("entryState"),
        "entry": {"entryState": signal.get("entryState")},
        "macroRegime": signal.get("macroRegime"),
        "benchmark": signal.get("benchmark"),
    }


def _research_candidates(rows: list[dict], cfg_lt: dict,
                         prior: dict[str, set[str]], *, price_proxy: bool) -> list[dict]:
    out = []
    for region in sorted({row.get("region") for row in rows if row.get("region")}):
        candidates = [_candidate(row, price_proxy=price_proxy)
                      for row in rows if row.get("region") == region]
        candidates = [row for row in candidates if row.get("ticker")]
        if len(candidates) < 5:
            continue
        table = pd.DataFrame.from_dict({row["ticker"]: {
            "alpha": _finite(row.get("alpha")) or 0.0,
            "dataInsufficient": bool(row.get("dataInsufficient")),
            "sector": row.get("sector"),
            "evidenceCoverage": row.get("evidenceCoverage"),
            "dataCompleteness": 0.0,
            "downsideVol": (_finite((row.get("risk") or {}).get("downsideVolPct")) or 25) / 100,
        } for row in candidates}, orient="index")
        selected = LT.select_names(table, cfg_lt, prior.get(region, set()))
        prior[region] = set(selected)
        lookup = {row["ticker"]: row for row in candidates}
        out.extend(lookup[ticker] for ticker in selected)
    return out


def _challenger_scores(candidates: list[dict], calibration: ExpandingBucketCalibration,
                       cfg_pf: dict) -> list[dict]:
    rows = []
    for candidate in candidates:
        estimate = calibration.expected(candidate.get("region"), candidate.get("alphaPercentile"))
        risk = KP._risk_unit(candidate)
        state = KP._state_multiplier(candidate, cfg_pf)
        mu = (estimate or {}).get("expectedExcessReturnPct")
        excluded = []
        if estimate is None:
            excluded.append("MATURED_CALIBRATION_NOT_READY")
        if risk is None or risk <= 0:
            excluded.append("DOWNSIDE_RISK_UNAVAILABLE")
        if state <= 0:
            excluded.append("ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING")
        # Keep the audit JSON standards-compliant.  An unready challenger row
        # sorts last through a finite sentinel and remains explicitly ineligible.
        score = (float(mu) / (risk * 100) * state
                 if mu is not None and risk and risk > 0 else -1e12)
        rows.append({
            "ticker": candidate["ticker"], "region": candidate.get("region"),
            "sector": candidate.get("sector") or "Unclassified",
            "score": score, "convictionScore": score,
            "alphaPercentile": candidate.get("alphaPercentile"),
            "downsideVolPct": _r(risk * 100, 2) if risk else None,
            "evidenceCoverage": candidate.get("evidenceCoverage"),
            "eligible": not excluded, "exclusionCodes": excluded,
            "calibration": estimate,
        })
    return rows


def _turnover_cost(weights: dict, prior: dict, candidates: list[dict], cfg_pf: dict) -> dict:
    region = {row["ticker"]: row.get("region") or "UNKNOWN" for row in candidates}
    tickers = sorted(set(weights) | set(prior))
    buys = sells = cost = 0.0
    for ticker in tickers:
        delta = float(weights.get(ticker, 0)) - float(prior.get(ticker, 0))
        policy = ((cfg_pf.get("transactionCosts") or {}).get(region.get(ticker)) or {})
        if delta > 0:
            buys += delta
            bps = float(policy.get("commissionBps", 0)) + float(policy.get("spreadBps", 0)) / 2
            cost += delta * bps / 10000
        elif delta < 0:
            sells += -delta
            bps = (float(policy.get("commissionBps", 0)) + float(policy.get("sellTaxBps", 0))
                   + float(policy.get("spreadBps", 0)) / 2)
            cost += -delta * bps / 10000
    old_cash = max(0.0, 1.0 - sum(float(x) for x in prior.values()))
    new_cash = max(0.0, 1.0 - sum(float(x) for x in weights.values()))
    return {"turnover": .5 * (buys + sells + abs(new_cash - old_cash)),
            "cost": cost, "buys": buys, "sells": sells}


def _outcome_for_decision_with_diagnostics(
        decision: dict, outcome_by_id: dict, signal_by_key: dict,
        horizon: int) -> tuple[dict | None, dict]:
    gross = benchmark = 0.0
    end_dates = []
    reasons: dict[str, set[str]] = defaultdict(set)
    regions: set[str] = set()
    for ticker, weight in decision["weights"].items():
        signal = signal_by_key.get((decision["date"], ticker))
        region = (decision.get("regionByTicker") or {}).get(ticker) or "UNKNOWN"
        regions.add(region)
        if signal is None:
            reasons["MISSING_SIGNAL"].add(ticker)
            continue
        outcome = outcome_by_id.get((signal or {}).get("id"))
        if outcome is None:
            reasons["MISSING_OUTCOME"].add(ticker)
            continue
        h = ((outcome or {}).get("horizons") or {}).get(str(horizon))
        if not h:
            reasons["HORIZON_NOT_MATURED"].add(ticker)
            continue
        if h.get("absoluteReturn") is None:
            reasons["MISSING_ABSOLUTE_RETURN"].add(ticker)
        if h.get("benchmarkReturn") is None:
            reasons["MISSING_BENCHMARK_RETURN"].add(ticker)
        if (h.get("absoluteReturn") is None
                or h.get("benchmarkReturn") is None):
            continue
        gross += float(weight) * float(h["absoluteReturn"])
        benchmark += float(weight) * float(h["benchmarkReturn"])
        end_dates.append(h.get("endDate"))
    if not decision["weights"]:
        reasons["EMPTY_PORTFOLIO"].add("<none>")
    diagnostic = {
        "complete": not reasons and bool(end_dates),
        "reasons": sorted(reasons),
        "tickersByReason": {reason: sorted(tickers)
                            for reason, tickers in sorted(reasons.items())},
        "affectedRegions": sorted(regions),
    }
    if reasons or not end_dates:
        return None, diagnostic
    return {
        "date": decision["date"], "endDate": max(end_dates),
        "selector": decision["selector"], "weights": decision["weights"],
        "cashWeight": decision["cashPct"] / 100,
        "grossReturn": gross, "benchmarkReturn": benchmark,
        "grossExcessReturn": gross - benchmark,
        "transactionCost": decision["transactionCost"],
        "costAdjustedReturn": gross - decision["transactionCost"],
        "costAdjustedExcessReturn": gross - benchmark - decision["transactionCost"],
        "turnover": decision["turnover"],
        "regionByTicker": decision.get("regionByTicker") or {},
        "top1": max(decision["weights"].values(), default=0),
        "top3": sum(sorted(decision["weights"].values(), reverse=True)[:3]),
        "effectiveNames": (1 / sum((w / sum(decision["weights"].values())) ** 2
                                   for w in decision["weights"].values())
                           if sum(decision["weights"].values()) > 0 else None),
    }, diagnostic


def _outcome_for_decision(decision: dict, outcome_by_id: dict, signal_by_key: dict,
                          horizon: int) -> dict | None:
    """Backward-compatible value-only wrapper for one portfolio decision."""
    outcome, _ = _outcome_for_decision_with_diagnostics(
        decision, outcome_by_id, signal_by_key, horizon)
    return outcome


def block_dates(rows: list[dict], horizon: int) -> list[str]:
    """Greedy non-overlapping rebalance dates, in order."""
    chosen, last_end = [], None
    for row in sorted(rows, key=lambda x: x["date"]):
        date = pd.Timestamp(row["date"])
        if last_end is None or date >= last_end:
            chosen.append(row["date"])
            last_end = pd.Timestamp(row["endDate"])
    return chosen


def shared_block_dates(rows_by_method: dict[str, list[dict]], horizon: int) -> list[str]:
    """One block schedule for every selector being compared.

    Letting each selector pick its own blocks from its own measurable dates is
    how the 08-22 report ended up comparing a champion starting 2013-01 against
    a challenger starting 2013-11, over benchmark CAGRs of 8.41% and 12.03%. A
    difference between two different periods is not a difference between two
    selectors.
    """
    common = None
    for rows in rows_by_method.values():
        dates = {row["date"] for row in rows}
        common = dates if common is None else (common & dates)
    if not common:
        return []
    # Two selectors hold different names, so the same entry date can mature on
    # different sessions. Take the later end so the schedule is non-overlapping
    # for BOTH — the earlier one would let the other selector's blocks touch.
    end_by_date: dict[str, str] = {}
    for rows in rows_by_method.values():
        for row in rows:
            if row["date"] in common:
                current = end_by_date.get(row["date"])
                if current is None or row["endDate"] > current:
                    end_by_date[row["date"]] = row["endDate"]
    return block_dates([{"date": date, "endDate": end_by_date[date]}
                        for date in sorted(common)], horizon)


def _path_metrics(rows: list[dict], horizon: int, cfg_pf: dict,
                  only_dates: list[str] | None = None) -> dict:
    if only_dates is not None:
        keep = set(only_dates)
        selected = sorted((row for row in rows if row["date"] in keep),
                          key=lambda x: x["date"])
    else:
        selected = []
        last_end = None
        for row in sorted(rows, key=lambda x: x["date"]):
            date = pd.Timestamp(row["date"])
            if last_end is None or date >= last_end:
                selected.append(row)
                last_end = pd.Timestamp(row["endDate"])
    if not selected:
        return {"available": False, "reason": "no_non_overlapping_matured_portfolios"}
    prior = {}
    # A region map that ACCUMULATES across the path. Built from the current
    # weights alone, a name being sold out of the book has no region, so
    # _turnover_cost falls back to 0 bps and the exit leg — commission, spread
    # and the 20bp KR sell tax — is charged nothing. On ~47% turnover that
    # understates cost on every rebalance, for every selector.
    region_map: dict[str, str] = {}
    for row in selected:
        region_map.update({t: r for t, r in (row.get("regionByTicker") or {}).items() if r})
        candidates = [{"ticker": ticker, "region": region_map.get(ticker)}
                      for ticker in set(row["weights"]) | set(prior)]
        cost = _turnover_cost(row["weights"], prior, candidates, cfg_pf)
        row["transactionCost"] = cost["cost"]
        row["turnover"] = cost["turnover"]
        row["costAdjustedReturn"] = row["grossReturn"] - cost["cost"]
        row["costAdjustedExcessReturn"] = row["grossExcessReturn"] - cost["cost"]
        prior = dict(row["weights"])
    returns = pd.Series([row["costAdjustedReturn"] for row in selected], dtype=float)
    benchmark = pd.Series([row["benchmarkReturn"] for row in selected], dtype=float)
    excess = returns - benchmark
    nav = (1 + returns).cumprod()
    bench_nav = (1 + benchmark).cumprod()
    drawdown = nav / nav.cummax() - 1
    periods = 252 / horizon
    years = len(selected) / periods
    cagr = float(nav.iloc[-1] ** (1 / years) - 1) if years > 0 and nav.iloc[-1] > 0 else None
    bench_cagr = (float(bench_nav.iloc[-1] ** (1 / years) - 1)
                  if years > 0 and bench_nav.iloc[-1] > 0 else None)
    std = float(returns.std(ddof=1)) if len(returns) > 1 else None
    downside = returns[returns < 0]
    downside_std = float(np.sqrt((downside ** 2).mean())) if len(downside) else None
    tracking = float(excess.std(ddof=1)) if len(excess) > 1 else None
    tail_n = max(1, int(math.ceil(len(returns) * .05)))
    nav_points = [{"date": row["endDate"], "nav": _r(value, 5),
                   "benchmarkNav": _r(bench_nav.iloc[idx], 5),
                   "drawdownPct": _r(drawdown.iloc[idx] * 100, 3),
                   "turnoverPct": _r(row["turnover"] * 100, 3)}
                  for idx, (row, value) in enumerate(zip(selected, nav))]

    def rolling_annualized_excess(years_back: int) -> list[dict]:
        points = []
        dated = [(pd.Timestamp(row["endDate"]), row) for row in selected]
        for stamp, _ in dated:
            start = stamp - pd.DateOffset(years=years_back)
            window = [row for end, row in dated if start < end <= stamp]
            expected_blocks = years_back * periods
            if len(window) < max(2, math.ceil(expected_blocks * .8)):
                continue
            portfolio_growth = float(np.prod([1 + row["costAdjustedReturn"] for row in window]))
            benchmark_growth = float(np.prod([1 + row["benchmarkReturn"] for row in window]))
            span_years = len(window) / periods
            if portfolio_growth <= 0 or benchmark_growth <= 0 or span_years <= 0:
                continue
            p_cagr = portfolio_growth ** (1 / span_years) - 1
            b_cagr = benchmark_growth ** (1 / span_years) - 1
            points.append({"date": stamp.strftime("%Y-%m-%d"),
                           "annualizedExcessPct": _r((p_cagr - b_cagr) * 100, 3)})
        compact = {row["date"][:7]: row for row in points}
        return list(compact.values())

    return {
        "available": True, "pathMethod": f"NON_OVERLAPPING_{horizon}D_REBALANCE_BLOCKS",
        "periods": len(selected), "firstDate": selected[0]["date"],
        "lastEndDate": selected[-1]["endDate"],
        "cagrPct": _r(cagr * 100, 3) if cagr is not None else None,
        "benchmarkCagrPct": _r(bench_cagr * 100, 3) if bench_cagr is not None else None,
        "annualizedExcessPct": (_r((cagr - bench_cagr) * 100, 3)
                                if cagr is not None and bench_cagr is not None else None),
        "sharpe": _r(returns.mean() / std * math.sqrt(periods), 3) if std and std > 0 else None,
        "sortino": (_r(returns.mean() / downside_std * math.sqrt(periods), 3)
                    if downside_std and downside_std > 0 else None),
        "annualizedRealizedVolPct": _r(std * math.sqrt(periods) * 100, 3) if std else None,
        "annualizedDownsideVolPct": (_r(downside_std * math.sqrt(periods) * 100, 3)
                                      if downside_std else None),
        "mddPct": _r(drawdown.min() * 100, 3),
        "cvar95Pct": _r(returns.nsmallest(tail_n).mean() * 100, 3),
        "hitRatePct": _r((excess > 0).mean() * 100, 2),
        "informationRatio": (_r(excess.mean() / tracking * math.sqrt(periods), 3)
                             if tracking and tracking > 0 else None),
        "trackingErrorPct": _r(tracking * math.sqrt(periods) * 100, 3) if tracking else None,
        "averageTurnoverPct": _r(np.mean([row["turnover"] for row in selected]) * 100, 2),
        "averageTop1Pct": _r(np.mean([row["top1"] for row in selected]) * 100, 2),
        "averageTop3Pct": _r(np.mean([row["top3"] for row in selected]) * 100, 2),
        "averageEffectiveNames": _r(np.mean([row["effectiveNames"] for row in selected
                                              if row["effectiveNames"] is not None]), 2),
        "rolling3YAnnualizedExcess": rolling_annualized_excess(3),
        "rolling5YAnnualizedExcess": rolling_annualized_excess(5),
        "nav": nav_points,
    }


def _bootstrap_ci(values: np.ndarray, *, draws: int = 2000, seed: int = 11) -> list[float]:
    """Percentile CI over non-overlapping blocks, which are ~independent."""
    if values.size < 2:
        return [None, None]
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, values.size, size=(draws, values.size))
    means = values[idx].mean(axis=1)
    return [_r(float(np.percentile(means, 2.5)) * 100, 3),
            _r(float(np.percentile(means, 97.5)) * 100, 3)]


def paired_comparison(rows_by_method: dict[str, list[dict]], dates: list[str],
                      *, horizon: int) -> dict:
    """Champion minus challenger on the same blocks, with an error bar.

    The previous report decided "CHALLENGER_BETTER" by comparing two point
    estimates with no uncertainty attached, on two different periods. On ~130
    blocks the sampling error of an annualized excess is wider than any gap
    either selector has ever shown, so a bare inequality is not a finding.
    """
    if not dates or len(rows_by_method) != 2:
        return {"available": False, "reason": "no_shared_blocks"}
    keep = set(dates)
    series = {}
    for method, rows in rows_by_method.items():
        by_date = {row["date"]: row for row in rows if row["date"] in keep}
        if len(by_date) != len(keep):
            return {"available": False, "reason": "selectors_not_measurable_on_same_blocks"}
        series[method] = np.array([by_date[date]["costAdjustedExcessReturn"]
                                   for date in dates], dtype=float)
    left, right = CHAMPION, CHALLENGER
    diff = series[left] - series[right]
    periods = 252 / horizon
    per_method = {}
    for method, values in series.items():
        per_method[method] = {
            "meanCostAdjustedExcessPct": _r(float(values.mean()) * 100, 3),
            "ci95Pct": _bootstrap_ci(values),
            "annualizedExcessPct": _r(float(values.mean()) * periods * 100, 3),
        }
    ci = _bootstrap_ci(diff)
    separated = bool(ci[0] is not None and (ci[0] > 0 or ci[1] < 0))
    return {
        "available": True,
        "blocks": len(dates),
        "firstDate": dates[0], "lastDate": dates[-1],
        "horizonDays": int(horizon),
        "bySelector": per_method,
        "championMinusChallengerPct": _r(float(diff.mean()) * 100, 3),
        "championMinusChallengerCi95Pct": ci,
        "separated": separated,
        "verdict": ("CHAMPION_BETTER" if separated and ci[0] > 0 else
                    "CHALLENGER_BETTER" if separated else "INDISTINGUISHABLE"),
        "methodKo": ("동일 블록·동일 기간·동일 벤치마크 구성에서의 쌍대 차이입니다. "
                     "95% 구간이 0을 포함하면 두 selector는 구분되지 않습니다."),
    }


def selection_null(contexts: dict, priced_by_date: dict, rows: list[dict],
                   dates: list[str], *, cfg_pf: dict, horizon: int, draws: int,
                   seed: int = 20260825) -> dict:
    """Run the same construction with the conviction scores permuted across names.

    Reuses ``KP.selection_and_baseline`` exactly as the live path does, so the
    only difference between the real book and a draw is which name carries which
    score. Each draw walks the same block schedule in order, so its turnover —
    and therefore its cost — is built the same way the real path's is.
    """
    if not dates:
        return {"available": False, "reason": "no_shared_blocks"}
    # A block date is usable only when EVERY name in that date's pool has a
    # matured outcome. Otherwise a draw that happens to pick the one unpriced
    # name dies, and with ~150 dates per draw even a 1% per-date failure rate
    # kills four draws in five — the null would quietly shrink to nothing.
    # Restricting dates instead keeps every draw complete, and the real book is
    # measured on exactly the same dates.
    usable, pool_gaps = [], 0
    for date in dates:
        if date not in contexts:
            continue
        priced = priced_by_date.get(date) or {}
        pool = [row["ticker"] for row in contexts[date][0]]
        if pool and all(ticker in priced for ticker in pool):
            usable.append(date)
        else:
            pool_gaps += 1
    if len(usable) < 2:
        return {"available": False, "reason": "no_fully_priced_block_dates",
                "blocksDroppedForPoolCoverage": pool_gaps}
    outcome_lookup = {row["date"]: row for row in rows}
    missing = [date for date in usable if date not in outcome_lookup]
    if missing:
        return {"available": False, "reason": "actual_path_not_measurable_on_blocks"}

    periods = 252 / horizon
    # The real conviction rows per date, computed once. Each draw reassigns these
    # scores, so every draw faces the same eligibility facts the real book did.
    base_scores = {date: KP.conviction_scores(contexts[date][0], cfg_pf)
                   for date in usable}

    def run_mode(mode: str) -> tuple[list[dict], dict]:
        samples: list[dict] = []
        discarded: dict[str, int] = defaultdict(int)
        for draw in range(int(draws)):
            rng = np.random.default_rng(seed + draw)
            keys: dict[str, float] = {}
            prior: dict[str, float] = {}
            null_regions: dict[str, str] = {}
            excess, returns, turnover = [], [], []
            reason = None
            for date in usable:
                candidates, macro = contexts[date]
                if not candidates:
                    reason = "no_candidates"
                    break
                scored = (SN.permuted_scores(base_scores[date], rng)
                          if mode == SN.INDEPENDENT
                          else SN.persistent_scores(base_scores[date], rng, keys))
                blob = KP.selection_and_baseline(
                    candidates, cfg_pf, macro, scored=scored, method=SN.NULL_METHOD)
                weights = blob["weights"]
                if not weights:
                    reason = "empty_portfolio"
                    break
                priced = _null_return(weights, priced_by_date.get(date))
                if priced is None:
                    reason = "drawn_name_outcome_not_matured"
                    break
                null_regions.update({row["ticker"]: row.get("region")
                                     for row in candidates if row.get("region")})
                names = [{"ticker": ticker, "region": null_regions.get(ticker)}
                         for ticker in set(weights) | set(prior)]
                leg = _turnover_cost(weights, prior, names, cfg_pf)
                prior = dict(weights)
                turnover.append(leg["turnover"])
                returns.append(priced["gross"] - leg["cost"])
                excess.append(priced["gross"] - priced["benchmark"] - leg["cost"])
            if len(excess) != len(usable):
                discarded[reason or "incomplete_path"] += 1
                continue
            sample = _path_statistics(np.array(returns), np.array(excess), periods)
            sample["turnoverPct"] = float(np.mean(turnover)) * 100
            samples.append(sample)
        return samples, dict(sorted(discarded.items()))

    actual_returns = np.array([outcome_lookup[d]["costAdjustedReturn"] for d in usable])
    actual_excess = np.array([outcome_lookup[d]["costAdjustedExcessReturn"] for d in usable])
    observed = _path_statistics(actual_returns, actual_excess, periods)
    actual_turnover = float(np.mean([outcome_lookup[d]["turnover"] for d in usable])) * 100

    by_mode: dict[str, dict] = {}
    for mode in SN.MODES:
        samples, discarded = run_mode(mode)
        if not samples:
            by_mode[mode] = {"available": False, "reason": "no_complete_null_draw",
                             "discardedDraws": discarded}
            continue
        statistics = {
            name: SN.summarize(observed.get(name), [row.get(name) for row in samples],
                               higher_is_better=True, label=name)
            for name in ("annualizedExcessPct", "informationRatio", "sharpe")
        }
        by_mode[mode] = {
            "available": True,
            "draws": len(samples),
            "discardedDraws": discarded,
            "nullMedianTurnoverPct": _r(float(np.median(
                [row["turnoverPct"] for row in samples])), 2),
            "statistics": statistics,
            "overall": SN.overall_verdict(statistics),
        }

    return {
        "available": True,
        "method": SN.NULL_METHOD,
        "modes": list(SN.MODES),
        "requestedDraws": int(draws),
        "blocks": len(usable),
        "blocksDroppedForPoolCoverage": pool_gaps,
        "firstDate": usable[0], "lastDate": usable[-1],
        "horizonDays": int(horizon),
        "actualTurnoverPct": _r(actual_turnover, 2),
        "actual": {name: _r(observed.get(name), 4) for name in observed},
        "heldFixed": ["dates", "research candidate pool", "name/sector/region caps",
                      "entry-state and evidence exclusions", "regime cash floor",
                      "baseline weighting function", "transaction costs",
                      "distribution of conviction scores"],
        "varied": ["which name each conviction score is attached to",
                   "the alpha selection floor, which is itself a score decision"],
        "byMode": by_mode,
        "overall": SN.combined_verdict(by_mode),
    }


def _null_return(weights: dict, priced: dict | None) -> dict | None:
    """Realised gross and benchmark return for a randomly drawn book."""
    if not priced:
        return None
    gross = benchmark = 0.0
    for ticker, weight in weights.items():
        cell = priced.get(ticker)
        if cell is None:
            return None
        gross += float(weight) * cell["absoluteReturn"]
        benchmark += float(weight) * cell["benchmarkReturn"]
    return {"gross": gross, "benchmark": benchmark}


def _path_statistics(returns: np.ndarray, excess: np.ndarray, periods: float) -> dict:
    """The three headline statistics, computed identically for real and null."""
    if returns.size < 2:
        return {"annualizedExcessPct": None, "informationRatio": None, "sharpe": None}
    nav = float(np.prod(1 + returns))
    bench_nav = float(np.prod(1 + (returns - excess)))
    years = returns.size / periods
    cagr = nav ** (1 / years) - 1 if nav > 0 and years > 0 else None
    bench_cagr = bench_nav ** (1 / years) - 1 if bench_nav > 0 and years > 0 else None
    std = float(returns.std(ddof=1))
    tracking = float(excess.std(ddof=1))
    return {
        "annualizedExcessPct": ((cagr - bench_cagr) * 100
                                if cagr is not None and bench_cagr is not None else None),
        "informationRatio": (float(excess.mean()) / tracking * math.sqrt(periods)
                             if tracking > 0 else None),
        "sharpe": (float(returns.mean()) / std * math.sqrt(periods)
                   if std > 0 else None),
    }


def _decision_exposure(decision: dict, key: str) -> dict[str, float]:
    lookup = {row.get("ticker"): row.get(key) or "UNKNOWN"
              for row in decision.get("selected") or []}
    result: dict[str, float] = defaultdict(float)
    for ticker, weight in (decision.get("weights") or {}).items():
        result[lookup.get(ticker, "UNKNOWN")] += float(weight)
    return dict(result)


def _allocation_l1(left: dict, right: dict) -> float:
    keys = set(left) | set(right)
    return sum(abs(float(left.get(key, 0)) - float(right.get(key, 0))) for key in keys)


def portfolio_replay(signals: list[dict], outcomes: list[dict], *, cfg_lt: dict,
                     cfg_pf: dict, diagnostics: dict) -> dict:
    """Replay champion/challenger on the same dates, candidates and constraints."""
    by_date: dict[str, list[dict]] = defaultdict(list)
    for row in signals:
        by_date[row.get("date")].append(row)
    outcome_by_id = {row.get("id"): row for row in outcomes}
    signal_by_key = {(row.get("date"), row.get("ticker")): row for row in signals}
    calibrator = ExpandingBucketCalibration(
        outcomes, horizon=int(cfg_pf.get("horizonDays", 126)),
        prior_strength=float(cfg_pf.get("shrinkagePriorStrength", 30)), min_dates=20)
    prior_research: dict[str, set[str]] = {}
    prior_weights = {CHAMPION: {}, CHALLENGER: {}}
    decisions = {CHAMPION: [], CHALLENGER: []}
    # The research pool is already narrowed to ~10 names per region, so keeping
    # every date's pool costs little and is what lets the null replay the same
    # construction without a second walk over the ledger.
    contexts: dict[str, tuple] = {}
    overlaps = []
    full_fidelity_dates = 0
    full_fidelity_ready = bool(
        diagnostics.get("historicalUniverseAvailable")
        and _finite(diagnostics.get("constituentCoveragePct")) == 100.0
        and diagnostics.get("fundamentalsPit")
        and diagnostics.get("macroPitStatus") == pit_data.PIT_EXACT)

    for date in sorted(d for d in by_date if d):
        rows = by_date[date]
        calibrator.advance(date)
        if full_fidelity_ready and any(
                all((row.get("factorPercentiles") or {}).get(sleeve) is not None
                    for sleeve in FULL_SLEEVES) for row in rows):
            full_fidelity_dates += 1
        candidates = _research_candidates(rows, cfg_lt, prior_research, price_proxy=True)
        if not candidates:
            continue
        macro_label = next((row.get("macroRegime") for row in rows if row.get("macroRegime")), None)
        macro_confidence = next((_finite(row.get("macroConfidence")) for row in rows
                                 if _finite(row.get("macroConfidence")) is not None), None)
        macro = {"regime": macro_label, "confidence": macro_confidence}
        contexts[date] = (candidates, macro)
        champion = KP.selection_and_baseline(candidates, cfg_pf, macro)
        challenger_scores = _challenger_scores(candidates, calibrator, cfg_pf)
        challenger = KP.selection_and_baseline(
            candidates, cfg_pf, macro, scored=challenger_scores, method=CHALLENGER)
        day_sets = {}
        for method, blob in ((CHAMPION, champion), (CHALLENGER, challenger)):
            weights = blob["weights"]
            cost = _turnover_cost(weights, prior_weights[method], candidates, cfg_pf)
            prior_weights[method] = dict(weights)
            selected = {row["ticker"]: row for row in blob["selected"]}
            ranking = blob["selection"].get("ranking") or []
            rank_by_ticker = {row.get("ticker"): index + 1
                              for index, row in enumerate(ranking)}
            ranking_by_ticker = {row.get("ticker"): row for row in ranking}
            decision = {
                "replayDate": date, "date": date, "modelVersion": diagnostics.get("modelVersion"),
                "replayVersion": diagnostics.get("replayVersion"), "selector": method,
                "selectedTickers": list(weights), "selected": [{
                    "ticker": ticker, "region": selected[ticker].get("region"),
                    "sector": selected[ticker].get("sector"),
                    "alphaPercentile": selected[ticker].get("alphaPercentile"),
                    "factorPercentiles": selected[ticker].get("factorPercentiles"),
                    "sleevesAvailable": selected[ticker].get("sleevesAvailable"),
                    "sleevesWithheld": selected[ticker].get("sleevesWithheld"),
                    "factorCoverage": selected[ticker].get("factorCoverage"),
                    "sourceQuality": selected[ticker].get("sourceQuality"),
                    "pitAvailability": selected[ticker].get("pitAvailability"),
                    "entryState": selected[ticker].get("entryState"),
                    "entryMultiplier": _r(KP._state_multiplier(selected[ticker], cfg_pf), 3),
                    "evidenceCoverage": selected[ticker].get("evidenceCoverage"),
                    "downsideVolPct": (selected[ticker].get("risk") or {}).get("downsideVolPct"),
                    "convictionScore": _finite(
                        (ranking_by_ticker.get(ticker) or {}).get("convictionScore")
                        if (ranking_by_ticker.get(ticker) or {}).get("convictionScore") is not None
                        else (ranking_by_ticker.get(ticker) or {}).get("score")),
                    "selectionRank": rank_by_ticker.get(ticker),
                    "historicalAlphaBucketCalibration": calibrator.expected(
                        selected[ticker].get("region"), selected[ticker].get("alphaPercentile")),
                    "baselineWeight": weights[ticker], "finalHistoricalReplayWeight": weights[ticker],
                } for ticker in weights],
                "weights": weights, "cashPct": blob["cashPct"],
                "regionByTicker": {ticker: selected[ticker].get("region") for ticker in weights},
                "sectorByTicker": {ticker: selected[ticker].get("sector") for ticker in weights},
                "benchmarkByTicker": {ticker: selected[ticker].get("benchmark") for ticker in weights},
                "macroRegime": macro_label,
                "macroEquityBudget": {
                    "maxEquityPct": _r(100 - blob["appliedMinCashPct"], 2),
                    "source": "REGIME_CASH_FLOOR_IMPLIED",
                    "historicalRiskBudgetAvailable": False,
                },
                "appliedMinCashPct": blob["appliedMinCashPct"],
                "nearestMisses": [row for row in ranking if not row.get("selected")][:5],
                "transactionCost": cost["cost"], "turnover": cost["turnover"],
                "transactionCostAssumptions": cfg_pf.get("transactionCosts") or {},
                "dataDiagnostics": {
                    "basis": "PRICE_SLEEVES_ONLY_AUDIT_PROXY",
                    "fullProductionFidelity": False,
                    "survivorshipRisk": diagnostics.get("survivorshipRisk"),
                    "fundamentalsPit": diagnostics.get("fundamentalsPit"),
                },
            }
            decisions[method].append(decision)
            day_sets[method] = set(weights)
        union = day_sets[CHAMPION] | day_sets[CHALLENGER]
        overlaps.append(len(day_sets[CHAMPION] & day_sets[CHALLENGER]) / max(1, len(union)))

    horizon_results = {method: {} for method in decisions}
    summaries = {}
    rows_by_method_horizon: dict[int, dict[str, list[dict]]] = defaultdict(dict)
    min_completeness = float(cfg_pf.get("minPortfolioCompletenessPct", 90.0))
    for method, method_decisions in decisions.items():
        for horizon in HORIZONS:
            rows = []
            dropped_by_reason: dict[str, int] = defaultdict(int)
            affected_regions: set[str] = set()
            affected_tickers: set[str] = set()
            for decision in method_decisions:
                outcome, diagnostic = _outcome_for_decision_with_diagnostics(
                    decision, outcome_by_id, signal_by_key, horizon)
                if outcome:
                    rows.append(outcome)
                else:
                    for reason in diagnostic["reasons"]:
                        dropped_by_reason[reason] += 1
                        affected_tickers.update(
                            diagnostic["tickersByReason"].get(reason) or [])
                    affected_regions.update(diagnostic["affectedRegions"])
            completeness = (len(rows) / len(method_decisions) * 100
                            if method_decisions else None)
            outcome_coverage = {
                "totalDecisions": len(method_decisions),
                "completeOutcomes": len(rows),
                "droppedDecisions": len(method_decisions) - len(rows),
                "completenessPct": _r(completeness, 2),
                "minimumCompletenessPct": min_completeness,
                # A dropped portfolio is not a random omission: a name without a
                # matured benchmark is disproportionately a halted or delisted
                # one, so a path built from the survivors is a different
                # strategy. Publish the headline only when nearly all of the
                # book was measurable, and say so rather than renormalizing.
                "sufficientForPath": bool(completeness is not None
                                          and completeness >= min_completeness),
                "droppedByReason": dict(sorted(dropped_by_reason.items())),
                "affectedRegions": sorted(affected_regions),
                "affectedTickersSample": sorted(affected_tickers)[:20],
            }
            rows_by_method_horizon[horizon][method] = rows
            horizon_results[method][str(horizon)] = {
                "observations": len(rows),
                "uniqueDates": len({row["date"] for row in rows}),
                "effectiveIndependentDates": _non_overlapping_count(
                    [row["date"] for row in rows], horizon),
                "meanGrossReturnPct": _r(np.mean([row["grossReturn"] for row in rows]) * 100, 3) if rows else None,
                "meanBenchmarkReturnPct": _r(np.mean([row["benchmarkReturn"] for row in rows]) * 100, 3) if rows else None,
                "meanGrossExcessPct": _r(np.mean([row["grossExcessReturn"] for row in rows]) * 100, 3) if rows else None,
                "meanCostAdjustedReturnPct": _r(np.mean([row["costAdjustedReturn"] for row in rows]) * 100, 3) if rows else None,
                "meanCostAdjustedExcessPct": _r(np.mean([row["costAdjustedExcessReturn"] for row in rows]) * 100, 3) if rows else None,
                "outcomeCoverage": outcome_coverage,
                "path": (_path_metrics(rows, horizon, cfg_pf)
                         if outcome_coverage["sufficientForPath"]
                         else {"available": False,
                               "reason": "portfolio_completeness_below_threshold",
                               "completenessPct": _r(completeness, 2),
                               "minimumCompletenessPct": min_completeness}),
            }

    # One block schedule for both selectors, so the comparison is like for like.
    shared = shared_block_dates(rows_by_method_horizon[HEADLINE_HORIZON], HEADLINE_HORIZON)
    for method in decisions:
        rows = rows_by_method_horizon[HEADLINE_HORIZON].get(method) or []
        coverage = horizon_results[method][str(HEADLINE_HORIZON)]["outcomeCoverage"]
        if not coverage["sufficientForPath"] or not shared:
            summaries[method] = horizon_results[method][str(HEADLINE_HORIZON)]["path"]
            continue
        summary = _path_metrics(rows, HEADLINE_HORIZON, cfg_pf, only_dates=shared)
        summary["blockScheduleShared"] = True
        summary["blockScheduleBasis"] = "DATES_MEASURABLE_FOR_EVERY_SELECTOR"
        summaries[method] = summary
        horizon_results[method][str(HEADLINE_HORIZON)]["path"] = summary

    champion_summary = summaries.get(CHAMPION) or {}
    challenger_summary = summaries.get(CHALLENGER) or {}
    by_method_date = {method: {row["date"]: row for row in rows}
                      for method, rows in decisions.items()}
    common_dates = sorted(set(by_method_date[CHAMPION]) & set(by_method_date[CHALLENGER]))
    allocation_differences = []
    turnover_differences = []
    region_differences = []
    sector_differences = []
    for date in common_dates:
        champion_day = by_method_date[CHAMPION][date]
        challenger_day = by_method_date[CHALLENGER][date]
        allocation_differences.append(_allocation_l1(
            champion_day["weights"], challenger_day["weights"]) / 2)
        turnover_differences.append(abs(
            champion_day["turnover"] - challenger_day["turnover"]))
        region_differences.append(_allocation_l1(
            _decision_exposure(champion_day, "region"),
            _decision_exposure(challenger_day, "region")) / 2)
        sector_differences.append(_allocation_l1(
            _decision_exposure(champion_day, "sector"),
            _decision_exposure(challenger_day, "sector")) / 2)
    # Every name's realised outcome at the headline horizon, so a randomly drawn
    # book can be priced on exactly the returns the real one was priced on.
    priced_by_date: dict[str, dict] = defaultdict(dict)
    for date, (candidates, _macro) in contexts.items():
        for candidate in candidates:
            signal = signal_by_key.get((date, candidate["ticker"]))
            cell = ((outcome_by_id.get((signal or {}).get("id")) or {})
                    .get("horizons") or {}).get(str(HEADLINE_HORIZON)) or {}
            if cell.get("absoluteReturn") is None or cell.get("benchmarkReturn") is None:
                continue
            priced_by_date[date][candidate["ticker"]] = {
                "absoluteReturn": float(cell["absoluteReturn"]),
                "benchmarkReturn": float(cell["benchmarkReturn"]),
            }

    comparison_paired = paired_comparison(
        {method: rows_by_method_horizon[HEADLINE_HORIZON].get(method) or []
         for method in decisions},
        shared, horizon=HEADLINE_HORIZON)
    null_report = selection_null(
        contexts, priced_by_date,
        rows_by_method_horizon[HEADLINE_HORIZON].get(CHAMPION) or [], shared,
        cfg_pf=cfg_pf, horizon=HEADLINE_HORIZON,
        draws=int(cfg_pf.get("selectionNullDraws", SN.DEFAULT_DRAWS)))

    integrity = data_integrity(diagnostics, signals)
    comparable = all(summary.get(key) is not None
                     for summary in (champion_summary, challenger_summary)
                     for key in ("annualizedExcessPct", "sharpe", "mddPct"))
    challenger_better = bool(comparable
        and challenger_summary["annualizedExcessPct"] > champion_summary["annualizedExcessPct"]
        and challenger_summary["sharpe"] >= champion_summary["sharpe"]
        and challenger_summary["mddPct"] >= champion_summary["mddPct"])
    champion_better = bool(comparable
        and champion_summary["annualizedExcessPct"] > challenger_summary["annualizedExcessPct"]
        and champion_summary["sharpe"] >= challenger_summary["sharpe"]
        and champion_summary["mddPct"] >= challenger_summary["mddPct"])
    return {
        "available": bool(decisions[CHAMPION]),
        "basis": "PRICE_SLEEVES_ONLY_AUDIT_PROXY",
        "fullProductionFidelity": False,
        "fullProductionFidelityDates": full_fidelity_dates,
        "warningKo": ("현재 실전 모델에는 Value/Quality가 포함되지만 과거 시점별 재무 데이터가 없어 "
                      "해당 부분은 동일 조건 백테스트가 아닙니다."),
        "selectors": {CHAMPION: {"summary": champion_summary,
                                  "horizons": horizon_results[CHAMPION]},
                      CHALLENGER: {"summary": challenger_summary,
                                   "horizons": horizon_results[CHALLENGER]}},
        "comparison": {
            "averagePortfolioJaccardPct": _r(np.mean(overlaps) * 100, 2) if overlaps else None,
            "averageNameAllocationDifferencePct": (_r(np.mean(allocation_differences) * 100, 2)
                                                    if allocation_differences else None),
            "averageTurnoverDifferencePct": (_r(np.mean(turnover_differences) * 100, 2)
                                              if turnover_differences else None),
            "averageRegionExposureDifferencePct": (_r(np.mean(region_differences) * 100, 2)
                                                    if region_differences else None),
            "averageSectorExposureDifferencePct": (_r(np.mean(sector_differences) * 100, 2)
                                                    if sector_differences else None),
            "historicalChampionBetter": champion_better,
            "historicalChallengerBetter": challenger_better,
            "historicalComparison": ("CHAMPION_BETTER" if champion_better else
                                     "CHALLENGER_BETTER" if challenger_better else "MIXED"),
            "productionSelector": CHAMPION,
            # The point-estimate inequality above is kept for continuity, but it
            # carries no uncertainty and is not what decides anything. This is.
            "paired": comparison_paired,
            "decisiveComparison": "paired",
        },
        "selectionNull": null_report,
        "promotionEvidence": {
            "historicalChampionBetter": champion_better,
            "historicalChallengerBetter": challenger_better,
            "historicalComparison": ("CHAMPION_BETTER" if champion_better else
                                     "CHALLENGER_BETTER" if challenger_better else "MIXED"),
            "prospectiveChampionBetter": "NOT_YET_MATURED",
            "prospectiveChallengerBetter": "NOT_YET_MATURED",
            "integrityGate": integrity["integrityGate"],
            "enoughIndependentPeriods": bool(
                (champion_summary.get("periods") or 0) >= 30
                and (challenger_summary.get("periods") or 0) >= 30),
            "promotionEligible": False,
            "humanApprovalRequired": True,
        },
        # Keep the artifact compact. Per-date rows are useful for audit, not UI.
        "replayDateCount": len(decisions[CHAMPION]),
        "auditSample": {method: rows[-3:] for method, rows in decisions.items()},
    }


def data_integrity(diagnostics: dict, signals: list[dict]) -> dict:
    regions = sorted({row.get("region") for row in signals if row.get("region")})
    universe_available = bool(diagnostics.get(
        "historicalUniverseAvailable", diagnostics.get("survivorshipRisk") == "LOW"))
    constituent_coverage = _finite(diagnostics.get("constituentCoveragePct"))
    universe_ready = bool(universe_available and constituent_coverage == 100.0)
    fundamentals_ready = bool(diagnostics.get("fundamentalsPit"))
    macro_ready = diagnostics.get("macroPitStatus") == pit_data.PIT_EXACT
    benchmark_gate = diagnostics.get("benchmarkCoverageGate") or {}
    benchmark_ready = (bool(benchmark_gate.get("eligible"))
                       if "eligible" in benchmark_gate else None)
    checks = {"historicalUniverse": universe_ready,
              "pointInTimeFundamentals": fundamentals_ready,
              "vintageMacro": macro_ready,
              "benchmarkCoverage": benchmark_ready}
    return {
        "historicalUniverseAvailable": universe_available,
        "constituentCoveragePct": _r(constituent_coverage, 2),
        "universeSource": (diagnostics.get("universeSource")
                           or ("HISTORICAL_MEMBERSHIP_DATASET" if universe_available
                               else "CURRENT_UNIVERSE_WITH_PRICE_HISTORY_FILTER_ONLY")),
        "firstReliableUniverseDate": diagnostics.get("firstReliableUniverseDate"),
        "survivorshipRisk": diagnostics.get("survivorshipRisk") or "HIGH",
        "affectedObservationsPct": _r(diagnostics.get(
            "affectedObservationsPct", 0.0 if universe_ready else 100.0), 2),
        "affectedRegions": diagnostics.get("affectedRegions", [] if universe_ready else regions),
        "impactOnPromotionEligibility": ("NONE" if universe_ready
                                         else "KELLY_AND_SELECTOR_PROMOTION_BLOCKED"),
        "pitFundamentals": {
            "available": fundamentals_ready,
            "rule": "availableFrom <= replayDate",
            "currentSnapshotBackfillAllowed": False,
        },
        "macroVintage": diagnostics.get("macroPitStatus"),
        "benchmarkCoverageGate": benchmark_gate or {"eligible": None,
                                                       "reason": "not_assessed"},
        "integrityGate": {
            "eligible": all(ok is True for ok in checks.values()),
            "checks": checks,
            "failures": [key for key, ok in checks.items() if ok is False],
            "unassessable": [key for key, ok in checks.items() if ok is None],
        },
        "historicalResultLabel": ("HISTORICAL_OOS" if universe_ready
                                  else "SURVIVORSHIP_BIAS_UNRESOLVED"),
    }


def expected_realized_gap(outcomes: list[dict], *, horizon=126) -> dict:
    calibrator = ExpandingBucketCalibration(outcomes, horizon=horizon, min_dates=20)
    frame = HO.horizon_frame(outcomes, horizon, cost_adjusted=False)
    if frame.empty:
        return {"status": "NOT_AVAILABLE", "regions": {}}
    frame = frame.dropna(subset=["outcomeEndDate", "alphaPercentile"]).copy()
    frame["bucket"] = [_bucket(value, (0, 60, 80, 90, 95, 100))
                       for value in frame["alphaPercentile"]]
    actual = (frame.groupby(["date", "region", "bucket"], dropna=True)
              ["costAdjustedExcessReturn"].mean().reset_index()
              .sort_values(["date", "region", "bucket"]))
    predictions = []
    for date, group in actual.groupby("date", sort=True):
        calibrator.advance(date)
        for _, row in group.iterrows():
            midpoint = np.mean([float(x) for x in str(row["bucket"]).split("-")])
            estimate = calibrator.expected(row["region"], midpoint)
            if estimate:
                predictions.append({"date": pd.Timestamp(date), "region": row["region"],
                                    "predicted": estimate["expectedExcessReturnPct"] / 100,
                                    "realized": float(row["costAdjustedExcessReturn"])})
    regions = {}
    pred = pd.DataFrame(predictions)
    if len(pred):
        for region, group in pred.groupby("region"):
            error = group["predicted"] - group["realized"]
            slope = intercept = None
            if len(group) >= 3 and float(group["predicted"].std()) > 0:
                slope, intercept = np.polyfit(group["predicted"], group["realized"], 1)
            regions[region] = {
                "observations": int(len(group)), "uniqueDates": int(group["date"].nunique()),
                "effectiveIndependentDates": _non_overlapping_count(group["date"], horizon),
                "meanAbsoluteForecastErrorPct": _r(error.abs().mean() * 100, 3),
                "signedBiasPct": _r(error.mean() * 100, 3),
                "predictedMeanExcessPct": _r(group["predicted"].mean() * 100, 3),
                "realizedMeanExcessPct": _r(group["realized"].mean() * 100, 3),
                "calibrationSlope": _r(slope, 4), "calibrationIntercept": _r(intercept, 4),
            }
    return {"status": "AVAILABLE" if regions else "NOT_AVAILABLE", "regions": regions,
            "evidenceClass": "HISTORICAL_OOS",
            "labelAvailabilityPolicy": "OUTCOME_END_DATE_LTE_PREDICTION_DATE"}


def build_report(signals: list[dict], outcomes: list[dict], *, cfg_lt: dict,
                 cfg_pf: dict, diagnostics: dict, replay_version: str | None = None,
                 model_version: str | None = None) -> dict:
    signals, rejected_signals = _generation_filter(
        signals, replay_version=replay_version, model_version=model_version)
    valid_ids = {row.get("id") for row in signals}
    outcomes = [row for row in outcomes if row.get("id") in valid_ids]
    outcomes, rejected_outcomes = _generation_filter(
        outcomes, replay_version=replay_version, model_version=model_version)
    alpha = alpha_diagnostics(
        signals, outcomes,
        edges=cfg_pf.get("alphaPercentileBuckets") or (0, 60, 80, 90, 95, 100),
        pit_fundamentals=bool(diagnostics.get("fundamentalsPit")))
    portfolio = portfolio_replay(signals, outcomes, cfg_lt=cfg_lt, cfg_pf=cfg_pf,
                                 diagnostics=diagnostics)
    integrity = data_integrity(diagnostics, signals)
    gap = expected_realized_gap(outcomes, horizon=int(cfg_pf.get("horizonDays", 126)))
    contract_failures = []
    if not signals:
        contract_failures.append("no_current_generation_signals")
    benchmark_gate = diagnostics.get("benchmarkCoverageGate") or {}
    if benchmark_gate.get("eligible") is not True:
        contract_failures.append(
            "benchmark_coverage_gate_failed" if "eligible" in benchmark_gate
            else "benchmark_coverage_gate_not_assessed")
    target_horizon = str(int(cfg_pf.get("horizonDays", 126)))
    for method, blob in (portfolio.get("selectors") or {}).items():
        coverage = (((blob.get("horizons") or {}).get(target_horizon) or {})
                    .get("outcomeCoverage") or {})
        if (int(coverage.get("totalDecisions") or 0) > 0
                and int(coverage.get("completeOutcomes") or 0) == 0
                and int((coverage.get("droppedByReason") or {}).get(
                    "MISSING_BENCHMARK_RETURN") or 0) > 0):
            contract_failures.append(
                f"{method}:{target_horizon}D_all_portfolios_dropped_for_missing_benchmark")
    # A sleeve carrying a live weight against its own historical evidence is a
    # standing unvalidated claim, so it is named in the report rather than left
    # for a reader to reconstruct from the per-horizon IC tables.
    sign_contradiction_claims = [
        f"live composite weight for the {row['region']} {row['sleeve']} sleeve, "
        f"whose historical rank IC contradicts its assumed positive sign at "
        f"{len(row['contradictedHorizons'])} of {len(row['evidence'])} horizons"
        for row in ((alpha.get("sleeveSignConsistency") or {})
                    .get("byRegionSleeve") or {}).values()
        if row.get("status") == "CONTRADICTED"
    ]
    return {
        "reportVersion": REPORT_VERSION,
        "evidenceClass": "HISTORICAL_OOS",
        "replayVersion": replay_version or diagnostics.get("replayVersion"),
        "dataVersion": diagnostics.get("dataVersion"),
        "modelVersion": model_version or diagnostics.get("modelVersion"),
        "generationIsolation": {"method": "EXACT_REPLAY_AND_MODEL_VERSION",
                                "excludedSignals": rejected_signals,
                                "excludedOutcomes": rejected_outcomes},
        "contractValidation": {
            "eligible": not contract_failures,
            "status": "VALID" if not contract_failures else "BLOCKED",
            "failures": contract_failures,
        },
        "alphaDiagnostics": alpha,
        "portfolioReplay": portfolio,
        "forecastGap": {"historicalOos": gap,
                        "prospectivePaper": {"status": "SEPARATE_LEDGER_REQUIRED"}},
        "dataIntegrity": integrity,
        "claims": {
            "actuallyValidated": [
                "same-session regional benchmark coverage above the publication gate",
                "price-based momentum and low-vol historical ranking diagnostics",
                "price-sleeve audit proxy through production selection and baseline weighting code",
                "maturity-aware historical probability and expected-return gaps",
            ],
            "notValidated": [
                "full live four-factor portfolio without PIT fundamentals",
                "historical universe free of survivorship bias",
                "vintage-clean macro conditioning",
                "prospective 126D performance before observations mature",
                *sign_contradiction_claims,
            ],
            "noModelShopping": True,
        },
    }
