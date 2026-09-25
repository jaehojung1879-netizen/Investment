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

EXTENDED (v2, `kr-terminal-action-reconstruction-v2`), NEVER REPLACED. The
contract tag stays `KR_TERMINAL_CORPORATE_ACTIONS_V1` — every field this v1
docstring above describes still means exactly what it always meant, and
every v1 fixture/test still passes unmodified. Four things were added
because a single cash figure and a single successor cannot represent every
real KR termination:

  `considerationComponents` -- a GENERALIZED list, for the cases a single
  `cashPerOldShare`/`successorSecurity` pair cannot represent: more than one
  successor security, a mixed cash-and-stock deal with more than one stock
  leg, or a per-component receipt that differs from the record's primary
  one. The singular fields stay populated with the PRIMARY (first CASH,
  first SUCCESSOR_SHARES) component for the common one-cash-or-one-successor
  case, so nothing that already reads them breaks; a reader that needs the
  full breakdown reads this list instead. Each component cites its own
  receipt, checked by the same construction-time rule as the singular
  fields.

  `amendmentHistory` -- the ORIGINAL filing plus every amendment that
  changed a term, preserved as first-class data (never flattened to "latest
  wins", per this repository's amendment-lineage invariant). Each entry
  cites its own receipt/date/report name and which fields it changed;
  `finalTermsReceiptNumber` says which entry's terms are the ones this
  record's own singular/component fields carry.

  `oldIssuerCorpCode` / `successorIssuerCorpCode` -- the DART issuer
  identity (never a name-similarity guess) behind `oldSecurity` /
  `successorSecurity`, resolved the same way every other identity in this
  repair line is: `kr_corporate_action_events.resolve_historical_dart_
  identity`, never re-implemented here.

  `unresolvedFields` -- an explicit list of which of this record's OWN
  fields remain unresolved and why, so a `TERMINATION_TYPE_UNRESOLVED` or a
  partially-resolved record never reads as silently complete.
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

# `considerationComponents[i]["type"]` -- generalizes beyond one cash amount
# and one successor. A component with a value MUST cite its own receipt,
# exactly the rule `build_record`/`validate_book` already apply to the
# singular fields.
COMPONENT_CASH = "CASH"
COMPONENT_SUCCESSOR_SHARES = "SUCCESSOR_SHARES"
COMPONENT_TYPES = frozenset({COMPONENT_CASH, COMPONENT_SUCCESSOR_SHARES})


def build_consideration_component(*, component_type: str,
                                   cash_amount: float | None = None,
                                   successor_security: str | None = None,
                                   successor_issuer_corp_code: str | None = None,
                                   shares_per_old_share: float | None = None,
                                   source_receipt_number: str | None = None,
                                   source_receipt_date: str | None = None) -> dict:
    """One leg of a (possibly multi-leg) consideration -- e.g. one of two
    successor securities in a split-merger, or a cash leg alongside a stock
    leg. Refuses a stated value with no citing receipt, the same rule
    `build_record` applies to its own singular fields."""
    if component_type not in COMPONENT_TYPES:
        raise ValueError(f"unknown consideration component type: {component_type}")
    has_value = any(v not in (None, "") for v in
                    (cash_amount, successor_security, shares_per_old_share))
    if has_value and not (source_receipt_number and source_receipt_date):
        raise ValueError("a resolved consideration component requires its DART receipt")
    return {
        "type": component_type,
        "cashAmount": cash_amount,
        "successorSecurity": successor_security,
        "successorIssuerCorpCode": successor_issuer_corp_code,
        "sharesPerOldShare": shares_per_old_share,
        "sourceReceiptNumber": source_receipt_number,
        "sourceReceiptDate": source_receipt_date,
    }


def build_amendment_entry(*, receipt_number: str, receipt_date: str,
                          report_name: str | None = None,
                          fields_changed: tuple[str, ...] = (),
                          supersedes_receipt_number: str | None = None) -> dict:
    """One entry in a record's `amendmentHistory` -- the original filing or
    one amendment to it, kept as first-class data rather than collapsed to
    "latest wins". `receiptDate` is this ENTRY's own PIT availability, never
    the original filing's -- the terms it carries were not knowable before
    this date, whatever the original decision date was."""
    if not receipt_number or not receipt_date:
        raise ValueError("an amendment entry requires its own receipt number and date")
    return {
        "receiptNumber": receipt_number,
        "receiptDate": receipt_date,
        "reportName": report_name,
        "fieldsChanged": list(fields_changed),
        "supersedesReceiptNumber": supersedes_receipt_number,
    }


def build_record(*, old_security: str, action_type: str,
                 old_issuer_corp_code: str | None = None,
                 decision_date: str | None = None,
                 effective_date: str | None = None,
                 cash_per_old_share: float | None = None,
                 successor_security: str | None = None,
                 successor_issuer_corp_code: str | None = None,
                 successor_shares_per_old_share: float | None = None,
                 fractional_share_treatment: str | None = None,
                 cash_in_lieu_rule: str | None = None,
                 last_trading_date: str | None = None,
                 source_receipt_number: str | None = None,
                 source_receipt_date: str | None = None,
                 sources: tuple[str, ...] = (),
                 consideration_components: tuple[dict, ...] = (),
                 amendment_history: tuple[dict, ...] = (),
                 final_terms_receipt_number: str | None = None,
                 unresolved_fields: tuple[str, ...] = ()) -> dict:
    """One terminal-action record.

    Refuses a term with no citing receipt outright, rather than storing it
    unvouched: this is the check `replay_recovery.load_corporate_actions`
    already runs on the US book at LOAD time, moved here to CONSTRUCTION
    time so a record can never exist in an unvouched state to begin with.
    Every entry in `consideration_components` was already checked by
    `build_consideration_component`, and is re-checked here (a caller could
    hand-build a dict instead of calling that function).
    """
    if action_type not in ACTION_TYPES:
        raise ValueError(f"unknown actionType: {action_type}")
    has_term = any(v not in (None, "") for v in
                   (cash_per_old_share, successor_security, successor_shares_per_old_share))
    if has_term and not (source_receipt_number and source_receipt_date):
        raise ValueError("a resolved consideration term requires its DART receipt")
    for component in consideration_components:
        if component.get("type") not in COMPONENT_TYPES:
            raise ValueError(f"unknown consideration component type: {component.get('type')}")
        component_has_value = any(
            component.get(field) not in (None, "")
            for field in ("cashAmount", "successorSecurity", "sharesPerOldShare"))
        if component_has_value and not (component.get("sourceReceiptNumber")
                                        and component.get("sourceReceiptDate")):
            raise ValueError("a resolved consideration component requires its DART receipt")
    evidence_status = EVIDENCE_SEALED if source_receipt_number else EVIDENCE_UNRESOLVED
    return {
        "oldSecurity": old_security,
        "oldIssuerCorpCode": old_issuer_corp_code,
        "actionType": action_type,
        "decisionDate": decision_date,
        "effectiveDate": effective_date,
        "cashPerOldShare": cash_per_old_share,
        "successorSecurity": successor_security,
        "successorIssuerCorpCode": successor_issuer_corp_code,
        "successorSharesPerOldShare": successor_shares_per_old_share,
        "fractionalShareTreatment": fractional_share_treatment,
        "cashInLieuRule": cash_in_lieu_rule,
        "lastTradingDate": last_trading_date,
        "sourceReceiptNumber": source_receipt_number,
        "sourceReceiptDate": source_receipt_date,
        "sourceReceiptNumbers": sorted({r for r in (
            [source_receipt_number] if source_receipt_number else []) + [
                c.get("sourceReceiptNumber") for c in consideration_components if c.get("sourceReceiptNumber")
            ] + [a.get("receiptNumber") for a in amendment_history if a.get("receiptNumber")] if r}),
        "evidenceStatus": evidence_status,
        "sources": list(sources),
        "considerationComponents": list(consideration_components),
        "amendmentHistory": list(amendment_history),
        "finalTermsReceiptNumber": final_terms_receipt_number or source_receipt_number,
        "unresolvedFields": list(unresolved_fields),
    }


def validate_book(actions: list[dict]) -> None:
    """The same defensive checks `build_record` applies at construction,
    reapplied at load time for a book read back from disk — so a hand-edited
    or externally-produced JSON file cannot smuggle an unvouched term past
    the loader the way `replay_recovery.load_corporate_actions` already
    guards the US book. Also re-checks every `considerationComponents` entry
    and every `amendmentHistory` entry, for the same reason.
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
        for component in row.get("considerationComponents") or []:
            if component.get("type") not in COMPONENT_TYPES:
                raise ValueError(f"unknown consideration component type: {key}")
            component_has_value = any(
                component.get(field) not in (None, "")
                for field in ("cashAmount", "successorSecurity", "sharesPerOldShare"))
            if component_has_value and not (component.get("sourceReceiptNumber")
                                            and component.get("sourceReceiptDate")):
                raise ValueError(f"unvouched consideration component: {key}")
        for amendment in row.get("amendmentHistory") or []:
            if not amendment.get("receiptNumber") or not amendment.get("receiptDate"):
                raise ValueError(f"amendment entry missing receipt number/date: {key}")


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


def all_successors_of(row: dict) -> list[str]:
    """Every distinct successor security a record names -- the primary
    `successorSecurity` field plus every `SUCCESSOR_SHARES` component,
    deduplicated, order-preserved. A record with one successor returns a
    one-element list; a split-merger into two successor entities returns
    both, which the single-successor `successorSecurity` field alone could
    never represent."""
    out: list[str] = []
    if row.get("successorSecurity") and row["successorSecurity"] not in out:
        out.append(row["successorSecurity"])
    for component in row.get("considerationComponents") or []:
        security = component.get("successorSecurity")
        if component.get("type") == COMPONENT_SUCCESSOR_SHARES and security and security not in out:
            out.append(security)
    return out


def chain_all_successors(actions: list[dict]) -> dict[str, dict]:
    """`oldSecurity` -> a REACHABILITY graph of every successor it can lead
    to, following EVERY successor a record names (not just the primary
    one) -- the multi-successor generalization `chain_successors` cannot
    express. Cycle-safe: a security already visited on the current walk is
    reported (`cyclesDetected`) and never re-descended into, so a malformed
    or genuinely circular input can never loop this function forever.
    Computes no return; see module docstring.
    """
    by_old: dict[str, list[str]] = {row["oldSecurity"]: all_successors_of(row) for row in actions}
    out: dict[str, dict] = {}
    for start in by_old:
        reachable: list[str] = []
        cycles: list[str] = []
        stack = [start]
        visited = {start}
        while stack:
            current = stack.pop()
            for successor in by_old.get(current, []):
                if successor in visited:
                    if successor not in cycles:
                        cycles.append(successor)
                    continue
                visited.add(successor)
                reachable.append(successor)
                stack.append(successor)
        out[start] = {"reachableSuccessors": sorted(reachable), "cyclesDetected": sorted(cycles)}
    return out


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
