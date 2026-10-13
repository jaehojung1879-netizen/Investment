"""Write the outcome-blind P4 readiness v2 report from committed reports and the recomputed pinned identities.

    python scripts/refresh_us_cash_profitability_readiness.py            # recomputes identities() (needs the signal-history commit locally)

Reads no price, return or label; builds no cohort; refuses to overwrite v1 or an existing v2.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import us_p4_readiness_refresh as R      # noqa: E402

READINESS = ROOT / "docs/us-readiness"
V1 = READINESS / "us-cash-profitability-exploratory-readiness-v1.json"
PREFLIGHT = READINESS / "us-cash-profitability-exploratory-preflight-v1.json"
SUPPLEMENT = READINESS / "us-h63-inference-calibration-v1-supplement-result.json"
OUT = READINESS / "us-cash-profitability-exploratory-readiness-v2.json"


def current_identities() -> dict[str, str]:
    spec = importlib.util.spec_from_file_location("p4_harness", ROOT / "scripts/run_us_cash_profitability_exploratory.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["p4_harness"] = module
    spec.loader.exec_module(module)
    return module.identities()


def main() -> int:
    if OUT.exists():
        raise SystemExit("READINESS_V2_ALREADY_WRITTEN")
    report = R.refresh(json.loads(V1.read_bytes()), json.loads(PREFLIGHT.read_bytes()), json.loads(SUPPLEMENT.read_bytes()),
                       current_identities(), R.sha256_file(V1), R.sha256_file(PREFLIGHT), R.sha256_file(SUPPLEMENT))
    OUT.write_text(R.canonical(report))
    print(report["scientificReadiness"], report["executionReadiness"], "->", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
