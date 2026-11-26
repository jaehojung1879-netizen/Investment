"""Phase 0 source probe for MVMA-v1. Outcome-free: no forward return, NAV or portfolio value is ever computed.

What it measures, per candidate source of the research proposal:

* reachability from this environment (HTTP status, bytes, SHA-256, Last-Modified),
* coverage (first / last observation, row count),
* point-in-time evidence: whether an ALFRED vintage exists at a requested date (ALFRED silently serves the CURRENT
  vintage when none exists, so the vintage stamped in the CSV header is compared with the date asked for), how far the
  latest observation in a vintage trails the vintage date (publication lag), and whether values in an early vintage
  were revised later,
* for Shiller's monthly file, which is published as a single current vintage, the differences between the two
  vintages reachable here, and how far each vintage's last earnings month trails its Last-Modified date.

Only valuation and macro inputs are parsed. The Shiller workbook also carries real total-return price columns; the
parser reads columns 0-4 and 12 (date, P, D, E, CPI, CAPE) and nothing else. The repository's SPY / QQQ total-return
file is inspected for ticker and date coverage only: its price columns are never parsed.

Usage::

    python -m research.market_valuation_macro_overlay_v1.source_probe --out research/market_valuation_macro_overlay_v1/evidence/source-probe.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TIMEOUT = 30

SHILLER_SOURCES = (
    ("YALE_ECON_PAGE_COPY", "http://www.econ.yale.edu/~shiller/data/ie_data.xls"),
    ("SHILLERDATA_HOSTED_ASSET",
     "https://img1.wsimg.com/blobby/go/e5e77e0b-59d1-44d9-ab25-4763ac982e53/downloads/ie_data.xls"),
)
SHILLERDATA_HOME = "https://shillerdata.com/"

# Columns read from Shiller's Data sheet: 0 date, 1 P, 2 D, 3 E, 4 CPI, 12 CAPE. Nothing else (columns 7-11 and 17+
# are real / total-return price paths, i.e. outcomes).
SHILLER_COLUMNS = {"P": 1, "D": 2, "E": 3, "CPI": 4, "CAPE": 12}

FRED_CURRENT = ("BAA", "GS10", "BAA10Y", "DBAA", "AAA10Y", "BAMLH0A0HYM2", "BAMLC0A0CM", "NFCI", "TB3MS", "DGS3MO")
ALFRED_SAMPLES = {
    "BAA": ("1995-01-03", "2000-01-03", "2005-01-03", "2011-06-01", "2016-06-01"),
    "GS10": ("1995-01-03", "2000-01-03", "2005-01-03", "2011-06-01", "2016-06-01"),
    "BAA10Y": ("2011-06-01", "2013-01-02", "2014-01-02", "2014-06-02", "2016-06-01"),
    "DBAA": ("2011-06-01", "2016-06-01"),
    "NFCI": ("2005-01-03", "2011-06-01", "2016-06-01"),
    "TB3MS": ("2005-01-03", "2011-06-01", "2016-06-01"),
    "BAMLH0A0HYM2": ("2016-06-01", "2022-06-01"),
}
REVISION_CHECKS = (("BAA", "2005-01-03"), ("GS10", "2005-01-03"), ("BAA", "2011-06-01"), ("GS10", "2011-06-01"),
                   ("NFCI", "2011-06-01"), ("TB3MS", "2005-01-03"))

FACTSET_LISTING = "https://insight.factset.com/topic/earnings/page/{page}"
FACTSET_SAMPLE_POST = "https://insight.factset.com/earningsinsight_02.17.17"
SP_DJI_EPS_WORKBOOK = "https://www.spglobal.com/spdji/en/documents/additional-material/sp-500-eps-est.xlsx"
KRX_ENDPOINT = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
# KRX Data Marketplace [12021]-family request for KOSPI 200 PER/PBR/dividend yield over January 2024 (a fixed, past
# window: the probe asks whether the endpoint answers at all, it does not collect a series).
KRX_INDEX_VALUATION_FORM = {
    "bld": "dbms/MDC/STAT/standard/MDCSTAT00702", "indIdx": "1", "indIdx2": "028",
    "strtDd": "20240102", "endDd": "20240131", "csvxls_isNo": "false",
}

REPO_INPUTS = {
    "SPY_QQQ_TOTAL_RETURN": "data/research/us-dual-benchmark-v1/spy-qqq-total-return.csv.gz",
    "POLICY_RATE_PROXIES": "data/research/us-dual-benchmark-v1/rates.json",
    "KODEX200_ISSUER_STANDARD_XLS": "docs/audits/kr-alpha-atlas-phase-c-integrity/sources/issuer-standard.xls",
    "BOK_POLICY_RATES": "data/bok-policy-rates.json",
}

FORBIDDEN_SHILLER_COLUMNS = frozenset(range(5, 12)) | frozenset(range(13, 30))


# --------------------------------------------------------------------------- pure parsers (unit-tested offline)

def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def shiller_month(value) -> str | None:
    """Shiller dates are floats like 2023.1 meaning October; always two decimals of month."""
    if not isinstance(value, float):
        return None
    text = "%.2f" % value
    year, month = text.split(".")
    if not 1 <= int(month) <= 12:
        return None
    return f"{year}-{month}"


def shiller_rows(cell) -> dict[str, dict[str, float | None]]:
    """Build {YYYY-MM: {P, D, E, CPI, CAPE}} from a cell accessor `cell(row, col)` -> value or None at end.

    The accessor is called only for column 0 and the columns in SHILLER_COLUMNS.
    """
    out: dict[str, dict[str, float | None]] = {}
    row = 0
    while True:
        try:
            first = cell(row, 0)
        except IndexError:
            break
        month = shiller_month(first)
        if month is not None:
            values = {}
            for name, col in SHILLER_COLUMNS.items():
                if col in FORBIDDEN_SHILLER_COLUMNS:
                    raise AssertionError("OUTCOME_COLUMN_REQUESTED")
                try:
                    value = cell(row, col)
                except IndexError:
                    value = None
                values[name] = float(value) if isinstance(value, (int, float)) and value == value else None
            out[month] = values
        row += 1
    return out


def shiller_summary(rows: dict[str, dict[str, float | None]]) -> dict:
    months = sorted(rows)

    def last(name):
        present = [m for m in months if rows[m][name] is not None]
        return present[-1] if present else None

    def first(name):
        present = [m for m in months if rows[m][name] is not None]
        return present[0] if present else None

    nonpositive_e = [m for m in months if rows[m]["E"] is not None and rows[m]["E"] <= 0]
    return {
        "months": len(months),
        "firstMonth": months[0] if months else None,
        "lastPriceMonth": last("P"),
        "lastEarningsMonth": last("E"),
        "lastDividendMonth": last("D"),
        "firstCapeMonth": first("CAPE"),
        "lastCapeMonth": last("CAPE"),
        "nonPositiveEarningsMonths": len(nonpositive_e),
    }


def vintage_differences(old: dict, new: dict, rel_tol: float = 1e-6) -> dict:
    """Per column, the months present in both vintages whose values differ beyond `rel_tol` (relative)."""
    common = sorted(set(old) & set(new))
    result = {"commonMonths": len(common), "columns": {}}
    for name in SHILLER_COLUMNS:
        diffs = []
        for month in common:
            a, b = old[month][name], new[month][name]
            if a is None or b is None:
                continue
            if abs(a - b) > rel_tol * max(1.0, abs(a)):
                diffs.append({"month": month, "old": a, "new": b, "relativeChange": (b - a) / a if a else None})
        result["columns"][name] = {"differingMonths": len(diffs), "differences": diffs}
    return result


def months_between(earlier: str, later_date: dt.date) -> float:
    """Months from the END of month `earlier` (YYYY-MM) to `later_date`, as days / 30.4375."""
    year, month = (int(x) for x in earlier.split("-"))
    nxt = dt.date(year + (month // 12), month % 12 + 1, 1)
    end = nxt - dt.timedelta(days=1)
    return round((later_date - end).days / 30.4375, 2)


def parse_fred_csv(text: str) -> tuple[str, list[tuple[str, float | None]]]:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if not lines or "," not in lines[0]:
        raise ValueError("NOT_A_FRED_CSV")
    header = lines[0].split(",")[1].strip()
    rows = []
    for line in lines[1:]:
        date, _, value = line.partition(",")
        value = value.strip()
        try:
            number = float(value) if value not in ("", ".") else None
        except ValueError:
            number = None
        rows.append((date.strip(), number))
    return header, rows


def fred_coverage(rows) -> dict:
    present = [d for d, v in rows if v is not None]
    return {"rows": len(rows), "valued": len(present), "firstObservation": present[0] if present else None,
            "lastObservation": present[-1] if present else None}


def alfred_vintage_reading(series: str, requested: str, header: str, rows) -> dict:
    """Classify one ALFRED vintage response.

    ALFRED answers a request for a date with no vintage by serving the CURRENT vintage under that vintage's own date,
    so a returned vintage AFTER the requested date means "no vintage existed then", not "a vintage that happened to be
    revised". The header is `SERIES_YYYYMMDD`.
    """
    match = re.fullmatch(re.escape(series) + r"_(\d{8})", header)
    cover = fred_coverage(rows)
    if not match or cover["valued"] == 0:
        return {"requested": requested, "status": "NO_DATA", "header": header, **cover}
    served = dt.datetime.strptime(match.group(1), "%Y%m%d").date().isoformat()
    status = "VINTAGE_SERVED" if served <= requested else "NO_VINTAGE_AT_DATE_CURRENT_SERVED"
    reading = {"requested": requested, "servedVintage": served, "status": status, **cover}
    if status == "VINTAGE_SERVED" and cover["lastObservation"]:
        last = dt.date.fromisoformat(cover["lastObservation"])
        reading["daysFromLastObservationToVintage"] = (dt.date.fromisoformat(served) - last).days
    return reading


def revision_count(early_rows, current_rows, tol: float = 1e-9) -> dict:
    current = dict(current_rows)
    compared = differing = 0
    examples = []
    for date, value in early_rows:
        if value is None or current.get(date) is None:
            continue
        compared += 1
        if abs(value - current[date]) > tol:
            differing += 1
            if len(examples) < 5:
                examples.append({"date": date, "early": value, "current": current[date]})
    return {"compared": compared, "differing": differing, "examples": examples}


FACTSET_SLUG = re.compile(r'href="https://insight\.factset\.com/((?:\d{4}/\d{1,2}/)?[a-z0-9][a-z0-9_.\-]*)"')
NON_POST = re.compile(r"^(topic|author|hubfs|tag|page|search|rss|subscribe)\b")


def factset_slugs(page_html: str) -> list[str]:
    return sorted({s for s in FACTSET_SLUG.findall(page_html) if not NON_POST.match(s)})


def factset_slug_year(slug: str) -> int | None:
    match = re.search(r"earningsinsight_(\d{1,2})\.(\d{1,2})\.(\d{2})", slug)
    if match:
        return 2000 + int(match.group(3))
    match = re.match(r"(\d{4})/", slug)
    if match:
        return int(match.group(1))
    match = re.search(r"-(20\d{2})(?:-\d+)?$", slug)
    return int(match.group(1)) if match else None


def forward_pe_sentences(page_html: str, limit: int = 3) -> list[str]:
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page_html)))
    found = re.findall(r"[^.]{0,120}forward 12-month P/E ratio[^.]{0,80}\.\s?\d{0,2}[^.]{0,120}", text)
    return [s.strip()[:300] for s in found[:limit]]


# --------------------------------------------------------------------------- network (never called by tests)

def http(url: str, data: dict | None = None, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    # The library default User-Agent is kept on purpose: FRED stalls (read timeout) on unrecognised custom agents.
    request = urllib.request.Request(url, data=body, headers=dict(headers or {}))
    started = time.time()
    print("GET" if body is None else "POST", url, file=sys.stderr, flush=True)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
            return {"url": url, "status": response.status, "bytes": len(raw), "sha256": sha256(raw),
                    "lastModified": response.headers.get("Last-Modified"), "raw": raw,
                    "seconds": round(time.time() - started, 2)}
    except urllib.error.HTTPError as exc:
        raw = exc.read() or b""
        return {"url": url, "status": exc.code, "bytes": len(raw), "sha256": sha256(raw), "raw": raw,
                "error": "HTTP_ERROR"}
    except Exception as exc:  # noqa: BLE001 - every refusal is recorded, never raised
        return {"url": url, "status": None, "bytes": 0, "error": type(exc).__name__ + ": " + str(exc)[:200]}


def public(response: dict) -> dict:
    return {k: v for k, v in response.items() if k != "raw"}


def probe_shiller() -> dict:
    try:
        import xlrd  # noqa: PLC0415 - optional, only the probe needs it
    except ImportError:
        return {"status": "XLRD_NOT_INSTALLED"}
    vintages = {}
    rows_by_source = {}
    for name, url in SHILLER_SOURCES:
        response = http(url)
        entry = public(response)
        if response.get("status") == 200:
            sheet = xlrd.open_workbook(file_contents=response["raw"]).sheet_by_name("Data")

            def cell(r, c, sheet=sheet):
                if r >= sheet.nrows:
                    raise IndexError
                if c >= sheet.ncols:
                    raise IndexError
                value = sheet.cell_value(r, c)
                return value if isinstance(value, float) else None

            rows = shiller_rows(cell)
            rows_by_source[name] = rows
            entry["summary"] = shiller_summary(rows)
            if entry.get("lastModified"):
                modified = dt.datetime.strptime(entry["lastModified"], "%a, %d %b %Y %H:%M:%S GMT").date()
                entry["lastModifiedDate"] = modified.isoformat()
                if entry["summary"]["lastEarningsMonth"]:
                    entry["monthsFromLastEarningsMonthEndToLastModified"] = months_between(
                        entry["summary"]["lastEarningsMonth"], modified)
        vintages[name] = entry
    home = public(http(SHILLERDATA_HOME))
    result = {"vintages": vintages, "shillerdataHome": home}
    if len(rows_by_source) == 2:
        ordered = sorted(rows_by_source, key=lambda n: vintages[n].get("lastModifiedDate") or "")
        result["revisionDiagnostic"] = {"older": ordered[0], "newer": ordered[1],
                                        **vintage_differences(rows_by_source[ordered[0]], rows_by_source[ordered[1]])}
    return result


def probe_fred() -> dict:
    current = {}
    current_rows = {}
    for series in FRED_CURRENT:
        response = http(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}")
        entry = public(response)
        if response.get("status") == 200:
            header, rows = parse_fred_csv(response["raw"].decode("utf-8", "replace"))
            current_rows[series] = rows
            entry.update(fred_coverage(rows))
        current[series] = entry
    vintages = {}
    vintage_rows = {}
    for series, dates in ALFRED_SAMPLES.items():
        vintages[series] = []
        for date in dates:
            response = http(f"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={series}&vintage_date={date}")
            if response.get("status") != 200:
                vintages[series].append({"requested": date, **public(response)})
                continue
            try:
                header, rows = parse_fred_csv(response["raw"].decode("utf-8", "replace"))
            except ValueError:
                vintages[series].append({"requested": date, "status": "NOT_CSV"})
                continue
            reading = alfred_vintage_reading(series, date, header, rows)
            vintages[series].append(reading)
            if reading["status"] == "VINTAGE_SERVED":
                vintage_rows[(series, date)] = rows
    revisions = []
    for series, date in REVISION_CHECKS:
        if (series, date) in vintage_rows and series in current_rows:
            revisions.append({"series": series, "earlyVintage": date,
                              **revision_count(vintage_rows[(series, date)], current_rows[series])})
    return {"current": current, "vintages": vintages, "revisionsEarlyVintageVsCurrent": revisions}


def probe_factset(max_pages: int = 120) -> dict:
    pages = []
    slugs: set[str] = set()
    for page in range(1, max_pages + 1):
        response = http(FACTSET_LISTING.format(page=page))
        pages.append({"page": page, "status": response.get("status")})
        if response.get("status") != 200:
            break
        slugs.update(factset_slugs(response["raw"].decode("utf-8", "replace")))
        time.sleep(1.0)
    by_year: dict[str, int] = {}
    earnings_insight_by_year: dict[str, int] = {}
    for slug in slugs:
        year = factset_slug_year(slug)
        key = str(year) if year else "UNDATED_SLUG"
        by_year[key] = by_year.get(key, 0) + 1
        if "earningsinsight" in slug:
            earnings_insight_by_year[key] = earnings_insight_by_year.get(key, 0) + 1
    sample = http(FACTSET_SAMPLE_POST)
    sample_entry = public(sample)
    if sample.get("status") == 200:
        sample_entry["forwardPeSentences"] = forward_pe_sentences(sample["raw"].decode("utf-8", "replace"))
    return {"listingPagesServed": sum(1 for p in pages if p["status"] == 200),
            "firstRefusedPage": next((p for p in pages if p["status"] != 200), None),
            "uniquePostSlugs": len(slugs), "slugsByYear": dict(sorted(by_year.items())),
            "earningsInsightSlugsByYear": dict(sorted(earnings_insight_by_year.items())),
            "samplePost": sample_entry}


def probe_krx() -> dict:
    response = http(KRX_ENDPOINT, data=KRX_INDEX_VALUATION_FORM, headers={
        "Referer": "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd", "User-Agent": "Mozilla/5.0"})
    entry = public(response)
    raw = response.get("raw") or b""
    entry["bodyHead"] = raw[:80].decode("utf-8", "replace")
    return {"request": KRX_INDEX_VALUATION_FORM, "response": entry}


def probe_sp_dji() -> dict:
    return {"epsWorkbook": public(http(SP_DJI_EPS_WORKBOOK))}


def probe_ecos() -> dict:
    present = bool(os.environ.get("ECOS_API_KEY"))
    home = public(http("https://ecos.bok.or.kr/"))
    return {"ecosApiKeyPresent": present, "homepage": home,
            "status": "KEY_PRESENT_NOT_PROBED" if present else "LOCAL_KEY_ABSENT_USE_ACTIONS_ROUTE"}


def repo_inputs() -> dict:
    out = {}
    for name, rel in REPO_INPUTS.items():
        path = REPO / rel
        if not path.exists():
            out[name] = {"path": rel, "status": "MISSING"}
            continue
        raw = path.read_bytes()
        entry = {"path": rel, "bytes": len(raw), "sha256": sha256(raw)}
        if rel.endswith(".csv.gz"):
            coverage: dict[str, dict] = {}
            with gzip.open(io.BytesIO(raw), "rt") as handle:
                header = handle.readline().strip().split(",")
                ticker_col, date_col = header.index("ticker"), header.index("date")
                for line in handle:
                    parts = line.split(",", max(ticker_col, date_col) + 1)
                    ticker, date = parts[ticker_col], parts[date_col]
                    c = coverage.setdefault(ticker, {"rows": 0, "first": date, "last": date})
                    c["rows"] += 1
                    c["first"] = min(c["first"], date)
                    c["last"] = max(c["last"], date)
            entry["columns"] = header
            entry["coverageByTicker"] = coverage
            entry["note"] = "ticker and date columns only; price columns were not parsed"
        elif rel.endswith(".json"):
            data = json.loads(raw)
            if isinstance(data, dict):
                entry["keys"] = {k: ({"entries": len(v), "first": min(v), "last": max(v)}
                                     if isinstance(v, dict) and v else type(v).__name__) for k, v in data.items()}
        out[name] = entry
    return out


def run(max_factset_pages: int) -> dict:
    return {
        "study": "market-valuation-macro-overlay-v1",
        "stage": "PHASE_0_SOURCE_PROBE",
        "probedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "outcomeReads": 0,
        "notes": "Valuation, macro and coverage metadata only; no forward return, NAV or portfolio value computed.",
        "shiller": probe_shiller(),
        "fred": probe_fred(),
        "factset": probe_factset(max_factset_pages),
        "spDji": probe_sp_dji(),
        "krx": probe_krx(),
        "ecos": probe_ecos(),
        "repositoryInputs": repo_inputs(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-factset-pages", type=int, default=120)
    args = parser.parse_args(argv)
    report = run(args.max_factset_pages)
    Path(args.out).write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({"shillerVintages": {k: v.get("summary") for k, v in report["shiller"]["vintages"].items()},
                      "factsetPages": report["factset"]["listingPagesServed"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
