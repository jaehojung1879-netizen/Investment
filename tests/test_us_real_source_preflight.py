"""Invented observations only. No network connectivity claim from these tests."""
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import importlib.util
import subprocess

import pandas as pd
import pytest

from pipeline import us_daily_market_data as D
from pipeline import us_daily_market_sources as S
from pipeline import us_real_source_preflight as P

NOW = "2026-10-12T06:00:00Z"
ROOT = Path(__file__).resolve().parents[1]


def membership():
    raw = b"Symbol,Security,CIK\nAAPL,Fixture tech,100\nJPM,Fixture bank,200\nBRK.B,Fixture share class,300\n"
    return D.MembershipResponse(raw, "SYNTHETIC_MEMBERSHIP", "fixture-v1", NOW, "2026-10-09T00:00:00Z", D.SYNTHETIC)


def fetch(ticker, start, end):
    dates = D.sessions(start, end, "US").tz_localize("America/New_York")
    frame = pd.DataFrame({"Open":100., "High":101., "Low":99., "Close":100., "Volume":1000.,
                          "Dividends":0., "Stock Splits":0.}, index=dates)
    metadata = {"symbol":ticker, "currency":"USD", "exchangeTimezoneName":"America/New_York",
                "instrumentType":"ETF" if ticker in D.BENCHMARKS else "EQUITY", "acquisitionOptions":D.PRICE_OPTIONS}
    return D.PriceResponse(frame, metadata, NOW)


def test_benchmark_first_small_actual_identity_sample_and_immutable_repeat(tmp_path):
    calls = []
    def provider(ticker, start, end):
        calls.append(ticker)
        return fetch(ticker, start, end)
    result = P.probe(tmp_path, membership(), provider, now=NOW)
    assert calls == ["SPY", "QQQ", "AAPL", "JPM", "BRK-B"]
    assert result["verdict"] == "PASS"
    assert result["validPriceRecordCount"] == 35
    assert result["sourceKind"] == D.SYNTHETIC
    assert result["calls"] == P.MAX_PROVIDER_CALLS
    assert not result["fullUniverseReady"] and not result["collectionComplete"]
    assert result["membership"]["effectiveMembershipDate"] is None
    assert result["integrity"]["appendOnlyBytesUnchanged"]
    assert result["integrity"]["repeatCount"] == 35
    assert result["integrity"]["noPricesBeforeFirstAcquisition"]
    assert result["integrity"]["nonidentitySplitsObserved"] == 0
    assert len(D.ObservationStore(tmp_path, D.SYNTHETIC).observations()) == 35
    hashes = json.loads((tmp_path/"evidence-hashes.json").read_text())
    for relative, sha in hashes.items():
        assert hashlib.sha256((tmp_path/relative).read_bytes()).hexdigest() == sha
    assert json.loads((tmp_path/"preflight.json").read_text()) == result


def test_benchmark_refusal_never_fans_out_to_members(tmp_path):
    calls = []
    def blocked(ticker, *_):
        calls.append(ticker)
        raise D.Refused("YAHOO_PROVIDER_REFUSAL", "ConnectionError: CONNECT tunnel failed, response 403")
    result = P.probe(tmp_path, membership(), blocked, now=NOW)
    assert calls == ["SPY", "QQQ"]
    assert result["verdict"] == "BLOCKED"
    assert result["failureClasses"] == ["PROXY_CONNECT_403"]
    assert result["validPriceRecordCount"] == 0
    assert not D.ObservationStore(tmp_path, D.SYNTHETIC).observations()


