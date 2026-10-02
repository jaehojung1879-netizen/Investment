"""KR Top120 regime review v1 — spec identity, execution authorization and the (future) data assembly.

EXPLORATORY_POST_OUTCOME_REGIME_DIAGNOSTIC. Historical execution is NOT part of the change that adds this file: `verify`
touches no data and no outcome, and `execute` refuses before reading a byte unless the run is a `workflow_dispatch` on
merged `main`, at a commit where this exact spec is committed, over the sealed `kr-factor-anatomy-v1` result, naming the
exact raw artifact, with no committed result and no committed execution marker.

Lifecycle (decided now, so the study does not repeat the sealing complexity of its predecessors):

1. protocol PR merges;
2. a human dispatches `execute` once;
3. identities and readiness gates are proven BEFORE anything durable exists: a failed gate writes `gates-failed.json`,
   creates NO lock and spends nothing;
4. only then a DURABLE, EXCLUSIVE one-shot lock is created on GitHub: the fixed study-level git tag
   `refs/tags/kr-top120-regime-review-v1-execution-lock` and the identity tag `...-execution-lock-<specSha256>`, both at the
   dispatched main commit, created by atomic `POST /git/refs` (an existing ref answers 422 and execution refuses). ANY ref under
   the `...-execution-lock` prefix, for ANY spec SHA, consumes the whole study: editing the spec never reopens it. Tags are
   never updated, moved or deleted;
5. only after the lock is established and verified may any outcome be read. ANY failure after the lock permanently
   consumes v1: a later `execute` refuses whether or not a result artifact was ever emitted, kept or expired;
6. the result artifact is emitted (a verdict, including DATA_INSUFFICIENT, is a successful process);
7. a seal commits the artifact's exact bytes (and the human-readable `execution-started.json`) without rerunning anything;
   the committed result path or marker also makes `execute` refuse. Those files are provenance, NOT the enforcement.

Actions artifacts and their retention are never consulted by the lock. Every authorization and lock test builds its own
synthetic repository and fake GitHub API, so none depends on the real repository's lifecycle state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

from . import kr_factor_anatomy as A
from . import kr_factor_anatomy_execution as AE
from . import kr_model_portfolio_execution as X
from . import kr_top120_regime_review as R
from . import replay_calendar as RC

digest, file_hash, import_closure = X.digest, X.file_hash, X.import_closure
ROOT = Path(__file__).resolve().parents[1]
STUDY = "kr-top120-regime-review-v1"
SPEC_PATH = "research_specs/" + STUDY + ".json"
RESULT_PATH = "docs/results/" + STUDY + "-result.json"
MARKER_PATH = "docs/results/" + STUDY + "-execution-started.json"
SCIENTIFIC_STATUS = R.SCIENTIFIC_STATUS


@dataclass
class Counters:
    """Everything that reads an outcome increments one of these; `verify` and a failed gate must leave all at zero."""
    targetCalls: int = 0
    labelCalls: int = 0
    outcomeColumnCalls: int = 0
    analysisCalls: int = 0
    markerWrites: int = 0

    def zero(self):
        return all(v == 0 for v in asdict(self).values())


@dataclass(frozen=True)
class ExecutionPermit:
    specSha256: str
    token: object


_PERMIT_TOKEN = object()


def require_permit(permit):
    if not isinstance(permit, ExecutionPermit) or permit.token is not _PERMIT_TOKEN:
        raise ValueError("REGIME_REVIEW_OUTCOME_ACCESS_WITHOUT_PERMIT")
    return permit


# --------------------------------------------------------------------------- #
# Frozen identity
# --------------------------------------------------------------------------- #
def verify_predecessor(spec, root=ROOT):
    """The sealed kr-factor-anatomy-v1 result is exactly what this study was designed over. Pure file hashing."""
    root = Path(root)
    pin = spec["predecessor"]
    for key, rel in pin["files"].items():
        if file_hash(root / rel) != pin["sha256"][key]:
            raise ValueError("PREDECESSOR_IDENTITY_CHANGED: " + key)
    provenance = json.loads((root / pin["files"]["provenance"]).read_text())
    for key, wanted in (("artifactArchiveSha256", pin["artifactArchiveSha256"]), ("specSha256", pin["specSha256"]),
                        ("inputIdentitySha256", pin["rawInputIdentitySha256"]), ("scientificStatus", pin["scientificStatus"])):
        if provenance.get(key) != wanted:
            raise ValueError("PREDECESSOR_PROVENANCE_CHANGED: " + key)
    manifest = json.loads((root / pin["files"]["manifest"]).read_text())
    if (manifest.get("scientificStatus"), manifest.get("specSha256"), manifest.get("inputIdentitySha256")) != (
            pin["scientificStatus"], pin["specSha256"], pin["rawInputIdentitySha256"]):
        raise ValueError("PREDECESSOR_MANIFEST_CHANGED")
    sidecar = (root / "research_specs" / "kr-factor-anatomy-v1.sha256").read_text().strip()
    if sidecar != pin["specSha256"]:
        raise ValueError("PREDECESSOR_SPEC_CHANGED")
    return True


def load_spec(root=ROOT):
    root = Path(root)
    path = root / SPEC_PATH
    spec = json.loads(path.read_text())
    sha = path.with_suffix(".sha256").read_text().strip()
    if digest(spec) != sha or spec.get("studyId") != STUDY:
        raise ValueError("SPEC_IDENTITY_CHANGED")
    if spec["scientificStatus"] != SCIENTIFIC_STATUS:
        raise ValueError("SCIENTIFIC_STATUS_CHANGED")
    expected = sorted(set(import_closure(spec["entryPoints"], root)) | set(spec["sealedDataInputs"]))
    if expected != sorted(spec["dependencyHashes"]):
        raise ValueError("IMPORT_CLOSURE_CHANGED")
    for rel, wanted in spec["dependencyHashes"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("HARNESS_OR_DEPENDENCY_CHANGED: " + rel)
    verify_predecessor(spec, root)
    if tuple(f["name"] for f in spec["factors"]) != R.FACTORS:
        raise ValueError("FACTOR_LIST_DIFFERS_FROM_ANATOMY")
    return spec, sha


def verify(root=ROOT, env=None):
    """Outcome-free: identity, closure and predecessor. This is the only mode ordinary pull-request CI runs."""
    spec, sha = load_spec(root)
    counters = Counters()
    try:
        authorize_execution(spec, sha, root, env)
        authorized = True
    except (ValueError, subprocess.CalledProcessError, OSError):
        authorized = False
    return {"studyId": STUDY, "mode": "verify", "status": "VERIFIED", "specSha256": sha,
            "scientificStatus": spec["scientificStatus"], "executeAuthorizedInThisEnvironment": authorized,
            "dependencyFiles": len(spec["dependencyHashes"]), "counters": asdict(counters),
            "stoppedBeforeOutcomes": counters.zero(), "historicalExecutionPerformed": False}


# --------------------------------------------------------------------------- #
# The durable one-shot lock (a GitHub git ref, never an artifact or a local file)
# --------------------------------------------------------------------------- #
_LOCK_TOKEN = object()


@dataclass(frozen=True)
class ExecutionLock:
    specSha256: str
    mainSha: str
    ref: str
    token: object


LOCK_PREFIX = "refs/tags/" + STUDY + "-execution-lock"


def lock_ref(spec_sha):
    """Identity of this revision's lock: study + exact spec SHA. It is recorded for provenance; it is NOT what makes the study
    one-shot. That is `STUDY_LOCK_REF` and the PREFIX check: any ref under LOCK_PREFIX, for any spec SHA, consumes the study."""
    return LOCK_PREFIX + "-" + spec_sha


STUDY_LOCK_REF = LOCK_PREFIX                       # one fixed, study-level ref: its atomic create is the exclusive claim


def github_api(method, path, payload=None, env=None):
    """(status, body) from the GitHub REST API. A transport error is raised, never swallowed."""
    env = os.environ if env is None else env
    request = urllib.request.Request(
        "https://api.github.com/repos/" + env["GITHUB_REPOSITORY"] + path,
        data=None if payload is None else json.dumps(payload).encode(), method=method,
        headers={"Authorization": "Bearer " + env["GH_TOKEN"], "Content-Type": "application/json",
                 "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, {}


def lock_exists(spec_sha=None, env=None, api=github_api):
    """True when ANY execution lock for this study exists, whatever spec SHA it carries; False when none does. Anything else
    (including a missing token) is UNVERIFIABLE and refuses. `spec_sha` is accepted for call compatibility and deliberately
    ignored: changing the spec never reopens the study."""
    env = os.environ if env is None else env
    if not env.get("GH_TOKEN") or not env.get("GITHUB_REPOSITORY"):
        raise ValueError("EXECUTION_LOCK_STATE_UNVERIFIABLE")
    status, body = api("GET", "/git/matching-refs/" + LOCK_PREFIX[len("refs/"):], None)
    if status == 200 and isinstance(body, list):
        return len(body) > 0
    raise ValueError("EXECUTION_LOCK_STATE_UNVERIFIABLE")


def claim_execution_lock(spec_sha, env=None, api=github_api):
    """Exclusive create, called only after identities and readiness gates passed and before ANY outcome is read.

    1. refuse if ANY lock for this study already exists (any spec SHA);
    2. atomically create the fixed study-level ref (a duplicate answers 422: the exclusive claim for the whole study);
    3. create this revision's spec-SHA ref (identity), then verify both point at the dispatched main commit.

    Only POST (create) and GET (read) are ever issued: no ref is PATCHed, moved, deleted or recreated, so a failure after
    this call cannot reopen the study. An ambiguous response refuses without outcome access."""
    env = os.environ if env is None else env
    if env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("FORMAL_EXECUTION_REQUIRES_ACTIONS_MAIN")
    if lock_exists(spec_sha, env, api):
        raise ValueError("EXECUTION_LOCK_ALREADY_EXISTS")
    main_sha, ref = env["GITHUB_SHA"], lock_ref(spec_sha)
    for target in (STUDY_LOCK_REF, ref):
        status, _ = api("POST", "/git/refs", {"ref": target, "sha": main_sha})
        if status == 422:
            raise ValueError("EXECUTION_LOCK_ALREADY_EXISTS")
        if status != 201:
            raise ValueError("ATOMIC_EXECUTION_LOCK_NOT_CREATED")
    for target in (STUDY_LOCK_REF, ref):
        status, body = api("GET", "/git/ref/" + target[len("refs/"):], None)
        if status != 200 or (body.get("object") or {}).get("sha") != main_sha:
            raise ValueError("EXECUTION_LOCK_NOT_ON_THE_AUTHORIZED_COMMIT")
    return ExecutionLock(spec_sha, main_sha, ref, _LOCK_TOKEN)


def require_lock(lock, sha):
    if not isinstance(lock, ExecutionLock) or lock.token is not _LOCK_TOKEN or lock.specSha256 != sha:
        raise ValueError("DURABLE_EXECUTION_LOCK_REQUIRED_BEFORE_ANY_OUTCOME")
    return lock


# --------------------------------------------------------------------------- #
# Execution authorization (merged main only)
# --------------------------------------------------------------------------- #
def _git(args, root):
    return subprocess.check_output(["git", *args], cwd=str(root))


def authorize_execution(spec, sha, root=ROOT, env=None, git=_git, lock_probe=None):
    """Raise unless this is a workflow_dispatch on main, at a commit that carries exactly this spec, over the exact sealed
    predecessor, naming exactly the preserved raw artifact, with no committed result or marker and NO durable execution lock
    (the lock is a GitHub tag; an unverifiable lock state refuses)."""
    env = os.environ if env is None else env
    root = Path(root)
    if env.get("GITHUB_ACTIONS") != "true":
        raise ValueError("FORMAL_EXECUTION_REQUIRES_ACTIONS")
    if env.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("FORMAL_EXECUTION_REQUIRES_MAIN")
    if env.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        raise ValueError("FORMAL_EXECUTION_REQUIRES_WORKFLOW_DISPATCH")
    head = git(["rev-parse", "HEAD"], root).decode().strip()
    if not env.get("GITHUB_SHA") or head != env["GITHUB_SHA"]:
        raise ValueError("CHECKOUT_IS_NOT_THE_DISPATCHED_COMMIT")
    for rel in (SPEC_PATH, str(Path(SPEC_PATH).with_suffix(".sha256"))):
        if git(["show", "HEAD:" + rel], root) != (root / rel).read_bytes():
            raise ValueError("SPEC_NOT_COMMITTED_AT_HEAD")
    verify_predecessor(spec, root)
    pin = spec["input"]
    if (env.get("REGIME_INPUT_ARTIFACT") != pin["artifactName"] or env.get("REGIME_INPUT_RUN_ID") != str(pin["producingRunId"])):
        raise ValueError("INPUT_ARTIFACT_IDENTITY_MISMATCH")
    if (root / RESULT_PATH).exists():
        raise ValueError("REGIME_REVIEW_RESULT_ALREADY_COMMITTED")
    if (root / MARKER_PATH).exists():
        raise ValueError("REGIME_REVIEW_EXECUTION_MARKER_ALREADY_COMMITTED")
    if (lock_probe or (lambda: lock_exists(sha, env)))():
        raise ValueError("EXECUTION_LOCK_ALREADY_EXISTS")
    return ExecutionPermit(sha, _PERMIT_TOKEN)


# --------------------------------------------------------------------------- #
# Data assembly: label-free signal-time panel first, outcomes only after the marker
# --------------------------------------------------------------------------- #
def signal_time_panel(bundle):
    """Everything known at the signal date. No target, endpoint or return is read here."""
    panel = bundle["features"].copy().reset_index(drop=True)
    market, accounting = bundle["market"], bundle["accounting"]
    panel["marketCap"] = [(market.at(t, d) or {}).get("marketCap", np.nan) for t, d in zip(panel.ticker, panel.date)]
    states = [bundle["overlay"][d] for d in panel.date]
    panel["riskMultiplier"] = [s.get("riskMultiplier") for s in states]
    panel["trendAdverse"] = [s.get("trendAdverse") for s in states]
    panel["volAdverse"] = [s.get("volAdverse") for s in states]
    panel["netIncomeImprovementToAssets"] = [
        AE.improvement_to_assets(accounting.get(t, []), d, "당기순이익") for t, d in zip(panel.ticker, panel.date)]
    return panel


def readiness_gates(panel, bundle, spec):
    """Label-free readiness. Returns the list of reasons the study cannot run; empty means ready."""
    reasons = []
    if panel.empty:
        return ["NO_PIT_NAME_DATES"]
    missing = [c for c in R.FACTORS if c not in panel.columns]
    if missing:
        reasons.append("FACTOR_COLUMNS_MISSING: " + ",".join(missing))
    if set(panel.date) != set(bundle["schedule"]):
        reasons.append("MISSING_SCHEDULED_SIGNAL_DATE")
    if panel.duplicated(["date", "ticker"]).any():
        reasons.append("DUPLICATE_PIT_NAME_DATE")
    cap = pd.to_numeric(panel.marketCap, errors="coerce")
    per_date = cap.notna().groupby(panel.date).sum()
    if (per_date < spec["readiness"]["minimumNamesWithMarketCapPerDate"]).any():
        reasons.append("MARKET_CAP_UNAVAILABLE_FOR_DYNAMIC_EXCLUSION")
    ready = pd.to_numeric(panel.riskMultiplier, errors="coerce").notna().groupby(panel.date).any()
    if not ready.any():
        reasons.append("NO_SIGNAL_TIME_BENCHMARK_STATE")
    return reasons


def attach_outcomes(panel, bundle, v1_spec, spec, permit, counters, lock=None, sha=None):
    """Endpoint returns and the v1 terminal discipline, identical in rule to the anatomy's `build_panel` (and cross-checked
    against the sealed v1 target on every row). Requires a permit AND the durable lock; increments the outcome counters."""
    require_permit(permit)
    require_lock(lock, permit.specSha256 if sha is None else sha)
    prices = bundle["prices"]
    days = RC.sessions("2013-01-01", "2028-12-31", "KR")
    out = panel.copy().reset_index(drop=True)
    foundation = json.loads((ROOT / v1_spec["inputs"]["terminalFoundationPath"]).read_text())
    complete = {row["code"] + ".KS": row.get("completeness") for row in foundation.get("securities", [])}
    target_from_sessions = AE.sealed_v1_function("target_from_sessions")
    attach_eligibility = AE.sealed_v1_function("attach_eligibility")
    for h in spec["horizons"]:
        records = []
        for ticker, date in zip(out.ticker, out.date):
            counters.outcomeColumnCalls += 1
            mine = A.endpoint_returns(days, prices, spec["benchmark"], ticker, date, h, spec["developmentCutoff"])
            counters.targetCalls += 1
            theirs = target_from_sessions(days, prices, spec["benchmark"], ticker, date, h, spec["developmentCutoff"])
            counters.labelCalls += 1
            if (mine["status"] != theirs["labelStatus"] or mine["entryDate"] != theirs["entryDate"]
                    or mine["exitDate"] != theirs["outcomeEndDate"]
                    or (mine["status"] == "MATURED" and abs(mine["relativeReturn"] - theirs["forwardRelativeReturn"]) > 1e-12)):
                raise ValueError("ENDPOINT_SEMANTICS_DIFFER_FROM_V1_TARGET")
            records.append(mine)
        frame = pd.DataFrame(records)
        elig = attach_eligibility(pd.DataFrame({"ticker": out.ticker, "outcomeEndDate": frame.exitDate}), prices, complete)
        status = frame.status.where(~(frame.status.eq("MATURED") & ~elig.eligibilityStatus.eq("ELIGIBLE")),
                                    "UNRESOLVED_TERMINAL_OR_DISTRIBUTION_EVIDENCE")
        s = str(h)
        out["entry" + s], out["exit" + s] = frame.entryDate.to_numpy(), frame.exitDate.to_numpy()
        out["stock" + s] = frame.stockReturn.astype(float).to_numpy()
        out["bench" + s] = frame.benchmarkReturn.astype(float).to_numpy()
        out["rawStatus" + s], out["status" + s] = frame.status.to_numpy(), status.to_numpy()
    return out


# --------------------------------------------------------------------------- #
# Marker (written only after identities and gates pass) and deterministic output
# --------------------------------------------------------------------------- #
def write_execution_marker(output, spec, sha, identity, counters, lock=None):
    """HUMAN-READABLE provenance of the lock, never the enforcement. Atomic and exclusive in the output directory."""
    counters.markerWrites += 1
    document = {"studyId": STUDY, "specSha256": sha, "inputIdentitySha256": identity["sha256"],
                "lockRef": None if lock is None else lock.ref, "lockedMainSha": None if lock is None else lock.mainSha,
                "predecessorResultSha256": spec["predecessor"]["sha256"]["result"], "outcomesReadBeforeThisMarker": 0}
    X.atomic_write(Path(output) / "execution-started.json", document, immutable=True)
    return document


def write_outputs(output, analysis, report, spec, sha, identity, counters):
    out = Path(output)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    result = AE.json_safe(analysis["result"])
    files = {"regime-review.json": X.atomic_write(out / "regime-review.json", result)}
    (out / "report.md").write_text(report, encoding="utf-8")
    files["report.md"] = hashlib.sha256(report.encode()).hexdigest()
    for name, rows in sorted(analysis["tables"].items()):
        data = AE._gzip_csv(pd.DataFrame(rows))
        (out / "tables" / (name + ".csv.gz")).write_bytes(data)
        files["tables/" + name + ".csv.gz"] = hashlib.sha256(data).hexdigest()
    manifest = {"studyId": STUDY, "specSha256": sha, "inputIdentitySha256": identity["sha256"],
                "scientificStatus": SCIENTIFIC_STATUS, "returnBasis": R.RETURN_BASIS,
                "predecessor": {"resultSha256": spec["predecessor"]["sha256"]["result"],
                                "manifestSha256": spec["predecessor"]["sha256"]["manifest"]},
                "counters": asdict(counters), "files": files}
    X.atomic_write(out / "manifest.json", AE.json_safe(manifest))
    return manifest


def execute(input_root, output, spec, sha, permit, root=ROOT, env=None, api=github_api):
    """Order: permit -> exact input identity -> predecessor -> label-free panel -> readiness gates -> DURABLE LOCK ->
    marker file -> outcomes -> tables. A failure before the lock spends nothing; a failure after it consumes the study."""
    require_permit(permit)
    if permit.specSha256 != sha:
        raise ValueError("PERMIT_FOR_A_DIFFERENT_SPEC")
    counters = Counters()
    identity = X.input_identity(input_root)
    if identity["sha256"] != spec["input"]["identitySha256"]:
        raise ValueError("INPUT_IDENTITY_MISMATCH")
    verify_predecessor(spec, root)
    v1_spec, _ = X.load_spec(root)
    bundle = X.prepare(input_root, v1_spec)
    A.assert_pit_membership(bundle["features"], AE.load_memberships(input_root, v1_spec))
    panel = signal_time_panel(bundle)
    reasons = readiness_gates(panel, bundle, spec)
    if reasons:
        Path(output).mkdir(parents=True, exist_ok=True)
        X.atomic_write(Path(output) / "gates-failed.json", {"studyId": STUDY, "reasons": reasons, "counters": asdict(counters)})
        raise ValueError("READINESS_GATE_FAILED: " + ";".join(reasons))
    lock = claim_execution_lock(sha, env, api)                   # durable + exclusive; nothing below runs without it
    write_execution_marker(output, spec, sha, identity, counters, lock)
    panel = attach_outcomes(panel, bundle, v1_spec, spec, permit, counters, lock, sha)
    panel = R.add_outcomes(panel, spec["benchmarks"]["minimumPeers"])
    counters.analysisCalls += 1
    analysis = R.analyze_all(panel, spec)
    return write_outputs(output, analysis, R.render_report(analysis["result"], spec), spec, sha, identity, counters)
