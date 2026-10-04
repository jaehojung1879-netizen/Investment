"""KR stock-within-industry anatomy v1 — frozen identity, one-shot lock, label-free assembly and (later) execution.

EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY. This module is PROTOCOL AND HARNESS. On pull requests only `verify` and
`readiness_audit` run; neither reads a price endpoint, a forward return or any outcome. `execute` exists but refuses unless a
workflow_dispatch on merged main carries this exact committed spec, names the exact preserved raw artifact, passes every readiness
gate and then wins a durable exclusive git-tag lock created BEFORE the first outcome is read.

It never reruns a sealed study (kr-model-overlay-portfolio-v1, kr-factor-anatomy-v1, kr-top120-regime-review-v1,
kr-industry-opportunity-anatomy-v1), never contacts KRX, DART or KIND, and reads the sealed factor-anatomy result only as a
pinned REFERENCE for an interpretive comparison.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from . import kr_factor_anatomy as A
from . import kr_factor_anatomy_execution as AE
from . import kr_industry_anatomy_execution as IE
from . import kr_model_portfolio_execution as X
from . import kr_stock_within_industry_anatomy as S
from . import kr_value_quality_catalyst as F
from . import replay_calendar as RC

digest, file_hash, import_closure = X.digest, X.file_hash, X.import_closure
ROOT = Path(__file__).resolve().parents[1]
STUDY = S.STUDY
SPEC_PATH = "research_specs/" + STUDY + ".json"
RESULT_PATH = "docs/results/" + STUDY + "-result.json"
MARKER_PATH = "docs/results/" + STUDY + "-execution-started.json"
READINESS_PATH = "docs/results/" + STUDY + "-readiness.json"
SCIENTIFIC_STATUS = S.SCIENTIFIC_STATUS
V4 = IE.V4


@dataclass
class Counters:
    """Everything that reads an outcome (or a sealed result's contents) increments one of these. `verify`, the readiness audit and a
    failed gate leave all at zero."""
    targetCalls: int = 0
    labelCalls: int = 0
    outcomeColumnCalls: int = 0
    analysisCalls: int = 0
    markerWrites: int = 0
    priorResultReads: int = 0

    def zero(self):
        return all(v == 0 for v in asdict(self).values())


@dataclass(frozen=True)
class ExecutionPermit:
    specSha256: str
    token: object


_PERMIT_TOKEN = object()


def require_permit(permit):
    if not isinstance(permit, ExecutionPermit) or permit.token is not _PERMIT_TOKEN:
        raise ValueError("STOCK_WITHIN_INDUSTRY_OUTCOME_ACCESS_WITHOUT_PERMIT")
    return permit


# --------------------------------------------------------------------------- #
# Frozen identity
# --------------------------------------------------------------------------- #
def verify_pins(spec, root=ROOT):
    """Membership, taxonomy, benchmark, feature-definition and prior-sealed identities exactly as preregistered. File hashing and JSON
    reads of FROZEN SPECS only: no sealed result is parsed here, no price or outcome is touched."""
    root = Path(root)
    IE.verify_pins(spec, root)       # v4 membership bytes, crosswalk shape, v4 decision, benchmark/return basis, raw-input pin
    anatomy = json.loads((root / "research_specs/kr-factor-anatomy-v1.json").read_text())
    registered = [{k: f[k] for k in ("name", "family", "orientation", "plain", "caveat")} for f in anatomy["factors"]]
    if registered != spec["features"]["definitions"]:
        raise ValueError("FEATURE_DEFINITIONS_DIFFER_FROM_SEALED_FACTOR_ANATOMY")
    if [f["name"] for f in registered] != list(F.RAW_FEATURES) or list(S.FEATURES) != spec["features"]["names"]:
        raise ValueError("FEATURE_LIST_DIFFERS_FROM_REPOSITORY_RAW_FEATURES")
    if {f["name"]: f["family"] for f in registered} != {n: fam for fam, names in F.FAMILIES.items() for n in names}:
        raise ValueError("FEATURE_FAMILIES_DIFFER_FROM_REPOSITORY")
    if anatomy["horizons"] != [126, 252] or anatomy["developmentCutoff"] != spec["developmentCutoff"]:
        raise ValueError("CALENDAR_CONVENTION_DIFFERS_FROM_SEALED_FACTOR_ANATOMY")
    for rel, wanted in spec["priorSealed"]["resultFiles"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("PRIOR_SEALED_RESULT_CHANGED: " + rel)
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
    frozen = {"horizons": list(S.HORIZONS), "primaryHorizon": S.PRIMARY_HORIZON, "minIndustryMembers": S.MIN_INDUSTRY_MEMBERS,
              "minPeers": S.MIN_PEERS, "minRankPeers": S.MIN_RANK_PEERS, "minDateCrossSection": S.MIN_DATE_CROSS_SECTION,
              "minStratumCrossSection": S.MIN_STRATUM_CROSS_SECTION, "minGroupSize": S.MIN_GROUP_SIZE,
              "minGroupIndustryN": S.MIN_GROUP_INDUSTRY_N, "minIndustriesPerDate": S.MIN_INDUSTRIES_PER_DATE,
              "minSliceDates": S.MIN_SLICE_DATES, "minValidDatesForLabel": S.MIN_VALID_DATES_FOR_LABEL, "nearZeroIc": S.NEAR_ZERO_IC,
              "survivesRatio": S.SURVIVES_RATIO, "weakensRatio": S.WEAKENS_RATIO, "annualMinDates": S.ANNUAL_MIN_DATES,
              "minSignViews": S.MIN_SIGN_VIEWS}
    for key, value in frozen.items():
        if spec["constants"][key] != value:
            raise ValueError("MODULE_CONSTANT_DIFFERS_FROM_SPEC: " + key)
    registries = {"weightLenses": list(S.WEIGHT_LENSES), "components": list(S.COMPONENTS), "featureLenses": list(S.FEATURE_LENSES),
                  "sensitivities": list(S.SENSITIVITIES), "slices": list(S.SLICES), "benchmarkStates": list(S.BENCHMARK_STATES)}
    for key, value in registries.items():
        if spec["registry"][key] != value:
            raise ValueError("MODULE_REGISTRY_DIFFERS_FROM_SPEC: " + key)
    if spec["registry"]["signViews"] != [list(v) for v in S.SIGN_VIEWS]:
        raise ValueError("MODULE_REGISTRY_DIFFERS_FROM_SPEC: signViews")
    if spec["registry"]["questions"] != {k: list(v) for k, v in S.QUESTIONS.items()}:
        raise ValueError("MODULE_REGISTRY_DIFFERS_FROM_SPEC: questions")
    return spec, sha


def authorize_execution(spec, sha, root=ROOT, env=None, git=None, lock_probe=None):
    """Raise unless this is a workflow_dispatch on main at a commit carrying exactly this spec, naming exactly the preserved raw artifact,
    with no committed result or marker and no durable execution lock (an unverifiable lock state refuses)."""
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
    verify_pins(spec, root)
    pin = spec["input"]
    if env.get("ANATOMY_INPUT_ARTIFACT") != pin["artifactName"] or env.get("ANATOMY_INPUT_RUN_ID") != str(pin["producingRunId"]):
        raise ValueError("INPUT_ARTIFACT_IDENTITY_MISMATCH")
    if (root / RESULT_PATH).exists():
        raise ValueError("STOCK_WITHIN_INDUSTRY_RESULT_ALREADY_COMMITTED")
    if (root / MARKER_PATH).exists():
        raise ValueError("STOCK_WITHIN_INDUSTRY_EXECUTION_MARKER_ALREADY_COMMITTED")
    if (lock_probe or (lambda: lock_exists(sha, env)))():
        raise ValueError("EXECUTION_LOCK_ALREADY_EXISTS")
    return ExecutionPermit(sha, _PERMIT_TOKEN)


def _git(args, root):
    return subprocess.check_output(["git", *args], cwd=str(root))


def verify(root=ROOT, env=None):
    """Outcome-free: identity, closure and pins. The only mode ordinary pull-request CI runs."""
    spec, sha = load_spec(root)
    counters = Counters()
    try:
        authorize_execution(spec, sha, root, env)
        authorized = True
    except (ValueError, subprocess.CalledProcessError, OSError, KeyError):
        authorized = False
    return {"studyId": STUDY, "mode": "verify", "status": "VERIFIED", "specSha256": sha, "scientificStatus": spec["scientificStatus"],
            "executeAuthorizedInThisEnvironment": authorized, "dependencyFiles": len(spec["dependencyHashes"]),
            "counters": asdict(counters), "stoppedBeforeOutcomes": counters.zero(), "historicalExecutionPerformed": False}


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
    """Exclusive create after identities and readiness gates passed and before ANY outcome is read. Only POST and GET are issued."""
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
# Label-free assembly
# --------------------------------------------------------------------------- #
def readiness_gates(features, schedule, intervals, spec, v4_schedule):
    """Label-free reasons the study cannot run; empty means ready. The sealed industry-study gates plus every registered feature column."""
    reasons = [r for r in IE.readiness_gates(features, schedule, intervals, spec, v4_schedule) if not r.startswith("SIGNAL_TIME_COLUMNS_MISSING")]
    missing = [c for c in ("marketCap",) + S.FEATURES if c not in features.columns]
    if missing and not features.empty:
        reasons.append("SIGNAL_TIME_COLUMNS_MISSING: " + ",".join(missing))
    return reasons


def forward_table(prices, schedule, days, spec, v1_spec, permit, counters, lock, sha):
    """Per signal date, per member, per horizon: (stock, benchmark, status). Requires permit AND lock; counts every read.
    Identical endpoint rule and terminal discipline to the accepted anatomy (cross-checked name by name against the sealed v1 target)."""
    require_permit(permit)
    require_lock(lock, sha)
    foundation = json.loads((ROOT / v1_spec["inputs"]["terminalFoundationPath"]).read_text())
    complete = {row["code"] + ".KS": row.get("completeness") for row in foundation.get("securities", [])}
    target_from_sessions = AE.sealed_v1_function("target_from_sessions")
    attach_eligibility = AE.sealed_v1_function("attach_eligibility")
    table, windows = {}, {}
    for h in S.HORIZONS:
        for date, tickers in schedule.items():
            records = []
            for ticker in tickers:
                counters.outcomeColumnCalls += 1
                mine = A.endpoint_returns(days, prices, spec["benchmark"], ticker, date, h, spec["developmentCutoff"])
                counters.targetCalls += 1
                theirs = target_from_sessions(days, prices, spec["benchmark"], ticker, date, h, spec["developmentCutoff"])
                counters.labelCalls += 1
                if (mine["status"] != theirs["labelStatus"] or mine["entryDate"] != theirs["entryDate"] or mine["exitDate"] != theirs["outcomeEndDate"]
                        or (mine["status"] == "MATURED" and abs(mine["relativeReturn"] - theirs["forwardRelativeReturn"]) > 1e-12)):
                    raise ValueError("ENDPOINT_SEMANTICS_DIFFER_FROM_V1_TARGET")
                records.append(mine)
            frame = pd.DataFrame(records)
            elig = attach_eligibility(pd.DataFrame({"ticker": tickers, "outcomeEndDate": frame.exitDate}), prices, complete)
            status = frame.status.where(~(frame.status.eq("MATURED") & ~elig.eligibilityStatus.eq("ELIGIBLE")), "UNRESOLVED_TERMINAL_OR_DISTRIBUTION_EVIDENCE")
            table[(date, h)] = {t: (r, b, s) for t, r, b, s in zip(tickers, frame.stockReturn.astype(float), frame.benchmarkReturn.astype(float), status)}
            windows[(date, h)] = (frame.entryDate.iloc[0], frame.exitDate.iloc[0]) if len(frame) else (None, None)
    return table, windows


def write_execution_marker(output, spec, sha, identity, counters, lock=None):
    counters.markerWrites += 1
    document = {"studyId": STUDY, "specSha256": sha, "inputIdentitySha256": identity["sha256"],
                "lockRef": None if lock is None else lock.ref, "lockedMainSha": None if lock is None else lock.mainSha, "outcomesReadBeforeThisMarker": 0}
    X.atomic_write(Path(output) / "execution-started.json", document, immutable=True)
    return document


def load_prior_result(root, spec, permit, counters):
    """The sealed factor-anatomy result as a pinned REFERENCE (its hash was verified by `verify_pins`). Read, never recomputed."""
    require_permit(permit)
    counters.priorResultReads += 1
    return json.loads((Path(root) / spec["priorSealed"]["referenceResult"]).read_text())


def execute(input_root, output, spec, sha, permit, root=ROOT, env=None, api=github_api):
    """Order: permit -> input identity -> pins -> label-free assembly -> readiness gates -> DURABLE LOCK -> marker -> outcomes -> tables.
    A failure before the lock spends nothing; a failure after it consumes the study."""
    require_permit(permit)
    if permit.specSha256 != sha:
        raise ValueError("PERMIT_FOR_A_DIFFERENT_SPEC")
    counters = Counters()
    identity = X.input_identity(input_root)
    if identity["sha256"] != spec["input"]["identitySha256"]:
        raise ValueError("INPUT_IDENTITY_MISMATCH")
    verify_pins(spec, root)
    v1_spec, _ = X.load_spec(root)
    bundle = X.prepare(input_root, v1_spec)
    A.assert_pit_membership(bundle["features"], AE.load_memberships(input_root, v1_spec))
    features = bundle["features"].copy().reset_index(drop=True)
    market = bundle["market"]
    features["marketCap"] = [(market.at(t, d) or {}).get("marketCap", np.nan) for t, d in zip(features.ticker, features.date)]
    schedule = IE.schedule_from_features(features)
    intervals, crosswalk, ends = IE.load_membership_inputs(root)
    from .kr_industry_membership import top120_schedule
    inputs = json.loads((Path(root) / "data/kr-industry-membership-foundation-v1/top120-inputs.json").read_text())
    v4_schedule = {d: [n[4:] if n.startswith("KRX:") else n for n in names] for d, names in top120_schedule(inputs)[0].items()}
    reasons = readiness_gates(features, schedule, intervals, spec, v4_schedule)
    if reasons:
        Path(output).mkdir(parents=True, exist_ok=True)
        X.atomic_write(Path(output) / "gates-failed.json", {"studyId": STUDY, "reasons": reasons, "counters": asdict(counters)})
        raise ValueError("READINESS_GATE_FAILED: " + ";".join(reasons))
    days = RC.sessions("2013-01-01", "2028-12-31", "KR")
    membership = IE.I.membership_table(schedule, intervals, crosswalk, ends)
    risk = {d: (bundle["overlay"].get(d) or {}).get("riskMultiplier") for d in schedule}
    lock = claim_execution_lock(sha, env, api)
    write_execution_marker(output, spec, sha, identity, counters, lock)
    forward, windows = forward_table(bundle["prices"], schedule, days, spec, v1_spec, permit, counters, lock, sha)
    counters.analysisCalls += 1
    panels = {name: S.build_stock_panel(membership, features, forward, windows, exclude=S.EXCLUDED_MEGA_CAPS if name != "FULL" else (), risk=risk)
              for name in S.SENSITIVITIES}
    for panel in panels.values():
        S.assert_identity(panel)
    prior = load_prior_result(root, spec, permit, counters)
    result = {"studyId": STUDY, "scientificStatus": SCIENTIFIC_STATUS, "returnBasis": S.RETURN_BASIS, "benchmark": spec["benchmark"],
              **S.analyze_all(panels, spec, prior)}
    return write_outputs(output, result, panels, spec, sha, identity, counters)


def write_outputs(output, result, panels, spec, sha, identity, counters):
    out = Path(output)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    files = {"stock-within-industry-anatomy.json": X.atomic_write(out / "stock-within-industry-anatomy.json", AE.json_safe(result))}
    for name, panel in sorted(panels.items()):
        data = AE._gzip_csv(panel)
        (out / "tables" / (name.lower() + ".csv.gz")).write_bytes(data)
        files["tables/" + name.lower() + ".csv.gz"] = hashlib.sha256(data).hexdigest()
    manifest = {"studyId": STUDY, "specSha256": sha, "inputIdentitySha256": identity["sha256"], "scientificStatus": SCIENTIFIC_STATUS,
                "returnBasis": S.RETURN_BASIS, "counters": asdict(counters), "files": files}
    X.atomic_write(out / "manifest.json", AE.json_safe(manifest))
    return manifest


# --------------------------------------------------------------------------- #
# Outcome-free readiness audit
# --------------------------------------------------------------------------- #
def committed_membership(root=ROOT):
    """The frozen v4 membership as a (date, ticker, industry, membershipStatus) table: committed files only, no price, cap or return."""
    from .kr_industry_membership import top120_schedule
    root = Path(root)
    intervals, crosswalk, ends = IE.load_membership_inputs(root)
    inputs = json.loads((root / "data/kr-industry-membership-foundation-v1/top120-inputs.json").read_text())
    schedule = {d: [n[4:] if n.startswith("KRX:") else n for n in names] for d, names in top120_schedule(inputs)[0].items()}
    return IE.I.membership_table(schedule, intervals, crosswalk, ends)


def readiness_audit(root=ROOT):
    """READY_FOR_STOCK_WITHIN_INDUSTRY_ANATOMY_EXECUTION or DATA_BLOCKED_BEFORE_STOCK_WITHIN_INDUSTRY_ANATOMY from structure, identity and
    the frozen membership only. It never touches a price, a market-cap value, a forward return or any outcome, and the counters prove it.
    Cap availability and terminal completeness of peers are outcome-time facts: they are measured at execution and stated as unmeasured."""
    root = Path(root)
    counters = Counters()
    checks, details = {}, {}

    def check(name, fn):
        try:
            result = fn()
            checks[name] = True if result in (True, None) else bool(result)
            if result not in (True, None, False):
                details[name] = result
        except (ValueError, KeyError, OSError, AssertionError) as error:
            checks[name] = False
            details[name] = str(error)

    spec = sha = None
    eligibility = {}
    try:
        spec, sha = load_spec(root)
        checks["frozenSpecAndImportClosure"] = True
    except (ValueError, KeyError, OSError) as error:
        checks["frozenSpecAndImportClosure"], details["frozenSpecAndImportClosure"] = False, str(error)
    if spec is not None:
        check("membershipTaxonomyBenchmarkFeatureAndPriorSealedPins", lambda: verify_pins(spec, root))
        v1 = json.loads((root / "research_specs/kr-model-overlay-portfolio-v1.json").read_text())
        check("rawInputArtifactPinnedWithDigest", lambda: bool(spec["input"]["artifactArchiveSha256"]) and spec["input"]["identitySha256"] == "233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7")
        check("priceInputsPinnedByReplayManifest", lambda: bool(v1["inputs"].get("replayManifestSha256")) and not v1["inputs"].get("replaceSilently", False))
        check("marketCapInputPinnedByKrxCacheDigest", lambda: bool(spec["input"].get("krxCacheSha256")))
        check("pitAccountingSnapshotPinnedByContentDigest", lambda: bool(v1["inputs"]["accounting"]["contentSha256"]) and len(v1["inputs"]["accounting"]["gitBlobSha1"]) >= 10)
        check("v4TerminalLimitationRecordedNotHidden", lambda: spec["membership"]["v4Facts"]["terminal"] == {"classified": 0, "denominator": 2345})
        check("noRecollectionRequired", lambda: spec["input"]["recollect"] is False)

        def membership_audit():
            membership = committed_membership(root)
            for name in S.SENSITIVITIES:
                eligibility[name] = S.membership_eligibility(membership, S.EXCLUDED_MEGA_CAPS if name != "FULL" else ())
            return (eligibility["FULL"]["eligibleStocksPerDate"]["min"] >= S.MIN_INDUSTRY_MEMBERS
                    and eligibility["FULL"]["datesWithAtLeastMinDateCrossSection"] >= S.MIN_VALID_DATES_FOR_LABEL)
        check("membershipEligibilityMeetsFrozenMinimumsOnCommittedMembership", membership_audit)
    check("deterministicConstruction", _synthetic_determinism)
    check("syntheticHarnessEndToEnd", _synthetic_end_to_end)
    check("noOutcomeAccess", lambda: counters.zero())
    check("syntheticTestsPresent", lambda: (root / "tests/test_kr_stock_within_industry_anatomy_v1.py").is_file()
          and (root / "tests/test_kr_stock_within_industry_anatomy_execution_v1.py").is_file())
    ready = all(checks.values())
    return {"studyId": STUDY, "mode": "readiness",
            "decision": "READY_FOR_STOCK_WITHIN_INDUSTRY_ANATOMY_EXECUTION" if ready else "DATA_BLOCKED_BEFORE_STOCK_WITHIN_INDUSTRY_ANATOMY",
            "checks": checks, "details": details, "specSha256": sha, "counters": asdict(counters), "basedOnAnyReturnResult": False,
            "membershipOnlyEligibility": eligibility,
            "notMeasuredBeforeExecution": ["signal-date market-cap availability of every peer (cap lens)", "matured-return completeness of every peer under the terminal discipline",
                                           "feature finiteness per date and industry", "any forward return"],
            "historicalExecutionPerformed": False, "scientificStatus": SCIENTIFIC_STATUS}


def _synthetic_membership(n=6, label="반도체 제조업"):
    tickers = [f"S{i}.KS" for i in range(n)]
    schedule = {"2020-01-03": tickers}
    intervals = {t: [{"start": None, "end": None, "label": label, "status": "RECONSTRUCTED_STABLE_NO_CHANGE_EVENT",
                      "reconstruction_status": "RECONSTRUCTED_STABLE_NO_CHANGE_EVENT"}] for t in tickers}
    crosswalk = {"mapping": {"반도체제조업": "ELECTRONICS_ELECTRICAL"}}
    return tickers, IE.I.membership_table(schedule, intervals, crosswalk)


def _synthetic_determinism():
    """Two builds of the same synthetic cohort must be identical (no clock, no randomness, order-independent)."""
    tickers, membership = _synthetic_membership()
    first = S.build_cohorts(membership)
    second = S.build_cohorts(membership.iloc[::-1].reset_index(drop=True))
    return first == second and next(iter(first.values()))["status"] == "ELIGIBLE"


def _synthetic_end_to_end():
    """A tiny SYNTHETIC panel (invented returns) through the panel builder and the identity check: proves the machinery runs without data."""
    tickers, membership = _synthetic_membership()
    date = "2020-01-03"
    features = pd.DataFrame({"date": date, "ticker": tickers, "marketCap": [float(i + 1) for i in range(6)],
                             **{c: [float(i) for i in range(6)] for c in S.FEATURES}})
    forward = {(date, h): {t: (0.01 * (i + 1), 0.005, "MATURED") for i, t in enumerate(tickers)} for h in S.HORIZONS}
    windows = {(date, h): ("2020-01-06", "2020-12-31") for h in S.HORIZONS}
    panel = S.build_stock_panel(membership, features, forward, windows)
    return S.assert_identity(panel) and int(panel.status.eq("ELIGIBLE").sum()) == 6
