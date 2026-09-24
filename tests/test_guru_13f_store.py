"""What a stored Guru 13F row has to mean.

The network half runs only in the backfill script. What is pinned here is
everything that decides whether a stored row is usable: the action
threshold that keeps rounding noise from reading as a trade, the acquisition
window that never becomes a fake exact date, that an amendment never
overwrites the original it amends, and the id-dedup that makes a re-run
resumable rather than duplicative.
"""
from __future__ import annotations

from pathlib import Path

from pipeline import guru_13f_store as STORE


MANAGER = {"id": "acme", "name": "Acme Capital", "cik": "0001111111"}


def _infotable_row(issuer, cusip, value, shares, title_class="COM", put_call=None):
    return {"issuer": issuer, "titleClass": title_class, "cusip": cusip,
            "valueUsd": value, "shares": shares, "shareType": "SH", "putCall": put_call}


def _filing(accession, filing_date, report_date, rows, form="13F-HR"):
    return {"accessionNumber": accession, "filingDate": filing_date,
            "reportDate": report_date, "filingForm": form, "infoTableRows": rows}


# --------------------------------------------------------------------------- #
# shard key
# --------------------------------------------------------------------------- #
def test_shard_key_is_the_report_quarter():
    assert STORE.shard_key("2019-03-31") == "2019-Q1"
    assert STORE.shard_key("2019-04-01") == "2019-Q2"
    assert STORE.shard_key("2019-12-31") == "2019-Q4"


# --------------------------------------------------------------------------- #
# The action threshold — see the module docstring for the exact numbers
# --------------------------------------------------------------------------- #
def test_a_tiny_relative_move_on_a_huge_base_is_hold_not_add():
    # 0.4% of ten million shares is real share count movement (40,000
    # shares) but under the relative bar.
    assert STORE.classify_action(10_000_000, 10_040_000) == STORE.HOLD


def test_a_huge_relative_move_on_a_tiny_base_is_hold_not_add():
    # 1 share -> 2 shares is a 100% relative move but 1 share of absolute
    # change, under the absolute floor.
    assert STORE.classify_action(1, 2) == STORE.HOLD


def test_a_move_clearing_both_bars_is_add_or_reduce():
    assert STORE.classify_action(10_000, 12_000) == STORE.ADD
    assert STORE.classify_action(12_000, 10_000) == STORE.REDUCE


def test_zero_to_positive_is_new_and_positive_to_zero_is_exit():
    assert STORE.classify_action(0, 5_000) == STORE.NEW
    assert STORE.classify_action(5_000, 0) == STORE.EXIT


# --------------------------------------------------------------------------- #
# The row builder — one quarter at a time
# --------------------------------------------------------------------------- #
def test_first_ever_filing_is_all_new_with_window_anchored_on_the_filing_date():
    filings = [_filing("0001-24-000001", "2024-02-14", "2023-12-31",
                       [_infotable_row("ALPHA INC", "111111111", 1_000_000, 10_000)])]
    rows = STORE.build_manager_rows(MANAGER, filings)
    assert len(rows) == 1
    row = rows[0]
    assert row["action"] == STORE.NEW
    assert row["previousShares"] == 0.0
    assert row["acquisitionWindowStart"] == "2024-02-14"
    assert row["acquisitionWindowEnd"] == "2023-12-31"
    assert row["portfolioWeight"] == 100.0


def test_second_quarter_new_position_windows_from_the_day_after_the_prior_report():
    filings = [
        _filing("0001-24-000001", "2024-02-14", "2023-12-31",
               [_infotable_row("ALPHA INC", "111111111", 1_000_000, 10_000)]),
        _filing("0001-24-000002", "2024-05-15", "2024-03-31",
               [_infotable_row("ALPHA INC", "111111111", 1_000_000, 10_000),
                _infotable_row("BETA INC", "222222222", 500_000, 5_000)]),
    ]
    rows = STORE.build_manager_rows(MANAGER, filings)
    beta = next(r for r in rows if r["CUSIP"] == "222222222")
    assert beta["action"] == STORE.NEW
    assert beta["acquisitionWindowStart"] == "2024-01-01"
    assert beta["acquisitionWindowEnd"] == "2024-03-31"


def test_a_dropped_position_is_a_synthetic_exit_row():
    filings = [
        _filing("0001-24-000001", "2024-02-14", "2023-12-31",
               [_infotable_row("ALPHA INC", "111111111", 1_000_000, 10_000)]),
        _filing("0001-24-000002", "2024-05-15", "2024-03-31", []),
    ]
    rows = STORE.build_manager_rows(MANAGER, filings)
    exit_rows = [r for r in rows if r["reportDate"] == "2024-03-31"]
    assert len(exit_rows) == 1
    assert exit_rows[0]["action"] == STORE.EXIT
    assert exit_rows[0]["shares"] == 0.0
    assert exit_rows[0]["previousShares"] == 10_000.0
    assert exit_rows[0]["issuer"] == "ALPHA INC", "issuer name survives from the last known holding"
    assert exit_rows[0]["acquisitionWindowStart"] is None
    assert exit_rows[0]["acquisitionWindowEnd"] is None


