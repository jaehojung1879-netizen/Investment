"""weekly-passive-first-v1: per-region weekly decision, 0-5 stocks, benchmark fallback.

The question each week, for KR and US separately: hold the region's passive
benchmark, or replace part of it with up to five stocks that have a DEFENSIBLE
expected advantage over that benchmark after the cost of switching into them.

Nothing here is a new model. Every quantity comes from an existing production
component, named where it is used:

* candidates: the production long-term research sleeve (``longterm.build``);
* edge: the production historical calibration (``historical_calibration``),
  used only where its bucket is ``usable`` — the region's alpha ordering is
  established and the bucket has enough effective dates. Otherwise the edge is
  NOT_AVAILABLE, never zero, and the region holds its benchmark;
* costs: ``benchmark_alpha.REALISTIC_COSTS`` (dated Korean sell tax);
* selection constraints: ``kelly_portfolio.select_portfolio_by_scores``.

Unused capital is held in the regional benchmark ETF, not cash, and the weights
always sum to 100%. Zero stocks is a normal, fully specified outcome. The frozen
specification is ``docs/weekly-decision/weekly-passive-first-v1.json``; this module
must agree with it (a test compares the constants).

KR and US are decided independently: no cross-region ranking, no pooled
calibration, no FX input. Their as-of dates are each region's own last completed
exchange session and are never presented as simultaneous.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from . import benchmark_alpha as BA
from . import historical_calibration as HC
from . import kelly_portfolio as KP
from . import portfolio_validation as PV
from . import replay_calendar as RC

POLICY_VERSION = "weekly-passive-first-v1"
POLICY_STATUS = "EXPLORATORY_WEEKLY_DECISION"
SPEC_PATH = "docs/weekly-decision/weekly-passive-first-v1.json"
BENCHMARKS = {"KR": "069500.KS", "US": "SPY"}
BENCHMARK_NAMES = {"KR": "KODEX 200", "US": "SPDR S&P 500 ETF"}
CURRENCY = {"KR": "KRW", "US": "USD"}
MAX_NAMES = 5
MIN_NAMES = 0
NAME_WEIGHT = 0.15            # config.json longterm.maxNameWeight
MAX_NAMES_PER_SECTOR = 2      # config.json kellyPortfolio.selection.maxNamesPerSector
EDGE_HORIZON_SESSIONS = 126
# Domestic equity ETFs are exempt from the Korean securities transaction tax;
# the US leg keeps the same regulatory-fee proxy the stock leg carries.
ETF_SELL_TAX_BPS = {"KR": 0.0, "US": 0.30}
# A session counts as completed only after its close plus a settlement buffer,
# in the exchange's own time zone, so daylight saving never moves the cut.
EXCHANGE_CLOSE = {"KR": ("Asia/Seoul", 15, 30), "US": ("America/New_York", 16, 0)}
SETTLEMENT_BUFFER_MINUTES = 60

SELECTION_CFG = {
    "selection": {"targetNames": MAX_NAMES, "minNames": MIN_NAMES,
                  "maxNamesPerSector": MAX_NAMES_PER_SECTOR,
                  "maxNamesPerRegion": MAX_NAMES},
}

STATUS_KO = {
    "PASSIVE_NO_DEFENSIBLE_EDGE": "지수 대비 비용을 넘는 방어 가능한 우위를 확인한 종목이 없어 지수 100%",
    "STOCKS_SELECTED": "지수 대비 비용 차감 후 기대 우위가 양(+)인 종목만 담고 나머지는 지수",
    "STALE_DATA_NO_NEW_DECISION": "최신 완료 세션 데이터가 아직 없어 새 판단을 내지 않음",
    "BLOCKED": "데이터 안전 차단 상태 — 종목·비중을 표시하지 않음",
    "NO_CANDIDATES": "리서치 후보가 없어 지수 100%",
}
EXCLUSION_KO = {
    "CALIBRATION_UNAVAILABLE": "과거 보정 자료 없음",
    "ORDERING_NOT_ESTABLISHED": "알파 순위의 수익 정렬이 통계적으로 확인되지 않음",
    "INSUFFICIENT_EFFECTIVE_SPREAD_DATES": "보정 표본 부족",
    "EXPECTED_NET_ADVANTAGE_NOT_POSITIVE": "비용 차감 후 기대 우위가 0 이하",
    "ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING": "진입/리서치 상태가 편입을 막음",
    "DOWNSIDE_RISK_UNAVAILABLE": "하방위험 측정 불가",
    "BELOW_TARGET_COUNT_CUTOFF": "5종목 한도 밖",
    "SECTOR_NAME_LIMIT": "섹터당 2종목 한도",
    "REGION_NAME_LIMIT": "지역 한도",
}


def _r(value, digits=4):
    return None if value is None else round(float(value), digits)


# --------------------------------------------------------------------------- #
# Costs
# --------------------------------------------------------------------------- #
def cost_breakdown(region: str, as_of: str) -> dict:
    """Round-trip cost, in percentage points, of replacing benchmark with a stock.

    Entering a stock from the benchmark sells the ETF and buys the stock; leaving
    it later sells the stock and buys the ETF back. Both round trips are paid.
    """
    policy = PV._dated_cost_policy(dict(BA.REALISTIC_COSTS[region]), as_of)
    commission = float(policy.get("commissionBps", 0))
    spread = float(policy.get("spreadBps", 0))
    sell_tax = float(policy.get("sellTaxBps", 0))
    stock_bps = 2 * commission + spread + sell_tax
    etf_bps = 2 * commission + spread + ETF_SELL_TAX_BPS[region]
    return {"stockRoundTripPct": _r(stock_bps / 100), "benchmarkRoundTripPct": _r(etf_bps / 100),
            "switchCostPct": _r((stock_bps + etf_bps) / 100),
            "sellTaxBps": sell_tax, "commissionBps": commission, "spreadBps": spread,
            "source": "pipeline/benchmark_alpha.py REALISTIC_COSTS (dated sell tax)"}


def trade_cost_fraction(region: str, as_of: str, *, is_benchmark: bool, side: str) -> float:
    """One leg's cost as a fraction of the traded weight (used by the replay)."""
    policy = PV._dated_cost_policy(dict(BA.REALISTIC_COSTS[region]), as_of)
    bps = float(policy.get("commissionBps", 0)) + float(policy.get("spreadBps", 0)) / 2
    if side == "sell":
        bps += ETF_SELL_TAX_BPS[region] if is_benchmark else float(policy.get("sellTaxBps", 0))
    return bps / 10000


