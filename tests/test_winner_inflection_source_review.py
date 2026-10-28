"""Non-consuming admission regression tests; invented filings and metadata only."""

from copy import deepcopy
import json
from pathlib import Path

import pytest
from pipeline import winner_inflection_admission as A
from pipeline import winner_inflection_execution as X
from pipeline import winner_inflection_filing_review as F

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("year", [1215, None, "2015", True])
def test_fiscal_year_fallback_cannot_be_used_as_verified_filing_identity(year):
    record = {"id": "SYN|accession", "ticker": "SYN", "fiscalYear": year,
              "periodStart": "2015-01-01", "periodEnd": "2015-12-31",
              "availableFrom": "2016-02-22", "acceptedDate": "2016-02-22 08:35:20"}
    before = deepcopy(record)
    good, withheld = F.reviewed_filing_shard([record], 2015)
    assert not good
    assert withheld == [{"id": record["id"], "ticker": "SYN",
                         "reason": "FISCAL_YEAR_SHARD_IDENTITY_UNPROVEN",
                         "expectedFiscalYear": 2015, "reportedFiscalYear": year}]
    assert record == before


def test_fiscal_shard_review_keeps_noncalendar_fiscal_labels_and_date_refusals():
    record = {"id": "SYN|valid", "ticker": "SYN", "fiscalYear": 2011,
              "periodStart": "2011-11-01", "periodEnd": "2012-01-31",
              "availableFrom": "2012-03-05", "acceptedDate": "2012-03-05 16:06:48"}
    missing_date = {**record, "id": "SYN|missing", "acceptedDate": None}
    good, withheld = F.reviewed_filing_shard([record, missing_date], 2011)
    assert good == [record]
    assert [r["id"] for r in withheld] == ["SYN|missing"]
    assert withheld[0]["reason"] == "BOTH_PUBLICATION_AND_ACCEPTANCE_DATES_REQUIRED"


def test_withheld_fiscal_metadata_survives_preparation_without_deleting_security():
    spec = json.loads((ROOT / A.SPEC_PATH).read_bytes())
    data, _ = X.synthetic_fixture(spec)
    ticker = sorted(data["filings"])[0]
    good, withheld = F.reviewed_filing_shard([{**data["filings"][ticker][0], "fiscalYear": 1215}], 2015)
    data["filings"][ticker] = good
    data["withheldFilingMetadata"] = withheld
    prepared = F.prepare_inputs(data)
    assert ticker in prepared["filings"] and not prepared["filings"][ticker]
    assert prepared["withheldFilingMetadata"] == withheld
    assert prepared["membership"].snapshots == data["membership"].snapshots
    assert F.prepare_inputs(prepared)["withheldFilingMetadata"] == withheld


def test_metadata_funnel_keeps_departed_names_and_strict_signal_day_boundary(monkeypatch):
    from scripts.inspect_wid_filing_dates import identity_census
    from pipeline.regional_alpha_features import MembershipSnapshots
    spec = json.loads((ROOT / A.SPEC_PATH).read_bytes())
    spec.update(inputStart="2020-01-01", signalEnd="2020-01-10")
    names = ["GOOD", "DEPARTED", "UNKNOWN_CIK", "NO_FILING", "MISMATCH", "EXCLUDED_INDUSTRY"]
    members = MembershipSnapshots([{"date": "2019-12-31", "members": names}])
    sectors = MembershipSnapshots([{"date": "2019-12-31", "rows": {
        t: {"cik": None if t == "UNKNOWN_CIK" else "123", "sector": "Financials" if t == "EXCLUDED_INDUSTRY" else "Industrials"}
        for t in names}}])
    identities = [{"symbol": t, "cik": "124" if t == "MISMATCH" else "123",
                   "sp500IdentityCategory": "DEPARTED_NO_PANEL_REASON_UNRESOLVED" if t == "DEPARTED" else "CURRENT_MEMBER_OWN_PANEL"}
                  for t in names]
    filings = [{"ticker": t, "cik": "123", "availableFrom": "2020-01-03" if t == "GOOD" else "2020-01-01",
                "acceptedDate": "2020-01-03" if t == "GOOD" else "2020-01-01"} for t in names if t != "NO_FILING"]
    monkeypatch.setattr(X, "observations", lambda *a: pytest.fail("no real observation/quote builder"))
    monkeypatch.setattr(X, "execute", lambda *a, **k: pytest.fail("no executor"))
    r = identity_census(spec, members, sectors, identities, filings)
    assert r["weeklyDates"] == 2 and r["enumeratedMemberDates"] == 12
    assert sum(r["firstMetadataReason"].values()) == 12
    assert r["firstMetadataReason"]["CONDITIONAL_SCOPE_EXCLUDED:DEPARTED_NO_PANEL_REASON_UNRESOLVED"] == 2
    assert r["firstMetadataReason"]["NO_STRICTLY_VISIBLE_FILING"] == 3
    assert r["firstMetadataReason"]["PROVISIONAL_ISSUER_ONLY_NOT_SECURITY_ADMISSION"] == 1
    assert r["securityShareClassVerified"] is r["comparableTotalReturnVerified"] is None
    assert r["admittedMemberDates"] == 0
    assert identity_census(spec, members, sectors, identities[::-1], filings[::-1]) == r
    with pytest.raises(ValueError, match="DUPLICATE_SOURCE_IDENTITY_SYMBOL"):
        identity_census(spec, members, sectors, identities + identities[:1], filings)


