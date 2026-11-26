"""Recover frozen US inputs and capture a separately labelled Yahoo vintage.

This module prepares inputs only. It never calculates a strategy return, chooses
a portfolio, or changes the original feature admission rules. Vendor responses
and security-level inputs stay in the supplied directory outside the repository.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import pickle
import shutil
import subprocess
import urllib.request

import numpy as np
import pandas as pd

from pipeline.us_dual_benchmark_data import OBJECTS, SOURCE_COMMIT, SealedReader
from research.us_selection_value_v1 import evaluate as EV
from research.us_selection_value_v1 import features as F
from research.us_selection_value_v1 import fetch_as_traded as Y

ROOT = Path(__file__).resolve().parents[2]
VINTAGE = "FRESH_YAHOO_CAPTURE_2026_11_17_NOT_ORIGINAL_PRIVATE_CACHE"
CTVA_PROBE_SHA256 = "c8f9f48f042a7d9c9843ee7777c73d26852987880c9c30aad910966f99956fa5"


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, sort_keys=True, allow_nan=False) + "\n")


def prefetch():
    """Fetch exact existing blobs in one request, never a mutable branch tip."""
    reader = SealedReader(ROOT)
    m = reader.manifest()
    refs = {r for k, rr in m["components"].items()
            if k.startswith(("price/20", "benchmark/20", "corporate-events/"))
            for r in rr}
    listing = subprocess.check_output([
        "git", "ls-tree", "-r", SOURCE_COMMIT,
        "ledger/replay-inputs/objects", "ledger/fundamentals/us"], cwd=ROOT, text=True)
    objects = []
    for line in listing.splitlines():
        meta, path = line.split("\t")
        if ((path.startswith("ledger/fundamentals/us/") and path.endswith(".jsonl.gz"))
                or (path.startswith(OBJECTS) and Path(path).name.removesuffix(".json.gz") in refs)):
            objects.append(meta.split()[2])
    checked = subprocess.check_output(
        ["git", "-c", "remote.origin.promisor=false", "cat-file", "--batch-check"],
        input="\n".join(objects) + "\n", cwd=ROOT, text=True,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})
    missing = [x.split()[0] for x in checked.splitlines() if x.endswith(" missing")]
    if missing:
        subprocess.run(["git", "fetch", "--no-tags", "--no-write-fetch-head", "origin", *missing],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    return {"objects": len(objects), "fetchedObjects": len(missing)}


def core_inputs(private):
    private.mkdir(parents=True, exist_ok=True)
    receipt = {"startedAtUTC": now(), "prefetch": prefetch()}
    if not (private / "close.pkl").exists():
        close, ident = F.PILOT.load_prices(ROOT)
        with (private / "close.pkl").open("wb") as f:
            pickle.dump({"close": close, "ident": ident}, f)
    if not (private / "filings.pkl").exists():
        raw, shards = F.PILOT.load_filings(ROOT)
        with (private / "filings.pkl").open("wb") as f:
            pickle.dump({"raw": raw, "shards": shards}, f)
    with (private / "close.pkl").open("rb") as f:
        pk = pickle.load(f)
    close = pk["close"]
    (private / "tickers.txt").write_text("\n".join(close.columns) + "\n")
    receipt.update(completedAtUTC=now(), priceIdentity=pk["ident"],
                   closeSha256=digest(private / "close.pkl"),
                   filingsSha256=digest(private / "filings.pkl"),
                   rows=len(close), tickers=len(close.columns),
                   firstSession=str(close.index[0].date()), lastSession=str(close.index[-1].date()),
                   generator="research.us_selection_value_v1.features.PILOT.load_prices/load_filings")
    save_json(private / "core-input-receipt.json", receipt)
    print("US frozen core inputs", len(close), len(close.columns), flush=True)


def capture(private):
    """Run the original fetcher, preserving its exact HTTP body as extra evidence."""
    out = private / "yahoo"
    rawdir = private / "yahoo-raw"
    out.mkdir(parents=True, exist_ok=True)
    rawdir.mkdir(parents=True, exist_ok=True)
    original_open = urllib.request.urlopen
    tickers = (private / "tickers.txt").read_text().split()
    for i, ticker in enumerate(tickers):
        receipt_file = rawdir / (ticker + ".receipt.json")
        if (out / (ticker + ".json.gz")).exists():
            continue

        def recorded_open(request, *args, **kwargs):
            observed = now()
            with original_open(request, *args, **kwargs) as response:
                body = response.read()
                code = response.status
                headers = {k: response.headers.get(k) for k in ("Content-Type", "Date", "ETag", "Last-Modified")}
            dest = rawdir / (ticker + ".response.json.gz")
            dest.write_bytes(gzip.compress(body, mtime=0))
            save_json(receipt_file, {"ticker": ticker, "url": request.full_url,
                      "observedAtUTC": observed, "status": code, "headers": headers,
                      "responseSha256": hashlib.sha256(body).hexdigest(),
                      "uncompressedBytes": len(body), "compressedSha256": digest(dest),
                      "vintage": VINTAGE})
            return io.BytesIO(body)

        urllib.request.urlopen = recorded_open
        try:
            status = Y.fetch(ticker, out)
        finally:
            urllib.request.urlopen = original_open
        if not receipt_file.exists():
            record = json.loads(gzip.decompress((out / (ticker + ".json.gz")).read_bytes()))
            save_json(receipt_file, {"ticker": ticker, "observedAtUTC": now(), "vintage": VINTAGE,
                      "status": status, "error": record.get("error")})
        if i % 50 == 0:
            print("US fresh capture", i, ticker, status, flush=True)
    receipts = [json.loads((rawdir / (t + ".receipt.json")).read_text()) for t in tickers]
    save_json(private / "yahoo-capture-manifest.json", {
        "vintage": VINTAGE, "notOriginalPrivateCache": True,
        "frozenURL": Y.URL, "userAgent": Y.UA, "tickers": len(tickers),
        "firstObservedAtUTC": min(r["observedAtUTC"] for r in receipts),
        "lastObservedAtUTC": max(r["observedAtUTC"] for r in receipts),
        "statusCounts": dict(Counter(str(r["status"]) for r in receipts)),
        "receipts": receipts})


def features(private):
    if (private / "features.pkl").exists():
        print("US original feature generator already completed; retaining file", flush=True)
        return
    started = now()
    F.main(["--private", str(private)])
    save_json(private / "feature-generator-receipt.json", {
        "startedAtUTC": started, "completedAtUTC": now(), "vintage": VINTAGE,
        "generator": "research.us_selection_value_v1.features.main (unchanged)",
        "sourceSha256": digest(Path(F.__file__)),
        "featuresSha256": digest(private / "features.pkl"),
        "featuresMetaSha256": digest(private / "features-meta.json"),
        "admissionOverrides": [], "performanceCalculated": False})


def verified_ctva_event(body, expected_sha=CTVA_PROBE_SHA256):
    if hashlib.sha256(body).hexdigest() != expected_sha:
        raise ValueError("CTVA_POSTCUTOFF_SOURCE_SHA256_MISMATCH")
    result = json.loads(body)["chart"]["result"][0]
    if result["meta"]["symbol"] != "CTVA":
        raise ValueError("CTVA_POSTCUTOFF_SOURCE_SYMBOL_MISMATCH")
    events = list((result.get("events") or {}).get("splits", {}).values())
    found = [v for v in events if F.ny_date(v["date"]).isoformat() == "2026-10-01"
             and v["numerator"] == 6665 and v["denominator"] == 1000]
    if len(found) != 1:
        raise ValueError("CTVA_EXPECTED_POSTCUTOFF_SPLIT_NOT_UNIQUE")
    return found[0]


def supplement_record(record, event, source_sha):
    """Add source evidence once; retain the original close rows and response SHA."""
    out = {**record, "splits": [list(s) for s in record["splits"]]}
    split = [int(event["date"]), float(event["numerator"]), float(event["denominator"])]
    if split not in out["splits"]:
        out["splits"].append(split)
        out["splits"].sort()
    sources = list(record.get("supplementarySources", []))
    source = {"reason": "POSTCUTOFF_SPLIT_OMITTED_BY_FIXED_CHART_END", "sourceSha256": source_sha,
              "eventDate": "2026-10-01", "splitRatio": 6.665,
              "repairAuthorizationCommit": "4710738", "originalAdmissionFunctionUnchanged": True}
    if source not in sources:
        sources.append(source)
    out["supplementarySources"] = sources
    return out


def split_factor_after(record, day):
    text = pd.Timestamp(day).date().isoformat()
    return float(np.prod([n / d for stamp, n, d in record["splits"]
                          if d > 0 and F.ny_date(stamp).isoformat() > text]))


def repair_ctva(private):
    """Input-only correction authorized and frozen in INPUT-REPAIR-ko.md."""
    body = gzip.decompress((private / "ctva-postcutoff-event-probe.response.json.gz").read_bytes())
    event = verified_ctva_event(body)
    record_path = private / "yahoo/CTVA.json.gz"
    record = json.loads(gzip.decompress(record_path.read_bytes()))
    repaired = supplement_record(record, event, CTVA_PROBE_SHA256)
    if repaired == record:
        print("US CTVA split supplement already present", flush=True)
        return
    archive = private / "pre-ctva-split-fix"
    archive.mkdir(exist_ok=True)
    receipt = {"authorizationCommit": "4710738", "observedAtUTC": now(),
               "event": event, "sourceSha256": CTVA_PROBE_SHA256,
               "archive": str(archive), "admissionOverrides": [], "pricesReplaced": False,
               "archivedFiles": {}}
    for name in ("features.pkl", "features-meta.json", "feature-generator-receipt.json",
                 "input-preparation-summary.json", "sealed-raw-comparison.json"):
        path = private / name
        if path.exists():
            receipt["archivedFiles"][name] = {"bytes": path.stat().st_size, "sha256": digest(path)}
            shutil.move(str(path), archive / name)
    shutil.copy2(record_path, archive / "CTVA.json.gz")
    receipt["archivedFiles"]["CTVA.json.gz"] = {"sha256": digest(record_path)}
    record_path.write_bytes(gzip.compress(json.dumps(repaired).encode(), mtime=0))
    receipt["repairedParsedRecordSha256"] = digest(record_path)
    save_json(private / "ctva-split-repair-receipt.json", receipt)
    print("US CTVA source split supplemented; original feature generator must run again", flush=True)


def sealed_audit(private):
    reader = SealedReader(ROOT)
    m = reader.manifest()
    events = defaultdict(dict)
    bars = defaultdict(dict)
    keys = set()
    for name, refs in sorted(m["components"].items()):
        if not name.startswith(("price/20", "benchmark/20", "corporate-events/20")):
            continue
        for ref in refs:
            for row in reader.component(ref):
                ticker = row["ticker"]
                if ticker.endswith((".KS", ".KQ")):
                    continue
                if name.startswith("corporate-events/"):
                    events[ticker][row["date"]] = row
                else:
                    keys.update(row)
                    bars[ticker][row["date"]] = row
    per_ticker = {}
    for ticker, panel in sorted(bars.items()):
        rawfile = private / "yahoo-raw" / (ticker + ".response.json.gz")
        if not rawfile.exists():
            per_ticker[ticker] = {"state": "FRESH_RESPONSE_NOT_SERVED"}
            continue
        reply = json.loads(gzip.decompress(rawfile.read_bytes()))
        results = reply.get("chart", {}).get("result")
        if not results:
            per_ticker[ticker] = {"state": "FRESH_CHART_RESULT_ABSENT"}
            continue
        result = results[0]
        quote = result["indicators"]["quote"][0]
        parsed = json.loads(gzip.decompress((private / "yahoo" / (ticker + ".json.gz")).read_bytes()))
        splits = sorted((F.ny_date(stamp).isoformat(), n / d) for stamp, n, d in parsed["splits"] if n > 0 and d > 0)
        fresh = {}
        for i, stamp in enumerate(result.get("timestamp", [])):
            value = quote["close"][i]
            if value is None or value <= 0:
                continue
            day = F.ny_date(stamp).isoformat()
            later = float(np.prod([r for d, r in splits if d > day]))
            volume = quote.get("volume", [None] * len(result["timestamp"]))[i]
            fresh[day] = (value * later, volume / later if volume is not None else None)
        cumulative = split_prefix = 1.0
        previous = None
        price_errors, volume_errors, zero_volumes = [], [], 0
        missing_closes = 0
        first = last = None
        for day, row in sorted(panel.items()):
            event = events[ticker].get(day, {})
            ratio = event.get("split", 1.0) or 1.0
            dividend = event.get("dividend", 0.0) or 0.0
            cumulative *= ratio
            split_prefix *= ratio
            if dividend > 0 and previous is not None and dividend < previous:
                cumulative /= 1.0 - dividend / previous
            if row["Close"] is None or not np.isfinite(row["Close"]):
                previous = None
                missing_closes += 1
                continue
            raw_close = row["Close"] / cumulative
            previous = raw_close
            if day not in fresh:
                continue
            py, vy = fresh[day]
            price_errors.append(abs(raw_close / py - 1.0))
            if vy is not None and vy > 0 and row.get("Volume") is not None:
                volume_errors.append(abs(row["Volume"] * split_prefix / vy - 1.0))
            elif vy == 0:
                zero_volumes += 1
            first = first or day
            last = day
        per_ticker[ticker] = {
            "state": "COMPARED" if price_errors else "NO_OVERLAP",
            "firstComparedSession": first, "lastComparedSession": last,
            "priceComparedSessions": len(price_errors),
            "priceMaximumAbsoluteRelativeError": max(price_errors) if price_errors else None,
            "priceMedianAbsoluteRelativeError": float(np.median(price_errors)) if price_errors else None,
            "volumeComparedSessions": len(volume_errors), "freshZeroVolumeSessions": zero_volumes,
            "volumeMaximumAbsoluteRelativeError": max(volume_errors) if volume_errors else None,
            "sealedEventSessions": len(events[ticker]), "freshSplitCount": len(splits),
            "sealedMissingCloseSessions": missing_closes,
            "sealedEventAbsent": not bool(events[ticker])}
    save_json(private / "sealed-raw-comparison.json", {
        "sourceCommit": SOURCE_COMMIT, "manifestSha256": m["sha256"],
        "vintage": VINTAGE, "storedPriceRowKeys": sorted(keys),
        "method": "Invert frozen forward TR recipe from FIRST_OBSERVED_SESSION with sealed as-traded dividends and splits; compare to fresh split-adjusted close times strictly later source split ratios, including the separately evidenced CTVA 2026-10-01 supplement when present.",
        "volumeMethod": "sealedVolume times splits on-or-before day compared with freshYahooVolume divided by strictly later splits (original price_adjustment basis).",
        "admissionImpact": "NONE: original AsTraded validator alone admits or rejects; inverse audit does not fill, replace or admit prices.",
        "caveat": "Some sealed ETFs including SPY have no corporate-events evidence. Inversion cannot recover their dividend-unadjusted close; original benchmark TR remains authoritative. No volume/liquidity filter is added.",
        "byTicker": per_ticker})


def inventory_report(private, out):
    feats = pd.read_pickle(private / "features.pkl")
    meta = json.loads((private / "features-meta.json").read_text())
    baseline = json.loads((ROOT / "research/us_selection_value_v1/results/result.json").read_text())
    yearly = defaultdict(Counter)
    weekly = []
    for day, g in feats.groupby("date", sort=True):
        count = len(EV.common(g))
        c = yearly[day[:4]]
        c["signalWeeks"] += 1
        c["pricedMemberRows"] += len(g)
        c["commonUniverseRows"] += count
        c["eligibleWeeks" if count >= 30 else "weeksBelowMinimum"] += 1
        weekly.append({"date": day, "commonUniverse": count, "pricedMembers": len(g)})
    yearly = {y: dict(v) for y, v in sorted(yearly.items())}
    differences = []
    for y in sorted(set(yearly) | set(baseline["yearSample"])):
        current = yearly.get(y, {})
        before = baseline["yearSample"].get(y, {})
        for field in sorted(set(current) | set(before)):
            if current.get(field, 0) != before.get(field, 0):
                differences.append({"year": y, "field": field, "current": current.get(field, 0),
                                    "original": before.get(field, 0)})
    capture_manifest = json.loads((private / "yahoo-capture-manifest.json").read_text())
    served_hashes_verified = 0
    for ticker in (private / "tickers.txt").read_text().split():
        rec = json.loads(gzip.decompress((private / "yahoo" / (ticker + ".json.gz")).read_bytes()))
        if rec["status"] == "SERVED":
            body = gzip.decompress((private / "yahoo-raw" / (ticker + ".response.json.gz")).read_bytes())
            if hashlib.sha256(body).hexdigest() != rec["sha256"]:
                raise ValueError("PARSED_CACHE_DOES_NOT_MATCH_CAPTURED_HTTP_BODY:" + ticker)
            served_hashes_verified += 1
    comparison = json.loads((private / "sealed-raw-comparison.json").read_text())
    compared = list(comparison["byTicker"].values())
    close_errors = [r["priceMaximumAbsoluteRelativeError"] for r in compared
                    if r.get("priceMaximumAbsoluteRelativeError") is not None]
    summary = {
        "study": "kr_us_strategy_batch_v1", "status": "US_INPUTS_PREPARED_NEW_CAPTURE",
        "performanceCalculated": False, "privateDirectory": str(private), "vintage": VINTAGE,
        "originalPrivateCacheRecovered": False, "sourceCommit": SOURCE_COMMIT,
        "manifestSha256": comparison["manifestSha256"], "admissionOverrides": [],
        "capture": {k: capture_manifest[k] for k in ["tickers", "firstObservedAtUTC", "lastObservedAtUTC", "statusCounts"]},
        "captureIntegrity": {"servedHTTPBodyHashesVerified": served_hashes_verified,
                             "originalFetcherSourceSha256": digest(Path(Y.__file__))},
        "originalAsTradedStatus": baseline["asTradedStatus"],
        "currentAsTradedStatus": meta["asTradedStatus"],
        "statusCountsMatch": meta["asTradedStatus"] == baseline["asTradedStatus"],
        "cikRuleValidation": meta["cikRuleValidation"],
        "originalCikRuleValidation": baseline["cikRuleValidation"],
        "yearSample": yearly, "yearSampleDifferences": differences,
        "weeklyUniverse": weekly,
        "rawInverseComparison": {
            "comparedTickers": len(close_errors),
            "tickersMaximumErrorBelow1eMinus8": sum(e < 1e-8 for e in close_errors),
            "doesNotOverrideAdmission": True,
            "priceOutliers": {t: r for t, r in comparison["byTicker"].items()
                              if r.get("priceMaximumAbsoluteRelativeError") is not None and r["priceMaximumAbsoluteRelativeError"] >= 1e-8},
            "volumeOutliers": {t: r for t, r in comparison["byTicker"].items()
                               if r.get("volumeMaximumAbsoluteRelativeError") is not None and r["volumeMaximumAbsoluteRelativeError"] >= 1e-8},
            "privateDetailFile": str(private / "sealed-raw-comparison.json")},
        "nport": {"status": "BLOCKED_OPTIONAL_C2_INPUT_ABSENT",
                  "minimumRequiredFile": str(private.parent / "nport/round8/C2.pkl"),
                  "existingAggregateReferences": ["research/followup_round8_v1/results/us-eval.json", "research/followup_round8_v1/results/us-audit.json"],
                  "noAdditionalPurchase": True},
        "files": {p.name: {"bytes": p.stat().st_size, "sha256": digest(p)}
                  for p in private.iterdir() if p.is_file() and p.name != "input-preparation-summary.json"},
    }
    repair = private / "ctva-split-repair-receipt.json"
    if repair.exists():
        summary["inputRepair"] = json.loads(repair.read_text())
    save_json(private / "input-preparation-summary.json", summary)
    if out:
        save_json(out, summary)
    print(json.dumps({"status": summary["status"], "asTradedStatus": summary["currentAsTradedStatus"],
                      "yearSampleDifferenceCount": len(differences), "rawInverse": summary["rawInverseComparison"]}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--stage", choices=("all", "core", "capture", "repair", "features", "audit", "report"), default="all")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    private = args.private.resolve()
    if private.is_relative_to(ROOT):
        raise ValueError("VENDOR_INPUTS_MUST_REMAIN_OUTSIDE_REPOSITORY")
    stages = ("core", "capture", "repair", "features", "audit", "report") if args.stage == "all" else (args.stage,)
    actions = {"core": core_inputs, "capture": capture, "repair": repair_ctva, "features": features, "audit": sealed_audit,
               "report": lambda p: inventory_report(p, args.out)}
    for stage in stages:
        actions[stage](private)


if __name__ == "__main__":
    main()
