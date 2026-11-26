import json

import numpy as np
import pandas as pd

from research.kr_us_earnings_expectations_v1 import analysis as AN
from research.kr_us_earnings_expectations_v1 import events as EVN


def test_quarters_are_cumulative_differences_and_need_the_previous_stage():
    q = EVN.quarterly_from_cumulative({(2020, 1): 10.0, (2020, 2): 25.0, (2020, 4): 60.0})
    assert q == {(2020, 1): 10.0, (2020, 2): 15.0}          # Q4 needs Q3 cumulative, so it is absent, not annualised


def test_sue_needs_four_prior_seasonal_differences_and_uses_only_the_past():
    q = {(y, s): float(y * 10 + s) for y in range(2015, 2019) for s in range(1, 5)}
    q[(2018, 4)] = 1000.0
    sue = EVN.sue_series(q)
    assert (2016, 4) not in sue                              # only 3 prior differences at that point
    assert (2018, 3) not in sue                              # every prior difference is 10: zero dispersion -> undefined, never infinite
    assert all(np.isfinite(v) for v in sue.values())


def test_kr_announcement_is_the_first_original_preliminary_disclosure_inside_the_window(tmp_path):
    ev = pd.DataFrame({"ticker": ["A"], "periodEnd": [pd.Timestamp("2024-03-31")], "filingDate": [pd.Timestamp("2024-05-15")]})
    rows = [{"report_nm": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)", "rcept_dt": "20240420"},
            {"report_nm": "연결재무제표기준영업(잠정)실적(공정공시)", "rcept_dt": "20240425"},
            {"report_nm": "연결재무제표기준영업(잠정)실적(공정공시)", "rcept_dt": "20240520"},
            {"report_nm": "영업(잠정)실적(공정공시)", "rcept_dt": "20240210"}]
    p = tmp_path / "k.json"
    p.write_text(json.dumps({"tickers": {"A": {"rows": rows}}}, ensure_ascii=False))
    out = EVN.attach_kr_announcements(ev, p)
    assert out["announceTime"].iloc[0] == pd.Timestamp("2024-04-25")


def test_us_after_close_release_reacts_from_the_next_day(tmp_path):
    ev = pd.DataFrame({"ticker": ["A"], "periodEnd": [pd.Timestamp("2024-03-31")], "filingDate": [pd.Timestamp("2024-05-02")]})
    rows = [{"acceptanceDateTime": "2024-04-30T20:30:00.000Z"}]          # 16:30 New York
    p = tmp_path / "u.json"
    p.write_text(json.dumps({"tickers": {"A": {"rows": rows}}}))
    out = EVN.attach_us_announcements(ev, p)
    assert out["announceEffective"].iloc[0] == pd.Timestamp("2024-05-01")


def test_fresh_signal_uses_only_filings_published_before_the_decision_and_within_window():
    ev = pd.DataFrame({"ticker": ["A", "A", "B"], "sue": [1.0, 2.0, 3.0],
                       "filingDate": pd.to_datetime(["2024-01-10", "2024-03-01", "2023-06-01"])})
    s = AN.fresh_sue(ev, pd.Timestamp("2024-03-01"))
    assert s.to_dict() == {"A": 1.0}                         # same-day filing not yet usable; B is stale


def test_top_pick_respects_group_cap_and_order():
    s = pd.Series({"a": 3.0, "b": 2.5, "c": 2.0, "d": 1.5})
    assert AN.pick_top(s, {"a": "x", "b": "x", "c": "x", "d": "y"}, n=3, per=2) == ["a", "b", "d"]
