"""rp1-b-h1-state-v1: Track B's weekly prospective market-state receipts. Every price below is invented; no test reads the network or git."""
import importlib
import json

import numpy as np
import pandas as pd
import pytest

from pipeline import prospective_receipt_core as CORE
from pipeline import replay_calendar as RC
from pipeline import rp1_b_h1_state as B
from pipeline import rp1_b_state_receipt as PREVIEW

script = importlib.import_module("scripts.record_rp1_b_h1_state")
REAL_RUN_ISOLATED = script.run_isolated        # tests/conftest.py stubs the hook for every other test; captured before it does

SIGNAL = "2026-10-30"                           # a Friday weekly decision session; next session Monday 2026-11-02
NEXT_SIGNAL = "2026-11-06"
MERGED = "2026-10-27T03:00:00+00:00"            # Tuesday KST: first prospective session 2026-10-28, first weekly session 2026-10-30
SAT = "2026-10-31T04:35:00+00:00"               # the cron's real Saturday start: ~43.4 hours before Monday's open
SUN = "2026-11-01T04:35:00+00:00"               # Sunday: inside the final 24 hours
IDENTITY = {"commitSha": "a" * 40, "files": {"pipeline/rp1_b_h1_state.py": "b" * 64}}
PACKAGE = B.SOURCE["vendorPackage"]


def bars(end=SIGNAL, start="2024-08-01", drift=0.0006, amp=0.003, tail=None, volume=1.0e8):
    days = pd.DatetimeIndex(RC.sessions(start, end, "KR"))
    steps = np.full(len(days), drift) + amp * np.sin(np.arange(len(days)) / 3.0)
    if tail:
        n, tail_drift, tail_amp = tail
        steps[-n:] = tail_drift + tail_amp * (-1.0) ** np.arange(n)
    close = 100.0 * np.exp(np.cumsum(steps))
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": volume}, index=days)


def calm():
    return bars()


def storm():
    """A two-year rise, then 63 sessions of +-3% swings and a slide below the 200-day mean: FAST == 2 with a positive 24-month return."""
    return bars(drift=0.0012, tail=(63, -0.003, 0.03))


def slow_decline():
    """A quiet two-year decline: below the 200-day mean, low volatility (FAST == 1), negative 24-month return."""
    return bars(drift=-0.0004, amp=0.002)


def clock_of(*instants):
    """A writer clock that returns the instants in order and then stays at the last one."""
    queue = [pd.Timestamp(t) for t in instants]

    def clock():
        return queue.pop(0) if len(queue) > 1 else queue[0]
    return clock


def record(directory, frame, *instants, package=PACKAGE, merged=MERGED, fetch=None):
    fetch = fetch or (lambda start: (frame, package))
    return script.record(directory, clock=clock_of(*instants), fetch=fetch, merged_at=merged, code_identity=IDENTITY)


def status(directory, step="record"):
    return json.loads((directory / f"publication-status.{step}.json").read_text())


def receipts(directory):
    return B.read_receipts(directory / script.RECEIPTS, pathway=B.LIVE)


# --------------------------------------------------------------------------- #
# The three state cases and the definition
# --------------------------------------------------------------------------- #
def test_normal_market_is_recorded_not_adverse(tmp_path):
    assert record(tmp_path, calm(), SAT) == 0
    assert status(tmp_path)["status"] == "RECORDED"
    (row,) = receipts(tmp_path)
    s = row["state"]
    assert (s["fast"], s["adverse"], s["fastLegAdverse"], s["returnLegAdverse"]) == (0, False, False, False)
    assert s["trailing24mReturn"] > 0 and s["baseSessionDate"] == "2024-10-30" and s["target24mDate"] == "2024-10-30"
    assert row["undeterminedReasons"] == [] and row["previousReceiptSha256"] is None
    assert (row["signalDate"], row["executionDate"], row["evidenceClass"], row["productionEffect"]) == \
        (SIGNAL, "2026-11-02", "PROSPECTIVE_PAPER", "NONE")
    assert row["source"]["sourceId"] == "FDR_KS200" and row["source"]["servedLastDate"] == SIGNAL
    assert row["source"]["fetchedAtUtc"] <= row["createdAtUtc"] and row["authorization"]["firstProspectiveSession"] == "2026-10-28"


