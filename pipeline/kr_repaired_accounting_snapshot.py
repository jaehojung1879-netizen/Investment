"""Frozen identity, provenance and measured coverage of the repaired KR accounting input.

Data-foundation only. Nothing here reads a price, a return, a label or any Alpha
artifact; it reads accounting filing records and never changes them. The snapshot
is the `kr-candidate-merged` directory at the pinned `signal-history` source
commit: `kr-canonical-v2` (raw DART statement rows) united with
`kr-xbrl-original` (fiscal-2015 Q1/H1/Q3 original XBRL), produced by
`scripts/merge_kr_candidate_snapshot.py`.

Two identities are kept apart on purpose:
* the CANDIDATE identity is the convention v1-v3 validation used (SHA-256 of the
  compact sorted mapping shard-file -> git blob SHA-1). It ties this snapshot to
  the validated candidate;
* the CONTENT identity hashes the decoded records, so it does not depend on gzip
  bytes, shard boundaries' compression, or input order.
"""
from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from . import dart_fundamentals as DF

STUDY = "kr-repaired-accounting-snapshot-v1"
SOURCE_COMMIT = "fb6e83743fd8cdba647d1522a4645b662a9d5647"
FROZEN_CONTENT_SHA256 = "e0199d98679357f405de9a95a4091045db814d65af61e2c698af1a70d54fda58"
CANDIDATE_SHA256 = "af642e7e79e9ba59ac6ee14faf033f4d63887188bab6506845c082e21dc3d1cc"
FAMILY_ACCOUNTS = {"assets": "자산총계", "liabilities": "부채총계", "net_income": "당기순이익",
                   "operating_cash_flow": "영업활동현금흐름"}
# Files whose exact bytes define how the snapshot was produced and is read.
CODE_FILES = (
    "scripts/merge_kr_candidate_snapshot.py",
    "scripts/build_kr_canonical_filings.py",
    "pipeline/dart_canonical_accounts.py",
    "pipeline/dart_xbrl_statements.py",
    "pipeline/dart_fundamentals.py",
    "pipeline/dart_derive.py",
    "pipeline/historical_store.py",
    "pipeline/accounting_quality.py",
    "pipeline/alpha_opportunity_features.py",
)


