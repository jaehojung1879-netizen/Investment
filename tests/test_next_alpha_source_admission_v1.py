"""Detector and linker rules of next_alpha_source_admission_v1 (no network, no prices)."""
import importlib
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "research" / "next_alpha_source_admission_v1" / "tools"
sys.path.insert(0, str(TOOLS))
G = importlib.import_module("guidance_detect")


def _html(body):
    return f"<html><body>{body}</body></html>".encode()


def test_bullet_list_guidance_is_found_by_heading_window():
    raw = _html("<p>2025 GUIDANCE</p><p>We are reaffirming the following guidance ranges for full year 2025:</p>"
                "<p>Diluted earnings per common share of $0.30 – $0.36</p>")
    out = G.detect(raw)
    assert out["metricGuidance"] and "eps" in out["metrics"] and "REAFFIRM" in out["verbs"]


def test_forward_looking_boilerplate_is_not_guidance():
    raw = _html("<p>Forward-looking statements are identified by words such as expect, outlook and guidance "
                "for fiscal 2024.</p>")
    assert not G.detect(raw)["metricGuidance"]


def test_raise_requires_a_guidance_object():
    assert "RAISE" not in G.detect(_html("<p>The company raised its quarterly dividend 5%.</p>"))["verbs"]
    assert "RAISE" in G.detect(_html("<p>The company raises its full-year outlook.</p>"))["verbs"]


def test_quarter_ranges_are_never_labelled_full_year_targets(monkeypatch):
    L = importlib.import_module("guidance_link")
    q = _html("<p>For the first quarter of fiscal 2017, the company expects net sales of $3.20 billion to $3.34 billion.</p>")
    fy = _html("<p>The Company expects full-year 2023 non-GAAP EPS in the range of $12.55 to $12.75.</p>")
    assert L.tuples(q) == []
    (t,) = L.tuples(fy)
    assert (t["target"], t["metric"], t["basis"], t["low"], t["high"]) == ("FY2023", "eps", "non_GAAP", "12.55", "12.75")


def _x(body):
    E = importlib.import_module("guidance_extract_v2")
    return [(t["target"], t["metric"], t["basis"], t["unit"], t["low"], t["high"], t["kind"]) for t in E.extract(_html(body))]


def test_v2_table_columns_assign_gaap_and_non_gaap():
    out = _x("<p>Financial Guidance</p><table><tr><td>GAAP</td><td>Non-GAAP</td></tr>"
             "<tr><td>2023 Operating Expenses</td><td>$3.675 - $3.725 billion</td><td>$3.04 - $3.09 billion</td></tr>"
             "<tr><td>2023 Capital Expenditures</td><td>$450 - $500 million</td></tr></table>")
    assert ("FY2023", "opex", "GAAP", "USD_million", 3675.0, 3725.0, "CURRENT") in out
    assert ("FY2023", "opex", "non_GAAP", "USD_million", 3040.0, 3090.0, "CURRENT") in out
    assert ("FY2023", "capex", "unstated", "USD_million", 450.0, 500.0, "CURRENT") in out


def test_v2_from_to_revision_separates_prior_and_current():
    out = _x("<p>Outlook for 2023</p><p>DTE Energy is revising 2023 operating EPS guidance from $6.09 - $6.40 to $5.65 - $5.85.</p>")
    assert ("FY2023", "eps", "non_GAAP", "USD_per_share", 6.09, 6.40, "PRIOR") in out
    assert ("FY2023", "eps", "non_GAAP", "USD_per_share", 5.65, 5.85, "CURRENT") in out


def test_v2_results_table_rows_are_not_guidance():
    out = _x("<p>2018 Financial Outlook</p><table><tr><td>September 30,</td><td>Reported</td></tr>"
             "<tr><td>2018</td><td>2017</td></tr><tr><td>Revenues</td><td>$922</td><td>$828</td></tr></table>")
    assert out == []


def test_dart_detail_filter_fix_drops_publication_type():
    sys.path.insert(0, str(TOOLS))
    P = importlib.import_module("run_probe_cached")
    assert P.fix_detail_filter({"pblntf_ty": "D", "pblntf_detail_ty": "D001", "bgn_de": "20240501"}) == {"pblntf_detail_ty": "D001", "bgn_de": "20240501"}
    assert P.fix_detail_filter({"pblntf_ty": "D"}) == {"pblntf_ty": "D"}
