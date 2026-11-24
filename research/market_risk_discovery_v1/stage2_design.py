"""Market Risk Discovery v1 -- Stage 2 frozen design for P1 (incremental pre-break warning).

This module is the single implementation of the P1 comparison. Stage 2 calls it with presence proxies or synthetic
signals (readiness, power, tests); the one-shot Stage 3 harness calls it with real values. It reads no file.

Question. At a US month-end decision where the existing price/volatility model reads "normal" (FAST = 0), does the
pre-selected real-time credit signal WIDEN_3M_ABOVE_EXPANDING_P80 add information about whether SPY total return makes
its first -15% passage within the next 126 sessions, over a model that already uses the continuous price information
inside the normal state (distance from the 200-session mean and 63-session realised volatility)?

Models (identical rows, identical refit dates, identical matured training set):

* M0  base rate of matured past labels, Jeffreys (k + 0.5) / (n + 1).
* M1  ridge logistic on [gap200, vol63], standardised on the training window.
* M2  ridge logistic on [gap200, vol63, credit flag], same standardisation rule and the same fixed penalty.

Walk-forward (PRIMARY): refit once a year at the first month-end session of the year, on common-sample rows whose
126-session label window ended on or before that session. An early-resolved positive is NOT used early (that would
tilt the training set towards positives). Evaluation starts in the first year whose training set has at least
MIN_TRAIN_ROWS rows and positives from at least MIN_TRAIN_EPISODES episodes.

Primary statistic: dBrier = mean(Brier_M1 - Brier_M2) over evaluation rows (positive = M2 better).
Primary null: circular rotation of the defined credit-flag sequence, every shift k with ROTATION_GUARD <= k <=
n - ROTATION_GUARD; M2 is refitted for each shift. It preserves the flag's persistence, the label process, the FAST
mask and M1 exactly and breaks only the flag-to-calendar alignment.
Gate beside the rotation p: dBrier stays positive with every single evaluation episode removed (evaluation side).
Reported, not gated: moving-block bootstrap interval of the per-row loss differences.
Secondary (not real time, descriptive): purged leave-one-episode-out cross-validation over all seven episodes.
Auxiliary (gate nothing): event hits, lead time, false alarms, log loss, calibration.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

HORIZON = 126
RIDGE_LAMBDA = 1.0
ROTATION_GUARD = 12
BLOCK_LENGTH = 12
BOOTSTRAP_DRAWS = 9999
BOOTSTRAP_SEED = 20261123
MIN_TRAIN_ROWS = 20
MIN_TRAIN_EPISODES = 2
MIN_EVAL_EPISODES = 3
MIN_EVAL_ROWS = 100
MIN_ROTATIONS = 100
ALPHA = 0.05
P_CLIP = 1e-6
CALIBRATION_EDGES = (0.0, 0.05, 0.10, 0.20, 0.40, 1.0)
MODELS = ("M0", "M1", "M2")
MODEL_COLUMNS = {"M1": (0, 1), "M2": (0, 1, 2)}   # columns of [gap, vol, flag]


@dataclass
class Row:
    """One common-sample month-end decision (FAST = 0, risk set, every input defined)."""
    idx: int             # session index of the decision close
    date: str
    gap: float           # close / SMA200 - 1 (price basis)
    vol: float           # 63-session realised vol, annualised (price basis)
    flag: float          # credit flag 0/1 (or a presence proxy / synthetic value)
    y: int | None        # 1 if a -15% first passage starts in (t, t+126], 0 if not, None if censored
    episode: str | None  # start date of that episode when y == 1


class Panel:
    def __init__(self, rows: list[Row]):
        self.rows = rows
        self.idx = np.array([r.idx for r in rows], dtype=int)
        self.year = np.array([int(r.date[:4]) for r in rows], dtype=int)
        self.X = np.array([[r.gap, r.vol, r.flag] for r in rows], dtype=float).reshape(len(rows), 3)
        self.y = np.array([np.nan if r.y is None else float(r.y) for r in rows])
        self.episode = np.array([r.episode or "" for r in rows], dtype=object)
        self.labelled = ~np.isnan(self.y)


# ------------------------------------------------------------------ estimators


def ridge_logit(X: np.ndarray, y: np.ndarray, lam: float = RIDGE_LAMBDA) -> np.ndarray:
    """Penalised logistic regression; column 0 is the (unpenalised) intercept. Newton to 1e-10."""
    k = X.shape[1]
    pen = np.full(k, lam)
    pen[0] = 1e-8
    beta = np.zeros(k)
    for _ in range(100):
        p = 1.0 / (1.0 + np.exp(-np.clip(X @ beta, -35, 35)))
        grad = X.T @ (p - y) + pen * beta
        hess = (X * (p * (1 - p))[:, None]).T @ X + np.diag(pen)
        step = np.linalg.solve(hess, grad)
        beta -= step
        if np.max(np.abs(step)) < 1e-10:
            break
    return beta


def fit_predict(Xtr: np.ndarray, ytr: np.ndarray, Xte: np.ndarray, model: str) -> np.ndarray:
    if model == "M0":
        return np.full(len(Xte), (ytr.sum() + 0.5) / (len(ytr) + 1.0))
    cols = list(MODEL_COLUMNS[model])
    a, b = Xtr[:, cols], Xte[:, cols]
    mean, sd = a.mean(axis=0), a.std(axis=0)
    safe = np.where(sd > 0, sd, 1.0)
    za = np.where(sd > 0, (a - mean) / safe, 0.0)
    zb = np.where(sd > 0, (b - mean) / safe, 0.0)
    beta = ridge_logit(np.column_stack([np.ones(len(za)), za]), ytr)
    eta = np.column_stack([np.ones(len(zb)), zb]) @ beta
    return 1.0 / (1.0 + np.exp(-np.clip(eta, -35, 35)))


def brier(p, y):
    return (p - y) ** 2


def logloss(p, y):
    q = np.clip(p, P_CLIP, 1 - P_CLIP)
    return -(y * np.log(q) + (1 - y) * np.log(1 - q))


# ------------------------------------------------------------------ walk-forward schedule


def refit_points(month_end_sessions: list[tuple[str, int]]) -> dict[int, int]:
    """Year -> session index of the first month-end of that year, from the calendar (not from the data rows)."""
    out: dict[int, int] = {}
    for date, idx in month_end_sessions:
        out[int(date[:4])] = min(out.get(int(date[:4]), idx), idx)
    return out


def matured_mask(p: Panel, at_idx: int) -> np.ndarray:
    return p.labelled & (p.idx + HORIZON <= at_idx)


def evaluation_start(p: Panel, refits: dict[int, int]) -> int | None:
    for year in sorted(refits):
        m = matured_mask(p, refits[year])
        eps = {e for e in p.episode[m & (p.y == 1)]}
        if m.sum() >= MIN_TRAIN_ROWS and len(eps) >= MIN_TRAIN_EPISODES:
            return year
    return None


def evaluation_mask(p: Panel, start: int) -> np.ndarray:
    return p.labelled & (p.year >= start)


def walk_forward(p: Panel, refits: dict[int, int], start: int, flags: np.ndarray | None = None,
                 models: tuple[str, ...] = MODELS) -> dict[str, np.ndarray]:
    """Predictions on the evaluation rows (in row order). `flags` replaces the flag column for every row."""
    X = p.X if flags is None else np.column_stack([p.X[:, :2], flags])
    ev = evaluation_mask(p, start)
    out = {m: np.full(len(p.rows), np.nan) for m in models}
    for year in sorted(set(p.year[ev])):
        tr = matured_mask(p, refits[year])
        te = ev & (p.year == year)
        for m in models:
            out[m][te] = fit_predict(X[tr], p.y[tr], X[te], m)
    return {m: v[ev] for m, v in out.items()}


def d_brier(preds: dict, y: np.ndarray) -> float:
    return float(np.mean(brier(preds["M1"], y) - brier(preds["M2"], y)))


def d_logloss(preds: dict, y: np.ndarray) -> float:
    return float(np.mean(logloss(preds["M1"], y) - logloss(preds["M2"], y)))


# ------------------------------------------------------------------ rotation null


def rotation_shifts(n: int, guard: int = ROTATION_GUARD) -> list[int]:
    return list(range(guard, n - guard + 1))


def sequence_positions(p: Panel, flag_sequence: list[tuple[int, float]]) -> tuple[np.ndarray, np.ndarray]:
    where = {i: j for j, (i, _) in enumerate(flag_sequence)}
    pos = np.array([where[i] for i in p.idx], dtype=int)
    vals = np.array([v for _, v in flag_sequence], dtype=float)
    return pos, vals


def rotated(pos: np.ndarray, vals: np.ndarray, k: int) -> np.ndarray:
    return vals[(pos + k) % len(vals)]


def rotation_null(p: Panel, refits, start, flag_sequence, stats: dict) -> dict[str, np.ndarray]:
    """Null draws of each statistic in `stats` (name -> f(preds, y)); M1 and M0 do not depend on the flag, so only M2
    is refitted per shift."""
    pos, vals = sequence_positions(p, flag_sequence)
    base = walk_forward(p, refits, start, models=("M0", "M1"))
    y = p.y[evaluation_mask(p, start)]
    draws = {name: [] for name in stats}
    for k in rotation_shifts(len(vals)):
        m2 = walk_forward(p, refits, start, rotated(pos, vals, k), models=("M2",))
        preds = {**base, **m2}
        for name, f in stats.items():
            draws[name].append(f(preds, y))
    return {name: np.array(v) for name, v in draws.items()}


def one_sided_p(draws: np.ndarray, observed: float) -> float:
    return float((1 + np.sum(draws >= observed - 1e-15)) / (1 + len(draws)))


# ------------------------------------------------------------------ corroboration


def block_bootstrap_ci(d: np.ndarray, length: int = BLOCK_LENGTH, draws: int = BOOTSTRAP_DRAWS,
                       seed: int = BOOTSTRAP_SEED) -> dict:
    n = len(d)
    rng = np.random.default_rng(seed)
    nb = math.ceil(n / length)
    starts = rng.integers(0, n - length + 1, size=(draws, nb))
    take = (starts[:, :, None] + np.arange(length)).reshape(draws, -1)[:, :n]
    means = d[take].mean(axis=1)
    return {"mean": float(d.mean()), "lo": float(np.quantile(means, 0.025)), "hi": float(np.quantile(means, 0.975)),
            "blockLength": length, "draws": draws, "seed": seed}


def leave_one_episode_out(d: np.ndarray, episodes: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """Evaluation-side only (no refit): mean loss difference with one episode's positive rows removed."""
    return {e: float(d[episodes != e].mean()) for e in sorted({e for e, v in zip(episodes, y) if v == 1})}


