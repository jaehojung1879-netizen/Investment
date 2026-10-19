import itertools

import pytest

from pipeline import kr_market_risk_model as K
from pipeline import rp1_c_risk_state_receipt as C

SIGNAL = "2026-09-11"  # a Friday KR weekly decision session


def test_all_twelve_observed_cells_equal_the_sealed_mapping():
    for s, t, f in itertools.product((0, 1), (0, 1), (0, 1, 2)):
        r = C.build_preview(SIGNAL, s, t, f)
        assert r["multipliers"] == {c: K.rule(c, s, t, f) for c in K.CANDIDATE_ORDER}
        assert r["undeterminedCandidates"] == [] and C.validate_preview(r)


def test_missing_layer_is_neither_benign_nor_adverse():
    r = C.build_preview(SIGNAL, None, None, 1)  # C0 reads FAST only; C1-C3 depend on the missing layers
    assert r["multipliers"]["C0"] == K.rule("C0", 0, 0, 1)
    assert r["multipliers"]["C1"] is None and "C1" in r["undeterminedCandidates"]
    severe = C.build_preview(SIGNAL, None, None, 2)  # a severe FAST break is 0.4 whatever the others are
    assert set(severe["multipliers"].values()) == {K.MINIMUM}


def test_state_outside_frozen_domain_is_refused():
    with pytest.raises(ValueError, match="STATE_OUTSIDE_FROZEN_DOMAIN"):
        C.build_preview(SIGNAL, 2, 0, 0)
    with pytest.raises(ValueError, match="STATE_OUTSIDE_FROZEN_DOMAIN"):
        C.build_preview(SIGNAL, 0, 0, 0.5)


def test_non_decision_session_is_refused():
    with pytest.raises(ValueError, match="WEEKLY_DECISION_SESSION"):
        C.build_preview("2026-09-10", 0, 0, 0)


def test_preview_cannot_claim_ledger_evidence_and_digest_detects_tampering():
    r = C.build_preview(SIGNAL, 1, 1, 1)
    bad = dict(r, evidenceClass="PROSPECTIVE_PAPER")
    bad["receiptSha256"] = C.P.receipt_digest(bad)
    with pytest.raises(ValueError, match="LEDGER_EVIDENCE"):
        C.validate_preview(bad)
    r["multipliers"]["C0"] = 1.0
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        C.validate_preview(r)


def test_module_is_kr_only_writes_nothing_and_touches_no_us_c1_machinery():
    src = open(C.__file__, encoding="utf-8").read()
    assert "P.append" not in src and "open(" not in src
    imports = [ln for ln in src.splitlines() if ln.startswith(("from .", "import "))]
    assert not any("c1" in ln or "execut" in ln for ln in imports)


def _resign(receipt):
    receipt['receiptSha256'] = C.P.receipt_digest(receipt)
    return receipt


def test_resigned_allowed_multiplier_substitution_is_rejected():
    r = C.build_preview(SIGNAL, 0, 0, 0)
    r['multipliers']['C0'] = K.REDUCED
    _resign(r)
    with pytest.raises(ValueError):
        C.validate_preview(r)


def test_resigned_layer_substitution_is_rejected_when_mapping_disagrees():
    r = C.build_preview(SIGNAL, 0, 0, 0)
    r['layers']['fast'] = 2
    _resign(r)
    with pytest.raises(ValueError):
        C.validate_preview(r)


def test_resigned_undetermined_substitution_is_rejected():
    r = C.build_preview(SIGNAL, None, None, 1)
    r['undeterminedCandidates'] = []
    _resign(r)
    with pytest.raises(ValueError):
        C.validate_preview(r)


STATES = list(itertools.product((0, 1, None), (0, 1, None), (0, 1, 2, None)))


@pytest.mark.parametrize('states', STATES)
def test_all_observed_and_missing_state_combinations_validate_independently(states, monkeypatch):
    from copy import deepcopy
    import json
    r = C.build_preview(SIGNAL, *states)
    expected = {c: K.multiplier(c, *states) for c in K.CANDIDATE_ORDER}
    assert r['multipliers'] == expected
    assert r['undeterminedCandidates'] == [c for c in K.CANDIDATE_ORDER if expected[c] is None]
    assert set(r) == set(C.REQUIRED) | {'receiptSha256'}
    before = deepcopy(r)
    # External JSON is validated without delegating to the producer or mutation.
    monkeypatch.setattr(C, 'build_preview', lambda *a: pytest.fail('validator called builder'))
    assert C.validate_preview(json.loads(json.dumps(r)))
    assert r == before


