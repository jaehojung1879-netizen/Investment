"""KR integrated alpha portfolio v1 — the PROSPECTIVE receipt contract (designed and tested here; nothing is written or scheduled by this change).

Historical results of this study are development evidence on outcome-exposed history. The only route to real evidence is a prospective record made
BEFORE the outcome exists: on every future decision date one immutable receipt stores the exact inputs and identities, the industry membership used, the
registered stock and industry feature values, STOCK_SCORE / INDUSTRY_SCORE / COMBINED_SCORE, the eligible names, the selected underlying S and I+S
books, the C0 and C1 states and multipliers, and ALL SIX target portfolios, under the frozen spec hash and the code identity. Receipts are appended to a
JSON Lines ledger and never rewritten; a key that already exists, an out-of-order date, a changed spec or an altered earlier row refuses the whole
append. A receipt contains no outcome and is evaluated only after its horizon has matured on the KR calendar.

Recording all six targets (not only the architecture the sealed development decision names) keeps the prospective record independent of that decision.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from . import kr_integrated_alpha_portfolio as M
from . import kr_market_risk_model as K
from . import replay_calendar as RC

SCHEMA_VERSION = 1
EVIDENCE_CLASS = "PROSPECTIVE_PAPER"
EVALUATION_HORIZONS = (21, 63, 126)
REQUIRED = ("schemaVersion", "studyId", "specSha256", "codeIdentity", "signalDate", "executionDate", "createdAtUtc", "inputIdentities", "industryMembership",
            "stockFeatures", "industryFeatures", "scores", "eligible", "underlying", "market", "targets", "developmentDecision", "evaluationHorizons",
            "evidenceClass")
FORBIDDEN_RECEIPT_KEY_FRAGMENTS = ("forward", "realized", "outcome", "sharpe", "cagr", "label", "nextreturn")
TOLERANCE = 1e-9


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def receipt_digest(receipt):
    body = {k: v for k, v in receipt.items() if k != "receiptSha256"}
    return hashlib.sha256(canonical(body)).hexdigest()


def _scan_for_outcomes(value, path=""):
    if isinstance(value, dict):
        for key, inner in value.items():
            if any(fragment in str(key).lower().replace("_", "") for fragment in FORBIDDEN_RECEIPT_KEY_FRAGMENTS):
                raise ValueError("OUTCOME_FIELD_IN_RECEIPT: " + path + "/" + str(key))
            _scan_for_outcomes(inner, path + "/" + str(key))
    elif isinstance(value, list):
        for inner in value:
            _scan_for_outcomes(inner, path)


def target_portfolios(underlying, multipliers):
    """All six target portfolios from the two underlying books and the two market multipliers. The market only SCALES the book already selected."""
    out = {}
    for arch in M.ARCH_ORDER:
        layer = "I+S" if M.ARCHITECTURES[arch]["industry"] else "S"
        market = M.ARCHITECTURES[arch]["market"]
        multiplier = 1.0 if market is None else multipliers[market]
        weights = {t: w * multiplier for t, w in sorted(underlying[layer]["baseWeights"].items())}
        out[arch] = {"name": M.ARCHITECTURES[arch]["name"], "underlying": layer, "marketCandidate": market, "equityRiskMultiplier": multiplier,
                     "selected": list(underlying[layer]["selected"]), "weights": weights, "cashWeight": 1.0 - math.fsum(weights.values())}
    return out


def build_receipt(*, signal_date, input_identities, industry_membership, stock_features, industry_features, scores, eligible, underlying, market,
                  spec_sha256, code_identity, created_at_utc, development_decision):
    """One receipt. `market` = {'C0': {'states': {...}, 'multiplier': m, 'heldForMissingState': bool}, 'C1': {...}}. The six targets are derived here
    from `underlying` and the multipliers, never accepted from the caller, so the shared-underlying identity cannot be broken by a typo."""
    if not input_identities or any(not isinstance(v, str) or len(v) != 64 for v in input_identities.values()):
        raise ValueError("INPUT_IDENTITY_REQUIRED")
    if sorted(market) != sorted(M.MARKET_CANDIDATES) or any(market[c]["multiplier"] not in K.LEVELS for c in market):
        raise ValueError("MARKET_MULTIPLIER_OUTSIDE_FROZEN_VOCABULARY")
    if sorted(underlying) != ["I+S", "S"]:
        raise ValueError("BOTH_UNDERLYING_BOOKS_REQUIRED")
    day = pd.Timestamp(signal_date)
    calendar = RC.sessions(str(day.date()), str((day + pd.Timedelta(days=20)).date()), "KR")
    if len(calendar) < 2 or calendar[0] != day:
        raise ValueError("SIGNAL_DATE_IS_NOT_A_KR_SESSION")
    multipliers = {c: market[c]["multiplier"] for c in market}
    receipt = {"schemaVersion": SCHEMA_VERSION, "studyId": M.STUDY, "specSha256": spec_sha256, "codeIdentity": dict(code_identity), "signalDate": str(day.date()),
               "executionDate": str(calendar[1].date()), "createdAtUtc": created_at_utc, "inputIdentities": dict(sorted(input_identities.items())),
               "industryMembership": dict(sorted(industry_membership.items())), "stockFeatures": stock_features, "industryFeatures": industry_features,
               "scores": scores, "eligible": {k: sorted(v) for k, v in eligible.items()},
               "underlying": {k: {"selected": list(v["selected"]), "baseWeights": dict(sorted(v["baseWeights"].items()))} for k, v in underlying.items()},
               "market": market, "targets": target_portfolios(underlying, multipliers), "developmentDecision": development_decision,
               "evaluationHorizons": list(EVALUATION_HORIZONS), "evidenceClass": EVIDENCE_CLASS}
    receipt["receiptSha256"] = receipt_digest(receipt)
    validate_receipt(receipt)
    return receipt


def validate_receipt(receipt):
    missing = [k for k in REQUIRED + ("receiptSha256",) if k not in receipt]
    if missing:
        raise ValueError("RECEIPT_FIELD_MISSING: " + ",".join(missing))
    if receipt["receiptSha256"] != receipt_digest(receipt):
        raise ValueError("RECEIPT_DIGEST_MISMATCH")
    if receipt["studyId"] != M.STUDY or receipt["evidenceClass"] != EVIDENCE_CLASS:
        raise ValueError("RECEIPT_IDENTITY_MISMATCH")
    _scan_for_outcomes({k: v for k, v in receipt.items() if k not in ("receiptSha256",)})
    if sorted(receipt["targets"]) != sorted(M.ARCH_ORDER):
        raise ValueError("ALL_SIX_TARGETS_REQUIRED")
    multipliers = {c: receipt["market"][c]["multiplier"] for c in M.MARKET_CANDIDATES}
    if any(m not in K.LEVELS for m in multipliers.values()):
        raise ValueError("RECEIPT_MULTIPLIER_OUTSIDE_FROZEN_VOCABULARY")
    expected = target_portfolios(receipt["underlying"], multipliers)
    for arch, target in receipt["targets"].items():
        if len(target["weights"]) > M.MAX_HOLDINGS or sum(target["weights"].values()) > 1 + TOLERANCE or any(w < 0 for w in target["weights"].values()):
            raise ValueError("TARGET_VIOLATES_THE_PORTFOLIO_CONSTRAINTS: " + arch)
        if target["selected"] != expected[arch]["selected"] or any(abs(target["weights"].get(t, 0) - w) > TOLERANCE for t, w in expected[arch]["weights"].items()) \
                or set(target["weights"]) != set(expected[arch]["weights"]):
            raise ValueError("TARGET_DIFFERS_FROM_UNDERLYING_TIMES_MULTIPLIER: " + arch)
    for layer, archs in (("S", "ABC"), ("I+S", "DEF")):
        if len({tuple(receipt["targets"][a]["selected"]) for a in archs}) != 1:
            raise ValueError("ARCHITECTURES_DO_NOT_SHARE_THE_UNDERLYING_SELECTION: " + layer)
    return True


def read_ledger(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for row in rows:
        validate_receipt(row)
    return rows


def append_receipt(path, receipt):
    """Append-only. Refuses a duplicate (studyId, signalDate), a signal date not after the last one, a spec different from the ledger's, and any existing
    row whose digest no longer verifies. Existing bytes are never rewritten: the new row is appended to the end of the file."""
    validate_receipt(receipt)
    rows = read_ledger(path)
    if any((r["studyId"], r["signalDate"]) == (receipt["studyId"], receipt["signalDate"]) for r in rows):
        raise ValueError("RECEIPT_ALREADY_EXISTS")
    if rows and pd.Timestamp(receipt["signalDate"]) <= pd.Timestamp(rows[-1]["signalDate"]):
        raise ValueError("RECEIPT_OUT_OF_ORDER")
    if rows and receipt["specSha256"] != rows[0]["specSha256"]:
        raise ValueError("RECEIPT_SPEC_CHANGED_WITHIN_A_LEDGER")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        stream.write(canonical(receipt) + b"\n")
    return receipt["receiptSha256"]


def matured(receipt, as_of, horizon):
    """True only once `horizon` KR sessions after the execution session have closed on or before `as_of`. Before that, no outcome may be computed."""
    if horizon not in EVALUATION_HORIZONS:
        raise ValueError("UNREGISTERED_HORIZON")
    start = pd.Timestamp(receipt["executionDate"])
    sessions = RC.sessions(str(start.date()), str(pd.Timestamp(as_of).date()), "KR")
    return len(sessions) - 1 >= horizon
