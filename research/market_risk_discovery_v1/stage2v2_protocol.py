"""Write the frozen Stage 2 v2 protocol (protocol-stage2-v2.json + .sha256).

The decision field is COMPUTED here from label-free and synthetic evidence by a rule fixed before the synthetic null
validation finished (stated in AUDIT-REMEDIATION-ko.md and below):

    READY_FOR_STAGE_3 iff
      1. the real credit-flag generator is ADEQUATE on the label-free checks, and
      2. in every null environment S0-S5 the gated v2 support-verdict rate has a Clopper-Pearson 95% lower bound
         <= 0.05 and a point estimate <= 0.075, and
      3. in every null environment S0-S5 the CRT rejection rate among worlds whose generator passed the same
         adequacy gate satisfies the same two bounds.
    otherwise NOT_READY_FOR_INFERENTIAL_STAGE_3.

    python -m research.market_risk_discovery_v1.stage2v2_protocol
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from . import stage3_execute_v2 as X

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE = "research/market_risk_discovery_v1"
V1_PROTOCOL_SHA = "e8bb2aee429f4c707a69f3b38df68f6cc63850c03ad6debe1d2848d01a56c8f6"
V1_HEAD = "87c824c3f6f05c9993b458c61ac89dbf7bb0c09a"

CODE = [f"{BASE}/__init__.py", f"{BASE}/stage2_design.py", f"{BASE}/stage2v2_crt.py", f"{BASE}/panels.py",
        f"{BASE}/baseline_census.py", f"{BASE}/label_census.py", f"{BASE}/stage3_execute_v2.py",
        "research/market_valuation_macro_overlay_v1/__init__.py",
        "research/market_valuation_macro_overlay_v1/features.py"]
INPUTS = [f"{BASE}/data/raw/yahoo-SPY-chart-20261110.json.gz", f"{BASE}/data/ssga-SPY-distributions.csv",
          f"{BASE}/data/alfred-BAA-asof-month-ends.csv", f"{BASE}/data/alfred-GS10-asof-month-ends.csv"]
EVIDENCE = [f"{BASE}/evidence/stage2-readiness.json", f"{BASE}/evidence/stage2v2-generator-selection.json",
            f"{BASE}/evidence/stage2v2-null-validation.json", f"{BASE}/stage2v2_synthetic.py"]
NULLS = ("S0", "S1", "S2", "S3", "S4", "S5")
SIZE_POINT_MAX = 0.075


def sha(rel: str) -> str:
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()


def size_ok(cell: dict) -> bool:
    return cell["n"] > 0 and cell["ci95"][0] <= 0.05 and cell["rate"] <= SIZE_POINT_MAX


def decide(selection: dict, nulls: dict) -> dict:
    reasons = []
    if not selection["chosen"]["adequacy"]["adequate"]:
        reasons.append("REAL_GENERATOR_INADEQUATE")
    for e in NULLS:
        env = nulls["environments"][e]
        if not size_ok(env["v2SupportVerdict"]):
            reasons.append(f"{e}_GATED_VERDICT_OVER_REJECTS")
        if not size_ok(env["crtRejectGivenAdequate"]):
            reasons.append(f"{e}_CRT_OVER_REJECTS_GIVEN_ADEQUATE")
    return {"decision": "READY_FOR_STAGE_3" if not reasons else "NOT_READY_FOR_INFERENTIAL_STAGE_3",
            "reasons": reasons}


def build() -> dict:
    ready = json.loads((HERE / "evidence/stage2-readiness.json").read_text())
    selection = json.loads((HERE / "evidence/stage2v2-generator-selection.json").read_text())
    nulls = json.loads((HERE / "evidence/stage2v2-null-validation.json").read_text())
    dec = decide(selection, nulls)
    return {
        "study": "market-risk-discovery-v1", "stage": "STAGE_2_PREREGISTRATION_V2",
        "supersedes": {"protocol": f"{BASE}/protocol-stage2.json", "sha256": V1_PROTOCOL_SHA, "head": V1_HEAD,
                       "reason": "independent audit NOT_READY: A1 rotation null does not test Y _|_ C | X; A2 synthetic "
                                 "validation did not include price-credit dependence or misspecification; B1 marker "
                                 "not exclusive; B2 scope unchecked"},
        "evidenceClass": "EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY", "promotionEligible": False,
        "creditLabelJoinsWhileWritingThis": 0, "stage3Executed": False,
        "decision": dec["decision"], "decisionReasons": dec["reasons"],
        "decisionRule": __doc__.split("    READY_FOR_STAGE_3 iff")[1].split("    python -m")[0].strip(),
        "hypothesis": {
            "id": "P1",
            "claimTested": "A (conditional information): given the month-end price-feature path, the real-time credit "
                           "flag path carries information about the 126-session first -15% passage labels",
            "nullHypothesis": "H0: the credit-flag path, given the price-feature path, follows the generator law G and "
                              "is independent of the labels",
            "notTested": "B (whether this particular M2 forecasts better than this particular M1) is reported as dBrier "
                         "but is not what the p-value refers to; the p-value is valid for H0 whatever M1's form",
            "direction": "one-sided on dBrier (M2 better)"},
        "unchangedFromV1": ["event definition and SPY total return", "126-session horizon", "FAST = 0 month-end risk "
                            "set", "gap200 and vol63", "WIDEN_3M_ABOVE_EXPANDING_P80", "ALFRED vintages and timing",
                            "yearly walk-forward on matured labels, evaluation start 2001", "M0/M1/M2 and ridge 1.0",
                            "128 evaluation rows, 23 positive rows, 5 evaluation episodes",
                            "dBrier as the statistic"],
        "changedFromV1": {
            "null": "v1 circular rotation (independence of C from the calendar) -> v2 conditional randomization test: "
                    "999 whole flag paths drawn from G(C_t | gap_t, vol_t, C_t-1, C_t-2), M2 refitted on each",
            "gate": "v2 adds a label-free generator adequacy gate; GENERATOR_INADEQUATE_NO_INFERENCE if it fails",
            "verdict": "EXPLORATORY_CONDITIONAL_INFORMATION_SUPPORT iff adequacy AND dBrier > 0 AND CRT p <= 0.05 AND "
                       "dBrier > 0 under every single-episode exclusion (evaluation side, no refit)",
            "auxiliaryPValues": "v1 rotation p-values for log loss and event hits are dropped; v2 reports a CRT p for "
                                "log loss and event metrics without p-values",
            "harness": "exclusive O_CREAT|O_EXCL marker, failure record, no-overwrite publication, structured scope"},
        "generator": {"form": "logistic: intercept, C_t-1, C_t-2, gap200_t, vol63_t (standardised), ridge 1.0, fitted "
                              "on all 337 defined months, all FAST states, no label",
                      "selection": selection["summary"], "realAdequacy": selection["chosen"]["adequacy"]},
        "nullValidation": nulls,
        "structure": ready["structure"]["gate"],
        "frozenConstants": X.frozen_constants(),
        "pins": {"code": {f: sha(f) for f in CODE}, "inputs": {f: sha(f) for f in INPUTS},
                 "evidence": {f: sha(f) for f in EVIDENCE}},
        "stage3Authorization": {
            "file": f"{BASE}/authorization-stage3-v2.json", "keys": sorted(X.AUTH_KEYS),
            "scope": {**X.EXPECTED_SCOPE, "protocolSha256": "<this protocol's sha256>"},
            "requiredQuote": X.REQUIRED_QUOTE, "authenticity": X.AUTHENTICITY,
            "verifyCommand": "python -m research.market_risk_discovery_v1.stage3_execute_v2 --verify-only",
            "executeCommand": "python -m research.market_risk_discovery_v1.stage3_execute_v2 --execute"},
    }


def main() -> int:
    spec = build()
    text = json.dumps(spec, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    X.PROTOCOL.write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    X.PROTOCOL_SHA.write_text(f"{digest}  protocol-stage2-v2.json\n")
    print(spec["decision"], spec["decisionReasons"], digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
