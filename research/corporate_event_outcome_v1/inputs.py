"""Admission contract for the economic inputs the historical evaluation needs.

This module does not build any of them (Codex's source lane owns price,
dividend and corporate-action data; #317 owns cash/tax adapters). It states
exactly what an admitted input must say about itself and refuses anything else.
A component that is absent is SOURCE_BLOCKED; nothing is substituted.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# v4 PIT intervals (Top120) plus the current-DART-KSIC learned extension for the rest. NOT point-in-time
# for the extension, so it is admitted only when the Owner names this exact tier in the manifest row.
COMPOSITE_INDUSTRY_TIER = 'V4_PIT_PLUS_DART_KSIC_NOT_PIT'
OWNER_ACCEPTANCE_REQUIRED = {COMPOSITE_INDUSTRY_TIER}

REQUIRED = {
    'stockTotalReturn': {'basis': {'SHAREHOLDER_TOTAL_RETURN_EX_DATE_SEALED'},
                         'why': 'KRX bars carry no dividends; A1 matured windows with a record date: see readiness'},
    'benchmarkTotalReturn069500': {'basis': {'ETF_SHAREHOLDER_TOTAL_RETURN_RECONCILED'},
                                   'why': 'unresolved accrual anomaly (AGENTS v2.46/v2.47)'},
    'investableKrwCash': {'basis': {'REALIZED_CASH_PAYOFF', 'INVESTABLE_NAV_RETURN'},
                          'why': 'funded control needs a payoff, not a quote (#317 build_cash_input_contract)'},
    'terminalConsideration': {'basis': {'CITED_DART_RECEIPT_CONSIDERATION'},
                              'why': 'held names delisted inside a window'},
    'tradability': {'basis': {'KRX_VOLUME_PRESENCE'}, 'why': 'entry/rebalance tradability'},
    'pitIndustry': {'basis': {'PIT_INDUSTRY_INTERVALS_ALL_COHORT_ISSUERS', COMPOSITE_INDUSTRY_TIER},
                    'why': 'B1 final support requires the industry-matched check'},
    'matchingCharacteristics': {'basis': {'PIT_SIGNAL_DATE_CROSS_SECTION'},
                                'why': 'log mcap, B/M, 12-1 momentum, 21d return, beta for 3-peer match'},
    'investorCostTaxContract': {'basis': {'OWNER_FIXED_ACCOUNT_CONTRACT'},
                                'why': 'one investor account/tax contract shared with #317'},
}
RIGHTS = 'VERIFIED_INTERNAL_RESEARCH'


def admit(manifest_path: Path | None) -> dict:
    """Return {component: 'ADMITTED' | 'SOURCE_BLOCKED:<code>'} plus the blocked list."""
    status = {}
    manifest = {}
    if manifest_path and Path(manifest_path).exists():
        manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    base = Path(manifest_path).parent if manifest_path else Path('.')
    for name, req in REQUIRED.items():
        row = (manifest.get('components') or {}).get(name)
        if not row:
            status[name] = 'SOURCE_BLOCKED:NOT_SUPPLIED'
            continue
        if row.get('basis') not in req['basis']:
            status[name] = 'SOURCE_BLOCKED:BASIS_NOT_ADMISSIBLE'
            continue
        if row.get('basis') in OWNER_ACCEPTANCE_REQUIRED and row.get('ownerAcceptedTier') != row.get('basis'):
            status[name] = 'SOURCE_BLOCKED:NOT_PIT_TIER_NEEDS_OWNER_ACCEPTANCE'
            continue
        if row.get('rights') != RIGHTS:
            status[name] = 'SOURCE_BLOCKED:RIGHTS_UNVERIFIED'
            continue
        path = base / row.get('path', '')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row.get('sha256'):
            status[name] = 'SOURCE_BLOCKED:DIGEST_MISMATCH'
            continue
        if not row.get('independentAudit'):
            status[name] = 'SOURCE_BLOCKED:NO_NON_AUTHOR_AUDIT'
            continue
        status[name] = 'ADMITTED'
    blocked = sorted(f'{k}:{v.split(":", 1)[1]}' for k, v in status.items() if v != 'ADMITTED')
    return {'components': status, 'blocked': blocked, 'required': {k: v['why'] for k, v in REQUIRED.items()}}
