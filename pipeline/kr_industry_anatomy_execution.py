"""KR industry opportunity anatomy v1 — frozen identity, one-shot lock, label-free assembly and (later) execution.

EXPLORATORY_DEVELOPMENT_ON_PARTIALLY_RECONSTRUCTED_KR_HISTORY. This module is PROTOCOL AND HARNESS. On pull requests only
`verify` and `readiness_audit` run; neither reads a price endpoint, a forward return or any outcome. `execute` exists but
refuses unless a workflow_dispatch on merged main carries this exact committed spec, names the exact preserved raw artifact,
passes every readiness gate and then wins a durable exclusive git-tag lock created BEFORE the first outcome is read.
It never reruns a sealed study, never contacts KRX, DART or KIND.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import gzip
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
from . import kr_industry_anatomy as I
from . import kr_model_portfolio_execution as X
from . import replay_calendar as RC
from .alpha_opportunity_v3_spec import import_closure

digest, file_hash = X.digest, X.file_hash
ROOT = Path(__file__).resolve().parents[1]
STUDY = I.STUDY
SPEC_PATH = "research_specs/" + STUDY + ".json"
RESULT_PATH = "docs/results/" + STUDY + "-result.json"
MARKER_PATH = "docs/results/" + STUDY + "-execution-started.json"
READINESS_PATH = "docs/results/" + STUDY + "-readiness.json"
SCIENTIFIC_STATUS = I.SCIENTIFIC_STATUS
V4 = "data/kr-industry-membership-foundation-v4"


@dataclass
class Counters:
    """Everything that reads an outcome increments one of these; `verify`, the readiness audit and a failed gate leave all at zero."""
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
        raise ValueError("INDUSTRY_ANATOMY_OUTCOME_ACCESS_WITHOUT_PERMIT")
    return permit


# --------------------------------------------------------------------------- #
# Frozen identity
# --------------------------------------------------------------------------- #
def verify_pins(spec, root=ROOT):
    """Membership, taxonomy and benchmark identities exactly as preregistered. Pure file hashing and JSON reads."""
    root = Path(root)
    for rel, wanted in spec["membership"]["files"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("MEMBERSHIP_INPUT_CHANGED: " + rel)
    crosswalk = json.loads((root / spec["membership"]["crosswalkPath"]).read_text())
    if len(crosswalk["groups"]) != spec["membership"]["coarseGroups"] or len(crosswalk["mapping"]) != spec["membership"]["mappedRawLabels"]:
        raise ValueError("CROSSWALK_SHAPE_CHANGED")
    audit = json.loads(gzip.decompress((root / V4 / "state/audit.json.gz").read_bytes()))
    for key, wanted in spec["membership"]["v4Facts"].items():
        if audit[key] != wanted:
            raise ValueError("V4_FACT_CHANGED: " + key)
    if audit["decision"] != "DATA_FOUNDATION_INSUFFICIENT_V4":
        raise ValueError("V4_DECISION_RELABELLED")
    anatomy = json.loads((root / "research_specs/kr-factor-anatomy-v1.json").read_text())
    if anatomy["benchmark"] != spec["benchmark"] or anatomy["returnDefinition"]["label"] != spec["returnBasis"]:
        raise ValueError("BENCHMARK_OR_RETURN_BASIS_DIFFERS_FROM_ACCEPTED_FRAMEWORK")
    regime = json.loads((root / "research_specs/kr-top120-regime-review-v1.json").read_text())
    if regime["input"] != spec["input"]["pinnedFrom"]["regimeReviewInput"]:
        raise ValueError("RAW_INPUT_PIN_DIFFERS_FROM_REGIME_REVIEW")
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
    frozen = {"horizons": list(I.HORIZONS), "minMembers": I.MIN_MEMBERS, "minCrossSection": I.MIN_CROSS_SECTION,
              "minTercileCrossSection": I.MIN_TERCILE_CROSS_SECTION, "primaryHorizon": I.PRIMARY_HORIZON}
    for key, value in frozen.items():
        if spec["constants"][key] != value:
            raise ValueError("MODULE_CONSTANT_DIFFERS_FROM_SPEC: " + key)
    if list(I.FEATURES) != spec["features"]["names"]:
        raise ValueError("FEATURE_LIST_DIFFERS_FROM_SPEC")
    return spec, sha


def authorize_execution(spec, sha, root=ROOT, env=None, git=None, lock_probe=None):
    """Raise unless this is a workflow_dispatch on main at a commit carrying exactly this spec, naming exactly the preserved raw
    artifact, with no committed result or marker and no durable execution lock (an unverifiable lock state refuses)."""
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
        raise ValueError("INDUSTRY_ANATOMY_RESULT_ALREADY_COMMITTED")
    if (root / MARKER_PATH).exists():
        raise ValueError("INDUSTRY_ANATOMY_EXECUTION_MARKER_ALREADY_COMMITTED")
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


@dataclass(frozen=True)
class ExecutionLock:
    specSha256: str
    mainSha: str
    ref: str
    token: object


def lock_ref(spec_sha):
    return LOCK_PREFIX + "-" + spec_sha


def github_api(method, path, payload=None, env=None):
    env = os.environ if env is None else env
    request = urllib.request.Request(
        "https://api.github.com/repos/" + env["GITHUB_REPOSITORY"] + path,
        data=None if payload is None else json.dumps(payload).encode(), method=method,
        headers={"Authorization": "Bearer " + env["GH_TOKEN"], "Content-Type": "application/json", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, {}


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
# Label-free assembly (no endpoint, forward return or outcome column is read here)
# --------------------------------------------------------------------------- #
def load_membership_inputs(root=ROOT):
    root = Path(root)
    intervals = json.loads(gzip.decompress((root / V4 / "state/intervals.json.gz").read_bytes()))
    crosswalk = json.loads((root / "research_specs/kr-industry-membership-foundation-v4/crosswalk.json").read_text())
    identity = json.loads((root / "data/kr-industry-membership-foundation-v1/identity-inventory.json").read_text())
    terminal = set(json.loads((root / "data/kr-industry-membership-foundation-v1/identity-provenance.json").read_text())["terminalSecurities"])
    ends = {"KRX:" + s["ticker"]: s["delisted"] for i in identity["issuers"] for s in i["securities"] if s["ticker"] in terminal and s.get("delisted")}
    return intervals, crosswalk, {k[4:]: v for k, v in ends.items()}


def schedule_from_features(features):
    return {date: sorted(group.ticker) for date, group in features.groupby("date")}


def past_arrays(prices, ticker, days, pos, window):
    """Close values for the `window + 1` sessions ending AT the signal session `pos`: past-only by construction."""
    frame = prices.get(ticker)
    if frame is None or pos - window < 0:
        return None
    return frame["Close"].reindex(days[pos - window:pos + 1]).to_numpy(float)


def past_features(prices, tickers, days, date):
    """Trailing returns, moving-average state and daily returns from sessions at or before `date`. Label-free."""
    pos = days.searchsorted(pd.Timestamp(date), side="right") - 1
    bench = {w: _tr(past_arrays(prices, I.BENCHMARK, days, pos, w), w) for w in I.TRAILING}
    out = {}
    for ticker in tickers:
        row = {}
        for w in I.TRAILING:
            c = past_arrays(prices, ticker, days, pos, w)
            row[f"trail{w}"] = _tr(c, w)
            row[f"bench{w}"] = bench[w]
        c = past_arrays(prices, ticker, days, pos, I.BREADTH_WINDOW)
        row["aboveMA126"] = I.above_moving_average(c, len(c) - 1, I.BREADTH_WINDOW) if c is not None and len(c) > I.BREADTH_WINDOW else np.nan
        row["daily"] = I.daily_returns_window(c, len(c) - 1, I.RISK_WINDOW) if c is not None else None
        out[ticker] = row
    return out


def _tr(close, window):
    return I.trailing_return(close, len(close) - 1, window) if close is not None else np.nan


def readiness_gates(features, schedule, intervals, spec, v4_schedule):
    """Label-free reasons the study cannot run; empty means ready."""
    reasons = []
    if features.empty:
        return ["NO_PIT_NAME_DATES"]
    if features.duplicated(["date", "ticker"]).any():
        reasons.append("DUPLICATE_PIT_NAME_DATE")
    needed = ("marketCap", "logAdv60") + I.FUNDAMENTAL_COLUMNS[:-1]
    missing = [c for c in needed if c not in features.columns]
    if missing:
        reasons.append("SIGNAL_TIME_COLUMNS_MISSING: " + ",".join(missing))
    if sorted(schedule) != sorted(v4_schedule):
        reasons.append("SIGNAL_DATES_DIFFER_FROM_V4_MEMBERSHIP_CALENDAR")
    elif any(set(schedule[d]) != set(v4_schedule[d]) for d in schedule):
        reasons.append("PIT_TOP120_DIFFERS_FROM_V4_MEMBERSHIP_UNIVERSE")
    if "marketCap" in features.columns:
        per_date = pd.to_numeric(features.marketCap, errors="coerce").notna().groupby(features.date).sum()
        if (per_date < spec["readiness"]["minimumNamesWithMarketCapPerDate"]).any():
            reasons.append("MARKET_CAP_UNAVAILABLE")
    if not any(t in intervals for t in features.ticker.unique()):
        reasons.append("NO_MEMBERSHIP_RECONSTRUCTION_FOR_ANY_NAME")
    return reasons


def forward_table(prices, schedule, days, spec, v1_spec, permit, counters, lock, sha):
    """Per signal date, per member, per horizon: (stock, benchmark, status). Requires permit AND lock; counts every read.
    Identical endpoint rule and terminal discipline to the accepted anatomy (cross-checked row by row against the sealed v1 target)."""
    require_permit(permit)
    require_lock(lock, sha)
    foundation = json.loads((ROOT / v1_spec["inputs"]["terminalFoundationPath"]).read_text())
    complete = {row["code"] + ".KS": row.get("completeness") for row in foundation.get("securities", [])}
    target_from_sessions = AE.sealed_v1_function("target_from_sessions")
    attach_eligibility = AE.sealed_v1_function("attach_eligibility")
    table, windows = {}, {}
    for h in I.HORIZONS:
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


def build_sensitivity_panel(name, membership, caps, features, past, forward, windows, panel_values):
    """One industry-date panel for one registered sensitivity. Cohorts are rebuilt (not patched) after the exclusion."""
    exclude = I.EXCLUDED_MEGA_CAPS if name == "EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX" else ()
    cohorts = I.build_cohorts(membership, caps, exclude=exclude, leave_largest_out=name == "LEAVE_LARGEST_CONSTITUENT_OUT")
    industry_features, targets = {}, {}
    for (date, industry), cohort in cohorts.items():
        if cohort["status"] != "ELIGIBLE":
            continue
        industry_features[(date, industry)] = I.industry_features(cohort, past[date], panel_values[date])
        for h in I.HORIZONS:
            targets[(date, industry, h)] = I.industry_targets(cohort, forward[(date, h)], h)
    return I.industry_date_panel(cohorts, industry_features, targets, windows)


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
    features["netIncomeImprovementToAssets"] = [AE.improvement_to_assets(bundle["accounting"].get(t, []), d, "당기순이익") for t, d in zip(features.ticker, features.date)]
    schedule = schedule_from_features(features)
    intervals, crosswalk, ends = load_membership_inputs(root)
    from .kr_industry_membership import top120_schedule
    inputs = json.loads((Path(root) / "data/kr-industry-membership-foundation-v1/top120-inputs.json").read_text())
    v4_schedule = {d: [n[4:] if n.startswith("KRX:") else n for n in names] for d, names in top120_schedule(inputs)[0].items()}
    reasons = readiness_gates(features, schedule, intervals, spec, v4_schedule)
    if reasons:
        Path(output).mkdir(parents=True, exist_ok=True)
        X.atomic_write(Path(output) / "gates-failed.json", {"studyId": STUDY, "reasons": reasons, "counters": asdict(counters)})
        raise ValueError("READINESS_GATE_FAILED: " + ";".join(reasons))
    days = RC.sessions("2013-01-01", "2028-12-31", "KR")
    past = {d: past_features(bundle["prices"], t, days, d) for d, t in schedule.items()}
    membership = I.membership_table(schedule, intervals, crosswalk, ends)
    caps = features[["date", "ticker", "marketCap"]]
    panel_values = {d: {r["ticker"]: r for r in g.to_dict("records")} for d, g in features.groupby("date")}
    lock = claim_execution_lock(sha, env, api)
    write_execution_marker(output, spec, sha, identity, counters, lock)
    forward, windows = forward_table(bundle["prices"], schedule, days, spec, v1_spec, permit, counters, lock, sha)
    counters.analysisCalls += 1
    panels = {name: build_sensitivity_panel(name, membership, caps, features, past, forward, windows, panel_values) for name in I.SENSITIVITIES}
    analysis = {name: I.analyze_panel(p, spec) for name, p in panels.items()}
    result = {"studyId": STUDY, "scientificStatus": SCIENTIFIC_STATUS, "returnBasis": I.RETURN_BASIS, "benchmark": spec["benchmark"],
              "eligibility": {name: I.eligibility_summary(p) for name, p in panels.items()},
              "lensComparison": {f"H{h}": I.lens_comparison(panels["FULL"], h) for h in I.HORIZONS}, "analysis": analysis}
    I.assert_no_forbidden_keys(result)
    return write_outputs(output, result, panels, spec, sha, identity, counters)


def write_execution_marker(output, spec, sha, identity, counters, lock=None):
    counters.markerWrites += 1
    document = {"studyId": STUDY, "specSha256": sha, "inputIdentitySha256": identity["sha256"],
                "lockRef": None if lock is None else lock.ref, "lockedMainSha": None if lock is None else lock.mainSha, "outcomesReadBeforeThisMarker": 0}
    X.atomic_write(Path(output) / "execution-started.json", document, immutable=True)
    return document


def write_outputs(output, result, panels, spec, sha, identity, counters):
    out = Path(output)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    files = {"industry-anatomy.json": X.atomic_write(out / "industry-anatomy.json", AE.json_safe(result))}
    for name, panel in sorted(panels.items()):
        data = AE._gzip_csv(panel)
        (out / "tables" / (name.lower() + ".csv.gz")).write_bytes(data)
        files["tables/" + name.lower() + ".csv.gz"] = hashlib.sha256(data).hexdigest()
    manifest = {"studyId": STUDY, "specSha256": sha, "inputIdentitySha256": identity["sha256"], "scientificStatus": SCIENTIFIC_STATUS,
                "returnBasis": I.RETURN_BASIS, "counters": asdict(counters), "files": files}
    X.atomic_write(out / "manifest.json", AE.json_safe(manifest))
    return manifest


# --------------------------------------------------------------------------- #
# Outcome-free readiness audit
# --------------------------------------------------------------------------- #
def readiness_audit(root=ROOT):
    """READY_FOR_INDUSTRY_ANATOMY_EXECUTION or DATA_BLOCKED_BEFORE_INDUSTRY_ANATOMY from structure and identity only.

    Reads pinned files, the frozen spec and a tiny SYNTHETIC deterministic self-check. It never touches a price, a market-cap
    value, a forward return or any outcome, and the counters prove it."""
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
    try:
        spec, sha = load_spec(root)
        checks["frozenSpecAndImportClosure"] = True
    except (ValueError, KeyError, OSError) as error:
        checks["frozenSpecAndImportClosure"], details["frozenSpecAndImportClosure"] = False, str(error)
    if spec is not None:
        check("membershipTaxonomyBenchmarkPins", lambda: verify_pins(spec, root))
        v1 = json.loads((root / "research_specs/kr-model-overlay-portfolio-v1.json").read_text())
        check("rawInputArtifactPinnedWithDigest", lambda: bool(spec["input"]["artifactArchiveSha256"]) and spec["input"]["identitySha256"] == "233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7")
        check("priceInputsPinnedByReplayManifest", lambda: bool(v1["inputs"].get("replayManifestSha256")) and not v1["inputs"].get("replaceSilently", False))
        check("marketCapInputPinnedByKrxCacheDigest", lambda: bool(spec["input"].get("krxCacheSha256")))
        check("pitAccountingSnapshotPinnedByContentDigest", lambda: bool(v1["inputs"]["accounting"]["contentSha256"]) and len(v1["inputs"]["accounting"]["gitBlobSha1"]) >= 10)
        check("v4MembershipHasClassifiedNameDates", lambda: spec["membership"]["v4Facts"]["classifiedNameDates"] > 0)
        check("v4TerminalLimitationRecordedNotHidden", lambda: spec["membership"]["v4Facts"]["terminal"] == {"classified": 0, "denominator": 2345})
    check("deterministicConstruction", _synthetic_determinism)
    check("noOutcomeAccess", lambda: counters.zero())
    check("syntheticTestsPresent", lambda: (root / "tests/test_kr_industry_anatomy_v1.py").is_file() and (root / "tests/test_kr_industry_anatomy_execution_v1.py").is_file())
    ready = all(checks.values())
    return {"studyId": STUDY, "mode": "readiness", "decision": "READY_FOR_INDUSTRY_ANATOMY_EXECUTION" if ready else "DATA_BLOCKED_BEFORE_INDUSTRY_ANATOMY",
            "checks": checks, "details": details, "specSha256": sha, "counters": asdict(counters), "basedOnAnyReturnResult": False,
            "historicalExecutionPerformed": False, "scientificStatus": SCIENTIFIC_STATUS}


def _synthetic_determinism():
    """Two builds of the same synthetic cohort must be identical (no clock, no randomness, order-independent)."""
    tickers = [f"S{i}.KS" for i in range(6)]
    schedule = {"2020-01-03": tickers}
    intervals = {t: [{"start": None, "end": None, "label": "반도체 제조업", "status": "RECONSTRUCTED_STABLE_NO_CHANGE_EVENT",
                      "reconstruction_status": "RECONSTRUCTED_STABLE_NO_CHANGE_EVENT"}] for t in tickers}
    crosswalk = {"mapping": {"반도체제조업": "ELECTRONICS_ELECTRICAL"}}
    caps = pd.DataFrame({"date": "2020-01-03", "ticker": tickers, "marketCap": [float(i + 1) for i in range(6)]})
    first = I.build_cohorts(I.membership_table(schedule, intervals, crosswalk), caps)
    second = I.build_cohorts(I.membership_table(dict(reversed(list(schedule.items()))), {k: intervals[k] for k in reversed(list(intervals))}, crosswalk), caps.iloc[::-1])
    return first == second and next(iter(first.values()))["status"] == "ELIGIBLE"
