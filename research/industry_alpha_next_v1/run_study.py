"""CLI for industry-alpha-kr-next-v1.

    python -m research.industry_alpha_next_v1.run_study synthetic          # invented world, full pipeline
    python -m research.industry_alpha_next_v1.run_study verify-inputs      # real pinned inputs, LABEL-FREE counts only
    python -m research.industry_alpha_next_v1.run_study execute --authorization <file>   # REFUSED unless authorized

`execute` order: authorization (spec, code, input identity, every owner decision, merged main in Actions) -> inputs
verified against pins -> label-free panel -> intended cohort digest -> DURABLE ONE-SHOT LOCK (git ref) -> marker ->
forward returns -> slots -> Holm -> result. A failure before the lock spends nothing; after it the study is consumed.
No flag, environment variable or synthetic path converts into an authorized run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import kr_factor_anatomy as A
from pipeline import kr_factor_anatomy_execution as AE
from pipeline import kr_industry_anatomy as I
from pipeline import replay_calendar as RC

from . import contracts as C
from . import evaluate as E
from . import input_check as IC
from . import inputs as IN
from . import panel as P
from . import study as S

HERE = Path(__file__).resolve().parent
RESULT_PATH = HERE / "result" / "industry-alpha-kr-next-v1-result.json"
LOCK_PREFIX = "refs/tags/industry-alpha-kr-next-v1-execution-lock"


@dataclass
class Counters:
    forwardReturnCalls: int = 0


# --------------------------------------------------------------------------- #
# Authorization
# --------------------------------------------------------------------------- #
def validate_owner_decisions(decisions):
    if not isinstance(decisions, dict) or any(decisions.get(k) is None for k in S.OWNER_DECISIONS):
        raise PermissionError("OWNER_DECISION_MISSING")
    if decisions["krHistoryClosureException"] is not True or decisions["classifiedOnlyEstimand"] is not True:
        raise PermissionError("KR_HISTORY_EXCEPTION_AND_CONDITIONED_ESTIMAND_MUST_BE_EXPLICITLY_ACCEPTED")
    if decisions["admissionRule"] not in ("BLOCK_SCOPED", "STUDY_WIDE"):
        raise PermissionError("INVALID_ADMISSION_RULE")
    m = decisions["minimumCompleteBlocks"]
    if isinstance(m, bool) or not isinstance(m, int) or m < 1:
        raise PermissionError("INVALID_MINIMUM_COMPLETE_BLOCKS")
    if not isinstance(decisions["sequentialGate"], bool):
        raise PermissionError("INVALID_SEQUENTIAL_GATE")
    if decisions["supportRule"] != "AS_REGISTERED":
        # Any other support rule is a change to study.py (new spec hash) made BEFORE authorization, never a flag.
        raise PermissionError("INVALID_SUPPORT_RULE")


def authorize(path, env=None, root=IN.ROOT):
    """Returns (OutcomePermit, decisions). Every check raises; there is no partial authorization."""
    env = os.environ if env is None else env
    design = json.loads((HERE / "design.json").read_text())
    if design.get("executionEnabled") is not True:
        raise PermissionError("EXECUTION_DISABLED_IN_DESIGN")
    if env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REF") != "refs/heads/main":
        raise PermissionError("EXECUTION_ONLY_FROM_MERGED_MAIN_IN_ACTIONS")
    if RESULT_PATH.exists():
        raise PermissionError("RESULT_ALREADY_COMMITTED")
    auth = json.loads(Path(path).read_text())
    if auth.get("studyId") != S.STUDY_ID:
        raise PermissionError("AUTHORIZATION_FOR_ANOTHER_STUDY")
    if auth.get("specSha256") != S.spec_sha256():
        raise PermissionError("SPEC_CHANGED_SINCE_AUTHORIZATION")
    if auth.get("codeSha256") != S.code_sha256():
        raise PermissionError("CODE_CHANGED_SINCE_AUTHORIZATION")
    if auth.get("inputIdentitySha256") != IN.identity(root)["sha256"]:
        raise PermissionError("INPUT_IDENTITY_CHANGED_SINCE_AUTHORIZATION")
    if not isinstance(auth.get("ownerLogin"), str) or not auth["ownerLogin"]:
        raise PermissionError("OWNER_IDENTITY_REQUIRED")
    validate_owner_decisions(auth.get("ownerDecisions"))
    return P.OutcomePermit(scope="AUTHORIZED_HISTORICAL", specSha256=auth["specSha256"]), auth["ownerDecisions"]


def github_api(method, path, payload=None, env=None):
    env = os.environ if env is None else env
    req = urllib.request.Request(f"https://api.github.com/repos/{env['GITHUB_REPOSITORY']}{path}", method=method,
                                 data=json.dumps(payload).encode() if payload else None,
                                 headers={"Authorization": f"Bearer {env['GITHUB_TOKEN']}",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read() or b"{}")


def claim_lock(sha, env=None, api=github_api):
    """Atomic POST of the study lock ref at the dispatched commit. ANY existing ref under the prefix refuses."""
    status, body = api("GET", "/git/matching-refs/" + LOCK_PREFIX[len("refs/"):], None, env)
    if status != 200:
        raise RuntimeError("LOCK_STATE_UNVERIFIABLE")
    if body:
        raise PermissionError("STUDY_ALREADY_CONSUMED")
    status, _ = api("POST", "/git/refs", {"ref": LOCK_PREFIX, "sha": sha}, env)
    if status != 201:
        raise PermissionError("LOCK_NOT_ACQUIRED")
    return {"ref": LOCK_PREFIX, "sha": sha}


# --------------------------------------------------------------------------- #
# Outcomes (permit required)
# --------------------------------------------------------------------------- #
def forward_table(prices, schedule, sessions, permit, counters, completeness, through):
    """{(date, h): {ticker: (stockReturn, benchmarkReturn, status)}} with the sealed endpoint rule and the sealed
    terminal/distribution eligibility: a MATURED pair whose evidence is ineligible becomes UNRESOLVED, never a number."""
    P.require_permit(permit)
    attach = AE.sealed_v1_function("attach_eligibility")
    table = {}
    for h in S.HORIZONS:
        for date, tickers in schedule.items():
            recs = []
            for t in tickers:
                counters.forwardReturnCalls += 1
                recs.append(A.endpoint_returns(sessions, prices, S.BENCHMARK, t, date, h, through))
            frame = pd.DataFrame(recs)
            elig = attach(pd.DataFrame({"ticker": tickers, "outcomeEndDate": frame.exitDate}), prices, completeness)
            status = frame.status.where(~(frame.status.eq("MATURED") & ~elig.eligibilityStatus.eq("ELIGIBLE")),
                                        "UNRESOLVED_TERMINAL_OR_DISTRIBUTION_EVIDENCE")
            table[(date, h)] = {t: (r, b, s) for t, r, b, s in zip(tickers, frame.stockReturn.astype(float),
                                                                  frame.benchmarkReturn.astype(float), status)}
    return table


def apply_admission(frame, decisions, horizon):
    """Owner-chosen admission on the intended industry-date blocks (cap-weighted primary target)."""
    total = len(frame)
    resolved = int(frame["cwStatus"].eq("MATURED").sum())
    if decisions["admissionRule"] == "STUDY_WIDE" and resolved < total:
        return None, {"rule": "STUDY_WIDE", "intendedBlocks": total, "resolvedBlocks": resolved, "status": "BLOCKED"}
    if resolved < decisions["minimumCompleteBlocks"]:
        return None, {"rule": decisions["admissionRule"], "intendedBlocks": total, "resolvedBlocks": resolved,
                      "status": "BLOCKED_BELOW_MINIMUM_COMPLETE_BLOCKS"}
    return frame, {"rule": decisions["admissionRule"], "intendedBlocks": total, "resolvedBlocks": resolved, "status": "ADMITTED"}


def analyse(rows, targets_by_h, sessions, decisions):
    """All KR slots, diagnostics and the 36-slot family from a label-free panel plus targets (both horizons)."""
    out, slots = {}, {}
    for h in S.HORIZONS:
        frame = rows.merge(targets_by_h[h], on=["date", "industry"], how="left")
        admitted, admission = apply_admission(frame, decisions, h)
        if admitted is None:
            res = {f"KR_H{h}_{b}": {"status": admission["status"], "p": 1.0} for b in
                   list(S.BLOCKS) + ["MARKET_CONTEXT", "LEADER_DIFFUSION"]}
        else:
            res = E.run_kr_horizon(admitted, sessions, h, sequential_gate=decisions["sequentialGate"])
        slots.update(res)
        diag = {}
        if admitted is not None:
            diag["equalWeightLens"] = {b: E.contrast(admitted, *E.h1_columns(b), "ewRelative", "ewStatus", sessions, h)
                                       for b in S.BLOCKS}
            diag["anticipationWithinPriorMomTerciles"] = {b: E.anticipation_split(admitted, b, sessions, h)
                                                          for b in ("PROFIT", "CASH")}
        out[f"H{h}"] = {"admission": admission, "diagnostics": diag}
    return {"slots": slots, "family": E.family(slots), "byHorizon": out}


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #
def load_real(root=IN.ROOT):
    membership = IN.load_membership(root)
    caps = IN.load_universe(root)
    prices, through = IN.load_prices(root)
    accounting = IN.load_accounting(root)
    return {"membership": membership, "caps": caps, "prices": prices, "accounting": accounting,
            "marketAdapter": IN.GitMarket(caps, prices), "through": through}


def verify_inputs(loaded=None, root=IN.ROOT):
    loaded = load_real(root) if loaded is None else loaded
    if loaded["through"] != S.DEVELOPMENT_CUTOFF:
        raise ValueError("REPLAY_THROUGH_DIFFERS_FROM_CUTOFF")
    report = IC.run(loaded, loaded["through"])
    report["inputIdentitySha256"] = IN.identity(root)["sha256"]
    report["findings"] = IC.structural_findings(report)
    I.assert_no_forbidden_keys(report)
    return report


def execute(authorization, env=None, api=github_api, root=IN.ROOT):
    permit, decisions = authorize(authorization, env, root)
    env = os.environ if env is None else env
    counters = Counters()
    loaded = load_real(root)
    built = IC.build_label_free(loaded)
    cohort_digest = C.intended_digest(P.intended_blocks(built["cohorts"]))
    completeness = {row["code"] + ".KS": row.get("completeness") for row in
                    json.loads((Path(root) / S.INPUT_POLICY["terminalFoundation"]).read_text()).get("securities", [])}
    lock = claim_lock(env["GITHUB_SHA"], env, api)
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    (RESULT_PATH.parent / "execution-started.json").write_text(json.dumps(
        {"studyId": S.STUDY_ID, "lock": lock, "specSha256": S.spec_sha256(), "intendedCohortSha256": cohort_digest,
         "inputIdentitySha256": IN.identity(root)["sha256"], "counters": asdict(counters)}, indent=1, sort_keys=True))
    forward = forward_table(loaded["prices"], built["schedule"], built["sessions"], permit, counters, completeness,
                            loaded["through"])
    if C.intended_digest(P.intended_blocks(built["cohorts"])) != cohort_digest:
        raise RuntimeError("INTENDED_COHORT_CHANGED_AFTER_LOCK")
    targets = {h: P.industry_and_laggard_targets(built["cohorts"], built["splits"], forward, h, permit) for h in S.HORIZONS}
    result = {"studyId": S.STUDY_ID, "evidenceClass": S.EVIDENCE_CLASS, "specSha256": S.spec_sha256(),
              "intendedCohortSha256": cohort_digest, "ownerDecisions": decisions,
              "analysis": analyse(built["rows"], targets, built["sessions"], decisions), "counters": asdict(counters)}
    I.assert_no_forbidden_keys(result)
    RESULT_PATH.write_text(json.dumps(result, indent=1, sort_keys=True, default=_json))
    return result


def _json(x):
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    if isinstance(x, (set, tuple)):
        return list(x)
    raise TypeError(type(x).__name__)


def synthetic_world(seed=7, months=150, industries=10, per=8, signal=0.0, start="2012-01-31"):
    """Invented industry-date panel + targets: every column the evaluator reads, nothing real. `signal` plants a
    MOM effect so tests can check the pipeline both finds a planted edge and stays quiet without one."""
    rng = np.random.default_rng(seed)
    dates = [str(d.date()) for d in pd.date_range(start, periods=months, freq="ME")]
    rows, tg = [], []
    for d in dates:
        for g in range(industries):
            f = {c: rng.normal() for cols in S.BLOCKS.values() for c in cols}
            f |= {c: rng.normal() for c in S.NUISANCE + S.MARKET_CONTEXT + S.DIFFUSION_BASE + S.DIFFUSION_SIGNAL}
            rows.append({"date": d, "industry": f"G{g}", "n": per, **f})
            y = signal * f["REL_MOM_126"] + rng.normal(scale=1.0)
            tg.append({"date": d, "industry": f"G{g}", "cwRelative": y, "cwStatus": "MATURED", "ewRelative": y,
                       "ewStatus": "MATURED", "laggardRelative": y, "laggardStatus": "MATURED"})
    return pd.DataFrame(rows), pd.DataFrame(tg), RC.sessions("2001-01-01", "2026-12-31", "KR")


def synthetic(signal=0.0):
    rows, tg, sessions = synthetic_world(signal=signal, months=260, start="2003-01-31")
    decisions = {"krHistoryClosureException": True, "classifiedOnlyEstimand": True, "admissionRule": "BLOCK_SCOPED",
                 "minimumCompleteBlocks": 1, "sequentialGate": True, "supportRule": "AS_REGISTERED"}
    return {"evidenceClass": "SYNTHETIC_FIXTURE", "analysis": analyse(rows, {h: tg for h in S.HORIZONS}, sessions, decisions)}


def authorization_draft(root=IN.ROOT):
    """The exact hashes an owner would sign. Every decision is null: a draft is NOT an authorization."""
    return {"studyId": S.STUDY_ID, "specSha256": S.spec_sha256(), "codeSha256": S.code_sha256(),
            "inputIdentitySha256": IN.identity(root)["sha256"], "ownerLogin": None,
            "ownerDecisions": {k: None for k in S.OWNER_DECISIONS},
            "note": "DRAFT_NOT_AUTHORIZATION: commit only after design.json executionEnabled=true is in the same tree"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    sub.add_parser("synthetic")
    v = sub.add_parser("verify-inputs")
    v.add_argument("--output")
    x = sub.add_parser("execute")
    x.add_argument("--authorization", required=True)
    sub.add_parser("authorization-draft")
    args = ap.parse_args(argv)
    if args.mode == "synthetic":
        out = synthetic()
    elif args.mode == "authorization-draft":
        out = authorization_draft()
    elif args.mode == "verify-inputs":
        out = verify_inputs()
        if args.output:
            Path(args.output).write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False, default=_json) + "\n")
    else:
        out = execute(args.authorization)
    json.dump(out, sys.stdout, indent=1, sort_keys=True, ensure_ascii=False, default=_json)
    print()


if __name__ == "__main__":
    main()
