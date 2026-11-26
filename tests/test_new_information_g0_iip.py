"""Synthetic tests for the #360 original-release IIP coverage gate."""
from pathlib import Path

import pytest

from research.new_information_g0_v1.iip_feasibility import audit_iip, month_number


def make_csv(path: Path, rows: list[tuple[str, str, str]]) -> None:
    base = "refMonth,published,industry,productionYoy,shipmentYoy,inventoryYoy,layout,sha256,num\n"
    content = base + "".join(
        f"{m},{date},{industry},1,2,3,COMBINED,synthetic,0\n"
        for m, date, industry in rows
    )
    path.write_text(content, encoding="utf-8")


def test_sparse_yoy_cannot_create_level_ratio(tmp_path):
    f = tmp_path / "iip.csv"
    make_csv(f, [
        ("2013-03", "2013-04-30", "SEMI"),
        ("2021-09", "2021-10-29", "SEMI"),
        ("2021-10", "2021-11-30", "SEMI"),
        ("2021-10", "2021-11-30", "AUTO"),
    ])
    a = audit_iip(f)
    assert a["months_parsed"] == 3
    assert a["longest_consecutive_run_months"] == 2
    assert a["nonconsecutive_month_gaps"] == 1
    assert a["filled_yoy_months"]["inventoryYoy"] == 3
    assert a["valid_inventory_to_shipment_level_ratio"] is False
    assert a["any_return_or_price_data_read"] is False


def test_release_must_be_after_measured_month(tmp_path):
    f = tmp_path / "iip.csv"
    make_csv(f, [("2021-09", "2021-09-29", "SEMI")])
    with pytest.raises(ValueError, match="Publication"):
        audit_iip(f)


def test_duplicate_month_rejected(tmp_path):
    f = tmp_path / "iip.csv"
    make_csv(f, [("2021-09", "2021-10-29", "SEMI"),
                 ("2021-09", "2021-10-29", "SEMI")])
    with pytest.raises(ValueError, match="Repeated"):
        audit_iip(f)


def test_month_continuity():
    assert month_number("2025-01") - month_number("2024-12") == 1
