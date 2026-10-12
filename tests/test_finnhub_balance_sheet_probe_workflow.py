"""Finnhub balance-sheet LIVE probe: the owner-dispatch-only, read-only path, and the verdicts it can reach.

The probe answers one question — did Finnhub omit the balance sheet, move it, or complete it later — with at most 12 real requests. What is pinned:

  * the job lives in the existing `fundamentals.yml` as a new `region` choice that no collector matches, because a new workflow file would break the
    frozen workflow census (`test_kr_alpha_atlas_price_repair_workflow_inventory.py`, byte-pinned) and `probes.yml` is byte-pinned by two sealed specs;
  * no event can start a collection through it, and no event but a dispatch of `main` can start it;
  * it holds a read-only token, writes nothing to signal-history, and the Finnhub key reaches exactly one step, and not at all for a plan-only run;
  * no dispatch input is interpolated into shell;
  * each of the four outcomes (omitted / moved / later completed / insufficient) is reachable from controlled responses and maps to one repair path;
  * the key can never end up in a report or a raw-evidence file;
  * the existing schedule path, the collectors' conditions and the sealed files are unchanged.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import finnhub_fundamentals as FF           # noqa: E402
from pipeline import historical_store as HS               # noqa: E402

WORKFLOW = ROOT / ".github/workflows/fundamentals.yml"
PLAN_JSON = ROOT / "docs/us-readiness/us-finnhub-balance-sheet-probe-plan-v1.json"
DOC = ROOT / "docs/us-finnhub-balance-sheet-probe-ko.md"
SECRET = "SECRETKEY-do-not-print"


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load("probe_finnhub_bs_live", "scripts/probe_finnhub_balance_sheet.py")


# ---------------------------------------------------------------- the workflow, read as text (pyyaml is not a runtime dependency)
def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def job_block(name: str) -> str:
    text = workflow_text()
    start = text.index(f"\n  {name}:\n") + 1
    nxt = re.search(r"\n  [a-z][a-z-]*:\n", text[start + 3:])
    return text[start:start + 3 + nxt.start()] if nxt else text[start:]


def job_if(name: str) -> str:
    return re.search(r"^    if: (.*)$", job_block(name), re.M).group(1)


def gh_if(expression: str, event: str, inputs: dict, ref: str) -> bool:
    """A faithful-enough evaluator of the only expression forms these `if:` lines use."""
    py = expression.replace("&&", " and ").replace("||", " or ")
    py = re.sub(r"!\s*startsWith\(\s*inputs\.(\w+)\s*,\s*'([^']*)'\s*\)", r"(not str(I.get('\1','')).startswith('\2'))", py)
    py = re.sub(r"startsWith\(\s*inputs\.(\w+)\s*,\s*'([^']*)'\s*\)", r"str(I.get('\1','')).startswith('\2')", py)
    py = re.sub(r"inputs\.(\w+)", r"I.get('\1','')", py)
    py = py.replace("github.event_name", "E").replace("github.ref", "R")
    return bool(eval(py, {"I": inputs, "E": event, "R": ref}))      # noqa: S307 - the expression is this repository's own


JOBS = ("kr", "us", "kr-raw", "us-finnhub-bs-probe")
DISPATCH_DEFAULTS = {"target": "auto", "region": "both", "max_calls": "", "max_minutes": ""}


def runs(event, ref="refs/heads/main", **inputs):
    given = {} if event == "schedule" else {**DISPATCH_DEFAULTS, **inputs}
    return {j for j in JOBS if gh_if(job_if(j), event, given, ref)}


def test_the_probe_job_is_selected_only_by_its_own_region_and_never_starts_a_collector():
    assert runs("schedule") == {"kr", "us"}                                                        # the nightly run is unchanged
    assert runs("workflow_dispatch") == {"kr", "us"}                                                # default dispatch is unchanged
    assert runs("workflow_dispatch", region="us") == {"us"} and runs("workflow_dispatch", region="kr") == {"kr"}
    assert runs("workflow_dispatch", target="raw-statements", region="both") == {"kr-raw"}
    assert runs("workflow_dispatch", region="finnhub-bs-probe") == {"us-finnhub-bs-probe"}          # and NOTHING else starts
    assert runs("workflow_dispatch", region="finnhub-bs-probe", max_calls="0") == {"us-finnhub-bs-probe"}


def test_secret_bearing_code_runs_only_for_a_dispatch_of_main():
    assert runs("workflow_dispatch", ref="refs/heads/claude/some-branch", region="finnhub-bs-probe") == set()
    assert runs("workflow_dispatch", ref="refs/pull/1/merge", region="finnhub-bs-probe") == set()
    assert runs("schedule", ref="refs/heads/main") == {"kr", "us"}
    assert runs("workflow_dispatch", region="finnhub-bs-probe", target="raw-probe-2015") == {"kr-raw"}   # no combination runs both


def test_the_collectors_conditions_are_byte_identical_to_the_ones_other_tests_pin():
    assert job_if("kr") == "github.event_name == 'schedule' || ((inputs.region == 'both' || inputs.region == 'kr') && !startsWith(inputs.target, 'raw-'))"
    assert job_if("us") == "github.event_name == 'schedule' || ((inputs.region == 'both' || inputs.region == 'us') && !startsWith(inputs.target, 'raw-'))"
    assert job_if("kr-raw") == "github.event_name == 'workflow_dispatch' && startsWith(inputs.target, 'raw-')"
    text = workflow_text()
    assert 'options: ["both", "kr", "us", "finnhub-bs-probe"]' in text and "cron: \"40 3 * * *\"" in text


def test_the_probe_job_is_read_only_and_never_touches_signal_history():
    job = job_block("us-finnhub-bs-probe")
    assert "permissions:\n      contents: read" in job and "contents: write" not in job
    assert job.count("actions/checkout@v5") == 2 and job.count("persist-credentials: false") == 2
    for forbidden in ("git push", "git commit", "git add", "git config", "git worktree", "git rebase", "git fetch", "gh ", "curl ", "pip install"):
        assert forbidden not in job, forbidden
    assert "ref: signal-history" in job and "path: signal-history" in job and "sparse-checkout: ledger/fundamentals/us" in job
    assert "--store signal-history/ledger/fundamentals/us" in job
    for step in job.split("      - name: Upload")[1:]:
        assert "signal-history" not in step.split("\n      - name:", 1)[0], "an upload step may not carry stored fundamentals"


def test_the_finnhub_key_reaches_exactly_one_step_and_not_at_all_for_a_plan_only_run():
    job = job_block("us-finnhub-bs-probe")
    assert job.count("secrets.") == 1 and "secrets.FINNHUB" in job
    step = job.split("- name: Probe (read-only)\n", 1)[1].split("\n      - name:", 1)[0]
    assert "secrets.FINNHUB" in step
    assert "FINNHUB_API_KEY: ${{ inputs.max_calls != '0' && secrets.FINNHUB || '' }}" in step
    assert not [line for line in job.splitlines() if "echo" in line and "FINNHUB_API_KEY" in line]


def test_no_dispatch_input_is_interpolated_into_a_shell_script():
    job = job_block("us-finnhub-bs-probe")
    for step in job.split("      - name: ")[1:]:
        for script in re.findall(r"run: \|\n((?:          .*\n?)+)", step):
            assert "${{" not in script, step.splitlines()[0]
    step = job.split("- name: Probe (read-only)\n", 1)[1]
    assert "MAX_CALLS: ${{ inputs.max_calls }}" in step and r'[[ "$calls" =~ ^[0-9]+$ ]]' in step
    assert "set -euo pipefail" in step and "| tee probe.log" in step
    assert '--max-calls "$calls"' in step and "--tickers" not in step


def test_evidence_is_split_into_a_sanitized_report_and_a_short_lived_raw_artifact():
    job = job_block("us-finnhub-bs-probe")
    report = job.split("- name: Upload the sanitized report\n", 1)[1].split("\n      - name:", 1)[0]
    raw = job.split("- name: Upload the raw response bodies (restricted, short retention)\n", 1)[1].split("\n      - name:", 1)[0]
    assert "finnhub-bs-probe-report" in report and "retention-days: 90" in report and "probe-raw" not in report
    assert "finnhub-bs-probe-raw-restricted" in raw and "retention-days: 7" in raw and "probe-raw.jsonl.gz" in raw
    assert "probe-report.json" not in raw and "timeout-minutes: 15" in job


def test_the_edit_to_fundamentals_yml_is_limited_to_the_region_choice_and_the_new_job():
    try:
        diff = subprocess.run(["git", "diff", "-U0", "origin/main...HEAD", "--", ".github/workflows/fundamentals.yml"],
                              capture_output=True, text=True, cwd=ROOT, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("no git history available")
    if not diff:
        pytest.skip("already merged: nothing to compare")
    removed = [line for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")]
    assert len(removed) == 2 and any("description:" in line for line in removed) and any("options:" in line for line in removed)


def test_sealed_and_neighbouring_files_are_untouched_by_this_change():
    try:
        diff = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD"], capture_output=True, text=True, cwd=ROOT, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("no git history available")
    touched = set(diff.split())
    protected = {".github/workflows/probes.yml", ".github/workflows/tests.yml", ".github/workflows/ledger.yml", "pipeline/datafeed.py",
                 "pipeline/us_real_source_preflight.py", "scripts/preflight_us_real_sources.py", "tests/test_workflow_inventory.py",
                 "tests/test_kr_alpha_atlas_price_repair_workflow_inventory.py", "docs/workflow-inventory.md",
                 "docs/workflow-inventory-addendum.md", "pipeline/us_cash_profitability.py", "pipeline/finnhub_fundamentals.py",
                 "pipeline/finnhub_derive.py"}
    assert not touched & protected and not [p for p in touched if p.startswith(("docs/results/", "research_specs/"))]
    probes = hashlib.sha256((ROOT / ".github/workflows/probes.yml").read_bytes()).hexdigest()
    assert probes == "2c00464e756e9512cec60961b22a35dd40d3798f350efb49a12e0aa94fab190d"      # still what two sealed specs pin


# ---------------------------------------------------------------- the probe: plan-only, selection, verdicts, leak guard
def usd(concept, value):
    return {"concept": "us-gaap_" + concept, "label": concept, "unit": "usd", "value": value}


def raw_filing(accession, quarter, end, filed, *, bs="yes", form="10-Q", extra_key=None):
    report = {"ic": [usd("NetIncomeLoss", 3.0)], "cf": [usd("NetCashProvidedByUsedInOperatingActivities", 5.0)]}
    if bs == "yes":
        report["bs"] = [usd("Assets", 100.0)]
    elif bs == "empty":
        report["bs"] = []
    elif bs == "moved":
        report[extra_key or "balanceSheet"] = [usd("Assets", 100.0)]
    return {"accessNumber": accession, "cik": "1", "form": form, "year": 2026, "quarter": quarter, "startDate": end[:4] + "-01-01",
            "endDate": end, "filedDate": filed, "acceptedDate": filed + " 06:00:00", "report": report}


def stored_row(ticker, filing, collected, with_bs):
    record, _ = FF.build_record(ticker, filing, collected, FF.QUARTERLY)
    if not with_bs:
        record["statements"]["bs"] = []
    return record


def make_store(tmp_path, tickers=("AAA", "BBB", "CCC", "DDD")):
    """Per ticker: a healthy Q1 stored in September and an empty Q2 stored in October; the first ticker also an empty 10-K."""
    rows = []
    for t in tickers:
        rows.append(stored_row(t, raw_filing("0000000001-26-000001", 1, "2026-03-31", "2026-05-01"), "2026-09-14T00:00:00Z", True))
        rows.append(stored_row(t, raw_filing("0000000001-26-000002", 2, "2026-06-30", "2026-07-30"), "2026-10-08T00:00:00Z", False))
    rows.append(stored_row(tickers[0], raw_filing("0000000001-26-000009", 0, "2026-03-31", "2026-05-20", form="10-K"), "2026-10-08T00:00:00Z", False))
    store = tmp_path / "store"
    store.mkdir()
    HS.write_shard(store / "finnhub-2026.jsonl.gz", rows)
    return store


def served(*filings):
    return "HTTP_200", json.dumps({"data": list(filings), "symbol": "X"})


def fetch_for(scenario):
    q1 = raw_filing("0000000001-26-000001", 1, "2026-03-31", "2026-05-01")
    q2 = {"omitted": raw_filing("0000000001-26-000002", 2, "2026-06-30", "2026-07-30", bs="empty"),
          "absent": raw_filing("0000000001-26-000002", 2, "2026-06-30", "2026-07-30", bs="none"),
          "moved": raw_filing("0000000001-26-000002", 2, "2026-06-30", "2026-07-30", bs="moved"),
          "completed": raw_filing("0000000001-26-000002", 2, "2026-06-30", "2026-07-30", bs="yes")}
    if scenario == "endpoint":
        q1 = raw_filing("0000000001-26-000001", 1, "2026-03-31", "2026-05-01", bs="empty")
        q2["endpoint"] = raw_filing("0000000001-26-000002", 2, "2026-06-30", "2026-07-30", bs="empty")

    def fetch(key, ticker, freq, start, end, timeout=45):
        return served(q1, q2[scenario]) if freq == FF.QUARTERLY else served()
    return fetch


@pytest.mark.parametrize("scenario,verdict,category", [
    ("omitted", "VENDOR_OMITS_BALANCE_SHEET_FOR_NEWLY_SERVED_FILINGS_ONLY", "VENDOR_OMITTED"),
    ("absent", "VENDOR_OMITS_BALANCE_SHEET_FOR_NEWLY_SERVED_FILINGS_ONLY", "VENDOR_OMITTED"),
    ("endpoint", "VENDOR_OMITS_BALANCE_SHEET_ENDPOINT_WIDE", "VENDOR_OMITTED"),
    ("moved", "BALANCE_SHEET_FOUND_UNDER_ANOTHER_KEY", "VENDOR_MOVED_FIELD"),
    ("completed", "SERVED_NOW_COMPLETION_AVAILABLE", "VENDOR_LATER_COMPLETED"),
])
def test_each_outcome_is_reachable_from_controlled_responses_and_names_one_repair_path(tmp_path, scenario, verdict, category):
    store = make_store(tmp_path)
    plan = PROBE.select_plan(PROBE.load_stored(store), quarterly=2, annual=0)
    report, raw = PROBE.run(SECRET, store, plan, 12, "2026-10-12", fetch=fetch_for(scenario), pace=0, store_commit="abc")
    assert report["verdict"] == verdict and report["category"] == category and report["mode"] == "LIVE" and report["storeCommit"] == "abc"
    assert report["nextRepairPath"] == PROBE.NEXT_REPAIR_PATH[verdict] and len(raw) == report["calls"] == 2
    assert SECRET not in json.dumps(report) and SECRET not in json.dumps(raw)


def test_a_thin_or_interrupted_run_is_insufficient_evidence_never_a_guess(tmp_path):
    store = make_store(tmp_path)
    plan = PROBE.select_plan(PROBE.load_stored(store), quarterly=3, annual=0)

    def refused(key, ticker, freq, start, end, timeout=45):
        return "HTTP_429", '{"error":"API limit reached"}'
    report, _ = PROBE.run(SECRET, store, plan, 12, "2026-10-12", fetch=refused, pace=0)
    assert report["calls"] == 1 and report["stopped"] == "STOPPED_ON_HTTP_429_RATE_LIMIT"          # one refusal ends the run: no more requests
    assert report["verdict"] == PROBE.INCONCLUSIVE and report["category"] == "INSUFFICIENT_EVIDENCE"

    def junk(key, ticker, freq, start, end, timeout=45):
        return "HTTP_200", "<html>not json</html>"
    report, _ = PROBE.run(SECRET, store, plan, 12, "2026-10-12", fetch=junk, pace=0)
    assert report["stopped"] == "STOPPED_ON_NON_JSON" and report["category"] == "INSUFFICIENT_EVIDENCE"

    def unrelated(key, ticker, freq, start, end, timeout=45):
        return served(raw_filing("0000000009-26-000001", 1, "2026-03-31", "2026-05-01"))           # nothing stored to pair with
    report, _ = PROBE.run(SECRET, store, plan, 12, "2026-10-12", fetch=unrelated, pace=0)
    assert report["category"] == "INSUFFICIENT_EVIDENCE" and report["nextRepairPath"].startswith("INSUFFICIENT_EVIDENCE")


def test_every_verdict_has_a_category_and_a_next_repair_path():
    assert set(PROBE.CATEGORY) == set(PROBE.NEXT_REPAIR_PATH) == {PROBE.SERVED_NOW, PROBE.KEY_MOVED, PROBE.NEW_ONLY, PROBE.ENDPOINT_WIDE, PROBE.INCONCLUSIVE}
    assert "S2_SUPPLEMENT" in PROBE.NEXT_REPAIR_PATH[PROBE.SERVED_NOW] and "S2_SUPPLEMENT" in PROBE.NEXT_REPAIR_PATH[PROBE.KEY_MOVED]
    assert "S3_BLOCKED_SOURCE" in PROBE.NEXT_REPAIR_PATH[PROBE.NEW_ONLY] and "S3_BLOCKED_SOURCE" in PROBE.NEXT_REPAIR_PATH[PROBE.ENDPOINT_WIDE]
    assert "do not start S2" in PROBE.NEXT_REPAIR_PATH[PROBE.INCONCLUSIVE]


def test_selection_pairs_an_empty_filing_with_a_healthy_one_and_is_deterministic(tmp_path):
    stored = PROBE.load_stored(make_store(tmp_path))
    plan = PROBE.select_plan(stored)
    assert plan == PROBE.select_plan(dict(reversed(list(stored.items()))))                          # independent of input order
    assert [p["freq"] for p in plan].count("annual") == 1 and plan[-1]["freq"] == "annual"          # only AAA has an empty 10-K
    assert {p["ticker"] for p in plan if p["freq"] == "quarterly"} == {"AAA", "BBB", "CCC", "DDD"}
    assert all(p["from"] == ("2025-01-01" if p["freq"] == "annual" else "2026-01-01") for p in plan)
    assert PROBE.select_plan({}) == []


def test_plan_only_needs_no_key_makes_no_request_and_leaves_a_pending_verdict(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.setattr(PROBE, "fetch_raw", lambda *a, **k: (_ for _ in ()).throw(AssertionError("a request was made")))
    out, raw = tmp_path / "plan.json", tmp_path / "raw.gz"
    assert PROBE.main(["--store", str(store), "--max-calls", "0", "--output", str(out), "--raw-out", str(raw), "--today", "2026-10-12",
                       "--store-commit", "deadbeef"]) == 0
    report = json.loads(out.read_text())
    assert report["mode"] == "PLAN_ONLY" and report["calls"] == 0 and report["verdict"] == "PENDING_NO_CALLS_MADE"
    assert report["category"] == "PENDING_OWNER_DISPATCH" and report["nextRepairPath"] is None and report["storeCommit"] == "deadbeef"
    assert report["planned"] and gzip.decompress(raw.read_bytes()) == b""


def test_a_live_run_without_a_key_stops_and_a_budget_above_the_ceiling_is_refused(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    args = ["--store", str(store), "--output", str(tmp_path / "o.json"), "--raw-out", str(tmp_path / "r.gz")]
    assert PROBE.main(args) == 1
    monkeypatch.setenv("FINNHUB_API_KEY", SECRET)
    assert PROBE.main(args + ["--max-calls", "21"]) == 2 and PROBE.main(args + ["--max-calls", "-1"]) == 2
    assert not (tmp_path / "o.json").exists() and PROBE.HARD_CEILING == 20


def test_the_default_budget_is_twelve_and_the_ceiling_caps_a_larger_plan(tmp_path):
    store = PROBE.load_stored(make_store(tmp_path))
    plan = PROBE.plan_from_tickers([f"T{i:02d}" for i in range(40)])
    calls = []

    def fetch(key, ticker, freq, start, end, timeout=45):
        calls.append(ticker)
        return served()
    PROBE.run(SECRET, store, plan, 99, "2026-10-12", fetch=fetch, pace=0)
    assert len(calls) == PROBE.HARD_CEILING
    calls.clear()
    PROBE.run(SECRET, store, plan, 12, "2026-10-12", fetch=fetch, pace=0)
    assert len(calls) == 12
    assert re.search(r'"--max-calls", type=int, default=12', (ROOT / "scripts/probe_finnhub_balance_sheet.py").read_text())


def test_a_key_that_reaches_an_output_aborts_the_write(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    monkeypatch.setenv("FINNHUB_API_KEY", SECRET)

    def echoing(key, ticker, freq, start, end, timeout=45):
        return "HTTP_200", json.dumps({"data": [], "echo": key})
    monkeypatch.setattr(PROBE, "fetch_raw", echoing)
    monkeypatch.setattr(PROBE.time, "sleep", lambda s: None)
    out, raw = tmp_path / "o.json", tmp_path / "r.gz"
    with pytest.raises(SystemExit, match="KEY_FOUND_IN_OUTPUT"):
        PROBE.main(["--store", str(store), "--max-calls", "1", "--output", str(out), "--raw-out", str(raw), "--today", "2026-10-12"])
    assert not out.exists() and not raw.exists()


def test_the_probe_writes_nothing_into_the_store_it_reads(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    before = {p.name: p.read_bytes() for p in store.iterdir()}
    monkeypatch.setenv("FINNHUB_API_KEY", SECRET)
    monkeypatch.setattr(PROBE, "fetch_raw", fetch_for("completed"))
    monkeypatch.setattr(PROBE.time, "sleep", lambda s: None)
    assert PROBE.main(["--store", str(store), "--max-calls", "4", "--output", str(tmp_path / "o.json"), "--raw-out", str(tmp_path / "r.gz")]) == 0
    assert {p.name: p.read_bytes() for p in store.iterdir()} == before
    assert json.loads((tmp_path / "o.json").read_text())["category"] == "VENDOR_LATER_COMPLETED"


# ---------------------------------------------------------------- the committed plan and the owner instructions
def test_the_committed_plan_is_a_pending_plan_only_report():
    report = json.loads(PLAN_JSON.read_text())
    assert report["mode"] == "PLAN_ONLY" and report["calls"] == 0 and report["callBudget"] == 0 and report["hardCeiling"] == 20
    assert report["verdict"] == "PENDING_NO_CALLS_MADE" and report["category"] == "PENDING_OWNER_DISPATCH" and report["perCall"] == []
    assert report["storeCommit"] == "4ddeb87bac078f2681fa83b1225111896edb319b" and len(report["planned"]) == 12 <= 20
    assert [p["freq"] for p in report["planned"]].count("annual") == 2
    assert "SECRET" not in json.dumps(report).upper()


def test_the_korean_instructions_state_the_pending_status_and_every_repair_path():
    text = DOC.read_text(encoding="utf-8")
    for needle in ("PENDING_OWNER_DISPATCH", "finnhub-bs-probe", "max_calls", "VENDOR_OMITTED", "VENDOR_MOVED_FIELD", "VENDOR_LATER_COMPLETED",
                   "INSUFFICIENT_EVIDENCE", "S2_SUPPLEMENT", "S3_BLOCKED_SOURCE", "병합"):
        assert needle in text, needle
