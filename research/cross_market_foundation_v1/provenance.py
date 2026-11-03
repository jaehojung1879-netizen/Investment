"""Verify exact source bytes without confusing availability with eligibility."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_SOURCE_BYTES = 32 * 1024 * 1024


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or ".." in path.parts
            or ":" in value or "\\" in value or path.as_posix() != value):
        raise ValueError("INVALID_SOURCE_PATH")
    return value


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_pinned_blob(repo: Path, commit: str, path: str) -> tuple[str, bytes]:
    """Read a bounded Git blob. No checkout, fetch, or study execution.

    Missing partial-clone objects are reported as unavailable. Fetching an exact
    commit/source is a separate explicit acquisition step, never a hidden side
    effect of a readiness check.
    """
    if not isinstance(commit, str) or not HEX40.fullmatch(commit):
        raise ValueError("EXACT_COMMIT_REQUIRED")
    path = _relative_path(path)
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")

    def git(*args: str) -> bytes:
        run = subprocess.run(["git", "--no-replace-objects", "-C", str(repo), *args],
                             capture_output=True, env=env, check=False, timeout=30)
        if run.returncode:
            raise ValueError("SOURCE_OBJECT_UNAVAILABLE")
        return run.stdout

    commit_type = git("cat-file", "-t", commit).strip()
    if commit_type != b"commit":
        raise ValueError("SOURCE_NOT_COMMIT")
    blob = git("rev-parse", "--verify", f"{commit}:{path}").decode().strip()
    if not HEX40.fullmatch(blob) or git("cat-file", "-t", blob).strip() != b"blob":
        raise ValueError("SOURCE_NOT_BLOB")
    size = int(git("cat-file", "-s", blob))
    if size > MAX_SOURCE_BYTES:
        raise ValueError("SOURCE_TOO_LARGE")
    raw = git("cat-file", "blob", blob)
    if len(raw) != size:
        raise ValueError("SOURCE_SIZE_MISMATCH")
    return blob, raw


def source_pin(repo: Path, commit: str, path: str, *, role: str) -> dict[str, Any]:
    blob, raw = read_pinned_blob(repo, commit, path)
    return {"commit": commit, "path": path, "blob": blob, "sha256": sha256_bytes(raw),
            "bytes": len(raw), "role": role,
            "url": f"https://github.com/jaehojung1879-netizen/Investment/blob/{commit}/{path}"}


def verify_source_pin(repo: Path, pin: dict[str, Any]) -> dict[str, Any]:
    """An exact byte receipt is not a rights/PIT/total-return admission."""
    if not isinstance(pin.get("sha256"), str) or not HEX64.fullmatch(pin["sha256"]):
        raise ValueError("EXPECTED_SHA256_REQUIRED")
    try:
        blob, raw = read_pinned_blob(repo, pin["commit"], pin["path"])
    except ValueError as exc:
        return {"path": pin.get("path"), "status": str(exc), "eligibleForResearch": None}
    matched = (blob == pin.get("blob") and len(raw) == pin.get("bytes")
               and sha256_bytes(raw) == pin["sha256"])
    return {"path": pin["path"], "status": "VERIFIED_BYTES" if matched else "SOURCE_DIGEST_MISMATCH",
            "eligibleForResearch": None}


def verify_file_receipts(root: Path, receipts: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Verify retained small evidence and prevent traversal/symlink escapes."""
    base = root.resolve()
    seen: set[str] = set()
    results = []
    for receipt in receipts:
        relative = _relative_path(receipt["path"])
        if relative in seen:
            raise ValueError("DUPLICATE_EVIDENCE_PATH")
        seen.add(relative)
        target = (base / relative).resolve()
        if not target.is_relative_to(base):
            raise ValueError("EVIDENCE_PATH_ESCAPE")
        if not target.is_file():
            state = "EVIDENCE_UNAVAILABLE"
        elif target.stat().st_size > MAX_SOURCE_BYTES:
            state = "EVIDENCE_TOO_LARGE"
        else:
            raw = target.read_bytes()
            state = ("VERIFIED_BYTES" if sha256_bytes(raw) == receipt.get("sha256")
                     and len(raw) == receipt.get("bytes") else "EVIDENCE_DIGEST_MISMATCH")
        results.append({"path": relative, "status": state})
    return results


def verify_receipt_inventory(root: Path, receipts: list[dict[str, Any]]) -> list[str]:
    """A receipt list must cover the packet, not merely a selected subset.

    The manifest itself is anchored by the reviewed Git commit rather than a
    recursive self hash. Interpreter caches are not source artifacts.
    """
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*")
              if path.is_file() and "__pycache__" not in path.parts
              and path.relative_to(root).as_posix() != "evidence/evidence-receipts.json"}
    declared = {_relative_path(row["path"]) for row in receipts}
    return (["UNRECEIPTED_PACKET_FILE:" + path for path in sorted(actual - declared)]
            + ["MISSING_PACKET_FILE:" + path for path in sorted(declared - actual)])
