"""Supplemental, DESCRIPTIVE diagnostics for the alpha-opportunity-model-v5 execution. Research only.

Frozen by `research_specs/alpha-opportunity-model-v5-diagnostics-v1.json` BEFORE any Alpha-v5 outcome. This
module is a supplement to the reviewed harness, not an amendment of the primary protocol, and it is built so
that it CANNOT change the primary result:

* it runs only after the complete registered primary result has been constructed, canonicalised and hashed
  (`primaryResultSha256`), and it is handed COPIES (`copy_context`);
* it has its own counters and never touches the primary counters;
* it produces no field the primary state machine reads, and `run_diagnostics_safely` converts ANY failure into a
  separate `DIAGNOSTIC_ERROR` record while the already-frozen primary payload stays exactly as it was;
* every output is scanned by a multiple-testing firewall that refuses significance, p-value, winner or promoted-
  predictor keys.

Nothing here is a claim. Coefficients are MODEL coefficients under training-only robust scaling, contributions are
MODEL attribution, ablation deltas are predictive reliance conditional on correlated substitutes, ALE curves are
descriptive B5 surfaces, regimes are mechanical labels. A hypothesis these suggest belongs to a NEW preregistration.
"""
from __future__ import annotations

import copy
import gzip
import io
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

from . import alpha_opportunity_model as V1
from . import alpha_opportunity_v2_model as M
from . import alpha_opportunity_v5_evidence as EV
from . import alpha_opportunity_v5_execution as X
from .alpha_opportunity_spec import canonical, digest, read_json

STUDY = "alpha-opportunity-model-v5-diagnostics-v1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "research_specs" / f"{STUDY}.json"
PARENT_SPEC_SHA256 = "d0f1aaf50d9629ba2f8a0a9802cd4ebd653018028ee97b2746f9e50703741e75"
SCHEMA_VERSION = 1
DIAGNOSTIC_ERROR = "DIAGNOSTIC_ERROR"
COMPLETE = "DIAGNOSTICS_COMPLETE"
NOT_RUN = "DIAGNOSTICS_NOT_RUN"
SPARSE = "DESCRIPTIVE_DATA_SPARSE"
NOT_APPLICABLE = "NOT_APPLICABLE"
FAMILIES = ("TREND_MOMENTUM", "RISK_VOLATILITY", "ATTENTION_LIQUIDITY", "ACCOUNTING")
REGIMES = ("POSITIVE/LOW", "POSITIVE/HIGH", "NON_POSITIVE/LOW", "NON_POSITIVE/HIGH")
REQUIRED_FALSE = ("affectsPrimaryClaim", "promotionEligible", "modelSelectionAllowed", "featureSelectionAllowed",
                  "resultCanRescuePrimary", "resultCanRefutePrimary", "resultCanGatePrimary", "resultCanTriggerRerun",
                  "resultCanChangeCandidateSelection", "resultCanTuneAnyParameter")
ARTIFACTS = {"ledger": "alpha-opportunity-model-v5-diagnostic-ledger.jsonl.gz",
             "models": "alpha-opportunity-model-v5-diagnostic-models.json",
             "summary": "alpha-opportunity-model-v5-diagnostic-summary.json"}


class DiagnosticFailure(RuntimeError):
    """A supplemental diagnostic could not be completed. Never a primary status."""


# --------------------------------------------------------------------------- #
# The frozen diagnostic spec.
# --------------------------------------------------------------------------- #
def load_diagnostic_spec(path=DEFAULT_SPEC, *, expected_hash, root=ROOT) -> dict:
    """Sidecar and digest agree with the externally supplied digest; the firewall flags are exactly the frozen ones;
    the semantic feature groups cover the sealed v5 registry exactly once per horizon."""
    path = Path(path)
    spec = read_json(path)
    seal = path.with_suffix(".sha256")
    if not seal.is_file() or not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError("UNSEALED_DIAGNOSTIC_SPEC")
    if not digest(spec) == seal.read_text().strip() == expected_hash:
        raise ValueError("SEALED_DIAGNOSTIC_SPEC_CHANGED: create and review a NEW version")
    if spec.get("studyId") != STUDY or spec["parent"]["specSha256"] != PARENT_SPEC_SHA256:
        raise ValueError("INVALID_DIAGNOSTIC_IDENTITY")
    firewall = spec["firewall"]
    if any(firewall.get(key) is not False for key in REQUIRED_FALSE):
        raise ValueError("DIAGNOSTIC_FIREWALL_FLAG_NOT_FALSE")
    if firewall.get("allDiagnosticsAreDescriptiveExploratory") is not True:
        raise ValueError("DIAGNOSTICS_MUST_BE_DESCRIPTIVE")
    from . import alpha_opportunity_v5_spec as S5
    sealed = S5.load_sealed(expected_hash=PARENT_SPEC_SHA256, root=root)
    for horizon, names in sealed["modifiedFromV4"]["features"]["KR"].items():
        assert_groups_cover(names, groups_for(spec, horizon))
    return spec


def groups_for(spec: dict, horizon) -> dict[str, list[str]]:
    """Family -> features for one horizon. ACCOUNTING exists only where the spec registers it."""
    groups = spec["featureGroups"]
    out = {family: list(groups[family]) for family in FAMILIES[:3]}
    accounting = groups["ACCOUNTING"]
    if str(horizon) in accounting["horizons"]:
        out["ACCOUNTING"] = list(accounting["features"])
    return out


def assert_groups_cover(names, groups) -> None:
    """Every registered feature belongs to exactly one family and no family names a feature outside the registry."""
    members = [name for feats in groups.values() for name in feats]
    if sorted(members) != sorted(names) or len(members) != len(set(members)):
        raise ValueError("FEATURE_GROUPS_DO_NOT_COVER_THE_REGISTRY_EXACTLY_ONCE")


def family_of(feature, groups) -> str:
    return next(family for family, feats in groups.items() if feature in feats)


def assert_firewall(node, spec) -> None:
    """Refuse any output key that would read as a significance claim, a winner or a promoted predictor."""
    forbidden = tuple(spec["firewall"]["forbiddenOutputKeySubstrings"])

    def walk(value, trail):
        if isinstance(value, dict):
            for key, item in value.items():
                if any(word in str(key).lower() for word in forbidden):
                    raise DiagnosticFailure(f"MULTIPLE_TESTING_FIREWALL: forbidden key {trail}/{key}")
                walk(item, f"{trail}/{key}")
        elif isinstance(value, list):
            for item in value:
                walk(item, trail)
    walk(node, "")


