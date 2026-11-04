"""Network-free tests on invented rows for the alpha-mechanism-sprint-v1 audit."""
from __future__ import annotations

import ast
import sys
from datetime import date
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import collect  # noqa: E402
import sprint  # noqa: E402


def row(name, dt, no):
    return {"report_nm": name, "rcept_dt": dt, "rcept_no": no}


def test_classify_uses_exact_report_names():
    assert sprint.classify("연결재무제표기준영업(잠정)실적(공정공시)") == sprint.PRELIM
    assert sprint.classify("[기재정정]영업(잠정)실적(공정공시)") == sprint.PRELIM
    assert sprint.classify("매출액또는손익구조30%(대규모법인은15%)이상변동") == sprint.PNL_CHANGE
    assert sprint.classify("영업실적등에대한전망(공정공시)") == sprint.GUIDANCE
    assert sprint.classify("분기보고서 (2024.03)") == sprint.FORMAL
    assert sprint.classify("기업설명회(IR)개최(안내공시)") == sprint.OTHER
    assert sprint.is_amendment("[기재정정]분기보고서 (2024.03)")
    assert not sprint.is_amendment("분기보고서 (2024.03)")


def test_prelim_maps_to_quarter_just_ended_and_amendments_are_ignored():
    rows = [row("영업(잠정)실적(공정공시)", "20240405", "20240405800001"),
            row("[기재정정]영업(잠정)실적(공정공시)", "20240402", "20240402800001"),
            row("연결재무제표기준영업(잠정)실적(공정공시)", "20240430", "20240430800051"),
            row("분기보고서 (2024.03)", "20240516", "20240516000001"),
            row("[기재정정]분기보고서 (2024.03)", "20240401", "20240401000001")]
    firsts = sprint.first_originals(rows)
    assert firsts[(sprint.PRELIM, date(2024, 3, 31))]["rcept_no"] == "20240405800001"
    assert firsts[(sprint.FORMAL, date(2024, 3, 31))]["rcept_dt"] == "20240516"
    assert sprint.previous_quarter_end(date(2024, 1, 2)) == date(2023, 12, 31)
    assert sprint.previous_quarter_end(date(2024, 3, 31)) == date(2023, 12, 31)


def test_member_quarters_use_first_snapshot_after_quarter_end():
    snaps = [{"date": "2024-03-04", "code": "A", "rank": 10},
             {"date": "2024-04-01", "code": "A", "rank": 130},
             {"date": "2024-04-01", "code": "B", "rank": 50}]
    member = sprint.member_quarters(snaps, [date(2024, 3, 31)])
    assert member[date(2024, 3, 31)] == {"B"}


def test_coverage_counts_only_prelims_not_after_formal():
    sessions = [date(2024, 4, d) for d in (1, 2, 3, 4, 5, 8)] + [date(2024, 5, d) for d in range(1, 31)]
    member = {date(2024, 3, 31): {"A", "B", "C"}}
    code_to_corp = {"A": "001", "B": "002"}
    firsts = {
        "001": {(sprint.PRELIM, date(2024, 3, 31)): row("영업(잠정)실적", "20240405", "1"),
                (sprint.FORMAL, date(2024, 3, 31)): row("분기보고서 (2024.03)", "20240516", "2")},
        "002": {(sprint.PRELIM, date(2024, 3, 31)): row("영업(잠정)실적", "20240520", "3"),
                (sprint.FORMAL, date(2024, 3, 31)): row("분기보고서 (2024.03)", "20240516", "4")},
    }
    table = sprint.coverage_table(member, code_to_corp, firsts, sessions)
    summary = sprint.summarize(table["units"])["overall"]
    assert summary["memberIssuerQuarters"] == 2
    assert summary["withPrelimNotAfterFormal"] == 1
    assert summary["coveragePct"] == 50.0
    assert table["unresolvedMemberSecuritiesByYear"] == {2024: 1}
    lead = [u for u in table["units"] if u["corp"] == "001"][0]["leadSessions"]
    assert lead == sprint.session_count_between(sessions, date(2024, 4, 5), date(2024, 5, 16))