def canonical_line(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_shard(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def shard_files(directory: Path) -> list[Path]:
    return sorted(p for p in Path(directory).glob("dart*.jsonl.gz"))


def content_sha256(shards: dict[str, list[dict]]) -> str:
    """Order- and compression-independent hash of decoded records."""
    h = hashlib.sha256()
    for name in sorted(shards):
        h.update((name + "\n").encode())
        for record in sorted(shards[name], key=lambda r: r["id"]):
            h.update((canonical_line(record) + "\n").encode())
    return h.hexdigest()


def candidate_identity(blob_sha1_by_shard: dict[str, str]) -> str:
    return sha256(json.dumps(blob_sha1_by_shard, sort_keys=True, separators=(",", ":")).encode())


def _measure(rows: list[dict]) -> dict:
    """Descriptive coverage only; no value is interpreted."""
    ids = [r["id"] for r in rows]
    by_source = Counter(str(r.get("source", "")).split(":fnlttSinglAcntAll")[0] + (
        ":" + str(r["fsDiv"]) if r.get("fsDiv") else "") for r in rows)
    stage = Counter(r["reportCode"] for r in rows)
    year = Counter(int(r["fiscalYear"]) for r in rows)
    availability = [r["availableFrom"] for r in rows if r.get("availableFrom")]
    present = {f: sum(1 for r in rows if a in (r.get("accounts") or {}))
               for f, a in FAMILY_ACCOUNTS.items()}
    all_four = sum(1 for r in rows if all(a in (r.get("accounts") or {}) for a in FAMILY_ACCOUNTS.values()))
    receipt_mismatch = sum(1 for r in rows if {x[:8] for x in (r.get("receiptNos") or [])} !=
                           {str(r.get("availableFrom", "")).replace("-", "")})
    late = 0
    for r in rows:
        deadline = DF.filing_deadline(int(r["fiscalYear"]), r["reportCode"])
        if deadline and r.get("availableFrom") and r["availableFrom"] > deadline:
            late += 1
    xbrl_basis = Counter()
    for r in rows:
        for entry in ((r.get("canonicalization") or {}).get("accounts") or {}).values():
            if isinstance(entry, dict) and entry.get("statementBasis"):
                xbrl_basis[entry["statementBasis"]] += 1
    return {
        "records": len(rows), "distinctIds": len(set(ids)),
        "distinctTickers": len({r["ticker"] for r in rows}),
        "bySourceAndFsDiv": dict(sorted(by_source.items())),
        "byReportCode": dict(sorted(stage.items())), "byFiscalYear": dict(sorted(year.items())),
        "fiscalYearRange": [min(year), max(year)] if year else None,
        "availableFromRange": [min(availability), max(availability)] if availability else None,
        "recordsWithAccount": present, "recordsWithAllFourFamilies": all_four,
        "recordsMissingAnyFamily": len(rows) - all_four,
        "recordsWithMultipleReceipts": sum(1 for r in rows if len(r.get("receiptNos") or []) > 1),
        "recordsWithReceiptDateNotEqualToAvailableFrom": receipt_mismatch,
        "recordsAvailableAfterStatutoryDeadline": late,
        "perAccountStatementBasisFromXbrl": dict(sorted(xbrl_basis.items())),
    }


def build_manifest(merged_dir: Path, canonical_dir: Path, xbrl_dir: Path, code_root: Path) -> dict:
    merged = {p.name: read_shard(p) for p in shard_files(merged_dir)}
    raw = {p.name: p.read_bytes() for p in shard_files(merged_dir)}
    blobs = {n: git_blob_sha1(b) for n, b in raw.items()}
    rows = [r for name in sorted(merged) for r in merged[name]]
    report = json.loads((Path(merged_dir) / "merge-report.json").read_text(encoding="utf-8"))
    canon_files = {p.name: git_blob_sha1(p.read_bytes()) for p in shard_files(canonical_dir)}
    xbrl_files = {p.name: git_blob_sha1(p.read_bytes()) for p in sorted(Path(xbrl_dir).glob("dart-xbrl-*.jsonl.gz"))}
    per_shard = {n: {"records": len(merged[n]), "gitBlobSha1": blobs[n], "fileSha256": sha256(raw[n]),
                     "contentSha256": content_sha256({n: merged[n]})} for n in sorted(merged)}
    return {
        "study": STUDY, "version": 1,
        "sourceCommit": SOURCE_COMMIT,
        "candidateIdentitySha256": candidate_identity(blobs),
        "snapshotContentSha256": content_sha256(merged),
        "recordCount": len(rows),
        "shards": per_shard,
        "inputs": {"kr-canonical-v2": canon_files, "kr-xbrl-original": xbrl_files,
                   "mergeReport": report},
        "code": {name: git_blob_sha1((Path(code_root) / name).read_bytes()) for name in CODE_FILES},
        "coverage": _measure(rows),
        "coverageByShard": {n: _measure(merged[n]) for n in sorted(merged)},
    }


def regenerate_and_compare(canonical_dir: Path, xbrl_dir: Path, merged_dir: Path, root: Path) -> dict:
    """Re-run the merger from its two sources and compare with the frozen shards."""
    import sys
    sys.path.insert(0, str(root))
    from scripts.merge_kr_candidate_snapshot import merge
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "merged"
        merge(out, Path(canonical_dir), Path(xbrl_dir))
        names = {p.name for p in shard_files(out)}
        frozen = {p.name for p in shard_files(merged_dir)}
        identical = names == frozen and all((out / n).read_bytes() == (Path(merged_dir) / n).read_bytes()
                                            for n in names)
        regenerated = {n: read_shard(out / n) for n in sorted(names)}
        return {"shardSetEqual": names == frozen, "byteIdentical": identical,
                "contentSha256": content_sha256(regenerated),
                "mergeReportEqual": (out / "merge-report.json").read_bytes() ==
                                    (Path(merged_dir) / "merge-report.json").read_bytes()}


def git_show(commit: str, path: str, cwd: Path) -> bytes:
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=cwd)


def materialize_from_git(root: Path, target: Path, commit: str = SOURCE_COMMIT) -> dict[str, Path]:
    """Copy only the frozen snapshot's own directories from a git object; never a checkout."""
    layout = {"merged": "ledger/fundamentals/kr-candidate-merged", "canonical": "ledger/fundamentals/kr-canonical-v2",
              "xbrl": "ledger/fundamentals/kr-xbrl-original"}
    out = {}
    for key, prefix in layout.items():
        directory = Path(target) / key
        directory.mkdir(parents=True, exist_ok=True)
        listing = subprocess.check_output(["git", "ls-tree", "--name-only", commit, prefix + "/"], cwd=root,
                                          text=True).split("\n")
        for entry in filter(None, listing):
            name = entry.rsplit("/", 1)[-1]
            if name.endswith(".jsonl.gz") or name == "merge-report.json":
                (directory / name).write_bytes(git_show(commit, entry, root))
        out[key] = directory
    return out