# --------------------------------------------------------------------------- #
# Small numeric helpers.
# --------------------------------------------------------------------------- #
def _f(value):
    """JSON-safe float: non-finite is None."""
    value = float(value)
    return value if math.isfinite(value) else None


def _quantiles(values):
    finite = np.array([v for v in values if v is not None and math.isfinite(v)], dtype=float)
    if not len(finite):
        return None, None
    q1, q3 = np.quantile(finite, [0.25, 0.75])
    return float(np.median(finite)), float(q3 - q1)


def weighted_pearson(x, y, w):
    total = w.sum()
    if total <= 0 or len(x) < 3:
        return None
    mx, my = (w * x).sum() / total, (w * y).sum() / total
    cov = (w * (x - mx) * (y - my)).sum() / total
    vx, vy = (w * (x - mx) ** 2).sum() / total, (w * (y - my) ** 2).sum() / total
    return None if vx <= 0 or vy <= 0 else float(cov / math.sqrt(vx * vy))


# --------------------------------------------------------------------------- #
# Ridge / Logistic exact decomposition and coefficient records (B4 only).
# --------------------------------------------------------------------------- #
def linear_view(fitted, frame) -> dict:
    """Coefficients, transformed values, missing indicators and exact per-feature contributions for `frame`.

    contribution_j = valueCoefficient_j * transformedFeature_j + missingIndicatorCoefficient_j * missingIndicator_j
    and  intercept + sum_j contribution_j  ==  the model's linear score.
    """
    transformer = fitted.transformer
    x = transformer.transform(frame)
    active = [name for name, on in zip(transformer.names, transformer.active) if on]
    a = len(active)
    coefficients = np.ravel(fitted.estimator.coef_)
    intercept = float(np.ravel(fitted.estimator.intercept_)[0])
    value_c, miss_c = coefficients[:a], coefficients[a:]
    values, missing = x[:, :a], x[:, a:]
    value_part, missing_part = values * value_c, missing * miss_c
    contribution = value_part + missing_part
    return {"active": active, "omitted": list(fitted.omitted), "valueCoefficient": value_c, "missingCoefficient": miss_c,
            "intercept": intercept, "transformed": values, "missingIndicator": missing, "contribution": contribution,
            "valuePart": value_part, "missingPart": missing_part, "score": intercept + contribution.sum(axis=1)}


def assert_exact_reconstruction(view, expected, tolerance, label) -> float:
    gap = float(np.max(np.abs(view["score"] - np.asarray(expected, dtype=float)))) if len(expected) else 0.0
    if gap > tolerance:
        raise DiagnosticFailure(f"EXACT_DECOMPOSITION_FAILED {label}: max gap {gap}")
    return gap


def family_contributions(view, groups) -> dict[str, dict[str, np.ndarray]]:
    """Signed = sum of the members' contributions; absolute = sum of the members' absolute contributions."""
    index = {name: i for i, name in enumerate(view["active"])}
    out = {}
    for family, features in groups.items():
        cols = [index[f] for f in features if f in index]
        signed = view["contribution"][:, cols].sum(axis=1) if cols else np.zeros(len(view["score"]))
        absolute = np.abs(view["contribution"][:, cols]).sum(axis=1) if cols else np.zeros(len(view["score"]))
        out[family] = {"signed": signed, "absolute": absolute}
    return out


def coefficient_record(fold, view) -> dict:
    return {"refitYear": int(fold["year"]), "trainingCutoff": fold["cutoff"], "intercept": view["intercept"],
            "activeFeatures": view["active"], "omittedFeatures": view["omitted"],
            "standardizedValueCoefficient": {n: float(c) for n, c in zip(view["active"], view["valueCoefficient"])},
            "missingIndicatorCoefficient": {n: float(c) for n, c in zip(view["active"], view["missingCoefficient"])}}


def coefficient_stability(records, registry) -> dict:
    """Descriptive distribution of every coefficient across the annual refits. No significance label."""
    ordered = sorted(records, key=lambda r: r["refitYear"])
    out = {"refits": len(ordered), "features": {}}

    def series(name, key):
        return [r[key].get(name) for r in ordered]

    for name in registry:
        block = {}
        for key, label in (("standardizedValueCoefficient", "value"), ("missingIndicatorCoefficient", "missingIndicator")):
            values = series(name, key)
            finite = [v for v in values if v is not None]
            med, iqr = _quantiles(finite)
            absolute, _ = _quantiles([abs(v) for v in finite])
            flips, previous = 0, 0
            for v in finite:
                sign = int(np.sign(v)) or previous
                flips += int(previous != 0 and sign != 0 and sign != previous)
                previous = sign or previous
            drift = [None if a is None or b is None else float(b - a) for a, b in zip(values[:-1], values[1:])]
            block[label] = {"active": len(finite), "omitted": len(values) - len(finite), "median": med,
                            "medianAbsolute": absolute, "interquartileRange": iqr,
                            "fractionPositive": None if not finite else float(np.mean([v > 0 for v in finite])),
                            "fractionNegative": None if not finite else float(np.mean([v < 0 for v in finite])),
                            "signFlipCount": flips, "yearToYearDrift": drift,
                            "medianAbsoluteYearToYearDrift": _quantiles([abs(d) for d in drift if d is not None])[0],
                            "signByRefit": [None if v is None else int(np.sign(v)) for v in values]}
        out["features"][name] = block

    def vector(record):
        v, m = record["standardizedValueCoefficient"], record["missingIndicatorCoefficient"]
        return np.array([v.get(n, 0.0) for n in registry] + [m.get(n, 0.0) for n in registry], dtype=float)

    vectors = [vector(r) for r in ordered]
    out["l2CoefficientVectorDrift"] = [{"fromYear": a["refitYear"], "toYear": b["refitYear"],
                                        "l2": float(np.linalg.norm(vb - va))}
                                       for (a, va), (b, vb) in zip(zip(ordered[:-1], vectors[:-1]),
                                                                   zip(ordered[1:], vectors[1:]))]
    out["medianL2CoefficientVectorDrift"] = _quantiles([d["l2"] for d in out["l2CoefficientVectorDrift"]])[0]
    out["interpretation"] = "model coefficients under training-only robust scaling; not causal effects"
    return out


