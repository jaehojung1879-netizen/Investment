"""rp1-inference-calibration-v1 (Track A / WP1) — can a 6- or 12-month forecast claim be told apart from zero on the samples we have?

Synthetic only. No price, return, label, winner flag, score or strategy outcome is read: every return here is INVENTED from seeded RNG
streams. The only repository facts used are exchange CALENDARS (to count how many weekly signal dates have a matured forward window).

WHAT IS REUSED, NOT COPIED. The frozen v4 calendar-time engine (`alpha_inference_calibration_v4`): its synthetic panel
(`simulate_replicate`), calendar-time attribution (`calendar_time_series`), self-normalized interval (`calendar_time_sn_interval`, U1
critical value 66.57), the five confirmatory statistics and their weights (`statistic_designs`, `_centred_rank_weights`), the per-replicate
driver (`replicate_intervals`) and the three-state Clopper-Pearson decision (`decide_statistic`, `alpha_inference_mc_decision`). The DGPs,
geometry, statistics, interval, thresholds and Monte Carlo decision levels are v5's protocol sections, inherited verbatim and compared
key by key on every load (`semantic_differences`). The replicate budget is v5's precision rule recomputed (`v5.chosen_replicates()`).

WHAT IS NEW, AND ONLY THIS. (1) The horizon/depth cells: H252 and H126 at 78 and 312 weeks and at each claim's ACTUAL matured sample
depth. (2) The FAIL-side Bonferroni count, recomputed for those cells by the frozen rule (all registered decisions). (3) One new seed.
(4) Descriptive power read-outs computed from the same null replicates, which gate nothing.

WHY THE CELL LOOP IS HERE. `v4.run_calibration` validates the v4 decision count (360) and cannot run any other grid, so this module calls
the same per-cell functions v4.run_calibration calls, in the same order; a test proves it returns v4's own cell bytes on a v4 protocol.

REGION. The v4 engine has no region parameter: its panel is defined by names per date, horizon, depth and DGP. A region therefore enters
only through its actual matured depth. KR H252 and US H252 share their 78- and 312-week cells (one computation, reported for both);
cross-sectional size is v4's 60 names in every cell, a stated limitation, not a US geometry claim.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.stats import norm

from pipeline import alpha_inference_calibration_v4 as v4
from pipeline import alpha_inference_calibration_v5 as v5
from pipeline import alpha_inference_mc_decision as mc
from pipeline import replay_calendar as RC
from pipeline.alpha_inference_calibration_v1 import _aggregate

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "RP1_INFERENCE_CALIBRATION_V1"
STUDY = "rp1-inference-calibration-v1"
SPEC_PATH = "docs/research-program/specs/rp1-inference-calibration-v1.json"
RESULT_PATH = "docs/research-program/results/rp1-inference-calibration-v1-result.json"
V5_SPEC_PATH = "research_specs/alpha-inference-calibration-v5.json"
V5_SPEC_SHA256 = "b32e1fad5f06ad61e11fb80801b8ba833f1b26d1a3a95233e48395d50a6bf5cc"   # the frozen v5 protocol this one inherits from
SEED = 20261018
# Every seed a committed study in this repository already consumed; the WP1 seed differs from all of them.
PRIOR_SEEDS = {**v5.PRIOR_SEEDS, "alpha-inference-calibration-v5": v5.FORMAL_PINS["seed"], "us-h63-supplemental-calibration": 20261013,
               "us-capital-allocation-evaluation": 20261012, "us-capital-allocation-policy": 20261011, "spec-seed-20261009": 20261009,
               "spec-seed-20261006": 20261006, "rp1-c1-synthetic-dry-run": 20261017}

# ---- the sample whose depth is calibrated (calendars only) ------------------------------------------------------------------------------
SAMPLE = {"firstSignalOnOrAfter": "2013-01-01", "lastDataSession": "2026-09-14",
          "grid": "the last exchange session of each calendar week (KR: XKRX, US: XNYS)",
          "matured": "a weekly signal date t is matured for horizon H when position(t) + 1 + H <= position(last data session): the trade is at "
                     "the next session's close and the window needs H further sessions",
          "why": "2013-01 is Study A's history start in both markets; 2026-09-14 is the last session of the sealed replay-v16 inputs; only "
                 "matured cohorts can enter a primary statistic"}
CLAIMS = (("KR", 252), ("US", 126), ("US", 252))
SCENARIO_DEPTHS = (78, 312)
INHERITED_KEYS = ("outcomeFree", "namesPerDate", "signalStepSessions", "confidence", "dgps", "dgpRationale", "nullConstruction",
                  "selectionFraction", "syntheticForecastScale", "statistics", "intervalConstruction", "descriptiveIntervalConstruction",
                  "undefinedStatistics", "acceptance")
MONTE_CARLO_INHERITED = ("purpose", "intervalMethod", "passSideOneSidedAlpha", "failSideFamilywiseAlpha", "failSideAdjustment",
                         "multiplicityRationale")
OWN_KEYS = ("contract", "studyId", "protocolStatus", "purpose", "seed", "priorSeeds", "simulationReplicates", "precisionCriterion",
            "predecessorSpecPath", "predecessorSpecSha256", "engineIdentity", "sample", "claims", "cells", "monteCarloDecision",
            "claimDecision", "studyABranch", "descriptivePower", "regionNote", "runRule", "prohibitions")
POWER_LEVEL = 0.80


def v5_spec(root=ROOT):
    raw = (Path(root) / V5_SPEC_PATH).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def engine_files(root=ROOT):
    """Every file the reused engine executes, plus the v5 module (budget rule) and this module's calendar source."""
    files = dict(v5.FORMAL_PINS["engineFiles"])
    for rel in ("pipeline/alpha_inference_calibration_v5.py",):
        files[rel] = hashlib.sha256((Path(root) / rel).read_bytes()).hexdigest()
    return files


