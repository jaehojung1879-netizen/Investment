"""Deterministic per-security inventory for the 22 KR terminated securities.

`alpha-opportunity-model-v3`'s sealed survivorship audit
(`docs/results/alpha-opportunity-model-v3-survivorship-audit.json`) found 22
KR securities that terminate inside the historical price sample with zero
dividend events and no terminal value on record. This module builds one
deterministic row per security from that audit's own `krTerminations` list —
never a hardcoded list — plus whatever DART identity, terminal-action and
dividend-lineage evidence has actually been resolved so far.

A SECURITY ABSENT FROM AN EVIDENCE MAP STAYS UNRESOLVED. `build_inventory`
never defaults a field to "ready" because evidence was not supplied; every
row is exactly as complete as the evidence maps handed to it, which is what
lets this module be called BOTH now (all maps empty, because this sandbox
has no live DART access — see the accompanying doc) and after a live
collection run, without a second code path.
"""
from __future__ import annotations

from . import kr_terminal_corporate_actions as TCA

READY = "READY"
NOT_APPLICABLE = "NOT_APPLICABLE"
BLOCKED = "BLOCKED"
STATUSES = frozenset({READY, NOT_APPLICABLE, BLOCKED})

MATRIX_FIELDS = (
    "terminationTypeResolved", "dartIssuerResolved", "dividendLineageResolved",
    "exDateSemanticsResolved", "terminalConsiderationResolved",
    "successorResolvedWhereRequired", "effectiveDateResolved",
    "lastTradingDateResolved", "rawEvidenceRetained", "sourceProvenanceRetained",
    # Added for `kr-terminal-action-reconstruction-v2`'s 12-field matrix
    # (TERMINAL_ACTION_CHAIN, EXCHANGE_RATIO) -- additive, every field above
    # keeps its original meaning and every v1 fixture still passes.
    "terminalActionChainResolved", "exchangeRatioResolved",
)

DART_DIRECTORY_NOT_AVAILABLE = "DART_DIRECTORY_NOT_AVAILABLE"
DIVIDEND_NOT_COLLECTED = "NOT_COLLECTED"
DIVIDEND_RESOLVED = "RESOLVED"

READY_FOR_V4_PREREGISTRATION = "READY_FOR_V4_PREREGISTRATION"
BLOCKED_BY_SOURCE_ACCESS = "BLOCKED_BY_SOURCE_ACCESS"
BLOCKED_BY_HISTORICAL_DEPTH = "BLOCKED_BY_HISTORICAL_DEPTH"
BLOCKED_BY_IDENTITY = "BLOCKED_BY_IDENTITY"
BLOCKED_BY_DIVIDEND_LINEAGE = "BLOCKED_BY_DIVIDEND_LINEAGE"
BLOCKED_BY_TERMINAL_CONSIDERATION = "BLOCKED_BY_TERMINAL_CONSIDERATION"
PARTIALLY_REPAIRED = "PARTIALLY_REPAIRED"
FOUNDATION_STATUSES = frozenset({
    READY_FOR_V4_PREREGISTRATION, BLOCKED_BY_SOURCE_ACCESS,
    BLOCKED_BY_HISTORICAL_DEPTH, BLOCKED_BY_IDENTITY,
    BLOCKED_BY_DIVIDEND_LINEAGE, BLOCKED_BY_TERMINAL_CONSIDERATION,
    PARTIALLY_REPAIRED,
})


def _status(resolved: bool, applicable: bool = True) -> str:
    if not applicable:
        return NOT_APPLICABLE
    return READY if resolved else BLOCKED


