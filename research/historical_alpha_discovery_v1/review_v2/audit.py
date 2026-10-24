"""Audit existing KR study outputs and source-derived blocked legs, not a sealed executor."""

from __future__ import annotations
import base64
import gzip
import hashlib
from html import unescape
import json
import math
from pathlib import Path
import re
import statistics

import numpy as np
import pandas as pd
from .. import run as R

HERE = Path(__file__).resolve().parent


def endpoint(prices, volumes, dates, *, entry, exit_day, split_events=(), barred_dates=()):
    """Only end wealth, without inventing any halted mark or terminal payoff."""
    if any(entry < d <= exit_day for d in barred_dates):
        raise ValueError("UNVALUED_RIGHT_CROSSED")
    a, b = dates.index(entry), dates.index(exit_day)
    if not (prices[a] > 0 and prices[b] > 0 and volumes[a] > 0 and volumes[b] > 0):
        raise ValueError("NONEXECUTABLE_ENDPOINT")
    selected_splits = [s for d, s in split_events if entry < d <= exit_day]
    if any(s not in (1.0, 10.0) for s in selected_splits):
        raise ValueError("UNREVIEWED_DISTRIBUTION_OR_SPLIT_FACTOR")
    factor = math.prod(selected_splits)
    if any(not np.isfinite(x) or x <= 0 for x in prices[a : b + 1]):
        raise ValueError("QUOTE_GAP")
    return {
        "grossEndpointReturn": factor * prices[b] / prices[a] - 1,
        "zeroVolumeMarks": sum(x <= 0 for x in volumes[a : b + 1]),
        "dailyRiskAvailable": all(x > 0 for x in volumes[a : b + 1]),
    }


def immutable_originals():
    original = json.loads((R.HERE / "results/manifest.json").read_text())
    for name, sha in original["filesSha256"].items():
        if hashlib.sha256((R.HERE / name).read_bytes()).hexdigest() != sha:
            raise ValueError("ORIGINAL_ARTIFACT_CHANGED:" + name)
    return len(original["filesSha256"])


def check_metrics():
    summary = json.loads((R.HERE / "results/summary.json").read_text())
    blocks = json.loads((R.HERE / "results/blocks.json").read_text())
    checks = []
    for row in summary["portfolios"]:
        if not row["complete"]:
            assert row["metrics"] is None
            continue
        name = "nav-{analysisWindow}-{sample}-{horizon}-{costMultiplier}-{book}.csv".format(**row)
        frame = pd.read_csv(R.HERE / "results" / name)
        v = frame.nav.to_numpy()
        r = (v[1:] / v[:-1] - 1).tolist()
        days = pd.to_datetime(frame.date)
        assert list(days) == list(R.calendar(str(days.iloc[0].date()), str(days.iloc[-1].date())))
        years = (days.iloc[-1] - days.iloc[0]).days / 365.25
        actual = {
            "totalReturn": v[-1] - 1,
            "cagr": v[-1] ** (1 / years) - 1,
            "sharpeZeroRf": statistics.mean(r) / statistics.stdev(r) * math.sqrt(252),
            "mdd": min(float(x / max(v[: i + 1]) - 1) for i, x in enumerate(v)),
            "dailyCvar95": statistics.mean(x for x in r if x <= np.quantile(r, 0.05)),
            "annualDownsideDeviation": math.sqrt(statistics.mean(min(x, 0) ** 2 for x in r)) * math.sqrt(252),
        }
        gap = max(abs(float(val) - row["metrics"][k]) for k, val in actual.items())
        assert gap < 1e-8, (name, gap)
        selected = [
            b
            for b in blocks
            if all(b[k] == row[k] for k in ["analysisWindow", "sample", "horizon", "costMultiplier", "book"])
        ]
        compound = math.prod(1 + b["netReturn"] for b in selected) - 1
        assert abs(compound - row["metrics"]["totalReturn"]) < 1e-8
        checks.append(
            {"nav": name, "maximumMetricGap": gap, "compoundGap": abs(compound - row["metrics"]["totalReturn"])}
        )
    # Paired statistics must refer to the same individual priced blocks.
    for comparison in summary["intradayVsMomentum"] + summary["pairedComparisons"]:
        matching = [
            b
            for b in blocks
            if all(b[k] == comparison[k] for k in ["analysisWindow", "sample", "horizon", "costMultiplier"])
        ]
        control = {b["entry"]: b for b in matching if b["book"] == comparison["control"]}
        delta = [
            b["netReturn"] - control[b["entry"]]["netReturn"]
            for b in matching
            if b["book"] == comparison["book"]
            and b["netReturn"] is not None
            and control[b["entry"]]["netReturn"] is not None
        ]
        assert len(delta) == comparison["validPairs"]
        if delta:
            assert abs(statistics.mean(delta) - comparison["meanBlockExcess"]) < 1e-8
        if len(delta) < 12:
            assert comparison["descriptiveYearBootstrap95"] is None
    return checks


