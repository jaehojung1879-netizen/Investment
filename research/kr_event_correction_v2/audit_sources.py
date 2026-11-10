"""Saved filing/result identity diagnostics only. Never read prices or returns."""
import gzip
import json
from pathlib import Path

from research.corporate_event_outcome_v1.input_pins_v2 import file_hash
from research.corporate_event_outcome_v1.shareholder_inputs_v2 import issuer_cash_dividends
from research.corporate_event_readiness_v1.cohort.families import is_subsidiary_report

ROOT = Path(__file__).resolve().parents[2]
DIV = ROOT / 'research/corporate_event_readiness_v1/cohort/data/dividend-decisions-v1.jsonl.gz'
EVENT = ROOT / 'research/broad_alpha_screen_v1/events-v1.jsonl.gz'


def audit():
    with gzip.open(DIV, 'rt') as stream:
        dividends = list(map(json.loads, stream))
    with gzip.open(EVENT, 'rt') as stream:
        events = list(map(json.loads, stream))
    selected = {'20190724800532', '20190726800709', '20200210800791', '20200309800657',
                '20230208800627', '20230208800675'}
    sample = [r for r in dividends if r['rcept_no'] in selected]
    corrected, flags, blocked = issuer_cash_dividends(sample, {'241560.KS': 'COMMON'})
    assert not blocked and flags['SUBSIDIARY_EXCLUDED'] == 3
    original = {}
    for row in sorted(sample, key=lambda r: r['rcept_no']):
        original[row['recordDate']] = row
    comparisons = [{'recordDate': row['recordDate'], 'exDate': ex,
                    'originalLastReceipt': original[row['recordDate']]['rcept_no'],
                    'originalOverwrittenDps': float(original[row['recordDate']]['dpsCommonKrw']),
                    'correctedOwnCommonDps': row['dps'], 'correctedReceipt': row['rcept_no']}
                   for ex, row in sorted(corrected['241560.KS'].items())]
    by_receipt = {r['rcept_no']: r for r in dividends}
    k7 = [e for e in events if e['hypothesis'] == 'K7_DIVIDEND_INCREASE']
    bad = [e for e in k7 if is_subsidiary_report(by_receipt[e['rcept_no']]['report_nm'])]
    result = json.loads((ROOT / 'research/broad_alpha_screen_v1/result-postoutcome-v1.json').read_text())
    bounds = {}
    for horizon in ('H126', 'H252'):
        mature = [e for e in k7 if e['independent'][horizon] and e[horizon + 'Matured']]
        bad_mature = [e for e in bad if e['independent'][horizon] and e[horizon + 'Matured']]
        accepted = result['hypotheses']['K7_DIVIDEND_INCREASE'][horizon]['slots']
        bounds[horizon] = {'matureInputs': len(mature), 'subsidiaryMatureInputs': len(bad_mature),
                           'acceptedSlots': accepted,
                           'wrongEntityAcceptedSlotsLowerBound': max(0, len(bad_mature) - (len(mature) - accepted))}
    return {'scope': 'FILING_IDENTITY_AND_SAVED_COUNTS_ONLY_NO_HISTORICAL_RETURN_RECALCULATION',
            'sourceSha256': {str(p.relative_to(ROOT)): file_hash(p) for p in (DIV, EVENT)},
            'dividendRows': len(dividends), 'subsidiaryDividendRows': sum(is_subsidiary_report(r.get('report_nm', '')) for r in dividends),
            'K7Rows': len(k7), 'K7DirectSubsidiaryRows': len(bad), 'K7AcceptedContaminationLowerBounds': bounds,
            'actualFilingDpsCorrections': comparisons,
            'returnOrCiCorrectionComputed': False, 'rawBodiesIndependentlyRevalidated': False,
            'sourceAdmission': 'BLOCKED_FULL_SECURITY_FISCAL_ACTION_AND_PORTFOLIO_QUALIFICATION_MISSING'}


if __name__ == '__main__':
    print(json.dumps(audit(), ensure_ascii=False, indent=2, sort_keys=True))
