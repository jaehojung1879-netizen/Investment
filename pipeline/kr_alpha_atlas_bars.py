"""kr-alpha-atlas Phase B — volume, traded-value and liquidity features from as-traded KRX bars, with the corporate-action basis made explicit.

WHAT THIS IS. A thin, pure layer over `liquidity_attention` (the registry's family D/E calculations are ITS functions, not copies) and
`krx_prices` (split detection and the vendor-basis conversion). It reads one ticker's as-traded OHLCV + listed-share bars and returns, for any
signal session T, every registered volume / traded-value / liquidity value and the reason a value is missing. It reads no label, no forward
price and no outcome, and nothing here is imported by production.

THE BASIS RULES (each one is a test).
  * Volume, traded value and turnover are three quantities. Volume is shares; traded value is KRW = AS-TRADED close x AS-TRADED volume, which a
    split cannot move; turnover is volume over listed shares, both on one split basis. An adjusted close is never multiplied by an unadjusted
    volume.
  * A split is a corporate action the market cannot manufacture (a clean par-value ratio, at least a 42.5% price move, corroborated by the
    listed-share count). `krx_prices.detect_splits` decides which sessions are splits; this module adds WHEN each became knowable.
    `LIST_SHRS` can lag the ex-date by weeks (064960.KS: 33 days), so a split is "confirmed by T" only once the share count has moved. A
    feature window that contains a price move shaped like a split which is NOT confirmed by T is MISSING, never adjusted with later knowledge.
  * The listed-share count is stale between the ex-date and its own update; a turnover window touching that interval is MISSING.
  * A suspension is not a session. KRX carries a halted issue's last close at zero volume; those rows are NaN here, so a window containing one is
    MISSING (strict), and nothing is filled with a fabricated trade. Suspensions are counted separately (E07).
  * A price move above the daily limit that no clean ratio explains (capital reduction, re-listing) is `UNEXPLAINED_PRICE_MOVE_IN_WINDOW`.

PIT. Every rolling statistic ends at the row's own session; `features_at` reads nothing later than T. The truncation-invariance test recomputes
a value from a frame cut at T and requires the same answer.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd

from . import kr_alpha_tournament_features as TF
from . import krx_prices as KP
from . import liquidity_attention as LA
from .price_adjustment import future_split_factor

CONTRACT = "KR_ALPHA_ATLAS_BARS_V1"
TRADING_VALUE_BASIS_PROXY = "PROXY_ASTRADED_CLOSE_X_VOLUME"
TRADING_VALUE_BASIS_OFFICIAL = "OFFICIAL_KRX_ACC_TRDVAL"

# Windows (sessions). Each is the registry's own name for the feature; none is searched.
W_SHOCK = 60
W_SHORT = 5
W_ADV = 60
W_TURNOVER = 60
W_AMIHUD = 60
W_COUNT = 21          # D08 / D09: days in the last month with a shock and a close at an extreme of the range
W_LIQ_FAST, W_LIQ_SLOW = 20, 120
W_AD = 20
W_TRADABLE = 20
W_SPREAD = 20
W_REGIME_BUFFER = 0

SHOCK_THRESHOLD = 1.0   # liquidity_attention.compute_features default: log(volume / 60d mean) > 1, a 2.7x day. Inherited, not tuned.

BARS_FEATURES = {
    "D01_volumeSurge5_60": 60, "D02_logVolumeShock60": 60, "D03_tradingValueShock5_60": 60, "D04_shockPersistence5d": 64, "D05_turnoverToMarketCap60": 60,
    "D06_priceVolumeDivergence": 80, "D07_volumePriceAlignment": 61, "D08_abnormalVolumeUpClose": 80, "D09_abnormalVolumeDownClose": 80,
    "D10_liquidityAcceleration": 120, "D11_accumulationDistributionProxy": 20, "E01_amihudIlliquidity60": 61, "E03_capacityMedianTradedValue60": 60,
    "E04_tradabilityGuard20": 20, "E05_highLowSpreadProxy": 21, "E06_volatilityConditionalOnVolume": 80, "E07_suspensionStaleRisk": 20,
}

MISSING_REASONS = ("NO_QUOTE_AT_SIGNAL", "INSUFFICIENT_HISTORY", "GAP_OR_SUSPENSION_IN_WINDOW", "UNCONFIRMED_CORPORATE_ACTION_IN_WINDOW",
                   "UNEXPLAINED_PRICE_MOVE_IN_WINDOW", "STALE_SHARE_COUNT_IN_WINDOW", "NON_POSITIVE_DENOMINATOR_OR_DEGENERATE")


# --------------------------------------------------------------------------- #
# Corporate-action events with the date each became knowable
# --------------------------------------------------------------------------- #
def split_events(traded):
    """Confirmed splits and the sessions that look like splits but were never confirmed, for ONE ticker.

    `traded` is `krx_prices.frame_from_rows(rows)` (zero-volume sessions already dropped). Returns (events, unconfirmed, stale):
      events      [{date, ratio, confirmedOn}] — exactly the sessions `detect_splits` books; `confirmedOn` is the first session on which the
                  share count had moved towards the ratio (never before the ex-date itself)
      unconfirmed [date] — price-led candidates (a clean ratio) that `detect_splits` did not book: never confirmed, or inside the liquidation tail
      stale       [(start, end)] — sessions whose listed-share count does not describe the price basis (between the ex-date and the share update)
    """
    if traded is None or not len(traded):
        return [], [], []
    ratios = KP.detect_splits(traded)
    shares = pd.to_numeric(traded["ListedShares"], errors="coerce").to_numpy(float)
    close = pd.to_numeric(traded["Close"], errors="coerce").to_numpy(float)
    index = traded.index
    moves = [(p, shares[p] / shares[p - 1]) for p in range(1, len(traded))
             if np.isfinite(shares[p]) and np.isfinite(shares[p - 1]) and shares[p - 1] > 0 and shares[p] != shares[p - 1]]
    events, stale, booked = [], [], set()
    for p in np.flatnonzero(ratios.to_numpy(float) != 1.0):
        ratio = float(ratios.iloc[p])
        dates = [index[w] for w, r in moves if abs((index[w] - index[p]).days) <= KP.SHARE_REGISTRY_LAG_DAYS
                 and r > 0 and abs(math.log(r / ratio)) < abs(math.log(r))]
        if not dates:      # cannot happen for a booked split; refuse to invent a confirmation date
            continue
        first = min(dates)
        events.append({"date": index[p], "ratio": ratio, "confirmedOn": max(index[p], first)})
        stale.append((min(index[p], first), max(index[p], first)))
        booked.add(int(p))
    unconfirmed = []
    for p in range(1, len(traded)):
        if p in booked or not (np.isfinite(close[p]) and np.isfinite(close[p - 1]) and close[p] > 0):
            continue
        if KP.nearest_clean_ratio(close[p - 1] / close[p]) is not None:
            unconfirmed.append(index[p])
    return events, unconfirmed, stale


def unexplained_dates(traded, events):
    """Sessions with a move beyond the daily limit that no booked split explains (`krx_prices.unexplained_moves`, on the same basis the replay uses)."""
    if traded is None or len(traded) < 2:
        return []
    ratios = pd.Series(1.0, index=traded.index)
    for e in events:
        ratios.loc[e["date"]] = e["ratio"]
    vendor = KP.to_vendor_basis(traded, ratios)
    return [pd.Timestamp(m["date"]) for m in KP.unexplained_moves(vendor)]


# --------------------------------------------------------------------------- #
# One ticker
# --------------------------------------------------------------------------- #
class TickerBars:
    """Everything needed to read any signal session of one ticker. Built once; `features_at` is a lookup plus a window scan."""

    def __init__(self, ticker, raw, calendar, trading_value=None):
        self.ticker = ticker
        self.calendar = calendar
        self.empty = raw is None or not len(raw)
        self.first = self.last = None
        self.events, self.unconfirmed, self.stale, self.unexplained = [], [], [], []
        self.trading_value_basis = TRADING_VALUE_BASIS_OFFICIAL if trading_value is not None else TRADING_VALUE_BASIS_PROXY
        if self.empty:
            self.daily = pd.DataFrame()
            return
        raw = raw[~raw.index.duplicated(keep="first")].sort_index()
        traded = raw[(pd.to_numeric(raw["Volume"], errors="coerce") > 0) & (pd.to_numeric(raw["Close"], errors="coerce") > 0)]
        self.first, self.last = raw.index.min(), raw.index.max()
        self.events, self.unconfirmed, self.stale = split_events(traded)
        self.unexplained = unexplained_dates(traded, self.events)
        span = calendar[(calendar >= self.first) & (calendar <= self.last)]
        self.span = span
        self.positions = {d: i for i, d in enumerate(span)}
        frame = traded.reindex(span)
        ratios = pd.Series(1.0, index=span)
        for e in self.events:
            if e["date"] in ratios.index:
                ratios.loc[e["date"]] = e["ratio"]
        after = pd.Series(future_split_factor(ratios.to_numpy(float)), index=span)
        adj = pd.DataFrame(index=span)
        for col in ("Open", "High", "Low", "Close"):
            adj[col] = pd.to_numeric(frame[col], errors="coerce") / after
        adj["Volume"] = pd.to_numeric(frame["Volume"], errors="coerce") * after
        shares = pd.to_numeric(frame["ListedShares"], errors="coerce") * after
        valid = pd.Series(True, index=span)
        for start, end in self.stale:
            valid.loc[(span >= start) & (span < end)] = False
        adj["Shares"] = shares.where(valid)
        self.traded_mask = frame["Close"].notna()
        self.asts = frame[["Close", "Volume", "ListedShares"]].astype(float)
        # KRW traded value on the AS-TRADED basis: unaffected by any split.
        asts_close = pd.to_numeric(frame["Close"], errors="coerce")
        asts_volume = pd.to_numeric(frame["Volume"], errors="coerce")
        dv = asts_close * asts_volume
        if trading_value is not None:
            dv = pd.to_numeric(trading_value.reindex(span), errors="coerce").where(self.traded_mask)
        adj["TradingValue"] = dv
        self.adj = adj
        self.daily = self._daily(adj)

    # -- vectorised daily table (rolling statistics end at each row's own session) ---------------------------------------------------------- #
    def _daily(self, a):
        close, volume, dv = a["Close"], a["Volume"], a["TradingValue"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)     # liquidity_attention's pct_change() default; a NaN session stays NaN in every window we read
            base = LA.compute_features(a[["Open", "High", "Low", "Close", "Volume"]], shares_outstanding=a["Shares"], shock_threshold=SHOCK_THRESHOLD)
        returns = close.pct_change(fill_method=None)
        shock = base["logVolumeShock60"]
        clv = base["closeLocationValue"]
        d = pd.DataFrame(index=a.index)
        d["D01_volumeSurge5_60"] = base["volumeRatio5_60"]
        d["D02_logVolumeShock60"] = shock
        d["D03_tradingValueShock5_60"] = np.log(LA._safe_ratio(dv.rolling(W_SHORT, min_periods=W_SHORT).mean(), dv.rolling(W_SHOCK, min_periods=W_SHOCK).mean()))
        d["D04_shockPersistence5d"] = LA.shock_persistence(shock, SHOCK_THRESHOLD, W_SHORT).where(shock.rolling(W_SHORT, min_periods=W_SHORT).count() == W_SHORT)
        daily_turnover = base["turnoverPct"]
        d["D05_turnoverToMarketCap60"] = daily_turnover.rolling(W_TURNOVER, min_periods=W_TURNOVER).mean()
        d["D06_priceVolumeDivergence"] = base["volumePriceDivergence20"]
        d["D07_volumePriceAlignment"] = base["volumePriceAlignment"]
        up = LA.close_near_high_after_shock(clv, shock, SHOCK_THRESHOLD).fillna(0.0).where(clv.notna() & shock.notna())
        down = LA.close_near_low_after_shock(clv, shock, SHOCK_THRESHOLD).fillna(0.0).where(clv.notna() & shock.notna())
        d["D08_abnormalVolumeUpClose"] = up.rolling(W_COUNT, min_periods=W_COUNT).sum()
        d["D09_abnormalVolumeDownClose"] = down.rolling(W_COUNT, min_periods=W_COUNT).sum()
        d["D10_liquidityAcceleration"] = np.log(LA._safe_ratio(dv.rolling(W_LIQ_FAST, min_periods=W_LIQ_FAST).mean(), dv.rolling(W_LIQ_SLOW, min_periods=W_LIQ_SLOW).mean()))
        flow = (2.0 * clv - 1.0) * volume
        d["D11_accumulationDistributionProxy"] = LA._safe_ratio(flow.rolling(W_AD, min_periods=W_AD).sum(), volume.rolling(W_AD, min_periods=W_AD).sum())
        amihud = LA.amihud_illiquidity_proxy(returns, dv, W_AMIHUD)
        d["E01_amihudIlliquidity60"] = np.log(amihud.where(amihud > 0))
        d["E03_capacityMedianTradedValue60"] = dv.rolling(W_ADV, min_periods=W_ADV).median()
        d["E05_highLowSpreadProxy"] = corwin_schultz(a["High"], a["Low"], W_SPREAD)
        d["E06_volatilityConditionalOnVolume"] = base["rangeTimesVolume"]
        traded = self.traded_mask.astype(float)
        d["E04_tradabilityGuard20"] = traded.rolling(W_TRADABLE, min_periods=W_TRADABLE).sum()
        d["E07_suspensionStaleRisk"] = (1.0 - traded).rolling(W_TRADABLE, min_periods=W_TRADABLE).sum()
        # Pure helpers the matrix also needs; never a registry feature on their own.
        d["_returnAbs"] = returns.abs()
        return d

    # -- one signal session ----------------------------------------------------------------------------------------------------------------- #
    def features_at(self, date):
        """({feature: value}, {feature: reason}) for the signal session `date`. Reads only sessions up to and including it."""
        values, reasons = {}, {}
        date = pd.Timestamp(date)
        if self.empty or date not in self.positions:
            for f in BARS_FEATURES:
                reasons[f] = "NO_QUOTE_AT_SIGNAL"
            return values, reasons
        pos = self.positions[date]
        row = self.daily.iloc[pos]
        listed = self.traded_mask.iloc[pos]
        for feature, window in BARS_FEATURES.items():
            value = row[feature]
            if not listed and feature not in ("E04_tradabilityGuard20", "E07_suspensionStaleRisk"):
                reasons[feature] = "NO_QUOTE_AT_SIGNAL"
                continue
            cause = None if feature in ("E04_tradabilityGuard20", "E07_suspensionStaleRisk") else self._window_cause(
                pos, window, date, share_based=(feature == "D05_turnoverToMarketCap60"))
            if cause:
                reasons[feature] = cause
            elif value is None or not np.isfinite(value):
                reasons[feature] = self._missing_reason(pos, window)
            else:
                values[feature] = float(value)
        return values, reasons

    def basis_cause(self, date, window):
        """The corporate-action problem (if any) inside the last `window` sessions of `date`, for features computed from another price source
        (the replay close) over the SAME ticker: the replay panel adjusts splits with the share count's later confirmation, which a live signal on
        `date` would not have had."""
        date = pd.Timestamp(date)
        if self.empty or date not in self.positions:
            return None
        return self._window_cause(self.positions[date], window, date)

    def _window_cause(self, pos, window, date, share_based=False):
        """A basis problem inside [pos-window+1, pos] known at `date`, or None."""
        lo = self.span[max(0, pos - window - 1)]       # one extra session: returns need the prior close
        for e in self.events:
            if lo <= e["date"] <= date and e["confirmedOn"] > date:
                return "UNCONFIRMED_CORPORATE_ACTION_IN_WINDOW"
        for u in self.unconfirmed:
            if lo <= u <= date:
                return "UNCONFIRMED_CORPORATE_ACTION_IN_WINDOW"
        for u in self.unexplained:
            if lo <= u <= date:
                return "UNEXPLAINED_PRICE_MOVE_IN_WINDOW"
        if share_based:
            window_start = self.span[max(0, pos - window + 1)]
            for start, end in self.stale:
                # sessions s with start <= s < end are stale; the interval is empty when the share count moved on the ex-date itself
                if end > start and max(start, window_start) < end and max(start, window_start) <= date:
                    return "STALE_SHARE_COUNT_IN_WINDOW"
        return None

    def _missing_reason(self, pos, window):
        if pos + 1 < window:
            return "INSUFFICIENT_HISTORY"
        sub = self.traded_mask.iloc[max(0, pos - window + 1):pos + 1]
        if not sub.all():
            return "GAP_OR_SUSPENSION_IN_WINDOW"
        return "NON_POSITIVE_DENOMINATOR_OR_DEGENERATE"

    # -- quote lookup in the shape `kr_market_value.MarketValueStore` has (so sealed feature code can run unchanged) -------------------------- #
    def quote(self, date):
        """The as-traded quote for `date`, or None when the ticker did not trade, or when its listed-share count does not describe that session
        (between a split's ex-date and the share update): a missing market capitalisation, never a wrong one."""
        date = pd.Timestamp(date)
        if self.empty or date not in self.positions:
            return None
        pos = self.positions[date]
        if not self.traded_mask.iloc[pos]:
            return None
        for start, end in self.stale:
            if start <= date < end:
                return None
        close, volume, shares = (float(self.asts.iloc[pos][c]) for c in ("Close", "Volume", "ListedShares"))
        if not (shares > 0 and np.isfinite(shares)):
            return None
        return {"date": str(date.date()), "securityId": self.ticker, "close": close, "volume": volume,
                "tradingValue": float(self.adj["TradingValue"].iloc[pos]), "listedShares": shares, "marketCap": close * shares}

    def trailing(self, date, lookback=60):
        """The last `lookback` calendar sessions ending at `date`, each a quote or None (a suspension is None, never a filled session)."""
        sessions = self.calendar[self.calendar <= pd.Timestamp(date)][-lookback:]
        return [self.quote(d) for d in sessions]


def corwin_schultz(high, low, window=20):
    """Corwin & Schultz (2012) high-low spread estimate, averaged over `window` sessions, negative estimates set to zero (as in the paper).

    S = 2 (e^a - 1) / (1 + e^a),  a = (sqrt(2 b) - sqrt(b)) / (3 - 2 sqrt 2) - sqrt(g / (3 - 2 sqrt 2)),
    b = ln(H_t/L_t)^2 + ln(H_{t+1}/L_{t+1})^2,  g = ln(max(H_t,H_{t+1}) / min(L_t,L_{t+1}))^2.
    A COST proxy for the cost model, never an alpha feature and never a quoted spread. NaN when either session of a pair is missing."""
    h, l = high.astype(float), low.astype(float)
    valid = (h > 0) & (l > 0) & (h >= l)
    h, l = h.where(valid), l.where(valid)
    beta = np.log(h / l) ** 2 + np.log(h.shift(1) / l.shift(1)) ** 2
    gamma = np.log(pd.concat([h, h.shift(1)], axis=1).max(axis=1, skipna=False) / pd.concat([l, l.shift(1)], axis=1).min(axis=1, skipna=False)) ** 2
    k = 3.0 - 2.0 * math.sqrt(2.0)
    alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    spread = (2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))).clip(lower=0.0)
    return spread.rolling(window, min_periods=window).mean()


def amihud_matches_sealed(close, trading_value):
    """The sealed instrument's value for the same window, for a regression test (`kr_alpha_tournament_features.amihud`)."""
    return TF.amihud(np.asarray(close, float), np.asarray(trading_value, float))
