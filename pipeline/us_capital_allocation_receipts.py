"""us-capital-allocation-alpha-v1 — the weekly PROSPECTIVE receipt (contract and synthetic tests only; nothing is written,
scheduled or authorized here).

One immutable receipt per weekly US decision session, written after that session's close and before the next session can
open, appended to a JSON Lines ledger in a RESEARCH namespace and never rewritten. Storage, digest and the append-only rule
are those of `prospective_receipt_core` (the format the KR studies already use). A receipt carries what the rule knew and
decided, never what happened next; outcomes are separate records (`us_capital_allocation_evaluation`).

NAMESPACE. The official weekly paper decisions live in `ledger/weekly-decisions/` and are produced by `weekly_decision` /
`weekly_publish`. This module imports neither, writes nowhere near that path (`assert_research_path` refuses it), stamps
`officialWeeklyDecisionAffected = False` on every row, and a receipt can never carry a weight into the official portfolio.

TWO PATHWAYS THAT NEVER MEET (as in the KR receipts).
  LIVE               `build_live_receipt`: authorization read ONLY from `REGISTERED_AUTHORIZATION`; spec, code and data identities
                     hashed here from disk; time from the writer's own clock. None is registered, so none can be built.
  SYNTHETIC_FIXTURE  for tests; explicit authorization and test clock; labelled SYNTHETIC_FIXTURE; can never pass live validation.

States: BLOCKED (fewer measured names than the floor: counts only), NO_ELIGIBLE_OPPORTUNITY (the whole book is the residual
asset), CANDIDATE_PORTFOLIO (one to five names, 15% each, the rest in the residual asset).
"""
from __future__ import annotations

import hashlib
import math
import subprocess
from pathlib import Path

import pandas as pd

from . import prospective_receipt_core as CORE
from . import replay_calendar as RC
from . import us_capital_allocation_policy as P

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
LIVE, SYNTHETIC = "LIVE", "SYNTHETIC_FIXTURE"
EVIDENCE_CLASS_BY_PATHWAY = {LIVE: "PROSPECTIVE_PAPER_RESEARCH_CANDIDATE", SYNTHETIC: "SYNTHETIC_FIXTURE"}
KEY_FIELDS = ("studyId", "signalDate")
DATA_IDENTITY_KEYS = ("fundamentalShards", "membershipSnapshot", "priceSnapshot", "sectorEvidence")
AUTHORIZATION_KEYS = ("specSha256", "specPath", "mergeCommitSha", "mergedAtUtc", "codeFileHashes")
RESEARCH_LEDGER = "ledger/research/us-capital-allocation-alpha-v1/receipts.jsonl"
FORBIDDEN_PATH_PARTS = ("weekly-decisions",)
REQUIRED = ("schemaVersion", "studyId", "namespace", "pathway", "policyVersion", "designDigest", "specSha256", "codeIdentity", "authorization",
            "signalDate", "executionDate", "createdAtUtc", "dataSnapshotIdentity", "featureVersion", "benchmarks", "horizonSessions",
            "membership", "coverage", "observationPrices", "pitEvidence", "dilution", "decision", "costsAssumedBps", "researchOnly",
            "productionEffect", "officialWeeklyDecisionAffected", "evidenceClass")
TOLERANCE = 1e-9
# A US regular session ends 16:00 ET = 20:00 UTC (EDT) or 21:00 UTC (EST); a half day ends earlier. 23:00 UTC is after every
# variant plus a margin for late prints. The earliest the NEXT session can open is 09:30 EDT = 13:30 UTC.
US_CLOSE_FINAL_UTC = pd.Timedelta(hours=23)
US_OPEN_EARLIEST_UTC = pd.Timedelta(hours=13, minutes=30)

# Registered by a later reviewed change after the owner approves this design. None exists, so no live receipt can be built.
REGISTERED_AUTHORIZATION = None


# --------------------------------------------------------------------------- #
# US calendar and timing
# --------------------------------------------------------------------------- #
def _sessions(start, days):
    start = pd.Timestamp(start).normalize()
    return RC.sessions(str(start.date()), str((start + pd.Timedelta(days=days)).date()), "US")


def is_us_session(day):
    day = pd.Timestamp(day).normalize()
    return bool(len(_sessions(day, 0)) and _sessions(day, 0)[0] == day)


def next_us_session(day):
    day = pd.Timestamp(day).normalize()
    later = _sessions(day + pd.Timedelta(days=1), 12)
    if not len(later):
        raise ValueError("NO_US_SESSION_WITHIN_12_DAYS")
    return later[0]


