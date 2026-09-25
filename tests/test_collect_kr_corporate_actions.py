"""`scripts/collect_kr_corporate_actions.py` against fake `call_fn`/
`directory_fn` — no network. Confirms the fail-closed and resumability
contracts `pipeline.collector_outcomes` requires of every collector in this
repository.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "collect_kr_corporate_actions", ROOT / "scripts/collect_kr_corporate_actions.py")
COLLECT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(COLLECT)

from pipeline import collector_outcomes as CO  # noqa: E402


def _inventory(tmp_path, codes):
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({"securities": [{"code": c} for c in codes]}))
    return path


def _directory():
    return [{"corpCode": "00123", "corpName": "우리은행", "stockCode": "000030",
            "modifyDate": None}]


def _list_payload(rows):
    return {"status": "000", "list": rows}


def _row(rcept_no, report_nm="합병결정"):
    return {"rcept_no": rcept_no, "rcept_dt": rcept_no[:8],
           "corp_code": "00123", "corp_name": "우리은행", "report_nm": report_nm}


# --------------------------------------------------------------------------- #
# Happy path: served, writes a shard, exits 0
# --------------------------------------------------------------------------- #
def test_a_served_run_writes_a_shard_and_completes(tmp_path):
    inventory = _inventory(tmp_path, ["000030.KS"])
    store = tmp_path / "store"

    def call_fn(path, params):
        assert path == "list.json"
        return _list_payload([_row("20190201000123")])

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         max_calls=10, max_minutes=10,
                         call_fn=call_fn, directory_fn=lambda key: _directory())
    assert report["outcome"] == "SERVED"
    assert report["written"] == 1
    assert (store / "kr-corporate-actions-disclosures.jsonl.gz").exists()
    assert not CO.is_reportable_failure(report["outcome"], written=report["written"])


def test_a_ticker_with_no_dart_identity_is_recorded_not_silently_skipped(tmp_path):
    inventory = _inventory(tmp_path, ["999999.KS"])  # not in the fake directory
    store = tmp_path / "store"

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         max_calls=10, max_minutes=10,
                         call_fn=lambda path, params: _list_payload([]),
                         directory_fn=lambda key: _directory())
    assert report["tickersWithNoDartIdentity"] == 1
    assert report["written"] == 0


# --------------------------------------------------------------------------- #
# Fail-closed: a refusal with zero progress is a reportable failure
# --------------------------------------------------------------------------- #
def test_a_refused_corp_code_directory_fails_closed(tmp_path):
    inventory = _inventory(tmp_path, ["000030.KS"])
    store = tmp_path / "store"

    def directory_fn(key):
        raise COLLECT.Refused("HTTP 401")

    with pytest.raises(COLLECT.Refused):
        COLLECT.run(store, key="fakekey", inventory_path=inventory,
                   max_calls=10, max_minutes=10,
                   call_fn=lambda p, params: _list_payload([]), directory_fn=directory_fn)


def test_a_refused_list_json_call_stops_with_zero_new_rows_reported_as_failure(tmp_path):
    inventory = _inventory(tmp_path, ["000030.KS"])
    store = tmp_path / "store"

    def call_fn(path, params):
        raise COLLECT.Refused("HTTP 400: b'LOGOUT'")

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         max_calls=10, max_minutes=10,
                         call_fn=call_fn, directory_fn=lambda key: _directory())
    assert report["stopReason"].startswith("REFUSED:")
    assert report["written"] == 0
    assert CO.is_reportable_failure(report["outcome"], written=report["written"]), \
        "a source refusal with zero progress must never read as success"


def test_rows_written_before_a_later_refusal_are_kept_and_not_a_reportable_failure(tmp_path):
    inventory = _inventory(tmp_path, ["000030.KS", "000060.KS"])
    store = tmp_path / "store"
    calls = {"n": 0}

    def call_fn(path, params):
        calls["n"] += 1
        if calls["n"] == 1:
            return _list_payload([_row("20190201000123")])
        raise COLLECT.Refused("HTTP 500")

    directory = _directory() + [{"corpCode": "00124", "corpName": "메리츠화재",
                                 "stockCode": "000060", "modifyDate": None}]
    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         max_calls=10, max_minutes=10,
                         call_fn=call_fn, directory_fn=lambda key: directory)
    assert report["written"] == 1
    assert not CO.is_reportable_failure(report["outcome"], written=report["written"])


# --------------------------------------------------------------------------- #
# Resumability: a ticker already SUCCESS is never re-queried
# --------------------------------------------------------------------------- #
def test_a_previously_succeeded_ticker_is_not_re_queried(tmp_path):
    inventory = _inventory(tmp_path, ["000030.KS"])
    store = tmp_path / "store"
    store.mkdir(parents=True)
    COLLECT.save_state(store, {
        "contract": COLLECT.STATE_CONTRACT, "rawContract": COLLECT.RAW_CONTRACT,
        "tickers": {"000030.KS": {"status": "SUCCESS", "corpCode": "00123"}}})

    calls = {"n": 0}

    def call_fn(path, params):
        calls["n"] += 1
        return _list_payload([_row("20190201000123")])

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         max_calls=10, max_minutes=10,
                         call_fn=call_fn, directory_fn=lambda key: _directory())
    assert calls["n"] == 0
    assert report["calls"] == 0


# --------------------------------------------------------------------------- #
# Never collects from the unconfirmed alotMatter endpoint
# --------------------------------------------------------------------------- #
def test_the_collector_never_calls_alotmatter():
    import inspect
    source = inspect.getsource(COLLECT)
    assert '"alotMatter' not in source and "'alotMatter" not in source, \
        "candidate endpoint stays out of the permanent-ledger collector until confirmed " \
        "(the module docstring may still explain why, in prose)"
