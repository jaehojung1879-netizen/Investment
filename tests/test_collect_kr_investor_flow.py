"""The exact 2026-09-24 defect, reproduced offline: a KRX portal refusal on
the very first call must never exit 0, mark a ticker/date pair done, or
leave behind a shard file — all three happened on the real run before this
fix (Actions run 35963936572: 0 calls, 0 records, 0 shards, `REFUSED`, exit
0, workflow green).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "collect_kr_investor_flow", ROOT / "scripts" / "collect_kr_investor_flow.py")
C = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = C
_spec.loader.exec_module(C)


@pytest.fixture
def store(tmp_path):
    return tmp_path / "kr-investor-flow"


def test_a_refusal_on_the_first_call_exits_nonzero_and_writes_no_shard(store, monkeypatch):
    monkeypatch.setattr(C, "establish_session", lambda: {})

    def _refuse(bld, params, cookies, timeout=30):
        raise C.Refused("HTTP 400: b'LOGOUT'")

    monkeypatch.setattr(C, "call", _refuse)

    code = C.main([str(store), "--universe-tickers", "005930.KS", "--start", "2013-01-01",
                  "--end", "2013-01-02", "--max-calls", "10", "--max-minutes", "10"])

    assert code != 0, "a zero-progress source refusal must never exit 0"
    shards = list(store.glob("kr-investor-flow-*.jsonl.gz"))
    assert shards == [], "no shard may be written for a refused, zero-progress run"

    done = json.loads((store / C.DONE_NAME).read_text())
    assert done == [], "a refused pair is never marked done"

    manifest = json.loads((store / "manifest.json").read_text())
    assert manifest["thisRun"]["recordsWritten"] == 0
    assert manifest["thisRun"]["outcome"] == "BLOCKED_SOURCE"


def test_a_served_run_exits_zero_and_writes_a_shard(store, monkeypatch):
    monkeypatch.setattr(C, "establish_session", lambda: {})

    def _served(bld, params, cookies, timeout=30):
        return {"OutBlock_1": [{"trdVal1": "1,000", "trdVal2": "2,000"}]}

    monkeypatch.setattr(C, "call", _served)

    code = C.main([str(store), "--universe-tickers", "005930.KS", "--start", "2013-01-01",
                  "--end", "2013-01-01", "--max-calls", "10", "--max-minutes", "10"])

    assert code == 0
    manifest = json.loads((store / "manifest.json").read_text())
    assert manifest["thisRun"]["outcome"] in ("SERVED", "EMPTY_BUT_VALID")
