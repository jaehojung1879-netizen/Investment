"""Invented report sources only; no network, recorder, model or historical outcomes."""
from copy import deepcopy
import hashlib
import json
import subprocess

import pytest

from pipeline import daily_decision_report as R

NOW = "2026-10-31T03:00:00+00:00"
PREFIX = "ledger/research-strategies/"


class MemorySnapshot:
    commit = "a" * 40
    committed_at = "2026-10-30T12:00:00+00:00"

    def __init__(self, docs=None):
        self.docs, self.sources = deepcopy(docs or {}), {}

    def read(self, path):
        value = self.docs.get(path)
        raw = json.dumps(value, sort_keys=True).encode()
        self.sources[path] = {"status": "READ" if value is not None else "MISSING", "sha256": hashlib.sha256(raw).hexdigest() if value is not None else None,
                              "url": R.REPO_URL + "/blob/" + self.commit + "/" + path, "path": path}
        return deepcopy(value)


def build(docs=None, now=NOW):
    return R.build(MemorySnapshot(docs), as_of=now, code_identity={"gitSha": "b" * 40})


def minimal_receipt():
    c = R.V1
    row = {k: None for k in c.REQUIRED}
    row.update(studyId=c.STUDY, schemaVersion=c.SCHEMA_VERSION, pathway=c.LIVE,
               evidenceClass=c.EVIDENCE_CLASS_BY_PATHWAY[c.LIVE], productionEffect="NONE", researchOnly=True,
               authorization={"mergedAtUtc": "2026-10-24T03:00:00+00:00"},
               signalDate="2026-10-30", executionDate="2026-11-02", createdAtUtc="2026-10-30T12:00:00+00:00",
               horizonsSessions=[126, 252], books={b: {"slots": [], "fallbackSlots": 5, "eligibleNames": 0,
                    "status": "THIN_CROSS_SECTION", "excluded": {"MISSING_WINDOW": 40}} for b in c.BOOKS})
    row["receiptSha256"] = R.P.receipt_digest(row)
    return row


def outcome(receipt):
    r = {"studyId": R.V1.STUDY, "evidenceClass": R.P.OUTCOME_EVIDENCE_CLASS,
         "receiptSha256": receipt["receiptSha256"], "signalDate": receipt["signalDate"],
         "executionDate": receipt["executionDate"], "horizonSessions": 126,
         "maturitySession": str(R.P.maturity_session(receipt["executionDate"], 126).date()),
         "createdAtUtc": "2027-12-01T12:00:00+00:00", "resolution": "COMPLETE", "status": "COMPLETE",
         "books": {"CH_LOWVOL": {"netExcessReturn": 0.0}}}
    r["recordSha256"] = hashlib.sha256(R.P.canonical(r)).hexdigest()
    return r


def test_unknown_is_not_zero_and_no_certified_pick_is_manufactured():
    r = build()
    for s in r["paperStudies"].values():
        assert s["recordedReceipts"] is None
        assert s["maturedRecordedOutcomes"] is None
        assert s["eligibleCounts"] is None
    for v in r["regions"].values():
        assert v["evidenceCertifiedCandidateCount"] is None
        assert v["benchmarkQuote"] is None
        assert v["freshnessAtReport"]["status"] == "UNKNOWN"
        assert v["newNominationsInThisReport"] == 0
    assert "UNKNOWN" in R.render(r)


def test_explicit_zero_and_skipped_survive_aggregate_workflow_success():
    pre = PREFIX + R.V1.STUDY + "/"
    r = build({pre + "assessment.json": {"studyId": R.V1.STUDY, "receipts": 0, "outcomes": 0},
               pre + "publication-status.record.json": {"studyId": R.V1.STUDY, "action": "record", "attemptedAt": "2026-10-30T12:00:00+00:00", "status": "SKIPPED", "reason": "NOT_FINAL_SESSION"},
               pre + "publication-status.json": {"studyId": R.V1.STUDY, "status": "OK", "steps": {"assess": {"status": "ASSESSED"}}}})
    s = r["paperStudies"][R.V1.STUDY]
    assert s["recordedReceipts"] == s["maturedRecordedOutcomes"] == 0
    assert s["eligibleCounts"] is None  # skipped before counting, not zero eligible
    assert s["attemptHistoryRows"] is None  # one status file is not a full attempt log
    assert s["latestRecordAttempt"]["status"] == "SKIPPED" and s["aggregateStatus"] == "OK"
    assert not r["safety"]["workflowSuccessIsStudySuccess"]


