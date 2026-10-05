"""KR market risk model v1 — frozen identity, outcome-free readiness, one-shot lock and (later) the single historical development execution.

EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY. The design is informed by the sealed, outcome-exposed `kr-market-risk-anatomy-v2`; every
historical number this study can ever produce is development evidence, never validation. Prospective receipts are the only route to real evidence.

Inputs are the exact immutable bytes `kr-market-risk-anatomy-v1` retained and the sealed anatomy v2 used (no new acquisition, no vendor contact):
the KOSPI 200 reference the sealed anatomy selected (`FDR_KS200`), its VIX role source (`FRED_VIXCLS`) and the two Treasury legs of the 10y-3m spread.

On pull requests only `verify` and `readiness` run. Readiness reads observation DATES only: it pushes a presence proxy (every observed date carries
the value 1.0) through the same state machine to measure where each candidate is determinable; no price, rate or forward quantity is read and the
counters prove it. `execute` refuses unless a workflow_dispatch on merged main carries this exact committed spec with every pin intact and no prior
result, marker or lock; the outcome-free gates run; ONLY THEN is the durable exclusive git-tag lock created, then the marker, and only after both is
any source value read. A failure before the lock spends nothing; a failure after it consumes the study for good.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

import pandas as pd

from . import kr_market_risk_anatomy as M
from . import kr_market_risk_anatomy_analysis as AN
from . import kr_market_risk_model as K
from . import kr_market_risk_source_parse as P
from . import kr_market_risk_sources as S
from .kr_model_portfolio_execution import digest, file_hash, import_closure   # the shared seal helpers, as kr-market-risk-anatomy-v2 imports them

ROOT = Path(__file__).resolve().parents[1]
STUDY = K.STUDY
SPEC_PATH = "research_specs/" + STUDY + ".json"
RESULT_PATH = "docs/results/" + STUDY + "-result.json"
MARKER_PATH = "docs/results/" + STUDY + "-execution-started.json"
MANIFEST_PATH = "docs/results/" + STUDY + "-manifest.json"
RECEIPT_SCHEMA_PATH = "research_specs/" + STUDY + "-receipt.schema.json"
SNAPSHOT_DIR = "data/kr-market-risk-anatomy-v1/sources"
SCIENTIFIC_STATUS = K.SCIENTIFIC_STATUS
DECISION_READY = "READY_FOR_MARKET_RISK_MODEL_V1_EXECUTION"
DECISION_BLOCKED = "DATA_BLOCKED_BEFORE_MARKET_RISK_MODEL_V1"
ARTIFACT_FILES = ("execution-started.json", "manifest.json", "market-risk-model.json")
RESULT_FILE, MARKER_FILE, MANIFEST_FILE = "market-risk-model.json", "execution-started.json", "manifest.json"

PREDECESSOR = "kr-market-risk-anatomy-v2"
PREDECESSOR_SEALED = ("research_specs/kr-market-risk-anatomy-v2.json", "research_specs/kr-market-risk-anatomy-v2.sha256",
                      "docs/results/kr-market-risk-anatomy-v2-result.json", "docs/results/kr-market-risk-anatomy-v2-manifest.json",
                      "docs/results/kr-market-risk-anatomy-v2-execution-started.json", "docs/results/kr-market-risk-anatomy-v2-seal-provenance.json",
                      "docs/results/kr-market-risk-anatomy-v2-readiness.json", "docs/kr-market-risk-anatomy-v2-final-result.md")
INHERITED = {"primaryReference": "FDR_KS200", "analysisEnd": "2026-09-17", "vixRoleSource": "FRED_VIXCLS"}
SOURCES = {"reference": "FDR_KS200", "vix": "FRED_VIXCLS", "us10y": "FRED_DGS10", "us3m": "FRED_DGS3MO"}
REFERENCE_QUALITY_START = "2006-01-01"          # the sealed anatomy's session-quality window start
MIN_DETERMINABLE_SHARE = S.FAMILY_FAST_COVERAGE  # 0.99, inherited
COUNTER_NAMES = ("valueReads", "stateComputations", "replayCalls", "forwardTargetCalls", "metricCalls", "nominationCalls", "markerWrites")


def github_api(method, path, payload=None, env=None):
    """Minimal GitHub REST call for the lock (the same shape the earlier one-shot studies use)."""
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


def atomic_write(path, document, *, immutable=False):
    """Canonical JSON, fsync, and (immutable) exclusive hard-link publication: an existing file is never overwritten. Returns the SHA-256 of the bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode() + b"\n"
    temp = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    try:
        with temp.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if immutable:
            os.link(temp, path)
        else:
            os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
    return hashlib.sha256(raw).hexdigest()


