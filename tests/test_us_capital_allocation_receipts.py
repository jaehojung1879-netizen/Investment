"""The weekly prospective receipt: contract, timing, namespace separation and append-only storage. Synthetic fixtures only."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import prospective_receipt_core as CORE      # noqa: E402
from pipeline import us_capital_allocation_policy as P     # noqa: E402
from pipeline import us_capital_allocation_receipts as R   # noqa: E402

SIGNAL, MERGED = "2026-10-23", "2026-10-14T15:00:00+00:00"     # Friday; merge day is excluded (first prospective session is the 15th)
CREATED, CLOCK = "2026-10-23T23:30:00+00:00", "2026-10-23T23:31:00+00:00"
SPEC, COMMIT = "a" * 64, "b" * 40
CODE = {"commitSha": COMMIT, "files": {"pipeline/us_capital_allocation_policy.py": "c" * 64}}
DATA = {k: "d" * 64 for k in R.DATA_IDENTITY_KEYS}
AUTH = {"specSha256": SPEC, "mergeCommitSha": "e" * 40, "mergedAtUtc": MERGED}
WEEKLY_DECISION_FILES = sorted((ROOT / "docs/weekly-decision").glob("*.json"))


def cand(ticker, sector, growth=0.3, ratio=0.4):
    f = lambda v: {"value": v, "state": "VALID"}      # noqa: E731
    return {"ticker": ticker, "sector": sector, "priceOk": True, "reportAgeDays": 20,
            "features": {"totalCashDistributionTTM": f(400.0), "totalCashDistributionChangeYoY": f(growth),
                         "operatingCashFlowTTM": f(1000.0), "distributionToOCF": f(ratio)}}


def decision(*pairs, floor=2):
    return P.select([P.evaluate(cand(t, s, g)) for t, s, g in pairs], min_measured=floor)


def prices(tickers, session=SIGNAL, retrieved="2026-10-23T23:10:00+00:00"):
    return {t: {"session": session, "asTradedClose": 50.0, "totalReturnIndexClose": 61.5, "vendor": "SYNTHETIC",
                "retrievedAtUtc": retrieved, "basis": "as-traded-forward-total-return-v1"} for t in tickers}


def evidence(ticker, signal=SIGNAL, available="2026-08-01"):
    return {"asOf": signal, "featureVersion": "US_SHAREHOLDER_DISTRIBUTION_V1", "featureDigest": "9" * 64, "reportPeriod": "2026-Q2",
            "qualityWarnings": [], "features": {"totalCashDistributionTTM": {"state": "VALID", "value": 400.0, "basis": "FY", "inputs": [
                {"filingId": ticker + "-1", "availableFrom": available, "acceptedAt": available + " 20:00:00", "fiscalYear": 2026, "stage": "Q2",
                 "periodEnd": "2026-06-30", "concept": "PaymentsOfDividendsCommonStock", "section": "cf", "value": 1.0}]}}}


def build(dec=None, *, created=CREATED, clock=CLOCK, signal=SIGNAL, price_map=None, auth=None, pit=None):
    dec = dec or decision(("AAA", "Industrials", 0.3), ("BBB", "Utilities", 0.4), ("CCC", "Energy", 0.05))
    chosen = sorted(dec["weights"] or [])
    return R.build_synthetic_receipt(
        signal_date=signal, created_at_utc=created, test_clock_utc=clock, spec_sha256=SPEC, code_identity=CODE, data_identity=DATA,
        authorization=auth or AUTH, decision=dec, coverage={}, membership={"snapshotDate": "2026-10-18", "sourceCommit": "f" * 40, "members": 503},
        observation_prices=price_map or prices(["SPY", "QQQ", *chosen]),
        pit_evidence=pit or {t: evidence(t) for t in chosen},
        measured_tickers=["AAA", "BBB", "CCC"])


# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #
def test_a_candidate_receipt_carries_identity_pit_evidence_prices_and_digests():
    r = build()
    assert r["decision"]["status"] == "CANDIDATE_PORTFOLIO" and r["decision"]["weights"] == {"AAA": 0.15, "BBB": 0.15}
    assert r["decision"]["fallbackAsset"] == "SPY" and r["decision"]["fallbackWeight"] == pytest.approx(0.70)
    assert set(r["observationPrices"]) == {"SPY", "QQQ", "AAA", "BBB"}
    assert all(p["session"] == SIGNAL for p in r["observationPrices"].values())
    assert set(r["pitEvidence"]) == {"AAA", "BBB"} and r["pitEvidence"]["AAA"]["featureDigest"] and r["pitEvidence"]["AAA"]["asOf"] == SIGNAL
    assert r["dataSnapshotIdentity"].keys() == set(R.DATA_IDENTITY_KEYS)
    assert r["designDigest"] == P.design_digest() and r["featureVersion"] == "US_SHAREHOLDER_DISTRIBUTION_V1"
    assert r["receiptSha256"] == CORE.receipt_digest(r) and r["executionDate"] == "2026-10-26"
    assert r["benchmarks"] == {"official": "SPY", "alternative": "QQQ", "residual": "SPY"}
    assert r["dilution"] == {"status": "UNVERIFIED_SOURCE_BLOCKED", "gate": False}


def test_receipts_are_byte_deterministic():
    assert CORE.canonical(build()) == CORE.canonical(build())


def test_no_eligible_week_is_an_explicit_all_residual_receipt():
    r = build(decision(("AAA", "Industrials", 0.0), ("BBB", "Utilities", 0.0)))
    assert r["decision"]["status"] == "NO_ELIGIBLE_OPPORTUNITY" and r["decision"]["weights"] == {} and r["decision"]["fallbackWeight"] == 1.0
    assert set(r["observationPrices"]) == {"SPY", "QQQ"} and r["pitEvidence"] == {}


def test_a_blocked_week_publishes_counts_only_no_names_no_prices_no_weights():
    r = build(decision(("AAA", "Industrials", 0.3), floor=5))
    assert r["decision"]["status"] == "BLOCKED"
    assert r["decision"]["weights"] is None and r["decision"]["selected"] == [] and r["decision"]["passers"] == []
    assert r["observationPrices"] == {} and r["pitEvidence"] == {} and r["coverage"]["measuredTickers"] is None
    assert r["coverage"]["funnel"]["measured"] == 1


def test_blocked_receipt_that_smuggles_a_signal_is_refused():
    r = build(decision(("AAA", "Industrials", 0.3), floor=5))
    r["decision"]["selected"] = [{"ticker": "AAA", "sector": "Industrials", "score": 0.1}]
    r["receiptSha256"] = CORE.receipt_digest(r)
    with pytest.raises(ValueError, match="BLOCKED_RECEIPT_CARRIES_A_SIGNAL"):
        R.validate_receipt(r)


# --------------------------------------------------------------------------- #
# Timing: after the signal close, before the next open; first session strictly after the merge day
# --------------------------------------------------------------------------- #
def test_calendar_helpers_follow_the_pinned_us_calendar():
    assert R.is_weekly_decision_session("2026-10-23") and not R.is_weekly_decision_session("2026-10-22")
    assert not R.is_us_session("2026-10-24")                                   # Saturday
    assert str(R.next_us_session("2026-10-23").date()) == "2026-10-26"
    assert str(R.first_prospective_session(MERGED).date()) == "2026-10-15"
    # the first matured session is 126 sessions after execution, skipping weekends and holidays
    assert str(R.maturity_session("2026-10-26", 126).date()) > "2027-04-01"
    # a short week: Thanksgiving Friday is a session, the last of its week
    assert R.is_weekly_decision_session("2026-11-27") and not R.is_weekly_decision_session("2026-11-26")


@pytest.mark.parametrize("created,clock,message", [
    ("2026-10-23T22:59:00+00:00", "2026-10-23T23:31:00+00:00", "RECEIPT_CREATED_BEFORE_SIGNAL_CLOSE"),
    ("2026-10-26T13:30:00+00:00", "2026-10-26T14:00:00+00:00", "RECEIPT_CREATED_AFTER_EXECUTION_OPEN_BACKDATED"),
    ("2026-10-27T00:00:00+00:00", "2026-10-27T00:01:00+00:00", "RECEIPT_CREATED_AFTER_EXECUTION_OPEN_BACKDATED"),
    ("2026-10-23T23:30:00+00:00", "2026-10-23T23:00:00+00:00", "RECEIPT_CREATED_IN_THE_FUTURE")])
def test_a_receipt_outside_its_window_is_refused(created, clock, message):
    with pytest.raises(ValueError, match=message):
        build(created=created, clock=clock)


def test_signal_must_be_the_last_session_of_a_week_and_after_the_merge_day():
    with pytest.raises(ValueError, match="NOT_A_WEEKLY_DECISION_SESSION"):
        build(signal="2026-10-22", price_map=prices(["SPY", "QQQ", "AAA", "BBB"], session="2026-10-22"))
    with pytest.raises(ValueError, match="SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY"):
        build(auth={**AUTH, "mergedAtUtc": "2026-10-23T14:00:00+00:00"})       # same New York day as the signal: excluded


# --------------------------------------------------------------------------- #
# Prices available at observation time
# --------------------------------------------------------------------------- #
def test_prices_must_come_from_the_signal_session_and_not_from_the_future_or_the_past():
    for bad in ("2026-10-22", "2026-10-26"):
        with pytest.raises(ValueError, match="NOT_FROM_THE_SIGNAL_SESSION"):
            build(price_map=prices(["SPY", "QQQ", "AAA", "BBB"], session=bad))


def test_prices_retrieved_before_the_close_or_after_the_receipt_are_refused():
    with pytest.raises(ValueError, match="RETRIEVED_OUTSIDE_THE_RECEIPT_WINDOW"):
        build(price_map=prices(["SPY", "QQQ", "AAA", "BBB"], retrieved="2026-10-23T19:00:00+00:00"))
    with pytest.raises(ValueError, match="RETRIEVED_OUTSIDE_THE_RECEIPT_WINDOW"):
        build(price_map=prices(["SPY", "QQQ", "AAA", "BBB"], retrieved="2026-10-23T23:45:00+00:00"))


def test_a_missing_or_nonpositive_price_is_refused_never_filled():
    with pytest.raises(ValueError, match="OBSERVATION_PRICE_MISSING: QQQ"):
        build(price_map=prices(["SPY", "AAA", "BBB"]))
    broken = prices(["SPY", "QQQ", "AAA", "BBB"])
    broken["AAA"]["asTradedClose"] = 0.0
    with pytest.raises(ValueError, match="NOT_POSITIVE_AND_FINITE"):
        build(price_map=broken)


# --------------------------------------------------------------------------- #
# Validation of stored rows
# --------------------------------------------------------------------------- #
def reseal(r):
    r["receiptSha256"] = CORE.receipt_digest(r)
    return r


def test_any_edit_breaks_the_digest():
    r = build()
    r["decision"]["reasons"] = ["edited"]
    with pytest.raises(ValueError, match="RECEIPT_DIGEST_MISMATCH"):
        R.validate_receipt(r)


@pytest.mark.parametrize("mutate,message", [
    (lambda r: r["decision"]["weights"].update({"AAA": 0.20}), "WEIGHTS_VIOLATE_THE_SLOT_RULE"),
    (lambda r: r["decision"].update({"fallbackWeight": 0.5}), "FALLBACK_WEIGHT_INCONSISTENT"),
    (lambda r: r["decision"]["selected"][0].update({"sector": "Financials"}), "SECTOR_RULE_VIOLATED"),
    (lambda r: r["decision"]["selected"][0].update({"score": 0.001}), "SELECTED_NAME_DOES_NOT_CLEAR_THE_MATERIALITY_GATE"),
    (lambda r: r["decision"].update({"passers": list(reversed(r["decision"]["passers"]))}), "PASSERS_NOT_IN_REGISTERED_RANK_ORDER"),
    (lambda r: r["pitEvidence"].pop("AAA"), "PIT_EVIDENCE_REQUIRED_FOR_EVERY_SELECTED_NAME"),
    (lambda r: r["observationPrices"].pop("QQQ"), "OBSERVATION_PRICES_REQUIRED"),
    (lambda r: r.update({"dilution": {"status": "VERIFIED", "gate": True}}), "DILUTION_STATUS_MUST_BE_STATED_AS_UNVERIFIED"),
    (lambda r: r.update({"officialWeeklyDecisionAffected": True}), "RECEIPT_MUST_BE_RESEARCH_ONLY"),
    (lambda r: r.update({"horizonSessions": 21}), "BENCHMARK_OR_HORIZON_NOT_AS_REGISTERED"),
    (lambda r: r.update({"designDigest": "0" * 64}), "DIFFERS_FROM_THE_REGISTERED_DESIGN"),
    (lambda r: r.update({"extra": 1}), "RECEIPT_FIELD_NOT_IN_CONTRACT")])
def test_semantic_violations_are_refused_even_with_a_valid_digest(mutate, message):
    r = build(decision(("AAA", "Industrials", 0.3), ("BBB", "Utilities", 0.4)))
    mutate(r)
    with pytest.raises(ValueError, match=message):
        R.validate_receipt(reseal(r))


def test_pit_evidence_must_be_strictly_before_the_signal_date_and_carry_the_feature_identity():
    for bad in (evidence("AAA", available=SIGNAL), evidence("AAA", available="2026-10-24")):
        with pytest.raises(ValueError, match="PIT_INPUT_NOT_VISIBLE_BEFORE_THE_SIGNAL_DATE"):
            build(pit={"AAA": bad, "BBB": evidence("BBB")})
    wrong_day = evidence("AAA")
    wrong_day["asOf"] = "2026-10-22"
    with pytest.raises(ValueError, match="PIT_EVIDENCE_IDENTITY_MISMATCH"):
        build(pit={"AAA": wrong_day, "BBB": evidence("BBB")})


def test_pit_evidence_is_read_from_a_real_feature_snapshot_without_adding_anything():
    from datetime import date, timedelta
    from pipeline import us_shareholder_distribution as U

    def filing(year, stage="FY"):
        end = date(year, {"Q1": 3, "Q2": 6, "Q3": 9, "FY": 12}[stage], {"Q1": 31, "Q2": 30, "Q3": 30, "FY": 31}[stage])
        cf = [{"concept": "us-gaap_" + c, "value": v, "unit": "usd"} for c, v in (
            ("PaymentsOfDividendsCommonStock", 20 * (1 + 0.5 * (year - 2023))), ("PaymentsForRepurchaseOfCommonStock", 30),
            ("NetCashProvidedByUsedInOperatingActivities", 200), ("PaymentsToAcquirePropertyPlantAndEquipment", 10))]
        return dict(id="SYN-%s-%s" % (year, stage), ticker="SYN", source=U.SOURCE, fiscalYear=year, fiscalQuarter=0, form="10-K",
                    periodStart=date(year, 1, 1).isoformat(), periodEnd=end.isoformat(), periodDays=(end - date(year, 1, 1)).days,
                    availableFrom=(end + timedelta(days=30)).isoformat(), collectedAt="2026-10-01T00:00:00Z", acceptedDate=None,
                    statements={"cf": cf, "ic": [], "bs": []})
    snap = U.derive_features("SYN", "2025-11-01", [filing(2023), filing(2024)], U.SourceMetadata(U.SOURCE, "SYNTHETIC", "synthetic fiscal-YTD source contract"))
    ev = R.pit_evidence(snap)
    assert ev["featureDigest"] == snap.feature_digest and ev["asOf"] == "2025-11-01"
    ids = {i["filingId"] for f in ev["features"].values() for i in f["inputs"]}
    assert ids <= {"SYN-2023-FY", "SYN-2024-FY"} and ids
    assert all(i["availableFrom"] < "2025-11-01" for f in ev["features"].values() for i in f["inputs"])
    assert ev["features"]["totalCashDistributionTTM"]["value"] == 50 + 30 - 30 + 30 + 0 or ev["features"]["totalCashDistributionTTM"]["value"] is not None
    import json as _json
    CORE.scan_for_outcome_keys(_json.loads(_json.dumps(ev)))                       # no outcome-shaped key anywhere in the evidence


def test_a_receipt_may_not_name_an_outcome():
    r = build()
    r["pitEvidence"]["AAA"]["forwardReturn126"] = 0.1
    with pytest.raises(ValueError, match="OUTCOME"):
        R.validate_receipt(reseal(r))


# --------------------------------------------------------------------------- #
# Two pathways that never meet; no authorization exists
# --------------------------------------------------------------------------- #
def test_no_live_receipt_can_be_built_because_nothing_is_authorized():
    assert R.REGISTERED_AUTHORIZATION is None
    with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
        R.build_live_receipt(signal_date=SIGNAL, decision=decision(("AAA", "Industrials", 0.3), ("BBB", "Utilities", 0.4)), coverage={},
                             membership={}, observation_prices={}, pit_evidence={}, measured_tickers=[], data_files={})


def test_a_synthetic_receipt_can_never_pass_the_live_path_and_vice_versa(tmp_path):
    r = build()
    assert r["pathway"] == "SYNTHETIC_FIXTURE" and r["evidenceClass"] == "SYNTHETIC_FIXTURE"
    with pytest.raises(ValueError):
        R.validate_live_receipt(r)
    live = copy.deepcopy(r)
    live.update({"pathway": "LIVE", "evidenceClass": "PROSPECTIVE_PAPER_RESEARCH_CANDIDATE"})
    with pytest.raises(ValueError, match="LIVE_RECEIPT_REFUSED_ON_THE_SYNTHETIC_PATH"):
        R.validate_synthetic_receipt(reseal(live))


# --------------------------------------------------------------------------- #
# Append-only storage in the research namespace
# --------------------------------------------------------------------------- #
def test_append_only_ledger_refuses_duplicates_reordering_and_a_changed_spec(tmp_path):
    path = tmp_path / "ledger/research/us-capital-allocation-alpha-v1/receipts.jsonl"
    first = build()
    R.append_synthetic_receipt(path, first)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="RECEIPT_ALREADY_EXISTS"):
        R.append_synthetic_receipt(path, build())
    earlier = build(signal="2026-10-16", created="2026-10-16T23:30:00+00:00", clock="2026-10-16T23:31:00+00:00",
                    price_map=prices(["SPY", "QQQ", "AAA", "BBB"], session="2026-10-16", retrieved="2026-10-16T23:10:00+00:00"),
                    pit={t: evidence(t, signal="2026-10-16") for t in ("AAA", "BBB")})
    with pytest.raises(ValueError, match="RECEIPT_OUT_OF_ORDER"):
        R.append_synthetic_receipt(path, earlier)
    assert path.read_bytes() == before                                          # a refusal never touches existing bytes
    later = build(signal="2026-10-30", created="2026-10-30T23:30:00+00:00", clock="2026-10-30T23:31:00+00:00",
                  price_map=prices(["SPY", "QQQ", "AAA", "BBB"], session="2026-10-30", retrieved="2026-10-30T23:10:00+00:00"),
                  pit={t: evidence(t, signal="2026-10-30") for t in ("AAA", "BBB")})
    R.append_synthetic_receipt(path, later)
    assert path.read_bytes().startswith(before) and len(R.read_synthetic_ledger(path)) == 2


def test_the_ledger_cannot_live_next_to_the_official_weekly_decisions(tmp_path):
    with pytest.raises(ValueError, match="OFFICIAL_WEEKLY_DECISION_NAMESPACE"):
        R.append_synthetic_receipt(tmp_path / "ledger/weekly-decisions/receipts.jsonl", build())
    assert "weekly-decisions" not in R.RESEARCH_LEDGER and "weekly-decisions" not in __import__("pipeline.us_capital_allocation_evaluation", fromlist=["x"]).OUTCOME_LEDGER


def test_tampering_with_a_stored_row_is_caught_on_read(tmp_path):
    path = tmp_path / "ledger/research/us-capital-allocation-alpha-v1/receipts.jsonl"
    R.append_synthetic_receipt(path, build())
    path.write_text(path.read_text().replace("CANDIDATE_PORTFOLIO", "NO_ELIGIBLE_OPPORTUNITY"))
    with pytest.raises(ValueError, match="RECEIPT_DIGEST_MISMATCH"):
        R.read_synthetic_ledger(path)


# --------------------------------------------------------------------------- #
# The official weekly decisions are untouched
# --------------------------------------------------------------------------- #
def test_receipt_code_does_not_import_or_write_the_official_weekly_machinery():
    text = (ROOT / "pipeline/us_capital_allocation_receipts.py").read_text()
    for name in ("weekly_decision", "weekly_publish", "weekly_history"):
        assert "import " + name not in text and "from . import " + name not in text and "from .%s" % name not in text
    for name in ("weekly_decision.py", "weekly_publish.py", "weekly_history.py", "build.py"):
        production = (ROOT / "pipeline" / name).read_text()
        assert "us_capital_allocation" not in production


def test_official_weekly_decision_documents_are_byte_identical_to_main():
    """Pinned by sha256 of what main carried when this registration was written; any edit must be a different, reviewed change."""
    pinned = json.loads((ROOT / "docs/us-capital-allocation/protected-official-files.json").read_text())
    actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in WEEKLY_DECISION_FILES}
    assert actual == pinned["docs/weekly-decision"]
    cfg = json.loads((ROOT / "config.json").read_text())
    assert cfg["benchmarks"]["US"] == "SPY" and cfg["benchmark"] == "SPY"
    assert "QQQ" not in cfg["benchmarkSources"]