@pytest.mark.parametrize("count", [True, -1, 2.5, "0", None, 9])
def test_assessment_without_ledger_does_not_invent_count(count):
    pre = PREFIX + R.V1.STUDY + "/"
    s = build({pre + "assessment.json": {"receipts": count}})["paperStudies"][R.V1.STUDY]
    assert s["recordedReceipts"] is None


def test_receipt_eligibility_is_paper_only_and_absent_is_not_thin_zero():
    row = minimal_receipt()
    pre = PREFIX + R.V1.STUDY + "/"
    r = build({pre + "receipts.jsonl": [row], pre + "assessment.json": {"studyId": R.V1.STUDY, "receipts": 1, "outcomes": 0,
              "challengers": {"CH_LOWVOL": {"verdict": "PASS"}}}})
    s = r["paperStudies"][R.V1.STUDY]
    assert s["recordedReceipts"] == 1
    assert all(v == 0 for v in s["eligibleCounts"].values())
    assert s["paperBooks"]["CH_LOWVOL"]["fallbackSlots"] == 5
    assert r["regions"]["KR"]["newNominationsInThisReport"] == 0
    assert r["regions"]["KR"]["evidenceCertifiedCandidateCount"] is None


@pytest.mark.parametrize("mutation", ["digest", "duplicate", "synthetic", "future"])
def test_forged_duplicate_synthetic_future_receipts_are_not_counted(mutation):
    row = minimal_receipt()
    rows = [row]
    if mutation == "digest":
        row["books"]["CH_LOWVOL"]["eligibleNames"] = 99
    elif mutation == "duplicate":
        rows.append(deepcopy(row))
    else:
        row["evidenceClass"] = "SYNTHETIC_FIXTURE" if mutation == "synthetic" else row["evidenceClass"]
        row["createdAtUtc"] = "2029-01-01T12:00:00+00:00" if mutation == "future" else row["createdAtUtc"]
        row["receiptSha256"] = R.P.receipt_digest(row)
    s = build({PREFIX + R.V1.STUDY + "/receipts.jsonl": rows})["paperStudies"][R.V1.STUDY]
    assert s["recordedReceipts"] is None and s["errors"]


def test_only_linked_matured_persisted_outcomes_are_shown_without_calculation(monkeypatch):
    row = minimal_receipt()
    o = outcome(row)
    pre = PREFIX + R.V1.STUDY + "/"
    docs = {pre + "receipts.jsonl": [row], pre + "outcomes.jsonl": [o]}
    monkeypatch.setattr(R.V1, "build_outcome", lambda *a, **k: pytest.fail("must never calculate an outcome"))
    r = build(docs, now="2028-01-01T12:00:00+00:00")
    assert r["paperStudies"][R.V1.STUDY]["maturedRecordedOutcomes"] == 1
    assert r["paperStudies"][R.V1.STUDY]["outcomeRecords"][0]["books"]["CH_LOWVOL"]["netExcessReturn"] == 0.0
    # A valid zero result is preserved, never converted to UNKNOWN by truthiness.
    o["createdAtUtc"] = "2026-10-31T00:00:00+00:00"
    o["recordSha256"] = hashlib.sha256(R.P.canonical({k: v for k, v in o.items() if k != "recordSha256"})).hexdigest()
    docs[pre + "outcomes.jsonl"] = [o]
    s = build(docs)["paperStudies"][R.V1.STUDY]
    assert s["maturedRecordedOutcomes"] is None and not s["outcomeRecords"]


