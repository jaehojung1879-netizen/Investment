"""Stage 6: score matured horizons from executable closes, distributions and costs.

Entry is the close of plannedExecution (the closing auction), exit the close of the 126th or
252nd regional session after it. Total return reinvests each cash distribution at its
ex-date close. A window that cannot be verified is SOURCE_BLOCKED, never 0%:
  MISSING_SESSION_CLOSE  a regional session inside the window has no close
  ZERO_VOLUME_SESSION    a session traded nothing (suspension)
  UNVERIFIED_SPLIT       a split/consolidation inside the window not listed in verified-corporate-actions.json
  UNEXPLAINED_MOVE       a close-to-close move beyond the daily limit with no verified event
  NO_EXIT_CLOSE          no close on the exit session (delisting, data end)
Prices are fetched once per evaluation run and frozen with SHA-256 under evaluations/<asOf>/.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

import availability as A
import ledger as L

HERE = Path(__file__).resolve().parent
VERIFIED_ACTIONS = HERE / "verified-corporate-actions.json"
MOVE_LIMIT = {"KR": 0.30, "US": 0.50}
UA = "Mozilla/5.0 (research fetch; decision-desk-v1 evaluator)"


def parse_chart(payload: dict) -> pd.DataFrame:
    res = payload["chart"]["result"][0]
    tz = res["meta"].get("exchangeTimezoneName", "UTC")
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(tz).normalize().tz_localize(None)
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({"close": q["close"], "volume": q.get("volume")}, index=idx)
    df["dividend"] = 0.0
    df["split"] = 1.0
    ev = res.get("events", {})
    for item in ev.get("dividends", {}).values():
        d = pd.Timestamp(item["date"], unit="s", tz="UTC").tz_convert(tz).normalize().tz_localize(None)
        df.loc[d, "dividend"] = (df.at[d, "dividend"] if d in df.index else 0.0) + float(item["amount"])
    for item in ev.get("splits", {}).values():
        d = pd.Timestamp(item["date"], unit="s", tz="UTC").tz_convert(tz).normalize().tz_localize(None)
        df.loc[d, "split"] = float(item["numerator"]) / float(item["denominator"])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def verified_actions() -> dict:
    if not VERIFIED_ACTIONS.exists():
        return {}
    return {(a["ticker"], a["date"]): a for a in json.loads(VERIFIED_ACTIONS.read_text())["actions"]}


def window_block(region: str, ticker: str, df: pd.DataFrame, entry: str, exit_: str, verified: dict) -> str | None:
    sessions = [str(pd.Timestamp(s).date()) for s in A.calendar(region).sessions_in_range(entry, exit_)]
    have = df.dropna(subset=["close"])
    idx = {str(d.date()) for d in have.index}
    if exit_ not in idx:
        return "NO_EXIT_CLOSE"
    missing = [s for s in sessions if s not in idx]
    if missing:
        return f"MISSING_SESSION_CLOSE {missing[:3]}"
    win = have.loc[entry:exit_]
    if "volume" in win and (win["volume"].fillna(0) == 0).any():
        return "ZERO_VOLUME_SESSION " + str(win.index[(win["volume"].fillna(0) == 0)][0].date())
    for d, ratio in win.loc[win["split"] != 1.0, "split"].items():
        if (ticker, str(d.date())) not in verified:
            return f"UNVERIFIED_SPLIT {d.date()} ratio {ratio}"
    moves = (win["close"] / win["close"].shift(1) - 1).abs()
    big = moves[moves > MOVE_LIMIT[region]]
    for d in big.index:
        if (ticker, str(d.date())) not in verified:
            return f"UNEXPLAINED_MOVE {d.date()}"
    return None


def total_return(df: pd.DataFrame, entry: str, exit_: str) -> float:
    w = df.dropna(subset=["close"]).loc[entry:exit_]
    gross = (w["close"] + w["dividend"]) / w["close"].shift(1)
    return float(gross.iloc[1:].prod() - 1)


def fetch_prices(store: Path, tickers: list[str], start: str) -> dict:
    store.mkdir(parents=True, exist_ok=True)
    p1 = int(pd.Timestamp(start).timestamp()) - 10 * 86400
    p2 = int(time.time()) + 86400
    manifest = {"fetchedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "files": {}}
    for t in sorted(set(tickers)):
        url = ("https://query2.finance.yahoo.com/v8/finance/chart/" + urllib.request.quote(t)
               + f"?period1={p1}&period2={p2}&interval=1d&events=div%2Csplit")
        body = None
        for i in range(6):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
                    body = r.read()
                break
            except Exception:  # vendor / proxy flakiness
                time.sleep(10 * (i + 1))
        if body is None:
            manifest["files"][t] = {"status": "FETCH_FAILED"}
            continue
        name = f"{t.replace('^', '').replace('=', '_')}.json.gz"
        (store / name).write_bytes(gzip.compress(body, mtime=0))
        manifest["files"][t] = {"file": name, "url": url, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
        time.sleep(4)
    (store / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest


def load_store(store: Path) -> dict[str, pd.DataFrame]:
    m = json.loads((store / "manifest.json").read_text())
    out = {}
    for t, meta in m["files"].items():
        if meta.get("file"):
            body = gzip.decompress((store / meta["file"]).read_bytes())
            if hashlib.sha256(body).hexdigest() != meta["sha256"]:
                raise RuntimeError(f"PRICE_STORE_CHANGED {t}")
            out[t] = parse_chart(json.loads(body))
    return out


def outcomes(rows: list[dict], prices: dict[str, pd.DataFrame], observed_at: str, cost_mult: float = 1.0) -> list[dict]:
    """Outcome rows for every record x horizon; PENDING rows are returned but should not be appended."""
    verified = verified_actions()
    done = {(o["recordDigest"], o["horizon"], o.get("costMultiplier", 1.0)) for o in rows
            if o.get("schema") == L.OUTCOME_SCHEMA and o["status"] != "PENDING"}
    out = []
    for r in rows:
        if r.get("schema") not in L.RECORD_SCHEMAS:
            continue
        cal = A.calendar(r["region"])
        today = pd.Timestamp(observed_at[:10])
        sessions = [str(pd.Timestamp(s).date()) for s in cal.sessions_in_range(r["plannedExecution"], min(today, cal.last_session))]
        for h in (126, 252):
            if (r["digest"], h, cost_mult) in done:
                continue
            if not sessions or sessions[0] != r["plannedExecution"]:
                out.append({"schema": L.OUTCOME_SCHEMA, "recordDigest": r["digest"], "region": r["region"], "path": r["path"],
                            "cohort": r["cohort"], "horizon": h, "observedAt": observed_at, "status": "PENDING",
                            "horizonEndSession": None, "returnAfterCostPct": None, "excessAfterCostPct": None,
                            "missingDataReason": "NOT_YET_EXECUTED", "costMultiplier": cost_mult})
                continue
            blocked = {}
            if len(sessions) > h and sessions[h] < observed_at[:10]:
                exit_ = sessions[h]
                for t in r["weights"]:
                    if t not in prices:
                        blocked[t] = "PRICE_SOURCE_UNAVAILABLE"
                        continue
                    reason = window_block(r["region"], t, prices[t], r["plannedExecution"], exit_, verified)
                    if reason:
                        blocked[t] = reason
            rec = dict(r)
            if cost_mult != 1.0:
                rec["costs"] = {k: v * cost_mult if isinstance(v, (int, float)) else v for k, v in r["costs"].items()}

            def tr(t, s, e):
                return total_return(prices[t], s, e) if t in prices else None
            o = L.evaluate(rec, h, sessions, tr, observed_at, blocked=blocked)
            o["costMultiplier"] = cost_mult
            out.append(o)
    return out
