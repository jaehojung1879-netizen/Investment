"""Fixed date-balanced Ridge, annual purged/embargoed refits, fair paired comparisons."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .contract import digest, model_groups
from .statistics import matched_comparison, percentiles, rank_ic, nw_summary, factor_reading


def date_weights(dates):
    dates = np.asarray(dates)
    _, inverse, counts = np.unique(dates, return_inverse=True, return_counts=True)
    return 1.0 / (len(counts) * counts[inverse])


def weighted_median(x, w):
    ok = np.isfinite(x)
    if not ok.any():
        return 0.5
    order = np.argsort(x[ok], kind="stable")
    v = x[ok][order]
    weight = w[ok][order]
    return float(v[np.searchsorted(np.cumsum(weight), weight.sum() / 2)])


class Transformer:
    """Fitted exclusively on training rows; fixed indicators for every feature."""

    def fit(self, frame, dates):
        self.columns = list(frame.columns)
        a = frame.to_numpy(float)
        w = date_weights(dates)
        self.active = np.isfinite(a).any(axis=0)
        self.medians = np.array([weighted_median(a[:, i], w) for i in range(a.shape[1])])
        filled = np.where(np.isfinite(a), a, self.medians)
        self.mean = w @ filled
        self.sd = np.sqrt(w @ ((filled - self.mean) ** 2))
        self.sd[self.sd < 1e-12] = 1
        self.trainingDigest = digest(
            {
                "dates": list(map(str, dates)),
                "medians": self.medians.tolist(),
                "mean": self.mean.tolist(),
                "sd": self.sd.tolist(),
                "active": self.active.tolist(),
            }
        )
        return self

    def transform(self, frame):
        if list(frame.columns) != self.columns:
            raise ValueError("TRANSFORM_COLUMN_DRIFT")
        a = frame.to_numpy(float)
        missing = ~np.isfinite(a)
        filled = np.where(missing, self.medians, a)
        z = (filled - self.mean) / self.sd
        z[:, ~self.active] = 0
        missing[:, ~self.active] = True
        return np.column_stack([z, missing.astype(float)])

    def audit(self):
        return {
            "columns": self.columns,
            "inactiveTrainingColumns": [c for c, a in zip(self.columns, self.active) if not a],
            "medians": self.medians.tolist(),
            "means": self.mean.tolist(),
            "sd": self.sd.tolist(),
            "trainingDigest": self.trainingDigest,
        }


def ridge_fit(x, y, w, penalty):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    w = np.asarray(w, float)
    if not np.isfinite(x).all() or not np.isfinite(y).all() or not np.isfinite(w).all():
        raise ValueError("NONFINITE_TRAINING_DATA")
    xm = w @ x
    ym = float(w @ y)
    z = x - xm
    beta = np.linalg.solve(z.T @ (z * w[:, None]) + penalty * np.eye(x.shape[1]), z.T @ (w * (y - ym)))
    return beta, ym - float(xm @ beta)


def training_indices(data, book, year, spec):
    first = data.rows.date[data.rows.date.str.startswith(str(year))].min()
    if not isinstance(first, str):
        return np.array([], int), None
    cutoff_pos = int(data.days.searchsorted(pd.Timestamp(first))) - spec["chronology"]["embargoSessions"]
    if cutoff_pos < 0:
        return np.array([], int), None
    cutoff = str(data.days[cutoff_pos].date())
    valid = book.table.state.eq("VALID") & book.table.exit.lt(cutoff) & data.rows.date.lt(first)
    b4 = data.values[spec["baselines"]["B4_COMBINED_SIMPLE"]].notna().any(axis=1)
    valid &= b4
    counts = data.rows[valid].groupby("date").size()
    dates = counts.index[counts >= spec["chronology"]["minNamesPerTrainingDate"]]
    ids = data.rows.index[valid & data.rows.date.isin(dates)].to_numpy(int)
    if len(dates) < spec["chronology"]["minTrainingDates"]:
        ids = np.array([], int)
    return ids, cutoff


def predictions(data, book, spec, counters, permit, budget):
    permit.require()
    ranks = percentiles(data)
    groups = model_groups(spec)[book.horizon]
    preds = {k: np.full(len(data.rows), np.nan) for k in groups}
    audit = []
    redundancy = []
    common = data.values[spec["baselines"]["B4_COMBINED_SIMPLE"]].notna().any(axis=1)
    for year in spec["chronology"]["evaluationYears"]:
        budget.check()
        train, cutoff = training_indices(data, book, year, spec)
        eval_ids = data.rows.index[common & data.rows.date.str.startswith(str(year))].to_numpy(int)
        # Forecasts cover outcome-invalid names too: selection cannot evade a
        # terminal loss because a target happened to be unavailable. A year with
        # no registered mature signal has no scientific model fit.
        matured = book.table.missingReason.ne("NOT_MATURED_BY_CUTOFF") & data.rows.date.str.startswith(str(year))
        if len(eval_ids) == 0 or not matured.any():
            continue
        if len(train) == 0:
            audit.append(
                {
                    "year": year,
                    "trainingCutoff": cutoff,
                    "status": "BLOCKED_INSUFFICIENT_PAST_TARGETS",
                    "models": list(groups),
                }
            )
            continue
        y = book.table.loc[train, "benchmarkRelative"].astype(float)
        dates = data.rows.loc[train, "date"]
        y = (y - y.groupby(dates).transform("mean")).to_numpy(float)
        w = date_weights(dates)
        # The outcome-blind map reads training-year features only. Pairwise observed
        # data, date-balanced correlations, no validation outcome clustering.
        redcols = sorted(set(groups["FULL"]))
        correlations = [
            ranks.loc[g.index, redcols].corr(method="spearman", min_periods=30)
            for _, g in data.rows.loc[train].groupby("date")
        ]
        stack = np.stack([r.to_numpy(float) for r in correlations])
        counts = np.isfinite(stack).sum(axis=0)
        average = np.divide(np.nansum(stack, axis=0), counts, out=np.full(counts.shape, np.nan), where=counts > 0)
        red = pd.DataFrame(average, index=redcols, columns=redcols)
        edges = [
            {"a": a, "b": b, "rho": float(red.loc[a, b])}
            for i, a in enumerate(redcols)
            for b in redcols[i + 1 :]
            if np.isfinite(red.loc[a, b]) and abs(red.loc[a, b]) >= 0.8
        ]
        redundancy.append(
            {
                "year": year,
                "trainingCutoff": cutoff,
                "features": redcols,
                "spearman": red.astype(object).where(red.notna(), None).values.tolist(),
                "clusters": clusters(redcols, edges),
                "edgesAbsRhoAtLeast08": edges,
                "outcomeSelection": False,
            }
        )
        for name, cols in groups.items():
            if not cols:
                audit.append(
                    {"model": name, "year": year, "horizon": book.horizon, "status": "BLOCKED_EMPTY_FEATURE_GROUP"}
                )
                continue
            budget.fit()
            tr = Transformer().fit(ranks.loc[train, cols], dates)
            xt = tr.transform(ranks.loc[train, cols])
            xe = tr.transform(ranks.loc[eval_ids, cols])
            coef, intercept = ridge_fit(xt, y, w, spec["linearModel"]["penalty"])
            counters.increment("ModelFits", permit.synthetic)
            preds[name][eval_ids] = xe @ coef + intercept
            audit.append(
                {
                    "model": name,
                    "horizon": book.horizon,
                    "year": year,
                    "trainingCutoff": cutoff,
                    "lastTrainingTargetExit": book.table.loc[train, "exit"].max(),
                    "firstEvaluationSignal": data.rows.loc[eval_ids, "date"].min(),
                    "trainingDates": dates.nunique(),
                    "trainingRows": len(train),
                    "evaluationRows": len(eval_ids),
                    "transform": tr.audit(),
                    "coefficients": coef.tolist(),
                    "intercept": intercept,
                    "status": "FITTED",
                    "trainingSampleSha256": digest(data.rows.loc[train, ["date", "ticker"]].to_dict("records")),
                }
            )
    return preds, audit, redundancy


def clusters(columns, edges):
    parents = {c: c for c in columns}

    def find(c):
        while parents[c] != c:
            c = parents[c]
        return c

    for edge in edges:
        a, b = find(edge["a"]), find(edge["b"])
        parents[max(a, b)] = min(a, b)
    groups = {}
    for c in columns:
        groups.setdefault(find(c), []).append(c)
    return list(groups.values())


def scheduled_evaluation_dates(data, book, spec):
    return sorted(
        data.rows.date[
            data.rows.date.str[:4].astype(int).isin(spec["chronology"]["evaluationYears"])
            & book.table.missingReason.ne("NOT_MATURED_BY_CUTOFF")
        ].unique()
    )


def baseline_reading(data, book, pred, scheduled, spec):
    from .statistics import linear_summary

    designs = {}
    ic = []
    mse = []
    rows = 0
    for date in scheduled:
        ids = data.rows.index[data.rows.date.eq(date) & np.isfinite(pred) & book.table.state.eq("VALID")].to_numpy(int)
        if len(ids) < 30:
            continue
        y = book.table.loc[ids, "benchmarkRelative"].to_numpy(float)
        target = y - y.mean()
        p = np.asarray(pred)[ids]
        from pipeline.alpha_opportunity_v5_evidence import rank_weighted_spread_design

        weight = rank_weighted_spread_design(p, data.rows.loc[ids, "ticker"].to_numpy()).weights
        designs[date] = (ids, weight, 0.0)
        ic.append(rank_ic(p, target))
        mse.append(float(np.mean((p - target) ** 2)))
        rows += len(ids)
    return {
        "rankWeightedSpread": linear_summary(data, book, designs, scheduled, spec),
        "rankIC": nw_summary(ic, book.horizon),
        "dateBalancedMse": float(np.mean(mse)) if mse else None,
        "observations": rows,
    }


def incremental(data, book, preds, spec):
    dates = scheduled_evaluation_dates(data, book, spec)
    result = {
        "baselines": {
            k: baseline_reading(data, book, v, dates, spec)
            for k, v in preds.items()
            if k.startswith("B") or k == "FULL"
        },
        "comparisons": {},
    }
    for name in preds:
        if name.startswith("ADD_"):
            base, alt = "B4_COMBINED_SIMPLE", name
        elif name.startswith("REMOVE_"):
            base, alt = name, "FULL"
        else:
            continue
        pair = matched_comparison(data, book, preds[base], preds[alt], dates, spec)
        metrics = [pair[k] for k in spec["level2"]["incrementalMetrics"]]
        pair.update(
            base=base,
            alternative=alt,
            family=name.split("_")[1],
            horizon=book.horizon,
            p=max(m["p"] for m in metrics) if all(m["p"] is not None for m in metrics) else None,
            positive=all(m["estimate"] is not None and m["estimate"] > 0 for m in metrics),
        )
        result["comparisons"][f"{name}_H{book.horizon}"] = pair
    return result


def residual_and_slopes(data, book, feature, spec, *, ranks=None, budget=None):
    ranks = percentiles(data) if ranks is None else ranks
    b4 = spec["baselines"]["B4_COMBINED_SIMPLE"]
    fid = feature["featureId"]
    residual = np.full(len(data.rows), np.nan)
    slopes = []
    sample = []
    controls = ranks[b4].to_numpy(float)
    candidate = ranks[fid].to_numpy(float)
    valid = book.table.state.eq("VALID").to_numpy()
    target = book.table.benchmarkRelative.to_numpy(float)
    if not hasattr(data, "_date_arrays"):
        data._date_arrays = {d: g.index.to_numpy(int) for d, g in data.rows.groupby("date")}
    for _, all_ids in data._date_arrays.items():
        ids = all_ids[np.isfinite(candidate[all_ids])]
        if len(ids) < 30:
            continue
        measured = np.isfinite(controls[ids])
        x = np.column_stack([np.where(measured, controls[ids], 0.5), (~measured).astype(float)])
        z = candidate[ids]
        design = np.column_stack([np.ones(len(ids)), x])
        if budget is not None:
            budget.date_fit("projection")
        coef = np.linalg.lstsq(design, z, rcond=None)[0]
        component = z - design @ coef
        residual[ids] = component if np.std(component) > 1e-10 else 0.0
        good = ids[valid[ids]]
        if len(good) < 30:
            continue
        mask = valid[ids]
        conditional = np.column_stack([np.ones(len(good)), x[mask], z[mask]])
        if np.linalg.matrix_rank(conditional) > np.linalg.matrix_rank(conditional[:, :-1]):
            if budget is not None:
                budget.date_fit("slope")
            c = np.linalg.lstsq(conditional, target[good], rcond=None)[0]
            slopes.append(float(c[-1]) * feature["expectedDirection"])
            sample.extend(good.tolist())
    return {
        "featureId": fid,
        "horizon": book.horizon,
        "residualized": factor_reading(data, book, feature, spec, score=pd.Series(residual, index=data.rows.index)),
        "conditionalSlope": nw_summary(slopes, book.horizon),
        "slopeObservations": len(sample),
        "slopeMethod": "FAMA_MACBETH_DATE_OLS_DESCRIPTIVE_NW",
        "outcomeFreeResidualization": True,
    }
