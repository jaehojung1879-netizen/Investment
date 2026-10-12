"""Prospective US observations, isolated from signals and historical research.

Raw Yahoo bars are split-adjusted / dividend-unadjusted. Only the repository's
strictly-after split factor is used to restore as-traded OHLCV and dividends.
No total-return index, label, model or investment decision is produced here.
"""
from __future__ import annotations

from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from zoneinfo import ZoneInfo

import exchange_calendars as xc
import pandas as pd

from . import collector_outcomes as CO
from . import historical_store as HS
from .datafeed import AS_TRADED_WITH_ACTIONS
from .market_dates import normalize_daily_index
from .price_adjustment import ADJUSTMENT_VERSION, future_split_factor
from .replay_calendar import CALENDAR_VERSION, sessions
from .universe import _MIN_SP500_CONSTITUENTS, _us_symbol

VERSION = "us-prospective-daily-market-data-v1"
LIVE = "LIVE_SOURCE_OBSERVATION"
SYNTHETIC = "SYNTHETIC_FIXTURE"
BENCHMARKS = ("SPY", "QQQ")
CLOSE_GRACE_MINUTES = 60
MAX_WINDOW_SESSIONS = 7
ROOT = Path(__file__).resolve().parents[1]
PRICE_BASIS = "AS_TRADED_OHLCV_NO_TOTAL_RETURN_ADJUSTMENT"
SOURCE_BASIS = "YAHOO_SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED"
PRICE_OPTIONS = {"interval": "1d", "auto_adjust": False, "back_adjust": False,
                 "repair": False, "actions": True}


class Refused(ValueError):
    def __init__(self, code, message, outcome=CO.BLOCKED_SOURCE):
        super().__init__(message)
        self.code, self.outcome = code, outcome


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def utc(value):
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise Refused("UTC_TIMESTAMP_REQUIRED", "Acquisition timestamps must explicitly be UTC")
    return stamp.astimezone(timezone.utc)


def stamp(value):
    return utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def sealed(row):
    value = dict(row)
    value["digest"] = digest(value)
    return value


def completed_sessions(now, count=MAX_WINDOW_SESSIONS):
    """XNYS schedule includes holidays, DST and early closes; missing bars do not."""
    at = utc(now)
    end = at.date().isoformat()
    start = (at.date() - timedelta(days=40)).isoformat()
    calendar = xc.get_calendar("XNYS", start="1990-01-01", end="2035-12-31")
    closed = [s.strftime("%Y-%m-%d") for s in sessions(start, end, "US")
              if calendar.session_close(s).to_pydatetime() + timedelta(minutes=CLOSE_GRACE_MINUTES) <= at]
    return closed[-count:]


@dataclass(frozen=True)
class MembershipResponse:
    raw: bytes
    source: str
    source_identity: str
    observed_at: str
    source_last_changed_at: str
    source_kind: str = LIVE


@dataclass(frozen=True)
class PriceResponse:
    frame: pd.DataFrame
    metadata: dict
    observed_at: str
    source: str = "Yahoo Finance/yfinance"
    source_version: str = "yfinance-0.2.65"


