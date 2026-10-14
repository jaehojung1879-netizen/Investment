"""Outcome-blind candidate-price recovery. Never modifies a sealed input store.

Coverage is observation existence, not a total-return or terminal-economics claim.
A name corroboration is explicitly weaker than permanent security identification.
Observations of different sources/bases remain separate; no close-series splicing.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
import hashlib
import io
import json
import math
from pathlib import Path
import re
import time

VERSION = 'US_DEPARTED_PUBLIC_PRICE_CANDIDATES_V1'
# Entity changes/reorganizations cannot be proved from a ticker/name CSV.
IDENTITY_HOLDS = {'AGN', 'IGT', 'CHK', 'BTU', 'NE', 'GCI', 'CTRA', 'S'}
# Explicit reviewed issuer-name abbreviations, NOT ticker/price-series rename joins.
NAME_ALIASES = {
    'CA': {('ca', 'ca technologies')},
    'CDAY': {('ceridian', 'ceridian hcm')},
    'DV': {('devry', 'devry education group')},
    'HAR': {('harman international', 'harman international industries')},
    'HOT': {('starwood hotels resorts', 'starwood hotels resorts worldwide')},
    'JCP': {('penney', 'j c penney')},
    'RDC': {('rowan cos', 'rowan companies')},
}
BASIS = {
    'A': 'BACK_ADJUSTED_OHLCV_WIKI_FIRST_YAHOO_FALLBACK',
    'D': 'YAHOO_OHLC_WITH_SEPARATE_ADJ_CLOSE',
    'E': 'YFINANCE_CLOSE_ROUNDED_2DP_UNPINNED_ADJUSTMENT_DEFAULT',
    'F': 'YAHOO_OHLC_WITH_SEPARATE_ADJ_CLOSE',
    'G': 'UNVERIFIED_PROVIDER_AND_ADJUSTMENT',
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def normalized_name(name):
    name = re.sub(r'\([^)]*\)', '', name.lower())
    tokens = re.findall(r'[a-z0-9]+', name)
    excluded = {'inc', 'incorporated', 'corp', 'corporation', 'co', 'company',
                'ltd', 'limited', 'plc', 'the', 'holdings', 'holding'}
    return ' '.join(t for t in tokens if t not in excluded)


def parse_csv(raw, sessions):
    """Quarantine invalid/duplicate dates. Missing volume remains None, never zero."""
    table = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    fields = {str(k).strip().lower().replace(' ', '_'): k for k in (table.fieldnames or [])}
    if 'date' not in fields or 'close' not in fields:
        raise ValueError('NOT_A_DAILY_PRICE_CSV')
    originals = list(table)
    dates = [str(r.get(fields['date'], '')).strip() for r in originals]
    slash = [v for v in dates if '/' in v]
    us_mdy = bool(slash) and all(re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}', v) and 1 <= int(v.split('/')[0]) <= 12 for v in slash) and any(int(v.split('/')[1]) > 12 for v in slash)
    rows, invalid, seen, duplicate_dates = {}, [], set(), set()
    raw_count, zero_volume = 0, 0
    for line, original in enumerate(originals, 2):
        raw_count += 1
        try:
            day = str(original[fields['date']]).strip()[:10]
            if '/' in day:
                if not us_mdy: raise ValueError('AMBIGUOUS_SLASH_DATE_FORMAT')
                day = datetime.strptime(day, '%m/%d/%Y').date().isoformat()
            if date.fromisoformat(day).isoformat() != day or day not in sessions:
                raise ValueError('NON_SESSION_OR_INVALID_DATE')
            if day in seen:
                duplicate_dates.add(day)
            seen.add(day)
            values = {}
            for name in ('open', 'high', 'low', 'close', 'volume', 'adj_close'):
                text = original.get(fields.get(name, ''))
                value = None if text in (None, '', 'null', 'NaN', 'nan') else float(text)
                if value is not None and (not math.isfinite(value) or value < 0 or (name != 'volume' and value == 0)):
                    raise ValueError('NONFINITE_OR_NONPOSITIVE_PRICE_OR_NEGATIVE_VOLUME')
                values[name] = value
            if values['close'] is None:
                raise ValueError('MISSING_CLOSE')
            if all(values[k] is not None for k in ('open', 'high', 'low')):
                if values['low'] > min(values['open'], values['close']) + 1e-7 or values['high'] < max(values['open'], values['close']) - 1e-7:
                    raise ValueError('OHLC_INCONSISTENT')
            if values['volume'] == 0:
                zero_volume += 1
            rows[day] = values
        except (ValueError, TypeError, KeyError) as exc:
            invalid.append({'line': line, 'reason': str(exc), 'date': original.get(fields['date'])})
    # Even identical duplicates are not silently accepted as distinct observations.
    for day in duplicate_dates:
        rows.pop(day, None)
    ordered = sorted(rows)
    expected = sorted(d for d in sessions if ordered and ordered[0] <= d <= ordered[-1])
    return rows, {'dateFormat': 'CONFIRMED_US_MDY' if us_mdy else 'ISO', 'rawFields': list(table.fieldnames or []), 'rawRows': raw_count, 'validRows': len(rows), 'first': ordered[0] if ordered else None,
                  'last': ordered[-1] if ordered else None, 'duplicateDates': sorted(duplicate_dates),
                  'invalidRows': invalid, 'zeroVolumeRows': zero_volume,
                  'volumeMissingRows': sum(v['volume'] is None for v in rows.values()),
                  'expectedSessionsInsideObservedSpan': len(expected),
                  'gapSessionsInsideObservedSpan': sorted(set(expected) - set(rows))}


def coverage_state(expected, observed):
    covered = set(expected) & set(observed)
    return ('FULL' if expected and len(covered) == len(expected) else 'PARTIAL' if covered else 'NONE'), covered


def compare_levels(left, right):
    """Same-date level ratios only. No time-difference, label, or forward-return read."""
    days = sorted(set(left) & set(right))
    ratios = sorted(left[d] / right[d] for d in days if left[d] > 0 and right[d] > 0)
    if not ratios:
        return {'overlapSessions': 0, 'state': 'NO_OVERLAP'}
    median = ratios[len(ratios) // 2]
    deviations = sorted(abs(v / median - 1) for v in ratios)
    p95 = deviations[min(len(deviations) - 1, int(.95 * len(deviations)))]
    return {'overlapSessions': len(ratios), 'first': days[0], 'last': days[-1],
            'medianSameDateLevelRatio': median, 'p95RelativeRatioDeviation': p95,
            'state': 'LEVEL_SHAPE_CORROBORATED' if p95 <= .01 else 'BASIS_OR_VALUE_DISAGREEMENT',
            'spliceAuthorized': False, 'independentProviderConfirmed': False}


def acquire(urls, directory, *, fetch, delay=.2, budget=500, sleep=time.sleep, now=None):
    """Explicit pinned HTTPS URLs; bounded sequential acquisition with no aggressive retry."""
    directory = Path(directory)
    if (directory / 'acquisition.json').exists():
        raise ValueError('ACQUISITION_MANIFEST_ALREADY_EXISTS')
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for item in urls[:budget]:
        url = item['url']
        if not re.match(r'^https://raw\.githubusercontent\.com/[^/]+/[^/]+/[0-9a-f]{40}/', url):
            raise ValueError('UNPINNED_OR_UNSUPPORTED_SOURCE_URL')
        try:
            status, raw = fetch(url)
        except Exception as exc:
            records.append({**item, 'error': type(exc).__name__, 'stopped': True})
            break
        record = {**item, 'status': status, 'bytes': len(raw), 'acquiredAt': now() if now else None}
        if status == 200:
            if len(raw) > 5 * 1024 * 1024:
                record['error'] = 'PER_FILE_BYTE_BUDGET';records.append(record);break
            object_name = digest(raw) + '.csv'
            path = directory / object_name
            if path.exists() and path.read_bytes() != raw:
                raise ValueError('CONTENT_ADDRESS_COLLISION')
            path.write_bytes(raw)
            record.update(sha256=digest(raw), object=object_name)
            if item.get('expectedSha256') and digest(raw) != item['expectedSha256']:
                record['revisionMismatch'] = True
        records.append(record)
        if record.get('revisionMismatch') or status in (401, 403, 429) or status >= 500:
            break
        sleep(delay)
    (directory / 'acquisition.json').write_bytes(canonical({'version': VERSION, 'records': records}))
    return records
