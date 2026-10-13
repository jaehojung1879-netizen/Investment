"""Supplemental synthetic calibration for the US H63 spread: the 150-244 names-per-date geometry (prerequisite P3, extension).

WHY. `us-h63-inference-calibration-v1` (P3) evaluated 245-330 names per date. The outcome-blind P4 preflight found 163 defined
weekly signal dates (2013-2016, one in 2026) holding 150-244 complete-case names: inside the study protocol's floor (150) and outside
the calibrated geometry. This module freezes a second, equally synthetic calibration that covers exactly that range.

WHAT CHANGES, AND NOTHING ELSE. Only the universe size (hence names per date), the seed and the replicate bookkeeping. The statistic,
the null, the five data-generating processes, the five interval methods, the Lobato 90% critical value 28.31, the acceptance
thresholds, the three-state Monte Carlo decision and the replicate count are the parent's. They are not re-declared: the effective
protocol is the parent protocol (verified by hash) with the listed keys replaced, and `semantic_differences` proves the rest is equal.

WHAT IS REUSED. `us_h63_inference_calibration` (simulation, residualised weights, every interval, `decide`) is called, not copied;
it is hash-pinned by the parent result and the P4 preflight, so this module imports it and never edits it.

NOT DONE. No real price, return, label, model output or strategy result is read; every return is invented from seeded streams. A PASS
here says an interval keeps its nominal error rates at these sizes under these invented processes. It says nothing about whether the
feature predicts returns, and it does not repair the 212 departed identities without prices (informative missingness is not modelled).
A FAIL or INCONCLUSIVE is recorded and STOPS: dates are not dropped and the rule is not changed to obtain a PASS.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from pipeline import alpha_inference_mc_decision as mc
from pipeline import us_h63_inference_calibration as U

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = "US_H63_INFERENCE_CALIBRATION_V1_SUPPLEMENT"
READINESS = ROOT / "docs/us-readiness"
PARENT_PROTOCOL = READINESS / "us-h63-inference-calibration-v1-protocol.json"
PARENT_RESULT = READINESS / "us-h63-inference-calibration-v1-result.json"
PARENT_CODE = ROOT / "pipeline/us_h63_inference_calibration.py"
PREFLIGHT = READINESS / "us-cash-profitability-exploratory-preflight-v1.json"
PROTOCOL_PATH = READINESS / "us-h63-inference-calibration-v1-supplement-protocol.json"
RESULT_PATH = READINESS / "us-h63-inference-calibration-v1-supplement-result.json"

# pinned identities of the parent calibration (also pinned by the P4 preflight's `identities`)
PARENT_PROTOCOL_SHA256 = "8bb72a8a083125e6506dfeca82eb1def1607b443afab2dc96233b54f7cbcf1ba"
PARENT_RESULT_SHA256 = "a6c34275ab28dd75487a1d3848d311eb7fa2efeefc261f04794e7f8e5a7ae8d7"
PARENT_CODE_SHA256 = "55e1d52b389aa86c9e6d631ada6b25532046f9cd3e77d38e949eefe20cffb1bc"

TARGET_AVAILABLE_NAMES = (150, 200, 244)    # lower protocol floor, middle of the range, one below the parent's smallest geometry
WEEKS = (260, 700)
SEED = 20261013                              # parent 20261012; chosen once, before any replicate
GEOMETRY_CHECK_REPLICATES = 20
GEOMETRY_CHECK_OFFSET = 100000               # replicate index offset: never collides with a scored replicate
GEOMETRY_TOLERANCE_NAMES = 5.0
# top-level keys of the parent protocol that the supplement is allowed to differ on; every other key must be equal
PERMITTED_DIFFERENCES = frozenset({"contract", "status", "purpose", "dgps", "sampleLengths", "monteCarloDecision", "seed", "power",
                                   "prohibitions", "realDataReads"})


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_parent() -> dict[str, Any]:
    """The parent protocol, result and simulation code must be byte-identical to the pinned versions; returns the parent protocol."""
    found = {"protocol": sha256_file(PARENT_PROTOCOL), "result": sha256_file(PARENT_RESULT), "code": sha256_file(PARENT_CODE)}
    expected = {"protocol": PARENT_PROTOCOL_SHA256, "result": PARENT_RESULT_SHA256, "code": PARENT_CODE_SHA256}
    moved = sorted(k for k in expected if found[k] != expected[k])
    if moved:
        raise RuntimeError("PARENT_CALIBRATION_CHANGED: " + ", ".join(moved))
    return json.loads(PARENT_PROTOCOL.read_bytes())


def universe_for(target_available: int, missing_rate: float) -> int:
    """Universe whose mean available names per date equals the target (availability is stationary at 1 - missingRate)."""
    return int(round(target_available / (1.0 - missing_rate)))


def build_dgps(parent: dict[str, Any]) -> list[dict[str, Any]]:
    """Every GATING parent DGP crossed with every target size; nothing but the universe (and the name) is overridden."""
    out = []
    for dgp in parent["dgps"]:
        if not dgp["gating"]:
            continue
        for target in TARGET_AVAILABLE_NAMES:
            cell = copy.deepcopy(dgp)
            cell["name"] = f"{dgp['name']}__N{target}"
            cell["parentDgp"] = dgp["name"]
            cell["targetAvailableNames"] = target
            cell["universe"] = universe_for(target, float(dgp["missingRate"]))
            out.append(cell)
    return out


def historical_geometry() -> dict[str, Any]:
    """Outcome-blind facts about the dates being covered, quoted from the committed P4 preflight."""
    pre = json.loads(PREFLIGHT.read_bytes())
    return {"source": "docs/us-readiness/us-cash-profitability-exploratory-preflight-v1.json", "sourceSha256": sha256_file(PREFLIGHT),
            "definedDatesBelowParentMinimum": pre["calibratedGeometry"]["definedDatesBelowCalibratedMin"],
            "byYear": {y: n for y, n in pre["calibratedGeometry"]["byYear"].items() if n},
            "parentMinimumNamesPerDate": pre["calibratedGeometry"]["minNamesEvaluated"],
            "protocolFloorNamesPerDate": pre["frozenDefinitions"]["minNamesPerDate"],
            "namesPerDateMedianByYear": {y: v["median"] for y, v in pre["namesPerDate"]["byYear"].items() if y in ("2013", "2014", "2015", "2016")},
            "maturedDefinedCohorts": pre["cohorts"]["maturedDefinedCohorts"]}


def build_protocol() -> dict[str, Any]:
    """The supplement protocol exactly as committed (the committed file is tested equal to this)."""
    parent = verify_parent()
    dgps = build_dgps(parent)
    decisions = len(dgps) * len(WEEKS) * 4
    return {
        "contract": CONTRACT,
        "status": "FROZEN_BEFORE_ANY_REPLICATE",
        "outcomeFree": True,
        "realDataReads": "FORBIDDEN: every return is synthetic; the only facts quoted from real data are outcome-blind name counts from the committed P4 preflight",
        "purpose": ("Cover the 150-244 names-per-date geometry that the parent calibration did not evaluate and that 163 defined historical "
                    "signal dates occupy. Same statistic, null, DGPs, methods, critical value 28.31, acceptance thresholds and decision "
                    "rule as the parent; only the universe size, the seed and the cell list differ. Not an alpha study."),
        "parent": {"protocol": "docs/us-readiness/us-h63-inference-calibration-v1-protocol.json", "protocolSha256": PARENT_PROTOCOL_SHA256,
                   "result": "docs/us-readiness/us-h63-inference-calibration-v1-result.json", "resultSha256": PARENT_RESULT_SHA256,
                   "code": "pipeline/us_h63_inference_calibration.py", "codeSha256": PARENT_CODE_SHA256,
                   "rule": "the effective protocol is the parent protocol with only the PERMITTED_DIFFERENCES keys replaced; "
                           "pipeline.us_h63_supplemental_calibration.semantic_differences proves it before any replicate"},
        "historicalGeometry": historical_geometry(),
        "sizeGrid": {"targetAvailableNamesPerDate": list(TARGET_AVAILABLE_NAMES),
                     "rationale": "150 is the study protocol's floor, 244 is the largest size below the parent's smallest geometry (245), 200 is the middle; "
                                  "three fixed points, not a search. Each cell holds ONE size for every date of the series, which is more demanding than "
                                  "the historical series (names per date rise over time)",
                     "universeRule": "round(target / (1 - missingRate)); availability is a stationary persistent Markov process, so mean available names "
                                     "equals the target up to rounding, less the permanent loss of names to unresolved terminal events in MISSING_AND_TERMINAL",
                     "geometryCheck": {"replicates": GEOMETRY_CHECK_REPLICATES, "replicateIndexOffset": GEOMETRY_CHECK_OFFSET,
                                       "toleranceNames": GEOMETRY_TOLERANCE_NAMES,
                                       "rule": "mean realised available names per date over the check replicates must lie within the tolerance of the target, "
                                               "otherwise the cell does not count as covering its size and the supplement is BLOCKED"}},
        "dgps": dgps,
        "sampleLengths": {"weeks": list(WEEKS), "roles": {"260": "registered gate length", "700": "exploratory historical depth (~2013-2026)"},
                          "note": "130 weeks (non-binding futility look, interval not quoted) is not re-evaluated"},
        "monteCarloDecision": {**parent["monteCarloDecision"], "failSideDecisionCount": decisions,
                               "failSideDecisionCountDefinition": f"{len(dgps)} DGP x size cells ({len(dgps) // len(TARGET_AVAILABLE_NAMES)} gating DGPs x "
                                                            f"{len(TARGET_AVAILABLE_NAMES)} sizes) x {len(WEEKS)} lengths x 4 metrics "
                                                            "(coverage, lower-bound error, upper-bound error, undefined frequency) for the primary candidate"},
        "seed": SEED,
        "replicates": parent["replicates"],
        "power": None,
        "verdictRule": {"SUPPLEMENT_PASS": "CT_SN is PASS in every cell (gating DGP x target size x 260/700 weeks) AND every cell's geometry check holds",
                        "SUPPLEMENT_BLOCKED": "any other outcome (any FAIL or INCONCLUSIVE cell, or a cell whose realised geometry misses its target). "
                                              "An INCONCLUSIVE cell is not resolved by rerunning, re-seeding, adding replicates or dropping the cell; "
                                              "a different design is a new contract version. On BLOCKED the 163 dates are NOT dropped and the "
                                              "statistical rule is NOT changed: they remain an uncalibrated extrapolation and are reported as such",
                        "comparators": "SD_SN, SD_NW_L12, CT_NW_AUTO and CT_CBB13 are classified by the same rule and reported; they never gate",
                        "claimBoundary": "PASS covers interval error rates at 150-244 invented names per date for these DGPs. It does not cover informative "
                                         "missingness of departed names, the historical size trajectory as a time-varying process, or real-return behaviour"},
        "prohibitions": ["no real return, price, label, model prediction or strategy PnL is read",
                         "no historical exploratory (P4) study is executed and no outcome budget is consumed",
                         "the parent protocol, result and simulation code are not edited",
                         "sizes, DGPs, weeks, seed, replicate count, thresholds and critical value may not change after the first replicate; a change is a new contract version"],
    }


def semantic_differences(parent: dict[str, Any], effective: dict[str, Any]) -> list[str]:
    """Top-level keys on which the effective protocol differs from the parent."""
    return sorted(k for k in set(parent) | set(effective) if parent.get(k) != effective.get(k))


def effective_protocol(supplement: dict[str, Any], parent: dict[str, Any] | None = None) -> dict[str, Any]:
    """The parent protocol with the supplement's cell list, seed and decision count; refuses anything else that would differ."""
    parent = parent or verify_parent()
    if supplement.get("contract") != CONTRACT or supplement.get("status") != "FROZEN_BEFORE_ANY_REPLICATE":
        raise RuntimeError("SUPPLEMENT_PROTOCOL_NOT_FROZEN")
    if supplement["parent"]["protocolSha256"] != PARENT_PROTOCOL_SHA256:
        raise RuntimeError("SUPPLEMENT_PARENT_MISMATCH")
    eff = copy.deepcopy(parent)
    eff["dgps"] = supplement["dgps"]
    eff["sampleLengths"] = {**parent["sampleLengths"], "weeks": supplement["sampleLengths"]["weeks"]}
    eff["monteCarloDecision"] = supplement["monteCarloDecision"]
    eff["seed"] = supplement["seed"]
    eff["replicates"] = supplement["replicates"]
    eff["power"] = None
    carried = {k: v for k, v in supplement["monteCarloDecision"].items() if k not in ("failSideDecisionCount", "failSideDecisionCountDefinition")}
    inherited = {k: v for k, v in parent["monteCarloDecision"].items() if k not in ("failSideDecisionCount", "failSideDecisionCountDefinition")}
    if carried != inherited:
        raise RuntimeError("SUPPLEMENT_CHANGED_FROZEN_PARENT_KEY: monteCarloDecision")
    if supplement["replicates"] != parent["replicates"]:
        raise RuntimeError("SUPPLEMENT_CHANGED_FROZEN_PARENT_KEY: replicates")
    if any(d["innovation"] != next(p for p in parent["dgps"] if p["name"] == d["parentDgp"])["innovation"] for d in supplement["dgps"]):
        raise RuntimeError("SUPPLEMENT_CHANGED_FROZEN_PARENT_KEY: dgps")
    illegal = set(semantic_differences(parent, eff)) - PERMITTED_DIFFERENCES
    if illegal:
        raise RuntimeError("SUPPLEMENT_UNPERMITTED_DIFFERENCE: " + ", ".join(sorted(illegal)))
    if supplement["seed"] == parent["seed"]:
        raise RuntimeError("SUPPLEMENT_REUSES_PARENT_SEED")
    return eff


