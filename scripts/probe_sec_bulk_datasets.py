"""Does SEC's bulk Financial Statement Data Sets work where the XBRL API didn't?

WHAT WAS ALREADY MEASURED. This probe ran once before, 2026-09-04 04:50 UTC,
and got a real answer: both `2025q2.zip` and `2013q1.zip` came back
`HTTP 403 SEC.gov | Request Rate Threshold Exceeded` — the same block page
`www.sec.gov/files/company_tickers.json` gives, on the same host. That run
proved the block is not specific to the ~500-scripted-calls XBRL API traffic
shape; a handful of large infrequent requests hit the identical wall. It did
not capture a redirect chain, response headers, the runner's egress address,
or a same-run comparison against `data.sec.gov` and `Archives` — and it is
twelve days old against a site whose answer has moved before (SEC served this
repository live on 2026-08-15, then refused it by the time this probe first
ran). `pipeline.institutional_13f`'s LIVE_SEC fetch and this probe's refusal
are the same host, weeks apart — worth re-measuring, not re-assuming.

THIS RUN'S AXIS. Not "is www.sec.gov blocked" — the header-isolation probe
already varied User-Agent shape four ways against two hosts and found no
variant that got through. This measures the THING THAT HAS NEVER BEEN ASKED:
does the answer differ by REQUEST SHAPE (bare vs identified client) on THIS
SPECIFIC PATH, and what does the full response — redirects, headers, exact
byte signature — say about who is refusing and why, correlated against the
runner's own egress address the way the fan-out probe correlates it for the
other two hosts.

WHAT'S INSIDE, IF IT DOWNLOADS. Each quarterly ZIP holds tab-separated
files: `sub.txt` (one row per filing — cik, form, fy, fp, and `filed`, the
receipt-date equivalent DART's rcept_no gave), `num.txt` (one row per
reported number — adsh linking back to sub.txt, tag, `ddate` the value is
as-of, `qtrs` the number of quarters it covers, value), plus `tag.txt` and
`pre.txt`. `qtrs` would answer directly, from the data, the question DART's
column semantics needed 84 companies' figures to settle by measurement:
whether a number is a quarter alone or a year-to-date cumulative.

Nothing is written to the ledger, and nothing is written to disk: the ZIP is
parsed from the in-memory response body and discarded when the process exits.

Usage:  python scripts/probe_sec_bulk_datasets.py [--output bulk-probe.json]
        [--quarter 2026q2] [--fallback-quarter 2025q4]
        [--samples AAPL,JPM,XOM,KO,O]
"""
from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.sec_access import BLOCK_MARKERS, decode_body, egress_ip  # noqa: E402

BASE = "https://www.sec.gov/files/dera/data/financial-statement-data-sets"
FAIR_ACCESS_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "InvestmentResearchDashboard/1.1 jaehojung1879-netizen@users.noreply.github.com")

# Plain integer CIKs, as `sub.txt` stores them — no zero-padding, unlike the
# companyfacts URL path.
KNOWN_CIKS = {"AAPL": 320193, "JPM": 19617, "XOM": 34088, "KO": 21344, "O": 726728}

WANTED_TAGS = ("Revenues", "NetIncomeLoss", "OperatingIncomeLoss",
              "StockholdersEquity", "Liabilities", "Assets",
              "NetCashProvidedByUsedInOperatingActivities")

EXPECTED_ARCHIVE_FILES = ("sub.txt", "num.txt", "tag.txt", "pre.txt")

# The comparison targets. `data.sec.gov` and the DERA ZIP host are different
# front doors on the same domain; `/Archives/.../index.json` is a third —
# small, genuinely under Archives, and present for any CIK with filings, so
# it does not depend on knowing one accession number in advance.
DATA_SEC_SMALL = "https://data.sec.gov/submissions/CIK0000320193.json"
ARCHIVES_SMALL = "https://www.sec.gov/Archives/edgar/data/320193/index.json"

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")

# What of a response's headers is worth keeping. Everything else is either
# noise (Date, per-request tracing IDs) or not present on sec.gov's edge.
RELEVANT_HEADER_KEYS = {
    "content-type", "content-length", "content-encoding", "server", "via",
    "cache-control", "x-cache", "x-amz-cf-id", "x-amz-cf-pop", "location",
    "retry-after", "etag", "last-modified", "date",
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse to follow — return None so the caller sees each hop as an
    HTTPError carrying that hop's own status and headers, including
    Location. Following silently would report only the final host, which
    would misattribute a redirect-time refusal to whichever host happened
    to answer last."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _hop(url: str, headers: dict, timeout: int) -> tuple[int | None, dict, bytes]:
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, headers=headers)
    try:
        response = opener.open(request, timeout=timeout)
        return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read()
        except Exception:  # pragma: no cover - network dependent
            pass
        hdrs = dict(exc.headers.items()) if exc.headers else {}
        return exc.code, hdrs, body
    except Exception as exc:  # pragma: no cover - network dependent
        return None, {}, f"{type(exc).__name__}: {exc}".encode()


