"""The probe's judgement, which must hold without a vendor.

The network half can only run in CI. What is pinned here is the part that
decides what the probe's answer MEANS: what counts as a publication date, and
that a DART error code is reported as a diagnosis rather than as "not 000".
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "probe_dart_fundamentals", ROOT / "scripts" / "probe_dart_fundamentals.py")
P = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = P
_spec.loader.exec_module(P)


# --------------------------------------------------------------------------- #
# The publication date — the field the whole plan hangs on
# --------------------------------------------------------------------------- #
def test_the_receipt_date_comes_from_the_receipt_number():
    """DART states the visibility date only inside `rcept_no`'s first 8 digits.

    Without it a filing has a period and no visibility date, and the replay
    would read Q1 numbers in April that nobody could see until May.
    """
    assert P.receipt_date({"rcept_no": "20230315000123"}) == "20230315"


def test_a_missing_or_malformed_receipt_number_is_none_not_a_guess():
    for row in ({}, {"rcept_no": ""}, {"rcept_no": "2023"},
                {"rcept_no": "notadate00000"}, {"rcept_no": None}):
        assert P.receipt_date(row) is None


def test_the_period_end_is_never_used_as_the_visibility_date():
    """The gap between the two IS the look-ahead this exists to prevent."""
    row = {"rcept_no": "20230315000123", "thstrm_dt": "2022.12.31"}
    assert P.receipt_date(row) == "20230315"
    assert P.receipt_date(row) != row["thstrm_dt"].replace(".", "")


# --------------------------------------------------------------------------- #
# Error codes are diagnoses
# --------------------------------------------------------------------------- #
def test_the_status_codes_that_change_what_to_do_are_named():
    """"000이 아님"은 진단이 아니다 — 키 문제와 한도 초과는 대응이 다르다."""
    assert "등록되지 않은" in P.describe("010")
    assert "요청 제한" in P.describe("020")
    assert "조회된 데이터 없음" in P.describe("013")
    assert P.describe("000").startswith("000")


def test_an_unknown_status_says_so_rather_than_passing_silently():
    assert "알 수 없는" in P.describe("777")
    assert "알 수 없는" in P.describe(None)


# --------------------------------------------------------------------------- #
# What the model actually reads
# --------------------------------------------------------------------------- #
def test_every_factor_input_the_production_model_needs_is_probed():
    """The probe checks the accounts the sleeves are built from, not just
    'does DART return financial statements'."""
    from pipeline import longterm  # noqa: F401  (import guards the names below)

    covered = {item for inputs in P.FACTOR_INPUTS.values() for item in inputs}
    for needed in ("당기순이익", "자본총계", "매출액", "영업이익",
                   "부채총계", "영업활동현금흐름", "주식수"):
        assert needed in covered, f"{needed} 없이는 만들 수 없는 팩터가 있다"


def test_the_probed_accounts_cover_the_factor_inputs_it_can_source():
    """Every statement line item the factors need is one the probe looks for.

    `주식수` and the prior period are deliberately outside WANTED_ACCOUNTS —
    they do not come from this endpoint — and the probe must not imply it
    checked them.
    """
    from_statements = {item for inputs in P.FACTOR_INPUTS.values() for item in inputs}
    from_statements -= {"주식수", "전기 당기순이익", "유형자산의취득"}
    assert from_statements <= set(P.WANTED_ACCOUNTS)


def test_account_aliases_are_probed_because_filers_label_differently():
    assert len(P.WANTED_ACCOUNTS["매출액"]) > 1
    assert len(P.WANTED_ACCOUNTS["당기순이익"]) > 1


def test_all_four_quarterly_report_codes_are_probed():
    """Annual-only would give one observation a year against a 63-day rebalance."""
    assert set(P.REPORT_CODES) == {"11011", "11012", "11013", "11014"}
