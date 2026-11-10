"""Explicit unavailable outcomes, float64 returns, fixed BOK risk-free proxy."""
import numpy as np
import pandas as pd


def metrics(days, navs, capital, rf):
    nav = pd.Series(navs, index=pd.to_datetime(days), dtype=float)
    if nav.isna().any() or len(nav) < 2:
        return {'cagr': None, 'mdd': None, 'sharpe': None, 'excessCagr': None, 'yearly': None,
                'status': 'SOURCE_BLOCKED_OR_INSUFFICIENT_OBSERVATIONS'}
    r = nav.pct_change().iloc[1:]
    ex = r - rf.reindex(r.index).fillna(0)
    sd = r.std()
    yearly = {}
    for year, g in nav.groupby(nav.index.year):
        loc = nav.index.get_loc(g.index[0])
        base = nav.iloc[loc - 1] if loc else capital
        yearly[str(year)] = float(g.iloc[-1] / base - 1)
    return {'cagr': float((nav.iloc[-1] / capital) ** (252 / (len(nav) - 1)) - 1),
            'calendarCagr': float((nav.iloc[-1] / capital) ** (365.2425 / (nav.index[-1] - nav.index[0]).days) - 1),
            'mdd': float((nav / nav.cummax() - 1).min()),
            'sharpe': float(ex.mean() / sd * np.sqrt(252)) if sd > 0 else None,
            'finalNavKrw': float(nav.iloc[-1]), 'yearly': yearly, 'sessions': len(nav), 'status': 'CALCULATED'}
