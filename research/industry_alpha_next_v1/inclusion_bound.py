"""Bounded inclusion of the terminated KR names whose industry is unknown, in place of dropping them.

Dropping an unclassified name that later terminated is the survivorship repair this repository forbids, and the 22
cannot be classified from the repository today (0/22). The registered alternative here is the promotion-gate rule
one level down: BOUND the bias instead of demanding it be zero. Every unclassified name stays in the cross-section
with its observed return, and is placed in the eligible industry that is LEAST favourable to the hypothesis,
independently in every cohort and month. A result counts only if it survives that placement.

Two parts, neither reading a price, return or outcome of a real security:

* `real_exposure` - from PIT Top120 membership and strictly prior monthly KRX caps only: how many unclassified
  terminated names sit in each signal-date cross-section, and the largest share of an eligible industry's
  cap-weighted (and equal-weighted) return one of them could take if placed there. This sizes the bound.
* `run` - a synthetic screen on the frozen calibration's worlds, with the alternative design's calendar-time spread:
  size and power of the SN test on the TRUE series, on the least-favourable BOUND series, and with the names
  DROPPED (which here is unbiased only because the synthetic names are random; in history it is not).

Limits stated before any number: the bound changes only the industry RETURN a name enters; the name's effect on its
industry's signal-date features (and hence the industry's rank) is not bounded. The stock-level idiosyncratic
volatility is an assumption (8% a month), not a measurement.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from . import alternative_design as A
from . import inference_calibration as C

DGPS = ("N1_GAUSS_CONST", "N2_T4_VOL_REGIME", "P10_T4_VOL_REGIME", "P20_T4_VOL_REGIME")
UNKNOWN_PER_DATE = 4          # the measured median (real_exposure: 1-8 per date, median 4)
SHARE_IF_PLACED = 0.14        # within one eligible industry; measured median cap share 0.109, EW 0.125-0.167
IDIO_MONTHLY = (0.08,)        # assumption (about 28% a year relative to its own industry)
TERMINAL_EVENTS = 11          # in-window names without complete terminal economics (16 - 5), placed at -100%
HOLDING_MONTHS = {126: 6}


# --------------------------------------------------------------------------- #
# Real exposure (membership and caps only)
# --------------------------------------------------------------------------- #
def real_exposure(root=None):
    import pandas as pd

    from pipeline import kr_industry_anatomy as I

    from . import inputs as IN
    from . import panel as P
    from .kr22_recovery import STUDY_WINDOW

    root = root or IN.ROOT
    m, caps_view = IN.load_membership(root), IN.load_universe(root)
    schedule = {d: v for d, v in P.monthly_signals(m["weekly"]).items() if STUDY_WINDOW[0] <= d[:7] <= STUDY_WINDOW[1]}
    caps = {(d, t): caps_view.cap(t, d) or np.nan for d, names in schedule.items() for t in names}
    capframe = pd.DataFrame([{"date": d, "ticker": t, "marketCap": v} for (d, t), v in caps.items()])
    cohorts = I.build_cohorts(I.membership_table(schedule, m["intervals"], m["crosswalk"], m["ends"]), capframe)
    rows = []
    for d, names in schedule.items():
        eligible = [c for (dd, _), c in cohorts.items() if dd == d and c["status"] == "ELIGIBLE"]
        for t in (t for t in names if t in m["terminal"]):
            ct = caps.get((d, t), np.nan)
            rows.append({"date": d, "ticker": t,
                         "capShareMax": max(ct / (math.fsum(caps[(d, x)] for x in c["members"]) + ct) for c in eligible),
                         "ewShareMax": max(1.0 / (c["n"] + 1) for c in eligible)})
    per_date = {}
    for r in rows:
        per_date[r["date"]] = per_date.get(r["date"], 0) + 1
    q = lambda key, p: round(float(np.quantile([r[key] for r in rows], p)), 4)  # noqa: E731
    return {"signalDates": len(schedule), "datesWithUnclassifiedTerminated": len(per_date),
            "memberMonths": len(rows), "securities": len({r["ticker"] for r in rows}),
            "perDate": {"min": min(per_date.values()), "median": float(np.median(list(per_date.values()))),
                        "max": max(per_date.values())},
            "capShareMaxIfPlaced": {"p50": q("capShareMax", .5), "p90": q("capShareMax", .9), "max": q("capShareMax", 1)},
            "ewShareMaxIfPlaced": {"min": q("ewShareMax", 0), "max": q("ewShareMax", 1)},
            "byYear": {y: sum(1 for r in rows if r["date"][:4] == y) for y in sorted({r["date"][:4] for r in rows})}}


# --------------------------------------------------------------------------- #
# Synthetic screen
# --------------------------------------------------------------------------- #
MODES = ("TRUE", "DROP", "BOUND_K2", "BOUND_K3", "BOUND_ALL", "BOUND_ALL_TERMINAL_RESOLVED")


def placement_adjustment(names_by_month, mode):
    """leg_adjust for `A.calendar_time_series`. Each unknown name is (true industry, candidate industries, excess
    return relative to its true industry, terminal flag).

    TRUE places it in its own industry; DROP leaves it out; BOUND_Kk places it, in every cohort-month, in whichever
    of its k candidate industries (the true one plus k-1 others) minimises the leg; BOUND_ALL over every eligible
    industry. A terminal name enters at -100% (no documented consideration) except under ..._TERMINAL_RESOLVED."""
    def adjust(month, cohort, industries, weights, month_returns):
        total = 0.0
        index = {g: i for i, g in enumerate(industries)}
        for true_g, candidates, excess, terminal in names_by_month.get(month, ()):
            if mode == "DROP" or true_g not in index:
                continue
            r_u = -1.0 if terminal and mode != "BOUND_ALL_TERMINAL_RESOLVED" else month_returns[true_g] + excess
            effect = weights * SHARE_IF_PLACED * (r_u - np.array([month_returns[g] for g in industries]))
            if mode == "TRUE":
                total += float(effect[index[true_g]])
            elif mode.startswith("BOUND_ALL"):
                total += float(effect.min())
            else:
                k = int(mode[-1])
                total += float(min(effect[index[g]] for g in candidates[:k] if g in index))
        return total
    return adjust


def _one(args):
    protocol, dgp_name, horizon, replicate, seed, idio = args
    dgp = dict(protocol["dgps"][dgp_name])
    dgp["ic"] = A.matched_monthly_ic(dgp["ic"], horizon, protocol["world"]["plantedRho"])
    rng = np.random.default_rng(np.random.SeedSequence([seed, DGPS.index(dgp_name), horizon, replicate, int(idio * 100)]))
    frame, _ = C.simulate_world(rng, dgp, protocol["world"], A.MONTHLY_HORIZON, protocol["lengths"]["KR"]["firstSignalMonth"])
    pop = frame[frame["cwStatus"].eq("MATURED")]
    months = sorted(pop["date"].unique())
    present = {d: list(g["industry"]) for d, g in pop.groupby("date")}
    every = sorted({g for v in present.values() for g in v})
    names = {}
    for d in months:
        names[d] = []
        for _ in range(UNKNOWN_PER_DATE):
            true_g = present[d][rng.integers(len(present[d]))]
            others = [g for g in rng.permutation(every) if g != true_g]
            names[d].append((true_g, [true_g] + others, float(rng.normal(0, idio)), False))
    for d in rng.choice(months, size=TERMINAL_EVENTS, replace=False):
        g, cand, e, _ = names[d][0]
        names[d][0] = (g, cand, e, True)
    return {mode: float(C.sn_statistic(A.calendar_time_series(frame, C.PLANTED_COLUMN, list(A.CONTROLS), HOLDING_MONTHS[horizon],
                                                               leg_adjust=placement_adjustment(names, mode))))
            for mode in MODES}


def run(replicates=300, workers=4, seed=None, idio=IDIO_MONTHLY[0]):
    protocol = C.load_protocol(formal=True)
    seed = protocol["seeds"]["development"] + 11 if seed is None else seed
    cv = protocol["criticalValues"]["sn"]["0.05"]
    cells = {}
    for dgp in DGPS:
        jobs = [(protocol, dgp, 126, r, seed, idio) for r in range(replicates)]
        with ProcessPoolExecutor(max_workers=workers) as ex:
            rows = list(ex.map(_one, jobs))
        cells[f"KR_H126_{dgp}"] = {mode: round(float(np.mean([r[mode] > cv for r in rows])), 4) for mode in MODES}
    return {"schema": "INDUSTRY_INCLUSION_BOUND_SCREEN_V1",
            "evidenceClass": "SYNTHETIC_DESIGN_SCREEN_NOT_A_FORMAL_CALIBRATION", "historicalOutcomesRead": 0,
            "seed": seed, "replicates": replicates, "test": "SN one-sided 5% (frozen critical value), calendar-time spread",
            "assumptions": {"unknownPerDate": UNKNOWN_PER_DATE, "shareIfPlaced": SHARE_IF_PLACED,
                            "idiosyncraticMonthly": idio, "terminalEventsAtMinus100Pct": TERMINAL_EVENTS,
                            "boundIgnoresRankEffect": True},
            "rejectionRates": cells}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--replicates", type=int, default=300)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--output")
    args = ap.parse_args(argv)
    result = run(args.replicates, args.workers)
    result["realExposure"] = real_exposure()
    text = json.dumps(result, indent=1, sort_keys=True)
    if args.output:
        with open(args.output, "w") as fh:
            fh.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
