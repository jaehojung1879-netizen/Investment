"""Label-free selection of the credit-flag generator for the v2 CRT. Reads credit and prices only.

Five candidate X designs / penalties were checked with the same posterior-predictive rule (in sample and out of time).
The first candidate written (quadratic + interaction + FAST indicators, ridge 1.0) passed in sample and failed out of
time; it was replaced, by this label-free evidence alone, with the first candidate that passed both: linear in gap200
and vol63, ridge 1.0. Every candidate's result is kept here.

    python -m research.market_risk_discovery_v1.stage2v2_generator_selection
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from . import stage2v2_crt as G
from . import stage3_execute_v2 as X

HERE = Path(__file__).resolve().parent


def _quad(a, b):
    return np.column_stack([a, b, a ** 2, b ** 2, a * b, (a < 0).astype(float), (b > 0.25).astype(float)])


CANDIDATES = {
    "quadratic_interaction_fast_ridge1": (_quad, 1.0),
    "quadratic_interaction_fast_ridge10": (_quad, 10.0),
    "linear_ridge1 (CHOSEN)": (G.x_design, 1.0),
    "linear_ridge0.1": (G.x_design, 0.1),
    "linear_logvol_ridge1": (lambda a, b: np.column_stack([a, np.log(b)]), 1.0),
}


def main() -> int:
    s = X.signal_sequence()
    out = {"labelReads": 0, "rule": "ADEQUATE iff 0 of 12 in-sample statistics outside the 99.5% band, <= 1 outside the "
                                    "95% band, and <= 1 of 10 out-of-time statistics outside the 95% band; bands include "
                                    "coefficient uncertainty (Laplace)", "candidates": {}}
    for name, (design, lam) in CANDIDATES.items():
        a = G.adequacy(s["gap"], s["vol"], s["flags"], s["months"], s["common"], lam=lam, design=design)
        out["candidates"][name] = {"adequate": a["adequate"], "inSampleOutside95": a["outside95"],
                                   "inSampleOutside995": a["outside995"], "outOfTimeOutside95": a["outOfTimeOutside95"]}
        if name.endswith("(CHOSEN)"):
            out["chosen"] = {"name": name, "adequacy": a}
    out["summary"] = {k: v["adequate"] for k, v in out["candidates"].items()}
    (HERE / "evidence" / "stage2v2-generator-selection.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps(out["candidates"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
