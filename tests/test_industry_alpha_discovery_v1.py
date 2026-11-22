"""industry-alpha-discovery-v1: parsers, point-in-time signals and the outcome engine on synthetic inputs only."""
from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.industry_alpha_discovery_v1 import engine as E
from research.industry_alpha_discovery_v1 import execute as X
from research.industry_alpha_discovery_v1 import parse_motie_hwp as MH
from research.industry_alpha_discovery_v1 import signals as SG
from research.industry_alpha_discovery_v1.collect_releases import classify, parse_flash_text
from research.industry_alpha_discovery_v1.parse_all import parse_iip_pdf

HERE = Path(__file__).resolve().parents[1] / "research" / "industry_alpha_discovery_v1"


# ------------------------------------------------------------------ parsers
def test_classify_reads_all_title_variants():
    rows = [{"num": "1", "title": "’21년 5월 1일 ∼ 5월 20일 수출입 현황 관세청 2021.05.21 1p"},
            {"num": "2", "title": "2026년 11월 1일 ~ 11월 10일 수출입 현황 [잠정치] 재정경제부 2026.11.11 4p"},
            {"num": "3", "title": "2013년 4월 수출입 동향 산업통상자원부 2013.05.02 24p"},
            {"num": "4", "title": "2026년 9월 산업활동동향 국가데이터처 2026.10.30 95p"},
            {"num": "5", "title": "2026년 10월 정보통신산업(ICT) 수출입 동향 산업통상부 2026.11.15 24p"}]
    got = {(r["family"], r["refMonth"], r["published"]) for r in
           classify(rows, families=("MOTIE", "FLASH10", "FLASH20", "IIP"))}
    assert got == {("FLASH20", "2021-05", "2021-05-21"), ("FLASH10", "2026-11", "2026-11-11"),
                   ("MOTIE", "2013-04", "2013-05-02"), ("IIP", "2026-09", "2026-10-30")}


def test_flash_sentence_parser():
    txt = """보도시점 배포즉시 배포 2026. 11. 11.(수) 09:00
    ※조업일수 고려 시 [(’25) 7.0 일, (’26) 7.5 일]
    수출현황
    ㅇ (주요품목) 전년동기대비 반도체(331.2%), 석유제품(100.7%), 컴퓨터 주변기기
       (237.7%) 등 증가, 승용차(△4.3%) 등 감소
    ㅇ (주요국가) 중국(148.0%)"""
    p = parse_flash_text(txt)
    assert p["items"]["반도체"] == 331.2 and p["items"]["승용차"] == -4.3 and p["items"]["주변기기"] == 237.7
    assert p["releaseTime"] == "09:00"
    assert p["workingDays"] == {"prior": 7.0, "current": 7.5}


def test_flash_arrow_variant():
    p = parse_flash_text("ㅇ (주요품목) 승용차(27.2%↑), 반도체(△18.1%↓), 석유제품(△37.8%↓) ㅇ (주요품목) 반도체(△23.6%↓)")
    assert p["items"] == {"승용차": 27.2, "반도체": -18.1, "석유제품": -37.8}


def test_motie_hwp_table_maps_header_months():
    lines = ["< 13대 품목별 2월 수출실적 >", "(단위 : 백만달러, %)", "품목명", "’12년 전체", "’13년", "1월", "2월P", "1～2월P",
             "반도체", "(증가율)", "50,430", "4,036", "3,886", "7,922", "(0.6)", "(7.2)", "(0.4)", "(3.8)",
             "자동차", "(증가율)", "47,201", "3,600", "3,100", "6,700", "(5.0)", "(△1.0)", "(△12.5)", "(△6.0)"]
    p = MH.parse(lines, "2013-02")
    assert p["rows"]["반도체"] == {"2013-01": (4036.0, 7.2), "2013-02": (3886.0, 0.4)}
    assert p["rows"]["자동차"]["2013-02"] == (3100.0, -12.5)


