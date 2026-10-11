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
import math
from pathlib import Path

from .config import REPO_ROOT

REPLAY_RESULT = REPO_ROOT / "docs" / "weekly-decision" / "weekly-passive-first-v1-replay.json"
INTEGRATED_AUDIT = REPO_ROOT / "docs" / "results" / "kr-integrated-alpha-portfolio-v1-postoutcome-completed-audit.json"
US_READINESS = REPO_ROOT / "docs" / "us-readiness" / "us-source-readiness-v1.json"
US_LOCAL = REPO_ROOT / "docs" / "us-readiness" / "weekly-passive-first-v1-us-local-currency.json"
BENCHMARK_RECON = REPO_ROOT / "docs" / "audits" / "kr-alpha-atlas-phase-c-integrity" / "benchmark-reconciliation.json"
BENCHMARK_RECON_CORRECTED = (REPO_ROOT / "docs" / "audits" / "kr-alpha-atlas-phase-c-integrity"
                             / "benchmark-reconciliation-corrected.json")

STOCK_SOURCE_AUDIT = (REPO_ROOT / "docs" / "audits" / "kr-alpha-atlas-phase-c-integrity"
                      / "stock-price-integrity.json")
REPLAY_RESULT_WEEKLY = REPO_ROOT / "docs" / "weekly-decision" / "weekly-passive-first-v1-weekly-replay.json"
REPLAY_RESULT_CORRECTED = (REPO_ROOT / "docs" / "weekly-decision"
                           / "weekly-passive-first-v1-replay-corrected-benchmark.json")
REPLAY_RESULT_WEEKLY_CORRECTED = (REPO_ROOT / "docs" / "weekly-decision"
                                  / "weekly-passive-first-v1-weekly-replay-corrected-benchmark.json")
# A distribution applied once moves the series by the official factor; twice,
# by its square. The band only sorts the events; it is not a test threshold.
DOUBLE_BAND = (1.8, 2.2)

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


def benchmark_audit() -> dict:
    """How replay-v16's 069500.KS series differs from the reconciled one, from committed audits only.

    For each ex-date Phase C could verify, the log of the replay's growth over
    the ex-date divided by the log of the official single distribution factor:
    1 means the distribution was applied once, 2 means twice.
    """
    old, stock = _load(BENCHMARK_RECON), _load(STOCK_SOURCE_AUDIT)
    if not old:
        return {"available": False}
    events = []
    for row in old.get("distributionAdjustmentDiagnostics") or []:
        official = math.log(row["officialSingleAdjustmentFactor"])
        if official <= 0:
            continue
        events.append({
            "exDate": row["exDate"], "cashKrwPerUnit": row["cashKrwPerUnit"],
            "officialFactor": round(row["officialSingleAdjustmentFactor"], 6),
            "replayOverRawMultiple": round(math.log(row["internalToRawGrowthFactor"]) / official, 3),
            "vendorOverRawMultiple": round(math.log(row["vendorToRawGrowthFactor"]) / official, 3),
            "replayOverVendorMultiple": round(
                math.log(max(row["internalToVendorGrowthFactor"], 1.0)) / official, 3)})
    doubled = [e for e in events if DOUBLE_BAND[0] <= e["replayOverRawMultiple"] <= DOUBLE_BAND[1]]
    single = [e for e in events if e not in doubled]
    gap = benchmark_definition_gap()
    return {
        "available": True,
        "ticker": "069500.KS",
        "status": "DISTRIBUTIONS_DOUBLE_APPLIED_IN_REPLAY_V16_BENCHMARK",
        "mechanismKo": ("replay-v16의 한국 세션 시세(FinanceDataReader/Naver)는 이 ETF에 대해 분배금이 이미 "
                        "반영된 수정 종가였고(벤더/원시 시세 비율 = 공식 분배 계수), pipeline/korea_prices.acquire가 "
                        "Yahoo 분배 이벤트를 price_adjustment.to_total_return으로 한 번 더 적용했습니다"
                        "(재현/벤더 비율 ≈ 공식 계수). 그래서 분배락일마다 계수가 두 번 곱해졌습니다."),
        "codePath": "pipeline/korea_prices.py acquire() -> price_adjustment.to_total_return(clean, _events_for(...))",
        "verifiableEvents": len(events), "doubledEvents": len(doubled),
        "singleOrOtherEvents": [e["exDate"] for e in single],
        "exceptionKo": ("2022-07-28은 재현/벤더 비율이 1.0(그 분배 이벤트가 Yahoo에 없음)이라 한 번만 반영됐습니다."
                        if any(e["exDate"] == "2022-07-28" for e in single) else None),
        "events": events,
        "annualGap": gap,
        "earlierYearsKo": ("발행사가 최근 20건만 제공해 2021-10 이전 분배락은 개별 검증이 안 됩니다. "
                           "다만 Phase C는 공식 보관 분배표(2012년~ 46건)로 전 기간 총수익을 재구성해 PASS했고, "
                           "연간 차이는 2013년부터 매년 양(+)입니다."),
        "stockLegs": {
            "conclusion": (stock or {}).get("ordinaryCashDoubleAdjustmentConclusion"),
            "scope": (stock or {}).get("scopeLimit"),
            "exception": (stock or {}).get("exception"),
            "noteKo": ("종목 시세는 6종목 표본에서 일반 현금배당 이중 반영이 발견되지 않았습니다(006800.KS 주식배당은 예외). "
                       "260종목 전체는 대조되지 않았습니다."),
        },
        "effectOnDecisionKo": ("주간 판단의 기대초과(보정)는 이 부풀려진 지수 대비로 측정된 봉인 결과 원장을 읽습니다. "
                               "같은 날 모든 종목에 공통인 이동이므로 순위 정렬 검정(t값)에는 영향이 없지만, "
                               "기대초과 수준은 종목에 불리하게 낮게 잡힙니다(연 1.1~4.5%p 차이, 126거래일 기준 대략 그 절반). 현재 판단(지수 100%)은 "
                               "정렬 미확인 때문이므로 바뀌지 않습니다."),
        "correctionKo": ("수정 회계: Phase C가 공식 분배금으로 대조한 일별 총수익 지수로 069500.KS 보유분만 다시 평가합니다. "
                         "판단·종목·비용은 그대로이며 원래(replay-v16) 결과는 지우지 않고 함께 보존합니다."),
    }


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


