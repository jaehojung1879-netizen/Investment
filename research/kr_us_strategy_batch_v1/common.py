"""Predeclared, market-independent estimators; no production or live writes."""
from __future__ import annotations

import hashlib
from functools import lru_cache

import numpy as np
import pandas as pd

SEED, DRAWS = 20261118, 4000


@lru_cache(maxsize=16)
def _block_counts(span, block):
    """Counts encode the exact non-circular moving-block draw on the full axis."""
    rng = np.random.default_rng(SEED)
    starts = rng.integers(0, span - block + 1, size=(DRAWS, int(np.ceil(span / block))))
    idx = (starts[:, :, None] + np.arange(block)).reshape(DRAWS, -1)[:, :span]
    counts = np.zeros((DRAWS, span), dtype=np.float64)
    np.add.at(counts, (np.arange(DRAWS)[:, None], idx), 1)
    counts.flags.writeable = False
    return counts


def stats(v, H=126, mask=None):
    """Paired differences in decimal units, preserving holes on the weekly axis.

    The tail probability is the historical bootstrap-tail approximation, not a
    studentized null test. Both names are retained to make that limit explicit.
    """
    v = np.asarray(v, dtype=float)
    if v.ndim != 1:
        raise ValueError("stats requires a single original weekly axis")
    block = {126: 25, 252: 50}[int(H)]
    ok = np.isfinite(v)
    if mask is not None:
        m = np.asarray(mask, dtype=bool)
        if m.shape != v.shape:
            raise ValueError("mask must retain the original weekly axis")
        ok &= m
    n = int(ok.sum())
    out = {"n": n, "mean": float(v[ok].mean()) if n else None,
           "blockWeeks": block, "independentBlocksApprox": round(n / block, 2),
           "ci": None, "pOneSided": None, "pOneSidedApprox": None}
    if n < 2 * block:
        return out
    counts = _block_counts(len(v), block)
    numerator = counts @ np.where(ok, v, 0)
    denominator = counts @ ok.astype(float)
    means = numerator[denominator > 0] / denominator[denominator > 0]
    p = float((1 + (means <= 0).sum()) / (len(means) + 1))
    out.update(ci=np.quantile(means, [0.025, 0.975]).tolist(),
               pOneSided=p, pOneSidedApprox=p)
    return out


def holm(pvalues):
    """Holm step-down; unavailable hypotheses retain p=1 family slots."""
    names = list(pvalues)
    p = np.array([1.0 if pvalues[k] is None else float(pvalues[k]) for k in names])
    if np.any(~np.isfinite(p)) or np.any((p < 0) | (p > 1)):
        raise ValueError("invalid probability")
    order = np.argsort(p, kind="stable")
    adj = np.minimum(1, np.maximum.accumulate(p[order] * np.arange(len(p), 0, -1)))
    return {names[int(j)]: float(a) for j, a in zip(order, adj, strict=True)}


def neutral_order(tickers, date, market):
    d = pd.Timestamp(date).strftime("%Y-%m-%d")
    return sorted(map(str, tickers), key=lambda t: (
        hashlib.sha256(f"{SEED}|{market}|{d}|{t}".encode()).hexdigest(), t))


