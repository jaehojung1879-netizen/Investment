"""Macro DISPLAY panel (region indicator tables).

The regime/stance judgement moved to pipeline.regime (a 6-axis direction
engine). This module now only formats the raw indicator values for the market
panel — it no longer declares "Risk-off" off arbitrary fixed levels (10Y > 4.5%,
USD/KRW > 1400). Those hard thresholds were the exact thing the redesign
removes: a level is only meaningful relative to the growth/inflation regime,
which regime.py assesses.
"""
from __future__ import annotations

import pandas as pd


def _last(series: pd.Series | None):
    if series is None:
        return None
    s = series.dropna()
    return float(s.iloc[-1]) if len(s) else None


def _change(series: pd.Series | None, periods: int = 21):
    if series is None:
        return None
    s = series.dropna()
    if len(s) <= periods:
        return None
    return float(s.iloc[-1] - s.iloc[-periods - 1])


def _pct_change(series: pd.Series | None, periods: int = 21):
    if series is None:
        return None
    s = series.dropna()
    if len(s) <= periods or s.iloc[-periods - 1] == 0:
        return None
    return float((s.iloc[-1] / s.iloc[-periods - 1] - 1) * 100)


def _fmt(v, suffix="", digits=2):
    return "—" if v is None else f"{round(v, digits)}{suffix}"


def _col(macro, name):
    return macro[name] if macro is not None and name in macro.columns else None


def _us_indicators(macro, vix) -> list:
    t10, t2 = _col(macro, "Treasury_10Y"), _col(macro, "Treasury_2Y")
    curve = _col(macro, "Yield_Curve")
    return [
        ["10Y", _fmt(_last(t10), "%"), "미국 국채 10년"],
        ["2Y", _fmt(_last(t2), "%"), "미국 국채 2년"],
        ["금리차", _fmt(_last(curve), "%p"), "10Y−2Y"],
        ["기준금리", _fmt(_last(_col(macro, "FedFunds")), "%"), "Fed Funds"],
        ["HY스프레드", _fmt(_last(_col(macro, "HY_Spread")), "%p"), "하이일드 신용"],
        ["실질10Y", _fmt(_last(_col(macro, "Real_10Y")), "%"), "TIPS 10년"],
        ["기대인플레", _fmt(_last(_col(macro, "Breakeven_10Y")), "%"), "10Y breakeven"],
        ["VIX", _fmt(_last(vix), "", 1), f"21일 {_fmt(_change(vix), '', 1)}"],
    ]


def _kr_indicators(macro) -> list:
    krw = _col(macro, "USD_KRW")
    k10, k3 = _last(_col(macro, "Korea_10Y")), _last(_col(macro, "Korea_3M"))
    kr_curve = (k10 - k3) if (k10 is not None and k3 is not None) else None
    return [
        ["원/달러", _fmt(_last(krw), "", 0), f"21일 {_fmt(_pct_change(krw), '%', 1)}"],
        ["한국 10Y", _fmt(k10, "%"), "국고채 10년"],
        ["한국 3M", _fmt(k3, "%"), "단기 금리"],
        ["한국 금리차", _fmt(kr_curve, "%p"), "10Y−3M"],
    ]


def summarize(macro: pd.DataFrame | None, vix: pd.Series | None, regime: dict | None = None) -> dict:
    if macro is None and vix is None:
        return {
            "available": False,
            "note": "FRED_API_KEY/ECOS_API_KEY 미설정 — 매크로 데이터가 비어 있습니다. GitHub Actions Secret 으로 키를 넣으면 채워집니다.",
        }
    reg_label = (regime or {}).get("regime")
    return {
        "available": True,
        "regime": reg_label,
        "regimeConfidence": (regime or {}).get("confidence"),
        "US": {"indicators": _us_indicators(macro, vix)},
        "KR": {"indicators": _kr_indicators(macro)},
        "note": "국면·위험예산은 상단 매크로 국면 패널(6축 방향 엔진) 참조 — 아래는 원지표 값만 표시",
    }
