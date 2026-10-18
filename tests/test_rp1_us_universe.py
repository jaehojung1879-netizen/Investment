"""Synthetic WP2 population accounting; no actual outcomes or label reads."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from pipeline import experiment_workbench as W
from scripts import rp1_us_universe as U
from scripts import rp1_inspect_us_universe as S

ROOT = Path(__file__).resolve().parents[1]


def spec():
    return json.loads((ROOT / S.SPEC).read_bytes())


def fixture():
    names = ["AAA", "BBB", "FIN", "RE", "UNKNOWN", "PARA", "OLD"]
    snapshots = [{"date": "2012-12-27", "members": names, "sourceCommit": "old"},
                 {"date": "2023-04-03", "members": names[:-1], "sourceCommit": "new"}]
    rows, ev_snaps, sectors = [], [], []
    for i, s in enumerate(snapshots):
        start = len(rows)
        rows.extend([[t, t + " Corp", "123" if i else None] for t in s["members"]])
        ev_snaps.append({"date": s["date"], "sourceCommit": s["sourceCommit"], "rows": list(range(start, len(rows)))})
        sectors.append({**s, "rows": {t: {"sector": ("Financials" if t == "FIN" else "Real Estate" if t == "RE"
            else "UNKNOWN" if t == "UNKNOWN" else "Industrials"), "cik": "123" if i else None} for t in s["members"]}})
    evidence = {"rows": rows, "snapshots": ev_snaps}
    dates = ["2013-01-02", "2013-01-03", "2023-04-03", "2023-04-04"]
    prices = {t: set(dates) for t in names if t != "OLD"}
    filings = [{"ticker": t, "cik": "123", "id": t, "availableFrom": "2012-12-01", "acceptedDate": "2012-12-02"}
               for t in names]
    return snapshots, sectors, evidence, prices, filings, dates


def measure(*, data=None):
    return U.measure(*(data or fixture()), spec(), through="2025-12-31")


def test_full_denominator_financials_and_known_conflict_holds_are_separate():
    report = measure()
    early = report["byYear"]["2013"]
    assert early["memberDays"] == 14
    assert early["financialRealEstateExcluded"] == 4
    assert early["industryUnresolved"] == 2
    assert early["exitedMemberDays"] == early["exitedNoPriceMemberDays"] == 2
    assert early["knownConflictMemberDays"] == 2  # PARA, still in denominator
    assert early["rules"]["R-a"]["eligibleMemberDays"] == 0
    assert early["rules"]["R-b"]["eligibleMemberDays"] == 4
    assert early["rules"]["R-b"]["legacyRawJoinMemberDays"] == 6
    assert early["rules"]["R-b"]["cikVerifiedMemberDays"] == 0
    assert report["byYear"]["2023"]["rules"]["R-a"]["eligibleMemberDays"] == 2
    assert report["selection"]["decision"] == "DATA_INSUFFICIENT"  # no missing-year pass
    for annual in report["byYear"].values():
        for row in annual["rules"].values():
            assert row["eligibleMemberDays"] + sum(row["firstFailureReasons"].values()) == annual["memberDays"]
    U.scan_output(report)


def test_cik_is_not_carried_back_and_accepted_day_is_strictly_public():
    d = fixture()
    before = measure(data=d)
    # Same-day membership unavailable, same-day accepted filing unavailable.
    d[4][:] = [{"ticker": t, "cik": "000123", "availableFrom": "2010-01-01", "acceptedDate": "2023-04-04"}
               for t in d[0][0]["members"]]
    after = measure(data=d)
    assert before["byYear"]["2013"] == after["byYear"]["2013"]
    assert after["byYear"]["2023"]["rules"]["R-a"]["eligibleMemberDays"] == 0
    projected = W.filing_prefix(d[4], "US", "2023-04-04")
    assert projected == ()
    assert not U.VisibleCiks(d[4]).matches("AAA", "123", "2023-04-04")
    assert U.VisibleCiks(d[4]).matches("AAA", "123", "2023-04-05")
    mismatch = U.VisibleCiks([{"ticker": "AAA", "cik": "456", "availableFrom": "2010-01-01"}])
    assert mismatch.reason("AAA", "123", "2023-04-04") == "CIK_MISMATCH"


def test_no_price_magnitude_or_future_presence_can_change_earlier_eligibility():
    data = fixture()
    baseline = measure(data=data)
    for i, t in enumerate(data[3]):
        data[3][t].update({"2026-01-01", "2026-01-02"})
    # Global diagnostic spans can change; past sample/coverage cannot.
    modified = measure(data=data)
    assert baseline["byYear"] == modified["byYear"]
    assert baseline["sampleIdentity"] == modified["sampleIdentity"]
    rows = [{"ticker": "AAA", "date": "2013-01-02", "Close": 1.0},
            {"ticker": "AAA", "date": "2026-01-01", "Close": 1e12}]
    a = U.presence(rows, "2025-12-31")
    rows[0]["Close"] = 1e100
    assert U.presence(rows, "2025-12-31") == a == {"AAA": {"2013-01-02"}}
    assert not U.presence([{**rows[0], "Close": float("nan")}], "2025-12-31")


def test_missing_year_exact_half_and_tie_break_without_rounding():
    years = list(range(2013, 2026))
    annual = {str(y): {"memberDays": 200, "rules": {r: {"eligibleMemberDays": 100} for r in U.RULES}} for y in years}
    assert U.select(years, annual)["decision"] == "R-a"
    annual["2013"]["rules"]["R-a"]["eligibleMemberDays"] = 99
    assert U.select(years, annual)["decision"] == "R-b"
    annual["2013"]["rules"]["R-b"]["eligibleMemberDays"] = 99
    assert U.select(years, annual)["decision"] == "DATA_INSUFFICIENT"
    del annual["2013"]
    assert U.select(years, annual)["decision"] == "DATA_INSUFFICIENT"


def test_no_current_only_universe_replacement_and_no_shareclass_cik_collapse():
    data = fixture()
    result = measure(data=data)
    assert result["byYear"]["2013"]["memberDays"] == 14  # includes departed OLD
    a = U.PopulationMember(W.Key("US", "2013-01-02", "replay-v16:US:AAA"))
    b = U.PopulationMember(W.Key("US", "2013-01-02", "replay-v16:US:BBB"))
    assert W.sample_identity([a, b]) == W.sample_identity([b, a])
    with pytest.raises(ValueError, match="DUPLICATE"):
        W.sample_identity([a, replace(a)])
    data[0][0]["members"].append("AAA")
    with pytest.raises(ValueError, match="DUPLICATE_SNAPSHOT_MEMBER"):
        measure(data=data)


def test_duplicate_alias_targets_hold_both_members_and_keep_full_denominator(monkeypatch):
    data = fixture()
    real = U.identity_maps
    def collide(*args, **kwargs):
        raw, malformed, mappings, ambiguous = real(*args, **kwargs)
        mappings["BBB"] = "AAA"
        return raw, malformed, mappings, ambiguous
    monkeypatch.setattr(U, "identity_maps", collide)
    report = measure(data=data)
    late = report["byYear"]["2023"]
    assert late["rules"]["R-a"]["eligibleMemberDays"] == 0
    assert late["rules"]["R-a"]["firstFailureReasons"]["DUPLICATE_PRICING_IDENTITY"] == 4
    assert late["rules"]["R-b"]["eligibleMemberDays"] == 4  # exact symbols unchanged
    assert late["memberDays"] == 13


def test_panel_postdating_departure_is_suspect_not_terminal_zero():
    data = fixture()
    data[3]["OLD"] = {"2025-01-02"}
    report = measure(data=data)
    suspect = next(p for p in report["suspectPanels"] if p["symbol"] == "OLD")
    assert "PANEL_POSTDATES_MEMBERSHIP" in suspect["reasons"]
    assert suspect["noExactPriceDays"] == suspect["memberDays"]
    assert report["departed"]["withoutAnyDirectPricePanel"] == 0
    assert report["departed"]["notIdentitySafeDirectPanel"] == 1
    assert report["byYear"]["2013"]["rules"]["R-b"]["eligibleMemberDays"] == 4


def test_same_day_observations_follow_existing_stable_membership_order():
    data = fixture()
    extra = {**data[0][-1], "sourceCommit": "newer"}
    data[0].append(extra)
    data[1].append({**data[1][-1], "sourceCommit": "newer"})
    data[2]["snapshots"].append({**data[2]["snapshots"][-1], "sourceCommit": "newer"})
    result = measure(data=data)
    assert result["snapshotCoverage"]["multipleObservationDays"] == 1
    assert result["byYear"] == measure()["byYear"]


def test_no_snapshot_cannot_silently_reduce_denominator():
    data = fixture()
    data[-1].append("2012-01-01")
    result = measure(data=data)
    assert result["selection"]["decision"] == "DATA_INSUFFICIENT"
    assert result["snapshotCoverage"]["missingSnapshotDates"] == ["2012-01-01"]


@pytest.mark.parametrize("key", ["forwardReturnH126", "labels", "winner", "cagr", "MDD", "Close", "weights", "model_prediction"])
def test_output_scanner_rejects_outcomes_and_price_values(key):
    with pytest.raises(ValueError, match="FORBIDDEN_OUTPUT"):
        U.scan_output({"nested": [{key: 0}]})
    with pytest.raises(ValueError, match="NONZERO"):
        U.scan_output({"labelReads": 1})


def test_preview_opens_no_source_or_spec(monkeypatch, capsys):
    def forbidden(*a, **kw):
        raise AssertionError("unexpected IO")
    monkeypatch.setattr(S, "inspect", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    assert S.main([]) == 0
    assert json.loads(capsys.readouterr().out)["sourceReads"] == 0


def test_raw_allowlist_denies_results_labels_and_benchmarks_without_subprocess(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("unexpected subprocess")
    monkeypatch.setattr(subprocess, "check_output", forbidden)
    src = S.Sources(ROOT)
    for path in ("docs/results/alpha-opportunity-model-v3-survivorship-audit.json", "ledger/historical/replay-v16/signals.jsonl.gz",
                 "ledger/labels/winner.json", "ledger/replay-inputs/objects/" + "a" * 64 + ".json.gz"):
        with pytest.raises(ValueError, match="ALLOWLIST"):
            src.blob(S.S.SOURCE_COMMIT, path)


def test_measure_and_inspection_with_outcome_spies_and_synthetic_sources(monkeypatch):
    from pipeline import us_decision_pilot as P, winner_inflection_execution as E, winner_inflection_exploration as X
    calls = []
    def forbidden(*a, **kw):
        calls.append(True)
        raise AssertionError("outcome access")
    for obj, names in ((P, ("simulate", "metrics", "label_reading")),
                       (E, ("execute", "outcome", "label_cohorts", "model_predictions", "economics")),
                       (X, ("training_plan",)), (W, ("LabelReference", "Fold"))):
        for name in names:
            monkeypatch.setattr(obj, name, forbidden)
    data = fixture()
    manifest = {"through": "2025-12-31", "components": {"price/2013-01": ["a" * 64]}}
    manifest["sha256"] = S.S.RI.digest(manifest)
    monkeypatch.setattr(S.S, "MANIFEST_SHA", manifest["sha256"])
    class FakeSources:
        def __init__(self, repo):
            self.receipts = {}
        def blob(self, commit, path):
            assert commit == S.S.SOURCE_COMMIT and path == S.S.MANIFEST
            return json.dumps(manifest).encode()
        def json(self, path):
            if path == S.S.MEMBERS:
                self.receipts[S.S.CODE_BASE + ":" + path] = {"sha256": "m"}
                return {"snapshots": data[0]}
            if path == S.S.SECTORS:
                return {"snapshots": data[1]}
            assert path == S.EVIDENCE
            return {**data[2], "pinnedMembershipSha256": "m"}
        def component(self, ref):
            assert ref == "a" * 64
            return [{"ticker": t, "date": day, "Close": 10.0} for t, days in data[3].items() for day in days]
        def rows(self, path):
            assert path.startswith("ledger/fundamentals/us/finnhub-")
            return data[4] if "2012" in path else []
    monkeypatch.setattr(S, "Sources", FakeSources)
    report = S.inspect(ROOT, spec())
    assert calls == []
    assert report["accessCounters"] == dict.fromkeys(("outcomeReads", "forwardPriceReads", "labelReads", "modelFits", "locksCreated"), 0)
    U.scan_output(report)


def test_spec_preserves_wp2_fifty_percent_and_never_authorizes_execution():
    fixed = spec()
    S.validate_spec(fixed)
    for key, value in (("years", [2023]), ("historicalExecutionAuthorized", True), ("pricePresenceOnly", False),
                       ("knownSuspectSymbols", {})):
        changed = deepcopy(fixed)
        changed[key] = value
        with pytest.raises(ValueError, match="CONTRACT_CHANGED"):
            S.validate_spec(changed)
    fixed["threshold"]["numerator"] = 49
    with pytest.raises(ValueError, match="CONTRACT_CHANGED"):
        S.validate_spec(fixed)


def test_committed_measurement_historical_code_and_equivalent_relocated_reader():
    path = ROOT / "docs/research-program/results/rp1-wp2-us-universe-v1.json"
    report = json.loads(path.read_bytes())
    U.scan_output(report)
    assert report["specSha256"] == S.S.RI.digest(spec())
    layout = S.verify_historical_code(report)
    assert layout["scientificChange"] is False
    assert report["daily"]["selection"] == U.select(spec()["years"], report["daily"]["byYear"])
    assert len(report["daily"]["byYear"]) == 13
    assert report["accessCounters"]["outcomeReads"] == 0


def test_sealed_directories_c1_files_and_workflow_census_unchanged():
    fixed = spec()
    for directory, expected in fixed["protectedTreeSha256"].items():
        assert U.RAF.digest_tree(ROOT / directory) == expected
    for name, expected in fixed["protectedC1FileSha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
