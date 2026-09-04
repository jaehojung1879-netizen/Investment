"""Does SEC's bulk Financial Statement Data Sets work where the XBRL API didn't?

WHY THIS AND NOT companyfacts AGAIN. The companyfacts probe measured real SEC
responses and got two live block pages instead of data: "Your Request
Originates from an Undeclared Automated Tool" on data.sec.gov, "Request Rate
Threshold Exceeded" on www.sec.gov's company_tickers.json. Both read as a
site-wide bot policy rather than a per-endpoint one — GitHub Actions runners
share IP ranges with a lot of other automated traffic, and SEC's front door
does not know this specific workflow apart from that traffic.

This is still sec.gov, so the same block may well apply — that is exactly
what this measures rather than assumes. What is different: SEC also
publishes bulk quarterly datasets as a handful of large ZIP downloads
(https://www.sec.gov/dera/data/financial-statement-data-sets.html) instead of
one API call per company. A handful of large, infrequent requests is a
different traffic SHAPE than ~500 scripted API calls, which is sometimes
treated differently by the same bot policy — and if it works, it is also
just fewer requests for a full backfill, not only a workaround.

WHAT'S INSIDE, IF IT DOWNLOADS. Each quarterly ZIP holds tab-separated
files: `sub.txt` (one row per filing — cik, form, fy, fp, and `filed`, the
receipt-date equivalent DART's rcept_no gave), and `num.txt` (one row per
reported number — adsh linking back to sub.txt, tag, `ddate` the value is
as-of, `qtrs` the number of quarters it covers, value). `qtrs` would answer
directly, from the data, the question DART's column semantics needed 84
companies' figures to settle by measurement: whether a number is a quarter
alone or a year-to-date cumulative.

Nothing is written to the ledger. This reports.

Usage:  python scripts/probe_sec_bulk_datasets.py [--output bulk-probe.json]
        [--quarters 2025q2,2013q1] [--samples AAPL,JPM,XOM,KO,O]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE = "https://www.sec.gov/files/dera/data/financial-statement-data-sets"
DEFAULT_USER_AGENT = (
    "InvestmentResearchDashboard/1.1 "
    "jaehojung1879-netizen@users.noreply.github.com"
)

# Plain integer CIKs, as `sub.txt` stores them — no zero-padding, unlike the
# companyfacts URL path. Same five names as the XBRL probe, for a like-for-
# like comparison against what that one measured.
KNOWN_CIKS = {"AAPL": 320193, "JPM": 19617, "XOM": 34088, "KO": 21344, "O": 726728}

# What each production factor needs, in the tags this dataset actually uses
# (US-GAAP, same as the XBRL API — this is the same underlying filing data,
# repackaged). Kept short: this probe is about reachability and shape, not a
# second full tag survey.
WANTED_TAGS = ("Revenues", "NetIncomeLoss", "OperatingIncomeLoss",
              "StockholdersEquity", "Liabilities", "Assets",
              "NetCashProvidedByUsedInOperatingActivities")


def _request(url: str, timeout: int = 120) -> tuple[bytes | None, str]:
    """Same retry-with-body discipline as the XBRL probe: a 403 that survives
    retries is worth reading, because the code alone does not say who is
    refusing."""
    req = urllib.request.Request(url, headers={
        "User-Agent": os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT),
        "Accept": "application/zip, */*",
        "Accept-Language": "en-US,en;q=0.8",
    })
    last_error = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read(), ""
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read(300).decode("utf-8", errors="replace").strip()
            except Exception:                          # pragma: no cover - network
                pass
            last_error = f"HTTP {exc.code}" + (f" — {body}" if body else "")
            if exc.code not in {403, 429, 500, 502, 503, 504} or attempt == 2:
                return None, last_error
        except Exception as exc:                      # pragma: no cover - network
            return None, f"{type(exc).__name__}: {exc}"
        time.sleep(2.0 * (2 ** attempt))
    return None, last_error


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


def probe_quarter(quarter: str, wanted_ciks: dict[str, int]) -> dict:
    url = f"{BASE}/{quarter}.zip"
    started = time.monotonic()
    raw, error = _request(url)
    elapsed = time.monotonic() - started
    if raw is None:
        return {"quarter": quarter, "url": url, "error": error, "elapsedSeconds": round(elapsed, 1)}
    entry = parse_quarter_zip(raw, wanted_ciks)
    entry["quarter"] = quarter
    entry["url"] = url
    entry["elapsedSeconds"] = round(elapsed, 1)
    return entry


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="bulk-probe.json")
    parser.add_argument("--quarters", default="2025q2,2013q1",
                        help="recent + near the replay start (2013-01), so "
                             "reachability and how-far-back are both measured")
    parser.add_argument("--samples", default="AAPL,JPM,XOM,KO,O")
    args = parser.parse_args(argv)

    samples = [s.strip().upper() for s in args.samples.split(",") if s.strip()]
    wanted_ciks = {t: KNOWN_CIKS[t] for t in samples if t in KNOWN_CIKS}
    quarters = [q.strip().lower() for q in args.quarters.split(",") if q.strip()]

    report: dict = {"probedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "quarters": {}}
    print(f"User-Agent: {os.environ.get('SEC_USER_AGENT', DEFAULT_USER_AGENT)}\n")

    for quarter in quarters:
        print(f"=== {quarter} ===")
        entry = probe_quarter(quarter, wanted_ciks)
        report["quarters"][quarter] = entry
        if entry.get("error"):
            print(f"  실패 — {entry['error']} ({entry.get('elapsedSeconds')}s)")
            continue
        print(f"  다운로드    {entry['bytes']:,} bytes / {entry['elapsedSeconds']}s")
        print(f"  파일 구성   {entry['files']}")
        print(f"  제출 행수   {entry['submissionRows']:,}")
        print(f"  숫자 행수   {entry['numericRows']:,}")
        for ticker, info in entry["samplesFound"].items():
            print(f"    {ticker:<6} {info}")
        missing = [t for t in samples if t not in entry["samplesFound"]]
        if missing:
            print(f"    누락: {', '.join(missing)}")
        print(f"  관련 팩트   {entry['relevantFacts']} · qtrs 분포 {entry['qtrsDistribution']}")
        if entry.get("sampleFact"):
            print(f"  예시        {entry['sampleFact']}")
        print()

    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ok = [e for e in report["quarters"].values() if not e.get("error")]
    print("=== 판정 ===")
    print(f"  다운로드 성공 분기 수 : {len(ok)}/{len(quarters)}")
    if ok:
        has_qtrs = all(e.get("qtrsDistribution") for e in ok)
        print(f"  qtrs로 기간 직접 판정 : {'예' if has_qtrs else '아니오 — 샘플에 관련 팩트 없음'}")
        print("  → 이 경로가 companyfacts보다 나은 대안입니다. 전체 백필 설계로 넘어갈 수 있습니다.")
    else:
        print("  → 이것도 막혀 있으면 site-wide 정책입니다. sec.gov 경로 자체를 재고해야 합니다.")
    print(f"\nwrote {args.output}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
