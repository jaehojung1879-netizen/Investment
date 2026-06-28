"""Macro environment summary from FRED series + VIX."""
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


def summarize(macro: pd.DataFrame | None, vix: pd.Series | None) -> dict:
    if macro is None and vix is None:
        return {
            "available": False,
            "note": "FRED_API_KEY 가 설정되지 않아 매크로 데이터가 비어 있습니다. GitHub Actions Secret 으로 키를 넣으면 채워집니다.",
        }

    t10 = macro["Treasury_10Y"] if macro is not None and "Treasury_10Y" in macro else None
    t2 = macro["Treasury_2Y"] if macro is not None and "Treasury_2Y" in macro else None
    curve = macro["Yield_Curve"] if macro is not None and "Yield_Curve" in macro else None
    vix_series = vix if vix is not None else (macro["VIX"] if macro is not None and "VIX" in macro else None)

    curve_now = _last(curve)
    vix_now = _last(vix_series)

    flags = []
    if curve_now is not None and curve_now < 0:
        flags.append({"name": "Yield Curve", "active": True, "message": "장단기 금리차 역전 (경기 둔화 신호)"})
    if vix_now is not None and vix_now > 25:
        flags.append({"name": "VIX", "active": True, "message": f"VIX {vix_now:.0f} (위험 회피 심리)"})
    t10_now = _last(t10)
    if t10_now is not None and t10_now > 4.5:
        flags.append({"name": "Rates", "active": True, "message": f"10년물 {t10_now:.1f}% (금리 부담)"})

    if curve_now is not None and curve_now < 0:
        stance = "Caution"
    elif vix_now is not None and vix_now > 25:
        stance = "Risk-off"
    else:
        stance = "Stable"

    return {
        "available": True,
        "stance": stance,
        "treasury10y": round(t10_now, 2) if t10_now is not None else None,
        "treasury2y": round(_last(t2), 2) if _last(t2) is not None else None,
        "yieldCurve": round(curve_now, 2) if curve_now is not None else None,
        "yieldCurveChange21d": round(_change(curve), 2) if _change(curve) is not None else None,
        "vix": round(vix_now, 1) if vix_now is not None else None,
        "vixChange21d": round(_change(vix_series), 1) if _change(vix_series) is not None else None,
        "riskFlags": flags,
    }
