"""Extend the frozen census to both supported workflow suffixes, no bypass."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DOCS = ('workflow-inventory.md','workflow-inventory-addendum.md',
        'workflow-inventory-phase-c-amendment.md','workflow-inventory-phase-c-price-repair.md')
NAME = re.compile(r'[A-Za-z0-9][\w.-]*\.ya?ml')


def section(text, heading):
    rest = text.split('## '+heading,1)[1]
    return rest.split('\n## ',1)[0]


def test_complete_workflow_census_preserves_frozen_layers():
    docs = [(ROOT/'docs'/p).read_text() for p in DOCS]
    actual = {p.name for p in (ROOT/'.github/workflows').iterdir() if p.suffix in {'.yml','.yaml'}}
    mentioned = set(NAME.findall('\n'.join(docs)))
    active = set().union(*(set(NAME.findall(section(d,'ACTIVE'))) for d in docs))
    retired = set(NAME.findall(section(docs[0],'RETIRED RESEARCH')))
    assert actual <= mentioned
    assert actual == active
    assert not retired & actual
    assert not retired & active


def test_source_repair_workflow_is_manual_main_only_and_shares_one_shot_namespace():
    text = (ROOT/'.github/workflows/kr-alpha-atlas-phase-c-price-repair.yaml').read_text()
    # No new parser dependency in the frozen formal numerical environment.
    trigger = re.search(r'^on:\n(.*?)(?=^[A-Za-z])',text,re.M|re.S).group(1)
    assert re.findall(r'^  ([\w-]+):',trigger,re.M)==['workflow_dispatch']
    assert re.search(r'^        default: validate$',trigger,re.M)
    assert re.search(r"^    if: github.ref == 'refs/heads/main'$",text,re.M)
    concurrency = re.search(r'^concurrency:\n(.*?)(?=^[A-Za-z])',text,re.M|re.S).group(1)
    assert re.search(r'^  group: kr-alpha-atlas-phase-c-v1-single-attempt$',concurrency,re.M)
    assert re.search(r'^  cancel-in-progress: false$',concurrency,re.M)
    assert 'kr-alpha-atlas-phase-c-v1-results-' in text
    assert 'python-version: \'3.11.16\'' in text
