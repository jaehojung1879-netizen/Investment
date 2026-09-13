"""The US PIT source probe's judgement, which must hold without a vendor.

The network half can only run in CI. What is pinned here is everything that
decides what the probe's answer MEANS — and each of these is a mistake this
repository has already made once:

  * a structured refusal proves reachability (KRX's `Unauthorized Key`), while
    an HTML interstitial does not (SEC's block page), and NOTHING coming back
    is not yet a fact about the vendor at all;
  * a date window that comes back full of recent rows is the Naver `fchart`
    shape, not depth;
  * a vendor serving only currently-listed names is a survivorship hole, not a
    coverage percentage;
  * a credential that was never sent is not evidence about the source.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "probe_us_pit_fundamentals", ROOT / "scripts" / "probe_us_pit_fundamentals.py")
P = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = P
_spec.loader.exec_module(P)


def _reading(periods, filings, *, field="filedDate", fields=None):
    return {"rowCount": len(periods), "periodEnds": list(periods),
            "filingDates": list(filings), "filingDateField": field,
            "fieldsFound": fields or {}, "sampleRow": {}}


# --------------------------------------------------------------------------- #
# Reachability is a different question from authorisation, and "no answer" is
# a different question from both
# --------------------------------------------------------------------------- #
def test_a_structured_refusal_proves_the_host_answered_us():
    """KRX answered `{"respMsg":"Unauthorized Key"}` and that established the
    base and the path were right. Reading it as "could not answer" would
    retire a source that was never actually asked."""
    assert P.reach_outcome(401, b'{"error":"Unknown API Key"}') == P.ANSWERED
    assert P.reach_outcome(403, b'{"status":"ERROR"}') == P.ANSWERED


def test_an_html_interstitial_is_not_the_vendors_protocol():
    body = b"<html><body>Your Request Originates from an Undeclared Automated Tool</body></html>"
    assert P.reach_outcome(403, body) == P.BLOCK_PAGE


def test_a_two_hundred_carrying_html_is_still_not_an_answer():
    """SEC serves refusals with 403 and sometimes with 200, so the body
    decides and never the status code."""
    assert P.reach_outcome(200, b"<html>maintenance</html>") == P.BLOCK_PAGE


def test_nothing_coming_back_is_not_the_same_as_being_refused():
    assert P.reach_outcome(None, None) == P.NO_ANSWER
    assert P.reach_outcome(None, b"") == P.NO_ANSWER


def test_no_answer_is_not_attributed_to_the_vendor():
    """Our side — egress policy, DNS, TLS — has not been ruled out, and
    attributing a refusal before that is how the SEC conclusion spent a
    while being an assumption."""
    verdict = P.vendor_verdict(P.NO_ANSWER, key_present=False, living={}, departed={})
    assert verdict["verdict"] == P.NO_ANSWER_FROM_HOST
    assert verdict["verdict"] != P.HOST_REFUSED


def test_a_block_page_is_attributed_to_the_host():
    verdict = P.vendor_verdict(P.BLOCK_PAGE, key_present=False, living={}, departed={})
    assert verdict["verdict"] == P.HOST_REFUSED


# --------------------------------------------------------------------------- #
# The publication date is decided before depth, because depth without it is
# lookahead rather than history
# --------------------------------------------------------------------------- #
def test_rows_inside_the_window_without_a_filing_date_are_not_depth():
    reading = _reading(["2012-03-31", "2012-06-30"], [None, None], field=None)
    assessed = P.assess_window(reading, takes_date_window=True)
    assert assessed["depth"] == P.NO_FILING_DATE
    assert assessed["depth"] != P.PIT_DEPTH_CONFIRMED


def test_rows_inside_the_window_with_a_filing_date_are_depth():
    reading = _reading(["2012-03-31"], ["2012-05-02"])
    assessed = P.assess_window(reading, takes_date_window=True)
    assert assessed["depth"] == P.PIT_DEPTH_CONFIRMED
    assert assessed["earliestPeriodInWindow"] == "2012-03-31"


def test_partial_filing_date_coverage_is_counted_not_rounded_up():
    reading = _reading(["2012-03-31", "2012-06-30"], ["2012-05-02", None])
    assessed = P.assess_window(reading, takes_date_window=True)
    assert assessed["filingDateCoverage"] == 1


# --------------------------------------------------------------------------- #
# A window that was accepted and not honoured is the Naver `fchart` shape —
# 46,356 Korean rows went missing that way and nothing failed
# --------------------------------------------------------------------------- #
def test_a_date_window_answered_with_recent_rows_is_not_depth():
    reading = _reading(["2026-06-30", "2026-03-31"], ["2026-07-31", "2026-05-01"])
    assessed = P.assess_window(reading, takes_date_window=True)
    assert assessed["depth"] == P.WINDOW_NOT_HONOURED
    assert assessed["depth"] != P.PIT_DEPTH_CONFIRMED
    assert assessed["returnedRange"] == ["2026-03-31", "2026-06-30"], \
        "돌려준 범위를 보고해야 창이 무시됐다는 걸 읽을 수 있다"


def test_an_endpoint_that_takes_no_date_is_a_different_finding():
    """"Too shallow" of an endpoint that cannot be asked by date blames the
    data for the endpoint, and they have different fixes."""
    reading = _reading(["2026-06-30"], ["2026-07-31"])
    assessed = P.assess_window(reading, takes_date_window=False)
    assert assessed["depth"] == P.NO_DATE_WINDOW_ENDPOINT
    assert assessed["depth"] != P.WINDOW_NOT_HONOURED


def test_an_endpoint_with_no_date_window_that_still_reaches_back_is_depth():
    reading = _reading(["2012-09-29"], ["2012-10-31"])
    assert P.assess_window(reading, takes_date_window=False)["depth"] == P.PIT_DEPTH_CONFIRMED


def test_an_error_body_is_carried_into_the_assessment_not_dropped():
    assessed = P.assess_window({"errorBody": "Premium Query Parameter"},
                               takes_date_window=True)
    assert assessed["depth"] == P.REFUSED
    assert assessed["detail"] == "Premium Query Parameter"


def test_a_response_with_no_rows_is_not_a_refusal():
    assessed = P.assess_window(P.empty_reading(), takes_date_window=True)
    assert assessed["depth"] == P.NO_ROWS


# --------------------------------------------------------------------------- #
# The two cohorts are never pooled: 219 of the 829 US names were members
# before 2013 and are gone
# --------------------------------------------------------------------------- #
def _confirmed():
    return {"depth": P.PIT_DEPTH_CONFIRMED, "fieldsFound": {}}


def _empty():
    return {"depth": P.NO_ROWS}


def test_a_vendor_answering_but_holding_nothing_is_a_survivorship_hole():
    verdict = P.vendor_verdict(P.ANSWERED, True,
                               living={"AAPL": _confirmed(), "KO": _confirmed()},
                               departed={"SHLD": _empty(), "ANR": _empty()})
    assert verdict["verdict"] == P.LIVING_ONLY
    assert verdict["verdict"] != P.OPEN, "살아 있는 이름만으로 경로를 열면 안 된다"


def test_departed_names_refused_per_symbol_are_not_called_a_coverage_hole():
    """FMP refused all four departed names with a SUBSCRIPTION sentence, and
    one of them (`AA`) still trades. A paywall and an absent history point at
    a price and at survivorship bias respectively, so they cannot share a
    verdict."""
    refusal = {"depth": P.REFUSED,
               "detail": "Special Endpoint : This value set for 'symbol' is "
                         "not available under your current subscription"}
    verdict = P.vendor_verdict(P.ANSWERED, True,
                               living={"AAPL": _confirmed()},
                               departed={"ANR": dict(refusal), "BIG": dict(refusal)})
    assert verdict["verdict"] == P.DEPARTED_REFUSED
    assert verdict["verdict"] != P.LIVING_ONLY
    assert verdict["verdict"] != P.OPEN
    assert "current subscription" in " ".join(verdict["refusals"]), \
        "구독 제한이라는 벤더의 문장이 판정에 남아야 돈으로 풀리는지 알 수 있다"


def test_a_mix_of_refusal_and_emptiness_is_read_as_the_coverage_hole():
    """One refused name does not turn an otherwise empty cohort into a
    billing question."""
    verdict = P.vendor_verdict(P.ANSWERED, True,
                               living={"AAPL": _confirmed()},
                               departed={"ANR": {"depth": P.REFUSED, "detail": "nope"},
                                         "BIG": _empty()})
    assert verdict["verdict"] == P.LIVING_ONLY


def test_both_cohorts_served_opens_the_route():
    verdict = P.vendor_verdict(P.ANSWERED, True,
                               living={"AAPL": _confirmed()},
                               departed={"SHLD": _confirmed()})
    assert verdict["verdict"] == P.OPEN


def test_a_departed_name_served_does_not_rescue_a_shallow_living_cohort():
    verdict = P.vendor_verdict(P.ANSWERED, True,
                               living={"AAPL": {"depth": P.WINDOW_NOT_HONOURED}},
                               departed={"SHLD": _confirmed()})
    assert verdict["verdict"] == P.TOO_SHALLOW


def test_a_missing_key_claims_nothing_about_depth():
    verdict = P.vendor_verdict(P.ANSWERED, key_present=False, living={}, departed={})
    assert verdict["verdict"] == P.KEY_MISSING
    assert verdict["verdict"] not in (P.TOO_SHALLOW, P.HOST_REFUSED, P.NO_POINT_IN_TIME)


def test_every_sample_refused_is_the_credential_not_the_depth():
    verdict = P.vendor_verdict(P.ANSWERED, True,
                               living={"AAPL": {"depth": P.REFUSED, "detail": "Invalid API key"}},
                               departed={"SHLD": {"depth": P.REFUSED, "detail": "Invalid API key"}})
    assert verdict["verdict"] == P.KEY_REFUSED
    assert "Invalid API key" in " ".join(verdict["refusals"]), \
        "벤더의 문장이 판정에 그대로 실려야 한다"


def test_data_without_a_publication_date_anywhere_retires_the_vendor():
    verdict = P.vendor_verdict(P.ANSWERED, True,
                               living={"AAPL": {"depth": P.NO_FILING_DATE}},
                               departed={"SHLD": {"depth": P.NO_FILING_DATE}})
    assert verdict["verdict"] == P.NO_POINT_IN_TIME


# --------------------------------------------------------------------------- #
# Per-vendor readers — a renamed field reads as an absent one, which is the
# worse finding, so candidates are checked and the answering name recorded
# --------------------------------------------------------------------------- #
def test_finnhub_filed_date_and_gaap_tags_are_read():
    payload = {"data": [{"symbol": "AAPL", "endDate": "2012-09-29",
                         "filedDate": "2012-10-31", "acceptedDate": "2012-10-31 16:30:00",
                         "report": {"ic": [{"concept": "NetIncomeLoss", "value": 41733}],
                                    "bs": [{"concept": "Assets", "value": 176064}]}}]}
    reading = P.read_finnhub(payload)
    assert reading["periodEnds"] == ["2012-09-29"]
    assert reading["filingDates"] == ["2012-10-31"]
    assert reading["filingDateField"] == "filedDate"
    assert reading["fieldsFound"]["netIncome"] == "NetIncomeLoss"
    assert reading["fieldsFound"]["assets"] == "Assets"


def test_finnhub_an_error_object_is_an_error_not_an_empty_result():
    reading = P.read_finnhub({"error": "You don't have access to this resource."})
    assert reading["errorBody"] == "You don't have access to this resource."
    assert "rowCount" not in reading


def test_polygon_filing_date_and_nested_financials_are_read():
    payload = {"results": [{"end_date": "2012-09-29", "filing_date": "2012-10-31",
                            "financials": {"income_statement": {
                                "NetIncomeLoss": {"value": 41733}}}}]}
    reading = P.read_polygon(payload)
    assert reading["filingDates"] == ["2012-10-31"]
    assert reading["filingDateField"] == "filing_date"
    assert reading["fieldsFound"]["netIncome"] == "NetIncomeLoss"


def test_polygon_an_error_status_is_read_from_the_body_not_the_http_code():
    reading = P.read_polygon({"status": "ERROR", "error": "Unknown API Key"})
    assert reading["errorBody"] == "Unknown API Key"


def test_simfin_column_oriented_rows_are_zipped_to_their_column_names():
    payload = [{"ticker": "AAPL", "statements": [
        {"statement": "PL",
         "columns": ["Ticker", "Report Date", "Publish Date", "Revenue"],
         "data": [["AAPL", "2012-09-29", "2012-10-31", 156508]]}]}]
    reading = P.read_simfin(payload)
    assert reading["periodEnds"] == ["2012-09-29"]
    assert reading["filingDates"] == ["2012-10-31"]
    assert reading["filingDateField"] == "publishdate"
    assert reading["fieldsFound"]["revenue"] == "revenue"


def test_fmp_accepts_both_spellings_of_the_filing_date():
    """`/api/v3` shipped `fillingDate` for years; `/stable` corrected it. A
    reader that knows one spelling reports "no point-in-time" about a response
    carrying it in every row."""
    stable = P.read_fmp([{"date": "2012-09-29", "filingDate": "2012-10-31"}])
    legacy = P.read_fmp([{"date": "2012-09-29", "fillingDate": "2012-10-31"}])
    assert stable["filingDateField"] == "filingDate"
    assert legacy["filingDateField"] == "fillingDate"
    assert stable["filingDates"] == legacy["filingDates"] == ["2012-10-31"]


def test_alphavantage_is_measured_for_the_absence_of_a_publication_date():
    reading = P.read_alphavantage(
        {"quarterlyReports": [{"fiscalDateEnding": "2012-09-29", "totalRevenue": "156508"}]})
    assert reading["filingDates"] == [None]
    assert reading["filingDateField"] is None
    assert P.assess_window(reading, takes_date_window=False)["depth"] == P.NO_FILING_DATE


def test_alphavantage_rate_limit_note_is_an_error_body_not_an_empty_result():
    reading = P.read_alphavantage({"Information": "rate limit is 25 requests per day"})
    assert "25 requests per day" in reading["errorBody"]


def test_a_field_present_but_always_null_is_reported_missing():
    rows = [{"revenue": None}, {"revenue": ""}]
    assert P._first_populated(rows, ["revenue"]) is None


def test_the_second_candidate_answers_when_the_first_is_never_populated():
    rows = [{"totalStockholdersEquity": None, "totalEquity": 5}]
    assert P._first_populated(rows, ["totalStockholdersEquity", "totalEquity"]) == "totalEquity"


# --------------------------------------------------------------------------- #
# Factors do not degrade gracefully: bookYield without a share count is an
# absent bookYield, not a weaker one
# --------------------------------------------------------------------------- #
def test_a_factor_missing_one_input_is_not_computable():
    served = [{"fieldsFound": {"equity": "StockholdersEquity", "sharesOutstanding": None}}]
    readiness = P.factor_readiness(served)
    assert readiness["value · bookYield"]["computable"] is False
    assert readiness["value · bookYield"]["missing"] == ["sharesOutstanding"]


def test_fields_are_pooled_across_the_samples_that_were_served():
    served = [{"fieldsFound": {"netIncome": "NetIncomeLoss"}},
              {"fieldsFound": {"equity": "StockholdersEquity"}}]
    readiness = P.factor_readiness(served)
    assert readiness["quality · roe"]["computable"] is True


def test_every_production_value_and_quality_factor_is_covered():
    """The 0.3 value + 0.2 quality that has never been tested in the US is
    exactly what this probe has to answer for."""
    needed = {"value · earningsYield", "value · bookYield", "value · fcfYield",
              "quality · roe", "quality · opMargin", "quality · profitMargin",
              "quality · debtToEquity"}
    assert needed <= set(P.FACTOR_INPUTS)


# --------------------------------------------------------------------------- #
# The samples and the size come from the replay's own membership file
# --------------------------------------------------------------------------- #
def _history(tmp_path):
    history = tmp_path / "universe-history.json"
    history.write_text(json.dumps({
        # `AA` sorts first alphabetically and left the universe LAST — and it
        # is the real trap: Alcoa still trades under that ticker, so an
        # alphabetical cohort leads with a name that is not gone at all.
        "AA":   {"listed": "2012-12-27", "delisted": "2017-03-08", "region": "US"},
        "SHLD": {"listed": "2012-12-27", "delisted": "2014-10-15", "region": "US"},
        "ANR":  {"listed": "2012-12-27", "delisted": "2013-05-05", "region": "US"},
        "NEWCO": {"listed": "2021-01-04", "delisted": "2023-01-04", "region": "US"},
        "AAPL": {"listed": "2012-12-27", "delisted": None, "region": "US"},
        "005930.KS": {"listed": "2012-12-27", "delisted": "2019-01-01", "region": "KR"},
    }))
    return history


def test_departed_samples_are_names_the_replay_held_before_it_starts(tmp_path):
    picked = P.departed_samples(_history(tmp_path), count=4)
    assert "NEWCO" not in picked, "리플레이 시작 뒤 상장한 이름은 깊이를 말해주지 못한다"
    assert "AAPL" not in picked, "아직 유니버스에 있는 이름은 이 코호트가 아니다"
    assert "005930.KS" not in picked, "미국 코호트에 한국 이름이 섞이면 안 된다"


def test_departed_samples_lead_with_the_names_that_left_earliest(tmp_path):
    """Alphabetical order put AA — a ticker that still trades — at the head of
    a cohort whose whole job is to ask about names that are gone."""
    picked = P.departed_samples(_history(tmp_path), count=3)
    assert picked == ["ANR", "SHLD", "AA"]
    assert picked[0] == "ANR", "가장 먼저 떠난 이름이 앞에 와야 한다"


def test_departed_samples_stay_stable_across_runs(tmp_path):
    assert P.departed_samples(_history(tmp_path), count=2) == \
        P.departed_samples(_history(tmp_path), count=2)


def test_departed_samples_fall_back_rather_than_crash_on_a_missing_file(tmp_path):
    assert P.departed_samples(tmp_path / "absent.json") == list(P.DEFAULT_DEPARTED)


def test_the_backfill_is_sized_off_every_name_that_was_ever_a_member():
    """Sizing off today's 70-name list under-orders by an order of magnitude
    and rebuilds the survivorship hole while doing it."""
    live = P.us_universe_size()
    assert live > 500, f"누적 미국 멤버가 {live}개로 읽혔다 — 현재 구성종목을 센 것 아닌가"


def test_backfill_cost_reports_calls_and_refuses_to_invent_a_duration():
    cost = P.backfill_cost(P.VENDORS["finnhub"], 829)
    assert cost["callsForFullBackfill"] == cost["callsPerTicker"] * 829
    assert "측정하지" in cost["rateLimit"]


# --------------------------------------------------------------------------- #
# The vendor table itself
# --------------------------------------------------------------------------- #
def test_every_vendor_can_be_reached_for_without_a_credential():
    """Reachability must be answerable even when nobody has a key, or a run
    with no secrets reports nothing at all."""
    for name, vendor in P.VENDORS.items():
        assert vendor["reachUrl"], name
        assert "apikey" not in vendor["reachUrl"].lower(), \
            f"{name} 의 도달성 확인에 키가 섞여 있다"
        assert "token=" not in vendor["reachUrl"].lower(), name


def test_every_vendor_offers_candidate_requests_rather_than_one_assumed_shape():
    for name, vendor in P.VENDORS.items():
        candidates = vendor["requests_for"]("AAPL", "KEY", "2012-01-01", "2013-06-30")
        assert candidates, name
        labels = [label for label, _, _ in candidates]
        assert len(labels) == len(set(labels)), f"{name} 후보 라벨이 중복이다"


def test_the_credential_reaches_every_candidate_request():
    for name, vendor in P.VENDORS.items():
        for label, url, headers in vendor["requests_for"](
                "AAPL", "SENTINEL", "2012-01-01", "2013-06-30"):
            carried = "SENTINEL" in url or any("SENTINEL" in str(v) for v in headers.values())
            assert carried, f"{name}/{label} 이 키를 싣지 않는다"


def test_the_window_is_asked_for_by_date_where_the_vendor_takes_one():
    for name, vendor in P.VENDORS.items():
        if not vendor["takesDateWindow"]:
            continue
        for label, url, _ in vendor["requests_for"](
                "AAPL", "KEY", "2012-01-01", "2013-06-30"):
            assert "2012-01-01" in url, f"{name}/{label} 이 시작일을 보내지 않는다"


def test_the_probe_window_ends_before_the_replay_starts_plus_a_quarter():
    """A source that reaches 2016 does not close a replay that starts in 2013,
    and an answer in years cannot tell the two apart."""
    assert P.WINDOW_START < P.REPLAY_START <= P.WINDOW_END


def test_the_replay_start_matches_the_calendar_the_replay_actually_uses():
    """The probe copies the constant to stay importable without pandas; this
    is what stops the copy from drifting."""
    from pipeline.replay_calendar import ORIGIN
    assert P.REPLAY_START == ORIGIN


def test_sec_targets_keep_the_known_refused_hosts_as_the_baseline():
    """Without the baseline in the same run, a new host answering would be
    attributable to the day rather than to the host."""
    hosts = [host for host, _, _ in P.SEC_TARGETS]
    assert "data.sec.gov" in hosts and "www.sec.gov" in hosts
    assert "efts.sec.gov" in hosts, "한 번도 묻지 않은 호스트가 있으면 SEC는 아직 다 측정되지 않았다"


def test_sec_requests_send_the_policy_compliant_header_set():
    assert P.SEC_HEADERS["Accept-Encoding"] == "gzip, deflate"
    assert "@" in P.SEC_HEADERS["User-Agent"]


# --------------------------------------------------------------------------- #
# Candidate requests — the URL shape and how the credential is presented are
# both variables, and KRX's transport was inferred from an error string and
# inferred wrong
# --------------------------------------------------------------------------- #
def _scripted_requests(script):
    """Replaces P._request with a canned (status, body) per call, in order."""
    calls = []

    def fake(url, headers=None, timeout=30):
        calls.append((url, headers or {}))
        status, body = script[min(len(calls) - 1, len(script) - 1)]
        return status, body, "" if status == 200 else f"HTTP {status}"

    return fake, calls


def _vendor(takes_window=True):
    return {"takesDateWindow": takes_window, "read": P.read_finnhub,
            "requests_for": lambda t, key, start, end: [
                ("first", f"https://example.test/a?token={key}", {}),
                ("second", "https://example.test/b", {"X-Token": key}),
            ]}


_ROW = (b'{"data": [{"endDate": "2012-09-29", "filedDate": "2012-10-31", '
        b'"report": {"ic": [{"concept": "NetIncomeLoss", "value": 1}]}}]}')


def test_an_empty_first_candidate_does_not_stop_the_second_being_asked(monkeypatch):
    """An auth form that does not take looks exactly like a company with no
    filings. Stopping on the empty answer would report "no 2013 rows" about a
    transport we simply presented wrong."""
    fake, calls = _scripted_requests([(200, b'{"data": []}'), (200, _ROW)])
    monkeypatch.setattr(P, "_request", fake)
    monkeypatch.setattr(P.time, "sleep", lambda *_: None)
    result = P.probe_sample(_vendor(), "AAPL", "KEY")
    assert len(calls) == 2
    assert result["servedBy"] == "second"
    assert result["depth"] == P.PIT_DEPTH_CONFIRMED


def test_a_confirmed_first_candidate_stops_the_run_instead_of_spending_quota(monkeypatch):
    fake, calls = _scripted_requests([(200, _ROW), (200, _ROW)])
    monkeypatch.setattr(P, "_request", fake)
    monkeypatch.setattr(P.time, "sleep", lambda *_: None)
    result = P.probe_sample(_vendor(), "AAPL", "KEY")
    assert len(calls) == 1, "확정된 뒤에도 계속 물으면 쿼터만 씁니다"
    assert result["servedBy"] == "first"


def test_every_candidates_refusal_body_is_kept(monkeypatch):
    fake, _ = _scripted_requests([
        (401, b'{"error": "Invalid API key"}'),
        (403, b'{"error": "You do not have access to this resource"}'),
    ])
    monkeypatch.setattr(P, "_request", fake)
    monkeypatch.setattr(P.time, "sleep", lambda *_: None)
    result = P.probe_sample(_vendor(), "AAPL", "KEY")
    assert result["servedBy"] is None
    assert result["depth"] == P.REFUSED
    bodies = " ".join(str(a.get("detail", "")) for a in result["attempts"])
    assert "Invalid API key" in bodies and "do not have access" in bodies


def test_the_most_informative_answer_wins_when_none_is_confirmed(monkeypatch):
    """A refusal and an answered-but-shallow response are not equal findings,
    and reporting the last one asked would make the order decide."""
    recent = (b'{"data": [{"endDate": "2026-06-30", "filedDate": "2026-07-31", '
              b'"report": {}}]}')
    fake, _ = _scripted_requests([(200, recent), (401, b'{"error": "no"}')])
    monkeypatch.setattr(P, "_request", fake)
    monkeypatch.setattr(P.time, "sleep", lambda *_: None)
    result = P.probe_sample(_vendor(), "AAPL", "KEY")
    assert result["depth"] == P.WINDOW_NOT_HONOURED
    assert result["servedBy"] == "first"


# --------------------------------------------------------------------------- #
# Depth and a filing date are not the same claim as usable numbers — run #1
# called polygon OPEN while finding none of the nine production accounts in it
# --------------------------------------------------------------------------- #
def _readiness(**found):
    served = [{"fieldsFound": found, "fieldsSeen": ["net_income_loss", "revenues"]}]
    return P.factor_readiness(served)


def test_depth_without_a_single_computable_factor_is_not_an_open_route():
    verdict = P.vendor_verdict(P.ANSWERED, True,
                               living={"AAPL": _confirmed()},
                               departed={"ANR": _confirmed()},
                               accounts=_readiness())
    assert verdict["verdict"] == P.ACCOUNTS_NOT_FOUND
    assert verdict["verdict"] != P.OPEN, "계산할 수 없는 소스로 수집기를 쓰게 하면 안 된다"


def test_the_vendors_own_field_names_ride_along_so_the_next_move_is_visible():
    verdict = P.vendor_verdict(P.ANSWERED, True,
                               living={"AAPL": _confirmed()},
                               departed={"ANR": _confirmed()},
                               accounts=_readiness())
    assert "net_income_loss" in verdict["fieldsSeen"], \
        "못 찾은 이름만 말하고 실제로 온 이름을 숨기면 다음 수가 안 보인다"


def test_accounts_that_compute_at_least_one_factor_still_open_the_route():
    verdict = P.vendor_verdict(
        P.ANSWERED, True,
        living={"AAPL": _confirmed()}, departed={"ANR": _confirmed()},
        accounts=_readiness(netIncome="NetIncomeLoss", equity="StockholdersEquity"))
    assert verdict["verdict"] == P.OPEN


def test_a_vendor_probed_without_an_accounts_reading_is_judged_as_before():
    """`accounts=None` means the caller did not measure them; that is not the
    same as measuring them and finding none."""
    verdict = P.vendor_verdict(P.ANSWERED, True,
                               living={"AAPL": _confirmed()},
                               departed={"ANR": _confirmed()}, accounts=None)
    assert verdict["verdict"] == P.OPEN


# --------------------------------------------------------------------------- #
# An empty answer is a refusal wearing a 200 — the control window is what tells
# "no such history" from "you did not understand the question"
# --------------------------------------------------------------------------- #
def test_an_empty_history_with_an_empty_control_indicts_our_request():
    """simfin answered all eight samples with zero rows, AAPL included, and
    that was written up as the vendor being shallow."""
    verdict = P.vendor_verdict(P.ANSWERED, True,
                               living={"AAPL": _empty(), "KO": _empty()},
                               departed={"ANR": _empty()},
                               control={"depth": P.NO_ROWS, "detail": "행이 없음"})
    assert verdict["verdict"] == P.REQUEST_NOT_RULED_OUT
    assert verdict["verdict"] != P.TOO_SHALLOW


def test_an_empty_history_with_a_served_control_is_genuinely_shallow():
    verdict = P.vendor_verdict(P.ANSWERED, True,
                               living={"AAPL": _empty()}, departed={"ANR": _empty()},
                               control={"depth": P.PIT_DEPTH_CONFIRMED})
    assert verdict["verdict"] == P.TOO_SHALLOW


def test_without_a_control_an_empty_history_stays_the_cautious_old_verdict():
    verdict = P.vendor_verdict(P.ANSWERED, True,
                               living={"AAPL": _empty()}, departed={"ANR": _empty()})
    assert verdict["verdict"] == P.TOO_SHALLOW


def test_a_refused_control_also_indicts_our_side():
    verdict = P.vendor_verdict(P.ANSWERED, True,
                               living={"AAPL": _empty()}, departed={"ANR": _empty()},
                               control={"depth": P.REFUSED, "detail": "bad request"})
    assert verdict["verdict"] == P.REQUEST_NOT_RULED_OUT


def test_the_control_window_is_one_where_the_answer_is_not_in_doubt():
    assert P.CONTROL_START > P.WINDOW_END, "대조 창은 최근이어야 한다"
    assert P.CONTROL_START < P.CONTROL_END


# --------------------------------------------------------------------------- #
# A renamed field reads as an absent one — so report what actually arrived
# --------------------------------------------------------------------------- #
def test_polygon_normalised_statement_keys_are_candidates_too():
    """run #1 looked only for the filer's US-GAAP tags and found none of the
    nine accounts in four tickers that had each returned six periods."""
    payload = {"results": [{"end_date": "2012-09-29", "filing_date": "2012-10-31",
                            "financials": {"income_statement": {
                                "net_income_loss": {"value": 41733},
                                "revenues": {"value": 156508}}}}]}
    reading = P.read_polygon(payload)
    assert reading["fieldsFound"]["netIncome"] == "net_income_loss"
    assert reading["fieldsFound"]["revenue"] == "revenues"


def test_polygon_still_reads_the_filers_own_tag_when_that_is_what_arrives():
    payload = {"results": [{"end_date": "2012-09-29", "filing_date": "2012-10-31",
                            "financials": {"income_statement": {
                                "NetIncomeLoss": {"value": 41733}}}}]}
    assert P.read_polygon(payload)["fieldsFound"]["netIncome"] == "NetIncomeLoss"


def test_every_reader_reports_the_field_names_it_actually_saw():
    polygon = P.read_polygon({"results": [{"end_date": "2012-09-29",
                                           "filing_date": "2012-10-31",
                                           "financials": {"x": {"mystery_key":
                                                                {"value": 1}}}}]})
    assert "mystery_key" in polygon["fieldsSeen"], \
        "벤더가 보낸 이름을 기록하지 않으면 '없음'과 '이름이 다름'을 구분할 수 없다"

    finnhub = P.read_finnhub({"data": [{"endDate": "2012-09-29",
                                        "filedDate": "2012-10-31",
                                        "report": {"ic": [{"concept": "OddTag",
                                                           "value": 1}]}}]})
    assert "OddTag" in finnhub["fieldsSeen"]

    fmp = P.read_fmp([{"date": "2012-09-29", "filingDate": "2012-10-31",
                       "surpriseField": 1}])
    assert "surpriseField" in fmp["fieldsSeen"]


def test_the_seen_field_list_is_capped_so_a_report_stays_readable():
    rows = [{f"field_{i}": i for i in range(200)} | {"date": "2012-09-29",
                                                     "filingDate": "2012-10-31"}]
    assert len(P.read_fmp(rows)["fieldsSeen"]) <= P.FIELDS_SEEN_CAP


def test_the_seen_fields_survive_into_the_readiness_report():
    served = [{"fieldsFound": {}, "fieldsSeen": ["net_income_loss"]}]
    assert P.factor_readiness(served)["_fieldsSeen"] == ["net_income_loss"]
