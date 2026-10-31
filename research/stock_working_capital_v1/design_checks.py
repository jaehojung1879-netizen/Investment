"""Synthetic rehearsal of the proposed comparison; no historical data loader.

The real execution boundary is deliberately absent. A domain string is a label
for tests, not a security capability. Source/owner authorizations must be wired
and independently audited before a future real-data runner can exist.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
import math
from statistics import NormalDist

import numpy as np

from .features import day, digest


def rehearsal_only(rows):
    if any(r.get("domain") != "SYNTHETIC_ONLY" or not r.get("security", "").startswith("SYN-")
           for r in rows):
        raise ValueError("REAL_HISTORY_EXECUTION_NOT_IMPLEMENTED_OR_AUTHORIZED")


def freeze_cohort(rows, signal, sessions):
    """Outcome-free intended membership; changing industry/size also changes SHA."""
    day(signal)
    if signal not in sessions or sessions != sorted(set(sessions)):
        raise ValueError("INVALID_SIGNAL_CALENDAR")
    ids = [r["security"] for r in rows]
    if len(ids) != len(set(ids)) or any(set(r) != {"security", "industry", "sizeBucket"} for r in rows):
        raise ValueError("INVALID_INTENDED_COHORT")
    if not rows or any(not all(isinstance(v, str) and v for v in r.values()) for r in rows):
        raise ValueError("UNCLASSIFIED_INTENDED_MEMBER")
    payload = {"signal": signal, "sessionsSha256": digest(sessions),
               "members": sorted(rows, key=lambda r: r["security"])}
    return {**payload, "sha256": digest(payload)}


def check_cohort(receipt, expected_sha, sessions):
    payload = {k: v for k, v in receipt.items() if k != "sha256"}
    if receipt.get("sha256") != expected_sha or digest(payload) != expected_sha:
        raise ValueError("INTENDED_COHORT_CHANGED")
    reconstructed = freeze_cohort(receipt["members"], receipt["signal"], sessions)
    if reconstructed != receipt:
        raise ValueError("COHORT_OR_CALENDAR_CHANGED")


def paired_rehearsal(rows, receipt, expected_sha, sessions, as_of, horizon, min_pairs):
    """All intended names remain in denominator. No missing-payoff exclusion.

    A single intended member missing any target/forecast/cost blocks this date's
    comparison, including missing stock in the industry reference. Both horizon
    and maturity are computed from a frozen exchange calendar, never caller
    'not matured' lists. Across dates the caller must report blocked dates too.
    """
    rehearsal_only(rows)
    check_cohort(receipt, expected_sha, sessions)
    day(as_of)
    if horizon not in (126, 252) or type(min_pairs) is not int or min_pairs < 2:
        raise ValueError("INVALID_COMPARISON_SPEC")
    keys = [r["security"] for r in rows]
    if len(keys) != len(set(keys)) or set(keys) != {r["security"] for r in receipt["members"]}:
        raise ValueError("MISSING_EXTRA_OR_DUPLICATE_INTENDED_MEMBER")
    i = sessions.index(receipt["signal"])
    # Signal close is not executable. H returns: next session open -> Hth close.
    end = i + horizon
    if end >= len(sessions) or day(sessions[end]) >= day(as_of):
        return {"status": "NOT_MATURED", "pairs": 0, "intended": len(keys)}
    missing = Counter()
    fields = ("targetNetExcess", "baselinePrediction", "augmentedPrediction")
    for r in rows:
        for f in fields:
            if type(r.get(f)) not in (int, float) or not math.isfinite(r[f]):
                missing["MISSING:" + f] += 1
        for reason in set(r.get("reasons", [])):
            missing[reason] += 1
    valid = sum(all(type(r.get(f)) in (int, float) and math.isfinite(r[f]) for f in fields)
                and not r.get("reasons") for r in rows)
    report = {"intended": len(keys), "pairs": valid, "missingByReason": dict(sorted(missing.items())),
              "coverage": valid / len(keys)}
    if missing or valid < min_pairs:
        return {**report, "status": "BLOCKED", "mseImprovement": None}
    improvement = [((r["targetNetExcess"] - r["baselinePrediction"]) ** 2
                    - (r["targetNetExcess"] - r["augmentedPrediction"]) ** 2) for r in rows]
    return {**report, "status": "SYNTHETIC_COMPLETE", "mseImprovement": float(np.mean(improvement))}


def purged_training(samples, evaluation_start, sessions, embargo=21):
    """Each label's actual close must precede the fixed embargo boundary."""
    rehearsal_only(samples)
    if type(embargo) is not int or embargo < 0 or sessions != sorted(set(sessions)):
        raise ValueError("INVALID_SPLIT")
    e = sessions.index(evaluation_start)
    if e < embargo:
        return []
    boundary = sessions[e - embargo]
    out = []
    for r in samples:
        if r["signal"] not in sessions or r["labelEnd"] not in sessions or r["signal"] > r["labelEnd"]:
            raise ValueError("INVALID_LABEL_WINDOW")
        if r["signal"] < evaluation_start and r["labelEnd"] < boundary:
            out.append(r)
    return out


