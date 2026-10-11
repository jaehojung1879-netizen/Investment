"""us-capital-allocation-alpha-v1 — the H126 outcome record and the paired SPY / QQQ comparison. Nothing here runs on real data yet.

An outcome is a SEPARATE record keyed by the receipt's digest. It can only be built once the maturity session (126 US sessions
after the execution session) is final by the writer's own clock; it never touches the receipt. A held name that has no exit
price makes the portfolio outcome unresolved: it is never marked at a last price, never read as zero and never dropped.

The comparison is one claim tested once. For every matured signal week s:

    net(P1)_s   = sum_i w_i R_i + (1 - W) R_SPY - W * switch          W = sum w_i, switch = stock + displaced-ETF round trip
    D_SPY_s     = net(P1)_s - R_SPY_s
    D_QQQ_s     = net(P1)_s - R_QQQ_s = D_SPY_s - (R_QQQ_s - R_SPY_s)

so the SAME selected names and the SAME weeks feed both comparisons and the QQQ one differs from the SPY one by exactly the passive
spread, which is reported on its own. Consecutive weekly horizons share 121 of 126 sessions, so the weekly series is far from
independent: the interval comes from a circular moving-block bootstrap with one-horizon blocks, and the number of independent
windows is matured weeks divided by the block length, not the number of weeks.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np
import pandas as pd

from . import price_adjustment as PA
from . import prospective_receipt_core as CORE
from . import us_capital_allocation_policy as P
from . import us_capital_allocation_receipts as R

OUTCOME_LEDGER = "ledger/research/us-capital-allocation-alpha-v1/outcomes.jsonl"
OUTCOME_CLASS = {R.LIVE: "PROSPECTIVE_OUTCOME", R.SYNTHETIC: "SYNTHETIC_FIXTURE"}
PRICED, TERMINAL_CITED, TERMINAL_UNRESOLVED = "PRICED", "TERMINAL_CONSIDERATION_CITED", "TERMINAL_ECONOMICS_UNRESOLVED"
VERDICTS = ("NOT_YET_EVALUABLE", "SUCCESS", "FAILURE", "INCONCLUSIVE")


# --------------------------------------------------------------------------- #
# Returns
# --------------------------------------------------------------------------- #
def total_return_between(frame: pd.DataFrame, entry, exit_):
    """As-traded forward total return from the entry close to the exit close, or (None, reason). Never filled, never interpolated."""
    if frame is None or "Close" not in frame or not len(frame):
        return None, "NO_PRICE_FRAME"
    entry, exit_ = pd.Timestamp(entry).normalize(), pd.Timestamp(exit_).normalize()
    index = pd.DatetimeIndex(frame.index).normalize()
    if entry not in index:
        return None, "NO_ENTRY_SESSION_PRICE"
    if exit_ not in index:
        return None, "NO_EXIT_SESSION_PRICE"
    window = frame.copy()
    window.index = index
    window = window.loc[entry:exit_]
    if (pd.to_numeric(window["Close"], errors="coerce") <= 0).any() or window["Close"].isna().any():
        return None, "NON_POSITIVE_OR_MISSING_CLOSE_IN_WINDOW"
    rebased, _ = PA.to_total_return(window)
    first, last = float(rebased["Close"].iloc[0]), float(rebased["Close"].iloc[-1])
    return last / first - 1.0, None


def name_outcome(frame, entry, exit_, terminal=None):
    value, reason = total_return_between(frame, entry, exit_)
    if value is not None:
        return {"state": PRICED, "entrySession": str(pd.Timestamp(entry).date()), "exitSession": str(pd.Timestamp(exit_).date()), "totalReturn": value}
    if terminal and terminal.get("citation") and CORE.finite(terminal.get("totalReturn")):
        return {"state": TERMINAL_CITED, "entrySession": str(pd.Timestamp(entry).date()), "exitSession": str(pd.Timestamp(exit_).date()),
                "totalReturn": float(terminal["totalReturn"]), "citation": str(terminal["citation"])}
    return {"state": TERMINAL_UNRESOLVED, "reason": reason, "entrySession": str(pd.Timestamp(entry).date()),
            "exitSession": str(pd.Timestamp(exit_).date()), "totalReturn": None}


def portfolio_outcome(weights, fallback_weight, names, spy, qqq):
    """Net P1 return and both excesses, or an unresolved status. `names[t]` are name outcomes; spy/qqq are floats."""
    unresolved = sorted(t for t in weights if names.get(t, {}).get("state") not in (PRICED, TERMINAL_CITED) or not CORE.finite(names[t].get("totalReturn")))
    if unresolved:
        return {"status": TERMINAL_UNRESOLVED if any(names.get(t, {}).get("state") == TERMINAL_UNRESOLVED for t in unresolved) else "NAME_OUTCOME_MISSING",
                "unresolvedTickers": unresolved, "netReturn": None, "excessVsSPY": None, "excessVsQQQ": None}
    stock_weight = math.fsum(weights.values())
    stock_part = math.fsum(w * names[t]["totalReturn"] for t, w in sorted(weights.items()))
    gross = stock_part + fallback_weight * spy
    switch = stock_weight * P.costs_bps()["switchBpsPerUnitStockWeight"] / 1e4
    net = gross - switch
    return {"status": "COMPLETE", "unresolvedTickers": [], "stockWeight": stock_weight, "grossReturn": gross, "switchCost": switch, "netReturn": net,
            "excessVsSPY": net - spy, "excessVsQQQ": net - qqq, "passiveSpreadQQQMinusSPY": qqq - spy,
            "selectionContributionGross": stock_part - stock_weight * spy}


def build_outcome_record(receipt, *, validate, price_frames, now_utc, terminal=None):
    validate(receipt)
    now = CORE.utc(now_utc)
    exit_session = R.maturity_session(receipt["executionDate"], receipt["horizonSessions"])
    if not R.has_matured(receipt["executionDate"], receipt["horizonSessions"], now):
        raise ValueError("HORIZON_NOT_MATURED: maturity session %s is final %s" % (
            exit_session.date(), (exit_session + R.US_CLOSE_FINAL_UTC).tz_localize("UTC")))
    entry = receipt["executionDate"]
    weights = dict(receipt["decision"]["weights"] or {})
    benchmarks = {}
    for ticker in (P.OFFICIAL_BENCHMARK, P.ALTERNATIVE_BENCHMARK):
        value, reason = total_return_between(price_frames.get(ticker), entry, exit_session)
        if value is None:
            raise ValueError("BENCHMARK_OUTCOME_UNAVAILABLE: %s %s" % (ticker, reason))
        benchmarks[ticker] = value
    names = {t: name_outcome(price_frames.get(t), entry, exit_session, (terminal or {}).get(t)) for t in sorted(weights)}
    record = {"evidenceClass": OUTCOME_CLASS[receipt["pathway"]], "pathway": receipt["pathway"], "receiptSha256": receipt["receiptSha256"],
              "studyId": receipt["studyId"], "signalDate": receipt["signalDate"], "executionDate": receipt["executionDate"],
              "horizonSessions": receipt["horizonSessions"], "maturitySession": str(exit_session.date()), "createdAtUtc": now.isoformat(),
              "benchmarkReturns": benchmarks, "nameOutcomes": names,
              "portfolio": portfolio_outcome(weights, receipt["decision"]["fallbackWeight"], names, benchmarks["SPY"], benchmarks["QQQ"])
              if receipt["decision"]["status"] != "BLOCKED" else {"status": "BLOCKED_RECEIPT", "netReturn": None, "excessVsSPY": None, "excessVsQQQ": None}}
    record["recordSha256"] = hashlib.sha256(CORE.canonical(record)).hexdigest()
    return record


def build_live_outcome_record(receipt, *, price_frames, terminal=None):
    """Outcome after maturity, on the writer's own clock. There is no timestamp argument to fabricate."""
    R.validate_live_receipt(receipt)
    return build_outcome_record(receipt, validate=R.validate_live_receipt, price_frames=price_frames, now_utc=CORE.system_utc_now(), terminal=terminal)


