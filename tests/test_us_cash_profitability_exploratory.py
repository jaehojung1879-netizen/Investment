"""US cash-profitability exploratory harness (P4): mechanics on synthetic, outcome-free fixtures only.

Pinned here: the harness reuses the calibrated weights and interval unchanged; compounded calendar-time attribution equals v4's
additive attribution in the uniform case and telescopes exactly on irregular real-calendar weeks; no outcome can be read without an
owner permit and the counter records every read; signal-date cohorts cannot change when post-signal data change; unresolved and
unmatured cohorts are excluded, never zero-filled; the decision rule is the frozen one; the committed preflight read no outcome.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import alpha_inference_calibration_v4 as V4          # noqa: E402
from pipeline import us_cash_profitability_exploratory as X        # noqa: E402
from pipeline import us_h63_inference_calibration as CAL           # noqa: E402

PREFLIGHT = ROOT / "docs/us-readiness/us-cash-profitability-exploratory-preflight-v1.json"
CHECKLIST = ROOT / "docs/us-readiness/us-cash-profitability-exploratory-readiness-v1.json"


def synthetic_rows(n, seed, sectors=("Industrials", "Health Care", "Utilities", "Energy")):
    rng = np.random.default_rng(seed)
    return [{"ticker": f"T{i:03d}", "sector": sectors[i % len(sectors)], X.FEATURE: float(rng.standard_normal()),
             **{c: float(rng.standard_normal()) for c in X.CONTROLS}} for i in range(n)]


def test_frozen_constants_match_the_protocol_and_calibration():
    protocol = json.loads((ROOT / "docs/us-readiness/us-cash-profitability-study-protocol-v1.json").read_text())
    cal = json.loads((ROOT / "docs/us-readiness/us-h63-inference-calibration-v1-protocol.json").read_text())
    assert X.SN_CRITICAL_VALUE == cal["methods"]["snCriticalValue"] == 28.31
    assert X.MIN_NAMES_PER_DATE == protocol["eligibleCrossSection"]["minimumNamesPerDate"] == 150
    assert X.HORIZON == protocol["primaryClaim"]["horizonSessions"] == 63
    assert list(X.EXCLUDED_SECTORS) == protocol["eligibleCrossSection"]["excludedSectors"]
    assert X.MIN_DEFINED_WEEKS == protocol["prerequisitesBeforeRegistration"][2]["calibrationResult"]["minimumWeeklySignalsForAnInterval"]
    assert set(X.CONTROLS) == {"logTradedValue63", "mom121", "vol252", "operatingProfitabilityToAssets"}


def test_cohort_weights_are_the_calibrated_construction():
    rows = synthetic_rows(200, 1)
    cohort = X.cohort_weights(rows)
    assert cohort["defined"] and abs(np.abs(cohort["weights"]).sum() - 2.0) < 1e-12
    cc = sorted(rows, key=lambda r: r["ticker"])
    avail = np.ones(len(cc), dtype=bool)
    codes = {s: k for k, s in enumerate(sorted({r["sector"] for r in cc}))}
    expected = CAL.residual_weights(CAL.centred_ranks(np.array([r[X.FEATURE] for r in cc]), avail),
                                    np.column_stack([CAL.centred_ranks(np.array([r[c] for r in cc]), avail) for c in X.CONTROLS]),
                                    np.array([codes[r["sector"]] for r in cc]), avail)
    assert np.array_equal(cohort["weights"], expected)


def test_floor_financials_and_missing_controls():
    rows = synthetic_rows(160, 2)
    rows[0][X.CONTROLS[0]] = None
    rows[1]["sector"] = "Financials"
    rows[2]["sector"] = "Real Estate"
    cohort = X.cohort_weights(rows)
    assert cohort["names"] == 157 and cohort["defined"]
    assert not X.cohort_weights(synthetic_rows(149, 3))["defined"]


def test_entry_is_the_session_after_the_signal_and_exit_63_later():
    sessions = [f"2026-01-{d:02d}" for d in range(1, 29)] + [f"2026-02-{d:02d}" for d in range(1, 29)] + \
               [f"2026-03-{d:02d}" for d in range(1, 29)]
    entry, exit_ = X.entry_exit(sessions, "2026-01-05")
    assert sessions[entry] == "2026-01-06" and exit_ - entry == 63


def test_compounded_attribution_reduces_to_v4_in_the_uniform_additive_case():
    rng = np.random.default_rng(5)
    weeks, names, step, h = 40, 12, 5, X.HORIZON
    daily = rng.standard_normal(((weeks - 1) * step + h, names)) * 0.01
    weights = rng.standard_normal((weeks, names))
    defined = rng.random(weeks) > 0.1
    defined[[0, -1]] = True
    d4, x4 = V4.calendar_time_series(daily, weights, h, step, None, defined)
    close = np.vstack([np.zeros((1, names)), np.cumsum(daily, axis=0)])      # close[s] - close[s-1] = daily[s-1]
    entry = np.arange(weeks) * step
    week_of = np.concatenate([[0], np.arange(daily.shape[0]) // step])
    d, x, _ = X.attribute_compounded(close, weights, entry, defined, week_of, h, compounded=False)
    assert len(d) == len(d4) and np.allclose(d, d4) and np.allclose(x, x4)


def test_compounded_attribution_telescopes_on_irregular_weeks():
    rng = np.random.default_rng(7)
    sessions, names = 400, 20
    close = 50.0 * np.exp(np.cumsum(rng.standard_normal((sessions, names)) * 0.02, axis=0))
    entry = np.arange(0, 300, 5)
    weights = rng.standard_normal((len(entry), names))
    week_of = np.repeat(np.arange(200), rng.integers(3, 6, 200))[:sessions]
    d, x, s = X.attribute_compounded(close, weights, entry, np.ones(len(entry), bool), week_of)
    expected = [weights[t] @ (close[e + 63] / close[e] - 1) for t, e in enumerate(entry)]
    assert np.allclose(s, expected) and abs(d.sum() - sum(expected)) < 1e-9 and abs(x.sum() - len(entry)) < 1e-9


def test_no_outcome_without_an_owner_permit_and_every_read_is_counted(tmp_path):
    counters = X.Counters()
    with pytest.raises(X.OutcomeAccessRefused):
        X.read_outcomes(None, lambda: 1, counters)
    with pytest.raises(X.OutcomeAccessRefused):
        X.read_outcomes(X.OutcomePermit("forged"), lambda: 1, counters)
    with pytest.raises(X.OutcomeAccessRefused):
        X.authorize(tmp_path / "absent.json", {"a": "1"})
    record = {"contract": X.CONTRACT, "authorizes": "ONE_EXPLORATORY_EXECUTION", "pinnedIdentities": {"a": "1"}}
    (tmp_path / "auth.json").write_text(json.dumps(record))
    with pytest.raises(X.OutcomeAccessRefused):
        X.authorize(tmp_path / "auth.json", {"a": "2"})
    permit = X.authorize(tmp_path / "auth.json", {"a": "1"})
    assert X.read_outcomes(permit, lambda: 42, counters) == 42 and counters.outcomeReads == 1


def _fixture(tmp_path, seed=11):
    rng = np.random.default_rng(seed)
    sessions = [str(np.datetime64("2020-01-01") + np.timedelta64(int(k), "D")) for k in range(700)]
    tickers = [f"T{i:03d}" for i in range(160)]
    closes = {t: 20.0 * np.exp(np.cumsum(rng.standard_normal(len(sessions)) * 0.02)) for t in tickers}
    cohorts = []
    for k in range(270):
        rows = [{"ticker": t, "sector": ("A", "B", "C")[i % 3], X.FEATURE: float(rng.standard_normal()),
                 **{c: float(rng.standard_normal()) for c in X.CONTROLS}} for i, t in enumerate(tickers)]
        cohort = X.cohort_weights(rows)
        held = cohort["weights"] != 0
        cohorts.append({"date": sessions[k * 2], "defined": cohort["defined"],
                        "heldTickers": [t for t, h in zip(cohort["tickers"], held) if h],
                        "heldWeights": [float(w) for w in cohort["weights"][held]]})
    record = {"contract": X.CONTRACT, "authorizes": "ONE_EXPLORATORY_EXECUTION", "pinnedIdentities": {"x": "1"}}
    (tmp_path / "auth.json").write_text(json.dumps(record))
    permit = X.authorize(tmp_path / "auth.json", {"x": "1"})

    def reader(names, dates):
        index = {s: k for k, s in enumerate(sessions)}
        return np.column_stack([[closes[t][index[s]] for s in dates] for t in names])
    return sessions, cohorts, permit, reader, closes


def test_execute_study_runs_end_to_end_once_and_follows_the_frozen_rule(tmp_path):
    sessions, cohorts, permit, reader, _ = _fixture(tmp_path)
    counters = X.Counters()
    out = X.execute_study(cohorts, sessions, sessions[-1], reader, permit, counters)
    assert counters.outcomeReads == 1 and counters.intervalComputations == 1
    assert out["status"] in (X.ABANDON, X.CONTINUE) and out["definedWeeks"] >= X.MIN_DEFINED_WEEKS
    assert (out["status"] == X.ABANDON) == (out["upperOneSided95"] <= 0)


def test_unresolved_exit_voids_the_cohort_and_short_samples_are_not_evaluable(tmp_path):
    sessions, cohorts, permit, reader, closes = _fixture(tmp_path)
    victim = cohorts[0]["heldTickers"][0]
    entry, exit_ = X.entry_exit(sessions, cohorts[0]["date"])
    closes[victim][exit_] = np.nan
    out = X.execute_study(cohorts, sessions, sessions[-1], reader, permit, X.Counters())
    assert cohorts[0]["date"] in out["unresolvedDates"]
    short = X.execute_study(cohorts[:100], sessions, sessions[-1], reader, permit, X.Counters())
    assert short["status"] == X.NOT_EVALUABLE and short["reason"] == "FEWER_THAN_260_DEFINED_WEEKLY_COHORTS"


def test_more_than_ten_percent_unresolved_dates_is_not_evaluable(tmp_path):
    """Protocol decisionRules.inconclusive: too many UNRESOLVED dates (> 10%) never yields a screen reading."""
    sessions, cohorts, permit, reader, closes = _fixture(tmp_path)
    victim = cohorts[0]["heldTickers"][0]
    closes[victim][300:] = np.nan                                   # the name stops trading; no terminal consideration exists
    counters = X.Counters()
    out = X.execute_study(cohorts, sessions, sessions[-1], reader, permit, counters)
    assert out["status"] == X.NOT_EVALUABLE and out["reason"] == "MORE_THAN_10_PCT_UNRESOLVED_DATES"
    assert out["unresolvedCohorts"] > 0.10 * out["maturedDefinedCohorts"] and counters.intervalComputations == 0


def test_signal_date_cohorts_ignore_post_signal_data(tmp_path):
    """Cohort weights are a function of signal-date rows only: changing every post-signal close leaves them identical."""
    rows = synthetic_rows(180, 9)
    before = X.cohort_weights(rows)["weights"]
    sessions, cohorts, permit, reader, closes = _fixture(tmp_path)
    for t in closes:
        closes[t][:] = closes[t][::-1]
    assert np.array_equal(before, X.cohort_weights(rows)["weights"])


def test_harness_imports_nothing_that_publishes_or_decides():
    for relative in ("pipeline/us_cash_profitability_exploratory.py", "scripts/run_us_cash_profitability_exploratory.py"):
        tree = ast.parse((ROOT / relative).read_text())
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not {m for m in names if any(k in m for k in ("weekly_publish", "current_champion", "kelly_portfolio",
                                                                "datafeed", "us_daily_market"))}, relative


@pytest.fixture(scope="module")
def preflight():
    if not PREFLIGHT.exists():
        pytest.skip("preflight not committed")
    return json.loads(PREFLIGHT.read_text())


def test_committed_preflight_read_no_outcome_and_reproduces_phase3(preflight):
    assert preflight["mode"] == "PREFLIGHT_OUTCOME_FREE"
    assert preflight["counters"]["outcomeReads"] == 0 and preflight["counters"]["intervalComputations"] == 0
    assert preflight["phase3Reproduction"]["reproduces"] is True


def test_readiness_checklist_is_consistent_and_authorizes_nothing(preflight):
    checklist = json.loads(CHECKLIST.read_text())
    assert checklist["authorizes"] == "NOTHING" and checklist["executed"] is False
    states = {item["state"] for item in checklist["items"]}
    assert states <= {"PASS", "CONDITIONAL", "BLOCKED"}
    expected = "BLOCKED" if "BLOCKED" in states else ("CONDITIONAL" if "CONDITIONAL" in states else "PASS")
    assert checklist["overall"] == expected
    assert not (ROOT / "docs/us-readiness/us-cash-profitability-exploratory-authorization-v1.json").exists()


def _runner():
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_us_cp_exploratory", ROOT / "scripts/run_us_cash_profitability_exploratory.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_execute_refuses_before_any_data_without_an_owner_authorization(tmp_path, monkeypatch):
    R = _runner()
    touched = []
    monkeypatch.setattr(R, "load_state", lambda *a, **k: touched.append("load_state"))
    monkeypatch.setattr(R, "identities", lambda: {"x": "1"})
    with pytest.raises(SystemExit, match="OUTPUT_MUST_BE_A_NEW_EXPLICIT_PATH_OUTSIDE_docs"):
        R.main(["execute", "--workspace", str(tmp_path), "--output", str(ROOT / "docs/x.json")])
    monkeypatch.setattr(R, "AUTHORIZATION", tmp_path / "absent.json")
    with pytest.raises(X.OutcomeAccessRefused, match="NO_OWNER_AUTHORIZATION"):
        R.main(["execute", "--workspace", str(tmp_path), "--output", str(tmp_path / "out.json")])
    monkeypatch.setattr(R, "RESULT", tmp_path / "spent.json")
    (tmp_path / "spent.json").write_text("{}")
    with pytest.raises(SystemExit, match="ONE_SHOT_ALREADY_SPENT"):
        R.main(["execute", "--workspace", str(tmp_path), "--output", str(tmp_path / "out2.json")])
    assert touched == [] and not (tmp_path / "out.json").exists()
