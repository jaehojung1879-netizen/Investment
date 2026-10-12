"""Build current-only paper observations from an existing validated source.

No market download, historical label, model fitting, replay or workflow dispatch.
Usage: python scripts/build_current_champion_decisions.py SITE_JSON OUTPUT_DIR
"""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import current_champion_decisions as C  # noqa: E402
from pipeline.validate import validate  # noqa: E402


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        raise SystemExit(__doc__)
    source, output = map(Path, argv)
    errors = validate(source, production=True)
    if errors:
        raise ValueError("PRODUCTION_SOURCE_INVALID: " + ", ".join(errors))
    raw = source.read_bytes()
    result = C.publish(json.loads(raw), hashlib.sha256(raw).hexdigest(), output)
    print(json.dumps({r: {"status": b["status"], "asOfDate": b["asOfDate"],
                          "reasonCodes": b["reasonCodes"]} for r, b in result["regions"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
