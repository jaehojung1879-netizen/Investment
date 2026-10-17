"""rp1-c1-us-exposure-ladder-replication-v1 — the frozen preregistration, the outcome-free readiness and the KR-equivalence audit.

This change computes no US outcome. Three modes exist and none of them reads a US price, return or rate VALUE:

* `verify`      — spec identity, import closure, every pin (the sealed KR spec and result, the reused KR source bytes, the US snapshot when present).
* `readiness`   — the dates-only data-quality gates on the US snapshot and a presence proxy (every observed date carries 1.0) pushed through the
                  frozen state machine on the XNYS calendar, so it shows WHERE each candidate is determinable, never WHAT its state is.
* `equivalence` — reproduces the SEALED KR decision from the retained KR bytes through the calendar-parameterised wrapper. It reads KR values the
                  sealed study already published and opens no new outcome; it proves the wrapper changed nothing but the calendar.

The formal one-shot execution (permit, durable lock, marker, US value reads, sealing) is NOT here. It belongs to a separate change that must respect
the existing approval and lock contract (see `lifecycle` in the spec).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
import math
from pathlib import Path

import pandas as pd

from . import kr_market_risk_anatomy as M
from . import kr_market_risk_anatomy_analysis as AN
from . import kr_market_risk_model as K
from . import kr_market_risk_model_execution as E
from . import kr_market_risk_source_parse as P
from . import rp1_c1_us_exposure as U
from . import rp1_c1_us_sources as SRC
from .kr_model_portfolio_execution import digest, file_hash, import_closure

ROOT = Path(__file__).resolve().parents[1]
STUDY = U.STUDY
SPEC_DIR = "docs/research-program/specs"
RESULT_DIR = "docs/research-program/results"
SPEC_PATH = SPEC_DIR + "/" + STUDY + ".json"
SCIENTIFIC_SIDECAR = SPEC_DIR + "/" + STUDY + ".scientific.sha256"
RESULT_PATH = RESULT_DIR + "/" + STUDY + "-result.json"
MARKER_PATH = RESULT_DIR + "/" + STUDY + "-execution-started.json"
EQUIVALENCE_PATH = RESULT_DIR + "/rp1-c1-kr-equivalence-v1.json"
ENTRY_POINTS = ["pipeline/rp1_c1_us_exposure.py", "pipeline/rp1_c1_us_sources.py", "pipeline/rp1_c1_us_exposure_spec.py"]
KR_SEALED = ("research_specs/kr-market-risk-model-v1.json", "research_specs/kr-market-risk-model-v1.sha256",
             "docs/results/kr-market-risk-model-v1-result.json", "docs/results/kr-market-risk-model-v1-manifest.json",
             "docs/results/kr-market-risk-model-v1-execution-started.json")
DECISION_READY = "READY_FOR_RP1_C1_FORMAL_EXECUTION"
DECISION_BLOCKED = "DATA_BLOCKED_BEFORE_RP1_C1"
DESIGN_PASSED = "DESIGN_CHECK_DETERMINABLE_NOT_A_GATE"
DESIGN_FAILED = "DESIGN_CHECK_NOT_DETERMINABLE"
MIN_DETERMINABLE_SHARE = SRC.S.FAMILY_FAST_COVERAGE        # 0.99, inherited exactly as the sealed KR readiness did
EQUIVALENCE_TOLERANCE = 1e-12
SCIENTIFIC_KEYS = ("model", "portfolio", "evaluation", "decision", "interpretation", "stopRules")


@dataclass
class Counters:
    usValueReads: int = 0
    stateComputationsOnValues: int = 0
    replayCallsOnValues: int = 0
    krSealedReproductionReads: int = 0

    def outcome_free(self):
        return self.usValueReads == 0 and self.stateComputationsOnValues == 0 and self.replayCallsOnValues == 0


# =======================================================================================================================================
# Frozen scientific content (computed from module constants; `load_spec` compares the spec against it on every load)
# =======================================================================================================================================
def model_definition():
    kr = E.model_definition()
    return {
        "inheritedFrom": {"studyId": K.STUDY, "modelVersion": K.MODEL_VERSION, "rule": "every layer, threshold, window, lag, cadence, multiplier, missing-state "
                                                                                          "rule and candidate mapping table is the sealed KR model's, imported"},
        "output": "equityRiskMultiplier in {1.0, 0.7, 0.4} on the US index exposure; never above 1.0",
        "levels": kr["levels"], "candidates": kr["candidates"], "candidateOrder": kr["candidateOrder"], "control": kr["control"],
        "structuralSwitches": kr["structuralSwitches"], "missingState": kr["missingState"], "reEntry": kr["reEntry"],
        "layers": {"SLOW": {**kr["layers"]["SLOW"], "sampling": "calendar month-end XNYS session; carried to later sessions until the next month-end"},
                   "TRANSITION": {**kr["layers"]["TRANSITION"], "state": "past-only expanding percentile of the known VIX level on calendar week-end XNYS sessions >= 0.80",
                                  "expandingHistoryStart": "the first weekly XNYS session of the grid (" + U.GRID_START + " or later)"},
                   "FAST": {**kr["layers"]["FAST"], "input": "YAHOO_GSPC (S&P 500 price index)"}},
        "decisionCadence": "calendar week-end XNYS session (a session whose next XNYS session lies in a later week)",
        "execution": "signal at the decision-date close; trade at the close of the NEXT XNYS session",
        "endDateInvariance": kr["endDateInvariance"],
        "differencesFromKr": [
            {"item": "exchange calendar", "kr": "XKRX", "us": "XNYS", "how": "passed as an argument to the identical sampling arithmetic"},
            {"item": "reference index / FAST input", "kr": "FDR_KS200 (KOSPI 200 price index)", "us": "YAHOO_GSPC (S&P 500 price index)"},
            {"item": "SLOW and TRANSITION inputs", "kr": "FRED DGS10, DGS3MO, VIXCLS", "us": "the SAME retained bytes (no re-acquisition)"},
            {"item": "transaction costs", "kr": "buy 15bp / sell 45bp", "us": f"buy {U.US_BUY_COST * 1e4:g}bp / sell {U.US_SELL_COST * 1e4:g}bp from the US cost table"},
            {"item": "evaluation window", "kr": "2007-01-01 .. 2026-09-17", "us": U.EVALUATION_START + " .. " + U.ANALYSIS_END + " (end inherited)"}],
        "knownConsequences": [
            "the 25% vol63 threshold is the KR constant; US index volatility is lower, so the FAST volatility leg fires less often in the US. It is reported, "
            "not adjusted",
            "the TRANSITION percentile is the same VIX history; its weekly sampling dates move from XKRX to XNYS week-ends"],
    }


def portfolio_definition():
    kr = E.portfolio_definition()
    return {
        "primary": {"asset": "YAHOO_GSPC, the SAME series the states are computed on", "assetBasis": "PRICE_INDEX_NOT_TOTAL_RETURN_NOT_DIRECTLY_INVESTABLE",
                    "cash": "ZERO_USD_NOMINAL", "dividends": "OMITTED_ON_BOTH_LEGS", "conventionBias": kr["conventionBias"],
                    "why": "the exact sealed KR convention, so the replication differs from KR only in the market"},
        "economic": {"asset": "YAHOO_SPY adjusted close", "assetBasis": SRC.SOURCES["YAHOO_SPY"]["basis"], "cash": "FRED_DTB3",
                     "cashDefinition": U.CASH_RATE_DEFINITION, "targets": "identical to the primary reading's (computed from the price-index states)",
                     "role": "reported beside the primary reading; never enters the decision",
                     "ifUnresolved": "when the SPY or DTB3 gate fails the economic reading is ECONOMIC_READING_UNRESOLVED and the primary reading still runs"},
        "start": kr["start"], "rebalance": kr["rebalance"], "trade": kr["trade"],
        "buyCost": U.US_BUY_COST, "sellCost": U.US_SELL_COST,
        "costSemantics": "repository US cost table (commission 5bp + half of a 6bp spread; sell adds 0.30bp); conservative for an ETF",
        "costStress": list(K.COST_STRESS), "grossPath": kr["grossPath"], "passiveReference": kr["passiveReference"],
        "noStockOrIndustrySelection": True, "leverage": kr["leverage"],
    }


def evaluation_definition():
    kr = E.evaluation_definition()
    return {
        "window": {"firstDecisionOnOrAfter": U.EVALUATION_START, "end": U.ANALYSIS_END, "gridStart": U.GRID_START,
                   "reason": "first full month after SPY's listing so both readings share one window; the end is the sealed KR study's analysis end"},
        "metrics": kr["metrics"], "falseAlarm": kr["falseAlarm"], "episodes": kr["episodes"], "rollingLossHorizons": kr["rollingLossHorizons"],
        "reboundHorizons": kr["reboundHorizons"], "halves": kr["halves"], "overlap": kr["overlap"],
        "addedDiagnostics": {
            "monthlyCvar": f"mean of the worst ceil({U.CVAR_LEVEL} x n) calendar-month returns, and the worst month",
            "upDownMarketGap": "per year: sum over passive up days of (passive - candidate) and over passive down days of (candidate - passive); arithmetic",
            "protectionByEpisode": "per >=15% reference episode: share of peak-to-trough sessions at a reduced target; UNPROTECTED when 0",
            "falseAlarmList": "every activation with date, target, H63 forward worst loss and status (FALSE_ALARM / FOLLOWED_BY_LARGE_LOSS / PENDING)",
            "subperiods": [list(p) for p in U.SUBPERIODS],
            "sharpeOverCash": "economic reading only: annualised mean daily excess over the DTB3 interval return / its std (ddof 1) x sqrt(252)",
            "status": "descriptive; frozen before any outcome; none enters the decision"},
    }


def decision_definition():
    return {**E.decision_definition(), "inheritedFrom": K.STUDY, "appliedTo": "the PRIMARY reading (net of 1x US costs)",
            "economicReadingRole": "reported beside the decision; cannot change it"}


def interpretation_definition():
    """How a sealed C1 result is read, fixed before it exists. The KR side is the sealed KR decision."""
    return {
        "krSealed": "NO_CANDIDATE_NOMINATED_CONTROL_RETAINED (C1 dominated C0 on the axes; no meaningful improvement route)",
        "table": [
            {"us": K.NOMINATION_NONE, "reading": "REPLICATED_CONTROL_RETAINED",
             "programme": "the exposure layer is a risk-preference option, not a source of return. Default stays passive 1.0; C0 applies only under an "
                          "explicit owner risk budget. No further threshold or rule search on these layers."},
            {"us": "C1 | C2 | C3", "reading": "NOT_REPLICATED_US_NOMINATION",
             "programme": "inconsistent across markets: no promotion; C0 and the US nominee are both carried into prospective receipts"},
            {"us": K.NOMINATION_TRADEOFF, "reading": "NOT_REPLICATED_US_TRADEOFF",
             "programme": "no nomination in either market; the trade-off is published and every candidate stays in prospective receipts"},
            {"us": "C0 dominated by PASSIVE with no candidate reducing |MDD| below the passive path", "reading": "NO_PROTECTION_IN_US",
             "programme": "the rule does not protect in the US; no US exposure layer"}],
        "economicQuestions": [
            "Does reducing exposure in high-risk states reduce MDD and monthly CVaR? (passive vs candidate, primary and economic readings)",
            "How much up-market return was given up for the loss reduction? (upMarketCostPerYear against downMarketSavingPerYear, reboundMissedH63/H126, "
            "sessionsUntilFullExposure)",
            "Did any candidate raise net annualised return, or only cut volatility and MDD? (net annualizedReturn vs passive; Sharpe over cash in the "
            "economic reading)",
            "Which state errors happened? (falseAlarmList; UNPROTECTED episodes in protectionByEpisode)",
            "Is it worth applying on top of a stock-selection book? Only a reading of THIS index result: the layer scales exposure, so its value on a book "
            "depends on that book's beta and correlation to the index; that is a separate study (see newHypotheses), not a conclusion of C1"],
        "neverConclude": ["the rule predicts crises", "the rule is validated", "a threshold should be changed", "the US result rescues or overturns the KR seal"],
    }


def stop_rules():
    return {
        "beforeTheLock": [
            "spec digest, scientific digest or import closure differs -> refuse (rebuild only if no scientific block changes)",
            "any sealed KR pin or reused KR source byte differs -> refuse",
            "the KR equivalence audit is not EXACT -> refuse",
            "US snapshot missing, identity failed, or the reference misses any XNYS session from FAST warm-up to the analysis end -> DATA_BLOCKED",
            "vendor cross-check YAHOO_GSPC vs FRED_SP500 is CONFLICT or INSUFFICIENT_OVERLAP -> DATA_BLOCKED",
            f"any candidate determinable on < {MIN_DETERMINABLE_SHARE:.0%} of decision dates, or not on the first -> DATA_BLOCKED",
            "a result, marker or execution lock already exists -> refuse"],
        "neverAfterAFailure": ["lower a gate threshold", "change the window", "swap a vendor or splice two vendors", "fill a missing session"],
        "afterTheLock": ["a failure consumes the study; no rerun, no retry with a changed input; the attempt artifact is preserved"],
        "economicReading": "an SPY or DTB3 gate failure marks only the economic reading UNRESOLVED; it never blocks or alters the primary reading",
    }


def new_hypotheses():
    """Proposed SEPARATE studies; none is part of C1, none may be selected using a C1 outcome."""
    return [
        {"id": "C1b-VOL-TARGET", "question": "Does continuous inverse-volatility scaling (target = past-only expanding median of vol63, cap 1.0) beat the "
                                             "discrete C0 ladder on MDD at equal or smaller up-market cost?",
         "literature": "Moreira-Muir 2017 for; Cederburg et al. 2020 and Barroso-Detzel against (out-of-sample and after costs)",
         "constraint": "its target rule must be fixed before any US or KR outcome of it is computed; never chosen from C1"},
        {"id": "C2-STOCK-BOOK-OVERLAY", "question": "Holding the same 0-5 name book fixed, does the sealed market multiplier reduce the book's MDD/CVaR "
                                                    "by more than the up-market cost, given the book's own beta to the index?",
         "constraint": "needs a frozen stock book from another study (e.g. Study A); C1 does not wait for it and it does not wait for C1"},
        {"id": "C1c-REENTRY-SPEED", "question": "Is the cost of de-risking mostly late RE-ENTRY? A study fixing the entry rule and varying only re-entry "
                                                "(memoryless vs a one-step-per-week ramp back to 1.0)",
         "constraint": "one structural switch, pre-registered; never a tuned speed"},
        {"id": "C1d-PROSPECTIVE-RECEIPTS-US", "question": "Record every candidate's US multiplier weekly from a future date, evaluated only after maturity",
         "constraint": "the only route to evidence; needs the US daily price collection approval (docs/us-persistent-daily-collection-v1.md)"}]


def scientific_digest(spec):
    return digest({k: spec[k] for k in SCIENTIFIC_KEYS})


# =======================================================================================================================================
# Pins
# =======================================================================================================================================
def kr_reused_files(root=ROOT):
    return {SRC.KR_SNAPSHOT_DIR + "/" + sid + "/normalized.csv": file_hash(Path(root) / SRC.KR_SNAPSHOT_DIR / sid / "normalized.csv")
            for sid in SRC.REUSED.values()}


def us_snapshot_files(root=ROOT):
    base = Path(root) / SRC.SNAPSHOT_DIR
    if not (base / "audit.json").exists():
        return {}
    return {str(p.relative_to(root)): file_hash(p) for p in sorted(base.rglob("*")) if p.is_file()}


def verify_kr_pins(spec, root=ROOT):
    root = Path(root)
    for rel, wanted in spec["krSealed"]["files"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("SEALED_KR_ARTIFACT_CHANGED: " + rel)
    sealed_inputs = json.loads((root / SRC.KR_SPEC_PATH).read_text())["inputs"]["files"]
    for rel, wanted in spec["inputs"]["reusedKrFiles"].items():
        if file_hash(root / rel) != wanted or sealed_inputs.get(rel) != wanted:
            raise ValueError("REUSED_KR_SOURCE_DIFFERS_FROM_THE_SEALED_KR_PIN: " + rel)
    return True


def verify_us_snapshot(spec, root=ROOT):
    pinned = spec["inputs"]["usSnapshot"]["files"]
    if pinned and us_snapshot_files(root) != pinned:
        raise ValueError("US_SNAPSHOT_CHANGED")
    return bool(pinned)


def load_spec(root=ROOT):
    root = Path(root)
    path = root / SPEC_PATH
    spec = json.loads(path.read_text())
    sha = path.with_suffix(".sha256").read_text().strip()
    if digest(spec) != sha or spec.get("studyId") != STUDY or spec.get("scientificStatus") != U.SCIENTIFIC_STATUS:
        raise ValueError("SPEC_IDENTITY_CHANGED")
    if scientific_digest(spec) != (root / SCIENTIFIC_SIDECAR).read_text().strip():
        raise ValueError("SCIENTIFIC_CONTENT_CHANGED")
    expected = sorted(set(import_closure(spec["entryPoints"], root)) | set(spec["sealedDataInputs"]))
    if expected != sorted(spec["dependencyHashes"]):
        raise ValueError("IMPORT_CLOSURE_CHANGED")
    for rel, wanted in spec["dependencyHashes"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("HARNESS_OR_DEPENDENCY_CHANGED: " + rel)
    verify_kr_pins(spec, root)
    verify_us_snapshot(spec, root)
    built = {"model": model_definition(), "portfolio": portfolio_definition(), "evaluation": evaluation_definition(), "decision": decision_definition(),
             "interpretation": interpretation_definition(), "stopRules": stop_rules()}
    for key, value in built.items():
        if json.loads(json.dumps(spec[key])) != json.loads(json.dumps(value)):
            raise ValueError("MODULE_RULE_DIFFERS_FROM_FROZEN_SPEC: " + key)
    return spec, sha


# =======================================================================================================================================
# Outcome-free readiness (dates only)
# =======================================================================================================================================
def snapshot_audit(root=ROOT):
    path = Path(root) / SRC.SNAPSHOT_DIR / "audit.json"
    return json.loads(path.read_text()) if path.exists() else None


def normalized_dates(path):
    """The FIRST column of a normalized file. No value is parsed."""
    with open(path, newline="") as stream:
        reader = csv.reader(stream)
        next(reader)
        return pd.DatetimeIndex([row[0] for row in reader])


def source_audit_for_gate(root, sid, audit):
    record = (audit or {}).get("sources", {}).get(sid)
    if not record or record.get("status") != "ACQUIRED":
        return None
    dates = normalized_dates(Path(root) / SRC.SNAPSHOT_DIR / sid / "normalized.csv")
    return {"status": "ACQUIRED", "dates": dates, "dropped": record.get("droppedRows", 0), "rows": record.get("rawRows", len(dates)),
            "identityOk": record.get("identityOk", False)}


def presence(dates):
    return pd.Series(1.0, index=pd.DatetimeIndex(dates))


def availability(reference_dates, spread_dates, vix_dates):
    """Presence proxies through the frozen state machine on the XNYS grid: where each candidate is determinable, never what it says."""
    sessions = U.market_sessions("US", str(max(pd.DatetimeIndex(reference_dates).min(), pd.Timestamp(U.GRID_START)).date()), U.ANALYSIS_END)
    states = U.layer_states(presence(reference_dates).reindex(sessions), presence(spread_dates), presence(vix_dates), sessions, "US",
                            SRC.lag_days("FRED_DGS10"), SRC.lag_days("FRED_VIXCLS"))
    schedule = U.decision_schedule(sessions, U.EVALUATION_START, U.ANALYSIS_END, "US")
    return schedule, {cid: K.determinable_share(states, schedule, cid) for cid in K.CANDIDATE_ORDER}


def kr_input_dates(root=ROOT):
    base = Path(root) / SRC.KR_SNAPSHOT_DIR
    return {key: normalized_dates(base / sid / "normalized.csv") for key, sid in SRC.REUSED.items()}


def readiness_audit(root=ROOT, assume_complete_reference=False):
    """DECISION_READY or DECISION_BLOCKED from identities and observation DATES alone. With `assume_complete_reference` (a design check only, never
    a gate) the US reference is taken to quote every XNYS session, so the SLOW/TRANSITION determinability of the retained FRED dates can be shown
    before the US snapshot exists."""
    root = Path(root)
    counters = Counters()
    blockers, checks, details = [], {}, {}
    out = {"studyId": STUDY, "mode": "readiness", "scientificStatus": U.SCIENTIFIC_STATUS, "basedOnAnyReturnResult": False}
    try:
        load_spec(root)
        checks["frozenSpecPinsAndImportClosure"] = True
    except (ValueError, KeyError, OSError) as error:
        checks["frozenSpecPinsAndImportClosure"], details["frozenSpecPinsAndImportClosure"] = False, str(error)
        blockers.append("FROZEN_IDENTITY_NOT_VERIFIED")
    kr = kr_input_dates(root)
    spread_dates = kr["us10y"].intersection(kr["us3m"])
    audit = snapshot_audit(root)
    if assume_complete_reference:
        reference_dates = U.market_sessions("US", U.GRID_START, U.ANALYSIS_END)
        out["referenceBasis"] = "ASSUMED_COMPLETE_XNYS_REFERENCE_DESIGN_CHECK_ONLY"
    else:
        ref_audit = source_audit_for_gate(root, "YAHOO_GSPC", audit)
        if ref_audit is None:
            blockers.append("US_SOURCE_SNAPSHOT_NOT_ACQUIRED")
            out.update(decision=DECISION_BLOCKED, blockers=blockers, checks=checks, details=details, counters=asdict(counters))
            return out
        reference_dates = ref_audit["dates"]
        out["referenceBasis"] = "RETAINED_YAHOO_GSPC_DATES"
    schedule, shares = availability(reference_dates, spread_dates, kr["vix"])
    for cid, share in shares.items():
        ok = share["firstDecisionDeterminable"] and share["share"] is not None and share["share"] >= MIN_DETERMINABLE_SHARE
        checks["determinable_" + cid] = ok
        if not ok:
            blockers.append("CANDIDATE_STATE_NOT_DETERMINABLE: " + cid)
    first_decision = str(schedule["decisionDate"].iloc[0].date()) if len(schedule) else None
    first_execution = str(schedule["executionDate"].iloc[0].date()) if len(schedule) else None
    if not assume_complete_reference:
        ok, reasons, info = SRC.reference_gate(ref_audit, first_decision, U.ANALYSIS_END)
        checks["referenceGate"], details["referenceGate"] = ok, {"reasons": reasons, **info}
        if not ok:
            blockers.extend("REFERENCE: " + r for r in reasons)
        cross = cross_check_status(root, audit)
        checks["vendorCrossCheck"], details["vendorCrossCheck"] = cross.get("status") == "CONSISTENT", cross
        if cross.get("status") != "CONSISTENT":
            blockers.append("VENDOR_CROSS_CHECK_" + str(cross.get("status")))
        economic = economic_gates(root, audit, first_execution)
        details["economicReading"] = economic
    for rel, code in ((RESULT_PATH, "RESULT"), (MARKER_PATH, "MARKER")):
        if (root / rel).exists():
            blockers.append("RP1_C1_" + code + "_ALREADY_COMMITTED")
    checks["noOutcomeAccess"] = counters.outcome_free()
    decision = (DESIGN_PASSED if not blockers else DESIGN_FAILED) if assume_complete_reference else (DECISION_READY if not blockers else DECISION_BLOCKED)
    out.update(decision=decision, blockers=blockers, checks=checks, details=details, counters=asdict(counters),
               decisionDates=int(len(schedule)), firstDecisionDate=first_decision, firstExecutionDate=first_execution,
               lastDecisionDate=str(schedule["decisionDate"].iloc[-1].date()) if len(schedule) else None,
               lastExecutionDate=str(schedule["executionDate"].iloc[-1].date()) if len(schedule) else None,
               determinable=shares, minimumDeterminableShare=MIN_DETERMINABLE_SHARE,
               method="presence proxy: every observed date carries 1.0; the frozen state machine then shows where a state is defined, never its value")
    return out


def cross_check_status(root, audit):
    """The ONE pre-registered value read before the lock: index LEVELS of the two S&P 500 routes on identical dates, tested for equality."""
    a, b = source_audit_for_gate(root, "YAHOO_GSPC", audit), source_audit_for_gate(root, "FRED_SP500", audit)
    if a is None or b is None:
        return {"status": "NOT_ACQUIRED"}
    read = lambda sid: AN.obs_series(P.read_normalized((Path(root) / SRC.SNAPSHOT_DIR / sid / "normalized.csv").read_bytes()))
    return {**SRC.cross_check(read("YAHOO_GSPC"), read("FRED_SP500")), "readsLevelsForEqualityOnly": True}


def economic_gates(root, audit, first_execution):
    asset = source_audit_for_gate(root, "YAHOO_SPY", audit)
    ok_a, reasons_a, info_a = SRC.asset_gate(asset, first_execution, U.ANALYSIS_END)
    cash = source_audit_for_gate(root, "FRED_DTB3", audit)
    if cash is None:
        ok_c, reasons_c, info_c = False, ["NOT_ACQUIRED"], {}
    else:
        ok_c, reasons_c, info_c = SRC.cash_gate(cash["dates"], first_execution, U.ANALYSIS_END)
    status = "ECONOMIC_READING_READY" if ok_a and ok_c else "ECONOMIC_READING_UNRESOLVED"
    return {"status": status, "asset": {"ok": ok_a, "reasons": reasons_a, **info_a}, "cash": {"ok": ok_c, "reasons": reasons_c, **info_c}}


# =======================================================================================================================================
# KR equivalence (reads only the sealed KR study's own retained bytes and compares with its sealed result)
# =======================================================================================================================================
def _compare(x, y, path, bad):
    """Exact structural comparison with a relative tolerance on floats; NaN in a freshly computed value equals a sealed None."""
    if isinstance(x, dict) or isinstance(y, dict):
        if not isinstance(x, dict) or not isinstance(y, dict) or set(x) != set(y):
            bad.append(path + " (keys)")
            return 0.0
        return max([_compare(x[k], y[k], path + "/" + str(k), bad) for k in x] or [0.0])
    if isinstance(x, (list, tuple)) or isinstance(y, (list, tuple)):
        if not isinstance(x, (list, tuple)) or not isinstance(y, (list, tuple)) or len(x) != len(y):
            bad.append(path + " (length)")
            return 0.0
        return max([_compare(p, q, f"{path}[{i}]", bad) for i, (p, q) in enumerate(zip(x, y))] or [0.0])
    if isinstance(x, float) and math.isnan(x):
        x = None
    if x is None or y is None:
        if x is not y:
            bad.append(path)
        return 0.0
    if isinstance(x, bool) or isinstance(y, bool) or isinstance(x, str) or isinstance(y, str):
        if x != y:
            bad.append(path)
        return 0.0
    d = abs(float(x) - float(y))
    if d > EQUIVALENCE_TOLERANCE * max(1.0, abs(float(y))):
        bad.append(path)
    return d


def kr_values(root=ROOT, counters=None):
    base = Path(root) / SRC.KR_SNAPSHOT_DIR
    read = lambda sid: AN.obs_series(P.read_normalized((base / sid / "normalized.csv").read_bytes()))
    if counters is not None:
        counters.krSealedReproductionReads += 4
    return {"reference": read(E.SOURCES["reference"]), "spread": AN.derived_spread(read(E.SOURCES["us10y"]), read(E.SOURCES["us3m"])),
            "vix": read(E.SOURCES["vix"])}


def equivalence_audit(root=ROOT):
    """EXACT when (1) the parameterised calendar functions equal the sealed KR functions on every session of the sealed KR grid, (2) the layer states
    are identical frame for frame, (3) the cash-aware replay with zero cash equals the sealed replay, and (4) the sealed KR result's decision, window,
    passive and candidate blocks are reproduced from the retained KR bytes within 1e-12 (relative)."""
    root = Path(root)
    counters = Counters()
    values = kr_values(root, counters)
    reference = values["reference"][values["reference"].index <= pd.Timestamp(E.INHERITED["analysisEnd"])]
    sessions = M.kr_sessions(str(reference.index.min().date()), E.INHERITED["analysisEnd"])
    checks = {}
    checks["periodEndWeekly"] = bool(U.period_end_sessions(sessions, "W", "KR").equals(K.period_end_sessions(sessions, "W")))
    checks["periodEndMonthly"] = bool(U.period_end_sessions(sessions, "M", "KR").equals(K.period_end_sessions(sessions, "M")))
    ours = U.decision_schedule(sessions, K.EVALUATION_START, E.INHERITED["analysisEnd"], "KR")
    sealed_schedule = K.decision_schedule(sessions, K.EVALUATION_START, E.INHERITED["analysisEnd"])
    checks["decisionSchedule"] = bool(ours.equals(sealed_schedule))
    close = reference.reindex(sessions)
    a = U.layer_states(close, values["spread"], values["vix"], sessions, "KR")
    b = K.layer_states(close, values["spread"], values["vix"], sessions)
    checks["layerStates"] = bool(a.equals(b))
    window = sessions[sessions >= sealed_schedule["executionDate"].iloc[0]]
    bench = close.reindex(window)
    zero = pd.Series(0.0, index=window)
    replay_equal = True
    for cid in K.CANDIDATE_ORDER:
        t = K.candidate_targets(b, sealed_schedule, cid)["target"].tolist()
        replay_equal &= U.replay_path_with_cash(bench, sealed_schedule, t, zero).equals(K.replay_path(bench, sealed_schedule, t))
    checks["zeroCashReplayEqualsSealedReplay"] = bool(replay_equal)
    result = U.evaluate(values, U.kr_sealed_config())
    sealed = json.loads((root / E.RESULT_PATH).read_text())
    blocks = {}
    for key in ("decision", "window", "passive", "candidates"):
        bad = []
        worst = _compare(json.loads(json.dumps(E.json_safe(result[key]))), sealed[key], key, bad)
        blocks[key] = {"maxAbsoluteDifference": worst, "mismatches": bad[:20], "mismatchCount": len(bad)}
        checks["sealedResult_" + key] = not bad
    return {"studyId": STUDY, "mode": "equivalence", "status": "EXACT" if all(checks.values()) else "DIFFERS", "checks": checks, "sealedBlocks": blocks,
            "sealedKrResultSha256": file_hash(root / E.RESULT_PATH), "sealedKrSpecSha256": (root / "research_specs/kr-market-risk-model-v1.sha256").read_text().strip(),
            "krInputs": {E.SNAPSHOT_DIR + "/" + sid + "/normalized.csv": file_hash(root / E.SNAPSHOT_DIR / sid / "normalized.csv") for sid in E.SOURCES.values()},
            "tolerance": EQUIVALENCE_TOLERANCE, "counters": asdict(counters), "usValuesRead": counters.usValueReads,
            "meaning": "the wrapper changes only the calendar argument; on XKRX it IS the sealed KR study. No new KR outcome is opened: every compared "
                       "number is already in the sealed KR result."}


def verify(root=ROOT):
    spec, sha = load_spec(root)
    counters = Counters()
    return {"studyId": STUDY, "mode": "verify", "status": "VERIFIED", "specSha256": sha, "scientificSha256": scientific_digest(spec),
            "usSnapshotPinned": bool(spec["inputs"]["usSnapshot"]["files"]), "dependencyFiles": len(spec["dependencyHashes"]),
            "counters": asdict(counters), "outcomeFree": counters.outcome_free(), "formalExecutionInThisChange": False}

