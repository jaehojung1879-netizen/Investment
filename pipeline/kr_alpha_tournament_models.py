"""KR alpha discovery tournament v1 — the five fitted model families, the common calibration and the uncertainty contraction.

Pure numerical functions on arrays: no I/O, no dates beyond what the caller hands in, no outcome beyond the training labels the caller already
restricted to its fold. Every estimator is deterministic (fixed seeds, one thread, fixed iteration counts, sorted inputs).
"""
from __future__ import annotations

import hashlib
import math

import numpy as np
from scipy.stats import rankdata
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import ElasticNet, LogisticRegression
from threadpoolctl import threadpool_limits

from . import kr_alpha_tournament as T
from . import kr_industry_anatomy as I


# --------------------------------------------------------------------------- #
# Sample weights
# --------------------------------------------------------------------------- #
def recency_weights(dates, cutoff, scheme):
    """Date-balanced weights (each signal date carries equal total weight) times 0.5 ** (age in years / half-life). Normalised to mean 1.
    Age is measured from the fold's own information cutoff, so a weight never depends on anything after it."""
    dates = np.asarray(dates)
    half_life = T.RECENCY_SCHEMES[scheme]
    uniq, inverse, counts = np.unique(dates, return_inverse=True, return_counts=True)
    w = 1.0 / counts[inverse]
    if half_life is not None:
        cut = np.datetime64(cutoff)
        age = (cut - uniq.astype("datetime64[D]")).astype(float) / 365.25
        if (age < 0).any():
            raise ValueError("RECENCY_WEIGHT_FROM_A_DATE_AFTER_THE_CUTOFF")
        w = w * 0.5 ** (age[inverse] / half_life)
    return w / w.mean()


# --------------------------------------------------------------------------- #
# Standardisation fitted on training rows only
# --------------------------------------------------------------------------- #
class Scaler:
    def __init__(self, X, w):
        w = w / w.sum()
        self.mean = w @ X
        var = w @ (X - self.mean) ** 2
        self.scale = np.where(var > 1e-24, np.sqrt(var), 1.0)

    def __call__(self, X):
        return (X - self.mean) / self.scale


# --------------------------------------------------------------------------- #
# Families
# --------------------------------------------------------------------------- #
class Fitted:
    """A fitted candidate: `predict(X)` returns a native score (higher = more attractive)."""

    def __init__(self, family, predict, coef=None):
        self.family, self._predict, self.coef = family, predict, coef

    def predict(self, X):
        out = np.asarray(self._predict(X), float)
        if not np.isfinite(out).all():
            raise ValueError("NON_FINITE_PREDICTION: " + self.family)
        return out


def fit_ridge(X, y, w, alpha_per_unit_weight):
    scaler = Scaler(X, w)
    Z = scaler(X)
    wn = w / w.sum()
    ybar = float(wn @ y)
    A_ = Z.T @ (Z * wn[:, None]) + alpha_per_unit_weight * np.eye(Z.shape[1])
    beta = np.linalg.solve(A_, Z.T @ (wn * (y - ybar)))
    return Fitted("SHRUNK_LINEAR", lambda Xn: ybar + scaler(Xn) @ beta, beta)


def fit_elastic_net(X, y, w, alpha):
    scaler = Scaler(X, w)
    wn = w / w.sum()
    ybar = float(wn @ y)
    ysd = math.sqrt(float(wn @ (y - ybar) ** 2)) or 1.0
    model = ElasticNet(alpha=alpha, l1_ratio=0.5, selection="cyclic", max_iter=5000, tol=1e-4, fit_intercept=True)
    model.fit(scaler(X), (y - ybar) / ysd, sample_weight=w)
    return Fitted("SPARSE_LINEAR", lambda Xn: ybar + ysd * model.predict(scaler(Xn)), model.coef_.copy())


def fit_tree(X, y, w, max_depth):
    model = HistGradientBoostingRegressor(learning_rate=0.05, max_iter=150, max_depth=max_depth, min_samples_leaf=200, l2_regularization=10.0,
                                          early_stopping=False, random_state=0)
    with threadpool_limits(limits=1):
        model.fit(X, y, sample_weight=w)

    def predict(Xn):
        with threadpool_limits(limits=1):
            return model.predict(Xn)
    return Fitted("SHALLOW_TREE", predict)


