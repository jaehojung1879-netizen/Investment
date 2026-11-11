"""Append-only research decision ledger (RESEARCH_DECISION_RECORD_V1) and its evaluator.

Records are hash-chained JSON lines. A record is never edited: outcomes are separate
OUTCOME rows that cite a record digest, and they are written only for horizons whose
end session has already closed. Activation outside research/decision_desk_v1/dry-run/
requires Owner approval and is refused here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRY_RUN_DIR = HERE / "dry-run"
SCHEMA = "RESEARCH_DECISION_RECORD_V1"
OUTCOME_SCHEMA = "RESEARCH_DECISION_OUTCOME_V1"
GENESIS = "0" * 64
PATHS = {"B0", "B1", "B2"}
RECORD_STATUSES = {"DRY_RUN_NOT_ACTIVATED", "RECORDED", "LATE_NOT_PROSPECTIVE"}
OUTCOME_STATUSES = {"PENDING", "SCORED", "SOURCE_BLOCKED"}
FORBIDDEN_KEYS = {"probability", "targetprice", "expectedreturn", "confidencepct", "winrate"}
REQUIRED = ["schema", "region", "path", "cohort", "signalAsOf", "informationCutoff", "generatedAt", "publishedAt",
            "modelVersion", "sourceHashes", "selectedTickers", "weights", "benchmark", "investmentThesis",
            "invalidationConditions", "plannedExecution", "plannedExecutionCloseUtc", "costs", "horizon126", "horizon252", "subsequentReturns",
            "status", "missingDataReason", "prevDigest", "digest"]


class LedgerError(ValueError):
    pass


def canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(record: dict) -> str:
    return hashlib.sha256(canonical({k: v for k, v in record.items() if k != "digest"})).hexdigest()


def _forbidden(obj, path="") -> list[str]:
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in FORBIDDEN_KEYS:
                hits.append(f"{path}/{k}")
            hits += _forbidden(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += _forbidden(v, f"{path}/{i}")
    return hits


def validate_record(r: dict) -> None:
    missing = [k for k in REQUIRED if k not in r]
    if missing:
        raise LedgerError(f"MISSING_FIELDS {missing}")
    if r["schema"] != SCHEMA or r["path"] not in PATHS or r["status"] not in RECORD_STATUSES:
        raise LedgerError("BAD_SCHEMA_PATH_OR_STATUS")
    if not (r["informationCutoff"] <= r["generatedAt"] <= r["publishedAt"]):
        raise LedgerError("TIME_ORDER informationCutoff <= generatedAt <= publishedAt violated")
    if r["plannedExecutionCloseUtc"] <= r["publishedAt"] and r["status"] != "LATE_NOT_PROSPECTIVE":
        raise LedgerError("EXECUTION_NOT_AFTER_PUBLICATION")
    w = r["weights"]
    if abs(sum(w.values()) - 1.0) > 1e-9 or any(v < 0 for v in w.values()):
        raise LedgerError("WEIGHTS_MUST_SUM_TO_ONE_LONG_ONLY")
    stocks = [t for t in w if t != r["benchmark"]]
    if sorted(stocks) != sorted(r["selectedTickers"]) or len(stocks) > 5:
        raise LedgerError("SELECTED_TICKERS_DISAGREE_WITH_WEIGHTS_OR_EXCEED_5")
    if r["horizon126"] is not None or r["horizon252"] is not None or r["subsequentReturns"] is not None:
        raise LedgerError("FUTURE_FIELDS_MUST_BE_EMPTY_IN_A_DECISION_RECORD")
    if not r["sourceHashes"]:
        raise LedgerError("SOURCE_HASHES_REQUIRED")
    hits = _forbidden(r)
    if hits:
        raise LedgerError(f"FORBIDDEN_NUMERIC_CLAIM {hits}")
    if digest(r) != r["digest"]:
        raise LedgerError("DIGEST_MISMATCH")


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verify_chain(rows: list[dict]) -> None:
    prev = GENESIS
    seen = set()
    for r in rows:
        if r.get("prevDigest") != prev:
            raise LedgerError(f"CHAIN_BROKEN at {r.get('digest')}")
        if r.get("schema") == SCHEMA:
            validate_record(r)
            key = (r["region"], r["path"], r["cohort"])
            if key in seen:
                raise LedgerError(f"DUPLICATE_RECORD {key}")
            seen.add(key)
        elif r.get("schema") == OUTCOME_SCHEMA:
            validate_outcome(r, rows)
        else:
            raise LedgerError("UNKNOWN_ROW_SCHEMA")
        if digest(r) != r["digest"]:
            raise LedgerError("DIGEST_MISMATCH")
        prev = r["digest"]


def append(path: Path, row: dict, *, owner_approved: bool = False) -> dict:
    """Append one row after verifying the whole existing chain. Never rewrites a line."""
    path = Path(path)
    if not owner_approved and DRY_RUN_DIR.resolve() not in path.resolve().parents:
        raise LedgerError("ACTIVATION_REQUIRES_OWNER_APPROVAL: only dry-run/ is writable")
    rows = read(path)
    verify_chain(rows)
    row = dict(row)
    row["prevDigest"] = rows[-1]["digest"] if rows else GENESIS
    row["digest"] = digest(row)
    verify_chain(rows + [row])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return row


# ----------------------------------------------------------------------------- outcomes
def validate_outcome(o: dict, rows: list[dict]) -> None:
    if o.get("status") not in OUTCOME_STATUSES:
        raise LedgerError("BAD_OUTCOME_STATUS")
    target = [r for r in rows if r.get("digest") == o.get("recordDigest") and r.get("schema") == SCHEMA]
    if not target:
        raise LedgerError("OUTCOME_CITES_UNKNOWN_RECORD")
    if o["status"] == "SCORED":
        if o.get("observedAt", "") <= o.get("horizonEndSession", "9999"):
            raise LedgerError("SCORED_BEFORE_HORIZON_CLOSED")
        if not isinstance(o.get("excessAfterCostPct"), (int, float)):
            raise LedgerError("SCORED_NEEDS_NUMBER")
    elif o.get("excessAfterCostPct") is not None or o.get("returnAfterCostPct") is not None:
        raise LedgerError("UNSCORED_OUTCOME_CARRIES_A_NUMBER")


def evaluate(record: dict, horizon: int, sessions: list[str], total_return, observed_at: str,
             blocked: dict | None = None) -> dict:
    """Build an OUTCOME row for one horizon.

    sessions: the regional session calendar (ISO dates) from plannedExecution onward.
    total_return(ticker, start, end) -> float | None: total-return ratio minus 1, None if unobservable.
    blocked: {ticker: reason} for names with an unverifiable corporate action inside the window.
    """
    start = record["plannedExecution"]
    if start not in sessions:
        raise LedgerError("EXECUTION_SESSION_NOT_IN_CALENDAR")
    i = sessions.index(start)
    base = {"schema": OUTCOME_SCHEMA, "recordDigest": record["digest"], "region": record["region"],
            "path": record["path"], "cohort": record["cohort"], "horizon": horizon, "observedAt": observed_at,
            "returnAfterCostPct": None, "excessAfterCostPct": None, "missingDataReason": None}
    if i + horizon >= len(sessions) or sessions[i + horizon] >= observed_at[:10]:
        return {**base, "status": "PENDING", "horizonEndSession": sessions[i + horizon] if i + horizon < len(sessions) else None}
    end = sessions[i + horizon]
    base["horizonEndSession"] = end
    blocked = blocked or {}
    hit = sorted(t for t in record["weights"] if t in blocked)
    if hit:
        return {**base, "status": "SOURCE_BLOCKED", "missingDataReason": {t: blocked[t] for t in hit}}
    costs = record["costs"]
    gross, missing = 0.0, []
    for t, w in record["weights"].items():
        r = total_return(t, start, end)
        if r is None:
            missing.append(t)
            continue
        leg_cost = costs["benchmarkRoundTripPct"] if t == record["benchmark"] else costs["stockRoundTripPct"]
        gross += w * ((1 + r) * (1 - leg_cost / 100) - 1)
    if missing:
        return {**base, "status": "SOURCE_BLOCKED", "missingDataReason": {t: "PRICE_UNOBSERVABLE" for t in missing}}
    bench = total_return(record["benchmark"], start, end)
    if bench is None:
        return {**base, "status": "SOURCE_BLOCKED", "missingDataReason": {record["benchmark"]: "PRICE_UNOBSERVABLE"}}
    bench_net = (1 + bench) * (1 - costs["benchmarkRoundTripPct"] / 100) - 1
    return {**base, "status": "SCORED", "returnAfterCostPct": round(gross * 100, 6),
            "excessAfterCostPct": round((gross - bench_net) * 100, 6)}