# ------------------------------------------------------------------ secondary: purged leave-one-episode-out CV


def episode_folds(p: Panel, starts: dict[str, int]) -> np.ndarray:
    """Fold of each labelled row = the first episode starting after it (rows after the last one form 'TAIL')."""
    s = sorted(starts.items(), key=lambda kv: kv[1])
    out = np.empty(len(p.rows), dtype=object)
    for i, t in enumerate(p.idx):
        out[i] = next((name for name, k in s if k > t), "TAIL")
    return out


def purged_cv(p: Panel, starts: dict[str, int], flags: np.ndarray | None = None,
              models: tuple[str, ...] = MODELS) -> dict[str, np.ndarray]:
    """NOT REAL TIME. Each fold is predicted by models trained on every other labelled row whose 126-session window
    does not overlap the fold's span (purge of HORIZON sessions on both sides)."""
    X = p.X if flags is None else np.column_stack([p.X[:, :2], flags])
    folds = episode_folds(p, starts)
    out = {m: np.full(len(p.rows), np.nan) for m in models}
    for f in sorted(set(folds[p.labelled])):
        te = p.labelled & (folds == f)
        lo, hi = p.idx[te].min(), p.idx[te].max()
        tr = p.labelled & (folds != f) & ((p.idx + HORIZON < lo) | (p.idx > hi + HORIZON))
        for m in models:
            out[m][te] = fit_predict(X[tr], p.y[tr], X[te], m)
    return {m: v[p.labelled] for m, v in out.items()}


