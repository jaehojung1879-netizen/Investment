"""Historical point-in-time replay — living the past one day at a time.

The premise, stated plainly because it is easy to get backwards:

    Refusing to use the past is not honesty. Refusing to look at the future
    while you are standing in the past is honesty.

So this engine walks a date grid from (say) 2013 to today and, on each date T,
runs the ranking model against **only** what was visible on T, then freezes the
result. The frozen record is never revisited when the model changes; a new model
produces new records under a new ``replayVersion``, and the old ones stay
exactly as they were.

WHY THE REPLAY IS THE SAME MODEL, NOT A LOOKALIKE
-------------------------------------------------
The factor definitions live in ``pipeline.longterm``. This module builds the
per-name raw input row and hands it to ``longterm.score_cross_section`` — the
identical function production calls. Entry state comes from ``pipeline.entry``,
regime from ``pipeline.regime`` (whose fixed release lags already prevent the
crudest macro leak). Nothing about the scoring is re-implemented here, because a
second copy of the alpha formula would drift and the replay would be validating
a model nobody runs.

WHY PRECOMPUTATION IS SAFE
--------------------------
Naively, "run the model as of T" means truncate every series at T and recompute.
That is O(dates x tickers x window) of pandas slicing and is far too slow for a
decade of daily dates. Instead each ticker's history is converted once into
NumPy arrays, and every metric is computed from the trailing window ending at
T's position. This is *arithmetically identical* to truncate-then-compute
because every metric here is backward-looking only — there is no ``shift(-n)``,
no ``cummax`` over future rows, no full-sample mean. ``tests/test_replay.py``
pins that equivalence against the pandas production functions rather than
leaving it as a claim.

WHAT IS DELIBERATELY MISSING
----------------------------
``shortTermModelScore`` is null in replays. Refitting the LightGBM ensemble per
ticker per date is thousands of CPU-hours, and fitting it once on the full
sample would be exactly the leak this module exists to prevent. Null with a
stated reason beats a number whose provenance we would have to apologise for.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import entry as entry_mod
from . import longterm as longterm_mod
from . import pit_data
from . import regime as regime_mod
from . import sectors as SECT
from .market_dates import normalize_daily_frame

# Bumped whenever the replay's own logic changes shape. Records carry it so two
# generations of replay never pool into one evidence base.
REPLAY_VERSION = "replay-v4"
FEATURE_VERSION = "hfeat-v1"
DATA_VERSION = "yahoo-adjusted-close-v3-regional-session-download"

EVIDENCE_HISTORICAL = "HISTORICAL_OOS"

# Minimum trailing rows before a name can be ranked at all (12-1 momentum needs
# 273). Also the guard that stops a freshly listed name from being scored.
MIN_HISTORY_ROWS = longterm_mod.MIN_HISTORY
# A close more than this many calendar days old is stale (halt, delisting, or a
# vendor gap); the name is dropped from that date's cross-section rather than
# ranked off a price nobody could trade.
MAX_STALE_CALENDAR_DAYS = 10

# Source weights for the PIT coverage score, chosen by how much of the decision
# each source drives. Prices dominate: momentum and lowvol are half the sleeve
# weight, and every risk metric and the entire entry layer is price-derived.
# Universe keeps a meaningful share of its own because survivorship bias
# contaminates every observation regardless of which sleeves fired.
#
# Sources that contributed nothing are dropped from the denominator rather than
# scored zero — see ``pit_data.coverage_score`` for why that is the honest
# treatment and where the missing-sleeve penalty is actually charged.
PIT_SOURCE_WEIGHTS_WITH_FUNDAMENTALS = {"price": 0.55, "fundamentals": 0.30,
                                        "universe": 0.15, "macro": 0.05}
PIT_SOURCE_WEIGHTS_PRICE_ONLY = {"price": 0.85, "universe": 0.15, "macro": 0.05}

SECTOR_ROTATION_STATES = ("IMPROVING", "STABLE", "DETERIORATING", "UNKNOWN")


# --------------------------------------------------------------------------- #
# NumPy price panel
# --------------------------------------------------------------------------- #
@dataclass
class TickerHistory:
    """One ticker's history as position-indexed NumPy arrays."""

    ticker: str
    dates: np.ndarray          # datetime64[ns], strictly increasing
    close: np.ndarray
    open_: np.ndarray
    volume: np.ndarray
    returns: np.ndarray        # close.pct_change(), returns[0] = nan

    def position(self, as_of: np.datetime64) -> int:
        """Index of the last row at or before ``as_of`` (-1 if none)."""
        return int(np.searchsorted(self.dates, as_of, side="right")) - 1


