"""MVMA-v1 input build and signal ledger on synthetic files (no network, no real outcome)."""
from __future__ import annotations

import csv
import datetime as dt
import gzip

import pandas as pd
import pytest

from research.market_valuation_macro_overlay_v1 import build_signals as B
from research.market_valuation_macro_overlay_v1 import collect_inputs as C


def test_month_end_sessions_come_from_the_calendar_not_the_data():
    sessions = pd.to_datetime(["2024-01-30", "2024-01-31", "2024-02-28", "2024-02-29", "2024-03-28"])
    assert C.month_end_sessions(sessions, "2024-01", "2024-03") == [
        dt.date(2024, 1, 31), dt.date(2024, 2, 29), dt.date(2024, 3, 28)]
    assert C.month_end_sessions(sessions, "2024-02", "2024-02") == [dt.date(2024, 2, 29)]


def test_latest_observation_skips_blanks():
    assert C.latest_observation([("2024-01-01", 1.0), ("2024-02-01", None)]) == ("2024-01-01", 1.0)
    assert C.latest_observation([("2024-01-01", None)]) == (None, None)


def test_gzip_is_byte_deterministic():
    assert C.gzip_bytes(b"abc") == C.gzip_bytes(b"abc")
    assert gzip.decompress(C.gzip_bytes(b"abc")) == b"abc"


def test_distribution_reconciliation_restates_splits_and_separates_zero_rows():
    issuer = [{"exDate": "2017-07-03", "dividend": 0.203, "shortTermCapitalGain": 0.0, "longTermCapitalGain": 0.0},
              {"exDate": "2018-01-02", "dividend": 0.30, "shortTermCapitalGain": 0.01, "longTermCapitalGain": 0.0},
              {"exDate": "2014-01-02", "dividend": 0.0, "shortTermCapitalGain": 0.0, "longTermCapitalGain": 0.0},
              {"exDate": "2026-11-02", "dividend": 0.31, "shortTermCapitalGain": 0.0, "longTermCapitalGain": 0.0}]
    vendor = [{"exDate": "2017-07-03", "amount": 0.406}, {"exDate": "2018-01-02", "amount": 0.31}]
    split = [{"date": "2017-11-30", "numerator": 1.0, "denominator": 2.0}]
    rec = C.reconcile_distributions(issuer, vendor, split)
    assert rec["matchedDates"] == 2 and rec["amountConflicts"] == 0
    assert rec["issuerZeroAmountRowsWithoutVendorEvent"] == 1
    assert rec["issuerPaidEventsMissingAtVendor"] == ["2026-11-02"]
    assert rec["verdict"] == "USE_ISSUER_DISTRIBUTIONS"
    unadjusted = C.reconcile_distributions(issuer[:1], vendor[:1])
    assert unadjusted["amountConflicts"] == 1
    assert C.reconcile_distributions(issuer[:2], vendor, split)["verdict"] == "VENDOR_MATCHES_ISSUER"


def _months(first, last):
    y, m = int(first[:4]), int(first[5:])
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


