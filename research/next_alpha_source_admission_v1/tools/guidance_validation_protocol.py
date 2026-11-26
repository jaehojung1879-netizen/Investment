"""Freeze an issuer-disjoint, source-only validation roster before reading its exhibits.

The saved random panel only fetched Item 2.02 releases dated 2022–2025. Its
complete company list is unavailable. Conservatively exclude every company
that had a qualifying release in that window, along with companies exposed
by the other committed sampling manifests. The restricted cohort cannot
estimate accuracy over the entire catalog, including established 2022–2025
issuers. This tool never fetches or scores an exhibit.
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
import random
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_START = "2014-01-01"
CATALOG_END = "2026-11-21"
CATALOG_SHA256 = "4fa79370feec010ab340b2ad9087bad0e32a691f67ddf9aac27dee2849f0ce09"
PANEL_START = "2022-01-01"
PANEL_END = "2025-12-31"
ROSTER_SEED = "investment-383-issuer-holdout-restricted-v1"
DOCS_PER_GROUP = 4
MAX_GROUPS = 40


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def catalog_records(raw):
    records = {}
    tickers = defaultdict(set)
    with io.StringIO(gzip.decompress(raw).decode("utf-8"), newline="") as handle:
        for row in csv.DictReader(handle):
            filed = date.fromisoformat(row["filingDate"]).isoformat()
            items = {item.strip() for item in row["items"].split(",")}
            if row["form"] != "8-K" or "2.02" not in items or not CATALOG_START <= filed <= CATALOG_END:
                continue
            cik, accession = int(row["cik"]), row["accession"]
            accepted = datetime.fromisoformat(row["acceptanceDateTime"])
            if cik <= 0 or accepted.utcoffset() is None or not accession.strip():
                raise ValueError(f"Malformed accession identity for {cik}/{accession}")
            record = {"cik": cik, "accession": accession, "filingDate": filed,
                      "acceptanceDateTime": accepted.astimezone(timezone.utc).isoformat(timespec="microseconds")}
            key = cik, accession
            if key in records and records[key] != record:
                raise ValueError(f"Conflicting filing metadata for {cik}/{accession}")
            records[key] = record
            ticker = row["ticker"].strip()
            if ticker:
                tickers[key].add(ticker)
    documents = [{**row, "tickers": sorted(tickers[key])} for key, row in records.items()]
    return sorted(documents, key=lambda row: (row["cik"], row["acceptanceDateTime"], row["accession"]))


def issuer_groups(records):
    """Conservatively treat CIKs joined by a catalog ticker as one group."""
    by_ticker = defaultdict(set)
    aliases = {}
    for record in records:
        cik = record["cik"]
        aliases[cik] = cik
        for ticker in record["tickers"]:
            by_ticker[ticker].add(cik)

    def representative(cik):
        while cik != aliases[cik]:
            cik = aliases[cik]
        return cik

    for ticker in sorted(by_ticker):
        linked = {representative(cik) for cik in by_ticker[ticker]}
        first = min(linked)
        for other in linked:
            aliases[other] = first
    return {cik: representative(cik) for cik in aliases}


def select_roster(records, gold_docs, stratified_docs, semi_tickers):
    groups = issuer_groups(records)
    catalog_keys = {(row["cik"], row["accession"]) for row in records}
    exposed_keys = {(int(row["cik"]), row["accession"]) for row in (*gold_docs, *stratified_docs)}
    if not exposed_keys <= catalog_keys:
        raise ValueError("Exposure manifest contains filings outside the pinned catalog")
    ticker_set = {ticker for row in records for ticker in row["tickers"]}
    if not semi_tickers or not semi_tickers <= ticker_set:
        raise ValueError("Semiconductor exposure tickers are missing from the pinned catalog")
    annotated = {int(row["cik"]) for row in gold_docs}
    stratified = {int(row["cik"]) for row in stratified_docs}
    possible_panel = {row["cik"] for row in records if PANEL_START <= row["filingDate"] <= PANEL_END}
    semiconductor = {row["cik"] for row in records if semi_tickers.intersection(row["tickers"])}
    exposures = annotated | stratified | possible_panel | semiconductor
    excluded_groups = {groups[cik] for cik in exposures}

    eligible = defaultdict(list)
    for row in records:
        group = groups[row["cik"]]
        if group not in excluded_groups:
            eligible[group].append(row)

    def ranked(group):
        return digest(f"{ROSTER_SEED}|group|{group}".encode())

    chosen = sorted(eligible, key=ranked)[:MAX_GROUPS]
    if len(chosen) < MAX_GROUPS:
        raise ValueError(f"Only {len(chosen)} eligible issuer groups for a {MAX_GROUPS}-group roster")
    documents = []
    for group in chosen:
        # Never use a price, response status, extractor output or gold label
        # to select the contiguous source block. Distinct CIKs stay distinct
        # for link construction even when treated as one validation group.
        by_cik = defaultdict(list)
        for document in eligible[group]:
            by_cik[document["cik"]].append(document)
        cik = min(by_cik, key=lambda x: (-len(by_cik[x]), x))
        filings = sorted(by_cik[cik], key=lambda row: (row["acceptanceDateTime"], row["accession"]))
        positions = max(1, len(filings) - DOCS_PER_GROUP + 1)
        start = int(digest(f"{ROSTER_SEED}|block|{group}".encode()), 16) % positions
        documents.extend({**row, "issuerGroup": group} for row in filings[start:start + DOCS_PER_GROUP])
    return {
        "protocol": "GUIDANCE_RESTRICTED_ISSUER_HOLDOUT_V1",
        "scope": "Issuer-disjoint restricted validation. No inference for all catalog issuers.",
        "selectionSeed": ROSTER_SEED,
        "catalogWindow": [CATALOG_START, CATALOG_END],
        "excludedPotentialPanelWindow": [PANEL_START, PANEL_END],
        "counts": {"catalogFilings": len(records), "catalogCiks": len(groups),
                   "goldCiks": len(annotated), "stratifiedCiks": len(stratified),
                   "potentialPanelCiks": len(possible_panel), "semiconductorCiks": len(semiconductor),
                   "excludedIssuerGroups": len(excluded_groups), "eligibleIssuerGroups": len(eligible),
                   "selectedIssuerGroups": len(chosen), "selectedFilings": len(documents)},
        "filingYears": dict(sorted(Counter(row["filingDate"][:4] for row in documents).items())),
        "documents": sorted(documents, key=lambda row: (row["issuerGroup"], row["acceptanceDateTime"],
                                                        row["accession"])),
    }


def freeze_catalog(catalog_path):
    paths = {"catalog": catalog_path,
             "legacyGoldManifest": ROOT / "gold/gold-docs.json",
             "legacyStratifiedManifest": ROOT / "results/guidance-stratified-sample.json",
             "legacySemiconductorRoster": ROOT / "results/source-admission-summary.json",
             "legacyPanelSelection": ROOT / "tools/panel_fetch.py"}
    raw = {name: path.read_bytes() for name, path in paths.items()}
    hashes = {name: digest(data) for name, data in raw.items()}
    if hashes["catalog"] != CATALOG_SHA256:
        raise ValueError("The accession catalog differs from the one used by the legacy study")
    semi = json.loads(raw["legacySemiconductorRoster"])["B_semiconductor"]["secProducersCustomers2014_2026"]
    roster = select_roster(catalog_records(raw["catalog"]), json.loads(raw["legacyGoldManifest"]),
                           json.loads(raw["legacyStratifiedManifest"]), set(semi))
    return {**roster, "inputSha256": hashes}


def precision_recall_f1(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None
    return precision, recall, f1


def issuer_bootstrap(counts, *, draws=2000, seed=383):
    """Return reproducible percentile intervals for micro metrics over issuer clusters.

    ``counts`` maps issuer groups to (TP, FP, FN). Repeated rows in the same
    issuer are sampled together. Undefined metrics remain unreported and the
    number of defined replicates is explicit. Date-cluster dependence is not
    modeled by this interval.
    """
    if draws < 1:
        raise ValueError("draws must be positive")
    values = [counts[key] for key in sorted(counts)]
    if any(len(row) != 3 or any(type(n) is not int or n < 0 for n in row) for row in values):
        raise ValueError("counts must contain nonnegative integer TP, FP and FN")
    data = [[], [], []]
    rng = random.Random(seed)
    if len(values) >= 2:
        for _ in range(draws):
            sample = rng.choices(values, k=len(values))
            totals = [sum(row[column] for row in sample) for column in range(3)]
            for samples, point in zip(data, precision_recall_f1(*totals), strict=True):
                if point is not None:
                    samples.append(point)
    points = precision_recall_f1(*(sum(row[column] for row in values) for column in range(3)))
    result = {"issuerClusters": len(values), "draws": draws, "seed": seed}
    for name, samples, point in zip(("precision", "recall", "f1"), data, points, strict=True):
        samples.sort()
        interval = [samples[round((len(samples) - 1) * q)] for q in (0.025, 0.975)] if samples else None
        result[name] = {"point": point, "interval95": interval, "definedDraws": len(samples)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path, help="Pinned SEC accession CSV.gz")
    parser.add_argument("output", type=Path, help="New roster JSON; existing results cannot be overwritten")
    args = parser.parse_args()
    roster = freeze_catalog(args.catalog)
    serialized = (json.dumps(roster, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with args.output.open("xb") as handle:
        handle.write(serialized)
    print(digest(serialized))


if __name__ == "__main__":
    main()
