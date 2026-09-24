"""What the ECOS fetch layer has to get right, against a mocked response.

NOT EXECUTED LIVE — no ECOS_API_KEY exists in this environment. Every test
here either calls pure functions with synthetic ECOS-shaped payloads, or
monkeypatches `urllib.request.urlopen` so `fetch_macro` never makes a real
request. A live smoke test is a separate, later `workflow_dispatch` step —
see `pipeline/ecos_macro.py`'s own module docstring.
"""
from __future__ import annotations

import json

from pipeline import ecos_macro as EM


# --------------------------------------------------------------------------- #
# URL construction — positional, not query-string
# --------------------------------------------------------------------------- #
def test_build_url_is_positional_and_in_ecos_order():
    url = EM.build_url(api_key="KEY123", stat_code="722Y001", cycle="D",
                       start="20130101", end="20260101")
    assert url == ("https://ecos.bok.or.kr/api/StatisticSearch/KEY123/json/kr/"
                   "20130101/20260101/722Y001/D")


def test_build_url_appends_item_code_when_given():
    url = EM.build_url(api_key="KEY123", stat_code="817Y002", cycle="D",
                       start="20130101", end="20260101", item_code="0101000")
    assert url.endswith("/817Y002/D/0101000")


def test_build_url_omits_item_code_2_without_item_code():
    url = EM.build_url(api_key="KEY123", stat_code="722Y001", cycle="D",
                       start="20130101", end="20260101", item_code_2="X")
    assert "X" not in url, "item_code_2 without item_code must not be appended"


# --------------------------------------------------------------------------- #
# resolve_spec — the 817Y002 ambiguity refusal
# --------------------------------------------------------------------------- #
def test_a_series_with_its_own_item_code_resolves_cleanly():
    series = {"KTB_3Y": {"seriesId": "817Y002", "itemCode": "0101000"}}
    resolved = EM.resolve_spec("KTB_3Y", series["KTB_3Y"], ecos_series=series)
    assert resolved == {"seriesId": "817Y002", "itemCode": "0101000"}


def test_a_series_with_no_sharer_and_no_item_code_resolves_fine():
    series = {"BaseRate": {"seriesId": "722Y001", "itemCode": None}}
    resolved = EM.resolve_spec("BaseRate", series["BaseRate"], ecos_series=series)
    assert resolved == {"seriesId": "722Y001", "itemCode": None}


def test_two_series_sharing_a_seriesid_with_no_itemcode_is_refused():
    """The exact KTB_3Y / CorpBond_3Y ambiguity — never guessed at."""
    series = {
        "KTB_3Y": {"seriesId": "817Y002", "itemCode": None},
        "CorpBond_3Y": {"seriesId": "817Y002", "itemCode": None},
    }
    try:
        EM.resolve_spec("KTB_3Y", series["KTB_3Y"], ecos_series=series)
        assert False, "expected AmbiguousSeries"
    except EM.AmbiguousSeries as exc:
        assert "CorpBond_3Y" in str(exc)


# --------------------------------------------------------------------------- #
# parse_response
# --------------------------------------------------------------------------- #
def test_a_normal_envelope_yields_its_rows():
    payload = {"StatisticSearch": {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상"},
                                   "row": [{"TIME": "20240102", "DATA_VALUE": "3.50"}]}}
    rows, error = EM.parse_response(payload)
    assert error is None and len(rows) == 1


def test_an_error_result_inside_the_envelope_is_reported_not_read_as_data():
    payload = {"StatisticSearch": {"RESULT": {"CODE": "ERROR-100", "MESSAGE": "필수 파라미터 오류"}}}
    rows, error = EM.parse_response(payload)
    assert rows == [] and "필수 파라미터" in error


def test_a_bare_top_level_result_is_a_transport_error():
    payload = {"RESULT": {"CODE": "ERROR-600", "MESSAGE": "인증키가 유효하지 않습니다"}}
    rows, error = EM.parse_response(payload)
    assert rows == [] and "인증키" in error


def test_an_unrecognised_payload_shape_is_reported_not_crashed_on():
    rows, error = EM.parse_response({"unexpected": "shape"})
    assert rows == [] and error is not None
    rows2, error2 = EM.parse_response("not even a dict")
    assert rows2 == [] and error2 is not None


# --------------------------------------------------------------------------- #
# row_to_observation
# --------------------------------------------------------------------------- #
def test_row_to_observation_parses_a_normal_row():
    date, value = EM.row_to_observation({"TIME": "20240102", "DATA_VALUE": "3.50"})
    assert date == "20240102" and value == 3.50


