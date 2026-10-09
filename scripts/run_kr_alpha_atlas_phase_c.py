"""Safe default: validate frozen registration; historical execution requires human gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.kr_alpha_atlas_phase_c import contract  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["freeze", "validate", "synthetic", "execute"], nargs="?", default="validate")
    parser.add_argument("--snapshot-archive", type=Path)
    parser.add_argument("--work", type=Path, default=Path("/tmp/kr-alpha-atlas-phase-c"))
    args = parser.parse_args()
    if args.mode == "freeze":
        # Before outcomes only. Never available in the formal workflow.
        from pipeline.kr_alpha_atlas_phase_c.lifecycle import GitHub

        github = GitHub()
        if github.locks("refs/tags/" + contract.STUDY + "-execution-lock") or github.previous_results(
            contract.STUDY + "-results-"
        ):
            raise ValueError("CONSUMED_REGISTRATION_CANNOT_BE_REFROZEN")
        spec = contract.build()
        (contract.ROOT / contract.SPEC).write_bytes(
            json.dumps(spec, indent=2, ensure_ascii=False, allow_nan=False).encode() + b"\n"
        )
        (contract.ROOT / contract.SIDECAR).write_text(contract.file_hash(contract.ROOT / contract.SPEC) + "\n")
    elif args.mode == "validate":
        from pipeline.kr_alpha_atlas_phase_c.preflight import verify_git_inputs

        spec = contract.load()
        facts = contract.calendar_facts(spec)
        inputs = verify_git_inputs(contract.ROOT, spec)
        print(
            json.dumps(
                {
                    "registration": "VALID",
                    "compute": spec["compute"],
                    "calendar": facts,
                    "inputSchemas": inputs,
                    "realOutcomeReads": 0,
                },
                ensure_ascii=False,
            )
        )
    elif args.mode == "synthetic":
        from pipeline.kr_alpha_atlas_phase_c.synthetic import complete_study

        spec = contract.load()
        result = complete_study(spec, args.work)
        print(json.dumps(result, ensure_ascii=False))
    else:
        from pipeline.kr_alpha_atlas_phase_c.lifecycle import formal

        print(json.dumps(formal(snapshot_archive=args.snapshot_archive, work=args.work), ensure_ascii=False))


if __name__ == "__main__":
    main()
