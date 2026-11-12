"""Compile research/decision_desk_v1/desk.json — the read-only publication the site renders.

Every item is labelled with one of the four publication types fixed by the #333 audit:
  HISTORICAL_EXPLORATORY | CORRECTED_CASH_SCOPE | SOURCE_BLOCKED | RESEARCH_ALLOCATION_AS_OF
plus PRODUCTION_RECEIPT for the production weekly decision copied by digest. Sources are
read from git objects at pinned commits (signal-history and unmerged PR heads) and each
carries its commit, path and blob id. Nothing here recomputes a strategy or a return.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import ledger as L  # noqa: E402

EF = ROOT / "research" / "evidence_first_v2"

PINS = {
    "signalHistory": "6398e94feddd4f552910d31b36bc8db0766576af",
    "pr329": "0a1f494171576af6928fe531145a8c8f050253fd",
    "pr332": "0f39c2fef93a9cf924f45ae87662de41090f2528",
    "pr331": "49c3aa891b1e85520c2a90d0d062678a738a87cf",
    "pr333": "61d0d3f6",
}
TYPES = {"HISTORICAL_EXPLORATORY", "CORRECTED_CASH_SCOPE", "SOURCE_BLOCKED", "RESEARCH_ALLOCATION_AS_OF", "PRODUCTION_RECEIPT"}


def git(commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)


def ref(commit: str, path: str, pr: int | None = None) -> dict:
    blob = subprocess.check_output(["git", "rev-parse", f"{commit}:{path}"], cwd=ROOT, text=True).strip()
    return {"commit": commit, "path": path, "blob": blob, "pr": pr}


def pct(x, d=2):
    return None if x is None or x == "" else round(float(x) * 100, d)


# ----------------------------------------------------------------------------- current decisions
def production(region: str) -> dict:
    sh = PINS["signalHistory"]
    latest = json.loads(git(sh, "ledger/weekly-decisions/latest.json"))
    r = latest["regions"][region]
    return {"type": "PRODUCTION_RECEIPT", "policy": r["policyVersion"], "receiptId": r["receiptId"], "digest": r["digest"],
            "asOfDate": r["asOfDate"], "weekStatus": r["weekStatus"], "generatedAt": r["generatedAt"],
            "status": r["status"], "statusKo": r["statusKo"], "weights": r["weights"], "stockCount": r["stockCount"],
            "noTradeReason": r["noTradeReason"], "calibrationOrdering": r["calibrationOrdering"],
            "freshness": r["freshness"], "costs": r["costs"],
            "watchlist": [{"ticker": w["ticker"], "name": w["name"], "alphaPercentile": w["alphaPercentile"],
                           "exclusionReasonsKo": w.get("exclusionReasonsKo", [])} for w in r.get("watchlist", [])[:5]],
            "source": ref(sh, "ledger/weekly-decisions/latest.json")}


def research_ledgers(region: str) -> list[dict]:
    sh = PINS["signalHistory"]
    out = []
    champ_path = "ledger/research-strategies/current-champion-decisions-v1/latest.json"
    champ = json.loads(git(sh, champ_path))["regions"][region]
    out.append({"type": "SOURCE_BLOCKED" if champ["status"] == "BLOCKED" else "RESEARCH_ALLOCATION_AS_OF",
                "id": "current-champion-decisions-v1 (C1/C2)", "signalAsOf": champ["asOfDate"], "status": champ["status"],
                "reasonCodes": champ.get("reasonCodes", []), "weights": None, "source": ref(sh, champ_path),
                "evidenceClass": champ["evidenceClass"]})
    if region == "KR":
        for sid in ("kr-selection-challenger-v1", "kr-selection-challenger-v2-accounting"):
            path = f"ledger/research-strategies/{sid}/receipts.jsonl"
            rows = [json.loads(x) for x in git(sh, path).decode().splitlines() if x.strip()]
            last = rows[-1]
            status = json.loads(git(sh, f"ledger/research-strategies/{sid}/publication-status.json"))
            books = {}
            for b, v in last["books"].items():
                books[b] = {"tickers": [s["ticker"] for s in v.get("slots", [])], "slotFraction": v.get("slotFraction"),
                            "status": v.get("status"), "eligibleNames": v.get("eligibleNames")}
            out.append({"type": "RESEARCH_ALLOCATION_AS_OF", "id": sid, "signalAsOf": last["signalDate"],
                        "informationCutoff": last["signalDate"], "generatedAt": last["createdAtUtc"],
                        "executionAt": last["executionDate"], "publishedAt": "signal-history commit (see source)",
                        "receiptSha256": last["receiptSha256"], "evidenceClass": last["evidenceClass"], "books": books,
                        "verdicts": status["steps"]["assess"].get("verdicts"), "outcomes": status["steps"]["outcomes"]["status"],
                        "receipts": len(rows), "residual": "069500.KS", "source": ref(sh, path)})
    return out


def us_cocktail_latest() -> dict:
    path = "research/us_macro_cocktail_v1/results/result.json"
    d = json.loads(git(PINS["pr331"], path))["latestAllocation"]
    return {"type": "HISTORICAL_EXPLORATORY", "id": "us-macro-cocktail-v1 latest allocation",
            "signalAsOf": d["decision"], "executionAt": d["execution"], "generatedAt": "2026-11-10 (after execution)",
            "currentRecommendation": False,
            "reason": "Generated after its own execution date; a historical reconstruction, not a prospective receipt (#333).",
            "weights": {k: v["weights"] for k, v in d["weights"].items()}, "source": ref(PINS["pr331"], path, 331)}


def horizon_ends(region: str, execution: str) -> dict:
    """Exact exit sessions from the exchange calendar (None if beyond the calendar's known holidays)."""
    import availability as A
    cal = A.calendar(region)
    sessions = [str(pd.Timestamp(x).date()) for x in cal.sessions_in_range(execution, cal.last_session)]
    return {f"h{h}": (sessions[h] if len(sessions) > h else None) for h in (126, 252)}


def dry_run(region: str) -> list[dict]:
    rows = L.read(L.DRY_RUN_DIR / "ledger.jsonl")
    L.verify_chain(rows)
    notes = [a for a in rows if a.get("schema") == L.ANNOTATION_SCHEMA]
    excl = L.primary_exclusions(rows)
    outs = [o for o in rows if o.get("schema") == L.OUTCOME_SCHEMA]
    out = []
    for r in rows:
        if r.get("schema") not in L.RECORD_SCHEMAS or r["region"] != region:
            continue
        reviewer = r.get("reviewer") if r["schema"] == L.SCHEMA_V2 else ("claude" if r["path"] == "B2" else None)
        arm = r["path"] + (f":{reviewer}" if r["path"] == "BX" else "")
        item = {"type": "RESEARCH_ALLOCATION_AS_OF", "id": f"decision-desk-v1 {arm} {r['cohort']}", "path": arm,
                "v3Path": EFC.v3_path(r), "v3PathLabel": EFC.V3_PATHS[EFC.v3_path(r)],
                "primaryExclusionReasons": excl[r["digest"]],
                "reviewer": reviewer, "cohort": r["cohort"], "schemaVersion": 2 if r["schema"] == L.SCHEMA_V2 else 1,
                "signalAsOf": r["signalAsOf"], "informationCutoff": r["informationCutoff"], "generatedAt": r["generatedAt"],
                "publishedAt": r["publishedAt"], "executionAt": r["plannedExecution"], "weights": r["weights"],
                "selectedTickers": r["selectedTickers"], "status": r["status"], "digest": r["digest"],
                "benchmark": r["benchmark"], "modelVersion": r["modelVersion"],
                "horizonEnd": horizon_ends(region, r["plannedExecution"]),
                "annotations": [{"category": a["category"], "detail": a["detail"]} for a in notes if r["digest"] in a["recordDigests"]],
                "outcomes": [{k: o.get(k) for k in ("horizon", "status", "horizonEndSession", "returnAfterCostPct",
                                                    "excessAfterCostPct", "missingDataReason")}
                             for o in outs if o["recordDigest"] == r["digest"]]}
        if r["path"] in ("B2", "BX"):
            th = r["investmentThesis"]
            item["b2"] = {"market": {"label": th["market"]["label"], "interpretation": th["market"]["interpretation"]},
                          "macro": {"label": th["macro"]["label"], "interpretation": th["macro"]["interpretation"]},
                          "picks": [{k: p[k] for k in ("ticker", "name", "reasons", "thesis6m", "thesis12m", "catalysts", "risks",
                                                        "notVerified", "whyVersusBenchmark", "researchWeight")}
                                    | {"layers": {k: v["label"] for k, v in p["layers"].items()},
                                       "invalidationConditions": r["invalidationConditions"][p["ticker"]]} for p in th["picks"]],
                          "reviewedRejected": th["reviewedRejected"],
                          "gatedOutCount": th.get("gatedOutCount", len(th.get("gatedOut", []))),
                          "zeroSelectionReason": th["zeroSelectionReason"], "knowledgeLimit": th["knowledgeLimit"]}
        out.append(item)
    return out


def pipeline() -> dict:
    import desk as DK
    reg = json.loads((HERE / "reviewers.json").read_text())
    return {"cohorts": [DK.cohort_status(m) for m in DK.all_cohorts()],
            "next": {"cohort": "2026-12", "trigger": "first FINAL_WEEKLY production receipt with asOfDate in 2026-12 (expected 2026-12-04)",
                     "protocol": "protocol-v2.json", "status": "AWAITING_PACKET"},
            "reviewers": [{k: r[k] for k in ("id", "role", "provider", "invocation", "status")} for r in reg["reviewers"]],
            "automation": reg["automation"]}


# ----------------------------------------------------------------------------- evidence-first v2
def _ef_load():
    if str(EF) not in sys.path:
        sys.path.insert(0, str(EF))
    import contract
    return contract


EFC = _ef_load()


def _efj(name: str) -> dict:
    return json.loads((EF / name).read_text())


def _efsha(name: str) -> str:
    return hashlib.sha256((EF / name).read_bytes()).hexdigest()


def evidence_first() -> dict:
    """Read-only copy of research/evidence_first_v2 results; each file is referenced by SHA-256."""
    matrix = _efj("evidence-grades.json")
    graded = EFC.validate_grades(matrix)
    grades = [{"id": it["id"], "region": it["region"], "label": it["label"], "path": it["path"],
               "grade": graded[it["id"]]["grade"], "blocks": graded[it["id"]]["blocks"], "track": graded[it["id"]]["track"],
               "prospectiveBlocks": it.get("prospectiveBlocks"), "blockScope": it.get("blockScope"),
               "decisionEligible": graded[it["id"]]["decisionEligible"], "decisionUse": it["decisionUse"],
               "criteria": [{"level": lvl, "met": c.get("met"), "ref": c.get("ref")} for lvl, c in it.get("criteria", {}).items()]}
              for it in matrix["items"]]
    lit = _efj("literature.json")
    census = _efj("results/census.json")
    ap = _efj("results/academic-path.json")
    dos = _efj("results/b3-dossiers.json")
    for d in dos["dossiers"]:
        EFC.validate_dossier(d, d["nominatingEvidence"]["grade"],
                             {r["ticker"]: r for r in census["regions"][d["region"]]["b1"]["topQuintile"]})
    integ = _efj("results/data-integrity.json")
    branch = lambda name: "FACTOR_REFERENCE" if name.startswith("5") else ("B1" if name[0] in "678" else "MAIN")  # noqa: E731
    funnel = {}
    for g, reg in census["regions"].items():
        pc = reg["productionComparison"]
        funnel[g] = {"asOf": reg["asOf"], "universeSource": reg["universeSource"],
                     "stages": [dict(st, branch=branch(st["stage"])) for st in reg["funnel"]],
                     "b1Rule": reg["b1"]["rule"], "b1TopQuintile": reg["b1"]["topQuintile"], "deepReview": reg["b1"]["deepReview"],
                     "factorTopQuintile": reg["factorTopQuintile"],
                     "productionComparison": {"receipt": pc["productionReceipt"], "both": pc["both"], "onlyB1": pc["onlyB1"],
                                              "onlyProduction": pc["onlyProduction"], "note": pc["note"]}}
    keep = ("full", "prePublication", "postPublication", "postPublicationEx2025", "ourEra")
    academic = {"verdict": ap["verdict"], "latestMonth": ap["latestMonth"], "gradeEffect": ap["gradeEffect"],
                "significantAtBonferroni": ap["significantAtBonferroni"],
                "protocolSha256": ap["protocolSha256"], "dataManifestSha256": ap["dataManifestSha256"],
                "portfolios": {k: {w: {m: v[w][m] for m in ("first", "last", "months", "annualExcessPct", "hacT",
                                                            "annualExcessAfterDragPct", "maxRelativeDrawdownPct")}
                                       | {"excess12mSharePositive": v[w]["excess12m"]["sharePositive"]}
                                       for w in keep if w in v}
                               for k, v in ap["portfolios"].items()}}
    integrity = {"definitions": integ["definitions"], "regions": {}}
    for g, r in integ["regions"].items():
        per = r["periods"]
        integrity["regions"][g] = {
            "dropSides": {k: r["dropSides"][k] for k in ("byReason", "bySide", "method")},
            "periods": {k: per[k] for k in ("freshnessRule", "factorRows", "rowsMixingReportPeriods", "rowsUsingSameDayFiling",
                                            "publicationLagDays", "ageDays")},
            "shareCounts": {"rule": r["shareCounts"]["rule"], "affects": r["shareCounts"]["affects"],
                            "flagged": r["shareCounts"]["flagged"]},
            "opmRule": r["opmRule"], "membershipSnapshot": r["membershipSnapshot"],
            "b1v2": {k: r["b1v2DryRun"][k] for k in ("stage3Survivors", "noCompleteFiling", "eligible", "ageDays", "top5", "rankingComparison")}}
    proto = _efj("prospective-protocol-v1.json")
    dry = _efj("results/prospective-dry-run.json")
    prospective = {"protocolSha256": dry["protocolSha256"], "status": proto["status"], "tracks": proto["tracks"],
                   "cohort": proto["cohort"], "arms": {k: {x: v[x] for x in ("v3Path", "track", "rule") if x in v} for k, v in proto["arms"].items()},
                   "b1Steps": proto["arms"]["B1_ROE"]["steps"], "portfolio": proto["portfolio"], "costs": proto["costs"],
                   "returns": proto["returns"], "comparison": proto["comparison"], "activation": dry["activation"],
                   "activationRequires": proto["activation"]["requires"], "dryRun": dry["regions"], "dryRunLabel": dry["label"],
                   "gates": [{k: g.get(k) for k in ("id", "status", "blocks", "detail", "test")} for g in L.ACTIVATION_GATES]}
    return {"schema": "EVIDENCE_FIRST_V2", "levels": matrix["levels"], "rule": matrix["rule"], "tracks": matrix["tracks"], "grades": grades,
            "integrity": integrity, "prospective": prospective,
            "v3Paths": EFC.V3_PATHS, "legacyToV3": EFC.LEGACY_TO_V3,
            "literature": {"sourcePolicy": lit["sourcePolicy"], "timeSeriesVsCrossSection": lit["timeSeriesVsCrossSection"],
                           "studies": lit["studies"]},
            "funnel": funnel, "survivorshipStatement": census["survivorshipStatement"], "academic": academic,
            "dossiers": {k: dos[k] for k in ("path", "role", "author", "knowledgeLimit", "concentrationNote", "regionDecision", "dossiers")},
            "sources": {n: _efsha(n) for n in ("evidence-grades.json", "literature.json", "results/census.json",
                                               "results/academic-path.json", "results/b3-dossiers.json",
                                               "academic-path-protocol.json", "results/data-integrity.json",
                                               "prospective-protocol-v1.json", "results/prospective-dry-run.json")}}


# ----------------------------------------------------------------------------- history table
def history() -> list[dict]:
    rows = []
    # ML v1 / v2 (#332 comparison, which preserves v1 numbers and the corrected v2 scope)
    cpath = "research/ml_strategy_tournament_v2/comparison.csv"
    for r in csv.DictReader(io.StringIO(git(PINS["pr332"], cpath).decode())):
        if r["version"] == "v1_REPORTED":
            t, label = "HISTORICAL_EXPLORATORY", "ML 토너먼트 v1 (원 보고값)"
        elif r["version"] == "A_VERIFIED_CASH" and r["status"] == "COMPLETE":
            t, label = "CORRECTED_CASH_SCOPE", "ML 토너먼트 v2 정정 (공식 ETF 회계)"
        elif r["status"].startswith("SOURCE_BLOCKED"):
            t, label = "SOURCE_BLOCKED", f"ML 토너먼트 v2 {r['version']}"
        else:
            continue
        rows.append({"region": "KR", "type": t, "study": label, "strategy": r["strategy"], "status": r["status"],
                     "period": "2016-01-11~2026-09-14", "cagrPct": pct(r["cagr"]), "excessVsEtfPp": pct(r["excessCagr"]),
                     "sharpe": round(float(r["sharpe"]), 3) if r["sharpe"] else None, "mddPct": pct(r["mdd"]),
                     "costBasis": "토너먼트 config 비용(매수·매도·세금) 적용", "benchmark": "069500.KS 교정 총수익",
                     "source": ref(PINS["pr332"], cpath, 332)})
    # KR adaptive cocktail (#329)
    apath = "research/adaptive_cocktail_v1/results/results.json"
    a = json.loads(git(PINS["pr329"], apath))
    w = a["window"]
    for k, m in a["performance"].items():
        rows.append({"region": "KR", "type": "HISTORICAL_EXPLORATORY", "study": "KR Adaptive Cocktail v1", "strategy": k,
                     "status": a["evidenceClass"], "period": f"{w['start']}~{w['end']}", "cagrPct": pct(m["cagr"]),
                     "excessVsEtfPp": pct(m["excessCagr"]), "sharpe": round(m["sharpe"], 3), "mddPct": pct(m["mdd"]),
                     "costBasis": "config 비용, 위상0 (위상 의존: #333 네 위상 ETF 격차 −9.40~+2.58%p)",
                     "benchmark": "069500.KS", "source": ref(PINS["pr329"], apath, 329)})
    # US macro cocktail (#331) primary + extended USD
    upath = "research/us_macro_cocktail_v1/results/result.json"
    u = json.loads(git(PINS["pr331"], upath))
    for win, wd in u["windows"].items():
        for k, s in wd["strategies"].items():
            m = s["USD"]
            rows.append({"region": "US", "type": "HISTORICAL_EXPLORATORY", "study": f"US Macro/Multi-Asset ({'주' if win == 'primary' else '확장'} 기간)",
                         "strategy": k, "status": "EXPLORATORY_ON_PUBLICLY_KNOWN_US_HISTORY",
                         "period": f"{m['start']}~{m['end']}", "cagrPct": m["cagrPct"], "excessVsEtfPp": None,
                         "sharpe": m["sharpeOverBil"], "mddPct": m["maxDrawdownPct"],
                         "costBasis": f"매수 10bp·매도 13bp, 연 회전 {s['turnoverTwoWayPerYear']:.2f}배",
                         "benchmark": "SPY (USD); KRW 환산은 errata v1 정의만 유효",
                         "source": ref(PINS["pr331"], upath, 331)})
    return rows


# ----------------------------------------------------------------------------- desk
FACTS = {
    "KR": {
        "known": [
            "Production 판단: 069500.KS 100%. 알파 순위가 수익 순서를 맞힌다는 근거가 없다(rank IC t 0.68).",
            "ML v1 141개: 검증된 ETF 초과성과 없음. v2 정정에서 주식 후보 3개는 기업행동 원천이 막혀 SOURCE_BLOCKED.",
            "산업모멘텀 우위는 리밸런싱 위상에 의존한다(네 위상 ETF 격차 −9.40~+2.58%p).",
            "S2 가치·확인은 비용 2배 시 +0.04%p, 2025년 제외 시 +0.0015%p. 연구 후보이며 승격 불가.",
            "2026-11-06 기준 KOSPI는 252일 고점 대비 −44%, 63일 −20%, 변동성 47%로 급락 국면이다.",
        ],
        "limits": [
            "과거 154개 기업행동이 미복구라 주식 전략 전체 CAGR이 미인증이다.",
            "069500 일간 이상수익(2026-07-31 +24.17%)의 경제적 설명이 미해결이다.",
            "현재 후보의 재무값은 현재 스냅샷이다. 전향 기록에서는 판단 시점 값이지만, 과거 재현값은 아니다.",
            "2026-11 B2는 정보 마감 뒤 공표된 H.10 환율·H.15 금리·VIX·미국 11-06 종가를 읽었다. PIT_CONTAMINATED로 표시하고 주 비교에서 제외한다(기록 원본 보존).",
        ],
    },
    "US": {
        "known": [
            "Production 판단: SPY 100%. 알파 정렬 미확인(rank IC t 0.17). QQQ는 별도 비교 기준이다.",
            "동적 ETF 배분 6종은 비용 차감 후 정적 S4를 이기지 못했다(주 기간 −0.98~−3.37%p).",
            "추세 규칙의 낙폭 방어는 동일위험 대조에서도 2008년 한 사건에서만 남았다. 2016년 이후는 열위(errata E4).",
            "KRW 'no-look-ahead' 환산 주장은 철회됐다(H.10 공표 시점). USD 결과는 그대로다.",
        ],
        "limits": [
            "S&P500 퇴출 324개 중 212개는 가격이 없다. 개별주 과거 성과는 계산하지 않는다(TRACK B 차단).",
            "IEF/TLT/SHY/BIL/GLD/UUP는 단일 공급자(Yahoo)이고, 2차 공급자는 접속 불가.",
            "B2의 TRV 선택은 AI 정성판단이다. 확률·목표수익을 산출하지 않으며 검증된 예측이 아니다.",
            "2026-11 B2 근거 문장의 'VIX 28'은 마감 15분 뒤 공표된 값이다(마감 시점 공개값은 16.61). PIT_CONTAMINATED로 주 비교에서 제외한다.",
        ],
    },
}

APPROVALS = [
    {"item": "1. #321 정확한 HEAD의 일반 merge (squash 금지) 및 main CI·Pages 정상 배포 확인", "owner": "Owner",
     "why": "threadpoolctl 3.8.0 충돌로 main과 모든 연구 PR의 Tests가 실패한다. #321은 production state-publisher 변경을 포함하므로 그 운영 영향까지 승인 범위에 들어간다(#335)."},
    {"item": "2. main을 #334에 병합(이력 보존) → 결합 원격 CI 통과 → #334 읽기 전용 화면 게시 승인", "owner": "Owner",
     "why": "게시는 화면뿐이다. 연구 원장 writer·evaluator·BX 비교군은 이 승인으로 켜지지 않는다."},
    {"item": "3. 전향 가상 비교(prospective-v1) 기록 활성화와 월간 운영 담당", "owner": "Owner",
     "why": "owner-approvals/prospective-v1.json에 protocol SHA-256을 적어 커밋해야 한다. 담당자는 매달 마감 전에 공개 관측(verify-publication)과 AI 리뷰를 수행한다. 남은 관문 G1·G2는 기존 B2 경로에만 걸리고 전향 가상 비교에는 걸리지 않는다."},
]


def build() -> dict:
    desk = {"schema": "DECISION_DESK_V1", "builtFrom": PINS, "publicationTypes": sorted(TYPES),
            "staleAfterDays": 10, "disclaimerKo": "연구·가상 판단입니다. 실제 자금 운용 승인이 없으며 production 비중을 바꾸지 않습니다.",
            "regions": {}, "history": history(), "approvalsNeeded": APPROVALS, "pipeline": pipeline(),
            "evidenceFirst": evidence_first(),
            "protocolSha256": hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()}
    for region in ("KR", "US"):
        reg = {"production": production(region), "research": research_ledgers(region), "deskRecords": dry_run(region),
               "facts": FACTS[region]}
        if region == "US":
            reg["historicalAllocations"] = [us_cocktail_latest()]
            reg["singleStockEligibility"] = {"type": "SOURCE_BLOCKED", "departed": 324, "departedNoPrice": 212,
                                             "admittedSessions": 0, "source": "research/us_macro_cocktail_v1/results/track-b-reaudit.json (PR #331)"}
        desk["regions"][region] = reg
    return desk


if __name__ == "__main__":
    import validate_desk as V
    d = build()
    V.validate(d)
    out = HERE / "desk.json"
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(out, hashlib.sha256(out.read_bytes()).hexdigest(), len(d["history"]), "history rows")
