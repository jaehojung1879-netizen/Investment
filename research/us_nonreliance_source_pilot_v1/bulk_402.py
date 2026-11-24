"""Extract all Item 4.02 metadata in a fixed #354 issuer cohort from a local SEC ZIP."""
import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

CATALOG_BLOB = "e755d3529b39c0b5dfce5e98932e9225dd978a45"
FIELDS = ("form", "items", "filingDate", "acceptanceDateTime", "accessionNumber", "reportDate", "primaryDocument")


def file_sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cohort(path):
    raw = path.read_bytes()
    if hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() != CATALOG_BLOB:
        raise ValueError("not the frozen #354 catalog")
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return sorted({f"{int(r['cik']):010d}" for r in csv.DictReader(f)})


def extract(archive, ciks, start, through):
    if date.fromisoformat(start) > date.fromisoformat(through):
        raise ValueError("invalid date range")
    if len(set(ciks)) != len(ciks):
        raise ValueError("duplicate cohort CIK")
    names = {}
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = PurePosixPath(info.filename).name
        if name in names:
            raise ValueError("duplicate archive basename: " + name)
        names[name] = info
    records, coverage = {}, []
    for cik in sorted(ciks):
        state = {"cik": cik, "pages": [], "missingPages": [], "itemUnknown": 0, "forms": 0}
        seen = {}

        def load(name):
            if name not in names:
                state["missingPages"].append(name)
                return None
            raw = archive.read(names[name])
            state["pages"].append({"name": name, "sha256": hashlib.sha256(raw).hexdigest()})
            return json.loads(raw)

        def scan(block, source):
            n = len(block["form"])
            if any(not isinstance(block.get(f), list) or len(block[f]) != n for f in FIELDS):
                raise ValueError("misaligned SEC columns: " + source)
            for i, form in enumerate(block["form"]):
                if form not in {"8-K", "8-K/A"}:
                    continue
                row = {f: block[f][i] for f in FIELDS}
                d = row["filingDate"]
                date.fromisoformat(d)
                if not start <= d <= through:
                    continue
                accession = row["accessionNumber"]
                if not accession:
                    raise ValueError("missing accession")
                if accession in seen:
                    if seen[accession] != row:
                        raise ValueError("conflicting accession: " + accession)
                    continue
                seen[accession] = row
                state["forms"] += 1
                items = {s.strip() for s in (row["items"] or "").split(",") if s.strip()}
                if not items:
                    state["itemUnknown"] += 1
                if "4.02" in items:
                    records[(cik, accession)] = {"cik": cik, **row, "page": source,
                                                "timestampStatus": "RAW_UNVERIFIED",
                                                "hasItem202": "2.02" in items}

        root = f"CIK{cik}.json"
        first = load(root)
        if first is not None:
            if f"{int(first['cik']):010d}" != cik:
                raise ValueError("issuer mismatch: " + root)
            scan(first["filings"]["recent"], root)
            for descriptor in first["filings"]["files"]:
                if descriptor["filingTo"] < start or descriptor["filingFrom"] > through:
                    continue
                page = descriptor["name"]
                if not page.startswith(f"CIK{cik}-submissions-") or PurePosixPath(page).name != page:
                    raise ValueError("unexpected historical page: " + page)
                block = load(page)
                if block is not None:
                    scan(block, page)
        state["status"] = ("INCOMPLETE_PAGES" if state["missingPages"] else
                           "UNKNOWN_ITEM_CODES" if state["itemUnknown"] else "DECLARED_PAGES_SCANNED")
        coverage.append(state)
    rows = [records[k] for k in sorted(records)]
    return {"start": start, "through": through, "cohortCount": len(ciks),
            "coverageCounts": dict(Counter(r["status"] for r in coverage)),
            "records": rows, "issuers": coverage,
            "unique402": len(rows), "unique402Without202": sum(not r["hasItem202"] for r in rows),
            "evidenceStatus": "METADATA_ONLY_NOT_PIT_ADMITTED"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("catalog", type=Path)
    p.add_argument("submissions_zip", type=Path)
    p.add_argument("--start", default="2014-01-01")
    p.add_argument("--through", required=True)
    a = p.parse_args()
    with ZipFile(a.submissions_zip) as z:
        report = extract(z, cohort(a.catalog), a.start, a.through)
    report["archiveSha256"] = file_sha(a.submissions_zip)
    report["catalogGitBlob"] = CATALOG_BLOB
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