def test_parse_prelim_text_reads_current_and_prior_year_with_unit():
    text = ("삼성전자/연결재무제표기준영업(잠정)실적(공정공시)/(2024.04.30) ※ 동 정보는 잠정치로서 단위 : 억원, % 구분 당기실적 전기실적 전기대비증감율(%) "
            "전년동기실적 전년동기대비증감율(%) ('24.1Q) ('23.4Q) ('23.1Q) 매출액 당해실적 719,156 677,799 6.10 637,454 12.82 "
            "누계실적 719,156 2,589,355 - 637,454 12.82 영업이익 당해실적 66,060 28,247 133.87 6,402 931.87 "
            "당기순이익 당해실적 (1,200) 63,448 - 15,746 -")
    parsed = sprint.parse_prelim_text(text)
    assert parsed["unit"] == "억원" and parsed["consolidated"]
    assert parsed["revenue"] == pytest.approx(719156e8)
    assert parsed["revenuePriorYear"] == pytest.approx(637454e8)
    assert parsed["operatingIncome"] == pytest.approx(66060e8)
    assert parsed["netIncome"] == pytest.approx(-1200e8)
    assert sprint.period_label_quarter(parsed["periodLabel"]) == (2024, 3)


def test_missing_figure_is_none_not_zero():
    parsed = sprint.parse_prelim_text("단위 : 백만원 매출액 당해실적 - - - - -")
    assert parsed["revenue"] is None and parsed["netIncome"] is None


def test_mde_shrinks_with_cohorts_and_cohorts_needed_inverts_it():
    one = sprint.mde(0.3, 40, 0.05, 1)
    assert sprint.mde(0.3, 40, 0.05, 4) == pytest.approx(one / 2)
    assert sprint.mde(0.3, 40, 0.05, sprint.cohorts_needed(0.3, 40, 0.05, 0.03)) == pytest.approx(0.03)


def test_walk_reads_every_page_and_fails_closed_on_changed_result_set():
    pages = {1: {"status": "000", "total_page": 2, "total_count": 3,
                 "list": [{"rcept_no": "1", "report_nm": "a"}, {"rcept_no": "2", "report_nm": "b"}]},
             2: {"status": "000", "total_page": 2, "total_count": 3, "list": [{"rcept_no": "3", "report_nm": "c"}]}}
    budget = {"calls": 0, "max": 10}
    rows = collect.walk(lambda c, t, p: pages[p], "X", "I", budget)
    assert [r["rcept_no"] for r in rows] == ["1", "2", "3"] and budget["calls"] == 2
    pages[2]["total_count"] = 4
    with pytest.raises(collect.SourceError):
        collect.walk(lambda c, t, p: pages[p], "X", "I", {"calls": 0, "max": 10})
    with pytest.raises(collect.CallBudgetExhausted):
        collect.walk(lambda c, t, p: pages[p], "X", "I", {"calls": 0, "max": 1})
    assert collect.walk(lambda c, t, p: {"status": "013"}, "X", "I", {"calls": 0, "max": 1}) == []


