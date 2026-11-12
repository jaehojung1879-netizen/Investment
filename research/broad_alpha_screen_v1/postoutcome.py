"""POST-OUTCOME diagnostic rerun of broad-alpha-screen-v1. It can never change, rescue or replace result-v1.json.

Designed after the registered result was read (the H252 numbers of every blocked book had been seen), so
everything it produces is EXPLORATORY_POST_OUTCOME. One thing differs from the registered run: a held name that
is suspended on its exit session and never trades again before its prices end is classified as an unresolved
terminal (excluded from the primary path, kept at -100% in the stress path), exactly like a name whose prices end
inside the window. The registered preflight only looked inside the window; the engine keeps an untradable name
past its exit and then finds no price. No hypothesis, threshold, horizon, cost or verdict rule is changed.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from research.corporate_event_outcome_v1 import engine as E
from research.corporate_event_outcome_v1 import power_calibration as PC

from . import screen as S

RESULT = S.HERE / 'result-postoutcome-v1.json'
OWNER_INSTRUCTION = '하고싶은거 다 해봐 (Owner, session conversation 2026-11-10, after the two pending decisions were listed)'
_registered_state = S.window_state


def window_state(slot: E.Slot, market: dict) -> tuple[str, str | None]:
    kind, first_missing = _registered_state(slot, market)
    if kind != 'PRICED':
        return kind, first_missing
    ses, lv = market['sessions'], market['levels'].get(slot.ticker, {})
    tradable = market['tradable'].get(slot.ticker, ())
    for day in ses[slot.exit:]:
        if day not in lv:
            return 'TERMINAL_UNRESOLVED', day        # still frozen when the prices end
        if day in tradable:
            return 'PRICED', None
    return 'PRICED', None


def main(argv=None) -> int:
    prices = Path((argv or sys.argv[1:])[0])
    if not S.RESULT.is_file():
        raise SystemExit('REFUSED: the registered result does not exist; this is a post-outcome diagnostic only')
    if RESULT.exists():
        raise SystemExit('REFUSED: post-outcome result already exists')
    _, problems = S.verify_contract(prices)
    if problems:
        raise SystemExit(f'REFUSED: {problems}')
    registered_sha = S.sha(S.RESULT)
    events = S.load_events()
    market = S.assemble(prices, events)
    S.window_state = window_state
    try:
        result = S.evaluate(events, market, PC.ticker_industry())
    finally:
        S.window_state = _registered_state
    result.update(evidenceClass='EXPLORATORY_POST_OUTCOME', studyId='broad-alpha-screen-v1-postoutcome',
                  registeredResultSha256=registered_sha, contractSha256=S.sha(S.CONTRACT),
                  ownerInstruction=OWNER_INSTRUCTION,
                  cannot='rescue, reclassify or reopen the registered verdicts; NOT_CONFIRMATORY',
                  onlyChange='suspended-at-exit names whose prices end before they trade again are unresolved terminals')
    tmp = RESULT.with_suffix('.tmp')
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True, default=float) + '\n', encoding='utf-8')
    os.replace(tmp, RESULT)
    assert S.sha(S.RESULT) == registered_sha
    print('written', S.sha(RESULT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
