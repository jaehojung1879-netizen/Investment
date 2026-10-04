"""Frozen identity, one-shot lifecycle and label-free machinery. Synthetic repositories and a fake GitHub API only."""
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pipeline import kr_factor_anatomy as A
from pipeline import kr_industry_anatomy as I
from pipeline import kr_industry_anatomy_execution as E
from pipeline import replay_calendar as RC

ROOT = Path(__file__).resolve().parents[1]
SPEC, SHA = E.load_spec(ROOT)
CROSSWALK = json.loads((ROOT / 'research_specs/kr-industry-membership-foundation-v4/crosswalk.json').read_text())
GOOD_ENV = {'GITHUB_ACTIONS': 'true', 'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_SHA': 'a' * 40,
            'ANATOMY_INPUT_ARTIFACT': SPEC['input']['artifactName'], 'ANATOMY_INPUT_RUN_ID': str(SPEC['input']['producingRunId']),
            'GH_TOKEN': 't', 'GITHUB_REPOSITORY': 'o/r'}


def fake_git(head='a' * 40, committed=True):
    def git(args, root):
        if args[0] == 'rev-parse':
            return (head + '\n').encode()
        return (Path(root) / args[1][len('HEAD:'):]).read_bytes() if committed else b'different'
    return git


def authorize(env=None, git=None, probe=lambda: False):
    return E.authorize_execution(SPEC, SHA, ROOT, dict(GOOD_ENV, **(env or {})), git or fake_git(), probe)


def test_frozen_spec_import_closure_and_scientific_label():
    assert SPEC['scientificStatus'] == 'EXPLORATORY_DEVELOPMENT_ON_PARTIALLY_RECONSTRUCTED_KR_HISTORY'
    assert SPEC['boundary']['passFailSemantics'] == 'NONE' and SPEC['phase'].startswith('PROTOCOL_AND_HARNESS_ONLY')
    assert SPEC['boundary']['mayRelabelV4Decision'] is False and SPEC['membership']['v4Decision'] == 'DATA_FOUNDATION_INSUFFICIENT_V4'
    assert SPEC['constants']['minMembers'] == 5 and SPEC['horizons'] == [63, 126, 252] and SPEC['primaryHorizon'] == 126


def test_pinned_membership_is_checked_byte_for_byte():
    assert E.verify_pins(SPEC, ROOT)
    tampered = copy.deepcopy(SPEC)
    first = next(iter(tampered['membership']['files']))
    tampered['membership']['files'][first] = '0' * 64
    with pytest.raises(ValueError, match='MEMBERSHIP_INPUT_CHANGED'):
        E.verify_pins(tampered, ROOT)
    relabelled = copy.deepcopy(SPEC)
    relabelled['membership']['v4Facts']['classifiedNameDates'] += 1
    with pytest.raises(ValueError, match='V4_FACT_CHANGED'):
        E.verify_pins(relabelled, ROOT)
    other = copy.deepcopy(SPEC)
    other['benchmark'] = 'OTHER.KS'
    with pytest.raises(ValueError, match='BENCHMARK'):
        E.verify_pins(other, ROOT)


def test_benchmark_and_return_basis_equal_the_accepted_framework():
    anatomy = json.loads((ROOT / 'research_specs/kr-factor-anatomy-v1.json').read_text())
    assert SPEC['benchmark'] == anatomy['benchmark'] == I.BENCHMARK == '069500.KS'
    assert SPEC['returnBasis'] == anatomy['returnDefinition']['label'] == I.RETURN_BASIS
    assert 'total shareholder return' in SPEC['returnDefinition']['basis']  # stated only as what it is NOT


def test_taxonomy_is_the_frozen_v4_crosswalk_unmodified():
    assert SPEC['membership']['coarseGroups'] == 14 == len(CROSSWALK['groups'])
    assert SPEC['membership']['mappedRawLabels'] == len(CROSSWALK['mapping']) == 82


