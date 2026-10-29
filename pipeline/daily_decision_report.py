"""Read-only daily presentation of committed observations; never a selector or assessor.

Only the named persisted sources are read. No fetcher, recorder, outcome builder,
optimizer or promotion path is called. Unknown measurements stay None.
"""
from __future__ import annotations

from datetime import datetime, timezone
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

ROOT = Path(__file__).resolve().parents[1]
STUDIES = {V1.STUDY: V1, V2.STUDY: V2, B.STUDY: B}
STATE = "state/latest.json"
WEEKLY = "ledger/weekly-decisions/"
STEPS = ("record", "outcomes", "assess", "coverage", "hook")
FILES = ("receipts.jsonl", "outcomes.jsonl", "attempts.jsonl", "assessment.json", "coverage.json",
         "outcome-pending.json", "publication-status.json", *(f"publication-status.{s}.json" for s in STEPS))
ALLOWED = {STATE, *(WEEKLY + n for n in ("latest.json", "publication-status.json", "receipts.jsonl")),
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
            raise ValueError("LOCAL_GIT_SNAPSHOT_UNAVAILABLE")
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
    regions = {}
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
    studies = {s: study_view(snapshot, s, now) for s in STUDIES}
    report = {"schema": "READ_ONLY_DAILY_DECISION_REPORT_V1", "reportAsOfUtc": now.isoformat(),
        "reportGeneratedAt": now.isoformat(), "reportAsOfKst": now.astimezone(W.ZoneInfo("Asia/Seoul")).isoformat(),
        "codeIdentity": code_identity, "sourceCommitSha": snapshot.commit, "sourceCommitTimestamp": snapshot.committed_at,
        "marketContext": {"regime": state.get("macroRegime") if _timestamp_ok(state.get("generatedAt"), now) else None,
            "sourceGeneratedAt": state.get("generatedAt"), "observedSession": state.get("marketAsOf"),
            "sourceProducerGitSha": state.get("buildCommitSha"), "sourceFetchTimestamp": None,
            "productionValidationReported": (state.get("productionValidation") or {}).get("passed"),
            "meaning": "INTERNAL_CONTEXT_NOT_PREDICTIVE_OR_SCIENTIFIC_APPROVAL"},
        "regions": regions, "paperStudies": studies, "weeklyPublication": publication,
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


def text(value):
    if value is None:
        return "UNKNOWN"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    value = redact_tree(str(value))
    return html.escape(value).replace("\n", " ").replace("|", "&#124;").replace("`", "&#96;").replace("[", "&#91;").replace("]", "&#93;")


def render(report):
    """Pure Markdown: report metadata is explicit input, never the wall clock."""
    r = report
    lines = ["# Investment 일간 판단 브리프", "", f"보고 기준/생성: {text(r['reportAsOfKst'])}",
             f"원천 Git: `{r['sourceCommitSha']}` / 커밋 시각: {text(r['sourceCommitTimestamp'])}",
             f"렌더러 Git: {text(r['codeIdentity'].get('gitSha'))}", "",
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
    lines += ["## 다음 적격 관문과 별도 D v2", "",
              "원천의 날짜·PIT·거래 가능성·권리·비용/총수익을 입증하고, 등록된 전향 평가와 독립 검토를 거쳐야 투자 적격을 주장할 수 있습니다. UNKNOWN은 0% 수익이나 적격 0명으로 바뀌지 않습니다.",
              r["inactiveD2"], "주간 게시·워크플로 성공은 연구 성공이 아닙니다. 이번 보고서는 저장된 결과만 읽으며 기록·평가·성과 실행·배분 변경을 하지 않습니다.", "",
              "<details><summary>원천별 Git 경로·읽기 상태·SHA256</summary>", "", "|경로|읽기 상태|SHA256|", "|---|---|---|"]
    for path, source in sorted(r["sources"].items()):
        lines.append(f"|[{path}]({source['url']})|{text(source['status'])}|{text(source['sha256'])}|")
    lines += ["", "</details>"]
    return "\n".join(lines) + "\n"