def test_fast_two_is_adverse_even_with_a_positive_24_month_return(tmp_path):
    assert record(tmp_path, storm(), SAT) == 0
    s = receipts(tmp_path)[0]["state"]
    assert s["fast"] == 2 and s["fastTrendAdverse"] and s["fastVolAdverse"] and s["vol63"] > 0.25
    assert s["trailing24mReturn"] > 0 and s["adverse"] is True


def test_negative_24_month_return_is_adverse_with_fast_one(tmp_path):
    assert record(tmp_path, slow_decline(), SAT) == 0
    s = receipts(tmp_path)[0]["state"]
    assert s["fast"] == 1 and s["fastVolAdverse"] is False and s["trailing24mReturn"] < 0 and s["adverse"] is True


def test_legs_equal_the_264_preview_on_a_complete_series():
    for frame in (calm(), storm(), slow_decline()):
        seen = B.observe(frame, SIGNAL)
        preview = PREVIEW.build_preview(frame["Close"].loc[B.fetch_start(SIGNAL):], SIGNAL)
        assert (seen["state"]["fast"], seen["state"]["trailing24mReturn"], seen["state"]["baseSessionDate"], seen["state"]["adverse"]) == \
            (preview["fast"], preview["trailing24mReturn"], preview["baseSessionDate"], preview["adverse"])


def test_definition_is_the_registered_b_h1_and_the_sealed_fast():
    spec = B.load_spec()
    assert spec["stateDefinition"]["definition"] == PREVIEW.DEFINITION == B.DEFINITION
    doc = (B.ROOT / "docs/research-program/03-studies-abc-ko.md").read_text(encoding="utf-8")
    assert "FAST=2(추세 이탈+고변동) 또는 직전 24개월 시장수익 < 0" in doc
    assert B.FAST_WINDOW_SESSIONS == 201 and B.LOOKBACK_MONTHS == 24 and spec["outcomeEvaluation"]["horizonSessions"] == 63
    assert spec["reference"]["sourceId"] == "FDR_KS200"
    model = json.loads((B.ROOT / "research_specs/kr-market-risk-model-v1.json").read_text(encoding="utf-8"))
    assert model["model"]["layers"]["FAST"]["input"] == spec["reference"]["sourceId"]


# --------------------------------------------------------------------------- #
# Missing legs: never benign
# --------------------------------------------------------------------------- #
def drop(frame, *dates):
    return frame.drop(index=pd.DatetimeIndex(dates))


def test_one_missing_leg_is_deferred_before_the_final_attempt_and_undetermined_after(tmp_path):
    no_base = drop(calm(), "2024-10-30")
    assert record(tmp_path, no_base, SAT) == 0
    assert status(tmp_path)["status"] == "DEFERRED" and status(tmp_path)["reason"].startswith("PROVIDER_WINDOW_GAP")
    assert not (tmp_path / script.RECEIPTS).exists()
    assert [a["status"] for a in script.read_attempts(tmp_path)] == ["DEFERRED"]
    assert record(tmp_path, no_base, SUN) == 0                       # the retry inside the final 24 hours records it
    (row,) = receipts(tmp_path)
    assert row["undeterminedReasons"] == ["TRAILING_24M_BASE_UNAVAILABLE"]
    assert row["state"]["trailing24mReturn"] is None and row["state"]["fast"] == 0 and row["state"]["adverse"] is None


def test_a_determined_adverse_leg_decides_when_the_other_is_missing(tmp_path):
    assert record(tmp_path, drop(storm(), "2024-10-30"), SUN) == 0
    row = receipts(tmp_path)[0]
    assert row["state"]["fast"] == 2 and row["state"]["trailing24mReturn"] is None and row["state"]["adverse"] is True


def test_both_legs_missing_is_undetermined(tmp_path):
    frame = drop(calm(), "2024-10-30", "2026-09-15")
    assert record(tmp_path, frame, SUN) == 0
    row = receipts(tmp_path)[0]
    assert row["undeterminedReasons"] == ["FAST_DATA_INSUFFICIENT", "TRAILING_24M_BASE_UNAVAILABLE"]
    assert row["state"]["fast"] is None and row["state"]["vol63"] is None and row["state"]["adverse"] is None
    assert "2026-09-15" in row["undeterminedDetail"]["fastWindowGapSessions"]


