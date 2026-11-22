"""MVMA-v1 Phase 2: the committed one-shot result, its authorization pins and its refusal to run again."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research.market_valuation_macro_overlay_v1 import execute_phase2 as EX

REPO = Path(__file__).resolve().parents[1]
RESULT = json.loads(EX.RESULT.read_text())
AUTH = json.loads(EX.AUTHORIZATION.read_text())


def test_a_second_run_is_refused():
    with pytest.raises(EX.ExecutionRefused, match="ONE_SHOT_ALREADY_SPENT"):
        EX.verify_authorization()


def test_every_pinned_code_and_input_still_matches_the_authorization():
    for rel, expected in {**AUTH["codeSha256"], **AUTH["inputSha256"]}.items():
        assert hashlib.sha256((REPO / rel).read_bytes()).hexdigest() == expected, rel
    assert AUTH["protocolSha256"] == "07e60dc03990bbbf319951a371fa61a3cd9e1e592e9fc6b4a9a7a9823d4a5df8"
    assert AUTH["scope"]["hypotheses"] == ["H1-US-TRAILING", "H2-US-VM1T"]


def test_result_keeps_its_evidence_class_and_is_never_promoted():
    assert RESULT["evidenceClass"] == "EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY"
    assert RESULT["promotionEligible"] is False and RESULT["productionChange"] is False
    assert RESULT["verdicts"]["promotionEligible"] is False
    assert RESULT["dca"]["role"] == "SEPARATE_DESCRIPTIVE_STUDY_NOT_IN_HOLM_FAMILY"


def test_result_covers_the_registered_window_and_family():
    primary = RESULT["primary"]
    assert primary["periods"] == 152 and primary["firstExecution"] == "2012-02-01"
    assert set(primary["holm"]["adjusted"]) == {"H1-US-TRAILING", "H2-US-VM1T"}
    h1 = primary["H1"]["H12M"]
    assert h1["nCheap"] + h1["nNotCheap"] == 152
    for policy, d in primary["decomposition"].items():
        assert d["annualActiveGross"] == pytest.approx(d["annualLevel"] + d["annualTiming"], abs=1e-12), policy


def test_report_quotes_the_result_numbers():
    report = (EX.HERE / "REPORT-PHASE2-ko.md").read_text()
    h1 = RESULT["primary"]["H1"]["H12M"]
    assert f"+{100 * h1['difference']:.2f}%p" in report
    assert f"{RESULT['primary']['holm']['adjusted']['H1-US-TRAILING']:.3f}" in report
    assert f"{RESULT['primary']['holm']['adjusted']['H2-US-VM1T']:.3f}" in report
    assert f"{100 * RESULT['primary']['policies']['B0']['net']['cagr']:.2f}%" in report
    assert f"{100 * RESULT['primary']['policies']['VM1T']['net']['cagr']:.2f}%" in report
