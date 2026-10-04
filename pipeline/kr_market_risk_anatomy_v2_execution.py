"""KR market risk anatomy v2 — frozen identity, label-free readiness, one-shot lock and (later) execution.

EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY. v2 exists only to correct SOURCE ADMISSIBILITY (see `kr_market_risk_sources_v2`): v1 is a permanently
valid BLOCKED study and is never unblocked in place. Everything v1 froze — features, orientations, horizons, episode algorithm, triggers, overlay comparison,
statistics, exclusions of revised-history series — is imported unchanged, and the v1 module files are byte-pinned by this spec's import closure.

No new external acquisition: the exact immutable bytes retained by v1 (`data/kr-market-risk-anatomy-v1/sources`) are the only source input.

On pull requests only `verify` and `readiness_audit` run. They read observation DATES and metadata (never a price, rate or forward quantity); the counters
prove it. `execute` refuses unless a workflow_dispatch on merged main carries this exact committed spec with every pin intact and no prior result, marker or
lock; the label-free gates run; ONLY THEN does it win the durable exclusive git-tag lock, and only after the lock is any source value read. A failure before
the lock spends nothing; a failure after it consumes v2. It never reruns a sealed study and never contacts a data vendor.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess

import pandas as pd

from . import kr_factor_anatomy_execution as AE
from . import kr_industry_anatomy_execution as IE
from . import kr_market_risk_anatomy as M
from . import kr_market_risk_anatomy_analysis as AN
from . import kr_market_risk_anatomy_execution as V1
from . import kr_market_risk_source_parse as P
from . import kr_market_risk_sources as S
from . import kr_market_risk_sources_v2 as R
from . import kr_model_portfolio_execution as X

digest, file_hash, import_closure = X.digest, X.file_hash, X.import_closure
ROOT = Path(__file__).resolve().parents[1]
STUDY = R.STUDY
V1_STUDY = M.STUDY
SPEC_PATH = "research_specs/" + STUDY + ".json"
V1_SPEC_PATH = V1.SPEC_PATH
V1_DESIGN_PATH = V1.DESIGN_PATH
SNAPSHOT_DIR = V1.SNAPSHOT_DIR                      # v2 acquires nothing: it reads v1's retained bytes
RESULT_PATH = "docs/results/" + STUDY + "-result.json"
MARKER_PATH = "docs/results/" + STUDY + "-execution-started.json"
READINESS_PATH = "docs/results/" + STUDY + "-readiness.json"
SCIENTIFIC_STATUS = M.SCIENTIFIC_STATUS
DECISION_READY = "READY_FOR_MARKET_RISK_ANATOMY_V2_EXECUTION"
DECISION_BLOCKED = "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY_V2"
V1_SEALED_ARTIFACTS = ("research_specs/kr-market-risk-anatomy-v1.json", "research_specs/kr-market-risk-anatomy-v1.sha256", "research_specs/kr-market-risk-anatomy-v1-design.json",
                       "research_specs/kr-market-risk-anatomy-v1-design.sha256", "docs/results/kr-market-risk-anatomy-v1-readiness.json",
                       "docs/results/kr-market-risk-anatomy-v1-source-provenance.json", "docs/kr-market-risk-anatomy-v1-source-readiness.md",
                       ".github/workflows/kr-market-risk-anatomy-v1.yml")

Counters = V1.Counters


@dataclass(frozen=True)
class ExecutionPermit:
    specSha256: str
    token: object


_PERMIT_TOKEN = object()


def require_permit(permit):
    if not isinstance(permit, ExecutionPermit) or permit.token is not _PERMIT_TOKEN:
        raise ValueError("MARKET_RISK_V2_OUTCOME_ACCESS_WITHOUT_PERMIT")
    return permit


def source_rules():
    """The frozen v2 rule constants as the module defines them; the spec carries the same values and `load_spec` compares them."""
    return {"qualityWindowStart": R.QUALITY_WINDOW_START, "maxBadSessionShare": R.MAX_BAD_SESSION_SHARE, "liveFreshnessDaysInformationalOnly": R.LIVE_FRESHNESS_DAYS,
            "referencePriority": list(R.REFERENCE_PRIORITY), "primaryFamilyOrder": list(R.PRIMARY_FAMILY_ORDER), "firstDateNoLaterThan": R.REFERENCE_FIRST_DATE_NO_LATER_THAN,
            "coreWindows": {k: list(v) for k, v in R.CORE_WINDOWS.items()}, "sessionCoverage": R.REFERENCE_SESSION_COVERAGE, "fullRangeCoverage": R.REFERENCE_FULL_RANGE_COVERAGE,
            "maxConsecutiveMissing": R.REFERENCE_MAX_CONSECUTIVE_MISSING, "rules": R.HISTORICAL_RULES}


# --------------------------------------------------------------------------- #
# Frozen identity
# --------------------------------------------------------------------------- #
def verify_pins(spec, root=ROOT):
    """v1's sealed artifacts are byte-identical, v1's design and source snapshot match their pins, and v2's own pins equal v1's (no new acquisition)."""
    root = Path(root)
    for rel, wanted in spec["predecessor"]["sealedArtifacts"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("V1_SEALED_ARTIFACT_CHANGED: " + rel)
    if sorted(spec["predecessor"]["sealedArtifacts"]) != sorted(V1_SEALED_ARTIFACTS):
        raise ValueError("V1_SEALED_ARTIFACT_SET_CHANGED")
    v1_spec = json.loads((root / V1_SPEC_PATH).read_text())
    if spec["sourcePins"] != v1_spec["sourcePins"] or spec["input"] != v1_spec["input"]:
        raise ValueError("SOURCE_PINS_DIFFER_FROM_THE_RETAINED_V1_BYTES")
    if spec["designSha256"] != v1_spec["designSha256"] or spec["inheritedDesign"]["sha256"] != v1_spec["designSha256"]:
        raise ValueError("INHERITED_DESIGN_CHANGED")
    if spec["newExternalAcquisition"] is not False:
        raise ValueError("NEW_EXTERNAL_ACQUISITION_NOT_PERMITTED_IN_V2")
    return V1.verify_pins(v1_spec, root)             # v1 design hashes and every retained source byte


def load_spec(root=ROOT):
    root = Path(root)
    path = root / SPEC_PATH
    spec = json.loads(path.read_text())
    sha = path.with_suffix(".sha256").read_text().strip()
    if digest(spec) != sha or spec.get("studyId") != STUDY:
        raise ValueError("SPEC_IDENTITY_CHANGED")
    if spec["scientificStatus"] != SCIENTIFIC_STATUS or spec["predecessor"]["studyId"] != V1_STUDY:
        raise ValueError("SCIENTIFIC_STATUS_CHANGED")
    expected = sorted(set(import_closure(spec["entryPoints"], root)) | set(spec["sealedDataInputs"]))
    if expected != sorted(spec["dependencyHashes"]):
        raise ValueError("IMPORT_CLOSURE_CHANGED")
    for rel, wanted in spec["dependencyHashes"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("HARNESS_OR_DEPENDENCY_CHANGED: " + rel)
    verify_pins(spec, root)
    if json.loads(json.dumps(spec["sourceRules"])) != json.loads(json.dumps(source_rules())):
        raise ValueError("MODULE_RULE_DIFFERS_FROM_FROZEN_SPEC")
    design = json.loads((root / V1_DESIGN_PATH).read_text())
    if design["constants"]["lossCuts"] != list(M.LOSS_CUTS) or design["constants"]["primaryEpisodeThreshold"] != M.PRIMARY_EPISODE_THRESHOLD:
        raise ValueError("MODULE_CONSTANT_DIFFERS_FROM_FROZEN_DESIGN")
    if sorted(design["features"]) != sorted(M.FEATURES) or sorted(design["sources"]) != sorted(S.SOURCES):
        raise ValueError("MODULE_REGISTRY_DIFFERS_FROM_FROZEN_DESIGN")
    return spec, sha


def _git(args, root):
    return subprocess.check_output(["git", *args], cwd=str(root))


def authorize_execution(spec, sha, root=ROOT, env=None, git=None, lock_probe=None):
    """Raise unless this is a workflow_dispatch on main at a commit carrying exactly this spec, with every pin intact, no committed result or marker and no
    durable execution lock (an unverifiable lock state refuses)."""
    git = git or _git
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
    verify_pins(spec, root)                       # every input hash is checked BEFORE any lock
    pin = spec["input"]
    if env.get("MARKET_INPUT_ARTIFACT") != pin["artifactName"] or env.get("MARKET_INPUT_RUN_ID") != str(pin["producingRunId"]):
        raise ValueError("INPUT_ARTIFACT_IDENTITY_MISMATCH")
    if (root / RESULT_PATH).exists():
        raise ValueError("MARKET_RISK_V2_RESULT_ALREADY_COMMITTED")
    if (root / MARKER_PATH).exists():
        raise ValueError("MARKET_RISK_V2_EXECUTION_MARKER_ALREADY_COMMITTED")
    if (lock_probe or (lambda: lock_exists(sha, env)))():
        raise ValueError("EXECUTION_LOCK_ALREADY_EXISTS")
    return ExecutionPermit(sha, _PERMIT_TOKEN)


def verify(root=ROOT, env=None):
    """Outcome-free: identity, closure and pins. The only mode ordinary pull-request CI runs besides readiness."""
    spec, sha = load_spec(root)
    counters = Counters()
    try:
        authorize_execution(spec, sha, root, env)
        authorized = True
    except (ValueError, subprocess.CalledProcessError, OSError, KeyError):
        authorized = False
    return {"studyId": STUDY, "mode": "verify", "status": "VERIFIED", "specSha256": sha, "designSha256": spec["designSha256"], "scientificStatus": spec["scientificStatus"],
            "executeAuthorizedInThisEnvironment": authorized, "dependencyFiles": len(spec["dependencyHashes"]), "counters": asdict(counters),
            "stoppedBeforeOutcomes": counters.zero(), "historicalExecutionPerformed": False}


# --------------------------------------------------------------------------- #
# The durable one-shot lock (a GitHub git ref, never an artifact or a local file)
# --------------------------------------------------------------------------- #
_LOCK_TOKEN = object()
LOCK_PREFIX = "refs/tags/" + STUDY + "-execution-lock"
STUDY_LOCK_REF = LOCK_PREFIX
github_api = IE.github_api


@dataclass(frozen=True)
class ExecutionLock:
    specSha256: str
    mainSha: str
    ref: str
    token: object


def lock_ref(spec_sha):
    return LOCK_PREFIX + "-" + spec_sha


def lock_exists(spec_sha=None, env=None, api=github_api):
    """True when ANY lock for this study exists, whatever spec SHA it carries; anything unverifiable refuses."""
    env = os.environ if env is None else env
    if not env.get("GH_TOKEN") or not env.get("GITHUB_REPOSITORY"):
        raise ValueError("EXECUTION_LOCK_STATE_UNVERIFIABLE")
    status, body = api("GET", "/git/matching-refs/" + LOCK_PREFIX[len("refs/"):], None)
    if status == 200 and isinstance(body, list):
        return len(body) > 0
    raise ValueError("EXECUTION_LOCK_STATE_UNVERIFIABLE")


def claim_execution_lock(spec_sha, env=None, api=github_api):
    """Exclusive create after identities and readiness gates passed and before ANY value is read. Only POST and GET are issued; a ref is never moved."""
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
# Label-free decision (DATES and metadata only)
# --------------------------------------------------------------------------- #
def decide(root=ROOT):
    """Label-free v2 decision: historical primary-reference rule, role sources and the frozen CORE gates, all from observation dates and the XKRX calendar.
    The calendar runs to the acquisition day only to define 'completed session'; the analysis end is the selected reference's own last admissible session."""
    views, audit = V1.snapshot_views(root)
    acquired_on = audit["acquiredOn"]
    sessions = M.kr_sessions("1990-01-02", acquired_on)
    raw = {sid: R.raw_row_dates(sid, root) for sid in S.REFERENCE_PRIORITY + (S.ROBUSTNESS_REFERENCE,) if not S.SOURCES[sid].get("documentedBlocker")}
    reference = R.select_primary_reference(views, raw, sessions, acquired_on)
    if reference["primary"] is not None:
        sessions = sessions[sessions <= pd.Timestamp(reference["analysisEnd"])]
    weekly = M.period_end_dates(sessions, "W")
    roles, role_coverage = {}, {}
    for role in S.ROLE_PRIORITY:
        roles[role], role_coverage[role] = S.select_role_source(role, views, sessions, weekly)
    gates = S.core_gates(views, reference, roles, sessions, acquired_on)
    gates = dict(gates, decision=DECISION_READY if gates["decision"] == V1.DECISION_READY else DECISION_BLOCKED)
    return {"reference": reference, "roles": roles, "roleCoverage": role_coverage, "gates": gates, "sessions": sessions, "views": views, "audit": audit, "raw": raw}


