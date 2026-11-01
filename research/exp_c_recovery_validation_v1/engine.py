"""EXP-C-RECOVERY-02 fixed comparison. Pure functions; never fetch market data."""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np

RIDGE = 1.0
MIN_TRAIN_SUPPORT = 12
MIN_TEST_BLOCKS = 32
BLOCK_SESSIONS = 126
BOOTSTRAPS = 9999
SEED = 31202
MDE_LIMIT = 0.0005  # squared decimal-return units, not a return or trading hurdle


def common_rows(close, decisions, executions, state, c0, final_sessions):
    """All arrays on the sealed exchange grid. No imputation or future cohort filter.

    Return pre-fit missingness for EVERY decision and a common H63-complete panel.
    63 log daily returns are used for sample realized-volatility (ddof=1).
    Primary target is simple index return minus zero cash from execution close.
    """
    close = np.asarray(close, float)
    rows, audit = [], []
    for slot, (d, e, s, target) in enumerate(zip(decisions, executions, state, c0, strict=True)):
        reasons = []
        features = None
        if d < 63 or not np.isfinite(close[d-63:d+1]).all() or (close[d-63:d+1] <= 0).any():
            reasons.append("TRAILING_PRICE_MISSING")
        else:
            r = np.diff(np.log(close[d-63:d+1]))
            vol63, vol21 = np.std(r, ddof=1), np.std(r[-21:], ddof=1)
            if vol63 <= 0 or not np.isfinite(vol63 + vol21):
                reasons.append("VOL_UNDEFINED")
            else:
                features = [close[d] / close[d-63] - 1, vol21 / vol63 - 1]
        if any(v is None or not math.isfinite(v) for v in s):
            reasons.append("STATE_MISSING")
        elif s[0] not in (0, 1, 2) or any(v not in (0, 1) for v in s[1:]):
            raise ValueError("INVALID_STATE")
        if target not in (1.0, 0.7, 0.4):
            raise ValueError("INVALID_C0")
        if e != d + 1:
            raise ValueError("NEXT_SESSION_REQUIRED")
        h = e + 63
        if h >= len(close) or h not in final_sessions:
            reasons.append("H63_PENDING_OR_NOT_FINAL")
        elif not np.isfinite(close[e:h+1]).all() or (close[e:h+1] <= 0).any():
            reasons.append("TARGET_PATH_MISSING")
        audit.append({"slot": slot, "decision": int(d), "reasons": reasons, "stressed": target < 1})
        if reasons:
            continue
        rows.append({"slot": slot, "d": int(d), "e": int(e), "end": int(h),
                     "final": int(h), "stress": target < 1, "x": [int(s[0] == 1), int(s[0] == 2),
                     int(s[1]), int(s[2]), *features], })
    return rows, audit


def attach_labels(close, rows):
    """Call only AFTER the eligible-date/missingness receipt is persisted."""
    for row in rows:
        e = row["e"]
        row["y"] = {h: float(close[e+h] / close[e] - 1) for h in (21, 63)}
        row["risk"] = {h: int(np.min(close[e:e+h+1] / close[e] - 1) <= -0.15) for h in (21, 63)}
    return rows


def support(rows):
    """Greedy disjoint H63 label windows: a support bound, NOT iid crisis episodes."""
    end, count = -1, 0
    for row in rows:
        if row["e"] > end:
            count += 1
            end = row["end"]
    return count


def train_indices(rows, test):
    # Strict finality AND one complete H63 session embargo after maturity.
    return [i for i, r in enumerate(rows) if r["end"] + 63 < test["d"] and r["final"] < test["d"]]


def predict(train, test, y, columns):
    """Ridge: mean squared error + lambda ||beta||²; intercept unpenalized.

    Center/scale from training only. Zero-variance columns map to zero. Same
    lambda, training rows and target for M1/M2; no CV or hyperparameter selection.
    """
    if columns == 0:
        return float(np.mean(y))
    x = np.asarray([r["x"][:columns] for r in train], float)
    t = np.asarray(test["x"][:columns], float)
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale = np.where(scale > 0, scale, 1.0)
    z, zt = (x - mean) / scale, (t - mean) / scale
    ym = np.mean(y)
    coef = np.linalg.solve(z.T @ z / len(y) + RIDGE * np.eye(columns), z.T @ (y - ym) / len(y))
    return float(ym + zt @ coef)


def walk_forward(rows, stressed=True):
    panel = [r for r in rows if r["stress"] == stressed]
    scored, skipped = [], []
    for test in panel:
        train = [panel[i] for i in train_indices(panel, test)]
        n_support = support(train)
        if n_support < MIN_TRAIN_SUPPORT:
            skipped.append(test["slot"])
            continue
        item = {"slot": test["slot"], "d": test["d"], "train_n": len(train),
                "train_support": n_support, "train_slots": [r["slot"] for r in train],
                "latest_train_end": train[-1]["end"], "scores": {}}
        for h in (63, 21):
            y = np.asarray([r["y"][h] for r in train])
            risk = np.asarray([r["risk"][h] for r in train])
            p = [predict(train, test, y, c) for c in (0, 4, 6)]
            q = [float(np.clip(predict(train, test, risk, c), 0, 1)) for c in (0, 4, 6)]
            item["scores"][h] = {"loss": [(test["y"][h] - v)**2 for v in p],
                                  "brier": [(test["risk"][h] - v)**2 for v in q],
                                  "event": test["risk"][h]}
        scored.append(item)
    return scored, skipped


