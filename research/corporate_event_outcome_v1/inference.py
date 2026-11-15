"""Registered inference: synchronized moving-block bootstrap, Bartlett HAC, Holm.

All functions take an already-computed daily difference series; nothing here
reads a market. ``synchronized_bootstrap`` draws ONE set of block starts and
applies it to every column, so A1, B1, cost variants and the A2 contrast keep
their same-day dependence.
"""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

from . import contract as C


def block_indices(T: int, block: int, draws: int, seed: int) -> np.ndarray:
    """(draws, T) resample index; consecutive blocks of length ``block`` cut to length T."""
    rng = np.random.default_rng(seed)
    block = max(1, min(block, T))
    per = math.ceil(T / block)
    starts = rng.integers(0, T - block + 1, size=(draws, per))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(draws, per * block)
    return idx[:, :T]


def synchronized_bootstrap(columns: dict[str, np.ndarray], block: int, *, draws: int = None,
                           seed: int = None) -> dict[str, np.ndarray]:
    draws = draws or C.BOOTSTRAP['draws']
    seed = C.BOOTSTRAP['seed'] if seed is None else seed
    lengths = {len(v) for v in columns.values()}
    if len(lengths) != 1:
        raise ValueError('UNSYNCHRONIZED_CALENDAR')
    T = lengths.pop()
    idx = block_indices(T, block, draws, seed)
    return {k: np.asarray(v, dtype=float)[idx].mean(axis=1) for k, v in columns.items()}


def basic_interval(mean: float, boot: np.ndarray, level: float) -> tuple[float, float]:
    a = (1 - level) / 2
    lo_q, hi_q = np.quantile(boot, [a, 1 - a])
    return 2 * mean - hi_q, 2 * mean - lo_q


def bootstrap_p(mean: float, boot: np.ndarray) -> float:
    centred = boot - mean
    return float((1 + np.sum(np.abs(centred) >= abs(mean))) / (len(boot) + 1))


def hac_se(x: np.ndarray, lag: int) -> float | None:
    x = np.asarray(x, dtype=float)
    T = len(x)
    if T < 2:
        return None
    u = x - x.mean()
    lag = min(lag, T - 1)
    v = float(u @ u) / T
    for j in range(1, lag + 1):
        v += 2 * (1 - j / (lag + 1)) * float(u[j:] @ u[:-j]) / T
    return math.sqrt(v / T) if v > 0 else None


def holm(pvalues: dict[str, float], alpha: float = C.FWER) -> dict[str, bool]:
    order = sorted(pvalues, key=lambda k: (pvalues[k], k))
    m, out, stop = len(order), {}, False
    for i, k in enumerate(order):
        if stop or pvalues[k] > alpha / (m - i):
            stop = True
            out[k] = False
        else:
            out[k] = True
    return out


def summarize(D: np.ndarray, horizon: str, boot: dict[str, np.ndarray]) -> dict:
    """delta_H = H * mean(D) with every registered interval; ``boot`` maps block length -> draws."""
    H = C.HORIZONS[horizon]
    D = np.asarray(D, dtype=float)
    m = float(D.mean())
    primary = boot[C.BOOTSTRAP['block'][horizon]]
    lo95, hi95 = basic_interval(m, primary, 0.95)
    lo_s, hi_s = basic_interval(m, primary, C.SIMULTANEOUS_LEVEL)
    se = hac_se(D, C.HAC_LAG[horizon])
    z = NormalDist().inv_cdf(1 - (1 - C.SIMULTANEOUS_LEVEL) / 2)
    sens = {}
    for b in C.BOOTSTRAP['sensitivityBlocks'][horizon]:
        lo, hi = basic_interval(m, boot[b], C.SIMULTANEOUS_LEVEL)
        sens[str(b)] = [H * lo, H * hi]
    return {
        'sessions': int(len(D)), 'meanDaily': m, 'delta': H * m,
        'ci95': [H * lo95, H * hi95], 'ciSimultaneous': [H * lo_s, H * hi_s],
        'simultaneousLevel': C.SIMULTANEOUS_LEVEL,
        'pBootstrapTwoSided': bootstrap_p(m, primary),
        'hac': ({'se': H * se, 'ciSimultaneous': [H * (m - z * se), H * (m + z * se)]}
                if se else None),
        'blockSensitivity': sens,
        'effectiveBlocks': len(D) / C.BOOTSTRAP['block'][horizon],
    }


def dependence_uncertain(summary: dict) -> bool:
    signs = [summary['ciSimultaneous'][0] > 0]
    if summary['hac']:
        signs.append(summary['hac']['ciSimultaneous'][0] > 0)
    signs += [v[0] > 0 for v in summary['blockSensitivity'].values()]
    return len(set(signs)) > 1