# --------------------------------------------------------------------------- #
# Per-date evaluation metrics over the primary evaluation rows.
# --------------------------------------------------------------------------- #
def per_date_metrics(frame, column) -> dict:
    """Per-date MSE, rankWeightedSpread and prediction variance of one prediction column (ticker order)."""
    rows = []
    for date, group in frame.groupby("date", sort=True):
        g = group.sort_values("ticker", kind="stable")
        p, y = g[column].to_numpy(float), g.forwardRelativeReturn.to_numpy(float)
        design = EV.rank_weighted_spread_design(p, g.ticker.to_numpy())
        rows.append({"date": date, "mse": float(np.mean((p - y) ** 2)), "spread": float(design.weights @ y),
                     "variance": float(np.var(p)), "n": len(g)})
    return pd.DataFrame(rows)


def _summary(frame, column):
    d = per_date_metrics(frame, column)
    return {"pooledMse": float(np.mean((frame[column].to_numpy(float) - frame.forwardRelativeReturn.to_numpy(float)) ** 2)),
            "equalDateMse": float(d.mse.mean()), "rankWeightedSpread": float(d.spread.mean()),
            "predictionCrossSectionalVariance": float(d.variance.mean()), "signalWeeks": int(len(d))}


def ablation_deltas(frame, baseline_column, ablated_column) -> dict:
    """metric(ablation) - metric(B4) for every registered metric, pooled and by fold. Descriptive only."""
    def delta(part):
        base, abl = _summary(part, baseline_column), _summary(part, ablated_column)
        return {k: _f(abl[k] - base[k]) for k in ("pooledMse", "equalDateMse", "rankWeightedSpread",
                                                   "predictionCrossSectionalVariance")}

    out = {"overall": {**delta(frame), "rows": int(len(frame)), "signalWeeks": int(frame.date.nunique())}, "byFold": {}}
    for year, part in frame.groupby("foldYear", sort=True):
        out["byFold"][str(int(year))] = {**delta(part), "rows": int(len(part))}
    return out


def ablation_sets(names, groups) -> dict[str, list[str]]:
    """Every B4_MINUS_FEATURE_j and every B4_MINUS_GROUP_G, with the members it removes."""
    sets = {f"B4_MINUS_FEATURE_{n}": [n] for n in names}
    sets.update({f"B4_MINUS_GROUP_{g}": list(f) for g, f in groups.items()})
    return sets


# --------------------------------------------------------------------------- #
# Training-only redundancy.
# --------------------------------------------------------------------------- #
def training_association(train, names, transformer) -> dict:
    """Date-weighted Pearson and Spearman among the ACTIVE transformed features, from TRAINING rows only,
    pairwise complete and before imputation."""
    raw = transformer.raw(train)
    weights = V1.date_weights(train.date)
    active = [(i, n) for i, (n, on) in enumerate(zip(transformer.names, transformer.active)) if on]
    out = {}
    for ai in range(len(active)):
        for bi in range(ai + 1, len(active)):
            (i, a), (j, b) = active[ai], active[bi]
            ok = np.isfinite(raw[:, i]) & np.isfinite(raw[:, j])
            x, y, w = raw[ok, i], raw[ok, j], weights[ok]
            out[f"{a}|{b}"] = {"pearson": weighted_pearson(x, y, w) if ok.sum() > 2 else None,
                               "spearman": weighted_pearson(rankdata(x), rankdata(y), w) if ok.sum() > 2 else None,
                               "pairs": int(ok.sum())}
    return out


def aggregate_association(per_fold) -> dict:
    keys = sorted({k for fold in per_fold for k in fold})
    out = {}
    for key in keys:
        cell = {}
        for stat in ("pearson", "spearman"):
            med, iqr = _quantiles([fold[key][stat] for fold in per_fold if key in fold])
            cell[stat] = {"median": med, "interquartileRange": iqr}
        cell["folds"] = sum(1 for fold in per_fold if key in fold)
        out[key] = cell
    return out


# --------------------------------------------------------------------------- #
# Linear versus nonlinear (B4 vs B5), head concordance.
# --------------------------------------------------------------------------- #
def _quintile_sets(score, tickers, k):
    top = sorted(range(len(score)), key=lambda i: (-score[i], tickers[i]))[:k]
    bottom = sorted(range(len(score)), key=lambda i: (score[i], tickers[i]))[:k]
    return set(top), set(bottom)


def linear_vs_nonlinear(frame) -> dict:
    if not np.isfinite(frame.pB5.to_numpy(float)).all():
        return {"status": "UNAVAILABLE", "reason": "B5_NOT_FITTED_FOR_EVERY_EVALUATION_FOLD"}

    def block(part):
        per = []
        for _, g in part.groupby("date", sort=True):
            g = g.sort_values("ticker", kind="stable")
            a, b = g.pB4.to_numpy(float), g.pB5.to_numpy(float)
            k = math.ceil(len(g) / 5)
            ta, ba = _quintile_sets(a, g.ticker.tolist(), k)
            tb, bb = _quintile_sets(b, g.ticker.tolist(), k)
            per.append({"pearson": float(np.corrcoef(a, b)[0, 1]) if np.ptp(a) > 0 and np.ptp(b) > 0 else None,
                        "spearman": float(spearmanr(a, b).statistic) if np.ptp(a) > 0 and np.ptp(b) > 0 else None,
                        "top": len(ta & tb) / k, "bottom": len(ba & bb) / k, "std": float(np.std(b - a))})
        y = part.forwardRelativeReturn.to_numpy(float)
        a, b = part.pB4.to_numpy(float), part.pB5.to_numpy(float)
        mean = lambda key: _quantiles([p[key] for p in per])  # noqa: E731
        return {"signalWeeks": len(per), "rows": int(len(part)),
                "mseB5MinusB4": _f(np.mean((b - y) ** 2) - np.mean((a - y) ** 2)),
                "pooledPearson": _f(np.corrcoef(a, b)[0, 1]) if np.ptp(a) > 0 and np.ptp(b) > 0 else None,
                "equalDatePearsonMedian": mean("pearson")[0], "equalDateSpearmanMedian": mean("spearman")[0],
                "equalDateSpearmanMean": _f(np.nanmean([p["spearman"] if p["spearman"] is not None else np.nan for p in per])),
                "topQuintileOverlapMean": _f(np.mean([p["top"] for p in per])),
                "bottomQuintileOverlapMean": _f(np.mean([p["bottom"] for p in per])),
                "signDisagreementRate": _f(np.mean(np.sign(a) != np.sign(b))),
                "dispersionOfB5MinusB4Pooled": _f(np.std(b - a)),
                "dispersionOfB5MinusB4MeanPerDate": _f(np.mean([p["std"] for p in per]))}

    return {"status": "MEASURED", "overall": block(frame),
            "byFold": {str(int(y)): block(part) for y, part in frame.groupby("foldYear", sort=True)},
            "b5CannotRescueB4": True}