def test_partial_benchmark_and_partial_sample_preserve_real_injected_progress(tmp_path):
    def partial(ticker, start, end):
        if ticker == "QQQ":
            raise D.Refused("YAHOO_PROVIDER_REFUSAL", "HTTP 429: Too Many Requests")
        return fetch(ticker,start,end)
    result = P.probe(tmp_path/"one", membership(), partial, now=NOW)
    assert result["verdict"] == "PARTIAL" and result["calls"] == 2
    assert result["failureClasses"] == ["PROVIDER_RATE_LIMIT"]
    assert result["validPriceRecordCount"] == 7
    def sample(ticker, start, end):
        r = fetch(ticker,start,end)
        if ticker == "BRK-B":
            r.metadata["symbol"] = "WRONG"
        return r
    result = P.probe(tmp_path/"two", membership(), sample, now=NOW)
    assert result["verdict"] == "PARTIAL"
    assert result["validPriceRecordCount"] == 28
    assert not result["scopeComplete"]
    assert result["failureClasses"] == ["IDENTITY_OR_SOURCE_CONTRACT_PROBLEM"]


@pytest.mark.parametrize("message,expected", [
    ("CONNECT tunnel failed, response 403", "PROXY_CONNECT_403"),
    ("HTTP 401 Unauthorized", "PROVIDER_AUTHORIZATION"),
    ("invalid crumb", "PROVIDER_AUTHORIZATION"),
    ("YFRateLimitError: Too Many Requests", "PROVIDER_RATE_LIMIT"),
    ("HTTP 403 Forbidden", "PROVIDER_OR_GATEWAY_FORBIDDEN_UNRESOLVED"),
    ("SSL certificate problem", "TRANSPORT_OR_PROVIDER_ERROR_UNRESOLVED"),
])
def test_failure_classes_do_not_invent_cause(message, expected):
    exc = D.Refused("YAHOO_PROVIDER_REFUSAL", message)
    assert P.classify(exc) == expected
    assert P.failure("SPY","BENCHMARK",exc)["originalMessage"] == message


@pytest.mark.parametrize("change,expected", [
    (lambda r: r.frame.drop(columns="Dividends",inplace=True), "MISSING_CORPORATE_ACTIONS"),
    (lambda r: r.frame.__setitem__("Stock Splits",float("nan")), "MISSING_CORPORATE_ACTIONS"),
    (lambda r: r.frame.drop(r.frame.index[0],inplace=True), "INCOMPLETE_FRAME"),
    (lambda r: r.metadata.update(currency="EUR"), "INVALID_CURRENCY_UNIT"),
    (lambda r: r.frame.__setitem__("Close",float("nan")), "SCHEMA_OR_INTEGRITY_VIOLATION"),
])
def test_frame_and_action_errors_are_distinct(tmp_path, change, expected):
    def provider(ticker,start,end):
        r=fetch(ticker,start,end)
        change(r)
        return r
    result=P.probe(tmp_path,membership(),provider,now=NOW)
    assert result["failureClasses"] == [expected]
    assert result["verdict"] == "BLOCKED"
    assert result["calls"] == 2


def test_actual_injected_actions_are_validated_once_and_not_total_return(tmp_path):
    def actions(ticker,start,end):
        r=fetch(ticker,start,end)
        if ticker=="JPM":
            r.frame.loc[:,["Open","High","Low","Close"]] /= 2
            r.frame.loc[r.frame.index[-1],"Stock Splits"] = 2
            r.frame.loc[r.frame.index[0],"Dividends"] = 1
        return r
    result=P.probe(tmp_path,membership(),actions,now=NOW)
    assert result["verdict"] == "PASS"
    assert result["integrity"]["nonzeroDividendsObserved"] == 1
    assert result["integrity"]["nonidentitySplitsObserved"] == 1
    assert result["integrity"]["asTradedBasisVerified"]
    assert not result["totalReturnComputed"]


def test_budget_prevents_more_requests(tmp_path):
    times=iter([0,0,181])
    result=P.probe(tmp_path,membership(),fetch,now=NOW,monotonic=lambda:next(times))
    assert result["calls"] == 1 and result["verdict"] == "PARTIAL"
    assert result["failureClasses"] == ["TIME_BUDGET"]