@pytest.mark.parametrize('states', STATES)
@pytest.mark.parametrize('candidate', K.CANDIDATE_ORDER)
def test_every_candidate_rejects_resigned_alternative_levels_and_null(states, candidate):
    from copy import deepcopy
    r = C.build_preview(SIGNAL, *states)
    for replacement in (*K.LEVELS, None):
        if replacement == r['multipliers'][candidate]:
            continue
        bad = deepcopy(r)
        bad['multipliers'][candidate] = replacement
        _resign(bad)
        with pytest.raises(ValueError):
            C.validate_preview(bad)


@pytest.mark.parametrize('layer', C.LAYER_KEYS)
@pytest.mark.parametrize('value', [True, False, '1', [], {}, .5, -1, 3, float('nan'), float('inf'), -float('inf'), 10**400])
def test_invalid_layer_types_domains_and_numbers_are_rejected(layer, value):
    r = C.build_preview(SIGNAL, 0, 0, 0)
    r['layers'][layer] = value
    # Non-finite JSON cannot be signed by the canonical helper. Re-sign every
    # representable attack; malformed numbers still must raise ValueError.
    try:
        _resign(r)
    except (TypeError, ValueError, OverflowError):
        pass
    with pytest.raises(ValueError):
        C.validate_preview(r)


@pytest.mark.parametrize('field,value', [
    ('schemaVersion', True), ('schemaVersion', 1.0), ('schemaVersion', '1'), ('schemaVersion', 2),
    ('studyId', 'other-study'), ('studyId', None), ('studyId', []),
    ('modelVersion', 'other-model'), ('modelVersion', None), ('modelVersion', {}),
    ('evidenceClass', 'PROSPECTIVE_PAPER'), ('evidenceClass', []), ('region', 'US'), ('region', []),
    ('ledgerWritten', True), ('ledgerWritten', 0), ('ledgerWritten', 'false'),
    ('layers', []), ('layers', None), ('multipliers', []), ('multipliers', None),
    ('undeterminedCandidates', None), ('undeterminedCandidates', {}), ('undeterminedCandidates', 'C0'),
    ('undeterminedCandidates', [None]), ('undeterminedCandidates', ['C9']),
    ('signalDate', None), ('signalDate', 20260911), ('signalDate', []), ('signalDate', {}),
    ('signalDate', '20260911'), ('signalDate', '2026-W37-5'), ('signalDate', '2026-9-11'),
    ('signalDate', '2026-09-11T00:00:00'), ('signalDate', '2026-09-11T00:00:00Z'),
    ('signalDate', 'NaT'), ('signalDate', '2026-02-30'), ('signalDate', '2026-09-10'),
    ('signalDate', '2026-09-12'), ('signalDate', '2026-10-09'), ('signalDate', '2036-01-04'),
])
def test_resigned_contract_type_identity_and_calendar_violations(field, value):
    r = C.build_preview(SIGNAL, 0, 0, 0)
    r[field] = value
    _resign(r)
    with pytest.raises(ValueError):
        C.validate_preview(r)


@pytest.mark.parametrize('field', C.REQUIRED + ('receiptSha256',))
def test_each_missing_field_is_a_validation_error(field):
    r = C.build_preview(SIGNAL, 0, 0, 0)
    del r[field]
    if field != 'receiptSha256':
        _resign(r)
    with pytest.raises(ValueError, match='FIELD_MISSING'):
        C.validate_preview(r)


@pytest.mark.parametrize('value', [None, [], (), 'receipt', 1, False])
def test_non_object_receipts_raise_validation_errors(value):
    with pytest.raises(ValueError):
        C.validate_preview(value)


@pytest.mark.parametrize('part,key', [('layers', 'slow'), ('layers', 'extra'), ('multipliers', 'C0'), ('multipliers', 'C9')])
def test_exact_layer_and_candidate_key_sets(part, key):
    r = C.build_preview(SIGNAL, 0, 0, 0)
    if key in r[part]:
        del r[part][key]
    else:
        r[part][key] = 0
    _resign(r)
    with pytest.raises(ValueError):
        C.validate_preview(r)


