"""Synthetic tests for the PIT US sector table, plus outcome-free checks on the committed snapshot files."""
import pytest

from research.master_research_program_v1.market_industry import us_sector_membership as U


def _payloads(extra=None):
    snaps = [
        ("2013-01-10", "2013-01-10T12:00:00Z", "c1", {"AAA": "Information Technology", "BF.B": "Consumer Staples", "CCC": "Telecommunications Services"}),
        ("2013-02-10", "2013-02-10T23:00:00Z", "c2", {"AAA": "Information Technology", "BF.B": "Consumer Staples", "CCC": "Telecommunication Services"}),
        ("2013-03-10", "2013-03-10T12:00:00Z", "c3", {"AAA": "Industries", "BF.B": None, "CCC": "Communication Services"}),
    ] + (extra or [])
    members = {"snapshots": [{"date": d, "publishedAt": p, "sourceCommit": c,
                              "members": [k.replace(".", "-") for k in rows]} for d, p, c, rows in snaps]}
    sectors = {"snapshots": [{"date": d, "sourceCommit": c, "sectorColumn": "GICS Sector", "hasCik": False,
                              "rows": {k: {"sector": v, "cik": None} for k, v in rows.items()}} for d, _, c, rows in snaps]}
    return members, sectors


def test_members_on_never_uses_a_later_snapshot():
    snaps = U.build_snapshots(*_payloads())
    assert U.snapshot_on(snaps, "2013-01-09") is None
    assert U.snapshot_on(snaps, "2013-01-10") is None                 # published during the day -> visible next day
    assert U.snapshot_on(snaps, "2013-01-11").source_commit == "c1"
    assert U.snapshot_on(snaps, "2013-02-10T22:59:00Z").source_commit == "c1"
    assert U.snapshot_on(snaps, "2013-02-10T23:00:00Z").source_commit == "c2"
    assert U.members_on(snaps, "2013-02-11") == frozenset({"AAA", "BF-B", "CCC"})


def test_future_snapshot_cannot_alter_past_membership():
    base = U.build_snapshots(*_payloads())
    more = U.build_snapshots(*_payloads([("2013-04-01", "2013-04-01T00:00:00Z", "c4", {"ZZZ": "Energy"})]))
    for day in ("2013-01-11", "2013-02-15", "2013-03-20"):
        assert U.membership_table(base, day) == U.membership_table(more, day)
    assert "ZZZ" in U.members_on(more, "2013-04-02")


def test_punctuation_join_and_spelling_variant():
    snaps = U.build_snapshots(*_payloads())
    sector, basis, used = U.sector_on(snaps, "2013-01-11", "BF-B")
    assert (sector, basis) == ("Consumer Staples", U.BASIS_PUBLISHED)
    assert snaps[0].row_for("BF-B")[1].startswith("PUNCTUATION_VARIANT")
    assert U.sector_on(snaps, "2013-01-11", "CCC")[0] == "Telecommunication Services"


def test_unrecognised_labels_are_not_guessed_but_carried_from_earlier_only():
    snaps = U.build_snapshots(*_payloads())
    assert U.normalise_sector("Industries") == (None, "NOT_A_GICS_SECTOR_NAME_NOT_GUESSED")
    sector, basis, used = U.sector_on(snaps, "2013-03-11", "AAA", carry=True)
    assert (sector, basis, used) == ("Information Technology", U.BASIS_CARRIED, "2013-02-10")
    assert U.sector_on(snaps, "2013-03-11", "AAA", carry=False) == (None, U.BASIS_UNAVAILABLE, None)
    assert U.sector_on(snaps, "2013-03-11", "BF-B")[1] == U.BASIS_CARRIED


def test_reclassification_is_not_normalised():
    assert U.normalise_sector("Telecommunication Services")[0] != U.normalise_sector("Communication Services")[0]


def test_sub_industry_snapshot_is_unusable_at_sector_level():
    rows = {f"S{i}": f"Sub-industry {i}" for i in range(U.SUB_INDUSTRY_SNAPSHOT_MIN_LABELS)}
    members, sectors = _payloads([("2013-05-01", "2013-05-01T00:00:00Z", "c5", rows)])
    snaps = U.build_snapshots(members, sectors)
    assert snaps[-1].sub_industry_column
    assert snaps[-1].sector_of("S1") == (None, "SNAPSHOT_SECTOR_COLUMN_CARRIES_SUB_INDUSTRY")


def test_identity_mismatch_refused():
    members, sectors = _payloads()
    sectors["snapshots"].pop()
    with pytest.raises(ValueError):
        U.build_snapshots(members, sectors)


def test_committed_snapshots_load_and_carry_no_outcome_fields():
    snaps = U.load_snapshots()
    assert len(snaps) == 195
    assert all(set(r) <= {"sector", "cik"} for s in snaps for r in s.rows.values())
    assert [s.date for s in snaps if s.sub_industry_column] == ["2023-03-07"]
    observed = {r["sector"] for s in snaps if not s.sub_industry_column for r in s.rows.values()}
    assert observed <= set(U.GICS_SECTORS) | set(U.SPELLING_VARIANTS) | set(U.NOT_SECTOR_LEVEL) | {None}
