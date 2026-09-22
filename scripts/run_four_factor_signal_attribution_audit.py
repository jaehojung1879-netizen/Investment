"""Run the four-factor signal attribution audit, read-only on sealed inputs.

NOT a portfolio replay: no selection, no valuation, no calendar of rebalance
blocks. This computes cross-sectional Rank IC between each production alpha
sleeve (and, where the sealed ledger stores it, a raw subfactor input) and
matured benchmark-relative forward returns, directly from
`historical-store` signals/outcomes.

Nothing here writes inside the ledger and nothing here changes a factor
weight, builds a new Alpha formula, or promotes a selector.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import four_factor_signal_attribution_audit as C   # noqa: E402
from pipeline import historical_store as HS                      # noqa: E402
from pipeline import longterm as LT                               # noqa: E402
from pipeline import provenance                                   # noqa: E402
from pipeline import replay_inputs as RI                          # noqa: E402


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


def _sign_label(mean) -> str | None:
    return C._sign(mean)


# --------------------------------------------------------------------------- #
# Per-region / pooled secondary diagnostics for one horizon
# --------------------------------------------------------------------------- #
def secondary_diagnostics(frame, horizon: int) -> dict:
    regions = sorted(frame["region"].dropna().unique())
    per_region_artifacts = {region: C.cross_section_pass(frame, region) for region in regions}

    redundancy = {
        region: C.redundancy_matrix(artifacts["corrFrames"])
        for region, artifacts in per_region_artifacts.items()
    }
    pooled_corr_frames = [f for artifacts in per_region_artifacts.values()
                          for f in artifacts["corrFrames"]]
    redundancy["pooled"] = C.redundancy_matrix(pooled_corr_frames)

    quintile = {
        region: C.quintile_monotonicity_table(artifacts["quintileMeans"])
        for region, artifacts in per_region_artifacts.items()
    }
    pooled_quintile_means = {sleeve: [[] for _ in range(5)] for sleeve in C.SLEEVES}
    for artifacts in per_region_artifacts.values():
        for sleeve in C.SLEEVES:
            for bucket_idx, values in enumerate(artifacts["quintileMeans"][sleeve]):
                pooled_quintile_means[sleeve][bucket_idx].extend(values)
    quintile["pooled"] = C.quintile_monotonicity_table(pooled_quintile_means)

    # Incremental IC and quartile spread go through the HAC estimator, so
    # "pooled" here means the SAME inverse-variance combination of two
    # independently-estimated regional summaries `pool_region_summaries`
    # already uses for the primary metric -- never a merged raw series.
    incremental_by_region = {
        region: C.incremental_ic_table(artifacts["incrementalRows"], horizon)
        for region, artifacts in per_region_artifacts.items()
    }
    incremental = {sleeve: {"byRegion": {region: incremental_by_region[region][sleeve]
                                         for region in regions}}
                  for sleeve in C.SLEEVES}
    for sleeve in C.SLEEVES:
        incremental[sleeve]["pooled"] = C.pool_region_summaries(
            {region: incremental[sleeve]["byRegion"][region] for region in regions})

    quartile_by_region = {
        region: C.quartile_spread_table(artifacts["quartileRows"], horizon)
        for region, artifacts in per_region_artifacts.items()
    }
    quartile = {sleeve: {"byRegion": {region: quartile_by_region[region][sleeve]
                                      for region in regions}}
               for sleeve in C.SLEEVES}
    for sleeve in C.SLEEVES:
        quartile[sleeve]["pooled"] = C.pool_region_summaries(
            {region: quartile[sleeve]["byRegion"][region] for region in regions})

    return {"redundancy": redundancy, "quintileMonotonicity": quintile,
            "incrementalIC": incremental, "quartileSpread": quartile}


# --------------------------------------------------------------------------- #
# Time stability -- one chronological split, fixed once on the primary frame
# --------------------------------------------------------------------------- #
def time_stability_report(frame, horizon: int) -> dict:
    first_dates, second_dates = C.half_split_dates(frame)
    regions = sorted(frame["region"].dropna().unique())
    out: dict[str, dict] = {}
    for sleeve in C.SLEEVES:
        out[sleeve] = {}
        for region in regions:
            standalone = C.half_sample_ic(frame, region, sleeve, first_dates, second_dates, horizon)
            first_frame = frame[frame["date"].isin(first_dates)]
            second_frame = frame[frame["date"].isin(second_dates)]
            first_art = C.cross_section_pass(first_frame, region)
            second_art = C.cross_section_pass(second_frame, region)
            incremental_first = C.incremental_ic_table(first_art["incrementalRows"], horizon)[sleeve]
            incremental_second = C.incremental_ic_table(second_art["incrementalRows"], horizon)[sleeve]
            quartile_first = C.quartile_spread_table(first_art["quartileRows"], horizon)[sleeve]
            quartile_second = C.quartile_spread_table(second_art["quartileRows"], horizon)[sleeve]
            out[sleeve][region] = {
                "standaloneFirstHalf": standalone["firstHalf"],
                "standaloneSecondHalf": standalone["secondHalf"],
                "standaloneSignFirst": _sign_label(standalone["firstHalf"].get("mean")),
                "standaloneSignSecond": _sign_label(standalone["secondHalf"].get("mean")),
                "incrementalFirstHalf": incremental_first,
                "incrementalSecondHalf": incremental_second,
                "quartileSpreadFirstHalf": quartile_first,
                "quartileSpreadSecondHalf": quartile_second,
            }
    return {"firstHalfDates": [str(d) for d in (first_dates[:1] + first_dates[-1:])]
                              if first_dates else [],
            "secondHalfDates": [str(d) for d in (second_dates[:1] + second_dates[-1:])]
                               if second_dates else [],
            "bySleeveRegion": out}


# --------------------------------------------------------------------------- #
# Classification (section 15) -- built from the primary-horizon pooled and
# region readings plus the time-stability signs
# --------------------------------------------------------------------------- #
def classification_report(primary_table: dict, secondary: dict, stability: dict) -> dict:
    out = {}
    for sleeve in C.SLEEVES:
        standalone_pooled = primary_table[sleeve]["pooled"]
        incremental_pooled = secondary["incrementalIC"][sleeve]["pooled"]
        region_signs = [_sign_label(row.get("mean"))
                        for row in primary_table[sleeve]["byRegion"].values()]
        half_signs = []
        for region_data in stability[sleeve].values():
            half_signs.append(region_data["standaloneSignFirst"])
            half_signs.append(region_data["standaloneSignSecond"])
        out[sleeve] = C.classify_sleeve(
            standalone_pooled=standalone_pooled, incremental_pooled=incremental_pooled,
            region_signs=region_signs, half_signs=half_signs)
    return out


# --------------------------------------------------------------------------- #
# Answers to the pre-registered Q1-Q10
# --------------------------------------------------------------------------- #
def answers(primary_table: dict, holm: dict, secondary: dict, classification: dict,
           stability: dict, redundancy_pooled: dict) -> list[dict]:
    def pooled_mean_ci(sleeve):
        row = primary_table[sleeve]["pooled"]
        ci = row.get("ci95")
        return row.get("mean"), ci

    q1_lines = []
    for sleeve in C.SLEEVES:
        mean, ci = pooled_mean_ci(sleeve)
        q1_lines.append(f"{sleeve}: pooled 126D IC {_fmt(mean)} "
                        f"[{_fmt(ci[0]) if ci else 'n/a'}, {_fmt(ci[1]) if ci else 'n/a'}]")
    q2_lines = []
    for sleeve in C.SLEEVES:
        raw_p = primary_table[sleeve]["pooled"].get("rawPValue")
        holm_p = holm.get(sleeve)
        q2_lines.append(f"{sleeve}: raw p={_fmt(raw_p)}, Holm-adjusted p={_fmt(holm_p)}")
    q3 = ("Redundancy matrix (pooled, mean pairwise Spearman): " +
         ", ".join(f"{a}-{b} {_fmt((redundancy_pooled.get('matrix') or {}).get(a, {}).get(b, {}).get('mean'))}"
                  for i, a in enumerate(C.SLEEVES) for b in C.SLEEVES[i + 1:]))
    q4_lines = []
    for sleeve in C.SLEEVES:
        standalone = primary_table[sleeve]["pooled"].get("mean")
        incremental = secondary["incrementalIC"][sleeve]["pooled"].get("mean")
        q4_lines.append(f"{sleeve}: standalone {_fmt(standalone)} vs incremental {_fmt(incremental)}")
    q5_lines = []
    for sleeve in C.SLEEVES:
        by_region = primary_table[sleeve]["byRegion"]
        signs = {region: _sign_label(row.get("mean")) for region, row in by_region.items()}
        q5_lines.append(f"{sleeve}: {signs}")
    q6_lines = []
    for sleeve in C.SLEEVES:
        first_signs = {region: data["standaloneSignFirst"] for region, data in stability[sleeve].items()}
        second_signs = {region: data["standaloneSignSecond"] for region, data in stability[sleeve].items()}
        q6_lines.append(f"{sleeve}: first-half {first_signs}, second-half {second_signs}")

    return [
        {"q": "Q1. Which sleeves show a standalone relationship with forward benchmark excess?",
         "a": "; ".join(q1_lines)},
        {"q": "Q2. What survives Holm multiple-testing correction across the primary four-sleeve family?",
         "a": "; ".join(q2_lines) + ". Correction applied over exactly these 4 pooled-126D p-values."},
        {"q": "Q3. Which sleeves are redundant with each other?", "a": q3},
        {"q": "Q4. Does any sleeve carry positive incremental information once the other three are controlled for?",
         "a": "; ".join(q4_lines)},
        {"q": "Q5. Do KR and US agree in direction?", "a": "; ".join(q5_lines)},
        {"q": "Q6. Does the direction persist across the first/second half of the sample?",
         "a": "; ".join(q6_lines)},
        {"q": "Q7. Do the two momentum inputs (12-1M, 6M) carry different information?",
         "a": "PIT_NOT_AVAILABLE -- the sealed ledger never stored the raw 12-1M/6M momentum "
              "inputs, only the blended momentum sleeve percentile. Not substituted with "
              "mom20Pct/mom60Pct, which are a different feature."},
        {"q": "Q8. How redundant are the value inputs (trailing/forward earnings yield, book yield, FCF yield)?",
         "a": "PIT_NOT_AVAILABLE -- no raw value input is stored on the sealed signal record."},
        {"q": "Q9. Does Quality mix offsetting profitability/growth/balance-sheet signals?",
         "a": "PIT_NOT_AVAILABLE -- no raw quality input is stored on the sealed signal record."},
        {"q": "Q10. Is the composite's weak discrimination best explained by uniformly weak sleeves, "
              "a mix of good and bad sleeves, excessive redundancy, or PIT coverage limits?",
         "a": ("Classification per sleeve: " +
               "; ".join(f"{sleeve}={classification[sleeve]['case']}" for sleeve in C.SLEEVES) +
               f". Redundancy: momentum-value mean pairwise Spearman "
               f"{_fmt((redundancy_pooled.get('matrix') or {}).get('momentum', {}).get('value', {}).get('mean'))}, "
               "momentum-lowvol "
               f"{_fmt((redundancy_pooled.get('matrix') or {}).get('momentum', {}).get('lowvol', {}).get('mean'))}. "
               "Subfactor-level attribution (which would separate 'sleeve is weak' from 'sleeve mixes a "
               "good and a bad input') is PIT_NOT_AVAILABLE for three of the four sleeves.")},
    ]


def markdown(report: dict) -> str:
    primary = report["primaryTable"]
    lines = [
        "# Four-factor signal attribution audit v1", "",
        "> Read-only research AUDIT on sealed replay-v16 inputs. No factor weight is",
        "> changed, no combination is searched, no new Alpha formula is built from this",
        "> sample, and no portfolio is selected or valued anywhere in this study.",
        "> `promotionEligible: false`, production unchanged.", "",
        "## Provenance inventory (Stage 0, measured before any statistic was computed)",
        "",
        "| Sleeve | Sealed-ledger coverage |", "|---|---:|",
    ]
    for sleeve in C.SLEEVES:
        pct = report["provenance"]["sleeveLevel"][sleeve]["presentPct"]
        lines.append(f"| {sleeve} | {_fmt(pct, '%')} |")
    lines += ["", "| Subfactor | Status |", "|---|---|"]
    for sleeve, names in C.SUBFACTOR_CANDIDATES.items():
        for name in names:
            status = report["provenance"]["subfactorLevel"][sleeve][name]["status"]
            lines.append(f"| {sleeve}.{name} | {status} |")
    lines += ["", report["provenance"]["note"], ""]

    lines += ["## Primary output table -- 126D pooled Rank IC (Holm-corrected)", "",
              "| Sleeve | Weight | 126D Rank IC | 95% CI | Raw p | Holm p | Incremental IC | "
              "KR sign | US sign | Coverage |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for sleeve in C.SLEEVES:
        row = primary[sleeve]["pooled"]
        ci = row.get("ci95") or [None, None]
        incremental = report["secondary"]["incrementalIC"][sleeve]["pooled"].get("mean")
        by_region = primary[sleeve]["byRegion"]
        kr_sign = _sign_label((by_region.get("KR") or {}).get("mean"))
        us_sign = _sign_label((by_region.get("US") or {}).get("mean"))
        cov = report["coverage"].get("US", {}).get(sleeve, {}).get("missingRatePct")
        lines.append(
            f"| {sleeve} | {LT.FACTOR_WEIGHTS.get(sleeve)} | {_fmt(row.get('mean'))} | "
            f"[{_fmt(ci[0])}, {_fmt(ci[1])}] | {_fmt(row.get('rawPValue'))} | "
            f"{_fmt(report['holm'].get(sleeve))} | {_fmt(incremental)} | {kr_sign} | {us_sign} | "
            f"{_fmt(100 - cov if cov is not None else None, '%')} |")

    lines += ["", "## Subfactor output table", "", "| Sleeve | Input | Status |", "|---|---|---|"]
    for sleeve, names in C.SUBFACTOR_CANDIDATES.items():
        for name in names:
            status = report["provenance"]["subfactorLevel"][sleeve][name]["status"]
            lines.append(f"| {sleeve} | {name} | {status} |")

    lines += ["", "## Redundancy matrix (pooled, time-averaged pairwise Spearman)", "",
              "| | " + " | ".join(C.SLEEVES) + " |", "|---|" + "---:|" * len(C.SLEEVES)]
    matrix = report["secondary"]["redundancy"]["pooled"].get("matrix") or {}
    for a in C.SLEEVES:
        lines.append(f"| {a} | " +
                    " | ".join(_fmt((matrix.get(a) or {}).get(b, {}).get("mean")) for b in C.SLEEVES) + " |")

    lines += ["", "## Quintile monotonicity (pooled)", "",
              "| Sleeve | Q1 | Q2 | Q3 | Q4 | Q5 | Monotonicity | Q5-Q1 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for sleeve in C.SLEEVES:
        row = report["secondary"]["quintileMonotonicity"]["pooled"][sleeve]
        means = row["quintileMeans"]
        lines.append(f"| {sleeve} | " + " | ".join(_fmt(m) for m in means) +
                    f" | {_fmt(row.get('monotonicityScore'))} | {_fmt(row.get('q5MinusQ1'))} |")

    lines += ["", "## Classification (descriptive only, section 15)", "",
              "| Sleeve | Case | Rationale |", "|---|---|---|"]
    for sleeve in C.SLEEVES:
        row = report["classification"][sleeve]
        lines.append(f"| {sleeve} | {row['case']} | {row['rationale']} |")

    lines += ["", "## EvidenceCoverage audit (descriptive, not primary confirmatory)", "",
              f"rawAlpha vs alpha rank Spearman: "
              f"{_fmt(report['evidenceCoverageAudit']['rawAlphaVsAlphaRankSpearman']['mean'])}", "",
              f"evidenceCoverage distribution: mean "
              f"{_fmt(report['evidenceCoverageAudit']['evidenceCoverageDistribution']['mean'])}, "
              f"sd {_fmt(report['evidenceCoverageAudit']['evidenceCoverageDistribution']['sd'])}", ""]

    lines += ["## Secondary horizons (descriptive only, never promoted to primary)", "",
              "| Sleeve | 21D pooled IC | 63D pooled IC | 252D pooled IC |",
              "|---|---:|---:|---:|"]
    for sleeve in C.SLEEVES:
        row = " | ".join(_fmt(report["secondaryHorizonTables"][h][sleeve]["pooled"].get("mean"))
                         for h in C.SECONDARY_HORIZONS)
        lines.append(f"| {sleeve} | {row} |")

    lines += ["", "## Q1-Q10", ""]
    for item in report["answers"]:
        lines += [f"**{item['q']}**", "", item["a"], ""]

    lines += ["## What this study does NOT establish", "",
              "- Not a promotion. `promotionEligible` is false; no factor weight is changed.",
              "- No new Alpha formula is built from this sample; the classification is",
              "  descriptive and is never used to recommend removing a sleeve on its own.",
              "- Subfactor-level attribution is PIT_NOT_AVAILABLE for momentum, value and",
              "  quality -- only lowvol's single raw input (vol252) is stored on the sealed",
              "  ledger.",
              "- This ledger has been used by ten prior studies; this result is DISCOVERY /",
              "  DIAGNOSTIC EVIDENCE, never final out-of-sample validation.", "",
              "## Proposed next research (NOT executed here)", ""]
    lines += report["nextResearchProposals"]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default="four-factor-signal-attribution-audit-report.json")
    parser.add_argument("--markdown", default="four-factor-signal-attribution-audit-report.md")
    args = parser.parse_args(argv)
    ledger = Path(args.ledger_dir)
    output, md = _guard(args.output, ledger), _guard(args.markdown, ledger)
    before = _digest_tree(ledger)

    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if not manifest or provenance.REPLAY_VERSION != "replay-v16":
        raise ValueError("four-factor-signal-attribution-audit-v1 requires sealed replay-v16 inputs")
    sealed = json.loads((ledger / "historical-portfolio-validation.json").read_text())
    if sealed.get("inputSnapshot", {}).get("sha256") != manifest["sha256"]:
        raise ValueError("sealed report and frozen inputs have different lineage")

    print("loading projected sealed signals and outcomes", flush=True)
    signals = HS.load(ledger, HS.SIGNALS, provenance.REPLAY_VERSION, project=HS.audit_projection)
    outcomes = HS.load(ledger, HS.OUTCOMES, provenance.REPLAY_VERSION)
    print(f"{len(signals)} signals, {len(outcomes)} outcomes", flush=True)

    print("Stage 0: provenance inventory", flush=True)
    prov = C.provenance_inventory(signals)

    print(f"building the primary {C.PRIMARY_HORIZON}D frame", flush=True)
    primary_frame = C.build_frame(signals, outcomes, C.PRIMARY_HORIZON)
    if primary_frame.empty:
        raise ValueError("no matured primary-horizon observations in the sealed ledger")

    print("primary sleeve IC table", flush=True)
    primary_table = C.sleeve_ic_table(primary_frame, C.PRIMARY_HORIZON)
    holm = C.holm_bonferroni(
        {sleeve: primary_table[sleeve]["pooled"].get("rawPValue") for sleeve in C.SLEEVES})

    print("secondary diagnostics (redundancy, incremental IC, quartile, quintile)", flush=True)
    secondary = secondary_diagnostics(primary_frame, C.PRIMARY_HORIZON)

    print("time stability (fixed chronological half-split)", flush=True)
    stability = time_stability_report(primary_frame, C.PRIMARY_HORIZON)

    print("classification", flush=True)
    classification = classification_report(primary_table, secondary, stability["bySleeveRegion"])

    print("evidence coverage audit", flush=True)
    evidence_audit = C.evidence_coverage_audit(primary_frame)

    coverage = C.coverage_report(primary_frame)

    secondary_horizon_tables = {}
    for horizon in C.SECONDARY_HORIZONS:
        print(f"secondary horizon {horizon}D (descriptive only)", flush=True)
        frame = C.build_frame(signals, outcomes, horizon)
        secondary_horizon_tables[horizon] = (
            C.sleeve_ic_table(frame, horizon) if not frame.empty
            else {sleeve: {"pooled": {"mean": None}} for sleeve in C.SLEEVES})

    report = {
        "version": C.VERSION, "status": "AUDIT", "promotionEligible": False,
        "productionChanged": False,
        "inputSnapshot": {"sha256": manifest["sha256"], "through": manifest["through"]},
        "primaryHorizon": C.PRIMARY_HORIZON,
        "secondaryHorizons": list(C.SECONDARY_HORIZONS),
        "provenance": prov,
        "primaryTable": primary_table,
        "holm": holm,
        "secondary": secondary,
        "timeStability": stability,
        "classification": classification,
        "evidenceCoverageAudit": evidence_audit,
        "coverage": coverage,
        "secondaryHorizonTables": secondary_horizon_tables,
        "confirmatoryFamily": {
            "primaryHorizon": C.PRIMARY_HORIZON,
            "hypotheses": list(C.SLEEVES),
            "statistic": "POOLED_WITHIN_REGION_126D_RANK_IC",
            "correction": "HOLM_BONFERRONI",
        },
        "researchHistoryContamination": (
            "replay-v16 has been used by ten prior CHALLENGER studies on this ledger. This "
            "result is DISCOVERY / DIAGNOSTIC EVIDENCE, not FINAL OUT-OF-SAMPLE VALIDATION, "
            "and is not used as production promotion evidence regardless of how favourable "
            "any single reading looks."),
        "nextResearchProposals": [
            "1. Case A (independent sleeve found): design an independent-sample validation "
            "of that sleeve's information, never a same-sample reweighting.",
            "2. Case B (standalone but redundant): investigate an orthogonal information "
            "source rather than reweighting the existing four sleeves.",
            "3. Case C (weak across the board): evaluate new information sources (earnings "
            "revisions, estimate dispersion, relative-strength breadth, valuation change) as "
            "a separate CHALLENGER -- proposed, not implemented here.",
            "4. Case D (insufficient data): extend PIT instrumentation to store the raw "
            "subfactor inputs (mom121, mom6, and the value/quality raw ratios) on future "
            "signal records so a subfactor audit becomes possible -- proposed, not executed.",
        ],
        "sealedInvariant": {"before": before, "after": _digest_tree(ledger)},
    }
    report["sealedInvariant"]["unchanged"] = (
        report["sealedInvariant"]["before"] == report["sealedInvariant"]["after"])
    if not report["sealedInvariant"]["unchanged"]:
        raise ValueError("SEALED_LEDGER_CHANGED")
    report["answers"] = answers(primary_table, holm, secondary, classification,
                                stability["bySleeveRegion"], secondary["redundancy"]["pooled"])

    output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 allow_nan=False, sort_keys=True) + "\n")
    md.write_text(markdown(report))
    print(markdown(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
