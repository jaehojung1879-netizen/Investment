"""KR market risk anatomy v1 — frozen identity, label-free readiness, one-shot lock and (later) execution.

EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY. On pull requests only `verify` and `readiness_audit` run. They read the committed source
snapshot's DATES and metadata (never a price, rate or forward quantity), compute no return, drawdown, episode or future label, and the counters prove it.

`execute` exists but refuses unless a workflow_dispatch on merged main carries this exact committed spec, whose frozen design and source snapshot match
their pinned hashes, with no prior result, marker or lock; it then evaluates the label-free readiness gates; ONLY THEN does it win a durable exclusive
git-tag lock, and only after the lock is the first source value read and the first outcome computed. A failure before the lock spends nothing; a
failure after it consumes v1. It never reruns a sealed study and never contacts a data vendor: the inputs are the committed immutable snapshot (and, for
the extended tier, the preserved raw artifact named in the spec).
"""
from __future__ import annotations

import csv
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
from . import kr_market_risk_source_parse as P
from . import kr_market_risk_sources as S
from . import kr_model_portfolio_execution as X

digest, file_hash, import_closure = X.digest, X.file_hash, X.import_closure
ROOT = Path(__file__).resolve().parents[1]
STUDY = M.STUDY
SPEC_PATH = "research_specs/" + STUDY + ".json"
DESIGN_PATH = "research_specs/" + STUDY + "-design.json"
SNAPSHOT_DIR = "data/kr-market-risk-anatomy-v1/sources"
RESULT_PATH = "docs/results/" + STUDY + "-result.json"
MARKER_PATH = "docs/results/" + STUDY + "-execution-started.json"
READINESS_PATH = "docs/results/" + STUDY + "-readiness.json"
SCIENTIFIC_STATUS = M.SCIENTIFIC_STATUS
DECISION_READY = "READY_FOR_MARKET_RISK_ANATOMY_EXECUTION"
DECISION_BLOCKED = "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY"


@dataclass
class Counters:
    """Everything that reads a source VALUE or computes an outcome increments one of these; verify, readiness and a failed gate leave all at zero."""
    valueReads: int = 0
    forwardTargetCalls: int = 0
    episodeCalls: int = 0
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
        raise ValueError("MARKET_RISK_OUTCOME_ACCESS_WITHOUT_PERMIT")
    return permit


# --------------------------------------------------------------------------- #
# Frozen identity
# --------------------------------------------------------------------------- #
def verify_pins(spec, root=ROOT):
    """The frozen design and the source snapshot, byte for byte. Pure hashing and JSON reads of the registry/audit; no price is parsed."""
    root = Path(root)
    design_path = root / DESIGN_PATH
    design = json.loads(design_path.read_text())
    if digest(design) != spec["designSha256"] or design_path.with_suffix(".sha256").read_text().strip() != spec["designSha256"]:
        raise ValueError("FROZEN_DESIGN_CHANGED")
    if design["scientificStatus"] != SCIENTIFIC_STATUS or design["studyId"] != STUDY:
        raise ValueError("SCIENTIFIC_STATUS_OR_STUDY_CHANGED")
    snapshot = root / SNAPSHOT_DIR
    if file_hash(snapshot / "audit.json") != spec["sourcePins"]["auditSha256"]:
        raise ValueError("SOURCE_AUDIT_CHANGED")
    for rel, wanted in spec["sourcePins"]["files"].items():
        if file_hash(snapshot / rel) != wanted:
            raise ValueError("SOURCE_SNAPSHOT_FILE_CHANGED: " + rel)
    if sorted(spec["sourcePins"]["files"]) != sorted(str(p.relative_to(snapshot)) for p in snapshot.rglob("*") if p.is_file() and p.name != "audit.json"):
        raise ValueError("SOURCE_SNAPSHOT_FILE_SET_CHANGED")
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
    verify_pins(spec, root)
    design = json.loads((root / DESIGN_PATH).read_text())
    if design["constants"]["lossCuts"] != list(M.LOSS_CUTS) or design["constants"]["primaryEpisodeThreshold"] != M.PRIMARY_EPISODE_THRESHOLD:
        raise ValueError("MODULE_CONSTANT_DIFFERS_FROM_FROZEN_DESIGN")
    if sorted(design["features"]) != sorted(M.FEATURES) or sorted(design["sources"]) != sorted(S.SOURCES):
        raise ValueError("MODULE_REGISTRY_DIFFERS_FROM_FROZEN_DESIGN")
    return spec, sha


