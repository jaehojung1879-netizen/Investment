#!/usr/bin/env python3
"""us-tiingo-price-recovery-pilot-v1: preview (default) | --check-connectivity | --run | --build-plan.

GitHub Codespaces (browser) or any Linux/macOS shell, from the repository root:

    python3 scripts/run_us_tiingo_recovery_pilot.py --check-connectivity     # no token, no data, nothing written
    python3 scripts/run_us_tiingo_recovery_pilot.py --run                    # asks for the token without echoing it

Windows: `py -3 scripts\\run_us_tiingo_recovery_pilot.py --run`.

Tiingo's Terms of Use 1.6(a) forbid a Starter account from keeping Tiingo Data in any persistent storage, logs or backups and 1.6(c)
extend that to Derived Products. So --run keeps every provider answer in this process's memory only and never writes one; it writes
exactly one file, the CONNECTION record (calls, authentication accepted, rate limited, stops), which names no security and carries
no Tiingo Data. Everything computed from the answers is discarded when the process ends unless the owner passes
--retention-authorization with Tiingo's written permission for derived aggregates; --show-transient-summary prints the counts to
the terminal only. The token comes from TIINGO_API_TOKEN or a hidden prompt, travels only in the Authorization header and is never
written. Data stays NOT_ADMITTED whatever happens.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import us_tiingo_recovery_pilot as P  # noqa: E402

RECOVERY = "docs/us-readiness/us-departed-public-price-recovery-v1.json"
EVIDENCE_PILOT = "docs/us-readiness/us-price-evidence-pilot-v1.json"


# ---- environment -----------------------------------------------------------------------------------------------------------------
def read_token(environ=os.environ, prompt=getpass.getpass):
    token = (environ.get("TIINGO_API_TOKEN") or environ.get("TIINGO_API_KEY") or "").strip()
    if not token:
        token = (prompt("Tiingo API token (input hidden): ") or "").strip()
    if not token or any(c.isspace() for c in token):
        raise P.Refused("NO_USABLE_TIINGO_TOKEN")
    return token


def sec_user_agent(environ=os.environ):
    """SEC asks automated clients to identify a contact. Uses SEC_USER_AGENT, else this checkout's own git user.email."""
    if environ.get("SEC_USER_AGENT"):
        return environ["SEC_USER_AGENT"]
    try:
        email = subprocess.run(["git", "config", "user.email"], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        email = ""
    return f"Investment us-tiingo-price-recovery-pilot-v1 {email}" if "@" in email else None


def urllib_fetch(method, url, headers, body, timeout):
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read(max(P.MAX_BYTES.values()) + 1)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers or {}), error.read(1 << 20)
    except urllib.error.URLError as error:  # proxy CONNECT refusal, DNS, TLS: the request never reached the provider
        raise P.NetworkBlocked(f"{type(error.reason).__name__}: {error.reason}") from None


