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
    "Headline_CPI": ("inflation", +1, 12, FRED + "CPIAUCSL"),
    "Core_CPI": ("inflation", +1, 12, FRED + "CPILFESL"),
    "Core_PCE": ("inflation", +1, 28, FRED + "PCEPILFE"),
    "Headline_PPI": ("inflation", +1, 30, FRED + "PPIFIS"),
    "Core_PPI": ("inflation", +1, 30, FRED + "WPSFD49116"),
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

# PPI is useful upstream-price context, but directly adding both PPI series to
# a CPI/PCE-heavy mean would double-count one release family.  They remain
# visible without changing the established regime-decision weights.
CONTEXT_ONLY_INDICATORS = {"Headline_PPI", "Core_PPI"}

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
    "Headline_CPI": "inflation_rate_yoy_and_3m_annualized",
    "Core_CPI": "inflation_rate_yoy_and_3m_annualized",
    "Core_PCE": "inflation_rate_yoy_and_3m_annualized",
    "Headline_PPI": "inflation_rate_yoy_and_3m_annualized",
    "Core_PPI": "inflation_rate_yoy_and_3m_annualized",
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

INDICATOR_META = {
    "CFNAI": ("시카고 연은 국가활동지수", "지수", "지수 변화"),
    "Payrolls": ("비농업 고용", "천 명/월", "천 명/월 변화"),
    "Unemployment": ("실업률", "%", "%p 변화"),
    "Initial_Claims": ("신규 실업수당 청구", "건", "건 변화"),
    "Headline_CPI": ("소비자물가 (Headline CPI)", "%", "%p 변화"),
    "Core_CPI": ("근원 소비자물가", "%", "%p 변화"),
    "Core_PCE": ("근원 개인소비지출 물가", "%", "%p 변화"),
    "Headline_PPI": ("생산자물가 (Headline PPI)", "%", "%p 변화"),
    "Core_PPI": ("근원 생산자물가", "%", "%p 변화"),
    "Breakeven_10Y": ("10년 기대인플레이션", "%", "%p 변화"),
    "WTI": ("WTI 유가", "%", "% 변화"),
    "Fed_Assets": ("연준 총자산", "%", "%p 변화"),
    "RRP": ("연준 역레포", "십억 달러", "십억 달러 변화"),
    "TGA": ("미 재무부 일반계정", "백만 달러", "백만 달러 변화"),
    "M2": ("M2 통화량", "%", "%p 변화"),
    "NFCI": ("시카고 연은 금융여건", "지수", "지수 변화"),
    "ANFCI": ("조정 금융여건", "지수", "지수 변화"),
    "HY_Spread": ("하이일드 스프레드", "%p", "%p 변화"),
    "IG_Spread": ("투자등급 스프레드", "%p", "%p 변화"),
    "Real_10Y": ("10년 실질금리", "%", "%p 변화"),
    "Broad_Dollar": ("광의 달러지수", "지수", "지수 변화"),
    "VIX": ("VIX 변동성지수", "지수", "지수 변화"),
    "Yield_Curve": ("10년-2년 금리차", "%p", "%p 변화"),
}