def test_row_to_observation_never_fabricates_a_zero_for_a_blank_value():
    for blank in ("", "-", None):
        date, value = EM.row_to_observation({"TIME": "20240102", "DATA_VALUE": blank})
        assert value is None


def test_row_to_observation_handles_comma_thousands():
    _, value = EM.row_to_observation({"TIME": "202401", "DATA_VALUE": "1,234.5"})
    assert value == 1234.5


# --------------------------------------------------------------------------- #
# fetch_macro — mocked network only
# --------------------------------------------------------------------------- #
class _FakeConfig:
    has_ecos = True
    ecos_api_key = "FAKEKEY"

    def __init__(self, series):
        self._series = series

    @property
    def ecos_series(self):
        return self._series


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_macro_returns_none_without_a_key():
    cfg = _FakeConfig({"BaseRate": {"seriesId": "722Y001", "itemCode": None}})
    cfg.has_ecos = False
    assert EM.fetch_macro(cfg, "2013-01-01", "2026-01-01") is None


def test_fetch_macro_returns_none_with_no_configured_series():
    cfg = _FakeConfig({})
    assert EM.fetch_macro(cfg, "2013-01-01", "2026-01-01") is None


def test_fetch_macro_builds_a_frame_from_a_mocked_response(monkeypatch):
    cfg = _FakeConfig({"BaseRate": {"seriesId": "722Y001", "itemCode": None}})
    body = json.dumps({"StatisticSearch": {
        "RESULT": {"CODE": "INFO-000"},
        "row": [{"TIME": "20240102", "DATA_VALUE": "3.50"},
               {"TIME": "20240103", "DATA_VALUE": "3.50"}]}}).encode("utf-8")

    def fake_urlopen(url, timeout=30):
        assert "722Y001" in url
        return _FakeResponse(body)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    frame = EM.fetch_macro(cfg, "2013-01-01", "2026-01-01")
    assert frame is not None
    assert "BaseRate" in frame.columns
    assert frame["BaseRate"]["20240102"] == 3.50


def test_fetch_macro_skips_an_ambiguous_pair_and_still_returns_the_rest(monkeypatch):
    cfg = _FakeConfig({
        "BaseRate": {"seriesId": "722Y001", "itemCode": None},
        "KTB_3Y": {"seriesId": "817Y002", "itemCode": None},
        "CorpBond_3Y": {"seriesId": "817Y002", "itemCode": None},
    })
    body = json.dumps({"StatisticSearch": {
        "RESULT": {"CODE": "INFO-000"},
        "row": [{"TIME": "20240102", "DATA_VALUE": "3.50"}]}}).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=30: _FakeResponse(body))
    frame = EM.fetch_macro(cfg, "2013-01-01", "2026-01-01")
    assert frame is not None
    assert "BaseRate" in frame.columns
    assert "KTB_3Y" not in frame.columns and "CorpBond_3Y" not in frame.columns


# --------------------------------------------------------------------------- #
# Vintage status
# --------------------------------------------------------------------------- #
def test_pit_status_is_revised_history_not_pit_exact():
    from pipeline import pit_data
    assert EM.PIT_STATUS_FOR_ALL_SERIES == pit_data.REVISED_HISTORY


# --------------------------------------------------------------------------- #
# config.json's real ecos.KR block — the schema fix this study made
# --------------------------------------------------------------------------- #
def test_real_config_normalizes_both_bare_strings_and_itemcode_objects():
    from pipeline.config import load_config

    cfg, _ = load_config()
    kr = cfg.ecos_regions.get("KR", {})
    # A bare-string series (no ambiguity) normalizes to {"seriesId", "itemCode": None}.
    assert kr["BaseRate"] == {"seriesId": "722Y001", "itemCode": None}
    # The two series that share 817Y002 both carry the new itemCode field,
    # explicitly unresolved rather than silently absent or guessed.
    assert kr["KTB_3Y"]["seriesId"] == "817Y002"
    assert kr["CorpBond_3Y"]["seriesId"] == "817Y002"
    assert kr["KTB_3Y"]["itemCode"] is None
    assert kr["CorpBond_3Y"]["itemCode"] is None


def test_real_config_ktb_and_corpbond_are_refused_as_ambiguous_until_resolved():
    from pipeline.config import load_config

    cfg, _ = load_config()
    series = cfg.ecos_series
    try:
        EM.resolve_spec("KTB_3Y", series["KTB_3Y"], ecos_series=series)
        assert False, "expected AmbiguousSeries until item codes are resolved"
    except EM.AmbiguousSeries:
        pass
