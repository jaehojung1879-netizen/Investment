"""Invented index only. No market downloads, LIVE rows or historical outcomes."""
import json
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import pytest

from pipeline import rp1_b_state_recording as B

SIGNAL = "2026-09-11"
MERGED = "2026-09-03T10:00:00Z"
NOW = "2026-09-11T09:05:00Z"


def source(signal=SIGNAL, kind="rising"):
    days = B.RC.sessions("2024-01-02", signal, "KR")
    changes = np.full(len(days), 0.0004) + 0.001 * np.sin(np.arange(len(days)))
    if kind == "negative24m":
        changes = np.full(len(days), -0.0004)
    if kind == "fast_only":
        # Above the 24m base, but below SMA200 with >25% Vol63.
        changes[:] = 0.001
        changes[-63:] = np.tile([0.025, -0.025], 32)[:63] - 0.002
    values = 100 * np.exp(np.cumsum(changes))
    rows = [{"sessionDate": str(d.date()), "close": float(v)} for d, v in zip(days, values)]
    final = (pd.Timestamp(signal) + B.P.KR_CLOSE_FINAL_UTC).tz_localize("UTC")
    s = {"schemaVersion": 1, "evidenceClass": B.SYNTHETIC, "sourceId": "SYNTHETIC_KR_INDEX",
         "instrumentId": "SYNTHETIC_KR_INDEX", "priceBasis": "SYNTHETIC_INDEX_CLOSE", "signalDate": signal,
         "availableAtUtc": final.isoformat(), "observedAtUtc": (final + pd.Timedelta(minutes=1)).isoformat(),
         "observations": rows}
    return seal_source(s)


def seal_source(s):
    s["sourceSha256"] = B.source_digest(s)
    return s


def build(s=None, *, merged=MERGED, now=NOW):
    return B.build_synthetic_receipt(s if s is not None else source(), merged_at_utc=merged, now_utc=now)


def redigest(r):
    r["receiptSha256"] = B.P.receipt_digest(r)
    return r


@pytest.mark.parametrize("kind,fast_adverse,return_adverse,adverse", [
    ("rising", False, False, False), ("fast_only", True, False, True), ("negative24m", False, True, True),
])
def test_original_OR_rule_and_each_leg(kind, fast_adverse, return_adverse, adverse):
    s = source(kind=kind); r = build(s); p = r["preview"]
    assert (p["fast"] == 2) is fast_adverse
    assert (p["trailing24mReturn"] < 0) is return_adverse
    assert p["adverse"] is adverse
    assert r["evidenceClass"] == "SYNTHETIC_FIXTURE"
    assert r["purpose"] == "MARKET_OBSERVED_STATE_ONLY"
    assert B.validate_synthetic_receipt(r, source=s)
    assert r["nextSessionDate"] == "2026-09-14"


@pytest.mark.parametrize("kind,expected", [("rising", None), ("negative24m", True)])
def test_missing_intermediate_KRX_session_makes_FAST_unavailable_not_row_compressed(kind, expected):
    s = source(kind=kind)
    missing = s["observations"].pop(-10)["sessionDate"]
    r = build(seal_source(s))
    assert r["availability"]["missingSessions"] == [missing]
    assert r["availability"]["fast"] == "UNAVAILABLE"
    assert r["preview"]["fast"] is None
    assert r["preview"]["trailing24mReturn"] is not None
    assert r["preview"]["adverse"] is expected


@pytest.mark.parametrize("kind,expected", [("fast_only", True), ("rising", None)])
def test_missing_24m_base_differs_from_missing_FAST_and_adverse_available_leg_decides(kind, expected):
    s = source(kind=kind)
    base = B.B.build_preview(pd.Series([r["close"] for r in s["observations"]],
                                       index=pd.to_datetime([r["sessionDate"] for r in s["observations"]])), SIGNAL)["baseSessionDate"]
    s["observations"] = [r for r in s["observations"] if r["sessionDate"] != base]
    r = build(seal_source(s))
    assert r["availability"]["base24m"] == "UNAVAILABLE"
    assert r["preview"]["trailing24mReturn"] is None
    assert r["preview"]["fast"] is not None and r["preview"]["adverse"] is expected
    assert r["preview"]["unavailableReasons"] == ["TRAILING_24M_BASE_UNAVAILABLE"]


