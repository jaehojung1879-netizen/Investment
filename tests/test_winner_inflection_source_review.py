"""Non-consuming admission regression tests; invented filings and metadata only."""

from copy import deepcopy
import json
from pathlib import Path

import pytest
from pipeline import winner_inflection_admission as A
from pipeline import winner_inflection_execution as X

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("missing", ["availableFrom", "acceptedDate"])
def test_wid_requires_both_dates_without_changing_shared_legacy_helper(missing):
    record = {"id": "SYNTHETIC", "ticker": "SYN", "availableFrom": "2020-01-01", "acceptedDate": "2020-01-02"}
    original = deepcopy(record)
    record[missing] = None
    accepted, rejected = X.reviewed_filings([record])
    assert not accepted and rejected[0]["reason"] == "BOTH_PUBLICATION_AND_ACCEPTANCE_DATES_REQUIRED"
    assert original[missing] is not None and record[missing] is None


def test_malformed_accepted_date_is_not_a_visibility_fallback():
    accepted, rejected = X.reviewed_filings([{"id": "SYN", "acceptedDate": "invalid", "availableFrom": "2020-01-01"}])
    assert not accepted and len(rejected) == 1


def test_rejected_filing_does_not_delete_security_from_observation_universe():
    spec = json.loads((ROOT / A.SPEC_PATH).read_bytes())
    data, config = X.synthetic_fixture(spec)
    ticker = sorted(data["filings"])[0]
    for r in data["filings"][ticker]:
        r["acceptedDate"] = None
    rows = X.observations(data, config)
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


@pytest.mark.parametrize("value", [None, "None", "", "0", "0000000000", True, "4343243243432434", "1.0"])
def test_missing_or_malformed_cik_never_becomes_an_identity(value):
    assert X.normalized_cik(value) is None


def test_valid_cik_padding_is_normalized_without_guessing():
    assert X.normalized_cik("0000320193") == X.normalized_cik(320193) == "320193"


def test_three_missing_ciks_do_not_certify_a_common_issuer():
    spec = json.loads((ROOT / A.SPEC_PATH).read_bytes())
    data, config = X.synthetic_fixture(spec)
    ticker = sorted(data["filings"])[0]
    data["identity"][ticker]["cik"] = None
    for r in data["filings"][ticker]:
        r["cik"] = None
    for snapshot in data["industries"].snapshots:
        snapshot["rows"][ticker]["cik"] = None
    rows = [r for r in X.observations(data, config) if r.ticker == ticker]
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
        X.require_spy_action_history([], "2011-01-01", "2021-07-06")
    for events in [[("2022-01-03", 1., 1.)], [("2020-01-07", 0., 2.)], [("2020-01-07", float("nan"), 1.)]]:
        with pytest.raises(ValueError, match="REQUIRES_DISTRIBUTION_HISTORY"):
            X.require_spy_action_history(events, "2011-01-01", "2021-07-06")
    X.require_spy_action_history([("2020-01-07", 1., 1.)], "2011-01-01", "2021-07-06")