def test_motie_header_with_stacked_year_prefixes_crosses_january():
    lines = ["② 15대 품목별 수출 추이", "(백만달러, 전년동기대비%, 비중%)", "품목명", "’21년 전체", "‘21년", "‘22년",
             "11월", "12월", "1월", "2월", "반도체", "128,000", "12,036", "12,781", "10,816", "10,368",
             "(29.0)", "(40.0)", "(35.1)", "(24.2)", "(23.8)"]
    p = MH.parse(lines, "2022-02")
    assert p["rows"]["반도체"] == {"2021-11": (12036.0, 40.0), "2021-12": (12781.0, 35.1),
                                 "2022-01": (10816.0, 24.2), "2022-02": (10368.0, 23.8)}


def test_motie_wrapped_item_names_are_joined():
    lines = ["< 13대 품목별 2월 수출실적 >", "품목명", "’13년", "1월", "2월P",
             "반도체", "(증가율)", "4,036", "3,886", "(7.2)", "(0.4)",
             "석유", "제품", "(증가율)", "4,500", "4,000", "(1.0)", "(△2.0)"]
    rows = MH.parse(lines, "2013-02")["rows"]
    assert set(rows) == {"반도체", "석유제품"} and rows["석유제품"]["2013-02"] == (4000.0, -2.0)


def test_motie_half_year_columns():
    lines = ["< 13대 품목별 상반기 수출실적 >", "(단위 : 백만달러, %)", "품목명", "‘14", "상반기", "’15", "1월", "2월",
             "6월P", "1～6월P", "반도체", "(증가율)", "29,243", "5,263", "4,760", "5,331", "31,018",
             "(10.6)", "(13.3)", "(7.0)", "(3.4)", "(6.1)"]
    assert MH.parse(lines, "2015-06")["rows"]["반도체"] == {"2015-01": (5263.0, 13.3), "2015-02": (4760.0, 7.0),
                                                          "2015-06": (5331.0, 3.4)}


def test_hwp_section_records():
    from research.industry_alpha_discovery_v1.hwp_text import section_lines

    def rec(tag, payload):
        return struct.pack("<I", tag | (len(payload) << 20)) + payload
    # an inline control (char 11 + 7 units of payload) inside the first paragraph is dropped
    ctrl = struct.pack("<H", 11) + b"\x00" * 14
    body = (rec(67, "반".encode("utf-16-le") + ctrl + "도체".encode("utf-16-le")) + rec(66, b"\x00" * 4)
            + rec(67, "4,036".encode("utf-16-le")))
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    assert section_lines(zlib.decompress(comp.compress(body) + comp.flush(), -15)) == ["반도체", "4,036"]


def test_iip_combined_row():
    txt = """○ 업종별 생산·출하·재고                                    전 동 월비
                     가중치 전월비 동월비 가중치 전월비 동월비 가중치 전월비 동월비
 19.     석유정제         277.6     3.7     -1.4    758.1     2.8     -4.5    510.3         6.3           9.6
 261.     반도체        1867.1    19.2    10.3     945.4     1.1      6.4   1430.1         7.4          21.6
"""
    r = parse_iip_pdf(txt)
    assert r["SEMI"] == {"productionYoy": 10.3, "shipmentYoy": 6.4, "inventoryYoy": 21.6, "layout": "COMBINED"}
    assert r["PETRO"]["inventoryYoy"] == 9.6


# ------------------------------------------------------------------ point-in-time signals
def _motie_rows():
    rows = []
    months = pd.period_range("2012-01", "2014-12", freq="M")
    for k, m in enumerate(months[12:]):
        pub = (m + 1).to_timestamp() + pd.Timedelta(days=0)
        for j, mm in enumerate([m - 1, m]):
            v = 100 + 10 * np.sin((k + j) / 3)
            rows.append({"releaseRefMonth": str(m), "published": pub, "item": "반도체", "valueMonth": str(mm),
                         "valueMusd": v * (1.001 if j == 0 else 1.0), "statedGrowthPct": 5.0 + j,
                         "vintage": "FIRST_RELEASE" if mm == m else "LATER_RELEASE", "num": str(k)})
    return pd.DataFrame(rows)


