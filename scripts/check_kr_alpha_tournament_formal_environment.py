"""Cheap preflight for the kr-alpha-discovery-tournament-v1 post-outcome integrity audit: is this interpreter the one the formal execution ran in?

POST_OUTCOME_FORENSIC_REPRODUCIBILITY_ENGINEERING. Runs BEFORE the raw snapshot is downloaded and before any reconstruction. Exit 0 only when the Python
environment (exact CPython patch release, every package version of the formal execute job, the thread variables, the constraint file) matches the committed
manifest. The host (runner image, CPU, BLAS kernels) is recorded and classified, never gating. The record is written either way so the artifact says what
this run actually looked like. Reads no market data, no label and no sealed result; takes no lock; makes no network call.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import kr_alpha_tournament_formal_environment as FE  # noqa: E402


def run(manifest_root=ROOT, output=None, observed=None, constraints_path=None):
    manifest = FE.load_manifest(manifest_root)
    constraints = Path(constraints_path or (Path(manifest_root) / FE.CONSTRAINTS_PATH))
    on_disk = constraints.read_text() if constraints.exists() else ""
    record = FE.parity_record(manifest, observed if observed is not None else FE.observe_environment(), on_disk)
    if output:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    record = run(output=args.output)
    summary = {"pythonEnvironment": record["pythonEnvironment"]["classification"], "host": record["host"]["classification"],
               "observedPython": record["observed"]["python"]["version"], "formalPython": record["pythonEnvironment"]["checked"]["pythonPatchRelease"]}
    print(json.dumps(summary, sort_keys=True))
    if not record["ok"]:
        for line in record["pythonEnvironment"]["failures"]:
            print("  " + line)
        print(FE.PARITY_FAILURE + ": the expensive study is NOT started in a knowingly different Python environment")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
