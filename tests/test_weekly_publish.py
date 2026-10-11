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
        "indices": [{"symbol": "^KS11", "asOf": "2026-10-08"}, {"symbol": "^GSPC", "asOf": "2026-10-09"}],
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
        assert blob["status"] == "DATA_BLOCKED" and not blob["holdings"] and not blob["weights"]
        assert not blob["watchlist"]
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
    assert "publication-status.json" in step.split("else", 1)[1]  # a refusal is published too
    assert text.index("Validate production artifact") < text.index("Weekly decision and append-only receipts")
    assert text.index("Weekly decision and append-only receipts") < text.index("Commit & push to signal-history")
    # No new workflow file: the census and pages.yml are byte-pinned by sealed studies.
    assert not (root / ".github/workflows/weekly-decision.yml").exists()


def test_session_evidence_is_the_index_tape_not_the_newest_stock():
    # One current US quote used to make the region look current.
    site = _site(indices=[{"symbol": "^KS11", "asOf": "2026-10-08"}, {"symbol": "^GSPC", "asOf": "2026-10-08"}])
    block = P.build_from_site(site, "sha", [])
    assert P.observed_sessions(site) == {"KR": "2026-10-08", "US": "2026-10-08"}
    assert block["regions"]["US"]["status"] == "STALE_DATA"
    assert block["regions"]["KR"]["status"] == "STOCKS_SELECTED"
    assert P.validate(block) == []


def test_validator_refuses_a_sized_or_unlabelled_watchlist():
    site = _site()
    site["longTerm"]["regions"]["KR"]["researchTable"] = [_candidate("A")]
    block = P.build_from_site(site, "sha", [])
    assert block["regions"]["KR"]["watchlist"] and P.validate(block) == []
    block["regions"]["KR"]["watchlist"][0]["weightPct"] = 15
    assert any(e.startswith("watchlist_sizing_or_forecast:KR") for e in P.validate(block))
    block = P.build_from_site(site, "sha", [])
    block["regions"]["KR"]["watchlistLabelKo"] = "추천"
    assert "watchlist_without_label:KR" in P.validate(block)


def test_refusal_is_published_as_a_status_and_leaves_the_decision_untouched(tmp_path, monkeypatch):
    site = tmp_path / "site.json"
    site.write_text(json.dumps(_site()))
    out, receipts, status = tmp_path / "w.json", tmp_path / "r.jsonl", tmp_path / "status.json"
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    assert P.main([str(site), str(receipts), str(out), str(receipts), str(status)]) == 0
    ok = json.loads(status.read_text())
    assert ok["status"] == "PUBLISHED" and ok["runId"] == "42" and ok["errors"] == []
    published = out.read_bytes()
    monkeypatch.setattr(P, "validate", lambda block: ["weights_not_100pct:KR"])
    out2 = tmp_path / "w2.json"
    assert P.main([str(site), str(receipts), str(out2), str(receipts), str(status)]) == 1
    refused = json.loads(status.read_text())
    assert refused["status"] == "REFUSED" and refused["errors"] == ["weights_not_100pct:KR"]
    assert not out2.exists() and out.read_bytes() == published


def test_benchmark_audit_reproduces_the_double_count_from_committed_phase_c_files():
    from pipeline import weekly_history as H
    audit = H.benchmark_audit()
    assert audit["available"] and audit["verifiableEvents"] == 20 and audit["doubledEvents"] == 19
    assert audit["singleOrOtherEvents"] == ["2022-07-28"]
    for event in audit["events"]:
        if event["exDate"] != "2022-07-28":
            assert 1.8 <= event["replayOverRawMultiple"] <= 2.2
            assert 0.85 <= event["vendorOverRawMultiple"] <= 1.15  # the vendor quote already carries one
    gaps = [r["gapPp"] for r in audit["annualGap"]["rows"]]
    assert len(gaps) == 14 and min(gaps) > 1.0 and max(gaps) < 4.6
    assert audit["stockLegs"]["conclusion"] == "NOT_DETECTED_ON_ORDINARY_CASH_EVENTS_IN_THIS_SAMPLE"


def test_corrected_benchmark_accounting_is_pinned_and_changes_no_decision():
    from pathlib import Path
    import hashlib
    root = Path(__file__).resolve().parent.parent
    protocol = json.loads((root / "docs/weekly-decision/weekly-passive-first-v1-benchmark-basis-protocol.json").read_text())
    series = protocol["correctedSeries"]
    assert hashlib.sha256((root / series["file"]).read_bytes()).hexdigest() == series["sha256"]
    from scripts import run_weekly_passive_first_replay as R
    corrected = R.corrected_benchmark_series()
    assert corrected.index.is_monotonic_increasing and (corrected > 0).all()
    assert str(corrected.index[-1].date()) == "2026-09-14"
    assert protocol["promotionEligible"] is False and protocol["liveValidated"] is False
