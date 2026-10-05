"""KR integrated alpha portfolio v1 — frozen identity, outcome-free readiness, one-shot lock and (later) the single historical development execution.

EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY. This integrates three sealed component studies (market risk model, industry anatomy, stock
within-industry anatomy) into six fixed architectures. Every historical number it can produce is development evidence for choosing an architecture to
record prospectively; none is validation.

On pull requests only `verify` and `readiness` run. Neither values a portfolio, reads a forward quantity or touches the preserved raw artifact: they
check identities, replay a tiny SYNTHETIC world through the whole six-path machinery, and push date-presence proxies through the sealed market state
machine. `execute` refuses unless a workflow_dispatch on merged main carries this exact committed spec with every pin intact and no prior result,
marker or lock. Signal-time feature construction and the registered depth / ranking gates run first and can stop the run before anything is spent. ONLY
THEN is the durable exclusive git-tag lock created, then the marker, and only after both is a market value read or a portfolio valued. A failure before
the lock spends nothing; a failure after it consumes the study for good.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
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
from . import kr_industry_anatomy_execution as IE
from . import kr_integrated_alpha_portfolio as M
from . import kr_integrated_alpha_portfolio_replay as R
from . import kr_market_risk_anatomy_analysis as AN
from . import kr_market_risk_model as K
from . import kr_market_risk_model_execution as MX
from . import kr_market_risk_source_parse as P
from . import kr_market_risk_sources as MS
from . import kr_model_portfolio_execution as X
from . import kr_stock_within_industry_anatomy as S
from . import kr_value_quality_catalyst as F
from . import replay_calendar as RC
from .regional_alpha_features import weekly_grid

digest, file_hash, import_closure = X.digest, X.file_hash, X.import_closure
ROOT = Path(__file__).resolve().parents[1]
STUDY = M.STUDY
SPEC_PATH = "research_specs/" + STUDY + ".json"
SPEC_SIDECAR = "research_specs/" + STUDY + ".sha256"
RESULT_PATH = "docs/results/" + STUDY + "-result.json"
MARKER_PATH = "docs/results/" + STUDY + "-execution-started.json"
MANIFEST_PATH = "docs/results/" + STUDY + "-manifest.json"
READINESS_PATH = "docs/results/" + STUDY + "-readiness.json"
RECEIPT_SCHEMA_PATH = "research_specs/" + STUDY + "-receipt.schema.json"
SCIENTIFIC_STATUS = M.SCIENTIFIC_STATUS
DECISION_READY = "READY_FOR_INTEGRATED_ALPHA_PORTFOLIO_V1_EXECUTION"
DECISION_BLOCKED = "DATA_BLOCKED_BEFORE_INTEGRATED_ALPHA_PORTFOLIO_V1"
RESULT_FILE, MARKER_FILE, MANIFEST_FILE = "integrated-alpha-portfolio.json", "execution-started.json", "manifest.json"
ARTIFACT_FILES = (MARKER_FILE, MANIFEST_FILE, RESULT_FILE)
V4 = IE.V4
MARKET_STUDY = "kr-market-risk-model-v1"
MARKET_SPEC = "research_specs/" + MARKET_STUDY + ".json"
MARKET_SNAPSHOT_DIR = MX.SNAPSHOT_DIR
INPUT_ARTIFACT_ENV, INPUT_RUN_ENV = "PORTFOLIO_INPUT_ARTIFACT", "PORTFOLIO_INPUT_RUN_ID"
PRIOR_STUDIES = ("kr-market-risk-anatomy-v1", "kr-market-risk-anatomy-v2", "kr-market-risk-model-v1", "kr-industry-opportunity-anatomy-v1",
                 "kr-stock-within-industry-anatomy-v1", "kr-model-overlay-portfolio-v1", "kr-factor-anatomy-v1", "kr-top120-regime-review-v1")
PRIOR_NEVER_RERUN = PRIOR_STUDIES
OVERLAY_SPEC = "research_specs/kr-model-overlay-portfolio-v1.json"
STOCK_SPEC = "research_specs/kr-stock-within-industry-anatomy-v1.json"
COUNTER_NAMES = ("featureBuilds", "marketValueReads", "marketStateComputations", "replayCalls", "metricCalls", "cashSensitivityCalls", "decisionCalls",
                 "markerWrites")
OUTCOME_COUNTER_NAMES = tuple(n for n in COUNTER_NAMES if n not in ("featureBuilds", "markerWrites"))


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


@dataclass
class Counters:
    """`featureBuilds` counts signal-time (past-only) feature construction, which the registered gates need BEFORE the lock. Everything else is an
    outcome or market-value counter: a gate that reads a value or values a portfolio increments one, and verify / readiness leave ALL at zero."""
    featureBuilds: int = 0
    marketValueReads: int = 0
    marketStateComputations: int = 0
    replayCalls: int = 0
    metricCalls: int = 0
    cashSensitivityCalls: int = 0
    decisionCalls: int = 0
    markerWrites: int = 0

    def zero(self):
        return all(v == 0 for v in asdict(self).values())

    def outcomes_zero(self):
        return all(getattr(self, n) == 0 for n in OUTCOME_COUNTER_NAMES)


@dataclass(frozen=True)
class ExecutionPermit:
    specSha256: str
    token: object


_PERMIT_TOKEN = object()
_LOCK_TOKEN = object()


def require_permit(permit):
    if not isinstance(permit, ExecutionPermit) or permit.token is not _PERMIT_TOKEN:
        raise ValueError("INTEGRATED_PORTFOLIO_OUTCOME_ACCESS_WITHOUT_PERMIT")
    return permit


# --------------------------------------------------------------------------- #
# The frozen scientific content, as the modules define it (the spec carries the same values and `load_spec` compares them)
# --------------------------------------------------------------------------- #
def stock_layer_definition():
    return {
        "role": "ALWAYS ON and identical in all six architectures: orders eligible stocks by cheapness and calm WITHIN their own industry",
        "peerGroup": "the frozen PIT industry membership (kr-industry-membership-foundation-v4, 14 groups) used ONLY as the peer group; at least 5 classified members",
        "valueScore": {"components": list(M.VALUE_COMPONENTS), "rule": "mean of the within-industry percentile ranks; BOTH components must be finite",
                       "neverSubstituted": "a missing component makes VALUE_SCORE missing; one component is never used for the other"},
        "riskScore": {"component": M.RISK_COMPONENT, "meaning": "higher = calmer (negative annualised downside semideviation over 126 sessions)",
                      "rule": "within-industry percentile rank"},
        "stockScore": {"weights": M.STOCK_WEIGHTS, "rule": "equal-weight mean of VALUE_SCORE and the within-industry percentile of negativeDownsideVol126; "
                       "requires every primary component; higher = more attractive"},
        "percentile": "kr_stock_within_industry_anatomy.within_industry_percentiles: average-rank (r - 0.5) / n among the finite values of the SAME signal date "
                      "and the stock's own industry; at least 5 finite values or NaN; ties share one percentile; past-only; fixed before any outcome",
        "excludedFromPrimaryScore": M.EXCLUDED_FROM_PRIMARY_SCORE,
        "eligibility": {"classifiedInEligibleIndustry": True, "stockScoreFinite": True, "tradable": "observed positive volume and trading value at the signal close",
                        "minimumAdv60Krw": M.PORTFOLIO["minimumAdvKrw"], "minimumDownsideVol126": M.PORTFOLIO["minimumDownsideVol"],
                        "minimumEligiblePerDate": M.MIN_ELIGIBLE_PER_DATE,
                        "depthRule": "every rebalance anchor must leave at least the minimum eligible stocks for the S book and for the I+S book, otherwise the run "
                                     "stops BEFORE the lock (signal-time fact; spends nothing). 0-5 holdings remain valid when executability leaves fewer.",
                        "noAbsoluteDoNotInvestThreshold": True},
        "missingStaysMissing": True}


def industry_layer_definition():
    return {
        "role": "OPTIONAL: when ON it re-orders eligible stocks by the state of their industry; when OFF it contributes exactly zero",
        "features": {"REL_MOM_126": "cap-weighted trailing-126-session return of the industry minus the benchmark's (kr_industry_anatomy.industry_features)",
                     "BREADTH_ABOVE_MA_126": "share of the industry's members above their own 126-session moving average (same function)"},
        "industryScore": {"weights": M.INDUSTRY_WEIGHTS, "rule": "50% cross-industry average-rank percentile of REL_MOM_126 + 50% of BREADTH_ABOVE_MA_126; BOTH required; "
                          "computed over the eligible industries (at least 5 classified members) with both finite on that date",
                          "minimumIndustriesRanked": M.MIN_INDUSTRIES_RANKED},
        "combinedScore": {"weights": M.COMBINED_WEIGHTS, "rule": "50% STOCK_SCORE + 50% INDUSTRY_SCORE of the stock's industry, fixed and untuned; requires both"},
        "notUsed": ["constituent dispersion", "OCF yield", "book-to-market of the industry", "fitted industry weights", "any macro series"],
        "cohort": "the sealed anatomy's FULL cohort (no mega-cap exclusion), frozen at the signal date",
        "rankabilityRule": "every rebalance anchor must rank at least the minimum industries, otherwise the run stops BEFORE the lock"}


def market_layer_definition():
    return {
        "role": "RISK OVERLAY ONLY: never changes eligibility or order. The identical underlying S or I+S book is built first and the already-selected book is scaled",
        "source": MARKET_STUDY, "reference": M.MARKET_REFERENCE, "multiplierVocabulary": list(K.LEVELS),
        "candidates": {cid: {"name": K.CANDIDATES[cid]["name"], "gating": K.CANDIDATES[cid]["gating"], "preemption": K.CANDIDATES[cid]["preemption"],
                             "table": K.mapping_table(cid)} for cid in M.MARKET_CANDIDATES},
        "c1Status": "SHADOW_CHALLENGER: the sealed model's formal non-nomination of C1 is preserved; this study judges C0 and C1 separately and promotes neither",
        "unchanged": "states, thresholds, windows, lags, missing-state hold rule, decision cadence, multiplier tables and timing are the sealed model's functions called directly",
        "timing": "weekly decision at the calendar week-end close; trade at the NEXT KR session's close, only when the multiplier changes",
        "application": "a pure scale of the held book (drifted proportions kept, no new name, no swap), re-expressed at multiplier 1, renormalised to at most 1, times the "
                       "new target; executed by the same sealed execute_rebalance as every other trade (ADV caps, partial fills, costs)",
        "atAnchors": "the multiplier in force scales the freshly sized base weights of that anchor's underlying decision",
        "missingState": "the sealed hold rule (hold the previous target; undefined at the first decision is refused)",
        "marketOff": "multiplier 1.0 throughout; no market trade"}


def portfolio_definition():
    return {
        "maximumHoldings": M.PORTFOLIO["maximumHoldings"], "minimumHoldings": 0, "leverage": "NONE", "tieBreak": "ticker ascending",
        "sizing": "inverse downside-volatility proportional water-fill under the 30% single-name cap and the 1% ADV capacity cap (kr_concentrated_portfolio.size); residual cash",
        "executionQuote": "an observed positive-volume quote at the execution close is required; otherwise the order is deferred (no fictitious fill)",
        "anchors": {"origin": M.FEATURE_START, "strideKrSessions": M.STRIDE_KR_SESSIONS, "firstAnchorOnOrAfter": M.EVALUATION_START,
                    "signal": "the last weekly KR signal strictly before the anchor", "execution": "the anchor's close", "betweenAnchors": "drifted holdings, no retarget",
                    "sameForAllSix": True, "architectureSpecificTradingRules": "NONE"},
        "costs": {"buyFixedCost": M.PORTFOLIO["buyFixedCost"], "sellFixedCost": M.PORTFOLIO["sellFixedCost"], "impactAtOnePercent": M.PORTFOLIO["impactAtOnePercent"],
                  "stress": list(M.COST_STRESS), "primary": 1.0, "semantics": "assumptions for every date, not statutory schedules; stress runs are descriptive"},
        "cash": {"primary": M.CASH_RATE_PRIMARY, "sharpeSortino": "NOT REPORTED: a risk-free assumption would have to be defended and none is claimed"},
        "inheritedFrom": "kr-model-overlay-portfolio-v1 (values compared with the sealed spec on every load)",
        "unresolvedTerminalEconomics": "a held name with no observed close, no observed zero-volume quote and no terminal economics blocks THAT architecture's path "
                                       "(complete: false); no survivor or successor is substituted and no name silently disappears",
        "futureInformation": "none: every score, state and decision is computed from information at or before the signal date",
        "parameters": dict(M.PORTFOLIO)}


def architecture_definition():
    return {"matrix": {k: dict(v) for k, v in M.ARCHITECTURES.items()}, "order": list(M.ARCH_ORDER),
            "axes": {"industry": ["OFF", "ON"], "market": ["OFF", "C0", "C1"]},
            "identity": "A, B, C share ONE underlying decision (same names, same base weights) and D, E, F share ONE; the six differ only along the two registered axes",
            "passiveReference": {"id": M.PASSIVE, "instrument": M.BENCHMARK, "returnBasis": M.RETURN_BASIS, "role": "reported separately; never a candidate",
                                 "notClaimed": "complete shareholder total return"}}


def metrics_definition():
    return {"return": ["cumulativeNetReturn", "netAnnualizedReturn", "excessAnnualizedVsPassive", "terminalExcessVsPassive", "cumulativeGrossReturn", "annualizedCostDrag"],
            "risk": ["maxDrawdown", "worstRollingReturnH63", "worstRollingReturnH126", "annualizedVolatility", "downsideVolatility", "recoverySessions"],
            "implementation": ["annualizedOneWayTurnover", "replacements", "totalCostFractionOfNav", "averageHoldings", "averageCashShare", "meanHerfindahl",
                               "maxSecurityWeight", "averageGrossEquityExposure"],
            "stability": ["halves", "calendarYears", "episodes", "costStress x1/x2/x3"],
            "attribution": ["industryOnVsOff", "c0VsOff", "c1VsOff", "c1VsC0", "interaction"],
            "overlap": "daily path statistics; rolling windows overlap and are descriptive; no significance test; no multiplicity correction",
            "annualisation": "calendar years (days / 365.2425) for returns; 252 sessions for volatility"}


def decision_definition():
    return {
        "bands": {"returnBandAnnual": M.RETURN_BAND, "meaningfulDrawdownImprovement": M.MEANINGFUL_DRAWDOWN_IMPROVEMENT,
                  "nonInferiorityDrawdownBand": M.NON_INFERIORITY_DRAWDOWN_BAND, "bandEpsilon": M.BAND_EPSILON,
                  "source": "inherited unchanged from the sealed kr-market-risk-model-v1 nomination; none is invented or tuned here"},
        "axes": ["net annualized return (1x costs)", "max drawdown (1x costs)"],
        "pairClasses": list(M.PAIR_CLASSES),
        "pairRule": {"nonInferior": "return >= base - 0.50 pp AND |MDD| <= 1.10 x base's",
                     "meaningfulGain": "return >= base + 0.50 pp (efficiency) OR |MDD| <= 0.90 x base's (protection)",
                     "IMPROVES": "non-inferior with a meaningful gain", "NON_INFERIOR_NO_MEANINGFUL_GAIN": "non-inferior without one",
                     "TRADE_OFF": "fails non-inferiority on one axis but gains meaningfully on the other: a risk-preference choice this study does not make",
                     "WORSE": "fails non-inferiority and gains nothing"},
        "industryLayer": {"primary": "I+S vs S under market OFF (D vs A)", "contexts": ["E vs B (C0)", "F vs C (C1)"],
                          "DEVELOPMENT_SUPPORTED": "primary IMPROVES and no context pair is WORSE",
                          "PARETO_TRADE_OFF": "primary TRADE_OFF", "NOT_SUPPORTED": M.INDUSTRY_NOT_SUPPORTED,
                          "blocked": "any needed path incomplete -> NOT_EVALUABLE_BLOCKED_PATH"},
        "marketLayer": {"judged": "C0 and C1 SEPARATELY, each on the SAME underlying portfolio without the overlay (B vs A, C vs A, E vs D, F vs D)",
                        "justification": "return participation lost is justified only while it stays inside the non-inferiority band; a larger loss bought with a larger "
                                         "drawdown reduction is a risk-preference choice and is reported as a trade-off",
                        "DEVELOPMENT_SUPPORTED": "primary pair on the final underlying portfolio IMPROVES and the same overlay is not WORSE on the other portfolio",
                        "notSupported": M.MARKET_NOT_SUPPORTED, "c1VsC0": "recorded beside; C1 replaces C0 only when BOTH are supported and C1 vs C0 IMPROVES"},
        "finalArchitecture": {"rule": "assembled mechanically: industry supported -> I+S else S; then the supported market candidate on that portfolio else none",
                              "mapping": {"S": "A", "S+M0": "B", "S+M1": "C", "I+S": "D", "I+S+M0": "E", "I+S+M1": "F"},
                              "genuineTradeOff": M.NO_UNAMBIGUOUS, "blockedPath": M.NO_FINAL_BLOCKED,
                              "noPostHocTieBreak": True, "noWeightedUtility": True, "cagrAloneDecides": False, "drawdownAloneDecides": False,
                              "meaning": "a DEVELOPMENT architecture to record prospectively; never validation, never production"},
        "descriptiveOnly": ["halves", "calendar years", "episodes", "cost stress", "cash-yield sensitivity", "interaction", "worst H63 / H126", "volatility"]}


def governance_definition():
    return {"lastLargeHistoricalArchitectureStudy": True,
            "afterAnUnfavourableResult": "no v1.1, no threshold sweep, no new factor blend, no new market rule, no top-k search, no cap or cost change",
            "defaultNextStep": "prospective receipts of all six target portfolios",
            "supersedes": [], "doesNotReopen": list(PRIOR_NEVER_RERUN)}


def pre_outcome_revisions():
    return []


# --------------------------------------------------------------------------- #
# Frozen identity
# --------------------------------------------------------------------------- #
def verify_pins(spec, root=ROOT):
    """Every sealed prior study byte-for-byte; the market model's mappings against ITS sealed spec; the inherited portfolio values against the overlay
    study's sealed spec; the cash-yield source; the preserved raw-input identity; and the industry membership pins. File hashing and JSON reads only."""
    root = Path(root)
    for rel, wanted in spec["priors"]["sealedArtifacts"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("PRIOR_SEALED_ARTIFACT_CHANGED: " + rel)
    for rel, wanted in spec["inputs"]["marketSourceFiles"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("MARKET_SOURCE_FILE_CHANGED: " + rel)
    if file_hash(root / M.CASH_YIELD["path"]) != spec["inputs"]["cashYieldFileSha256"]:
        raise ValueError("CASH_YIELD_SOURCE_CHANGED")
    market = json.loads((root / MARKET_SPEC).read_text())
    for cid in M.MARKET_CANDIDATES:
        if market["model"]["candidates"][cid]["table"] != K.mapping_table(cid) or spec["marketLayer"]["candidates"][cid]["table"] != K.mapping_table(cid):
            raise ValueError("MARKET_MAPPING_DIFFERS_FROM_THE_SEALED_MODEL: " + cid)
    if market["model"]["levels"] != list(K.LEVELS) or market["decision"]["returnBand"] != M.RETURN_BAND \
            or market["decision"]["meaningfulDrawdownImprovement"] != M.MEANINGFUL_DRAWDOWN_IMPROVEMENT \
            or market["decision"]["nonInferiorityDrawdownBand"] != M.NON_INFERIORITY_DRAWDOWN_BAND:
        raise ValueError("BANDS_OR_LEVELS_DIFFER_FROM_THE_SEALED_MODEL")
    overlay = json.loads((root / OVERLAY_SPEC).read_text())
    for key, value in M.PORTFOLIO.items():
        if key in overlay["portfolio"] and overlay["portfolio"][key] != value:
            raise ValueError("PORTFOLIO_VALUE_DIFFERS_FROM_THE_SEALED_OVERLAY_STUDY: " + key)
    if overlay["rebalance"]["strideKrSessions"] != M.STRIDE_KR_SESSIONS or overlay["rebalance"]["origin"] != M.FEATURE_START \
            or overlay["gates"]["firstCoverageDate"] != M.EVALUATION_START or overlay["benchmark"] != M.BENCHMARK or overlay["developmentCutoff"] != M.DEVELOPMENT_CUTOFF:
        raise ValueError("CALENDAR_OR_BENCHMARK_DIFFERS_FROM_THE_SEALED_OVERLAY_STUDY")
    stock = json.loads((root / STOCK_SPEC).read_text())
    if stock["input"] != spec["input"] or stock["membership"] != spec["membership"]:
        raise ValueError("INPUT_OR_MEMBERSHIP_PIN_DIFFERS_FROM_THE_SEALED_STOCK_ANATOMY")
    IE.verify_pins(spec, root)
    return True


def load_spec(root=ROOT):
    root = Path(root)
    path = root / SPEC_PATH
    spec = json.loads(path.read_text())
    sha = path.with_suffix(".sha256").read_text().strip()
    if digest(spec) != sha or spec.get("studyId") != STUDY:
        raise ValueError("SPEC_IDENTITY_CHANGED")
    if spec["scientificStatus"] != SCIENTIFIC_STATUS or spec["developmentStatement"] != M.DEVELOPMENT_STATEMENT:
        raise ValueError("SCIENTIFIC_STATUS_CHANGED")
    expected = sorted(set(import_closure(spec["entryPoints"], root)) | set(spec["sealedDataInputs"]))
    if expected != sorted(spec["dependencyHashes"]):
        raise ValueError("IMPORT_CLOSURE_CHANGED")
    for rel, wanted in spec["dependencyHashes"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("HARNESS_OR_DEPENDENCY_CHANGED: " + rel)
    verify_pins(spec, root)
    for key, built in (("stockLayer", stock_layer_definition()), ("industryLayer", industry_layer_definition()), ("marketLayer", market_layer_definition()),
                       ("portfolio", portfolio_definition()), ("architectures", architecture_definition()), ("metrics", metrics_definition()),
                       ("decision", decision_definition()), ("cashYield", M.CASH_YIELD), ("governance", governance_definition()),
                       ("preOutcomeRevisions", pre_outcome_revisions())):
        if json.loads(json.dumps(spec[key])) != json.loads(json.dumps(built)):
            raise ValueError("MODULE_RULE_DIFFERS_FROM_FROZEN_SPEC: " + key)
    if spec["prospective"]["receiptSchemaSha256"] != file_hash(root / RECEIPT_SCHEMA_PATH):
        raise ValueError("RECEIPT_SCHEMA_CHANGED")
    return spec, sha


def _git(args, root):
    return subprocess.check_output(["git", *args], cwd=str(root))


def authorize_execution(spec, sha, root=ROOT, env=None, git=None, lock_probe=None):
    """Raise unless this is a workflow_dispatch on main at a commit carrying exactly this spec, naming exactly the preserved raw artifact, with every pin
    intact, no committed result, marker or manifest and no durable execution lock (an unverifiable lock state refuses)."""
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
    for rel in (SPEC_PATH, SPEC_SIDECAR):
        if git(["show", "HEAD:" + rel], root) != (root / rel).read_bytes():
            raise ValueError("SPEC_NOT_COMMITTED_AT_HEAD")
    verify_pins(spec, root)
    pin = spec["input"]
    if env.get(INPUT_ARTIFACT_ENV) != pin["artifactName"] or env.get(INPUT_RUN_ENV) != str(pin["producingRunId"]):
        raise ValueError("INPUT_ARTIFACT_IDENTITY_MISMATCH")
    for rel, code in ((RESULT_PATH, "RESULT"), (MARKER_PATH, "MARKER"), (MANIFEST_PATH, "MANIFEST")):
        if (root / rel).exists():
            raise ValueError("INTEGRATED_PORTFOLIO_" + code + "_ALREADY_COMMITTED")
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
    """Exclusive create after identities and the registered gates passed and before ANY market value is read or portfolio valued. Only POST and GET are
    issued; a ref is never moved."""
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
# Signal-time assembly (past-only; allowed BEFORE the lock because it can stop the run without spending it)
# --------------------------------------------------------------------------- #
def calendar_anchors(spec):
    """Anchors from the calendar alone: independent of any data, price or outcome."""
    days = RC.sessions(spec["featureStart"], spec["developmentCutoff"], "KR")
    weekly = weekly_grid(spec["featureStart"], spec["developmentCutoff"], "KR")
    return days, weekly, R.anchor_schedule(days, weekly, spec["evaluationStart"], spec["strideKrSessions"])


def decisions_for_date(date, members, features, membership, cohorts, past, panel_values):
    """The two underlying decisions of ONE signal date plus the depth facts, from signal-time inputs only. `features` is that date's feature frame,
    `membership` that date's (ticker, industry) rows, `cohorts` {(date, industry): cohort}, `past` the sealed past-only industry inputs."""
    eligible_industries = {industry: c for (d, industry), c in cohorts.items() if d == date and c["status"] == "ELIGIBLE"}
    industry_features = {industry: I.industry_features(c, past, panel_values) for industry, c in sorted(eligible_industries.items())}
    iscores = M.industry_scores(industry_features)
    frame = features.merge(membership[["ticker", "industry"]], on="ticker")
    frame = frame[frame.industry.isin(set(eligible_industries))]
    columns = ["date", "industry", "ticker", *M.STOCK_FEATURES, "tradable", "adv60", "downsideVol126"]
    scored = M.stock_scores(frame[columns]) if len(frame) else frame.assign(STOCK_SCORE=np.nan, VALUE_SCORE=np.nan, RISK_SCORE=np.nan)
    pair = M.underlying_pair(M.decision_rows(scored, iscores))
    return pair, {"members": len(members), "classifiedInEligibleIndustry": int(len(frame)), "eligibleIndustries": len(eligible_industries),
                  "industriesRanked": int(sum(v["ranked"] for v in iscores.values())), "eligibleS": pair["S"]["eligibleCount"],
                  "eligibleIS": pair["I+S"]["eligibleCount"]}


def build_signal_bundle(input_root, spec, root, counters):
    """Everything the registered gates and the six replays need that is known at or before each signal date. Reads the preserved raw snapshot (prices,
    caps, PIT accounting) through the sealed loaders; computes features, memberships, cohorts, industry scores, stock scores and both underlying decisions."""
    counters.featureBuilds += 1
    v1_spec, _ = X.load_spec(root)
    accounting, memberships, market, prices = X.load_sources(input_root, v1_spec)
    benchmark = prices.get(spec["benchmark"])
    days, weekly, anchors = calendar_anchors(spec)
    signals = sorted({s for _, s in anchors})
    rows = []
    for date in signals:
        snapshot = memberships.on(date)
        if snapshot is None:
            raise ValueError("PIT_MEMBERSHIP_MISSING: " + date)
        for ticker in snapshot["members"]:
            row = F.feature_at(ticker, date, accounting.get(ticker, []), market, prices.get(ticker), benchmark)
            row["marketCap"] = (market.at(ticker, date) or {}).get("marketCap", np.nan)
            rows.append(row)
    features = pd.DataFrame(rows)
    A.assert_pit_membership(features, AE.load_memberships(input_root, v1_spec))
    schedule = IE.schedule_from_features(features)
    intervals, crosswalk, ends = IE.load_membership_inputs(root)
    membership = I.membership_table(schedule, intervals, crosswalk, ends)
    cohorts = I.build_cohorts(membership, features[["date", "ticker", "marketCap"]])
    all_days = RC.sessions("2013-01-01", "2028-12-31", "KR")
    decisions, depth = {}, {}
    for date in signals:
        group = features[features.date == date]
        past = IE.past_features(prices, schedule[date], all_days, date)
        panel_values = {r["ticker"]: r for r in group.to_dict("records")}
        decisions[date], depth[date] = decisions_for_date(date, schedule[date], group, membership[membership.date == date], cohorts, past, panel_values)
    return {"features": features, "schedule": schedule, "intervals": intervals, "decisions": decisions, "depth": depth, "anchors": anchors, "days": days,
            "weekly": weekly, "prices": prices, "market": market, "v1Spec": v1_spec}


def v4_schedule(root):
    from .kr_industry_membership import top120_schedule
    inputs = json.loads((Path(root) / "data/kr-industry-membership-foundation-v1/top120-inputs.json").read_text())
    return {d: [n[4:] if n.startswith("KRX:") else n for n in names] for d, names in top120_schedule(inputs)[0].items()}


def depth_summary(depth, anchors):
    s = [depth[sig]["eligibleS"] for _, sig in anchors]
    i = [depth[sig]["eligibleIS"] for _, sig in anchors]
    ranked = [depth[sig]["industriesRanked"] for _, sig in anchors]

    def stats(values):
        return {"min": int(min(values)), "median": float(np.median(values)), "max": int(max(values))} if values else None
    return {"anchors": len(anchors), "eligibleStocksS": stats(s), "eligibleStocksIS": stats(i), "industriesRanked": stats(ranked),
            "minimumEligiblePerDate": M.MIN_ELIGIBLE_PER_DATE, "minimumIndustriesRanked": M.MIN_INDUSTRIES_RANKED}


def pre_lock_gates(bundle, spec, root):
    """Label-free, value-free reasons the study cannot run; empty means ready. Registered depth and ranking gates at EVERY anchor."""
    reasons = []
    features, schedule, anchors, depth = bundle["features"], bundle["schedule"], bundle["anchors"], bundle["depth"]
    if features.empty or not anchors:
        return ["NO_PIT_NAME_DATES_OR_ANCHORS"]
    if features.duplicated(["date", "ticker"]).any():
        reasons.append("DUPLICATE_PIT_NAME_DATE")
    v4 = v4_schedule(root)
    for date in sorted(schedule):
        if date not in v4 or set(schedule[date]) != set(v4[date]):
            reasons.append("PIT_TOP120_DIFFERS_FROM_V4_MEMBERSHIP_UNIVERSE:" + date)
    if any(prov.get("availableFrom", "") >= date for date, prov in zip(features.date, features.accountingProvenance)):
        reasons.append("ACCOUNTING_PUBLICATION_NOT_STRICTLY_PRIOR")
    per_date = pd.to_numeric(features.marketCap, errors="coerce").notna().groupby(features.date).sum()
    if (per_date < spec["readiness"]["minimumNamesWithMarketCapPerDate"]).any():
        reasons.append("MARKET_CAP_UNAVAILABLE")
    for _, signal in anchors:
        facts = depth[signal]
        if facts["eligibleS"] < M.MIN_ELIGIBLE_PER_DATE:
            reasons.append("STOCK_DEPTH_BELOW_MINIMUM:S:" + signal)
        if facts["eligibleIS"] < M.MIN_ELIGIBLE_PER_DATE:
            reasons.append("STOCK_DEPTH_BELOW_MINIMUM:I+S:" + signal)
        if facts["industriesRanked"] < M.MIN_INDUSTRIES_RANKED:
            reasons.append("INDUSTRY_LAYER_UNRANKABLE:" + signal)
    return sorted(set(reasons))


# --------------------------------------------------------------------------- #
# Market states (the sealed model's functions, called directly)
# --------------------------------------------------------------------------- #
def load_market_values(root, counters, permit, lock, sha):
    """Source VALUES, only after the permit and the durable lock; every read is counted."""
    require_permit(permit)
    require_lock(lock, sha)
    out = {}
    for key, sid in MX.SOURCES.items():
        counters.marketValueReads += 1
        series = AN.obs_series(P.read_normalized((Path(root) / MARKET_SNAPSHOT_DIR / sid / "normalized.csv").read_bytes()))
        out[key] = series[series.index <= pd.Timestamp(MX.INHERITED["analysisEnd"])] if key == "reference" else series
    return out


def market_tables(values, counters, cutoff=M.DEVELOPMENT_CUTOFF):
    """{candidate: decision table} through the cutoff, from the sealed model: layer states, the weekly schedule and the hold rule."""
    sessions = MX.grid(values["reference"].index)
    close = values["reference"].reindex(sessions)
    spread = AN.derived_spread(values["us10y"], values["us3m"])
    counters.marketStateComputations += 1
    states = K.layer_states(close, spread, values["vix"], sessions, MS.lag_days(MX.SOURCES["us10y"]), MS.lag_days(MX.SOURCES["vix"]))
    return M.market_schedule(states, sessions, K.EVALUATION_START, cutoff)


# --------------------------------------------------------------------------- #
# The six paths and the registered decisions
# --------------------------------------------------------------------------- #
def run_architectures(decisions, anchors, tables, ctx, counters, permit, lock, sha, cfg=M.PORTFOLIO, stresses=M.COST_STRESS):
    """Every architecture at every registered cost stress. A and its market variants B, C trade the SAME decision objects (so do D, E, F)."""
    require_permit(permit)
    require_lock(lock, sha)
    underlying = {"S": {s: p["S"] for s, p in decisions.items()}, "I+S": {s: p["I+S"] for s, p in decisions.items()}}
    results = {}
    for arch in M.ARCH_ORDER:
        layer = "I+S" if M.ARCHITECTURES[arch]["industry"] else "S"
        market = M.ARCHITECTURES[arch]["market"]
        for stress in stresses:
            counters.replayCalls += 1
            results[(arch, stress)] = R.replay_architecture(arch, underlying[layer], anchors, None if market is None else tables[market], ctx, cfg, stress=stress)
    return results


def month_end_nav(path):
    frame = pd.DataFrame({"date": [r["date"] for r in path], "nav": [r["nav"] for r in path]})
    last = frame.groupby(frame.date.str[:7]).tail(1)
    return {d: float(v) for d, v in zip(last.date, last.nav)}


def load_cash_events(root):
    """The frozen Bank of Korea base-rate proxy, or None (DATA_UNAVAILABLE) when it cannot be read; never blocks the primary study."""
    try:
        document = json.loads((Path(root) / M.CASH_YIELD["path"]).read_text())
        events = document["events"]
        if not events or [e["date"] for e in events] != sorted(e["date"] for e in events):
            return None, "SOURCE_MALFORMED"
        return events, document
    except (OSError, ValueError, KeyError):
        return None, "SOURCE_UNREADABLE"


def assemble(results, decisions, anchors, depth, counters, root, spec, permit, lock, sha):
    """Summaries, comparisons, attribution, interaction, cash sensitivity and the registered layer decisions from the finished paths."""
    require_permit(permit)
    require_lock(lock, sha)
    summaries, stress_table, navs, blocked, passive = {}, {}, {}, {}, None
    events, document = load_cash_events(root)
    for arch in M.ARCH_ORDER:
        primary = results[(arch, 1.0)]
        if not primary["complete"]:
            summaries[arch] = {"complete": False, "reason": primary["reason"]}
            blocked[arch] = primary["reason"]
            continue
        counters.metricCalls += 1
        summaries[arch] = R.summarize_path(primary["path"])
        navs[arch] = month_end_nav(primary["path"])
        if passive is None:
            passive = R.passive_summary(primary["path"])
        stress_table[arch] = {}
        for stress in M.COST_STRESS[1:]:
            other = results[(arch, stress)]
            if other["complete"]:
                counters.metricCalls += 1
                s = R.summarize_path(other["path"])
                stress_table[arch]["x" + str(int(stress))] = {k: s[k] for k in ("netAnnualizedReturn", "excessAnnualizedVsPassive", "maxDrawdown", "annualizedCostDrag")}
            else:
                stress_table[arch]["x" + str(int(stress))] = {"complete": False, "reason": other["reason"]}
        counters.cashSensitivityCalls += 1
        summaries[arch]["cashYield"] = ({"status": "COMPUTED", "variants": R.cash_sensitivity(primary["path"], events)} if events
                                        else {"status": "DATA_UNAVAILABLE", "reason": document})
    layer_decisions = M.decide({a: {**s, "complete": s.get("complete", False)} for a, s in summaries.items()})
    counters.decisionCalls += 1
    underlying_audit = {"anchors": len(anchors), "identicalUnderlyingPerAxis": True,
                        "meanNamesDifferingBetweenSAndIS": float(np.mean([len(set(decisions[s]["S"]["selected"]) ^ set(decisions[s]["I+S"]["selected"])) / 2
                                                                         for _, s in anchors])),
                        "anchorsWithIdenticalSelection": int(sum(decisions[s]["S"]["selected"] == decisions[s]["I+S"]["selected"] for _, s in anchors))}
    return {"summaries": summaries, "costStress": stress_table, "monthEndNav": navs, "blockedPaths": blocked, "passive": passive,
            "comparisons": M.comparisons({a: s for a, s in summaries.items()}), "attribution": M.attribution(summaries), "interaction": M.interaction(summaries),
            "layerDecisions": layer_decisions, "underlyingAudit": underlying_audit, "stockLayerDepth": depth_summary(depth, anchors),
            "cashYieldSource": cash_source_audit(root, spec)}


def write_execution_marker(output, spec, sha, counters, lock):
    require_lock(lock, sha)
    counters.markerWrites += 1
    values_read = sum(getattr(counters, n) for n in OUTCOME_COUNTER_NAMES)
    document = {"studyId": STUDY, "specSha256": sha, "lockRef": lock.ref, "studyLockRef": STUDY_LOCK_REF, "lockedMainSha": lock.mainSha,
                "valuesReadBeforeThisMarker": values_read, "featureBuildsBeforeThisMarker": counters.featureBuilds, "scientificStatus": SCIENTIFIC_STATUS}
    if values_read != 0:
        raise ValueError("VALUES_READ_OR_PORTFOLIOS_VALUED_BEFORE_THE_MARKER")
    atomic_write(Path(output) / MARKER_FILE, document, immutable=True)
    return document


def execute(input_root, output, spec, sha, permit, root=ROOT, env=None, api=github_api):
    """Order: permit -> input identity -> pins -> signal-time assembly -> registered gates -> DURABLE LOCK -> marker -> market values -> six paths x three
    cost stresses -> metrics -> layer decisions -> result -> manifest. A refused gate writes gates-failed.json, creates no lock and spends nothing."""
    require_permit(permit)
    if permit.specSha256 != sha:
        raise ValueError("PERMIT_FOR_A_DIFFERENT_SPEC")
    counters = Counters()
    identity = X.input_identity(input_root)
    if identity["sha256"] != spec["input"]["identitySha256"]:
        raise ValueError("INPUT_IDENTITY_MISMATCH")
    verify_pins(spec, root)
    bundle = build_signal_bundle(input_root, spec, root, counters)
    readiness = readiness_audit(root)
    reasons = pre_lock_gates(bundle, spec, root) + [b for b in readiness["blockers"] if not b.endswith("_ALREADY_COMMITTED")]
    if reasons:
        Path(output).mkdir(parents=True, exist_ok=True)
        atomic_write(Path(output) / "gates-failed.json", {"studyId": STUDY, "reasons": reasons, "depth": depth_summary(bundle["depth"], bundle["anchors"]) if bundle["anchors"] else None,
                                                         "counters": asdict(counters)})
        raise ValueError("READINESS_GATE_FAILED: " + ";".join(reasons[:20]))
    lock = claim_execution_lock(sha, env, api)
    write_execution_marker(output, spec, sha, counters, lock)
    values = load_market_values(root, counters, permit, lock, sha)
    tables = market_tables(values, counters, spec["developmentCutoff"])
    ctx = R.Context(bundle["prices"], bundle["market"], bundle["days"], spec["benchmark"])
    results = run_architectures(bundle["decisions"], bundle["anchors"], tables, ctx, counters, permit, lock, sha)
    assembled = assemble(results, bundle["decisions"], bundle["anchors"], bundle["depth"], counters, root, spec, permit, lock, sha)
    result = {"studyId": STUDY, "scientificStatus": SCIENTIFIC_STATUS, "developmentStatement": M.DEVELOPMENT_STATEMENT, "specSha256": sha,
              "returnBasis": M.RETURN_BASIS, "benchmark": spec["benchmark"], "lockRef": lock.ref, "lockedMainSha": lock.mainSha,
              "window": {"firstAnchor": bundle["anchors"][0][0], "lastAnchor": bundle["anchors"][-1][0], "anchors": len(bundle["anchors"]),
                         "developmentCutoff": spec["developmentCutoff"]},
              "marketDecisionTables": {cid: {"decisions": int(len(t)), "first": str(t["decisionDate"].iloc[0].date()), "last": str(t["decisionDate"].iloc[-1].date()),
                                             "heldForMissingState": int(t["heldForMissingState"].sum())} for cid, t in tables.items()},
              **assembled,
              "statements": ["DEVELOPMENT evidence on outcome-exposed KR history; not validation, not prospective, not production",
                             "a final architecture is a development architecture to record prospectively, never a validated or production model",
                             "returns are adjusted-index returns with partial distributions; neither a price return nor a complete shareholder total return",
                             "primary cash earns zero; the cash-yield sensitivity is an accounting overlay and never a model input",
                             "overlapping windows are descriptive; no significance test; no multiplicity correction",
                             "no layer decision, comparison or sensitivity is tuned, re-specified or rerun after this result"]}
    M.assert_no_forbidden_keys(result)
    return write_outputs(output, result, spec, sha, counters)


def write_outputs(output, result, spec, sha, counters):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    files = {RESULT_FILE: atomic_write(out / RESULT_FILE, json_safe(result), immutable=True)}
    files[MARKER_FILE] = file_hash(out / MARKER_FILE)
    manifest = {"studyId": STUDY, "specSha256": sha, "scientificStatus": SCIENTIFIC_STATUS, "counters": asdict(counters), "files": files,
                "inputIdentitySha256": spec["input"]["identitySha256"]}
    atomic_write(out / MANIFEST_FILE, json_safe(manifest), immutable=True)
    return manifest


# --------------------------------------------------------------------------- #
# Outcome-free readiness: identities, calendar-only anchors, committed membership, the sealed market state machine on date-presence proxies, the frozen
# cash source and a SYNTHETIC end-to-end six-path world
# --------------------------------------------------------------------------- #
def committed_membership_depth(root, spec):
    """Membership-only upper bounds at the anchors' signal dates: classified stocks in eligible industries, eligible industries. No price, cap or return."""
    membership = S_committed_membership(root)
    days, weekly, anchors = calendar_anchors(spec)
    signals = {s for _, s in anchors}
    sub = membership[membership.date.isin(signals)]
    if sub.empty:
        return None
    facts = S.membership_eligibility(sub.reset_index(drop=True))
    cohorts = S.build_cohorts(sub)
    per_date_industries = pd.Series({d: sum(1 for (dd, _), c in cohorts.items() if dd == d and c["status"] == "ELIGIBLE") for d in sorted(signals) if d in set(sub.date)})
    return {"anchors": len(anchors), "signalDates": len(signals), "firstAnchor": anchors[0][0] if anchors else None, "lastAnchor": anchors[-1][0] if anchors else None,
            "classifiedStocksInEligibleIndustriesPerDate": facts["eligibleStocksPerDate"],
            "eligibleIndustriesPerDate": {"min": int(per_date_industries.min()), "median": float(per_date_industries.median()), "max": int(per_date_industries.max())},
            "anchorDaysInPortfolioCalendar": all(day in {str(d.date()) for d in days} for day, _ in anchors),
            "note": "membership-only upper bounds; tradability, ADV, downside volatility and finite scores are signal-time facts measured by the pre-lock gates"}


def S_committed_membership(root):
    from .kr_stock_within_industry_anatomy_execution import committed_membership
    return committed_membership(root)


def cash_source_audit(root, spec):
    events, document = load_cash_events(root)
    if not events:
        return {"status": "DATA_UNAVAILABLE", "reason": document}
    first, last = events[0]["date"], events[-1]["date"]
    days = RC.sessions(spec["featureStart"], spec["developmentCutoff"], "KR")
    beyond = int(sum(str(d.date()) > document["verifiedThrough"] for d in days))
    return {"status": "FROZEN_PROXY", "events": len(events), "firstEvent": first, "lastEvent": last, "verifiedThrough": document["verifiedThrough"],
            "coversFeatureStart": first <= spec["featureStart"], "sessionsAfterVerifiedThroughCarriedAtTheLastRate": beyond,
            "basis": document.get("basis"), "source": document.get("source")}


def market_presence_audit(root):
    """The sealed market state machine on date-presence proxies: WHERE each candidate is determinable, never what a state is. Dates only."""
    dates = {key: MX.source_dates(root, sid) for key, sid in MX.SOURCES.items()}
    sessions = MX.grid(dates["reference"])
    reference = MX.presence(dates["reference"]).reindex(sessions)
    schedule, shares = MX.availability(reference, MX.presence(dates["us10y"].intersection(dates["us3m"])), MX.presence(dates["vix"]), sessions)
    return {"decisionDates": int(len(schedule)), "firstDecisionDate": str(schedule["decisionDate"].iloc[0].date()),
            "determinable": {cid: shares[cid] for cid in M.MARKET_CANDIDATES},
            "ok": all(shares[cid]["firstDecisionDeterminable"] and shares[cid]["share"] is not None and shares[cid]["share"] >= MX.MIN_DETERMINABLE_SHARE
                      for cid in M.MARKET_CANDIDATES)}


class SyntheticMarket:
    """A deterministic invented store: every ticker trades every session at KRW 6bn. For readiness and tests only; no historical value."""

    def __init__(self, days):
        self.days = [str(d.date()) for d in days]
        self.index = {d: i for i, d in enumerate(self.days)}

    def at(self, ticker, day):
        return {"volume": 1000, "tradingValue": 6e9, "marketCap": 1e12} if day in self.index else None

    def trailing(self, ticker, date, lookback=60):
        i = self.index[date]
        return [self.at(ticker, d) for d in self.days[max(0, i - lookback + 1):i + 1]]


def synthetic_world(start="2015-01-01", end="2017-12-29", evaluation_start="2016-06-01", seed=7):
    """An invented six-path world: 12 tickers in two industries, invented prices, a synthetic market decision table, deterministic scores."""
    days = RC.sessions(start, end, "KR")
    rng = np.random.default_rng(seed)
    tickers = [f"T{i:02d}.KS" for i in range(12)]
    prices = {t: pd.DataFrame({"Close": 100 * np.cumprod(1 + rng.normal(0.0004, 0.012, len(days)))}, index=days) for t in tickers + [M.BENCHMARK]}
    weekly = [str(d.date()) for d in pd.Series(days, index=days).groupby(days.to_period("W")).max()]
    anchors = R.anchor_schedule(days, weekly, evaluation_start)
    decisions = {}
    for signal in sorted({s for _, s in anchors}):
        rows = []
        for i, t in enumerate(tickers):
            h = int(hashlib.sha256((signal + t).encode()).hexdigest()[:6], 16) / 0xFFFFFF
            ind = 0.7 if i < 6 else 0.3
            rows.append({"ticker": t, "industry": "X" if i < 6 else "Y", "STOCK_SCORE": h, "VALUE_SCORE": h, "RISK_SCORE": h, "INDUSTRY_SCORE": ind,
                         "COMBINED_SCORE": 0.5 * h + 0.5 * ind, "tradable": True, "adv60": 6e9, "downsideVol126": 0.18 + 0.01 * i})
        decisions[signal] = M.underlying_pair(rows)
    executions = pd.DatetimeIndex([days[400], days[480], days[560]])
    table = pd.DataFrame({"decisionDate": executions - pd.Timedelta(days=3), "executionDate": executions, "target": [0.7, 0.4, 1.0]})
    first = pd.DataFrame({"decisionDate": [days[0]], "executionDate": [days[0]], "target": [1.0]})
    tables = {"C0": pd.concat([first, table], ignore_index=True), "C1": pd.concat([first, table.assign(target=[0.7, 0.7, 1.0])], ignore_index=True)}
    for t in tables.values():
        t["heldForMissingState"] = False
    return {"days": days, "prices": prices, "market": SyntheticMarket(days), "anchors": anchors, "decisions": decisions, "tables": tables, "tickers": tickers}


def synthetic_paths(world=None):
    world = world or synthetic_world()
    ctx = R.Context(world["prices"], world["market"], world["days"])
    counters, permit = Counters(), ExecutionPermit("0" * 64, _PERMIT_TOKEN)
    lock = ExecutionLock("0" * 64, "a" * 40, "refs/tags/synthetic", _LOCK_TOKEN)
    return run_architectures(world["decisions"], world["anchors"], world["tables"], ctx, counters, permit, lock, "0" * 64, stresses=(1.0,)), counters


def _synthetic_six_paths():
    """The whole six-path machinery on an invented world: all complete, the shared-underlying identity holds, and a second run is byte-identical."""
    first, _ = synthetic_paths()
    second, _ = synthetic_paths()
    if not all(r["complete"] for r in first.values()):
        return False
    same = all(first[k]["path"][-1]["nav"] == second[k]["path"][-1]["nav"] for k in first)
    abc = {a: [r["weights"] for r in first[(a, 1.0)]["path"] if r["kind"] == "ANCHOR"] for a in "ABC"}
    return bool(same) and len(abc["A"]) > 3


def readiness_audit(root=ROOT):
    """READY_FOR_INTEGRATED_ALPHA_PORTFOLIO_V1_EXECUTION or DATA_BLOCKED_BEFORE_INTEGRATED_ALPHA_PORTFOLIO_V1 from identities, the calendar, committed files
    and a synthetic world alone. The preserved raw artifact is not touched, and counters prove no market value was read and no portfolio valued."""
    root = Path(root)
    counters = Counters()
    blockers, checks, details = [], {}, {}
    out = {"studyId": STUDY, "mode": "readiness", "scientificStatus": SCIENTIFIC_STATUS, "basedOnAnyReturnResult": False, "historicalExecutionPerformed": False}

    def check(name, fn, blocker):
        try:
            result = fn()
            checks[name] = True if result in (True, None) else bool(result)
            if result not in (True, None, False):
                details[name] = result
        except (ValueError, KeyError, OSError, AssertionError) as error:
            checks[name], details[name] = False, str(error)
        if not checks[name]:
            blockers.append(blocker)

    try:
        spec, sha = load_spec(root)
        checks["frozenSpecPinsAndImportClosure"] = True
    except (ValueError, KeyError, OSError) as error:
        checks["frozenSpecPinsAndImportClosure"], details["frozenSpecPinsAndImportClosure"] = False, str(error)
        return {**out, "decision": DECISION_BLOCKED, "blockers": ["FROZEN_IDENTITY_NOT_VERIFIED"], "checks": checks, "details": details, "counters": asdict(counters)}
    check("priorStudiesUnchangedAndNotRerun", lambda: all(file_hash(root / r) == w for r, w in spec["priors"]["sealedArtifacts"].items()), "PRIOR_SEALED_STUDY_CHANGED")
    check("marketMappingsAreTheSealedModelsOwn", lambda: all(K.mapping_table(c) == spec["marketLayer"]["candidates"][c]["table"] for c in M.MARKET_CANDIDATES),
          "MARKET_MAPPING_CHANGED")
    out["marketPresence"] = {}

    def market():
        out["marketPresence"] = market_presence_audit(root)
        return out["marketPresence"]["ok"]
    check("marketCandidatesDeterminableFromDatePresence", market, "MARKET_STATE_NOT_DETERMINABLE")
    check("anchorsFromTheCalendarAlone", lambda: bool(calendar_anchors(spec)[2]), "NO_ANCHORS")
    out["membershipDepthUpperBounds"] = None

    def membership():
        out["membershipDepthUpperBounds"] = committed_membership_depth(root, spec)
        facts = out["membershipDepthUpperBounds"]
        return bool(facts) and facts["classifiedStocksInEligibleIndustriesPerDate"]["min"] >= M.MIN_ELIGIBLE_PER_DATE \
            and facts["eligibleIndustriesPerDate"]["min"] >= M.MIN_INDUSTRIES_RANKED and facts["anchorDaysInPortfolioCalendar"]
    check("committedMembershipCanSupportTheRegisteredDepth", membership, "MEMBERSHIP_DEPTH_BELOW_MINIMUM")
    out["cashYieldSource"] = cash_source_audit(root, spec)
    checks["cashYieldSensitivityStatus"] = out["cashYieldSource"]["status"]       # DATA_UNAVAILABLE would NOT block the primary study
    check("syntheticSixPathWorldCompleteAndDeterministic", _synthetic_six_paths, "SYNTHETIC_SIX_PATH_CHECK_FAILED")
    check("noOutcomeAccess", lambda: counters.zero(), "OUTCOME_COUNTER_NONZERO")
    check("syntheticTestsPresent", lambda: all((root / "tests" / name).is_file() for name in spec["tests"]), "SYNTHETIC_TESTS_MISSING")
    for rel, code in ((RESULT_PATH, "RESULT"), (MARKER_PATH, "MARKER"), (MANIFEST_PATH, "MANIFEST")):
        if (root / rel).exists():
            blockers.append("INTEGRATED_PORTFOLIO_" + code + "_ALREADY_COMMITTED")
    days, weekly, anchors = calendar_anchors(spec)
    return {**out, "decision": DECISION_READY if not blockers else DECISION_BLOCKED, "blockers": blockers, "checks": checks, "details": details,
            "counters": asdict(counters), "specSha256": sha, "anchors": len(anchors), "firstAnchor": anchors[0][0], "lastAnchor": anchors[-1][0],
            "notMeasuredBeforeExecution": ["signal-date feature finiteness, tradability and ADV of the PIT members (measured by the pre-lock gates)",
                                           "any market value, return, drawdown or portfolio outcome"]}


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