@pytest.mark.parametrize('value', [True, False, '1.0', [], {}, float('nan'), float('inf'), -.4, .7000000000000001, 10**400])
def test_multiplier_non_numeric_nonfinite_and_inexact_values(value):
    r = C.build_preview(SIGNAL, 0, 0, 0)
    r['multipliers']['C0'] = value
    try:
        _resign(r)
    except (TypeError, ValueError, OverflowError):
        pass
    with pytest.raises(ValueError):
        C.validate_preview(r)


@pytest.mark.parametrize('value', [[], ['C1'], ['C1', 'C2', 'C3', 'C3'], ['C3', 'C2', 'C1']])
def test_missing_candidate_list_must_equal_exact_ordered_none_results(value):
    r = C.build_preview(SIGNAL, None, None, 1)
    assert r['undeterminedCandidates'] == ['C1', 'C2', 'C3']
    r['undeterminedCandidates'] = value
    _resign(r)
    with pytest.raises(ValueError):
        C.validate_preview(r)


@pytest.mark.parametrize('value', [None, 1, [], 'g'*64, 'a'*63, 'A'*64])
def test_malformed_digest_is_a_validation_error(value):
    r = C.build_preview(SIGNAL, 0, 0, 0)
    r['receiptSha256'] = value
    with pytest.raises(ValueError, match='DIGEST_MISMATCH'):
        C.validate_preview(r)


def test_schema_one_rejects_added_output_or_nested_outcome_fields():
    for key in ('extra', 'weights', 'outcome'):
        r = C.build_preview(SIGNAL, 0, 0, 0)
        r[key] = {'outcome': 0}
        _resign(r)
        with pytest.raises(ValueError):
            C.validate_preview(r)


def test_weekly_decision_can_be_thursday_before_calendar_holiday():
    r = C.build_preview('2026-10-08', 0, 0, 0)
    assert r['signalDate'] == '2026-10-08' and C.validate_preview(r)


def test_builder_normalizes_nan_and_integral_states_without_changing_output():
    assert C.build_preview(SIGNAL, float('nan'), None, 2.0) == C.build_preview(SIGNAL, None, None, 2)
    assert C.build_preview(SIGNAL, 1.0, 0.0, 1.0) == C.build_preview(SIGNAL, 1, 0, 1)
    for invalid in (True, '1', [], {}, float('inf')):
        with pytest.raises(ValueError):
            C.build_preview(SIGNAL, invalid, 0, 0)


def test_validator_calls_frozen_multiplier_for_each_candidate(monkeypatch):
    r = C.build_preview(SIGNAL, None, 1, 1)
    calls = []
    original = K.multiplier
    def observed(candidate, slow, transition, fast):
        calls.append((candidate, slow, transition, fast))
        return original(candidate, slow, transition, fast)
    monkeypatch.setattr(K, 'multiplier', observed)
    assert C.validate_preview(r)
    assert calls == [(c, None, 1, 1) for c in K.CANDIDATE_ORDER]


@pytest.mark.parametrize('states,layer,replacement', [((0, 1, 0), 'slow', 1), ((1, 0, 0), 'transition', 1), ((0, 0, 0), 'fast', 2)])
def test_each_resigned_valid_layer_change_requires_matching_model_output(states, layer, replacement):
    r = C.build_preview(SIGNAL, *states)
    r['layers'][layer] = replacement
    _resign(r)
    with pytest.raises(ValueError, match='DISAGREE_WITH_FROZEN_MODEL'):
        C.validate_preview(r)


@pytest.mark.parametrize('states', STATES)
def test_resigned_wrong_none_list_is_rejected_for_every_state_combination(states):
    r = C.build_preview(SIGNAL, *states)
    r['undeterminedCandidates'] = [] if r['undeterminedCandidates'] else ['C0']
    _resign(r)
    with pytest.raises(ValueError, match='UNDETERMINED_CANDIDATES_DISAGREE'):
        C.validate_preview(r)


def test_normal_builder_outputs_are_byte_equivalent_to_requested_head():
    import subprocess
    original = subprocess.check_output([
        'git', 'show', 'bd86901d12168a4ada40e6d0f075e9d9953b2538:pipeline/rp1_c_risk_state_receipt.py'], text=True)
    legacy = {'__name__': 'pipeline._pr266_legacy_preview', '__package__': 'pipeline'}
    exec(compile(original, '<PR266 requested source>', 'exec'), legacy)
    for states in STATES:
        before = legacy['build_preview'](SIGNAL, *states)
        after = C.build_preview(SIGNAL, *states)
        assert C.P.canonical(before) == C.P.canonical(after)
