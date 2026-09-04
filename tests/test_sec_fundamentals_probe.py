"""The SEC probe's parsing, which must hold without a vendor.

The network half can only run in CI. What is pinned here is the part that
decides what the probe's answer MEANS: which US-GAAP tag a concept resolved
to, that a `dei:` share-count tag is looked up in a different namespace than
the `us-gaap:` financial-statement tags, and that a quarterly duration fact's
period length is read from its own `start`/`end` rather than assumed.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "probe_sec_fundamentals", ROOT / "scripts" / "probe_sec_fundamentals.py")
P = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = P
_spec.loader.exec_module(P)


def _facts(**tags):
    """A minimal companyfacts payload: {tag: [fact, ...]} under us-gaap."""
    return {"entityName": "Test Co", "facts": {
        "us-gaap": {tag: {"units": {"USD": rows}} for tag, rows in tags.items()},
        "dei": {},
    }}


# --------------------------------------------------------------------------- #
# Tag resolution — filers do not agree on tags the way DART filers mostly
# agree on Korean labels
# --------------------------------------------------------------------------- #
def test_the_first_candidate_tag_present_is_used():
    payload = _facts(NetIncomeLoss=[{"val": 100, "form": "10-K", "filed": "2024-02-01",
                                     "fy": 2023, "start": "2023-01-01", "end": "2023-12-31"}])
    entry = P.parse_companyfacts(payload)
    assert entry["accounts"]["netIncome"]["tag"] == "NetIncomeLoss"


def test_a_later_alias_is_used_when_the_first_candidate_is_absent():
    """`Revenues` is the first candidate; a filer using the newer ASC 606 tag
    must still resolve, not read as revenue-less."""
    payload = _facts(RevenueFromContractWithCustomerExcludingAssessedTax=[
        {"val": 500, "form": "10-K", "filed": "2024-02-01", "fy": 2023}])
    entry = P.parse_companyfacts(payload)
    assert entry["accounts"]["revenue"]["tag"] == \
        "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_a_concept_with_no_matching_tag_is_reported_missing_not_guessed():
    entry = P.parse_companyfacts(_facts())
    assert entry["accounts"]["equity"]["tag"] is None
    assert entry["accounts"]["equity"]["candidatesChecked"] == P.CANDIDATE_TAGS["equity"]


# --------------------------------------------------------------------------- #
# Share counts live in a different namespace than the financial statements
# --------------------------------------------------------------------------- #
def test_share_counts_are_read_from_the_dei_namespace_not_us_gaap():
    payload = _facts(NetIncomeLoss=[{"val": 100, "form": "10-K",
                                     "filed": "2024-02-01", "fy": 2023}])
    payload["facts"]["dei"] = {
        "EntityCommonStockSharesOutstanding": {
            "units": {"shares": [{"val": 1_000_000, "end": "2024-01-01"}]}}}
    entry = P.parse_companyfacts(payload)
    assert entry["sharesTag"] == "EntityCommonStockSharesOutstanding"
    assert entry["sharesFactCount"] == 1


def test_no_dei_share_tag_is_reported_rather_than_falling_back_to_us_gaap():
    entry = P.parse_companyfacts(_facts())
    assert entry["sharesTag"] is None
    assert "sharesFactCount" not in entry


# --------------------------------------------------------------------------- #
# Filed dates — the field the whole plan hangs on, same as DART's receipt date
# --------------------------------------------------------------------------- #
def test_filed_date_coverage_is_counted_against_every_fact_not_just_some():
    payload = _facts(NetIncomeLoss=[
        {"val": 100, "form": "10-K", "filed": "2024-02-01", "fy": 2023},
        {"val": 90, "form": "10-K", "fy": 2022},  # no filed date
    ])
    entry = P.parse_companyfacts(payload)
    assert entry["factCount"] == 2
    assert entry["hasFiledDate"] == 1, "누락된 filed는 있는 것으로 세면 안 된다"


# --------------------------------------------------------------------------- #
# Quarterly duration is arithmetic on start/end, not a guessed column
# --------------------------------------------------------------------------- #
def test_the_quarterly_period_length_is_computed_from_its_own_start_and_end():
    payload = _facts(NetIncomeLoss=[
        {"val": 30, "form": "10-Q", "filed": "2023-11-01",
         "start": "2023-07-01", "end": "2023-09-30", "fy": 2023},
    ])
    entry = P.parse_companyfacts(payload)
    assert entry["sampleQuarterlyFact"]["days"] == 91
    assert entry["sampleQuarterlyFact"]["filed"] == "2023-11-01"


def test_an_annual_only_company_reports_no_quarterly_sample_rather_than_a_guess():
    payload = _facts(NetIncomeLoss=[
        {"val": 100, "form": "10-K", "filed": "2024-02-01", "fy": 2023}])
    entry = P.parse_companyfacts(payload)
    assert "sampleQuarterlyFact" not in entry


# --------------------------------------------------------------------------- #
# What the model actually reads
# --------------------------------------------------------------------------- #
def test_every_factor_input_the_production_model_needs_is_probed():
    covered = {item for inputs in P.FACTOR_INPUTS.values() for item in inputs}
    for needed in ("netIncome", "equity", "revenue", "operatingIncome",
                  "liabilities", "operatingCashFlow", "capex", "sharesOutstanding"):
        assert needed in covered, f"{needed} 없이는 만들 수 없는 팩터가 있다"


def test_multiple_tag_aliases_are_checked_where_filers_disagree():
    assert len(P.CANDIDATE_TAGS["revenue"]) > 1
    assert len(P.CANDIDATE_TAGS["netIncome"]) > 1


# --------------------------------------------------------------------------- #
# Retries — found live: the probe's first real run reported "SEC blocks this"
# about a request the already-working 13F reader would have retried past.
# `_request` must match that reader's retry behaviour, not its own guess.
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _http_error(code):
    import urllib.error
    return urllib.error.HTTPError("https://example.invalid/x", code, "err", {}, None)


def test_a_403_is_retried_and_a_later_success_is_returned(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=30):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(403)
        return _FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(P.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(P.time, "sleep", lambda s: None)

    raw, error = P._request("https://example.invalid/x")
    assert raw == b'{"ok": true}' and error == ""
    assert calls["n"] == 3, "세 번째 시도에서 성공했어야 한다"


def test_a_persistent_403_is_reported_after_the_retry_budget_is_spent(monkeypatch):
    monkeypatch.setattr(P.urllib.request, "urlopen",
                        lambda req, timeout=30: (_ for _ in ()).throw(_http_error(403)))
    monkeypatch.setattr(P.time, "sleep", lambda s: None)

    raw, error = P._request("https://example.invalid/x")
    assert raw is None and error == "HTTP 403"


def test_a_403_that_survives_retries_reports_its_body_not_just_the_code(monkeypatch):
    """The status code alone does not say WHO is refusing — SEC's own bot
    policy, a CDN challenge page, and a network block all answer 403."""
    import io
    import urllib.error

    def fake_urlopen(req, timeout=30):
        raise urllib.error.HTTPError(
            "https://example.invalid/x", 403, "err", {},
            io.BytesIO(b"Your Request Originates from an Undeclared Automated Tool"))

    monkeypatch.setattr(P.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(P.time, "sleep", lambda s: None)

    raw, error = P._request("https://example.invalid/x")
    assert raw is None
    assert "Undeclared Automated Tool" in error, \
        "차단 메시지가 있으면 상태코드만 말고 그 내용을 담아야 진단이 된다"


def test_a_non_retryable_status_fails_on_the_first_attempt(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=30):
        calls["n"] += 1
        raise _http_error(404)

    monkeypatch.setattr(P.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(P.time, "sleep", lambda s: None)

    raw, error = P._request("https://example.invalid/x")
    assert raw is None and error == "HTTP 404"
    assert calls["n"] == 1, "재시도해도 소용없는 상태코드를 세 번 두드리면 안 된다"


# --------------------------------------------------------------------------- #
# CIK resolution — a blocked ticker map must not also block measuring the
# endpoint that actually matters (companyfacts, a different host)
# --------------------------------------------------------------------------- #
def test_a_blocked_ticker_map_falls_back_to_known_ciks_for_default_samples(monkeypatch):
    monkeypatch.setattr(P.urllib.request, "urlopen",
                        lambda req, timeout=30: (_ for _ in ()).throw(_http_error(403)))
    monkeypatch.setattr(P.time, "sleep", lambda s: None)

    cik_map, source, error = P.ticker_to_cik(["AAPL", "ZZZZ"])
    assert cik_map["AAPL"] == P.KNOWN_CIKS["AAPL"]
    assert source["AAPL"] == "KNOWN_CIKS fallback"
    assert "ZZZZ" not in cik_map, "폴백에도 없는 티커를 지어내면 안 된다"
    assert error == "HTTP 403"


def test_a_working_ticker_map_is_preferred_over_the_fallback(monkeypatch):
    import json as _json
    payload = _json.dumps(
        {"0": {"cik_str": 999999, "ticker": "AAPL", "title": "Apple"}}).encode()
    monkeypatch.setattr(P.urllib.request, "urlopen",
                        lambda req, timeout=30: _FakeResponse(payload))

    cik_map, source, error = P.ticker_to_cik(["AAPL"])
    assert cik_map["AAPL"] == "0000999999"
    assert source["AAPL"] == "company_tickers.json"
    assert error == ""
