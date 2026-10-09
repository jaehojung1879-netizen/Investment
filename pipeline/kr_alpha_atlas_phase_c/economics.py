"""Frozen, capacity-aware long-only diagnostics; never survivor-renormalize a book."""

from __future__ import annotations

import numpy as np

from pipeline.selection_value import decompose_edge, decompose_turnover
from .statistics import percentiles


def stock_cost(spec, date, sell=False):
    costs = spec["costs"]
    tax = 0.0
    if sell:
        tax = next(row["sellTaxBps"] for row in reversed(costs["sellTaxSchedule"]) if date >= row["effectiveFrom"])
    return (costs["commissionBps"] + costs["quotedSpreadBps"] / 2 + tax) / 10000


def anchors(data, book, feature, spec):
    # Predetermined by calendar and registered usable range, never by predictions/outcomes.
    dates = sorted(
        data.rows.date[
            (data.rows.date >= feature["usableRange"][0])
            & (data.rows.date.str[:4].astype(int).isin(spec["chronology"]["evaluationYears"]))
        ].unique()
    )
    selected = []
    next_date = ""
    for date in dates:
        entry = int(data.days.searchsorted(date, side="right"))
        end = entry + book.horizon
        if end >= len(data.days) or str(data.days[end].date()) > spec["developmentCutoff"]:
            continue
        if date >= next_date:
            selected.append(date)
            next_date = str(data.days[end].date())
    return selected


def select(data, ids, score, prediction, entry, exit_day, spec, *, diagnostic=False, liquidity="ALL", capital=None):
    rows = data.rows.loc[ids]
    value = data.values.loc[ids, "E03_capacityMedianTradedValue60"]
    liquidity_mask = (
        value.ge(value.median())
        if liquidity == "HIGH"
        else value.lt(value.median())
        if liquidity == "LOW"
        else np.ones(len(ids), bool)
    )
    if diagnostic:
        selected_ids = ids[(score >= 2 / 3) & liquidity_mask]
        return {int(i): 1 / len(selected_ids) for i in selected_ids} if len(selected_ids) else {}
    # Future tax changes are not known at the signal. Realized exits use their
    # effective dated tax, but eligibility uses the then-current schedule only.
    signal = str(rows.date.iloc[0])
    friction = stock_cost(spec, signal) + stock_cost(spec, signal, True)
    friction += 2 * spec["costs"]["benchmarkEachWayBps"] / 10000
    capital = spec["economics"]["capitalKrw"] if capital is None else capital
    candidates = rows.index[
        (score >= 2 / 3)
        & np.isfinite(prediction[ids])
        & (prediction[ids] > friction)
        & rows.tradableAtSignal.astype(bool)
        & data.values.loc[ids, "E04_tradabilityGuard20"].ge(20)
        & liquidity_mask
        & value.ge(capital * 0.2 / spec["economics"]["orderShareMedianValue"])
    ]
    candidates = sorted(candidates, key=lambda i: (-float(prediction[i]), str(data.rows.loc[i, "ticker"])))
    industries = {}
    weights = {}
    for i in candidates:
        industry = data.rows.loc[i, "industry"]
        if not isinstance(industry, str) or industry == "UNCLASSIFIED" or industries.get(industry, 0) >= 2:
            continue
        industries[industry] = industries.get(industry, 0) + 1
        weights[int(i)] = 0.2
        if len(weights) == 5:
            break
    return weights


