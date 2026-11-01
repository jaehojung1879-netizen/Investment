"""Exact Git-blob adapters for already published artifacts, never strategy imports."""
import csv
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
WEEKLY = "docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json"
DISCOVERY = "research/historical_alpha_discovery_v1/"


class GitSources:
    def __init__(self, repo, pins):
        self.repo = Path(repo)
        self.pins = pins
        self.read = {}

    def blob(self, commit, path):
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("EXACT_COMMIT_REQUIRED")
        key = commit + ":" + path
        expected = self.pins["blobs"].get(key)
        if expected is None:
            raise ValueError("UNPINNED_SOURCE_REFUSED")
        raw = subprocess.check_output(["git", "show", key], cwd=self.repo)
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise ValueError("SOURCE_SHA256_MISMATCH")
        self.read[key] = actual
        return raw

    def json(self, commit, path):
        return json.loads(self.blob(commit, path))

    def hashes(self, commit, paths):
        return {p: self.pins["blobs"][commit + ":" + p] for p in paths}


def weekly_pairs(source):
    commit = source.pins["mainCommit"]
    obj = source.json(commit, WEEKLY)
    # Establish the NET interpretation from the original documentation/code; no rerun.
    docs = [WEEKLY, "docs/weekly-passive-first-v1.md", "scripts/run_weekly_passive_first_replay.py"]
    for doc in docs[1:]:
        source.blob(commit, doc)
    pairs = []
    for region, payload in obj["regions"].items():
        def adapt(key):
            return {
                "region": region, "strategyId": key, "studyId": obj["id"],
                "sourceStudyId": obj["id"],
                "upstreamRegionalPathsContentSha256": obj["regionalPathsSha256"],
                "notMarketC1FormalStudy": True,
                "strategyMeaning": {"C1": "REGIONAL_CHAMPION_WITH_RESIDUAL_CASH_NOT_MARKET_C1", "C2": "SAME_CHAMPION_WITH_RESIDUAL_ETF_NOT_MARKET_C2", "P0": "REGIONAL_ETF_BUY_AND_HOLD", "P1": "PASSIVE_FIRST_AT_21_SESSION_ANCHORS"}[key],
                "instrument": payload["benchmark"] if key == "P0" else None,
                "currency": payload["baseCurrency"], "frequency": "WEEKLY",
                "valueType": "NAV_LEVEL",
                "sourceNavRounding": "SIX_DECIMAL_WEEKLY_LEVELS",
                "decisionCadence": obj["calendar"]["cadence"],
                "returnBasis": payload["benchmarkDefinition"] if key == "P0" else "REPLAY_STOCK_AND_CASH_OR_ETF_MIX_PARTIAL_SHAREHOLDER_ECONOMICS",
                "costBasis": "NET_ALREADY_CHARGED", "costScenario": "ORIGINAL_REALISTIC_TRADE_COST_SCHEDULE",
                "evidenceClass": obj["evidenceClass"], "sourceStatus": payload["status"],
                "sourceCommit": commit, "hashes": source.hashes(commit, docs),
                "fxReturnsIncluded": payload["fxReturnsIncluded"],
                "sourceHeadlineEligible": payload["headlineEligible"], "headlineFlagUsedForAdmission": False,
                "sourceReportedOriginalStart": payload["paths"][key]["startDate"],
                "sourceReportedDailyCagrPct_NOT_RECOMPUTED": payload["paths"][key]["cagrPct"],
                "limitations": ["WEEKLY_NAV_NOT_DAILY", "STARTS_AFTER_ORIGINAL_CAPITAL_DATE_FIRST_INTERVAL_NOT_RECONSTRUCTED", "NO_COMPLETE_POSITION_TRADE_LEDGER_CONSUMED", "NET_TRADING_COSTS_DO_NOT_PROVE_INVESTOR_TAX_OR_COMPLETE_SHAREHOLDER_RETURN", payload["status"]],
                "nav": payload["weeklyNav"][key],
            }
        for key in ("C1", "C2", "P1"):
            pairs.append((f"A/{region}/{key}-P0", adapt(key), adapt("P0")))
    return pairs


