#!/usr/bin/env python3
"""Write research_specs/kr-alpha-discovery-tournament-v1.json and its .sha256 sidecar from the module definitions (pre-execution only).

Refuses to run once a result, marker, manifest or lock exists for the study: a frozen spec is never re-derived after outcomes.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import kr_alpha_tournament_execution as E  # noqa: E402


def main():
    for rel in (E.RESULT_PATH, E.MARKER_PATH, E.MANIFEST_PATH):
        if (ROOT / rel).exists():
            raise SystemExit("RESULT_EXISTS_SPEC_IS_FROZEN: " + rel)
    spec = E.build_spec(ROOT)
    (ROOT / E.SPEC_PATH).write_text(json.dumps(spec, sort_keys=True, indent=1, ensure_ascii=False) + "\n")
    (ROOT / E.SPEC_SIDECAR).write_text(E.digest(spec) + "\n")
    print(E.digest(spec))


if __name__ == "__main__":
    main()