@dataclass
class Counters:
    """Everything that reads a source VALUE or computes an outcome increments one of these; verify, readiness and a refused gate leave all at zero."""
    valueReads: int = 0
    stateComputations: int = 0
    replayCalls: int = 0
    forwardTargetCalls: int = 0
    metricCalls: int = 0
    nominationCalls: int = 0
    markerWrites: int = 0

    def zero(self):
        return all(v == 0 for v in asdict(self).values())


@dataclass(frozen=True)
class ExecutionPermit:
    specSha256: str
    token: object


_PERMIT_TOKEN = object()
_LOCK_TOKEN = object()


def require_permit(permit):
    if not isinstance(permit, ExecutionPermit) or permit.token is not _PERMIT_TOKEN:
        raise ValueError("MARKET_RISK_MODEL_OUTCOME_ACCESS_WITHOUT_PERMIT")
    return permit


# --------------------------------------------------------------------------- #
# The frozen scientific content, as the modules define it (the spec carries the same values and `load_spec` compares them)
# --------------------------------------------------------------------------- #
def model_definition():
    return {
        "output": "equityRiskMultiplier in {1.0, 0.7, 0.4}; 1.0 = normal KR equity risk budget, below 1.0 = partial de-risking, never above 1.0",
        "levels": list(K.LEVELS),
        "layers": {
            "SLOW": {"feature": K.SLOW_FEATURE, "definition": M.FEATURES[K.SLOW_FEATURE][2], "inversionLookbackSessions": K.INVERSION_LOOKBACK_SESSIONS,
                     "inputs": [SOURCES["us10y"], SOURCES["us3m"]], "spread": "DGS10 - DGS3MO on dates where both legs exist",
                     "cadence": K.SLOW_CADENCE, "sampling": "calendar month-end KR session; carried to later sessions until the next month-end",
                     "lagCalendarDays": K.FRED_LAG_DAYS, "staleCalendarDays": K.FRED_STALE_DAYS},
            "TRANSITION": {"feature": K.TRANSITION_FEATURE, "input": SOURCES["vix"], "cadence": K.TRANSITION_CADENCE,
                           "state": "past-only expanding percentile of the known VIX level on calendar week-end KR sessions >= 0.80",
                           "highPercentile": K.TRANSITION_HIGH_PERCENTILE, "minimumObservations": K.TRANSITION_MIN_OBS,
                           "expandingHistoryStart": "the first weekly session of the frozen reference grid (1990-01-03)",
                           "lagCalendarDays": K.FRED_LAG_DAYS, "staleCalendarDays": K.FRED_STALE_DAYS,
                           "excluded": {"policyEasingFlag": "not a layer input: a stress-state marker in the anatomy, would add a degree of freedom",
                                        "creditSpreads": "HY/IG OAS valid only from 2023-10; cannot drive a core model",
                                        "usdkrw": "weak or wrong-signed in the anatomy; not a layer input", "vixChange": "near 0.5 in the anatomy; not a layer input"}},
            "FAST": {"definition": "count of adverse legs of the existing overlay: close < mean(last 200 closes); std63(ddof=1) x sqrt(252) > 0.25",
                     "values": [0, 1, 2], "trendWindow": K.FAST_TREND_WINDOW, "volWindow": K.FAST_VOL_WINDOW, "volThreshold": K.FAST_VOL_THRESHOLD,
                     "implementation": "kr_market_risk_anatomy.overlay_state_from_window (literal replica of kr_market_risk_overlay.state_at)",
                     "input": SOURCES["reference"]}},
        "candidates": {cid: {**{k: (list(v) if isinstance(v, tuple) else v) for k, v in K.CANDIDATES[cid].items()}, "table": K.mapping_table(cid)}
                       for cid in K.CANDIDATE_ORDER},
        "candidateOrder": list(K.CANDIDATE_ORDER), "control": K.CONTROL,
        "structuralSwitches": {"gating": "FAST == 1 reduces only when SLOW or TRANSITION is adverse", "preemption": "SLOW and TRANSITION both adverse step the level down by one (floor 0.4)",
                               "severeFast": "FAST == 2 is 0.4 in every candidate"},
        "missingState": "a candidate's multiplier is defined only when every completion of the missing layers it reads gives the same answer; otherwise it HOLDS its previous "
                        "target (no information, no action), counted per candidate; undefined on the first decision date is refused. Missing is never benign and never maximally adverse.",
        "reEntry": "MEMORYLESS_STATE_MAPPING: the multiplier is a function of today's observable states only; normal exposure resumes on the first decision date whose state maps "
                   "to 1.0. No trough, rebound threshold, minimum hold, hysteresis or future information.",
        "decisionCadence": "calendar week-end KR session (a session whose next KR session lies in a later week)",
        "execution": "signal at the decision-date close; trade at the close of the NEXT KR session",
        "endDateInvariance": "a state at t is identical whether the data end at t or later (calendar-anchored sampling, known-at-t inputs, past-only percentiles)",
    }