def test_a_session_missing_inside_the_window_is_a_hole_not_a_shorter_window():
    """The preview alone counts rows: one missing session lets 201 rows span 202 sessions. Calendar alignment refuses the leg instead."""
    frame = drop(storm(), "2026-09-15")
    assert PREVIEW.build_preview(frame["Close"].loc[B.fetch_start(SIGNAL):], SIGNAL)["fast"] is not None
    seen = B.observe(frame, SIGNAL)
    assert seen["state"]["fast"] is None and seen["undeterminedReasons"] == ["FAST_DATA_INSUFFICIENT"]


@pytest.mark.parametrize("volume", [float("nan"), None, -1.0, float("inf"), 0.0])
def test_a_window_session_with_unusable_volume_is_not_a_traded_session(volume):
    """Track A's VOLUME_INVALID fix is not undone here: a missing, non-finite or negative volume (or a suspension) carries no close."""
    frame = calm().astype({"Volume": object})
    frame.loc[pd.Timestamp("2026-09-15"), "Volume"] = volume
    seen = B.observe(frame, SIGNAL)
    assert seen["state"]["fast"] is None and "2026-09-15" in seen["detail"]["fastWindowGapSessions"]


def test_an_off_calendar_vendor_row_inside_a_window_removes_that_leg():
    frame = calm()
    extra = frame.loc[[pd.Timestamp("2026-09-15")]].copy()
    extra.index = pd.DatetimeIndex(["2026-09-13"])                   # a Sunday
    seen = B.observe(pd.concat([frame, extra]).sort_index(), SIGNAL)
    assert seen["state"]["fast"] is None and seen["undeterminedReasons"] == ["FAST_WINDOW_OFF_CALENDAR_ROW"]
    # 2026-09-18's 24-month target is 2024-09-18, a Chuseok holiday: the expected base is Friday 2024-09-13. A vendor row on the
    # holiday 2024-09-16 would be a later "session" on or before the target, so the base is ambiguous and the return leg is removed.
    holiday = bars(end="2026-09-18")
    assert B.observe(holiday, "2026-09-18")["state"]["baseSessionDate"] == "2024-09-13"
    ghost = holiday.loc[[pd.Timestamp("2024-09-13")]].copy()
    ghost.index = pd.DatetimeIndex(["2024-09-16"])
    seen = B.observe(pd.concat([holiday, ghost]).sort_index(), "2026-09-18")
    assert seen["state"]["trailing24mReturn"] is None and seen["undeterminedReasons"] == ["TRAILING_24M_BASE_OFF_CALENDAR_ROW"]
    early = holiday.loc[[pd.Timestamp("2024-09-13")]].copy()
    early.index = pd.DatetimeIndex(["2024-09-08"])                    # a Sunday before the base: not ambiguous
    assert B.observe(pd.concat([holiday, early]).sort_index(), "2026-09-18")["state"]["baseSessionDate"] == "2024-09-13"


# --------------------------------------------------------------------------- #
# Future data
# --------------------------------------------------------------------------- #
def test_a_row_after_the_signal_session_refuses_the_attempt(tmp_path):
    future = bars(end="2026-11-02")
    assert record(tmp_path, future, SAT) == 1
    assert status(tmp_path)["status"] == "REFUSED" and status(tmp_path)["reason"] == "VENDOR_ROW_AFTER_SIGNAL_SESSION"
    assert not (tmp_path / script.RECEIPTS).exists()
    saturday = calm()
    row = saturday.iloc[[-1]].copy()
    row.index = pd.DatetimeIndex(["2026-10-31"])
    with pytest.raises(B.AttemptStop, match="VENDOR_ROW_AFTER_SIGNAL_SESSION"):
        B.observe(pd.concat([saturday, row]), SIGNAL)


def test_the_state_depends_only_on_data_through_the_signal_session():
    """Changing every price after the signal session (here: the data a later download would carry) cannot move this receipt."""
    base = bars(end="2026-12-31")
    shocked = base.copy()
    shocked.loc[shocked.index > pd.Timestamp(SIGNAL), ["Open", "High", "Low", "Close"]] *= 0.5
    a = B.observe(base.loc[:SIGNAL], SIGNAL)
    b = B.observe(shocked.loc[:SIGNAL], SIGNAL)
    assert a == b


