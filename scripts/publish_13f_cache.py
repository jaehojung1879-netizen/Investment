"""Persist the dashboard's verified 13F snapshots separately from model state.

Only a successfully deployed Pages build with at least one live manager may
publish. The Git ref update is non-forced; a race with the ledger or another
publisher rereads the current branch and merges per manager before retrying.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import sys
import time

from pipeline.institutional_13f import merge_snapshots
from scripts.publish_state import APIError, GitHub

BRANCH = "signal-history"
CACHE = "state/institutional_13f_cache.json"


def publish(api, incoming, registry, attempts=5, pause=time.sleep):
    for attempt in range(attempts):
        head = api.request("GET", f"/git/ref/heads/{BRANCH}")["object"]["sha"]
        commit = api.request("GET", f"/git/commits/{head}")
        try:
            content = api.request("GET", f"/contents/{CACHE}?ref={head}")
        except APIError as exc:
            if exc.status != 404:
                raise
            root = api.request("GET", f"/git/trees/{commit['tree']['sha']}")
            state = next((x for x in root["tree"] if x["path"] == "state"), None)
            if state:
                if state["type"] != "tree":
                    raise ValueError("state is not a directory")
                subtree = api.request("GET", f"/git/trees/{state['sha']}")
                if any(x["path"] == "institutional_13f_cache.json" for x in subtree["tree"]):
                    raise ValueError("existing 13F cache cannot be read")
            previous = {}
        else:
            if content.get("type") != "file" or content.get("encoding") != "base64":
                raise ValueError("13F cache is not an ordinary JSON file")
            previous = json.loads(base64.b64decode(content["content"]))
        old = previous.get("managers") or {}
        merged = merge_snapshots(old, incoming.get("managers") or {}, registry)
        if not merged:
            raise ValueError("no valid official 13F snapshots")
        if merged == old:
            return "unchanged"
        payload = {
            "source": "SEC EDGAR Form 13F-HR",
            "fetchedAt": max(previous.get("fetchedAt") or "", incoming["fetchedAt"]),
            "managers": merged,
        }
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        tree = api.request("POST", "/git/trees", {
            "base_tree": commit["tree"]["sha"],
            "tree": [{"path": CACHE, "mode": "100644", "type": "blob", "content": encoded}],
        })
        new = api.request("POST", "/git/commits", {
            "message": "data: preserve last verified SEC 13F disclosures",
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
    site = json.loads(Path("data/site-data.json").read_text(encoding="utf-8"))
    disclosure = site.get("institutionalHoldings13F") or {}
    live = [m for m in disclosure.get("managers", []) if m.get("status") == "AVAILABLE"
            and m.get("sourceMode") == "LIVE_SEC"]
    if not live:
        print("::warning::SEC 13F: no live disclosures; existing official cache preserved.")
        return 0
    if disclosure.get("overdueOrMissingCount", 0):
        print("::warning::SEC 13F: some managers have no confirmed due-quarter disclosure.")
    cache = json.loads(Path("data/institutional_13f_cache.json").read_text(encoding="utf-8"))
    registry = json.loads(Path("data/institutional_managers.json").read_text(encoding="utf-8"))
    api = GitHub(os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GH_TOKEN", ""))
    print(f"SEC 13F cache {publish(api, cache, registry)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
