"""Unit tests for prospective sealing of fundamental-acceleration signal
records -- the append-only, digest-verified store that lets a future
non-replay-contaminated validation happen once a sealed record's horizon
matures.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from pipeline import fundamental_acceleration as FA
from pipeline import fundamental_acceleration_seal as SEAL
from pipeline import pit_data


def _record(ticker, period, available_from, fields):
    return pit_data.FundamentalRecord(
        ticker=ticker, report_period=period, available_from=available_from,
        report_date=available_from, fields=dict(fields),
    )


def _store():
    return pit_data.FundamentalStore({
        "A": [
            _record("A", "2019-Q1", "2019-05-01",
                    {"roe": 0.10, "operatingMargin": 0.18, "profitMargin": 0.08}),
            _record("A", "2019-Q2", "2019-08-01",
                    {"roe": 0.14, "operatingMargin": 0.20, "profitMargin": 0.10}),
        ],
        "B": [
            _record("B", "2019-Q1", "2019-05-01",
                    {"roe": 0.05, "operatingMargin": 0.09, "profitMargin": 0.03}),
            _record("B", "2019-Q2", "2019-08-01",
                    {"roe": 0.02, "operatingMargin": 0.07, "profitMargin": 0.01}),
        ],
        "C": [
            _record("C", "2019-Q1", "2019-05-01",
                    {"roe": 0.07, "operatingMargin": 0.11, "profitMargin": 0.05}),
            _record("C", "2019-Q2", "2019-08-01",
                    {"roe": 0.12, "operatingMargin": 0.15, "profitMargin": 0.09}),
        ],
    })


# --------------------------------------------------------------------------- #
# build_candidate_rows / score_candidate_rows
# --------------------------------------------------------------------------- #
def test_build_and_score_candidate_rows():
    candidates = [
        {"ticker": "A", "region": "US", "sector": "Technology",
         "factorPercentiles": {"quality": 60}},
        {"ticker": "B", "region": "US", "sector": "Technology",
         "factorPercentiles": {"quality": 40}},
        {"ticker": "C", "region": "US", "sector": "Technology",
         "factorPercentiles": {"quality": 50}},
    ]
    rows = SEAL.build_candidate_rows(candidates, _store(), "2019-09-01")
    assert len(rows) == 3
    assert set(rows["status"]) == {FA.OK}
    scored = SEAL.score_candidate_rows(rows)
    ranked = scored.set_index("ticker")["accelerationPercentile"]
    # C has the largest positive deltas (roe +0.05/+0.04/+0.04), A the next
    # largest (+0.04/+0.02/+0.02), B the most negative (-0.03/-0.02/-0.02).
    assert ranked["C"] > ranked["A"] > ranked["B"]


def test_score_candidate_rows_empty_input():
    scored = SEAL.score_candidate_rows(pd.DataFrame())
    assert scored.empty


# --------------------------------------------------------------------------- #
# seal_records -- schema and digest
# --------------------------------------------------------------------------- #
def test_seal_records_carries_required_fields_and_digest():
    candidates = [{"ticker": "A", "region": "US", "sector": "Technology",
                  "factorPercentiles": {"quality": 60}}]
    rows = SEAL.build_candidate_rows(candidates, _store(), "2019-09-01")
    scored = SEAL.score_candidate_rows(rows)
    records = SEAL.seal_records(scored, "2019-09-01", generated_at="2019-09-01T00:00:00+00:00")
    assert len(records) == 1
    record = records[0]
    for field in ("sealVersion", "accelerationVersion", "generatedAt", "asOfDate",
                  "ticker", "region", "sector", "status", "dataSufficient",
                  "currentReportPeriod", "previousReportPeriod", "deltas",
                  "compositeZ", "accelerationPercentile", "digest"):
        assert field in record
    assert record["sealVersion"] == SEAL.SEAL_VERSION
    assert record["ticker"] == "A"
    assert record["asOfDate"] == "2019-09-01"
    assert record["digest"] == SEAL.digest_row(record)


def test_seal_records_digest_changes_if_content_changes():
    candidates = [{"ticker": "A", "region": "US", "sector": "Technology"}]
    rows = SEAL.build_candidate_rows(candidates, _store(), "2019-09-01")
    scored = SEAL.score_candidate_rows(rows)
    record = SEAL.seal_records(scored, "2019-09-01")[0]
    original_digest = record["digest"]
    tampered = dict(record)
    tampered["deltas"] = dict(tampered["deltas"])
    tampered["deltas"]["roe"] = 999.0
    assert SEAL.digest_row(tampered) != original_digest


# --------------------------------------------------------------------------- #
# append_seal -- append-only, never overwrites an existing key
# --------------------------------------------------------------------------- #
def test_append_seal_writes_new_records(tmp_path):
    path = tmp_path / "seal.jsonl"
    candidates = [{"ticker": "A", "region": "US", "sector": "Technology"}]
    rows = SEAL.build_candidate_rows(candidates, _store(), "2019-09-01")
    scored = SEAL.score_candidate_rows(rows)
    records = SEAL.seal_records(scored, "2019-09-01")
    count = SEAL.append_seal(path, records)
    assert count == 1
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert stored["ticker"] == "A"


def test_append_seal_refuses_to_overwrite_existing_key(tmp_path):
    path = tmp_path / "seal.jsonl"
    candidates = [{"ticker": "A", "region": "US", "sector": "Technology"}]
    rows = SEAL.build_candidate_rows(candidates, _store(), "2019-09-01")
    scored = SEAL.score_candidate_rows(rows)
    records = SEAL.seal_records(scored, "2019-09-01")
    SEAL.append_seal(path, records)
    with pytest.raises(ValueError, match="already-sealed"):
        SEAL.append_seal(path, records)
    # The file must be unchanged by the refused attempt.
    assert len(path.read_text().strip().splitlines()) == 1


def test_append_seal_allows_new_date_for_same_ticker(tmp_path):
    path = tmp_path / "seal.jsonl"
    candidates = [{"ticker": "A", "region": "US", "sector": "Technology"}]
    rows1 = SEAL.build_candidate_rows(candidates, _store(), "2019-09-01")
    SEAL.append_seal(path, SEAL.seal_records(SEAL.score_candidate_rows(rows1), "2019-09-01"))
    rows2 = SEAL.build_candidate_rows(candidates, _store(), "2019-09-02")
    SEAL.append_seal(path, SEAL.seal_records(SEAL.score_candidate_rows(rows2), "2019-09-02"))
    assert len(path.read_text().strip().splitlines()) == 2


def test_append_seal_refuses_duplicate_keys_within_one_batch(tmp_path):
    path = tmp_path / "seal.jsonl"
    candidates = [{"ticker": "A", "region": "US", "sector": "Technology"}]
    rows = SEAL.build_candidate_rows(candidates, _store(), "2019-09-01")
    records = SEAL.seal_records(SEAL.score_candidate_rows(rows), "2019-09-01")
    with pytest.raises(ValueError, match="duplicate"):
        SEAL.append_seal(path, records + records)


def test_existing_keys_reads_empty_for_missing_file(tmp_path):
    assert SEAL.existing_keys(tmp_path / "missing.jsonl") == set()
