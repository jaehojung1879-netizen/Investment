"""Experiment 1 (historical forecast comparison): which month-end information, added ONE family at a time to the
price/volatility baseline, made the 126-session first -15% SPY passage more or less predictable, 1998-2026.

This is an observational forecast comparison on outcome-exposed history. It reports accuracy, calibration and warning
quality; it computes NO p-value and makes no claim of conditional independence (the #365/#366 null-distribution work
showed no valid test exists for this sample). Every number is EXPLORATORY.

Models (each is M1 plus at most one candidate; no composite):

    M0  Jeffreys base rate of matured training labels
    M1  gap200, vol63                                   (baseline, unchanged from #365)
    M2  M1 + WIDEN_3M_ABOVE_EXPANDING_P80                (P1 flag, unchanged)
    M3  M1 + CREDIT_WIDEN_3M_Z  -- the same 3-month as-of BAA-GS10 change as the flag, standardised by the
         expanding mean/sd of all strictly earlier defined changes (>= 12), NOT thresholded (credit family)
    M4  M1 + VIX close / 100 at the decision close (option family): option-implied 30-day volatility given the
         trailing 63-session realised volatility. This is NOT a variance-risk-premium measure: a variance risk
         premium compares implied VARIANCE with the expected (forward) realised variance over the same 30 days,
         while M4 enters implied VOLATILITY and BACKWARD 63-session realised volatility as two free linear terms.
         M4 asks only whether the VIX level adds to M1.
    M5  M1 + VIX / VIX3M - 1 at the decision close (option family, term structure; VIX3M exists from 2007-12-04).
         Sample B holds only 4 episodes with positive rows (2018-12, 2020-03, 2022-05, 2025-04): the source starts
         2007-12 and 2008-01..2012-08 is inside an episode (DATA/HISTORY constraint). The real-time rule that
         training needs >= 2 matured episodes from the SAME sample then leaves 2 to evaluate (DESIGN constraint),
         which fails the structure gate, so M5 is reported DATA_INSUFFICIENT.

Samples (all models within a sample share rows, refit dates and training sets):

    A  month-ends from 1997-01-31, risk set, FAST = 0, gap/vol/flag/credit_z/vix defined     -> M0-M4
    B  as A and VIX3M defined                                                               -> M0-M5

Walk-forward, ridge 1.0, standardisation, evaluation-start rule and labels are stage2_design's, unchanged.
A WARNING is p_model >= 2 x p_M0 at the same decision (fixed before any outcome; identical for every model).
"""
from __future__ import annotations

import numpy as np

from . import stage2_design as D

FEATURES = ("gap", "vol", "flag", "credit_z", "vix", "vix_slope")
MODELS = {"M0": (), "M1": ("gap", "vol"), "M2": ("gap", "vol", "flag"), "M3": ("gap", "vol", "credit_z"),
          "M4": ("gap", "vol", "vix"), "M5": ("gap", "vol", "vix_slope")}
SAMPLES = {"A": {"requires": ("gap", "vol", "flag", "credit_z", "vix"), "models": ("M0", "M1", "M2", "M3", "M4")},
           "B": {"requires": FEATURES, "models": ("M0", "M1", "M2", "M3", "M4", "M5")}}
WARNING_MULTIPLE = 2.0
PERIOD_SPLIT_YEAR = 2013
CANDIDATES = ("M2", "M3", "M4", "M5")


