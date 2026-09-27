"""Deterministic KR terminated-security label-eligibility policy.

`alpha-opportunity-model-v4` preregistration only. This module computes
whether a historical (security, signal date, horizon) observation may ever
receive a forward-return LABEL -- it never reads a price, a return, or an
outcome, and it never computes one. It is a pure function of already-sealed
completeness metadata (`docs/results/kr-terminal-action-reconstruction-v2
.json`'s per-security `completeness` rows) plus one calendar fact a caller
supplies (does this window's own exit session fall after the security's
last traded session).

CORRECTION (this revision): the first version of this module took a
`known_terminated_codes` set and a `code` and used membership in that set as
its FIRST branch -- "not one of the 22 known-to-terminate => ELIGIBLE,
otherwise evaluate completeness". That is a look-ahead defect: it used the
security's *eventual* outcome (does it terminate at all) to decide whether a
PRE-termination observation, whose own target window never touches the
termination event, gets extra scrutiny. Two securities with identical
observable dividend/terminal-action evidence through a target's own exit
date must be treated identically whether or not one of them happens to
terminate years later -- that is not what the first version did, because it
never even looked at completeness evidence for a security outside the
audited list, and it excluded EVERY observation on an audited security
(regardless of whether that observation's own window ever touches the
termination event) for a reason keyed on list membership rather than on the
window's own data requirement.

THE FIX. `label_eligibility` no longer takes a security's code or its
termination-list membership at all. It takes exactly two things that are
facts about the OBSERVATION itself, never about the security's future:

  `completeness`   -- the sealed completeness row for this security, or
                       `None` if this repository has never audited its
                       dividend/terminal-action evidence. Audit coverage
                       today extends only to the 22 KR securities in the
                       sealed `alpha-opportunity-model-v3` survivorship
                       audit's `krTerminations` list -- a fact about which
                       securities this repository has BUILT evidence for
                       (a research-coverage accident of sequencing: that
                       audit was commissioned to investigate exactly these
                       22), never a fact used by this function to decide
                       eligibility. A currently-surviving security that
                       happened to be audited for the same reason (e.g. a
                       false positive in an earlier list, or a future
                       symmetric audit) would be evaluated by the identical
                       rule below.
  `window_crosses_termination` -- whether THIS window's own scheduled exit
                       session falls after the security's own last traded
                       session. This is legitimate, not a look-ahead: a
                       forward-return target is, by construction, a claim
                       about a FUTURE interval relative to its signal date,
                       and asking whether that interval's own endpoint
                       crosses a corporate event that occurred INSIDE it is
                       asking about the target's own definition, exactly as
                       `alpha_opportunity_v2_evaluation.target_from_sessions`
                       already asks whether the target's own endpoint session
                       exists in the price panel at all
                       (`MISSING_FORWARD_PRICE_OR_DELISTING`). It is never
                       used to ask anything about a window that does not
                       itself span the event.

WHY THE PRE-TERMINATION GATE IS NOT SURVIVORSHIP-CONDITIONED EVEN THOUGH THE
22 STAY EXCLUDED TODAY. `exDateSemanticsResolved` is computed (in
`kr_termination_inventory.completeness_row`) from a security's OWN dividend
evidence -- whether a disclosure states an ex-date DIRECTLY -- never from
whether it terminates. Production's real basis for every OTHER KR security
(continuing or departed-but-still-trading) is simply "whatever Yahoo's own
per-row dividend date says" (`pipeline/price_adjustment.to_total_return`
trusts the vendor row's own index date as the ex-date, with no independent
verification anywhere in this codebase) -- so holding the 22 audited names to
a stricter, DART-confirmed standard while everyone else defers to unverified
Yahoo rows would ITSELF be the asymmetric, outcome-correlated scrutiny this
correction removes. The reason the 22 fail today is not that standard; it is
a stronger, prior, DART-verified fact this repository already established
for them specifically: `alpha-opportunity-model-v3`'s sealed audit measured
ZERO Yahoo dividend rows across their ENTIRE observed lives (not merely after
delisting), and Yahoo has ~93% dividend-event coverage (215/238) on
continuing names over the same window -- so "trust whatever Yahoo says" has
literally nothing to trust for these 22, not merely something unverified.
`completeness is None` (not audited) therefore defers to production exactly
as every other KR security already does; `completeness` present with
`exDateSemanticsResolved` still `BLOCKED` means this repository has already
looked and confirmed there is nothing to defer to. Both branches are
computed from the security's OWN dividend record, never from a termination
flag -- proved by `tests/test_alpha_opportunity_v4.py`'s future-termination-
invariance tests, which vary only a synthetic "terminates later" label while
holding completeness fixed and show the eligibility call is identical.

A SECOND-ORDER CONCERN, INVESTIGATED AND CORROBORATED (this revision): even
with the code fix above, a fair question remains -- WHO gets a `completeness`
row at all is itself decided by a research project commissioned specifically
to investigate the 22 known-terminated names, so does trusting
`completeness is None` as "defer to production" quietly re-import the same
bias through the back door (nobody ever looks for the same failure mode in a
name that happens to survive)? This is not answered by code alone; it needed
evidence. `docs/results/kr-dividend-amount-lineage-v2.json`'s
`continuingNameReconciliation` already cross-validates DART fiscal-year
dividend amounts against Yahoo's own window sums for a 25-name CONTINUING-name
sample selected by `pipeline.kr_continuing_dividend_sample.select_continuing_
sample` -- ranked purely by how many monthly snapshots a code held a top-120
market-cap rank, EXCLUDING the 22 under study, with NOTHING about dividend
completeness in the ranking rule. Measured directly: of 226 ticker-fiscal-year
rows across those 25 names where DART states a real dividend amount, 224
(99.1%) show at least one matching-or-mismatched Yahoo event in the same
window, and ZERO of the 25 continuing names show the specific failure pattern
all 22 terminated names show (DART confirms dividends existed; Yahoo shows
NONE across the whole observed life). One name (010140.KS) has no DART
fiscal-year rows to check at all -- a data-absence case (`this security may
never have paid a dividend in the window`, category C: unknown from this
evidence, never assumed to be A or B) that neither corroborates nor
contradicts the pattern, and is not counted either way.

This is corroboration, not a full audit, and is reported as exactly that: it
supports treating `completeness is None` as a genuine "unknown" (never a
"confirmed clean") default for the 213 continuing names this sample does not
cover, because the SPECIFIC failure mode this study cares about was measured,
on an outcome-blind sample, to be rare among continuing names (0 of 25) and
universal among the audited terminated ones (22 of 22) -- not merely assumed
absent because nobody checked. A full audit of all 260 KR securities remains
future, separate, additive work (`docs/alpha-opportunity-model-v4-
preregistration.md`'s own scope section), never claimed to be done here.

WHAT THIS MODULE NEVER DOES. It never treats an unresolved exchange ratio or
successor as final. It never invents an ex-date from a record date (no
sealed, dated Korean settlement-cycle rule exists anywhere in this
repository -- see `docs/kr-terminated-security-total-return-foundation-v1
.md`). It never carries the last traded price forward through a
termination, never treats a name's realised return magnitude as a reason to
exclude it, never uses today's universe membership to stand in for a
historical one, and never uses whether -- or when -- a security eventually
terminates as an input to any decision about a window that does not itself
span that event.
"""
from __future__ import annotations

