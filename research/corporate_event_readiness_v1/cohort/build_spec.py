"""Freeze the preregistration CANDIDATE for A1/B1 with exact code and input hashes.

Writes ``kr-corporate-information-events-v1-candidate.json``. Status stays
PROPOSED_NOT_REGISTERED: this file is the object an Owner approval would pin,
not the approval. Statistical contract text follows the Owner's draft in
Issue #292 comment 6671600416 (C0/C1/C2/D) and does not loosen it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CODE = ['research/corporate_event_readiness_v1/filings.py',
        *[f'research/corporate_event_readiness_v1/cohort/{n}' for n in (
            '__init__.py', 'dart_client.py', 'families.py', 'identity.py', 'collect_index.py',
            'collect_issuers.py', 'bodies.py', 'events.py', 'power.py', 'run_cohort.py',
            'candidate_signal.py', 'crosscheck_ds005.py', 'crosscheck_routes.py', 'build_spec.py')],
        'pipeline/kr_corporate_action_events.py', 'pipeline/dart_ownership_universe.py',
        'pipeline/replay_calendar.py']
INPUTS = ['issuer-index-rows-v1.jsonl.gz', 'issuer-universe-v1.json', 'issuer-index-manifest-v1.json',
          'cohort-events-v1.jsonl.gz', 'cohort-funnel-v1.json', 'body-receipts-v1.json.gz', 'inputs-v1.json',
          'ds005-crosscheck-v1.json', 'document-route-crosscheck-v1.json']


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def spec(data_dir: Path) -> dict:
    return {
        'studyId': 'kr-corporate-information-events-v1',
        'status': 'PROPOSED_NOT_REGISTERED',
        'evidenceClassIfExecuted': 'EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY',
        'contractSource': 'Issue #292 comment 6671600416 (Owner draft C0/C1/C2/D), unchanged in substance',
        'hypothesisFamily': {
            'slots': ['A1_CAPITAL_ALLOCATION_CANCELLATION', 'B1_LARGE_SUPPLY_CONTRACT', 'H3_INSIDER_NOT_RUN_P_EQUALS_1'],
            'correction': 'Holm FWER 0.05 over 3 slots; simultaneous two-sided 98.333% interval lower bound > 0',
        },
        'A1': {'event': 'Original receipt of a common-share cancellation decision (주식소각결정) or a buyback '
                        '(자기주식취득결정/신탁) whose FILED purpose states cancellation; amendments are later states.',
               'comparatorA2': 'Buyback or trust with no cancellation stated (descriptive matched contrast only).'},
        'B1': {'event': 'Original 단일판매·공급계약체결 whose FILED contract amount / FILED recent revenue >= 10%, '
                        'amount, revenue and ratio all stated; CONTRACT_RATIO_MISMATCH excluded.'},
        'population': {'identity': 'PIT KOSPI Top300 monthly snapshot strictly before the receipt day',
                       'fullKospiLiquidityUniverse': 'SOURCE_BLOCKED (KRX portal LOGOUT); not substituted'},
        'timing': {'pitGrade': 'DATE_ONLY_CONSERVATIVE',
                   'signal': 'close of first KR session strictly after receipt day',
                   'entry': 'close of the following session', 'pitExact': 0},
        'independence': 'one event per issuer per hypothesis per H window from entry (embargo H126 / H252)',
        'primaryEstimand': 'calendar-time research book: mean daily net difference vs funded ex-ante-beta-matched '
                           'ETF(069500.KS)+KRW-cash book; delta126 = 126*alpha; MEE 3pp (H126), 4pp (H252, secondary)',
        'inference': {'primary': 'synchronized moving-block bootstrap, block 252 sessions (H126) / 504 (H252), '
                                 'B=9999, seed 319320', 'secondary': 'Bartlett HAC lag 125/251; issuer x entry-week '
                                 'two-way clustered event regressions'},
        'decisionOrder': ['SOURCE_BLOCKED', 'REJECT_ECONOMIC_EFFECT (upper bound < MEE) / FAIL_COST_ROBUSTNESS '
                          '(2x cost point <= 0)', 'DEVELOPMENT_SUPPORT (all gates)', 'UNCERTAIN'],
        'fixedSplits': {'valueUp': '2024-02-26', 'recentConcentration': ['2025-01-01', '2026-12-31']},
        'blockedBeforeExecution': [
            'investable KRW cash series (BOK proxy is not a payoff)',
            'stock total-return basis: KRX bars carry no dividends; dividend lineage per name',
            'terminal economics for names delisted inside a holding window',
            'PIT industry labels outside the Top120 v4 reconstruction',
            'pre-event residual volatility and design effect for the final MDE (needs a price read)',
            'investor account, tax and cost contract shared with #317 economics',
        ],
        'codeSha256': {p: sha(ROOT / p) for p in CODE},
        'inputSha256': {n: sha(data_dir / n) for n in INPUTS if (data_dir / n).exists()},
        'approvalRequest': {
            'phrase': 'APPROVE KR_PHASE_D_NEW_AXIS_EXCEPTION kr-corporate-information-events-v1 <specSha256>',
            'scope': 'ONE historical execution of A1 and B1 over the frozen cohort, after every blockedBeforeExecution '
                     'item is admitted by a separate source PR and an independent non-author audit; no re-run, '
                     'no threshold or window change, no Atlas/Phase C reuse',
        },
    }


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--data', type=Path, default=HERE / 'data')
    args = p.parse_args()
    body = spec(args.data)
    text = json.dumps(body, ensure_ascii=False, indent=1, sort_keys=True) + '\n'
    out = HERE / 'kr-corporate-information-events-v1-candidate.json'
    out.write_text(text, encoding='utf-8')
    print(out.name, hashlib.sha256(text.encode()).hexdigest())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
