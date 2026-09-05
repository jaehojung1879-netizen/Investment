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
def _unauthorized(date, message="Unauthorized Key"):
    return {"date": date, "error": f"refused — {message}", "status": 401,
            "respMsg": message,
            "keyNotRecognised": "key" in message.lower(),
            "serviceNotAuthorised": "api call" in message.lower(),
            "bodyHead": '{"respMsg":"%s","respCode":"401"}' % message}


def test_an_all_unauthorized_run_is_not_a_finding_about_the_source():
    evidence = P.membership_evidence([_unauthorized("2013-01-02"),
                                      _unauthorized("2026-09-01")])
    assert evidence["verdict"] == "NOT_MEASURED_KEY_NOT_RECOGNISED"
    assert "nothing here is a finding" in evidence["reason"]


def test_a_mixed_failure_is_still_insufficient_snapshots():
    # A 404 alongside a real answer is a different situation: the service does
    # serve us, so the shortfall is about the paths or the dates.
    evidence = P.membership_evidence([
        _snap("2013-01-02", ["005930"]),
        {"date": "2026-09-01", "error": "HTTP 404"}])
    assert evidence["verdict"] == "INSUFFICIENT_SNAPSHOTS"


def test_a_served_pair_still_reaches_a_real_verdict():
    # The unauthorized branch must not swallow runs that actually answered.
    old = [f"{i:06d}" for i in range(200)]
    new = [f"{i:06d}" for i in range(20, 220)]
    evidence = P.membership_evidence([_snap("2013-01-02", old),
                                      _snap("2026-09-01", new)])
    assert evidence["verdict"] == "POINT_IN_TIME"


# --------------------------------------------------------------------------- #
# How the key is presented is a variable, not an inference
#
# The 401 said "Unauthorized Key", and I read that as proof the AUTH_KEY header
# name was right — a service that never saw a key would say "missing". That is
# an inference about someone else's error strings, and inferring from a
# vendor's wording is what cost two rounds on the portal. The transport is
# resolved by trying it now.
# --------------------------------------------------------------------------- #
def test_the_header_name_is_not_the_only_transport_tried():
    names = [name for name, _, _ in P.AUTH_TRANSPORTS]
    assert names[0] == "header:AUTH_KEY"          # what was already measured
    assert any(n.startswith("query:") for n in names)
    assert len(set(names)) == len(names)


def test_a_query_transport_puts_the_key_in_the_url_not_the_headers(monkeypatch):
    seen = {}

    class _Resp:
        status = 200
        def read(self): return b'{"OutBlock_1": []}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _fake(request, timeout=None):
        seen["url"] = request.full_url
        seen["headers"] = dict(request.headers)
        return _Resp()

    monkeypatch.setattr(P.urllib.request, "urlopen", _fake)
    P.call("https://x/svc", "sto/stk_bydd_trd", {"basDd": "20130102"}, "SECRET",
           transport=("query:authKey", "query", "authKey"))
    assert "authKey=SECRET" in seen["url"]
    assert not any(v == "SECRET" for v in seen["headers"].values())


def test_a_header_transport_keeps_the_key_out_of_the_url(monkeypatch):
    seen = {}

    class _Resp:
        status = 200
        def read(self): return b'{"OutBlock_1": []}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _fake(request, timeout=None):
        seen["url"] = request.full_url
        seen["headers"] = dict(request.headers)
        return _Resp()

    monkeypatch.setattr(P.urllib.request, "urlopen", _fake)
    P.call("https://x/svc", "sto/stk_bydd_trd", {"basDd": "20130102"}, "SECRET",
           transport=("header:AUTH_KEY", "header", "AUTH_KEY"))
    assert "SECRET" not in seen["url"]
    assert any(v == "SECRET" for v in seen["headers"].values())


# --------------------------------------------------------------------------- #
# The vendor's own words, not our guess at them
#
# The first run's label was hardcoded to "Unauthorized Key" for any 401. The
# second run's bodies actually read `Unauthorized API Call`, and the label was
# overwriting that — two different statements collapsed into one. They are not
# the same finding: the first says the key is not recognised, the second says
# it IS and the call is not authorised for it. Only the second points at a
# subscription rather than at the key.
# --------------------------------------------------------------------------- #
def test_the_service_message_is_parsed_out_of_the_body():
    assert P.resp_message('{"respMsg":"Unauthorized API Call","respCode":"401"}') \
        == "Unauthorized API Call"
    assert P.resp_message("<html>not json</html>") is None
    assert P.resp_message('{"respCode":"401"}') is None


def test_an_unrecognised_key_and_an_unauthorised_call_are_different_verdicts():
    key = P.membership_evidence([_unauthorized("2013-01-02", "Unauthorized Key"),
                                 _unauthorized("2026-09-01", "Unauthorized Key")])
    call = P.membership_evidence([_unauthorized("2013-01-02", "Unauthorized API Call"),
                                  _unauthorized("2026-09-01", "Unauthorized API Call")])
    assert key["verdict"] == "NOT_MEASURED_KEY_NOT_RECOGNISED"
    assert call["verdict"] == "NOT_MEASURED_SERVICE_NOT_AUTHORISED"
    assert key["verdict"] != call["verdict"]


def test_the_unauthorised_call_verdict_points_at_the_subscription_not_the_code():
    report = P.membership_evidence([
        _unauthorized("2013-01-02", "Unauthorized API Call"),
        _unauthorized("2026-09-01", "Unauthorized API Call")])
    assert "subscribing the key" in report["reason"]
    assert "not changing this code" in report["reason"]
    assert report["respMsg"] == "Unauthorized API Call"


def test_the_message_is_carried_onto_the_snapshot_verbatim(monkeypatch):
    import urllib.error

    def _fake(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {},
            __import__("io").BytesIO(
                b'{"respMsg":"Unauthorized API Call","respCode":"401"}'))

    monkeypatch.setattr(P.urllib.request, "urlopen", _fake)
    answer = P.call("https://x/svc", "sto/stk_bydd_trd", {"basDd": "20130102"}, "K")
    assert answer["respMsg"] == "Unauthorized API Call"
    assert answer["serviceNotAuthorised"] is True
    assert answer["keyNotRecognised"] is False
    assert "Unauthorized API Call" in answer["error"]