# ------------------------------------------------------------------ auxiliary


def event_metrics(p: Panel, start: int, flags: np.ndarray, starts: dict[str, int]) -> dict:
    """Per evaluation episode: FAST-normal opportunities in its pre-window, whether the flag was on at any of them,
    and the lead (sessions) of the first flagged one. False-alarm share over flagged evaluation rows."""
    ev = evaluation_mask(p, start)
    out, hits = {}, 0
    for e in sorted({e for e in p.episode[ev & (p.y == 1)]}):
        opp = np.where(ev & (p.episode == e))[0]
        flagged = [i for i in opp if flags[i] >= 0.5]
        hits += bool(flagged)
        out[e] = {"opportunities": int(len(opp)), "flaggedOpportunities": len(flagged), "hit": bool(flagged),
                  "firstFlag": p.rows[flagged[0]].date if flagged else None,
                  "leadSessions": int(starts[e] - p.idx[flagged[0]]) if flagged else None}
    fl = ev & (flags >= 0.5)
    return {"episodes": out, "hits": hits, "evaluationEpisodes": len(out), "flaggedRows": int(fl.sum()),
            "falseAlarmShare": float(np.mean(p.y[fl] == 0)) if fl.any() else None,
            "flagRateOnNegatives": float(np.mean(flags[ev & (p.y == 0)])) if (ev & (p.y == 0)).any() else None}


