"""Market Risk Discovery v1 -- Stage 1 source audit (US). Reads no signal-outcome relation.

1. ALFRED: the first published vintage of BAA and GS10, and an as-of ledger for every month-end decision session
   from that vintage to 2026-10: for decision session d, the latest observation in the vintage in force on the
   calendar day BEFORE d (an H.15 release on d lands after the close). Extends MVMA-v1's 2007-2024 ledger.
2. SPY: #331's preserved raw chart (git blob, byte-identical) audited for XNYS session coverage, its distribution
   events reconciled with SSGA's official SPY distributions, and its total-return index reconciled with the
   repository's SSGA-reconciled 2011+ ledger (data/research/us-dual-benchmark-v1). Price reconciliation is a ledger
   check; no return is related to any signal here.

Usage::

    python -m research.market_risk_discovery_v1.source_audit
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from research.market_valuation_macro_overlay_v1 import source_probe as SP

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA = HERE / "data"
BRANCH_331 = "49c3aa891b1e85520c2a90d0d062678a738a87cf"
SPY_331 = "research/us_macro_cocktail_v1/data/raw/yahoo_SPY.json.gz"
SPY_331_SHA = "381dd6ccb483fccdc90ad8f8ac0ca45cc2fe54de1d0174cae76aedb63adcc062"   # #331 manifest (uncompressed)
SSGA = REPO / "research/market_valuation_macro_overlay_v1/data/raw/ssga-spdr-historical-distributions-20261122.xlsx"
DUAL = REPO / "data/research/us-dual-benchmark-v1/spy-qqq-total-return.csv.gz"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def gz(raw: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as h:
        h.write(raw)
    return buf.getvalue()


# ------------------------------------------------------------------ ALFRED


def served_vintage(series: str, date: str) -> tuple[str | None, list]:
    r = SP.http(f"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={series}&vintage_date={date}")
    if r.get("status") != 200:
        return None, []
    header, rows = SP.parse_fred_csv(r["raw"].decode())
    reading = SP.alfred_vintage_reading(series, date, header, rows)
    return (reading.get("servedVintage") if reading["status"] == "VINTAGE_SERVED" else None), rows


def first_vintage(series: str, lo: str = "1995-01-02", hi: str = "1999-01-04") -> str:
    """Smallest date with a served vintage (bisection on calendar days; ALFRED answers 404 before the first)."""
    a, b = dt.date.fromisoformat(lo), dt.date.fromisoformat(hi)
    if served_vintage(series, b.isoformat())[0] is None:
        raise RuntimeError("NO_VINTAGE_AT_UPPER_BOUND")
    while (b - a).days > 1:
        mid = a + (b - a) // 2
        if served_vintage(series, mid.isoformat())[0] is None:
            a = mid
        else:
            b = mid
    return b.isoformat()


def month_end_sessions(first_month: str, last_month: str) -> list[str]:
    from pipeline import replay_calendar  # noqa: PLC0415
    out: dict[str, str] = {}
    for ts in replay_calendar.sessions(f"{first_month}-01", "2026-11-20", "US"):
        d = ts.date().isoformat()
        if first_month <= d[:7] <= last_month:
            out[d[:7]] = max(out.get(d[:7], d), d)
    return [out[k] for k in sorted(out)]


def asof_ledger(series: str, decisions: list[str], current: dict[str, float]) -> list[dict]:
    def one(d):
        asked = (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()
        served, rows = served_vintage(series, asked)
        valued = [(o, v) for o, v in rows if v is not None]
        obs, val = valued[-1] if (served and valued) else (None, None)
        return {"decisionDate": d, "vintageRequested": asked, "servedVintage": served, "observationDate": obs,
                "value": val, "revisedSinceVintage": None if obs is None else current.get(obs) != val,
                "retrievedAt": now()}
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(one, decisions))


def alfred_section() -> dict:
    out = {}
    for series in ("BAA", "GS10"):
        cur = SP.http(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}")
        _, cur_rows = SP.parse_fred_csv(cur["raw"].decode())
        current = {o: v for o, v in cur_rows if v is not None}
        (DATA / "raw").mkdir(parents=True, exist_ok=True)
        (DATA / "raw" / f"fred-{series}-current.csv.gz").write_bytes(gz(cur["raw"]))
        first = first_vintage(series)
        decisions = month_end_sessions(first[:7] if first[8:] == "01" else first[:7], "2026-10")
        decisions = [d for d in decisions if d > first]
        ledger = asof_ledger(series, decisions, current)
        text = io.StringIO()
        w = csv.DictWriter(text, fieldnames=list(ledger[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(ledger)
        path = DATA / f"alfred-{series}-asof-month-ends.csv"
        path.write_text(text.getvalue())
        served = [r for r in ledger if r["value"] is not None]
        lags = [(dt.date.fromisoformat(r["decisionDate"]) - dt.date.fromisoformat(r["observationDate"])).days
                for r in served]
        out[series] = {"firstVintage": first, "decisions": len(ledger), "first": ledger[0]["decisionDate"],
                       "last": ledger[-1]["decisionDate"], "served": len(served), "missing": len(ledger) - len(served),
                       "revisedSinceVintage": sum(bool(r["revisedSinceVintage"]) for r in served),
                       "observationLagDays": {"min": min(lags), "max": max(lags)},
                       "ledger": {"path": str(path.relative_to(REPO)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
                       "currentSnapshotSha256": hashlib.sha256(cur["raw"]).hexdigest(), "currentRetrievedAt": now()}
    return out


# ------------------------------------------------------------------ SPY


def spy_section() -> dict:
    import openpyxl  # noqa: PLC0415 - audit-time only; the extracted CSV is what tests read
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{BRANCH_331}:{SPY_331}"], capture_output=True, check=True).stdout
    raw = gzip.decompress(blob)
    if hashlib.sha256(raw).hexdigest() != SPY_331_SHA:
        raise RuntimeError("SPY_331_HASH_MISMATCH")
    (DATA / "raw").mkdir(parents=True, exist_ok=True)
    (DATA / "raw" / "yahoo-SPY-chart-20261110.json.gz").write_bytes(gz(raw))
    chart = json.loads(raw)["chart"]["result"][0]
    day = lambda ts: dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()  # noqa: E731
    closes = {day(t): c for t, c in zip(chart["timestamp"], chart["indicators"]["quote"][0]["close"]) if c is not None}
    vendor_divs = {day(v["date"]): v["amount"] for v in chart["events"]["dividends"].values()}

    ws = openpyxl.load_workbook(SSGA, read_only=True)["dividend"]
    issuer = []
    for r in ws.iter_rows(values_only=True):
        if r and r[1] == "SPY":
            amt = sum(float(str(x).strip()) for x in (r[6], r[7], r[8]) if str(x or "").strip())
            issuer.append({"exDate": dt.datetime.strptime(str(r[3]).strip(), "%m/%d/%Y").date().isoformat(), "amount": amt})
    issuer.sort(key=lambda e: e["exDate"])
    text = io.StringIO()
    w = csv.DictWriter(text, fieldnames=["exDate", "amount"], lineterminator="\n")
    w.writeheader()
    w.writerows(issuer)
    (DATA / "ssga-SPY-distributions.csv").write_text(text.getvalue())
    iss = {e["exDate"]: e["amount"] for e in issuer}
    common = sorted(set(iss) & set(vendor_divs))
    conflicts = [{"exDate": d, "issuer": iss[d], "vendor": vendor_divs[d]} for d in common if abs(iss[d] - vendor_divs[d]) > 5e-4]

    from pipeline import replay_calendar  # noqa: PLC0415
    sessions = [t.date().isoformat() for t in replay_calendar.sessions("1993-01-29", "2026-11-09", "US")]
    missing = [s for s in sessions if s not in closes]
    extra = [d for d in closes if d not in set(sessions)]
    off_session = [d for d in iss if d >= "1993-01-29" and d not in closes]

    # Total-return index from raw close + ISSUER distributions, reconciled with the repository's 2011+ ledger.
    tr, level, prev = {}, 1.0, None
    for s in sessions:
        if s not in closes:
            continue
        if prev is not None:
            level *= (closes[s] + iss.get(s, 0.0)) / closes[prev]
        tr[s] = level
        prev = s
    dual = {}
    with gzip.open(DUAL, "rt") as h:
        for row in csv.DictReader(h):
            if row["ticker"] == "SPY":
                dual[row["date"]] = float(row["totalReturnClose"])
    both = [d for d in sorted(dual) if d in tr]
    a = np.array([tr[d] for d in both])
    b = np.array([dual[d] for d in both])
    ra, rb = a[1:] / a[:-1] - 1, b[1:] / b[:-1] - 1
    diff_bp = np.abs(ra - rb) * 1e4
    return {
        "source": {"pr": 331, "commit": BRANCH_331, "path": SPY_331, "uncompressedSha256": SPY_331_SHA,
                   "fetchedAtUtc": "2026-11-10T22:29:37+00:00", "stored": "data/raw/yahoo-SPY-chart-20261110.json.gz"},
        "sessions": {"first": min(closes), "last": max(closes), "chartRows": len(closes), "xnysSessions": len(sessions),
                     "missingXnysSessions": len(missing), "rowsOffCalendar": len(extra)},
        "distributions": {"vendorEvents": len(vendor_divs), "issuerEvents": len(issuer), "matchedDates": len(common),
                          "amountConflicts": conflicts, "issuerOnly": sorted(set(iss) - set(vendor_divs)),
                          "vendorOnly": sorted(set(vendor_divs) - set(iss)), "issuerExDatesOffSession": off_session,
                          "splits": chart["events"].get("splits")},
        "trReconciliationWithRepositoryLedger": {
            "overlap": [both[0], both[-1]], "sessions": len(both),
            "dailyAbsDiffBp": {"median": float(np.median(diff_bp)), "p99": float(np.percentile(diff_bp, 99)),
                               "max": float(diff_bp.max()), "over1bp": int((diff_bp > 1).sum())},
            "cumulativeRatio": float((a[-1] / a[0]) / (b[-1] / b[0]))},
        "basis": "split-adjusted raw close plus SSGA issuer distributions reinvested at the ex-date close",
    }


def main() -> int:
    report = {"study": "market-risk-discovery-v1", "stage": "STAGE_1_SOURCE_AUDIT", "builtAt": now(),
              "signalOutcomeRelationsRead": 0, "alfred": alfred_section(), "spy": spy_section()}
    (HERE / "evidence" / "us-source-audit.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: report["alfred"][k] for k in report["alfred"]}, indent=1))
    print(json.dumps({k: v for k, v in report["spy"].items() if k != "source"}, indent=1)[:2500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
