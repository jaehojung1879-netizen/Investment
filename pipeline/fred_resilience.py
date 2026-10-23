"""FRED resilience and short-term ML model identity (issue #279). INACTIVE: imported by no production path.

What this fixes, once wired (see docs/fred-resilience-model-identity-v1.md for the wiring and why it is held):

* `fredapi` 0.5.2 calls `urlopen(url)` with no timeout and `datafeed.fetch_macro` never retries, so a hanging FRED can hold a build for the
  job's whole 360-minute default. `TimeoutFred` keeps fredapi's own URL building and XML parsing (so a fetched series is byte-for-byte
  the series production reads today) and only adds a per-request timeout and a typed error that keeps the HTTP status.
* `fetch_macro_with_availability` returns the SAME frame `datafeed.fetch_macro` builds, plus a machine-readable availability record:
  requested / fetched / failed per series, attempts, HTTP status, first and last valid observation, the date the ML inputs first all
  exist, and which series sets it. Bounded: per-request timeout, bounded retries on retryable failures only, and a provider circuit breaker
  so an all-down FRED costs a few requests, not 27 x attempts x timeout.
* A model's identity is what it was trained on. Without FRED the short-term ML layer drops its macro columns and `features.py` inserts the
  constants Treasury_10Y = 3.0 and Yield_Curve = 0.5. `model_identity` records the feature-set digest, the placeholders and the training
  start, compares them with the registered feature set derived from the production code itself, and never lets a different feature set
  carry the registered modelVersion unmarked.
* What to do with a degraded day (hold the short-term ML/regime signals, record a separately named variant, or reuse the last registered
  model) is an owner decision. `DEGRADED_POLICY` is None and `recording_decision` therefore fails closed: HOLD, never record under the
  registered version.

Nothing here changes a feature, a window, a threshold or the weekly decision, and nothing here reads a return.
"""
from __future__ import annotations

import hashlib
import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

SCHEMA = "fred-availability-v1"
IDENTITY_SCHEMA = "short-term-ml-identity-v1"
PROVIDER = "FRED"
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF_S = (2.0, 4.0)
DEFAULT_PROVIDER_FAILURES_BEFORE_STOP = 3
OK, EMPTY = "OK", "EMPTY"
RATE_LIMITED, SERVER_ERROR, TIMEOUT, NETWORK_ERROR = "RATE_LIMITED", "SERVER_ERROR", "TIMEOUT", "NETWORK_ERROR"
CLIENT_ERROR, MALFORMED, NOT_ATTEMPTED = "CLIENT_ERROR", "MALFORMED", "NOT_ATTEMPTED_PROVIDER_UNAVAILABLE"
RETRYABLE = frozenset({RATE_LIMITED, SERVER_ERROR, TIMEOUT, NETWORK_ERROR})
PROVIDER_LEVEL = RETRYABLE                      # a failure that says something about FRED, not about one series
FULL, PARTIAL, UNAVAILABLE, DISABLED = "FULL", "PARTIAL", "UNAVAILABLE", "DISABLED"
# features.py inserts these constants when the macro column is absent (lines 116-121 at main 7b0dbad). Mirrored, never applied here.
MACRO_PLACEHOLDERS = {"Treasury_10Y": 3.0, "Yield_Curve": 0.5}
REGISTERED, DEGRADED, UNVERIFIED = "REGISTERED_FEATURE_SET", "DEGRADED_FEATURE_SET", "COVERAGE_UNVERIFIED"
# A request that succeeded is not a usable training input: the series must also be fresh, overlap, and leave the registered training
# window intact. The thresholds are owner policy (docs/fred-resilience-model-identity-v1.md O7). None = unset: nothing can be REGISTERED.
COVERAGE_POLICY_KEYS = ("maxStalenessDays", "minOverlapObservations", "latestAllowedTrainingStart")
COVERAGE_POLICY = None
# Owner decision (docs/fred-resilience-model-identity-v1.md). None = unset: a degraded model is never recorded.
DEGRADED_POLICY = None
POLICY_OPTIONS = ("HOLD_SHORT_TERM_ML_AND_REGIME_SIGNALS", "RECORD_AS_SEPARATE_VARIANT", "REUSE_LAST_REGISTERED_MODEL")