def paired_uncertainty(scored):
    """Calendar-aligned moving-block bootstrap of paired loss, with empty bins.

    Bin by 126 exchange sessions, retain all intervening empty bins, resample
    circular TWO-bin blocks (252 sessions) with one fixed seed. Each bootstrap
    estimates sum(score)/sum(count), preserving the stress-cohort sparsity.
    Basic centered 95% CI and upper-tail centered p are asymptotic/exploratory.
    Nested models do not receive a Clark-West adjustment: actual MSE is primary.
    """
    if not scored:
        return {"delta": None, "ci95": None, "p": None, "blocks": 0, "mde80": None}
    bins = np.asarray([r["d"] // BLOCK_SESSIONS for r in scored])
    losses = np.asarray([r["scores"][63]["loss"] for r in scored])
    delta = losses[:, 1] - losses[:, 2]
    length = int(bins.max() - bins.min() + 1)
    sums, counts = np.zeros(length), np.zeros(length)
    np.add.at(sums, bins - bins.min(), delta)
    np.add.at(counts, bins - bins.min(), 1)
    occupied = int(np.count_nonzero(counts))
    point = float(delta.mean())
    if occupied < MIN_TEST_BLOCKS:
        return {"delta": point, "ci95": None, "p": None, "blocks": occupied, "mde80": None}
    rng, draws = np.random.default_rng(SEED), []
    for _ in range(BOOTSTRAPS):
        starts = rng.integers(0, length, size=math.ceil(length / 2))
        idx = np.column_stack((starts, (starts + 1) % length)).ravel()[:length]
        denominator = counts[idx].sum()
        if denominator == 0:
            raise ValueError("EMPTY_BOOTSTRAP_CONSUMES_RUN")
        draws.append(sums[idx].sum() / denominator - point)
    spread = float(np.std(draws, ddof=1))
    if spread <= 0:
        return {"delta": point, "ci95": None, "p": None, "blocks": occupied, "mde80": None}
    low, high = np.quantile(draws, [0.025, 0.975])
    return {"delta": point, "ci95": [float(point - high), float(point - low)],
            "p": (1 + sum(v >= point for v in draws)) / (BOOTSTRAPS + 1),
            "blocks": occupied, "mde80": (1.95996398454 + 0.84162123357) * spread}


def descriptive(scored):
    if not scored:
        return {"n": 0, "mse": None, "events": None, "brier": None}
    return {"n": len(scored), "by_horizon": {str(h): {
        "mse": np.mean([r["scores"][h]["loss"] for r in scored], axis=0).tolist(),
        "events": sum(r["scores"][h]["event"] for r in scored),
        "brier": np.mean([r["scores"][h]["brier"] for r in scored], axis=0).tolist()}
        for h in (63, 21)}}


def preflight_support(rows, stressed=True):
    panel = [r for r in rows if r["stress"] == stressed]
    candidates = [test for test in panel
                  if support([panel[i] for i in train_indices(panel, test)]) >= MIN_TRAIN_SUPPORT]
    blocks = len({r["d"] // BLOCK_SESSIONS for r in candidates})
    return {"eligible": len(panel), "potential_oos": len(candidates), "occupied_126_session_blocks": blocks,
            "admissible": blocks >= MIN_TEST_BLOCKS}


def evaluate_region(rows, audit):
    primary, skipped = walk_forward(rows)
    uncertainty = paired_uncertainty(primary)
    ci = uncertainty["ci95"]
    verdict = "POWER_BLOCKED"
    if ci is not None and uncertainty["mde80"] <= MDE_LIMIT:
        verdict = "POSITIVE_REGION_COMPONENT" if ci[0] > 0 and uncertainty["p"] < 0.05 else "NO_EVIDENCE"
    elif uncertainty["delta"] is not None and uncertainty["delta"] <= 0:
        verdict = "NO_EVIDENCE"
    # Diagnostics are computed once, no additional significance tests.
    negative, _ = walk_forward(rows, stressed=False)
    mid = len(primary) // 2
    return {"verdict": verdict, "primary": {**descriptive(primary), **uncertainty},
            "halves": [descriptive(primary[:mid]), descriptive(primary[mid:])],
            "non_stressed_control": descriptive(negative), "skipped_train_support_slots": skipped,
            "common_eligible_slots": [r["slot"] for r in rows], "missingness": audit,
            "folds": [{k: v for k, v in r.items() if k != "scores"} for r in primary]}


def joint_verdict(regions):
    """ONE intersection-union primary claim: both KR AND US improve.

    max(pKR,pUS) controls the single conjunction test without an independence
    assumption or multiple region-specific discovery claims. CIs are marginal.
    """
    ps = [r.get("primary", {}).get("p") for r in regions.values()]
    joint_p = max(ps) if all(p is not None for p in ps) else None
    if any(r["verdict"] == "NO_EVIDENCE" for r in regions.values()):
        return {"verdict": "NO_EVIDENCE", "primary_p": joint_p}
    if any(r["verdict"] != "POSITIVE_REGION_COMPONENT" for r in regions.values()):
        return {"verdict": "POWER_BLOCKED", "primary_p": joint_p}
    return {"verdict": "GO_TO_ECONOMIC_COMPARISON", "primary_p": max(r["primary"]["p"] for r in regions.values())}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
