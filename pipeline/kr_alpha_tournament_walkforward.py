"""KR alpha discovery tournament v1 — nested walk-forward: outer folds, purged and embargoed inner blocks, inner scoring, the frozen selection rule,
the ensemble and the per-anchor forecasts.

ISOLATION, BY CONSTRUCTION. Every function that fits, scores or calibrates for outer fold Y receives `train = eligible & exitDate < C_Y` and nothing
else from the label frame; the outer anchors of year Y are predicted from signal-time representations only. A label whose exit is on or after C_Y is
never indexed by fold Y's fitting code (a test perturbs exactly those labels and requires byte-identical fold-Y forecasts).

Pure functions over arrays and frames handed in by the caller. Labels are an OUTCOME: the execution harness builds them only behind its permit and
durable lock; synthetic tests build invented ones.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from . import kr_alpha_tournament as T
from . import kr_alpha_tournament_models as M
from . import kr_alpha_tournament_portfolio as P

LABEL_COLUMNS = ("entryDate", "exitDate", "eligible", "yEcon", *T.TARGET_ORDER, "r21Stock", "r21Bench")


# --------------------------------------------------------------------------- #
# Calendar arithmetic (no prices)
# --------------------------------------------------------------------------- #
class Calendar:
    def __init__(self, sessions):
        self.days = [str(d)[:10] for d in sessions]
        self.index = {d: i for i, d in enumerate(self.days)}

    def pos_on_or_before(self, day):
        import bisect
        return bisect.bisect_right(self.days, day) - 1

    def entry(self, signal):
        """The first session strictly after the signal date."""
        return self.days[self.pos_on_or_before(signal) + 1]

    def shift(self, day, n):
        return self.days[self.index[day] + n]

    def exit(self, signal, horizon):
        return self.days[self.pos_on_or_before(signal) + 1 + horizon]


def outer_folds(anchors, first_year=T.OUTER_FIRST_YEAR):
    """[{year, cutoff, anchors}] — one per calendar year from `first_year`; the cutoff is the SIGNAL date of the year's first anchor."""
    out = {}
    for day, signal in anchors:
        year = int(day[:4])
        if year >= first_year:
            out.setdefault(year, []).append((day, signal))
    return [{"year": y, "cutoff": out[y][0][1], "anchors": out[y]} for y in sorted(out)]


def training_mask(labels, cutoff):
    """The ONLY label rows fold `cutoff` may read: label-eligible and exit strictly before the cutoff."""
    exit_ = labels["exitDate"].astype(object)
    ok = exit_.notna().to_numpy() & labels["eligible"].fillna(False).astype(bool).to_numpy()
    return ok & (exit_.fillna("9999-12-31").astype(str).to_numpy() < cutoff)