def issuer_evidence():
    findings = []
    selected = {("002790.KS", 2015), ("090430.KS", 2016), ("009830.KS", 2023), ("012450.KS", 2024)}
    base = R.ROOT / "data/kr-industry-membership-foundation-v2/acquired-dart/annual"
    for manifest in sorted(base.glob("*/manifest-originals.json")):
        doc = json.loads(manifest.read_text())
        records = [
            r
            for r in doc["records"]
            if (r.get("target", {}).get("ticker"), r.get("target", {}).get("fiscalYear")) in selected
        ]
        if not records:
            continue
        archive = manifest.parent / doc["archive"]
        raw = archive.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == doc["archiveSha256"]
        bodies = json.loads(gzip.decompress(raw))
        for row in records:
            for section in row.get("sections", []):
                decoded = base64.b64decode(bodies[section["sha256"]])
                assert hashlib.sha256(decoded).hexdigest() == section["sha256"]
                text = re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", unescape(decoded.decode("utf8", errors="replace"))))
                if row["target"]["ticker"] == "012450.KS":
                    marker = "2024년 9월 1일"
                elif row["target"]["ticker"] == "009830.KS":
                    marker = "인적분할"
                else:
                    marker = "액면분할"
                found = text.find(marker)
                responses = [r for r in row["responses"] if r.get("sha256") == section["sha256"]]
                findings.append(
                    {
                        "ticker": row["target"]["ticker"],
                        "receipt": row["target"]["receiptNos"],
                        "archive": str(archive.relative_to(R.ROOT)),
                        "archiveSha256": doc["archiveSha256"],
                        "sectionSha256": section["sha256"],
                        "url": responses[0]["url"] if responses else None,
                        "marker": marker,
                        "markerFound": found >= 0,
                        "excerpt": text[max(0, found - 60) : found + 600] if found >= 0 else None,
                        "publicationIsAfterHistoricalSignal": True,
                        "use": "OUTCOME_SOURCE_AUDIT_ONLY_NEVER_SIGNAL_BACKFILL",
                    }
                )
    return findings


