"""Synthetic document structures for the outcome-free SEC guidance extractor."""
import importlib
import sys
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1] / "research" / "next_alpha_source_admission_v1" / "tools"
sys.path.insert(0, str(TOOLS))
S = importlib.import_module("guidance_extract_structured")
V2 = importlib.import_module("guidance_extract_v2")


def structure(doc):
    return S.inspect(f"<html><body>{doc}</body></html>".encode())


def facts(result):
    fields = "target", "metric", "basis", "unit", "low", "high", "kind"
    return [tuple(row[field] for field in fields) for row in result["predictions"]]


def test_colspan_preserves_revision_ranges_and_excludes_year_ago_actual():
    result = structure("""
        <h2>Fiscal year 2026 guidance</h2><table>
        <tr><th rowspan="2">Metric</th><th colspan="2">FY2026 prior forecast</th>
          <th colspan="2">FY2026 current forecast</th><th rowspan="2">FY2025 actual</th></tr>
        <tr><th>Low</th><th>High</th><th>Low</th><th>High</th></tr>
        <tr><th>Revenue ($ in millions)</th><td>30</td><td>35</td><td>42</td><td>48</td><td>20</td></tr>
        </table>""")
    assert facts(result) == [
        ("FY2026", "revenue", "unstated", "USD_million", 30, 35, "PRIOR"),
        ("FY2026", "revenue", "unstated", "USD_million", 42, 48, "CURRENT"),
    ]
    assert [row["source"]["columns"] for row in result["predictions"]] == [[1, 2], [3, 4]]
    assert all(isinstance(row["block"], int) for row in result["predictions"])


def test_transposed_forward_reconciliation_recovers_totals_on_both_bases():
    doc = """
        <h2>Financial outlook</h2><table><caption>Q4 FY2026 projected reconciliation</caption>
        <tr><th rowspan="2">Period</th><th colspan="2">GAAP diluted EPS</th>
          <th colspan="2">Non-GAAP diluted EPS</th><th rowspan="2">Impact of restructuring on EPS</th></tr>
        <tr><th>Low</th><th>High</th><th>Low</th><th>High</th></tr>
        <tr><th>Current</th><td>$1.05</td><td>$1.20</td><td>$1.45</td><td>$1.55</td><td>$0.30</td></tr>
        <tr><th>Prior year</th><td>$0.85</td><td>$0.95</td><td>$1.10</td><td>$1.20</td><td>$0.25</td></tr>
        </table>"""
    assert V2.extract(doc.encode()) == []
    assert facts(structure(doc)) == [
        ("Q4FY2026", "eps", "GAAP", "USD_per_share", 1.05, 1.20, "CURRENT"),
        ("Q4FY2026", "eps", "non_GAAP", "USD_per_share", 1.45, 1.55, "CURRENT"),
    ]


def test_historical_transposed_reconciliation_does_not_inherit_prior_table_scope():
    result = structure("""
        <h2>FY2026 financial outlook</h2><table><caption>GAAP to non-GAAP reconciliation</caption>
        <tr><th>Period</th><th>GAAP EPS</th><th>Adjusted EPS</th></tr>
        <tr><th>Three months ended June 30, 2025</th><td>$1.10</td><td>$1.70</td></tr>
        <tr><th>FY2025</th><td>$4.30</td><td>$5.20</td></tr>
        </table>""")
    assert facts(result) == []
    assert result["needs_review"] == []


def test_spacer_and_empty_value_do_not_slide_reported_value_under_guidance_header():
    result = structure("""
        <table><caption>2026 financial outlook</caption>
        <tr><th>Metric</th><th>Current</th><th>Prior year actual</th></tr>
        <tr><th>Revenue ($ in millions)</th><td></td><td>181.4</td></tr>
        <tr><td colspan="3">&nbsp;</td></tr>
        <tr><th>Capital expenditures ($ in millions)</th><td>45.1</td><td>35.4</td></tr>
        </table>""")
    assert facts(result) == [("FY2026", "capex", "unstated", "USD_million", 45.1, 45.1, "CURRENT")]


def test_units_follow_table_axes_instead_of_number_size_or_cross_table_context():
    result = structure("""
        <h2>FY2026 outlook</h2><table>
        <tr><th>Metric</th><th>Current</th></tr>
        <tr><th>Revenue (in billions)</th><td>approximately 2.1</td></tr>
        <tr><th>Capital expenditures (in thousands)</th><td>4,500 – 5,000</td></tr>
        <tr><th>Gross margin</th><td>42% – 46%</td></tr>
        <tr><th>Non-GAAP EPS (per share)</th><td>$2.2 ± $0.20</td></tr>
        <tr><th>Operating income</th><td>$1.2+ billion</td></tr>
        <tr><th>Net income (EUR millions)</th><td>93</td></tr>
        </table>""")
    assert facts(result) == [
        ("FY2026", "revenue", "unstated", "USD_million", 2100.0, 2100.0, "CURRENT"),
        ("FY2026", "capex", "unstated", "USD_million", 4.5, 5.0, "CURRENT"),
        ("FY2026", "gross_margin", "unstated", "pct", 42.0, 46.0, "CURRENT"),
        ("FY2026", "eps", "non_GAAP", "USD_per_share", 2.0, 2.4, "CURRENT"),
        ("FY2026", "operating_income", "unstated", "USD_million", 1200.0, None, "CURRENT"),
    ]
    assert [row["reason"] for row in result["needs_review"]] == ["UNRESOLVED_NUMERIC_UNIT"]


