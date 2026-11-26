"""MVMA-v1 Phase 2: the one authorized exploratory execution of H1-US-TRAILING and H2-US-VM1T.

Nothing here chooses a rule. Signals and targets are read from the ledger frozen in PR #357
(`evidence/us-signal-readiness.csv`, rebuilt and compared by a test); every constant is read from the sealed
`protocol.json` through `protocol.load_protocol()`; LEVEL / TIMING / COST is #316's `decompose`, vendored byte-for-byte
(`vendor/market_timing_pr316.py`, git blob dabc7ee0, checked by `execute_phase2.py` before it runs).

Conventions (stated, not tuned):
* A period runs from one execution close (next session after a month-end decision) to the next. A portfolio set to
  weight x at the start of a period and left to drift earns exactly x R_E + (1 - x) R_F over it, so the monthly series
  is exact and the decomposition's arithmetic identity holds on it.
* The daily NAV drifts inside the month and is reset to the target at each execution. Costs are charged on every trade
  actually made (target change AND drift reset), both legs, at the protocol's one-way rate. The first build is uncharged
  for every policy (#316 convention). The decomposition's COST term charges target changes only (#316 convention); the
  gap to the NAV is reported as a residual.
* p-values are TWO-SIDED (the protocol names the expected sign but not the sidedness; two-sided is the conservative
  reading) and Holm is applied to the PRIMARY family only.
"""
from __future__ import annotations

import bisect
import csv
import gzip
import math
from pathlib import Path

import numpy as np

from . import features as F
from .vendor import market_timing_pr316 as MT

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
READINESS_CSV = HERE / "evidence/us-signal-readiness.csv"
SPY_FILE = REPO / "data/research/us-dual-benchmark-v1/spy-qqq-total-return.csv.gz"
BIL_CHART = HERE / "data/raw/yahoo-BIL-chart-20261110.json.gz"
BIL_ISSUER = HERE / "data/ssga-BIL-distributions.csv"
POLICIES = ("B0", "B1", "B2", "V1", "M1T", "VM1T", "D1")
DYNAMIC = ("V1", "M1T", "VM1T", "D1")


# ------------------------------------------------------------------ inputs

def load_spy(path: Path = SPY_FILE) -> tuple[list[str], dict[str, float], dict[str, float]]:
    dates, tr, raw = [], {}, {}
    with gzip.open(path, "rt") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row["ticker"] != "SPY":
                continue
            dates.append(row["date"])
            tr[row["date"]] = float(row["totalReturnClose"])
            raw[row["date"]] = float(row["rawClose"])
    return dates, tr, raw


def load_ledger(path: Path = READINESS_CSV) -> list[dict]:
    rows = []
    for row in csv.DictReader(path.open()):
        parsed = dict(row)
        for key in ("cheap", "earningsStable", "creditStress", "deepDrawdown"):
            parsed[key] = {"True": True, "False": False}.get(row.get(key, ""), None)
        for key in ("pe", "spread"):
            parsed[key] = float(row[key]) if row.get(key) not in ("", "None", None) else None
        for policy in DYNAMIC:
            value = row.get("target" + policy, "")
            parsed["target" + policy] = float(value) if value else None
        rows.append(parsed)
    return rows


def month_end_sessions(sessions: list[str], first_month: str, last_month: str) -> list[str]:
    by_month: dict[str, str] = {}
    for s in sessions:
        if first_month <= s[:7] <= last_month:
            by_month[s[:7]] = max(by_month.get(s[:7], s), s)
    return [by_month[k] for k in sorted(by_month)]


def add_months(month: str, k: int) -> str:
    index = int(month[:4]) * 12 + int(month[5:7]) - 1 + k
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def next_session(sessions: list[str], date: str, k: int = 1) -> str:
    i = bisect.bisect_right(sessions, date)
    return sessions[i + k - 1]


# ------------------------------------------------------------------ portfolio arithmetic

def period_returns(index: dict[str, float], starts: list[str], ends: list[str]) -> np.ndarray:
    return np.array([index[e] / index[s] - 1.0 for s, e in zip(starts, ends)])


