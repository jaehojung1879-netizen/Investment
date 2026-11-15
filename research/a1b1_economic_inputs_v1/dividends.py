"""Direct SEIBro ex-date evidence; no record-date inference or share-class guess."""
from datetime import datetime
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def parse_ex_dates(raw):
    if len(raw) > 4 * 1024 * 1024 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('UNSAFE_OR_OVERSIZED_XML')
    tree = ET.fromstring(raw)
    if tree.tag != 'vector':
        raise ValueError('SEIBRO_VECTOR_REQUIRED')
    nodes = tree.findall('./data/result')
    if not tree.get('result', '').isdigit() or int(tree.get('result')) != len(nodes):
        raise ValueError('SEIBRO_COUNT_OR_RESPONSE_ERROR')
    selected, rejected, seen = [], [], set()
    for node in nodes:
        row = {e.tag: e.get('value') for e in node}
        reason = None
        if (row.get('RGT_RACD') != '103' or row.get('RGT_RSN_DTAIL_SORT_CD') != '02'
                or row.get('DT_TPCD') != '03' or row.get('DT_TPNM') != '권리락일'):
            reason = 'NOT_EXPLICIT_CASH_DIVIDEND_EX_DATE'
        try:
            day = datetime.strptime(row.get('STD_DT', ''), '%Y%m%d').date().isoformat()
            record = datetime.strptime(row.get('RGT_STD_DT', ''), '%Y%m%d').date().isoformat()
            if (day > record or row.get('DT_BEGIN_DT') != row.get('STD_DT')
                    or row.get('DT_EXPRY_DT') != row.get('STD_DT')):
                reason = 'DATE_SEMANTICS_CONFLICT'
        except ValueError:
            reason = 'INVALID_OFFICIAL_DATE'
            day = record = None
        if not row.get('ISSUCO_CUSTNO') or not row.get('SHOTN_CD_ISSUIN_NO'):
            reason = 'ISSUER_IDENTITY_MISSING'
        key = (row.get('ISSUCO_CUSTNO'), record, day)
        if key in seen:
            reason = 'DUPLICATE_ISSUER_DISTRIBUTION'
        if reason:
            rejected.append({'row': row, 'reason': reason})
            continue
        seen.add(key)
        selected.append({'issuerId': row['ISSUCO_CUSTNO'], 'issuerShortCode': row['SHOTN_CD_ISSUIN_NO'],
                         'issuerName': row.get('ISSUCO_NM'), 'exDate': day, 'recordDate': record,
                         'exDateSource': 'DIRECT', 'sourcePayloadSha256': hashlib.sha256(raw).hexdigest(),
                         'securityId': None, 'shareClassStatus': 'UNRESOLVED',
                         'sourceVintage': 'CURRENT_REVISED_QUERY_NOT_HISTORICAL_PUBLICATION',
                         'totalReturnStatus': 'BLOCKED_AMOUNT_CLASS_ACTION_COVERAGE_REQUIRED'})
    return {'rows': selected, 'rejected': rejected, 'sourcePayloadSha256': hashlib.sha256(raw).hexdigest()}


def reconcile_decisions(decisions, direct_rows):
    """Identify possible joins, never append '0' to an issuer code to invent a security."""
    matches = []
    for decision in decisions:
        if decision.get('amendment') or decision.get('parseStatus') != 'PARSED':
            continue
        stock = decision.get('stock_code') or ''
        candidates = [r for r in direct_rows if r['issuerShortCode'] == stock[:5]
                      and len(stock) == 6 and r['recordDate'] == decision.get('recordDate')]
        if len(candidates) != 1:
            continue
        source = candidates[0]
        prior = decision.get('exDateCandidate')
        matches.append({'receipt': decision['rcept_no'], 'corpCode': decision['corp_code'],
                        'stockCode': stock, 'recordDate': source['recordDate'],
                        'officialExDate': source['exDate'], 'priorCandidate': prior,
                        'candidateAgreement': None if prior is None else prior == source['exDate'],
                        'issuerSourceSha256': source['sourcePayloadSha256'],
                        'dartSource': decision.get('source'),
                        'status': 'ISSUER_JOIN_CANDIDATE_SHARE_CLASS_CONFIRMATION_REQUIRED'})
    return matches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--decisions', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    pins = json.loads(Path(__file__).with_name('source-qualification.json').read_text())
    direct = []
    for pin in pins['officialExDatePayloads']:
        raw = (args.raw / pin['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != pin['sha256']:
            raise ValueError('OFFICIAL_SOURCE_BYTES_CHANGED')
        direct.extend(parse_ex_dates(raw)['rows'])
    raw = args.decisions.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pins['dividendDecisionsSha256']:
        raise ValueError('DART_DECISIONS_SNAPSHOT_CHANGED')
    decisions = [json.loads(line) for line in gzip.decompress(raw).splitlines()]
    joined = reconcile_decisions(decisions, direct)
    report = {'directIssuerDates': len(direct), 'issuerJoinCandidates': len(joined),
              'previouslyNoDateCandidate': sum(r['priorCandidate'] is None for r in joined),
              'priorCandidateConflicts': sum(r['candidateAgreement'] is False for r in joined),
              'fullyQualifiedEconomicEventIncrease': 0, 'outcomeAuthorized': False, 'joins': joined}
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'joins'}))


if __name__ == '__main__':
    main()