def block(data, book, date, weights, fallback, spec, *, capital=None):
    entry = int(data.days.searchsorted(date, side="right"))
    end = entry + book.horizon
    entry_day, exit_day = str(data.days[entry].date()), str(data.days[end].date())
    selected = list(weights)
    missing = [
        i for i in selected if book.table.loc[i, "state"] != "VALID" or book.table.loc[i, "industryState"] != "VALID"
    ]
    if missing:
        return {
            "date": date,
            "status": "BLOCKED",
            "reason": "SELECTED_OR_INDUSTRY_REFERENCE_UNPRICEABLE",
            "selected": [data.rows.loc[i, "ticker"] for i in selected],
            "invalidSelected": len(missing),
        }
    bench = np.asarray(data.benchmark_close[entry : end + 1], float)
    if len(bench) != book.horizon + 1 or not np.isfinite(bench).all() or (bench <= 0).any():
        return {"date": date, "status": "BLOCKED", "reason": "BENCHMARK_WINDOW_INVALID"}
    b = float(bench[-1] / bench[0] - 1)
    capital = spec["economics"]["capitalKrw"] if capital is None else capital
    budget = sum(weights.values())
    if min(weights.values(), default=0) < 0 or budget > 1 + 1e-10 or capital <= 0:
        raise ValueError("LONG_ONLY_BUDGET_FAILURE")
    unused = max(0.0, 1 - budget)  # Equal-weight summation may exceed one by a float ulp.
    buy_fee = stock_cost(spec, entry_day)
    bench_fee = spec["costs"]["benchmarkEachWayBps"] / 10000
    executed = {i: w / (1 + buy_fee) for i, w in weights.items()}
    invested = sum(executed.values())
    passive = unused / (1 + bench_fee) if fallback == "PASSIVE_BENCHMARK" else 0.0
    cash = unused if fallback == "CASH" else 0.0
    entry_bill = invested * buy_fee + passive * bench_fee
    # Entry fees are financed inside each slot budget. Gross wealth retains that
    # fee reserve as zero-yield cash; net wealth spends it at entry, never borrows.
    path = np.full(book.horizon + 1, cash + entry_bill) + passive * bench / bench[0]
    gross = 0.0
    industry = 0.0
    selection = 0.0
    max_participation = 0.0
    sale_notional = 0.0
    for i, w in executed.items():
        t = book.table.loc[i]
        levels = np.asarray(data.closes[t.ticker][entry : end + 1], float)
        path += w * levels / levels[0]
        gross += w * float(t.gross)
        industry += w * (float(t.looIndustry) - b)
        selection += w * (float(t.gross) - float(t.looIndustry))
        sale_notional += w * (1 + float(t.gross))
        # Both buy and sell orders must meet capacity. Exit cap comes from signal-time
        # median only: no future liquidity information governs original selection.
        capacity = float(data.values.loc[i, "E03_capacityMedianTradedValue60"])
        max_participation = max(
            max_participation, capital * w * max(1, 1 + float(t.gross)) / capacity
        )
    if max_participation > spec["economics"]["orderShareMedianValue"]:
        return {
            "date": date,
            "status": "BLOCKED",
            "reason": "EXIT_ORDER_CAPACITY_LIMIT",
            "participation": max_participation,
        }
    fallback_gross = passive * b
    gross += fallback_gross
    stock_bill = invested * buy_fee + sale_notional * stock_cost(spec, exit_day, True)
    passive_bill = passive * bench_fee * (2 + b)
    costs = stock_bill + passive_bill
    benchmark_weight = 1 / (1 + bench_fee)
    benchmark_bill = benchmark_weight * bench_fee * (2 + b)
    benchmark_net = benchmark_weight * b - benchmark_bill
    path_net = path.copy()
    path_net -= entry_bill
    path_net[-1] -= sale_notional * stock_cost(spec, exit_day, True) + passive * bench_fee * (1 + b)
    benchmark_path = benchmark_weight * bench / bench[0]
    benchmark_path[-1] -= benchmark_weight * bench_fee * (1 + b)
    benchmark_path = np.r_[1.0, benchmark_path[1:]]
    benchmark_daily = (benchmark_path[1:] / benchmark_path[:-1] - 1).tolist()
    a = invested * b
    f = fallback_gross
    residual = gross - (a + industry + selection + f)
    if abs(residual) > 1e-10 or min(weights.values(), default=0) < 0 or invested > 1 + 1e-10:
        raise ValueError("ECONOMIC_ATTRIBUTION_OR_LONG_ONLY_FAILURE")
    industry_weights = {}
    terminal_weights = {}
    for i, w in executed.items():
        label = data.rows.loc[i, "industry"]
        industry_weights[label] = industry_weights.get(label, 0.0) + w
        terminal_weights[data.rows.loc[i, "ticker"]] = w * (1 + float(book.table.loc[i, "gross"])) / (1 + gross)
    return {
        "date": date,
        "entry": entry_day,
        "exit": exit_day,
        "status": "DEVELOPMENT_DIAGNOSTIC",
        "weights": {data.rows.loc[i, "ticker"]: w for i, w in weights.items()},
        "executedWeights": {data.rows.loc[i, "ticker"]: w for i, w in executed.items()},
        "entryCapitalKrw": capital,
        "entryCashWeight": cash,
        "entryFeeWeight": entry_bill,
        "executedFallbackWeight": passive,
        "selectedCount": len(weights),
        "industryWeights": industry_weights,
        "terminalWeights": terminal_weights,
        "unusedWeight": unused,
        "grossReturn": gross,
        "netReturn": gross - costs,
        "benchmarkReturn": b,
        "benchmarkNetReturn": benchmark_net,
        "grossExcess": gross - b,
        "netExcess": gross - costs - benchmark_net,
        "turnoverBuy": invested + passive,
        "turnoverSell": sale_notional + passive * (1 + b),
        "costReturn": costs,
        "maximumProxyParticipation": max_participation,
        "dailyGrossWealth": path.tolist(),
        "dailyNetWealth": path_net.tolist(),
        "dailyBenchmarkNetReturns": benchmark_daily,
        "attribution": {
            "A_marketExposure": a,
            "B_industryAllocation": industry,
            "C_stockSelection": selection,
            "D_riskFactorExposure": None,
            "E_cost": -costs,
            "F_fallback": f,
            "G_residual": residual,
        },
    }