def test_both_inputs_unavailable_stays_unknown():
    s = source(); s["observations"] = s["observations"][-10:]
    r = build(seal_source(s))
    assert r["preview"]["adverse"] is None
    assert set(r["preview"]["unavailableReasons"]) == {"FAST_DATA_INSUFFICIENT", "TRAILING_24M_BASE_UNAVAILABLE"}


def test_missing_signal_close_is_explicit_not_stale_success():
    s = source(); s["observations"].pop()
    r = build(seal_source(s))
    assert r["availability"]["missingSessions"] == [SIGNAL]
    assert r["preview"]["unavailableReasons"] == ["SIGNAL_DATE_CLOSE_UNAVAILABLE"]
    assert r["preview"]["adverse"] is None


def test_invalid_session_close_preserves_reason_and_no_fill():
    s = source(); day = s["observations"][-7]["sessionDate"]; s["observations"][-7]["close"] = None
    r = build(seal_source(s))
    assert r["availability"]["missingSessions"] == []
    assert r["availability"]["invalidCloseSessions"] == [day]
    assert r["preview"]["fast"] is None


def test_KRX_holiday_is_not_a_missing_observation_and_off_calendar_bar_refused():
    s = source(); r = build(s)
    assert "2026-07-17" not in r["availability"]["missingSessions"]
    s["observations"].append({"sessionDate": "2026-07-17", "close": 100})
    s["observations"].sort(key=lambda row: row["sessionDate"])
    with pytest.raises(ValueError, match="OFF_CALENDAR"):
        build(seal_source(s))


def test_holiday_Friday_uses_actual_Thursday_week_end_and_Monday_open():
    r=build(source("2026-07-16"),merged="2026-07-09T10:00:00Z",now="2026-07-16T09:05:00Z")
    assert r["nextSessionDate"]=="2026-07-20"
    with pytest.raises(ValueError,match="NOT_A_KR_SESSION"):
        build(source("2026-07-17"),merged="2026-07-09T10:00:00Z",now="2026-07-17T09:05:00Z")


@pytest.mark.parametrize("now,error", [("2026-09-11T09:00:00Z", None),
    ("2026-09-11T08:59:59Z", "BEFORE_SIGNAL_CLOSE"), ("2026-09-11T03:00:00Z", "BEFORE_SIGNAL_CLOSE"),
    ("2026-09-14T00:00:00Z", "AFTER_EXECUTION_OPEN"), ("2026-09-14T00:00:01Z", "AFTER_EXECUTION_OPEN")])
def test_finality_and_next_open_boundaries(now, error):
    s = source(); s["observedAtUtc"] = s["availableAtUtc"]
    if error:
        with pytest.raises(ValueError, match=error): build(seal_source(s), now=now)
    else:
        assert build(seal_source(s), now=now)["createdAtUtc"] == "2026-09-11T09:00:00+00:00"


def test_same_KST_day_authorization_is_not_prospective():
    with pytest.raises(ValueError, match="BEFORE_PROSPECTIVE_ELIGIBILITY"):
        build(merged="2026-09-10T23:59:00Z")


@pytest.mark.parametrize("field,value", [("availableAtUtc", "2026-09-11T10:00:00Z"),
    ("observedAtUtc", "2026-09-11T10:00:00Z"), ("observedAtUtc", "2026-09-11T08:59:59Z"),
    ("observedAtUtc", "2026-09-11T09:01:00"), ("observedAtUtc", "NaT")])
def test_availability_and_observation_clocks(field, value):
    s=source(); s[field]=value
    with pytest.raises(ValueError): build(seal_source(s))


