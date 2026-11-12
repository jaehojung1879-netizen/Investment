"""c2-fixed-exposure-attribution-v1 — deterministic economics of the FIXED saved KR C2 path.

C2 (study ``weekly-passive-first-v1-replay-corrected-benchmark``) holds, for each of
155 blocks of 21 sessions, the sealed CHAMPION stock weights ``w_j`` and puts the
residual ``e = 1 - sum(w)`` in 069500.KS. Nothing here changes a selection, a date
or a weight. This module only answers, block by block and then over H126/H252:

    C2 - ETF  =  SELECTION  +  EXPOSURE  -  (cost difference)

with an exposure that was knowable when the block was traded::

    s     = sum_j w_j                                  stock sleeve weight
    R_S   = sum_j w_j r_j / s                          stock sleeve return (buy and hold)
    b     = sum_j w_j beta_j / s                       ex-ante sleeve beta, from closes
                                                       STRICTLY up to the signal date
    control  = (e + s*b) * ETF  +  s*(1-b) * CASH      the tradable fixed-exposure twin
    SELECTION = s * (R_S - b*R_E - (1-b)*R_F)          C2 gross - control gross
    EXPOSURE  = s * (b - 1) * (R_E - R_F)              control gross - ETF gross

Both identities are exact (checked on every block). ``b`` is never a full-sample
estimate. When the control would need ``e + s*b > 1`` (leverage) or ``< 0`` it is
clipped and the clip is reported, because the untradable twin is not a control.

Cash ``R_F`` is a SCENARIO, never a measured investable return: no investable KRW
cash series is pinned in this repository (SOURCE_BLOCKED). The registered band is
{ZERO, BOK_POLICY_PROXY, BOK_POLICY_PLUS_100BP}; a verdict needs all three to agree.

Pure functions only. No file, network, price store or ledger is read here; the
runner (``c2_attribution_run.py``) supplies inputs and refuses to touch real C2
outcomes without the owner's exact-hash authorization.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

TOL = 1e-9
BETA_WINDOW_RETURNS = 252          # 253 closes, signal date inclusive
BETA_MIN_RETURNS = 200
BLOCKS_H126 = 6                    # 6 x 21 sessions
BLOCKS_H252 = 12                   # 12 x 21 sessions
CASH_SCENARIOS = ("ZERO", "BOK_POLICY_PROXY", "BOK_POLICY_PLUS_100BP")
COST_MULTIPLIERS = (1.0, 2.0, 3.0)


class AttributionError(ValueError):
    """A registered identity or input contract failed; the block is not attributable."""


# --------------------------------------------------------------------------- #
# per-name inputs
# --------------------------------------------------------------------------- #
def ols_beta(stock_returns, etf_returns, *, minimum=BETA_MIN_RETURNS):
    """OLS slope of stock on ETF daily returns over pairs where BOTH are finite.

    Returns ``(beta, n)`` or ``(None, n)`` when fewer than ``minimum`` pairs exist or
    the ETF has no variance. Never fills a missing return.
    """
    if len(stock_returns) != len(etf_returns):
        raise AttributionError("BETA_INPUT_LENGTH_MISMATCH")
    pairs = [(float(s), float(e)) for s, e in zip(stock_returns, etf_returns)
             if s is not None and e is not None and math.isfinite(s) and math.isfinite(e)]
    n = len(pairs)
    if n < minimum:
        return None, n
    mx = sum(e for _, e in pairs) / n
    my = sum(s for s, _ in pairs) / n
    vxx = sum((e - mx) ** 2 for _, e in pairs)
    if vxx <= 0:
        return None, n
    vxy = sum((e - mx) * (s - my) for s, e in pairs)
    return vxy / vxx, n


def growth_from_terminal(weights, terminal_weights, gross_return, cash_weight, cash_growth):
    """Recover each name's block growth from a replay valuation row.

    ``replay_valuation.window`` is buy-and-hold inside a block: terminal weight
    ``tw_j = w_j * G_j / (1 + R)``, and ``1 + R = sum_j w_j G_j + c * G_F``. Both are
    re-checked; a row that fails either (e.g. a corporate-action successor) raises.
    """
    one_plus = 1.0 + float(gross_return)
    growth = {}
    for ticker, w in weights.items():
        if ticker not in terminal_weights:
            raise AttributionError(f"TERMINAL_WEIGHT_MISSING:{ticker}")
        if w <= 0:
            raise AttributionError(f"NON_POSITIVE_WEIGHT:{ticker}")
        growth[ticker] = float(terminal_weights[ticker]) * one_plus / float(w)
    extra = set(terminal_weights) - set(weights)
    if extra:
        raise AttributionError("SUCCESSOR_OR_UNEXPECTED_TERMINAL_HOLDING:" + ",".join(sorted(extra)))
    rebuilt = sum(float(w) * growth[t] for t, w in weights.items()) + float(cash_weight) * float(cash_growth)
    if abs(rebuilt - one_plus) > 1e-7:
        raise AttributionError(f"BUY_AND_HOLD_IDENTITY_FAILED:{rebuilt - one_plus:.3e}")
    return growth


# --------------------------------------------------------------------------- #
# block attribution
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Block:
    date: str
    end_date: str
    signal_date: str
    weights: dict                     # stock target weights (C2 sleeve), sum <= 1
    growth: dict                      # 1 + r_j per name over the block
    betas: dict                       # ex-ante beta per name, None if unavailable
    etf_growth: float                 # 1 + R_E (Phase C reconciled gross ETF TR)
    cash_growth: dict                 # scenario -> 1 + R_F
    years: float                      # elapsed calendar years of the block


@dataclass
class BlockResult:
    date: str
    status: str
    stock_weight: float = 0.0
    beta: float | None = None
    control_equity: float | None = None
    clip: str | None = None
    c2_gross: float | None = None
    etf: float | None = None
    by_cash: dict = field(default_factory=dict)


def attribute_block(block: Block) -> BlockResult:
    s = sum(block.weights.values())
    if s < -TOL or s > 1 + TOL:
        raise AttributionError("STOCK_WEIGHT_OUT_OF_RANGE")
    e = 1.0 - s
    r_e = block.etf_growth - 1.0
    if s <= TOL:
        # an all-ETF block: C2 == ETF == control, nothing to attribute
        res = BlockResult(block.date, "ALL_ETF", 0.0, None, 1.0, None, r_e, r_e)
        for name, g in block.cash_growth.items():
            res.by_cash[name] = {"control": r_e, "selection": 0.0, "exposure": 0.0}
        return res
    missing = sorted(t for t in block.weights if block.betas.get(t) is None)
    if missing:
        return BlockResult(block.date, "BETA_UNAVAILABLE:" + ",".join(missing), s)
    r_s = sum(w * (block.growth[t] - 1.0) for t, w in block.weights.items()) / s
    b = sum(w * block.betas[t] for t, w in block.weights.items()) / s
    c2 = e * r_e + s * r_s
    equity = e + s * b
    clip = None
    if equity > 1.0:
        equity, clip = 1.0, "LEVERAGE_REQUIRED_CAPPED_AT_ETF_100"
    elif equity < 0.0:
        equity, clip = 0.0, "NEGATIVE_EXPOSURE_FLOORED_AT_0"
    res = BlockResult(block.date, "ATTRIBUTED", s, b, equity, clip, c2, r_e)
    for name, g in block.cash_growth.items():
        r_f = g - 1.0
        control = equity * r_e + (1.0 - equity) * r_f
        selection = c2 - control
        exposure = control - r_e
        if abs((selection + exposure) - (c2 - r_e)) > TOL:
            raise AttributionError("ATTRIBUTION_IDENTITY_FAILED")
        if clip is None:
            closed = s * (r_s - b * r_e - (1 - b) * r_f)
            if abs(closed - selection) > TOL:
                raise AttributionError("SELECTION_CLOSED_FORM_MISMATCH")
        res.by_cash[name] = {"control": control, "selection": selection, "exposure": exposure}
    return res


# --------------------------------------------------------------------------- #
# costs and turnover
# --------------------------------------------------------------------------- #
def turnover_split(prior_terminal: dict, target: dict, etf: str):
    """One-way turnover split into names REPLACED and weights RETARGETED (AGENTS v2.11).

    ``prior_terminal`` are drifted weights at the end of the previous block (stocks
    and the ETF leg); ``target`` the new block's weights. The ETF leg is a weight
    change, never a name replacement.
    """
    replaced = retargeted = 0.0
    for t in set(prior_terminal) | set(target):
        a, b = float(prior_terminal.get(t, 0.0)), float(target.get(t, 0.0))
        d = abs(b - a)
        if d < 1e-12:
            continue
        if t != etf and (a == 0.0 or b == 0.0):
            replaced += d
        else:
            retargeted += d
    return replaced / 2.0, retargeted / 2.0


def trade_cost(prior_terminal: dict, target: dict, etf: str, cost_fn, as_of: str, multiplier=1.0):
    """Cost fraction of NAV, charged with the dated region/side schedule ``cost_fn``.

    ``cost_fn(as_of, side, is_benchmark) -> fraction per unit traded`` is the
    repository's ``weekly_decision.trade_cost_fraction`` bound to KR in the runner.
    """
    cost = 0.0
    for t in sorted(set(prior_terminal) | set(target)):
        d = float(target.get(t, 0.0)) - float(prior_terminal.get(t, 0.0))
        if abs(d) < 1e-12:
            continue
        cost += abs(d) * cost_fn(as_of, "buy" if d > 0 else "sell", t == etf)
    return cost * multiplier


# --------------------------------------------------------------------------- #
# path statistics
# --------------------------------------------------------------------------- #
def chain(returns):
    nav, out = 1.0, []
    for r in returns:
        nav *= 1.0 + r
        out.append(nav)
    return out


def max_drawdown(navs):
    peak, worst = -math.inf, 0.0
    for v in navs:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1.0)
    return worst


def cagr(navs, years):
    if not navs or years <= 0 or navs[-1] <= 0:
        return None
    return navs[-1] ** (1.0 / years) - 1.0


def jensen_split(cand, bench, years):
    """Annual log-growth gap = arithmetic active + Jensen term (exact; #309's identity)."""
    log_gap = sum(math.log1p(c) - math.log1p(b) for c, b in zip(cand, bench)) / years
    arith = sum(c - b for c, b in zip(cand, bench)) / years
    return {"logGrowthGap": log_gap, "arithmeticActive": arith, "jensen": log_gap - arith}


def windows(returns, k):
    """Compounded returns of every run of ``k`` consecutive blocks (overlapping)."""
    out = []
    for i in range(len(returns) - k + 1):
        nav = 1.0
        for r in returns[i:i + k]:
            nav *= 1.0 + r
        out.append(nav - 1.0)
    return out


def newey_west(series, lag):
    """Mean, Bartlett-HAC standard error and 95% normal interval. ``None`` if n<=lag+1."""
    xs = [x for x in series if x is not None]
    n = len(xs)
    if n <= lag + 1:
        return {"n": n, "mean": None, "se": None, "ci95": None}
    m = sum(xs) / n
    d = [x - m for x in xs]
    var = sum(v * v for v in d) / n
    for k in range(1, lag + 1):
        w = 1.0 - k / (lag + 1.0)
        var += 2.0 * w * sum(d[t] * d[t - k] for t in range(k, n)) / n
    se = math.sqrt(max(var, 0.0) / n)
    return {"n": n, "mean": m, "se": se, "ci95": [m - 1.959964 * se, m + 1.959964 * se]}


def verdict(per_scenario: dict) -> str:
    """Registered decision on the annualized SELECTION term (cost 1x).

    ``per_scenario[name] = {"mean":..., "ci95":[lo,hi], "mean2x":...}`` for each cash
    scenario. Needs all three cash scenarios; agreement is required in both directions.
    """
    if set(per_scenario) != set(CASH_SCENARIOS) or any(v.get("ci95") is None for v in per_scenario.values()):
        return "SOURCE_OR_SAMPLE_INSUFFICIENT"
    lows = [v["ci95"][0] for v in per_scenario.values()]
    highs = [v["ci95"][1] for v in per_scenario.values()]
    if all(lo > 0 for lo in lows) and all((v.get("mean2x") or -1) > 0 for v in per_scenario.values()):
        return "SELECTION_SURVIVES_FIXED_EXPOSURE"
    if all(hi < 0 for hi in highs):
        return "SELECTION_NEGATIVE_AFTER_FIXED_EXPOSURE"
    return "NO_SELECTION_EVIDENCE_CI_CONTAINS_ZERO"


def summarize(results: list[BlockResult], c2_net: list, control_net: dict, etf_net: list,
              years_total: float, blocks_per_year: float) -> dict:
    """Path summary. ``control_net[scenario]`` / ``c2_net`` / ``etf_net`` are block net returns."""
    attributed = [r for r in results if r.status in ("ATTRIBUTED", "ALL_ETF")]
    unavailable = [r for r in results if r.status.startswith("BETA_UNAVAILABLE")]
    out = {"blocks": len(results), "attributed": len(attributed), "betaUnavailable": len(unavailable),
           "clipped": sum(1 for r in results if r.clip), "c2": {}, "etf": {}, "scenarios": {}}
    def complete(series):
        return bool(series) and all(x is not None and math.isfinite(x) for x in series)

    for label, series in (("c2", c2_net), ("etf", etf_net)):
        if not complete(series):
            # one unvalued block breaks the compounded path; nothing is renormalised
            out[label] = {"status": "PATH_INCOMPLETE", "cagr": None, "mdd": None, "h126": None, "h252": None}
            continue
        navs = chain(series)
        out[label] = {"status": "COMPLETE", "cagr": cagr(navs, years_total), "mdd": max_drawdown([1.0] + navs),
                      "h126": windows(series, BLOCKS_H126), "h252": windows(series, BLOCKS_H252)}
    for name in CASH_SCENARIOS:
        sel = [r.by_cash[name]["selection"] if name in r.by_cash else None for r in results]
        ctrl = control_net.get(name) or []
        paths_ok = complete(ctrl) and complete(c2_net)
        out["scenarios"][name] = {
            "selectionAnnualized": newey_west([x * blocks_per_year if x is not None else None for x in sel],
                                              BLOCKS_H126 - 1),
            "controlCagr": cagr(chain(ctrl), years_total) if paths_ok else None,
            "c2VsControl": jensen_split(c2_net, ctrl, years_total) if paths_ok else None,
        }
    out["c2VsEtf"] = (jensen_split(c2_net, etf_net, years_total)
                      if complete(c2_net) and complete(etf_net) else None)
    return out