# ---- the committed plan --------------------------------------------------------------------------------------------------------
def build_plan():
    """Repository-side, before any request: needs pandas/exchange_calendars (the owner's run does not)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("audit_departed", ROOT / "scripts/audit_us_departed_public_prices.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    from pipeline import replay_calendar as RC
    _, snapshots, _, missing = audit.inputs()
    calendar = [str(d.date()) for d in RC.sessions(audit.START, audit.END, "US")]
    expected, _ = audit.expected_members(snapshots, calendar, missing)
    inventory = json.loads((ROOT / RECOVERY).read_text())["inventory"]
    prior = {s["ticker"]: s["filingCiksCandidateOnly"] for s in json.loads((ROOT / EVIDENCE_PILOT).read_text())["securities"]}
    provenance = {RECOVERY: P.digest((ROOT / RECOVERY).read_bytes()), EVIDENCE_PILOT: P.digest((ROOT / EVIDENCE_PILOT).read_bytes()),
                  audit.MEMBERSHIP: P.digest((ROOT / audit.MEMBERSHIP).read_bytes()), audit.AUDIT: P.digest((ROOT / audit.AUDIT).read_bytes()),
                  "window": [audit.START, audit.END]}
    return P.build_plan(inventory, expected, calendar, prior, provenance)


def load_plan():
    plan = json.loads((ROOT / P.PLAN_PATH).read_text())
    if plan["studyId"] != P.STUDY or len(plan["identities"]) != 20:
        raise P.Refused("NOT_THE_REGISTERED_PLAN")
    return plan


# ---- outputs -------------------------------------------------------------------------------------------------------------------
def render_markdown(report):
    q = report["questions"]
    lines = ["# Tiingo 가격 복구 파일럿 v1 — 실행 보고서", "",
             f"- 실제 Tiingo 응답: **{report['liveProviderResponse']}** · 판정: **{q['7_decision']}** · 모든 식별자 **{report['admission']}**",
             f"- 실행: {report['run'].get('startedAtUtc')} · plan SHA `{report['planSha256'][:16]}…` · 호출 {report['calls']}",
             f"- 중단된 출처: {report['stoppedSources'] or '없음'}", "",
             "| 질문 | 값 |", "|---|---|",
             f"| 1. 가격 응답이 있는 종목 (20개 중) | {q['1_identitiesWithTiingoPriceRows']} |",
             f"| 2. 기존 결손 대비 추가 확보 가능 세션 | {q['2_newlyRecoverableSessionsVsExistingMissing']['lower']}–{q['2_newlyRecoverableSessionsVsExistingMissing']['upper']} "
             f"(기존 결손 {q['2_newlyRecoverableSessionsVsExistingMissing']['existingMissingSessionsInPilot']}, 2024년 이후 {q['2_newlyRecoverableSessionsVsExistingMissing']['sessionsFrom2024AmongCounted']}) |",
             f"| 3. 독립 신원 확인 / Tiingo만 / HOLD / 무응답 | {q['3_identity']['independentlyCorroborated']} / {q['3_identity']['tiingoOnlyUnresolved']} / {q['3_identity']['hold']} / {q['3_identity']['noTiingoResponse']} |",
             f"| 4. 기업행동 lineage 미해결 / 종결대가 미해결 | {q['4_unresolved']['corporateActionLineageUnresolved']} / {q['4_unresolved']['terminalConsiderationInsideMembership']} |",
             f"| 5. 기존 후보(PARTIAL·FULL) 중 Tiingo 행·배당분할 필드 | {q['5_valueForExisting175']['partialOrFullWithTiingoRows']} · {q['5_valueForExisting175']['withDividendOrSplitFields']} (설명 안 되는 조정 단계 {q['5_valueForExisting175']['adjustmentStepsUnexplained']}) |",
             f"| 6. Tiingo 호출 / 212개 확대 시 예상 호출 | {q['6_costBenefit']['tiingoCallsUsed']} / {q['6_costBenefit']['tiingoCallsFor212AtTwoPerIdentity']} (무료 한도 {q['6_costBenefit']['freeTierLimits']}) |",
             "", "## 식별자별 (수·날짜만)", "", "| ID | 층 | 가격 응답 | 신원 | 창 안 세션 | 추가 확보 범위 | 배당/분할 | 종결 |", "|---|---|---|---|---:|---|---|---|"]
    for i in report["identities"]:
        s = i["sessions"]
        lines.append(f"| {i['auditIdentifier']} | {i['stratum']} | {i['tiingoPriceResponse']} | {i['identity']['state']} | {s['tiingoSessionsInWindow']}/{s['expectedSessions']} | "
                     f"{s['newlyRecoverableBounds'][0]}–{s['newlyRecoverableBounds'][1]} | {s['dividendEventsInWindow']}/{s['splitEventsInWindow']} | {i['terminal']} |")
    lines += ["", "## 사전 고정 판정 규칙", "", report["decisionRule"], "", "## 편입 전 검증 목록", ""]
    lines += [f"- {c}" for c in q["8_preAdmissionChecklist"]]
    lines += ["", "## Tiingo가 부족할 때 다음 검토 대상", "", "| 측정 결과 | 먼저 검토 | 이유 |", "|---|---|---|"]
    lines += [f"| {r['ifMeasured']} | {r['reviewFirst']} | {r['why']} |" for r in report["nextSourceDecisionTable"]]
    lines += ["", *[f"- {s}" for s in report["statements"]], ""]
    return "\n".join(lines)


def write_json(path, document, token):
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if token and token in text:
        raise P.Refused("TOKEN_WOULD_BE_WRITTEN")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def transient_summary(report):
    """Printed to the terminal, never written. 1.6(c): the owner should not copy it into a file, chat or note."""
    q = report["questions"]
    return {"retentionClass": "TRANSIENT_DISPLAY_ONLY_DO_NOT_SAVE", "decision": q["7_decision"],
            "identitiesWithTiingoPriceRows": q["1_identitiesWithTiingoPriceRows"],
            "newlyRecoverableSessions": [q["2_newlyRecoverableSessionsVsExistingMissing"]["lower"], q["2_newlyRecoverableSessionsVsExistingMissing"]["upper"]],
            "identity": q["3_identity"]}


def preview(plan):
    requests = [{"source": "tiingoMedia", "url": P.TIINGO_SUPPORTED_TICKERS}]
    for e in plan["identities"]:
        requests += [{"source": "tiingo", "url": P.tiingo_meta_url(e["auditIdentifier"])},
                     {"source": "tiingo", "url": P.tiingo_prices_url(e["auditIdentifier"], e["expectedPricingWindow"]["first"], e["expectedPricingWindow"]["last"])}]
    return {"mode": "PREVIEW_NO_REQUEST_MADE", "identities": [(e["auditIdentifier"], e["stratum"], e["pilotDisposition"]) for e in plan["identities"]],
            "tiingoRequests": len([r for r in requests if r["source"] == "tiingo"]), "firstRequests": requests[:3],
            "alsoRequested": ["SEC cik-lookup-data.txt + submissions for candidate CIKs (contact User-Agent from git user.email)",
                              "OpenFIGI ticker mapping (2 requests, no key)"],
            "budgets": P.BUDGET, "pacingSeconds": P.PACING_SECONDS, "licence": P.LICENCE,
            "writes": {"always": P.ACCESS_JSON, "onlyWithRetentionAuthorization": [P.REPORT_JSON, P.REPORT_MD], "never": "any provider response"},
            "token": "TIINGO_API_TOKEN or a hidden prompt; never written", "next": "--check-connectivity first, then --run"}


def main(argv=None, *, fetch=urllib_fetch, environ=os.environ, prompt=getpass.getpass, sleep=time.sleep, clock=time.time):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="store_true", help="make the requests (default: preview only)")
    parser.add_argument("--check-connectivity", action="store_true", help="one unauthenticated request per host; no token, no data, no file")
    parser.add_argument("--show-transient-summary", action="store_true", help="print the derived counts to the terminal only (never written)")
    parser.add_argument("--retention-authorization", type=Path, help="Tiingo's written permission to keep derived aggregates (JSON)")
    parser.add_argument("--existing-session-table", type=Path, help="#243 private session table, for exact new-session counts")
    parser.add_argument("--force", action="store_true", help="replace existing output files")
    parser.add_argument("--build-plan", action="store_true", help="repository maintenance: rebuild the committed plan")
    parser.add_argument("--report-root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.build_plan:
        text = json.dumps(build_plan(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
        (ROOT / P.PLAN_PATH).write_text(text, encoding="utf-8")
        print(P.digest(text.encode()))
        return 0
    plan = load_plan()
    if args.check_connectivity:
        session = P.Session(fetch, sleep=sleep, clock=clock)
        print(json.dumps({"mode": "CONNECTIVITY_ONLY_NO_TOKEN_NO_DATA_NOTHING_WRITTEN", "hosts": P.check_connectivity(session)}, indent=2))
        return 0
    if not args.run:
        print(json.dumps(preview(plan), indent=2))
        return 0

    # Everything that can refuse is decided before the first request, so a refusal never spends a provider call.
    authorization = None
    if args.retention_authorization:
        authorization = P.validate_retention_authorization(json.loads(args.retention_authorization.read_text(encoding="utf-8")))
    outputs = [args.report_root / P.ACCESS_JSON] + ([args.report_root / P.REPORT_JSON, args.report_root / P.REPORT_MD] if authorization else [])
    for path in outputs:
        if path.exists() and not args.force:
            raise P.Refused("OUTPUT_EXISTS_USE_FORCE_TO_REPLACE: " + str(path))
    existing = P.load_existing_table(args.existing_session_table) if args.existing_session_table else None
    token = read_token(environ, prompt)

    started = time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime(clock()))
    session = P.Session(fetch, token=token, sec_user_agent=sec_user_agent(environ), sleep=sleep, clock=clock)
    run_meta = {"startedAtUtc": started, "planSha256": P.digest(P.canonical(plan)),
                "secContactUserAgent": "PRESENT" if session.sec_user_agent else "ABSENT_SEC_NOT_RUN",
                "derivedRetention": "AUTHORIZED_IN_WRITING" if authorization else "NOT_AUTHORIZED_DISCARDED_AT_EXIT"}
    answers = P.acquire(plan, session)                     # in memory only
    report = P.analyze(plan, answers, session.records, session.stopped, existing_table=existing, run_meta=run_meta)
    write_json(args.report_root / P.ACCESS_JSON, P.access_summary(plan, session.records, session.stopped, run_meta), token)
    if authorization:
        report["retentionAuthorization"] = authorization
        P.scan_report(report)
        markdown = render_markdown(report)
        if token in markdown:
            raise P.Refused("TOKEN_WOULD_BE_WRITTEN")
        write_json(args.report_root / P.REPORT_JSON, report, token)
        (args.report_root / P.REPORT_MD).write_text(markdown, encoding="utf-8")
    out = {"access": P.ACCESS_JSON, "liveProviderResponse": report["liveProviderResponse"], "stoppedSources": session.stopped,
           "derived": "WRITTEN_UNDER_AUTHORIZATION" if authorization else "DISCARDED_NOT_WRITTEN_STARTER_TOS_1_6"}
    if args.show_transient_summary:
        out["transient"] = transient_summary(report)
    print(json.dumps(out, indent=2))
    del answers, report                                     # nothing outlives the process
    blocked = {"ACCESS_BLOCKED_BEFORE_PROVIDER", "AUTH_REJECTED", "ACCESS_FORBIDDEN"}
    return 2 if session.stopped.get("tiingo") in blocked else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except P.Refused as refused:
        print("REFUSED: " + str(refused), file=sys.stderr)
        raise SystemExit(3) from None
