"""rp1-c1-us-exposure-ladder-replication-v1 — WP4d: source freeze, owner authorization, the one-shot execution, its validator and its report.

FROZEN_RULE_REPLICATION_ON_PUBLICLY_KNOWN_US_HISTORY. Nothing here changes a rule, a threshold, a window, a cost, a metric or the decision; all of
those are the frozen spec's (`rp1_c1_us_exposure_spec.load_spec` compares them on every load). This module is the harness around them and lives
outside the spec's sealed closure, as the v4/v5 harnesses did; the owner's authorization pins every one of its files.

Stages in the existing host workflow (see `HOST_WORKFLOW`); this storage migration also freezes on its reviewed merge:

  freeze-sources  acquire the four US sources with the repository's acquirer, run the dates-only readiness on bounded inputs and open ONE Draft PR carrying only the dates-and-hashes manifest and the re-pinned spec. No US outcome is computed.
  dry-run         reacquire and verify the pinned bounded inputs, run every pre-lock check, then run the whole evaluation, the validator and the report on
                  INVENTED values over the real XNYS calendar. No lock, no US value.
  execute         the owner's dispatch on merged main with the exact committed authorization: pins, readiness READY, equivalence EXACT, then the
                  durable lock, the marker, and only then the first US value. A failure after the lock consumes the study; there is no retry.

STORAGE AND RIGHTS. Three of the four US sources are licensed data whose terms do not permit redistribution (`rp1_c1_us_sources.SOURCE_RIGHTS`).
Their bytes exist only inside a runner until discarded; outputs carry aggregate statistics, never a daily price, level or NAV
series.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from . import kr_market_risk_anatomy_analysis as AN
from . import kr_market_risk_model as K
from . import kr_market_risk_model_execution as E
from . import kr_market_risk_source_parse as P
from . import rp1_c1_us_exposure as U
from . import rp1_c1_us_exposure_spec as SP
from . import rp1_c1_us_sources as SRC
from . import rp1_c1_us_validator as V
from . import rp1_c1_us_refetch as R
from .kr_model_portfolio_execution import file_hash

ROOT = Path(__file__).resolve().parents[1]
STUDY = SP.STUDY
HOST_WORKFLOW = ".github/workflows/seal-kr-factor-anatomy-v1.yml"
AUTHORIZATION_DIR = "docs/research-program/authorizations"
AUTHORIZATION_PATH = AUTHORIZATION_DIR + "/rp1-c1-us-exposure-execution-authorization.json"
AUTHORIZATION_TEMPLATE_PATH = AUTHORIZATION_DIR + "/rp1-c1-us-exposure-execution-authorization.template.json"
CONTRACT = "RP1_C1_US_EXPOSURE_SCOPED_PRIMARY_AND_CASH_V1"
AUTHORIZES = "ONE_FORMAL_EXECUTION"
ACKNOWLEDGMENTS = ("frozenRuleReplicationNotValidation", "publiclyKnownUsHistory", "oneShotFailureAfterTheLockConsumesTheStudy",
                   "noThresholdWindowRuleOrCandidateChangeAfterTheResult", "noProductionOrPortfolioChange", "licensedSourceBytesStayRunnerTemporaryAndNeverPublished",
                   "economicReadingIsDescriptiveAndCannotChangeTheDecision", "separateCashEconomicSpecReviewed")
HARNESS_FILES = ("pipeline/rp1_c1_us_execution.py", "pipeline/rp1_c1_us_validator.py", "scripts/run_rp1_c1_us_wp4d.py", HOST_WORKFLOW)
RESULTS_ARTIFACT_PREFIX = "rp1-c1-us-exposure-results-"
ATTEMPT_ARTIFACT_PREFIX = "rp1-c1-us-exposure-attempt-"
LOCK_PREFIX = "refs/tags/" + STUDY + "-execution-lock"
RESULT_FILE, MARKER_FILE, MANIFEST_FILE, VALIDATION_FILE, REPORT_FILE = ("result.json", "execution-started.json", "manifest.json", "validation.json",
                                                                         "report.md")
SYNTHETIC_STAMP = "SYNTHETIC_VALUES_DRY_RUN_NOT_A_RESULT"


class Refused(ValueError):
    """A pre-lock refusal: nothing is spent."""


@dataclass
class Counters:
    """Strategy value loads and outcomes are counted; source hash/unit/sanity checks produce no outcome. Pre-lock modes leave these at zero."""
    usValueReads: int = 0
    evaluations: int = 0
    validations: int = 0
    markerWrites: int = 0
    lockClaims: int = 0

    def zero(self):
        return all(v == 0 for v in asdict(self).values())


@dataclass(frozen=True)
class Permit:
    specSha256: str
    authorizationSha256: str
    token: object


@dataclass(frozen=True)
class Lock:
    specSha256: str
    mainSha: str
    ref: str
    token: object


_PERMIT, _LOCK = object(), object()


def _require(permit, lock, sha):
    if not isinstance(permit, Permit) or permit.token is not _PERMIT or permit.specSha256 != sha:
        raise ValueError("US_OUTCOME_ACCESS_WITHOUT_PERMIT")
    if not isinstance(lock, Lock) or lock.token is not _LOCK or lock.specSha256 != sha:
        raise ValueError("DURABLE_EXECUTION_LOCK_REQUIRED_BEFORE_ANY_US_VALUE")


def _git(args, root):
    return subprocess.check_output(["git", *args], cwd=str(root))


# =======================================================================================================================================
# Pins and the owner's authorization
# =======================================================================================================================================
def harness_pins(root=ROOT):
    return {rel: file_hash(Path(root) / rel) for rel in HARNESS_FILES}


def current_pins(root=ROOT):
    """Everything an authorization fixes: the spec and its scientific digest, the source freeze, and every harness file."""
    spec, sha = SP.load_spec(root)
    pin = spec["inputs"]["usSnapshot"]
    if pin["status"] != "FROZEN":
        raise Refused("SOURCE_FREEZE_NOT_PINNED_BY_THE_SPEC")
    return {"specSha256": sha, "scientificSha256": SP.scientific_digest(spec),
            "cashEconomicScientificSha256": spec["cashEconomicSpec"]["scientificSha256"],
            "sourceFreeze": {k: pin[k] for k in ("manifestPath", "manifestSha256", "freezeRunId", "normalization", "analysisFiles", "scopedInputs")},
            "harness": harness_pins(root)}


def authorization_template():
    return {"contract": CONTRACT, "studyId": STUDY, "authorizes": "NOTHING", "ownerLogin": "OWNER_APPROVAL_NOT_ISSUED",
            "acknowledgments": {k: False for k in ACKNOWLEDGMENTS}, "pins": {},
            "instructions": "NON_AUTHORIZING_TEMPLATE. After the source freeze is merged, `python scripts/run_rp1_c1_us_wp4d.py authorization-draft "
                            "--owner <login>` prints the exact pins. The owner reviews them, sets every acknowledgment to true deliberately, commits the "
                            "file at " + AUTHORIZATION_PATH + " through a reviewed PR, and types the SHA-256 of the committed bytes into the execute "
                            "dispatch. Nothing else authorizes an execution."}


def authorization_draft(root=ROOT, owner=""):
    if not owner:
        raise Refused("OWNER_LOGIN_REQUIRED")
    return {"contract": CONTRACT, "studyId": STUDY, "authorizes": AUTHORIZES, "ownerLogin": owner,
            "acknowledgments": {k: False for k in ACKNOWLEDGMENTS}, "pins": current_pins(root),
            "instructions": "DRAFT. It authorizes nothing until the owner sets every acknowledgment to true and commits it at " + AUTHORIZATION_PATH}


def authorization_status(root=ROOT):
    """Outcome-free description for verify and dry-run: is an authorization committed, and do its pins still match? Never a permit."""
    path = Path(root) / AUTHORIZATION_PATH
    if not path.exists():
        return {"status": "NOT_ISSUED", "path": AUTHORIZATION_PATH}
    try:
        auth, pins = json.loads(path.read_text()), current_pins(root)
    except (ValueError, KeyError, OSError) as error:
        return {"status": "UNVERIFIABLE", "reason": str(error)}
    complete = auth.get("authorizes") == AUTHORIZES and all(auth.get("acknowledgments", {}).get(k) is True for k in ACKNOWLEDGMENTS)
    return {"status": ("ISSUED_PINS_MATCH" if auth.get("pins") == pins else "ISSUED_PINS_DIFFER") if complete else "INCOMPLETE",
            "sha256": file_hash(path), "ownerLogin": auth.get("ownerLogin")}


def authorize(root, env, expected_sha, git=_git, api=E.github_api):
    """Raise unless: first attempt of a workflow_dispatch on main by the repository owner, at the current main tip, carrying the committed spec and the
    committed authorization whose SHA-256 the owner typed, with scope ONE_FORMAL_EXECUTION, every acknowledgment true, every pin equal to the current
    bytes, no result or marker and no lock."""
    root = Path(root)
    if env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_EVENT_NAME") != "workflow_dispatch" or env.get("GITHUB_REF") != "refs/heads/main" \
            or env.get("GITHUB_RUN_ATTEMPT") != "1":
        raise Refused("REQUIRES_THE_FIRST_ATTEMPT_OF_A_MANUAL_DISPATCH_ON_MAIN")
    if env.get("GITHUB_ACTOR") != env.get("GITHUB_REPOSITORY", "/").split("/")[0]:
        raise Refused("OWNER_DISPATCH_REQUIRED")
    head = git(["rev-parse", "HEAD"], root).decode().strip()
    if head != env.get("GITHUB_SHA"):
        raise Refused("CHECKOUT_IS_NOT_THE_DISPATCHED_COMMIT")
    status, body = api("GET", "/git/ref/heads/main", None, env)
    if status != 200 or (body.get("object") or {}).get("sha") != head:
        raise Refused("DISPATCHED_COMMIT_IS_NOT_THE_MAIN_TIP")
    for rel in (SP.SPEC_PATH, str(Path(SP.SPEC_PATH).with_suffix(".sha256")), SP.SCIENTIFIC_SIDECAR):
        if git(["show", "HEAD:" + rel], root) != (root / rel).read_bytes():
            raise Refused("SPEC_NOT_COMMITTED_AT_HEAD")
    try:
        raw = git(["show", "HEAD:" + AUTHORIZATION_PATH], root)
    except subprocess.CalledProcessError as error:
        raise Refused("NO_COMMITTED_OWNER_AUTHORIZATION") from error
    if raw != (root / AUTHORIZATION_PATH).read_bytes():
        raise Refused("AUTHORIZATION_NOT_COMMITTED_AT_HEAD")
    if not expected_sha or file_hash(root / AUTHORIZATION_PATH) != expected_sha:
        raise Refused("OWNER_AUTHORIZATION_HASH_MISMATCH")
    auth = json.loads(raw)
    if auth.get("contract") != CONTRACT or auth.get("studyId") != STUDY or auth.get("authorizes") != AUTHORIZES \
            or auth.get("ownerLogin") != env["GITHUB_ACTOR"] or any(auth.get("acknowledgments", {}).get(k) is not True for k in ACKNOWLEDGMENTS):
        raise Refused("OWNER_SCOPE_OR_ACKNOWLEDGMENT_MISSING")
    pins = current_pins(root)
    if auth.get("pins") != pins:
        raise Refused("AUTHORIZED_PINS_DIFFER_FROM_THE_CURRENT_BYTES")
    for rel, code in ((SP.RESULT_PATH, "RESULT"), (SP.MARKER_PATH, "MARKER")):
        if (root / rel).exists():
            raise Refused("RP1_C1_" + code + "_ALREADY_COMMITTED")
    if lock_exists(env, api):
        raise Refused("EXECUTION_LOCK_ALREADY_EXISTS")
    return Permit(pins["specSha256"], expected_sha, _PERMIT)


# =======================================================================================================================================
# The durable one-shot lock (git refs; only POST and GET are ever issued)
# =======================================================================================================================================
def lock_ref(spec_sha):
    return LOCK_PREFIX + "-" + spec_sha


def lock_exists(env, api=E.github_api):
    if not env.get("GH_TOKEN") or not env.get("GITHUB_REPOSITORY"):
        raise Refused("EXECUTION_LOCK_STATE_UNVERIFIABLE")
    status, body = api("GET", "/git/matching-refs/" + LOCK_PREFIX[len("refs/"):], None, env)
    if status == 200 and isinstance(body, list):
        return len(body) > 0
    raise Refused("EXECUTION_LOCK_STATE_UNVERIFIABLE")


def claim_lock(permit, env, api=E.github_api, counters=None):
    if not isinstance(permit, Permit) or permit.token is not _PERMIT:
        raise ValueError("LOCK_WITHOUT_PERMIT")
    if lock_exists(env, api):
        raise Refused("EXECUTION_LOCK_ALREADY_EXISTS")
    main_sha = env["GITHUB_SHA"]
    if counters is not None:
        counters.lockClaims += 1
    for target in (LOCK_PREFIX, lock_ref(permit.specSha256)):
        status, _ = api("POST", "/git/refs", {"ref": target, "sha": main_sha}, env)
        if status == 422:
            raise ValueError("EXECUTION_LOCK_ALREADY_EXISTS")
        if status != 201:
            raise ValueError("ATOMIC_EXECUTION_LOCK_NOT_CREATED")
    for target in (LOCK_PREFIX, lock_ref(permit.specSha256)):
        status, body = api("GET", "/git/ref/" + target[len("refs/"):], None, env)
        if status != 200 or (body.get("object") or {}).get("sha") != main_sha:
            raise ValueError("EXECUTION_LOCK_NOT_ON_THE_AUTHORIZED_COMMIT")
    return Lock(permit.specSha256, main_sha, lock_ref(permit.specSha256), _LOCK)


# =======================================================================================================================================
# Outcome-free stages: probe and freeze
# =======================================================================================================================================
def snapshot_summary(snapshot_dir):
    """Per source: status, identity, first/last date, rows and dropped rows, from audit.json. Dates and counts only."""
    audit = SP.snapshot_audit(snapshot_dir) or {"sources": {}}
    keys = ("status", "identityOk", "firstDate", "lastDate", "validRows", "droppedRows", "duplicateDates", "httpStatus", "error", "dividendEventDates")
    return {sid: {k: r.get(k) for k in keys if k in r} for sid, r in audit["sources"].items()}


def probe(root, snapshot_dir):
    """The outcome-free source probe: what was acquired, its identity, and the full dates-only readiness, on an UNPINNED snapshot. Nothing is kept."""
    readiness = SP.readiness_audit(root, snapshot_dir=snapshot_dir)
    return {"studyId": STUDY, "mode": "probe", "sources": snapshot_summary(snapshot_dir), "rights": SRC.SOURCE_RIGHTS, "readiness": readiness,
            "fileCount": len(SP.snapshot_files(snapshot_dir)), "retained": False, "usValueReads": 0,
            "meaning": "a dates-only rehearsal of the formal gates on live vendor bytes; the bytes are discarded with the runner"}


def freeze_manifest(root, snapshot_dir, *, run_id, commit_sha):
    """Bounded analysis digests plus audit-only full raw digests. No values."""
    root = Path(root)
    if (root / AUTHORIZATION_PATH).exists():
        raise Refused("AN_AUTHORIZATION_IS_COMMITTED_WITHDRAW_IT_BEFORE_A_NEW_FREEZE")
    readiness = SP.readiness_audit(root, snapshot_dir=snapshot_dir)
    if readiness["decision"] != SP.DECISION_READY:
        raise Refused("READINESS_NOT_READY: " + ";".join(readiness["blockers"]))
    return {"studyId": STUDY, "kind": "RP1_C1_HASH_REFETCH_MANIFEST_NO_VALUES", "storage": SRC.STORAGE,
            "freezeRunId": str(run_id), "freezeCommitSha": commit_sha, "sourceRegistry": SRC.SOURCES,
            "normalization": {"contract": R.contract(), "codeHashes": R.code_pins(root)},
            "analysisFiles": R.fingerprints(snapshot_dir), "rawFilesAuditOnly": R.provenance(snapshot_dir),
            "scopedInputs": {s: R.scoped_fingerprints(snapshot_dir, s) for s in R.SCOPES},
            "cashEconomicSpec": SP.cash_economic_spec(),
            "observations": {sid: {"firstDate": record.get("firstDate"), "lastDate": record.get("lastDate"),
                "validRows": record.get("validRows"), "identity": record.get("identity"),
                "datesSha256": R.sha(R.encoded([str(d.date()) for d in SP.normalized_dates(Path(snapshot_dir) / sid / "normalized.csv")]))}
                for sid, record in SP.snapshot_audit(snapshot_dir)["sources"].items()},
            "rights": SRC.SOURCE_RIGHTS,
            "readiness": {k: readiness[k] for k in ("decision", "blockers", "checks", "details", "determinable", "decisionDates",
                                                       "firstDecisionDate", "firstExecutionDate", "lastExecutionDate", "counters")},
            "statements": ["No source price, level, rate or return appears in this file.",
                "Raw hashes are provenance only; EXACT bounded analysis hashes are the execution admission.",
                "Re-fetch availability/equality is not guaranteed. A provider revision or access denial stops before the lock; no automatic re-pin."]}


def freeze_manifest_path(run_id):
    return SP.SOURCE_FREEZE_DIR + "/" + SP.SOURCE_FREEZE_PREFIX + str(run_id) + ".json"


# =======================================================================================================================================
# Values (after the lock only) and the post-lock diagnostics
# =======================================================================================================================================
def _read(path):
    return AN.obs_series(P.read_normalized(Path(path).read_bytes()))


def read_values(root, snapshot_dir, economic=True):
    """The source values in the shape `rp1_c1_us_exposure.evaluate` takes. Called only by `load_values` (permit and lock) and by tests."""
    kr = Path(root) / SRC.KR_SNAPSHOT_DIR
    reference = _read(Path(snapshot_dir) / "YAHOO_GSPC" / "normalized.csv")
    return {"reference": reference[reference.index <= pd.Timestamp(U.ANALYSIS_END)],
            "spread": AN.derived_spread(_read(kr / SRC.REUSED["us10y"] / "normalized.csv"), _read(kr / SRC.REUSED["us3m"] / "normalized.csv")),
            "vix": _read(kr / SRC.REUSED["vix"] / "normalized.csv"),
            "asset": _read(Path(snapshot_dir) / "YAHOO_SPY" / "normalized.csv") if economic else pd.Series(dtype=float),
            "cash": _read(Path(snapshot_dir) / "FRED_DTB3" / "normalized.csv") if economic else pd.Series(dtype=float)}


def load_values(root, snapshot_dir, counters, permit, lock, sha, economic=True):
    _require(permit, lock, sha)
    counters.usValueReads += 1
    return read_values(root, snapshot_dir, economic)


def load_cash_values(root, snapshot_dir, values, counters, permit, lock, sha, *, basis="SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED"):
    _require(permit, lock, sha)
    from .winner_inflection_execution import cash_reinvestment_close
    spec, _ = SP.load_spec(root)
    if not SP.verify_us_snapshot(spec, root, snapshot_dir, "CASH_ECONOMIC"):
        raise ValueError("CASH_ECONOMIC_INPUT_NOT_FROZEN")
    counters.usValueReads += 1
    close, events = SRC.cash_components((Path(snapshot_dir) / "YAHOO_SPY/cash_input.json").read_bytes(), basis=basis)
    # Existing #253 arithmetic; never reimplement Replay v11 or cash reinvestment here.
    return {**values, "asset": cash_reinvestment_close(close, events), "cash": _read(Path(snapshot_dir) / "FRED_DTB3/normalized.csv")}


def spy_basis_diagnostic(raw_chart, first_execution, analysis_end):
    """Post-lock compatibility diagnostic: Yahoo adjclose versus Replay v11's vendor-equivalent forward factor.

    This is NOT a cash-dividend reinvestment comparison or independent vendor certification. Neither economic definition is changed.
    """
    from . import price_adjustment as PA
    result = json.loads(raw_chart)["chart"]["result"][0]
    offset = int(result.get("meta", {}).get("gmtoffset", 0))
    dates = pd.DatetimeIndex([pd.Timestamp(int(t) + offset, unit="s").normalize() for t in result["timestamp"]])
    close, events = SRC.cash_components(raw_chart)
    adj = pd.Series(result["indicators"]["adjclose"][0]["adjclose"], index=dates, dtype=float)
    actions = pd.DataFrame([{"date": pd.Timestamp(d), PA.DIVIDEND: dividend, PA.SPLIT: split} for d, dividend, split in events]).set_index("date")
    forward, _ = PA.to_total_return(pd.DataFrame({"Close": close}), actions)
    diff = (adj.pct_change() - forward["Close"].pct_change()).dropna()
    diff = diff[(diff.index >= pd.Timestamp(first_execution)) & (diff.index <= pd.Timestamp(analysis_end))]
    years = len(diff) / K.ANNUALISATION
    return {"sessions": int(len(diff)), "maxAbsoluteDailyDifference": float(diff.abs().max()) if len(diff) else None,
            "sessionsAbove1bp": int((diff.abs() > 1e-4).sum()), "meanDailyDifferencePerYear": float(diff.sum() / years) if years else None,
            "exDividendSessions": sum(first_execution <= d <= analysis_end for d, _, _ in events),
            "comparison": "YAHOO_ADJCLOSE_VS_REPLAY_V11_VENDOR_EQUIVALENT_FORWARD_FACTOR",
            "meaning": "vendor-factor compatibility only, not cash reinvestment or independent certification; descriptive, never a correction"}


def interpretation(result):
    """The frozen interpretation table applied mechanically: the decision maps to one reading; the NO_PROTECTION condition is reported beside it."""
    nomination = result["decision"]["developmentNomination"]
    axes = result["decision"]["axes"]
    protects = [cid for cid in K.CANDIDATE_ORDER if axes[cid]["maxDrawdown"] > axes[K.PASSIVE]["maxDrawdown"]]
    reading = {K.NOMINATION_NONE: "REPLICATED_CONTROL_RETAINED", K.NOMINATION_TRADEOFF: "NOT_REPLICATED_US_TRADEOFF"}.get(nomination,
                                                                                                                          "NOT_REPLICATED_US_NOMINATION")
    return {"reading": reading, "decisionStatus": nomination, "nominated": nomination if nomination in K.CANDIDATE_ORDER else None,
            "noProtectionInUs": bool(K.dominates(axes[K.PASSIVE], axes[K.CONTROL]) and not protects),
            "candidatesWithShallowerDrawdownThanPassive": protects, "table": "spec.interpretation.table, frozen before any US outcome"}


# =======================================================================================================================================
# Evaluation assembly shared by execute and dry-run
# =======================================================================================================================================
def evaluate_and_validate(values, economic_ready, counters):
    config = U.us_config(economic=economic_ready, diagnostics=True)
    counters.evaluations += 1
    result = U.evaluate(values, config)
    counters.validations += 1
    validation = V.validate(values, config, result)
    return config, result, validation


def cash_economic_result(values, primary_result, counters):
    _, result, validation = evaluate_and_validate(values, True, counters)
    for key in ("passive", "candidates", "decision", "window"):
        if E.json_safe(result[key]) != E.json_safe(primary_result[key]):
            raise ValueError("CASH_ECONOMIC_CHANGED_THE_FROZEN_PRIMARY")
    if validation["status"] != "CONSISTENT":
        raise ValueError("CASH_ECONOMIC_FAILED_INDEPENDENT_VALIDATION")
    return {"status": "MEASURED", "spec": SP.cash_economic_spec(), "economic": result["economic"], "validation": validation}


def comparison_rows(result, validation, reading):
    """PASSIVE and C0..C3 on the same economic measures, from the published result (the validator's independent values back each number)."""
    rows, base = [], (result["passive"] if reading == "primary" else result["economic"]["passive"])
    candidates = result["candidates"] if reading == "primary" else result["economic"]["candidates"]
    ind = validation["independent"][reading]
    passive_cagr = base["summary"]["annualizedReturn"]
    rows.append({"strategy": K.PASSIVE, "cagr": passive_cagr, "cagrMinusPassive": 0.0, "maxDrawdown": base["summary"]["maxDrawdown"],
                 "monthlyCvar5": base["monthlyCvar"]["cvar"], "worstMonth": base["monthlyCvar"]["worstMonth"], "costDrag": 0.0, "reducedSessionShare": 0.0,
                 "upMarketCostPerYear": 0.0, "downMarketSavingPerYear": 0.0})
    for cid in K.CANDIDATE_ORDER:
        c = candidates[cid]
        net = c["net"]
        tail = c["diagnostics"]["monthlyCvar"] if reading == "primary" else c["monthlyCvar"]
        gaps = c["diagnostics"]["upDownMarketGap"] if reading == "primary" else c["upDownMarketGap"]
        row = {"strategy": cid, "cagr": net["annualizedReturn"], "cagrMinusPassive": _minus(net["annualizedReturn"], passive_cagr),
               "maxDrawdown": net["maxDrawdown"], "monthlyCvar5": tail["cvar"], "worstMonth": tail["worstMonth"],
               "costDrag": c["implementation"]["costDrag"] if reading == "primary" else c["costDrag"],
               "reducedSessionShare": net["reducedSessionShare"], "upMarketCostPerYear": gaps["upMarketCostPerYear"],
               "downMarketSavingPerYear": gaps["downMarketSavingPerYear"]}
        if reading == "primary":
            re = ind[cid]["reentry"]
            row.update(reboundMissedH63Mean=re["reboundMissedH63"]["mean"], reboundMissedH126Mean=re["reboundMissedH126"]["mean"],
                       sessionsUntilFullExposureMedian=re["sessionsUntilFullExposure"]["median"],
                       recoveryOpportunityCostMean=re["recoveryOpportunityCost"]["mean"],
                       falseAlarmShare=c["falseAlarm"]["falseAlarmShare"],
                       unprotectedEpisodes=sum(1 for e in c["diagnostics"]["protectionByEpisode"] if e["unprotected"]),
                       totalCost=c["implementation"]["totalCostFractionOfNav"])
        rows.append(row)
    return rows


def _minus(a, b):
    return None if a is None or b is None else a - b


def _pct(x, digits=2):
    return "n/a" if x is None else f"{100 * x:.{digits}f}%"


def render_report(result, validation, meaning, stamp=None):
    lines = ["# rp1-c1 US exposure ladder replication — comparison report", ""]
    if stamp:
        lines += [f"**{stamp}** — every number below comes from invented values; it proves the machinery, nothing about the market.", ""]
    lines += [f"Evidence status: `{U.SCIENTIFIC_STATUS}`. {U.EVIDENCE_STATEMENT}", "",
              f"Window: first decision {result['window']['firstDecisionDate']}, last execution {result['window']['lastExecutionDate']}, "
              f"{result['window']['sessions']} sessions, {result['window']['decisionDates']} weekly decisions.", "",
              f"Validator: **{validation['status']}** ({validation['checks']} independent checks, max |difference| "
              f"{validation['maxAbsoluteDifference']:.2e}, tolerance {validation['tolerance']:g}).", ""]
    readings = [("primary", "Primary reading — S&P 500 price index, cash at 0% (the sealed KR convention)", result, validation)]
    if result.get("economic"):
        readings.append(("economic", "Original economic reading — VENDOR adjusted-close SPY, de-risked share earns DTB3", result, validation))
    if result.get("cashEconomic", {}).get("status") == "MEASURED":
        cash = result["cashEconomic"]
        readings.append(("economic", "Separate cash-reinvestment economic reading — " + cash["spec"]["definition"]["id"] +
                         " / scientific SHA-256 " + cash["spec"]["scientificSha256"], {**result, "economic": cash["economic"]}, cash["validation"]))
    for key, title, view, checks in readings:
        lines += [f"## {title}", "", "| strategy | CAGR | vs passive | MDD | monthly CVaR 5% | worst month | cost drag/yr | de-risked share | "
                  "up-market cost/yr | down-market saving/yr |", "|---|---|---|---|---|---|---|---|---|---|"]
        for r in comparison_rows(view, checks, key):
            lines.append(f"| {r['strategy']} | {_pct(r['cagr'])} | {_pct(r['cagrMinusPassive'])} | {_pct(r['maxDrawdown'])} | {_pct(r['monthlyCvar5'])} | "
                         f"{_pct(r['worstMonth'])} | {_pct(r['costDrag'], 3)} | {_pct(r['reducedSessionShare'], 1)} | {_pct(r['upMarketCostPerYear'])} | "
                         f"{_pct(r['downMarketSavingPerYear'])} |")
        if key == "economic":
            lines += ["", f"Cash only (DTB3): CAGR {_pct(view['economic']['cashOnly']['annualizedReturn'])}."]
        lines.append("")
    lines += ["## Re-entry and regime errors (primary reading, reference episodes of at least 15%)", "",
              "| strategy | rebound missed H63 (mean) | rebound missed H126 (mean) | sessions to full exposure (median) | recovery opportunity cost (mean) | "
              "false-alarm share | unprotected episodes | total cost (NAV share) |", "|---|---|---|---|---|---|---|---|"]
    for r in comparison_rows(result, validation, "primary")[1:]:
        lines.append(f"| {r['strategy']} | {_pct(r['reboundMissedH63Mean'])} | {_pct(r['reboundMissedH126Mean'])} | "
                     f"{'n/a' if r['sessionsUntilFullExposureMedian'] is None else int(r['sessionsUntilFullExposureMedian'])} | "
                     f"{_pct(r['recoveryOpportunityCostMean'])} | {_pct(r['falseAlarmShare'], 1)} | {r['unprotectedEpisodes']} | {_pct(r['totalCost'], 3)} |")
    lines += ["", "## Frozen decision and reading", "",
              f"Decision (sealed KR rule, primary reading, net of 1x US costs): `{meaning['decisionStatus']}`; nominated: `{meaning['nominated']}`.",
              f"Frozen interpretation: **{meaning['reading']}**; no-protection condition: `{meaning['noProtectionInUs']}`.", "",
              "Never concluded from this report: that the rule predicts crises, that it is validated, that a threshold should change, or that it rescues "
              "or overturns the KR seal. A rule change needs a NEW study identity.", ""]
    return "\n".join(lines)


# =======================================================================================================================================
# The formal execution
# =======================================================================================================================================
def execute(output, root, snapshot_dir, env, expected_sha, api=E.github_api, git=_git):
    """Order: spec -> authorization -> snapshot pins and dates-only readiness -> KR equivalence -> DURABLE LOCK -> marker -> US values -> evaluation,
    validator, report -> immutable outputs. A refusal before the lock writes gates-blocked.json and spends nothing."""
    out, root = Path(output), Path(root)
    out.mkdir(parents=True, exist_ok=True)
    counters = Counters()
    try:
        spec, sha = SP.load_spec(root)
        permit = authorize(root, env, expected_sha, git, api)
        readiness = SP.readiness_audit(root, snapshot_dir=snapshot_dir, require_frozen=True)
        if readiness["decision"] != SP.DECISION_READY:
            raise Refused("READINESS_NOT_READY: " + ";".join(readiness["blockers"]))
        equivalence = SP.equivalence_audit(root)
        if equivalence["status"] != "EXACT":
            raise Refused("KR_EQUIVALENCE_NOT_EXACT")
    except (ValueError, OSError, KeyError) as error:
        reason = str(error) if isinstance(error, Refused) else "INPUT_VERIFICATION_FAILED:" + type(error).__name__
        E.atomic_write(out / "gates-blocked.json", {"studyId": STUDY, "refusal": reason, "lockClaimed": False, "counters": asdict(counters)})
        raise Refused(reason) from None
    lock = claim_lock(permit, env, api, counters)
    marker = {"studyId": STUDY, "specSha256": sha, "authorizationSha256": permit.authorizationSha256, "lockRef": lock.ref, "studyLockRef": LOCK_PREFIX,
              "lockedMainSha": lock.mainSha, "usValueReadsBeforeThisMarker": counters.usValueReads}
    if marker["usValueReadsBeforeThisMarker"] != 0:
        raise ValueError("VALUES_READ_BEFORE_THE_MARKER")
    counters.markerWrites += 1
    E.atomic_write(out / MARKER_FILE, marker, immutable=True)
    economic_ready = readiness["details"]["economicReading"]["status"] == "ECONOMIC_READING_READY"
    values = load_values(root, snapshot_dir, counters, permit, lock, sha, economic=economic_ready)
    config, result, validation = evaluate_and_validate(values, economic_ready, counters)
    window = result["window"]
    basis = spy_basis_diagnostic((Path(snapshot_dir) / "YAHOO_SPY" / "raw_chart.json").read_bytes(), window["firstExecutionDate"], U.ANALYSIS_END) \
        if economic_ready else None
    meaning = interpretation(result)
    cash_ready = readiness["details"]["cashEconomicReading"]["status"] == "CASH_ECONOMIC_READY"
    cash_result = cash_economic_result(load_cash_values(root, snapshot_dir, values, counters, permit, lock, sha), result, counters) if cash_ready else \
        {"status": "UNRESOLVED", "spec": SP.cash_economic_spec(), "readiness": readiness["details"]["cashEconomicReading"]}
    document = {"studyId": STUDY, "scientificStatus": U.SCIENTIFIC_STATUS, "evidenceStatement": U.EVIDENCE_STATEMENT, "specSha256": sha,
                "authorizationSha256": permit.authorizationSha256, "lockRef": lock.ref, "lockedMainSha": lock.mainSha,
                "sourceFreeze": spec["inputs"]["usSnapshot"]["manifestSha256"], "config": config, **result,
                "economicReadingStatus": readiness["details"]["economicReading"]["status"], "spyBasisDiagnostic": basis, "interpretation": meaning,
                "cashEconomic": cash_result,
                "validationStatus": validation["status"],
                "statements": ["frozen-rule replication on publicly known US history; not validation, not prospective, not production",
                               "the primary asset is the S&P 500 price index with cash at zero, the sealed KR convention; the economic reading is "
                               "descriptive and cannot change the decision",
                               "aggregate statistics only: no daily price, level or NAV series is published"]}
    K.assert_no_forbidden_keys(document)
    files = {RESULT_FILE: E.atomic_write(out / RESULT_FILE, E.json_safe(document), immutable=True),
             VALIDATION_FILE: E.atomic_write(out / VALIDATION_FILE, E.json_safe(validation), immutable=True)}
    report = render_report(document, validation, meaning).encode()
    (out / REPORT_FILE).write_bytes(report)
    files[REPORT_FILE] = file_hash(out / REPORT_FILE)
    files[MARKER_FILE] = file_hash(out / MARKER_FILE)
    manifest = {"studyId": STUDY, "specSha256": sha, "authorizationSha256": permit.authorizationSha256, "counters": asdict(counters), "files": files,
                "sourceFreeze": spec["inputs"]["usSnapshot"]}
    E.atomic_write(out / MANIFEST_FILE, E.json_safe(manifest), immutable=True)
    if validation["status"] != "CONSISTENT":
        raise ValueError("RESULT_FAILED_INDEPENDENT_VALIDATION_STUDY_CONSUMED")
    return manifest


# =======================================================================================================================================
# Dry run: every pre-lock check on the real pins, then the whole pipeline on invented values over the real calendar
# =======================================================================================================================================
def synthetic_us_values(seed=20261017):
    """Invented values on the real XNYS calendar from the grid start to the analysis end (and FRED-style business-day series). Never market data."""
    sessions = U.market_sessions("US", U.GRID_START, U.ANALYSIS_END)
    rng = np.random.default_rng(seed)
    regime = np.where(np.sin(np.arange(len(sessions)) / 260.0) > 0.6, 0.025, 0.010)
    reference = pd.Series(300.0 * np.exp(np.cumsum(0.0003 + regime * rng.standard_normal(len(sessions)))), index=sessions)
    days = pd.date_range(U.GRID_START, U.ANALYSIS_END, freq="B")
    t = np.arange(len(days))
    return {"reference": reference, "asset": reference * np.exp(0.00007 * np.arange(len(sessions))),
            "spread": pd.Series(1.2 * np.sin(t / 400.0) + 0.3 * rng.standard_normal(len(days)), index=days),
            "vix": pd.Series(np.abs(19 + 7 * np.sin(t / 150.0) + 3 * rng.standard_normal(len(days))), index=days),
            "cash": pd.Series(np.maximum(0.0, 3.0 + 2.5 * np.sin(t / 900.0)), index=days)}


def dry_run(output, root, snapshot_dir=None):
    """No permit, no lock, no US value. Reports the authorization state, the snapshot identity and readiness on the pins, the KR equivalence, then runs
    evaluation, validator and report on `synthetic_us_values` and writes them stamped SYNTHETIC."""
    out, root = Path(output), Path(root)
    out.mkdir(parents=True, exist_ok=True)
    counters = Counters()
    spec, sha = SP.load_spec(root)
    frozen = spec["inputs"]["usSnapshot"]["status"] == "FROZEN"
    readiness = SP.readiness_audit(root, snapshot_dir=snapshot_dir, require_frozen=frozen) if snapshot_dir else \
        {"decision": SP.DECISION_BLOCKED, "blockers": ["NO_SNAPSHOT_DIRECTORY_GIVEN"]}
    equivalence = SP.equivalence_audit(root)
    real_reads = counters.usValueReads
    synthetic = Counters()
    config, result, validation = evaluate_and_validate(synthetic_us_values(), True, synthetic)
    result["cashEconomic"] = cash_economic_result(synthetic_us_values(), result, synthetic)
    meaning = interpretation(result)
    (out / ("synthetic-" + REPORT_FILE)).write_text(render_report(result, validation, meaning, stamp=SYNTHETIC_STAMP))
    E.atomic_write(out / ("synthetic-" + VALIDATION_FILE), E.json_safe({"stamp": SYNTHETIC_STAMP, **validation}))
    summary = {"studyId": STUDY, "mode": "dry-run", "specSha256": sha, "sourceFreeze": spec["inputs"]["usSnapshot"]["status"],
               "authorization": authorization_status(root), "readiness": {k: readiness.get(k) for k in ("decision", "blockers", "snapshotIdentity")},
               "equivalence": equivalence["status"], "syntheticPipeline": {"stamp": SYNTHETIC_STAMP, "validation": validation["status"],
                                                                          "checks": validation["checks"], "decisionStatus": meaning["decisionStatus"]},
               "lockClaimed": False, "usValueReads": real_reads, "counters": asdict(counters),
               "readyToExecute": readiness.get("decision") == SP.DECISION_READY and equivalence["status"] == "EXACT"
                                 and authorization_status(root)["status"] == "ISSUED_PINS_MATCH"}
    E.atomic_write(out / "dry-run.json", E.json_safe(summary))
    return summary

