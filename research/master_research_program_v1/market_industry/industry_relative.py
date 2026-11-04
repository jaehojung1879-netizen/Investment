"""Industry-relative total return against the regional ETF on identical dates. Pure: no I/O, no data.

    industry relative return = industry basket TR (equal- or cap-weighted) - regional ETF TR, over the SAME [start, end] window.

Rules (each tested on synthetic inputs):

* MEMBERSHIP IS FIXED AT THE SIGNAL DATE from a PIT membership function the caller supplies (``membership_on(as_of)`` returning
  ``{ticker: industry}``). The basket is the cohort of that date; later membership never enters it, and the window starts no earlier
  than the signal date.
* IDENTICAL DATES. Every constituent window and the ETF window must have exactly the same start and end; a mismatch raises
  ``DATE_MISMATCH`` rather than being aligned silently.
* NO SILENT RENORMALISATION. A constituent without a return (or, for cap weights, without a signal-date cap) makes the basket
  ``None``; the missing names are COUNTED and returned. Dropping them and re-weighting the rest would be a different basket.
* Concentration diagnostics (top-1 / top-2 cap share) travel with every cap-weighted basket.
"""
from __future__ import annotations

import math
from datetime import date


def _d(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _finite(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def check_window(window, stock_windows, etf_window):
    start, end = _d(window[0]), _d(window[1])
    if end <= start:
        raise ValueError("EMPTY_WINDOW")
    if (_d(etf_window[0]), _d(etf_window[1])) != (start, end):
        raise ValueError("DATE_MISMATCH: ETF")
    for ticker, w in stock_windows.items():
        if w is not None and (_d(w[0]), _d(w[1])) != (start, end):
            raise ValueError("DATE_MISMATCH: " + ticker)
    return start, end


def concentration(caps):
    vals = sorted((c for c in caps.values() if _finite(c) and c > 0), reverse=True)
    total = sum(vals)
    if not vals or total <= 0:
        return {"top1CapShare": None, "top2CapShare": None, "names": len(caps)}
    return {"top1CapShare": vals[0] / total, "top2CapShare": sum(vals[:2]) / total, "names": len(caps)}


def basket_return(members, returns, caps=None, weighting="EQUAL"):
    """{'value': float|None, 'missingReturn': n, 'missingCap': n, 'names': n}. No renormalisation over missing names."""
    members = sorted(members)
    missing_ret = [m for m in members if not _finite(returns.get(m))]
    out = {"names": len(members), "missingReturn": len(missing_ret), "missingCap": 0, "value": None, "weighting": weighting}
    if not members:
        out["reason"] = "EMPTY_BASKET"
        return out
    if weighting == "EQUAL":
        if missing_ret:
            out["reason"] = "MISSING_CONSTITUENT_RETURN"
            return out
        out["value"] = sum(returns[m] for m in members) / len(members)
        return out
    if weighting != "CAP":
        raise ValueError("UNKNOWN_WEIGHTING")
    caps = caps or {}
    missing_cap = [m for m in members if not (_finite(caps.get(m)) and caps[m] > 0)]
    out["missingCap"] = len(missing_cap)
    if missing_ret or missing_cap:
        out["reason"] = "MISSING_CONSTITUENT_RETURN" if missing_ret else "MISSING_SIGNAL_DATE_CAP"
        return out
    total = sum(caps[m] for m in members)
    out["value"] = sum(caps[m] * returns[m] for m in members) / total
    out.update(concentration({m: caps[m] for m in members}))
    return out


def industry_relative(membership_on, signal_date, window, industry, stock_returns, etf_return, caps=None):
    """Industry basket TR minus ETF TR for the cohort of `signal_date`.

    stock_returns: {ticker: {"start", "end", "tr"}}; etf_return: {"start", "end", "tr"}; caps: {ticker: signal-date cap} or None.
    """
    if _d(window[0]) < _d(signal_date):
        raise ValueError("WINDOW_STARTS_BEFORE_SIGNAL")
    members = sorted(t for t, ind in membership_on(signal_date).items() if ind == industry)
    windows = {t: ((stock_returns[t]["start"], stock_returns[t]["end"]) if t in stock_returns else None) for t in members}
    check_window(window, windows, (etf_return["start"], etf_return["end"]))
    if not _finite(etf_return.get("tr")):
        raise ValueError("ETF_RETURN_MISSING")
    rets = {t: (stock_returns[t]["tr"] if t in stock_returns else None) for t in members}
    out = {"industry": industry, "signalDate": str(_d(signal_date)), "members": members}
    for weighting in ("EQUAL", "CAP"):
        if weighting == "CAP" and caps is None:
            out["CAP"] = {"value": None, "reason": "NO_CAPS_SUPPLIED"}
            continue
        b = basket_return(members, rets, caps, weighting)
        b["relative"] = None if b["value"] is None else b["value"] - etf_return["tr"]
        out[weighting] = b
    return out


def industry_cross_section(membership_on, signal_date, window, stock_returns, etf_return, caps=None):
    """Every industry of the signal-date membership, plus how many baskets were refused for a missing constituent."""
    industries = sorted({ind for ind in membership_on(signal_date).values() if ind is not None})
    rows = [industry_relative(membership_on, signal_date, window, ind, stock_returns, etf_return, caps) for ind in industries]
    return {"rows": rows, "industries": len(rows), "equalWeightRefused": sum(1 for r in rows if r["EQUAL"]["value"] is None)}
