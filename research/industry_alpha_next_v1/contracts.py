"""Small synthetic acceptance oracles. No files, network, fitted models or real loaders.

These functions specify contracts for a future independently audited implementation.
They are not an investment model or an authorization mechanism.
"""
from __future__ import annotations

import math
from datetime import datetime


def _synthetic(scope):
    if scope != "SYNTHETIC_FIXTURE":
        raise ValueError("SYNTHETIC_ONLY")


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def visible_assignment(row, signal, *, scope):
    """Strict lane: release visibility AND economic validity AND dated identity."""
    _synthetic(scope)
    required = ("security_id", "industry_id", "taxonomy_version", "source_sha256")
    if any(not isinstance(row.get(k), str) or not row[k] for k in required):
        return False
    digest = row["source_sha256"]
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        return False
    if row.get("evidence_class") != "PIT_CONFIRMED":
        return False
    try:
        ts = datetime.fromisoformat(signal)
        release = datetime.fromisoformat(row["published_at"])
        start = datetime.fromisoformat(row["valid_from"])
        end = datetime.fromisoformat(row["valid_to"]) if row.get("valid_to") else None
        if any(x.tzinfo is None for x in (ts, release, start)) or (end and end.tzinfo is None):
            return False
        return release < ts and start <= ts and (end is None or ts < end)
    except (KeyError, TypeError, ValueError):
        return False


def frozen_return(weights, outcomes, *, scope):
    """All frozen peers are required; missing terminal consideration blocks the block."""
    _synthetic(scope)
    if not weights or any(not _finite(w) or w <= 0 for w in weights.values()):
        raise ValueError("INVALID_WEIGHTS")
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12):
        raise ValueError("WEIGHTS_NOT_ONE")
    if any(not _finite(outcomes.get(k)) or outcomes[k] < -1 for k in weights):
        return None
    return sum(w * outcomes[k] for k, w in weights.items())


def excluding(weights, removed, *, scope, minimum=5):
    """Remove identities before ALL features/targets; rerun depth gate, then normalize."""
    _synthetic(scope)
    if not weights or any(not _finite(w) or w <= 0 for w in weights.values()):
        raise ValueError("INVALID_WEIGHTS")
    kept = {k: w for k, w in weights.items() if k not in removed}
    if len(kept) < minimum:
        return None
    total = sum(kept.values())
    return {k: w / total for k, w in kept.items()}