def _to_history(ticker: str, frame: pd.DataFrame) -> TickerHistory | None:
    if frame is None or "Close" not in frame:
        return None
    data = frame[[c for c in ("Close", "Open", "Volume") if c in frame.columns]].copy()
    data = data.apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=["Close"])
    if data.empty:
        return None
    data = normalize_daily_frame(data)
    close = data["Close"].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = np.empty_like(close)
        returns[0] = np.nan
        returns[1:] = np.where(close[:-1] > 0, close[1:] / close[:-1] - 1.0, np.nan)
    open_ = (data["Open"].to_numpy(dtype=float) if "Open" in data
             else np.full_like(close, np.nan))
    volume = (data["Volume"].to_numpy(dtype=float) if "Volume" in data
              else np.full_like(close, np.nan))
    return TickerHistory(ticker, data.index.to_numpy(dtype="datetime64[ns]"),
                         close, open_, volume, returns)


class PricePanel:
    """All tickers' histories, converted once, sliced cheaply per replay date."""

    def __init__(self, prices: dict[str, pd.DataFrame]):
        self._histories: dict[str, TickerHistory] = {}
        for ticker, frame in (prices or {}).items():
            history = _to_history(ticker, frame)
            if history is not None:
                self._histories[ticker] = history

    def __contains__(self, ticker: str) -> bool:
        return ticker in self._histories

    def tickers(self) -> list[str]:
        return sorted(self._histories)

    def get(self, ticker: str) -> TickerHistory | None:
        return self._histories.get(ticker)

    def membership_view(self, as_of) -> "_PanelMembershipView":
        return _PanelMembershipView(self, as_of)

    def trading_days(self, tickers: list[str] | None = None) -> pd.DatetimeIndex:
        names = tickers if tickers is not None else self.tickers()
        stamps: set = set()
        for ticker in names:
            history = self._histories.get(ticker)
            if history is not None:
                stamps.update(history.dates.tolist())
        return pd.DatetimeIndex(sorted(stamps))


class _PanelMembershipView:
    """``has_history``-only probe used by ``UniverseHistory.snapshot``.

    Boolean-masking every price frame once per replay date is the single most
    expensive thing a naive implementation does. A binary search over the
    already-sorted date array answers the same question in microseconds.
    """

    def __init__(self, panel: PricePanel, as_of):
        self._panel = panel
        self._as_of = np.datetime64(pd.Timestamp(as_of).normalize(), "ns")

    def has_history(self, ticker: str, min_rows: int = 1) -> bool:
        history = self._panel.get(ticker)
        if history is None:
            return False
        return history.position(self._as_of) + 1 >= max(1, int(min_rows))


# --------------------------------------------------------------------------- #
# Backward-only metrics on a trailing window
# --------------------------------------------------------------------------- #
def _tail(arr: np.ndarray, end: int, size: int) -> np.ndarray:
    """The ``size`` values ending at position ``end`` inclusive."""
    start = max(0, end + 1 - size)
    return arr[start:end + 1]


def _ratio(numer: float, denom: float) -> float | None:
    if not np.isfinite(numer) or not np.isfinite(denom) or denom == 0:
        return None
    return float(numer / denom - 1.0)


def momentum_12_1(h: TickerHistory, pos: int) -> float | None:
    """12-month momentum skipping the last month — matches longterm.momentum_12_1."""
    if pos + 1 < longterm_mod.MIN_HISTORY:
        return None
    return _ratio(h.close[pos - 20], h.close[pos - 251])


def momentum_6m(h: TickerHistory, pos: int) -> float | None:
    if pos + 1 < 126:
        return None
    return _ratio(h.close[pos], h.close[pos - 125])


def momentum_days(h: TickerHistory, pos: int, days: int) -> float | None:
    if pos - days < 0:
        return None
    return _ratio(h.close[pos], h.close[pos - days])


def realized_vol_252(h: TickerHistory, pos: int) -> float | None:
    r = _tail(h.returns, pos, 252)
    r = r[np.isfinite(r)]
    if len(r) < 60:
        return None
    return float(np.std(r, ddof=1) * math.sqrt(252))


def downside_vol_252(h: TickerHistory, pos: int) -> float | None:
    r = _tail(h.returns, pos, 252)
    r = r[np.isfinite(r)]
    neg = r[r < 0]
    if len(neg) < 20:
        return None
    return float(math.sqrt(float(np.mean(neg ** 2))) * math.sqrt(252))


def cvar_95(h: TickerHistory, pos: int) -> float | None:
    r = _tail(h.returns, pos, 252)
    r = r[np.isfinite(r)]
    if len(r) < 60:
        return None
    var = float(np.quantile(r, 0.05))
    tail = r[r <= var]
    if not len(tail):
        return None
    return float(-tail.mean() * 100)


def max_drawdown_252(h: TickerHistory, pos: int) -> float | None:
    sample = _tail(h.close, pos, 252)
    sample = sample[np.isfinite(sample)]
    if not len(sample):
        return None
    peak = np.maximum.accumulate(sample)
    return float(np.min((sample - peak) / peak) * 100)


def moving_average(h: TickerHistory, pos: int, window: int) -> float | None:
    sample = _tail(h.close, pos, window)
    if len(sample) < window:
        return None
    return float(np.mean(sample))


