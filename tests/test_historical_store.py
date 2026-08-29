"""The historical ledger has to survive a push to GitHub.

The replay job computed a full decade of evidence for two consecutive nights and
lost all of it both times: written as two monolithic JSONL files the ledger was
900 MB and 830 MB, and GitHub rejects any blob over 100 MB. These tests pin the
properties that make the store pushable — sharded, compressed, deterministic,
and loudly self-checking — because a regression in any of them is invisible
locally and only shows up as a rejected push after a 13-minute job.
"""
from __future__ import annotations

import gzip
import json

import numpy as np
import pandas as pd
import pytest

from pipeline import historical_outcomes as HO
from pipeline import historical_replay as HR
from pipeline import historical_store as HS


def signal(id_, date, *, generation="replay-v1", **extra):
    return {"id": id_, "date": date, "asOf": date, "ticker": "AAPL", "region": "US",
            "replayVersion": generation, **extra}


def outcome(id_, date, *, horizons=("21", "126"), generation="replay-v1"):
    return {"id": id_, "date": date, "ticker": "AAPL", "region": "US",
            "replayVersion": generation,
            "horizons": {h: {"excessReturn": 0.01} for h in horizons}}


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
def test_signals_are_sharded_by_month_not_written_as_one_file(tmp_path):
    HS.append_signals(tmp_path, [signal("a", "2019-05-15"), signal("b", "2019-06-03"),
                                 signal("c", "2020-01-09")])
    keys = [key for _, key, _ in HS.iter_shards(tmp_path, HS.SIGNALS)]
    assert keys == ["2019-05", "2019-06", "2020-01"]
    assert not HS.legacy_path(tmp_path, HS.SIGNALS).exists()


def test_shards_are_gzipped(tmp_path):
    HS.append_signals(tmp_path, [signal("a", "2019-05-15")])
    _, _, path = HS.iter_shards(tmp_path, HS.SIGNALS)[0]
    assert path.suffix == ".gz"
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        assert json.loads(handle.read().strip())["id"] == "a"


def test_replay_generations_live_in_separate_directories(tmp_path):
    HS.append_signals(tmp_path, [signal("a", "2019-05-15", generation="replay-v1"),
                                 signal("b", "2019-05-15", generation="replay-v2")])
    assert HS.generations(tmp_path) == ["replay-v1", "replay-v2"]
    # Evidence from two generations cannot be pooled by accident because it is
    # not in the same file to begin with.
    assert [r["id"] for r in HS.load(tmp_path, HS.SIGNALS, generation="replay-v1")] == ["a"]
    assert [r["id"] for r in HS.load(tmp_path, HS.SIGNALS, generation="replay-v2")] == ["b"]
    assert len(HS.load(tmp_path, HS.SIGNALS)) == 2


def test_only_touched_shards_are_rewritten(tmp_path):
    HS.append_signals(tmp_path, [signal("a", "2019-05-15"), signal("b", "2020-01-09")])
    untouched = HS.shard_path(tmp_path, "replay-v1", HS.SIGNALS, "2019-05")
    before = untouched.read_bytes()
    stamp = untouched.stat().st_mtime_ns

    HS.append_signals(tmp_path, [signal("c", "2020-01-10")])
    # A daily run must not rewrite a decade of frozen history to add one date.
    assert untouched.read_bytes() == before
    assert untouched.stat().st_mtime_ns == stamp


# --------------------------------------------------------------------------- #
# Determinism — the property that keeps daily commits small
# --------------------------------------------------------------------------- #
def test_identical_records_serialize_to_identical_bytes(tmp_path):
    rows = [signal("b", "2019-05-20"), signal("a", "2019-05-15")]
    first = HS.encode(sorted(rows, key=lambda r: r["id"]))
    second = HS.encode(sorted(reversed(rows), key=lambda r: r["id"]))
    # gzip stamps mtime into its header by default; if that leaked through,
    # every nightly rewrite would be a new git blob even with no new evidence.
    assert first == second


