"""Read-only documentation checks, NOT Claude's missing forensic/backtest code.

Default: original bytes + arithmetic of ALREADY published aggregate returns.
--input-metadata: additionally count filing metadata only; never load prices,
construct factors/labels, simulate a portfolio, fit a model or touch a lock.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify(input_metadata=False):
    manifest = json.loads((HERE / 'evidence-manifest.json').read_bytes())
    for name, expected in manifest['frozenFiles'].items():
        actual = (ROOT / name).read_bytes()
        original = subprocess.check_output(['git', 'show', manifest['baselineHead'] + ':' + name], cwd=ROOT)
        if sha(actual) != expected or sha(original) != expected:
            raise ValueError('FROZEN_BYTES_CHANGED:' + name)
    review_bytes = (HERE / 'review-5541660596.json').read_bytes()
    review = json.loads(review_bytes)
    if sha(review_bytes) != manifest['review']['archiveSha256'] or sha(review['body'].encode()) != manifest['review']['bodySha256']:
        raise ValueError('REVIEW_ARCHIVE_CHANGED')
    if sha(Path(__file__).read_bytes()) != manifest['partialVerifier']['sha256']:
        raise ValueError('DOCUMENTATION_VERIFIER_CHANGED')
    result = json.loads((ROOT / 'docs/us-decision-pilot-v1/result.json').read_bytes())
    strategies = result['strategies']
    spy, b2, forced = (strategies[k] for k in ('B0_SPY', 'B2_MULTIFACTOR', 'FORCED_5_MULTIFACTOR_DIAGNOSTIC'))
    log_gap = lambda a, b: 100 * (math.log1p(a) - math.log1p(b))
    checked = {'b2MinusSpyAnnualLogPp': log_gap(b2['cagr'], spy['cagr']),
        'spyCostRemovalAnnualLogPp': log_gap(spy['grossCagr'], spy['cagr']),
        'b2CostAnnualLogPp': log_gap(b2['cagr'], b2['grossCagr']),
        'year2024B2MinusSpyReturnPp': 100 * (b2['yearlyReturns']['2024'] - spy['yearlyReturns']['2024']),
        'year2024B2MinusSpyLogPp': log_gap(b2['yearlyReturns']['2024'], spy['yearlyReturns']['2024']),
        'forcedB2MinusBroadB2NetCagrPp': 100 * (forced['cagr'] - b2['cagr']),
        'forcedB2IncrementalCostDragPp': 100 * (forced['annualizedCostDrag'] - b2['annualizedCostDrag'])}
    for name, value in checked.items():
        if not math.isclose(value, manifest['aggregateArithmeticChecked'][name], abs_tol=1e-10):
            raise ValueError('AGGREGATE_ARITHMETIC_CHANGED:' + name)
    weekly = {r['date']: r['completeCases'] for r in result['weeklyAvailability']}
    if {day: weekly[day] for day in manifest['weeklyCompleteCasesChecked']} != manifest['weeklyCompleteCasesChecked']:
        raise ValueError('FROZEN_WEEKLY_COUNTS_CHANGED')
    if input_metadata:
        sys.path.insert(0, str(ROOT))
        from scripts import run_us_decision_pilot as S
        from pipeline import us_cash_profitability as CP
        S.verify_contract()  # pinned original helper bytes BEFORE filing metadata reads
        raw, shards = S.load_filings()  # ONLY ledger/fundamentals/us, no price/result reader
        rows = [r for records in raw.values() for r in records]
        late = [r for r in rows if '2026-10-07' <= str(r.get('collectedAt', ''))[:10] <= '2026-10-10']
        visible = [r for r in late if CP.visible_day(r) and CP.visible_day(r).isoformat() < '2026-09-14']
        june = lambda r: r.get('form') == '10-Q' and str(r.get('periodEnd', '')).startswith('2026-06')
        metadata = {'rawRecords': len(rows), 'shards': len(shards), 'collected20261007Through10': len(late),
            'emptyBalanceSheet': sum(not (r.get('statements') or {}).get('bs') for r in late),
            'visibleStrictlyBeforeCutoff': len(visible), 'june10QAllLateRecords': sum(map(june, late)),
            'june10QVisibleBeforeCutoff': sum(map(june, visible)),
            'june30Exact10Q': sum(r.get('form') == '10-Q' and r.get('periodEnd') == '2026-06-30' for r in late)}
        if metadata != manifest['inputMetadataChecked']['counts']:
            raise ValueError('INPUT_METADATA_COUNTS_CHANGED')
        checked['inputMetadata'] = metadata
    print(json.dumps({'scope': 'FROZEN_BYTES_AGGREGATE_ARITHMETIC_AND_OPTIONAL_FILING_METADATA_ONLY',
                      'newPortfolioSimulations': 0, 'forwardPriceReads': 0, 'checked': checked}, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-metadata', action='store_true')
    verify(parser.parse_args().input_metadata)