def build_synthetic_outcome_record(receipt, *, price_frames, test_clock_utc, terminal=None):
    R.validate_synthetic_receipt(receipt)
    return build_outcome_record(receipt, validate=R.validate_synthetic_receipt, price_frames=price_frames, now_utc=test_clock_utc, terminal=terminal)


# --------------------------------------------------------------------------- #
# Inference
# --------------------------------------------------------------------------- #
def block_indices(n, block, replicates, seed):
    """Circular moving-block resampling indices, shape (replicates, n). One matrix serves every series, so pairs stay paired."""
    if n < 1 or block < 1:
        raise ValueError("EMPTY_SERIES")
    rng = np.random.Generator(np.random.PCG64(seed))
    blocks = -(-n // block)
    starts = rng.integers(0, n, size=(replicates, blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return idx.reshape(replicates, blocks * block)[:, :n]


def one_sided_bounds(values, idx, confidence=P.registration()["inference"]["confidence"]):
    means = np.asarray(values, dtype=float)[idx].mean(axis=1)
    return {"mean": float(np.mean(values)), "lower": float(np.quantile(means, 1.0 - confidence)), "upper": float(np.quantile(means, confidence))}


def _ols(x, y):
    xc = x - x.mean()
    denominator = float((xc * xc).sum())
    if denominator == 0.0:
        return None, None
    slope = float((xc * (y - y.mean())).sum() / denominator)
    return float(y.mean() - slope * x.mean()), slope


def growth_loading(d_spy, spread, idx_small):
    """Weekly SPY excess regressed on the QQQ-SPY spread. Slope = how much of the excess is the growth tilt; intercept = what is left."""
    x_all, y_all = np.asarray(spread, float), np.asarray(d_spy, float)
    intercept, slope = _ols(x_all, y_all)
    if intercept is None:
        return {"status": "SPREAD_HAS_NO_VARIATION"}
    x, y = x_all[idx_small], y_all[idx_small]
    xm, ym = x.mean(axis=1, keepdims=True), y.mean(axis=1, keepdims=True)
    xc = x - xm
    den = (xc * xc).sum(axis=1)
    ok = den > 0
    slopes = (xc * (y - ym)).sum(axis=1)[ok] / den[ok]
    intercepts = ym[ok, 0] - slopes * xm[ok, 0]
    return {"status": "MEASURED", "intercept": intercept, "slope": slope,
            "interceptInterval90": [float(np.quantile(intercepts, 0.05)), float(np.quantile(intercepts, 0.95))],
            "slopeInterval90": [float(np.quantile(slopes, 0.05)), float(np.quantile(slopes, 0.95))],
            "meaning": "descriptive; no verdict power"}


def evaluate_program(records, *, benchmark_integrity=None):
    """The single verdict computation. `records` are outcome records (matured by construction)."""
    cfg = P.registration()
    inference, gate = cfg["inference"], cfg["maturityGate"]
    rows = sorted(records, key=lambda r: r["signalDate"])
    dates = [r["signalDate"] for r in rows]
    if len(set(dates)) != len(dates):
        raise ValueError("DUPLICATE_SIGNAL_WEEK_IN_OUTCOMES")
    blocked = [r for r in rows if r["portfolio"]["status"] == "BLOCKED_RECEIPT"]
    unresolved = [r["signalDate"] for r in rows if r["portfolio"]["status"] not in ("COMPLETE", "BLOCKED_RECEIPT")]
    usable = [r for r in rows if r["portfolio"]["status"] == "COMPLETE"]
    # A BLOCKED week held only the residual asset: the book was 100% SPY. It is evaluated as such, not dropped.
    n = len(usable) + len(blocked)
    result = {"signalWeeks": len(rows), "maturedWeeks": n, "blockedWeeksHeldAsResidual": len(blocked), "unresolvedWeeks": unresolved,
              "independentWindows": n // inference["blockWeeks"], "gate": gate, "firstSignal": dates[0] if dates else None,
              "lastSignal": dates[-1] if dates else None}
    if not rows:
        return {**result, "verdict": "NOT_YET_EVALUABLE", "reasons": ["NO_MATURED_OUTCOMES"]}
    sessions = len(R._sessions(rows[0]["executionDate"], (pd.Timestamp(rows[-1]["maturitySession"]) - pd.Timestamp(rows[0]["executionDate"])).days))
    result["trackingSessions"] = sessions
    spy = np.array([r["benchmarkReturns"]["SPY"] for r in usable] + [r["benchmarkReturns"]["SPY"] for r in blocked], float)
    qqq = np.array([r["benchmarkReturns"]["QQQ"] for r in usable] + [r["benchmarkReturns"]["QQQ"] for r in blocked], float)
    d_spy = np.array([r["portfolio"]["excessVsSPY"] for r in usable] + [0.0 for _ in blocked], float)
    d_qqq = d_spy - (qqq - spy)
    selection = np.array([r["portfolio"]["selectionContributionGross"] for r in usable] + [0.0 for _ in blocked], float)
    held = np.array([len(r["nameOutcomes"]) > 0 for r in usable] + [False for _ in blocked])
    ready = (n >= gate["minMaturedSignals"] and sessions >= gate["minPaperDays"] and result["independentWindows"] >= gate["minIndependentWindows"])
    reasons = []
    if not ready:
        return {**result, "verdict": "NOT_YET_EVALUABLE", "reasons": ["MATURITY_GATE_NOT_MET"],
                "descriptive": {"meanExcessVsSPY": float(d_spy.mean()), "meanExcessVsQQQ": float(d_qqq.mean()),
                                "meanPassiveSpread": float((qqq - spy).mean()), "heldShare": float(held.mean())}}
    idx = block_indices(n, inference["blockWeeks"], inference["replicates"], inference["seed"])
    bounds = {"SPY": one_sided_bounds(d_spy, idx, inference["confidence"]), "QQQ": one_sided_bounds(d_qqq, idx, inference["confidence"])}
    result.update(bounds=bounds, heldShare=float(held.mean()),
                  decomposition={"meanSelectionContributionGross": float(selection.mean()), "meanPassiveSpreadQQQMinusSPY": float((qqq - spy).mean()),
                                 "meanSwitchCost": float(np.mean([r["portfolio"]["switchCost"] for r in usable])) if usable else 0.0},
                  growthLoading=growth_loading(d_spy, qqq - spy, idx[:2000]))
    if unresolved:
        reasons.append("UNRESOLVED_TERMINAL_OUTCOME")
    if benchmark_integrity is None or any(benchmark_integrity.get(b) != "PASS" for b in ("SPY", "QQQ")):
        reasons.append("BENCHMARK_INTEGRITY_NOT_PASS")
    if reasons:
        verdict = "INCONCLUSIVE"
    elif bounds["SPY"]["lower"] > 0 and bounds["QQQ"]["lower"] > 0 and result["heldShare"] >= 0.10:
        verdict, reasons = "SUCCESS", ["BOTH_ONE_SIDED_LOWER_BOUNDS_ABOVE_ZERO"]
    elif bounds["SPY"]["upper"] < 0 or bounds["QQQ"]["upper"] < 0:
        verdict, reasons = "FAILURE", ["UPPER_BOUND_BELOW_ZERO_FOR_A_PASSIVE_ALTERNATIVE"]
    else:
        verdict, reasons = "INCONCLUSIVE", ["NEITHER_BOTH_LOWER_BOUNDS_ABOVE_ZERO_NOR_AN_UPPER_BOUND_BELOW_ZERO"]
        if result["heldShare"] < 0.10 and bounds["SPY"]["lower"] > 0 and bounds["QQQ"]["lower"] > 0:
            reasons.append("POLICY_HELD_A_NAME_IN_FEWER_THAN_10_PERCENT_OF_WEEKS")
    return {**result, "verdict": verdict, "reasons": reasons}


# --------------------------------------------------------------------------- #
# Secondary diagnostic: does CHOOSING add anything over drawing at random from the same pool?
# --------------------------------------------------------------------------- #
def selection_null(weeks, *, draws=2000, seed=20261012, per_sector=P.MAX_NAMES_PER_SECTOR):
    """Mean selection contribution of the real picks against the same construction on random picks from the same pool.

    `weeks[i]` = {"selected": [tickers], "pool": [tickers], "returns": {ticker: total return}, "sector": {ticker: sector}, "spy": float}.
    Same count, same sector cap, same weeks; only WHICH names changes. Returns the real mean, the null distribution's mean and the
    +1-corrected one-sided p-value (never zero). Descriptive: no verdict power.
    """
    if not weeks:
        return {"realMean": None, "nullMean": None, "nullP95": None, "pValueOneSided": None, "draws": draws, "meaning": "descriptive; no verdict power"}
    rng = np.random.Generator(np.random.PCG64(seed))

    def contribution(picks, week):
        return math.fsum(P.SLOT_WEIGHT * (week["returns"][t] - week["spy"]) for t in picks)

    real = float(np.mean([contribution(w["selected"], w) for w in weeks])) if weeks else None
    null = np.zeros(draws)
    for d in range(draws):
        total = 0.0
        for week in weeks:
            k = len(week["selected"])
            pool = sorted(week["pool"])
            order = rng.permutation(len(pool))
            picks, count = [], {}
            for i in order:
                ticker = pool[i]
                sector = week.get("sector", {}).get(ticker)
                if len(picks) >= k:
                    break
                if count.get(sector, 0) >= per_sector:
                    continue
                picks.append(ticker)
                count[sector] = count.get(sector, 0) + 1
            total += contribution(picks, week)
        null[d] = total / len(weeks)
    p_value = (1 + int((null >= real).sum())) / (draws + 1) if real is not None else None
    return {"realMean": real, "nullMean": float(null.mean()), "nullP95": float(np.quantile(null, 0.95)), "pValueOneSided": p_value, "draws": draws,
            "meaning": "descriptive; no verdict power"}
