"""Audit the original US proxy's membership denominator without reading outcomes."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import pickle

import numpy as np
import pandas as pd

from research.us_selection_value_v1 import features as F
from research.us_rank_independent_check_v1.crosscheck import norm
from research.kr_us_replica_filter_v1.verify import HERE, PRIOR, ROOT, digest, save


def membership_audit(private, out):
    feature_path = private / "features.pkl"
    frame = pd.read_pickle(feature_path)
    frame["date"] = pd.to_datetime(frame.date)
    old_close_path = private / "close.pkl"
    with old_close_path.open("rb") as f:
        close = pickle.load(f)["close"]
    old_books_path = PRIOR / "results/US/funding-book-schedules.json.gz"
    with gzip.open(old_books_path, "rt") as f:
        baseline = json.load(f)["PASSIVE"]
    membership_path, sector_path, identity_path = (ROOT / x for x in (F.PILOT.MEMBERSHIP, F.PILOT.SECTORS, F.PILOT.IDENTITY))
    membership = F.RAF.MembershipSnapshots(json.loads(gzip.decompress(membership_path.read_bytes()))["snapshots"])
    sectorbook = F.CA.SectorBook(json.loads(gzip.decompress(sector_path.read_bytes()))["snapshots"])
    identity = json.loads(identity_path.read_text())["regions"]["US"]["identity"]
    malformed = {k.upper(): v["resolvedTo"] for k, v in identity["malformed"].items() if v.get("resolvedTo")}
    renames = {k: v["pricedBy"] for k, v in identity["renames"].items() if v.get("pricedBy")}
    for k, v in F.verified_class_links(close).items():
        renames.setdefault(k, v)
    bynorm = {norm(t): t for t in close}
    assert len(bynorm) == len(close.columns)
    rows, dates = [], []
    for date, cross in frame.groupby("date", sort=True):
        day = str(date.date())
        if day not in baseline:
            continue
        weights = baseline[day]
        by = cross.set_index("ticker")
        snap = membership.on(day)
        assert snap["date"] <= day
        seen, found = set(), set()
        counts = Counter()
        for symbol in sorted(snap["members"]):
            ticker = malformed.get(symbol.upper(), symbol)
            ticker = renames.get(ticker, ticker)
            ticker = bynorm.get(norm(ticker), ticker)
            sector, _ = sectorbook.lookup(snap, symbol)
            source = by.loc[ticker] if ticker in by.index else None
            feature_identity = str(source.identity) if source is not None else None
            cap_state = str(source.marketCapState) if source is not None else None
            quote = close.at[date, ticker] if ticker in close.columns else np.nan
            valid_price = np.isfinite(quote) and quote > 0
            if ticker in seen:
                reason = "DUPLICATE_PRICE_ID"
            elif ticker in weights:
                reason = "IN_REPLICA"
                found.add(ticker)
            elif not valid_price:
                reason = "NO_DECISION_QUOTE"
            elif source is None:
                reason = "NO_FEATURE_ROW_DESPITE_QUOTE"
            elif feature_identity not in {"MEMBERSHIP_CIK", "PIT_SINGLE_CIK"}:
                reason = "ORIGINAL_IDENTITY_RULE"
            else:
                reason = "NO_POSITIVE_CAP_PROXY"
            seen.add(ticker)
            counts[reason] += 1
            rows.append({"date": day, "snapshot": snap["date"], "member": symbol, "priceTicker": ticker,
                         "industry": sector, "reason": reason, "featureIdentity": feature_identity,
                         "capState": cap_state, "decisionPriceExists": bool(valid_price),
                         "proxyWeight": weights[ticker] if reason == "IN_REPLICA" else None})
        assert found == set(weights), (day, set(weights) - found)
        dates.append({"date":day, "membershipNames":len(snap["members"]), "proxyNames":len(weights),
                      "memberCountCoverage":len(weights)/len(snap["members"]), **counts})
    out.mkdir(parents=True, exist_ok=True)
    result = pd.DataFrame(rows)
    days = pd.DataFrame(dates).fillna(0)
    assert len(days) == len(baseline)
    result.to_csv(out / "candidate-support.csv.gz", index=False, compression={"method":"gzip","mtime":0})
    days.to_csv(out / "candidate-support-by-date.csv", index=False)
    reason = result.groupby(["reason"],sort=True).size()
    by_sector = result.groupby(["industry","reason"],dropna=False).size().unstack(fill_value=0)
    by_sector.to_csv(out / "candidate-support-by-sector.csv")
    summary = {
        "label":"ORIGINAL_MEMBERSHIP_NAME_DATES_NOT_FUND_DOLLAR_WEIGHTS",
        "decisionWeeks":len(days), "listedMemberDates":len(result),
        "memberCountCoverage":{"min":float(days.memberCountCoverage.min()),
                               "median":float(days.memberCountCoverage.median()),"max":float(days.memberCountCoverage.max())},
        "medianMemberCount":float(days.membershipNames.median()), "medianProxyCount":float(days.proxyNames.median()),
        "reasonCounts":{str(k):int(v) for k,v in reason.items()},
        "quotableMissingIsNotProofOfFreeFloatWeights":True,
        "noOutcomesRead":True,
        "inputSHA256":{str(p):digest(p) for p in [feature_path,old_close_path,old_books_path,membership_path,sector_path,identity_path]},
    }
    save(out / "candidate-support-summary.json",summary)
    print(json.dumps(summary,ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--private",type=Path,required=True)
    parser.add_argument("--out",type=Path,default=HERE/"results/US")
    args = parser.parse_args()
    membership_audit(args.private,args.out)


if __name__ == "__main__":
    main()