def load_series(root, counters, permit, lock, sha, analysis_end):
    """Source VALUES, only after the permit and the durable lock; every read is counted. The reference is cut at the analysis end, never extended."""
    require_permit(permit)
    require_lock(lock, sha)
    out = {}
    for sid in S.ACQUIRED_IDS:
        path = Path(root) / SNAPSHOT_DIR / sid / "normalized.csv"
        if path.exists():
            counters.valueReads += 1
            series = AN.obs_series(P.read_normalized(path.read_bytes()))
            out[sid] = series[series.index <= pd.Timestamp(analysis_end)] if sid in S.REFERENCE_PRIORITY else series
    return out


def extended_tier_audit(root=ROOT):
    root = Path(root)
    spec = json.loads((root / SPEC_PATH).read_text())
    base = V1.extended_tier_audit(root)
    return dict(base, rawInputArtifact={k: spec["input"][k] for k in ("artifactName", "artifactId", "producingRunId", "artifactArchiveSha256")})


# --------------------------------------------------------------------------- #
# Execution (permit -> pins -> label-free gates -> LOCK -> marker -> values -> outcomes)
# --------------------------------------------------------------------------- #
def write_execution_marker(output, spec, sha, counters, lock=None):
    counters.markerWrites += 1
    document = {"studyId": STUDY, "specSha256": sha, "designSha256": spec["designSha256"], "sourceAuditSha256": spec["sourcePins"]["auditSha256"],
                "lockRef": None if lock is None else lock.ref, "lockedMainSha": None if lock is None else lock.mainSha, "valuesReadBeforeThisMarker": 0}
    X.atomic_write(Path(output) / "execution-started.json", document, immutable=True)
    return document


