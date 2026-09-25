"""Normalized KR terminal corporate-action records.

WHAT A RECORD ANSWERS. What a shareholder actually received when a security
stopped trading: cash, successor shares, a tender price, or nothing
established yet. Schema generalized from `data/replay-corporate-actions.json`
's existing `REPLAY_CORPORATE_ACTIONS_V1` ESRX record — the same shape,
extended to the termination types a delisting or a share exchange can take
that a cash-and-stock merger cannot, and to KR.

THE BOOK IS REVIEWED, NEVER INFERRED. `load_book`/`validate_book` apply the
same defensive checks `pipeline/replay_recovery.load_corporate_actions`
already applies to the US book: every action identity is unique, and a
record that STATES a consideration term (a cash amount, a successor, an
exchange ratio) must cite the DART receipt it came from. A record with no
citation stays `TERMINATION_TYPE_UNRESOLVED` — never a fabricated value, and
never inferred from price behaviour, name similarity or ticker similarity.

NO RETURN IS EVER COMPUTED HERE. `chain_successors`/`successor_has_panel`
build only the LINEAGE a future label engine would need — which security a
holding became, and whether that security itself has a price panel — never
a valuation of it. See `docs/kr-terminated-security-total-return-foundation-
v1.md` for why that boundary is enforced at the module level, not by
convention alone.
"""
from __future__ import annotations

CONTRACT = "KR_TERMINAL_CORPORATE_ACTIONS_V1"

MERGER_CASH = "MERGER_CASH"
MERGER_STOCK = "MERGER_STOCK"
MERGER_CASH_AND_STOCK = "MERGER_CASH_AND_STOCK"
SHARE_EXCHANGE = "SHARE_EXCHANGE"
SHARE_TRANSFER = "SHARE_TRANSFER"
TENDER_CASH_OUT = "TENDER_CASH_OUT"
HOLDING_COMPANY_REORGANIZATION = "HOLDING_COMPANY_REORGANIZATION"
INSOLVENCY_DELISTING = "INSOLVENCY_DELISTING"
VOLUNTARY_DELISTING = "VOLUNTARY_DELISTING"
OTHER_TERMINATION = "OTHER_TERMINATION"
TERMINATION_TYPE_UNRESOLVED = "TERMINATION_TYPE_UNRESOLVED"

ACTION_TYPES = frozenset({
    MERGER_CASH, MERGER_STOCK, MERGER_CASH_AND_STOCK, SHARE_EXCHANGE,
    SHARE_TRANSFER, TENDER_CASH_OUT, HOLDING_COMPANY_REORGANIZATION,
    INSOLVENCY_DELISTING, VOLUNTARY_DELISTING, OTHER_TERMINATION,
    TERMINATION_TYPE_UNRESOLVED,
})

# Used only by the completeness matrix (`kr_termination_inventory.py`) to ask
# "does this resolved type still owe a term" — never to fabricate one.
REQUIRES_CASH_TERM = frozenset({MERGER_CASH, MERGER_CASH_AND_STOCK, TENDER_CASH_OUT})
REQUIRES_SUCCESSOR_TERM = frozenset({MERGER_STOCK, MERGER_CASH_AND_STOCK,
                                     SHARE_EXCHANGE, SHARE_TRANSFER,
                                     HOLDING_COMPANY_REORGANIZATION})

REQUIRED_FIELDS = (
    "oldSecurity", "actionType", "effectiveDate",
    "cashPerOldShare", "successorSecurity", "successorSharesPerOldShare",
    "fractionalShareTreatment", "cashInLieuRule", "lastTradingDate",
    "sourceReceiptNumber", "sourceReceiptDate", "evidenceStatus",
)

EVIDENCE_UNRESOLVED = "UNRESOLVED"
EVIDENCE_SEALED = "SEALED_FROM_DART_RECEIPT"

_CONSIDERATION_FIELDS = ("cashPerOldShare", "successorSecurity",
                         "successorSharesPerOldShare")


