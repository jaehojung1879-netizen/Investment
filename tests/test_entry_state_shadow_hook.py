"""The scheduled-ledger hook of entry-state-shadow-ledger-v1 (#306): gating, isolation, idempotency, provenance.

Invented inputs only. Nothing is fetched; the real child process runs with ``--offline``.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tests.test_entry_state_shadow_observation import NODE, fixture

ROOT = Path(__file__).resolve().parents[1]
STUDY = "entry-state-shadow-ledger-v1"
SCHEDULED = {"GITHUB_ACTIONS": "true", "GITHUB_WORKFLOW": "Append paper-signal ledger", "GITHUB_REF": "refs/heads/main"}
MAIN_A, MAIN_B = "a" * 40, "b" * 40


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree(root: Path) -> dict:
    return {str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file()}


def mini_ledger(tmp_path: Path):
    """A miniature signal-history ledger: the two published inputs plus files that must never change."""
    champion, weekly, config = fixture()
    ledger = tmp_path / "ledger"
    files = {
        "research-strategies/current-champion-decisions-v1/latest.json": json.dumps(champion),
        "weekly-decisions/latest.json": json.dumps(weekly),
        "weekly-decisions/receipts.jsonl": '{"receipt":1}\n',
        "signals.jsonl": '{"signal":1}\n{"signal":2}\n',
        "summary.json": '{"ok":true}\n',
        "research-strategies/kr-selection-challenger-v1/receipts.jsonl": '{"r":1}\n',
    }
    for rel, body in files.items():
        path = ledger / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"kellyPortfolio": config}))
    return ledger, cfg


def child(ledger: Path, cfg: Path, main_sha: str):
    """The recorder's real CLI, as `run_isolated` starts it, minus the live price fetch."""
    env = {**__import__("os").environ, "GITHUB_SHA": main_sha}
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/record_entry_state_shadow.py"), "run",
         str(ledger / "research-strategies/current-champion-decisions-v1/latest.json"),
         str(ledger / "weekly-decisions/latest.json"), str(cfg), str(ledger / "research-strategies" / STUDY), "--offline"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)


# ----------------------------------------------------------------------------------------------------------------------- gating
@pytest.mark.parametrize("env,expected", [
    ({}, False),
    ({**SCHEDULED, "GITHUB_REF": "refs/pull/306/merge"}, False),          # a pull-request run never records
    ({**SCHEDULED, "GITHUB_WORKFLOW": "Tests"}, False),
    ({**SCHEDULED, "GITHUB_ACTIONS": "false"}, False),
    ({**SCHEDULED, "GITHUB_REF": "refs/heads/claude/some-branch"}, False),
    (SCHEDULED, True),
])
def test_hook_records_only_in_the_scheduled_workflow_on_main(monkeypatch, env, expected):
    shadow = importlib.import_module("scripts.record_entry_state_shadow")
    for key in SCHEDULED:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert shadow.hook_enabled() is expected


def _isolated_paper_ledger_step(monkeypatch):
    """The paper-ledger step also runs other studies' hooks; here none may touch git, the clock or the vendor."""
    for module, name in (("scripts.record_kr_selection_challenger", "run_all"), ("scripts.record_kr_selection_challenger_v2", "run_all")):
        monkeypatch.setattr(importlib.import_module(module), name, lambda *a: 0)
    monkeypatch.setattr(importlib.import_module("scripts.record_rp1_b_h1_state"), "run_isolated", lambda *a, **k: 0)
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: {})


def _site(tmp_path):
    path = tmp_path / "site.json"
    path.write_text(json.dumps({"modelVersion": "m", "generatedAt": "2026-11-02T04:30:00+00:00", "provenance": {"modelVersion": "m"}}))
    return path


