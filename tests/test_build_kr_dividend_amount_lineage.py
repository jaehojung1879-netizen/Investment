"""`scripts/build_kr_dividend_amount_lineage.py`'s pure logic on synthetic
fixtures. The real end-to-end run (against a real `signal-history`
checkout) is documented, not unit-tested here -- see
`docs/kr-terminal-action-reconstruction-v2.md`.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "build_kr_dividend_amount_lineage", ROOT / "scripts/build_kr_dividend_amount_lineage.py")
BUILD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BUILD)


def test_dart_rows_for_reconciliation_keeps_only_common_cash_dps():
    entries = [
        {"metric": "CASH_DPS", "shareClass": "COMMON", "value": 500.0,
         "sourceReceiptDate": "2020-03-01", "fiscalYear": 2019,
         "sourceReceiptNumber": "r1"},
        {"metric": "CASH_DPS", "shareClass": "PREFERRED", "value": 550.0,
         "sourceReceiptDate": "2020-03-01", "fiscalYear": 2019,
         "sourceReceiptNumber": "r1"},
        {"metric": "STOCK_DPS", "shareClass": "COMMON", "value": 0.1,
         "sourceReceiptDate": "2020-03-01", "fiscalYear": 2019,
         "sourceReceiptNumber": "r1"},
    ]
    rows = BUILD.dart_rows_for_reconciliation(entries, "005930.KS")
    assert len(rows) == 1
    assert rows[0]["amountPerShare"] == 500.0
    assert rows[0]["isStockDividend"] is False


def test_load_dividend_section_rows_returns_empty_without_a_shard(tmp_path):
    rows = BUILD.load_dividend_section_rows(tmp_path)
    assert rows == []