def discovery_pairs(source):
    commit = source.pins["discoveryCommit"]
    spec = source.json(commit, DISCOVERY + "spec.json")
    obj = source.json(commit, DISCOVERY + "results/summary.json")
    coverage = source.json(commit, DISCOVERY + "results/coverage.json")
    manifest = source.json(commit, DISCOVERY + "results/manifest.json")
    counts_path = DISCOVERY + "results/portfolio-summary.csv"
    counts = list(csv.DictReader(io.StringIO(source.blob(commit, counts_path).decode())))
    source.blob(commit, DISCOVERY + "run.py")  # frozen declared calendar/cost convention
    portfolios = obj["portfolios"]
    by_key = {(p["analysisWindow"], p["sample"], p["horizon"], p["costMultiplier"], p["book"]): p for p in portfolios}
    pairs, blocked = [], []
    shared = [DISCOVERY + p for p in ("spec.json", "run.py", "results/summary.json", "results/coverage.json", "results/manifest.json", "results/portfolio-summary.csv")]
    for p in portfolios:
        if p["book"] == "ETF":
            continue
        key = (p["analysisWindow"], p["sample"], p["horizon"], p["costMultiplier"])
        identifier = "B/" + "/".join(str(x) for x in (*key, p["book"] + "-ETF"))
        if not p["complete"]:
            count = next(c for c in counts if all(str(c[k]) == str(p[k]) for k in ("analysisWindow", "sample", "horizon", "costMultiplier", "book")))
            blocked.append({"id": identifier, "status": "BLOCKED", "reason": "ORIGINAL_COMPOUNDED_NAV_INCOMPLETE_NO_STITCHING",
                            "originalStudy": obj["study"], "sourceCommit": commit,
                            "hashes": source.hashes(commit, shared),
                            "sourceScheduledBlockCount": sum(c["analysisWindow"] == key[0] and c["sample"] == key[1] and c["horizon"] == key[2] for c in coverage),
                            "sourcePricedBlockCount": int(count["pricedBlocks"]),
                            "sourceMissingBlockCount": int(count["scheduledBlocks"]) - int(count["pricedBlocks"]),
                            "fullPeriodReturn": None})
            continue
        if not by_key[(*key, "ETF")]["complete"]:
            raise ValueError("COMPLETE_BENCHMARK_REQUIRED")

        def adapt(book):
            path = DISCOVERY + "results/nav-" + "-".join(str(x) for x in (*key, book)) + ".csv"
            raw = source.blob(commit, path)
            if hashlib.sha256(raw).hexdigest() != manifest["filesSha256"][path[len(DISCOVERY):]]:
                raise ValueError("ORIGINAL_MANIFEST_NAV_MISMATCH")
            nav = [[r["date"], float(r["nav"])] for r in csv.DictReader(io.StringIO(raw.decode()))]
            declared = by_key[(*key, book)]["metrics"]
            if (nav[0][0] != declared["from"] or nav[-1][0] != declared["through"]
                    or len(nav)-1 != declared["dailyObservations"]):
                raise ValueError("COMPLETE_CSV_DOES_NOT_MATCH_ORIGINAL_SAMPLE_BOUNDS")
            return {
                "region": "KR", "strategyId": book, "studyId": obj["study"], "instrument": "069500.KS" if book == "ETF" else None,
                "currency": "KRW", "frequency": "DAILY", "calendarPolicy": "XKRX_DISCOVERY_V1",
                "valueType": "NAV_LEVEL",
                "returnBasis": "CORRECTED_GROSS_ETF_DISTRIBUTIONS" if book == "ETF" else "SPLIT_CONTINUOUS_PARTIAL_STOCK_DISTRIBUTIONS",
                "costBasis": "NET_ALREADY_CHARGED", "costScenario": f"ORIGINAL_{key[3]}X_ALREADY_CHARGED",
                "evidenceClass": obj["evidenceClass"], "sourceCommit": commit,
                "hashes": source.hashes(commit, shared + [path]),
                "originalHoldingHorizonLabel": key[2], "analysisWindow": key[0], "sample": key[1],
                "sourceCompleteFlag": True, "sourceReturnDefinition": spec["returnBasis"],
                "sourceCostDefinition": spec["costs"], "limitations": obj["limitations"], "nav": nav,
            }
        pairs.append((identifier, adapt(p["book"]), adapt("ETF")))
    return pairs, blocked
