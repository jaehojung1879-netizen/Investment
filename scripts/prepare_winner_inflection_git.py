"""Inspect WID local readiness, or explicitly restore metadata from a local donor.

No network fetch, raw payload recovery, approval, label or model execution.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import industry_foundation as IF  # noqa: E402
from pipeline import winner_inflection_admission as A  # noqa: E402
from pipeline.winner_inflection_local_git import restore_metadata  # noqa: E402
from scripts import inspect_experiment_sources as S  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", default="inspect", choices=("inspect", "restore-metadata"))
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--donor", type=Path)
    args = parser.parse_args(argv)
    spec = json.loads((ROOT / A.SPEC_PATH).read_bytes())
    result = {
        "mode": args.mode,
        "sourceCommit": spec["sourceCommit"],
        "metadataCommit": spec["metadataCommit"],
        "outcomeReads": 0,
        "modelFits": 0,
        "networkRequests": 0,
        "executionAuthorized": False,
    }
    if args.mode == "restore-metadata":
        if args.donor is None:
            parser.error("restore-metadata requires an explicit local --donor")

        def validate(raw):
            value = json.loads(raw)
            if IF.digest({k: v for k, v in value.items() if k != "sha256"}) != spec["sourceManifestSha256"]:
                raise ValueError("REGISTERED_MANIFEST_CHANGED")

        result["recovery"] = restore_metadata(
            args.repo,
            args.donor,
            [spec["sourceCommit"], spec["metadataCommit"]],
            spec["sourceCommit"],
            S.MANIFEST,
            validate,
        )
    result["sourcePreflight"] = A.source_preflight(args.repo, spec)
    print(json.dumps(result, indent=2))
    return 0 if result["sourcePreflight"]["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
