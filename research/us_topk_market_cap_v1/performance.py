"""Evaluate ONLY already frozen rankings; private labels never enter git."""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import hashlib
import json
import math

import numpy as np
import pandas as pd

from pipeline import replay_calendar as RC
from pipeline.us_decision_pilot import rebalance
from research.us_historical_market_recovery_v1 import engine as E
from research.us_historical_market_recovery_v1.public_prices import load_public_prices, PARA_TERMINAL
from research.us_topk_market_cap_v1.inputs import invert_forward, read, write

BUY, SELL = .0008, .00083
ASOF = "2026-11-13"
COMPLETE = "COMPLETE_ORIGINAL_RESEARCH_CONTRACT"


def net(gross, cash_wealth=0.):
    # Contractual terminal cash needs no market sell at H; cash_wealth is
    # dollar wealth per pre-buy-cost dollar, not a portfolio weight at entry.
    return ((1 + gross) * (1 - SELL) + cash_wealth * SELL) / (1 + BUY) - 1


def weights(selected, mode):
    if not selected:
        raise ValueError("NO_SELECTED_COMPANIES")
    denominator = sum(r["cap"] for r in selected)
    return {r["ticker"]: (1 / len(selected) if mode == "equal_company" else r["cap"] / denominator)
            for r in selected}


def summarize(rows, calendar):
    valid = [r for r in rows if r["status"] == "COMPLETE"]
    mature = [r for r in rows if r["end"] <= ASOF]
    values = np.array([r["excess"] for r in valid], dtype=float)
    h = rows[0]["horizon"] if rows else None
    # Greedy count of disjoint holding intervals, not an IID effective n.
    previous_end, independent = "", 0
    for row in sorted(valid, key=lambda r: r["entry"]):
        if row["entry"] > previous_end:
            independent += 1
            previous_end = row["end"]
    out = {"ranked_cohorts": len(rows), "mature_denominator": len(mature), "complete_cohorts": len(valid),
           "failed_mature_cohorts": dict(Counter(r["status"] for r in mature if r["status"] != "COMPLETE")),
           "immature": len(rows) - len(mature), "disjoint_holding_intervals": independent,
           "mean_excess": float(values.mean()) if len(values) else None,
           "median_excess": float(np.median(values)) if len(values) else None,
           "win_rate": float((values > 0).mean()) if len(values) else None,
           "p10_excess": float(np.quantile(values, .1)) if len(values) else None,
           "mean_net_return": float(np.mean([r["net_return"] for r in valid])) if valid else None,
           "mean_spy_net_return": float(np.mean([r["spy_net_return"] for r in valid])) if valid else None,
           "first_signal": min((r["signal"] for r in valid), default=None),
           "last_signal": max((r["signal"] for r in valid), default=None)}
    # Segmented moving blocks preserve overlapping 126/252-session cohorts.
    length = math.ceil(h / 5) if h else None
    runs, run = [], []
    for row in sorted(valid, key=lambda r: r["entry"]):
        if run and calendar.index(row["entry"]) - calendar.index(run[-1]["entry"]) > 6:
            runs.append(run)
            run = []
        run.append(row)
    if run:
        runs.append(run)
    out["block_length_weeks"] = length
    out["consecutive_run_lengths"] = [len(r) for r in runs]
    out["moving_block_mean_ci95"] = None
    out["block_ci_status"] = "INSUFFICIENT_CONTIGUOUS_SUPPORT"
    if runs and all(len(r) >= length for r in runs) and independent >= 2:
        rng = np.random.default_rng(340253)
        draws = np.zeros(2000)
        for run in runs:
            x = np.array([r["excess"] for r in run])
            starts = rng.integers(0, len(x) - length + 1, size=(2000, math.ceil(len(x) / length)))
            expanded = x[starts[:, :, None] + np.arange(length)].reshape(2000, -1)[:, :len(x)]
            draws += expanded.sum(axis=1) / len(values)
        out["moving_block_mean_ci95"] = np.quantile(draws, [.025, .975]).tolist()
        out["block_ci_status"] = "SEGMENTED_MOVING_BLOCK_EXPLORATORY_NO_MULTIPLICITY_CORRECTION"
    return out


