"""Outcome-free power / minimum detectable effect (MDE) for the S2 candidate hypotheses.

Inputs are the measured event counts from results/ledger-summary.json and ASSUMED
per-event return dispersions and within-date correlations (no return is read; the
assumptions are stated per row and must be replaced by pre-registered values).
MDE (two-sided 5%, power 80%) = (1.96 + 0.84) * sigma / sqrt(N_eff),
N_eff = N_events / (1 + (m - 1) * rho), m = events per independent date.
"""
from __future__ import annotations

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
Z = 1.96 + 0.84


def mde(n_events: float, n_dates: float, sigma: float, rho: float) -> dict:
    m = n_events / n_dates if n_dates else 1.0
    n_eff = n_events / (1 + (m - 1) * rho)
    return {"nEvents": round(n_events), "nIndependentDates": round(n_dates), "eventsPerDate": round(m, 2),
            "rhoAssumed": rho, "sigmaAssumed": sigma, "nEffective": round(n_eff, 1),
            "mdePctPoints": round(100 * Z * sigma / math.sqrt(n_eff), 2)}


def main() -> None:
    s = json.load(open(os.path.join(HERE, "results", "ledger-summary.json"), encoding="utf-8"))
    rows = []
    # KOSPI 200 regular reviews: 27 reviews 2013-06..2026-06 if collection completes; adds per
    # review taken from the observed KOSDAQ 150 rate scaled to 200 names is NOT used — the
    # count below is the design count (27 reviews x ~6 adds), labelled DESIGN.
    for h, sig in (("H21", 0.08), ("H126", 0.22), ("H252", 0.30)):
        rows.append({"hypothesis": "A1 KOSPI200 regular review adds", "horizon": h, "countBasis": "DESIGN_27_REVIEWS_X_6",
                     **mde(27 * 6, 27, sig, 0.15)})
    kq = s["kosdaq150"]
    for h, sig in (("H21", 0.12), ("H126", 0.35), ("H252", 0.45)):
        rows.append({"hypothesis": "A2 KOSDAQ150 regular review adds", "horizon": h, "countBasis": "OBSERVED_5_REVIEWS",
                     **mde(kq["addsRegular"], kq["distinctRegularReviewDates"], sig, 0.15)})
        rows.append({"hypothesis": "A2 KOSDAQ150 regular review adds", "horizon": h, "countBasis": "DESIGN_22_REVIEWS_X_13",
                     **mde(22 * 13, 22, sig, 0.15)})
    sp = s["sp500"]
    for h, sig in (("H21", 0.07), ("H126", 0.20), ("H252", 0.28)):
        rows.append({"hypothesis": "A3 S&P500 adds (control market)", "horizon": h, "countBasis": "OBSERVED_PARSED",
                     **mde(sp["adds"], sp["distinctEffectiveDates"], sig, 0.10)})
    ko = s["kofia"]
    for h, sig in (("H21", 0.07), ("H63", 0.12), ("H126", 0.17)):
        rows.append({"hypothesis": "D1 market forced-sale episodes (KOSPI level)", "horizon": h,
                     "countBasis": "OBSERVED_EPISODES", **mde(ko["forcedSaleIndependentEpisodes"],
                                                            ko["forcedSaleIndependentEpisodes"], sig, 0.0)})
    for h, sig, n in (("H126", 0.06, 14), ("H252", 0.08, 7)):
        rows.append({"hypothesis": "B1 US flow-induced-trading decile spread (GCAP 2019Q3-2026Q3)", "horizon": h,
                     "countBasis": "DESIGN_NON_OVERLAPPING_PERIODS", "nEvents": n, "nIndependentDates": n,
                     "sigmaAssumed": sig, "rhoAssumed": None, "nEffective": n,
                     "mdePctPoints": round(100 * Z * sig / math.sqrt(n), 2)})
    for h, sig, n in (("H126", 0.15, 8),):
        rows.append({"hypothesis": "C1 NPS domestic-equity band breach (market level)", "horizon": h,
                     "countBasis": "DESIGN_UPPER_BOUND", "nEvents": n, "nIndependentDates": n,
                     "sigmaAssumed": sig, "rhoAssumed": None, "nEffective": n,
                     "mdePctPoints": round(100 * Z * sig / math.sqrt(n), 2)})
    out = {"method": __doc__.strip().splitlines()[0], "note": "sigma and rho are assumptions, not measurements",
           "rows": rows}
    json.dump(out, open(os.path.join(HERE, "results", "power-mde.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    for r in rows:
        print(r["hypothesis"][:45].ljust(46), r["horizon"], r["countBasis"][:22].ljust(23), r["nEffective"], r["mdePctPoints"])


if __name__ == "__main__":
    main()