@pytest.mark.parametrize('env,reason', [({'GITHUB_ACTIONS': 'false'}, 'REQUIRES_ACTIONS'), ({'GITHUB_REF': 'refs/heads/x'}, 'REQUIRES_MAIN'),
                                        ({'GITHUB_EVENT_NAME': 'pull_request'}, 'WORKFLOW_DISPATCH'),
                                        ({'ANATOMY_INPUT_ARTIFACT': 'wrong'}, 'INPUT_ARTIFACT_IDENTITY_MISMATCH'),
                                        ({'ANATOMY_INPUT_RUN_ID': '1'}, 'INPUT_ARTIFACT_IDENTITY_MISMATCH')])
def test_authorization_refuses_outside_the_exact_context(env, reason):
    with pytest.raises(ValueError, match=reason):
        authorize(env)


def test_authorization_requires_the_committed_spec_head_and_no_lock_or_result(monkeypatch):
    permit = authorize()
    assert E.require_permit(permit) is permit
    with pytest.raises(ValueError, match='CHECKOUT_IS_NOT_THE_DISPATCHED_COMMIT'):
        authorize(git=fake_git(head='b' * 40))
    with pytest.raises(ValueError, match='SPEC_NOT_COMMITTED_AT_HEAD'):
        authorize(git=fake_git(committed=False))
    with pytest.raises(ValueError, match='EXECUTION_LOCK_ALREADY_EXISTS'):
        authorize(probe=lambda: True)
    monkeypatch.setattr(E, 'RESULT_PATH', 'README.md')
    with pytest.raises(ValueError, match='RESULT_ALREADY_COMMITTED'):
        authorize()


def test_pull_request_environment_is_never_authorized():
    report = E.verify(ROOT, {'GITHUB_EVENT_NAME': 'pull_request'})
    assert report['status'] == 'VERIFIED' and report['executeAuthorizedInThisEnvironment'] is False
    assert report['stoppedBeforeOutcomes'] and report['historicalExecutionPerformed'] is False


class FakeApi:
    def __init__(self, existing=(), refuse_create=None):
        self.refs, self.calls, self.refuse_create = {r: 'x' for r in existing}, [], refuse_create

    def __call__(self, method, path, payload=None):
        self.calls.append(method)
        if method == 'GET' and path.startswith('/git/matching-refs/'):
            prefix = 'refs/' + path[len('/git/matching-refs/'):]
            return 200, [{'ref': r} for r in self.refs if r.startswith(prefix)]
        if method == 'POST':
            if payload['ref'] in self.refs:
                return 422, {}
            if self.refuse_create:
                return 500, {}
            self.refs[payload['ref']] = payload['sha']
            return 201, {}
        if method == 'GET' and path.startswith('/git/ref/'):
            ref = 'refs/' + path[len('/git/ref/'):]
            return (200, {'object': {'sha': self.refs[ref]}}) if ref in self.refs else (404, {})
        return 405, {}


def test_one_shot_lock_is_study_level_exclusive_and_only_posts_and_gets():
    api = FakeApi()
    lock = E.claim_execution_lock(SHA, GOOD_ENV, api)
    assert E.require_lock(lock, SHA) is lock and set(api.calls) <= {'GET', 'POST'}
    assert E.STUDY_LOCK_REF in api.refs and E.lock_ref(SHA) in api.refs
    with pytest.raises(ValueError, match='EXECUTION_LOCK_ALREADY_EXISTS'):
        E.claim_execution_lock('f' * 64, GOOD_ENV, api)  # a DIFFERENT spec sha is refused by the study-level ref
    assert E.lock_exists(None, GOOD_ENV, api) is True
    with pytest.raises(ValueError, match='NOT_CREATED'):
        E.claim_execution_lock(SHA, GOOD_ENV, FakeApi(refuse_create=True))
    with pytest.raises(ValueError, match='UNVERIFIABLE'):
        E.lock_exists(None, {}, api)
    with pytest.raises(ValueError, match='REQUIRES_ACTIONS_MAIN'):
        E.claim_execution_lock(SHA, dict(GOOD_ENV, GITHUB_REF='refs/heads/x'), FakeApi())


def test_outcomes_need_both_permit_and_lock_and_leave_counters_zero_on_refusal():
    counters = E.Counters()
    with pytest.raises(ValueError, match='WITHOUT_PERMIT'):
        E.forward_table({}, {}, None, SPEC, {}, object(), counters, None, SHA)
    with pytest.raises(ValueError, match='DURABLE_EXECUTION_LOCK_REQUIRED'):
        E.forward_table({}, {}, None, SPEC, {}, authorize(), counters, None, SHA)
    assert counters.zero()