# --------------------------------------------------------------------------- #
# Edge
# --------------------------------------------------------------------------- #
def edge_estimate(calibration: dict | None, region: str, alpha_percentile) -> dict:
    """The calibrated 126-session edge for one name, or an explicit absence."""
    if not calibration or not calibration.get("available"):
        return {"available": False, "reason": "CALIBRATION_UNAVAILABLE"}
    row = HC.lookup_bucket(calibration, region, alpha_percentile)
    if row is None:
        return {"available": False, "reason": "CALIBRATION_UNAVAILABLE"}
    ordering = ((calibration.get("regions") or {}).get(region) or {}).get("ordering") or {}
    out = {
        "bucket": row.get("bucket"),
        "pointEstimatePct": row.get("calibratedExpectedExcessReturnPct"),
        "confidenceIntervalPct": row.get("confidenceIntervalPct"),
        "standardErrorPct": row.get("standardErrorPct"),
        "basis": row.get("conservativeBasis"),
        "effectiveDates": row.get("effectiveDates"),
        "orderingEstablished": bool(ordering.get("established")),
        "horizonSessions": int(calibration.get("horizonDays") or EDGE_HORIZON_SESSIONS),
    }
    if not row.get("usable"):
        out.update(available=False, reason=row.get("unusableReason") or "ORDERING_NOT_ESTABLISHED")
        return out
    out.update(available=True, reason=None, expectedExcessPct=row.get("calibratedExpectedExcessReturnPct"))
    return out


