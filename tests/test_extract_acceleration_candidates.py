"""Unit test for the candidate-list extraction that feeds prospective
fundamental-acceleration sealing from the live build's own output.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "extract_acceleration_candidates.py"
spec = importlib.util.spec_from_file_location("extract_acceleration_candidates", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_extract_candidates_reads_research_table_per_region():
    site_data = {
        "longTerm": {
            "regions": {
                "US": {"researchTable": [
                    {"ticker": "JPM", "region": "US", "sector": "Financials",
                     "factorPercentiles": {"momentum": 89, "quality": 78}},
                ]},
                "KR": {"researchTable": [
                    {"ticker": "005930.KS", "region": "KR", "sector": "Technology",
                     "factorPercentiles": {"momentum": 50, "quality": None}},
                ]},
            }
        }
    }
    candidates = module.extract_candidates(site_data)
    assert len(candidates) == 2
    by_ticker = {c["ticker"]: c for c in candidates}
    assert by_ticker["JPM"]["region"] == "US"
    assert by_ticker["JPM"]["sector"] == "Financials"
    assert by_ticker["JPM"]["factorPercentiles"]["quality"] == 78
    assert by_ticker["005930.KS"]["factorPercentiles"]["quality"] is None


def test_extract_candidates_skips_rows_without_ticker():
    site_data = {"longTerm": {"regions": {"US": {"researchTable": [{"sector": "Technology"}]}}}}
    assert module.extract_candidates(site_data) == []


def test_extract_candidates_handles_missing_longterm_block():
    assert module.extract_candidates({}) == []
