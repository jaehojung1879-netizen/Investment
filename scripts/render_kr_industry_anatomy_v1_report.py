#!/usr/bin/env python3
"""Render the human-readable seal report from the committed result JSON. Reads numbers; recomputes nothing."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "docs/results"
RESULT = R / "kr-industry-opportunity-anatomy-v1-result.json"
REPORT = R / "kr-industry-opportunity-anatomy-v1-report.md"
SENS = ("FULL", "LEAVE_LARGEST_CONSTITUENT_OUT", "EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX")
SLICES = ("FULL_SAMPLE", "PRE_2025_COMPLETE_WINDOW", "TOUCHES_2025_OR_LATER", "TOUCHES_2026")
CELLS = [(lens, h) for lens in ("CAP_WEIGHTED", "EQUAL_WEIGHT") for h in (63, 126, 252)]


def n(value, digits=3, signed=True):
    if value is None:
        return "n/a"
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"


def pp(value):
    return "n/a" if value is None else f"{value * 100:+.1f}"


def sign(value):
    return "." if value is None or value == 0 else ("+" if value > 0 else "-")


def render(result):
    a = result["analysis"]
    full = a["FULL"]
    feats = sorted({k.split("|")[0] for k in full["ic"]})
    key = lambda f, lens="CAP_WEIGHTED", h=126: f"{f}|{lens}|H{h}"  # noqa: E731
    ic = lambda s, f, lens="CAP_WEIGHTED", h=126: a[s]["ic"][key(f, lens, h)]  # noqa: E731
    te = lambda s, f, lens="CAP_WEIGHTED", h=126: a[s]["tercile"][key(f, lens, h)]  # noqa: E731
    elig = result["eligibility"]
    consistent = [f for f in feats if len({sign(ic("FULL", f, l, h)["mean"]) for l, h in CELLS}) == 1 and sign(ic("FULL", f)["mean"]) != "."]
    out = []
    w = out.append
    w("# kr-industry-opportunity-anatomy-v1 — sealed exploratory result")
    w("")
    w("**Status: `" + result["scientificStatus"] + "`.** Descriptive historical associations on a partially reconstructed history. Not confirmatory, not validated, "
      "not production-ready, not prospective. The membership underneath ended `DATA_FOUNDATION_INSUFFICIENT_V4` under its own frozen gates; "
      "this study ran under a separately preregistered exploratory eligibility rule and that result is not relabelled.")
    w("")
    w("This report is rendered from the committed exact result bytes by `scripts/render_kr_industry_anatomy_v1_report.py`. It reads numbers and recomputes nothing. "
      "The formal one-shot execution (run 37182657697) has been spent and cannot be rerun.")
    w("")
    w("* Return basis: `" + result["returnBasis"] + "` (adjusted index, partial observed distributions; not total shareholder return). Benchmark: `" + result["benchmark"] + "`.")
    w("* Target: industry return (cohort and weights fixed at the signal date) minus the same-window benchmark return. Primary: CAP_WEIGHTED H126. Descriptive: H63, H252, EQUAL_WEIGHT.")
    w("* Statistic: per-date cross-sectional Spearman across eligible industries (IC) and top-minus-bottom tercile spread, then the mean over dates. Weekly signals overlap, so the number of independent observations is far smaller than the date counts shown.")
    w("")
    w("## 1. Eligibility and coverage")
    w("")
    w("| Sensitivity | industry-dates | eligible | ineligible (below 5 classified members) | eligible industries per date min / median / max |")
    w("|---|---:|---:|---:|---|")
    for s in SENS:
        e = elig[s]
        p = e["eligibleIndustriesPerDate"]
        w(f"| {s} | {e['industryDates']} | {e['eligible']} | {e['ineligible']} | {p['min']} / {p['median']:.0f} / {p['max']} |")
    w("")
    w("`meanClassifiedCoverage` in the raw result (about 0.068) is the average SHARE OF THE 120-NAME COHORT held by one industry, not membership coverage; "
      "overall classified coverage is the v4 figure (95.295% of 73,200 name-dates, terminal securities unclassified). An ineligible industry-date is INELIGIBLE, not zero.")
    w("")
    cov = full["coverage"]
    w("Feature and target coverage (FULL, CAP_WEIGHTED H126; eligible industry-dates = " + str(cov[key(feats[0])]["eligibleIndustryDates"]) + ", target finite = " + str(cov[key(feats[0])]["targetFinite"]) + "):")
    w("")
    w("| Feature | feature finite | both finite | IC valid dates | tercile valid dates |")
    w("|---|---:|---:|---:|---:|")
    for f in feats:
        c = cov[key(f)]
        w(f"| {f} | {c['featureFinite']} | {c['bothFinite']} | {ic('FULL', f)['validDates']} | {te('FULL', f)['validDates']} |")
    w("")
    w("A date is valid for IC only with at least 8 eligible industries holding both values, and for the tercile spread with at least 9; fundamentals are missing far more often than price features, and missing is never zero.")
    w("")
    w("## 2. Primary anatomy: CAP_WEIGHTED, H126 (all 19 features, no selection)")
    w("")
    w("| Feature | IC mean | IC median | IC positive share | IC valid dates | HAC se (descriptive) | IC mean / se (descriptive) | tercile spread (pp) | tercile positive share | tercile valid dates |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for f in feats:
        i, t = ic("FULL", f), te("FULL", f)
        w(f"| {f} | {n(i['mean'])} | {n(i['median'])} | {n(i['positiveFraction'], 2, False)} | {i['validDates']} | {n(i['hacSe'], 3, False)} | {n(i['mean'] / i['hacSe'], 1) if i['hacSe'] else 'n/a'} | {pp(t['mean'])} | {n(t['positiveFraction'], 2, False)} | {t['validDates']} |")
    w("")
    w("The HAC standard error is Newey-West over the date series with lag ceil(H/5), labelled descriptive; the ratio is just the reported mean divided by the reported standard error. "
      "Most mean ICs sit within about one standard error of zero; the clear exceptions in the ratio column are discussed in section 6.")
    w("")
    w("## 3. Horizons and lenses (IC mean; sign pattern across the six cells)")
    w("")
    w("| Feature | CAP H63 | CAP H126 | CAP H252 | EW H63 | EW H126 | EW H252 | signs |")
    w("|---|---:|---:|---:|---:|---:|---:|---|")
    for f in feats:
        v = [ic("FULL", f, l, h)["mean"] for l, h in CELLS]
        w(f"| {f} | " + " | ".join(n(x) for x in v) + " | " + "".join(sign(x) for x in v) + " |")
    w("")
    w("Features whose IC sign is identical in all six cells (rule-based, not chosen after looking): " + (", ".join(consistent) or "none") + ".")
    lens = result["lensComparison"]
    w("")
    w("Rank agreement between the cap-weighted and equal-weight relative returns of the same industries (per-date Spearman, mean over dates): "
      + "; ".join(f"{h} {n(lens[h]['mean'], 3, False)} over {lens[h]['validDates']} dates, positive on {n(lens[h]['positiveFraction'], 2, False)} of them" for h in ("H63", "H126", "H252")) + ".")
    w("")
    w("## 4. Chronology (IC mean by signal year, CAP_WEIGHTED H126; dates in brackets)")
    w("")
    years = sorted({y for f in feats for y in ic("FULL", f)["byYear"]})
    w("| Feature | " + " | ".join(years) + " |")
    w("|---|" + "---:|" * len(years))
    for f in feats:
        by = ic("FULL", f)["byYear"]
        w(f"| {f} | " + " | ".join((f"{n(by[y]['mean'], 2)} ({by[y]['dates']})" if y in by else "n/a") for y in years) + " |")
    w("")
    w("Outcome-window slices (decided by entry and exit dates, boundaries fixed in the spec; IC mean and valid dates):")
    w("")
    w("| Feature | FULL | PRE-2025 windows | 2025-or-later windows | touches 2026 |")
    w("|---|---:|---:|---:|---:|")
    for f in feats:
        cells = [full["slices"][key(f) + "|" + s] for s in SLICES]
        w(f"| {f} | " + " | ".join(f"{n(c['mean'])} ({c['validDates']})" for c in cells) + " |")
    w("")
    w("The 2025-or-later and 2026 slices rest on very few dates for the price features (for example REL_MOM_126: "
      + str(full["slices"][key("REL_MOM_126") + "|TOUCHES_2025_OR_LATER"]["validDates"]) + " and " + str(full["slices"][key("REL_MOM_126") + "|TOUCHES_2026"]["validDates"])
      + ") because forward windows must be complete by the development cutoff; they are descriptive only.")
    w("")
    w("## 5. Mega-cap and concentration sensitivities (CAP_WEIGHTED H126; IC mean / tercile pp; IC dates, tercile dates)")
    w("")
    w("| Feature | FULL | leave largest constituent out | exclude Samsung Electronics and SK Hynix |")
    w("|---|---:|---:|---:|")
    for f in feats:
        cells = []
        for s in SENS:
            i, t = ic(s, f), te(s, f)
            cells.append(f"{n(i['mean'])} / {pp(t['mean'])} ({i['validDates']}, {t['validDates']})")
        w(f"| {f} | " + " | ".join(cells) + " |")
    w("")
    w("Leaving the largest constituent out shrinks the eligible cross-section (see section 1), so its fundamental columns have only a handful of tercile dates and are not informative.")
    w("")
    w("Concentration strata by top-1 cap share (fixed cutoff 0.35; IC mean and valid dates within each stratum, minimum 5 industries):")
    w("")
    w("| Feature | top-1 share below 0.35 | top-1 share at or above 0.35 |")
    w("|---|---:|---:|")
    for f in feats:
        lo, hi = full["strata"].get(key(f) + "|TOP1_CAP_SHARE_LOW"), full["strata"].get(key(f) + "|TOP1_CAP_SHARE_HIGH")
        if lo:
            w(f"| {f} | {n(lo['mean'])} ({lo['validDates']}) | {n(hi['mean'])} ({hi['validDates']}) |")
    w("")
    h = {f: (ic("FULL", f), te("FULL", f)) for f in feats}
    llo = {f: (ic("LEAVE_LARGEST_CONSTITUENT_OUT", f), te("LEAVE_LARGEST_CONSTITUENT_OUT", f)) for f in feats}
    w("## 6. Observed, hypothesised, not established")
    w("")
    w("### Observed (descriptive, this sample only)")
    w("")
    m = lambda f, k=0: h[f][k]["mean"]  # noqa: E731
    w(f"* Price-state features lean positive at H126: REL_MOM_126 IC {n(m('REL_MOM_126'))}, tercile {pp(m('REL_MOM_126', 1))} pp; BREADTH_ABOVE_MA_126 IC {n(m('BREADTH_ABOVE_MA_126'))}, tercile {pp(m('BREADTH_ABOVE_MA_126', 1))} pp; "
      f"CONSTITUENT_DISPERSION_126 IC {n(m('CONSTITUENT_DISPERSION_126'))}, tercile {pp(m('CONSTITUENT_DISPERSION_126', 1))} pp. The ICs are small (a few hundredths) and positive on roughly 55–60% of dates. Positive-share and relative-momentum breadth variants are weaker or mixed (see section 2).")
    w(f"* REL_MOM_126 across horizons and lenses: IC {', '.join(n(ic('FULL', 'REL_MOM_126', l, hh)['mean']) for l, hh in CELLS)} (CAP H63/H126/H252, EW H63/H126/H252); the CAP H252 value is slightly negative, so the pattern is not uniform across horizons.")
    w(f"* Leaving the largest constituent out: REL_MOM_126 IC stays {n(llo['REL_MOM_126'][0]['mean'])} but its tercile spread falls from {pp(m('REL_MOM_126', 1))} to {pp(llo['REL_MOM_126'][1]['mean'])} pp; "
      f"CONSTITUENT_DISPERSION_126 keeps both ({n(llo['CONSTITUENT_DISPERSION_126'][0]['mean'])}, {pp(llo['CONSTITUENT_DISPERSION_126'][1]['mean'])} pp); excluding only Samsung Electronics and SK Hynix leaves REL_MOM_126 essentially unchanged ({pp(te('EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX', 'REL_MOM_126')['mean'])} pp).")
    w(f"* MEDIAN_netIncomeImprovementToAssets is negative in every cell (IC {n(m('MEDIAN_netIncomeImprovementToAssets'))}, tercile {pp(m('MEDIAN_netIncomeImprovementToAssets', 1))} pp at CAP H126), in both lenses, pre-2025 and 2025-or-later, and under both mega-cap sensitivities. "
      f"MEDIAN_ocfImprovementToAssets does not show it (IC {n(m('MEDIAN_ocfImprovementToAssets'))}, tercile {pp(m('MEDIAN_ocfImprovementToAssets', 1))} pp).")
    w(f"* MEDIAN_ocfYieldProxy has the largest positive IC ({n(m('MEDIAN_ocfYieldProxy'))}, tercile {pp(m('MEDIAN_ocfYieldProxy', 1))} pp) and positive signs in all six cells, but its slices disagree: "
      f"{n(full['slices'][key('MEDIAN_ocfYieldProxy') + '|PRE_2025_COMPLETE_WINDOW']['mean'])} over {full['slices'][key('MEDIAN_ocfYieldProxy') + '|PRE_2025_COMPLETE_WINDOW']['validDates']} pre-2025 dates against "
      f"{n(full['slices'][key('MEDIAN_ocfYieldProxy') + '|TOUCHES_2025_OR_LATER']['mean'])} over {full['slices'][key('MEDIAN_ocfYieldProxy') + '|TOUCHES_2025_OR_LATER']['validDates']} later dates.")
    w(f"* Industry book-to-market did not reproduce the stock-level association: IC {n(m('MEDIAN_bookToMarketProxy'))}, tercile {pp(m('MEDIAN_bookToMarketProxy', 1))} pp at CAP H126, with mixed signs across cells.")
    ratio = lambda f: h[f][0]["mean"] / h[f][0]["hacSe"]  # noqa: E731
    w("* Descriptive IC / HAC-standard-error ratios at CAP H126: " + ", ".join(f"{f} {ratio(f):+.1f}" for f in ("REL_MOM_126", "BREADTH_ABOVE_MA_126", "CONSTITUENT_DISPERSION_126", "MEDIAN_ocfYieldProxy", "MEDIAN_netIncomeImprovementToAssets", "MEDIAN_bookToMarketProxy"))
      + ". Only the two fundamental features exceed two in absolute value; with overlapping signals, about fourteen coarse industries and no multiplicity correction these are descriptive magnitudes, not tests.")
    w("* Cap-weighted and equal-weight future industry-return rankings agree strongly (section 3), so the rankings are not dominated by a single mega-cap.")
    w("")
    w("### Plausible hypotheses (not tested here)")
    w("")
    w("* Industry relative momentum and breadth may carry useful historical state information at multi-month horizons.")
    w("* Improving earnings measures may already be anticipated by prices, so improvement could lag rather than lead returns.")
    w("* Industry-level value may behave differently from stock-level value because industry aggregates mix quality and business-cycle composition.")
    w("* Concentration and the recent mega-cap regime may condition some effects (the strata and 2025-or-later slices differ from the pre-2025 pattern for several features).")
    w("")
    w("### Not established")
    w("")
    w("This study does NOT establish prospective predictability, causality, a profitable implementable industry-rotation strategy, optimal feature weights, optimal thresholds or any production allocation rule. "
      "Nothing here is an investment recommendation.")
    w("")
    w("## 7. Limitations")
    w("")
    w("* Exploratory, outcome-exposed single historical sample; 19 features × 6 target cells × 3 sensitivities × several slices with no multiplicity correction. No isolated number is confirmation.")
    w("* About 14 coarse industries (6–12 eligible per date); ICs and tercile spreads are noisy, and the tercile spread rests on far fewer valid dates than the IC.")
    w("* Weekly signals overlap; effective independent dates are roughly dates divided by H/5 (the result records them). The HAC standard errors are descriptive.")
    w("* The industry history is a reconstruction (current official anchor plus disclosed change events) that is not point-in-time exact; the 22 terminal securities are unclassified; most classified name-dates rest on a no-change inference.")
    w("* An industry-date is resolved only if every cohort member has a matured return, so some windows are unresolved rather than renormalised.")
    w("* Top-120 large caps only; the return basis has partial distributions, so banks and other high-dividend names are unreliable.")
    w("* No industry-specific cycle data and no revised macro history entered the study.")
    return "\n".join(out) + "\n"


def main():
    result = json.loads(RESULT.read_text())
    text = render(result)
    if "--check" in sys.argv:
        if REPORT.read_text() != text:
            raise SystemExit("REPORT_DIFFERS_FROM_RENDERED_RESULT")
        return
    REPORT.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