def classify_body(status: int | None, body: bytes) -> tuple[str, str | None]:
    """ZIP, BLOCK_PAGE, JSON, HTML or UNKNOWN, plus the marker if blocked.

    Deliberately a fourth shape beside `pipeline.sec_access.classify`'s
    SERVED/BLOCKED/ERROR: that one assumes success looks like JSON, which a
    quarterly dataset never does. A response is read by its own magic bytes
    first — a block page cannot forge a PK header — and only falls through to
    the text markers when it isn't one.
    """
    if body[:4] in ZIP_MAGIC:
        return "ZIP", None
    text = body[:2000].decode("utf-8", "replace")
    for marker in BLOCK_MARKERS:
        if marker.lower() in text.lower():
            return "BLOCK_PAGE", marker
    stripped = text.lstrip()
    if stripped[:1] in ("{", "["):
        return "JSON", None
    if stripped[:1] == "<":
        return "HTML", None
    return "UNKNOWN", None


def diagnostic_fetch(url: str, *, user_agent: str | None, timeout: int = 120,
                     max_redirects: int = 5) -> dict:
    """One fully-logged, UNRETRIED request. Every field the task requires.

    `user_agent=None` sends none at all — urllib supplies its own default,
    which is exactly the "undeclared automated tool" shape SEC's own block
    page names. That is a deliberate probe of the identification axis, not
    an oversight; fair-access compliance is what the second call this script
    makes for every target restores.
    """
    headers = {"Accept": "application/zip, application/json, */*",
              "Accept-Encoding": "gzip, deflate", "Accept-Language": "en-US,en;q=0.8"}
    if user_agent is not None:
        headers["User-Agent"] = user_agent

    started = datetime.datetime.now(datetime.timezone.utc)
    chain = []
    hop_url = url
    status, hdrs, body = None, {}, b""
    for _ in range(max_redirects + 1):
        status, hdrs, body = _hop(hop_url, headers, timeout)
        location = hdrs.get("Location")
        chain.append({"url": hop_url, "status": status, "location": location})
        if status in REDIRECT_STATUSES and location:
            hop_url = urllib.parse.urljoin(hop_url, location)
            continue
        break
    finished = datetime.datetime.now(datetime.timezone.utc)

    decoded = decode_body(body, hdrs.get("Content-Encoding"))
    kind, marker = classify_body(status, decoded)
    return {
        "requestedUrl": url,
        "finalUrl": chain[-1]["url"],
        "redirected": len(chain) > 1,
        "redirectChain": chain,
        "status": status,
        "headers": {k: v for k, v in hdrs.items() if k.lower() in RELEVANT_HEADER_KEYS},
        "contentType": hdrs.get("Content-Type"),
        "contentLengthHeader": hdrs.get("Content-Length"),
        "rawBytes": len(body),
        "decodedBytes": len(decoded),
        "bodyKind": kind,
        "blockMarker": marker,
        "bodyHeadHex": decoded[:16].hex(),
        "bodyHeadText": (decoded[:200].decode("utf-8", "replace")
                        if kind != "ZIP" else None),
        "userAgentSent": user_agent if user_agent is not None else "(none — urllib default)",
        "startedAt": started.isoformat(),
        "finishedAt": finished.isoformat(),
        "elapsedSeconds": round((finished - started).total_seconds(), 3),
        "_decodedBody": decoded,  # stripped before the report is written
    }


def _read_tsv(archive: zipfile.ZipFile, name: str) -> list[dict]:
    with archive.open(name) as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
        return list(csv.DictReader(text, delimiter="\t"))