def test_asof_never_sees_a_later_release():
    r = SG.item_rows(_motie_rows(), "SEMI")
    v = SG.asof_values(r, "2013-06-15")
    assert max(v) <= "2013-05"
    # the 2013-05 value is the FIRST release (published 2013-06-01); its revision arrives on 2013-07-01
    v2 = SG.asof_values(r, "2013-07-15")
    assert v2["2013-05"][0] != v["2013-05"][0]


def test_revision_after_decision_cannot_change_signal():
    rows = _motie_rows()
    a = SG.monthly_signals(rows, "SEMI")
    late = rows.copy()
    late.loc[late["published"] > pd.Timestamp("2014-03-01"), "valueMusd"] *= 3
    b = SG.monthly_signals(late, "SEMI")
    early = a["published"] <= pd.Timestamp("2014-03-01")
    pd.testing.assert_series_equal(a.loc[early, "g3"], b.loc[early, "g3"])


def test_flash_surprise_uses_strictly_earlier_reading():
    flash = pd.DataFrame([{"family": "FLASH10", "refMonth": "2014-02", "published": "2014-02-11", "item": "반도체",
                           "yoyPct": 20.0},
                          {"family": "FLASH20", "refMonth": "2014-02", "published": "2014-02-21", "item": "반도체",
                           "yoyPct": 10.0}])
    monthly = pd.DataFrame([{"industry": "SEMI", "published": pd.Timestamp("2014-02-01"), "yoy1": 0.05},
                            {"industry": "SEMI", "published": pd.Timestamp("2014-02-21"), "yoy1": 0.99}])
    s = SG.flash_surprises(flash, monthly)
    assert s.iloc[0]["surprise"] == pytest.approx(0.15) and s.iloc[0]["priorSource"] == "MOTIE"
    assert s.iloc[1]["surprise"] == pytest.approx(-0.10) and s.iloc[1]["priorSource"] == "FLASH"


# ------------------------------------------------------------------ engine
def _market(seed=1):
    idx = pd.bdate_range("2012-01-02", "2026-11-20")
    rng = np.random.default_rng(seed)
    cols = json.loads((HERE / "data" / "price-manifest.json").read_text())
    data = {t: 100 * np.exp(np.cumsum(rng.normal(0, .01, len(idx)))) for t in cols}
    return E.Market(pd.DataFrame(data, index=idx))


def test_entry_is_strictly_after_publication():
    mkt = _market()
    i = mkt.entry_session("2020-03-02")
    assert mkt.sessions[i] == pd.Timestamp("2020-03-03")
    assert mkt.sessions[mkt.entry_session("2020-03-02", same_day=True)] == pd.Timestamp("2020-03-02")


def test_ols_hac_recovers_slope_and_holm():
    rng = np.random.default_rng(0)
    x = rng.normal(size=400)
    y = 2 * x + rng.normal(size=400)
    r = E.ols_hac(y, x, 5)
    assert abs(r["coef"][1] - 2) < .2
    assert E.holm({"a": .01, "b": .04, "c": .03}) == {"a": .03, "c": .06, "b": .06}


def test_tilt_path_costs_and_constant_exposure():
    mkt = _market()
    dec = pd.DataFrame({"entryIdx": [300, 400, 500], "on": [True, False, True]})
    p = E.tilt_path(mkt, ["005930.KS", "000660.KS"], dec, .3, start=300, end=700)
    assert .85 < p["turnover"] < .95          # three 0.3 switches; the sleeve drifts between them
    never = E.tilt_path(mkt, ["005930.KS"], dec.assign(on=False), .3, start=300, end=700)
    bench = mkt.close["069500.KS"].iloc[300:701]
    assert never["nav"].iloc[-1] == pytest.approx(bench.iloc[-1] / bench.iloc[0])


