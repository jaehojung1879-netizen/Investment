"""Vendor vintage and process restart invariance for the prospective paper book."""
from datetime import datetime, timezone
import json

import pandas as pd
import pytest

from pipeline import entry_state_shadow_ledger as L
from test_entry_state_shadow_ledger import SUNDAY, observation


ORIGINS = {"000001.KS": "2026-10-30", "069500.KS": "2026-10-30"}
DATES = ["2026-10-30", "2026-11-02", "2026-11-03"]
MONDAY = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
TUESDAY = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)


def read(directory, name):
    p = directory / name
    return [json.loads(s) for s in p.read_text().splitlines()] if p.exists() else []


def frames(stock, etf=(100.0, 101.0, 102.0)):
    return {ticker: pd.DataFrame({"Close": values}, index=pd.to_datetime(DATES[:len(values)]))
            for ticker, values in [("000001.KS", stock), ("069500.KS", etf[:len(stock)])]}


def record(directory, *, as_of="2026-10-30", stock_weight=0.3):
    return L.append_decisions(directory, L.decision_receipts(
        observation(as_of=as_of, stocks={"000001.KS": stock_weight}, residual=1-stock_weight),
        recorded_at=SUNDAY, code={"commit": "test"}, observation_sha256=as_of))


def test_superseded_receipt_cannot_trade_after_restart(tmp_path):
    record(tmp_path, as_of="2026-10-23", stock_weight=0.8)
    record(tmp_path, stock_weight=0.2)
    close = lambda ticker, session: 100.0
    L.advance(tmp_path, now=MONDAY, close_of=close, through="2026-11-02")
    original = (tmp_path / "fills.jsonl").read_bytes()
    L.advance(tmp_path, now=TUESDAY, close_of=close, through="2026-11-03")
    assert (tmp_path / "fills.jsonl").read_bytes() == original
    selected = [r for r in read(tmp_path, "fills.jsonl") if r["strategyId"] == "KR:N1:IN_RANK"]
    assert len(selected) == 1
    assert selected[0]["decisionAsOfDate"] == "2026-10-30"
    assert selected[0]["supersededReceiptIds"]


@pytest.mark.parametrize("scale", [0.5, 2.0, 0.9], ids=["split", "reverse-split", "dividend-adjustment"])
def test_acquisition_vintage_and_restart_do_not_change_nav(tmp_path, scale, monkeypatch):
    from scripts import record_entry_state_shadow as recorder

    one, resumed = tmp_path / "one", tmp_path / "resumed"
    record(one)
    record(resumed)
    acquisition = [frames([100.0, 100.0])]
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **kw: acquisition[0])
    L.advance(resumed, now=MONDAY, close_of=recorder.live_closes(resumed), through="2026-11-02")
    later = frames([100*scale, 100*scale, 110*scale])
    acquisition[0] = later
    L.advance(resumed, now=TUESDAY, close_of=recorder.live_closes(resumed), through="2026-11-03")
    L.advance(one, now=TUESDAY, close_of=recorder.live_closes(one), through="2026-11-03")
    for name in ("fills.jsonl", "nav-daily.jsonl"):
        a, b = read(one, name), read(resumed, name)
        key = lambda r: (r["strategyId"], r.get("date", r.get("session")))
        a, b = sorted(a, key=key), sorted(b, key=key)
        assert len(a) == len(b)
        for left, right in zip(a, b):
            assert key(left) == key(right)
            for field in ("nav", "postTradeNav", "costFraction"):
                if field in left:
                    assert left[field] == pytest.approx(right[field], abs=1e-12)
            if "units" in left:
                assert left["units"] == pytest.approx(right["units"], abs=1e-12)
    rank = [r for r in read(resumed, "nav-daily.jsonl") if r["strategyId"] == "KR:N1:IN_RANK"]
    assert rank[-1]["nav"] / rank[0]["nav"] == pytest.approx(0.3*1.1 + 0.7*102/101)


def test_nonuniform_vendor_revision_is_refused_without_rewriting(tmp_path):
    record(tmp_path)
    L.advance(tmp_path, now=MONDAY, close_of=L.anchored_closes(
        frames([100, 100]), ORIGINS, []), through="2026-11-02")
    saved = (tmp_path / "nav-daily.jsonl").read_bytes()
    with pytest.raises(ValueError, match="VENDOR_RETURN_PREFIX_REVISED"):
        L.anchored_closes(frames([50, 49, 55]), ORIGINS, read(tmp_path, "nav-daily.jsonl"))
    assert (tmp_path / "nav-daily.jsonl").read_bytes() == saved


def test_origin_must_be_exact_not_first_available_quote():
    source = frames([100, 100, 110])
    source["000001.KS"] = source["000001.KS"].iloc[1:]
    lookup = L.anchored_closes(source, ORIGINS, [])
    assert lookup("000001.KS", "2026-11-02") is None


def test_old_price_coordinate_book_is_not_silently_migrated():
    with pytest.raises(ValueError, match="LEGACY_VALUATION_BASIS"):
        L.anchored_closes(frames([100, 100, 110]), ORIGINS, [
            {"status": "MARKED", "date": "2026-11-02", "nav": 1,
             "returnBasis": "VENDOR_ADJUSTED_CLOSE_AT_MARK_TIME_LATER_READJUSTMENTS_NOT_REAPPLIED"}])


def test_changed_origin_cannot_rebase_published_marks(tmp_path):
    record(tmp_path)
    L.advance(tmp_path, now=MONDAY, close_of=L.anchored_closes(
        frames([100, 100]), ORIGINS, []), through="2026-11-02")
    changed = {**ORIGINS, "000001.KS": "2026-11-02"}
    with pytest.raises(ValueError, match="VALUATION_ORIGIN_CHANGED"):
        L.anchored_closes(frames([100, 100, 110]), changed, read(tmp_path, "nav-daily.jsonl"))


def test_interrupted_two_file_checkpoint_is_refused(tmp_path):
    record(tmp_path)
    close = L.anchored_closes(frames([100, 100]), ORIGINS, [])
    L.advance(tmp_path, now=MONDAY, close_of=close, through="2026-11-02")
    (tmp_path / "nav-daily.jsonl").unlink()  # interrupted after fills were persisted
    saved_fills = (tmp_path / "fills.jsonl").read_bytes()
    with pytest.raises(ValueError, match="FILL_NAV_CHECKPOINT_INCOMPLETE"):
        L.advance(tmp_path, now=TUESDAY, close_of=close, through="2026-11-03")
    assert (tmp_path / "fills.jsonl").read_bytes() == saved_fills
    assert not (tmp_path / "nav-daily.jsonl").exists()


def test_live_adapter_uses_fixed_signal_origins(tmp_path, monkeypatch):
    from scripts import record_entry_state_shadow as recorder

    record(tmp_path)
    calls = []
    def fetch(tickers, start, **kwargs):
        calls.append((tickers, start, kwargs))
        return frames([50, 50, 55])
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", fetch)
    close = recorder.live_closes(tmp_path)
    assert calls == [(["000001.KS", "069500.KS"], "2026-10-30", {"auto_adjust": True})]
    assert close("000001.KS", "2026-11-03") == pytest.approx(1.1)
    assert close.valuation_origins == ORIGINS
