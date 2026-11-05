from copy import deepcopy
import hashlib
import json
import os

import pytest

from pipeline import prospective_receipt_core as C
from pipeline import replay_calendar as RC
from research.master_integration_preflight_v1 import adapters as A
from research.master_integration_preflight_v1 import receipt as R


def inputs(region="KR", signal="2026-10-30", created=None):
    created = created or ("2026-10-30T10:00:00Z" if region == "KR" else "2026-10-30T22:00:00Z")
    cutoff = R.bounds(region, __import__('pandas').Timestamp(signal))[1].isoformat()
    raw = b'{"synthetic":"source"}'
    observation = {"dataKind": "SYNTHETIC", "fixtureId": "synthetic:weekly-observation", "region": region,
                   "signalDate": signal, "createdAtUtc": created, "fixtureBoundaryUtc": "2026-10-01T00:00:00Z",
                   "informationCutoffUtc": cutoff, "calendarVersion": RC.CALENDAR_VERSION,
                   "commonUniverse": ["SYN_A", "SYN_B"], "costPolicySha256": "a" * 64,
                   "executionPolicySha256": "b" * 64, "returnBasisSha256": "c" * 64,
                   "marketState": "OBSERVED", "industryState": "UNOBSERVED",
                   "stockQualification": {f"S{i}": "UNOBSERVED" for i in range(1, 6)},
                   "sourceEvidence": [{"role": "common", "raw": raw, "sha256": hashlib.sha256(raw).hexdigest(),
                                       "sourceCommit": "d" * 40, "dataKind": "SYNTHETIC",
                                       "rightsStatus": "SYNTHETIC_ONLY", "pitStatus": "VERIFIED",
                                       "availableAtUtc": "2026-10-29T00:00:00Z", "vintageAtUtc": "2026-10-29T00:00:00Z"}]}
    observation["commonUniverseSha256"] = A.digest(observation["commonUniverse"])
    arms = [{"arm": arm, **{key: observation[key] for key in A.IDENTITIES}} for arm in A.ARMS]
    return observation, arms


def prepared(region="KR"):
    observation, arms = inputs(region)
    return R.prepare_receipt(observation, arms, fixture_clock=observation["createdAtUtc"])


def scratch(tmp_path):
    path = tmp_path / "synthetic-store"
    path.mkdir()
    (path / R.SENTINEL).write_bytes(R.SENTINEL_BYTES)
    return path


@pytest.mark.parametrize("region", ["KR", "US"])
def test_no_selection_or_result_and_regional_receipt_codec(region):
    row = prepared(region)
    assert row["receiptSha256"] == C.receipt_digest(row)
    assert row["benchmarkTicker"] == ("069500.KS" if region == "KR" else "SPY")
    assert row["executionDate"] == "2026-11-02"
    assert row["nameCountPolicy"]["minimum"] == 0
    assert row["arms"]["P0"]["status"] == "POLICY_BASELINE_ONLY"
    assert all(row["arms"][p]["status"] == "BLOCKED" for p in A.ARMS[1:])
    assert row["industryState"] == "UNOBSERVED"
    assert row["activationEnabled"] is False and row["status"] == "PREPARED"
    C.scan_for_outcome_keys(row)


def test_same_week_idempotency_and_source_revision_conflict(tmp_path):
    path = scratch(tmp_path)
    row = prepared()
    assert R.append_synthetic_receipt(path, row)["appendCount"] == 1
    before = (path / "KR.jsonl").read_bytes()
    obs, arms = inputs(created="2026-10-30T11:00:00Z")
    later = R.prepare_receipt(obs, arms, fixture_clock=obs["createdAtUtc"])
    assert R.append_synthetic_receipt(path, later)["appendCount"] == 0
    assert (path / "KR.jsonl").read_bytes() == before
    obs["sourceEvidence"][0]["raw"] = b"synthetic:revised"
    obs["sourceEvidence"][0]["sha256"] = hashlib.sha256(b"synthetic:revised").hexdigest()
    revised = R.prepare_receipt(obs, arms, fixture_clock=obs["createdAtUtc"])
    with pytest.raises(ValueError, match="SAME_WEEK"):
        R.append_synthetic_receipt(path, revised)
    assert (path / "KR.jsonl").read_bytes() == before


