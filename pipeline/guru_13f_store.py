"""Historical, point-in-time Form 13F holdings store — the Guru Decision Atlas.

DATA FOUNDATION ONLY. This module stores what US institutional managers
disclosed on Form 13F and when — nothing evaluative. It never computes a
future/forward return for a position, never ranks or compares managers, and
is never imported by ``pipeline/longterm.py``, ``pipeline/opportunity.py``,
``pipeline/kelly_portfolio.py`` or ``pipeline/build.py`` (mechanically
enforced by ``tests/test_guru_alpha_separation.py``). It is a SEPARATE,
research-only system from ``pipeline/institutional_13f.py`` (the small
manager-watchlist dashboard reader): that module keeps only the most recent
two filings per manager and lets an amendment supersede its original, because
it exists to show "what a manager holds now". This module exists to show
"what was disclosed, and when, across the manager's entire filing history" —
so it never truncates to two filings and never lets an amendment overwrite
the original it amends. Both are kept, distinguished by ``amendmentFlag`` /
``originalOrAmended``, keyed by their own ``accessionNumber``.

WHY NOT AN EXACT TRADE DATE OR PRICE. A 13F reports quarter-end HOLDINGS, not
trades. It says nothing about when inside the quarter a position was bought,
sold, or at what price. Inventing either would be a fabrication with no
source to support it. Instead, a NEW or ADD row carries an
``acquisitionWindowStart``/``acquisitionWindowEnd`` pair: the interval during
which the change could have happened, bounded by the two report dates that
bracket it (or, when there is no earlier report at all, the manager's own
first-ever FILING date — the earliest point at which the public had any
visibility into this manager, which is the only defensible floor when the
position could in principle have existed since before EDGAR ever heard from
this filer).

SCHEMA (one row per manager x accession x CUSIP/class/putCall):
    managerId, managerName, managerCIK, reportDate, filingDate,
    accessionNumber, filingForm, amendmentFlag, originalOrAmended,
    issuer, titleClass, CUSIP, putCall, shares, reportedValue,
    portfolioWeight, previousShares, changeShares, changePct, action,
    acquisitionWindowStart, acquisitionWindowEnd, id

ACTION THRESHOLD. ``classify_action`` returns HOLD, not ADD/REDUCE, whenever
EITHER the relative share change is under ``ACTION_RELATIVE_CHANGE_PCT``
(0.5%, matching the 0.5% band ``institutional_13f._changes`` already uses
for its own increased/decreased split, so this repository's two 13F readers
do not define "noise" two different ways) OR the absolute share change is
under ``ACTION_MIN_ABSOLUTE_SHARE_CHANGE`` (100 shares). Either test alone
guards a different rounding failure: a relative-only rule reads a 1-share
move on a 3-share base as a 33% "increase"; an absolute-only rule reads a
0.6% move on a billion-share base as material. A move must clear BOTH bars
to be called a real change.

STORAGE. Rows are sharded by report quarter under
``data/research/guru-decision-atlas/holdings-<YYYY-Qn>.jsonl.gz``, gzip
encoded byte-deterministically via ``historical_store.encode`` — the same
encoder ``ledger/historical`` uses, reused rather than reimplemented, so an
unchanged shard re-serializes to identical bytes and git records no diff.
The path layout differs from ``historical_store``'s (report quarter, not
signal month; one kind, not signals+outcomes; no replay generation
directory) because this store has no generation concept and is two orders
of magnitude smaller than the historical ledger it borrows the encoder from
— a dedicated small manifest is cheaper and clearer here than bending
``historical_store``'s generation-keyed layout to a store that has none.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path

from . import historical_store as HS
from .config import REPO_ROOT

STORE_ROOT = REPO_ROOT / "data" / "research" / "guru-decision-atlas"
MANIFEST_NAME = "manifest.json"
STORE_VERSION = "GURU_13F_STORE_V1"

NEW = "NEW"
ADD = "ADD"
HOLD = "HOLD"
REDUCE = "REDUCE"
EXIT = "EXIT"
ACTIONS = (NEW, ADD, HOLD, REDUCE, EXIT)

ORIGINAL = "ORIGINAL"
AMENDED = "AMENDED"

# See the module docstring's "ACTION THRESHOLD" section for the reasoning.
ACTION_RELATIVE_CHANGE_PCT = 0.5
ACTION_MIN_ABSOLUTE_SHARE_CHANGE = 100.0

_SHARD_RE = re.compile(r"^holdings-(\d{4}-Q[1-4])\.jsonl\.gz$")


# --------------------------------------------------------------------------- #
# Paths / shard discovery
# --------------------------------------------------------------------------- #
def shard_key(report_date: str) -> str:
    """``2019-03-31`` -> ``2019-Q1``. Shards by report quarter, not by
    filing date, so every position disclosed for the same quarter-end lands
    in one shard regardless of how long a filer took to submit it."""
    year, month = int(report_date[:4]), int(report_date[5:7])
    quarter = (month - 1) // 3 + 1
    return f"{year}-Q{quarter}"


def shard_path(root: Path, key: str) -> Path:
    return Path(root) / f"holdings-{key}.jsonl.gz"


def iter_shards(root: Path) -> list[tuple[str, Path]]:
    root = Path(root)
    if not root.is_dir():
        return []
    found = []
    for path in root.iterdir():
        match = _SHARD_RE.match(path.name)
        if match:
            found.append((match.group(1), path))
    return sorted(found)


# --------------------------------------------------------------------------- #
# Action classification and change fields
# --------------------------------------------------------------------------- #
def classify_action(previous_shares: float, current_shares: float) -> str:
    """Deterministic, threshold-gated — see the module docstring."""
    if previous_shares <= 0 and current_shares > 0:
        return NEW
    if current_shares <= 0 and previous_shares > 0:
        return EXIT
    if previous_shares <= 0 and current_shares <= 0:
        return HOLD
    change = current_shares - previous_shares
    relative_pct = abs(change / previous_shares) * 100.0
    if relative_pct < ACTION_RELATIVE_CHANGE_PCT or abs(change) < ACTION_MIN_ABSOLUTE_SHARE_CHANGE:
        return HOLD
    return ADD if change > 0 else REDUCE


def _position_key(row: dict) -> tuple[str, str, str]:
    return (row["cusip"], row.get("putCall") or "", row.get("titleClass") or "")


def _aggregate_infotable(rows: list[dict]) -> dict[tuple, dict]:
    """Flat parsed infoTable rows -> one row per (CUSIP, putCall, class).

    The same grouping rule ``institutional_13f._aggregate`` applies,
    reimplemented here rather than imported so this module's only dependency
    on the dashboard reader is its pure XML parser, not its private helpers.
    """
    grouped: dict[tuple, dict] = {}
    for row in rows:
        key = _position_key(row)
        if key not in grouped:
            grouped[key] = dict(row)
        else:
            grouped[key]["valueUsd"] += row["valueUsd"]
            grouped[key]["shares"] += row["shares"]
    return grouped


def _next_day(iso_date: str) -> str:
    return (date.fromisoformat(iso_date) + timedelta(days=1)).isoformat()


# --------------------------------------------------------------------------- #
# The row builder
# --------------------------------------------------------------------------- #
def build_manager_rows(manager: dict, filings: list[dict]) -> list[dict]:
    """One manager's entire filing history -> the full schema, every filing
    scored independently against a shared, chronological baseline.

    ``filings``: any order, each a dict with ``accessionNumber``,
    ``filingDate``, ``reportDate``, ``filingForm`` (``13F-HR`` or
    ``13F-HR/A``) and ``infoTableRows`` (flat rows from
    ``institutional_13f.parse_information_table``, not yet aggregated).

    For each report date, the BASELINE that the next quarter's changes are
    measured against comes from that quarter's PRIMARY filing only — the
    13F-HR when one was filed, else the earliest 13F-HR/A. An amendment is
    stored with its own action/change columns computed against the same
    baseline its quarter's original was, but it never becomes the baseline
    for the quarter AFTER it: this repository's point-in-time discipline
    treats what was ORIGINALLY disclosed for a quarter as what the public
    knew going into the next one, not a later restatement of it.
    """
    ordered = sorted(filings, key=lambda f: (f["reportDate"], f["filingDate"], f["accessionNumber"]))
    if not ordered:
        return []
    first_filing_date = min(f["filingDate"] for f in ordered)

    by_report_date: dict[str, list[dict]] = {}
    for filing in ordered:
        by_report_date.setdefault(filing["reportDate"], []).append(filing)
    report_dates = sorted(by_report_date)

    baseline: dict[str, dict[tuple, dict]] = {}
    for report_date in report_dates:
        candidates = by_report_date[report_date]
        primary = next((f for f in candidates if f["filingForm"] == "13F-HR"), candidates[0])
        baseline[report_date] = _aggregate_infotable(primary["infoTableRows"])

    previous_report_date = {
        report_date: (report_dates[i - 1] if i else None)
        for i, report_date in enumerate(report_dates)
    }

    out: list[dict] = []
    for filing in ordered:
        current = _aggregate_infotable(filing["infoTableRows"])
        total_value = sum(row["valueUsd"] for row in current.values())
        prior_report_date = previous_report_date[filing["reportDate"]]
        prior = baseline.get(prior_report_date, {}) if prior_report_date else {}
        amended = filing["filingForm"].endswith("/A")

        for key in sorted(set(current) | set(prior)):
            cur = current.get(key)
            base = prior.get(key)
            previous_shares = float(base["shares"]) if base else 0.0
            current_shares = float(cur["shares"]) if cur else 0.0
            action = classify_action(previous_shares, current_shares)
            change_shares = current_shares - previous_shares
            change_pct = None if previous_shares == 0 else round(change_shares / previous_shares * 100, 2)
            reported_value = float(cur["valueUsd"]) if cur else 0.0
            template = cur or base

            window_start = window_end = None
            if action in (NEW, ADD):
                window_end = filing["reportDate"]
                window_start = _next_day(prior_report_date) if prior_report_date else first_filing_date

            out.append({
                "managerId": manager["id"], "managerName": manager["name"],
                "managerCIK": manager["cik"], "reportDate": filing["reportDate"],
                "filingDate": filing["filingDate"], "accessionNumber": filing["accessionNumber"],
                "filingForm": filing["filingForm"], "amendmentFlag": amended,
                "originalOrAmended": AMENDED if amended else ORIGINAL,
                "issuer": template["issuer"], "titleClass": template.get("titleClass") or "—",
                "CUSIP": key[0], "putCall": template.get("putCall"),
                "shares": current_shares, "reportedValue": reported_value,
                "portfolioWeight": (round(reported_value / total_value * 100, 4)
                                    if total_value else None),
                "previousShares": previous_shares, "changeShares": change_shares,
                "changePct": change_pct, "action": action,
                "acquisitionWindowStart": window_start, "acquisitionWindowEnd": window_end,
                "id": f"{filing['accessionNumber']}:{key[0]}:{key[1]}:{key[2]}",
            })
    return out


def reconstruct_infotable_rows(stored_rows: list[dict]) -> list[dict]:
    """The inverse of ``build_manager_rows`` for one filing's own rows.

    A resumable backfill must not re-download a filing just to rebuild the
    NEXT quarter's baseline off it — the filing's own holdings are already
    sitting in the store. A synthesized EXIT row (``shares == 0``) was never
    actually in the filing and is excluded; every other row reproduces
    exactly what that filing reported.
    """
    return [
        {"issuer": row["issuer"], "titleClass": row["titleClass"], "cusip": row["CUSIP"],
         "valueUsd": row["reportedValue"], "shares": row["shares"],
         "shareType": "SH", "putCall": row.get("putCall")}
        for row in stored_rows if row.get("shares", 0) > 0
    ]


# --------------------------------------------------------------------------- #
# Writing / reading the store
# --------------------------------------------------------------------------- #
def _dedupe_by_id(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        rid = row.get("id")
        if rid in seen:
            continue
        seen.add(rid)
        out.append(row)
    return out


def _sort_key(row: dict) -> tuple:
    return (str(row.get("reportDate") or ""), str(row.get("managerCIK") or ""),
            str(row.get("CUSIP") or ""), str(row.get("id") or ""))


def write_holdings(root: Path, rows: list[dict]) -> tuple[int, int]:
    """Append unseen rows into their quarter shards. Returns (appended, skipped).

    An id already on disk is skipped, never overwritten — the same
    immutability discipline ``historical_store.append_signals`` uses for the
    historical ledger. This is what makes a re-run of the backfill safe:
    recomputing a manager's full history and calling this again writes
    nothing new for filings that were already stored.
    """
    root = Path(root)
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(shard_key(row["reportDate"]), []).append(row)

    appended = skipped = 0
    for key, batch in grouped.items():
        path = shard_path(root, key)
        existing = HS.read_jsonl(path)
        existing_ids = {row.get("id") for row in existing}
        fresh = [row for row in batch if row.get("id") not in existing_ids]
        skipped += len(batch) - len(fresh)
        if not fresh:
            continue
        merged = sorted(_dedupe_by_id(existing + fresh), key=_sort_key)
        payload = HS.encode(merged)
        if not path.exists() or path.read_bytes() != payload:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        appended += len(fresh)
    return appended, skipped


def load_holdings(root: Path) -> list[dict]:
    out: list[dict] = []
    for _, path in iter_shards(root):
        out.extend(HS.read_jsonl(path))
    return out


def processed_filings(root: Path) -> set[tuple[str, str, str]]:
    """``(managerCIK, reportDate, accessionNumber)`` triples already stored —
    the resumability index a backfill checks before re-downloading a filing.
    """
    seen: set[tuple[str, str, str]] = set()
    for _, path in iter_shards(root):
        for row in HS.iter_jsonl(path):
            seen.add((row.get("managerCIK"), row.get("reportDate"), row.get("accessionNumber")))
    return seen


def write_manifest(root: Path) -> dict:
    """A cheap index of what is on disk: shards, records, bytes, a sha256 per
    shard — the content-addressed check that makes an unexpectedly-changed
    shard visible in a diff review without decompressing anything."""
    root = Path(root)
    manifest: dict = {
        "storeVersion": STORE_VERSION,
        "shardKey": "report quarter (YYYY-Qn), derived from reportDate",
        "compression": "gzip", "shards": {}, "totalBytes": 0, "totalRecords": 0,
    }
    for key, path in iter_shards(root):
        size = path.stat().st_size
        records = sum(1 for _ in HS.iter_jsonl(path))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest["shards"][key] = {"bytes": size, "records": records, "sha256": digest}
        manifest["totalBytes"] += size
        manifest["totalRecords"] += records
    root.mkdir(parents=True, exist_ok=True)
    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def read_manifest(root: Path) -> dict:
    path = Path(root) / MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
