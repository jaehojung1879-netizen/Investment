"""KR alpha discovery tournament v1 — frozen identity, outcome-free readiness, the one-shot lock and (later) the single development execution.

EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY. On pull requests only `verify` and `readiness` run: they check identities, compute calendar
and membership facts from committed files, and run the whole tournament on an INVENTED world. Neither touches the preserved raw artifact, reads a
price after a signal date, builds a label, fits on real data or values a real portfolio; their outcome counters stay zero.

`execute` refuses unless a workflow_dispatch on merged main carries this exact committed spec with every pin intact and no committed result, marker or
manifest and no lock ref under the study prefix. It then (1) verifies the input identity, (2) builds signal-time features and runs every label-free
gate (any failure stops the run having spent nothing), and ONLY THEN (3) creates the durable git-tag lock, (4) writes the marker, (5) builds the first
label. A failure after the lock consumes the study for good.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

from . import kr_alpha_tournament as T
from . import kr_alpha_tournament_features as F
from . import kr_alpha_tournament_portfolio as P
from . import kr_alpha_tournament_receipts as RC_
from . import kr_alpha_tournament_study as ST
from . import kr_alpha_tournament_walkforward as W
from . import kr_factor_anatomy as A
from . import kr_factor_anatomy_execution as AE
from . import kr_industry_anatomy as I
from . import kr_industry_anatomy_execution as IE
from . import kr_integrated_alpha_portfolio_replay as R
from . import kr_market_risk_overlay as O
from . import kr_model_portfolio_execution as X
from . import kr_stock_within_industry_anatomy as S
from . import kr_value_quality_catalyst as VQ
from . import replay_calendar as RC
from .regional_alpha_features import weekly_grid

digest, file_hash, import_closure = X.digest, X.file_hash, X.import_closure
ROOT = Path(__file__).resolve().parents[1]
STUDY = T.STUDY
SPEC_PATH = "research_specs/" + STUDY + ".json"
SPEC_SIDECAR = "research_specs/" + STUDY + ".sha256"
RECEIPT_SCHEMA_PATH = "research_specs/" + STUDY + "-receipt.schema.json"
RESULT_PATH = "docs/results/" + STUDY + "-result.json"
MARKER_PATH = "docs/results/" + STUDY + "-execution-started.json"
MANIFEST_PATH = "docs/results/" + STUDY + "-manifest.json"
READINESS_PATH = "docs/results/" + STUDY + "-readiness.json"
WORKFLOW_PATH = ".github/workflows/" + STUDY + ".yml"
DESIGN_PATH = "docs/" + STUDY + "-design.md"
RESULT_FILE, MARKER_FILE, MANIFEST_FILE = "tournament-result.json", "execution-started.json", "manifest.json"
ARTIFACT_FILES = (MARKER_FILE, MANIFEST_FILE, RESULT_FILE)
INTEGRATED_SPEC = "research_specs/kr-integrated-alpha-portfolio-v1.json"
OVERLAY_SPEC = "research_specs/kr-model-overlay-portfolio-v1.json"
INPUT_ARTIFACT_ENV, INPUT_RUN_ENV = "TOURNAMENT_INPUT_ARTIFACT", "TOURNAMENT_INPUT_RUN_ID"
LOCK_PREFIX = "refs/tags/" + STUDY + "-execution-lock"
STUDY_LOCK_REF = LOCK_PREFIX
ENTRY_POINTS = ["pipeline/kr_alpha_tournament_execution.py", "pipeline/kr_alpha_tournament_seal.py"]
SEALED_DATA_INPUTS = [WORKFLOW_PATH, DESIGN_PATH, RECEIPT_SCHEMA_PATH, "scripts/run_kr_alpha_discovery_tournament_v1.py",
                      "scripts/seal_kr_alpha_discovery_tournament_v1.py", "data/kr-industry-membership-foundation-v1/top120-inputs.json"]
PRIOR_SEALED_RESULTS = (
    "docs/results/kr-model-overlay-portfolio-v1-result.json", "docs/results/kr-factor-anatomy-v1-result.json",
    "docs/results/kr-industry-opportunity-anatomy-v1-result.json", "docs/results/kr-stock-within-industry-anatomy-v1-result.json",
    "docs/results/kr-integrated-alpha-portfolio-v1-postoutcome-completed-audit.json", "docs/alpha-opportunity-model-v5-final-postmortem.md",
    "docs/regional-alpha-model-v1.md", "docs/alpha-research-foundation-v2-errata.md", INTEGRATED_SPEC, OVERLAY_SPEC)
OUTCOME_COUNTERS = ("labelBuilds", "modelFits", "predictions", "allocatorSolves", "ledgerReplays", "metricCalls")
COUNTERS = ("featureBuilds", *OUTCOME_COUNTERS, "markerWrites")
DECISION_READY = "READY_FOR_ONE_HISTORICAL_DEVELOPMENT_EXECUTION_AFTER_MERGE"


def new_counters():
    return dict.fromkeys(COUNTERS, 0)


def outcomes_zero(counters):
    return all(counters.get(n, 0) == 0 for n in OUTCOME_COUNTERS)


# --------------------------------------------------------------------------- #
# Frozen scientific content (the spec carries the same values; `load_spec` compares them)
# --------------------------------------------------------------------------- #
def frozen_sections():
    return {
        "objective": T.OBJECTIVE, "developmentStatement": T.DEVELOPMENT_STATEMENT, "scientificStatus": T.SCIENTIFIC_STATUS,
        "returnBasis": T.RETURN_BASIS, "benchmark": T.BENCHMARK, "developmentCutoff": T.DEVELOPMENT_CUTOFF, "featureStart": T.FEATURE_START,
        "evaluationStart": T.EVALUATION_START, "strideKrSessions": T.STRIDE_KR_SESSIONS,
        "horizons": {"primary": T.PRIMARY_HORIZON, "secondary": T.SECONDARY_HORIZON, "innerBlock": T.INNER_BLOCK_HORIZON,
                     "secondaryRole": "descriptive evaluation of the same H126 process predictions; never trained on; cannot rescue"},
        "duplicateResearchAudit": T.duplicate_research_audit(),
        "information": {"classes": T.INFORMATION_CLASSES, "usableClasses": list(T.USABLE_INFORMATION_CLASSES), "registry": T.INFORMATION_REGISTRY},
        "features": {"stock": list(T.STOCK_FEATURES), "industry": list(T.INDUSTRY_FEATURES), "market": list(T.MARKET_FEATURES),
                     "representations": T.REPRESENTATIONS, "rawMagnitudeRule": T.RAW_MAGNITUDE_RULE, "robustZClip": T.ROBUST_Z_CLIP,
                     "robustZMinFinite": T.ROBUST_Z_MIN_FINITE, "withinIndustryMinPeers": T.WITHIN_INDUSTRY_MIN_PEERS,
                     "industryMinRanked": T.INDUSTRY_MIN_RANKED, "interactions": [list(x) for x in T.INTERACTIONS],
                     "linearColumns": F.linear_columns(), "treeColumns": F.tree_columns(), "linearImputation": T.LINEAR_IMPUTATION,
                     "treeImputation": T.TREE_IMPUTATION},
        "targets": {"registry": T.TARGETS, "economicLabel": T.ECONOMIC_LABEL, "minNamesPerLabelDate": T.MIN_NAMES_PER_LABEL_DATE},
        "candidates": {"families": T.MODEL_FAMILIES, "recency": T.RECENCY_SCHEMES, "excluded": T.EXCLUDED_METHODS,
                       "registry": T.candidate_registry()},
        "trialLedger": T.trial_ledger(),
        "preOutcomeRevisions": {"revisions": T.PRE_OUTCOME_REVISIONS, "note": T.PRE_OUTCOME_REVISIONS_NOTE},
        "walkForward": T.WALK_FORWARD, "selection": T.SELECTION, "calibration": T.CALIBRATION, "calibrationHacLag": T.CALIBRATION_HAC_LAG,
        "uncertainty": T.UNCERTAINTY,
        "portfolio": {"inherited": T.PORTFOLIO, "passiveLeg": T.PASSIVE_LEG, "allocator": T.ALLOCATOR, "translators": T.PORTFOLIO_TRANSLATORS,
                      "decisionFocusedChallenger": T.DECISION_FOCUSED_CHALLENGER, "covarianceLookback": T.COVARIANCE_LOOKBACK},
        "evaluation": {"periods": {k: list(v) for k, v in T.PERIODS.items()}, "periodNote": T.PERIOD_NOTE, "stresses": T.STRESSES,
                       "descriptive": list(T.DESCRIPTIVE_DIAGNOSTICS), "noBespokeRescue": T.NO_BESPOKE_RESCUE, "multiplicity": T.MULTIPLICITY,
                       "bootstrapDraws": T.BOOTSTRAP_DRAWS, "bootstrapBlockSessions": T.BOOTSTRAP_BLOCK_SESSIONS, "spaMeanBlock": T.SPA_MEAN_BLOCK,
                       "pboGroups": T.PBO_GROUPS, "seed": T.RANDOM_SEED, "outerIcHacLag": T.OUTER_IC_HAC_LAG},
        "verdict": {"codes": T.VERDICTS, "rules": T.VERDICT_RULES, "meaningfulGPp": T.MEANINGFUL_G_PP, "dsrMin": T.DSR_MIN, "spaMaxP": T.SPA_MAX_P,
                    "pboMax": T.PBO_MAX, "minPeriodsPositive": T.MIN_PERIODS_POSITIVE, "minSignalCoveragePercent": T.MIN_SIGNAL_COVERAGE_PERCENT},
        "stopRules": T.STOP_RULES,
    }


def lifecycle_definition():
    return {"resultPath": RESULT_PATH, "markerPath": MARKER_PATH, "manifestPath": MANIFEST_PATH, "readinessPath": READINESS_PATH,
            "lockPrefix": LOCK_PREFIX, "resultsArtifactPrefix": STUDY + "-results-", "attemptArtifactPrefix": STUDY + "-attempt-",
            "order": ["workflow_dispatch on merged main only", "committed spec and sidecar at HEAD, every pin intact",
                      "no committed result / marker / manifest, no lock ref under the prefix, no unexpired results artifact",
                      "exact preserved raw-input artifact (name, run, id, archive digest) downloaded and its identity verified",
                      "signal-time features and every label-free gate (a failure here spends nothing)",
                      "durable exclusive git-tag lock (atomic POST /git/refs; only POST and GET are ever issued)",
                      "execution marker (zero values read before it)", "first label, then the tournament, the paths and the verdict",
                      "one results artifact, then the exact-byte Draft seal PR (stdlib only; never merges, never marks ready)"],
            "consumed": "a failure after the lock consumes the study permanently; it is never rerun",
            "sealLesson": "scripts/seal_kr_integrated_alpha_portfolio_v1.py has no `if __name__ == '__main__': main()`, so every seal subcommand of run "
                          "37374530672 was a silent no-op and its commit step found no file; this study's seal script is exercised as a real "
                          "subprocess by a test"}


def prospective_definition():
    return {"evidenceClass": "PROSPECTIVE_PAPER", "module": "pipeline/kr_alpha_tournament_receipts.py", "receiptSchemaPath": RECEIPT_SCHEMA_PATH,
            "fields": list(RC_.RECEIPT_FIELDS), "rules": list(RC_.RULES),
            "status": "DESIGNED_NOT_RUNNING: no receipt is written and no schedule exists in this change"}


def priors(root=ROOT):
    return {rel: file_hash(Path(root) / rel) for rel in PRIOR_SEALED_RESULTS}


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #
def verify_pins(spec, root=ROOT):
    root = Path(root)
    for rel, wanted in spec["priors"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("PRIOR_SEALED_ARTIFACT_CHANGED: " + rel)
    integrated = json.loads((root / INTEGRATED_SPEC).read_text())
    for key in ("input", "membership"):
        if integrated[key] != spec[key]:
            raise ValueError("INPUT_OR_MEMBERSHIP_PIN_DIFFERS_FROM_THE_SEALED_INTEGRATED_STUDY: " + key)
    overlay = json.loads((root / OVERLAY_SPEC).read_text())
    for key, value in T.PORTFOLIO.items():
        if key in overlay["portfolio"] and overlay["portfolio"][key] != value:
            raise ValueError("PORTFOLIO_VALUE_DIFFERS_FROM_THE_SEALED_OVERLAY_STUDY: " + key)
    if overlay["benchmark"] != T.BENCHMARK or overlay["developmentCutoff"] != T.DEVELOPMENT_CUTOFF:
        raise ValueError("BENCHMARK_OR_CUTOFF_DIFFERS_FROM_THE_SEALED_OVERLAY_STUDY")
    IE.verify_pins(spec, root)
    return True


def load_spec(root=ROOT):
    root = Path(root)
    path = root / SPEC_PATH
    spec = json.loads(path.read_text())
    sha = (root / SPEC_SIDECAR).read_text().strip()
    if digest(spec) != sha or spec.get("studyId") != STUDY:
        raise ValueError("SPEC_IDENTITY_CHANGED")
    expected = sorted(set(import_closure(spec["entryPoints"], root)) | set(spec["sealedDataInputs"]))
    if expected != sorted(spec["dependencyHashes"]):
        raise ValueError("IMPORT_CLOSURE_CHANGED")
    for rel, wanted in spec["dependencyHashes"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("HARNESS_OR_DEPENDENCY_CHANGED: " + rel)
    verify_pins(spec, root)
    for key, built in {**frozen_sections(), "lifecycle": lifecycle_definition(), "prospective": prospective_definition()}.items():
        if json.loads(json.dumps(spec[key])) != json.loads(json.dumps(built)):
            raise ValueError("MODULE_RULE_DIFFERS_FROM_FROZEN_SPEC: " + key)
    if spec["receiptSchemaSha256"] != file_hash(root / RECEIPT_SCHEMA_PATH):
        raise ValueError("RECEIPT_SCHEMA_CHANGED")
    return spec, sha


def build_spec(root=ROOT):
    """The spec as the modules define it. Used once by scripts/build_kr_alpha_discovery_tournament_v1_spec.py; `load_spec` re-derives and compares."""
    root = Path(root)
    integrated = json.loads((root / INTEGRATED_SPEC).read_text())
    spec = {"studyId": STUDY, "phase": "PREREGISTRATION_HARNESS_SYNTHETIC_TESTS_ONLY_NO_HISTORICAL_OUTCOME_COMPUTED",
            **frozen_sections(), "input": integrated["input"], "membership": integrated["membership"], "priors": priors(root),
            "lifecycle": lifecycle_definition(), "prospective": prospective_definition(), "receiptSchemaSha256": file_hash(root / RECEIPT_SCHEMA_PATH),
            "entryPoints": ENTRY_POINTS, "sealedDataInputs": SEALED_DATA_INPUTS,
            "outcomeAccess": {"beforeLock": ["calendar", "committed membership", "signal-time features (past-only)", "input identity"],
                              "afterLockOnly": ["forward prices and labels", "fits on real labels", "valued portfolios", "every metric"]}}
    closure = sorted(set(import_closure(ENTRY_POINTS, root)) | set(SEALED_DATA_INPUTS))
    spec["dependencyHashes"] = {rel: file_hash(root / rel) for rel in closure}
    return spec


# --------------------------------------------------------------------------- #
# Authorization and the durable one-shot lock (a GitHub git ref, never an artifact or a local file)
# --------------------------------------------------------------------------- #
_PERMIT_TOKEN, _LOCK_TOKEN = object(), object()


class ExecutionPermit:
    def __init__(self, sha, token):
        self.specSha256, self.token = sha, token


class ExecutionLock:
    def __init__(self, spec_sha, main_sha, ref, token):
        self.specSha256, self.mainSha, self.ref, self.token = spec_sha, main_sha, ref, token


def require_permit(permit):
    if not isinstance(permit, ExecutionPermit) or permit.token is not _PERMIT_TOKEN:
        raise ValueError("TOURNAMENT_OUTCOME_ACCESS_WITHOUT_PERMIT")
    return permit


def require_lock(lock, sha):
    if not isinstance(lock, ExecutionLock) or lock.token is not _LOCK_TOKEN or lock.specSha256 != sha:
        raise ValueError("DURABLE_EXECUTION_LOCK_REQUIRED_BEFORE_ANY_OUTCOME")
    return lock


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


def lock_ref(spec_sha):
    return LOCK_PREFIX + "-" + spec_sha


def lock_exists(env=None, api=github_api):
    """True when ANY ref under the study prefix exists, whatever spec SHA it carries; an unverifiable state refuses."""
    env = os.environ if env is None else env
    if not env.get("GH_TOKEN") or not env.get("GITHUB_REPOSITORY"):
        raise ValueError("EXECUTION_LOCK_STATE_UNVERIFIABLE")
    status, body = api("GET", "/git/matching-refs/" + LOCK_PREFIX[len("refs/"):], None)
    if status == 200 and isinstance(body, list):
        return len(body) > 0
    raise ValueError("EXECUTION_LOCK_STATE_UNVERIFIABLE")


def _git(args, root):
    return subprocess.check_output(["git", *args], cwd=str(root))


def authorize_execution(spec, sha, root=ROOT, env=None, git=None, lock_probe=None):
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
            raise ValueError("TOURNAMENT_" + code + "_ALREADY_COMMITTED")
    if (lock_probe or (lambda: lock_exists(env)))():
        raise ValueError("EXECUTION_LOCK_ALREADY_EXISTS")
    return ExecutionPermit(sha, _PERMIT_TOKEN)


def claim_execution_lock(spec_sha, env=None, api=github_api):
    """Exclusive create AFTER identities and every label-free gate passed and BEFORE the first label. Only POST and GET are issued."""
    env = os.environ if env is None else env
    if env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("FORMAL_EXECUTION_REQUIRES_ACTIONS_MAIN")
    if lock_exists(env, api):
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


# --------------------------------------------------------------------------- #
# Signal-time assembly (past-only; allowed BEFORE the lock because it can stop the run without spending it)
# --------------------------------------------------------------------------- #
def calendar_facts(spec=None):
    days = RC.sessions(T.FEATURE_START, T.DEVELOPMENT_CUTOFF, "KR")
    weekly = weekly_grid(T.FEATURE_START, T.DEVELOPMENT_CUTOFF, "KR")
    anchors = R.anchor_schedule(days, weekly, T.EVALUATION_START, T.STRIDE_KR_SESSIONS)
    return [str(d.date()) for d in days], weekly, anchors


def _window(frame, days, pos, length):
    if frame is None or pos - length + 1 < 0:
        return None
    return pd.to_numeric(frame["Close"].reindex(days[pos - length + 1:pos + 1]), errors="coerce").to_numpy(float)


def build_signal_bundle(input_root, spec, root, counters):
    """Every signal-time quantity, through the sealed loaders: PIT Top120, the 11 sealed features, the derived price / liquidity features, the v4
    industry state, leave-one-out industry momentum and the past-only market state. Nothing after a signal date is read."""
    counters["featureBuilds"] += 1
    v1_spec, _ = X.load_spec(root)
    accounting, memberships, market, prices = X.load_sources(input_root, v1_spec)
    benchmark = prices.get(T.BENCHMARK)
    all_days = RC.sessions("2013-01-01", "2028-12-31", "KR")
    days_list = [str(d.date()) for d in all_days]
    _, weekly, anchors = calendar_facts()
    schedule, rows = {}, []
    for date in weekly:
        snapshot = memberships.on(date)
        if snapshot is None:
            raise ValueError("PIT_MEMBERSHIP_MISSING: " + date)
        schedule[date] = list(snapshot["members"])
        pos = all_days.searchsorted(pd.Timestamp(date), side="right") - 1
        bench = _window(benchmark, all_days, pos, 253)
        state = O.state_at(benchmark, date)
        for ticker in snapshot["members"]:
            row = VQ.feature_at(ticker, date, accounting.get(ticker, []), market, prices.get(ticker), benchmark)
            quote = market.at(ticker, date)
            cap = (quote or {}).get("marketCap")
            close = _window(prices.get(ticker), all_days, pos, 253)
            row.update(F.derived_price_features(close if close is not None else [], bench if bench is not None else []))
            trailing = market.trailing(ticker, date, 60)
            row.update(F.liquidity_features(trailing, cap))
            tv = [q["tradingValue"] if q is not None else np.nan for q in trailing] if len(trailing) == 60 else []
            row["logAmihud60"] = F.amihud(close[-61:] if close is not None else [], tv)
            row["marketCap"] = cap if cap is not None else np.nan
            row["marketTrendAdverse"] = float(state["trendAdverse"]) if state.get("status") == "READY" else np.nan
            row["marketVol63"] = state.get("benchmarkVol63", np.nan) if state.get("status") == "READY" else np.nan
            rows.append(row)
    features = pd.DataFrame(rows)
    A.assert_pit_membership(features, AE.load_memberships(input_root, v1_spec))
    intervals, crosswalk, ends = IE.load_membership_inputs(root)
    membership = I.membership_table(schedule, intervals, crosswalk, ends)
    cohorts = I.build_cohorts(membership, features[["date", "ticker", "marketCap"]])
    stock_cohorts = S.build_cohorts(membership)
    industry_of = {(r.date, r.ticker): r.industry for r in membership.itertuples() if isinstance(r.industry, str)}
    extra = []
    for date in weekly:
        group = features[features.date == date]
        past = IE.past_features(prices, schedule[date], all_days, date)
        panel_values = {r["ticker"]: r for r in group.to_dict("records")}
        eligible = {ind: c for (d, ind), c in cohorts.items() if d == date and c["status"] == "ELIGIBLE"}
        ind_values = {ind: I.industry_features(c, past, panel_values) for ind, c in sorted(eligible.items())}
        caps = dict(zip(group.ticker, group.marketCap))
        trail = {t: past.get(t, {}).get("trail126", np.nan) for t in schedule[date]}
        for ticker in group.ticker:
            ind = industry_of.get((date, ticker))
            sc = stock_cohorts.get((date, ind)) if ind else None
            peers = S.peers_of(sc, ticker)
            rec = {"date": date, "ticker": ticker, "industry": ind if ind in eligible else np.nan, "industryEligible": bool(ind in eligible),
                   "stockMinusLooIndustry126": F.loo_industry_momentum(ticker, peers, trail, caps)}
            for f in T.INDUSTRY_FEATURES:
                rec["ind_" + f] = ind_values[ind].get(f, np.nan) if ind in ind_values else np.nan
            extra.append(rec)
    features = features.merge(pd.DataFrame(extra), on=["date", "ticker"], how="left", validate="one_to_one")
    return {"features": features, "schedule": schedule, "weekly": weekly, "anchors": anchors, "allDays": all_days, "daysList": days_list,
            "prices": prices, "market": market, "v1Spec": v1_spec, "membership": membership}


def _v4(root):
    from .kr_industry_membership import top120_schedule
    inputs = json.loads((Path(root) / "data/kr-industry-membership-foundation-v1/top120-inputs.json").read_text())
    return {d: [n[4:] if n.startswith("KRX:") else n for n in names] for d, names in top120_schedule(inputs)[0].items()}


def signal_coverage(features, anchors):
    """Share of outer anchors whose signal date has at least MIN_NAMES_PER_LABEL_DATE tradable names above the ADV floor (signal-time only)."""
    outer = [(d, s) for d, s in anchors if int(d[:4]) >= T.OUTER_FIRST_YEAR]
    ok = 0
    for _, signal in outer:
        g = features[features.date == signal]
        n = int((g.tradable.astype(bool) & (pd.to_numeric(g.adv60, errors="coerce") >= T.PORTFOLIO["minimumAdvKrw"])).sum())
        ok += n >= T.MIN_NAMES_PER_LABEL_DATE
    return 100.0 * ok / max(1, len(outer)), len(outer)


def pre_lock_gates(bundle, spec, root):
    """Label-free, value-free reasons the study cannot run; empty means ready."""
    reasons = []
    features = bundle["features"]
    if features.empty or not bundle["anchors"]:
        return ["NO_PIT_NAME_DATES_OR_ANCHORS"]
    if features.duplicated(["date", "ticker"]).any():
        reasons.append("DUPLICATE_PIT_NAME_DATE")
    v4 = _v4(root)
    for date, members in sorted(bundle["schedule"].items()):
        if date not in v4 or set(members) != set(v4[date]):
            reasons.append("PIT_TOP120_DIFFERS_FROM_V4_MEMBERSHIP_UNIVERSE:" + date)
    if any(prov.get("availableFrom", "") >= date for date, prov in zip(features.date, features.accountingProvenance)):
        reasons.append("ACCOUNTING_PUBLICATION_NOT_STRICTLY_PRIOR")
    missing = [c for c in (*T.STOCK_FEATURES, *("ind_" + f for f in T.INDUSTRY_FEATURES), *T.MARKET_FEATURES) if c not in features]
    if missing:
        reasons.append("SIGNAL_TIME_COLUMNS_MISSING:" + ",".join(missing))
    coverage, _ = signal_coverage(features, bundle["anchors"])
    if coverage < T.MIN_SIGNAL_COVERAGE_PERCENT:
        reasons.append("SIGNAL_COVERAGE_BELOW_%d_PERCENT" % T.MIN_SIGNAL_COVERAGE_PERCENT)
    reasons += calendar_plan_reasons(calendar_fold_plan())
    return sorted(set(reasons))


def calendar_plan_reasons(plan):
    """A year with too little inner history is a registered PASSIVE year, not a blocker; only a plan with NO year able to become active blocks."""
    if not any(f["innerEvidence"]["sufficient"] for f in plan["folds"]):
        return ["NO_OUTER_YEAR_HAS_SUFFICIENT_INNER_EVIDENCE_BY_CALENDAR"]
    return []


def calendar_fold_plan():
    """The outer folds and their inner blocks from the CALENDAR ALONE (a weekly date's H126 label exit is calendar arithmetic, no price)."""
    days, weekly, anchors = calendar_facts()
    cal = W.Calendar(RC.sessions("2013-01-01", "2028-12-31", "KR"))
    exits = {d: cal.exit(d, T.PRIMARY_HORIZON) for d in weekly}
    folds = []
    for fold in W.outer_folds(anchors):
        train = [d for d in weekly if exits[d] < fold["cutoff"]]
        recent = train[len(train) // 2:]
        blocks = [list(b) for b in np.array_split(np.array(recent, dtype=object), T.INNER_BLOCKS)]
        plan = []
        for b in blocks:
            first_entry = cal.entry(b[0])
            emb = cal.days[cal.pos_on_or_before(b[0]) - T.EMBARGO_SESSIONS]
            inner_train = [d for d in train if exits[d] < first_entry and d <= emb]
            plan.append({"validFrom": b[0], "validTo": b[-1], "validationDates": len(b), "innerTrainingDates": len(inner_train),
                         "purgeRule": "exit < " + first_entry, "embargoThrough": emb,
                         "status": "VALID" if len(inner_train) >= T.MIN_TRAIN_DATES and len(b) >= T.MIN_VALID_DATES else "INSUFFICIENT"})
        valid = sum(b["status"] == "VALID" for b in plan)
        sufficient = valid >= T.MIN_VALID_FOLDS and valid - 1 >= T.MIN_ECONOMIC_FOLDS
        folds.append({"year": fold["year"], "cutoff": fold["cutoff"], "anchors": len(fold["anchors"]), "calendarTrainingDates": len(train),
                      "firstTrainingSignal": train[0] if train else None, "lastTrainingSignal": train[-1] if train else None, "innerBlocks": plan,
                      "innerEvidence": {"validInnerFolds": valid, "economicScoringFoldsAvailable": max(0, valid - 1),
                                        "requiredValidInnerFolds": T.MIN_VALID_FOLDS, "requiredFiniteEconomicFolds": T.MIN_ECONOMIC_FOLDS,
                                        "sufficient": sufficient,
                                        "plannedState": "ELIGIBLE_FOR_INNER_SELECTION" if sufficient else T.PASSIVE_INSUFFICIENT_EVIDENCE,
                                        "keptInFinalEvaluation": True}})
    return {"weeklyDates": len(weekly), "anchors": len(anchors), "outerAnchors": sum(f["anchors"] for f in folds), "folds": folds,
            "passiveInsufficientInnerEvidenceYearsByCalendar": [f["year"] for f in folds if not f["innerEvidence"]["sufficient"]],
            "passiveYearsNote": "a year listed here is 100% passive because too little past-only inner history existed at its cutoff; it is not "
                                "moved, re-dated or dropped, and its sessions stay in every final active-vs-passive statistic"}


# --------------------------------------------------------------------------- #
# Real-data adapters (OUTCOME side: used only after the lock)
# --------------------------------------------------------------------------- #
class RealContext:
    def __init__(self, bundle):
        self.ctx = R.Context(bundle["prices"], bundle["market"], bundle["allDays"])
        self.calendar = W.Calendar(bundle["allDays"])
        self.prices = bundle["prices"]
        self._risk = {}

    def close_at(self, ticker, day):
        frame = self.prices.get(ticker)
        stamp = pd.Timestamp(day)
        if frame is None or stamp not in frame.index:
            return None
        value = frame.loc[stamp, "Close"]
        return float(value) if np.isfinite(value) and value > 0 else None

    def mark(self, ticker, day, previous):
        return R.mark_price(self.ctx, ticker, day, previous)

    def executable(self, ticker, day):
        quote = self.ctx.market.at(ticker, day)
        return bool(quote and quote["volume"] > 0)

    def adv_of(self, ticker, day):
        prev = self.calendar.days[self.calendar.pos_on_or_before(day) - 1]
        return R.adv_map(self.ctx, [ticker], prev, day).get(ticker)

    def risk(self, schedule):
        def provider(date):
            if date not in self._risk:
                pos = self.ctx.days.searchsorted(pd.Timestamp(date), side="right") - 1
                closes = {t: _window(self.prices.get(t), self.ctx.days, pos, T.COVARIANCE_LOOKBACK + 1) for t in schedule[date]}
                closes = {t: c for t, c in closes.items() if c is not None}
                self._risk[date] = P.risk_inputs(closes, _window(self.prices.get(T.BENCHMARK), self.ctx.days, pos, T.COVARIANCE_LOOKBACK + 1))
            return self._risk[date]
        return provider


def terminal_ineligible(bundle, root, through):
    """(date, ticker) pairs whose MATURED label the sealed terminal discipline withholds (attach_eligibility, the v1 rule)."""
    foundation = json.loads((Path(root) / bundle["v1Spec"]["inputs"]["terminalFoundationPath"]).read_text())
    complete = {row["code"] + ".KS": row.get("completeness") for row in foundation.get("securities", [])}
    attach = AE.sealed_v1_function("attach_eligibility")
    cal = W.Calendar(bundle["allDays"])
    out = set()
    for date, tickers in bundle["schedule"].items():
        exit_ = cal.exit(date, T.PRIMARY_HORIZON)
        if exit_ > through:
            continue
        elig = attach(pd.DataFrame({"ticker": tickers, "outcomeEndDate": [exit_] * len(tickers)}), bundle["prices"], complete)
        out |= {(date, t) for t, s in zip(tickers, elig.eligibilityStatus) if s != "ELIGIBLE"}
    return out


def cross_check_endpoints(labels, bundle, spec, through):
    """Every H126 relative label equals the sealed `target_from_sessions` (same entry, exit, status, value)."""
    target = AE.sealed_v1_function("target_from_sessions")
    for r in labels.itertuples():
        theirs = target(bundle["allDays"], bundle["prices"], T.BENCHMARK, r.ticker, r.date, T.PRIMARY_HORIZON, through)
        if theirs["labelStatus"] == "MATURED" and r.status == "MATURED" and np.isfinite(r.yEcon) \
                and abs(theirs["forwardRelativeReturn"] - r.yEcon) > 1e-12:
            raise ValueError("ENDPOINT_SEMANTICS_DIFFER_FROM_V1_TARGET")
        if (theirs["labelStatus"] == "MATURED") != (r.status == "MATURED"):
            raise ValueError("ENDPOINT_STATUS_DIFFERS_FROM_V1_TARGET")
    return True


# --------------------------------------------------------------------------- #
# Writing (canonical JSON; immutable first write)
# --------------------------------------------------------------------------- #
def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return [json_safe(v) for v in value.tolist()]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write(path, document, immutable=False):
    return X.atomic_write(path, json_safe(document), immutable=immutable)


def write_marker(output, spec, sha, counters, lock):
    require_lock(lock, sha)
    if not outcomes_zero(counters):
        raise ValueError("MARKER_AFTER_OUTCOME_ACCESS")
    counters["markerWrites"] += 1
    return write(Path(output) / MARKER_FILE, {"studyId": STUDY, "specSha256": sha, "lockRef": lock.ref, "studyLockRef": STUDY_LOCK_REF,
                                              "lockedMainSha": lock.mainSha, "valuesReadBeforeThisMarker": 0, "counters": dict(counters),
                                              "scientificStatus": T.SCIENTIFIC_STATUS}, immutable=True)


def execute(input_root, output, spec, sha, permit, root=ROOT, env=None, api=github_api):
    """The single development execution. Everything before `claim_execution_lock` is label-free and can stop the run without spending it."""
    require_permit(permit)
    counters = new_counters()
    output = Path(output)
    identity_before = X.input_identity(input_root)["sha256"]
    if identity_before != spec["input"]["identitySha256"]:
        raise ValueError("INPUT_IDENTITY_MISMATCH")
    bundle = build_signal_bundle(input_root, spec, root, counters)
    reasons = pre_lock_gates(bundle, spec, root)
    if reasons:
        write(output / "gates-failed.json", {"studyId": STUDY, "specSha256": sha, "reasons": reasons, "counters": counters,
                                             "spent": False, "rule": "a pre-lock refusal spends nothing; no lock exists"})
        raise ValueError("PRE_LOCK_GATES_FAILED: " + ";".join(reasons))
    if not outcomes_zero(counters):
        raise ValueError("OUTCOME_ACCESS_BEFORE_LOCK")
    lock = claim_execution_lock(sha, env, api)
    write_marker(output, spec, sha, counters, lock)
    # ---------------- outcomes from here on: permit AND lock held ----------------
    require_lock(lock, sha)
    real = RealContext(bundle)
    rows = bundle["features"]
    rep = F.represent(rows)
    data = W.prepare_data(rep)
    ineligible = terminal_ineligible(bundle, root, T.DEVELOPMENT_CUTOFF)
    raw_labels = ST.build_labels(rows[["date", "ticker", "industry", "industryEligible", "marketCap"]], real.calendar, real.close_at,
                                 T.DEVELOPMENT_CUTOFF, ineligible, counters)
    cross_check_endpoints(raw_labels, bundle, spec, T.DEVELOPMENT_CUTOFF)
    labels = W.align_labels(data, raw_labels)
    risk = real.risk(bundle["schedule"])
    process = W.run_process(data, labels, bundle["anchors"], T.candidate_registry(), risk, real.calendar, counters)
    outer = W.outer_folds(bundle["anchors"])
    first = outer[0]["anchors"][0][0]
    paths = ST.run_paths(process["anchors"], data, risk, bundle["daysList"], first, T.DEVELOPMENT_CUTOFF, real.mark, real.executable,
                         real.adv_of, counters)
    coverage, outer_count = signal_coverage(rows, bundle["anchors"])
    identity_after = X.input_identity(input_root)["sha256"]
    counters["metricCalls"] += 1
    assessed = ST.assemble(process, paths, labels, coverage, identity_unchanged=identity_after == identity_before)
    result = {"studyId": STUDY, "specSha256": sha, "lockRef": lock.ref, "lockedMainSha": lock.mainSha, "scientificStatus": T.SCIENTIFIC_STATUS,
              "developmentStatement": T.DEVELOPMENT_STATEMENT, "inputIdentitySha256": identity_before, "inputIdentityAfterSha256": identity_after,
              "trialLedger": T.trial_ledger(len(process["folds"])), "process": ST.process_summary(process), "outerAnchors": outer_count,
              "signalCoveragePercent": coverage, **{k: v for k, v in assessed.items()}, "counters": counters, "promotionEligible": False,
              "prospectiveEvidence": "NONE: development evidence on outcome-exposed history; confirmation is prospective receipts only"}
    result_sha = write(output / RESULT_FILE, result, immutable=True)
    marker_sha = file_hash(output / MARKER_FILE)
    write(output / MANIFEST_FILE, {"studyId": STUDY, "specSha256": sha, "files": {RESULT_FILE: result_sha, MARKER_FILE: marker_sha},
                                   "counters": counters, "scientificStatus": T.SCIENTIFIC_STATUS}, immutable=True)
    return result


# --------------------------------------------------------------------------- #
# Outcome-free readiness and verify
# --------------------------------------------------------------------------- #
def committed_membership_depth(root=ROOT):
    v4 = _v4(root)
    sizes = [len(v) for v in v4.values()]
    return {"weeklyDates": len(v4), "minMembers": min(sizes), "maxMembers": max(sizes), "source": "data/kr-industry-membership-foundation-v1/top120-inputs.json"}


def synthetic_determinism(full=False):
    """The whole tournament twice on the invented world; the canonical result digests must agree. Uses a separate counter dict."""
    digests = []
    for _ in range(2):
        out = ST.run_synthetic(ST.SyntheticWorld(names=24, industries=4), full=full, counters={})
        digests.append(digest(json_safe({k: v for k, v in out["result"].items()})))
    return {"deterministic": digests[0] == digests[1], "resultDigest": digests[0], "registry": "FULL" if full else "ONE_PER_FAMILY",
            "world": "INVENTED: no market data, no claim about any market"}


def readiness_audit(root=ROOT, full_registry=False):
    counters = new_counters()
    plan = calendar_fold_plan()
    spec, sha = load_spec(root)
    synthetic = synthetic_determinism(full=full_registry)
    reasons = calendar_plan_reasons(plan)
    if not synthetic["deterministic"]:
        reasons.append("SYNTHETIC_TOURNAMENT_NOT_DETERMINISTIC")
    if not outcomes_zero(counters):
        reasons.append("OUTCOME_COUNTER_NONZERO")
    return {"studyId": STUDY, "specSha256": sha, "decision": DECISION_READY if not reasons else "BLOCKED_BEFORE_EXECUTION", "reasons": reasons,
            "calendarFoldPlan": plan, "membershipDepth": committed_membership_depth(root), "trialLedger": T.trial_ledger(len(plan["folds"])),
            "synthetic": synthetic, "counters": counters, "realOutcomesRead": False, "rawArtifactTouched": False,
            "note": "dates, committed membership and an invented world only; no price after any signal date, no label, no real fit, no real portfolio"}


def verify(root=ROOT):
    spec, sha = load_spec(root)
    for rel in (RESULT_PATH, MARKER_PATH, MANIFEST_PATH):
        if (Path(root) / rel).exists():
            raise ValueError("RESULT_ALREADY_PRESENT_IN_A_PREREGISTRATION_CHECKOUT: " + rel)
    return {"studyId": STUDY, "specSha256": sha, "verified": True, "outcomeCountersZero": True}