def completeness_row(*, identity: dict | None, action: dict | None,
                     dividends: dict | None, last_trading_date: str | None) -> dict:
    """One security's field x READY/NOT_APPLICABLE/BLOCKED row.

    `exDateSemanticsResolved` is `READY` only when `dividends` states
    `exDateSource: "DIRECT"` — an ex-date DART's own disclosure stated,
    never one this codebase derived. No sealed, dated KR settlement-cycle
    rule exists anywhere in this repository to derive an ex-date from a
    record date (see `kr_corporate_action_events.EX_DATE_STATUS_BLOCKED`),
    so a `DERIVED` or absent source stays `BLOCKED` — never invented here,
    and never flipped to `READY` by a hardcoded rule.
    """
    action_type = (action or {}).get("actionType") or TCA.TERMINATION_TYPE_UNRESOLVED
    action = action or {}
    type_resolved = action_type in TCA.ACTION_TYPES - {TCA.TERMINATION_TYPE_UNRESOLVED}
    requires_successor = action_type in TCA.REQUIRES_SUCCESSOR_TERM
    # Only an explicitly cash-only type proves that shares are irrelevant.
    cash_only = action_type in {TCA.MERGER_CASH, TCA.TENDER_CASH_OUT, TCA.CASH_SHARE_EXCHANGE}
    cited = bool(action.get("sourceReceiptNumber") and action.get("sourceReceiptDate"))
    unresolved = set(action.get("unresolvedFields") or [])
    cash_resolved = cited and action.get("cashPerOldShare") is not None
    successor_resolved = (cited and bool(action.get("successorSecurity"))
                          and "successorSecurity" not in unresolved)
    ratio_resolved = (cited and action.get("successorSharesPerOldShare") is not None
                      and "successorSharesPerOldShare" not in unresolved)
    # A receipt/sealed status alone states no economic terms. Require every
    # leg owed by the resolved type; generic delisting types stay blocked.
    consideration_resolved = (
        type_resolved
        and action_type in TCA.REQUIRES_CASH_TERM | TCA.REQUIRES_SUCCESSOR_TERM
        and (action_type not in TCA.REQUIRES_CASH_TERM or cash_resolved)
        and (not requires_successor or (successor_resolved and ratio_resolved))
        and not unresolved.intersection({"terminalConsideration", "cashPerOldShare",
                                         "considerationComponents"}))
    has_raw_evidence = bool((action or {}).get("sourceReceiptNumber")
                            or (action or {}).get("sources")
                            or (action or {}).get("sourceReceiptNumbers"))
    return {
        "terminationTypeResolved": _status(type_resolved),
        "dartIssuerResolved": _status(bool((identity or {}).get("corpCode"))),
        "dividendLineageResolved": _status(
            bool(dividends and dividends.get("status") == DIVIDEND_RESOLVED)),
        "exDateSemanticsResolved": _status(
            bool(dividends and dividends.get("exDateSource") == "DIRECT")),
        "terminalConsiderationResolved": _status(
            consideration_resolved),
        "successorResolvedWhereRequired": _status(
            successor_resolved, applicable=not cash_only),
        "effectiveDateResolved": _status(bool((action or {}).get("effectiveDate"))),
        "lastTradingDateResolved": _status(bool(last_trading_date)),
        "rawEvidenceRetained": _status(has_raw_evidence),
        "sourceProvenanceRetained": _status(bool((action or {}).get("sources"))),
        # Capturing a disclosure/amendment list does not resolve its terms.
        # A chain needs a dated, resolved action with complete economics and
        # a final-terms citation; explicit outstanding fields keep it blocked.
        "terminalActionChainResolved": _status(
            consideration_resolved and bool(action.get("effectiveDate"))
            and action.get("amendmentHistory") is not None
            and bool(action.get("finalTermsReceiptNumber")) and not unresolved),
        "exchangeRatioResolved": _status(ratio_resolved, applicable=not cash_only),
    }


