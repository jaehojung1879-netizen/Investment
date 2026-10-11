"""Dated GICS sector labels for the sealed S&P 500 membership snapshots. Bounded, input-only.

    python scripts/acquire_us_sp500_snapshot_sectors.py --output data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz

The sealed membership file (`research_specs/alpha-opportunity-model-v1-us-membership.json.gz`) keeps only the member
symbols of each of its 195 snapshots, so no PIT sector exists in the repository. The upstream dataset commit each
snapshot came from DOES carry a sector column: this reads exactly those 195 commits, one request each, no retry loop,
no other URL, and refuses a response whose SHA-256 is not the `rawCsvSha256` the v3 identity evidence already pinned.
The label is therefore the classification the source PUBLISHED at that snapshot, never today's classification
pushed backwards. It is a dataset label, not an index-provider file, and is used for descriptive coverage only.

Nothing here reads a price or a return.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEMBERSHIP = ROOT / "research_specs/alpha-opportunity-model-v1-us-membership.json.gz"
EVIDENCE = ROOT / "research_specs/alpha-opportunity-model-v3-us-identity-evidence.json.gz"
URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/{commit}/data/constituents.csv"
TIMEOUT = 25
SECTOR_COLUMNS = ("GICS Sector", "Sector")
SYMBOL_COLUMNS = ("Symbol",)
CIK_COLUMNS = ("CIK",)
MAX_SNAPSHOTS = 200


def fetch(commit: str) -> bytes:
    request = urllib.request.Request(URL.format(commit=commit), headers={"User-Agent": "investment-research-input-audit/1.0"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def parse(raw: bytes) -> dict:
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    sector = next((c for c in SECTOR_COLUMNS if c in (reader.fieldnames or [])), None)
    symbol = next((c for c in SYMBOL_COLUMNS if c in (reader.fieldnames or [])), None)
    if sector is None or symbol is None:
        raise ValueError("SECTOR_OR_SYMBOL_COLUMN_MISSING: %s" % (reader.fieldnames,))
    cik = next((c for c in CIK_COLUMNS if c in (reader.fieldnames or [])), None)
    rows = {}
    for row in reader:
        key = (row[symbol] or "").strip()
        if not key:
            continue
        rows[key] = {"sector": (row[sector] or "").strip() or None,
                     "cik": str(int(row[cik])) if cik and (row[cik] or "").strip().isdigit() else None}
    return {"sectorColumn": sector, "hasCik": cik is not None, "rows": rows}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    snapshots = json.loads(gzip.decompress(MEMBERSHIP.read_bytes()))["snapshots"]
    # Two snapshots share the date 2013-05-05, so a date alone is not an identity.
    pinned = {(s["date"], s["sourceCommit"]): s["rawCsvSha256"]
              for s in json.loads(gzip.decompress(EVIDENCE.read_bytes()))["snapshots"]}
    if len(snapshots) > MAX_SNAPSHOTS:
        raise ValueError("SNAPSHOT_COUNT_EXCEEDS_BOUND")
    out, failures = [], []
    for snap in snapshots:
        date, commit = snap["date"], snap["sourceCommit"]
        try:
            raw = fetch(commit)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            failures.append({"date": date, "commit": commit, "reason": "FETCH_FAILED: %s" % type(exc).__name__})
            continue
        digest = hashlib.sha256(raw).hexdigest()
        if digest != pinned.get((date, commit)):
            failures.append({"date": date, "commit": commit, "reason": "RAW_CSV_SHA256_DIFFERS_FROM_PINNED_EVIDENCE"})
            continue
        parsed = parse(raw)
        members = set(snap["members"])
        out.append({"date": date, "sourceCommit": commit, "rawCsvSha256": digest, "sectorColumn": parsed["sectorColumn"],
                    "hasCik": parsed["hasCik"], "rows": parsed["rows"],
                    "membersWithoutRow": sorted(members - set(parsed["rows"]))})
    payload = {"schema": "US_SP500_SNAPSHOT_SECTORS_V1", "source": "datasets/s-and-p-500-companies at the pinned per-snapshot commits",
               "requests": len(snapshots), "snapshots": out, "failures": failures,
               "label": "DATASET_PUBLISHED_SECTOR_AT_SNAPSHOT_NOT_AN_INDEX_PROVIDER_FILE"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    data = gzip.compress(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(), compresslevel=9, mtime=0)
    args.output.write_bytes(data)
    print("snapshots %d/%d verified, failures %d, bytes %d, sha256 %s" % (len(out), len(snapshots), len(failures), len(data), hashlib.sha256(data).hexdigest()))
    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(main())