@pytest.mark.parametrize("missing", ["availableFrom", "acceptedDate"])
def test_wid_requires_both_dates_without_changing_shared_legacy_helper(missing):
    record = {"id": "SYNTHETIC", "ticker": "SYN", "availableFrom": "2020-01-01", "acceptedDate": "2020-01-02"}
    original = deepcopy(record)
    record[missing] = None
    accepted, rejected = F.reviewed_filings([record])
    assert not accepted and rejected[0]["reason"] == "BOTH_PUBLICATION_AND_ACCEPTANCE_DATES_REQUIRED"
    assert original[missing] is not None and record[missing] is None


def test_malformed_accepted_date_is_not_a_visibility_fallback():
    accepted, rejected = F.reviewed_filings([{"id": "SYN", "acceptedDate": "invalid", "availableFrom": "2020-01-01"}])
    assert not accepted and len(rejected) == 1


@pytest.mark.parametrize("field,value", [
    ("availableFrom", "2020-01-01garbage"), ("acceptedDate", "2020-01-02 99:99:99"),
    ("acceptedDate", "2020-02-30T17:00:00"), ("acceptedDate", "2020-01-02T17:00:00junk")])
def test_full_public_timestamp_is_validated_not_only_first_ten_characters(field, value):
    record = {"id": "SYN", "availableFrom": "2020-01-01", "acceptedDate": "2020-01-02 17:00:00"}
    record[field] = value
    accepted, rejected = F.reviewed_filings([record])
    assert not accepted and rejected[0]["id"] == "SYN"


@pytest.mark.parametrize("later", ["availableFrom", "acceptedDate"])
def test_downstream_filing_states_uses_later_date_and_excludes_whole_signal_day(later):
    from pipeline import winner_inflection as I
    record = {"id": "SYN", "ticker": "SYN", "availableFrom": "2020-01-02", "acceptedDate": "2020-01-02",
              "fiscalYear": 2019, "periodDays": 365, "periodEnd": "2019-12-31"}
    record[later] = "2020-01-03 23:59:59"  # later than the signal close+buffer
    accepted, rejected = F.reviewed_filings([record])
    assert not rejected
    state = I.FilingStates(accepted, "US")
    assert state.days == ["2020-01-03"]
    assert state.at("2020-01-02")["sourceIds"] == []
    assert state.at("2020-01-03")["sourceIds"] == []
    assert state.at("2020-01-06")["sourceIds"] == ["SYN"]


def test_offset_acceptance_after_signal_is_withheld_without_mutating_source():
    from pipeline import winner_inflection as I
    record = {"id": "SYN", "ticker": "SYN", "availableFrom": "2020-01-02",
              "fiscalYear": 2019, "periodDays": 365, "periodEnd": "2019-12-31",
              "acceptedDate": "2020-01-02T23:30:00-08:00"}  # New York Jan 3
    original = deepcopy(record)
    accepted, rejected = F.reviewed_filings([record])
    assert not rejected and record == original
    assert accepted[0]["_widOriginalAvailability"]["acceptedDate"] == original["acceptedDate"]
    state = I.FilingStates(accepted, "US")
    assert state.at("2020-01-03")["sourceIds"] == []
    assert state.at("2020-01-06")["sourceIds"] == ["SYN"]


def test_rejected_filing_does_not_delete_security_from_observation_universe():
    spec = json.loads((ROOT / A.SPEC_PATH).read_bytes())
    data, config = X.synthetic_fixture(spec)
    ticker = sorted(data["filings"])[0]
    for r in data["filings"][ticker]:
        r["acceptedDate"] = None
    rows = F.observations(data, config)
    own = [r for r in rows if r.ticker == ticker]
    assert own and all(not r.investable for r in own)


def test_partial_technical_review_cannot_resolve_rights_identity_or_returns(tmp_path, monkeypatch):
    root = ROOT / "docs/winner-inflection-discovery/admission-review-v2"
    review = json.loads((root / "review.json").read_text())
    raw = (root / "source-audit.json").read_bytes()
    monkeypatch.setattr(A, "EVIDENCE_ROOT", tmp_path)
    evidence = tmp_path / "SYNTHETIC_COPY_OF_METADATA_REVIEW.json"
    evidence.write_bytes(raw)
    for name in ["membershipIndustry", "size", "vintage", "terminal"]:
        review["claims"][name]["citations"][0]["reference"] = str(evidence)
    spec = json.loads((ROOT / A.SPEC_PATH).read_bytes())
    result = A.admission(spec, review)
    assert set(result["reasons"]) == {"SOURCE_REVIEW_UNRESOLVED:" + s for s in ["rights", "identity", "returnBasis"]}
    assert result["status"] == "BLOCKED" and result["outcomeReads"] == result["modelFits"] == 0
    evidence.write_bytes(raw + b"\nTAMPER")
    assert any("UNVERIFIED" in r for r in A.admission(spec, review)["reasons"])


