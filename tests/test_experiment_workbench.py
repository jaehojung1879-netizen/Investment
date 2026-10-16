"""Information-boundary failures on synthetic data, never historical outcomes."""
from dataclasses import replace
import json

import pytest

from pipeline import experiment_workbench as W
from pipeline import replay_calendar as RC
from pipeline.regional_alpha_features import MembershipSnapshots
from scripts import inspect_experiment_sources as A

SHA = "a" * 64


def source(**kw):
    return W.Source(**{"reference": "synthetic:filing", "sha256": SHA, "vintage": "SYNTHETIC_FIXTURE",
                       "observed_at": "2020-01-02T01:00:00Z", "observation_gap": None, **kw})


def cell(**kw):
    return W.Cell(**{"name": "financial.example", "value": 1.0, "unit": "ratio",
                     "available_at": "2020-01-02T01:00:00Z", "source": source(), **kw})


def observation(**kw):
    return W.Observation(**{"key": W.Key("KR", "2020-01-03", "SYN:1"), "ticker": "SYN1",
        "issuer_id": "SYN:ISSUER", "identity_status": "PROVISIONAL", "signal_at": "2020-01-03T09:00:00Z",
        "knowledge_policy": "PUBLIC_RECONSTRUCTION", "universe_source": source(),
        "universe_available_at": "2020-01-02T01:00:00Z", "investable": True, "eligibility_reason": None,
        "industry_id": "SYN:GROUP", "industry_status": "RECONSTRUCTED", "cells": (cell(),), **kw})


def label(market="KR", horizon=63, **kw):
    days = RC.sessions("2020-01-03", "2022-01-01", market)
    end = str(days[horizon].date())
    maturity = end + ("T09:00:00Z" if market == "KR" else "T22:00:00Z")
    return W.LabelReference(**{"sample_id": observation().key.sample_id, "market": market,
        "horizon_sessions": horizon, "execution_at": "2020-01-03T06:30:00Z" if market == "KR" else "2020-01-03T21:00:00Z",
        "maturity_at": maturity, "available_at": maturity, "price_basis_status": "VERIFIED",
        "terminal_status": "NOT_TERMINATED", "reference": "synthetic:separate-target-store", **kw})


def test_dates_identity_and_shared_sample_contract():
    a = observation()
    b = observation(key=W.Key("KR", "2020-01-03", "SYN:2"), ticker="OLD_ALIAS")
    assert W.sample_identity([a, b]) == W.sample_identity([b, a])
    assert replace(b, ticker="NEW_ALIAS").key.sample_id == b.key.sample_id
    assert replace(b, cells=(cell(value=2.0),)).key.sample_id == b.key.sample_id
    with pytest.raises(ValueError, match="DUPLICATE"):
        W.sample_identity([a, a])


@pytest.mark.parametrize("name", ["financial.forwardReturn", "financial.winner", "price.H126_return",
                                  "risk.target", "macro.prediction", "financial.label"])
def test_outcome_columns_cannot_enter_features(name):
    with pytest.raises(ValueError):
        cell(name=name)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_unmeasured_values_do_not_become_numbers(value):
    with pytest.raises(ValueError, match="INVALID_FEATURE"):
        cell(value=value)
    missing = cell(value=None, missing_reason="NOT_STATED", available_at=None)
    assert missing.value is None
    assert cell(value=0.0).value == 0.0
    with pytest.raises(ValueError, match="MISSING_REASON"):
        cell(value=None)


def test_public_and_observed_time_are_independent_boundaries():
    late = source(observed_at="2021-01-01T00:00:00Z")
    assert observation(cells=(cell(source=late),)).knowledge_policy == "PUBLIC_RECONSTRUCTION"
    with pytest.raises(ValueError, match="SOURCE_NOT_OBSERVED"):
        observation(cells=(cell(source=late),), knowledge_policy="OBSERVED_PROSPECTIVE")
    with pytest.raises(ValueError, match="FEATURE_NOT_PUBLIC"):
        observation(cells=(cell(available_at="2020-01-04T00:00:00Z"),))
    with pytest.raises(ValueError, match="UNIVERSE_NOT_PUBLIC"):
        observation(universe_available_at="2020-01-04T00:00:00Z")
    with pytest.raises(ValueError, match="TIMESTAMP_WITHOUT_TIMEZONE"):
        observation(signal_at="2020-01-03T09:00:00")


def test_unknown_identity_and_missing_industry_remain_in_the_sample():
    row = observation(issuer_id=None, identity_status="UNRESOLVED", investable=None,
                      eligibility_reason="IDENTITY_UNRESOLVED", industry_id=None, industry_status="UNRESOLVED")
    assert row.key.sample_id and row.investable is None
    with pytest.raises(ValueError, match="ELIGIBILITY_REASON"):
        replace(row, eligibility_reason=None)
    with pytest.raises(ValueError, match="DUPLICATE_OR_MUTABLE"):
        observation(cells=(cell(), cell()))


