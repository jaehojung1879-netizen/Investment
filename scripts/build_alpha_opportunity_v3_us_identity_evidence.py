"""Seal the identity columns behind the pinned US membership observations.

    git clone https://github.com/datasets/s-and-p-500-companies <checkout>
    python scripts/build_alpha_opportunity_v3_us_identity_evidence.py <checkout> \
        research_specs/alpha-opportunity-model-v3-us-identity-evidence.json.gz

The pinned membership (`alpha-opportunity-model-v1-us-membership.json.gz`)
keeps only the Symbol column of each upstream commit. Identity needs the
other columns that the SAME commits state: the security name and, from 2019
on, the SEC CIK. This reads exactly the commits the pinned file cites, checks
that the Symbol column reproduces the pinned member list for every one of
them, and writes each commit's raw-CSV hash plus its (rawSymbol, name, CIK)
rows. Metadata only: no price, no return.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / "research_specs/alpha-opportunity-model-v1-us-membership.json.gz"
NAME_COLUMNS = ("Security", "Name", "Company")


def build(checkout):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(checkout), *args])

    pinned = json.loads(gzip.decompress(PINNED.read_bytes()))
    rows_table, row_index, snapshots = [], {}, []
    for snap in pinned["snapshots"]:
        raw = git("show", snap["sourceCommit"] + ":data/constituents.csv")
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
        header = list(rows[0].keys())
        members = sorted({r["Symbol"].replace(".", "-") for r in rows if r.get("Symbol")})
        if members != snap["members"]:
            raise ValueError("UPSTREAM_DOES_NOT_REPRODUCE_PINNED_SNAPSHOT: " + snap["sourceCommit"])
        name_col = next(c for c in NAME_COLUMNS if c in header)
        ids = []
        for r in rows:
            if not r.get("Symbol"):
                continue
            key = (r["Symbol"], (r.get(name_col) or "").strip(), (r.get("CIK") or "").strip() or None)
            if key not in row_index:
                row_index[key] = len(rows_table)
                rows_table.append(list(key))
            ids.append(row_index[key])
        snapshots.append({"date": snap["date"], "sourceCommit": snap["sourceCommit"],
                          "rawCsvSha256": hashlib.sha256(raw).hexdigest(), "nameColumn": name_col,
                          "hasCik": "CIK" in header, "rows": sorted(ids)})
    return {"schema": "US_MEMBERSHIP_IDENTITY_EVIDENCE_V1", "source": pinned["source"],
            "ref": pinned["ref"], "pinnedMembershipSha256": hashlib.sha256(PINNED.read_bytes()).hexdigest(),
            "reproducesPinnedMembers": True,
            "rowFields": ["rawSymbol", "name", "cik"], "rows": rows_table, "snapshots": snapshots}


def main(argv=None):
    argv = argv or sys.argv[1:]
    value = build(Path(argv[0]))
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    Path(argv[1]).write_bytes(gzip.compress(raw, mtime=0))
    print(len(value["rows"]), "distinct identity rows over", len(value["snapshots"]), "snapshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
