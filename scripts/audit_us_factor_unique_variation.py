"""US factor reboot, Phase C: distinct characteristic variation, joint attrition, stale-filing and membership-age sensitivity.

    python scripts/audit_us_factor_unique_variation.py --workspace <dir> [--extract] [--limit-dates N]

Outcome-blind. Reuses the Phase 3 readiness audit's member funnel and feature builder (`scripts/audit_us_alpha_phase3_readiness.py`,
itself built on the multifactor and capital-allocation audits) on the SAME fixed sample: every 13th weekly signal date from
2013-01-04, S&P 500 members from the latest snapshot strictly before the date that pass the Phase 2 price and identity gates.
Inputs are pinned: Finnhub filings from signal-history 704d7db6 (blob-verified), replay-v16 sealed panels (manifest f0781292...).

Added to the Phase 3 feature set, with no new accounting arithmetic beyond one ratio:
* `assetGrowthPct`, `capexIntensityPct` from `pipeline.accounting_quality.derive_us_fields`, evaluated on the SAME filings
  `us_cash_profitability.features_as_of` treats as visible (strictly after max(availableFrom, acceptedDate)), current key and
  180-day stale rule;
* `revenueGrowthTTM` = sealed `finnhub_derive` TTM revenue at the current (year, stage) over the same stage one year earlier, minus 1,
  only when the earlier TTM is positive (the one new ratio, declared in the inventory).
No forward price, return, label, model or portfolio is read. Price features end at the signal date (the shared builder raises on a
future price).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import accounting_quality as AQ                     # noqa: E402
from pipeline import finnhub_derive as FD                         # noqa: E402
from pipeline import us_capital_allocation_coverage as C          # noqa: E402
from pipeline import us_cash_profitability as CP                  # noqa: E402
from pipeline import us_dual_benchmark_data as D                  # noqa: E402
from pipeline import us_factor_unique_variation as UV             # noqa: E402


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


P3 = _load("phase3_audit", "scripts/audit_us_alpha_phase3_readiness.py")
OUT = ROOT / "docs/us-readiness/us-factor-unique-variation-v1.json"
EXCLUDED_SECTORS = P3.EXCLUDED_SECTORS


def extra_accounting(records: list[dict], as_of: str) -> dict:
    """Investment and revenue-growth fields on exactly the filings the cash-profitability contract treats as current."""
    out = {"assetGrowthPct": None, "capexIntensityPct": None, "revenueGrowthTTM": None, "reportAgeDays": None}
    by_key = FD.index_filings(CP.visible_records(records, as_of))
    key = CP.current_key(by_key)
    if key is None:
        return out
    end = CP._day(by_key[key].get("periodEnd"))
    age = (CP._day(as_of) - end).days
    out["reportAgeDays"] = age
    if age > CP.MAX_REPORT_AGE_DAYS:
        return out
    fields, _ = AQ.derive_us_fields(by_key, key[0], key[1])
    out["assetGrowthPct"] = fields.get("assetGrowthPct")
    out["capexIntensityPct"] = fields.get("capexIntensityPct")
    now, _ = FD.trailing_twelve_months(by_key, key[0], key[1], "revenue")
    before, _ = FD.trailing_twelve_months(by_key, key[0] - 1, key[1], "revenue")
    if now is not None and before is not None and before > 0:
        out["revenueGrowthTTM"] = now / before - 1.0
    return out


def collect(workspace: Path, limit_dates: int | None):
    ctx, membership, dates = P3.DX.build_context(workspace)
    snapshot_dates = [(s or {}).get("date") for s in (membership.on(d) for d in dates)]
    sampled = dates[::P3.SAMPLE_EVERY_WEEKS]
    if limit_dates:
        sampled = sampled[::max(1, len(sampled) // limit_dates)][:limit_dates]
    raw = P3.raw_records(workspace, P3.A.FUNDAMENTALS_COMMIT)
    panel, store, identity = P3.OV.load_sealed()
    reader = D.SealedReader(ROOT)
    events = P3.MF.load_events(reader, reader.manifest())
    bench = panel.get("SPY")
    cache, rows, status = {}, [], Counter()
    for date in sampled:
        snapshot = membership.on(date)
        for raw_symbol in snapshot["members"]:
            member = C.classify_member(ctx, snapshot, date, raw_symbol)
            status[member.status] += 1
            if member.status in P3.PRICE_FAILURES:
                continue
            v = P3.row_values(panel, store, raw, events, cache, member, date, bench)
            if v is None:
                continue
            row = {"date": date, "ticker": member.ticker, "sector": member.sector,
                   "cashState": v["_state"]["cashOperatingProfitability"]}
            row.update({f: v.get(f) for f in UV.FEATURES if f in v})
            row.update(extra_accounting(raw.get(member.ticker, []), date))
            rows.append(row)
    return pd.DataFrame(rows), dates, snapshot_dates, sampled, status, identity


def build_report(frame, dates, snapshot_dates, sampled, status, identity) -> dict:
    for f in UV.FEATURES:
        if f not in frame:
            frame[f] = None
    classified = frame[frame["sector"] != "UNCLASSIFIED"]
    nonfin = classified[~classified["sector"].isin(EXCLUDED_SECTORS)].reset_index(drop=True)
    fin = classified[classified["sector"].isin(EXCLUDED_SECTORS)].reset_index(drop=True)
    cash_ok = nonfin["cashOperatingProfitability"].map(UV.finite)
    ages = nonfin["reportAgeDays"].astype(float)
    return {
        "id": "us-factor-unique-variation-v1", "contract": UV.CONTRACT,
        "evidenceClass": "OUTCOME_BLIND_FEATURE_STRUCTURE",
        "readsReturns": False, "readsLabels": False, "forwardPricesRead": False, "fitsPredictiveModels": False,
        "authorizes": "NOTHING",
        "meaning": ("R^2 here is how much of a characteristic's within-date ORDERING sector and the other families already carry. "
                    "It says nothing about whether the characteristic predicts a return; unique variation is a precondition for "
                    "incremental information, not evidence of it."),
        "inputs": {"fundamentalsCommit": P3.A.FUNDAMENTALS_COMMIT, "replayIdentity": identity,
                   "membership": str(P3.A.MEMBERSHIP.relative_to(ROOT)), "sectors": str(P3.A.SECTORS.relative_to(ROOT)),
                   "featureBuilders": ["scripts/audit_us_alpha_phase3_readiness.py:row_values",
                                       "pipeline/accounting_quality.py:derive_us_fields",
                                       "pipeline/finnhub_derive.py:trailing_twelve_months"]},
        "sampling": {"rule": "every %dth weekly signal date from %s (Phase 2's fixed rule)" % (P3.SAMPLE_EVERY_WEEKS, sampled[0]),
                     "dates": len(sampled), "firstDate": sampled[0], "lastDate": sampled[-1],
                     "memberDatesSeen": int(sum(status.values())), "statusCounts": dict(sorted(status.items())),
                     "eligibleMemberDates": int(len(frame)), "eligibleNonFinancialMemberDates": int(len(nonfin)),
                     "financialAndRealEstateMemberDates": int(len(fin)),
                     "survivorship": "priced S&P 500 members only; 212 departed identities have no panel (survivor-conditioned)"},
        "definitions": {"families": {k: list(v) for k, v in UV.FAMILIES.items()}, "representatives": UV.REPRESENTATIVES,
                        "minNamesPerDate": UV.MIN_NAMES, "attritionOrder": list(UV.ATTRITION_ORDER)},
        "availabilityNonFinancialPct": UV.availability(nonfin),
        "availabilityFinancialAndRealEstatePct": UV.availability(fin) if len(fin) else None,
        "uniqueVariationNonFinancial": UV.unique_variation(nonfin),
        "jointAttritionNonFinancial": UV.attrition(nonfin),
        "staleFilingSensitivity": {
            "feature": "cashOperatingProfitability",
            "productionRuleDays": CP.MAX_REPORT_AGE_DAYS,
            "availablePctIfStaleRuleWere": UV.stale_threshold_sensitivity(ages, cash_ok),
            "reportAgeDaysAmongAvailable": {"median": float(ages[cash_ok].median()),
                                            "p90": float(ages[cash_ok].quantile(.9))},
            "cashStateCounts": dict(Counter(nonfin["cashState"]).most_common()),
        },
        "membershipSnapshotAge": {**UV.snapshot_age(dates, snapshot_dates),
                                  "rule": "latest S&P 500 snapshot strictly before each of the weekly signal dates"},
        "notMeasuredHere": ["any relation between a characteristic and a later return",
                            "departed members without a price panel (survivor-conditioned sample)",
                            "verified market capitalisation, EV, gross profit, EBITDA (no PIT source or derivation)",
                            "13F, Form 4, short interest, consensus estimates (blocked or unprobed sources)"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--limit-dates", type=int)
    args = parser.parse_args(argv)
    if args.extract:
        P3.A.extract(args.workspace, P3.A.FUNDAMENTALS_COMMIT)
    report = build_report(*collect(args.workspace, args.limit_dates))
    text = json.dumps(report, indent=1, sort_keys=True, allow_nan=False, ensure_ascii=False,
                      default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n"
    if args.limit_dates:
        print(text[:6000])
        return 0
    OUT.write_text(text, encoding="utf-8")
    print("wrote", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
