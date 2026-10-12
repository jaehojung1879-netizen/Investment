"""US alpha research Phase 3 readiness: can the proposed first hypothesis (cash-based operating profitability, sector- and
size-neutral, incremental to momentum, volatility and accounting profitability) be measured point-in-time on a broad enough
S&P 500 cross-section? Outcome-blind: no forward price, return, label, NAV or model output is read.

    python scripts/audit_us_alpha_phase3_readiness.py --workspace <dir> [--extract] [--limit-dates N]

`--extract` copies `ledger/fundamentals/us/*.jsonl.gz` from the pinned signal-history commit into the workspace (git blob ids
are re-verified on every read). Sampling repeats Phase 2's fixed rule exactly: every 13th weekly signal date from 2013-01-04.

What is measured, per sampled member-date that passes Phase 2's price and identity gates:
* availability and reason codes of `cashOperatingProfitability` and `accrualsToAssets` (`pipeline/us_cash_profitability.py`);
* availability of the baseline controls the primary test residualises on (sector, size proxy, momentum, volatility, ROE);
* names per date with the feature AND every control, outside Financials and Real Estate, against registration floors;
* two independent size proxies and their agreement (shares x as-traded close; 63-session median traded value);
* ordering overlap with existing features (mean within-date Spearman) and the share of the feature's cross-sectional rank
  variance that sector alone explains. Overlap says two features order companies alike; it says nothing about prediction.
* whether names missing the feature differ on price characteristics (missingness bias).
The power section re-reads only the variance side of an already-committed report (`pipeline/us_alpha_phase3_power.py`).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import us_alpha_phase3_power as POWER                # noqa: E402
from pipeline import us_capital_allocation_coverage as C           # noqa: E402
from pipeline import us_cash_profitability as CP                   # noqa: E402
from pipeline import us_dual_benchmark_data as D                   # noqa: E402
from pipeline import us_multifactor_inputs as M                    # noqa: E402


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


A = _load("coverage_audit", "scripts/audit_us_capital_allocation_coverage.py")
OV = _load("overlap_audit", "scripts/audit_us_capital_allocation_overlap.py")
DX = _load("selection_diag", "scripts/audit_us_capital_allocation_selection_diagnostics.py")
MF = _load("multifactor_audit", "scripts/audit_us_multifactor_pit_readiness.py")

OUT = ROOT / "docs/us-readiness/us-alpha-phase3-readiness-v1.json"
SAMPLE_EVERY_WEEKS = MF.SAMPLE_EVERY_WEEKS
EXCLUDED_SECTORS = ("Financials", "Real Estate")
FLOORS = (100, 150, 200)
ADV_SESSIONS = 63
MIN_NAMES = 30
FEATURES = ("cashOperatingProfitability", "accrualsToAssets")
CONTROLS = ("logTradedValue63", "mom121", "vol252", "operatingProfitabilityToAssets")
SENSITIVITY_SIZE = "logMarketCapProxy"     # share-count basis unverified; reported as a sensitivity, never the primary control
OVERLAP_WITH = ("operatingProfitabilityToAssets", "roe", "operatingMargin", "profitMargin", "debtToEquity", "earningsGrowth", "mom121", "vol252", "beta252",
                "logMarketCapProxy", "logTradedValue63", "earningsYield", "bookYield", "fcfYield")
PRICE_FAILURES = MF.PRICE_FAILURES


def raw_records(workspace: Path, commit: str) -> dict:
    """Raw Finnhub filings by ticker, blob ids verified against the extraction manifest."""
    declared = json.loads((workspace / "source-manifest.json").read_text())
    if declared["commit"] != commit:
        raise ValueError("SOURCE_COMMIT_MISMATCH")
    expected = {Path(f["path"]).name: f["gitBlob"] for f in declared["files"]}
    grouped = defaultdict(list)
    for path in sorted(workspace.glob("finnhub-*.jsonl.gz")):
        blob = path.read_bytes()
        if hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest() != expected[path.name]:
            raise ValueError("SOURCE_BLOB_MISMATCH: " + path.name)
        for line in gzip.decompress(blob).decode("utf-8").split("\n"):
            if line.strip():
                record = json.loads(line)
                grouped[record["ticker"]].append(record)
    return grouped


def traded_value_median(as_traded, volume, pos, split_positions):
    """Median as-traded dollar volume over the 63 sessions ending at `pos`; withheld when a split falls inside the window."""
    start = pos - ADV_SESSIONS + 1
    if start < 0 or any(start < p <= pos for p in split_positions):
        return None
    window = as_traded[start:pos + 1] * volume[start:pos + 1]
    window = window[np.isfinite(window) & (window > 0)]
    return float(np.median(window)) if len(window) >= ADV_SESSIONS // 2 else None


def row_values(panel, store, raw, events, cache, member, date, bench):
    values = OV.existing_features(panel, store, member.ticker, date, bench)
    if values is None:
        return None
    h = panel.get(member.ticker)
    pos = h.position(np.datetime64(date, "ns"))
    if member.ticker not in cache:
        ev = events.get(member.ticker, [])
        traded = M.as_traded_from_total_return(h.dates, h.close, ev)
        split_pos = [int(np.searchsorted(h.dates, np.datetime64(s, "ns"), side="left")) for s in M.split_dates(ev)]
        cache[member.ticker] = (traded, split_pos, M.split_dates(ev))
    traded, split_pos, split_days = cache[member.ticker]
    price = float(traded[pos])
    cash = CP.features_as_of(raw.get(member.ticker, []), date)
    out = dict(values)
    out.update({k: cash[k] for k in FEATURES + ("operatingProfitabilityToAssets",)})
    out["_state"] = dict(cash["state"])
    out["_sharesBasis"] = cash["sharesBasis"]
    cap, cap_state = CP.market_cap_proxy(cash["sharesForProxy"], price, cash["sharesVisibleDay"], date,
                                         [str(s) for s in split_days]) if cash["sharesVisibleDay"] else (None, cash["state"]["sharesForProxy"])
    out["_state"]["logMarketCapProxy"] = cap_state
    out["logMarketCapProxy"] = float(np.log(cap)) if cap else None
    adv = traded_value_median(traded, h.volume, pos, split_pos)
    out["logTradedValue63"] = float(np.log(adv)) if adv else None
    pair = MF.FA.resolve_filing_pair(store, member.ticker, "US", date)
    if pair.current is not None:
        y = M.value_yields(pair.current.fields, price, pair.current.available_from, date, split_days)
        out.update({k: y[k] for k in M.NUMERATORS})
    return out


def finite(x):
    return x is not None and isinstance(x, (int, float)) and np.isfinite(x)


def pct(n, d):
    return round(100.0 * n / d, 3) if d else None


def mean_spearman(frame, a, b):
    rhos = []
    for _, g in frame.groupby("date"):
        pair = g[[a, b]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(pair) >= MIN_NAMES and pair[a].nunique() > 2 and pair[b].nunique() > 2:
            rhos.append(float(pair[a].rank().corr(pair[b].rank())))
    if not rhos:
        return None
    return {"meanRho": round(float(np.mean(rhos)), 3), "p10": round(float(np.quantile(rhos, .1)), 3),
            "p90": round(float(np.quantile(rhos, .9)), 3), "dates": len(rhos)}


def sector_share_of_rank_variance(frame, feature):
    """Mean over dates of between-sector variance / total variance of the feature's within-date percentile rank."""
    shares = []
    for _, g in frame.groupby("date"):
        g = g[["sector", feature]].dropna()
        if len(g) < MIN_NAMES:
            continue
        r = g[feature].rank(pct=True)
        total = float(r.var(ddof=0))
        if total <= 0:
            continue
        between = float(r.groupby(g["sector"]).transform("mean").var(ddof=0))
        shares.append(between / total)
    return {"meanShare": round(float(np.mean(shares)), 3), "dates": len(shares)} if shares else None


