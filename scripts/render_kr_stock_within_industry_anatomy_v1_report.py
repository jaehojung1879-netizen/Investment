#!/usr/bin/env python3
"""Render the human-readable seal report from the committed result JSON. Reads numbers; recomputes nothing.

`render(result)` is a pure function of the committed result bytes; `--check` fails if the committed report differs from it."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "docs/results"
RESULT = R / "kr-stock-within-industry-anatomy-v1-result.json"
REPORT = R / "kr-stock-within-industry-anatomy-v1-report.md"
SENS = ("FULL", "EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX")
LENSES = ("CAP_WEIGHTED", "EQUAL_WEIGHT")
HORIZONS = (63, 126, 252)
COMPONENTS = ("STOCK_MINUS_LOO_INDUSTRY", "LOO_INDUSTRY_MINUS_MARKET", "STOCK_MINUS_MARKET")
WITHIN, RAW = "WITHIN_INDUSTRY_RANK", "RAW"
PRIMARY = "STOCK_MINUS_LOO_INDUSTRY"
SLICES = ("PRE_2025_COMPLETE_WINDOW", "TOUCHES_2025_OR_LATER")
STATES = (1.0, 0.7, 0.4)


def n(value, digits=3, signed=True):
    if value is None:
        return "n/a"
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"


def pp(value):
    return "n/a" if value is None else f"{value * 100:+.2f}"


def frac(value):
    return "n/a" if value is None else f"{value:.2f}"


def render(result):
    a = result["analysis"]
    registered = json.loads((ROOT / "research_specs/kr-stock-within-industry-anatomy-v1.json").read_text())["features"]["names"]
    assert sorted(registered) == sorted(result["signViews"])
    feats = list(registered)  # the frozen registration order; the result file itself stores keys alphabetically
    pooled = lambda s, f, fl=WITHIN, c=PRIMARY, lens="CAP_WEIGHTED", h=126: a[s]["pooledIc"][f"{f}|{fl}|{c}|{lens}|H{h}"]  # noqa: E731
    pri = lambda f: pooled("FULL", f)  # noqa: E731
    cmp126 = lambda f: result["priorComparison"][f + "|H126"]  # noqa: E731
    out = []
    w = out.append
    w("# kr-stock-within-industry-anatomy-v1 — sealed exploratory result")
    w("")
    w("**Status: `" + result["scientificStatus"] + "`.** Descriptive historical associations on an outcome-exposed, partially reconstructed history. Not confirmatory, "
      "not validated, not predictive, not production-ready, not prospective. Nothing here is a model, a selection rule or a recommendation, and no feature is "
      "called best. The membership underneath ended `DATA_FOUNDATION_INSUFFICIENT_V4`; that decision is not relabelled.")
    w("")
    w("This report is rendered from the committed exact result bytes by `scripts/render_kr_stock_within_industry_anatomy_v1_report.py`. It reads numbers and "
      "recomputes nothing. The formal one-shot execution (run 37196246044) has been spent and cannot be rerun. No registered feature, horizon, taxonomy, "
      "sample, sensitivity or interpretation rule was changed after the outcomes were read, and none was selected from them.")
    w("")
    w("* Return basis: `" + result["returnBasis"] + "` (adjusted index, partial observed distributions; neither a price return nor a total shareholder return). Benchmark: `" + result["benchmark"] + "`.")
    w("* Primary target: stock forward return minus the LEAVE-ONE-OUT CAP_WEIGHTED industry forward return (the evaluated stock is excluded from the cohort and the weights; weights are signal-date market caps of the peers). Primary horizon H126; H63 and H252 descriptive; EQUAL_WEIGHT is the robustness benchmark.")
    w("* Primary statistic: per signal date, the Spearman between the WITHIN-INDUSTRY feature rank and that target across the common-sample stocks of the date (at least 30), then the mean over dates. Weekly signals overlap, so the effective number of independent observations is far smaller than the valid dates shown.")
    w("* The three components satisfy stock − market = (leave-one-out industry − market) + (stock − leave-one-out industry) on every matured row. Rank correlations are not additive, so no figure below is a decomposition of another.")
    w("")
    w("## 1. Eligibility and denominators")
    w("")
    w("| Sensitivity | stock-dates | signal dates | eligible | below 5 industry members | unclassified | excluded by sensitivity | eligible per date min / median / max |")
    w("|---|---:|---:|---:|---:|---:|---:|---|")
    for s in SENS:
        e = result["eligibility"][s]
        b = e["byStatus"]
        per = e["eligibleStocksPerDate"]
        w(f"| {s} | {e['stockDates']} | {e['signalDates']} | {b.get('ELIGIBLE', 0)} | {b.get('INELIGIBLE_BELOW_MINIMUM_INDUSTRY_MEMBERS', 0)} | "
          f"{b.get('INELIGIBLE_UNCLASSIFIED', 0)} | {b.get('EXCLUDED_BY_SENSITIVITY', 0)} | {per['min']} / {per['median']:g} / {per['max']} |")
    e = result["eligibility"]["FULL"]
    w("")
    w(f"UNKNOWN names retained in the denominator: {e['unknownRetainedInDenominator']}. Ineligible reasons (FULL): " + ", ".join(f"{k} {v}" for k, v in sorted(e["ineligibleReasons"].items())) + ". "
      "No UNKNOWN name was used to fill a cohort and no terminal name was replaced by a survivor.")
    w("")
    w("Target status by lens and horizon (FULL; every eligible stock-date has a status):")
    w("")
    w("| lens / horizon | MATURED | PENDING | ineligible stock-date | any other |")
    w("|---|---:|---:|---:|---:|")
    for key, counts in sorted(e["targetStatus"].items()):
        other = sum(v for k, v in counts.items() if k not in ("MATURED", "PENDING", "INELIGIBLE_STOCK_DATE"))
        w(f"| {key.replace(chr(124), ' ')} | {counts.get('MATURED', 0)} | {counts.get('PENDING', 0)} | {counts.get('INELIGIBLE_STOCK_DATE', 0)} | {other} |")
    w("")
    w("Feature coverage (FULL, CAP_WEIGHTED H126; the common sample is eligible, matured, raw finite and within-industry rank finite):")
    w("")
    w("| feature | eligible | matured | raw finite | within-industry rank finite | common sample |")
    w("|---|---:|---:|---:|---:|---:|")
    for f in feats:
        c = a["FULL"]["coverage"][f"{f}|CAP_WEIGHTED|H126"]
        w(f"| {f} | {c['eligibleStockDates']} | {c['maturedTargets']} | {c['rawFiniteAmongEligible']} | {c['withinRankFiniteAmongEligible']} | {c['commonSample']} |")
    w("")
    w("## 2. Primary: within-industry rank vs stock − leave-one-out CAP_WEIGHTED industry, H126, FULL")
    w("")
    w("Features are listed in the registered order, never sorted by result.")
    w("")
    w("| feature | mean | median | positive-date fraction | valid dates | descriptive HAC se | mean / se | positive-year fraction (years >= 13 dates) |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|")
    for f in feats:
        p = pri(f)
        ratio = None if not p["hacSe"] else p["mean"] / p["hacSe"]
        w(f"| {f} | {n(p['mean'])} | {n(p['median'])} | {frac(p['positiveFraction'])} | {p['validDates']} | {n(p['hacSe'], 3, False)} | {n(ratio, 1)} | {frac(p['positiveYearFraction'])} |")
    w("")
    w("Annual mean rank correlation (same cell):")
    w("")
    years = sorted({y for f in feats for y in pri(f)["byYear"]})
    w("| feature | " + " | ".join(years) + " |")
    w("|---|" + "---:|" * len(years))
    for f in feats:
        by = pri(f)["byYear"]
        w(f"| {f} | " + " | ".join(n(by[y]["mean"], 2) if y in by else "n/a" for y in years) + " |")
    w("")
    w("## 3. Stock − market vs stock − leave-one-out industry")
    w("")
    w("Reference A is the SEALED `kr-factor-anatomy-v1` mean per-date rank correlation (stock − market, PIT Top120, v1 terminal discipline), read from its pinned result and not recomputed; "
      "it is on a different (larger) sample. A' is this study's own same-sample stock − market reading of the RAW feature. B is this study's within-industry rank vs stock − leave-one-out industry. "
      "Shift classes use the conventions frozen in the spec (|mean| < 0.01 is not a direction; ratio >= 0.75 SURVIVES; >= 0.25 WEAKENS_MATERIALLY; otherwise LARGELY_ABSORBED); they are interpretive, never tests.")
    for h in (126, 252):
        w("")
        w(f"H{h} (CAP_WEIGHTED, FULL):")
        w("")
        w("| feature | A sealed stock−market | A' same-sample stock−market (raw) | raw feature vs stock−LOO industry | B within-industry vs stock−LOO industry | LOO industry−market (raw) | B vs A | B vs A' |")
        w("|---|---:|---:|---:|---:|---:|---|---|")
        for f in feats:
            c = result["priorComparison"][f"{f}|H{h}"]
            w(f"| {f} | {n(c['sealedStockMinusMarket'])} | {n(c['sameSampleStockMinusMarketRaw'])} | {n(c['rawStockMinusLooIndustry'])} | {n(c['withinIndustryStockMinusLooIndustry'])} | "
              f"{n(c['looIndustryMinusMarketRaw'])} | {c['shiftVersusSealed']['shiftClass']} ({n(c['shiftVersusSealed']['ratio'], 2)}) | {c['shiftVersusSameSample']['shiftClass']} ({n(c['shiftVersusSameSample']['ratio'], 2)}) |")
    w("")
    w("Both lenses and all three components of the primary H126 cell (mean per-date rank correlation, FULL, CAP_WEIGHTED):")
    w("")
    w("| feature | RAW vs stock−LOO | WITHIN vs stock−LOO | RAW vs LOO industry−market | WITHIN vs LOO industry−market | RAW vs stock−market | WITHIN vs stock−market |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    for f in feats:
        cells = []
        for c in (PRIMARY, "LOO_INDUSTRY_MINUS_MARKET", "STOCK_MINUS_MARKET"):
            cells += [n(pooled("FULL", f, RAW, c)["mean"]), n(pooled("FULL", f, WITHIN, c)["mean"])]
        w(f"| {f} | " + " | ".join(cells) + " |")
    w("")
    w("## 4. Sign stability over the eight registered views")
    w("")
    w("Views: FULL and EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX x CAP_WEIGHTED and EQUAL_WEIGHT at H126; FULL CAP_WEIGHTED at H63 and H252; FULL CAP_WEIGHTED H126 over the PRE_2025 and 2025+ outcome windows. Only the sign of each view's mean is read.")
    w("")
    w("| feature | label | positive views | negative views | views read |")
    w("|---|---|---:|---:|---:|")
    for f in feats:
        s = result["signViews"][f]
        w(f"| {f} | {s['label']} | {s.get('positiveViews', 'n/a')} | {s.get('negativeViews', 'n/a')} | {s['viewsRead']} / {s['viewsRegistered']} |")
    w("")
    w("## 5. Weight lens, horizon and sensitivity grid (within-industry rank vs stock − leave-one-out industry)")
    w("")
    cells = [(s, lens, h) for s in SENS for lens in LENSES for h in HORIZONS]
    w("| feature | " + " | ".join(f"{'FULL' if s == 'FULL' else 'EXCL'} {'CAP' if lens == 'CAP_WEIGHTED' else 'EQ'} H{h}" for s, lens, h in cells) + " |")
    w("|---|" + "---:|" * len(cells))
    for f in feats:
        w(f"| {f} | " + " | ".join(n(pooled(s, f, lens=lens, h=h)["mean"]) for s, lens, h in cells) + " |")
    w("")
    w("EXCL = Samsung Electronics and SK Hynix removed before cohorts, ranks and weights.")
    w("")
    w("## 6. Outcome-window slices and signal-date market state (FULL, CAP_WEIGHTED H126)")
    w("")
    w("| feature | PRE_2025 | dates | 2025+ | dates | state 1.0 | dates | state 0.7 | dates | state 0.4 | dates |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for f in feats:
        cells = []
        for s in SLICES:
            x = a["FULL"]["slices"][f"{f}|{WITHIN}|{PRIMARY}|CAP_WEIGHTED|H126|{s}"]
            cells += [n(x["mean"]), str(x["validDates"])]
        for s in STATES:
            x = a["FULL"]["benchmarkStates"][f"{f}|{WITHIN}|{PRIMARY}|CAP_WEIGHTED|H126|BENCHMARK_STATE_{s}"]
            cells += [n(x["mean"]), str(x["validDates"])]
        w(f"| {f} | " + " | ".join(cells) + " |")
    w("")
    w("The 0.4 state has few dates; read it as a count, not a regime estimate.")
    w("")
    w("## 7. Secondary statistics that do not let large industries dominate (FULL, CAP_WEIGHTED H126)")
    w("")
    w("Equal-industry rank correlation is invariant to the within-industry transform. The group spread is top minus bottom third by feature inside an industry-date (at least 2 stocks per group), averaged with equal weight per industry (at least 3 industries) then per date; ties across a group boundary invalidate the industry-date.")
    w("")
    w("| feature | equal-industry rank correlation | valid dates | mean industries per date | group spread (pp) | valid dates | mean industries per date |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    for f in feats:
        e1 = a["FULL"]["equalIndustryIc"][f"{f}|{PRIMARY}|CAP_WEIGHTED|H126"]
        g = a["FULL"]["groupSpread"][f"{f}|{PRIMARY}|CAP_WEIGHTED|H126"]
        w(f"| {f} | {n(e1['mean'])} | {e1['validDates']} | {n(e1['meanIndustriesPerDate'], 1, False)} | {pp(g['mean'])} | {g['validDates']} | {n(g['meanIndustriesPerDate'], 1, False)} |")
    w("")
    w("## 8. The five registered questions (tables of the registered numbers, not an answer key)")
    for question, entry in result["questions"].items():
        w("")
        w("### " + question)
        w("")
        w("| feature | mean (primary) | valid dates | sign label | B vs A | B vs A' |")
        w("|---|---:|---:|---|---|---|")
        for f, body in entry.items():
            if "primary" not in body:
                continue
            c = body["priorComparison"]
            w(f"| {f} | {n(body['primary']['mean'])} | {body['primary']['validDates']} | {body['signStability']['label']} | {c['shiftVersusSealed']['shiftClass']} | {c['shiftVersusSameSample']['shiftClass']} |")
        if "sizeControl" in entry:
            w("")
            w("`logAdv60` size control (CAP_WEIGHTED H126; within-industry size is a context variable, not a feature):")
            w("")
            w("| sensitivity | rank overlap with within-industry size | lower half by size | dates | upper half by size | dates |")
            w("|---|---:|---:|---:|---:|---:|")
            for s, body in entry["sizeControl"].items():
                c = body["CAP_WEIGHTED"]
                lo, hi = (c["byWithinIndustrySizeHalf"][k] for k in ("LOWER_HALF_BY_WITHIN_INDUSTRY_SIZE", "UPPER_HALF_BY_WITHIN_INDUSTRY_SIZE"))
                w(f"| {s} | {n(c['rankOverlapWithWithinIndustrySize']['mean'])} | {n(lo['mean'])} | {lo['validDates']} | {n(hi['mean'])} | {hi['validDates']} |")
        if "byBenchmarkState" in entry:
            w("")
            w("`negativeDownsideVol126` by signal-date market state (CAP_WEIGHTED H126):")
            w("")
            w("| sensitivity | state 1.0 | dates | state 0.7 | dates | state 0.4 | dates |")
            w("|---|---:|---:|---:|---:|---:|---:|")
            for s, states in entry["byBenchmarkState"].items():
                w(f"| {s} | " + " | ".join(f"{n(states[str(k)]['mean'])} | {states[str(k)]['validDates']}" for k in STATES) + " |")
    w("")
    positive = [f for f in feats if result["signViews"][f]["label"] == "POSITIVE_IN_ALL_REGISTERED_VIEWS"]
    dependent = [f for f in feats if result["signViews"][f]["label"] == "SIGN_DEPENDS_ON_VIEW"]
    big_industry = [f for f in feats if abs(cmp126(f)["looIndustryMinusMarketRaw"]) >= 0.05]
    classes = {}
    for f in feats:
        classes.setdefault(cmp126(f)["shiftVersusSealed"]["shiftClass"], []).append(f)
    w("## 9. Observed")
    w("")
    w("* Registered features positive in all eight views: " + ", ".join(positive) + ".")
    w("* Registered features whose sign depends on the view: " + ", ".join(dependent) + ".")
    w("* Shift versus the sealed stock − market reading at H126 (conventions frozen before outcomes): " + "; ".join(f"{k}: {len(v)}" for k, v in sorted(classes.items())) + ". Features that change sign against the sealed reading at H126: " + (", ".join(classes.get("CHANGES_SIGN", [])) or "none") + ".")
    c252 = {}
    for f in feats:
        for ref, name in (("shiftVersusSealed", "sealed"), ("shiftVersusSameSample", "same-sample")):
            c252.setdefault((name, result["priorComparison"][f + "|H252"][ref]["shiftClass"]), []).append(f)
    for name in ("sealed", "same-sample"):
        w(f"* Shift at H252 versus the {name} stock − market reading: " + "; ".join(f"{k[1]}: {len(v)}" for k, v in sorted(c252.items()) if k[0] == name)
          + ". Features that change sign: " + (", ".join(c252.get((name, "CHANGES_SIGN"), [])) or "none") + ".")
    w("* The leave-one-out industry component (RAW feature vs industry − market) has |mean| >= 0.05 only for: " + (", ".join(big_industry) or "none") + ".")
    top = max(feats, key=lambda f: abs(pri(f)["mean"] / pri(f)["hacSe"]))
    w(f"* The largest |mean / descriptive standard error| among the primary cells is {abs(pri(top)['mean'] / pri(top)['hacSe']):.1f} ({top}); the descriptive standard error is itself an approximation under overlapping weekly dates and no multiplicity correction is applied.")
    w("")
    w("## 10. Hypotheses (for a NEW preregistration on an independent sample; none is tested here)")
    w("")
    w("* The book-to-market and earnings-yield associations are not an industry-composition artefact: they keep their sign and most of their size after the industry component is removed.")
    w("* The `logAdv60` association was not only a size or mega-cap or industry-composition effect in this sample, but its size-control and mega-cap-exclusion readings are descriptive and the sample is exposed.")
    w("* `negativeDownsideVol126` and `relative126` look regime- or window-dependent rather than stable once industry is removed.")
    w("* Accrual and cash-flow-to-asset features carry little within-industry information here, and their coverage differs by region of the history (Korean value and quality are dark in the first years).")
    w("")
    w("## 11. Not established")
    w("")
    w("* That any feature predicts forward returns, has been validated, or should be used for selection, weighting or a portfolio.")
    w("* That the within-industry readings are PIT-exact: the industry history is a reconstruction and terminal securities are unclassified.")
    w("* That these readings survive an independent sample, a multiplicity correction, or a change of benchmark, taxonomy, horizon or weighting.")
    w("* That a sealed prior result was wrong or right: the comparison is interpretive, on a different sample, and the sealed studies were not rerun.")
    w("")
    w("## 12. Limitations")
    w("")
    w("Outcome-exposed single sample; reconstructed industry history; peer sets of four to a few dozen names make the leave-one-out benchmark noisy; weekly signals overlap; large caps only; "
      "partial-distribution return basis (banks and high-dividend names unreliable); issue-cap accounting proxies; no multiplicity correction; any peer without a matured return makes a target unresolved; "
      "a within-industry rank removes industry composition, not size, mega-cap or sector-cycle effects inside an industry.")
    return "\n".join(out) + "\n"


def main(argv):
    result = json.loads(RESULT.read_text())
    text = render(result)
    if "--check" in argv:
        if REPORT.read_text() != text:
            raise SystemExit("REPORT_DIFFERS_FROM_RENDER_OF_COMMITTED_RESULT")
        return 0
    REPORT.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
