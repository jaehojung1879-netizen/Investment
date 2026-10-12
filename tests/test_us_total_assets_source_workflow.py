"""The owner-gated total-assets source probe job in fundamentals.yml: who selects it, who holds which key, and what its gate decides.

The gate step's REAL shell script is extracted from the workflow text and executed, so a change to the workflow cannot pass these tests by
editing a copy of its logic. The job is read as text (pyyaml is not a runtime dependency).
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/fundamentals.yml"
JOB = "us-total-assets-source-probe"
CONTACT = "ops@investor-diagnostics.test"


def text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def job_block(name: str = JOB) -> str:
    body = text()
    start = body.index(f"\n  {name}:\n") + 1
    nxt = re.search(r"\n  [a-z][a-z-]*:\n", body[start + 3:])
    block = body[start:start + 3 + nxt.start()] if nxt else body[start:]
    return block.split("\n  # kr-accounting-coverage-repair-v1", 1)[0]       # the next job's header comment is not this job's


def steps(block: str) -> list[str]:
    parts = re.split(r"\n      - name: ", block)
    return ["      - name: " + p for p in parts[1:]]


def step(name_prefix: str) -> str:
    return next(s for s in steps(job_block()) if s.startswith("      - name: " + name_prefix))


def run_script(step_text: str) -> str:
    match = re.search(r"        run: \|\n((?:          .*\n?|\n)+)", step_text)
    assert match, "step has no run block"
    return "\n".join(line[10:] if line.startswith("          ") else line for line in match.group(1).split("\n"))


def gate(tmp_path, *, max_calls="", sources="all", contact="", event="workflow_dispatch", ref="refs/heads/main"):
    out = tmp_path / "gh_output"
    out.write_text("")
    env = {**os.environ, "MAX_CALLS": max_calls, "PROBE_SOURCES": sources, "SEC_CONTACT": contact, "EVENT": event, "REF": ref, "GITHUB_OUTPUT": str(out)}
    done = subprocess.run(["bash", "-c", run_script(step("Decide the mode"))], env=env, cwd=ROOT, capture_output=True, text=True)
    outputs = dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)
    return done, outputs


def selects(region: str, *, target="auto", event="workflow_dispatch") -> set[str]:
    from_text = {"kr": "github.event_name == 'schedule' || ((inputs.region == 'both' || inputs.region == 'kr') && !startsWith(inputs.target, 'raw-'))",
                 "us": "github.event_name == 'schedule' || ((inputs.region == 'both' || inputs.region == 'us') && !startsWith(inputs.target, 'raw-'))"}
    chosen = set()
    if event == "workflow_dispatch":
        if region in ("both", "kr") and not target.startswith("raw-"):
            chosen.add("kr")
        if region in ("both", "us") and not target.startswith("raw-"):
            chosen.add("us")
        assert all(f"if: {expr}" in text() for expr in from_text.values())
        if region == "total-assets-source-probe" and target == "auto":
            assert "    if: github.event_name == 'workflow_dispatch' && inputs.region == 'total-assets-source-probe' && inputs.target == 'auto'" in job_block()
            chosen.add(JOB)
    return chosen


def test_only_its_own_region_selects_the_job_and_no_collector_starts_with_it():
    assert selects("total-assets-source-probe") == {JOB}
    assert selects("both") == {"kr", "us"} and selects("finnhub-bs-probe") == set()
    assert selects("total-assets-source-probe", target="raw-statements") == set()
    assert selects("total-assets-source-probe", event="schedule") == set()
    assert 'options: ["both", "kr", "us", "finnhub-bs-probe", "total-assets-source-probe"]' in text() and 'cron: "40 3 * * *"' in text()


def test_the_job_is_read_only_schedules_nothing_and_never_touches_signal_history():
    job = job_block()
    assert "permissions:\n      contents: read" in job and "contents: write" not in job
    assert job.count("persist-credentials: false") == 1 and "actions/checkout" in job
    for forbidden in ("git push", "git commit", "git add", "signal-history", "gh api", "gh workflow", "cron:", "schedule", "pull-requests"):
        assert forbidden not in job, forbidden
    assert "write_shard" not in job and "ledger/fundamentals" not in job


def test_each_vendor_key_is_named_by_exactly_one_step_and_no_step_names_two():
    job = job_block()
    assert sorted(re.findall(r"secrets\.([A-Z_]+)", job)) == ["FINNHUB", "FMP", "MASSIVE"]
    for secret, env_name, label in (("FINNHUB", "FINNHUB_API_KEY", "Finnhub standardized"), ("MASSIVE", "MASSIVE_API_KEY", "Massive v1"),
                                    ("FMP", "FMP_API_KEY", "FMP stable")):
        holders = [s for s in steps(job) if f"secrets.{secret}" in s]
        assert len(holders) == 1 and holders[0].startswith(f"      - name: {label}")
        assert f"{env_name}: ${{{{ secrets.{secret} }}}}" in holders[0]
        assert sum("secrets." in line for line in holders[0].split("\n")) == 1
    for s in steps(job):
        if "secrets." in s:
            assert "steps.gate.outputs.vendors_run == 'true'" in s, "a key step runs only when the gate validated a live main dispatch"
        else:
            assert "KEY" not in s.split("run:")[0] or "SEC_CONTACT" in s
    assert "secrets." not in step("SEC data.sec.gov") and "secrets." not in step("Decide") and "secrets." not in step("Plan only")
    assert "secrets." not in step("Merge") and "secrets." not in step("Summary")


def test_run_scripts_never_interpolate_expressions_and_never_print_a_value():
    for s in steps(job_block()):
        if "        run: |" in s:
            assert "${{" not in run_script(s), s.split("\n")[0]
    for name in ("Finnhub", "Massive", "FMP"):
        script = run_script(step(name))
        assert "present (value never printed)" in script and "echo \"$" not in script
        for env_name in ("FINNHUB_API_KEY", "MASSIVE_API_KEY", "FMP_API_KEY"):
            assert not re.search(rf"echo[^\n]*\${{?{env_name}(?!:-)", script) and "set -x" not in script


def test_the_report_artifact_holds_verdicts_only():
    upload = step("Upload the report")
    assert "us-total-assets-source-probe-report" in upload and "retention-days: 90" in upload and "if: always()" in upload
    assert "raw" not in upload.lower()


# ---- the gate, executed -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("max_calls,calls,source", [("", "20", "default"), ("0", "0", "explicit"), ("1", "1", "explicit"), ("12", "12", "explicit"), ("20", "20", "explicit")])
def test_blank_zero_and_a_number_are_three_different_decisions(tmp_path, max_calls, calls, source):
    done, out = gate(tmp_path, max_calls=max_calls, contact=CONTACT)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (out["calls"], out["source"]) == (calls, source)
    assert out["mode"] == ("plan" if calls == "0" else "live") and out["inject"] == ("false" if calls == "0" else "true")
    assert out["reason"] == ("PLAN_ONLY_REQUESTED" if calls == "0" else "LIVE_ON_MAIN_DISPATCH")


@pytest.mark.parametrize("bad", ["00", "01", "21", "-1", "1.5", " 5", "5 ", "abc", "0x10", "1e1", "２", "12;echo", "$(id)"])
def test_invalid_budgets_stop_at_the_gate_without_echoing_the_input(tmp_path, bad):
    done, out = gate(tmp_path, max_calls=bad, contact=CONTACT)
    assert done.returncode == 2 and out == {}
    assert done.stdout.strip().startswith("::error title=max_calls::") and bad.strip() not in done.stdout.replace("1-20", "").replace("0 (plan", "") or bad == "0x10"


@pytest.mark.parametrize("bad", ["", "ALL", "both", "finnhub", "all,sec", "sec; true"])
def test_unknown_source_choices_stop_at_the_gate(tmp_path, bad):
    done, out = gate(tmp_path, sources=bad, contact=CONTACT)
    assert done.returncode == 2 and out == {} and "probe_sources" in done.stdout


@pytest.mark.parametrize("ref,event", [("refs/heads/claude/some-branch", "workflow_dispatch"), ("refs/pull/1/merge", "workflow_dispatch"), ("refs/heads/main", "schedule"),
                                       ("refs/heads/main2", "workflow_dispatch"), ("refs/tags/main", "workflow_dispatch")])
def test_a_live_request_off_main_withholds_every_key_and_the_sec_requests(tmp_path, ref, event):
    done, out = gate(tmp_path, max_calls="12", contact=CONTACT, ref=ref, event=event)
    assert done.returncode == 0
    assert (out["mode"], out["inject"], out["reason"], out["sec_run"], out["vendors_run"]) == ("live", "false", "LIVE_WITHHELD_NOT_MAIN_DISPATCH", "false", "false")


def test_sec_requests_need_a_contact_the_owner_typed(tmp_path):
    for contact, note in (("", "SEC_CONTACT_MISSING"), ("nope", "SEC_CONTACT_NOT_AN_EMAIL_ADDRESS"),
                          ("me@users.noreply.github.com", "SEC_CONTACT_IS_A_PLACEHOLDER_OR_NOREPLY_ADDRESS")):
        done, out = gate(tmp_path, max_calls="5", sources="sec", contact=contact)
        assert done.returncode == 0 and out["sec_run"] == "false" and out["sec_note"] == note and out["vendors_run"] == "false"
    done, out = gate(tmp_path, max_calls="5", sources="sec", contact=CONTACT)
    assert out["sec_run"] == "true" and out["sec_note"] == "CONTACT_SUPPLIED" and out["vendors_run"] == "false"
    assert CONTACT not in done.stdout, "the contact is used, not echoed into the log"


def test_vendors_only_never_runs_sec_and_sec_only_never_runs_vendors(tmp_path):
    _, vendors = gate(tmp_path, max_calls="5", sources="vendors", contact=CONTACT)
    _, sec = gate(tmp_path, max_calls="5", sources="sec", contact=CONTACT)
    _, both = gate(tmp_path, max_calls="5", sources="all", contact=CONTACT)
    assert (vendors["sec_run"], vendors["vendors_run"]) == ("false", "true")
    assert (sec["sec_run"], sec["vendors_run"]) == ("true", "false")
    assert (both["sec_run"], both["vendors_run"]) == ("true", "true")
    _, plan = gate(tmp_path, max_calls="0", sources="all", contact=CONTACT)
    assert (plan["sec_run"], plan["vendors_run"], plan["inject"]) == ("false", "false", "false")


def test_exactly_one_of_plan_or_live_steps_per_decision():
    plan_if = re.search(r"^        if: (.*)$", step("Plan only"), re.M).group(1)
    assert plan_if == "steps.gate.outputs.inject != 'true'"
    live_conditions = [re.search(r"^        if: (.*)$", s, re.M).group(1) for s in steps(job_block()) if "scripts/probe_us_total_assets_sources.py --sources" in s and "Plan only" not in s]
    assert all("inject" not in c or "== 'true'" in c for c in live_conditions) and len(live_conditions) == 4
    assert {c.split("steps.gate.outputs.")[1].split(" ")[0] for c in live_conditions} == {"sec_run", "vendors_run"}


def test_the_ranking_script_flags_name_the_sample_and_the_ceiling():
    for s in steps(job_block()):
        if "--sources" in s and "--merge" not in s:
            script = run_script(s)
            assert "--max-calls" in script and "--output" in script
    assert "--max-calls 0" in run_script(step("Plan only"))
