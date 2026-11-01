"""Pure, network-free functions for industry-information-transfer-v1.

Everything here works on already-parsed preliminary-earnings observations and a
session calendar. No price after the forecast origin and no stock return label is
read anywhere in this module.
"""
from __future__ import annotations

import bisect
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import numpy as np

CLIP_REVENUE = 1.0
CLIP_OP = 0.5
MIN_MARKET_PEERS = 5
MIN_INDUSTRY_PEERS = 2
MIN_TRAIN_QUARTERS = 8
TRAIN_GAP_QUARTERS = 2
NW_LAG = 2


# --------------------------------------------------------------------------- quarters and sessions
def quarter_index(q: date) -> int:
    return q.year * 4 + (q.month - 1) // 3


def quarter_from_index(index: int) -> date:
    year, k = divmod(index, 4)
    month = 3 * (k + 1)
    return date(year, month, 31 if month in (3, 12) else 30)


class Sessions:
    def __init__(self, days: list[date]):
        self.days = sorted(days)

    def next_after(self, d: date) -> date | None:
        i = bisect.bisect_right(self.days, d)
        return self.days[i] if i < len(self.days) else None

    def before(self, d: date) -> date | None:
        i = bisect.bisect_left(self.days, d)
        return self.days[i - 1] if i > 0 else None

    def count_between(self, a: date, b: date) -> int:
        """Sessions s with a < s <= b."""
        return bisect.bisect_right(self.days, b) - bisect.bisect_right(self.days, a)


def available(disclosed: date, origin: date, sessions: Sessions) -> bool:
    """Conservative: a disclosure is usable from the close of the next session after its receipt date."""
    nxt = sessions.next_after(disclosed)
    return nxt is not None and nxt <= origin


# --------------------------------------------------------------------------- observations
def revenue_growth(rev: float | None, prior: float | None) -> float | None:
    if rev is None or prior is None or rev <= 0 or prior <= 0:
        return None
    return max(-CLIP_REVENUE, min(CLIP_REVENUE, math.log(rev / prior)))


def op_change(op: float | None, op_prior: float | None, rev_prior: float | None) -> float | None:
    if op is None or op_prior is None or rev_prior is None or rev_prior <= 0:
        return None
    return max(-CLIP_OP, min(CLIP_OP, (op - op_prior) / rev_prior))


@dataclass
class Obs:
    corp: str
    quarter: date
    disclosed: date
    y: float | None
    y_op: float | None
    industry: str | None
    market_cap: float | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class Row:
    corp: str
    quarter: date
    origin: date
    y: float
    own: float
    mkt: float
    ind: float
    n_mkt: int
    n_ind: int
    industry: str
    y_op: float | None = None
    own_op: float | None = None
    mkt_op: float | None = None
    ind_op: float | None = None
    stale: float | None = None
    ind_ex_largest: float | None = None
    indmom: float | None = None
    market_cap: float | None = None
    peers: list = field(default_factory=list)


def _mean(values):
    return sum(values) / len(values) if values else None