def test_paper_ledger_step_calls_the_hook_only_when_scheduled_and_survives_its_failure(tmp_path, monkeypatch):
    update = importlib.import_module("scripts.update_ledger")
    shadow = importlib.import_module("scripts.record_entry_state_shadow")
    _isolated_paper_ledger_step(monkeypatch)
    seen = []
    monkeypatch.setattr(shadow, "run_isolated", lambda *a, **k: seen.append(a) or 0)
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    site = _site(tmp_path)
    for key in SCHEDULED:
        monkeypatch.delenv(key, raising=False)
    assert update.main([str(site), str(ledger)]) == 0 and seen == []         # not scheduled: never called
    for key, value in SCHEDULED.items():
        monkeypatch.setenv(key, value)
    assert update.main([str(site), str(ledger)]) == 0
    champion, weekly, config, namespace = seen[0]
    assert champion == ledger / "research-strategies/current-champion-decisions-v1/latest.json"
    assert weekly == ledger / "weekly-decisions/latest.json" and config == ROOT / "config.json"
    assert namespace == ledger / "research-strategies" / STUDY
    before = tree(ledger)
    monkeypatch.setattr(shadow, "run_isolated", lambda *a, **k: 124)       # the child timed out
    assert update.main([str(site), str(ledger)]) == 0
    monkeypatch.setattr(shadow, "run_isolated", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert update.main([str(site), str(ledger)]) == 0                       # an exception never fails the paper ledger
    status = json.loads((ledger / "research-strategies" / STUDY / "publication-status.json").read_text())
    assert status["status"] == "STEP_FAILED" and status["productionEffect"] == "NONE" and "boom" in status["error"]
    changed = {k for k, v in tree(ledger).items() if before.get(k) != v}
    assert all(k.startswith(f"research-strategies/{STUDY}/") or k in {"signals.jsonl", "portfolio-signals.jsonl", "summary.json",
                                                                       "outcomes.jsonl", "portfolio-outcomes.jsonl"} for k in changed)


# ---------------------------------------------------------------------------------------------- the real child, on a mini ledger
@pytest.mark.skipif(NODE is None, reason="Node unavailable")
def test_real_child_writes_only_its_own_namespace_and_a_reread_changes_nothing(tmp_path):
    ledger, cfg = mini_ledger(tmp_path)
    before = tree(ledger)
    first = child(ledger, cfg, MAIN_A)
    assert first.returncode == 0, first.stderr
    after = tree(ledger)
    namespace = f"research-strategies/{STUDY}/"
    assert {k: v for k, v in before.items()} == {k: v for k, v in after.items() if k in before}      # nothing existing changed
    assert all(k.startswith(namespace) for k in after.keys() - before.keys())
    assert {Path(k).name for k in after.keys() - before.keys()} == {"decisions.jsonl", "publication-status.json"}

    # The same published week read again on a later run, from a moved main commit: no conflict, no new line, no fill, no NAV.
    decisions = (ledger / namespace / "decisions.jsonl").read_bytes()
    second = child(ledger, cfg, MAIN_B)
    assert second.returncode == 0, second.stderr
    assert (ledger / namespace / "decisions.jsonl").read_bytes() == decisions
    assert not (ledger / namespace / "fills.jsonl").exists() and not (ledger / namespace / "nav-daily.jsonl").exists()
    status = json.loads((ledger / namespace / "publication-status.json").read_text())
    assert status["status"] == "OK" and status["report"]["decisions"] == {
        "alreadyPresent": len(decisions.splitlines()), "appended": 0, "conflictsRefused": []}


@pytest.mark.skipif(NODE is None, reason="Node unavailable")
def test_receipt_provenance_is_content_addressed_and_says_what_was_not_verified(tmp_path):
    """Known limitation, pinned: the scheduled hook runs before its inputs are committed again, so `sourceCommit` is the MAIN commit that
    ran the workflow, not an immutable signal-history commit. The receipt therefore carries the SHA-256 of every input byte it read, and
    the verification label says the bytes were not authenticated against a Git object."""
    ledger, cfg = mini_ledger(tmp_path)
    assert child(ledger, cfg, MAIN_A).returncode == 0
    rows = [json.loads(s) for s in (ledger / "research-strategies" / STUDY / "decisions.jsonl").read_text().splitlines()]
    assert rows and len({r["receiptId"] for r in rows}) == len(rows)
    for row in rows:
        assert row["sourceCommit"] == MAIN_A and row["code"]["commit"] == MAIN_A         # the code/config commit, not the source's
        assert row["sourceHashes"]["championSha256"] == sha((ledger / "research-strategies/current-champion-decisions-v1/latest.json").read_bytes())
        assert row["sourceHashes"]["weeklySha256"] == sha((ledger / "weekly-decisions/latest.json").read_bytes())
        assert row["sourceHashes"]["configSha256"] == sha(cfg.read_bytes())
        assert row["sourceHashes"]["sourceVerification"] == "SHA256_OF_BYTES_WRITTEN_IN_THIS_RUN_BEFORE_COMMIT"
        assert row["productionEffect"] == "NONE" and row["liveValidated"] is False and row["evidenceClass"] == "PROSPECTIVE_PAPER"
        assert row["executionSession"] > row["asOfDate"]                                   # a fill can never predate the signal session


# ------------------------------------------------------------------------ a refused observation must not cost the paper path its NAV
def _recorder():
    return importlib.import_module("scripts.record_entry_state_shadow")


def _stored_week(directory):
    """One recorded week (signal 2026-10-30, executes 2026-11-02), as the first successful scheduled run would have left it."""
    from tests.test_entry_state_shadow_ledger import SUNDAY, observation
    L = importlib.import_module("pipeline.entry_state_shadow_ledger")
    L.append_decisions(directory, L.decision_receipts(observation(as_of="2026-10-30"), recorded_at=SUNDAY, code={}, observation_sha256="w1"))
    return L


def test_a_refused_observation_still_marks_the_stored_book_and_keeps_the_readout(tmp_path, monkeypatch):
    """The weekly decision is rewritten daily but the champion artifact only when no session is mid-flight, so from Tuesday to Saturday
    the two published files are from different generations and the observer refuses to pair them. That refusal concerns NEW decisions
    only; the stored book still has to be marked, and the stored status the daily brief reads must keep its NAV table."""
    from datetime import datetime, timezone
    recorder = _recorder()
    directory = tmp_path / "study"
    L = _stored_week(directory)
    now = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
    prices = {"2026-11-02": 100.0, "2026-11-03": 101.0, "2026-11-04": 102.0, "2026-11-05": 103.0}

    def closes(ticker, session):
        return prices.get(session) if ticker == "069500.KS" else 50.0
    closes.quote_through = {"069500.KS": "2026-11-05", "000001.KS": "2026-11-05"}
    closes.valuation_origins = {}
    monkeypatch.setattr(L, "utc_now", lambda: now)
    monkeypatch.setattr(recorder, "live_closes", lambda d: closes)

    def refuse(*a, **k):
        raise RuntimeError("OBSERVATION_REFUSED: DIFFERENT_GENERATION_CANNOT_PAIR")
    monkeypatch.setattr(recorder, "observe", refuse)
    assert recorder.run(Path("c.json"), Path("w.json"), Path("cfg.json"), directory) == 0
    status = json.loads((directory / "publication-status.json").read_text())
    assert status["status"] == "OK"
    assert status["report"]["observation"] == {"status": "REFUSED", "reason": "OBSERVATION_REFUSED: DIFFERENT_GENERATION_CANNOT_PAIR"}
    assert status["report"]["decisions"]["appended"] == 0
    policy = status["report"]["readout"]["strategies"]["KR:CURRENT_POLICY"]
    assert policy["fillState"] == "FILLED" and policy["navDate"] == "2026-11-05" and policy["nav"] is not None
    assert (directory / "nav-daily.jsonl").exists()


def test_a_refused_observation_with_no_ledger_yet_is_reported_as_refused(tmp_path, monkeypatch):
    recorder = _recorder()
    directory = tmp_path / "study"

    def refuse(*a, **k):
        raise RuntimeError("OBSERVATION_REFUSED: DIFFERENT_GENERATION_CANNOT_PAIR")
    monkeypatch.setattr(recorder, "observe", refuse)
    assert recorder.main(["run", "c.json", "w.json", "cfg.json", str(directory)]) == 1
    status = json.loads((directory / "publication-status.json").read_text())
    assert status["status"] == "REFUSED" and "DIFFERENT_GENERATION_CANNOT_PAIR" in status["error"]
    assert not (directory / "decisions.jsonl").exists()


@pytest.mark.skipif(NODE is None, reason="Node unavailable")
def test_the_recorded_refusal_reason_is_the_error_not_the_node_banner(tmp_path):
    ledger, cfg = mini_ledger(tmp_path)
    weekly = ledger / "weekly-decisions/latest.json"
    doc = json.loads(weekly.read_text())
    doc["generatedAt"] = "2026-11-02T06:11:21+00:00"                        # a later weekly generation than the champion's
    weekly.write_text(json.dumps(doc))
    result = child(ledger, cfg, MAIN_A)
    assert result.returncode == 1
    status = json.loads((ledger / "research-strategies" / STUDY / "publication-status.json").read_text())
    assert status["status"] == "REFUSED" and "DIFFERENT_GENERATION_CANNOT_PAIR" in status["error"]
    assert "Node.js v" not in status["error"]