def test_rewriting_an_unchanged_shard_reports_no_change(tmp_path):
    rows = [outcome("a", "2019-05-15")]
    assert HS.write_outcomes_shard(tmp_path, "replay-v1", "2019-05", rows) is True
    assert HS.write_outcomes_shard(tmp_path, "replay-v1", "2019-05", rows) is False
    assert HS.write_outcomes_shard(tmp_path, "replay-v1", "2019-05",
                                   [outcome("a", "2019-05-15", horizons=("21",))]) is True


def test_row_order_does_not_change_the_stored_bytes(tmp_path):
    HS.append_signals(tmp_path, [signal("a", "2019-05-15"), signal("b", "2019-05-16")])
    path = HS.shard_path(tmp_path, "replay-v1", HS.SIGNALS, "2019-05")
    ordered = path.read_bytes()
    path.unlink()
    HS.append_signals(tmp_path, [signal("b", "2019-05-16"), signal("a", "2019-05-15")])
    assert path.read_bytes() == ordered


# --------------------------------------------------------------------------- #
# The size guard that the old layout did not have
# --------------------------------------------------------------------------- #
def test_oversized_shard_fails_locally_instead_of_at_the_remote(tmp_path):
    HS.append_signals(tmp_path, [signal("a", "2019-05-15", note="x" * 2048)])
    HS.assert_pushable(tmp_path)          # comfortably small
    with pytest.raises(RuntimeError) as excinfo:
        HS.assert_pushable(tmp_path, limit=1)
    message = str(excinfo.value)
    assert "signals-2019-05.jsonl.gz" in message
    assert "100 MB" in message            # names the limit that actually bites


def test_audit_reports_every_stored_file_largest_first(tmp_path):
    HS.append_signals(tmp_path, [signal("a", "2019-05-15", note="x" * 4096),
                                 signal("b", "2020-01-09")])
    rows = HS.audit(tmp_path)
    assert len(rows) == 2
    assert rows[0]["bytes"] >= rows[1]["bytes"]


def test_manifest_indexes_shards_without_decompressing_the_ledger(tmp_path):
    HS.append_signals(tmp_path, [signal("a", "2019-05-15"), signal("b", "2020-01-09")])
    HS.write_outcomes_shard(tmp_path, "replay-v1", "2019-05", [outcome("a", "2019-05-15")])
    manifest = HS.write_manifest(tmp_path, diagnostics={"replayVersion": "replay-v1",
                                                        "firstDate": "2019-05-15"})
    block = manifest["generations"]["replay-v1"]
    assert block["signalRecords"] == 2 and block["outcomeRecords"] == 1
    assert manifest["totalBytes"] > 0
    assert HS.read_manifest(tmp_path)["lastRun"]["firstDate"] == "2019-05-15"


# --------------------------------------------------------------------------- #
# Reading, and not stranding an existing ledger
# --------------------------------------------------------------------------- #
def test_a_legacy_monolithic_ledger_still_reads(tmp_path):
    HS.legacy_path(tmp_path, HS.SIGNALS).write_text(
        json.dumps(signal("a", "2019-05-15")) + "\n", encoding="utf-8")
    assert [r["id"] for r in HS.load(tmp_path, HS.SIGNALS)] == ["a"]


def test_migration_refiles_legacy_records_without_rewriting_them(tmp_path):
    original = [signal("a", "2019-05-15", alphaPercentile=90),
                signal("b", "2020-01-09", alphaPercentile=12)]
    HS.legacy_path(tmp_path, HS.SIGNALS).write_text(
        "\n".join(json.dumps(r) for r in original) + "\n", encoding="utf-8")

    moved = HS.migrate_legacy(tmp_path)

    assert moved[HS.SIGNALS] == 2
    assert not HS.legacy_path(tmp_path, HS.SIGNALS).exists()
    assert sorted(HS.load(tmp_path, HS.SIGNALS), key=lambda r: r["id"]) == original


def test_ids_are_readable_without_loading_the_records(tmp_path):
    HS.append_signals(tmp_path, [signal("a", "2019-05-15"),
                                 signal("b", "2019-05-16", generation="replay-v2")])
    ids = HS.ids_by_generation(tmp_path, HS.SIGNALS)
    assert ids == {"replay-v1": {"a"}, "replay-v2": {"b"}}


