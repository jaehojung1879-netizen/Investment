"""Stage 2 of protocol v2: the point-in-time evidence packet and its review request.

Reuses evidence.py's receipt reading, candidate rows, gates and raw-store fetch (v1 code is
kept unchanged so the 2026-11 pack stays reproducible) and replaces only the market/macro
layers with release-time-filtered versions. Every number carries the observation date and
the UTC time it became public.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import availability as A
import evidence as E

HERE = Path(__file__).resolve().parent
PROTOCOL_V2 = HERE / "protocol-v2.json"
REVIEWERS = HERE / "reviewers.json"
COHORTS = HERE / "cohorts"
US_MACRO = ("GLD", "UUP", "IEF")
FRED = ("DGS10", "DGS3MO", "VIXCLS", "DEXKOUS", "T10YIE")


def iso(t: pd.Timestamp) -> str:
    return pd.Timestamp(t).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def raw_close(store: Path, sym: str) -> pd.Series:
    name = "yahoo_" + sym.replace("^", "").replace("=", "_") + ".json.gz"
    res = json.loads(gzip.decompress((store / name).read_bytes()))["chart"]["result"][0]
    tz = res["meta"].get("exchangeTimezoneName", "UTC")
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(tz).normalize().tz_localize(None)
    s = pd.Series(res["indicators"]["quote"][0]["close"], index=idx, dtype=float).dropna()
    s = s[~s.index.duplicated(keep="last")]
    splits = {}
    for item in (res.get("events") or {}).get("splits", {}).values():
        d = pd.Timestamp(item["date"], unit="s", tz="UTC").tz_convert(tz).normalize().tz_localize(None)
        splits[d] = float(item["numerator"]) / float(item["denominator"])
    s.attrs["splits"] = splits  # undone after the cutoff by availability.available_closes
    return s


def raw_fred(store: Path, series: str) -> pd.Series:
    text = gzip.decompress((store / f"fred_{series}.csv.gz").read_bytes()).decode()
    rows = [line.split(",") for line in text.strip().splitlines()[1:]]
    return pd.Series({pd.Timestamp(d): float(v) for d, v in rows if v not in ("", ".")}).sort_index()


def _obs(series: pd.Series, i: int, avail) -> dict:
    d = series.index[i]
    return {"value": float(series.iloc[i]), "obsDate": str(d.date()), "availableAtUtc": iso(avail(d))}


def market_layer(store: Path, region: str, cutoff: pd.Timestamp) -> dict:
    sym = "SPY" if region == "US" else "^KS11"
    s = A.available_closes(region, raw_close(store, sym), cutoff)
    r = s.pct_change().dropna()

    def avail(d):
        return A.exchange_close_utc(region, d)
    out = {"index": sym, "last": _obs(s, -1, avail), "aboveMA200": bool(s.iloc[-1] > s.iloc[-200:].mean()),
           "return63Pct": float((s.iloc[-1] / s.iloc[-64] - 1) * 100),
           "return252Pct": float((s.iloc[-1] / s.iloc[-253] - 1) * 100) if len(s) > 253 else None,
           "vol63Pct": float(r.iloc[-63:].std() * np.sqrt(252) * 100),
           "drawdownFrom252HighPct": float((s.iloc[-1] / s.iloc[-252:].max() - 1) * 100)}
    if region == "US":
        q = A.available_closes("US", raw_close(store, "QQQ"), cutoff)
        out["qqqMinusSpy63Pp"] = float(((q.iloc[-1] / q.iloc[-64]) - (s.iloc[-1] / s.iloc[-64])) * 100)
    return out


def macro_layer(store: Path, region: str, cutoff: pd.Timestamp) -> dict:
    f = {k: A.available_fred(k, raw_fred(store, k), cutoff) for k in FRED}

    def obs(k):
        return _obs(f[k], -1, lambda d, k=k: A.release_utc(k, d))

    def chg(k, n=63):
        return float(f[k].iloc[-1] - f[k].iloc[-1 - n]) if len(f[k]) > n else None
    out = {"y10": obs("DGS10"), "dY10_63": chg("DGS10"),
           "curve10y3m": float(f["DGS10"].iloc[-1] - f["DGS3MO"].iloc[-1]), "vix": obs("VIXCLS"),
           "breakeven10": obs("T10YIE"), "dBreakeven63": chg("T10YIE")}
    for sym in US_MACRO:
        s = A.available_closes("US", raw_close(store, sym), cutoff)
        out[f"{sym.lower()}Return126"] = {"pct": float((s.iloc[-1] / s.iloc[-127] - 1) * 100),
                                         "lastSession": str(s.index[-1].date()),
                                         "availableAtUtc": iso(A.exchange_close_utc("US", s.index[-1]))}
    if region == "KR":
        out["usdkrwH10"] = obs("DEXKOUS")
        out["usdkrwH10Change63Pct"] = float((f["DEXKOUS"].iloc[-1] / f["DEXKOUS"].iloc[-64] - 1) * 100)
    out["excluded"] = {"KRW=X": "FX_VENDOR: no verifiable bar close time"}
    return out


def execution_schedule(region: str, sealed_at: pd.Timestamp, window_hours: int) -> dict:
    cal = A.calendar(region)
    earliest = sealed_at + pd.Timedelta(hours=window_hours)
    for s in cal.sessions_in_range((earliest - pd.Timedelta(days=1)).tz_localize(None).normalize(),
                                   (earliest + pd.Timedelta(days=14)).tz_localize(None).normalize()):
        if pd.Timestamp(cal.session_open(s)) >= earliest:
            return {"plannedExecution": str(pd.Timestamp(s).date()),
                    "registrationDeadlineUtc": iso(cal.session_open(s)),
                    "plannedExecutionCloseUtc": iso(cal.session_close(s))}
    raise RuntimeError("NO_EXECUTION_SESSION")


def build_packet(signal_commit: str, month: str, store: Path, sealed_at: pd.Timestamp, protocol_sha: str) -> dict:
    rec = E.cohort_receipts(signal_commit, month)
    window = json.loads(PROTOCOL_V2.read_text())["schedule"]["reviewWindowHours"]
    regions = {}
    for region, r in sorted(rec["regions"].items()):
        cutoff = A.cutoff_utc(region, r["asOfDate"])
        rows = E.candidate_rows(r)
        for row in rows:
            row["gatesFailed"] = E.gates(row, r["freshness"], cutoff)
        regions[region] = {
            "receiptId": r["receiptId"], "receiptDigest": r["digest"], "asOfDate": r["asOfDate"],
            "informationCutoffUtc": iso(cutoff), "receiptGeneratedAt": r["generatedAt"],
            "productionStatus": r["status"], "productionWeights": r["weights"], "noTradeReason": r.get("noTradeReason"),
            "fundamentalPublicationTimes": {"stated": sum(any((x.get("valuationProfitability") or {}).get(k) for k in E.PUBLICATION_KEYS) for x in rows),
                                            "notStated": sum(not any((x.get("valuationProfitability") or {}).get(k) for k in E.PUBLICATION_KEYS) for x in rows),
                                            "note": "a receipt that states no publication time is not evidence the fundamentals were public at the cutoff (activation gate G2)"},
            "calibrationOrdering": r.get("calibrationOrdering"), "costs": r["costs"], "freshness": r["freshness"],
            "modelVersion": r["inputs"]["modelVersion"], "siteDataSha256": r["inputs"]["siteDataSha256"],
            "market": market_layer(store, region, cutoff), "macro": macro_layer(store, region, cutoff),
            "candidates": rows, "gatePassers": [c["ticker"] for c in rows if not c["gatesFailed"]],
            "schedule": execution_schedule(region, sealed_at, window),
        }
        if pd.Timestamp(r["generatedAt"]) > sealed_at:
            raise RuntimeError("RECEIPT_GENERATED_AFTER_PACKET")
    return {"schema": "DECISION_DESK_EVIDENCE_PACKET_V2", "cohort": month, "protocolV2Sha256": protocol_sha,
            "sealedAtUtc": iso(sealed_at), "signalHistoryCommit": signal_commit, "receiptsBlob": rec["receiptsBlob"],
            "receiptsSha256": rec["receiptsSha256"],
            "marketManifestSha256": hashlib.sha256((store / "manifest.json").read_bytes()).hexdigest(),
            "availabilityRules": A.SOURCE_EVIDENCE, "regions": regions}


def review_request(packet: dict, packet_sha: str) -> dict:
    reg = json.loads(REVIEWERS.read_text())
    enabled = [r for r in reg["reviewers"] if r["status"] == "ENABLED"]
    return {"schema": "B2_REVIEW_REQUEST_V1", "cohort": packet["cohort"], "status": "AI_REVIEW_REQUIRED",
            "packetSha256": packet_sha,
            "deadlinesUtc": {r: v["schedule"]["registrationDeadlineUtc"] for r, v in packet["regions"].items()},
            "requiredReviewers": [r["id"] for r in enabled if r["role"] == "PRIMARY_B2"],
            "optionalComparisonReviewers": [r["id"] for r in enabled if r["role"] == "COMPARISON_ARM"],
            "pendingApprovalReviewers": [r["id"] for r in reg["reviewers"] if r["status"] != "ENABLED"],
            "whyNotAutomatic": reg["automation"],
            "namesToReview": {r: v["gatePassers"] for r, v in packet["regions"].items()},
            "steps": [
                f"python research/decision_desk_v1/desk.py review-template --month {packet['cohort']} --reviewer <id>",
                "fill labels and interpretation for every gate passer from the packet alone (no other sources after the cutoff)",
                f"python research/decision_desk_v1/desk.py commit-review --month {packet['cohort']} --reviewer <id>  # writes the commitment; commit it first",
                "commit the review file in a later commit, before the earliest deadline",
                f"python research/decision_desk_v1/desk.py decide --month {packet['cohort']}"]}


def write_packet(signal_commit: str, month: str, fetch: bool, now: pd.Timestamp | None = None) -> tuple[Path, dict]:
    protocol_sha = hashlib.sha256(PROTOCOL_V2.read_bytes()).hexdigest()
    out_dir = COHORTS / month
    if (out_dir / "evidence-packet.json").exists():
        raise RuntimeError("PACKET_ALREADY_EXISTS: a sealed packet is never regenerated")
    store = out_dir / "market"
    now = now or pd.Timestamp(dt.datetime.now(dt.timezone.utc))
    if fetch:
        rec = E.cohort_receipts(signal_commit, month)
        E.fetch_market(store, max(r["asOfDate"] for r in rec["regions"].values()))
    pk = build_packet(signal_commit, month, store, now, protocol_sha)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "evidence-packet.json"
    path.write_text(json.dumps(pk, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    (out_dir / "review-request.json").write_text(json.dumps(review_request(pk, sha), indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return path, pk
