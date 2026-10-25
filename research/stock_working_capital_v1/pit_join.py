"""Pinned local input measurement only. No return labels, models or execution.

Default PLAN_ONLY. --inspect --output <new directory> writes non-actionable
crosswalk receipts and coverage, preserving every intended member. Exit 3 means
measured but source admission blocked; exit 4 means infrastructure/source error.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import base64
import gzip
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import subprocess

import exchange_calendars as xc

from pipeline import kr_industry_membership_v3 as V3
from . import features as F
from . import pit_admission as A
from . import pit_filing_evidence as E

ROOT = Path(__file__).resolve().parents[2]
RAW_COMMIT = "1bf68f59cffa20239977e2cfaa0f35a07d0ec884"
EVIDENCE_COMMIT = "b589d658eedd3c47f555df20db86f37792ee3358"
D2 = "data/kr-industry-membership-foundation-v2/acquired-dart/annual"
D3 = "data/kr-industry-membership-foundation-v3"
INTERVALS = "data/kr-industry-membership-foundation-v4/state/intervals.json.gz"
CROSSWALK = "research_specs/kr-industry-membership-foundation-v4/crosswalk.json"
TERMINAL = "docs/results/kr-termination-inventory.json"  # identity metadata only, no return fields
EVENTS = D3 + "/state/events.json.gz"


class PinnedInputs:
    def __init__(self, root):
        self.root, self.receipts, self.notice_hashes = Path(root), {}, set()

    def blob(self, commit, path):
        raw_allowed = re.fullmatch(r"ledger/(?:fundamentals/kr-raw/raw|universe/kr/krx-universe|prices/kr/krx-prices)-20\d{2}\.jsonl\.gz", path)
        annual_allowed = re.fullmatch(re.escape(D2) + r"/batch-(?:0\d|1\d|2[0-5])/(?:manifest-originals\.json|originals\.json\.gz)", path)
        notice_hash = path.removeprefix(D3 + "/notices/").removesuffix(".bin")
        notice_allowed = path == D3 + "/notices/" + notice_hash + ".bin" and notice_hash in self.notice_hashes
        evidence_allowed = path in {INTERVALS, CROSSWALK, TERMINAL, EVENTS} or annual_allowed or notice_allowed
        if not ((commit == RAW_COMMIT and raw_allowed) or (commit == EVIDENCE_COMMIT and evidence_allowed)):
            raise ValueError("NON_INPUT_OR_UNPINNED_PATH_REFUSED:" + path)
        p = subprocess.run(["git", "cat-file", "blob", commit + ":" + path], cwd=self.root,
                           env={**os.environ, "GIT_NO_LAZY_FETCH": "1"}, capture_output=True)
        if p.returncode:
            raise ValueError("PINNED_LOCAL_SOURCE_UNAVAILABLE:" + path)
        self.receipts[commit + ":" + path] = {"sha256": E.sha(p.stdout), "bytes": len(p.stdout)}
        return p.stdout

    def json(self, path):
        raw = self.blob(EVIDENCE_COMMIT, path)
        return json.loads(gzip.decompress(raw) if path.endswith(".gz") else raw)

    def rows(self, path):
        raw = self.blob(RAW_COMMIT, path)
        return [json.loads(line) for line in gzip.decompress(raw).splitlines() if line.strip()]


def load_originals(source):
    originals, diagnostics = defaultdict(list), Counter()
    for batch in range(26):
        prefix = f"{D2}/batch-{batch:02d}/"
        manifest = source.json(prefix + "manifest-originals.json")
        if manifest.get("archive") != "originals.json.gz":
            raise ValueError("ORIGINAL_ARCHIVE_REFERENCE_CHANGED")
        raw = source.blob(EVIDENCE_COMMIT, prefix + "originals.json.gz")
        if E.sha(raw) != manifest["archiveSha256"]:
            raise ValueError("ORIGINAL_ARCHIVE_DIGEST_MISMATCH")
        bodies = json.loads(gzip.decompress(raw))
        for record in manifest["records"]:
            target = record["target"]
            receipts = target.get("receiptNos", [])
            if len(receipts) != 1:
                diagnostics["TARGET_RECEIPT_AMBIGUOUS"] += 1
                continue
            key = target["ticker"], target["fiscalYear"], receipts[0]
            main = next((r for r in record["responses"] if not r.get("section")), None)
            if main is None or main.get("status") != 200:
                diagnostics["ORIGINAL_MAIN_NOT_SERVED"] += 1
                originals[key].append({"evidenceError": "ORIGINAL_MAIN_NOT_SERVED"})
                continue
            body = base64.b64decode(bodies[main["sha256"]], validate=True)
            if E.sha(body) != main["sha256"]:
                raise ValueError("ORIGINAL_MAIN_BODY_DIGEST_MISMATCH")
            try:
                evidence = E.original_main(target, body, main["url"])
            except (ValueError, KeyError, UnicodeError) as exc:
                reason = str(exc)
                diagnostics[reason] += 1
                evidence = {"evidenceError": reason}
            else:
                diagnostics["ORIGINAL_LIST_ROW_AND_MAIN_MATCH"] += 1
            originals[key].append(evidence)
    return originals, dict(sorted(diagnostics.items()))


def bridge_event_issuer(event, originals):
    """Use only original annual identity evidence PUBLIC BEFORE the notice.

    A current directory or an annual report first filed after the notice cannot
    certify the issuer behind an old industry event for a reused security code.
    """
    candidates = [m for key, values in originals.items() if key[0] == event["ticker"]
                  for m in values if not m.get("evidenceError") and m["availableFrom"] < event["notice_date"]]
    if not candidates:
        return {"issuerCorpCode": None, "issuerBridgeSourceSha256": None, "issuerBridgeAvailableFrom": None}
    stamp = max(m["availableFrom"] for m in candidates)
    latest = [m for m in candidates if m["availableFrom"] == stamp]
    if (len({(m["corpCode"], m["mainSha256"]) for m in latest}) != 1
            or E.normal_name(latest[0]["companyName"]) != E.normal_name(event["identity"]["company"])):
        return {"issuerCorpCode": None, "issuerBridgeSourceSha256": None, "issuerBridgeAvailableFrom": None}
    m = latest[0]
    return {"issuerCorpCode": m["corpCode"], "issuerBridgeSourceSha256": m["mainSha256"],
            "issuerBridgeAvailableFrom": m["availableFrom"]}


def load_industry_events(source, originals):
    events, rejected = defaultdict(list), Counter()
    stored = source.json(EVENTS)
    source.notice_hashes = {e[k] for e in stored for k in ("document_sha256", "viewer_sha256")}
    for e in stored:
        blobs = {}
        for kind in ("document", "viewer"):
            h = e[kind + "_sha256"]
            body = source.blob(EVIDENCE_COMMIT, D3 + "/notices/" + h + ".bin")
            if E.sha(body) != h:
                raise ValueError("INDUSTRY_NOTICE_DIGEST_MISMATCH")
            blobs[kind] = V3.decode(body)[0]
        parsed = V3.parse_notice(blobs["document"], blobs["viewer"])
        fields = ("effective_date", "before_label", "after_label", "identity", "status")
        if any(parsed.get(k) != e.get(k) for k in fields) or parsed.get("status") != "PARSED":
            rejected["INDUSTRY_NOTICE_REPARSE_MISMATCH"] += 1
            continue
        if (e["identity"]["stock_code"] + ".KS" != e["ticker"]
                or e["receipt_no"][:8] != e["notice_date"].replace("-", "")
                or not e["document_url"].startswith("https://kind.krx.co.kr/external/")):
            rejected["INDUSTRY_NOTICE_IDENTITY_OR_DATE_MISMATCH"] += 1
            continue
        F.day(e["notice_date"])
        F.day(e["effective_date"])
        events[e["ticker"]].append({**e, **bridge_event_issuer(e, originals)})
    return events, {"retainedNotices": sum(map(len, events.values())), "rejectedByReason": dict(rejected),
                    "noticesWithPreNoticeIssuerBridge": sum(e["issuerCorpCode"] is not None for v in events.values() for e in v),
                    "existingParserSha256": E.sha((ROOT / "pipeline/kr_industry_membership_v3.py").read_bytes())}


def signal_bar_status(record):
    close, volume = record.get("close"), record.get("volume")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (close, volume)):
        return "MISSING_OR_INVALID_SIGNAL_BAR_COMPONENT"
    if close <= 0 or volume < 0:
        return "INVALID_SIGNAL_BAR"
    return "OBSERVED_TRADABLE_SIGNAL_BAR" if volume > 0 else "ZERO_VOLUME_NONTRADABLE_SIGNAL_BAR"


def source_demand(cohorts, rows):
    """Prioritise missing original evidence by INPUT coverage, never returns.

    This is a retrieval worklist, not a reduced investment universe or approved
    historical sample. Every other intended member stays in the main receipts.
    """
    by_date = {c["signal"]: c for c in cohorts}
    demand, summaries = {}, {}
    for signal in F.SIGNALS:
        usable = [r for r in rows if r["signals"][signal]["inputReadable"] and r["datedIdentityMatched"]
                  and r["industryIssuerMatched"] and not by_date[r["signal"]]["reasons"]
                  and r["tradingStatus"] == "OBSERVED_TRADABLE_SIGNAL_BAR"]
        receipts = set()
        for r in usable:
            for leg in r["filingReceipts"]:
                for receipt in leg:
                    receipts.add(receipt)
                    d = demand.setdefault(receipt, {"receipt": receipt, "tickers": set(), "neededFor": set(),
                        "originalPackageUrl": f"https://opendart.fss.or.kr/api/fnlttXbrl.xml?rcept_no={receipt}&reprt_code=11011"})
                    d["tickers"].add(r["ticker"])
                    d["neededFor"].add(signal)
        summaries[signal] = {"memberDatesPassingOtherInputGates": len(usable),
                             "distinctSecurities": len({r["ticker"] for r in usable}),
                             "originalReceiptsNeeded": len(receipts)}
    return {"status": "INPUT_ONLY_RETRIEVAL_WORKLIST_NOT_AN_INVESTMENT_SAMPLE", "bySignal": summaries,
            "distinctOriginalReceipts": len(demand),
            "requests": [{k: sorted(v) if isinstance(v, set) else v for k, v in d.items()}
                         for _, d in sorted(demand.items())],
            "warning": "No request made. Do not lower sample minima or remove other intended names to execute this coverage-selected subset."}


def inspect(source):
    calendar = xc.get_calendar("XKRX", start="2015-01-01", end="2026-01-31")
    sessions = [str(s.date()) for s in calendar.sessions]
    signals = [s for s in sessions if "2017-01-01" <= s <= "2025-08-29" and F.day(s).weekday() == 4]
    universe, filings = [], []
    for year in range(2016, 2026):
        universe.extend(source.rows(f"ledger/universe/kr/krx-universe-{year}.jsonl.gz"))
    for year in range(2015, 2025):
        filings.extend(r for r in source.rows(f"ledger/fundamentals/kr-raw/raw-{year}.jsonl.gz") if r.get("reportCode") == "11011")
    snapshots = A.TopSnapshots(universe, sessions)
    signal_set = set(signals)
    trading = {}
    for year in range(2017, 2026):
        for r in source.rows(f"ledger/prices/kr/krx-prices-{year}.jsonl.gz"):
            # Only contemporaneous signal close/volume is projected, never a
            # future entry/end price, holding return or historical label.
            if r["date"] not in signal_set:
                continue
            key = r["date"], r["ticker"]
            if key in trading:
                raise ValueError("DUPLICATE_SIGNAL_SESSION_PRICE_KEY")
            trading[key] = signal_bar_status(r)
    originals, original_diagnostics = load_originals(source)
    events, event_diagnostics = load_industry_events(source, originals)
    terminal_rows = source.json(TERMINAL)["securities"]
    terminal = {r["code"]: r["lastTradingDate"] for r in terminal_rows}
    if any(not v for v in terminal.values()):
        raise ValueError("TERMINAL_LAST_TRADING_DATE_UNRESOLVED")
    worker = A.Crosswalk(snapshots=snapshots, filings=filings, originals=originals,
                         intervals=source.json(INTERVALS), events=events, crosswalk=source.json(CROSSWALK),
                         terminal=terminal, trading=trading, sessions=sessions)
    cohorts, rows = [], []
    for s in signals:
        c, r = worker.on(s)
        cohorts.append(c)
        rows.extend(r)
    report = {"schema": "STOCK_WC_PIT_JOIN_V1", "status": "INPUT_JOIN_MEASURED_ADMISSION_BLOCKED",
              "diagnosticOnly": True, "notANewSignalSchedule": True, "signalRange": [signals[0], signals[-1]],
              "scope": "All Friday KRX sessions as coverage grid; eventDue marks the original proposed per-issuer annual event.",
              "sourceCommits": {"raw": RAW_COMMIT, "evidence": EVIDENCE_COMMIT},
              "sourceReceipts": source.receipts,
              "calendar": {"sha256": F.digest(sessions), "package": importlib.metadata.version("exchange-calendars"),
                           "observed": "XKRX calendar; no holiday forward/back fill"},
              "coverage": A.coverage(cohorts, rows),
              "byYear": {str(y): A.coverage([c for c in cohorts if c["signal"][:4] == str(y)],
                                           [r for r in rows if r["signal"][:4] == str(y)]) for y in range(2017, 2026)},
              "originalSourceEvidence": original_diagnostics, "industrySourceEvidence": event_diagnostics,
              "historicalReturnLabelsRead": 0, "historicalReturnCalculations": 0, "modelFits": 0,
              "originalFinancialPackagesAvailable": 0,
              "sourceDemandSummary": {k: v for k, v in source_demand(cohorts, rows).items() if k != "requests"},
              "limits": ["Monthly Top120 carry-forward is not the exact same-session daily market-cap ranking.",
                         "Original listing/main metadata is not certification of original financial values or a 12-month fiscal start.",
                         "Dated industry notice means last publicly observed official label, not exhaustive historical event coverage.",
                         "Positive signal-date volume is not proof of an executable next-open entry or complete holding-period economics.",
                         "Known future termination is audit-only, never a survivor filter; past-ended members remain with reasons.",
                         "No portfolio, return outcome, production signal, sealed study or original WC proposal changed."]}
    return report, cohorts, rows


def canonical_lines(rows):
    return b"".join(json.dumps(r, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode() + b"\n" for r in rows)


def verify_measurement(directory):
    """Verify committed receipts and recompute coverage, not financial outcomes."""
    directory = Path(directory)
    report = json.loads((directory / "coverage.json").read_text())
    loaded = {}
    for name in ("cohorts.jsonl.gz", "rows.jsonl.gz"):
        raw = (directory / name).read_bytes()
        if E.sha(raw) != report["outputSha256"][name]:
            raise ValueError("OUTPUT_RECEIPT_DIGEST_MISMATCH:" + name)
        loaded[name] = [json.loads(r) for r in gzip.decompress(raw).splitlines()]
    if "source-demand.json" in report["outputSha256"]:
        if E.sha((directory / "source-demand.json").read_bytes()) != report["outputSha256"]["source-demand.json"]:
            raise ValueError("SOURCE_DEMAND_DIGEST_MISMATCH")
    cohorts, rows = loaded["cohorts.jsonl.gz"], loaded["rows.jsonl.gz"]
    by_date = {c["signal"]: c for c in cohorts}
    for c in cohorts:
        if c.get("intendedSha256") != F.digest({k: v for k, v in c.items() if k != "intendedSha256"}):
            raise ValueError("INTENDED_COHORT_DIGEST_MISMATCH")
    for r in rows:
        c = by_date[r["signal"]]
        members = {m["ticker"]: m for m in c["members"]}
        m = members[r["ticker"]]
        if (r["intendedSha256"] != c["intendedSha256"] or r["snapshotDate"] != c["snapshotDate"]
                or r["rankAtSnapshot"] != m["rank"]):
            raise ValueError("ROW_NOT_BOUND_TO_INTENDED_COHORT")
        for s in r["signals"].values():
            if not s["inputAdmitted"] and s["value"] is not None:
                raise ValueError("BLOCKED_INPUT_MUST_NOT_EXPOSE_SIGNAL_VALUE")
            if s["inputAdmitted"] and (s["reasons"] or not s["inputReadable"]
                    or not s["originalFinancialFactsMatched"] or not s["fiscalWindowsComparable"]
                    or not r["datedIdentityMatched"] or not r["originalMainPairMatched"]
                    or r["industry"]["group"] is None or not r["industryIssuerMatched"] or c["reasons"]
                    or r["tradingStatus"] != "OBSERVED_TRADABLE_SIGNAL_BAR"):
                raise ValueError("INPUT_ADMISSION_SEMANTICS_INCONSISTENT")
    if A.coverage(cohorts, rows) != report["coverage"]:
        raise ValueError("COVERAGE_RECEIPT_MISMATCH")
    if any(report.get(k) != 0 for k in ("historicalReturnLabelsRead", "historicalReturnCalculations", "modelFits")):
        raise ValueError("OUTSIDE_INPUT_MEASUREMENT_CONTRACT")
    return {"status": "INPUT_RECEIPTS_VERIFIED_NOT_EXECUTION_APPROVAL", "memberDates": len(rows)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inspect", action="store_true")
    p.add_argument("--output", type=Path)
    p.add_argument("--verify", type=Path)
    args = p.parse_args(argv)
    if args.verify:
        if args.inspect or args.output:
            p.error("--verify cannot be combined with measurement")
        print(json.dumps(verify_measurement(args.verify)))
        return 0
    if not args.inspect:
        print(json.dumps({"status": "PLAN_ONLY", "sourceReads": 0, "historicalReturnLabelsRead": 0}))
        return 0
    if args.output is None or args.output.exists():
        p.error("--output must be a NEW directory; never overwrite prior receipts")
    try:
        report, cohorts, rows = inspect(PinnedInputs(ROOT))
        if not cohorts or report["coverage"]["expectedMemberDates"] == 0:
            raise ValueError("EMPTY_INTENDED_POPULATION_NOT_A_SUCCESS")
        args.output.mkdir(parents=True, exist_ok=False)
        for name, data in (("cohorts.jsonl.gz", cohorts), ("rows.jsonl.gz", rows)):
            raw = gzip.compress(canonical_lines(data), mtime=0)
            (args.output / name).write_bytes(raw)
            report.setdefault("outputSha256", {})[name] = E.sha(raw)
        demand = json.dumps(source_demand(cohorts, rows), ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
        (args.output / "source-demand.json").write_bytes(demand)
        report["outputSha256"]["source-demand.json"] = E.sha(demand)
        report["codeSha256"] = {n: E.sha((Path(__file__).parent / n).read_bytes()) for n in (
            "features.py", "pit_filing_evidence.py", "pit_admission.py", "pit_join.py")}
        (args.output / "coverage.json").write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "SOURCE_OR_INFRASTRUCTURE_ERROR", "error": str(exc), "historicalReturnLabelsRead": 0}))
        return 4
    print(json.dumps({"status": report["status"], "coverage": report["coverage"]}, ensure_ascii=False))
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
