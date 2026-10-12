"""US multifactor PIT readiness: which value, quality, momentum, cash-flow, risk and distribution variables can be joined into one
weekly S&P 500 cross-section, and how much they overlap. Outcome-blind: no forward return, label, NAV or model fit is read.

    python scripts/audit_us_multifactor_pit_readiness.py --workspace <dir>

Sampling is fixed in advance: every 13th weekly signal date (one per quarter). For each sampled date and each PIT S&P 500 member
the audit records which feature families are AVAILABLE (a usable, point-in-time value exists), then the pairwise cross-sectional
rank correlation of representative features. A high correlation says two features order companies alike; it says nothing about
whether either predicts anything.

What is separated explicitly:
* PIT_EXACT: values reproduced from filings visible before the signal date (sealed fundamentals, #220 engine) and prices up to it;
* RECONSTRUCTED: values this audit rebuilds from sealed evidence (as-traded price from the total-return index and sealed events);
* SNAPSHOT_ONLY / ABSENT: values with no historical vintage in the repository (market capitalisation, trailing/forward P/E,
  consensus estimates). They are listed, not used.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import fundamental_acceleration as FA               # noqa: E402
from pipeline import regional_alpha_features as RAF               # noqa: E402
from pipeline import us_capital_allocation_coverage as C          # noqa: E402
from pipeline import us_capital_allocation_policy as POL          # noqa: E402
from pipeline import us_dual_benchmark_data as D                  # noqa: E402
from pipeline import us_multifactor_inputs as M                   # noqa: E402


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


OV = _load("overlap_audit", "scripts/audit_us_capital_allocation_overlap.py")
DX = _load("selection_diag", "scripts/audit_us_capital_allocation_selection_diagnostics.py")

OUT = ROOT / "docs/us-readiness/us-multifactor-pit-readiness-v1.json"
SAMPLE_EVERY_WEEKS = 13
MIN_NAMES = 30
FLAG = 0.70
FAMILIES = ("priceMomentum", "priceRisk", "leadershipBreadth", "qualityComplete", "accelerationComplete", "cashFlow",
            "valueEarnings", "valueBook", "valueFcf", "valueAny", "distributionCore4", "dilution")
COMBINATIONS = {
    "existingModelInputs": ("priceMomentum", "priceRisk", "qualityComplete"),
    "plusCashFlow": ("priceMomentum", "priceRisk", "qualityComplete", "cashFlow"),
    "plusValue": ("priceMomentum", "priceRisk", "qualityComplete", "cashFlow", "valueAny"),
    "plusDistribution": ("priceMomentum", "priceRisk", "qualityComplete", "cashFlow", "valueAny", "distributionCore4"),
}
REDUNDANCY_FEATURES = ("mom121", "relative126", "high52Distance", "vol252", "maxDD252", "beta252", "relativeStrengthBreadth52w",
                       "roe", "operatingMargin", "debtToEquity", "earningsGrowth", "delta_roe", "earningsYield", "bookYield", "fcfYield",
                       "fcfConversion", "incrementalDistributionOverOCF", "distributionToOCF", "totalCashDistributionChangeYoY")
FAMILY_OF = {"mom121": "momentum", "relative126": "momentum", "high52Distance": "momentum", "vol252": "risk", "maxDD252": "risk",
             "beta252": "risk", "relativeStrengthBreadth52w": "leadership", "roe": "quality", "operatingMargin": "quality",
             "debtToEquity": "quality", "earningsGrowth": "quality", "delta_roe": "acceleration", "earningsYield": "value",
             "bookYield": "value", "fcfYield": "value", "fcfConversion": "cashFlow", "incrementalDistributionOverOCF": "distribution",
             "distributionToOCF": "distribution", "totalCashDistributionChangeYoY": "distribution"}
PRICE_FAILURES = (C.NO_PRICE_PANEL, C.PRICE_HISTORY_INSUFFICIENT, C.PRICE_STALE, C.IDENTITY_AMBIGUOUS)


def load_events(reader, manifest):
    events = defaultdict(list)
    for name in sorted(manifest["components"]):
        if name.startswith("corporate-events/20"):
            for ref in manifest["components"][name]:
                for row in reader.component(ref):
                    if not row["ticker"].endswith((".KS", ".KQ")):
                        events[row["ticker"]].append((row["date"], float(row.get("dividend") or 0.0), float(row.get("split") or 1.0)))
    return events


def store_inventory(store):
    fields, statuses = Counter(), Counter()
    total = 0
    for ticker in store.tickers():
        if ticker.endswith((".KS", ".KQ")):
            continue
        for record in store._records[ticker]:
            total += 1
            statuses[record.pit_status] += 1
            for key, value in record.fields.items():
                fields[key] += value is not None
    return {"usRecords": total, "pitStatus": dict(statuses), "nonNullByField": dict(sorted(fields.items()))}


def available(value):
    return value is not None and np.isfinite(value)


def row_features(panel, store, events_cache, events, member, date, bench, snapshot_row):
    """Feature values (or None) for one eligible member-date. Pure function of data visible on `date`."""
    values = OV.existing_features(panel, store, member.ticker, date, bench)
    out = {"_hasPriceHistory": values is not None}
    if values is None:
        return out
    out.update(values)
    pair = FA.resolve_filing_pair(store, member.ticker, "US", date)
    current = pair.current
    h = panel.get(member.ticker)
    pos = h.position(np.datetime64(date, "ns"))
    if member.ticker not in events_cache:
        events_cache[member.ticker] = M.as_traded_from_total_return(h.dates, h.close, events.get(member.ticker, []))
    price = float(events_cache[member.ticker][pos])
    if current is not None:
        y = M.value_yields(current.fields, price, current.available_from, date, M.split_dates(events.get(member.ticker, [])))
        out.update({k: y[k] for k in M.NUMERATORS})
        out["_valueState"] = y["state"]
    if snapshot_row is not None:
        f = snapshot_row.features
        ocf, capex = f["operatingCashFlowTTM"].value, f["capitalExpendituresTTM"].value
        out["_ocf"], out["_capex"] = ocf, capex
        out["fcfConversion"] = (ocf - capex) / ocf if ocf and ocf > 0 and capex is not None else None
        if member.status == C.JOINT_MEASURED:
            g, ratio = f["totalCashDistributionChangeYoY"].value, f["distributionToOCF"].value
            out["totalCashDistributionChangeYoY"], out["distributionToOCF"] = g, ratio
            out["incrementalDistributionOverOCF"] = POL.incremental_over_ocf(ratio, g) if g > -1 else None
    return out


def family_flags(v, member):
    cur = lambda *names: all(available(v.get(n)) for n in names)      # noqa: E731
    flags = {
        "priceMomentum": cur("mom121", "relative126", "high52Distance"),
        "priceRisk": cur("vol252", "maxDD252", "beta252"),
        "leadershipBreadth": available(v.get("relativeStrengthBreadth52w")),
        "qualityComplete": cur(*RAF.FUNDAMENTAL),
        "accelerationComplete": cur(*[f"delta_{x}" for x in FA.PRIMARY_FIELDS]),
        "cashFlow": available(v.get("_ocf")) and v["_ocf"] > 0 and available(v.get("_capex")),
        "valueEarnings": available(v.get("earningsYield")), "valueBook": available(v.get("bookYield")), "valueFcf": available(v.get("fcfYield")),
        "distributionCore4": member.status == C.JOINT_MEASURED,
        "dilution": False,
    }
    flags["valueAny"] = flags["valueEarnings"] or flags["valueBook"] or flags["valueFcf"]
    return flags


def spearman_mean(frame, names):
    matrix = {a: {} for a in names}
    for a in names:
        for b in names:
            if a >= b:
                continue
            rhos = []
            for _, g in frame.groupby("date"):
                pair = g[[a, b]].replace([np.inf, -np.inf], np.nan).dropna()
                if len(pair) >= MIN_NAMES and pair[a].nunique() > 2 and pair[b].nunique() > 2:
                    rhos.append(float(pair[a].rank().corr(pair[b].rank())))
            if rhos:
                matrix[a][b] = {"meanRho": round(float(np.mean(rhos)), 3), "dates": len(rhos)}
    return matrix


def pct(n, d):
    return round(100.0 * n / d, 3) if d else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--limit-dates", type=int)
    args = parser.parse_args(argv)
    ctx, membership, dates = DX.build_context(args.workspace)
    sampled = dates[::SAMPLE_EVERY_WEEKS]
    if args.limit_dates:
        sampled = sampled[:args.limit_dates]
    panel, store, identity = OV.load_sealed()
    reader = D.SealedReader(ROOT)
    events = load_events(reader, reader.manifest())
    bench = panel.get("SPY")
    cache = {}
    rows, by_year = [], defaultdict(lambda: Counter())
    universe_status = Counter()
    for date in sampled:
        snapshot = membership.on(date)
        for raw in snapshot["members"]:
            member = C.classify_member(ctx, snapshot, date, raw)
            universe_status[member.status] += 1
            if member.status in PRICE_FAILURES:
                continue
            v = row_features(panel, store, cache, events, member, date, bench, member.snapshot)
            if not v.get("_hasPriceHistory"):
                continue
            flags = family_flags(v, member)
            year = date[:4]
            by_year[year]["eligible"] += 1
            for name, flag in flags.items():
                by_year[year][name] += bool(flag)
            for combo, parts in COMBINATIONS.items():
                by_year[year][combo] += all(flags[p] for p in parts)
            rows.append({"date": date, "ticker": member.symbol, "sector": member.sector, "measured": member.status == C.JOINT_MEASURED,
                         "filingVisible": member.snapshot is not None, **{k: v.get(k) for k in REDUNDANCY_FEATURES},
                         **{"flag_" + k: bool(x) for k, x in flags.items()}})
    frame = pd.DataFrame(rows)
    eligible = len(frame)
    availability = {y: {"eligibleMemberDates": c["eligible"], **{f: pct(c[f], c["eligible"]) for f in FAMILIES},
                        **{k: pct(c[k], c["eligible"]) for k in COMBINATIONS}} for y, c in sorted(by_year.items())}
    overall = {f: pct(int(frame["flag_" + f].sum()), eligible) for f in FAMILIES}
    pairwise = {a: {b: pct(int((frame["flag_" + a] & frame["flag_" + b]).sum()), eligible) for b in FAMILIES if b != "dilution"}
                for a in FAMILIES if a != "dilution"}
    combos = {k: {"memberDates": int(np.all([frame["flag_" + p] for p in parts], axis=0).sum()),
                  "pct": pct(int(np.all([frame["flag_" + p] for p in parts], axis=0).sum()), eligible),
                  "companies": int(frame.loc[np.all([frame["flag_" + p] for p in parts], axis=0), "ticker"].nunique())}
              for k, parts in COMBINATIONS.items()}
    full = np.all([frame["flag_" + p] for p in COMBINATIONS["plusDistribution"]], axis=0)
    sectors = {s: {"eligibleShare": pct(int((frame["sector"] == s).sum()), eligible),
                   "plusDistributionShare": pct(int(((frame["sector"] == s) & full).sum()), int(full.sum()))}
               for s in sorted(frame["sector"].unique())}
    redundancy = spearman_mean(frame, REDUNDANCY_FEATURES)
    flagged = sorted("%s~%s" % (a, b) for a, row in redundancy.items() for b, x in row.items() if abs(x["meanRho"]) >= FLAG)
    # Missingness bias without a return: do measured names differ from filing-visible unmeasured names on price/quality characteristics?
    probe = ("mom121", "vol252", "beta252", "high52Distance", "roe", "operatingMargin")
    visible = frame[frame["filingVisible"]].copy()
    ranks = visible.groupby("date")[list(probe)].rank(pct=True)
    bias = {}
    for f in probe:
        m, u = ranks.loc[visible["measured"], f].dropna(), ranks.loc[~visible["measured"], f].dropna()
        bias[f] = {"meanPercentileMeasured": round(float(m.mean()), 4) if len(m) else None,
                   "meanPercentileUnmeasured": round(float(u.mean()), 4) if len(u) else None, "nMeasured": int(len(m)), "nUnmeasured": int(len(u))}
    sector_bias = {s: {"shareOfMeasured": pct(int(((visible["sector"] == s) & visible["measured"]).sum()), int(visible["measured"].sum())),
                       "shareOfFilingVisible": pct(int((visible["sector"] == s).sum()), len(visible))} for s in sorted(visible["sector"].unique())}
    v3 = json.loads(DX.A.V3_AUDIT.read_text())["regions"]["US"]
    report = {
        "id": "us-multifactor-pit-readiness-v1", "evidenceClass": "OUTCOME_BLIND_MULTIFACTOR_READINESS",
        "readsReturns": False, "readsLabels": False, "fitsModels": False, "forwardPricesRead": False,
        "sampling": {"rule": "every %dth weekly signal date from %s (fixed in advance)" % (SAMPLE_EVERY_WEEKS, sampled[0]), "dates": len(sampled),
                     "firstDate": sampled[0], "lastDate": sampled[-1], "memberDatesSeen": sum(universe_status.values()),
                     "priceAndIdentityEligibleMemberDates": eligible, "statusCounts": dict(sorted(universe_status.items()))},
        "pitClassification": {
            "PIT_EXACT": {"priceMomentum": "sealed replay-v16 closes up to the signal date",
                          "priceRisk": "same", "leadershipBreadth": "weekly bins clipped at the signal date",
                          "quality": "sealed Finnhub financials-reported, receipt-date visibility (roe, operatingMargin, profitMargin, debtToEquity, earningsGrowth)",
                          "acceleration": "consecutive-filing deltas of the same fields", "cashFlow": "PR #220 engine: OCF and capex TTM, filing-chain verified",
                          "distributionCore4": "PR #220 engine with exact concepts"},
            "RECONSTRUCTED": {"asTradedPrice": "total-return index divided by the cumulative dividend/split step rebuilt from sealed events "
                                               "(round-trip exact against price_adjustment on synthetic series)",
                              "value": "epsTtm, bookValuePerShare, fcfPerShare (sealed, PIT_EXACT) divided by the reconstructed as-traded price; share-count basis "
                                       "of the numerators is NOT context-verified and a split between filing and observation withholds the yield"},
            "SNAPSHOT_ONLY_OR_ABSENT": {"marketCap": "MARKET_CAP_PIT_UNRESOLVED: no dated share count x price series", "trailingPE": "absent from the sealed store",
                                        "forwardPE_consensus": "HISTORICAL_CONSENSUS_UNAVAILABLE", "bookYield_vendor": "absent (derived above instead)",
                                        "periodEndSharesAndDilution": "BLOCKED", "sectorHistory": "dated only for S&P 500 snapshots (195), not for departed names",
                                        "catalysts": "no point-in-time earnings-calendar, guidance or event feed exists in the repository"},
            "sealedFundamentalsInventory": store_inventory(store)},
        "availabilityByYearPct": availability, "availabilityOverallPct": overall, "pairwiseJointAvailabilityPct": pairwise,
        "combinations": combos, "sectorRepresentation": sectors,
        "featureRedundancy": {"features": list(REDUNDANCY_FEATURES), "familyOf": FAMILY_OF, "pairwiseMeanRankCorrelation": redundancy,
                              "flaggedAtAbsRho70": flagged, "minNamesPerDate": MIN_NAMES,
                              "reading": "ordering similarity only; value features use a reconstructed price basis and are NOT an approved feature"},
        "missingnessBias": {"question": "do names whose distribution features are measured differ from filing-visible names that are not, on price and quality characteristics?",
                            "percentileProbes": bias, "sectorMix": sector_bias,
                            "reading": "a percentile far from 0.5 on either side means missingness is not random with respect to that characteristic"},
        "survivorshipAndIdentity": {"departedWithoutUsablePanel": v3["sampleSurvivorship"]["noPanelDeparted"], "currentWithoutPanel": v3["sampleSurvivorship"]["noPanelCurrent"],
                                    "terminatedPanels": v3["terminations"]["terminatedInPanel"], "membershipSnapshots": v3["membershipSnapshots"],
                                    "terminalConsiderationCited": 1, "identityInput": identity,
                                    "reading": "the US sample contains no failed or acquired company with a price panel; value, momentum and quality are all measured on survivors"},
        "verdict": "A weekly cross-section of price, risk, quality, cash-flow and (reconstructed) value exists point-in-time for a "
                   "survivor-biased S&P 500 sample. It is NOT a fully point-in-time research matrix: market cap, consensus, dilution and catalysts are absent, "
                   "value rests on a reconstructed price basis with unverified numerator share counts, and departed names are missing.",
    }
    if args.limit_dates:
        print(json.dumps({k: report[k] for k in ("sampling", "availabilityOverallPct", "combinations")}, indent=1))
        return 0
    OUT.write_text(json.dumps(report, indent=1, sort_keys=True, allow_nan=False, ensure_ascii=False, default=lambda o: o.item()) + "\n", encoding="utf-8")
    print("eligible %d, flagged %s -> %s" % (eligible, flagged, OUT.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
