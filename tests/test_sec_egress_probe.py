"""The egress probe's judgement, pinned without SEC.

The header-isolation run ruled out the request shape, and in doing so held the
runner — and therefore the egress address — fixed. One address refused eight
times is one observation repeated eight times. This fans out across runners to
vary that, and the discipline it must keep is the same one the header probe
kept with its baseline: an experiment that did not vary its variable proves
nothing about it. So the address COUNT is checked before any verdict.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location(
    "probe_sec_egress", ROOT / "scripts" / "probe_sec_egress.py")
P = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = P
_spec.loader.exec_module(P)


def _shard(shard, ip, **outcomes):
    return {"shard": shard, "egressIp": ip,
            "attempts": {host: {"outcome": outcome, "status": 200 if outcome == "SERVED" else 403}
                         for host, outcome in outcomes.items()}}


# --------------------------------------------------------------------------- #
# The guard that comes before the verdict
# --------------------------------------------------------------------------- #
def test_one_address_across_every_shard_is_refused_a_verdict():
    # Six shards that all landed on the same address is the header run again,
    # not a new experiment — and it must not read as "the pool is blocked".
    shards = [_shard(i, "10.0.0.1", **{"data.sec.gov": "BLOCKED"}) for i in range(6)]
    report = P.summarize(shards)
    assert report["verdict"] == "DID_NOT_VARY_THE_ADDRESS"
    assert report["distinctAddresses"] == 1
    assert "says nothing" in report["meaning"]


def test_shards_with_no_address_at_all_are_refused_a_verdict():
    shards = [_shard(i, None, **{"data.sec.gov": "BLOCKED"}) for i in range(3)]
    assert P.summarize(shards)["verdict"] == "DID_NOT_VARY_THE_ADDRESS"


# --------------------------------------------------------------------------- #
# The three real outcomes
# --------------------------------------------------------------------------- #
def test_a_mixed_result_is_an_address_lottery_not_a_pool_policy():
    shards = [_shard(0, "10.0.0.1", **{"data.sec.gov": "BLOCKED"}),
              _shard(1, "10.0.0.2", **{"data.sec.gov": "SERVED"})]
    report = P.summarize(shards)
    assert report["verdict"] == "SERVED_ON_SOME_ADDRESSES"
    assert "lottery" in report["meaning"]
    assert report["served"] == ["10.0.0.2/data.sec.gov"]
    assert report["refused"] == ["10.0.0.1/data.sec.gov"]


def test_every_address_refused_upholds_the_pool_reading():
    shards = [_shard(0, "10.0.0.1", **{"data.sec.gov": "BLOCKED"}),
              _shard(1, "10.0.0.2", **{"data.sec.gov": "BLOCKED"})]
    report = P.summarize(shards)
    assert report["verdict"] == "REFUSED_ON_EVERY_ADDRESS"
    assert report["served"] == []


def test_every_address_served_says_the_block_was_not_permanent():
    shards = [_shard(0, "10.0.0.1", **{"data.sec.gov": "SERVED"}),
              _shard(1, "10.0.0.2", **{"data.sec.gov": "SERVED"})]
    report = P.summarize(shards)
    assert report["verdict"] == "SERVED_ON_EVERY_ADDRESS"
    assert "re-measured" in report["meaning"]


def test_the_two_hosts_are_counted_separately():
    # A fix that reaches data.sec.gov may not reach www.sec.gov, so one being
    # served must not hide the other being refused.
    shards = [_shard(0, "10.0.0.1", **{"data.sec.gov": "SERVED",
                                       "www.sec.gov": "BLOCKED"}),
              _shard(1, "10.0.0.2", **{"data.sec.gov": "SERVED",
                                       "www.sec.gov": "BLOCKED"})]
    report = P.summarize(shards)
    assert report["verdict"] == "SERVED_ON_SOME_ADDRESSES"
    assert sorted(report["refused"]) == ["10.0.0.1/www.sec.gov", "10.0.0.2/www.sec.gov"]


def test_the_request_is_held_at_the_headers_that_worked_in_august():
    # The address is the variable; the request must not move with it or the
    # run isolates nothing again.
    sent = P.headers("me@example.com")
    assert sent["User-Agent"].startswith("InvestmentResearchDashboard/1.1")
    assert "Accept-Encoding" not in sent