CONTRACT = "ALPHA_OPPORTUNITY_V4_KR_LABEL_ELIGIBILITY_V2"

ELIGIBLE = "ELIGIBLE"
INELIGIBLE = "INELIGIBLE"
STATUSES = frozenset({ELIGIBLE, INELIGIBLE})

READY = "READY"
NOT_APPLICABLE = "NOT_APPLICABLE"

# Stable reason codes. Never invented after an outcome is seen; every code
# below existed before any label under this policy was ever constructed.
# None reads or implies a security's eventual termination status.
NO_COMPLETENESS_EVIDENCE = "KR_TERMINATION_CROSSING_WINDOW_NO_COMPLETENESS_EVIDENCE"
DIVIDEND_BASIS_AUDIT_NOT_PERFORMED = "KR_DIVIDEND_BASIS_AUDIT_NOT_PERFORMED_DEFERS_TO_PRODUCTION"
EXDATE_LINEAGE_UNRESOLVED = "KR_DIVIDEND_EXDATE_LINEAGE_UNRESOLVED"
TOTAL_RETURN_SERIES_NOT_BUILT = "KR_TOTAL_RETURN_SERIES_NOT_YET_BUILT"
PRE_TERMINATION_WINDOW_BASIS_RESOLVED = "PRE_TERMINATION_WINDOW_TOTAL_RETURN_BASIS_RESOLVED"
TERMINATION_TYPE_UNRESOLVED = "KR_TERMINATION_TYPE_UNRESOLVED"
TERMINAL_CONSIDERATION_UNRESOLVED = "KR_TERMINAL_CONSIDERATION_UNRESOLVED"
SUCCESSOR_IDENTITY_UNRESOLVED = "KR_SUCCESSOR_IDENTITY_UNRESOLVED"
TERMINAL_ACTION_CHAIN_UNRESOLVED = "KR_TERMINAL_ACTION_CHAIN_UNRESOLVED"
SUCCESSOR_HAS_NO_PRICE_PANEL = "KR_SUCCESSOR_HAS_NO_PRICE_PANEL"
TERMINATION_WINDOW_FULLY_RESOLVED = "TERMINATION_WINDOW_FULLY_RESOLVED"