def fit_pls(X, y, w, n_components):
    """Weighted PLS1 (NIPALS). Deterministic; components beyond the data's rank stop early."""
    scaler = Scaler(X, w)
    Z = scaler(X)
    wn = w / w.sum()
    ybar = float(wn @ y)
    Xk, yk = Z.copy(), y - ybar
    Ws, Ps, Qs = [], [], []
    for _ in range(n_components):
        wk = Xk.T @ (wn * yk)
        norm = float(np.linalg.norm(wk))
        if norm < 1e-14:
            break
        wk /= norm
        t = Xk @ wk
        tt = float(wn @ (t * t))
        if tt < 1e-18:
            break
        p = Xk.T @ (wn * t) / tt
        q = float(wn @ (yk * t)) / tt
        Xk = Xk - np.outer(t, p)
        yk = yk - q * t
        Ws.append(wk)
        Ps.append(p)
        Qs.append(q)
    if not Ws:
        beta = np.zeros(Z.shape[1])
    else:
        W_, P_ = np.column_stack(Ws), np.column_stack(Ps)
        beta = W_ @ np.linalg.solve(P_.T @ W_, np.asarray(Qs))
    return Fitted("LATENT_FACTOR", lambda Xn: ybar + scaler(Xn) @ beta, beta)


def _date_seed(date, salt):
    return int.from_bytes(hashlib.sha256((str(date) + "|" + salt).encode()).digest()[:8], "big")


def ranking_pairs(X, y, dates, w, pairs_per_date, salt="pairs"):
    """Within-date pairs (one name from the top half of the target, one from the bottom half, never equal targets), both orientations; the pair
    draw is seeded by the date only, so it does not depend on row order or on any other date. Pair weight = the date's weight / (2 x pairs)."""
    diffs, labels, weights = [], [], []
    order = np.lexsort((np.arange(len(y)), dates))
    dates_sorted = dates[order]
    bounds = np.flatnonzero(np.r_[True, dates_sorted[1:] != dates_sorted[:-1], True])
    for a, b in zip(bounds[:-1], bounds[1:]):
        idx = order[a:b]
        idx = idx[np.isfinite(y[idx])]
        if len(idx) < 4:
            continue
        ranked = idx[np.lexsort((idx, y[idx]))]
        half = len(ranked) // 2
        low, high = ranked[:half], ranked[len(ranked) - half:]
        rng = np.random.default_rng(_date_seed(dates_sorted[a], salt))
        hi = high[rng.integers(0, len(high), pairs_per_date)]
        lo = low[rng.integers(0, len(low), pairs_per_date)]
        keep = y[hi] > y[lo]
        hi, lo = hi[keep], lo[keep]
        if not len(hi):
            continue
        d = X[hi] - X[lo]
        dw = float(np.mean(w[idx])) / (2 * len(hi))
        diffs += [d, -d]
        labels += [np.ones(len(hi)), np.zeros(len(hi))]
        weights += [np.full(len(hi), dw), np.full(len(hi), dw)]
    if not diffs:
        return None
    return np.vstack(diffs), np.concatenate(labels), np.concatenate(weights)


def fit_ranker(X, y, w, dates, C, pairs_per_date):
    scaler = Scaler(X, w)
    pairs = ranking_pairs(scaler(X), y, np.asarray(dates), w, pairs_per_date)
    if pairs is None:
        raise ValueError("NO_RANKING_PAIRS")
    D, L, W = pairs
    model = LogisticRegression(C=C, fit_intercept=False, solver="lbfgs", max_iter=1000)
    model.fit(D, L, sample_weight=W / W.mean())
    beta = model.coef_.ravel().copy()
    return Fitted("LEARNING_TO_RANK", lambda Xn: scaler(Xn) @ beta, beta)


def fit_candidate(candidate, X, y, w, dates):
    """Dispatch one registered configuration. X is the family's own design (linear or tree); y the candidate's target."""
    family, params = candidate["family"], candidate["params"]
    ok = np.isfinite(y)
    X, y, w, dates = X[ok], y[ok], w[ok], np.asarray(dates)[ok]
    if len(y) < 50:
        raise ValueError("TOO_FEW_TRAINING_ROWS")
    if family == "SHRUNK_LINEAR":
        return fit_ridge(X, y, w, params["alphaPerUnitWeight"])
    if family == "SPARSE_LINEAR":
        return fit_elastic_net(X, y, w, params["alpha"])
    if family == "SHALLOW_TREE":
        return fit_tree(X, y, w, params["max_depth"])
    if family == "LATENT_FACTOR":
        return fit_pls(X, y, w, params["n_components"])
    if family == "LEARNING_TO_RANK":
        return fit_ranker(X, y, w, dates, params["C"], T.MODEL_FAMILIES["LEARNING_TO_RANK"]["pairsPerDate"])
    raise ValueError("UNKNOWN_FAMILY: " + family)


