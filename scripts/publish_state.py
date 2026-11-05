"""Publish only state/latest.json; never fetch or materialize the ledger.

The caller must run update_state.py after successful production deployment.
Git's non-fast-forward check is the transaction boundary: every proposed commit
has exactly the HEAD we inspected as its sole parent. A racing ledger commit
therefore causes a rejection, followed by a fresh read (at most five attempts).
"""
from __future__ import annotations

import base64
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

BRANCH = "signal-history"
STATE = "state/latest.json"


class APIError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"GitHub API request failed (HTTP {status})")


class GitHub:
    def __init__(self, repository, token):
        if not token:
            raise ValueError("GH_TOKEN is required")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("invalid repository")
        self.base = f"https://api.github.com/repos/{repository}"
        self.token = token

    def request(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.base + path, data=body, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Never log response bodies, state contents or request headers.
            raise APIError(exc.code) from None


def freshness(state):
    if not isinstance(state, dict) or state.get("dataMode") != "live" or state.get("seed") is not False or state.get("stale") is not False:
        raise ValueError("state must be a live validated snapshot")
    if (state.get("productionValidation") or {}).get("passed") is not True:
        raise ValueError("production validation missing")
    market = date.fromisoformat(state["marketAsOf"])
    generated = datetime.fromisoformat(state["generatedAt"].replace("Z", "+00:00"))
    if generated.tzinfo is None:
        raise ValueError("generatedAt must include timezone")
    return market, generated


def publish(api, candidate, attempts=5, pause=time.sleep):
    encoded = json.dumps(candidate, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    incoming = freshness(candidate)
    missing = object()
    for attempt in range(attempts):
        head = api.request("GET", f"/git/ref/heads/{BRANCH}")["object"]["sha"]
        commit = api.request("GET", f"/git/commits/{head}")
        try:
            content = api.request("GET", f"/contents/{STATE}?ref={head}")
        except APIError as exc:
            if exc.status != 404:
                raise
            # Prove absence via the tree: a contents 404 alone could be a
            # permission failure. Never bootstrap a missing branch implicitly.
            root = api.request("GET", f"/git/trees/{commit['tree']['sha']}")
            state_dir = next((x for x in root["tree"] if x["path"] == "state"), None)
            if state_dir:
                if state_dir["type"] != "tree":
                    raise ValueError("state is not a directory") from None
                subtree = api.request("GET", f"/git/trees/{state_dir['sha']}")
                if any(x["path"] == "latest.json" for x in subtree["tree"]):
                    raise ValueError("existing state cannot be read") from None
            current = missing
        else:
            if content.get("type") != "file" or content.get("encoding") != "base64":
                raise ValueError("state content is not an ordinary JSON file")
            current = json.loads(base64.b64decode(content["content"], validate=False))
            # Python accepts NaN/Infinity and overflowing exponents on decode.
            # Refuse every nested nonfinite value before creating Git objects.
            json.dumps(current, allow_nan=False)
        if current is not missing:
            previous = freshness(current)
            if candidate == current:
                return "unchanged"
            if any(new < old for new, old in zip(incoming, previous)):
                raise ValueError("refusing state freshness regression")
            if incoming[1] == previous[1]:
                raise ValueError("different state at the same generation time")
        tree = api.request("POST", "/git/trees", {
            "base_tree": commit["tree"]["sha"],
            "tree": [{"path": STATE, "mode": "100644", "type": "blob",
                      "content": encoded}],
        })
        new = api.request("POST", "/git/commits", {
            "message": "state: publish last successful production snapshot",
            "tree": tree["sha"], "parents": [head],
        })
        try:
            api.request("PATCH", f"/git/refs/heads/{BRANCH}", {"sha": new["sha"], "force": False})
            return "published"
        except APIError as exc:
            if exc.status not in (409, 422) or attempt + 1 == attempts:
                raise
            pause(attempt + 1)
    raise ValueError("no publication attempts configured")


def main():
    try:
        api = GitHub(os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GH_TOKEN", ""))
        result = publish(api, json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    except (APIError, ValueError, KeyError, TypeError, OSError, IndexError, urllib.error.URLError):
        print("state publication failed closed; deployment already completed", file=sys.stderr)
        return 1
    print(f"production state {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
