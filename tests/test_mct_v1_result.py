"""MCT-v1 committed one-shot result: refusal to re-run, pinned inputs, and report fidelity."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research.market_causal_transmission_v1 import execute as EX

REPO = Path(__file__).resolve().parents[1]
RESULT = json.loads(EX.RESULT.read_text())
AUTH = json.loads(EX.AUTHORIZATION.read_text())
REPORT = (EX.HERE / "REPORT-ko.md").read_text()


def test_a_second_run_is_refused():
    with pytest.raises(EX.ExecutionRefused, match="ONE_SHOT_ALREADY_SPENT"):
        EX.verify()
    marker = json.loads(EX.MARKER.read_text())
    assert marker["outcomeReadsBeforeThisMarker"] == 0


def test_every_pinned_file_still_matches_the_authorization():
    for rel, expected in AUTH["pinnedSha256"].items():
        assert hashlib.sha256((REPO / rel).read_bytes()).hexdigest() == expected, rel
    assert RESULT["protocolSha256"] == AUTH["protocolSha256"]


def test_result_keeps_its_evidence_class_and_family():
    assert RESULT["evidenceClass"] == "EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY"
    assert RESULT["promotionEligible"] is False
    assert set(RESULT["holm"]) == {"H1-P", "H2-P", "H3-P"}
    assert RESULT["H2"]["h12"]["n"] == 416


def test_report_quotes_the_result():
    h1 = RESULT["H1"]["prediction"]["12"]["mpMinusCbi"]
    assert f"{h1['p']:.3f}" in REPORT
    assert f"{RESULT['H2']['H2-P']['p']:.3f}" in REPORT
    assert f"{RESULT['H3']['policies']['VULN']['timingNetP']:.3f}" in REPORT
    assert f"{100 * RESULT['H3']['B0']['cagr']:.2f}%" in REPORT
    assert f"{RESULT['H2']['incremental']['h12']['p']:.3f}" in REPORT
