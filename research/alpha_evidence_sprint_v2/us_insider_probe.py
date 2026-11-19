"""Outcome-blind source-eligibility probe for US insider open-market purchases (SEC Form 4).

Reads SEC's flattened insider-transactions datasets for a fixed set of quarters and counts,
for issuers in the pinned point-in-time S&P 500 snapshot in force on the filing date,
open-market purchases (TRANS_CODE 'P', acquired) and their filing lag. No price, return or
label is read. The comparison only asks whether the source is PIT, deep and dense enough.

    python research/alpha_evidence_sprint_v2/us_insider_probe.py --out <dir> [--quarters 2013q1 ...]

SEC's fair-access policy asks automated clients to declare a company and a CONTACT ADDRESS in the
User-Agent. Measured 2026-11-03 from the authoring sandbox: a request declaring a placeholder
contact was served (HTTP 200, 14,032,058 bytes for 2013q1), the same URL with a generic client
string and no address answered HTTP 403. This probe sends no personal address; collecting more
quarters needs an owner-declared contact (and GitHub Actions egress was already refused by SEC,
AGENTS.md v2.9), so the source is ACCESS_CONDITIONAL, not free-and-automatic.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import hashlib
import io
import json
import statistics
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS = ROOT / "data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz"
URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{q}_form345.zip"
AGENT = "Investment-research-source-probe/1.0 (research use)"
DEFAULT_QUARTERS = ("2013q1", "2017q1", "2021q1", "2025q1")


def membership():
    snaps = json.loads(gzip.decompress(SNAPSHOTS.read_bytes()))["snapshots"]
    snaps.sort(key=lambda s: s["date"])
    return [s["date"] for s in snaps], [set(s["rows"]) for s in snaps]


def members_on(dates, sets, day: str):
    i = bisect.bisect_right(dates, day) - 1
    return sets[i] if i >= 0 else set()


def rows(z: zipfile.ZipFile, name: str):
    with z.open(name) as fh:
        reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"), delimiter="\t")
        yield from reader


def iso(text: str) -> str | None:
    """SEC dates are DD-MON-YYYY in these files."""
    months = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
                                          "NOV", "DEC"), 1)}
    try:
        d, m, y = text.strip().split("-")
        return date(int(y), months[m.upper()], int(d)).isoformat()
    except (ValueError, KeyError):
        return None


def summarize_quarter(z: zipfile.ZipFile, dates, sets) -> dict:
    subs = {}
    for r in rows(z, "SUBMISSION.tsv"):
        if r["DOCUMENT_TYPE"] in ("4", "4/A"):
            subs[r["ACCESSION_NUMBER"]] = (iso(r["FILING_DATE"]), (r["ISSUERTRADINGSYMBOL"] or "").upper().strip(),
                                           r["DOCUMENT_TYPE"])
    purchases, lags, issuers, amended = 0, [], set(), 0
    nonmember = 0
    for r in rows(z, "NONDERIV_TRANS.tsv"):
        if r["TRANS_CODE"] != "P" or r["TRANS_ACQUIRED_DISP_CD"] != "A":
            continue
        sub = subs.get(r["ACCESSION_NUMBER"])
        if not sub or not sub[0]:
            continue
        filed, symbol, doc = sub
        if symbol.replace(".", "-") not in members_on(dates, sets, filed):
            nonmember += 1
            continue
        purchases += 1
        issuers.add(symbol)
        amended += doc == "4/A"
        t = iso(r["TRANS_DATE"] or "")
        if t:
            lags.append((date.fromisoformat(filed) - date.fromisoformat(t)).days)
    q = statistics.quantiles(lags, n=10) if len(lags) >= 10 else None
    return {"form4Submissions": len(subs), "sp500OpenMarketPurchaseRows": purchases,
            "sp500IssuersWithPurchase": len(issuers), "amendmentRows": amended,
            "nonMemberPurchaseRows": nonmember,
            "filingLagDays": None if not q else {"p10": q[0], "median": statistics.median(lags), "p90": q[-1],
                                                 "negative": sum(1 for x in lags if x < 0)}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--quarters", nargs="*", default=list(DEFAULT_QUARTERS))
    ap.add_argument("--from-zip", nargs="*", default=[],
                    help="summarise already-downloaded quarterly zips (name like 2013q1.zip) without any request")
    args = ap.parse_args(argv)
    dates, sets = membership()
    out = {"probe": "us-insider-form4-source-eligibility-v1", "evidenceClass": "OUTCOME_BLIND_SOURCE_PROBE",
           "membershipSource": {"path": str(SNAPSHOTS.relative_to(ROOT)),
                                "sha256": hashlib.sha256(SNAPSHOTS.read_bytes()).hexdigest()},
           "quarters": {}, "returnsRead": 0, "pricesRead": 0}
    for local in args.from_zip:
        payload = Path(local).read_bytes()
        q = Path(local).stem
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            out["quarters"][q] = {"status": "SERVED_EARLIER_LOCAL_COPY", "bytes": len(payload),
                                  "sha256": hashlib.sha256(payload).hexdigest(), **summarize_quarter(z, dates, sets)}
    for q in ([] if args.from_zip else args.quarters):
        req = urllib.request.Request(URL.format(q=q), headers={"User-Agent": AGENT})
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                payload = response.read()
        except Exception as error:  # noqa: BLE001 - recorded as the probe's answer
            out["quarters"][q] = {"status": "UNREACHABLE", "error": f"{type(error).__name__}: {str(error)[:160]}"}
            continue
        if not payload.startswith(b"PK"):
            out["quarters"][q] = {"status": "NOT_A_ZIP", "bytes": len(payload)}
            continue
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            out["quarters"][q] = {"status": "SERVED", "bytes": len(payload),
                                  "sha256": hashlib.sha256(payload).hexdigest(),
                                  **summarize_quarter(z, dates, sets)}
    Path(args.out).mkdir(parents=True, exist_ok=True)
    (Path(args.out) / "us-insider-probe.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps({q: {k: v.get(k) for k in ("status", "sp500OpenMarketPurchaseRows", "sp500IssuersWithPurchase")}
                      for q, v in out["quarters"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
