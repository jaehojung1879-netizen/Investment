"""Frozen listed-share test applied to proposal T's six rows. No network, price or outcome."""
import json
from types import SimpleNamespace

from . import kr22_execution_reconciliation as X
from . import kr22_source_recovery as SR

REPORT = json.loads(X.REPORT.read_text())


def snaps(table):
    dates = sorted({d for t in table.values() for d in t})
    return SimpleNamespace(dates=dates, by_date={d: {k: {"listedShares": v[d]} for k, v in table.items() if d in v} for d in dates})


def row(ratio="0.5"):
    return {"oldSecurity": "OLD.KS", "successorSecurity": "NEW.KS", "effectiveDate": "2020-01-15",
            "reviewedRatio": {"commonShareRatio": ratio}}


def test_committed_report_splits_the_six_rows_three_and_three():
    s = REPORT["summary"]
    assert s["countReconciled"] == ["000830.KS", "037620.KS", "079440.KS"]
    assert s["documentedNotCountReconciled"] == ["002550.KS", "003450.KS", "003600.KS"]
    assert REPORT["pricesRead"] == 0 and REPORT["historicalOutcomesRead"] == 0


def test_all_new_shares_for_all_old_shares_reconciles_exactly():
    s = snaps({"OLD.KS": {"2020-01-02": 1000.0, "2020-02-03": 0.0}, "NEW.KS": {"2020-01-02": 5000.0, "2020-02-03": 5500.0}})
    r = X.reconcile(row(), s)
    assert r["status"] == SR.EXACT and r["impliedOldSharesExchanged"] == 1000.0


def test_acquirer_stake_or_treasury_delivery_is_documented_not_contradicted():
    stake = snaps({"OLD.KS": {"2020-01-02": 1000.0, "2020-02-03": 0.0}, "NEW.KS": {"2020-01-02": 5000.0, "2020-02-03": 5350.0}})
    r = X.reconcile(row(), stake)
    assert r["status"] == "DOCUMENTED_NOT_COUNT_RECONCILED" and abs(r["impliedVsOldListed"] + 0.3) < 1e-9
    treasury = snaps({"OLD.KS": {"2020-01-02": 1000.0, "2020-02-03": 0.0}, "NEW.KS": {"2020-01-02": 5000.0, "2020-02-03": 5000.0}})
    assert X.reconcile(row(), treasury)["basis"] == "NO_LISTED_SHARE_CHANGE_TREASURY_DELIVERY_STATED"
