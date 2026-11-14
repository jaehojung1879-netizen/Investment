"""Export field/date gaps, identity links and outcome-free missingness counts."""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import csv
import gzip
import json
from pathlib import Path

from pipeline import replay_calendar as RC
from research.us_historical_market_recovery_v1.audit import read, canonical, digest
from research.us_historical_market_recovery_v1.engine import ranges


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uploaded-dir", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    out, private, uploaded = args.output, args.private_root, args.uploaded_dir
    result = read(out / "results.json")
    requests = {r["audit_identifier"]: r for r in read(uploaded / "us-212-market-data-request.json")}
    inventory = {r["audit_identifier"]: r for r in result["inventory"]}
    docs = read(private / "identity-sources/public-receipts.json")
    supplied = read(uploaded / "public-corporate-event-evidence.json")
    # Metadata only. Every actual raw source remains in the private bundle.
    (out / "public-source-receipts.json").write_bytes(canonical({"downloaded": docs, "supplied": supplied,
        "uploaded_sha256": read(uploaded / "provenance.json"),
        "account_collection_runs": [43538004827, 43539000217, 43540781549]}))
    supplemental = {}
    for name in ("last-gap-public-charts.json", "last-gap-account-attempts.json"):
        if (private / name).exists():
            supplemental[name] = read(private / name)
    (out / "supplemental-source-attempts.json").write_bytes(canonical(supplemental))
    links = []
    for ticker, request in requests.items():
        evidence = result["source_receipts"].get(ticker)
        event = inventory[ticker]["event"]
        links.append({"audit_identifier": ticker, "security_audit_id": request["security_audit_id"],
          "issuer_name_candidates": request["names"], "existing_dated_ciks": request["existing_dated_ciks"],
          "sec_name_cik_candidates": request["sec_exact_name_cik_candidates"],
          "class_link": evidence, "event_issuer_link": event if event.get("event_date") else None,
          "permanent_security_id": None,
          "status": "DATED_DOCUMENT_COMMON_CLASS_LINK_AUTHOR_VALIDATED" if evidence else "SECURITY_CLASS_LINK_UNRESOLVED",
          "restriction": "CIK identifies issuer, not a permanent share-class identifier; profile name is insufficient"})
    controls = [r for r in supplied if r["audit_identifier"] not in requests]
    (out / "security-lineage.json").write_bytes(canonical({"collection_security_links": links,
        "outside_cohort_identity_controls": controls,
        "do_not_join": ["SE Spectra CIK1373835 != Sea Ltd IPO2017-10-20",
          "AGN CIK850693 != Allergan plc CIK1578845",
          "BTU old common cancelled2017-04-03 != reissued BTU",
          "CHK old common cancelled2021-02-09 != new equity",
          "VIAC post2019 CIK813828 ClassB -> PARA != old Viacom CIK1339947 or ClassA VIACA/PARAA",
          "FRC/SIVB/SBNY bank resolutions do not establish parent/common payoff or successor shares"]}))
    gap_rows = []
    for ticker, r in inventory.items():
        providers = "YAHOO_CHART;FMP_EOD;FINNHUB_PROFILE2;FINNHUB_PRICE_DIV_SPLIT_CONTROL_403;PINNED_PUBLIC_CACHE"
        base = {"ticker": ticker, "security_audit_id": r["security_audit_id"], "providers_checked": providers}
        for date_range in r["missing_date_ranges"]:
            gap_rows.append({**base, "field": "daily_OHLCV_candidate_dates", **date_range,
              "reason": "NO_CANDIDATE_PRICE_DATE; a terminal event may require consideration instead"})
        for blocker in r["blockers"]:
            if blocker == "PRICE_DATES_MISSING":
                continue
            field = {"DATED_PRICE_SECURITY_AND_SHARE_CLASS_UNVERIFIED": "dated_security_id_share_class",
              "DIVIDEND_SPLIT_BASIS_OR_LINEAGE_UNVERIFIED": "cash_dividend_ex_pay_currency_split_and_price_basis",
              "TERMINAL_OR_SUCCESSOR_CONTRACT_NEEDS_WINDOW_REVIEW": "last_trade_terminal_cash_stock_CVR_or_OTC_link"}[blocker]
            gap_rows.append({**base, "field": field, "from": r["requested_from"],
                "through": r["requested_through"], "reason": blocker})
        if r["requested_followup_after_as_of"]:
            gap_rows.append({**base, "field": "future_followup", "from": "2026-11-14",
                "through": r["requested_followup_after_as_of"], "reason": "NOT_YET_OBSERVABLE; do not backfill"})
    labels = read(private / "holding-returns.json.gz")
    calendar = [str(d.date()) for d in RC.sessions("2011-01-03", "2028-01-14", "US")]
    holding_gaps = defaultdict(list)
    primary_missing = defaultdict(Counter)
    complete = "COMPLETE_ORIGINAL_RESEARCH_CONTRACT"
    newly_complete = defaultdict(Counter)
    paired = defaultdict(dict)
    for r in labels:
        paired[r["horizon"], r["signal"], r["ticker"]][r["phase"]] = r["status"]
        if r["phase"] == "after" and r["status"] != complete:
            holding_gaps[r["ticker"], r["horizon"], r["status"]].append(r)
            kind = inventory.get(r["ticker"], {}).get("event", {}).get("event", "ORIGINAL_UNIVERSE_OTHER")
            primary_missing[r["signal"][:4]][kind + ":" + r["status"]] += 1
    for (ticker, horizon, reason), rows in sorted(holding_gaps.items()):
        base = {"ticker": ticker, "security_audit_id": requests.get(ticker, {}).get("security_audit_id", "ORIGINAL_UNIVERSE"),
          "field": "H" + str(horizon) + "_holding_path", "from": min(r["entry"] for r in rows),
          "through": max(r["end"] for r in rows), "reason": reason + ";count=" + str(len(rows)),
          "providers_checked": "ORIGINAL_REPLAY_V16;NEW_PRIVATE_SOURCE_PACKETS;SPY_SSGA"}
        missing = {d for r in rows for d in r.get("missing_security_sessions", [])}
        if missing:
            gap_rows.extend({**base, **dates, "field": "H" + str(horizon) + "_missing_daily_OHLCV"} for dates in ranges(missing, calendar))
        else:
            gap_rows.append(base)
        benchmark_missing = {d for r in rows for d in r.get("missing_benchmark_sessions", [])}
        gap_rows.extend({**base, **dates, "ticker": "SPY", "field": "H" + str(horizon) + "_benchmark_daily_price"} for dates in ranges(benchmark_missing, calendar))
    for (horizon, _, ticker), states in paired.items():
        if states["after"] == complete and states["before"] != complete:
            newly_complete[str(horizon)][ticker] += 1
    with (out / "remaining-gaps.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ticker", "security_audit_id", "field", "from", "through", "reason", "providers_checked"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(gap_rows)
    # Supplemental member-week grid is NEVER mixed into primary pilot eligibility.
    historical = defaultdict(lambda: {"target_member_weeks": 0, "accounting_all_four_candidate": 0,
                       "security_class_unresolved_member_weeks": 0, "known_event_crossings": Counter()})
    seen = set()
    with gzip.open(uploaded / "historical-member-weeks.jsonl.gz", "rt") as f:
        for line in f:
            r = json.loads(line)
            ticker, day = r["ticker"], r["date"]
            if ticker not in inventory or (ticker, day) in seen:
                continue
            seen.add((ticker, day))
            bucket = historical[day[:4]]
            bucket["target_member_weeks"] += 1
            bucket["accounting_all_four_candidate"] += bool(r.get("all_four"))
            bucket["security_class_unresolved_member_weeks"] += ticker not in result["source_receipts"]
            event = inventory[ticker]["event"]
            if not event.get("event_date") or event["event"] in {"SAME_COMMON_STOCK_RENAME", "CLASS_B_SYMBOL_CHANGE"}:
                continue
            pos = bisect_left(calendar, day) + 1
            for horizon in (126, 252):
                if calendar[pos] <= event["event_date"] <= calendar[pos + horizon]:
                    bucket["known_event_crossings"]["H" + str(horizon) + ":" + event["event"]] += 1
    summary = {"primary_unresolved_by_signal_year_and_event": dict(primary_missing),
      "newly_complete_by_identifier": dict(newly_complete),
      "historical_2013_2022_member_week_diagnostic": dict(historical),
      "diagnostic_restriction": "Historical member grid retains sector/ineligible records and issuer candidates; not the pilot H denominator or admission",
      "unknown_event_identifiers": sum(r["event"]["event"] == "UNCLASSIFIED_NOT_ASSUMED_DELISTED" for r in inventory.values()),
      "primary_2013_2022_eligible_cohorts": 0,
      "unresolved_holdings": sum(len(v) for v in holding_gaps.values()), "gap_rows": len(gap_rows),
      "request_file_sha256": digest((uploaded / "us-212-market-data-request.json").read_bytes())}
    event_years = defaultdict(Counter)
    for r in inventory.values():
        event = r["event"]
        if event.get("event_date"):
            key = event["event"] + (":PRICE_PACKET_VALIDATED" if r["source_acquired"] else ":PRICE_PACKET_NOT_VALIDATED")
            event_years[event["event_date"][:4]][key] += 1
    summary["known_events_by_effective_year_and_price_evidence"] = dict(event_years)
    cohorts = defaultdict(list)
    for r in labels:
        cohorts[r["horizon"], r["phase"], r["signal"]].append(r["status"])
    complete_dates = Counter()
    for (horizon, phase, _), states in cohorts.items():
        if all(s == complete for s in states):
            complete_dates["H" + str(horizon) + ":" + phase] += 1
    summary["complete_fixed_union_cohort_dates"] = dict(complete_dates)
    (out / "missingness-by-year.json").write_bytes(canonical(summary))
    print(json.dumps({k: v for k, v in summary.items() if k not in ("primary_unresolved_by_signal_year_and_event", "historical_2013_2022_member_week_diagnostic")}, indent=2))


if __name__ == "__main__":
    main()
