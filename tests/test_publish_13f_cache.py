import base64
import json

from scripts.publish_13f_cache import CACHE, publish
from scripts.publish_state import APIError


def row(report, filing):
    return {"id": "x", "cik": "0000000001", "reportDate": report,
            "filingDate": filing, "filingUrl": "https://www.sec.gov/Archives/test.xml",
            "positionCount": 1, "totalValueUsd": 10,
            "topHoldings": [{"issuer": "X"}]}


def test_publication_preserves_newer_remote_and_retries_ref_race():
    old = row("2026-06-30", "2026-08-14")
    new = row("2026-09-30", "2026-11-13")
    registry = [{"id": "x", "cik": "0000000001"}]
    incoming = {"fetchedAt": "2026-11-14T00:00:00Z", "managers": {"x": new}}

    class API:
        head = "h1"
        attempts = 0
        remote = old

        def request(self, method, path, payload=None):
            if path.startswith("/git/ref/heads/"):
                return {"object": {"sha": self.head}}
            if path.startswith("/git/commits/"):
                return {"tree": {"sha": "t"}}
            if path.startswith("/contents/"):
                previous = {"fetchedAt": "2026-08-15T00:00:00Z",
                            "managers": {"x": self.remote}}
                return {"type": "file", "encoding": "base64",
                        "content": base64.b64encode(json.dumps(previous).encode()).decode()}
            if path == "/git/trees":
                assert [x["path"] for x in payload["tree"]] == [CACHE]
                assert json.loads(payload["tree"][0]["content"])["managers"]["x"] == new
                return {"sha": "newtree"}
            if path == "/git/commits":
                assert payload["parents"] == [self.head]
                return {"sha": "newcommit"}
            if method == "PATCH":
                assert payload["force"] is False
                self.attempts += 1
                if self.attempts == 1:
                    self.head = "h2"
                    self.remote = new
                    raise APIError(422)
            raise AssertionError((method, path))

    api = API()
    assert publish(api, incoming, registry, pause=lambda _: None) == "unchanged"
    assert api.attempts == 1


def test_hook_is_restricted_to_existing_post_deploy_command(tmp_path, monkeypatch):
    from scripts import publish_13f_cache as P

    calls = []
    monkeypatch.setattr(P, "publish_disclosures",
                        lambda *args: calls.append(args) or "published")
    root = tmp_path.resolve()
    artifact = root / "data/site-data.json"
    destination = root / ".state/latest.next.json"
    env = {"GITHUB_ACTIONS": "true",
           "GITHUB_WORKFLOW": "Build insight data and deploy Pages",
           "GITHUB_JOB": "build-and-deploy",
           "GITHUB_REF": "refs/heads/main",
           "GITHUB_EVENT_NAME": "schedule"}
    for key in env:
        assert P.preserve_after_pages({}, artifact, destination, root,
                                      {**env, key: "wrong"}) == "not-pages-production"
    assert P.preserve_after_pages({}, artifact, root / "other.json", root, env) == "not-pages-production"
    assert P.preserve_after_pages({}, artifact, destination, root, env) == "published"
    assert len(calls) == 1


def test_hook_failure_does_not_block_original_state_publication(tmp_path, monkeypatch, capsys):
    from scripts import publish_13f_cache as P

    def fail(*args):
        raise APIError(403)

    monkeypatch.setattr(P, "publish_disclosures", fail)
    root = tmp_path.resolve()
    env = {"GITHUB_ACTIONS": "true",
           "GITHUB_WORKFLOW": "Build insight data and deploy Pages",
           "GITHUB_JOB": "build-and-deploy", "GITHUB_REF": "refs/heads/main",
           "GITHUB_EVENT_NAME": "push"}
    result = P.preserve_after_pages({}, root / "data/site-data.json",
                                    root / ".state/latest.next.json", root, env)
    assert result == "publication-failed"
    assert "SEC 13F cache publication failed" in capsys.readouterr().err
