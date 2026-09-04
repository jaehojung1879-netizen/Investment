"""The KRX probe's judgement, pinned without the vendor.

Only one thing here really matters, and it is the thing that would otherwise
be discovered years into a replay: an endpoint that takes a date and ignores
it returns a perfectly shaped cross-section for 2013 that is TODAY'S. Every
count, format and ticker check passes on it. So the probe's verdict must turn
on whether the dates DISAGREE, and these tests hold it to that — a repeated
snapshot is refused even when it is complete and well formed, which is exactly
when it is most convincing.

The transport moved to the KRX Open API (`AUTH_KEY`) after the public portal
answered `LOGOUT` to every request, with and without a real session. The
judgement below is transport-agnostic and did not move with it.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location(
    "probe_krx_index_membership", ROOT / "scripts" / "probe_krx_index_membership.py")
P = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = P
_spec.loader.exec_module(P)


def _payload(codes) -> bytes:
    return json.dumps({"OutBlock_1": [{"ISU_SRT_CD": c, "ISU_ABBRV": f"name-{c}"}
                                      for c in codes]}).encode("utf-8")


def _snap(date, codes):
    return P.parse_constituents(date, 200, _payload(codes))


# --------------------------------------------------------------------------- #
# Parsing — a block page is a fact about the source, not a crash
# --------------------------------------------------------------------------- #
def test_a_non_json_response_is_reported_with_what_came_back():
    entry = P.parse_constituents("2013-01-02", 200, b"<html>blocked</html>")
    assert "error" in entry and "not JSON" in entry["error"]
    assert "blocked" in entry["bodyHead"]


def test_an_unexpected_payload_shape_is_reported_not_read_as_empty():
    entry = P.parse_constituents("2013-01-02", 200, b'{"message": "no data"}')
    assert entry.get("error")
    assert entry.get("count") is None


def test_codes_are_deduplicated_and_carry_the_pipeline_suffix():
    entry = _snap("2013-01-02", ["005930", "005930", "000660"])
    assert entry["count"] == 2
    assert P.to_pipeline_ticker("005930") == "005930.KS"


# --------------------------------------------------------------------------- #
# The decisive check: does the date change the answer?
# --------------------------------------------------------------------------- #
def test_identical_lists_across_a_decade_are_refused_however_complete():
    codes = [f"{i:06d}" for i in range(200)]
    evidence = P.membership_evidence([_snap("2013-01-02", codes),
                                      _snap("2026-09-01", codes)])
    assert evidence["verdict"] == "NOT_POINT_IN_TIME"
    assert evidence["oldestNewestOverlapPct"] == 100.0
    assert "date stamped on it" in evidence["reason"]


def test_a_list_that_only_ever_grows_is_still_refused():
    # Overlap below 100 is not enough on its own: a source that adds names but
    # never loses one is not describing membership, and the departed names are
    # the entire point of the file.
    old = [f"{i:06d}" for i in range(180)]
    new = old + [f"{i:06d}" for i in range(180, 200)]
    evidence = P.membership_evidence([_snap("2013-01-02", old),
                                      _snap("2026-09-01", new)])
    assert evidence["verdict"] == "NOT_POINT_IN_TIME"
    assert evidence["departedMembers"] == 0


def test_lists_that_lose_and_gain_names_are_accepted_as_history():
    old = [f"{i:06d}" for i in range(200)]
    new = [f"{i:06d}" for i in range(20, 220)]
    evidence = P.membership_evidence([_snap("2013-01-02", old),
                                      _snap("2026-09-01", new)])
    assert evidence["verdict"] == "POINT_IN_TIME"
    assert evidence["departedMembers"] == 20
    assert evidence["joinedMembers"] == 20
    assert evidence["departedSample"][0].endswith(".KS")


def test_one_answering_date_cannot_settle_the_question_either_way():
    evidence = P.membership_evidence([_snap("2013-01-02", ["005930"]),
                                      {"date": "2026-09-01", "error": "HTTP 403"}])
    assert evidence["verdict"] == "INSUFFICIENT_SNAPSHOTS"
    assert evidence["snapshotsUsable"] == 1


def test_pairwise_movement_is_reported_between_every_adjacent_pair():
    evidence = P.membership_evidence([_snap("2013-01-02", ["A", "B"]),
                                      _snap("2020-01-02", ["B", "C"]),
                                      _snap("2026-09-01", ["C", "D"])])
    assert [row["from"] for row in evidence["pairwise"]] == ["2013-01-02", "2020-01-02"]
    assert evidence["pairwise"][0]["left"] == 1


# --------------------------------------------------------------------------- #
# Reach into the replay's own universe — measured, never a gate
# --------------------------------------------------------------------------- #
def test_universe_reach_counts_only_names_the_snapshot_actually_holds():
    reach = P.universe_reach([_snap("2013-01-02", ["005930", "999999"])],
                             ["005930.KS", "000660.KS"])
    assert reach["byDate"][0]["universeNamesHeld"] == 1
    assert reach["byDate"][0]["universeNamesHeldPct"] == 50.0


def test_universe_reach_says_so_when_nothing_answered():
    assert P.universe_reach([{"date": "2013-01-02", "error": "HTTP 403"}],
                            ["005930.KS"]) == {"measured": False}


# --------------------------------------------------------------------------- #
# What the rows carry decides whether a dated market-cap universe is possible
#
# The replay's KR universe is ~119 large names, not literally the KOSPI 200.
# A per-issue cross-section carrying MKTCAP reconstructs that universe by the
# rule it actually uses, so the probe reports the columns rather than assuming
# them.
# --------------------------------------------------------------------------- #
def test_market_cap_and_share_columns_are_reported_when_present():
    raw = json.dumps({"OutBlock_1": [
        {"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자",
         "MKTCAP": "400000000", "LIST_SHRS": "5969782550"}]}).encode("utf-8")
    entry = P.parse_constituents("2013-01-02", 200, raw)
    assert entry["hasMarketCap"] is True
    assert entry["hasSharesOutstanding"] is True
    assert "MKTCAP" in entry["columns"]


def test_their_absence_is_reported_rather_than_assumed():
    entry = _snap("2013-01-02", ["005930"])
    assert entry["hasMarketCap"] is False
    assert entry["hasSharesOutstanding"] is False


def test_the_open_api_rows_key_is_read():
    # OutBlock_1 is what the Open API returns; the portal's `output` is kept
    # so an older captured response still parses.
    entry = P.parse_constituents("2013-01-02", 200,
                                 json.dumps({"output": [{"ISU_CD": "000660"}]}).encode())
    assert entry["count"] == 1


# --------------------------------------------------------------------------- #
# A refused key measured our credentials, not the data
#
# MEASURED: every endpoint answered
# `{"respMsg":"Unauthorized Key","respCode":"401"}`. That settles two things a
# bare status could not — the base and path are right (a wrong path gives 404,
# not structured KRX JSON) and the key was READ and rejected rather than
# missing. Rolled up into INSUFFICIENT_SNAPSHOTS it would read as "KRX has no
# dated cross-section" and retire a source that was never actually asked.
# --------------------------------------------------------------------------- #
def _unauthorized(date):
    return {"date": date,
            "error": "key refused — the service answered Unauthorized Key",
            "status": 401, "unauthorizedKey": True,
            "bodyHead": '{"respMsg":"Unauthorized Key","respCode":"401"}'}


def test_an_all_unauthorized_run_is_not_a_finding_about_the_source():
    evidence = P.membership_evidence([_unauthorized("2013-01-02"),
                                      _unauthorized("2026-09-01")])
    assert evidence["verdict"] == "NOT_MEASURED_UNAUTHORIZED_KEY"
    assert "nothing here is a finding" in evidence["reason"]
    # The two facts the 401 establishes, both worth keeping in the reason.
    assert "path and base are right" in evidence["reason"]


def test_a_mixed_failure_is_still_insufficient_snapshots():
    # A 404 alongside a real answer is a different situation: the service does
    # serve us, so the shortfall is about the paths or the dates.
    evidence = P.membership_evidence([
        _snap("2013-01-02", ["005930"]),
        {"date": "2026-09-01", "error": "HTTP 404", "unauthorizedKey": False}])
    assert evidence["verdict"] == "INSUFFICIENT_SNAPSHOTS"


def test_a_served_pair_still_reaches_a_real_verdict():
    # The unauthorized branch must not swallow runs that actually answered.
    old = [f"{i:06d}" for i in range(200)]
    new = [f"{i:06d}" for i in range(20, 220)]
    evidence = P.membership_evidence([_snap("2013-01-02", old),
                                      _snap("2026-09-01", new)])
    assert evidence["verdict"] == "POINT_IN_TIME"
