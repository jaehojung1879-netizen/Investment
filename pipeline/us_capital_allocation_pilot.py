"""Executable preflight of the research-only weekly observation path. Synthetic fixtures only; no real receipt is written anywhere.

Every check RUNS the production code on invented inputs and records PASS only if the expected refusal or output occurred. It
establishes that the path behaves; it does not establish that the live inputs exist (they do not: see the readiness report).
The temporary ledger it writes lives in a caller-supplied directory and uses the SYNTHETIC pathway, which the live ledger path
refuses to read.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import prospective_receipt_core as CORE
from pipeline import us_capital_allocation_coverage as C
from pipeline import us_capital_allocation_evaluation as E
from pipeline import us_capital_allocation_policy as P
from pipeline import us_capital_allocation_receipts as R
from pipeline import us_capital_allocation_weekly as W
from pipeline import us_shareholder_distribution as U

ROOT = Path(__file__).resolve().parents[1]
META = U.SourceMetadata(U.SOURCE, "SYNTHETIC", "synthetic fiscal-YTD source contract")
SIGNAL, MERGED = "2026-02-27", "2026-02-10T15:00:00+00:00"
CREATED, CLOCK = "2026-02-27T23:30:00+00:00", "2026-02-27T23:31:00+00:00"
SNAPSHOT = {"date": "2026-02-20", "sourceCommit": "f" * 40}
SECTORS = ["Industrials", "Health Care", "Utilities", "Energy", "Consumer Staples", "Materials"]
N = 60


def filing(ticker, year, dividends, repurchases=30, ocf=100, available=None):
    end = date(year, 12, 31)
    cf = [{"concept": "us-gaap_" + c, "value": v, "unit": "usd"}
          for c, v in ((U.FLOW_CONCEPTS["cashDividendsPaidTTM"], dividends), (U.FLOW_CONCEPTS["commonStockRepurchasesTTM"], repurchases),
                       (U.FLOW_CONCEPTS["operatingCashFlowTTM"], ocf), (U.FLOW_CONCEPTS["capitalExpendituresTTM"], 10))]
    return dict(id=f"{ticker}-{year}-FY", ticker=ticker, source=U.SOURCE, fiscalYear=year, fiscalQuarter=0, form="10-K",
                periodStart=date(year, 1, 1).isoformat(), periodEnd=end.isoformat(), periodDays=(end - date(year, 1, 1)).days,
                availableFrom=available or (end + timedelta(days=30)).isoformat(), collectedAt="2026-02-01T00:00:00Z", acceptedDate=None,
                statements={"cf": cf, "ic": [], "bs": [{"concept": "us-gaap_CommonStockSharesOutstanding", "value": 100, "unit": "shares"}]})


def synthetic_world(*, price_history=300, renames=None):
    names = ["T%02d" % i for i in range(N)]
    engines = {}
    for i, t in enumerate(names):
        priced_as = (renames or {}).get(t, t)      # fundamentals and prices are both filed under the verified successor ticker
        engines[priced_as] = U.FeatureEngine(priced_as, [filing(priced_as, 2024, 20), filing(priced_as, 2025, 20 + (i % 12) * 4)], META)
    sessions = pd.bdate_range(end=SIGNAL, periods=price_history)
    priced = {(renames or {}).get(t, t) for t in names}
    prices = C.PricePresence.from_rows({"ticker": t, "date": d.strftime("%Y-%m-%d"), "Close": 50.0} for t in priced for d in sessions)
    sectors = C.SectorBook([{**SNAPSHOT, "rows": {t: {"cik": "1", "sector": SECTORS[i % len(SECTORS)]} for i, t in enumerate(names)}}])
    ctx = C.WeekContext(engines=engines, prices=prices, sectors=sectors, ciks={}, category={}, malformed={}, renames=dict(renames or {}),
                        ambiguous=set())
    return ctx, {**SNAPSHOT, "members": names}


def _frame(sessions=5):
    index = pd.bdate_range(end=SIGNAL, periods=sessions)
    close = np.linspace(100.0, 105.0, sessions)
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1000.0, "Dividends": 0.0, "Stock Splits": 0.0}, index=index)


def _prices(chosen, retrieved="2026-02-27T23:10:00+00:00"):
    keys = ("SPY", "QQQ", *chosen)
    return {t: W.price_row(_frame(), SIGNAL, "SYNTHETIC", retrieved) for t in keys}


def _build(week, *, clock=CLOCK, created=CREATED, retrieved="2026-02-27T23:10:00+00:00"):
    chosen = sorted(week["decision"]["weights"] or [])
    return R.build_synthetic_receipt(
        signal_date=SIGNAL, created_at_utc=created, test_clock_utc=clock, spec_sha256="a" * 64,
        code_identity={"commitSha": "b" * 40, "files": {"pipeline/us_capital_allocation_policy.py": "c" * 64}},
        data_identity={k: "d" * 64 for k in R.DATA_IDENTITY_KEYS},
        authorization={"specSha256": "a" * 64, "mergeCommitSha": "e" * 40, "mergedAtUtc": MERGED},
        decision=week["decision"], coverage={}, membership=week["membership"], observation_prices=_prices(chosen, retrieved),
        pit_evidence=week["pit_evidence"], measured_tickers=week["measured_tickers"])


def _expect_refusal(callable_, fragment):
    try:
        callable_()
    except Exception as exc:        # noqa: BLE001 -- the check is that a refusal with this reason occurs
        return fragment in str(exc), str(exc)[:160]
    return False, "NO_REFUSAL"


def preflight(workdir: Path, official_files: dict | None = None) -> list[dict]:
    """The twelve operational checks. Each: {'id', 'status': PASS|FAIL, 'evidence'}."""
    results = []

    def record(check, ok, evidence):
        results.append({"id": check, "status": "PASS" if ok else "FAIL", "evidence": evidence})

    ctx, snapshot = synthetic_world()
    week = W.observe_week(ctx, snapshot, SIGNAL)
    receipt = _build(week)

    ok, msg = _expect_refusal(lambda: W.observe_week(ctx, {**snapshot, "date": SIGNAL}, SIGNAL), "MEMBERSHIP_SNAPSHOT_NOT_STRICTLY_BEFORE")
    record("PIT_MEMBERSHIP_STRICTLY_BEFORE_SIGNAL", ok, msg)

    late = filing("T00", 2025, 200, available=SIGNAL)
    ctx.engines["T00"] = U.FeatureEngine("T00", [filing("T00", 2024, 20), late], META)
    hidden = C.classify_member(ctx, snapshot, SIGNAL, "T00").status
    record("FILING_AVAILABLE_ON_THE_SIGNAL_DAY_IS_INVISIBLE", hidden == C.REPORT_STALE, "status=%s" % hidden)
    ctx.engines["T00"] = U.FeatureEngine("T00", [filing("T00", 2024, 20), filing("T00", 2025, 20)], META)

    refusals = [_expect_refusal(lambda: R.check_timing(signal_date="2026-02-16", created_at_utc=CREATED, now_utc=CLOCK, merged_at_utc=MERGED), "SIGNAL_DATE_IS_NOT_A_US_SESSION"),
                _expect_refusal(lambda: R.check_timing(signal_date="2026-02-26", created_at_utc=CREATED, now_utc=CLOCK, merged_at_utc=MERGED), "NOT_A_WEEKLY_DECISION_SESSION"),
                _expect_refusal(lambda: W.price_row(_frame().iloc[:-1], SIGNAL, "SYNTHETIC", CREATED), "NO_CLOSE_ON_THE_SIGNAL_SESSION")]
    record("TRADING_SESSION_EVIDENCE", all(r[0] for r in refusals), [r[1] for r in refusals])

    renamed = sorted(week["decision"]["weights"])[0]
    mapped_ctx, mapped_snapshot = synthetic_world(renames={renamed: renamed + "NEW"})
    mapped = W.observe_week(mapped_ctx, mapped_snapshot, SIGNAL)
    ambiguous_ctx, ambiguous_snapshot = synthetic_world()
    ambiguous_ctx.ambiguous.add("T02")
    amb = C.classify_member(ambiguous_ctx, ambiguous_snapshot, SIGNAL, "T02").status
    record("HISTORICAL_IDENTIFIER_MAPPING", amb == C.IDENTITY_AMBIGUOUS and mapped["priceTickers"].get(renamed) == renamed + "NEW",
           {"ambiguousExcluded": amb, "selectedSymbol": renamed, "priceSeriesTicker": mapped["priceTickers"].get(renamed)})

    evidence = receipt["pitEvidence"]
    digests = [e["featureDigest"] for e in evidence.values()]
    visible = all(str(i["availableFrom"])[:10] < SIGNAL and str(i["acceptedAt"] or "0")[:10] < SIGNAL
                  for e in evidence.values() for f in e["features"].values() for i in f["inputs"])
    record("FEATURE_LINEAGE_SHA256_AND_INPUT_VISIBILITY", bool(digests) and all(CORE.is_sha256(d) for d in digests) and visible,
           {"names": len(digests), "allInputsVisibleBeforeSignal": visible})

    weights = receipt["decision"]["weights"]
    record("SELECTED_WEIGHTS_AND_RESIDUAL_SPY", abs(sum(weights.values()) + receipt["decision"]["fallbackWeight"] - 1.0) < 1e-9
           and receipt["decision"]["fallbackAsset"] == "SPY" and all(w == P.SLOT_WEIGHT for w in weights.values()),
           {"weights": weights, "residualSPY": receipt["decision"]["fallbackWeight"]})

    record("COST_TREATMENT_RECORDED", receipt["costsAssumedBps"] == P.costs_bps(), receipt["costsAssumedBps"]["switchBpsPerUnitStockWeight"])

    short_ctx, short_snapshot = synthetic_world(price_history=100)
    blocked = _build(W.observe_week(short_ctx, short_snapshot, SIGNAL))
    record("BLOCKED_DATE_RECEIPT_HAS_NO_WEIGHTS_OR_EVIDENCE",
           blocked["decision"]["status"] == "BLOCKED" and blocked["decision"]["weights"] is None and blocked["pitEvidence"] == {}
           and blocked["observationPrices"] == {}, blocked["decision"]["reasons"])

    ledger = Path(workdir) / "ledger/research/us-capital-allocation-alpha-v1/receipts.jsonl"
    R.append_synthetic_receipt(ledger, receipt)
    dup_ok, dup_msg = _expect_refusal(lambda: R.append_synthetic_receipt(ledger, receipt), "RECEIPT_ALREADY_EXISTS")
    path_ok, path_msg = _expect_refusal(lambda: R.append_synthetic_receipt(Path(workdir) / "ledger/weekly-decisions/x.jsonl", receipt), "")
    live_ok, live_msg = _expect_refusal(lambda: R.read_live_ledger(ledger), "")
    record("APPEND_ONLY_NON_DUPLICATE_AND_NAMESPACE", dup_ok and path_ok and live_ok and R.read_synthetic_ledger(ledger) == [receipt],
           {"duplicate": dup_msg, "officialWeeklyPath": path_msg, "syntheticRowOnLiveReader": live_msg})

    stale = _expect_refusal(lambda: _build(week, retrieved="2026-02-27T20:00:00+00:00"), "OBSERVATION_PRICE_RETRIEVED_OUTSIDE_THE_RECEIPT_WINDOW")
    old_sig = C.classify_member(ctx, snapshot, "2026-03-20", "T03").status      # 21 days after the last close in the fixture
    record("LATEST_VERSUS_STALE_INPUTS", stale[0] and old_sig == C.PRICE_STALE and week["decision"]["status"] != "BLOCKED",
           {"priceRetrievedBeforeCloseRefused": stale[1], "priceOlderThanLimit": old_sig})

    days = pd.bdate_range("2026-03-02", periods=30)
    delisted = pd.DataFrame({"Close": [100.0] * 5, "Dividends": 0.0, "Stock Splits": 0.0}, index=days[:5])
    outcome = E.name_outcome(delisted, days[0], days[-1])
    portfolio = E.portfolio_outcome({"X": 0.15}, 0.85, {"X": outcome}, 0.01, 0.02)
    record("DELISTED_NAME_WITHOUT_EXIT_IS_UNRESOLVED_NEVER_ZERO", outcome["state"] == E.TERMINAL_UNRESOLVED and outcome["totalReturn"] is None
           and portfolio["netReturn"] is None, {"name": outcome["state"], "portfolio": portfolio["status"]})

    live_refused = _expect_refusal(lambda: R.build_live_receipt(signal_date=SIGNAL, decision=week["decision"], coverage={}, membership={},
                                                               observation_prices={}, pit_evidence={}, measured_tickers=[], data_files={}),
                                   "NOT_AUTHORIZED")
    unchanged = True
    if official_files is not None:
        unchanged = all(hashlib.sha256((ROOT / "docs/weekly-decision" / n).read_bytes()).hexdigest() == h for n, h in official_files.items())
    record("OFFICIAL_P1_UNTOUCHED_AND_LIVE_PATH_REFUSED", live_refused[0] and unchanged and R.REGISTERED_AUTHORIZATION is None,
           {"liveRefusal": live_refused[1], "officialFilesUnchanged": unchanged, "registeredAuthorization": R.REGISTERED_AUTHORIZATION})
    return results