def summarize(blocks, spec):
    bad = [b for b in blocks if b["status"] == "BLOCKED"]
    if bad or not blocks:
        return {
            "status": "BLOCKED",
            "reason": "INCOMPLETE_PAIRED_PORTFOLIO" if bad else "NO_MATURED_ANCHORS",
            "blocks": blocks,
            "validBlocks": len(blocks) - len(bad),
            "blockedBlocks": len(bad),
            "netExcess": None,
        }
    daily = []
    benchmark_daily = []
    full_nav = [1.0]
    cumulative = 1.0
    for b in blocks:
        wealth = np.asarray(b["dailyNetWealth"])
        if (wealth <= 0).any():
            return {"status": "BLOCKED", "reason": "NONPOSITIVE_PORTFOLIO_WEALTH", "blocks": blocks, "netExcess": None}
        # Entry cost belongs to the first held return; the baseline is pre-trade NAV.
        path = np.r_[1.0, wealth[1:]]
        daily.extend((path[1:] / path[:-1] - 1).tolist())
        full_nav.extend((cumulative * wealth).tolist())
        cumulative *= 1 + b["netReturn"]
        benchmark_daily.extend(b["dailyBenchmarkNetReturns"])
    # Include entry costs in block compounding; daily risk statistics separately state
    # intra-block path convention and do not silently drop costs from total return.
    net = np.array([b["netReturn"] for b in blocks])
    bench = np.array([b["benchmarkNetReturn"] for b in blocks])
    nav = np.r_[1, np.cumprod(1 + net)]
    gross_nav = np.prod([1 + b["grossReturn"] for b in blocks])
    years = sum(len(b["dailyGrossWealth"]) - 1 for b in blocks) / 252
    downside = np.minimum(np.asarray(daily), 0)
    full_nav = np.asarray(full_nav)
    drawdown = float(np.min(full_nav / np.maximum.accumulate(full_nav) - 1))
    means = {
        key: float(np.mean([b["attribution"][key] for b in blocks]))
        for key in blocks[0]["attribution"]
        if key != "D_riskFactorExposure"
    }
    compounding = decompose_edge(blocks, years=years)
    if "arithmeticSelectionEdgePp" in compounding:
        compounding["arithmeticBookBenchmarkEdgePp"] = compounding.pop("arithmeticSelectionEdgePp")
    compounding["arithmeticTermMeaning"] = (
        "TOTAL_BOOK_BENCHMARK_EDGE_INCLUDES_INDUSTRY_AND_FALLBACK_NOT_C_STOCK_SELECTION"
    )
    compounding["method"] = "pipeline.selection_value.decompose_edge"
    return {
        "status": "DEVELOPMENT_DIAGNOSTIC",
        "claimStatus": spec["benchmarkIntegrity"]["claimGate"],
        "blocks": blocks,
        "validBlocks": len(blocks),
        "blockedBlocks": 0,
        "grossGrowth": float(gross_nav),
        "netGrowth": float(nav[-1]),
        "benchmarkNetGrowth": float(np.prod(1 + bench)),
        "netExcess": float(np.mean(net - bench)),
        "marketExposure": {
            "averageInvestedWeight": float(np.mean([sum(b["executedWeights"].values()) for b in blocks])),
            "grossBlockBeta": float(
                np.cov([b["grossReturn"] for b in blocks], [b["benchmarkReturn"] for b in blocks], ddof=0)[0, 1]
                / np.var([b["benchmarkReturn"] for b in blocks])
            )
            if len(blocks) > 1 and np.var([b["benchmarkReturn"] for b in blocks]) > 1e-12
            else None,
            "status": "DESCRIPTIVE",
        },
        "arithmeticAttribution": means,
        "drawdown": drawdown,
        "descriptiveBootstrap": bootstrap(np.asarray(daily), np.asarray(benchmark_daily), spec),
        "downsideDailyVolatility": float(np.sqrt(np.mean(downside**2)) * np.sqrt(252)),
        "concentrationMaximum": max(max(b["weights"].values(), default=0) for b in blocks),
        "industryConcentrationMaximum": max(max(b["industryWeights"].values(), default=0) for b in blocks),
        "zeroSelectedSessionShare": sum((len(b["dailyGrossWealth"]) - 1) for b in blocks if b["selectedCount"] == 0)
        / sum(len(b["dailyGrossWealth"]) - 1 for b in blocks),
        "holdingChangeTurnover": decompose_turnover(blocks),
        "turnoverDefinition": "all stock orders are full liquidation round trips; name/retarget components separately describe holding changes, never replace the actual order cost bill",
        "turnoverMean": float(np.mean([b["turnoverBuy"] + b["turnoverSell"] for b in blocks])),
        "implementationCostsMean": float(np.mean([b["costReturn"] for b in blocks])),
        "compounding": compounding,
    }


