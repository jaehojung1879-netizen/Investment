"""Read-only audit of the frozen #354 Item 2.02 catalog; never read returns."""
import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BLOB = "e755d3529b39c0b5dfce5e98932e9225dd978a45"
NY = ZoneInfo("America/New_York")
FIELDS = ("ticker", "cik", "form", "items", "filingDate", "acceptanceDateTime", "accession", "reportDate")


def tokens(row):
    return {x.strip() for x in row["items"].split(",")}


def key(row):
    return str(int(row["cik"])), row["accession"]


def audit(rows):
    unique = {}
    both = 0
    for row in rows:
        if row["form"] not in {"8-K", "8-K/A"} or "2.02" not in tokens(row):
            raise ValueError("outside Item 2.02 catalog")
        both += "4.02" in tokens(row)
        k = key(row)
        signature = tuple(row[f] for f in FIELDS if f not in {"ticker", "cik"})
        if k in unique and unique[k][0] != signature:
            raise ValueError("conflicting issuer/accession metadata")
        unique[k] = (signature, row)
    selected = [v[1] for v in unique.values() if "4.02" in tokens(v[1])]
    return {"rawRows": len(rows), "uniqueIssuerAccessions": len(unique),
            "issuers": len({k[0] for k in unique}), "bothRawRows": both,
            "bothUniqueIssuerAccessions": len(selected),
            "bothIssuers": len({key(r)[0] for r in selected}),
            "bothSince2014": sum(r["filingDate"] >= "2014-01-01" for r in selected),
            "bothByYear": dict(sorted(Counter(r["filingDate"][:4] for r in selected).items())),
            "scope": "INTERSECTION_ONLY_NOT_FULL_ITEM_402_POPULATION"}


def effective_day(local):
    return (local.date() + timedelta(days=int(local.hour >= 16))).isoformat()


def compare_index(raw, eastern):
    """Compare the existing UTC assumption against an independently read SEC index clock."""
    assumed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if assumed.tzinfo is None:
        raise ValueError("missing offset")
    if not eastern:
        return {"status": "UNVERIFIED"}
    observed = datetime.fromisoformat(eastern)
    if observed.tzinfo is not None:
        raise ValueError("SEC index field must be local clock")
    # Reject ambiguous/nonexistent DST clocks rather than invent an instant.
    a, b = (observed.replace(tzinfo=NY, fold=f) for f in (0, 1))
    if a.utcoffset() != b.utcoffset():
        return {"status": "UNVERIFIED_DST_CLOCK"}
    delta = (assumed - a).total_seconds()
    return {"status": "MATCH" if delta == 0 else "MISMATCH",
            "differenceSeconds": delta,
            "existingEffectiveCalendarDay": effective_day(assumed.astimezone(NY)),
            "indexEffectiveCalendarDay": effective_day(a)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("catalog", type=Path, help="Exact frozen #354 us-8k-item202.csv.gz")
    p.add_argument("--index-sample", type=Path, default=Path(__file__).with_name("index_sample.csv"))
    a = p.parse_args()
    raw = a.catalog.read_bytes()
    git_blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    if git_blob != BLOB:
        raise ValueError("unexpected catalog Git blob")
    with gzip.open(a.catalog, "rt", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("catalog schema changed")
        rows = list(reader)
    report = audit(rows)
    by_key = {key(r): r for r in rows}
    with a.index_sample.open(encoding="utf-8", newline="") as f:
        sample = list(csv.DictReader(f))
    if len({key(r) for r in sample}) != len(sample):
        raise ValueError("duplicate sample key")
    checks = []
    for row in sample:
        original = by_key[key(row)]
        checks.append({"cik": key(row)[0], "accession": row["accession"],
                       **compare_index(original["acceptanceDateTime"], row["indexEastern"])})
    report.update(gitBlob=git_blob, sha256=hashlib.sha256(raw).hexdigest(),
                  indexSampleChecks=checks, indexSampleCounts=dict(Counter(r["status"] for r in checks)))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
