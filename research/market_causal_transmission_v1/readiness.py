"""Outcome-free readiness for MCT-v1: signal frequencies, state cells and shock counts. Reads no return."""
from __future__ import annotations

import json
import sys
from collections import Counter
from itertools import product
from pathlib import Path

from . import panel as P
from . import transmission as T

HERE = Path(__file__).resolve().parent
TRAIN, OOS = ("1970-01", "1989-12"), ("1990-01", "2024-08")
KEYS = ("highPe", "highCape", "earnDown", "creditStress", "trendDown", "volHigh", "vulnTriple")


def build() -> dict:
    rows = P.signals()
    out = {"study": "market-causal-transmission-v1", "stage": "READINESS_OUTCOME_FREE", "outcomeReads": 0}
    for name, (a, b) in (("training", TRAIN), ("outOfSample", OOS)):
        sub = [r for r in rows if a <= r["month"] <= b]
        out[name] = {"months": len(sub), "first": sub[0]["month"], "last": sub[-1]["month"],
                     "signals": {k: {str(v): n for v, n in Counter(r[k] for r in sub).items()} for k in KEYS}}
        cells = Counter()
        for r in sub:
            parts = (r["highPe"], r["earnDown"], r["creditStress"])
            cells["MISSING" if None in parts else "".join("1" if v else "0" for v in parts)] += 1
        out[name]["vulnCells_PE_EARN_CREDIT"] = {k: cells.get(k, 0) for k in
                                                 ["".join(c) for c in product("01", repeat=3)] + ["MISSING"]}
    shocks = T.shock_panel()
    out["H1"] = {"months": len(shocks), "first": shocks[0]["month"], "last": shocks[-1]["month"],
                 "mpNonZero": sum(r["MP"] != 0 for r in shocks), "cbiNonZero": sum(r["CBI"] != 0 for r in shocks),
                 "bothNonZero": sum(r["MP"] != 0 and r["CBI"] != 0 for r in shocks),
                 "mpsAvailable": sum(r["MPS"] is not None for r in shocks),
                 "scale": T.shock_scale(shocks, ["MP", "CBI", "MPS", "MPS_ORTH"]),
                 "controlsMissing": sum(any(r[k] is None for k in T.CONTROLS) for r in shocks)}
    return out


def main() -> int:
    report = build()
    (HERE / "evidence" / "readiness.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
