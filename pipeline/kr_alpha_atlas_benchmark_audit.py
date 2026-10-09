"""069500.KS-only source/adjustment audit, outside the frozen alpha executor.

Gross benchmark returns only. No stock labels, excess returns or portfolios.
Independent issuer prices and distributions use the same Yahoo factor recipe as
the registered index; true cash-reinvested returns are separate diagnostics.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import pandas as pd

from pipeline.kr_alpha_atlas_phase_c import contract
from pipeline import replay_calendar as RC

TICKER = "069500.KS"
THRESHOLD = 0.005


def benchmark_only(ticker):
    if ticker != TICKER:
        raise ValueError("ONLY_REGISTERED_BENCHMARK_IS_PERMITTED")


def verified_sources(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "sources.json").read_text())
    benchmark_only(manifest["ticker"])
    for row in manifest["files"].values():
        path = directory / row["path"]
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError("SOURCE_PATH_ESCAPES_SNAPSHOT")
        if contract.file_hash(path) != row["sha256"]:
            raise ValueError("INDEPENDENT_SOURCE_DIGEST_CHANGED")
    return manifest


def issuer_prices(path):
    import xlrd  # audit-only dependency, never added to the scientific runtime

    sheet = xlrd.open_workbook(path).sheet_by_index(0)
    if sheet.cell_value(0, 0) != "KODEX 200 기준가격" or sheet.cell_value(3, 1) != "종가":
        raise ValueError("OFFICIAL_INSTRUMENT_OR_SCHEMA_MISMATCH")
    market, nav = {}, {}
    for i in range(4, sheet.nrows):
        row = sheet.row_values(i)
        stamp = str(row[0])
        if not re.fullmatch(r"\d{8}", stamp):
            raise ValueError("INVALID_ISSUER_DATE")
        date = str(pd.Timestamp(stamp).date())
        if date in market:
            raise ValueError("DUPLICATE_BENCHMARK_SESSION")
        if isinstance(row[1], (int, float)) and np.isfinite(row[1]) and row[1] > 0:
            market[date] = float(row[1])
        if isinstance(row[5], (int, float)) and np.isfinite(row[5]) and row[5] > 0:
            nav[date] = float(row[5])
    return pd.Series(market, dtype=float).sort_index(), pd.Series(nav, dtype=float).sort_index()


def vendor_prices(path):
    rows = json.loads(Path(path).read_text().strip().replace("'", '"'))
    out = {}
    for row in rows[1:]:
        stamp = str(pd.Timestamp(str(row[0])).date())
        if stamp in out or not np.isfinite(row[4]) or row[4] <= 0:
            raise ValueError("INVALID_VENDOR_BENCHMARK_QUOTE")
        out[stamp] = float(row[4])
    return pd.Series(out, dtype=float).sort_index()


def issuer_distributions(path, days):
    rows = json.loads(Path(path).read_text())["dividList"]
    records = []
    used = set()
    for row in rows:
        record = pd.Timestamp(row["basicD"])
        pos = int(days.searchsorted(record, side="left")) - 1
        if pos < 0:
            raise ValueError("DISTRIBUTION_CALENDAR_TOO_SHORT")
        ex_date = str(days[pos].date())
        if ex_date in used:
            raise ValueError("DUPLICATE_DISTRIBUTION")
        used.add(ex_date)
        amount = float(row["dividA"])
        if not np.isfinite(amount) or amount <= 0:
            raise ValueError("INVALID_OFFICIAL_DISTRIBUTION")
        records.append({"ticker": TICKER, "recordDate": str(record.date()), "exDate": ex_date,
                        "paymentDate": str(pd.Timestamp(row["payD"]).date()), "cashKrwPerUnit": amount})
    return sorted(records, key=lambda r: r["exDate"])


def crosscheck_distributions(json_path, xls_path):
    import xlrd

    records = json.loads(Path(json_path).read_text())["dividList"]
    sheet = xlrd.open_workbook(xls_path).sheet_by_index(0)
    if sheet.cell_value(0, 0) != "KODEX 200":
        raise ValueError("WRONG_DISTRIBUTION_INSTRUMENT")
    xls = {str(sheet.cell_value(i, 0)): float(sheet.cell_value(i, 3)) for i in range(3, sheet.nrows)}
    expected = {r["basicD"]: float(r["dividA"]) for r in records}
    if xls != expected:
        raise ValueError("ISSUER_DISTRIBUTION_FORMATS_DISAGREE")
    return {"status": "PASS", "records": len(records), "amount": "gross cash, not taxable amount or investor net cash"}


def frozen_benchmark(root, spec):
    """Allowlist benchmark and corporate-event objects; never load price/* objects."""
    commit = spec["phaseBIdentity"]["inputs"]["sourceCommit"]
    raw = subprocess.check_output(["git", "cat-file", "blob", commit + ":ledger/historical/replay-v16/inputs.json"], cwd=root)
    manifest = json.loads(raw)
    if manifest["sha256"] != spec["phaseBIdentity"]["inputs"]["replayManifestSha256"] or contract.digest(
        {k: v for k, v in manifest.items() if k != "sha256"}
    ) != manifest["sha256"]:
        raise ValueError("FROZEN_REPLAY_MANIFEST_CHANGED")
    prices, events, hashes, lineage = {}, [], [], []
    for name, refs in sorted(manifest["components"].items()):
        if not (name.startswith("benchmark/") or name.startswith("corporate-events/")):
            continue
        for ref in refs:
            blob = subprocess.check_output(["git", "cat-file", "blob", commit + ":ledger/replay-inputs/objects/" + ref + ".json.gz"], cwd=root)
            content = gzip.decompress(blob)
            if hashlib.sha256(content).hexdigest() != ref:
                raise ValueError("FROZEN_BENCHMARK_COMPONENT_CHANGED")
            selected = [r for r in json.loads(content) if r.get("ticker") == TICKER]
            if selected:
                hashes.append({"component": name, "sha256": ref})
            if name == "benchmark/source":
                lineage.extend(selected)
            elif name.startswith("benchmark/20"):
                for row in selected:
                    if row["date"] in prices or row["Close"] <= 0:
                        raise ValueError("FROZEN_BENCHMARK_QUOTE_INVALID")
                    prices[row["date"]] = row["Close"]
            elif name.startswith("corporate-events/20"):
                events.extend(selected)
    return pd.Series(prices, dtype=float).sort_index(), {
        "sourceCommit": commit, "replayManifestSha256": manifest["sha256"],
        "componentContentHashes": hashes, "lineage": lineage,
        "benchmarkCorporateEventsPreserved": len(events),
        "definition": spec["targets"]["gross"],
    }


def adjusted_index(prices, distributions, *, ticker=TICKER, shareholder=False):
    benchmark_only(ticker)
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("CANONICAL_BENCHMARK_SESSIONS_REQUIRED")
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any():
        raise ValueError("MISSING_OR_INVALID_BENCHMARK_QUOTE")
    cash = {r["exDate"]: r["cashKrwPerUnit"] for r in distributions}
    result = pd.Series(index=prices.index, dtype=float)
    result.iloc[0] = 1.0
    for i in range(1, len(prices)):
        previous, close = prices.iloc[i - 1], prices.iloc[i]
        amount = cash.get(prices.index[i], 0.0)
        if amount >= previous:
            raise ValueError("DISTRIBUTION_NOT_BELOW_PREVIOUS_CLOSE")
        growth = (close + amount) / previous if shareholder else close / (previous - amount)
        result.iloc[i] = result.iloc[i - 1] * growth
    return result


def annual_comparison(internal, independent, sessions, years, *, coverage_from, cutoff):
    out = []
    day_strings = pd.Index([str(x.date()) for x in sessions])
    for year in years:
        selected = day_strings[(day_strings >= f"{year}-01-01") & (day_strings <= min(f"{year}-12-31", cutoff))]
        if not len(selected):
            raise ValueError("NO_REGISTERED_SESSIONS_FOR_YEAR")
        pos = day_strings.get_loc(selected[0])
        if pos == 0:
            raise ValueError("ANNUAL_ANCHOR_ABSENT")
        anchor, end = day_strings[pos - 1], selected[-1]
        required = pd.Index([anchor, *selected])
        matched = int(sum(d in internal.index and d in independent.index for d in selected))
        full = all(d in internal.index and d in independent.index for d in required)
        cash_known = coverage_from is not None and anchor >= coverage_from
        a = float(internal[end] / internal[anchor] - 1) if all(d in internal.index for d in required) else None
        b = float(independent[end] / independent[anchor] - 1) if full and cash_known else None
        difference = a - b if a is not None and b is not None else None
        out.append({
            "year": year, "anchorSession": anchor, "endSession": end,
            "partialYear": end < f"{year}-12-01", "expectedSessions": len(selected),
            "matchingSessions": matched, "identicalSessionCoverage": full,
            "internalReturn": a, "independentReturn": b,
            "differencePercentagePoints": difference * 100 if difference is not None else None,
            "status": ("PASS" if abs(difference) <= THRESHOLD else "FAIL") if difference is not None else "INSUFFICIENT_DATA",
            "explanation": "same ETF market-price adjustment recipe, independent official cash records" if b is not None else "full annual official distribution history unavailable; no zero-dividend assumption",
        })
    return out


def run(root, source_dir):
    spec = contract.load(root)
    benchmark_only(spec["benchmark"])
    sources = verified_sources(source_dir)
    p = Path(source_dir)
    market, nav = issuer_prices(p / sources["files"]["issuerPrices"]["path"])
    vendor = vendor_prices(p / sources["files"]["vendorPrices"]["path"])
    internal, identity = frozen_benchmark(root, spec)
    cutoff = spec["developmentCutoff"]
    days = RC.sessions("2012-01-01", cutoff, "KR")
    distribution_path = p / sources["files"]["issuerDistributions"]["path"]
    cash_payload = json.loads(distribution_path.read_text())["dividList"]
    cash_crosscheck = crosscheck_distributions(
        distribution_path, p / sources["files"]["issuerDistributionsXls"]["path"]
    )
    last_record = max([pd.Timestamp(r["basicD"]) for r in cash_payload] + [pd.Timestamp(cutoff)])
    distribution_days = RC.sessions("2012-01-01", str(last_record.date()), "KR")
    distributions = issuer_distributions(distribution_path, distribution_days)
    distributions = [r for r in distributions if r["exDate"] <= cutoff]
    # Clip every input before return calculations; source capture is not cutoff.
    market, nav, vendor, internal = [s[s.index <= cutoff] for s in (market, nav, vendor, internal)]
    adjusted = adjusted_index(market, distributions)
    shareholder = adjusted_index(market, distributions, shareholder=True)
    years = list(range(2013, 2027))
    coverage = distributions[0]["exDate"] if distributions else None
    comparisons = annual_comparison(internal, adjusted, days, years, coverage_from=coverage, cutoff=cutoff)
    for row in comparisons:
        row.update(internalReplayManifestSha256=identity["replayManifestSha256"],
                   independentPricesSha256=sources["files"]["issuerPrices"]["sha256"],
                   independentDistributionsSha256=sources["files"]["issuerDistributions"]["sha256"],
                   internalDefinitionRef="comparedDefinitions.internal",
                   independentDefinitionRef="comparedDefinitions.independent")
    diagnostics = []
    for row in comparisons:
        a, b = row["anchorSession"], row["endSession"]
        diagnostics.append({"year": row["year"],
                            "officialPriceOnlyReturn": float(market[b] / market[a] - 1) if a in market and b in market else None,
                            "navPriceOnlyReturn": float(nav[b] / nav[a] - 1) if a in nav and b in nav else None,
                            "vendorAdjustedReturn": float(vendor[b] / vendor[a] - 1) if a in vendor and b in vendor else None,
                            "shareholderReinvestedReturn": float(shareholder[b] / shareholder[a] - 1) if coverage is not None and a >= coverage and a in shareholder and b in shareholder else None,
                            "priceAndNavVersusAdjustedIndex": "NOT_COMPARABLE"})
    adjustments = []
    for row in distributions:
        ex = row["exDate"]
        pos = int(days.searchsorted(pd.Timestamp(ex)))
        prev = str(days[pos - 1].date())
        if not all(d in s.index for s in (market, vendor, internal) for d in (prev, ex)):
            continue
        raw_growth = market[ex] / market[prev]
        adjustments.append({**row, "previousSession": prev,
                            "officialSingleAdjustmentFactor": 1 / (1 - row["cashKrwPerUnit"] / market[prev]),
                            "vendorToRawGrowthFactor": float((vendor[ex] / vendor[prev]) / raw_growth),
                            "internalToRawGrowthFactor": float((internal[ex] / internal[prev]) / raw_growth),
                            "internalToVendorGrowthFactor": float((internal[ex] / internal[prev]) / (vendor[ex] / vendor[prev]))})
    required = [r for r in comparisons if r["year"] in spec["chronology"]["evaluationYears"]]
    aggregate = "FAIL" if any(r["status"] == "FAIL" for r in required) else (
        "PASS" if all(r["status"] == "PASS" for r in required) else "INSUFFICIENT_DATA"
    )
    contract.load(root)
    return {
        "schema": "KR_ALPHA_ATLAS_BENCHMARK_ONLY_AUDIT_V1", "ticker": TICKER,
        "scope": "BENCHMARK_ONLY_NO_STOCK_ALPHA", "status": aggregate,
        "specFileSha256": contract.file_hash(Path(root) / contract.SPEC),
        "auditDependencyHashes": {p: contract.file_hash(Path(root) / p) for p in [
            "pipeline/kr_alpha_atlas_benchmark_audit.py", "scripts/audit_kr_alpha_atlas_benchmark.py",
            "requirements-kr-alpha-atlas-integrity-audit.txt"]},
        "developmentCutoff": cutoff, "thresholdReturnDifference": THRESHOLD,
        "sources": sources, "internalIdentity": identity,
        "distributionFormatCrosscheck": cash_crosscheck,
        "comparedDefinitions": {"internal": spec["targets"]["gross"],
                                "independent": "official ETF market close / (prior close - official gross distribution); same Yahoo adjusted-index recipe",
                                "cashCoverageFrom": coverage,
                                "cashTiming": "last registered KR session before issuer record date; ex-date, not payment date",
                                "taxAndCosts": "gross before investor tax and trading costs; fund fees embedded in ETF prices",
                                "shareholderDiagnostic": "(close + distribution) / prior close; distinct reinvestment convention, never used to choose a passing definition"},
        "requiredEvaluationYears": spec["chronology"]["evaluationYears"],
        "annualComparisons": comparisons, "definitionDiagnostics": diagnostics,
        "distributionAdjustmentDiagnostics": adjustments,
        "sourceLimitations": ["issuer exposes only most recent 20 cash records; earlier years cannot be certified",
                              "fresh Naver is the original vendor lineage, a mechanism diagnostic, not independent verification",
                              "frozen benchmark corporate-event rows absent; original Yahoo benchmark event amounts not preserved",
                              "ETF market, NAV, index and shareholder returns are not interchangeable"],
        "benchmarkIntegrityUnchanged": spec["benchmarkIntegrity"],
        "registrationAmendmentImplemented": False,
        "benchmarkOnlyAnnualComparisons": len(comparisons),
        "realHistoricalAlphaOutcomeReads": 0, "realForwardLabels": 0,
        "realHistoricalModelFits": 0, "realPortfolioBacktests": 0,
        "formalExecutionDispatches": 0, "permanentExecutionLocksCreated": 0,
    }
