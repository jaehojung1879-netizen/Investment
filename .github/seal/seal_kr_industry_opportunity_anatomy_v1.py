#!/usr/bin/env python3
"""Temporary, byte-preserving result seal for kr-industry-opportunity-anatomy-v1. Runs only inside the sealing workflow.

It verifies the downloaded artifact archive and the files inside it and copies exact bytes into docs/results/ and
data/. It never calls an anatomy, cohort, feature, target or portfolio function and recomputes no statistic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

STUDY = "kr-industry-opportunity-anatomy-v1"
RUN_ID = 37182657697
ARTIFACT_ID = 11295658265
ARTIFACT_NAME = "kr-industry-opportunity-anatomy-v1-results-37182657697"
ARCHIVE_SHA256 = "ee336dc4ff51cbef21f3f8adbb780c5987e93525d677cdc7bdb5a7dd5400f4ba"
EXECUTION_SHA = "f830b92efabab6011f9190293f2e060e9b4fe70b"
SPEC_SHA256 = "98278ce5724b27dd19d253eab6cb1e7854ea432a62098441cdad46d067609f55"
SCIENTIFIC_STATUS = "EXPLORATORY_DEVELOPMENT_ON_PARTIALLY_RECONSTRUCTED_KR_HISTORY"
REQUIRED = ("industry-anatomy.json", "manifest.json", "execution-started.json")
DESTINATIONS = {
    "industry-anatomy.json": "docs/results/kr-industry-opportunity-anatomy-v1-result.json",
    "manifest.json": "docs/results/kr-industry-opportunity-anatomy-v1-manifest.json",
    "execution-started.json": "docs/results/kr-industry-opportunity-anatomy-v1-execution-started.json",
}
TABLE_DIR = "data/kr-industry-opportunity-anatomy-v1/tables"
PROVENANCE = "docs/results/kr-industry-opportunity-anatomy-v1-seal-provenance.json"
SPEC_PATH = "research_specs/kr-industry-opportunity-anatomy-v1.json"
SPEC_SIDECAR = "research_specs/kr-industry-opportunity-anatomy-v1.sha256"


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def check_main_state(root):
    root = Path(root)
    if (root / DESTINATIONS["industry-anatomy.json"]).exists() or (root / PROVENANCE).exists():
        raise SystemExit("RESULT_ALREADY_SEALED")
    spec = json.loads((root / SPEC_PATH).read_text())
    canonical = hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    if (root / SPEC_SIDECAR).read_text().strip() != SPEC_SHA256 or canonical != SPEC_SHA256:
        raise SystemExit("COMMITTED_SPEC_DIFFERS_FROM_THE_FROZEN_SPEC")


def check_artifact_metadata(meta):
    if meta.get("id") != ARTIFACT_ID or meta.get("name") != ARTIFACT_NAME:
        raise SystemExit("ARTIFACT_ID_OR_NAME_MISMATCH")
    if meta.get("expired"):
        raise SystemExit("ARTIFACT_EXPIRED")
    run = meta.get("workflow_run") or {}
    if run.get("id") != RUN_ID or run.get("head_sha") != EXECUTION_SHA:
        raise SystemExit("ARTIFACT_RUN_OR_SHA_MISMATCH")
    if meta.get("digest") != "sha256:" + ARCHIVE_SHA256:
        raise SystemExit("ARTIFACT_API_DIGEST_MISMATCH")


def verify_archive(archive):
    actual = sha256_file(archive)
    if actual != ARCHIVE_SHA256:
        raise SystemExit("ARCHIVE_SHA256_MISMATCH: " + actual)
    return actual


def extract_and_verify(archive, workdir):
    workdir = Path(workdir)
    if workdir.exists() and any(workdir.iterdir()):
        raise SystemExit("WORKDIR_NOT_CLEAN")
    workdir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            target = (workdir / info.filename).resolve()
            if workdir.resolve() not in target.parents and target != workdir.resolve():
                raise SystemExit("UNSAFE_ARCHIVE_MEMBER: " + info.filename)
        z.extractall(workdir)
    for name in REQUIRED:
        if not (workdir / name).is_file():
            raise SystemExit("MISSING_REQUIRED_FILE: " + name)
    manifest = json.loads((workdir / "manifest.json").read_text())
    for key, value in {"studyId": STUDY, "specSha256": SPEC_SHA256, "scientificStatus": SCIENTIFIC_STATUS}.items():
        if manifest.get(key) != value:
            raise SystemExit("MANIFEST_MISMATCH: " + key)
    for name, wanted in manifest["files"].items():
        path = workdir / name
        if not path.is_file() or sha256_file(path) != wanted:
            raise SystemExit("MANIFEST_FILE_HASH_MISMATCH: " + name)
    marker = json.loads((workdir / "execution-started.json").read_text())
    if marker.get("specSha256") != SPEC_SHA256 or marker.get("outcomesReadBeforeThisMarker") != 0:
        raise SystemExit("EXECUTION_MARKER_MISMATCH")
    return {"manifest": manifest, "marker": marker}


def seal(workdir, root, sealed_at_utc, verified, lock_refs):
    workdir, root = Path(workdir), Path(root)
    committed = {}
    for name, destination in DESTINATIONS.items():
        data = (workdir / name).read_bytes()
        target = root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        committed[destination] = {"sourceFile": name, "sha256": sha256_bytes(data), "bytes": len(data)}
    tables = {}
    for name in sorted(verified["manifest"]["files"]):
        if name.startswith("tables/"):
            data = (workdir / name).read_bytes()
            target = root / TABLE_DIR / Path(name).name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            tables[TABLE_DIR + "/" + Path(name).name] = {"sourceFile": name, "sha256": sha256_bytes(data), "bytes": len(data)}
    provenance = {
        "studyId": STUDY, "kind": "RESULT_SEAL_EXACT_ARTIFACT_BYTES", "executionRunId": RUN_ID, "executionSha": EXECUTION_SHA,
        "artifactName": ARTIFACT_NAME, "artifactId": ARTIFACT_ID, "artifactArchiveSha256": ARCHIVE_SHA256, "specSha256": SPEC_SHA256,
        "scientificStatus": SCIENTIFIC_STATUS, "inputIdentitySha256": verified["marker"].get("inputIdentitySha256"),
        "executionLock": {"observedRefs": lock_refs, "lockedMainSha": verified["marker"].get("lockedMainSha"), "lockRefInMarker": verified["marker"].get("lockRef")},
        "committedFiles": committed, "committedTables": tables, "sealedAtUtc": sealed_at_utc, "statisticsRecomputed": False,
        "statements": ["No scientific statistic was recomputed by this seal.",
                       "The committed result, manifest, execution marker and tables are the exact bytes of the artifact members (result renamed only).",
                       "Committing the result and marker paths makes the anatomy code refuse any further execution; the git-tag lock already consumed the study."],
    }
    (root / PROVENANCE).write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return provenance


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-main").add_argument("--root", default=".")
    sub.add_parser("check-metadata").add_argument("--metadata", required=True)
    p = sub.add_parser("seal")
    for a in ("--archive", "--workdir", "--sealed-at", "--lock-refs"):
        p.add_argument(a, required=True)
    p.add_argument("--root", default=".")
    args = parser.parse_args()
    if args.cmd == "check-main":
        check_main_state(args.root)
    elif args.cmd == "check-metadata":
        check_artifact_metadata(json.loads(Path(args.metadata).read_text()))
    else:
        verify_archive(args.archive)
        verified = extract_and_verify(args.archive, args.workdir)
        refs = [{"ref": r["ref"], "sha": r["object"]["sha"]} for r in json.loads(Path(args.lock_refs).read_text())]
        print(json.dumps(seal(args.workdir, args.root, args.sealed_at, verified, refs), indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
