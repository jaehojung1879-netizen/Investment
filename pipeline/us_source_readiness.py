"""Outcome-blind US information-source readiness (us-source-readiness-v1).

Measures what the sealed US point-in-time fundamentals store CAN support, and
records which sources are blocked, paid, closed or never probed. It reads no
price after a filing, no return, no label and no model output; the only
inputs are filing metadata and which reported concepts are present.

The inventory rows that are not measured here cite the repository document or
result that measured them, verbatim in substance; nothing is re-asserted from
memory and an unprobed source is marked NOT_PROBED, never "available".
"""
from __future__ import annotations

import gzip
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

DIVIDEND_CONCEPTS = ("us-gaap_CommonStockDividendsPerShareDeclared",
                     "us-gaap_CommonStockDividendsPerShareCashPaid")
SHARE_CONCEPTS = ("dei_EntityCommonStockSharesOutstanding",
                  "us-gaap_CommonStockSharesOutstanding",
                  "us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding")
BUYBACK_CONCEPTS = ("us-gaap_PaymentsForRepurchaseOfCommonStock",)
CASH_DIVIDEND_CONCEPTS = ("us-gaap_PaymentsOfDividendsCommonStock", "us-gaap_PaymentsOfDividends")
OCF_CONCEPTS = ("us-gaap_NetCashProvidedByUsedInOperatingActivities",
                "us-gaap_NetCashProvidedByUsedInOperatingActivitiesContinuingOperations")


def _concepts(record: dict) -> set[str]:
    out = set()
    for rows in (record.get("statements") or {}).values():
        for row in rows or []:
            if row.get("concept") and row.get("value") is not None:
                out.add(row["concept"])
    return out


def _days(a: str | None, b: str | None) -> int | None:
    try:
        return (date.fromisoformat(str(b)[:10]) - date.fromisoformat(str(a)[:10])).days
    except (TypeError, ValueError):
        return None


def _quantiles(values: list[int]) -> dict:
    if not values:
        return {"n": 0}
    s = sorted(values)
    pick = lambda q: s[min(len(s) - 1, int(q * (len(s) - 1)))]  # noqa: E731
    return {"n": len(s), "p10": pick(.1), "median": pick(.5), "p90": pick(.9), "max": s[-1]}


def measure_store(records) -> dict:
    """Filing-level readiness, by fiscal year and form, from raw filings only."""
    by_year = defaultdict(lambda: defaultdict(int))
    delays = defaultdict(list)
    tickers = set()
    negative_delay = 0
    malformed = 0
    for record in records:
        tickers.add(record.get("ticker"))
        fiscal = record.get("fiscalYear")
        if not isinstance(fiscal, int) or not 1990 <= fiscal <= 2100:
            malformed += 1
            continue
        year = str(fiscal)
        form = record.get("form") or "UNKNOWN"
        concepts = _concepts(record)
        cell = by_year[year]
        cell["filings"] += 1
        cell["dividendPerShare"] += bool(concepts & set(DIVIDEND_CONCEPTS))
        cell["shareCount"] += bool(concepts & set(SHARE_CONCEPTS))
        cell["buyback"] += bool(concepts & set(BUYBACK_CONCEPTS))
        cell["cashDividendsPaid"] += bool(concepts & set(CASH_DIVIDEND_CONCEPTS))
        cell["operatingCashFlow"] += bool(concepts & set(OCF_CONCEPTS))
        cell["acceptedTimestamp"] += bool(record.get("acceptedDate"))
        delay = _days(record.get("periodEnd"), record.get("availableFrom"))
        if delay is not None:
            if delay < 0:
                negative_delay += 1
            delays[form].append(delay)
    years = {}
    for year, cell in sorted(by_year.items()):
        n = cell["filings"]
        years[year] = {"filings": n, **{k: round(100 * cell[k] / n, 2) for k in (
            "dividendPerShare", "cashDividendsPaid", "shareCount", "buyback", "operatingCashFlow",
            "acceptedTimestamp")}}
    return {
        "tickers": len(tickers - {None}),
        "filings": sum(c["filings"] for c in by_year.values()),
        "byFiscalYearPctOfFilings": years,
        "filingDelayDays": {form: _quantiles(v) for form, v in sorted(delays.items())},
        "filingsVisibleBeforePeriodEnd": negative_delay,
        "malformedFiscalYearFilings": malformed,
        "note": ("Presence counts a filing that STATES the concept; a dividend concept absent from a "
                 "non-payer's filing is a true absence, so these are reporting rates, not data gaps."),
    }


