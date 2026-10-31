import ast
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from pipeline import market_research_c1c_source_evidence as S
from pipeline import market_research_c1c_source_resolution as R


def _committed():
    return json.loads(R.OUTPUT.read_text())


def _chain():
    quotes, chain, endpoint = S.load_chain()
    return quotes, chain, endpoint, S.load_official_payments()


def _valid_source(event, **override):
    source = {"documentIdentifier": "KRX-DISCLOSURE-SYNTHETIC-0001", "url": "https://example.invalid/disclosure/1", "retrievedAtUtc": "2026-10-31T00:00:00Z",
              "sha256": "c" * 64, "paymentDate": str((pd.Timestamp(event["record"]) + pd.Timedelta(days=4)).date()), "taxableBasePerUnit": 100.0,
              "cashPerUnit": event["cash"], "origin": "OFFICIAL_PER_EVENT_DOCUMENT"}
    source.update(override)
    return source


def _event(record="2018-04-30", cash=200.0, holds=True):
    return {"record": pd.Timestamp(record), "cash": cash, "recordDateRuleHolds": holds}


def test_the_26_unresolved_events_are_exactly_the_chain_minus_the_official_ones_and_none_is_verified():
    quotes, chain, _, official = _chain()
    table = R.event_table(quotes, chain, official)
    expected = sorted(str(d.date()) for d in chain.record if d not in set(official.record))
    assert [r["recordDate"] for r in table] == expected and len(table) == 26
    assert all(r["paymentDate"] == "UNRESOLVED" and r["taxableBasePerUnit"] == "UNRESOLVED" for r in table)
    assert [r["status"] for r in table].count("VERIFIED") == 0
    assert sorted({r["status"] for r in table}) == ["PARTIAL_RECORD_RULE_ONLY", "PARTIAL_RULE_BOUNDED"]
    assert sum(r["status"] == "PARTIAL_RECORD_RULE_ONLY" for r in table) == 2      # the two 2012 events before the read notice chain


def test_all_46_record_dates_obey_the_deeds_last_session_of_jan_apr_jul_oct_rule():
    quotes, chain, _, _ = _chain()
    assert all(R.record_date_rule_holds(d, quotes.index) for d in chain.record)
    assert _committed()["events"]["recordDatesMatchingTheDeedRule"] == 46
    assert not R.record_date_rule_holds(pd.Timestamp("2018-04-27"), quotes.index)   # not the last session of April
    assert not R.record_date_rule_holds(pd.Timestamp("2018-05-31"), quotes.index)   # last session, wrong month


def test_a_verified_status_needs_an_official_per_event_document_with_exact_date_and_taxable_base():
    event = _event()
    assert R.classify_event(event) == "PARTIAL_RULE_BOUNDED"
    assert R.classify_event(event, _valid_source(event)) == "VERIFIED"           # the gate is not vacuous
    for missing in ("documentIdentifier", "url", "retrievedAtUtc", "sha256", "paymentDate", "taxableBasePerUnit", "origin"):
        with pytest.raises(ValueError, match="EVENT_SOURCE_INCOMPLETE:" + missing):
            R.classify_event(event, _valid_source(event, **{missing: None}))


@pytest.mark.parametrize("override,error", [
    ({"origin": "UNIFORM_LAG_PATTERN_INFERRED"}, "NOT_AN_OFFICIAL_PER_EVENT_DOCUMENT"),
    ({"origin": "THIRD_PARTY_TABLE"}, "NOT_AN_OFFICIAL_PER_EVENT_DOCUMENT"),
    ({"sha256": "abc"}, "HASH_INVALID"),
    ({"paymentDate": "2018-04-30"}, "PAYMENT_NOT_AFTER_RECORD_DATE"),
    ({"paymentDate": "2018-04-20"}, "PAYMENT_NOT_AFTER_RECORD_DATE"),
    ({"cashPerUnit": 150.0}, "CASH_DISAGREES_WITH_CHAIN"),
])
def test_unsupported_dates_inferred_origins_and_mismatched_cash_never_become_verified(override, error):
    event = _event()
    with pytest.raises(ValueError, match=error):
        R.classify_event(event, _valid_source(event, **override))


def test_taxable_base_cannot_be_taken_from_the_gross_cash_or_left_empty():
    event = _event()
    with pytest.raises(ValueError, match="EVENT_SOURCE_INCOMPLETE:taxableBasePerUnit"):
        R.classify_event(event, _valid_source(event, taxableBasePerUnit=0))        # a missing base is not "equal to cash"
    with pytest.raises(ValueError, match="EVENT_SOURCE_INCOMPLETE:taxableBasePerUnit"):
        R.classify_event(event, _valid_source(event, taxableBasePerUnit=None))


def test_a_record_date_that_violates_the_rule_is_unresolved_not_partial():
    assert R.classify_event(_event(holds=False)) == "UNRESOLVED"
    assert R.classify_event(_event(record="2012-04-30")) == "PARTIAL_RECORD_RULE_ONLY"   # before the read notice chain


