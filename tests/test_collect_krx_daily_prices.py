"""Synthetic-only collector integrity audit; real transports are forbidden."""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location(
    "collect_krx_daily_prices", ROOT / "scripts" / "collect_krx_daily_prices.py")
CKP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CKP)

AS_OF = dt.date(2026, 10, 19)


def _run(tmp_path, monkeypatch, targets):
    monkeypatch.setattr(CKP, "call", lambda *a, **k: {"OutBlock_1": []})
    return CKP.collect(tmp_path, targets, auth_key="k", base="b", keep=None,
                       max_calls=10, max_minutes=1.0, pace=0, log=lambda *_: None,
                       as_of=AS_OF)


def test_recent_empty_answer_is_provisional_not_done(tmp_path, monkeypatch):
    result = _run(tmp_path, monkeypatch, ["2026-10-16", "2026-10-19"])
    assert result["closed"] == []
    assert result["provisional"] == ["2026-10-16", "2026-10-19"]
    assert result["remaining"] == 2
    assert CKP.load_done(tmp_path) == set()


@pytest.mark.parametrize("day", ["2026-10-16", "2026-10-15", "2026-10-14", "2026-09-01"])
def test_empty_open_session_never_ages_into_done(tmp_path, monkeypatch, day):
    result = _run(tmp_path, monkeypatch, [day])
    assert result["closed"] == []
    assert result["provisional"] == [day]
    assert result["remaining"] == 1
    assert CKP.load_done(tmp_path) == set()


def _payload(day="2026-10-15", code="005930"):
    return {"OutBlock_1": [{"ISU_CD": code, "BAS_DD": day.replace("-", ""),
                            "TDD_CLSPRC": "1000", "TDD_OPNPRC": "1000",
                            "TDD_HGPRC": "1000", "TDD_LWPRC": "1000",
                            "ACC_TRDVOL": "10", "LIST_SHRS": "1000"}]}


def _answer(tmp_path, monkeypatch, targets, payload, **kw):
    asked = kw.pop("asked", [])
    def fake(*a, **k):
        asked.append(a[2]["basDd"])
        return payload
    monkeypatch.setattr(CKP, "call", fake)
    result = CKP.collect(tmp_path, targets, auth_key="synthetic", base="unused",
                         keep=kw.pop("keep", None), max_calls=kw.pop("max_calls", 10),
                         max_minutes=kw.pop("max_minutes", 1), pace=0, log=lambda *_: None,
                         as_of=AS_OF, **kw)
    return result, asked


def test_wrong_served_date_does_not_complete_requested_session(tmp_path, monkeypatch):
    result, _ = _answer(tmp_path, monkeypatch, ["2026-10-15"], _payload("2026-10-14"))
    assert result["stopped"]
    assert CKP.load_done(tmp_path) == set()
    assert not list(tmp_path.glob("krx-prices-*.jsonl.gz"))


@pytest.fixture(autouse=True)
def forbid_real_api(monkeypatch):
    import urllib.request
    def forbidden(*a, **kw):
        pytest.fail("real API/transport access is forbidden in collector audit")
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


@pytest.mark.parametrize("day", ["2026-10-17", "2026-10-18", "2026-10-09", "2026-10-05", "2026-07-17", "2013-12-31"])
def test_only_pinned_calendar_closures_are_permanent_without_api(tmp_path, monkeypatch, day):
    def unexpected(*a, **kw):
        pytest.fail("closed-date classification must not call KRX")
    monkeypatch.setattr(CKP, "call", unexpected)
    result = CKP.collect(tmp_path, [day], auth_key="synthetic", base="unused", keep=None,
                         max_calls=0, max_minutes=1, pace=0, log=lambda *_: None, as_of=AS_OF)
    assert result["closed"] == [day] and result["calls"] == 0
    assert result["remaining"] == 0
    assert CKP.load_done(tmp_path) == {day}


