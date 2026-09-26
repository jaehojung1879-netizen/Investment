"""`scripts/collect_kr_dividend_sections.py` against fake `call_fn`/
`directory_fn` -- no network. Same fail-closed / resumability discipline as
`test_collect_kr_corporate_actions.py`.
"""
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "collect_kr_dividend_sections", ROOT / "scripts/collect_kr_dividend_sections.py")
COLLECT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(COLLECT)

from pipeline import collector_outcomes as CO  # noqa: E402


def _inventory(tmp_path, codes, names=None):
    names = names or {}
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(
        {"securities": [{"code": c, "krxName": names.get(c)} for c in codes]}))
    return path


def _directory():
    return [{"corpCode": "00123", "corpName": "우리은행", "stockCode": "000030",
            "modifyDate": None}]


def _write_universe_shard(tmp_path, rows):
    universe_root = tmp_path / "universe" / "kr"
    universe_root.mkdir(parents=True, exist_ok=True)
    path = universe_root / "krx-universe-2020.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return universe_root


def _alotmatter_payload(rows, status="000"):
    if status == "013":
        return {"status": "013", "message": "조회된 데이타가 없습니다."}
    return {"status": status, "list": rows}


def _dividend_row(rcept_no, se="주당현금배당금(원)", thstrm="500", corp_code="00123"):
    return {"rcept_no": rcept_no, "corp_code": corp_code, "corp_name": "우리은행",
           "se": se, "thstrm": thstrm, "frmtrm": None, "lwfr": None, "stock_knd": "보통주"}


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
def test_a_served_run_writes_a_shard_and_completes(tmp_path):
    inventory = _inventory(tmp_path, ["000030.KS"])
    store = tmp_path / "store"

    def call_fn(path, params):
        assert path == "alotMatter.json"
        year = params["bsns_year"]
        if year != "2013":
            return _alotmatter_payload([], status="013")
        return _alotmatter_payload([_dividend_row("20130201000123")])

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         universe_root=tmp_path / "no-universe-here",
                         max_calls=1000, max_minutes=10,
                         call_fn=call_fn, directory_fn=lambda key: _directory())
    assert report["outcome"] == "SERVED"
    assert report["written"] == 1
    assert report["tickersSucceeded"] == 1
    assert report["datasetComplete"] is True
    assert (store / "kr-dividend-sections.jsonl.gz").exists()
    assert not CO.is_reportable_failure(report["outcome"], written=report["written"])


def test_a_ticker_with_no_dart_identity_is_recorded_not_silently_skipped(tmp_path):
    inventory = _inventory(tmp_path, ["999999.KS"])
    store = tmp_path / "store"

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         universe_root=tmp_path / "no-universe-here",
                         max_calls=1000, max_minutes=10,
                         call_fn=lambda path, params: _alotmatter_payload([], status="013"),
                         directory_fn=lambda key: _directory())
    assert report["tickersWithNoDartIdentity"] == 1
    assert report["written"] == 0


def test_status_013_marks_the_year_done_without_manufacturing_a_row(tmp_path):
    inventory = _inventory(tmp_path, ["000030.KS"])
    store = tmp_path / "store"

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         universe_root=tmp_path / "no-universe-here",
                         max_calls=1000, max_minutes=10,
                         call_fn=lambda path, params: _alotmatter_payload([], status="013"),
                         directory_fn=lambda key: _directory())
    assert report["written"] == 0
    assert report["tickersSucceeded"] == 1
    assert report["datasetComplete"] is True


# --------------------------------------------------------------------------- #
# Fail-closed
# --------------------------------------------------------------------------- #
def test_a_refused_corp_code_directory_fails_closed(tmp_path):
    import pytest

    inventory = _inventory(tmp_path, ["000030.KS"])
    store = tmp_path / "store"

    def directory_fn(key):
        raise COLLECT.Refused("HTTP 401")

    with pytest.raises(COLLECT.Refused):
        COLLECT.run(store, key="fakekey", inventory_path=inventory,
                   universe_root=tmp_path / "no-universe-here",
                   max_calls=10, max_minutes=10,
                   call_fn=lambda p, params: _alotmatter_payload([], status="013"),
                   directory_fn=directory_fn)


