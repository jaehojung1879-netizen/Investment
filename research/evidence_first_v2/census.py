"""Investable-universe census and the B1 academic screen, KR and US, at the latest data date.

python research/evidence_first_v2/census.py [--fetch-us-prices]

Reads git objects at a pinned signal-history commit (KRX universe and prices, PIT
fundamentals, production receipts) plus frozen US closes, and reports how many names
survive each stage and why the rest drop out. It computes no forward return, fits nothing
and selects nothing officially: the B1 screen is E1 (externally documented, not locally
replicated), so the official selection stays 0 names / ETF default.

Fundamentals are never derived a second time: KR reads pit-kr.jsonl as published; US runs
the repository's own scripts/build_pit_fundamentals.py over the raw Finnhub shards into a
temporary directory (its output hash is recorded).
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SIGNAL_COMMIT = "6398e94feddd4f552910d31b36bc8db0766576af"
AS_OF = {"KR": "2026-10-30", "US": "2026-11-10"}
US_PRICES = HERE / "data" / "us-prices"
OUT = HERE / "results" / "census.json"
KR_MIN_TRADED_VALUE = 1e9          # KRW, the repository's existing H2 liquidity floor
KR_LARGE_CAP_RANK = 150            # top half of the KRX top-300 snapshot
MAX_FILING_AGE_DAYS = 456          # 15 months
MAX_DEBT_TO_EQUITY = 2.0
PREFERRED = re.compile(r"(\d?우[A-Z]?|우\(.+\))$")
UA = "Mozilla/5.0 (research fetch; evidence-first-v2 census)"


def git_bytes(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{SIGNAL_COMMIT}:{path}"], cwd=ROOT)


def jsonl_gz(path: str) -> list[dict]:
    return [json.loads(x) for x in gzip.decompress(git_bytes(path)).decode().splitlines() if x.strip()]


def jsonl(path: str) -> list[dict]:
    return [json.loads(x) for x in git_bytes(path).decode().splitlines() if x.strip()]


# ----------------------------------------------------------------------------- fundamentals
FIELDS = ("roe", "operatingMargin", "debtToEquity", "bookValuePerShare")


def latest_filings(rows: list[dict], as_of: str) -> dict[str, dict]:
    """Field-wise point-in-time view: each field takes its latest value visible on the as-of date.

    A newer filing whose derivation is incomplete (e.g. a 10-Q without a balance sheet) does not erase
    an older visible value; each field records the filing it came from so staleness is checked per field.
    """
    by: dict[str, list[dict]] = {}
    for r in rows:
        if r["availableFrom"] <= as_of:
            by.setdefault(r["ticker"], []).append(r)
    out = {}
    for t, rs in by.items():
        rs.sort(key=lambda r: (r["availableFrom"], r["reportDate"]))
        fields, src = {}, {}
        for r in rs:
            for k in FIELDS:
                if r["fields"].get(k) is not None:
                    fields[k] = r["fields"][k]
                    src[k] = {"reportDate": r["reportDate"], "availableFrom": r["availableFrom"]}
        newest = rs[-1]
        out[t] = {"ticker": t, "fields": fields, "fieldSources": src, "reportDate": newest["reportDate"],
                  "availableFrom": newest["availableFrom"]}
    return out


def us_fundamentals() -> tuple[list[dict], str]:
    """Fresh PIT derivation with the repository's own builder (no second implementation)."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "us"
        store.mkdir()
        listing = subprocess.check_output(["git", "ls-tree", "--name-only", f"{SIGNAL_COMMIT}:ledger/fundamentals/us"], cwd=ROOT, text=True).split()
        for name in listing:
            if name.startswith("finnhub-") or name.startswith("shares"):
                (store / name).write_bytes(git_bytes(f"ledger/fundamentals/us/{name}"))
        out = Path(tmp) / "pit-us.jsonl"
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_pit_fundamentals.py"), str(store), "--region", "us",
                        "--output", str(out)], cwd=ROOT, check=True, capture_output=True)
        raw = out.read_bytes()
    return [json.loads(x) for x in raw.decode().splitlines() if x.strip()], hashlib.sha256(raw).hexdigest()


# ----------------------------------------------------------------------------- prices
def kr_prices(tickers: set[str]) -> dict[str, pd.DataFrame]:
    rows = []
    for y in (2024, 2025, 2026):
        rows += [r for r in jsonl_gz(f"ledger/prices/kr/krx-prices-{y}.jsonl.gz") if r["ticker"] in tickers]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return {t: g.set_index("date").sort_index() for t, g in df.groupby("ticker")}


