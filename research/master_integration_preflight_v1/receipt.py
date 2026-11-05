"""Synthetic observation receipts using the existing immutable core, no engine.

There is no live recording API. Local append requires an existing explicit test
store outside every worktree. No prices, picks, weights or results are accepted.
"""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import subprocess

import pandas as pd

from pipeline import prospective_receipt_core as C
from pipeline import replay_calendar as RC
from . import adapters as A

SENTINEL = ".synthetic-preflight-store"
SENTINEL_BYTES = b"SYNTHETIC_PREFLIGHT_ONLY\n"
ROOT = Path(__file__).resolve().parents[2]
RECEIPT_FIELDS = {"schema", "studyId", "contractRef", "specSha256", "evidenceClass", "status",
                  "activationEnabled", "fixtureId", "region", "signalDate", "createdAtUtc", "fixtureBoundaryUtc",
                  "executionDate", "informationCutoffUtc", "calendarVersion", "commonUniverse", "sourceEvidence",
                  *A.HASH_IDENTITIES, "marketState", "industryState", "stockQualification", "benchmarkTicker",
                  "currency", "supplementalBenchmark", "nameCountPolicy", "arms", "receiptSha256"}


def _require(ok, code):
    if not ok:
        raise ValueError(code)


def sessions(region, start, days=20):
    day = pd.Timestamp(start)
    _require(day.tzinfo is None and day == day.normalize(), "SESSION_DATE_REQUIRED")
    return RC.sessions(str(day.date()), str((day + pd.Timedelta(days=days)).date()), region)


def bounds(region, day):
    if region == "KR":
        return day.tz_localize("UTC"), (day + C.KR_CLOSE_FINAL_UTC).tz_localize("UTC")
    import exchange_calendars as xc
    exchange = xc.get_calendar("XNYS", start="1990-01-01", end="2035-12-31")
    return exchange.session_open(day), exchange.session_close(day)


def timing(region, signal, created, now, boundary):
    dates = sessions(region, signal)
    day = pd.Timestamp(signal)
    _require(len(dates) >= 2 and dates[0] == day, "SIGNAL_NOT_REGIONAL_SESSION")
    execution = dates[1]
    _require(tuple(day.isocalendar())[:2] != tuple(execution.isocalendar())[:2], "WEEKLY_FINAL_SIGNAL_REQUIRED")
    if region == "KR":
        return C.check_timing(signal_date=signal, created_at_utc=created, now_utc=now, merged_at_utc=boundary)
    local_boundary = C.utc(boundary).tz_convert("America/New_York").date()
    _require(day.date() > local_boundary, "SIGNAL_BEFORE_FIXTURE_BOUNDARY")
    _require(C.utc(created) <= C.utc(now), "RECEIPT_CREATED_IN_THE_FUTURE")
    _require(bounds(region, day)[1] <= C.utc(created) < bounds(region, execution)[0], "BACKDATED_OR_BEFORE_FINAL_CLOSE")
    return execution


def prepare_receipt(observation, arm_inputs, *, fixture_clock=None):
    observation = A.adapt_synthetic_inputs(observation, arm_inputs)
    now = C.system_utc_now() if fixture_clock is None else C.utc(fixture_clock)
    # A test clock is never accepted for actual evidence (adapter enforces SYNTHETIC).
    region = observation["region"]
    signal = observation["signalDate"]
    if "createdAtUtc" in observation:
        _require(C.utc(observation["createdAtUtc"]) == now, "CREATION_MUST_MATCH_WRITER_CLOCK")
    execution = timing(region, signal, now, now, observation["fixtureBoundaryUtc"])
    cutoff = C.utc(observation["informationCutoffUtc"])
    _require(cutoff == bounds(region, pd.Timestamp(signal))[1], "SIGNAL_FINAL_CUTOFF_REQUIRED")
    _require(observation.get("marketState") in {"OBSERVED", "UNOBSERVED", "SOURCE_BLOCKED"}, "MARKET_STATE_REQUIRED")
    _require(observation.get("industryState") in {"OBSERVED", "UNOBSERVED", "SOURCE_BLOCKED"}, "INDUSTRY_STATE_REQUIRED")
    sources = [{k: deepcopy(v) for k, v in row.items() if k != "raw"} for row in observation["sourceEvidence"]]
    row = {"schema": "MASTER_PREPARED_RECEIPT_V1", "studyId": "portfolio-d-p0-p5-comparison-v1",
           "contractRef": A.contract_reference(), "specSha256": A.CANONICAL_SHA256,
           "evidenceClass": "SYNTHETIC_PREFLIGHT", "status": "PREPARED", "activationEnabled": False,
           "fixtureId": observation["fixtureId"], "region": region, "signalDate": signal,
           "createdAtUtc": now.isoformat(),
           "fixtureBoundaryUtc": C.utc(observation["fixtureBoundaryUtc"]).isoformat(),
           "executionDate": str(execution.date()),
           "informationCutoffUtc": cutoff.isoformat(), "calendarVersion": RC.CALENDAR_VERSION,
           "commonUniverse": observation["commonUniverse"], "sourceEvidence": sources,
           **{key: observation[key] for key in A.HASH_IDENTITIES},
           "marketState": observation["marketState"], "industryState": observation["industryState"],
           "stockQualification": observation["stockQualification"],
           "benchmarkTicker": "069500.KS" if region == "KR" else "SPY",
           "currency": "KRW" if region == "KR" else "USD", "supplementalBenchmark": None if region == "KR" else "QQQ",
           "nameCountPolicy": {"minimum": 0, "maximum": 5, "dynamic": True, "zeroNames": "REGIONAL_ETF_POLICY_ONLY"},
           "arms": {arm: {"status": "POLICY_BASELINE_ONLY" if arm == "P0" else "BLOCKED",
                          "reason": "NO_SELECTION_REQUIRED" if arm == "P0" else "NO_QUALIFIED_INPUT_REGISTRY"}
                    for arm in A.ARMS}}
    row["receiptSha256"] = C.receipt_digest(row)
    validate_receipt(row)
    return row


