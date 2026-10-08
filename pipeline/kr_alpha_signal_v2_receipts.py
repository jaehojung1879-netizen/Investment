"""kr-alpha-signal-v2 — the weekly PROSPECTIVE receipt (contract and synthetic tests only; nothing is written, scheduled or authorized here).

kr-alpha-signal-v2 (H2, value with business confirmation) is one CANDIDATE_SIGNAL_FAMILY inside the kr-alpha-atlas program, not the program itself.

One immutable receipt per weekly KR decision session, written after that session's close and before the next session opens, appended to a JSON
Lines ledger and never rewritten. Storage and digest are those of `prospective_receipt_core` (the format the three existing study receipts use). A
receipt carries what the signal knew and decided, never what happened next; outcomes are separate records built only after the maturity session
has closed.

TWO PATHWAYS THAT NEVER MEET.
  LIVE               `build_live_receipt` / `append_live_receipt` / `build_live_outcome_record`. The authorization is read ONLY from
                     `REGISTERED_AUTHORIZATION` (never accepted from a caller); spec, code and data identities are hashed here from the files on
                     disk; time comes only from the writer's own clock. Evidence class PROSPECTIVE_PAPER.
  SYNTHETIC_FIXTURE  `build_synthetic_receipt` / `append_synthetic_receipt` / `build_synthetic_outcome_record`, for tests. The caller supplies an
                     authorization and an explicit test clock, and the result is labelled SYNTHETIC_FIXTURE: it can never pass live validation or
                     enter a live ledger, and a live receipt can never enter a synthetic one.
There is no flag, environment variable or argument that turns one into the other.

States, in the order they are decided:
  BLOCKED                  PIT coverage below the floor: identities and counts only, no per-name signal, no forecast, no weights;
  NOT_READY                signal computed, no authorized calibrated forecast: research-only signal records, no weights;
  NO_ELIGIBLE_OPPORTUNITY  forecast present, nothing clears cost and uncertainty: zero names, the whole book in the declared fallback;
  CANDIDATE_PORTFOLIO      one to five names at one slot each, unused slots in the declared fallback.

No receipt is prospective evidence until the final design is merged AND an authorization is registered below. None is registered.
"""
from __future__ import annotations

import hashlib
import math
import subprocess
from pathlib import Path

import pandas as pd

from . import kr_alpha_signal_v2 as S
from . import prospective_receipt_core as CORE

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 2
LIVE, SYNTHETIC = "LIVE", "SYNTHETIC_FIXTURE"
EVIDENCE_CLASS_BY_PATHWAY = {LIVE: CORE.EVIDENCE_CLASS, SYNTHETIC: "SYNTHETIC_FIXTURE"}
KEY_FIELDS = ("studyId", "signalDate")
DECISION_STATES = ("BLOCKED", "NOT_READY", "NO_ELIGIBLE_OPPORTUNITY", "CANDIDATE_PORTFOLIO")
DATA_IDENTITY_KEYS = ("pitFeatureSnapshot", "universeSnapshot", "industryMembership")
AUTHORIZATION_KEYS = ("specSha256", "specPath", "mergeCommitSha", "mergedAtUtc", "codeFileHashes")
REQUIRED = ("schemaVersion", "studyId", "pathway", "designVersion", "designDigest", "specSha256", "codeIdentity", "authorization", "signalDate",
            "executionDate", "createdAtUtc", "dataSnapshotIdentity", "trainingCutoff", "benchmark", "evaluationHorizons", "coverage", "signal", "forecast",
            "decision", "costsAssumedBps", "researchOnly", "productionEffect", "evidenceClass")
TOLERANCE = 1e-9

# The authorization that makes receipts prospective evidence, registered by a later reviewed change after the frozen design merges:
# {"specSha256", "specPath", "mergeCommitSha", "mergedAtUtc", "codeFileHashes": {repo path: sha256}}. None exists, so no live receipt can be built.
REGISTERED_AUTHORIZATION = None