def rsi_14(h: TickerHistory, pos: int) -> float | None:
    """Simple-moving-average RSI, matching pipeline.features._rsi."""
    delta = np.diff(_tail(h.close, pos, 16))
    if len(delta) < 14:
        return None
    window = delta[-14:]
    gain = float(np.mean(np.where(window > 0, window, 0.0)))
    loss = float(np.mean(np.where(window < 0, -window, 0.0)))
    if loss == 0:
        # 0/0 is undefined in the pandas original too; only an all-gain window
        # is genuinely RSI 100.
        return 100.0 if gain > 0 else None
    rs = gain / loss
    return float(100.0 - 100.0 / (1.0 + rs))


def volatility_window(h: TickerHistory, pos: int, window: int) -> float | None:
    r = _tail(h.returns, pos, window)
    r = r[np.isfinite(r)]
    if len(r) < window:
        return None
    return float(np.std(r, ddof=1) * math.sqrt(252))


def volume_surge(h: TickerHistory, pos: int) -> float | None:
    """5-day average volume against the 60-day average — build.volume_surge."""
    vol = _tail(h.volume, pos, 60)
    vol = vol[np.isfinite(vol)]
    if len(vol) < 60:
        return None
    base = float(np.mean(vol))
    if base <= 0:
        return None
    return round(float(np.mean(vol[-5:]) / base), 2)


def beta_to(h: TickerHistory, pos: int, bench: TickerHistory | None) -> float | None:
    """Beta on the last 252 overlapping sessions, aligned by date."""
    if bench is None:
        return None
    bench_pos = bench.position(h.dates[pos])
    if bench_pos < 0:
        return None
    stock_dates = _tail(h.dates, pos, 300)
    stock_ret = _tail(h.returns, pos, 300)
    bench_dates = _tail(bench.dates, bench_pos, 300)
    bench_ret = _tail(bench.returns, bench_pos, 300)
    common, si, bi = np.intersect1d(stock_dates, bench_dates, return_indices=True)
    if len(common) < 61:
        return None
    a, b = stock_ret[si][-252:], bench_ret[bi][-252:]
    mask = np.isfinite(a) & np.isfinite(b)
    a, b = a[mask], b[mask]
    if len(a) < 60:
        return None
    var_b = float(np.var(b, ddof=1))
    if var_b == 0:
        return None
    return float(np.cov(a, b, ddof=1)[0, 1] / var_b)


def relative_momentum(h: TickerHistory, pos: int, bench: TickerHistory | None,
                      days: int = 20) -> float | None:
    """Change in the stock/benchmark ratio — matches features.rel_momentum."""
    if bench is None or pos - days < 0:
        return None
    bench_now = bench.position(h.dates[pos])
    bench_then = bench.position(h.dates[pos - days])
    if bench_now < 0 or bench_then < 0:
        return None
    now = _ratio(h.close[pos] * bench.close[bench_then], bench.close[bench_now] * h.close[pos - days])
    return now


# --------------------------------------------------------------------------- #
# Entry features from the NumPy panel
# --------------------------------------------------------------------------- #
def entry_features(h: TickerHistory, pos: int, surge: float | None) -> dict:
    """Entry-layer inputs, mirroring ``pipeline.entry.entry_features``."""
    last = float(h.close[pos])
    ma20 = moving_average(h, pos, 20)
    ma50 = moving_average(h, pos, 50)
    ma200 = moving_average(h, pos, 200)
    rsi = rsi_14(h, pos)
    vol20 = volatility_window(h, pos, 20)
    vol60 = volatility_window(h, pos, 60)
    mom63 = momentum_days(h, pos, 60)

    recent = _tail(h.returns, pos, 20)
    recent = recent[np.isfinite(recent)]
    max_adverse = float(np.min(recent) * 100) if len(recent) else None

    gap = None
    opens = _tail(h.open_, pos, 10)
    prev_closes = _tail(h.close, pos - 1, 10) if pos >= 1 else np.array([])
    if len(opens) == len(prev_closes) and len(opens):
        with np.errstate(divide="ignore", invalid="ignore"):
            gaps = np.where(prev_closes > 0, opens / prev_closes - 1.0, np.nan)
        gaps = gaps[np.isfinite(gaps)]
        if len(gaps):
            gap = float(np.min(gaps) * 100)

    dist200 = (last / ma200 - 1) * 100 if ma200 else None
    vol_spike = (vol20 / vol60) if (vol20 and vol60 and vol60 > 0) else None
    return {
        "aboveMA20": bool(ma20 and last > ma20),
        "aboveMA50": bool(ma50 and last > ma50),
        "aboveMA200": bool(ma200 and last > ma200),
        "dist200Pct": round(dist200, 1) if dist200 is not None else None,
        "rsi14": round(rsi, 1) if rsi is not None else None,
        "vol20Pct": round(vol20 * 100, 1) if vol20 is not None else None,
        "volSpike": round(vol_spike, 2) if vol_spike is not None else None,
        "mom63Pct": round(mom63 * 100, 1) if mom63 is not None else None,
        "maxAdversePct": round(max_adverse, 1) if max_adverse is not None else None,
        "gapDownPct": round(gap, 1) if gap is not None else None,
        "volumeSurge": surge,
        # Earnings calendars are not available point-in-time from the free feed,
        # so the EVENT_RISK-by-earnings branch is inactive in replay. That makes
        # replayed entry states slightly *more* permissive than production, which
        # is recorded rather than hidden.
        "earningsInDays": None,
    }


