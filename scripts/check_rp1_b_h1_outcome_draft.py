"""Outcome-free feasibility smoke; never formal calibration or registration.

Run: python -m scripts.check_rp1_b_h1_outcome_draft
Only the existing synthetic protocol JSON is read. Nothing fetches market data.
"""
import json
from pathlib import Path

import numpy as np

from pipeline import alpha_inference_calibration_v4 as V4
from pipeline import rp1_b_h1_outcome_draft as D

ROOT = Path(__file__).resolve().parents[1]
SEED = 2026103101  # development stream; never a formal seed
REPLICATES = 48


def smoke():
    spec = json.loads((ROOT / "research_specs/alpha-inference-calibration-v5.json").read_text())
    spec = {**spec, "namesPerDate": 120, "seed": SEED}
    out = []
    # Six per state is only an inherited support floor, not a calibrated depth.
    for j, dgp in enumerate(spec["dgps"]):
        for pattern in ("ALTERNATING", "CLUSTERED"):
            states = ["adverse", "notAdverse"] * 6 if pattern == "ALTERNATING" else ["adverse"] * 6 + ["notAdverse"] * 6
            covered = positive = undefined = 0
            largest_identity_error = 0.0
            widths = []
            for r in range(REPLICATES):
                # Exact 12*63 daily rows; v4 generates weeks on a five-session grid.
                draw = V4.simulate_replicate(spec, dgp, horizon=63, weeks=140, replicate=r, dgp_index=j)
                daily = draw["daily"][:12 * 63]
                score = draw["selectionScore"][np.arange(12) * 63 // 5]
                weights = np.zeros((12, 120))
                for k in range(12):
                    order = np.argsort(-score[k], kind="stable")
                    weights[k, order[:40]], weights[k, order[-40:]] = 1 / 40, -1 / 40
                series, _, ci = D.state_contrast_attribution(daily, weights, states)
                block_values = np.einsum("bsi,bi->b", daily.reshape(12, 63, 120), weights)
                target = np.mean(block_values[np.array(states) == "notAdverse"]) - np.mean(block_values[np.array(states) == "adverse"])
                error = abs(float(series.sum()) - float(target))
                largest_identity_error = max(largest_identity_error, error)
                if not np.isclose(series.sum(), target, rtol=1e-11, atol=1e-11):
                    raise AssertionError("CALENDAR_ATTRIBUTION_NOT_EXACT")
                if ci is None:
                    undefined += 1
                else:
                    covered += ci["lower"] <= 0 <= ci["upper"]
                    positive += ci["lower"] > 0
                    widths.append(ci["width"])
            out.append({"dgp": dgp["name"], "pattern": pattern, "replicates": REPLICATES,
                        "coverageCount": int(covered), "positiveFalsePositiveCount": int(positive), "undefinedCount": undefined,
                        "maxAttributionIdentityError": largest_identity_error,
                        "medianIntervalWidthSyntheticUnits": float(np.median(widths)) if widths else None})
    return {"status": "DEVELOPMENT_SMOKE_NOT_CALIBRATION", "marketOutcomeReads": 0,
            "seed": SEED, "replicatesPerCell": REPLICATES, "calibrated": False,
            "limitation": "Additive synthetic returns, independent synthetic scores, exogenous balanced states only. Does not calibrate original momentum, compounded total returns, endogenous states, imbalance or selection missingness.",
            "cells": out, "liveGate": D.live_gate({"status": "REGISTERED"})}


if __name__ == "__main__":
    print(json.dumps(smoke(), sort_keys=True, indent=2))