def portfolio_definition():
    return {
        "asset": "the sealed anatomy's primary reference FDR_KS200 (KOSPI 200 price index), the SAME series the states are computed on; nothing else is held",
        "assetBasis": "PRICE_INDEX_NOT_TOTAL_RETURN_NOT_DIRECTLY_INVESTABLE",
        "whyNotTheEtf": "the retained KODEX 200 route (YAHOO_069500) starts 2007-01-29, is an as-traded close without dividends and never passed the anatomy's source-quality gates",
        "cash": K.CASH_RATE, "dividends": "OMITTED_ON_BOTH_LEGS",
        "conventionBias": "omitted dividends favour de-risking (the reduced share forgoes no dividend), zero cash yield disfavours it; directions stated, sizes not measured",
        "noStockOrIndustrySelection": True, "leverage": "NONE (multiplier <= 1.0)",
        "start": "NAV 1 at the close of the first execution session holding the first target; the initial build is not a rebalance and is not charged",
        "rebalance": "only when the target changes; holdings drift otherwise",
        "trade": "exactly to target x post-cost NAV at the execution-session close; costs paid from cash",
        "buyCost": K.BUY_COST, "sellCost": K.SELL_COST, "costSemantics": "repository KR buy 15bp / sell 45bp, unchanged (conservative for an index exposure)",
        "costStress": list(K.COST_STRESS), "grossPath": "the same decisions with zero cost",
        "passiveReference": {"id": K.PASSIVE, "multiplier": 1.0, "role": "participation denominator and dominance reference; never nominated"},
    }


def evaluation_definition():
    return {
        "window": {"firstDecisionOnOrAfter": K.EVALUATION_START, "end": INHERITED["analysisEnd"], "warmUp": "every session before the first decision date",
                   "reason": "the anatomy's reference session-quality window starts 2006-01-01; 2006 is warm-up for the 200-session FAST window"},
        "metrics": {
            "returnParticipation": ["cumulativeReturn", "annualizedReturn", "participation.upside", "participation.downside", "averageEquityWeight", "targetShare", "reducedSessionShare"],
            "downside": ["maxDrawdown", "worstRollingReturnH63", "worstRollingReturnH126", "downsideVolatility", "annualizedVolatility", "episodeCapture",
                         "maxDrawdownRecoverySessions", "sessionsToRegainPeakValue"],
            "falseAlarm": ["activations", "falseAlarms", "falseAlarmShare", "reducedSessionsWithoutSubsequentLargeLoss",
                           "shareOfMaturedSessionsReducedWithoutSubsequentLargeLoss", "pendingActivations"],
            "reboundReEntry": ["reboundMissedH63", "reboundMissedH126", "sessionsUntilFullExposure", "recoveryOpportunityCost"],
            "implementation": ["multiplierSwitches", "tradedNotional", "oneWayTurnover", "annualizedOneWayTurnover", "totalCostFractionOfNav", "costDrag"],
            "robustness": ["halves", "episodesByThreshold", "calendarYears (descriptive only)"]},
        "falseAlarm": {"horizon": K.FALSE_ALARM_HORIZON, "lossCut": K.FALSE_ALARM_LOSS_CUT,
                       "definition": "an activation (target falls from 1.0) whose reference forward worst loss within H63 stays above -10%; unmatured windows are PENDING and excluded"},
        "episodes": {"algorithm": "kr_market_risk_anatomy.underwater_episodes on the reference over the evaluation window",
                     "thresholds": list(K.EPISODE_THRESHOLDS), "primaryThreshold": K.PRIMARY_EPISODE_THRESHOLD, "namedDates": "NONE"},
        "rollingLossHorizons": list(K.ROLLING_LOSS_HORIZONS), "reboundHorizons": list(K.REBOUND_HORIZONS),
        "halves": "split at the middle evaluation session; each half rebased; descriptive",
        "overlap": "rolling and forward windows overlap; every such number is descriptive, no significance test, no multiplicity correction",
    }


