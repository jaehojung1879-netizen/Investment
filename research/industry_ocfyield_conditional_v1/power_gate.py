"""Outcome-free power and feasibility gate for industry-ocfyield-conditional-v1.

Reads ONLY the input columns the frozen protocol names (never rel_*, status*, entry*/exit*, reason). Labels are
synthetic, drawn on the real 610-date x 14-industry grid so that overlapping H126/H252 windows share shocks exactly as
their calendar positions dictate. The real feature and control values decide which industry-dates exist, the per-date
cross-section size and the collinearity the partial statistic has to work through.

    python -m research.industry_ocfyield_conditional_v1.power_gate            # writes power-gate-result.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROTOCOL_PATH = HERE / "protocol.json"
RESULT_PATH = HERE / "power-gate-result.json"
FORBIDDEN_COLUMN_PREFIXES = ("rel_", "status", "entry", "exit", "reason")  # case-sensitive: outcome columns are lower-case
PRIMARY_ALPHA = 0.05 / 2  # protocol.inference.multiplicity: Holm over two horizon slots, first step one-sided


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_protocol(path=PROTOCOL_PATH):
    return json.loads(Path(path).read_text())


def load_inputs(protocol, path=None):
    cols = list(protocol["inputColumns"])
    for c in cols:
        if c.startswith(FORBIDDEN_COLUMN_PREFIXES):
            raise ValueError(f"OUTCOME_COLUMN_REQUESTED: {c}")
    frame = pd.read_csv(path or ROOT / protocol["panel"], usecols=cols)
    if set(frame.columns) != set(cols):
        raise ValueError("INPUT_COLUMNS_MISMATCH")
    return frame


# --------------------------------------------------------------------------- #
# Support: which industry-dates have every input, on the inherited minimum
# --------------------------------------------------------------------------- #
def support(frame, protocol):
    """Grid (dates x industries), the joint finite mask, and the dates meeting minCrossSection."""
    feature = protocol["feature"]
    controls = protocol["controls"]["available"]
    dates = sorted(frame["date"].unique())
    industries = sorted(frame["industry"].unique())
    if frame.duplicated(["date", "industry"]).any():
        raise ValueError("DUPLICATE_INDUSTRY_DATE")
    wide = {c: frame.pivot(index="date", columns="industry", values=c).reindex(index=dates, columns=industries)
            for c in [feature] + controls}
    finite = np.ones((len(dates), len(industries)), bool)
    for c in wide:
        finite &= np.isfinite(wide[c].to_numpy(float))
    counts = finite.sum(axis=1)
    usable = counts >= protocol["minCrossSection"]
    return {"dates": dates, "industries": industries, "wide": wide, "finite": finite, "counts": counts, "usable": usable}


def _ranks(x):
    return pd.Series(x).rank(method="average").to_numpy(float)


def residualiser(design):
    """M = I - X (X'X)^+ X' with X = [1, design]."""
    n = design.shape[0]
    x = np.column_stack([np.ones(n), design])
    return np.eye(n) - x @ np.linalg.pinv(x.T @ x) @ x.T


def date_designs(sup, protocol, synthetic_beta=None):
    """Per usable date: column positions, residualiser on control ranks, residualised feature rank, signal s."""
    feature = protocol["feature"]
    controls = protocol["controls"]["available"]
    out = []
    for t in np.flatnonzero(sup["usable"]):
        cols = np.flatnonzero(sup["finite"][t])
        ctrl = [_ranks(sup["wide"][c].to_numpy(float)[t, cols]) for c in controls]
        if synthetic_beta is not None:
            ctrl.append(_ranks(synthetic_beta[t, cols]))
        m = residualiser(np.column_stack(ctrl))
        f = m @ _ranks(sup["wide"][feature].to_numpy(float)[t, cols])
        norm = float(np.sqrt(f @ f))
        if norm == 0:
            continue
        s = f / f.std(ddof=0)
        out.append({"t": int(t), "cols": cols, "m": m, "fres": f / norm, "s": s,
                    "df": len(cols) - 1 - len(ctrl) - 1})
    return out


# --------------------------------------------------------------------------- #
# Inference
# --------------------------------------------------------------------------- #
def sn_statistic(x):
    """Lobato / Shao self-normalised t on the last axis (identical arithmetic to #290's inference_calibration)."""
    x = np.asarray(x, float)
    n = x.shape[-1]
    m = x.mean(axis=-1, keepdims=True)
    partial = np.cumsum(x - m, axis=-1)
    return np.sqrt(n) * m[..., 0] / np.sqrt((partial ** 2).sum(axis=-1) / n ** 2)


def sn_critical_value(alpha, *, paths=100_000, length=2_000, seed=20261031, chunk=2_000):
    rng = np.random.default_rng(seed)
    stats = [sn_statistic(rng.standard_normal((chunk, length))) for _ in range(paths // chunk)]
    return float(np.quantile(np.concatenate(stats), 1 - alpha))


def newey_west_t(x, lag):
    x = np.asarray(x, float)
    n = x.shape[-1]
    m = x.mean(axis=-1, keepdims=True)
    d = x - m
    var = (d * d).mean(axis=-1)
    for k in range(1, min(lag, n - 1) + 1):
        var = var + 2 * (1 - k / (lag + 1)) * (d[..., k:] * d[..., :-k]).sum(axis=-1) / n
    return m[..., 0] / np.sqrt(np.maximum(var, 1e-300) / n)


# --------------------------------------------------------------------------- #
# Synthetic labels and the per-date partial Spearman
# --------------------------------------------------------------------------- #
def noise(rng, kind, shape):
    if kind == "IID_NORMAL":
        return rng.standard_normal(shape)
    if kind == "T4":
        return rng.standard_t(4, shape) / math.sqrt(2.0)
    raise ValueError(kind)


def ar1_panel(rng, n_dates, n_ind, phi):
    out = np.empty((n_dates, n_ind))
    out[0] = rng.standard_normal(n_ind)
    scale = math.sqrt(1 - phi * phi)
    for t in range(1, n_dates):
        out[t] = phi * out[t - 1] + scale * rng.standard_normal(n_ind)
    return out


def forward_window_sums(u, hw):
    """sums[:, t] = u[:, t+1] + ... + u[:, t+hw]; zero (never used) where the window passes the grid end."""
    b, n_dates, n_ind = u.shape
    cum = np.concatenate([np.zeros((b, 1, n_ind)), np.cumsum(u, axis=1)], axis=1)
    sums = np.zeros_like(u)
    sums[:, : n_dates - hw] = cum[:, hw + 1:] - cum[:, 1: n_dates - hw + 1]
    return sums


def partial_series(designs, window_sums, rho, hw):
    """(reps, dates) per-date partial Spearman of the synthetic labels against the residualised feature rank."""
    c = rho / math.sqrt(hw * (1 - rho * rho)) if rho else 0.0
    reps = window_sums.shape[0]
    out = np.empty((reps, len(designs)))
    for j, d in enumerate(designs):
        y = c * hw * d["s"][None, :] + window_sums[:, d["t"], d["cols"]]
        r = np.argsort(np.argsort(y, axis=1), axis=1).astype(float)  # continuous labels: no ties
        ry = r @ d["m"]
        out[:, j] = (ry @ d["fres"]) / np.sqrt((ry * ry).sum(axis=1))
    return out


def run_cell(sup, protocol, *, horizon, design, noise_kind, crit, rng, reps):
    hw = protocol["horizons"][horizon]["weeks"]
    n_dates, n_ind = sup["finite"].shape
    beta = ar1_panel(rng, n_dates, n_ind, 0.98) if design == "K3" else None
    designs = [d for d in date_designs(sup, protocol, beta) if d["t"] + hw <= n_dates - 1]
    result = {"horizon": horizon, "design": design, "noise": noise_kind, "usableDates": len(designs),
              "meanCrossSection": float(np.mean([len(d["cols"]) for d in designs])) if designs else None,
              "meanResidualDf": float(np.mean([d["df"] for d in designs])) if designs else None,
              "byRho": {}}
    for rho in protocol["dgp"]["effectGrid"]:
        rej_sn = rej_nw = 0
        means, per_date_var = [], []
        done = 0
        while done < reps:
            b = min(250, reps - done)
            u = noise(rng, noise_kind, (b, n_dates, n_ind))
            sums = forward_window_sums(u, hw)
            x = partial_series(designs, sums, rho, hw)
            means.append(x.mean(axis=1))
            per_date_var.append(x.var(axis=0, ddof=1).mean())
            rej_sn += int((sn_statistic(x) > crit).sum())
            rej_nw += int((newey_west_t(x, hw) > 1.959963984540054).sum())
            done += b
        means = np.concatenate(means)
        result["byRho"][f"{rho:g}"] = {
            "registeredSnRejection": rej_sn / reps,
            "liberalNeweyWestRejection": rej_nw / reps,
            "meanStatistic": float(means.mean()),
            "sdOfDateMean": float(means.std(ddof=1)),
            "meanPerDateSd": float(math.sqrt(np.mean(per_date_var))),
        }
    null = result["byRho"]["0"]
    result["effectiveIndependentDatesUnderNull"] = (null["meanPerDateSd"] ** 2 / null["sdOfDateMean"] ** 2
                                                    if null["sdOfDateMean"] > 0 else None)
    return result


def decide(cells, protocol):
    rule = protocol["decisionRule"]
    key = f"{rule['economicallyMeaningfulRho']:g}"
    primary = next(c for c in cells if c["horizon"] == "H126" and c["design"] == "K2" and c["noise"] == "IID_NORMAL")
    power = primary["byRho"][key]["registeredSnRejection"]
    sizes = {f"{c['horizon']}|{c['design']}|{c['noise']}": c["byRho"]["0"]["registeredSnRejection"] for c in cells}
    size_ok = all(v <= rule["sizeCeiling"] for v in sizes.values())
    go = power >= rule["powerFloor"] and size_ok
    return {"verdict": "GO" if go else "NO_GO", "primaryPowerAtMeaningfulRho": power,
            "powerFloor": rule["powerFloor"], "sizeByCell": sizes, "sizeCeiling": rule["sizeCeiling"],
            "sizeWithinCeiling": size_ok}


def minimum_detectable(cell, floor):
    hits = [float(r) for r, v in cell["byRho"].items() if v["registeredSnRejection"] >= floor]
    return min(hits) if hits else None


def support_summary(sup):
    dates = pd.to_datetime(pd.Series(sup["dates"]))
    usable = sup["usable"]
    return {"gridDates": len(sup["dates"]), "industries": len(sup["industries"]),
            "industryDates": int(sup["finite"].size), "jointFiniteIndustryDates": int(sup["finite"].sum()),
            "datesMeetingMinCrossSection": int(usable.sum()),
            "usableDatesByYear": {str(k): int(v) for k, v in dates[usable].dt.year.value_counts().sort_index().items()},
            "yearsWithZeroUsableDates": sorted(int(y) for y in set(dates.dt.year) - set(dates[usable].dt.year)),
            "crossSectionOnUsableDates": {"min": int(sup["counts"][usable].min()),
                                          "median": float(np.median(sup["counts"][usable])),
                                          "max": int(sup["counts"][usable].max())}}


def full_grid_counterfactual(sup, protocol, *, crit, reps, seed):
    """POST-GATE DIAGNOSTIC, NOT A DECISION INPUT (added after the frozen gate result was read).

    Asks whether ANY data repair could rescue the question: every one of the 14 industries is measured on every one of
    the 610 dates (synthetic persistent feature and controls, AR(1) phi 0.98), H126, K2, IID noise. Repairs to
    terminal economics, KSIC or ex-dates can only remove industry-dates from the real support, so this is a ceiling."""
    rng = np.random.default_rng(seed)
    n_dates, n_ind = sup["finite"].shape
    wide = {c: pd.DataFrame(ar1_panel(rng, n_dates, n_ind, 0.98))
            for c in [protocol["feature"]] + protocol["controls"]["available"]}
    full = {"dates": sup["dates"], "industries": sup["industries"], "wide": wide,
            "finite": np.ones((n_dates, n_ind), bool), "counts": np.full(n_dates, n_ind),
            "usable": np.ones(n_dates, bool)}
    cell = run_cell(full, protocol, horizon="H126", design="K2", noise_kind="IID_NORMAL", crit=crit, rng=rng, reps=reps)
    cell["minimumDetectableRhoAtPowerFloor"] = minimum_detectable(cell, protocol["decisionRule"]["powerFloor"])
    cell["status"] = "POST_GATE_DIAGNOSTIC_CEILING_NOT_A_DECISION_INPUT"
    return cell


def run(protocol, frame, *, reps=None, crit=None):
    sup = support(frame, protocol)
    rng = np.random.default_rng(protocol["seed"])
    reps = reps or protocol["replications"]
    crit = crit if crit is not None else sn_critical_value(PRIMARY_ALPHA, seed=protocol["seed"])
    cells = []
    for horizon in protocol["horizons"]:
        for design in ("K2", "K3"):
            for kind in protocol["dgp"]["noise"]:
                cells.append(run_cell(sup, protocol, horizon=horizon, design=design, noise_kind=kind, crit=crit,
                                      rng=rng, reps=reps))
    decision = decide(cells, protocol)
    for c in cells:
        c["minimumDetectableRhoAtPowerFloor"] = minimum_detectable(c, protocol["decisionRule"]["powerFloor"])
    ceiling = full_grid_counterfactual(sup, protocol, crit=crit, reps=max(reps // 2, 1), seed=protocol["seed"] + 1)
    return {"studyId": protocol["studyId"], "stage": protocol["stage"],
            "outcomeAccess": "NONE: input columns only, synthetic labels",
            "protocolSha256": sha256(PROTOCOL_PATH), "panelSha256": sha256(ROOT / protocol["panel"]),
            "replications": reps, "primaryAlpha": PRIMARY_ALPHA, "snOneSidedCritical": crit, "support": support_summary(sup),
            "cells": cells, "decision": decision, "fullCoverageCeiling": ceiling}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=None)
    ap.add_argument("--out", default=str(RESULT_PATH))
    args = ap.parse_args(argv)
    protocol = load_protocol()
    result = run(protocol, load_inputs(protocol), reps=args.reps)
    Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps(result["decision"], indent=1))


if __name__ == "__main__":
    main()
