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


def _inventory(tmp_path, codes, names=None):
    names = names or {}
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(
        {"securities": [{"code": c, "krxName": names.get(c)} for c in codes]}))
    return path


def _directory():
    return [{"corpCode": "00123", "corpName": "우리은행", "stockCode": "000030",
            "modifyDate": None}]


def _list_payload(rows, *, page_no=1, page_count=100, total_count=None,
                  total_page=None, status="000"):
    if status == "013":
        return {"status": "013", "message": "조회된 데이타가 없습니다."}
    if total_count is None:
        total_count = len(rows)
    if total_page is None:
        total_page = -(-total_count // page_count) if total_count else 0
    return {"status": status, "list": rows, "page_no": page_no, "page_count": page_count,
           "total_count": total_count, "total_page": total_page}


def _row(rcept_no, report_nm="합병결정", corp_code="00123", corp_name="우리은행"):
    return {"rcept_no": rcept_no, "rcept_dt": rcept_no[:8],
           "corp_code": corp_code, "corp_name": corp_name, "report_nm": report_nm}


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
# Pagination: every page is walked, a ticker is SUCCESS only once complete
# --------------------------------------------------------------------------- #
def test_a_multi_page_issuer_is_walked_to_completion_and_deduplicated(tmp_path):
    """A >100-row issuer: two pages, a relevant filing appearing only on
    page 2, and no duplicate row in the merged shard."""
    inventory = _inventory(tmp_path, ["000030.KS"])
    store = tmp_path / "store"
    page1_rows = [_row(f"2019010{n}000001", report_nm="사업보고서") for n in range(1, 3)] \
        + [_row("20190201000123", report_nm="합병결정")]
    page2_rows = [_row("20190301000999", report_nm="공개매수신고서")]

    def call_fn(path, params):
        assert path == "list.json"
        page_no = int(params["page_no"])
        if page_no == 1:
            return _list_payload(page1_rows, page_no=1, total_count=101, total_page=2)
        if page_no == 2:
            return _list_payload(page2_rows, page_no=2, total_count=101, total_page=2)
        raise AssertionError(f"unexpected page {page_no}")

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         max_calls=10, max_minutes=10,
                         call_fn=call_fn, directory_fn=lambda key: _directory())
    assert report["outcome"] == "SERVED"
    # Only the merger (page 1) and tender (page 2) rows match a family
    # keyword; the 사업보고서 rows never match one. Both pages were reached.
    assert report["written"] == 2
    assert report["calls"] == 2


def test_a_page_that_never_appears_leaves_the_ticker_unresolved_not_success(tmp_path):
    """Pagination metadata says 2 pages exist; only page 1 is ever served
    (simulating a source that stops answering mid-walk). The ticker must
    never read SUCCESS."""
    inventory = _inventory(tmp_path, ["000030.KS"])
    store = tmp_path / "store"

    def call_fn(path, params):
        page_no = int(params["page_no"])
        if page_no == 1:
            return _list_payload([_row("20190201000123")], page_no=1,
                                 total_count=150, total_page=2)
        raise COLLECT.Refused("HTTP 500")

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         max_calls=10, max_minutes=10,
                         call_fn=call_fn, directory_fn=lambda key: _directory())
    # The HTTP-level Refused on page 2 propagates and stops the whole run
    # (systemic), and the ticker's state was never set to SUCCESS.
    assert report["stopReason"].startswith("REFUSED:")
    assert report["written"] == 0


def test_inconsistent_pagination_metadata_marks_the_ticker_not_success_and_continues(tmp_path):
    """A later page's totalCount disagrees with the first page's (the
    result set changed mid-walk) -- this must fail closed for that ticker
    without stopping the whole run."""
    inventory = _inventory(tmp_path, ["000030.KS", "000060.KS"], names={"000060.KS": "메리츠화재"})
    store = tmp_path / "store"

    def call_fn(path, params):
        corp = params["corp_code"]
        page_no = int(params["page_no"])
        if corp == "00123":
            if page_no == 1:
                return _list_payload([_row("20190201000123")], page_no=1,
                                     total_count=150, total_page=2)
            # Disagrees with page 1's totalCount -- the result set moved.
            return _list_payload([_row("20190301000999")], page_no=2,
                                 total_count=151, total_page=2)
        return _list_payload([_row("20230101000001", corp_code="00124",
                                   corp_name="메리츠화재")])

    directory = _directory() + [{"corpCode": "00124", "corpName": "메리츠화재",
                                 "stockCode": "000060", "modifyDate": None}]
    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         max_calls=10, max_minutes=10,
                         call_fn=call_fn, directory_fn=lambda key: directory)
    assert report["tickersWithPaginationFailure"] == 1
    assert report["tickersSucceeded"] == 1
    assert not CO.is_reportable_failure(report["outcome"], written=report["written"])


def test_zero_matching_disclosures_status_013_is_success_not_a_failure(tmp_path):
    """DART's own 'no data' status for a ticker with nothing matching."""
    inventory = _inventory(tmp_path, ["000030.KS"])
    store = tmp_path / "store"

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         max_calls=10, max_minutes=10,
                         call_fn=lambda path, params: _list_payload([], status="013"),
                         directory_fn=lambda key: _directory())
    assert report["tickersSucceeded"] == 1
    assert report["written"] == 0
    assert report["outcome"] in ("EMPTY_BUT_VALID", "SERVED")


# --------------------------------------------------------------------------- #
# Identity: the SAME historical resolver as `dart_ownership_universe`
# --------------------------------------------------------------------------- #
def test_a_delisted_issuer_with_no_stock_code_resolves_by_unique_krx_name(tmp_path):
    """DART's current corpCode.xml row for a delisted issuer often carries
    a BLANK stock code; this must still resolve via a unique exact
    normalized historical company name, never stay unresolved."""
    inventory = _inventory(tmp_path, ["004940.KS"], names={"004940.KS": "외환은행"})
    store = tmp_path / "store"
    directory = [{"corpCode": "00999", "corpName": "외환은행", "stockCode": "",
                 "modifyDate": None}]

    def call_fn(path, params):
        assert params["corp_code"] == "00999"
        return _list_payload([_row("20130301000001", corp_code="00999", corp_name="외환은행")])

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         max_calls=10, max_minutes=10,
                         call_fn=call_fn, directory_fn=lambda key: directory)
    assert report["tickersSucceeded"] == 1
    assert report["tickersWithNoDartIdentity"] == 0


def test_an_ambiguous_name_match_stays_unresolved_never_guessed(tmp_path):
    """Two different corp codes share the same normalized company name --
    this must stay UNRESOLVED, never pick either one."""
    inventory = _inventory(tmp_path, ["999999.KS"], names={"999999.KS": "동명주식회사"})
    store = tmp_path / "store"
    directory = [
        {"corpCode": "00801", "corpName": "동명주식회사", "stockCode": "", "modifyDate": None},
        {"corpCode": "00802", "corpName": "동명주식회사", "stockCode": "", "modifyDate": None},
    ]

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         max_calls=10, max_minutes=10,
                         call_fn=lambda path, params: (_ for _ in ()).throw(
                             AssertionError("must never call list.json for an ambiguous name")),
                         directory_fn=lambda key: directory)
    assert report["tickersWithNoDartIdentity"] == 1
    assert report["tickersSucceeded"] == 0


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