# --------------------------------------------------------------------------- #
# Amendment preservation — the whole point of this being a separate store
# --------------------------------------------------------------------------- #
def test_an_amendment_is_stored_alongside_its_original_never_over_it():
    filings = [
        _filing("0001-24-000001", "2024-02-14", "2023-12-31",
               [_infotable_row("ALPHA INC", "111111111", 1_000_000, 10_000)], form="13F-HR"),
        _filing("0001-24-000005", "2024-03-01", "2023-12-31",
               [_infotable_row("ALPHA INC", "111111111", 1_200_000, 10_000)], form="13F-HR/A"),
    ]
    rows = STORE.build_manager_rows(MANAGER, filings)
    by_accession = {r["accessionNumber"]: r for r in rows}
    assert "0001-24-000001" in by_accession and "0001-24-000005" in by_accession
    original = by_accession["0001-24-000001"]
    amendment = by_accession["0001-24-000005"]
    assert original["originalOrAmended"] == "ORIGINAL" and not original["amendmentFlag"]
    assert amendment["originalOrAmended"] == "AMENDED" and amendment["amendmentFlag"]
    assert original["reportedValue"] == 1_000_000.0
    assert amendment["reportedValue"] == 1_200_000.0, "the amendment's own restated value is kept, not overwritten"


def test_an_amendment_never_becomes_next_quarters_baseline():
    filings = [
        _filing("0001-24-000001", "2024-02-14", "2023-12-31",
               [_infotable_row("ALPHA INC", "111111111", 1_000_000, 10_000)], form="13F-HR"),
        _filing("0001-24-000005", "2024-03-01", "2023-12-31",
               [_infotable_row("ALPHA INC", "111111111", 1_200_000, 50_000)], form="13F-HR/A"),
        _filing("0001-24-000002", "2024-05-15", "2024-03-31",
               [_infotable_row("ALPHA INC", "111111111", 1_000_000, 10_040)], form="13F-HR"),
    ]
    rows = STORE.build_manager_rows(MANAGER, filings)
    q1_2024 = next(r for r in rows if r["reportDate"] == "2024-03-31")
    # If the amendment's 50,000 shares had become the baseline this would be
    # a huge REDUCE; the original's 10,000 is the baseline instead, so a
    # 10,000 -> 10,040 move (0.4%) is a sub-threshold HOLD.
    assert q1_2024["previousShares"] == 10_000.0
    assert q1_2024["action"] == STORE.HOLD


# --------------------------------------------------------------------------- #
# Reconstruction round-trip — what makes the backfill resumable
# --------------------------------------------------------------------------- #
def test_reconstructed_rows_feed_the_builder_to_the_same_result_as_the_original_rows():
    original_rows = [_infotable_row("ALPHA INC", "111111111", 1_000_000, 10_000)]
    filings = [_filing("0001-24-000001", "2024-02-14", "2023-12-31", original_rows)]
    first_pass = STORE.build_manager_rows(MANAGER, filings)

    reconstructed = STORE.reconstruct_infotable_rows(first_pass)
    second_filings = [_filing("0001-24-000001", "2024-02-14", "2023-12-31", reconstructed)]
    second_pass = STORE.build_manager_rows(MANAGER, second_filings)
    assert first_pass == second_pass


def test_reconstruction_excludes_synthetic_exit_rows():
    filings = [
        _filing("0001-24-000001", "2024-02-14", "2023-12-31",
               [_infotable_row("ALPHA INC", "111111111", 1_000_000, 10_000)]),
        _filing("0001-24-000002", "2024-05-15", "2024-03-31", []),
    ]
    rows_for_q2 = [r for r in STORE.build_manager_rows(MANAGER, filings)
                  if r["reportDate"] == "2024-03-31"]
    assert STORE.reconstruct_infotable_rows(rows_for_q2) == []


# --------------------------------------------------------------------------- #
# Write/read: dedup by id, resumability
# --------------------------------------------------------------------------- #
def test_write_holdings_is_idempotent_and_reports_skips(tmp_path: Path):
    filings = [_filing("0001-24-000001", "2024-02-14", "2023-12-31",
                       [_infotable_row("ALPHA INC", "111111111", 1_000_000, 10_000)])]
    rows = STORE.build_manager_rows(MANAGER, filings)

    appended1, skipped1 = STORE.write_holdings(tmp_path, rows)
    assert appended1 == len(rows) and skipped1 == 0

    appended2, skipped2 = STORE.write_holdings(tmp_path, rows)
    assert appended2 == 0 and skipped2 == len(rows)

    loaded = STORE.load_holdings(tmp_path)
    assert len(loaded) == len(rows), "the second write must not duplicate anything"


def test_processed_filings_reports_manager_report_date_accession_triples(tmp_path: Path):
    filings = [_filing("0001-24-000001", "2024-02-14", "2023-12-31",
                       [_infotable_row("ALPHA INC", "111111111", 1_000_000, 10_000)])]
    rows = STORE.build_manager_rows(MANAGER, filings)
    STORE.write_holdings(tmp_path, rows)
    seen = STORE.processed_filings(tmp_path)
    assert ("0001111111", "2023-12-31", "0001-24-000001") in seen


def test_manifest_carries_a_sha256_per_shard(tmp_path: Path):
    filings = [_filing("0001-24-000001", "2024-02-14", "2023-12-31",
                       [_infotable_row("ALPHA INC", "111111111", 1_000_000, 10_000)])]
    rows = STORE.build_manager_rows(MANAGER, filings)
    STORE.write_holdings(tmp_path, rows)
    manifest = STORE.write_manifest(tmp_path)
    assert manifest["totalRecords"] == len(rows)
    shard = manifest["shards"]["2023-Q4"]
    assert len(shard["sha256"]) == 64