# --------------------------------------------------------------------------- #
# Date grids
# --------------------------------------------------------------------------- #
def replay_dates(trading_days: pd.DatetimeIndex, start=None, end=None,
                 frequency: str = "W") -> list[pd.Timestamp]:
    """Pick the replay grid from real trading days.

    ``frequency``:
      ``D``  every trading day — highest fidelity, ~5x the cost
      ``W``  last trading day of each week (default)
      ``M``  last trading day of each month — cheapest, coarsest

    Only actual trading days are ever returned, so a signal is never frozen on a
    date the market was shut.
    """
    days = pd.DatetimeIndex(sorted(pd.DatetimeIndex(trading_days).normalize().unique()))
    if start is not None:
        days = days[days >= pd.Timestamp(start).normalize()]
    if end is not None:
        days = days[days <= pd.Timestamp(end).normalize()]
    if not len(days):
        return []
    freq = (frequency or "W").upper()
    if freq in {"D", "DAILY"}:
        return list(days)
    key = "W" if freq in {"W", "WEEKLY"} else "M"
    series = pd.Series(days, index=days)
    period = days.to_period("W" if key == "W" else "M")
    picked = series.groupby(period).max()
    return [pd.Timestamp(d) for d in picked.tolist()]


# --------------------------------------------------------------------------- #
# Sector rotation proxy
# --------------------------------------------------------------------------- #
def _sector_rotation(sector_rel_now: dict[str, float],
                     sector_rel_prev: dict[str, float]) -> dict[str, str]:
    """Improving/deteriorating from each sector's own relative-strength trend.

    ``pipeline.rotation`` uses sector ETFs, which have their own listing history
    and would need a second PIT feed. The median relative momentum of the
    sector's own members is self-contained, available for the whole replay
    window, and is labelled a proxy rather than passed off as the production
    rotation read.
    """
    out: dict[str, str] = {}
    for sector, now in sector_rel_now.items():
        prev = sector_rel_prev.get(sector)
        if prev is None or not np.isfinite(now) or not np.isfinite(prev):
            out[sector] = "UNKNOWN"
            continue
        delta = now - prev
        if delta > 0.01:
            out[sector] = "IMPROVING"
        elif delta < -0.01:
            out[sector] = "DETERIORATING"
        else:
            out[sector] = "STABLE"
    return out


# --------------------------------------------------------------------------- #
# One replay date
# --------------------------------------------------------------------------- #
def _finite(value):
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _round(value, digits=4):
    f = _finite(value)
    return round(f, digits) if f is not None else None


def signal_id(as_of: str, region: str, ticker: str, replay_version: str,
              model_version: str) -> str:
    return "|".join(str(v or "UNKNOWN")
                    for v in (as_of, region, ticker, replay_version, model_version))


