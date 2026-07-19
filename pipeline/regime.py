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


def point_in_time_latest(series: pd.Series, lag_bdays: int, asof: pd.Timestamp | None = None):
    """Latest observation KNOWN to the public on/before ``asof``.

    A monthly CPI print for observation date D is not public until ~D+lag. Using
    it at D would be look-ahead. We shift the observation index forward by the
    release lag and then take the last row at/before ``asof``.
    """
    s = series.dropna()
    if s.empty:
        return None, None
    asof = asof or s.index.max()
    released = s.copy()
    released.index = released.index + pd.tseries.offsets.BDay(lag_bdays)
    visible = released[released.index <= asof]
    if visible.empty:
        return None, None
    # Map back to the underlying observation date for display.
    last_release_date = visible.index[-1]
    obs_date = last_release_date - pd.tseries.offsets.BDay(lag_bdays)
    return float(visible.iloc[-1]), obs_date


def _expanding_z(series: pd.Series, value: float) -> float | None:
    s = series.dropna()
    if len(s) < 24:
        return None
    mu, sd = s.mean(), s.std(ddof=0)
    if not sd:
        return None
    return float((value - mu) / sd)


def _change(series: pd.Series, months: int) -> float | None:
    s = series.dropna()
    # Series may be daily or monthly; approximate a month as 21 rows if daily.
    step = months * (21 if len(s) > 400 else 1)
    if len(s) <= step:
        return None
    return float(s.iloc[-1] - s.iloc[-step - 1])


def indicator_read(name: str, series: pd.Series, asof: pd.Timestamp | None = None) -> dict | None:
    axis, sign, lag, url = INDICATORS[name]
    val, obs = point_in_time_latest(series, lag, asof)
    if val is None:
        return None
    # For level series (indices/CPI), score the year-over-year change; for
    # rate/spread series, score the level. Heuristic: names ending in level-like.
    level_change = _change(series, 3)
    z = _expanding_z(series, val)
    direction = 0
    if level_change is not None:
        direction = int(np.sign(level_change))
    elif z is not None:
        direction = int(np.sign(z))
    fresh_days = None
    if obs is not None:
        fresh_days = int((pd.Timestamp.today().normalize() - obs.normalize()).days)
    return {
        "name": name,
        "axis": axis,
        "sign": sign,
        "latestValue": round(val, 4),
        "change1m": round(_change(series, 1), 4) if _change(series, 1) is not None else None,
        "change3m": round(level_change, 4) if level_change is not None else None,
        "zscore": round(z, 2) if z is not None else None,
        "direction": direction,
        "axisContribution": (sign * direction) if direction else 0,
        "observationDate": obs.strftime("%Y-%m-%d") if obs is not None else None,
        "releaseLagBdays": lag,
        "freshnessDays": fresh_days,
        "stale": (fresh_days is not None and fresh_days > 120),
        "source": url,
    }


def _axis_summary(reads: list[dict]) -> dict:
    """Aggregate indicator reads into one axis value/direction/confidence."""
    contribs = [r["axisContribution"] for r in reads if r["axisContribution"] != 0]
    fresh = [r for r in reads if not r["stale"]]
    if not reads:
        return {"value": None, "direction": None, "confidence": 0.0, "nIndicators": 0}
    value = float(np.mean(contribs)) if contribs else 0.0
    # Confidence: coverage of expected indicators (rough) × freshness fraction.
    coverage = min(1.0, len(reads) / 3.0)
    freshness = len(fresh) / len(reads) if reads else 0.0
    conf = round(0.6 * coverage + 0.4 * freshness, 2)
    direction = "positive" if value > 0.15 else ("negative" if value < -0.15 else "flat")
    return {"value": round(value, 2), "direction": direction, "confidence": conf, "nIndicators": len(reads)}


def _regime_label(growth: dict, inflation: dict) -> tuple[str, float]:
    gc, ic = growth["confidence"], inflation["confidence"]
    conf = round(min(gc, ic), 2)
    gv, iv = growth["value"], inflation["value"]
    if conf < 0.34 or gv is None or iv is None:
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

    reads: dict[str, dict] = {}
    for name in INDICATORS:
        s = series_map.get(name)
        if s is None:
            continue
        r = indicator_read(name, s, asof)
        if r is not None:
            reads[name] = r

    axes = {}
    for axis in AXES:
        axis_reads = [r for r in reads.values() if r["axis"] == axis]
        summ = _axis_summary(axis_reads)
        summ["ko"] = AXIS_KO[axis]
        summ["labelKo"] = (DIRECTION_POS if (summ["value"] or 0) >= 0 else DIRECTION_NEG)[axis] if summ["value"] is not None else "데이터 부족"
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
        "asOf": (lambda d: d.strftime("%Y-%m-%d") if d is not None else None)(
            asof or (macro.index.max() if macro is not None and len(macro) else None)),
        "indicatorCount": len(reads),
        "note": None if reads else "매크로 데이터 없음 (FRED_API_KEY/ECOS_API_KEY 미설정) — 국면 판정 불가, confidence 0",
    }
