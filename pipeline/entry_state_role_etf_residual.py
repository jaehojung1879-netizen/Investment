"""Entry state in the RANK versus entry state on the WEIGHT, with the regional ETF as the residual.

WHY A NEW STUDY AND NOT A RERUN
-------------------------------
`entry-selection-separation-v1` (sealed result, +1.385pp net excess for the weight rung, paired +2.069pp, 95% CI [-1.881,
+6.061]) left the throttled capital in KRW CASH and compared both rungs to a benchmark matched to their own invested weight.
Its weight rung averaged 56.0% cash against the control's 30.4%, so its number mixes two effects: where entry state acts,
and how much of the book sits in cash instead of the market. It also carried a second, unstated difference: the control
called `kelly_portfolio.selection_and_baseline` with the macro regime (whose cash floor can exceed `minCashPct`), while the
weight rung called `select_portfolio_by_scores` / `baseline_weights` with the plain `minCashPct`. Neither is repaired in the
sealed study; this study is a NEW comparison with its own id that removes both:

* the residual of every book is the region's own ETF (KR 069500.KS, US SPY), never cash, on BOTH rungs;
* both rungs get the identical budget: the same macro-regime cash floor from `kelly_portfolio._regime_adjustment`, computed
  once per block and handed to both rungs; what that floor withholds goes to the ETF too;
* KR and US are separate books in their own currency (KRW, USD) against their own ETF; nothing is pooled;
* every path starts from 100% of its regional ETF (the default) and pays the dated cost of each leg it trades, once:
  stock legs at the stock schedule, ETF legs at the ETF schedule (`weekly_decision.trade_cost_fraction`, no ETF sell tax);
* NAV is carried forward through drifted holdings; principal is never reset at a rebalance.

THE AXIS, AND ONLY THE AXIS
---------------------------
    ENTRY_IN_RANK      `alpha_reliability.reliability_scores`, unmodified: the entry-state multiplier is inside the score
                       that ranks and tilts (today's production shape). Weights are `baseline_weights` of that ranking.
    ENTRY_AT_WEIGHT    `entry_selection_separation.entry_weighted_scores`, unmodified: the continuous multiplier divided
                       back out before selection and tilt, then applied once to each held name's own weight.

Selection is `kelly_portfolio.select_portfolio_by_scores` and sizing `kelly_portfolio.baseline_weights` for both rungs. A
multiplier of 0 stays a full eligibility exclusion on both rungs. No third allocator exists here.

NAME COUNT IS A SCENARIO, NOT A RESULT OF THIS STUDY
-----------------------------------------------------
`targetNames` is the scenario N, `maxNamesPerRegion` equals N inside a single-region book (a region cap has no meaning there),
`minNames` is 0 and never fills a slot. The legacy `minNames=3` / `maxNamesPerRegion=3` are NOT inherited. The grid
N in SCENARIO_NAME_COUNTS was fixed before any path was valued and every N is published; `PRIMARY_NAME_COUNT` (5, the legacy
`targetNames`) is the single contrast the verdict reads, chosen for continuity with the sealed study, and is labelled
`LEGACY_TARGET_SCENARIO_NOT_AN_OPTIMUM`. N=10 is in the grid so that a count above five is measured, not assumed away. No N,
window, sector or threshold may be chosen from these results.

EVIDENCE CLASS
--------------
`HISTORICAL_DEVELOPMENT_OUTCOME_EXPOSED`. replay-v16 history 2013-2026 has been read by more than ten studies, including this
exact axis; nothing here is out of sample, nothing here promotes a selector, and production does not import this module.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import alpha_reliability as AR
from . import benchmark_alpha as BA
from . import entry_selection_separation as ES
from . import kelly_portfolio as KP
from . import weekly_decision as W

STUDY_ID = "entry-state-role-etf-residual-v1"
SPEC_PATH = "research/entry_state_role_etf_residual_v1/spec.json"
EVIDENCE_CLASS = "HISTORICAL_DEVELOPMENT_OUTCOME_EXPOSED"
REGIONAL_ETF = {"KR": "069500.KS", "US": "SPY"}
SEPARATE_COMPARISON = {"US": "QQQ"}
CURRENCY = {"KR": "KRW", "US": "USD"}
ENTRY_IN_RANK = "ENTRY_IN_RANK"
ENTRY_AT_WEIGHT = "ENTRY_AT_WEIGHT"
RUNGS = (ENTRY_IN_RANK, ENTRY_AT_WEIGHT)
RESIDUALS = ("ETF", "CASH")              # CASH is a secondary, separately reported decomposition, never the primary
PRIMARY_RESIDUAL = "ETF"
SCENARIO_NAME_COUNTS = (0, 1, 2, 3, 4, 5, 10)
PRIMARY_NAME_COUNT = 5
PRIMARY_NAME_COUNT_LABEL = "LEGACY_TARGET_SCENARIO_NOT_AN_OPTIMUM"
HORIZONS = {"H126": 126, "H252": 252}
PRIMARY_HORIZON = "H126"
BLOCK_SESSIONS = 21
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_BLOCK = 6                      # 6 x 21 sessions = the primary 126-session horizon
BOOTSTRAP_SEED = 20261101
RETURN_BASIS = "REPLAY_V16_CLOSE_WITH_FORWARD_ACCUMULATED_DISTRIBUTIONS_PARTIAL"
NET_ALREADY_CHARGED = "NET_ALREADY_CHARGED"
NO_COST = "NO_TRADE_NO_COST"
ZERO = 1e-12


class AdditionalCostRefused(ValueError):
    """A NAV series that already carries its trading costs may not be charged again."""


def refuse_additional_cost(series_meta: dict) -> None:
    """Every consumer that would deduct a cost from a published NAV calls this first."""
    if series_meta.get("costBasis") == NET_ALREADY_CHARGED:
        raise AdditionalCostRefused(
            f"{series_meta.get('strategyId')}: costBasis NET_ALREADY_CHARGED, no further cost may be deducted")


# ------------------------------------------------------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------------------------------------------------------
def regional_config(cfg_pf: dict, region: str, n: int) -> dict:
    """The research cost config with the scenario count; the legacy minNames / per-region cap are NOT inherited."""
    out = BA.cost_config(cfg_pf)
    selection = dict(out.get("selection") or {})
    selection["targetNames"] = int(n)
    selection["maxNamesPerRegion"] = int(n)
    selection["minNames"] = 0
    out["selection"] = selection
    out["regionCaps"] = {region: 1.0}
    return out


def spec() -> dict:
    """The frozen comparison definition. Its digest is published with every result."""
    return {
        "studyId": STUDY_ID,
        "evidenceClass": EVIDENCE_CLASS,
        "question": "Economic difference between entry state inside the selection rank and entry state applied to the "
                    "weight after selection, with identical sample, region, execution session, residual asset and costs.",
        "rungs": {ENTRY_IN_RANK: "alpha_reliability.reliability_scores (multiplier inside the score)",
                  ENTRY_AT_WEIGHT: "entry_selection_separation.entry_weighted_scores, multiplier applied to held weight"},
        "selectionFunction": "kelly_portfolio.select_portfolio_by_scores",
        "sizingFunction": "kelly_portfolio.baseline_weights",
        "budget": "max(minCashPct, macro regime cash floor) from kelly_portfolio._regime_adjustment, identical per block "
                  "for both rungs; the withheld budget goes to the residual asset",
        "regions": {r: {"etf": REGIONAL_ETF[r], "currency": CURRENCY[r]} for r in REGIONAL_ETF},
        "separateComparison": SEPARATE_COMPARISON,
        "residuals": {"primary": PRIMARY_RESIDUAL, "secondary": "CASH (KRW policy-rate accrual), reported apart"},
        "scenarioNameCounts": list(SCENARIO_NAME_COUNTS),
        "primaryNameCount": PRIMARY_NAME_COUNT, "primaryNameCountLabel": PRIMARY_NAME_COUNT_LABEL,
        "legacyConstraintsNotInherited": {"minNames": 3, "maxNamesPerRegion": 3},
        "heldFixed": ["maxNamesPerSector=2", "maxPositionWeight=0.30", "minCashPct=15 plus macro regime floor",
                      "convictionTiltRange=1.0", "21-session blocks on the common KRX/NYSE schedule",
                      "expanding bucket calibration (horizon 126, prior strength 30, min 20 dates, gross)",
                      "realistic dated cost schedule (benchmark_alpha.REALISTIC_COSTS, ETF legs without sell tax)"],
        "initialState": "100% regional ETF; the ETF-only path never trades",
        "execution": "block anchor session close, signal = last weekly signal strictly before the anchor",
        "horizons": HORIZONS, "primaryHorizon": PRIMARY_HORIZON,
        "pairedInference": {"statistic": "per-block log NAV growth difference, annualized",
                            "bootstrap": "circular block", "blockLengthBlocks": BOOTSTRAP_BLOCK,
                            "draws": BOOTSTRAP_DRAWS, "seed": BOOTSTRAP_SEED, "level": 0.95},
        "missingData": "a block that cannot be valued stops that path (INPUT_UNAVAILABLE) at that block; no name is "
                       "dropped and no return is filled with zero; unmatured horizons are PENDING, not zero",
        "forbidden": ["choosing N, window, sector or threshold from these results",
                      "calling any of this out-of-sample", "promotion", "production change",
                      "transferring the sealed +1.385pp cash-residual number to an ETF-residual strategy"],
        "promotionEligible": False, "liveValidated": False, "productionChanged": False,
    }


def spec_sha256() -> str:
    return hashlib.sha256(json.dumps(spec(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def code_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for rel in ("pipeline/entry_state_role_etf_residual.py", "scripts/run_entry_state_role_etf_residual.py"):
        digest.update(rel.encode())
        digest.update((root / rel).read_bytes())
    return digest.hexdigest()


# ------------------------------------------------------------------------------------------------------------------------------
# One decision
# ------------------------------------------------------------------------------------------------------------------------------
def decide(rung: str, candidates: list[dict], scored: list[dict], macro: dict | None, cfg: dict) -> dict:
    """Stock target weights for one rung. Same budget, same selector, same sizer for both rungs."""
    if rung not in RUNGS:
        raise ValueError(f"unknown rung {rung}")
    _, _, regime_cash, _ = KP._regime_adjustment(macro, cfg)
    local_cfg = dict(cfg)
    local_cfg["minCashPct"] = max(float(cfg.get("minCashPct", 10)), float(regime_cash))
    target = int((cfg.get("selection") or {}).get("targetNames", 0))
    states = {row["ticker"]: row.get("entryStateMultiplier") for row in scored}
    if target <= 0:
        return {"weights": {}, "selected": [], "ranking": scored, "states": states,
                "appliedMinCashPct": local_cfg["minCashPct"], "throttledWeight": 0.0}
    ranking = scored if rung == ENTRY_IN_RANK else ES.entry_weighted_scores(scored)
    selected, _ = KP.select_portfolio_by_scores(candidates, ranking, local_cfg, method=rung)
    raw = KP.baseline_weights(selected, local_cfg, ranking_rows=ranking)
    throttled = 0.0
    if rung == ENTRY_AT_WEIGHT:
        shrunk = {}
        for ticker, weight in raw.items():
            multiplier = float(states.get(ticker) or 0.0)
            shrunk[ticker] = weight * multiplier
            throttled += weight - shrunk[ticker]
        raw = shrunk
    weights, _ = KP._serialize_allocation(pd.Series(raw, dtype=float))
    weights = {t: float(w) for t, w in weights.items() if w > ZERO}
    return {"weights": weights, "selected": selected, "ranking": ranking, "states": states,
            "appliedMinCashPct": local_cfg["minCashPct"], "throttledWeight": throttled}


# ------------------------------------------------------------------------------------------------------------------------------
# Accounting: legs, cost once, NAV carried forward
# ------------------------------------------------------------------------------------------------------------------------------
def trade_legs(prior: dict, target: dict, region: str, as_of: str, etf_tickers: set[str]) -> tuple[list[dict], float]:
    """Every traded leg and its dated cost, as fractions of NAV before the trade. Cost is charged exactly once here."""
    legs, cost = [], 0.0
    for ticker in sorted(set(prior) | set(target)):
        delta = float(target.get(ticker, 0.0)) - float(prior.get(ticker, 0.0))
        if abs(delta) <= 1e-10:
            continue
        side = "buy" if delta > 0 else "sell"
        rate = W.trade_cost_fraction(region, as_of, is_benchmark=ticker in etf_tickers, side=side)
        leg_cost = abs(delta) * rate
        cost += leg_cost
        legs.append({"ticker": ticker, "side": side, "weight": round(abs(delta), 10),
                     "instrument": "ETF" if ticker in etf_tickers else "STOCK",
                     "costRateBps": round(rate * 1e4, 4), "costFraction": leg_cost})
    return legs, cost


def _residual_target(stock_weights: dict, residual: str, etf: str) -> dict:
    target = dict(stock_weights)
    left = 1.0 - sum(stock_weights.values())
    if left < -1e-8:
        raise ValueError("stock weights exceed NAV")
    if residual == "ETF" and left > ZERO:
        target[etf] = target.get(etf, 0.0) + left
    return target


def run_path(*, rung: str, region: str, n: int, residual: str, contexts: dict, calibrator, calendar: list[dict],
             cfg_pf: dict, valuation, fixed_target: dict | None = None, strategy_id: str | None = None) -> dict:
    """Value one regional path on the fixed blocks. `fixed_target` values a passive path (ETF or QQQ) instead."""
    etf = REGIONAL_ETF[region]
    etf_tickers = {etf, SEPARATE_COMPARISON.get(region, etf)}
    cfg = regional_config(cfg_pf, region, n)
    state = AR.ReliabilityState(AR.WINDOW_BLOCKS)
    held = {etf: 1.0}                    # every path starts fully in its regional ETF
    nav = 1.0
    daily: list[tuple[str, float]] = []
    blocks, status, stop = [], "COMPLETE", None
    for block in calendar:
        if fixed_target is not None:
            stock_weights, info = {}, None
            target = dict(fixed_target)
        else:
            signal_date = block["signalDate"]
            calibrator.advance(signal_date)
            raw_candidates, macro = contexts.get(signal_date) or ([], {})
            regional = [c for c in raw_candidates if c.get("region") == region]
            candidates = AR.confidence_rows(regional, state, block["date"], persistence=False, confidence=False)
            incumbents = {t for t in held if t not in etf_tickers}
            scored = AR.reliability_scores(candidates, calibrator, cfg, as_of=block["date"], incumbents=incumbents,
                                           hysteresis=False, cost_hurdle=False)
            info = decide(rung, candidates, scored, macro, cfg)
            stock_weights = info["weights"]
            target = _residual_target(stock_weights, residual, etf)
        legs, cost = trade_legs(held, target, region, block["date"], etf_tickers)
        region_by_ticker = {t: region for t in target}
        decision = {"date": block["date"], "replayDate": block["signalDate"], "selector": rung,
                    "weights": target, "regionByTicker": region_by_ticker,
                    "cashPct": (1 - sum(target.values())) * 100, "rebalanceDecision": True,
                    "selectedTickers": list(stock_weights)}
        row, diagnostic = valuation.window(decision, block)
        if row is None:
            status = "INPUT_UNAVAILABLE"
            stop = {"date": block["date"], "endDate": block["endDate"], **diagnostic}
            break
        start_nav = nav * (1.0 - cost)
        growth = np.asarray(row["dailyGrossNav"], dtype=float)
        dates = row["dailyDates"]
        for i, (date, value) in enumerate(zip(dates, growth)):
            if i == 0 and daily and daily[-1][0] == date:
                daily[-1] = (date, start_nav * value)   # the rebalance session: post-trade NAV replaces the pre-trade mark
            else:
                daily.append((date, start_nav * value))
        nav = start_nav * float(growth[-1])
        stocks_now = set(stock_weights)
        stocks_before = {t for t in held if t not in etf_tickers}
        blocks.append({
            "date": block["date"], "endDate": block["endDate"], "signalDate": block["signalDate"],
            "nextTradableSession": block["endDate"],
            "targetWeights": {t: round(w, 8) for t, w in target.items()},
            "stockNames": len(stocks_now), "residualWeight": round(1 - sum(stock_weights.values()), 8),
            "added": sorted(stocks_now - stocks_before), "retained": sorted(stocks_now & stocks_before),
            "replaced": sorted(stocks_before - stocks_now),
            "legs": legs, "costFraction": cost, "oneWayTurnover": sum(l["weight"] for l in legs) / 2,
            "navStart": start_nav, "navEnd": nav,
            "throttledWeight": None if info is None else round(info["throttledWeight"], 8),
            "appliedMinCashPct": None if info is None else info["appliedMinCashPct"],
        })
        held = {t: float(w) for t, w in (row.get("terminalWeights") or {}).items() if w > ZERO}
    return {"strategyId": strategy_id or f"{region}:{rung}:N{n}:{residual}", "region": region, "rung": rung, "n": n,
            "residual": residual, "status": status, "stoppedAt": stop, "blocks": blocks, "daily": daily}


# ------------------------------------------------------------------------------------------------------------------------------
# Metrics
# ------------------------------------------------------------------------------------------------------------------------------
def _years(first: str, last: str) -> float:
    return (pd.Timestamp(last) - pd.Timestamp(first)).days / 365.25


def _nav_on(daily: list[tuple[str, float]]) -> pd.Series:
    return pd.Series({pd.Timestamp(d): v for d, v in daily}, dtype=float).sort_index()


def path_metrics(path: dict, etf_path: dict) -> dict:
    if path["status"] != "COMPLETE" or not path["daily"]:
        return {"available": False, "status": path["status"], "stoppedAt": path["stoppedAt"]}
    nav, bench = _nav_on(path["daily"]), _nav_on(etf_path["daily"])
    if not nav.index.equals(bench.index):
        raise ValueError(f"{path['strategyId']}: NAV dates differ from the ETF path")
    years = _years(path["daily"][0][0], path["daily"][-1][0])
    first = 1.0
    cagr = (nav.iloc[-1] / first) ** (1 / years) - 1
    bench_cagr = (bench.iloc[-1] / first) ** (1 / years) - 1
    r, b = nav.pct_change().dropna(), bench.pct_change().dropna()
    active = np.log1p(r) - np.log1p(b)
    vol = float(r.std(ddof=1) * math.sqrt(252))
    te = float(active.std(ddof=1) * math.sqrt(252))
    dd = float((nav / nav.cummax() - 1).min())
    bdd = float((bench / bench.cummax() - 1).min())
    blocks = path["blocks"]
    turnover = sum(bl["oneWayTurnover"] for bl in blocks[1:])
    tail = r.sort_values().iloc[:max(1, int(math.ceil(len(r) * 0.05)))]
    added = sum(len(bl["added"]) for bl in blocks[1:])
    retained = sum(len(bl["retained"]) for bl in blocks[1:])
    return {
        "available": True, "first": path["daily"][0][0], "last": path["daily"][-1][0], "years": round(years, 4),
        "blocks": len(blocks), "cagrPct": round(cagr * 100, 4), "etfCagrPct": round(bench_cagr * 100, 4),
        "annualizedExcessVsEtfPp": round((cagr - bench_cagr) * 100, 4),
        "annualizedVolPct": round(vol * 100, 4), "etfAnnualizedVolPct": round(float(b.std(ddof=1) * math.sqrt(252)) * 100, 4),
        "trackingErrorPct": round(te * 100, 4),
        "informationRatio": round(float(active.mean() * 252) / te, 4) if te > 0 else None,
        "mddPct": round(dd * 100, 4), "etfMddPct": round(bdd * 100, 4),
        "dailyCvar95Pct": round(float(tail.mean()) * 100, 4),
        "annualOneWayTurnoverX": round(turnover / years, 4) if years else None,
        "costDragPctOfNavTotal": round(sum(bl["costFraction"] for bl in blocks) * 100, 4),
        "averageStockNames": round(float(np.mean([bl["stockNames"] for bl in blocks])), 4),
        "averageResidualPct": round(float(np.mean([bl["residualWeight"] for bl in blocks])) * 100, 4),
        "namesAddedPerRebalance": round(added / max(1, len(blocks) - 1), 4),
        "namesRetainedPerRebalance": round(retained / max(1, len(blocks) - 1), 4),
        "incumbentRetentionPct": (round(100 * retained / (retained + sum(len(bl["replaced"]) for bl in blocks[1:])), 2)
                                  if retained + sum(len(bl["replaced"]) for bl in blocks[1:]) else None),
    }


def _anchor_navs(path: dict) -> list[float]:
    """NAV at each block anchor after its trade, plus the final mark; index k = anchor k."""
    return [bl["navStart"] for bl in path["blocks"]] + ([path["blocks"][-1]["navEnd"]] if path["blocks"] else [])


def horizon_windows(path: dict, etf_path: dict, sessions: int, total_blocks: int) -> dict:
    """Forward excess over the ETF from every anchor; overlapping windows for the mean, every k-th for the sample."""
    step = sessions // BLOCK_SESSIONS
    if path["status"] != "COMPLETE":
        return {"available": False, "status": path["status"]}
    a, e = _anchor_navs(path), _anchor_navs(etf_path)
    values = []
    for k in range(len(a) - step):
        values.append((a[k + step] / a[k]) - (e[k + step] / e[k]))
    pending = max(0, total_blocks - len(values))
    if not values:
        return {"available": False, "status": "PENDING_NOT_MATURED", "pendingAnchors": pending}
    arr = np.asarray(values)
    sample = arr[::step]
    return {"available": True, "windowSessions": sessions, "maturedAnchors": len(values),
            "pendingAnchorsNotMatured": pending,
            "meanExcessPct": round(float(arr.mean()) * 100, 4), "medianExcessPct": round(float(np.median(arr)) * 100, 4),
            "hitRatePct": round(float((arr > 0).mean()) * 100, 2),
            "nonOverlappingWindows": int(len(sample)),
            "nonOverlappingMeanExcessPct": round(float(sample.mean()) * 100, 4),
            "nonOverlappingWorstExcessPct": round(float(sample.min()) * 100, 4)}


def paired_difference(challenger: dict, control: dict) -> dict:
    """Annualized mean per-block log growth difference, challenger minus control, circular block bootstrap CI."""
    if challenger["status"] != "COMPLETE" or control["status"] != "COMPLETE":
        return {"available": False, "reason": "PATH_NOT_COMPLETE"}
    ca, cb = challenger["blocks"], control["blocks"]
    if [b["date"] for b in ca] != [b["date"] for b in cb]:
        raise ValueError("paired paths do not share their anchors")
    d = np.asarray([math.log(x["navEnd"] / x["navStart"]) + math.log(1 - x["costFraction"])
                    - math.log(y["navEnd"] / y["navStart"]) - math.log(1 - y["costFraction"])
                    for x, y in zip(ca, cb)])
    years = _years(ca[0]["date"], ca[-1]["endDate"])
    per_year = len(d) / years
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n = len(d)
    draws = []
    for _ in range(BOOTSTRAP_DRAWS):
        starts = rng.integers(0, n, size=int(math.ceil(n / BOOTSTRAP_BLOCK)))
        idx = np.concatenate([(s + np.arange(BOOTSTRAP_BLOCK)) % n for s in starts])[:n]
        draws.append(d[idx].mean() * per_year)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    point = d.mean() * per_year
    return {"available": True, "pairedBlocks": n, "statistic": "annualized mean log NAV growth difference (incl. cost)",
            "pointEstimatePp": round(point * 100, 4), "ci95Pp": [round(lo * 100, 4), round(hi * 100, 4)],
            "contains_zero": bool(lo <= 0 <= hi),
            "direction": "CONTAINS_ZERO" if lo <= 0 <= hi else ("BETTER" if lo > 0 else "WORSE")}


def nav_rows(path: dict, *, currency: str, cost_basis: str, source: dict) -> list[dict]:
    meta = {"region": path["region"], "strategyId": path["strategyId"], "currency": currency, "frequency": "DAILY",
            "returnBasis": RETURN_BASIS, "costBasis": cost_basis, "evidenceClass": EVIDENCE_CLASS, **source}
    return [{**meta, "date": d, "nav": round(v, 10)} for d, v in path["daily"]]