def ridge_rehearsal(training, evaluation, evaluation_start, sessions, min_training=30):
    """Fixed alpha=1, train-only imputation/scaling, one extra signal at a time.

    Numeric baseline columns are supplied by the *synthetic* fixture. The real
    schema, industry encoding and source adapters remain approval prerequisites.
    Evaluation labels are never inspected to fit or construct a prediction.
    """
    rehearsal_only(training + evaluation)
    if type(min_training) is not int or min_training < 3:
        raise ValueError("INVALID_TRAINING_MINIMUM")
    train = purged_training(training, evaluation_start, sessions)
    for batch in (training, evaluation):
        keys = [(r["signal"], r["security"]) for r in batch]
        if len(set(keys)) != len(keys):
            raise ValueError("DUPLICATE_DATED_SECURITY")
    if len(train) < min_training or not evaluation:
        raise ValueError("INSUFFICIENT_PURGED_TRAINING")
    if any(r["signal"] != evaluation_start for r in evaluation):
        raise ValueError("EVALUATION_DATE_MISMATCH")
    n = len(train[0]["baseline"])
    for row in train + evaluation:
        if len(row["baseline"]) != n or not n:
            raise ValueError("BASELINE_SCHEMA_CHANGED")
        for v in [*row["baseline"], row["newSignal"]]:
            if v is not None and (type(v) not in (int, float) or not math.isfinite(v)):
                raise ValueError("INVALID_FEATURE")
    y = np.array([r["targetNetExcess"] for r in train], dtype=float)
    if not np.isfinite(y).all():
        raise ValueError("MISSING_TRAINING_TARGET")

    def fit(augmented):
        def vector(row):
            return [*row["baseline"], *([row["newSignal"]] if augmented else [])]
        x = np.array([vector(r) for r in train], dtype=float)
        e = np.array([vector(r) for r in evaluation], dtype=float)
        if not np.isfinite(x).any(axis=0).all():
            raise ValueError("ALL_MISSING_TRAINING_COLUMN")
        medians = np.nanmedian(x, axis=0)
        x = np.where(np.isnan(x), medians, x)
        e = np.where(np.isnan(e), medians, e)
        mean, scale = x.mean(axis=0), x.std(axis=0)
        scale[scale == 0] = 1
        x = np.column_stack([np.ones(len(x)), (x - mean) / scale])
        e = np.column_stack([np.ones(len(e)), (e - mean) / scale])
        penalty = np.eye(x.shape[1])
        penalty[0, 0] = 0
        beta = np.linalg.solve(x.T @ x + penalty, x.T @ y)
        return (e @ beta).tolist()
    return {"status": "SYNTHETIC_ONLY", "trainingRows": len(train),
            "baseline": fit(False), "augmented": fit(True), "tuningTrials": 0}


def sensitivity_members(members, signal, excluded_industries):
    """Freeze sensitivities before labels, without choosing a favorable sector.

    The industry exclusion list must come from the proposed dated taxonomy.
    Largest two are determined by SIGNAL-date capitalization, not future winners.
    Neither a missing cap nor an unknown industry disappears silently.
    """
    day(signal)
    keys = [r["security"] for r in members]
    if len(set(keys)) != len(keys) or not members:
        raise ValueError("INVALID_MEMBERSHIP")
    if any(not r.get("industry") or type(r.get("marketCap")) not in (int, float)
           or not math.isfinite(r["marketCap"]) or r["marketCap"] <= 0 for r in members):
        raise ValueError("SENSITIVITY_METADATA_UNRESOLVED")
    top_two = {r["security"] for r in sorted(members, key=lambda r: (-r["marketCap"], r["security"]))[:2]}
    return {"FULL": keys, "EXCLUDE_2025_2026": keys if signal < "2025-01-01" else [],
            "EXCLUDE_SIGNAL_TOP2": [r["security"] for r in members if r["security"] not in top_two],
            "EXCLUDE_FIXED_INDUSTRIES": [r["security"] for r in members if r["industry"] not in excluded_industries]}


