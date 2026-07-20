"""Macro DIRECTION & REGIME engine — replaces the fixed-threshold Risk-off call.

v1 declared "Risk-off" the moment the 10Y crossed 4.5% or USD/KRW crossed 1400.
Those are arbitrary levels: 4.5% in a 5% growth boom means something different
than 4.5% in a slowdown. v2 reads six macro AXES by DIRECTION (accelerating /
decelerating), each an expanding-z aggregate of first-party indicators, and
maps Growth × Inflation to a named regime with a confidence, the prior regime,
supporting and contradicting evidence.

Axes:
  growth               성장 가속/둔화     (CFNAI, payrolls, unemployment↓, claims↓)
  inflation            물가 가속/둔화     (core CPI/PCE, breakeven, oil)
  liquidity            유동성 확대/축소   (Fed assets, RRP↓, TGA↓, M2)
  financialConditions  금융여건 완화/긴축 (NFCI↓, HY/IG spreads↓, real yield↓, dollar↓)
  riskAppetite         위험선호 확대/축소 (VIX↓, HY spread↓, breadth)
  earningsCredit       이익·신용 개선/악화 (HY/IG spreads↓, curve)

Regimes: Goldilocks · Reflation · Stagflation · Deflation/Slowdown ·
Transition/Low confidence.

The regime does NOT add to any single-stock alpha. It drives a SEPARATE
risk-budget layer (equity budget range, cash range, style tilt).

POINT-IN-TIME: each indicator carries a conservative publication lag; the
'latest' read for a monthly series is the last observation whose release date is
on/before the as-of date — see ``point_in_time_latest``. Missing series lower
coverage/confidence rather than defaulting to neutral or bullish.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# indicator -> (axis, sign, release_lag_business_days, source_url)
# sign: +1 means "higher raw value pushes the axis positive" (accelerating).
#       For inverse indicators (unemployment for growth) sign is -1.
FRED = "https://fred.stlouisfed.org/series/"
INDICATORS: dict[str, tuple] = {
    # growth
    "CFNAI": ("growth", +1, 20, FRED + "CFNAI"),
    "Payrolls": ("growth", +1, 5, FRED + "PAYEMS"),
    "Unemployment": ("growth", -1, 5, FRED + "UNRATE"),
    "Initial_Claims": ("growth", -1, 5, FRED + "ICSA"),
    # inflation
    "Core_CPI": ("inflation", +1, 12, FRED + "CPILFESL"),
    "Core_PCE": ("inflation", +1, 28, FRED + "PCEPILFE"),
    "Breakeven_10Y": ("inflation", +1, 1, FRED + "T10YIE"),
    "WTI": ("inflation", +1, 1, FRED + "DCOILWTICO"),
    # liquidity
    "Fed_Assets": ("liquidity", +1, 6, FRED + "WALCL"),
    "RRP": ("liquidity", -1, 1, FRED + "RRPONTSYD"),
    "TGA": ("liquidity", -1, 3, FRED + "WTREGEN"),
    "M2": ("liquidity", +1, 30, FRED + "M2SL"),
    # financial conditions
    "NFCI": ("financialConditions", -1, 4, FRED + "NFCI"),
    "ANFCI": ("financialConditions", -1, 4, FRED + "ANFCI"),
    "HY_Spread": ("financialConditions", -1, 1, FRED + "BAMLH0A0HYM2"),
    "IG_Spread": ("financialConditions", -1, 1, FRED + "BAMLC0A0CM"),
    "Real_10Y": ("financialConditions", -1, 1, FRED + "DFII10"),
    "Broad_Dollar": ("financialConditions", -1, 1, FRED + "DTWEXBGS"),
    # risk appetite
    "VIX": ("riskAppetite", -1, 0, "https://www.cboe.com/tradable_products/vix/"),
    # earnings / credit
    "Yield_Curve": ("earningsCredit", +1, 0, FRED + "T10Y2Y"),
}

AXES = ["growth", "inflation", "liquidity", "financialConditions", "riskAppetite", "earningsCredit"]
AXIS_KO = {
    "growth": "성장", "inflation": "물가", "liquidity": "유동성",
    "financialConditions": "금융여건", "riskAppetite": "위험선호", "earningsCredit": "이익·신용",
}
DIRECTION_POS = {"growth": "가속", "inflation": "가속", "liquidity": "확대",
                 "financialConditions": "완화", "riskAppetite": "확대", "earningsCredit": "개선"}
DIRECTION_NEG = {"growth": "둔화", "inflation": "둔화", "liquidity": "축소",
                 "financialConditions": "긴축", "riskAppetite": "축소", "earningsCredit": "악화"}

# Indicator-specific transformations. A price index is converted to an
# inflation RATE before its direction is classified; employment, claims,
# liquidity, spreads and market levels retain their economically appropriate
# units. This registry intentionally replaces the old universal raw 3m change.
TRANSFORMATIONS = {
    "Core_CPI": "inflation_rate_yoy_and_3m_annualized",
    "Core_PCE": "inflation_rate_yoy_and_3m_annualized",
    "Payrolls": "monthly_change_3m_average",
    "Unemployment": "three_month_average_change",
    "Initial_Claims": "four_week_average_change",
    "M2": "yoy_growth_rate",
    "Fed_Assets": "thirteen_week_growth_rate",
    "HY_Spread": "level_zscore_and_recent_change",
    "IG_Spread": "level_zscore_and_recent_change",
    "VIX": "level_zscore_and_recent_change",
    "Yield_Curve": "level_and_steepening_change",
    "WTI": "three_month_price_return",
}


def _visible_observations(series: pd.Series, lag_bdays: int,
                          asof: pd.Timestamp | None = None) -> tuple[pd.Series, pd.Timestamp | None]:
    s = series.dropna().sort_index()
    if s.empty:
        return s, asof
    eval_asof = pd.Timestamp(asof) if asof is not None else pd.Timestamp(s.index.max())
    release_dates = pd.DatetimeIndex(s.index) + pd.tseries.offsets.BDay(lag_bdays)
    return s[release_dates <= eval_asof], eval_asof


def point_in_time_latest(series: pd.Series, lag_bdays: int, asof: pd.Timestamp | None = None):
    """Latest observation KNOWN to the public on/before ``asof``.

    A monthly CPI print for observation date D is not public until ~D+lag. Using
    it at D would be look-ahead. We shift the observation index forward by the
    release lag and then take the last row at/before ``asof``.
    """
    visible, _ = _visible_observations(series, lag_bdays, asof)
    if visible.empty:
        return None, None
    return float(visible.iloc[-1]), pd.Timestamp(visible.index[-1])


def _expanding_z(series: pd.Series, value: float) -> float | None:
    s = series.dropna()
    if len(s) < 24:
        return None
    mu, sd = s.mean(), s.std(ddof=0)
    if not sd:
        return None
    return float((value - mu) / sd)


def _observations(series: pd.Series) -> pd.Series:
    """Collapse forward-filled macro frames back to actual value observations."""
    s = series.dropna()
    return s[s.ne(s.shift())]


def _direction(value: float | None, threshold: float = 1e-9) -> int:
    if value is None or not np.isfinite(value) or abs(value) <= threshold:
        return 0
    return int(np.sign(value))


def _transform(name: str, visible: pd.Series) -> dict:
    s = _observations(visible)
    raw_latest = float(visible.iloc[-1])
    method = TRANSFORMATIONS.get(name, "recent_level_change")
    transformed = raw_latest
    change = None
    z = _expanding_z(s, float(s.iloc[-1])) if len(s) else None

    if method == "inflation_rate_yoy_and_3m_annualized":
        yoy = s.pct_change(12) * 100
        ann3 = ((s / s.shift(3)) ** 4 - 1) * 100
        rate = yoy.dropna()
        transformed = float(rate.iloc[-1]) if not rate.empty else None
        change = float(rate.iloc[-1] - rate.iloc[-4]) if len(rate) >= 4 else None
        z = _expanding_z(rate, transformed) if transformed is not None else None
        ann3_latest = float(ann3.dropna().iloc[-1]) if not ann3.dropna().empty else None
        return {"latest": raw_latest, "transformed": transformed, "change": change,
                "direction": _direction(change, 0.05), "z": z,
                "annualized3m": ann3_latest, "method": method}
    if method == "monthly_change_3m_average":
        level = s.diff().rolling(3).mean().dropna()
        transformed = float(level.iloc[-1]) if not level.empty else None
        change = float(level.iloc[-1] - level.iloc[-4]) if len(level) >= 4 else None
    elif method == "three_month_average_change":
        level = s.rolling(3).mean().dropna()
        transformed = float(level.iloc[-1]) if not level.empty else None
        change = float(level.iloc[-1] - level.iloc[-4]) if len(level) >= 4 else None
    elif method == "four_week_average_change":
        level = s.rolling(4).mean().dropna()
        transformed = float(level.iloc[-1]) if not level.empty else None
        change = float(level.iloc[-1] - level.iloc[-5]) if len(level) >= 5 else None
    elif method == "yoy_growth_rate":
        level = (s.pct_change(12) * 100).dropna()
        transformed = float(level.iloc[-1]) if not level.empty else None
        change = float(level.iloc[-1] - level.iloc[-4]) if len(level) >= 4 else None
    elif method == "thirteen_week_growth_rate":
        level = (s.pct_change(13) * 100).dropna()
        transformed = float(level.iloc[-1]) if not level.empty else None
        change = float(level.iloc[-1] - level.iloc[-5]) if len(level) >= 5 else None
    elif method in {"level_zscore_and_recent_change", "level_and_steepening_change"}:
        step = 21 if len(s) > 400 else min(3, max(1, len(s) - 1))
        change = float(s.iloc[-1] - s.iloc[-step - 1]) if len(s) > step else None
        level_signal = _direction(z, 0.25)
        change_signal = _direction(change)
        combined = (level_signal + change_signal) / 2
        return {"latest": raw_latest, "transformed": raw_latest, "change": change,
                "direction": _direction(combined, 0.25), "z": z, "method": method}
    elif method == "three_month_price_return":
        step = 63 if len(s) > 400 else min(3, max(1, len(s) - 1))
        change = float(s.iloc[-1] / s.iloc[-step - 1] - 1) if len(s) > step else None
        transformed = change
    else:
        step = 21 if len(s) > 400 else min(3, max(1, len(s) - 1))
        change = float(s.iloc[-1] - s.iloc[-step - 1]) if len(s) > step else None
    z = _expanding_z(pd.Series(s, dtype=float), float(s.iloc[-1])) if len(s) else None
    return {"latest": raw_latest, "transformed": transformed, "change": change,
            "direction": _direction(change), "z": z, "method": method}


def indicator_read(name: str, series: pd.Series, asof: pd.Timestamp | None = None) -> dict | None:
    axis, sign, lag, url = INDICATORS[name]
    visible, eval_asof = _visible_observations(series, lag, asof)
    if visible.empty:
        return None
    obs = pd.Timestamp(visible.index[-1])
    tr = _transform(name, visible)
    fresh_days = int((eval_asof.normalize() - obs.normalize()).days) if eval_asof is not None else None
    return {
        "name": name,
        "axis": axis,
        "sign": sign,
        "latestValue": round(tr["latest"], 4),
        "transformedValue": round(tr["transformed"], 4) if tr["transformed"] is not None else None,
        "change": round(tr["change"], 4) if tr["change"] is not None else None,
        "annualized3m": round(tr.get("annualized3m"), 4) if tr.get("annualized3m") is not None else None,
        "transformation": tr["method"],
        "zscore": round(tr["z"], 2) if tr["z"] is not None else None,
        "direction": tr["direction"],
        "axisContribution": (sign * tr["direction"]) if tr["direction"] else 0,
        "observationDate": obs.strftime("%Y-%m-%d") if obs is not None else None,
        "releaseLagBdays": lag,
        "freshnessDays": fresh_days,
        "stale": (fresh_days is not None and fresh_days > 120),
        "source": url,
    }


def _axis_summary(reads: list[dict], expected_count: int | None = None) -> dict:
    """Aggregate indicator reads into one axis value/direction/confidence."""
    contribs = [r["axisContribution"] for r in reads if r["axisContribution"] != 0]
    fresh = [r for r in reads if not r.get("stale")]
    if not reads:
        return {"value": None, "direction": None, "confidence": 0.0,
                "coverage": 0.0, "freshness": 0.0, "agreement": 0.0,
                "nIndicators": 0}
    value = float(np.mean(contribs)) if contribs else 0.0
    expected_count = expected_count or 3
    coverage = min(1.0, len(reads) / expected_count)
    freshness = len(fresh) / len(reads) if reads else 0.0
    agreement = abs(float(np.mean(contribs))) if contribs else 0.0
    conf = round(coverage * freshness * (0.5 + 0.5 * agreement), 2)
    direction = "positive" if value > 0.15 else ("negative" if value < -0.15 else "flat")
    return {"value": round(value, 2), "direction": direction, "confidence": conf,
            "coverage": round(coverage, 2), "freshness": round(freshness, 2),
            "agreement": round(agreement, 2), "nIndicators": len(reads)}


def _regime_label(growth: dict, inflation: dict) -> tuple[str, float]:
    gc, ic = growth["confidence"], inflation["confidence"]
    conf = round(min(gc, ic), 2)
    gv, iv = growth["value"], inflation["value"]
    if conf < 0.34 or gv is None or iv is None or abs(gv) <= 0.15 or abs(iv) <= 0.15:
        return "Transition/Low confidence", conf
    if gv >= 0 and iv < 0:
        return "Goldilocks", conf
    if gv >= 0 and iv >= 0:
        return "Reflation", conf
    if gv < 0 and iv >= 0:
        return "Stagflation", conf
    return "Deflation/Slowdown", conf


# Base equity risk budget by regime (percent range of a risk portfolio). This is
# the SEPARATE allocation layer; it never touches single-stock alpha.
_REGIME_BUDGET = {
    "Goldilocks": (70, 90, "위험선호 · 성장/모멘텀 우위"),
    "Reflation": (60, 80, "실물·가치·에너지 우위, 듀레이션 주의"),
    "Stagflation": (30, 55, "퀄리티·저변동·실물자산 방어, 듀레이션 회피"),
    "Deflation/Slowdown": (25, 50, "듀레이션·퀄리티 방어, 신용 회피"),
    "Transition/Low confidence": (45, 70, "중립 유지 · 확신 확보 전 무리한 베팅 자제"),
}


def build(macro: pd.DataFrame | None, vix: pd.Series | None,
          prior_regime: str | None = None, asof: pd.Timestamp | None = None) -> dict:
    """Build the regime read. Degrades honestly: no data -> low confidence and a
    Transition label, never a fabricated bullish/neutral score."""
    series_map: dict[str, pd.Series] = {}
    if macro is not None:
        for c in macro.columns:
            series_map[c] = macro[c]
    if vix is not None:
        series_map["VIX"] = vix

    candidates = []
    if macro is not None and len(macro):
        candidates.append(pd.Timestamp(macro.index.max()))
    if vix is not None and len(vix):
        candidates.append(pd.Timestamp(vix.index.max()))
    eval_asof = pd.Timestamp(asof) if asof is not None else (max(candidates) if candidates else None)

    reads: dict[str, dict] = {}
    for name in INDICATORS:
        s = series_map.get(name)
        if s is None:
            continue
        r = indicator_read(name, s, eval_asof)
        if r is not None:
            reads[name] = r

    axes = {}
    for axis in AXES:
        axis_reads = [r for r in reads.values() if r["axis"] == axis]
        expected_count = sum(1 for spec in INDICATORS.values() if spec[0] == axis)
        summ = _axis_summary(axis_reads, expected_count=expected_count)
        summ["ko"] = AXIS_KO[axis]
        if summ["direction"] == "positive":
            summ["labelKo"] = DIRECTION_POS[axis]
        elif summ["direction"] == "negative":
            summ["labelKo"] = DIRECTION_NEG[axis]
        elif summ["direction"] == "flat":
            summ["labelKo"] = "보합/상쇄"
        else:
            summ["labelKo"] = "데이터 부족"
        summ["indicators"] = axis_reads
        axes[axis] = summ

    label, conf = _regime_label(axes["growth"], axes["inflation"])

    # Supporting / contradicting evidence: indicators whose contribution agrees
    # (or not) with a risk-on reading of the regime.
    risk_on = label in ("Goldilocks", "Reflation")
    supporting, contradicting = [], []
    for r in reads.values():
        c = r["axisContribution"]
        if c == 0:
            continue
        agrees = (c > 0) if risk_on else (c < 0)
        (supporting if agrees else contradicting).append(
            {"name": r["name"], "axis": r["axis"], "direction": r["direction"], "z": r["zscore"]})

    lo, hi, tilt = _REGIME_BUDGET[label]
    # Adjust budget by financial conditions & risk appetite (tighter -> lower).
    fc, ra = axes["financialConditions"]["value"], axes["riskAppetite"]["value"]
    adj = 0
    if fc is not None and fc < -0.3:
        adj -= 10
    if ra is not None and ra < -0.3:
        adj -= 10
    if fc is not None and fc > 0.3:
        adj += 5
    lo_adj, hi_adj = max(10, lo + adj), max(20, hi + adj)

    coverage = round(len(reads) / len(INDICATORS), 2)
    return {
        "available": bool(reads),
        "regime": label,
        "priorRegime": prior_regime,
        "changed": bool(prior_regime and prior_regime != label),
        "confidence": conf,
        "coverage": coverage,
        "axes": axes,
        "supporting": supporting[:8],
        "contradicting": contradicting[:8],
        "riskBudget": {
            "equityRangePct": [int(lo_adj), int(hi_adj)],
            "cashRangePct": [int(100 - hi_adj), int(100 - lo_adj)],
            "styleTilt": tilt,
            "note": "매크로 국면 기반 위험예산 — 개별 종목 알파에 가산하지 않고 전체 노출·현금·스타일만 조정",
        },
        "asOf": eval_asof.strftime("%Y-%m-%d") if eval_asof is not None else None,
        "indicatorCount": len(reads),
        "pointInTimeLimitations": "고정 발표시차 근사치 사용; 실제 release calendar 및 ALFRED vintage 미사용",
        "regimeMethod": "6축 진단 표시; 국면 라벨은 성장×물가, 위험예산은 금융여건·위험선호로 보정",
        "note": None if reads else "매크로 데이터 없음 (FRED_API_KEY/ECOS_API_KEY 미설정) — 국면 판정 불가, confidence 0",
    }
