"""End to end on invented data: universe -> classification -> decision -> receipt -> ledger. No real filing, price or outcome."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import us_capital_allocation_coverage as C      # noqa: E402
from pipeline import us_capital_allocation_policy as P        # noqa: E402
from pipeline import us_capital_allocation_receipts as R      # noqa: E402
from pipeline import us_capital_allocation_weekly as W        # noqa: E402
from pipeline import us_shareholder_distribution as U         # noqa: E402

META = U.SourceMetadata(U.SOURCE, "SYNTHETIC", "synthetic fiscal-YTD source contract")
SIGNAL, MERGED = "2026-02-27", "2026-02-10T15:00:00+00:00"
CREATED, CLOCK = "2026-02-27T23:30:00+00:00", "2026-02-27T23:31:00+00:00"
SNAPSHOT = {"date": "2026-02-20", "sourceCommit": "f" * 40}
SECTOR_NAMES = ["Industrials", "Health Care", "Utilities", "Energy", "Consumer Staples", "Materials"]
N = 60


def filing(ticker, year, dividends, repurchases=30, ocf=100):
    end = date(year, 12, 31)
    cf = [{"concept": "us-gaap_" + c, "value": v, "unit": "usd"}
          for c, v in ((U.FLOW_CONCEPTS["cashDividendsPaidTTM"], dividends), (U.FLOW_CONCEPTS["commonStockRepurchasesTTM"], repurchases),
                       (U.FLOW_CONCEPTS["operatingCashFlowTTM"], ocf), (U.FLOW_CONCEPTS["capitalExpendituresTTM"], 10))]
    return dict(id=f"{ticker}-{year}-FY", ticker=ticker, source=U.SOURCE, fiscalYear=year, fiscalQuarter=0, form="10-K",
                periodStart=date(year, 1, 1).isoformat(), periodEnd=end.isoformat(), periodDays=(end - date(year, 1, 1)).days,
                availableFrom=(end + timedelta(days=30)).isoformat(), collectedAt="2026-02-01T00:00:00Z", acceptedDate=None,
                statements={"cf": cf, "ic": [], "bs": [{"concept": "us-gaap_CommonStockSharesOutstanding", "value": 100, "unit": "shares"}]})


def tickers():
    return ["T%02d" % i for i in range(N)]


def world(*, price_history=300):
    names = tickers()
    engines = {t: U.FeatureEngine(t, [filing(t, 2024, 20), filing(t, 2025, 20 + (i % 12) * 4)], META) for i, t in enumerate(names)}
    sessions = pd.bdate_range(end=SIGNAL, periods=price_history)
    prices = C.PricePresence.from_rows({"ticker": t, "date": d.strftime("%Y-%m-%d"), "Close": 50.0} for t in names for d in sessions)
    sectors = C.SectorBook([{**SNAPSHOT, "rows": {t: {"cik": "1", "sector": SECTOR_NAMES[i % len(SECTOR_NAMES)]} for i, t in enumerate(names)}}])
    ctx = C.WeekContext(engines=engines, prices=prices, sectors=sectors, ciks={}, category={}, malformed={}, renames={}, ambiguous=set())
    return ctx, {**SNAPSHOT, "members": names}


def frame(sessions=5):
    index = pd.bdate_range(end=SIGNAL, periods=sessions)
    close = np.linspace(100.0, 105.0, sessions)
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1000.0,
                         "Dividends": 0.0, "Stock Splits": 0.0}, index=index)


def prices_for(chosen):
    return {t: W.price_row(frame(), SIGNAL, "SYNTHETIC", "2026-02-27T23:10:00+00:00") for t in ("SPY", "QQQ", *chosen)}


def build(week, *, clock=CLOCK, created=CREATED):
    chosen = sorted(week["decision"]["weights"] or [])
    return R.build_synthetic_receipt(
        signal_date=SIGNAL, created_at_utc=created, test_clock_utc=clock, spec_sha256="a" * 64,
        code_identity={"commitSha": "b" * 40, "files": {"pipeline/us_capital_allocation_policy.py": "c" * 64}},
        data_identity={k: "d" * 64 for k in R.DATA_IDENTITY_KEYS},
        authorization={"specSha256": "a" * 64, "mergeCommitSha": "e" * 40, "mergedAtUtc": MERGED},
        decision=week["decision"], coverage={}, membership=week["membership"], observation_prices=prices_for(chosen),
        pit_evidence=week["pit_evidence"], measured_tickers=week["measured_tickers"])


def test_week_selects_within_the_registered_limits():
    ctx, snapshot = world()
    week = W.observe_week(ctx, snapshot, SIGNAL)
    decision = week["decision"]
    assert decision["status"] != "BLOCKED" and 0 < len(decision["selected"]) <= P.MAX_NAMES
    sectors = [s["sector"] for s in decision["selected"]]
    assert all(sectors.count(s) <= P.MAX_NAMES_PER_SECTOR for s in set(sectors))
    assert sum(decision["weights"].values()) + decision["fallbackWeight"] == pytest.approx(1.0)
    assert set(week["pit_evidence"]) == set(decision["weights"])
    assert week["statusCounts"][C.JOINT_MEASURED] == N


def test_selection_is_independent_of_member_order():
    ctx, snapshot = world()
    first = W.observe_week(ctx, snapshot, SIGNAL)["decision"]
    second = W.observe_week(ctx, {**snapshot, "members": list(reversed(snapshot["members"]))}, SIGNAL)["decision"]
    assert first == second


def test_short_price_history_blocks_rather_than_selects():
    ctx, snapshot = world(price_history=100)
    week = W.observe_week(ctx, snapshot, SIGNAL)
    assert week["decision"]["status"] == "BLOCKED" and week["decision"]["weights"] is None
    assert week["statusCounts"] == {C.PRICE_HISTORY_INSUFFICIENT: N}


def test_same_day_or_later_membership_snapshot_is_refused():
    ctx, snapshot = world()
    for stamp in (SIGNAL, "2026-03-06"):
        with pytest.raises(ValueError, match="MEMBERSHIP_SNAPSHOT_NOT_STRICTLY_BEFORE"):
            W.observe_week(ctx, {**snapshot, "date": stamp}, SIGNAL)
    with pytest.raises(ValueError):
        W.observe_week(ctx, None, SIGNAL)


def test_filing_available_on_the_signal_day_is_not_used():
    ctx, snapshot = world()
    for available, expected in ((SIGNAL, C.REPORT_STALE), ("2026-02-26", C.JOINT_MEASURED)):
        late = filing("T00", 2025, 200)
        late["availableFrom"] = available
        ctx.engines["T00"] = U.FeatureEngine("T00", [filing("T00", 2024, 20), late], META)
        # Only the 2024 report is visible on the signal day itself, and it is more than 180 days old.
        assert C.classify_member(ctx, snapshot, SIGNAL, "T00").status == expected


def test_receipt_roundtrip_and_append_only_ledger(tmp_path):
    ctx, snapshot = world()
    week = W.observe_week(ctx, snapshot, SIGNAL)
    receipt = build(week)
    assert receipt["officialWeeklyDecisionAffected"] is False and receipt["namespace"] == P.NAMESPACE
    assert set(receipt["pitEvidence"]) == set(week["decision"]["weights"])
    assert receipt["membership"]["snapshotDate"] < SIGNAL
    path = tmp_path / "ledger/research/us-capital-allocation-alpha-v1/receipts.jsonl"
    R.append_synthetic_receipt(path, receipt)
    with pytest.raises(ValueError, match="RECEIPT_ALREADY_EXISTS"):
        R.append_synthetic_receipt(path, receipt)                     # the same week cannot be written twice
    assert R.read_synthetic_ledger(path) == [receipt]


def test_receipt_refused_before_the_close_has_final_prices():
    ctx, snapshot = world()
    week = W.observe_week(ctx, snapshot, SIGNAL)
    with pytest.raises(ValueError):
        build(week, created="2026-02-27T20:00:00+00:00", clock="2026-02-27T20:01:00+00:00")


def test_price_row_requires_the_signal_session_and_never_substitutes_an_earlier_close():
    row = W.price_row(frame(), SIGNAL, "SYNTHETIC", "2026-02-27T23:10:00+00:00")
    assert row["session"] == SIGNAL and row["asTradedClose"] == pytest.approx(105.0) and row["basis"] == W.PRICE_BASIS
    with pytest.raises(ValueError, match="NO_CLOSE_ON_THE_SIGNAL_SESSION"):
        W.price_row(frame().iloc[:-1], SIGNAL, "SYNTHETIC", "2026-02-27T23:10:00+00:00")
