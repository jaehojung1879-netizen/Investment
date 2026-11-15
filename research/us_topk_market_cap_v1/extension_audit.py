"""Input-only historical samples; no outcome or ETF-to-company-cap inference."""
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import argparse
import csv
import gzip
import json
import re

from pipeline import replay_calendar as RC
from research.us_topk_market_cap_v1.inputs import read, write

YEARS = {"2018", "2020", "2022"}


def canonical(name):
    value = name.lower().replace("&", "and")
    value = re.sub(r"\bclass\s+[a-z0-9-]+\b.*", "", value)
    words = re.findall(r"[a-z0-9]+", value)
    while words and words[-1] in {"inc", "incorporated", "corp", "corporation", "co", "company", "plc", "ltd", "limited"}:
        words.pop()
    return " ".join(words)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--uploaded", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    private, uploaded, out = args.private, args.uploaded, args.output
    receipts = read(private / "sec-companyfacts-receipts.json") + read(private / "extension-companyfacts-receipts.json")
    shares = {}
    for receipt in receipts:
        if receipt["status"] != 200:
            continue
        data = read(private / receipt["object"])
        facts = []
        for ns, tag in [("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding"),
                        ("ifrs-full", "NumberOfSharesOutstanding")]:
            for fact in data["facts"].get(ns, {}).get(tag, {}).get("units", {}).get("shares", []):
                if fact.get("start") or fact["val"] <= 0:
                    continue
                facts.append({**fact, "tag": ns + ":" + tag})
        first = {}
        for fact in sorted(facts, key=lambda r: (r["filed"], r["accn"])):
            first.setdefault((fact["end"], fact["tag"]), fact)
        shares[str(int(data["cik"]))] = list(first.values())
    prices = read(private / "signal-raw-prices.json.gz")
    calendar = [str(d.date()) for d in RC.sessions("2012-01-01", "2023-01-31", "US")]
    cache = {}

    def measurement(cik, day):
        key = cik, day
        if key not in cache:
            eligible = [r for r in shares.get(cik, []) if r["filed"] < day and r["end"] <= day]
            fact = max(eligible, key=lambda r: (r["end"], r["filed"])) if eligible else None
            if fact and (datetime.fromisoformat(day) - datetime.fromisoformat(fact["end"])).days > 550:
                fact = None
            cache[key] = fact
        return cache[key]

    by_week, gaps = defaultdict(Counter), []
    with gzip.open(uploaded / "historical-member-weeks.jsonl.gz", "rt") as stream:
        for line in stream:
            row = json.loads(line)
            day = row["date"]
            if day[:4] not in YEARS:
                continue
            count = by_week[day]
            count["members"] += 1
            cik = str(int(row["cik"])) if row.get("cik") else None
            ticker = row["ticker"]
            raw = prices.get(ticker, {}).get(day)
            fact = measurement(cik, day) if cik else None
            count["has_candidate_cik"] += bool(cik)
            count["has_signal_raw_quote"] += bool(raw)
            count["has_visible_actual_share_fact"] += bool(fact)
            count["candidate_plus_raw_quote_plus_share_fact"] += bool(cik and raw and fact)
            count["missing_candidate_cik"] += not bool(cik)
            count["missing_raw_quote"] += not bool(raw)
            count["missing_actual_share_fact"] += not bool(fact)
            for field, missing in [("dated_security_class_identity", not cik), ("as_traded_signal_close", not raw),
                                   ("visible_actual_common_shares", not fact)]:
                if missing:
                    gaps.append({"signal": day, "ticker": ticker, "field": field,
                                 "candidate_status": row["issuer_status"]})
    weekly = [{"signal": d, **c, "verified_company_cap_rank": False,
               "note": "Candidate CIK/name links do not verify dated security class; no IWF or complete index event ledger"}
              for d, c in sorted(by_week.items())]
    with (out / "historical-extension-weekly-coverage.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(weekly[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(weekly)
    write(private / "historical-extension-gaps.json.gz", gaps)
    annual = []
    for year in sorted(YEARS):
        rows = [r for r in weekly if r["signal"].startswith(year)]
        for k in (5, 10, 100):
            annual.append({"year": year, "k": k, "signal_weeks": len(rows), "verified_primary_float_rank_weeks": 0,
                "verified_reported_company_cap_rank_weeks": 0, "financial_pool_performance_weeks": 0,
                "candidate_cap_support_at_least_k_weeks": sum(r["candidate_plus_raw_quote_plus_share_fact"] >= k for r in rows),
                "mean_member_count": sum(r["members"] for r in rows) / len(rows),
                "mean_candidate_cik_count": sum(r["has_candidate_cik"] for r in rows) / len(rows),
                "mean_raw_quote_count": sum(r["has_signal_raw_quote"] for r in rows) / len(rows),
                "mean_joint_candidate_share_quote_count": sum(r["candidate_plus_raw_quote_plus_share_fact"] for r in rows) / len(rows),
                "weeks_opened_by_quotes_only": sum(r["missing_candidate_cik"] == 0 and r["missing_actual_share_fact"] == 0 for r in rows),
                "weeks_opened_by_identity_only": sum(r["missing_raw_quote"] == 0 and r["missing_actual_share_fact"] == 0 for r in rows),
                "weeks_opened_by_shares_only": sum(r["missing_candidate_cik"] == 0 and r["missing_raw_quote"] == 0 for r in rows),
                "largest_blocker": "DATED_SECURITY_CLASS_AND_COMPLETE_INDEX_CONSTITUENT_EVENTS; THEN_UNBOUNDED_MISSING_COMPANY_CAPS",
                "next_single_source": "Existing-entitlement dated S&P constituent/company/security/IWF-and-cap export for every signal week; no new paid purchase",
                "rank_week_upper_bound_if_complete_next_source_supplied": len(rows),
                "performance_opening_not_guaranteed": "Selected security total-return paths and terminal rights must then pass independently"})
    write(out / "historical-extension-annual.json", annual)
    # Actual filing samples: SEC fund-position quotes vs cached raw quotes.
    candidates = read(uploaded / "historical-issuer-candidates.json")
    source_receipts = read(out / "historical-extension-source-receipts.json")
    samples, boundary = [], []
    discrepancies = []
    for receipt in source_receipts:
        day = receipt["as_of"]
        if receipt.get("retrieved_status") != 200:
            continue
        priceday = calendar[bisect_left(calendar, day + "x") - 1]
        active = [r for r in candidates if r["first_week"] <= priceday <= r["last_week"]]
        names = defaultdict(list)
        for r in active:
            names[canonical(r["name"])].append(r)
        holdings = read(private / "spy-extension" / (receipt["accession"] + "-holdings.json.gz"))
        counts, companies = Counter(), defaultdict(lambda: {"fund_value": 0., "unresolved_fields": set()})
        for row in holdings:
            if row.get("assetCat") != "EC":
                continue
            counts["equity_rows"] += 1
            possible = names.get(canonical(row["name"]), [])
            ciks = {str(int(r["cik"])) for r in possible}
            if len(ciks) != 1:
                counts["no_unique_name_candidate"] += 1
                cik, ticker = None, None
            else:
                counts["unique_name_candidate_rows"] += 1
                cik = next(iter(ciks))
                ticker = sorted({r["ticker"] for r in possible})[0]
            key = cik or row["name"]
            companies[key]["fund_value"] += float(row["valUSD"])
            if not cik:
                companies[key]["unresolved_fields"].add("issuer_security_link")
                continue
            raw = prices.get(ticker, {}).get(priceday)
            fact = measurement(cik, priceday)
            if not raw:
                companies[key]["unresolved_fields"].add("raw_close")
            if not fact:
                companies[key]["unresolved_fields"].add("actual_common_share_count")
            if raw and fact:
                counts["candidate_share_raw_support_rows"] += 1
            # Only unique single-symbol candidate matches; dual-class ticker
            # ambiguity is not accepted as quote confirmation.
            if raw and len({r["ticker"] for r in possible}) == 1 and row.get("balance") and float(row["balance"]) > 0:
                implied = float(row["valUSD"]) / float(row["balance"])
                deviation = abs(implied / raw - 1)
                counts["quote_comparisons"] += 1
                counts["quote_agrees_within_0_1pct"] += deviation <= .001
                if deviation > .001:
                    discrepancies.append({"as_of": day, "quote_date": priceday, "ticker": ticker,
                        "issuer_name": row["name"], "field": "SPY_fund_value_per_share_vs_cached_raw_close",
                        "relative_difference": deviation, "status": "UNRECONCILED_NOT_ADMITTED"})
        ordered = sorted(companies.values(), key=lambda r: -r["fund_value"])
        for k in (5, 10, 100):
            window = ordered[max(0, k - 3):k + 2]
            boundary.append({"as_of": day, "filed": receipt["filed"], "k": k,
                "basis": "ETF_POSITION_VALUE_BOUNDARY_DIAGNOSTIC_NOT_COMPANY_CAP_RANK",
                "companies_in_boundary_window": len(window),
                "with_unresolved_input_fields": sum(bool(r["unresolved_fields"]) for r in window),
                "missing_field_counts": dict(Counter(f for r in window for f in r["unresolved_fields"])),
                "new_verified_weekly_topk_ranks": 0})
        samples.append({"as_of": day, "filed": receipt["filed"], "quote_date": priceday, **counts,
                        "source_sha_matches_prior": receipt["matches_prior_receipt"],
                        "admission": "NAME_CANDIDATES_AND_ETF_QUOTE_CROSSCHECK_ONLY; NO_FUND_WEIGHT_AS_COMPANY_CAP"})
    write(out / "historical-extension-sample-checks.json", samples)
    write(out / "historical-extension-boundaries.json", boundary)
    write(out / "historical-extension-quote-discrepancies.json", discrepancies)
    print(json.dumps({"annual": annual, "samples": samples}, indent=2))


if __name__ == "__main__":
    main()
