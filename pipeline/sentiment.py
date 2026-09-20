"""Quantitative market-direction read per region (US / KR).

This replaces the per-stock regime cards with a market-level "where are we"
panel built entirely from observable data: breadth (how many names are above
their long-term trend), median momentum across the screened universe, and the
macro risk gauges. No opinions, no hand-entered views.
"""
from __future__ import annotations

import statistics

import pandas as pd


def _last(series):
    if series is None:
        return None
    s = series.dropna()
    return float(s.iloc[-1]) if len(s) else None


def _col(macro, name):
    return macro[name] if macro is not None and name in macro.columns else None


def _pct_change(series, periods=21):
    if series is None:
        return None
    s = series.dropna()
    if len(s) <= periods or s.iloc[-periods - 1] == 0:
        return None
    return float((s.iloc[-1] / s.iloc[-periods - 1] - 1) * 100)


def _label(score: float) -> str:
    return "강세" if score >= 60 else ("약세" if score < 40 else "중립")


def fear_greed_label(score: float) -> str:
    """CNN-style Fear & Greed bands."""
    if score < 25:
        return "극도의 공포"
    if score < 45:
        return "공포"
    if score < 55:
        return "중립"
    if score < 75:
        return "탐욕"
    return "극도의 탐욕"


def _region(name: str, rows: list[dict], macro: pd.DataFrame | None, vix) -> dict | None:
    if not rows:
        return None
    n = len(rows)

    def breadth(key: str) -> tuple[float | None, int]:
        """Share above the average, over names where it could be measured.

        Counting an uncomputable average as "below" would make breadth a
        function of how many names are newly listed rather than of the market.
        `risk.diagnose` therefore returns None, not False, for a name whose
        rolling mean does not exist yet — and this excludes those names from
        the ratio rather than scoring them bearish.

        NOTHING MEASURABLE IS `None`, NOT 0%. The same argument taken to its
        limit: returning 0.0 for an empty measured set is the exact failure the
        exclusion exists to prevent, wearing the strongest possible value.
        200-day breadth carries 0.4 of this score, so an all-unmeasurable
        cross-section — a fresh universe, a vendor that served prices too short
        to average — moved the index 20 points toward fear and the panel read
        "극도의 공포" from data that said nothing at all. The count is returned
        beside the share so the caller can publish what it was measured on: a
        breadth of 100% over two names and over five hundred are not the same
        reading and the artifact could not previously tell them apart.
        """
        measured = [r for r in rows if r.get(key) is not None]
        if not measured:
            return None, 0
        return 100 * sum(1 for r in measured if r[key]) / len(measured), len(measured)

    breadth200, measured200 = breadth("aboveMA200")
    breadth50, measured50 = breadth("aboveMA50")
    bull_pct = 100 * sum(1 for r in rows if r.get("regime") == "Bull") / n
    moms = [r["mom63"] for r in rows if r.get("mom63") is not None]
    med_mom = statistics.median(moms) * 100 if moms else None

    # An unmeasured component contributes NOTHING, never its most bearish
    # value. `bull_pct` is always measurable — `risk.diagnose` classifies an
    # unresolvable name "Transition", which is a stated verdict rather than a
    # missing one — so it has no such branch.
    score = 50.0
    if breadth200 is not None:
        score += (breadth200 - 50) * 0.4   # ±20
    if breadth50 is not None:
        score += (breadth50 - 50) * 0.1    # ±5
    if med_mom is not None:
        score += 8 if med_mom > 0 else -8
    score += (bull_pct - 50) * 0.1         # ±5

    def pct(value: float | None) -> str:
        return "—" if value is None else f"{value:.0f}%"

    def basis(measured: int, suffix: str) -> str:
        return f"{suffix} · 산출 {measured}/{n}종목" if measured else f"{suffix} · 산출 불가"

    components = [
        ["추세 위 비중(200일)", pct(breadth200), basis(measured200, f"{name} 유니버스")],
        ["추세 위 비중(50일)", pct(breadth50), basis(measured50, "단기 추세")],
        ["상승국면 비중", f"{bull_pct:.0f}%", "Bull 분류 비율"],
        ["중앙값 모멘텀(60일)",
         "—" if med_mom is None else f"{med_mom:+.1f}%",
         basis(len(moms), "유니버스 중앙값")],
    ]

    if name == "US":
        vixn = _last(vix)
        hy = _last(_col(macro, "HY_Spread"))
        curve = _last(_col(macro, "Yield_Curve"))
        if vixn is not None:
            components.append(["VIX", f"{vixn:.1f}", "변동성"])
            score += -10 if vixn > 25 else (5 if vixn < 16 else 0)
        if hy is not None:
            components.append(["HY 스프레드", f"{hy:.1f}%p", "신용 위험"])
            score += -10 if hy > 5 else 0
        if curve is not None and curve < 0:
            score -= 8
    else:  # KR
        krw = _col(macro, "USD_KRW")
        krwn = _last(krw)
        krw_chg = _pct_change(krw)
        k10 = _last(_col(macro, "Korea_10Y"))
        k3 = _last(_col(macro, "Korea_3M"))
        if krwn is not None:
            components.append(["원/달러", f"{krwn:.0f}", f"21일 {krw_chg:+.1f}%" if krw_chg is not None else ""])
            score += -10 if krwn > 1400 else 0
            if krw_chg is not None and krw_chg > 3:
                score -= 6
        if k10 is not None and k3 is not None and (k10 - k3) < 0:
            score -= 8

    score = max(0.0, min(100.0, score))
    return {
        "region": name,
        "score": round(score),
        "label": _label(score),
        "fearGreed": fear_greed_label(score),
        "breadth200": None if breadth200 is None else round(breadth200),
        # What the breadth was measured on. A share with no denominator beside
        # it cannot be told apart from one measured over the whole universe,
        # and the score weights this component more heavily than any other.
        "breadth200MeasuredNames": measured200,
        "breadth50MeasuredNames": measured50,
        "universeNames": n,
        "unmeasuredComponents": [key for key, value in
                                 (("breadth200", breadth200), ("breadth50", breadth50),
                                  ("medianMomentum63", med_mom))
                                 if value is None],
        "components": components,
    }


def summarize(screened: list[dict], macro: pd.DataFrame | None, vix) -> dict:
    us = _region("US", [r for r in screened if r.get("region") == "US"], macro, vix)
    kr = _region("KR", [r for r in screened if r.get("region") == "KR"], macro, vix)
    return {"US": us, "KR": kr}