def fetch_us_prices(tickers: list[str]) -> None:
    US_PRICES.mkdir(parents=True, exist_ok=True)
    man = {"fetchedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "batches": []}
    for i in range(0, len(tickers), 20):
        batch = tickers[i:i + 20]
        url = "https://query2.finance.yahoo.com/v7/finance/spark?symbols=" + ",".join(batch) + "&range=2y&interval=1d"
        body = None
        for k in range(6):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
                    body = r.read()
                break
            except Exception:
                time.sleep(10 * (k + 1))
        name = f"spark-{i // 20:03d}.json.gz"
        if body is not None:
            (US_PRICES / name).write_bytes(gzip.compress(body, mtime=0))
        man["batches"].append({"file": name if body else None, "symbols": batch,
                               "sha256": hashlib.sha256(body).hexdigest() if body else None})
        time.sleep(3)
    (US_PRICES / "manifest.json").write_text(json.dumps(man, indent=1) + "\n")


def us_prices() -> dict[str, pd.Series]:
    man = json.loads((US_PRICES / "manifest.json").read_text())
    out = {}
    for b in man["batches"]:
        if not b["file"]:
            continue
        body = gzip.decompress((US_PRICES / b["file"]).read_bytes())
        if hashlib.sha256(body).hexdigest() != b["sha256"]:
            raise RuntimeError(f"US_PRICE_STORE_CHANGED {b['file']}")
        for res in json.loads(body)["spark"]["result"]:
            r = res["response"][0]
            if not r.get("timestamp"):
                continue
            idx = pd.to_datetime(r["timestamp"], unit="s", utc=True).tz_convert("America/New_York").normalize().tz_localize(None)
            s = pd.Series(r["indicators"]["quote"][0]["close"], index=idx, dtype=float).dropna()
            out[res["symbol"]] = s[~s.index.duplicated(keep="last")]
    return out


def momentum_12_2(close: pd.Series, as_of: str) -> float | None:
    s = close.loc[:as_of]
    if len(s) < 253:
        return None
    return float(s.iloc[-22] / s.iloc[-253] - 1)


# ----------------------------------------------------------------------------- census
def funnel_stage(counts: list, name: str, survivors: set, dropped: dict) -> set:
    counts.append({"stage": name, "remaining": len(survivors), "dropped": {k: len(v) for k, v in dropped.items() if v}})
    return survivors


def b1_screen(rows: dict[str, dict], large: set[str]) -> dict:
    """B1_PROFITABILITY_V1 — fixed before any forward return is observed (there is none yet).
    Large caps among factor-complete names, operating margin > 0, debt/equity <= 2, ranked by ROE
    (the available PIT proxy for operating profitability; gross profits / assets is not derived)."""
    elig = {t: r for t, r in rows.items() if t in large and r["operatingMargin"] > 0 and r["debtToEquity"] <= MAX_DEBT_TO_EQUITY}
    ranked = sorted(elig, key=lambda t: (-elig[t]["roe"], t))
    q = max(1, len(ranked) // 5)
    return {"eligible": len(elig), "topQuintile": ranked[:q], "deepReview": ranked[:5]}


def census_region(region: str, members: dict[str, dict], prices, fund: dict[str, dict], production: dict) -> dict:
    as_of = AS_OF[region]
    counts: list = []
    names = {t: m.get("name", t) for t, m in members.items()}
    s = funnel_stage(counts, "0 원래 유니버스", set(members), {})
    drop = {"PREFERRED_OR_NON_COMMON": {t for t in s if region == "KR" and PREFERRED.search(names[t] or "")}}
    s = funnel_stage(counts, "1 상장·보통주 신원", s - set().union(*drop.values()), drop)
    drop = {"NO_CLOSE_ON_AS_OF": set(), "ZERO_VOLUME_LAST_20": set(), "LOW_TRADED_VALUE": set()}
    for t in s:
        px = prices.get(t)
        if px is None or (pd.Timestamp(as_of) not in (px.index if isinstance(px, pd.Series) else px.index)):
            drop["NO_CLOSE_ON_AS_OF"].add(t)
            continue
        if region == "KR":
            last = px.loc[:as_of].tail(20)
            if (last["volume"] <= 0).any():
                drop["ZERO_VOLUME_LAST_20"].add(t)
            elif (last["close"] * last["volume"]).median() < KR_MIN_TRADED_VALUE:
                drop["LOW_TRADED_VALUE"].add(t)
    s = funnel_stage(counts, "2 매매 가능(가격·거래·유동성)", s - set().union(*drop.values()), drop)
    drop = {"PRICE_HISTORY_UNDER_252": set(), "CORPORATE_ACTION_UNRESOLVED": set()}
    closes, share_drift = {}, set()
    for t in s:
        px = prices[t]
        c = (px["close"] if region == "KR" else px).loc[:as_of]
        if len(c) < 253:
            drop["PRICE_HISTORY_UNDER_252"].add(t)
            continue
        if region == "KR":  # KRX closes are as traded: a one-day share-count jump can be a split the close does not adjust
            sh = px["listedShares"].loc[:as_of].tail(253)
            jump = np.abs(np.log(sh / sh.shift(1))).max()
            if jump >= np.log(1.2):
                drop["CORPORATE_ACTION_UNRESOLVED"].add(t)
                continue
            if sh.max() / sh.min() > 1.01:
                share_drift.add(t)
        closes[t] = c
    s = funnel_stage(counts, "3 가격 이력·기업행동", s - set().union(*drop.values()), drop)
    counts[-1]["kept_shareCountDriftOver1pct"] = len(share_drift)
    drop = {"NO_PIT_FILING": set(), "FILING_OLDER_THAN_15M": set(), "PROFITABILITY_MISSING": set(),
            "OPERATING_LINE_MISSING_ACCOUNTING_DEFINITION": set(), "BOOK_VALUE_OR_LEVERAGE_MISSING": set()}
    factor_rows = {}
    for t in s:
        f = fund.get(t)
        if f is None:
            drop["NO_PIT_FILING"].add(t)
            continue
        fl = {k: v for k, v in f["fields"].items()
              if (pd.Timestamp(as_of) - pd.Timestamp(f["fieldSources"][k]["reportDate"])).days <= MAX_FILING_AGE_DAYS}
        if not fl and f["fields"]:
            drop["FILING_OLDER_THAN_15M"].add(t)
            continue
        if fl.get("roe") is None:
            drop["PROFITABILITY_MISSING"].add(t)
            continue
        if fl.get("operatingMargin") is None:
            drop["OPERATING_LINE_MISSING_ACCOUNTING_DEFINITION"].add(t)
            continue
        if abs(fl["operatingMargin"]) > 1.0:  # added after inspection (SK Square 27.0): a data-validity rule, not a performance rule
            drop["OPERATING_LINE_MISSING_ACCOUNTING_DEFINITION"].add(t)
            continue
        if fl.get("bookValuePerShare") is None or fl.get("debtToEquity") is None:
            drop["BOOK_VALUE_OR_LEVERAGE_MISSING"].add(t)
            continue
        close = float(closes[t].iloc[-1])
        factor_rows[t] = {"roe": fl["roe"], "operatingMargin": fl["operatingMargin"], "debtToEquity": fl["debtToEquity"],
                          "bookToPrice": fl["bookValuePerShare"] / close, "momentum12_2": momentum_12_2(closes[t], as_of),
                          "roeFrom": f["fieldSources"]["roe"], "close": close}
    s = funnel_stage(counts, "4 PIT 재무 충족·팩터 계산 가능", set(factor_rows), drop)
    ages = [(pd.Timestamp(as_of) - pd.Timestamp(r["roeFrom"]["reportDate"])).days for r in factor_rows.values()]
    counts[-1]["profitabilityPeriodAgeDays"] = {"median": float(np.median(ages)) if ages else None, "max": max(ages) if ages else None}
    counts[-1]["rulesAddedAfterInspection"] = ["|operatingMargin| > 1 treated as an accounting-definition mismatch"]
    top = {}
    for fac, key in (("profitability(ROE)", "roe"), ("value(B/P)", "bookToPrice"), ("momentum(12-2)", "momentum12_2")):
        ranked = sorted(factor_rows, key=lambda t: (-factor_rows[t][key], t))
        top[fac] = ranked[: max(1, len(ranked) // 5)]
    counts.append({"stage": "5 (참고) 팩터별 상위 20% 합집합", "remaining": len(set().union(*top.values())),
                   "byFactor": {k: len(v) for k, v in top.items()}})
    large = ({t for t in factor_rows if members[t].get("rank", 999) <= KR_LARGE_CAP_RANK} if region == "KR" else set(factor_rows))
    b1 = b1_screen(factor_rows, large)
    counts.append({"stage": "6 B1 적격: 4단계 중 대형주·영업이익률>0·부채/자본≤2", "remaining": b1["eligible"],
                   "topQuintile": len(b1["topQuintile"])})
    counts.append({"stage": "7 기업 심층검토 대상(B1 상위 5)", "remaining": len(b1["deepReview"])})
    counts.append({"stage": "8 최종 연구용 선정", "remaining": 0,
                   "reason": "B1 is E1 (externally documented, not locally replicated); no path reaches E2, so the official choice is ETF_DEFAULT"})
    prod = set(production["tickers"])
    b1set = set(b1["topQuintile"])
    stage_of = {}
    for t in sorted(prod):
        stage_of[t] = ("FACTOR_COMPLETE" if t in factor_rows else "DROPPED_BEFORE_FACTORS")
    return {
        "asOf": as_of, "funnel": counts,
        "b1": {"rule": b1_screen.__doc__.strip(), "topQuintile": [{"ticker": t, "name": names.get(t), **{k: round(v, 4) if isinstance(v, float) else v for k, v in factor_rows[t].items()}} for t in b1["topQuintile"]],
               "deepReview": b1["deepReview"]},
        "factorTopQuintile": top,
        "productionComparison": {"productionReceipt": production["receiptId"], "productionTickers": sorted(prod),
                                 "onlyProduction": sorted(prod - b1set), "onlyB1": sorted(b1set - prod), "both": sorted(prod & b1set),
                                 "productionNameStatus": stage_of,
                                 "note": "Production ranks a four-factor composite (value, momentum, quality, low-vol) and blocks every name because its ordering is not established; B1 ranks one documented signal. Disagreement is expected and is information about the screens, not about returns."},
    }


def production_names() -> dict:
    rows = jsonl("ledger/weekly-decisions/receipts.jsonl")
    out = {}
    for r in rows:
        if r["weekStatus"] != "FINAL_WEEKLY":
            continue
        cur = out.get(r["region"])
        if cur is None or r["asOfDate"] > cur["asOfDate"]:
            out[r["region"]] = r
    return {g: {"receiptId": r["receiptId"], "tickers": sorted({c["ticker"] for c in r.get("candidates", [])} | {w["ticker"] for w in r.get("watchlist", [])})}
            for g, r in out.items()}


def run(fetch_prices: bool = False) -> dict:
    prod = production_names()
    # KR
    uni = [r for r in jsonl_gz("ledger/universe/kr/krx-universe-2026.jsonl.gz") if r["date"] < AS_OF["KR"]]
    snap = max(r["date"] for r in uni)
    kr_members = {r["ticker"]: r for r in uni if r["date"] == snap}
    kr_fund = latest_filings(jsonl("ledger/fundamentals/pit-kr.jsonl"), AS_OF["KR"])
    kr = census_region("KR", kr_members, kr_prices(set(kr_members)), kr_fund, prod["KR"])
    kr["universeSource"] = f"KRX market-cap snapshot {snap} (top 300; strictly before the as-of date)"
    # US
    hist = json.loads((ROOT / "data" / "universe-history.json").read_text())
    us_members = {t: {"name": t} for t, v in hist.items() if v["delisted"] is None and v["region"] == "US"}
    if fetch_prices:
        fetch_us_prices(sorted(us_members))
    us_rows, us_sha = us_fundamentals()
    us = census_region("US", us_members, us_prices(), latest_filings(us_rows, AS_OF["US"]), prod["US"])
    us["universeSource"] = "data/universe-history.json current S&P 500 members (last membership change recorded 2026-08-19); current survivors only"
    us["volumeNotChecked"] = "Yahoo batch closes carry no volume; S&P 500 membership is taken as the liquidity screen"
    us["fundamentalsDerivation"] = {"script": "scripts/build_pit_fundamentals.py --region us", "outputSha256": us_sha}
    return {"schema": "UNIVERSE_CENSUS_V1", "signalHistoryCommit": SIGNAL_COMMIT,
            "usPriceManifestSha256": hashlib.sha256((US_PRICES / "manifest.json").read_bytes()).hexdigest(),
            "regions": {"KR": kr, "US": us},
            "survivorshipStatement": "The US census lists today's members only. It supports a current screen, never a historical performance claim."}


if __name__ == "__main__":
    res = run("--fetch-us-prices" in sys.argv)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False, sort_keys=True, default=float) + "\n")
    for g, v in res["regions"].items():
        print("==", g, v["asOf"])
        for c in v["funnel"]:
            print("  ", c)
        print("   B1 deep review:", v["b1"]["deepReview"])
        pc = v["productionComparison"]
        print("   production only", len(pc["onlyProduction"]), "B1 only", len(pc["onlyB1"]), "both", pc["both"])