def is_weekly_decision_session(day):
    """The last US session of its calendar (ISO) week, from the pinned exchange calendar."""
    day = pd.Timestamp(day).normalize()
    if not is_us_session(day):
        return False
    week = _sessions(day - pd.Timedelta(days=day.weekday()), 6)
    return len(week) > 0 and week[-1] == day


def first_prospective_session(merged_at_utc):
    """First US session strictly after the New York calendar date of the authorizing merge; same-day observations are excluded."""
    merge_day = CORE.utc(merged_at_utc).tz_convert("America/New_York").tz_localize(None).normalize()
    return next_us_session(merge_day)


def check_timing(*, signal_date, created_at_utc, now_utc, merged_at_utc):
    day = pd.Timestamp(signal_date).normalize()
    if not is_us_session(day):
        raise ValueError("SIGNAL_DATE_IS_NOT_A_US_SESSION")
    if not is_weekly_decision_session(day):
        raise ValueError("SIGNAL_DATE_IS_NOT_A_WEEKLY_DECISION_SESSION")
    if day < first_prospective_session(merged_at_utc):
        raise ValueError("SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY")
    created, now = CORE.utc(created_at_utc), CORE.utc(now_utc)
    if created > now:
        raise ValueError("RECEIPT_CREATED_IN_THE_FUTURE")
    execution = next_us_session(day)
    if created < (day + US_CLOSE_FINAL_UTC).tz_localize("UTC"):
        raise ValueError("RECEIPT_CREATED_BEFORE_SIGNAL_CLOSE")
    if created >= (execution + US_OPEN_EARLIEST_UTC).tz_localize("UTC"):
        raise ValueError("RECEIPT_CREATED_AFTER_EXECUTION_OPEN_BACKDATED")
    return execution


def maturity_session(execution_date, horizon=P.HORIZON_SESSIONS):
    """The US session `horizon` sessions after the execution session (the execution session is session 0)."""
    if not isinstance(horizon, int) or horizon <= 0:
        raise ValueError("HORIZON_MUST_BE_A_POSITIVE_SESSION_COUNT")
    start = pd.Timestamp(execution_date).normalize()
    sessions = _sessions(start, 2 * horizon + 40)
    if len(sessions) <= horizon or sessions[0] != start:
        raise ValueError("EXECUTION_DATE_IS_NOT_A_US_SESSION_OR_CALENDAR_TOO_SHORT")
    return sessions[horizon]


def has_matured(execution_date, horizon, now_utc):
    """True only once the maturity session itself is final (23:00 UTC that day), by a timezone-aware clock."""
    return CORE.utc(now_utc) >= (maturity_session(execution_date, horizon) + US_CLOSE_FINAL_UTC).tz_localize("UTC")


# --------------------------------------------------------------------------- #
# Authorization and identities
# --------------------------------------------------------------------------- #
def require_registered_authorization():
    auth = REGISTERED_AUTHORIZATION
    if auth is None:
        raise ValueError("US_CAPITAL_ALLOCATION_ALPHA_NOT_AUTHORIZED: the owner has not approved the registration")
    if sorted(auth) != sorted(AUTHORIZATION_KEYS) or not CORE.is_sha256(auth["specSha256"]) or not CORE.is_git_sha(auth["mergeCommitSha"]) \
            or not auth["codeFileHashes"] or not all(CORE.is_sha256(v) for v in auth["codeFileHashes"].values()):
        raise ValueError("REGISTERED_AUTHORIZATION_MALFORMED")
    CORE.utc(auth["mergedAtUtc"])
    return dict(auth)


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assert_research_path(path):
    """A research receipt can only live under the research namespace, never next to the official weekly decisions."""
    parts = Path(path).parts
    if any(p in parts for p in FORBIDDEN_PATH_PARTS):
        raise ValueError("RESEARCH_RECEIPT_REFUSED_IN_THE_OFFICIAL_WEEKLY_DECISION_NAMESPACE")
    return path


