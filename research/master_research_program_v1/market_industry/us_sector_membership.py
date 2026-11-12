"""PIT US sector membership for S&P 500 members, from the repository's hash-verified dataset snapshots. Outcome-free, pure.

Sources (both already in the repository; this module reads no price, return or label):

* ``research_specs/alpha-opportunity-model-v1-us-membership.json.gz`` -- the sealed membership: 195 snapshots of the public
  ``datasets/s-and-p-500-companies`` repository, each with ``date``, ``publishedAt`` (the upstream commit time) and member symbols.
* ``data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz`` -- the sector column of the SAME 195 commits,
  refused at acquisition unless the raw CSV matched the pinned ``rawCsvSha256`` (``scripts/acquire_us_sp500_snapshot_sectors.py``).
  Label: ``DATASET_PUBLISHED_SECTOR_AT_SNAPSHOT_NOT_AN_INDEX_PROVIDER_FILE``. It is a dataset label, not an S&P/MSCI GICS file.

Rules (each tested on synthetic snapshots):

* VISIBILITY. A snapshot is visible at ``as_of`` only when its ``publishedAt`` <= ``as_of``. A date without a time is read as
  00:00 UTC of that day, so a snapshot published during day D is first visible on D + 1 (the upstream commit can land after the US
  close). A later snapshot is never consulted, and adding one can never change an earlier answer.
* ORDER. Snapshots sharing a date (three on 2013-05-05) are ordered by ``publishedAt`` then commit; the latest visible one wins.
* SYMBOL JOIN. Members use ``BF-B``; the CSV rows use ``BF.B``. A member is joined to its row by exact symbol first, then by the
  single observed punctuation variant ('-' -> '.'); the join basis is counted, never silent.
* SECTOR NORMALISATION is a table of OBSERVED raw names only. Official GICS sector names map to themselves. One spelling variant
  is mapped: ``Telecommunications Services`` -> ``Telecommunication Services`` (T and VZ alternate between the two spellings across
  snapshots with nothing else changing). Every other observed raw value is NOT a sector-level label and is returned as ``None``
  with its reason: ``Industries`` (7 rows) and ``Technology`` (4 rows) are not GICS sector names and are not guessed into one
  (mapping them by the same symbol's LATER label would be look-ahead); ``Airlines`` (1 row, 2021-03-11, on the malformed
  ``American Airlines Group`` symbol row recorded in AGENTS v2.27) is likewise unrecognised; the 2023-03-07 snapshot's sector column carries
  sub-industry names (123 distinct values) and is unusable at sector level; a blank cell is ``None``.
* RECLASSIFICATION IS NOT NORMALISATION. ``Telecommunication Services`` and ``Communication Services`` are kept as different
  labels: the latter is a re-defined sector that also absorbed names from Information Technology and Consumer Discretionary
  (GOOGL, FB, DIS, NFLX, CMCSA in the data). The data shows the change only at the 2020-05-10 snapshot because no snapshot exists
  between 2018-04-02 and 2020-05-10.
* CARRY. ``sector_on`` may carry a member's sector from the latest EARLIER visible snapshot that had a usable sector-level label
  for it (never a later one); the basis ``AS_PUBLISHED`` / ``CARRIED_FROM_EARLIER_SNAPSHOT`` / ``UNAVAILABLE`` is returned beside it.
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MEMBERSHIP_PATH = ROOT / "research_specs/alpha-opportunity-model-v1-us-membership.json.gz"
SECTORS_PATH = ROOT / "data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz"

GICS_SECTORS = ("Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy", "Financials", "Health Care",
                "Industrials", "Information Technology", "Materials", "Real Estate", "Telecommunication Services", "Utilities")
SPELLING_VARIANTS = {"Telecommunications Services": "Telecommunication Services"}
NOT_SECTOR_LEVEL = {"Industries": "NOT_A_GICS_SECTOR_NAME_NOT_GUESSED", "Technology": "NOT_A_GICS_SECTOR_NAME_NOT_GUESSED",
                    "Airlines": "NOT_A_GICS_SECTOR_NAME_NOT_GUESSED"}
SUB_INDUSTRY_SNAPSHOT_MIN_LABELS = 20   # a sector column has at most 12 distinct sector-level names; 2023-03-07 carries 123
JOIN_VARIANTS = (("-", "."),)

BASIS_PUBLISHED = "AS_PUBLISHED"
BASIS_CARRIED = "CARRIED_FROM_EARLIER_SNAPSHOT"
BASIS_UNAVAILABLE = "UNAVAILABLE"


def normalise_sector(raw):
    """(canonical sector or None, reason). Only names observed in the data are handled; anything else is unrecognised."""
    if raw is None or not str(raw).strip():
        return None, "BLANK_SECTOR_CELL"
    raw = str(raw).strip()
    if raw in GICS_SECTORS:
        return raw, "OFFICIAL_SECTOR_NAME"
    if raw in SPELLING_VARIANTS:
        return SPELLING_VARIANTS[raw], "SPELLING_VARIANT_OF_OFFICIAL_SECTOR_NAME"
    if raw in NOT_SECTOR_LEVEL:
        return None, NOT_SECTOR_LEVEL[raw]
    return None, "NOT_SECTOR_LEVEL_LABEL"


def _utc(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    text = str(value)
    if len(text) == 10:
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class Snapshot:
    date: str
    published_at: datetime
    source_commit: str
    members: frozenset
    rows: dict = field(compare=False)          # csv symbol -> {"sector": raw, "cik": str|None}
    sector_column: str = ""
    has_cik: bool = False

    @property
    def sub_industry_column(self):
        return len({r.get("sector") for r in self.rows.values()}) >= SUB_INDUSTRY_SNAPSHOT_MIN_LABELS

    def row_for(self, member):
        """(row or None, join basis)."""
        if member in self.rows:
            return self.rows[member], "EXACT_SYMBOL"
        for a, b in JOIN_VARIANTS:
            alt = member.replace(a, b)
            if alt != member and alt in self.rows:
                return self.rows[alt], "PUNCTUATION_VARIANT_" + a + "_TO_" + b
        return None, "NO_ROW"

    def sector_of(self, member):
        """(canonical sector or None, reason) as published in THIS snapshot."""
        row, basis = self.row_for(member)
        if row is None:
            return None, basis
        if self.sub_industry_column:
            return None, "SNAPSHOT_SECTOR_COLUMN_CARRIES_SUB_INDUSTRY"
        return normalise_sector(row.get("sector"))

    def cik_of(self, member):
        row, _ = self.row_for(member)
        return None if row is None else row.get("cik")


def build_snapshots(membership_payload, sector_payload):
    """Join the two payloads on (date, sourceCommit); refuses any snapshot present in one and not the other."""
    members = {(s["date"], s["sourceCommit"]): s for s in membership_payload["snapshots"]}
    sectors = {(s["date"], s["sourceCommit"]): s for s in sector_payload["snapshots"]}
    if set(members) != set(sectors):
        raise ValueError("SNAPSHOT_IDENTITY_MISMATCH")
    out = []
    for key, m in members.items():
        s = sectors[key]
        out.append(Snapshot(date=m["date"], published_at=_utc(m["publishedAt"]), source_commit=m["sourceCommit"],
                            members=frozenset(m["members"]), rows=dict(s["rows"]), sector_column=s.get("sectorColumn", ""),
                            has_cik=bool(s.get("hasCik"))))
    return sorted(out, key=lambda x: (x.published_at, x.source_commit))


def load_snapshots(membership_path=MEMBERSHIP_PATH, sector_path=SECTORS_PATH):
    with gzip.open(membership_path) as fh:
        membership = json.load(fh)
    with gzip.open(sector_path) as fh:
        sectors = json.load(fh)
    return build_snapshots(membership, sectors)


def visible(snapshots, as_of):
    """Snapshots published at or before `as_of` (date -> 00:00 UTC of that day), oldest first."""
    cutoff = _utc(as_of)
    return [s for s in snapshots if s.published_at <= cutoff]


def snapshot_on(snapshots, as_of):
    """The latest snapshot visible at `as_of`, or None. Never a later one."""
    seen = visible(snapshots, as_of)
    return seen[-1] if seen else None


def members_on(snapshots, as_of):
    snap = snapshot_on(snapshots, as_of)
    return frozenset() if snap is None else snap.members


def sector_on(snapshots, as_of, member, carry=True):
    """(sector or None, basis, snapshot date used). Carry looks only at EARLIER visible snapshots in which `member` was a member."""
    seen = visible(snapshots, as_of)
    if not seen or member not in seen[-1].members:
        return None, BASIS_UNAVAILABLE, None
    sector, _ = seen[-1].sector_of(member)
    if sector is not None:
        return sector, BASIS_PUBLISHED, seen[-1].date
    if carry:
        for snap in reversed(seen[:-1]):
            if member not in snap.members:
                break
            earlier, _ = snap.sector_of(member)
            if earlier is not None:
                return earlier, BASIS_CARRIED, snap.date
    return None, BASIS_UNAVAILABLE, None


def membership_table(snapshots, as_of, carry=True):
    """{member: {"sector", "basis", "sectorSnapshot"}} for the snapshot visible at `as_of`."""
    snap = snapshot_on(snapshots, as_of)
    if snap is None:
        return {}
    out = {}
    for m in sorted(snap.members):
        sector, basis, used = sector_on(snapshots, as_of, m, carry=carry)
        out[m] = {"sector": sector, "basis": basis, "sectorSnapshot": used}
    return out
