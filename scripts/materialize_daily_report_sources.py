"""Make the blobs the daily brief reads present locally. The only step of the daily routine that may touch the network.

The renderer forbids lazy fetching, so a partial clone (`--filter=blob:none`) has none of the `signal-history` blobs it
needs. This reads ONLY the paths `daily_decision_report.ALLOWED` names, at one pinned full commit SHA, and writes nothing to
the working tree or the index (`git cat-file blob` only populates the object store). A path the commit does not contain is
reported as absent, never created.

    python scripts/materialize_daily_report_sources.py FULL_40_CHARACTER_SHA
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import daily_decision_report as R  # noqa: E402


def materialize(commit, root=ROOT):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("FULL_IMMUTABLE_SOURCE_SHA_REQUIRED")
    present, absent, failed = [], [], []
    for path in sorted(R.ALLOWED):
        tree = subprocess.run(["git", "ls-tree", commit, "--", path], cwd=root, capture_output=True, text=True)
        if tree.returncode:
            raise ValueError("COMMIT_NOT_AVAILABLE_LOCALLY: fetch the branch first")
        if not tree.stdout.strip():
            absent.append(path)
            continue
        blob = subprocess.run(["git", "cat-file", "blob", f"{commit}:{path}"], cwd=root, capture_output=True)
        (present if blob.returncode == 0 else failed).append(path)
    return {"commit": commit, "allowedPaths": len(R.ALLOWED), "present": len(present), "absentInCommit": len(absent),
            "failed": failed}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_ref", help="full 40-character signal-history commit SHA")
    args = parser.parse_args(argv)
    try:
        result = materialize(args.source_ref)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