def test_clean_environment_without_referenced_evidence_stays_blocked(tmp_path, monkeypatch):
    review = json.loads((ROOT / "docs/winner-inflection-discovery/admission-review-v2/review.json").read_bytes())
    monkeypatch.setattr(A, "EVIDENCE_ROOT", tmp_path)
    result = A.admission(json.loads((ROOT / A.SPEC_PATH).read_bytes()), review)
    assert result["status"] == "BLOCKED"
    assert all("REVIEWED_EVIDENCE_BYTES_UNVERIFIED:" + claim in result["reasons"]
               for claim in ("membershipIndustry", "size", "vintage", "terminal"))
    assert not list(tmp_path.iterdir())  # never silently materializes missing evidence


@pytest.mark.parametrize("value", [None, "None", "", "0", "0000000000", True, "4343243243432434", "1.0"])
def test_missing_or_malformed_cik_never_becomes_an_identity(value):
    assert F.normalized_cik(value) is None


def test_valid_cik_padding_is_normalized_without_guessing():
    assert F.normalized_cik("0000320193") == F.normalized_cik(320193) == "320193"


def test_three_missing_ciks_do_not_certify_a_common_issuer():
    spec = json.loads((ROOT / A.SPEC_PATH).read_bytes())
    data, config = X.synthetic_fixture(spec)
    ticker = sorted(data["filings"])[0]
    data["identity"][ticker]["cik"] = None
    for r in data["filings"][ticker]:
        r["cik"] = None
    for snapshot in data["industries"].snapshots:
        snapshot["rows"][ticker]["cik"] = None
    rows = [r for r in F.observations(data, config) if r.ticker == ticker]
    assert rows and all(r.identity_status == "UNRESOLVED" and not r.investable for r in rows)


def test_empty_spy_actions_cannot_relabel_a_total_return_index_as_native():
    import pandas as pd
    from pipeline import us_multifactor_inputs as MI
    dates = pd.to_datetime(["2020-01-06", "2020-01-07"])
    # This is the actual algorithmic failure mode, on entirely invented values.
    index = [100., 102.]
    recovered = MI.as_traded_from_total_return(dates, index, [])
    assert list(recovered) == index  # algebraic identity does NOT certify raw prices
    with pytest.raises(ValueError, match="REQUIRES_DISTRIBUTION_HISTORY"):
        F.require_spy_action_history([], "2011-01-01", "2021-07-06")
    for events in [[("2022-01-03", 1., 1.)], [("2020-01-07", 0., 2.)], [("2020-01-07", float("nan"), 1.)]]:
        with pytest.raises(ValueError, match="REQUIRES_DISTRIBUTION_HISTORY"):
            F.require_spy_action_history(events, "2011-01-01", "2021-07-06")
    F.require_spy_action_history([("2020-01-07", 1., 1.)], "2011-01-01", "2021-07-06")


def test_c1_pinned_shared_executor_bytes_are_unchanged_and_wid_adapter_is_pinned():
    path = "pipeline/winner_inflection_execution.py"
    spec = json.loads((ROOT / "docs/research-program/specs/rp1-c1-us-exposure-ladder-replication-v1.json").read_bytes())
    assert A.file_sha(ROOT / path) == spec["dependencyHashes"][path]
    assert "pipeline/winner_inflection_filing_review.py" in A.CLOSURE


def test_wid_preparation_is_detached_and_idempotent_without_universe_loss():
    data, config = X.synthetic_fixture(json.loads((ROOT / A.SPEC_PATH).read_bytes()))
    ticker = sorted(data["filings"])[0]
    data["filings"][ticker][0]["acceptedDate"] = None
    old_count = len(data["filings"][ticker])
    once = F.prepare_inputs(data)
    twice = F.prepare_inputs(once)
    assert len(data["filings"][ticker]) == old_count
    assert len(once["filings"][ticker]) == len(twice["filings"][ticker]) == old_count - 1
    assert set(data["identity"]) == set(twice["identity"])
    assert once["withheldFilingMetadata"] == twice["withheldFilingMetadata"]


def test_wid_wrapper_preserves_withheld_metadata_at_persisted_evaluation(monkeypatch):
    data, config = X.synthetic_fixture(json.loads((ROOT / A.SPEC_PATH).read_bytes()))
    ticker = sorted(data["filings"])[0]
    record = data["filings"][ticker][0]
    record["acceptedDate"] = None
    saved = []

    def fake_execute(prepared, spec, *, checkpoint):
        assert all(r["id"] != record["id"] for r in prepared["filings"][ticker])
        checkpoint("evaluation", "records", {"status": "SYNTHETIC"})
        return {"evaluation": {"status": "SYNTHETIC"}}

    monkeypatch.setattr(X, "execute", fake_execute)
    result = F.execute(data, config, checkpoint=lambda *args: saved.append(args))
    assert result["evaluation"]["withheldFilingMetadata"][0]["id"] == record["id"]
    assert saved[0][2]["withheldFilingMetadata"] == result["evaluation"]["withheldFilingMetadata"]