# Short, plain-language guides shown next to each trend chart.  These are
# descriptions of the indicator—not model-generated forecasts.
INDICATOR_GUIDE = {
    "Headline_CPI": {
        "meaningKo": "식품·에너지를 포함해 미국 도시 소비자가 실제로 지불하는 대표 소비자물가의 전체 흐름입니다.",
        "readKo": "전년 대비 상승률은 장기 물가 압력, 최근 3개월 연율은 단기 재가속·둔화를 보여줍니다.",
        "useKo": "체감물가와 에너지 충격을 확인하고 근원 CPI·근원 PCE와 방향이 같은지 비교합니다.",
        "cautionKo": "식품·에너지 가격 때문에 월별 변동이 커 한 번의 발표보다 3개월 흐름을 우선합니다.",
    },
    "CFNAI": {
        "meaningKo": "미국 생산·고용·소비·주택·판매 등 85개 월간 지표를 한 숫자로 합친 경기 종합 온도계입니다.",
        "readKo": "0은 미국 경제가 역사적 평균 속도로 성장한다는 뜻입니다. 양수는 평균보다 빠른 성장, 음수는 평균보다 느린 성장입니다.",
        "useKo": "월별 값은 흔들림이 커서 3개월 이동평균을 함께 봅니다. 이동평균이 상승하면 경기 모멘텀 개선, 하락하면 둔화 신호로 해석합니다.",
        "cautionKo": "시카고 연은은 미국 중앙은행 체계의 지역 연은 중 하나입니다. 이 지표는 금리 결정을 직접 예고하지 않으며 사후 수정될 수 있습니다.",
    },
    "Payrolls": {
        "meaningKo": "미국 비농업 부문의 일자리 수가 한 달 동안 얼마나 늘거나 줄었는지 보여줍니다.",
        "readKo": "3개월 평균 고용 증가폭이 커지면 성장 가속, 작아지면 성장 둔화 쪽 증거입니다.",
        "useKo": "소비 여력과 경기 지속성을 확인하되 실업률·임금과 함께 봅니다.",
        "cautionKo": "월별 변동과 수정 폭이 커 한 번의 발표만으로 방향을 단정하지 않습니다.",
    },
    "Unemployment": {
        "meaningKo": "일할 의사가 있는 경제활동인구 중 실업자의 비율입니다.",
        "readKo": "3개월 평균이 상승하면 고용시장 약화, 하락하면 고용시장 개선으로 봅니다.",
        "useKo": "급격한 상승은 경기 둔화 위험을 높이지만 노동참여율 변화도 함께 확인해야 합니다.",
        "cautionKo": "경기에 후행하는 성격이 있어 전환점을 늦게 확인할 수 있습니다.",
    },
    "Initial_Claims": {
        "meaningKo": "미국에서 새로 실업보험을 신청한 사람 수로, 고용시장의 빠른 주간 신호입니다.",
        "readKo": "4주 평균이 상승하면 해고 증가, 하락하면 고용시장 안정으로 해석합니다.",
        "useKo": "비농업 고용보다 먼저 움직일 수 있어 경기 변곡점 확인에 유용합니다.",
        "cautionKo": "휴일·계절요인으로 흔들릴 수 있어 4주 평균을 우선합니다.",
    },
    "Core_CPI": {
        "meaningKo": "가격 변동이 큰 식품·에너지를 제외한 미국 소비자물가의 기조입니다.",
        "readKo": "전년 대비 상승률과 최근 3개월 연율이 함께 내려가면 물가 둔화 신뢰가 높아집니다.",
        "useKo": "금리와 주식 밸류에이션에 영향을 주는 인플레이션 압력을 확인합니다.",
        "cautionKo": "주거비처럼 반영이 느린 항목 때문에 실제 체감물가와 시차가 날 수 있습니다.",
    },
    "Core_PCE": {
        "meaningKo": "연준이 물가 목표 판단에 주로 참고하는 식품·에너지 제외 개인소비지출 물가지수입니다.",
        "readKo": "상승률 둔화는 금리 부담 완화, 재가속은 긴축 장기화 위험 쪽 증거입니다.",
        "useKo": "CPI와 함께 물가 방향의 일관성을 확인합니다.",
        "cautionKo": "발표가 늦고 과거 수치가 수정될 수 있습니다.",
    },
    "Headline_PPI": {
        "meaningKo": "미국 생산자가 최종수요 상품·서비스를 판매할 때 받는 가격의 전체 흐름입니다.",
        "readKo": "전년 대비 상승률과 최근 3개월 연율로 생산단계 가격 압력의 재가속·둔화를 봅니다.",
        "useKo": "소비자물가보다 앞단의 비용 압력을 확인하는 보조지표로 CPI와 함께 비교합니다.",
        "cautionKo": "기업 마진·환율·유통비 때문에 생산자 가격이 소비자 가격으로 그대로 전가되지는 않습니다.",
    },
    "Core_PPI": {
        "meaningKo": "식품·에너지·유통마진 성격의 무역서비스를 제외한 미국 최종수요 생산자물가입니다.",
        "readKo": "변동성이 큰 항목을 덜어 생산단계의 기조적 가격 압력을 확인합니다.",
        "useKo": "Headline PPI 움직임이 일시적 충격인지 더 넓은 비용 압력인지 교차 확인합니다.",
        "cautionKo": "CPI·PCE와 조사 대상과 가중치가 달라 같은 물가율로 해석하면 안 됩니다.",
    },
    "NFCI": {
        "meaningKo": "시카고 연은이 금리·신용·레버리지 등 금융여건을 종합한 주간 지수입니다.",
        "readKo": "0보다 높을수록 역사적 평균보다 긴축적, 낮을수록 완화적인 금융여건을 뜻합니다.",
        "useKo": "경기 자체보다 자금조달 환경과 위험자산 압력을 확인하는 보조축입니다.",
        "cautionKo": "시장가격이 빠르게 반영돼 실물경기와 방향이 잠시 다를 수 있습니다.",
    },
    "VIX": {
        "meaningKo": "S&P 500 옵션 가격에 반영된 향후 약 30일의 기대 변동성입니다.",
        "readKo": "급등은 위험회피 확대, 안정·하락은 위험선호 회복 쪽 신호입니다.",
        "useKo": "시장 스트레스와 포지션 규모 조절에 쓰되 방향 예측값으로 사용하지 않습니다.",
        "cautionKo": "높은 VIX가 곧 추가 하락을 뜻하지 않으며 급등 뒤 빠르게 정상화될 수 있습니다.",
    },
    "Yield_Curve": {
        "meaningKo": "미국 10년물과 2년물 국채금리 차이로 장단기 성장·정책 기대를 압축합니다.",
        "readKo": "역전은 긴축 부담, 다시 가팔라지는 과정은 회복 기대 또는 단기 침체 신호일 수 있습니다.",
        "useKo": "수준뿐 아니라 역전 해소의 원인이 장기금리 상승인지 단기금리 하락인지 구분합니다.",
        "cautionKo": "한 가지 임계값만으로 침체 시점을 예측할 수 없습니다.",
    },
}

