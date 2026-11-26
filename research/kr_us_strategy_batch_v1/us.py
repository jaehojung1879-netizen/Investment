"""Frozen-design US batch evaluation; original selectors, costs and NAV engine.

python -m research.kr_us_strategy_batch_v1.us --private /workspace/batch-inputs/us
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import pickle

import numpy as np
import pandas as pd

from pipeline import us_decision_pilot as UP
from research.alpha_search_round6_v1 import us as R6
from research.kr_us_strategy_batch_v1 import common as CM
from research.us_selection_value_v1 import cocktail as CK
from research.us_selection_value_v1 import evaluate as EV

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
REG = json.loads((HERE / "registry.json").read_text())
SELECTORS = REG["usSelectors"]
MEGA = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "AVGO", "TSLA")
ALIASES = {"VALUE": "WITHIN_SECTOR_VALUE", "SECTOR_MOMENTUM": "SECTOR_MOMENTUM_BASKET"}
ETF = "US:SPY"
POLICIES = ("US:WF_PC_LCB", "US:WF_ALL_LCB")


def clean_json(value):
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return str(pd.Timestamp(value).date())
    return value


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean_json(value), indent=1, sort_keys=True, allow_nan=False) + "\n")


def csv(out, name, frame):
    frame.to_csv(out / (name + ".csv.gz"), compression={"method": "gzip", "mtime": 0})


def normalize_stock(native, q):
    stocks = {t: float(w) for t, w in native.items() if t not in ("SPY", "CASH") and w > 0}
    total = sum(stocks.values())
    if total <= 0:
        return {"SPY": 1.0}
    result = {t: q * w / total for t, w in stocks.items()}
    if q < 1:
        result["SPY"] = 1 - q
    return result


def neutral_names(x, day, confirmed=False):
    order = CM.neutral_order(list(x.index), day, "US")
    selected, sectors = [], Counter()
    for ticker in order:
        if confirmed and not bool(x.at[ticker, "confirmed"]):
            continue
        sector = x.at[ticker, "sector"]
        if sectors[sector] >= 2:
            continue
        selected.append(ticker)
        sectors[sector] += 1
        if len(selected) == 5:
            break
    return selected


def native_book(x, selector, day):
    if selector in ("QUALITY_NEUTRAL", "CONFIRM_NEUTRAL"):
        names = neutral_names(x, day, selector == "CONFIRM_NEUTRAL")
        return {t: 1 / len(names) for t in names} if names else {"SPY": 1.0}
    if selector == "COCKTAIL":
        return CK.book(x, "COCKTAIL")[0]
    if selector == "U1":
        return R6.top5_neutral(x, CK.book(x, "COCKTAIL")[0])[0]
    if selector in ("OW", "OW_RESID"):
        raise ValueError("OPTIONAL_C2_INPUT_UNAVAILABLE")
    names = EV.book(x, ALIASES.get(selector, selector), "TOP5")
    return {t: 1 / len(names) for t in names} if names else {"SPY": 1.0}


def fixed_path(window, weights, *, buy=EV.BUY, sell=EV.SELL):
    """Exact endpoint costs; internal missing marks carry within the window only."""
    names = list(weights)
    raw = window[names]
    endpoints = raw.iloc[[0, -1]]
    if not np.isfinite(endpoints.to_numpy()).all() or (endpoints <= 0).any().any():
        return None
    relative = raw.ffill().divide(raw.iloc[0])
    if not np.isfinite(relative.to_numpy()).all() or (relative <= 0).any().any():
        return None
    growth = relative.to_numpy() @ np.array([weights[t] for t in names])
    wealth = np.r_[1.0, (1 - buy) * growth]
    wealth[-1] *= 1 - sell
    net = float(wealth[-1] - 1)
    expected = float((1 - buy) * growth[-1] * (1 - sell) - 1)
    if abs(net - expected) > 1e-12:
        raise AssertionError("FIXED_DAILY_ENDPOINT_COST_MISMATCH")
    return {"net": net, "mdd": float(np.min(wealth / np.maximum.accumulate(wealth) - 1)),
            "gross": float(growth[-1] - 1), "internalMissingMarks": int(raw.iloc[1:-1].isna().sum().sum())}


def make_books(close, feats, dates, private):
    frames, books, peers, audit, exposure, book_rows, states = {}, defaultdict(dict), defaultdict(dict), [], [], [], []
    available = [s for s in SELECTORS if s not in ("OW", "OW_RESID")]
    for selector in available:
        peers[selector] = {}
    grid = {k: v for k, v in REG["grid"].items() if v["market"] == "US" and v["selector"] in available}
    by_date = {pd.Timestamp(d): g for d, g in feats.groupby("date", sort=True)}
    for day in dates:
        g = by_date.get(day)
        common = EV.common(g) if g is not None else pd.DataFrame()
        states.append({"date": day, "commonNames": len(common), "eligible": len(common) >= 30,
                       "pricedMemberRows": len(g) if g is not None else 0})
        books[ETF][day] = {"SPY": 1.0}
        if len(common) < 30:
            continue
        x = EV.score(common)
        frames[day] = x
        natives = {s: native_book(x, s, day) for s in available}
        for config, info in grid.items():
            books[config][day] = normalize_stock(natives[info["selector"]], info["q"])
        books["US:NATIVE_COCKTAIL"][day] = natives["COCKTAIL"]
        books["US:NATIVE_U1"][day] = natives["U1"]
        for selector in available:
            config = "US:" + selector + ":Q020"
            target = books[config][day]
            peer, legs = CM.match_book(x, target, "SPY", sector_col="sector", cap_col="marketCap")
            if peer is not None and any(t != "SPY" for t in target):
                peers[selector][day] = peer
            for leg in legs:
                audit.append({"date": day, "selector": selector, **leg})
        top5 = set(x["marketCap"].sort_values(ascending=False).head(5).index)
        for config in books:
            w = books[config].get(day)
            if w is None:
                continue
            for ticker, weight in w.items():
                book_rows.append({"date": day, "config": config, "ticker": ticker, "weight": weight})
            stocks = {t: v for t, v in w.items() if t != "SPY"}
            sector = defaultdict(float)
            for t, v in stocks.items():
                sector[x.at[t, "sector"]] += v
            exposure.append({"date": day, "config": config, "actualNames": len(stocks),
                             "stockWeight": sum(stocks.values()), "etfWeight": w.get("SPY", 0),
                             "megaWeight": sum(w.get(t, 0) for t in MEGA),
                             "capTop5Weight": sum(w.get(t, 0) for t in top5),
                             "largestSectorWeight": max(sector.values()) if sector else 0,
                             "nativeEtfWeight": natives.get(grid.get(config, {}).get("selector"), {}).get("SPY", 0),
                             "sectorWeights": json.dumps(sector, sort_keys=True)})
    blocked = {s: {"status": "BLOCKED_OPTIONAL_C2_INPUT_ABSENT",
                   "requiredFile": str(private.parent / "nport/round8/C2.pkl"),
                   "preservedCoreP": 1.0} for s in ("OW", "OW_RESID")}
    return frames, dict(books), dict(peers), grid, blocked, pd.DataFrame(audit), pd.DataFrame(exposure), pd.DataFrame(book_rows), pd.DataFrame(states)


def cohort_data(close, qqq, dates, books, peers):
    fixed, mdds, peer_net, entries, exits, asset_net, gap_rows = {}, {}, {}, {}, {}, {}, []
    for horizon in (126, 252):
        net = pd.DataFrame(np.nan, index=dates, columns=list(books))
        mdd = net.copy()
        peer = pd.DataFrame(np.nan, index=dates, columns=list(peers))
        entry = pd.Series(pd.NaT, index=dates, dtype="datetime64[ns]")
        exit_ = entry.copy()
        assets = {}
        for day in dates:
            pos = close.index.get_loc(day)
            if pos + 1 + horizon >= len(close):
                continue
            e, z = close.index[pos + 1], close.index[pos + 1 + horizon]
            entry.at[day], exit_.at[day] = e, z
            window = close.loc[e:z]
            assets[day] = EV.net(close.loc[z] / close.loc[e] - 1)
            for config, schedule in books.items():
                w = schedule.get(day)
                if w is None:
                    continue
                result = fixed_path(window, w)
                if result is not None:
                    net.at[day, config], mdd.at[day, config] = result["net"], result["mdd"]
                    if result["internalMissingMarks"]:
                        gap_rows.append({"date": day, "H": horizon, "config": config, **result})
            for selector, schedule in peers.items():
                if day in schedule:
                    result = fixed_path(window, schedule[day])
                    if result is not None:
                        peer.at[day, selector] = result["net"]
        qnet = pd.Series(np.nan, index=dates)
        for day in dates:
            if pd.notna(entry.at[day]) and pd.notna(exit_.at[day]):
                a, b = qqq.loc[entry.at[day]], qqq.loc[exit_.at[day]]
                if np.isfinite(a) and np.isfinite(b) and a > 0:
                    qnet.at[day] = EV.net(float(b / a - 1))
        fixed[horizon], mdds[horizon], peer_net[horizon] = net, mdd, peer
        entries[horizon], exits[horizon] = entry, exit_
        asset_net[horizon] = assets
        fixed[horizon]["US:QQQ"] = qnet
        print("US fixed windows", horizon, len(assets), flush=True)
    return fixed, mdds, peer_net, entries, exits, asset_net, pd.DataFrame(gap_rows)


def policies(fixed, mdds, exits, dates, grid, books):
    result = {}
    excess = fixed[126][list(grid)].subtract(fixed[126][ETF], axis=0)
    for policy in POLICIES:
        allowed = [k for k in grid if policy.endswith("ALL_LCB") or grid[k]["selector"] == "PRICE_CONFIRMED"]
        picked = CM.choose_policy(excess, mdds[126][list(grid)], mdds[126][ETF], exits[126], dates, grid, allowed)
        choices = picked["choices"]
        schedule = {}
        for day in dates:
            config = choices.loc[day]
            key = ETF if config == "ETF" else config
            if day in books[key]:
                schedule[day] = books[key][day]
            for horizon in (126, 252):
                fixed[horizon].at[day, policy] = fixed[horizon].at[day, key]
                mdds[horizon].at[day, policy] = mdds[horizon].at[day, key]
        books[policy] = schedule
        result[policy] = picked
    return result


def first_policy_fit(policy):
    trace = policy["trace"]
    if "sufficient" in trace:
        valid = trace[trace["sufficient"].astype(bool)]
        if not valid.empty:
            return pd.Timestamp(valid.iloc[0].get("date", valid.index[0]))
    for fit in policy["fits"]:
        n = fit.get("nTrain", 0)
        if n >= 104:
            return pd.Timestamp(fit.get("date", fit.get("fitDate")))
    return None


def summarise(fixed, mdds, peer_net, entries, exits, books, grid, blocked, dates, policies_, exposure):
    result = {"market": "US", "label": REG["label"], "designCommit": "e6786ee",
              "signalDates": [dates[0], dates[-1], len(dates)], "blocked": blocked,
              "fixed": {}, "selection": {}, "coreComparisons": {}, "policy": {}, "periods": {}}
    available = list(peer_net[126])
    warmups = {k: first_policy_fit(v) for k, v in policies_.items()}
    valid_starts = [d for d in warmups.values() if d is not None]
    post_start = max(valid_starts) if valid_starts else None
    result["postWarmupStart"] = post_start
    for k, v in policies_.items():
        result["policy"][k] = {"firstSufficientFit": warmups[k], "fits": v["fits"]}
    for h in (126, 252):
        net = fixed[h]
        excess = net.subtract(net[ETF], axis=0)
        common = net[list(grid)].notna().all(axis=1) & net[ETF].notna()
        select = pd.DataFrame({s: net["US:" + s + ":Q020"] - peer_net[h][s] for s in available}, index=dates)
        matched_common = select.notna().all(axis=1)
        result["fixed"][str(h)] = {}
        result["selection"][str(h)] = {}
        result["periods"][str(h)] = {}
        for config in books:
            own = CM.stats(excess[config], h)
            item = {"own": own, "common": CM.stats(excess[config], h, common),
                    "meanNet": float(net[config].mean()), "meanEtfNetOwnDates": float(net.loc[net[config].notna(), ETF].mean()),
                    "meanCohortMDD": float(mdds[h][config].mean()),
                    "meanNetExcessQQQ": float((net[config] - net["US:QQQ"]).mean())}
            if post_start is not None:
                item["postWarmup"] = CM.stats(excess[config], h, common & (dates >= post_start))
            result["fixed"][str(h)][config] = item
            periods = {"ENTRY_FROM_2023": entries[h] >= pd.Timestamp("2023-01-03"),
                       "EXIT_BY_2022": exits[h] <= pd.Timestamp("2022-12-30")}
            result["periods"][str(h)][config] = {p: CM.stats(excess[config], h, common & mask) for p, mask in periods.items()}
        for s in available:
            config = "US:" + s + ":Q020"
            total = len(books[config])
            matched = len([d for d in books[config] if d in books[config] and d in peer_net[h].index and pd.notna(peer_net[h].at[d, s])])
            result["selection"][str(h)][s] = {"own": CM.stats(select[s], h),
                "common": CM.stats(select[s], h, matched_common),
                "coverage": {"decisionWeeks": total, "maturedResolvedMatchedWeeks": matched,
                             "eligibleMaturedTargetWeeks": int((exits[h].notna() & pd.Series(dates.isin(books[config]), index=dates)).sum()),
                             "resolvedTargetWeeks": int(net[config].notna().sum()),
                             "pairedReturnWeeks": int(select[s].notna().sum()),
                             "commonMatchedReturnWeeks": int(matched_common.sum())}}
        for s in blocked:
            result["selection"][str(h)][s] = blocked[s]
            for config, metadata in REG["grid"].items():
                if metadata["market"] == "US" and metadata["selector"] == s:
                    result["fixed"][str(h)][config] = blocked[s]
        core = {}
        for claim in REG["coreClaims"]:
            if claim["market"] != "US":
                continue
            a, b = claim["a"], claim["b"]
            if claim["kind"] == "selection":
                series = select[claim["selector"]] if claim["selector"] in select else pd.Series(np.nan, index=dates)
                mask = matched_common
            elif a in excess:
                series = excess[a] if b == "ETF" else excess[a] - excess[b]
                mask = common.copy()
                if claim["kind"] == "factor":
                    ca = exposure[exposure["config"] == a].set_index("date")["actualNames"].reindex(dates)
                    cb = exposure[exposure["config"] == b].set_index("date")["actualNames"].reindex(dates)
                    mask &= (ca == 5) & (cb == 5)
                if claim["kind"] == "policy":
                    mask &= dates >= post_start if post_start is not None else False
            else:
                series, mask = pd.Series(np.nan, index=dates), common & False
            core[claim["id"]] = {"own": CM.stats(series, h), "common": CM.stats(series, h, mask)}
        result["coreComparisons"][str(h)] = core
        result.setdefault("commonDates", {})[str(h)] = {"portfolio": [d for d in dates[common]],
                                                        "selection": [d for d in dates[matched_common]]}
    return result


def attribution(fixed, entries, asset_net, books, dates):
    rows, years, summary = [], [], {}
    for h in (126, 252):
        summary[str(h)] = {}
        etf = fixed[h][ETF]
        for config, schedule in books.items():
            contrib = pd.DataFrame(np.nan, index=dates, columns=sorted({t for w in schedule.values() for t in w if t != "SPY"}))
            for day, w in schedule.items():
                if day not in asset_net[h] or pd.isna(fixed[h].at[day, config]):
                    continue
                if len(contrib.columns):
                    contrib.loc[day] = 0.0
                for ticker, weight in w.items():
                    if ticker != "SPY":
                        contrib.at[day, ticker] = weight * (asset_net[h][day][ticker] - etf.at[day])
                if abs(contrib.loc[day].sum() - (fixed[h].at[day, config] - etf.at[day])) > 1e-10:
                    raise AssertionError("TICKER_EXCESS_ATTRIBUTION_DOES_NOT_SUM:" + config)
            excess = fixed[h][config] - etf
            sums = contrib.sum(min_count=1)
            means = contrib.mean()
            for ticker in contrib:
                rows.append({"H": h, "config": config, "ticker": ticker,
                             "cohorts": int(excess.notna().sum()), "sumContribution": sums[ticker],
                             "meanContribution": means[ticker]})
            year_labels = entries[h].dt.year
            for year in sorted(year_labels.dropna().unique()):
                mask = year_labels == year
                v = CM.stats(excess, h, mask)
                years.append({"H": h, "config": config, "entryYear": int(year),
                              "sumContribution": float(excess[mask].sum()), **v})
            valid = excess.notna()
            mega_cols = [t for t in MEGA if t in contrib]
            mega = contrib[mega_cols].sum(axis=1) if mega_cols else pd.Series(0.0, index=dates)
            top = str(sums.idxmax()) if sums.notna().any() else None
            year_sums = excess.groupby(year_labels).sum(min_count=1)
            peak = int(year_sums.idxmax()) if year_sums.notna().any() else None
            direct = pd.Series({d: any(t in MEGA and w.get(t, 0) > 0 for t in w) for d, w in schedule.items()}).reindex(dates, fill_value=False)
            summary[str(h)][config] = {
                "label": "POST_HOC_SENSITIVITY_NOT_A_NEW_RULE", "original": CM.stats(excess, h),
                "fixedMegaMeanContribution": float(mega[valid].mean()) if valid.any() else None,
                "fixedMegaSignedShareOfTotal": float(mega[valid].sum() / excess[valid].sum()) if abs(excess[valid].sum()) > 1e-12 else None,
                "fixedMegaWeightsReturnedToETF": CM.stats(excess - mega, h),
                "excludeDirectMegaCohorts": CM.stats(excess, h, ~direct),
                "postHocMaximumTicker": top,
                "maximumTickerWeightsReturnedToETF": CM.stats(excess - contrib[top], h) if top else CM.stats(excess, h),
                "postHocMaximumEntryYear": peak,
                "excludeMaximumEntryYear": CM.stats(excess, h, year_labels != peak) if peak else CM.stats(excess, h)}
    return pd.DataFrame(rows), pd.DataFrame(years), summary


def native_baseline(fixed):
    old = json.loads((ROOT / "research/alpha_search_round6_v1/results/us.json").read_text())
    pc = json.loads((ROOT / "research/us_selection_value_v1/results/result.json").read_text())
    result = {}
    for h in (126, 252):
        result[str(h)] = {}
        for key, prior_key in (("US:NATIVE_COCKTAIL", "COCKTAIL"), ("US:NATIVE_U1", "U1_TOP5_CAP_NEUTRAL")):
            v = fixed[h][key] - fixed[h][ETF]
            prior = old["fixed"][str(h)]["FULL"][prior_key]["vsSPY"]
            result[str(h)][key] = {"currentN": int(v.notna().sum()), "originalN": prior["n"],
                                  "currentMean": float(v.mean()), "originalMean": prior["mean"],
                                  "meanGap": float(v.mean() - prior["mean"]),
                                  "originalCI": prior["ci"], "originalSource": "research/alpha_search_round6_v1/results/us.json"}
        v = fixed[h]["US:PRICE_CONFIRMED:Q100"] - fixed[h][ETF]
        prior = pc["fixedHolding"][f"PRICE_CONFIRMED|TOP5|{h}|ALL"]
        result[str(h)]["US:PRICE_CONFIRMED:Q100"] = {
            "currentN": int(v.notna().sum()), "originalN": prior["cohorts"],
            "currentMean": float(v.mean()), "originalMean": prior["meanNetExcessSPY"],
            "meanGap": float(v.mean() - prior["meanNetExcessSPY"]),
            "originalSource": "research/us_selection_value_v1/results/result.json"}
    return result


def run_fixed(private, out):
    out.mkdir(parents=True, exist_ok=True)
    close, feats, qqq, bench_meta = EV.load(private)
    prior = json.loads((ROOT / "research/alpha_search_round6_v1/results/us.json").read_text())["signalDates"]
    from research.us_selection_value_v1.features import weekly_signal_dates
    dates = pd.DatetimeIndex([d for d in weekly_signal_dates(close) if prior[0] <= str(d.date()) <= prior[1]])
    frames, books, peers, grid, blocked, audit, exposure, book_rows, states = make_books(close, feats, dates, private)
    print("US books", len(frames), len(books), "peer candidates", len(peers), flush=True)
    fixed, mdds, peer_net, entries, exits, assets, gaps = cohort_data(close, qqq, dates, books, peers)
    policy = policies(fixed, mdds, exits, dates, grid, books)
    policy_book_rows, policy_exposure = [], []
    indexed_exposure = exposure.set_index(["date", "config"])
    for policy_id, fitted in policy.items():
        for day in dates:
            chosen = fitted["choices"].loc[day]
            source = ETF if chosen == "ETF" else chosen
            for ticker, weight in books[policy_id].get(day, {}).items():
                policy_book_rows.append({"date": day, "config": policy_id, "ticker": ticker,
                                         "weight": weight, "chosenConfig": source})
            if (day, source) in indexed_exposure.index:
                row = indexed_exposure.loc[(day, source)].to_dict()
                policy_exposure.append({"date": day, "config": policy_id, "chosenConfig": source, **row})
    book_rows = pd.concat([book_rows, pd.DataFrame(policy_book_rows)], ignore_index=True)
    exposure = pd.concat([exposure, pd.DataFrame(policy_exposure)], ignore_index=True)
    summary = summarise(fixed, mdds, peer_net, entries, exits, books, grid, blocked, dates, policy, exposure)
    ticker, year, sensitivity = attribution(fixed, entries, assets, books, dates)
    summary["sensitivity"] = sensitivity
    summary["nativeBaselineDiff"] = native_baseline(fixed)
    summary["nativeNormalizationEffect"] = {
        str(h): {s: CM.stats(fixed[h][f"US:{s}:Q100"] - fixed[h][f"US:NATIVE_{s}"], h)
                 for s in ("COCKTAIL", "U1")} for h in (126, 252)}
    summary["benchmarkAdjustments"] = bench_meta
    summary["inputPreparation"] = json.loads((private / "input-preparation-summary.json").read_text())
    summary["matching"] = {"caliper": [.5, 2], "peerPool": "EV.common on same date", "withoutReplacement": True,
                           "auditLegs": len(audit), "failureCounts": audit["reason"].value_counts().to_dict() if "reason" in audit else {}}
    summary["matching"]["bySelector"] = {}
    for selector in peers:
        a = audit[audit["selector"] == selector]
        matched = a["reason"] == "MATCHED"
        eligible = sum(any(t != "SPY" and w > 0 for t, w in target.items())
                       for target in books["US:" + selector + ":Q020"].values())
        total_weight = a["weight"].sum()
        summary["matching"]["bySelector"][selector] = {
            "allDecisionWeeks": len(dates), "nonemptyEligibleBookWeeks": eligible,
            "fullyMatchedDecisionWeeks": len(peers[selector]),
            "completeBookMatchRate": len(peers[selector]) / eligible if eligible else None,
            "legMatchRate": float(matched.mean()) if len(a) else None,
            "weightedLegCoverage": float(a.loc[matched, "weight"].sum() / total_weight) if total_weight > 0 else None,
            "unmatchedLegReasons": a.loc[~matched, "reason"].value_counts().to_dict(),
            "matchedCapRatioMinimum": float(a.loc[matched, "capRatio"].min()),
            "matchedCapRatioMaximum": float(a.loc[matched, "capRatio"].max())}
    summary["etfKey"] = ETF
    summary["exposure"] = {}
    for config, exp in exposure.groupby("config"):
        summary["exposure"][config] = {
            "weeks": len(exp), "meanActualNames": float(exp["actualNames"].mean()),
            "minimumActualNames": int(exp["actualNames"].min()),
            "maximumActualNames": int(exp["actualNames"].max()),
            "meanStockWeight": float(exp["stockWeight"].mean()),
            "meanEtfWeight": float(exp["etfWeight"].mean()),
            "meanDirectMegaWeight": float(exp["megaWeight"].mean()),
            "meanCommonCapTop5Weight": float(exp["capTop5Weight"].mean()),
            "meanLargestSectorWeight": float(exp["largestSectorWeight"].mean()),
            "etfLookThroughIncluded": False}
    summary["coverage"] = {"originalSignalWeeks": prior[2], "currentTimeAxisWeeks": len(dates),
                           "currentEligibleWeeks": len(frames), "dailyMddCarryMarkWindows": len(gaps)}
    for h in (126, 252):
        excess = fixed[h].subtract(fixed[h][ETF], axis=0)
        csv(out, f"cohorts-net-{h}", fixed[h])
        csv(out, f"cohorts-excess-{h}", excess)
        csv(out, f"cohorts-mdd-{h}", mdds[h])
        csv(out, f"peer-cohorts-net-{h}", peer_net[h])
        csv(out, f"cohort-dates-{h}", pd.DataFrame({"entry": entries[h], "exit": exits[h]}))
    for name, frame in (("books", book_rows), ("matching-audit", audit), ("exposure", exposure),
                        ("signal-coverage", states), ("daily-mdd-mark-gaps", gaps),
                        ("ticker-contribution", ticker), ("entry-year-contribution", year)):
        csv(out, name, frame)
    for key, value in policy.items():
        csv(out, key.split(":")[-1] + "-trace", value["trace"])
        save(out / (key.split(":")[-1] + "-fits.json"), value["fits"])
    save(out / "summary.json", summary)
    with (private / "batch-us-state.pkl").open("wb") as f:
        pickle.dump({"close": close, "books": books, "dates": dates, "grid": grid,
                     "postWarmupStart": summary["postWarmupStart"]}, f)
    print("US fixed results written", out, flush=True)


def replacement_diagnostics(prices, orders):
    previous, last_day = {}, None
    names_replaced = names_entered = names_exited = carried_retarget = traded = 0.0
    for day, target in sorted(orders.items()):
        if last_day is None:
            drifted = previous
        else:
            ratios = {t: float(prices.at[day, t] / prices.at[last_day, t]) for t in previous}
            growth = sum(previous[t] * ratios[t] for t in previous)
            drifted = {t: previous[t] * ratios[t] / growth for t in previous}
        entered = (set(target) - set(previous)) - {"SPY"}
        exited = (set(previous) - set(target)) - {"SPY"}
        names_entered += len(entered)
        names_exited += len(exited)
        names_replaced += min(len(entered), len(exited))
        for ticker in set(drifted) | set(target):
            delta = abs(target.get(ticker, 0) - drifted.get(ticker, 0))
            traded += delta
            if ticker in previous and ticker in target:
                carried_retarget += delta
        previous, last_day = target, day
    return {"namesReplaced": names_replaced, "namesEntered": names_entered, "namesExited": names_exited,
            "carriedWeightRetarget": carried_retarget,
            "targetChangeTwoWay": traded, "rebalanceEvents": len(orders)}


def ledger_one(task):
    config, interval, close, schedule, dates, post_start = task
    prices = close.loc[dates[0]:]
    accounts, diagnostics = [], []
    for phase in range(interval):
        orders = {prices.index[1]: {"SPY": 1.0}}
        for i in range(phase, len(dates), interval):
            day = dates[i]
            if day not in schedule:
                return config, interval, {"status": "NOT_ESTIMABLE", "reason": "SIGNAL_UNAVAILABLE:" + str(day.date())}, None
            pos = close.index.get_loc(day)
            fill = close.index[pos + 1]
            orders[fill] = schedule[day]
        columns = sorted({t for w in orders.values() for t in w})
        try:
            accounts.append(UP.simulate(prices[columns], orders))
            diagnostics.append(replacement_diagnostics(prices, orders))
        except ValueError as error:
            return config, interval, {"status": "NOT_ESTIMABLE", "reason": str(error)}, None
    nav = sum(a["nav"] for a in accounts) / interval
    costs = sum(a["costInitialCapital"] for a in accounts) / interval
    turnover = sum(a["twoWayTurnover"] for a in accounts) / interval
    years = (len(nav) - 1) / 252
    benchmark = UP.simulate(prices[["SPY"]], {prices.index[1]: {"SPY": 1.0}})["nav"]
    full = CM.nav_window(nav, benchmark)
    raw_spy = prices["SPY"] / prices["SPY"].iloc[0]
    raw_comparison = CM.nav_window(nav, raw_spy)
    full.update(rawSpyCagr=raw_comparison["etfCagr"], rawSpyMdd=raw_comparison["etfMdd"],
                cagrGapVersusRawSpy=raw_comparison["cagrGap"],
                annualArithmeticGapVersusRawSpy=raw_comparison["annualArithmeticDailyGap"],
                rawBenchmarkNote="Original R6 decision-close SPY TR without initial trading cost; main uses next-close costed ETF account.")
    full["rawDecisionDaySpyComparison"] = CM.nav_window(nav, prices["SPY"] / prices["SPY"].iloc[0])
    full.update(status="ESTIMATED_DESCRIPTIVE", costPerYear=float(costs.sum() / years),
                oneWayTurnoverPerYear=float(turnover.sum() / 2 / years),
                namesReplacedPerYear=sum(d["namesReplaced"] for d in diagnostics) / interval / years,
                namesEnteredPerYear=sum(d["namesEntered"] for d in diagnostics) / interval / years,
                namesExitedPerYear=sum(d["namesExited"] for d in diagnostics) / interval / years,
                carriedWeightRetargetPerYear=sum(d["carriedWeightRetarget"] for d in diagnostics) / interval / years,
                diagnostics="Name replacement excludes SPY; carried retarget uses pre-cost drifted weights and is a separate target-change diagnostic.")
    result = {"full": full}
    if config in ("US:NATIVE_COCKTAIL", "US:NATIVE_U1"):
        reference = json.loads((ROOT / "research/alpha_search_round6_v1/results/us.json").read_text())
        selector = "COCKTAIL" if config.endswith("COCKTAIL") else "U1_TOP5_CAP_NEUTRAL"
        original = reference["ledgers"][f"L{interval}|FULL|{selector}"]
        result["nativePublishedBaselineDiff"] = {
            "currentCagr": full["cagr"], "publishedCagr": original["cagr"],
            "ownCagrGap": full["cagr"] - original["cagr"],
            "currentMdd": full["mdd"], "publishedMdd": original["mdd"],
            "mddGap": full["mdd"] - original["mdd"],
            "currentOneWayTurnoverPerYear": full["oneWayTurnoverPerYear"],
            "publishedOneWayTurnoverPerYear": original["oneWayTurnoverPerYear"],
            "oneWayTurnoverPerYearGap": full["oneWayTurnoverPerYear"] - original["oneWayTurnoverPerYear"],
            "currentCostedEtfCagr": full["etfCagr"], "publishedRawSpyCagr": original["spyCagr"],
            "benchmarkHarnessDifference": "Published R6 benchmark starts at decision-day close without cost; batch ETF is the original engine's next-close costed SPY account. Native own NAV is compared separately."}
    if post_start is not None:
        post_nav, post_bench = nav.loc[pd.Timestamp(post_start):], benchmark.loc[pd.Timestamp(post_start):]
        result["postWarmup"] = CM.nav_window(post_nav, post_bench)
        result["postWarmup"]["inheritedPositionsNotFreshReset"] = True
    return config, interval, result, pd.DataFrame({"nav": nav, "spy": benchmark, "rawSpy": raw_spy, "costInitialCapital": costs, "twoWayTurnover": turnover})


def run_ledgers(private, out, workers):
    with (private / "batch-us-state.pkl").open("rb") as f:
        state = pickle.load(f)
    summary = json.loads((out / "summary.json").read_text())
    summary["ledgers"] = {"L26": {}, "L52": {}}
    tasks = [(key, interval, state["close"], schedule, state["dates"], state["postWarmupStart"])
             for interval in (26, 52) for key, schedule in state["books"].items()]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(ledger_one, task) for task in tasks]
        for future in as_completed(futures):
            key, interval, result, frame = future.result()
            summary["ledgers"][f"L{interval}"][key] = result
            if frame is not None:
                csv(out, f"NAV-L{interval}-" + key.replace(":", "_"), frame)
            save(out / "summary.json", summary)
            print("US ledger complete", interval, key, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=HERE / "results/US")
    parser.add_argument("--stage", choices=("all", "fixed", "ledgers"), default="all")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if args.stage in ("all", "fixed"):
        run_fixed(args.private, args.out)
    if args.stage in ("all", "ledgers"):
        run_ledgers(args.private, args.out, args.workers)


if __name__ == "__main__":
    main()
