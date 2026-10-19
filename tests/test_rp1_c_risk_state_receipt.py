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
