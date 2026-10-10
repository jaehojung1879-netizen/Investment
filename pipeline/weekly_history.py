"""Historical-evidence adapter for the weekly decision pages.

Reads already-produced, committed result files and turns them into a compact
block the site can draw. It computes no new outcome. Every row keeps its own
evidence class, period, benchmark definition and caveats, and rows from
different studies are never merged into one number: they differ in horizon,
universe, period, costs and fallback asset.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from .config import REPO_ROOT

REPLAY_RESULT = REPO_ROOT / "docs" / "results" / "weekly-passive-first-v1-replay.json"
INTEGRATED_AUDIT = REPO_ROOT / "docs" / "results" / "kr-integrated-alpha-portfolio-v1-postoutcome-completed-audit.json"
BENCHMARK_RECON = REPO_ROOT / "docs" / "audits" / "kr-alpha-atlas-phase-c-integrity" / "benchmark-reconciliation.json"
BENCHMARK_RECON_CORRECTED = (REPO_ROOT / "docs" / "audits" / "kr-alpha-atlas-phase-c-integrity"
                             / "benchmark-reconciliation-corrected.json")

PATH_LABELS_KO = {
    "P0": "지수 100% 보유",
    "P1": "주간 판단 규칙(weekly-passive-first-v1)",
    "C1": "기존 CHAMPION 선택기(잔여 현금)",
    "C2": "기존 CHAMPION 선택기(잔여 지수)",
}
SUMMARY_KEYS = (
    "startDate", "endDate", "years", "blocks", "initialCapitalKrw", "finalValueKrw",
    "cumulativeGrossReturnPct", "cumulativeNetReturnPct", "cagrPct", "grossCagrPct",
    "benchmarkCagrPct", "excessCagrPp", "arithmeticActiveReturnPpPerYear",
    "geometricMinusArithmeticPp", "annualizedCostDragPct", "maxDrawdownPct",
    "annualizedVolatilityPct", "annualizedDownsideVolatilityPct", "oneWayTurnoverPerYear",
    "nameTrades", "averageNamesHeld", "zeroNameBlockSharePct", "averageBenchmarkWeightPct",
    "calendarYearReturnPct", "excessByCalendarYearPp", "halves", "topContributions",
)


def _load(path: Path):
    try:
        raw = path.read_bytes()
        if path.suffix == ".gz":
            raw = gzip.decompress(raw)
        return json.loads(raw)
    except (OSError, ValueError):
        return None


def _thin(points: list, limit: int = 260) -> list:
    """Keep at most ``limit`` evenly spaced points plus the last one."""
    if len(points) <= limit:
        return points
    step = len(points) / limit
    picked = [points[int(i * step)] for i in range(limit)]
    if picked[-1] != points[-1]:
        picked.append(points[-1])
    return picked


def benchmark_definition_gap() -> dict:
    """replay-v16 069500.KS annual return minus Phase C's reconciled gross ETF return."""
    old, new = _load(BENCHMARK_RECON), _load(BENCHMARK_RECON_CORRECTED)
    if not old or not new:
        return {"available": False}
    corrected = {r["year"]: r.get("internalReturn") for r in new.get("annualComparisons") or []}
    rows = []
    for r in old.get("annualComparisons") or []:
        a, b = r.get("internalReturn"), corrected.get(r["year"])
        if a is None or b is None:
            continue
        rows.append({"year": r["year"], "replayV16Pct": round(a * 100, 2),
                     "reconciledPct": round(b * 100, 2), "gapPp": round((a - b) * 100, 2)})
    return {"available": bool(rows), "rows": rows,
            "minGapPp": min((r["gapPp"] for r in rows), default=None),
            "maxGapPp": max((r["gapPp"] for r in rows), default=None),
            "noteKo": ("과거 재현(replay-v16)의 KODEX 200 수익률은 Phase C가 공식 시세·분배금으로 대조한 "
                       "총수익률보다 매년 높았습니다. 같은 가격 레시피를 쓰는 재현 경로끼리의 비교는 내부적으로 "
                       "일관되지만, 절대 수익률 수준은 과대일 수 있습니다.")}


