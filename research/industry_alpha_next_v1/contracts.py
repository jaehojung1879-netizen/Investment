"""Small synthetic acceptance oracles. No files, network, fitted models or real loaders.

These functions specify contracts for a future independently audited implementation.
They are not an investment model or an authorization mechanism.
"""
from __future__ import annotations

import hashlib
import json
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


MISSING_REASONS = frozenset({
    "UNKNOWN_TERMINAL_ECONOMICS", "SOURCE_OUTAGE", "RETURN_BASIS_UNRESOLVED",
    "CORPORATE_ACTION_UNRESOLVED", "IDENTITY_UNRESOLVED",
    "INDUSTRY_UNCLASSIFIED", "TRADING_HALT"})
TERMINAL_REASONS = frozenset({"UNKNOWN_TERMINAL_ECONOMICS"})


def intended_digest(intended_by_block):
    """SHA-256 of the signal-time cohort; seal it BEFORE any outcome is read."""
    canon = {b: sorted(m) for b, m in sorted(intended_by_block.items())}
    return hashlib.sha256(json.dumps(canon, sort_keys=True, separators=(",", ":"))
                          .encode()).hexdigest()


def _reasons(value):
    seq = (value,) if isinstance(value, str) else value
    if not isinstance(seq, (list, tuple)) or not seq or any(r not in MISSING_REASONS for r in seq):
        raise ValueError("UNKNOWN_OUTCOME_MISSING_REASON")
    return tuple(sorted(set(seq)))


def _receipt_sha(receipt):
    body = {k: v for k, v in receipt.items() if k != "receiptSha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=list,
                                     separators=(",", ":")).encode()).hexdigest()