def validate_receipt(row):
    _require(isinstance(row, dict) and set(row) == RECEIPT_FIELDS, "RECEIPT_SHAPE_INVALID")
    C.scan_for_outcome_keys(row)
    A._refuse_actions(row)
    _require(row.get("schema") == "MASTER_PREPARED_RECEIPT_V1" and row.get("status") == "PREPARED"
             and row.get("evidenceClass") == "SYNTHETIC_PREFLIGHT" and row.get("activationEnabled") is False,
             "NON_SYNTHETIC_OR_ACTIVATED_RECEIPT_REFUSED")
    _require(row.get("contractRef") == A.contract_reference() and row.get("specSha256") == A.CANONICAL_SHA256,
             "CANONICAL_CONTRACT_CHANGED")
    _require(row.get("studyId") == A.contract_reference()["studyId"], "STUDY_ID_CHANGED")
    _require(row.get("region") in ("KR", "US") and row.get("receiptSha256") == C.receipt_digest(row), "RECEIPT_TAMPERED")
    # Reconstruct the pure input checks from retained metadata and verified digests.
    _require(row.get("commonUniverseSha256") == A.digest(row.get("commonUniverse")), "UNIVERSE_CHANGED")
    _require(row.get("benchmarkTicker") == ("069500.KS" if row["region"] == "KR" else "SPY"), "REGIONAL_ETF_REQUIRED")
    _require(row.get("calendarVersion") == RC.CALENDAR_VERSION, "CALENDAR_VERSION_CHANGED")
    _require(isinstance(row.get("fixtureId"), str) and row["fixtureId"].startswith("synthetic:"), "FIXTURE_ID_REQUIRED")
    _require(all(C.is_sha256(row.get(k)) for k in A.HASH_IDENTITIES), "COMMON_IDENTITIES_REQUIRED")
    _require(row.get("commonUniverse") and row["commonUniverse"] == sorted(set(row["commonUniverse"])), "COMMON_UNIVERSE_REQUIRED")
    cutoff = C.utc(row["informationCutoffUtc"])
    _require(cutoff == bounds(row["region"], pd.Timestamp(row["signalDate"]))[1], "SIGNAL_FINAL_CUTOFF_REQUIRED")
    _require(row.get("sourceEvidence"), "SOURCE_EVIDENCE_REQUIRED")
    roles = []
    for source in row["sourceEvidence"]:
        _require(set(source) == {"role", "sha256", "sourceCommit", "dataKind", "rightsStatus", "pitStatus",
                                 "availableAtUtc", "vintageAtUtc"}, "SOURCE_METADATA_SHAPE_INVALID")
        roles.append(source.get("role"))
        _require(source.get("dataKind") == "SYNTHETIC" and source.get("rightsStatus") == "SYNTHETIC_ONLY"
                 and source.get("pitStatus") == "VERIFIED" and C.is_sha256(source.get("sha256"))
                 and C.is_git_sha(source.get("sourceCommit")), "SOURCE_METADATA_INVALID")
        _require(C.utc(source["availableAtUtc"]) <= cutoff and C.utc(source["vintageAtUtc"]) <= cutoff, "SOURCE_NOT_AVAILABLE_AT_CUTOFF")
    _require(all(isinstance(r, str) and r for r in roles) and len(roles) == len(set(roles)), "SOURCE_ROLES_INVALID")
    _require(row.get("marketState") in {"OBSERVED", "UNOBSERVED", "SOURCE_BLOCKED"}
             and row.get("industryState") in {"OBSERVED", "UNOBSERVED", "SOURCE_BLOCKED"}, "STATE_INVALID")
    _require(row.get("nameCountPolicy") == {"minimum": 0, "maximum": 5, "dynamic": True,
             "zeroNames": "REGIONAL_ETF_POLICY_ONLY"}, "NAME_POLICY_CHANGED")
    _require(row.get("currency") == ("KRW" if row["region"] == "KR" else "USD"), "CURRENCY_CHANGED")
    _require(row.get("supplementalBenchmark") == (None if row["region"] == "KR" else "QQQ"), "SUPPLEMENTAL_BENCHMARK_CHANGED")
    _require(set(row.get("stockQualification", {})) == {f"S{i}" for i in range(1, 6)}
             and all(value in A.QUALIFICATION_STATES for value in row["stockQualification"].values()), "UNREGISTERED_ADMISSION")
    _require(set(row.get("arms", {})) == set(A.ARMS)
             and row["arms"]["P0"]["status"] == "POLICY_BASELINE_ONLY"
             and all(row["arms"][arm]["status"] == "BLOCKED" for arm in A.ARMS[1:]), "ARM_PROMOTION_REFUSED")
    _require(row["arms"] == {arm:{"status":"POLICY_BASELINE_ONLY" if arm == "P0" else "BLOCKED",
                                "reason":"NO_SELECTION_REQUIRED" if arm == "P0" else "NO_QUALIFIED_INPUT_REGISTRY"}
                             for arm in A.ARMS}, "ARM_METADATA_CHANGED")
    execution = timing(row["region"], row["signalDate"], row["createdAtUtc"], row["createdAtUtc"], row["fixtureBoundaryUtc"])
    _require(row.get("executionDate") == str(execution.date()), "EXECUTION_CHANGED")


