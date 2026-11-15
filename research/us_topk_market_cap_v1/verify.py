"""Verify lineage, eligibility denominators, self-financing and artifacts."""
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import gzip
import hashlib
import json

from research.us_topk_market_cap_v1.inputs import read, write


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(a, b):
    if abs(a - b) > 1e-10:
        raise ValueError(f"NUMERIC_RECONCILIATION_FAILED:{a}:{b}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--market-private", type=Path, required=True)
    ap.add_argument("--original-private", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--write-manifest", action="store_true")
    args = ap.parse_args()
    private, out = args.private, args.output
    originals = {}
    for label, root in [("original", args.original_private), ("corrected", args.market_private)]:
        manifest = read(root / "bundle-manifest.json")
        for name, record in manifest["files"].items():
            if (root / name).stat().st_size != record["bytes"] or sha(root / name) != record["sha256"]:
                raise ValueError("PRIVATE_ORIGINAL_CHANGED:" + name)
        originals[label] = {"verified_files": len(manifest["files"]), "manifest_sha256": sha(root / "bundle-manifest.json")}
    freeze = read(out / "rank-freeze-receipt.json")
    for name, expected in freeze["files"].items():
        if sha(private / name) != expected:
            raise ValueError("FROZEN_RANK_CHANGED")
    code_root = Path(__file__).resolve().parent
    actual_code = {p.name: sha(p) for p in sorted(code_root.glob("*.py"))}
    if read(out / "study-code-hashes.json") != actual_code:
        raise ValueError("REPORT_CODE_CHANGED_REGENERATE_REPORT")
    if sha(code_root / "protocol.json") != freeze["protocol_sha256"]:
        raise ValueError("PROTOCOL_CHANGED_AFTER_RANK_FREEZE")
    if sha(private / "signal-raw-prices.json.gz") != freeze["signal_raw_prices_sha256"]:
        raise ValueError("SIGNAL_PRICE_INPUT_CHANGED_AFTER_FREEZE")
    ranks = read(private / "rankings.json.gz")
    by_rank = {(r["pool"], r["k"], r["signal"]): r for r in ranks}
    for rank in ranks:
        if rank["status"].startswith("VERIFIED"):
            if rank["unbounded_missing_companies"] or len(rank["selected"]) != rank["k"]:
                raise ValueError("MISSING_COMPANY_SILENTLY_DROPPED")
            if len({s["cik"] for s in rank["selected"]}) != rank["k"]:
                raise ValueError("COMPANY_DOUBLE_COUNTED")
            if len({s["ticker"] for s in rank["selected"]}) != rank["k"]:
                raise ValueError("HELD_SECURITY_DOUBLE_COUNTED")
            for s in rank["selected"]:
                if not s["filed"] < rank["signal"] or s["share_end"] > rank["signal"]:
                    raise ValueError("FUTURE_SHARE_INFORMATION")
                if s["ticker"] != sorted(s["listed_classes"])[0]:
                    raise ValueError("HELD_CLASS_RULE_DRIFT")
    paths = {(r["ticker"], r["entry"], r["end"]): r for r in read(private / "path-cache.json.gz")}
    cohorts = read(private / "performance-cohorts.json.gz")
    for row in cohorts:
        if row["status"] != "COMPLETE":
            continue
        if row["end"] > "2026-11-13":
            raise ValueError("IMMATURE_COUNTED_COMPLETE")
        rank = by_rank[row["pool"], row["k"], row["signal"]]
        total = sum(s["cap"] for s in rank["selected"])
        terminal_value, stock_value = 0., 0.
        for security in rank["selected"]:
            path = paths[security["ticker"], row["entry"], row["end"]]
            if path["status"] != "COMPLETE":
                raise ValueError("INCOMPLETE_SELECTED_PATH_REPLACED")
            w = 1 / row["k"] if row["weighting"] == "equal_company" else security["cap"] / total
            value = w * (1 + path["gross"])
            if path.get("cash_terminal"):
                terminal_value += value
            else:
                stock_value += value
        expected = (stock_value * (1 - .00083) + terminal_value) / 1.0008 - 1
        close(expected, row["net_return"])
        spy = paths["SPY", row["entry"], row["end"]]
        close((1 + spy["gross"]) * .99917 / 1.0008 - 1, row["spy_net_return"])
        close(row["net_return"] - row["spy_net_return"], row["excess"])
    for group in read(out / "nav-segments.json"):
        previous_end = ""
        for segment in group["segments"]:
            if segment["first_entry"] <= previous_end:
                raise ValueError("NAV_GAP_STITCHED_OR_OVERLAPPED")
            previous_end = segment["last_mark"]
            close(segment["weekly"][-1]["nav"], segment["nav"])
            close(segment["daily"][-1]["nav"], segment["nav"])
            close(segment["daily"][-1]["spy_nav"], segment["spy_nav"])
    native = {r["signal"]: set(r["tickers"]) for r in read(args.market_private / "repaired-input-eligible-cohorts.json")["cohorts"]}
    grouped = defaultdict(list)
    for row in read(args.market_private / "holding-returns.json.gz"):
        if row["phase"] == "after" and row["ticker"] in native.get(row["signal"], set()) and row["end"] <= "2026-11-13":
            grouped[row["horizon"], row["signal"]].append(row)
    baseline_checks = {str(h): sum(all(r["status"] == "COMPLETE_ORIGINAL_RESEARCH_CONTRACT" for r in rows)
                                   for (horizon, _), rows in grouped.items() if horizon == h) for h in (126, 252)}
    if baseline_checks != {"126": 133, "252": 67}:
        raise ValueError("PREVIOUS_133_67_COVERAGE_NOT_REPRODUCED")
    # Verify every public source receipt against the cached object, not just HTTP.
    source_count = 0
    for receipt_file in ["sec-companyfacts-receipts.json", "extension-companyfacts-receipts.json"]:
        for r in read(private / receipt_file):
            if r["status"] == 200:
                blob = gzip.decompress((private / r["object"]).read_bytes())
                if hashlib.sha256(blob).hexdigest() != r["sha256"]:
                    raise ValueError("SEC_SOURCE_BYTES_CHANGED")
                data = json.loads(blob)
                if int(data["cik"]) != int(r["cik"]):
                    raise ValueError("SEC_ISSUER_CHANGED")
                source_count += 1
    for receipt in read(private / "sec-class-filings.json"):
        if receipt["status"] == 200:
            raw = gzip.decompress((private / "sec-filings" / (receipt["accn"] + ".htm.gz")).read_bytes())
            if hashlib.sha256(raw).hexdigest() != receipt["sha256"]:
                raise ValueError("SEC_CLASS_FILING_CHANGED")
    for receipt in read(out / "historical-extension-source-receipts.json"):
        if receipt["retrieved_status"] == 200:
            raw = gzip.decompress((private / "spy-extension" / (receipt["accession"] + ".gz")).read_bytes())
            if hashlib.sha256(raw).hexdigest() != receipt["retrieved_sha256"]:
                raise ValueError("SEC_ETF_SOURCE_CHANGED")
    execution = {"status": "PASS", "base_main": "4f4497bcc9e7f9369bf5529225585ad39b0d7725",
                 "verified_utc": datetime.now(timezone.utc).isoformat(), "private_originals": originals,
                 "frozen_rank_sha256": freeze["files"]["rankings.json.gz"],
                 "verified_sec_companyfacts_issuers": source_count,
                 "prior_native_all_holding_complete_week_checks": baseline_checks,
                 "complete_portfolio_cohort_rows": sum(r["status"] == "COMPLETE" for r in cohorts),
                 "official_full_index_primary_complete_weeks": 0,
                 "raw_prices_keys_and_private_rankings_published": False}
    manifest_path = out / "artifact-manifest.json"
    artifacts = {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()
                 and p.suffix in {".json", ".csv", ".md", ".png"}
                 and p.name not in {"artifact-manifest.json", "verification.json", "ci-status.json"}}
    if args.write_manifest:
        write(manifest_path, {"files": artifacts, "base_main": execution["base_main"]})
    elif read(manifest_path)["files"] != artifacts:
        raise ValueError("AGGREGATE_ARTIFACT_MANIFEST_CHANGED")
    write(out / "verification.json", execution)
    print(json.dumps(execution, indent=2))


if __name__ == "__main__":
    main()