REASON_CODES = frozenset({
    NO_COMPLETENESS_EVIDENCE, DIVIDEND_BASIS_AUDIT_NOT_PERFORMED, EXDATE_LINEAGE_UNRESOLVED,
    TOTAL_RETURN_SERIES_NOT_BUILT, PRE_TERMINATION_WINDOW_BASIS_RESOLVED,
    TERMINATION_TYPE_UNRESOLVED, TERMINAL_CONSIDERATION_UNRESOLVED,
    SUCCESSOR_IDENTITY_UNRESOLVED, TERMINAL_ACTION_CHAIN_UNRESOLVED,
    SUCCESSOR_HAS_NO_PRICE_PANEL, TERMINATION_WINDOW_FULLY_RESOLVED,
})

# Completeness fields this module reads ONLY on the termination-crossing
# path. Listed explicitly so a test can assert the pre-termination path
# never reads any of them (`test_future_metadata_mutation_invariance`).
TERMINATION_EVENT_FIELDS = frozenset({
    "terminationTypeResolved", "terminalConsiderationResolved",
    "successorResolvedWhereRequired", "terminalActionChainResolved",
})


def label_eligibility(*, completeness: dict | None, window_crosses_termination: bool,
                      total_return_series_available: bool = False,
                      successor_codes: tuple[str, ...] = (),
                      priced_securities: frozenset = frozenset()) -> dict:
    """One (security, window) eligibility decision. Reads no price or return.

    Takes no security identifier and no termination-list membership: see the
    module docstring for why. `window_crosses_termination` is a pure
    calendar fact the caller computes from the same regional session
    calendar `alpha_opportunity_v2_evaluation.target_from_sessions` already
    uses (exit session strictly after the security's own last traded
    session).
    """
    if not window_crosses_termination:
        # Nothing about a corporate termination is read on this path -- see
        # TERMINATION_EVENT_FIELDS and the module docstring.
        if completeness is None:
            return {"status": ELIGIBLE, "reasonCode": DIVIDEND_BASIS_AUDIT_NOT_PERFORMED}
        if completeness.get("exDateSemanticsResolved") != READY:
            return {"status": INELIGIBLE, "reasonCode": EXDATE_LINEAGE_UNRESOLVED}
        if not total_return_series_available:
            return {"status": INELIGIBLE, "reasonCode": TOTAL_RETURN_SERIES_NOT_BUILT}
        return {"status": ELIGIBLE, "reasonCode": PRE_TERMINATION_WINDOW_BASIS_RESOLVED}

    # The window's own exit session is after the security's last traded
    # session: the termination event is INSIDE this target, so its economics
    # are a genuine input to constructing this specific label.
    if not completeness:
        return {"status": INELIGIBLE, "reasonCode": NO_COMPLETENESS_EVIDENCE}
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


def pre_termination_window_verdict(*, completeness: dict | None,
                                   total_return_series_available: bool = False) -> dict:
    """`label_eligibility` restricted to a window that does not cross
    termination -- the only question a per-security (not per-window) audit
    can answer, since crossing depends on which window."""
    return label_eligibility(completeness=completeness, window_crosses_termination=False,
                             total_return_series_available=total_return_series_available)


def termination_crossing_window_verdict(*, completeness: dict | None,
                                        successor_codes: tuple[str, ...] = (),
                                        priced_securities: frozenset = frozenset()) -> dict:
    """`label_eligibility` restricted to a window that crosses termination."""
    return label_eligibility(completeness=completeness, window_crosses_termination=True,
                             successor_codes=successor_codes, priced_securities=priced_securities)


