"""Human authorization, GitHub permanent one-shot lock, and ordered preparation."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .contract import ROOT, SPEC, canonical, digest, file_hash, load
from .executor import Budget, execute, persist
from .labels import Counters, formal_permit
from pipeline.kr_model_raw_snapshot import immutable_bytes

REPOSITORY = "jaehojung1879-netizen/Investment"
HUMAN = "jaehojung1879-netizen"


_LOCK_PROOF = object()


@dataclass(frozen=True)
class VerifiedLock:
    document: dict
    proof: object = field(repr=False, default=None)


class GitHub:
    def __init__(self, repository=REPOSITORY):
        if repository != REPOSITORY:
            raise ValueError("WRONG_REPOSITORY")
        self.repository = repository

    def api(self, path, method="GET", payload=None):
        command = ["gh", "api", "repos/" + self.repository + "/" + path, "--method", method]
        if payload is not None:
            command += ["--input", "-"]
        process = subprocess.run(
            command, input=canonical(payload) if payload is not None else None, capture_output=True, timeout=60
        )
        if process.returncode:
            raise RuntimeError("GITHUB_REQUEST_REFUSED: " + path)  # Never echo tokens/stdin.
        return json.loads(process.stdout)

    def main(self):
        return self.api("git/ref/heads/main")["object"]["sha"]

    def locks(self, prefix):
        return self.api("git/matching-refs/tags/" + prefix.removeprefix("refs/tags/"))

    def previous_results(self, prefix):
        page = 1
        while page <= 1000:
            artifacts = self.api(f"actions/artifacts?per_page=100&page={page}")["artifacts"]
            if any(a["name"].startswith(prefix) for a in artifacts):
                return True
            if len(artifacts) < 100:
                return False
            page += 1
        raise RuntimeError("PREVIOUS_ARTIFACT_HISTORY_EXCEEDS_PREFLIGHT_LIMIT")

    def claim(self, prefix, head, spec_sha):
        # GitHub ref POST is atomic; an existing ref (422) is a refusal, never retry.
        self.api("git/refs", "POST", {"ref": prefix, "sha": head})
        self.api("git/refs", "POST", {"ref": prefix + "-spec-" + spec_sha, "sha": head})
        lock = self.api("git/ref/" + prefix.removeprefix("refs/"))
        if lock["object"]["sha"] != head:
            raise RuntimeError("PERMANENT_LOCK_VERIFICATION_FAILED")
        return VerifiedLock({"ref": prefix, "sha": head, "specSha256": spec_sha, "verified": True}, _LOCK_PROOF)

    def human_author(self, sha):
        commit = self.api("commits/" + sha)
        return (commit.get("author") or {}).get("login")


def authorization(root, spec, github, head):
    path = Path(root) / spec["lifecycle"]["authorizationPath"]
    if not path.exists():
        raise ValueError("EXPLICIT_HUMAN_EXECUTION_AUTHORIZATION_ABSENT")
    doc = json.loads(path.read_text())
    wanted = {
        "studyId": spec["studyId"],
        "action": "ONE_FORMAL_EXECUTION",
        "authorizedBy": HUMAN,
        "specFileSha256": file_hash(Path(root) / SPEC),
        "dependencyManifestSha256": digest(spec["dependencyHashes"]),
    }
    if doc != wanted:
        raise ValueError("AUTHORIZATION_NOT_EXACT_FROZEN_CONTRACT")
    author_commit = (
        subprocess.check_output(
            ["git", "log", "-1", "--format=%H", "--", spec["lifecycle"]["authorizationPath"]], cwd=root
        )
        .decode()
        .strip()
    )
    if not author_commit or github.human_author(author_commit) != HUMAN:
        raise ValueError("AUTHORIZATION_NOT_COMMITTED_BY_REGISTERED_HUMAN")
    if (
        os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or os.environ.get("GITHUB_ACTOR") != HUMAN
        or os.environ.get("GITHUB_REF") != "refs/heads/main"
    ):
        raise ValueError("HUMAN_MAIN_MANUAL_DISPATCH_REQUIRED")
    return {"authorizationCommit": author_commit, "authorizedBy": HUMAN, "mergedMain": head, **wanted}


def ordered_once(*, checks, prepare, claim, run, on_failure):
    """Shared real/synthetic lifecycle. All preparation precedes claim; no retry loop."""
    checks()
    prepared = prepare()
    receipt = None
    try:
        receipt = claim()
        return run(prepared, receipt)
    except BaseException as error:
        # claim may have created the first permanent ref before verification failed.
        on_failure(error, receipt)
        raise


def formal(root=ROOT, *, snapshot_archive=None, work, github=None):
    from .preflight import prepare, verify_runtime
    from .synthetic import smoke

    root = Path(root)
    work = Path(work)
    github = github or GitHub()
    spec = json.loads((root / SPEC).read_text())  # parse only; actual main/auth precede validation
    counters = Counters()
    budget = Budget(spec)
    audit = {}
    head = None
    output = work / "results"

    def checks():
        nonlocal head
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
        if (
            github.main() != head
            or subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root).strip()
        ):
            raise ValueError("ACTUAL_CLEAN_MERGED_MAIN_REQUIRED")
        audit["authorization"] = authorization(root, spec, github, head)
        load(root)
        if (root / spec["lifecycle"]["resultPath"]).exists() or github.previous_results(
            spec["lifecycle"]["artifactPrefix"]
        ):
            raise ValueError("PREVIOUS_FORMAL_RESULT_EXISTS")
        if github.locks(spec["lifecycle"]["lockPrefix"]):
            raise ValueError("STUDY_PERMANENTLY_CONSUMED")

    def pre():
        data, identity = prepare(root, spec, snapshot_archive, work / "inputs")
        audit["inputs"] = identity
        verify_runtime(spec)
        smoke(spec)  # Same label/model/economic functions, invented names only.
        data.validate_features(spec)
        budget.check()
        output.mkdir(parents=True, exist_ok=True)
        immutable_bytes(
            work / "preflight.json",
            canonical({"studyId": spec["studyId"], "head": head, "outcomeReads": 0, "audit": audit}) + b"\n",
        )
        if github.main() != head or github.locks(spec["lifecycle"]["lockPrefix"]):
            raise ValueError("MAIN_OR_LOCK_CHANGED_DURING_PREFLIGHT")
        load(root)
        return data

    def run(data, receipt):
        # FIRST historical outcome-access boundary. Everything above is outcome-free.
        immutable_bytes(output / "lock-receipt.json", canonical(receipt.document) + b"\n")
        permit = formal_permit(data.source_identity, receipt)
        result = execute(data, spec, permit, counters=counters, budget=budget)
        load(root)
        audit.update(head=head, lock=receipt.document, counters=asdict(counters), runtime=verify_runtime(spec))
        return persist(result, output, audit)

    def failed(error, receipt):
        consumed = receipt is not None
        if not consumed:
            try:
                consumed = bool(github.locks(spec["lifecycle"]["lockPrefix"]))
            except RuntimeError:
                immutable_bytes(
                    work / "lock-status-unknown.json",
                    canonical({"status": "VERIFY_LOCK_BEFORE_ANY_RECOVERY", "reason": str(error)}) + b"\n",
                )
                return
        if not consumed:
            immutable_bytes(
                work / "pre-outcome-failure.json", canonical({"status": "NOT_CONSUMED", "reason": str(error)}) + b"\n"
            )
            return
        output.mkdir(parents=True, exist_ok=True)
        immutable_bytes(
            output / "consumed-failure.json",
            canonical(
                {
                    "status": "CONSUMED_NO_RETRY",
                    "errorClass": type(error).__name__,
                    "reason": str(error),
                    "lock": receipt.document if receipt is not None else None,
                    "counters": asdict(counters),
                    "exactByteRecoveryOnly": True,
                }
            )
            + b"\n",
        )

    return ordered_once(
        checks=checks,
        prepare=pre,
        claim=lambda: github.claim(spec["lifecycle"]["lockPrefix"], head, file_hash(root / SPEC)),
        run=run,
        on_failure=failed,
    )
