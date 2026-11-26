"""MCT-v1 estimators. Pure numpy; no I/O and no data. Every forecast is walk-forward on matured outcomes only."""
from __future__ import annotations

import math

import numpy as np

# ------------------------------------------------------------------ forecasting models for P(loss)


def shrunk_cell_prob(cell_hits: float, cell_n: float, base: float, strength: float) -> float:
    """Beta-shrinkage of a cell frequency toward the base rate with `strength` pseudo-observations."""
    return (cell_hits + strength * base) / (cell_n + strength)


def logistic_fit(X: np.ndarray, y: np.ndarray, l2: float, iters: int = 50) -> np.ndarray:
    """Newton-Raphson logistic regression with an L2 penalty on the slopes (not the intercept)."""
    Xi = np.column_stack([np.ones(len(X)), X])
    beta = np.zeros(Xi.shape[1])
    penalty = np.diag([0.0] + [l2] * X.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-Xi @ beta))
        grad = Xi.T @ (y - p) - penalty @ beta
        hess = Xi.T @ (Xi * (p * (1 - p))[:, None]) + penalty
        step = np.linalg.solve(hess, grad)
        beta += step
        if np.max(np.abs(step)) < 1e-10:
            break
    return beta


def logistic_predict(beta: np.ndarray, x: np.ndarray) -> float:
    return float(1.0 / (1.0 + math.exp(-(beta[0] + float(beta[1:] @ x)))))


def walk_forward(features: list[dict], loss: list[bool | None], horizon: int, eval_mask: list[bool],
                 model: dict, strength: float, l2: float) -> list[float | None]:
    """P(loss) at each evaluation month, fitted on rows s with s + horizon <= t (outcome matured by t) only.

    model = {"kind": "BASE" | "CELLS" | "LOGIT", "inputs": [...]}. A row whose inputs are missing gets the base-rate
    forecast (the registered fallback), and missing-input training rows are excluded from that model's fit.
    """
    out: list[float | None] = []
    for t in range(len(features)):
        if not eval_mask[t]:
            out.append(None)
            continue
        train = [s for s in range(0, t - horizon + 1) if loss[s] is not None]
        if not train:
            out.append(None)
            continue
        ys = np.array([float(loss[s]) for s in train])
        base = float(ys.mean())
        inputs = model.get("inputs", [])
        x_now = [features[t].get(k) for k in inputs]
        if model["kind"] == "BASE" or any(v is None for v in x_now):
            out.append(base)
            continue
        usable = [s for s in train if all(features[s].get(k) is not None for k in inputs)]
        if model["kind"] == "CELLS":
            key = tuple(bool(v) for v in x_now)
            members = [s for s in usable if tuple(bool(features[s][k]) for k in inputs) == key]
            hits = sum(float(loss[s]) for s in members)
            out.append(shrunk_cell_prob(hits, len(members), base, strength))
        elif model["kind"] == "LOGIT":
            X = np.array([[float(features[s][k]) for k in inputs] for s in usable])
            y = np.array([float(loss[s]) for s in usable])
            if len(set(y)) < 2:
                out.append(base)
                continue
            beta = logistic_fit(X, y, l2)
            out.append(logistic_predict(beta, np.array([float(v) for v in x_now])))
        else:
            raise ValueError("UNKNOWN_MODEL_KIND")
    return out


def brier(p: list[float], y: list[float]) -> np.ndarray:
    return (np.asarray(p) - np.asarray(y)) ** 2


def log_loss(p: list[float], y: list[float]) -> float:
    p = np.clip(np.asarray(p), 1e-6, 1 - 1e-6)
    y = np.asarray(y)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def auc(p: list[float], y: list[float]) -> float | None:
    p, y = np.asarray(p), np.asarray(y).astype(bool)
    pos, neg = p[y], p[~y]
    if not pos.size or not neg.size:
        return None
    greater = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(greater / (pos.size * neg.size))


# ------------------------------------------------------------------ inference


def normal_p(t: float) -> float:
    return math.erfc(abs(t) / math.sqrt(2.0))