def paired_population_receipt(base, alternative, targets, *, scope,
                              intended_by_block, missing_reasons=None):
    """Conservative signal-frozen paired outcome admission; synthetic only.

    A block with any missing outcome or forecast is entirely blocked. This
    prevents a survivor-only intersection from silently entering a paired test.
    """
    _synthetic(scope)
    if not isinstance(intended_by_block, dict) or not intended_by_block:
        raise ValueError("INTENDED_SIGNAL_POPULATION_REQUIRED")
    if not all(isinstance(x, dict) for x in (base, alternative, targets)):
        raise ValueError("PAIRED_INPUTS_MUST_BE_DICTS")
    missing_reasons = {} if missing_reasons is None else missing_reasons
    if not isinstance(missing_reasons, dict):
        raise ValueError("INVALID_MISSING_REASONS")
    reasons = {"UNKNOWN_TERMINAL_ECONOMICS", "SOURCE_OUTAGE",
               "OUTCOME_NOT_MATURED", "RETURN_BASIS_UNRESOLVED",
               "CORPORATE_ACTION_UNRESOLVED"}
    ids = []
    for block, members in intended_by_block.items():
        if not isinstance(block, str) or not block or not isinstance(members, (list, tuple)) or not members:
            raise ValueError("INVALID_SIGNAL_BLOCK")
        if any(not isinstance(x, str) or not x for x in members) or len(set(members)) != len(members):
            raise ValueError("INVALID_SIGNAL_MEMBERS")
        ids.extend(members)
    if len(set(ids)) != len(ids):
        raise ValueError("DUPLICATE_MEMBER_ACROSS_BLOCKS")
    if any(set(d) - set(ids) for d in (base, alternative, targets, missing_reasons)):
        raise ValueError("POST_SIGNAL_SURVIVOR_ADDITION")
    if any(r not in reasons for r in missing_reasons.values()):
        raise ValueError("UNKNOWN_OUTCOME_MISSING_REASON")
    blocks, accepted, missing_total = {}, [], 0
    for block, members in sorted(intended_by_block.items()):
        missing = {}
        for x in members:
            value = targets.get(x)
            if not _finite(value) or value < -1:
                missing[x] = missing_reasons.get(x, "UNDOCUMENTED_MISSING_OUTCOME")
            elif x in missing_reasons:
                raise ValueError("CONTRADICTORY_OUTCOME_MISSING_REASON")
            elif not _finite(base.get(x)):
                missing[x] = "BASE_FORECAST_MISSING"
            elif not _finite(alternative.get(x)):
                missing[x] = "ALT_FORECAST_MISSING"
        missing_total += len(missing)
        if not missing:
            accepted.extend(members)
        blocks[block] = {
            "intendedIds": tuple(sorted(members)),
            "status": "BLOCKED" if missing else "COMPLETE",
            "missing": {x: missing[x] for x in sorted(missing)},
        }
    ready = missing_total == 0
    return {
        "status": "COMPLETE" if ready else "BLOCKED_INCOMPLETE_INTENDED_POPULATION",
        "evidenceClass": "SYNTHETIC_CONTRACT_ONLY",
        "intendedIds": tuple(sorted(ids)),
        "intendedCount": len(ids), "missingCount": missing_total,
        "completeBlockCount": sum(x["status"] == "COMPLETE" for x in blocks.values()),
        "blockedBlockCount": sum(x["status"] == "BLOCKED" for x in blocks.values()),
        "coverage": len(accepted) / len(ids),
        "commonIds": tuple(sorted(accepted)) if ready else (),
        "inferentialComparisonAllowed": ready,
        "blocks": blocks,
    }


def common_ids(base, alternative, targets, *, scope, intended_by_block=None,
               missing_reasons=None):
    """No silent intersection: require complete signal-frozen paired population."""
    receipt = paired_population_receipt(
        base, alternative, targets, scope=scope,
        intended_by_block=intended_by_block, missing_reasons=missing_reasons)
    if not receipt["inferentialComparisonAllowed"]:
        raise ValueError("BLOCKED_INCOMPLETE_INTENDED_POPULATION")
    return receipt["commonIds"]


def training_ids(rows, test_start, *, scope, embargo=21):
    """Session ordinals; the entire label interval must finish before the embargo."""
    _synthetic(scope)
    return tuple(r["id"] for r in rows
                 if r["signal"] < test_start and r["entry"] < r["exit"]
                 and r["exit"] < test_start - embargo)


def simple_excess(industry, market, *, scope):
    _synthetic(scope)
    if not _finite(industry) or not _finite(market):
        return None
    return industry - market


def paired_net_delta(gross_base, gross_alt, cost_base, cost_alt, *, scope):
    _synthetic(scope)
    values = (gross_base, gross_alt, cost_base, cost_alt)
    if not all(_finite(v) for v in values):
        return None
    if cost_base < 0 or cost_alt < 0:
        raise ValueError("NEGATIVE_COST")
    return (gross_alt - cost_alt) - (gross_base - cost_base)


def leader_gap(trailing, leaders, *, scope):
    """Signal-frozen leaders and disjoint laggards; no forward winners as leaders."""
    _synthetic(scope)
    if not leaders or not set(leaders) < set(trailing):
        return None
    laggards = set(trailing) - set(leaders)
    if not all(_finite(v) for v in trailing.values()):
        return None
    return (sum(trailing[k] for k in leaders) / len(leaders)
            - sum(trailing[k] for k in laggards) / len(laggards))
