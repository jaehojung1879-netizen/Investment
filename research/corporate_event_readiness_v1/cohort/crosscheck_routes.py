"""Field-level comparison of the two body routes on #320's 13 fixed filings.

Route 1: #320's retained public-viewer bytes (``evidence/*.html.gz``, read by
``filings.load_filing`` with its own hash checks). Route 2: OpenDART
``document.xml`` original document ZIP. Raw bytes differ (container markup);
the claim checked here is only that the parsed terms are identical.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..filings import load_filing, parse_filing
from .bodies import document_body, parse_body
from .dart_client import DartClient

FIELDS = ('family', 'decision_date', 'quantity_common', 'quantity_other', 'issued_shares_common_at_decision',
          'amount_krw', 'purpose', 'contract_amount_krw', 'recent_revenue_krw', 'reported_contract_ratio_pct',
          'revenue_fiscal_year', 'contract_start', 'contract_end', 'expected_execution_start',
          'expected_execution_end')


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--offline', action='store_true')
    args = p.parse_args(argv)
    evidence = Path(__file__).resolve().parents[1] / 'evidence'
    samples = json.loads((evidence / 'filing-samples.json').read_text(encoding='utf-8'))['samples']
    client = DartClient(args.cache, offline=args.offline)
    rows = []
    for sample in samples:
        viewer = parse_filing(load_filing(evidence, sample), sample)
        raw, info = document_body(client, sample['rcept_no'])
        api = parse_body(raw, sample)
        diff = {k: [viewer.get(k), api.get(k)] for k in FIELDS if viewer.get(k) != api.get(k)}
        rows.append({'rcept_no': sample['rcept_no'], 'family': viewer.get('family'),
                     'viewerSha256': sample['sha256'], 'documentXmlBodySha256': info['bodySha256'],
                     'rawBytesEqual': sample['sha256'] == info['bodySha256'],
                     'parsedFieldsEqual': not diff, 'differences': diff})
    report = {'fields': list(FIELDS), 'compared': len(rows),
              'parsedFieldsEqual': sum(r['parsedFieldsEqual'] for r in rows),
              'rawBytesEqual': sum(r['rawBytesEqual'] for r in rows), 'rows': rows}
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('compared', 'parsedFieldsEqual', 'rawBytesEqual')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
