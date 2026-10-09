"""One exact original artifact download; no recollection or retry fallback."""

from pathlib import Path
import subprocess

from .contract import file_hash
from .lifecycle import GitHub


def download(spec, path):
    pin = spec["frozenArtifact"]
    github = GitHub()
    meta = github.api("actions/artifacts/" + str(pin["artifactId"]))
    if (
        meta["name"] != pin["artifactName"]
        or meta["workflow_run"]["id"] != pin["producingRunId"]
        or meta["expired"]
        or meta.get("digest") != "sha256:" + pin["archiveSha256"]
    ):
        raise ValueError("ORIGINAL_ARTIFACT_UNAVAILABLE_OR_IDENTITY_CHANGED")
    path = Path(path)
    if path.exists():
        raise ValueError("FRESH_ARCHIVE_PATH_REQUIRED")
    # gh follows the signed redirect without exposing authorization or URL.
    with path.open("xb") as stream:
        process = subprocess.run(
            ["gh", "api", "repos/" + github.repository + "/actions/artifacts/" + str(pin["artifactId"]) + "/zip"],
            stdout=stream,
            stderr=subprocess.PIPE,
        )
    if process.returncode or file_hash(path) != pin["archiveSha256"]:
        raise ValueError("EXACT_ARCHIVE_RETRIEVAL_FAILED_BEFORE_LOCK")
    return path
