"""PIT-NOT industry labels for cohort issuers outside the v4 Top120 reconstruction (outcome-free).

v4 labels come from KRX KIND change events (blocked from this environment). OpenDART
``company.json`` gives each issuer's CURRENT KSIC code only. This module extends coverage
with a label that is explicitly NOT point-in-time:

* the KSIC code -> v4 research-industry map is LEARNED from the Top120 overlap (names that
  have both a v4 label and a DART code) by longest-prefix majority; nothing is hand-written;
* its accuracy is MEASURED by leave-one-out on that overlap and published per answering
  level, so a consumer can see how much to trust an outside-Top120 label;
* every extended label carries ``tier = CURRENT_DART_KSIC_LEARNED_NOT_PIT``. Reclassifications
  (holding-company conversions, spin-offs) are invisible to it, which is why it can support an
  industry-removal / industry-matched CHECK but is not a sealed PIT label.
No price, return or label of any outcome is read.
"""
from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from . import contract as C

LEVELS = (5, 4, 3, 2)
MIN_ACCEPTED_LEVEL = 3   # fixed from the label-only leave-one-out: level 2 agreed 13/17, levels 3-5 206/206
TIER = 'CURRENT_DART_KSIC_LEARNED_NOT_PIT'
V4 = C.REPO / 'data/kr-industry-membership-foundation-v4/state/intervals.json.gz'


def v4_current_labels() -> dict[str, str]:
    """stock code (6 digits) -> last non-null v4 research industry (the current anchor)."""
    out = {}
    for code, ivs in json.loads(gzip.open(V4).read()).items():
        labelled = [iv for iv in ivs if iv.get('research_industry_id')]
        if labelled:
            out[code.split('.')[0]] = labelled[-1]['research_industry_id']
    return out


def learn(pairs: list[tuple[str, str]]) -> dict[int, dict[str, Counter]]:
    table: dict[int, dict[str, Counter]] = {n: defaultdict(Counter) for n in LEVELS}
    for code, group in pairs:
        for n in LEVELS:
            if len(code) >= n:
                table[n][code[:n]][group] += 1
    return table


def predict(code: str, table) -> dict | None:
    for n in LEVELS:
        if len(code) >= n and code[:n] in table[n]:
            cnt = table[n][code[:n]]
            group, top = cnt.most_common(1)[0]
            ties = [g for g, v in cnt.items() if v == top]
            if len(ties) > 1:       # a tied prefix is not an answer: fall to the shorter prefix
                continue
            return {'group': group, 'level': n, 'support': sum(cnt.values()),
                    'purity': round(top / sum(cnt.values()), 4)}
    return None


def build(company_rows: list[dict]) -> dict:
    v4 = v4_current_labels()
    kcode = {r['stock_code']: r for r in company_rows if r.get('induty_code') and r.get('stock_code')}
    overlap = sorted((s, kcode[s]['induty_code'], v4[s]) for s in kcode if s in v4)
    loo = Counter()
    for s, code, truth in overlap:
        table = learn([(c, g) for t, c, g in overlap if t != s])
        got = predict(code, table)
        key = f'level{got["level"]}' if got else 'UNANSWERED'
        loo[(key, bool(got) and got['group'] == truth)] += 1
    levels = {}
    for key in sorted({k for k, _ in loo}):
        right, wrong = loo[(key, True)], loo[(key, False)]
        levels[key] = {'n': right + wrong, 'agree': right,
                       'agreement': round(right / (right + wrong), 4) if right + wrong else None}
    answered = sum(v['n'] for k, v in levels.items() if k != 'UNANSWERED')
    agree = sum(v['agree'] for k, v in levels.items() if k != 'UNANSWERED')
    table = learn([(c, g) for _, c, g in overlap])
    labels = {}
    for r in company_rows:
        sc, code = r.get('stock_code'), r.get('induty_code')
        if not sc:
            continue
        if sc in v4:
            labels[r['corp_code']] = {'group': v4[sc], 'tier': 'V4_CURRENT_ANCHOR', 'kind': 'V4'}
        elif code and (p := predict(code, table)) and p['level'] >= MIN_ACCEPTED_LEVEL:
            labels[r['corp_code']] = {**p, 'tier': TIER, 'kind': 'EXTENDED', 'induty_code': code}
        else:
            labels[r['corp_code']] = {'group': None, 'tier': 'UNLABELLED', 'kind': 'NONE',
                                      'induty_code': code}
    return {
        'contract': 'KR_INDUSTRY_EXTENSION_FROM_DART_KSIC_V1', 'tier': TIER,
        'issuers': len(company_rows), 'overlapWithV4': len(overlap),
        'leaveOneOut': {'byAnsweringLevel': levels, 'answered': answered, 'agree': agree,
                        'agreement': round(agree / answered, 4) if answered else None,
                        'unanswered': levels.get('UNANSWERED', {}).get('n', 0)},
        'labelKinds': dict(Counter(v['kind'] for v in labels.values())),
        'labels': dict(sorted(labels.items())),
    }


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--company', type=Path, required=True, help='company.jsonl collected from OpenDART')
    ap.add_argument('--out', type=Path, default=Path(__file__).parent / 'data')
    args = ap.parse_args()
    rows = [json.loads(line) for line in args.company.read_text(encoding='utf-8').splitlines()]
    doc = build(rows)
    doc['minAcceptedLevel'] = MIN_ACCEPTED_LEVEL
    doc['source'] = {'endpoint': 'opendart company.json', 'collected': '2026-11-07', 'calls': len(rows),
                     'statusCounts': dict(Counter(r['status'] for r in rows))}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'company-facts-v1.jsonl.gz').write_bytes(gzip.compress(
        ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows).encode(), 9, mtime=0))
    (args.out / 'industry-extension-v1.json').write_text(
        json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({k: doc[k] for k in ('overlapWithV4', 'labelKinds')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
