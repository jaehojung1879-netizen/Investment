"""Illustrative RANK-IC proxy for how long a prospective US test would need. NOT a power analysis of the registered primary statistic.

WHAT THIS SUPPORTS, AND WHAT IT DOES NOT. Every number here is about the mean of a weekly cross-sectional Spearman rank IC,
because the only US dispersion this repository has published is a rank-IC dispersion
(`four-factor-signal-attribution-audit-v1`, per-date standard deviation 0.10-0.24 on the S&P 500 at every horizon). The proposed
primary statistic of `us-cash-profitability-signal-v1` is a DIFFERENT quantity: a residualised long-short H63 factor spread, i.e.
a weighted RETURN in percentage points. Its sampling variance depends on the cross-sectional return dispersion of each date,
on the residualised weights and on the overlap of consecutive H63 windows, none of which a rank-IC dispersion measures (an IC is
unitless and bounded; the spread is not). These figures therefore:
* DO support: the order of magnitude of how slowly a mean rank IC of a quarterly accounting signal is resolved on the S&P 500,
  and the correction of Phase 2's independence-based IC table (which ignored the common-factor part of the per-date dispersion);
* DO NOT support: a power, minimum detectable effect, gate size or futility boundary for the primary spread test. Those need the
  primary statistic's own variance under the registered calendar-time attribution, which is not yet calibrated (protocol
  prerequisite P3) and must never be read off this table.

Method: only the VARIANCE side of the committed report is read (each US sleeve's HAC 95% interval and its number of weekly dates),
never a sign or a mean; the historical standard error is rescaled to a prospective span of T years,

    SE(T) = SE_hist * sqrt(years_hist / T),    MDE_IC(T) = (z_0.95 + z_0.80) * SE(T)

which keeps the measured autocorrelation of overlapping weekly windows. Assumptions: the new feature's IC series is about as noisy
as the production value/quality sleeves', the prospective period resembles 2013-2026, and residualisation gains nothing.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import NormalDist, median

REPORT = Path(__file__).resolve().parent.parent / "docs/results/four-factor-signal-attribution-audit-report.json"
WEEKS_PER_YEAR = 365.25 / 7
Z_ALPHA = NormalDist().inv_cdf(0.95)     # one-sided 5%
Z_POWER = NormalDist().inv_cdf(0.80)
SPANS_YEARS = (3, 5, 8, 10)
SLEEVES = ("momentum", "value", "quality", "lowvol")
SCOPE = "ILLUSTRATIVE_RANK_IC_PROXY_NOT_PRIMARY_STATISTIC_POWER"


def us_dispersion(report: dict) -> dict:
    """{horizon: {sleeve: {perDateStd, seHist, yearsHist, effectiveIndependentDates}}} from the committed report."""
    tables = {str(report["primaryHorizon"]): report["primaryTable"], **report["secondaryHorizonTables"]}
    out = {}
    for horizon, table in sorted(tables.items(), key=lambda kv: int(kv[0])):
        out[horizon] = {}
        for sleeve in SLEEVES:
            us = table[sleeve]["byRegion"]["US"]
            low, high = us["ci95"]
            out[horizon][sleeve] = {"perDateStd": us["std"], "seHist": (high - low) / (2 * 1.959964),
                                    "yearsHist": us["uniqueDates"] / WEEKS_PER_YEAR,
                                    "effectiveIndependentDates": us["effectiveIndependentDates"]}
    return out


def minimum_detectable_ic(se_hist: float, years_hist: float, years: float) -> float:
    return (Z_ALPHA + Z_POWER) * se_hist * (years_hist / years) ** 0.5


def years_to_detect(se_hist: float, years_hist: float, ic: float) -> float:
    """Prospective years until MDE(T) falls to `ic`."""
    return years_hist * ((Z_ALPHA + Z_POWER) * se_hist / ic) ** 2


def planning_table(report: dict | None = None, target_ics=(0.02, 0.03, 0.05)) -> dict:
    report = report if report is not None else json.loads(REPORT.read_text())
    disp = us_dispersion(report)
    table = {}
    for horizon, sleeves in disp.items():
        fundamental = [sleeves[s] for s in ("value", "quality")]      # slow accounting sleeves: the closest analogue
        se = median(x["seHist"] for x in fundamental)
        years = median(x["yearsHist"] for x in fundamental)
        table[horizon] = {
            "anchor": "median of the US value and quality sleeves",
            "perDateIcStdBySleeve": {s: round(v["perDateStd"], 4) for s, v in sleeves.items()},
            "seHistBySleeve": {s: round(v["seHist"], 5) for s, v in sleeves.items()},
            "effectiveIndependentDatesHist": {s: v["effectiveIndependentDates"] for s, v in sleeves.items()},
            "minimumDetectableMeanRankIc": {"%dy" % t: round(minimum_detectable_ic(se, years, t), 4) for t in SPANS_YEARS},
            "yearsToDetectMeanRankIc": {"ic=%.2f" % ic: round(years_to_detect(se, years, ic), 1) for ic in target_ics},
        }
    return {"scope": SCOPE,
            "supports": ["order of magnitude of how slowly a mean weekly rank IC is resolved on the S&P 500",
                         "the correction of Phase 2's independence-based rank-IC table"],
            "doesNotSupport": ["power or minimum detectable effect of the primary residualised H63 long-short spread",
                               "the gate size, the futility boundary or any conditional-power figure of the primary test",
                               "inference coverage of any interval"],
            "statistic": "mean weekly cross-sectional Spearman rank IC (unitless), NOT the primary factor spread (a return)",
            "source": "docs/results/four-factor-signal-attribution-audit-report.json (US byRegion, variance side only)",
            "test": "one-sided 5%, power 80%, weekly signals, HAC-scaled", "byHorizonSessions": table,
            "independenceBasedPhase2ForComparison": {"330 names, 12 H126 windows (6 years)": 0.0395},
            "assumptions": ["the new feature's per-date IC dispersion resembles the production value/quality sleeves'",
                            "the prospective regime resembles 2013-2026", "no residualisation gain is assumed",
                            "illustrative rank-IC proxy only; no sign or mean of any IC is used"]}
