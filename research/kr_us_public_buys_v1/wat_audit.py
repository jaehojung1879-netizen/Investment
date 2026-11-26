"""Input-only audits across the frozen US shares, prices, caps and book targets."""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import json
import pickle
from pathlib import Path
import time
from urllib.error import HTTPError, URLError

import numpy as np
import pandas as pd

from research.kr_us_public_buys_v1 import wat, wat_sources
from research.kr_us_replica_filter_v1 import us as baseline
from research.kr_us_strategy_batch_v1 import us as batch

HERE = Path(__file__).resolve().parent
FIELDS = ("sharesForProxy", "marketCap", "asTradedClose")
VALID_ID = ("MEMBERSHIP_CIK", "PIT_SINGLE_CIK")
SEC_QUANTITIES = (1e-6, 1e-3, 1e3, 1e6)
CANDIDATE_CLASSES_FOR_REVIEW = {"BRK-B", "GOOG", "GOOGL", "META", "PARA", "PSKY", "VTRS"}


def scale_like(x):
    return any(.8*expected <= x <= 1.2*expected for expected in SEC_QUANTITIES)


def load_splits(private, names):
    result = {}
    for n in sorted(names):
        path = private/"yahoo"/f"{n}.json.gz"
        if not path.is_file():
            continue
        data = json.loads(gzip.decompress(path.read_bytes()))
        if data.get("status") != "SERVED":
            continue
        result[n] = [(pd.Timestamp(stamp, unit="s").normalize(), a/b)
                     for stamp, a, b in data["splits"] if a > 0 and b > 0 and a != b]
    return result


def splits_between(splits, t, start, end):
    if pd.isna(start) or pd.isna(end):
        return []
    return [(day, factor) for day, factor in splits.get(t, []) if start < day <= end]


def field_flags(features, splits):
    rows = []
    ordered = features.sort_values(["ticker", "date"])
    for field in FIELDS:
        frame = ordered.loc[ordered[field].gt(0), ["date", "ticker", field, "sharesBasis",
           "sharesVisibleDay", "marketCapState", "identity"]].copy()
        g = frame.groupby("ticker")
        frame["previousValue"] = g[field].shift()
        frame["previousDate"] = g.date.shift()
        frame["previousSharesVisibleDay"] = g.sharesVisibleDay.shift()
        frame["observedRatio"] = frame[field]/frame.previousValue
        keep = (frame.date-frame.previousDate).dt.days.le(28) & ~frame.observedRatio.between(.2,5)
        for r in frame.loc[keep].assign(currentValue=frame.loc[keep, field]).itertuples(index=False):
            split = splits_between(splits, r.ticker, r.previousDate, r.date)
            wider_split = splits_between(splits, r.ticker, r.previousDate-pd.Timedelta(days=91), r.date)
            implied = str(r.sharesBasis).startswith("NET_INCOME_OVER_")
            recognized = abs(r.observedRatio*np.prod([factor for _, factor in split])-1) <= .2 if field == "asTradedClose" else False
            rows.append({"date": r.date, "ticker": r.ticker, "field": field, "previousDate": r.previousDate,
                         "observedRatio": r.observedRatio, "previousValue": r.previousValue,
                         "currentValue": r.currentValue, "unitScaleLike": scale_like(r.observedRatio),
                         "sharesBasis": r.sharesBasis, "sharesVisibleDay": r.sharesVisibleDay,
                         "previousSharesVisibleDay": r.previousSharesVisibleDay, "marketCapState": r.marketCapState,
                         "identity": r.identity, "splitInObservationInterval": json.dumps(
                             [[s.date().isoformat(), f] for s,f in split]),
                         "splitEvidencePrior91Days": json.dumps([[s.date().isoformat(), f] for s,f in wider_split]),
                         "inputExplanation": "SPLIT_PRICE_BASIS_RECONCILED" if recognized else
                             "POSSIBLE_SHARE_UPDATE_AFTER_SPLIT" if wider_split else
                             "UNVERIFIED_SHARE_UNIT_SCALE" if scale_like(r.observedRatio) else
                             "IMPLIED_FROM_NET_INCOME_AND_EPS" if implied else "UNVERIFIED"})
    return pd.DataFrame(rows)