def replay_block(report: dict | None, regions=("KR",)) -> dict:
    if not report:
        return {"available": False, "reason": "REPLAY_RESULT_NOT_COMMITTED"}
    out = {"available": True, "id": report.get("id"), "evidenceClass": report.get("evidenceClass"),
           "promotionEligible": False, "liveValidated": False,
           "specSha256": report.get("specSha256"), "through": report.get("through"),
           "cadence": (report.get("calendar") or {}).get("cadence"),
           "candidatePool": report.get("candidatePool"), "regions": {}}
    for region in regions:
        blob = (report.get("regions") or {}).get(region)
        if not blob:
            continue
        paths = {}
        for key, summary in (blob.get("paths") or {}).items():
            if not summary.get("available"):
                paths[key] = {"available": False, "status": summary.get("status"),
                              "failureCount": summary.get("failureCount"),
                              "labelKo": PATH_LABELS_KO.get(key, key)}
                continue
            paths[key] = {"available": True, "labelKo": PATH_LABELS_KO.get(key, key),
                          **{k: summary.get(k) for k in SUMMARY_KEYS if k in summary}}
        out["regions"][region] = {
            "benchmark": blob.get("benchmark"), "status": blob.get("status"),
            "headlineEligible": bool(blob.get("headlineEligible")),
            "benchmarkDefinition": blob.get("benchmarkDefinition"),
            "baseCurrency": blob.get("baseCurrency"),
            "fxReturnsIncluded": blob.get("fxReturnsIncluded"),
            "anchorsWithOrderingEstablished": blob.get("anchorsWithOrderingEstablished"),
            "anchorsWithStocks": blob.get("anchorsWithStocks"),
            "blocks": len(blob.get("decisions") or []),
            "paths": paths,
            "nav": {k: _thin(v) for k, v in (blob.get("weeklyNav") or {}).items()},
            "recentDecisions": (blob.get("decisions") or [])[-12:],
        }
    return out


def integrated_block(audit: dict | None) -> dict:
    """kr-integrated-alpha-portfolio-v1, as its own formal result reported it."""
    if not audit:
        return {"available": False}
    formal = audit.get("formalReported") or {}
    summaries = formal.get("summaries") or {}
    passive = formal.get("passive") or {}

    def row(key, label):
        s = summaries.get(key) or {}
        return {"key": key, "labelKo": label,
                "cagrPct": round(s["netAnnualizedReturn"] * 100, 2) if s.get("netAnnualizedReturn") is not None else None,
                "excessCagrPp": round(s["excessAnnualizedVsPassive"] * 100, 2)
                if s.get("excessAnnualizedVsPassive") is not None else None,
                "maxDrawdownPct": round(s["maxDrawdown"] * 100, 2) if s.get("maxDrawdown") is not None else None,
                "oneWayTurnoverPerYear": round(s["annualizedOneWayTurnover"], 2)
                if s.get("annualizedOneWayTurnover") is not None else None,
                "costDragPct": round(s["annualizedCostDrag"] * 100, 2) if s.get("annualizedCostDrag") is not None else None,
                "startDate": s.get("firstDate"), "endDate": s.get("lastDate")}
    return {
        "available": True, "study": "kr-integrated-alpha-portfolio-v1",
        "evidenceClass": "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY",
        "formalDecision": formal.get("finalArchitecture"),
        "rows": [row("A", "종목만(A)"), row("D", "산업+종목(D)")],
        "passiveCagrPct": round(passive["annualizedReturn"] * 100, 2) if passive.get("annualizedReturn") is not None else None,
        "passiveMaxDrawdownPct": round(passive["maxDrawdown"] * 100, 2) if passive.get("maxDrawdown") is not None else None,
        "caveatsKo": [
            "2017–2026 개발 평가(결과 노출)이며 D의 우위는 2025–2026과 전기전자 산업에 집중됐습니다.",
            "이 연구의 069500.KS 시계열은 외부 대조가 끝나지 않은 축적 지수였습니다(BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED).",
            "사후에 가장 좋아 보이는 구조를 고르는 근거로 쓰지 않습니다.",
        ],
    }


PHASE_C = {
    "study": "kr-alpha-atlas Phase C/D",
    "evidenceClass": "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY",
    "candidatesTested": 38, "readings": 73, "nominations": 0, "level4": "NOT_TRIGGERED",
    "resultSha256": "13775cc0d919a5934662b7caa8874af730987a8b8200250f03f47b9c3e4a6964",
    "summaryKo": ("38개 후보·73개 변수-기간 평가에서 보정 후 독립적 종목선택 알파 0개. "
                  "비용 반영 포트폴리오 백테스트(Level 4)는 진행되지 않았습니다."),
}


def build_history(regions=("KR",)) -> dict:
    return {
        "replay": replay_block(_load(REPLAY_RESULT), regions),
        "existingStudies": {"integratedAlphaPortfolio": integrated_block(_load(INTEGRATED_AUDIT)),
                            "phaseC": PHASE_C},
        "benchmarkDefinitionGap": benchmark_definition_gap(),
        "separationKo": ("각 결과는 기간·유니버스·비용·대체자산 정의가 달라 하나의 수치로 합치지 않습니다. "
                         "과거 성과가 가장 좋았던 방식을 사전에 알 수 있었던 것처럼 표시하지 않습니다."),
    }
