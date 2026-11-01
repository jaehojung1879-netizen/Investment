"""Fail-closed source-bound runner. Default verifies code; no market value read.

Only --execute may access values, after owner-authenticated exact-hash approval
and atomic permanent GitHub ref. No history replay, acquisition or workflow call.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import engine  # noqa: E402

REPO = "jaehojung1879-netizen/Investment"
OWNER = "jaehojung1879-netizen"
STUDY = "EXP-C-RECOVERY-02"
LOCK = "research-locks/EXP-C-RECOVERY-02"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def api(endpoint, method="GET", payload=None):
    # Use configured gh authentication. Never print credentials or vendor data.
    command = ["gh", "api", endpoint, "--method", method]
    if payload is not None:
        command += ["--input", "-"]
    return json.loads(subprocess.check_output(command, input=None if payload is None else json.dumps(payload), text=True))


def freeze_identity():
    frozen = read_json(HERE / "FREEZE.json")
    for name, expected in frozen["files"].items():
        if sha(HERE / name) != expected:
            raise ValueError("CODE_OR_CONTRACT_CHANGED: " + name)
    return engine.digest(frozen)


def authorization(identity, comment, source_manifest_sha):
    # Trusted owner identity comes from GitHub, never from a caller JSON field.
    if comment.get("user", {}).get("login") != OWNER:
        raise ValueError("OWNER_IDENTITY_REQUIRED")
    expected = {"study": STUDY, "freeze_sha256": identity,
                "source_manifest_sha256": source_manifest_sha,
                "closure_exception": "C.7_AND_STOP_LIST_SINGLE_COMPARISON_ONLY",
                "outcome_exposed": True, "one_shot": True,
                "source_rights_accepted": True, "persistence_ready": True,
                "action": "AUTHORIZE_EXACT_HASH_HISTORICAL_EXECUTION"}
    # Raw JSON comment only: no loose keyword matching or implied authorization.
    actual = json.loads(comment["body"])
    if actual != {**expected, "code_commit": actual.get("code_commit")}:
        raise ValueError("EXACT_OWNER_AUTHORIZATION_MISMATCH")
    if actual["code_commit"] != git("rev-parse", "HEAD"):
        raise ValueError("OWNER_EXACT_HEAD_MISMATCH")
    if git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("DIRTY_CHECKOUT")
    return actual


def prepare_sources(repo_root, us_root, contract):
    """Read ONLY exact pinned normalized sources through sealed parser/modules."""
    import numpy as np
    import pandas as pd
    sys.path.insert(0, str(repo_root))
    from pipeline import kr_market_risk_anatomy as anatomy
    from pipeline import kr_market_risk_model as kr
    from pipeline import kr_market_risk_source_parse as parser
    from pipeline import rp1_c1_us_exposure as us

    def read(path):
        return anatomy.obs_series(parser.read_normalized(path.read_bytes()))

    source_root = repo_root / "data/kr-market-risk-anatomy-v1/sources"
    rates = {s: read(source_root / s / "normalized.csv") for s in ("FRED_DGS10", "FRED_DGS3MO", "FRED_VIXCLS")}
    spread = rates["FRED_DGS10"] - rates["FRED_DGS3MO"]
    panels = {}
    for region in ("KR", "US"):
        ref = source_root / "FDR_KS200/normalized.csv" if region == "KR" else us_root / "YAHOO_GSPC/normalized.csv"
        close = read(ref)
        end = contract["analysis_end"]
        # KR grid starts on the first retained KR session; US starts 1990-01-01.
        start = str(close.index.min().date()) if region == "KR" else us.GRID_START
        sessions = us.market_sessions(region, start, end)
        c = close.reindex(sessions)
        # No filled/spliced price path, and no date omitted to repair an outcome.
        # Warm-up gaps are allowed; common_rows records all affected decisions.
        if region == "KR":
            states = kr.layer_states(c, spread, rates["FRED_VIXCLS"], sessions)
            schedule = kr.decision_schedule(sessions, kr.EVALUATION_START, end)
        else:
            states = us.layer_states(c, spread, rates["FRED_VIXCLS"], sessions, "US")
            schedule = us.decision_schedule(sessions, us.EVALUATION_START, end, "US")
        targets = kr.candidate_targets(states, schedule, "C0")["target"]
        d = sessions.get_indexer(schedule["decisionDate"])
        e = sessions.get_indexer(schedule["executionDate"])
        selected = states.loc[schedule["decisionDate"], ["fast", "slow", "transition"]].to_numpy()
        rows, audit = engine.common_rows(c.to_numpy(), d, e, selected, targets, set(range(len(sessions))))
        panels[region] = {"close": np.asarray(c), "rows": rows, "audit": audit,
                          "date_ids": [str(pd.Timestamp(x).date()) for x in schedule["decisionDate"]]}
    return panels


def persist(path, obj):
    # Immutable receipts; caller must use a durable output filesystem.
    with Path(path).open("x") as stream:
        json.dump(obj, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        import os
        os.fsync(stream.fileno())


def runtime_gate():
    from importlib.metadata import version
    if sys.version_info[:2] != (3, 11):
        raise ValueError("PINNED_PYTHON_3_11_REQUIRED")
    for name, expected in {"numpy": "2.3.1", "pandas": "2.3.0", "exchange-calendars": "4.11.1",
                           "korean-lunar-calendar": "0.4.0"}.items():
        if version(name) != expected:
            raise ValueError("PINNED_RUNTIME_REQUIRED: " + name)


def source_gate(us_root):
    manifest = read_json(HERE / "SOURCES.json")
    for name, expected in manifest["repository_pins"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("SEALED_DEPENDENCY_CHANGED: " + name)
    # Restricted raw chart/normalized/audit remain in runner temporary storage.
    for name, expected in manifest["us_pins"].items():
        if sha(us_root / name) != expected:
            raise ValueError("US_FROZEN_SOURCE_MISSING_OR_CHANGED: " + name)
    return manifest


def execute(args):
    identity = freeze_identity()
    contract = read_json(HERE / "CONTRACT.json")
    if not args.approval_comment_id or not args.us_source_root or not args.output:
        raise ValueError("NOT_EXECUTED: exact-head owner comment, exact US source bundle and durable output required")
    comment = api(f"repos/{REPO}/issues/comments/{args.approval_comment_id}")
    approval = authorization(identity, comment, sha(HERE / "SOURCES.json"))
    # Approval must be in this new Draft PR, never in #312/#289 or another PR.
    pr = api(comment["issue_url"].split("api.github.com/", 1)[1].replace("/issues/", "/pulls/"))
    if pr["head"]["sha"] != approval["code_commit"] or not pr["draft"] or pr["base"]["ref"] != "main":
        raise ValueError("APPROVAL_MUST_BELONG_TO_EXACT_HEAD_DRAFT_PR")
    us_root, output = Path(args.us_source_root).resolve(), Path(args.output).resolve()
    if ROOT == output or ROOT in output.parents:
        raise ValueError("OUTPUT_MUST_BE_OUTSIDE_REPOSITORY")
    # Non-author exact-head audit is a hard pre-execution gate, not a self-review.
    reviews = api(f"repos/{REPO}/pulls/{pr['number']}/reviews?per_page=100")
    if not any(r["commit_id"] == approval["code_commit"] and r["state"] == "APPROVED"
               and r["user"]["login"] != pr["user"]["login"] for r in reviews):
        raise ValueError("INDEPENDENT_EXACT_HEAD_AUDIT_REQUIRED")
    runtime_gate()
    source_gate(us_root)
    output.mkdir(parents=True, exist_ok=False)
    persist(output / "preflight.json", {"freeze": identity, "approval": approval,
            "time": datetime.now(timezone.utc).isoformat(), "source_value_parses": 0})
    # Globally atomic permanent ref; any existing ref or API error STOPs. Never
    # delete it, retry a spent study, dispatch an old workflow or merge anything.
    api(f"repos/{REPO}/git/refs", "POST", {"ref": "refs/tags/" + LOCK, "sha": approval["code_commit"]})
    persist(output / "first-look.json", {"freeze": identity, "lock": LOCK, "status": "CONSUMED_BEFORE_VALUE_READ"})
    panels = prepare_sources(ROOT, us_root, contract)
    persist(output / "eligible-dates.json", {k: {"date_ids": p["date_ids"], "common_slots": [r["slot"] for r in p["rows"]],
            "missingness": p["audit"]} for k, p in panels.items()})
    support = {k: engine.preflight_support(p["rows"]) for k, p in panels.items()}
    persist(output / "support.json", support)
    if not all(v["admissible"] for v in support.values()):
        persist(output / "result.json", {"status": "POWER_BLOCKED_BEFORE_LABELS_OR_FIT",
                "verdict": "POWER_BLOCKED", "support": support, "actual_fit_test_n": {"KR": 0, "US": 0},
                "mse": None, "ci95": None, "p": None})
        print("POWER_BLOCKED: no labels constructed, no fits, study consumed; stop")
        return
    regions = {}
    for region, panel in panels.items():
        rows = engine.attach_labels(panel["close"], panel["rows"])
        regions[region] = engine.evaluate_region(rows, panel["audit"])
    result = {"status": "EXECUTED_EXPLORATORY", "pit": "APPROXIMATE_AVAILABILITY_NOT_PIT_EXACT",
              "freeze": identity, "regions": regions, **engine.joint_verdict(regions)}
    persist(output / "result.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "regions"}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--prepare", action="store_true", help="Read-only runtime/source hash checks; no values parsed or lock created")
    parser.add_argument("--approval-comment-id", type=int)
    parser.add_argument("--us-source-root")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        if args.execute and args.prepare:
            raise ValueError("PREPARE_AND_EXECUTE_ARE_EXCLUSIVE")
        if args.prepare:
            identity = freeze_identity()
            checks = {}
            try:
                runtime_gate()
                checks["runtime"] = "PASS"
            except (ValueError, ImportError) as exc:
                checks["runtime"] = str(exc)
            if args.us_source_root:
                try:
                    source_gate(Path(args.us_source_root))
                    checks["sources"] = "HASHES_MATCH_NOT_AUTHORIZATION"
                except (ValueError, OSError) as exc:
                    checks["sources"] = "SOURCE_BLOCKED: " + str(exc)
            else:
                checks["sources"] = "SOURCE_BLOCKED: original US bundle not supplied"
            print(json.dumps({"status": "EXECUTION_BLOCKED", "freeze": identity, "checks": checks,
                              "source_value_parses": 0, "locks_created": 0, "input_cohort_scan": "NOT_AUTHORIZED"}))
        elif args.execute:
            execute(args)
        else:
            print(json.dumps({"status": "NOT_EXECUTED", "freeze_sha256": freeze_identity(), "source_value_parses": 0,
                              "blocker": "Exact-head owner exception/authorization, independent audit and eligible source access required"}))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
