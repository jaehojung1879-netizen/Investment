"""Offline object view and metadata-only recovery for WID admission.

No remote, worktree, refs, replacement refs or hooks are inherited by the view.
Commit/tree bodies and the one hash-checked input manifest are metadata; source
price, action and filing blob bodies are never copied by recovery.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
import subprocess
import tempfile


def git(root, *args, **kwargs):
    return subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(root), *args],
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
        stderr=subprocess.DEVNULL,
        **kwargs,
    )


@contextmanager
def local_view(root):
    """Use the existing object store, with NO promisor remote capable of fetching.

    Alternates expose object bytes, not donor repository configuration or refs.
    Keep the environment guard too, but do not depend on its Git-version support.
    """
    root = Path(root).resolve()
    objects = Path(git(root, "rev-parse", "--path-format=absolute", "--git-path", "objects", text=True).strip())
    if "\n" in str(objects) or "\r" in str(objects):
        raise ValueError("UNSAFE_OBJECT_DIRECTORY")
    with tempfile.TemporaryDirectory(prefix="wid-local-object-view-") as tmp:
        view = Path(tmp)
        git(view, "init", "--bare", "-q")
        (view / "objects/info/alternates").write_text(str(objects) + "\n")
        yield view


def object_type(root, oid):
    if not re.fullmatch(r"[0-9a-f]{40}", oid):
        raise ValueError("EXACT_GIT_SHA1_REQUIRED")
    try:
        return git(root, "cat-file", "-t", oid, text=True).strip()
    except subprocess.CalledProcessError:
        return None


def restore_metadata(target, donor, commits, manifest_commit, manifest_path, validate_manifest):
    """Explicit LOCAL recovery. No fetch, remote refs, market payload or approval.

    Only caller-fixed commit/tree objects and one validated manifest blob enter
    the pack. A metadata-only target still fails admission for missing payloads.
    """
    if Path(target).resolve() == Path(donor).resolve():
        raise ValueError("DISTINCT_LOCAL_DONOR_REQUIRED")
    with local_view(donor) as view:
        selected, pending = set(), []
        for commit in sorted(set(commits)):
            if object_type(view, commit) != "commit":
                raise ValueError("DONOR_COMMIT_MISSING:" + commit)
            raw = git(view, "cat-file", "commit", commit)
            tree = raw.split(b"\n", 1)[0].decode().removeprefix("tree ")
            if not re.fullmatch(r"[0-9a-f]{40}", tree):
                raise ValueError("INVALID_COMMIT_TREE")
            selected.add(commit)
            pending.append(tree)
        trees = set()
        while pending:
            tree = pending.pop()
            if tree in trees:
                continue
            if object_type(view, tree) != "tree":
                raise ValueError("DONOR_TREE_MISSING:" + tree)
            trees.add(tree)
            raw = git(view, "cat-file", "tree", tree)
            offset = 0
            while offset < len(raw):
                end = raw.index(b"\0", offset)
                mode = raw[offset:end].split(b" ", 1)[0]
                oid = raw[end + 1 : end + 21].hex()
                if len(oid) != 40:
                    raise ValueError("MALFORMED_TREE")
                if mode == b"40000":
                    pending.append(oid)
                offset = end + 21
            if len(trees) > 100_000:
                raise ValueError("METADATA_TREE_LIMIT")
        selected.update(trees)
        manifest = git(view, "cat-file", "blob", manifest_commit + ":" + manifest_path)
        validate_manifest(manifest)  # Verify exact registered hash BEFORE writing.
        manifest_oid = git(view, "rev-parse", manifest_commit + ":" + manifest_path, text=True).strip()
        selected.add(manifest_oid)
        if object_type(view, manifest_oid) != "blob":
            raise ValueError("MANIFEST_NOT_BLOB")
        # No revision walk, no parent expansion and no reuse of external delta bases.
        pack = git(
            view,
            "pack-objects",
            "--stdout",
            "--window=0",
            "--no-reuse-delta",
            "--no-reuse-object",
            input=("\n".join(sorted(selected)) + "\n").encode(),
        )
        if len(pack) > 32 * 1024 * 1024:
            raise ValueError("METADATA_PACK_TOO_LARGE")
    git(target, "index-pack", "--stdin", input=pack)
    return {
        "commits": len(set(commits)),
        "trees": len(trees),
        "manifestBlobs": 1,
        "marketPayloadBlobsCopied": 0,
        "packBytes": len(pack),
        "networkRequests": 0,
        "authorizationGranted": False,
        "outcomeReads": 0,
        "modelFits": 0,
    }