def build_rows(obs: list[Obs], sessions: Sessions, *, industry_override: dict | None = None,
               attrition: dict | None = None) -> list[Row]:
    """One Row per eligible target. ``industry_override`` maps (corp, quarter) -> label (permutation control)."""
    by_q: dict[date, list[Obs]] = defaultdict(list)
    by_key = {}
    for o in obs:
        by_q[o.quarter].append(o)
        by_key[(o.corp, o.quarter)] = o

    def ind_of(o):
        if industry_override is not None:
            return industry_override.get((o.corp, o.quarter))
        return o.industry

    rows = []
    tally = attrition if attrition is not None else {}
    for q, members in sorted(by_q.items()):
        prev_q = quarter_from_index(quarter_index(q) - 1)
        for o in members:
            tally["units"] = tally.get("units", 0) + 1
            if o.y is None:
                tally["noTarget"] = tally.get("noTarget", 0) + 1
                continue
            origin = sessions.before(o.disclosed)
            own_prev = by_key.get((o.corp, prev_q))
            if own_prev is None or own_prev.y is None or own_prev.disclosed >= o.disclosed:
                tally["noOwnHistory"] = tally.get("noOwnHistory", 0) + 1
                continue
            industry = ind_of(o)
            if industry is None:
                tally["noIndustry"] = tally.get("noIndustry", 0) + 1
                continue
            early = [p for p in members if p.corp != o.corp and p.y is not None and available(p.disclosed, origin, sessions)]
            if len(early) < MIN_MARKET_PEERS:
                tally["fewMarketPeers"] = tally.get("fewMarketPeers", 0) + 1
                continue
            same = [p for p in early if ind_of(p) == industry]
            if len(same) < MIN_INDUSTRY_PEERS:
                tally["fewIndustryPeers"] = tally.get("fewIndustryPeers", 0) + 1
                continue
            tally["eligible"] = tally.get("eligible", 0) + 1
            stale_peers = [p for p in by_q.get(prev_q, []) if p.corp != o.corp and p.y is not None
                           and ind_of_stale(p, industry, ind_of, by_key, q) and available(p.disclosed, origin, sessions)]
            ranked = sorted(same, key=lambda p: (-(p.market_cap or 0.0), p.corp))
            ex_largest = ranked[1:] if len(ranked) >= 3 else []
            rows.append(Row(
                corp=o.corp, quarter=q, origin=origin, y=o.y, own=own_prev.y,
                mkt=_mean([p.y for p in early]), ind=_mean([p.y for p in same]),
                n_mkt=len(early), n_ind=len(same), industry=industry,
                y_op=o.y_op, own_op=own_prev.y_op,
                mkt_op=_mean([p.y_op for p in early if p.y_op is not None]),
                ind_op=_mean([p.y_op for p in same if p.y_op is not None]),
                stale=_mean([p.y for p in stale_peers]) if len(stale_peers) >= MIN_INDUSTRY_PEERS else None,
                ind_ex_largest=_mean([p.y for p in ex_largest]) if ex_largest else None,
                market_cap=o.market_cap,
                peers=[(p.corp, p.disclosed.isoformat(), p.y) for p in sorted(same, key=lambda p: (p.disclosed, p.corp))],
            ))
    return rows


def ind_of_stale(peer_prev: Obs, industry: str, ind_of, by_key, q: date) -> bool:
    """A q-1 observation counts as a same-industry stale peer if the peer's industry in quarter q (else q-1) matches."""
    current = by_key.get((peer_prev.corp, q))
    label = ind_of(current) if current is not None else ind_of(peer_prev)
    return label == industry


def permuted_industries(obs: list[Obs], rng: random.Random) -> dict:
    """Within each quarter, shuffle industry labels across firms (group sizes preserved)."""
    out = {}
    by_q = defaultdict(list)
    for o in obs:
        if o.industry is not None:
            by_q[o.quarter].append(o)
    for q, members in sorted(by_q.items()):
        members = sorted(members, key=lambda o: o.corp)
        labels = [o.industry for o in members]
        rng.shuffle(labels)
        for o, label in zip(members, labels):
            out[(o.corp, q)] = label
    return out


# --------------------------------------------------------------------------- models
def ols_fit(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    design = np.column_stack([np.ones(len(y)), x])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    return coef


def ols_predict(coef: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(x)), x]) @ coef