def parse_quarter_zip(raw: bytes, wanted_ciks: dict[str, int]) -> dict:
    """Everything the probe reports about one quarter, from its raw ZIP bytes.

    Split from the network call so the parsing — matching submissions by CIK,
    filtering facts to the wanted tags, the `qtrs` distribution — is the part
    pinned by a test, not the download.
    """
    entry: dict = {"bytes": len(raw)}
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        entry["error"] = f"not a zip: {exc}"
        return entry
    entry["files"] = archive.namelist()
    entry["zipIntegrityOk"] = archive.testzip() is None
    entry["expectedFiles"] = {name: name in archive.namelist()
                              for name in EXPECTED_ARCHIVE_FILES}
    entry["fileSizes"] = {name: archive.getinfo(name).file_size
                          for name in EXPECTED_ARCHIVE_FILES
                          if name in archive.namelist()}

    if "sub.txt" not in archive.namelist() or "num.txt" not in archive.namelist():
        entry["error"] = "sub.txt/num.txt not found — layout may have changed"
        return entry

    subs = _read_tsv(archive, "sub.txt")
    entry["submissionRows"] = len(subs)
    cik_to_ticker = {v: k for k, v in wanted_ciks.items()}
    matched = {row["adsh"]: row for row in subs if int(row.get("cik") or -1) in cik_to_ticker}
    entry["samplesFound"] = {
        cik_to_ticker[int(row["cik"])]: {
            "form": row.get("form"), "fy": row.get("fy"), "fp": row.get("fp"),
            "period": row.get("period"), "filed": row.get("filed"),
        }
        for row in matched.values()
    }

    nums = _read_tsv(archive, "num.txt")
    entry["numericRows"] = len(nums)
    relevant = [row for row in nums if row.get("adsh") in matched and row.get("tag") in WANTED_TAGS]
    entry["relevantFacts"] = len(relevant)
    qtrs_seen: dict[str, int] = {}
    for row in relevant:
        qtrs_seen[row.get("qtrs", "?")] = qtrs_seen.get(row.get("qtrs", "?"), 0) + 1
    entry["qtrsDistribution"] = qtrs_seen
    if relevant:
        sample = relevant[0]
        entry["sampleFact"] = {k: sample.get(k) for k in
                               ("tag", "ddate", "qtrs", "uom", "value")}
    return entry


def _strip_body(diag: dict) -> dict:
    return {k: v for k, v in diag.items() if k != "_decodedBody"}


def probe_bulk_zip(quarter: str, fallback_quarter: str | None,
                   wanted_ciks: dict[str, int], *, timeout: int) -> dict:
    """The core test: one quarter's ZIP, asked twice — bare, then identified.

    Exactly one attempt each, no retry — the task requires the FIRST
    request's own result, not a result laundered through retries. If the
    identified request still fails to produce a ZIP, one fallback quarter is
    tried (identified UA only) in case the primary quarter is simply not
    published yet, which is a different finding from a refusal.
    """
    url = f"{BASE}/{quarter}.zip"
    print(f"=== {quarter}.zip — request 1, no declared User-Agent, no retry ===")
    first = diagnostic_fetch(url, user_agent=None, timeout=timeout)
    print(f"  {first['status']} {first['bodyKind']} "
         f"{first['decodedBytes']:,}B ({first['elapsedSeconds']}s) "
         f"final={first['finalUrl']}")

    print(f"=== {quarter}.zip — request 2, fair-access User-Agent, no retry ===")
    second = diagnostic_fetch(url, user_agent=FAIR_ACCESS_USER_AGENT, timeout=timeout)
    print(f"  {second['status']} {second['bodyKind']} "
         f"{second['decodedBytes']:,}B ({second['elapsedSeconds']}s) "
         f"final={second['finalUrl']}")

    chosen, chosen_quarter, used_fallback = second, quarter, False
    if second["bodyKind"] != "ZIP" and fallback_quarter:
        print(f"=== {fallback_quarter}.zip — cross-check, fair-access User-Agent, no retry ===")
        fb_url = f"{BASE}/{fallback_quarter}.zip"
        fallback = diagnostic_fetch(fb_url, user_agent=FAIR_ACCESS_USER_AGENT, timeout=timeout)
        print(f"  {fallback['status']} {fallback['bodyKind']} "
             f"{fallback['decodedBytes']:,}B ({fallback['elapsedSeconds']}s)")
        if fallback["bodyKind"] == "ZIP":
            chosen, chosen_quarter, used_fallback = fallback, fallback_quarter, True
    else:
        fallback = None

    parsed = None
    if chosen["bodyKind"] == "ZIP":
        parsed = parse_quarter_zip(chosen["_decodedBody"], wanted_ciks)
        print(f"  parsed {chosen_quarter}: files={parsed.get('files')} "
             f"expected={parsed.get('expectedFiles')} "
             f"zipIntegrityOk={parsed.get('zipIntegrityOk')}")
        if parsed.get("samplesFound"):
            for ticker, info in parsed["samplesFound"].items():
                print(f"    {ticker:<6} {info}")
        print(f"  관련 팩트 {parsed.get('relevantFacts')} · "
             f"qtrs 분포 {parsed.get('qtrsDistribution')}")

    return {
        "quarter": quarter, "fallbackQuarter": fallback_quarter,
        "usedFallback": used_fallback, "chosenQuarter": chosen_quarter,
        "requestNoUserAgent": _strip_body(first),
        "requestFairAccessUserAgent": _strip_body(second),
        "requestFallbackQuarter": _strip_body(fallback) if fallback else None,
        "parsed": parsed,
    }


