"""The Guru 13F access probe's judging logic, pinned without a network.

`sec_access.classify` assumes a served response looks like JSON; a bulk
dataset ZIP never does, and `classify_maybe_zip` is the one place that
difference is handled — this is what proves it does not regress into
reporting a served ZIP as a block page.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.sec_access import BLOCKED, ERROR, SERVED  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "probe_guru_13f_access", ROOT / "scripts" / "probe_guru_13f_access.py")
P = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = P
_spec.loader.exec_module(P)


def test_a_zip_body_is_served_even_though_it_is_not_json():
    outcome, marker = P.classify_maybe_zip(200, b"PK\x03\x04rest of a real zip")
    assert outcome == SERVED and marker is None


def test_a_block_page_is_blocked_regardless_of_status():
    body = b"Your Request Originates from an Undeclared Automated Tool"
    outcome, _marker = P.classify_maybe_zip(200, body)
    assert outcome == BLOCKED


def test_a_403_with_no_recognizable_body_is_an_error_not_a_silent_pass():
    outcome, _marker = P.classify_maybe_zip(403, b"")
    assert outcome == ERROR


def test_judge_prefers_the_bulk_route_when_both_are_served():
    verdict = P.judge({"outcome": SERVED}, {"outcome": SERVED})
    assert verdict["verdict"] == SERVED and verdict["recommendedRoute"] == "BULK_DATASET"


def test_judge_falls_back_to_per_manager_when_only_that_route_is_served():
    verdict = P.judge({"outcome": BLOCKED}, {"outcome": SERVED})
    assert verdict["recommendedRoute"] == "PER_MANAGER_SUBMISSIONS"


def test_judge_reports_none_when_both_routes_are_blocked():
    verdict = P.judge({"outcome": BLOCKED}, {"outcome": BLOCKED})
    assert verdict["verdict"] == BLOCKED and verdict["recommendedRoute"] == "NONE"
