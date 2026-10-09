"""Exactly X1-X6, their frozen components and negative controls. No search."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from .statistics import percentiles, group_weights, linear_summary, nw_summary


def permutation(values, date, seed):
    stream = int.from_bytes(hashlib.sha256(f"{seed}:{date}".encode()).digest()[:8], "big")
    return np.asarray(values)[np.random.default_rng(stream).permutation(len(values))]


def contrast(a, b, valid, min_cell=3):
    masks = [(a == x) & (b == y) & valid for x, y in ((1, 1), (1, 0), (0, 1), (0, 0))]
    if min(m.sum() for m in masks) < min_cell:
        return None
    return sum(sign * m.astype(float) / m.sum() for sign, m in zip((1, -1, -1, 1), masks))


def binary_tercile(percentile):
    return np.where(percentile >= 2 / 3, 1, np.where(percentile <= 1 / 3, 0, np.nan))


def analyze(data, books, spec):
    ranks = percentiles(data)
    out = {}
    for ix in spec["interactions"]:
        name = ix["interactionId"]
        h = ix["horizon"]
        book = books[h]
        if ix["readiness"]["status"] != "READY":
            out[name] = {
                "interactionId": name,
                "horizon": h,
                "status": "BLOCKED",
                "reason": ix["readiness"]["reason"],
                "p": None,
                "negativeControlStatus": "BLOCKED_NO_PROXY_SUBSTITUTION",
                "features": ix["features"],
            }
            continue
        a, b = ix["features"]
        start, end = ix["readiness"]["evaluableRange"]
        dates = sorted(
            data.rows.date[
                (data.rows.date >= start)
                & (data.rows.date <= end)
                & book.table.missingReason.ne("NOT_MATURED_BY_CUTOFF")
            ].unique()
        )
        designs, control, difference = {}, {}, {}
        cell_counts = []
        regimes = {"NORMAL": [], "STRESSED": []}
        lagged = {"NORMAL": [], "STRESSED": []}
        for date in dates:
            ids = data.rows.index[data.rows.date.eq(date)].to_numpy(int)
            valid = (
                book.table.loc[ids, "state"].eq("VALID").to_numpy()
                & data.values.loc[ids, [a, b]].notna().all(axis=1).to_numpy()
            )
            av = binary_tercile(ranks.loc[ids, a].to_numpy(float))
            bv = binary_tercile(ranks.loc[ids, b].to_numpy(float))
            if name.startswith("X1"):
                bv = data.rows.loc[ids, "b08Confirmed"].to_numpy(float)
                valid &= data.rows.loc[ids, "b08State"].ne("INELIGIBLE").to_numpy()
            if valid.sum() < 30:
                continue
            if name.startswith("X6"):
                p = ranks.loc[ids, b].to_numpy(float)
                w = group_weights((p >= 2 / 3) & valid, (p <= 1 / 3) & valid)
                if w is None:
                    continue
                good = ids[valid]
                wg = w[valid]
                value = float(wg @ book.table.loc[good, "benchmarkRelative"].to_numpy(float))
                state = "STRESSED" if data.values.loc[ids[0], a] < 1 else "NORMAL"
                regimes[state].append({"date": date, "value": value})
                past_date = (pd.Timestamp(date) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
                past = data.rows.date[data.rows.date.le(past_date)].max()
                if isinstance(past, str):
                    past_ids = data.rows.index[data.rows.date.eq(past)]
                    s = data.values.loc[past_ids[0], a]
                    if np.isfinite(s):
                        lagged["STRESSED" if s < 1 else "NORMAL"].append({"date": date, "value": value})
                continue
            weight = contrast(av, bv, valid, spec["level3"]["minCell"])
            if weight is None:
                continue
            good = ids[valid]
            designs[date] = (good, weight[valid], 0.0)
            counts = [int(((av == x) & (bv == y) & valid).sum()) for x, y in ((1, 1), (1, 0), (0, 1), (0, 0))]
            cell_counts.append({"date": date, "HH_HL_LH_LL": counts, "names": int(valid.sum())})
            if name.startswith("X1") or name.startswith("X3"):
                # Registered contrast among expensive / lagging names.
                cw = group_weights((av == 0) & (bv == 1) & valid, (av == 0) & (bv == 0) & valid)
            elif name.startswith("X2"):
                pa = permutation(av, date, spec["level3"]["seed"])
                cw = contrast(pa, bv, valid, spec["level3"]["minCell"])
            elif name.startswith("X5"):
                pb = permutation(bv, date, spec["level3"]["seed"])
                cw = contrast(av, pb, valid, spec["level3"]["minCell"])
            else:
                raise ValueError("UNREGISTERED_INTERACTION")
            if cw is not None:
                control[date] = (good, cw[valid], 0.0)
                # X1/X3 four-corner primary ALREADY subtracts the expensive/
                # lagging slice. Do not subtract that same control twice.
                paired_weight = weight if name.startswith(("X1", "X3")) else weight - cw
                difference[date] = (good, paired_weight[valid], 0.0)
        if name.startswith("X6"):
            # A shared regime is constant across names on a date. It cannot be
            # a four-corner cross-section. Frozen split across dates is descriptive.
            state_result = {k: nw_summary([r["value"] for r in v], h) for k, v in regimes.items()}
            lag_result = {k: nw_summary([r["value"] for r in v], h) for k, v in lagged.items()}
            enough = min(len(v) for v in regimes.values()) >= spec["level3"]["minDatesPerState"]
            out[name] = {
                "interactionId": name,
                "horizon": h,
                "features": ix["features"],
                "status": "DESCRIPTIVE_UNCALIBRATED_STATE_CONTRAST" if enough else "BLOCKED",
                "regimeSlopes": state_result,
                "perDateByState": regimes,
                "negativeControl": lag_result,
                "negativeControlLag": "ONE_CALENDAR_YEAR_PAST_ONLY",
                "p": None,
                "claim": "market trend/volatility only; no CPI, inflation or unemployment claim",
            }
            continue
        primary = linear_summary(data, book, designs, dates, spec)
        neg = linear_summary(data, book, control, dates, spec)
        paired = linear_summary(data, book, difference, dates, spec)
        # Absolute direction of conditional hypotheses was not registered; test
        # relationship existence two-sided, and publish both sign and control.
        p = max(primary["p"], paired["p"]) if primary["p"] is not None and paired["p"] is not None else None
        out[name] = {
            "interactionId": name,
            "features": ix["features"],
            "horizon": h,
            "status": "DEVELOPMENT" if p is not None else "BLOCKED",
            "contrast": primary,
            "negativeControl": neg,
            "pairedVersusNegativeControl": paired,
            "cells": cell_counts,
            "p": p,
        }
    return out