# =======================================================================================================================================
# Depths from calendars (dates only)
# =======================================================================================================================================
def matured_weeks(market, horizon, sample=SAMPLE):
    """Number of weekly signal dates with a matured H-session window. Reads exchange calendars only."""
    sessions = RC.sessions(sample["firstSignalOnOrAfter"], sample["lastDataSession"], market)
    grid = sessions.to_series().groupby(sessions.to_period("W")).max()
    position = {d: i for i, d in enumerate(sessions)}
    last = len(sessions) - 1
    return int(sum(1 for d in grid if position[d] + 1 + horizon <= last))


def claim_depths():
    return {f"{market}_H{h}": matured_weeks(market, h) for market, h in CLAIMS}


def registered_cells():
    """{horizon: sorted depths}: the 78- and 312-week scenarios plus every claim's actual depth at that horizon."""
    depths = claim_depths()
    out = {}
    for market, h in CLAIMS:
        out.setdefault(h, set(SCENARIO_DEPTHS)).add(depths[f"{market}_H{h}"])
    return {str(h): sorted(v) for h, v in sorted(out.items())}


def decision_count(cells, dgps):
    return len(dgps) * sum(len(v) for v in cells.values()) * len(v4.CONFIRMATORY) * v4.METRICS_PER_STATISTIC