def us_readiness_block(report: dict | None) -> dict:
    """Compact, outcome-blind US source readiness for the site."""
    if not report:
        return {"available": False}
    store = report.get("pitStore") or {}
    years = store.get("byFiscalYearPctOfFilings") or {}
    keep = [y for y in sorted(years) if "2013" <= y <= "2026"]
    return {
        "available": True, "evidenceClass": report.get("evidenceClass"),
        "historicalDiscoveryPhase": report.get("historicalDiscoveryPhase"),
        "inventory": [{k: row.get(k) for k in ("axis", "status", "detailKo", "minimumToUnblock")}
                      for row in report.get("inventory") or []],
        "closedStudies": report.get("closedStudies") or [],
        "pitStore": {"tickers": store.get("tickers"), "filings": store.get("filings"),
                     "filingDelayDays": store.get("filingDelayDays"),
                     "byYear": {y: years[y] for y in keep}},
    }


def build_history(regions=("KR", "US")) -> dict:
    return {
        "usReadiness": us_readiness_block(_load(US_READINESS)),
        "usLocalCurrency": _load(US_LOCAL) or {"available": False},
        "replay": replay_block(_load(REPLAY_RESULT), regions),
        "replayCorrected": replay_block(_load(REPLAY_RESULT_CORRECTED), regions),
        "weeklyReplay": replay_block(_load(REPLAY_RESULT_WEEKLY), regions),
        "weeklyReplayCorrected": replay_block(_load(REPLAY_RESULT_WEEKLY_CORRECTED), regions),
        "benchmarkAudit": benchmark_audit(),
        "existingStudies": {"integratedAlphaPortfolio": integrated_block(_load(INTEGRATED_AUDIT)),
                            "phaseC": PHASE_C},
        "benchmarkDefinitionGap": benchmark_definition_gap(),
        "separationKo": ("각 결과는 기간·유니버스·비용·대체자산 정의가 달라 하나의 수치로 합치지 않습니다. "
                         "과거 성과가 가장 좋았던 방식을 사전에 알 수 있었던 것처럼 표시하지 않습니다."),
    }
