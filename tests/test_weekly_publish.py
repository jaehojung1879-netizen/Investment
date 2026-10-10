"""The weekly artifact is derived only from a production site-data.json."""
import json

import pytest

from pipeline import weekly_decision as W
from pipeline import weekly_publish as P
from test_weekly_decision import _calibration, _candidate


def _site(**overrides):
    cal = _calibration("KR")
    cal["regions"]["US"] = _calibration("US", usable=False, established=False)["regions"]["US"]
    site = {
        "generatedAt": "2026-10-10T02:00:00+00:00",
        "provenance": {"buildCommitSha": "abc", "modelVersion": "m", "dataMode": "live"},
        "names": {"A": "에이"},
        "details": {"A": {"region": "KR", "asOf": "2026-10-08"},
                    "X": {"region": "US", "asOf": "2026-10-09"}},
        "longTerm": {"regions": {"KR": {"picks": [_candidate("A")]},
                                 "US": {"picks": [_candidate("X", region="US")]}}},
        "historicalValidation": {"alphaCalibration": cal, "ledgerCommitSha": "led"},
    }
    site.update(overrides)
    return site


def test_builds_independent_regions_from_site_data():
    block = P.build_from_site(_site(), "sha", [])
    kr, us = block["regions"]["KR"], block["regions"]["US"]
    assert kr["asOfDate"] == "2026-10-08" and us["asOfDate"] == "2026-10-09"
    assert kr["stockCount"] == 1 and kr["holdings"][0]["name"] == "에이"
    assert us["stockCount"] == 0 and us["weights"] == {"SPY": 1.0}
    assert kr["weekStatus"] == "FINAL_WEEKLY"  # KRX closed on Friday 2026-10-09
    assert kr["inputs"]["siteDataSha256"] == "sha"
    assert P.validate(block) == []


@pytest.mark.parametrize("flag", [{"recommendationsBlocked": True}, {"seed": True}, {"stale": True},
                                  {"provenance": {"dataMode": "synthetic"}}])
def test_unsafe_artifacts_publish_no_decision(flag):
    block = P.build_from_site(_site(**flag), "sha", [])
    assert block["blocked"] is True and block["unsafeReason"]
    for blob in block["regions"].values():
        assert blob["status"] == "BLOCKED" and not blob["holdings"] and not blob["weights"]
    assert P.validate(block) == []


def test_validator_refuses_invalid_publications():
    block = P.build_from_site(_site(), "sha", [])
    kr = block["regions"]["KR"]
    kr["weights"] = {"A": 0.15, "069500.KS": 0.80}
    assert "weights_not_100pct:KR" in P.validate(block)
    block = P.build_from_site(_site(), "sha", [])
    block["regions"]["KR"]["holdings"][0]["expectedNetAdvantagePct"] = -0.2
    assert any(e.startswith("unsupported_holding:KR") for e in P.validate(block))
    block = P.build_from_site(_site(), "sha", [])
    block["liveValidated"] = True
    assert "claims_validation" in P.validate(block)
    block = P.build_from_site(_site(), "sha", [])
    block["regions"]["US"]["weights"] = {"SPY": 0.5}
    assert "weights_not_100pct:US" in P.validate(block)


def test_main_appends_only_final_receipts_and_never_rewrites(tmp_path):
    site = tmp_path / "site.json"
    site.write_text(json.dumps(_site()))
    out, receipts = tmp_path / "weekly.json", tmp_path / "r.jsonl"
    assert P.main([str(site), str(receipts), str(out), str(receipts)]) == 0
    first = [json.loads(line) for line in receipts.read_text().splitlines()]
    assert {r["region"] for r in first} == {"KR", "US"}
    # A later build for the same week with a different site artifact is refused.
    changed = _site(generatedAt="2026-10-10T03:00:00+00:00")
    site.write_text(json.dumps(changed))
    assert P.main([str(site), str(receipts), str(out), str(receipts)]) == 0
    second = [json.loads(line) for line in receipts.read_text().splitlines()]
    assert [r["digest"] for r in second] == [r["digest"] for r in first]
    # ...and the page shows the recorded week, not the refused recomputation.
    shown = json.loads(out.read_text())["regions"]["KR"]
    assert shown["publishedFrom"] == "RECORDED_RECEIPT"
    assert shown["digest"] == next(r["digest"] for r in first if r["region"] == "KR")
    assert P.validate(json.loads(out.read_text())) == []


def test_same_site_data_gives_identical_receipts():
    a = P.build_from_site(_site(), "sha", [])
    b = P.build_from_site(_site(), "sha", [])
    assert all(a["regions"][r]["digest"] == b["regions"][r]["digest"] for r in ("KR", "US"))


def test_history_is_attached_without_new_outcomes():
    block = P.build_from_site(_site(), "sha", [])
    history = block["history"]
    assert history["existingStudies"]["phaseC"]["nominations"] == 0
    gap = history["benchmarkDefinitionGap"]
    assert gap["available"] and gap["minGapPp"] > 0
    assert W.POLICY_VERSION == block["policyVersion"]


def test_ledger_workflow_publishes_without_touching_pinned_files():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    text = (root / ".github/workflows/ledger.yml").read_text()
    step = text.split("- name: Weekly decision and append-only receipts", 1)[1].split("- name:", 1)[0]
    assert "python -m pipeline.weekly_publish data/site-data.json" in step
    assert "continue-on-error: true" in step  # a refusal never costs the paper ledger its day
    assert "ledger/weekly-decisions/receipts.jsonl" in step
    assert text.index("Validate production artifact") < text.index("Weekly decision and append-only receipts")
    assert text.index("Weekly decision and append-only receipts") < text.index("Commit & push to signal-history")
    # No new workflow file: the census and pages.yml are byte-pinned by sealed studies.
    assert not (root / ".github/workflows/weekly-decision.yml").exists()