def nav_path(targets: list[float], execs: list[str], sessions: list[str], spy: dict[str, float],
             bil: dict[str, float], one_way: float, stress: float = 1.0) -> dict:
    """Daily NAV, drifting inside each period and reset to the target at each execution (len(execs) = len(targets) + 1)."""
    if len(execs) != len(targets) + 1:
        raise ValueError("EXECS_MUST_BOUND_EVERY_PERIOD")
    if any(not 0.0 <= w <= 1.0 for w in targets):
        raise AssertionError("LEVERAGE_OR_SHORT_TARGET")
    rate = one_way * stress
    value, cost_total, turnover = 1.0, 0.0, 0.0
    nav = {execs[0]: 1.0}
    equity, cash = targets[0] * value, (1.0 - targets[0]) * value
    for k in range(len(targets)):
        start, end = execs[k], execs[k + 1]
        i0, i1 = bisect.bisect_left(sessions, start), bisect.bisect_left(sessions, end)
        e0, c0 = equity, cash
        for s in sessions[i0 + 1:i1 + 1]:
            equity, cash = e0 * spy[s] / spy[start], c0 * bil[s] / bil[start]
            nav[s] = equity + cash
        value = equity + cash
        if k + 1 < len(targets):
            drifted = equity / value
            traded = abs(targets[k + 1] - drifted) * value
            cost = rate * 2.0 * traded          # buy one leg, sell the other
            turnover += traded / value
            cost_total += cost
            value -= cost
            equity, cash = targets[k + 1] * value, (1.0 - targets[k + 1]) * value
            nav[end] = value
    return {"nav": nav, "cost": cost_total, "turnover": turnover}


def monthly_from_nav(nav: dict[str, float], execs: list[str]) -> np.ndarray:
    return np.array([nav[b] / nav[a] - 1.0 for a, b in zip(execs, execs[1:])])


def path_metrics(nav: dict[str, float], monthly: np.ndarray, cash_monthly: np.ndarray) -> dict:
    dates = sorted(nav)
    values = np.array([nav[d] for d in dates])
    days = (np.datetime64(dates[-1]) - np.datetime64(dates[0])).astype(int)
    cagr = values[-1] ** (365.25 / days) - 1.0
    peak = np.maximum.accumulate(values)
    excess = monthly - cash_monthly
    sd = float(excess.std(ddof=1))
    downside = excess[excess < 0]
    growth = np.cumprod(1.0 + monthly)
    rolling12 = growth[11:] / np.concatenate([[1.0], growth[:-12]]) - 1.0
    return {"cagr": float(cagr), "maxDrawdown": float((values / peak - 1.0).min()),
            "annualVolatility": float(monthly.std(ddof=1) * math.sqrt(12)),
            "sharpe": float(excess.mean() / sd * math.sqrt(12)) if sd > 0 else None,
            "sortino": (float(excess.mean() / math.sqrt((downside ** 2).sum() / excess.size) * math.sqrt(12))
                        if downside.size else None),
            "worstMonth": float(monthly.min()), "worst12Months": float(rolling12.min()),
            "terminalValue": float(values[-1])}


