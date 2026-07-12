"""Validate site-data artifacts before Pages deployment."""
from __future__ import annotations
import json, math, sys
from pathlib import Path
from .quality import recommendations_blocked


def _walk(o, path="$"):
    if isinstance(o, dict):
        for k,v in o.items(): yield from _walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i,v in enumerate(o): yield from _walk(v, f"{path}[{i}]")
    elif isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        yield path


def validate(path: str | Path, production: bool = True) -> list[str]:
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    errors=[]; m=data.get('meta',{})
    for k in ['portfolioName','meta','generatedAt','core','screened','tradeIdeas']:
        if k not in data: errors.append(f'missing_{k}')
    bad=list(_walk(data))
    if bad: errors.append('nan_or_infinity:' + ','.join(bad[:5]))
    if production:
        if data.get('seed'): errors.append('seed_artifact_not_allowed_for_production')
        if data.get('stale'): errors.append('stale_artifact_not_allowed_for_production')
        if m.get('modelsTrained',0) <= 0: errors.append('modelsTrained_zero')
        if (m.get('coveragePct') or 0) < 95: errors.append('coverage_below_95')
    blocked,reasons = recommendations_blocked(data)
    for region, ideas in (data.get('tradeIdeas') or {}).items():
        for idea in ideas:
            q=idea.get('quality') or {}
            if not q.get('eligible') or q.get('qualityGrade') == 'REJECT':
                errors.append(f'ineligible_recommendation:{idea.get("ticker")}')
            if idea.get('suggestedWeightPct') is not None:
                errors.append(f'public_weight_exposed:{idea.get("ticker")}')
    if data.get('recommendationsBlocked') and any((data.get('tradeIdeas') or {}).get(r) for r in ('KR','US')):
        errors.append('blocked_artifact_contains_trade_ideas')
    return errors


def main(argv=None):
    argv=argv or sys.argv[1:]
    if not argv:
        print('usage: python -m pipeline.validate data/site-data.json [--allow-seed]'); return 2
    production='--allow-seed' not in argv
    errs=validate(argv[0], production=production)
    if errs:
        print('VALIDATION FAILED')
        for e in errs: print('-',e)
        return 1
    print('validation ok')
    return 0
if __name__=='__main__': sys.exit(main())
