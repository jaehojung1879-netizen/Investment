"""The Atlas audit must leave the Atlas untouched and be reproducible; no outcome enters an entry state."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("research.track_b_pilot.audit_atlas")
from research.track_b_pilot import audit_atlas as AU  # noqa: E402

HERE = Path(AU.__file__).resolve().parent


def test_atlas_json_is_byte_identical_to_the_pinned_original():
    assert hashlib.sha256((HERE / "drawdown-atlas.json").read_bytes()).hexdigest() == AU.ATLAS_SHA256


def test_forward_arrays_next_close_shifts_entry_by_one_session():
    tr = np.linspace(100.0, 130.0, 40)
    tr[5] = 80.0  # a dip only visible to an entry at or before session 5
    f0, m0 = AU.forward_arrays(tr, 0)[21]
    f1, m1 = AU.forward_arrays(tr, 1)[21]
    assert f0[0] == pytest.approx(tr[21] / tr[0] - 1)
    assert f1[0] == pytest.approx(tr[22] / tr[1] - 1)
    assert m1[0] == pytest.approx(tr[2:23].min() / tr[1] - 1)
    assert np.isnan(f0[19]) and not np.isnan(f0[18])  # 18 + 21 = 39 is the last session


def test_contrast_refuses_to_read_a_side_with_fewer_than_three_spells():
    a = {"252": {"meanReturn": -0.1, "lossProbability": 0.5, "medianFurtherMin": -0.2, "nSpells": 2}}
    b = {"252": {"meanReturn": 0.1, "lossProbability": 0.1, "medianFurtherMin": -0.1, "nSpells": 5}}
    assert AU.contrast(a, b)["status"] == "INSUFFICIENT_SPELLS_NOT_READ"
    a["252"]["nSpells"] = 3
    assert AU.contrast(a, b)["status"] == "SAME_DIRECTION_ALL_THREE"


def test_full_audit_is_deterministic_and_reproduces_atlas_cells():
    first = AU.build()
    assert first["atlasCellsReproducedExactly"] is True
    assert AU.render(first) == AU.render(AU.build())
    assert first["noPValues"] and first["noStrategy"] and first["noNewVariables"]


# ---- follow-up audit ----
from research.track_b_pilot import audit_atlas_followup as FU  # noqa: E402


def _cell(gap_days, gap_spells):
    return {"close_t/days": {"gap": {"252": gap_days}}, "close_t/spells": {"gap": {"252": gap_spells}}}


def _g(mean, loss, n=(5, 5)):
    return {"mean": mean, "loss": loss, "median": mean, "furtherMinMedian": -0.1, "spellsAdverseBenign": list(n)}


def test_classification_needs_both_episodes_removed_view_to_call_a_pattern_similar():
    good = _cell(_g(-0.1, 0.2), _g(-0.1, 0.2))
    views = {v: good for v in ("full", "excl_2000_episode", "excl_2007_episode", "excl_both_episodes")}
    assert FU.classify(views)["classification"] == "SIMILAR_ACROSS_INDEPENDENT_EPISODES"
    views["excl_both_episodes"] = _cell(_g(-0.1, 0.2, (2, 5)), _g(-0.1, 0.2, (2, 5)))  # < 3 spells: unreadable
    assert FU.classify(views)["classification"] == "INSUFFICIENT_SAMPLE"
    views["excl_both_episodes"] = _cell(_g(0.1, -0.2), _g(0.1, -0.2))  # readable and reversed
    assert FU.classify(views)["classification"] == "DEPENDS_ON_SPECIFIC_EPISODES"


def test_classification_does_not_classify_a_pattern_that_is_absent_in_the_full_sample():
    bad = _cell(_g(0.1, -0.1), _g(0.1, -0.1))
    views = {v: bad for v in ("full", "excl_2000_episode", "excl_2007_episode", "excl_both_episodes")}
    assert FU.classify(views)["classification"] == "DIRECTION_ABSENT_IN_FULL"


def test_strict_variant_removes_only_entries_whose_window_reaches_the_episode():
    f = np.arange(100, dtype=float)
    out = FU.strict_arrays({21: (f.copy(), f.copy())}, 1, [(60, 80)])[21][0]
    assert np.isnan(out[38:60]).all() and not np.isnan(out[37]) and not np.isnan(out[60])  # 60 - 21 - 1 = 38


def test_followup_is_deterministic_and_leaves_atlas_untouched():
    a, b = FU.build(), FU.build()
    assert FU.render(a) == FU.render(b)
    assert hashlib.sha256((HERE / "drawdown-atlas.json").read_bytes()).hexdigest() == AU.ATLAS_SHA256
    assert a["classificationIsStatistical"] is False and a["noNewVariables"]
