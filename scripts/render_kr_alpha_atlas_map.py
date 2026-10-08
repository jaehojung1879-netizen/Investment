"""Validate the kr-alpha-atlas registry and render docs/kr-alpha-atlas-information-map.md from it (`--check` compares instead of writing)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import kr_alpha_atlas_registry as A  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    registry = A.load()
    A.validate(registry)
    text = A.render_map(registry)
    target = A.ROOT / A.MAP_PATH
    if args.check:
        if target.read_text(encoding="utf-8") != text:
            raise SystemExit("MAP_OUT_OF_DATE: run scripts/render_kr_alpha_atlas_map.py")
    else:
        target.write_text(text, encoding="utf-8")
    print(json.dumps(A.summary(registry), sort_keys=True))


if __name__ == "__main__":
    main()