def probe_comparisons(timeout: int) -> dict:
    """The same-run cross-check: is this www.sec.gov-wide, data.sec.gov-only,
    or specific to the DERA ZIP path — asked with the identified UA only,
    since the UA axis is already covered by the bulk-ZIP requests above."""
    out = {}
    for name, url in (("data.sec.gov", DATA_SEC_SMALL),
                      ("www.sec.gov/Archives", ARCHIVES_SMALL)):
        print(f"=== comparison: {name} ===")
        diag = diagnostic_fetch(url, user_agent=FAIR_ACCESS_USER_AGENT, timeout=timeout)
        print(f"  {diag['status']} {diag['bodyKind']} {diag['decodedBytes']:,}B "
             f"({diag['elapsedSeconds']}s)")
        out[name] = _strip_body(diag)
    return out


def judge(bulk: dict, comparisons: dict) -> dict:
    """A / B / C exactly as the task defines them, from what was measured."""
    zip_served = (bulk["requestFairAccessUserAgent"]["bodyKind"] == "ZIP"
                 or bulk["requestNoUserAgent"]["bodyKind"] == "ZIP"
                 or (bulk.get("requestFallbackQuarter") or {}).get("bodyKind") == "ZIP")
    data_sec_served = comparisons.get("data.sec.gov", {}).get("bodyKind") in ("JSON",)
    archives_served = comparisons.get("www.sec.gov/Archives", {}).get("bodyKind") in ("JSON",)

    if zip_served:
        return {"verdict": "VIABLE",
                "meaning": ("GitHub Actions에서 분기 ZIP 다운로드가 가능합니다. 향후 분기 ZIP "
                            "다운로드 → 829개 historical US universe의 CIK만 필터 → 필요한 "
                            "10-K/10-Q 및 재무항목만 PIT 형태로 가공 → 원본 삭제 구조를 쓸 수 "
                            "있습니다.")}
    if data_sec_served or archives_served:
        return {"verdict": "PARTIALLY_VIABLE",
                "meaning": (f"data.sec.gov 서빙={data_sec_served}, Archives 서빙={archives_served}, "
                            "ZIP 경로만 막혀 있습니다. 서빙되는 경로로 구축 방식을 다시 설계해야 "
                            "합니다 — 예를 들어 Archives에서 개별 filing을 받는 방식.")}
    return {"verdict": "BLOCKED",
            "meaning": ("분기 ZIP도, data.sec.gov도, Archives도 첫 요청부터 막혀 있습니다. "
                        "GitHub-hosted runner에서 SEC bootstrap을 계속 시도하는 것은 중단하고, "
                        "local/self-hosted runner 등 Actions IP pool 밖에서 한 번만 받는 경로를 "
                        "권고합니다.")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="bulk-probe.json")
    parser.add_argument("--quarter", default="2026q2",
                        help="primary quarter to request")
    parser.add_argument("--fallback-quarter", default="2025q4",
                        help="asked only if the primary quarter does not yield a ZIP; "
                             "empty string disables it")
    parser.add_argument("--samples", default="AAPL,JPM,XOM,KO,O")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)

    samples = [s.strip().upper() for s in args.samples.split(",") if s.strip()]
    wanted_ciks = {t: KNOWN_CIKS[t] for t in samples if t in KNOWN_CIKS}
    fallback = args.fallback_quarter.strip() or None

    print(f"Fair-access User-Agent: {FAIR_ACCESS_USER_AGENT}")
    print("Runner egress IP: ", end="", flush=True)
    ip = egress_ip()
    print(ip or "(could not determine)")
    print()

    bulk = probe_bulk_zip(args.quarter, fallback, wanted_ciks, timeout=args.timeout)
    print()
    comparisons = probe_comparisons(args.timeout)
    print()
    verdict = judge(bulk, comparisons)

    report = {
        "probedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "egressIp": ip,
        "fairAccessUserAgent": FAIR_ACCESS_USER_AGENT,
        "bulkZip": bulk,
        "comparisons": comparisons,
        "verdict": verdict["verdict"],
        "verdictMeaning": verdict["meaning"],
    }
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=== 판정 ===")
    print(f"  {verdict['verdict']}")
    print(f"  {verdict['meaning']}")
    print(f"\nwrote {args.output}")
    return 0 if verdict["verdict"] == "VIABLE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
