"""Outcome-free regression cases for the guidance comparison and review routing."""

import hashlib
import importlib
from pathlib import Path
import sys

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "research/next_alpha_source_admission_v1/tools"
sys.path.insert(0, str(TOOLS))
evaluation = importlib.import_module("guidance_evaluate_v4")


def fact(low, high=None, **fields):
    return {"target": "FY2026", "metric": "revenue", "basis": "GAAP", "unit": "USD_million",
            "kind": "CURRENT", "low": low, "high": low if high is None else high, **fields}


def test_strict_tolerance_does_not_select_a_greedy_matching():
    report = evaluation.score_rows([fact(100.4), fact(99.9)], [fact(100), fact(100.8)])

    assert report == {"tp": 2, "fp": 0, "fn": 0, "precision": 1, "recall": 1, "f1": 1}


def test_direction_and_exact_links_are_scored_separately_with_gaps():
    docs = {letter: {"cik": 10, "acceptanceDateTime": f"2026-0{month}-25T18:00:00Z"}
            for month, letter in enumerate("abcd", 1)}
    gold = {"a": [fact(100, 120)], "b": [fact(105, 115)], "c": [fact(126)], "d": [fact(130)]}
    candidates = {"a": [fact(100, 120)], "b": [fact(110, 120)],
                  "c": [fact(126), fact(136)], "d": [fact(130)]}

    labels, _ = evaluation.revisions(gold, docs)
    predicted, conflicts = evaluation.revisions(candidates, docs)
    score = evaluation.score_revisions(predicted, labels)

    assert conflicts == 1
    assert [(row["prior_accession"], row["accession"], row["direction"]) for row in predicted] == [
        ("a", "b", "RAISE"),
    ]
    assert score["links"]["tp"] == 1 and score["links"]["fn"] == 2
    assert score["directionGivenMatchedLink"] == 0
    assert score["directionConfusions"] == {"NARROW->RAISE": 1}


def test_distinct_company_or_accounting_basis_never_forms_a_link():
    docs = {"a": {"cik": 10, "acceptanceDateTime": "2026-01-25T18:00:00Z"},
            "b": {"cik": 11, "acceptanceDateTime": "2026-02-25T18:00:00Z"},
            "c": {"cik": 10, "acceptanceDateTime": "2026-03-25T18:00:00Z"}}
    rows = {"a": [fact(100)], "b": [fact(120)], "c": [fact(126, basis="non_GAAP")]}

    assert evaluation.revisions(rows, docs) == ([], 0)


def test_context_routes_mixed_historical_comparator_to_review():
    row = fact(840, 860, block=0)
    clean = [("p", "For fiscal 2026 the company expects revenue of $840 million to $860 million.")]
    mixed = [("p", clean[0][1].rstrip(".") + ", compared with $750 million a year ago.")]

    assert evaluation.explicit_narrative_anchor(clean, row)
    assert not evaluation.explicit_narrative_anchor(mixed, row)


def test_official_recapture_verifies_hash_and_keeps_legacy_identity_distinct(tmp_path):
    raw = b"<html>SEC exhibit</html>"
    digest = hashlib.sha256(raw).hexdigest()
    directory = tmp_path / "sections"
    directory.mkdir()
    cached = directory / digest
    cached.write_bytes(raw)
    registered = "a" * 64
    doc = {"accession": "123", "cik": 7, "sha256": registered}
    record = {"accession": "123", "cik": 7, "status": "OFFICIAL_ARCHIVE_SECTION",
              "registeredHttpSha256": registered, "sectionSha256": digest, "sectionBytes": len(raw)}

    assert evaluation.verified_body(record, doc, tmp_path) == raw
    cached.write_bytes(raw + b"edited")
    with pytest.raises(ValueError, match="Hash or byte length"):
        evaluation.verified_body(record, doc, tmp_path)