def test_old_fresh_claim_index_is_not_etf_quote_or_current_session():
    region = {"generatedAt": "2026-10-24T10:00:00+00:00", "status": "PASSIVE_NO_DEFENSIBLE_EDGE",
              "freshness": {"status": "FRESH", "sourceDate": "2026-10-23"}, "watchlist": [
                  {"ticker": "ONE.KS", "rank": 1, "priceMomentum": {"asOf": "2026-10-23"},
                   "exclusionCodes": ["ORDERING_NOT_ESTABLISHED"]}]}
    r = build({R.WEEKLY + "latest.json": {"regions": {"KR": region}},
               R.STATE: {"generatedAt": "2026-10-28T12:00:00+00:00", "holdingsByRegion": {"KR": ["FAKE"]},
                         "modelPortfolioWeights": {"FAKE": .99}, "opportunityTiersByTicker": {"FAKE": "BUY"}}})
    v = r["regions"]["KR"]
    assert v["freshnessAtReport"]["status"] == "STALE"
    assert v["freshnessReportedAtCreation"]["status"] == "FRESH"
    assert v["benchmarkQuote"] is None
    assert "FAKE" not in json.dumps(r)
    assert v["exploratoryWatchlist"][0]["freshness"]["status"] == "STALE"


def test_future_and_non_session_dates_do_not_become_fresh():
    assert R.freshness("KR", "2026-11-01", R.utc(NOW))["status"] == "INVALID"
    assert R.freshness("KR", "2026-10-24", R.utc(NOW))["status"] == "INVALID"
    assert R.freshness("KR", "nonsense", R.utc(NOW))["status"] == "INVALID"


def test_pure_deterministic_render_no_mutations_or_model_calls(monkeypatch):
    monkeypatch.setattr(R.W, "decide", lambda *a, **k: pytest.fail("not a new selector"))
    source = MemorySnapshot({R.STATE: {"macroRegime": "<script>x</script>|token=private"}})
    original = deepcopy(source.docs)
    a = R.build(source, as_of=NOW, code_identity={"gitSha": "b" * 40})
    b = R.build(MemorySnapshot(original), as_of=NOW, code_identity={"gitSha": "b" * 40})
    assert a == b and source.docs == original
    assert R.render(a) == R.render(b)
    assert R.text(0) == "0" and R.text(None) == "UNKNOWN"
    assert "<script>" not in R.text("<script>")
    assert "private" not in R.text("token=private")
    assert "N=0 to N&gt;10" not in R.render(a)  # literal static policy distinction is retained
    assert "N=0 to N>10" in R.render(a)