def risk_exposure(blocks, data, book, spec):
    # D explains book excess and is not a second additive return credit.
    if not blocks or any(b["status"] == "BLOCKED" for b in blocks):
        return {"status": "BLOCKED", "additive": False}
    columns = spec["economics"]["riskFactorColumns"]
    ranks = percentiles(data, columns)
    x = []
    y = []
    selection = []
    for b in blocks:
        ids = data.rows.index[data.rows.date.eq(b["date"]) & book.table.state.eq("VALID")].to_numpy(int)
        row = []
        from pipeline.alpha_opportunity_v5_evidence import rank_weighted_spread_design

        for fid in columns:
            score = ranks.loc[ids, fid].to_numpy(float)
            good = np.isfinite(score)
            if good.sum() < 30:
                break
            w = rank_weighted_spread_design(score[good], data.rows.loc[ids[good], "ticker"].to_numpy()).weights
            row.append(float(w @ book.table.loc[ids[good], "benchmarkRelative"].to_numpy(float)))
        if len(row) == len(columns):
            x.append(row)
            y.append(b["grossExcess"])
            selection.append(b["attribution"]["C_stockSelection"])
    if len(x) < max(12, len(columns) + 2):
        return {"status": "BLOCKED_INSUFFICIENT_BLOCKS", "additive": False, "columns": columns}
    design = np.column_stack([np.ones(len(x)), x])
    coef = np.linalg.lstsq(design, y, rcond=None)[0]
    selection_coef = np.linalg.lstsq(design, selection, rcond=None)[0]
    return {
        "status": "DESCRIPTIVE",
        "additive": False,
        "blocks": len(x),
        "columns": columns,
        "excessLoadings": coef[1:].tolist(),
        "stockSelectionLoadings": selection_coef[1:].tolist(),
        "intercept": float(coef[0]),
        "selectionResidualIntercept": float(selection_coef[0]),
        "claim": "D is a nested explanatory regression, not additive alpha; neither intercept is a confirmed selection edge",
    }