def test_the_signal_session_must_be_served(tmp_path):
    stale = bars(end="2026-10-29")                                    # the cache has not been updated with Friday yet
    assert record(tmp_path, stale, SAT) == 0 and status(tmp_path)["status"] == "DEFERRED"
    assert status(tmp_path)["reason"] == "SIGNAL_SESSION_CLOSE_UNAVAILABLE"
    invalid = calm().astype({"Volume": object})
    invalid.loc[pd.Timestamp(SIGNAL), "Volume"] = None
    assert record(tmp_path, invalid, SUN) == 0 and status(tmp_path)["status"] == "DEFERRED"
    assert status(tmp_path)["detail"] == {"state": "VOLUME_INVALID"}     # never recorded, even on the final attempt
    assert not (tmp_path / script.RECEIPTS).exists()


# --------------------------------------------------------------------------- #
# Timing: the receipt window
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("instant,expected", [
    ("2026-10-30T08:59:59+00:00", "SKIPPED"),        # 17:59:59 KST Friday: Friday is not final; Thursday is not a weekly session
    ("2026-10-30T09:00:00+00:00", "DEFERRED"),       # 18:00 KST: inside the window, but the next open is > 24 hours away
    ("2026-11-01T23:59:59+00:00", "RECORDED"),       # 08:59:59 KST Monday: the last second of the window
    ("2026-11-02T00:00:00+00:00", "SKIPPED"),        # 09:00 KST Monday: the open; outside the window
    ("2026-11-03T04:35:00+00:00", "SKIPPED"),        # a weekday run inside the KRX session
])
def test_receipt_window_boundaries(tmp_path, instant, expected):
    frame = drop(calm(), "2024-10-30")             # a provider gap, so the Friday-evening run defers rather than records
    if expected == "RECORDED":
        frame = calm()
    record(tmp_path, frame, instant)
    assert status(tmp_path)["status"] == expected
    assert (tmp_path / script.RECEIPTS).exists() == (expected == "RECORDED")


def test_a_complete_series_records_from_the_first_minute_of_the_window(tmp_path):
    assert record(tmp_path, calm(), "2026-10-30T09:00:00+00:00") == 0 and status(tmp_path)["status"] == "RECORDED"


def test_window_closing_during_the_download_or_the_write_refuses(tmp_path):
    start, during, after = "2026-11-01T23:59:00+00:00", "2026-11-01T23:59:30+00:00", "2026-11-02T00:00:00+00:00"
    assert record(tmp_path, calm(), start, after) == 1                         # the download ended after the open
    assert status(tmp_path)["status"] == "REFUSED"
    assert record(tmp_path, calm(), start, during, during, after) == 1        # the clock at the write is past the open
    assert status(tmp_path)["reason"].startswith("RECEIPT_WINDOW_CLOSED_DURING_RECORDING")
    assert not (tmp_path / script.RECEIPTS).exists()


def test_before_the_floor_and_before_registration_nothing_is_recorded(tmp_path):
    early = bars(end="2026-10-23")
    assert record(tmp_path, early, "2026-10-24T04:35:00+00:00") == 0
    assert status(tmp_path)["reason"].startswith("SIGNAL_BEFORE_REGISTERED_FLOOR")
    assert record(tmp_path, calm(), SAT, merged="2026-10-30T03:00:00+00:00") == 0       # merged on the signal's own KST date
    assert status(tmp_path)["reason"].startswith("SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY")
    assert not (tmp_path / script.RECEIPTS).exists()


@pytest.mark.parametrize("start,end", [("2026-09-14", "2026-10-16"), ("2026-12-14", "2027-01-15")])
def test_weekly_sessions_equals_the_core_definition_day_by_day(start, end):
    """Chuseok 2026 (Thursday-Friday holidays) moves that week's decision session to Wednesday; year-end closures likewise."""
    days = RC.sessions(start, end, "KR")
    fast = [str(d.date()) for d, _ in B.weekly_sessions(start, end)]
    assert fast == [str(d.date()) for d in days if CORE.is_weekly_decision_session(d)]
    if start.startswith("2026-09"):
        assert "2026-09-23" in fast