def score_candidates(candidates: list[dict], calibration: dict | None, region: str,
                     as_of: str, incumbents: set[str] | None = None) -> list[dict]:
    """Score one region's candidates. Absent edges stay absent; nothing is zero-filled."""
    incumbents = incumbents or set()
    costs = cost_breakdown(region, as_of)
    switch = float(costs["switchCostPct"])
    rows = []
    for candidate in candidates:
        if (candidate.get("region") or region) != region:
            continue
        edge = edge_estimate(calibration, region, candidate.get("alphaPercentile"))
        risk = KP._risk_unit(candidate)
        state = KP._state_multiplier(candidate, {})
        net = (float(edge["expectedExcessPct"]) - switch) if edge.get("available") else None
        incumbent = candidate.get("ticker") in incumbents
        credit = switch if incumbent else 0.0
        excluded = []
        if not edge.get("available"):
            excluded.append(edge.get("reason") or "CALIBRATION_UNAVAILABLE")
        elif net is not None and net <= 0:
            excluded.append("EXPECTED_NET_ADVANTAGE_NOT_POSITIVE")
        if state <= 0:
            excluded.append("ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING")
        if risk is None or risk <= 0:
            excluded.append("DOWNSIDE_RISK_UNAVAILABLE")
        score = ((net + credit) / (risk * 100) * state
                 if net is not None and risk and risk > 0 and state > 0 else -1e12)
        entry = (candidate.get("entry") or {}).get("entryState") or candidate.get("entryState")
        rows.append({
            "ticker": candidate["ticker"], "name": candidate.get("name"),
            "region": region, "sector": candidate.get("sector") or "Unclassified",
            "sectorKo": candidate.get("sectorKo"),
            "alphaPercentile": candidate.get("alphaPercentile"),
            "longTermResearchView": candidate.get("longTermResearchView"),
            "entryState": entry,
            "stateMultiplier": _r(state, 3),
            "downsideVolPct": _r(risk * 100, 2) if risk else None,
            "edge": edge,
            "switchCostPct": switch,
            "expectedNetAdvantagePct": _r(net),
            "incumbent": incumbent, "retentionCreditPct": _r(credit),
            "score": score, "convictionScore": score,
            "evidenceCoverage": candidate.get("evidenceCoverage"),
            "eligible": not excluded, "exclusionCodes": excluded,
        })
    return rows


# --------------------------------------------------------------------------- #
# Decision
# --------------------------------------------------------------------------- #
def decide(region: str, candidates: list[dict], calibration: dict | None, as_of: str,
           incumbents: set[str] | None = None) -> dict:
    """Apply the fixed 0-5 rule. Pure: same inputs, same output."""
    benchmark = BENCHMARKS[region]
    scored = score_candidates(candidates, calibration, region, as_of, incumbents)
    pool = [c for c in candidates if (c.get("region") or region) == region]
    selected, meta = KP.select_portfolio_by_scores(pool, scored, SELECTION_CFG,
                                                   method=POLICY_VERSION)
    chosen = [c["ticker"] for c in selected]
    by_ticker = {r["ticker"]: r for r in meta.get("ranking") or []}
    for row in scored:
        ranked = by_ticker.get(row["ticker"])
        if ranked is not None:
            row["exclusionCodes"] = list(ranked.get("exclusionCodes") or row["exclusionCodes"])
        row["selected"] = row["ticker"] in chosen
    weights = {t: NAME_WEIGHT for t in chosen}
    benchmark_weight = round(1.0 - NAME_WEIGHT * len(chosen), 10)
    if benchmark_weight < -1e-9:
        raise ValueError("stock weights exceed 100%")
    holdings = []
    for row in sorted((r for r in scored if r["selected"]), key=lambda r: (-r["score"], r["ticker"])):
        holdings.append({k: row[k] for k in (
            "ticker", "name", "sector", "sectorKo", "alphaPercentile", "entryState",
            "downsideVolPct", "expectedNetAdvantagePct", "switchCostPct", "incumbent")}
            | {"weightPct": round(NAME_WEIGHT * 100, 4),
               "edgePct": row["edge"].get("expectedExcessPct"),
               "edgeConfidenceIntervalPct": row["edge"].get("confidenceIntervalPct"),
               "reasonKo": (f"보정 기대초과 {row['edge'].get('expectedExcessPct'):+.2f}%p(126거래일) − "
                            f"전환비용 {row['switchCostPct']:.2f}%p = 순우위 "
                            f"{row['expectedNetAdvantagePct']:+.2f}%p")})
    if not pool:
        status = "NO_CANDIDATES"
    elif chosen:
        status = "STOCKS_SELECTED"
    else:
        status = "PASSIVE_NO_DEFENSIBLE_EDGE"
    excluded = sorted(
        ({"ticker": r["ticker"], "name": r.get("name"), "codes": r["exclusionCodes"],
          "reasonsKo": [EXCLUSION_KO.get(c, c) for c in r["exclusionCodes"]]}
         for r in scored if not r["selected"]), key=lambda r: r["ticker"])
    ordering = (((calibration or {}).get("regions") or {}).get(region) or {}).get("ordering") or {}
    return {
        "region": region, "asOfDate": as_of, "policyVersion": POLICY_VERSION,
        "benchmark": benchmark, "benchmarkName": BENCHMARK_NAMES[region],
        "status": status, "statusKo": STATUS_KO[status],
        "stockCount": len(chosen),
        "weights": {**weights, benchmark: benchmark_weight} if benchmark_weight > 0 else dict(weights),
        "stockWeightPct": round(NAME_WEIGHT * 100 * len(chosen), 4),
        "benchmarkWeightPct": round(benchmark_weight * 100, 4),
        "holdings": holdings,
        "candidates": [{k: r[k] for k in (
            "ticker", "name", "sector", "alphaPercentile", "entryState", "downsideVolPct",
            "expectedNetAdvantagePct", "eligible", "selected", "exclusionCodes")}
            | {"edgePointEstimatePct": r["edge"].get("pointEstimatePct"),
               "edgeAvailable": bool(r["edge"].get("available"))}
            for r in sorted(scored, key=lambda r: (-r["score"], r["ticker"]))],
        "excluded": excluded,
        "noTradeReason": None if chosen else (
            "ORDERING_NOT_ESTABLISHED" if pool and not ordering.get("established")
            else ("NO_CANDIDATES" if not pool else "NO_POSITIVE_NET_ADVANTAGE")),
        "calibrationOrdering": {k: ordering.get(k) for k in (
            "established", "reason", "topMinusBottomTStat", "rankICTStat", "meanRankIC",
            "topBucketSpreadPct") if k in ordering},
        "costs": cost_breakdown(region, as_of),
    }