@pytest.mark.parametrize("mutation,error", [
    (lambda s:s["observations"][0].update(close=101), "SOURCE_HASH_MISMATCH"),
    (lambda s:s.update(observations=[]), "SOURCE_INPUT_EMPTY"),
    (lambda s:s.update(instrumentId="REAL_INDEX"), "NOT_AN_ADMITTED"),
    (lambda s:s.update(evidenceClass="PROSPECTIVE_PAPER"), "NOT_AN_ADMITTED"),
    (lambda s:s["observations"].append(s["observations"][-1]), "DUPLICATE_OR_UNORDERED"),
    (lambda s:s["observations"].append({"sessionDate":"2026-09-14","close":1}), "DATA_AFTER"),
    (lambda s:s["observations"][-1].update(close=True), "CLOSE_MALFORMED"),
])
def test_bad_sources_refused(mutation, error):
    s=source(); mutation(s)
    if error != "SOURCE_HASH_MISMATCH": seal_source(s)
    with pytest.raises(ValueError, match=error): build(s)


def test_contract_disk_tampering_refused_without_touching_real_contract(monkeypatch, tmp_path):
    target=tmp_path/B.CONTRACT_PATH; target.parent.mkdir(parents=True)
    target.write_bytes((B.ROOT/B.CONTRACT_PATH).read_bytes()+b" ")
    monkeypatch.setattr(B,"ROOT",tmp_path)
    with pytest.raises(ValueError, match="CONTRACT_HASH_MISMATCH"): build()


def test_dependency_and_CLI_disk_identity_are_measured(monkeypatch, tmp_path):
    identity=B.current_identity()
    paths = [pin["path"] for pin in identity["codeFiles"]]
    assert "pipeline/rp1_b_state_receipt.py" in paths
    assert "pipeline/kr_market_risk_model.py" in paths
    assert "pipeline/replay_calendar.py" in paths
    assert "scripts/record_rp1_b_state.py" in paths
    for rel in paths+[B.CONTRACT_PATH]:
        p=tmp_path/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes((B.ROOT/rel).read_bytes())
    monkeypatch.setattr(B,"ROOT",tmp_path)
    assert B.current_identity()==identity
    (tmp_path/"pipeline/rp1_b_state_receipt.py").write_text("# changed code\n")
    assert B.current_identity()["codeSha256"] != identity["codeSha256"]


@pytest.mark.parametrize("field", ["contractSha256", "codeSha256"])
def test_rehashed_receipt_cannot_forge_contract_or_code_identity(field):
    r=build(); r["identity"][field]="a"*64
    with pytest.raises(ValueError,match="IDENTITY_MISMATCH"): B.validate_synthetic_receipt(redigest(r))


def test_redigested_receipt_must_match_source_not_just_arithmetic(tmp_path):
    s=source(); r=build(s)
    # A different internally consistent state with its own preview digest.
    r["preview"]["trailing24mReturn"]=-0.1; r["preview"]["adverse"]=True
    r["preview"]["receiptSha256"]=B.P.receipt_digest(r["preview"])
    with pytest.raises(ValueError,match="DISAGREES_WITH_SOURCE"):
        B.append_synthetic(tmp_path/"ledger.jsonl",redigest(r),source=s,expected_checkpoint=B.checkpoint())
    assert not (tmp_path/"ledger.jsonl").exists()


def test_normal_append_is_immutable_and_duplicate_refused(tmp_path):
    path=tmp_path/"ledger.jsonl"; s=source(); r=build(s)
    pin=B.append_synthetic(path,r,source=s,expected_checkpoint=B.checkpoint()); original=path.read_bytes()
    assert B.verify_synthetic_ledger(path,expected_checkpoint=pin)["rows"]==1
    with pytest.raises(ValueError,match="ALREADY_EXISTS"):
        B.append_synthetic(path,r,source=s,expected_checkpoint=pin)
    s2=source("2026-09-18"); r2=build(s2,now="2026-09-18T09:05:00Z")
    pin2=B.append_synthetic(path,r2,source=s2,expected_checkpoint=pin)
    assert path.read_bytes().startswith(original)
    assert B.verify_synthetic_ledger(path,expected_checkpoint=pin2)["rows"]==2