def replay_one_date(as_of, panel: PricePanel, universe_by_region: dict[str, list[str]],
                    *, benchmarks: dict[str, str], cfg_lt: dict,
                    fundamental_store: pit_data.FundamentalStore | None = None,
                    macro_view: pit_data.MacroVintageView | None = None,
                    survivorship_risk: str = "HIGH",
                    model_version: str = "unknown",
                    previous: dict[str, dict] | None = None,
                    macro_read: dict | None = None) -> list[dict]:
    """Everything the model would have said on ``as_of``, and nothing else.

    ``previous`` is the map of the *prior replay date's* records keyed by
    ticker. It supplies the change features (what moved since last time), which
    matter more for opportunity detection than any level does. It is strictly
    backward-looking: the caller walks dates in ascending order.
    """
    stamp = pd.Timestamp(as_of).normalize()
    as_of_np = np.datetime64(stamp, "ns")
    as_of_str = stamp.strftime("%Y-%m-%d")
    previous = previous or {}
    exclude = set((cfg_lt or {}).get("excludeFromRanking", []))
    store = fundamental_store or pit_data.FundamentalStore({})

    macro_status = pit_data.UNAVAILABLE
    if macro_view is not None and macro_view.available:
        macro_status = macro_view.pit_status()
    macro_label = (macro_read or {}).get("regime")
    macro_confidence = (macro_read or {}).get("confidence")

    records: list[dict] = []
    for region in sorted(universe_by_region):
        bench_ticker = (benchmarks or {}).get(region)
        bench = panel.get(bench_ticker) if bench_ticker else None

        positions: dict[str, int] = {}
        histories: dict[str, TickerHistory] = {}
        for ticker in universe_by_region.get(region, []):
            if ticker in exclude or ticker == bench_ticker:
                continue
            history = panel.get(ticker)
            if history is None:
                continue
            pos = history.position(as_of_np)
            if pos < 0 or pos + 1 < MIN_HISTORY_ROWS:
                continue
            age = (stamp - pd.Timestamp(history.dates[pos])).days
            if age > MAX_STALE_CALENDAR_DAYS:
                continue           # halted, delisted, or a vendor gap — not tradable
            positions[ticker] = pos
            histories[ticker] = history
        if len(positions) < 5:
            continue

        pit_fundamentals, fundamental_status = store.snapshot(stamp, sorted(positions))

        raw_rows: dict[str, dict] = {}
        for ticker, pos in positions.items():
            history = histories[ticker]
            # The filing supplies per-share numerators; the price that turns
            # them into yields is the one on this replay date, not the one on
            # the filing date. Anything the file states outright is kept as-is.
            fundamentals = pit_data.derive_price_relative(
                pit_fundamentals.get(ticker) or {}, history.close[pos])
            raw_rows[ticker] = {
                "sector": SECT.sector_of(ticker, fundamentals.get("sector")),
                "mom121": momentum_12_1(history, pos),
                "mom6": momentum_6m(history, pos),
                "earningsYield": fundamentals.get("earningsYield"),
                "fwdEarningsYield": fundamentals.get("fwdEarningsYield"),
                "bookYield": fundamentals.get("bookYield"),
                "fcfYield": fundamentals.get("fcfYield"),
                "roe": fundamentals.get("roe"),
                "opMargin": fundamentals.get("operatingMargin"),
                "profitMargin": fundamentals.get("profitMargin"),
                "debtToEquity": fundamentals.get("debtToEquity"),
                "earningsGrowth": fundamentals.get("earningsGrowth"),
                "marketCap": fundamentals.get("marketCap"),
                "vol252": realized_vol_252(history, pos),
                "downsideVol": downside_vol_252(history, pos),
                "cvar95": cvar_95(history, pos),
                "maxDD252": max_drawdown_252(history, pos),
                "beta": beta_to(history, pos, bench),
            }

        table = longterm_mod.score_cross_section(raw_rows, cfg_lt)
        if table is None or table.empty:
            continue
        pct = table[["momentum", "value", "quality", "lowvol"]].apply(longterm_mod._percentile)
        alpha_pct = table["alpha"].rank(method="average", pct=True).mul(100).round(0)

        # Entry states, ranked for overheat within this region's cross-section.
        surges = {t: volume_surge(histories[t], positions[t]) for t in table.index}
        feats = {t: entry_features(histories[t], positions[t], surges.get(t)) for t in table.index}
        scores = {t: entry_mod.overheat_score(f) for t, f in feats.items()}
        scores = {t: v for t, v in scores.items() if v is not None}
        overheat = (pd.Series(scores).rank(pct=True) * 100).to_dict() if scores else {}

        rel_now = {t: relative_momentum(histories[t], positions[t], bench) for t in table.index}
        rel_prev = {t: relative_momentum(histories[t], max(0, positions[t] - 21), bench)
                    for t in table.index}

        sector_rel_now: dict[str, list[float]] = {}
        sector_rel_prev: dict[str, list[float]] = {}
        for ticker in table.index:
            sector = table.loc[ticker, "sector"] or "Unclassified"
            if _finite(rel_now.get(ticker)) is not None:
                sector_rel_now.setdefault(sector, []).append(float(rel_now[ticker]))
            if _finite(rel_prev.get(ticker)) is not None:
                sector_rel_prev.setdefault(sector, []).append(float(rel_prev[ticker]))
        rotation = _sector_rotation(
            {k: float(np.median(v)) for k, v in sector_rel_now.items()},
            {k: float(np.median(v)) for k, v in sector_rel_prev.items()},
        )

        for ticker in table.index:
            row = table.loc[ticker]
            history, pos = histories[ticker], positions[ticker]
            ap = int(alpha_pct.loc[ticker]) if pd.notna(alpha_pct.loc[ticker]) else None
            classification = entry_mod.classify(feats[ticker], overheat.get(ticker))
            sector = row["sector"] or "Unclassified"
            prior = previous.get(ticker) or {}
            prior_features = prior.get("features") or {}

            mom20 = momentum_days(history, pos, 20)
            mom20_prev = momentum_days(history, max(0, pos - 20), 20)
            mom60 = momentum_days(history, pos, 60)
            mom60_prev = momentum_days(history, max(0, pos - 60), 60)
            vol20 = volatility_window(history, pos, 20)
            vol60 = volatility_window(history, pos, 60)
            ma50 = moving_average(history, pos, 50)
            ma200 = moving_average(history, pos, 200)
            last = float(history.close[pos])

            level = {
                "alphaPercentile": float(ap) if ap is not None else None,
                "momentumPercentile": _finite(pct.loc[ticker, "momentum"]),
                "valuePercentile": _finite(pct.loc[ticker, "value"]),
                "qualityPercentile": _finite(pct.loc[ticker, "quality"]),
                "lowvolPercentile": _finite(pct.loc[ticker, "lowvol"]),
                "relMomentum": _round(rel_now.get(ticker)),
                "aboveMA50": 1.0 if (ma50 and last > ma50) else 0.0,
                "aboveMA200": 1.0 if (ma200 and last > ma200) else 0.0,
                "rsi14": _finite(feats[ticker].get("rsi14")),
                "dist200Pct": _finite(feats[ticker].get("dist200Pct")),
                "volumeSurge": _finite(surges.get(ticker)),
                "realizedVolPct": _round((_finite(row.get("vol252")) or 0) * 100, 2)
                                   if _finite(row.get("vol252")) is not None else None,
                "downsideVolPct": _round((_finite(row.get("downsideVol")) or 0) * 100, 2)
                                   if _finite(row.get("downsideVol")) is not None else None,
                "cvar95Pct": _round(row.get("cvar95"), 3),
                "maxDD252Pct": _round(row.get("maxDD252"), 2),
                "mom20Pct": _round((mom20 or 0) * 100, 2) if mom20 is not None else None,
                "mom60Pct": _round((mom60 or 0) * 100, 2) if mom60 is not None else None,
                "overheatPercentile": _finite(overheat.get(ticker)),
                "evidenceCoverage": _finite(row.get("evidenceCoverage")),
            }
            # Change features. "What is different from last time" is the whole
            # point of the opportunity layer, so these are first-class inputs and
            # not derived downstream where a leak could sneak in.
            change = {
                "alphaPercentileDelta": (
                    level["alphaPercentile"] - prior_features["alphaPercentile"]
                    if level["alphaPercentile"] is not None
                    and prior_features.get("alphaPercentile") is not None else None),
                "relMomentumDelta": (
                    level["relMomentum"] - prior_features["relMomentum"]
                    if level["relMomentum"] is not None
                    and prior_features.get("relMomentum") is not None else None),
                "momentum20Acceleration": _round(
                    ((mom20 - mom20_prev) * 100) if (mom20 is not None and mom20_prev is not None) else None, 2),
                "momentum60Acceleration": _round(
                    ((mom60 - mom60_prev) * 100) if (mom60 is not None and mom60_prev is not None) else None, 2),
                "volumeSurgeDelta": (
                    level["volumeSurge"] - prior_features["volumeSurge"]
                    if level["volumeSurge"] is not None
                    and prior_features.get("volumeSurge") is not None else None),
                "volRegimeRatio": _round((vol20 / vol60) if (vol20 and vol60 and vol60 > 0) else None, 3),
                "entryStateImproved": _entry_direction(prior.get("entryState"),
                                                        classification["entryState"]),
                "sectorRotationImproved": _rotation_direction(prior.get("sectorRotation"),
                                                              rotation.get(sector, "UNKNOWN")),
                "ma200Crossed": (
                    1.0 if (level["aboveMA200"] == 1.0 and prior_features.get("aboveMA200") == 0.0)
                    else -1.0 if (level["aboveMA200"] == 0.0 and prior_features.get("aboveMA200") == 1.0)
                    else 0.0) if prior_features.get("aboveMA200") is not None else None,
            }

            # A fundamentals status of CURRENT_SNAPSHOT_ONLY means the sleeve was
            # withheld from the replay entirely, so it is reported as UNAVAILABLE
            # (contributed nothing) rather than as a stale input that leaked in.
            fundamental_state = fundamental_status.get(ticker, pit_data.CURRENT_SNAPSHOT_ONLY)
            used_fundamentals = bool(pit_fundamentals.get(ticker))
            statuses = {
                "price": pit_data.PriceView.price_pit_status,
                "fundamentals": (fundamental_state if used_fundamentals
                                 else pit_data.UNAVAILABLE),
                "macro": macro_status,
                "universe": (pit_data.PIT_EXACT if survivorship_risk == "LOW"
                             else pit_data.PIT_APPROXIMATE if survivorship_risk == "MEDIUM"
                             else pit_data.REVISED_HISTORY),
            }
            pit_block = pit_data.quality_report(
                statuses, survivorship_risk=survivorship_risk, look_ahead_passed=True,
                weights=(PIT_SOURCE_WEIGHTS_WITH_FUNDAMENTALS if used_fundamentals
                         else PIT_SOURCE_WEIGHTS_PRICE_ONLY))
            pit_block["fundamentalsSleeveUsed"] = used_fundamentals
            pit_block["fundamentalsSourceState"] = fundamental_state

            records.append({
                "id": signal_id(as_of_str, region, ticker, REPLAY_VERSION, model_version),
                "asOf": as_of_str,
                "date": as_of_str,
                "ticker": ticker,
                "region": region,
                "sector": sector,
                "evidenceClass": EVIDENCE_HISTORICAL,
                "longTermAlphaPercentile": ap,
                "alpha": _round(row.get("alpha"), 4),
                "rawAlpha": _round(row.get("rawAlpha"), 4),
                "alphaPercentile": ap,
                "longTermResearchView": longterm_mod.research_view(row, ap),
                "dataInsufficient": bool(row.get("dataInsufficient")),
                "valueTrap": bool(row.get("valueTrap")),
                "factorPercentiles": {
                    "momentum": _int(pct.loc[ticker, "momentum"]),
                    "value": _int(pct.loc[ticker, "value"]),
                    "quality": _int(pct.loc[ticker, "quality"]),
                    "lowvol": _int(pct.loc[ticker, "lowvol"]),
                },
                "factorAvailability": {
                    "sleevesAvailable": [key for key in ("momentum", "value", "quality", "lowvol")
                                         if _finite(pct.loc[ticker, key]) is not None],
                    "sleevesWithheld": [key for key in ("momentum", "value", "quality", "lowvol")
                                        if _finite(pct.loc[ticker, key]) is None],
                    "factorCoverage": _round(float(row.get("factorCoverage") or 0), 3),
                    "sourceQuality": _round(float(row.get("sourceQuality") or 0), 3),
                    "pitFundamentalsUsed": used_fundamentals,
                },
                "entryState": classification["entryState"],
                "entryReasons": classification["reasons"],
                "overheatPercentile": classification["overheatPercentile"],
                "relativeMomentum": _round(rel_now.get(ticker)),
                "volumeSurge": _finite(surges.get(ticker)),
                "macroRegime": macro_label,
                "macroConfidence": _finite(macro_confidence),
                "sectorRotation": rotation.get(sector, "UNKNOWN"),
                "shortTermModelScore": None,
                "shortTermModelStatus": "NOT_REPLAYED_COMPUTE_BUDGET",
                "marketCap": _round(row.get("marketCap"), 2),
                "refClose": round(last, 6),
                "benchmark": bench_ticker,
                "risk": {
                    "vol252Pct": level["realizedVolPct"],
                    "downsideVolPct": level["downsideVolPct"],
                    "cvar95Pct": level["cvar95Pct"],
                    "maxDD252Pct": level["maxDD252Pct"],
                    "beta": _round(row.get("beta"), 3),
                },
                "features": {**level, **change},
                "modelVersion": model_version,
                "replayVersion": REPLAY_VERSION,
                "featureVersion": FEATURE_VERSION,
                "dataVersion": DATA_VERSION,
                "futureDataUsed": False,
                "pit": pit_block,
            })
    return records