# =======================================================================================================================================
# The frozen protocol (built from module constants and the v5 protocol; `load_spec` compares a committed spec against it)
# =======================================================================================================================================
def build_spec(root=ROOT):
    base, base_sha = v5_spec(root)
    cells = registered_cells()
    count = decision_count(cells, base["dgps"])
    depths = claim_depths()
    spec = {key: base[key] for key in INHERITED_KEYS}
    spec.update({
        "contract": CONTRACT, "studyId": STUDY,
        "protocolStatus": "FROZEN_BEFORE_ANY_FORMAL_REPLICATE",
        "purpose": "Synthetic calibration of the calendar-time SN interval at H252 (KR, US) and H126 (US) on 78 and 312 weeks and on each "
                   "claim's actual matured sample depth. It decides which 6- or 12-month horizon may carry a PRIMARY confirmatory claim in "
                   "Study A and reads no market outcome.",
        "seed": SEED, "priorSeeds": PRIOR_SEEDS,
        "simulationReplicates": v5.chosen_replicates(),
        "precisionCriterion": {**base["precisionCriterion"], "inheritedFrom": "alpha-inference-calibration-v5",
                               "derivedBy": "pipeline.alpha_inference_calibration_v5.chosen_replicates (recomputed on every load)"},
        "predecessorSpecPath": V5_SPEC_PATH, "predecessorSpecSha256": base_sha,
        "engineIdentity": {"module": "pipeline.alpha_inference_calibration_v4", "contract": v4.CONTRACT,
                           "called": ["simulate_replicate", "statistic_designs", "calendar_time_series", "calendar_time_sn_interval",
                                      "replicate_intervals", "decide_statistic", "alpha_inference_calibration_v1._aggregate",
                                      "alpha_inference_mc_decision.top_level_status"],
                           "files": engine_files(root),
                           "rule": "the runner verifies every file's sha256 before any simulation; an engine file is never edited"},
        "sample": SAMPLE,
        "claims": {f"{m}_H{h}": {"market": m, "horizonSessions": h, "actualMaturedWeeks": depths[f"{m}_H{h}"],
                                 "nonOverlappingWindows": round(depths[f"{m}_H{h}"] * 5 / h, 3)} for m, h in CLAIMS},
        "cells": {"horizons": cells, "dgps": [d["name"] for d in base["dgps"]], "count": len(base["dgps"]) * sum(len(v) for v in cells.values()),
                  "rule": "every (horizon, depth, DGP) cell is evaluated with the unchanged v4 per-replicate driver; KR and US claims at the same "
                          "horizon share the 78- and 312-week cells because the engine has no region parameter"},
        "monteCarloDecision": {**{k: base["monteCarloDecision"][k] for k in MONTE_CARLO_INHERITED},
                               "failSideDecisionCount": count,
                               "failSideDecisionCountDefinition": f"registered cells ({len(base['dgps'])} DGPs x "
                                                                  f"{sum(len(v) for v in cells.values())} horizon/depth pairs) x confirmatory "
                                                                  f"statistics ({len(v4.CONFIRMATORY)}) x metrics ({v4.METRICS_PER_STATISTIC}); "
                                                                  f"each FAIL-side decision uses one-sided alpha 0.05/{count}"},
        "claimDecision": {
            "rule": "a claim (market, horizon) is CALIBRATED_FOR_PRIMARY_INFERENCE only if every DGP cell at its ACTUAL matured depth is "
                    "PASS (all five confirmatory statistics, all three metrics); any FAIL there is NOT_CALIBRATED_FAIL; otherwise "
                    "NOT_CERTIFIED_INCONCLUSIVE. The 78- and 312-week cells are depth scenarios: reported, and they enter the FAIL-side "
                    "multiplicity count, but they do not decide a claim.",
            "consequence": "a claim that is not CALIBRATED_FOR_PRIMARY_INFERENCE is DESCRIPTIVE ONLY for that market and horizon; it is never "
                           "re-seeded, re-run with more replicates, re-thresholded or rescued by another interval in this protocol"},
        "studyABranch": {
            "source": "docs/research-program/03-studies-abc-ko.md section A: H252 is primary if WP1 calibration passes; otherwise H126 is "
                      "primary and H252 is descriptive",
            "KR": "H252 if KR_H252 is CALIBRATED_FOR_PRIMARY_INFERENCE, else H126 (calibrated by alpha-inference-calibration-v5 at 312/624 "
                  "weeks; the KR H126 actual depth exceeds 312 weeks)",
            "US": "H252 if US_H252 is CALIBRATED_FOR_PRIMARY_INFERENCE, else H126 if US_H126 is, else NONE: no US horizon may carry a primary "
                  "Study A claim and US Study A is descriptive / prospective only"},
        "descriptivePower": {
            "gates": "nothing",
            "alternative": "a uniform-accrual location shift: a true effect theta adds theta x x(w) to every calendar-week contribution D(w). "
                           "The SN normalizer is then unchanged and the estimate shifts by exactly theta, so the null replicates give the "
                           "exact power curve: the interval's lower bound exceeds zero iff theta > halfWidth - estimate.",
            "mde80": f"the {POWER_LEVEL:.0%} quantile of (halfWidth - estimate) over the defined null replicates, in the statistic's own units",
            "mde80InEstimatorSd": "mde80 / sd(estimate): the MDE as a multiple of the estimator's standard deviation (unit free)",
            "gaussianReference": "z_{1-0.025/2} + z_{0.80}, the same multiple for an interval with KNOWN variance at the same 97.5% level",
            "units": "the synthetic panel's units are arbitrary; only unit-free multiples transfer to a real study"},
        "regionNote": "Region enters only through the actual matured depth; 60 names per date in every cell (v4 geometry).",
        "runRule": "One formal run of this exact spec, made after the spec commit and before any other formal replicate, with "
                   "`scripts/run_rp1_inference_calibration.py formal`; its output bytes are committed unchanged. The result is accepted only "
                   "if its specSha256 equals this file's digest. The run is deterministic (fixed unit order, seeded streams, one BLAS thread), "
                   "so the existing Tests workflow re-runs fixed cells with the formal seed and requires byte-identical cells; `reproduce` "
                   "re-runs a larger fixed subset on demand. No workflow file is added or edited (the workflow inventory and every workflow "
                   "path are pinned by sealed specs and by the rp1-c1 scope test). A different seed, replicate count, cell, threshold or "
                   "interval needs a NEW protocol identity.",
        "prohibitions": ["no market data, label, winner flag or strategy outcome", "no edit of any v1-v5 engine file or the v4/v5 protocols",
                         "no re-seed, re-run for a different verdict, replicate increase, threshold change or cell change after a result",
                         "a development smoke uses another seed and at most 50 replicates, carries no verdict and is never committed"],
    })
    return spec