def authorize_execution(spec, sha, root=ROOT, env=None, git=None, lock_probe=None):
    """Raise unless this is a workflow_dispatch on main at a commit carrying exactly this spec, with the frozen design and snapshot matching their pins,
    no committed result or marker and no durable execution lock (an unverifiable lock state refuses)."""
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
    verify_pins(spec, root)                       # input hashes are checked BEFORE any lock
    pin = spec["input"]
    if env.get("MARKET_INPUT_ARTIFACT") != pin["artifactName"] or env.get("MARKET_INPUT_RUN_ID") != str(pin["producingRunId"]):
        raise ValueError("INPUT_ARTIFACT_IDENTITY_MISMATCH")
    if (root / RESULT_PATH).exists():
        raise ValueError("MARKET_RISK_RESULT_ALREADY_COMMITTED")
    if (root / MARKER_PATH).exists():
        raise ValueError("MARKET_RISK_EXECUTION_MARKER_ALREADY_COMMITTED")
    if (lock_probe or (lambda: lock_exists(sha, env)))():
        raise ValueError("EXECUTION_LOCK_ALREADY_EXISTS")
    return ExecutionPermit(sha, _PERMIT_TOKEN)


def _git(args, root):
    return subprocess.check_output(["git", *args], cwd=str(root))


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
# Label-free snapshot access (DATES and metadata only)
# --------------------------------------------------------------------------- #
def snapshot_views(root=ROOT):
    """{source id: {'status','dates','rows','dropped','identityOk'}} from the committed audit and the FIRST COLUMN (date) of each normalized file. No value is
    read or parsed. identityOk is recomputed from the retained vendor identity block by the registered function (see sources.identity_ok)."""
    root = Path(root) / SNAPSHOT_DIR
    audit = json.loads((root / "audit.json").read_text())
    views = {}
    for sid, record in audit["sources"].items():
        if record["status"] != "ACQUIRED":
            views[sid] = {"status": record["status"], "dates": pd.DatetimeIndex([])}
            continue
        with open(root / sid / "normalized.csv", newline="") as stream:
            reader = csv.reader(stream)
            next(reader)
            dates = [row[0] for row in reader]
        views[sid] = {"status": "ACQUIRED", "dates": pd.DatetimeIndex(dates), "rows": record["validRows"] + record["droppedRows"],
                      "dropped": record["droppedRows"], "identityOk": S.identity_ok(S.SOURCES[sid], record.get("identity", {}))}
    return views, audit


def load_series(root, counters, permit, lock, sha):
    """Source VALUES, only after the permit and the durable lock; every read is counted."""
    require_permit(permit)
    require_lock(lock, sha)
    out = {}
    for sid in S.ACQUIRED_IDS:
        path = Path(root) / SNAPSHOT_DIR / sid / "normalized.csv"
        if path.exists():
            counters.valueReads += 1
            out[sid] = AN.obs_series(P.read_normalized(path.read_bytes()))
    return out


def decide(root=ROOT):
    """Label-free decision from dates only: the primary-reference rule, the role sources and the frozen CORE gates."""
    views, audit = snapshot_views(root)
    acquired_on = audit["acquiredOn"]
    sessions = M.kr_sessions("1990-01-02", acquired_on)
    reference = S.select_primary_reference(views, sessions, acquired_on)
    weekly = M.period_end_dates(sessions, "W")
    roles, role_coverage = {}, {}
    for role in S.ROLE_PRIORITY:
        roles[role], role_coverage[role] = S.select_role_source(role, views, sessions, weekly)
    gates = S.core_gates(views, reference, roles, sessions, acquired_on)
    return {"reference": reference, "roles": roles, "roleCoverage": role_coverage, "gates": gates, "sessions": sessions, "views": views, "audit": audit}


def vendor_cross_check_status(views):
    """The same-index vendor cross-check needs VALUES, so it is run only when both KOSPI 200 routes are individually eligible; otherwise it is not needed
    and no value is read."""
    return "NOT_RUN_NO_PAIR_OF_ELIGIBLE_ROUTES"


