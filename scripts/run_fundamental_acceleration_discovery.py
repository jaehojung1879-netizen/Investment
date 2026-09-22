"""Run the fundamental-acceleration DISCOVERY study, read-only on sealed
replay-v16 inputs (signals, outcomes, and the sealed PIT fundamentals
files).

NOT a portfolio replay: no selection, no valuation, no calendar of rebalance
blocks. This computes a filing-over-filing acceleration composite from
`FundamentalStore`'s existing per-filing history, then the same kind of
cross-sectional Rank IC / Holm / redundancy / stability diagnostics
`four_factor_signal_attribution_audit.py` already established, reused rather
than reimplemented.

Nothing here writes inside the ledger and nothing here changes a factor
weight, selects a portfolio, or promotes a selector.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import fundamental_acceleration as FA                        # noqa: E402
from pipeline import fundamental_acceleration_discovery as D               # noqa: E402
from pipeline import four_factor_signal_attribution_audit as FFA           # noqa: E402
from pipeline import historical_store as HS                                # noqa: E402
from pipeline import pit_data                                              # noqa: E402
from pipeline import provenance                                            # noqa: E402
from pipeline import replay_inputs as RI                                   # noqa: E402


def _guard(path: str, ledger: Path) -> Path:
    target = Path(path).resolve()
    if target == ledger.resolve() or ledger.resolve() in target.parents:
        raise ValueError("research output must remain outside the sealed ledger")
    if target.exists():
        raise FileExistsError("refusing to overwrite existing artifact: " + str(target))
    return target


def _digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            with path.open("rb") as stream:
                digest.update(hashlib.file_digest(stream, "sha256").digest())
    return digest.hexdigest()


def _fmt(value, suffix=""):
    return "n/a" if value is None else f"{value:.4f}{suffix}"


def _ci_str(ci):
    return f"[{_fmt(ci[0])}, {_fmt(ci[1])}]" if ci else "[n/a, n/a]"


def answers(*, coverage: dict, orthogonality: dict, standalone: dict, incremental: dict,
           holm: dict, region: dict, half: dict, quintile: dict, quality_conditional: dict,
           classification: dict, secondary_tables: dict) -> list[dict]:
    sp, ip = standalone["pooled"], incremental["pooled"]
    q_cells = "; ".join(
        f"{k}: high-low={_fmt(v['difference'])} (n={v['observations']})"
        for k, v in sorted(quality_conditional.items()))
    return [
        {"q": "Q1. Is the two-consecutive-filing PIT construction computable on real data, "
              "and at what overall coverage?",
         "a": f"Data-sufficient coverage ratio {_fmt(coverage['overall']['dataSufficientRatio'])} "
              f"over {coverage['overall']['total']} signal name-dates "
              f"({'MEETS' if coverage['meetsMinCoverageRatio'] else 'BELOW'} the pre-registered "
              f"{D.MIN_COVERAGE_RATIO} minimum). Status breakdown: {coverage['overall']['byStatus']}."},
        {"q": "Q2. How does coverage split by region and by chronological half?",
         "a": "By region: " +
              "; ".join(f"{r}: {_fmt(v['dataSufficientRatio'])}"
                       for r, v in sorted(coverage["byRegion"].items())) +
              ". By half: first "
              f"{_fmt(coverage['byTimeHalf'].get('firstHalf', {}).get('dataSufficientRatio'))}, "
              f"second {_fmt(coverage['byTimeHalf'].get('secondHalf', {}).get('dataSufficientRatio'))}."},
        {"q": "Q3. Which of the four primary fields (roe, operatingMargin, profitMargin, "
              "earningsGrowth) most limits coverage among OK consecutive-filing pairs?",
         "a": "; ".join(f"{field}: {_fmt(v['presentPct'], '%')}"
                        for field, v in sorted(coverage["byField"].items()))},
        {"q": "Q4. Is the acceleration composite genuinely distinct information from the "
              "existing Quality LEVEL factor, or a relabelling of it?",
         "a": f"Pooled Spearman(accelerationPercentile, qualityPercentile) = "
              f"{_fmt(orthogonality['qualityAbsRho'])} "
              f"({'FAILS' if orthogonality['failsRedundancy'] else 'PASSES'} the pre-registered "
              f"|rho| < {D.MAX_ORTHOGONALITY_ABS_RHO} redundancy threshold)."},
        {"q": "Q5. How does the acceleration composite correlate with the other three existing "
              "sleeves (momentum, value, lowvol), descriptively?",
         "a": "; ".join(f"{k}: {_fmt(v['meanSpearman'])}"
                        for k, v in sorted(orthogonality["byFactor"].items()) if k != "quality")},
        {"q": f"Q6. What is the standalone pooled-within-region Rank IC at the primary "
              f"{D.PRIMARY_HORIZON}D horizon, with its 95% CI and Holm-adjusted p-value?",
         "a": f"mean {_fmt(sp.get('mean'))}, CI {_ci_str(sp.get('ci95'))}, raw p "
              f"{_fmt(sp.get('rawPValue'))}, Holm p {_fmt(holm.get('standalone'))}."},
        {"q": "Q7. What is the incremental Rank IC once Quality's own level is residualized "
              "out (single-predictor regression, Quality alone), with its 95% CI and "
              "Holm-adjusted p-value?",
         "a": f"mean {_fmt(ip.get('mean'))}, CI {_ci_str(ip.get('ci95'))}, raw p "
              f"{_fmt(ip.get('rawPValue'))}, Holm p {_fmt(holm.get('incremental'))}."},
        {"q": "Q8. Do KR and US agree in direction on the standalone Rank IC?",
         "a": f"{region['signsByRegion']} -- {'AGREE' if region['agree'] else region['label']}."},
        {"q": "Q9. Does the direction persist across a fixed chronological half-split of the "
              "sample?",
         "a": f"first half mean {_fmt((half.get('firstHalf') or {}).get('mean'))}, "
              f"second half mean {_fmt((half.get('secondHalf') or {}).get('mean'))} -- "
              f"{'AGREE' if half.get('agree') else half.get('label')}."},
        {"q": "Q10. Is the primary-horizon relationship monotone across acceleration quintiles?",
         "a": f"quintile means {quintile['quintileMeans']}, monotonicity "
              f"{_fmt(quintile['monotonicityScore'])}, Q5-Q1 {_fmt(quintile['q5MinusQ1'])}."},
        {"q": "Q11. Within a fixed Quality-percentile quintile, does a median-split on "
              "acceleration separate forward excess return (descriptive only, no score, "
              "ranking or rule)?",
         "a": q_cells or "insufficient cross-sections to compute"},
        {"q": "Q12. What is the overall outcome classification, and what does this study "
              "recommend next?",
         "a": f"{classification['case']} -- {classification['rationale']} "
              "Per design, a favourable reading here is discovery-stage evidence only; "
              "confirmatory validation is reserved for the prospective sealed window, "
              "never for a same-sample re-tune of this composite."},
    ]


def markdown(report: dict) -> str:
    cov, orth = report["coverage"], report["orthogonality"]
    standalone, incremental = report["standalone"], report["incremental"]
    lines = [
        "# Fundamental-acceleration discovery v1", "",
        "> Read-only research DISCOVERY study on sealed replay-v16 inputs. No factor",
        "> weight is changed, no portfolio is selected or valued, no threshold is tuned",
        "> after seeing a result. `promotionEligible: false`, production unchanged.", "",
        "## Coverage (Stage A)", "",
        f"Overall data-sufficient ratio: **{_fmt(cov['overall']['dataSufficientRatio'])}** "
        f"over {cov['overall']['total']} name-dates "
        f"({'PASS' if cov['meetsMinCoverageRatio'] else 'FAIL'}, threshold "
        f"{D.MIN_COVERAGE_RATIO}).", "",
        "| Region | Total | Data-sufficient | Ratio |", "|---|---:|---:|---:|",
    ]
    for region, row in sorted(cov["byRegion"].items()):
        lines.append(f"| {region} | {row['total']} | {row['dataSufficient']} | "
                     f"{_fmt(row['dataSufficientRatio'])} |")
    lines += ["", "| Field | Present among OK filing pairs |", "|---|---:|"]
    for field, row in sorted(cov["byField"].items()):
        lines.append(f"| {field} | {_fmt(row['presentPct'], '%')} |")

    lines += ["", "## Orthogonality vs. existing sleeves (Stage B)", "",
              f"|rho| vs Quality: **{_fmt(orth['qualityAbsRho'])}** "
              f"({'FAILS' if orth['failsRedundancy'] else 'PASSES'} the "
              f"{D.MAX_ORTHOGONALITY_ABS_RHO} redundancy threshold).", "",
              "| Factor | Mean Spearman |", "|---|---:|"]
    for key, row in sorted(orth["byFactor"].items()):
        lines.append(f"| {key} | {_fmt(row['meanSpearman'])} |")

    dd = report["debtAccelerationDiagnostic"]
    lines += ["", "## Debt-to-equity acceleration (diagnostic only, never scored)", "",
              f"Non-exempt observations: {dd['nonExemptObservations']}, exempt masked: "
              f"{dd['exemptObservationsMasked']}, mean delta (non-exempt): "
              f"{_fmt(dd['meanDeltaDebtToEquityNonExempt'])}. Exempt sectors: "
              f"{', '.join(dd['exemptSectors'])}."]

    lines += ["", f"## Primary discovery statistics ({D.PRIMARY_HORIZON}D)", "",
              "| Statistic | Mean | 95% CI | Raw p | Holm p |",
              "|---|---:|---:|---:|---:|",
              f"| Standalone Rank IC | {_fmt(standalone['pooled'].get('mean'))} | "
              f"{_ci_str(standalone['pooled'].get('ci95'))} | "
              f"{_fmt(standalone['pooled'].get('rawPValue'))} | "
              f"{_fmt(report['holm'].get('standalone'))} |",
              f"| Incremental Rank IC (beyond Quality) | "
              f"{_fmt(incremental['pooled'].get('mean'))} | "
              f"{_ci_str(incremental['pooled'].get('ci95'))} | "
              f"{_fmt(incremental['pooled'].get('rawPValue'))} | "
              f"{_fmt(report['holm'].get('incremental'))} |"]

    lines += ["", "## Region stability", "",
              f"{report['regionStability']['signsByRegion']} -- "
              f"{'AGREE' if report['regionStability']['agree'] else report['regionStability']['label']}",
              "", "## Time stability (fixed chronological half-split)", "",
              f"First half mean {_fmt((report['halfStability'].get('firstHalf') or {}).get('mean'))}, "
              f"second half mean {_fmt((report['halfStability'].get('secondHalf') or {}).get('mean'))} -- "
              f"{'AGREE' if report['halfStability'].get('agree') else report['halfStability'].get('label')}"]

    lines += ["", "## Quintile table (pooled)", "",
              "| Q1 | Q2 | Q3 | Q4 | Q5 | Monotonicity | Q5-Q1 |",
              "|---:|---:|---:|---:|---:|---:|---:|",
              "| " + " | ".join(_fmt(m) for m in report["quintile"]["quintileMeans"]) +
              f" | {_fmt(report['quintile'].get('monotonicityScore'))} | "
              f"{_fmt(report['quintile'].get('q5MinusQ1'))} |"]

    lines += ["", "## Quality-level-conditional (descriptive only)", "",
              "| Quality quintile | High-accel mean excess | Low-accel mean excess | Diff | n |",
              "|---|---:|---:|---:|---:|"]
    for key, row in sorted(report["qualityConditional"].items()):
        lines.append(f"| {key} | {_fmt(row['highAccelerationMeanExcess'])} | "
                     f"{_fmt(row['lowAccelerationMeanExcess'])} | {_fmt(row['difference'])} | "
                     f"{row['observations']} |")

    lines += ["", "## Secondary horizons (descriptive only, never promoted to primary)", "",
              "| Horizon | Standalone pooled IC |", "|---|---:|"]
    for horizon in D.SECONDARY_HORIZONS:
        row = report["secondaryHorizonTables"].get(str(horizon), {})
        lines.append(f"| {horizon}D | {_fmt(row.get('pooled', {}).get('mean'))} |")

    lines += ["", "## Classification (Q1-Q12)", "",
              f"**{report['classification']['case']}**", "",
              report['classification']['rationale'], ""]
    for item in report["answers"]:
        lines += [f"**{item['q']}**", "", item["a"], ""]

    lines += ["## What this study does NOT establish", "",
              "- Not a promotion. `promotionEligible` is false; no factor weight is changed,",
              "  no portfolio is selected or valued.",
              "- No threshold, window, or field was tuned after seeing a result -- the",
              "  composite formula, the primary horizon, and the 0.60/0.70 thresholds were",
              "  all fixed by `docs/challenger-2-fundamental-acceleration-v1-design.md` before",
              "  this module was written.",
              "- Confirmatory evidence is reserved for the prospective sealed window; a",
              "  favourable historical reading here is DISCOVERY-STAGE evidence only.",
              "- This ledger has been used by eleven prior studies; this result is DISCOVERY",
              "  / DIAGNOSTIC EVIDENCE, never final out-of-sample validation.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default="fundamental-acceleration-discovery-report.json")
    parser.add_argument("--markdown", default="fundamental-acceleration-discovery-report.md")
    args = parser.parse_args(argv)
    ledger = Path(args.ledger_dir)
    output, md = _guard(args.output, ledger), _guard(args.markdown, ledger)
    before = _digest_tree(ledger)

    store_manifest = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store_manifest.manifest()
    if not manifest or provenance.REPLAY_VERSION != "replay-v16":
        raise ValueError("fundamental-acceleration-discovery-v1 requires sealed replay-v16 inputs")
    sealed = json.loads((ledger / "historical-portfolio-validation.json").read_text())
    if sealed.get("inputSnapshot", {}).get("sha256") != manifest["sha256"]:
        raise ValueError("sealed report and frozen inputs have different lineage")

    print("loading projected sealed signals and outcomes", flush=True)
    signals = HS.load(ledger, HS.SIGNALS, provenance.REPLAY_VERSION, project=HS.audit_projection)
    outcomes = HS.load(ledger, HS.OUTCOMES, provenance.REPLAY_VERSION)
    print(f"{len(signals)} signals, {len(outcomes)} outcomes", flush=True)

    print("loading sealed PIT fundamentals store", flush=True)
    fundamentals_dir = ledger / "fundamentals"
    fund_store = pit_data.FundamentalStore.from_many([
        fundamentals_dir / "pit-kr.jsonl", fundamentals_dir / "pit-us.jsonl"])
    print(f"fundamentals store: {len(fund_store)} filings across "
         f"{len(fund_store.tickers())} tickers, diagnostics={fund_store.diagnostics}",
         flush=True)

    print("computing acceleration readings for every signal name-date", flush=True)
    readings = D.build_readings(signals, fund_store)
    print(f"{len(readings)} readings built", flush=True)

    print("building the cross-sectional acceleration composite", flush=True)
    readings = D.build_composite(readings)

    print("Stage A: coverage", flush=True)
    coverage = D.coverage_table(readings)

    print("Stage B: orthogonality", flush=True)
    orthogonality = D.orthogonality_table(readings)

    print("debt-to-equity acceleration diagnostic (sector-exempt, never scored)", flush=True)
    debt_diagnostic = D.debt_acceleration_diagnostic(readings)

    print(f"building the primary {D.PRIMARY_HORIZON}D outcome frame", flush=True)
    primary_frame = D.build_outcome_frame(readings, outcomes, D.PRIMARY_HORIZON)
    if primary_frame.empty:
        raise ValueError("no matured primary-horizon observations in the sealed ledger")

    print("standalone and incremental Rank IC", flush=True)
    standalone = D.standalone_ic_summary(primary_frame, D.PRIMARY_HORIZON)
    incremental = D.incremental_ic_summary(primary_frame, D.PRIMARY_HORIZON)
    holm = FFA.holm_bonferroni({
        "standalone": standalone["pooled"].get("rawPValue"),
        "incremental": incremental["pooled"].get("rawPValue"),
    })

    print("quintile / region stability / time stability / quality-conditional", flush=True)
    quintile = D.quintile_table(primary_frame)
    region_stability = D.region_stability(standalone)
    half_stability = D.half_split_stability(primary_frame, D.PRIMARY_HORIZON)
    quality_conditional = D.quality_conditional_table(primary_frame)

    print("classification", flush=True)
    classification = D.classify_outcome(
        coverage=coverage, orthogonality=orthogonality,
        standalone_pooled=standalone["pooled"], incremental_pooled=incremental["pooled"])

    secondary_horizon_tables = {}
    for horizon in D.SECONDARY_HORIZONS:
        print(f"secondary horizon {horizon}D (descriptive only)", flush=True)
        frame = D.build_outcome_frame(readings, outcomes, horizon)
        secondary_horizon_tables[str(horizon)] = (
            D.standalone_ic_summary(frame, horizon) if not frame.empty
            else {"pooled": {"mean": None}})

    report = {
        "version": D.VERSION, "status": "DISCOVERY", "promotionEligible": False,
        "productionChanged": False,
        "inputSnapshot": {"sha256": manifest["sha256"], "through": manifest["through"]},
        "primaryHorizon": D.PRIMARY_HORIZON,
        "secondaryHorizons": list(D.SECONDARY_HORIZONS),
        "fundamentalsStoreDiagnostics": fund_store.diagnostics,
        "totalReadings": len(readings),
        "coverage": coverage,
        "orthogonality": orthogonality,
        "debtAccelerationDiagnostic": debt_diagnostic,
        "standalone": standalone,
        "incremental": incremental,
        "holm": holm,
        "quintile": quintile,
        "regionStability": region_stability,
        "halfStability": half_stability,
        "qualityConditional": quality_conditional,
        "classification": classification,
        "secondaryHorizonTables": secondary_horizon_tables,
        "confirmatoryFamily": {
            "primaryHorizon": D.PRIMARY_HORIZON,
            "hypotheses": ["standalone", "incremental"],
            "statistic": "POOLED_WITHIN_REGION_126D_RANK_IC",
            "correction": "HOLM_BONFERRONI",
        },
        "composite": {
            "primaryFields": list(FA.PRIMARY_FIELDS),
            "diagnosticFields": list(FA.DIAGNOSTIC_FIELDS),
            "minPrimaryFields": FA.MIN_PRIMARY_FIELDS,
            "winsor": FA.WINSOR,
            "normalization": "longterm.sector_neutral_z, per (date, region)",
        },
        "researchHistoryContamination": (
            "replay-v16 has been used by eleven prior CHALLENGER studies on this ledger. "
            "This result is DISCOVERY / DIAGNOSTIC EVIDENCE, not FINAL OUT-OF-SAMPLE "
            "VALIDATION, and is not used as production promotion evidence regardless of "
            "how favourable any single reading looks. Confirmatory validation is reserved "
            "for the prospective sealed signal window."),
        "sealedInvariant": {"before": before, "after": _digest_tree(ledger)},
    }
    report["sealedInvariant"]["unchanged"] = (
        report["sealedInvariant"]["before"] == report["sealedInvariant"]["after"])
    if not report["sealedInvariant"]["unchanged"]:
        raise ValueError("SEALED_LEDGER_CHANGED")
    report["answers"] = answers(
        coverage=coverage, orthogonality=orthogonality, standalone=standalone,
        incremental=incremental, holm=holm, region=region_stability, half=half_stability,
        quintile=quintile, quality_conditional=quality_conditional,
        classification=classification, secondary_tables=secondary_horizon_tables)

    output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 allow_nan=False, sort_keys=True) + "\n")
    md.write_text(markdown(report))
    print(markdown(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