class Returns:
    def __init__(self, private):
        self.calendar = [str(d.date()) for d in RC.sessions("2011-01-03", "2028-01-14", "US")]
        self.holdings = {(r["signal"], r["horizon"], r["ticker"]): r
                         for r in read(private / "holding-returns.json.gz") if r["phase"] == "after"}
        original = read(private / "baseline-bars.json.gz")
        original_events = read(private / "baseline-events.json.gz")
        self.baseline = {}
        for ticker, data in original.items():
            if ticker == "PARA":
                continue
            tr = pd.Series({d: r["Close"] for d, r in data.items()}, dtype=float).sort_index()
            tr.index = pd.to_datetime(tr.index)
            good = {d for d, r in data.items() if E.positive(r["Close"]) and E.positive(r.get("Volume"))}
            raw = pd.Series(invert_forward(data, original_events.get(ticker, {}), "2026-09-14"), dtype=float)
            raw.index = pd.to_datetime(raw.index)
            self.baseline[ticker] = E.Series(ticker, tr, raw, good,
                                             "PINNED_ORIGINAL_TR", "f0781292", True, True)
        self.preferred = {}
        for ticker, r in read(private / "new-source-series.json.gz").items():
            tr = pd.Series(r["tr"], dtype=float).sort_index()
            raw = pd.Series(r["raw_close"], dtype=float).sort_index()
            tr.index, raw.index = pd.to_datetime(tr.index), pd.to_datetime(raw.index)
            self.preferred[ticker] = E.Series(ticker, tr, raw, set(r["good_days"]),
                                              r["source"], r["receipt"], True, True)
        public, _ = load_public_prices(private, original, self.calendar)
        self.preferred.update(public)
        del original
        for old, new in {"ABC": "COR", "BLL": "BALL", "FB": "META", "ANTM": "ELV"}.items():
            if old in self.preferred and new not in self.preferred:
                self.preferred[new] = self.preferred[old]
            if old in self.baseline and new not in self.baseline:
                self.baseline[new] = self.baseline[old]
        terms_path = Path(__file__).resolve().parents[1] / "us_historical_market_recovery_v1/inputs/terminal-followup.json"
        self.terminals = read(terms_path)
        self.terminals["MRO"] = {"date": "2024-11-22", "shares": .255, "successor": "COP",
            "cash_in_lieu_required": True, "effective_before_open": True, "verified": True,
            "citation": "https://www.sec.gov/Archives/edgar/data/1163165/000110465924122112/tm2428935d2_8k.htm",
            **self.terminals["MRO"]}
        if "WBA" in self.preferred:
            self.terminals["WBA"] = {"date": "2025-08-28", "cash": 11.45, "cvr": True,
                "last_trading_date": max(d for d in self.preferred["WBA"].good_days if d < "2025-08-28"),
                "verified": True, "effective_before_open": True,
                "citation": "https://www.sec.gov/Archives/edgar/data/1618921/000119312525190603/d87240dex991.htm"}
        self.terminals["PARA"] = PARA_TERMINAL
        for ticker, cash, date in [("ATVI", 95., "2023-10-13"), ("TWTR", 54.2, "2022-10-27")]:
            s = self.preferred.get(ticker)
            if s:
                self.terminals[ticker] = {"date": date, "cash": cash, "verified": True,
                    "last_trading_date": max(d for d in s.good_days if d < date),
                    "citation": "REUSED_VERIFIED_RECOVERY_TERMS", "effective_before_open": True}
        self.cache = {}

    def get(self, ticker, entry, end, signal=None, horizon=None):
        key = ticker, entry, end
        if key in self.cache:
            return self.cache[key]
        if end > ASOF:
            return {"status": "HOLDING_NOT_MATURE"}
        terminal = self.terminals.get(ticker)
        is_cash = bool(terminal and entry <= terminal["date"] <= end and terminal.get("cash") is not None
                       and not terminal.get("shares") and not terminal.get("cvr"))
        old = self.holdings.get((signal, horizon, ticker))
        if old is not None:
            if old["entry"] != entry or old["end"] != end:
                raise ValueError("CORRECTED_CACHED_HOLDING_CALENDAR_MISMATCH")
            if old["status"] == COMPLETE:
                result = {"status": "COMPLETE", "gross": old["gross_usd_total_return"],
                          "source": "EXACT_CORRECTED_HOLDING_PATH_REUSED", "cash_terminal": is_cash}
                self.cache[key] = result
                return result
            # Accounting eligibility is not a gate in the full-index cap study.
            if "CIK" not in old["status"] and old["end"] <= ASOF:
                result = {"status": old["status"]}
                self.cache[key] = result
                return result
        preferred, baseline = self.preferred.get(ticker), self.baseline.get(ticker)
        needed = E.required_old_quote_end(entry, end, terminal)
        series = E.whole_window_source(preferred, baseline, entry, needed)
        if series is None:
            result = {"status": "PRICE_SOURCE_UNAVAILABLE"}
        else:
            try:
                gross = E.holding(series, entry, end, self.calendar, terminal=terminal,
                                  successors=self.preferred)
                result = {"status": "COMPLETE", "gross": gross, "source": series.source, "cash_terminal": is_cash}
            except E.Unresolved as exc:
                result = {"status": str(exc)}
        self.cache[key] = result
        return result