def holder_return(path, sessions, signal, horizon, buy_bps, sell_bps, domain):
    """Source-admitted shareholder wealth, including delivered rights/distributions.

    Synthetic values stand for *certified* shareholder wealth and executable
    entry open, never adjusted index / unadjusted volume mixtures. A suspension
    may be held only with an explicitly verified mark; its exit cannot trade.
    Missing marks, unresolved rights/delistings and incomplete dividends block.
    This primitive does not certify a real source or invent the wealth series.
    """
    if domain != "SYNTHETIC_ONLY":
        raise ValueError("REAL_HISTORY_EXECUTION_NOT_IMPLEMENTED_OR_AUTHORIZED")
    if horizon not in (126, 252) or sessions != sorted(set(sessions)):
        raise ValueError("INVALID_HORIZON_OR_CALENDAR")
    if any(type(v) not in (float, int) or not math.isfinite(v) or v < 0 or v >= 10000
           for v in (buy_bps, sell_bps)):
        raise ValueError("INVALID_COST")
    i = sessions.index(signal)
    expected = sessions[i + 1:i + horizon + 1]
    if len(expected) != horizon or [r.get("date") for r in path] != expected:
        raise ValueError("INCOMPLETE_EXCHANGE_SESSION_PATH")
    for r in path:
        if r.get("economics") != "SYNTHETIC_VERIFIED_SHAREHOLDER_WEALTH":
            raise ValueError("UNRESOLVED_DISTRIBUTION_OR_CORPORATE_ACTION")
        if type(r.get("wealth")) not in (int, float) or not math.isfinite(r["wealth"]) or r["wealth"] < 0:
            raise ValueError("UNRESOLVED_DAILY_MARK")
    entry = path[0].get("entryOpen")
    if (type(entry) not in (int, float) or not math.isfinite(entry) or entry <= 0
            or path[0].get("tradable") is not True or path[-1].get("tradable") is not True):
        raise ValueError("NONEXECUTABLE_ENTRY_OR_EXIT")
    return path[-1]["wealth"] * (1 - sell_bps / 10000) / (entry * (1 + buy_bps / 10000)) - 1


def kr_sell_tax_bps(stamp):
    """Explicit proposal copied from existing dated policy, not the frozen typo."""
    d = day(stamp)
    if d < date(2019, 6, 3):
        return 30
    if d < date(2021, 1, 1):
        return 25
    if d < date(2023, 1, 1):
        return 23
    if d < date(2024, 1, 1):
        return 20
    if d < date(2025, 1, 1):
        return 18
    if d < date(2026, 1, 1):
        return 15
    return 20


def holm(p_values):
    if not p_values or any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1 for p in p_values):
        raise ValueError("INVALID_MULTIPLICITY_FAMILY")
    order = sorted(range(len(p_values)), key=p_values.__getitem__)
    out, previous = [0.] * len(order), 0.
    for rank, index in enumerate(order):
        previous = max(previous, min(1., p_values[index] * (len(order) - rank)))
        out[index] = previous
    return out


def synthetic_uncertainty(blocks, minimum_blocks, family_size, domain):
    """Each comparison counts its OWN independent blocks, not pooled cohorts.

    Normal MDE is an optimistic planning approximation, not achieved power.
    Bounds use bootstrap of independent nonoverlapping blocks; real weekly
    overlapping labels require year/block resampling in a future audited runner.
    No synthetic statistic can nominate a stock signal.
    """
    if domain != "SYNTHETIC_ONLY":
        raise ValueError("REAL_HISTORY_EXECUTION_NOT_IMPLEMENTED_OR_AUTHORIZED")
    if type(minimum_blocks) is not int or minimum_blocks < 3 or type(family_size) is not int or family_size < 1:
        raise ValueError("INVALID_STATISTICAL_SPEC")
    ids = [r["block"] for r in blocks]
    if len(set(ids)) != len(ids):
        raise ValueError("DUPLICATE_INDEPENDENT_BLOCK")
    values = [r["delta"] for r in blocks if type(r.get("delta")) in (int, float) and math.isfinite(r["delta"])]
    n = len(values)
    out = {"intendedBlocks": len(blocks), "validBlocks": n, "status": "INSUFFICIENT_VALID_BLOCKS",
           "mean": None, "ci95": None, "mde80NormalApprox": None, "promotionEligible": False}
    if n < minimum_blocks:
        return out
    if n != len(blocks):
        return {**out, "status": "BLOCKED_INCOMPLETE_BLOCKS"}
    a = np.array(values, dtype=float)
    sd = float(a.std(ddof=1))
    if sd == 0:
        return {**out, "status": "DEGENERATE_UNCERTAINTY"}
    rng = np.random.default_rng(290286)
    means = np.mean(rng.choice(a, size=(5000, n)), axis=1)
    z = NormalDist().inv_cdf(1 - .05 / (2 * family_size)) + NormalDist().inv_cdf(.8)
    return {**out, "status": "SYNTHETIC_DESCRIPTIVE_ONLY", "mean": float(a.mean()),
            "ci95": [float(x) for x in np.quantile(means, [.025, .975])],
            "mde80NormalApprox": z * sd / math.sqrt(n)}