class FredRequestError(Exception):
    """One failed FRED request, classified. `kind` decides whether a retry can help."""

    def __init__(self, kind, message=None, http_status=None):
        super().__init__(f"{kind}: {message}" if message else kind)
        self.kind, self.message, self.http_status = kind, message, http_status


def _http_kind(code):
    if code == 429:
        return RATE_LIMITED
    return SERVER_ERROR if code >= 500 else CLIENT_ERROR


def _xml_message(body):
    try:
        return ET.fromstring(body).get("message")
    except ET.ParseError:
        return None


def timeout_fred(api_key, timeout=DEFAULT_TIMEOUT_S, opener=urlopen, root_url=None):
    """A fredapi client whose every request has a timeout. Only the transport changes: `get_series` (URL, '.'-as-NaN, date parsing) is
    fredapi's own, so a successful fetch is the series `datafeed.fetch_macro` reads today."""
    from fredapi import Fred

    class _TimeoutFred(Fred):
        # Overrides fredapi's private `Fred.__fetch_data` (mangled name). Parsing is identical; only timeout and error typing are added.
        def _Fred__fetch_data(self, url):
            url += "&api_key=" + self.api_key
            try:
                response = opener(url, timeout=timeout)
                body = response.read()
            except HTTPError as exc:
                raise FredRequestError(_http_kind(exc.code), _xml_message(exc.read() or b""), exc.code) from None
            except (socket.timeout, TimeoutError) as exc:
                raise FredRequestError(TIMEOUT, str(exc) or "timed out") from None
            except URLError as exc:
                kind = TIMEOUT if isinstance(exc.reason, (socket.timeout, TimeoutError)) else NETWORK_ERROR
                raise FredRequestError(kind, str(exc.reason)) from None
            try:
                return ET.fromstring(body)
            except ET.ParseError as exc:
                raise FredRequestError(MALFORMED, str(exc)) from None

    client = _TimeoutFred(api_key=api_key)
    if root_url:
        client.root_url = root_url
    return client


def _span(series):
    valid = series.dropna() if isinstance(series, pd.Series) else pd.Series(dtype=float)
    if valid.empty:
        return None, None, 0
    return str(pd.Timestamp(valid.index.min()).date()), str(pd.Timestamp(valid.index.max()).date()), int(len(valid))


def fetch_series(client, series_id, start, *, attempts=DEFAULT_ATTEMPTS, backoff=DEFAULT_BACKOFF_S, sleep=time.sleep):
    """(series or None, record). Retries only retryable failures, at most `attempts` requests in total."""
    record = {"seriesId": series_id, "attempts": 0, "status": None, "httpStatus": None, "message": None}
    for attempt in range(attempts):
        record["attempts"] = attempt + 1
        try:
            series = client.get_series(series_id, observation_start=start)
        except FredRequestError as exc:
            record.update(status=exc.kind, httpStatus=exc.http_status, message=exc.message)
        except ValueError as exc:            # fredapi's own "No data exists for series id" and friends
            record.update(status=CLIENT_ERROR, message=str(exc))
        else:
            first, last, n = _span(series)
            record.update(status=OK if n else EMPTY, httpStatus=200, message=None, firstValidDate=first, lastValidDate=last,
                          validObservations=n)
            return (series if n else None), record
        if record["status"] not in RETRYABLE or attempt == attempts - 1:
            break
        sleep(backoff[min(attempt, len(backoff) - 1)] if backoff else 0.0)
    record.update(firstValidDate=None, lastValidDate=None, validObservations=0)
    return None, record


