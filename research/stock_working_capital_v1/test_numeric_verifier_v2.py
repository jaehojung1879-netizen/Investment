"""Exact mixed-basis regressions, entirely invented financial values and ZIPs."""
import io
import ast
import inspect
import zipfile

import pytest

from . import pit_filing_evidence as ORIGINAL
from . import numeric_verifier_v2 as E
from . import opendart_recovery as O
from . import portable_collection as P
from .test_pit_admission import filing, meta, package


def mixed(record, *, separate_first, malformed=None, duplicate_selected=False, value_delta=0):
    # Keep original namespace declarations. Add different basis contexts and
    # facts under unique IDs; the requested amount is untouched.
    base = package(record, member='ConsolidatedMember', value_delta=value_delta)
    other = package(record, member='SeparateMember', value_delta=777)
    def xml(p):
        with zipfile.ZipFile(io.BytesIO(p['raw'])) as z:
            return z.read('instance.xbrl').decode()
    c, s = xml(base), xml(other)
    s = s[s.index('>')+1:s.rindex('</xbrli:xbrl>')]
    s = s.replace('id="F"', 'id="FS"').replace('id="B"', 'id="BS"')
    s = s.replace('contextRef="F"', 'contextRef="FS"').replace('contextRef="B"', 'contextRef="BS"')
    s = s.replace('<xbrli:unit id="U"><xbrli:measure>iso:KRW</xbrli:measure></xbrli:unit>', '')
    if malformed == 'unknown_member': s = s.replace('SeparateMember', 'UnknownMember')
    if malformed == 'wrong_issuer': s = s.replace(record['corpCode'], '87654321')
    if malformed == 'wrong_axis': s = s.replace('ConsolidatedAndSeparateFinancialStatementsAxis', 'OtherAxis')
    if malformed == 'unbound_qname': s = s.replace('ifrs-full:SeparateMember', 'evil:SeparateMember')
    if malformed == 'duplicate_context': s += s[s.index('<xbrli:context'):s.index('</xbrli:context>')+len('</xbrli:context>')]
    if separate_first: c = c[:c.index('>')+1]+s+c[c.index('>')+1:]
    else: c = c.replace('</xbrli:xbrl>', s+'</xbrli:xbrl>')
    if duplicate_selected:
        c = c.replace('</xbrli:xbrl>', '<ifrs-full:Inventories contextRef="B" unitRef="U" decimals="0">'+str(ORIGINAL.F.matching_rows(record, 'inventory')[0]['thstrm_amount'])+'</ifrs-full:Inventories></xbrli:xbrl>')
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo('instance.xbrl',date_time=(2024,1,1,0,0,0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info,c)
    raw = out.getvalue()
    return {**base, 'raw':raw, 'sha256':ORIGINAL.sha(raw)}


@pytest.mark.parametrize('fs_div', ['CFS', 'OFS'])
@pytest.mark.parametrize('separate_first', [False, True])
@pytest.mark.parametrize('field', ['inventory', 'receivables'])
def test_requested_basis_is_selected_independent_of_other_basis_order(fs_div, separate_first, field):
    r = filing(2024)
    p = mixed(r, separate_first=separate_first)
    if fs_div == 'OFS':
        # Other basis carries different known amounts: cannot borrow CFS.
        for row in r['rows']: row['thstrm_amount'] = str(int(row['thstrm_amount'])+777)
        r['fsDiv'] = 'OFS'
    assert E.original_financial_facts(r, meta(2024), p, field)['ready']


@pytest.mark.parametrize('malformed', ['unknown_member','wrong_issuer','wrong_axis','unbound_qname','duplicate_context'])
def test_unproven_other_context_must_not_be_silently_filtered(malformed):
    r = filing(2024)
    with pytest.raises(ValueError):
        E.original_financial_facts(r, meta(2024), mixed(r,separate_first=True,malformed=malformed),'inventory')


def test_wrong_selected_amount_still_refuses():
    r=filing(2024)
    with pytest.raises(ValueError):
        E.original_financial_facts(r,meta(2024),mixed(r,separate_first=False,value_delta=1),'inventory')


def test_opposite_basis_alone_is_not_a_match():
    r=filing(2024)
    with pytest.raises(ValueError):
        E.original_financial_facts(r,meta(2024),package(r,member='SeparateMember'),'inventory')


def test_duplicate_selected_basis_fact_still_refuses():
    r=filing(2024)
    with pytest.raises(ValueError):
        E.original_financial_facts(r,meta(2024),mixed(r,separate_first=False,duplicate_selected=True),'inventory')


def test_original_acquisition_code_and_plan_stay_exactly_valid():
    assert E.identity()['legacyModuleSha256'] == E.LEGACY_MODULE_SHA256
    assert ORIGINAL.sha(O.PLAN.read_bytes()) == O.PLAN_SHA256
    assert len(P.validate_plan(P.read_plan(O.PLAN))) == 68
    r = filing(2024)
    with pytest.raises(ValueError, match='STATEMENT_BASIS'):
        ORIGINAL.original_financial_facts(r,meta(2024),mixed(r,separate_first=True),'inventory')


def test_numeric_arithmetic_is_the_legacy_reader_with_only_explicit_basis_selection():
    old = inspect.getsource(ORIGINAL.original_financial_facts)
    expected = old.replace('            ctx = _context(root, x, record, namespaces)\n',
                           '            ctx = _context(root, x, record, namespaces)\n            if ctx is None:\n                continue\n')
    assert ast.dump(ast.parse(inspect.getsource(E.original_financial_facts))) == ast.dump(ast.parse(expected))
    old_context = inspect.getsource(ORIGINAL._context)
    expected_context = old_context.replace('(members[0].text or "").split(":")[-1] != expected',
                                           '(members[0].text or "").split(":")[-1] not in ("ConsolidatedMember", "SeparateMember")')
    expected_context = expected_context.replace('    period = ctx.find("{" + XI + "}period")',
                                               '    if (members[0].text or "").split(":")[-1] != expected:\n        return None\n    period = ctx.find("{" + XI + "}period")')
    assert ast.dump(ast.parse(inspect.getsource(E._context))) == ast.dump(ast.parse(expected_context))


def test_opt_in_audit_binds_original_package_plan_and_both_numeric_code_versions():
    r = filing(2024)
    p = mixed(r,separate_first=True)
    t = meta(2024)
    legacy = O.verify_fact_candidates([r], {t['receipt']:p}, [t])
    current = O.verify_fact_candidates([r], {t['receipt']:p}, [t], numeric_verifier='mixed-basis-v2')
    assert legacy['verifiedFinancialFactCount'] == 0
    assert current['verifiedFinancialFactCount'] == 3
    assert current['numericVerifier'] == {**E.identity(), 'acquisitionPlanSha256':O.PLAN_SHA256}
    assert {f['sourceSha256'] for f in current['facts']} == {p['sha256']}
    assert not current['sourceAdmissionAuthorized'] and current['fiscalAgePolicySelected'] is None
    with pytest.raises(ValueError, match='UNKNOWN_NUMERIC'):
        O.verify_fact_candidates([],{},[],numeric_verifier='invented')


def test_v2_is_never_reported_from_an_envelope_only_command(capsys):
    assert O.main(['--acquisition','absent','--receipt','absent','--numeric-verifier','mixed-basis-v2']) == 4
    assert 'NUMERIC_AUDIT_VERSION_REQUIRES_NEW_OUTPUT' in capsys.readouterr().out


@pytest.mark.parametrize('kwargs', [{'currency':'USD'}, {'unit_uri':'https://evil.invalid/iso4217'},
                                   {'start':'2023-07-01'}, {'end':'2024-12-30'}, {'value_delta':1}])
def test_v2_retains_exact_currency_unit_duration_and_amount_refusals(kwargs):
    r=filing(2024)
    with pytest.raises(ValueError):
        E.original_financial_facts(r,meta(2024),package(r,**kwargs),'inventory')