def test_tamper_never_rewrites_previous_rows(tmp_path):
    path = scratch(tmp_path)
    row = prepared()
    R.append_synthetic_receipt(path, row)
    broken = deepcopy(row)
    broken["signalDate"] = "2026-10-23"
    (path / "KR.jsonl").write_text(json.dumps(broken) + "\n")
    before = (path / "KR.jsonl").read_bytes()
    with pytest.raises(ValueError, match="TAMPERED"):
        R.append_synthetic_receipt(path, row)
    assert (path / "KR.jsonl").read_bytes() == before


@pytest.mark.parametrize("region,signal,created", [
    ("KR", "2026-10-29", "2026-10-29T10:00:00Z"),
    ("US", "2026-07-03", "2026-07-03T22:00:00Z"),
    ("KR", "2026-10-30", "2026-10-30T08:59:00Z"),
    ("US", "2026-10-30", "2026-11-02T14:30:00Z"),
])
def test_weekly_final_calendar_holiday_and_backdate_rejection(region, signal, created):
    # Use a valid cutoff declaration; timing must independently refuse.
    obs, arms = inputs(region)
    obs["signalDate"], obs["createdAtUtc"] = signal, created
    with pytest.raises(ValueError):
        R.prepare_receipt(obs, arms, fixture_clock=created)


def test_claimed_past_creation_cannot_impersonate_writer_clock():
    obs, arms = inputs()
    with pytest.raises(ValueError, match="WRITER_CLOCK"):
        R.prepare_receipt(obs, arms, fixture_clock="2026-11-02T10:00:00Z")
    with pytest.raises(ValueError, match="WRITER_CLOCK"):
        R.prepare_receipt(obs, arms)


def test_kr_holiday_shortened_week_and_us_early_close():
    assert R.timing("US", "2026-11-27", "2026-11-27T18:01:00Z", "2026-11-27T18:01:00Z", "2026-10-01T00:00:00Z").strftime("%Y-%m-%d") == "2026-11-30"
    # KR Oct9 is a holiday, so Oct8 is a weekly final session.
    assert R.timing("KR", "2026-10-08", "2026-10-08T10:00:00Z", "2026-10-08T10:00:00Z", "2026-10-01T00:00:00Z").strftime("%Y-%m-%d") == "2026-10-12"


def test_absent_store_and_production_paths_refused_without_bootstrap(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="EXISTING"):
        R.append_synthetic_receipt(missing, prepared())
    assert not missing.exists()
    with pytest.raises(ValueError, match="SENTINEL"):
        R.append_synthetic_receipt(tmp_path, prepared())
    with pytest.raises(ValueError, match="WORKTREE"):
        R.append_synthetic_receipt(R.ROOT, prepared())
    path = scratch(tmp_path)
    (path / "KR.lock").touch()
    with pytest.raises(ValueError, match="BUSY"):
        R.append_synthetic_receipt(path, prepared())


def test_hardlink_does_not_create_a_writer_escape(tmp_path):
    path = scratch(tmp_path)
    outside = tmp_path / "protected"
    outside.write_bytes(b"")
    os.link(outside, path / "KR.jsonl")
    with pytest.raises(ValueError, match="HARDLINK"):
        R.append_synthetic_receipt(path, prepared())
    assert outside.read_bytes() == b""


def test_separate_git_repository_cannot_become_a_synthetic_store(tmp_path):
    import subprocess
    path=scratch(tmp_path)
    subprocess.run(["git","init","-q",str(path)],check=True)
    with pytest.raises(ValueError,match="GIT_REPOSITORY"):
        R.append_synthetic_receipt(path,prepared())
    assert not (path/"KR.jsonl").exists()


@pytest.mark.parametrize("field,value", [("studyId","other"),("activationEnabled",True),
                                       ("currency","EUR"),("supplementalBenchmark","QQQ")])
def test_resigned_metadata_cannot_change_contract_or_activation(field,value):
    row=prepared()
    row[field]=value
    row["receiptSha256"]=C.receipt_digest(row)
    with pytest.raises(ValueError):
        R.validate_receipt(row)


@pytest.mark.parametrize("region,horizon", [(r,h) for r in ("KR", "US") for h in (126,252)])
def test_maturity_never_creates_a_performance_or_certification(region,horizon):
    row = prepared(region)
    pending = R.maturity_readiness(row,horizon,as_of_utc=row["createdAtUtc"])
    assert pending["status"] == "OBSERVATION_INCOMPLETE" and pending["performance"] is None
    later = R.maturity_readiness(row,horizon,as_of_utc="2029-01-01T00:00:00Z")
    assert later["status"] == "CALENDAR_ELAPSED_DATA_UNOBSERVED" and later["performance"] is None
    assert later["evidenceCertified"] is False
