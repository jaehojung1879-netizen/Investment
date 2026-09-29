"""v3 of the fixed-sample original-XBRL validation.

Same independent reader as v1/v2 with two explicit options: the v2 entity-scheme
rule and a presentation check demoted from mandatory gate to descriptive
corroboration, with the concept required to be an IFRS-namespace concept named by
the frozen family. No sample selection, candidate access or outcome reads here.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from . import kr_xbrl_value_validation as V1
from . import kr_xbrl_value_validation_v2 as V2

STUDY = "kr-original-xbrl-value-validation-v3"
# Published in git before the implementation and before any live run.
PROTOCOL_FREEZE_COMMIT = "8456693de19edb6950f2587bd4b671182c045d0c"
PROTOCOL_SHA256 = "302fc108b9ed37053dc1e006c1079fa730dfff5aab907fe705f008485939fe84"


def load_frozen(repo: Path):
    """Verify v1 and v2 frozen bytes/ancestry and the v3 protocol before any source access."""
    protocol_v1, protocol_v2, sample = V2.load_frozen(repo)
    subprocess.run(["git", "merge-base", "--is-ancestor", PROTOCOL_FREEZE_COMMIT, "HEAD"],
                   cwd=repo, check=True, capture_output=True)
    name = "research_specs/" + STUDY + ".json"
    raw = (repo / name).read_bytes()
    if V1.sha256(raw) != PROTOCOL_SHA256:
        raise ValueError("V3_PROTOCOL_CHANGED")
    if raw != subprocess.check_output(["git", "show", PROTOCOL_FREEZE_COMMIT + ":" + name], cwd=repo):
        raise ValueError("V3_FREEZE_COMMIT_BYTES_DIFFER")
    protocol = json.loads(raw)
    if (protocol["sample"]["requiredSha256"] != V1.SAMPLE_SHA256
            or protocol["candidate"]["sha256"] != protocol_v1["candidate"]["sha256"]
            or protocol["predecessors"]["v2"]["protocolSha256"] != V2.PROTOCOL_SHA256):
        raise ValueError("V3_PROTOCOL_DISAGREES_WITH_PREDECESSORS")
    return protocol_v1, protocol, sample


def validate_item(item, candidate_value, raw=None, filing_rows=None):
    return V1.validate_item(item, candidate_value, raw, filing_rows,
                            corp_code_schemes=V2.V2_CORP_CODE_SCHEMES, presentation_gate=False)