def _decile_index(values, tickers, bins=10):
    order = sorted(range(len(values)), key=lambda i: (values[i], tickers[i]))
    idx = np.empty(len(values), dtype=int)
    for rank, i in enumerate(order):
        idx[i] = min(bins - 1, rank * bins // len(values))
    return idx


def head_concordance(frame) -> dict:
    """Ridge expected return against the separate Logistic head. Descriptive; the probability head never gates."""
    if not np.isfinite(frame.prob.to_numpy(float)).all():
        return {"status": "UNAVAILABLE", "reason": "LOGISTIC_HEAD_NOT_FITTED_FOR_EVERY_EVALUATION_FOLD"}
    er_rows, pr_rows, corr = [], [], []
    for _, g in frame.groupby("date", sort=True):
        g = g.sort_values("ticker", kind="stable")
        er = g.pB4.to_numpy(float)
        pr = g.prob.to_numpy(float)
        corr.append((float(spearmanr(er, pr).statistic) if np.ptp(er) > 0 and np.ptp(pr) > 0 else None,
                     float(np.corrcoef(er, pr)[0, 1]) if np.ptp(er) > 0 and np.ptp(pr) > 0 else None))
        for d, y, z in zip(_decile_index(er, g.ticker.tolist()), g.forwardRelativeReturn, g.beatBenchmarkNet):
            er_rows.append((int(d), float(y), float(z)))
        for d, y, z in zip(_decile_index(pr, g.ticker.tolist()), g.forwardRelativeReturn, g.beatBenchmarkNet):
            pr_rows.append((int(d), float(y), float(z)))

    def table(rows):
        out = []
        for d in range(10):
            part = [r for r in rows if r[0] == d]
            out.append({"decile": d + 1, "rows": len(part),
                        "realizedBeatBenchmarkRate": _f(np.mean([r[2] for r in part])) if part else None,
                        "meanRealizedRelativeReturn": _f(np.mean([r[1] for r in part])) if part else None})
        return out

    p, z = frame.prob.to_numpy(float), frame.beatBenchmarkNet.to_numpy(float)
    edges = np.linspace(0.0, 1.0, 11)
    bins = np.minimum((p * 10).astype(int), 9)
    calibration = [{"bin": k + 1, "lower": float(edges[k]), "upper": float(edges[k + 1]), "rows": int((bins == k).sum()),
                    "meanPredictedProbability": _f(p[bins == k].mean()) if (bins == k).any() else None,
                    "realizedBeatBenchmarkRate": _f(z[bins == k].mean()) if (bins == k).any() else None}
                   for k in range(10)]
    er = frame.pB4.to_numpy(float)
    return {"status": "MEASURED", "role": "DESCRIPTIVE_ONLY_NEVER_A_GATE",
            "equalDateSpearmanOfHeadsMean": _f(np.nanmean([c[0] if c[0] is not None else np.nan for c in corr])),
            "equalDatePearsonOfHeadsMean": _f(np.nanmean([c[1] if c[1] is not None else np.nan for c in corr])),
            "expectedReturnDeciles": table(er_rows), "probabilityDeciles": table(pr_rows),
            "probabilityCalibration": calibration,
            "disagreement": {"expectedReturnPositiveProbabilityBelowHalf": int(((er > 0) & (p < 0.5)).sum()),
                             "expectedReturnNotPositiveProbabilityAtLeastHalf": int(((er <= 0) & (p >= 0.5)).sum()),
                             "rows": int(len(frame))}}


# --------------------------------------------------------------------------- #
# Accumulated local effects of B5.
# --------------------------------------------------------------------------- #
def ale_feature(fitted, train, valid, name, *, bins, minimum_support) -> dict:
    """1-D ALE of the fitted HGB for one feature. Edges come from TRAINING values only; the fold's out-of-fold rows are
    assigned to those bins and only bins with enough support are estimated, never bridged or extrapolated."""
    transformer, model = fitted.transformer, fitted.estimator
    train_values = pd.to_numeric(train[name], errors="coerce").to_numpy(float)
    train_values = train_values[np.isfinite(train_values)]
    if len(train_values) < 2:
        return {"status": "DEGENERATE_TRAINING_FEATURE"}
    edges = np.unique(np.quantile(train_values, np.linspace(0.0, 1.0, bins + 1)))
    if len(edges) < 2:
        return {"status": "DEGENERATE_TRAINING_FEATURE"}
    values = pd.to_numeric(valid[name], errors="coerce").to_numpy(float)
    observed = np.isfinite(values)
    rows = valid.loc[observed].reset_index(drop=True)
    assigned = np.clip(np.searchsorted(edges[1:-1], values[observed], side="right"), 0, len(edges) - 2)
    out_bins, accumulated, defined = [], 0.0, True
    for k in range(len(edges) - 1):
        members = rows.loc[assigned == k]
        entry = {"bin": k + 1, "lower": float(edges[k]), "upper": float(edges[k + 1]), "support": int(len(members))}
        if len(members) < minimum_support:
            out_bins.append({**entry, "status": "UNSUPPORTED", "localEffect": None, "accumulated": None})
            defined = False
            continue
        low, high = members.copy(), members.copy()
        low[name], high[name] = float(edges[k]), float(edges[k + 1])
        effect = float(np.mean(model.predict(transformer.transform(high)) - model.predict(transformer.transform(low))))
        accumulated = accumulated + effect if defined else None
        out_bins.append({**entry, "status": "SUPPORTED", "localEffect": effect,
                         "accumulated": accumulated if defined else None})
    usable = [(b["support"], out_bins[i - 1]["accumulated"] if i else 0.0, b["accumulated"])
              for i, b in enumerate(out_bins) if b["accumulated"] is not None]
    centre = (sum(n * (lo + hi) / 2 for n, lo, hi in usable) / sum(n for n, _, _ in usable)) if usable else None
    for b in out_bins:
        b["centeredAle"] = None if b["accumulated"] is None or centre is None else float(b["accumulated"] - centre)
    return {"status": "MEASURED", "edges": [float(e) for e in edges], "bins": out_bins,
            "supportedBins": int(sum(b["status"] == "SUPPORTED" for b in out_bins)), "rowsWithObservedValue": int(observed.sum())}


def aggregate_ale(per_fold) -> dict:
    """Descriptive median across folds by decile index."""
    by_bin: dict[int, list[dict]] = {}
    for fold in per_fold:
        if fold.get("status") == "MEASURED":
            for b in fold["bins"]:
                by_bin.setdefault(b["bin"], []).append(b)
    return {str(k): {"foldsSupported": sum(1 for b in v if b["status"] == "SUPPORTED"), "folds": len(v),
                     "medianUpperEdge": _quantiles([b["upper"] for b in v])[0],
                     "medianLocalEffect": _quantiles([b["localEffect"] for b in v])[0],
                     "medianCenteredAle": _quantiles([b["centeredAle"] for b in v])[0]}
            for k, v in sorted(by_bin.items())}


# --------------------------------------------------------------------------- #
# Regimes: information known at the signal date only.
# --------------------------------------------------------------------------- #
def benchmark_regimes(bench_close, days, schedule, cfg) -> dict:
    """{signal date: {trend, volatility, regime}} from the benchmark's own past. `bench_close` is aligned to `days`.

    Each label at date t reads `bench_close[: t + 1]` only; the volatility threshold is the median of the same statistic
    over the STRICTLY EARLIER schedule dates (expanding), so no later data and no full-sample constant enters."""
    days = pd.DatetimeIndex(days)
    close = np.asarray(bench_close, dtype=float)
    trend_window, vol_window = 126, 63
    minimum_prior = int(cfg["VOLATILITY"]["minimumPriorSignalDates"])
    out, prior_vols = {}, []
    for date in sorted(schedule):
        i = int(days.searchsorted(pd.Timestamp(date), side="left"))
        window = close[: i + 1]
        trend = None
        if i >= trend_window and np.isfinite(window[i]) and np.isfinite(window[i - trend_window]) and window[i - trend_window] > 0:
            trend = "POSITIVE" if window[i] / window[i - trend_window] - 1.0 > 0 else "NON_POSITIVE"
        vol = None
        if i >= vol_window:
            seg = window[i - vol_window: i + 1]
            if np.isfinite(seg).all() and (seg > 0).all():
                vol = float(np.std(seg[1:] / seg[:-1] - 1.0, ddof=1) * math.sqrt(252))
        level = None
        if vol is not None and len(prior_vols) >= minimum_prior:
            level = "HIGH" if vol > float(np.median(prior_vols)) else "LOW"
        out[date] = {"trend": trend, "volatility": level, "volatility63": vol,
                     "regime": f"{trend}/{level}" if trend and level else "UNDETERMINED"}
        if vol is not None:
            prior_vols.append(vol)
    return out


def _metric_block(part) -> dict:
    per = per_date_metrics(part, "pB4")
    y = part.forwardRelativeReturn.to_numpy(float)
    mse = {c: float(np.mean((part[c].to_numpy(float) - y) ** 2)) for c in ("pB0", "pB2", "pB4")}
    block = {"signalWeeks": int(part.date.nunique()), "eligibleNames": int(len(part)),
             "b4Mse": mse["pB4"], "b0Mse": mse["pB0"], "b2Mse": mse["pB2"],
             "b4VsB0MseImprovement": mse["pB0"] - mse["pB4"], "b4VsB2MseImprovement": mse["pB2"] - mse["pB4"],
             "b4EqualDateMse": float(per.mse.mean()), "rankWeightedSpread": float(per.spread.mean())}
    if np.isfinite(part.pB5.to_numpy(float)).all():
        sp = []
        for _, g in part.groupby("date"):
            a, b = g.pB4.to_numpy(float), g.pB5.to_numpy(float)
            sp.append(float(spearmanr(a, b).statistic) if np.ptp(a) > 0 and np.ptp(b) > 0 else np.nan)
        block["b4B5Agreement"] = {"equalDateSpearmanMean": _f(np.nanmean(sp)) if not np.isnan(sp).all() else None,
                                  "signAgreementRate": float(np.mean(np.sign(part.pB4) == np.sign(part.pB5)))}
    else:
        block["b4B5Agreement"] = None
    if np.isfinite(part.prob.to_numpy(float)).all():
        p, z = np.clip(part.prob.to_numpy(float), 1e-12, 1 - 1e-12), part.beatBenchmarkNet.to_numpy(float)
        block["logisticBrier"] = float(np.mean((p - z) ** 2))
        block["logisticLogLoss"] = float(-np.mean(z * np.log(p) + (1 - z) * np.log(1 - p)))
    else:
        block["logisticBrier"] = block["logisticLogLoss"] = None
    return block


def regime_tables(frame, regimes, cfg) -> dict:
    """Descriptive metrics by mechanical regime and by calendar evaluation year. Below the fixed minimum: counts only."""
    minimum = int(cfg["minimumSignalWeeks"])
    labelled = frame.assign(regime=frame.date.map(lambda d: regimes.get(d, {}).get("regime", "UNDETERMINED")),
                            year=frame.date.str[:4])

    def cell(part):
        weeks = int(part.date.nunique())
        if weeks < minimum:
            return {"status": SPARSE, "signalWeeks": weeks, "eligibleNames": int(len(part))}
        return {"status": "DESCRIPTIVE", **_metric_block(part)}

    return {"minimumSignalWeeks": minimum,
            "byRegime": {r: cell(labelled.loc[labelled.regime.eq(r)]) for r in REGIMES},
            "undetermined": {"signalWeeks": int(labelled.loc[labelled.regime.eq("UNDETERMINED")].date.nunique())},
            "byCalendarYear": {y: cell(part) for y, part in labelled.groupby("year", sort=True)},
            "notAClaim": True}


# --------------------------------------------------------------------------- #
# Per-horizon pass: refit, decompose, ablate, ALE.
# --------------------------------------------------------------------------- #
def evaluation_folds(cell) -> list[int]:
    return [int(f["year"]) for f in cell["folds"] if f["evaluation"] and f["status"] == "READY"]


def run_horizon(horizon, ctx, runtime_spec, diag) -> dict:
    """Everything supplemental for one horizon, from copies of the primary intermediates."""
    names = ctx["rungs"]["B4"]
    groups = groups_for(diag, horizon)
    assert_groups_cover(names, groups)
    table = ctx["table"].copy()
    tol = float(diag["predictionDecomposition"]["absoluteTolerance"])
    ale_cfg = diag["ale"]
    counters = ctx["diagnosticCounters"]
    years = set(evaluation_folds(ctx["cell"]))
    sets = ablation_sets(names, groups)
    folds_out, coefficient_records, logistic_records = [], [], []
    association_folds, ale_folds = [], {n: [] for n in names}
    ablation_frames: dict[str, list] = {k: [] for k in sets}
    ablation_missing: dict[str, list] = {k: [] for k in sets}
    ledger_parts, contribution_by_date = [], []
    primary_pred = ctx["cell"]["predictions"].set_index(["date", "ticker"])

    for fold in V1.folds(M.as_v1_target(ctx["modelling"]), ctx["schedule"], runtime_spec):
        if fold["year"] not in years or fold["status"] != "READY":
            continue
        train, valid = fold["train"], fold["validation"]
        # ---- B4 Ridge: refit, prove it reproduces the primary prediction, decompose exactly. ----
        counters["diagnosticFits"] += 1
        ridge = X.fit_model("ridge", train, valid, names, runtime_spec)
        keys = list(zip(valid.date, valid.ticker))
        reference = primary_pred.loc[keys, "pB4"].to_numpy(float)
        if not np.allclose(ridge.prediction, reference, rtol=0.0, atol=1e-12):
            raise DiagnosticFailure("DIAGNOSTIC_REFIT_DIFFERS_FROM_PRIMARY_B4")
        view = linear_view(ridge, valid)
        gap = assert_exact_reconstruction(view, ridge.prediction, tol, f"B4 H{horizon} {fold['year']}")
        coefficient_records.append(coefficient_record(fold, view))
        fam = family_contributions(view, groups)
        # ---- Logistic head on the LOG-ODDS scale only. ----
        logit_view = None
        try:
            counters["diagnosticFits"] += 1
            logistic = X.fit_model("logistic", train, valid, names, runtime_spec)
            logit_view = linear_view(logistic, valid)
            assert_exact_reconstruction(logit_view, logistic.estimator.decision_function(logistic.transformer.transform(valid)),
                                        tol, f"LOGISTIC_LOG_ODDS H{horizon} {fold['year']}")
            logistic_records.append({**coefficient_record(fold, logit_view), "scale": "LOG_ODDS"})
        except (ValueError, FloatingPointError, Warning):
            logit_view = None
        # ---- training-only redundancy ----
        association_folds.append(training_association(train, names, ridge.transformer))
        # ---- B5 ALE (bins from TRAINING only) ----
        try:
            counters["diagnosticFits"] += 1
            hgb = X.fit_model("hgb", train, valid, names, runtime_spec)
            for name in [n for n, on in zip(hgb.transformer.names, hgb.transformer.active) if on]:
                counters["aleFeatureFolds"] += 1
                ale_folds[name].append({"refitYear": int(fold["year"]),
                                        **ale_feature(hgb, train, valid, name, bins=ale_cfg["bins"],
                                                      minimum_support=ale_cfg["minimumBinSupport"])})
        except (ValueError, FloatingPointError, Warning):
            pass
        # ---- leave-one-feature-out / leave-one-family-out on IDENTICAL folds ----
        for label, removed in sets.items():
            remaining = [n for n in names if n not in removed]
            if not remaining:
                ablation_missing[label].append({"refitYear": int(fold["year"]), "reason": "NO_REMAINING_FEATURES"})
                continue
            try:
                counters["diagnosticFits"] += 1
                fit = X.fit_model("ridge", train, valid, remaining, runtime_spec)
            except (ValueError, FloatingPointError, Warning) as exc:
                ablation_missing[label].append({"refitYear": int(fold["year"]), "reason": type(exc).__name__})
                continue
            ablation_frames[label].append(pd.DataFrame({"date": valid.date.to_numpy(), "ticker": valid.ticker.to_numpy(),
                                                        "pAblated": fit.prediction}))
        # ---- ledger rows and per-date contribution summaries for the primary evaluation rows ----
        wanted = table.loc[table.foldYear.eq(fold["year"]), ["date", "ticker"]]
        position = {k: i for i, k in enumerate(keys)}
        rows_idx = [position[k] for k in zip(wanted.date, wanted.ticker)]
        ledger_parts.append((fold, valid, view, logit_view, fam, rows_idx))
        for date, idx in pd.Series(rows_idx, index=wanted.date.to_numpy()).groupby(level=0):
            ix = np.asarray(idx)
            entry = {"date": date, "foldYear": int(fold["year"]), "names": int(len(ix)),
                     "intercept": view["intercept"], "families": {}}
            total_abs = sum(float(np.mean(fam[f]["absolute"][ix])) for f in groups)
            for family in groups:
                entry["families"][family] = {
                    "meanSigned": float(np.mean(fam[family]["signed"][ix])),
                    "meanAbsolute": float(np.mean(fam[family]["absolute"][ix])),
                    "crossSectionalDispersion": float(np.std(fam[family]["signed"][ix])),
                    "shareOfAbsoluteContribution": None if total_abs <= 0 else float(np.mean(fam[family]["absolute"][ix]) / total_abs)}
            contribution_by_date.append(entry)
        folds_out.append({"refitYear": int(fold["year"]), "trainingCutoff": fold["cutoff"],
                          "trainingRows": int(len(train)), "trainingDates": int(train.date.nunique()),
                          "validationRows": int(len(valid)), "activeFeatures": view["active"], "omittedFeatures": view["omitted"],
                          "transform": {"center": {n: float(c) for n, c in zip(view["active"], ridge.transformer.center)},
                                        "scale": {n: float(c) for n, c in zip(view["active"], ridge.transformer.scale)}},
                          "b4Intercept": view["intercept"], "maxExactReconstructionGap": gap,
                          "logisticCoefficients": next((r for r in logistic_records if r["refitYear"] == fold["year"]), None)})

    # ---- ablation summaries against B4 on the primary evaluation rows ----
    base = table[["date", "ticker", "foldYear", "forwardRelativeReturn", "pB4"]]
    ablations = {}
    for label, removed in sets.items():
        if not ablation_frames[label]:
            ablations[label] = {"removes": removed, "status": "UNAVAILABLE", "failures": ablation_missing[label]}
            continue
        merged = base.merge(pd.concat(ablation_frames[label], ignore_index=True), on=["date", "ticker"], how="inner")
        ablations[label] = {"removes": removed, "status": "MEASURED", "failures": ablation_missing[label],
                            **ablation_deltas(merged, "pB4", "pAblated")}
    # ---- the descriptive attribution map: unique reliance, shared information, family reliance, side by side ----
    associations = aggregate_association(association_folds)
    partner = {}
    for name in names:
        best = None
        for key, cell in associations.items():
            a, b = key.split("|")
            if name in (a, b):
                corr = cell["pearson"]["median"]
                if corr is not None and (best is None or abs(corr) > abs(best[1])):
                    best = (b if a == name else a, corr)
        partner[name] = None if best is None else {"feature": best[0], "medianWeightedPearson": best[1]}
    reliance = {n: {"family": family_of(n, groups),
                    "uniquePooledMseDelta": ablations[f"B4_MINUS_FEATURE_{n}"].get("overall", {}).get("pooledMse"),
                    "familyPooledMseDelta": ablations[f"B4_MINUS_GROUP_{family_of(n, groups)}"].get("overall", {}).get("pooledMse"),
                    "mostAssociatedFeature": partner[n]} for n in names}
    sample = ledger_parts
    return {"horizon": horizon, "groups": groups, "folds": folds_out, "coefficientRecords": coefficient_records,
            "logisticRecords": logistic_records,
            "coefficientStability": coefficient_stability(coefficient_records, names),
            "logisticCoefficientStability": coefficient_stability(
                [{k: v for k, v in r.items() if k != "scale"} for r in logistic_records], names) if logistic_records else None,
            "ablations": ablations, "association": {"perFold": association_folds, "aggregate": associations},
            "attributionMap": reliance,
            "ale": {n: {"perFold": ale_folds[n], "aggregate": aggregate_ale(ale_folds[n])} for n in names},
            "contributionByDate": contribution_by_date, "_ledger": sample}


def contribution_summaries(contribution_by_date, groups) -> dict:
    by_fold: dict[int, list] = {}
    for e in contribution_by_date:
        by_fold.setdefault(e["foldYear"], []).append(e)

    def average(entries):
        out = {}
        for family in groups:
            out[family] = {key: _f(np.nanmean([e["families"][family][key] if e["families"][family][key] is not None
                                               else np.nan for e in entries]))
                           for key in ("meanSigned", "meanAbsolute", "crossSectionalDispersion", "shareOfAbsoluteContribution")}
        return out

    return {"signalWeeks": len(contribution_by_date), "overall": average(contribution_by_date),
            "byFold": {str(y): average(v) for y, v in sorted(by_fold.items())},
            "byDate": contribution_by_date, "definitions": {
                "signed": "sum over the family's members of valueCoefficient*transformed + missingCoefficient*indicator",
                "absolute": "sum over the family's members of the absolute member contribution",
                "share": "family mean absolute contribution divided by the sum over families",
                "note": "model attribution, not true importance; intercept is reported separately"}}


# --------------------------------------------------------------------------- #
# Ledger.
# --------------------------------------------------------------------------- #
def ledger_rows(horizon, part, table, regimes, groups, study, names) -> list[dict]:
    """One row per primary evaluation name-date, from the fold pass (never from a second fit)."""
    fold, valid, view, logit_view, fam, rows_idx = part
    wanted = table.loc[table.foldYear.eq(fold["year"])].set_index(["date", "ticker"])
    index = {k: i for i, k in enumerate(zip(valid.date, valid.ticker))}
    active = view["active"]
    out = []
    for (date, ticker), row in wanted.iterrows():
        i = index[(date, ticker)]
        src = valid.iloc[i]
        contributions = {n: float(view["contribution"][i, j]) for j, n in enumerate(active)}
        out.append({
            "studyId": study, "horizon": int(horizon), "signalDate": date, "ticker": ticker,
            "foldId": int(fold["year"]), "trainingCutoff": fold["cutoff"],
            "featureValues": {n: _f(src[n]) if n in src and pd.notna(src[n]) else None for n in names},
            "transformedFeatureValues": {n: float(view["transformed"][i, j]) for j, n in enumerate(active)},
            "missingIndicators": {n: int(view["missingIndicator"][i, j]) for j, n in enumerate(active)},
            "predictions": {k: _f(row[c]) for k, c in (("B0", "pB0"), ("B1", "pB1"), ("B2", "pB2"), ("B3", "pB3"),
                                                        ("B4", "pB4"), ("B5", "pB5"))},
            "logisticProbability": _f(row["prob"]),
            "b4Intercept": view["intercept"],
            "b4FeatureContributions": contributions,
            "b4FamilyContributions": {f: {"signed": float(fam[f]["signed"][i]), "absolute": float(fam[f]["absolute"][i])}
                                      for f in groups},
            "realizedRelativeReturn": _f(row["forwardRelativeReturn"]), "beatBenchmarkNet": int(row["beatBenchmarkNet"]),
            "roundTripCost": _f(row["roundTripCost"]), "selected": bool(row["pB4"] - row["roundTripCost"] > 0),
            "eligibilityStatus": str(row.get("eligibilityStatus")), "eligibilityReasonCode": str(row.get("eligibilityReasonCode")),
            "regime": regimes.get(date, {"regime": "UNDETERMINED"})["regime"]})
    return out


def serialize_ledger(rows) -> bytes:
    """Canonical JSON lines sorted by (horizon, signalDate, ticker), gzip with a fixed header time."""
    ordered = sorted(rows, key=lambda r: (r["horizon"], r["signalDate"], r["ticker"]))
    raw = b"".join(canonical(r) + b"\n" for r in ordered)
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0, compresslevel=6) as handle:
        handle.write(raw)
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# Orchestration: primary first, diagnostics after, failures isolated.
# --------------------------------------------------------------------------- #
def copy_context(ctx: dict) -> dict:
    """Deep, independent copies of every intermediate the diagnostics read."""
    return copy.deepcopy(ctx)


