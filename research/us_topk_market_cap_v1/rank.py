"""Freeze company rankings without importing or opening holding outcomes."""
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json

from pipeline import replay_calendar as RC
from research.us_topk_market_cap_v1.inputs import read, write

ROOT = Path(__file__).resolve().parents[2]
STANDARD = {"dei:EntityCommonStockSharesOutstanding", "us-gaap:CommonStockSharesOutstanding",
            "ifrs-full:NumberOfSharesOutstanding"}


def class_price(cik, member, held, listed):
    """Declared common-equity equivalents; never duplicate a company cap.

    Unquoted voting classes are valued at the economic equivalent listed
    common price. This is a reported-total-cap estimate, not an IWF market cap.
    """
    if cik == "1067983":  # BRK A converts to 1,500 B, same distributions.
        return held, 1500.0 if "ClassA" in member else 1.0
    if cik == "922621":  # ERIE B distribution entitlement is 150 A.
        return held, 150.0 if "ClassB" in member else 1.0
    if cik == "1652044":  # GOOGL A/B; GOOG C. B converts one-for-one A.
        return ("GOOG" if "ClassC" in member else "GOOGL"), 1.0
    if cik == "1754301":
        return ("FOX" if "ClassB" in member else "FOXA"), 1.0
    if cik == "1564708":
        return ("NWS" if "ClassB" in member else "NWSA"), 1.0
    if cik == "1467373" and "ClassX" in member:
        return held, 0.0  # Accenture X has votes, no dividend or capital rights.
    if cik == "1091667" and "ClassB" in member:
        return held, 0.0  # Charter B has votes, not the LLC exchangeable units.
    if cik in {"1381197", "1690820", "1973266"} and "ClassB" in member:
        # Up-C voting shares are not the underlying noncontrolling LLC units.
        # These require a company economic-interest reconciliation, not 1:1.
        raise ValueError("UP_C_ECONOMIC_COMPANY_CAP_UNRESOLVED")
    if len(listed) > 1:
        raise ValueError("LISTED_CLASS_PRICE_MAPPING_UNRESOLVED")
    return held, 1.0


def latest_facts(cik, day, standard, filings):
    candidates = []
    for fact in standard.get(cik, {}).get("facts", []):
        if fact["filed"] < day and fact["end"] <= day:
            candidates.append({"end": fact["end"], "filed": fact["filed"], "accn": fact["accn"],
                               "receipt": fact["receipt"], "parts": [{"value": fact["val"], "member": ""}],
                               "basis": fact["tag"], "priority": 1})
    for filing in filings.get(cik, []):
        if filing.get("status") != 200 or filing["filed"] >= day:
            continue
        grouped = defaultdict(list)
        for fact in filing["facts"]:
            tag = fact["tag"]
            if cik == "1403161":
                if tag != "v:SharesOutstandingAsConvertedBasis" or not fact["dims"]:
                    continue
                if not any("CommonClass" in d["member"] or "CommonStock" in d["member"]
                           for d in fact["dims"]):
                    continue
            elif tag != "dei:EntityCommonStockSharesOutstanding":
                continue
            if fact["end"] > day or any("ClassOfStockAxis" not in d["axis"] for d in fact["dims"]):
                continue
            member = "|".join(d["member"] for d in fact["dims"])
            grouped[fact["end"]].append({"value": fact["value"], "member": member})
        for end, parts in grouped.items():
            # One class/member exactly once; never sum a dimensional breakdown
            # with its own nondimensional aggregate.
            parts = list({p["member"]: p for p in parts}.values())
            if any(p["member"] for p in parts):
                parts = [p for p in parts if p["member"]]
            candidates.append({"end": end, "filed": filing["filed"], "accn": filing["accn"],
                               "receipt": filing["sha256"], "parts": parts,
                               "basis": "SEC_ORIGINAL_CLASS_COUNTS" if cik != "1403161" else "SEC_COMMON_AS_CONVERTED_NO_PREFERRED",
                               "priority": 2})
    # Newest reported measurement; earliest publication for the same basis/end.
    if not candidates:
        raise ValueError("ACTUAL_SHARES_OUTSTANDING_UNAVAILABLE")
    end = max(r["end"] for r in candidates)
    candidates = [r for r in candidates if r["end"] == end]
    priority = max(r["priority"] for r in candidates)
    return min((r for r in candidates if r["priority"] == priority), key=lambda r: (r["filed"], r["accn"]))