def membership_snapshot(response: MembershipResponse, now):
    observed = utc(response.observed_at)
    if response.source_kind not in (LIVE, SYNTHETIC):
        raise Refused("UNKNOWN_SOURCE_KIND", "Explicit real or synthetic source kind required")
    if not response.source or not response.source_identity:
        raise Refused("SOURCE_IDENTITY_MISSING", "Membership source identity is missing")
    if not timedelta(0) <= utc(now)-observed <= timedelta(hours=36):
        raise Refused("STALE_OR_FUTURE_UNIVERSE", "Membership observation is stale or future-dated")
    if utc(response.source_last_changed_at) > observed:
        raise Refused("FUTURE_SOURCE_REVISION", "Source revision was not observable at acquisition")
    try:
        reader = csv.DictReader(io.StringIO(response.raw.decode("utf-8-sig")))
        if not {"Symbol", "Security", "CIK"}.issubset(reader.fieldnames or []):
            raise ValueError("Required membership columns missing")
        raw_rows = list(reader)
        members, seen = [], set()
        for row in raw_rows:
            symbol, name, cik = row["Symbol"].strip().upper(), row["Security"].strip(), row["CIK"].strip()
            if None in row or any(v is None for v in row.values()):
                raise ValueError("Incomplete CSV row")
            ticker = _us_symbol(symbol)
            if (not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", symbol) or not name or
                    not re.fullmatch(r"\d{1,10}", cik) or int(cik) <= 0 or
                    ticker in seen or ticker in BENCHMARKS):
                raise ValueError("Invalid, ambiguous or duplicate member; no row may be dropped")
            seen.add(ticker)
            cik = cik.zfill(10)
            members.append({"ticker": ticker, "sourceSymbol": symbol, "issuerName": name,
                            "issuerCik": cik, "securityId": f"CIK:{cik}|CLASS_SYMBOL:{ticker}",
                            "identityStatus": "PROVISIONAL_CIK_SYMBOL_NOT_PERMANENT_SECURITY_ID",
                            "providerDateAdded": row.get("Date added") or None})
        minimum = _MIN_SP500_CONSTITUENTS if response.source_kind == LIVE else 1
        if not minimum <= len(members) <= 550:
            raise ValueError(f"Incomplete or implausible constituent response: {len(members)}")
    except (ValueError, AttributeError, KeyError, UnicodeError) as exc:
        raise Refused("MEMBERSHIP_SCHEMA_OR_COMPLETENESS", str(exc), CO.SCHEMA_CHANGED) from exc
    members.sort(key=lambda m: m["ticker"])
    return sealed({"schema": "US_OBSERVED_UNIVERSE_V1", "version": VERSION,
                   "sourceKind": response.source_kind, "source": response.source,
                   "sourceIdentity": response.source_identity, "sourceRawSha256": hashlib.sha256(response.raw).hexdigest(),
                   "sourceLastChangedAt": stamp(response.source_last_changed_at),
                   "observedAt": stamp(response.observed_at), "availableFrom": stamp(response.observed_at),
                   "observationUsCalendarDate": observed.astimezone(ZoneInfo("America/New_York")).date().isoformat(),
                   "effectiveMembershipDate": None, "memberCount": len(members), "members": members,
                   "pitCompleteHistoricalUniverse": False, "officialCompletenessVerified": False,
                   "qualityWarnings": ["SECONDARY_SOURCE_CURRENT_LIST_NOT_OFFICIAL_RECONCILIATION",
                                       "CIK_IS_ISSUER_ID_NOT_PERMANENT_SECURITY_ID",
                                       "NO_PRE_OBSERVATION_OR_EFFECTIVE_DATE_MEMBERSHIP_INFERENCE"]})


def target_members(snapshot, previous=None):
    """Never silently turn a missing old member into a verified departure."""
    old = {m["ticker"]: m for m in (previous or {}).get("members", [])}
    current = {m["ticker"]: m for m in snapshot["members"]}
    issues = []
    for ticker, member in current.items():
        prior = old.get(ticker)
        if prior and prior["issuerCik"] != member["issuerCik"]:
            issues.append({"ticker": ticker, "code": "TICKER_REUSED_DIFFERENT_CIK", "blocksPrice": True})
        elif prior and prior["issuerName"] != member["issuerName"]:
            issues.append({"ticker": ticker, "code": "NAME_CHANGE_IDENTITY_REVIEW_REQUIRED", "blocksPrice": True})
    for ticker in sorted(old.keys()-current.keys()):
        issues.append({"ticker": ticker, "code": "REMOVED_OR_MISSING_EFFECTIVE_DATE_UNVERIFIED", "blocksPrice": True})
        current[ticker] = old[ticker]
    for ticker in BENCHMARKS:
        current[ticker] = {"ticker": ticker, "securityId": f"BENCHMARK_INSTRUMENT:{ticker}",
                           "identityStatus": "INSTRUMENT_SYMBOL_NOT_PERMANENT_SECURITY_ID"}
    return [current[t] for t in sorted(current)], issues


