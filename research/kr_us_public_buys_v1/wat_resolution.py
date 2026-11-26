"""Index the separately resolved and still-uncertain original US input flags."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.kr_us_public_buys_v1 import wat_sources
from research.kr_us_strategy_batch_v1 import us as batch

HERE = Path(__file__).resolve().parent


def condition_on_source_flags(frame, overlay):
    overlay_keys = set(zip(overlay.date, overlay.ticker, strict=True))
    flags = []
    for row in frame.itertuples(index=False):
        current_is_corrected = (row.date, row.ticker) in overlay_keys
        former_is_corrected = (row.previousDate, row.ticker) in overlay_keys
        split = json.loads(row.splitEvidencePrior91Days)
        factors = [x[1] for x in split]
        scale_match = any(.8 <= row.observedRatio/f <= 1.2 for f in factors)
        if row.inputExplanation == "SPLIT_PRICE_BASIS_RECONCILED":
            resolution = "AS_TRADED_PRICE_BASIS_MATCHES_SPLIT"
        elif row.field == "sharesForProxy" and scale_match:
            resolution = "CHANGE_MATCHES_SPLIT_FACTOR_PRIOR_91D"
        elif row.field in ("marketCap", "sharesForProxy") and (current_is_corrected or former_is_corrected):
            resolution = "VERIFIED_COVER_APPLIES_TO_AT_LEAST_ONE_SIDE"
        else:
            resolution = "UNRESOLVED_SEPARATE_SOURCE_OR_CLASS_REQUIRED"
        flags.append({"date": row.date, "ticker": row.ticker, "field": row.field,
                      "previousDate": row.previousDate, "proxyValueRatio": row.observedRatio,
                      "causeHint": row.inputExplanation, "officialCurrentCapCorrected": current_is_corrected,
                      "officialPreviousCapCorrected": former_is_corrected, "resolution": resolution})
    return pd.DataFrame(flags)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=HERE/"results/WAT")
    a = ap.parse_args(argv)
    overlay = pd.read_csv(a.out/"corrected-caps.csv", parse_dates=["date"])
    assert not overlay[["date", "ticker"]].duplicated().any()
    for r in overlay.itertuples(index=False):
        assert pd.Timestamp(r.acceptedET) < wat_sources.decision_close(r.date)
        assert pd.Timestamp(r.shareAsOf) <= r.date
        assert np.isclose(r.correctedMarketCap, r.confirmedActualShares*r.rawAsTradedPrice, rtol=1e-14)
    frame = pd.read_csv(a.out/"input-jump-audit.csv", parse_dates=["date", "previousDate"])
    table = condition_on_source_flags(frame, overlay)
    table.to_csv(a.out/"field-flags-resolution.csv", index=False)
    open_items = table.loc[table.resolution.str.startswith("UNRESOLVED")].copy()
    missing_total = pd.DataFrame({
        "date": pd.to_datetime(["2026-02-13", "2026-02-20"]), "ticker": "WAT",
        "field": "marketCap", "causeHint": "BDS_8K_ESTABLISHES_ISSUANCE_AMOUNT_ONLY",
        "resolution": "EXACT_POST_TRANSACTION_TOTAL_NOT_YET_PUBLIC"})
    pd.concat([open_items, missing_total], ignore_index=True).sort_values(["date", "ticker"]).to_csv(
        a.out/"unresolved-input-flags.csv", index=False)
    counts = table.groupby(["field", "resolution"]).size().reset_index(name="rows")
    batch.save(a.out/"input-resolution-summary.json", {
        "resolutionRows": counts.to_dict("records"),
        "dateTickerCorrections": len(overlay),
        "correctedTickerCount": overlay.ticker.nunique(),
        "correctionsByTicker": overlay.ticker.value_counts().sort_index().to_dict(),
        "unresolvedInputFlags": len(open_items),
        "separatelyUnresolvedPostMergerWeeks": 2})
    print(counts.to_string(index=False))


if __name__ == "__main__":
    main()