def evaluate(data, book, feature, predictions, spec, *, interaction=None):
    ranks = percentiles(data, [feature["featureId"]])[feature["featureId"]]
    oriented = ranks if feature["expectedDirection"] == 1 else 1 - ranks
    forecast = predictions["ADD_" + feature["family"]] if interaction is None else predictions["FULL"]
    if interaction is not None:
        all_ranks = percentiles(data)
        name = interaction["interactionId"]
        a, b = interaction["features"]
        if name.startswith("X1"):
            oriented = all_ranks[a]
            keep = (all_ranks[a] >= 2 / 3) & data.rows.b08Confirmed.eq(1)
        elif name.startswith("X2"):
            oriented = all_ranks[a]
            keep = (all_ranks[a] >= 2 / 3) & (all_ranks[b] <= 1 / 3)
        elif name.startswith("X5"):
            oriented = 1 - all_ranks[a]
            keep = (all_ranks[a] <= 1 / 3) & (all_ranks[b] <= 1 / 3)
        else:
            raise ValueError("UNREGISTERED_CONDITIONAL_ECONOMIC_POLICY")
        oriented = oriented.where(keep, np.nan)
        feature = {**feature, "usableRange": interaction["readiness"]["evaluableRange"]}
    policies = {}
    for diagnostic, liquidity in ((d, l) for d in (True, False) for l in ("ALL", "HIGH", "LOW")):
        name = ("DIAGNOSTIC" if diagnostic else "SLOTS") + (
            "_" + liquidity + "_LIQUIDITY" if liquidity != "ALL" else ""
        )
        for fallback in spec["economics"]["fallbacks"]:
            blocks = []
            nav = 1.0
            for date in anchors(data, book, feature, spec):
                if nav is None:
                    blocks.append({"date": date, "status": "BLOCKED", "reason": "UNPRICED_PRIOR_NAV"})
                    continue
                capital = spec["economics"]["capitalKrw"] * nav
                ids = data.rows.index[data.rows.date.eq(date)].to_numpy(int)
                entry = int(data.days.searchsorted(date, side="right"))
                end = entry + book.horizon
                weights = select(
                    data,
                    ids,
                    oriented.loc[ids].to_numpy(float),
                    forecast,
                    str(data.days[entry].date()),
                    str(data.days[end].date()),
                    spec,
                    diagnostic=diagnostic,
                    liquidity=liquidity,
                    capital=capital,
                )
                b = block(data, book, date, weights, fallback, spec, capital=capital)
                blocks.append(b)
                nav = nav * (1 + b["netReturn"]) if b["status"] != "BLOCKED" else None
                if nav is not None and nav <= 0:
                    nav = None
            policies[name + "_" + fallback] = summarize(blocks, spec)
    for policy in policies.values():
        policy["riskFactorExposure"] = risk_exposure(policy["blocks"], data, book, spec)
    return {
        "featureId": feature["featureId"],
        "interactionId": interaction["interactionId"] if interaction is not None else None,
        "horizon": book.horizon,
        "policies": policies,
        "benchmarkClaimStatus": spec["benchmarkIntegrity"]["claimGate"],
        "pairedPolicyComparisonStatus": "BLOCKED" if any(p["status"] == "BLOCKED" for p in policies.values()) else "MATCHED_ANCHORS",
        "tradingValueBasis": spec["tradingValueBasis"],
    }


def bootstrap(portfolio, benchmark, spec):
    """Bounded circular paired calendar-session blocks, descriptive only."""
    policy = spec["inference"]["portfolioBootstrap"]
    n = len(portfolio)
    if not n or len(benchmark) != n:
        return {"status": "BLOCKED", "draws": 0}
    rng = np.random.default_rng(policy["seed"])
    width = policy["blockSessions"]
    offsets = np.arange(width)
    results = []
    for _ in range(policy["draws"]):
        starts = rng.integers(0, n, size=int(np.ceil(n / width)))
        ids = ((starts[:, None] + offsets) % n).ravel()[:n]
        results.append(float(np.mean(portfolio[ids] - benchmark[ids])))
    return {
        "status": "DESCRIPTIVE_NOT_A_NOMINATION_GATE",
        "draws": policy["draws"],
        "blockSessions": width,
        "pairedMeanDailyExcessQuantiles": np.quantile(results, [0.025, 0.5, 0.975]).tolist(),
    }