def capitalize(cik, day, symbols, prices, events, standard, filings):
    fact = latest_facts(cik, day, standard, filings)
    held = sorted(symbols)[0]
    if (datetime.fromisoformat(day) - datetime.fromisoformat(fact["end"])).days > 550:
        raise ValueError("ACTUAL_SHARE_MEASUREMENT_OLDER_THAN_550_DAYS")
    cap, parts = 0.0, []
    for part in fact["parts"]:
        ticker, conversion = class_price(cik, part["member"], held, symbols)
        if not conversion:
            parts.append({**part, "price_ticker": ticker, "conversion": 0.0, "cap": 0.0})
            continue
        price = prices.get(ticker, {}).get(day)
        if not price or price <= 0:
            raise ValueError("SIGNAL_AS_TRADED_CLOSE_UNAVAILABLE:" + ticker)
        split = 1.0
        # Reporting-source end before a known split: carry share count forward
        # on the same as-traded basis as price. No weighted-average EPS shares.
        for date, event in events.get(ticker, {}).items():
            if fact["end"] < date <= day:
                split *= event.get("split") or 1.0
        value = part["value"] * split * conversion * price
        cap += value
        parts.append({**part, "price_ticker": ticker, "conversion": conversion,
                      "split_factor": split, "raw_close": price, "cap": value})
    if not cap > 0:
        raise ValueError("NONPOSITIVE_CAP")
    return {"cik": cik, "ticker": held, "listed_classes": sorted(symbols), "cap": cap,
            "cap_basis": "REPORTED_TOTAL_COMMON_CAP_ESTIMATE_NOT_INDEX_FLOAT",
            "share_end": fact["end"], "filed": fact["filed"], "accn": fact["accn"],
            "receipt": fact["receipt"], "parts": parts, "share_basis": fact["basis"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--market-private", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    prices = read(args.private / "signal-raw-prices.json.gz")
    standard = read(args.private / "shares-standard.json.gz")
    events = read(args.market_private / "baseline-events.json.gz")
    class_filings = defaultdict(list)
    for row in read(args.private / "sec-class-filings.json"):
        class_filings[str(int(row["cik"]))].append(row)
    membership = read(ROOT / "research_specs/alpha-opportunity-model-v1-us-membership.json.gz")["snapshots"]
    sectors = {s["date"]: s for s in read(ROOT / "data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz")["snapshots"]}
    dates = [s["date"] for s in membership]
    calendar = [str(d.date()) for d in RC.sessions("2013-01-01", "2028-01-14", "US")]
    weeks = defaultdict(list)
    for day in calendar:
        if "2013-01-01" <= day <= "2026-09-13":
            weeks[datetime.fromisoformat(day).isocalendar()[:2]].append(day)
    signals = [max(ds) for ds in weeks.values() if max(ds) <= "2026-09-11"]
    financial = {r["signal"]: set(r["tickers"]) for r in read(args.market_private / "repaired-input-eligible-cohorts.json")["cohorts"]}
    annual, frozen, missing = Counter(), [], []
    for signal in signals:
        pos = bisect_left(dates, signal) - 1
        if pos < 0:
            continue
        snap = membership[pos]
        meta = sectors[snap["date"]]
        companies, unavailable = defaultdict(list), []
        for symbol in snap["members"]:
            row = meta["rows"].get(symbol, meta["rows"].get(symbol.replace("-", "."), {}))
            cik = row.get("cik")
            if not cik:
                unavailable.append({"ticker": symbol, "reason": "DATED_ISSUER_CIK_MISSING"})
            else:
                companies[str(int(cik))].append(symbol)
        caps = []
        for cik, symbols in companies.items():
            try:
                record = capitalize(cik, signal, symbols, prices, events, standard, class_filings)
                sector_row = meta["rows"].get(record["ticker"], meta["rows"].get(record["ticker"].replace("-", "."), {}))
                record["sector"] = sector_row.get("sector", "Unclassified")
                caps.append(record)
            except ValueError as exc:
                unavailable.append({"cik": cik, "ticker": sorted(symbols)[0],
                                    "classes": symbols, "reason": str(exc)})
        caps.sort(key=lambda r: (-r["cap"], r["cik"]))
        entry_index = bisect_left(calendar, signal) + 1
        for pool in ("OBSERVED_SP500_SNAPSHOT", "CORRECTED_FINANCIAL_POOL"):
            if pool == "CORRECTED_FINANCIAL_POOL" and signal not in financial:
                continue
            pool_names = financial.get(signal, set()) if pool == "CORRECTED_FINANCIAL_POOL" else None
            pool_caps = [r for r in caps if pool_names is None or any(t in pool_names for t in r["listed_classes"])]
            pool_missing = [r for r in unavailable if pool_names is None or r["ticker"] in pool_names
                            or any(t in pool_names for t in r.get("classes", []))]
            if pool_names is not None:
                represented = {t for r in pool_caps for t in r["listed_classes"]} | {r["ticker"] for r in pool_missing}
                for ticker in sorted(pool_names - represented):
                    pool_missing.append({"ticker": ticker, "reason": "CORRECTED_POOL_SYMBOL_CLASS_MAPPING_MISSING"})
            for k in (5, 10, 100):
                status = "VERIFIED_REPORTED_CAP_ON_OBSERVED_UNIVERSE"
                if pool_missing:
                    status = "BOUNDARY_UNCERTAIN_UNBOUNDED_MISSING_CAP_OR_IDENTITY"
                elif len(pool_caps) < k:
                    status = "FEWER_THAN_K_COMPANIES_IN_POOL"
                selected = pool_caps[:k]
                row = {"signal": signal, "entry": calendar[entry_index], "pool": pool, "k": k,
                       "snapshot": snap["date"], "snapshot_age_days": (datetime.fromisoformat(signal) - datetime.fromisoformat(snap["date"])).days,
                       "universe_securities": len(snap["members"]) if pool_names is None else len(pool_names),
                       "companies_with_caps": len(pool_caps), "unbounded_missing_companies": len(pool_missing),
                       "status": status, "primary_index_float_rank_status": "UNAVAILABLE_NO_IWF_NO_OFFICIAL_WEEKLY_CHANGE_FILE",
                       "selected": selected,
                       "cutoff_cap": selected[-1]["cap"] if len(selected) == k else None,
                       "exits": {str(h): calendar[entry_index + h] for h in (126, 252)}}
                frozen.append(row)
                annual[(signal[:4], pool, k, status)] += 1
            missing.extend({"signal": signal, "pool": pool, **r} for r in pool_missing)
    args.output.mkdir(exist_ok=True)
    # This receipt is written before any forward holding-return file is opened.
    files = {"rankings.json.gz": write(args.private / "rankings.json.gz", frozen),
             "ranking-missingness.json.gz": write(args.private / "ranking-missingness.json.gz", missing)}
    receipt = {"study": "US_TOPK_COMPANY_MARKET_CAP_V1", "phase": "RANKS_FROZEN_BEFORE_FORWARD_LABELS",
               "created_utc": datetime.now(timezone.utc).isoformat(), "files": files,
               "protocol_sha256": hashlib.sha256((ROOT / "research/us_topk_market_cap_v1/protocol.json").read_bytes()).hexdigest(),
               "signal_raw_prices_sha256": hashlib.sha256((args.private / "signal-raw-prices.json.gz").read_bytes()).hexdigest(),
               "annual": [{"year": y, "pool": p, "k": k, "status": s, "weeks": n}
                          for (y, p, k, s), n in sorted(annual.items())]}
    write(args.output / "rank-freeze-receipt.json", receipt)
    print(json.dumps({"frozen_rank_rows": len(frozen), "verified_rows": sum(r["status"].startswith("VERIFIED") for r in frozen),
                      "missing_reasons": dict(Counter(r["reason"] for r in missing))}, indent=2))


if __name__ == "__main__":
    main()
