"""KR alpha discovery tournament v1 — automatic result-SEAL step (standard library only).

It verifies identities and copies verified bytes. It never imports the model, the execution harness or any data module, so it cannot recompute,
rerun, re-rank or reinterpret an outcome: the import list of this file is the proof, and a test checks it.

Lifecycle it serves: formal execute on merged main -> identity gates -> durable lock -> outcomes -> immutable result artifact -> THIS STEP verifies the
artifact archive digest, file list, manifest, marker, spec and lock identities -> copies the exact result / marker / manifest bytes -> writes a
provenance record -> one DRAFT pull request. A human reviews and merges. This module never merges, never marks a PR ready, never force-pushes, and
stops (no PR) on any mismatch.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import zipfile

STUDY = "kr-alpha-discovery-tournament-v1"
SPEC_PATH = "research_specs/" + STUDY + ".json"
SPEC_SIDECAR = "research_specs/" + STUDY + ".sha256"
LOCK_PREFIX = "refs/tags/" + STUDY + "-execution-lock"
RESULTS_ARTIFACT_PREFIX = STUDY + "-results-"
ATTEMPT_ARTIFACT_PREFIX = STUDY + "-attempt-"
ARTIFACT_FILES = ("execution-started.json", "manifest.json", "tournament-result.json")
COMMITTED = {"tournament-result.json": "docs/results/" + STUDY + "-result.json",
             "execution-started.json": "docs/results/" + STUDY + "-execution-started.json",
             "manifest.json": "docs/results/" + STUDY + "-manifest.json"}
PROVENANCE_PATH = "docs/results/" + STUDY + "-seal-provenance.json"
SEAL_BRANCH_PREFIX = "research/" + STUDY + "-result-seal-"
PR_TITLE = "Research: seal KR alpha discovery tournament v1 development result"
SCIENTIFIC_STATUS = "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def committed_spec_sha(root):
    return Path(root, SPEC_SIDECAR).read_text().strip()


def check_main(root):
    """Before anything: the frozen spec sidecar exists and nothing is sealed yet."""
    root = Path(root)
    if not (root / SPEC_PATH).exists() or not (root / SPEC_SIDECAR).exists():
        raise ValueError("FROZEN_SPEC_MISSING")
    for rel in list(COMMITTED.values()) + [PROVENANCE_PATH]:
        if (root / rel).exists():
            raise ValueError("RESULT_ALREADY_SEALED: " + rel)
    return committed_spec_sha(root)


def check_artifact_metadata(meta, run_id):
    """The artifact must be THIS run's results artifact (never an attempt artifact) and not expired."""
    name = meta.get("name", "")
    if name.startswith(ATTEMPT_ARTIFACT_PREFIX) or name != RESULTS_ARTIFACT_PREFIX + str(run_id):
        raise ValueError("NOT_THE_FORMAL_RESULTS_ARTIFACT")
    if meta.get("expired") or str((meta.get("workflow_run") or {}).get("id")) != str(run_id):
        raise ValueError("ARTIFACT_RUN_MISMATCH_OR_EXPIRED")
    digest = str(meta.get("digest") or "")
    if not digest.startswith("sha256:") or len(digest) != 7 + 64:
        raise ValueError("ARTIFACT_DIGEST_MISSING")
    return digest[len("sha256:"):]