def reference_diagnostics(views, sessions, acquired_on):
    """For every reference candidate the MEASURED quantity behind each frozen test (dates and counts only): first/last date, staleness at acquisition, share of
    invalid rows, session coverage in the two core windows and over the whole range, and the longest run of missing sessions. Explains a blocker; changes none."""
    out = {}
    for sid in S.REFERENCE_PRIORITY + (S.ROBUSTNESS_REFERENCE,):
        view = views.get(sid)
        entry = S.SOURCES[sid]
        if entry.get("documentedBlocker") or not view or view.get("status") != "ACQUIRED" or len(view["dates"]) == 0:
            out[sid] = {"measured": False, "reason": entry.get("documentedBlocker") or "NOT_ACQUIRED"}
            continue
        dates = pd.DatetimeIndex(view["dates"])
        last = dates.max()
        out[sid] = {"measured": True, "role": entry["role"], "family": entry["family"], "firstDate": str(dates.min().date()), "lastDate": str(last.date()),
                    "staleDaysAtAcquisition": int((pd.Timestamp(acquired_on) - last).days), "freshnessLimitDays": S.REFERENCE_FRESHNESS_DAYS,
                    "droppedRowShare": round(view["dropped"] / max(view["rows"], 1), 6), "droppedRowShareLimit": S.REFERENCE_MAX_DROPPED_SHARE,
                    "sessionCoverage": {k: M.session_coverage(dates, sessions, a, b) for k, (a, b) in S.CORE_WINDOWS.items()},
                    "fullRangeCoverageFrom2006": M.session_coverage(dates, sessions, "2006-01-01", str(last.date())),
                    "longestMissingRunFrom2006": S.max_consecutive_missing(dates, sessions, "2006-01-01", str(last.date())),
                    "eligibleAsPrimary": entry["role"] == "KR_REFERENCE"}
    return out