def fetch_macro_with_availability(series_map, api_key, start, *, client=None, timeout=DEFAULT_TIMEOUT_S, attempts=DEFAULT_ATTEMPTS,
                                  backoff=DEFAULT_BACKOFF_S, provider_failures_before_stop=DEFAULT_PROVIDER_FAILURES_BEFORE_STOP,
                                  sleep=time.sleep, clock=time.monotonic):
    """(macro frame or None, availability). The frame is composed exactly as `datafeed.fetch_macro` composes it."""
    from . import pit_data
    began = clock()
    if not api_key or not series_map:
        return None, availability({}, series_map or {}, disabled=True, elapsed=0.0)
    client = client or timeout_fred(api_key, timeout)
    frame, records, streak = {}, {}, 0
    for name, series_id in series_map.items():
        if streak >= provider_failures_before_stop:
            records[name] = {"seriesId": series_id, "attempts": 0, "status": NOT_ATTEMPTED, "httpStatus": None, "message": None,
                             "firstValidDate": None, "lastValidDate": None, "validObservations": 0}
            continue
        series, record = fetch_series(client, series_id, start, attempts=attempts, backoff=backoff, sleep=sleep)
        records[name] = record
        if series is not None:
            frame[name] = series
            streak = 0
        else:
            streak = streak + 1 if record["status"] in PROVIDER_LEVEL else 0
    macro = pit_data.derive_macro_columns(pd.DataFrame(frame)) if frame else None
    policy = {"timeoutSeconds": timeout, "attempts": attempts, "backoffSeconds": list(backoff),
              "providerFailuresBeforeStop": provider_failures_before_stop}
    return macro, availability(records, series_map, elapsed=clock() - began, policy=policy)


def availability(records, series_map, *, disabled=False, elapsed=0.0, policy=None):
    """The machine-readable state of one fetch. `dataDegraded` is true whenever a requested series is missing."""
    from .features import ML_MACRO_COLS
    names = list(series_map)
    fetched = [n for n in names if records.get(n, {}).get("status") == OK]
    failed = [n for n in names if n not in fetched]
    status = DISABLED if disabled else FULL if names and not failed else UNAVAILABLE if not fetched else PARTIAL
    ml_requested = [n for n in names if n in ML_MACRO_COLS]
    ml_fetched = [n for n in ml_requested if n in fetched]
    missing = [n for n in ml_requested if n not in ml_fetched]
    starts = {n: records[n]["firstValidDate"] for n in ml_fetched}
    ends = {n: records[n]["lastValidDate"] for n in ml_fetched}
    latest_start, earliest_end = (max(starts.values()), min(ends.values())) if starts else (None, None)
    # A date on which ALL requested ML inputs exist only when none is missing and their valid spans overlap. Otherwise there is none.
    overlap = bool(starts) and not missing and latest_start <= earliest_end
    return {"schema": SCHEMA, "provider": PROVIDER, "status": status, "dataDegraded": status != FULL, "requested": len(names),
            "fetched": len(fetched), "failedSeries": failed, "series": {n: records.get(n) for n in names},
            "mlMacroSeries": {"requested": ml_requested, "fetched": ml_fetched, "missing": missing, "overlapVerified": overlap,
                              "allPresentFrom": latest_start if overlap else None, "allPresentThrough": earliest_end if overlap else None,
                              "limitingSeries": sorted(n for n, d in starts.items() if d == latest_start) if overlap else [],
                              "stalestSeries": sorted(n for n, d in ends.items() if d == earliest_end) if overlap else []},
            "elapsedSeconds": round(float(elapsed), 3), "requestPolicy": policy}


def data_source_label(avail):
    """What was actually fetched, never what was configured."""
    market = "Yahoo Finance + FinanceDataReader/Stooq fallback (market)"
    if avail["status"] == DISABLED:
        return market + "; FRED disabled"
    if avail["status"] == UNAVAILABLE:
        return market + f"; FRED unavailable (0 of {avail['requested']} series)"
    if avail["status"] == PARTIAL:
        return market + f" + FRED partial ({avail['fetched']} of {avail['requested']} series)"
    return market + " + FRED (macro)"


