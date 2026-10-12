"""Independent, current-only CHAMPION paper observations; never a return replay.

Uses the original production selection/baseline functions and constraints. C2
copies C1's serialized stock weights and substitutes only residual cash. The
current production candidate pool and macro budget differ from the historical
price-sleeve proxy/21-session sequence; this is explicitly a prospective variant.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

from . import kelly_portfolio as KP
from . import weekly_decision as W

ROOT = Path(__file__).resolve().parents[1]
VERSION = "current-champion-decisions-v1"
SCHEMA = "CURRENT_CHAMPION_RECEIPT_V1"
ARTIFACT = "CURRENT_CHAMPION_ARTIFACT_V1"
PUBLICATION = "CURRENT_CHAMPION_PUBLICATION_V1"
RELATIVE_STORE = "ledger/research-strategies/" + VERSION
EVIDENCE = "PROSPECTIVE_RESEARCH_ONLY_CURRENT_CHAMPION_VARIANT"
ENGINE_SHA = "6a4bd54be11e35e7348f64d0c99e7764635c4efcea62306da0b6ca81bfb3b06c"
CONFIG_SHA = "d1169e1e4a84ded1385e11e591ea01a4b383e7a625960ece9278a0bde3c15273"
LIMITATIONS = [
    "현재 관측 연구 변형입니다. 과거 21세션 앵커의 투자 순서와 동일하지 않습니다.",
    "현재 production 장기 후보는 과거 price-sleeve proxy 후보와 다릅니다.",
    "현재 거시 위험예산을 적용합니다. 과거에는 국면 현금 하한만 기록된 앵커가 있습니다.",
    "conviction은 팩터 순위/관측 위험 점수이며 기대수익·확률·검증된 알파가 아닙니다.",
    "현재 재무 스냅샷의 PIT/빈티지 한계가 남습니다. 실계좌·매매 실행·승격 대상이 아닙니다.",
]


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def receipt_digest(row):
    return digest({k: v for k, v in row.items() if k not in {"digest", "previousObservationChange"}})


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def methodology():
    """A new policy version is required before silently changing the engine/config."""
    engine = hashlib.sha256((ROOT / "pipeline/kelly_portfolio.py").read_bytes()).hexdigest()
    raw = (ROOT / "config.json").read_bytes()
    if engine != ENGINE_SHA or hashlib.sha256(raw).hexdigest() != CONFIG_SHA:
        raise ValueError("UNREGISTERED_CHAMPION_ENGINE_OR_CONFIGURATION")
    return json.loads(raw)["kellyPortfolio"]


def allocation(region, candidates, cfg, macro, names=None):
    """No region pooling, Kelly optimization, expected-return estimate or outcomes."""
    base = KP.selection_and_baseline(deepcopy(candidates), deepcopy(cfg), deepcopy(macro))
    lookup = {r["ticker"]: r for r in base["selected"]}
    ranking = {r["ticker"]: r for r in base["selection"]["ranking"]}
    weights = {t: w for t, w in base["weights"].items() if w > 0}
    if set(weights) & {"CASH", W.BENCHMARKS[region]}:
        raise ValueError("RESIDUAL_ASSET_IDENTITY_COLLISION")
    stock_total = sum(weights.values())
    residual = round(1.0 - stock_total, 6)
    if residual < 0 or any(not finite(w) or w < 0 for w in weights.values()):
        raise ValueError("INVALID_CHAMPION_ALLOCATION")
    holdings = [{"ticker": t, "name": (names or {}).get(t) or t,
                 "weightPct": round(w * 100, 6), "sector": lookup[t].get("sector"),
                 "alphaPercentile": lookup[t].get("alphaPercentile"),
                 "factorPercentiles": lookup[t].get("factorPercentiles"),
                 "convictionScore": ranking[t]["convictionScore"],
                 "downsideVolPct": ranking[t]["downsideVolPct"],
                 "evidenceCoverage": ranking[t]["evidenceCoverage"],
                 "entryState": (lookup[t].get("entry") or {}).get("entryState") or lookup[t].get("entryState"),
                 "reasonKo": "팩터 conviction 순위·하방 위험·상태 배율 및 원래 집중도/현금 제약으로 선정"}
                for t, w in weights.items() if w > 0]
    status = "STOCKS_SELECTED" if holdings else "NO_ELIGIBLE_STOCKS"
    common = {"status": status, "currency": W.CURRENCY[region], "stockCount": len(holdings), "holdings": holdings,
              "stockWeights": weights, "stockWeightPct": round(stock_total * 100, 6),
              "residualWeightPct": round(residual * 100, 6), "totalWeightPct": 100.0,
              "selection": base["selection"], "appliedMinCashPct": base["appliedMinCashPct"],
              "macroWarnings": base["macroWarnings"], "scoreMeaningKo": base["selection"]["notAForecastKo"]}
    c1 = {**deepcopy(common), "strategy": "C1", "weights": {**weights, "CASH": residual},
          "residualAsset": "CASH"}
    c2 = {**deepcopy(common), "strategy": "C2", "weights": {**weights, W.BENCHMARKS[region]: residual},
          "residualAsset": W.BENCHMARKS[region]}
    return {"C1": c1, "C2": c2}


def _safety_reason(site):
    mode = (site.get("provenance") or {}).get("dataMode") or site.get("dataMode")
    if (mode != "live" or any(site.get(k) for k in ("seed", "synthetic", "stale", "recommendationsBlocked"))
            or (site.get("meta") or {}).get("syntheticData")):
        return "UNSAFE_OR_NON_LIVE_SOURCE"
    if (site.get("longTerm") or {}).get("weightsWithheld") is not False:
        return "LONG_TERM_INPUTS_WITHHELD"
    return None


def build(site, source_sha256):
    if len(source_sha256) != 64 or any(c not in "0123456789abcdef" for c in source_sha256):
        raise ValueError("INVALID_SOURCE_ARTIFACT_DIGEST")
    now = datetime.fromisoformat(str(site["generatedAt"]).replace("Z", "+00:00"))
    if now.tzinfo is None:
        raise ValueError("SOURCE_OBSERVATION_TIME_REQUIRES_TIMEZONE")
    cfg = methodology()
    unsafe = _safety_reason(site)
    by_symbol = {r.get("symbol"): r for r in site.get("indices") or []}
    out = {"schema": ARTIFACT, "version": VERSION, "generatedAt": site["generatedAt"],
           "liveValidated": False, "evidenceClass": EVIDENCE, "regions": {},
           "sourceArtifactSha256": source_sha256}
    for region in W.BENCHMARKS:
        row = {"region": region, "status": "BLOCKED", "reasonCodes": [], "receiptId": None,
               "asOfDate": None, "decisions": {}, "liveValidated": False, "evidenceClass": EVIDENCE}
        out["regions"][region] = row
        tape = by_symbol.get(W.SESSION_EVIDENCE[region]) or {}
        try:
            fresh = W.freshness(region, tape.get("asOf"), now)
        except (ValueError, TypeError):
            row["reasonCodes"] = ["INVALID_REGIONAL_SESSION"]
            continue
        row.update(asOfDate=fresh["expectedSession"], freshness=fresh, sourceObservedDate=tape.get("asOf"))
        reasons = row["reasonCodes"]
        if unsafe:
            reasons.append(unsafe)
        if fresh["observedSession"] != fresh["expectedSession"] or tape.get("freshnessStatus") != "CURRENT":
            reasons.append("REGIONAL_INDEX_NOT_CURRENT")
        region_blob = ((site.get("longTerm") or {}).get("regions") or {}).get(region)
        candidates = (region_blob or {}).get("picks")
        if not isinstance(candidates, list):
            reasons.append("REGIONAL_CHAMPION_CANDIDATE_POOL_MISSING")
            candidates = []
        elif not candidates:
            reasons.append("REGIONAL_CHAMPION_CANDIDATE_POOL_EMPTY")
        if any(not isinstance(r, dict) for r in candidates):
            reasons.append("INVALID_CANDIDATE_ROW")
            continue
        if len({r.get("ticker") for r in candidates}) != len(candidates):
            reasons.append("DUPLICATE_CANDIDATE")
        for candidate in candidates:
            ticker = candidate.get("ticker")
            if ticker in {"CASH", W.BENCHMARKS[region]}:
                reasons.append("RESIDUAL_ASSET_IDENTITY_COLLISION:" + ticker)
            risk = candidate.get("risk") or {}
            detail = (site.get("details") or {}).get(ticker) or {}
            if (not ticker or candidate.get("region") != region
                    or not finite(candidate.get("alphaPercentile"))
                    or not 0 <= candidate["alphaPercentile"] <= 100
                    or not finite(candidate.get("evidenceCoverage"))
                    or not 0 <= candidate["evidenceCoverage"] <= 1
                    or not finite(risk.get("downsideVolPct")) or risk["downsideVolPct"] <= 0
                    or not candidate.get("longTermResearchView")
                    or not ((candidate.get("entry") or {}).get("entryState") or candidate.get("entryState"))):
                reasons.append("INCOMPLETE_CANDIDATE:" + str(ticker))
            asof = detail.get("asOf")
            try:
                dated = W.session_on_or_before(region, asof) if asof else None
            except (ValueError, TypeError):
                dated = None
            if dated != fresh["expectedSession"]:
                reasons.append("CANDIDATE_SESSION_NOT_CURRENT:" + str(ticker))
        regime = site.get("macroRegime") or {}
        budget = (regime.get("riskBudget") or {}).get("equityRangePct") if isinstance(regime, dict) else None
        if (not isinstance(regime, dict) or not regime.get("regime")
                or not finite(regime.get("confidence")) or not 0 <= regime["confidence"] <= 1
                or not isinstance(budget, list) or len(budget) != 2
                or not all(finite(v) for v in budget) or not 0 <= budget[0] <= budget[1] <= 100):
            reasons.append("MACRO_RISK_CONTEXT_MISSING")
        if reasons:
            continue
        macro = {k: site["macroRegime"].get(k) for k in ("regime", "confidence", "riskBudget")}
        inputs = {"region": region, "asOfDate": row["asOfDate"], "candidates": candidates,
                  "macro": macro, "configuration": cfg}
        record = {"schema": SCHEMA, "version": VERSION, "region": region,
                  "receiptId": f"{VERSION}|{region}|{row['asOfDate']}",
                  "asOfDate": row["asOfDate"], "generatedAt": site["generatedAt"], "baseCurrency": W.CURRENCY[region],
                  "liveValidated": False, "evidenceClass": EVIDENCE,
                  "cadence": "CURRENT_SESSION_OBSERVATION_NOT_21_SESSION_EXECUTION_SEQUENCE",
                  "inputs": {"regionalSha256": digest(inputs), "sourceArtifactSha256": source_sha256,
                             "configurationSha256": digest(cfg), "engineSha256": ENGINE_SHA,
                             "buildCommitSha": (site.get("provenance") or {}).get("buildCommitSha")},
                  "limitations": LIMITATIONS,
                  "decisions": allocation(region, candidates, cfg, macro, site.get("names"))}
        record["digest"] = receipt_digest(record)
        row.update(status="READY", receiptId=record["receiptId"], digest=record["digest"],
                   decisions=record["decisions"], receipt=record)
    return out


def publish(site, source_sha256, directory):
    """Separate append-only store staged by the existing ledger workflow.

    Never opens/writes the official weekly receipts, historical returns or locks.
    A changed same-session input blocks this region rather than rewriting history.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "receipts.jsonl"
    existing = [json.loads(s) for s in path.read_text().splitlines() if s.strip()] if path.exists() else []
    ids = {}
    for record in existing:
        if (record.get("schema") != SCHEMA or record.get("version") != VERSION
                or record.get("region") not in W.BENCHMARKS
                or record.get("receiptId") != f"{VERSION}|{record.get('region')}|{record.get('asOfDate')}"
                or record.get("liveValidated") is not False or record.get("evidenceClass") != EVIDENCE
                or record.get("digest") != receipt_digest(record) or record["receiptId"] in ids):
            raise ValueError("INVALID_RESEARCH_RECEIPT_HISTORY")
        ids[record["receiptId"]] = record
    block = build(site, source_sha256)
    additions = []
    for region, blob in block["regions"].items():
        record = blob.pop("receipt", None)
        if record is None:
            continue
        prior = ids.get(record["receiptId"])
        if prior:
            if prior["inputs"]["regionalSha256"] != record["inputs"]["regionalSha256"]:
                blob.update(status="BLOCKED", reasonCodes=["CONFLICTING_SAME_SESSION_INPUT"],
                            decisions={}, receiptId=None, digest=None)
                continue
            record = prior
        else:
            earlier = [r for r in existing if r["region"] == region and r["asOfDate"] < record["asOfDate"]]
            if earlier:
                old = max(earlier, key=lambda r: r["asOfDate"])
                before, after = old["decisions"]["C1"]["stockWeights"], record["decisions"]["C1"]["stockWeights"]
                record["previousObservationChange"] = {"priorAsOfDate": old["asOfDate"],
                    "added": sorted(set(after) - set(before)), "removed": sorted(set(before) - set(after)),
                    "weightChangesPct": {t: round((after.get(t, 0) - before.get(t, 0)) * 100, 6)
                                        for t in sorted(set(before) | set(after))}}
            additions.append(record)
        blob.update(digest=record["digest"], decisions=record["decisions"],
                    publishedFrom="RECORDED_RESEARCH_RECEIPT")
    # Preserve every existing line's exact bytes, including key order/number tokens.
    if additions:
        with path.open("ab") as stream:
            if path.stat().st_size and not path.read_bytes().endswith(b"\n"):
                stream.write(b"\n")
            for record in additions:
                stream.write(canonical(record) + b"\n")
    for name, payload in (("latest.json", block), ("publication-status.json", {
        "schema": PUBLICATION, "status": "PUBLISHED", "generatedAt": site["generatedAt"],
        "sourceArtifactSha256": source_sha256, "liveValidated": False})):
        (directory / name).write_bytes(canonical(payload) + b"\n")
    return block
