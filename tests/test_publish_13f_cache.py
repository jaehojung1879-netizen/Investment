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
