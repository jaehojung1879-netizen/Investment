"""Run frozen regional-alpha-model-v1 on sealed inputs without modifying them."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import sklearn  # noqa: E402
from pipeline import regional_alpha_features as F  # noqa: E402
from pipeline import regional_alpha_model as M  # noqa: E402


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_json(path, value):
    path.write_bytes(F.canonical(clean(value)))


def write_frame(path, frame):
    path.write_bytes(gzip.compress(frame.to_csv(index=False, float_format="%.17g", lineterminator="\n").encode(), mtime=0))


def coverage_table(frame, manifest):
    rows = []
    for region in ("US", "KR"):
        region_frame = frame.loc[frame.region.eq(region)]
        periods = [("ALL", region_frame), ("PRE_2015", region_frame.loc[region_frame.date < "2015-01-01"]),
                   ("POST_2015", region_frame.loc[region_frame.date >= "2015-01-01"])]
        periods += [(str(year), g) for year, g in region_frame.groupby(region_frame.date.str[:4])]
        for period, group in periods:
            row = dict(region=region, period=period, rows=len(group), dates=group.date.nunique())
            for kind, kinds in {"all": ("price", "fundamental", "acceleration", "leadership", "size"),
                                "price": ("price", "leadership"), "fundamental": ("fundamental",),
                                "acceleration": ("acceleration",), "fx": ("fx",)}.items():
                names = [x["feature"] for x in manifest if x["region"] == region and x["eligible"] and x["group"] in kinds]
                row[kind+"Coverage"] = float(group[names].notna().mean().mean()) if names and len(group) else None
            rows.append(row)
    return rows


def missingness_diagnostic(predictions):
    rows = []
    for (region, year), group in predictions.loc[predictions.method.eq("HGBR")].groupby(["region", "validationYear"]):
        missing = group[list(F.FUNDAMENTAL)].isna().mean(axis=1)
        missing_ic = missing.corr(group.predictionScore, method="spearman") if missing.nunique() > 1 and group.predictionScore.nunique() > 1 else None
        buckets = {}
        for label, mask in (("allFundamentalsMissing", missing.eq(1)), ("someFundamentalPresent", missing.lt(1))):
            part = group.loc[mask]
            values = []
            for _, date_rows in part.groupby("date"):
                if len(date_rows.dropna(subset=["futureExcess126"])) >= 10 and date_rows.predictionScore.nunique() > 1:
                    values.append(date_rows.predictionScore.corr(date_rows.futureExcess126, method="spearman"))
            buckets[label] = dict(rows=len(part), meanDateIC=float(np.nanmean(values)) if values else None)
        rows.append(dict(region=region, year=int(year), meanFundamentalMissing=float(missing.mean()),
                         scoreMissingnessSpearman=missing_ic, strata=buckets))
    return rows


def fmt(x):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.6f}"
    return str(x)


def answers(report):
    metrics = report["metrics"]
    primary = metrics["primary"]
    result = [
        ("Q1. Feature lineage PIT-safe?", "Only source-gated features admitted. Visible-only raw filing re-derivation, dated membership snapshots, backward-only prices. Snapshot timing and missing/delisted price coverage limit completeness; no claim of exact historical universe coverage. See Table A and lineageAudit."),
        ("Q2. Independently trained US/KR?", "Yes. Distinct training rows, transformations, annual fits and fitted parameters; no pooled model or region input."),
    ]
    for number, key in enumerate(("US/RIDGE", "US/HGBR", "KR/RIDGE", "KR/HGBR"), 3):
        s = primary.get(key, {}).get("rankIC", {})
        result.append((f"Q{number}. {key} walk-forward Rank IC?", f"{fmt(s.get('mean'))}; CI {s.get('ci95')}. DISCOVERY_ONLY."))
    result += [
        ("Q7. Do CIs include zero?", "; ".join(k+": "+str(v["rankIC"]["containsZero"]) for k, v in sorted(primary.items()))),
        ("Q8. Annual sign consistency?", "; ".join(k+": "+fmt(v["positiveFoldFraction"]) for k, v in sorted(primary.items()))),
        ("Q9. Quintile monotonicity?", "; ".join(k+": "+fmt(v["monotonicity"]) for k, v in sorted(primary.items()))),
        ("Q10. Top10 beats benchmark?", "; ".join(k+": mean="+fmt(v["top10Excess"]["mean"])+", CI="+str(v["top10Excess"]["ci95"]) for k, v in sorted(primary.items())) + ". Gross overlapping signal diagnostic; not portfolio returns."),
        ("Q11. Beats simple baselines?", "See Table D and pairedICComparisons: differences are paired by date with HAC CI. A positive point gap alone is not established superiority. Four-factor unavailable because historical sectors are unresolved; no proxy substituted."),
        ("Q12. Incremental nonlinearity?", "; ".join(r+": "+str(metrics["pairedICComparisons"].get(r+"/HGBR-minus-RIDGE")) for r in ("US", "KR"))),
        ("Q13. Incremental fundamentals over price-only?", "; ".join(r+": "+str(metrics["pairedICComparisons"].get(r+"/HGBR-minus-HGBR_PRICE_ONLY")) for r in ("US", "KR")) + ". KR full-minus-price also includes dated size, so it cannot isolate fundamentals alone."),
        ("Q14. Evidence of KR DART missingness distortion?", "Annual coverage, score-versus-missingness association and all-missing/partly-present strata are published in missingnessDiagnostic. These are observational; association does not establish vendor-regime causation. No calendar year or ticker was fitted."),
        ("Q15. Leading US interactions?", "Not identified causally. HGBR has no built-in feature importance; no post-result interaction search was run. Ridge standardized coefficients by annual fold are published; they never select features."),
        ("Q16. Regional A/B/C?", str(metrics["classification"]) + ". STRONG=A, PROMISING=B, NO_MODEL_EVIDENCE=C; NOT_EVALUABLE is missing measurement, not failure evidence."),
        ("Q17. Move to prospective sealing?", str(report["prospectiveEligibleRegions"]) + ". No production promotion or automatic schedule. Schema in the frozen design; evaluate after 126D maturity."),
        ("Q18. Close historical discovery?", "Yes. HISTORICAL_ALPHA_DISCOVERY_PHASE=CLOSED. One budget per region spent. No tuning, additional algorithm or factor search follows this run."),
    ]
    return result


def markdown(report):
    metrics = report["metrics"]
    lines = ["# regional-alpha-model-v1 results", "", "**DISCOVERY_ONLY — promotionEligible=false.**",
             "Walk-forward OOS means held out from that annual fit, not independently validated historical evidence.", "",
             f"Input commit: `{F.INPUT_COMMIT}`. Input manifest: `{report['inputManifestDigest']}`.",
             f"Sealed input tree unchanged: `{report['sealedInvariant']['unchanged']}`.", "",
             "## Table A — Feature lineage", "",
             "| Region | Feature | Raw source → canonical | PIT rule | Coverage | Eligible |",
             "|---|---|---|---|---:|---|"]
    for r in report["featureManifest"]:
        lines.append(f"| {r['region']} | {r['feature']} | {r['rawSource']} → {r['canonicalField']} | {r['pitRule']} | {fmt(r['historicalCoverage']['ratio'])} | {r['eligible']} |")
    lines += ["", "## Table B — Annual walk-forward folds", "", "| Region | Model | Validation year | Train cutoff | Train / validation rows | Rank IC | Q5-Q1 | Label coverage |",
              "|---|---|---:|---|---:|---:|---:|---:|"]
    for f in metrics["annual"]:
        m = f["metrics"]
        lines.append(f"| {f['region']} | {f['model']} | {f['validationYear']} | {f['trainingCutoff']} | {f['trainRows']} / {f['validationRows']} | {fmt(m['rankIC']['mean'])} | {fmt(m['q5MinusQ1']['mean'])} | {fmt(m['labelCoverage'])} |")
    lines += ["", "## Table C — Primary evidence", "", "| Region / model | Rank IC | 95% HAC CI | SE | p | Dates / effective | Positive folds | Q5-Q1 | Monotonicity |",
              "|---|---:|---|---:|---:|---:|---:|---:|---:|"]
    for key, m in sorted(metrics["primary"].items()):
        ic = m["rankIC"]
        lines.append(f"| {key} | {fmt(ic['mean'])} | {ic['ci95']} | {fmt(ic['se'])} | {fmt(ic['pValue'])} | {ic['dates']} / {ic['effectiveIndependentDates']} | {fmt(m['positiveFoldFraction'])} | {fmt(m['q5MinusQ1']['mean'])} | {fmt(m['monotonicity'])} |")
    lines += ["", "## Quintiles and Top10", "", "| Region / model | Q1–Q5 mean excess | Top10 mean | Median | Positive rate | HAC CI | Top10 minus universe |",
              "|---|---|---:|---:|---:|---|---:|"]
    for key, m in sorted(metrics["primary"].items()):
        top = m["top10Excess"]
        lines.append(f"| {key} | {m['quintileMeans']} | {fmt(top['mean'])} | {fmt(top['median'])} | {fmt(top['positiveBlockRate'])} | {top['ci95']} | {fmt(m['top10MinusUniverse']['mean'])} |")
    lines += ["", "## Table D — Baselines", "", "| Region / method | Rank IC | Q5-Q1 | Top10 excess | Status |", "|---|---:|---:|---:|---|"]
    for key, m in sorted(metrics["baselines"].items()):
        lines.append(f"| {key} | {fmt(m.get('rankIC', {}).get('mean'))} | {fmt(m.get('q5MinusQ1', {}).get('mean'))} | {fmt(m.get('top10Excess', {}).get('mean'))} | {m.get('status', 'MEASURED')} |")
    lines += ["", "## Table E — Model complexity", "", "| Region / model | Features | Annual fits | Training rows across fits (repeated) |", "|---|---:|---:|---:|"]
    for key in sorted(metrics["primary"]):
        fs = [f for f in metrics["annual"] if f['region']+'/'+f['model'] == key]
        lines.append(f"| {key} | {fs[0]['featureCount']} | {len(fs)} | {sum(f['trainRows'] for f in fs)} |")
    lines += ["", f"Ridge: `{M.RIDGE_PARAMS}`; HGBR: `{M.HGBR_PARAMS}`.", "One thread, annual fits, one fixed specification; no random holdout or parameter search.", "",
              "## Table F — Coverage", "", "| Region | Period | Rows | All | Price | Fundamental | Acceleration | FX |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in report["coverage"]:
        lines.append(f"| {r['region']} | {r['period']} | {r['rows']} | {fmt(r['allCoverage'])} | {fmt(r['priceCoverage'])} | {fmt(r['fundamentalCoverage'])} | {fmt(r['accelerationCoverage'])} | {fmt(r['fxCoverage'])} |")
    lines += ["", "## Paired IC differences (HGBR minus comparison)", "", "| Comparison | Mean gap | 95% HAC CI |", "|---|---:|---|"]
    for key, value in sorted(metrics["pairedICComparisons"].items()):
        lines.append(f"| {key} | {fmt(value['mean'])} | {value['ci95']} |")
    lines += ["", "## Required answers", ""]
    for question, answer in report["answers"]:
        lines += [f"**{question}**", "", answer, ""]
    lines += ["## Limitations and dependencies", "", "No future sector or current-market-cap backfill. Unresolved candidates are excluded before outcomes, not deleted after poor performance.",
              "Universe snapshots are observed membership, not exact event dates. Unpriced/departed names and unmatured outcomes remain coverage limitations; no delisting loss is fabricated.",
              "FX publication lineage, as-traded valuation price basis and historical sector data remain unresolved. ECOS fetch/unverified IDs/duplicate series and KR live Yahoo asymmetry are separate production dependencies.",
              "All returns are decimal arithmetic excess at 126D, not annualized portfolio results. Overlapping blocks are not compounded. No production promotion, automatic schedule, or follow-up historical search.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--us-membership", type=Path, default=ROOT/"data/research/regional-alpha-model-v1/us-membership.json.gz")
    args = parser.parse_args(argv)
    ledger, out = args.ledger_dir.resolve(), args.output_dir.resolve()
    if out == ledger or ledger in out.parents or out.exists():
        raise ValueError("output must be a new directory outside sealed inputs")
    out.mkdir(parents=True)
    before = F.digest_tree(ledger)
    print("Stage -1: loading source-verified frozen inputs", flush=True)
    input_manifest, prices, fundamental_store, source_lineage = F.load_inputs(ledger)
    print("auditing raw filing visibility", flush=True)
    vetted, audit = F.vetted_fundamentals(ledger, fundamental_store)
    manifest = F.feature_manifest()
    memberships = F.load_memberships(ledger, args.us_membership)
    print("constructing feature matrix WITHOUT forward labels", flush=True)
    matrix, universe_coverage = F.build_matrix(prices, memberships, vetted, input_manifest["through"], manifest)
    write_json(out/"feature-manifest.json", manifest)
    write_frame(out/"feature-matrix.csv.gz", matrix)
    write_json(out/"universe-coverage.json", universe_coverage)
    frozen_manifest = hashlib.sha256((out/"feature-manifest.json").read_bytes()).hexdigest()
    print(f"FROZEN manifest {frozen_manifest}; {len(matrix)} rows; now constructing labels", flush=True)
    frame = M.join_outcomes(matrix, prices)
    print("fitting independent annual US/KR models", flush=True)
    predictions, folds = M.walk_forward(frame, manifest)
    metrics, daily = M.evaluate(predictions, folds)
    cols = ["region", "date", "ticker", "benchmark", "outcomeJoinId", "method", "validationYear",
            "trainingCutoff", "predictionScore", "rankPercentile", "futureExcess126", "outcomeEndDate"]
    write_frame(out/"oos-predictions.csv.gz", predictions[cols].sort_values(["region", "method", "date", "ticker"]))
    write_json(out/"region-fold-metrics.json", metrics)
    write_json(out/"date-metrics.json", {k: v.reset_index(drop=True).to_dict("records") for k, v in daily.items()})
    after = F.digest_tree(ledger)
    if before != after:
        raise ValueError("SEALED_LEDGER_CHANGED")
    if frozen_manifest != hashlib.sha256((out/"feature-manifest.json").read_bytes()).hexdigest():
        raise ValueError("FEATURE_SPEC_CHANGED_AFTER_OUTCOMES")
    report = dict(version=M.VERSION, evidenceStatus="DISCOVERY_ONLY", promotionEligible=False,
                  productionChanged=False, historicalAlphaDiscoveryPhase="CLOSED",
                  discoveryBudgetConsumed={"US": 1, "KR": 1}, inputCommit=F.INPUT_COMMIT,
                  inputManifestDigest=input_manifest["sha256"], featureManifestDigest=frozen_manifest,
                  usMembershipDigest=hashlib.sha256(args.us_membership.read_bytes()).hexdigest(),
                  sourceLineage=source_lineage, lineageAudit=audit, featureManifest=manifest,
                  coverage=coverage_table(matrix, manifest), missingnessDiagnostic=missingness_diagnostic(predictions),
                  metrics=metrics, versions=dict(sklearn=sklearn.__version__, numpy=np.__version__, pandas=pd.__version__),
                  sealedInvariant=dict(before=before, after=after, unchanged=True),
                  prospectiveEligibleRegions=[r for r, c in metrics["classification"].items()
                                              if c in ("STRONG_DISCOVERY_ONLY", "PROMISING_BUT_UNCERTAIN_DISCOVERY")])
    report["answers"] = answers(report)
    report = clean(report)
    write_json(out/"regional-alpha-model-v1-report.json", report)
    (out/"regional-alpha-model-v1-report.md").write_text(markdown(report), encoding="utf-8")
    write_json(out/"artifact-digests.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()})
    print(json.dumps(metrics["classification"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
