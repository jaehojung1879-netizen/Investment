"""US total-assets source feasibility: the data contract, the bounded probe, and the fixed sample. No network, no key, no outcome."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from pipeline import us_total_assets_source as TA  # noqa: E402
import probe_us_total_assets_sources as P  # noqa: E402

SENTINEL = "SENTINEL-KEY-0123456789abcdef"
CONTACT = "ops@investor-diagnostics.test"
BLOCK_PAGE = b"<html><title>SEC.gov | Request Rate Threshold Exceeded</title>Your Request Originates from an Undeclared Automated Tool</html>"


def sample_filing(**over):
    base = {"id": "AAA|0000111111-26-000001", "group": "RECENTLY_MISSING", "ticker": "AAA", "cik": "111111", "accession": "0000111111-26-000001",
            "form": "10-Q", "periodEnd": "2026-06-30", "availableFrom": "2026-08-05", "storedAssets": None}
    base.update(over)
    return base


def concept_payload(rows, cik=111111):
    return {"cik": cik, "taxonomy": "us-gaap", "tag": "Assets", "entityName": "AAA Corp", "units": {"USD": rows}}


def fact(end, val, accn, filed, form="10-Q", fy=2026, fp="Q2"):
    return {"end": end, "val": val, "accn": accn, "fy": fy, "fp": fp, "form": form, "filed": filed}


# ---- HTTP meaning ------------------------------------------------------------------------------------------------------------------------
def test_sec_403_with_block_page_is_a_cdn_block_not_a_vendor_refusal():
    result = TA.classify_exchange("sec", 403, BLOCK_PAGE, None, None)
    assert result["category"] == TA.HTTP_403_SEC_BLOCK and result["evidence"]["blockMarker"]


def test_a_200_carrying_a_block_page_is_a_block_not_data():
    assert TA.classify_exchange("sec", 200, BLOCK_PAGE, None, True)["category"] == TA.HTTP_403_SEC_BLOCK


def test_status_categories_are_distinct():
    cats = {
        TA.classify_exchange("vendor", 200, b"{}", None, True)["category"],
        TA.classify_exchange("vendor", 200, b"{}", None, False)["category"],
        TA.classify_exchange("vendor", 401, b"{}", None, None)["category"],
        TA.classify_exchange("vendor", 402, b"{}", None, None)["category"],
        TA.classify_exchange("vendor", 403, b'{"error":"You don\'t have access to this resource."}', None, None)["category"],
        TA.classify_exchange("vendor", 429, b"{}", None, None)["category"],
        TA.classify_exchange("vendor", 500, b"{}", None, None)["category"],
        TA.classify_exchange("vendor", None, b"", "network", None)["category"],
        TA.classify_exchange("vendor", None, b"", "proxy", None)["category"],
    }
    assert len(cats) == 9


def test_vendor_entitlement_sentence_is_kept_and_credentials_are_redacted():
    body = b'{"error":"You do not have access to this resource, upgrade your plan. apikey=abcdefgh12345678"}'
    evidence = TA.classify_exchange("vendor", 403, body, None, None)["evidence"]
    assert "upgrade" in evidence["entitlementSentence"] and "abcdefgh12345678" not in evidence["entitlementSentence"]


# ---- SEC contact -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("value,problem", [
    ("", "SEC_CONTACT_MISSING"), ("   ", "SEC_CONTACT_MISSING"), (None, "SEC_CONTACT_MISSING"), ("not-an-email", "SEC_CONTACT_NOT_AN_EMAIL_ADDRESS"),
    ("someone@users.noreply.github.com", "SEC_CONTACT_IS_A_PLACEHOLDER_OR_NOREPLY_ADDRESS"), ("a@example.com", "SEC_CONTACT_IS_A_PLACEHOLDER_OR_NOREPLY_ADDRESS"),
    ("a b@x.org", "SEC_CONTACT_NOT_AN_EMAIL_ADDRESS")])
def test_sec_contact_is_never_invented_or_accepted_as_a_placeholder(value, problem):
    assert TA.sec_contact_problem(value) == problem
    with pytest.raises(ValueError):
        TA.sec_user_agent(value or "")


def test_user_agent_carries_exactly_the_contact_given():
    assert CONTACT in TA.sec_user_agent(CONTACT)


# ---- identity and point-in-time ----------------------------------------------------------------------------------------------------------
def test_exact_accession_from_sec_is_pit_proven_and_visible_only_from_its_own_filing_date():
    read = TA.read_sec_company_concept(concept_payload([
        fact("2026-06-30", 9_000_000_000, "0000111111-26-000001", "2026-08-05"),
        fact("2026-06-30", 9_100_000_000, "0000111111-27-000002", "2027-02-10", form="10-K", fy=2026, fp="FY"),  # a later filing repeating the period
    ]))
    assert read["valid"]
    check = TA.check_filing(sample_filing(), read["observations"], "2026-10-12T00:00:00Z")
    assert check["identity"] == TA.EXACT_ACCESSION and check["pit"] == TA.PIT_PROVEN
    assert check["totalAssets"] == 9_000_000_000, "the later filing's restated comparative must not replace the original"
    assert check["distinctAccessionsForPeriodEnd"] == 2 and check["correctionsDistinguishable"]
    assert not TA.visible_at(check, "2026-08-04") and TA.visible_at(check, "2026-08-05")
    assert check["observedAt"] == "2026-10-12T00:00:00Z"


def test_an_observation_made_today_is_not_availability_for_a_historical_signal_date():
    read = TA.read_sec_company_concept(concept_payload([fact("2026-06-30", 1, "0000111111-26-000001", "2026-08-05")]))
    check = TA.check_filing(sample_filing(), read["observations"], "2099-01-01T00:00:00Z")
    assert not TA.visible_at(check, "2026-06-30")


def test_vendor_without_accession_has_only_a_weak_identity_and_no_pit_claim():
    obs = [TA.observation("massive_balance_sheets", cik=111111, ticker="AAA", periodEnd="2026-06-30", filedDate="2026-08-05", totalAssets=5.0,
                          filingDateSemantics="DOCUMENTED_LATEST_FILING_INCLUDING_PERIOD")]
    check = TA.check_filing(sample_filing(), obs, "t")
    assert check["identity"] == TA.WEAK_CIK_PERIOD_END and check["pit"] == TA.PIT_NO_ACCESSION and not check["usableAsOriginalAtFilingDate"]
    assert not TA.visible_at(check, "2030-01-01")


def test_vendor_filing_date_that_differs_from_the_original_is_flagged_not_original():
    obs = [TA.observation("massive_balance_sheets", cik=111111, periodEnd="2026-06-30", filedDate="2027-02-10", totalAssets=5.0)]
    assert TA.check_filing(sample_filing(), obs, "t")["pit"] == TA.PIT_NOT_ORIGINAL


def test_ticker_only_or_period_only_never_joins():
    only_ticker = TA.observation("x", ticker="AAA", totalAssets=1.0)
    only_period = TA.observation("x", periodEnd="2026-06-30", totalAssets=1.0)
    other_cik_same_period = TA.observation("x", cik=999, periodEnd="2026-06-30", totalAssets=1.0)
    for obs in (only_ticker, only_period, other_cik_same_period):
        check = TA.check_filing(sample_filing(), [obs], "t")
        assert check["identity"] == TA.REJECTED_IDENTITY and check["pit"] == TA.PIT_NO_MATCH


def test_a_conflicting_accession_is_rejected_even_when_cik_and_period_match():
    obs = [TA.observation("x", cik=111111, periodEnd="2026-06-30", accession="0000111111-26-000009", filedDate="2026-08-05", totalAssets=1.0)]
    assert TA.check_filing(sample_filing(), obs, "t")["identity"] == TA.REJECTED_IDENTITY


def test_exact_accession_with_a_different_filing_date_is_a_conflict():
    obs = TA.read_sec_company_concept(concept_payload([fact("2026-06-30", 1, "0000111111-26-000001", "2026-08-06")]))["observations"]
    assert TA.check_filing(sample_filing(), obs, "t")["pit"] == TA.PIT_DATE_CONFLICT


def test_value_comparison_against_the_stored_reported_assets():
    obs = TA.read_sec_company_concept(concept_payload([fact("2026-06-30", 12_813_000_000, "0000111111-26-000001", "2026-08-05")]))["observations"]
    assert TA.check_filing(sample_filing(storedAssets=12_813_000_000.0), obs, "t")["valueEqualsStoredReported"] is True
    assert TA.check_filing(sample_filing(storedAssets=12_000_000_000.0), obs, "t")["valueEqualsStoredReported"] is False
    assert TA.check_filing(sample_filing(storedAssets=None), obs, "t")["valueEqualsStoredReported"] is None


def test_readers_reject_the_wrong_shape_instead_of_inventing_rows():
    assert not TA.read_sec_company_concept({"tag": "Liabilities", "taxonomy": "us-gaap", "units": {"USD": []}})["valid"]
    assert not TA.read_sec_company_concept([])["valid"]
    assert not TA.read_sec_company_facts({"facts": {"dei": {}}})["valid"]
    assert not TA.read_finnhub_standardized({"error": "You don't have access to this resource."})["valid"]
    assert not TA.read_massive_balance_sheets({"status": "NOT_AUTHORIZED", "message": "not entitled"})["valid"]
    assert not TA.read_fmp_balance_sheet({"Error Message": "limit"})["valid"]
    assert not TA.read_sec_ticker_file({"0": {"cik_str": 1, "ticker": "A", "title": "A"}})["valid"], "a handful of rows is not the ticker file"


def test_company_facts_reader_reads_only_us_gaap_assets():
    payload = {"cik": 111111, "entityName": "AAA", "facts": {"us-gaap": {"Assets": {"units": {"USD": [fact("2026-06-30", 7, "0000111111-26-000001", "2026-08-05")]}},
                                                                         "Liabilities": {"units": {"USD": [fact("2026-06-30", 3, "0000111111-26-000001", "2026-08-05")]}}}}}
    read = TA.read_sec_company_facts(payload)
    assert [o["totalAssets"] for o in read["observations"]] == [7.0]


def test_finnhub_standardized_reader_records_which_field_answered_and_stated_provenance():
    payload = {"symbol": "AAA", "cik": "111111", "data": [
        {"period": "2026-06-30", "year": 2026, "quarter": 2, "v": [{"concept": "us-gaap_Assets", "label": "Total assets", "unit": "usd", "value": 9.0}]}]}
    read = TA.read_finnhub_standardized(payload, "AAA")
    obs = read["observations"][0]
    assert read["valid"] and obs["totalAssets"] == 9.0 and obs["fieldUsed"].startswith("v[") and obs["accession"] is None and obs["filedDate"] is None
    assert TA.check_filing(sample_filing(), [obs], "t")["pit"] == TA.PIT_NO_ACCESSION


def test_fmp_accession_is_read_from_the_sec_link_when_present():
    payload = [{"symbol": "AAA", "cik": "0000111111", "date": "2026-06-30", "filingDate": "2026-08-05", "acceptedDate": "2026-08-05 16:00:00",
                "totalAssets": 5, "reportedCurrency": "USD", "period": "Q2", "fiscalYear": "2026",
                "finalLink": "https://www.sec.gov/Archives/edgar/data/111111/000011111126000001/0000111111-26-000001-index.htm"}]
    obs = TA.read_fmp_balance_sheet(payload)["observations"][0]
    assert obs["accession"] == "0000111111-26-000001" and obs["currency"] == "USD"
    assert TA.check_filing(sample_filing(), [obs], "t")["pit"] == TA.PIT_PROVEN


def test_a_company_that_changed_cik_is_not_joined_by_ticker():
    # APA Corp (1841666) is the successor to Apache (6769): the same ticker spans two CIKs, so a ticker-only join would cross filers.
    old = TA.observation("x", cik=6769, ticker="APA", periodEnd="2021-03-31", totalAssets=1.0)
    check = TA.check_filing(sample_filing(ticker="APA", cik="1841666", periodEnd="2021-03-31"), [old], "t")
    assert check["identity"] == TA.REJECTED_IDENTITY


# ---- the fixed sample --------------------------------------------------------------------------------------------------------------------
def test_sample_is_sealed_small_and_covers_every_group_without_amendments():
    sample = P.load_sample()
    assert sample["digest"] == P.digest_of(sample)
    assert len(sample["probeTickers"]) == 8 and len(sample["filings"]) == 32 and not sample["shortfall"]
    groups = {f["group"] for f in sample["filings"]}
    assert groups == {"RECENTLY_MISSING", "RECENT_COMPLETE", "HISTORICAL_EARLIEST", "HISTORICAL_ANNUAL"}
    assert len({f["id"] for f in sample["filings"]}) == 32
    for f in sample["filings"]:
        assert TA.normalize_accession(f["accession"]) == f["accession"] and f["cik"] and f["availableFrom"] >= f["periodEnd"]
        assert (f["storedAssets"] is None) == (f["group"] == "RECENTLY_MISSING")
    assert sample["populationFacts"]["amendmentForms"] == 0, "the store has no amendment forms, so correction handling cannot be tested on stored filings"


# ---- the plan ----------------------------------------------------------------------------------------------------------------------------
def test_plan_is_deterministic_bounded_and_keyless():
    sample = P.load_sample()
    plan_a, plan_b = P.plan_requests(sample, list(P.SOURCES), 20), P.plan_requests(sample, list(P.SOURCES), 20)
    assert plan_a == plan_b
    assert len(plan_a["sec"]) == 1 + 8 + 2 and len(plan_a["finnhub"]) == 8 and len(plan_a["massive"]) == 8 and len(plan_a["fmp"]) == 9
    assert all(len(v) <= P.HARD_CEILING for v in plan_a.values())
    assert plan_a["sec"][0]["host"] == "www.sec.gov"
    assert {r["host"] for r in plan_a["sec"]} == {"www.sec.gov", "data.sec.gov"}
    text = json.dumps(plan_a)
    assert "apikey" not in text.lower() and "token" not in text.lower()
    assert all("/vX/" not in r["url"] for v in plan_a.values() for r in v), "Massive's sunset financials endpoint is never used"
    assert len(P.plan_requests(sample, ["sec"], 3)["sec"]) == 3
    assert P.plan_requests(sample, list(P.SOURCES), 0) == {s: [] for s in P.SOURCES}
    assert len(P.plan_requests(sample, ["sec"], 99)["sec"]) <= P.HARD_CEILING


def never_called(*_a, **_k):
    raise AssertionError("a request was made")


def test_plan_only_makes_no_request_needs_no_key_or_contact():
    report = P.run(P.load_sample(), list(P.SOURCES), 0, contact=None, env={}, transport=never_called)
    assert report["mode"] == "PLAN_ONLY"
    assert all(v["verdict"] == "PENDING_OWNER_DISPATCH" for v in report["sources"].values())
    assert report["sources"]["sec"]["plannedRequests"] and report["secUserAgentContactSupplied"] is False


# ---- live paths against a fake transport -------------------------------------------------------------------------------------------------
class Fake:
    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def __call__(self, request, headers):
        self.calls.append((request, headers))
        status, body = self.handler(request, headers)
        return {"status": status, "body": body, "truncated": False, "errorKind": None, "errorText": "", "elapsedMs": 1, "contentType": "application/json"}


def sec_all_blocked(_r, _h):
    return 403, BLOCK_PAGE


def run_live(sources, handler, env=None, contact=CONTACT, max_calls=20):
    fake = Fake(handler)
    report = P.run(P.load_sample(), sources, max_calls, contact=contact, env=env or {}, transport=fake, sleep=lambda _s: None)
    return report, fake


def test_sec_blocked_everywhere_is_reported_as_blocked_and_hosts_stop_after_two_pages():
    report, fake = run_live(["sec"], sec_all_blocked)
    sec = report["sources"]["sec"]
    assert sec["verdict"] == "SEC_BLOCK_PERSISTS_ON_ACTIONS_RUNNER" and set(sec["hostsBlocked"]) == {"www.sec.gov", "data.sec.gov"}
    hits = {}
    for request, _ in fake.calls:
        hits[request["host"]] = hits.get(request["host"], 0) + 1
    assert hits["data.sec.gov"] == P.SEC_BLOCK_STOP_AFTER and hits["www.sec.gov"] == 1, "no aggressive retries after a block page"
    assert any(r["category"] == TA.SKIPPED_AFTER_BLOCK for r in sec["requests"])
    assert report["secBlockCleared"]["claim"] is False


def test_sec_block_is_only_cleared_by_a_live_200_with_valid_data_from_the_data_host():
    sample = P.load_sample()
    by_cik = {f["cik"]: f for f in sample["filings"] if f["group"] == "RECENTLY_MISSING"}

    def handler(request, _h):
        if request["kind"] == "SEC_WWW_SMALL_RESOURCE":
            return 200, json.dumps({str(i): {"cik_str": i, "ticker": f"T{i}", "title": "x"} for i in range(1500)}).encode()
        f = by_cik[request["cik"]]
        rows = [fact(f["periodEnd"], 123, f["accession"], f["availableFrom"]), fact(f["periodEnd"], 124, "0000000000-99-000001", "2030-01-01", form="10-K")]
        payload = concept_payload(rows, cik=int(request["cik"]))
        if request["kind"] == "SEC_COMPANYFACTS":
            payload = {"cik": int(request["cik"]), "facts": {"us-gaap": {"Assets": {"units": {"USD": rows}}}}}
        return 200, json.dumps(payload).encode()

    report, _ = run_live(["sec"], handler)
    sec = report["sources"]["sec"]
    assert sec["verdict"] == "SEC_DATA_HOST_REACHABLE" and sec["wwwReachable"] and report["secBlockCleared"]["claim"] is True
    assert sec["summary"]["byGroup"]["RECENTLY_MISSING"]["pitProven"] == 8
    assert all(c["usableAsOriginalAtFilingDate"] for c in report["checks"]["sec"] if c["group"] == "RECENTLY_MISSING")


def test_sec_not_run_without_a_valid_contact_and_makes_no_request():
    for contact in (None, "", "x@users.noreply.github.com"):
        report, fake = run_live(["sec"], never_called, contact=contact)
        assert report["sources"]["sec"]["verdict"] == "NOT_RUN" and not fake.calls


def test_vendor_without_its_key_is_not_run():
    report, fake = run_live(["finnhub", "massive", "fmp"], never_called, env={})
    assert all(v["verdict"] == "NOT_RUN" for v in report["sources"].values()) and not fake.calls


def test_entitlement_refusal_stops_the_vendor_after_the_first_request_and_keeps_the_sentence():
    def handler(_r, _h):
        return 403, b'{"error":"You don\'t have access to this resource."}'
    report, fake = run_live(["finnhub"], handler, env={"FINNHUB_API_KEY": SENTINEL})
    entry = report["sources"]["finnhub"]
    assert entry["verdict"] == "NOT_ENTITLED_ON_THIS_KEY" and "access" in entry["vendorSentence"]
    assert len(fake.calls) == 1 and sum(r["category"] == TA.SKIPPED_AFTER_BLOCK for r in entry["requests"]) == 7


def test_rate_limit_stops_the_vendor_and_is_not_a_coverage_finding():
    report, fake = run_live(["massive"], lambda _r, _h: (429, b'{"error":"slow down"}'), env={"MASSIVE_API_KEY": SENTINEL})
    assert report["sources"]["massive"]["verdict"] == "RATE_LIMITED_BEFORE_MEASURED" and len(fake.calls) == 1


def test_keys_travel_in_headers_or_the_fmp_query_and_never_into_the_report():
    def handler(request, headers):
        if request["kind"].startswith("FINNHUB"):
            assert headers["X-Finnhub-Token"] == SENTINEL
            return 200, json.dumps({"data": []}).encode()
        if request["kind"].startswith("MASSIVE"):
            assert headers["Authorization"] == f"Bearer {SENTINEL}"
            return 200, json.dumps({"results": []}).encode()
        assert request["queryKey"] == ("apikey", SENTINEL)
        return 200, b"[]"
    env = {"FINNHUB_API_KEY": SENTINEL, "MASSIVE_API_KEY": SENTINEL, "FMP_API_KEY": SENTINEL}
    report, _ = run_live(["finnhub", "massive", "fmp"], handler, env=env)
    assert SENTINEL not in json.dumps(report)
    assert all(v["verdict"] == "NO_VALID_RESPONSE" or v["verdict"].startswith("ACCESSIBLE") for v in report["sources"].values())


def test_leak_guard_refuses_a_report_that_contains_a_credential():
    assert P.leak_check(f"x {SENTINEL} y", [SENTINEL]) and not P.leak_check("clean", [SENTINEL])
    def handler(_r, _h):
        return 500, f'{{"message":"bad {SENTINEL}"}}'.encode()
    report, _ = run_live(["finnhub"], handler, env={"FINNHUB_API_KEY": SENTINEL})
    assert SENTINEL not in json.dumps(report), "the vendor sentence is scrubbed before it is recorded"


def test_fmp_depth_refusal_is_a_depth_answer_not_an_entitlement_stop():
    sample = P.load_sample()

    def handler(request, _h):
        if request["params"]["limit"] == "120":
            return 402, b'{"Error Message":"Premium Query Parameter: limit"}'
        ticker = request["ticker"]
        rows = [f for f in sample["filings"] if f["ticker"] == ticker and f["group"] == "RECENT_COMPLETE"]
        return 200, json.dumps([{"symbol": ticker, "cik": rows[0]["cik"], "date": rows[0]["periodEnd"], "filingDate": rows[0]["availableFrom"],
                                 "totalAssets": rows[0]["storedAssets"], "reportedCurrency": "USD",
                                 "finalLink": f"https://www.sec.gov/Archives/edgar/data/1/x/{rows[0]['accession']}-index.htm"}]).encode()

    report, fake = run_live(["fmp"], handler, env={"FMP_API_KEY": SENTINEL})
    entry = report["sources"]["fmp"]
    assert entry["stopped"] is None and len(fake.calls) == 9
    assert entry["requests"][1]["depthQuestion"] == "DEEP_WINDOW_REFUSED_PLAN_DEPTH_CAP"
    assert all(c[0]["params"]["limit"] == "5" for c in fake.calls[2:])
    assert entry["summary"]["byGroup"]["RECENT_COMPLETE"]["pitProven"] == 8
    assert entry["summary"]["byGroup"]["HISTORICAL_EARLIEST"]["matched"] == 0, "a 5-quarter window cannot reach the replay's first years"


def test_merge_combines_per_source_reports_without_a_request():
    a = {"mode": "LIVE", "sources": {"sec": {"verdict": "X"}}, "checks": {"sec": []}, "observedAt": "t"}
    b = {"mode": "LIVE", "sources": {"fmp": {"verdict": "Y"}}, "checks": {"fmp": []}}
    merged = P.merge_parts([a, b])
    assert set(merged["sources"]) == {"sec", "fmp"} and merged["observedAt"] == "t"


def test_probe_scripts_hold_no_default_credentials_or_inventions():
    text = (ROOT / "scripts/probe_us_total_assets_sources.py").read_text()
    pipeline_text = (ROOT / "pipeline/us_total_assets_source.py").read_text()
    assert "jaehojung" not in text and "jaehojung" not in pipeline_text, "no identity of the owner is written into code"


def test_merged_sec_block_status_is_recomputed_not_copied_from_the_first_part():
    vendors = {"mode": "LIVE", "sources": {"finnhub": {"verdict": "X"}}, "checks": {}, "secBlockCleared": {"claim": False, "basis": "stale"}}
    sec = {"mode": "LIVE", "sources": {"sec": {"verdict": "SEC_DATA_HOST_REACHABLE"}}, "checks": {}}
    assert P.merge_parts([vendors, sec])["secBlockCleared"]["claim"] is True
    assert P.merge_parts([sec, vendors])["secBlockCleared"]["claim"] is True
    assert P.merge_parts([vendors])["secBlockCleared"]["claim"] is False
    blocked = {"mode": "LIVE", "sources": {"sec": {"verdict": "SEC_BLOCK_PERSISTS_ON_ACTIONS_RUNNER"}}, "checks": {}}
    assert P.merge_parts([vendors, blocked])["secBlockCleared"]["claim"] is False