def test_rule_bounded_interval_is_recomputed_and_never_wider_than_the_hypothetical_one():
    quotes, chain, endpoint, official = _chain()
    price = S.as_traded_prices(quotes, chain, endpoint)
    table = R.event_table(quotes, chain, official)
    out = R.rule_bounded_interval(price, chain, official, table)
    assert out == _committed()["trustDeed"]["ruleBoundedInterval"]
    hypothetical = S.timing_sensitivity(price, chain, official)["mixedLagScenarioWith20Known"]["signedInterval"]
    assert out["signedInterval"]["lowerPpPerYear"] >= hypothetical["lowerPpPerYear"] - 1e-9
    assert out["signedInterval"]["upperPpPerYear"] <= hypothetical["upperPpPerYear"] + 1e-9
    assert out["knownFixedPpPerYear"] == pytest.approx(-0.00819, abs=1e-5) and "NOT_CERTIFIED" in out["status"]


def test_committed_evidence_matches_a_fresh_build_up_to_float_noise():
    def close(a, b):
        if isinstance(a, dict):
            return a.keys() == b.keys() and all(close(a[k], b[k]) for k in a)
        if isinstance(a, list):
            return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
        if isinstance(a, float):
            return a == pytest.approx(b, abs=2e-5)
        return a == b
    assert close(R.build(), _committed())


def test_trust_deed_identities_are_well_formed_and_the_amendment_chain_is_ordered():
    deed = _committed()["trustDeed"]
    dates = [a["date"] for a in deed["amendmentNotices"]]
    assert dates == sorted(dates) and len(dates) == 12 and "2012-12-17" in dates
    assert all(re.fullmatch(r"[0-9a-f]{64}", a["sha256"]) for a in deed["amendmentNotices"]) and re.fullmatch(r"[0-9a-f]{64}", deed["currentDeedSha256"])
    assert "NOT committed" in deed["retention"] and "byte for byte" in deed["attachmentsAreNotVersionSpecific"]
    assert deed["ruleLagSessionsAfterEx"] == [2, 9] and deed["ruleReadFrom"] == "2012-12-17"


def test_no_rights_entry_is_a_grant_and_the_explicit_restrictions_are_reported():
    matrix = _committed()["rightsTerms"]
    text = json.dumps(matrix, ensure_ascii=False)
    assert "GRANTED" not in text and '"VERIFIED"' not in text
    by = {m["input"].split(" ")[0]: m for m in matrix}
    issuer = matrix[0]
    assert issuer["retention"] == "EXPLICITLY_RESTRICTED_WITHOUT_PRIOR_PERMISSION" and issuer["repositoryRetainsCoveredData"] is True
    assert issuer["permissionDocumentRetained"] is False and "데이터베이스화" in issuer["term"]["quote"]
    assert "KRX" in json.dumps(by["KS200"], ensure_ascii=False) and "자동화" in matrix[1]["term"]["quote"]
    assert matrix[2]["researchUse"].startswith("THIRD_PARTY_OWNER_PERMISSION_REQUIRED") and matrix[2]["term"]["bytesSha256"] is None
    assert "not relied on" in matrix[2]["note"]
    assert matrix[3]["researchUse"].startswith("PUBLIC_DOMAIN_PER_PUBLISHER_STATEMENT") and "not recorded as a grant" in matrix[3]["note"]


def test_fred_copyright_flags_are_recomputed_from_the_retained_series_notes():
    flags = R.fred_note_flags()
    assert flags == {"FRED_VIXCLS": True, "FRED_DGS10": False, "FRED_DGS3MO": False}
    matrix = _committed()["rightsTerms"]
    assert matrix[2]["retainedSeriesNotesContainCopyright"] is True
    assert matrix[3]["retainedSeriesNotesContainCopyright"] == {"DGS10": False, "DGS3MO": False}


def test_cash_options_compute_no_return_and_keep_the_funded_reading_blocked():
    cash = _committed()["cashOptions"]
    assert "BLOCKED" in cash["funded_investor_reading"] and "no return is fabricated" in cash["funded_investor_reading"]
    assert cash["A_REGISTERED_ZERO"]["status"].startswith("OPPORTUNITY_COST_SCENARIO") and cash["D_BOK_BASE_RATE"]["status"].startswith("NON_INVESTABLE")
    assert not re.search(r"\d+(\.\d+)?\s*%", json.dumps(cash["B_LISTED_KRW_SHORT_BOND_OR_MONEY_MARKET_ETF"]))   # no rate is asserted for any option
    assert "ownerDecision" in cash


def test_the_issuer_cap_and_the_out_of_window_event_are_recorded_without_changing_the_population():
    ev = _committed()
    assert ev["issuerEndpoints"]["distributionEndpoint"]["records"] == 20 and ev["events"]["population"] == 46
    assert ev["issuerEndpoints"]["outOfWindowObservation"]["recordDate"] == "2026-10-30"
    assert "not added" in ev["issuerEndpoints"]["outOfWindowObservation"]["note"]
    assert ev["issuerEndpoints"]["distributionEndpoint"]["oldestRecord"] == "2021-10-29"


def test_module_imports_only_the_source_evidence_module_and_runs_no_strategy_code():
    tree = ast.parse(Path(R.__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(("." * node.level) + (node.module or a.name) for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert imported <= {"__future__", "json", "re", "pathlib", "pandas", ".market_research_c1c_source_evidence"}
    assert "replay(" not in Path(R.__file__).read_text()


def test_committed_events_block_is_internally_consistent():
    events = _committed()["events"]
    assert events["verifiedCount"] + events["partialRuleBounded"] + events["partialRecordRuleOnly"] + events["unresolvedNoRule"] == events["unresolved"] == 26
    assert events["population"] - events["officialPaymentDates"] == events["unresolved"]
    assert (events["verifiedCount"], events["partialRuleBounded"], events["partialRecordRuleOnly"]) == (0, 24, 2)
