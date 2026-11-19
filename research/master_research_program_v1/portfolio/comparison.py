"""portfolio-d-p0-p5-comparison-v1 — one engine for P0..P5 (pure; no real outcome is read here).

Formalises the PROPOSED ``hierarchical-vs-direct-selection-comparison-v1`` design
(docs/research-program/07-market-industry-stock-portfolio-hierarchy-ko.md §7) as an executable,
prospective-only comparison:

    P0 regional ETF 100%            P1 direct stock selection (s_M)
    P2 industry baskets only (s_I)  P3 industry -> within-industry stock (s_I, then s_S|I)
    P4 industry-neutral stock       P5 additive s_I + s_S|I

Every arm is valued by the SAME function on the SAME blocks, same eligible set, same cost
schedule and same name-count policy; the engine never reads the arm label (swapping labels
gives identical paths). The market risk multiplier is OFF in the primary comparison and is
measured only as a separate increment. Cost/turnover/statistics helpers are reused from
``research/alpha_evidence_sprint_v2/c2_attribution.py`` rather than written twice.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from research.alpha_evidence_sprint_v2 import c2_attribution as A

ARMS = ("P0", "P1", "P2", "P3", "P4", "P5")
# Pre-specified comparison family (Holm across all six). Order is fixed before any outcome.
COMPARISONS = (("P1", "P0"), ("P2", "P0"), ("P3", "P1"), ("P3", "P4"), ("P4", "P0"), ("P5", "P1"))
INPUT_STATES = ("ADMITTED", "UNVALIDATED", "SOURCE_BLOCKED")
ARM_INPUTS = {"P0": (), "P1": ("stockScore",), "P2": ("industryScore",),
              "P3": ("industryScore", "withinIndustryScore"), "P4": ("withinIndustryScore",),
              "P5": ("industryScore", "withinIndustryScore")}
MAX_NAMES = 5          # Portfolio D policy: 0..5 names, 0 => ETF 100%
NW_LAG = {"H126": 5, "H252": 11}


class ComparisonError(ValueError):
    pass


@dataclass(frozen=True)
class Block:
    date: str
    signal_date: str
    growth: dict          # 1 + r per security over the block (None = unpriced/unresolved)
    etf_growth: float
    cash_growth: float = 1.0


def arm_status(input_states: dict, arm: str) -> str:
    """ADMITTED only if every input the arm needs is ADMITTED. P0 needs none."""
    states = [input_states.get(k, "SOURCE_BLOCKED") for k in ARM_INPUTS[arm]]
    for s in states:
        if s not in INPUT_STATES:
            raise ComparisonError(f"UNKNOWN_INPUT_STATE:{s}")
    if "SOURCE_BLOCKED" in states:
        return "BLOCKED_NO_QUALIFIED_INPUT"
    if "UNVALIDATED" in states:
        return "RESEARCH_PAPER_ONLY"
    return "ADMITTED"


def validate_targets(targets: dict, etf: str):
    stocks = {t: w for t, w in targets.items() if t != etf}
    if len(stocks) > MAX_NAMES:
        raise ComparisonError("MORE_THAN_MAX_NAMES")
    if any(w < -1e-12 for w in targets.values()) or sum(targets.values()) > 1 + 1e-9:
        raise ComparisonError("WEIGHTS_OUT_OF_RANGE")


def fill_etf(targets: dict, etf: str) -> dict:
    """Residual weight goes to the regional ETF (zero names => ETF 100%), never to cash."""
    stocks = {t: float(w) for t, w in targets.items() if t != etf and w > 1e-12}
    residual = 1.0 - sum(stocks.values())
    return {**stocks, etf: residual} if residual > 1e-12 else stocks


def arm_path(blocks, targets_by_block, etf, cost_fn, multiplier=1.0):
    """Net block returns of one arm. Costs are charged on the drifted prior book exactly as the
    replay's ``account()`` does. A held security with unknown growth makes that block None and
    breaks the path from there (NOT_EVALUABLE_BLOCKED_PATH), never a renormalised book."""
    prior, out = {}, []
    blocked = False
    for b, targets in zip(blocks, targets_by_block):
        validate_targets(targets, etf)
        tgt = fill_etf(targets, etf)
        if blocked:
            out.append(None)
            continue
        growth = {t: (b.etf_growth if t == etf else b.growth.get(t)) for t in tgt}
        if any(g is None for g in growth.values()):
            blocked = True
            out.append(None)
            continue
        cost = A.trade_cost(prior, tgt, etf, cost_fn, b.date, multiplier)
        gross = sum(w * growth[t] for t, w in tgt.items()) - 1.0
        out.append((1 - cost) * (1 + gross) - 1)
        end = {t: w * growth[t] for t, w in tgt.items()}
        total = sum(end.values())
        prior = {t: v / total for t, v in end.items()} if total > 0 else {}
    return out


def multiplier_increment(blocks, base_returns, equity_multipliers):
    """Separately reported market-layer increment: scale the finished arm's equity by m_t (<=1),
    the rest earns cash. Increment = scaled path - unscaled path, per block. Costs of the scale
    change are not added here (reported as a known simplification of the increment only)."""
    out = []
    for b, r, m in zip(blocks, base_returns, equity_multipliers):
        if r is None or m is None:
            out.append(None)
            continue
        if not 0.0 <= m <= 1.0:
            raise ComparisonError("MULTIPLIER_OUT_OF_RANGE")
        scaled = m * r + (1 - m) * (b.cash_growth - 1.0)
        out.append(scaled - r)
    return out


def _norm_p(z):
    return math.erfc(abs(z) / math.sqrt(2.0))


def paired(a, b, lag):
    """Newey-West summary of the per-block difference a-b over blocks where both exist."""
    diffs = [x - y for x, y in zip(a, b) if x is not None and y is not None]
    nw = A.newey_west(diffs, lag)
    if nw["se"] in (None, 0):
        return {**nw, "p": None}
    return {**nw, "p": _norm_p(nw["mean"] / nw["se"])}


def holm(pvalues: dict) -> dict:
    """Holm step-down adjusted p-values; a missing p stays a full-weight slot at 1.0."""
    items = sorted(((1.0 if p is None else p), k) for k, p in pvalues.items())
    m, running, out = len(items), 0.0, {}
    for i, (p, k) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


def compare(paths: dict, lag: int, alpha=0.05) -> dict:
    """Run the pre-specified family on per-arm net block returns."""
    raw = {f"{a}-{b}": paired(paths[a], paths[b], lag) for a, b in COMPARISONS}
    adj = holm({k: v["p"] for k, v in raw.items()})
    return {k: {**v, "pHolm": adj[k], "separated": adj[k] < alpha and v["mean"] is not None}
            for k, v in raw.items()}


def hierarchy_verdict(axes: dict, input_states: dict) -> str:
    """§7.3 decision. ``axes`` keys: predictive, economic, decompositionArithmeticLed,
    notIndustryConcentration, stable (bools or None). All five must pass."""
    if arm_status(input_states, "P3") == "BLOCKED_NO_QUALIFIED_INPUT":
        return "BLOCKED_NO_QUALIFIED_INPUT"
    keys = ("predictive", "economic", "decompositionArithmeticLed", "notIndustryConcentration", "stable")
    if any(axes.get(k) is None for k in keys):
        return "NOT_EVALUABLE"
    if axes["predictive"] and not axes["economic"]:
        return "PREDICTIVE_ONLY_NOT_ECONOMIC"
    if axes["economic"] and not axes["notIndustryConcentration"]:
        return "INDUSTRY_TILT_NOT_HIERARCHY"
    if all(axes[k] for k in keys):
        return "HIERARCHY_ADDS_VALUE"
    return "SIMPLER_STRUCTURE_RETAINED"


def summarize_arm(returns, years):
    if any(r is None for r in returns):
        return {"status": "NOT_EVALUABLE_BLOCKED_PATH"}
    navs = A.chain(returns)
    return {"status": "COMPLETE", "cagr": A.cagr(navs, years), "mdd": A.max_drawdown([1.0] + navs),
            "h126": A.windows(returns, A.BLOCKS_H126), "h252": A.windows(returns, A.BLOCKS_H252)}


def arm_receipt(*, region, signal_date, arm, targets, input_states, spec_sha256, etf):
    """Prospective target receipt for one arm (write-once in the caller's ledger).

    The digest is the repository's own ``prospective_receipt_core.receipt_digest``. Names are
    marked non-displayable unless the arm is ADMITTED, so a report can never show an
    unvalidated stock selection. No outcome-like key may appear (scanned by the core)."""
    from pipeline import prospective_receipt_core as core
    if arm not in ARMS:
        raise ComparisonError("UNKNOWN_ARM")
    validate_targets(targets, etf)
    status = arm_status(input_states, arm)
    receipt = {"study": "portfolio-d-p0-p5-comparison-v1", "evidenceClass": core.EVIDENCE_CLASS,
               "region": region, "signalDate": signal_date, "arm": arm, "armStatus": status,
               "specSha256": spec_sha256, "targets": fill_etf(targets, etf),
               "displayableToReport": status == "ADMITTED"}
    core.scan_for_outcome_keys(receipt)          # raises OUTCOME_FIELD_IN_RECEIPT
    receipt["receiptSha256"] = core.receipt_digest(receipt)
    return receipt
