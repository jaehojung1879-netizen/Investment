"""MVMA-v1 US input build. Preserves source bytes, retrieval time, hashes, coverage and revision status.

Outcome-free: it reads valuation, macro and distribution EVENTS, never an ETF price path for a return. What it builds,
in the user's priority order (repository -> existing artifact / branch -> public collection):

1. Reused from the repository's own preserved data: nothing is re-fetched that the repository already pins (SPY total
   return, policy rates); `source_probe.repo_inputs` records their hashes.
2. Reused from an existing branch: #331's preserved raw BIL chart (git blob 760070137b5b, uncompressed SHA-256
   5d0b7e05...). Copied byte-identically, never re-downloaded.
3. Collected from public endpoints that need no credential:
   * Shiller `ie_data.xls`, both reachable vintages, raw bytes kept (gzip, mtime 0) plus the six columns used;
   * ALFRED `BAA` and `GS10`: for every month-end US decision session d, the vintage in force on the CALENDAR DAY
     BEFORE d (an H.15 release on d lands after the 16:00 close), with the latest observation in that vintage;
   * SSGA's historical SPDR distribution workbook (issuer source for BIL distributions).
   FRED/ALFRED through `FRED_API_KEY` is the Actions route for the same data; the public CSV route answers identically
   without a key, so no secret is needed and none is read here.

Usage::

    python -m research.market_valuation_macro_overlay_v1.collect_inputs --out-dir research/market_valuation_macro_overlay_v1/data
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import io
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import source_probe as SP

REPO = Path(__file__).resolve().parents[2]
FIRST_DECISION_MONTH = "2007-01"   # 60 months before the first evaluated decision (2012-01) for the credit history
LAST_DECISION_MONTH = "2024-08"
ALFRED_SERIES = ("BAA", "GS10")
SSGA_DISTRIBUTIONS = "https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx"
BIL_BRANCH_COMMIT = "49c3aa891b1e85520c2a90d0d062678a738a87cf"
BIL_BRANCH_PATH = "research/us_macro_cocktail_v1/data/raw/yahoo_BIL.json.gz"
BIL_EXPECTED_UNCOMPRESSED_SHA256 = "5d0b7e05ad87d644e0264080c0e1fe08b3e3920190c83a4575c871d2327bfb3e"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def gzip_bytes(raw: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as handle:
        handle.write(raw)
    return buf.getvalue()


def month_end_sessions(sessions, first_month: str, last_month: str) -> list[dt.date]:
    """Last session of each calendar month, from the exchange calendar (never from where data stop)."""
    by_month: dict[str, dt.date] = {}
    for ts in sessions:
        d = ts.date()
        key = f"{d.year:04d}-{d.month:02d}"
        if first_month <= key <= last_month:
            by_month[key] = max(by_month.get(key, d), d)
    return [by_month[k] for k in sorted(by_month)]


def latest_observation(rows) -> tuple[str, float] | tuple[None, None]:
    valued = [(d, v) for d, v in rows if v is not None]
    return valued[-1] if valued else (None, None)


def write(path: Path, raw: bytes) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": str(path.relative_to(REPO)), "bytes": len(raw), "sha256": SP.sha256(raw)}


def build_shiller(out: Path) -> dict:
    import xlrd  # noqa: PLC0415 - collection-only dependency
    entries = {}
    for name, url in SP.SHILLER_SOURCES:
        retrieved = now()
        response = SP.http(url)
        entry = {"source": name, "url": url, "retrievedAt": retrieved, "httpStatus": response.get("status"),
                 "lastModified": response.get("lastModified")}
        if response.get("status") != 200:
            entry["error"] = response.get("error")
            entries[name] = entry
            continue
        raw = response["raw"]
        modified = dt.datetime.strptime(response["lastModified"], "%a, %d %b %Y %H:%M:%S GMT").date()
        tag = modified.strftime("%Y%m%d")
        entry["original"] = {"sha256": SP.sha256(raw), "bytes": len(raw)}
        entry["stored"] = write(out / "raw" / f"shiller-ie_data-{tag}.xls.gz", gzip_bytes(raw))
        sheet = xlrd.open_workbook(file_contents=raw).sheet_by_name("Data")

        def cell(r, c, sheet=sheet):
            if r >= sheet.nrows or c >= sheet.ncols:
                raise IndexError
            value = sheet.cell_value(r, c)
            return value if isinstance(value, float) else None

        rows = SP.shiller_rows(cell)
        last_price = SP.shiller_summary(rows)["lastPriceMonth"]
        text = io.StringIO()
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(["month", "P", "D", "E", "CPI", "CAPE", "partialMonth"])
        for month in sorted(rows):
            r = rows[month]
            writer.writerow([month] + ["" if r[k] is None else repr(r[k]) for k in ("P", "D", "E", "CPI", "CAPE")]
                            + [int(month == last_price)])
        entry["extracted"] = write(out / f"shiller-monthly-{tag}.csv", text.getvalue().encode())
        entry["summary"] = SP.shiller_summary(rows)
        entry["lastModifiedDate"] = modified.isoformat()
        entry["evidenceClass"] = "REVISED_HISTORY_SINGLE_VINTAGE"
        entry["note"] = ("Final row is a partial month (the file labels it e.g. 'Sept price'); flagged partialMonth=1 and "
                         "never used. Columns 5-11 and 13+ (real / total-return paths) are not extracted.")
        entries[name] = entry
    return entries


def build_alfred(out: Path, decisions: list[dt.date], sleep: float, workers: int = 6) -> dict:
    result = {}
    for series in ALFRED_SERIES:
        current = SP.http(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}")
        current_entry = {"url": current["url"], "httpStatus": current.get("status"), "retrievedAt": now()}
        current_rows = []
        if current.get("status") == 200:
            current_entry["stored"] = write(out / "raw" / f"fred-{series}-current.csv.gz", gzip_bytes(current["raw"]))
            _, current_rows = SP.parse_fred_csv(current["raw"].decode())
            current_entry.update(SP.fred_coverage(current_rows))
        def fetch(d, series=series, current_rows=current_rows):
            asked = d - dt.timedelta(days=1)
            url = f"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={series}&vintage_date={asked.isoformat()}"
            response = SP.http(url)
            row = {"decisionDate": d.isoformat(), "vintageRequested": asked.isoformat(),
                   "httpStatus": response.get("status"), "retrievedAt": now()}
            if response.get("status") == 200:
                header, rows = SP.parse_fred_csv(response["raw"].decode())
                reading = SP.alfred_vintage_reading(series, asked.isoformat(), header, rows)
                obs_date, value = latest_observation(rows)
                row.update({"status": reading["status"], "servedVintage": reading.get("servedVintage"),
                            "observationDate": obs_date, "value": value, "responseSha256": response["sha256"],
                            "responseBytes": response["bytes"],
                            "revisedSinceVintage": (None if obs_date is None else
                                                    dict(current_rows).get(obs_date) != value)})
            else:
                row.update({"status": "HTTP_" + str(response.get("status")), "error": response.get("error")})
            time.sleep(sleep)
            return row

        # A few concurrent requests; results are re-ordered by decision date, so the ledger is deterministic.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            ledger = list(pool.map(fetch, decisions))
        text = io.StringIO()
        fields = ["decisionDate", "vintageRequested", "servedVintage", "status", "observationDate", "value",
                  "revisedSinceVintage", "httpStatus", "responseSha256", "responseBytes", "retrievedAt"]
        writer = csv.DictWriter(text, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(ledger)
        served = [r for r in ledger if r.get("status") == "VINTAGE_SERVED" and r.get("value") is not None]
        result[series] = {
            "current": current_entry,
            "vintageLedger": write(out / f"alfred-{series}-asof-decisions.csv", text.getvalue().encode()),
            "decisions": len(ledger), "vintageServed": len(served),
            "missing": len(ledger) - len(served),
            "revisedSinceVintage": sum(1 for r in served if r.get("revisedSinceVintage")),
            "maxDaysDecisionMinusObservationMonthStart": max(
                ((dt.date.fromisoformat(r["decisionDate"]) - dt.date.fromisoformat(r["observationDate"])).days
                 for r in served), default=None),
            "evidenceClass": "PIT_EXACT_ALFRED_VINTAGE",
        }
    return result


def build_bil(out: Path) -> dict:
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{BIL_BRANCH_COMMIT}:{BIL_BRANCH_PATH}"],
                          capture_output=True, check=False)
    entry = {"sourcePr": 331, "sourceCommit": BIL_BRANCH_COMMIT, "sourcePath": BIL_BRANCH_PATH,
             "originalFetchedAtUtc": "2026-11-10T22:32:51+00:00",
             "originalUrl": "https://query2.finance.yahoo.com/v8/finance/chart/BIL?period1=0&period2=1794268800"
                            "&interval=1d&events=div%2Csplit&includeAdjustedClose=true"}
    if blob.returncode != 0:
        entry["status"] = "BRANCH_OBJECT_UNAVAILABLE: fetch origin claude/us-macro-multi-asset-v1-1zc092"
        return entry
    raw = gzip.decompress(blob.stdout)
    entry["uncompressedSha256"] = SP.sha256(raw)
    if entry["uncompressedSha256"] != BIL_EXPECTED_UNCOMPRESSED_SHA256:
        entry["status"] = "HASH_MISMATCH"
        return entry
    entry["stored"] = write(out / "raw" / "yahoo-BIL-chart-20261110.json.gz", gzip_bytes(raw))
    chart = json.loads(raw)["chart"]["result"][0]
    dividends = chart.get("events", {}).get("dividends", {})
    entry["yahooDividendEvents"] = [
        {"exDate": dt.datetime.fromtimestamp(v["date"], dt.timezone.utc).date().isoformat(), "amount": v["amount"]}
        for v in sorted(dividends.values(), key=lambda e: e["date"])]
    entry["yahooSplits"] = [
        {"date": dt.datetime.fromtimestamp(v["date"], dt.timezone.utc).date().isoformat(),
         "numerator": v["numerator"], "denominator": v["denominator"]}
        for v in chart.get("events", {}).get("splits", {}).values()]
    entry["sessions"] = len(chart.get("timestamp", []))
    entry["status"] = "REUSED_BYTE_IDENTICAL"
    return entry


def build_ssga(out: Path) -> dict:
    import openpyxl  # noqa: PLC0415
    retrieved = now()
    response = SP.http(SSGA_DISTRIBUTIONS)
    entry = {"url": SSGA_DISTRIBUTIONS, "retrievedAt": retrieved, "httpStatus": response.get("status"),
             "lastModified": response.get("lastModified")}
    if response.get("status") != 200:
        entry["error"] = response.get("error")
        return entry
    raw = response["raw"]
    entry["stored"] = write(out / "raw" / f"ssga-spdr-historical-distributions-{retrieved[:10].replace('-', '')}.xlsx",
                            raw)
    sheet = openpyxl.load_workbook(io.BytesIO(raw), read_only=True)["dividend"]
    events = []
    for row in sheet.iter_rows(values_only=True):
        if not row or row[1] != "BIL":
            continue

        def iso(value):
            return dt.datetime.strptime(str(value).strip(), "%m/%d/%Y").date().isoformat()

        def num(value):
            text = str(value or "").strip()
            return float(text) if text else 0.0

        events.append({"exDate": iso(row[3]), "recordDate": iso(row[4]), "payableDate": iso(row[5]),
                       "dividend": num(row[6]), "shortTermCapitalGain": num(row[7]),
                       "longTermCapitalGain": num(row[8])})
    events.sort(key=lambda e: e["exDate"])
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=list(events[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(events)
    entry["bilEvents"] = write(out / "ssga-BIL-distributions.csv", text.getvalue().encode())
    entry["bilEventCount"] = len(events)
    entry["bilFirstExDate"], entry["bilLastExDate"] = events[0]["exDate"], events[-1]["exDate"]
    entry["_events"] = events
    return entry


def reconcile_distributions(issuer: list[dict], vendor: list[dict], splits: list[dict] | None = None,
                            tolerance: float = 2e-3) -> dict:
    """Event-level lineage check (dates and amounts only, no price).

    Issuer amount = dividend + capital gains per share AS OF THE EVENT. The vendor restates past amounts per CURRENT
    share, so before each split it is divided back by the split factor before comparison. An issuer row with a zero
    amount (zero-rate months) is a statement that nothing was paid, not a missing vendor event, and is counted apart.
    """
    splits = sorted(splits or [], key=lambda e: e["date"])
    issuer_by_date = {e["exDate"]: e["dividend"] + e["shortTermCapitalGain"] + e["longTermCapitalGain"] for e in issuer}

    def as_of_event(date: str, amount: float) -> float:
        for split in splits:
            if date < split["date"]:
                # Yahoo "1:2" (numerator 1, denominator 2): one new share for two old, so an old-share amount is
                # the restated per-current-share amount times 1/2.
                amount = amount * split["numerator"] / split["denominator"]
        return amount

    vendor_by_date = {e["exDate"]: as_of_event(e["exDate"], e["amount"]) for e in vendor}
    common = sorted(set(issuer_by_date) & set(vendor_by_date))
    conflicts = [{"exDate": d, "issuer": issuer_by_date[d], "vendorAsOfEvent": round(vendor_by_date[d], 6)}
                 for d in common if abs(issuer_by_date[d] - vendor_by_date[d]) > tolerance]
    issuer_only = sorted(set(issuer_by_date) - set(vendor_by_date))
    zero_only = [d for d in issuer_only if issuer_by_date[d] == 0.0]
    paid_only = [d for d in issuer_only if issuer_by_date[d] != 0.0]
    return {"issuerEvents": len(issuer_by_date), "vendorEvents": len(vendor_by_date), "matchedDates": len(common),
            "splitsApplied": [s["date"] + " " + str(s["numerator"]) + ":" + str(s["denominator"]) for s in splits],
            "toleranceAbs": tolerance, "amountConflicts": len(conflicts), "conflicts": conflicts,
            "issuerZeroAmountRowsWithoutVendorEvent": len(zero_only),
            "issuerPaidEventsMissingAtVendor": paid_only,
            "vendorOnly": sorted(set(vendor_by_date) - set(issuer_by_date)),
            "verdict": ("USE_ISSUER_DISTRIBUTIONS" if (paid_only or conflicts) else "VENDOR_MATCHES_ISSUER")}


def run(out: Path, sleep: float) -> dict:
    from pipeline import replay_calendar  # noqa: PLC0415 - pinned XNYS calendar
    sessions = replay_calendar.sessions("2006-12-01", "2024-09-30", "US")
    decisions = month_end_sessions(sessions, FIRST_DECISION_MONTH, LAST_DECISION_MONTH)
    manifest = {"study": "market-valuation-macro-overlay-v1", "stage": "US_INPUT_BUILD", "builtAt": now(),
                "outcomeReads": 0, "calendar": replay_calendar.CALENDAR_VERSION,
                "decisionDates": {"first": decisions[0].isoformat(), "last": decisions[-1].isoformat(),
                                  "count": len(decisions)},
                "secretsUsed": [], "shiller": build_shiller(out), "alfred": build_alfred(out, decisions, sleep)}
    bil = build_bil(out)
    ssga = build_ssga(out)
    issuer_events = ssga.pop("_events", [])
    if issuer_events and bil.get("yahooDividendEvents") is not None:
        manifest["bilDistributionReconciliation"] = reconcile_distributions(
            issuer_events, bil["yahooDividendEvents"], bil.get("yahooSplits"))
    bil.pop("yahooDividendEvents", None)
    manifest["bil"], manifest["ssga"] = bil, ssga
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest


def reconcile_preserved(out: Path) -> dict:
    """Recompute the BIL lineage check from the PRESERVED files only (no network), and store it in the manifest."""
    manifest = json.loads((out / "manifest.json").read_text())
    issuer = []
    for row in csv.DictReader((out / "ssga-BIL-distributions.csv").open()):
        issuer.append({"exDate": row["exDate"], "dividend": float(row["dividend"]),
                       "shortTermCapitalGain": float(row["shortTermCapitalGain"]),
                       "longTermCapitalGain": float(row["longTermCapitalGain"])})
    chart = json.loads(gzip.decompress((out / "raw" / "yahoo-BIL-chart-20261110.json.gz").read_bytes()))
    events = chart["chart"]["result"][0]["events"]

    def day(ts):
        return dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()

    vendor = [{"exDate": day(v["date"]), "amount": v["amount"]} for v in events.get("dividends", {}).values()]
    splits = [{"date": day(v["date"]), "numerator": v["numerator"], "denominator": v["denominator"]}
              for v in events.get("splits", {}).values()]
    manifest["bil"]["yahooSplits"] = splits
    manifest["bilDistributionReconciliation"] = reconcile_distributions(issuer, vendor, splits)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest["bilDistributionReconciliation"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parent / "data"))
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--reconcile-only", action="store_true",
                        help="recompute the BIL lineage check from preserved files; no network")
    args = parser.parse_args(argv)
    if args.reconcile_only:
        print(json.dumps(reconcile_preserved(Path(args.out_dir).resolve()), indent=1))
        return 0
    manifest = run(Path(args.out_dir).resolve(), args.sleep)
    print(json.dumps({k: manifest["alfred"][k]["vintageServed"] for k in ALFRED_SERIES}),
          manifest.get("bilDistributionReconciliation", {}).get("verdict"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
