"""Retrieve real DART `document.xml` filing bodies for the disclosures
`kr_corporate_action_events.plausibly_responsible_disclosures` narrows each
of the 22 terminated securities' 451-row disclosure index down to.

WHY THIS IS A SEPARATE COLLECTOR, NOT A THIRD `alotMatter`-STYLE PASS.
`document.xml` is not a structured JSON endpoint -- it serves a ZIP of the
filing's own raw XML/HTML documents (`scripts/probe_kr_corporate_actions
.probe_document_retrieval` already established this live). What this
script stores is therefore RAW EVIDENCE (the filing's own text, exactly as
DART served it), never a structured field: no `terminationType`, no
`cashPerOldShare`, no `successorSecurity` is assigned here. A later,
separate parsing pass reads what THIS script retrieves and decides what, if
anything, can be responsibly extracted -- see `kr_terminal_action_document
_parser.py`, which this collector never imports and which has not been run
on any real document yet.

WHAT IS STORED, AND WHY NOT THE RAW ZIP BYTES. Committing 130+ ZIP archives
verbatim risks exactly the "huge redundant filing body" this repair line's
own design doc warns against. Each ZIP member's TEXT is decoded (UTF-8,
falling back to EUC-KR/CP949 -- both real, still-common encodings for older
Korean regulatory filings) and stored alongside a SHA-256 of the original
ZIP bytes, so the stored text is independently verifiable against a fresh
fetch without the repository carrying the binary itself. No HTML/XML markup
is stripped: a future parser may need table structure, and stripping it now
would be an interpretation this script is not the place to make.

NARROWING NEVER WIDENS. Only disclosures `plausibly_responsible_
disclosures` already selected are ever fetched here -- this script builds
that same narrowed list itself (reading the real disclosure-index shard and
each security's real `lastTradingDate`), rather than accepting a receipt
list from elsewhere, so a caller cannot accidentally point it at the full
451-row index.

SAME DISCIPLINE AS EVERY OTHER COLLECTOR IN THIS REPAIR LINE: a hard call
budget checked before every fetch, resumable per-receipt state, fails
closed on a refusal with zero progress.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import collector_outcomes as CO  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402
from pipeline import kr_corporate_action_events as KCA  # noqa: E402

BASE = "https://opendart.fss.or.kr/api"
PACE_SECONDS = 0.3
STATE_CONTRACT = "KR_TERMINAL_ACTION_DOCUMENT_FETCH_STATE_V1"
RAW_CONTRACT = "KR_TERMINAL_ACTION_DOCUMENT_TEXT_V1"

# 130 real narrowed receipts were measured across the 22 securities on the
# 2026-09-25 disclosure index (see docs/kr-terminal-action-reconstruction-
# v2.md) -- a conservative budget above that count, not a guaranteed one:
# the disclosure index grows over time and a later run may narrow to more.
DEFAULT_MAX_CALLS = 200
DEFAULT_MAX_MINUTES = 30


class Refused(RuntimeError):
    pass


class CallBudgetExhausted(RuntimeError):
    """Raised BEFORE the call that would exceed `--max-calls`, never after."""


def call_document_xml(key: str, receipt_no: str, timeout: int = 30) -> tuple[bytes, str]:
    url = f"{BASE}/document.xml?crtfc_key={key}&rcept_no={receipt_no}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raise Refused(f"HTTP {exc.code}") from exc
    except Exception as exc:  # pragma: no cover - network dependent
        raise Refused(f"{type(exc).__name__}: {exc}") from exc
    return raw, content_type


def decode_member(raw: bytes) -> tuple[str, str]:
    """(text, encodingUsed) -- UTF-8 first, then EUC-KR/CP949, both real
    encodings DART's own filings still use depending on filer and era.
    Never silently drops bytes: a member neither encoding can decode is
    returned with `encodingUsed="UNDECODABLE"` and empty text, so a caller
    knows to fall back to the raw bytes rather than trusting empty text as
    "no content"."""
    for encoding in ("utf-8", "cp949"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return "", "UNDECODABLE"


def extract_zip_members(raw: bytes) -> list[dict]:
    """Every member of a `document.xml` ZIP response, decoded to text.
    Raises `Refused` if `raw` is not a ZIP at all (DART sometimes answers a
    bad receipt number with a JSON refusal body instead) -- never silently
    stored as an empty document list."""
    if raw[:2] != b"PK":
        raise Refused(f"document.xml did not return a ZIP ({len(raw)} bytes)")
    members = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            member_bytes = zf.read(info.filename)
            text, encoding = decode_member(member_bytes)
            members.append({
                "filename": info.filename, "bytes": info.file_size,
                "sha256": hashlib.sha256(member_bytes).hexdigest(),
                "encodingUsed": encoding, "text": text,
            })
    return members


def load_disclosures(store: Path) -> list[dict]:
    path = store / "kr-corporate-actions-disclosures.jsonl.gz"
    if not path.exists():
        return []
    return HS.read_jsonl(path)


def load_state(store: Path) -> dict:
    path = store / "document-fetch-state.json"
    if not path.exists():
        return {"contract": STATE_CONTRACT, "rawContract": RAW_CONTRACT, "receipts": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raw = {}
    if raw.get("contract") != STATE_CONTRACT or raw.get("rawContract") != RAW_CONTRACT:
        return {"contract": STATE_CONTRACT, "rawContract": RAW_CONTRACT, "receipts": {}}
    raw.setdefault("receipts", {})
    return raw


def save_state(store: Path, state: dict) -> None:
    (store / "document-fetch-state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def narrowed_receipts(store: Path, inventory_path: Path) -> list[tuple[str, str]]:
    """(ticker, receiptNo) pairs -- built HERE from the real disclosure
    index and each security's real `lastTradingDate`, never accepted from
    a caller, so this collector can never be pointed at an unnarrowed set.
    """
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    last_trading_by_ticker = {row["code"]: row.get("lastTradingDate")
                              for row in inventory["securities"]}
    disclosures = load_disclosures(store)
    by_ticker: dict[str, list[dict]] = {}
    for row in disclosures:
        by_ticker.setdefault(row["ticker"], []).append(row)

    out = []
    for ticker in sorted(last_trading_by_ticker):
        narrowed = KCA.plausibly_responsible_disclosures(
            by_ticker.get(ticker, []), last_trading_date=last_trading_by_ticker[ticker])
        for row in narrowed:
            out.append((ticker, row["receiptNo"]))
    return out


def run(store: Path, *, key: str, inventory_path: Path, max_calls: int, max_minutes: int,
       call_fn=call_document_xml) -> dict:
    store.mkdir(parents=True, exist_ok=True)
    targets = narrowed_receipts(store, inventory_path)

    state = load_state(store)
    receipt_states = state["receipts"]
    existing_path = store / "kr-terminal-action-documents.jsonl.gz"
    existing = HS.read_jsonl(existing_path) if existing_path.exists() else []

    deadline = time.monotonic() + max_minutes * 60
    call_counter = {"n": 0}
    written = 0
    stop_reason = "WORK_LIST_EXHAUSTED"
    new_rows: list[dict] = []

    try:
        for ticker, receipt_no in targets:
            if time.monotonic() >= deadline:
                stop_reason = "TIME_BUDGET_SPENT"
                break
            if receipt_states.get(receipt_no, {}).get("status") == "SUCCESS":
                continue
            if call_counter["n"] >= max_calls:
                stop_reason = "CALL_BUDGET_SPENT"
                break
            call_counter["n"] += 1
            try:
                raw, content_type = call_fn(key, receipt_no)
                members = extract_zip_members(raw)
            except Refused as exc:
                receipt_states[receipt_no] = {
                    "status": "FETCH_FAILED", "ticker": ticker, "error": str(exc),
                    "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
                continue
            new_rows.append({
                "id": f"dart-document:{receipt_no}", "ticker": ticker, "receiptNo": receipt_no,
                "zipSha256": hashlib.sha256(raw).hexdigest(), "contentType": content_type,
                "members": members, "retrievedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            written += 1
            receipt_states[receipt_no] = {"status": "SUCCESS", "ticker": ticker,
                                          "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
            time.sleep(PACE_SECONDS)
    except Refused as exc:
        stop_reason = f"REFUSED: {exc}"

    calls = call_counter["n"]
    merged = {row["id"]: row for row in [*existing, *new_rows]}
    changed = HS.write_shard(existing_path, list(merged.values()))
    save_state(store, state)

    receipts_requested = len(targets)
    receipts_succeeded = sum(r.get("status") == "SUCCESS" for r in receipt_states.values())
    receipts_failed = sum(r.get("status") == "FETCH_FAILED" for r in receipt_states.values())
    receipts_remaining = receipts_requested - receipts_succeeded - receipts_failed
    full_work_list_exhausted = stop_reason == "WORK_LIST_EXHAUSTED"
    dataset_complete = full_work_list_exhausted and receipts_remaining == 0

    outcome = CO.run_outcome(stop_reason=stop_reason, calls=calls, written=written)
    return {
        "contract": RAW_CONTRACT, "stopReason": stop_reason, "outcome": outcome,
        "calls": calls, "callBudget": max_calls, "written": written, "shardChanged": changed,
        "totalDocuments": len(merged),
        "receiptsRequested": receipts_requested,
        "receiptsSucceeded": receipts_succeeded,
        "receiptsFailed": receipts_failed,
        "receiptsRemaining": receipts_remaining,
        "fullWorkListExhausted": full_work_list_exhausted,
        "datasetComplete": dataset_complete,
        "operatorMessage": (
            "All narrowed receipts reached a terminal state (retrieved or "
            "fetch-failed)." if dataset_complete else
            f"INCOMPLETE: {receipts_remaining} of {receipts_requested} receipt(s) not yet "
            f"attempted this run (stopped: {stop_reason}). Resumable -- re-run this "
            "workflow with the same --inventory to continue."),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir")
    parser.add_argument(
        "--inventory", type=Path,
        default=ROOT / "docs/results/kr-termination-inventory.json")
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    parser.add_argument("--max-minutes", type=int, default=DEFAULT_MAX_MINUTES)
    args = parser.parse_args(argv)

    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        print("ERROR: DART_API_KEY not in the environment.")
        return 1

    try:
        report = run(Path(args.store_dir), key=key, inventory_path=args.inventory,
                    max_calls=args.max_calls, max_minutes=args.max_minutes)
    except Refused as exc:
        print(f"REFUSED before any progress: {exc}")
        report = {"outcome": CO.classify_refusal(str(exc)), "calls": 0, "written": 0,
                  "datasetComplete": False,
                  "operatorMessage": "No progress was made this run; re-run once the "
                                     "refusal's cause is resolved."}

    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    print(f"\n{report.get('operatorMessage', '')}")
    if CO.is_reportable_failure(report["outcome"], written=report["written"]):
        print(f"\nFAIL: {report['outcome']} with zero rows written this run.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
