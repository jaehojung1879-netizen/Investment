"""Read-only daily presentation of committed observations; never a selector or assessor.

Only the named persisted sources are read. No fetcher, recorder, outcome builder,
optimizer or promotion path is called. Unknown measurements stay None.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess

from . import weekly_decision as W
from . import prospective_receipt_core as P
from . import kr_selection_challenger as V1
from . import kr_selection_challenger_v2 as V2
from . import rp1_b_h1_state as B
from . import entry_state_shadow_ledger as SH

ROOT = Path(__file__).resolve().parents[1]
STUDIES = {V1.STUDY: V1, V2.STUDY: V2, B.STUDY: B}
STATE = "state/latest.json"
WEEKLY = "ledger/weekly-decisions/"
STEPS = ("record", "outcomes", "assess", "coverage", "hook")
FILES = ("receipts.jsonl", "outcomes.jsonl", "attempts.jsonl", "assessment.json", "coverage.json",
         "outcome-pending.json", "publication-status.json", *(f"publication-status.{s}.json" for s in STEPS))
SHADOW = f"ledger/research-strategies/{SH.STUDY}/publication-status.json"
ALLOWED = {STATE, SHADOW, *(WEEKLY + n for n in ("latest.json", "publication-status.json", "receipts.jsonl")),
           *(f"ledger/research-strategies/{s}/{n}" for s in STUDIES for n in FILES)}
REPO_URL = "https://github.com/jaehojung1879-netizen/Investment"


def utc(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return result.astimezone(timezone.utc)


def _strict_json(raw):
    def refuse(_):
        raise ValueError("NONFINITE_JSON")
    return json.loads(raw, parse_constant=refuse)


class GitSnapshot:
    """Pinned committed blobs only. Missing paths are recorded, never fabricated."""
    def __init__(self, root, commit):
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("FULL_IMMUTABLE_SOURCE_SHA_REQUIRED")
        self.root, self.commit, self.sources = Path(root), commit, {}
        self.committed_at = self._git("show", "-s", "--format=%cI", commit).decode().strip()

    def _git(self, *args):
        import os
        r = subprocess.run(["git", *args], cwd=self.root, capture_output=True,
                           env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})
        if r.returncode:
            # Names the object so a partial clone (blobs fetched lazily, which this reader forbids) is diagnosable: see
            # docs/daily-decision-report.md "Reproduce" for the one command that materialises the blobs first.
            raise ValueError("LOCAL_GIT_SNAPSHOT_UNAVAILABLE: " + (args[-1] if args else "?"))
        return r.stdout

    def read(self, path):
        if path not in ALLOWED:
            raise ValueError("NON_REPORT_SOURCE_REFUSED")
        identity = {"path": path, "commitSha": self.commit, "sha256": None,
                    "url": f"{REPO_URL}/blob/{self.commit}/{path}", "status": "MISSING"}
        self.sources[path] = identity
        entry = self._git("ls-tree", self.commit, "--", path)
        if not entry:
            return None
        if not entry.startswith(b"100644 blob "):
            identity["status"] = "INVALID_BLOB_MODE"
            return None
        size = int(self._git("cat-file", "-s", f"{self.commit}:{path}"))
        if size > 16 * 1024 * 1024:
            identity["status"] = "SOURCE_SIZE_LIMIT"
            return None
        raw = self._git("show", f"{self.commit}:{path}")
        identity.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        try:
            result = ([_strict_json(line) for line in raw.splitlines() if line.strip()]
                      if path.endswith(".jsonl") else _strict_json(raw))
            expected = list if path.endswith(".jsonl") else dict
            if not isinstance(result, expected):
                raise ValueError("SOURCE_SHAPE")
        except (ValueError, UnicodeError):
            identity["status"] = "INVALID_JSON_OR_SHAPE"
            return None
        identity["status"] = "READ"
        return result


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _timestamp_ok(value, as_of):
    try:
        return utc(value) <= as_of
    except (ValueError, TypeError):
        return False


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _study_document(value, study, name, as_of, errors, *, step=False):
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("studyId") != study:
        errors.append(name + ":STUDY_ID_OR_SHAPE_MISMATCH")
        return None
    if step and (value.get("action") != name or not _timestamp_ok(value.get("attemptedAt"), as_of)):
        errors.append(name + ":STEP_ACTION_OR_TIME_INVALID")
        return None
    return value


def freshness(region, observed, as_of):
    expected = W.last_completed_session(region, as_of)
    if observed is None:
        return {"status": "UNKNOWN", "sourceDate": None, "expectedSession": expected,
                "observedSession": None, "reason": "NO_OBSERVATION"}
    result = W.freshness(region, observed, as_of)
    # Preserve the source date; a holiday label cannot become an ETF quotation.
    if result.get("observedSession") != observed:
        result.update(status="INVALID", reason="NON_SESSION_SOURCE_DATE")
    return {**result, "sourceDate": observed}


def _validated_rows(rows, module, kind, as_of, errors):
    if rows is None:
        return None
    try:
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("LEDGER_ROW_SHAPE")
            if kind == "receipts":
                module.validate_receipt(row, pathway=module.LIVE)
                execution = P.check_timing(signal_date=row["signalDate"], created_at_utc=row["createdAtUtc"],
                    now_utc=row["createdAtUtc"], merged_at_utc=row["authorization"]["mergedAtUtc"])
                if str(execution.date()) != row["executionDate"]:
                    raise ValueError("RECEIPT_EXECUTION_DATE_MISMATCH")
                key = row["signalDate"]
            else:
                module.validate_outcome(row, pathway=module.LIVE)
                key = (row["receiptSha256"], row["horizonSessions"])
            if key in seen or not _timestamp_ok(row.get("createdAtUtc"), as_of):
                raise ValueError("DUPLICATE_OR_FUTURE_RECORD")
            seen.add(key)
        if module is B and kind == "receipts":
            B.verify_chain(rows)
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        errors.append(f"{kind}:" + type(exc).__name__)
        return None
    return rows


def study_view(snapshot, study, as_of):
    prefix = f"ledger/research-strategies/{study}/"
    docs = {name: snapshot.read(prefix + name) for name in FILES}
    module, errors = STUDIES[study], []
    assessment = _study_document(docs["assessment.json"], study, "assessment", as_of, errors) or {}
    coverage = _study_document(docs["coverage.json"], study, "coverage", as_of, errors) or {}
    aggregate = _study_document(docs["publication-status.json"], study, "aggregate", as_of, errors) or {}
    steps = {}
    for name in STEPS:
        path = prefix + f"publication-status.{name}.json"
        candidate = docs[f"publication-status.{name}.json"]
        if snapshot.sources[path]["status"] == "MISSING":
            candidate = _mapping(aggregate.get("steps")).get(name)
        steps[name] = _study_document(candidate, study, name, as_of, errors, step=True)
    reported = _count(assessment.get("receipts")) if module is not B else _count(coverage.get("recordedSessions"))
    zero_basis = "COMMITTED_ASSESSMENT_OR_COVERAGE_ZERO"
    if reported is None and module is not B and _count(_mapping(steps["assess"]).get("receipts")) == 0:
        reported, zero_basis = 0, "COMMITTED_ASSESS_STEP_TOTAL_ZERO"
    receipts = _validated_rows(docs["receipts.jsonl"], module, "receipts", as_of, errors)
    if receipts is None and snapshot.sources[prefix + "receipts.jsonl"]["status"] == "MISSING" and reported == 0:
        receipts = []  # The committed assessment/coverage explicitly corroborates zero.
    count = len(receipts) if receipts is not None else None
    if reported is not None and count != reported:
        errors.append("RECEIPT_COUNT_NOT_CORROBORATED")
    latest = max(receipts, key=lambda r: r["signalDate"]) if receipts else None
    # A later outcomes/assess success must never be reported as a recorded signal.
    attempts = docs["attempts.jsonl"]
    valid_attempts = attempts
    try:
        for attempt in attempts or []:
            if (module is not B or not isinstance(attempt, dict) or attempt.get("studyId") != study
                    or attempt.get("evidence") is not False or not _timestamp_ok(attempt.get("attemptedAtUtc"), as_of)
                    or hashlib.sha256(P.canonical({k: v for k, v in attempt.items() if k != "rowSha256"})).hexdigest() != attempt.get("rowSha256")):
                raise ValueError("ATTEMPT_LOG_NOT_VERIFIED")
    except (ValueError, TypeError):
        errors.append("ATTEMPT_LOG_NOT_VERIFIED")
        valid_attempts = None
    outcomes, outcome_count = [], None
    if module is not B:
        outcomes = _validated_rows(docs["outcomes.jsonl"], module, "outcomes", as_of, errors)
        if outcomes is None and snapshot.sources[prefix + "outcomes.jsonl"]["status"] == "MISSING" and _count(assessment.get("outcomes")) == 0:
            outcomes = []
        try:
            by_digest = {r["receiptSha256"]: r for r in receipts or []}
            for row in outcomes or []:
                receipt = by_digest[row["receiptSha256"]]
                h = row["horizonSessions"]
                if (h not in receipt["horizonsSessions"] or row["executionDate"] != receipt["executionDate"]
                        or row["signalDate"] != receipt["signalDate"]
                        or row["maturitySession"] != str(P.maturity_session(receipt["executionDate"], h).date())
                        or not P.has_matured(receipt["executionDate"], h, as_of)):
                    raise ValueError("OUTCOME_NOT_LINKED_OR_MATURED")
            outcome_count = len(outcomes) if outcomes is not None else None
        except (ValueError, KeyError, TypeError):
            errors.append("OUTCOME_NOT_LINKED_OR_MATURED")
            outcomes = None
        if _count(assessment.get("outcomes")) is not None and outcome_count != assessment["outcomes"]:
            errors.append("OUTCOME_COUNT_NOT_CORROBORATED")
    pending_doc = _study_document(docs["outcome-pending.json"], study, "pending", as_of, errors) or {}
    pending = pending_doc.get("pending")
    return {"studyId": study, "evidenceClass": "PAPER_EXPERIMENT_NOT_INVESTMENT_APPROVAL",
            "recordedReceipts": count, "assessmentReportedReceipts": reported,
            "receiptCountBasis": "SERIALIZED_LEDGER_VALIDATION_NOT_SCIENTIFIC_APPROVAL" if docs["receipts.jsonl"] is not None and receipts is not None else
                                 zero_basis if count == 0 else "UNKNOWN",
            "attemptHistoryRows": len(valid_attempts) if valid_attempts is not None else None,
            "attemptLogPhysicalRows": len(attempts) if attempts is not None else None,
            "attemptReasons": [{k: a.get(k) for k in ("signalDate", "attemptedAtUtc", "status", "reason", "runId")} for a in valid_attempts or []],
            "latestRecordAttempt": steps["record"], "stepStatuses": steps,
            "aggregateStatus": aggregate.get("status"),
            "latestReceipt": {k: latest.get(k) for k in ("signalDate", "executionDate", "createdAtUtc", "receiptSha256", "universe", "source")} if latest else None,
            "paperBooks": {b: {k: v.get(k) for k in ("status", "eligibleNames", "excluded", "fallbackSlots")}
                           for b, v in (latest.get("books") or {}).items()} if latest else None,
            "eligibleCounts": {b: _count(v.get("eligibleNames")) for b, v in (latest.get("books") or {}).items()} if latest else None,
            "assessmentVerdicts": {b: _mapping(v).get("verdict") for b, v in _mapping(assessment.get("challengers")).items()} if assessment else None,
            "assessmentReadings": assessment.get("challengers"),
            "assessmentRiskPaths": assessment.get("riskPaths"),
            "maturedRecordedOutcomes": outcome_count,
            "outcomeRecords": [{k: r.get(k) for k in ("signalDate", "horizonSessions", "maturitySession", "status", "resolution", "books", "priceBasis")} for r in outcomes or []],
            "outcomeInterpretation": "CONTRACT_NOT_REGISTERED" if module is B else "PERSISTED_OUTCOMES_ONLY_NO_RECALCULATION",
            "pendingOutcomes": len(pending) if isinstance(pending, list) else None,
            "coverage": coverage or None, "errors": errors,
            "nextEvidence": "Authorized final-weekly receipt with actual source/eligibility proof, then registered matured outcomes and assessment; paper success is not investment admission"
                            if module is not B else "Record actual weekly state; register the eight open outcome decisions before any return study"}


def latest_completed_week_end(region, now):
    """The most recent week-end session already completed at `now`: the session a weekly decision in force is made for."""
    session = W.last_completed_session(region, now)
    for _ in range(12):
        if W.is_week_end_session(region, session):
            return session
        session = W.session_on_or_before(region, (W.pd.Timestamp(session) - W.pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    raise ValueError("NO_WEEK_END_SESSION_IN_LOOKBACK")


def stance(region, row, view, now, weekly_blocked, final=None):
    """What the stored weekly decision says to hold TODAY, shown only when every stored fact agrees.

    The stored decision is read, never recomputed. A weekly decision is made for a week-end session and stays in force until the
    next week-end session has completed, so Friday's decision is the current one on the following Monday-Thursday even though the
    session-freshness table calls its observation date STALE. Anything short of a digest-backed FINAL weekly decision for the
    latest completed week-end, created from fresh inputs and internally consistent (status, count, ETF weight, holdings), is
    UNKNOWN, never a guessed 0 or 100%. A stock selection is never displayed: this renderer has no investment-admission
    registry, so names and weights stay withheld.
    """
    unknown = lambda reason: {"displayed": False, "stockCount": None, "benchmarkWeightPct": None,  # noqa: E731
                              "holdings": None, "statusKo": None, "reason": reason}
    if weekly_blocked:
        return unknown("WEEKLY_PUBLICATION_BLOCKED")
    if (row.get("weekStatus") == "INTRA_WEEK_PREVIEW" and final is not None
            and isinstance(row.get("asOfDate"), str) and row["asOfDate"] > final.get("asOfDate", "")
            and _timestamp_ok(row.get("generatedAt"), now)):
        # A daily preview is not a replacement for the committed weekly target.
        row = final
    if not _timestamp_ok(row.get("generatedAt"), now):
        return unknown("POLICY_TIMESTAMP_MISSING_OR_AFTER_REPORT")
    status = row.get("status")
    if status not in W.DECISION_STATUSES:
        return unknown("POLICY_STATUS_UNRECOGNIZED")
    if row.get("weekStatus") != "FINAL_WEEKLY":
        return unknown("NOT_A_FINAL_WEEKLY_DECISION")
    if _mapping(row.get("freshness")).get("status") != "FRESH":
        return unknown("INPUTS_NOT_FRESH_WHEN_THE_DECISION_WAS_MADE")
    if row.get("asOfDate") != latest_completed_week_end(region, now):
        return unknown("NOT_THE_LATEST_COMPLETED_WEEK_END_DECISION")
    if not view["lastValidFinalSession"] or row.get("asOfDate") != view["lastValidFinalSession"]:
        return unknown("NO_DIGEST_VALID_FINAL_RECEIPT_FOR_THIS_DECISION")
    count, weight, holdings = row.get("stockCount"), row.get("benchmarkWeightPct"), row.get("holdings")
    if status == "PASSIVE_NO_DEFENSIBLE_EDGE":
        if (type(count) is int and count == 0 and holdings == [] and type(weight) in (int, float) and weight == 100
                and row.get("benchmark") == view["benchmark"]):
            keys = ("status", "stockCount", "holdings", "benchmarkWeightPct", "benchmark", "asOfDate", "inputs")
            if final is None or any(row.get(k) != final.get(k) for k in keys):
                return unknown("FINAL_RECEIPT_SUMMARY_MISMATCH")
            return {"displayed": True, "stockCount": 0, "benchmarkWeightPct": 100.0, "holdings": [],
                    "statusKo": row.get("statusKo"), "reason": "STORED_FINAL_DECISION_IS_THE_ETF_DEFAULT"}
        return unknown("PASSIVE_STATUS_FIELDS_INCONSISTENT")
    return unknown("STOCK_SELECTION_NOT_DISPLAYED_NO_INVESTMENT_ADMISSION_REGISTRY")


TRACKED = ("ETF_ONLY", "CURRENT_POLICY")


def _finite(value, *, positive=False):
    return (type(value) in (int, float) and value == value and abs(value) != float("inf")
            and (not positive or value > 0))


def tracked_path(snapshot, now):
    """Stored status of the prospective paper ledger (no orders): NAV against the regional ETF. Never recomputed.

    The prospective paper ledger is not an account and not a historical backtest; each is reported on its own line.
    """
    doc = snapshot.read(SHADOW)
    base = {"studyId": SH.STUDY, "evidenceClass": SH.EVIDENCE_CLASS, "realAccountPerformance": None,
            "rows": [], "researchScenarioCount": None, "errors": []}
    if doc is None:
        return {**base, "status": "NOT_STARTED_NO_STORED_STATUS", "atUtc": None}
    errors = []
    if (doc.get("schema") != "ENTRY_STATE_SHADOW_STATUS_V1" or doc.get("studyId") != SH.STUDY
            or doc.get("productionEffect") != "NONE"):
        errors.append("STATUS_IDENTITY_INVALID")
    if not _timestamp_ok(doc.get("atUtc"), now):
        errors.append("STATUS_TIMESTAMP_MISSING_OR_AFTER_REPORT")
    readout = _mapping(_mapping(doc.get("report")).get("readout"))
    if readout.get("evidenceClass") != SH.EVIDENCE_CLASS:
        errors.append("READOUT_EVIDENCE_CLASS_MISMATCH")
    if errors:
        return {**base, "status": "INVALID_STORED_STATUS", "atUtc": doc.get("atUtc"), "errors": errors}
    if doc.get("status") != "OK":
        return {**base, "status": "LAST_ATTEMPT_" + str(doc.get("status")), "atUtc": doc.get("atUtc"),
                "errors": [str(doc.get("reason"))] if doc.get("reason") else []}
    strategies = _mapping(readout.get("strategies"))
    rows = []
    for region in W.BENCHMARKS:
        for name in TRACKED + (("SEPARATE_COMPARISON:QQQ",) if region == "US" else ()):
            sid = f"{region}:{name}"
            item = _mapping(strategies.get(sid))
            if not item:
                rows.append({"strategyId": sid, "status": "NOT_IN_STORED_STATUS"})
                continue
            nav = item.get("nav") if _finite(item.get("nav"), positive=True) else None
            excess = item.get("excessVsEtfPct") if _finite(item.get("excessVsEtfPct")) else None
            invalid_dates = False
            if nav is not None:
                try:
                    nav_day = date.fromisoformat(item["navDate"])
                    if SH.session_final_utc(str(nav_day), region) > min(now, utc(doc["atUtc"])):
                        raise ValueError("NAV_SESSION_NOT_FINAL")
                    if W.session_on_or_before(region, str(nav_day)) != str(nav_day):
                        raise ValueError("NAV_DATE_NOT_A_SESSION")
                    if excess is not None:
                        base_day = date.fromisoformat(item["etfBaseDate"])
                        if base_day > nav_day or W.session_on_or_before(region, str(base_day)) != str(base_day):
                            raise ValueError("INVALID_ETF_BASE_DATE")
                except (ValueError, KeyError, TypeError):
                    invalid_dates = True
                    nav = excess = None
            else:
                excess = None
            rows.append({"strategyId": sid, "status": "READ", "fillState": item.get("fillState"),
                         "navDate": item.get("navDate") if nav is not None else None, "nav": nav,
                         "excessVsEtfPct": excess, "etfBaseDate": item.get("etfBaseDate") if excess is not None else None,
                         "fills": item.get("fills") if type(item.get("fills")) is int else None,
                         "chargedCostPctOfNav": item.get("chargedCostPctOfNav") if _finite(item.get("chargedCostPctOfNav")) else None,
                         "maturity": {h: _mapping(item.get("maturity")).get(h) for h in SH.HORIZONS}})
            if invalid_dates:
                rows[-1].update(status="INVALID_STORED_DATES", errors=["NAV_OR_ETF_DATE_NOT_VERIFIED"])
    scenarios = sum(1 for k in strategies if ":N" in k)
    return {**base, "status": "READ", "atUtc": doc.get("atUtc"), "rows": rows, "researchScenarioCount": scenarios}


def build(snapshot, *, as_of, code_identity):
    now = utc(as_of)
    if utc(snapshot.committed_at) > now:
        raise ValueError("SNAPSHOT_COMMITTED_AFTER_REPORT_AS_OF")
    state = snapshot.read(STATE) or {}
    weekly = snapshot.read(WEEKLY + "latest.json") or {}
    publication = snapshot.read(WEEKLY + "publication-status.json") or {}
    ledger = snapshot.read(WEEKLY + "receipts.jsonl")
    weekly_errors, valid_weekly = [], []
    for row in ledger or []:
        try:
            if W.receipt_digest(row) != row.get("digest") or W.receipt_session_error(row):
                raise ValueError("INVALID_WEEKLY_RECEIPT")
            if _timestamp_ok(row.get("generatedAt"), now):
                valid_weekly.append(row)
        except (ValueError, KeyError, TypeError):
            weekly_errors.append("INVALID_WEEKLY_RECEIPT")
    regions, finals = {}, {}
    for region, benchmark in W.BENCHMARKS.items():
        row = _mapping(_mapping(weekly.get("regions")).get(region))
        source = _mapping(row.get("inputs"))
        observed = _mapping(row.get("freshness")).get("sourceDate")
        watched = []
        if _timestamp_ok(row.get("generatedAt"), now) and not weekly.get("blocked"):
            for item in (row.get("watchlist") if isinstance(row.get("watchlist"), list) else [])[:W.WATCHLIST_SIZE]:
                if not isinstance(item, dict):
                    continue
                quote = _mapping(item.get("priceMomentum"))
                watched.append({"ticker": item.get("ticker"), "name": item.get("name"), "rank": item.get("rank"),
                                "quoteSession": quote.get("asOf"), "freshness": freshness(region, quote.get("asOf"), now),
                                "rejectionReasons": item.get("exclusionCodes"),
                                "class": "EXPLORATORY_WATCHLIST_NOT_RECOMMENDATION"})
        final = W.latest_final(valid_weekly, region)
        finals[region] = final
        regions[region] = {"benchmark": benchmark, "auxiliaryBenchmark": "QQQ" if region == "US" else None,
            "currency": W.CURRENCY[region], "defaultPolicy": "REGIONAL_ETF_IF_NO_ADMITTED_STOCK_SIGNAL",
            "operatingStockRange": [W.MIN_NAMES, W.MAX_NAMES], "newNominationsInThisReport": 0,
            "evidenceCertifiedCandidateCount": None, "certificationReason": "NO_INVESTMENT_ADMISSION_REGISTRY_IN_THESE_SOURCES",
            "persistedPolicyStatus": row.get("status"), "persistedWeekStatus": row.get("weekStatus"),
            "policyGeneratedAt": row.get("generatedAt"), "sourceTimestamp": source.get("siteGeneratedAt"),
            "sourceFetchTimestamp": None, "sourceProducerGitSha": source.get("buildCommitSha"),
            "sourceArtifactSha256": source.get("siteDataSha256"), "observedSession": observed,
            "freshnessAtReport": freshness(region, observed, now), "freshnessReportedAtCreation": row.get("freshness"),
            "benchmarkQuote": None, "benchmarkQuoteFreshness": "UNKNOWN_NO_ETF_QUOTE_IN_PERSISTED_SUMMARY",
            "lastValidFinalSession": final.get("asOfDate") if final else None,
            "exploratoryWatchlist": watched,
            "nextEvidence": "Source-valid dated inputs and independently admitted net benchmark-relative economic evidence; rank, internal weight, opportunity tier or paper PASS cannot substitute"}
    for region, view in regions.items():
        view["currentStance"] = stance(region, _mapping(_mapping(weekly.get("regions")).get(region)), view, now,
                                       bool(weekly.get("blocked")), finals[region])
    tracked = tracked_path(snapshot, now)
    studies = {s: study_view(snapshot, s, now) for s in STUDIES}
    report = {"schema": "READ_ONLY_DAILY_DECISION_REPORT_V1", "reportAsOfUtc": now.isoformat(),
        "reportGeneratedAt": now.isoformat(), "reportAsOfKst": now.astimezone(W.ZoneInfo("Asia/Seoul")).isoformat(),
        "codeIdentity": code_identity, "sourceCommitSha": snapshot.commit, "sourceCommitTimestamp": snapshot.committed_at,
        "marketContext": {"regime": state.get("macroRegime") if _timestamp_ok(state.get("generatedAt"), now) else None,
            "sourceGeneratedAt": state.get("generatedAt"), "observedSession": state.get("marketAsOf"),
            "sourceProducerGitSha": state.get("buildCommitSha"), "sourceFetchTimestamp": None,
            "productionValidationReported": (state.get("productionValidation") or {}).get("passed"),
            "meaning": "INTERNAL_CONTEXT_NOT_PREDICTIVE_OR_SCIENTIFIC_APPROVAL"},
        "regions": regions, "trackedPath": tracked, "paperStudies": studies, "weeklyPublication": publication,
        "weeklyLedgerErrors": weekly_errors,
        "inactiveD2": "Separate Track D v2 research objective N=0 to N>10; this renderer does not activate it or change operating 0–5 policy",
        "safety": {"readOnly": True, "historicalOutcomesExecuted": False, "productionEffect": "NONE",
                   "internalWeightsOrOpportunityTiersUsedAsApproval": False, "workflowSuccessIsStudySuccess": False},
        "sources": snapshot.sources}
    return redact_tree(report)


def redact_tree(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if re.fullmatch(r"(?i)(?:api[_-]?key|(?:access_|refresh_)?token|authorization|crtfc_key|secret|password)", str(k))
                else redact_tree(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_tree(v) for v in value]
    if isinstance(value, str):
        return re.sub(r"(?i)((?:api[_-]?key|token|authorization|crtfc_key)\s*[=:]\s*)(?:bearer\s+)?[^\s&,]+", r"\1[REDACTED]", value)
    return value


def _item(value):
    if value is None:
        return "UNKNOWN"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return "(" + _collection(value) + ")"
    return str(value)


def _collection(value):
    """Plain `a, b` / `k=v; k2=v2`. An empty list is an explicit none; None inside stays UNKNOWN."""
    if isinstance(value, dict):
        return "; ".join(f"{k}={_item(v)}" for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))) or "없음"
    return ", ".join(_item(v) for v in value) or "없음"


def text(value):
    if value is None:
        return "UNKNOWN"
    if isinstance(value, (dict, list)):
        value = _collection(value)
    value = redact_tree(str(value))
    return html.escape(value, quote=False).replace("\n", " ").replace("|", "&#124;").replace("`", "&#96;").replace("[", "&#91;").replace("]", "&#93;")


def _pct(value, digits=4):
    return "UNKNOWN" if value is None else f"{value:+.{digits}f}%"


def headline(report):
    """One line: what the stored weekly decision says to hold today, per region, or UNKNOWN with its reason.

    Built from the same `currentStance` the table below uses; it never shows a stock and never turns an unverified decision into 0 or 100%.
    """
    parts = []
    for region, v in report["regions"].items():
        c = v["currentStance"]
        if c["displayed"]:
            parts.append(f"{region} {c['stockCount']}종목 · {v['benchmark']} {c['benchmarkWeightPct']:.0f}%")
        else:
            parts.append(f"{region} UNKNOWN ({text(c['reason'])})")
    return "**오늘의 운영 판단** (저장된 최종 주간 판단 기준, 다음 주말 세션까지 유효): " + " / ".join(parts)


def render(report):
    """Pure Markdown: report metadata is explicit input, never the wall clock."""
    r = report
    lines = ["# Investment 일간 판단 브리프", "", f"보고 기준/생성: {text(r['reportAsOfKst'])}",
             f"원천 Git: `{r['sourceCommitSha']}` / 커밋 시각: {text(r['sourceCommitTimestamp'])}",
             f"렌더러 Git: {text(r['codeIdentity'].get('gitSha'))}", "", headline(r), "",
             "KR 069500.KS · US SPY 기본 / QQQ 보조. 운영은 지역별 0–5종목이며, 적격 신호가 없으면 기존 ETF 기본값을 유지합니다.",
             "이 보고서는 신규 종목을 지명하거나 비중을 계산하지 않습니다. 신호 인증 모집단은 UNKNOWN이며, 보고서의 신규 지명은 0입니다.",
             "내부 모델 비중·opportunity tier·탐색 순위·paper 성공은 투자 승인이나 검증된 알파가 아닙니다.", "",
             "## 보존된 시장 문맥", "",
             f"거시 표시: {text(r['marketContext']['regime'])} / 원천 생성: {text(r['marketContext']['sourceGeneratedAt'])} / 관측일: {text(r['marketContext']['observedSession'])}",
             f"원천 수집 시각: {text(r['marketContext']['sourceFetchTimestamp'])}; 산출물 검증 보고값: {text(r['marketContext']['productionValidationReported'])} (과학적 성공이 아님).", "",
             "독립적으로 인증된 시장위험·낙폭 증거: UNKNOWN (이 입력에는 별도 투자 적격 인증 원천이 없음). 내부 거시 표시를 위험관리 승인으로 쓰지 않습니다.", "",
             "## 운영 판단과 신선도", "",
             "| 지역 | 기본 / 보조 | 보존 정책 상태 | 관측 세션 | 지금 기대 완료 세션 | 지금 신선도 | ETF 시세 |",
             "|---|---|---|---|---|---|---|"]
    for region, v in r["regions"].items():
        f = v["freshnessAtReport"]
        lines.append("|" + "|".join(text(x) for x in (region, v["benchmark"] + (" / QQQ" if region == "US" else ""), v["persistedPolicyStatus"], v["observedSession"], f["expectedSession"], f["status"], v["benchmarkQuote"])) + "|")
    for region, v in r["regions"].items():
        lines += ["", f"{region}: 정책 생성 {text(v['policyGeneratedAt'])}; 입력 산출물 시각 {text(v['sourceTimestamp'])}; 수집 시각 {text(v['sourceFetchTimestamp'])}; 생산 Git {text(v['sourceProducerGitSha'])}.",
                  f"주간 상태 {text(v['persistedWeekStatus'])}; 마지막 유효 FINAL {text(v['lastValidFinalSession'])}. 저장 당시 FRESH와 현재 신선도는 별개이며, 지수 날짜를 ETF 시세 날짜로 쓰지 않습니다."]
    publication = r["weeklyPublication"]
    lines += ["", f"최신 주간 게시 시도: {text(publication.get('status'))}, {text(publication.get('attemptedAt'))}; 오류 {text(publication.get('errors'))}; 이월 {text(publication.get('deferredRegions'))}."]
    lines += ["", "## 현재 운영 판단 — 저장된 최종 주간 판단 기준", "",
              "| 지역 | 보유 종목 수 | ETF 비중 | 보유 종목 | 근거 |", "|---|---|---|---|---|"]
    for region, v in r["regions"].items():
        c = v["currentStance"]
        if c["displayed"]:
            etf = f"{v['benchmark']} {c['benchmarkWeightPct']:.0f}%" + (" (QQQ는 보조 비교만)" if region == "US" else "")
            lines.append("|" + "|".join(text(x) for x in (region, f"{c['stockCount']}개", etf, c["holdings"], c["reason"])) + "|")
        else:
            lines.append("|" + "|".join(text(x) for x in (region, None, None, None, c["reason"])) + "|")
    lines += ["", "현재 운영 정책(weekly-passive-first-v1)은 지역별 0–5종목을 허용하며 0개이면 ETF 100%입니다. 이 범위는 기존 정책의 설명이지 연구 목표의 종목 수 상한이나 목표가 아닙니다(별도 D v2 연구는 0개부터 10개 초과까지를 다룹니다). 표는 digest가 확인된 FINAL 주간 판단이 가장 최근에 완료된 주말 세션의 판단이고 저장된 필드끼리 일치할 때만 채웁니다. 주간 판단은 다음 주말 세션이 끝날 때까지 유효합니다. "
              "그 밖에는 UNKNOWN이며 0개나 100%로 바꿔 쓰지 않습니다. 종목이 선정돼도 이 보고서에는 이름·비중을 표시하지 않습니다(투자 승인 레지스트리가 없음).", ""]
    t = r["trackedPath"]
    lines += ["## ETF 대비 성과 — 세 가지를 합치지 않고 따로 읽음", "",
              "1. **검증된 실제 계좌 성과: 없음.** 주문·체결·계좌 기록이 이 입력에 없습니다. UNKNOWN은 0%가 아닙니다.",
              f"2. **전향 paper 경로** ({text(t['evidenceClass'])}, 주문 없음, 아직 검증 아님): 저장 상태 {text(t['status'])}; 저장 시각 {text(t['atUtc'])}.",
              "3. **과거 탐색 백테스트**(HISTORICAL_DEVELOPMENT, 결과 노출 후 재현): 이 표에 합산하지 않습니다. 연구 결과는 `docs/daily-decision-report.md`의 \u201c연구 결과 읽기\u201d에 적힌 별도 명령으로 따로 읽습니다.", ""]
    if t["status"] == "READ":
        lines += ["| 경로 | 체결 상태 | NAV 기준일 | NAV | ETF 대비 초과 (ETF 기준일) | 체결 수 | 누적 비용 | H126 | H252 |", "|---|---|---|---|---|---|---|---|---|"]
        for row in t["rows"]:
            if row["status"] != "READ":
                lines.append("|" + "|".join(text(x) for x in (row["strategyId"], row["status"], None, None, None, None, None, None, None)) + "|")
                continue
            nav = None if row["nav"] is None else f"{row['nav']:.6f}"
            excess = f"{_pct(row['excessVsEtfPct'])} ({text(row['etfBaseDate'])})" if row["excessVsEtfPct"] is not None else None
            cost = None if row["chargedCostPctOfNav"] is None else f"{row['chargedCostPctOfNav']:.4f}%"
            lines.append("|" + "|".join(text(x) for x in (row["strategyId"], row["fillState"], row["navDate"], nav, excess, row["fills"], cost,
                                                           row["maturity"].get("H126"), row["maturity"].get("H252"))) + "|")
        lines += ["", f"연구용 시나리오 {text(t['researchScenarioCount'])}개는 성과 표에서 제외합니다. 초과 수익은 각 경로가 시작한 세션의 ETF 기준 NAV 비율이며 검증된 알파가 아닙니다. "
                  "H126/H252 PENDING은 0% 수익이 아니라 아직 만기되지 않았다는 뜻입니다."]
    else:
        lines += ["전향 paper 경로의 NAV 행이 없거나 읽을 수 없어 ETF 대비 성과는 **UNKNOWN**입니다(0%가 아님). 오류: " + text(t["errors"])]
    lines += ["", "## 탐색 관찰 목록 — 투자 적격 아님", "", "|지역|티커|보존 순위|시세 세션|지금 신선도|편입 제외 사유|", "|---|---|---|---|---|---|"]
    for region, v in r["regions"].items():
        for item in v["exploratoryWatchlist"]:
            lines.append("|" + "|".join(text(x) for x in (region, item["ticker"], item["rank"], item["quoteSession"], item["freshness"]["status"], item["rejectionReasons"])) + "|")
    lines += ["", "## Paper 연구 — 기록·건너뜀·평가를 따로 읽음", ""]
    for study, v in r["paperStudies"].items():
        attempt = v["latestRecordAttempt"] or {}
        protocol = _mapping(r["codeIdentity"].get("registeredStudies")).get(study)
        lines += [f"### {study}", "", f"- 기록 영수증: {text(v['recordedReceipts'])} ({text(v['receiptCountBasis'])}); 전체 시도 이력 수: {text(v['attemptHistoryRows'])}.",
                  f"- 최신 기록 단계: {text(attempt.get('status'))} / {text(attempt.get('reason'))}; 시도 시각 {text(attempt.get('attemptedAt'))}; run {text(attempt.get('runId'))}.",
                  f"- 집계 상태: {text(v['aggregateStatus'])}; 실제 적격 수: {text(v['eligibleCounts'])}; 최신 영수증: {text(v['latestReceipt'])}.",
                  f"- Paper 장부 상태/제외/ETF fallback 슬롯: {text(v['paperBooks'])}.",
                  f"- 평가: {text(v['assessmentVerdicts'])}; 만기된 저장 outcome: {text(v['maturedRecordedOutcomes'])}; 대기: {text(v['pendingOutcomes'])}; 위험 경로: {text(v['assessmentRiskPaths'])}.",
                  f"- 저장된 평가 근거(재평가 없음): {text(v['assessmentReadings'])}; 열린 결과 결정: {text(_mapping(v['stepStatuses'].get('outcomes')).get('openDecisions'))}.",
                  f"- 단계별 상태: {text({s: d.get('status') if d else None for s, d in v['stepStatuses'].items()})}; 결과 계약: {text(v['outcomeInterpretation'])}.",
                  f"- 기존 만기 결과(재계산 없음): {text(v['outcomeRecords'])}; 오류: {text(v['errors'])}.",
                  f"- 다음 증거: {text(v['nextEvidence'])}.", ""]
        protocol = _mapping(protocol)
        lines += [f"- 등록 하한 {text(protocol.get('firstEligibleFloor'))}; 최소 적격 이름 {text(protocol.get('minimumEligibleNames'))}; 본 평가 영수증 {text(protocol.get('primaryReceiptCohort'))}; 지평 {text(protocol.get('horizons'))}; 원 명세 SHA256 {text(protocol.get('sha256'))}.", ""]
    lines += ["## 이 보고서와 연구 보고서의 경계", "",
              "- **매일 보는 것**은 이 문서입니다: 오늘의 운영 판단, 신선도, 검증 상태, 전향 paper 경로의 ETF 대비 성과.",
              "- **연구 근거**(한국·미국 종목 알파, 시장 위험관리, 산업 알파)는 과거 탐색 결과이며 이 문서의 판단에 들어가지 않습니다. "
              "`docs/daily-decision-report.md`의 \u201c연구 결과 읽기\u201d에 적힌 별도 명령으로 따로 읽습니다.",
              "- 어느 쪽도 종목 추천·배분 변경·모델 승격의 근거가 아닙니다.", ""]
    lines += ["## 다음 적격 관문과 별도 D v2", "",
              "원천의 날짜·PIT·거래 가능성·권리·비용/총수익을 입증하고, 등록된 전향 평가와 독립 검토를 거쳐야 투자 적격을 주장할 수 있습니다. UNKNOWN은 0% 수익이나 적격 0명으로 바뀌지 않습니다.",
              r["inactiveD2"], "주간 게시·워크플로 성공은 연구 성공이 아닙니다. 이번 보고서는 저장된 결과만 읽으며 기록·평가·성과 실행·배분 변경을 하지 않습니다.", "",
              "<details><summary>원천별 Git 경로·읽기 상태·SHA256</summary>", "", "|경로|읽기 상태|SHA256|", "|---|---|---|"]
    for path, source in sorted(r["sources"].items()):
        lines.append(f"|[{path}]({source['url']})|{text(source['status'])}|{text(source['sha256'])}|")
    lines += ["", "</details>"]
    return "\n".join(lines) + "\n"