def _int(value):
    f = _finite(value)
    return int(f) if f is not None else None


def _entry_direction(before: str | None, after: str | None) -> float | None:
    """+1 improved, -1 worsened, 0 unchanged — on the entry-state ladder."""
    order = {state: i for i, state in enumerate(reversed(entry_mod.ENTRY_STATES))}
    if before not in order or after not in order:
        return None
    return float(np.sign(order[after] - order[before]))


def _rotation_direction(before: str | None, after: str | None) -> float | None:
    order = {"DETERIORATING": 0, "UNKNOWN": 1, "STABLE": 1, "IMPROVING": 2}
    if before not in order or after not in order:
        return None
    return float(np.sign(order[after] - order[before]))


# --------------------------------------------------------------------------- #
# Full replay
# --------------------------------------------------------------------------- #
def run_replay(prices: dict[str, pd.DataFrame], universe: dict[str, list[str]], *,
               benchmarks: dict[str, str], cfg_lt: dict,
               start=None, end=None, frequency: str = "W",
               fundamental_store: pit_data.FundamentalStore | None = None,
               macro: pd.DataFrame | None = None, vix: pd.Series | None = None,
               universe_history: pit_data.UniverseHistory | None = None,
               model_version: str = "unknown",
               existing_ids: set[str] | None = None,
               progress: bool = False) -> dict:
    """Walk the grid forward and freeze one cross-section per date.

    ``existing_ids`` makes the run incremental: a signal already in the ledger
    is skipped, never recomputed and never overwritten. That is what lets CI run
    this daily without re-deriving a decade of history — and it is also the
    mechanism that makes historical signals immutable in practice, not just in
    intent.
    """
    panel = PricePanel(prices)
    macro_view = pit_data.MacroVintageView(macro, vix)
    universe_history = universe_history or pit_data.UniverseHistory({})
    existing_ids = existing_ids or set()

    bench_tickers = [t for t in (benchmarks or {}).values() if t in panel]
    calendar = panel.trading_days(bench_tickers or None)
    grid = replay_dates(calendar, start=start, end=end, frequency=frequency)

    signals: list[dict] = []
    previous: dict[str, dict] = {}
    skipped = 0
    dates_done = 0
    coverage_samples: list[float] = []
    regimes: dict[str, int] = {}

    for stamp in grid:
        snapshot = universe_history.snapshot(stamp, universe,
                                             view=panel.membership_view(stamp),
                                             min_history=MIN_HISTORY_ROWS)
        macro_t, vix_t = macro_view.as_of(stamp)
        macro_read = None
        if macro_t is not None or vix_t is not None:
            try:
                macro_read = regime_mod.build(macro_t, vix_t, asof=stamp)
            except Exception:
                macro_read = None

        rows = replay_one_date(
            stamp, panel, snapshot.by_region, benchmarks=benchmarks, cfg_lt=cfg_lt,
            fundamental_store=fundamental_store, macro_view=macro_view,
            survivorship_risk=snapshot.survivorship_risk, model_version=model_version,
            previous=previous, macro_read=macro_read,
        )
        previous = {row["ticker"]: row for row in rows}
        for row in rows:
            coverage_samples.append(float((row.get("pit") or {}).get("pitCoverage") or 0.0))
            if row.get("macroRegime"):
                regimes[row["macroRegime"]] = regimes.get(row["macroRegime"], 0) + 1
            if row["id"] in existing_ids:
                skipped += 1
                continue
            signals.append(row)
        dates_done += 1
        if progress and dates_done % 25 == 0:
            print(f"  replay {stamp.date()} — {len(signals)} new signals")

    diagnostics = {
        "gridDates": [d.strftime("%Y-%m-%d") for d in grid[-4:]],
        "replayVersion": REPLAY_VERSION,
        "featureVersion": FEATURE_VERSION,
        "dataVersion": DATA_VERSION,
        "modelVersion": model_version,
        "frequency": frequency,
        "requestedStart": str(start) if start else None,
        "requestedEnd": str(end) if end else None,
        "firstDate": grid[0].strftime("%Y-%m-%d") if grid else None,
        "lastDate": grid[-1].strftime("%Y-%m-%d") if grid else None,
        "replayDates": len(grid),
        "signalsGenerated": len(signals),
        "signalsSkippedAlreadyPresent": skipped,
        "meanPitCoverage": round(float(np.mean(coverage_samples)), 4) if coverage_samples else 0.0,
        "survivorshipRisk": "LOW" if universe_history.available else "HIGH",
        "survivorshipNote": (None if universe_history.available
                             else pit_data.SURVIVORSHIP_UNRESOLVED),
        "fundamentalsPit": bool(fundamental_store and fundamental_store.available),
        "historicalUniverseAvailable": bool(universe_history.available),
        "constituentCoveragePct": 100.0 if universe_history.available else None,
        "universeSource": ("HISTORICAL_MEMBERSHIP_DATASET" if universe_history.available
                           else "CURRENT_UNIVERSE_WITH_PRICE_HISTORY_FILTER_ONLY"),
        "firstReliableUniverseDate": (grid[0].strftime("%Y-%m-%d")
                                      if grid and universe_history.available else None),
        "affectedObservationsPct": 0.0 if universe_history.available else 100.0,
        "affectedRegions": [] if universe_history.available else sorted(universe),
        "impactOnPromotionEligibility": ("NONE" if universe_history.available
                                         else "KELLY_AND_SELECTOR_PROMOTION_BLOCKED"),
        "fundamentalsContract": getattr(fundamental_store, "diagnostics", {}),
        "macroPitStatus": macro_view.pit_status(),
        "regimeDistribution": dict(sorted(regimes.items())),
        "shortTermModelReplayed": False,
        "knownDeviationsFromProduction": [
            "short_term_lightgbm_score_not_replayed",
            "earnings_calendar_unavailable_event_risk_branch_inactive",
            "sector_rotation_is_member_relative_strength_proxy_not_etf_rrg",
            "entry_sector_concentration_overlay_not_applied_no_sleeve_in_replay",
        ],
    }
    return {"signals": signals, "diagnostics": diagnostics}


