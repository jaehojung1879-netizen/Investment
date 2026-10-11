"""SPY versus QQQ as two passive alternatives — descriptive, not stock-picking alpha.

Every statistic here is computed on ONE matched session set: the sessions both
ETFs have a total-return close for, inside one declared window. Neither ETF is
given its own start or end. The headline window is the existing US weekly
replay's execution span (``docs/weekly-decision/weekly-passive-first-v1-weekly
-replay.json``: 2013-01-07 .. 2026-09-14), fixed BEFORE any QQQ figure was
computed and not moved afterwards; the full sealed overlap is published beside
it as a secondary view, never instead of it.

Conventions (stated, not implied):

* Return basis: as-traded forward total return, distributions reinvested at the
  ex-date close, gross of investor withholding tax.
* Expense ratios are NOT deducted: market-price total return already carries
  them. Deducting them again would double count the fee.
* Trading costs: one entry and one exit at ``config.json kellyPortfolio
  .transactionCosts.US`` (commission + spread in, commission + spread + sell fee
  out), identical for both ETFs. They move levels, never the ranking.
* USD Sharpe: excess over the effective federal funds rate (FRED ``DFF``, as
  sealed in the replay macro panel), accrued ACT/360 between sessions.
  KRW Sharpe: excess over the BOK policy-rate proxy the replay uses, ACT/365.
* KRW: USD wealth x fx(t)/fx(start), one H.10 fixing per session shared by both
  ETFs. FX multiplies both paths by the same factor, so it changes levels and
  volatility but cannot change the QQQ/SPY ratio; that identity is published.

A higher historical QQQ CAGR is a DESCRIPTIVE finding about one sample. It is
not evidence for a future weight, and nothing here sets one.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252
HEADLINE_WINDOW = ("2013-01-07", "2026-09-14")
HEADLINE_WINDOW_SOURCE = "docs/weekly-decision/weekly-passive-first-v1-weekly-replay.json calendar first.date / last.endDate"
ROLLING = {"1y": 252, "3y": 756}


def span_years(first: pd.Timestamp, last: pd.Timestamp) -> float:
    # Same year length replay_valuation.span_years uses.
    return (pd.Timestamp(last) - pd.Timestamp(first)).days / 365.2425


def matched(spy: pd.Series, qqq: pd.Series, start: str, end: str) -> pd.DataFrame:
    """Both closes on the sessions BOTH carry inside [start, end]."""
    frame = pd.concat({"SPY": spy, "QQQ": qqq}, axis=1, join="inner").sort_index()
    frame = frame.loc[pd.Timestamp(start):pd.Timestamp(end)]
    if frame.isna().any().any() or (frame <= 0).any().any():
        raise ValueError("MATCHED_SERIES_INVALID")
    if len(frame) < 2:
        raise ValueError("MATCHED_WINDOW_EMPTY")
    return frame


def rate_accrual(dates: pd.DatetimeIndex, annual_pct: dict, day_count: int) -> pd.Series:
    """Per-interval simple accrual of the rate in force at the interval start."""
    rates = pd.Series(annual_pct, dtype=float)
    rates.index = pd.to_datetime(rates.index)
    rates = rates.sort_index().dropna()
    pos = rates.index.searchsorted(dates[:-1], side="right") - 1
    if (pos < 0).any():
        raise ValueError("RISK_FREE_NOT_AVAILABLE_AT_START")
    days = np.diff(dates.values).astype("timedelta64[D]").astype(float)
    accrual = rates.to_numpy()[pos] / 100 * days / day_count
    return pd.Series(accrual, index=dates[1:])


def path_statistics(nav: pd.Series, rf_accrual: pd.Series | None) -> dict:
    returns = nav.pct_change().dropna()
    years = span_years(nav.index[0], nav.index[-1])
    total = nav.iloc[-1] / nav.iloc[0] - 1
    cagr = (1 + total) ** (1 / years) - 1
    vol = float(returns.std(ddof=1) * math.sqrt(TRADING_DAYS))
    drawdown = nav / nav.cummax() - 1
    trough = drawdown.idxmin()
    peak = nav.loc[:trough].idxmax()
    recovered = nav.loc[trough:][nav.loc[trough:] >= nav.loc[peak]]
    out = {"totalReturnPct": round(total * 100, 3), "cagrPct": round(cagr * 100, 3),
           "annualizedVolPct": round(vol * 100, 3),
           "maxDrawdownPct": round(float(drawdown.min()) * 100, 3),
           "maxDrawdownPeak": peak.strftime("%Y-%m-%d"),
           "maxDrawdownTrough": trough.strftime("%Y-%m-%d"),
           "maxDrawdownRecovered": recovered.index[0].strftime("%Y-%m-%d") if len(recovered) else None,
           "sharpe": None}
    if rf_accrual is not None:
        excess = returns - rf_accrual.reindex(returns.index)
        if excess.notna().all() and excess.std(ddof=1) > 0:
            out["sharpe"] = round(float(excess.mean() / excess.std(ddof=1) * math.sqrt(TRADING_DAYS)), 4)
        out["riskFreeCagrPct"] = round(((1 + rf_accrual).prod() ** (1 / years) - 1) * 100, 3)
    out["calmar"] = round(cagr / abs(drawdown.min()), 4) if drawdown.min() < 0 else None
    return out


def calendar_years(frame: pd.DataFrame) -> list[dict]:
    """Year-end to year-end on matched sessions; first/last years marked partial."""
    out = []
    ends = frame.groupby(frame.index.year).tail(1)
    previous = frame.iloc[0]
    previous_date = frame.index[0]
    for stamp, row in ends.iterrows():
        spy = row["SPY"] / previous["SPY"] - 1
        qqq = row["QQQ"] / previous["QQQ"] - 1
        full = previous_date.year == stamp.year - 1 and stamp.month == 12 and stamp.day >= 24
        out.append({"year": stamp.year, "from": previous_date.strftime("%Y-%m-%d"),
                    "to": stamp.strftime("%Y-%m-%d"), "fullYear": bool(full),
                    "spyPct": round(spy * 100, 3), "qqqPct": round(qqq * 100, 3),
                    "qqqMinusSpyPctPt": round((qqq - spy) * 100, 3),
                    "winner": "QQQ" if qqq > spy else ("SPY" if spy > qqq else "TIE")})
        previous, previous_date = row, stamp
    return out


def rolling_relative(frame: pd.DataFrame, sessions: int) -> dict:
    """QQQ wealth over SPY wealth across every ``sessions``-long window."""
    ratio = frame["QQQ"] / frame["SPY"]
    if len(ratio) <= sessions:
        return {"available": False, "reason": "INSUFFICIENT_SESSIONS", "windows": 0}
    rel = (ratio / ratio.shift(sessions) - 1).dropna()
    worst = rel.idxmin()
    best = rel.idxmax()
    return {"available": True, "sessions": sessions, "windows": int(len(rel)),
            "qqqAheadSharePct": round(float((rel > 0).mean() * 100), 2),
            "medianPct": round(float(rel.median() * 100), 3),
            "p10Pct": round(float(rel.quantile(.10) * 100), 3),
            "p90Pct": round(float(rel.quantile(.90) * 100), 3),
            "worstPct": round(float(rel.min() * 100), 3), "worstEnd": worst.strftime("%Y-%m-%d"),
            "bestPct": round(float(rel.max() * 100), 3), "bestEnd": best.strftime("%Y-%m-%d"),
            "note": "overlapping windows; the share is descriptive, not an independent-sample probability"}


def relative_path(frame: pd.DataFrame) -> dict:
    ratio = frame["QQQ"] / frame["SPY"]
    ratio = ratio / ratio.iloc[0]
    drawdown = ratio / ratio.cummax() - 1
    trough = drawdown.idxmin()
    peak = ratio.loc[:trough].idxmax()
    spy_r = frame["SPY"].pct_change().dropna()
    qqq_r = frame["QQQ"].pct_change().dropna()
    diff = qqq_r - spy_r
    return {"endingRelativeWealth": round(float(ratio.iloc[-1]), 6),
            "maxRelativeUnderperformancePct": round(float(drawdown.min() * 100), 3),
            "maxRelativeUnderperformancePeak": peak.strftime("%Y-%m-%d"),
            "maxRelativeUnderperformanceTrough": trough.strftime("%Y-%m-%d"),
            "dailyReturnCorrelation": round(float(spy_r.corr(qqq_r)), 5),
            "trackingErrorPct": round(float(diff.std(ddof=1) * math.sqrt(TRADING_DAYS) * 100), 3),
            "betaQqqOnSpy": round(float(np.cov(qqq_r, spy_r, ddof=1)[0, 1] / spy_r.var(ddof=1)), 4)}


def weekly_points(frame: pd.DataFrame, fx: pd.Series | None) -> list[dict]:
    """Last matched session of each ISO week, for charts. Real observations only."""
    nav = frame / frame.iloc[0]
    weeks = nav.groupby([nav.index.isocalendar().year, nav.index.isocalendar().week]).tail(1)
    out = []
    for stamp, row in weeks.iterrows():
        point = {"date": stamp.strftime("%Y-%m-%d"), "spyNavUsd": round(float(row["SPY"]), 6),
                 "qqqNavUsd": round(float(row["QQQ"]), 6),
                 "qqqOverSpy": round(float(row["QQQ"] / row["SPY"]), 6)}
        if fx is not None and np.isfinite(fx.get(stamp, np.nan)):
            factor = float(fx.loc[stamp] / fx.iloc[0])
            point["fxFactor"] = round(factor, 6)
        out.append(point)
    return out


def net_of_trading_costs(frame: pd.DataFrame, costs: dict) -> dict:
    """Buy at the first matched close, sell at the last; same cost for both ETFs."""
    entry = (costs["commissionBps"] + costs["spreadBps"]) / 1e4
    exit_ = (costs["commissionBps"] + costs["spreadBps"] + costs["sellTaxBps"]) / 1e4
    years = span_years(frame.index[0], frame.index[-1])
    out = {"entryCostPct": round(entry * 100, 4), "exitCostPct": round(exit_ * 100, 4),
           "costSource": "config.json kellyPortfolio.transactionCosts.US",
           "expenseRatioDeducted": False,
           "expenseRatioNote": "fund fees are inside market-price total return; not deducted again"}
    for ticker in ("SPY", "QQQ"):
        gross = frame[ticker].iloc[-1] / frame[ticker].iloc[0]
        net = gross * (1 - entry) * (1 - exit_)
        out[ticker] = {"netTotalReturnPct": round((net - 1) * 100, 3),
                       "netCagrPct": round((net ** (1 / years) - 1) * 100, 3)}
    out["qqqMinusSpyNetCagrPctPt"] = round(out["QQQ"]["netCagrPct"] - out["SPY"]["netCagrPct"], 3)
    return out


def compare(spy: pd.Series, qqq: pd.Series, *, start: str, end: str, fx: pd.Series,
            usd_rate: dict, krw_rate: dict, costs: dict) -> dict:
    frame = matched(spy, qqq, start, end)
    dates = frame.index
    usd_rf = rate_accrual(dates, usd_rate, 360)
    usd = {t: path_statistics(frame[t] / frame[t].iloc[0], usd_rf) for t in ("SPY", "QQQ")}
    years = calendar_years(frame)
    full_years = [y for y in years if y["fullYear"]]
    rel = relative_path(frame)

    fx_window = fx.reindex(dates)
    krw: dict = {"available": False}
    if np.isfinite(fx_window.iloc[0]) and np.isfinite(fx_window.iloc[-1]):
        valid = fx_window.dropna()
        krw_frame = frame.loc[valid.index].mul(valid / valid.iloc[0], axis=0)
        krw_rf = rate_accrual(valid.index, krw_rate, 365)
        ratio_usd = frame["QQQ"].iloc[-1] / frame["SPY"].iloc[-1] / (frame["QQQ"].iloc[0] / frame["SPY"].iloc[0])
        ratio_krw = (krw_frame["QQQ"].iloc[-1] / krw_frame["SPY"].iloc[-1]
                     / (krw_frame["QQQ"].iloc[0] / krw_frame["SPY"].iloc[0]))
        krw = {"available": True, "sessionsWithFx": int(len(valid)),
               "sessionsWithoutFx": int(len(dates) - len(valid)),
               "fxStart": float(valid.iloc[0]), "fxEnd": float(valid.iloc[-1]),
               "usdKrwChangePct": round((valid.iloc[-1] / valid.iloc[0] - 1) * 100, 3),
               "SPY": path_statistics(krw_frame["SPY"] / krw_frame["SPY"].iloc[0], krw_rf),
               "QQQ": path_statistics(krw_frame["QQQ"] / krw_frame["QQQ"].iloc[0], krw_rf),
               "relativeWealthIdentityError": float(abs(ratio_krw / ratio_usd - 1)),
               "fxSeries": "FRED H.10 DEXKOUS, latest fixing on or before the session",
               "riskFree": "BOK policy-rate proxy (replay-v16 risk-free/KRW), ACT/365"}
    return {
        "window": {"start": dates[0].strftime("%Y-%m-%d"), "end": dates[-1].strftime("%Y-%m-%d"),
                   "requestedStart": start, "requestedEnd": end,
                   "matchedSessions": int(len(dates)),
                   "calendarYears": round(span_years(dates[0], dates[-1]), 4)},
        "usd": usd, "usdRiskFree": "FRED DFF effective federal funds rate (replay-v16 macro), ACT/360",
        "relative": rel,
        "rolling": {k: rolling_relative(frame, n) for k, n in ROLLING.items()},
        "calendarYears": years,
        "fullYearsCompared": len(full_years),
        "fullYearsQqqAhead": sum(1 for y in full_years if y["winner"] == "QQQ"),
        "spyAheadYears": [y["year"] for y in years if y["winner"] == "SPY"],
        "krw": krw,
        "netOfTradingCosts": net_of_trading_costs(frame, costs),
        "weekly": weekly_points(frame, fx_window),
    }
