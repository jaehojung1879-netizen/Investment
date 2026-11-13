"""Append-only research decision ledger (RESEARCH_DECISION_RECORD_V1) and its evaluator.

Records are hash-chained JSON lines. A record is never edited: outcomes are separate
OUTCOME rows that cite a record digest, and they are written only for horizons whose
end session has already closed. Activation outside research/decision_desk_v1/dry-run/
requires Owner approval and is refused here.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRY_RUN_DIR = HERE / "dry-run"
SCHEMA = "RESEARCH_DECISION_RECORD_V1"
SCHEMA_V2 = "RESEARCH_DECISION_RECORD_V2"
OUTCOME_SCHEMA = "RESEARCH_DECISION_OUTCOME_V1"
ANNOTATION_SCHEMA = "RESEARCH_DECISION_ANNOTATION_V1"
RECORD_SCHEMAS = {SCHEMA, SCHEMA_V2}
ANNOTATION_CATEGORIES = {"PIT_CONTAMINATED", "PUBLICATION_VERIFIED", "PUBLICATION_LATE", "INDEPENDENCE_NOT_VERIFIED",
                         "B2_NO_REVIEW", "NOTE", "PUBLICATION_NOT_OBSERVED"}
# A record carrying any of these is scored but never enters the primary comparison.
PRIMARY_EXCLUDING = {"PIT_CONTAMINATED", "PUBLICATION_LATE", "PUBLICATION_NOT_OBSERVED"}

# Release gates found by the independent preflight (#335). The writer outside dry-run/ stays refused
# while any gate that blocks the target is OPEN. Each RESOLVED gate names the test that proves it.
ACTIVATION_GATES = [
    {"id": "G1_MACRO_VINTAGE", "blocks": ["DESK_V2_B2"], "status": "OPEN",
     "detail": "FRED values are read at the current vintage. An observation revised after the cutoff is dropped when revision "
               "metadata is supplied (availability.available_fred), but the FRED CSV carries none, so a silent revision cannot be "
               "detected. Prospective-v1 arms read no macro series.",
     "test": "test_review_gaps.py::test_revised_observation_is_dropped_not_substituted"},
    {"id": "G2_FUNDAMENTAL_PUBLICATION", "blocks": ["DESK_V2_B2"], "status": "OPEN",
     "detail": "Production receipts carry no per-field publication time. A stated time after the cutoff now fails gate G6_PUBLICATION; "
               "an absent one is flagged, not trusted. Prospective-v1 arms read dated PIT filings (availableFrom strictly before the decision date).",
     "test": "test_review_gaps.py::test_fundamental_published_after_cutoff_fails_gates"},
    {"id": "G3_SAME_DAY_CUTOFF", "blocks": [], "status": "RESOLVED", "test": "test_review_gaps.py::test_same_day_iso_cutoff_is_published"},
    {"id": "G4_PROSE_NUMBERS", "blocks": [], "status": "RESOLVED", "test": "test_review_gaps.py::test_unsourced_number_in_prose_is_refused"},
    {"id": "G5_SOURCE_BLOCKED_RETRY", "blocks": [], "status": "RESOLVED", "test": "test_review_gaps.py::test_source_blocked_is_superseded_append_only"},
    {"id": "G6_NON_POSITIVE_PRICE", "blocks": [], "status": "RESOLVED", "test": "test_review_gaps.py::test_zero_or_negative_price_blocks"},
    {"id": "G7_PRIMARY_EXCLUSION", "blocks": [], "status": "RESOLVED", "test": "test_review_gaps.py::test_primary_comparison_excludes_contaminated_and_unobserved"},
    {"id": "G8_PUBLICATION_OBSERVED", "blocks": [], "status": "RESOLVED",
     "detail": "PUBLICATION_VERIFIED needs the public commit to be OBSERVED before the deadline; a later check can only record PUBLICATION_NOT_OBSERVED. "
               "An operator must therefore run verify-publication before each deadline.",
     "test": "test_review_gaps.py::test_publication_checked_after_deadline_is_not_verified"},
    {"id": "G9_FUTURE_SPLIT", "blocks": [], "status": "RESOLVED", "test": "test_review_gaps.py::test_future_split_is_undone_at_the_cutoff"},
    {"id": "G10_MISSED_DEADLINE", "blocks": [], "status": "RESOLVED",
     "detail": "Clarified: the registration deadline applies to every path. A cohort decided after it records nothing (REGISTRATION_CLOSED); no path is back-filled.",
     "test": "test_review_gaps.py::test_missed_deadline_records_no_path"},
    {"id": "G11_CONCURRENT_APPEND", "blocks": [], "status": "RESOLVED", "test": "test_review_gaps.py::test_concurrent_appends_keep_one_chain"},
    {"id": "G12_DOUBLE_COST", "blocks": [], "status": "RESOLVED", "test": "test_review_gaps.py::test_evaluate_writes_base_and_double_cost"},
    {"id": "G13_REVIEW_BEFORE_SEAL", "blocks": [], "status": "RESOLVED", "test": "test_review_gaps.py::test_decide_refuses_review_before_packet_seal"},
    {"id": "CI_GREEN", "blocks": ["ALL"], "status": "OPEN",
     "detail": "Every PR's Tests job fails on the shared threadpoolctl 3.8.0 pin until #321 merges."},
]


def open_gates(target: str) -> list[dict]:
    return [g for g in ACTIVATION_GATES if g["status"] != "RESOLVED" and ("ALL" in g["blocks"] or target in g["blocks"])]
PATHS_V2 = {"B0", "B1", "B2", "BX"}
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
    if r.get("schema") == SCHEMA_V2:
        return validate_record_v2(r)
    _validate_common(r)


def _validate_common(r: dict, check_digest: bool = True) -> None:
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
    if check_digest and digest(r) != r["digest"]:
        raise LedgerError("DIGEST_MISMATCH")


def validate_record_v2(r: dict) -> None:
    """V2 = V1 fields + reviewer, protocolVersion and a registration deadline fixed by the packet."""
    for k in ("reviewer", "protocolVersion", "registrationDeadlineUtc", "packetSha256"):
        if k not in r:
            raise LedgerError(f"MISSING_FIELDS ['{k}']")
    if r["path"] not in PATHS_V2:
        raise LedgerError("BAD_SCHEMA_PATH_OR_STATUS")
    if r["path"] in ("B2", "BX") and not r["reviewer"]:
        raise LedgerError("AI_PATH_NEEDS_A_REVIEWER")
    if r["path"] in ("B0", "B1") and r["reviewer"] is not None:
        raise LedgerError("RULE_PATH_HAS_NO_REVIEWER")
    if r["publishedAt"] > r["registrationDeadlineUtc"]:
        raise LedgerError("REGISTRATION_CLOSED: published after the cohort's registration deadline")
    if r["plannedExecutionCloseUtc"] <= r["registrationDeadlineUtc"]:
        raise LedgerError("EXECUTION_NOT_AFTER_DEADLINE")
    v1 = dict(r)
    v1["schema"] = SCHEMA
    v1["path"] = "B2" if r["path"] == "BX" else r["path"]
    _validate_common(v1, check_digest=False)
    if digest(r) != r["digest"]:
        raise LedgerError("DIGEST_MISMATCH")


def record_key(r: dict) -> tuple:
    """One record per (region, path, reviewer, cohort); a V1 B2 record is the 'claude' reviewer's."""
    reviewer = r.get("reviewer") if r["schema"] == SCHEMA_V2 else ("claude" if r["path"] == "B2" else None)
    return (r["region"], r["path"], reviewer, r["cohort"])