def execute(output, spec, sha, permit, root=ROOT, env=None, api=github_api, input_root=None, extended_builder=None):
    """Order: permit -> pins -> label-free decision (gates) -> DURABLE LOCK -> marker -> source values -> outcomes. A failed gate writes gates-failed.json,
    creates no lock and spends nothing."""
    require_permit(permit)
    if permit.specSha256 != sha:
        raise ValueError("PERMIT_FOR_A_DIFFERENT_SPEC")
    counters = Counters()
    verify_pins(spec, root)
    decision = decide(root)
    if decision["gates"]["decision"] != DECISION_READY:
        Path(output).mkdir(parents=True, exist_ok=True)
        X.atomic_write(Path(output) / "gates-failed.json", {"studyId": STUDY, "decision": decision["gates"]["decision"], "blockers": decision["gates"]["blockers"],
                                                          "reference": decision["reference"], "counters": asdict(counters)})
        raise ValueError("READINESS_GATE_FAILED: " + ";".join(decision["gates"]["blockers"]))
    lock = claim_execution_lock(sha, env, api)
    write_execution_marker(output, spec, sha, counters, lock)
    primary, end = decision["reference"]["primary"], decision["reference"]["analysisEnd"]
    series = load_series(root, counters, permit, lock, sha, end)
    counters.forwardTargetCalls += 1
    counters.episodeCalls += 1
    panel = AN.build_core_panel(series[primary], {k: v for k, v in series.items() if k != primary}, decision["roles"], S.lag_days)
    extended = extended_builder(input_root, panel, spec, root) if extended_builder and input_root else None
    counters.analysisCalls += 1
    result = {"studyId": STUDY, "predecessor": V1_STUDY, "scientificStatus": SCIENTIFIC_STATUS, "analysisEnd": end,
              "primaryReference": {k: decision["reference"][k] for k in ("primary", "family", "basis", "instrument", "composite", "analysisEnd", "spliced")},
              "roleSources": decision["roles"], "extendedStatus": "NOT_RUN_NO_INPUT" if extended is None else "RUN", **AN.analyze(panel, extended)}
    return write_outputs(output, result, spec, sha, counters)