def read_archive(archive_bytes, expected_archive_sha):
    """Verify the archive digest BEFORE opening it, then require exactly the three registered files. Returns {name: bytes} untouched."""
    if sha256(archive_bytes) != expected_archive_sha:
        raise ValueError("ARCHIVE_SHA256_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = sorted(n for n in archive.namelist() if not n.endswith("/"))
        if names != sorted(ARTIFACT_FILES):
            raise ValueError("UNEXPECTED_ARTIFACT_FILE_LIST: " + ",".join(names))
        return {name: archive.read(name) for name in names}


def verify_bundle(files, spec_sha, main_sha):
    """Every identity the result must carry: manifest -> result and marker bytes; manifest, marker and result -> this spec; marker -> the lock refs
    on the execution commit with zero values read before it; counters show exactly one marker."""
    manifest, marker, result = (json.loads(files[n]) for n in ("manifest.json", "execution-started.json", "tournament-result.json"))
    if manifest.get("studyId") != STUDY or marker.get("studyId") != STUDY or result.get("studyId") != STUDY:
        raise ValueError("STUDY_ID_MISMATCH")
    if manifest.get("specSha256") != spec_sha or marker.get("specSha256") != spec_sha or result.get("specSha256") != spec_sha:
        raise ValueError("SPEC_SHA_MISMATCH")
    if manifest.get("files") != {"tournament-result.json": sha256(files["tournament-result.json"]), "execution-started.json": sha256(files["execution-started.json"])}:
        raise ValueError("MANIFEST_FILE_HASH_MISMATCH")
    if marker.get("lockRef") != LOCK_PREFIX + "-" + spec_sha or marker.get("studyLockRef") != LOCK_PREFIX:
        raise ValueError("MARKER_LOCK_REF_MISMATCH")
    if marker.get("lockedMainSha") != main_sha or result.get("lockedMainSha") != main_sha or result.get("lockRef") != marker["lockRef"]:
        raise ValueError("LOCKED_COMMIT_MISMATCH")
    if marker.get("valuesReadBeforeThisMarker") != 0 or (manifest.get("counters") or {}).get("markerWrites") != 1:
        raise ValueError("MARKER_ORDER_NOT_PROVEN")
    if manifest.get("scientificStatus") != SCIENTIFIC_STATUS or result.get("scientificStatus") != SCIENTIFIC_STATUS:
        raise ValueError("SCIENTIFIC_STATUS_MISMATCH")
    return {"manifest": manifest, "marker": marker}


def verify_locks(api, spec_sha, main_sha):
    """Both lock refs must exist and point at the execution commit. Only GET is issued."""
    for ref in (LOCK_PREFIX, LOCK_PREFIX + "-" + spec_sha):
        status, body = api("GET", "/git/ref/" + ref[len("refs/"):], None)
        if status != 200 or ((body or {}).get("object") or {}).get("sha") != main_sha:
            raise ValueError("LOCK_REF_MISSING_OR_MOVED: " + ref)
    return True


def verify_run(run, jobs, main_sha):
    """The execution run: a workflow_dispatch on main at the locked commit whose `execute` job succeeded."""
    if run.get("event") != "workflow_dispatch" or run.get("head_branch") != "main" or run.get("head_sha") != main_sha:
        raise ValueError("EXECUTION_RUN_IDENTITY_MISMATCH")
    execute = [j for j in jobs if j.get("name") == "execute"]
    if len(execute) != 1 or execute[0].get("conclusion") != "success":
        raise ValueError("EXECUTE_JOB_DID_NOT_SUCCEED")
    return True


def write_seal(files, root, provenance):
    """Copy the exact bytes (no parse-and-dump, no pretty printing) and write the provenance record. Refuses to overwrite anything."""
    root = Path(root)
    written = {}
    for name, rel in COMMITTED.items():
        target = root / rel
        if target.exists():
            raise ValueError("RESULT_ALREADY_SEALED: " + rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(files[name])
        if sha256(target.read_bytes()) != sha256(files[name]):
            raise ValueError("COPY_NOT_BYTE_IDENTICAL: " + rel)
        written[rel] = {"sourceFile": name, "sha256": sha256(files[name]), "bytes": len(files[name])}
    record = dict(provenance, committedFiles=written, studyId=STUDY, scientificStatus=SCIENTIFIC_STATUS,
                  sealRules=["exact artifact bytes, renamed only", "no statistic recomputed", "no outcome re-executed", "draft pull request only; a human merges"])
    path = root / PROVENANCE_PATH
    if path.exists():
        raise ValueError("RESULT_ALREADY_SEALED: " + PROVENANCE_PATH)
    path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    return record


def verify_written(root):
    """Before a pull request is opened: the committed files still equal the provenance record byte for byte."""
    root = Path(root)
    record = json.loads((root / PROVENANCE_PATH).read_text())
    for rel, entry in record["committedFiles"].items():
        if sha256((root / rel).read_bytes()) != entry["sha256"]:
            raise ValueError("SEALED_FILE_CHANGED_BEFORE_PR: " + rel)
    return record


def pr_body(record):
    return "\n".join([
        "**RESULT SEAL ONLY — NO OUTCOME RECOMPUTED, NO RERUN, NO TUNING**", "",
        "Exact bytes of the formal `" + STUDY + "` result, verified and committed by the same workflow that executed it.", "",
        "- execution run: " + str(record["executionRunId"]) + " · execution SHA: " + record["executionSha"],
        "- artifact: " + record["artifactName"] + " (id " + str(record["artifactId"]) + ")",
        "- archive SHA-256: " + record["artifactArchiveSha256"],
        "- spec SHA-256: " + record["specSha256"],
        "- lock refs: " + LOCK_PREFIX + " and " + LOCK_PREFIX + "-" + record["specSha256"],
        "- scientific status: " + SCIENTIFIC_STATUS, "",
        "DEVELOPMENT evidence on outcome-exposed KR history about a model-selection PROCESS; not validation. Whatever the verdict, the frozen "
        "process is confirmed only by prospective receipts; nothing here is a production model. Draft; a human reviews and merges. Opened by GITHUB_TOKEN, so pull-request "
        "workflows do not start on their own."])


HANDOFF_CLASSIFICATION = "RECOVERABLE_SEAL_HANDOFF_FAILURE"
HANDOFF_EXIT_CODE = 3
RETRYABLE_STATUSES = (0, 500, 502, 503, 504)


class RecoverableSealHandoff(ValueError):
    """The exact-byte seal was verified, written, committed and pushed, but the Draft pull request could not be created (typically a repository
    setting that withholds PR creation from GITHUB_TOKEN). It is a HANDOFF failure, never an execution or scientific one: the result is intact on an
    immutable branch and a human opens the Draft PR by hand. The formal execution is never rerun because of it."""

    def __init__(self, status, head, base, record):
        super().__init__("RECOVERABLE_SEAL_HANDOFF: DRAFT_PULL_REQUEST_NOT_CREATED status=" + str(status) + " head=" + head)
        self.status, self.head, self.base, self.record = status, head, base, record


def manual_handoff(head, base, record):
    """Everything a human needs to open the Draft PR by hand. Pure data: it grants nothing, uses no credential and re-verifies nothing."""
    return {"classification": HANDOFF_CLASSIFICATION, "executionStatus": "SUCCEEDED_AND_SEALED_ON_THE_BRANCH", "executionRerunAllowed": False,
            "scientificStatus": SCIENTIFIC_STATUS, "branch": head, "base": base, "title": PR_TITLE, "draft": True, "body": pr_body(record),
            "committedFiles": sorted((record.get("committedFiles") or {})),
            "manualSteps": ["do NOT rerun the formal workflow and do NOT dispatch mode=execute again (the study is consumed or sealed; a rerun is refused by the lock)",
                            "the seal branch " + head + " is already pushed and must not be force-pushed, amended or deleted",
                            "open ONE pull request from " + head + " into " + base + " as a DRAFT with the title and body above (GitHub UI: Compare & pull request -> Create draft pull request)",
                            "review that the four committed files equal the verified artifact bytes recorded in the provenance record, then a human merges",
                            "if GITHUB_TOKEN may not create pull requests, the repository setting 'Allow GitHub Actions to create and approve pull requests' is the cause; "
                            "changing it is a human decision and no credential or permission is changed by this workflow"]}


def existing_pr(api, owner, head):
    """The number of an already-open pull request from this exact head, or None. Makes a retry idempotent."""
    status, body = api("GET", "/pulls?state=all&head=" + owner + ":" + head, None)
    if status == 200 and isinstance(body, list) and body:
        return body[0].get("number")
    return None


def open_draft_pr(api, head, base, record, owner=None, attempts=3, sleep=None):
    """POST one DRAFT pull request. The only write this module issues to the pulls API; no merge, no ready-for-review, no update.

    Transient failures (network, 5xx) are retried a bounded number of times with the injected `sleep`; any other refusal (for example 403 because
    GITHUB_TOKEN may not create pull requests) is raised at once as a RecoverableSealHandoff. A pull request that already exists for this head is
    returned, so repeating the step never creates a second one. A response that is not a draft is NOT recoverable: it is a violation."""
    if not head.startswith(SEAL_BRANCH_PREFIX) or base != "main":
        raise ValueError("SEAL_BRANCH_OR_BASE_NOT_REGISTERED")
    if owner:
        found = existing_pr(api, owner, head)
        if found:
            return found
    payload = {"title": PR_TITLE, "head": head, "base": base, "body": pr_body(record), "draft": True, "maintainer_can_modify": False}
    status, body = 0, {}
    for attempt in range(attempts):
        status, body = api("POST", "/pulls", payload)
        if status == 201:
            break
        if status not in RETRYABLE_STATUSES or attempt == attempts - 1:
            raise RecoverableSealHandoff(status, head, base, record)
        if sleep:
            sleep(2 ** (attempt + 1))
    if not (body or {}).get("draft"):
        raise ValueError("DRAFT_PULL_REQUEST_NOT_CREATED")
    return body.get("number")
