"""US factor reboot Phase C: outcome-blind unique-variation statistics.

Pinned here:
  * R^2 is computed on within-date percentile ranks, so a monotone transform of a feature changes nothing;
  * a feature identical to one of its controls reads controlR2 = 1, an independent one reads near 0;
  * a feature is never controlled by its own family's representative, and every representative belongs to its family;
  * a date with no complete case yields no statistic rather than a crash or a zero (the empty-frame column-selection trap);
  * joint attrition can only fall as families are added, and a tighter stale rule can only remove rows;
  * neither the module nor its runner imports an outcome, label, model or portfolio module, and the committed report says so.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import us_factor_unique_variation as UV        # noqa: E402

REPORT = ROOT / "docs/us-readiness/us-factor-unique-variation-v1.json"


def frame(n=150, dates=("2020-01-03", "2020-04-03"), seed=7):
    rng = np.random.default_rng(seed)
    rows = []
    for d in dates:
        base = {f: rng.normal(size=n) for f in UV.FEATURES}
        sectors = rng.choice(["A", "B", "C"], size=n)
        for i in range(n):
            rows.append({"date": d, "ticker": "T%d" % i, "sector": sectors[i], **{f: float(base[f][i]) for f in UV.FEATURES}})
    return pd.DataFrame(rows)


def test_representatives_belong_to_their_family_and_controls_exclude_the_own_family():
    for fam, rep in UV.REPRESENTATIVES.items():
        assert rep in UV.FAMILIES[fam]
    assert set(UV.REPRESENTATIVES) == set(UV.FAMILIES) == set(UV.ATTRITION_ORDER)
    for feature in UV.FEATURES:
        controls = UV.controls_for(feature)
        assert all(UV.FAMILY_OF[c] != UV.FAMILY_OF[feature] for c in controls)
        assert len(controls) == len(UV.FAMILIES) - 1
    assert "logMarketCapProxy" not in UV.REPRESENTATIVES.values()


def test_a_feature_equal_to_a_control_is_fully_explained_and_an_independent_one_is_not():
    f = frame()
    f["roe"] = f["mom121"] * 3.0 + 1.0                        # linear in a control's value, so identical rank
    out = UV.unique_variation(f)
    assert out["roe"]["controlR2"]["mean"] == pytest.approx(1.0, abs=1e-9)
    assert out["roe"]["uniqueShareMean"] == pytest.approx(0.0, abs=1e-9)
    assert out["bookYield"]["controlR2"]["mean"] < 0.25        # 8 noise controls + 2 sector dummies on 150 rows
    assert out["bookYield"]["controlR2"]["dates"] == 2


def test_statistics_are_invariant_to_a_monotone_transform():
    f = frame()
    g = f.copy()
    g["fcfYield"] = np.exp(g["fcfYield"] * 2.0)
    assert UV.unique_variation(f)["fcfYield"] == UV.unique_variation(g)["fcfYield"]


def test_a_date_with_no_complete_case_yields_nothing_rather_than_crashing():
    f = frame(dates=("2020-01-03",))
    f["vol252"] = None
    out = UV.unique_variation(f)
    assert out["roe"]["controlR2"] is None and out["roe"]["uniqueShareMean"] is None
    empty = UV.complete_cases(f, ["vol252", "roe"])
    assert list(empty.columns) == ["vol252", "roe", "sector"] and len(empty) == 0


def test_below_minimum_names_is_not_measured():
    f = frame(n=UV.MIN_NAMES - 1, dates=("2020-01-03",))
    assert UV.unique_variation(f)["roe"]["controlR2"] is None


def test_joint_attrition_never_rises_and_reports_names_per_date():
    f = frame()
    rng = np.random.default_rng(1)
    for rep in UV.REPRESENTATIVES.values():
        f.loc[rng.random(len(f)) < 0.1, rep] = None
    steps = UV.attrition(f)
    joint = [s["jointPct"] for s in steps]
    assert joint == sorted(joint, reverse=True)
    assert [s["addFamily"] for s in steps] == list(UV.ATTRITION_ORDER)
    assert steps[-1]["namesPerDate"]["dates"] == 2


def test_a_tighter_stale_rule_only_removes_rows():
    ages = pd.Series([30, 100, 130, 170, 200, None])
    available = pd.Series([True, True, True, True, False, False])
    out = UV.stale_threshold_sensitivity(ages, available)
    assert out == {"90": 16.667, "120": 33.333, "150": 50.0, "180": 66.667}


def test_snapshot_age_counts_calendar_days_to_the_resolved_snapshot():
    out = UV.snapshot_age(["2020-01-10", "2020-03-10", "2020-03-17"], ["2020-01-01", "2019-12-01", None])
    assert out["weeks"] == 3 and out["weeksWithoutSnapshot"] == 1
    assert out["maxDays"] == 100 and out["weeksOver90Days"] == 1 and out["weeksOver45Days"] == 1


FORBIDDEN_MODULES = ("historical_outcomes", "replay_valuation", "kelly_portfolio", "portfolio_validation", "selection_null",
                     "regional_alpha_model", "us_p4_execution", "us_cash_profitability_exploratory", "alpha_inference_calibration")


@pytest.mark.parametrize("path", ["pipeline/us_factor_unique_variation.py", "scripts/audit_us_factor_unique_variation.py"])
def test_no_outcome_label_model_or_portfolio_import(path):
    tree = ast.parse((ROOT / path).read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names |= {node.module or ""} | {a.name for a in node.names}
    assert not any(m in n for n in names for m in FORBIDDEN_MODULES), names
    text = (ROOT / path).read_text()
    for token in ("forwardReturn", "excessReturn", "target_from", "outcomeEnd", "pct_change"):
        assert token not in text


def test_committed_report_is_outcome_blind_and_authorizes_nothing():
    report = json.loads(REPORT.read_text())
    assert report["readsReturns"] is False and report["readsLabels"] is False
    assert report["forwardPricesRead"] is False and report["fitsPredictiveModels"] is False
    assert report["authorizes"] == "NOTHING"
    assert report["definitions"]["representatives"] == UV.REPRESENTATIVES
    assert set(report["uniqueVariationNonFinancial"]) == set(UV.FEATURES)
    assert report["inputs"]["replayIdentity"]["manifestSha256"].startswith("f0781292")
