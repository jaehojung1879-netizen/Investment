"""Leakage-safe incremental-prediction evaluator for industry-alpha-kr-next-v1. Pure numpy/pandas, no I/O.

The question every contrast asks is the same: on the SAME rows, does the alternative model's out-of-fold forecast of the
date-centred target have a smaller squared error than the base model's? Centring the target within each signal date
removes the market's common move, so a model cannot score by predicting the market; what remains is the ordering and
spread of industries against each other.

* FOLDS ARE CHRONOLOGICAL AND PURGED. A training row is admitted only if its whole label window ends at least
  EMBARGO_SESSIONS before the first test signal; the test year's own rows are never seen. Decided by the calendar, never
  by whether an outcome exists.
* PREPROCESSING IS TRAIN-ONLY. Medians, missing indicators, means and scales come from the training rows of that fold.
* PAIRED ON ONE POPULATION. Base and alternative are fitted and scored on exactly the same rows; a row the target cannot
  resolve is out for BOTH and is counted, never silently dropped from one side.
* INFERENCE IS A NULL-CENTRED MOVING-BLOCK BOOTSTRAP of the per-date loss differential, one-sided, +1 corrected; below
  the registered support it is INSUFFICIENT_SUPPORT with p = 1, never a precise-looking interval.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import study as S


# --------------------------------------------------------------------------- #
# Calendar folds
# --------------------------------------------------------------------------- #
def label_exit_position(sessions, date, horizon):
    """Index of the exit session: entry = next session after the signal, exit = entry + horizon (sealed endpoint rule)."""
    days = pd.DatetimeIndex(sessions)
    return int(days.searchsorted(pd.Timestamp(date), side="right")) + horizon


def signal_position(sessions, date):
    return int(pd.DatetimeIndex(sessions).searchsorted(pd.Timestamp(date), side="right")) - 1


def folds(dates, sessions, horizon, *, embargo=S.EMBARGO_SESSIONS, min_training_signals=12 * S.MIN_TRAINING_YEARS):
    """[(test_year, train_dates, test_dates)] from signal dates alone. A year is a test year once at least
    `min_training_signals` earlier signals have labels that end `embargo` sessions before its first test signal."""
    dates = sorted(set(dates))
    out = []
    for year in sorted({d[:4] for d in dates}):
        test = [d for d in dates if d[:4] == year]
        start = signal_position(sessions, test[0])
        train = [d for d in dates if d < test[0] and label_exit_position(sessions, d, horizon) < start - embargo]
        if len(train) >= min_training_signals:
            out.append((year, train, test))
    return out


# --------------------------------------------------------------------------- #
# Train-only design and ridge
# --------------------------------------------------------------------------- #
def design(train, test, columns):
    """Median-impute, add missing indicators for columns missing anywhere in TRAIN, standardise on TRAIN."""
    Xtr = train.reindex(columns=list(columns)).apply(pd.to_numeric, errors="coerce").to_numpy(float)
    Xte = test.reindex(columns=list(columns)).apply(pd.to_numeric, errors="coerce").to_numpy(float)
    med = np.array([np.nanmedian(c) if np.isfinite(c).any() else 0.0 for c in Xtr.T])
    flag = np.array([~np.isfinite(c).all() for c in Xtr.T], bool)
    def fill(X):
        miss = ~np.isfinite(X)
        Y = np.where(miss, med, X)
        return np.hstack([Y, miss[:, flag].astype(float)])
    A, B = fill(Xtr), fill(Xte)
    mu, sd = A.mean(axis=0), A.std(axis=0)
    sd[sd == 0] = 1.0
    return (A - mu) / sd, (B - mu) / sd


def date_weights(dates):
    """Each date carries total weight 1, split equally across its rows."""
    s = pd.Series(1.0, index=range(len(dates)))
    counts = pd.Series(list(dates)).map(pd.Series(list(dates)).value_counts())
    return (s / counts.to_numpy()).to_numpy(float)


def ridge_fit(X, y, w, lam=S.RIDGE_LAMBDA):
    """Weighted ridge with an unpenalised intercept."""
    w = np.asarray(w, float)
    wsum = w.sum()
    xm = (w[:, None] * X).sum(axis=0) / wsum
    ym = float((w * y).sum() / wsum)
    Xc, yc = X - xm, y - ym
    beta = np.linalg.solve(Xc.T @ (w[:, None] * Xc) + lam * np.eye(X.shape[1]), Xc.T @ (w * yc))
    return beta, ym - float(xm @ beta)


def centred(frame, target):
    y = pd.to_numeric(frame[target], errors="coerce")
    return y - y.groupby(frame["date"]).transform("mean")


def oof_predictions(frame, columns, target, sessions, horizon):
    """Out-of-fold forecasts of the date-centred target for rows of test years; NaN elsewhere.

    `frame` must already be the admitted paired population (finite target). Returns (Series, fold list)."""
    frame = frame.reset_index(drop=True)
    y = centred(frame, target).to_numpy(float)
    pred = np.full(len(frame), np.nan)
    info = []
    for year, train_dates, test_dates in folds(frame["date"], sessions, horizon):
        tr = frame["date"].isin(train_dates).to_numpy()
        te = frame["date"].isin(test_dates).to_numpy()
        if not te.any() or tr.sum() < 2:
            continue
        if not columns:
            pred[te] = 0.0
        else:
            Xtr, Xte = design(frame[tr], frame[te], columns)
            beta, b0 = ridge_fit(Xtr, y[tr], date_weights(frame.loc[tr, "date"]))
            pred[te] = Xte @ beta + b0
        info.append({"testYear": year, "trainDates": len(train_dates), "testDates": len(test_dates),
                     "trainRows": int(tr.sum()), "testRows": int(te.sum())})
    return pd.Series(pred, index=frame.index), info


# --------------------------------------------------------------------------- #
# Paired loss differential and inference
# --------------------------------------------------------------------------- #
def loss_differential(frame, target, pred_base, pred_alt):
    """Per-date mean of (base error^2 - alt error^2) on the centred target; positive means the alternative is better."""
    frame = frame.reset_index(drop=True)
    y = centred(frame, target)
    ok = pred_base.notna() & pred_alt.notna() & y.notna()
    d = ((y - pred_base) ** 2 - (y - pred_alt) ** 2)[ok]
    return d.groupby(frame.loc[ok, "date"]).mean().sort_index()


def moving_block_bootstrap_p(d, *, block=S.BOOTSTRAP["blockSignals"], draws=S.BOOTSTRAP["draws"], seed=S.BOOTSTRAP["seed"]):
    """One-sided p for mean(d) > 0 under the null-centred moving-block bootstrap; +1 in both terms."""
    x = np.asarray(d, float)
    n = len(x)
    if n == 0:
        return 1.0
    if not np.isfinite(x).all():
        raise ValueError("NONFINITE_BOOTSTRAP_DIFFERENTIAL")
    observed = x.mean()
    z = x - observed
    rng = np.random.default_rng(seed)
    b = min(block, n)
    starts_max = n - b + 1
    k = math.ceil(n / b)
    hits = 0
    for _ in range(draws):
        idx = np.concatenate([np.arange(s, s + b) for s in rng.integers(0, starts_max, size=k)])[:n]
        hits += z[idx].mean() >= observed
    return (1 + hits) / (draws + 1)


def support_blocks(test_dates):
    """Non-overlapping 252-session-equivalent blocks spanned by the monthly test signals."""
    return len(set(test_dates)) // S.BOOTSTRAP["blockSignals"]


def holm(pvalues, alpha=S.HOLM_ALPHA):
    """{slot: p} -> {slot: {'p','pHolm','reject'}}. Blocked or missing slots must be passed as p = 1."""
    # A NaN p-value must never be ranked ahead of valid hypotheses or become a discovery.
    clean = {}
    for key, raw in pvalues.items():
        try:
            p = float(raw)
        except (TypeError, ValueError, OverflowError):
            p = 1.0
        clean[key] = p if math.isfinite(p) and 0.0 <= p <= 1.0 else 1.0
    items = sorted(clean.items(), key=lambda kv: (kv[1], kv[0]))
    m, running, out, stop = len(items), 0.0, {}, False
    for i, (k, p) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)
        stop = stop or p > alpha / (m - i)
        out[k] = {"p": p, "pHolm": running, "reject": not stop}
    return out


def date_spearman(frame, target, pred):
    """Per-date rank correlation of forecast and centred target (descriptive diagnostic only)."""
    frame = frame.reset_index(drop=True).assign(_p=pred.to_numpy(), _y=centred(frame, target).to_numpy())
    vals = []
    for _, g in frame.dropna(subset=["_p", "_y"]).groupby("date"):
        if len(g) >= S.MIN_INDUSTRIES_PER_DATE and g["_p"].nunique() > 1:
            vals.append(g["_p"].rank().corr(g["_y"].rank()))
    return {"meanDateSpearman": float(np.mean(vals)) if vals else None, "dates": len(vals)}


# --------------------------------------------------------------------------- #
# One contrast
# --------------------------------------------------------------------------- #
def admit(frame, target, status_col):
    """Paired population: rows whose target resolved, on dates with at least MIN_INDUSTRIES_PER_DATE such rows.
    Returns (admitted frame, attrition report by reason). Rows are removed for BOTH models alike."""
    status = frame[status_col].fillna("UNKNOWN")
    target_values = pd.to_numeric(frame[target], errors="coerce").to_numpy(dtype=float)
    numeric_finite = pd.Series(np.isfinite(target_values), index=frame.index)
    finite = numeric_finite & status.eq("MATURED")
    reasons = status.mask(status.eq("MATURED") & ~numeric_finite, "MATURED_BUT_NONFINITE_TARGET")
    reasons = reasons[~finite].value_counts().to_dict()
    kept = frame[finite]
    per_date = kept.groupby("date").size()
    thin = per_date[per_date < S.MIN_INDUSTRIES_PER_DATE].index
    report = {"intendedRows": int(len(frame)), "unresolvedRowsByReason": {str(k): int(v) for k, v in sorted(reasons.items())},
              "thinDates": int(len(thin)), "rowsOnThinDates": int(kept["date"].isin(thin).sum())}
    kept = kept[~kept["date"].isin(thin)]
    report["admittedRows"], report["admittedDates"] = int(len(kept)), int(kept["date"].nunique())
    return kept.reset_index(drop=True), report


def contrast(frame, base_cols, alt_cols, target, status_col, sessions, horizon):
    pop, attrition = admit(frame, target, status_col)
    out = {"attrition": attrition, "baseColumns": list(base_cols), "altColumns": list(alt_cols)}
    if pop.empty:
        return out | {"status": "NO_ADMITTED_ROWS", "p": 1.0}
    pb, info = oof_predictions(pop, base_cols, target, sessions, horizon)
    pa, _ = oof_predictions(pop, alt_cols, target, sessions, horizon)
    d = loss_differential(pop, target, pb, pa)
    if not np.isfinite(d.to_numpy(dtype=float)).all():
        return out | {"status": "NONFINITE_LOSS_DIFFERENTIAL", "p": 1.0}
    blocks = support_blocks(d.index)
    out.update(folds=info, testDates=int(len(d)), supportBlocks=blocks,
               meanLossReduction=float(d.mean()) if len(d) else None,
               shareDatesImproved=float((d > 0).mean()) if len(d) else None,
               baseDiagnostic=date_spearman(pop, target, pb), altDiagnostic=date_spearman(pop, target, pa))
    if not len(d):
        return out | {"status": "NO_TEST_DATES", "p": 1.0}
    p = moving_block_bootstrap_p(d.to_numpy())
    if blocks < S.MIN_NONOVERLAPPING_H252_BLOCKS:
        # Below the registered support the family p is 1; the bootstrap p is published as DESCRIPTIVE only.
        return out | {"status": "INSUFFICIENT_SUPPORT", "p": 1.0, "descriptiveBootstrapP": p}
    return out | {"status": "EVALUATED", "p": p}


def h1_columns(block):
    full = [c for cols in S.BLOCKS.values() for c in cols] + list(S.NUISANCE)
    drop = set(S.BLOCKS[block])
    return [c for c in full if c not in drop], full


def run_kr_horizon(frame, sessions, horizon, *, sequential_gate):
    """All KR slots of one horizon. H1 first; H2 only when the gate allows. Returns {slotId: result}."""
    res = {}
    for block in S.BLOCKS:
        base, alt = h1_columns(block)
        res[f"KR_H{horizon}_{block}"] = contrast(frame, base, alt, "cwRelative", "cwStatus", sessions, horizon)
    return res | h2_slots(frame, sessions, horizon, gate_open=not sequential_gate, res=res)


def h2_slots(frame, sessions, horizon, *, gate_open, res):
    full = h1_columns("MOM")[1]
    out = {}
    if not gate_open:
        # Preregistration: an H1 non-concentration slot must pass the FULL 36-slot Holm (every other slot at p = 1).
        gate = family(res)
        gate_open = any(gate[k]["reject"] and res[k]["p"] < 1.0 for k in res if not k.endswith("CONCENTRATION"))
    if not gate_open:
        closed = {"status": "GATED_CLOSED_NO_H1_PASS", "p": 1.0}
        return {f"KR_H{horizon}_MARKET_CONTEXT": closed, f"KR_H{horizon}_LEADER_DIFFUSION": closed}
    out[f"KR_H{horizon}_MARKET_CONTEXT"] = contrast(frame, full, full + list(S.MARKET_CONTEXT), "cwRelative", "cwStatus",
                                                    sessions, horizon)
    base = list(S.DIFFUSION_BASE)
    out[f"KR_H{horizon}_LEADER_DIFFUSION"] = contrast(frame, base, base + list(S.DIFFUSION_SIGNAL), "laggardRelative",
                                                      "laggardStatus", sessions, horizon)
    return out


def family(results_by_slot):
    """Single 36-slot Holm family. Any registered slot without a result (US, H3, blocked) enters as p = 1."""
    pvals = {s["id"]: results_by_slot.get(s["id"], {}).get("p", 1.0) for s in S.slots()}
    return holm(pvals)


def mom_terciles(frame):
    """0/1/2 by within-date rank of REL_MOM_126 (signal-time, label-free); NaN where the date has < 3 finite values."""
    mom = pd.to_numeric(frame["REL_MOM_126"], errors="coerce")
    rank = mom.groupby(frame["date"]).rank(pct=True)
    count = mom.notna().groupby(frame["date"]).transform("sum")
    return np.floor(np.minimum(rank * 3, 2.999)).where(count >= 3)


def anticipation_split(frame, block, sessions, horizon):
    """Descriptive, not a slot: the block's per-row error reduction from the FULL-population fit, averaged inside
    prior-MOM terciles. Answers 'is the information only useful where the price has not already moved?'."""
    base, alt = h1_columns(block)
    pop, _ = admit(frame, "cwRelative", "cwStatus")
    if pop.empty:
        return {str(t): None for t in (0, 1, 2)}
    pb, _ = oof_predictions(pop, base, "cwRelative", sessions, horizon)
    pa, _ = oof_predictions(pop, alt, "cwRelative", sessions, horizon)
    y = centred(pop, "cwRelative")
    gain = (y - pb) ** 2 - (y - pa) ** 2
    terc = mom_terciles(pop)
    out = {}
    for t in (0, 1, 2):
        ok = terc.eq(t) & gain.notna()
        per_date = gain[ok].groupby(pop.loc[ok, "date"]).mean()
        out[str(t)] = {"testDates": int(len(per_date)), "meanLossReduction": float(per_date.mean()) if len(per_date) else None}
    return out