def require_registered_authorization():
    auth = REGISTERED_AUTHORIZATION
    if auth is None:
        raise ValueError("KR_ALPHA_SIGNAL_V2_NOT_AUTHORIZED: no frozen design has been merged and authorized for prospective receipts")
    if sorted(auth) != sorted(AUTHORIZATION_KEYS) or not CORE.is_sha256(auth["specSha256"]) or not CORE.is_git_sha(auth["mergeCommitSha"]) \
            or not auth["codeFileHashes"] or not all(CORE.is_sha256(v) for v in auth["codeFileHashes"].values()):
        raise ValueError("REGISTERED_AUTHORIZATION_MALFORMED")
    CORE.utc(auth["mergedAtUtc"])
    return dict(auth)


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(*args, root=ROOT):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def _verified_live_identities(auth, data_files, root):
    """Hash the spec, the authorized code files and the data snapshots from disk; refuse any mismatch with the registered authorization."""
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
    data = {key: file_sha256(Path(path)) for key, path in sorted(data_files.items())}
    return {"commitSha": commit, "files": files}, data


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


def _build(*, pathway, rows, signal_date, created_at_utc, now_utc, spec_sha256, code_identity, data_identity, authorization, forecasts,
           previous_holdings, fallback):
    _check_identities(spec_sha256, code_identity, data_identity, authorization)
    if not CORE.is_weekly_decision_session(signal_date):
        raise ValueError("SIGNAL_DATE_IS_NOT_A_WEEKLY_DECISION_SESSION")
    execution = CORE.check_timing(signal_date=signal_date, created_at_utc=created_at_utc, now_utc=now_utc, merged_at_utc=authorization["mergedAtUtc"])
    records = S.cross_section(rows, signal_date)
    decision = S.decide(records, signal_date=signal_date, forecasts=forecasts, previous_holdings=previous_holdings, fallback=fallback)
    blocked = decision["status"] == "BLOCKED"
    forecast_block = None if (blocked or forecasts is None) else {
        k: forecasts[k] for k in ("modelId", "modelSha256", "trainingCutoff", "trainingTargetLastExitDate", "calibrationStatus", "names")}
    receipt = {"schemaVersion": SCHEMA_VERSION, "studyId": S.STUDY, "pathway": pathway, "designVersion": S.DESIGN_VERSION, "designDigest": S.design_digest(),
               "specSha256": spec_sha256, "codeIdentity": {"commitSha": code_identity["commitSha"], "files": dict(sorted(code_identity["files"].items()))},
               "authorization": {"specSha256": authorization["specSha256"], "mergeCommitSha": authorization["mergeCommitSha"],
                                 "mergedAtUtc": authorization["mergedAtUtc"],
                                 "firstProspectiveSession": str(CORE.first_prospective_session(authorization["mergedAtUtc"]).date())},
               "signalDate": str(pd.Timestamp(signal_date).normalize().date()),
               "executionDate": str(execution.date()), "createdAtUtc": str(created_at_utc),
               "dataSnapshotIdentity": dict(sorted(data_identity.items())),
               "trainingCutoff": forecast_block["trainingCutoff"] if forecast_block else None,
               "benchmark": S.BENCHMARK, "evaluationHorizons": list(S.EVALUATION_HORIZONS), "coverage": S.coverage(records),
               "signal": None if blocked else records, "forecast": forecast_block,
               "decision": {"status": decision["status"], "reasons": decision["reasons"], "fallback": decision["fallback"],
                            "weights": decision["weights"], "fallbackWeight": decision["fallbackWeight"], "candidates": decision["candidates"],
                            "previousHoldings": sorted(previous_holdings), "maxHoldings": S.MAX_HOLDINGS, "slotWeight": S.SLOT_WEIGHT,
                            "maxNamesPerIndustry": S.MAX_NAMES_PER_INDUSTRY, "seMultiple": S.SE_MULTIPLE},
               "costsAssumedBps": {"stock": dict(S.STOCK_COSTS_BPS), "passiveLeg": dict(S.PASSIVE_LEG_COSTS_BPS),
                                   "roundTripUsedForEntry": S.round_trip_cost(fallback) * 10000.0},
               "researchOnly": True, "productionEffect": "NONE", "evidenceClass": EVIDENCE_CLASS_BY_PATHWAY[pathway]}
    receipt["receiptSha256"] = CORE.receipt_digest(receipt)
    validate_receipt(receipt)
    return receipt


