"""Experiment 1 readiness: outcome-free facts. Sample structure uses presence proxies (no signal value meets a label);
redundancy uses signal values only (no label). Writes evidence/exp1-readiness.json.

    python -m research.market_risk_discovery_v1.exp1_readiness
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from . import exp1_design as E
from . import exp1_panels as EP

HERE = Path(__file__).resolve().parent


def redundancy(rows: list[dict]) -> dict:
    """Spearman-free, plain Pearson correlations among the features on sample-A rows. No label is read."""
    keep = E.sample_rows(rows, "A")
    out = {"rows": len(keep), "pairs": {}}
    feats = ("gap", "vol", "flag", "credit_z", "vix")
    X = {f: np.array([r[f] for r in keep], float) for f in feats}
    for i, a in enumerate(feats):
        for b in feats[i + 1:]:
            out["pairs"][f"{a}~{b}"] = float(np.corrcoef(X[a], X[b])[0, 1])
    # linear overlap with (gap, vol) only; the unexplained share is NOT evidence of predictive information
    A = np.column_stack([np.ones(len(keep)), X["gap"], X["vol"]])
    for f in ("vix", "credit_z", "flag"):
        res = X[f] - A @ np.linalg.lstsq(A, X[f], rcond=None)[0]
        out[f"{f}_R2_on_gap_vol"] = float(1 - res.var() / X[f].var())
    return out


def main() -> int:
    pres = EP.rows("presence")
    struct = {s: E.structure(E.Panel(E.sample_rows(pres["rows"], s)), pres["refits"]) for s in E.SAMPLES}
    red = redundancy(EP.rows("signal")["rows"])      # values without any label
    report = {"stage": "EXP1_READINESS", "signalLabelJoins": 0, "structure": struct, "redundancyNoLabels": red,
              "inputsManifest": json.loads((HERE / "data" / "exp1-inputs-manifest.json").read_text())}
    (HERE / "evidence" / "exp1-readiness.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"structure": struct, "redundancy": red}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
