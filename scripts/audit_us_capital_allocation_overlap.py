"""Overlap of the candidate distribution features with the EXISTING price and quality features. Outcome-blind.

    python scripts/audit_us_capital_allocation_overlap.py --matrix <weekly matrix from the coverage audit> --output <json>

Question: is "distribution grew, covered by operating cash flow" new information, or a re-reading of momentum, risk or quality
the model already carried? Answered with cross-sectional rank correlations BETWEEN FEATURES on each sampled signal date. No return,
label or future price is read: the existing feature functions refuse a price dated after the signal date, and the module imports no
outcome code. The existing features are the ones `regional_alpha_features` builds (price, quality, acceleration, leadership);
value is reported NOT_MEASURED because that matrix itself excludes it (per-share numerator price basis, market cap not PIT).

A high rank correlation says two features order companies alike. It does not say either predicts anything.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import fundamental_acceleration as FA              # noqa: E402
from pipeline import historical_replay as HR                     # noqa: E402
from pipeline import pit_data as PIT                             # noqa: E402
from pipeline import regional_alpha_features as RAF              # noqa: E402
from pipeline import replay_inputs as RI                         # noqa: E402
from pipeline import us_capital_allocation_policy as POL         # noqa: E402
from pipeline import us_dual_benchmark_data as D                 # noqa: E402

SAMPLE_EVERY_WEEKS = 13               # one weekly date per quarter, fixed in advance
OVERLAP_FLAG = 0.70                   # the orthogonality threshold the earlier US design and fundamental-acceleration study used
MIN_NAMES_PER_DATE = 30
FAMILIES = {
    "priceMomentum": ("mom121", "return126", "relative126", "relative121", "high52Distance", "ma200Distance", "rsi14"),
    "priceRisk": ("vol252", "vol60", "downsideVol252", "maxDD252", "beta252"),
    "leadership": ("relativeStrengthBreadth52w",),
    "quality": ("roe", "operatingMargin", "profitMargin", "debtToEquity", "earningsGrowth"),
    "acceleration": tuple("delta_" + f for f in FA.PRIMARY_FIELDS),
}
CANDIDATES = ("incrementalDistributionOverOCF", "totalCashDistributionChangeYoY", "distributionToOCF", "totalCashDistributionTTM")
BENCH = "SPY"
RAF_MIN_POS = 272                     # regional_alpha_features.build_matrix: at least 272 prior sessions


def _plain(value):
    if hasattr(value, "item"):
        return value.item()
    raise TypeError("not JSON serializable: %r" % (type(value),))


def load_sealed():
    reader = D.SealedReader(ROOT)
    manifest = reader.manifest()
    by_ticker, fundamentals = {}, []
    for name in sorted(manifest["components"]):
        if name.startswith(("price/20", "benchmark/20")):
            for ref in manifest["components"][name]:
                for row in reader.component(ref):
                    if not row["ticker"].endswith((".KS", ".KQ")):
                        by_ticker.setdefault(row["ticker"], []).append({k: v for k, v in row.items() if k != "ticker"})
        elif name == "fundamentals":
            for ref in manifest["components"][name]:
                fundamentals.extend(reader.component(ref))
    records = {}
    for row in fundamentals:
        record = PIT.FundamentalRecord(**row["record"])
        if not record.ticker.endswith((".KS", ".KQ")):
            records.setdefault(record.ticker, []).append(record)
    panel = HR.PricePanel({t: RI.rows_frame(rows).sort_index() for t, rows in by_ticker.items()})
    return panel, PIT.FundamentalStore(records), {"manifestSha256": manifest["sha256"], "through": manifest["through"]}


def existing_features(panel, store, ticker, date, bench):
    h = panel.get(ticker)
    pos = h.position(np.datetime64(date, "ns")) if h else -1
    if pos < RAF_MIN_POS:
        return None
    if (np.datetime64(date) - h.dates[pos]).astype("timedelta64[D]").astype(int) > HR.MAX_STALE_CALENDAR_DAYS:
        return None
    values = RAF.price_features(h, pos, bench, date)
    values["relativeStrengthBreadth52w"] = RAF.weekly_breadth(h, bench, date)
    pair = FA.resolve_filing_pair(store, ticker, "US", date)
    current = pair.current
    values.update({f: current.fields.get(f) if current else None for f in RAF.FUNDAMENTAL})
    deltas = FA.compute_deltas(current, pair.previous) if pair.status == FA.OK else {}
    values.update({"delta_" + f: deltas.get(f) for f in FA.PRIMARY_FIELDS})
    return values


def spearman_by_date(frame, left, right):
    out = []
    for date, g in frame.groupby("date"):
        pair = g[[left, right]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(pair) >= MIN_NAMES_PER_DATE and pair[left].nunique() > 2 and pair[right].nunique() > 2:
            out.append(float(pair[left].rank().corr(pair[right].rank())))
    return out


def summary(values):
    if not values:
        return None
    a = np.array(values)
    return {"dates": len(a), "meanRho": round(float(a.mean()), 4), "medianRho": round(float(np.median(a)), 4),
            "p10": round(float(np.quantile(a, .1)), 4), "p90": round(float(np.quantile(a, .9)), 4), "flaggedRedundant": bool(abs(a.mean()) >= OVERLAP_FLAG)}


def family_r2(frame, target, columns):
    """Mean cross-sectional R-squared of the candidate's RANK on the ranks of a family (complete cases per date)."""
    out = []
    for date, g in frame.groupby("date"):
        d = g[[target, *columns]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(d) < max(MIN_NAMES_PER_DATE, len(columns) + 10):
            continue
        y = d[target].rank().to_numpy(float)
        x = np.column_stack([np.ones(len(d)), *[d[c].rank().to_numpy(float) for c in columns]])
        beta, *_ = np.linalg.lstsq(x, y, rcond=None)
        resid = y - x @ beta
        tss = float(((y - y.mean()) ** 2).sum())
        if tss > 0:
            r2 = 1.0 - float((resid ** 2).sum()) / tss
            out.append(1.0 - (1.0 - r2) * (len(d) - 1) / (len(d) - len(columns) - 1))
    return {"dates": len(out), "meanAdjustedR2": round(float(np.mean(out)), 4) if out else None}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    matrix = pd.read_csv(args.matrix, compression="gzip", dtype={"symbol": str, "ticker": str})
    dates = sorted(matrix["date"].unique())
    sampled = dates[::SAMPLE_EVERY_WEEKS]
    measured = matrix[(matrix["status"] == "JOINT_MEASURED") & matrix["date"].isin(sampled)].copy()
    counts = measured.groupby("date").size()
    measured = measured[measured["date"].isin(counts[counts >= MIN_NAMES_PER_DATE].index)]
    growth = measured["yoy"].astype(float)
    ratio = measured["distributionToOCF"].astype(float)
    measured["incrementalDistributionOverOCF"] = np.where(growth > -1.0, ratio * growth / (1.0 + growth), np.nan)
    measured = measured.rename(columns={"yoy": "totalCashDistributionChangeYoY", "distributionToOCF": "distributionToOCF",
                                        "distribution": "totalCashDistributionTTM"})
    panel, store, identity = load_sealed()
    bench = panel.get(BENCH)
    rows = []
    for record in measured.itertuples(index=False):
        values = existing_features(panel, store, record.ticker, record.date, bench)
        if values is not None:
            rows.append({"date": record.date, "ticker": record.ticker, "sector": record.sector, **values,
                         **{c: getattr(record, c) for c in CANDIDATES}})
    frame = pd.DataFrame(rows)
    pairs = {c: {fam: {f: summary(spearman_by_date(frame, c, f)) for f in names if f in frame} for fam, names in FAMILIES.items()} for c in CANDIDATES}
    flagged = sorted({"%s~%s" % (c, f) for c, fams in pairs.items() for fam in fams.values() for f, s in fam.items() if s and s["flaggedRedundant"]})
    r2 = {c: {fam: family_r2(frame, c, [f for f in names if f in frame]) for fam, names in FAMILIES.items()} for c in CANDIDATES}
    r2_all = {c: family_r2(frame, c, [f for names in FAMILIES.values() for f in names if f in frame]) for c in CANDIDATES}
    # Where do the rule's own picks sit among the measured names on the existing features? (percentile within the date, no return)
    profile, picks = {}, 0
    for date, g in frame.groupby("date"):
        evaluations = [POL.evaluate({"ticker": r.ticker, "sector": r.sector, "priceOk": True, "reportAgeDays": 0,
                                     "features": {"totalCashDistributionTTM": {"value": r.totalCashDistributionTTM, "state": "VALID"},
                                                  "totalCashDistributionChangeYoY": {"value": r.totalCashDistributionChangeYoY, "state": "VALID"},
                                                  "operatingCashFlowTTM": {"value": 1.0, "state": "VALID"},
                                                  "distributionToOCF": {"value": r.distributionToOCF, "state": "VALID"}}})
                       for r in g.itertuples(index=False)]
        decision = POL.select(evaluations, min_measured=0)
        chosen = {s["ticker"] for s in decision["selected"]}
        if not chosen:
            continue
        ranks = g.set_index("ticker")[[f for names in FAMILIES.values() for f in names if f in g]].rank(pct=True)
        for t in chosen & set(ranks.index):
            picks += 1
            for f, v in ranks.loc[t].items():
                if pd.notna(v):
                    profile.setdefault(f, []).append(float(v))
    report = {
        "id": "us-capital-allocation-feature-overlap-v1", "evidenceClass": "OUTCOME_BLIND_FEATURE_OVERLAP",
        "readsReturns": False, "readsLabels": False, "fitsModels": False, "forwardPricesRead": False,
        "sampling": {"rule": "every %dth weekly signal date, dates with at least %d measured names" % (SAMPLE_EVERY_WEEKS, MIN_NAMES_PER_DATE),
                     "datesSampled": int(frame["date"].nunique()) if len(frame) else 0, "rows": int(len(frame)),
                     "firstDate": frame["date"].min() if len(frame) else None, "lastDate": frame["date"].max() if len(frame) else None},
        "existingFeatures": {"source": "pipeline/regional_alpha_features.py price_features, weekly_breadth, FA.resolve_filing_pair (replay-v16 sealed inputs)",
                             "families": {k: list(v) for k, v in FAMILIES.items()},
                             "value": {"status": "NOT_MEASURED", "reason": "the existing matrix excludes earningsYield/bookYield/fcfYield (per-share numerator price basis unresolved) and market cap (not PIT)",
                                       "definitionalNote": "the candidate features are scaled by operating cash flow, not by price, so they are not a price-denominated value ratio by construction"},
                             "qualityCaveat": "fundamental fields are the sealed store's, not re-vetted against raw filings as the original matrix does"},
        "inputs": identity, "redundancyThreshold": OVERLAP_FLAG,
        "pairwiseRankCorrelation": pairs, "flaggedPairs": flagged,
        "rankRSquaredOnExistingFamilies": r2, "rankRSquaredOnAllExistingFeatures": r2_all,
        "selectedNamesPercentileProfile": {"picks": picks, "meanPercentileWithinDate": {f: round(float(np.mean(v)), 4) for f, v in sorted(profile.items())},
                                           "reading": "0.5 = no tilt; descriptive only"},
        "meaning": "a high rank correlation means similar ordering, not predictive value; none of this reads a return",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1, sort_keys=True, allow_nan=False, ensure_ascii=False, default=_plain) + "\n", encoding="utf-8")
    print("dates %d rows %d flagged %s" % (report["sampling"]["datesSampled"], report["sampling"]["rows"], flagged))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