def test_label_free_assembly_and_audit_never_touch_an_outcome(monkeypatch):
    def boom(*a, **k):
        raise AssertionError('OUTCOME_READ_ON_PULL_REQUEST')
    monkeypatch.setattr(A, 'endpoint_returns', boom)
    monkeypatch.setattr(E.AE, 'sealed_v1_function', boom)
    monkeypatch.setattr(E, 'forward_table', boom)
    assert E.verify(ROOT)['counters'] == E.Counters().__dict__
    audit = E.readiness_audit(ROOT)
    assert audit['counters'] == E.Counters().__dict__ and audit['basedOnAnyReturnResult'] is False


def test_readiness_decision_is_one_of_two_and_structural():
    audit = E.readiness_audit(ROOT)
    assert audit['decision'] in ('READY_FOR_INDUSTRY_ANATOMY_EXECUTION', 'DATA_BLOCKED_BEFORE_INDUSTRY_ANATOMY')
    assert audit['decision'] == 'READY_FOR_INDUSTRY_ANATOMY_EXECUTION' and all(audit['checks'].values())
    blocked = copy.deepcopy(SPEC)
    assert blocked  # a failing pin flips the decision rather than being ignored:
    stored = E.verify_pins
    try:
        E.verify_pins = lambda *a, **k: (_ for _ in ()).throw(ValueError('PIN'))
        flipped = E.readiness_audit(ROOT)
    finally:
        E.verify_pins = stored
    assert flipped['decision'] == 'DATA_BLOCKED_BEFORE_INDUSTRY_ANATOMY'


def test_readiness_gates_report_reasons_without_reading_outcomes():
    rows = pd.DataFrame({'date': ['2020-01-03'] * 3, 'ticker': ['A', 'B', 'C'], 'marketCap': [1.0, 2.0, 3.0], 'logAdv60': 1.0,
                         **{c: 0.0 for c in I.FUNDAMENTAL_COLUMNS[:-1]}})
    schedule = {'2020-01-03': ['A', 'B', 'C']}
    assert E.readiness_gates(rows, schedule, {'A': []}, SPEC, schedule) == []
    assert 'SIGNAL_DATES_DIFFER_FROM_V4_MEMBERSHIP_CALENDAR' in E.readiness_gates(rows, schedule, {'A': []}, SPEC, {'2020-01-10': ['A']})
    assert 'PIT_TOP120_DIFFERS_FROM_V4_MEMBERSHIP_UNIVERSE' in E.readiness_gates(rows, schedule, {'A': []}, SPEC, {'2020-01-03': ['A', 'B', 'Z']})
    assert 'DUPLICATE_PIT_NAME_DATE' in E.readiness_gates(pd.concat([rows, rows]), schedule, {'A': []}, SPEC, schedule)
    assert 'MARKET_CAP_UNAVAILABLE' in E.readiness_gates(rows.assign(marketCap=np.nan), schedule, {'A': []}, SPEC, schedule)
    assert any(r.startswith('SIGNAL_TIME_COLUMNS_MISSING') for r in E.readiness_gates(rows.drop(columns='logAdv60'), schedule, {'A': []}, SPEC, schedule))
    assert E.readiness_gates(rows.iloc[0:0], schedule, {}, SPEC, schedule) == ['NO_PIT_NAME_DATES']


def test_no_revised_macro_history_enters_the_historical_anatomy():
    assert not any(any(x in name.lower() for x in ('ecos', 'fred', 'macro', 'rate')) for name in I.FEATURES)
    for module in ('pipeline/kr_industry_anatomy.py', 'pipeline/kr_industry_anatomy_execution.py'):
        text = (ROOT / module).read_text().lower()
        code = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith(('#', '"', "'")))
        assert 'import ecos' not in code and 'kr_market_context' not in code and 'fred' not in code.replace('foreign', '')
    assert 'ECOS or FRED revised macro history' in SPEC['features']['excluded']


