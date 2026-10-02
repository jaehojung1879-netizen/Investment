"""KR factor anatomy v1 — assembly of the frozen tables from one analysis panel, and the human-readable report.

Pure: the panel, the sealed-v1 prediction records and the spec go in, JSON-able tables and row-level frames come
out. Nothing here reads a file, calls a network, fits a model or values a portfolio. The execution module is the
only caller that touches real data, and only after a permit exists.

EXPLORATORY / DEVELOPMENT / HYPOTHESIS-GENERATING. There is no PASS, no FAIL, no promotion, no weight and no
"best factor" anywhere in the output schema (`assert_no_forbidden_keys` runs on every result).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import kr_factor_anatomy as A
from . import kr_value_quality_catalyst as F

PRIMARY_UNIVERSE = "BROAD_PIT_ANALYSIS_UNIVERSE"
SECONDARY_UNIVERSE = "V1_INVESTABLE_ANALYSIS_UNIVERSE"
V1_DISCIPLINE = "V1_TERMINAL_DISCIPLINE"
ALL_OBSERVED = "ALL_OBSERVED_ENDPOINTS"


def outcome_column(horizon, treatment):
    return ("rel" if treatment == V1_DISCIPLINE else "relObs") + str(horizon)


def header(spec):
    return {"studyId": spec["studyId"], "scientificStatus": spec["scientificStatus"],
            "returnBasis": A.RETURN_BASIS, "totalReturnAnalysis": "DATA_FOUNDATION_REQUIRED",
            "dividendAdjustment": "NONE_APPLIED", "structuralClassification": spec["structuralClassification"]["status"],
            "developmentCutoff": spec["developmentCutoff"], "benchmark": spec["benchmark"],
            "interpretation": "HYPOTHESIS_GENERATING_ONLY; NO_PASS_FAIL; NO_PROMOTION; CANNOT_RESCUE_OR_ALTER_KR_V1"}


def denominators(panel, spec):
    """Observed valid outcomes and withheld/unresolved outcomes, by year and horizon. Nothing is zero-filled."""
    out = {}
    for h in spec["horizons"]:
        by_year = {}
        for year, g in panel.groupby(panel.date.str[:4]):
            by_year[year] = {"signalRows": int(len(g)),
                             "v1TerminalDiscipline": {str(k): int(v) for k, v in g["status" + str(h)].value_counts().items()},
                             "rawEndpointStatus": {str(k): int(v) for k, v in g["rawStatus" + str(h)].value_counts().items()},
                             "observedValidOutcomes": int(np.isfinite(A.clean_numeric(g["rel" + str(h)])).sum()),
                             "observedValidOutcomesAllEndpoints": int(np.isfinite(A.clean_numeric(g["relObs" + str(h)])).sum())}
        out[str(h)] = by_year
    return out


def prepare_universe(panel, universe, spec):
    sub = panel.loc[A.universe_mask(panel, universe, spec)].reset_index(drop=True)
    context = ["marketCap", "adv60"]
    factors = [f["name"] for f in spec["factors"]]
    return A.add_signal_time_ranks(sub, factors + context)


def add_family_columns(sub, v1_scores, spec):
    """Frozen rank-mean family scores (signal-time, equal weight over the constituents a name HAS, the v1
    `scores()` rule), plus the exact archived v1 family scores per horizon where v1 produced them."""
    out = sub.copy()
    for family, members in F.FAMILIES.items():
        cols = [m + "__pct" for m in members]
        out[family + "_RANKMEAN"] = out[cols].mean(axis=1, skipna=True)
    for h, frame in (v1_scores or {}).items():
        keep = frame[["date", "ticker"] + [f + "_SCORE" for f in F.FAMILIES]].rename(
            columns={f + "_SCORE": f + "_V1_H" + str(h) for f in F.FAMILIES})
        out = out.merge(keep, on=["date", "ticker"], how="left", validate="one_to_one")
    names = [f + "_RANKMEAN" for f in F.FAMILIES] + [c for c in out.columns if "_V1_H" in c]
    return A.add_signal_time_ranks(out, names), names


def flatten_rows(rows):
    """One flat table per factor/horizon: a row per signal date with every decile statistic in its own column."""
    flat = []
    for r in rows:
        record = {k: r[k] for k in ("date", "year", "signalNames", "outcomeNames", "spread", "rho")}
        for key, prefix in (("means", "mean"), ("medians", "median"), ("beat", "beat"), ("counts", "count")):
            for i, value in enumerate(r[key]):
                record[f"{prefix}_d{i + 1}"] = value
        flat.append(record)
    return pd.DataFrame(flat)


def regime_table(rows, regime_by_date):
    """The same date-equal-weighted spread and rank correlation split by the frozen v1 benchmark state
    (`kr_market_risk_overlay.state_at().riskMultiplier`: past-only trend and 63-session volatility, 1.0 / 0.7 / 0.4).
    No regime boundary is invented here."""
    groups = {}
    for r in rows:
        state = regime_by_date.get(r["date"])
        if state is None or (isinstance(state, float) and not np.isfinite(state)):
            continue
        groups.setdefault(str(state), {"spread": [], "rho": []})
        groups[str(state)]["spread"].append(r["spread"])
        groups[str(state)]["rho"].append(r["rho"])
    return {state: {"datesWithDeciles": int(np.isfinite(v["spread"]).sum()),
                    "meanD10MinusD1": A._nanmean(v["spread"]), "meanRankCorrelation": A._nanmean(v["rho"])}
            for state, v in sorted(groups.items())}


def standalone(sub, spec, treatment=V1_DISCIPLINE, columns=None):
    """Factor tables for one prepared universe. Row-level per-date records are returned separately."""
    columns = columns or [f["name"] for f in spec["factors"]]
    tables, rows = {}, {}
    regime = dict(zip(sub.date, sub.riskMultiplier)) if "riskMultiplier" in sub else {}
    for col in columns:
        for h in spec["horizons"]:
            result = A.factor_anatomy(sub, col, outcome_column(h, treatment), h, spec)
            per_date = result.pop("perDate")
            result["byBenchmarkState"] = regime_table(per_date, regime)
            rows[(col, h)] = flatten_rows(per_date)
            tables.setdefault(col, {})[str(h)] = result
    return tables, rows


def size_liquidity(sub, spec, treatment=V1_DISCIPLINE):
    out = {}
    factors = [f["name"] for f in spec["factors"]]
    for h in spec["horizons"]:
        y = outcome_column(h, treatment)
        block = {"marketCapStrata": {}, "adv60Strata": {}}
        for col in factors:
            block["marketCapStrata"][col] = A.stratified_association(sub, col, "marketCap", y, spec)
            if col == "logAdv60":
                block["adv60Strata"][col] = {"status": "NOT_APPLICABLE_SAME_VARIABLE_AS_PARTITION"}
            else:
                block["adv60Strata"][col] = A.stratified_association(sub, col, "adv60", y, spec)
        block["liquidityViews"] = {
            "rawAdvRankVsFutureReturn": "see standalone.logAdv60 deciles",
            "advEffectWithinMarketCapStrata": block["marketCapStrata"]["logAdv60"],
            "marketCapEffectWithinAdvStrata": A.stratified_association(sub, "marketCap", "adv60", y, spec)}
        block["contextMarketCapDeciles"] = {k: v for k, v in A.factor_anatomy(sub, "marketCap", y, h, spec).items()
                                            if k != "perDate"}
        out[str(h)] = block
    return out


def families(sub, v1_scores, spec, treatment=V1_DISCIPLINE):
    enriched, names = add_family_columns(sub, v1_scores, spec)
    tables, rows = {}, {}
    for col in names:
        horizons = spec["horizons"]
        if "_V1_H" in col:
            horizons = [int(col.rsplit("_H", 1)[1])]
        for h in horizons:
            result = A.factor_anatomy(enriched, col, outcome_column(h, treatment), h, spec)
            rows[(col, h)] = flatten_rows(result.pop("perDate"))
            tables.setdefault(col, {})[str(h)] = result
    return tables, rows, enriched


def fundamentals_vs_price(sub, spec, treatment=V1_DISCIPLINE):
    cfg = spec["fundamentalsVsPrice"]
    strata = {s["name"]: {"column": s["column"]} for s in cfg["strata"]}
    out = {"signalTime": {}, "windowRealised": {}}
    sub = sub.copy()
    sub["ocfImprovementUp"] = [None if not np.isfinite(v) else bool(v > 0)
                               for v in A.clean_numeric(sub.ocfImprovementToAssets)]
    sub["netIncomeImprovementUp"] = [None if not np.isfinite(v) else bool(v > 0)
                                     for v in A.clean_numeric(sub.netIncomeImprovementToAssets)]
    for flag in ("ocfImprovementUp", "netIncomeImprovementUp"):
        out["signalTime"][flag] = {str(h): A.four_state_table(sub, flag, outcome_column(h, treatment),
                                                              strata=strata, spec=spec)
                                   for h in spec["horizons"]}
    window = cfg["windowRealised"]
    if window["column"] in sub:
        out["windowRealised"] = {str(window["horizon"]): A.four_state_table(
            sub, window["column"], outcome_column(window["horizon"], treatment), strata=strata, spec=spec,
            mean_columns=tuple(window["meanColumns"]))}
    return out


def interactions(sub, spec, treatment=V1_DISCIPLINE):
    out = {}
    for item in spec["interactions"]:
        out[item["id"]] = {str(h): A.interaction_table(sub, item["a"], item["b"], outcome_column(h, treatment), spec)
                           for h in spec["horizons"]}
    return out


def labels_and_map(tables, strata_block, spec):
    """Rule-based descriptive labels and the one-page executive map, all factors side by side, unsorted."""
    rows = []
    for factor in spec["factors"]:
        name = factor["name"]
        entry = {"factor": name, "family": factor["family"], "plainMeaning": factor["plain"],
                 "caveat": factor["caveat"], "horizons": {}}
        for h in spec["horizons"]:
            anatomy = tables[name][str(h)]
            sign = int(np.sign(anatomy["meanRankCorrelation"])) if np.isfinite(anatomy["meanRankCorrelation"]) else 0
            cap = strata_block[str(h)]["marketCapStrata"][name]["table"]
            liq = strata_block[str(h)]["adv60Strata"][name]
            agreement = A.strata_agreement(cap, sign)
            liq_agreement = A.strata_agreement(liq["table"], sign) if "table" in liq else None
            entry["horizons"][str(h)] = {
                "direction": {1: "POSITIVE", -1: "NEGATIVE", 0: "NONE"}[sign],
                "d10MinusD1": anatomy["d10MinusD1"], "meanRankCorrelation": anatomy["meanRankCorrelation"],
                "interval": anatomy["interval"], "positiveYearFraction": anatomy["spreadYearStability"]["positiveYearFraction"],
                "marketCapStrataAgreement": agreement, "liquidityStrataAgreement": liq_agreement,
                "descriptiveLabel": A.descriptive_label(anatomy, agreement, spec)}
        rows.append(entry)
    return rows


def event_frame(sub, horizon, v1_predictions, treatment=V1_DISCIPLINE):
    """All valid outcome windows of one horizon with the sealed v1 prediction attached where it exists."""
    y = outcome_column(horizon, treatment)
    h = str(horizon)
    keep = sub.loc[np.isfinite(A.clean_numeric(sub[y]))].copy()
    events = pd.DataFrame({"date": keep.date, "ticker": keep.ticker, "entryDate": keep["entry" + h],
                           "exitDate": keep["exit" + h], "stockReturn": keep["stock" + h],
                           "benchmarkReturn": keep["bench" + h], "relativeReturn": keep[y]})
    events = pd.concat([events.reset_index(drop=True), keep.drop(columns=["date", "ticker"]).reset_index(drop=True)], axis=1)
    events["prediction"], events["predictionError"], events["v1Rank"] = np.nan, np.nan, np.nan
    if v1_predictions is not None and len(v1_predictions):
        slim = v1_predictions[["date", "ticker", "prediction", "rank"]].rename(columns={"prediction": "p", "rank": "r"})
        events = events.merge(slim, on=["date", "ticker"], how="left", validate="one_to_one")
        events["prediction"], events["v1Rank"] = events.p, events.r
        events["predictionError"] = events.relativeReturn - events.prediction
        events = events.drop(columns=["p", "r"])
    return events


def explain_events(selected, v1_folds, horizon, spec):
    """Per selected event: 11 raw features, within-date percentiles, family scores, the fold coefficients and the
    exact linear decomposition. A decomposition that does not reproduce the archived prediction says so."""
    out = []
    folds = {(int(f["horizon"]), int(f["cutoff"][:4])): f for f in (v1_folds or [])}
    for row in selected.to_dict("records"):
        item = {k: row.get(k) for k in ("date", "ticker", "entryDate", "exitDate", "stockReturn", "benchmarkReturn",
                                          "relativeReturn", "prediction", "predictionError", "v1Rank")}
        item["rawFeatures"] = {n: (None if not np.isfinite(A.clean_numeric([row.get(n)])[0]) else float(row[n]))
                               for n in F.RAW_FEATURES}
        item["withinDatePercentile"] = {n: (None if not np.isfinite(row.get(n + "__pct", np.nan)) else float(row[n + "__pct"]))
                                        for n in F.RAW_FEATURES}
        item["rankMeanFamilyScores"] = {f: (None if not np.isfinite(row.get(f + "_RANKMEAN", np.nan)) else float(row[f + "_RANKMEAN"]))
                                        for f in F.FAMILIES}
        fold = folds.get((horizon, int(row["date"][:4])))
        if fold is not None and row.get("prediction") is not None and np.isfinite(row.get("prediction", np.nan)):
            item["v1Decomposition"] = A.reconstruct_prediction(row, fold, archived=row["prediction"])
        else:
            item["v1Decomposition"] = {"status": "NO_V1_PREDICTION_OR_FOLD"}
        out.append(item)
    return out


def winners_losers(events, v1_folds, horizon, spec):
    tables = A.mechanical_event_tables(events, spec)
    return {name: explain_events(frame, v1_folds, horizon, spec) for name, frame in tables.items()}


def case_studies(events, v1_folds, spec):
    out = {}
    for ticker in spec["caseStudies"]["tickers"]:
        picked = A.case_selection(events, ticker)
        if picked["status"] != "SELECTED":
            out[ticker] = {"status": picked["status"]}
            continue
        out[ticker] = {"status": "SELECTED"}
        for key in ("highestPrediction", "lowestPrediction", "largestPositiveError", "largestNegativeError"):
            row = picked[key]
            out[ticker][key] = explain_events(pd.DataFrame([row]), v1_folds, spec["caseStudies"]["horizon"], spec)[0]
    return out


def analyze_all(panel, spec, v1=None, *, structural=None):
    """Assemble every frozen table. `v1` = {"predictions": {horizon: frame}, "folds": [..]} or None."""
    v1 = v1 or {"predictions": {}, "folds": []}
    result = {"header": header(spec), "denominators": denominators(panel, spec), "universes": {}}
    rows = {}
    treatments = {V1_DISCIPLINE: "PRIMARY", ALL_OBSERVED: "SENSITIVITY_STANDALONE_ONLY"}
    for universe in (PRIMARY_UNIVERSE, SECONDARY_UNIVERSE):
        sub = prepare_universe(panel, universe, spec)
        block = {"rows": int(len(sub)), "standalone": {}, "sizeLiquidity": None}
        tables, per_date = standalone(sub, spec, V1_DISCIPLINE)
        block["standalone"][V1_DISCIPLINE] = tables
        rows[(universe, V1_DISCIPLINE)] = per_date
        if universe == PRIMARY_UNIVERSE:
            block["standalone"][ALL_OBSERVED], sens_rows = standalone(sub, spec, ALL_OBSERVED)
            rows[(universe, ALL_OBSERVED)] = sens_rows
        block["sizeLiquidity"] = size_liquidity(sub, spec)
        block["families"], family_rows, enriched = families(sub, v1["predictions"], spec)
        rows[(universe, "families")] = family_rows
        block["fundamentalsVsPrice"] = fundamentals_vs_price(sub, spec)
        block["interactions"] = interactions(sub, spec)
        block["labelsAndExecutiveMap"] = labels_and_map(tables, block["sizeLiquidity"], spec)
        result["universes"][universe] = block
        if universe == PRIMARY_UNIVERSE:
            primary_enriched = enriched
    result["treatments"] = treatments
    result["structuralClassification"] = structural or {"status": spec["structuralClassification"]["status"],
                                                        "subgroupTables": "DATA_FOUNDATION_REQUIRED"}
    kepco = spec["kepco"]["ticker"]
    kept, dropped = A.apply_exclusion(panel, [kepco])
    leave_sub = prepare_universe(kept, PRIMARY_UNIVERSE, spec)
    leave_tables, _ = standalone(leave_sub, spec, V1_DISCIPLINE)
    result["kepco"] = {"ticker": kepco, "fullUniverseIncludesKepco": True, "removedRows": int(len(dropped)),
                       "leaveKepcoOutStandalone": leave_tables,
                       "status": "SINGLE_TICKER_LEAVE_OUT_NOT_A_CLASSIFICATION_CLAIM"}
    events, detail = {}, {}
    for h in spec["horizons"]:
        events[h] = event_frame(primary_enriched, h, v1["predictions"].get(h))
        detail[str(h)] = winners_losers(events[h], v1["folds"], h, spec)
        if v1["predictions"].get(h) is not None and len(v1["predictions"][h]):
            detail[str(h)]["mostFrequentV1TopFive"] = A.top5_frequency(v1["predictions"][h], spec).to_dict("records")
    result["winnersLosers"] = detail
    cs_h = spec["caseStudies"]["horizon"]
    result["caseStudies"] = case_studies(events[cs_h], v1["folds"], spec)
    A.assert_no_forbidden_keys(result)
    return result, rows


PLAIN_BANNER = ("EXPLORATORY / DEVELOPMENT / HYPOTHESIS-GENERATING. Korean history through 2026-09-14 is already "
                "outcome-exposed: nothing below validates, rescues or promotes any model, factor or portfolio, and "
                "nothing alters the sealed DEVELOPMENT_REJECT of kr-model-overlay-portfolio-v1.")


def render_report(result, spec):
    """Human-readable Markdown. Rows keep the spec's factor order; they are never sorted by result."""
    lines = ["# KR factor anatomy v1 — market map", "", "**" + PLAIN_BANNER + "**", "",
             "Return basis: `" + A.RETURN_BASIS + "` — the stock's and the KODEX 200 benchmark's adjusted-index return "
             "over the same sessions, dividend-reinvested ONLY where the vendor served distributions. It is neither a pure "
             "price return nor a complete total shareholder return; high-dividend stocks (banks, financials) are NOT "
             "reliably represented. Total-return analysis: DATA_FOUNDATION_REQUIRED.", "",
             "Structural/sector subgroup analysis: " + result["structuralClassification"]["status"] +
             " (no historical classification is back-applied from today).", ""]
    primary = result["universes"][PRIMARY_UNIVERSE]
    lines += ["## A. Executive map (broad PIT universe, side by side, spec order)", "",
              "| factor | family | H126 D10−D1 | H126 yrs positive | H126 label | H252 D10−D1 | H252 yrs positive | H252 label |",
              "|---|---|---|---|---|---|---|---|"]
    def fmt(x, digits=4):
        return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{digits}f}"
    for row in primary["labelsAndExecutiveMap"]:
        h1, h2 = row["horizons"]["126"], row["horizons"]["252"]
        lines.append(f"| {row['factor']} | {row['family']} | {fmt(h1['d10MinusD1'])} | {fmt(h1['positiveYearFraction'], 2)} | "
                     f"{h1['descriptiveLabel']} | {fmt(h2['d10MinusD1'])} | {fmt(h2['positiveYearFraction'], 2)} | "
                     f"{h2['descriptiveLabel']} |")
    lines += ["", "## B. Factor cards", ""]
    for row in primary["labelsAndExecutiveMap"]:
        name = row["factor"]
        lines += ["### " + name, "", row["plainMeaning"], "", "Caveat: " + row["caveat"], ""]
        for h in ("126", "252"):
            t = primary["standalone"][V1_DISCIPLINE][name][h]
            lines += [f"**H{h}** — dates with deciles {t['datesWithDeciles']}, outcome observations {t['outcomeObservations']}",
                      "", "| decile | mean rel. | median rel. | beat benchmark |", "|---|---|---|---|"]
            for i in range(10):
                lines.append(f"| D{i + 1} | {fmt(t['decileMeanRelative'][i])} | {fmt(t['decileMedianRelative'][i])} | "
                             f"{fmt(t['decileBeatBenchmarkFraction'][i], 3)} |")
            lines += ["", "Calendar-year D10−D1: " + ", ".join(f"{y}: {fmt(v['mean'])}" for y, v in t["annualD10MinusD1"].items()), ""]
    lines += ["## C. Structural anomaly section", "",
              "- Regulated / public-enterprise sensitivity: DATA_FOUNDATION_REQUIRED (no dated authoritative list).",
              "- Financial-company sensitivity: DATA_FOUNDATION_REQUIRED (no dated authoritative list).",
              "- Price-return vs total-return: see header above; no dividend adjustment was fabricated.",
              "- KEPCO (015760.KS) stays in every primary table; the leave-KEPCO-out figures are a labelled single-ticker "
              "sensitivity, not a classification claim.", "",
              "## D. Winner / loser anatomy and E. Samsung / SK Hynix / KEPCO case studies", "",
              "Mechanical selections with exact v1 decompositions are in the machine-readable results "
              "(`winnersLosers`, `caseStudies`). No narrative is attached by the execution code.", ""]
    return "\n".join(lines) + "\n"
