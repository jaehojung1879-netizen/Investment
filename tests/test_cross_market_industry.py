"""Independent boundary checks: publication/identity/concentration, no real outcomes."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from pipeline import industry_foundation as F
from research.cross_market_foundation_v1 import industry as I

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "research/cross_market_foundation_v1/evidence"
SHA = hashlib.sha256(b"synthetic-only provenance").hexdigest()
SEC_URL = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/0000320193-23-000106.hdr.sgml"


def sec_fact(raw=None):
    raw = raw or (EVIDENCE / "industry-sec-aapl-2023-header.sgml").read_bytes()
    return I.parse_sec_header(raw, expected_sha256=hashlib.sha256(raw).hexdigest(), source_url=SEC_URL)


def member(name, **changes):
    values = dict(security_id=name, ticker=name, region="KR", taxonomy_id="SYNTHETIC",
                  taxonomy_version="v1", industry_id="A", valid_from="2019-01-01", valid_to=None,
                  source_date="2019-01-01", release_date="2019-01-01", known_to=None,
                  source="synthetic://fixture", source_sha256=SHA, evidence_kind="DATED_ASSIGNMENT",
                  identity_provenance="synthetic fixture")
    values.update(changes)
    return F.Membership(**values)


def configuration(**changes):
    kwargs = dict(region="KR", taxonomy_id="SYNTHETIC", taxonomy_version="v1", industry_id="A",
                  minimum_constituents=2, weighting="EQUAL_WEIGHT", currency="KRW",
                  investability={name: I.Investability(True, "2020-01-01", "2020-01-01", SHA, "2020-01-03", SHA)
                                 for name in ("SYN_A", "SYN_B", "SYN_C")})
    kwargs.update(changes)
    return kwargs


def plan(**changes):
    return I.industry_plan([member(name) for name in ("SYN_A", "SYN_B", "SYN_C")],
                           ["SYN_A", "SYN_B", "SYN_C"], "2020-01-03", **configuration(**changes))


def observation(value, **changes):
    kwargs = dict(value=value, entry_date="2020-01-06", exit_date="2020-02-03", currency="KRW",
                  basis="TOTAL_SHAREHOLDER_RETURN", source_sha256=SHA, distribution_status="COMPLETE")
    kwargs.update(changes)
    return F.ReturnObservation(**kwargs)


def paired(**changes):
    cohort = F.freeze_cohort([member("SYN_A"), member("SYN_B")], ["SYN_A", "SYN_B"], "2020-01-03",
                             **{key: value for key, value in configuration().items()
                                if key in {"region", "taxonomy_id", "taxonomy_version", "industry_id", "minimum_constituents"}})
    kwargs = dict(entry_date="2020-01-06", exit_date="2020-02-03", currency="KRW", regime="SYNTHETIC_EXPANSION",
                  regime_observed_on="2020-01-01", regime_released_on="2020-01-02", regime_sha256=SHA, scope="SYNTHETIC")
    kwargs.update(changes)
    return I.paired_synthetic_attribution(cohort, {"SYN_A": observation(.2), "SYN_B": observation(-.1)},
                                          "SYN_A", observation(.04), **kwargs)


def kind_event(notice="2020-01-02", effective="2020-01-03", before="A", after="B", receipt=None):
    receipt = receipt or notice.replace("-", "") + "000123"
    viewer = '<h1 class="ttl type-99 fleft">가 (000001)</h1>'.encode()
    document = ("<table><tr><td>2.업종 및 업종코드 변경내역</td><td>변경 전</td><td>업종</td><td>" + before +
                "</td></tr><tr><td>변경 후</td><td>업종</td><td>" + after + "</td></tr><tr><td>3.변경일</td><td>" +
                effective + "</td></tr><tr><td>4.변경사유</td><td>기타</td></tr></table>").encode()
    listing = ("<table><tr><td>1</td><td>" + notice + " 12:00</td><td>가</td><td><a onclick=\"openDisclsViewer('" +
               receipt + "','')\">업종변경</a></td><td>가</td></tr></table>").encode()
    sources = {hashlib.sha256(raw).hexdigest(): raw for raw in (viewer, document, listing)}
    event = dict(status="PARSED", ticker="000001.KS", receipt_no=receipt, notice_date=notice,
                 effective_date=effective, before_label=before, after_label=after, document_url="synthetic://kind")
    for name, raw in [("viewer_sha256", viewer), ("document_sha256", document), ("listing_sha256", listing)]:
        event[name] = hashlib.sha256(raw).hexdigest()
    return event, sources


def visible(rows, stamp):
    return F.membership_at(rows, "KRX:000001.KS", stamp, region="KR", taxonomy_id="KIND_LITERAL",
                           taxonomy_version="REPORTED_UNVERSIONED")


def test_real_sec_payload_identity_and_eastern_timezone_are_verified():
    fact = sec_fact()
    assert fact.cik == "0000320193" and fact.sic == "3571"
    assert fact.accepted_at_utc == "2023-11-02T22:08:27+00:00"
    assert fact.filed_on == "2023-11-03" and fact.effective_change_date is None
    assert fact.taxonomy_edition == "UNVERIFIED"
    assert not hasattr(fact, "security_id")
    probe = json.loads((EVIDENCE / "industry-sec-probe.json").read_text())
    assert probe["http_status"] == 200 and probe["response_sha256"] == fact.source_sha256


def test_current_sec_fact_never_backfills_prior_dates_or_its_filing_day():
    fact = sec_fact()
    assert I.sec_issuer_at([fact], fact.cik, "2023-11-03") is None
    assert I.sec_issuer_at([fact], fact.cik, "2023-11-04") == fact
    assert I.sec_issuer_at([fact], "0000000001", "2024-01-01") is None


def test_sec_corrections_preserve_earlier_public_state():
    old = sec_fact()
    new = replace(old, sic="9999", filed_on="2024-01-05", accepted_at_utc="2024-01-05T15:00:00+00:00")
    assert I.sec_issuer_at([new, old], old.cik, "2024-01-05").sic == "3571"
    assert I.sec_issuer_at([old, new], old.cik, "2024-01-06").sic == "9999"
    with pytest.raises(ValueError, match="CONFLICTING"):
        I.sec_issuer_at([old, replace(old, sic="9999")], old.cik, "2024-01-01")


@pytest.mark.parametrize("transform", [lambda raw: raw + b"<FILER><CIK>1</FILER>",
                                        lambda raw: raw.replace(b"<ASSIGNED-SIC>3571", b""),
                                        lambda raw: raw.replace(b"<CIK>0000320193", b"<CIK>0000320193\n<CIK>0000000001")])
def test_sec_ambiguous_or_missing_issuer_evidence_refused(transform):
    raw = (EVIDENCE / "industry-sec-aapl-2023-header.sgml").read_bytes()
    with pytest.raises(ValueError):
        sec_fact(transform(raw))


def test_changed_raw_bytes_and_invented_taxonomy_or_change_dates_refused():
    raw = (EVIDENCE / "industry-sec-aapl-2023-header.sgml").read_bytes()
    with pytest.raises(ValueError, match="MISSING_OR_CHANGED"):
        I.parse_sec_header(raw + b"x", expected_sha256=hashlib.sha256(raw).hexdigest(), source_url=SEC_URL)
    for changes in [{"taxonomy": "GICS"}, {"effective_change_date": "2013-01-01"}, {"taxonomy_edition": "1987"}]:
        with pytest.raises(ValueError, match="NOT_ESTABLISHED"):
            replace(sec_fact(), **changes)


@pytest.mark.parametrize("url", [
    SEC_URL.replace("/320193/", "/789019/"),
    SEC_URL.replace("/000032019323000106/", "/000032019323000107/"),
    SEC_URL.replace("0000320193-23-000106.hdr.sgml", "0000320193-23-000107.hdr.sgml"),
    SEC_URL + "?different=citation",
    SEC_URL.replace("www.sec.gov", "www.sec.gov.example.com"),
])
def test_sec_raw_header_must_match_cited_cik_accession_and_archive_file(url):
    raw = (EVIDENCE / "industry-sec-aapl-2023-header.sgml").read_bytes()
    with pytest.raises(ValueError, match="SEC_ARCHIVE"):
        I.parse_sec_header(raw, expected_sha256=hashlib.sha256(raw).hexdigest(), source_url=url)


def test_kind_forward_fact_requires_publication_and_effective_date():
    event, sources = kind_event(effective="2020-02-01")
    rows = I.kind_dated_memberships([event], sources)
    assert visible(rows, "2019-12-31") is None
    assert visible(rows, "2020-01-02") is None
    assert visible(rows, "2020-01-31") is None
    assert visible(rows, "2020-02-01").industry_id == "KIND:B"


def test_kind_late_release_never_rewrites_past_and_never_uses_before_label():
    event, sources = kind_event(notice="2020-02-01", effective="2020-01-01")
    rows = I.kind_dated_memberships([event], sources)
    assert visible(rows, "2020-01-15") is None
    assert visible(rows, "2020-02-01") is None
    assert visible(rows, "2020-02-02").industry_id == "KIND:B"


def test_kind_supersession_waits_for_announcement_and_future_effectiveness():
    a, raw_a = kind_event()
    b, raw_b = kind_event(notice="2020-01-05", effective="2020-01-10", before="B", after="C")
    rows = I.kind_dated_memberships([b, a], {**raw_a, **raw_b})
    assert visible(rows, "2020-01-09").industry_id == "KIND:B"
    assert visible(rows, "2020-01-10").industry_id == "KIND:C"


@pytest.mark.parametrize("field,value", [("notice_date", "2019-01-01"), ("after_label", "INVENTED"),
                                         ("ticker", "000002.KS"), ("status", "CURRENT_ANCHOR")])
def test_kind_raw_identity_publication_and_metadata_must_agree(field, value):
    event, sources = kind_event()
    with pytest.raises(ValueError):
        I.kind_dated_memberships([dict(event, **{field: value})], sources)


def test_real_retained_kind_bytes_are_reused_without_current_anchors():
    rows, audit = I.load_retained_kind(ROOT)
    assert len(rows) == 80 and len({row.security_id for row in rows}) == 62
    assert audit["currentAnchorsAdmitted"] is False and audit["admittedPriorHistoryBeforeFirstNotice"] is False
    assert not audit["historicalOutcomeComputed"]
    assert all(row.evidence_kind == "DATED_ASSIGNMENT" for row in rows)
    assert all(row.taxonomy_version == "REPORTED_UNVERSIONED" for row in rows)


def test_source_audit_reproduces_committed_evidence_and_preserves_failed_v4():
    audit = I.build_industry_source_audit(ROOT)
    committed = json.loads((EVIDENCE / "industry-source-audit.json").read_text())
    assert audit == committed
    assert audit["priorDecisionsUnchanged"]["v4"] == "DATA_FOUNDATION_INSUFFICIENT_V4"
    assert len(audit["terminal22"]) == 22
    strict = audit["strictLastPublicObservationInput"]
    assert strict["classifiedNameDates"] == 10093 and strict["nameDates"] == 73200
    assert strict["terminalNameDates"] == 2345 and strict["terminalSecuritiesWithObservation"] == 0
    assert strict["empiricalReadiness"] == "SOURCE_BLOCKED"


def test_fixed_main_source_is_not_silently_relabelled_after_working_tree_drift(tmp_path):
    path = "data/kr-industry-membership-foundation-v3/state/events.json.gz"
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_bytes((ROOT / path).read_bytes() + b"changed")
    with pytest.raises(ValueError, match="MISSING_OR_CHANGED"):
        I.load_retained_kind(tmp_path)


def test_equal_weight_concentration_and_leave_largest_out_remain_diagnostics():
    result = plan()
    assert result["hhi"] == pytest.approx(1 / 3)
    assert result["effectiveMemberCount"] == pytest.approx(3)
    assert result["largestRemoval"]["removedSecurityId"] == "SYN_A"
    assert result["largestRemoval"]["hhi"] == pytest.approx(.5)
    assert not result["historicalOutcomeComputed"]


def test_cap_weights_reuse_original_engine_and_expose_single_name_dominance():
    caps = {name: F.Capitalization(value, "2020-01-01", "2020-01-02", "KRW", SHA)
            for name, value in [("SYN_A", 8), ("SYN_B", 1), ("SYN_C", 1)]}
    result = plan(weighting="MARKET_CAP_WEIGHT", capitalizations=caps)
    assert result["weights"]["SYN_A"] == .8
    assert result["hhi"] == pytest.approx(.66)
    caps["SYN_A"] = replace(caps["SYN_A"], release_date="2020-01-03")
    blocked = plan(weighting="MARKET_CAP_WEIGHT", capitalizations=caps)
    assert blocked["missingCapitalizations"] == ["SYN_A"]
    assert blocked["weights"] is None and blocked["hhi"] is None


@pytest.mark.parametrize("available", [None, False])
def test_uninvestable_or_unknown_name_blocks_without_survivor_renormalisation(available):
    eligibility = configuration()["investability"]
    eligibility["SYN_A"] = replace(eligibility["SYN_A"], available=available)
    result = plan(investability=eligibility)
    assert result["status"] == "SOURCE_BLOCKED" and result["weights"] is None
    assert result["hhi"] is None and result["missingInvestability"] == ["SYN_A"]


@pytest.mark.parametrize("changes", [{"valid_through": "2020-01-02"},
                                      {"terminated_on": "2020-01-03"},
                                      {"validity_source_sha256": ""}])
def test_stale_terminated_or_unproven_validity_cannot_extrapolate_investability(changes):
    eligibility = configuration()["investability"]
    eligibility["SYN_A"] = replace(eligibility["SYN_A"], **changes)
    result = plan(investability=eligibility)
    assert result["status"] == "SOURCE_BLOCKED" and result["weights"] is None
    assert result["missingInvestability"] == ["SYN_A"]


def test_unclassified_full_universe_and_undersized_groups_are_not_deleted():
    result = I.industry_plan([member("SYN_A"), member("SYN_B")], ["SYN_A", "SYN_B", "UNCLASSIFIED"],
                             "2020-01-03", **configuration())
    assert result["cohort"]["missing_classification"] == ("UNCLASSIFIED",)
    assert result["weights"] is None
    assert plan(minimum_constituents=4)["weights"] is None


def test_disjoint_synthetic_attribution_prevents_industry_stock_double_count():
    result = paired()
    assert result["stockReturn"] == pytest.approx(.2)
    assert result["components"]["market_return"] == .04
    assert result["components"]["industry_excess_return"] == pytest.approx(.01)
    assert result["components"]["stock_within_industry_return"] == pytest.approx(.15)
    with pytest.raises(ValueError, match="OVERLAPPING"):
        I.compose_disjoint_attribution(dict(result["components"], stock_market_relative_return=.16))


@pytest.mark.parametrize("kwargs", [{"scope": "HISTORICAL"}, {"regime_released_on": "2020-01-03"},
                                   {"regime_observed_on": "2020-02-01"}, {"regime_sha256": ""}])
def test_new_historical_outcome_and_future_or_unproven_regime_are_refused(kwargs):
    with pytest.raises(ValueError):
        paired(**kwargs)


def test_currency_mismatch_partial_distributions_and_unresolved_terminal_block():
    cohort = F.freeze_cohort([member("SYN_A"), member("SYN_B")], ["SYN_A", "SYN_B"], "2020-01-03",
                             region="KR", taxonomy_id="SYNTHETIC", taxonomy_version="v1", industry_id="A", minimum_constituents=2)
    for changes in [{"distribution_status": "PARTIAL"}, {"terminal_status": "UNRESOLVED"}, {"currency": "USD"}]:
        observations = {"SYN_A": observation(.2), "SYN_B": observation(-.1, **changes)}
        result = I.paired_synthetic_attribution(cohort, observations, "SYN_A", observation(.04),
                                               entry_date="2020-01-06", exit_date="2020-02-03", currency="KRW",
                                               regime="SYNTHETIC", regime_observed_on="2020-01-01", regime_released_on="2020-01-02",
                                               regime_sha256=SHA, scope="SYNTHETIC")
        assert result["status"] == "SOURCE_BLOCKED" and result["components"] is None