@pytest.mark.parametrize("attack", ["edit", "duplicate", "truncate", "delete", "redigest_entire_history"])
def test_ledger_unauthorized_mutation_and_duplicate_addition(attack, tmp_path):
    path=tmp_path/"ledger.jsonl"; s=source(); r=build(s)
    pin=B.append_synthetic(path,r,source=s,expected_checkpoint=B.checkpoint()); raw=path.read_bytes()
    if attack=="edit": raw=raw.replace(b'"adverse":false',b'"adverse":true')
    if attack=="duplicate": raw+=raw
    if attack=="truncate": raw=raw[:-1]
    if attack=="delete": raw=b""
    if attack=="redigest_entire_history":
        row=json.loads(raw); row["receipt"]["source"]["observedAtUtc"]="2026-09-11T09:02:00+00:00"
        redigest(row["receipt"]); row["recordSha256"]=B.digest({k:v for k,v in row.items() if k!="recordSha256"})
        raw=B.P.canonical(row)+b"\n"
    path.write_bytes(raw)
    with pytest.raises(ValueError): B.verify_synthetic_ledger(path,expected_checkpoint=pin)


def test_duplicate_addition_is_rejected_even_with_a_new_untrusted_byte_hash(tmp_path):
    path=tmp_path/"ledger.jsonl"; s=source(); r=build(s)
    B.append_synthetic(path,r,source=s,expected_checkpoint=B.checkpoint())
    first=json.loads(path.read_bytes()); extra=json.loads(path.read_bytes())
    extra["previousSha256"]=first["recordSha256"]
    extra["recordSha256"]=B.digest({k:v for k,v in extra.items() if k!="recordSha256"})
    raw=B.P.canonical(first)+b"\n"+B.P.canonical(extra)+b"\n"; path.write_bytes(raw)
    with pytest.raises(ValueError,match="DUPLICATE_OR_OUT_OF_ORDER"):
        B.verify_synthetic_ledger(path,expected_checkpoint=B.checkpoint(raw,2))


def test_hardlinked_existing_file_is_never_appended(tmp_path):
    path=tmp_path/"ledger.jsonl"; s=source(); r=build(s)
    pin=B.append_synthetic(path,r,source=s,expected_checkpoint=B.checkpoint())
    linked=tmp_path/"linked.jsonl"; os.link(path,linked); original=path.read_bytes()
    s2=source("2026-09-18"); r2=build(s2,now="2026-09-18T09:05:00Z")
    with pytest.raises(ValueError,match="SINGLE_LINK_FILE"):
        B.append_synthetic(linked,r2,source=s2,expected_checkpoint=pin)
    assert path.read_bytes()==original


def test_concurrent_writers_with_same_pin_cannot_duplicate(tmp_path):
    path=tmp_path/"ledger.jsonl"; s=source(); r=build(s)
    def attempt(_):
        try: return B.append_synthetic(path,r,source=s,expected_checkpoint=B.checkpoint())
        except ValueError: return "REFUSED"
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(attempt,range(2)))
    assert sum(isinstance(x,dict) for x in results)==1
    assert results.count("REFUSED")==1
    assert len(path.read_bytes().splitlines())==1


def test_LIVE_refuses_before_any_source_or_ledger_access(monkeypatch):
    def no_access(*a, **kw): raise AssertionError("unexpected file access")
    monkeypatch.setattr(Path,"read_bytes",no_access)
    monkeypatch.setattr(Path,"open",no_access)
    with pytest.raises(ValueError,match="DISABLED_PENDING_REGISTRATION"): B.record_live()


def test_synthetic_cannot_write_into_checkout(monkeypatch, tmp_path):
    s=source(); r=build(s)
    # Use an existing tracked path: it must be refused before opening it.
    target=B.ROOT/"pipeline/rp1_b_state_receipt.py"; original=target.read_bytes()
    with pytest.raises(ValueError,match="OUTSIDE_CHECKOUT"):
        B.append_synthetic(target,r,source=s,expected_checkpoint=B.checkpoint())
    assert target.read_bytes()==original