def security_level_verdict(*, code: str, completeness: dict | None) -> dict:
    """Both window-scoped verdicts for one security, for the audit script.

    Never itself used to construct a label: a real execution calls
    `label_eligibility` per (security, signal date, horizon), because
    `window_crosses_termination` is a per-observation fact this function
    does not have.
    """
    return {
        "code": code,
        "preTerminationWindows": pre_termination_window_verdict(completeness=completeness),
        "terminationCrossingWindows": termination_crossing_window_verdict(completeness=completeness),
    }


def bulk_security_verdicts(*, kr_terminations: list[dict],
                           completeness_by_code: dict[str, dict]) -> list[dict]:
    """One `security_level_verdict` row per security in the sealed v3
    `krTerminations` list -- never a hardcoded code list."""
    return [security_level_verdict(code=row["code"], completeness=completeness_by_code.get(row["code"]))
            for row in sorted(kr_terminations, key=lambda r: r["code"])]


# --------------------------------------------------------------------------- #
# Execution-data versioning: prefix stability, never byte-immutability.
# --------------------------------------------------------------------------- #
def assert_foundation_not_regressed(*, cited_snapshot: dict, current_snapshot: dict) -> bool:
    """The KR terminal-action reconstruction artifact is expected to IMPROVE
    over time (a future data-foundation PR resolving more evidence), never to
    be pinned byte-for-byte -- see `docs/alpha-opportunity-model-v4-
    preregistration.md` section 1 and the historical replay invariant that a
    growing ledger's own requirement is PREFIX STABILITY, not immutability.

    A future execution reads whatever current snapshot exists and calls this
    first: every security named in `cited_snapshot` must still be named in
    `current_snapshot`, and no completeness field that was `READY` in the
    cited snapshot may read anything other than `READY` in the current one.
    Raises `FOUNDATION_REGRESSED` naming the exact security/field on any
    violation; returns True otherwise. This never checks whether the
    snapshot IMPROVED (that is what makes new eligibility possible without a
    new preregistration) -- only that it never got worse.
    """
    cited_by_code = {row["code"]: row["completeness"] for row in cited_snapshot["securities"]}
    current_by_code = {row["code"]: row["completeness"] for row in current_snapshot.get("securities", [])}
    for code, cited_completeness in cited_by_code.items():
        if code not in current_by_code:
            raise ValueError(f"FOUNDATION_REGRESSED: {code} missing from current snapshot")
        current_completeness = current_by_code[code]
        for field, cited_value in cited_completeness.items():
            if cited_value == READY and current_completeness.get(field) != READY:
                raise ValueError(f"FOUNDATION_REGRESSED: {code}.{field} was READY, now "
                                 f"{current_completeness.get(field)!r}")
    return True


def freeze_execution_snapshot(reconstruction_snapshot: dict) -> str:
    """The THIRD tier of the versioning contract, alongside `assert_
    foundation_not_regressed`'s prefix-stability check: POLICY is sealed by
    this spec; FOUNDATION may improve monotonically before an execution
    starts (checked by that function); the EXECUTION SNAPSHOT is whichever
    current foundation state a specific execution run reads, and it must be
    frozen -- hashed and recorded immutably -- exactly once, BEFORE that run
    constructs its first label. A run may never re-read a newer snapshot
    partway through and may never choose among candidate snapshots based on
    which one produces a more favourable result: `canonical` and `digest`
    (`pipeline.alpha_opportunity_spec`) make the hash a pure, deterministic
    function of content, so the SAME snapshot always freezes to the SAME
    hash regardless of when or how many times it is computed. This function
    performs no I/O and reads no return or label; it only fixes what
    "the data used" means for a run that has not started yet.
    """
    from .alpha_opportunity_spec import digest
    return digest(reconstruction_snapshot)


def assert_snapshot_matches_frozen_hash(*, reconstruction_snapshot: dict, frozen_hash: str) -> bool:
    """A later step of the SAME execution run proves it is still reading the
    snapshot it froze at the start, guarding against a mid-run swap (e.g. a
    concurrent data-foundation PR landing between two steps of one run).
    Raises `EXECUTION_SNAPSHOT_CHANGED_MID_RUN` on any mismatch.
    """
    actual = freeze_execution_snapshot(reconstruction_snapshot)
    if actual != frozen_hash:
        raise ValueError(f"EXECUTION_SNAPSHOT_CHANGED_MID_RUN: expected {frozen_hash}, got {actual}")
    return True