def decision_definition():
    return {
        "axes": [{"metric": a, "better": d} for a, d in K.DOMINANCE_AXES],
        "axisBasis": "net of 1x repository costs over the full evaluation window",
        "steps": ["PARETO: eliminate any candidate dominated by another candidate or by the passive reference",
                  "NON-INFERIORITY versus C0, both required: net annualized return >= C0's - 0.50 pp, and |maxDrawdown| <= 1.10 x |C0 maxDrawdown|",
                  "MEANINGFUL IMPROVEMENT versus C0, at least one: EFFICIENCY_ROUTE net annualized return >= C0's + 0.50 pp, "
                  "or PROTECTION_ROUTE |maxDrawdown| <= 0.90 x |C0 maxDrawdown|",
                  "exactly one survivor is nominated; none keeps the control; several mutually non-dominated survivors are reported as a Pareto trade-off "
                  "and none is nominated"],
        "returnBand": K.RETURN_BAND, "nonInferiorityDrawdownBand": K.NON_INFERIORITY_DRAWDOWN_BAND,
        "meaningfulDrawdownImprovement": K.MEANINGFUL_DRAWDOWN_IMPROVEMENT, "bandEpsilon": K.BAND_EPSILON, "routes": list(K.ROUTES),
        "noSurvivor": K.NOMINATION_NONE, "severalSurvivors": K.NOMINATION_TRADEOFF,
        "tieBreak": "NONE: survivors are mutually non-dominated, and ranking them (by return, simplicity or anything else) would silently prefer one hypothesis "
                    "(fewer false alarms, less lateness, both) over another; every candidate stays in the prospective receipts either way",
        "prospectiveFinalArchitecture": "the nominated candidate, otherwise C0 (the control) for both NO_CANDIDATE_NOMINATED_CONTROL_RETAINED and "
                                        "NO_UNAMBIGUOUS_NOMINATION_PARETO_TRADEOFF; all four candidates' multipliers are recorded in every receipt regardless",
        "meaning": "a DEVELOPMENT nomination of an architecture for later Market x Industry x Stock integration and prospective receipts; never validation, never production",
        "weightedUtility": "NONE", "cagrAloneDecides": False, "drawdownAloneDecides": False,
    }


def pre_outcome_revisions():
    """Frozen design changes made after the first protocol commit and before ANY outcome access, each with its reason. Recorded in the spec so the
    revision is part of the sealed identity rather than a silent edit."""
    return [{
        "id": "NOMINATION_RULE_REVISION_1", "madeBeforeAnyOutcome": True, "outcomeCountersAtRevision": "ALL_ZERO",
        "replaced": "every candidate had to improve max drawdown by >= 10% versus C0; survivors within 0.50 pp of the lead return were ranked by a simplicity order",
        "reason": "C1 can never be more de-risked than C0 (it differs only in leaving an isolated FAST==1 warning at 1.0), so its hypothesis is fewer false alarms, "
                  "less time de-risked and better participation at acceptable protection; a mandatory 10% drawdown gain made it ineligible by construction, and a "
                  "simplicity order would have silently preferred the least-structured hypothesis",
        "now": "Pareto elimination, symmetric non-inferiority bands versus C0 (return -0.50 pp, drawdown +10% relative), at least one meaningful improvement "
               "(efficiency route +0.50 pp return, or protection route -10% relative drawdown), no tie-break: several survivors are a reported Pareto trade-off",
        "unchanged": ["candidates and mapping tables", "states and thresholds", "multiplier vocabulary", "evaluation window", "costs", "diagnostics",
                      "prospective receipts", "lifecycle"]}]


