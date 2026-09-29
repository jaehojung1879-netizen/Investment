"""v2 of the fixed-sample original-XBRL validation: one entity-scheme rule.

Reuses the v1 independent reader unchanged except for a single explicit option,
`corp_code_schemes`, which v1 leaves empty. Nothing here selects a sample,
touches candidate data or reads outcomes. v1 files are only verified, never
edited.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from . import kr_xbrl_value_validation as V1

STUDY = "kr-original-xbrl-value-validation-v2"
# Published in git before the implementation and before any live run.
PROTOCOL_FREEZE_COMMIT = "14f42050fd15487f5c87717d61615e1b08701e7e"
PROTOCOL_SHA256 = "a0251b2459de1ed820c7306c822e29429d92b18b72e2063d044e34ba8db3871d"
DART_CIK_SCHEME = "http://dart.fss.or.kr/ifrs/CIK"
V2_CORP_CODE_SCHEMES = frozenset({DART_CIK_SCHEME})


def load_frozen(repo: Path):
    """Verify v1 (bytes, ancestry, sample) and v2 protocol bytes before any source access."""
    protocol_v1, sample = V1.load_frozen(repo)  # v1 ancestry, exact bytes, 60 items, sample SHA
    subprocess.run(["git", "merge-base", "--is-ancestor", PROTOCOL_FREEZE_COMMIT, "HEAD"],
                   cwd=repo, check=True, capture_output=True)
    name = "research_specs/" + STUDY + ".json"
    raw = (repo / name).read_bytes()
    if V1.sha256(raw) != PROTOCOL_SHA256:
        raise ValueError("V2_PROTOCOL_CHANGED")
    if raw != subprocess.check_output(["git", "show", PROTOCOL_FREEZE_COMMIT + ":" + name], cwd=repo):
        raise ValueError("V2_FREEZE_COMMIT_BYTES_DIFFER")
    protocol = json.loads(raw)
    if (protocol["sample"]["requiredSha256"] != V1.SAMPLE_SHA256
            or protocol["candidate"]["sha256"] != protocol_v1["candidate"]["sha256"]
            or protocol["singleSemanticChange"]["rule"].count(DART_CIK_SCHEME) != 1):
        raise ValueError("V2_PROTOCOL_DISAGREES_WITH_V1")
    return protocol_v1, protocol, sample


def validate_item(item, candidate_value, raw=None, filing_rows=None):
    return V1.validate_item(item, candidate_value, raw, filing_rows,
                            corp_code_schemes=V2_CORP_CODE_SCHEMES)