def maturity_readiness(row, horizon, *, as_of_utc):
    validate_receipt(row)
    _require(type(horizon) is int and horizon in (126, 252), "H126_H252_ONLY")
    dates = sessions(row["region"], row["executionDate"], 2 * horizon + 50)
    _require(len(dates) > horizon and str(dates[0].date()) == row["executionDate"], "MATURITY_CALENDAR_INCOMPLETE")
    maturity = dates[horizon]
    return {"status": "CALENDAR_ELAPSED_DATA_UNOBSERVED" if C.utc(as_of_utc) >= bounds(row["region"], maturity)[1]
            else "OBSERVATION_INCOMPLETE", "maturitySession": str(maturity.date()),
            "horizonSessions": horizon, "performance": None, "evidenceCertified": False}


def _scratch_directory(directory):
    path = Path(directory)
    _require(path.exists() and path.is_dir() and not path.is_symlink(), "EXISTING_SYNTHETIC_STORE_REQUIRED")
    resolved = path.resolve()
    _require(not any(part in {"ledger", "signal-history", ".git", "state"} for part in resolved.parts), "PRODUCTION_STORE_REFUSED")
    roots = subprocess.check_output(["git", "-C", str(ROOT), "worktree", "list", "--porcelain"], text=True)
    for line in roots.splitlines():
        if line.startswith("worktree "):
            _require(not resolved.is_relative_to(Path(line[9:]).resolve()), "WORKTREE_STORE_REFUSED")
    for flag in ("--is-inside-work-tree", "--is-inside-git-dir"):
        found = subprocess.run(["git", "-C", str(resolved), "rev-parse", flag], capture_output=True, text=True)
        _require(found.returncode != 0 or found.stdout.strip() != "true", "GIT_REPOSITORY_STORE_REFUSED")
    marker = path / SENTINEL
    _require(marker.is_file() and not marker.is_symlink() and marker.read_bytes() == SENTINEL_BYTES,
             "SYNTHETIC_STORE_SENTINEL_REQUIRED")
    return resolved


def append_synthetic_receipt(directory, row):
    """Scratch-only serialized append, preserving the first receipt on requery.

    The exclusive lock is local/test only, never a production concurrency plan.
    No automatic initialization, scheduler, activation, or live writer exists.
    """
    validate_receipt(row)
    root = _scratch_directory(directory)
    path = root / (row["region"] + ".jsonl")
    _require(not path.is_symlink(), "SYMLINK_LEDGER_REFUSED")
    _require(not path.exists() or path.is_file(), "ORDINARY_SCRATCH_FILE_REQUIRED")
    _require(not path.exists() or path.stat().st_nlink == 1, "HARDLINK_LEDGER_REFUSED")
    lock = root / (row["region"] + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError("SYNTHETIC_WRITER_BUSY") from exc
    try:
        os.close(fd)
        rows = C.read_ledger(path, validate_receipt)
        key = (row["region"], row["signalDate"])
        def semantic(value):
            return C.canonical({k: v for k, v in value.items() if k not in {"receiptSha256", "createdAtUtc"}})
        for old in rows:
            if (old["region"], old["signalDate"]) == key:
                _require(semantic(old) == semantic(row), "SAME_WEEK_SOURCE_OR_INPUT_CONFLICT")
                return {"status": "UNCHANGED", "receiptSha256": old["receiptSha256"], "appendCount": 0}
        sha = C.append(path, row, validate=validate_receipt, key_fields=("region", "signalDate"))
        return {"status": "SYNTHETIC_APPENDED", "receiptSha256": sha, "appendCount": 1}
    finally:
        lock.unlink()