def test_unknown_calendar_fails_before_call_or_write(tmp_path, monkeypatch):
    def unknown(*a):
        raise ValueError("calendar unavailable")
    monkeypatch.setattr(CKP.RC, "sessions", unknown)
    asked = []
    with pytest.raises(ValueError, match="calendar unavailable"):
        _answer(tmp_path, monkeypatch, ["2026-10-15"], _payload(), asked=asked)
    assert not asked and not list(tmp_path.iterdir())


def test_future_session_is_not_called_or_completed(tmp_path, monkeypatch):
    result, asked = _answer(tmp_path, monkeypatch, ["2026-10-20"], _payload("2026-10-20"))
    assert asked == [] and result["remaining"] == 1
    assert result["provisional"] == ["2026-10-20"]
    assert CKP.load_done(tmp_path) == set()


@pytest.mark.parametrize("mutation", ["missing_date", "invalid_date", "mixed_dates", "conflicting_alias", "duplicate", "invalid_close", "not_a_row", "nan_close", "zero_close", "nan_volume", "inf_open", "neginf_high", "inf_shares", "negative_volume", "negative_low"])
def test_invalid_or_mixed_daily_response_never_advances_done(tmp_path, monkeypatch, mutation):
    from copy import deepcopy
    payload = _payload()
    row = payload["OutBlock_1"][0]
    if mutation == "missing_date": row.pop("BAS_DD")
    elif mutation == "invalid_date": row["BAS_DD"] = "20261399"
    elif mutation == "mixed_dates":
        other = deepcopy(row); other.update(ISU_CD="000001", BAS_DD="20261014")
        payload["OutBlock_1"].append(other)
    elif mutation == "conflicting_alias": row["TRD_DD"] = "20261014"
    elif mutation == "duplicate": payload["OutBlock_1"].append(deepcopy(row))
    elif mutation == "invalid_close": row["TDD_CLSPRC"] = "-"
    elif mutation == "nan_close": row["TDD_CLSPRC"] = "NaN"
    elif mutation == "zero_close": row["TDD_CLSPRC"] = "0"
    elif mutation == "nan_volume": row["ACC_TRDVOL"] = "NaN"
    elif mutation == "inf_open": row["TDD_OPNPRC"] = "Infinity"
    elif mutation == "neginf_high": row["TDD_HGPRC"] = "-Infinity"
    elif mutation == "inf_shares": row["LIST_SHRS"] = "inf"
    elif mutation == "negative_volume": row["ACC_TRDVOL"] = "-5"
    elif mutation == "negative_low": row["TDD_LWPRC"] = "-1"
    elif mutation == "not_a_row": payload["OutBlock_1"].append(None)
    result, _ = _answer(tmp_path, monkeypatch, ["2026-10-15"], payload)
    assert result["stopped"]
    assert CKP.load_done(tmp_path) == set()
    assert not list(tmp_path.glob("*.jsonl.gz"))


def test_supported_date_alias_is_checked_not_guessed(tmp_path, monkeypatch):
    payload = _payload()
    row = payload["OutBlock_1"][0]
    row["TRD_DD"] = row.pop("BAS_DD")
    result, asked = _answer(tmp_path, monkeypatch, ["2026-10-15"], payload)
    assert asked == ["20261015"] and result["sessions"] == ["2026-10-15"]
    assert CKP.load_done(tmp_path) == {"2026-10-15"}


def test_empty_open_session_retries_then_commits_once(tmp_path, monkeypatch):
    for _ in range(3):
        result, asked = _answer(tmp_path, monkeypatch, ["2026-10-15"], {"OutBlock_1": []})
        assert asked == ["20261015"] and result["remaining"] == 1
        assert CKP.load_done(tmp_path) == set()
    result, _ = _answer(tmp_path, monkeypatch, ["2026-10-15"], _payload())
    assert result["remaining"] == 0
    before = {p.name:p.read_bytes() for p in tmp_path.iterdir()}
    result, asked = _answer(tmp_path, monkeypatch, ["2026-10-15"], {"OutBlock_1": []})
    assert asked == [] and result["written"] == []
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()} == before


