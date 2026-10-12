"""Outcome-blind refresh of the US cash-profitability P4 readiness checklist after the supplemental calibration.

Reads only committed JSON reports (the v1 checklist, the P4 preflight, the supplemental calibration result) and the pinned-identity
table; reads no price, return, label or model output and builds no cohort. It does not edit v1: it writes a v2 report that

* replaces the one checklist item the supplement bears on (`CALIBRATED_GEOMETRY`) with a state derived from the supplement verdict,
* keeps every other v1 item exactly as it was measured (nothing is upgraded because a neighbouring item improved), and
* groups the open items the way the owner has to decide them: calibration, survivorship, membership/identity, authorization, lock.

Whether a limitation is TECHNICAL (code a later PR can write) or an OWNER DECISION (risk acceptance, authorization) is stated per item.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT = "US_CASH_PROFITABILITY_EXPLORATORY_V1"
V2_CONTRACT = "US_CASH_PROFITABILITY_EXPLORATORY_READINESS_V2"

TECHNICAL = "TECHNICAL"
OWNER = "OWNER_DECISION"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def calibrated_geometry_item(v1_item: dict[str, Any], supplement: dict[str, Any]) -> dict[str, Any]:
    """CALIBRATED_GEOMETRY derived from the supplement verdict; PASS only if the supplement is a non-development SUPPLEMENT_PASS."""
    verdict = supplement["verdict"]
    passed = (verdict["supplementStatus"] == "SUPPLEMENT_PASS" and not supplement["developmentOnly"]
              and verdict["cellsPresent"] == verdict["cellsExpected"])
    evidence = {"parentMinimumNamesPerDate": v1_item["evidence"]["calibratedMinimumNamesPerDate"],
                "definedDatesBelowParentMinimum": v1_item["evidence"]["definedDatesBelowIt"], "byYear": v1_item["evidence"]["byYear"],
                "supplementStatus": verdict["supplementStatus"], "cellsPresent": verdict["cellsPresent"], "cellsExpected": verdict["cellsExpected"],
                "primaryStateCounts": verdict["primaryStateCounts"], "nonPassingCells": verdict["nonPassingCells"],
                "supplementReplicates": supplement["replicates"], "supplementProtocolSha256": supplement["protocolSha256"]}
    if passed:
        return {"id": "CALIBRATED_GEOMETRY", "state": "PASS", "evidence": evidence,
                "scope": "CT_SN keeps its nominal 90% coverage, one-sided errors and defined-interval frequency at 150, 200 and 244 invented "
                         "names per date for the five gating DGPs at 260 and 700 weeks, in addition to the parent's 245-330. Not covered: "
                         "informative missingness of departed names, the time-varying size trajectory as one process, and real-return behaviour",
                "classification": TECHNICAL}
    return {"id": "CALIBRATED_GEOMETRY", "state": "BLOCKED", "evidence": evidence,
            "condition": "the supplemental calibration did not PASS; it is recorded and stopped. The 163 defined dates are NOT dropped and the "
                         "statistical rule is NOT changed: they remain an uncalibrated extrapolation the owner would have to accept or a new "
                         "calibration contract would have to address",
            "classification": OWNER}


def refresh(v1: dict[str, Any], preflight: dict[str, Any], supplement: dict[str, Any], identities_now: dict[str, str],
            v1_sha256: str, preflight_sha256: str, supplement_sha256: str) -> dict[str, Any]:
    if v1["contract"] != CONTRACT or preflight["contract"] != CONTRACT or v1["executed"] is not False:
        raise ValueError("INPUT_REPORTS_NOT_THE_OUTCOME_FREE_P4_REPORTS")
    if preflight["counters"]["outcomeReads"] != 0 or preflight["counters"]["intervalComputations"] != 0:
        raise ValueError("PREFLIGHT_COUNTERS_NOT_ZERO")
    pinned = preflight["identities"]
    stale = sorted(k for k in pinned if identities_now.get(k) != pinned[k])
    if stale or set(identities_now) != set(pinned):
        raise ValueError("PINNED_IDENTITY_CHANGED: " + ",".join(stale or sorted(set(identities_now) ^ set(pinned))))
    items = {i["id"]: i for i in v1["items"]}
    geometry = calibrated_geometry_item(items["CALIBRATED_GEOMETRY"], supplement)
    survivorship, membership = items["DEPARTED_SECURITIES_AND_TERMINAL_CONSIDERATION"], items["UNIVERSE_MEMBERSHIP_AND_IDENTITY"]
    exposure, authorization, lock = items["OUTCOME_EXPOSURE_AND_BUDGET"], items["OWNER_AUTHORIZATION"], items["DURABLE_ONE_SHOT_LOCK"]
    carried = [items[k] for k in ("PIT_FINANCIAL_STATEMENT_VISIBILITY", "PRICE_AND_CORPORATE_ACTION_CONSISTENCY", "COMPLETE_CASE_SAMPLE",
                                  "H63_OUTCOME_CONSTRUCTION", "CT_SN_INFERENCE_CONTRACT", "FROZEN_DEFINITIONS_NO_LEAKAGE")]
    groups = {
        "calibrationReadiness": {"state": geometry["state"], "items": [geometry],
                                 "parentP3": {"status": "PASS", "gatingCells": "260 and 700 weeks, 245-330 names per date"}},
        "survivorshipLimitation": {"state": survivorship["state"], "classification": OWNER, "items": [survivorship],
                                   "mustRemainVisible": "212 of 324 departed identities have no price history; the sample is survivor-conditioned and is "
                                                        "NEVER described as survivorship-unbiased. ABANDON may partly reflect the missing departed names; "
                                                        "CONTINUE is not confirmation. Not repairable here"},
        "membershipAndIdentityLimitation": {"state": membership["state"], "classification": OWNER, "items": [membership],
                                            "mustRemainVisible": "stale snapshots inside 21 gaps over 45 days (max 769), 7,260 member-dates excluded as "
                                                                 "IDENTITY_AMBIGUOUS, only 14 verified renames"},
        "outcomeExposure": {"state": exposure["state"], "classification": OWNER, "items": [exposure]},
        "ownerAuthorization": {"state": authorization["state"], "classification": OWNER, "items": [authorization]},
        "durableOneShotLock": {"state": lock["state"], "classification": TECHNICAL, "items": [lock],
                               "note": "the workflow and ref logic is code (technical), but creating it for this study is part of the owner-gated PR"},
    }
    ready_to_authorize = geometry["state"] == "PASS"
    return {
        "contract": V2_CONTRACT, "study": v1["study"], "supersedes": {"path": "docs/us-readiness/us-cash-profitability-exploratory-readiness-v1.json",
                                                                      "sha256": v1_sha256, "note": "v1 is left unedited"},
        "authorizes": "NOTHING", "executed": False, "outcomeFree": True,
        "inputs": {"preflight": {"path": "docs/us-readiness/us-cash-profitability-exploratory-preflight-v1.json", "sha256": preflight_sha256},
                   "supplementResult": {"path": "docs/us-readiness/us-h63-inference-calibration-v1-supplement-result.json", "sha256": supplement_sha256}},
        "identityReverification": {"result": "ALL_PINNED_IDENTITIES_REPRODUCE", "count": len(pinned),
                                   "scope": "replay manifest (read from the pinned signal-history commit), fundamentals commit, membership, sectors, "
                                            "study protocol, calibration protocol/result and six harness code files, recomputed on the current checkout",
                                   "notRepeated": "the 715-cohort rebuild was not re-run: every input it reads is identical to the committed preflight's, "
                                                  "the harness code is byte-identical, and the build is deterministic, so a re-run would reproduce the committed "
                                                  "preflight; the preflight's counters (outcomeReads 0, intervalComputations 0, featureBuilds 715) are quoted, not re-measured"},
        "counters": preflight["counters"],
        "cohortFacts": {"definedSignalDates": preflight["cohorts"]["definedSignalDates"], "maturedDefinedCohorts": preflight["cohorts"]["maturedDefinedCohorts"],
                        "lastMaturedSignalDate": preflight["lastMaturedSignalDate"], "unresolvedCohorts": preflight["cohorts"]["unresolvedCohorts"]},
        "groups": groups, "carriedUnchangedFromV1": carried,
        "observationsNotGatingP4": v1["observationsNotGatingP4"],
        "scientificReadiness": "CONDITIONAL" if ready_to_authorize else "BLOCKED",
        "scientificReadinessMeaning": ("calibration covers every defined date; the remaining conditions are survivorship, membership and outcome-exposure "
                                       "limits the owner must accept in writing" if ready_to_authorize else
                                       "the supplemental calibration did not PASS; see calibrationReadiness"),
        "executionReadiness": "BLOCKED",
        "executionBlockedBy": ["OWNER_AUTHORIZATION", "DURABLE_ONE_SHOT_LOCK"],
        "evidenceClassOfTheFutureRun": preflight["evidenceClassOfTheFutureRun"],
        "interpretation": {"independentConfirmation": False, "survivorshipUnbiased": False,
                           "ABANDON_BEFORE_PROSPECTIVE_COLLECTION": "calibrated upper bound <= 0: stop; may partly reflect missing departed names",
                           "CONTINUE_TO_PROSPECTIVE_REGISTRATION_REVIEW": "anything else: only permission to REVIEW a prospective registration; never confirmation, "
                                                                          "promotion, production use or an investment decision"},
    }


def canonical(obj: Any) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