# --------------------------------------------------------------------------
# execution pieces (the runner pools these)
# --------------------------------------------------------------------------
def replicate_job(args: tuple) -> dict[str, Any]:
    protocol, dgp_index, weeks, rep = args
    geometry, dgp = U.resolve_dgp(protocol, protocol["dgps"][dgp_index])
    key = (int(protocol["seed"]), dgp_index, weeks, rep)
    return U.replicate_intervals(geometry, dgp, weeks=weeks, seed_key=key, methods_cfg=protocol["methods"])


def geometry_job(args: tuple) -> dict[str, Any]:
    protocol, dgp_index, weeks, k = args
    geometry, dgp = U.resolve_dgp(protocol, protocol["dgps"][dgp_index])
    sim = U.simulate(geometry, dgp, weeks=weeks, seed_key=(int(protocol["seed"]), dgp_index, weeks, GEOMETRY_CHECK_OFFSET + k))
    per_date = sim["available"].sum(axis=1)
    return {"mean": float(per_date.mean()), "min": int(per_date.min()), "max": int(per_date.max())}


def geometry_summary(rows: list[dict[str, Any]], target: int, tolerance: float = GEOMETRY_TOLERANCE_NAMES) -> dict[str, Any]:
    mean = float(np.mean([r["mean"] for r in rows]))
    return {"replicates": len(rows), "targetAvailableNames": target, "meanAvailableNames": mean,
            "minAvailableNamesObserved": int(min(r["min"] for r in rows)), "maxAvailableNamesObserved": int(max(r["max"] for r in rows)),
            "toleranceNames": tolerance, "holds": bool(abs(mean - target) <= tolerance)}


