"""A strategy that starts after ETF_ONLY must be compared with the ETF from ITS OWN start, not from the ETF's.

Found in independent review of the shadow ledger status report: `excessVsEtfPct` divided the strategy NAV by the
ETF_ONLY NAV of the same date. Every strategy starts at NAV 1.0, so a strategy whose first target arrives a week later
(its week-one scenario was blocked and held the previous book) was compared with an ETF path that already contained that
week's return. Synthetic prices only.
"""
from __future__ import annotations

from datetime import datetime, timezone
import copy

import pytest

from pipeline import entry_state_shadow_ledger as L
from tests.test_entry_state_shadow_ledger import observation

WEEK1_SUNDAY = datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)     # signal 2026-10-30 -> executes 2026-11-02
WEEK2_SUNDAY = datetime(2026, 11, 8, 3, 0, tzinfo=timezone.utc)     # signal 2026-11-06 -> executes 2026-11-09
PRICES = {
    "2026-11-02": {"069500.KS": 100.0, "000001.KS": 50.0},
    "2026-11-03": {"069500.KS": 110.0, "000001.KS": 50.0},          # the ETF rises 10% before N1 starts
    "2026-11-04": {"069500.KS": 110.0, "000001.KS": 50.0},
    "2026-11-05": {"069500.KS": 110.0, "000001.KS": 50.0},
    "2026-11-06": {"069500.KS": 110.0, "000001.KS": 50.0},
    "2026-11-09": {"069500.KS": 110.0, "000001.KS": 50.0},
    "2026-11-10": {"069500.KS": 110.0, "000001.KS": 50.0},          # flat after N1 starts
}


def close_of(ticker, session):
    return PRICES.get(session, {}).get(ticker)


def _blocked_week_one():
    obs = copy.deepcopy(observation(as_of="2026-10-30"))
    scenario = obs["regions"]["KR"]["researchScenarios"][0]
    scenario["status"] = "INSUFFICIENT_ELIGIBLE_NAMES"
    scenario["rankStateInSelection"] = scenario["stateAtPositionWeight"] = None
    return obs


def _ledger(tmp_path):
    L.append_decisions(tmp_path, L.decision_receipts(_blocked_week_one(), recorded_at=WEEK1_SUNDAY, code={},
                                                     observation_sha256="w1"))
    L.append_decisions(tmp_path, L.decision_receipts(observation(as_of="2026-11-06"), recorded_at=WEEK2_SUNDAY, code={},
                                                     observation_sha256="w2"))
    now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    L.advance(tmp_path, now=now, close_of=close_of, through="2026-11-10")
    return L.status_report(tmp_path, now=now)["strategies"]


def test_late_starting_strategy_is_not_charged_with_the_etf_move_before_it_started(tmp_path):
    report = _ledger(tmp_path)
    late, etf = report["KR:N1:IN_RANK"], report["KR:ETF_ONLY"]
    assert etf["nav"] == pytest.approx(1.10)                         # ETF_ONLY has been invested since 2026-11-02
    assert late["lastFillSession"] == "2026-11-09"                   # N1 only got a target in week two
    # Prices are flat after N1 starts, so its excess over the ETF can only be the cost it paid, a few hundredths of a percent.
    assert late["excessVsEtfPct"] is not None
    assert -0.5 < late["excessVsEtfPct"] <= 0.0
    assert late["etfBaseDate"] == "2026-11-09"


def test_same_start_is_unchanged(tmp_path):
    report = _ledger(tmp_path)
    same = report["KR:CURRENT_POLICY"]                                # passive from week one, same start as ETF_ONLY
    assert same["excessVsEtfPct"] == pytest.approx(0.0, abs=1e-9)
    assert same["etfBaseDate"] == "2026-11-02"


def test_missing_etf_base_is_unknown_not_zero(tmp_path):
    L.append_decisions(tmp_path, L.decision_receipts(observation(), recorded_at=WEEK1_SUNDAY, code={},
                                                     observation_sha256="w1"))
    now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
    L.advance(tmp_path, now=now, close_of=close_of, through="2026-11-03")
    lines = [ln for ln in (tmp_path / "nav-daily.jsonl").read_text().splitlines() if "KR:ETF_ONLY" not in ln]
    (tmp_path / "nav-daily.jsonl").write_text("\n".join(lines) + "\n")   # the ETF reference is not available
    out = L.status_report(tmp_path, now=now)["strategies"]["KR:CURRENT_POLICY"]
    assert out["excessVsEtfPct"] is None and out["etfBaseDate"] is None
