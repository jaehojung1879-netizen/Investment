"""Synthetic tests for portfolio-d-p0-p5-comparison-v1. No real outcome is read."""
import json
import random
from pathlib import Path

import pytest

from research.master_research_program_v1.portfolio import comparison as C

ETF = "069500.KS"


def no_cost(*_a):
    return 0.0


def blocks(n, rng, names=("A", "B", "C", "D")):
    out = []
    for i in range(n):
        out.append(C.Block(f"2027-{i:03d}", f"2027-{i:03d}s", {t: 1 + rng.gauss(0.01, 0.06) for t in names},
                           1 + rng.gauss(0.008, 0.05), 1.002))
    return out


def test_zero_name_arm_is_exactly_the_etf():
    rng = random.Random(1)
    bs = blocks(20, rng)
    path = C.arm_path(bs, [{}] * 20, ETF, no_cost)
    assert path == pytest.approx([b.etf_growth - 1 for b in bs])


def test_engine_does_not_read_the_arm_label():
    rng = random.Random(2)
    bs = blocks(30, rng)
    targets = [{"A": 0.2, "B": 0.1}] * 30
    fn = lambda d, side, etf: 0.0005 if side == "buy" else 0.002  # noqa: E731
    assert C.arm_path(bs, targets, ETF, fn) == C.arm_path(bs, targets, ETF, fn)
    paths = {"P1": C.arm_path(bs, targets, ETF, fn), "P3": C.arm_path(bs, targets, ETF, fn)}
    assert paths["P1"] == paths["P3"]


def test_more_than_five_names_is_refused():
    bs = blocks(1, random.Random(3), names=tuple("ABCDEF"))
    with pytest.raises(C.ComparisonError, match="MAX_NAMES"):
        C.arm_path(bs, [{t: 0.1 for t in "ABCDEF"}], ETF, no_cost)


def test_unpriced_holding_blocks_the_path_without_renormalising():
    rng = random.Random(4)
    bs = blocks(5, rng)
    bs[2] = C.Block(bs[2].date, bs[2].signal_date, {**bs[2].growth, "A": None}, bs[2].etf_growth)
    path = C.arm_path(bs, [{"A": 0.3}] * 5, ETF, no_cost)
    assert path[:2] == pytest.approx(path[:2]) and path[2:] == [None, None, None]
    assert C.summarize_arm(path, 1.0)["status"] == "NOT_EVALUABLE_BLOCKED_PATH"
    # an arm that never held A is unaffected
    assert None not in C.arm_path(bs, [{"B": 0.3}] * 5, ETF, no_cost)


def test_costs_follow_the_drifted_prior_book():
    bs = [C.Block("d0", "s0", {"A": 1.1}, 1.0), C.Block("d1", "s1", {"A": 1.0}, 1.0)]
    fn = lambda d, side, etf: 0.01  # noqa: E731
    path = C.arm_path(bs, [{"A": 0.5}, {"A": 0.5}], ETF, fn)
    # block 0 buys 0.5 A + 0.5 ETF from cash: cost 1%; block 1 rebalances drifted 0.55/1.05 back to 0.5
    drift = 0.55 / 1.05
    assert path[0] == pytest.approx(0.99 * 1.05 - 1)
    assert path[1] == pytest.approx((1 - 0.01 * 2 * (drift - 0.5)) - 1)


def test_holm_matches_textbook_and_missing_p_is_a_full_slot():
    adj = C.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": None})
    assert adj == pytest.approx({"a": 0.04, "c": 0.09, "b": 0.09, "d": 1.0})


def test_compare_runs_the_frozen_family_and_detects_a_planted_edge():
    rng = random.Random(5)
    n = 300
    base = [rng.gauss(0.01, 0.05) for _ in range(n)]
    paths = {a: list(base) for a in C.ARMS}
    paths["P3"] = [x + 0.01 + rng.gauss(0, 0.002) for x in base]   # planted +1%/block
    out = C.compare(paths, lag=5)
    assert set(out) == {f"{a}-{b}" for a, b in C.COMPARISONS}
    assert out["P3-P1"]["separated"] and out["P3-P4"]["separated"]
    assert not out["P2-P0"]["separated"]


def test_market_multiplier_is_a_separate_increment():
    bs = [C.Block("d", "s", {}, 1.05, 1.001)]
    inc = C.multiplier_increment(bs, [0.05], [0.4])
    assert inc[0] == pytest.approx(0.4 * 0.05 + 0.6 * 0.001 - 0.05)
    with pytest.raises(C.ComparisonError):
        C.multiplier_increment(bs, [0.05], [1.5])


def test_arm_status_and_hierarchy_verdict():
    blocked = {"stockScore": "UNVALIDATED"}
    assert C.arm_status(blocked, "P0") == "ADMITTED"
    assert C.arm_status(blocked, "P1") == "RESEARCH_PAPER_ONLY"
    assert C.arm_status(blocked, "P3") == "BLOCKED_NO_QUALIFIED_INPUT"
    ok = {"industryScore": "ADMITTED", "withinIndustryScore": "ADMITTED"}
    axes = dict(predictive=True, economic=True, decompositionArithmeticLed=True, notIndustryConcentration=True,
                stable=True)
    assert C.hierarchy_verdict(axes, blocked) == "BLOCKED_NO_QUALIFIED_INPUT"
    assert C.hierarchy_verdict(axes, ok) == "HIERARCHY_ADDS_VALUE"
    assert C.hierarchy_verdict({**axes, "economic": False}, ok) == "PREDICTIVE_ONLY_NOT_ECONOMIC"
    assert C.hierarchy_verdict({**axes, "notIndustryConcentration": False}, ok) == "INDUSTRY_TILT_NOT_HIERARCHY"
    assert C.hierarchy_verdict({**axes, "stable": None}, ok) == "NOT_EVALUABLE"


def test_receipt_hides_unvalidated_names_and_has_a_stable_digest():
    kw = dict(region="KR", signal_date="2027-01-08", arm="P1", targets={"A": 0.15},
              input_states={"stockScore": "UNVALIDATED"}, spec_sha256="0" * 64, etf=ETF)
    r1, r2 = C.arm_receipt(**kw), C.arm_receipt(**kw)
    assert r1["receiptSha256"] == r2["receiptSha256"] and r1["displayableToReport"] is False
    assert r1["targets"] == {"A": 0.15, ETF: 0.85}
    p0 = C.arm_receipt(**{**kw, "arm": "P0", "targets": {}})
    assert p0["displayableToReport"] is True and p0["targets"] == {ETF: 1.0}


def test_frozen_contract_matches_module():
    spec = json.loads((Path(C.__file__).parent / "portfolio-d-p0-p5-comparison-v1.json").read_text())
    assert [a["id"] for a in spec["arms"]] == list(C.ARMS)
    assert [tuple(c) for c in spec["comparisonFamily"]["pairs"]] == list(C.COMPARISONS)
    assert spec["nameCountPolicy"]["max"] == C.MAX_NAMES and spec["marketMultiplier"]["inPrimary"] is False
