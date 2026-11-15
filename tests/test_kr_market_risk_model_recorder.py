"""The LIVE recorder of kr-market-risk-model-v1 receipts, exercised on SYNTHETIC inputs and an injected clock. No real vendor is read."""
import json

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_market_risk_anatomy as M
from pipeline import kr_market_risk_model_receipts as R
from scripts import record_kr_market_risk_model as RC

SIGNAL = "2026-11-06"          # a Friday KR session; its receipt window runs from 18:00 KST Friday to the Monday open
IN_WINDOW = pd.Timestamp("2026-11-07T12:00:00Z")
MERGED = "2026-11-01T00:00:00+00:00"
IDENTITY = {"commitSha": "a" * 40, "files": {}, "sealedSpecSha256": "b" * 64, "calendarVersion": "test"}


def inputs(last_close=SIGNAL):
    sessions = M.kr_sessions("2014-01-02", last_close)
    rng = np.random.default_rng(7)
    close = pd.Series(250 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, len(sessions)))), index=sessions)
    days = pd.bdate_range("2013-06-03", SIGNAL)
    return {"KS200": close,
            "DGS10": pd.Series(2.0 + np.abs(rng.normal(0, 0.3, len(days))), index=days),
            "DGS3MO": pd.Series(1.0 + np.abs(rng.normal(0, 0.3, len(days))), index=days),
            "VIXCLS": pd.Series(15 + np.abs(rng.normal(0, 5, len(days))), index=days)}


@pytest.fixture()
def open_floor(monkeypatch):
    real = RC.load_registration

    def load(root=RC.ROOT):
        return {**real(root), "firstEligibleSignalSessionFloor": "2026-01-01"}
    monkeypatch.setattr(RC, "load_registration", load)


def run(tmp_path, *, now=IN_WINDOW, fetch=None):
    return RC.record(tmp_path, clock=lambda: now, fetch=fetch or (lambda s: inputs()), merged_at=MERGED, code_identity=IDENTITY)


def status(tmp_path):
    return json.loads((tmp_path / RC.STATUS).read_text())


def test_real_registration_verifies_every_pin():
    reg = RC.load_registration()
    assert reg["productionEffect"] == "NONE" and reg["finalArchitecture"] == "C0"
    assert "scripts/record_kr_market_risk_model.py" in reg["codeFileHashes"]


def test_records_one_valid_receipt_then_skips(tmp_path, open_floor):
    assert run(tmp_path) == 0 and status(tmp_path)["status"] == "RECORDED"
    rows = R.read_ledger(tmp_path / RC.RECEIPTS)
    assert len(rows) == 1 and rows[0]["signalDate"] == SIGNAL and rows[0]["executionDate"] == "2026-11-09"
    assert rows[0]["evidenceClass"] == "PROSPECTIVE_PAPER" and rows[0]["finalArchitecture"] == "C0"
    assert set(rows[0]["inputIdentities"]) == {"KS200", "DGS10", "DGS3MO", "VIXCLS"}
    before = (tmp_path / RC.RECEIPTS).read_bytes()
    assert run(tmp_path) == 0 and status(tmp_path)["status"] == "SKIPPED"
    assert (tmp_path / RC.RECEIPTS).read_bytes() == before


def test_outside_the_window_writes_nothing(tmp_path, open_floor):
    assert run(tmp_path, now=pd.Timestamp("2026-11-11T12:00:00Z")) == 0   # Wednesday: last final session is not a weekly decision session
    assert status(tmp_path)["status"] == "SKIPPED" and not (tmp_path / RC.RECEIPTS).exists()


def test_provider_failure_is_deferred_and_logged(tmp_path, open_floor):
    def broken(signal):
        raise OSError("vendor down")
    assert run(tmp_path, fetch=broken) == 0
    assert status(tmp_path)["status"] == "DEFERRED" and not (tmp_path / RC.RECEIPTS).exists()
    assert json.loads((tmp_path / RC.ATTEMPTS).read_text().splitlines()[0])["evidence"] is False


def test_unserved_signal_close_is_deferred(tmp_path, open_floor):
    assert run(tmp_path, fetch=lambda s: inputs("2026-11-05")) == 0
    assert status(tmp_path)["status"] == "DEFERRED" and not (tmp_path / RC.RECEIPTS).exists()


def test_before_the_registered_floor_nothing_is_recorded(tmp_path):
    assert run(tmp_path) == 0 and status(tmp_path)["status"] == "SKIPPED"
    assert "SIGNAL_BEFORE_REGISTERED_FLOOR" in status(tmp_path)["reason"] and not (tmp_path / RC.RECEIPTS).exists()


def test_a_changed_pinned_file_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(RC, "file_sha256", lambda p: "0" * 64)
    assert run(tmp_path) == 1 and status(tmp_path)["status"] == "REFUSED"


def test_input_identity_ignores_rows_after_the_signal_date():
    series = inputs()["VIXCLS"]
    extended = pd.concat([series, pd.Series([99.0], index=[pd.Timestamp("2026-11-09")])])
    assert RC.input_identity(series, SIGNAL) == RC.input_identity(extended, SIGNAL)


def test_hook_sits_beside_the_b_h1_hook_and_is_isolated():
    text = (RC.ROOT / "scripts" / "update_ledger.py").read_text()
    assert "record_kr_market_risk_model" in text and "market_risk.run_isolated" in text
    assert text.index("record_rp1_b_h1_state") < text.index("record_kr_market_risk_model")


def test_isolated_hook_reports_a_timeout_and_a_crash_without_raising(tmp_path):
    import sys
    import importlib
    original = importlib.reload(RC).run_isolated      # conftest stubs the module attribute for other tests; this one needs the original
    assert original(tmp_path, timeout=1, command=[sys.executable, "-c", "import time; time.sleep(5)"]) == 124
    assert status(tmp_path)["status"] == "TIMEOUT"
    assert original(tmp_path, command=[sys.executable, "-c", "raise SystemExit(7)"]) == 7
    assert status(tmp_path)["status"] == "EXCEPTION"
