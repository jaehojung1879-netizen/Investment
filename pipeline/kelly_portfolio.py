"""Auditable constrained Fractional Kelly model portfolio.

The long-term alpha score is deliberately *not* treated as an expected return.
Expected excess returns come only from matured, point-in-time paper-ledger
outcomes.  When that history or the covariance sample is insufficient the
module returns an explicit shadow/fallback state and preserves the existing
inverse-downside-volatility portfolio.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from sklearn.covariance import LedoitWolf
except Exception:  # dependency absence is reported, never silently imputed
    LedoitWolf = None

try:  # scipy is already a transitive dependency of scikit-learn.
    from scipy.optimize import minimize
except Exception:  # pragma: no cover - exercised through fallback tests
    minimize = None


STATUSES = {
    "DISABLED", "SHADOW_INSUFFICIENT_HISTORY", "SHADOW_READY",
    "ACTIVE_PAPER", "ACTIVE_VALIDATED", "OPTIMIZATION_FAILED",
    "FALLBACK_RISK_WEIGHTED", "BLOCKED",
}


def load_json(path: str | Path | None, default):
    if not path:
        return default
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def load_jsonl(path: str | Path | None) -> list[dict]:
    if not path:
        return []
    try:
        return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return []


def _bucket(value: float | None, edges: list[float]) -> tuple[float, float] | None:
    if value is None or not np.isfinite(value):
        return None
    for lo, hi in zip(edges[:-1], edges[1:]):
        if lo <= value < hi or (value == edges[-1] and hi == edges[-1]):
            return float(lo), float(hi)
    return None


def _non_overlapping_dates(rows: list[dict], horizon: int) -> list[pd.Timestamp]:
    dates = sorted({pd.Timestamp(r["date"]).normalize() for r in rows if r.get("date")})
    chosen: list[pd.Timestamp] = []
    for date in dates:
        if not chosen or date >= chosen[-1] + pd.offsets.BDay(horizon):
            chosen.append(date)
    return chosen


def _effective_sample_size(rows: list[dict], horizon: int) -> tuple[int, int]:
    """Conservative count for overlapping horizons and same-day cross-sections."""
    non_overlap = _non_overlapping_dates(rows, horizon)
    if not non_overlap:
        return 0, 0
    counts = pd.Series([r.get("date") for r in rows]).value_counts()
    cross_section_credit = math.sqrt(max(1.0, float(counts.median())))
    effective = min(len(rows), int(math.floor(len(non_overlap) * cross_section_credit)))
    return max(1, effective), len(non_overlap)


def estimate_expected_returns(candidates: list[dict], outcomes: list[dict],
                              cfg: dict, as_of: str | pd.Timestamp | None = None) -> list[dict]:
    """Estimate cost-adjusted 126d excess returns from matured OOS outcomes.

    Candidate alpha percentiles are used only to select a historical calibration
    bucket; the alpha score itself never enters a return formula.
    """
    horizon = int(cfg.get("horizonDays", 126))
    edges = [float(x) for x in cfg.get("alphaPercentileBuckets", [0, 60, 80, 90, 95, 100])]
    min_eff = int(cfg.get("minEffectiveObservations", 30))
    min_dates = int(cfg.get("minNonOverlappingDates", 12))
    prior_strength = float(cfg.get("shrinkagePriorStrength", min_eff))
    cutoff = pd.Timestamp(as_of).normalize() if as_of is not None else pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()

    matured = []
    for row in outcomes:
        h = (row.get("horizons") or {}).get(str(horizon))
        if not h or h.get("excessReturn") is None or row.get("date") is None:
            continue
        # A stored outcome is still ignored if it would not have matured by the
        # requested as-of date. This makes look-ahead impossible in replays.
        if pd.Timestamp(row["date"]).normalize() + pd.offsets.BDay(horizon) > cutoff:
            continue
        pct = row.get("alphaPercentile")
        if pct is None:
            continue
        enriched = dict(row)
        enriched["_bucket"] = _bucket(float(pct), edges)
        enriched["_excess"] = float(h["excessReturn"])
        matured.append(enriched)

    result = []
    for candidate in candidates:
        target = _bucket(candidate.get("alphaPercentile"), edges)
        region = candidate.get("region") or "UNKNOWN"
        same_region = [r for r in matured if (r.get("region") or "UNKNOWN") == region and r.get("_bucket")]
        rows = [r for r in same_region if r["_bucket"] == target] if target else []
        level = "REGION_ALPHA_BUCKET"

        # Merge adjacent buckets only when the exact bucket is thin. The
        # expansion order is deterministic and remains within the same region.
        if len(rows) < min_eff and target:
            centers = sorted({b for b in (_bucket(r.get("alphaPercentile"), edges) for r in same_region) if b},
                             key=lambda b: abs(((b[0] + b[1]) / 2) - ((target[0] + target[1]) / 2)))
            rows = []
            for b in centers:
                rows.extend(r for r in same_region if r["_bucket"] == b)
                eff, ndates = _effective_sample_size(rows, horizon)
                if eff >= min_eff and ndates >= min_dates:
                    break
            level = "REGION_MERGED_ALPHA_BUCKETS"

        eff, ndates = _effective_sample_size(rows, horizon)
        raw = float(np.mean([r["_excess"] for r in rows])) if rows else 0.0
        cost = float((cfg.get("costHaircut") or {}).get(region, 0.0))
        net = raw - cost
        shrink = eff / (eff + prior_strength) if eff else 0.0
        sufficient = eff >= min_eff and ndates >= min_dates
        expected = net * shrink if sufficient else 0.0

        # Recent deterioration receives a transparent 25% haircut, never a boost.
        haircut = 1.0
        if sufficient and len(rows) >= 8:
            ordered = sorted(rows, key=lambda r: r.get("date") or "")
            split = max(1, len(ordered) // 2)
            old_mean = float(np.mean([r["_excess"] for r in ordered[:split]]))
            recent_mean = float(np.mean([r["_excess"] for r in ordered[split:]]))
            if expected > 0 and recent_mean < old_mean:
                haircut = 0.75
                expected *= haircut

        lo, hi = target or (None, None)
        result.append({
            "ticker": candidate["ticker"], "horizonDays": horizon,
            "expectedExcessReturnPct": round(expected * 100, 3),
            "rawObservedExcessReturnPct": round(raw * 100, 3),
            "costHaircutPct": round(cost * 100, 3),
            "recentPerformanceHaircut": haircut,
            "shrinkageFactor": round(shrink, 4),
            "effectiveSampleSize": eff, "nonOverlappingDates": ndates,
            "alphaPercentileBucket": f"{lo:g}-{hi:g}" if lo is not None else None,
            "estimationLevel": level if rows else "NO_MATURED_REGION_HISTORY",
            "status": "SHADOW" if sufficient else "SHADOW_INSUFFICIENT_HISTORY",
        })
    return result


def estimate_covariance(prices: dict, tickers: list[str], cfg: dict) -> tuple[pd.DataFrame | None, dict]:
    """Ledoit-Wolf annualized covariance on a common daily-return window."""
    lookback = int(cfg.get("covarianceLookbackDays", 504))
    minimum = int(cfg.get("covarianceMinDays", 252))
    series = {}
    for ticker in tickers:
        frame = prices.get(ticker)
        if frame is not None and "Close" in frame:
            s = frame["Close"].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
            if len(s) >= minimum + 1:
                series[ticker] = s.pct_change(fill_method=None)
    if len(series) < 2:
        return None, {"status": "INSUFFICIENT", "reason": "fewer_than_two_price_series", "observations": 0}
    panel = pd.concat(series, axis=1, join="inner").dropna().tail(lookback)
    if len(panel) < minimum:
        return None, {"status": "INSUFFICIENT", "reason": "common_return_history_below_minimum", "observations": len(panel)}
    try:
        if cfg.get("useLedoitWolf", True):
            if LedoitWolf is None:
                return None, {"status": "FAILED", "reason": "ledoit_wolf_dependency_unavailable",
                              "observations": len(panel)}
            estimator = LedoitWolf().fit(panel.to_numpy(dtype=float))
            matrix = estimator.covariance_ * 252.0
            shrinkage = float(estimator.shrinkage_)
            method = "LEDOIT_WOLF"
        else:
            matrix = panel.cov().to_numpy(dtype=float) * 252.0
            shrinkage = None
            method = "SAMPLE"
        matrix = (matrix + matrix.T) / 2
        eigen_min = float(np.linalg.eigvalsh(matrix).min())
        if eigen_min < 0:
            matrix += np.eye(len(matrix)) * (-eigen_min + 1e-12)
        cov = pd.DataFrame(matrix, index=panel.columns, columns=panel.columns)
        return cov, {"status": "READY", "method": method, "observations": len(panel),
                     "lookbackDays": lookback, "shrinkage": shrinkage,
                     "minEigenvalue": round(float(np.linalg.eigvalsh(matrix).min()), 12)}
    except Exception as exc:
        return None, {"status": "FAILED", "reason": f"covariance_error:{exc.__class__.__name__}", "observations": len(panel)}


def _exposures(weights: pd.Series, candidates: list[dict], themes: dict) -> tuple[dict, dict, dict]:
    by_ticker = {c["ticker"]: c for c in candidates}
    sector: dict[str, float] = {}
    theme: dict[str, float] = {}
    region: dict[str, float] = {}
    for ticker, weight in weights.items():
        if weight <= 0:
            continue
        c = by_ticker[ticker]
        sec = c.get("sector") or "Unclassified"
        reg = c.get("region") or "UNKNOWN"
        sector[sec] = sector.get(sec, 0.0) + float(weight)
        region[reg] = region.get(reg, 0.0) + float(weight)
        labels = themes.get(ticker) or ["Unclassified"]
        for label in labels:
            theme[label] = theme.get(label, 0.0) + float(weight)
    return sector, theme, region


def _state_multiplier(candidate: dict, cfg: dict) -> float:
    if candidate.get("dataInsufficient") or candidate.get("valueTrap"):
        return 0.0
    if candidate.get("longTermResearchView") != "POSITIVE":
        return 0.0
    state = ((candidate.get("entry") or {}).get("entryState") or candidate.get("entryState") or "WATCH")
    if state in {"EVENT_RISK", "AVOID"}:
        return 0.0
    if state == "WAIT_FOR_PULLBACK":
        return float(cfg.get("waitForPullbackWeightMultiplier", 0.25))
    if state == "WATCH":
        return float(cfg.get("watchWeightMultiplier", 0.5))
    return 1.0


def optimize_fractional_kelly(expected_returns: list[dict], covariance: pd.DataFrame,
                              candidates: list[dict], cfg: dict, applied_fraction: float,
                              themes: dict | None = None, prior_weights: dict | None = None) -> dict:
    """Solve the long-only constrained mean-variance Kelly approximation."""
    themes, prior_weights = themes or {}, prior_weights or {}
    er = {r["ticker"]: r for r in expected_returns}
    tickers = [c["ticker"] for c in candidates if c["ticker"] in covariance.index and c["ticker"] in er]
    max_names = int(cfg.get("maxNames", 12))
    tickers = sorted(tickers, key=lambda t: er[t].get("expectedExcessReturnPct") or 0, reverse=True)[:max_names]
    candidates = [next(c for c in candidates if c["ticker"] == t) for t in tickers]
    if len(tickers) < int(cfg.get("minNames", 6)):
        return {"ok": False, "reason": "eligible_names_below_minimum"}
    if minimize is None:
        return {"ok": False, "reason": "scipy_optimizer_unavailable"}

    cov = covariance.loc[tickers, tickers].to_numpy(dtype=float)
    horizon = float(cfg.get("horizonDays", 126))
    mu = np.array([(er[t].get("expectedExcessReturnPct") or 0.0) / 100.0 * (252.0 / horizon) for t in tickers])
    mu_eff = mu * float(applied_fraction)
    name_cap = float(cfg.get("maxPositionWeight", 0.10))
    budget = 1.0 - float(cfg.get("minCashPct", 10)) / 100.0
    sector_cap = float(cfg.get("maxSectorWeight", 0.25))
    theme_cap = float(cfg.get("maxThemeWeight", 0.20))
    region_caps = cfg.get("regionCaps") or {}
    turnover_cap = float(cfg.get("maxTurnoverPct", 25)) / 100.0
    penalty = float(cfg.get("turnoverPenalty", 0.002))
    risk_aversion = float(cfg.get("riskAversion", 1.0))
    prior = np.array([max(0.0, float(prior_weights.get(t, 0.0))) for t in tickers])
    has_prior = bool(prior_weights)

    multipliers = np.array([_state_multiplier(c, cfg) for c in candidates])
    bounds = [(0.0, name_cap * float(m)) for m in multipliers]
    if sum(hi for _, hi in bounds) <= 0:
        return {"ok": False, "reason": "no_entry_eligible_positive_names"}

    def objective(w):
        turnover = np.abs(w - prior).sum() if has_prior else 0.0
        return -(mu_eff @ w - 0.5 * risk_aversion * (w @ cov @ w) - penalty * turnover)

    constraints = [{"type": "ineq", "fun": lambda w: budget - w.sum()}]
    sectors = sorted({c.get("sector") or "Unclassified" for c in candidates})
    for sector in sectors:
        idx = np.array([i for i, c in enumerate(candidates) if (c.get("sector") or "Unclassified") == sector])
        constraints.append({"type": "ineq", "fun": lambda w, idx=idx: sector_cap - w[idx].sum()})
    theme_labels = sorted({label for c in candidates for label in (themes.get(c["ticker"]) or ["Unclassified"])
                           if label != "Unclassified"})
    for label in theme_labels:
        idx = np.array([i for i, c in enumerate(candidates) if label in (themes.get(c["ticker"]) or ["Unclassified"])])
        constraints.append({"type": "ineq", "fun": lambda w, idx=idx: theme_cap - w[idx].sum()})
    for region, cap in region_caps.items():
        idx = np.array([i for i, c in enumerate(candidates) if c.get("region") == region])
        if len(idx):
            constraints.append({"type": "ineq", "fun": lambda w, idx=idx, cap=float(cap): cap - w[idx].sum()})
    if has_prior:
        constraints.append({"type": "ineq", "fun": lambda w: turnover_cap * 2.0 - np.abs(w - prior).sum()})

    inv = np.divide(1.0, np.sqrt(np.maximum(np.diag(cov), 1e-10)))
    x0 = inv / inv.sum() * min(budget, sum(hi for _, hi in bounds))
    x0 = np.minimum(x0, np.array([hi for _, hi in bounds]))
    result = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=constraints,
                      options={"maxiter": 1000, "ftol": 1e-11})
    if not result.success or not np.all(np.isfinite(result.x)):
        return {"ok": False, "reason": "optimization_failed", "detail": str(result.message)[:160]}

    weights = pd.Series(np.maximum(result.x, 0.0), index=tickers)
    try:
        raw = np.linalg.pinv(cov) @ mu
        raw = pd.Series(np.maximum(raw, 0.0) * float(applied_fracti￿m÷¶Ëkºwµçâu¶÷fW%ÒææFW¢u¶÷fW%ÒÒæÖUö6 ¢w&÷W÷7V72Ò°¢%4T5Dõ%ô4"ÂfÆöB6frævWB&Ö6V7F÷%vVvB"Âã#RÂÆÖ&F3¢¶2ævWB'6V7F÷""÷"%Væ6Æ76fVB%ÒÀ¢%DTÔUô4"ÂfÆöB6frævWB&ÖFVÖUvVvB"Âã#ÂÆÖ&F3¢FVÖW2ævWB5²'F6¶W"%Ò÷"²%Væ6Æ76fVB%ÒÀ¢%$Ttôåô4"ÂæöæRÂÆÖ&F3¢¶2ævWB'&Vvöâ"÷"%Tä´äõtâ%ÒÀ¢Ð¢'÷F6¶W"Ò¶5²'F6¶W"%Ó¢2f÷"2â6æFFFW7Ð¢f÷"òâ&ævRB ¢f÷"&VfÂfVEö6ÂÆ&VÇ5öfââw&÷W÷7V73 ¢w&÷W3¢F7E·7G"ÂÆ7E·7G%ÕÒÒ·Ð¢f÷"F6¶W"ârææFW ¢f÷"Æ&VÂâÆ&VÇ5öfâ'÷F6¶W%·F6¶W%Ò ¢w&÷W2ç6WFFVfVÇBÆ&VÂÂµÒæVæBF6¶W"¢f÷"Æ&VÂÂæÖW2âw&÷W2æFV×2 ¢b&VfÓÒ%DTÔUô4"æBÆ&VÂÓÒ%Væ6Æ76fVB# ¢6öçFçVP¢6ÒfVEö6 ¢b&VfÓÒ%$Ttôåô4# ¢6ÒfÆöB6frævWB'&Vvöä62"÷"·ÒævWBÆ&VÂÂã¢F÷FÂÒfÆöBu¶æÖW5Òç7VÒ¢b62æ÷BæöæRæBF÷FÂâ6²RÓ ¢u¶æÖW5Ò£Ò6òF÷FÀ¢¶WÒb'·&VfÓ§¶Æ&VÇÒ ¢b¶Wæ÷Bâ&æFæw3 ¢&æFæw2æVæB¶W¢'VFvWBÒãÒfÆöB6frævWB&Öä667B"Âòã ¢brç7VÒâ'VFvWC ¢r£Ò'VFvWBòfÆöBrç7VÒ¢&æFæw2æVæB$Ôåô44"¢&WGW&ârÂ&æFæw0  ¦FVb&ÆVæE÷vF÷&6µ÷vVvFVE÷÷'FföÆò&6µ÷vVvG3¢F7BÂ¶VÆÇ÷vVvG3¢F7BÀ¢6æFFFW3¢Æ7E¶F7EÒÂ6fs¢F7BÀ¢FVÖW3¢F7BÂæöæRÒæöæRÀ¢&÷%÷vVvG3¢F7BÂæöæRÒæöæRÓâF7C ¢FVÖW2Â&÷%÷vVvG2ÒFVÖW2÷"·ÒÂ&÷%÷vVvG2÷"·Ð¢F6¶W'2Ò¶5²'F6¶W"%Òf÷"2â6æFFFW5Ð¢&6²ÒBå6W&W2·C¢fÆöB&6µ÷vVvG2ævWBBÂãf÷"BâF6¶W'7Ò¢¶VÆÇÒBå6W&W2·C¢fÆöB¶VÆÇ÷vVvG2ævWBBÂãf÷"BâF6¶W'7Ò¢&ÆVæBÒfÆöB6frævWB&&ÆVæEvVvB"Âã#R¢6öÖ&æVBÒãÒ&ÆVæB¢&6²²&ÆVæB¢¶VÆÇ¢6öÖ&æVBÂ&æFæw2Òö6÷÷'FföÆò6öÖ&æVBÂ6æFFFW2Â6frÂFVÖW2 ¢b&÷%÷vVvG3 ¢&÷"ÒBå6W&W2·C¢fÆöB&÷%÷vVvG2ævWBBÂãf÷"BâF6¶W'7Ò¢GW&æ÷fW"ÒãR¢fÆöB6öÖ&æVBÒ&÷"æ'2ç7VÒ¢6ÒfÆöB6frævWB&ÖGW&æ÷fW%7B"Â#Ròã ¢bGW&æ÷fW"â6æBGW&æ÷fW"â ¢6öÖ&æVBÒ&÷"²6öÖ&æVBÒ&÷"¢6òGW&æ÷fW"¢6öÖ&æVBÂÖ÷&RÒö6÷÷'FföÆò6öÖ&æVBÂ6æFFFW2Â6frÂFVÖW2¢&æFæw2æWFVæBf÷"âÖ÷&Rbæ÷Bâ&æFæw2¢&æFæw2æVæB%EU$äõdU%ô4"¢&WGW&â²'vVvG2#¢6öÖ&æVBÂ&&æFæt6öç7G&çG2#¢&æFæw7Ð  ¦FVbö6æFFFU÷&÷w2Æöæu÷FW&Ó¢F7BÂæöæRÓâÆ7E¶F7EÓ ¢&÷w3¢Æ7E¶F7EÒÒµÐ¢f÷"&VvöâÂ&Æö"âÆöæu÷FW&Ò÷"·ÒævWB'&Vvöç2"÷"·ÒæFV×2 ¢6÷W&6RÒ&Æö"÷"·ÒævWB'6·2"÷"µÐ¢f÷"&÷râ6÷W&6S ¢FVÒÒF7B&÷r¢FVÕ²'&Vvöâ%ÒÒFVÒævWB'&Vvöâ"÷"&Vvöà¢&÷w2æVæBFVÒ¢&WGW&â&÷w0  ¦FVb÷&6µ÷vVvG26æFFFW3¢Æ7E¶F7EÒÂ6fs¢F7BÓâF7C ¢&rÒ¶5²'F6¶W"%Ó¢ÖãÂfÆöB2ævWB&ÖöFVÅ6ÆVWfUvVvE7B"÷"ãòãf÷"2â6æFFFW7Ð¢F÷FÂÒ7VÒ&rçfÇVW2¢'VFvWBÒãÒfÆöB6frævWB&Öä667B"Âòã ¢bF÷FÂâ ¢&rÒ·C¢ròF÷FÂ¢'VFvWBf÷"BÂrâ&ræFV×2Ð¢6VBÂòÒö6÷÷'FföÆòBå6W&W2&rÂGGSÖfÆöBÂ6æFFFW2Â6frÂ·Ò¢&WGW&â6VBçFõöF7B  ¦FVb÷&VvÖUöF§W7FÖVçBÖ7&õ÷&VvÖS¢F7BÂæöæRÂ6fs¢F7BÓâGWÆU·7G"ÂfÆöBÂfÆöBÂÆ7E·7G%ÕÓ ¢Ö7&õ÷&VvÖRÒÖ7&õ÷&VvÖR÷"·Ð¢Æ&VÂÒÖ7&õ÷&VvÖRævWB'&VvÖR"÷"%G&ç6FöâôÆ÷r6öæfFVæ6R ¢ÖærÒ6frævWB'&VvÖT×VÇFÆW'2"÷"·Ð¢&÷rÒÖærævWBÆ&VÂ÷"ÖærævWB%G&ç6FöâôÆ÷r6öæfFVæ6R"÷"·Ð¢×VÇFÆW"ÒfÆöB&÷rævWB&¶VÆÇ×VÇFÆW""ÂãR¢v&ææw2ÒµÐ¢6öæfFVæ6RÒÖ7&õ÷&VvÖRævWB&6öæfFVæ6R"¢b6öæfFVæ6R2æ÷BæöæRæBfÆöB6öæfFVæ6RÂãS ¢×VÇFÆW"£ÒÖãRÂfÆöB6öæfFVæ6RòãR¢v&ææw2æVæB$ÄõuôÔ5$õô4ôädDTä4Uô´TÄÅô$5UB"¢&WGW&âÆ&VÂÂ×VÇFÆW"ÂfÆöB&÷rævWB&Öä667B"Â6frævWB&Öä667B"ÂÂv&ææw0  ¦FVb'VÆEöÖöFVÅ÷÷'FföÆòÆöæu÷FW&Ó¢F7BÂæöæRÂ&6W3¢F7BÂ÷WF6öÖW3¢Æ7E¶F7EÒÀ¢6fs¢F7BÂæöæRÒæöæRÂÖ7&õ÷&VvÖS¢F7BÂæöæRÒæöæRÀ¢FVÖW3¢F7BÂæöæRÒæöæRÂ&÷%÷vVvG3¢F7BÂæöæRÒæöæRÀ¢5ööc¢7G"ÂæöæRÒæöæRÂ&Æö6¶VC¢&ööÂÒfÇ6RÀ¢fÆFFöå÷7FGW3¢F7BÂæöæRÒæöæRÓâF7C ¢""%F÷ÖÆWfVÂ76VÖ&Çg&öÒ6Æ'&FVB&WGW&ç2F&÷VvfæÂ&ÆVæFVBvVvG2â"" ¢6frÂFVÖW2Â&÷%÷vVvG2Ò6fr÷"·ÒÂFVÖW2÷"·ÒÂ&÷%÷vVvG2÷"·Ð¢fÆFFöå÷7FGW2ÒfÆFFöå÷7FGW2÷"·Ð¢&6RÒfÆöB6frævWB&¶VÆÇg&7Föâ"Âã#R¢&ÆVæBÒfÆöB6frævWB&&ÆVæEvVvB"Âã#R¢Æ&VÂÂ&VvÖUö×VÇBÂ&VvÖUö66Âv&ææw2Ò÷&VvÖUöF§W7FÖVçBÖ7&õ÷&VvÖRÂ6fr¢Æö6Åö6frÒF7B6fr¢Æö6Åö6fu²&Öä667B%ÒÒÖfÆöB6frævWB&Öä667B"ÂÂ&VvÖUö66¢ÆVBÒ&6R¢&VvÖUö×VÇ@¢6¶VÆWFöâÒ°¢'7FGW2#¢%4Dõuôå5Tdd4TåEô5Dõ%"Â&ÖWFöB#¢$$ÄTäDTEô4ôå5E$äTEôe$5DôäÅô´TÄÅ"À¢&÷&¦öäF2#¢çB6frævWB&÷&¦öäF2"Â#bÂ&&6T¶VÆÇg&7Föâ#¢&6RÀ¢'&VvÖR#¢Æ&VÂÂ'&VvÖT×VÇFÆW"#¢&÷VæB&VvÖUö×VÇBÂBÀ¢&ÆVD¶VÆÇg&7Föâ#¢&÷VæBÆVBÂBÂ&¶VÆÇ&ÆVæEvVvB#¢&ÆVæBÀ¢'&6µvVvFVD&ÆVæEvVvB#¢ãÒ&ÆVæBÂ&667B#¢ãÀ¢&WV7FVEföÅ7B#¢æöæRÂ&W7FÖFVDÖG&vF÷vå7B#¢æöæRÂ'GW&æ÷fW%7B#¢ãÀ¢&WV7FVE&WGW&å7FGW2#¢$å5Tdd4TåB"Â&fÆÆ&6µ&V6öâ#¢æöæRÀ¢'÷6Föç2#¢µÒÂ'&6µvVvFVEvVvG2#¢·ÒÂ&6öç7G&æVD¶VÆÇvVvG2#¢·ÒÀ¢&fæÅvVvG2#¢·ÒÂ'6V7F÷$W÷7W&R#¢·ÒÂ'FVÖTW÷7W&R#¢·ÒÂ'&VvöäW÷7W&R#¢·ÒÀ¢&6öç7G&çG2#¢¶³¢Æö6Åö6frævWB²f÷"²â&Ö÷6FöåvVvB"Â&Ö6V7F÷%vVvB"Â&ÖFVÖUvVvB"Â&Öä667B"Â&ÖGW&æ÷fW%7B"Â&ÖäæÖW2"Â&ÖæÖW2"Â'&Vvöä62"ÒÀ¢'v&ææw2#¢v&ææw2Â'fÆFFöâ#¢²&VÆv&ÆTf÷$7FfFöâ#¢fÇ6WÒÀ¢Ð¢bæ÷B6frævWB&Væ&ÆVB"ÂG'VR ¢6¶VÆWFöå²'7FGW2%ÒÒ$D4$ÄTB ¢&WGW&â6¶VÆWFöà¢b&Æö6¶VC ¢6¶VÆWFöå²'7FGW2%ÒÒ$$Äô4´TB ¢6¶VÆWFöå²'v&ææw2%ÒæVæB%$T4ôÔÔTäDDôå5ô$Äô4´TC²tTtE5õtDTÄB"¢&WGW&â6¶VÆWFöà ¢6æFFFW2Òö6æFFFU÷&÷w2Æöæu÷FW&Ò¢bÆVâ6æFFFW2ÂçBÆö6Åö6frævWB&ÖäæÖW2"Âb ¢6¶VÆWFöå²&fÆÆ&6µ&V6öâ%ÒÒ&ÆöæwFW&Õö6æFFFW5ö&VÆ÷uöÖæ×VÒ ¢&WGW&â6¶VÆWFöà¢&6µ÷vVvG2Ò÷&6µ÷vVvG26æFFFW2ÂÆö6Åö6fr¢W7FÖFW2ÒW7FÖFUöWV7FVE÷&WGW&ç26æFFFW2Â÷WF6öÖW2ÂÆö6Åö6frÂ5ööcÖ5ööb¢W7FÖFUöÖÒ¶U²'F6¶W"%Ó¢Rf÷"RâW7FÖFW7Ð¢7Vff6VçBÒ¶Rf÷"RâW7FÖFW2bU²'7FGW2%ÒÓÒ%4Dõr%Ð¢6÷bÂ6÷eöÖWFÒW7FÖFUö6÷f&æ6R&6W2Â¶5²'F6¶W"%Òf÷"2â6æFFFW5ÒÂÆö6Åö6fr¢6¶VÆWFöå²&6÷f&æ6R%ÒÒ6÷eöÖWF¢6¶VÆWFöå²&WV7FVE&WGW&äW7FÖFW2%ÒÒW7FÖFW0 ¢fÆÆ&6µ÷&V6öâÒæöæP¢Væ6öç7G&æVC¢F7E·7G"ÂfÆöEÒÒ·Ð¢¶VÆÇ÷vVvG3¢F7E·7G"ÂfÆöEÒÒ·Ð¢bÆVâ7Vff6VçBÂçBÆö6Åö6frævWB&ÖäæÖW2"Âb ¢fÆÆ&6µ÷&V6öâÒ&WV7FVE÷&WGW&åö7F÷'öç7Vff6VçB ¢VÆb6÷b2æöæS ¢fÆÆ&6µ÷&V6öâÒ6÷eöÖWFævWB'&V6öâ"÷"&6÷f&æ6U÷VæfÆ&ÆR ¢VÇ6S ¢÷FÖ¦VBÒ÷FÖ¦Uög&7FöæÅö¶VÆÇW7FÖFW2Â6÷bÂ6æFFFW2ÂÆö6Åö6frÂÆVBÀ¢FVÖW3×FVÖW2Â&÷%÷vVvG3×&÷%÷vVvG2¢bæ÷B÷FÖ¦VBævWB&ö²" ¢6¶VÆWFöå²'7FGW2%ÒÒ$õDÔ¤DôåôdÄTB ¢fÆÆ&6µ÷&V6öâÒ÷FÖ¦VBævWB'&V6öâ"÷"&÷FÖ¦FöåöfÆVB ¢6¶VÆWFöå²'v&ææw2%ÒæVæBb$õDÔ¤U#§¶fÆÆ&6µ÷&V6öçÒ"¢VÇ6S ¢¶VÆÇ÷vVvG2Ò÷FÖ¦VE²'vVvG2%ÒçFõöF7B¢Væ6öç7G&æVBÒ÷FÖ¦VE²'Væ6öç7G&æVEvVvG2%ÒçFõöF7B¢6¶VÆWFöå²&÷FÖ¦Föâ%ÒÒ²&ö&¦V7FfR#¢÷FÖ¦VE²&ö&¦V7FfR%ÒÂ&FW&Föç2#¢÷FÖ¦VE²&FW&Föç2%×Ð ¢bfÆÆ&6µ÷&V6öã ¢fæÂÒBå6W&W2&6µ÷vVvG2ÂGGSÖfÆöB¢fæÂÂ&æFæw2Òö6÷÷'FföÆòfæÂÂ6æFFFW2ÂÆö6Åö6frÂFVÖW2¢6¶VÆWFöå²&fÆÆ&6µ&V6öâ%ÒÒfÆÆ&6µ÷&V6öà¢6¶VÆWFöå²'v&ææw2%ÒæVæB$´TÄÅôäõEô5DdDTC²U5Däuõ$4µõtTtDTEõõ%DdôÄõõ$UDäTB"¢VÇ6S ¢&ÆVæFVBÒ&ÆVæE÷vF÷&6µ÷vVvFVE÷÷'FföÆò&6µ÷vVvG2Â¶VÆÇ÷vVvG2Â6æFFFW2À¢Æö6Åö6frÂFVÖW2Â&÷%÷vVvG2¢fæÂÂ&æFæw2Ò&ÆVæFVE²'vVvG2%ÒÂ&ÆVæFVE²&&æFæt6öç7G&çG2%Ð¢6¶VÆWFöå²'7FGW2%ÒÒ%4Dõuõ$TE"b6frævWB&ÖöFR"Â'6F÷r"ÓÒ'6F÷r"VÇ6R$5DdUõU" ¢6¶VÆWFöå²&WV7FVE&WGW&å7FGW2%ÒÒ%4Dõr  ¢6V7F÷%öWÂFVÖUöWÂ&VvöåöWÒöW÷7W&W2fæÂÂ6æFFFW2ÂFVÖW2¢&÷"ÒBå6W&W2·C¢fÆöB&÷%÷vVvG2ævWBBÂãf÷"BâfæÂææFWÒ¢GW&æ÷fW"ÒãR¢fÆöBfæÂÒ&÷"æ'2ç7VÒb&÷%÷vVvG2VÇ6RfÆöBfæÂç7VÒ¢÷6Föç2ÒµÐ¢f÷"6æFFFRâ6æFFFW3 ¢F6¶W"Ò6æFFFU²'F6¶W"%Ð¢WÒW7FÖFUöÖævWBF6¶W"Â·Ò¢rÒfÆöBfæÂævWBF6¶W"Âã¢÷6Föåö&æFæw2Ò¶"f÷""â&æFæw2b"æVæG7vFb#§·F6¶W'Ò"÷ ¢"ç7F'G7vF%4T5Dõ%ô4¢"æB"ç7ÆB#¢"Â³ÒÓÒ6æFFFRævWB'6V7F÷""÷"%Væ6Æ76fVB"÷ ¢"ç7F'G7vF%$Ttôåô4¢"æB"ç7ÆB#¢"Â³ÒÓÒ6æFFFRævWB'&Vvöâ"÷ ¢"ç7F'G7vF%DTÔUô4¢"æB"ç7ÆB#¢"Â³ÒâFVÖW2ævWBF6¶W"÷"²%Væ6Æ76fVB%ÒÐ¢÷6Föç2æVæB°¢'F6¶W"#¢F6¶W"Â'&Vvöâ#¢6æFFFRævWB'&Vvöâ"Â'6V7F÷"#¢6æFFFRævWB'6V7F÷""÷"%Væ6Æ76fVB"À¢'FVÖW2#¢FVÖW2ævWBF6¶W"÷"²%Væ6Æ76fVB%ÒÂ&ÇW&6VçFÆR#¢6æFFFRævWB&ÇW&6VçFÆR"À¢&WV7FVDW6W75&WGW&å7B#¢WævWB&WV7FVDW6W75&WGW&å7B"À¢&WV7FVE&WGW&å6×ÆU6¦R#¢WævWB&VffV7FfU6×ÆU6¦R"ÂÀ¢&WV7FVE&WGW&å7FGW2#¢WævWB'7FGW2"À¢'&6´ÆWfVÂ#¢6æFFFRævWB'&6²"÷"·ÒævWB'föÃ#S%7B"À¢'&6µvVvFVEvVvE7B#¢&÷VæBfÆöB&6µ÷vVvG2ævWBF6¶W"Âã¢Â"À¢'Væ6öç7G&æVD¶VÆÇvVvE7B#¢&÷VæBfÆöBVæ6öç7G&æVBævWBF6¶W"Âã¢Â"À¢&6öç7G&æVD¶VÆÇvVvE7B#¢&÷VæBfÆöB¶VÆÇ÷vVvG2ævWBF6¶W"Âã¢Â"À¢&ÖöFVÅ÷'FföÆõvVvE7B#¢&÷VæBr¢Â"À¢&VçG'7FFR#¢6æFFFRævWB&VçG'"÷"·ÒævWB&VçG'7FFR"À¢&&æFæt6öç7G&çG2#¢÷6Föåö&æFæw2À¢Ò¢÷6Föç2ç6÷'B¶WÖÆÖ&F¢²&ÖöFVÅ÷'FföÆõvVvE7B%ÒÂ&WfW'6SÕG'VR¢6¶VÆWFöâçWFFR°¢&667B#¢&÷VæBãÒfÆöBfæÂç7VÒ¢Â"Â'GW&æ÷fW%7B#¢&÷VæBGW&æ÷fW"¢Â"À¢'÷6Föç2#¢÷6Föç2Â'&6µvVvFVEvVvG2#¢¶³¢&÷VæBbÂbf÷"²Âbâ&6µ÷vVvG2æFV×2ÒÀ¢&6öç7G&æVD¶VÆÇvVvG2#¢¶³¢&÷VæBbÂbf÷"²Âbâ¶VÆÇ÷vVvG2æFV×2ÒÀ¢&fæÅvVvG2#¢¶³¢&÷VæBfÆöBbÂbf÷"²ÂbâfæÂæFV×2ÒÀ¢'6V7F÷$W÷7W&R#¢¶³¢&÷VæBb¢Â"f÷"²Âbâ6V7F÷%öWæFV×2ÒÀ¢'FVÖTW÷7W&R#¢¶³¢&÷VæBb¢Â"f÷"²ÂbâFVÖUöWæFV×2ÒÀ¢'&VvöäW÷7W&R#¢¶³¢&÷VæBb¢Â"f÷"²Âbâ&VvöåöWæFV×2ÒÀ¢&&æFæt6öç7G&çG2#¢&æFæw2À¢Ò¢b6÷b2æ÷BæöæS ¢6öÖÖöâÒ·Bf÷"BâfæÂææFWbBâ6÷bææFWÐ¢'"ÒfæÂæÆö5¶6öÖÖöåÒçFõöçV×GGSÖfÆöB¢6¶VÆWFöå²&WV7FVEföÅ7B%ÒÒ&÷VæBfÆöBÖFç7'BÖãÂ'"6÷bæÆö5¶6öÖÖöâÂ6öÖÖöåÒçFõöçV×'"¢Â"¢27F÷&6ÂG&vF÷vâ2FW67&FfRæ÷Bf÷&V67BæBW6W2öæÇFP¢26ÖRFÇ6Æ÷6R7F÷'fÆ&ÆRBFR÷'FföÆò6Æ7VÆFöâFÖRà¢G' ¢&WGW&ç2ÒBæ6öæ6B·C¢&6W5·EÕ²$6Æ÷6R%Òç7Eö6ævRfÆÅöÖWFöCÔæöæR¢f÷"BâfæÂææFWbBâ&6W2æB$6Æ÷6R"â&6W5·E×ÒÀ¢3ÓÂ¦öãÒ&ææW""æG&÷æçFÂçBÆö6Åö6frævWB&6÷f&æ6TÆöö¶&6´F2"ÂSB¢6öÖÖöâÒ·Bf÷"BâfæÂææFWbBâ&WGW&ç2æ6öÇVÖç5Ð¢bÆVâ&WGW&ç2æB6öÖÖöã ¢FÒã²&WGW&ç5¶6öÖÖöåÒæ×VÂfæÂæÆö5¶6öÖÖöåÒÂ3Óç7VÒ3Óæ7V×&öB¢G&vF÷vâÒFòFæ7VÖÖÒã ¢6¶VÆWFöå²&W7FÖFVDÖG&vF÷vå7B%ÒÒ&÷VæBfÆöBG&vF÷vâæÖâ¢Â"¢W6WBW6WFöã ¢70¢F÷FÂÒfÆöBfæÂç7VÒ²6¶VÆWFöå²&667B%Òòã ¢65öö²Ò¢æ÷BÆVâfæÂ÷"fÆöBfæÂæÖÃÒfÆöBÆö6Åö6frævWB&Ö÷6FöåvVvB"Âã²RÓ¢æBÆÂbÃÒfÆöBÆö6Åö6frævWB&Ö6V7F÷%vVvB"Âã#R²RÓf÷"bâ6V7F÷%öWçfÇVW2¢æBÆÂÆ&VÂÓÒ%Væ6Æ76fVB"÷"bÃÒfÆöBÆö6Åö6frævWB&ÖFVÖUvVvB"Âã#²RÓ¢f÷"Æ&VÂÂbâFVÖUöWæFV×2¢æBÆÂbÃÒfÆöBÆö6Åö6frævWB'&Vvöä62"÷"·ÒævWBÆ&VÂÂã²RÓ¢f÷"Æ&VÂÂbâ&VvöåöWæFV×2¢¢7FfFöâÒÆö6Åö6frævWB&7FfFöâ"÷"·Ð¢&Vvöåö2ÒfÆFFöå÷7FGW2ævWB'&Vvöä2"÷"·Ð¢&æµö5÷÷6FfRÒ&ööÂ&Vvöåö2æBÆÂ&÷rævWB&ÖVâ"÷"âf÷"&÷râ&Vvöåö2çfÇVW2¢7FfFöåö6V6·2Ò°¢'W$F2#¢çBfÆFFöå÷7FGW2ævWB'W$F2"÷"ãÒçB7FfFöâævWB&ÖåW$F2"Â#S"À¢&ÖGW&VE6væÇ2#¢çBfÆFFöå÷7FGW2ævWB&ÖGW&VE6væÇ2"÷"ãÒçB7FfFöâævWB&ÖäÖGW&VE6væÇ2"ÂÀ¢'÷6FfT6÷7DF§W7FVDW6W72#¢fÆFFöå÷7FGW2ævWB&6÷7DF§W7FVDW6W75&WGW&â"÷"âÀ¢'÷6FfU&æ´2#¢&æµö5÷÷6FfRÀ¢&æôÖFDFWFW&÷&Föâ#¢fÆFFöå÷7FGW2ævWB&æôÖFDFWFW&÷&Föâ"2G'VRÀ¢&VÖä&÷fVB#¢fÇ6RÀ¢Ð¢&WV&VBÒ¶7FfFöåö6V6·5²'W$F2%ÒÂ7FfFöåö6V6·5²&ÖGW&VE6væÇ2%ÕÐ¢b7FfFöâævWB'&WV&U÷6FfT6÷7DF§W7FVDW6W72"ÂG'VR ¢&WV&VBæVæB7FfFöåö6V6·5²'÷6FfT6÷7DF§W7FVDW6W72%Ò¢b7FfFöâævWB'&WV&U÷6FfU&æ´2"ÂG'VR ¢&WV&VBæVæB7FfFöåö6V6·5²'÷6FfU&æ´2%Ò¢b7FfFöâævWB'&WV&TæôÖFDFWFW&÷&Föâ"ÂG'VR ¢&WV&VBæVæB7FfFöåö6V6·5²&æôÖFDFWFW&÷&Föâ%Ò¢6¶VÆWFöå²'fÆFFöâ%ÒÒ°¢'vVvG5ÇW4667B#¢&÷VæBF÷FÂ¢ÂbÀ¢&æöäæVvFfR#¢&ööÂfæÂãÒÓRÓ"æÆÂÀ¢&fæFR#¢&ööÂçæ6fæFRfæÂçFõöçV×æÆÂÀ¢&6öç7G&çG56F6fVB#¢&ööÂ65öö²æB'2F÷FÂÒãÃÒRÓbÀ¢&7FfFöä6V6·2#¢7FfFöåö6V6·2À¢&VÆv&ÆTf÷$7FfFöâ#¢&ööÂ&WV&VBæBÆÂ&WV&VBÀ¢&ÖçVÅ&WfWu&WV&VB#¢G'VRÀ¢Ð¢&WGW&â6¶VÆWFöà￿