def provenance_errors(meta):
    """Validator rule for a wired artifact: a FRED claim needs fetched series, and degradation must be stated."""
    errors = []
    avail, source = meta.get("macroAvailability"), meta.get("dataSource", "")
    if not isinstance(avail, dict):
        return ["MACRO_AVAILABILITY_MISSING"]
    if "FRED (macro)" in source and avail.get("status") != FULL:
        errors.append("DATA_SOURCE_CLAIMS_FRED_BUT_FETCH_WAS_NOT_FULL")
    if avail.get("fetched", 0) == 0 and "FRED" in source and "unavailable" not in source and "disabled" not in source:
        errors.append("DATA_SOURCE_CLAIMS_FRED_WITH_ZERO_SERIES")
    if bool(meta.get("dataDegraded")) != bool(avail.get("dataDegraded")):
        errors.append("DATA_DEGRADED_FLAG_INCONSISTENT")
    ml = avail.get("mlMacroSeries") or {}
    if ml.get("allPresentFrom") is not None and (ml.get("missing") or not ml.get("overlapVerified")):
        errors.append("ALL_PRESENT_FROM_WITHOUT_VERIFIED_OVERLAP")
    identity = meta.get("shortTermModelIdentity")
    if isinstance(identity, dict) and identity.get("variant") != REGISTERED and identity.get("effectiveModelId") == identity.get("registeredModelVersion"):
        errors.append("DEGRADED_MODEL_RECORDED_UNDER_REGISTERED_VERSION")
    return errors


# ---------------------------------------------------------------------------------------------------------------------------------
# Model identity
# ---------------------------------------------------------------------------------------------------------------------------------
def feature_set_digest(columns):
    return hashlib.sha256(json.dumps(sorted(columns), separators=(",", ":")).encode()).hexdigest()


def macro_placeholders(macro):
    """The constants features.py would insert for this macro frame (it inserts when the column is absent)."""
    present = set(macro.columns) if isinstance(macro, pd.DataFrame) else set()
    return {c: v for c, v in MACRO_PLACEHOLDERS.items() if c not in present}


def reference_feature_columns(series_map, history_days=400):
    """The registered short-term ML feature set, derived by running the production feature code on an invented frame that carries every
    configured series. Column NAMES do not depend on values, so this is the set a full FRED fetch produces."""
    from . import features as F
    days = pd.bdate_range("2020-01-01", periods=history_days)
    t = np.arange(len(days), dtype=float)
    close = pd.Series(100 + np.sin(t / 9.0) + t / 50.0, index=days)
    price = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1e6 + t}, index=days)
    macro = pd.DataFrame({name: 1.0 + 0.01 * np.cos(t / 7.0) for name in series_map}, index=days)
    from . import pit_data
    macro = pit_data.derive_macro_columns(macro)
    feat = F.build_features(price, benchmark_close=close * 0.9, vix=pd.Series(20 + np.sin(t), index=days), macro=macro)
    return F.feature_columns(feat)


def training_start(data, feature_cols, target_col):
    """First row walk_forward / current_signal can train on (they drop rows with any missing feature or target)."""
    frame = data.dropna(subset=list(feature_cols) + [target_col])
    return None if frame.empty else str(pd.Timestamp(frame.index.min()).date())


def ml_input_coverage(avail, as_of, training_starts=None, policy=COVERAGE_POLICY, macro=None):
    """Whether the fetched ML macro inputs are USABLE as the registered model's training input on `as_of`, not merely fetched.
    (verified, reasons). Unset policy -> (None, [...]): coverage is unverified, never assumed."""
    reasons = []
    ml = avail.get("mlMacroSeries") or {}
    if ml.get("missing"):
        reasons.append("ML_MACRO_SERIES_MISSING")
    if not ml.get("overlapVerified"):
        reasons.append("ML_MACRO_SERIES_DO_NOT_OVERLAP")
    if policy is None:
        return None, reasons + ["COVERAGE_POLICY_UNSET"]
    if not isinstance(policy, dict) or set(policy) != set(COVERAGE_POLICY_KEYS):
        raise ValueError("COVERAGE_POLICY_INCOMPLETE")
    through = ml.get("allPresentThrough")
    if through is None or (pd.Timestamp(as_of) - pd.Timestamp(through)).days > policy["maxStalenessDays"]:
        reasons.append("ML_MACRO_SERIES_STALE")
    if ml.get("overlapVerified") and isinstance(macro, pd.DataFrame):
        cols = [c for c in ml.get("fetched", []) if c in macro.columns]
        if int(macro[cols].dropna().shape[0]) < policy["minOverlapObservations"]:
            reasons.append("ML_MACRO_OVERLAP_TOO_SHORT")
    elif ml.get("overlapVerified"):
        reasons.append("ML_MACRO_OVERLAP_UNMEASURED")
    starts = [d for d in (training_starts or {}).values() if d]
    if not starts:
        reasons.append("TRAINING_START_UNMEASURED")
    elif max(starts) > policy["latestAllowedTrainingStart"]:
        reasons.append("TRAINING_START_LATER_THAN_REGISTERED_WINDOW")
    return not reasons, reasons


