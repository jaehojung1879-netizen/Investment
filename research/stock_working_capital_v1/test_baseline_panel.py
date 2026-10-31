"""Invented filings only; no prices, returns, fit or historical study."""
from copy import deepcopy

import pytest

from . import baseline_panel as B
from . import features as F
from .test_study import filing


def test_sales_denominator_growth_is_not_a_collection_improvement():
    out = B.pair_controls(filing(2024, sales=200), filing(2023), "2025-03-21")
    for signal in F.SIGNALS:
        v = out["controls"][signal]["values"]
        assert v["salesGrowth"] == 1
        assert v["numeratorTermAtPriorSales"] == 0
        assert v["denominatorTermAtCurrentBalance"] == v["rawIntensityChange"] > 0


@pytest.mark.parametrize("old,now,sales", [(30, 15, 100), (30, 45, 200), (30, 0, 100), (0, 10, 75)])
def test_components_reconcile_and_never_read_comparative_columns(old, now, sales):
    out = B.pair_controls(filing(2024, inventory=now, sales=sales), filing(2023, inventory=old), "2025-03-21")
    v = out["controls"]["inventory_discipline"]["values"]
    assert v["numeratorTermAtPriorSales"] + v["denominatorTermAtCurrentBalance"] == pytest.approx(v["rawIntensityChange"])
    assert v["currentFocalIntensity"] == pytest.approx(now / sales)


@pytest.mark.parametrize("fault", ["same_day", "basis", "taxonomy", "unit", "missing", "duplicate"])
def test_inherited_pit_and_context_rejections_remain_rejections(fault):
    now, old, stamp = filing(2024), filing(2023), "2025-03-21"
    if fault == "same_day": stamp = "2025-03-20"
    if fault == "basis": old["fsDiv"] = "OFS"
    if fault == "taxonomy": old["rows"][1]["account_id"] = "ifrs_Inventories"
    if fault == "unit": now["rows"][1]["currency"] = "USD"
    if fault == "missing": now["rows"][1]["thstrm_amount"] = ""
    if fault == "duplicate": now["rows"].append(deepcopy(now["rows"][1]))
    out = B.pair_controls(now, old, stamp)["controls"]["inventory_discipline"]
    assert out["values"] is None and out["reasons"]


def inputs():
    c = {"signal": "2025-03-21", "members": [{"ticker": "123456.KS"}, {"ticker": "999999.KS"}]}
    c["intendedSha256"] = F.digest(c)
    rows = [{"signal": c["signal"], "ticker": m["ticker"], "intendedSha256": c["intendedSha256"],
             "filingReceipts": [filing(2023)["receiptNos"], filing(2024)["receiptNos"]]
             if m["ticker"] == "123456.KS" else [None, None]} for m in c["members"]]
    return [c], rows, [filing(2023), filing(2024, sales=200), filing(2025)]


def test_full_intended_panel_keeps_missing_name_and_ignores_future_annual():
    report, panel = B.build_controls(*inputs())
    assert report["memberDates"] == len(panel) == 2
    assert report["sourceAdmitted"] is False and report["historicalOutcomesRead"] == report["modelFits"] == 0
    for signal in F.SIGNALS:
        assert report["signals"][signal]["rawControlPairsReadable"] == 1
        assert report["signals"][signal]["positiveIntensityChangesWithNoNumeratorImprovement"] == 1
        assert panel[1]["controls"][signal]["values"] is None
    assert B.build_controls(*inputs()) == (report, panel)


@pytest.mark.parametrize("fault", ["duplicate", "remove", "pair", "digest", "extra"])
def test_cohort_and_selected_filing_pair_are_not_silently_changed(fault):
    cohorts, rows, filings = inputs()
    if fault == "duplicate": rows.append(deepcopy(rows[0]))
    if fault == "remove": rows.pop()
    if fault == "pair": rows[0]["filingReceipts"][0] = ["20240320000009"]
    if fault == "digest": cohorts[0]["intendedSha256"] = "0" * 64
    if fault == "extra": rows[0]["ticker"] = "111111.KS"
    with pytest.raises(ValueError): B.build_controls(cohorts, rows, filings)