def nw_mean(series: np.ndarray, lag: int) -> dict:
    z = np.asarray(series, dtype=float)
    n = z.size
    mu = float(z.mean())
    c = z - mu
    lr = float(c @ c) / n
    for k in range(1, min(lag, n - 1) + 1):
        lr += 2.0 * (1.0 - k / (lag + 1.0)) * float(c[k:] @ c[:-k]) / n
    se = math.sqrt(max(lr, 0.0) / n)
    return {"mean": mu, "se": se, "t": mu / se if se > 0 else None, "p": normal_p(mu / se) if se > 0 else None,
            "n": n, "lag": lag}


def ols_hac(y: np.ndarray, X: np.ndarray, lag: int, names: list[str]) -> dict:
    """OLS with intercept and a Bartlett Newey-West covariance; returns coefficients, SEs and the covariance."""
    Xi = np.column_stack([np.ones(len(X)), X])
    xtx_inv = np.linalg.inv(Xi.T @ Xi)
    beta = xtx_inv @ Xi.T @ y
    u = y - Xi @ beta
    g = Xi * u[:, None]
    s = g.T @ g
    for k in range(1, min(lag, len(y) - 1) + 1):
        w = 1.0 - k / (lag + 1.0)
        gamma = g[k:].T @ g[:-k]
        s += w * (gamma + gamma.T)
    cov = xtx_inv @ s @ xtx_inv
    se = np.sqrt(np.diag(cov))
    coef = {n: {"b": float(b), "se": float(e), "p": normal_p(b / e) if e > 0 else None}
            for n, b, e in zip(["const"] + names, beta, se)}
    r2 = 1.0 - float(u @ u) / float(((y - y.mean()) ** 2).sum())
    return {"coef": coef, "n": int(len(y)), "lag": lag, "r2": r2, "_beta": beta, "_cov": cov}


def linear_contrast(fit: dict, names: list[str], weights: dict[str, float]) -> dict:
    full = ["const"] + names
    w = np.array([weights.get(n, 0.0) for n in full])
    est = float(w @ fit["_beta"])
    se = math.sqrt(float(w @ fit["_cov"] @ w))
    return {"estimate": est, "se": se, "p": normal_p(est / se) if se > 0 else None}


def holm(pvalues: dict[str, float | None]) -> dict[str, float | None]:
    present = sorted(((k, v) for k, v in pvalues.items() if v is not None), key=lambda kv: kv[1])
    m, running, out = len(present), 0.0, {k: None for k in pvalues}
    for i, (k, p) in enumerate(present):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


# ------------------------------------------------------------------ allocation


def exposure_from_probability(p: float | None, base: float | None, previous: float) -> float:
    """Registered three-level map: p < base -> 1.0; base <= p < 2*base -> 0.8; p >= 2*base -> 0.6; missing -> hold."""
    if p is None or base is None:
        return previous
    if p < base:
        return 1.0
    if p < 2.0 * base:
        return 0.8
    return 0.6


def equal_vol_weight(r_e: np.ndarray, r_f: np.ndarray, target: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if (mid * r_e + (1 - mid) * r_f).std(ddof=1) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def path_stats(r: np.ndarray, rf: np.ndarray) -> dict:
    nav = np.cumprod(1 + r)
    peak = np.maximum.accumulate(np.concatenate([[1.0], nav]))
    dd = np.concatenate([[1.0], nav]) / peak - 1
    years = len(r) / 12
    ex = r - rf
    roll12 = nav[11:] / np.concatenate([[1.0], nav[:-12]]) - 1
    tail = np.sort(r)[: max(1, int(0.05 * len(r)))]
    return {"cagr": float(nav[-1] ** (1 / years) - 1), "maxDrawdownMonthly": float(dd.min()),
            "annualVolatility": float(r.std(ddof=1) * math.sqrt(12)),
            "sharpe": float(ex.mean() / ex.std(ddof=1) * math.sqrt(12)), "worst12Months": float(roll12.min()),
            "cvar5Monthly": float(tail.mean())}
