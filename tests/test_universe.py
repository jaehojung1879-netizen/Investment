from types import SimpleNamespace

import pandas as pd
import pytest

from pipeline import universe as U


def test_us_rows_keeps_every_constituent_in_source_order():
    frame = pd.DataFrame({
        "Symbol": ["ZBRA", "AAPL", "BRK.B"],
        "Security": ["Zebra", "Apple", "Berkshire"],
    })

    tickers, names = U._us_rows(frame)

    assert tickers == ["ZBRA", "AAPL", "BRK-B"]
    assert names["BRK-B"] == "Berkshire"


def test_us_sp500_rejects_short_primary_and_uses_complete_backup(monkeypatch):
    short, complete = object(), object()
    monkeypatch.setattr(
        U,
        "_us_rows",
        lambda frame: (
            (["SHORT"] * 120, {})
            if frame is short
            else (["COMPLETE"] * 500, {})
        ),
    )

    tickers, _ = U._complete_us_from([
        ("short primary", lambda: short),
        ("complete backup", lambda: complete),
    ])

    assert len(tickers) == 500
    assert set(tickers) == {"COMPLETE"}


def test_resolve_refuses_partial_us_fallback(monkeypatch):
    monkeypatch.setattr(U, "_us_sp500", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(U, "_kr_kospi", lambda size: (["005930.KS"], {"005930.KS": "Samsung"}))
    cfg = SimpleNamespace(
        universe_size=120,
        universe={"US": ["AAPL"], "KR": ["005930.KS"]},
        core=[],
        names={},
        region_of=lambda ticker: "US",
    )

    with pytest.raises(RuntimeError, match="refusing partial fallback"):
        U.resolve(cfg)