# --------------------------------------------------------------------------- #
# LIVE pathway: registered authorization only, identities hashed here, the writer's own clock
# --------------------------------------------------------------------------- #
def build_live_receipt(*, rows, signal_date, data_files, forecasts=None, previous_holdings=(), fallback=S.PRIMARY_FALLBACK, root=ROOT):
    """The only way to build a receipt that can become prospective evidence. Takes no authorization, spec hash, code hash or timestamp."""
    auth = require_registered_authorization()
    code_identity, data_identity = _verified_live_identities(auth, data_files, root)
    now = CORE.system_utc_now()
    return _build(pathway=LIVE, rows=rows, signal_date=signal_date, created_at_utc=now.isoformat(), now_utc=now, spec_sha256=auth["specSha256"],
                  code_identity=code_identity, data_identity=data_identity, authorization=auth, forecasts=forecasts,
                  previous_holdings=previous_holdings, fallback=fallback)


def validate_live_receipt(receipt):
    """A live receipt must carry the REGISTERED authorization exactly, and a synthetic fixture can never pass."""
    validate_receipt(receipt)
    if receipt["pathway"] != LIVE:
        raise ValueError("SYNTHETIC_RECEIPT_REFUSED_ON_THE_LIVE_PATH")
    auth = require_registered_authorization()
    block = receipt["authorization"]
    if (block["specSha256"], block["mergeCommitSha"], block["mergedAtUtc"]) != (auth["specSha256"], auth["mergeCommitSha"], auth["mergedAtUtc"]):
        raise ValueError("RECEIPT_AUTHORIZATION_IS_NOT_THE_REGISTERED_ONE")
    return True


def append_live_receipt(path, receipt):
    return CORE.append(path, receipt, validate=validate_live_receipt, key_fields=KEY_FIELDS)


def read_live_ledger(path):
    return CORE.read_ledger(path, validate_live_receipt)


def build_live_outcome_record(receipt, *, horizon, name_outcomes):
    """Outcome after maturity, on the writer's own clock. There is no timestamp argument to fabricate."""
    validate_live_receipt(receipt)
    return _outcome(receipt, horizon=horizon, name_outcomes=name_outcomes, now_utc=CORE.system_utc_now(), validate=validate_live_receipt)


# --------------------------------------------------------------------------- #
# SYNTHETIC_FIXTURE pathway: tests only; explicit authorization and test clock; never live evidence
# --------------------------------------------------------------------------- #
def build_synthetic_receipt(*, rows, signal_date, created_at_utc, test_clock_utc, spec_sha256, code_identity, data_identity, authorization,
                            forecasts=None, previous_holdings=(), fallback=S.PRIMARY_FALLBACK):
    return _build(pathway=SYNTHETIC, rows=rows, signal_date=signal_date, created_at_utc=created_at_utc, now_utc=test_clock_utc,
                  spec_sha256=spec_sha256, code_identity=code_identity, data_identity=data_identity, authorization=authorization,
                  forecasts=forecasts, previous_holdings=previous_holdings, fallback=fallback)


def _validate_synthetic(receipt):
    validate_receipt(receipt)
    if receipt["pathway"] != SYNTHETIC:
        raise ValueError("LIVE_RECEIPT_REFUSED_ON_THE_SYNTHETIC_PATH")
    return True


def append_synthetic_receipt(path, receipt):
    return CORE.append(path, receipt, validate=_validate_synthetic, key_fields=KEY_FIELDS)


def read_synthetic_ledger(path):
    return CORE.read_ledger(path, _validate_synthetic)


def build_synthetic_outcome_record(receipt, *, horizon, name_outcomes, test_clock_utc):
    _validate_synthetic(receipt)
    return _outcome(receipt, horizon=horizon, name_outcomes=name_outcomes, now_utc=test_clock_utc, validate=_validate_synthetic)


def _outcome(receipt, *, horizon, name_outcomes, now_utc, validate):
    if horizon not in S.EVALUATION_HORIZONS:
        raise ValueError("UNREGISTERED_HORIZON")
    return CORE.build_outcome_record(receipt, validate=validate, horizon=horizon, name_outcomes=name_outcomes, now_utc=now_utc,
                                     weights_field=("decision", "weights"))


