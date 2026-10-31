"""Invented cost schedules and published scalar fixtures; no outcome engine."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import math

import pytest

from scripts import analyze_c2_aggregate_evidence as A


def fixture():
    common = dict(available=True, startDate='2013-01-07', endDate='2026-09-14', sessions=3547,
                  blocks=155, years=13.6841, initialCapitalKrw=50000000, averageNamesHeld=3,
                  averageBenchmarkWeightPct=40.59, nameTrades=545)
    c2 = {**common, 'cagrPct': 14.258, 'grossCagrPct': 15.910, 'maxDrawdownPct': -32.027,
          'annualizedVolatilityPct': 17.028, 'annualizedDownsideVolatilityPct': 17.492,
          'oneWayTurnoverPerYear': 4.195, 'annualizedCostDragPct': 1.652,
          'totalCostPctOfNav': 19.627, 'arithmeticActiveReturnPpPerYear': .620,
          'geometricMinusArithmeticPp': 1.131, 'excessCagrPp': 1.752,
          'halves': {'splitDate': '2019-10-22', 'firstHalfCagrPct': 8.580, 'secondHalfCagrPct': 20.146},
          'excessByCalendarYearPp': {'2017': 1., '2018': -1.}, 'topContributions': []}
    p0 = {**c2, 'cagrPct': 12.507, 'grossCagrPct': 12.511, 'totalCostPctOfNav': .055,
          'maxDrawdownPct': -40.806, 'annualizedVolatilityPct': 22.349,
          'annualizedDownsideVolatilityPct': 23.351, 'oneWayTurnoverPerYear': 0,
          'annualizedCostDragPct': .005, 'averageBenchmarkWeightPct': 100,
          'halves': {'splitDate': '2019-10-22', 'firstHalfCagrPct': 2.134, 'secondHalfCagrPct': 23.753}}
    c1 = {**c2, 'cagrPct': 10.395, 'grossCagrPct': 11.953, 'annualizedCostDragPct': 1.558,
          'maxDrawdownPct': -19.801, 'oneWayTurnoverPerYear': 3.886}
    doc = {'regions': {'KR': {'benchmark': '069500.KS', 'baseCurrency': 'KRW',
                            'benchmarkDefinition': 'PHASE_C_RECONCILED_GROSS_ETF_TOTAL_RETURN',
                            'paths': {'C2': c2, 'C1': c1, 'P0': p0}}},
           'finalAnchorCalibration': {'regions': {'KR': {'ordering': {
               'established': False, 'rankICTStat': .677, 'topMinusBottomTStat': 1.422}}}}}
    return doc


def test_aggregate_falsification_keeps_cost_risk_and_selection_distinct():
    doc = fixture()
    before = deepcopy(doc)
    result = A.analyze(doc, doc)
    assert doc == before
    diff = result['contrastsFromRoundedPublishedScalars']
    assert diff['C2_MINUS_PASSIVE']['maxDrawdownPct'] == pytest.approx(8.779)
    assert diff['C2_MINUS_C1']['maxDrawdownPct'] == pytest.approx(-12.226)
    assert diff['C2_MINUS_C1']['cagrPct'] == pytest.approx(3.863)
    assert diff['C2_MINUS_C1']['annualizedCostDragPct'] == pytest.approx(.094)
    assert result['decomposition']['geometricResidualSharePct'] == pytest.approx(64.5547945205)
    assert result['decomposition']['causalStockSelectionAlpha'] is None
    assert result['stability']['c2MinusPassiveHalfCagrPp']['secondHalfCagrPct'] == pytest.approx(-3.607)
    assert result['verdict'] == 'INCONCLUSIVE' and result['validatedAlpha'] is False
    assert result['calibration']['directC2ConvictionRankingTest'] is False


def test_conservative_matched_cost_bounds_rule_out_three_x_but_not_two_x():
    paths = fixture()['regions']['KR']['paths']
    two, three = [A.cost_bounds(paths['C2'], paths['P0'], k) for k in (2, 3)]
    assert two['edgeUpperPp'] == .129648
    assert three['edgeUpperPp'] == -1.470084
    assert two['positiveEdgeRuledOutOnRecordedBasis'] is False
    assert three['positiveEdgeRuledOutOnRecordedBasis'] is True
    assert two['candidateNetCagrUpperPct'] >= 12.6310166315
    assert three['passiveNetCagrLowerPct'] <= 12.4967997656


def test_bound_encloses_invented_exact_stress_and_is_not_identified_as_exact():
    # Equal 1x retention but different 2x/3x results proves aggregate nonidentification.
    schedules = [[.1], [1-math.sqrt(.9)]*2]
    candidate = {'years': 10., 'grossCagrPct': 10., 'cagrPct': ((1.1**10)*.9)**.1*100-100}
    passive = {'years': 10., 'grossCagrPct': 5., 'totalCostPctOfNav': .05}
    for k in (2, 3):
        bound = A.cost_bounds(candidate, passive, k)
        exact = [((1.1**10)*math.prod(1-k*c for c in schedule))**.1*100-100 for schedule in schedules]
        assert exact[0] != pytest.approx(exact[1])
        assert max(exact) <= bound['candidateNetCagrUpperPct']
        assert bound['status'] == 'CONDITIONAL_BOUND_NOT_REPLAY'


def test_missing_or_invalid_measurement_never_becomes_zero():
    assert A.number({'x': 0}, 'x') == Decimal(0)
    for value in (None, True, math.nan, math.inf, '0'):
        with pytest.raises(ValueError, match='UNMEASURED_OR_INVALID'):
            A.number({'x': value}, 'x')


@pytest.mark.parametrize('key,value', [('sessions', 3546), ('initialCapitalKrw', 1), ('endDate', '2026-09-13')])
def test_mismatched_samples_are_not_compared(key, value):
    doc = fixture()
    doc['regions']['KR']['paths']['C2'][key] = value
    with pytest.raises(ValueError, match='NONCOMMON_CALENDAR_OR_CAPITAL'):
        A.analyze(doc, doc)


def test_unknown_stress_domain_abstains():
    candidate = {'years': 10., 'grossCagrPct': 10., 'cagrPct': -10.}
    passive = {'years': 10., 'grossCagrPct': 5., 'totalCostPctOfNav': .05}
    result = A.cost_bounds(candidate, passive, 3)
    assert result['status'] == 'DOMAIN_NOT_PROVEN' and result['edgeUpperPp'] is None


def test_source_tampering_aborts_before_output(monkeypatch, tmp_path):
    monkeypatch.setattr(A.subprocess, 'check_output', lambda *a, **k: b'{}')
    output = tmp_path/'fake.json'
    with pytest.raises(ValueError, match='SOURCE_HASH_MISMATCH'):
        A.main(['--output', str(output)])
    assert not output.exists()


def test_real_aggregate_reproduction_is_deterministic_and_cannot_overwrite(tmp_path):
    output = tmp_path/'actual.json'
    A.main(['--output', str(output)])
    actual = json.loads(output.read_text())
    assert actual['historicalLedgerReads'] == actual['valuationCalls'] == actual['modelFits'] == 0
    assert actual['recordedExcessCagrPp'] == 1.752
    assert actual['costBounds'][1]['edgeUpperPp'] < 0
    assert hashlib.sha256(output.read_bytes()).hexdigest() == '9141dea7364bbd3fc37ba5d3e9d4bbf1682ba67ad27faa893dc96e1471b14cdc'
    again = tmp_path/'again.json'
    A.main(['--output', str(again)])
    assert output.read_bytes() == again.read_bytes()
    with pytest.raises(FileExistsError):
        A.main(['--output', str(output)])


def annual_fixture():
    passive = {'startDate': '2017-01-03', 'endDate': '2019-09-30',
               'calendarYearReturnPct': {'2017': 10., '2018': -10., '2019': 0.}}
    candidate = {'calendarYearReturnPct': {'2017': 5., '2018': 0., '2019': .0004},
                 'excessByCalendarYearPp': {'2017': -5., '2018': 10., '2019': .0004}}
    return candidate, passive


def test_annual_direction_is_post_hoc_and_rounded_zero_abstains():
    candidate, passive = annual_fixture()
    result = A.calendar_context(candidate, passive)
    assert result['allYears']['UP']['losses'] == 1
    assert result['allYears']['DOWN']['wins'] == 1
    assert result['allYears']['UNDETERMINED']['unresolvedByRounding'] == 1
    assert result['rows'][2]['outperformed'] is None
    assert result['directionIsExPostOutcomeContext'] is True
    assert result['betaMatchedSelectionAlpha'] is None
    assert result['interiorYearsExcludingWindowBookends']['DOWN']['years'] == 1


def test_annual_context_refuses_dropped_year_or_inconsistent_excess():
    candidate, passive = annual_fixture()
    del candidate['excessByCalendarYearPp']['2018']
    with pytest.raises(ValueError, match='NONCOMMON_OR_MISSING_CALENDAR_YEARS'):
        A.calendar_context(candidate, passive)
    candidate, passive = annual_fixture()
    candidate['excessByCalendarYearPp']['2018'] = -5.
    with pytest.raises(ValueError, match='INCONSISTENT_PUBLISHED_ANNUAL_EXCESS'):
        A.calendar_context(candidate, passive)


def test_double_rounded_source_excess_cannot_turn_raw_tie_into_win():
    # Source E=round(round(C_raw,3)-B_raw,3): equal .0005 can publish E=.001.
    candidate, passive = annual_fixture()
    passive['calendarYearReturnPct']['2019'] = .001
    candidate['calendarYearReturnPct']['2019'] = .001
    candidate['excessByCalendarYearPp']['2019'] = .001
    row = A.calendar_context(candidate, passive)['rows'][2]
    assert row['outperformed'] is None


def test_same_marginal_volatility_can_have_different_beta_and_no_identified_alpha():
    # Invented demeaned daily returns: .5*x vs an orthogonal vector, same sigma.
    x, a, b = [.01, -.01, .01, -.01], [.005, -.005, .005, -.005], [.005, .005, -.005, -.005]
    beta = lambda y: sum(u*v for u, v in zip(x, y))/sum(u*u for u in x)
    assert beta(a) == .5 and beta(b) == 0
    bound = A.exposure_bound({'annualizedVolatilityPct': 10.}, {'annualizedVolatilityPct': 20.})
    assert bound['absoluteBetaUpperBound'] >= max(abs(beta(a)), abs(beta(b)))
    assert bound['unitBetaFeasibleOnRecordedBasis'] is False
    assert bound['estimatedBeta'] is bound['selectionAlpha'] is None
    absent = A.exposure_bound({'annualizedVolatilityPct': 0}, {'annualizedVolatilityPct': 0})
    assert absent['absoluteBetaUpperBound'] is None


def test_real_v2_context_keeps_v1_result_immutable_and_direction_nonpredictive(tmp_path):
    original = A.ROOT/'research/c2_aggregate_evidence_v1/result.json'
    before = original.read_bytes()
    output = tmp_path/'v2.json'
    A.main(['--calendar-context', '--output', str(output)])
    result = json.loads(output.read_text())
    context = result['publishedCalendarContext']
    assert result['id'] == 'c2-aggregate-falsification-v2'
    assert context['allYears']['DOWN'] == {'years': 5, 'wins': 5, 'losses': 0, 'unresolvedByRounding': 0}
    assert context['allYears']['UP'] == {'years': 9, 'wins': 2, 'losses': 7, 'unresolvedByRounding': 0}
    assert context['interiorYearsExcludingWindowBookends']['UP']['wins'] == 1
    assert context['interiorYearsExcludingWindowBookends']['UP']['years'] == 7
    assert result['fallbackReplacement']['arithmeticActiveNetDifferencePpPerYear'] == 4.202
    assert result['fallbackReplacement']['geometricMinusArithmeticDifferencePp'] == -.34
    assert result['fallbackReplacement']['causalSelectionEffect'] is None
    assert result['exposureBound']['absoluteBetaUpperBound'] < .762
    assert result['exposureBound']['unitBetaFeasibleOnRecordedBasis'] is False
    assert original.read_bytes() == before
