"""The same 2026-09-24 exit-semantics defect, for the short-selling collector
sharing `collect_kr_investor_flow.py`'s KRX-portal-refusal shape.
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
    "collect_kr_short_selling", ROOT / "scripts" / "collect_kr_short_selling.py")
C = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = C
_spec.loader.exec_module(C)


@pytest.fixture
def store(tmp_path):
    return tmp_path / "kr-short-selling"


def test_a_refusal_after_bld_discovery_exits_nonzero_and_writes_no_shard(store, monkeypatch):
    monkeypatch.setattr(C, "establish_session", lambda screen_url: {})
    # Bypass bld discovery so the run reaches the per-ticker/date loop, where
    # the real 2026-09-24 refusal actually happened.
    monkeypatch.setattr(C, "find_working_bld",
                        lambda candidates, params, cookies, referer: candidates[0])

    def _refuse(bld, params, cookies, referer, timeout=30):
        raise C.Refused("HTTP 400")

    monkeypatch.setattr(C, "call", _refuse)

    code = C.main([str(store), "--universe-tickers", "005930.KS", "--start", "2013-01-01",
                  "--end", "2013-01-02", "--max-calls", "10", "--max-minutes", "10"])

    assert code != 0, "a zero-progress source refusal must never exit 0"
    trading_shards = list(store.glob("kr-short-trading-*.jsonl.gz"))
    netpos_shards = list(store.glob("kr-short-netpos-*.jsonl.gz"))
    assert trading_shards == [] and netpos_shards == [], (
        "no shard may be written for a refused, zero-progress run")

    done = json.loads((store / C.DONE_NAME).read_text())
    assert done == [], "a refused pair is never marked done"

    manifest = json.loads((store / "manifest.json").read_text())
    assert manifest["thisRun"]["rowsWritten"] == 0
    assert manifest["thisRun"]["outcome"] == "BLOCKED_SOURCE"


def test_no_bld_candidate_served_at_all_exits_nonzero_before_any_manifest(store, monkeypatch):
    monkeypatch.setattr(C, "establish_session", lambda screen_url: {})
    monkeypatch.setattr(C, "find_working_bld", lambda candidates, params, cookies, referer: None)

    code = C.main([str(store), "--universe-tickers", "005930.KS", "--start", "2013-01-01",
                  "--end", "2013-01-01"])

    assert code != 0
    assert not (store / "manifest.json").exists()


def test_a_served_run_exits_zero(store, monkeypatch):
    monkeypatch.setattr(C, "establish_session", lambda screen_url: {})
    monkeypatch.setattr(C, "find_working_bld",
                        lambda candidates, params, cookies, referer: candidates[0])

    def _served(bld, params, cookies, referer, timeout=30):
        return {"OutBlock_1": [{"trdVal1": "1,000"}]}

    monkeypatch.setattr(C, "call", _served)

    code = C.main([str(store), "--universe-tickers", "005930.KS", "--start", "2013-01-01",
                  "--end", "2013-01-01", "--max-calls", "10", "--max-minutes", "10"])

    assert code == 0
    manifest = json.loads((store / "manifest.json").read_text())
    assert manifest["thisRun"]["outcome"] in ("SERVED", "EMPTY_BUT_VALID")