def _header(diag_sha, primary_sha, harness, name, rows):
    return {"schemaVersion": SCHEMA_VERSION, "artifact": name, "studyId": STUDY, "rowCount": int(rows),
            "primaryResultSha256": primary_sha, "diagnosticSpecSha256": diag_sha, "harnessFileHashes": harness,
            "affectsPrimaryClaim": False, "promotionEligible": False}


def run_supplemental(ctx, *, runtime_spec, diag, diag_sha, primary_sha, harness_hashes) -> dict:
    """Build the three diagnostic artifacts from copies of the primary intermediates. Raises on any inconsistency."""
    ctx = copy_context(ctx)
    ctx["diagnosticCounters"] = {"diagnosticFits": 0, "aleFeatureFolds": 0}
    models, summary, ledger = {}, {}, []
    for horizon, hctx in sorted(ctx["horizons"].items()):
        if hctx.get("table") is None:
            summary[str(horizon)] = {"status": NOT_RUN, "reason": "NO_PRIMARY_EVALUATION_TABLE"}
            continue
        hctx["diagnosticCounters"] = ctx["diagnosticCounters"]
        hctx["schedule"] = ctx["schedule"]
        out = run_horizon(horizon, hctx, runtime_spec, diag)
        table, groups = hctx["table"], out["groups"]
        regimes = benchmark_regimes(ctx["benchmarkClose"], ctx["days"], ctx["schedule"], diag["regimes"])
        rows = []
        for part in out.pop("_ledger"):
            rows += ledger_rows(horizon, part, table, regimes, groups, STUDY, hctx["rungs"]["B4"])
        ledger += rows
        models[str(horizon)] = {k: out[k] for k in ("groups", "folds", "coefficientStability", "logisticCoefficientStability",
                                                    "ablations", "association", "attributionMap", "ale")}
        models[str(horizon)]["coefficientRecords"] = out["coefficientRecords"]
        models[str(horizon)]["logisticCoefficientRecords"] = out["logisticRecords"]
        summary[str(horizon)] = {
            "status": COMPLETE,
            "contributions": contribution_summaries(out["contributionByDate"], groups),
            "linearVsNonlinear": linear_vs_nonlinear(table),
            "headConcordance": head_concordance(table),
            "regimes": regime_tables(table, regimes, diag["regimes"]),
            "accountingGroup": groups.get("ACCOUNTING", NOT_APPLICABLE) if "ACCOUNTING" in groups else NOT_APPLICABLE,
            "evaluationRows": int(len(table))}
    ledger_bytes = serialize_ledger(ledger)
    models_doc = {**_header(diag_sha, primary_sha, harness_hashes, ARTIFACTS["models"],
                            sum(len(m["folds"]) for m in models.values())),
                  "horizons": models, "conventions": diag["ablation"]["convention"]}
    summary_doc = {**_header(diag_sha, primary_sha, harness_hashes, ARTIFACTS["summary"], len(summary)),
                   "horizons": summary}
    for document in (models_doc, summary_doc):
        assert_firewall(document, diag)
    artifacts = {ARTIFACTS["ledger"]: ledger_bytes,
                 ARTIFACTS["models"]: X.jsonable_bytes(models_doc),
                 ARTIFACTS["summary"]: X.jsonable_bytes(summary_doc)}
    import hashlib
    references = {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                         "schemaVersion": SCHEMA_VERSION,
                         "rowCount": len(ledger) if name == ARTIFACTS["ledger"] else None}
                  for name, data in artifacts.items()}
    return {"status": COMPLETE, "artifacts": artifacts, "references": references,
            "counters": ctx["diagnosticCounters"]}


