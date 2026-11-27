"""Inactive adapter for a future live-only FRED integration.

No historical runner, workflow, ledger, production build or registered policy is
modified. The caller must supply the independently authorized model/series plan.
This module cannot authorize a writer or make a trade.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from pipeline import fred_resilience as fr

HOLD_POLICY = "HOLD_SHORT_TERM_ML_AND_REGIME_SIGNALS"


def fetch_once(cfg, **kwargs):
    """The exact returned macro frame must also feed any downstream model."""
    return fr.fetch_macro_with_availability(
        cfg.fred_series, cfg.fred_api_key, cfg.model.history_start, **kwargs
    )


def _date(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _policy_valid(policy):
    return (
        isinstance(policy, dict)
        and set(policy) == set(fr.COVERAGE_POLICY_KEYS)
        and type(policy["maxStalenessDays"]) is int
        and policy["maxStalenessDays"] >= 0
        and type(policy["minOverlapObservations"]) is int
        and policy["minOverlapObservations"] > 0
        and _date(policy["latestAllowedTrainingStart"])
    )


def assess(*, model_version, as_of, macro, availability, expected_series, plan, observed):
    """Return metadata and a paper-recording recommendation, never permission.

    plan: slot -> {"columns": list[str], "target": str, "coveragePolicy": dict}
    observed: slot -> (actual feature frame, actual feature column names)
    Slot identity must include each planned ticker, horizon and path (e.g. core
    or screen). Missing/extra slots are not silently dropped. Plan authenticity,
    live action identity and writer authorization belong to the future caller.
    """
    reasons = []
    identities = {}
    if not _date(as_of):
        reasons.append("AS_OF_INVALID")
    if not isinstance(model_version, str) or not model_version:
        reasons.append("MODEL_VERSION_MISSING")
    if not isinstance(availability, dict):
        availability = {}
        reasons.append("AVAILABILITY_MISSING")
    records = availability.get("series")
    if not isinstance(records, dict):
        records = {}
    if not isinstance(expected_series, dict) or not expected_series:
        expected_series = {}
        reasons.append("SERIES_PLAN_UNSET")
    if (
        availability.get("status") != fr.FULL
        or availability.get("dataDegraded") is not False
        or availability.get("requested") != len(expected_series)
        or availability.get("fetched") != len(expected_series)
        or set(records) != set(expected_series)
        or any(
            not isinstance(records.get(name), dict)
            or records[name].get("status") != fr.OK
            or records[name].get("seriesId") != series_id
            for name, series_id in expected_series.items()
        )
    ):
        reasons.append("SOURCE_PLAN_NOT_FULLY_OBSERVED")
    if not isinstance(macro, pd.DataFrame) or not set(expected_series) <= set(macro.columns):
        reasons.append("MACRO_FRAME_INCOMPLETE")
    if not isinstance(plan, dict) or not plan:
        plan = {}
        reasons.append("MODEL_PLAN_UNSET")
    if not isinstance(observed, dict):
        observed = {}
        reasons.append("MODEL_OBSERVATIONS_MISSING")
    if set(plan) != set(observed):
        reasons.append("MODEL_SLOT_CENSUS_MISMATCH")
    for slot, spec in plan.items():
        if not isinstance(spec, dict) or not _policy_valid(spec.get("coveragePolicy")):
            reasons.append(f"{slot}:COVERAGE_POLICY_UNSET_OR_INVALID")
            continue
        expected = spec.get("columns")
        target = spec.get("target")
        if (
            not isinstance(expected, list) or not expected
            or not all(isinstance(x, str) and x for x in expected)
            or len(set(expected)) != len(expected)
            or not isinstance(target, str) or not target or target in expected
        ):
            reasons.append(f"{slot}:FEATURE_PLAN_INVALID")
            continue
        try:
            frame, columns = observed[slot]
            columns = list(columns)
            if (
                not isinstance(frame, pd.DataFrame)
                or not frame.columns.is_unique or not frame.index.is_unique
                or len(set(columns)) != len(columns)
                or not set(columns + [target]) <= set(frame.columns)
            ):
                raise ValueError("invalid feature frame")
            first = fr.training_start(frame, columns, target)
            if not _date(first):
                reasons.append(f"{slot}:TRAINING_START_UNMEASURED")
                continue
            identity = fr.model_identity(
                model_version, columns, expected, macro, availability,
                {slot: first}, as_of=as_of, coverage_policy=spec["coveragePolicy"],
            )
            identities[slot] = identity
            if fr.recording_decision(identity, HOLD_POLICY)["action"] != "RECORD_UNDER_REGISTERED_MODEL_VERSION":
                reasons.append(f"{slot}:IDENTITY_NOT_REGISTERED")
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            reasons.append(f"{slot}:MODEL_EVIDENCE_INVALID")
    if len(identities) != len(plan):
        reasons.append("MODEL_IDENTITY_CENSUS_INCOMPLETE")
    return {
        "schema": "FRED_LIVE_PREFLIGHT_V1",
        "asOf": as_of,
        "macroAvailability": availability,
        "identities": identities,
        "plannedSlots": len(plan),
        "observedSlots": len(observed),
        "reasons": sorted(set(reasons)),
        "decision": "HOLD" if reasons else "REGISTERED_INPUTS_OBSERVED",
        "writerAuthorized": False,
        "productionEffect": "NONE",
    }