# --------------------------------------------------------------------------- #
# Freshness and the weekly key
# --------------------------------------------------------------------------- #
def last_completed_session(region: str, now: datetime) -> str:
    """The latest session of the region's exchange whose close + buffer has passed."""
    tz, hour, minute = EXCHANGE_CLOSE[region]
    local = now.astimezone(ZoneInfo(tz))
    cal = "KR" if region == "KR" else "US"
    start = (local - pd.Timedelta(days=20)).strftime("%Y-%m-%d")
    days = RC.sessions(start, local.strftime("%Y-%m-%d"), cal)
    cutoff = local.replace(hour=hour, minute=minute, second=0, microsecond=0) \
        + pd.Timedelta(minutes=SETTLEMENT_BUFFER_MINUTES)
    for day in reversed(list(days)):
        if day.date() < local.date() or local >= cutoff:
            return day.strftime("%Y-%m-%d")
    raise ValueError("no completed session in the lookback window")


def is_week_end_session(region: str, session: str) -> bool:
    """True when the next exchange session falls in a later ISO week."""
    cal = "KR" if region == "KR" else "US"
    stamp = pd.Timestamp(session)
    following = RC.sessions((stamp + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                            (stamp + pd.Timedelta(days=21)).strftime("%Y-%m-%d"), cal)
    if not len(following):
        raise ValueError("calendar exhausted")
    return following[0].isocalendar()[:2] != stamp.isocalendar()[:2]


def session_on_or_before(region: str, date: str) -> str:
    """A vendor row dated on an exchange holiday is mapped to the real session."""
    cal = "KR" if region == "KR" else "US"
    stamp = pd.Timestamp(date)
    days = RC.sessions((stamp - pd.Timedelta(days=20)).strftime("%Y-%m-%d"),
                       stamp.strftime("%Y-%m-%d"), cal)
    if not len(days):
        raise ValueError("no session on or before " + date)
    return days[-1].strftime("%Y-%m-%d")


def freshness(region: str, latest_observed: str | None, now: datetime) -> dict:
    expected = last_completed_session(region, now)
    if latest_observed is not None:
        latest_observed = session_on_or_before(region, latest_observed)
    if latest_observed is None:
        return {"status": "STALE", "expectedSession": expected, "observedSession": None,
                "reason": "NO_OBSERVATION"}
    stale = latest_observed < expected
    return {"status": "STALE" if stale else "FRESH", "expectedSession": expected,
            "observedSession": latest_observed,
            "weekEnd": is_week_end_session(region, latest_observed),
            "reason": "SOURCE_NOT_UPDATED" if stale else None}


# --------------------------------------------------------------------------- #
# Receipts
# --------------------------------------------------------------------------- #
DIGEST_EXCLUDED = ("generatedAt", "digest", "previousWeekChange", "freshness",
                   "publishedFrom", "laterRecomputationDigest")


def canonical(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def receipt_digest(receipt: dict) -> str:
    content = {k: v for k, v in receipt.items() if k not in DIGEST_EXCLUDED}
    return hashlib.sha256(canonical(content)).hexdigest()


def calibration_digest(calibration: dict | None) -> str:
    """Identity of the calibration buckets a decision read."""
    regions = (calibration or {}).get("regions") or {}
    return hashlib.sha256(canonical({r: {"buckets": b.get("buckets"), "ordering": b.get("ordering")}
                                     for r, b in regions.items()})).hexdigest()


def receipt_id(region: str, as_of: str) -> str:
    return f"{POLICY_VERSION}|{region}|{as_of}"


def previous_change(decision: dict, prior: dict | None) -> dict:
    if not prior:
        return {"available": False, "reason": "NO_PRIOR_FINAL_RECEIPT"}
    now = {h["ticker"] for h in decision.get("holdings") or []}
    was = {h["ticker"] for h in prior.get("holdings") or []}
    return {"available": True, "priorAsOfDate": prior.get("asOfDate"),
            "added": sorted(now - was), "removed": sorted(was - now), "kept": sorted(now & was),
            "benchmarkWeightPctBefore": prior.get("benchmarkWeightPct"),
            "benchmarkWeightPctAfter": decision.get("benchmarkWeightPct"),
            "changed": now != was}


def build_receipt(decision: dict, *, generated_at: str, inputs: dict, evidence: dict,
                  week_status: str, prior: dict | None = None) -> dict:
    receipt = {
        "receiptId": receipt_id(decision["region"], decision["asOfDate"]),
        "schema": "WEEKLY_DECISION_RECEIPT_V1",
        "policyVersion": POLICY_VERSION, "policyStatus": POLICY_STATUS,
        "specPath": SPEC_PATH, "region": decision["region"],
        "market": "KRX" if decision["region"] == "KR" else "NYSE/Nasdaq",
        "asOfDate": decision["asOfDate"], "weekStatus": week_status,
        "evidenceStatus": evidence,
        "inputs": inputs,
        **{k: v for k, v in decision.items() if k not in ("region", "asOfDate", "policyVersion")},
        "liveValidated": False,
        "generatedAt": generated_at,
    }
    receipt["previousWeekChange"] = previous_change(decision, prior)
    receipt["digest"] = receipt_digest(receipt)
    return receipt


def append_receipts(existing: list[dict], new: list[dict]) -> tuple[list[dict], dict]:
    """Append-only merge. An identity already present is never rewritten."""
    known = {row["receiptId"]: row for row in existing}
    appended, unchanged, conflicts = [], [], []
    for receipt in new:
        if receipt.get("weekStatus") != "FINAL_WEEKLY":
            continue
        if receipt_digest(receipt) != receipt.get("digest"):
            raise ValueError(f"receipt digest mismatch: {receipt.get('receiptId')}")
        prior = known.get(receipt["receiptId"])
        if prior is None:
            appended.append(receipt)
            known[receipt["receiptId"]] = receipt
        elif prior.get("digest") == receipt["digest"]:
            unchanged.append(receipt["receiptId"])
        else:
            conflicts.append({"receiptId": receipt["receiptId"], "kept": prior.get("digest"),
                              "refused": receipt["digest"]})
    return existing + appended, {"appended": [r["receiptId"] for r in appended],
                                 "unchanged": unchanged, "conflicts": conflicts}


def latest_final(receipts: list[dict], region: str, before: str | None = None) -> dict | None:
    rows = [r for r in receipts if r.get("region") == region
            and r.get("policyVersion") == POLICY_VERSION
            and r.get("weekStatus") == "FINAL_WEEKLY"
            and (before is None or r.get("asOfDate") < before)]
    return max(rows, key=lambda r: r["asOfDate"]) if rows else None


# --------------------------------------------------------------------------- #
# Site payload
# --------------------------------------------------------------------------- #
EVIDENCE = {
    "prediction": "MODEL_DERIVED_CALIBRATION_HISTORICAL_OOS",
    "selection": "EXPLORATORY_POLICY_NOT_VALIDATED",
    "historicalDevelopment": "POST_OUTCOME_EXPOSED_EXPLORATORY_REPLAY",
    "prospectivePaper": "RECEIPTS_ACCUMULATING_NOT_YET_EVALUABLE",
    "verifiedLive": "NOT_VERIFIED",
}


def build(long_term: dict | None, calibration: dict | None, observed_sessions: dict,
          *, now: datetime | None = None, blocked: bool = False,
          prior_receipts: list[dict] | None = None, names: dict | None = None,
          input_identity: dict | None = None, history: dict | None = None) -> dict:
    """Assemble ``weeklyDecision`` for site-data. Never raises on missing inputs."""
    now = now or datetime.now(timezone.utc)
    generated = now.astimezone(timezone.utc).isoformat()
    names = names or {}
    prior_receipts = prior_receipts or []
    regions = {}
    for region in ("KR", "US"):
        if blocked:
            regions[region] = {"region": region, "status": "BLOCKED", "statusKo": STATUS_KO["BLOCKED"],
                               "benchmark": BENCHMARKS[region], "holdings": [], "weights": {},
                               "policyVersion": POLICY_VERSION}
            continue
        observed = observed_sessions.get(region)
        fresh = freshness(region, observed, now)
        last = latest_final(prior_receipts, region)
        if fresh["status"] == "STALE":
            regions[region] = {
                "region": region, "status": "STALE_DATA_NO_NEW_DECISION",
                "statusKo": STATUS_KO["STALE_DATA_NO_NEW_DECISION"],
                "benchmark": BENCHMARKS[region], "freshness": fresh,
                "policyVersion": POLICY_VERSION, "holdings": [], "weights": {},
                "lastValidReceipt": last,
            }
            continue
        blob = ((long_term or {}).get("regions") or {}).get(region) or {}
        candidates = []
        for row in blob.get("picks") or []:
            item = dict(row)
            item["region"] = region
            item["name"] = names.get(item["ticker"]) or item.get("name")
            candidates.append(item)
        observed = fresh["observedSession"]
        prior = latest_final(prior_receipts, region, before=observed)
        incumbents = {h["ticker"] for h in (prior or {}).get("holdings") or []}
        decision = decide(region, candidates, calibration, observed, incumbents)
        week_status = "FINAL_WEEKLY" if fresh.get("weekEnd") else "INTRA_WEEK_PREVIEW"
        inputs = {"calibrationHorizonSessions": (calibration or {}).get("horizonDays"),
                  "calibrationAvailable": bool((calibration or {}).get("available")),
                  "candidatePool": "longTerm.regions.%s.picks" % region,
                  "candidateCount": len(candidates), **(input_identity or {})}
        receipt = build_receipt(decision, generated_at=generated, inputs=inputs,
                                evidence=EVIDENCE, week_status=week_status, prior=prior)
        receipt["freshness"] = fresh
        regions[region] = receipt
    return {
        "policyVersion": POLICY_VERSION, "policyStatus": POLICY_STATUS, "specPath": SPEC_PATH,
        "generatedAt": generated, "blocked": bool(blocked),
        "evidence": EVIDENCE, "liveValidated": False,
        "regions": regions,
        "history": history or {"available": False, "reason": "REPLAY_RESULT_NOT_SUPPLIED"},
        "disclaimerKo": ("탐색적 주간 판단입니다. 검증된 투자 시스템이 아니며 매매를 실행하지 않습니다. "
                         "근거가 부족하면 지역 지수를 기본값으로 둡니다."),
    }
