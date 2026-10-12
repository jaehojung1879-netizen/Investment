"""How long a prospective US rank-IC test needs, anchored on dispersion this repository has ALREADY published. Reads no new outcome.

Phase 2 (`docs/us-capital-allocation/us-multifactor-study-proposal-v1.json`) sized the IC test by treating the names inside a
signal window as independent (SE = 1/sqrt(names x windows)). Realised per-date US rank ICs are far more dispersed than that,
because names share sector, size and market exposures: `four-factor-signal-attribution-audit-v1` measured a per-date standard
deviation of 0.10-0.24 on the S&P 500 at every horizon, against 1/sqrt(330) = 0.055.

This module reads only the VARIANCE side of that committed report (each US sleeve's HAC 95% interval and its number of weekly
dates), never a sign or a mean, and rescales the historical standard error to a prospective span of T years:

    SE(T) = SE_hist * sqrt(years_hist / T),    MDE(T) = (z_0.95 + z_0.80) * SE(T)

which keeps the measured autocorrelation of overlapping weekly windows. It assumes a new feature's IC series is about as noisy
as the four production sleeves' and that the prospective period resembles 2013-2026; residualising on sector and size could
reduce the dispersion and is NOT measured here. Every number is an assumption-anchored planning figure, not evidence.
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
            "minimumDetectableMeanIc": {"%dy" % t: round(minimum_detectable_ic(se, years, t), 4) for t in SPANS_YEARS},
            "yearsToDetect": {"ic=%.2f" % ic: round(years_to_detect(se, years, ic), 1) for ic in target_ics},
        }
    return {"source": "docs/results/four-factor-signal-attribution-audit-report.json (US byRegion, variance side only)",
            "test": "one-sided 5%, power 80%, weekly signals, HAC-scaled", "byHorizonSessions": table,
            "independenceBasedPhase2ForComparison": {"330 names, 12 H126 windows (6 years)": 0.0395},
            "assumptions": ["the new feature's per-date IC dispersion resembles the production value/quality sleeves'",
                            "the prospective regime resembles 2013-2026", "no residualisation gain is assumed",
                            "planning figures only; no sign or mean of any IC is used"]}
