"""US point-in-time cross-sections for us-selection-value-v1. Reads NO forward price: every value is known at the signal close.

    python -m research.us_selection_value_v1.features --private <dir outside git>

REUSE, NOT REIMPLEMENTATION. Prices, filings, membership, sector, identity rules and the four accounting fields come from the
owner's `US_DECISION_PILOT_V1` loaders (`scripts/run_us_decision_pilot.py`: `load_prices`, `load_filings`, `AccountingCache`,
`price_matrix_features`) and `pipeline.us_decision_pilot.scores`. TTM sums use `finnhub_derive.trailing_twelve_months`.

THE ONE NEW IDENTITY RULE. The pilot admits a filing set only when the membership snapshot's CIK is among the visible filings'
CIKs. The snapshot file carries a CIK only from 2023 on, so 2013-2022 had ZERO admissible names. Here a snapshot WITHOUT a CIK
admits a ticker only when every filing visible before the signal date carries one and the same CIK (`PIT_SINGLE_CIK`); two
or more CIKs is `CIK_AMBIGUOUS_EXCLUDED`. Snapshots WITH a CIK keep the pilot rule exactly. The rule's agreement with the
membership CIK is measured on the 2023+ snapshots where both are available (`cikRuleValidation`).

AS-TRADED PRICE. The replay close is a split- and forward-dividend-adjusted index, so shares x close is not a market value.
Yahoo's split-adjusted, dividend-unadjusted close x the product of later split ratios rebuilds the as-traded close on the
signal date. A ticker whose Yahoo series does not track the replay series (ratio jumps) is `AS_TRADED_SERIES_MISMATCH` and
gets no market cap. Market cap = filing share count (pilot's carried weighted diluted count) x as-traded close, withheld when
a split falls between the share filing's visible day and the signal date (`us_cash_profitability.market_cap_proxy`).
It is a PROXY (weighted-average shares, not period-end float), used for size peers, value yields and the Top-K control.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import importlib.util
import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline import finnhub_derive as FD  # noqa: E402
from pipeline import finnhub_fundamentals as FF  # noqa: E402
from pipeline import us_cash_profitability as CP  # noqa: E402
from pipeline import us_decision_pilot as UP  # noqa: E402
from pipeline import regional_alpha_features as RAF  # noqa: E402
from pipeline import us_capital_allocation_coverage as CA  # noqa: E402

_spec = importlib.util.spec_from_file_location("us_decision_pilot_runner", ROOT / "scripts/run_us_decision_pilot.py")
PILOT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(PILOT)

EXCLUDED_SECTORS = ("Financials", "Real Estate")


def ny_date(ts):
    # Yahoo daily bars carry the session open in UTC; NY open is 13:30/14:30 UTC, so the UTC calendar date is the session date
    return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).date()


class AsTraded:
    """As-traded close on a date from Yahoo split-adjusted closes and split events, validated against the replay series."""

    def __init__(self, private: Path, close: pd.DataFrame):
        self.series, self.splits, self.status = {}, {}, {}
        ydir = private / "yahoo"
        for t in close.columns:
            p = ydir / (t + ".json.gz")
            if not p.exists():
                self.status[t] = "NOT_REQUESTED"
                continue
            rec = json.loads(gzip.decompress(p.read_bytes()))
            if rec["status"] != "SERVED" or not rec.get("rows"):
                self.status[t] = "NOT_SERVED"
                continue
            s = pd.Series({pd.Timestamp(ny_date(ts)): c for ts, c in rec["rows"]}, dtype=float)
            s = s[~s.index.duplicated(keep="last")].sort_index()
            splits = [(pd.Timestamp(ny_date(ts)), n / d) for ts, n, d in rec["splits"] if d > 0 and n > 0]
            # identity check: replay / yahoo-split-adjusted must move only by dividend reinvestment (small, positive steps)
            both = pd.concat([close[t], s], axis=1, keys=["r", "y"]).dropna()
            both = both[(both.r > 0) & (both.y > 0)]
            if len(both) < 260:
                self.status[t] = "AS_TRADED_OVERLAP_TOO_SHORT"
                continue
            step = np.log(both.r / both.y).diff().dropna()
            bad = (step.abs() > 0.05).mean()
            if bad > 0.002 or step.abs().max() > 0.35:
                self.status[t] = "AS_TRADED_SERIES_MISMATCH"
                continue
            self.series[t], self.splits[t], self.status[t] = s, splits, "VERIFIED"

    def close_on(self, t, day):
        s = self.series.get(t)
        if s is None or day not in s.index:
            return None
        factor = 1.0
        for when, ratio in self.splits[t]:
            if when > day:
                factor *= ratio
        return float(s.loc[day] * factor)

    def split_days(self, t):
        return [str(w.date()) for w, _ in self.splits.get(t, [])]


class Cache(PILOT.AccountingCache):
    """The pilot cache plus TTM levels and the visible CIK set; identical visibility and staleness rules."""

    def at(self, day):
        values, ciks = super().at(day)
        n = PILOT.bisect_left(self.days, day)
        key2 = ("x", n)
        if key2 not in self.cache:
            visible = self.records[:n]
            by_key = FD.index_filings(visible)
            key = CP.current_key(by_key)
            extra = {}
            if key is not None:
                year, stage = key
                for field in ("netIncome", "operatingCashFlow", "revenue", "capex"):
                    extra[field + "TTM"], _ = FD.trailing_twelve_months(by_key, year, stage, field)
                    extra[field + "TTMPrior"], _ = FD.trailing_twelve_months(by_key, year - 1, stage, field)
                current = by_key[key]
                resolved = FF.resolve_units(current)
                extra["equity"] = FD.amount(current, "bs", FD.EQUITY, resolved)
                extra["_impliedShares"] = implied_shares(current, resolved)
                extra["_currentVisibleDay"] = CP.visible_day(current).isoformat()
            self.cache[key2] = extra
        extra = dict(self.cache[key2])
        if values.get("reportAgeDays") is None or not 0 <= values["reportAgeDays"] <= 180:
            extra = {k: None for k in extra}
        implied = extra.pop("_impliedShares", None)
        visible = extra.pop("_currentVisibleDay", None)
        values.update(extra)
        values.setdefault("sharesBasis", None)
        if not values.get("sharesForProxy") and implied:
            # CORRECTION F2 (2026-11-15, after the first evaluation; an input defect found by audit, not by a return):
            # filings that state no share count (GOOGL, XOM ...) get net income / diluted EPS from the SAME filing
            values.update(sharesForProxy=implied, sharesBasis="NET_INCOME_OVER_DILUTED_EPS_SAME_FILING", sharesVisibleDay=visible)
        return values, ciks


def implied_shares(record, resolved):
    """Net income / diluted EPS of one filing (same period, same statement). None unless both are stated, EPS is at least
    one cent in size and the two have the same sign. A proxy share count, labelled as such wherever it is used."""
    ni = FD.amount(record, FD.FLOWS["netIncome"][0], FD.FLOWS["netIncome"][1], resolved)
    eps = None
    for row in record.get("statements", {}).get("ic", []):
        if row.get("concept", "").split("_", 1)[-1] == "EarningsPerShareDiluted" and isinstance(row.get("value"), (int, float)):
            eps = float(row["value"])
            break
    if ni is None or eps is None or abs(eps) < 0.01 or ni == 0 or (ni > 0) != (eps > 0):
        return None
    return float(ni / eps)


def verified_class_links(close):
    """CORRECTION F1: symbol -> successor for the class links Codex verified with an official SEC citation and the same CIK
    (research/us_historical_market_recovery_v1/results/security-lineage.json); used only where the successor is priced."""
    d = json.loads((ROOT / "research/us_historical_market_recovery_v1/results/security-lineage.json").read_text())
    out = {}
    for x in d["collection_security_links"]:
        link = x.get("class_link") or {}
        succ = link.get("successor_symbol")
        if succ and link.get("identity_citation") and succ in close.columns:
            out[x["audit_identifier"]] = succ
    return out


def weekly_signal_dates(close):
    cutoff = str(close.index[-1].date())
    calendar = PILOT.RC.sessions("2013-01-01", str((close.index[-1] + pd.Timedelta(days=10)).date()), "US")
    grid = pd.Series(calendar, index=calendar).groupby(calendar.to_period("W")).max()
    return [d for d in grid if str(d.date()) <= cutoff and d in close.index]


def build(private: Path):
    S = private
    pk = pickle.load(open(S / "close.pkl", "rb"))
    close = pk["close"]
    raw = pickle.load(open(S / "filings.pkl", "rb"))["raw"]
    membership = RAF.MembershipSnapshots(json.loads(gzip.decompress((ROOT / PILOT.MEMBERSHIP).read_bytes()))["snapshots"])
    sectors = CA.SectorBook(json.loads(gzip.decompress((ROOT / PILOT.SECTORS).read_bytes()))["snapshots"])
    identity = json.loads((ROOT / PILOT.IDENTITY).read_bytes())["regions"]["US"]["identity"]
    categories = {t: c for c, ts in identity["categories"].items() for t in ts}
    ambiguous = {t for t, c in categories.items() if c == "TICKER_REUSE_DIFFERENT_ISSUER"} | set(identity["panelPostdatesMembership"])
    malformed = {k.upper(): v["resolvedTo"] for k, v in identity["malformed"].items() if v.get("resolvedTo")}
    renames = {t: r["pricedBy"] for t, r in identity["renames"].items() if r.get("pricedBy")}
    links = verified_class_links(close)
    for old, succ in links.items():
        renames.setdefault(old, succ)
    caches = {t: Cache(rows) for t, rows in raw.items()}
    momentum, vol = PILOT.price_matrix_features(close)
    traded = AsTraded(S, close)
    rows, funnel, cikval = [], defaultdict(Counter), Counter()
    for day in weekly_signal_dates(close):
        text = str(day.date())
        snap = membership.on(text)
        if snap is None:
            funnel[text]["NO_DATED_MEMBERSHIP"] += 1
            continue
        seen = set()
        for symbol in snap["members"]:
            c = funnel[text]
            c["memberDates"] += 1
            normalized = malformed.get(symbol.upper(), symbol)
            ticker = renames.get(normalized, normalized)
            # a verified class link (same CIK, official citation) maps the OLD symbol to its successor's panel; the reuse hold
            # concerns today's holder of the old symbol, whose panel is never read for it
            if (normalized in ambiguous and normalized not in links) or ticker in seen:
                c["IDENTITY_HOLD"] += 1
                continue
            seen.add(ticker)
            sector, basis = sectors.lookup(snap, symbol)
            if sector == CA.UNCLASSIFIED:
                c["SECTOR_UNCLASSIFIED"] += 1
                continue
            if ticker not in close:
                c["NO_PRICE_PANEL"] += 1
                continue
            if pd.isna(momentum.at[day, ticker]) or pd.isna(vol.at[day, ticker]):
                c["PRICE_HISTORY_INCOMPLETE"] += 1
                continue
            rec = {"date": text, "ticker": ticker, "sector": sector, "sectorBasis": basis,
                   "momentum252": float(momentum.at[day, ticker]), "vol252": float(vol.at[day, ticker]),
                   "inCommonUniverse": sector not in EXCLUDED_SECTORS}
            if ticker not in caches:
                rec["identity"] = "NO_PIT_FILINGS"
                c["NO_PIT_FILINGS"] += 1
                rows.append(rec)
                continue
            values, ciks = caches[ticker].at(text)
            member_cik = sectors.cik(snap, symbol)
            if member_cik:
                ok = str(int(member_cik)) in ciks
                rec["identity"] = "MEMBERSHIP_CIK" if ok else "CIK_UNVERIFIED_OR_MISMATCH"
                single = len(ciks) == 1
                cikval["single" if single else "multi"] += 1
                if single:
                    cikval["single_agrees" if ok else "single_disagrees"] += 1
            else:
                rec["identity"] = "PIT_SINGLE_CIK" if len(ciks) == 1 else ("CIK_AMBIGUOUS_EXCLUDED" if ciks else "NO_VISIBLE_FILING")
            c[rec["identity"]] += 1
            if rec["identity"] in ("MEMBERSHIP_CIK", "PIT_SINGLE_CIK"):
                keep = list(UP.ACCOUNTING) + ["netIncomeTTM", "operatingCashFlowTTM", "operatingCashFlowTTMPrior", "revenueTTM",
                                              "revenueTTMPrior", "capexTTM", "capexTTMPrior", "equity", "sharesForProxy",
                                              "sharesBasis", "sharesVisibleDay", "reportEnd", "reportAgeDays"]
                rec.update({k: values.get(k) for k in keep})
                px = traded.close_on(ticker, day)
                rec["asTradedStatus"] = traded.status.get(ticker)
                rec["asTradedClose"] = px
                if values.get("sharesForProxy") and px:
                    mcap, why = CP.market_cap_proxy(values["sharesForProxy"], px, values["sharesVisibleDay"], text, traded.split_days(ticker))
                else:
                    mcap, why = None, ("NO_AS_TRADED_PRICE" if not px else CP.SHARES_NOT_STATED)
                rec["marketCap"], rec["marketCapState"] = mcap, why
            rows.append(rec)
    df = pd.DataFrame(rows)
    return df, {k: dict(v) for k, v in funnel.items()}, dict(cikval), dict(Counter(traded.status.values())), traded.status


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    a = ap.parse_args(argv)
    S = Path(a.private)
    df, funnel, cikval, at_status, at_by = build(S)
    df.to_pickle(S / "features.pkl")
    json.dump({"funnel": funnel, "cikRuleValidation": cikval, "asTradedStatus": at_status, "asTradedByTicker": at_by},
              open(S / "features-meta.json", "w"))
    print(json.dumps({"rows": len(df), "cikRuleValidation": cikval, "asTradedStatus": at_status}))


if __name__ == "__main__":
    main()
