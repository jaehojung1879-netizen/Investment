"""Audit saved guidance measurements using the pinned Item 2.02 filing catalog.

Only archived source-admission metadata is read. All event counts are
conditional on the archived v2 extractor and the panel that was processed.
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

ARCHIVE = Path(__file__).resolve().parents[1] / "results"
CATALOG_SHA256 = "4fa79370feec010ab340b2ad9087bad0e32a691f67ddf9aac27dee2849f0ce09"
START, THROUGH = "2014-01-01", "2026-11-21"
SEMIS = {
    "producerOrEquipment": {"AMAT", "AMD", "KLAC", "LRCX", "MU", "NVDA", "STX", "WDC"},
    "cloudCustomer": {"AMZN", "GOOG", "GOOGL", "META", "MSFT"},
}
ALPHABET = {"1288776", "1652044"}
DIRECTIONAL = {"RAISE", "LOWER"}
BOOTSTRAP_REPLICATES = 2000
SEED = 20261126


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def utc(timestamp):
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timezone required for acceptance timestamp: {timestamp}")
    return parsed.astimezone(timezone.utc)


def quarter(timestamp):
    return f"{timestamp.year}Q{(timestamp.month - 1) // 3 + 1}"


def load_catalog(path):
    raw = path.read_bytes()
    if sha256(raw) != CATALOG_SHA256:
        raise ValueError("Item 2.02 catalog SHA-256 does not match the archived frame")
    rows = csv.DictReader(io.TextIOWrapper(io.BytesIO(gzip.decompress(raw)), encoding="utf-8"))
    filings, amendments = {}, set()
    for row in rows:
        if not START <= row["filingDate"] <= THROUGH or "2.02" not in {item.strip() for item in row["items"].split(",")}:
            continue
        key = row["cik"], row["accession"]
        if row["form"] == "8-K/A":
            amendments.add(key)
        if row["form"] != "8-K":
            continue
        stamp = utc(row["acceptanceDateTime"])
        if key in filings:
            existing = filings[key]
            if (existing["accepted"], existing["filed"]) != (stamp, row["filingDate"]):
                raise ValueError(f"Conflicting filing timestamps for {key}")
            existing["tickers"].add(row["ticker"])
        else:
            filings[key] = {"accepted": stamp, "filed": row["filingDate"], "tickers": {row["ticker"]}}
    return filings, amendments


def role_ciks(filings):
    by_role = {role: {cik for (cik, _), filing in filings.items() if filing["tickers"] & tickers}
               for role, tickers in SEMIS.items()}
    if any(len([role for role, ids in by_role.items() if cik in ids]) != 1
           for cik in set.union(*by_role.values())):
        raise ValueError("An issuer appears in more than one semiconductor role")
    return by_role


def resolve_links(rows, filings):
    by_accession = defaultdict(list)
    for (cik, accession), filing in filings.items():
        by_accession[accession].append((cik, filing))
    resolved = []
    for row in rows:
        accepted, prior = utc(row["accepted_at"]), utc(row["prior_accepted_at"])
        if prior >= accepted:
            raise ValueError(f"Non-increasing release timestamps at {row['accession']}")
        possible = [(cik, filing) for cik, filing in by_accession[row["accession"]]
                    if row["issuer"] in filing["tickers"] and filing["accepted"] == accepted]
        if len(possible) != 1:
            raise ValueError(f"Ambiguous or absent current accession {row['accession']}")
        cik, _ = possible[0]
        preceding = filings.get((cik, row["prior_accession"]))
        if preceding is None or preceding["accepted"] != prior:
            raise ValueError(f"Unverified same-issuer prior accession {row['prior_accession']}")
        resolved.append({**row, "cik": cik, "accepted": accepted})
    return resolved


def corp_cluster(cik):
    # The sensitivity combines Google and its Alphabet successor for variance
    # diagnostics. Filing evidence and links retain the original legal CIK.
    return "Alphabet (Google predecessor + successor)" if cik in ALPHABET else cik


def concentration(counts):
    total = sum(counts.values())
    if not total:
        return {"groups": 0, "largestShare": None, "inverseConcentration": None}
    return {
        "groups": len(counts),
        "largestShare": round(max(counts.values()) / total, 6),
        "inverseConcentration": round(total**2 / sum(n**2 for n in counts.values()), 6),
    }


def effective_n(counts):
    sizes = list(counts.values())
    total = sum(sizes)
    return {str(rho): (round(total**2 / sum(n + rho * n * (n - 1) for n in sizes), 3) if total else None)
            for rho in (0.0, 0.05, 0.2, 1.0)}


def event_counts(rows):
    filings = {(r["cik"], r["accession"]) for r in rows}
    releases = {(r["cik"], r["accepted"]) for r in rows}
    issuer_periods = {(cik, quarter(accepted)) for cik, accepted in releases}
    issuer_sizes = Counter(cik for cik, _ in releases)
    corporate_sizes = Counter(corp_cluster(cik) for cik, _ in releases)
    quarter_sizes = Counter(quarter(accepted) for _, accepted in releases)
    return {
        "linkRows": len(rows),
        "currentFilings": len(filings),
        "issuerAcceptanceEvents": len(releases),
        "issuerCalendarQuarters": len(issuer_periods),
        "calendarQuarters": len(quarter_sizes),
        "linkConcentrationByLegalIssuer": concentration(Counter(r["cik"] for r in rows)),
        "acceptanceEventConcentrationByLegalIssuer": concentration(issuer_sizes),
        "acceptanceEventConcentrationByCorporateGroup": concentration(corporate_sizes),
        "acceptanceEventConcentrationByCalendarQuarter": concentration(quarter_sizes),
        "singleDimensionDesignEffectNByIssuerRho": effective_n(issuer_sizes),
        "singleDimensionDesignEffectNByQuarterRho": effective_n(quarter_sizes),
    }


def link_counts(rows):
    link_keys = {(r["cik"], r["accession"], r["prior_accession"], r["target"], r["metric"], r["basis"], r["unit"])
                 for r in rows}
    extremes = [r for r in rows if r["relChange"] is not None and abs(r["relChange"]) >= 0.5]
    return {
        "all": event_counts(rows),
        "raiseLower": event_counts([r for r in rows if r["class"] in DIRECTIONAL]),
        "uniqueLinkKeys": len(link_keys),
        "currentPriorFilingPairs": len({(r["cik"], r["accession"], r["prior_accession"]) for r in rows}),
        "metricRows": dict(Counter(r["metric"] for r in rows)),
        "directionRows": dict(Counter(r["class"] for r in rows)),
        "extremeRelativeMidpointChanges": {"absAtLeast": 0.5, "count": len(extremes),
                                            "tickers": dict(Counter(r["issuer"] for r in extremes))},
    }


def role_summary(rows, filings, by_role, metadata):
    def coverage(observations):
        return {
            "linkRows": len(observations),
            "issuerAcceptanceEvents": len({(r["cik"], r["accepted"]) for r in observations}),
            "legalIssuers": len({r["cik"] for r in observations}),
        }

    output = {}
    for role, ciks in by_role.items():
        scoped = [row for row in rows if row["cik"] in ciks]
        shown = {ticker: metadata[ticker] for ticker in sorted(SEMIS[role])}
        output[role] = {
            "candidateLegalIssuers": sorted(ciks, key=int),
            "candidateCorporateGroups": len({corp_cluster(cik) for cik in ciks}),
            "catalogFilings": sum(cik in ciks for cik, _ in filings),
            "reportedLegacySampleReleaseRows": sum(row["releases"] for row in shown.values()),
            "reportedNumericCapexDetectorHits": sum(row["capexGuidance"] for row in shown.values()),
            "publishedDetectionByTicker": shown,
            "metricCoverage": {"demand": None, **{
                metric: coverage([r for r in scoped if r["metric"] == metric])
                for metric in ("revenue", "revenue_growth", "capex")
            }},
            "allMetricCoverage": coverage(scoped),
        }
    return output


def correlation(a, b):
    ac, bc = a - np.mean(a), b - np.mean(b)
    divisor = np.linalg.norm(ac) * np.linalg.norm(bc)
    return float(np.dot(ac, bc) / divisor) if divisor else None


def spearman(a, b):
    return correlation(rankdata(a), rankdata(b)) if len(a) >= 2 else None


def rounded(x):
    return None if x is None else round(float(x), 6)


def interval(values, percentiles=(0.025, 0.975)):
    valid = [x for x in values if x is not None and np.isfinite(x)]
    return {"validReplicates": len(valid), "quantiles": [rounded(x) for x in np.quantile(valid, percentiles)] if valid else None}


def cluster_interval(a, b, clusters):
    assignments = {name: np.unique(keys, return_inverse=True) for name, keys in clusters.items()}
    sizes = {name: len(unique) for name, (unique, _) in assignments.items()}
    if min(sizes.values()) < 2:
        return {"clusters": sizes, "validReplicates": 0, "quantiles": None}
    rng = np.random.default_rng(SEED)
    draws = []
    for _ in range(BOOTSTRAP_REPLICATES):
        weights = np.ones(len(a), dtype=int)
        for name, (_, codes) in assignments.items():
            n = sizes[name]
            weights *= np.bincount(rng.integers(n, size=n), minlength=n)[codes]
        indices = np.repeat(np.arange(len(a)), weights)
        draws.append(spearman(a[indices], b[indices]))
    return {"clusters": sizes, **interval(draws)}


def residual_rank_correlation(a, b, issuers, seasons):
    design = np.column_stack([np.asarray(labels) == group for labels in (issuers, seasons) for group in sorted(set(labels))])
    ranks = np.column_stack([rankdata(a), rankdata(b)])
    residuals = ranks - design @ np.linalg.lstsq(design, ranks, rcond=None)[0]
    return correlation(residuals[:, 0], residuals[:, 1])


def noise_stress(a, b):
    rng = np.random.default_rng(SEED)
    stress = {}
    for sigma in (0.01, 0.03, 0.05):
        shared, independent = [], []
        for _ in range(500):
            e0, e1, e2 = rng.normal(0, sigma, size=(3, len(a)))
            shared.append(spearman((1 + a) * np.exp(e0) - 1, (1 + b) * np.exp(-e0) - 1))
            independent.append(spearman((1 + a) * np.exp(e1) - 1, (1 + b) * np.exp(e2) - 1))
        stress[str(sigma)] = {
            "addedSharedActualError": interval(shared, (0.05, 0.5, 0.95)),
            "addedIndependentGuideErrors": interval(independent, (0.05, 0.5, 0.95)),
        }
    return stress


def independence(rows):
    stamps = [utc(row["accepted_at"]) for row in rows]
    issuers = [row["cik"] for row in rows]
    if len(set(zip(issuers, stamps))) != len(rows):
        raise ValueError("Duplicate issuer-acceptance event in archived comparison")
    a = np.array([row["surprise"] for row in rows])
    b = np.array([row["fwdGuideChange"] for row in rows])
    if not np.all(np.isfinite(a) & np.isfinite(b) & (a > -1) & (b > -1)):
        raise ValueError("Archived growth and surprise ratios must be finite and above -100%")
    periods = [quarter(stamp) for stamp in stamps]
    seasons = [period[-1] for period in periods]
    issuer_array = np.asarray(issuers)
    fy = [row for row in rows if row["fyRevision"] is not None]
    pearson = correlation(a, b)
    return {
        "events": len(rows),
        "eventsByLegalIssuer": dict(Counter(issuers)),
        "calendarQuarters": len(set(periods)),
        "issuerCalendarQuarters": len(set(zip(issuers, periods))),
        "spearmanAverageTies": rounded(spearman(a, b)),
        "pearsonR2": rounded(pearson**2) if pearson is not None else None,
        "issuerClusteredSpearman95": cluster_interval(a, b, {"issuer": issuers}),
        "calendarQuarterClusteredSpearman95": cluster_interval(a, b, {"calendarQuarter": periods}),
        "crossedClusterSpearman95": cluster_interval(a, b, {"issuer": issuers, "calendarQuarter": periods}),
        "leaveOneIssuerOutSpearman": {cik: rounded(spearman(a[issuer_array != cik], b[issuer_array != cik]))
                                     for cik in sorted(set(issuers), key=int)},
        "spearmanAfterIssuerAndCalendarSeasonAdjustment": rounded(residual_rank_correlation(a, b, issuers, seasons)),
        "sensitivityRemoveSharedActualFromGrowthProxySpearman": rounded(spearman(a, (1 + a) * (1 + b) - 1)),
        "sameTargetAnnualRevisionCoverage": {
            "coTimedPairs": len(fy), "nonzeroRevisions": sum(row["fyRevision"] != 0 for row in fy),
            "legalIssuers": len({row["cik"] for row in fy}), "inferenceEligible": False,
        },
        "addedLogScaleMeasurementErrorStress90": noise_stress(a, b),
    }


def report(catalog, archives):
    filings, amendments = load_catalog(catalog)
    hashes = {}

    def read(filename):
        raw = (archives / filename).read_bytes()
        hashes[filename] = sha256(raw)
        return json.loads(raw)

    source = read("source-admission-summary.json")
    panel = resolve_links(read("guidance-links-panel.json")["links"], filings)
    semi = resolve_links(read("guidance-links-semi.json")["links"], filings)
    archived_events = read("guidance-independence-events.json")
    by_role = role_ciks(filings)
    semi_ciks = set.union(*by_role.values())
    if any(row["cik"] not in semi_ciks for row in semi):
        raise ValueError("Unexpected CIK in the declared semiconductor panel")
    events = {"semiconductor": [], "randomPanel": []}
    filing_acceptances = {(cik, filing["accepted"]) for (cik, _), filing in filings.items()}
    for row in archived_events:
        if (row["cik"], utc(row["accepted_at"])) not in filing_acceptances:
            raise ValueError(f"Archived comparison timestamp absent from catalog for {row['cik']}")
        events["semiconductor" if row["cik"] in semi_ciks else "randomPanel"].append(row)
    if len(events["semiconductor"]) != 195 or len(events["randomPanel"]) != 22:
        raise ValueError("Archived cohort boundaries do not reproduce the documented event counts")
    screening = source["A_guidance"]["stratifiedSample"]
    return {
        "status": "SOURCE_ONLY",
        "catalog": {"sha256": CATALOG_SHA256, "start": START, "through": THROUGH,
                    "uniqueNonAmendedFilings": len(filings), "uniqueLegalIssuers": len({cik for cik, _ in filings}),
                    "amendmentsExcluded": len(amendments), "filingsByYear": dict(Counter(f["filed"][:4] for f in filings.values())),
                    "calendarQuarters": len({quarter(f["accepted"]) for f in filings.values()})},
        "archivedInputSha256": hashes,
        "expansion": {"archivedStratifiedSample": screening,
                      "legacyRandomPanelReleaseRows": source["A_guidance"]["randomPanel2022_2025"]["filings"],
                      "populationRevisionEstimate": None,
                      "reason": "A calibrated population change rate requires historical source coverage, independent annotation, and adjustment for detector selection and unequal cluster sizes."},
        "randomPanelLinks": link_counts(panel),
        "semiconductorLinks": link_counts(semi),
        "semiconductorRoles": role_summary(semi, filings, by_role, source["B_semiconductor"]["secProducersCustomers2014_2026"]),
        "alphabetCikRollup": {"predecessor": "1288776", "successor": "1652044", "crossCikLinkingPerformed": False},
        "sharedCurrentFilingsAcrossPanels": len({(r["cik"], r["accession"]) for r in panel} & {(r["cik"], r["accession"]) for r in semi}),
        "informationOverlap": {key: independence(rows) for key, rows in events.items()},
        "interpretation": {
            "scope": "All link and event metrics are diagnostics on archived v2-derived observations. Independent episode validation requires source adjudication.",
            "mechanicalDependence": "Surprise is actual divided by the issuer's prior guide minus one. The adjacent-quarter proxy is next-quarter guide divided by the same actual minus one. Their denominators couple measurement error. The product sensitivity removes that actual algebraically and still compares different fiscal periods.",
            "consensus": "The benchmark is the issuing company's previous guide. This archive supplies no analyst consensus.",
            "uncertainty": "Percentile intervals resample legal issuers or calendar quarters with 2000 replicates. The crossed sensitivity multiplies independently resampled issuer and quarter weights for each event. Few clusters, unequal cluster sizes, and variation across periods limit inference. Design-effect sample sizes are one-dimensional illustrative sensitivities to assumed exchangeable dependence.",
            "measurementError": "Stress cases add hypothetical normal errors on the log scale to existing observed ratios. These simulations characterize sensitivity. They supply no estimate of latent reliability.",
            "sector": "Revenue covers the reported company metric. Cloud-company capex covers the company guidance and can include spending unrelated to semiconductors. A consistent forward demand series is absent from the saved extract schema.",
            "gate": "Preregistration remains on hold until accession-level source coverage and independent extraction, direction and same-target link accuracy pass the admission criteria.",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    args = parser.parse_args()
    print(json.dumps(report(args.catalog, args.archive), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
