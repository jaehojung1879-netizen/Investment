"""Git-pinned real inputs for industry-alpha-kr-next-v1. Every byte is read from a pinned git object and verified.

Sources (and the existing pins they are checked against):
* PIT Top120 schedule, v4 industry intervals, crosswalk, terminal identities: committed on main, verified against the
  sealed industry anatomy's own membership pins (`research_specs/kr-industry-opportunity-anatomy-v1.json`), loaded with
  that study's own `load_membership_inputs`.
* KRX universe snapshots (caps): `signal-history@4ea107ed`, each blob checked against the overlay spec's `universeBlobs`.
* Prices: replay-v16 manifest at the same commit (its own digest AND the pinned `replayManifestSha256`), each object
  checked by the content sha256 that is its name.
* PIT accounting: the repaired snapshot at `fb6e8374`, blob sha1 per shard and content sha256 against the overlay spec.

Loading prices reads the whole panel, including dates that are forward windows of earlier signals. That is the same
past-only feature build every sealed KR study performed before its lock; NOTHING here computes a forward return, and
`input_check` publishes counts only.
"""
from __future__ import annotations

import bisect
import gzip
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from pipeline import kr_industry_anatomy_execution as IE
from pipeline import kr_industry_membership as KM
from pipeline import kr_repaired_accounting_snapshot as K
from pipeline import replay_inputs as RI

from . import study as S

ROOT = Path(__file__).resolve().parents[2]
OVERLAY_SPEC = "research_specs/kr-model-overlay-portfolio-v1.json"
ANATOMY_SPEC = "research_specs/kr-industry-opportunity-anatomy-v1.json"


def _git(args, root=ROOT, data=None):
    return subprocess.run(["git", *args], cwd=root, input=data, capture_output=True, check=True).stdout


def git_blobs(commit, paths, root=ROOT):
    """{path: bytes} via one `git cat-file --batch` (objects may be fetched lazily from a blob-less clone)."""
    if not paths:
        return {}
    req = "".join(f"{commit}:{p}\n" for p in paths).encode()
    raw = _git(["cat-file", "--batch"], root, req)
    out, i = {}, 0
    for p in paths:
        header_end = raw.index(b"\n", i)
        header = raw[i:header_end].split()
        if len(header) < 3 or header[1] != b"blob":
            raise ValueError("GIT_OBJECT_MISSING: " + p)
        size = int(header[2])
        out[p] = raw[header_end + 1:header_end + 1 + size]
        i = header_end + 1 + size + 1
    return out


def blob_sha1(raw):
    return hashlib.sha1(b"blob %d\0" % len(raw) + raw).hexdigest()


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


# --------------------------------------------------------------------------- #
# Membership (main)
# --------------------------------------------------------------------------- #
def load_membership(root=ROOT):
    spec = json.loads((Path(root) / ANATOMY_SPEC).read_text())
    for rel, digest in spec["membership"]["files"].items():
        if sha256((Path(root) / rel).read_bytes()) != digest:
            raise ValueError("MEMBERSHIP_PIN_MISMATCH: " + rel)
    intervals, crosswalk, ends = IE.load_membership_inputs(root)
    inputs = json.loads((Path(root) / S.INPUT_POLICY["top120Inputs"]).read_text())
    weekly = {d: [n[4:] if n.startswith("KRX:") else n for n in names]
              for d, names in KM.top120_schedule(inputs)[0].items()}
    terminal = set(json.loads((Path(root) / "data/kr-industry-membership-foundation-v1/identity-provenance.json")
                              .read_text())["terminalSecurities"])
    return {"intervals": intervals, "crosswalk": crosswalk, "ends": ends, "weekly": weekly, "terminal": terminal}


# --------------------------------------------------------------------------- #
# Universe snapshots -> strictly prior caps
# --------------------------------------------------------------------------- #
class SnapshotCaps:
    """Strictly prior monthly KRX universe snapshot cap (issue cap, not free float)."""

    def __init__(self, rows):
        by_date = {}
        for r in rows:
            by_date.setdefault(r["date"], {})[r["ticker"]] = r
        self.dates = sorted(by_date)
        self.by_date = by_date

    def snapshot_before(self, date):
        i = bisect.bisect_left(self.dates, date) - 1
        return self.dates[i] if i >= 0 else None

    def cap(self, ticker, date):
        snap = self.snapshot_before(date)
        row = self.by_date.get(snap, {}).get(ticker) if snap else None
        value = row.get("marketCap") if row else None
        return float(value) if value else None


def load_universe(root=ROOT):
    overlay = json.loads((Path(root) / OVERLAY_SPEC).read_text())
    pins, commit = overlay["inputs"]["universeBlobs"], overlay["inputs"]["universeSourceCommit"]
    if commit != S.INPUT_POLICY["signalHistoryCommit"]:
        raise ValueError("UNIVERSE_COMMIT_DIFFERS_FROM_STUDY_POLICY")
    blobs = git_blobs(commit, sorted(pins), root)
    rows = []
    for path, raw in blobs.items():
        if blob_sha1(raw) != pins[path]:
            raise ValueError("UNIVERSE_BLOB_MISMATCH: " + path)
        rows.extend(json.loads(line) for line in gzip.decompress(raw).decode().splitlines() if line.strip())
    return SnapshotCaps(rows)


