"""Point-in-time signal inputs for MVMA-v1. Pure: no I/O, no network, no return, no NAV.

Every function answers "what could an investor have known at decision date d". Inputs are `Observation`s carrying
both the economic observation date and the date the value became usable (`effective_at`). The rules:

* `asof` returns the latest observation whose `effective_at` is ON OR BEFORE the decision date; a value that became
  usable later is invisible, whatever its observation date.
* A history statistic (the 60-month mean PER, the 60-month credit-spread percentile) is computed over the values
  RECORDED at earlier decision dates (`decision_series`), never over today's series re-read for the past, and never
  includes the current decision date.
* A quantity that has no meaning (non-positive earnings for a PER, too few valid history points) is `None`, never a
  substitute number.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

PE_HISTORY_MONTHS = 60
PE_HISTORY_MIN_VALID = 54          # 90% of the window must be measured, else the mean is missing
EARNINGS_CHANGE_MONTHS = 3
CREDIT_HISTORY_MONTHS = 60
CREDIT_HISTORY_MIN_VALID = 54
CREDIT_PERCENTILE = 75.0
CREDIT_WIDENING_MONTHS = 3
DRAWDOWN_WINDOW_SESSIONS = 252
DRAWDOWN_TRIGGER = -0.20
SHILLER_EARNINGS_LAG_MONTHS = 4   # quarter-end earnings usable only 4 full months after the quarter ends


@dataclass(frozen=True)
class Observation:
    observation_date: date
    effective_at: date
    value: float | None


def _finite(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)


def asof(observations: list[Observation], decision_date: date) -> Observation | None:
    """Latest-observed record usable on `decision_date` (effective_at <= decision_date)."""
    usable = [o for o in observations if o.effective_at <= decision_date]
    if not usable:
        return None
    return max(usable, key=lambda o: (o.observation_date, o.effective_at))


def decision_series(observations: list[Observation], decision_dates: list[date]) -> list[float | None]:
    """The value an investor would have recorded at each decision date (None when nothing usable / not finite)."""
    out = []
    for d in decision_dates:
        o = asof(observations, d)
        out.append(o.value if o is not None and _finite(o.value) else None)
    return out


def price_to_earnings(price: float | None, earnings: float | None) -> float | None:
    if not _finite(price) or not _finite(earnings) or earnings <= 0 or price <= 0:
        return None
    return price / earnings


def trailing_mean_prior(values: list[float | None], index: int, window: int = PE_HISTORY_MONTHS,
                        min_valid: int = PE_HISTORY_MIN_VALID) -> float | None:
    """Mean of values[index-window .. index-1] (the current value is excluded) if enough are measured."""
    if index < window:
        return None
    sample = [v for v in values[index - window:index] if _finite(v)]
    if len(sample) < min_valid:
        return None
    return sum(sample) / len(sample)


def valuation_discount(values: list[float | None], index: int) -> float | None:
    """PE(t) / PE5(t) - 1, with PE5 the mean of the 60 PRIOR decision-date values."""
    current = values[index]
    mean = trailing_mean_prior(values, index)
    if not _finite(current) or mean is None or mean <= 0:
        return None
    return current / mean - 1.0


def valuation_cheap(values: list[float | None], index: int) -> bool | None:
    discount = valuation_discount(values, index)
    return None if discount is None else discount < 0.0


def earnings_stable(eps_values: list[float | None], index: int, lag: int = EARNINGS_CHANGE_MONTHS) -> bool | None:
    """EPS(t) >= EPS(t-3), both as recorded at their own decision dates."""
    if index < lag:
        return None
    now, before = eps_values[index], eps_values[index - lag]
    if not _finite(now) or not _finite(before):
        return None
    return now >= before


def percentile_linear(sample: list[float], q: float) -> float:
    """Type-7 (linear interpolation) percentile, the numpy default, written out so it cannot drift with numpy."""
    xs = sorted(sample)
    if not xs:
        raise ValueError("EMPTY_SAMPLE")
    h = (len(xs) - 1) * q / 100.0
    lo = math.floor(h)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (h - lo) * (xs[hi] - xs[lo])


def credit_stress(spreads: list[float | None], index: int) -> bool | None:
    """Spread above the 75th percentile of its 60 PRIOR decision-date values AND wider than 3 decision dates ago."""
    current = spreads[index]
    if not _finite(current) or index < CREDIT_HISTORY_MONTHS or index < CREDIT_WIDENING_MONTHS:
        return None
    sample = [v for v in spreads[index - CREDIT_HISTORY_MONTHS:index] if _finite(v)]
    before = spreads[index - CREDIT_WIDENING_MONTHS]
    if len(sample) < CREDIT_HISTORY_MIN_VALID or not _finite(before):
        return None
    return current > percentile_linear(sample, CREDIT_PERCENTILE) and current > before


def drawdown_from_high(closes: list[float | None], index: int, window: int = DRAWDOWN_WINDOW_SESSIONS) -> float | None:
    """close(t) / max(close over the `window` sessions ending at t, inclusive) - 1. Missing if any session is missing."""
    if index + 1 < window:
        return None
    sample = closes[index + 1 - window:index + 1]
    if not all(_finite(v) and v > 0 for v in sample):
        return None
    return sample[-1] / max(sample) - 1.0


def deep_drawdown(closes: list[float | None], index: int) -> bool | None:
    dd = drawdown_from_high(closes, index)
    return None if dd is None else dd <= DRAWDOWN_TRIGGER


def quarter_end_on_or_before(month_index: int) -> int:
    """Largest month index (year*12 + month-1) <= month_index whose month is March, June, September or December."""
    return month_index - ((month_index % 12) + 1) % 3


def shiller_earnings_effective_month(decision_month_index: int, lag_months: int = SHILLER_EARNINGS_LAG_MONTHS) -> int:
    """The Shiller earnings month usable at the end of decision month M: the latest quarter-end month q <= M - lag.

    Shiller interpolates quarterly S&P earnings to months, so an intra-quarter month depends on the NEXT quarter-end
    value; only quarter-end months are ever read, and only once `lag_months` full months have passed after them.
    """
    return quarter_end_on_or_before(decision_month_index - lag_months)


def month_index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def month_from_index(index: int) -> tuple[int, int]:
    return index // 12, index % 12 + 1

