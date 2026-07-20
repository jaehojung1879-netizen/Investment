"""Write a production state snapshot after validation and deployment succeed."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.state import snapshot_from_payload  # noqa: E402
from pipeline.validate import validate  # noqa: E402


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 2:
        print("usage: python scripts/update_state.py <site-data.json> <state/latest.json>")
        return 2
    artifact, destination = map(Path, argv)
    errors = validate(artifact, production=True)
    if errors:
        print("refusing to publish invalid production state:", ", ".join(errors))
        return 1
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    snapshot = snapshot_from_payload(payload, validation_passed=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote validated state: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
