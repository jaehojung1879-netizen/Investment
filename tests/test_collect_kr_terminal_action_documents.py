"""`scripts/collect_kr_terminal_action_documents.py` against a fake
`call_fn` -- no network. Synthetic ZIP fixtures only; this collector has
not been run against real DART content yet (see the module docstring and
`docs/kr-terminal-action-reconstruction-v2.md`).
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "collect_kr_terminal_action_documents",
    ROOT / "scripts/collect_kr_terminal_action_documents.py")
COLLECT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(COLLECT)

from pipeline import collector_outcomes as CO  # noqa: E402


def _make_zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _inventory(tmp_path, rows):
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({"securities": rows}))
    return path


def _write_disclosure_shard(store, rows):
    store.mkdir(parents=True, exist_ok=True)
    path = store / "kr-corporate-actions-disclosures.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _disclosure(ticker, rcept_no, rcept_date, families=("MERGER",)):
    return {"ticker": ticker, "corpCode": "00123", "corpName": "x", "reportName": "합병결정",
           "disclosureFamilies": list(families), "receiptNo": rcept_no, "receiptDate": rcept_date,
           "filerName": "x", "isAmendment": False}


# --------------------------------------------------------------------------- #
# decode_member / extract_zip_members
# --------------------------------------------------------------------------- #
def test_utf8_member_decodes_directly():
    text, encoding = COLLECT.decode_member("합병결정 원문입니다".encode())
    assert encoding == "utf-8"
    assert "합병결정" in text


def test_euckr_member_falls_back_and_decodes():
    text, encoding = COLLECT.decode_member("합병결정".encode("cp949"))
    assert encoding == "cp949"
    assert "합병결정" in text


def test_extract_zip_members_reads_every_file_with_its_own_hash():
    raw = _make_zip({"main.xml": b"<doc>content</doc>", "attach.xml": b"<attach/>"})
    members = COLLECT.extract_zip_members(raw)
    assert len(members) == 2
    names = {m["filename"] for m in members}
    assert names == {"main.xml", "attach.xml"}
    main = next(m for m in members if m["filename"] == "main.xml")
    assert main["sha256"] == hashlib.sha256(b"<doc>content</doc>").hexdigest()


def test_non_zip_response_is_refused_not_silently_stored():
    import pytest
    with pytest.raises(COLLECT.Refused, match="did not return a ZIP"):
        COLLECT.extract_zip_members(b'{"status":"013"}')


# --------------------------------------------------------------------------- #
# narrowed_receipts -- built from the real disclosure index, never accepted
# from a caller
# --------------------------------------------------------------------------- #
def test_narrowed_receipts_only_includes_plausibly_responsible_filings(tmp_path):
    store = tmp_path / "store"
    _write_disclosure_shard(store, [
        _disclosure("000030.KS", "20190101000001", "2019-01-15"),
        _disclosure("000030.KS", "20100101000001", "2010-01-01"),  # far outside window
    ])
    inventory = _inventory(tmp_path, [{"code": "000030.KS", "lastTradingDate": "2019-02-12"}])
    targets = COLLECT.narrowed_receipts(store, inventory)
    assert targets == [("000030.KS", "20190101000001")]


def test_a_security_with_no_last_trading_date_contributes_nothing(tmp_path):
    store = tmp_path / "store"
    _write_disclosure_shard(store, [_disclosure("000030.KS", "20190101000001", "2019-01-15")])
    inventory = _inventory(tmp_path, [{"code": "000030.KS", "lastTradingDate": None}])
    targets = COLLECT.narrowed_receipts(store, inventory)
    assert targets == []


# --------------------------------------------------------------------------- #
# run() -- happy path, resumability, hard call budget
# --------------------------------------------------------------------------- #
def test_a_served_run_writes_a_shard_and_completes(tmp_path):
    store = tmp_path / "store"
    _write_disclosure_shard(store, [_disclosure("000030.KS", "20190101000001", "2019-01-15")])
    inventory = _inventory(tmp_path, [{"code": "000030.KS", "lastTradingDate": "2019-02-12"}])
    zip_bytes = _make_zip({"main.xml": b"<doc>x</doc>"})

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         max_calls=10, max_minutes=10,
                         call_fn=lambda key, rcept: (zip_bytes, "application/x-zip"))
    assert report["outcome"] == "SERVED"
    assert report["written"] == 1
    assert report["datasetComplete"] is True
    assert (store / "kr-terminal-action-documents.jsonl.gz").exists()
    assert not CO.is_reportable_failure(report["outcome"], written=report["written"])


def test_a_fetch_failure_is_recorded_and_does_not_stop_the_run(tmp_path):
    store = tmp_path / "store"
    _write_disclosure_shard(store, [
        _disclosure("000030.KS", "20190101000001", "2019-01-15"),
        _disclosure("000030.KS", "20190201000002", "2019-01-20"),
    ])
    inventory = _inventory(tmp_path, [{"code": "000030.KS", "lastTradingDate": "2019-02-12"}])

    def call_fn(key, rcept):
        if rcept == "20190101000001":
            raise COLLECT.Refused("HTTP 404")
        return _make_zip({"main.xml": b"<doc/>"}), "application/x-zip"

    report = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         max_calls=10, max_minutes=10, call_fn=call_fn)
    assert report["receiptsFailed"] == 1
    assert report["receiptsSucceeded"] == 1
    assert report["written"] == 1


def test_no_call_ever_occurs_beyond_max_calls(tmp_path):
    store = tmp_path / "store"
    _write_disclosure_shard(store, [
        _disclosure("000030.KS", f"2019010100000{n}", "2019-01-15") for n in range(1, 6)
    ])
    inventory = _inventory(tmp_path, [{"code": "000030.KS", "lastTradingDate": "2019-02-12"}])
    calls_made = {"n": 0}

    def call_fn(key, rcept):
        calls_made["n"] += 1
        return _make_zip({"main.xml": b"<doc/>"}), "application/x-zip"

    COLLECT.run(store, key="fakekey", inventory_path=inventory,
               max_calls=2, max_minutes=10, call_fn=call_fn)
    assert calls_made["n"] == 2


def test_a_budget_exhausted_run_is_resumed_next_time(tmp_path):
    store = tmp_path / "store"
    _write_disclosure_shard(store, [
        _disclosure("000030.KS", "20190101000001", "2019-01-15"),
        _disclosure("000030.KS", "20190201000002", "2019-01-20"),
    ])
    inventory = _inventory(tmp_path, [{"code": "000030.KS", "lastTradingDate": "2019-02-12"}])

    def call_fn(key, rcept):
        return _make_zip({"main.xml": b"<doc/>"}), "application/x-zip"

    first = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                        max_calls=1, max_minutes=10, call_fn=call_fn)
    assert first["receiptsSucceeded"] == 1
    assert first["datasetComplete"] is False

    second = COLLECT.run(store, key="fakekey", inventory_path=inventory,
                         max_calls=10, max_minutes=10, call_fn=call_fn)
    assert second["receiptsSucceeded"] == 2
    assert second["datasetComplete"] is True