def calibration(pr: np.ndarray, y: np.ndarray) -> dict:
    bins = []
    for lo, hi in zip(CALIBRATION_EDGES, CALIBRATION_EDGES[1:]):
        m = (pr >= lo) & ((pr < hi) if hi < 1 else (pr <= hi))
        bins.append({"range": [lo, hi], "n": int(m.sum()), "meanP": float(pr[m].mean()) if m.any() else None,
                     "observed": float(y[m].mean()) if m.any() else None})
    return {"meanP": float(pr.mean()), "observed": float(y.mean()), "bins": bins}


# ------------------------------------------------------------------ gate and verdict (frozen before any outcome)


VERDICTS = ("DATA_INSUFFICIENT", "EXPLORATORY_INCREMENTAL_SUPPORT", "DIRECTIONAL_NOT_SEPARATED",
            "NOT_DETECTED_UNDERPOWERED")


def structure_gate(p: Panel, refits: dict[int, int], flag_sequence) -> dict:
    """Outcome-free: depends on label definedness, the episode calendar and flag DEFINEDNESS only."""
    start = evaluation_start(p, refits)
    if start is None:
        return {"pass": False, "reasons": ["NO_EVALUATION_START"], "start": None}
    ev = evaluation_mask(p, start)
    eps = sorted({e for e in p.episode[ev & (p.y == 1)]})
    shifts = len(rotation_shifts(len(flag_sequence)))
    reasons = [r for r, bad in (("FEW_EVALUATION_EPISODES", len(eps) < MIN_EVAL_EPISODES),
                                ("FEW_EVALUATION_ROWS", ev.sum() < MIN_EVAL_ROWS),
                                ("FEW_ROTATIONS", shifts < MIN_ROTATIONS)) if bad]
    tr = matured_mask(p, refits[start])
    return {"pass": not reasons, "reasons": reasons, "start": start, "evaluationRows": int(ev.sum()),
            "evaluationPositives": int(np.nansum(p.y[ev])), "evaluationEpisodes": eps, "rotations": shifts,
            "trainingRowsAtStart": int(tr.sum()),
            "trainingEpisodesAtStart": sorted({e for e in p.episode[tr & (p.y == 1)]})}