# --------------------------------------------------------------------------- #
# Duplicates, retries, chain and tampering
# --------------------------------------------------------------------------- #
def test_duplicate_runs_are_idempotent_and_the_next_week_chains(tmp_path):
    assert record(tmp_path, calm(), SAT) == 0
    first = (tmp_path / script.RECEIPTS).read_bytes()
    assert record(tmp_path, calm(), SUN) == 0
    assert status(tmp_path)["status"] == "SKIPPED" and status(tmp_path)["reason"].startswith("RECEIPT_ALREADY_EXISTS")
    assert (tmp_path / script.RECEIPTS).read_bytes() == first
    assert record(tmp_path, bars(end=NEXT_SIGNAL), "2026-11-07T04:35:00+00:00") == 0
    rows = receipts(tmp_path)
    assert [r["signalDate"] for r in rows] == [SIGNAL, NEXT_SIGNAL]
    assert rows[1]["previousReceiptSha256"] == rows[0]["receiptSha256"]
    assert (tmp_path / script.RECEIPTS).read_bytes().startswith(first)


def test_a_retry_after_a_provider_failure_records_once(tmp_path):
    calls = []

    def flaky(start):
        calls.append(start)
        if len(calls) == 1:
            raise ConnectionError("cache unreachable")
        return calm(), PACKAGE
    assert script.record(tmp_path, clock=clock_of(SAT), fetch=flaky, merged_at=MERGED, code_identity=IDENTITY) == 0
    assert status(tmp_path)["status"] == "DEFERRED" and status(tmp_path)["reason"].startswith("PROVIDER_FETCH_FAILED: ConnectionError")
    assert script.record(tmp_path, clock=clock_of(SUN), fetch=flaky, merged_at=MERGED, code_identity=IDENTITY) == 0
    assert status(tmp_path)["status"] == "RECORDED" and len(receipts(tmp_path)) == 1
    assert [a["reason"].split(":")[0] for a in script.read_attempts(tmp_path)] == ["PROVIDER_FETCH_FAILED"]


def _rewrite(path, rows):
    path.write_bytes(b"".join(CORE.canonical(r) + b"\n" for r in rows))


def _two_weeks(tmp_path):
    record(tmp_path, calm(), SAT)
    record(tmp_path, bars(end=NEXT_SIGNAL), "2026-11-07T04:35:00+00:00")
    return [json.loads(line) for line in (tmp_path / script.RECEIPTS).read_text().splitlines()]


def test_a_tampered_value_is_refused_even_with_a_recomputed_digest(tmp_path):
    rows = _two_weeks(tmp_path)
    rows[0]["state"]["adverse"] = True
    rows[0]["receiptSha256"] = CORE.receipt_digest(rows[0])
    _rewrite(tmp_path / script.RECEIPTS, rows)
    with pytest.raises(ValueError, match="ADVERSE_DISAGREES"):
        receipts(tmp_path)


def test_a_tampered_digest_a_deleted_row_and_a_reorder_are_refused(tmp_path):
    rows = _two_weeks(tmp_path)
    path = tmp_path / script.RECEIPTS
    bad = json.loads(json.dumps(rows))
    bad[1]["state"]["vol63"] = 0.01
    _rewrite(path, bad)
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        receipts(tmp_path)
    _rewrite(path, rows[1:])
    with pytest.raises(ValueError, match="LEDGER_CHAIN_BROKEN"):
        receipts(tmp_path)
    _rewrite(path, rows[::-1])
    with pytest.raises(ValueError, match="LEDGER_CHAIN_BROKEN"):
        receipts(tmp_path)
    path.write_bytes(CORE.canonical(rows[0]) + b"\n" + b'{"truncated":')
    with pytest.raises(ValueError, match="LEDGER_ROW_NOT_JSON"):
        receipts(tmp_path)


def test_a_broken_ledger_refuses_every_later_append(tmp_path):
    rows = _two_weeks(tmp_path)
    _rewrite(tmp_path / script.RECEIPTS, rows[1:])
    before = (tmp_path / script.RECEIPTS).read_bytes()
    assert record(tmp_path, bars(end="2026-11-13"), "2026-11-14T04:35:00+00:00") == 1
    assert status(tmp_path)["reason"].startswith("LEDGER_INTEGRITY_FAILED")
    assert (tmp_path / script.RECEIPTS).read_bytes() == before


