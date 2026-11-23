"""Prospective MVMA guardrails; NOT part of the sealed Phase 2 execution.

These helpers are opt-in building blocks for a separately authorized future
version. They do not modify, import-run, or rewrite the #358 evidence artifacts.
Do not replace the pinned execute_phase2.py or phase2.py with these helpers
inside the original one-shot experiment.
"""
from __future__ import annotations

import math
from pathlib import Path

from . import phase2 as P2


class FutureExecutionRefused(RuntimeError):
    """A next-version execution would violate one-shot output ownership."""


def claim_future_one_shot(result: Path, monthly: Path, claim: Path) -> Path:
    """Claim a *new* output namespace once, fail-closed even on process crashes.

    The future executor must call this before reading outcome data and must not
    clear the marker after a failure. Claiming a namespace with preexisting
    results or a partial monthly CSV is forbidden. File mode 'x' atomically
    refuses concurrent claim attempts on a local filesystem.
    """
    paths = (Path(result), Path(monthly))
    marker = Path(claim)
    if marker in paths or paths[0] == paths[1]:
        raise FutureExecutionRefused("INVALID_OUTPUT_NAMESPACE")
    if any(path.exists() for path in paths):
        raise FutureExecutionRefused("ONE_SHOT_ALREADY_SPENT: outcome file exists")
    try:
        with marker.open("x", encoding="utf-8") as handle:
            handle.write("CLAIMED_DO_NOT_RETRY_WITHOUT_NEW_AUTHORIZATION\n")
    except FileExistsError as exc:
        raise FutureExecutionRefused("ONE_SHOT_ALREADY_SPENT: claim exists") from exc
    # Recheck after the exclusive claim to catch preexisting/racing artifacts.
    if any(path.exists() for path in paths):
        raise FutureExecutionRefused("ONE_SHOT_ALREADY_SPENT: outcome file appeared")
    return marker


def corrected_dca(rule: str, triggers: list[bool], execs: list[str],
                  spy: dict[str, float], bil: dict[str, float],
                  one_way: float, parked_fraction: float) -> dict:
    """DCA portfolio with a one-way fee on BOTH fresh SPY and BIL purchases.

    A parked-BIL release incurs a BIL sale and a SPY purchase; new money
    incurs a SPY purchase. Matches the sealed accounting convention but fixes
    the missing entry fee when parking in BIL. Synthetic-only tests; NO replay
    of the sealed #358 outcome series.
    """
    if rule not in ("DCA-A", "DCA-B", "DCA-C"):
        raise ValueError("UNKNOWN_DCA_RULE")
    if len(execs) != len(triggers) + 1:
        raise ValueError("EXECUTION_TRIGGER_LENGTH_MISMATCH")
    if not (0.0 <= parked_fraction <= 1.0 and 0.0 <= one_way < 1.0):
        raise ValueError("INVALID_DCA_COST_OR_PARKING")
    equity = cash = 0.0
    fees = 0.0
    flows: list[tuple[str, float]] = []
    parked_shares: list[float] = []
    for k, date in enumerate(execs[:-1]):
        if k:
            prior = execs[k - 1]
            equity *= spy[date] / spy[prior]
            cash *= bil[date] / bil[prior]
        flows.append((date, -1.0))
        deploy = rule == "DCA-A" or bool(triggers[k])
        if deploy:
            # One full new SPY purchase; sell BIL and buy SPY for old cash.
            fee = one_way * (1.0 + 2.0 * cash)
            equity += 1.0 + cash - fee
            cash = 0.0
        else:
            buy_spy = 1.0 - parked_fraction
            buy_bil = parked_fraction
            fee = one_way * (buy_spy + buy_bil)
            equity += buy_spy * (1.0 - one_way)
            cash += buy_bil * (1.0 - one_way)
        fees += fee
        parked_shares.append(cash / (equity + cash))

    prior, end = execs[-2], execs[-1]
    equity *= spy[end] / spy[prior]
    cash *= bil[end] / bil[prior]
    terminal = equity + cash
    flows.append((end, terminal))
    return {"rule": rule, "contributed": len(triggers), "terminalValue": terminal,
            "xirr": P2.xirr(flows), "parkedAtEnd": cash,
            "deploymentRatioAtEnd": equity / terminal,
            "averageParkedShare": sum(parked_shares) / len(parked_shares),
            "costPaid": fees}