# --------------------------------------------------------------------------- #
# Common calibration: native score -> expected incremental return over 069500.KS
# --------------------------------------------------------------------------- #
def within_date_rank(dates, values):
    """Average-rank percentile in (0, 1) within each date; does not depend on row order."""
    dates = np.asarray(dates)
    values = np.asarray(values, float)
    out = np.full(len(values), np.nan)
    for d in np.unique(dates):
        idx = np.flatnonzero(dates == d)
        ok = idx[np.isfinite(values[idx])]
        if len(ok):
            out[ok] = (rankdata(values[ok], method="average") - 0.5) / len(ok)
    return out


def calibrate(dates, s, y_econ, *, min_names=T.MIN_NAMES_PER_CALIBRATION_DATE, lag=T.CALIBRATION_HAC_LAG):
    """Fit the frozen calibration on OUT-OF-FOLD (date, rank s, economic label) triples. Returns the mapping parameters."""
    dates, s, y = np.asarray(dates), np.asarray(s, float), np.asarray(y_econ, float)
    slopes, intercepts = [], []
    for d in np.unique(dates):
        idx = np.flatnonzero((dates == d) & np.isfinite(s) & np.isfinite(y))
        if len(idx) < min_names:
            continue
        x = s[idx] - 0.5
        vx = float(np.mean((x - x.mean()) ** 2))
        if vx <= 0:
            continue
        b = float(np.mean((x - x.mean()) * (y[idx] - y[idx].mean())) / vx)
        slopes.append(b)
        intercepts.append(float(y[idx].mean() - b * x.mean()))
    if len(slopes) < 3:
        return {"status": "INSUFFICIENT_CALIBRATION_DATES", "dates": len(slopes), "b": None, "se": None, "bStar": 0.0, "carry": 0.0,
                "credited": 0.0, "slopeSe": 0.0}
    hac = I.newey_west_mean(slopes, lag)
    b, se = hac["mean"], hac["se"]
    b_star = b * max(0.0, 1.0 - se ** 2 / b ** 2) if b > 0 and se is not None else 0.0
    carry = float(np.mean(intercepts))
    return {"status": "CALIBRATED", "dates": len(slopes), "b": b, "se": se, "bStar": b_star, "carry": carry, "credited": min(0.0, carry),
            "slopeSe": se if se is not None else 0.0}


def apply_calibration(cal, s):
    s = np.asarray(s, float)
    mu = cal["credited"] + cal["bStar"] * (s - 0.5)
    sd = cal["slopeSe"] * np.abs(s - 0.5)
    return mu, sd


def contract(member_mu, member_sd):
    """Ensemble mean, disagreement + calibration uncertainty, and the signal-to-noise contraction. member_* are (members x names) arrays.
    Asserts |mu_post| <= |mu| with the sign preserved on every row (a contraction, never a factor)."""
    mu_k = np.atleast_2d(np.asarray(member_mu, float))
    sd_k = np.atleast_2d(np.asarray(member_sd, float))
    mu = mu_k.mean(axis=0)
    disagreement = mu_k.var(axis=0) if mu_k.shape[0] > 1 else np.zeros(mu_k.shape[1])
    calibration = (sd_k ** 2).mean(axis=0)
    sigma2 = disagreement + calibration
    denom = mu ** 2 + sigma2
    kappa = np.where(denom > 0, mu ** 2 / np.where(denom > 0, denom, 1.0), 0.0)
    post = kappa * mu
    if not (np.all(np.abs(post) <= np.abs(mu) + 1e-15) and np.all(post * mu >= -1e-30)):
        raise ValueError("CONTRACTION_VIOLATED")
    return {"mu": mu, "disagreement": disagreement, "calibrationVar": calibration, "sigma2": sigma2, "kappa": kappa, "muPost": post}


# --------------------------------------------------------------------------- #
# Prediction diagnostics used inside the inner loop (also reused by the outer evaluation)
# --------------------------------------------------------------------------- #
def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return np.nan
    ra, rb = rankdata(a[ok]), rankdata(b[ok])
    if ra.std() == 0 or rb.std() == 0:
        return np.nan
    return float(np.corrcoef(ra, rb)[0, 1])


def per_date_ic(dates, score, outcome, min_names=T.SELECTION["minNamesPerIcDate"]):
    dates = np.asarray(dates)
    out = {}
    for d in np.unique(dates):
        idx = np.flatnonzero(dates == d)
        if len(idx) >= min_names:
            value = spearman(np.asarray(score)[idx], np.asarray(outcome)[idx])
            if np.isfinite(value):
                out[str(d)] = value
    return out