def test_a_receipt_claiming_an_undetermined_leg_early_is_refused(tmp_path):
    record(tmp_path, drop(calm(), "2024-10-30"), SUN)
    row = json.loads((tmp_path / script.RECEIPTS).read_text())
    row["createdAtUtc"] = row["source"]["fetchedAtUtc"] = "2026-10-31T04:35:00+00:00"
    row["receiptSha256"] = CORE.receipt_digest(row)
    with pytest.raises(ValueError, match="BEFORE_THE_FINAL_ATTEMPT_WINDOW"):
        B.validate_receipt(row, pathway=B.LIVE)


def test_no_outcome_key_and_no_live_class_for_a_fixture():
    frame = calm()
    receipt = B.build_receipt(frame, pathway=B.SYNTHETIC, signal_date=SIGNAL, created_at_utc=SAT, now_utc=SAT, fetched_at_utc=SAT,
                              merged_at_utc=MERGED, spec=B.load_spec(verify_code=False), spec_digest="c" * 64, code_identity=IDENTITY,
                              vendor_package=PACKAGE, previous_receipt_sha256=None)
    CORE.scan_for_outcome_keys(receipt)
    assert receipt["evidenceClass"] == "SYNTHETIC_FIXTURE"
    with pytest.raises(ValueError, match="PATHWAY_MISMATCH"):
        B.validate_receipt(receipt, pathway=B.LIVE)


# --------------------------------------------------------------------------- #
# Provider failures and identity
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("served,reason", [
    (pd.DataFrame(), "PROVIDER_EMPTY_RESPONSE"),
    (None, "PROVIDER_EMPTY_RESPONSE"),
    (pd.DataFrame({"Open": [1.0]}, index=pd.DatetimeIndex([SIGNAL])), "PROVIDER_EMPTY_RESPONSE"),
])
def test_empty_or_shapeless_provider_answers_are_deferred(tmp_path, served, reason):
    assert record(tmp_path, served, SUN) == 0
    assert status(tmp_path)["status"] == "DEFERRED" and status(tmp_path)["reason"] == reason


def test_a_year_the_route_silently_skipped_removes_exactly_the_legs_that_read_it():
    """The route reads one CSV per year and skips a failed one without an error. Each skipped year costs only what reads it."""
    frame = calm()
    no_2024 = B.observe(frame[frame.index.year != 2024], SIGNAL)      # the 24-month base lives in 2024
    assert no_2024["state"]["fast"] == 0 and no_2024["state"]["trailing24mReturn"] is None and no_2024["state"]["adverse"] is None
    no_2025 = B.observe(frame[frame.index.year != 2025], SIGNAL)      # neither the FAST window nor the base reads 2025
    assert no_2025["state"] == B.observe(frame, SIGNAL)["state"]
    with pytest.raises(B.AttemptStop, match="SIGNAL_SESSION_CLOSE_UNAVAILABLE"):
        B.observe(frame[frame.index.year != 2026], SIGNAL)


def test_duplicate_vendor_dates_and_a_changed_package_are_refused(tmp_path):
    frame = calm()
    assert record(tmp_path, pd.concat([frame, frame.iloc[[-5]]]), SAT) == 1
    assert status(tmp_path)["reason"] == "VENDOR_DUPLICATE_DATES"
    assert record(tmp_path, frame, SAT, package="finance-datareader==0.9.200") == 1
    assert status(tmp_path)["reason"].startswith("SOURCE_ROUTE_CHANGED")
    assert not (tmp_path / script.RECEIPTS).exists()


def test_unknown_registration_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "registration_merged_at", lambda *a: (_ for _ in ()).throw(ValueError("SPEC_NOT_ON_MAIN")))
    assert script.record(tmp_path, clock=clock_of(SAT), fetch=lambda s: (calm(), PACKAGE), code_identity=IDENTITY) == 1
    assert status(tmp_path)["reason"] == "SPEC_NOT_ON_MAIN" and status(tmp_path)["status"] == "REFUSED"


