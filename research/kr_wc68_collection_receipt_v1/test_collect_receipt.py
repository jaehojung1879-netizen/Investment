"""Offline regression tests for the fixed 68 original-DART acquisition receipt verifier.

No DART network, secrets, real financial values, prices or history outcomes.
"""
import hashlib
import json
from pathlib import Path

import pytest

from research.kr_wc68_collection_receipt_v1 import collect_receipt as C


PINNED = Path(__file__).with_name("receipt.json")


def test_committed_fixed68_receipt_matches_independent_immutable_digest():
    raw = PINNED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == C.RECEIPT_SHA256
    doc = C.load_pinned_receipt(PINNED)
    assert doc["planSha256"] == C.PLAN_SHA256
    assert doc["rawBytesCommitted"] is False
    assert doc["sourceAdmissionAuthorized"] is False
    assert doc["originalFinancialValuesVerified"] is False
    assert len(doc["rows"]) == len({r["receipt"] for r in doc["rows"]}) == 68


@pytest.mark.parametrize("mutation", ["empty", "one_extra", "duplicate", "claimed_hash", "wrong_route"])
def test_reacquisition_refuses_substituted_receipt_before_network(tmp_path, monkeypatch, mutation):
    doc = json.loads(PINNED.read_text())
    if mutation == "empty":
        doc["rows"] = []
    elif mutation == "one_extra":
        doc["rows"].append({**doc["rows"][0], "receipt": "99999999999999"})
    elif mutation == "duplicate":
        doc["rows"][1] = doc["rows"][0]
    elif mutation == "claimed_hash":
        doc["rows"][0]["sha256"] = "0" * 64
    else:
        doc["route"] = "UNVERIFIED"
    path = tmp_path / "forged.json"
    path.write_text(json.dumps(doc))
    monkeypatch.setattr(C.urllib.request, "urlopen",
                        lambda *args, **kwargs: pytest.fail("unauthenticated receipt must not call DART"))
    with pytest.raises(ValueError, match="RECEIPT_BYTES_NOT_THE_AUDITED_FIXED68_SNAPSHOT"):
        C.verify(path, "synthetic-key", pause=0)


def test_reacquisition_content_mismatch_is_hard_failure_no_raw_persistence(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return b"SYNTHETIC_WRONG_CONTENT"

    monkeypatch.setattr(C.urllib.request, "urlopen", lambda *args, **kw: FakeResponse())
    with pytest.raises(ValueError, match="FIXED68_REACQUISITION_INCOMPLETE_OR_MISMATCH: matched=0"):
        C.verify(PINNED, "synthetic-key", pause=0)


def test_verify_cli_exits_nonzero_for_a_bad_receipt(monkeypatch, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"planSha256": C.PLAN_SHA256, "rows": []}))
    monkeypatch.setenv("DART_API_KEY", "synthetic-key")
    with pytest.raises(ValueError, match="RECEIPT_BYTES_NOT_THE_AUDITED_FIXED68_SNAPSHOT"):
        C.main(["verify", str(path)])