def paired_population_receipt(base, alternative, targets, *, scope,
                              intended_by_block, sealed_intended_sha256,
                              minimum_complete_blocks, not_matured_blocks=(),
                              missing_reasons=None):
    """Signal-frozen paired admission, BLOCK-scoped; synthetic only.

    Records are keyed by (block, member): the same security legitimately recurs
    on every signal date, duplicates are rejected only inside one block.
    The intended cohort must match a digest sealed before outcomes. A block with
    any missing outcome/forecast is blocked as a whole and reported by reason;
    other complete blocks remain admissible only if their count reaches the
    pre-registered minimum. Blocks not yet matured are decided by the calendar
    (``not_matured_blocks``), never by the presence of an outcome. Rule (b) of
    audit R3; the study-wide alternative awaits owner confirmation.
    """
    _synthetic(scope)
    if not isinstance(intended_by_block, dict) or not intended_by_block:
        raise ValueError("INTENDED_SIGNAL_POPULATION_REQUIRED")
    if not all(isinstance(x, dict) for x in (base, alternative, targets)):
        raise ValueError("PAIRED_INPUTS_MUST_BE_DICTS")
    if isinstance(minimum_complete_blocks, bool) or not isinstance(minimum_complete_blocks, int) \
            or minimum_complete_blocks < 1:
        raise ValueError("MINIMUM_COMPLETE_BLOCKS_REQUIRED")
    missing_reasons = {} if missing_reasons is None else missing_reasons
    if not isinstance(missing_reasons, dict):
        raise ValueError("INVALID_MISSING_REASONS")
    keys = []
    for block, members in intended_by_block.items():
        if not isinstance(block, str) or not block or not isinstance(members, (list, tuple)) or not members:
            raise ValueError("INVALID_SIGNAL_BLOCK")
        if any(not isinstance(x, str) or not x for x in members) or len(set(members)) != len(members):
            raise ValueError("INVALID_SIGNAL_MEMBERS")
        keys.extend((block, m) for m in members)
    if intended_digest(intended_by_block) != sealed_intended_sha256:
        raise ValueError("INTENDED_COHORT_DIGEST_MISMATCH")
    unmatured = set(not_matured_blocks)
    if unmatured - set(intended_by_block):
        raise ValueError("UNKNOWN_NOT_MATURED_BLOCK")
    universe = set(keys)
    if any(set(d) - universe for d in (base, alternative, targets, missing_reasons)):
        raise ValueError("POST_SIGNAL_SURVIVOR_ADDITION")
    parsed = {k: _reasons(v) for k, v in missing_reasons.items()}
    blocks, accepted = {}, []
    by_reason, missing_total, terminal_missing = {}, 0, 0
    for block, members in sorted(intended_by_block.items()):
        if block in unmatured:
            blocks[block] = {"intendedIds": tuple(sorted(members)),
                             "status": "NOT_MATURED_BY_CALENDAR", "missing": {}}
            continue
        missing = {}
        for m in members:
            k, value = (block, m), targets.get((block, m))
            if not _finite(value) or value < -1:
                missing[m] = parsed.get(k, ("UNDOCUMENTED_MISSING_OUTCOME",))
            elif k in parsed:
                raise ValueError("CONTRADICTORY_OUTCOME_MISSING_REASON")
            elif not _finite(base.get(k)):
                missing[m] = ("BASE_FORECAST_MISSING",)
            elif not _finite(alternative.get(k)):
                missing[m] = ("ALT_FORECAST_MISSING",)
        for rs in missing.values():
            missing_total += 1
            terminal_missing += bool(TERMINAL_REASONS & set(rs))
            for r in rs:
                by_reason[r] = by_reason.get(r, 0) + 1
        if not missing:
            accepted.extend((block, m) for m in members)
        blocks[block] = {"intendedIds": tuple(sorted(members)),
                         "status": "BLOCKED" if missing else "COMPLETE",
                         "missing": {m: missing[m] for m in sorted(missing)}}
    complete = sum(x["status"] == "COMPLETE" for x in blocks.values())
    blocked = sum(x["status"] == "BLOCKED" for x in blocks.values())
    ready = complete >= minimum_complete_blocks
    receipt = {
        "status": ("COMPLETE" if ready and not blocked else
                   "PARTIAL_BLOCKS_REPORTED" if ready else "BLOCKED_INSUFFICIENT_COMPLETE_BLOCKS"),
        "evidenceClass": "SYNTHETIC_CONTRACT_ONLY",
        "admissionRule": "BLOCK_SCOPED_MINIMUM_COMPLETE_BLOCKS",
        "intendedCohortSha256": sealed_intended_sha256,
        "intendedBlockCount": len(blocks), "intendedMemberCount": len(keys),
        "notMaturedBlockCount": len(unmatured),
        "completeBlockCount": complete, "blockedBlockCount": blocked,
        "minimumCompleteBlocks": minimum_complete_blocks,
        "missingCount": missing_total, "terminalMissingCount": terminal_missing,
        "missingByReason": dict(sorted(by_reason.items())),
        "evaluatedMemberCoverage": (len(accepted) / sum(len(intended_by_block[b]) for b in blocks
                                                       if b not in unmatured)
                                    if len(unmatured) < len(blocks) else None),
        "commonIds": tuple(sorted(accepted)) if ready else (),
        "inferentialComparisonAllowed": ready,
        "blocks": blocks,
    }
    receipt["receiptSha256"] = _receipt_sha(receipt)
    return receipt


def common_ids(*args, **kwargs):
    """No silent intersection: only an approved receipt yields (block, member) ids."""
    receipt = paired_population_receipt(*args, **kwargs)
    if not receipt["inferentialComparisonAllowed"]:
        raise ValueError("BLOCKED_INSUFFICIENT_COMPLETE_BLOCKS")
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


def paired_net_delta(receipt, key, gross_base, gross_alt, cost_base, cost_alt, *, scope):
    """Net paired increment for ONE (block, member) id of an approved receipt."""
    _synthetic(scope)
    if (not isinstance(receipt, dict) or not receipt.get("inferentialComparisonAllowed")
            or receipt.get("receiptSha256") != _receipt_sha(receipt)):
        raise ValueError("APPROVED_RECEIPT_REQUIRED")
    if tuple(key) not in receipt["commonIds"]:
        raise ValueError("ID_NOT_IN_APPROVED_RECEIPT")
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
