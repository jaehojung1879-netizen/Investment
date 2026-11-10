"""Outcome-free correction of the existing P2/K7 definitions, no new hypotheses."""
from __future__ import annotations

import bisect
from collections import Counter, defaultdict

from pipeline.kr_corporate_action_events import is_amendment
from research.broad_alpha_screen_v1 import hypotheses as H
from research.corporate_event_readiness_v1.cohort.families import is_subsidiary_report
from research.corporate_event_outcome_v1.shareholder_inputs_v2 import SourceBlocked, dilution_evidence, number, receipt_day

P2, K7 = 'P2_DILUTION', 'K7_DIVIDEND_INCREASE'


def build(index_rows, dividend_rows, snapshots, admission, sessions):
    """Only filing metadata and admitted fiscal/security identities are read.

    `snapshots[date][code]` carries official listedShares. A prior snapshot must
    predate the receipt, even when a declared record date lies in the future.
    Missing fiscal-year evidence blocks the cohort; it is not a selective drop.
    """
    dates, positions = sorted(snapshots), {d: i for i, d in enumerate(sessions)}
    out, drops = [], Counter()

    def snapshot(day):
        i = bisect.bisect_left(dates, day) - 1
        if i < 0:
            return {}
        return snapshots[dates[i]]

    def timed(row, hyp):
        day = receipt_day(row)
        signal = bisect.bisect_right(sessions, day)
        if signal + 1 >= len(sessions):
            return None
        return {'hypothesis': hyp, 'rcept_no': row['rcept_no'], 'corp_code': row['corp_code'],
                'stock_code': row['stock_code'], 'ticker': row['stock_code'] + '.KS',
                'receiptDay': day, 'signalSession': sessions[signal], 'entrySession': sessions[signal + 1],
                'pitGrade': 'DATE_ONLY_CONSERVATIVE', '_entry': signal + 1}

    def common(row, day):
        ticker = row['stock_code'] + '.KS'
        identity = admission['securityIdentities'].get(ticker)
        if not identity or not identity.get('sourceSha256'):
            raise SourceBlocked('SECURITY_IDENTITY_UNQUALIFIED:' + ticker)
        if identity.get('corp_code') != row['corp_code'] or not identity['from'] <= day <= identity['through']:
            raise SourceBlocked('DATED_SECURITY_IDENTITY_UNRESOLVED:' + ticker)
        return identity['securityClass'] == 'COMMON'

    amendments = defaultdict(list)
    for row in index_rows:
        if is_amendment(row.get('report_nm', '')) and not is_subsidiary_report(row.get('report_nm', '')):
            amendments[(row['corp_code'], row.get('family'))].append(row)
    for row in index_rows:
        family, day = row.get('family'), receipt_day(row)
        if family not in ('RIGHTS', 'CB', 'EB', 'BW') or not '2013-01-01' <= day <= H.AS_OF:
            continue
        if is_amendment(row.get('report_nm', '')) or is_subsidiary_report(row.get('report_nm', '')):
            continue
        if row['stock_code'] not in snapshot(day) or not common(row, day):
            continue
        event = timed(row, P2)
        if event is None:
            continue
        amended = False
        for correction in amendments[(row['corp_code'], family)]:
            if day <= receipt_day(correction) < event['signalSession']:
                parent = admission['amendmentLinks'].get(correction['rcept_no'])
                if not parent:
                    raise SourceBlocked('P2_AMENDMENT_CHAIN_UNRESOLVED:' + correction['rcept_no'])
                amended |= parent == row['rcept_no']
        if amended:
            drops['P2_KNOWN_PRE_SIGNAL_AMENDMENT'] += 1
            continue
        event['detail'] = {'family': family, 'dilutionEvidence': dilution_evidence(family)}
        out.append(event)

    own = [r for r in dividend_rows if not is_subsidiary_report(r.get('report_nm', ''))
           and r.get('dividendClass') == '결산배당' and r.get('dividendKind') == '현금배당'
           and r.get('recordDate')]

    def fiscal(row, signal):
        meta = admission['fiscalPeriods'].get(row['rcept_no'])
        if not meta or not meta.get('sourceSha256') or meta.get('knownOn', '9999') >= signal:
            raise SourceBlocked('VERIFIED_FISCAL_PERIOD_MISSING:' + row['rcept_no'])
        return int(meta['fiscalYear'])

    def resolved(original, signal):
        key = (original['corp_code'], original['stock_code'], original['recordDate'])
        versions = [r for r in own if (r['corp_code'], r['stock_code'], r['recordDate']) == key
                    and receipt_day(r) < signal]
        originals = {r['rcept_no'] for r in versions if not r.get('amendment')}
        if len(originals) != 1:
            raise SourceBlocked('DUPLICATE_YEAR_END_ORIGINALS:' + original['rcept_no'])
        chosen = original
        for row in sorted(versions, key=lambda r: r['rcept_no']):
            if row.get('amendment'):
                parent = admission['amendmentLinks'].get(row['rcept_no'])
                if parent not in (original['rcept_no'], chosen['rcept_no']):
                    raise SourceBlocked('DIVIDEND_AMENDMENT_CHAIN_UNRESOLVED:' + row['rcept_no'])
                chosen = row
        return chosen

    for row in sorted(own, key=lambda r: r['rcept_no']):
        day = receipt_day(row)
        if row.get('amendment') or not '2013-01-01' <= day <= H.AS_OF:
            continue
        if row['stock_code'] not in snapshot(day) or not common(row, day):
            continue
        event = timed(row, K7)
        if event is None:
            continue
        signal = event['signalSession']
        fy = fiscal(row, signal)
        current = resolved(row, signal)
        candidates = [r for r in own if r['stock_code'] == row['stock_code'] and not r.get('amendment')
                      and receipt_day(r) < day and fiscal(r, signal) == fy - 1]
        if not candidates:
            drops['K7_NO_PRIOR_FISCAL_YEAR_IN_SOURCE'] += 1
            continue
        if len(candidates) != 1:
            raise SourceBlocked('PRIOR_FISCAL_YEAR_NOT_UNIQUE:' + row['rcept_no'])
        previous = resolved(candidates[0], signal)
        try:
            dps, prior = number(current.get('dpsCommonKrw')), number(previous.get('dpsCommonKrw'))
        except SourceBlocked as exc:
            raise SourceBlocked(str(exc) + ':' + row['rcept_no']) from exc
        if prior <= 0:
            drops['K7_NONPOSITIVE_PRIOR_DPS'] += 1
            continue
        a = snapshot(min(previous['recordDate'], day)).get(row['stock_code'], {}).get('listedShares')
        b = snapshot(min(current['recordDate'], day)).get(row['stock_code'], {}).get('listedShares')
        if not a or not b:
            raise SourceBlocked('PIT_SHARE_COUNT_MISSING:' + row['rcept_no'])
        if not 0.9 <= b / a <= 1.1:
            drops['K7_REGISTERED_SHARE_COMPARABILITY_FILTER'] += 1
            continue
        change = dps / prior - 1
        if change < H.DIVIDEND_CHANGE:
            continue
        event['detail'] = {'dpsChangePct': 100 * change, 'verifiedFiscalYear': fy,
                           'currentVersion': current['rcept_no'], 'previousVersion': previous['rcept_no']}
        out.append(event)
    # Reuse exactly the existing per-issuer H126/H252 overlap convention.
    H.mark_independent(out)
    for event in out:
        event.pop('_entry')
        for h in (126, 252):
            event[f'H{h}Matured'] = positions[event['entrySession']] + h < len(sessions)
    return sorted(out, key=lambda e: (e['hypothesis'], e['entrySession'], e['rcept_no'])), dict(drops)
