"""Shared exit-semantics vocabulary for collectors reading an external source.

WHY THIS EXISTS. `collect_kr_investor_flow.py` and `collect_kr_short_selling.py`
each read `data.krx.co.kr`'s public statistics portal, and both had the same
defect: a run refused by the source on its very first call still printed a
summary and returned exit code 0. Measured directly on real GitHub Actions
runs (2026-09-24): the investor-flow collector logged
`호출 0 · 수집 0건 · 샤드 0개 변경 · 종료 사유 REFUSED: HTTP 400: b'LOGOUT'`
and the workflow step still showed green — a source refusal read exactly
like a normal "nothing left to do" completion. A collector that cannot tell
these apart cannot be trusted to report its own health, so this module gives
every collector in this repository one shared vocabulary for the difference
rather than a bespoke string per source.

THE SIX STATES ANSWER TWO DIFFERENT QUESTIONS. Did the source answer at all
(`SERVED`/`EMPTY_BUT_VALID` vs. the four refusal states), and if it refused,
was that refusal about who's asking (`AUTH_REQUIRED`), what's being asked
for (`BLOCKED_SOURCE`), the shape of the answer (`SCHEMA_CHANGED`), or
whether the request even reached the source (`NETWORK_ERROR`). Collapsing
these into one boolean "worked/didn't" is the exact same defect
`AGENTS.md`'s vendor-refusal invariants already warn against one level up:
different refusals have different fixes, and merging them loses the ability
to tell which fix is needed.

A REFUSAL NEVER READS AS SUCCESS WHEN IT MADE ZERO PROGRESS. `run_outcome`
classifies a whole run from its `stop_reason` string, `calls` made and
`written` rows produced. When the run made no progress AT ALL and the stop
reason is a refusal, `is_reportable_failure` says so — the caller is
expected to return a non-zero exit code, which stops the GitHub Actions
step (and, by the workflow's own default behaviour, the commit-and-push
step after it) rather than committing an empty manifest that looks like a
completed collection. A run that already wrote real rows before hitting a
refusal keeps its exit code 0: the rows it wrote are real and worth
keeping, and failing that job would only make it harder to see what was
collected before the source cut it off.
"""
from __future__ import annotations

SERVED = "SERVED"
EMPTY_BUT_VALID = "EMPTY_BUT_VALID"
BLOCKED_SOURCE = "BLOCKED_SOURCE"
AUTH_REQUIRED = "AUTH_REQUIRED"
SCHEMA_CHANGED = "SCHEMA_CHANGED"
NETWORK_ERROR = "NETWORK_ERROR"

REFUSAL_OUTCOMES = frozenset({BLOCKED_SOURCE, AUTH_REQUIRED, SCHEMA_CHANGED, NETWORK_ERROR})

_PROGRESS_STOP_REASONS = frozenset(
    {"WORK_LIST_EXHAUSTED", "CALL_BUDGET_SPENT", "TIME_BUDGET_SPENT"})


def classify_refusal(message: str) -> str:
    """One of the four refusal outcomes, from a `Refused` exception's message.

    Pattern matching on a raw error string is a coarse instrument, so this
    stays conservative: anything not clearly about authorization, schema, or
    the network defaults to `BLOCKED_SOURCE` — "the source declined to serve
    this" — rather than guessing a more specific reason it cannot support.
    """
    text = str(message)
    lowered = text.lower()
    if "401" in text or "unauthorized" in lowered:
        return AUTH_REQUIRED
    if "not json" in lowered or "payload was" in lowered:
        return SCHEMA_CHANGED
    network_tokens = ("timeout", "timed out", "connection", "urlerror",
                      "gaierror", "socket", "reset by peer", "name or service")
    if any(token in lowered for token in network_tokens):
        return NETWORK_ERROR
    return BLOCKED_SOURCE


def run_outcome(*, stop_reason: str, calls: int, written: int) -> str:
    """Classify one collector run from its own stop reason and progress.

    `calls`/`written` are THIS RUN's counts, never the cumulative done-ledger
    size — a run that made zero progress because the source refused every
    call must never read the same as a run that made zero progress because
    the work list was already empty.
    """
    if stop_reason.startswith("REFUSED:"):
        return classify_refusal(stop_reason[len("REFUSED:"):])
    if stop_reason in _PROGRESS_STOP_REASONS:
        if calls > 0 and written == 0:
            return EMPTY_BUT_VALID
        return SERVED
    # An unrecognised stop reason is never read as SERVED: a collector that
    # invents a new stop reason without teaching this function about it
    # should fail loudly, not silently report a healthy run.
    return BLOCKED_SOURCE


def is_reportable_failure(outcome: str, *, written: int) -> bool:
    """True when a caller should exit non-zero rather than report success.

    Only a refusal that produced zero rows THIS RUN is a reportable
    failure — real rows collected before a later refusal are still real and
    are not thrown away by failing the job that collected them.
    """
    return outcome in REFUSAL_OUTCOMES and written == 0
