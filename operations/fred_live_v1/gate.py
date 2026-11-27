"""Inactive adapter for a future live-only FRED integration.

No historical runner, workflow, ledger, production build or registered policy is
modified. The caller must supply the independently authorized model/series plan.
This module cannot authorize a writer or make a trade.
"""
from __future__ import annotations

from datetime import date

import numpy as np
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


def _valid_index(frame):
    return (
        isinstance(frame.index, pd.DatetimeIndex)
        and not frame.index.hasnans
        and frame.index.is_unique
        and frame.index.is_monotonic_increasing
    )


def _finite_columns(frame, columns):
    for column in columns:
        values = frame[column].dropna()
        if not pd.api.types.is_numeric_dtype(values) or not np.isfinite(values.to_numpy(dtype=float)).all():
            return False
    return True


def _last_date(index):
    return index[-1].date().isoformat() if len(index) else None


def _macro_evidence(macro, expected_series, availability, records, as_of):
    if not isinstance(macro, pd.DataFrame) or not macro.columns.is_unique:
        return ["MACRO_FRAME_INVALID"]
    if not _valid_index(macro) or not _date(as_of):
        return ["MACRO_FRAME_CLOCK_INVALID"]
    if not set(expected_series) <= set(macro.columns):
        return ["MACRO_FRAME_INCOMPLETE"]
    if not _finite_columns(macro, list(expected_series)):
        return ["MACRO_FRAME_NONFINITE_OR_NONNUMERIC"]
    reasons = []
    for name in expected_series:
        actual = macro[name].dropna()
        record = records.get(name)
        if (
            actual.empty or not isinstance(record, dict)
            or record.get("firstValidDate") != actual.index[0].date().isoformat()
            or record.get("lastValidDate") != _last_date(actual.index)
            or type(record.get("validObservations")) is not int
            or record.get("validObservations") != len(actual)
        ):
            reasons.append(f"{name}:MACRO_SERIES_RECEIPT_MISMATCH")
        elif _last_date(actual.index) > as_of:
            reasons.append(f"{name}:MACRO_SERIES_FUTURE")
    if not reasons:
        try:
            recalculated = fr.availability(records, expected_series)
            if (
                availability.get("mlMacroSeries") != recalculated["mlMacroSeries"]
                or availability.get("failedSeries") != recalculated["failedSeries"]
            ):
                reasons.append("MACRO_COVERAGE_RECEIPT_MISMATCH")
        except (KeyError, TypeError, ValueError, AttributeError):
            reasons.append("MACRO_COVERAGE_RECEIPT_INVALID")
    return reasons


def assess(*, model_version, as_of, macro, availability, expected_series, plan, observed):
    """Return metadata and a paper-recording recommendation, never permission.

    plan: slot -> {"columns": list[str], "target": str, "coveragePolicy": dict,
                   "minTrainingRows": int, "latestFeatureDate": str}
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
    reasons.extend(_macro_evidence(macro, expected_series, availability, records, as_of))
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
        minimum = spec.get("minTrainingRows")
        last_expected = spec.get("latestFeatureDate")
        if (
            not isinstance(expected, list) or not expected
            or not all(isinstance(x, str) and x for x in expected)
            or len(set(expected)) != len(expected)
            or not isinstance(target, str) or not target or target in expected
            or type(minimum) is not int or minimum <= 0
            or not _date(last_expected) or not _date(as_of) or last_expected > as_of
        ):
            reasons.append(f"{slot}:FEATURE_PLAN_INVALID")
            continue
        try:
            frame, columns = observed[slot]
            columns = list(columns)
            if (
                not isinstance(frame, pd.DataFrame)
                or not frame.columns.is_unique or not _valid_index(frame)
                or len(set(columns)) != len(columns)
                or not set(columns + [target]) <= set(frame.columns)
            ):
                raise ValueError("invalid feature frame")
            # The legacy identity digest is order-insensitive; the live plan is not.
            if columns != expected:
                reasons.append(f"{slot}:ORDERED_FEATURE_PLAN_MISMATCH")
                continue
            if (
                not _finite_columns(frame, columns + [target])
                or not len(frame) or _last_date(frame.index) > as_of
            ):
                reasons.append(f"{slot}:MODEL_FRAME_NONFINITE_OR_FUTURE")
                continue
            if _last_date(frame.dropna(subset=columns).index) != last_expected:
                reasons.append(f"{slot}:LATEST_FEATURE_SESSION_MISMATCH")
                continue
            if len(frame.dropna(subset=columns + [target])) < minimum:
                reasons.append(f"{slot}:TRAINING_ROWS_BELOW_PLAN")
                continue
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