def test_empty_session_does_not_block_an_independent_session(tmp_path, monkeypatch):
    def fake(base, endpoint, params, key):
        return {"OutBlock_1": []} if params["basDd"] == "20261014" else _payload()
    monkeypatch.setattr(CKP, "call", fake)
    result = CKP.collect(tmp_path, ["2026-10-14", "2026-10-15"], auth_key="synthetic", base="unused",
                         keep=None, max_calls=2, max_minutes=1, pace=0, as_of=AS_OF, log=lambda *_: None)
    assert result["calls"] == 2 and result["remaining"] == 1
    assert CKP.load_done(tmp_path) == {"2026-10-15"}


def test_duplicate_targets_consume_only_one_call(tmp_path, monkeypatch):
    result, asked = _answer(tmp_path, monkeypatch, ["2026-10-15"]*3, _payload())
    assert asked == ["20261015"] and result["remaining"] == 0
    assert result["bars"] == 1


def test_no_retained_rows_cannot_create_a_completion_marker(tmp_path, monkeypatch):
    result, _ = _answer(tmp_path, monkeypatch, ["2026-10-15"], _payload(), keep={"000001.KS"})
    assert result["remaining"] == 1 and result["provisional"] == ["2026-10-15"]
    assert CKP.load_done(tmp_path) == set()


@pytest.mark.parametrize("raw", ["{bad", "{}", '["2026-10-15", "2026-10-15"]', '[123]', '["invalid"]'])
def test_invalid_legacy_checkpoint_is_preserved_and_blocks_calls(tmp_path, monkeypatch, raw):
    path = tmp_path / CKP.DONE_NAME
    path.write_text(raw)
    asked = []
    with pytest.raises(ValueError):
        _answer(tmp_path, monkeypatch, ["2026-10-15"], _payload(), asked=asked)
    assert not asked and path.read_text() == raw
    assert sorted(p.name for p in tmp_path.iterdir()) == [CKP.DONE_NAME]


def test_legacy_done_without_session_rows_is_not_silently_trusted_or_repaired(tmp_path, monkeypatch):
    path = tmp_path / CKP.DONE_NAME
    path.write_text('["2026-10-15"]\n')
    before = path.read_bytes()
    asked = []
    with pytest.raises(ValueError, match="DONE_WITHOUT_SESSION_ROWS"):
        _answer(tmp_path, monkeypatch, ["2026-10-15"], _payload(), asked=asked)
    assert not asked and path.read_bytes() == before
    assert not list(tmp_path.glob("*.jsonl.gz"))


def test_staged_shard_failure_keeps_prior_bytes_and_checkpoint(tmp_path, monkeypatch):
    _answer(tmp_path, monkeypatch, ["2026-10-14"], _payload("2026-10-14"))
    before = {p.name:p.read_bytes() for p in tmp_path.iterdir()}
    def broken(path, rows):
        path.write_bytes(b"partial synthetic write")
        raise OSError("injected write failure")
    monkeypatch.setattr(CKP.HS, "write_shard", broken)
    with pytest.raises(OSError, match="injected"):
        _answer(tmp_path, monkeypatch, ["2026-10-15"], _payload())
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()} == before


def test_checkpoint_replace_failure_preserves_old_done_and_allows_safe_retry(tmp_path, monkeypatch):
    _answer(tmp_path, monkeypatch, ["2026-10-14"], _payload("2026-10-14"))
    path = tmp_path / CKP.DONE_NAME
    before = path.read_bytes()
    original = Path.replace
    def broken(self, target):
        if Path(target).name == CKP.DONE_NAME:
            raise OSError("injected checkpoint failure")
        return original(self, target)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", broken)
        with pytest.raises(OSError, match="checkpoint"):
            _answer(tmp_path, patch, ["2026-10-15"], _payload())
    assert path.read_bytes() == before
    result, asked = _answer(tmp_path, monkeypatch, ["2026-10-15"], _payload())
    assert asked == ["20261015"] and result["remaining"] == 0
    rows = CKP.HS.read_jsonl(tmp_path / "krx-prices-2026.jsonl.gz")
    assert len(rows) == len({r["id"] for r in rows}) == 2