@pytest.mark.parametrize("market", ["KR", "US"])
def test_future_filings_and_same_day_release_cannot_change_an_earlier_prefix(market):
    old = {"id": "SYN:1", "availableFrom": "2020-01-01", "acceptedDate": "2020-01-01 17:00:00",
           "receiptNos": ["20200101000001"], "nested": {"x": 1}}
    future = {**old, "id": "SYN:2", "availableFrom": "2020-01-03", "acceptedDate": "2020-01-03 17:00:00",
              "receiptNos": ["20200103000001"]}
    before = W.filing_prefix([old], market, "2020-01-03")
    assert before == W.filing_prefix([old, future], market, "2020-01-03")
    before[0]["nested"]["x"] = 99
    assert old["nested"]["x"] == 1
    if market == "US":
        assert not W.filing_prefix([{**old, "acceptedDate": "2020-01-04"}], market, "2020-01-03")


def test_membership_reuses_strictly_prior_snapshot_without_survivor_filter():
    snapshots = MembershipSnapshots([{"date": "2020-01-01", "members": ["SYN_DEPARTED", "SYN_ALIVE"]},
                                     {"date": "2020-01-03", "members": ["SYN_ALIVE"]}])
    assert "SYN_DEPARTED" in snapshots.on("2020-01-03")["members"]


@pytest.mark.parametrize("market", ["KR", "US"])
@pytest.mark.parametrize("horizon", W.HORIZONS)
def test_label_reference_is_metadata_separate_from_features_and_calendar_checked(market, horizon):
    ref = label(market, horizon)
    with pytest.raises(ValueError, match="LABEL_HORIZON_CALENDAR"):
        replace(ref, maturity_at="2020-01-06T22:00:00Z")
    with pytest.raises(ValueError, match="MATURITY_SESSION_NOT_FINAL"):
        day = ref.maturity_at[:10]
        replace(ref, maturity_at=day + ("T06:30:00Z" if market == "KR" else "T16:00:00Z"))
    assert not hasattr(ref, "value") and not hasattr(observation(), "label")


def test_unmatured_overlap_terminal_and_embargo_boundaries():
    ref = label()
    fold = W.Fold("2020-06-30T00:00:00Z", "2020-07-01T00:00:00Z", "2020-10-01T00:00:00Z",
                  "2020-06-01T00:00:00Z", "VALIDATION")
    assert fold.training_reason(ref) is None
    assert fold.training_reason(replace(ref, terminal_status="UNRESOLVED")) == "BLOCKED_OUTCOME_ECONOMICS"
    assert fold.training_reason(replace(ref, available_at=fold.label_deadline)) == "LABEL_NOT_RELEASED_BEFORE_DEADLINE"
    overlapping = label(horizon=126)
    assert fold.training_reason(overlapping) == "OVERLAPPING_LABEL_INTERVAL"
    assert replace(fold, role="TEST").training_reason(ref) is None
    with pytest.raises(ValueError, match="WALK_FORWARD"):
        replace(fold, training_cutoff=fold.evaluation_start)


def test_preview_metadata_is_explicit_deterministic_and_never_authorizes_execution():
    args = dict(strategy="SYNTHETIC", strategy_sha256=SHA, code_sha256=SHA,
                data_versions={"synthetic": SHA}, seed=42, samples_sha256=SHA,
                result_path="/tmp/workbench-synthetic", created_at="2020-01-03T09:00:00Z")
    assert W.preview_manifest(**args) == W.preview_manifest(**args)
    assert W.preview_manifest(**args)["historicalExecutionAuthorized"] is False
    with pytest.raises(ValueError, match="RUN_IDENTITY"):
        W.preview_manifest(**{**args, "result_path": "relative"})


def test_etf_cash_costs_and_return_basis_are_explicit_and_separate():
    economics = W.Economics("KR", "069500.KS", "GROSS_SHAREHOLDER_TOTAL_RETURN",
                             "GROSS_SHAREHOLDER_TOTAL_RETURN", "VERIFIED", source(), source())
    assert economics.blockers() == ()
    assert replace(economics, cash_rate=None).blockers() == ("CASH_ALTERNATIVE_UNRESOLVED",)
    assert "RETURN_BASIS_MISMATCH" in replace(economics, benchmark_return_definition="PRICE_ONLY").blockers()
    with pytest.raises(ValueError, match="BENCHMARK"):
        replace(economics, benchmark="SPY")


def test_readiness_default_opens_no_sources_and_raw_reader_refuses_outcomes(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(A, "inspect", lambda *_: pytest.fail("unexpected source read"))
    assert A.main([]) == 0
    assert json.loads(capsys.readouterr().out)["sourceReads"] == 0
    for commit, path in [(A.SOURCE_COMMIT, "ledger/outcomes.jsonl"),
                         (A.CODE_BASE, "docs/us-decision-pilot-v1/result.json"),
                         (A.SOURCE_COMMIT, "ledger/replay-inputs/objects/" + SHA + ".json.gz")]:
        with pytest.raises(ValueError, match="ALLOWLIST"):
            A.Sources(tmp_path).blob(commit, path)


def test_filing_cache_rechecks_report_age_without_reading_future_data(monkeypatch):
    records = [{"availableFrom": "2020-02-01", "acceptedDate": "2020-02-01", "id": "SYN:1"}]
    def synthetic(*_):
        return {"cashOperatingProfitability": 1.0, "accrualsToAssets": 1.0,
                "operatingProfitabilityToAssets": 1.0, "state": {}, "reportEnd": "2019-12-31"}
    monkeypatch.setattr(A.CP, "features_as_of", synthetic)
    cache = A.FilingAvailability(records, "US")
    assert cache.at("2020-02-03")[0] is True
    assert cache.at("2020-12-01")[:2] == (False, A.CP.REPORT_STALE)
