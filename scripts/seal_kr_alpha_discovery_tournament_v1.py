#!/usr/bin/env python3
"""Automatic Draft result seal for kr-alpha-discovery-tournament-v1. Standard library only; imports nothing but `pipeline.kr_alpha_tournament_seal`.

check-main  the frozen spec exists and nothing is sealed on the checked-out commit
seal        verify run, jobs, artifact metadata, archive digest, file list, manifest, marker, spec and lock refs; copy the exact bytes; write provenance
open-pr     re-verify the written bytes against provenance and open ONE Draft pull request (never merges, never marks ready). If only the PR API call
            is refused it exits 3 with a RECOVERABLE_SEAL_HANDOFF_FAILURE record: the exact bytes are already on the pushed branch and a human opens the
            Draft PR by hand; the execution is never rerun

It never recomputes, reruns or reinterprets an outcome. Any mismatch stops with a non-zero exit and no pull request.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import kr_alpha_tournament_seal as SEAL  # noqa: E402


def github_api(method, path, payload=None):
    request = urllib.request.Request(
        "https://api.github.com/repos/" + os.environ["GITHUB_REPOSITORY"] + path,
        data=None if payload is None else json.dumps(payload).encode(), method=method,
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"], "Content-Type": "application/json", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, {}
    except (urllib.error.URLError, TimeoutError):
        return 0, {}


def seal(args, api=github_api):
    root = Path(args.root)
    spec_sha = SEAL.check_main(root)
    run = json.loads(Path(args.run).read_text())
    jobs = json.loads(Path(args.jobs).read_text())["jobs"]
    meta = json.loads(Path(args.metadata).read_text())
    SEAL.verify_run(run, jobs, args.main_sha)
    archive_sha = SEAL.check_artifact_metadata(meta, args.run_id)
    files = SEAL.read_archive(Path(args.archive).read_bytes(), archive_sha)
    SEAL.verify_bundle(files, spec_sha, args.main_sha)
    SEAL.verify_locks(api, spec_sha, args.main_sha)
    record = SEAL.write_seal(files, root, {
        "executionRunId": int(args.run_id), "executionSha": args.main_sha, "sealBranchBaseSha": args.main_sha, "runEvent": run["event"],
        "runConclusionOfExecuteJob": "success", "artifactName": meta["name"], "artifactId": meta["id"], "artifactGithubDigest": meta["digest"],
        "artifactArchiveSha256": archive_sha, "artifactFileList": sorted(files), "specSha256": spec_sha,
        "lockRefs": [SEAL.LOCK_PREFIX, SEAL.LOCK_PREFIX + "-" + spec_sha], "sealedAtUtc": args.sealed_at})
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check-main")
    check.add_argument("--root", default=".")
    s = sub.add_parser("seal")
    for name in ("--root", "--run-id", "--main-sha", "--run", "--jobs", "--metadata", "--archive", "--sealed-at"):
        s.add_argument(name, required=name != "--root", default="." if name == "--root" else None)
    o = sub.add_parser("open-pr")
    o.add_argument("--root", default=".")
    o.add_argument("--head", required=True)
    args = parser.parse_args(argv)
    if args.command == "check-main":
        print(SEAL.check_main(args.root))
    elif args.command == "seal":
        print(json.dumps(seal(args), sort_keys=True))
    else:
        record = SEAL.verify_written(args.root)
        try:
            print(SEAL.open_draft_pr(github_api, args.head, "main", record, owner=os.environ["GITHUB_REPOSITORY"].split("/")[0], sleep=time.sleep))
        except SEAL.RecoverableSealHandoff as error:
            handoff = SEAL.manual_handoff(error.head, error.base, error.record)
            print(json.dumps(dict(handoff, httpStatus=error.status), sort_keys=True))
            summary = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary:
                with open(summary, "a") as stream:
                    stream.write("## " + SEAL.HANDOFF_CLASSIFICATION + "\n\nThe formal execution SUCCEEDED and the exact-byte seal is on the pushed branch `" + error.head
                                 + "`. Only the Draft PR API call was refused (HTTP " + str(error.status) + "). This is not an execution or scientific failure and "
                                 "the execution must NOT be rerun.\n\n" + "\n".join("- " + step for step in handoff["manualSteps"]) + "\n")
            sys.exit(SEAL.HANDOFF_EXIT_CODE)


if __name__ == "__main__":
    main()
