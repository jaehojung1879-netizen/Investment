"""Synthetic tests for the pure parts of the G2 insider density gate (no network, no outcome)."""
import math

import pytest

from research.alpha_evidence_sprint_v2 import kr_insider as K
from research.master_research_program_v1.stock import insider_density_gate as G
from research.master_research_program_v1.stock import kr_event_counts as E


def test_wilson_matches_closed_form_and_edges():
    lo, hi = G.wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4) and hi == pytest.approx(0.7634, abs=1e-4)
    lo0, hi0 = G.wilson(0, 12)
    assert lo0 == pytest.approx(0.0, abs=1e-12) and 0 < hi0 < 0.3
    lo1, hi1 = G.wilson(12, 12)
    assert hi1 == 1.0 and lo1 > 0.7
    assert G.wilson(0, 0) == (None, None)


def test_projection_scales_share_and_interval_to_top120():
    p = G.project(3, 12)
    assert p["share"] == 0.25 and p["projected"] == pytest.approx(30.0)
    lo, hi = G.wilson(3, 12)
    assert p["low"] == pytest.approx(120 * lo) and p["high"] == pytest.approx(120 * hi)
    assert G.project(0, 0)["projected"] is None


def test_anchor_verdict_uses_lower_bounds_to_pass_and_upper_bounds_to_fail():
    big_buy = {"projected": 40, "low": 20, "high": 60}
    big_ctrl = {"projected": 70, "low": 50, "high": 90}
    assert G.anchor_verdict(big_buy, big_ctrl) == "PASS"
    tiny_buy = {"projected": 1, "low": 0, "high": 4.9}
    assert G.anchor_verdict(tiny_buy, big_ctrl) == "FAIL"
    tiny_ctrl = {"projected": 10, "low": 5, "high": 19.9}
    assert G.anchor_verdict(big_buy, tiny_ctrl) == "FAIL"
    wide_buy = {"projected": 8, "low": 2, "high": 30}
    assert G.anchor_verdict(wide_buy, big_ctrl) == "UNCERTAIN"
    assert G.anchor_verdict({"projected": None}, big_ctrl) == "UNMEASURED"


def test_gate_decision_three_way():
    n = 10                      # need ceil(0.6 * 10) = 6
    assert G.gate_decision(["PASS"] * 6 + ["FAIL"] * 4, [True] * 6 + [False] * 4)["verdict"] == "PROJECTED_PASS"
    assert G.gate_decision(["PASS"] * 3 + ["UNCERTAIN"] * 2 + ["FAIL"] * 5, [False] * n)["verdict"] == "PROJECTED_FAIL"
    out = G.gate_decision(["PASS"] * 3 + ["UNCERTAIN"] * 4 + ["FAIL"] * 3, [True] * 7 + [False] * 3)
    assert out["verdict"] == "UNCERTAIN" and out["anchorsRequired"] == 6 and out["anchorsPointEstimatePass"] == 7
    assert G.gate_decision(["PASS"] * 93 + ["FAIL"] * 62, [True] * 155)["anchorsRequired"] == math.ceil(0.6 * 155)


def test_membership_uses_latest_snapshot_on_or_before_anchor_never_later():
    snaps = {"2020-01-02": [{"code": "000001", "rank": 5}, {"code": "000002", "rank": 130}],
             "2020-02-03": [{"code": "000001", "rank": 150}, {"code": "000002", "rank": 7}]}
    members = G.top_members(snaps)
    assert members["2020-01-02"] == {"000001"}
    assert G.members_at("2020-01-31", members) == {"000001"}       # Feb snapshot not yet visible
    assert G.members_at("2020-02-03", members) == {"000002"}
    assert G.members_at("2019-12-31", members) is None


def test_conditioning_keeps_only_member_issuers_or_all_when_unconditioned():
    codes = {"corpA": "000001", "corpB": "000002", "corpC": None}
    assert G.condition(codes, {"000002"}) == ["corpB"]
    assert G.condition(codes, None) == ["corpA", "corpB", "corpC"]