def _git(*args, root=ROOT):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def _verified_live_identities(auth, data_files, root):
    if file_sha256(Path(root) / auth["specPath"]) != auth["specSha256"]:
        raise ValueError("SPEC_FILE_DIFFERS_FROM_THE_AUTHORIZED_SPEC")
    files = {}
    for rel, pinned in sorted(auth["codeFileHashes"].items()):
        actual = file_sha256(Path(root) / rel)
        if actual != pinned:
            raise ValueError("CODE_CHANGED_SINCE_AUTHORIZATION: " + rel)
        files[rel] = actual
    head = _git("rev-parse", "HEAD", root=root)
    commit = head.stdout.strip()
    if head.returncode != 0 or not CORE.is_git_sha(commit):
        raise ValueError("CODE_COMMIT_UNKNOWN")
    if _git("merge-base", "--is-ancestor", auth["mergeCommitSha"], commit, root=root).returncode != 0:
        raise ValueError("RUNNING_COMMIT_DOES_NOT_CONTAIN_THE_AUTHORIZING_MERGE")
    if sorted(data_files) != sorted(DATA_IDENTITY_KEYS):
        raise ValueError("DATA_SNAPSHOT_IDENTITY_REQUIRED")
    return {"commitSha": commit, "files": files}, {key: file_sha256(Path(path)) for key, path in sorted(data_files.items())}


def _check_identities(spec_sha256, code_identity, data_identity, authorization):
    if not CORE.is_sha256(spec_sha256):
        raise ValueError("SPEC_IDENTITY_REQUIRED")
    if not CORE.is_git_sha(code_identity.get("commitSha")) or not code_identity.get("files") \
            or not all(CORE.is_sha256(v) for v in code_identity["files"].values()):
        raise ValueError("CODE_IDENTITY_REQUIRED")
    if sorted(data_identity) != sorted(DATA_IDENTITY_KEYS) or not all(CORE.is_sha256(v) for v in data_identity.values()):
        raise ValueError("DATA_SNAPSHOT_IDENTITY_REQUIRED")
    if not authorization or authorization.get("specSha256") != spec_sha256 or not CORE.is_git_sha(authorization.get("mergeCommitSha")) \
            or not authorization.get("mergedAtUtc"):
        raise ValueError("AUTHORIZATION_DOES_NOT_MATCH_THE_SPEC")


# --------------------------------------------------------------------------- #
# Building
# --------------------------------------------------------------------------- #
EVIDENCE_FEATURES = (*P.MEASURED_FEATURES, "cashDividendsPaidTTM", "commonStockRepurchasesTTM")


def pit_evidence(snapshot) -> dict:
    """What a selected name's features rested on: every filing input with its availability, acceptance and fiscal period.

    Taken from a PR #220 `FeatureSnapshot`; nothing is added, recomputed or inferred. A reader can re-derive the snapshot from the
    named filings and compare `featureDigest`.
    """
    return {"asOf": snapshot.as_of, "featureVersion": snapshot.feature_version, "featureDigest": snapshot.feature_digest,
            "reportPeriod": snapshot.report_period, "qualityWarnings": list(snapshot.quality_warnings),
            "features": {name: {"state": snapshot.features[name].state.value, "value": snapshot.features[name].value,
                                "basis": snapshot.features[name].basis,
                                "inputs": [{"filingId": i.filing_id, "availableFrom": i.available_from, "acceptedAt": i.accepted_at,
                                            "fiscalYear": i.fiscal_year, "stage": i.stage, "periodEnd": i.period_end, "concept": i.concept,
                                            "section": i.section, "value": i.value} for i in snapshot.features[name].inputs]}
                         for name in EVIDENCE_FEATURES}}


def _check_pit_evidence(evidence, signal_date, ticker):
    """Strictly-before availability, re-checked from the receipt alone."""
    if evidence.get("asOf") != signal_date or evidence.get("featureVersion") != P.U.FEATURE_VERSION or not CORE.is_sha256(evidence.get("featureDigest")):
        raise ValueError("PIT_EVIDENCE_IDENTITY_MISMATCH: " + ticker)
    for name, feature in (evidence.get("features") or {}).items():
        for item in feature.get("inputs", []):
            for key in ("availableFrom", "acceptedAt"):
                if item.get(key) and str(item[key])[:10] >= signal_date:
                    raise ValueError("PIT_INPUT_NOT_VISIBLE_BEFORE_THE_SIGNAL_DATE: %s %s.%s" % (ticker, name, item.get("filingId")))


