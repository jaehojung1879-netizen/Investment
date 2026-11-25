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
