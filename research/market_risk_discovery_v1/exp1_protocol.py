"""Write the frozen experiment-1 protocol (exp1-protocol.json + .sha256).

    python -m research.market_risk_discovery_v1.exp1_protocol
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from . import exp1_execute as X

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE = "research/market_risk_discovery_v1"
CODE = [f"{BASE}/{f}" for f in ("__init__.py", "exp1_design.py", "exp1_panels.py", "exp1_inputs.py", "exp1_execute.py",
                                "stage2_design.py", "panels.py", "baseline_census.py", "label_census.py",
                                "stage3_execute_v2.py")] + [
    "research/market_valuation_macro_overlay_v1/__init__.py", "research/market_valuation_macro_overlay_v1/features.py",
    "research/market_valuation_macro_overlay_v1/source_probe.py"]
INPUTS = [f"{BASE}/data/raw/yahoo-SPY-chart-20261110.json.gz", f"{BASE}/data/ssga-SPY-distributions.csv",
          f"{BASE}/data/alfred-BAA-asof-month-ends.csv", f"{BASE}/data/alfred-GS10-asof-month-ends.csv",
          f"{BASE}/data/raw/fred-VIXCLS.csv.gz", f"{BASE}/data/raw/fred-VXVCLS.csv.gz", f"{BASE}/data/exp1-inputs-manifest.json"]
EVIDENCE = [f"{BASE}/evidence/exp1-readiness.json"]


def sha(rel: str) -> str:
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()


def build() -> dict:
    ready = json.loads((HERE / "evidence/exp1-readiness.json").read_text())
    return {
        "study": "market-risk-discovery-v1", "experiment": "EXP1_HISTORICAL_FORECAST_COMPARISON",
        "evidenceClass": "EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY", "inferentialClaim": None, "promotionEligible": False,
        "signalLabelJoinsWhileWritingThis": 0, "executed": False,
        "question": "Added one family at a time to gap200/vol63 at FAST-normal month-ends, which real-time information "
                    "made the 126-session first -15% SPY total-return passage more or less predictable, 2001-2026?",
        "target": "126-session first -15% passage, full-recovery episode end, risk set, right censoring (Stage 1)",
        "models": {"M0": "Jeffreys base rate", "M1": "gap200, vol63", "M2": "M1 + WIDEN_3M_ABOVE_EXPANDING_P80",
                   "M3": "M1 + CREDIT_WIDEN_3M_Z (continuous, expanding z, no threshold)",
                   "M4": "M1 + VIX close/100 at the decision close (equivalent to implied-minus-realised with vol63)",
                   "M5": "M1 + VIX/VIX3M - 1 (term structure; sample B)"},
        "samples": ready["structure"],
        "sampleBNote": "sample B (VIX3M from 2007-12-04) fails the outcome-free structure gate: its first FAST-normal "
                       "risk-set month-end is 2012-08 and only 2 episodes can be evaluated in real time. M5 will be "
                       "reported DATA_INSUFFICIENT; it is not replaced by another variable.",
        "redundancyNoLabels": ready["redundancyNoLabels"],
        "estimation": "yearly walk-forward on matured labels, ridge 1.0 on standardised inputs, evaluation from the "
                      "first year with >= 20 training rows and >= 2 training episodes (stage2_design, unchanged)",
        "warning": "p_model >= 2 x p_M0 at the same decision",
        "outputs": ["Brier, Brier skill vs M0, log loss, calibration bins per model",
                    "per evaluation episode: opportunities, warned, first warning, lead sessions; missed episodes",
                    "warning rate, warning rate on negative rows, false-alarm rows and spells",
                    "Brier and dBrier vs M1 for 2001-2012 and 2013-2026",
                    "dBrier vs M1 with each evaluation episode's positive rows excluded (evaluation side, no refit)",
                    "forecastImprovementObserved = dBrier>0 overall, in both periods and under every exclusion "
                    "(descriptive flag that gates whether an investment step may be PROPOSED; it runs nothing)"],
        "noPValues": "no p-value, rotation or CRT is computed or reported; #366 showed none is valid for this sample",
        "investment": "NOT part of this run. If a candidate shows forecastImprovementObserved, the pre-specified rule "
                      "in HISTORICAL-EXPERIMENT-PLAN-ko.md section 7 may be proposed for a separate approval.",
        "frozenConstants": X.frozen_constants(),
        "pins": {"code": {f: sha(f) for f in CODE}, "inputs": {f: sha(f) for f in INPUTS},
                 "evidence": {f: sha(f) for f in EVIDENCE}},
        "authorization": {"file": f"{BASE}/authorization-exp1.json", "keys": sorted(X.AUTH_KEYS),
                          "scope": {**X.EXPECTED_SCOPE, "protocolSha256": "<this protocol's sha256>"},
                          "requiredQuote": X.REQUIRED_QUOTE, "authenticity": "UNAUTHENTICATED_FILE_RECORD_OF_OWNER_APPROVAL",
                          "verify": "python -m research.market_risk_discovery_v1.exp1_execute --verify-only",
                          "execute": "python -m research.market_risk_discovery_v1.exp1_execute --execute"},
    }


def main() -> int:
    text = json.dumps(build(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    X.PROTOCOL.write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    X.PROTOCOL_SHA.write_text(f"{digest}  exp1-protocol.json\n")
    print(digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