def iter_store(directory: Path):
    for path in sorted(Path(directory).glob("finnhub-*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)


# --------------------------------------------------------------------------- #
# Inventory of sources not measured here, each citing its own evidence.
# --------------------------------------------------------------------------- #
INVENTORY = [
    {"axis": "Historical S&P 500 membership (as-of)", "status": "AVAILABLE_WITH_DOCUMENTED_IDENTITY_LIMITS",
     "evidence": "docs/results/alpha-opportunity-model-v3-survivorship-audit.json; AGENTS.md v2.27",
     "detailKo": "핀 고정된 구성종목 이력. 기호 오류 2건과 14개 검증된 티커 변경을 해소했으나 2023-04 이전 CIK 부재로 일부 변경은 미검증."},
    {"axis": "Delisted / departed company prices", "status": "BLOCKED_PAID_SOURCE",
     "evidence": "docs/us-delisted-prices-source.md (Probes run #2, 2026-09-16); data/us-unpriced-members.json",
     "detailKo": "replay-v16 기준 829개 역대 구성종목 중 194개(v3 재집계 212개 정체성) 가격 없음. polygon(PLAN_LIMITED)·FMP(HTTP 402)는 보유하나 유료. 요금제·비용은 미측정 — 결제는 소유자 결정.",
     "minimumToUnblock": "polygon.io 또는 financialmodelingprep 유료 플랜(구체 요금 미확인), 이후 새 replay 세대"},
    {"axis": "Dividends / adjusted total return (priced names, SPY)", "status": "AVAILABLE_PRICED_NAMES_ONLY",
     "evidence": "config.json benchmarkSources; docs/us-delisted-prices-source.md",
     "detailKo": "Yahoo auto_adjust 총수익 기준. 가격이 없는 퇴출 종목은 배당도 없음."},
    {"axis": "M&A consideration / successor chains", "status": "PARTIAL",
     "evidence": "data/replay-corporate-actions.json (US 1건: CASH_AND_STOCK_MERGER)",
     "detailKo": "출처가 인용된 기업행동 1건만 장부에 있음. 나머지 인수·합병 대가는 미구축."},
    {"axis": "SEC filing acceptance time", "status": "AVAILABLE_VIA_FINNHUB_SEC_DIRECT_BLOCKED",
     "evidence": "docs/us-pit-fundamentals-source.md; AGENTS.md vendor-refusal invariants",
     "detailKo": "Finnhub financials-reported가 SEC acceptedDate를 availableFrom으로 제공. SEC 직접 접근은 Actions egress에서 차단."},
    {"axis": "PIT fundamentals (earnings, cash flow, balance sheet)", "status": "AVAILABLE_MEASURED_BELOW",
     "evidence": "signal-history ledger/fundamentals/us (this audit)", "detailKo": "아래 측정치 참조."},
    {"axis": "Shareholder distributions (dividend change, buybacks)", "status": "DERIVABLE_NOT_YET_DERIVED",
     "evidence": "AGENTS.md v2.23 (CommonStockDividendsPerShareDeclared in the sealed US store); this audit",
     "detailKo": "원시 항목은 이미 PIT 저장소에 있음. 기간 대비 변화 필드는 아직 없음. 미검증 새 정보 축."},
    {"axis": "Relative-strength persistence (breadth)", "status": "ALREADY_TESTED_CLOSED",
     "evidence": "docs/us-alpha-research-design-v1.md (superseded into regional-alpha-model-v1); AGENTS.md v2.24",
     "detailKo": "regional-alpha-model-v1의 31개 특징 행렬에 포함되어 NO_MODEL_EVIDENCE로 종료. 재실행 금지."},
    {"axis": "Fundamental acceleration", "status": "ALREADY_TESTED_CLOSED",
     "evidence": "docs/results/fundamental-acceleration-discovery-report.json",
     "detailKo": "US 커버리지 81.79%의 깨끗한 판독에서 증거 없음(CASE D)."},
    {"axis": "Institutional ownership (13F)", "status": "BLOCKED_SOURCE",
     "evidence": "AGENTS.md v2.25 (guru-13f probe BLOCKED / route NONE); data/institutional_13f_cache.json is a dated display cache",
     "detailKo": "SEC 차단으로 역사적 13F 수집 불가. 표시용 캐시는 특징으로 쓰지 않음."},
    {"axis": "Insider trading (Form 4)", "status": "BLOCKED_SOURCE",
     "evidence": "AGENTS.md v2.23", "detailKo": "SEC 차단, 무료 대체 벤더 없음."},
    {"axis": "Analyst estimates / revisions", "status": "BLOCKED_PAID_SOURCE",
     "evidence": "AGENTS.md v2.23; docs/us-alpha-research-design-v1.md candidates A-C",
     "detailKo": "Finnhub 무료 티어는 현재 스냅샷 수준, 역사 추정치는 별도 유료 상품."},
    {"axis": "Short interest", "status": "NOT_PROBED",
     "evidence": "no probe in this repository", "detailKo": "이 저장소에서 원천을 시험한 적이 없음. 가용하다고 주장하지 않음."},
    {"axis": "Liquidity / capacity", "status": "AVAILABLE_PRICED_NAMES_ONLY",
     "evidence": "Yahoo daily volume in the replay price panel", "detailKo": "가격이 있는 종목만. 개인 규모 주문은 거래대금 대비 작다고 가정(측정 아님)."},
]

CLOSED_STUDIES = [
    {"study": "regional-alpha-model-v1", "result": "NO_MODEL_EVIDENCE (US)",
     "evidence": "AGENTS.md v2.24 (Actions run 35826122755)"},
    {"study": "four-factor-signal-attribution-audit-v1", "result": "all sleeves region-sign-unstable; no pooled sleeve clears raw significance",
     "evidence": "docs/results/four-factor-signal-attribution-audit-report.json"},
    {"study": "fundamental-acceleration-discovery-v1", "result": "CASE D — NO_DISCOVERY_EVIDENCE",
     "evidence": "docs/results/fundamental-acceleration-discovery-report.json"},
    {"study": "alpha-opportunity-model-v3", "result": "BLOCKED_BY_DATA_INTEGRITY (US survivorship)",
     "evidence": "docs/results/alpha-opportunity-model-v3-survivorship-audit.json"},
]


def build_report(store_dir: Path) -> dict:
    return {
        "id": "us-source-readiness-v1",
        "evidenceClass": "OUTCOME_BLIND_SOURCE_INVENTORY",
        "readsReturns": False, "readsLabels": False, "readsModelOutput": False,
        "historicalDiscoveryPhase": "CLOSED",
        "historicalDiscoveryPhaseEvidence": "docs/us-alpha-research-design-v1.md (US_ALPHA_DISCOVERY_BUDGET spent by regional-alpha-model-v1)",
        "pitStore": measure_store(iter_store(store_dir)),
        "inventory": INVENTORY,
        "closedStudies": CLOSED_STUDIES,
    }