def test_prior_sealed_studies_are_not_rerun_and_workflow_never_executes_on_pull_requests():
    workflow = (ROOT / '.github/workflows/kr-industry-opportunity-anatomy-v1.yml').read_text()
    for other in ('run_kr_factor_anatomy', 'run_kr_top120_regime_review', 'kr-model-overlay-portfolio-v1 execute', 'collect_dart', 'KRX_API'):
        assert other not in workflow
    execute = workflow[workflow.index('  execute:'):]
    assert "github.event_name == 'workflow_dispatch' && inputs.mode == 'execute'" in execute and 'refs/heads/main' in execute
    assert 'contents: write' in execute and workflow.count('contents: write') == 1
    assert 'pull_request' in workflow and "mode execute" not in workflow.split('execute:')[0]
    assert '--mode execute' in execute and '--mode execute' not in workflow.split('  execute:')[0]


def test_past_features_from_synthetic_prices_ignore_the_future():
    days = RC.sessions('2018-01-01', '2020-12-31', 'KR')
    date = str(days[300].date())
    flat = pd.DataFrame({'Close': np.linspace(100, 200, len(days))}, index=days)
    spike = flat.copy()
    spike.iloc[320:] = 1e6
    base = E.past_features({'X.KS': flat, I.BENCHMARK: flat}, ['X.KS'], days, date)['X.KS']
    later = E.past_features({'X.KS': spike, I.BENCHMARK: spike}, ['X.KS'], days, date)['X.KS']
    assert base['trail126'] == later['trail126'] and base['aboveMA126'] == later['aboveMA126'] == 1.0
    assert np.array_equal(base['daily'], later['daily']) and len(base['daily']) == 126
    short = E.past_features({'X.KS': flat.iloc[:50]}, ['X.KS'], days, date)['X.KS']
    assert np.isnan(short['trail126'])  # missing history is missing, not zero


def test_forward_table_and_full_panel_on_synthetic_prices(monkeypatch):
    days = RC.sessions('2018-01-01', '2021-12-31', 'KR')
    tickers = [f'S{i}.KS' for i in range(6)]
    rng = np.random.default_rng(1)
    prices = {t: pd.DataFrame({'Close': 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, len(days)))}, index=days) for t in tickers + [I.BENCHMARK]}
    date = str(days[300].date())
    schedule = {date: tickers}
    counters = E.Counters()
    permit = authorize()
    lock = E.claim_execution_lock(SHA, GOOD_ENV, FakeApi())
    v1_spec, _ = E.X.load_spec(ROOT)
    forward, windows = E.forward_table(prices, schedule, days, SPEC, v1_spec, permit, counters, lock, SHA)
    assert counters.outcomeColumnCalls == 3 * 6 and counters.targetCalls == counters.labelCalls == 18
    entry, exit_ = windows[(date, 126)]
    assert entry == str(days[301].date()) and exit_ == str(days[301 + 126].date())
    r, b, status = forward[(date, 126)]['S0.KS']
    assert status in ('MATURED', 'UNRESOLVED_TERMINAL_OR_DISTRIBUTION_EVIDENCE')
    intervals = {t: [{'start': None, 'end': None, 'label': '반도체 제조업', 'status': 'RECONSTRUCTED_STABLE_NO_CHANGE_EVENT',
                      'reconstruction_status': 'RECONSTRUCTED_STABLE_NO_CHANGE_EVENT'}] for t in tickers}
    membership = I.membership_table(schedule, intervals, CROSSWALK)
    caps = pd.DataFrame({'date': date, 'ticker': tickers, 'marketCap': np.arange(1.0, 7.0)})
    past = {date: E.past_features(prices, tickers, days, date)}
    values = {date: {t: {'logAdv60': 20.0} for t in tickers}}
    for name in I.SENSITIVITIES:
        panel = E.build_sensitivity_panel(name, membership, caps, None, past, forward, windows, values)
        assert set(panel.industry) == {'ELECTRONICS_ELECTRICAL'} and len(panel) == 1
        if name == 'FULL':
            assert panel.iloc[0].status == 'ELIGIBLE' and panel.iloc[0].classifiedCoverage == pytest.approx(1.0)
        elif name == 'LEAVE_LARGEST_CONSTITUENT_OUT':
            assert panel.iloc[0].status == 'ELIGIBLE' and panel.iloc[0].n == 5  # exactly the registered minimum remains
        else:
            assert panel.iloc[0].n == 6  # none of the synthetic names is one of the two registered mega caps
