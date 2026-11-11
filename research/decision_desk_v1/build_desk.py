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


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import ledger as L  # noqa: E402

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


def dry_run(region: str) -> list[dict]:
    rows = L.read(L.DRY_RUN_DIR / "ledger.jsonl")
    L.verify_chain(rows)
    out = []
    for r in rows:
        if r.get("schema") != L.SCHEMA or r["region"] != region:
            continue
        item = {"type": "RESEARCH_ALLOCATION_AS_OF", "id": f"decision-desk-v1 {r['path']} {r['cohort']}", "path": r["path"],
                "signalAsOf": r["signalAsOf"], "informationCutoff": r["informationCutoff"], "generatedAt": r["generatedAt"],
                "publishedAt": r["publishedAt"], "executionAt": r["plannedExecution"], "weights": r["weights"],
                "selectedTickers": r["selectedTickers"], "status": r["status"], "digest": r["digest"],
                "benchmark": r["benchmark"], "modelVersion": r["modelVersion"]}
        if r["path"] == "B2":
            th = r["investmentThesis"]
            item["b2"] = {"market": {"label": th["market"]["label"], "interpretation": th["market"]["interpretation"]},
                          "macro": {"label": th["macro"]["label"], "interpretation": th["macro"]["interpretation"]},
                          "picks": [{k: p[k] for k in ("ticker", "name", "reasons", "thesis6m", "thesis12m", "catalysts", "risks",
                                                        "notVerified", "whyVersusBenchmark", "researchWeight")}
                                    | {"layers": {k: v["label"] for k, v in p["layers"].items()},
                                       "invalidationConditions": r["invalidationConditions"][p["ticker"]]} for p in th["picks"]],
                          "reviewedRejected": th["reviewedRejected"], "gatedOutCount": len(th["gatedOut"]),
                          "zeroSelectionReason": th["zeroSelectionReason"], "knowledgeLimit": th["knowledgeLimit"]}
        out.append(item)
    return out


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
            "Production 판단: 069500.KS 100%. 알파 순위의 수익 정렬이 확인되지 않았다(rank IC t 0.68).",
            "ML v1 141개: 검증된 ETF 초과성과 없음. v2 정정에서 주식 후보 3개는 기업행동 원천이 막혀 SOURCE_BLOCKED.",
            "산업모멘텀 우위는 리밸런싱 위상에 의존한다(네 위상 ETF 격차 −9.40~+2.58%p).",
            "S2 가치·확인은 비용 2배 시 +0.04%p, 2025년 제외 시 +0.0015%p. 연구 후보이며 승격 불가.",
            "2026-11-06 기준 KOSPI는 252일 고점 대비 −44%, 63일 −20%, 변동성 47%로 급락 국면이다.",
        ],
        "limits": [
            "과거 154개 기업행동이 미복구라 주식 전략 전체 CAGR이 미인증이다.",
            "069500 일간 이상수익(2026-07-31 +24.17%)의 경제적 설명이 미해결이다.",
            "현재 후보의 재무값은 현재 스냅샷이다. 전향 기록에서는 판단 시점 값이지만, 과거 재현값은 아니다.",
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
        ],
    },
}

APPROVALS = [
    {"item": "#321 CI/Pages 복구 일반 merge 및 정상 Pages 배포", "owner": "Owner", "why": "threadpoolctl 3.8.0 충돌로 main·모든 연구 PR CI가 실패 중이다. 이 데스크의 실제 게시도 Pages 정상화 이후에야 가능하다."},
    {"item": "decision-desk-v1 전향 원장 활성화(dry-run → signal-history 기록)", "owner": "Owner", "why": "승인 전에는 research/decision_desk_v1/dry-run/ 에만 기록한다."},
    {"item": "월간 B2 리뷰 작성 담당과 시각", "owner": "Owner", "why": "매월 첫 FINAL_WEEKLY 후 실행 전까지 AI 리뷰를 작성해야 전향 기록으로 인정된다."},
    {"item": "US 개별주 유료 원천(Norgate/Sharadar) 구매 여부", "owner": "Owner", "why": "라이선스(구독 종료 시 삭제 의무)와 원본 보관 규칙의 충돌을 먼저 확인해야 한다."},
    {"item": "KR 018880·005930 공식 기업행동 패키지", "owner": "원천 담당 + 외부 회계 reviewer", "why": "#333 G의 우선순위 1·2. v2 주식 경제성 인증의 선행 조건이다."},
]


def build() -> dict:
    desk = {"schema": "DECISION_DESK_V1", "builtFrom": PINS, "publicationTypes": sorted(TYPES),
            "staleAfterDays": 10, "disclaimerKo": "연구·가상 판단입니다. 실제 자금 운용 승인이 없으며 production 비중을 바꾸지 않습니다.",
            "regions": {}, "history": history(), "approvalsNeeded": APPROVALS,
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