def test_production_destination_refused_before_any_source_call(monkeypatch):
    def forbidden():
        pytest.fail("No request before output validation")
    monkeypatch.setattr(S,"current_sp500",forbidden)
    with pytest.raises(D.Refused,match="outside"):
        P.main(ROOT/"ledger")


def test_pre_membership_refusal_unknown_counts_and_no_price_probe(tmp_path, monkeypatch):
    def blocked():
        raise D.Refused("MEMBERSHIP_HTTP_REFUSAL","HTTP 401 Unauthorized")
    monkeypatch.setattr(S,"current_sp500",blocked)
    monkeypatch.setattr(S,"yahoo_daily",lambda *_:pytest.fail("No prices without membership"))
    assert P.main(tmp_path) == 0
    result=json.loads((tmp_path/"preflight.json").read_text())
    assert result["sourceKind"] == D.LIVE
    assert result["verdict"] == "BLOCKED" and result["calls"] == 0
    assert "membership" not in result
    assert not result["fullUniverseReady"]


def test_future_observations_are_unavailable_before_acquisition(tmp_path):
    def delayed(ticker,start,end):
        original=fetch(ticker,start,end)
        return D.PriceResponse(original.frame,original.metadata,D.stamp(D.utc(NOW)+timedelta(seconds=20)))
    P.probe(tmp_path,membership(),delayed,now=NOW)
    store=D.ObservationStore(tmp_path,D.SYNTHETIC)
    assert store.prices_at(NOW)=={}
    assert len(store.prices_at(D.utc(NOW)+timedelta(seconds=20)))==35


def test_retained_cli_does_not_request_sources_on_import(monkeypatch):
    def forbidden(*_):
        pytest.fail("Manual diagnostic must not run on import")
    monkeypatch.setattr(P, "main", forbidden)
    monkeypatch.setattr(S, "current_sp500", forbidden)
    monkeypatch.setattr(S, "yahoo_daily", forbidden)
    spec = importlib.util.spec_from_file_location("retained_preflight_cli", ROOT/"scripts/preflight_us_real_sources.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


def test_temporary_network_job_removed_and_no_automatic_source_hooks():
    for workflow in (ROOT/".github/workflows").iterdir():
        if workflow.suffix not in (".yml", ".yaml"):
            continue
        text = workflow.read_text()
        assert "preflight_us_real_sources.py" not in text
        assert "us-real-source-preflight:" not in text
        assert "us-preflight-evidence:" not in text
    for name in ('pipeline/us_real_source_preflight.py','scripts/preflight_us_real_sources.py'):
        code=(ROOT/name).read_text()
        assert not any(x in code for x in ('fit(', 'forward_return', 'load_market_values', 'append_signals', 'weekly_publish', 'workflow_dispatch', 'git push'))


def test_historical_real_source_evidence_matches_original_producer_git_bytes():
    evidence = json.loads((ROOT/"docs/us-readiness/us-real-source-preflight-actions-evidence-v1.json").read_text())
    assert evidence["verdict"] == "PASS"
    assert evidence["runId"] == 38211219882
    assert evidence["artifact"]["id"] == 11728239669
    assert evidence["observedCountsFromCompletedJobName"] == {
        "SPY": 7, "QQQ": 7, "successfulConstituentSample": 3, "validPriceRecords": 35}
    for path, sha in evidence["sourceCodeSha256FromProducerGitCommit"].items():
        original = subprocess.check_output(["git", "show", evidence["producerHeadSha"]+":"+path], cwd=ROOT)
        assert hashlib.sha256(original).hexdigest() == sha
    # The recorded workflow hash is historical; never substitute current CI bytes.
    assert evidence["sourceCodeSha256FromProducerGitCommit"][".github/workflows/tests.yml"] != hashlib.sha256(
        (ROOT/".github/workflows/tests.yml").read_bytes()).hexdigest()
