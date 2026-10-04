"""Frozen identity, one-shot lifecycle and label-free machinery. Synthetic repositories and a fake GitHub API only."""
import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pipeline import kr_factor_anatomy as A
from pipeline import kr_factor_anatomy_execution as AE
from pipeline import kr_industry_anatomy as I
from pipeline import kr_industry_anatomy_execution as IE
from pipeline import kr_stock_within_industry_anatomy as S
from pipeline import kr_stock_within_industry_anatomy_execution as E
from pipeline import kr_top120_regime_review_execution as RE
from pipeline import replay_calendar as RC

ROOT = Path(__file__).resolve().parents[1]
SPEC, SHA = E.load_spec(ROOT)
CROSSWALK = json.loads((ROOT / 'research_specs/kr-industry-membership-foundation-v4/crosswalk.json').read_text())
GOOD_ENV = {'GITHUB_ACTIONS': 'true', 'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_SHA': 'a' * 40,
            'ANATOMY_INPUT_ARTIFACT': SPEC['input']['artifactName'], 'ANATOMY_INPUT_RUN_ID': str(SPEC['input']['producingRunId']),
            'GH_TOKEN': 't', 'GITHUB_REPOSITORY': 'o/r'}


@pytest.fixture(autouse=True)
def synthetic_lifecycle_paths(monkeypatch):
    """The study is now sealed (its result and marker are committed), so the synthetic authorization and lifecycle tests, which exercise the
    rules rather than the repository state, point the result and marker paths at files that do not exist. The sealed state itself is pinned by
    tests/test_kr_stock_within_industry_anatomy_v1_result_seal.py."""
    monkeypatch.setattr(E, 'RESULT_PATH', 'docs/results/synthetic-absent-result.json')
    monkeypatch.setattr(E, 'MARKER_PATH', 'docs/results/synthetic-absent-marker.json')


def fake_git(head='a' * 40, committed=True):
    def git(args, root):
        if args[0] == 'rev-parse':
            return (head + '\n').encode()
        return (Path(root) / args[1][len('HEAD:'):]).read_bytes() if committed else b'different'
    return git


def authorize(env=None, git=None, probe=lambda: False):
    return E.authorize_execution(SPEC, SHA, ROOT, dict(GOOD_ENV, **(env or {})), git or fake_git(), probe)


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


# --------------------------------------------------------------------------- #
# Frozen spec and pins
# --------------------------------------------------------------------------- #
def test_frozen_spec_import_closure_and_scientific_label():
    assert SPEC['scientificStatus'] == 'EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY' == S.SCIENTIFIC_STATUS
    assert SPEC['boundary']['passFailSemantics'] == 'NONE' and SPEC['phase'].startswith('PROTOCOL_AND_HARNESS_ONLY')
    assert SPEC['boundary']['outcomeExecutionInThisChange'] is False and SPEC['boundary']['mayCallAnyFeatureValidatedOrPredictive'] is False
    assert SPEC['constants']['minPeers'] == 4 and SPEC['constants']['minIndustryMembers'] == 5
    assert SPEC['horizons'] == [63, 126, 252] and SPEC['primaryHorizon'] == 126
    assert SPEC['membership']['v4Decision'] == 'DATA_FOUNDATION_INSUFFICIENT_V4' and SPEC['input']['recollect'] is False
    assert SPEC['targets']['primary'].startswith('stock forward return minus leave-one-out CAP_WEIGHTED')


def test_pins_are_checked_byte_for_byte():
    assert E.verify_pins(SPEC, ROOT)
    for mutate, message in (
            (lambda s: s['membership']['files'].__setitem__(next(iter(s['membership']['files'])), '0' * 64), 'MEMBERSHIP_INPUT_CHANGED'),
            (lambda s: s['membership']['v4Facts'].__setitem__('classifiedNameDates', 1), 'V4_FACT_CHANGED'),
            (lambda s: s.__setitem__('benchmark', 'OTHER.KS'), 'BENCHMARK'),
            (lambda s: s['priorSealed']['resultFiles'].__setitem__(next(iter(s['priorSealed']['resultFiles'])), '0' * 64), 'PRIOR_SEALED_RESULT_CHANGED'),
            (lambda s: s['features']['definitions'][0].__setitem__('plain', 'changed'), 'FEATURE_DEFINITIONS_DIFFER'),
            (lambda s: s['features'].__setitem__('names', s['features']['names'][::-1]), 'FEATURE_')):
        tampered = copy.deepcopy(SPEC)
        mutate(tampered)
        with pytest.raises(ValueError, match=message):
            E.verify_pins(tampered, ROOT)


