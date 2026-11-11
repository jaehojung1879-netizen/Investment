"""Evidence packs for decision-desk-v1 cohorts.

Reads (never writes) the production weekly receipts on signal-history at a pinned
commit, verifies each receipt digest with production's own function, fetches dated
market/macro observations truncated at the cohort cutoff, and evaluates the frozen
B2 gates. Nothing here fits a model, selects a weight or reads a forward return.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import weekly_decision as W  # noqa: E402  (read-only reuse of the production digest)

PROTOCOL = json.loads((HERE / "protocol.json").read_text())
RECEIPTS_PATH = "ledger/weekly-decisions/receipts.jsonl"
UA = "Mozilla/5.0 (research fetch; decision-desk-v1)"
MARKET_SYMBOLS = {"US": ["SPY", "QQQ", "IEF", "GLD", "UUP"], "KR": ["069500.KS", "^KS11", "KRW=X"]}
FRED_SERIES = ["DGS10", "DGS3MO", "VIXCLS", "DEXKOUS", "T10YIE"]
FINANCIAL_SECTORS = {"Financial Services", "Real Estate", "Utilities"}


# ----------------------------------------------------------------------------- receipts
def git_bytes(commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)


def git_blob(commit: str, path: str) -> str:
    return subprocess.check_output(["git", "rev-parse", f"{commit}:{path}"], cwd=ROOT, text=True).strip()


def cohort_receipts(signal_commit: str, month: str) -> dict:
    """First FINAL_WEEKLY receipt per region whose asOfDate is in `month` (YYYY-MM)."""
    raw = git_bytes(signal_commit, RECEIPTS_PATH)
    out = {}
    for line in raw.decode().splitlines():
        r = json.loads(line)
        if r.get("weekStatus") != "FINAL_WEEKLY" or not r["asOfDate"].startswith(month):
            continue
        if W.receipt_digest(r) != r["digest"]:
            raise RuntimeError(f"RECEIPT_DIGEST_MISMATCH {r['receiptId']}")
        if r["region"] not in out or r["asOfDate"] < out[r["region"]]["asOfDate"]:
            out[r["region"]] = r
    return {"signalHistoryCommit": signal_commit, "receiptsBlob": git_blob(signal_commit, RECEIPTS_PATH),
            "receiptsSha256": hashlib.sha256(raw).hexdigest(), "regions": out}


def candidate_rows(receipt: dict) -> list[dict]:
    """Union of the receipt's candidates and watchlist, one row per ticker, fields as published."""
    rows: dict[str, dict] = {}
    for w in receipt.get("watchlist", []):
        rows[w["ticker"]] = {"source": "watchlist", **w}
    for c in receipt.get("candidates", []):
        base = rows.setdefault(c["ticker"], {"source": "candidates"})
        for k, v in c.items():
            base.setdefault(k, v)
        if base["source"] == "watchlist":
            base["source"] = "watchlist+candidates"
    return sorted(rows.values(), key=lambda r: (-r.get("alphaPercentile", 0), r["ticker"]))


# ----------------------------------------------------------------------------- gates
def gates(row: dict, freshness: dict) -> list[str]:
    failed = []
    cov = row.get("coverage") or {}
    if freshness.get("status") != "FRESH" or cov.get("dataCompleteness") is None or cov["dataCompleteness"] < 0.75 \
            or (cov.get("sleevesPresent") or 0) < 3:
        failed.append("G1_DATA")
    if row.get("entryState") == "AVOID":
        failed.append("G2_ENTRY")
    pm = row.get("priceMomentum") or {}
    if pm.get("aboveMA200") is False and (pm.get("mom63Pct") is not None and pm["mom63Pct"] < 0):
        failed.append("G3_FALLING_PRICE")
    lr = row.get("liquidityRisk") or {}
    if lr.get("maxDD252Pct") is None or lr.get("vol252Pct") is None or lr["maxDD252Pct"] <= -50 or lr["vol252Pct"] >= 60:
        failed.append("G4_RISK")
    vp = row.get("valuationProfitability") or {}
    if row.get("sector") not in FINANCIAL_SECTORS and (vp.get("debtToEquity") is None or vp["debtToEquity"] >= 200):
        failed.append("G5_LEVERAGE")
    return failed