def write_outputs(output, result, spec, sha, counters):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    files = {"market-risk-anatomy.json": X.atomic_write(out / "market-risk-anatomy.json", AE.json_safe(result))}
    manifest = {"studyId": STUDY, "specSha256": sha, "designSha256": spec["designSha256"], "sourceAuditSha256": spec["sourcePins"]["auditSha256"],
                "scientificStatus": SCIENTIFIC_STATUS, "counters": asdict(counters), "files": files}
    X.atomic_write(out / "manifest.json", AE.json_safe(manifest))
    return manifest


extended_internals = V1.extended_internals


# --------------------------------------------------------------------------- #
# Outcome-free readiness report
# --------------------------------------------------------------------------- #
def v1_comparison(root=ROOT):
    """Why v2 differs from v1 for each candidate: v1's recorded reasons (read from the committed, unchanged v1 readiness JSON) beside the v2 reasons."""
    v1 = json.loads((Path(root) / "docs/results/kr-market-risk-anatomy-v1-readiness.json").read_text())
    return {sid: {"v1Eligible": e["eligible"], "v1Reasons": e["reasons"]} for sid, e in v1["primaryReference"]["evaluated"].items()} | {
        "_v1Decision": v1["decision"], "_v1Blockers": v1["blockers"]}


def source_identity(root, audit, source_id):
    record = audit["sources"][source_id]
    return {"id": source_id, "vendor": record.get("vendor"), "symbol": record.get("symbol"), "host": record.get("host"), "instrument": record.get("instrument"),
            "basis": record.get("basis"), "unit": record.get("unit"), "vintageClass": record.get("vintageClass"), "fetchedAtUtc": record.get("fetchedAtUtc"),
            "retainedFileSha256": record.get("files"), "identityOkByRegisteredFunction": S.identity_ok(S.SOURCES[source_id], record.get("identity", {})),
            "rawRows": record.get("rawRows"), "validRows": record.get("validRows"), "droppedRowsAsRecorded": record.get("droppedRows"),
            "firstDate": record.get("firstDate"), "lastDate": record.get("lastDate")}