def build_record(*, old_security: str, action_type: str,
                 effective_date: str | None = None,
                 cash_per_old_share: float | None = None,
                 successor_security: str | None = None,
                 successor_shares_per_old_share: float | None = None,
                 fractional_share_treatment: str | None = None,
                 cash_in_lieu_rule: str | None = None,
                 last_trading_date: str | None = None,
                 source_receipt_number: str | None = None,
                 source_receipt_date: str | None = None,
                 sources: tuple[str, ...] = ()) -> dict:
    """One terminal-action record.

    Refuses a term with no citing receipt outright, rather than storing it
    unvouched: this is the check `replay_recovery.load_corporate_actions`
    already runs on the US book at LOAD time, moved here to CONSTRUCTION
    time so a record can never exist in an unvouched state to begin with.
    """
    if action_type not in ACTION_TYPES:
        raise ValueError(f"unknown actionType: {action_type}")
    has_term = any(v not in (None, "") for v in
                   (cash_per_old_share, successor_security, successor_shares_per_old_share))
    if has_term and not (source_receipt_number and source_receipt_date):
        raise ValueError("a resolved consideration term requires its DART receipt")
    evidence_status = EVIDENCE_SEALED if source_receipt_number else EVIDENCE_UNRESOLVED
    return {
        "oldSecurity": old_security,
        "actionType": action_type,
        "effectiveDate": effective_date,
        "cashPerOldShare": cash_per_old_share,
        "successorSecurity": successor_security,
        "successorSharesPerOldShare": successor_shares_per_old_share,
        "fractionalShareTreatment": fractional_share_treatment,
        "cashInLieuRule": cash_in_lieu_rule,
        "lastTradingDate": last_trading_date,
        "sourceReceiptNumber": source_receipt_number,
        "sourceReceiptDate": source_receipt_date,
        "evidenceStatus": evidence_status,
        "sources": list(sources),
    }


def validate_book(actions: list[dict]) -> None:
    """The same defensive checks `build_record` applies at construction,
    reapplied at load time for a book read back from disk — so a hand-edited
    or externally-produced JSON file cannot smuggle an unvouched term past
    the loader the way `replay_recovery.load_corporate_actions` already
    guards the US book.
    """
    seen = set()
    for row in actions:
        if row.get("actionType") not in ACTION_TYPES:
            raise ValueError(f"unknown actionType: {row.get('actionType')}")
        if not row.get("oldSecurity"):
            raise ValueError("terminal action missing oldSecurity")
        key = (row["oldSecurity"], row.get("effectiveDate"))
        if key in seen:
            raise ValueError(f"duplicate terminal action: {key}")
        seen.add(key)
        has_term = any(row.get(field) not in (None, "") for field in _CONSIDERATION_FIELDS)
        if has_term and not (row.get("sourceReceiptNumber") and row.get("sourceReceiptDate")):
            raise ValueError(f"unvouched consideration term: {key}")


def load_book(path) -> dict:
    import json
    from pathlib import Path

    book = json.loads(Path(path).read_text(encoding="utf-8"))
    if book.get("schema") != CONTRACT:
        raise ValueError(f"not a {CONTRACT} book: {path}")
    validate_book(book.get("actions") or [])
    return book


def chain_successors(actions: list[dict]) -> dict[str, list[str]]:
    """`oldSecurity` -> its full successor chain.

    Follows `successorSecurity` links until one is unset, or a cycle would
    repeat a security already in the chain — reported by stopping there,
    never followed past the repeat. Computes no return; see module
    docstring.
    """
    by_old = {row["oldSecurity"]: row for row in actions}
    chains: dict[str, list[str]] = {}
    for start in by_old:
        chain = [start]
        current = start
        while True:
            row = by_old.get(current)
            successor = row.get("successorSecurity") if row else None
            if not successor or successor in chain:
                break
            chain.append(successor)
            current = successor
        chains[start] = chain
    return chains


def successor_has_panel(chains: dict[str, list[str]], priced: set[str]) -> dict[str, dict]:
    """For each chain: whether its terminal link has a price panel, and
    whether that terminus itself has a further action pending (appears as an
    `oldSecurity` too) — reported, never resolved, which is what makes a
    chained corporate action structurally supported without this module
    ever computing what it is worth.
    """
    by_old = set(chains)
    out = {}
    for start, chain in chains.items():
        terminus = chain[-1]
        out[start] = {
            "chain": chain,
            "terminusHasPricePanel": terminus in priced,
            "terminusHasItsOwnFurtherAction": terminus in by_old and terminus != start,
        }
    return out
