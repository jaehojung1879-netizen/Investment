"""Cash-only source paging, no dividend-yield/performance selection or TR."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from research.corporate_event_readiness_v1.etf.source import (
    inspect_distribution_history, project_distribution_page,
)

ROOT = Path(__file__).resolve().parents[1] / 'research/corporate_event_readiness_v1/etf'


def fixture():
    pages = json.loads((ROOT / 'distribution-history-pages-v1.json').read_text())['pages']
    return deepcopy(pages), (ROOT / 'issuer-projection.json').read_bytes()


def inspect(pages, product):
    return inspect_distribution_history([json.dumps(p).encode() for p in pages], product_source=product)


def test_actual_full_period_retrieval_recovers_seven_older_records():
    pages, product = fixture()
    result = inspect(pages, product)
    assert [len(p['dividList']) for p in pages] == [12, 10]
    assert result['declaredCount'] == result['coverage']['observedEvents'] == 22
    assert result['coverage']['firstRecordDate'] == '2012-12-28'
    assert result['coverage']['lastRecordDate'] == '2026-10-15'
    assert len([r for r in result['events'] if r['recordDate'] < '2025-01-01']) == 7
    assert all(e['exDate'] is None and e['investorNetCash'] is None for e in result['events'])
    assert result['coverageGapYears'] == [2019, 2020, 2021, 2022, 2023, 2024]
    assert not result['coverage']['fullHistoryCertified']
    assert not result['economicEmpiricismReady'] and not result['outcomeExecutionAuthorized']


def test_projection_never_selects_yield_or_nav_fields():
    pages, _ = fixture()
    expected = project_distribution_page(json.dumps(pages[0]).encode())
    pages[0]['publishedReturn'] = 'SYN_UNREAD'
    for row in pages[0]['dividList']:
        row.update(yield1='SYN_UNREAD', yield1Nav='SYN_UNREAD', dividY='SYN_UNREAD')
    assert project_distribution_page(json.dumps(pages[0]).encode()) == expected


@pytest.mark.parametrize('mutation,reason', [
    (lambda p: p.pop(), 'INCOMPLETE_OR_EXCESS'),
    (lambda p: p[1].update(totalCnt=21), 'STABLE_POSITIVE'),
    (lambda p: p[1]['dividList'].__setitem__(0, deepcopy(p[0]['dividList'][0])), 'OVERLAPPING'),
    (lambda p: p[1]['dividList'][0].update(fid='OTHER'), 'ISSUER_INSTRUMENT'),
    (lambda p: p[1]['dividList'][0].update(stkTicker='069500'), 'ISSUER_INSTRUMENT'),
    (lambda p: p[0].update(totalCnt=True), 'INVALID_DISTRIBUTION_PAGE'),
])
def test_partial_changed_duplicate_or_other_instrument_pages_are_refused(mutation, reason):
    pages, product = fixture()
    mutation(pages)
    with pytest.raises(ValueError, match=reason):
        inspect(pages, product)


def test_empty_post_completion_probe_is_not_added_to_the_complete_page_set():
    pages, product = fixture()
    pages.append({'totalCnt': 0, 'dividList': []})
    with pytest.raises(ValueError, match='STABLE_POSITIVE'):
        inspect(pages, product)


def test_no_pages_is_not_an_empty_complete_history():
    _, product = fixture()
    with pytest.raises(ValueError, match='DISTRIBUTION_PAGES_REQUIRED'):
        inspect([], product)
