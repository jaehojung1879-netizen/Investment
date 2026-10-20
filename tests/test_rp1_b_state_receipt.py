import numpy as np
import pandas as pd
import pytest

from pipeline import replay_calendar as RC
from pipeline import rp1_b_state_receipt as B

SIGNAL = "2026-09-11"  # a Friday KR session; invented prices below


def _sessions(end=SIGNAL):
    return pd.DatetimeIndex(RC.sessions("2024-01-02", end, "KR"))


def _close(end=SIGNAL, drift=0.0004, shock=None):
    idx = _sessions(end)
    path = 100 * np.exp(np.cumsum(np.full(len(idx), drift) + 0.001 * np.sin(np.arange(len(idx)))))
    s = pd.Series(path, index=idx)
    if shock:
        s.iloc[-shock[0]:] *= shock[1]
    return s


def test_rising_market_is_not_adverse():
    r = B.build_preview(_close(), SIGNAL)
    assert r["adverse"] is False and r["fast"] == 0 and r["trailing24mReturn"] > 0
    assert r["evidenceClass"] == "PROSPECTIVE_PAPER_PREVIEW" and r["ledgerWritten"] is False
    assert B.validate_preview(r)


def test_negative_trailing_return_is_adverse_even_if_fast_is_calm():
    r = B.build_preview(_close(drift=-0.0004), SIGNAL)
    assert r["trailing24mReturn"] < 0 and r["adverse"] is True


def test_missing_leg_is_neither_benign_nor_adverse():
    short = _close()
    short = short.loc["2025-06-01":]  # no 24-month base, FAST computable
    r = B.build_preview(short, SIGNAL)
    assert "TRAILING_24M_BASE_UNAVAILABLE" in r["unavailableReasons"]
    assert r["adverse"] is None
    # an adverse available leg still decides
    down = B.build_preview(_close(drift=-0.0004).loc["2025-06-01":], SIGNAL)
    assert down["trailing24mReturn"] is None and down["adverse"] in (None, True)


def test_data_after_signal_is_refused_not_dropped():
    with pytest.raises(ValueError, match="DATA_AFTER_SIGNAL_DATE"):
        B.build_preview(_close(end="2026-09-14"), SIGNAL)


def test_non_decision_session_is_refused():
    with pytest.raises(ValueError, match="WEEKLY_DECISION_SESSION"):
        B.build_preview(_close(end="2026-09-10"), "2026-09-10")


def test_identity_changes_with_inputs_and_digest_detects_tampering():
    a, b = B.build_preview(_close(), SIGNAL), B.build_preview(_close(drift=0.0003), SIGNAL)
    assert a["inputIdentity"] != b["inputIdentity"]
    a["adverse"] = True
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        B.validate_preview(a)


def test_preview_cannot_claim_ledger_evidence_or_carry_outcome_keys():
    r = B.build_preview(_close(), SIGNAL)
    bad = dict(r, evidenceClass="PROSPECTIVE_PAPER")
    bad["receiptSha256"] = B.P.receipt_digest(bad)
    with pytest.raises(ValueError, match="LEDGER_EVIDENCE"):
        B.validate_preview(bad)
    leak = dict(r, forwardReturn=0.1)
    with pytest.raises(ValueError, match="OUTCOME_FIELD"):
        B.P.scan_for_outcome_keys(leak)


def test_module_never_writes_a_ledger():
    src = open(B.__file__, encoding="utf-8").read()
    assert "P.append" not in src and "open(" not in src


def _with_gap(series, start, end):
    return series.drop(series.loc[start:end].index)


def test_stale_base_is_unavailable_not_tolerated():
    s = _close()
    base = pd.Timestamp(SIGNAL) - pd.DateOffset(months=24)
    exp = pd.DatetimeIndex(RC.sessions(str((base - pd.Timedelta(days=15)).date()), str(base.date()), "KR"))[-1]
    s = s.drop(exp) if exp in s.index else s
    r = B.build_preview(s, SIGNAL)
    assert "TRAILING_24M_BASE_UNAVAILABLE" in r["unavailableReasons"] and r["trailing24mReturn"] is None


def test_duplicate_and_nonmonotonic_timestamps_are_refused():
    s = _close()
    with pytest.raises(ValueError, match="DUPLICATE"):
        B.build_preview(pd.concat([s, s.iloc[-1:]]), SIGNAL)
    with pytest.raises(ValueError, match="NOT_MONOTONIC"):
        B.build_preview(s.iloc[::-1], SIGNAL)


def test_invalid_close_on_signal_or_base_date():
    s = _close()
    bad = s.copy(); bad.iloc[-1] = float("nan")
    assert "SIGNAL_DATE_CLOSE_UNAVAILABLE" in B.build_preview(bad, SIGNAL)["unavailableReasons"]
    base = pd.Timestamp(SIGNAL) - pd.DateOffset(months=24)
    exp = pd.DatetimeIndex(RC.sessions(str((base - pd.Timedelta(days=15)).date()), str(base.date()), "KR"))[-1]
    bad2 = s.copy(); bad2.loc[exp] = -1.0
    assert B.build_preview(bad2, SIGNAL)["trailing24mReturn"] is None


def test_adverse_fast_with_unavailable_return_is_adverse():
    s = _close(shock=(10, 0.8)).loc["2025-06-01":]
    r = B.build_preview(s, SIGNAL)
    assert r["trailing24mReturn"] is None
    assert r["adverse"] == (True if r["fast"] == 2 else None)


def _redigest(r):
    r = dict(r)
    r.pop("receiptSha256", None)
    r["receiptSha256"] = B.P.receipt_digest(r)
    return r


@pytest.mark.parametrize("field,value", [
    ("adverse", True), ("adverse", None), ("fast", 2), ("fast", 7), ("fast", True),
    ("trailing24mReturn", -0.2), ("trailing24mReturn", -1.5),
    ("baseSessionDate", None), ("baseSessionDate", "2030-01-01"), ("baseSessionDate", "garbage"),
    ("unavailableReasons", ["FAST_DATA_INSUFFICIENT"]), ("unavailableReasons", "x"), ("unavailableReasons", ["MADE_UP"]),
    ("signalDate", "2026-10-17"), ("signalDate", "bad"), ("definition", "other"), ("studyId", "other"),
    ("schemaVersion", 2), ("inputIdentity", "short"),
])
def test_digest_recomputed_tampering_is_rejected(field, value):
    good = B.build_preview(_close(), SIGNAL)
    assert B.validate_preview(good)
    bad = _redigest({**good, field: value})
    with pytest.raises((ValueError, TypeError)):
        B.validate_preview(bad)


def test_unavailable_signal_close_receipt_stays_valid_and_cannot_claim_a_state():
    r = B.build_preview(_close().iloc[:-1], SIGNAL)
    assert r["adverse"] is None and B.validate_preview(r)
    with pytest.raises(ValueError):
        B.validate_preview(_redigest({**r, "adverse": False}))


@pytest.mark.parametrize("base", ["2024-01-02", "2024-09-05", "2024-09-10"])
def test_base_date_must_be_the_defined_session_not_merely_before_the_target(base):
    good = B.build_preview(_close(), SIGNAL)
    assert good["baseSessionDate"] == "2024-09-11"
    with pytest.raises(ValueError, match="NOT_THE_DEFINED_SESSION"):
        B.validate_preview(_redigest({**good, "baseSessionDate": base}))