def test_no_module_reads_prices_returns_or_labels():
    forbidden = {"replay_valuation", "kelly_portfolio", "historical_outcomes", "price_adjustment",
                 "attach_labels", "target_from_sessions", "outcomes"}
    for name in ("sprint.py", "analyze.py", "collect.py", "sample_docs.py"):
        tree = ast.parse((HERE / name).read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names |= {a.name.split(".")[-1] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        names |= {(n.module or "").split(".")[-1] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not names & forbidden, (name, names & forbidden)


MONTHLY = ("※ 동 정보는 잠정치로서 향후 확정치와는 다를 수 있음. 1. 실적내용 구분(단위 : 백만원, %) 당기실적 전기실적 "
           "전기대비증감율(%) 전년동기실적 전년동기대비증감율(%) (2016.9월) (2016.8월) (2015.9월) 매출액 당해실적 - - - - - "
           "영업이익 당해실적 - - - - - 당기순이익 당해실적 - - - - - 수주(백만불, 누계기준) 5,415 5,274 - 10,664 -49.22 "
           "2. 정보제공내역")
ANNUAL = ("※ 동 정보는 잠정치로서 1. 연결실적내용 단위 : 억원, % 구분 당기실적 전기실적 전기대비증감율(%) 전년동기실적 "
          "전년동기대비증감율(%) ('17년 연간 ) ('16년 연간) - 매출액 당해실적 62,705 60,941 2.9% - - 누계실적 - - - - - "
          "영업이익 당해실적 9,303 8,809 5.6% - - 당기순이익 당해실적 6,185 5,792 6.8% - - 2. 정보제공내역")


def test_monthly_operating_filing_on_the_prelim_form_is_not_an_earnings_disclosure():
    parsed = sprint.parse_prelim_text(MONTHLY)
    assert parsed["periodKind"] == "MONTH"
    assert parsed["revenue"] is None and not parsed["earningsStated"]
    assert sprint.stated_quarter(parsed) is None


def test_annual_form_reads_prior_year_from_the_previous_period_column():
    parsed = sprint.parse_prelim_text(ANNUAL)
    assert parsed["periodKind"] == "ANNUAL" and parsed["earningsStated"]
    assert parsed["revenue"] == pytest.approx(62705e8)
    assert parsed["revenuePriorYear"] == pytest.approx(60941e8)
    assert sprint.stated_quarter(parsed) == date(2017, 12, 31)


@pytest.mark.parametrize("label,expected", [
    ("'24.1Q", (2024, "QUARTER", 3)), ("2013년 1분기", (2013, "QUARTER", 3)),
    ("'17년 연간 ", (2017, "ANNUAL", 12)), ("2016.9월", (2016, "MONTH", 9)),
    ("2020년 반기", (2020, "HALF", 6)), ("2021년 3Q", (2021, "QUARTER", 9)), ("", None),
    ("2013.01.01~2013.03.31", (2013, "QUARTER", 3)), ("15.4.1~15.6.30", (2015, "QUARTER", 6)),
    ("2014년 2/4분기", (2014, "QUARTER", 6)), ("FY15.3분기", (2015, "QUARTER", 9)),
    ("2019년1분기", (2019, "QUARTER", 3)), ("'13.04", (2013, "MONTH", 4)),
    ("2024.1.1~2024.12.31", (2024, "ANNUAL", 12)), ("-", None),
    ("2013-1Q", (2013, "QUARTER", 3)), ("2015Y 4Q", (2015, "QUARTER", 12)), ("'22.4.1 ~6.30", (2022, "QUARTER", 6)),
    ("`13.04.01~`13.06.30", (2013, "QUARTER", 6)), ("14.2.1~2.28", (2014, "MONTH", 2)),
])
def test_normalize_period(label, expected):
    assert sprint.normalize_period(label) == expected


def test_confirmed_prelims_skip_monthly_filings_and_amendments():
    rows = [row("영업(잠정)실적(공정공시)", "20161019", "A"), row("영업(잠정)실적(공정공시)", "20161028", "B"),
            row("[기재정정]영업(잠정)실적(공정공시)", "20161020", "C")]
    parses = {"A": sprint.parse_prelim_text(MONTHLY),
              "B": {"earningsStated": True, "periodYear": 2016, "periodEndMonth": 9},
              "C": {"earningsStated": True, "periodYear": 2016, "periodEndMonth": 9}}
    confirmed = sprint.confirmed_prelims(rows, parses)
    assert list(confirmed) == [date(2016, 9, 30)] and confirmed[date(2016, 9, 30)]["rcept_no"] == "B"


def test_spearman_handles_ties_and_degenerate_input():
    assert sprint.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert sprint.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert sprint.spearman([1, 1, 1], [1, 2, 3]) is None
    assert sprint.spearman([1, 2], [1, 2]) is None


def test_period_tokens_read_left_to_right_and_prefer_the_range_over_its_parts():
    descriptor = "2014년 2/4분기 (2014.4.1~2014.6.30) 2014년 1/4분기 (2014.1.1~2014.3.31) 2013년 2/4분기"
    assert sprint.period_tokens(descriptor)[:2] == [(2014, "QUARTER", 6), (2014, "QUARTER", 6)]
    assert sprint.period_tokens("(2013.01.01~2013.03.31) (2012.10.01~2012.12.31)") == [(2013, "QUARTER", 3), (2012, "QUARTER", 12)]


def test_2025_seven_column_layout_reads_prior_year_after_the_sign_turn_column():
    text = ("※ 동 정보는 잠정치로서 단위 : 백만원 전년동기대비 ('25.Q3) ('25.Q2) 증감율(%) 흑자적자전환여부 ('24.Q3) "
            "증감율(%) 흑자적자전환여부 매출액 당해실적 4,159,797 3,825,380 8.7 - 3,206,651 29.7 - "
            "영업이익 당해실적 100 90 11.1 - 80 25.0 - 2. 정보제공내역")
    parsed = sprint.parse_prelim_text(text)
    assert parsed["layout"] == "SEVEN_COLUMN_WITH_SIGN_TURN"
    assert parsed["periodKind"] == "QUARTER" and parsed["periodEndMonth"] == 9
    assert parsed["revenuePriorYear"] == pytest.approx(3206651e6)
    assert parsed["operatingIncomePriorYear"] == pytest.approx(80e6)
