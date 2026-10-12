"""Write docs/us-readiness/us-total-assets-source-decision-v1.json from pipeline/us_total_assets_decision.py. Offline; no request, no key."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import us_total_assets_decision as D  # noqa: E402

OUTPUT = ROOT / "docs/us-readiness/us-total-assets-source-decision-v1.json"


def main() -> int:
    decision = D.build()
    problems = D.validate(decision)
    if problems:
        raise SystemExit("DECISION_INVALID: " + ", ".join(problems))
    OUTPUT.write_text(json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