def validate_annotation(a: dict, rows: list[dict]) -> None:
    if a.get("category") not in ANNOTATION_CATEGORIES:
        raise LedgerError("BAD_ANNOTATION_CATEGORY")
    if not a.get("recordDigests") or not a.get("detail") or not a.get("createdAt"):
        raise LedgerError("ANNOTATION_INCOMPLETE")
    known = {r["digest"] for r in rows if r.get("schema") in RECORD_SCHEMAS}
    if not set(a["recordDigests"]) <= known:
        raise LedgerError("ANNOTATION_CITES_UNKNOWN_RECORD")
    if {"weights", "selectedTickers", "excessAfterCostPct", "returnAfterCostPct"} & set(a):
        raise LedgerError("ANNOTATION_CANNOT_CHANGE_A_DECISION_OR_OUTCOME")


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
        if r.get("schema") in RECORD_SCHEMAS:
            validate_record(r)
            key = record_key(r)
            if key in seen:
                raise LedgerError(f"DUPLICATE_RECORD {key}")
            seen.add(key)
        elif r.get("schema") == OUTCOME_SCHEMA:
            validate_outcome(r, rows)
        elif r.get("schema") == ANNOTATION_SCHEMA:
            validate_annotation(r, rows)
        else:
            raise LedgerError("UNKNOWN_ROW_SCHEMA")
        if digest(r) != r["digest"]:
            raise LedgerError("DIGEST_MISMATCH")
        prev = r["digest"]


