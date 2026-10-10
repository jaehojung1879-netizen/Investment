"""us-source-readiness-v1 measures filings, never outcomes."""
import ast
import gzip
import json
from pathlib import Path

from pipeline import us_source_readiness as U

ROOT = Path(__file__).resolve().parent.parent


def _filing(ticker, year, form, period_end, available, concepts):
    return {"ticker": ticker, "fiscalYear": year, "form": form, "periodEnd": period_end,
            "availableFrom": available, "acceptedDate": available + " 16:00:00",
            "statements": {"cf": [{"concept": c, "value": 1.0} for c in concepts]}}


def test_measures_reporting_rates_and_delays(tmp_path):
    rows = [
        _filing("A", 2020, "10-Q", "2020-03-31", "2020-05-01", ["us-gaap_PaymentsOfDividendsCommonStock"]),
        _filing("B", 2020, "10-K", "2020-12-31", "2021-02-20", []),
        _filing("C", 1215, "10-K", "2020-12-31", "2021-02-20", []),
    ]
    with gzip.open(tmp_path / "finnhub-2020.jsonl.gz", "wt") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    out = U.measure_store(U.iter_store(tmp_path))
    assert out["filings"] == 2 and out["malformedFiscalYearFilings"] == 1
    assert out["byFiscalYearPctOfFilings"]["2020"]["cashDividendsPaid"] == 50.0
    assert out["filingDelayDays"]["10-Q"]["median"] == 31
    assert out["filingsVisibleBeforePeriodEnd"] == 0


def test_a_value_never_stated_is_not_counted_as_present():
    rec = {"ticker": "A", "fiscalYear": 2021, "form": "10-K", "periodEnd": "2021-12-31",
           "availableFrom": "2022-02-01",
           "statements": {"cf": [{"concept": "us-gaap_PaymentsOfDividends", "value": None}]}}
    out = U.measure_store([rec])
    assert out["byFiscalYearPctOfFilings"]["2021"]["cashDividendsPaid"] == 0.0


def test_inventory_never_claims_an_unprobed_or_paid_source_is_available():
    statuses = {row["axis"]: row["status"] for row in U.INVENTORY}
    assert statuses["Short interest"] == "NOT_PROBED"
    assert statuses["Delisted / departed company prices"] == "BLOCKED_PAID_SOURCE"
    assert statuses["Analyst estimates / revisions"] == "BLOCKED_PAID_SOURCE"
    assert all(row["evidence"] for row in U.INVENTORY)


def test_module_reads_no_outcomes():
    tree = ast.parse((ROOT / "pipeline/us_source_readiness.py").read_text())
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | \
        {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    forbidden = {"pipeline.historical_outcomes", "pipeline.replay_valuation", "pipeline.datafeed",
                 "pipeline.portfolio_validation"}
    assert not ({m for m in imported if m} & forbidden)
    text = (ROOT / "pipeline/us_source_readiness.py").read_text()
    assert "excessReturn" not in text and "outcomes" not in text.lower().replace("outcome-blind", "")


def test_history_keeps_us_out_of_the_headline():
    from pipeline import weekly_history as H
    history = H.build_history()
    us = history["replay"]["regions"]["US"]
    assert us["headlineEligible"] is False and us["status"] == "SURVIVORSHIP_BIASED_PARTIAL"
    assert history["usReadiness"]["historicalDiscoveryPhase"] == "CLOSED"
    local = history["usLocalCurrency"]
    assert local["basis"] == "USD" and "C1" not in local["paths"]  # KRW cash has no exact USD form
    # The rule never held a US stock, so its path is SPY's in either currency.
    assert local["paths"]["P1"] == local["paths"]["P0"]


def test_usd_conversion_is_an_exact_identity():
    import pandas as pd
    from scripts.derive_us_local_currency import convert
    fx = pd.Series([1000.0, 1100.0, 1210.0], index=pd.to_datetime(["2020-01-02", "2021-01-04", "2022-01-03"]))
    # A KRW path that is pure FX appreciation is flat in USD.
    out = convert([["2021-01-04", 1.1], ["2022-01-03", 1.21]], fx, "2020-01-02", "2022-01-03")
    assert out["finalNav"] == 1.0 and abs(out["cagrPct"]) < 1e-9
