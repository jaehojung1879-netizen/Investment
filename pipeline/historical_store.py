"""On-disk layout for the HISTORICAL_OOS ledger.

A decade of weekly cross-sections over ~625 names is ~400k signal records and
roughly the same number of outcomes. Written as two monolithic JSONL files that
is ~900 MB and ~830 MB — past GitHub's 100 MB blob limit, so the replay job
computed a full decade of evidence every night and then had its push rejected.
Nothing ever landed; the "incremental" replay restarted from zero each run.

This module stores the same records in a shape a git branch can actually carry:

    ledger/historical/<replayVersion>/signals-<YYYY-MM>.jsonl.gz
    ledger/historical/<replayVersion>/outcomes-<YYYY-MM>.jsonl.gz
    ledger/historical/manifest.json

Three properties matter, and each one is a deliberate choice:

*Sharded by signal month.* Only the shards a run actually touches are rewritten.
Signals are immutable, so old signal shards are written once and never again;
outcomes stop changing once every horizon in that month has matured, about a
year after the fact. A daily commit therefore carries a few hundred KB rather
than a fresh copy of the entire ledger.

*Separated by replay generation.* A generation is a directory. Evidence from two
replay versions cannot be pooled by accident because it is not even in the same
file — the same invariant the old layout enforced with a per-row filter.

*Byte-deterministic.* Rows are sorted, gzip is given a fixed mtime, so an
unchanged shard re-serializes to identical bytes and git records no change at
all. Without this, recomputing outcomes would produce a new blob for every
shard every night, which is the monolithic problem again in slow motion.

Legacy monolithic files are still readable, and ``migrate_legacy`` converts
them in place, so an existing ledger is never stranded.
"""
from __future__ import annotations

import gzip
import io
import json
import re
from collections.abc import Iterable, Iterator
from pathlib import Path

SIGNALS = "signals"
OUTCOMES = "outcomes"
KINDS = (SIGNALS, OUTCOMES)

STORE_DIR = "historical"
MANIFEST_NAME = "manifest.json"
DIAGNOSTICS_NAME = "historical-diagnostics.json"
UNIVERSE_NAME = "universe.json"
LEGACY_NAMES = {SIGNALS: "historical-signals.jsonl",
                OUTCOMES: "historical-outcomes.jsonl"}

LAYOUT_VERSION = 2

# GitHub's pre-receive hook rejects any blob over 100 MB. We refuse well below
# it: a shard is rewritten whenever records land in its month, so a small shard
# is also what keeps each commit small. Exceeding this is a bug in the shard key
# (too coarse), not a reason to raise the ceiling.
GITHUB_BLOB_LIMIT = 100 * 1024 * 1024
MAX_SHARD_BYTES = 48 * 1024 * 1024

UNDATED_SHARD = "undated"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
# ``undated`` is matched too: a record with an unparseable date is a bug worth
# seeing, and dropping it from the index would hide it rather than surface it.
_SHARD_RE = re.compile(
    rf"^(signals|outcomes)-(\d{{4}}-\d{{2}}|{UNDATED_SHARD})\.jsonl\.gz$")


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def _safe(value: str | None, fallback: str = "unversioned") -> str:
    text = _UNSAFE.sub("-", str(value or "")).strip("-")
    return text or fallback


def store_root(ledger_dir: str | Path) -> Path:
    return Path(ledger_dir) / STORE_DIR


def generation_dir(ledger_dir: str | Path, generation: str | None) -> Path:
    return store_root(ledger_dir) / _safe(generation)


def shard_key(date: str | None) -> str:
    """Month bucket for a record. ``2019-03-22`` -> ``2019-03``."""
    text = str(date or "")
    return text[:7] if len(text) >= 7 and text[4] == "-" else UNDATED_SHARD


def shard_path(ledger_dir: str | Path, generation: str | None, kind: str,
               key: str) -> Path:
    return generation_dir(ledger_dir, generation) / f"{kind}-{key}.jsonl.gz"


def legacy_path(ledger_dir: str | Path, kind: str) -> Path:
    return Path(ledger_dir) / LEGACY_NAMES[kind]


def diagnostics_path(ledger_dir: str | Path) -> Path:
    return Path(ledger_dir) / DIAGNOSTICS_NAME


def generations(ledger_dir: str | Path) -> list[str]:
    root = store_root(ledger_dir)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def iter_shards(ledger_dir: str | Path, kind: str,
                generation: str | None = None) -> list[tuple[str, str, Path]]:
    """``(generation, shard key, path)`` for every shard, in a stable order."""
    if generation is not None:
        names = [_safe(generation)]
    else:
        names = generations(ledger_dir)
    found: list[tuple[str, str, Path]] = []
    for name in names:
        folder = store_root(ledger_dir) / name
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            match = _SHARD_RE.match(path.name)
            if match and match.group(1) == kind:
                found.append((name, match.group(2), path))
    return sorted(found, key=lambda item: (item[0], item[1]))


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #
def _sort_key(row: dict) -> tuple:
    return (str(row.get("date") or row.get("asOf") or ""),
            str(row.get("region") or ""),
            str(row.get("ticker") or ""),
            str(row.get("id") or ""))