# --------------------------------------------------------------------------- #
# Prices (replay-v16 objects)
# --------------------------------------------------------------------------- #
def load_prices(root=ROOT, tickers=None):
    commit = S.INPUT_POLICY["signalHistoryCommit"]
    manifest_raw = git_blobs(commit, ["ledger/historical/replay-v16/inputs.json"], root)["ledger/historical/replay-v16/inputs.json"]
    manifest = json.loads(manifest_raw)
    if RI.digest({k: v for k, v in manifest.items() if k != "sha256"}) != manifest["sha256"] \
            or manifest["sha256"] != S.INPUT_POLICY["replayManifestSha256"]:
        raise ValueError("REPLAY_MANIFEST_MISMATCH")
    refs = [(name, ref) for name in sorted(manifest["components"]) if RI.is_price_panel(name)
            for ref in manifest["components"][name]]
    paths = [f"ledger/replay-inputs/objects/{ref}.json.gz" for _, ref in refs]
    blobs = git_blobs(commit, paths, root)
    rows = {}
    for (_, ref), path in zip(refs, paths):
        raw = gzip.decompress(blobs[path])
        if sha256(raw) != ref:
            raise ValueError("REPLAY_OBJECT_MISMATCH: " + ref)
        for r in json.loads(raw):
            t = r.get("ticker")
            if t and t.endswith(".KS") and (tickers is None or t in tickers):
                prev = rows.setdefault(t, {}).get(r["date"])
                if prev is not None and prev != r:
                    raise ValueError("CONFLICTING_REPLAY_PRICE_RECORD")
                rows[t][r["date"]] = r
    return {t: RI.rows_frame([{k: v for k, v in r.items() if k != "ticker"} for r in by.values()]).sort_index()
            for t, by in rows.items()}, manifest["through"]


# --------------------------------------------------------------------------- #
# Accounting (repaired snapshot)
# --------------------------------------------------------------------------- #
def load_accounting(root=ROOT):
    overlay = json.loads((Path(root) / OVERLAY_SPEC).read_text())
    pin = overlay["inputs"]["accounting"]
    with tempfile.TemporaryDirectory() as tmp:
        merged = K.materialize_from_git(Path(root), Path(tmp), pin["sourceCommit"])["merged"]
        files = K.shard_files(merged)
        blobs = {p.name: K.git_blob_sha1(p.read_bytes()) for p in files}
        if blobs != pin["gitBlobSha1"]:
            raise ValueError("ACCOUNTING_SNAPSHOT_MISSING_OR_CHANGED")
        shards = {p.name: K.read_shard(p) for p in files}
    if K.content_sha256(shards) != pin["contentSha256"]:
        raise ValueError("ACCOUNTING_CONTENT_CHANGED")
    out = {}
    for rows in shards.values():
        for r in rows:
            out.setdefault(r["ticker"], []).append(r)
    return out


# --------------------------------------------------------------------------- #
# Market adapter for the sealed feature function
# --------------------------------------------------------------------------- #
class GitMarket:
    """`.at` / `.trailing` with the interface `kr_value_quality_catalyst.feature_at` expects.

    marketCap = strictly prior universe snapshot (issue cap); volume = replay Volume; tradingValue = replay Close x Volume
    (a PROXY: the replay Close carries forward-accumulated distributions, so this is not the official KRX ACC_TRDVAL)."""

    def __init__(self, caps, prices):
        self.caps, self.prices = caps, prices

    def _row(self, ticker, stamp):
        frame = self.prices.get(ticker)
        if frame is None or stamp not in frame.index:
            return None
        v, c = frame.at[stamp, "Volume"], frame.at[stamp, "Close"]
        if not pd.notna(v) or not pd.notna(c):
            return None
        return {"volume": float(v), "tradingValue": float(v) * float(c)}

    def at(self, ticker, date):
        row = self._row(ticker, pd.Timestamp(date))
        cap = self.caps.cap(ticker, date)
        if row is None or cap is None:
            return None
        return {"marketCap": cap, **row}

    def trailing(self, ticker, date, n):
        frame = self.prices.get(ticker)
        if frame is None:
            return []
        idx = frame.index[frame.index <= pd.Timestamp(date)][-n:]
        return [self._row(ticker, stamp) for stamp in idx]


def identity(root=ROOT):
    """One digest over the pins this study reads (not over the bytes; the bytes are verified against these pins)."""
    overlay = json.loads((Path(root) / OVERLAY_SPEC).read_text())["inputs"]
    anatomy = json.loads((Path(root) / ANATOMY_SPEC).read_text())["membership"]["files"]
    pins = {"policy": S.INPUT_POLICY, "universeBlobs": overlay["universeBlobs"], "accounting": overlay["accounting"],
            "membershipFiles": anatomy,
            "top120InputsSha256": sha256((Path(root) / S.INPUT_POLICY["top120Inputs"]).read_bytes()),
            "terminalFoundationSha256": sha256((Path(root) / S.INPUT_POLICY["terminalFoundation"]).read_bytes())}
    return {"pins": pins, "sha256": sha256(S.canonical(pins))}