def test_feature_definitions_are_the_sealed_anatomys_and_the_repositorys():
    from pipeline import kr_value_quality_catalyst as F
    anatomy = json.loads((ROOT / 'research_specs/kr-factor-anatomy-v1.json').read_text())
    assert [d['name'] for d in SPEC['features']['definitions']] == list(F.RAW_FEATURES) == SPEC['features']['names']
    assert SPEC['features']['definitions'] == [{k: f[k] for k in ('name', 'family', 'orientation', 'plain', 'caveat')} for f in anatomy['factors']]
    assert SPEC['features']['withinIndustryTransform']['minimumFinitePeers'] == S.MIN_RANK_PEERS
    assert SPEC['features']['withinIndustryTransform']['frozenBeforeOutcomes'] is True
    assert 'pipeline/kr_value_quality_catalyst.py' in SPEC['dependencyHashes']  # the feature source is hash-pinned through the closure


def test_benchmark_return_basis_and_taxonomy_equal_the_accepted_framework():
    anatomy = json.loads((ROOT / 'research_specs/kr-factor-anatomy-v1.json').read_text())
    assert SPEC['benchmark'] == anatomy['benchmark'] == S.BENCHMARK == '069500.KS'
    assert SPEC['returnBasis'] == anatomy['returnDefinition']['label'] == S.RETURN_BASIS
    assert SPEC['membership']['coarseGroups'] == 14 == len(CROSSWALK['groups']) and SPEC['membership']['mappedRawLabels'] == len(CROSSWALK['mapping'])
    industry = json.loads((ROOT / 'research_specs/kr-industry-opportunity-anatomy-v1.json').read_text())
    assert SPEC['membership'] == industry['membership'] and SPEC['input'] == industry['input']


def test_module_constants_and_registries_equal_the_spec():
    spec_constants = SPEC['constants']
    assert spec_constants['minDateCrossSection'] == S.MIN_DATE_CROSS_SECTION == 30
    assert spec_constants['minGroupIndustryN'] == 3 * spec_constants['minGroupSize']
    assert SPEC['registry']['signViews'] == [list(v) for v in S.SIGN_VIEWS]
    assert set(S.QUESTIONS) == set(SPEC['questions']) and len(S.QUESTIONS) == 5
    changed = copy.deepcopy(SPEC)
    assert changed['registry']['sensitivities'] == ['FULL', 'EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX']
    assert SPEC['sensitivities']['excludedMegaCaps'] == ['005930.KS', '000660.KS']


# --------------------------------------------------------------------------- #
# Authorization, lock and the one-shot lifecycle
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize('env,reason', [({'GITHUB_ACTIONS': 'false'}, 'REQUIRES_ACTIONS'), ({'GITHUB_REF': 'refs/heads/x'}, 'REQUIRES_MAIN'),
                                        ({'GITHUB_EVENT_NAME': 'pull_request'}, 'WORKFLOW_DISPATCH'),
                                        ({'ANATOMY_INPUT_ARTIFACT': 'wrong'}, 'INPUT_ARTIFACT_IDENTITY_MISMATCH'),
                                        ({'ANATOMY_INPUT_RUN_ID': '1'}, 'INPUT_ARTIFACT_IDENTITY_MISMATCH')])
def test_authorization_refuses_outside_the_exact_context(env, reason):
    with pytest.raises(ValueError, match=reason):
        authorize(env)


def test_authorization_requires_the_committed_spec_head_and_no_lock_result_or_marker(monkeypatch):
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
    monkeypatch.setattr(E, 'RESULT_PATH', 'docs/results/absent.json')
    monkeypatch.setattr(E, 'MARKER_PATH', 'README.md')
    with pytest.raises(ValueError, match='MARKER_ALREADY_COMMITTED'):
        authorize()


