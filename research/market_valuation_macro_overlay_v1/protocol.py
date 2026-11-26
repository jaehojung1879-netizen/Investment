"""Load and verify the frozen MVMA-v1 protocol. Refuses anything that would let an outcome in or move a rule.

`load_protocol` checks, on every load:

* the file's SHA-256 equals the committed sidecar `protocol.sha256` (an edit is a new protocol, not a silent change),
* every firewall flag is false and no execution authorization is named,
* the registered constants equal the ones `features` and `signals` actually use, so the prose and the code cannot
  drift apart,
* only ELIGIBLE hypotheses sit in the Holm family, and no SOURCE_BLOCKED / NOT_RUN cell is counted in it,
* forward and trailing variants are never registered under one name,
* the evaluation window's month count matches its stated dates,
* no forbidden result semantics (a p-value, a winner, a recommended weight) appear anywhere in it.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from . import features, signals

HERE = Path(__file__).resolve().parent
PROTOCOL_PATH = HERE / "protocol.json"
SIDECAR_PATH = HERE / "protocol.sha256"
FIREWALL_FLAGS = ("outcomeExecutionAuthorized", "promotionEligible", "productionChange", "liveValidated",
                  "modelSelectionAfterOutcomeAllowed", "thresholdChangeAfterOutcomeAllowed",
                  "rerunAfterSubstantiveResultAllowed")
FORBIDDEN_KEYS = frozenset({"pValue", "pValues", "winner", "bestPolicy", "recommendedWeight", "result", "results",
                            "cagr", "sharpe", "forwardReturn", "nav", "excessReturn"})
ELIGIBLE = "ELIGIBLE_EXPLORATORY_PENDING_DATA_BUILD"


class ProtocolError(ValueError):
    pass


def _walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_keys(item)


def _months_inclusive(first: str, last: str) -> int:
    a, b = date.fromisoformat(first), date.fromisoformat(last)
    return (b.year - a.year) * 12 + (b.month - a.month) + 1


def validate(spec: dict) -> dict:
    firewall = spec.get("firewall", {})
    for flag in FIREWALL_FLAGS:
        if firewall.get(flag) is not False:
            raise ProtocolError("FIREWALL_FLAG_NOT_FALSE: " + flag)
    if firewall.get("executionAuthorizationFile") is not None:
        raise ProtocolError("EXECUTION_AUTHORIZATION_PRESENT")
    if spec.get("evidenceClassification") != "EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY":
        raise ProtocolError("EVIDENCE_CLASSIFICATION_CHANGED")
    if not spec.get("developmentStatement"):
        raise ProtocolError("DEVELOPMENT_STATEMENT_MISSING")

    hits = sorted(k for k in set(_walk_keys(spec)) if k in FORBIDDEN_KEYS)
    if hits:
        raise ProtocolError("FORBIDDEN_RESULT_KEYS: " + ",".join(hits))

    s = spec["signals"]
    code = {
        "PE_HISTORY_MONTHS": features.PE_HISTORY_MONTHS, "PE_HISTORY_MIN_VALID": features.PE_HISTORY_MIN_VALID,
        "EARNINGS_CHANGE_MONTHS": features.EARNINGS_CHANGE_MONTHS,
        "CREDIT_HISTORY_MONTHS": features.CREDIT_HISTORY_MONTHS,
        "CREDIT_HISTORY_MIN_VALID": features.CREDIT_HISTORY_MIN_VALID,
        "CREDIT_PERCENTILE": features.CREDIT_PERCENTILE, "CREDIT_WIDENING_MONTHS": features.CREDIT_WIDENING_MONTHS,
        "DRAWDOWN_WINDOW_SESSIONS": features.DRAWDOWN_WINDOW_SESSIONS, "DRAWDOWN_TRIGGER": features.DRAWDOWN_TRIGGER,
    }
    for key, value in code.items():
        if s.get(key) != value:
            raise ProtocolError(f"SIGNAL_CONSTANT_MISMATCH: {key} spec={s.get(key)} code={value}")

    policies = spec["policies"]
    for name, weight in signals.STATIC_POLICIES.items():
        if policies[name].get("weight") != weight:
            raise ProtocolError("STATIC_WEIGHT_MISMATCH: " + name)
    for name, policy in policies.items():
        if policy["kind"] != "DYNAMIC" or policy.get("status") == "SOURCE_BLOCKED":
            continue
        rule_name = name.rstrip("TF") if name.endswith(("1T", "1F")) else name
        if rule_name not in signals.RULES:
            raise ProtocolError("POLICY_WITHOUT_RULE: " + name)
        if list(policy["inputs"]) != list(signals.RULES[rule_name][1]):
            raise ProtocolError("POLICY_INPUTS_MISMATCH: " + name)
    for name in ("M1", "VM1"):
        if name in policies:
            raise ProtocolError("UNQUALIFIED_EARNINGS_VARIANT: " + name + " must be registered as T or F")

    primaries = [h for h in spec["hypotheses"] if h["holmFamily"] == "PRIMARY"]
    for h in spec["hypotheses"]:
        if h["holmFamily"] == "PRIMARY" and h["status"] != ELIGIBLE:
            raise ProtocolError("INELIGIBLE_HYPOTHESIS_IN_FAMILY: " + h["id"])
        if h["status"] in ("SOURCE_BLOCKED", "NOT_RUN") and h["holmFamily"] != "NOT_IN_FAMILY":
            raise ProtocolError("UNAVAILABLE_HYPOTHESIS_IN_FAMILY: " + h["id"])
    if not primaries:
        raise ProtocolError("EMPTY_PRIMARY_FAMILY")
    ids = [h["id"] for h in spec["hypotheses"]]
    if len(ids) != len(set(ids)):
        raise ProtocolError("DUPLICATE_HYPOTHESIS_ID")

    window = spec["calendar"]["evaluationWindowUS"]
    months = _months_inclusive(window["firstDecision"], window["lastDecision"])
    if months != window["months"]:
        raise ProtocolError(f"WINDOW_MONTH_COUNT_MISMATCH: {months} != {window['months']}")
    if months // 12 < spec["inference"]["minIndependentBlocks"]:
        raise ProtocolError("TOO_FEW_INDEPENDENT_BLOCKS")

    if spec["signalSources"]["US_TRAILING_PE"]["earningsLagMonths"] != features.SHILLER_EARNINGS_LAG_MONTHS:
        raise ProtocolError("EARNINGS_LAG_MISMATCH")
    if spec["markets"]["KR"]["status"] != "NOT_RUN_PHASE_D_GOVERNANCE":
        raise ProtocolError("KR_STATUS_CHANGED_WITHOUT_EXCEPTION")
    return spec


def load_protocol(path: Path = PROTOCOL_PATH, sidecar: Path = SIDECAR_PATH) -> dict:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    expected = sidecar.read_text().split()[0]
    if digest != expected:
        raise ProtocolError(f"PROTOCOL_DIGEST_MISMATCH: {digest} != {expected}")
    return validate(json.loads(raw))
