#!/usr/bin/env python3
"""Temporary, byte-preserving result seal for kr-factor-anatomy-v1. Runs only inside the sealing workflow.

It verifies the downloaded artifact archive and the files inside it and copies exact bytes into docs/results/. It
imports nothing from `pipeline` except the canonical-JSON digest helper used to check the committed spec, never
calls an anatomy or portfolio function, and recomputes no statistic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

STUDY = "kr-factor-anatomy-v1"
RUN_ID = 36960496371
ARTIFACT_ID = 11207962601
ARTIFACT_NAME = "kr-factor-anatomy-v1-results-36960496371"
ARCHIVE_SHA256 = "f8020bdac9878f523091881d129e3c414234012c17e1fd61e1e49b6d6538b80f"
EXECUTION_SHA = "cd82a5b7edb08f18ccdaa3f231415354aef9a41c"
SPEC_SHA256 = "ceb97f481ae7261e89da4467fba03465f0c78cc3654cd799c26e5088ee3bc3d2"
INPUT_IDENTITY_SHA256 = "233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7"
SCIENTIFIC_STATUS = "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"
REQUIRED = ("anatomy.json", "manifest.json", "report.md")
DESTINATIONS = {
    "anatomy.json": "docs/results/kr-factor-anatomy-v1-result.json",
    "report.md": "docs/results/kr-factor-anatomy-v1-report.md",
    "manifest.json": "docs/results/kr-factor-anatomy-v1-manifest.json",
}
PROVENANCE = "docs/results/kr-factor-anatomy-v1-seal-provenance.json"
SPEC_PATH = "research_specs/kr-factor-anatomy-v1.json"
SPEC_SIDECAR = "research_specs/kr-factor-anatomy-v1.sha256"


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def check_main_state(root):
    """The committed spec is exactly the frozen one and no result is already on main."""
    root = Path(root)
    if (root / DESTINATIONS["anatomy.json"]).exists() or (root / PROVENANCE).exists():
        raise SystemExit("RESULT_ALREADY_SEALED_ON_MAIN")
    sys.path.insert(0, str(root))
    from pipeline.alpha_opportunity_spec import digest  # canonical-JSON digest only
    spec = json.loads((root / SPEC_PATH).read_text())
    if (root / SPEC_SIDECAR).read_text().strip() != SPEC_SHA256 or digest(spec) != SPEC_SHA256:
        raise SystemExit("COMMITTED_SPEC_DIFFERS_FROM_THE_FROZEN_SPEC")
    if spec["input"]["identitySha256"] != INPUT_IDENTITY_SHA256:
        raise SystemExit("COMMITTED_INPUT_IDENTITY_DIFFERS")


def check_artifact_metadata(meta, workflow_run_head_sha=None):
    """`meta` is the JSON of GET /repos/{repo}/actions/artifacts/{id}."""
    if meta.get("id") != ARTIFACT_ID or meta.get("name") != ARTIFACT_NAME:
        raise SystemExit("ARTIFACT_ID_OR_NAME_MISMATCH")
    if meta.get("expired"):
        raise SystemExit("ARTIFACT_EXPIRED")
    run = meta.get("workflow_run") or {}
    if run.get("id") != RUN_ID:
        raise SystemExit("ARTIFACT_RUN_MISMATCH")
    if run.get("head_sha") != EXECUTION_SHA:
        raise SystemExit("ARTIFACT_EXECUTION_SHA_MISMATCH")
    digest = meta.get("digest")
    if digest is not None and digest != "sha256:" + ARCHIVE_SHA256:
        raise SystemExit("ARTIFACT_API_DIGEST_MISMATCH")
    return True


def verify_archive(archive):
    """Fail closed unless the archive bytes hash to exactly the expected digest. Nothing is extracted before this."""
    actual = sha256_file(archive)
    if actual != ARCHIVE_SHA256:
        raise SystemExit("ARCHIVE_SHA256_MISMATCH: " + actual)
    return actual


def extract_and_verify(archive, workdir):
    """Extract into a clean directory and verify manifest provenance and every file hash the manifest records."""
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
    expected = {"studyId": STUDY, "specSha256": SPEC_SHA256, "inputIdentitySha256": INPUT_IDENTITY_SHA256,
                "scientificStatus": SCIENTIFIC_STATUS}
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise SystemExit("MANIFEST_MISMATCH: " + key)
    recorded = manifest["files"]
    for name in ("anatomy.json", "report.md"):
        if recorded.get(name) != sha256_file(workdir / name):
            raise SystemExit("MANIFEST_FILE_HASH_MISMATCH: " + name)
    tables = 0
    for name, wanted in recorded.items():
        if name in ("anatomy.json", "report.md"):
            continue
        path = workdir / name
        if not path.is_file() or sha256_file(path) != wanted:
            raise SystemExit("MANIFEST_FILE_HASH_MISMATCH: " + name)
        tables += 1
    return {"manifest": manifest, "tablesVerifiedNotCommitted": tables}


def seal(workdir, root, sealed_at_utc, verified):
    """Copy the exact bytes and write the provenance record. No statistic is read or recomputed."""
    workdir, root = Path(workdir), Path(root)
    committed = {}
    for name, destination in DESTINATIONS.items():
        data = (workdir / name).read_bytes()
        target = root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        committed[destination] = {"sourceFile": name, "sha256": sha256_bytes(data), "bytes": len(data)}
    provenance = {
        "studyId": STUDY,
        "kind": "RESULT_SEAL_EXACT_ARTIFACT_BYTES",
        "executionRunId": RUN_ID,
        "executionSha": EXECUTION_SHA,
        "artifactName": ARTIFACT_NAME,
        "artifactId": ARTIFACT_ID,
        "artifactArchiveSha256": ARCHIVE_SHA256,
        "specSha256": SPEC_SHA256,
        "inputIdentitySha256": INPUT_IDENTITY_SHA256,
        "scientificStatus": SCIENTIFIC_STATUS,
        "committedFiles": committed,
        "artifactTablesVerifiedNotCommitted": verified["tablesVerifiedNotCommitted"],
        "tablesNote": "tables/*.csv.gz remain only in the (expiring) Actions artifact; their hashes are recorded in the committed manifest.",
        "sealedAtUtc": sealed_at_utc,
        "statisticsRecomputed": False,
        "statements": [
            "No scientific statistic was recomputed by this seal.",
            "The committed result, report and manifest are the exact bytes of the artifact members anatomy.json, report.md and manifest.json (renamed only).",
            "Committing the result path makes the anatomy workflow refuse any further execute (ANATOMY_RESULT_ALREADY_COMMITTED).",
        ],
    }
    out = root / PROVENANCE
    out.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return provenance


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-main").add_argument("--root", default=".")
    p = sub.add_parser("check-metadata")
    p.add_argument("--metadata", required=True)
    p = sub.add_parser("verify-archive")
    p.add_argument("--archive", required=True)
    p = sub.add_parser("seal")
    p.add_argument("--archive", required=True)
    p.add_argument("--workdir", required=True)
    p.add_argument("--root", default=".")
    p.add_argument("--sealed-at", required=True)
    args = parser.parse_args()
    if args.cmd == "check-main":
        check_main_state(args.root)
    elif args.cmd == "check-metadata":
        check_artifact_metadata(json.loads(Path(args.metadata).read_text()))
    elif args.cmd == "verify-archive":
        print(verify_archive(args.archive))
    else:
        verify_archive(args.archive)
        verified = extract_and_verify(args.archive, args.workdir)
        print(json.dumps(seal(args.workdir, args.root, args.sealed_at, verified), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
