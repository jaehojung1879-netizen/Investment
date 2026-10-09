"""kr-alpha-atlas Phase B — input loading with identities. No feature is computed and no label, forward price or outcome is read here.

TWO ROUTES TO THE SAME OBJECT.
  * `load_inputs(commit, root)` with an empty `root` materialises the inputs the sealed studies pinned (`kr-model-overlay-portfolio-v1`: accounting blobs, universe
    blobs, replay-v16 manifest and price objects — every one verified by git blob hash or content hash by the sealed `kr_model_raw_snapshot`
    code) and adds the two stores that study did not pin: the KRX bar ledger (`ledger/prices/kr`, as-traded OHLCV + listed shares) and the DART
    share counts. Every file read gets its git blob SHA-1 recorded in `identity`, so a later run can prove it read the same bytes.
  * the same call with `root` = the preserved raw-input artifact (authorised Actions route) also finds the official KRX daily market values
    (`market/`), which hold the authoritative `ACC_TRDVAL`, and uses them. Both go through the sealed `X.load_sources` unchanged.

THE KRX MARKET-VALUE FILES ARE NOT IN GIT. `kr_market_value` caches them under `market/` in an Actions artifact only. Without them traded value is
the as-traded close x volume proxy and the loader says so (`tradingValueBasis`). The proxy is exact in shares and in the as-traded close; it differs
from the official figure by the gap between the closing price and the session's volume-weighted price. That gap is not measured here.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import subprocess

import pandas as pd

from . import historical_store as HS
from . import kr_alpha_atlas_bars as B
from . import kr_alpha_tournament as T
from . import kr_industry_anatomy_execution as IE
from . import kr_model_portfolio_execution as X
from . import kr_model_raw_snapshot as K
from . import kr_repaired_accounting_snapshot as AS
from . import krx_prices as KP
from . import replay_calendar as RC
from .kr_continuing_dividend_sample import is_likely_common_share

CONTRACT = "KR_ALPHA_ATLAS_INPUTS_V1"
ROOT = Path(__file__).resolve().parents[1]
PRICE_LEDGER = "ledger/prices/kr"
SHARES_PATH = "ledger/fundamentals/kr/shares.jsonl.gz"
BENCHMARK = T.BENCHMARK


def git_blob(repo, commit, path):
    return subprocess.check_output(["git", "cat-file", "blob", f"{commit}:{path}"], cwd=repo)


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def digest(obj):
    return hashlib.sha256(_canonical(obj)).hexdigest()


class MatrixInputs:
    """Everything `kr_alpha_atlas_matrix.build_matrix` reads. Plain attributes so a test can hand it synthetic data."""

    def __init__(self, **kw):
        self.accounting = kw.get("accounting", {})          # ticker -> [filing record]   (DART, receipt-dated)
        self.shares = kw.get("shares", {})                  # ticker -> {(year, code): shares}  (DART, net of treasury)
        self.memberships = kw["memberships"]                # MembershipSnapshots (PIT Top120, source snapshot strictly older than the signal date)
        self.universe_rows = kw.get("universe_rows", {})    # snapshot date -> [row]  (rank, marketCap, name)
        self.prices = kw.get("prices", {})                  # ticker -> replay-v16 frame (Close, High, Low, Open, Volume; split-continuous total-return)
        self.bars = kw.get("bars", {})                      # ticker -> TickerBars
        self.industry = kw.get("industry")                  # (intervals, crosswalk, ends) from the sealed v4 foundation
        self.calendar = kw["calendar"] if kw.get("calendar") is not None else RC.sessions("2013-01-01", "2028-12-31", "KR")
        self.names = kw.get("names", {})                    # ticker -> latest recorded name
        self.market = kw.get("market")                      # official KRX market-value store, or None
        self.identity = kw.get("identity", {})
        self.trading_value_basis = kw.get("trading_value_basis", B.TRADING_VALUE_BASIS_PROXY)

    def is_preferred(self, ticker):
        name = self.names.get(ticker)
        return None if name is None else not is_likely_common_share(name)


def _bar_frames(rows_by_ticker, calendar, tickers, official=None):
    bars = {}
    for ticker in sorted(tickers):
        rows = rows_by_ticker.get(ticker)
        frame = KP.frame_from_rows(rows, traded_only=False) if rows else pd.DataFrame()
        trading_value = official(ticker) if official else None
        bars[ticker] = B.TickerBars(ticker, frame if len(frame) else None, calendar, trading_value)
    return bars


def official_trading_value(market):
    """ticker -> Series of KRX `ACC_TRDVAL`, from the sealed `MarketValueStore`. None for a ticker the store never saw."""
    by_ticker = {}
    for (date, ticker), row in market.rows.items():
        by_ticker.setdefault(ticker, {})[pd.Timestamp(date)] = row["tradingValue"]
    return lambda t: pd.Series(by_ticker[t]).sort_index() if t in by_ticker else None


def _shares_by_ticker(records):
    out = {}
    for r in records:
        value = r.get("sharesOutstanding")
        if value and value > 0:
            out.setdefault(r["ticker"], {})[(int(r["fiscalYear"]), str(r["reportCode"]))] = float(value)
    return out


def load_inputs(commit, root, repo=ROOT):
    """Materialise and verify the pinned inputs under `root` (idempotent: `immutable_bytes` refuses a byte that differs), then read the bar ledger
    and share counts at `commit`. If `root` is the preserved raw-input artifact, `market/` is present and the official `ACC_TRDVAL` is used."""
    spec = K.frozen_spec()
    root = Path(root)
    pinned = spec["inputs"]["universeSourceCommit"]
    if commit != pinned:
        raise ValueError("COMMIT_IS_NOT_THE_PINNED_SOURCE_COMMIT: " + commit)
    members = K.materialize_universe(root, spec, repo)
    K.materialize_inherited(root, spec, repo)
    accounting, memberships, market, prices = X.load_sources(root, spec)
    calendar = RC.sessions("2013-01-01", "2028-12-31", "KR")
    blobs, rows_by_ticker = {}, {}
    ever = set(members) | {t for s in memberships.snapshots for t in s["members"]}
    for year in range(2013, 2027):
        path = f"{PRICE_LEDGER}/krx-prices-{year}.jsonl.gz"
        raw = git_blob(repo, commit, path)
        blobs[path] = AS.git_blob_sha1(raw)
        for line in gzip.decompress(raw).decode().splitlines():
            row = json.loads(line)
            if row["ticker"] in ever:
                rows_by_ticker.setdefault(row["ticker"], []).append(row)
    raw_shares = git_blob(repo, commit, SHARES_PATH)
    shares = _shares_by_ticker([json.loads(line) for line in gzip.decompress(raw_shares).decode().splitlines()])
    universe_rows, names = {}, {}
    for path in sorted((root / "ledger/universe/kr").glob("krx-universe-*.jsonl.gz")):
        for row in HS.read_jsonl(path):
            universe_rows.setdefault(row["date"], []).append({k: row.get(k) for k in ("ticker", "rank", "marketCap", "name")})
            names[row["ticker"]] = row.get("name") or names.get(row["ticker"])
    official = official_trading_value(market) if market.rows else None
    identity = {
        "contract": CONTRACT, "sourceCommit": commit, "frozenSpecSha256": K.SPEC_SHA,
        "accountingContentSha256": spec["inputs"]["accounting"]["contentSha256"], "accountingBlobSha1": spec["inputs"]["accounting"]["gitBlobSha1"],
        "universeBlobSha1": spec["inputs"]["universeBlobs"], "replayManifestSha256": spec["inputs"]["replayManifestSha256"],
        "barLedgerBlobSha1": dict(sorted(blobs.items())), "dartSharesBlobSha1": AS.git_blob_sha1(raw_shares),
        "industryFoundation": industry_identity(), "calendarVersion": RC.CALENDAR_VERSION,
        "marketValueStore": market.identity() if market.rows else "ABSENT_NOT_IN_GIT"}
    identity["sha256"] = digest(identity)
    return MatrixInputs(accounting=accounting, shares=shares, memberships=memberships, universe_rows=universe_rows, prices=prices,
                        bars=_bar_frames(rows_by_ticker, calendar, ever, official), industry=IE.load_membership_inputs(ROOT), calendar=calendar,
                        names=names, market=market if market.rows else None, identity=identity,
                        trading_value_basis=B.TRADING_VALUE_BASIS_OFFICIAL if official else B.TRADING_VALUE_BASIS_PROXY)


def industry_identity():
    files = {}
    for rel in (IE.V4 + "/state/intervals.json.gz", "research_specs/kr-industry-membership-foundation-v4/crosswalk.json",
                "data/kr-industry-membership-foundation-v1/identity-inventory.json", "data/kr-industry-membership-foundation-v1/identity-provenance.json"):
        files[rel] = AS.git_blob_sha1((ROOT / rel).read_bytes())
    return files
