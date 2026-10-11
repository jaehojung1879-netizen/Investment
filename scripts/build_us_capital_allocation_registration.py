"""Write (or check) the machine-readable registration of us-capital-allocation-alpha-v1.

    python scripts/build_us_capital_allocation_registration.py          # write
    python scripts/build_us_capital_allocation_registration.py --check  # exit 1 if the committed file differs from the code

The file is generated from `pipeline.us_capital_allocation_policy.registration()` and nothing else, so the registration a reader
reviews and the rule the code runs cannot drift apart. It lives under `docs/us-capital-allocation/`, not `research_specs/` or
`docs/results/`, because the sealed Phase C registration pins those folders. It reads no price, return or outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import us_capital_allocation_policy as P   # noqa: E402

PATH = ROOT / "docs/us-capital-allocation/us-capital-allocation-alpha-v1-registration.json"
PROTECTED = ROOT / "docs/us-capital-allocation/protected-official-files.json"
MAIN_COMMIT = "f81be25dceb1a29a665d02ab6d9dd5505378e876"     # main when this registration was written


def protected_rendered() -> str:
    """sha256 of every official weekly-decision document, so a later test can prove this study never edited one."""
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "docs/weekly-decision").glob("*.json"))}
    return json.dumps({"mainCommit": MAIN_COMMIT, "docs/weekly-decision": files}, indent=1, sort_keys=True) + "\n"


def rendered() -> str:
    return json.dumps(P.registration(), indent=1, sort_keys=True, allow_nan=False, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = rendered()
    if args.check:
        same = PATH.exists() and PATH.read_text(encoding="utf-8") == text
        print("registration file %s the code" % ("matches" if same else "DIFFERS FROM"))
        return 0 if same else 1
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(text, encoding="utf-8")
    PROTECTED.write_text(protected_rendered(), encoding="utf-8")
    print("wrote %s sha256 %s designDigest %s" % (PATH.relative_to(ROOT), hashlib.sha256(text.encode()).hexdigest(), P.design_digest()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