@contextmanager
def _exclusive(path: Path):
    """One writer at a time: an OS lock on a sibling lock file, held across read-verify-append."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def append(path: Path, row: dict, *, owner_approved: bool = False, expected_tip: str | None = None) -> dict:
    """Append one row after verifying the whole existing chain. Never rewrites a line.

    The read, the chain check and the write happen under one exclusive lock, so two writers cannot both
    chain onto the same tip. expected_tip (compare-and-swap) refuses if the ledger moved since the caller read it."""
    path = Path(path)
    if not owner_approved and DRY_RUN_DIR.resolve() not in path.resolve().parents:
        raise LedgerError("ACTIVATION_REQUIRES_OWNER_APPROVAL: only dry-run/ is writable")
    target = "DESK_V2_B2" if row.get("path") in ("B2", "BX") else "DESK_WRITER"
    if owner_approved and open_gates(target):
        raise LedgerError("ACTIVATION_GATES_OPEN " + ", ".join(g["id"] for g in open_gates(target)))
    with _exclusive(path):
        rows = read(path)
        verify_chain(rows)
        tip = rows[-1]["digest"] if rows else GENESIS
        if expected_tip is not None and expected_tip != tip:
            raise LedgerError(f"STALE_TIP expected {expected_tip[:12]} found {tip[:12]}")
        row = dict(row)
        row["prevDigest"] = tip
        row["digest"] = digest(row)
        verify_chain(rows + [row])
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            fh.flush()
    return row


# ----------------------------------------------------------------------------- outcomes
def validate_outcome(o: dict, rows: list[dict]) -> None:
    if o.get("status") not in OUTCOME_STATUSES:
        raise LedgerError("BAD_OUTCOME_STATUS")
    target = [r for r in rows if r.get("digest") == o.get("recordDigest") and r.get("schema") in RECORD_SCHEMAS]
    if not target:
        raise LedgerError("OUTCOME_CITES_UNKNOWN_RECORD")
    key = (o.get("recordDigest"), o.get("horizon"), o.get("costMultiplier", 1.0))
    i = next((k for k, r in enumerate(rows) if r is o), len(rows))
    prior = [r for r in rows[:i] if r.get("schema") == OUTCOME_SCHEMA and r.get("status") != "PENDING"
             and (r["recordDigest"], r["horizon"], r.get("costMultiplier", 1.0)) == key]
    if prior:
        if prior[-1]["status"] == "SCORED":
            raise LedgerError("OUTCOME_ALREADY_SCORED")
        if o.get("supersedes") != prior[-1].get("digest"):
            raise LedgerError("RETRY_MUST_SUPERSEDE_THE_LAST_SOURCE_BLOCKED_ROW")
    if o["status"] == "SCORED":
        if "primaryComparisonEligible" in o:
            excluded = {d for a in rows[:i] if a.get("schema") == ANNOTATION_SCHEMA and a.get("category") in PRIMARY_EXCLUDING
                        for d in a["recordDigests"]}
            if o["primaryComparisonEligible"] and o["recordDigest"] in excluded:
                raise LedgerError("EXCLUDED_RECORD_MARKED_PRIMARY")
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
        if r is None or not math.isfinite(r) or r <= -1:
            missing.append(t)
            continue
        leg_cost = costs["benchmarkRoundTripPct"] if t == record["benchmark"] else costs["stockRoundTripPct"]
        gross += w * ((1 + r) * (1 - leg_cost / 100) - 1)
    if missing:
        return {**base, "status": "SOURCE_BLOCKED", "missingDataReason": {t: "PRICE_UNOBSERVABLE" for t in missing}}
    bench = total_return(record["benchmark"], start, end)
    if bench is None or not math.isfinite(bench) or bench <= -1:
        return {**base, "status": "SOURCE_BLOCKED", "missingDataReason": {record["benchmark"]: "PRICE_UNOBSERVABLE"}}
    bench_net = (1 + bench) * (1 - costs["benchmarkRoundTripPct"] / 100) - 1
    return {**base, "status": "SCORED", "returnAfterCostPct": round(gross * 100, 6),
            "excessAfterCostPct": round((gross - bench_net) * 100, 6)}


# ----------------------------------------------------------------------------- primary comparison
def publication_observed(rows: list[dict]) -> set[str]:
    """Record digests whose public commit was OBSERVED before their own deadline.

    A PUBLICATION_VERIFIED annotation written after the deadline rests on committer time alone, which the
    committer controls; it does not count (#335 G8). Derived from the existing rows, so no record is edited."""
    recs = {r["digest"]: r for r in rows if r.get("schema") in RECORD_SCHEMAS}
    ok = set()
    for a in rows:
        if a.get("schema") == ANNOTATION_SCHEMA and a.get("category") == "PUBLICATION_VERIFIED":
            for d in a["recordDigests"]:
                r = recs.get(d)
                deadline = r and (r.get("registrationDeadlineUtc") or r.get("plannedExecutionCloseUtc"))
                if r and a["createdAt"] <= deadline:
                    ok.add(d)
    return ok


def primary_exclusions(rows: list[dict]) -> dict[str, list[str]]:
    """digest -> reasons a record is outside the primary comparison (empty list = eligible)."""
    observed = publication_observed(rows)
    out = {}
    for r in rows:
        if r.get("schema") not in RECORD_SCHEMAS:
            continue
        why = sorted({a["category"] for a in rows if a.get("schema") == ANNOTATION_SCHEMA
                      and a.get("category") in PRIMARY_EXCLUDING and r["digest"] in a["recordDigests"]})
        if r["digest"] not in observed:
            why.append("PUBLICATION_NOT_OBSERVED_BEFORE_DEADLINE")
        out[r["digest"]] = why
    return out


def primary_comparison(rows: list[dict]) -> list[dict]:
    """The latest SCORED outcome per (record, horizon, cost multiple) for records with no exclusion."""
    excl = primary_exclusions(rows)
    latest = {}
    for o in rows:
        if o.get("schema") == OUTCOME_SCHEMA and o["status"] != "PENDING":
            latest[(o["recordDigest"], o["horizon"], o.get("costMultiplier", 1.0))] = o
    return [o for o in latest.values() if o["status"] == "SCORED" and not excl.get(o["recordDigest"], ["UNKNOWN_RECORD"])]