def price_records(reply, member, snapshot, target_dates, now):
    """Restore prices only, using actions actually acquired by this observation."""
    recent = completed_sessions(now)
    if not target_dates or any(d not in recent for d in target_dates):
        raise Refused("UNBOUNDED_OR_INCOMPLETE_SESSION", "Only the latest seven completed US sessions may be requested")
    observed = utc(reply.observed_at)
    if observed < utc(snapshot["observedAt"]):
        raise Refused("PRICE_PRECEDES_MEMBERSHIP_OBSERVATION", "Price acquisition predates its query universe")
    if not timedelta(0) <= observed-utc(now) <= timedelta(hours=1):
        raise Refused("PRICE_ACQUISITION_OUTSIDE_RUN", "Source acquisition must belong to this bounded observation run")
    metadata = reply.metadata
    if (metadata.get("acquisitionOptions") != PRICE_OPTIONS or reply.source_version != "yfinance-0.2.65" or
            metadata.get("currency") != "USD" or metadata.get("exchangeTimezoneName") != "America/New_York" or
            _us_symbol(metadata.get("symbol", "")) != member["ticker"] or
            metadata.get("instrumentType") != ("ETF" if member["ticker"] in BENCHMARKS else "EQUITY")):
        raise Refused("PRICE_SOURCE_IDENTITY_OR_UNIT", "Vendor identity, currency or exchange timezone mismatch", CO.SCHEMA_CHANGED)
    frame = reply.frame
    if frame is None or frame.empty:
        raise Refused("EMPTY_OR_REFUSED_DOWNLOAD", "No valid daily bars; not evidence of a closed market")
    if frame.columns.duplicated().any() or not set(AS_TRADED_WITH_ACTIONS).issubset(frame.columns):
        raise Refused("MISSING_PRICE_OR_ACTION_COLUMNS", "Missing prices/actions must never become zero", CO.SCHEMA_CHANGED)
    index = pd.DatetimeIndex(frame.index)
    if index.tz is not None and str(index.tz) != "America/New_York":
        raise Refused("AMBIGUOUS_SESSION_TIMEZONE", "Daily labels must preserve the US exchange wall date", CO.SCHEMA_CHANGED)
    labels = normalize_daily_index(index)
    if labels.isna().any() or labels.duplicated().any() or any(t.hour or t.minute or t.second for t in index):
        raise Refused("INVALID_OR_DUPLICATE_SESSION_LABEL", "Invalid or duplicate daily labels", CO.SCHEMA_CHANGED)
    clean = frame.loc[:, AS_TRADED_WITH_ACTIONS].copy()
    clean.index = labels
    clean = clean.sort_index()
    expected = [d for d in recent if d >= min(target_dates)]
    actual = [d.strftime("%Y-%m-%d") for d in clean.index]
    if actual != expected:
        raise Refused("STALE_TRUNCATED_OR_FUTURE_DOWNLOAD", "Vendor window differs from the independently scheduled session grid")
    if any(d not in completed_sessions(reply.observed_at) for d in actual):
        raise Refused("OBSERVATION_BEFORE_SESSION_COMPLETION", "Bar acquisition precedes the completed-session grace bound")
    for _, row in clean.iterrows():
        values = list(row)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            raise Refused("INVALID_OR_MISSING_VALUE", "Nonfinite, missing or nonnumeric price/action value", CO.SCHEMA_CHANGED)
        o, h, low, close, volume, dividend, split = values
        if min(o, h, low, close) <= 0 or volume < 0 or dividend < 0 or split < 0 or low > min(o, close) or h < max(o, close) or low > h:
            raise Refused("INVALID_BAR_OR_ACTION", "Invalid OHLCV or corporate action", CO.SCHEMA_CHANGED)
    if "Capital Gains" in frame.columns:
        gains = frame["Capital Gains"].copy()
        gains.index = labels
        gains = gains.sort_index()
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in gains):
            raise Refused("INVALID_CAPITAL_GAINS", "Reported capital gains must be finite nonnegative values", CO.SCHEMA_CHANGED)
        clean["Capital Gains"] = list(gains)
    raw = [{"date": d.strftime("%Y-%m-%d"), **{c: float(v) for c, v in row.items()}}
           for d, row in clean.iterrows()]
    ratios = clean["Stock Splits"].where(clean["Stock Splits"] > 0, 1.0)
    factors = future_split_factor(ratios)
    if any(not math.isfinite(float(f)) or f <= 0 for f in factors):
        raise Refused("INVALID_SPLIT_PRODUCT", "Split products must be positive and finite", CO.SCHEMA_CHANGED)
    panel_digest = digest(raw)
    records = []
    for i, (date, row) in enumerate(clean.iterrows()):
        session = date.strftime("%Y-%m-%d")
        if session not in target_dates:
            continue
        factor = float(factors[i])
        core = {"date": session, "securityId": member["securityId"], "ticker": member["ticker"],
                "currency": "USD", "priceUnit": "USD_PER_SHARE", "volumeUnit": "SHARES",
                "dividendUnit": "USD_PER_SHARE", "priceBasis": PRICE_BASIS, "adjustmentVersion": ADJUSTMENT_VERSION,
                **{c: float(row[c])*factor for c in ("Open", "High", "Low", "Close")},
                "Volume": float(row["Volume"])/factor, "cashDividendAsTraded": float(row["Dividends"])*factor,
                "splitRatio": float(ratios.iloc[i]),
                "capitalGainsAsTraded": float(row["Capital Gains"])*factor if "Capital Gains" in clean else None,
                "capitalGainsStatus": "REPORTED" if "Capital Gains" in clean else "NOT_REPORTED"}
        if any(not math.isfinite(core[k]) for k in (*AS_TRADED_WITH_ACTIONS[:5], "cashDividendAsTraded", "splitRatio")) or (core["capitalGainsAsTraded"] is not None and not math.isfinite(core["capitalGainsAsTraded"])) or min(core[k] for k in ("Open", "High", "Low", "Close")) <= 0:
            raise Refused("UNRESTORABLE_AS_TRADED_VALUE", "Restored prices/volume/actions must be valid finite values", CO.SCHEMA_CHANGED)
        source_acquisition_id = digest([VERSION, member["securityId"], stamp(reply.observed_at),
                                        reply.source, reply.source_version, panel_digest, metadata])
        records.append(sealed({"schema": "US_DAILY_PRICE_OBSERVATION_V1", "version": VERSION,
                               "sourceKind": snapshot["sourceKind"], "id": digest([VERSION, session, member["securityId"]]),
                               "core": core, "coreDigest": digest(core), "availableFrom": stamp(reply.observed_at),
                               "acquiredAt": stamp(reply.observed_at), "source": reply.source,
                               "sourceVersion": reply.source_version, "sourceBasis": SOURCE_BASIS,
                               "sourcePanelDigest": panel_digest, "sourcePanel": raw, "sourceMetadata": metadata,
                               "sourceAcquisitionId": source_acquisition_id,
                               "splitFactorStrictlyAfterSession": factor, "universeSnapshotDigest": snapshot["digest"],
                               "identityStatus": member["identityStatus"],
                               "membershipApplicability": "OBSERVED_QUERY_SET_NOT_ASSERTED_SESSION_MEMBERSHIP",
                               "securityIdentityApplicability": "CURRENT_QUERY_IDENTITY_NOT_VERIFIED_BEFORE_CAPTURE",
                               "totalReturnComputed": False}))
    return records