def match_book(frame, weights, etf, sector_col="industry", cap_col="_mcap", order=None):
    """Strict one-to-one same-industry, [0.5,2] cap match, without rescue.

    Caller supplies the point-in-time eligible ticker-indexed peer frame. A
    failed leg invalidates the complete control book; partial audit is retained.
    """
    if not frame.index.is_unique:
        raise ValueError("peer frame must have unique ticker index")
    held = {t for t, w in weights.items() if t != etf and w > 0}
    if order is None:
        order = sorted(held, key=lambda t: (-weights[t], t))
    else:
        order = [t for t in order if t in held]
        if set(order) != held or len(order) != len(held):
            raise ValueError("matching order must contain each held stock once")
    matched, used, audit = {}, set(), []
    if weights.get(etf, 0) > 0:
        matched[etf] = float(weights[etf])
    for rank, t in enumerate(order, 1):
        row = {"rank": rank, "ticker": t, "weight": float(weights[t]),
               "peer": None, "reason": None, "heldCap": None, "peerCap": None,
               "capRatio": None, "logCapDistance": None,
               "sameIndustryAvailable": 0, "withinCaliperAvailable": 0}
        if t not in frame.index:
            row["reason"] = "HELD_NOT_IN_ELIGIBLE_POOL"
        else:
            sector, cap = frame.at[t, sector_col], frame.at[t, cap_col]
            if pd.isna(sector):
                row["reason"] = "HELD_INDUSTRY_MISSING"
            elif pd.isna(cap) or not np.isfinite(float(cap)) or float(cap) <= 0:
                row["reason"] = "HELD_CAP_INVALID"
            else:
                cap = float(cap)
                row["heldCap"] = cap
                peer = frame.loc[(frame[sector_col] == sector) & ~frame.index.isin(held | used)]
                row["sameIndustryAvailable"] = len(peer)
                if peer.empty:
                    row["reason"] = "NO_UNUSED_SAME_INDUSTRY_PEER"
                else:
                    peer = peer.copy()
                    peer["_ratio"] = pd.to_numeric(peer[cap_col], errors="coerce") / cap
                    peer = peer.loc[np.isfinite(peer["_ratio"]) & peer["_ratio"].between(0.5, 2)]
                    row["withinCaliperAvailable"] = len(peer)
                    if peer.empty:
                        row["reason"] = "NO_PEER_WITHIN_CAP_CALIPER"
                    else:
                        chosen = min(peer.index, key=lambda p: (abs(np.log(peer.at[p, "_ratio"])), str(p)))
                        used.add(chosen)
                        matched[chosen] = float(weights[t])
                        row.update(peer=str(chosen), reason="MATCHED", peerCap=float(peer.at[chosen, cap_col]),
                                   capRatio=float(peer.at[chosen, "_ratio"]),
                                   logCapDistance=float(abs(np.log(peer.at[chosen, "_ratio"]))))
        audit.append(row)
    return (None if any(a["reason"] != "MATCHED" for a in audit) else matched), audit