def inner_blocks(dates, train, labels, calendar):
    """Purged + embargoed inner folds inside the outer training set. `dates` = signal date per row; `train` = the outer training mask."""
    train_dates = sorted(set(np.asarray(dates)[train]))
    recent = train_dates[len(train_dates) // 2:]
    groups = [list(g) for g in np.array_split(np.array(recent, dtype=object), T.INNER_BLOCKS)] if recent else []
    out = []
    exit_ = labels["exitDate"].astype(object).fillna("9999-12-31").astype(str).to_numpy()
    dates = np.asarray(dates)
    for j, block in enumerate(groups):
        if not block:
            out.append({"block": j, "status": "EMPTY"})
            continue
        first_signal, first_entry = block[0], calendar.entry(block[0])
        embargo_limit = calendar.days[max(0, calendar.pos_on_or_before(first_signal) - T.EMBARGO_SESSIONS)]
        tr = train & (exit_ < first_entry) & (dates <= embargo_limit)
        va = train & np.isin(dates, block)
        n_tr, n_va = len(set(dates[tr])), len(set(dates[va]))
        status = "VALID" if n_tr >= T.MIN_TRAIN_DATES and n_va >= T.MIN_VALID_DATES else "INSUFFICIENT"
        out.append({"block": j, "status": status, "train": tr, "valid": va, "firstSignal": first_signal, "firstEntry": first_entry,
                    "embargoLimit": embargo_limit, "trainDates": n_tr, "validDates": n_va, "lastValidSignal": block[-1]})
    return out


def econ_dates(block_dates, calendar, horizon=T.INNER_BLOCK_HORIZON):
    """Non-overlapping anchor-spaced dates inside a validation block: the next date's entry is on or after the previous block's exit."""
    chosen, free_from = [], ""
    for d in sorted(block_dates):
        if calendar.entry(d) >= free_from:
            chosen.append(d)
            free_from = calendar.exit(d, horizon)
    return chosen


# --------------------------------------------------------------------------- #
# One candidate: inner evaluation
# --------------------------------------------------------------------------- #
def design_for(candidate, data):
    return data["Xtree"] if T.MODEL_FAMILIES[candidate["family"]]["design"] == "tree" else data["Xlin"]


def fit_on(candidate, data, labels, mask, cutoff, counters=None):
    if int(mask.sum()) < 50:
        raise ValueError("TOO_FEW_TRAINING_ROWS")
    X = design_for(candidate, data)[mask]
    y = labels[candidate["target"]].to_numpy(float)[mask]
    dates = data["dates"][mask]
    w = M.recency_weights(dates, cutoff, candidate["recency"])
    if counters is not None:
        counters["modelFits"] = counters.get("modelFits", 0) + 1
    return M.fit_candidate(candidate, X, y, w, dates)


def _single_member_forecast(cal, preds_by_date_row, rows):
    s = M.within_date_rank(np.zeros(len(rows)), preds_by_date_row)
    mu, sd = M.apply_calibration(cal, s)
    c = M.contract(mu[None, :], sd[None, :])
    return c["muPost"]


def inner_economic_block(rows, mu_post, risk, w_prev, cfg=T.PORTFOLIO):
    """One anchor-spaced inner block: allocate on the shrunk forecasts and return (active block log-growth, new weights). Inner approximation
    (registered): 21-session buy-and-hold block returns, linear costs, label-eligible names; the outer path is valued daily."""
    r = risk(rows["date"].iloc[0])
    pos = {t: i for i, t in enumerate(r["tickers"])}
    eligible = (rows["tradable"].astype(bool).to_numpy() & (rows["adv60"].to_numpy(float) >= cfg["minimumAdvKrw"])
                & np.isfinite(mu_post) & np.isfinite(rows["r21Stock"].to_numpy(float)) & rows["ticker"].isin(pos).to_numpy())
    tick = rows["ticker"].to_numpy()[eligible]
    rb = float(rows["r21Bench"].dropna().iloc[0]) if rows["r21Bench"].notna().any() else np.nan
    if not np.isfinite(rb):
        return None, w_prev
    idx = [pos[t] for t in tick]
    w0 = np.array([w_prev.get(t, 0.0) for t in tick])
    cb, cs = P.unit_costs()
    lower, upper = P.trade_box(w0, rows["adv60"].to_numpy(float)[eligible], cfg["referenceNavKrw"])
    w, _ = P.allocate(mu_post[eligible], r["cov"][np.ix_(idx, idx)], r["ceb"][idx], w0, cb, cs, lower, upper)
    sold = sum(v for t, v in w_prev.items() if t not in set(tick))
    cost = float(cb * np.maximum(w - w0, 0).sum() + cs * (np.maximum(w0 - w, 0).sum() + sold))
    active = float(np.dot(w, rows["r21Stock"].to_numpy(float)[eligible] - rb)) - cost
    growth = math.log(max(1e-12, 1 + rb + active)) - math.log(1 + rb)
    return growth, {t: float(v) for t, v in zip(tick, w) if v > 0}


def evaluate_inner(candidate, data, labels, blocks, cutoff, risk, calendar, counters=None):
    """IC per valid fold, out-of-fold calibration triples, coverage and the inner economic score of ONE candidate."""
    valid = [b for b in blocks if b["status"] == "VALID"]
    dates = data["dates"]
    rank_outcome = labels["C_CROSS_SECTIONAL_RANK"].to_numpy(float)
    y_econ = labels["yEcon"].to_numpy(float)
    folds, oof = [], {"dates": [], "s": [], "y": []}
    econ, coverage_hits, coverage_rows = [], 0, 0
    for j, b in enumerate(valid):
        try:
            model = fit_on(candidate, data, labels, b["train"] & np.isfinite(labels[candidate["target"]].to_numpy(float)), b["firstSignal"], counters)
        except ValueError as error:
            folds.append({"block": b["block"], "status": "FIT_FAILED", "reason": str(error)})
            continue
        idx = np.flatnonzero(b["valid"])
        pred = model.predict(design_for(candidate, data)[idx])
        coverage_hits += int(np.isfinite(pred).sum())
        coverage_rows += len(idx)
        s = M.within_date_rank(dates[idx], pred)
        ics = M.per_date_ic(dates[idx], pred, rank_outcome[idx])
        ic = float(np.mean(list(ics.values()))) if ics else np.nan
        if j >= 1:
            cal = M.calibrate(oof["dates"], oof["s"], oof["y"])
            growth, w_prev, blocks_used = [], {}, 0
            for d in econ_dates(sorted(set(dates[idx])), calendar):
                rows_idx = idx[dates[idx] == d]
                rows = data["rep"].iloc[rows_idx].assign(r21Stock=labels["r21Stock"].to_numpy(float)[rows_idx],
                                                          r21Bench=labels["r21Bench"].to_numpy(float)[rows_idx])
                mu_post = _single_member_forecast(cal, pred[np.isin(idx, rows_idx)], rows_idx)
                g, w_prev = inner_economic_block(rows.reset_index(drop=True), mu_post, risk, w_prev)
                if counters is not None:
                    counters["allocatorSolves"] = counters.get("allocatorSolves", 0) + 1
                if g is not None:
                    growth.append(g)
                    blocks_used += 1
            econ.append(float(np.mean(growth) * 252 / T.INNER_BLOCK_HORIZON) if growth else np.nan)
        oof["dates"] += list(dates[idx])
        oof["s"] += list(s)
        oof["y"] += list(y_econ[idx])
        folds.append({"block": b["block"], "status": "SCORED", "ic": ic, "icDates": len(ics)})
    scored = [f for f in folds if f["status"] == "SCORED"]
    positives = sum(1 for f in scored if np.isfinite(f["ic"]) and f["ic"] > 0)
    need = math.ceil(T.SELECTION["minIcFoldShare"][0] * len(scored) / T.SELECTION["minIcFoldShare"][1]) if scored else 1
    pooled = M.calibrate(oof["dates"], oof["s"], oof["y"])
    coverage = coverage_hits / coverage_rows if coverage_rows else 0.0
    econ_ok = bool(econ) and all(np.isfinite(e) for e in econ)
    reasons = []
    if len(scored) < T.MIN_VALID_FOLDS:
        reasons.append("TOO_FEW_VALID_INNER_FOLDS")
    if positives < need:
        reasons.append("IC_DIRECTION_UNSTABLE")
    if not (pooled["b"] is not None and pooled["b"] > 0):
        reasons.append("CALIBRATION_SLOPE_NOT_POSITIVE")
    if coverage < T.SELECTION["minCoverage"]:
        reasons.append("COVERAGE_BELOW_MINIMUM")
    if not econ_ok:
        reasons.append("ECONOMIC_SCORE_NOT_FINITE")
    return {"id": candidate["id"], "family": candidate["family"], "folds": folds, "positiveIcFolds": positives, "requiredPositiveIcFolds": need,
            "calibration": {k: pooled[k] for k in ("status", "dates", "b", "se", "bStar", "carry")}, "coverage": coverage,
            "economicScores": econ, "economicScore": float(np.mean(econ)) if econ_ok else None, "survives": not reasons, "rejections": reasons,
            "oof": oof}


def select_ensemble(results, k=T.SELECTION["K"]):
    """Step 2-3 of the frozen rule: rank survivors by inner economic score (ties by id), keep the best of each family until K."""
    survivors = sorted((r for r in results if r["survives"]), key=lambda r: (-r["economicScore"], r["id"]))
    members, families = [], set()
    for r in survivors:
        if r["family"] in families:
            continue
        members.append(r["id"])
        families.add(r["family"])
        if len(members) == k:
            break
    return members


# --------------------------------------------------------------------------- #
# Decision-focused challenger (quarantined)
# --------------------------------------------------------------------------- #
def fit_dfl(Xlin, y_econ, dates, round_trip_cost, gamma=T.DFL_GAMMA, theta0=T.DFL_THETA0):
    """Parametric long-only policy: w_i = sigmoid(t0 + z_i't) / N_date. Maximises mean_d log(1 + sum_i w_i (e_i - c)) - gamma |t|^2 on the outer
    training rows only. Deterministic L-BFGS from t = 0."""
    scaler = M.Scaler(Xlin, np.ones(len(Xlin)))
    Z = scaler(Xlin)
    ok = np.isfinite(y_econ)
    Z, e, d = Z[ok], y_econ[ok] - round_trip_cost, np.asarray(dates)[ok]
    uniq, inv, counts = np.unique(d, return_inverse=True, return_counts=True)
    n_d = counts[inv].astype(float)

    def f(params):
        t0, th = params[0], params[1:]
        a = Z @ th + t0
        sig = 1 / (1 + np.exp(-np.clip(a, -50, 50)))
        w = sig / n_d
        port = np.bincount(inv, weights=w * e, minlength=len(uniq))
        g = 1 + port
        if (g <= 0).any():
            return 1e6, np.zeros_like(params)
        val = -np.mean(np.log(g)) + gamma * float(th @ th)
        dlog = (1 / g)[inv] / len(uniq)
        dw = -dlog * e * sig * (1 - sig) / n_d
        grad = np.concatenate([[dw.sum()], Z.T @ dw + 2 * gamma * th])
        return float(val), grad

    x0 = np.zeros(Z.shape[1] + 1)
    x0[0] = theta0
    res = minimize(f, x0, jac=True, method="L-BFGS-B", options={"maxiter": 500})
    params = res.x

    def weights(Xn, n_names):
        a = scaler(Xn) @ params[1:] + params[0]
        return (1 / (1 + np.exp(-np.clip(a, -50, 50)))) / max(1, n_names)
    return {"weights": weights, "theta": params, "converged": bool(res.success)}


# --------------------------------------------------------------------------- #
# The outer process
# --------------------------------------------------------------------------- #
def run_outer_fold(fold, data, labels, registry, risk, calendar, counters=None):
    """Everything the process decides for outer year Y, using only rows that trained before C_Y. Returns the fold log and per-anchor forecasts."""
    cutoff = fold["cutoff"]
    train = training_mask(labels, cutoff)
    log = {"year": fold["year"], "cutoff": cutoff, "trainingRows": int(train.sum()), "trainingDates": len(set(data["dates"][train]))}
    blocks = inner_blocks(data["dates"], train, labels, calendar)
    log["innerBlocks"] = [{k: b[k] for k in b if k not in ("train", "valid")} for b in blocks]
    valid = [b for b in blocks if b["status"] == "VALID"]
    results = []
    if len(valid) >= T.MIN_VALID_FOLDS:
        for cand in registry:
            results.append(evaluate_inner(cand, data, labels, blocks, cutoff, risk, calendar, counters))
    members = select_ensemble(results)
    log["candidates"] = [{k: r[k] for k in r if k != "oof"} for r in results]
    log["ensemble"] = members
    log["state"] = "ENSEMBLE" if members else "PASSIVE_DEFAULT_NO_STABLE_CANDIDATE"
    by_id = {c["id"]: c for c in registry}
    oof = {r["id"]: r["oof"] for r in results}
    fitted, cals = {}, {}
    all_models = {}
    for cand in registry:                       # every configuration is refitted on the full past: members for the forecast, all for the universe
        mask = train & np.isfinite(labels[cand["target"]].to_numpy(float))
        try:
            all_models[cand["id"]] = fit_on(cand, data, labels, mask, cutoff, counters)
        except ValueError:
            all_models[cand["id"]] = None
    for mid in members:
        fitted[mid] = all_models[mid]
        o = oof[mid]
        cals[mid] = M.calibrate(o["dates"], o["s"], o["y"])
    log["memberCalibration"] = {m: {k: cals[m][k] for k in ("status", "dates", "b", "se", "bStar", "carry")} for m in members}
    dfl = fit_dfl(data["Xlin"][train], labels["yEcon"].to_numpy(float)[train], data["dates"][train], sum(P.unit_costs()))
    log["decisionFocusedChallenger"] = {"converged": dfl["converged"]}
    anchors = {}
    for day, signal in fold["anchors"]:
        idx = np.flatnonzero(data["dates"] == signal)
        if not len(idx):
            anchors[day] = {"signal": signal, "available": False, "reason": "NO_SIGNAL_TIME_CROSS_SECTION"}
            continue
        rows = data["rep"].iloc[idx]
        entry = {"signal": signal, "available": len(idx) >= T.MIN_NAMES_PER_LABEL_DATE, "tickers": list(rows.ticker), "rows": idx}
        if members:
            mus, sds, natives = [], [], {}
            for mid in members:
                pred = fitted[mid].predict(design_for(by_id[mid], data)[idx])
                natives[mid] = pred
                mu, sd = M.apply_calibration(cals[mid], M.within_date_rank(np.zeros(len(idx)), pred))
                mus.append(mu)
                sds.append(sd)
            c = M.contract(np.vstack(mus), np.vstack(sds))
            entry.update({"mu": c["mu"], "muPost": c["muPost"], "sigma2": c["sigma2"], "kappa": c["kappa"], "disagreement": c["disagreement"],
                          "memberScores": natives})
        universe = {}
        for cid, model in all_models.items():
            if model is not None:
                universe[cid] = model.predict(design_for(by_id[cid], data)[idx])
        entry["universeScores"] = universe
        entry["dflWeights"] = dfl["weights"](data["Xlin"][idx], len(idx))
        if counters is not None:
            counters["predictions"] = counters.get("predictions", 0) + 1
        anchors[day] = entry
    return log, anchors


def run_process(data, labels, anchors, registry, risk, calendar, counters=None):
    """The whole outer walk-forward. Returns {folds: [...], anchors: {day: forecast}}."""
    folds, forecasts = [], {}
    for fold in outer_folds(anchors):
        log, per_anchor = run_outer_fold(fold, data, labels, registry, risk, calendar, counters)
        folds.append(log)
        forecasts.update(per_anchor)
    return {"folds": folds, "anchors": forecasts}


def prepare_data(rep):
    """Design matrices aligned to the (date, ticker)-sorted representation frame."""
    from . import kr_alpha_tournament_features as F
    rep = rep.sort_values(["date", "ticker"]).reset_index(drop=True)
    Xlin, lin_names = F.linear_design(rep)
    Xtree, tree_names = F.tree_design(rep)
    return {"rep": rep, "dates": rep["date"].to_numpy().astype(str), "Xlin": Xlin, "Xtree": Xtree, "linearColumns": lin_names, "treeColumns": tree_names}


def align_labels(data, labels):
    """Labels re-indexed to the representation rows; a missing label row is an ineligible row, never a zero."""
    keyed = labels.set_index(["date", "ticker"])
    out = keyed.reindex(pd.MultiIndex.from_arrays([data["rep"]["date"], data["rep"]["ticker"]])).reset_index(drop=True)
    out["eligible"] = out["eligible"].astype("boolean").fillna(False).astype(bool)
    return out
