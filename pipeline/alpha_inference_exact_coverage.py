"""Exact Gaussian coverage of self-normalized mean intervals (DEVELOPMENT_ONLY).

This module is a diagnostic instrument for the synthetic inference calibration
programme, not part of any frozen calibration contract.  It reads no files.

For a zero-mean Gaussian vector ``y ~ N(0, Sigma)`` and a symmetric matrix ``A``
the event ``y' A y <= 0`` has probability given exactly by Imhof (1961).  The
v3 self-normalized interval and the v4 calendar-time interval both cover the
null value exactly when such a quadratic form is non-positive, so their
coverage under a Gaussian synthetic null can be computed without Monte Carlo
error.  That separates a method's own finite-sample distortion from the noise
of a 300-replicate simulation, which is what the v3 diagnosis needed.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.integrate import quad


def imhof_probability_nonpositive(eigenvalues: np.ndarray) -> float:
    """P(sum_j lambda_j Z_j^2 <= 0) for iid standard normal Z (Imhof 1961)."""
    lam = np.asarray(eigenvalues, dtype=float)
    if lam.size == 0 or not np.isfinite(lam).all():
        raise ValueError("eigenvalues must be a non-empty finite vector")
    scale = float(np.max(np.abs(lam)))
    if scale == 0.0:
        raise ValueError("quadratic form is identically zero")
    lam = lam / scale
    lam = lam[np.abs(lam) > 1e-13]

    def integrand(u: float) -> float:
        theta = 0.5 * float(np.sum(np.arctan(lam * u)))
        log_rho = 0.25 * float(np.sum(np.log1p((lam * u) ** 2)))
        if log_rho > 700.0:
            return 0.0
        return math.sin(theta) / (u * math.exp(log_rho))

    edges = np.concatenate([[0.0], np.logspace(-3, 6, 400)])
    total = 0.0
    for lower, upper in zip(edges[:-1], edges[1:]):
        value, _ = quad(integrand, float(lower), float(upper), limit=200)
        total += value
    probability_positive = 0.5 + total / math.pi
    return float(min(1.0, max(0.0, 1.0 - probability_positive)))


def gaussian_coverage(covariance: np.ndarray, form: np.ndarray) -> float:
    """P(y' A y <= 0) for y ~ N(0, covariance)."""
    sigma = np.asarray(covariance, dtype=float)
    jitter = 1e-12 * float(np.trace(sigma)) / len(sigma)
    root = np.linalg.cholesky(sigma + jitter * np.eye(len(sigma)))
    inner = root.T @ np.asarray(form, dtype=float) @ root
    return imhof_probability_nonpositive(np.linalg.eigvalsh(0.5 * (inner + inner.T)))


def daily_autocovariance(lags: np.ndarray, dgp: dict[str, Any], names_in_mean: int) -> np.ndarray:
    """Autocovariance of the equal-weight mean of `names_in_mean` synthetic daily returns.

    Shared and idiosyncratic components are stationary AR(1) with stationary
    standard deviations ``sigmaShared``/``sigmaIdiosyncratic``; idiosyncratic
    names are independent, so their mean has variance divided by the count.
    """
    m = np.abs(np.asarray(lags))
    shared = float(dgp["sigmaShared"]) ** 2 * float(dgp["phiShared"]) ** m
    idio = float(dgp["sigmaIdiosyncratic"]) ** 2 / names_in_mean * float(dgp["phiIdiosyncratic"]) ** m
    return shared + idio


def signal_date_covariance(dgp: dict[str, Any], horizon: int, weeks: int, step: int, names: int) -> np.ndarray:
    """Covariance of the weekly overlapping forward-sum universe mean (``dateMean``)."""
    j = np.arange(-(horizon - 1), horizon)
    weights = horizon - np.abs(j)
    lags = np.arange(weeks)
    gamma = np.array([np.sum(weights * daily_autocovariance(step * k + j, dgp, names)) for k in lags])
    return gamma[np.abs(lags[:, None] - lags[None, :])]


def calendar_map(weeks: int, horizon: int, step: int) -> tuple[np.ndarray, np.ndarray]:
    """Session-to-calendar-week attribution matrix and exposure profile for all-defined cohorts."""
    sessions = (weeks - 1) * step + horizon
    s = np.arange(sessions)
    first = np.maximum(0, -(-(s - horizon + 1) // step))
    last = np.minimum(weeks - 1, s // step)
    active = np.maximum(0, last - first + 1).astype(float)
    calendar_weeks = -(-sessions // step)
    mapping = np.zeros((calendar_weeks, sessions))
    mapping[s // step, s] = active
    exposure = mapping.sum(axis=1) / horizon
    return mapping, exposure


def self_normalized_form(exposure: np.ndarray, critical_value: float) -> np.ndarray:
    """Quadratic form whose non-positivity is coverage of 0 by the exposure-profile SN interval.

    With ``exposure`` identically one this is exactly v3's interval.
    """
    x = np.asarray(exposure, dtype=float)
    count = len(x)
    one = np.ones(count)
    residual = np.eye(count) - np.outer(x, one) / x.sum()
    partial = np.tril(np.ones((count, count))) @ residual
    return count * np.outer(one, one) - critical_value * partial.T @ partial


def circular_block_normal_form(weeks: int, block: int, z: float) -> np.ndarray:
    """Normal-quantile approximation of a circular block bootstrap mean interval.

    Valid only when ``weeks`` is a multiple of ``block``; the bootstrap variance of
    the mean is then exactly ``(k / n^2) * mean_s (T_s - b*ybar)^2`` over the n
    circular block sums T_s, a quadratic form in y.  Coverage of 0 by
    ``ybar +/- z sqrt(V*)`` is non-positivity of ``ybar^2 - z^2 V*``.
    """
    if weeks % block:
        raise ValueError("weeks must be a multiple of block")
    k = weeks // block
    rows = np.zeros((weeks, weeks))
    for start in range(weeks):
        rows[start, (start + np.arange(block)) % weeks] = 1.0
    centred = rows - block * np.full((weeks, weeks), 1.0 / weeks)
    variance_form = (k / weeks**2) * (centred.T @ centred) / weeks
    mean_form = np.full((weeks, weeks), 1.0 / weeks**2)
    return mean_form - z * z * variance_form
