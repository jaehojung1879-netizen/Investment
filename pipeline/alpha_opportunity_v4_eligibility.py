"""Deterministic KR terminated-security label-eligibility policy.

`alpha-opportunity-model-v4` preregistration only. This module computes
whether a historical (security, signal date, horizon) observation may ever
receive a forward-return LABEL -- it never reads a price, a return, or an
outcome, and it never computes one. It is a pure function of already-sealed
completeness metadata (`docs/results/kr-terminal-action-reconstruction-v2
.json`'s per-security `completeness` rows) plus calendar facts a caller
supplies (does this window cross the security's last trading date).

WHY A SECURITY-LEVEL GATE, NOT ONLY A WINDOW-CROSSES-TERMINATION GATE.
Production's KR price panel (`pipeline/korea_prices.py`) takes distributions
from Yahoo "if Yahoo happens to carry the name", and Yahoo serves none of
the 22 securities `alpha-opportunity-model-v3`'s sealed survivorship audit
found terminating inside the sample. That is not only a problem for the
window that crosses termination: it means EVERY session of these 22
securities' trading life, not only the final one, is on a price-return
basis while the matched benchmark (069500.KS) and every continuing name are
on a total-return basis. A forward window entirely BEFORE termination is
therefore not automatically clean; it is clean only once the security's own
dividend ex-date lineage is resolved (`exDateSemanticsResolved: READY` in
the sealed completeness matrix) AND a total-return series has actually been
reconstructed and spliced into the price panel used to build labels. Until
both are true, no observation on that security -- pre- or post-termination
-- is eligible. This is a stronger, and simpler, predeclared rule than
trying to bound only the terminal window, and it is the one this module
enforces: `exDateSemanticsResolved` gates the WHOLE security.

WHY THIS IS A COMPUTED CONSEQUENCE, NOT A HARDCODED LIST. Every function
here takes the completeness row as an argument. As of this seal (see
`docs/results/alpha-opportunity-model-v4-eligibility-policy.json`), all 22
known-terminated securities read `exDateSemanticsResolved: BLOCKED` in
`docs/results/kr-terminal-action-reconstruction-v2.json`, so this policy
excludes all 22 today -- but if a future, separate data-foundation PR
resolves a specific security's ex-date lineage (never inferred, never
derived from a record date -- see that document's own PIT semantics
section) and splices a real total-return series for it, the SAME function,
unmodified, would admit that security's pre-termination observations
without a new preregistration. A window crossing termination additionally
requires the full terminal-action chain (`terminalActionChainResolved`) and,
where a successor is required, that successor's own price panel.

WHAT THIS MODULE NEVER DOES. It never treats an unresolved exchange ratio or
successor as final. It never invents an ex-date from a record date (no
sealed, dated Korean settlement-cycle rule exists anywhere in this
repository -- see `docs/kr-terminated-security-total-return-foundation-v1
.md`). It never carries the last traded price forward through a
termination, never treats a name's realised return magnitude as a reason to
exclude it, and never uses today's universe membership to stand in for a
historical one. A security or window this module marks INELIGIBLE is
DATA_UNAVAILABLE for that label, never assigned a zero, a benchmark-matching
return, or any other manufactured value.
"""
from __future__ import annotations

CONTRACT = "ALPHA_OPPORTUNITY_V4_KR_LABEL_ELIGIBILITY_V1"

ELIGIBLE = "ELIGIBLE"
INELIGIBLE = "INELIGIBLE"
STATUSES = frozenset({ELIGIBLE, INELIGIBLE})

READY = "READY"
NOT_APPLICABLE = "NOT_APPLICABLE"

# Stable reason codes. Never invented after an outcome is seen; every code
# below existed before any label under this policy was ever constructed.
NOT_A_KNOWN_TERMINATED_SECURITY = "NOT_A_KNOWN_TERMINATED_SECURITY"
NO_COMPLETENESS_EVIDENCE = "KR_TERMINATED_SECURITY_NO_COMPLETENESS_EVIDENCE"
EXDATE_LINEAGE_UNRESOLVED = "KR_TERMINATED_SECURITY_DIVIDEND_EXDATE_LINEAGE_UNRESOLVED"
TOTAL_RETURN_SERIES_NOT_BUILT = "KR_TERMINATED_SECURITY_TOTAL_RETURN_SERIES_NOT_YET_BUILT"
TERMINATION_TYPE_UNRESOLVED = "KR_TERMINATION_TYPE_UNRESOLVED"
TERMINAL_CONSIDERATION_UNRESOLVED = "KR_TERMINAL_CONSIDERATION_UNRESOLVED"
SUCCESSOR_IDENTITY_UNRESOLVED = "KR_SUCCESSOR_IDENTITY_UNRESOLVED"
TERMINAL_ACTION_CHAIN_UNRESOLVED = "KR_TERMINAL_ACTION_CHAIN_UNRESOLVED"
SUCCESSOR_HAS_NO_PRICE_PANEL = "KR_SUCCESSOR_HAS_NO_PRICE_PANEL"
PRE_TERMINATION_WINDOW_BASIS_RESOLVED = "PRE_TERMINATION_WINDOW_TOTAL_RETURN_BASIS_RESOLVED"
TERMINATION_WINDOW_FULLY_RESOLVED = "TERMINATION_WINDOW_FULLY_RESOLVED"