def test_future_results_and_unknown_fields_are_not_a_receipt():
    r=build(); r["preview"]["forwardReturn"]=0.1
    with pytest.raises(ValueError,match="OUTCOME_FIELD"): B.validate_synthetic_receipt(redigest(r))
    r=build(); r["weights"]={"fake":1}
    with pytest.raises(ValueError,match="FIELDS_MISMATCH"): B.validate_synthetic_receipt(redigest(r))
    r=build(); r["preview"]["weights"]={"fake":1}
    redigest(r["preview"])
    with pytest.raises(ValueError,match="PREVIEW_FIELDS_MISMATCH"): B.validate_synthetic_receipt(redigest(r))


def cli(*args):
    return subprocess.run([sys.executable,str(B.ROOT/"scripts/record_rp1_b_state.py"),*map(str,args)],
                          capture_output=True,text=True,cwd=B.ROOT)


def test_cli_LIVE_missing_input_and_IO_errors_are_nonzero(tmp_path):
    result=cli("record-live")
    assert result.returncode==1 and "DISABLED_PENDING_REGISTRATION" in result.stderr and not result.stdout
    pin=tmp_path/"pin.json"; pin.write_text(json.dumps(B.checkpoint()))
    result=cli("record-synthetic","--input",tmp_path/"missing.json","--ledger",tmp_path/"ledger.jsonl",
               "--checkpoint",pin,"--merged-at",MERGED,"--now",NOW)
    assert result.returncode==1 and "REFUSED" in result.stderr and not result.stdout
    assert not (tmp_path/"ledger.jsonl").exists()
    inp=tmp_path/"failed-source.json"; inp.write_text(json.dumps({"status":"SERVER_ERROR","httpStatus":503}))
    result=cli("record-synthetic","--input",inp,"--ledger",tmp_path/"ledger.jsonl",
               "--checkpoint",pin,"--merged-at",MERGED,"--now",NOW)
    assert result.returncode==1 and "SOURCE_FIELDS_MISMATCH" in result.stderr and not result.stdout


@pytest.mark.parametrize("key,value", [("expectedSessions",1),("suppliedSessions",True),
    ("fast","UNAVAILABLE"),("missingSessions",["2026-07-17"]),("invalidCloseSessions",["garbage"])])
def test_rehashed_availability_tampering_fails_standalone_validation(key,value):
    r=build();r["availability"][key]=value
    with pytest.raises(ValueError): B.validate_synthetic_receipt(redigest(r))


def test_writer_IO_failure_propagates_instead_of_success(monkeypatch,tmp_path):
    s=source(); r=build(s)
    def failure(*args): raise OSError("synthetic storage failure")
    monkeypatch.setattr(B.os,"fsync",failure)
    with pytest.raises(OSError,match="storage failure"):
        B.append_synthetic(tmp_path/"ledger.jsonl",r,source=s,expected_checkpoint=B.checkpoint())


def test_cli_end_to_end_synthetic_only(tmp_path):
    inp=tmp_path/"source.json"; inp.write_text(json.dumps(source()))
    pin=tmp_path/"pin.json"; pin.write_text(json.dumps(B.checkpoint())); ledger=tmp_path/"ledger.jsonl"
    result=cli("record-synthetic","--input",inp,"--ledger",ledger,"--checkpoint",pin,"--merged-at",MERGED,"--now",NOW)
    assert result.returncode==0,result.stderr
    result_pin=json.loads(result.stdout)["checkpoint"]
    pin.write_text(json.dumps(result_pin))
    result=cli("validate-synthetic","--ledger",ledger,"--checkpoint",pin)
    assert result.returncode==0 and json.loads(result.stdout)["rows"]==1
    assert json.loads(ledger.read_text())["receipt"]["evidenceClass"]==B.SYNTHETIC


def test_no_live_authorization_or_evaluation_was_invented():
    status=B.activation_status()
    assert status["liveEnabled"] is False and status["registeredAuthorization"] is None
    assert "H63_BLOCK_ORIGIN_SPREAD_SAMPLE_AND_EVALUATION_SCHEDULE_UNREGISTERED" in status["blockers"]
    assert B.load_contract()["sourceAdmission"] is None