def choose_policy(excess126df, cohort_mdd126df, etf_mdd126series,
                  exit126series, all_dates, meta, allowed):
    """Annual selection using only fully matured data strictly before fit date."""
    dates = pd.DatetimeIndex(all_dates)
    if not dates.is_monotonic_increasing or dates.has_duplicates:
        raise ValueError("policy dates must be strictly chronological")
    r = excess126df.copy()
    r.index = pd.DatetimeIndex(r.index)
    md = cohort_mdd126df.copy()
    md.index = pd.DatetimeIndex(md.index)
    em = etf_mdd126series.copy()
    em.index = pd.DatetimeIndex(em.index)
    ex = pd.to_datetime(exit126series.copy())
    ex.index = pd.DatetimeIndex(ex.index)
    allowed = [c for c in allowed if c in r and c in md]
    r = r.reindex(index=dates, columns=allowed)
    md = md.reindex(index=dates, columns=allowed)
    em, ex = em.reindex(dates), ex.reindex(dates)
    finite = np.isfinite(r).all(axis=1) & np.isfinite(md).all(axis=1) & np.isfinite(em)
    choices, trace, fits = [], [], []
    current, year, fit = "ETF", None, None
    for d in dates:
        if d.year != year:
            year, fit = d.year, d
            mask = finite & ex.notna() & (ex < fit) & (dates < fit)
            n = int(mask.sum())
            maxexit = ex[mask].max() if n else pd.NaT
            sufficient = bool(n >= 104 and allowed)
            etf_mdd = float(em[mask].mean()) if n else None
            candidates = []
            for c in allowed:
                s = stats(r[c], 126, mask) if sufficient else {"n": n, "mean": None, "ci": None,
                                                             "pOneSided": None, "pOneSidedApprox": None}
                mdd = float(md.loc[mask, c].mean()) if n else None
                guard = bool(mdd is not None and etf_mdd is not None and mdd >= etf_mdd)
                lower = s["ci"][0] if s["ci"] is not None else None
                candidates.append({"id": c, "stats": s, "lcb": lower, "meanCohortMdd": mdd,
                                   "etfMeanCohortMdd": etf_mdd, "riskGuard": guard,
                                   "eligible": bool(sufficient and guard and lower is not None and lower > 0)})
            eligible = [c for c in candidates if c["eligible"]]
            def key(c):
                m = meta[c["id"]]
                return (-c["lcb"], m["q"], m.get("k") or 0, c["id"])
            current = min(eligible, key=key)["id"] if eligible else "ETF"
            receipt = {"fitDate": fit.isoformat(), "year": year, "nTrain": n,
                       "maxTrainExit": maxexit.isoformat() if pd.notna(maxexit) else None,
                       "sufficient": sufficient, "chosen": current,
                       "reason": "POSITIVE_LCB_AND_RISK_GUARD" if eligible else (
                           "NO_ELIGIBLE_CANDIDATE" if sufficient else "INSUFFICIENT_MATURED_COMMON"),
                       "candidateFits": candidates}
            fits.append(receipt)
        choices.append(current)
        trace.append({"date": d, "fitDate": fit, "chosen": current, "nTrain": fits[-1]["nTrain"],
                      "maxTrainExit": fits[-1]["maxTrainExit"], "sufficient": fits[-1]["sufficient"],
                      "reason": fits[-1]["reason"]})
    return {"choices": pd.Series(choices, index=dates, name="chosen"),
            "trace": pd.DataFrame(trace), "fits": fits}


def nav_window(nav, benchmark):
    """Paired daily NAV window, with CAGR gap split into arithmetic+remainder."""
    pair = pd.concat([nav.rename("nav"), benchmark.rename("etf")], axis=1, join="inner")
    if len(pair) < 2:
        return {"n": len(pair), "cagr": None, "etfCagr": None, "cagrGap": None, "excess": None,
                "mdd": None, "etfMdd": None, "annualArithmeticDailyGap": None,
                "compoundingRemainder": None}
    if not np.isfinite(pair.to_numpy()).all() or (pair <= 0).any().any():
        raise ValueError("unresolved or nonpositive NAV cannot be silently removed")
    pair.index = pd.DatetimeIndex(pair.index)
    if not pair.index.is_monotonic_increasing or pair.index.has_duplicates:
        raise ValueError("NAV dates must be strictly chronological")
    calendar_years = (pair.index[-1] - pair.index[0]).days / 365.25
    years = (len(pair) - 1) / 252
    if calendar_years <= 0:
        raise ValueError("NAV window has no elapsed calendar time")
    growth = pair.iloc[-1] / pair.iloc[0]
    cg = growth ** (1 / years) - 1
    mdd = (pair / pair.cummax() - 1).min()
    arithmetic = float((pair.pct_change().iloc[1:, 0] - pair.pct_change().iloc[1:, 1]).mean() * 252)
    gap = float(cg.iloc[0] - cg.iloc[1])
    return {"n": len(pair), "start": pair.index[0].date().isoformat(),
            "end": pair.index[-1].date().isoformat(), "years": years,
            "calendarYears": calendar_years, "annualization": "252_SESSIONS_FROZEN_ENGINE",
            "cagr": float(cg.iloc[0]), "etfCagr": float(cg.iloc[1]), "cagrGap": gap, "excess": gap,
            "mdd": float(mdd.iloc[0]), "etfMdd": float(mdd.iloc[1]),
            "annualArithmeticDailyGap": arithmetic, "compoundingRemainder": gap - arithmetic}