def readiness_audit(root=ROOT):
    """READY_FOR_MARKET_RISK_ANATOMY_V2_EXECUTION or DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY_V2 from identities, structure and observation DATES alone. It never
    parses a price, rate or forward quantity, and the counters prove it."""
    root = Path(root)
    counters = Counters()
    checks, details = {}, {}
    spec = sha = None
    try:
        spec, sha = load_spec(root)
        checks["frozenSpecDesignSnapshotAndImportClosure"] = True
    except (ValueError, KeyError, OSError) as error:
        checks["frozenSpecDesignSnapshotAndImportClosure"], details["frozenSpecDesignSnapshotAndImportClosure"] = False, str(error)
    out = {"studyId": STUDY, "predecessor": V1_STUDY, "mode": "readiness", "specSha256": sha, "counters": asdict(counters), "basedOnAnyReturnResult": False,
           "historicalExecutionPerformed": False, "scientificStatus": SCIENTIFIC_STATUS, "newExternalAcquisition": False}
    if spec is None:
        return {**out, "decision": DECISION_BLOCKED, "checks": checks, "details": details, "blockers": ["FROZEN_IDENTITY_NOT_VERIFIED"]}
    decided = decide(root)
    views, audit, reference = decided["views"], decided["audit"], decided["reference"]
    checks["noOutcomeAccess"] = counters.zero()
    checks["sourceRegistryIsPredictorEligibleOnly"] = S.validate_registry()
    gates = decided["gates"]
    primary = reference.get("primary")
    out.update(
        decision=gates["decision"], checks=checks, details=details, blockers=gates["blockers"], gates=gates["gates"], primaryReference=reference, roleSources=decided["roles"],
        roleCoverage=decided["roleCoverage"], coreCoverageTables=gates["coverage"], acquiredOn=audit["acquiredOn"], extendedTier=extended_tier_audit(root),
        sourceCoverage=AN.coverage_tables(views, decided["sessions"], decided["roles"]), v1Comparison=v1_comparison(root),
        sourceInventory={sid: {"status": audit["sources"][sid]["status"], "firstDate": audit["sources"][sid].get("firstDate"), "lastDate": audit["sources"][sid].get("lastDate"),
                               "validRows": audit["sources"][sid].get("validRows"), "droppedRows": audit["sources"][sid].get("droppedRows"),
                               "identityOkByRegisteredFunction": views[sid].get("identityOk"), "vintageClass": S.SOURCES[sid]["vintageClass"]} for sid in audit["sources"]},
        excludedRevisedOrUnbuiltInputs={sid: {"vintageClass": S.SOURCES[sid]["vintageClass"], "reason": S.SOURCES[sid]["excluded"]} for sid in S.EXCLUDED_IDS},
        documentedBlocker={sid: S.SOURCES[sid]["documentedBlocker"] for sid in S.SOURCES if S.SOURCES[sid].get("documentedBlocker")})
    if primary is not None:
        metrics = reference["evaluated"][primary]["metrics"]
        out["selectedReference"] = {"identity": source_identity(root, audit, primary), "analysisEnd": reference["analysisEnd"], "firstUsableDate": metrics["firstDate"],
                                    "lastUsableDate": metrics["lastDate"], "quality": metrics["quality"], "sessionCoverage": metrics["sessionCoverage"],
                                    "fullRangeCoverage": metrics["fullRangeCoverage"], "longestMissingRun": metrics["longestMissingRun"],
                                    "liveOperationalFreshness": metrics["liveOperationalFreshness"], "spliced": False,
                                    "vintageClass": S.SOURCES[primary]["vintageClass"]}
    out["covers2008"] = bool(primary) and gates["gates"].get("REFERENCE_GFC_2007_2009", {}).get("pass", False)
    return out
