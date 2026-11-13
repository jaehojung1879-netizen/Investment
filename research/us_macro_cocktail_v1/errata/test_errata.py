"""Errata v1 checks (pytest -q research/us_macro_cocktail_v1/errata)."""
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import errata_v1 as E  # noqa: E402


def test_h10_release_is_monday_after_the_week_at_1615_et():
    hol = {pd.Timestamp("2026-10-12")}
    assert E.h10_release(pd.Timestamp("2026-10-30"), hol) == pd.Timestamp("2026-11-02 16:15")
    assert E.h10_release(pd.Timestamp("2026-10-27"), hol) == pd.Timestamp("2026-11-02 16:15")
    # a Monday federal holiday moves the release to Tuesday
    assert E.h10_release(pd.Timestamp("2026-10-07"), hol) == pd.Timestamp("2026-10-13 16:15")


def test_available_fx_never_uses_an_unpublished_observation():
    fx = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2026-10-23", "2026-10-30", "2026-11-02"]))
    sessions = pd.to_datetime(["2026-10-30", "2026-11-02", "2026-11-03"])
    val, obs = E.fx_available(pd.DatetimeIndex(sessions), fx)
    # Oct-23 week releases Mon Oct-26 16:15; Oct-30 releases Mon Nov-02 16:15 (after the 16:00 close)
    assert val.iloc[0] == 1.0 and val.iloc[1] == 1.0 and val.iloc[2] == 2.0


def test_committed_errata_reproduces_the_audit_counterexample():
    e = json.loads((HERE / "results" / "errata-v1.json").read_text())
    end = e["windows"]["primary"]["fxAtEnd"]
    assert end["originalNextObservation"] == 1344.51 and end["sameDayObservation"] == 1333.99
    assert end["availableObservationDate"] == "2026-10-23"
    assert e["windows"]["primary"]["targetsExecutedInWindow"] == 130
    assert e["originalResultsUnchanged"] is True


def test_executed_targets_drop_post_window_execution():
    sched = type("S", (), {"executions": pd.to_datetime(["2026-10-01", "2026-11-02"])})
    t = {pd.Timestamp("2026-09-30"): {"SPY": 1.0}, pd.Timestamp("2026-10-30"): {"BIL": 1.0}}
    assert list(E.executed_targets(sched, t, "2026-10-30")) == [pd.Timestamp("2026-09-30")]