def summarise(rows, sampled, universe_status):
    frame = pd.DataFrame(rows)
    frame["year"] = frame["date"].str[:4]
    nonfin = frame[~frame["sector"].isin(EXCLUDED_SECTORS) & (frame["sector"] != "UNCLASSIFIED")]
    for name in FEATURES + CONTROLS + (SENSITIVITY_SIZE,):
        frame["ok_" + name] = frame[name].map(finite)
        nonfin = nonfin.assign(**{"ok_" + name: nonfin[name].map(finite)})
    nonfin = nonfin.assign(primaryComplete=np.all([nonfin["ok_" + n] for n in ("cashOperatingProfitability",) + CONTROLS], axis=0))
    sensitivity = np.all([nonfin["ok_" + n] for n in ("cashOperatingProfitability", SENSITIVITY_SIZE) + CONTROLS[1:]], axis=0)

    reasons = {f: dict(Counter(s[f] for s in nonfin["_state"]).most_common())
               for f in FEATURES + ("operatingProfitabilityToAssets", "logMarketCapProxy")}
    reasons["sharesBasisWhereMarketCapProxyAvailable"] = dict(Counter(nonfin.loc[nonfin["ok_logMarketCapProxy"], "_sharesBasis"]).most_common())
    by_year = {}
    for year, g in nonfin.groupby("year"):
        per_date = g.groupby("date")["primaryComplete"].sum()
        by_year[year] = {"eligibleNonFinancialMemberDates": int(len(g)),
                         **{f + "Pct": pct(int(g["ok_" + f].sum()), len(g)) for f in FEATURES + CONTROLS + (SENSITIVITY_SIZE,)},
                         "primaryCompletePct": pct(int(g["primaryComplete"].sum()), len(g)),
                         "namesPerDatePrimaryComplete": {"min": int(per_date.min()), "median": float(per_date.median()),
                                                         "max": int(per_date.max())}}
    per_date = nonfin.groupby("date")["primaryComplete"].sum()
    floors = {str(f): {"datesBelow": int((per_date < f).sum()), "of": int(len(per_date)),
                       "firstDateAtOrAbove": next((d for d, n in per_date.items() if n >= f), None)} for f in FLOORS}
    overall = {"eligibleMemberDatesAllSectors": int(len(frame)), "eligibleNonFinancialMemberDates": int(len(nonfin)),
               "excludedFinancialAndRealEstateShare": pct(int(frame["sector"].isin(EXCLUDED_SECTORS).sum()), len(frame)),
               **{f + "Pct": pct(int(nonfin["ok_" + f].sum()), len(nonfin)) for f in FEATURES + CONTROLS + (SENSITIVITY_SIZE,)},
               "primaryCompletePct": pct(int(nonfin["primaryComplete"].sum()), len(nonfin)),
               "sensitivityCompleteWithMarketCapProxyPct": pct(int(sensitivity.sum()), len(nonfin)),
               "namesPerDateSensitivityComplete": {"median": float(pd.Series(sensitivity, index=nonfin.index).groupby(nonfin["date"]).sum().median())},
               "namesPerDatePrimaryComplete": {"median": float(per_date.median()), "p10": float(per_date.quantile(.1)),
                                               "min": int(per_date.min()), "max": int(per_date.max())},
               "companiesEverPrimaryComplete": int(nonfin.loc[nonfin["primaryComplete"], "ticker"].nunique())}
    since = per_date[per_date.index >= "2016-01-01"]
    overall["namesPerDatePrimaryCompleteFrom2016"] = ({"median": float(since.median()), "min": int(since.min()),
                                                       "p10": float(since.quantile(.1))} if len(since) else None)
    overlap = {f: {o: mean_spearman(nonfin, f, o) for o in OVERLAP_WITH} for f in FEATURES}
    overlap["cashOperatingProfitability"]["accrualsToAssets"] = mean_spearman(nonfin, "cashOperatingProfitability", "accrualsToAssets")
    size_agreement = mean_spearman(nonfin, "logMarketCapProxy", "logTradedValue63")
    sector_share = {f: sector_share_of_rank_variance(nonfin, f)
                    for f in FEATURES + ("operatingProfitabilityToAssets", "roe", "mom121", "vol252")}
    ranks = nonfin.groupby("date")[["mom121", "vol252", "logTradedValue63"]].rank(pct=True)
    bias = {}
    for name in ("mom121", "vol252", "logTradedValue63"):
        have = ranks.loc[nonfin["ok_cashOperatingProfitability"], name].dropna()
        lack = ranks.loc[~nonfin["ok_cashOperatingProfitability"], name].dropna()
        bias[name] = {"meanPercentileWithFeature": round(float(have.mean()), 4) if len(have) else None,
                      "meanPercentileWithoutFeature": round(float(lack.mean()), 4) if len(lack) else None,
                      "nWith": int(len(have)), "nWithout": int(len(lack))}
    sectors = {s: {"shareOfEligible": pct(int((nonfin["sector"] == s).sum()), len(nonfin)),
                   "shareOfPrimaryComplete": pct(int(((nonfin["sector"] == s) & nonfin["primaryComplete"]).sum()),
                                                 int(nonfin["primaryComplete"].sum()))}
               for s in sorted(nonfin["sector"].unique())}
    return {
        "sampling": {"rule": "every %dth weekly signal date from %s (Phase 2's fixed rule)" % (SAMPLE_EVERY_WEEKS, sampled[0]),
                     "dates": len(sampled), "firstDate": sampled[0], "lastDate": sampled[-1],
                     "memberDatesSeen": sum(universe_status.values()), "statusCounts": dict(sorted(universe_status.items()))},
        "overall": overall, "byYear": by_year, "namesPerDateFloors": floors, "missingReasons": reasons,
        "orderingOverlapMeanSpearman": overlap, "sizeProxyAgreement": size_agreement,
        "sectorShareOfRankVariance": sector_share, "missingnessBias": bias, "sectorRepresentation": sectors,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--limit-dates", type=int)
    args = parser.parse_args(argv)
    if args.extract:
        A.extract(args.workspace, A.FUNDAMENTALS_COMMIT)
    ctx, membership, dates = DX.build_context(args.workspace)
    sampled = dates[::SAMPLE_EVERY_WEEKS]
    if args.limit_dates:
        sampled = sampled[::max(1, len(sampled) // args.limit_dates)][:args.limit_dates]
    raw = raw_records(args.workspace, A.FUNDAMENTALS_COMMIT)
    panel, store, identity = OV.load_sealed()
    reader = D.SealedReader(ROOT)
    events = MF.load_events(reader, reader.manifest())
    bench = panel.get("SPY")
    cache, rows, universe_status = {}, [], Counter()
    for date in sampled:
        snapshot = membership.on(date)
        for raw_symbol in snapshot["members"]:
            member = C.classify_member(ctx, snapshot, date, raw_symbol)
            universe_status[member.status] += 1
            if member.status in PRICE_FAILURES:
                continue
            v = row_values(panel, store, raw, events, cache, member, date, bench)
            if v is None:
                continue
            rows.append({"date": date, "ticker": member.ticker, "sector": member.sector, "_state": v["_state"],
                         "_sharesBasis": v["_sharesBasis"],
                         **{k: v.get(k) for k in set(FEATURES + CONTROLS + OVERLAP_WITH)}})
    report = {
        "id": "us-alpha-phase3-readiness-v1", "evidenceClass": "OUTCOME_BLIND_SOURCE_AND_DESIGN_READINESS",
        "readsReturns": False, "readsLabels": False, "fitsModels": False, "forwardPricesRead": False,
        "featureContract": CP.CONTRACT, "featureStatus": "CANDIDATE_NOT_REGISTERED",
        "inputs": {"fundamentalsCommit": A.FUNDAMENTALS_COMMIT, "replayIdentity": identity,
                   "membership": str(A.MEMBERSHIP.relative_to(ROOT)), "sectors": str(A.SECTORS.relative_to(ROOT))},
        "eligibleCrossSection": {"priceAndIdentity": "Phase 2 funnel (C.classify_member): price panel, history, identity",
                                 "excludedSectors": list(EXCLUDED_SECTORS),
                                 "why": "operating cash flow and total assets do not measure operating profitability for banks, insurers and REITs"},
        "primaryCompleteDefinition": ["cashOperatingProfitability"] + list(CONTROLS) + ["sector label"],
        "sensitivitySizeControl": SENSITIVITY_SIZE,
        **summarise(rows, sampled, universe_status),
        "powerPlanning": POWER.planning_table(),
        "notMeasuredHere": ["any relation between a feature and a later return", "period-end share counts (SEC blocked)",
                            "departed names without a price panel (212 identities; survivor-conditioned sample)"],
    }
    if args.limit_dates:
        print(json.dumps({k: report[k] for k in ("sampling", "overall", "namesPerDateFloors", "missingReasons")}, indent=1))
        return 0
    OUT.write_text(json.dumps(report, indent=1, sort_keys=True, allow_nan=False, ensure_ascii=False,
                              default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n", encoding="utf-8")
    print("wrote", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