class Panel:
    """Rows are dicts with idx, date, the FEATURES, y (1/0/None) and episode."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.idx = np.array([r["idx"] for r in rows], dtype=int)
        self.year = np.array([int(r["date"][:4]) for r in rows], dtype=int)
        self.X = {f: np.array([r[f] for r in rows], dtype=float) for f in FEATURES}
        self.y = np.array([np.nan if r["y"] is None else float(r["y"]) for r in rows])
        self.episode = np.array([r["episode"] or "" for r in rows], dtype=object)
        self.labelled = ~np.isnan(self.y)


def sample_rows(rows: list[dict], sample: str) -> list[dict]:
    need = SAMPLES[sample]["requires"]
    return [r for r in rows if all(r[f] is not None and np.isfinite(r[f]) for f in need)]


def fit_predict(p: Panel, tr: np.ndarray, te: np.ndarray, model: str) -> np.ndarray:
    ytr = p.y[tr]
    cols = MODELS[model]
    if not cols:
        return np.full(int(te.sum()), (ytr.sum() + 0.5) / (len(ytr) + 1.0))
    a = np.column_stack([p.X[c][tr] for c in cols])
    b = np.column_stack([p.X[c][te] for c in cols])
    mean, sd = a.mean(axis=0), a.std(axis=0)
    safe = np.where(sd > 0, sd, 1.0)
    za = np.where(sd > 0, (a - mean) / safe, 0.0)
    zb = np.where(sd > 0, (b - mean) / safe, 0.0)
    beta = D.ridge_logit(np.column_stack([np.ones(len(za)), za]), ytr, D.RIDGE_LAMBDA)
    return 1.0 / (1.0 + np.exp(-np.clip(np.column_stack([np.ones(len(zb)), zb]) @ beta, -35, 35)))


def matured(p: Panel, at_idx: int) -> np.ndarray:
    return p.labelled & (p.idx + D.HORIZON <= at_idx)


def evaluation_start(p: Panel, refits: dict[int, int]) -> int | None:
    for year in sorted(refits):
        m = matured(p, refits[year])
        if m.sum() >= D.MIN_TRAIN_ROWS and len({e for e in p.episode[m & (p.y == 1)]}) >= D.MIN_TRAIN_EPISODES:
            return year
    return None


def walk_forward(p: Panel, refits, start, models) -> dict[str, np.ndarray]:
    ev = p.labelled & (p.year >= start)
    out = {m: np.full(len(p.rows), np.nan) for m in models}
    for year in sorted(set(p.year[ev])):
        tr = matured(p, refits[year])
        te = ev & (p.year == year)
        for m in models:
            out[m][te] = fit_predict(p, tr, te, m)
    return {m: v[ev] for m, v in out.items()}


def structure(p: Panel, refits) -> dict:
    start = evaluation_start(p, refits)
    if start is None:
        return {"pass": False, "reasons": ["NO_EVALUATION_START"], "start": None}
    ev = p.labelled & (p.year >= start)
    eps = sorted({e for e in p.episode[ev & (p.y == 1)]})
    tr = matured(p, refits[start])
    reasons = [r for r, bad in (("FEW_EVALUATION_EPISODES", len(eps) < D.MIN_EVAL_EPISODES),
                                ("FEW_EVALUATION_ROWS", ev.sum() < D.MIN_EVAL_ROWS)) if bad]
    return {"pass": not reasons, "reasons": reasons, "start": start, "rows": len(p.rows),
            "evaluationRows": int(ev.sum()), "evaluationPositiveRows": int(np.nansum(p.y[ev])),
            "evaluationEpisodes": eps, "independentEvaluationEpisodes": len(eps),
            "trainingEpisodesAtStart": sorted({e for e in p.episode[tr & (p.y == 1)]}),
            "firstRow": p.rows[0]["date"] if p.rows else None}


# ------------------------------------------------------------------ descriptive outputs (no p-values)


def warnings(preds: dict) -> dict[str, np.ndarray]:
    return {m: preds[m] >= WARNING_MULTIPLE * preds["M0"] for m in preds if m != "M0"}


def episode_table(p: Panel, ev: np.ndarray, warn: np.ndarray, starts: dict[str, int]) -> dict:
    rows = np.where(ev)[0]
    out = {}
    for e in sorted({e for e in p.episode[ev & (p.y == 1)]}):
        opp = [k for j, k in enumerate(rows) if p.episode[k] == e]
        first = next((k for k in opp if warn[list(rows).index(k)]), None)
        out[e] = {"opportunities": len(opp), "warned": first is not None,
                  "firstWarning": p.rows[first]["date"] if first is not None else None,
                  "leadSessions": int(starts[e] - p.idx[first]) if first is not None else None}
    return out


def spells(mask: np.ndarray) -> int:
    return int(np.sum(mask[1:] & ~mask[:-1]) + (1 if len(mask) and mask[0] else 0))


def evaluate_sample(p: Panel, refits, starts: dict[str, int], sample: str) -> dict:
    st = structure(p, refits)
    if not st["pass"]:
        return {"structure": st, "status": "DATA_INSUFFICIENT"}
    models = SAMPLES[sample]["models"]
    start = st["start"]
    ev = p.labelled & (p.year >= start)
    y = p.y[ev]
    preds = walk_forward(p, refits, start, models)
    warn = warnings(preds)
    brier = {m: float(D.brier(v, y).mean()) for m, v in preds.items()}
    out = {"structure": st, "status": "COMPUTED", "models": {}}
    halves = {"before": p.year[ev] < PERIOD_SPLIT_YEAR, "from": p.year[ev] >= PERIOD_SPLIT_YEAR}
    for m in models:
        bm = D.brier(preds[m], y)
        rec = {"brier": brier[m], "brierSkillVsM0": 1 - brier[m] / brier["M0"],
               "logLoss": float(D.logloss(preds[m], y).mean()), "calibration": D.calibration(preds[m], y),
               "brierByPeriod": {k: (float(bm[h].mean()) if h.any() else None) for k, h in halves.items()}}
        if m != "M0":
            w = warn[m]
            neg = y == 0
            rec["warnings"] = {"rate": float(w.mean()), "rateOnNegativeRows": float(w[neg].mean()) if neg.any() else None,
                               "falseAlarmRows": int((w & neg).sum()), "falseAlarmSpells": spells(w & neg),
                               "episodes": episode_table(p, ev, w, starts)}
            rec["warnings"]["missedEpisodes"] = [e for e, v in rec["warnings"]["episodes"].items() if not v["warned"]]
        if m in CANDIDATES or m == "M1":
            d = D.brier(preds["M1"], y) - bm
            rec["dBrierVsM1"] = float(d.mean())
            rec["dBrierVsM1ByPeriod"] = {k: (float(d[h].mean()) if h.any() else None) for k, h in halves.items()}
            rec["dBrierVsM1EpisodeExclusion"] = {e: float(d[p.episode[ev] != e].mean())
                                                 for e in st["evaluationEpisodes"]}
        out["models"][m] = rec
    for m in models:
        if m in CANDIDATES:
            r = out["models"][m]
            r["forecastImprovementObserved"] = bool(
                r["dBrierVsM1"] > 0 and all(v is not None and v > 0 for v in r["dBrierVsM1ByPeriod"].values())
                and all(v > 0 for v in r["dBrierVsM1EpisodeExclusion"].values()))
    out["note"] = ("descriptive only: positive rows are not independent crises; episode exclusion removes an "
                   "episode's positive rows on the evaluation side without refitting; no p-values")
    return out


def evaluate(rows: list[dict], refits, starts) -> dict:
    return {s: evaluate_sample(Panel(sample_rows(rows, s)), refits, starts, s) for s in SAMPLES}