TRANSFORMATION_KO = {
    "inflation_rate_yoy_and_3m_annualized": "전년동월비 인플레이션율과 3개월 연율의 최근 방향",
    "monthly_change_3m_average": "월간 증감의 3개월 이동평균 방향",
    "three_month_average_change": "3개월 평균 수준의 최근 변화",
    "four_week_average_change": "4주 이동평균의 최근 변화",
    "yoy_growth_rate": "전년동월비 증가율의 최근 방향",
    "thirteen_week_growth_rate": "13주 증가율의 최근 방향",
    "level_zscore_and_recent_change": "장기 z-score 수준과 최근 변화의 결합",
    "level_and_steepening_change": "금리차 수준과 최근 스티프닝 변화의 결합",
    "three_month_price_return": "최근 3개월 가격수익률",
    "recent_level_change": "최근 수준 변화",
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


def _display_history(name: str, visible: pd.Series) -> pd.Series:
    """Series whose units match the transformed value shown on the card."""
    s = _observations(visible)
    method = TRANSFORMATIONS.get(name, "recent_level_change")
    if method == "inflation_rate_yoy_and_3m_annualized":
        return (s.pct_change(12) * 100).dropna()
    if method == "monthly_change_3m_average":
        return s.diff().rolling(3).mean().dropna()
    if method == "three_month_average_change":
        return s.rolling(3).mean().dropna()
    if method == "four_week_average_change":
        return s.rolling(4).mean().dropna()
    if method == "yoy_growth_rate":
        return (s.pct_change(12) * 100).dropna()
    if method == "thirteen_week_growth_rate":
        return (s.pct_change(13) * 100).dropna()
    if method == "three_month_price_return":
        step = 63 if len(s) > 400 else 3
        return (s.pct_change(step) * 100).dropna()
    return s


def _history_points(series: pd.Series, max_points: int = 720) -> list[dict]:
    clean = series.dropna()
    if len(clean) > max_points:
        step = int(np.ceil(len(clean) / max_points))
        sampled = clean.iloc[::step]
        if sampled.index[-1] != clean.index[-1]:
            sampled = pd.concat([sampled, clean.iloc[[-1]]])
        clean = sampled
    return [
        {"date": pd.Timestamp(d).strftime("%Y-%m-%d"), "value": round(float(v), 4)}
        for d, v in clean.items()
        if np.isfinite(v)
    ]


def indicator_read(name: str, series: pd.Series, asof: pd.Timestamp | None = None) -> dict | None:
    axis, sign, lag, url = INDICATORS[name]
    visible, eval_asof = _visible_observations(series, lag, asof)
    if visible.empty:
        return None
    obs = pd.Timestamp(visible.index[-1])
    tr = _transform(name, visible)
    fresh_days = int((eval_asof.normalize() - obs.normalize()).days) if eval_asof is not None else None
    context_only = name in CONTEXT_ONLY_INDICATORS
    contribution = 0 if context_only else ((sign * tr["direction"]) if tr["direction"] else 0)
    display_name, value_unit, change_unit = INDICATOR_META.get(
        name, (name, "", "변화")
    )
    display_history = _display_history(name, visible)
    trend_history = (
        _observations(visible).rolling(3).mean().dropna()
        if name == "CFNAI" else pd.Series(dtype=float)
    )
    guide = INDICATOR_GUIDE.get(name, {
        "meaningKo": f"{display_name}의 최근 수준과 방향을 보여주는 지표입니다.",
        "readKo": f"{TRANSFORMATION_KO.get(tr['method'], tr['method'])}를 기준으로 방향을 읽습니다.",
        "useKo": f"{AXIS_KO[axis]} 축의 여러 근거 중 하나로만 사용합니다.",
        "cautionKo": "단일 지표만으로 국면이나 자산 가격을 예측하지 않습니다.",
    })
    if context_only:
        contribution_ko = "판정 보조"
        signal_summary = f"{TRANSFORMATION_KO.get(tr['method'], tr['method'])} → 생산단계 물가 확인용 · 국면 점수에 직접 가중하지 않음"
    elif contribution > 0:
        contribution_ko = DIRECTION_POS[axis]
        signal_summary = f"{TRANSFORMATION_KO.get(tr['method'], tr['method'])} → {AXIS_KO[axis]} {contribution_ko} 기여"
    elif contribution < 0:
        contribution_ko = DIRECTION_NEG[axis]
        signal_summary = f"{TRANSFORMATION_KO.get(tr['method'], tr['method'])} → {AXIS_KO[axis]} {contribution_ko} 기여"
    else:
        contribution_ko = "중립"
        signal_summary = f"{TRANSFORMATION_KO.get(tr['method'], tr['method'])} → 유의한 방향 없음"
    return {
        "name": name,
        "displayNameKo": display_name,
        "axis": axis,
        "sign": sign,
        "latestValue": round(tr["latest"], 4),
        "transformedValue": round(tr["transformed"], 4) if tr["transformed"] is not None else None,
        "change": round(tr["change"], 4) if tr["change"] is not None else None,
        "annualized3m": round(tr.get("annualized3m"), 4) if tr.get("annualized3m") is not None else None,
        "transformation": tr["method"],
        "transformationKo": TRANSFORMATION_KO.get(tr["method"], tr["method"]),
        "valueUnit": value_unit,
        "changeUnit": change_unit,
        "zscore": round(tr["z"], 2) if tr["z"] is not None else None,
        "direction": tr["direction"],
        "axisContribution": contribution,
        "contextOnly": context_only,
        "axisContributionKo": contribution_ko,
        "signalSummaryKo": signal_summary,
        "history": _history_points(display_history),
        "historyLabelKo": display_name if name == "CFNAI" else TRANSFORMATION_KO.get(tr["method"], display_name),
        "trendHistory": _history_points(trend_history),
        "trendLabelKo": "3개월 이동평균" if name == "CFNAI" else None,
        "referenceLines": (
            [{"value": 0.0, "labelKo": "역사적 추세 성장"},
             {"value": -0.7, "labelKo": "3개월 평균 경기위축 경계"}]
            if name == "CFNAI" else []
        ),
        "guide": guide,
        "observationDate": obs.strftime("%Y-%m-%d") if obs is not None else None,
        "releaseLagBdays": lag,
        "freshnessDays": fresh_days,
        "stale": (fresh_days is not None and fresh_days > 120),
        "source": url,
    }


def _axis_summary(reads: list[dict], expected_count: int | None = None) -> dict:
    """Aggregate indicator reads into one axis value/direction/confidence."""
    decision_reads = [r for r in reads if not r.get("contextOnly")]
    contribs = [r["axisContribution"] for r in decision_reads if r["axisContribution"] != 0]
    fresh = [r for r in decision_reads if not r.get("stale")]
    if not decision_reads:
        return {"value": None, "direction": None, "confidence": 0.0,
                "coverage": 0.0, "freshness": 0.0, "agreement": 0.0,
                "nIndicators": 0}
    value = float(np.mean(contribs)) if contribs else 0.0
    expected_count = expected_count or 3
    coverage = min(1.0, len(decision_reads) / expected_count)
    freshness = len(fresh) / len(decision_reads) if decision_reads else 0.0
    agreement = abs(float(np.mean(contribs))) if contribs else 0.0
    conf = round(coverage * freshness * (0.5 + 0.5 * agreement), 2)
    direction = "positive" if value > 0.15 else ("negative" if value < -0.15 else "flat")
    return {"value": round(value, 2), "direction": direction, "confidence": conf,
            "coverage": round(coverage, 2), "freshness": round(freshness, 2),
            "agreement": round(agreement, 2), "nIndicators": len(decision_reads),
            "nContextIndicators": len(reads) - len(decision_reads)}


def _regime_decision(growth: dict, inflation: dict) -> dict:
    gc, ic = growth["confidence"], inflation["confidence"]
    conf = round(min(gc, ic), 2)
    gv, iv = growth["value"], inflation["value"]
    thresholds = {"minimumConfidence": 0.34, "directionAbsMin": 0.15}
    base = {
        "confidence": conf,
        "confidenceRuleKo": "성장·물가 두 축 중 낮은 신뢰도를 국면 판정 신뢰도로 사용",
        "thresholds": thresholds,
        "growth": {"value": gv, "direction": growth.get("direction"),
                   "labelKo": growth.get("labelKo"), "confidence": gc},
        "inflation": {"value": iv, "direction": inflation.get("direction"),
                      "labelKo": inflation.get("labelKo"), "confidence": ic},
        "matrixKo": "성장 가속×물가 둔화=골디락스 · 가속×가속=리플레이션 · 둔화×가속=스태그플레이션 · 둔화×둔화=디플레·둔화",
    }
    if gv is None or iv is None:
        return {**base, "label": "Transition/Low confidence",
                "displayLabelKo": "판정 보류·데이터 부족", "reasonCode": "MISSING_AXIS",
                "summaryKo": "성장 또는 물가 축 데이터가 없어 국면 조합을 판정하지 않습니다."}
    if conf < thresholds["minimumConfidence"]:
        return {**base, "label": "Transition/Low confidence",
                "displayLabelKo": "전환·저신뢰", "reasonCode": "LOW_CONFIDENCE",
                "summaryKo": f"성장·물가 중 낮은 축 신뢰도가 {conf:.0%}로 판정 기준 34%에 미달합니다."}
    growth_mixed = abs(gv) <= thresholds["directionAbsMin"]
    inflation_mixed = abs(iv) <= thresholds["directionAbsMin"]
    if growth_mixed or inflation_mixed:
        if growth_mixed and inflation_mixed:
            code = "BOTH_AXES_MIXED"
            summary = f"성장({gv:+.2f})과 물가({iv:+.2f}) 신호가 모두 중립 범위(±0.15)에서 상쇄됩니다."
        elif growth_mixed:
            code = "GROWTH_MIXED"
            summary = f"물가는 {inflation.get('labelKo', '방향 확인')}이지만 성장 신호가 보합/상쇄({gv:+.2f})라 국면을 단정하지 않습니다."
        else:
            code = "INFLATION_MIXED"
            summary = f"성장은 {growth.get('labelKo', '방향 확인')}({gv:+.2f})이지만 물가 신호가 보합/상쇄({iv:+.2f})라 국면을 단정하지 않습니다."
        return {**base, "label": "Transition/Low confidence",
                "displayLabelKo": "전환·신호 상쇄", "reasonCode": code,
                "summaryKo": summary}

    if gv >= 0 and iv < 0:
        label, display = "Goldilocks", "골디락스"
    elif gv >= 0 and iv >= 0:
        label, display = "Reflation", "리플레이션"
    elif gv < 0 and iv >= 0:
        label, display = "Stagflation", "스태그플레이션"
    else:
        label, display = "Deflation/Slowdown", "디플레·둔화"
    return {**base, "label": label, "displayLabelKo": display,
            "reasonCode": label.upper().replace("/", "_"),
            "summaryKo": f"성장 {growth.get('labelKo')}({gv:+.2f}) × 물가 {inflation.get('labelKo')}({iv:+.2f}) 조합으로 {display}로 판정합니다."}


def _regime_label(growth: dict, inflation: dict) -> tuple[str, float]:
    decision = _regime_decision(growth, inflation)
    return decision["label"], decision["confidence"]


def _environment_summary(axes: dict, decision: dict) -> dict:
    """Plain-language macro read; descriptive context, never a forecast."""
    growth, inflation = axes["growth"], axes["inflation"]
    liquidity, conditions = axes["liquidity"], axes["financialConditions"]
    label = decision.get("displayLabelKo") or decision.get("label")
    growth_text = f"성장 신호는 {growth.get('labelKo', '확인 대기')}({growth.get('value') if growth.get('value') is not None else '—'})입니다."
    inflation_text = f"Headline·Core CPI, Core PCE와 시장 기대를 합친 물가 신호는 {inflation.get('labelKo', '확인 대기')}({inflation.get('value') if inflation.get('value') is not None else '—'})입니다. PPI는 생산단계 압력 확인용으로 별도 표시합니다."
    if conditions.get("value") is None:
        conditions_text = "금융여건 데이터가 부족해 위험예산 보정은 제한적입니다."
    elif conditions["value"] > 0.15:
        conditions_text = "신용스프레드·실질금리·달러를 합친 금융여건은 완화 쪽입니다."
    elif conditions["value"] < -0.15:
        conditions_text = "신용스프레드·실질금리·달러를 합친 금융여건은 긴축 쪽입니다."
    else:
        conditions_text = "금융여건 신호는 서로 상쇄돼 중립권입니다."
    if liquidity.get("value") is None:
        liquidity_text = "유동성 축은 데이터 확인 대기입니다."
    else:
        liquidity_text = f"연준 자산·RRP·TGA·M2를 합친 유동성은 {liquidity.get('labelKo')} 쪽입니다."
    return {
        "headlineKo": f"현재 거시 판정은 ‘{label}’이며, 성장과 물가의 방향을 먼저 보고 금융여건·유동성으로 위험예산을 보정합니다.",
        "takeawaysKo": [growth_text, inflation_text, conditions_text, liquidity_text],
        "watchKo": decision.get("summaryKo"),
        "methodKo": "Headline CPI를 체감·에너지 충격, Core CPI/PCE를 기조 물가로 구분합니다. PPI는 중복 가중 없이 생산단계 압력을 교차 확인하며, 단일 발표로 국면을 확정하지 않습니다.",
    }


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
        expected_count = sum(1 for name, spec in INDICATORS.items()
                             if spec[0] == axis and name not in CONTEXT_ONLY_INDICATORS)
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

    decision = _regime_decision(axes["growth"], axes["inflation"])
    label, conf = decision["label"], decision["confidence"]

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
        "regimeDecision": decision,
        "environmentSummary": _environment_summary(axes, decision),
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