def concentration(selected, allocation):
    sectors = defaultdict(float)
    for row in selected:
        sectors[row["sector"]] += allocation[row["ticker"]]
    w, s = sorted(allocation.values(), reverse=True), sorted(sectors.values(), reverse=True)
    return {"company_top1": w[0], "company_top5": sum(w[:5]),
            "company_hhi": sum(v * v for v in w), "company_effective_n": 1 / sum(v * v for v in w),
            "sector_top1": s[0], "sector_hhi": sum(v * v for v in s),
            "sector_effective_n": 1 / sum(v * v for v in s), "sector_weights": dict(sectors)}


def run_nav(ranks, mode, returns):
    segments, current = [], None
    for index, rank in enumerate(ranks):
        if not rank["status"].startswith("VERIFIED"):
            if current:
                current["end_reason"] = "NEXT_RANK_UNVERIFIED"
                segments.append(current)
            current = None
            continue
        if index + 1 == len(ranks):
            break
        start, end = rank["entry"], ranks[index + 1]["entry"]
        if returns.calendar.index(end) - returns.calendar.index(start) > 6 or end > ASOF:
            if current:
                current["end_reason"] = "NONCONSECUTIVE_RANK_OR_FUTURE"
                segments.append(current)
            current = None
            continue
        target = weights(rank["selected"], mode)
        growth = {t: returns.get(t, start, end) for t in target}
        spy = returns.get("SPY", start, end)
        if any(r["status"] != "COMPLETE" for r in [*growth.values(), spy]):
            if current:
                current["end_reason"] = "WEEKLY_PRICE_OR_TERMINAL_GAP"
                segments.append(current)
            current = None
            continue
        if current is None:
            current = {"first_entry": start, "last_mark": start, "nav": 1., "spy_nav": 1.,
                       "weights": {}, "turnover": 0., "cost_initial_capital": 0.,
                       "weekly": [], "daily": [], "peak": 1., "mdd": 0.,
                       "daily_peak": 1., "daily_mdd": 0.}
        fee, turnover = rebalance(current["weights"], target, BUY, SELL)
        post = target  # Target weights are fractions of NAV after fees.
        current["cost_initial_capital"] += current["nav"] * fee
        current["turnover"] += turnover
        before = current["nav"]
        spy_before = current["spy_nav"]
        spy_entry_factor = 1 / (1 + BUY) if not current["weekly"] else 1
        for day in returns.calendar[returns.calendar.index(start) + 1:returns.calendar.index(end) + 1]:
            labels = {t: returns.get(t, start, day) for t in target}
            spy_day = returns.get("SPY", start, day)
            if any(r["status"] != "COMPLETE" for r in [*labels.values(), spy_day]):
                raise ValueError("COMPLETE_WEEK_HAS_UNRESOLVED_DAILY_MARK")
            daily_nav = before * (1 - fee) * (sum(target[t] * (1 + labels[t]["gross"]) for t in target)
                                             + max(0., 1 - sum(target.values())))
            current["daily_peak"] = max(current["daily_peak"], daily_nav)
            current["daily_mdd"] = min(current["daily_mdd"], daily_nav / current["daily_peak"] - 1)
            current["daily"].append({"date": day, "nav": daily_nav,
                                     "spy_nav": spy_before * spy_entry_factor * (1 + spy_day["gross"])})
        marked = {t: post[t] * (1 + growth[t]["gross"]) for t in post}
        gain = sum(marked.values()) + max(0., 1 - sum(post.values()))
        current["nav"] *= (1 - fee) * gain
        current["weights"] = {t: v / gain for t, v in marked.items() if not growth[t].get("cash_terminal")}
        current["spy_nav"] *= (1 + spy["gross"]) * spy_entry_factor
        current["last_mark"] = end
        current["peak"] = max(current["peak"], current["nav"])
        current["mdd"] = min(current["mdd"], current["nav"] / current["peak"] - 1)
        current["weekly"].append({"entry": start, "mark": end, "nav": current["nav"],
                                  "spy_nav": current["spy_nav"], "fee": fee,
                                  "turnover": turnover, "weekly_return": current["nav"] / before - 1})
    if current:
        current["end_reason"] = "LAST_AVAILABLE_VERIFIED_RANK_RIGHT_CENSORED"
        segments.append(current)
    for segment in segments:
        segment.pop("weights", None)
        segment.pop("peak", None)
        segment.pop("daily_peak", None)
        segment["intervals"] = len(segment["weekly"])
        segment["return_before_hypothetical_end_sell"] = segment["nav"] - 1
        segment["spy_return_before_end_sell"] = segment["spy_nav"] - 1
        segment["weekly_observation_mdd"] = segment.pop("mdd")
        segment["excess_if_liquidated_at_last_observed_mark"] = (segment["nav"] - segment["spy_nav"]) * (1 - SELL)
    return segments


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--market-private", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    receipt = read(args.output / "rank-freeze-receipt.json")
    for name, sha in receipt["files"].items():
        if hashlib.sha256((args.private / name).read_bytes()).hexdigest() != sha:
            raise ValueError("FROZEN_RANKS_CHANGED")
    ranks = read(args.private / "rankings.json.gz")
    returns = Returns(args.market_private)  # First forward-label access AFTER hash verification.
    cohorts, concentrations = [], []
    for rank in ranks:
        if not rank["status"].startswith("VERIFIED"):
            continue
        for mode in ("equal_company", "company_market_cap"):
            allocation = weights(rank["selected"], mode)
            concentrations.append({"signal": rank["signal"], "pool": rank["pool"], "k": rank["k"],
                                   "weighting": mode, **concentration(rank["selected"], allocation)})
            for h in (126, 252):
                end = rank["exits"][str(h)]
                labels = {t: returns.get(t, rank["entry"], end, rank["signal"], h) for t in allocation}
                spy = returns.get("SPY", rank["entry"], end)
                row = {"signal": rank["signal"], "entry": rank["entry"], "end": end, "horizon": h,
                       "pool": rank["pool"], "k": rank["k"], "weighting": mode,
                       "status": "COMPLETE", "failed_names": {t: r["status"] for t, r in labels.items() if r["status"] != "COMPLETE"}}
                if end > ASOF:
                    row["status"] = "HOLDING_NOT_MATURE"
                elif row["failed_names"]:
                    row["status"] = "SELECTED_HOLDING_INCOMPLETE_NO_REPLACEMENT"
                elif spy["status"] != "COMPLETE":
                    row["status"] = "SPY_" + spy["status"]
                else:
                    gross = sum(allocation[t] * labels[t]["gross"] for t in allocation)
                    cash = sum(allocation[t] * (1 + labels[t]["gross"]) for t in allocation if labels[t].get("cash_terminal"))
                    row["net_return"] = net(gross, cash)
                    row["spy_net_return"] = net(spy["gross"])
                    row["excess"] = row["net_return"] - row["spy_net_return"]
                cohorts.append(row)
    write(args.private / "performance-cohorts.json.gz", cohorts)
    write(args.private / "path-cache.json.gz", [{"ticker": t, "entry": a, "end": b, **r} for (t, a, b), r in returns.cache.items()])
    groups = defaultdict(list)
    for r in cohorts:
        groups[r["pool"], r["k"], r["weighting"], r["horizon"], "ALL"].append(r)
        groups[r["pool"], r["k"], r["weighting"], r["horizon"], r["signal"][:4]].append(r)
    stats = [{"pool": p, "k": k, "weighting": w, "horizon": h, "signal_year": y,
              **summarize(rows, returns.calendar)} for (p, k, w, h, y), rows in sorted(groups.items())]
    write(args.output / "performance-summary.json", stats)
    write(args.output / "concentration.json", concentrations)
    nav = []
    for pool in sorted({r["pool"] for r in ranks}):
        for k in (5, 10, 100):
            selected = sorted((r for r in ranks if r["pool"] == pool and r["k"] == k), key=lambda r: r["signal"])
            for mode in ("equal_company", "company_market_cap"):
                nav.append({"pool": pool, "k": k, "weighting": mode, "segments": run_nav(selected, mode, returns)})
    write(args.output / "nav-segments.json", nav)
    write(args.private / "path-cache.json.gz", [{"ticker": t, "entry": a, "end": b, **r} for (t, a, b), r in returns.cache.items()])
    write(args.output / "performance-execution.json", {
        "rank_receipt_sha256": hashlib.sha256((args.output / "rank-freeze-receipt.json").read_bytes()).hexdigest(),
        "rank_phase": receipt["phase"], "cohort_rows": len(cohorts),
        "complete_rows": sum(r["status"] == "COMPLETE" for r in cohorts),
        "private_path_sources": dict(Counter(r.get("source", r["status"]) for r in returns.cache.values())),
        "no_replacement": True, "returns_read_after_frozen_rank_hash_check": True})
    print(json.dumps([r for r in stats if r["signal_year"] == "ALL"], indent=2))


if __name__ == "__main__":
    main()