def test_quarter_leaf_and_calendar_year_remain_distinct_from_fiscal_year():
    result = structure("""
        <table><caption>Financial guidance</caption>
        <tr><th rowspan="2">Metric</th><th colspan="2">FY2026</th><th rowspan="2">CY2026</th></tr>
        <tr><th>Q2</th><th>Full year</th></tr>
        <tr><th>Revenue ($ in millions)</th><td>20</td><td>85</td><td>96</td></tr>
        </table>""")
    assert [row[0] for row in facts(result)] == ["Q2FY2026", "FY2026", "CY2026"]


def test_actual_reported_and_undated_periods_fail_closed():
    result = structure("""
        <h1>Fourth Quarter 2025 Financial Results</h1><table><caption>Financial outlook</caption>
        <tr><th>Metric</th><th>2025</th><th>Prior outlook</th><th>First quarter</th></tr>
        <tr><th>Revenue ($ in millions)</th><td>10</td><td>9</td><td>13</td></tr>
        </table>""")
    assert facts(result) == [("Q1FY2026", "revenue", "unstated", "USD_million", 13, 13, "CURRENT")]
    assert [row["reason"] for row in result["needs_review"]] == ["REPORTED_PERIOD", "MISSING_EXPLICIT_TARGET"]


def test_unpaired_endpoint_and_conflicting_same_target_are_reviewable():
    result = structure("""
        <h2>FY2026 guidance</h2><table>
        <tr><th rowspan="2">Metric</th><th colspan="2">Guidance range</th></tr>
        <tr><th>Lower end</th><th>Upper end</th></tr>
        <tr><th>Revenue ($ in millions)</th><td>31</td><td></td></tr>
        </table><table>
        <tr><th>Metric</th><th>FY2026 current guidance</th></tr>
        <tr><th>Adjusted EPS</th><td>$1.45</td></tr>
        <tr><th>Adjusted EPS</th><td>$1.80</td></tr>
        </table>""")
    assert facts(result) == []
    assert [entry["reason"] for entry in result["needs_review"]] == [
        "MISSING_OR_CONFLICTING_RANGE_BOUND", "CONFLICTING_VALUES_FOR_TARGET", "CONFLICTING_VALUES_FOR_TARGET",
    ]


def test_amounts_with_split_symbols_and_nested_layout_tables_find_their_dom_origin():
    result = structure("""
        <h2>FY2026 guidance</h2><table><tr><td><table>
        <tr><th>Metric</th><th colspan="2">Current</th></tr>
        <tr><th>Capital expenditures (in millions)</th><td>$</td><td>90</td></tr>
        </table></td></tr></table>""")
    assert facts(result) == [("FY2026", "capex", "unstated", "USD_million", 90, 90, "CURRENT")]
    assert result["predictions"][0]["source"] == {"table": 1, "row": 1, "columns": [2]}


def test_forward_reconciliation_keeps_secondary_point_as_provenance_for_outlook_range():
    result = structure("""
        <table><caption>FY2026 financial outlook</caption>
        <tr><th>Metric</th><th>Current</th></tr>
        <tr><th>Adjusted EPS</th><td>$2.10 – $2.40</td></tr>
        </table><table>
        <tr><th colspan="3">FY2026 projected GAAP to non-GAAP reconciliation</th></tr>
        <tr><th scope="col">Period</th><th>GAAP EPS</th><th>Adjusted EPS</th></tr>
        <tr><th>Current</th><td>$2.02</td><td>$2.21</td></tr>
        </table>""")
    assert facts(result) == [
        ("FY2026", "eps", "non_GAAP", "USD_per_share", 2.10, 2.40, "CURRENT"),
        ("FY2026", "eps", "GAAP", "USD_per_share", 2.02, 2.02, "CURRENT"),
    ]
    assert result["predictions"][0]["reconciliation_sources"] == [{"table": 1, "row": 2, "columns": [2]}]


def test_unresolved_header_date_or_half_year_never_becomes_full_year():
    result = structure("""
        <table><caption>FY2026 financial outlook</caption>
        <tr><th>Metric</th><th>Six months ending June 30, 2026</th><th>H2 2026 guidance</th></tr>
        <tr><th>Revenue ($ in millions)</th><td>123</td><td>179</td></tr>
        </table>""")
    assert facts(result) == []
    assert {entry["reason"] for entry in result["needs_review"]} == {"UNRESOLVED_NON_ANNUAL_INTERVAL"}


def test_value_and_metric_units_override_column_units_and_ignore_hidden_text():
    result = structure("""
        <table><caption>FY2026 financial outlook</caption>
        <tr><th>Metric</th><th>Current outlook ($ in millions)</th></tr>
        <tr><th>Revenue (in billions)</th><td>2.10 <span hidden><span>old</span> 1.90</span></td></tr>
        <tr><th>Capital expenditures</th><td>1.50 to 1.70 billion</td></tr>
        </table>""")
    assert facts(result) == [
        ("FY2026", "revenue", "unstated", "USD_million", 2100, 2100, "CURRENT"),
        ("FY2026", "capex", "unstated", "USD_million", 1500, 1700, "CURRENT"),
    ]