def target_flags(schedules):
    out = []
    for name, bydate in schedules.items():
        weights = pd.DataFrame(bydate).T.fillna(0).sort_index()
        weights = weights.drop(columns=["SPY", "QQQ", "CASH"], errors="ignore")
        previous = weights.shift()
        for i, j in zip(*np.where((weights.sub(previous).abs().ge(.05)|weights.ge(.1)).to_numpy()), strict=True):
            d, t = weights.index[i], weights.columns[j]
            a, b = previous.iat[i,j], weights.iat[i,j]
            out.append({"date": d, "ticker": t, "book": name, "currentWeight": b,
                        "previousWeight": a, "weightDelta": b-a,
                        "deltaAtLeast5pp": abs(b-a) >= .05, "weightAtLeast10pct": b >= .1})
    return pd.DataFrame(out)


def split_audit(features, splits):
    rows = []
    positive = features.loc[features.sharesForProxy.gt(0) & features.asTradedClose.gt(0)].copy()
    positive = positive.loc[positive.ticker.isin({ticker for ticker, events in splits.items() if events})
                            | positive.marketCapState.eq("SPLIT_BETWEEN_FILING_AND_OBSERVATION")]
    positive["sharePublicTS"] = pd.to_datetime(positive.sharesVisibleDay)
    for r in positive.itertuples(index=False):
        events = splits_between(splits, r.ticker, r.sharePublicTS, r.date)
        cap_is_held = r.marketCapState == "SPLIT_BETWEEN_FILING_AND_OBSERVATION"
        if events or (isinstance(r.marketCapState, str) and "SPLIT" in r.marketCapState):
            cap_is_held = cap_is_held or (pd.isna(r.marketCap) and "SPLIT" in str(r.marketCapState))
            rows.append({"date": r.date, "ticker": r.ticker, "sharePublicDay": r.sharesVisibleDay,
                         "marketCapState": r.marketCapState, "positiveMarketCap": bool(r.marketCap > 0),
                         "localSplitEvents": json.dumps([[s.date().isoformat(), f] for s,f in events]),
                         "splitGuardApplied": cap_is_held})
    return pd.DataFrame(rows)


def public_cover_facts(directory, ciks, fetch=False):
    facts, receipts = {}, []
    for cik in sorted(ciks):
        file = directory/f"CIK{int(cik):010d}.json.gz"
        url = f"https://data.sec.gov/api/xbrl/companyfacts/{file.name.removesuffix('.gz')}"
        if not file.is_file() and fetch:
            try:
                raw = wat_sources.sec_get(url)
                if int(json.loads(raw).get("cik", -1)) != int(cik):
                    raise ValueError("SEC company facts CIK mismatch")
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(gzip.compress(raw, compresslevel=3, mtime=0))
            except (HTTPError, URLError, ValueError) as exc:
                receipts.append({"cik": cik, "status": "FETCH_FAILED", "reason": str(exc), "url": url})
                continue
            finally:
                time.sleep(.25)
        if not file.is_file():
            receipts.append({"cik": cik, "status": "MISSING", "url": url})
            continue
        raw = gzip.decompress(file.read_bytes())
        parsed = json.loads(raw)
        if int(parsed["cik"]) != int(cik):
            raise ValueError(f"CIK mismatch {cik}")
        tag = parsed.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {})
        grouped = defaultdict(set)
        for x in tag.get("units", {}).get("shares", []):
            if x["form"] in wat_sources.SEC_COVER_KINDS and x.get("end") and x.get("filed"):
                grouped[x["accn"]].add((x["end"], x["filed"], x["val"]))
        facts[cik] = {k: tuple(sorted(v)) for k, v in grouped.items()}
        receipts.append({"cik": cik, "status": "SEC_COMPANYFACTS_ISSUER_DEI_SCREEN_ONLY", "issuer": parsed.get("entityName"),
                         "sha256": wat_sources.sha(raw), "filingContexts": len(grouped),
                         "url": url})
    return facts, receipts