def test_pull_request_environment_is_never_authorized():
    report = E.verify(ROOT, {'GITHUB_EVENT_NAME': 'pull_request'})
    assert report['status'] == 'VERIFIED' and report['executeAuthorizedInThisEnvironment'] is False
    assert report['stoppedBeforeOutcomes'] and report['historicalExecutionPerformed'] is False
    spec = importlib.util.spec_from_file_location('run_stock', ROOT / 'scripts/run_kr_stock_within_industry_anatomy_v1.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    with pytest.raises(ValueError, match='FORMAL_EXECUTION_REQUIRES_ACTIONS'):
        runner.run('execute', input_root='x', output='y', env={'GITHUB_EVENT_NAME': 'pull_request'})
    with pytest.raises(ValueError, match='UNREGISTERED_EXECUTION_MODE'):
        runner.run('anything')


def test_lock_prefix_is_the_registered_study_ref():
    assert E.LOCK_PREFIX == 'refs/tags/kr-stock-within-industry-anatomy-v1-execution-lock'


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
    with pytest.raises(ValueError, match='LOCK_REQUIRED'):
        E.require_lock(object(), SHA)


def test_outcomes_need_both_permit_and_lock_and_leave_counters_zero_on_refusal():
    counters = E.Counters()
    with pytest.raises(ValueError, match='WITHOUT_PERMIT'):
        E.forward_table({}, {}, None, SPEC, {}, object(), counters, None, SHA)
    with pytest.raises(ValueError, match='DURABLE_EXECUTION_LOCK_REQUIRED'):
        E.forward_table({}, {}, None, SPEC, {}, authorize(), counters, None, SHA)
    with pytest.raises(ValueError, match='WITHOUT_PERMIT'):
        E.load_prior_result(ROOT, SPEC, object(), counters)
    assert counters.zero()


def test_label_free_assembly_and_audit_never_touch_an_outcome(monkeypatch):
    def boom(*a, **k):
        raise AssertionError('OUTCOME_READ_ON_PULL_REQUEST')
    monkeypatch.setattr(A, 'endpoint_returns', boom)
    monkeypatch.setattr(AE, 'sealed_v1_function', boom)
    monkeypatch.setattr(E, 'forward_table', boom)
    monkeypatch.setattr(E, 'load_prior_result', boom)
    assert E.verify(ROOT)['counters'] == E.Counters().__dict__
    audit = E.readiness_audit(ROOT)
    assert audit['counters'] == E.Counters().__dict__ and audit['basedOnAnyReturnResult'] is False and audit['historicalExecutionPerformed'] is False


# --------------------------------------------------------------------------- #
# Readiness: one outcome-free decision and the exact membership-only eligibility
# --------------------------------------------------------------------------- #
def test_readiness_decision_is_one_of_two_and_structural():
    audit = E.readiness_audit(ROOT)
    assert audit['decision'] in ('READY_FOR_STOCK_WITHIN_INDUSTRY_ANATOMY_EXECUTION', 'DATA_BLOCKED_BEFORE_STOCK_WITHIN_INDUSTRY_ANATOMY')
    assert audit['decision'] == 'READY_FOR_STOCK_WITHIN_INDUSTRY_ANATOMY_EXECUTION' and all(audit['checks'].values()), audit['details']
    stored = E.verify_pins
    try:
        E.verify_pins = lambda *a, **k: (_ for _ in ()).throw(ValueError('PIN'))
        flipped = E.readiness_audit(ROOT)
    finally:
        E.verify_pins = stored
    assert flipped['decision'] == 'DATA_BLOCKED_BEFORE_STOCK_WITHIN_INDUSTRY_ANATOMY'
    assert 'signal-date market-cap availability of every peer (cap lens)' in audit['notMeasuredBeforeExecution']


def test_membership_only_eligibility_is_pinned_from_the_frozen_membership():
    audit = E.readiness_audit(ROOT)['membershipOnlyEligibility']
    full = audit['FULL']
    assert full['stockDates'] == 73200 and full['signalDates'] == 610
    assert full['byStatus'] == {'ELIGIBLE': 61049, 'INELIGIBLE_BELOW_MINIMUM_INDUSTRY_MEMBERS': 8707, 'INELIGIBLE_UNCLASSIFIED': 3444}
    assert full['unknownRetainedInDenominator'] == 3442 and full['eligibleIndustryDates'] == 5818 and full['industryDates'] == 8540
    assert full['eligibleStocksPerDate'] == {'min': 90, 'median': 100.0, 'max': 111} and full['datesWithAtLeastMinDateCrossSection'] == 610
    excl = audit['EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX']
    assert excl['stockDates'] == 73200 and excl['byStatus']['EXCLUDED_BY_SENSITIVITY'] == 1220 and excl['byStatus']['ELIGIBLE'] == 59829
    assert sum(full['byStatus'].values()) == full['stockDates']  # nothing is dropped from the denominator


def test_readiness_gates_report_reasons_without_reading_outcomes():
    rows = pd.DataFrame({'date': ['2020-01-03'] * 3, 'ticker': ['A', 'B', 'C'], 'marketCap': [1.0, 2.0, 3.0], **{c: 0.0 for c in S.FEATURES}})
    schedule = {'2020-01-03': ['A', 'B', 'C']}
    assert E.readiness_gates(rows, schedule, {'A': []}, SPEC, schedule) == []
    assert 'SIGNAL_DATES_DIFFER_FROM_V4_MEMBERSHIP_CALENDAR' in E.readiness_gates(rows, schedule, {'A': []}, SPEC, {'2020-01-10': ['A']})
    assert 'DUPLICATE_PIT_NAME_DATE' in E.readiness_gates(pd.concat([rows, rows]), schedule, {'A': []}, SPEC, schedule)
    assert 'MARKET_CAP_UNAVAILABLE' in E.readiness_gates(rows.assign(marketCap=np.nan), schedule, {'A': []}, SPEC, schedule)
    for column in ('relative126', 'momentum121', 'negativeDownsideVol126'):  # features the sealed industry gate did not require
        assert any(r.startswith('SIGNAL_TIME_COLUMNS_MISSING') for r in E.readiness_gates(rows.drop(columns=column), schedule, {'A': []}, SPEC, schedule))
    assert E.readiness_gates(rows.iloc[0:0], schedule, {}, SPEC, schedule) == ['NO_PIT_NAME_DATES']


# --------------------------------------------------------------------------- #
# Sealed studies are never rerun
# --------------------------------------------------------------------------- #
def test_sealed_studies_refuse_to_rerun_and_this_study_never_calls_them():
    env = dict(GOOD_ENV, REGIME_INPUT_ARTIFACT=SPEC['input']['artifactName'], REGIME_INPUT_RUN_ID=str(SPEC['input']['producingRunId']))
    spec_i, sha_i = IE.load_spec(ROOT)
    with pytest.raises(ValueError, match='RESULT_ALREADY_COMMITTED'):
        IE.authorize_execution(spec_i, sha_i, ROOT, env, fake_git(), lambda: False)
    spec_a, sha_a = AE.load_spec(ROOT)
    with pytest.raises(ValueError, match='RESULT_ALREADY_COMMITTED'):
        AE.authorize_execution(spec_a, sha_a, ROOT, env, fake_git())
    spec_r, sha_r = RE.load_spec(ROOT)
    with pytest.raises(ValueError, match='EXECUTION_LOCK_ALREADY_EXISTS'):
        RE.authorize_execution(spec_r, sha_r, ROOT, env, fake_git(), lambda: True)  # its lock tag exists on GitHub
    overlay = importlib.util.spec_from_file_location('run_overlay', ROOT / 'scripts/run_kr_model_overlay_portfolio_v1.py')
    runner = importlib.util.module_from_spec(overlay)
    overlay.loader.exec_module(runner)
    with pytest.raises(ValueError, match='EXECUTE_UNAUTHORIZED|REQUIRES_ACTIONS_MAIN|AUTHORIZATION_NOT_COMMITTED|SUBSTANTIVE_RESULT_ALREADY_CLOSED_V1'):
        runner.run('execute')
    for module in ('pipeline/kr_stock_within_industry_anatomy.py', 'pipeline/kr_stock_within_industry_anatomy_execution.py',
                   'scripts/run_kr_stock_within_industry_anatomy_v1.py'):
        text = (ROOT / module).read_text()
        for forbidden in ('run_kr_factor_anatomy', 'run_kr_top120_regime_review', 'run_kr_model_overlay', 'run_kr_industry_anatomy',
                          'IE.execute(', 'IE.claim_execution_lock', 'AE.execute(', 'RE.execute(', 'X.execute(', 'collect_dart', 'KRX_API'):
            assert forbidden not in text


def test_prior_sealed_results_and_spec_seals_are_unchanged():
    assert (ROOT / 'research_specs/kr-model-overlay-portfolio-v1.sha256').read_text().strip() == '563b64ee6f4709a263719669f795ad55e7828e340f082358af1599453253b6fd'
    assert (ROOT / 'research_specs/kr-industry-opportunity-anatomy-v1.sha256').read_text().strip() == '98278ce5724b27dd19d253eab6cb1e7854ea432a62098441cdad46d067609f55'
    assert set(SPEC['priorSealed']['neverRerun']) == {'kr-model-overlay-portfolio-v1', 'kr-factor-anatomy-v1', 'kr-top120-regime-review-v1',
                                                      'kr-industry-opportunity-anatomy-v1'}
    assert SPEC['priorSealed']['referenceResult'] in SPEC['priorSealed']['resultFiles']


def test_workflow_never_executes_on_pull_requests_and_has_one_write_permission():
    workflow = (ROOT / '.github/workflows/kr-stock-within-industry-anatomy-v1.yml').read_text()
    for other in ('run_kr_factor_anatomy', 'run_kr_top120_regime_review', 'run_kr_industry_anatomy', 'kr-model-overlay-portfolio-v1 execute',
                  'collect_dart', 'KRX_API', 'schedule:', 'cron'):
        assert other not in workflow
    execute = workflow[workflow.index('  execute:'):]
    assert "github.event_name == 'workflow_dispatch' && inputs.mode == 'execute'" in execute and 'refs/heads/main' in execute
    assert 'contents: write' in execute and workflow.count('contents: write') == 1
    assert '--mode execute' in execute and '--mode execute' not in workflow.split('  execute:')[0]
    assert 'pull_request' in workflow and 'listMatchingRefs' in execute and 'getArtifact' in execute and 'digest' in execute


# --------------------------------------------------------------------------- #
# Machinery on synthetic prices (the real endpoint rule and the sealed v1 target as the cross-check)
# --------------------------------------------------------------------------- #
def test_forward_table_and_panel_on_synthetic_prices():
    days = RC.sessions('2018-01-01', '2021-12-31', 'KR')
    tickers = [f'S{i}.KS' for i in range(6)]
    rng = np.random.default_rng(1)
    prices = {t: pd.DataFrame({'Close': 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, len(days)))}, index=days) for t in tickers + [S.BENCHMARK]}
    date = str(days[300].date())
    schedule = {date: tickers}
    counters = E.Counters()
    lock = E.claim_execution_lock(SHA, GOOD_ENV, FakeApi())
    v1_spec, _ = E.X.load_spec(ROOT)
    forward, windows = E.forward_table(prices, schedule, days, SPEC, v1_spec, authorize(), counters, lock, SHA)
    assert counters.outcomeColumnCalls == 3 * 6 and counters.targetCalls == counters.labelCalls == 18
    for h in S.HORIZONS:
        assert windows[(date, h)] == (str(days[301].date()), str(days[301 + h].date()))
    intervals = {t: [{'start': None, 'end': None, 'label': '반도체 제조업', 'status': 'RECONSTRUCTED_STABLE_NO_CHANGE_EVENT',
                      'reconstruction_status': 'RECONSTRUCTED_STABLE_NO_CHANGE_EVENT'}] for t in tickers}
    membership = I.membership_table(schedule, intervals, CROSSWALK)
    features = pd.DataFrame({'date': date, 'ticker': tickers, 'marketCap': np.arange(1.0, 7.0), **{c: np.arange(6.0) for c in S.FEATURES}})
    panel = S.build_stock_panel(membership, features, forward, windows)
    assert S.assert_identity(panel) and panel.status.eq('ELIGIBLE').all()
    for h in S.HORIZONS:
        matured = panel[f'status_CAP_WEIGHTED_{h}'].eq('MATURED')
        assert matured.all()
        for i, t in enumerate(tickers):
            peers = [p for p in tickers if p != t]
            peer_caps = {p: float(tickers.index(p) + 1) for p in peers}
            total = sum(peer_caps.values())
            expected = sum(peer_caps[p] / total * forward[(date, h)][p][0] for p in peers)
            row = panel[panel.ticker == t].iloc[0]
            assert row[f'loo_CAP_WEIGHTED_{h}'] == pytest.approx(expected)
            assert row[f'loo_EQUAL_WEIGHT_{h}'] == pytest.approx(np.mean([forward[(date, h)][p][0] for p in peers]))
