"""Reproduce the real Pages #41617427637 refusal without preparing real inputs.

The consumed-study guard is an invariant, not a failure to suppress. The API
adapter below is offline and no formal execution or outcome code is called.
"""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import subprocess

import pytest

from pipeline import kr_alpha_atlas_reproducibility as V4

ROOT = Path(__file__).resolve().parents[1]


def test_maintenance_retains_the_actual_historical_pages_and_verifier_objects():
    record = json.loads((ROOT / V4.MAINTENANCE_RECORD).read_text())
    for path, field in ((V4.PAGES_WORKFLOW, "originalPagesSha256"),
                        (V4.VERIFIER_MODULE, "originalVerifierSha256")):
        raw = subprocess.check_output(["git", "show", record["referenceMain"] + ":" + path], cwd=ROOT)
        assert hashlib.sha256(raw).hexdigest() == record[field]
    assert V4.pages_maintenance_admitted(ROOT)


def test_pages_preflight_preserves_consumed_study_refusal(tmp_path, monkeypatch):
    main = "37f8cbf6b1c066f6b3c65235953648d17ebf2f69"
    github = SimpleNamespace(main=lambda: main, locks=lambda _: ["existing-global-lock"],
                             previous_results=lambda _: True)
    monkeypatch.setattr(V4.R.lifecycle, "GitHub", lambda: github)
    # The regression exercises the lifecycle gate, not CPU dispatch or inputs.
    monkeypatch.setattr(V4.NR, "verify", lambda _: None)
    called = []
    monkeypatch.setattr(V4, "prepare", lambda *args, **kwargs: called.append("inputs"))
    with pytest.raises(ValueError, match="AUDIT_REQUIRES_UNAUTHORIZED_UNCONSUMED_STUDY"):
        V4.audit(ROOT, tmp_path / "diagnostic", main)
    assert called == []