def model_identity(model_version, feature_cols, reference_cols, macro, avail, training_starts=None, *, as_of=None,
                   coverage_policy=COVERAGE_POLICY):
    """REGISTERED only when the feature names match, nothing was filled with a constant, the fetch was FULL AND the inputs are verified
    usable (fresh, overlapping, registered training window). Matching names alone are never enough."""
    digest, reference = feature_set_digest(feature_cols), feature_set_digest(reference_cols)
    placeholders = macro_placeholders(macro)
    same_inputs = digest == reference and not placeholders and avail.get("status") == FULL
    coverage, coverage_reasons = ml_input_coverage(avail, as_of, training_starts, coverage_policy, macro) if same_inputs else (False, [])
    known_gap = [r for r in coverage_reasons if r != "COVERAGE_POLICY_UNSET"]
    if not same_inputs or coverage is False or known_gap:
        variant = DEGRADED
    elif coverage is None:
        variant = UNVERIFIED         # same inputs, but nobody has registered what "usable" means: not the registered model either
    else:
        variant = REGISTERED
    suffix = {REGISTERED: None, UNVERIFIED: "unverified", DEGRADED: "degraded"}[variant]
    starts = sorted(d for d in (training_starts or {}).values() if d)
    return {"schema": IDENTITY_SCHEMA, "registeredModelVersion": model_version, "variant": variant,
            "effectiveModelId": model_version if variant == REGISTERED else f"{model_version}#{suffix}-{digest[:12]}",
            "coverageVerified": coverage, "coverageReasons": coverage_reasons, "asOf": as_of,
            "featureSetSha256": digest, "registeredFeatureSetSha256": reference, "featureCount": len(feature_cols),
            "registeredFeatureCount": len(reference_cols), "missingFeatures": sorted(set(reference_cols) - set(feature_cols)),
            "constantPlaceholders": placeholders, "macroStatus": avail.get("status"),
            "trainingStart": {"earliest": starts[0] if starts else None, "latest": starts[-1] if starts else None,
                              "byModel": dict(sorted((training_starts or {}).items()))},
            "regimeInputsDegraded": bool(avail.get("dataDegraded"))}


def recording_decision(identity, policy=DEGRADED_POLICY):
    """Whether a short-term ML / regime-dependent paper signal may be recorded. Fail-closed while the owner policy is unset."""
    if identity.get("variant") == REGISTERED and not identity.get("regimeInputsDegraded"):
        return {"action": "RECORD_UNDER_REGISTERED_MODEL_VERSION", "modelId": identity["registeredModelVersion"]}
    if policy is None:
        return {"action": "HOLD", "reason": "DEGRADED_INPUTS_AND_OWNER_POLICY_UNSET", "modelId": None}
    if policy not in POLICY_OPTIONS:
        raise ValueError("UNKNOWN_DEGRADED_POLICY")
    if policy == "RECORD_AS_SEPARATE_VARIANT":
        return {"action": "RECORD_AS_SEPARATE_VARIANT", "modelId": identity["effectiveModelId"]}
    if policy == "REUSE_LAST_REGISTERED_MODEL":     # needs a persisted registered model, which does not exist yet
        return {"action": "HOLD", "reason": "NO_PERSISTED_REGISTERED_MODEL_TO_REUSE", "modelId": None}
    return {"action": "HOLD", "reason": policy, "modelId": None}
