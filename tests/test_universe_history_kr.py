"""The Korean half of the membership file: what it now writes, and what it still refuses.

`build_universe_history.py` wrote no Korean rows for the life of the replay,
and the refusal was right twice over — `KRX-DELISTING` is "every KRX name ever
delisted", not "was a member of the investable universe", and today's names
with no lower bound admit a 2020 listing into the 2013 cross-section. Both read
as KNOWN membership, so the file reported 100% coverage over a cross-section it
had invented, and nothing caught it because Yahoo serves almost none of those
tickers.

So the bar for lifting the refusal is not "we have a source" but "the refusal
still holds everywhere the source does not reach". Both halves are tested:

  * with no collected shards, KR stays undescribed and any Korean row already
    in the file is still pruned — the old behaviour, unchanged;
  * with shards, KR is described from them, and the names that left the
    universe come back with the dates they left on.

The end-to-end assertion is the last one: the file this writes has to make
`UniverseHistory` report Korean membership as KNOWN, because
`membershipCoveragePct` 0.0 is the thing this whole exercise exists to move.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build_universe_history as BUH  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402
from pipeline import krx_universe as KU  # noqa: E402
from pipeline import pit_data  # noqa: E402


def _shards(store: Path, by_date: dict[str, list[tuple[str, float]]]) -> None:
    """by_date: {"2013-01-02": [(code, market cap), ...]}"""
    rows: dict[int, list[dict]] = {}
    for date, issues in by_date.items():
        ranked = KU.rank_issues([{"code": code, "name": code, "marketCap": cap,
                                  "listedShares": 1.0} for code, cap in issues])
        rows.setdefault(KU.shard_year(date), []).extend(
            KU.snapshot_rows(date, ranked))
    store.mkdir(parents=True, exist_ok=True)
    for year, year_rows in rows.items():
        HS.write_shard(store / f"krx-universe-{year}.jsonl.gz", year_rows)


def _config(tmp_path: Path, kr: list[str], size: int = 120) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"universeSize": size,
                                "universe": {"KR": kr, "US": []}}),
                    encoding="utf-8")
    return path


def _build(tmp_path, *extra) -> dict:
    out = tmp_path / "universe-history.json"
    assert BUH.main(["--skip-us", str(out), *extra]) == 0
    return json.loads(out.read_text(encoding="utf-8"))


# ------------------------------------------------------- the refusal stands

def test_without_shards_korea_is_still_undescribed(tmp_path, capsys):
    written = _build(tmp_path)
    assert written == {}
    assert "no free source" in capsys.readouterr().out


def test_without_shards_an_existing_korean_row_is_still_pruned(tmp_path):
    """The fabricated membership an earlier version wrote must stay deleted.

    The union merge would otherwise preserve it forever, which is why the
    prune exists — and making the prune conditional must not switch it off.
    """
    out = tmp_path / "universe-history.json"
    out.write_text(json.dumps({
        "005930.KS": {"listed": None, "delisted": None, "region": "KR"},
        "AAPL": {"listed": "2013-01-02", "delisted": None, "region": "US"}}),
        encoding="utf-8")
    assert BUH.main(["--skip-us", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == {
        "AAPL": {"listed": "2013-01-02", "delisted": None, "region": "US"}}


def test_an_empty_shard_directory_is_no_source_at_all(tmp_path):
    """A pointed-at directory that holds nothing must not read as a source."""
    (tmp_path / "krx").mkdir()
    assert _build(tmp_path, "--krx-snapshots", str(tmp_path / "krx")) == {}


# ------------------------------------------------------- the refusal lifts

def test_with_shards_korea_is_described_and_not_pruned(tmp_path):
    _shards(tmp_path / "krx", {"2013-01-02": [("000001", 300.0), ("000002", 200.0)],
                               "2016-01-04": [("000001", 300.0), ("000002", 200.0)]})
    written = _build(tmp_path, "--krx-snapshots", str(tmp_path / "krx"),
                     "--config", str(_config(tmp_path, [])))
    assert set(written) == {"000001.KS", "000002.KS"}
    assert all(row["region"] == "KR" for row in written.values())


def test_a_name_that_left_the_universe_comes_back_with_its_exit_date(tmp_path):
    """The survivorship gap, by name and by date. This is the whole point.

    `000002` is large in 2013 and gone by 2016 — the shape of the 210 issues
    Probes run #4 found had departed between 2013-01-02 and 2026-09-01.
    """
    _shards(tmp_path / "krx", {
        "2013-01-02": [("000001", 300.0), ("000002", 200.0)],
        "2016-01-04": [("000001", 300.0)]})
    written = _build(tmp_path, "--krx-snapshots", str(tmp_path / "krx"),
                     "--config", str(_config(tmp_path, [])))
    assert written["000002.KS"]["listed"] == "2013-01-02"
    assert written["000002.KS"]["delisted"] == "2016-01-04"
    assert written["000001.KS"]["delisted"] is None


def test_a_later_arrival_gets_a_lower_bound_not_a_free_pass(tmp_path):
    """The look-ahead the previous Korean attempt was deleted for.

    A name first seen in 2016 must not be admitted to the 2013 cross-section,
    and `listed: None` — no lower bound — is exactly how it would be.
    """
    _shards(tmp_path / "krx", {
        "2013-01-02": [("000001", 300.0)],
        "2016-01-04": [("000001", 300.0), ("000009", 200.0)]})
    written = _build(tmp_path, "--krx-snapshots", str(tmp_path / "krx"),
                     "--config", str(_config(tmp_path, [])))
    assert written["000009.KS"]["listed"] == "2016-01-04"


# ------------------------------------------------------- the universe rule

def test_the_size_cap_is_the_universe_s_own_number_read_from_config(tmp_path):
    """`universe._kr_kospi` takes `head(universe_size)`; so does this."""
    _shards(tmp_path / "krx", {"2013-01-02": [("000001", 300.0), ("000002", 200.0),
                                              ("000003", 100.0)]})
    written = _build(tmp_path, "--krx-snapshots", str(tmp_path / "krx"),
                     "--config", str(_config(tmp_path, [], size=2)))
    assert set(written) == {"000001.KS", "000002.KS"}


def test_an_explicit_size_overrides_the_config(tmp_path):
    _shards(tmp_path / "krx", {"2013-01-02": [("000001", 300.0), ("000002", 200.0),
                                              ("000003", 100.0)]})
    written = _build(tmp_path, "--krx-snapshots", str(tmp_path / "krx"),
                     "--config", str(_config(tmp_path, [], size=2)),
                     "--kr-universe-size", "3")
    assert set(written) == {"000001.KS", "000002.KS", "000003.KS"}


def test_a_configured_name_outside_the_cut_is_kept_not_delisted(tmp_path):
    """Otherwise the build shrinks the universe the system actually trades."""
    _shards(tmp_path / "krx", {"2013-01-02": [("000001", 300.0), ("000002", 200.0),
                                              ("005935", 1.0)]})
    written = _build(tmp_path, "--krx-snapshots", str(tmp_path / "krx"),
                     "--config", str(_config(tmp_path, ["005935.KS"], size=2)))
    assert written["005935.KS"]["delisted"] is None


def test_an_unreadable_config_costs_only_the_protective_half(tmp_path):
    """A missing config degrades the result; it must not invent one."""
    _shards(tmp_path / "krx", {"2013-01-02": [("000001", 300.0)]})
    written = _build(tmp_path, "--krx-snapshots", str(tmp_path / "krx"),
                     "--config", str(tmp_path / "absent.json"))
    assert set(written) == {"000001.KS"}


# ------------------------------------------------------- what it buys

def test_the_written_file_makes_korean_membership_known(tmp_path):
    """`membershipCoveragePct` 0.0 is the number this exists to move.

    Reading the file back through `UniverseHistory` is the only assertion that
    proves it: the rows could be well-formed and still leave Korea unresolved
    if the region string or the ticker suffix did not match what `snapshot`
    keys on.
    """
    _shards(tmp_path / "krx", {
        "2013-01-02": [("000001", 300.0), ("000002", 200.0)],
        "2016-01-04": [("000001", 300.0)]})
    out = tmp_path / "universe-history.json"
    assert BUH.main(["--skip-us", str(out), "--krx-snapshots",
                     str(tmp_path / "krx"), "--config",
                     str(_config(tmp_path, ["000001.KS"]))]) == 0

    history = pit_data.UniverseHistory.from_json(out)
    assert history.available
    assert history.signature["regions"] == {"KR": 2}

    snap = history.snapshot("2014-06-30", {"KR": ["000001.KS"]})
    assert snap.regions["KR"]["membershipUnknown"] == 0
    assert snap.membership_coverage_pct == 100.0
    # The departed name is back in the 2014 cross-section, which is the
    # survivorship fix stated as a membership fact.
    assert "000002.KS" in snap.by_region["KR"]


def test_the_departed_name_is_gone_again_after_its_exit_date(tmp_path):
    _shards(tmp_path / "krx", {
        "2013-01-02": [("000001", 300.0), ("000002", 200.0)],
        "2016-01-04": [("000001", 300.0)]})
    out = tmp_path / "universe-history.json"
    assert BUH.main(["--skip-us", str(out), "--krx-snapshots",
                     str(tmp_path / "krx"), "--config",
                     str(_config(tmp_path, ["000001.KS"]))]) == 0

    history = pit_data.UniverseHistory.from_json(out)
    after = history.snapshot("2017-06-30", {"KR": ["000001.KS"]})
    assert "000002.KS" not in after.by_region["KR"]