def mean_ci(values: list[float | None]) -> dict[str, Any] | None:
    a = np.array([v for v in values if v is not None], dtype=float)
    if len(a) < 2:
        return None
    se = a.std(ddof=1) / np.sqrt(len(a))
    return {"mean": float(a.mean()), "mc95": [float(a.mean() - 1.96 * se), float(a.mean() + 1.96 * se)], "n": int(len(a))}


def build_cell(protocol: dict[str, Any], dgp_index: int, weeks: int, records: list[dict[str, Any]],
               geometry_rows: list[dict[str, Any]]) -> dict[str, Any]:
    dgp = protocol["dgps"][dgp_index]
    count = int(protocol["monteCarloDecision"]["failSideDecisionCount"])
    decisions = {m: U.decide(records, m, 0.0, protocol["acceptance"], protocol["monteCarloDecision"], count) for m in U.METHODS}
    return {"dgp": dgp["name"], "parentDgp": dgp["parentDgp"], "targetAvailableNames": dgp["targetAvailableNames"],
            "universe": dgp["universe"], "weeks": weeks, "primaryState": decisions[U.PRIMARY_METHOD]["state"], "methods": decisions,
            "geometry": geometry_summary(geometry_rows, dgp["targetAvailableNames"]),
            "nullEstimate": mean_ci([r["_estimate"] for r in records]),
            "meanDefinedDateFraction": float(np.mean([r["_definedFraction"] for r in records]))}


def verdict(cells: list[dict[str, Any]], expected_cells: int) -> dict[str, Any]:
    """SUPPLEMENT_PASS only if every expected cell is present, CT_SN-PASS and has its realised geometry."""
    states: dict[str, int] = {}
    for c in cells:
        states[c["primaryState"]] = states.get(c["primaryState"], 0) + 1
    complete = len(cells) == expected_cells
    all_pass = complete and all(c["primaryState"] == mc.PASS for c in cells)
    geometry_ok = complete and all(c["geometry"]["holds"] for c in cells)
    status = "SUPPLEMENT_PASS" if all_pass and geometry_ok else "SUPPLEMENT_BLOCKED"
    return {"supplementStatus": status, "cellsExpected": expected_cells, "cellsPresent": len(cells), "primaryStateCounts": states,
            "allCellsGeometryAsDesigned": geometry_ok,
            "nonPassingCells": [{"dgp": c["dgp"], "weeks": c["weeks"], "state": c["primaryState"]} for c in cells if c["primaryState"] != mc.PASS],
            "onBlocked": None if status == "SUPPLEMENT_PASS" else "STOP: recorded as-is; no rerun, no re-seed, no extra replicates, no dropped dates, no rule change"}