@pytest.fixture()
def synthetic_inputs(tmp_path):
    months = _months("2005-01", "2024-09")
    with (tmp_path / B.SHILLER_FILE).open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "P", "D", "E", "CPI", "CAPE", "partialMonth"])
        for i, mo in enumerate(months):
            w.writerow([mo, 1000 + 3 * i, 1, 50 + 0.2 * i, 1, 20, int(mo == months[-1])])
    decisions = []
    for mo in _months("2007-01", "2024-08"):
        y, m = int(mo[:4]), int(mo[5:])
        nxt = dt.date(y + m // 12, m % 12 + 1, 1)
        decisions.append(nxt - dt.timedelta(days=1))
    for series, base in (("BAA", 6.0), ("GS10", 3.0)):
        with (tmp_path / f"alfred-{series}-asof-decisions.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["decisionDate", "status", "observationDate", "value"])
            for i, d in enumerate(decisions):
                prev = (d.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
                obs = prev.isoformat()
                if series == "GS10" and i == 100:
                    obs = (prev - dt.timedelta(days=40)).replace(day=1).isoformat()   # stale leg
                w.writerow([d.isoformat(), "VINTAGE_SERVED", obs, base + (i % 7) * 0.1])
    spy = tmp_path / "spy.csv.gz"
    sessions = pd.bdate_range("2010-01-01", "2024-09-30")
    with gzip.open(spy, "wt") as f:
        f.write("ticker,date,totalReturnClose,rawClose\n")
        for i, s in enumerate(sessions):
            f.write(f"SPY,{s.date().isoformat()},NOT_A_NUMBER,{100 + (i % 300)}\n")
    return tmp_path, spy, decisions


def test_signal_ledger_builds_on_the_registered_window_without_reading_total_return(synthetic_inputs):
    data_dir, spy, decisions = synthetic_inputs
    report = B.build(data_dir, spy)     # a total-return read would raise on NOT_A_NUMBER
    assert report["window"]["count"] == 152
    assert report["window"]["first"].startswith("2012-01") and report["window"]["last"].startswith("2024-08")
    assert report["spreadObservationMonthMismatches"] == 1
    assert report["outcomeReads"] == 0
    for policy in ("V1", "M1T", "VM1T", "D1"):
        assert set(report["policies"][policy]["targetCounts"]) <= {0.6, 0.8, 1.0}
    row = next(r for r in report["rows"] if r["decisionDate"] == decisions[100].isoformat())
    assert row["spread"] is None


def test_earnings_quarter_in_ledger_is_at_least_four_months_old(synthetic_inputs):
    data_dir, spy, _ = synthetic_inputs
    for row in B.build(data_dir, spy)["rows"]:
        d = dt.date.fromisoformat(row["decisionDate"])
        qy, qm = (int(x) for x in row["shillerEarningsQuarter"].split("-"))
        assert qm in (3, 6, 9, 12)
        assert (d.year * 12 + d.month) - (qy * 12 + qm) >= 4


# ------------------------------------------------------------------ committed inputs and readiness

from pathlib import Path  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "research/market_valuation_macro_overlay_v1/data"
EVIDENCE = REPO / "research/market_valuation_macro_overlay_v1/evidence"


def _stored_entries(node):
    if isinstance(node, dict):
        if {"path", "sha256", "bytes"} <= set(node):
            yield node
        for value in node.values():
            yield from _stored_entries(value)


def test_every_preserved_input_matches_its_manifest_hash():
    manifest = json.loads((DATA / "manifest.json").read_text())
    entries = list(_stored_entries(manifest))
    assert len(entries) == 11   # 6 raw files + 2 Shiller extracts + 2 ALFRED ledgers + 1 SSGA BIL extract
    for entry in entries:
        raw = (REPO / entry["path"]).read_bytes()
        assert len(raw) == entry["bytes"], entry["path"]
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"], entry["path"]
    assert manifest["secretsUsed"] == [] and manifest["outcomeReads"] == 0


def test_alfred_ledgers_cover_every_decision_with_a_vintage_before_it():
    for series in ("BAA", "GS10"):
        rows = list(csv.DictReader((DATA / f"alfred-{series}-asof-decisions.csv").open()))
        assert len(rows) == 212
        for row in rows:
            assert row["status"] == "VINTAGE_SERVED"
            assert row["servedVintage"] <= row["vintageRequested"] < row["decisionDate"]
            assert row["observationDate"] < row["decisionDate"]


def test_protocol_readiness_facts_equal_the_committed_readiness_report():
    spec = json.loads((REPO / "research/market_valuation_macro_overlay_v1/protocol.json").read_text())
    report = json.loads((EVIDENCE / "us-signal-readiness.json").read_text())
    facts = spec["preOutcomeReadiness"]["facts"]
    assert facts["stateTable2x2"] == report["stateTable2x2"]
    assert facts["meanTargets"] == {k: v["meanTarget"] for k, v in report["policies"].items()}
    assert report["window"]["count"] == spec["calendar"]["evaluationWindowUS"]["months"]
    cells = report["stateTable2x2"]
    assert cells["CHEAP_BAD"] < spec["preOutcomeReadiness"]["MIN_STATE_CELL_DECISIONS"]


def test_readiness_report_is_reproducible_from_committed_inputs():
    rebuilt = B.build(DATA)
    committed = json.loads((EVIDENCE / "us-signal-readiness.json").read_text())
    rebuilt.pop("rows")
    assert json.loads(json.dumps(rebuilt, sort_keys=True, default=str)) == committed