def execute():
    old_count = immutable_originals()
    metrics = check_metrics()
    source, _, m, _, _, _, _ = R.load_inputs()
    old = json.loads((R.HERE / "results/summary.json").read_text())
    assert source.identities == old["sourceHashes"]
    blocks = json.loads((R.HERE / "results/blocks.json").read_text())
    primary = [
        b
        for b in blocks
        if b["analysisWindow"] == "FULL"
        and b["sample"] == R.SPEC["samples"][0]
        and b["horizon"] == 126
        and b["costMultiplier"] == 1
        and b["book"] == "INTRADAY"
    ]
    manifest = json.loads(source.blob("ledger/historical/replay-v16/inputs.json"))
    events = []
    for name, refs in manifest["components"].items():
        if name.startswith("corporate-events/20"):
            for ref in refs:
                raw = gzip.decompress(source.blob("ledger/replay-inputs/objects/" + ref + ".json.gz"))
                assert hashlib.sha256(raw).hexdigest() == ref
                events.extend(json.loads(raw))
    mirae_path = (
        R.ROOT / "docs/audits/kr-alpha-atlas-phase-c-integrity/mirae-source-recovery/006800-source-correction.json"
    )
    mirae = json.loads(mirae_path.read_text())
    evidence = issuer_evidence()
    cases = []
    for b in primary:
        for failure in b["failures"]:
            ticker = failure["ticker"]
            entry = b["entry"]
            end = b["exit"]
            own = [e for e in events if e["ticker"] == ticker and entry < e["date"] <= end]
            row = {
                "ticker": ticker,
                "entry": entry,
                "exit": end,
                "originalReason": failure["reason"],
                "events": own,
                "dailyPortfolioRiskRecovered": False,
                "wholeBookReconstructed": False,
            }
            if ticker in {"009830.KS", "012450.KS"}:
                row.update(
                    status="BLOCKED_DISTRIBUTED_SECURITY_ECONOMICS",
                    reason="Stored issuer sections corroborate demerger/consolidation changes but do not establish complete parent-to-distributed-security entitlement. Parent-only noninteger vendor split cannot value cash-in-lieu or the distributed security.",
                    successorCandidate="452260.KS" if ticker == "009830.KS" else "489790.KS",
                )
            else:
                dates = [str(d.date()) for d in m["close"].index]
                c = m["close"][ticker].to_list()
                v = m["volume"][ticker].to_list()
                if ticker == "006800.KS":
                    assert not any(entry < e["date"] <= end for e in mirae["registeredPartialEvents"])
                    assert all(d < entry for d in mirae["quarantinedSessions"])
                    # Exact same-session quote agreement with already-preserved repair, no sealed function called.
                    q = {r["date"]: r["close"] for r in mirae["rawQuotes"]}
                    assert c[dates.index(entry)] == q[entry] and c[dates.index(end)] == q[end]
                    interval = range(dates.index(entry), dates.index(end) + 1)
                    assert all(dates[i] in q and c[i] == q[dates[i]] for i in interval)
                    result = endpoint(c, v, dates, entry=entry, exit_day=end, barred_dates=mirae["quarantinedSessions"])
                    row.update(
                        status="RECOVERED_SEPARATE_2025_QUOTE_INTERVAL",
                        sourceRepairSha256=hashlib.sha256(mirae_path.read_bytes()).hexdigest(),
                        **result,
                    )
                else:
                    splits = [(e["date"], e["split"]) for e in own if e.get("split", 1) != 1]
                    assert len(splits) == 1 and splits[0][1] == 10 and not any(e.get("dividend") for e in own)
                    day, ratio = splits[0]
                    i = dates.index(day)
                    before = i - 1
                    while v[before] <= 0:
                        before -= 1
                    shares = m["listedShares"][ticker]
                    assert float(shares.iloc[i] / shares.iloc[before]) == ratio
                    result = endpoint(c, v, dates, entry=entry, exit_day=end, split_events=splits)
                    row.update(status="RECOVERED_SPLIT_ENDPOINT_ONLY", officialShareRatio=ratio, **result)
                a, z = dates.index(entry), dates.index(end)
                replay = m["adjusted"][ticker].iloc[z] / m["adjusted"][ticker].iloc[a] - 1
                row["originalReplayEndpointDiagnostic"] = float(replay)
                row["netSingleNameReturnDiagnostic"] = (1 + row["grossEndpointReturn"]) / (
                    1 + R.cost(entry, stock=True, sell=False)
                ) * (1 - R.cost(end, stock=True, sell=True)) - 1
                row["basis"] = "SOURCE_REGISTERED_PARTIAL_DISTRIBUTIONS_NOT_COMPLETE_TOTAL_RETURN"
            cases.append(row)
    result = {
        "auditCodeSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "review": json.loads((HERE / "plan.json").read_text()),
        "originalFilesHashVerified": old_count,
        "completeNavChecks": metrics,
        "sourceHashes": source.identities,
        "issuerEvidence": evidence,
        "blockedLegReview": cases,
        "pit": "Strict historical selection and past-only price windows, but reconstructed industries/revised source are not certified contemporary PIT; conditional survivor sample explicitly ex-post.",
        "costFinding": "Frozen executable uses 2019-06-03 dated 30->25bps sell tax. Original spec note agrees; original stockSellTaxBps key 2019ConservativeFullYear is contradictory metadata. No original bytes changed or return-optimized tax choice.",
        "returnFinding": "Original proxy numbers reproduce. Stock partial distributions versus ETF gross distributions do NOT establish equal complete shareholder-return basis.",
        "statisticalConclusion": "NO_RELIABLE_INCREMENTAL_ALPHA; missing selected paths and small paired samples prevent promotion. Recovered components do not recover full strategy NAV or risk.",
    }
    (HERE / "audit-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "originalFiles": old_count,
                "navChecks": len(metrics),
                "cases": [
                    {k: r.get(k) for k in ["ticker", "status", "grossEndpointReturn", "zeroVolumeMarks"]} for r in cases
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    execute()