# --------------------------------------------------------------------------- #
# Call budget: a HARD ceiling, checked before every ticker-year call
# --------------------------------------------------------------------------- #
def test_call_budget_exhausted_mid_ticker_leaves_it_partial_not_success(tmp_path):
    inventory = _inventory(tmp_path, ["000030.KS"])
    store = tmp_path / "store"
    calls_made = {"n": 0}

    def call_fn(path, params):
        calls_made["n"] += 1
        return _alotmatter_payload([], status="013")

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         universe_root=tmp_path / "no-universe-here",
                         max_calls=3, max_minutes=10,
                         call_fn=call_fn, directory_fn=lambda key: _directory())
    assert calls_made["n"] == 3
    assert report["calls"] == 3
    assert report["stopReason"] == "CALL_BUDGET_SPENT"
    assert report["tickersPartial"] == 1
    assert report["tickersSucceeded"] == 0
    assert report["datasetComplete"] is False


def test_no_call_ever_occurs_beyond_max_calls(tmp_path):
    inventory = _inventory(tmp_path, ["000030.KS"])
    store = tmp_path / "store"
    calls_made = {"n": 0}

    def call_fn(path, params):
        calls_made["n"] += 1
        if calls_made["n"] > 5:
            raise AssertionError("call budget was exceeded")
        return _alotmatter_payload([], status="013")

    COLLECT.run(store, key="fakekey", inventory_path=inventory,
               universe_root=tmp_path / "no-universe-here",
               max_calls=5, max_minutes=10,
               call_fn=call_fn, directory_fn=lambda key: _directory())
    assert calls_made["n"] == 5


def test_the_partial_ticker_resumes_from_the_first_uncollected_year_next_run(tmp_path):
    inventory = _inventory(tmp_path, ["000030.KS"])
    store = tmp_path / "store"
    seen_years = []

    def call_fn(path, params):
        seen_years.append(params["bsns_year"])
        return _alotmatter_payload([], status="013")

    first = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                        universe_root=tmp_path / "no-universe-here",
                        max_calls=3, max_minutes=10,
                        call_fn=call_fn, directory_fn=lambda key: _directory())
    assert first["tickersPartial"] == 1
    first_years = list(seen_years)
    seen_years.clear()

    second = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         universe_root=tmp_path / "no-universe-here",
                         max_calls=1000, max_minutes=10,
                         call_fn=call_fn, directory_fn=lambda key: _directory())
    assert second["tickersSucceeded"] == 1
    # Years already collected the first run are never re-queried.
    assert not set(first_years) & set(seen_years)


def test_previously_completed_tickers_are_preserved_when_a_later_one_runs_out(tmp_path):
    inventory = _inventory(tmp_path, ["000030.KS", "000031.KS"])
    store = tmp_path / "store"

    def directory_fn(key):
        return [{"corpCode": "00123", "corpName": "우리은행", "stockCode": "000030"},
               {"corpCode": "00124", "corpName": "다른회사", "stockCode": "000031"}]

    # First run: budget only covers the first ticker's full year range.
    years = len(COLLECT.years_in_range())
    report1 = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                          universe_root=tmp_path / "no-universe-here",
                          max_calls=years, max_minutes=10,
                          call_fn=lambda p, params: _alotmatter_payload([], status="013"),
                          directory_fn=directory_fn)
    assert report1["tickersSucceeded"] == 1

    report2 = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                          universe_root=tmp_path / "no-universe-here",
                          max_calls=years, max_minutes=10,
                          call_fn=lambda p, params: _alotmatter_payload([], status="013"),
                          directory_fn=directory_fn)
    assert report2["tickersSucceeded"] == 2
    assert report2["datasetComplete"] is True


# --------------------------------------------------------------------------- #
# The continuing-name cross-validation sample is real, not hand-picked
# --------------------------------------------------------------------------- #
def test_continuing_sample_is_drawn_from_the_real_universe_shard(tmp_path):
    inventory = _inventory(tmp_path, ["000030.KS"], names={"000030.KS": "우리은행"})
    universe_root = _write_universe_shard(tmp_path, [
        {"date": "2020-01-01", "ticker": "005930.KS", "rank": 1, "name": "삼성전자"},
        {"date": "2020-01-01", "ticker": "000030.KS", "rank": 2, "name": "우리은행"},
    ])

    def directory_fn(key):
        return [{"corpCode": "00123", "corpName": "우리은행", "stockCode": "000030"},
               {"corpCode": "00999", "corpName": "삼성전자", "stockCode": "005930"}]

    tickers = COLLECT.target_tickers(inventory, universe_root, sample_size=5)
    codes = [t[0] for t in tickers]
    assert "005930" in codes
    assert "000030" in codes  # the terminated security is still requested


def test_an_empty_universe_root_still_collects_the_terminated_securities(tmp_path):
    inventory = _inventory(tmp_path, ["000030.KS"])
    tickers = COLLECT.target_tickers(inventory, tmp_path / "does-not-exist", sample_size=5)
    assert tickers == [("000030", None)]