def test_git_snapshot_hashes_missing_corrupt_and_read_allowlist(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for k, v in (("user.name", "Synthetic Fixture"), ("user.email", "fixture@example.invalid")):
        subprocess.run(["git", "-C", str(tmp_path), "config", k, v], check=True)
    p = tmp_path / R.STATE
    p.parent.mkdir()
    p.write_text('{"marketAsOf": "2026-10-29"}')
    bad = tmp_path / (R.WEEKLY + "latest.json")
    bad.parent.mkdir(parents=True)
    bad.write_text('{"quote": NaN}')
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "invented source"], check=True)
    sha = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()
    s = R.GitSnapshot(tmp_path, sha)
    assert s.read(R.STATE)["marketAsOf"] == "2026-10-29"
    assert s.sources[R.STATE]["sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert s.read(R.WEEKLY + "latest.json") is None
    assert s.sources[R.WEEKLY + "latest.json"]["status"] == "INVALID_JSON_OR_SHAPE"
    assert s.read(R.WEEKLY + "receipts.jsonl") is None
    with pytest.raises(ValueError, match="NON_REPORT_SOURCE"):
        s.read("ledger/fundamentals/private.json")
    with pytest.raises(ValueError, match="IMMUTABLE"):
        R.GitSnapshot(tmp_path, "signal-history")


def test_naive_timestamp_and_future_snapshot_are_refused():
    with pytest.raises(ValueError, match="TIMEZONE"):
        build(now="2026-10-31T03:00:00")
    with pytest.raises(ValueError, match="COMMITTED_AFTER"):
        build(now="2026-10-29T03:00:00+00:00")


def test_wrong_study_zero_and_future_steps_are_quarantined():
    pre = PREFIX + R.V1.STUDY + "/"
    s = build({pre + "assessment.json": {"studyId": "OTHER", "receipts": 0, "outcomes": 0},
               pre + "publication-status.record.json": {"studyId": R.V1.STUDY, "action": "record", "status": "RECORDED", "attemptedAt": "2035-01-01T00:00:00+00:00"},
               pre + "publication-status.json": {"studyId": R.V1.STUDY, "status": "OK", "steps": "corrupt"}})["paperStudies"][R.V1.STUDY]
    assert s["recordedReceipts"] is None and s["maturedRecordedOutcomes"] is None
    assert s["latestRecordAttempt"] is None and s["receiptCountBasis"] == "UNKNOWN"
    assert any("MISMATCH" in e for e in s["errors"])


def test_wrong_digest_cannot_carry_validated_basis_label():
    row = minimal_receipt()
    row["receiptSha256"] = "0" * 64
    s = build({PREFIX + R.V1.STUDY + "/receipts.jsonl": [row]})["paperStudies"][R.V1.STUDY]
    assert s["recordedReceipts"] is None and s["receiptCountBasis"] == "UNKNOWN"


def test_impossible_future_signal_even_with_rehashed_body_is_refused():
    row = minimal_receipt()
    row.update(signalDate="2030-01-04", executionDate="2030-01-07")
    row["receiptSha256"] = R.P.receipt_digest(row)
    s = build({PREFIX + R.V1.STUDY + "/receipts.jsonl": [row]})["paperStudies"][R.V1.STUDY]
    assert s["recordedReceipts"] is None and s["latestReceipt"] is None


def test_attempts_are_signed_dated_B_rows_not_unchecked_json_lines():
    pre = PREFIX + R.B.STUDY + "/"
    row = R.B.attempt_row(signal_date=None, kind="SKIPPED", reason="NOT_WEEKLY", detail={},
                         attempted_at_utc="2026-10-30T01:00:00+00:00")
    s = build({pre + "attempts.jsonl": [row]})["paperStudies"][R.B.STUDY]
    assert s["attemptHistoryRows"] == 1 and s["attemptReasons"][0]["reason"] == "NOT_WEEKLY"
    row["reason"] = "RECORDED"
    s = build({pre + "attempts.jsonl": [row]})["paperStudies"][R.B.STUDY]
    assert s["attemptHistoryRows"] is None and s["attemptLogPhysicalRows"] == 1
    assert not s["attemptReasons"]


def test_report_json_also_redacts_error_credentials():
    pre = PREFIX + R.V1.STUDY + "/"
    r = build({pre + "publication-status.record.json": {"studyId": R.V1.STUDY, "action": "record", "status": "REFUSED",
               "attemptedAt": "2026-10-30T12:00:00+00:00", "reason": "api_key=private Authorization: Bearer private2"}})
    assert "private" not in json.dumps(r)
    assert "[REDACTED]" in json.dumps(r)
    nested = R.redact_tree({"api_key": "private", "Authorization": "Bearer private", "nested": {"token": "private"}})
    assert "private" not in json.dumps(nested)


def test_output_guard_covers_sibling_worktrees_metadata_and_symlinks(tmp_path):
    from scripts.render_daily_decision_report import safe_output
    repo, other = tmp_path / "repo", tmp_path / "other"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Synthetic", "-c", "user.email=fixture@example.invalid",
                    "commit", "--allow-empty", "-qm", "synthetic"], check=True)
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "--detach", "-q", str(other)], check=True)
    alias = tmp_path / "alias"
    alias.symlink_to(other, target_is_directory=True)
    for path in [repo / "ledger/new", other / "ledger/new", repo / ".git/new", alias / "ledger/new"]:
        with pytest.raises(ValueError, match="OUTPUT_INSIDE"):
            safe_output(path, root=repo)
        assert not path.exists()
    assert safe_output(tmp_path / "reports/new", root=repo) == tmp_path / "reports/new"