def filing_screen(private, cache, features, candidates, splits, fetch=False):
    with (private/"filings.pkl").open("rb") as f:
        raw = pickle.load(f)["raw"]
    filing_lookup = defaultdict(list)
    for name in sorted(candidates):
        for r in raw.get(name, []):
            if r.get("cik") and r.get("availableFrom"):
                filing_lookup[name,r["availableFrom"]].append(r)
    ciks = {rec["cik"] for rs in filing_lookup.values() for rec in rs}
    fact_by_issuer, receipts = public_cover_facts(cache/"companyfacts", ciks, fetch)
    records = []
    pool = features.loc[features.ticker.isin(candidates) & features.identity.isin(VALID_ID)
              & features.marketCap.gt(0) & features.sharesForProxy.gt(0)].sort_values(["date","ticker"])
    for row in pool.itertuples(index=False):
        d, t, visible = row.date, row.ticker, row.sharesVisibleDay
        if t in CANDIDATE_CLASSES_FOR_REVIEW:
            continue
        matches = filing_lookup[t,visible]
        sec = {r["accession"]:r for r in matches if r.get("accession") and r.get("cik")}
        if len(sec) != 1:
            continue
        acc, rec = next(iter(sec.items()))
        cik = rec["cik"]
        rows = fact_by_issuer.get(cik, {}).get(acc, ())
        if len(rows) != 1:
            continue
        share_asof, filed, qty = rows[0]
        official_ratio = qty / row.sharesForProxy
        if not scale_like(official_ratio):
            continue
        stamp = pd.Timestamp(rec["acceptedDate"], tz="America/New_York") if rec.get("acceptedDate") else pd.NaT
        before_cutoff = pd.notna(stamp) and stamp < wat_sources.decision_close(d)
        after_share_date = splits_between(splits, t, pd.Timestamp(share_asof), d)
        if not before_cutoff or filed != visible or qty < 1_000_000 or after_share_date:
            continue
        records.append({"date": d, "ticker": t, "previousShares": row.sharesForProxy,
                        "candidateShares": qty, "previousMarketCap": row.marketCap,
                        "rawAsTradedPrice": row.asTradedClose,
                        "shareAsOf": share_asof, "acceptedET": stamp.isoformat(),
                        "sourceId": acc, "sourceCik": cik, "secFilingDate": filed,
                        "oldShareBasis": row.sharesBasis, "candidateRatio": official_ratio})
    cols = ("date", "ticker", "previousShares", "candidateShares", "previousMarketCap", "rawAsTradedPrice",
            "shareAsOf", "acceptedET", "sourceId", "sourceCik", "secFilingDate", "oldShareBasis", "candidateRatio")
    return pd.DataFrame(records, columns=cols), receipts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--private", type=Path, default=Path("/workspace/batch-inputs/us"))
    ap.add_argument("--inputs", type=Path, default=Path("/workspace/exposure-inputs/us"))
    ap.add_argument("--cache", type=Path, default=Path("/workspace/wat-sec-inputs"))
    ap.add_argument("--out", type=Path, default=HERE/"results/WAT")
    ap.add_argument("--fetch-companyfacts", action="store_true")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    p, close, hashes, f = wat.load_inputs(a.private, a.inputs)
    del close
    splits = load_splits(a.private, f.ticker.unique())
    fields = field_flags(f, splits)
    bks = {"B": p["passive"], "U1_NATIVE": p["native"]["U1"], "U1_20": p["books"]["U1"],
           "U1_FUNDED": wat.nav.load_books(baseline.PRIOR/"results/US/funding-book-schedules.json.gz")["U1"]}
    targets = target_flags(bks)
    crossing = split_audit(f, splits)
    candidates = set(fields.ticker)|set(targets.ticker)
    candidates.discard("WAT")
    filing, receipts = filing_screen(a.private, a.cache, f, candidates, splits, a.fetch_companyfacts)
    fields.to_csv(a.out/"input-jump-audit.csv", index=False)
    baseline.csv(a.out/"target-jump-audit.csv.gz", targets)
    baseline.csv(a.out/"split-crossing-audit.csv.gz", crossing)
    filing.to_csv(a.out/"sec-fact-screen.csv", index=False)
    batch.save(a.out/"sec-fact-source-receipts.json", receipts)
    batch.save(a.out/"jump-audit-summary.json", {
        "positiveAdjacentInputFlagsByField": fields.field.value_counts().to_dict(),
        "flagsByFieldUniqueTicker": fields.groupby("field").ticker.nunique().to_dict(),
        "unresolvedFieldFlags": int(fields.inputExplanation.ne("SPLIT_PRICE_BASIS_RECONCILED").sum()),
        "localSplitCoverageTickers": len(splits), "splitCrossings": len(crossing),
        "splitCrossingsMarketCapPositive": int(crossing.positiveMarketCap.sum()),
        "weightFlagRows": targets.groupby("book").size().to_dict(),
        "weightJumpRows": targets.groupby("book").deltaAtLeast5pp.sum().to_dict(),
        "overweightRows": targets.groupby("book").weightAtLeast10pct.sum().to_dict(),
        "companyFactsScreenCandidates": len(filing),
        "inputSha256": hashes})


if __name__ == "__main__":
    main()