def test_anchor_counts_remove_unresolved_issuers_from_every_class():
    states = {"a": "NET_BUYER", "b": "NO_OPEN_MARKET_TRADE", "c": "NO_OPEN_MARKET_TRADE", "d": "NET_SELLER"}
    out = G.anchor_counts(states, {"c", "zz"})
    assert out == {"NET_BUYER": 1, "NET_SELLER": 1, "NO_OPEN_MARKET_TRADE": 1,
                   "UNRESOLVED_UNPARSED_FILING_IN_WINDOW": 1}


def test_original_filter_excludes_amendments_and_other_reports():
    assert G.is_insider_original("임원ㆍ주요주주특정증권등소유상황보고서")
    assert not G.is_insider_original("[기재정정]임원ㆍ주요주주특정증권등소유상황보고서")
    assert not G.is_insider_original("주식등의대량보유상황보고서(일반)")


SESS = [f"2020-01-{d:02d}" for d in (2, 3, 6, 7, 8, 9, 10, 13, 14, 15)]


def test_gate_table_end_to_end_on_a_synthetic_sample_with_quarantine():
    good = K.Event("corpA", "r1", "2020-01-02", "2020-01-03", 100, None)
    events, counts = K.split_events([good, K.Quarantine("corpB", "r2", "2020-01-02", "X", 1, 2)])
    codes = {"corpA": "000001", "corpB": "000002", "corpC": "000003"}
    members = {"2020-01-02": {"000001", "000002", "000003"}}
    per, decision = G.gate_table(events, [("corpC", "2020-01-06")], codes, members, ["2020-01-09"], SESS)
    row = per[0]
    assert row["NET_BUYER"] == 1 and row["NO_OPEN_MARKET_TRADE"] == 1   # quarantined corpB reads no-trade
    assert row["UNRESOLVED_UNPARSED_FILING_IN_WINDOW"] == 1 and row["measured"] == 2
    assert counts["quarantined"] == 1 and decision["anchors"] == 1


def test_late_row_profile_buckets_gaps_and_labels():
    recs = [{"lateRowReasons": {"장내매수(+)|보통주|+2d": 1}},
            {"lateRowReasons": {"장내매수(+)|보통주|+212d": 1, "증여(+)|보통주|+9d": 2}}]
    out = G.late_row_profile(recs)
    assert out["lateRowsByCalendarDayGap"] == {"1-4d": 1, ">30d": 1, "5-30d": 2}
    assert out["filingsWhoseLateRowsAreAllOpenMarket"] == 1 and out["filingsProfiled"] == 2


def test_event_report_classification_is_a_reading_list_and_skips_amendments():
    table = E.CATEGORIES["B"]
    assert E.classify("주요사항보고서(자기주식취득결정)", table) == ["BUYBACK_DECISION"]
    assert E.classify("[기재정정]주요사항보고서(자기주식취득결정)", table) == []
    tallied = E.tally({"c1": [{"report_nm": "주요사항보고서(유상증자결정)", "rcept_dt": "20200101"}]}, table)
    assert tallied["RIGHTS_OFFERING_DECISION"] == {"filings": 1, "issuers": 1, "byYear": {"2020": 1}}


def test_binding_constraints_count_which_lower_bound_missed():
    rows = [{"anchorVerdict": "PASS", "buyersWilson95": [6, 50], "noTradeWilson95": [30, 90]},
            {"anchorVerdict": "UNCERTAIN", "buyersWilson95": [3, 50], "noTradeWilson95": [30, 90]},
            {"anchorVerdict": "UNCERTAIN", "buyersWilson95": [3, 50], "noTradeWilson95": [10, 90]}]
    assert G.binding_constraints(rows) == {"buyerLowerBoundBelow5": 2, "noTradeLowerBoundBelow20": 1, "both": 1}