def test_all_empty_cli_is_not_success(tmp_path, monkeypatch):
    monkeypatch.setenv("KRX_API_KEY", "synthetic")
    monkeypatch.setattr(CKP, "call", lambda *a, **k: {"OutBlock_1": []})
    assert CKP.main([str(tmp_path), "--all-issues", "--start", "2026-10-15", "--end", "2026-10-15", "--pace", "0"]) == 1
    assert CKP.load_done(tmp_path) == set()


@pytest.mark.parametrize("budget", ["calls", "minutes"])
def test_exhausted_budget_leaves_session_pending_without_call(tmp_path, monkeypatch, budget):
    kw = {"max_calls": 0} if budget == "calls" else {"max_minutes": 0}
    result, asked = _answer(tmp_path, monkeypatch, ["2026-10-15"], _payload(), **kw)
    assert not asked and result["stopped"] and result["remaining"] == 1
    assert CKP.load_done(tmp_path) == set()


def test_pacing_cannot_launch_another_call_after_time_budget(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(CKP.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(CKP.time, "sleep", lambda _: clock.__setitem__(0, 120.0))
    asked = []
    def fake(base, endpoint, params, key):
        asked.append(params["basDd"])
        return _payload("2026-10-14")
    monkeypatch.setattr(CKP, "call", fake)
    result = CKP.collect(tmp_path, ["2026-10-14", "2026-10-15"], auth_key="synthetic", base="unused",
                         keep=None, max_calls=2, max_minutes=1, pace=120, as_of=AS_OF, log=lambda *_: None)
    assert asked == ["20261014"] and result["remaining"] == 1
    assert CKP.load_done(tmp_path) == {"2026-10-14"}


def test_refusal_counts_attempt_and_preserves_retry(tmp_path, monkeypatch):
    def refused(*a, **kw):
        raise CKP.Refused("synthetic denial")
    monkeypatch.setattr(CKP, "call", refused)
    result = CKP.collect(tmp_path, ["2026-10-15"], auth_key="synthetic", base="unused",
                         keep=None, max_calls=1, max_minutes=1, pace=0, as_of=AS_OF, log=lambda *_: None)
    assert result["calls"] == 1 and result["remaining"] == 1 and result["stopped"]
    assert CKP.load_done(tmp_path) == set()
    result, asked = _answer(tmp_path, monkeypatch, ["2026-10-15"], _payload())
    assert asked == ["20261015"] and result["remaining"] == 0


@pytest.mark.parametrize("hole", ["signal", "recent_window"])
def test_raw_bar_gap_withholds_kr_a0_shared_eligibility_inputs(hole):
    """#262 calls these unchanged bars/H2 guards; no A0 study/data is run."""
    import pandas as pd
    from pipeline import kr_alpha_atlas_bars as B
    from pipeline import kr_alpha_signal_v2 as H2
    calendar = CKP.RC.sessions("2025-01-01", "2026-10-15", "KR")[-150:]
    rows = [{"date": str(d.date()), "ticker": "005930.KS", "open": 1000., "high": 1000.,
             "low": 1000., "close": 1000., "volume": 2_000_000., "listedShares": 1_000_000.}
            for d in calendar]
    removed = len(rows)-1 if hole == "signal" else len(rows)-5
    day = str(calendar[-1].date())
    def inputs(raw):
        bars = B.TickerBars("005930.KS", CKP.KP.frame_from_rows(raw, traded_only=False), calendar)
        quote = bars.quote(day)
        values, reasons = bars.features_at(day)
        guard = values.get("E04_tradabilityGuard20")
        row = {"isPreferredShare": False, "industry": "SYNTHETIC_INDUSTRY",
               "priceAsOf": day if quote else None,
               "positiveVolumeSessions20": int(guard) if guard is not None else None,
               "medianTradedValue60Krw": values.get("E03_capacityMedianTradedValue60")}
        return row, reasons, H2._ineligibility(row, pd.Timestamp(day))
    complete, _, complete_reasons = inputs(rows)
    assert complete_reasons == [] and complete["medianTradedValue60Krw"] == 2_000_000_000.
    missing, missing_reasons, eligibility = inputs([r for i,r in enumerate(rows) if i != removed])
    assert "NOT_TRADED_EVERY_SESSION_20" in eligibility
    assert missing["medianTradedValue60Krw"] is None
    if hole == "signal":
        assert "PRICE_NOT_ON_SIGNAL_DATE" in eligibility
        assert missing_reasons["E03_capacityMedianTradedValue60"] == "NO_QUOTE_AT_SIGNAL"
    else:
        assert missing["priceAsOf"] == day and missing["positiveVolumeSessions20"] == 19
        assert missing_reasons["E03_capacityMedianTradedValue60"] == "GAP_OR_SUSPENSION_IN_WINDOW"


def test_cli_and_collector_default_to_the_same_kr_date(tmp_path, monkeypatch):
    monkeypatch.setattr(CKP, "today_kr", lambda: AS_OF)
    monkeypatch.setenv("KRX_API_KEY", "synthetic")
    asked = []
    def fake(base, endpoint, params, key):
        asked.append(params["basDd"])
        return {"OutBlock_1": []}
    monkeypatch.setattr(CKP, "call", fake)
    assert CKP.main([str(tmp_path), "--all-issues", "--start", "2026-10-19", "--pace", "0"]) == 1
    assert asked == ["20261019"]
    assert CKP.load_done(tmp_path) == set()


def test_absent_secondary_field_stays_none_not_zero_and_day_completes(tmp_path, monkeypatch):
    payload = _payload()
    payload["OutBlock_1"][0]["ACC_TRDVOL"] = "-"
    bars, error = CKP.daily_bars(payload, "2026-10-15")
    assert error is None and bars[0]["volume"] is None
    result, _ = _answer(tmp_path, monkeypatch, ["2026-10-15"], payload)
    assert CKP.load_done(tmp_path) == {"2026-10-15"}


# --------------------------------------------------------------------------- #
# Numeric domain of every stored field (audit comment 6318346502, Finding A)
# --------------------------------------------------------------------------- #
FIELD_KEYS = {"open": "TDD_OPNPRC", "high": "TDD_HGPRC", "low": "TDD_LWPRC",
              "volume": "ACC_TRDVOL", "listedShares": "LIST_SHRS"}


@pytest.mark.parametrize("field,raw", [
    (f, v) for f in FIELD_KEYS for v in ("NaN", "nan", "Infinity", "-Infinity", "1e400")
] + [("volume", "-5"), ("volume", "1.5"), ("listedShares", "0"), ("listedShares", "-1"),
     ("listedShares", "10.5"), ("open", "-1"), ("high", "-1"), ("low", "-1"),
     ("open", "0"), ("high", "900"), ("low", "1100"), ("open", "1200")])
def test_invalid_secondary_field_never_stores_or_advances_done(tmp_path, monkeypatch, field, raw):
    payload = _payload()
    payload["OutBlock_1"][0][FIELD_KEYS[field]] = raw
    result, _ = _answer(tmp_path, monkeypatch, ["2026-10-15"], payload)
    assert result["stopped"] and "INVALID_DAILY_VALUE" in result["stopped"]
    assert CKP.load_done(tmp_path) == set()
    assert not list(tmp_path.glob("*.jsonl.gz"))


def test_a_bad_issue_outside_keep_still_refuses_the_whole_response(tmp_path, monkeypatch):
    from copy import deepcopy
    payload = _payload()
    other = deepcopy(payload["OutBlock_1"][0])
    other.update(ISU_CD="000001", ACC_TRDVOL="NaN")
    payload["OutBlock_1"].append(other)
    result, _ = _answer(tmp_path, monkeypatch, ["2026-10-15"], payload, keep={"005930.KS"})
    assert result["stopped"] and CKP.load_done(tmp_path) == set()
    assert not list(tmp_path.glob("*.jsonl.gz"))


def test_suspended_issue_with_zero_volume_and_zero_range_is_stored(tmp_path, monkeypatch):
    payload = _payload()
    payload["OutBlock_1"][0].update(ACC_TRDVOL="0", TDD_OPNPRC="0", TDD_HGPRC="0", TDD_LWPRC="0")
    result, _ = _answer(tmp_path, monkeypatch, ["2026-10-15"], payload)
    assert result["stopped"] is None and CKP.load_done(tmp_path) == {"2026-10-15"}
    row, = CKP.HS.read_jsonl(tmp_path / "krx-prices-2026.jsonl.gz")
    assert (row["volume"], row["open"], row["close"]) == (0.0, 0.0, 1000.0)


@pytest.mark.parametrize("key", ["TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC", "ACC_TRDVOL", "LIST_SHRS"])
def test_unstated_field_is_kept_as_none_never_zero(tmp_path, monkeypatch, key):
    payload = _payload()
    payload["OutBlock_1"][0][key] = "-"
    result, _ = _answer(tmp_path, monkeypatch, ["2026-10-15"], payload)
    assert result["stopped"] is None and CKP.load_done(tmp_path) == {"2026-10-15"}
    row, = CKP.HS.read_jsonl(tmp_path / "krx-prices-2026.jsonl.gz")
    field = {v: k for k, v in FIELD_KEYS.items()}[key]
    assert row[field] is None


def test_zero_price_with_unstated_volume_is_not_assumed_suspended(tmp_path, monkeypatch):
    payload = _payload()
    payload["OutBlock_1"][0].update(ACC_TRDVOL="-", TDD_OPNPRC="0")
    result, _ = _answer(tmp_path, monkeypatch, ["2026-10-15"], payload)
    assert "ZERO_PRICE_ON_ROW_NOT_KNOWN_SUSPENDED:open" in result["stopped"]
    assert CKP.load_done(tmp_path) == set()


def test_stored_shard_is_standard_json(tmp_path, monkeypatch):
    import gzip
    import json
    _answer(tmp_path, monkeypatch, ["2026-10-15"], _payload())
    for line in gzip.open(tmp_path / "krx-prices-2026.jsonl.gz").read().decode().splitlines():
        json.loads(line, parse_constant=lambda c: pytest.fail(f"nonstandard token {c}"))


def test_storage_guard_refuses_nonfinite_rows_before_any_write(tmp_path, monkeypatch):
    # Defence in depth: even if a bar slipped past validation, nothing is staged.
    monkeypatch.setattr(CKP, "bar_value_errors", lambda bar: [])
    payload = _payload()
    payload["OutBlock_1"][0]["ACC_TRDVOL"] = "NaN"
    with pytest.raises(ValueError, match="NONFINITE_NUMERIC_IN_FRESH_ROW"):
        _answer(tmp_path, monkeypatch, ["2026-10-15"], payload)
    assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------- #
# Cross-section completeness (Finding B): reported, never assumed, never gated on a count
# --------------------------------------------------------------------------- #
def _universe(tmp_path, snapshots):
    rows = [{"id": f"krx-universe:{d}:{t}", "date": d, "region": "KR", "ticker": t, "rank": i + 1}
            for d, tickers in snapshots.items() for i, t in enumerate(sorted(tickers))]
    path = tmp_path / "universe"
    path.mkdir()
    CKP.HS.write_shard(path / "krx-universe-2026.jsonl.gz", rows)
    return path


def test_partial_response_completes_the_date_but_is_reported_unresolved(tmp_path, monkeypatch):
    store = tmp_path / "store"
    store.mkdir()
    universe = _universe(tmp_path, {"2026-10-01": {"005930.KS", "000660.KS"},
                                    "2026-11-02": {"005930.KS", "000660.KS"}})
    snapshots = CKP.membership_snapshots(universe)
    result, _ = _answer(store, monkeypatch, ["2026-10-15"], _payload(), snapshots=snapshots)
    assert CKP.load_done(store) == {"2026-10-15"}
    receipt, = result["completeness"]
    assert receipt["status"] == "UNRESOLVED_PIT_MEMBERS_ABSENT"
    assert receipt["missingListedBeforeAndAfter"] == ["000660.KS"]
    assert result["completenessUnresolved"] == ["2026-10-15"]
    report = CKP.diagnose(store, universe)
    assert report["status"] == "UNRESOLVED"
    assert report["receiptsByStatus"] == {"UNRESOLVED_PIT_MEMBERS_ABSENT": 1}


def test_full_cross_section_is_complete_only_against_the_prior_snapshot(tmp_path, monkeypatch):
    from copy import deepcopy
    store = tmp_path / "store"
    store.mkdir()
    universe = _universe(tmp_path, {"2026-10-01": {"005930.KS", "000660.KS"}})
    payload = _payload()
    other = deepcopy(payload["OutBlock_1"][0])
    other["ISU_CD"] = "000660"
    payload["OutBlock_1"].append(other)
    result, _ = _answer(store, monkeypatch, ["2026-10-15"], payload,
                        snapshots=CKP.membership_snapshots(universe))
    assert result["completeness"][0]["status"] == "COMPLETE_AGAINST_PRIOR_PIT_SNAPSHOT"
    report = CKP.diagnose(store, universe)
    assert report["status"] == "COMPLETE_AGAINST_PRIOR_PIT_SNAPSHOT"
    assert report["membershipKeepSha256"] == CKP.keep_digest({"005930.KS", "000660.KS"})


def test_missing_member_without_a_later_snapshot_is_exit_unknown(tmp_path):
    receipts = CKP.completeness_receipts({"2026-10-15": {"005930.KS"}}, ["2026-10-15"],
                                         {"2026-10-01": {"005930.KS", "000660.KS"}})
    assert receipts[0]["missingExitUnknown"] == ["000660.KS"]
    assert receipts[0]["missingListedBeforeAndAfter"] == []
    assert receipts[0]["status"] == "UNRESOLVED_PIT_MEMBERS_ABSENT"


def test_no_prior_snapshot_or_no_universe_is_unresolved(tmp_path, monkeypatch):
    receipts = CKP.completeness_receipts({"2026-10-15": {"005930.KS"}}, ["2026-10-15"],
                                         {"2026-11-02": {"005930.KS"}})
    assert receipts[0]["status"] == "UNRESOLVED_NO_PRIOR_PIT_SNAPSHOT"
    result, _ = _answer(tmp_path, monkeypatch, ["2026-10-15"], _payload())
    assert result["completeness"][0]["status"] == "UNRESOLVED_NO_PRIOR_PIT_SNAPSHOT"
    assert CKP.diagnose(tmp_path, None)["status"] == "UNRESOLVED"


def test_diagnosis_is_read_only_and_reports_legacy_anomalies(tmp_path, monkeypatch):
    def forbidden(*a, **k):
        pytest.fail("diagnosis must not call KRX")
    monkeypatch.setattr(CKP, "call", forbidden)
    rows = [{"id": "krx-price:2026-10-14:005930", "date": "2026-10-14", "region": "KR",
             "ticker": "005930.KS", "close": 1000.0, "volume": float("nan")},
            {"id": "krx-price:undated", "date": None, "region": "KR", "ticker": "005930.KS"}]
    CKP.HS.write_shard(tmp_path / "krx-prices-2026.jsonl.gz", rows)
    (tmp_path / CKP.DONE_NAME).write_text('["2026-10-15"]\n')
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    report = CKP.diagnose(tmp_path, None)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    assert report["status"] == "UNRESOLVED"
    assert report["anomalies"]["doneOpenSessionWithoutRows"] == ["2026-10-15"]
    assert report["anomalies"]["rowsWithoutDone"] == ["2026-10-14"]
    assert report["anomalies"]["storedNonfiniteValuesByField"] == {"volume": 1}
    assert report["anomalies"]["rowsWithoutValidDate"] == 1


def test_diagnose_cli_needs_no_key_and_writes_nothing(tmp_path, monkeypatch, capsys):
    import json
    monkeypatch.delenv("KRX_API_KEY", raising=False)
    assert CKP.main([str(tmp_path), "--diagnose"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "UNRESOLVED"
    assert list(tmp_path.iterdir()) == []