def _price_block(prices, signal_date, created, tickers):
    """Prices AVAILABLE at observation time: one final close per name, from the signal session itself, never later."""
    out = {}
    for ticker in sorted(set(tickers)):
        row = prices.get(ticker)
        if not row:
            raise ValueError("OBSERVATION_PRICE_MISSING: " + ticker)
        for key in ("session", "asTradedClose", "totalReturnIndexClose", "vendor", "retrievedAtUtc", "basis"):
            if key not in row:
                raise ValueError("OBSERVATION_PRICE_FIELD_MISSING: %s.%s" % (ticker, key))
        if row["session"] != signal_date:
            raise ValueError("OBSERVATION_PRICE_NOT_FROM_THE_SIGNAL_SESSION: " + ticker)
        if not (CORE.finite(row["asTradedClose"]) and row["asTradedClose"] > 0 and CORE.finite(row["totalReturnIndexClose"]) and row["totalReturnIndexClose"] > 0):
            raise ValueError("OBSERVATION_PRICE_NOT_POSITIVE_AND_FINITE: " + ticker)
        retrieved = CORE.utc(row["retrievedAtUtc"])
        if retrieved < (pd.Timestamp(signal_date) + US_CLOSE_FINAL_UTC).tz_localize("UTC") or retrieved > created:
            raise ValueError("OBSERVATION_PRICE_RETRIEVED_OUTSIDE_THE_RECEIPT_WINDOW: " + ticker)
        out[ticker] = {k: row[k] for k in ("session", "asTradedClose", "totalReturnIndexClose", "vendor", "retrievedAtUtc", "basis")}
    return out


def _build(*, pathway, signal_date, created_at_utc, now_utc, spec_sha256, code_identity, data_identity, authorization, decision, coverage,
           membership, observation_prices, pit_evidence, measured_tickers):
    _check_identities(spec_sha256, code_identity, data_identity, authorization)
    execution = check_timing(signal_date=signal_date, created_at_utc=created_at_utc, now_utc=now_utc, merged_at_utc=authorization["mergedAtUtc"])
    signal = str(pd.Timestamp(signal_date).normalize().date())
    created = CORE.utc(created_at_utc)
    selected = [] if decision["weights"] is None else sorted(decision["weights"])
    blocked = decision["status"] == "BLOCKED"
    receipt = {
        "schemaVersion": SCHEMA_VERSION, "studyId": P.STUDY_ID, "namespace": P.NAMESPACE, "pathway": pathway, "policyVersion": P.POLICY_VERSION,
        "designDigest": P.design_digest(), "specSha256": spec_sha256,
        "codeIdentity": {"commitSha": code_identity["commitSha"], "files": dict(sorted(code_identity["files"].items()))},
        "authorization": {"specSha256": authorization["specSha256"], "mergeCommitSha": authorization["mergeCommitSha"],
                          "mergedAtUtc": authorization["mergedAtUtc"],
                          "firstProspectiveSession": str(first_prospective_session(authorization["mergedAtUtc"]).date())},
        "signalDate": signal, "executionDate": str(execution.date()), "createdAtUtc": str(created_at_utc),
        "dataSnapshotIdentity": dict(sorted(data_identity.items())), "featureVersion": P.U.FEATURE_VERSION,
        "benchmarks": {"official": P.OFFICIAL_BENCHMARK, "alternative": P.ALTERNATIVE_BENCHMARK, "residual": P.RESIDUAL_ASSET},
        "horizonSessions": P.HORIZON_SESSIONS,
        "membership": dict(membership),
        "coverage": {"funnel": decision["funnel"], "measuredTickers": None if blocked else sorted(measured_tickers)},
        "observationPrices": {} if blocked else _price_block(observation_prices, signal, created, [P.OFFICIAL_BENCHMARK, P.ALTERNATIVE_BENCHMARK, *selected]),
        "pitEvidence": {} if blocked else {t: pit_evidence[t] for t in selected},
        "dilution": {"status": P.DILUTION_STATUS, "gate": False},
        "decision": {"status": decision["status"], "reasons": decision["reasons"], "weights": decision["weights"],
                     "fallbackAsset": P.RESIDUAL_ASSET, "fallbackWeight": decision["fallbackWeight"], "selected": decision["selected"],
                     "passers": decision["passers"], "skippedForSectorCap": decision["skippedForSectorCap"], "maxNames": P.MAX_NAMES,
                     "slotWeight": P.SLOT_WEIGHT, "maxNamesPerSector": P.MAX_NAMES_PER_SECTOR},
        "costsAssumedBps": P.costs_bps(), "researchOnly": True, "productionEffect": "NONE", "officialWeeklyDecisionAffected": False,
        "evidenceClass": EVIDENCE_CLASS_BY_PATHWAY[pathway]}
    receipt["receiptSha256"] = CORE.receipt_digest(receipt)
    validate_receipt(receipt)
    return receipt


