"""Source-only checks for the independent guidance holdout and uncertainty."""

import gzip
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "research/next_alpha_source_admission_v1/tools/guidance_validation_protocol.py"
SPEC = importlib.util.spec_from_file_location("guidance_validation_protocol", TOOL)
VP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VP)


def document(cik, accession, year=2021, tickers=None):
    return {"cik": cik, "accession": str(accession), "filingDate": f"{year}-03-01",
            "acceptanceDateTime": f"{year}-03-01T12:34:56+00:00",
            "tickers": tickers if tickers is not None else [str(cik)]}


def test_roster_excludes_any_old_panel_company_and_aliases(monkeypatch):
    monkeypatch.setattr(VP, "MAX_GROUPS", 2)
    records = [document(1, 1, 2023, ["OLD"]), document(2, 2, tickers=["OLD"]), document(3, 3),
               document(4, 4), document(5, 5, tickers=["SEM"]), document(6, 6), document(7, 7),
               document(7, 8), document(7, 9), document(7, 10), document(7, 11)]
    gold = [{"cik": 3, "accession": "3"}]
    stratified = [{"cik": 4, "accession": "4"}]
    result = VP.select_roster(records, gold, stratified, {"SEM"})

    assert result == VP.select_roster(list(reversed(records)), gold, stratified, {"SEM"})
    assert result["counts"]["catalogCiks"] == 7
    assert result["counts"]["eligibleIssuerGroups"] == 2
    assert {row["cik"] for row in result["documents"]} == {6, 7}
    seven = [row["accession"] for row in result["documents"] if row["cik"] == 7]
    assert len(seven) == VP.DOCS_PER_GROUP


def test_csv_dedup_retains_tickers_but_refuses_conflicting_times():
    header = "ticker,cik,form,items,filingDate,acceptanceDateTime,accession\n"
    body = ("OLD,1,8-K,2.02,2021-03-01,2021-03-01T12:45:00Z,1\n"
            "NEW,1,8-K,2.02,2021-03-01,2021-03-01T12:45:00+00:00,1\n"
            "NEW,1,8-K/A,2.02,2021-03-01,2021-03-01T12:46:00Z,2\n")
    records = VP.catalog_records(gzip.compress((header + body).encode()))

    assert len(records) == 1
    assert records[0]["tickers"] == ["NEW", "OLD"]
    conflicting = body.replace("12:45:00+00:00", "12:46:00+00:00")
    with pytest.raises(ValueError, match="Conflicting filing metadata"):
        VP.catalog_records(gzip.compress((header + conflicting).encode()))


def test_issuer_bootstrap_reproducible_and_marks_undefined_points():
    result = VP.issuer_bootstrap({2: (0, 0, 2), 1: (8, 1, 2)}, draws=100)

    assert result == VP.issuer_bootstrap({1: (8, 1, 2), 2: (0, 0, 2)}, draws=100)
    assert result["issuerClusters"] == 2
    assert result["precision"]["point"] == 8 / 9
    assert result["recall"]["point"] == 8 / 12
    assert result["precision"]["definedDraws"] < 100
    assert VP.issuer_bootstrap({})["precision"]["point"] is None
    assert VP.issuer_bootstrap({1: (3, 0, 0)})["f1"]["interval95"] is None