REASON_CODES = frozenset({
    NOT_A_KNOWN_TERMINATED_SECURITY, NO_COMPLETENESS_EVIDENCE, EXDATE_LINEAGE_UNRESOLVED,
    TOTAL_RETURN_SERIES_NOT_BUILT, TERMINATION_TYPE_UNRESOLVED, TERMINAL_CONSIDERATION_UNRESOLVED,
    SUCCESSOR_IDENTITY_UNRESOLVED, TERMINAL_ACTION_CHAIN_UNRESOLVED, SUCCESSOR_HAS_NO_PRICE_PANEL,
    PRE_TERMINATION_WINDOW_BASIS_RESOLVED, TERMINATION_WINDOW_FULLY_RESOLVED,
})


def label_eligibility(*, code: str, known_terminated_codes: frozenset,
                      completeness: dict | None, window_crosses_termination: bool,
                      successor_codes: tuple[str, ...] = (),
                      priced_securities: frozenset = frozenset(),
                      total_return_series_built: frozenset = frozenset()) -> dict:
    """One (security, window) eligibility decision. Reads no price or return.

    `window_crosses_termination` is a pure calendar fact the caller computes
    from the same regional session calendar `alpha_opportunity_v2_evaluation
    .target_from_sessions` already uses (exit session strictly after the
    security's own last traded session) -- this module does not compute it,
    to avoid a second, possibly disagreeing, calendar implementation.
    """
    if code not in known_terminated_codes:
        return {"status": ELIGIBLE, "reasonCode": NOT_A_KNOWN_TERMINATED_SECURITY}
    if not completeness:
        return {"status": INELIGIBLE, "reasonCode": NO_COMPLETENESS_EVIDENCE}
    if completeness.get("exDateSemanticsResolved") != READY:
        return {"status": INELIGIBLE, "reasonCode": EXDATE_LINEAGE_UNRESOLVED}
    if code not in total_return_series_built:
        return {"status": INELIGIBLE, "reasonCode": TOTAL_RETURN_SERIES_NOT_BUILT}
    if not window_crosses_termination:
        return {"status": ELIGIBLE, "reasonCode": PRE_TERMINATION_WINDOW_BASIS_RESOLVED}
    if completeness.get("terminationTypeResolved") != READY:
        return {"status": INELIGIBLE, "reasonCode": TERMINATION_TYPE_UNRESOLVED}
    if completeness.get("terminalConsiderationResolved") != READY:
        return {"status": INELIGIBLE, "reasonCode": TERMINAL_CONSIDERATION_UNRESOLVED}
    successor_applicable = completeness.get("successorResolvedWhereRequired") != NOT_APPLICABLE
    if successor_applicable and completeness.get("successorResolvedWhereRequired") != READY:
        return {"status": INELIGIBLE, "reasonCode": SUCCESSOR_IDENTITY_UNRESOLVED}
    if completeness.get("terminalActionChainResolved") != READY:
        return {"status": INELIGIBLE, "reasonCode": TERMINAL_ACTION_CHAIN_UNRESOLVED}
    if successor_applicable:
        unpriced = sorted(s for s in successor_codes if s not in priced_securities)
        if unpriced:
            return {"status": INELIGIBLE, "reasonCode": SUCCESSOR_HAS_NO_PRICE_PANEL,
                    "unpricedSuccessors": unpriced}
    return {"status": ELIGIBLE, "reasonCode": TERMINATION_WINDOW_FULLY_RESOLVED}


def security_level_verdict(*, code: str, completeness: dict | None) -> dict:
    """Whether ANY observation on this security could ever be eligible today,
    ignoring the window-crosses-termination distinction -- `exDateSemantics
    Resolved` gates the entire security regardless of window, so this is the
    single check that decides whether a security's pre-termination history
    is usable at all under current evidence. Used by the audit script; never
    used to construct a label itself.
    """
    if not completeness:
        return {"code": code, "status": INELIGIBLE, "reasonCode": NO_COMPLETENESS_EVIDENCE}
    if completeness.get("exDateSemanticsResolved") != READY:
        return {"code": code, "status": INELIGIBLE, "reasonCode": EXDATE_LINEAGE_UNRESOLVED}
    return {"code": code, "status": "CONDITIONALLY_ELIGIBLE_PENDING_TOTAL_RETURN_SERIES_BUILD",
            "reasonCode": None}


def bulk_security_verdicts(*, kr_terminations: list[dict],
                           completeness_by_code: dict[str, dict]) -> list[dict]:
    """One `security_level_verdict` row per security in the sealed v3
    `krTerminations` list -- never a hardcoded code list."""
    return [security_level_verdict(code=row["code"],
                                   completeness=completeness_by_code.get(row["code"]))
            for row in sorted(kr_terminations, key=lambda r: r["code"])]
