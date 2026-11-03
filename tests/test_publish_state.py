"""Offline Git Data API contract tests backed by small, real Git trees."""
import base64
import json
from pathlib import Path
import subprocess

import pytest

from scripts.publish_state import APIError, GitHub, STATE, main, publish


def snapshot(day=2, market="2026-10-30"):
    return dict(dataMode="live", seed=False, stale=False,
                productionValidation={"passed": True}, marketAsOf=market,
                generatedAt=f"2026-11-{day:02d}T00:00:00+00:00", holdingsByRegion={})


class GitAPI:
    """Translate the exact endpoint contract into git plumbing, no ledger reads."""
    def __init__(self, root):
        self.root = root
        self.calls = []
        self.race = None
        self.reject = False
        self.git("init", "--bare", str(root))
        self.git("config", "user.name", "fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        ledger_blob = self.blob("synthetic ledger\n" * 1024)
        ledger = self.git("mktree", stdin=f"100644 blob {ledger_blob}\treceipts.jsonl\n")
        protected = self.blob("protected state")
        latest = self.blob(json.dumps(snapshot(1)))
        state = self.git("mktree", stdin=f"100644 blob {latest}\tlatest.json\n100644 blob {protected}\tsealed.json\n")
        tree = self.git("mktree", stdin=f"040000 tree {ledger}\tledger\n040000 tree {state}\tstate\n")
        head = self.git("commit-tree", tree, stdin="fixture")
        self.git("update-ref", "refs/heads/signal-history", head)

    def git(self, *args, stdin=None):
        return subprocess.check_output(["git", *args], cwd=self.root.parent if not self.root.exists() else self.root,
                                       input=None if stdin is None else stdin.encode(), stderr=subprocess.PIPE).decode().strip()

    def blob(self, content):
        return self.git("hash-object", "-w", "--stdin", stdin=content)

    @property
    def head(self):
        return self.git("rev-parse", "refs/heads/signal-history")

    def tree(self, ref):
        entries = []
        for line in self.git("ls-tree", ref).splitlines():
            mode, kind, sha, path = line.split()
            entries.append(dict(mode=mode, type=kind, sha=sha, path=path))
        return {"tree": entries}

    def request(self, method, path, payload=None):
        self.calls.append((method, path))
        if path == "/git/ref/heads/signal-history":
            return {"object": {"sha": self.head}}
        if path.startswith("/git/commits/"):
            return {"tree": {"sha": self.git("rev-parse", path.rsplit("/", 1)[1] + "^{tree}")}}
        if path.startswith("/contents/"):
            assert path.startswith(f"/contents/{STATE}?ref=")
            head = path.split("ref=")[1]
            try:
                content = self.git("show", f"{head}:{STATE}")
            except subprocess.CalledProcessError:
                raise APIError(404) from None
            return {"type": "file", "encoding": "base64", "content": base64.b64encode(content.encode()).decode()}
        if method == "GET" and path.startswith("/git/trees/"):
            return self.tree(path.rsplit("/", 1)[1])
        if path == "/git/trees":
            assert payload["tree"][0]["path"] == STATE
            assert len(payload["tree"]) == 1
            # Rebuild only the state subtree, preserving all other entries.
            root = self.tree(payload["base_tree"])["tree"]
            state = next((x for x in root if x["path"] == "state"), None)
            children = [] if state is None else self.tree(state["sha"])["tree"]
            children = [x for x in children if x["path"] != "latest.json"]
            children.append(dict(mode="100644", type="blob", path="latest.json", sha=self.blob(payload["tree"][0]["content"])))
            def mktree(entries):
                return self.git("mktree", stdin="".join(f"{x['mode']} {x['type']} {x['sha']}\t{x['path']}\n" for x in entries))
            root = [x for x in root if x["path"] != "state"]
            root.append(dict(mode="040000", type="tree", path="state", sha=mktree(children)))
            return {"sha": mktree(root)}
        if path == "/git/commits":
            assert len(payload["parents"]) == 1
            return {"sha": self.git("commit-tree", payload["tree"], "-p", payload["parents"][0], stdin=payload["message"])}
        if method == "PATCH":
            assert payload["force"] is False
            if self.race:
                race, self.race = self.race, None
                race()
            if self.reject or subprocess.run(["git", "merge-base", "--is-ancestor", self.head, payload["sha"]], cwd=self.root).returncode:
                raise APIError(422)
            self.git("update-ref", "refs/heads/signal-history", payload["sha"], self.head)
            return {}
        raise AssertionError((method, path))


@pytest.fixture
def api(tmp_path):
    return GitAPI(tmp_path / "repo.git")


def test_success_and_duplicate_preserve_every_other_path(api):
    before = api.head
    assert publish(api, snapshot()) == "published"
    after = api.head
    assert api.git("diff-tree", "--no-commit-id", "--name-only", "-r", before, after) == STATE
    assert api.git("rev-parse", before + ":ledger") == api.git("rev-parse", after + ":ledger")
    assert api.git("rev-parse", before + ":state/sealed.json") == api.git("rev-parse", after + ":state/sealed.json")
    assert publish(api, snapshot()) == "unchanged"
    assert api.head == after
    assert not list(api.root.parent.glob("*work*"))


def test_concurrent_ledger_commit_survives(api):
    old = api.head
    def ledger_writer():
        ledger = api.git("mktree", stdin=f"100644 blob {api.blob('appended ledger')}\treceipts.jsonl\n")
        state = api.git("rev-parse", old + ":state")
        tree = api.git("mktree", stdin=f"040000 tree {ledger}\tledger\n040000 tree {state}\tstate\n")
        new = api.git("commit-tree", tree, "-p", old, stdin="concurrent ledger")
        api.git("update-ref", "refs/heads/signal-history", new, old)
    api.race = ledger_writer
    assert publish(api, snapshot(), pause=lambda _: None) == "published"
    assert api.git("show", api.head + ":ledger/receipts.jsonl") == "appended ledger"
    assert sum(m == "PATCH" for m, _ in api.calls) == 2


def test_concurrent_newer_state_prevents_rollback(api):
    api.race = lambda: publish(api, snapshot(3))
    with pytest.raises(ValueError, match="regression"):
        publish(api, snapshot(2), pause=lambda _: None)
    assert json.loads(api.git("show", api.head + ":" + STATE)) == snapshot(3)


def test_bounded_conflict_and_failure_isolation(api):
    before = api.head
    api.reject = True
    with pytest.raises(APIError):
        publish(api, snapshot(), pause=lambda _: None)
    assert sum(m == "PATCH" for m, _ in api.calls) == 5
    assert api.head == before


@pytest.mark.parametrize("status", [401, 403, 500])
def test_api_failure_does_not_retry_or_move_head(api, status):
    before = api.head
    original = api.request
    def fail(method, path, payload=None):
        if method == "PATCH":
            raise APIError(status)
        return original(method, path, payload)
    api.request = fail
    with pytest.raises(APIError):
        publish(api, snapshot())
    assert api.head == before


@pytest.mark.parametrize("change", [dict(marketAsOf="2026-10-29"), dict(generatedAt="2026-10-31T00:00:00Z"), dict(seed=True), dict(generatedAt="bad")])
def test_stale_and_invalid_inputs_fail_without_writes(api, change):
    candidate = snapshot()
    candidate.update(change)
    with pytest.raises(ValueError):
        publish(api, candidate)
    assert not any(method in ("POST", "PATCH") for method, _ in api.calls)


def test_equal_generation_different_content_fails_closed(api):
    candidate = snapshot(1)
    candidate["holdingsByRegion"] = {"SYN": []}
    with pytest.raises(ValueError, match="same generation"):
        publish(api, candidate)


def test_missing_token(monkeypatch, capsys):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert main() == 1
    assert "failed closed" in capsys.readouterr().err
    with pytest.raises(ValueError, match="GH_TOKEN"):
        GitHub("owner/repo", "")


def test_missing_latest_is_narrowly_created(api):
    state = api.git("mktree", stdin=f"100644 blob {api.blob('protected')}\tsealed.json\n")
    ledger = api.git("rev-parse", api.head + ":ledger")
    tree = api.git("mktree", stdin=f"040000 tree {ledger}\tledger\n040000 tree {state}\tstate\n")
    old = api.head
    head = api.git("commit-tree", tree, "-p", old, stdin="missing latest")
    api.git("update-ref", "refs/heads/signal-history", head, old)
    assert publish(api, snapshot()) == "published"
    assert api.git("diff-tree", "--no-commit-id", "--name-only", "-r", head, api.head) == STATE


@pytest.mark.parametrize("content", ["null", "[]", "0", '"not a snapshot"', "{broken"])
def test_existing_invalid_state_is_never_treated_as_missing(api, content):
    old = api.head
    tree = api.request("POST", "/git/trees", {
        "base_tree": api.git("rev-parse", old + "^{tree}"),
        "tree": [{"path": STATE, "mode": "100644", "type": "blob", "content": content}],
    })
    commit = api.request("POST", "/git/commits", {
        "tree": tree["sha"], "parents": [old], "message": "invalid stored fixture",
    })
    api.git("update-ref", "refs/heads/signal-history", commit["sha"], old)
    before = api.head
    api.calls.clear()
    with pytest.raises(ValueError):
        publish(api, snapshot())
    assert api.head == before
    assert not any(method in ("POST", "PATCH") for method, _ in api.calls)


def test_workflow_deploys_then_validates_and_publishes():
    text = (Path(__file__).resolve().parents[1] / ".github/workflows/pages.yml").read_text()
    tail = text[text.index('      - name: Publish last successful state'):]
    assert "worktree" not in tail and "git fetch" not in tail
    assert text.index("uses: actions/deploy-pages@v4") < text.index("python scripts/update_state.py") < text.index("python scripts/publish_state.py")


def test_exhausted_materialization_device_and_state_only_publication(api):
    # /dev/full is a kernel-provided bounded ENOSPC fixture, no real disk fill.
    # Reproduce the failing operation (writing a ledger blob during checkout),
    # then prove publication needs no filesystem for those ledger bytes.
    import errno
    ledger = api.git("show", api.head + ":ledger/receipts.jsonl").encode()
    with open("/dev/full", "wb", buffering=0) as exhausted:
        with pytest.raises(OSError) as error:
            exhausted.write(ledger)
    assert error.value.errno == errno.ENOSPC
    before = api.git("rev-parse", api.head + ":ledger")
    assert publish(api, snapshot()) == "published"
    assert api.git("rev-parse", api.head + ":ledger") == before
    print(f"synthetic ledger materialization avoided={len(ledger)} bytes; state={len(json.dumps(snapshot()).encode())} bytes")


def test_synthetic_checkout_disk_comparison(api, tmp_path):
    old_checkout = tmp_path / "old-worktree"
    api.git("worktree", "add", "--detach", str(old_checkout), api.head)
    before = int(subprocess.check_output(["du", "-sb", str(old_checkout)]).split()[0])
    ledger_bytes = (old_checkout / "ledger/receipts.jsonl").stat().st_size
    assert publish(api, snapshot()) == "published"
    state_bytes = len((json.dumps(snapshot(), ensure_ascii=False, indent=2) + "\n").encode())
    assert ledger_bytes > state_bytes
    print(f"synthetic old_checkout={before} bytes; ledger={ledger_bytes} bytes; new_state_payload={state_bytes} bytes; new_ledger_checkout=0 bytes")