class ObservationStore:
    """Immutable content-addressed daily chunks; mutable indexes are not trusted.

    Existing gzip bytes never change. A revision is evidence in quarantine,
    not an overwrite. An interrupted run resumes by scanning committed IDs.
    """
    def __init__(self, root, source_kind=LIVE):
        self.root = Path(root).resolve()
        if self.root.is_relative_to(ROOT):
            raise Refused("ISOLATED_OUTPUT_REQUIRED", "Use an output directory outside the repository checkout")
        if source_kind not in (LIVE, SYNTHETIC):
            raise Refused("UNKNOWN_SOURCE_KIND", "Explicit source kind required")
        for parent in (self.root, *self.root.parents):
            git = parent / ".git"
            # Managed environments reserve empty read-only .git directories
            # at /tmp and /workspace. A directory without HEAD is not a checkout.
            if git.is_file() or (git.is_dir() and (git / "HEAD").is_file()):
                raise Refused("GIT_DESTINATION_WRITE_FORBIDDEN", "Stage outside every Git checkout; never write directly to production signal-history")
        self.source_kind = source_kind
        namespace = VERSION + ("-fixtures" if source_kind == SYNTHETIC else "")
        self.prices = self.root / "prices/us" / namespace
        self.universe = self.root / "universe/us" / namespace

    def _safe(self, path):
        resolved = path.resolve()
        if not any(resolved.is_relative_to(p) for p in (self.prices, self.universe)):
            raise Refused("UNSAFE_STORE_PATH", "A symlink escapes the two isolated namespaces")
        return path

    @contextmanager
    def locked(self):
        self._safe(self.prices).mkdir(parents=True, exist_ok=True)
        with self._safe(self.prices / ".collection.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise Refused("CONCURRENT_COLLECTION", "Another collection owns this store") from exc
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _immutable(self, path, payload):
        self._safe(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != payload:
                raise Refused("IMMUTABLE_FILE_CONFLICT", f"Existing file differs: {path.name}")
            return False
        handle, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)  # Exclusive publication of complete bytes.
            except FileExistsError:
                if path.read_bytes() != payload:
                    raise Refused("IMMUTABLE_FILE_CONFLICT", "Concurrent file conflict") from None
                return False
        finally:
            temporary.unlink(missing_ok=True)
        return True

    def _chunk(self, folder, prefix, rows):
        if not rows:
            return None
        rows = [json.loads(canonical(r)) for r in sorted(rows, key=lambda r: r.get("id") or r["digest"])]
        payload = HS.encode(rows)
        if len(payload) > HS.MAX_SHARD_BYTES:
            raise Refused("CHUNK_TOO_LARGE", "Shard more finely; never exceed the existing blob ceiling")
        sha = hashlib.sha256(payload).hexdigest()
        path = folder / f"{prefix}-{sha}.jsonl.gz"
        self._immutable(path, payload)
        return str(path.relative_to(self.root))

    def _rows(self, folder, pattern):
        rows = []
        if not folder.exists():
            return rows
        for path in sorted(folder.glob(pattern)):
            self._safe(path)
            expected = path.name.removesuffix(".jsonl.gz").rsplit("-", 1)[-1]
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise Refused("STORE_DIGEST_MISMATCH", f"Corrupt chunk: {path.name}")
            try:
                decoded = list(HS.read_jsonl(path))
            except (ValueError, OSError, EOFError, UnicodeError) as exc:
                raise Refused("STORE_DECODE_ERROR", "Stored source chunk cannot be decoded") from exc
            for row in decoded:
                if (not isinstance(row, dict) or row.get("version") != VERSION or row.get("sourceKind") != self.source_kind or
                        row.get("digest") != digest({k: v for k, v in row.items() if k != "digest"})):
                    raise Refused("STORE_RECORD_MISMATCH", f"Invalid version, source kind or record digest: {path.name}")
                rows.append(row)
        return rows

    def snapshots(self):
        rows = self._rows(self.universe, "*/snapshot-*.jsonl.gz")
        for row in rows:
            source = self.universe / "sources" / (row["sourceRawSha256"] + ".csv")
            if not source.exists() or hashlib.sha256(self._safe(source).read_bytes()).hexdigest() != row["sourceRawSha256"]:
                raise Refused("MEMBERSHIP_SOURCE_MISSING_OR_CORRUPT", "Original source bytes cannot be verified")
        return rows

    def snapshot_at(self, asof):
        rows = [r for r in self.snapshots() if utc(r["availableFrom"]) <= utc(asof)]
        return max(rows, key=lambda r: (r["availableFrom"], r["digest"])) if rows else None

    def save_snapshot(self, snapshot, raw):
        known = self.snapshots()
        if snapshot["digest"] not in {r["digest"] for r in known} and known:
            latest = max(utc(r["observedAt"]) for r in known)
            if utc(snapshot["observedAt"]) <= latest:
                raise Refused("BACKDATED_OR_CONFLICTING_UNIVERSE_OBSERVATION", "A later insertion cannot rewrite an earlier observed universe")
        if hashlib.sha256(raw).hexdigest() != snapshot["sourceRawSha256"]:
            raise Refused("SOURCE_BYTES_MISMATCH", "Membership bytes differ from registered digest")
        self._immutable(self.universe / "sources" / (snapshot["sourceRawSha256"] + ".csv"), raw)
        return self._chunk(self.universe / snapshot["observedAt"][:7], "snapshot-"+snapshot["digest"], [snapshot])

    def observations(self, dates=None):
        patterns = ["*/observations-*.jsonl.gz"] if dates is None else [f"{d[:7]}/observations-{d}-*.jsonl.gz" for d in sorted(set(dates))]
        rows = [r for pattern in patterns for r in self._rows(self.prices, pattern)]
        known_snapshots = set()
        for sha in {r["universeSnapshotDigest"] for r in rows}:
            matches = self._rows(self.universe, "*/snapshot-"+sha+"-*.jsonl.gz")
            if len(matches) != 1 or matches[0]["digest"] != sha:
                raise Refused("PRICE_UNIVERSE_REFERENCE_MISSING", "Referenced universe observation is missing or duplicated")
            snapshot = matches[0]
            source = self.universe / "sources" / (snapshot["sourceRawSha256"]+".csv")
            if not source.exists() or hashlib.sha256(self._safe(source).read_bytes()).hexdigest() != snapshot["sourceRawSha256"]:
                raise Refused("MEMBERSHIP_SOURCE_MISSING_OR_CORRUPT", "Referenced original source cannot be verified")
            known_snapshots.add(sha)
        acquisitions = {}
        for day in {r["acquiredAt"][:10] for r in rows}:
            for acquisition in self._rows(self.prices / "source-acquisitions" / day[:7], "source-"+day+"-*.jsonl.gz"):
                if acquisition["id"] in acquisitions:
                    raise Refused("DUPLICATE_SOURCE_ACQUISITION", "Duplicate committed source evidence")
                acquisitions[acquisition["id"]] = acquisition
        identities = {}
        for row in rows:
            acquisition = acquisitions.get(row["sourceAcquisitionId"])
            if (not acquisition or acquisition["sourcePanelDigest"] != digest(acquisition["sourcePanel"]) or
                    acquisition["id"] != digest([VERSION, acquisition["securityId"], acquisition["availableFrom"],
                                                 acquisition["source"], acquisition["sourceVersion"],
                                                 acquisition["sourcePanelDigest"], acquisition["sourceMetadata"]]) or
                    acquisition["sourcePanelDigest"] != row["sourcePanelDigest"] or
                    acquisition["sourceMetadata"] != row["sourceMetadata"] or
                    acquisition["securityId"] != row["core"]["securityId"] or
                    acquisition["availableFrom"] != row["availableFrom"]):
                raise Refused("PRICE_ACQUISITION_MISSING_OR_INVALID", "Original acquisition evidence cannot be verified")
            core = row["core"]
            if (row["coreDigest"] != digest(core) or row["sourcePanelDigest"] != digest(row["sourcePanel"]) or
                    row["universeSnapshotDigest"] not in known_snapshots or
                    row["id"] != digest([VERSION, core["date"], core["securityId"]])):
                raise Refused("PRICE_PROVENANCE_INVALID", "Invalid economic core, source panel or universe reference")
            if row["id"] in identities:
                raise Refused("DUPLICATE_COMMITTED_ID", "A price observation must have one original record")
            identities[row["id"]] = row
        return identities

    def append_prices(self, rows):
        existing = self.observations({r["core"]["date"] for r in rows})
        self.save_acquisitions(rows)
        fresh, revisions, repeated = [], [], 0
        for row in rows:
            prior = existing.get(row["id"])
            if prior:
                if row["coreDigest"] == prior["coreDigest"]:
                    repeated += 1
                    continue
                if utc(row["availableFrom"]) <= utc(prior["availableFrom"]):
                    raise Refused("BACKDATED_PRICE_REVISION", "A correction must be a later source observation")
                revisions.append(sealed({"schema": "US_DAILY_PRICE_REVISION_QUARANTINE_V1",
                                         "version": VERSION, "sourceKind": self.source_kind,
                                         "id": row["id"], "originalDigest": prior["digest"],
                                         "availableFrom": row["availableFrom"], "candidate": row,
                                         "reason": "SOURCE_REVISION_REQUIRES_EXPLICIT_REVIEW"}))
            else:
                fresh.append(row)
                existing[row["id"]] = row
        written = []
        for date in sorted({r["core"]["date"] for r in fresh}):
            written.append(self._chunk(self.prices / date[:7], "observations-"+date,
                                       [r for r in fresh if r["core"]["date"] == date]))
        if revisions:
            written.append(self._chunk(self.prices / "quarantine", "revision", revisions))
        return {"appended": len(fresh), "repeated": repeated, "conflicts": len(revisions), "files": written}

    def save_acquisitions(self, rows):
        # Even split-driven vendor changes with an unchanged as-traded core
        # retain new acquisition evidence. Do not confuse a source frame with
        # a new logical daily price, and do not discard its provenance.
        observations = {}
        for row in rows:
            identity = row["sourceAcquisitionId"]
            observations[identity] = sealed({"schema": "US_PRICE_SOURCE_ACQUISITION_V1", "version": VERSION,
                                            "sourceKind": self.source_kind, "id": identity,
                                            "securityId": row["core"]["securityId"],
                                            "availableFrom": row["availableFrom"], "source": row["source"],
                                            "sourceVersion": row["sourceVersion"], "sourceBasis": row["sourceBasis"],
                                            "sourcePanelDigest": row["sourcePanelDigest"],
                                            "sourcePanel": row["sourcePanel"], "sourceMetadata": row["sourceMetadata"]})
        for day in sorted({r["availableFrom"][:10] for r in observations.values()}):
            folder = self.prices / "source-acquisitions" / day[:7]
            prior = {r["id"] for r in self._rows(folder, "source-"+day+"-*.jsonl.gz")}
            fresh = [r for r in observations.values() if r["availableFrom"][:10] == day and r["id"] not in prior]
            self._chunk(folder, "source-"+day, fresh)

    def prices_at(self, asof):
        """Later acquisition/correction cannot change an earlier information set."""
        at = utc(asof)
        originals = {k: r for k, r in self.observations().items() if utc(r["availableFrom"]) <= at}
        conflicts = {r["id"] for r in self._rows(self.prices / "quarantine", "revision-*.jsonl.gz")
                     if utc(r["availableFrom"]) <= at}
        return {k: {"status": "REVISION_CONFLICT" if k in conflicts else "OBSERVED",
                    "record": None if k in conflicts else r} for k, r in sorted(originals.items())}

    def manifests(self):
        rows = self._rows(self.prices / "manifests", "run-*.jsonl.gz")
        for row in rows:
            for relative in row.get("writtenChunks", []):
                path = self._safe(self.root / relative)
                if not path.is_file():
                    raise Refused("COMMITTED_CHUNK_MISSING", "A manifest's committed chunk is missing")
                self._rows(path.parent, path.name)
        return rows

    def save_manifest(self, manifest):
        return self._chunk(self.prices / "manifests", "run", [sealed(manifest)])


def collect(root, membership_response, fetch_price, *, now, target_dates=None, max_calls=600, max_seconds=900, batch_size=40, recheck=False):
    """Injectable, bounded collector. Commit partial progress before any interruption.

    Benchmark refusal is a preflight stop, not 503 more requests to a known
    unavailable provider. An existing price is skipped on resume unless recheck
    is explicitly requested. No current list is back-applied as membership.
    """
    store = ObservationStore(root, membership_response.source_kind)
    with store.locked():
        return _collect_locked(store, membership_response, fetch_price, now=now,
                               target_dates=target_dates, max_calls=max_calls, max_seconds=max_seconds, batch_size=batch_size, recheck=recheck)


def _collect_locked(store, response, fetch_price, *, now, target_dates, max_calls, max_seconds, batch_size, recheck):
    recent = completed_sessions(now)
    target_dates = sorted(set(target_dates or recent[-1:]))
    if not target_dates or any(d not in recent for d in target_dates) or max_calls < 1 or batch_size < 1 or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise Refused("INVALID_COLLECTION_SCOPE", "Explicit bounded completed sessions and positive budgets required")
    snapshot = membership_snapshot(response, now)
    previous = store.snapshot_at(snapshot["observedAt"])
    targets, issues = target_members(snapshot, previous)
    old_runs = store.manifests()
    # An unresolved disappearance or reused symbol cannot clear merely because
    # the next source capture repeats the new list. v1 deliberately has no
    # implicit resolution; a verified, versioned review is a separate change.
    prior_runs = [r for r in old_runs if r.get("requestedInstruments") and
                  utc(r["availableFrom"]) <= utc(snapshot["observedAt"])]
    if prior_runs:
        prior_run = max(prior_runs, key=lambda r: (utc(r["availableFrom"]), r["digest"]))
        by_ticker = {m["ticker"]: m for m in targets}
        for issue in prior_run.get("identityIssues", []):
            if issue["blocksPrice"] and issue not in issues:
                issues.append(issue)
            ticker = issue["ticker"]
            if ticker not in by_ticker:
                by_ticker[ticker] = next(m for m in prior_run["requestedInstruments"] if m["ticker"] == ticker)
        targets = [by_ticker[t] for t in sorted(by_ticker)]
    issues.sort(key=lambda i: (i["ticker"], i["code"]))
    store.save_snapshot(snapshot, response.raw)
    existing = store.observations(target_dates)
    run_id = digest([VERSION, snapshot["digest"], target_dates, max_calls, max_seconds, batch_size, recheck])
    active_revisions = [r for r in store._rows(store.prices / "quarantine", "revision-*.jsonl.gz")
                        if utc(r["availableFrom"]) <= utc(now)]
    expected_ids = {digest([VERSION, d, m["securityId"]]) for d in target_dates for m in targets}
    if expected_ids.issubset(existing) and not issues and not any(r["id"] in expected_ids for r in active_revisions):
        completed = [r for r in old_runs if r.get("runId") == run_id and r.get("collectionComplete")]
        if completed:
            return {k: v for k, v in completed[0].items() if k != "digest"}
    buffer, failures, files = [], [], []
    calls, appended, repeated, conflicts = 0, 0, 0, 0
    interrupted = False
    observed_watermark = stamp(now)
    budget_stop = None
    started = time.monotonic()
    blocked = {i["ticker"]: i["code"] for i in issues if i["blocksPrice"]}
    expected = {digest([VERSION, date, m["securityId"]]): (date, m["ticker"]) for m in targets for date in target_dates}

    def flush():
        nonlocal appended, repeated, conflicts
        if buffer:
            result = store.append_prices(buffer)
            appended += result["appended"]
            repeated += result["repeated"]
            conflicts += result["conflicts"]
            files.extend(result["files"])
            buffer.clear()

    ordered = sorted(targets, key=lambda m: (m["ticker"] not in BENCHMARKS, m["ticker"]))
    try:
        benchmark_failed = False
        for member in ordered:
            ticker = member["ticker"]
            if ticker not in BENCHMARKS and benchmark_failed:
                break
            if ticker in blocked:
                failures.append({"ticker": ticker, "outcome": CO.BLOCKED_SOURCE, "code": blocked[ticker]})
                continue
            if not recheck and all(digest([VERSION, d, member["securityId"]]) in existing for d in target_dates):
                continue
            if calls >= max_calls or time.monotonic()-started >= max_seconds:
                budget_stop = "CALL_BUDGET_SPENT" if calls >= max_calls else "TIME_BUDGET_SPENT"
                break
            calls += 1
            try:
                reply = fetch_price(ticker, min(target_dates), recent[-1])
                observed_watermark = max(observed_watermark, stamp(reply.observed_at))
                buffer.extend(price_records(reply, member, snapshot, target_dates, now))
                if len(buffer) >= batch_size:
                    flush()
            except Refused as exc:
                failures.append({"ticker": ticker, "outcome": exc.outcome, "code": exc.code, "sourceMessage": str(exc)})
                benchmark_failed |= ticker in BENCHMARKS
    except BaseException:
        interrupted = True
        raise
    finally:
        flush()
        stored = store.observations(target_dates)
        missing = [{"date": d, "ticker": t} for key, (d, t) in sorted(expected.items()) if key not in stored]
        missing_benchmarks = [r for r in missing if r["ticker"] in BENCHMARKS]
        active_ids = {r["id"] for r in store._rows(store.prices / "quarantine", "revision-*.jsonl.gz")
                      if utc(r["availableFrom"]) <= utc(observed_watermark)} & set(expected)
        status = "INTERRUPTED" if interrupted else ("REVISION_CONFLICT" if active_ids else "IDENTITY_BLOCKED" if blocked else "PARTIAL" if missing else "COMPLETE")
        manifest = {"schema": "US_DAILY_COLLECTION_MANIFEST_V1", "version": VERSION, "sourceKind": store.source_kind,
                    "runId": run_id, "plannedAt": stamp(now), "sourceObservationAt": snapshot["observedAt"], "targetSessions": target_dates,
                    "availableFrom": max([observed_watermark, snapshot["observedAt"]]+[r["availableFrom"] for k, r in stored.items() if k in expected]),
                    "universeSnapshotDigest": snapshot["digest"], "sourceRawSha256": snapshot["sourceRawSha256"],
                    "status": status, "collectionComplete": status == "COMPLETE" and not blocked,
                    "pitCompleteHistoricalUniverse": False, "sourceOfficialCompletenessVerified": False,
                    "calendarVersion": CALENDAR_VERSION, "calendar": "XNYS", "closeGraceMinutes": CLOSE_GRACE_MINUTES,
                    "calls": calls, "appended": appended, "repeated": repeated, "conflicts": conflicts,
                    "activeRevisionConflicts": len(active_ids),
                    "expectedConstituentSecurityCount": len(snapshot["members"]),
                    "observedIssuerCikCount": len({m["issuerCik"] for m in snapshot["members"]}), "expectedRecordCount": len(expected),
                    "missing": missing, "missingBenchmarks": missing_benchmarks, "sourceFailures": failures,
                    "identityIssues": issues, "requestedInstruments": targets, "writtenChunks": sorted(set(files)),
                    "priceBasis": PRICE_BASIS, "totalReturnComputed": False,
                    "qualityWarnings": snapshot["qualityWarnings"], "recheckRequested": recheck,
                    "stopReason": "INTERRUPTED" if interrupted else "SOURCE_REFUSAL" if failures else budget_stop or "WORK_LIST_EXHAUSTED"}
        store.save_manifest(manifest)
    return manifest