# --------------------------------------------------------------------------- #
# Frozen identity
# --------------------------------------------------------------------------- #
def verify_pins(spec, root=ROOT):
    root = Path(root)
    for rel, wanted in spec["predecessor"]["sealedArtifacts"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("PREDECESSOR_SEALED_ARTIFACT_CHANGED: " + rel)
    if sorted(spec["predecessor"]["sealedArtifacts"]) != sorted(PREDECESSOR_SEALED):
        raise ValueError("PREDECESSOR_SEALED_ARTIFACT_SET_CHANGED")
    for rel, wanted in spec["inputs"]["files"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("INPUT_FILE_CHANGED: " + rel)
    readiness = json.loads((root / "docs/results/kr-market-risk-anatomy-v2-readiness.json").read_text())
    result = json.loads((root / "docs/results/kr-market-risk-anatomy-v2-result.json").read_text())
    inherited = {"primaryReference": result["primaryReference"]["primary"], "analysisEnd": result["analysisEnd"], "vixRoleSource": result["roleSources"]["VIX"]}
    if inherited != INHERITED or spec["inherited"] != INHERITED or readiness["selectedReference"]["analysisEnd"] != INHERITED["analysisEnd"] \
            or readiness["roleSources"]["VIX"] != INHERITED["vixRoleSource"] or readiness["primaryReference"]["primary"] != INHERITED["primaryReference"]:
        raise ValueError("INHERITED_REFERENCE_DIFFERS_FROM_THE_SEALED_ANATOMY")
    return True


def load_spec(root=ROOT):
    root = Path(root)
    path = root / SPEC_PATH
    spec = json.loads(path.read_text())
    sha = path.with_suffix(".sha256").read_text().strip()
    if digest(spec) != sha or spec.get("studyId") != STUDY:
        raise ValueError("SPEC_IDENTITY_CHANGED")
    if spec["scientificStatus"] != SCIENTIFIC_STATUS or spec["developmentStatement"] != K.DEVELOPMENT_STATEMENT or spec["predecessor"]["studyId"] != PREDECESSOR:
        raise ValueError("SCIENTIFIC_STATUS_CHANGED")
    expected = sorted(set(import_closure(spec["entryPoints"], root)) | set(spec["sealedDataInputs"]))
    if expected != sorted(spec["dependencyHashes"]):
        raise ValueError("IMPORT_CLOSURE_CHANGED")
    for rel, wanted in spec["dependencyHashes"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("HARNESS_OR_DEPENDENCY_CHANGED: " + rel)
    verify_pins(spec, root)
    for key, built in (("model", model_definition()), ("portfolio", portfolio_definition()), ("evaluation", evaluation_definition()),
                       ("decision", decision_definition()), ("preOutcomeRevisions", pre_outcome_revisions())):
        if json.loads(json.dumps(spec[key])) != json.loads(json.dumps(built)):
            raise ValueError("MODULE_RULE_DIFFERS_FROM_FROZEN_SPEC: " + key)
    if spec["prospective"]["receiptSchemaSha256"] != file_hash(root / RECEIPT_SCHEMA_PATH):
        raise ValueError("RECEIPT_SCHEMA_CHANGED")
    return spec, sha


def _git(args, root):
    return subprocess.check_output(["git", *args], cwd=str(root))


def authorize_execution(spec, sha, root=ROOT, env=None, git=None, lock_probe=None):
    """Raise unless this is a workflow_dispatch on main at a commit carrying exactly this spec, with every pin intact, no committed result, marker or
    manifest and no durable execution lock (an unverifiable lock state refuses)."""
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
    for rel, code in ((RESULT_PATH, "RESULT"), (MARKER_PATH, "MARKER"), (MANIFEST_PATH, "MANIFEST")):
        if (root / rel).exists():
            raise ValueError("MARKET_RISK_MODEL_" + code + "_ALREADY_COMMITTED")
    if (lock_probe or (lambda: lock_exists(sha, env)))():
        raise ValueError("EXECUTION_LOCK_ALREADY_EXISTS")
    return ExecutionPermit(sha, _PERMIT_TOKEN)


# --------------------------------------------------------------------------- #
# The durable one-shot lock (a GitHub git ref, never an artifact or a local file)
# --------------------------------------------------------------------------- #
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
# Outcome-free readiness (observation DATES only)
# --------------------------------------------------------------------------- #
def source_dates(root, source_id):
    """The FIRST column (date) of a retained normalized file. No value is read or parsed."""
    with open(Path(root) / SNAPSHOT_DIR / source_id / "normalized.csv", newline="") as stream:
        reader = csv.reader(stream)
        next(reader)
        return pd.DatetimeIndex([row[0] for row in reader])


def presence(dates):
    """Presence proxy: 1.0 on every observed date. Pushed through the state machine it reproduces exactly WHERE a state is defined, never WHAT it is."""
    return pd.Series(1.0, index=pd.DatetimeIndex(dates))


def grid(reference_dates):
    first = pd.DatetimeIndex(reference_dates).min()
    return M.kr_sessions(str(first.date()), INHERITED["analysisEnd"])


def availability(close, spread_obs, vix_obs, sessions):
    """Per-candidate determinable share on the evaluation decision dates. Used by readiness on presence proxies; the same function would give the same
    pattern on values, because definedness depends only on which dates exist (and on positive closes, which the anatomy readiness measured)."""
    states = K.layer_states(close, spread_obs, vix_obs, sessions, S.lag_days(SOURCES["us10y"]), S.lag_days(SOURCES["vix"]))
    schedule = K.decision_schedule(sessions, K.EVALUATION_START, INHERITED["analysisEnd"])
    return schedule, {cid: K.determinable_share(states, schedule, cid) for cid in K.CANDIDATE_ORDER}


def readiness_audit(root=ROOT):
    """READY_FOR_MARKET_RISK_MODEL_V1_EXECUTION or DATA_BLOCKED_BEFORE_MARKET_RISK_MODEL_V1 from identities and observation DATES alone."""
    root = Path(root)
    counters = Counters()
    blockers, checks, details = [], {}, {}
    try:
        load_spec(root)
        checks["frozenSpecPinsAndImportClosure"] = True
    except (ValueError, KeyError, OSError) as error:
        checks["frozenSpecPinsAndImportClosure"], details["frozenSpecPinsAndImportClosure"] = False, str(error)
        blockers.append("FROZEN_IDENTITY_NOT_VERIFIED")
    out = {"studyId": STUDY, "mode": "readiness", "scientificStatus": SCIENTIFIC_STATUS, "basedOnAnyReturnResult": False, "historicalExecutionPerformed": False}
    if blockers:
        return {**out, "decision": DECISION_BLOCKED, "blockers": blockers, "checks": checks, "details": details, "counters": asdict(counters)}
    dates = {key: source_dates(root, sid) for key, sid in SOURCES.items()}
    sessions = grid(dates["reference"])
    reference = presence(dates["reference"]).reindex(sessions)
    quality = sessions[sessions >= pd.Timestamp(REFERENCE_QUALITY_START)]
    observed = set(dates["reference"])
    missing = [str(d.date()) for d in quality if d not in observed]
    checks["referenceCompleteFrom2006"] = not missing
    if missing:
        blockers.append("REFERENCE_SESSION_MISSING_IN_QUALITY_WINDOW")
    spread_dates = dates["us10y"].intersection(dates["us3m"])
    schedule, shares = availability(reference, presence(spread_dates), presence(dates["vix"]), sessions)
    for cid, share in shares.items():
        ok = share["firstDecisionDeterminable"] and share["share"] is not None and share["share"] >= MIN_DETERMINABLE_SHARE
        checks["determinable_" + cid] = ok
        if not ok:
            blockers.append("CANDIDATE_STATE_NOT_DETERMINABLE: " + cid)
    for rel, code in ((RESULT_PATH, "RESULT"), (MARKER_PATH, "MARKER"), (MANIFEST_PATH, "MANIFEST")):
        if (root / rel).exists():
            blockers.append("MARKET_RISK_MODEL_" + code + "_ALREADY_COMMITTED")
    checks["noOutcomeAccess"] = counters.zero()
    return {**out, "decision": DECISION_READY if not blockers else DECISION_BLOCKED, "blockers": blockers, "checks": checks, "details": details,
            "counters": asdict(counters), "inherited": INHERITED, "referenceMissingSessionsFrom2006": missing,
            "decisionDates": int(len(schedule)), "firstDecisionDate": str(schedule["decisionDate"].iloc[0].date()) if len(schedule) else None,
            "lastDecisionDate": str(schedule["decisionDate"].iloc[-1].date()) if len(schedule) else None,
            "lastExecutionDate": str(schedule["executionDate"].iloc[-1].date()) if len(schedule) else None,
            "determinable": shares, "minimumDeterminableShare": MIN_DETERMINABLE_SHARE,
            "method": "presence proxy: every observed date carries 1.0; the frozen state machine then shows where a state is defined, never its value"}


def verify(root=ROOT, env=None):
    """Outcome-free: identity, closure and pins. The only mode ordinary pull-request CI runs besides readiness."""
    spec, sha = load_spec(root)
    counters = Counters()
    try:
        authorize_execution(spec, sha, root, env)
        authorized = True
    except (ValueError, subprocess.CalledProcessError, OSError, KeyError):
        authorized = False
    return {"studyId": STUDY, "mode": "verify", "status": "VERIFIED", "specSha256": sha, "scientificStatus": spec["scientificStatus"],
            "executeAuthorizedInThisEnvironment": authorized, "dependencyFiles": len(spec["dependencyHashes"]), "counters": asdict(counters),
            "stoppedBeforeOutcomes": counters.zero(), "historicalExecutionPerformed": False}


# --------------------------------------------------------------------------- #
# Execution (permit -> pins -> outcome-free gates -> LOCK -> marker -> values -> outcomes)
# --------------------------------------------------------------------------- #
def write_execution_marker(output, spec, sha, counters, lock):
    require_lock(lock, sha)
    counters.markerWrites += 1
    document = {"studyId": STUDY, "specSha256": sha, "lockRef": lock.ref, "studyLockRef": STUDY_LOCK_REF, "lockedMainSha": lock.mainSha,
                "valuesReadBeforeThisMarker": counters.valueReads, "scientificStatus": SCIENTIFIC_STATUS}
    if document["valuesReadBeforeThisMarker"] != 0:
        raise ValueError("VALUES_READ_BEFORE_THE_MARKER")
    atomic_write(Path(output) / MARKER_FILE, document, immutable=True)
    return document


def load_values(root, counters, permit, lock, sha):
    """Source VALUES, only after the permit and the durable lock; every read is counted. The reference is cut at the inherited analysis end."""
    require_permit(permit)
    require_lock(lock, sha)
    out = {}
    for key, sid in SOURCES.items():
        counters.valueReads += 1
        series = AN.obs_series(P.read_normalized((Path(root) / SNAPSHOT_DIR / sid / "normalized.csv").read_bytes()))
        out[key] = series[series.index <= pd.Timestamp(INHERITED["analysisEnd"])] if key == "reference" else series
    return out


def evaluate(values, counters, permit, lock, sha):
    """Every outcome of the study, from values read after the lock. Pure assembly of `kr_market_risk_model` functions."""
    require_permit(permit)
    require_lock(lock, sha)
    sessions = grid(values["reference"].index)
    close = values["reference"].reindex(sessions)
    spread = AN.derived_spread(values["us10y"], values["us3m"])
    counters.stateComputations += 1
    states = K.layer_states(close, spread, values["vix"], sessions, S.lag_days(SOURCES["us10y"]), S.lag_days(SOURCES["vix"]))
    schedule = K.decision_schedule(sessions, K.EVALUATION_START, INHERITED["analysisEnd"])
    window = sessions[sessions >= schedule["executionDate"].iloc[0]]
    bench = close.reindex(window)
    counters.forwardTargetCalls += 1
    forward = M.forward_targets(bench, K.FALSE_ALARM_HORIZON)["forwardWorstLoss"]
    episodes = K.episodes_in_window(bench)
    targets = {cid: K.candidate_targets(states, schedule, cid) for cid in K.CANDIDATE_ORDER}
    passive_targets = [K.FULL] * len(schedule)
    counters.replayCalls += 1
    passive = K.replay_path(bench, schedule, passive_targets, stress=0.0)
    result = {"candidates": {}, "passive": None}
    counters.metricCalls += 1
    result["passive"] = {"summary": K.path_summary(passive, passive), "halves": K.halves(passive, passive), "calendarYears": K.calendar_years(passive),
                         "episodeCapture": K.episode_capture(passive, bench, M.episodes_at_least(episodes, K.PRIMARY_EPISODE_THRESHOLD))}
    nomination_input = {K.PASSIVE: {"netAnnualizedReturn": result["passive"]["summary"]["annualizedReturn"],
                                    "maxDrawdown": result["passive"]["summary"]["maxDrawdown"], "reducedSessionShare": 0.0}}
    for cid in K.CANDIDATE_ORDER:
        t = targets[cid]
        counters.replayCalls += 1
        paths = {stress: K.replay_path(bench, schedule, t["target"].tolist(), stress=stress) for stress in (0.0,) + K.COST_STRESS}
        net, gross = paths[1.0], paths[0.0]
        by_threshold = {}
        for threshold in K.EPISODE_THRESHOLDS:
            chosen = M.episodes_at_least(episodes, threshold)
            capture, rebound = K.episode_capture(net, bench, chosen), K.rebound_cost(net, bench, chosen)
            by_threshold[f"depth_ge_{int(threshold * 100)}pct"] = {
                "capture": capture, "rebound": rebound,
                "summary": {key: K.summarise_episodes(capture, key) for key in ("lossCaptureRatio", "avoidedLoss", "sessionsToRegainPeakValue")}
                | {key: K.summarise_episodes(rebound, key) for key in ("reboundMissedH63", "reboundMissedH126", "sessionsUntilFullExposure", "recoveryOpportunityCost")}}
        summary = K.path_summary(net, passive)
        result["candidates"][cid] = {
            "name": K.CANDIDATES[cid]["name"], "decisionDates": int(len(t)), "heldForMissingState": int(t["heldForMissingState"].sum()),
            "net": summary, "gross": K.path_summary(gross, passive),
            "stress": {f"x{int(s)}": {"annualizedReturn": K.path_summary(paths[s], passive)["annualizedReturn"],
                                      "costDrag": gross_minus(gross, paths[s])} for s in K.COST_STRESS},
            "implementation": {**K.implementation_cost(net), "costDrag": gross_minus(gross, net)},
            "falseAlarm": K.false_alarm_profile(net, forward), "episodes": by_threshold,
            "halves": K.halves(net, passive), "calendarYears": K.calendar_years(net)}
        nomination_input[cid] = {"netAnnualizedReturn": summary["annualizedReturn"], "maxDrawdown": summary["maxDrawdown"],
                                 "reducedSessionShare": summary["reducedSessionShare"]}
    counters.nominationCalls += 1
    result["decision"] = {**K.development_nomination(nomination_input), "axes": nomination_input}
    result["window"] = {"firstDecisionDate": str(schedule["decisionDate"].iloc[0].date()), "firstExecutionDate": str(window[0].date()),
                        "lastExecutionDate": str(schedule["executionDate"].iloc[-1].date()), "end": str(window[-1].date()), "sessions": int(len(window) - 1),
                        "decisionDates": int(len(schedule)), "episodeCounts": {f"depth_ge_{int(x * 100)}pct": len(M.episodes_at_least(episodes, x)) for x in K.EPISODE_THRESHOLDS}}
    return result


def gross_minus(gross, net):
    n = len(net) - 1
    g, x = K.annualized(gross["nav"].iloc[-1] / gross["nav"].iloc[0], n), K.annualized(net["nav"].iloc[-1] / net["nav"].iloc[0], n)
    return None if g is None or x is None else g - x


def execute(output, spec, sha, permit, root=ROOT, env=None, api=github_api):
    """Order: permit -> pins -> outcome-free readiness gates -> DURABLE LOCK -> marker -> source values -> outcomes -> result -> manifest. A refused gate
    writes gates-blocked.json, creates no lock and spends nothing."""
    require_permit(permit)
    if permit.specSha256 != sha:
        raise ValueError("PERMIT_FOR_A_DIFFERENT_SPEC")
    counters = Counters()
    verify_pins(spec, root)
    readiness = readiness_audit(root)
    if readiness["decision"] != DECISION_READY:
        Path(output).mkdir(parents=True, exist_ok=True)
        atomic_write(Path(output) / "gates-blocked.json", {"studyId": STUDY, "decision": readiness["decision"], "blockers": readiness["blockers"],
                                                          "counters": asdict(counters)})
        raise ValueError("READINESS_GATE_BLOCKED: " + ";".join(readiness["blockers"]))
    lock = claim_execution_lock(sha, env, api)
    write_execution_marker(output, spec, sha, counters, lock)
    values = load_values(root, counters, permit, lock, sha)
    outcomes = evaluate(values, counters, permit, lock, sha)
    result = {"studyId": STUDY, "scientificStatus": SCIENTIFIC_STATUS, "developmentStatement": K.DEVELOPMENT_STATEMENT, "specSha256": sha,
              "modelVersion": K.MODEL_VERSION, "inherited": INHERITED, "lockRef": lock.ref, "lockedMainSha": lock.mainSha, **outcomes,
              "statements": ["DEVELOPMENT evidence on outcome-exposed KR history; not validation, not prospective, not production",
                             "a nomination is an architecture for later integration and prospective receipts, not a validated model",
                             "the asset is a KOSPI 200 price index without dividends; cash earns zero",
                             "overlapping windows are descriptive; no significance test; no multiplicity correction"]}
    K.assert_no_forbidden_keys(result)
    return write_outputs(output, result, spec, sha, counters)


def write_outputs(output, result, spec, sha, counters):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    files = {RESULT_FILE: atomic_write(out / RESULT_FILE, json_safe(result), immutable=True)}
    files[MARKER_FILE] = file_hash(out / MARKER_FILE)
    manifest = {"studyId": STUDY, "specSha256": sha, "scientificStatus": SCIENTIFIC_STATUS, "counters": asdict(counters), "files": files,
                "inputFiles": spec["inputs"]["files"]}
    atomic_write(out / MANIFEST_FILE, json_safe(manifest), immutable=True)
    return manifest


def json_safe(value):
    """NaN/inf -> None, numpy scalars -> Python; keys and order are left to the canonical writer."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