def build_inventory(*, kr_terminations: list[dict],
                    kr_membership_windows: dict[str, dict] | None = None,
                    dart_identity: dict[str, dict] | None = None,
                    terminal_actions: dict[str, dict] | None = None,
                    dividend_lineage: dict[str, dict] | None = None) -> list[dict]:
    """One deterministic row per security in `kr_terminations`.

    `kr_terminations` is expected to be the sealed v3 audit's own
    `krTerminations` list, read by the caller — see this module's docstring
    and `scripts/build_kr_termination_inventory.py`, which is the only place
    that list is ever read from disk.
    """
    kr_membership_windows = kr_membership_windows or {}
    dart_identity = dart_identity or {}
    terminal_actions = terminal_actions or {}
    dividend_lineage = dividend_lineage or {}
    rows = []
    for term in sorted(kr_terminations, key=lambda r: r["code"]):
        code = term["code"]
        window = kr_membership_windows.get(code) or {}
        identity = dart_identity.get(code)
        action = terminal_actions.get(code)
        dividends = dividend_lineage.get(code)
        last_trading_date = term.get("lastSession")
        rows.append({
            "code": code,
            "krxName": term.get("krxName"),
            "firstMembershipDate": window.get("first"),
            "lastMembershipDate": window.get("last"),
            "lastTradingDate": last_trading_date,
            "dartCorpCode": (identity or {}).get("corpCode"),
            "dartIdentityStatus": (identity or {}).get("status") or DART_DIRECTORY_NOT_AVAILABLE,
            "terminationType": (action or {}).get("actionType") or TCA.TERMINATION_TYPE_UNRESOLVED,
            "evidenceSources": list((action or {}).get("sources") or []),
            "evidenceReceiptNumbers": sorted((action or {}).get("sourceReceiptNumbers") or
                                             [r for r in [(action or {}).get("sourceReceiptNumber")] if r]),
            "evidenceReceiptDates": [r for r in [(action or {}).get("sourceReceiptDate")] if r],
            "dividendEventsKnownFromYahoo": term.get("dividendEvents", 0),
            "dividendLineageStatus": (dividends or {}).get("status") or DIVIDEND_NOT_COLLECTED,
            "completeness": completeness_row(
                identity=identity, action=action, dividends=dividends,
                last_trading_date=last_trading_date),
        })
    return rows


def foundation_status(rows: list[dict]) -> str:
    """One of `FOUNDATION_STATUSES`, computed from the matrix alone.

    Never forced to `READY_FOR_V4_PREREGISTRATION` — see module docstring
    and section 17 of the task this module was built for. A security absent
    from the DART directory keeps the whole foundation `BLOCKED_BY_
    SOURCE_ACCESS`, because nothing downstream of identity resolution can
    even be attempted for it.
    """
    if not rows:
        return BLOCKED_BY_SOURCE_ACCESS
    # A status string alone is not evidence -- "searched and found nothing"
    # (e.g. `NOT_FOUND`) must read the same as never having searched. Only an
    # actual resolved `dartCorpCode` counts.
    any_identity_resolved = any(row["dartCorpCode"] for row in rows)
    if not any_identity_resolved:
        return BLOCKED_BY_SOURCE_ACCESS
    all_ready = all(
        all(value in (READY, NOT_APPLICABLE) for value in row["completeness"].values())
        for row in rows)
    if all_ready:
        return READY_FOR_V4_PREREGISTRATION
    any_ready_anywhere = any(
        any(value == READY for value in row["completeness"].values()) for row in rows)
    if not any_ready_anywhere:
        return BLOCKED_BY_SOURCE_ACCESS
    blocked_fields = {field for row in rows for field, value in row["completeness"].items()
                      if value == BLOCKED}
    if "dartIssuerResolved" in blocked_fields and len(blocked_fields) == 1:
        return BLOCKED_BY_IDENTITY
    if blocked_fields <= {"dividendLineageResolved", "exDateSemanticsResolved"}:
        return BLOCKED_BY_DIVIDEND_LINEAGE
    if blocked_fields <= {"terminalConsiderationResolved", "successorResolvedWhereRequired",
                          "terminationTypeResolved", "terminalActionChainResolved",
                          "exchangeRatioResolved"}:
        return BLOCKED_BY_TERMINAL_CONSIDERATION
    return PARTIALLY_REPAIRED


def summary(rows: list[dict]) -> dict:
    """The per-field READY count across all rows, for the doc's completeness
    matrix table — never a value used to decide `foundation_status`."""
    return {
        "securities": len(rows),
        "byField": {
            field: sum(row["completeness"][field] == READY for row in rows)
            for field in MATRIX_FIELDS
        },
        "terminationTypeBreakdown": {
            action_type: sum(row["terminationType"] == action_type for row in rows)
            for action_type in sorted(TCA.ACTION_TYPES)
            if any(row["terminationType"] == action_type for row in rows)
        },
    }