def verdict(d: float, rot_p: float, loeo: dict) -> str:
    """Pre-outcome revision 1 (synthetic power only): the block-bootstrap lower bound is reported, not gated. With
    about 11 blocks over 5 evaluation episodes it passed 3.5% of null worlds and 35% of worlds with a planted
    relative risk of about 6.6, while rotation + leave-one-episode-out kept the null rate at 4.5%."""
    if d > 0 and rot_p <= ALPHA and all(v > 0 for v in loeo.values()):
        return "EXPLORATORY_INCREMENTAL_SUPPORT"
    if d > 0:
        return "DIRECTIONAL_NOT_SEPARATED"
    return "NOT_DETECTED_UNDERPOWERED"


def primary(p: Panel, refits, flag_sequence) -> dict:
    """Primary statistic and its rotation p only (used by the power simulation)."""
    gate = structure_gate(p, refits, flag_sequence)
    if not gate["pass"]:
        return {"verdict": "DATA_INSUFFICIENT", "structure": gate}
    start = gate["start"]
    y = p.y[evaluation_mask(p, start)]
    preds = walk_forward(p, refits, start)
    d = d_brier(preds, y)
    null = rotation_null(p, refits, start, flag_sequence, {"dBrier": d_brier})["dBrier"]
    return {"structure": gate, "dBrier": d, "rotationP": one_sided_p(null, d), "preds": preds, "y": y}


def evaluate(p: Panel, refits: dict[int, int], flag_sequence: list[tuple[int, float]], starts: dict[str, int]) -> dict:
    """The whole frozen P1 comparison."""
    gate = structure_gate(p, refits, flag_sequence)
    if not gate["pass"]:
        return {"verdict": "DATA_INSUFFICIENT", "structure": gate}
    start = gate["start"]
    ev = evaluation_mask(p, start)
    y, eps = p.y[ev], p.episode[ev]
    preds = walk_forward(p, refits, start)
    b = {m: float(brier(v, y).mean()) for m, v in preds.items()}
    ll = {m: float(logloss(v, y).mean()) for m, v in preds.items()}
    d, dll = b["M1"] - b["M2"], ll["M1"] - ll["M2"]
    null = rotation_null(p, refits, start, flag_sequence, {"dBrier": d_brier, "dLogLoss": d_logloss})
    dser = brier(preds["M1"], y) - brier(preds["M2"], y)
    boot = block_bootstrap_ci(dser)
    loeo = leave_one_episode_out(dser, eps, y)
    flags = p.X[:, 2]
    events = event_metrics(p, start, flags, starts)
    pos, vals = sequence_positions(p, flag_sequence)
    ev_null = np.array([event_metrics(p, start, rotated(pos, vals, k), starts)["hits"]
                        for k in rotation_shifts(len(vals))])
    cv = purged_cv(p, starts)
    ycv = p.y[p.labelled]
    cv_d = d_brier(cv, ycv)
    return {
        "structure": gate,
        "primary": {"brier": b, "dBrier": d, "rotationP": one_sided_p(null["dBrier"], d),
                    "rotationNull": {q: float(np.quantile(null["dBrier"], float(q))) for q in ("0.05", "0.5", "0.95")},
                    "blockBootstrap": boot, "leaveOneEpisodeOut": loeo,
                    "brierSkillVsM0": {m: 1 - b[m] / b["M0"] for m in ("M1", "M2")}},
        "verdict": verdict(d, one_sided_p(null["dBrier"], d), loeo),
        "auxiliary": {
            "logloss": ll, "dLogLoss": dll, "dLogLossRotationP": one_sided_p(null["dLogLoss"], dll),
            "events": events, "eventHitRotationP": one_sided_p(ev_null.astype(float), float(events["hits"])),
            "eventHitNullDistribution": {str(h): int(np.sum(ev_null == h)) for h in range(events["evaluationEpisodes"] + 1)},
            "calibration": {m: calibration(preds[m], y) for m in MODELS}},
        "secondaryNotRealTime": {"purgedLeaveOneEpisodeOutCV": {
            "rows": int(len(ycv)), "episodes": sorted({e for e in p.episode[p.labelled & (p.y == 1)]}),
            "brier": {m: float(brier(v, ycv).mean()) for m, v in cv.items()}, "dBrier": cv_d}},
    }
