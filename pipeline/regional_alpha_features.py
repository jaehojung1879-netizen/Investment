"""Research-only PIT feature matrix; no production imports of this module.

The manifest is an allowlist, not a list inferred from numeric dataframe columns.
Source eligibility is decided before labels are constructed.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import dart_derive as DD
from . import finnhub_derive as FD
from . import fundamental_acceleration as FA
from . import historical_replay as HR
from . import historical_store as HS
from . import pit_data as PIT
from . import provenance
from . import replay_calendar as RC
from . import replay_inputs as RI

VERSION = "REGIONAL_ALPHA_MODEL_V1_FEATURE_MATRIX"
BENCHMARKS = {"US": "SPY", "KR": "069500.KS"}
INPUT_COMMIT = "b71d8cb5ce21815980d28b606852f9294d43cc53"
PRICE = (tuple(f"return{n}" for n in (21, 63, 126, 252)) +
         tuple(f"relative{n}" for n in (21, 63, 126, 252)) +
         ("mom6", "mom121", "relative121", "high52Distance", "rsi14", "ma200Distance",
          "vol20", "vol60", "vol252", "downsideVol252", "maxDD252", "beta252", "volumeSurge5_60"))
FUNDAMENTAL = ("roe", "operatingMargin", "profitMargin", "debtToEquity", "earningsGrowth")
DELTAS = tuple("delta_" + f for f in FA.PRIMARY_FIELDS)
EXCLUDED = {
    "earningsYield": "PER_SHARE_NUMERATOR_PRICE_BASIS_UNRESOLVED",
    "bookYield": "PER_SHARE_NUMERATOR_PRICE_BASIS_UNRESOLVED",
    "fcfYield": "PER_SHARE_NUMERATOR_PRICE_BASIS_UNRESOLVED",
    "fwdEarningsYield": "HISTORICAL_CONSENSUS_UNAVAILABLE",
    **{f: "HISTORICAL_SECTOR_UNAVAILABLE" for f in (
        "momentumPercentile", "valuePercentile", "qualityPercentile", "lowvolPercentile",
        "rawAlpha", "alphaPercentile", "sectorRelative63", "sectorRelative126", "sectorBreadth")},
}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode() + b"\n"


def digest_tree(root):
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            with path.open("rb") as stream:
                digest.update(hashlib.file_digest(stream, "sha256").digest())
    return digest.hexdigest()


def feature_manifest():
    rows = []
    for region in ("US", "KR"):
        groups = {"price": PRICE, "fundamental": FUNDAMENTAL, "acceleration": DELTAS,
                  "leadership": ("relativeStrengthBreadth52w",) if region == "US" else (),
                  "size": ("marketCap",) if region == "KR" else ()}
        for group, names in groups.items():
            for name in names:
                raw = ("Yahoo unadjusted+actions" if region == "US" else "FDR/KRX+Yahoo distributions")
                field = "replay-inputs price/* Close, Volume; own benchmark Close"
                rule = "all input sessions <= asOfDate; no future observations"
                if group in ("fundamental", "acceleration"):
                    raw = "Finnhub financials-reported" if region == "US" else "DART accounts"
                    field = "FundamentalStore.fields." + name.removeprefix("delta_")
                    rule = "visible-only raw derivation equals canonical; latest visible report period; FA resolver"
                if group == "size":
                    raw, field = "KRX sto/stk_bydd_trd MKTCAP", "krx-universe.marketCap"
                    rule = "latest strictly prior snapshot; never current market cap"
                rows.append(dict(feature=name, region=region, group=group, rawSource=raw,
                                 canonicalField=field, pitRule=rule, eligible=True,
                                 status="ELIGIBLE", transformation="within-date/region average percentile; missing indicator"))
        excluded = dict(EXCLUDED)
        if region == "US":
            excluded["marketCap"] = "MARKET_CAP_PIT_UNRESOLVED"
        else:
            excluded.update(fxBeta26w="FX_PUBLICATION_TIME_UNRESOLVED", absFxBeta26w="FX_PUBLICATION_TIME_UNRESOLVED")
        for name, reason in excluded.items():
            rows.append(dict(feature=name, region=region, group="excluded", rawSource=None,
                             canonicalField=name, pitRule=reason, eligible=False,
                             status="DATA_LINEAGE_UNRESOLVED", transformation=None))
    return rows


def allowed_features(manifest, region, price_only=False):
    return [r["feature"] for r in manifest if r["region"] == region and r["eligible"]
            and (not price_only or r["group"] in ("price", "leadership", "risk"))]


class MembershipSnapshots:
    """Select only a source snapshot strictly older than the signal date."""
    def __init__(self, snapshots):
        self.snapshots = sorted(snapshots, key=lambda x: x["date"])
        self.dates = [x["date"] for x in self.snapshots]

    def on(self, date):
        pos = bisect_right(self.dates, date) - 1
        # Daily data cannot establish intraday publication: do not use same-day.
        while pos >= 0 and self.dates[pos] >= date:
            pos -= 1
        return self.snapshots[pos] if pos >= 0 else None


def load_memberships(ledger, us_path):
    us = json.loads(gzip.decompress(Path(us_path).read_bytes()))
    snapshots = []
    grouped = {}
    for path in sorted((Path(ledger) / "universe/kr").glob("krx-universe-*.jsonl.gz")):
        for row in HS.read_jsonl(path):
            grouped.setdefault(row["date"], []).append(row)
    for date, rows in sorted(grouped.items()):
        ranked = sorted((r for r in rows if r.get("rank") is not None), key=lambda r: (r["rank"], r["ticker"]))[:120]
        snapshots.append(dict(date=date, members=sorted(r["ticker"] for r in ranked),
                              marketCaps={r["ticker"]: r.get("marketCap") for r in ranked},
                              source="KRX sto/stk_bydd_trd", sourceDigest=hashlib.sha256(canonical(rows)).hexdigest()))
    if not snapshots or not us["snapshots"]:
        raise ValueError("DATA_LINEAGE_UNRESOLVED: dated universe snapshots required")
    return {"US": MembershipSnapshots(us["snapshots"]), "KR": MembershipSnapshots(snapshots)}


def vetted_fundamentals(ledger, store):
    """Never repair sealed fields. Admit only values reproduced from visible raw inputs.

    This also catches global fiscal-period indexes incorporating late prior filings.
    Per-share ratios are intentionally outside this audit's eligible set.
    """
    raw = {}
    for region, folder, prefix in (("US", "us", "finnhub-"), ("KR", "kr", "dart-")):
        for path in sorted((Path(ledger) / "fundamentals" / folder).glob(prefix + "*.jsonl.gz")):
            for row in HS.read_jsonl(path):
                raw.setdefault(row["ticker"], []).append(row)
    records, audit = {}, {"canonicalRecords": len(store), "matchedFields": 0, "withheldFields": 0,
                           "mixedReceiptRecords": 0, "rawTickers": len(raw)}
    for ticker, filings in sorted(store._records.items()):
        region = "KR" if ticker.endswith((".KS", ".KQ")) else "US"
        derivation = DD if region == "KR" else FD
        for filing in filings:
            visible = [r for r in raw.get(ticker, []) if r.get("availableFrom")
                       and r["availableFrom"] <= filing.available_from]
            if region == "KR":
                clean = []
                for r in visible:
                    receipts = r.get("receiptNos") or []
                    dates = {s[:8] for s in receipts}
                    if len(dates) != 1 or next(iter(dates)) != r["availableFrom"].replace("-", ""):
                        audit["mixedReceiptRecords"] += 1
                    else:
                        clean.append(r)
                visible = clean
            index = derivation.index_filings(sorted(visible, key=lambda r: r["availableFrom"]))
            year, stage = filing.report_period.rsplit("-", 1)
            key = (int(year), stage)
            source = index.get(key)
            derived = (derivation.derive_fields(index, *key)[0]
                       if source and source["availableFrom"] == filing.available_from else {})
            fields = {}
            for name in FUNDAMENTAL:
                value = PIT._safe_number(filing.fields.get(name))
                other = PIT._safe_number(derived.get(name))
                if value is not None and other is not None and np.isclose(value, other, rtol=1e-10, atol=1e-12):
                    fields[name] = value
                    audit["matchedFields"] += 1
                elif value is not None:
                    audit["withheldFields"] += 1
            # Keep empty filings: dropping one would carry forward stale fields invisibly.
            records.setdefault(ticker, []).append(replace(filing, fields=fields))
    return PIT.FundamentalStore(records), audit


def load_inputs(ledger):
    store = RI.InputStore(ledger, "replay-v16", provenance.DATA_VERSION)
    manifest = store.manifest()
    if not manifest:
        raise ValueError("sealed replay-v16 inputs required")
    components, by_ticker = {}, {}
    for name in sorted(manifest["components"]):
        if RI.is_price_panel(name):
            for row in store.load_component(name):
                by_ticker.setdefault(row["ticker"], []).append({k: v for k, v in row.items() if k != "ticker"})
        elif name in ("fundamentals", "price/source", "benchmark/source", "corporate-events/source"):
            components[name] = store.load_component(name)
    if (components.get("corporate-events/source") or [{}])[0].get("basis") != "AS_TRADED_CLOSE_WITH_FORWARD_ACCUMULATED_TOTAL_RETURN":
        raise ValueError("price basis unresolved")
    for region, ticker in BENCHMARKS.items():
        if not any(r.get("region") == region and r.get("ticker") == ticker for r in components["benchmark/source"]):
            raise ValueError("benchmark lineage mismatch")
    prices = {t: RI.rows_frame(rows).sort_index() for t, rows in by_ticker.items()}
    records = {}
    for row in components["fundamentals"]:
        record = PIT.FundamentalRecord(**row["record"])
        records.setdefault(record.ticker, []).append(record)
    return manifest, prices, PIT.FundamentalStore(records), {k: v for k, v in components.items() if k != "fundamentals"}


def weekly_grid(start, through, region):
    days = RC.sessions(start, str((pd.Timestamp(through) + pd.Timedelta(days=10)).date()), region)
    picked = pd.Series(days, index=days).groupby(days.to_period("W")).max()
    return [str(d.date()) for d in picked if str(d.date()) <= through]


def weekly_breadth(h, bench, date):
    cutoff = pd.Timestamp(date)
    def weekly(obj):
        # Completed W-FRI bins cannot change when future rows are appended.
        # Cache the bins once per immutable panel, then clip BEFORE tail/returns.
        if not hasattr(obj, "_alpha_weekly"):
            series = pd.Series(obj.close, index=pd.DatetimeIndex(obj.dates))
            obj._alpha_weekly = series.resample("W-FRI").last()
        return obj._alpha_weekly.loc[:cutoff]
    levels = pd.concat([weekly(h), weekly(bench)], axis=1).tail(53)
    if len(levels) < 53 or levels.isna().any().any():
        return None
    returns = levels.pct_change(fill_method=None).iloc[1:]
    return float((returns.iloc[:, 0] > returns.iloc[:, 1]).mean())


def price_features(h, pos, bench, date):
    if pos < 0 or h.dates[pos] > np.datetime64(date):
        raise PIT.LookAheadError("future price")
    result = {f"return{n}": HR.momentum_days(h, pos, n) for n in (21, 63, 126, 252)}
    for n in (21, 63, 126, 252):
        value = None
        if pos >= n and result[f"return{n}"] is not None:
            a, b = bench.position(h.dates[pos]), bench.position(h.dates[pos-n])
            if a >= 0 and b >= 0 and bench.dates[a] == h.dates[pos] and bench.dates[b] == h.dates[pos-n]:
                value = result[f"return{n}"] - (bench.close[a] / bench.close[b] - 1)
        result[f"relative{n}"] = value
    result.update(mom6=HR.momentum_6m(h, pos), mom121=HR.momentum_12_1(h, pos),
                  relative121=None, high52Distance=float(h.close[pos] / max(h.close[pos-251:pos+1]) - 1),
                  rsi14=HR.rsi_14(h, pos), ma200Distance=HR._ratio(h.close[pos], HR.moving_average(h, pos, 200)),
                  vol20=HR.volatility_window(h, pos, 20), vol60=HR.volatility_window(h, pos, 60),
                  vol252=HR.realized_vol_252(h, pos), downsideVol252=HR.downside_vol_252(h, pos),
                  maxDD252=HR.max_drawdown_252(h, pos), beta252=HR.beta_to(h, pos, bench),
                  volumeSurge5_60=HR.volume_surge(h, pos))
    if pos >= 272:
        a, b = bench.position(h.dates[pos-20]), bench.position(h.dates[pos-251])
        if a >= 0 and b >= 0 and bench.dates[a] == h.dates[pos-20] and bench.dates[b] == h.dates[pos-251]:
            result["relative121"] = result["mom121"] - (bench.close[a] / bench.close[b] - 1)
    return result


def build_matrix(prices, memberships, fundamentals, through, manifest):
    panel = HR.PricePanel(prices)
    rows, coverage = [], []
    for region in ("US", "KR"):
        bench = panel.get(BENCHMARKS[region])
        if bench is None:
            raise ValueError("benchmark unavailable: " + region)
        previous_year = None
        for date in weekly_grid(RC.ORIGIN, through, region):
            if date[:4] != previous_year:
                print(f"features {region} {date[:4]}", flush=True)
                previous_year = date[:4]
            snapshot = memberships[region].on(date)
            if snapshot is None:
                coverage.append(dict(region=region, date=date, expected=None, eligible=0, status="NO_PRIOR_SNAPSHOT"))
                continue
            count = 0
            for ticker in snapshot["members"]:
                if ticker in BENCHMARKS.values():
                    continue
                h = panel.get(ticker)
                pos = h.position(np.datetime64(date, "ns")) if h else -1
                if pos < 272 or (np.datetime64(date) - h.dates[pos]).astype("timedelta64[D]").astype(int) > HR.MAX_STALE_CALENDAR_DAYS:
                    continue
                values = price_features(h, pos, bench, date)
                if region == "US":
                    values["relativeStrengthBreadth52w"] = weekly_breadth(h, bench, date)
                else:
                    values["marketCap"] = snapshot["marketCaps"].get(ticker)
                pair = FA.resolve_filing_pair(fundamentals, ticker, region, date)
                current = pair.current
                values.update({f: current.fields.get(f) if current else None for f in FUNDAMENTAL})
                deltas = FA.compute_deltas(current, pair.previous) if pair.status == FA.OK else {}
                values.update({"delta_"+f: deltas.get(f) for f in FA.PRIMARY_FIELDS})
                row = dict(region=region, date=date, ticker=ticker, sector=None,
                           benchmark=BENCHMARKS[region], membershipDate=snapshot["date"],
                           membershipProvenance=snapshot.get("sourceCommit") or snapshot["sourceDigest"],
                           pitFundamentalDate=current.available_from if current else None,
                           pitPreviousFundamentalDate=pair.previous.available_from if pair.previous else None,
                           pitPriceDate=str(pd.Timestamp(h.dates[pos]).date()),
                           outcomeJoinId=f"{VERSION}:{region}:{date}:{ticker}", **values)
                rows.append(row)
                count += 1
            coverage.append(dict(region=region, date=date, expected=len(snapshot["members"]), eligible=count,
                                 status="DATED_SNAPSHOT_UNIVERSE"))
    frame = pd.DataFrame(rows).sort_values(["region", "date", "ticker"]).reset_index(drop=True)
    if frame.empty:
        raise ValueError("no feature observations")
    for region in ("US", "KR"):
        mask = frame.region.eq(region)
        for name in allowed_features(manifest, region):
            frame.loc[mask, "raw_"+name] = pd.to_numeric(frame.loc[mask, name], errors="coerce").replace([np.inf, -np.inf], np.nan)
            frame.loc[mask, name] = frame.loc[mask].groupby("date")["raw_"+name].rank(method="average", pct=True)
            frame.loc[mask, name+"__missing"] = frame.loc[mask, name].isna().astype(int)
    for item in manifest:
        sub = frame.loc[frame.region.eq(item["region"])]
        name = item["feature"]
        present = sub[name].notna() if item["eligible"] else pd.Series(False, index=sub.index)
        item["historicalCoverage"] = dict(rows=len(sub), present=int(present.sum()),
                                           ratio=float(present.mean()),
                                           firstDate=sub.loc[present, "date"].min() if present.any() else None,
                                           lastDate=sub.loc[present, "date"].max() if present.any() else None)
    return frame, coverage
