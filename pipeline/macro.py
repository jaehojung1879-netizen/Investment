"""Macro environment summary, grouped by region (US / KR).

Each region returns a stance, a list of display indicators, and any active
risk flags. All series come from FRED (a single API key covers both US and
international data); VIX comes from the price feed.
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


def _us_region(macro, vix) -> dict:
    t10 = _col(macro, "Treasury_10Y")
    t2 = _col(macro, "Treasury_2Y")
    curve = _col(macro, "Yield_Curve")
    ff = _col(macro, "FedFunds")
    hy = _col(macro, "HY_Spread")

    t10n, curven, vixn, hyn = _last(t10), _last(curve), _last(vix), _last(hy)
    flags = []
    if curven is not None and curven < 0:
        flags.append("장단기 금리차 역전 (경기 둔화 신호)")
    if hyn is not None and hyn > 5:
        flags.append(f"하이일드 스프레드 {hyn:.1f}%p (신용 경계)")
    if vixn is not None and vixn > 25:
        flags.append(f"VIX {vixn:.0f} (위험 회피)")
    if t10n is not None and t10n > 4.5:
        flags.append(f"10년물 {t10n:.1f}% (금리 부담)")

    stance = "Risk-off" if (vixn and vixn > 25) or (hyn and hyn > 5) else ("Caution" if curven is not None and curven < 0 else "Stable")
    indicators = [
        ["10Y", _fmt(t10n, "%"), "미국 국채 10년"],
        ["2Y", _fmt(_last(t2), "%"), "미국 국채 2년"],
        ["금리차", _fmt(curven, "%p"), "10Y−2Y"],
        ["기준금리", _fmt(_last(ff), "%"), "Fed Funds"],
        ["HY스프레드", _fmt(hyn, "%p"), "하이일드 신용"],
        ["VIX", _fmt(vixn, "", 1), f"21일 {_fmt(_change(vix), '', 1)}"],
    ]
    return {"stance": stance, "indicators": indicators, "riskFlags": flags}


def _kr_region(macro) -> dict:
    krw = _col(macro, "USD_KRW")
    k10 = _col(macro, "Korea_10Y")
    k3 = _col(macro, "Korea_3M")

    krwn = _last(krw)
    krw_chg = _pct_change(krw)
    k10n, k3n = _last(k10), _last(k3)
    kr_curve = (k10n - k3n) if (k10n is not None and k3n is not None) else None

    flags = []
    if krwn is not None and krwn > 1400:
        flags.append(f"원/달러 {krwn:.0f} (원화 약세·외국인 자금이탈 위험)")
    if krw_chg is not None and krw_chg > 3:
        flags.append(f"원화 21일 {krw_chg:+.1f}% (급격한 약세)")
    if kr_curve is not None and kr_curve < 0:
        flags.append("한국 장단기 금리차 역전")
    if k10n is not None and (_change(k10) or 0) > 0.3:
        flags.append("한국 10년물 금리 상승")

    stance = "Risk-off" if (krwn and krwn > 1400) or (krw_chg and krw_chg > 3) else ("Caution" if kr_curve is not None and kr_curve < 0 else "Stable")
    indicators = [
        ["원/달러", _fmt(krwn, "", 0), f"21일 {_fmt(krw_chg, '%', 1)}"],
        ["한국 10Y", _fmt(k10n, "%"), "국고채 10년"],
        ["한국 3M", _fmt(k3n, "%"), "단기 금리"],
        ["한국 금리차", _fmt(kr_curve, "%p"), "10Y−3M"],
    ]
    return {"stance": stance, "indicators": indicators, "riskFlags": flags}


def summarize(macro: pd.DataFrame | None, vix: pd.Series | None) -> dict:
    if macro is None and vix is None:
        return {
            "available": False,
            "note": "FRED_API_KEY 미설정 — 매크로 데이터가 비어 있습니다. GitHub Actions Secret 으로 키를 넣으면 채워집니다.",
        }
    return {
        "available": True,
        "US": _us_region(macro, vix),
        "KR": _kr_region(macro),
    }
