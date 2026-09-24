"""The exit-semantics vocabulary every network collector's run reduces to.

This is the fix for the real defect measured on 2026-09-24: the KR
investor-flow collector logged zero calls, zero records, and a `REFUSED`
stop reason after the KRX portal answered `HTTP 400: b'LOGOUT'` on its very
first request, and the GitHub Actions job still reported success. These
tests pin the classification a caller is expected to act on so that never
reads as `SERVED` again.
"""
from __future__ import annotations

from pipeline import collector_outcomes as OUT


# --------------------------------------------------------------------------- #
# classify_refusal
# --------------------------------------------------------------------------- #
def test_an_http_400_logout_body_is_blocked_source():
    assert OUT.classify_refusal("HTTP 400: b'LOGOUT'") == OUT.BLOCKED_SOURCE


def test_a_401_style_message_is_auth_required():
    assert OUT.classify_refusal("HTTP 401: unauthorized") == OUT.AUTH_REQUIRED


def test_a_non_json_response_is_schema_changed():
    assert OUT.classify_refusal("response was not JSON") == OUT.SCHEMA_CHANGED


def test_a_connection_level_exception_is_network_error():
    assert OUT.classify_refusal("URLError: [Errno -2] Name or service not known") == OUT.NETWORK_ERROR
    assert OUT.classify_refusal("TimeoutError: timed out") == OUT.NETWORK_ERROR


def test_an_unrecognised_message_defaults_to_blocked_source_not_a_guess():
    assert OUT.classify_refusal("something entirely new") == OUT.BLOCKED_SOURCE


# --------------------------------------------------------------------------- #
# run_outcome — this is the exact 2026-09-24 defect, pinned
# --------------------------------------------------------------------------- #
def test_the_real_kr_investor_flow_refusal_is_never_served():
    outcome = OUT.run_outcome(
        stop_reason="REFUSED: HTTP 400: b'LOGOUT'", calls=0, written=0)
    assert outcome == OUT.BLOCKED_SOURCE
    assert outcome != OUT.SERVED


def test_work_list_exhausted_with_real_progress_is_served():
    assert OUT.run_outcome(stop_reason="WORK_LIST_EXHAUSTED", calls=50, written=50) == OUT.SERVED


def test_budget_spent_mid_run_with_progress_is_served():
    assert OUT.run_outcome(stop_reason="CALL_BUDGET_SPENT", calls=200, written=180) == OUT.SERVED


def test_calls_made_but_every_row_empty_is_empty_but_valid_not_served():
    """The source answered every call (no exception raised) but had nothing
    for any of the requested ticker/dates — a genuinely different fact from
    a source that refused to answer at all."""
    assert OUT.run_outcome(stop_reason="WORK_LIST_EXHAUSTED", calls=10, written=0) == OUT.EMPTY_BUT_VALID


def test_nothing_pending_at_all_is_served_not_empty_but_valid():
    """Zero calls because there was nothing left to do (a re-run with an
    already-complete done-ledger) is a normal, healthy no-op."""
    assert OUT.run_outcome(stop_reason="WORK_LIST_EXHAUSTED", calls=0, written=0) == OUT.SERVED


def test_an_unrecognised_stop_reason_is_never_served():
    """A collector that invents a new stop reason without updating this
    module fails loudly rather than silently reporting a healthy run."""
    assert OUT.run_outcome(stop_reason="SOMETHING_NEW", calls=0, written=0) == OUT.BLOCKED_SOURCE


# --------------------------------------------------------------------------- #
# is_reportable_failure
# --------------------------------------------------------------------------- #
def test_a_zero_progress_refusal_is_a_reportable_failure():
    assert OUT.is_reportable_failure(OUT.BLOCKED_SOURCE, written=0) is True


def test_a_refusal_after_real_progress_is_not_a_reportable_failure():
    """Rows collected before a later refusal are real and are kept; failing
    the job would only obscure what was actually collected."""
    assert OUT.is_reportable_failure(OUT.BLOCKED_SOURCE, written=25) is False


def test_served_is_never_a_reportable_failure():
    assert OUT.is_reportable_failure(OUT.SERVED, written=0) is False


def test_empty_but_valid_is_never_a_reportable_failure():
    """A source that legitimately has nothing to say is not a refusal."""
    assert OUT.is_reportable_failure(OUT.EMPTY_BUT_VALID, written=0) is False