def equal_volatility_weight(r_e: np.ndarray, r_f: np.ndarray, target_vol: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if (mid * r_e + (1 - mid) * r_f).std(ddof=1) < target_vol:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ------------------------------------------------------------------ inference

def normal_two_sided_p(t: float) -> float:
    return math.erfc(abs(t) / math.sqrt(2.0))


def hac_ols(y: np.ndarray, x: np.ndarray, lag: int) -> dict:
    """OLS of y on [1, x] with a Bartlett-kernel Newey-West covariance; returns the slope, its SE, t and two-sided p."""
    X = np.column_stack([np.ones_like(x, dtype=float), x.astype(float)])
    n = y.size
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    u = y - X @ beta
    g = X * u[:, None]
    s = g.T @ g
    for k in range(1, min(lag, n - 1) + 1):
        w = 1.0 - k / (lag + 1.0)
        gamma = g[k:].T @ g[:-k]
        s += w * (gamma + gamma.T)
    cov = xtx_inv @ s @ xtx_inv
    se = math.sqrt(cov[1, 1])
    t = beta[1] / se
    return {"intercept": float(beta[0]), "slope": float(beta[1]), "se": se, "t": float(t),
            "pTwoSided": normal_two_sided_p(t), "n": int(n), "lag": lag}


def block_bootstrap(n: int, block: int, replicates: int, seed: int, statistic) -> np.ndarray:
    """Moving-block bootstrap: blocks of `block` consecutive indices, uniform starts, concatenated and cut to n."""
    rng = np.random.default_rng(seed)
    blocks = math.ceil(n / block)
    out = []
    for _ in range(replicates):
        starts = rng.integers(0, n - block + 1, size=blocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        value = statistic(idx)
        if value is not None:
            out.append(value)
    return np.array(out)


def percentile_ci(draws: np.ndarray) -> list[float] | None:
    return [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))] if draws.size else None


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    items = sorted(pvalues.items(), key=lambda kv: kv[1])
    m, running, out = len(items), 0.0, {}
    for i, (name, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[name] = running
    return out


# ------------------------------------------------------------------ H1

def conditional_difference(y: np.ndarray, d: np.ndarray, lag: int, block: int, replicates: int, seed: int) -> dict:
    ols = hac_ols(y, d, lag)

    def stat(idx):
        dd, yy = d[idx], y[idx]
        if dd.all() or not dd.any():
            return None
        return float(yy[dd].mean() - yy[~dd].mean())

    draws = block_bootstrap(y.size, block, replicates, seed, stat)
    return {"meanCheap": float(y[d].mean()), "meanNotCheap": float(y[~d].mean()), "nCheap": int(d.sum()),
            "nNotCheap": int((~d).sum()), "difference": ols["slope"], "hac": ols,
            "bootstrap": {"block": block, "replicates": replicates, "valid": int(draws.size), "ci95": percentile_ci(draws)}}


def forward_excess(spy: dict, bil: dict, execs: list[str], horizon: int, count: int) -> tuple[np.ndarray, np.ndarray]:
    starts, ends = execs[:count], execs[horizon:horizon + count]
    return period_returns(spy, starts, ends) - period_returns(bil, starts, ends), period_returns(spy, starts, ends)


# ------------------------------------------------------------------ robustness helper

def median_cheap(pe: list[float | None], index: int) -> bool | None:
    if index < F.PE_HISTORY_MONTHS or pe[index] is None:
        return None
    sample = [v for v in pe[index - F.PE_HISTORY_MONTHS:index] if v is not None]
    if len(sample) < F.PE_HISTORY_MIN_VALID:
        return None
    return pe[index] < float(np.median(sample))


# ------------------------------------------------------------------ DCA (separate, descriptive)

def xirr(flows: list[tuple[str, float]]) -> float | None:
    t0 = np.datetime64(flows[0][0])
    years = np.array([(np.datetime64(d) - t0).astype(int) / 365.25 for d, _ in flows])
    amounts = np.array([a for _, a in flows])

    def npv(r):
        return float((amounts / (1 + r) ** years).sum())

    lo, hi = -0.99, 1.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def run_dca(rule: str, triggers: list[bool | None], execs: list[str], spy: dict, bil: dict, one_way: float,
            parked_fraction: float) -> dict:
    """1 unit at every execution; A invests all; B/C park `parked_fraction` until their trigger, then deploy all parked."""
    equity = cash = 0.0
    contributed, cost = 0.0, 0.0
    flows, parked_share = [], []
    for k, date in enumerate(execs[:-1]):
        if k:
            prev = execs[k - 1]
            equity *= spy[date] / spy[prev]
            cash *= bil[date] / bil[prev]
        contributed += 1.0
        flows.append((date, -1.0))
        if rule == "DCA-A" or triggers[k]:
            buy = 1.0 + cash
            cost += one_way * (1.0 + 2.0 * cash)     # new money buys one leg; parked cash sells BIL and buys SPY
            equity += buy - one_way * (1.0 + 2.0 * cash)
            cash = 0.0
        else:
            invest = 1.0 - parked_fraction
            cost += one_way * invest
            equity += invest - one_way * invest
            cash += parked_fraction
        parked_share.append(cash / (equity + cash))
    last, end = execs[-2], execs[-1]
    equity *= spy[end] / spy[last]
    cash *= bil[end] / bil[last]
    terminal = equity + cash
    flows.append((end, terminal))
    return {"rule": rule, "contributed": contributed, "terminalValue": terminal, "xirr": xirr(flows),
            "parkedAtEnd": cash, "deploymentRatioAtEnd": equity / terminal, "averageParkedShare": float(np.mean(parked_share)),
            "costPaid": cost}


# ------------------------------------------------------------------ the registered analysis

def _window_rows(ledger: list[dict], spec: dict) -> list[dict]:
    window = spec["calendar"]["evaluationWindowUS"]
    rows = [r for r in ledger if window["firstDecision"] <= r["decisionDate"] <= window["lastDecision"]]
    if len(rows) != window["months"]:
        raise AssertionError(f"WINDOW_ROW_COUNT {len(rows)} != {window['months']}")
    return rows


def _targets(rows: list[dict], policy: str, spec: dict) -> list[float]:
    static = spec["policies"][policy].get("weight")
    if static is not None:
        return [float(static)] * len(rows)
    return [r["target" + policy] for r in rows]


def _policy_block(name, targets, execs, sessions, spy, bil, r_e, r_f, cash_m, one_way, stress=1.0):
    gross = nav_path(targets, execs, sessions, spy, bil, 0.0)
    net = nav_path(targets, execs, sessions, spy, bil, one_way, stress)
    m_gross, m_net = monthly_from_nav(gross["nav"], execs), monthly_from_nav(net["nav"], execs)
    if np.max(np.abs(m_gross - MT.overlay_returns(targets, r_e, r_f))) > 1e-10:
        raise AssertionError("DRIFTING_NAV_DISAGREES_WITH_PERIOD_IDENTITY: " + name)
    return {"averageTarget": float(np.mean(targets)), "turnoverOneWaySum": net["turnover"],
            "annualTurnover": net["turnover"] / (len(targets) / 12.0), "costPaid": net["cost"],
            "gross": path_metrics(gross["nav"], m_gross, cash_m), "net": path_metrics(net["nav"], m_net, cash_m),
            "_monthlyNet": m_net, "_monthlyGross": m_gross, "_navNet": net["nav"]}


def analyze(ledger: list[dict], sessions: list[str], spy: dict, bil: dict, spec: dict, delay: int = 1,
            cost_stress: float = 1.0, with_inference: bool = True) -> dict:
    rows = _window_rows(ledger, spec)
    decisions = [r["decisionDate"] for r in rows]
    # The 12-month forward window of the last decision ends at the execution after the decision 12 months later.
    month_ends = month_end_sessions(sessions, decisions[0][:7], add_months(decisions[-1][:7], 12))
    if month_ends[:len(decisions)] != decisions:
        raise AssertionError("LEDGER_DECISIONS_ARE_NOT_THE_CALENDAR_MONTH_ENDS")
    execs_all = [next_session(sessions, d, delay) for d in month_ends]
    n = len(rows)
    execs = execs_all[:n + 1]
    r_e, r_f = period_returns(spy, execs[:-1], execs[1:]), period_returns(bil, execs[:-1], execs[1:])
    one_way = spec["costs"]["US"]["oneWayBps"] / 1e4
    decomposition_cost = 2.0 * one_way * cost_stress            # both legs per unit of exposure change

    result = {"periods": n, "firstExecution": execs[0], "lastExecution": execs[-1], "executionDelaySessions": delay,
              "costStress": cost_stress, "policies": {}, "decomposition": {}}
    blocks = {}
    for policy in POLICIES:
        blocks[policy] = _policy_block(policy, _targets(rows, policy, spec), execs, sessions, spy, bil, r_e, r_f, r_f,
                                       one_way, cost_stress)
    for policy in DYNAMIC:
        x = _targets(rows, policy, spec)
        d = MT.decompose(x, r_e, r_f, decomposition_cost, decomposition_cost)
        xbar = d["averageExposure"]
        static = [xbar] * n
        static_block = _policy_block(policy + "_STATIC", static, execs, sessions, spy, bil, r_e, r_f, r_f, one_way,
                                     cost_stress)
        net_series = d["netTimingSeries"]
        nw = MT.newey_west_mean(net_series, spec["inference"]["hac"]["lagMonthlyPolicy"])
        result["decomposition"][policy] = {
            "averageExposure": xbar, "exposureChanges": d["exposureChanges"],
            "annualLevel": 12 * d["level"], "annualTiming": 12 * d["timing"], "annualCost": 12 * d["meanCost"],
            "annualTimingNetOfCost": 12 * d["timingNetOfCost"], "annualActiveGross": 12 * d["meanActiveGross"],
            "annualActiveNet": 12 * d["meanActiveNet"], "timingNetSeAnnual": 12 * nw["se"],
            "maxDrawdownMonthly": d["maxDrawdown"],
            "exposureMatchedStatic": {k: static_block[k] for k in ("gross", "net")},
            "navCagrNetMinusStaticNet": blocks[policy]["net"]["cagr"] - static_block["net"]["cagr"],
            "_netTimingSeries": net_series,
        }
    for policy, block in blocks.items():
        result["policies"][policy] = {k: v for k, v in block.items() if not k.startswith("_")}
    result["_blocks"] = blocks
    result["_rows"] = rows
    result["_execsAll"] = execs_all
    result["_rE"], result["_rF"] = r_e, r_f
    if not with_inference:
        return result

    inf = spec["inference"]
    boot = inf["bootstrap"]
    # ---------------- H1: forward 12M (primary) and 6M (secondary) SPY-minus-BIL excess, cheap vs not cheap
    cheap = np.array([r["cheap"] for r in rows], dtype=object)
    if any(c is None for c in cheap):
        raise AssertionError("H1_CHEAP_UNDETERMINED_IN_WINDOW")
    cheap = cheap.astype(bool)
    h1 = {}
    for horizon, lag in ((12, inf["hac"]["lag12M"]), (6, inf["hac"]["lag6M"])):
        excess, spy_fwd = forward_excess(spy, bil, execs_all, horizon, n)
        entry = conditional_difference(excess, cheap, lag, boot["blockMonthsPrimary"], boot["replicates"], boot["seed"])
        entry["spyTotalReturnMeanCheap"] = float(spy_fwd[cheap].mean())
        entry["spyTotalReturnMeanNotCheap"] = float(spy_fwd[~cheap].mean())
        if horizon == 12:
            entry["bootstrapBlockSensitivity"] = {
                str(b): percentile_ci(block_bootstrap(n, b, boot["replicates"], boot["seed"],
                                                      lambda idx: (None if cheap[idx].all() or not cheap[idx].any()
                                                                   else float(excess[idx][cheap[idx]].mean()
                                                                              - excess[idx][~cheap[idx]].mean()))))
                for b in boot["blockMonthsSensitivity"]}
            result["_h1Excess12"] = excess
        h1[f"H{horizon}M"] = entry
    result["H1"] = h1

    # ---------------- H2: VM1T cost-net TIMING, annualised
    series = result["decomposition"]["VM1T"]["_netTimingSeries"]
    nw = MT.newey_west_mean(series, inf["hac"]["lagMonthlyPolicy"])
    draws = block_bootstrap(n, boot["blockMonthsPrimary"], boot["replicates"], boot["seed"],
                            lambda idx: float(12 * series[idx].mean()))
    result["H2"] = {"annualTimingNetOfCost": 12 * nw["mean"], "seAnnual": 12 * nw["se"], "hacLag": nw["lag"],
                    "t": nw["mean"] / nw["se"], "pTwoSided": normal_two_sided_p(nw["mean"] / nw["se"]),
                    "bootstrapCi95Annual": percentile_ci(draws),
                    "bootstrapBlockSensitivity": {
                        str(b): percentile_ci(block_bootstrap(n, b, boot["replicates"], boot["seed"],
                                                              lambda idx: float(12 * series[idx].mean())))
                        for b in boot["blockMonthsSensitivity"]}}
    adjusted = holm({"H1-US-TRAILING": h1["H12M"]["hac"]["pTwoSided"], "H2-US-VM1T": result["H2"]["pTwoSided"]})
    result["holm"] = {"alpha": inf["multipleTesting"]["alpha"], "adjusted": adjusted}
    return result
