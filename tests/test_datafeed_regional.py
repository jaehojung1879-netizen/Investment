from types import SimpleNamespace

import numpy as np
import pandas as pd

from pipeline import datafeed
from pipeline import historical_outcomes as outcomes


def _frame(index):
    values = np.linspace(100.0, 120.0, len(index))
    return pd.DataFrame({
        "Open": values,
        "High": values,
        "Low": values,
        "Close": values,
        "Volume": np.full(len(index), 1_000),
    }, index=index)


def test_download_retry_forces_exchange_local_daily_labels(monkeypatch):
    captured = {}

    def fake_download(tickers, **kwargs):
        captured.update(kwargs)
        return _frame(pd.date_range("2024-01-02", periods=2))

    monkeypatch.setitem(
        __import__("sys").modules, "yfinance",
        SimpleNamespace(download=fake_download),
    )

    assert datafeed.download_retry(["005930.KS"], "2024-01-01") is not None
    assert captured["ignore_tz"] is True


def test_regional_fetch_never_mixes_market_calendars_in_one_batch(monkeypatch):
    """Regions are downloaded separately; benchmarks are not fetched here at all.

    Benchmark acquisition moved to ``pipeline.benchmark_source``, which adds the
    two things this path could not provide: vendor redundancy and a plausibility
    check against the session calendar already on record. Folding the benchmark
    into the universe fetch is what let a one-row response pass for a decade of
    index history on 08-20, 08-23 and 08-24.
    """
    calls = []

    def fake_fetch(tickers, start, batch=40):
        calls.append((list(tickers), start, batch))
        dates = pd.bdate_range("2024-01-02", periods=3)
        return {ticker: _frame(dates) for ticker in tickers}

    monkeypatch.setattr(datafeed, "fetch_prices", fake_fetch)
    prices = datafeed.fetch_regional_prices(
        {"US": ["AAPL", "MSFT"], "KR": ["005930.KS"]}, "2020-01-01")

    assert calls == [
        (["AAPL", "MSFT"], "2020-01-01", 40),
        (["005930.KS"], "2020-01-01", 40),
    ]
    assert set(prices) == {"AAPL", "MSFT", "005930.KS"}


def test_benchmark_session_preflight_accepts_timezone_equivalent_dates():
    dates = pd.bdate_range("2019-01-02", periods=500)
    prices = {
        "005930.KS": _frame(dates.tz_localize("Asia/Seoul")),
        "^KS200": _frame(dates),
    }

    result = outcomes.benchmark_session_preflight(
        prices, {"KR": ["005930.KS"]}, {"KR": "^KS200"},
        start="2020-01-01", horizon=21, min_history_rows=20,
    )

    assert result["eligible"] is True
    assert result["regions"]["KR"]["coveragePct"] == 100.0


def test_benchmark_session_preflight_fails_with_actionable_samples():
    stock_dates = pd.bdate_range("2019-01-02", periods=500)
    benchmark_dates = pd.date_range("2019-01-06", periods=500, freq="W-SUN")
    prices = {
        "005930.KS": _frame(stock_dates),
        "^KS200": _frame(benchmark_dates),
    }

    result = outcomes.benchmark_session_preflight(
        prices, {"KR": ["005930.KS"]}, {"KR": "^KS200"},
        start="2020-01-01", horizon=21, min_history_rows=20,
    )

    assert result["eligible"] is False
    failure = result["failures"][0]
    assert failure["region"] == "KR"
    assert failure["coveragePct"] == 0.0
    assert failure["missingSamples"][0] == {
        "ticker": "005930.KS",
        "startDate": "2020-01-01",
        "endDate": "2020-01-30",
        "benchmarkHasStart": False,
        "benchmarkHasEnd": False,
    }