def test_moved_code_or_dependency_refuses(tmp_path):
    import shutil
    root = tmp_path / "repo"
    for rel in (B.SPEC_PATH, *B.load_spec()["codeFileHashes"], *B.SCIENTIFIC_FILES):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(B.ROOT / rel, root / rel)
    B.load_spec(root)
    with (root / "pipeline/rp1_b_state_receipt.py").open("a") as stream:
        stream.write("\n# edited\n")
    with pytest.raises(ValueError, match="SCIENTIFIC_DEPENDENCY_CHANGED"):
        B.load_spec(root)
    with (root / "pipeline/rp1_b_h1_state.py").open("a") as stream:
        stream.write("\n# edited\n")
    with pytest.raises(ValueError, match="CODE_CHANGED_SINCE_REGISTRATION"):
        B.load_spec(root)
    values = B.conformance_values()
    values["fastVolThreshold"] = 0.3
    with pytest.raises(ValueError, match="conformance"):
        B.V1.verify_scientific_dependencies(B.load_spec(verify_code=False), files=B.SCIENTIFIC_FILES, values=values)


def test_the_receipt_stores_derived_values_and_identities_not_vendor_rows(tmp_path):
    record(tmp_path, calm(), SAT)
    row = receipts(tmp_path)[0]
    text = json.dumps(row)
    assert '"Close"' not in text and "Volume" not in text
    assert CORE.is_sha256(row["source"]["servedSha256"]) and CORE.is_sha256(row["inputIdentity"])
    other = calm()
    other.loc[pd.Timestamp("2025-03-04"), "Close"] *= 1.0001
    assert B.observe(other, SIGNAL)["inputIdentity"] != row["inputIdentity"]


# --------------------------------------------------------------------------- #
# Coverage and block geometry (signal-time facts only), outcome gate
# --------------------------------------------------------------------------- #
def test_coverage_reports_a_missed_week_with_its_last_attempt(tmp_path):
    assert record(tmp_path, bars(end="2026-10-29"), SUN) == 0                       # Friday never served: missed
    assert record(tmp_path, bars(end=NEXT_SIGNAL), "2026-11-07T04:35:00+00:00") == 0
    assert script.coverage(tmp_path, clock=clock_of("2026-11-09T04:35:00+00:00")) == 0
    report = json.loads((tmp_path / script.COVERAGE).read_text())
    assert report["dueSessions"] == 2 and report["recordedSessions"] == 1 and report["evidence"] is False
    assert report["missedSessions"] == [{"signalDate": SIGNAL, "lastAttempt": ["DEFERRED", "SIGNAL_SESSION_CLOSE_UNAVAILABLE"]}]
    assert report["blockGeometry"]["maturedBlocks"] == 0
    assert report["blockGeometry"]["inferenceStatus"] == "DESCRIPTIVE_ONLY_INSUFFICIENT_STATE_BLOCKS"


