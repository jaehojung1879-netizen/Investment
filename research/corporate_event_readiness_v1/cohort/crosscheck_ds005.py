"""Independent field check: body-parsed buyback terms vs OpenDART DS005 structured values.

DS005 ``tsstkAqDecsn`` serves DART's own structured fields for 2015+ buyback
decisions. Joining on rcept_no, compares the common-share quantity and the
purpose class used by A1/A2 classification. Disagreements are listed, never
silently resolved in either direction.
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from .dart_client import DartClient
from .events import purpose_class


def num(text) -> str | None:
    if not text or text.strip() in ('-', ''):
        return None
    value = text.replace(',', '').strip()
    return value if value.isdigit() else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--events', type=Path, required=True, help='cohort-events-v1.jsonl.gz')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--offline', action='store_true')
    args = p.parse_args(argv)
    client = DartClient(args.cache, offline=args.offline)
    events = [json.loads(line) for line in gzip.open(args.events, 'rt', encoding='utf-8')]
    buybacks = [e for e in events if e['family'] == 'BUYBACK' and e['receiptDay'] >= '2015-01-01'
                and e.get('terms')]
    by_corp: dict[str, list[dict]] = {}
    for e in buybacks:
        by_corp.setdefault(e['corp_code'], []).append(e)
    tally, mismatches, missing = Counter(), [], []
    for corp in sorted(by_corp):
        payload, _ = client.get_json('tsstkAqDecsn.json', {'corp_code': corp, 'bgn_de': '20150101',
                                                            'end_de': '20261031'})
        ds = {row['rcept_no']: row for row in payload.get('list', [])}
        for e in by_corp[corp]:
            row = ds.get(e['rcept_no'])
            if row is None:
                missing.append(e['rcept_no'])
                tally['NOT_IN_DS005'] += 1
                continue
            q_ok = num(row.get('aqpln_stk_ostk')) == (e['terms'].get('quantity_common') or None)
            p_ok = (purpose_class(row.get('aq_pp')) == 'CANCELLATION_STATED') == \
                   (purpose_class(e['terms'].get('purpose')) == 'CANCELLATION_STATED')
            tally['QUANTITY_MATCH' if q_ok else 'QUANTITY_MISMATCH'] += 1
            tally['CANCELLATION_FLAG_MATCH' if p_ok else 'CANCELLATION_FLAG_MISMATCH'] += 1
            if not (q_ok and p_ok):
                mismatches.append({'rcept_no': e['rcept_no'], 'bodyQuantity': e['terms'].get('quantity_common'),
                                   'ds005Quantity': row.get('aqpln_stk_ostk'), 'bodyPurpose': e['terms'].get('purpose'),
                                   'ds005Purpose': row.get('aq_pp')})
    report = {'compared': len(buybacks), 'issuers': len(by_corp), 'tally': dict(sorted(tally.items())),
              'mismatches': mismatches, 'notInDs005': sorted(missing), 'apiCalls': client.calls}
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('compared', 'issuers', 'tally')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