def build_live_receipt(*, signal_date, decision, coverage, membership, observation_prices, pit_evidence, measured_tickers, data_files, root=ROOT):
    """The only way to build a receipt that can become prospective evidence. Takes no authorization, spec hash, code hash or timestamp."""
    auth = require_registered_authorization()
    code_identity, data_identity = _verified_live_identities(auth, data_files, root)
    now = CORE.system_utc_now()
    return _build(pathway=LIVE, signal_date=signal_date, created_at_utc=now.isoformat(), now_utc=now, spec_sha256=auth["specSha256"],
                  code_identity=code_identity, data_identity=data_identity, authorization=auth, decision=decision, coverage=coverage,
                  membership=membership, observation_prices=observation_prices, pit_evidence=pit_evidence, measured_tickers=measured_tickers)


def build_synthetic_receipt(*, signal_date, created_at_utc, test_clock_utc, spec_sha256, code_identity, data_identity, authorization, decision,
                            coverage, membership, observation_prices, pit_evidence, measured_tickers):
    return _build(pathway=SYNTHETIC, signal_date=signal_date, created_at_utc=created_at_utc, now_utc=test_clock_utc, spec_sha256=spec_sha256,
                  code_identity=code_identity, data_identity=data_identity, authorization=authorization, decision=decision, coverage=coverage,
                  membership=membership, observation_prices=observation_prices, pit_evidence=pit_evidence, measured_tickers=measured_tickers)


# --------------------------------------------------------------------------- #
# Validation and storage
# --------------------------------------------------------------------------- #
def validate_live_receipt(receipt):
    validate_receipt(receipt)
    if receipt["pathway"] != LIVE:
        raise ValueError("SYNTHETIC_RECEIPT_REFUSED_ON_THE_LIVE_PATH")
    auth = require_registered_authorization()
    block = receipt["authorization"]
    if (block["specSha256"], block["mergeCommitSha"], block["mergedAtUtc"]) != (auth["specSha256"], auth["mergeCommitSha"], auth["mergedAtUtc"]):
        raise ValueError("RECEIPT_AUTHORIZATION_IS_NOT_THE_REGISTERED_ONE")
    return True


def validate_synthetic_receipt(receipt):
    validate_receipt(receipt)
    if receipt["pathway"] != SYNTHETIC:
        raise ValueError("LIVE_RECEIPT_REFUSED_ON_THE_SYNTHETIC_PATH")
    return True


def append_live_receipt(path, receipt):
    return CORE.append(assert_research_path(path), receipt, validate=validate_live_receipt, key_fields=KEY_FIELDS)


def append_synthetic_receipt(path, receipt):
    return CORE.append(assert_research_path(path), receipt, validate=validate_synthetic_receipt, key_fields=KEY_FIELDS)


def read_live_ledger(path):
    return CORE.read_ledger(assert_research_path(path), validate_live_receipt)


def read_synthetic_ledger(path):
    return CORE.read_ledger(assert_research_path(path), validate_synthetic_receipt)