def test_block_geometry_counts_states_and_never_assigns_an_unobserved_week():
    weekly = [str(d.date()) for d, _ in B.weekly_sessions(SIGNAL, "2029-12-31")]
    fake = [{"signalDate": d, "state": {"adverse": (i // 13) % 2 == 0}, "undeterminedReasons": []} for i, d in enumerate(weekly)
            if i % 40 != 39]
    geo = B.state_blocks(fake, now_utc="2030-01-10T12:00:00+00:00", horizon=63, min_blocks=6, first_eligible=SIGNAL)
    assert geo["originSession"] == "2026-11-02" and geo["maturedBlocks"] == sum(geo["counts"].values())
    assert geo["counts"]["unobserved"] >= 0 and geo["maturedBlocks"] >= 12
    recorded = {r["signalDate"] for r in fake}
    for block in geo["blocks"]:
        assert block["state"] != "unobserved" or block["stateSignalDate"] not in recorded
        assert block["stateSignalDate"] < block["entrySession"]
    few = B.state_blocks(fake[:30], now_utc="2027-06-01T12:00:00+00:00", horizon=63, min_blocks=6, first_eligible=SIGNAL)
    assert few["inferenceStatus"] == "DESCRIPTIVE_ONLY_INSUFFICIENT_STATE_BLOCKS"


def test_outcome_evaluation_is_blocked_and_computes_nothing(tmp_path):
    assert script.outcomes(tmp_path) == 0
    st = status(tmp_path, "outcomes")
    assert st["status"] == "BLOCKED_OUTCOME_CONTRACT_NOT_REGISTERED" and st["computed"] is False
    assert {"D1_ELIGIBLE_POPULATION", "D6_INFERENCE"} <= set(st["openDecisions"])
    spec = B.load_spec()
    spec["outcomeEvaluation"]["registeredContract"] = {"id": "edited-in-place"}
    with pytest.raises(ValueError, match="OUTCOME_CONTRACT_STATE_UNEXPECTED"):
        B.outcome_gate(spec)
    assert not (tmp_path / "outcomes.jsonl").exists()


# --------------------------------------------------------------------------- #
# Integration with the paper-ledger step: isolated, visible, never blocking
# --------------------------------------------------------------------------- #
def test_run_all_writes_every_step_and_an_aggregate(tmp_path, monkeypatch):
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp("2026-11-03T04:35:00Z"))
    assert script.run_all(tmp_path) == 0
    aggregate = json.loads((tmp_path / script.STATUS).read_text())
    assert aggregate["status"] == "OK" and aggregate["signalRecordState"] == "SKIPPED"
    assert set(aggregate["steps"]) == {"record", "coverage", "outcomes"} and aggregate["productionEffect"] == "NONE"


def test_a_failing_step_is_visible_and_does_not_stop_the_next(tmp_path, monkeypatch):
    monkeypatch.setattr(script, "record", lambda directory: (_ for _ in ()).throw(RuntimeError("boom")))
    assert script.run_all(tmp_path) == 1
    aggregate = json.loads((tmp_path / script.STATUS).read_text())
    assert aggregate["status"] == "STEP_FAILED" and aggregate["failedSteps"] == ["record"]
    assert aggregate["steps"]["outcomes"]["status"] == "BLOCKED_OUTCOME_CONTRACT_NOT_REGISTERED"


def test_isolated_child_timeout_and_crash_are_written_and_returned(tmp_path):
    import sys
    code = REAL_RUN_ISOLATED(tmp_path, timeout=1, command=[sys.executable, "-c", "import time; time.sleep(5)"])
    assert code == 124 and json.loads((tmp_path / script.STATUS).read_text())["failedSteps"] == ["hook"]
    assert REAL_RUN_ISOLATED(tmp_path, command=[sys.executable, "-c", "raise SystemExit(3)"]) == 3
    assert status(tmp_path, "hook")["reason"] == "CHILD_PROCESS_EXITED_3"
    assert REAL_RUN_ISOLATED(tmp_path, command=[sys.executable, "-c", "pass"]) == 0
    assert status(tmp_path, "hook")["status"] == "OK" and json.loads((tmp_path / script.STATUS).read_text())["status"] == "OK"


def test_paper_ledger_step_calls_the_isolated_hook_and_survives_its_failure(tmp_path, monkeypatch):
    update = importlib.import_module("scripts.update_ledger")
    monkeypatch.setattr(importlib.import_module("scripts.record_kr_selection_challenger"), "run_all", lambda *a: 0)
    monkeypatch.setattr(importlib.import_module("scripts.record_kr_selection_challenger_v2"), "run_all", lambda *a: 0)
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: {})
    seen = []
    monkeypatch.setattr(script, "run_isolated", lambda directory, **k: seen.append(directory) or 0)
    site = {"modelVersion": "m", "generatedAt": "2026-10-31T04:30:00+00:00", "provenance": {"modelVersion": "m"}}
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site))
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    assert update.main([str(path), str(ledger)]) == 0
    assert seen == [ledger / "research-strategies" / B.STUDY]
    monkeypatch.setattr(script, "run_isolated", lambda *a, **k: 124)
    assert update.main([str(path), str(ledger)]) == 0
    monkeypatch.setattr(script, "run_isolated", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert update.main([str(path), str(ledger)]) == 0
    assert not list((B.ROOT / ".github/workflows").glob("*rp1-b*"))


def test_the_isolated_child_really_runs_the_cli(tmp_path):
    """One real child process through the script's own CLI (the clock-free outcome gate, so the test cannot depend on the weekday)."""
    import sys
    study = tmp_path / "study"
    command = [sys.executable, str(B.ROOT / "scripts/record_rp1_b_h1_state.py"), "outcomes", str(study)]
    assert REAL_RUN_ISOLATED(study, timeout=300, command=command) == 0
    assert status(study, "outcomes")["status"] == "BLOCKED_OUTCOME_CONTRACT_NOT_REGISTERED"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["study"]