def run_diagnostics_safely(ctx, **kwargs) -> dict:
    """Any failure, and any malformed return, becomes a separate DIAGNOSTIC_ERROR record. It cannot change a primary
    status or payload and it never authorises a substantive retry."""
    try:
        out = run_supplemental(ctx, **kwargs)
        if (not isinstance(out, dict) or out.get("status") != COMPLETE or not isinstance(out.get("artifacts"), dict)
                or not all(isinstance(v, (bytes, bytearray)) for v in out["artifacts"].values())
                or not isinstance(out.get("references"), dict)):
            raise DiagnosticFailure("DIAGNOSTIC_OUTPUT_INVALID")
        return out
    except BaseException as exc:  # noqa: BLE001 - isolation is the point: nothing here may escape into the primary path
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return {"status": DIAGNOSTIC_ERROR, "artifacts": {}, "references": {},
                "error": {"code": type(exc).__name__, "message": str(exc)[:300]},
                "authorizesRetry": False, "changesPrimary": False}


REFERENCES_NAME = "alpha-opportunity-model-v5-diagnostic-references.json"


def execute_with_diagnostics(*, run_kwargs, diag=None, diag_sha=None, harness_hashes=None,
                             persist_primary=None) -> dict:
    """PRIMARY FIRST AND PRIMARY DURABLE. 1) the complete registered primary result is built; 2) canonicalised;
    3) its hash frozen; 4) `persist_primary(bytes)` makes the primary result durable (the caller writes it atomically);
    5) ONLY THEN are the supplemental diagnostics run, on copies. The primary bytes are final at step 4: they are never
    rewritten, never gain a diagnostic reference and never depend on whether diagnostics finish, so a diagnostic failure
    of ANY kind (an exception, an OOM kill, a timeout, a crash) cannot destroy, alter or invalidate a completed primary
    result. The references to the diagnostic artifacts live in their own document (`references`), never in the primary
    file. `diag=None` disables the layer and yields exactly the same primary bytes."""
    capture = {} if diag is not None else None
    result = X.run_execution(**run_kwargs, capture=capture)
    frozen = X.freeze_primary(result)
    primary_bytes = X.finalize_primary(frozen)
    if persist_primary is not None:
        persist_primary(primary_bytes)               # durable BEFORE any diagnostic function is invoked
    if diag is None:
        return {"frozen": frozen, "primaryBytes": primary_bytes, "diagnosticArtifacts": {},
                "references": None, "referencesBytes": None, "diagnosticStatus": "DISABLED"}
    reached = (result["phaseReached"] == "COMPLETE" and result["executionMode"] == X.FORMAL
               and any(h.get("table") is not None for h in (capture.get("horizons") or {}).values()))
    if not reached:
        out = {"status": NOT_RUN, "artifacts": {}, "references": {},
               "reason": "PRIMARY_RUN_DID_NOT_REACH_EVALUATION_IN_A_FORMAL_EXECUTION"}
    else:
        out = run_diagnostics_safely(capture, runtime_spec=run_kwargs["runtime_spec"], diag=diag, diag_sha=diag_sha,
                                     primary_sha=frozen["sha256"], harness_hashes=harness_hashes)
    references = {"schemaVersion": SCHEMA_VERSION, "status": out["status"], "diagnosticSpecSha256": diag_sha,
                  "primaryResultSha256": frozen["sha256"], "primaryResultFileSha256": _sha256(primary_bytes),
                  "artifacts": out["references"], "error": out.get("error"), "reason": out.get("reason"),
                  "authorizesRetry": False, "changesPrimary": False,
                  "firewall": "descriptive only; cannot gate, rescue, refute, select, tune or trigger a rerun"}
    return {"frozen": frozen, "primaryBytes": primary_bytes, "diagnosticArtifacts": out["artifacts"],
            "references": references, "referencesBytes": X.jsonable_bytes(references),
            "diagnosticStatus": out["status"]}


def _sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()