def live_features(prices: dict[str, pd.DataFrame], universe: dict[str, list[str]], *,
                  benchmarks: dict[str, str], cfg_lt: dict,
                  as_of=None, grid_dates: int = 4, frequency: str = "W",
                  fundamental_store: pit_data.FundamentalStore | None = None,
                  macro: pd.DataFrame | None = None, vix: pd.Series | None = None,
                  model_version: str = "unknown") -> dict:
    """Today's feature vectors, built by the SAME code that built the training set.

    This is not a convenience wrapper — it is the fix for the most common silent
    failure in a deployed model. If the daily build assembled its own
    "current momentum, current alpha percentile" from the production long-term
    table, those numbers would differ from the replay's in a dozen small ways
    (fundamentals present vs absent, a different previous-observation spacing
    for the change features, a different overheat cross-section). The model
    would then be scored on features it was never trained on, and nothing would
    error — the scores would just quietly stop meaning anything.

    Running the replay engine over the last few grid dates guarantees the
    training and serving feature definitions cannot drift apart, because there
    is only one definition. In particular the value/quality percentiles are
    absent here exactly as they are absent in a price-only historical ledger.
    """
    replay = run_replay(
        prices, universe, benchmarks=benchmarks, cfg_lt=cfg_lt,
        start=(pd.Timestamp(as_of) - pd.tseries.offsets.BDay(10 * max(2, grid_dates))
               if as_of is not None else None),
        end=as_of, frequency=frequency, fundamental_store=fundamental_store,
        macro=macro, vix=vix, model_version=model_version,
    )
    rows = replay["signals"]
    if not rows:
        return {"asOf": None, "rows": [], "diagnostics": replay["diagnostics"]}
    latest = max(row["asOf"] for row in rows)
    return {
        "asOf": latest,
        "rows": [row for row in rows if row["asOf"] == latest],
        "diagnostics": replay["diagnostics"],
    }
