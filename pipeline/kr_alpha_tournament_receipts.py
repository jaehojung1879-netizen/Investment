"""KR alpha discovery tournament v1 — immutable prospective prediction receipts (designed, not running).

All Korean history through the development cutoff is development evidence. Confirmation can only come from receipts written BEFORE their outcomes
exist: one receipt per future decision date, carrying everything the frozen process decided and the identities it decided from, sealed by a SHA-256 of
its canonical content and appended to an append-only JSON Lines ledger. Nothing here schedules, writes or evaluates a receipt in this change.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

RECEIPT_FIELDS = (
    "studyId", "receiptVersion", "asOfTimestampUtc", "decisionDate", "codeSha", "specSha256", "dataSnapshotIdentity", "trainingCutoff",
    "candidateRegistryDigest", "selectedModels", "ensembleWeights", "predictions", "passiveWeight", "activePortfolio", "costsAssumed",
    "evidenceClass", "receiptSha256")
PREDICTION_FIELDS = ("ticker", "eligible", "memberScores", "rank", "expectedIncrementalReturn", "uncertaintyVariance", "contraction",
                     "shrunkExpectedIncrementalReturn")
RULES = (
    "one receipt per future decision date, appended before the execution-session close; no future outcome exists at creation",
    "every eligible security carries its member scores, rank, calibrated expected incremental return, uncertainty and shrunk forecast",
    "the active portfolio and the passive weight are derived from the frozen allocator, never typed in by hand",
    "receiptSha256 is the SHA-256 of the canonical JSON of every other field; a reader recomputes it",
    "append-only JSON Lines; a duplicate decision date, an out-of-order date, a changed spec or an altered earlier row refuses the append",
    "a receipt is evaluated only after its H126 horizon has matured; no receipt is rewritten",
    "historical development results and prospective receipts are separate evidence classes and are never pooled",
)
RECEIPT_VERSION = "kr-alpha-discovery-tournament-v1-receipt-1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def seal(receipt):
    body = {k: v for k, v in receipt.items() if k != "receiptSha256"}
    return hashlib.sha256(canonical(body)).hexdigest()


def build_receipt(*, as_of_utc, decision_date, code_sha, spec_sha, data_identity, training_cutoff, registry_digest, selected, ensemble_weights,
                  predictions, active_portfolio, costs, study="kr-alpha-discovery-tournament-v1"):
    """Build and seal one receipt. `predictions` is a list of dicts with PREDICTION_FIELDS; `active_portfolio` {ticker: weight}. The passive weight
    is derived (1 - sum active), never accepted from the caller."""
    for p in predictions:
        missing = [f for f in PREDICTION_FIELDS if f not in p]
        if missing:
            raise ValueError("RECEIPT_PREDICTION_FIELD_MISSING: " + ",".join(missing))
    if any(w < 0 for w in active_portfolio.values()) or sum(active_portfolio.values()) > 1 + 1e-12:
        raise ValueError("RECEIPT_PORTFOLIO_VIOLATES_LONG_ONLY_UNLEVERED")
    if not str(decision_date) <= str(as_of_utc)[:10]:
        raise ValueError("RECEIPT_WRITTEN_BEFORE_ITS_DECISION_DATE")
    receipt = {"studyId": study, "receiptVersion": RECEIPT_VERSION, "asOfTimestampUtc": as_of_utc, "decisionDate": decision_date,
               "codeSha": code_sha, "specSha256": spec_sha, "dataSnapshotIdentity": data_identity, "trainingCutoff": training_cutoff,
               "candidateRegistryDigest": registry_digest, "selectedModels": list(selected), "ensembleWeights": dict(ensemble_weights),
               "predictions": sorted(predictions, key=lambda p: p["ticker"]), "passiveWeight": 1.0 - sum(active_portfolio.values()),
               "activePortfolio": dict(sorted(active_portfolio.items())), "costsAssumed": costs, "evidenceClass": "PROSPECTIVE_PAPER"}
    if not training_cutoff < decision_date:
        raise ValueError("TRAINING_CUTOFF_NOT_BEFORE_DECISION_DATE")
    receipt["receiptSha256"] = seal(receipt)
    return receipt


def verify_receipt(receipt):
    if set(receipt) != set(RECEIPT_FIELDS) or seal(receipt) != receipt["receiptSha256"]:
        raise ValueError("RECEIPT_ALTERED_OR_MALFORMED")
    return True


def append(ledger_path, receipt):
    """Append one sealed receipt; refuse a duplicate or out-of-order date, a spec change, or any altered earlier row."""
    verify_receipt(receipt)
    path = Path(ledger_path)
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    for row in rows:
        verify_receipt(row)
    if rows:
        if receipt["decisionDate"] <= rows[-1]["decisionDate"]:
            raise ValueError("RECEIPT_DATE_NOT_STRICTLY_AFTER_THE_LAST")
        if receipt["specSha256"] != rows[0]["specSha256"]:
            raise ValueError("RECEIPT_SPEC_CHANGED")
    with path.open("ab") as stream:
        stream.write(canonical(receipt) + b"\n")
    return len(rows) + 1