def test_records_without_a_usable_date_are_still_stored(tmp_path):
    HS.append_signals(tmp_path, [{"id": "x", "replayVersion": "replay-v1"}])
    # Silently dropping a record because its date is malformed would be a
    # quieter, worse failure than the one this whole module exists to fix.
    assert [r["id"] for r in HS.load(tmp_path, HS.SIGNALS)] == ["x"]
    assert HS.shard_key(None) == HS.UNDATED_SHARD


def test_orphan_outcome_shards_are_pruned(tmp_path):
    HS.write_outcomes_shard(tmp_path, "replay-v1", "2019-05", [outcome("a", "2019-05-15")])
    HS.write_outcomes_shard(tmp_path, "replay-v1", "2020-01", [outcome("b", "2020-01-09")])
    assert HS.prune_orphan_outcomes(tmp_path, "replay-v1", keep={"2019-05"}) == 1
    assert [key for _, key, _ in HS.iter_shards(tmp_path, HS.OUTCOMES)] == ["2019-05"]


# --------------------------------------------------------------------------- #
# Coverage accumulated shard by shard must equal coverage over the whole ledger
# --------------------------------------------------------------------------- #
def test_shardwise_coverage_equals_whole_ledger_coverage():
    signals = [signal(f"s{i}", f"2019-0{i}-15") for i in range(1, 7)]
    outcomes = [outcome(f"s{i}", f"2019-0{i}-15",
                        horizons=("21", "126") if i < 4 else ("21",))
                for i in range(1, 7)]

    whole = HO.coverage_summary(signals, outcomes, horizon=126)

    accumulator = HO.CoverageAccumulator(126)
    for i in range(0, 6, 2):                       # two records at a time
        accumulator.add_signals(signals[i:i + 2]).add_outcomes(outcomes[i:i + 2])

    assert accumulator.summary() == whole
    assert whole["signalsRecorded"] == 6 and whole["maturedSignals"] == 3
    assert whole["maturedByHorizon"]["21"] == 6


# --------------------------------------------------------------------------- #
# End to end, the way the nightly job drives it
# --------------------------------------------------------------------------- #
def _frame(seed: int, periods: int = 1400, start: str = "2015-01-01") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(start, periods=periods)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.014, periods)))
    return pd.DataFrame({
        "Open": close * (1 + rng.normal(0, 0.003, periods)),
        "High": close * 1.01, "Low": close * 0.99, "Close": close,
        "Volume": rng.lognormal(14, 0.4, periods),
    }, index=index)


@pytest.fixture(scope="module")
def replayed():
    prices = {f"T{i:02d}": _frame(200 + i) for i in range(8)}
    prices["SPY"] = _frame(9999)
    universe = {"US": [t for t in prices if t.startswith("T")]}
    replay = HR.run_replay(
        prices, universe, benchmarks={"US": "SPY"},
        cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
        start="2017-01-01", end="2017-08-31", frequency="M", model_version="test")
    return prices, replay["signals"]


def _persist(ledger_dir, prices, signals, generation=HR.REPLAY_VERSION):
    """The write half of scripts/run_replay.main, minus the network."""
    appended, skipped = HS.append_signals(ledger_dir, signals)
    bench = {"SPY": prices["SPY"]["Close"]}
    shards = HS.iter_shards(ledger_dir, HS.SIGNALS, generation)
    rewritten = 0
    for _, key, path in shards:
        shard_signals = HS.read_jsonl(path)
        outcomes = HO.compute_outcomes(shard_signals, prices, bench)
        rewritten += bool(HS.write_outcomes_shard(ledger_dir, generation, key, outcomes))
    return appended, skipped, rewritten, len(shards)


def test_a_real_replay_round_trips_through_the_store(tmp_path, replayed):
    prices, signals = replayed
    assert signals, "fixture produced no signals"

    appended, skipped, _, shard_count = _persist(tmp_path, prices, signals)

    assert appended == len(signals) and skipped == 0
    assert shard_count >= 2                       # genuinely sharded, not one file
    stored = HS.load(tmp_path, HS.SIGNALS, generation=HR.REPLAY_VERSION)
    assert len(stored) == len(signals)
    assert sorted(stored, key=lambda r: r["id"]) == sorted(signals, key=lambda r: r["id"])
    HS.assert_pushable(tmp_path)


