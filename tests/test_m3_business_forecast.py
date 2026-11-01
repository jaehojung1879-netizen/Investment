"""Offline parser and pre-result causal accounting checks."""
import hashlib
import subprocess
from pathlib import Path

import pytest

from research.m3_backlog_v1.parser import GROUPS, parse_table
from research.m3_backlog_v1.geometry import known_before_month_end, month_end
from research.m3_backlog_v1.run import eligible_training, metrics


def table(first='18,230', prior='19,843'):
    rows=[]
    for g,label in GROUPS.items():
        name={'computers_electronics':'Computers and electronic products','electrical_equipment':'Electrical equipment, appliances,\n and components'}.get(g,label)
        rows.append(f'{name}…… {first}   {prior}   22,260')
    return 'Table 1. Value of Manufacturers Shipments\n[Millions of Dollars]\nSeasonally Adjusted  Not Seasonally Adjusted\n'+'\n'.join(rows)+'\nTable 2.'


def test_single_space_does_not_skip_current_cell():
    assert all(x==[18230,19843] for x in parse_table(table(),1).values())


@pytest.mark.parametrize('bad',['NA','(D)','(S)','0','-1'])
def test_never_skip_suppressed_or_invalid_current_cell(bad):
    with pytest.raises(ValueError):parse_table(table(first=bad),1)


def test_unit_and_seasonal_basis_required():
    with pytest.raises(ValueError):parse_table(table().replace('Seasonally Adjusted','Unknown basis'),1)


def test_unknown_same_day_not_midnight():
    assert not known_before_month_end({'printedPublicationDate':'2009-04-30'},month_end('2009-04'))


def test_all_future_months_must_be_published_before_training():
    ex={'cutoffMonth':'2008-10','outcome':[.1]*6,'futureTargetReferences_METADATA_ONLY':['2008-11','2008-12','2009-01']}
    meta={m:{'printedPublicationDate':'2009-01-05'} for m in ex['futureTargetReferences_METADATA_ONLY']}
    meta['2009-01']['printedPublicationDate']='2009-03-05'
    assert eligible_training([ex],'2009-02',meta)==[]
    assert eligible_training([ex],'2009-04',meta)==[ex]


def test_skill_sign_and_identical_forecasts():
    assert metrics([0],[0],[1])['skill']==0
    assert metrics([0],[1],[1])['skill']==1
    assert metrics([0],[-1],[1])['skill']==-3


def test_original_known_prefix_manual_cells():
    p=Path('/workspace/m3-source-feasibility-20261031/original-release-pdfs/2008-11.pdf')
    if not p.exists():pytest.skip('Private/local original cache absent; no CI network fetch')
    assert hashlib.sha256(p.read_bytes()).hexdigest()=='0e40f4a118a315af282484149a89c0a06f95c09f3ecd0dafd04fc0e0599a3ba2'
    text=subprocess.check_output(['pdftotext','-layout',str(p),'-']).decode()
    assert list(parse_table(text,1).values())==[[18230,19843],[27466,27563],[28685,28461],[29859,31260],[9633,10330],[46331,48073]]
    assert list(parse_table(text,3).values())==[[21345,23203],[59941,60660],[105239,106070],[125765,124560],[22786,23431],[467916,470107]]