def test_sell_tax_schedule_is_dated():
    assert E.sell_tax_bps("2019-06-02") == 30 and E.sell_tax_bps("2025-06-01") == 15 and E.sell_tax_bps("2026-02-01") == 20


def test_execute_refuses_without_authorization(tmp_path, monkeypatch):
    monkeypatch.setattr(X, "HERE", tmp_path)
    (tmp_path / "protocol.json").write_text("{}")
    (tmp_path / "authorization.json").write_text(json.dumps({"protocolSha256": "0" * 64, "codeSha256": {},
                                                             "inputSha256": {}}))
    with pytest.raises(SystemExit, match="PROTOCOL_CHANGED"):
        X.check_authorization()


def test_full_pipeline_runs_on_synthetic_world():
    mkt = _market(3)
    months = pd.period_range("2012-01", "2026-09", freq="M")
    rng = np.random.default_rng(5)
    rows, flash, iip = [], [], []
    for k, m in enumerate(months):
        pub = (m + 1).to_timestamp()
        for item in ("반도체", "자동차", "석유제품", "선박"):
            for j, mm in enumerate([m - 2, m - 1, m]):
                rows.append({"releaseRefMonth": str(m), "published": pub, "item": item, "valueMusd": 100 + rng.normal(),
                             "valueMonth": str(mm), "statedGrowthPct": rng.normal(5, 10),
                             "vintage": "FIRST_RELEASE" if j == 2 else "LATER_RELEASE", "num": str(k)})
        if m >= pd.Period("2021-01", "M"):
            for fam, day in (("FLASH10", 11), ("FLASH20", 21)):
                flash.append({"family": fam, "refMonth": str(m), "published": f"{m}-{day}", "item": "반도체",
                              "yoyPct": rng.normal(5, 20), "workingDaysPrior": 7.0, "workingDaysCurrent": 7.5})
        if m >= pd.Period("2015-01", "M"):
            iip.append({"refMonth": str(m), "published": str((m + 1).to_timestamp() + pd.Timedelta(days=28))[:10],
                        "industry": "SEMI", "productionYoy": rng.normal(), "shipmentYoy": rng.normal(),
                        "inventoryYoy": rng.normal(), "layout": "COMBINED"})
    motie = pd.DataFrame(rows)
    monthly = SG.monthly_signals(motie, "SEMI")
    h1 = X.run_h1(mkt, pd.DataFrame(flash), monthly)
    assert h1["tests"]["H21"]["status"] == "ESTIMATED" and set(h1["strategies"]) >= {"B0", "P", "S", "SP"}
    quarters = pd.read_csv(HERE.parent / "investment_decision_alpha_v1" / "results" / "kr-semis-case-quarters.csv")
    h2 = X.run_h2(mkt, motie, quarters)
    assert h2["SEMI"]["tests"]["H126"]["status"] == "ESTIMATED"
    assert h2["SEMI"]["revisions"]["accelCompared"] > 0
    h3 = X.run_h3(mkt, pd.DataFrame(iip))
    assert h3["status"] == "ESTIMATED"
    assert X.run_h3(mkt, pd.DataFrame(iip[:30]))["status"] == "NOT_ESTIMABLE_DATA_GATE"


def test_protocol_seal_matches():
    import hashlib
    sealed = (HERE / "protocol.sha256").read_text().split()[0]
    assert hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest() == sealed


def test_protocol_data_identity_matches_committed_inputs():
    import hashlib
    p = json.loads((HERE / "protocol.json").read_text())
    for rel, h in p["dataIdentity"].items():
        if rel.startswith("data/"):
            assert hashlib.sha256((HERE / rel).read_bytes()).hexdigest() == h, rel