def encode(rows: Iterable[dict]) -> bytes:
    """Deterministic gzip: same records in, same bytes out, every time."""
    payload = "".join(
        json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows
    ).encode("utf-8")
    buffer = io.BytesIO()
    # mtime=0 and a fixed compress level are what make the output reproducible;
    # the default embeds "now" in the header and every rewrite becomes a diff.
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(payload)
    return buffer.getvalue()


def read_jsonl(path: str | Path) -> list[dict]:
    """Read a shard or a plain ``.jsonl``; gzip is detected by extension."""
    p = Path(path)
    if not p.exists():
        return []
    if p.suffix == ".gz":
        with gzip.open(p, "rt", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    with p.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def iter_jsonl(path: str | Path) -> Iterator[dict]:
    """Stream a shard without materializing it — used for id scans."""
    p = Path(path)
    if not p.exists():
        return
    opener = (lambda: gzip.open(p, "rt", encoding="utf-8")) if p.suffix == ".gz" \
        else (lambda: p.open("r", encoding="utf-8"))
    with opener() as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def write_shard(path: str | Path, rows: list[dict]) -> bool:
    """Write a shard, sorted and deduplicated. True if the bytes changed.

    An empty shard is removed rather than left behind as an empty file, so a
    directory listing is always an honest index of what exists.
    """
    p = Path(path)
    ordered = sorted(_dedupe(rows), key=_sort_key)
    if not ordered:
        if p.exists():
            p.unlink()
            return True
        return False
    payload = encode(ordered)
    if p.exists() and p.read_bytes() == payload:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(payload)
    return True


def _dedupe(rows: Iterable[dict]) -> list[dict]:
    """First write of an id wins — an existing record is never replaced."""
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        rid = row.get("id")
        if rid is None:
            out.append(row)
            continue
        if rid in seen:
            continue
        seen.add(rid)
        out.append(row)
    return out


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
def load(ledger_dir: str | Path, kind: str,
         generation: str | None = None, project=None) -> list[dict]:
    """Every record of one kind, oldest shard first.

    Falls back to the legacy monolithic file when no shards exist, so a ledger
    written by the previous layout still reads.

    ``project`` is applied to each record as it is read and only its result is
    kept, so the discarded part never coexists with the rest of the ledger. That
    matters at this size: 413k signals plus 409k outcomes hold 8.5 GB, and a
    signal's ``features`` block is 28 of its 37 keys while the audit path reads
    exactly one of them. Restoring former index members widens the cross-section
    by half again, which without a projection lands around 12.8 GB before
    `alpha_diagnostics` builds its frames — on a 16 GB runner that is an OOM,
    and an OOM in the nightly job looks like the pipeline being broken again.
    """
    shards = iter_shards(ledger_dir, kind, generation)
    if not shards:
        rows = read_jsonl(legacy_path(ledger_dir, kind))
        if generation is not None:
            rows = [row for row in rows if row.get("replayVersion") == generation]
        return [project(row) for row in rows] if project else rows
    out: list[dict] = []
    for _, _, path in shards:
        if project:
            # Projected shard by shard so the full records are freed between
            # shards instead of all being alive at the peak.
            out.extend(project(row) for row in iter_jsonl(path))
        else:
            out.extend(read_jsonl(path))
    return out


def audit_projection(row: dict) -> dict:
    """Trim a signal to what the audit path actually reads.

    `portfolio_validation` touches exactly one key inside `features`
    (`evidenceCoverage`); the other 27 exist for `opportunity.build_dataset`,
    which the audits never call. Keeping the block whole costs gigabytes for one
    float.
    """
    features = row.get("features")
    if not features:
        return row
    trimmed = dict(row)
    trimmed["features"] = {"evidenceCoverage": features.get("evidenceCoverage")}
    return trimmed


def ids_by_generation(ledger_dir: str | Path, kind: str) -> dict[str, set[str]]:
    """Record ids grouped by replay generation, without loading the records.

    The incremental replay only needs to know what already exists. Reading four
    hundred thousand full records to answer that costs gigabytes; reading their
    ids costs tens of megabytes.
    """
    out: dict[str, set[str]] = {}
    shards = iter_shards(ledger_dir, kind)
    sources: list[Path] = [path for _, _, path in shards]
    if not sources:
        legacy = legacy_path(ledger_dir, kind)
        if legacy.exists():
            sources = [legacy]
    for path in sources:
        for row in iter_jsonl(path):
            rid = row.get("id")
            if rid is None:
                continue
            out.setdefault(str(row.get("replayVersion") or "unversioned"), set()).add(rid)
    return out


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #
def append_signals(ledger_dir: str | Path, rows: list[dict]) -> tuple[int, int]:
    """Append unseen signals into their month shards. Returns (appended, skipped).

    Only the shards that receive new records are read and rewritten, and an id
    already on disk is skipped — signals are immutable, so a second sighting of
    an id is never allowed to overwrite the first.
    """
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        if not row.get("id"):
            continue
        key = (_safe(row.get("replayVersion")), shard_key(row.get("date") or row.get("asOf")))
        grouped.setdefault(key, []).append(row)

    appended = skipped = 0
    for (generation, key), batch in grouped.items():
        path = shard_path(ledger_dir, generation, SIGNALS, key)
        existing = read_jsonl(path)
        seen = {row.get("id") for row in existing}
        fresh = []
        for row in batch:
            if row["id"] in seen:
                skipped += 1
                continue
            seen.add(row["id"])
            fresh.append(row)
        if not fresh:
            continue
        write_shard(path, existing + fresh)
        appended += len(fresh)
    return appended, skipped


def write_outcomes_shard(ledger_dir: str | Path, generation: str | None,
                         key: str, rows: list[dict]) -> bool:
    """Replace one outcome shard. Outcomes are derived, so replacing is correct."""
    return write_shard(shard_path(ledger_dir, generation, OUTCOMES, key), rows)


def prune_orphan_outcomes(ledger_dir: str | Path, generation: str | None,
                          keep: Iterable[str]) -> int:
    """Drop outcome shards with no matching signal shard."""
    keep = set(keep)
    removed = 0
    for _, key, path in iter_shards(ledger_dir, OUTCOMES, generation):
        if key not in keep:
            path.unlink()
            removed += 1
    return removed


# --------------------------------------------------------------------------- #
# Manifest & size guard
# --------------------------------------------------------------------------- #
def audit(ledger_dir: str | Path) -> list[dict]:
    """Every stored file with its size, largest first."""
    root = store_root(ledger_dir)
    files = [p for p in root.rglob("*") if p.is_file()] if root.is_dir() else []
    for kind in KINDS:
        legacy = legacy_path(ledger_dir, kind)
        if legacy.exists():
            files.append(legacy)
    rows = [{"path": str(p.relative_to(Path(ledger_dir))), "bytes": p.stat().st_size}
            for p in files]
    return sorted(rows, key=lambda row: row["bytes"], reverse=True)


def oversized(ledger_dir: str | Path, limit: int = MAX_SHARD_BYTES) -> list[dict]:
    return [row for row in audit(ledger_dir) if row["bytes"] > limit]


def assert_pushable(ledger_dir: str | Path, limit: int = MAX_SHARD_BYTES) -> None:
    """Fail here, with an explanation, rather than at GitHub's pre-receive hook.

    A remote rejection arrives after the expensive part of the job has already
    run and says nothing about which knob to turn; this says exactly which shard
    grew and that the shard key is what needs to change.
    """
    too_big = oversized(ledger_dir, limit)
    if not too_big:
        return
    lines = [f"  {row['path']}  {row['bytes'] / 1024 / 1024:.1f} MB" for row in too_big]
    raise RuntimeError(
        "historical ledger shards exceed the writable size limit "
        f"({limit / 1024 / 1024:.0f} MB; GitHub rejects blobs over "
        f"{GITHUB_BLOB_LIMIT / 1024 / 1024:.0f} MB):\n" + "\n".join(lines) +
        "\nThe shard key is too coarse for this universe — shard finer rather "
        "than raising the limit.")


def write_manifest(ledger_dir: str | Path, *, diagnostics: dict | None = None) -> dict:
    """An index of what is on disk: shards, record counts, bytes.

    Cheap to read and enough to answer "did the replay actually land, and how
    much of it" without decompressing a single shard.
    """
    manifest = {
        "layoutVersion": LAYOUT_VERSION,
        "shardKey": "signal month (YYYY-MM)",
        "compression": "gzip",
        "generations": {},
        "totalBytes": 0,
    }
    for generation in generations(ledger_dir):
        block: dict = {"signals": {}, "outcomes": {}, "bytes": 0}
        for kind in KINDS:
            for _, key, path in iter_shards(ledger_dir, kind, generation):
                size = path.stat().st_size
                block[kind][key] = {"bytes": size,
                                    "records": sum(1 for _ in iter_jsonl(path))}
                block["bytes"] += size
        block["signalRecords"] = sum(s["records"] for s in block["signals"].values())
        block["outcomeRecords"] = sum(s["records"] for s in block["outcomes"].values())
        manifest["generations"][generation] = block
        manifest["totalBytes"] += block["bytes"]
    if diagnostics:
        manifest["lastRun"] = {
            "replayVersion": diagnostics.get("replayVersion"),
            "firstDate": diagnostics.get("firstDate"),
            "lastDate": diagnostics.get("lastDate"),
            "replayDates": diagnostics.get("replayDates"),
        }
    root = store_root(ledger_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


# --------------------------------------------------------------------------- #
# Which universe a generation's records were produced against
# --------------------------------------------------------------------------- #
def universe_stamp_path(ledger_dir: str | Path, generation: str | None) -> Path:
    return generation_dir(ledger_dir, generation) / UNIVERSE_NAME


def read_universe_stamp(ledger_dir: str | Path, generation: str | None) -> dict:
    path = universe_stamp_path(ledger_dir, generation)
    if not path.exists():
        return {}
    try:
        stamp = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return stamp if isinstance(stamp, dict) else {}


def stamp_universe(ledger_dir: str | Path, generation: str | None,
                   signature: dict, **detail) -> dict:
    """Record the universe definition this generation's records were built on.

    A sidecar rather than a manifest field on purpose: the manifest is rebuilt
    from the shards on every run, so anything written there is only as durable
    as the code that rebuilds it. This has to outlive that.
    """
    stamp = {**dict(signature), **detail}
    path = universe_stamp_path(ledger_dir, generation)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stamp, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return stamp


def universe_conflict(ledger_dir: str | Path, generation: str | None,
                      signature: dict, *,
                      survivors_only: str = "survivors-only") -> str | None:
    """The reason this generation must not be extended, or None if it may be.

    Appending is safe only while the cross-section is defined the same way.
    `alphaPercentile` is a rank WITHIN the date's cross-section and selection
    puts a floor on it, so widening the universe silently rewrites what every
    surviving name's old record meant — and the old records are skipped by id,
    so they keep the ranks they were given against a universe that no longer
    exists. The result reads as one clean generation and is two.

    Three things are refused, and only these three:

      * the MODE changed — survivors-only became point-in-time, or back;
      * a region that had membership coverage no longer has any;
      * a region's membership SHRANK, which means the file lost names that
        were in the historical cross-section.

    Growth is not refused. The index gains members every month and CI rebuilds
    the file on every run, so gating on the exact content hash would refuse the
    second run and every run after it — a guard that has to be switched off to
    get any work done protects nothing.

    An unstamped generation that already holds records predates this stamp, so
    it was necessarily built from today's constituent list. That is a conflict
    with anything but survivors-only — not an unknown to wave through.
    """
    existing = len(ids_by_generation(ledger_dir, SIGNALS).get(generation, set()))
    if not existing:
        return None
    recorded = read_universe_stamp(ledger_dir, generation)
    was = recorded.get("mode") or survivors_only
    now = signature.get("mode")
    head = f"generation {generation!r} holds {existing} signals"
    tail = ("Cross-sectional ranks are not comparable across universes; bump "
            "REPLAY_VERSION to start a new generation instead of mixing them.")
    if was != now:
        return f"{head} built with universe mode {was!r}, but this run resolves {now!r}. {tail}"
    before = recorded.get("regions") or {}
    for region, count in sorted(before.items()):
        current = (signature.get("regions") or {}).get(region, 0)
        if current < int(count or 0):
            what = ("no longer has any" if not current
                    else f"describes only {current} of {count}")
            return (f"{head} whose {region} cross-section came from {count} "
                    f"described names; this run {what}. {tail}")
    return None


def read_manifest(ledger_dir: str | Path) -> dict:
    path = store_root(ledger_dir) / MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


# --------------------------------------------------------------------------- #
# Migration
# --------------------------------------------------------------------------- #
def migrate_legacy(ledger_dir: str | Path, *, remove: bool = True) -> dict:
    """Convert monolithic ``historical-*.jsonl`` files into shards.

    Records are moved verbatim — the migration re-files them, it never rewrites
    them, so an id that existed before the migration exists after it unchanged.
    """
    moved = {SIGNALS: 0, OUTCOMES: 0}
    for kind in KINDS:
        legacy = legacy_path(ledger_dir, kind)
        if not legacy.exists():
            continue
        grouped: dict[tuple[str, str], list[dict]] = {}
        for row in iter_jsonl(legacy):
            key = (_safe(row.get("replayVersion")),
                   shard_key(row.get("date") or row.get("asOf")))
            grouped.setdefault(key, []).append(row)
            moved[kind] += 1
        for (generation, key), batch in grouped.items():
            path = shard_path(ledger_dir, generation, kind, key)
            write_shard(path, read_jsonl(path) + batch)
        if remove:
            legacy.unlink()
    return moved