def extended_tier_audit(root=ROOT):
    """Structural, label-free readiness of EXTENDED_KR_INTERNALS: the PIT Top120 schedule that is committed and the preserved raw-input artifact pin. Value
    coverage (prices, market caps) is measured at execution; an internals statistic is missing whenever any PIT member lacks its input."""
    from .kr_industry_membership import top120_schedule
    root = Path(root)
    inputs = json.loads((root / "data/kr-industry-membership-foundation-v1/top120-inputs.json").read_text())
    schedule = sorted(top120_schedule(inputs)[0])
    spec = json.loads((root / SPEC_PATH).read_text())
    return {"tier": "EXTENDED_KR_INTERNALS", "requiredForDecision": False, "pitSignalDates": len(schedule), "firstPitSignalDate": schedule[0], "lastPitSignalDate": schedule[-1],
            "rawInputArtifact": {k: spec["input"][k] for k in ("artifactName", "artifactId", "producingRunId", "artifactArchiveSha256")},
            "status": "STRUCTURALLY_READY_VALUE_COVERAGE_MEASURED_AT_EXECUTION", "neverReconstructedFromTodaysConstituents": True,
            "startsMateriallyLaterThanCore": True}


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
    series = load_series(root, counters, permit, lock, sha)
    primary = decision["reference"]["primary"]
    lag_of = S.lag_days
    counters.forwardTargetCalls += 1
    counters.episodeCalls += 1
    panel = AN.build_core_panel(series[primary], {k: v for k, v in series.items() if k != primary}, decision["roles"], lag_of)
    extended = extended_builder(input_root, panel, spec, root) if extended_builder and input_root else None
    counters.analysisCalls += 1
    result = {"studyId": STUDY, "scientificStatus": SCIENTIFIC_STATUS, "primaryReference": {k: decision["reference"][k] for k in ("primary", "family", "basis", "instrument", "composite")},
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


def extended_internals(input_root, panel, spec, root=ROOT):
    """EXTENDED_KR_INTERNALS on the PIT Top120 schedule from the preserved raw-input artifact: per weekly PIT date, the members' 63-session return, SMA200 state
    and signal-date market cap through the pure `internals_features`. A statistic is missing whenever ANY member lacks its input (never zero, never
    renormalised). `int_breadth_deterioration_63` uses the breadth of the latest PIT snapshot at or before the session 63 sessions earlier. Returns a daily-grid
    frame (NaN off the PIT dates). Only called after the lock."""
    import numpy as np
    from .kr_industry_membership import top120_schedule
    v1_spec, _ = X.load_spec(root)
    _, memberships, market, prices = X.load_sources(input_root, v1_spec)
    inputs = json.loads((Path(root) / "data/kr-industry-membership-foundation-v1/top120-inputs.json").read_text())
    schedule = [d for d in sorted(top120_schedule(inputs)[0]) if pd.Timestamp(d) in panel["sessions"]]
    sessions = panel["sessions"]
    closes = {t: pd.to_numeric(f["Close"], errors="coerce").reindex(sessions).to_numpy(float) for t, f in prices.items()}
    columns = [n for n in M.FEATURES if n.startswith("int_")]
    frame = pd.DataFrame(np.nan, index=sessions, columns=columns)
    for date in schedule:
        pos = sessions.get_loc(pd.Timestamp(date))
        members = memberships.on(date)["members"]
        r63, above, caps = [], [], []
        for t in members:
            c = closes.get(t)
            ok = c is not None and pos >= 199
            window = c[pos - 199:pos + 1] if ok else None
            valid = ok and np.isfinite(window).all() and (window > 0).all()
            r63.append(float(c[pos] / c[pos - 63] - 1.0) if valid else np.nan)
            above.append(float(c[pos] > window.mean()) if valid else np.nan)
            quote = market.at(t, date)
            caps.append(float(quote["marketCap"]) if quote and quote.get("marketCap") else np.nan)
        for name, value in M.internals_features(r63, above, caps).items():
            frame.at[pd.Timestamp(date), name] = value
    breadth = frame["int_breadth_above_sma200"]
    pit_dates = pd.DatetimeIndex([pd.Timestamp(d) for d in schedule])
    for date in pit_dates:
        pos = sessions.get_loc(date)
        if pos >= 63:
            earlier = pit_dates[pit_dates <= sessions[pos - 63]]
            if len(earlier):
                frame.at[date, "int_breadth_deterioration_63"] = breadth.loc[date] - breadth.loc[earlier[-1]]
    return frame


# --------------------------------------------------------------------------- #
# Outcome-free readiness report
# --------------------------------------------------------------------------- #
def readiness_audit(root=ROOT):
    """READY_FOR_MARKET_RISK_ANATOMY_EXECUTION or DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY from identities, structure and observation DATES alone. It never
    parses a price, rate or forward quantity, and the counters prove it. A blocked decision lists the exact blockers; the study is never redefined."""
    root = Path(root)
    counters = Counters()
    checks, details = {}, {}
    spec = sha = None
    try:
        spec, sha = load_spec(root)
        checks["frozenSpecDesignSnapshotAndImportClosure"] = True
    except (ValueError, KeyError, OSError) as error:
        checks["frozenSpecDesignSnapshotAndImportClosure"], details["frozenSpecDesignSnapshotAndImportClosure"] = False, str(error)
    out = {"studyId": STUDY, "mode": "readiness", "specSha256": sha, "counters": asdict(counters), "basedOnAnyReturnResult": False, "historicalExecutionPerformed": False,
           "scientificStatus": SCIENTIFIC_STATUS}
    if spec is None:
        return {**out, "decision": DECISION_BLOCKED, "checks": checks, "details": details, "blockers": ["FROZEN_IDENTITY_NOT_VERIFIED"]}
    decided = decide(root)
    views, audit = decided["views"], decided["audit"]
    checks["noOutcomeAccess"] = counters.zero()
    checks["sourceRegistryIsPredictorEligibleOnly"] = S.validate_registry()
    gates = decided["gates"]
    out.update(
        decision=gates["decision"], checks=checks, details=details, blockers=gates["blockers"], gates=gates["gates"], primaryReference=decided["reference"], roleSources=decided["roles"],
        roleCoverage=decided["roleCoverage"], coreCoverageTables=gates["coverage"], sourceCoverage=AN.coverage_tables(views, decided["sessions"], decided["roles"]),
        referenceDiagnostics=reference_diagnostics(views, decided["sessions"], audit["acquiredOn"]), vendorCrossCheck=vendor_cross_check_status(views), extendedTier=extended_tier_audit(root), acquiredOn=audit["acquiredOn"],
        sourceInventory={sid: {"status": audit["sources"][sid]["status"], "firstDate": audit["sources"][sid].get("firstDate"), "lastDate": audit["sources"][sid].get("lastDate"),
                               "validRows": audit["sources"][sid].get("validRows"), "droppedRows": audit["sources"][sid].get("droppedRows"),
                               "identityOkAsRecorded": audit["sources"][sid].get("identityOk"),
                               "identityOkByRegisteredFunction": views[sid].get("identityOk"), "vintageClass": S.SOURCES[sid]["vintageClass"]} for sid in audit["sources"]},
        excludedRevisedOrUnbuiltInputs={sid: {"vintageClass": S.SOURCES[sid]["vintageClass"], "reason": S.SOURCES[sid]["excluded"]} for sid in S.EXCLUDED_IDS},
        documentedBlocker={sid: S.SOURCES[sid]["documentedBlocker"] for sid in S.SOURCES if S.SOURCES[sid].get("documentedBlocker")},
        earliestDefensibleCoreHistoryDate=None if gates["decision"] != DECISION_READY else min(str(v["dates"].min().date()) for sid, v in views.items() if sid == decided["reference"]["primary"]),
        covers2008=bool(decided["reference"].get("primary")) and gates["gates"].get("REFERENCE_GFC_2007_2009", {}).get("pass", False))
    return out
