"""Network-free exact provenance and routing checks for weekly DART refresh."""
from pathlib import Path

import pytest

from pipeline import dart_weekly_workflow_maintenance as M

ROOT = Path(__file__).resolve().parents[1]


def test_exact_variant_and_historical_blob():
    original = M.historical_bytes(ROOT)
    assert M.original_for_census(ROOT) == original
    assert (ROOT / M.WORKFLOW).read_bytes() == M.variant(original)


def test_unregistered_change_fails_closed(tmp_path, monkeypatch):
    original = M.historical_bytes(ROOT)
    monkeypatch.setattr(M, "historical_bytes", lambda _: original)
    path = tmp_path / M.WORKFLOW
    path.parent.mkdir(parents=True)
    path.write_bytes(M.variant(original) + b"\n# unregistered edit\n")
    with pytest.raises(ValueError, match="UNREGISTERED_DELTA"):
        M.original_for_census(tmp_path)


def test_invalid_original_fails_closed():
    with pytest.raises(ValueError, match="BASE_CHANGED"):
        M.variant(b"unexpected workflow")


def test_schedule_keeps_original_writer_and_narrow_paths():
    live = (ROOT / M.WORKFLOW).read_text()
    assert live.count('cron: "17 19 * * 2"') == 1
    assert live.count("github.event.schedule == '40 3 * * *'") == 2
    assert "group: signal-history-fundamentals" in live
    assert "cancel-in-progress: false" in live
    assert "MAX_CALLS=600" in live and "MAX_MINUTES=120" in live
    assert "paths=(ledger/fundamentals/kr-raw ledger/fundamentals/kr-canonical-v2)" in live
    assert 'if [ "$EVENT_NAME" != schedule ]; then' in live
    assert "SEALED_SIGNAL_HISTORY_COMMIT: 4ea107ed0cde289f0a049a65ff13d2441a786710" in live