# ----------------------------------------------------------------------------- market / macro
def _get(url: str) -> bytes:
    last = None
    for i in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
            if body:
                return body
        except Exception as exc:  # proxy / vendor flakiness
            last = exc
        time.sleep(10 * (i + 1))
    raise RuntimeError(f"FETCH_FAILED {url}: {last!r}")


def fetch_market(store: Path, cutoff: str) -> dict:
    """Fetch and freeze raw market/macro bytes; returns manifest (sha256 of each raw body)."""
    store.mkdir(parents=True, exist_ok=True)
    end = int(dt.datetime.fromisoformat(cutoff).replace(tzinfo=dt.timezone.utc).timestamp()) + 2 * 86400
    manifest = {"fetchedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "cutoff": cutoff, "files": {}}
    jobs = [(s, "https://query2.finance.yahoo.com/v8/finance/chart/" + urllib.request.quote(s)
             + f"?period1={end - 420 * 86400}&period2={end}&interval=1d&events=div%2Csplit") for r in MARKET_SYMBOLS for s in MARKET_SYMBOLS[r]]
    jobs += [(s, f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}&cosd=2025-01-01") for s in FRED_SERIES]
    for sym, url in jobs:
        body = _get(url)
        name = ("yahoo_" if "yahoo" in url else "fred_") + sym.replace("^", "").replace("=", "_") + (".json.gz" if "yahoo" in url else ".csv.gz")
        (store / name).write_bytes(gzip.compress(body, mtime=0))
        manifest["files"][name] = {"url": url, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        time.sleep(6)
    (store / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest


def load_close(store: Path, sym: str, cutoff: str) -> pd.Series:
    name = "yahoo_" + sym.replace("^", "").replace("=", "_") + ".json.gz"
    res = json.loads(gzip.decompress((store / name).read_bytes()))["chart"]["result"][0]
    tz = res["meta"].get("exchangeTimezoneName", "UTC")
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(tz).normalize().tz_localize(None)
    s = pd.Series(res["indicators"]["quote"][0]["close"], index=idx, dtype=float).dropna()
    s = s[~s.index.duplicated(keep="last")]
    return s.loc[:cutoff]


def load_fred(store: Path, series: str, cutoff: str) -> pd.Series:
    text = gzip.decompress((store / f"fred_{series}.csv.gz").read_bytes()).decode()
    rows = [line.split(",") for line in text.strip().splitlines()[1:]]
    s = pd.Series({pd.Timestamp(d): float(v) for d, v in rows if v not in ("", ".")}).sort_index()
    return s.loc[: pd.Timestamp(cutoff) - pd.Timedelta(days=1)]  # one-day publication lag, as in us-macro-cocktail-v1


def market_layer(store: Path, region: str, cutoff: str) -> dict:
    idx_sym = "SPY" if region == "US" else "^KS11"
    s = load_close(store, idx_sym, cutoff)
    r = s.pct_change().dropna()
    out = {"index": idx_sym, "lastSession": str(s.index[-1].date()), "close": float(s.iloc[-1]),
           "aboveMA200": bool(s.iloc[-1] > s.iloc[-200:].mean()),
           "return252Pct": float((s.iloc[-1] / s.iloc[-253] - 1) * 100) if len(s) > 253 else None,
           "return63Pct": float((s.iloc[-1] / s.iloc[-64] - 1) * 100),
           "vol63Pct": float(r.iloc[-63:].std() * np.sqrt(252) * 100),
           "drawdownFrom252HighPct": float((s.iloc[-1] / s.iloc[-252:].max() - 1) * 100)}
    if region == "US":
        q = load_close(store, "QQQ", cutoff)
        out["qqqMinusSpy63Pp"] = float(((q.iloc[-1] / q.iloc[-64]) - (s.iloc[-1] / s.iloc[-64])) * 100)
    return out


def macro_layer(store: Path, region: str, cutoff: str) -> dict:
    f = {k: load_fred(store, k, cutoff) for k in FRED_SERIES}

    def chg(series, n=63):
        return float(series.iloc[-1] - series.iloc[-1 - n]) if len(series) > n else None
    out = {"fredValuesDatedBefore": cutoff, "y10": float(f["DGS10"].iloc[-1]), "dY10_63": chg(f["DGS10"]),
           "curve10y3m": float(f["DGS10"].iloc[-1] - f["DGS3MO"].iloc[-1]), "vix": float(f["VIXCLS"].iloc[-1]),
           "breakeven10": float(f["T10YIE"].iloc[-1]), "dBreakeven63": chg(f["T10YIE"])}
    for sym in ("GLD", "UUP", "IEF"):
        s = load_close(store, sym, cutoff)
        out[f"{sym.lower()}Return126Pct"] = float((s.iloc[-1] / s.iloc[-127] - 1) * 100)
    if region == "KR":
        fx = f["DEXKOUS"]
        out["usdkrwH10LastObservation"] = {"date": str(fx.index[-1].date()), "value": float(fx.iloc[-1]),
                                           "note": "H.10 publishes weekly; an observation is usable only after its Monday release"}
        k = load_close(store, "KRW=X", cutoff)
        out["usdkrwVendorChange63Pct"] = float((k.iloc[-1] / k.iloc[-64] - 1) * 100)
    return out


def evidence_pack(signal_commit: str, month: str, store: Path) -> dict:
    rec = cohort_receipts(signal_commit, month)
    regions = {}
    for region, r in sorted(rec["regions"].items()):
        cutoff = r["asOfDate"]
        rows = candidate_rows(r)
        for row in rows:
            row["gatesFailed"] = gates(row, r["freshness"])
        regions[region] = {
            "receiptId": r["receiptId"], "receiptDigest": r["digest"], "asOfDate": cutoff,
            "receiptGeneratedAt": r["generatedAt"], "productionStatus": r["status"], "productionWeights": r["weights"],
            "noTradeReason": r.get("noTradeReason"), "calibrationOrdering": r.get("calibrationOrdering"),
            "costs": r["costs"], "freshness": r["freshness"], "modelVersion": r["inputs"]["modelVersion"],
            "siteDataSha256": r["inputs"]["siteDataSha256"], "market": market_layer(store, region, cutoff),
            "macro": macro_layer(store, region, cutoff), "candidates": rows,
        }
    manifest = json.loads((store / "manifest.json").read_text())
    return {"schema": "DECISION_DESK_EVIDENCE_PACK_V1", "cohort": month, "signalHistoryCommit": rec["signalHistoryCommit"],
            "receiptsBlob": rec["receiptsBlob"], "receiptsSha256": rec["receiptsSha256"],
            "marketManifestSha256": hashlib.sha256((store / "manifest.json").read_bytes()).hexdigest(),
            "marketFetchedAtUtc": manifest["fetchedAtUtc"], "regions": regions}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--signal-commit", required=True)
    ap.add_argument("--month", required=True)
    ap.add_argument("--fetch", action="store_true")
    a = ap.parse_args()
    store = HERE / "inputs" / a.month / "market"
    if a.fetch:
        rec = cohort_receipts(a.signal_commit, a.month)
        fetch_market(store, max(r["asOfDate"] for r in rec["regions"].values()))
    pack = evidence_pack(a.signal_commit, a.month, store)
    out = HERE / "inputs" / a.month / "evidence-pack.json"
    out.write_text(json.dumps(pack, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(out, hashlib.sha256(out.read_bytes()).hexdigest())