def validate_receipt(receipt):
    """Structural and semantic checks a reader re-runs on every row."""
    missing = [k for k in REQUIRED + ("receiptSha256",) if k not in receipt]
    if missing:
        raise ValueError("RECEIPT_FIELD_MISSING: " + ",".join(missing))
    extra = sorted(set(receipt) - set(REQUIRED) - {"receiptSha256"})
    if extra:
        raise ValueError("RECEIPT_FIELD_NOT_IN_CONTRACT: " + ",".join(extra))
    if receipt["receiptSha256"] != CORE.receipt_digest(receipt):
        raise ValueError("RECEIPT_DIGEST_MISMATCH")
    if receipt["studyId"] != P.STUDY_ID or receipt["namespace"] != P.NAMESPACE or receipt["schemaVersion"] != SCHEMA_VERSION \
            or receipt["pathway"] not in EVIDENCE_CLASS_BY_PATHWAY or receipt["evidenceClass"] != EVIDENCE_CLASS_BY_PATHWAY[receipt["pathway"]] \
            or receipt["policyVersion"] != P.POLICY_VERSION or receipt["featureVersion"] != P.U.FEATURE_VERSION:
        raise ValueError("RECEIPT_IDENTITY_MISMATCH")
    if receipt["designDigest"] != P.design_digest():
        raise ValueError("RECEIPT_DESIGN_DIFFERS_FROM_THE_REGISTERED_DESIGN")
    if receipt["researchOnly"] is not True or receipt["productionEffect"] != "NONE" or receipt["officialWeeklyDecisionAffected"] is not False:
        raise ValueError("RECEIPT_MUST_BE_RESEARCH_ONLY")
    if receipt["authorization"]["specSha256"] != receipt["specSha256"]:
        raise ValueError("AUTHORIZATION_DOES_NOT_MATCH_THE_SPEC")
    if receipt["signalDate"] < receipt["authorization"]["firstProspectiveSession"]:
        raise ValueError("SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY")
    created = CORE.utc(receipt["createdAtUtc"])
    if created < (pd.Timestamp(receipt["signalDate"]) + US_CLOSE_FINAL_UTC).tz_localize("UTC") \
            or created >= (pd.Timestamp(receipt["executionDate"]) + US_OPEN_EARLIEST_UTC).tz_localize("UTC"):
        raise ValueError("RECEIPT_TIMESTAMP_OUTSIDE_ITS_WINDOW")
    if receipt["benchmarks"] != {"official": "SPY", "alternative": "QQQ", "residual": "SPY"} or receipt["horizonSessions"] != P.HORIZON_SESSIONS:
        raise ValueError("RECEIPT_BENCHMARK_OR_HORIZON_NOT_AS_REGISTERED")
    if receipt["dilution"] != {"status": P.DILUTION_STATUS, "gate": False}:
        raise ValueError("DILUTION_STATUS_MUST_BE_STATED_AS_UNVERIFIED")
    CORE.scan_for_outcome_keys({k: v for k, v in receipt.items() if k != "receiptSha256"})
    decision = receipt["decision"]
    status = decision["status"]
    if status not in P.DECISION_STATES:
        raise ValueError("UNKNOWN_DECISION_STATE")
    if status == "BLOCKED":
        if decision["weights"] is not None or decision["fallbackWeight"] is not None or decision["selected"] or decision["passers"] \
                or receipt["observationPrices"] or receipt["pitEvidence"] or receipt["coverage"]["measuredTickers"] is not None:
            raise ValueError("BLOCKED_RECEIPT_CARRIES_A_SIGNAL")
        return True
    weights, selected = decision["weights"], decision["selected"]
    if weights is None or len(weights) > P.MAX_NAMES or any(abs(w - P.SLOT_WEIGHT) > TOLERANCE for w in weights.values()):
        raise ValueError("WEIGHTS_VIOLATE_THE_SLOT_RULE")
    if abs(decision["fallbackWeight"] - (1.0 - math.fsum(weights.values()))) > TOLERANCE:
        raise ValueError("FALLBACK_WEIGHT_INCONSISTENT")
    if (status == "NO_ELIGIBLE_OPPORTUNITY") != (not weights):
        raise ValueError("STATE_DISAGREES_WITH_WEIGHTS")
    if sorted(weights) != sorted(s["ticker"] for s in selected):
        raise ValueError("SELECTED_AND_WEIGHTS_DISAGREE")
    sectors = [s["sector"] for s in selected]
    if any(sectors.count(x) > P.MAX_NAMES_PER_SECTOR for x in set(sectors)) or any(s in P.EXCLUDED_SECTORS or s in (None, "UNCLASSIFIED") for s in sectors):
        raise ValueError("SECTOR_RULE_VIOLATED")
    if any(s["score"] is None or s["score"] < P.MIN_INCREMENTAL_OVER_OCF for s in selected):
        raise ValueError("SELECTED_NAME_DOES_NOT_CLEAR_THE_MATERIALITY_GATE")
    ranked = [(-p["score"], p["ticker"]) for p in decision["passers"]]
    if ranked != sorted(ranked):
        raise ValueError("PASSERS_NOT_IN_REGISTERED_RANK_ORDER")
    if sorted(receipt["pitEvidence"]) != sorted(weights):
        raise ValueError("PIT_EVIDENCE_REQUIRED_FOR_EVERY_SELECTED_NAME")
    for ticker, evidence in receipt["pitEvidence"].items():
        _check_pit_evidence(evidence, receipt["signalDate"], ticker)
    needed = {P.OFFICIAL_BENCHMARK, P.ALTERNATIVE_BENCHMARK, *weights}
    if set(receipt["observationPrices"]) != needed:
        raise ValueError("OBSERVATION_PRICES_REQUIRED_FOR_BENCHMARKS_AND_SELECTED_NAMES")
    return True
