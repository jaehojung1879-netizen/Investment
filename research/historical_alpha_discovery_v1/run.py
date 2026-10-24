"""One fixed exploratory experiment, independent of every sealed executor.

Run from the repository root: python -m research.historical_alpha_discovery_v1.run
Only explicit pinned Git blobs are read. No network, production imports or ledgers.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess

import exchange_calendars as xc
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPEC = json.loads((HERE / "spec.json").read_text())
ETF = "069500.KS"
BOOKS = ("ETF", "MOMENTUM", "INTRADAY", "OVERNIGHT", "HALF_INTRADAY_HALF_ETF")
KNOWN_BASIS_BLOCK = {"006800.KS"}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def calendar(start, end):
    days = xc.get_calendar("XKRX", start="2012-01-01", end="2027-12-31").sessions.tz_localize(None)
    # Same published exceptional closure correction as existing replay_calendar.
    days = days.difference(pd.to_datetime(["2026-05-25", "2026-06-03", "2026-07-17"]))
    return days[(days >= start) & (days <= end)]


class GitInputs:
    def __init__(self, root=ROOT, commit=SPEC["dataCommit"]):
        self.root, self.commit, self.identities = Path(root), commit, {}
        if not re.fullmatch("[0-9a-f]{40}", commit):
            raise ValueError("EXACT_SOURCE_COMMIT_REQUIRED")

    def blob(self, path):
        raw = subprocess.check_output(["git", "show", self.commit + ":" + path], cwd=self.root)
        self.identities[path] = digest(raw)
        return raw

    def rows(self, path):
        return [json.loads(line) for line in gzip.decompress(self.blob(path)).splitlines() if line]


def load_inputs():
    source = GitInputs()
    universe = []
    for year in range(2013, 2027):
        universe.extend(source.rows(f"ledger/universe/kr/krx-universe-{year}.jsonl.gz"))
    universe = pd.DataFrame(universe)
    if universe.duplicated(["date", "ticker"]).any():
        raise ValueError("DUPLICATE_UNIVERSE_KEY")
    ever = set(universe.loc[universe["rank"] <= 120, "ticker"])
    raw = []
    raw_counts = {}
    for year in range(2013, 2027):
        rows = source.rows(f"ledger/prices/kr/krx-prices-{year}.jsonl.gz")
        raw_counts[str(year)] = {
            "allRows": len(rows),
            "allTickers": len({r["ticker"] for r in rows}),
            "dateMin": min(r["date"] for r in rows),
            "dateMax": max(r["date"] for r in rows),
        }
        raw.extend(r for r in rows if r["ticker"] in ever and r["date"] <= SPEC["through"])
    raw = pd.DataFrame(raw)
    if raw.duplicated(["date", "ticker"]).any():
        raise ValueError("DUPLICATE_KRX_PRICE_KEY")
    manifest_raw = source.blob("ledger/historical/replay-v16/inputs.json")
    manifest = json.loads(manifest_raw)
    adjusted = []
    for name, refs in sorted(manifest["components"].items()):
        if not name.startswith("price/") or not "2013-01" <= name[6:] <= SPEC["through"][:7]:
            continue
        for ref in refs:
            decoded = gzip.decompress(source.blob("ledger/replay-inputs/objects/" + ref + ".json.gz"))
            if digest(decoded) != ref:
                raise ValueError("PRICE_CONTENT_HASH_MISMATCH")
            adjusted.extend(r for r in json.loads(decoded) if r["ticker"] in ever and r["date"] <= SPEC["through"])
    adjusted = pd.DataFrame(adjusted)
    if adjusted.duplicated(["date", "ticker"]).any():
        raise ValueError("DUPLICATE_REPLAY_PRICE_KEY")
    days = calendar(SPEC["sourceStart"], SPEC["through"])
    matrices = {
        k: raw.pivot(index="date", columns="ticker", values=k)
        .set_axis(pd.to_datetime(sorted(raw.date.unique())), axis=0)
        .reindex(days)
        for k in ("open", "close", "volume", "listedShares")
    }
    prices = adjusted.pivot(index="date", columns="ticker", values="Close")
    prices.index = pd.to_datetime(prices.index)
    matrices["adjusted"] = prices.reindex(days)
    correction_path = ROOT / "docs/audits/kr-alpha-atlas-phase-c-integrity/corrected-inputs.json"
    correction = json.loads(correction_path.read_text())
    # Use the existing externally reconciled ETF index, not raw price or NAV.
    benchmark = pd.DataFrame(correction["benchmarkQuotes"]).set_index("date")["Close"]
    benchmark.index = pd.to_datetime(benchmark.index)
    matrices["benchmark"] = benchmark.reindex(days)
    if matrices["benchmark"].isna().any() or (matrices["benchmark"] <= 0).any():
        raise ValueError("BENCHMARK_SESSION_GAP")
    inventory_path = ROOT / "docs/results/kr-termination-inventory.json"
    inventory = json.loads(inventory_path.read_text())["securities"]
    terminal = {r["code"]: r["lastTradingDate"] for r in inventory}
    industry_path = ROOT / "data/kr-industry-membership-foundation-v4/state/intervals.json.gz"
    industries = json.loads(gzip.decompress(industry_path.read_bytes()))
    local = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in (correction_path, inventory_path, industry_path)}
    return source, universe, matrices, terminal, industries, raw_counts, local


def industry_on(intervals, ticker, date):
    found = [
        r
        for r in intervals.get(ticker, [])
        if (r.get("start") is None or r["start"] <= date) and (r.get("end") is None or date < r["end"])
    ]
    return found[0].get("research_industry_id") if len(found) == 1 else None


def features_at(matrices, signal_i, members, industries, *, conditional_exclusions=frozenset()):
    """Read only <=signal_i. Reindex first, never turn a missing session into a shorter window."""
    reasons, output = Counter(), []
    if signal_i < 252:
        return [], Counter({"INSUFFICIENT_CALENDAR_LOOKBACK": len(members)})
    signal = str(matrices["close"].index[signal_i].date())
    for row in members:
        ticker = row["ticker"]
        if ticker in conditional_exclusions:
            reasons["EX_POST_CONDITIONAL_SAMPLE_EXCLUSION"] += 1
            continue
        if re.search(r"우(?:[A-Z0-9]*)?$", row.get("name", "")):
            reasons["PREFERRED_NAME_HEURISTIC"] += 1
            continue
        if ticker not in matrices["close"]:
            reasons["NO_PRICE_PANEL"] += 1
            continue
        window = {
            k: matrices[k][ticker].iloc[signal_i - 252 : signal_i + 1].to_numpy(dtype=float)
            for k in ("open", "close", "volume", "listedShares")
        }
        if any(not np.isfinite(v).all() or (v <= 0).any() for v in window.values()):
            reasons["MISSING_OR_UNTRADED_REQUIRED_KRX_SESSION"] += 1
            continue
        c, o, v, s = (window[k] for k in ("close", "open", "volume", "listedShares"))
        if (np.abs(c[1:] / c[:-1] - 1) > 0.32).any() or (np.abs(s[1:] / s[:-1] - 1) > 0.10).any():
            reasons["CORPORATE_ACTION_AMBIGUITY_IN_PAST_WINDOW"] += 1
            continue
        median = float(np.median((c * v)[-60:]))
        if median < 1e9:
            reasons["LOW_MEDIAN60_PROXY_LIQUIDITY"] += 1
            continue
        sector = industry_on(industries, ticker, signal)
        if not sector:
            reasons["UNCLASSIFIED_RECONSTRUCTED_INDUSTRY"] += 1
            continue
        mom = float(c[-22] / c[0] - 1)  # signal-21 / signal-252
        intraday = float(np.log(c[-126:] / o[-126:]).sum())
        total126 = float(np.log(c[-1] / c[-127]))
        output.append(
            {
                "ticker": ticker,
                "industry": sector,
                "momentum": mom,
                "intraday": intraday,
                "overnight": total126 - intraday,
                "median60": median,
                "marketCap": float(row["marketCap"]),
                "rank": int(row["rank"]),
            }
        )
    return output, reasons


def select(features, book):
    if book == "ETF" or not features:
        return []
    ranked = sorted(features, key=lambda r: (-r["momentum"], r["ticker"]))
    pool = [r for r in ranked[: int(np.ceil(len(ranked) / 3))] if r["momentum"] > 0]
    key = "momentum" if book == "MOMENTUM" else "overnight" if book == "OVERNIGHT" else "intraday"
    ordered = sorted(pool, key=lambda r: (-r[key], r["ticker"]))
    sectors, selected = Counter(), []
    for row in ordered:
        if sectors[row["industry"]] < 2:
            selected.append(row)
            sectors[row["industry"]] += 1
        if len(selected) == 5:
            break
    return selected


def tax_bps(date):
    # Same dated KOSPI combined sell-tax schedule as benchmark_alpha.py; no import.
    schedule = [
        ("1900-01-01", 30),
        ("2019-06-03", 25),
        ("2021-01-01", 23),
        ("2023-01-01", 20),
        ("2024-01-01", 18),
        ("2025-01-01", 15),
        ("2026-01-01", 20),
    ]
    return next(rate for start, rate in reversed(schedule) if date >= start)


def cost(date, *, stock, sell, multiplier=1):
    return multiplier * (11.5 + (tax_bps(date) if stock and sell else 0)) / 10000


def path_for(m, ticker, entry_i, end_i, terminal):
    """Selection already happened. An unresolved selected path blocks; never replace it."""
    days = m["close"].index[entry_i : end_i + 1]
    if ticker in KNOWN_BASIS_BLOCK:
        return None, "KNOWN_UNRESOLVED_PRICE_BASIS"
    if ticker in terminal and str(days[-1].date()) > terminal[ticker]:
        return None, "UNRESOLVED_TERMINAL_CONSIDERATION"
    if ticker not in m["adjusted"]:
        return None, "MISSING_OUTCOME_PANEL"
    p = m["adjusted"][ticker].iloc[entry_i : end_i + 1].to_numpy(dtype=float)
    volume = m["volume"][ticker].iloc[entry_i : end_i + 1].to_numpy(dtype=float)
    if len(p) != len(days) or not np.isfinite(p).all() or (p <= 0).any():
        return None, "MISSING_OUTCOME_KRX_SESSION"
    if not np.isfinite(volume).all() or (volume <= 0).any():
        return None, "SUSPENDED_OR_UNTRADED_VALUATION_SESSION"
    return p / p[0], None


def block_path(
    m, selected, book, entry_i, end_i, terminal, *, multiplier=1, nav_krw=50e6, charge_entry=True, charge_exit=True
):
    days = m["close"].index[entry_i : end_i + 1]
    entry, end = str(days[0].date()), str(days[-1].date())
    sleeve = 0.5 if book == "HALF_INTRADAY_HALF_ETF" else 1.0
    weight = 0.2 * sleeve
    total = np.zeros(len(days))
    costs = {"entryFraction": 0.0, "exitFraction": 0.0, "grossTurnover": 0.0}
    failures = []
    for row in selected:
        ticker = row["ticker"]
        p, reason = path_for(m, ticker, entry_i, end_i, terminal)
        if reason:
            failures.append({"ticker": ticker, "reason": reason})
            continue
        buy, sell = (
            cost(entry, stock=True, sell=False, multiplier=multiplier),
            cost(end, stock=True, sell=True, multiplier=multiplier),
        )
        asset = weight / (1 + buy)
        entry_order, exit_order = nav_krw * asset, nav_krw * asset * p[-1]
        # Signal-time floor and realized capacity use as-traded prices/volume, never adjusted prices.
        exit_tv = (m["close"][ticker] * m["volume"][ticker]).iloc[max(0, end_i - 59) : end_i + 1]
        if entry_order > 0.01 * row["median60"] or exit_tv.isna().any() or exit_order > 0.01 * float(exit_tv.median()):
            failures.append({"ticker": ticker, "reason": "REALIZED_CAPACITY_EXCEEDED"})
            continue
        total += asset * p
        total[-1] -= asset * p[-1] * sell
        costs["entryFraction"] += weight - asset
        costs["exitFraction"] += asset * p[-1] * sell
        costs["grossTurnover"] += asset * (1 + p[-1])
    fallback = 1 - weight * len(selected)
    p = m["benchmark"].iloc[entry_i : end_i + 1].to_numpy(dtype=float)
    if not np.isfinite(p).all() or (p <= 0).any():
        failures.append({"ticker": ETF, "reason": "BENCHMARK_WINDOW_GAP"})
    else:
        buy = cost(entry, stock=False, sell=False, multiplier=multiplier) if charge_entry else 0.0
        sell = cost(end, stock=False, sell=True, multiplier=multiplier) if charge_exit else 0.0
        asset = fallback / (1 + buy)
        ratios = p / p[0]
        total += asset * ratios
        total[-1] -= asset * ratios[-1] * sell
        costs["entryFraction"] += fallback - asset
        costs["exitFraction"] += asset * ratios[-1] * sell
        costs["grossTurnover"] += asset * (1 + ratios[-1])
    return (None if failures else total), failures, costs


def metrics(levels, dates):
    """Daily returns on one continuous NAV only. Initial and terminal fees included."""
    v = np.asarray(levels, dtype=float)
    if len(v) < 3 or not np.isfinite(v).all() or (v <= 0).any():
        raise ValueError("CONTIGUOUS_FINITE_NAV_REQUIRED")
    r = v[1:] / v[:-1] - 1
    yrs = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days / 365.25
    sd = np.std(r, ddof=1)
    downside = float(np.sqrt(np.mean(np.minimum(r, 0) ** 2)) * np.sqrt(252))
    threshold = np.quantile(r, 0.05)
    return {
        "totalReturn": float(v[-1] / v[0] - 1),
        "cagr": float((v[-1] / v[0]) ** (1 / yrs) - 1),
        "arithmeticAnnualReturn": float(np.mean(r) * 252),
        "sharpeZeroRf": float(np.mean(r) / sd * np.sqrt(252)) if sd > 0 else None,
        "annualVolatility": float(sd * np.sqrt(252)),
        "annualDownsideDeviation": downside,
        "mdd": float(np.min(v / np.maximum.accumulate(v) - 1)),
        "dailyCvar95": float(np.mean(r[r <= threshold])),
        "dailyObservations": len(r),
        "from": str(pd.Timestamp(dates[0]).date()),
        "through": str(pd.Timestamp(dates[-1]).date()),
    }


def paired_summary(rows, control="ETF"):
    lookup = {
        (r["analysisWindow"], r["sample"], r["horizon"], r["costMultiplier"], r["entry"], r["book"]): r for r in rows
    }
    result = []
    for window in SPEC["analysisWindows"]:
        for sample in sorted({r["sample"] for r in rows}):
            for h in SPEC["horizons"]:
                for mult in (1, 2):
                    for book in BOOKS[1:]:
                        matched = []
                        pre = [
                            r
                            for r in rows
                            if (r["analysisWindow"], r["sample"], r["horizon"], r["costMultiplier"], r["book"])
                            == (window, sample, h, mult, book)
                        ]
                        for row in pre:
                            other = lookup[(window, sample, h, mult, row["entry"], control)]
                            if row["netReturn"] is not None and other["netReturn"] is not None:
                                matched.append((row["entry"][:4], row["netReturn"] - other["netReturn"]))
                        delta = np.array([x[1] for x in matched])
                        byyear = defaultdict(list)
                        for year, value in matched:
                            byyear[year].append(value)
                        ci = None
                        if len(byyear) >= 6 and len(delta) >= 12:
                            years = sorted(byyear)
                            rng = np.random.default_rng(260624)
                            draws = [
                                np.mean([v for yr in rng.choice(years, len(years), replace=True) for v in byyear[yr]])
                                for _ in range(2000)
                            ]
                            ci = list(map(float, np.quantile(draws, [0.025, 0.975])))
                        result.append(
                            {
                                "analysisWindow": window,
                                "sample": sample,
                                "horizon": h,
                                "costMultiplier": mult,
                                "book": book,
                                "control": control,
                                "scheduledBlocks": len(pre),
                                "validPairs": len(delta),
                                "years": len(byyear),
                                "meanBlockExcess": float(delta.mean()) if len(delta) else None,
                                "descriptiveYearBootstrap95": ci,
                                "evidence": "EXPLORATORY_DESCRIPTIVE",
                            }
                        )
    return result


def execute(output):
    source, universe, m, terminal, industries, raw_counts, local = load_inputs()
    days = m["close"].index
    first = days.get_loc(pd.Timestamp(SPEC["firstEntry"]))
    rows, trajectories, coverage, features_log = [], [], [], []
    excluded = frozenset(terminal) | KNOWN_BASIS_BLOCK
    embargo = days[days > pd.Timestamp(SPEC["developmentEnd"])][21]
    for sample in SPEC["samples"]:
        exclusions = excluded if sample == SPEC["samples"][1] else frozenset()
        for h in SPEC["horizons"]:
            for window in SPEC["analysisWindows"]:
                schedule = list(range(first, len(days) - h, h))
                if window == "DEVELOPMENT_THROUGH_2019":
                    schedule = [i for i in schedule if str(days[i + h].date()) <= SPEC["developmentEnd"]]
                elif window == "EVALUATION_2020_AFTER_EMBARGO":
                    schedule = [i for i in schedule if days[i] > embargo]
                if not schedule:
                    continue
                first_in_window = schedule[0]
                paths = {(mult, book): [1.0] for mult in (1, 2) for book in BOOKS}
                path_dates = [days[first_in_window]]
                alive = {(mult, book): True for mult in (1, 2) for book in BOOKS}
                for entry_i in schedule:
                    signal_i, end_i = entry_i - 1, entry_i + h
                    signal, entry, end = map(lambda x: str(days[x].date()), (signal_i, entry_i, end_i))
                    snap = universe.loc[universe.date < signal, "date"].max()
                    members = universe.loc[(universe.date == snap) & (universe["rank"] <= 120)].to_dict("records")
                    features, reasons = features_at(m, signal_i, members, industries, conditional_exclusions=exclusions)
                    split = (
                        "DEVELOPMENT"
                        if end <= SPEC["developmentEnd"]
                        else "EVALUATION"
                        if days[entry_i] > embargo
                        else "PURGED_SPLIT_BOUNDARY"
                    )
                    coverage.append(
                        {
                            "analysisWindow": window,
                            "sample": sample,
                            "horizon": h,
                            "signal": signal,
                            "snapshot": snap,
                            "members": len(members),
                            "measurable": len(features),
                            "reasons": dict(reasons),
                            "split": split,
                        }
                    )
                    for feature in features:
                        features_log.append(
                            {
                                "analysisWindow": window,
                                "sample": sample,
                                "horizon": h,
                                "signal": signal,
                                "snapshot": snap,
                                **feature,
                            }
                        )
                    for mult in (1, 2):
                        for book in BOOKS:
                            selected = select(features, book)
                            key = mult, book
                            # After a broken NAV, calculate fixed-initial-capital standalone diagnostics,
                            # explicitly refusing a full compounded path and its later capacity claim.
                            nav = paths[key][-1] * 50e6 if alive[key] else 50e6
                            block, failures, costs = block_path(
                                m,
                                selected,
                                book,
                                entry_i,
                                end_i,
                                terminal,
                                multiplier=mult,
                                nav_krw=nav,
                                charge_entry=book != "ETF" or entry_i == first_in_window,
                                charge_exit=book != "ETF" or entry_i == schedule[-1],
                            )
                            row = {
                                "analysisWindow": window,
                                "sample": sample,
                                "horizon": h,
                                "costMultiplier": mult,
                                "book": book,
                                "signal": signal,
                                "entry": entry,
                                "exit": end,
                                "split": split,
                                "selected": [r["ticker"] for r in selected],
                                "industryCounts": dict(Counter(r["industry"] for r in selected)),
                                "stockWeight": len(selected) * (0.1 if book == BOOKS[-1] else 0.2),
                                "navBasis": "COMPOUNDED" if alive[key] else "STANDALONE_AFTER_UNRESOLVED_NAV",
                                "netReturn": float(block[-1] - 1) if block is not None else None,
                                "failures": failures,
                                **costs,
                            }
                            rows.append(row)
                            if block is None:
                                alive[key] = False
                            elif alive[key]:
                                # Entry fees at same anchor close merge with the previous block's exit.
                                # Initial fee is bundled into first actual daily return; no zero-time observation.
                                base = paths[key][-1]
                                if entry_i == first_in_window:
                                    paths[key].extend((base * block[1:]).tolist())
                                else:
                                    paths[key][-1] = base * block[0]
                                    paths[key].extend((base * block[1:]).tolist())
                    if entry_i == first_in_window:
                        path_dates.extend(days[entry_i + 1 : end_i + 1])
                    else:
                        path_dates.extend(days[entry_i + 1 : end_i + 1])
                for (mult, book), path in paths.items():
                    trajectories.append(
                        {
                            "analysisWindow": window,
                            "sample": sample,
                            "horizon": h,
                            "costMultiplier": mult,
                            "book": book,
                            "complete": alive[mult, book],
                            "metrics": metrics(path, path_dates) if alive[mult, book] else None,
                        }
                    )
                    if alive[mult, book]:
                        pd.DataFrame({"date": path_dates, "nav": path}).to_csv(
                            output / f"nav-{window}-{sample}-{h}-{mult}-{book}.csv", index=False, float_format="%.12g"
                        )
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_json(output / "blocks.json", orient="records", indent=2)
    pd.DataFrame(features_log).to_csv(output / "signal-features.csv", index=False, float_format="%.12g")
    pd.DataFrame(coverage).to_json(output / "coverage.json", orient="records", indent=2)
    summary = {
        "study": SPEC["study"],
        "evidenceClass": SPEC["evidenceClass"],
        "verdict": "NO_PROMOTION_EXPLORATORY_ONLY",
        "portfolios": trajectories,
        "pairedComparisons": paired_summary(rows),
        "intradayVsMomentum": paired_summary(rows, "MOMENTUM"),
        "rawCoverageByYear": raw_counts,
        "universeEverTop120": int(universe.loc[universe["rank"] <= 120, "ticker"].nunique()),
        "conditionalExcluded": sorted(excluded),
        "conditionalExclusionUsesFutureIdentity": True,
        "sourceHashes": source.identities,
        "localSourceHashes": local,
        "dataCommit": source.commit,
        "specSha256": digest((HERE / "spec.json").read_bytes()),
        "codeSha256": digest(Path(__file__).read_bytes()),
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "exchangeCalendars": xc.__version__,
        },
        "limitations": [
            "Stock partial distributions versus gross ETF distributions; not symmetric complete total return.",
            "Ex-post continuing sample has survivorship bias; no live recommendation.",
            "Reconstructed industry and historical input revision availability not fully certified PIT.",
            "No unresolved payoff assumed. Strict broken paths have no full-period Sharpe/CAGR.",
            "No training or tuning; chronological partitions are exposed development history.",
            "Standalone blocks after an unresolved NAV are diagnostics, not a financed investment path.",
        ],
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {"output": str(output), "blocks": len(rows), "completePaths": sum(p["complete"] for p in trajectories)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results")
    args = parser.parse_args()
    resolved = args.output.resolve()
    if resolved == ROOT or (resolved.is_relative_to(ROOT) and not resolved.is_relative_to(HERE / "results")):
        raise ValueError("OUTPUT_MUST_BE_NEW_STUDY_RESULTS_OR_EXTERNAL_DIRECTORY")
    resolved.mkdir(parents=True, exist_ok=True)
    execute(resolved)