def digest(spec):
    return hashlib.sha256((json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()).hexdigest()


def semantic_differences(base, spec):
    """INHERITED keys must equal v5's; every other key must be one of this protocol's own keys."""
    mismatches = [k for k in INHERITED_KEYS if base.get(k) != spec.get(k)]
    mismatches += [f"monteCarloDecision.{k}" for k in MONTE_CARLO_INHERITED
                   if base.get("monteCarloDecision", {}).get(k) != spec.get("monteCarloDecision", {}).get(k)]
    unclassified = sorted(set(spec) - set(INHERITED_KEYS) - set(OWN_KEYS))
    return {"inheritedMismatches": mismatches, "unclassifiedKeys": unclassified}


def load_spec(root=ROOT):
    root = Path(root)
    path = root / SPEC_PATH
    raw = path.read_bytes()
    spec = json.loads(raw)
    sha = hashlib.sha256(raw).hexdigest()
    if path.with_suffix(".sha256").read_text().strip() != sha:
        raise ValueError("SPEC_SIDECAR_MISMATCH")
    if spec != build_spec(root):
        raise ValueError("SPEC_DIFFERS_FROM_MODULE_DEFINITION")
    base, base_sha = v5_spec(root)
    if spec["predecessorSpecSha256"] != base_sha or base_sha != V5_SPEC_SHA256:
        raise ValueError("V5_PROTOCOL_CHANGED")
    differences = semantic_differences(base, spec)
    if differences["inheritedMismatches"] or differences["unclassifiedKeys"]:
        raise ValueError(f"PROTOCOL_DIFFERS: {differences}")
    if spec["seed"] in PRIOR_SEEDS.values():
        raise ValueError("SEED_REUSES_A_CLOSED_PROTOCOL")
    if spec["simulationReplicates"] != v5.chosen_replicates() or spec["simulationReplicates"] != 8000:
        raise ValueError("REPLICATES_DO_NOT_MATCH_THE_V5_PRECISION_RULE")
    for rel, wanted in spec["engineIdentity"]["files"].items():
        if hashlib.sha256((root / rel).read_bytes()).hexdigest() != wanted:
            raise ValueError("ENGINE_FILE_CHANGED: " + rel)
    return spec, sha


# =======================================================================================================================================
# Execution (the same per-cell sequence v4.run_calibration uses)
# =======================================================================================================================================
def engine_spec(spec):
    """The dictionary the v4 per-replicate functions read: this protocol under the v4 contract label."""
    return {**spec, "contract": v4.CONTRACT}


def power_readout(intervals):
    measured = [r for r in intervals if r is not None]
    if len(measured) < 2:
        return None
    estimate = np.array([r["estimate"] for r in measured])
    half = np.array([(r["upper"] - r["lower"]) / 2.0 for r in measured])
    sd = float(estimate.std(ddof=1))
    mde = float(np.quantile(half - estimate, POWER_LEVEL))
    level = 1.0 - (1.0 - 0.975) / 2.0
    return {"definedReplicates": len(measured), "estimateSd": sd, "medianHalfWidth": float(np.median(half)), "mde80": mde,
            "mde80InEstimatorSd": mde / sd if sd > 0 else None,
            "medianHalfWidthInEstimatorSd": float(np.median(half)) / sd if sd > 0 else None,
            "gaussianReferenceInEstimatorSd": float(norm.ppf(level) + norm.ppf(POWER_LEVEL))}


def run_cell(spec, dgp_index, horizon, weeks, replicates=None, power=True):
    """One (DGP, horizon, depth) cell, exactly as `v4.run_calibration` computes it, plus the non-gating power read-out."""
    engine = engine_spec(spec)
    dgp = spec["dgps"][dgp_index]
    sims = int(spec["simulationReplicates"] if replicates is None else replicates)
    cell = {"dgp": dgp["name"], "horizonSessions": int(horizon), "calendarWeeks": int(weeks),
            "nonOverlappingWindows": round(int(weeks) * int(spec["signalStepSessions"]) / int(horizon), 3)}
    records = [v4.replicate_intervals(engine, dgp, horizon=int(horizon), weeks=int(weeks), replicate=r, dgp_index=dgp_index)
               for r in range(sims)]
    decisions = {s: v4.decide_statistic([rec[s]["primary"] for rec in records], sims, engine) for s in v4.CONFIRMATORY}
    comparator = {s: _aggregate([rec[s]["comparator"] for rec in records], sims) for s in v4.CONFIRMATORY + v4.DESCRIPTIVE}
    cell.update({"status": mc.combine_states([d["state"] for d in decisions.values()]), "statistics": decisions,
                 "failures": {k: d["failureCodes"] for k, d in decisions.items() if d["failureCodes"]},
                 "inconclusive": {k: d["inconclusiveCodes"] for k, d in decisions.items() if d["inconclusiveCodes"]},
                 "descriptive": {"rankIC": comparator["rankIC"]}, "nonGatingV3SignalDateComparator": comparator})
    if power:
        cell["descriptivePower"] = {s: power_readout([rec[s]["primary"] for rec in records]) for s in v4.CONFIRMATORY}
    return cell


def _unit(args):
    spec, dgp_index, horizon, weeks, replicates = args
    return run_cell(spec, dgp_index, horizon, weeks, replicates)


def units(spec):
    return [(d, int(h), int(w)) for d in range(len(spec["dgps"])) for h, depths in spec["cells"]["horizons"].items() for w in depths]


def claim_verdicts(spec, cells):
    out = {}
    for name, claim in spec["claims"].items():
        at_depth = [c for c in cells if c["horizonSessions"] == claim["horizonSessions"] and c["calendarWeeks"] == claim["actualMaturedWeeks"]]
        states = [c["status"] for c in at_depth]
        verdict = ("CALIBRATED_FOR_PRIMARY_INFERENCE" if states and all(s == mc.PASS for s in states)
                   else "NOT_CALIBRATED_FAIL" if mc.FAIL in states else "NOT_CERTIFIED_INCONCLUSIVE")
        profile = {}
        for depth in sorted({c["calendarWeeks"] for c in cells if c["horizonSessions"] == claim["horizonSessions"]}):
            depth_states = [c["status"] for c in cells if c["horizonSessions"] == claim["horizonSessions"] and c["calendarWeeks"] == depth]
            profile[str(depth)] = mc.combine_states(depth_states)
        out[name] = {**claim, "verdict": verdict, "cellsAtActualDepth": {c["dgp"]: c["status"] for c in at_depth},
                     "depthProfile": profile}
    return out


def study_a_branch(verdicts):
    kr = "H252" if verdicts["KR_H252"]["verdict"] == "CALIBRATED_FOR_PRIMARY_INFERENCE" else "H126"
    if verdicts["US_H252"]["verdict"] == "CALIBRATED_FOR_PRIMARY_INFERENCE":
        us = "H252"
    elif verdicts["US_H126"]["verdict"] == "CALIBRATED_FOR_PRIMARY_INFERENCE":
        us = "H126"
    else:
        us = "NONE_DESCRIPTIVE_OR_PROSPECTIVE_ONLY"
    return {"KR": kr, "US": us}


def run_calibration(spec, *, workers=1, replicates=None, progress=None):
    """Every registered cell, in the fixed unit order; a pool changes wall time only."""
    jobs = [(spec, d, h, w, replicates) for d, h, w in units(spec)]
    if workers > 1:
        from multiprocessing import get_context
        with get_context("spawn").Pool(workers) as pool:
            cells = []
            for cell in pool.imap(_unit, jobs):
                cells.append(cell)
                if progress:
                    progress(cell)
    else:
        cells = []
        for job in jobs:
            cells.append(_unit(job))
            if progress:
                progress(cells[-1])
    verdicts = claim_verdicts(spec, cells)
    status = mc.top_level_status(cell_states=[c["status"] for c in cells], insufficient_depth_cells=0)
    return {"contract": CONTRACT, "studyId": STUDY, "outcomeFree": True, "seed": spec["seed"],
            "simulationReplicates": int(spec["simulationReplicates"] if replicates is None else replicates),
            "monteCarloDecision": spec["monteCarloDecision"], "acceptance": spec["acceptance"], "statistics": spec["statistics"],
            "cells": cells, "primaryStatus": status,
            "statusCounts": {s: sum(1 for c in cells if c["status"] == s) for s in (mc.PASS, mc.FAIL, mc.INCONCLUSIVE)},
            "claims": verdicts, "studyABranch": study_a_branch(verdicts),
            "primaryStatusMeaning": "the conjunction over every registered cell, depth scenarios included; a claim's usability is "
                                    "claims[*].verdict, decided at its actual depth only (claimDecision)"}