def test_a_second_run_over_the_same_dates_changes_nothing_on_disk(tmp_path, replayed):
    prices, signals = replayed
    _persist(tmp_path, prices, signals)
    before = {p: p.read_bytes() for _, _, p in
              HS.iter_shards(tmp_path, HS.SIGNALS) + HS.iter_shards(tmp_path, HS.OUTCOMES)}

    appended, skipped, rewritten, _ = _persist(tmp_path, prices, signals)

    # This is the whole point of the daily job: re-running it must produce an
    # empty commit, not a fresh copy of every shard.
    assert appended == 0 and skipped == len(signals) and rewritten == 0
    after = {p: p.read_bytes() for _, _, p in
             HS.iter_shards(tmp_path, HS.SIGNALS) + HS.iter_shards(tmp_path, HS.OUTCOMES)}
    assert after == before


def test_outcomes_join_back_to_their_signals(tmp_path, replayed):
    prices, signals = replayed
    _persist(tmp_path, prices, signals)
    signal_ids = {r["id"] for r in HS.load(tmp_path, HS.SIGNALS)}
    outcomes = HS.load(tmp_path, HS.OUTCOMES)
    assert outcomes
    assert {o["id"] for o in outcomes} <= signal_ids
    # A signal and its outcome must land in the same month shard, or a shard
    # would have to be read twice to resolve one record.
    for _, key, path in HS.iter_shards(tmp_path, HS.OUTCOMES):
        for row in HS.read_jsonl(path):
            assert HS.shard_key(row["date"]) == key


# --------------------------------------------------------------------------- #
# Load-time projection
# --------------------------------------------------------------------------- #
def test_the_audit_projection_keeps_the_one_feature_the_audit_reads():
    """`features` is 28 of a signal's 37 keys; the audit path reads one of them.

    413k signals plus 409k outcomes hold 8.5 GB, and restoring former index
    members widens the cross-section by half again. Keeping 27 unused floats per
    record is the difference between fitting a 16 GB runner and an OOM that
    looks like the pipeline breaking again.
    """
    row = {
        "id": "x", "ticker": "AAA", "date": "2020-01-06",
        "factorPercentiles": {"momentum": 90},
        "features": {"evidenceCoverage": 0.75, "rsi14": 51.0, "mom20Pct": 1.2,
                     "volumeSurge": 0.9, "dist200Pct": -2.0},
    }

    out = HS.audit_projection(row)

    assert out["features"] == {"evidenceCoverage": 0.75}
    assert out["factorPercentiles"] == {"momentum": 90}   # everything else intact
    assert out["id"] == "x" and out["ticker"] == "AAA"
    assert row["features"]["rsi14"] == 51.0               # input not mutated


def test_a_signal_without_features_survives_the_projection():
    row = {"id": "x", "ticker": "AAA"}
    assert HS.audit_projection(row) == row


def test_projection_is_applied_while_loading_not_after(tmp_path):
    rows = [{"id": f"s{i}", "date": "2020-01", "replayVersion": "v1",
             "features": {"evidenceCoverage": 0.5, "junk": i}} for i in range(5)]
    HS.write_shard(HS.shard_path(tmp_path, "v1", HS.SIGNALS, "2020-01"), rows)

    loaded = HS.load(tmp_path, HS.SIGNALS, "v1", project=HS.audit_projection)

    assert len(loaded) == 5
    assert all(row["features"] == {"evidenceCoverage": 0.5} for row in loaded)
    assert all("junk" not in row["features"] for row in loaded)


def test_loading_without_a_projection_is_unchanged(tmp_path):
    """The model trainer needs every feature, so the default must not trim."""
    rows = [{"id": "s1", "date": "2020-01", "replayVersion": "v1",
             "features": {"evidenceCoverage": 0.5, "rsi14": 44.0}}]
    HS.write_shard(HS.shard_path(tmp_path, "v1", HS.SIGNALS, "2020-01"), rows)

    loaded = HS.load(tmp_path, HS.SIGNALS, "v1")

    assert loaded[0]["features"] == {"evidenceCoverage": 0.5, "rsi14": 44.0}
