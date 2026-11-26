import math

import numpy as np
import pytest

from research.next_alpha_source_admission_v1.tools import guidance_archived_audit as audit


def test_rank_correlation_uses_average_ties_and_refuses_constant_series():
    assert audit.spearman(np.array([1, 1, 3]), np.array([1, 2, 3])) == pytest.approx(math.sqrt(0.75))
    assert audit.spearman(np.array([1, 1, 1]), np.array([1, 2, 3])) is None


def test_crossed_cluster_interval_requires_multiple_groups_on_each_axis():
    interval = audit.cluster_interval(np.array([1, 2]), np.array([1, 2]),
                                      {"issuer": ["a", "a"], "quarter": ["q1", "q2"]})
    assert interval == {"clusters": {"issuer": 1, "quarter": 2}, "validReplicates": 0, "quantiles": None}


def test_alphabet_cluster_sensitivity_preserves_legal_issuer_boundaries():
    current = "2020-08-01T20:00:00+00:00"
    prior = "2020-05-01T20:00:00Z"
    filings = {
        ("1652044", "current"): {"accepted": audit.utc(current), "tickers": {"GOOG", "GOOGL"}},
        ("1288776", "prior"): {"accepted": audit.utc(prior), "tickers": {"GOOG"}},
    }
    assert audit.corp_cluster("1288776") == audit.corp_cluster("1652044")
    with pytest.raises(ValueError, match="Unverified same-issuer"):
        audit.resolve_links([{
            "accession": "current", "prior_accession": "prior", "issuer": "GOOGL",
            "accepted_at": current, "prior_accepted_at": prior,
        }], filings)


def test_filing_events_collapse_metrics_and_cluster_dependence():
    rows = [{"cik": "1", "accession": "a", "accepted": audit.utc("2020-07-01T16:00:00Z")}] * 3
    rows.append({"cik": "1", "accession": "b", "accepted": audit.utc("2020-09-30T16:00:00Z")})
    counts = audit.event_counts(rows)
    assert counts["linkRows"] == 4
    assert counts["issuerAcceptanceEvents"] == 2
    assert counts["issuerCalendarQuarters"] == 1
    assert counts["singleDimensionDesignEffectNByIssuerRho"]["1.0"] == 1.0
