"""An empty KRX answer is final only once the session had time to publish."""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location(
    "collect_krx_daily_prices", ROOT / "scripts" / "collect_krx_daily_prices.py")
CKP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CKP)

AS_OF = dt.date(2026, 10, 19)


def _run(tmp_path, monkeypatch, targets):
    monkeypatch.setattr(CKP, "call", lambda *a, **k: {"OutBlock_1": []})
    return CKP.collect(tmp_path, targets, auth_key="k", base="b", keep=None,
                       max_calls=10, max_minutes=1.0, pace=0, log=lambda *_: None,
                       as_of=AS_OF)


def test_recent_empty_answer_is_provisional_not_done(tmp_path, monkeypatch):
    result = _run(tmp_path, monkeypatch, ["2026-10-16", "2026-10-19"])
    assert result["closed"] == []
    assert result["provisional"] == ["2026-10-16", "2026-10-19"]
    assert result["remaining"] == 2
    assert CKP.load_done(tmp_path) == set()


def test_old_empty_answer_is_a_settled_closure(tmp_path, monkeypatch):
    result = _run(tmp_path, monkeypatch, ["2026-10-05"])
    assert result["closed"] == ["2026-10-05"]
    assert result["provisional"] == []
    assert result["remaining"] == 0
    assert CKP.load_done(tmp_path) == {"2026-10-05"}


def test_settle_boundary():
    assert not CKP.is_settled("2026-10-16", AS_OF)
    assert CKP.is_settled("2026-10-15", AS_OF)