# --------------------------------------------------------------------------- #
# Validation shared by both pathways
# --------------------------------------------------------------------------- #
def validate_receipt(receipt):
    """Structural and semantic checks a reader re-runs on every row. A blocked or not-ready receipt can carry no weight; weights must equal the
    registered slot rule; nothing in the receipt may name an outcome; the evidence class must match the pathway."""
    missing = [k for k in REQUIRED + ("receiptSha256",) if k not in receipt]
    if missing:
        raise ValueError("RECEIPT_FIELD_MISSING: " + ",".join(missing))
    extra = sorted(set(receipt) - set(REQUIRED) - {"receiptSha256"})
    if extra:
        raise ValueError("RECEIPT_FIELD_NOT_IN_CONTRACT: " + ",".join(extra))
    if receipt["receiptSha256"] != CORE.receipt_digest(receipt):
        raise ValueError("RECEIPT_DIGEST_MISMATCH")
    if receipt["studyId"] != S.STUDY or receipt["schemaVersion"] != SCHEMA_VERSION or receipt["pathway"] not in EVIDENCE_CLASS_BY_PATHWAY \
            or receipt["evidenceClass"] != EVIDENCE_CLASS_BY_PATHWAY[receipt["pathway"]]:
        raise ValueError("RECEIPT_IDENTITY_MISMATCH")
    if receipt["researchOnly"] is not True or receipt["productionEffect"] != "NONE":
        raise ValueError("RECEIPT_MUST_BE_RESEARCH_ONLY")
    if receipt["authorization"]["specSha256"] != receipt["specSha256"]:
        raise ValueError("AUTHORIZATION_DOES_NOT_MATCH_THE_SPEC")
    if receipt["signalDate"] < receipt["authorization"]["firstProspectiveSession"]:
        raise ValueError("SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY")
    created = CORE.utc(receipt["createdAtUtc"])
    if created < (pd.Timestamp(receipt["signalDate"]) + CORE.KR_CLOSE_FINAL_UTC).tz_localize("UTC") \
            or created >= (pd.Timestamp(receipt["executionDate"]) + CORE.KR_OPEN_UTC).tz_localize("UTC"):
        raise ValueError("RECEIPT_TIMESTAMP_OUTSIDE_ITS_WINDOW")
    CORE.scan_for_outcome_keys({k: v for k, v in receipt.items() if k != "receiptSha256"})
    decision = receipt["decision"]
    status = decision["status"]
    if status not in DECISION_STATES:
        raise ValueError("UNKNOWN_DECISION_STATE")
    if status in ("BLOCKED", "NOT_READY"):
        if decision["weights"] is not None or decision["fallbackWeight"] is not None or decision["candidates"] or receipt["forecast"] is not None:
            raise ValueError("NON_ACTIONABLE_RECEIPT_CARRIES_A_DECISION")
        if status == "BLOCKED" and receipt["signal"] is not None:
            raise ValueError("BLOCKED_RECEIPT_CARRIES_A_SIGNAL")
        return True
    weights = decision["weights"]
    if receipt["forecast"] is None or weights is None:
        raise ValueError("ACTIONABLE_STATE_WITHOUT_A_FORECAST")
    if len(weights) > S.MAX_HOLDINGS or any(abs(w - S.SLOT_WEIGHT) > TOLERANCE for w in weights.values()):
        raise ValueError("WEIGHTS_VIOLATE_THE_SLOT_RULE")
    if abs(decision["fallbackWeight"] - (1.0 - math.fsum(weights.values()))) > TOLERANCE:
        raise ValueError("FALLBACK_WEIGHT_INCONSISTENT")
    if (status == "NO_ELIGIBLE_OPPORTUNITY") != (not weights):
        raise ValueError("STATE_DISAGREES_WITH_WEIGHTS")
    states = {r["ticker"]: r["state"] for r in receipt["signal"]}
    if any(states.get(t) != "CHEAP_CONFIRMED" for t in weights):
        raise ValueError("HELD_NAME_IS_NOT_CHEAP_CONFIRMED")
    return True
