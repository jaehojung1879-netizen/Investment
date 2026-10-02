"""Synthetic ECOS contract tests; no external API or Alpha outcomes."""
import json
from urllib.error import URLError

import pytest

from pipeline import ecos_macro as EM
from pipeline.config import load_config


def spec(table="T", item="I", cycle="D"):
    return dict(seriesId=table, itemCode=item, cycle=cycle, sourceStatus="LIVE_VALIDATED_SOURCE")


def test_positional_contract_and_selectors():
    url = EM.build_url(api_key="SYNTHETIC", stat_code="T", cycle="M", start="202401", end="202402", item_code="I")
    assert url == "https://ecos.bok.or.kr/api/StatisticSearch/SYNTHETIC/json/kr/1/1000/T/M/202401/202402/I"
    assert not EM.build_url(api_key="K", stat_code="T", cycle="D", start="S", end="E", item_code_2="WRONG").endswith("WRONG")


@pytest.mark.parametrize("bad", [dict(seriesId="817Y002"), spec(item=None), spec(cycle=None),
                                {**spec(), "sourceStatus":"DATA_LINEAGE_UNRESOLVED"}])
def test_ambiguous_or_unverified_refused(bad):
    with pytest.raises(EM.AmbiguousSeries):
        EM.resolve_spec("KTB_3Y", bad, ecos_series={"CorpBond_3Y": bad})


def test_distinct_verified_items_in_same_table_are_valid():
    values = {"KTB_3Y":spec("817Y002", "G"), "CorpBond_3Y":spec("817Y002", "C")}
    assert EM.resolve_spec("KTB_3Y", values["KTB_3Y"], ecos_series=values)["itemCode"] == "G"


@pytest.mark.parametrize("value", [None, "", "-", "NaN", "inf", "bad"])
def test_missing_nonfinite_not_zero(value):
    assert EM.row_to_observation({"TIME":"202401", "DATA_VALUE":value})[1] is None


def test_numeric_and_envelope():
    assert EM.row_to_observation({"TIME":"202401", "DATA_VALUE":"1,234.5"}) == ("202401",1234.5)
    assert EM.parse_response({"StatisticSearch":{"row":[{}]}}) == ([{}],None)
    assert EM.parse_response("wrong")[1] == "INVALID_ENVELOPE"
    assert EM.parse_response({"RESULT":{"CODE":"ERROR-600", "MESSAGE":"credential in url"}}) == ([],"ERROR-600")


class Config:
    has_ecos=True
    ecos_api_key="SYNTHETIC_SECRET"
    ecos_series={"Rate":spec("R", "I", "D"), "CPI":spec("C", "I", "M")}


def test_mixed_native_cycles_and_periods(monkeypatch):
    calls=[]
    def request(key, service, *parts):
        calls.append(parts)
        cycle=parts[3]
        return {"StatisticSearch":{"list_total_count":1,"row":[{"TIME": "20240102" if cycle=="D" else "202401", "DATA_VALUE":"2"}]}},None
    monkeypatch.setattr(EM,"request",request)
    frame=EM.fetch_macro(Config(),"2024-01-02","2024-02-03")
    assert calls[0][3:6] == ("D","20240102","20240203")
    assert calls[1][3:6] == ("M","202401","202402")
    assert frame.attrs["nativeCycles"] == {"Rate":"D","CPI":"M"}
    assert frame.attrs["vintageStatus"] == "REVISED_HISTORY"


def test_transport_exception_never_printed(monkeypatch,capsys):
    def failure(*a,**k):
        raise URLError("https://example/SYNTHETIC_SECRET")
    monkeypatch.setattr("urllib.request.urlopen",failure)
    assert EM.request("SYNTHETIC_SECRET","StatisticSearch",1,10) == ({},"TRANSPORT_OR_DECODE_ERROR")
    assert capsys.readouterr().out == ""


def test_unverified_real_candidates_fail_closed():
    cfg,_=load_config()
    assert len(cfg.ecos_series)==9
    for name,value in cfg.ecos_series.items():
        assert "cycle" in value
        if value["sourceStatus"] != "LIVE_VALIDATED_SOURCE":
            with pytest.raises(EM.AmbiguousSeries):
                EM.resolve_spec(name,value,ecos_series=cfg.ecos_series)


def test_config_preserves_verified_native_fields(tmp_path):
    path=tmp_path/"cfg.json"
    path.write_text(json.dumps({"ecos":{"KR":{"CPI":spec("C","I","M")}}}))
    cfg,_=load_config(path)
    assert cfg.ecos_series["CPI"] == spec("C","I","M")


def test_no_key_or_no_config_abstains():
    cfg=Config();cfg.has_ecos=False
    assert EM.fetch_macro(cfg,"2024-01-01","2024-02-01") is None
    cfg.has_ecos=True;cfg.ecos_series={}
    assert EM.fetch_macro(cfg,"2024-01-01","2024-02-01") is None


def test_quarter_and_annual_periods():
    assert EM.period("2024-07-02","Q")=="2024Q3"
    assert EM.period("2024-07-02","A")=="2024"


def test_partial_paginated_series_is_discarded(monkeypatch):
    cfg=Config();cfg.ecos_series={'Rate':spec('R','I','D')}
    def request(key,service,*parts):
        if parts[0]==1:
            return {'StatisticSearch':{'list_total_count':1001,'row':[{'TIME':str(i),'DATA_VALUE':'1'} for i in range(1000)]}},None
        return {},'TRANSPORT_OR_DECODE_ERROR'
    monkeypatch.setattr(EM,'request',request)
    assert EM.fetch_macro(cfg,'2024-01-01','2024-02-01') is None
