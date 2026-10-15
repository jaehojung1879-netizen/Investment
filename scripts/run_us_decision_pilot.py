"""Reproduce the current, outcome-free refusal of US_DECISION_PILOT_V1.

No override flag: a renamed copy of sealed prices does not resolve the owner's
input-use restriction. The separate computation core is tested on synthetic data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import us_decision_pilot as P  # noqa: E402

PROTOCOL = 'docs/us-decision-pilot-v1-protocol.json'
STRATEGIES = ('B0_SPY', 'B1_PRICE', 'B2_MULTIFACTOR', 'B3_GATED_PRICE', 'B3_GATED_MULTIFACTOR',
              'FORCED_5_PRICE_DIAGNOSTIC', 'FORCED_5_MULTIFACTOR_DIAGNOSTIC', 'B2_PLUS_VALUE')
METRICS = ('cagr', 'annualizedCagrDifferenceVsSPY', 'mdd', 'annualVolatility', 'sharpe',
           'twoWayTurnover', 'tradingCostInitialCapital', 'meanNames', 'meanCash')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(root=ROOT):
    """Read contracts and source MANIFEST only; never open a price/result payload."""
    root = Path(root)
    protocol = json.loads((root / PROTOCOL).read_bytes())
    if protocol['id'] != P.STUDY or protocol['coreCodeSha256'] != sha(root / 'pipeline/us_decision_pilot.py'):
        raise ValueError('PILOT_PROTOCOL_OR_CODE_CHANGED')
    if protocol['orchestrationCodeSha256'] != sha(root / 'scripts/run_us_decision_pilot.py'):
        raise ValueError('PILOT_ORCHESTRATION_CHANGED')
    for path, expected in protocol['protectionSources'].items():
        if sha(root / path) != expected:
            raise ValueError('PROTECTION_SOURCE_CHANGED:' + path)
    manifest = json.loads((root / 'data/research/us-dual-benchmark-v1/manifest.json').read_bytes())
    csv_path = 'data/research/us-dual-benchmark-v1/spy-qqq-total-return.csv.gz'
    reason = 'SEALED_INPUT_READ_SCOPE_UNRESOLVED'
    return {
        'id': P.STUDY, 'evidenceClass': P.EVIDENCE, 'verdict': 'NOT ESTIMABLE',
        'executionState': 'NOT_EXECUTED', 'newComparisonBudgetConsumed': False,
        'realOutcomeReads': 0, 'sealedResultReads': 0, 'remoteLockWrites': 0,
        'scopeResolution': {'status': 'PENDING_OWNER_CLARIFICATION', 'reason': reason,
            'useGrant': protocol['sourceScope']['ownerUseGrant'],
            'restriction': protocol['sourceScope']['ownerRestriction'],
            'assumption': protocol['sourceScope']['conservativeApplication']},
        'sourceMetadataOnly': {'benchmarkDerivativePath': csv_path,
            'declaredSha256NotPayloadVerified': manifest['files'].get(csv_path),
            'builtFrom': manifest['builtFrom'],
            'withheld': 'Exported replay-v16 prices are not treated as an independent unsealed source'},
        'strategies': {s: {'status': 'NOT_ESTIMABLE', 'reason': reason,
                          'metrics': {k: None for k in METRICS}, 'yearlyPerformance': None} for s in STRATEGIES},
        'selectionDiagnostics': {str(h): {'status': 'NOT_ESTIMABLE', 'rankIC': None,
            'topGroupSpread': None, 'incrementB2VsB1': None, 'ablation': None} for h in P.HORIZONS},
        'annualMissingness': {'status': 'NOT_MEASURED', 'reason': 'NO_STUDY_INPUT_READ', 'years': None},
        'mostUsefulFactor': None,
        'gatedPortfolioAdditionalConstraint': 'No verified PIT expected-net-excess calibration for B1/B2; a rank is not a return forecast; missing forecast is not a measured all-cash strategy',
        'currentCandidates': {'status': 'CURRENT_CANDIDATES_NOT_VERIFIED', 'candidates': [],
            'requiredInputs': ['current completed-session prices with action basis',
                'current dated membership and sectors', 'strictly visible PIT filings',
                'score-specific expected-net-excess evidence for investable candidates']},
        'nextSingleAction': 'Clarify whether the explicit existing-price/PIT use grant permits READ-ONLY replay-v16 price reuse; otherwise supply a legitimately independent permitted panel. Neither authorizes P4 or relaxes MF1 admission.',
        'protocolSha256': sha(root / PROTOCOL),
        'promotionEligible': False, 'productionEffect': 'NONE', 'publicPricePayloads': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--csv', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.report.exists() or args.csv.exists():
        raise ValueError('OUTPUT_EXISTS_NO_OVERWRITE')
    result = build()
    with args.report.open('x') as out:
        json.dump(result, out, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        out.write('\n')
    with args.csv.open('x', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=['strategy', 'status', *METRICS, 'reason'])
        writer.writeheader()
        for strategy, row in result['strategies'].items():
            writer.writerow({'strategy': strategy, 'status': row['status'], **row['metrics'], 'reason': row['reason']})
    print(json.dumps({'verdict': result['verdict'], 'executionState': result['executionState'],
                      'realOutcomeReads': result['realOutcomeReads']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