def spearman(a, b) -> float | None:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3:
        return None
    ra = np.argsort(np.argsort(a, kind="mergesort"), kind="mergesort").astype(float)
    rb = np.argsort(np.argsort(b, kind="mergesort"), kind="mergesort").astype(float)
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def oos_compare(rows: list[Row], base: tuple[str, ...], challenger: tuple[str, ...], target: str = "y",
                *, min_train_quarters: int = MIN_TRAIN_QUARTERS, gap: int = TRAIN_GAP_QUARTERS) -> dict:
    """Expanding-window OOS comparison on the identical row set (rows missing any feature are dropped for both)."""
    cols = sorted(set(base) | set(challenger))
    usable = [r for r in rows if getattr(r, target) is not None and all(getattr(r, c) is not None for c in cols)]
    quarters = sorted({r.quarter for r in usable})
    per_quarter = []
    for q in quarters:
        qi = quarter_index(q)
        train = [r for r in usable if quarter_index(r.quarter) <= qi - gap]
        if len({r.quarter for r in train}) < min_train_quarters:
            continue
        test = [r for r in usable if r.quarter == q]
        if len(test) < 3:
            continue
        ytr = np.array([getattr(r, target) for r in train])
        yte = np.array([getattr(r, target) for r in test])
        preds = {}
        for name, feats in (("base", base), ("challenger", challenger)):
            xtr = np.array([[getattr(r, c) for c in feats] for r in train])
            xte = np.array([[getattr(r, c) for c in feats] for r in test])
            preds[name] = ols_predict(ols_fit(xtr, ytr), xte)
        mse_b = float(np.mean((yte - preds["base"]) ** 2))
        mse_c = float(np.mean((yte - preds["challenger"]) ** 2))
        inc_ic = spearman(preds["challenger"] - preds["base"], yte - preds["base"])
        per_quarter.append({"quarter": q.isoformat(), "n": len(test), "mseBase": mse_b, "mseChallenger": mse_c,
                            "delta": mse_b - mse_c, "incrementalRankIC": inc_ic,
                            "sstTest": float(np.sum((yte - ytr.mean()) ** 2)),
                            "sseBase": float(np.sum((yte - preds["base"]) ** 2)),
                            "sseChallenger": float(np.sum((yte - preds["challenger"]) ** 2))})
    deltas = [p["delta"] for p in per_quarter]
    ics = [p["incrementalRankIC"] for p in per_quarter if p["incrementalRankIC"] is not None]
    sst = sum(p["sstTest"] for p in per_quarter)
    return {
        "base": list(base), "challenger": list(challenger), "target": target,
        "rowsUsable": len(usable), "quartersEvaluated": len(per_quarter),
        "rowsEvaluated": sum(p["n"] for p in per_quarter),
        "firstEvaluatedQuarter": per_quarter[0]["quarter"] if per_quarter else None,
        "delta": nw_summary(deltas), "incrementalRankIC": nw_summary(ics),
        "oosR2Base": 1 - sum(p["sseBase"] for p in per_quarter) / sst if sst else None,
        "oosR2Challenger": 1 - sum(p["sseChallenger"] for p in per_quarter) / sst if sst else None,
        "perQuarter": per_quarter,
    }


# --------------------------------------------------------------------------- inference
def nw_summary(series: list[float], lag: int = NW_LAG) -> dict:
    """Mean with a Newey-West (Bartlett) standard error and a two-sided normal p-value."""
    x = np.asarray(series, float)
    n = len(x)
    if n < 3:
        return {"n": n, "mean": float(x.mean()) if n else None, "se": None, "t": None, "p": None,
                "ci95": None, "positiveShare": None}
    mean = float(x.mean())
    e = x - mean
    gamma0 = float(e @ e) / n
    var = gamma0
    for k in range(1, min(lag, n - 1) + 1):
        weight = 1 - k / (lag + 1)
        var += 2 * weight * float(e[k:] @ e[:-k]) / n
    se = math.sqrt(max(var, 0.0) / n)
    t = mean / se if se > 0 else None
    p = math.erfc(abs(t) / math.sqrt(2)) if t is not None else None
    return {"n": n, "mean": mean, "se": se, "t": t, "p": p,
            "ci95": [mean - 1.959964 * se, mean + 1.959964 * se],
            "positiveShare": float(np.mean(x > 0))}


def holm(pvalues: dict[str, float | None], alpha: float = 0.05) -> dict:
    """Holm step-down. A slot that was not run carries p = 1 and still counts in the family."""
    items = sorted(((p if p is not None else 1.0), k) for k, p in pvalues.items())
    m = len(items)
    out, still = {}, True
    for i, (p, k) in enumerate(items):
        threshold = alpha / (m - i)
        reject = still and p <= threshold
        still = reject
        out[k] = {"p": p, "threshold": threshold, "rejectNull": reject}
    return out


def decide_h1(primary: dict, permutation_p: float | None, stale_delta: float | None, holm_row: dict) -> str:
    d = primary["delta"]
    if primary["quartersEvaluated"] < 20 or primary["rowsEvaluated"] < 500:
        return "DATA_BLOCKED"
    if d["mean"] is None or d["mean"] <= 0:
        return "REJECT"
    if (holm_row["rejectNull"] and permutation_p is not None and permutation_p <= 0.05
            and stale_delta is not None and d["mean"] > stale_delta):
        return "KEEP"
    return "INCONCLUSIVE"
