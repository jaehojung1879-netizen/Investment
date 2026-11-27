"""Bounded retry fairness, persistence and no false negative evidence."""
import json
from types import SimpleNamespace

from scripts import collect_dart_fundamentals as collect

DF = collect.DF


def test_due_untried_precedes_retries_then_oldest_retry():
    pending = [("A.KS", 2026, "11014"), ("B.KS", 2026, "11014"),
               ("C.KS", 2025, "11011"), ("D.KS", 2026, "11011")]
    state = {DF.record_id("A.KS", 2026, "11014"): "2026-11-24T01:00:00.000000+00:00",
             DF.record_id("C.KS", 2025, "11011"): "2026-11-20T01:00:00.000000+00:00"}
    assert collect.prioritize_due(pending, "2026-11-25", state) == [
        pending[1], pending[2], pending[0], pending[3]]


def test_retry_state_rejects_corrupt_naive_and_future_timestamps(tmp_path):
    (tmp_path / collect.RETRY_FILE).write_text(json.dumps({
        "good": "2020-01-01T09:00:00+09:00", "naive": "2020-01-01",
        "broken": "garbage", "future": "9999-01-01T00:00:00+00:00",
        "not_string": {}}))
    assert collect.load_retry_state(tmp_path) == {"good": "2020-01-01T00:00:00.000000+00:00"}


def setup_collector(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(collect, "load_config", lambda: (SimpleNamespace(longterm={}), None))
    monkeypatch.setattr(collect.universe_mod, "resolve",
                        lambda _: ({"KR": ["000001.KS", "000002.KS"]}, None))
    monkeypatch.setattr(collect, "corp_code_map",
                        lambda _: {"000001": "00000001", "000002": "00000002"})
    monkeypatch.setattr(collect.time, "sleep", lambda _: None)


def run_one(store):
    assert collect.main([str(store), "--target", "statements",
                         "--from-year", "2020", "--to-year", "2020",
                         "--max-calls", "1"]) == 0


def test_short_repeated_runs_reach_every_due_filing(tmp_path, monkeypatch):
    setup_collector(monkeypatch)
    seen = []

    def call(path, params):
        seen.append((params["corp_code"], params["reprt_code"]))
        return {"status": "100"}, ""

    monkeypatch.setattr(collect, "call", call)
    for _ in range(8):
        run_one(tmp_path)
    assert len(seen) == len(set(seen)) == 8
    assert len(collect.load_retry_state(tmp_path)) == 8
    assert json.loads((tmp_path / "absent.json").read_text()) == {}


def test_stop_clears_legacy_absence_but_keeps_retry_clock(tmp_path, monkeypatch):
    setup_collector(monkeypatch)
    rid = DF.record_id("000001.KS", 2020, "11011")
    (tmp_path / "absent.json").write_text(json.dumps({
        rid: {"fiscalYear": 2020, "reportCode": "11011", "status": "013",
              "checkedAt": "2021-04-01T00:00:00Z"}}))
    monkeypatch.setattr(collect, "call", lambda *args: ({"status": "800"}, ""))
    run_one(tmp_path)
    assert json.loads((tmp_path / "absent.json").read_text()) == {}
    assert set(collect.load_retry_state(tmp_path)) == {rid}


def test_success_or_settled_negative_removes_retry_clock(tmp_path, monkeypatch):
    setup_collector(monkeypatch)
    rid = DF.record_id("000001.KS", 2020, "11011")
    monkeypatch.setattr(collect, "call", lambda *args: ({"status": "013"}, ""))
    run_one(tmp_path)
    assert rid in json.loads((tmp_path / "absent.json").read_text())
    assert collect.load_retry_state(tmp_path) == {}
