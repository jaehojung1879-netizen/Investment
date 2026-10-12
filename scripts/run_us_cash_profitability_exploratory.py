"""US cash-profitability H63 exploratory study (P4): outcome-free PREFLIGHT, or the owner-authorized one-shot EXECUTION.

    python scripts/run_us_cash_profitability_exploratory.py preflight --workspace <dir> [--extract] [--workers 4]
    python scripts/run_us_cash_profitability_exploratory.py execute --workspace <dir>      # refuses without owner authorization

PREFLIGHT reads no forward price: it verifies every pinned input identity, builds the signal-date cohorts for the whole weekly
grid with the frozen definitions, counts complete-case names and defined/matured cohorts, and scans PRICE-ROW PRESENCE (dates on
which a positive close exists; no value) for held names at entry and exit. It never calls `read_outcomes`; the counters it writes
prove that. It also reproduces the committed Phase 3 readiness counts on the same 55 fixed dates, which shows the harness builds the
frozen feature and control definitions rather than a second implementation of them.

EXECUTE is the one-shot exploratory run. It requires `docs/us-readiness/us-cash-profitability-exploratory-authorization-v1.json`
(owner-written, pinning every identity below and this harness's file hashes); without it the run stops before any outcome is read.
Running it consumes the study's one exploratory budget and is never repeated. The local guards (no committed result, a new output
path outside docs/) are NOT a durable one-shot lock: a re-run on another machine would pass them. The durable lock (a manual
workflow on merged main that atomically creates a study-level git ref before the first outcome read, as the KR one-shots do) is an
owner-approved follow-up and does not exist yet; see docs/us-cash-profitability-exploratory-preflight-ko.md.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import multiprocessing as mp
import sys
from bisect import bisect_left
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import replay_calendar as RC                        # noqa: E402
from pipeline import us_capital_allocation_coverage as C           # noqa: E402
from pipeline import us_cash_profitability_exploratory as X        # noqa: E402
from pipeline import us_dual_benchmark_data as D                   # noqa: E402


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


A = _load("coverage_audit", "scripts/audit_us_capital_allocation_coverage.py")
A3 = _load("phase3_readiness", "scripts/audit_us_alpha_phase3_readiness.py")
OV, MF, DX = A3.OV, A3.MF, A3.DX

READINESS = ROOT / "docs/us-readiness"
PREFLIGHT_OUT = READINESS / "us-cash-profitability-exploratory-preflight-v1.json"
CHECKLIST_OUT = READINESS / "us-cash-profitability-exploratory-readiness-v1.json"
SURVIVORSHIP_AUDIT = ROOT / "docs/results/alpha-opportunity-model-v3-survivorship-audit.json"
AUTHORIZATION = READINESS / "us-cash-profitability-exploratory-authorization-v1.json"
RESULT = READINESS / "us-cash-profitability-exploratory-result-v1.json"      # committed only by the one authorized run's seal
PHASE3_READINESS = READINESS / "us-alpha-phase3-readiness-v1.json"
PROTOCOL = READINESS / "us-cash-profitability-study-protocol-v1.json"
CAL_PROTOCOL = READINESS / "us-h63-inference-calibration-v1-protocol.json"
CAL_RESULT = READINESS / "us-h63-inference-calibration-v1-result.json"
HARNESS_FILES = ("pipeline/us_cash_profitability_exploratory.py", "scripts/run_us_cash_profitability_exploratory.py",
                 "pipeline/us_cash_profitability.py", "pipeline/us_h63_inference_calibration.py",
                 "pipeline/alpha_inference_calibration_v4.py", "scripts/audit_us_alpha_phase3_readiness.py")
CALIBRATED_MIN_NAMES = 245          # smallest names-per-date geometry the calibration evaluated (SMALL_COLLINEAR)
LAST_PANEL_SESSION = "2026-09-14"   # replay-v16 inputs `through`

STATE: dict = {}


def us_sessions() -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in RC.sessions(RC.ORIGIN, "2026-12-31", "US")]


def build_all(workers: int, cache: Path | None) -> list[dict]:
    """Signal-date cohorts for the whole grid. `cache` (development only) holds outcome-free cohorts keyed by the harness code."""
    import hashlib
    import inspect
    key = {f: X.sha256_file(ROOT / f) for f in HARNESS_FILES if f != "scripts/run_us_cash_profitability_exploratory.py"}
    key["build_date"] = hashlib.sha256(inspect.getsource(build_date).encode()).hexdigest()
    if cache is not None and cache.exists():
        stored = json.loads(cache.read_text())
        if stored["key"] == key:
            return stored["cohorts"]
    with mp.get_context("fork").Pool(workers) as pool:
        cohorts = sorted(pool.map(build_date, STATE["dates"], chunksize=4), key=lambda c: c["date"])
    if cache is not None:
        cache.write_text(json.dumps({"key": key, "cohorts": cohorts}))
    return cohorts


def identities() -> dict[str, str]:
    """Every input the run depends on, pinned by content (replay manifest, fundamentals commit, membership, sectors, specs, code)."""
    reader = D.SealedReader(ROOT)
    manifest = reader.manifest()                                   # raises FROZEN_REPLAY_MANIFEST_CHANGED on any change
    ident = {"replayManifestSha256": manifest["sha256"], "replayThrough": manifest["through"],
             "fundamentalsCommit": A.FUNDAMENTALS_COMMIT,
             "membershipSha256": X.sha256_file(A.MEMBERSHIP), "sectorsSha256": X.sha256_file(A.SECTORS),
             "studyProtocolSha256": X.sha256_file(PROTOCOL), "calibrationProtocolSha256": X.sha256_file(CAL_PROTOCOL),
             "calibrationResultSha256": X.sha256_file(CAL_RESULT)}
    ident.update({"code:" + f: X.sha256_file(ROOT / f) for f in HARNESS_FILES})
    return ident


def load_state(workspace: Path) -> None:
    grouped, ciks, _, _ = A.load_filings(workspace, A.FUNDAMENTALS_COMMIT)
    prices, _ = A.load_price_presence()
    import gzip
    membership = A3.MF.RAF.MembershipSnapshots(json.loads(gzip.decompress(A.MEMBERSHIP.read_bytes()))["snapshots"])
    payload = json.loads(gzip.decompress(A.SECTORS.read_bytes()))
    category, malformed, renames, ambiguous = A.identity_tables()
    # Engine-free context: classify_member resolves identity and price exactly as the Phase 2/3 funnels do and never builds a
    # #220 distribution snapshot (every price-and-identity-eligible member returns NO_FUNDAMENTAL_RECORD here).
    ctx = C.WeekContext(engines={}, prices=prices, sectors=C.SectorBook(payload["snapshots"]), ciks=ciks, category=category,
                        malformed=malformed, renames=renames, ambiguous=ambiguous)
    dates = A3.DX.V3.weekly_grid(RC.sessions(RC.ORIGIN, "2026-09-25", "US"), A.THROUGH)
    raw = A3.raw_records(workspace, A.FUNDAMENTALS_COMMIT)
    panel, store, replay_identity = OV.load_sealed()
    reader = D.SealedReader(ROOT)
    events = MF.load_events(reader, reader.manifest())
    STATE.update(ctx=ctx, membership=membership, dates=dates, raw=raw, panel=panel, store=store, events=events,
                 bench=panel.get("SPY"), presence=prices, replayIdentity=replay_identity)


def build_date(date: str) -> dict:
    """Signal-date cohort for one date. Reads nothing after `date`."""
    ctx, membership, panel = STATE["ctx"], STATE["membership"], STATE["panel"]
    snapshot = membership.on(date)
    rows, status, cache = [], Counter(), {}
    for raw_symbol in snapshot["members"]:
        member = C.classify_member(ctx, snapshot, date, raw_symbol)
        status[member.status] += 1
        if member.status in A3.PRICE_FAILURES:
            continue
        v = A3.row_values(panel, STATE["store"], STATE["raw"], STATE["events"], cache, member, date, STATE["bench"])
        if v is None:
            status["NO_PRICE_HISTORY_FOR_FEATURES"] += 1
            continue
        rows.append({"ticker": member.ticker, "sector": member.sector, **{k: v.get(k) for k in (X.FEATURE,) + X.CONTROLS}})
    counters = X.Counters()
    cohort = X.cohort_weights(rows, counters)
    nonfin = [r for r in rows if r["sector"] not in X.EXCLUDED_SECTORS and r["sector"] != "UNCLASSIFIED"]
    return {"date": date, "memberStatus": dict(status), "eligibleNonFinancial": len(nonfin), "names": cohort["names"],
            "defined": cohort["defined"], "tickers": cohort["tickers"],
            "heldTickers": [t for t, w in zip(cohort["tickers"], cohort["weights"]) if w != 0],
            "heldWeights": [float(w) for w in cohort["weights"] if w != 0],
            "featureBuilds": counters.featureBuilds, "outcomeReads": counters.outcomeReads}


def has_close_on(ticker: str, session: str) -> bool:
    """A positive close exists ON this session (PricePresence keeps dates only; no value is read)."""
    dates = STATE["presence"]._dates.get(ticker) or []
    i = bisect_left(dates, session)
    return i < len(dates) and dates[i] == session


def presence_scan(cohorts: list[dict], sessions: list[str]) -> dict:
    """Matured defined cohorts whose held names lack a close on the entry or exit session (dates only; no price value is read)."""
    last_idx = sessions.index(LAST_PANEL_SESSION)
    matured, unresolved, examples = 0, 0, []
    for c in cohorts:
        if not c["defined"]:
            continue
        entry, exit_ = X.entry_exit(sessions, c["date"])
        if exit_ > last_idx:
            continue
        matured += 1
        bad = [t for t in c["heldTickers"] if not (has_close_on(t, sessions[entry]) and has_close_on(t, sessions[exit_]))]
        if bad:
            unresolved += 1
            examples.append({"date": c["date"], "entry": sessions[entry], "exit": sessions[exit_], "tickers": bad[:5]})
    return {"maturedDefinedCohorts": matured, "unresolvedCohorts": unresolved, "definedAndResolved": matured - unresolved,
            "unresolvedSharePct": round(100.0 * unresolved / matured, 3) if matured else None,
            "exceedsProtocolMaximum": bool(matured and unresolved > X.MAX_UNRESOLVED_SHARE * matured),
            "unresolvedExamples": examples[:10],
            "rule": "a held name needs a positive close ON the entry session and ON the exit session; interior gaps are carried forward"}


def collection_audit(last_matured: str) -> dict:
    """Per collection day: filings with / without a stated balance sheet and cash-flow statement (metadata only, no value), and the
    balance-sheet-less filings that become visible on or before the last matured signal date (the only ones that can touch P4)."""
    days = defaultdict(Counter)
    early = []
    for records in STATE["raw"].values():
        for r in records:
            st = r.get("statements") or {}
            days[str(r.get("collectedAt"))[:10]][("bs" if st.get("bs") else "noBs") + ("Cf" if st.get("cf") else "NoCf")] += 1
            visible = max(str(r.get("availableFrom") or ""), str(r.get("acceptedDate") or "")[:10])
            if not st.get("bs") and str(r.get("collectedAt"))[:10] > LAST_PANEL_SESSION and visible < last_matured:
                early.append({"ticker": r.get("ticker"), "form": r.get("form"), "periodEnd": r.get("periodEnd"), "visibleAfter": visible})
    return {"byCollectionDay": {d: dict(c) for d, c in sorted(days.items())},
            "lateCollectedWithoutBalanceSheetVisibleBeforeLastMaturedSignal": sorted(early, key=lambda e: (e["visibleAfter"], e["ticker"])),
            "reading": "filings collected after 2026-09-14 carry no balance sheet, so total assets (the denominator of the feature and of "
                       "the accrual-profitability control) is not stated for them. The ones visible before the last matured signal date "
                       "are listed: on those dates the name falls back to its previous filing or drops out (frozen staleness rule), which "
                       "is part of the pinned input, not repaired. Prospective signals would be dark"}


def preflight(args) -> int:
    ident = identities()
    load_state(args.workspace)
    dates = STATE["dates"]
    sessions = us_sessions()
    cohorts = build_all(args.workers, args.cohort_cache)
    names = np.array([c["names"] for c in cohorts])
    by_year = defaultdict(list)
    for c in cohorts:
        by_year[c["date"][:4]].append(c["names"])
    sampled = {d for d in dates[::A3.SAMPLE_EVERY_WEEKS]}
    sample = [c for c in cohorts if c["date"] in sampled]
    committed = json.loads(PHASE3_READINESS.read_text())["overall"]
    reproduction = {
        "dates": len(sample),
        "primaryCompleteMemberDates": int(sum(c["names"] for c in sample)),
        "eligibleNonFinancialMemberDates": int(sum(c["eligibleNonFinancial"] for c in sample)),
        "medianNamesPerDate": float(np.median([c["names"] for c in sample])),
        "companiesEver": len({t for c in sample for t in c["tickers"]}),
    }
    reproduction["committed"] = {"eligibleNonFinancialMemberDates": committed["eligibleNonFinancialMemberDates"],
                                 "primaryCompletePct": committed["primaryCompletePct"],
                                 "medianNamesPerDate": committed["namesPerDatePrimaryComplete"]["median"],
                                 "companiesEver": committed["companiesEverPrimaryComplete"]}
    pct = round(100.0 * reproduction["primaryCompleteMemberDates"] / reproduction["eligibleNonFinancialMemberDates"], 3)
    reproduction["reproduces"] = (reproduction["eligibleNonFinancialMemberDates"] == committed["eligibleNonFinancialMemberDates"]
                                  and pct == committed["primaryCompletePct"]
                                  and reproduction["medianNamesPerDate"] == committed["namesPerDatePrimaryComplete"]["median"]
                                  and reproduction["companiesEver"] == committed["companiesEverPrimaryComplete"])
    scan = presence_scan(cohorts, sessions)
    last_idx = sessions.index(LAST_PANEL_SESSION)
    last_matured = max(c["date"] for c in cohorts if X.entry_exit(sessions, c["date"])[1] <= last_idx)
    defined = [c for c in cohorts if c["defined"]]
    report = {
        "contract": X.CONTRACT, "study": X.STUDY_ID, "mode": "PREFLIGHT_OUTCOME_FREE",
        "evidenceClassOfTheFutureRun": X.EVIDENCE_CLASS,
        "identities": ident,
        "counters": {"featureBuilds": int(sum(c["featureBuilds"] for c in cohorts)),
                     "outcomeReads": int(sum(c["outcomeReads"] for c in cohorts)), "intervalComputations": 0},
        "weeklySignalDates": {"count": len(dates), "first": dates[0], "last": dates[-1]},
        "namesPerDate": {"median": float(np.median(names)), "p10": float(np.quantile(names, .1)), "min": int(names.min()),
                         "max": int(names.max()),
                         "byYear": {y: {"dates": len(v), "median": float(np.median(v)), "min": int(min(v))} for y, v in sorted(by_year.items())}},
        "floor150": {"datesBelow": int((names < X.MIN_NAMES_PER_DATE).sum()),
                     "belowDates": [c["date"] for c in cohorts if not c["defined"]]},
        "calibratedGeometry": {"minNamesEvaluated": CALIBRATED_MIN_NAMES,
                               "definedDatesBelowCalibratedMin": int(sum(1 for c in defined if c["names"] < CALIBRATED_MIN_NAMES)),
                               "byYear": {y: int(sum(1 for c in defined if c["date"][:4] == y and c["names"] < CALIBRATED_MIN_NAMES))
                                          for y in sorted(by_year)}},
        "cohorts": {**scan, "definedSignalDates": len(defined), "minimumDefinedWeeks": X.MIN_DEFINED_WEEKS},
        "fundamentalsCollection": collection_audit(last_matured),
        "lastMaturedSignalDate": last_matured,
        "memberStatusNote": "engine-free context: NO_FUNDAMENTAL_RECORD here means price-and-identity eligible; the feature path decides the rest",
        "memberStatusTotals": dict(sum((Counter(c["memberStatus"]) for c in cohorts), Counter())),
        "phase3Reproduction": reproduction,
        "frozenDefinitions": {"feature": X.FEATURE, "controls": list(X.CONTROLS), "excludedSectors": list(X.EXCLUDED_SECTORS),
                              "minNamesPerDate": X.MIN_NAMES_PER_DATE, "horizon": X.HORIZON,
                              "snCriticalValue": X.SN_CRITICAL_VALUE, "entryConvention": "close of the first session after the signal date"},
    }
    PREFLIGHT_OUT.write_text(json.dumps(report, indent=1, sort_keys=True, allow_nan=False) + "\n")
    CHECKLIST_OUT.write_text(json.dumps(readiness_checklist(report), indent=1, sort_keys=True, allow_nan=False, ensure_ascii=False) + "\n")
    print(json.dumps({k: report[k] for k in ("counters", "namesPerDate", "floor150", "cohorts", "phase3Reproduction")}, indent=1)[:4000])
    return 0 if reproduction["reproduces"] and report["counters"]["outcomeReads"] == 0 else 1


def readiness_checklist(report: dict) -> dict:
    """Machine-readable PASS / CONDITIONAL / BLOCKED checklist, every number read from the preflight or a committed audit."""
    us = json.loads(SURVIVORSHIP_AUDIT.read_text())["regions"]["US"]
    years = us["memberDatesByYear"]
    cohorts, geometry, names = report["cohorts"], report["calibratedGeometry"], report["namesPerDate"]
    status = report["memberStatusTotals"]
    below_cal = geometry["definedDatesBelowCalibratedMin"]
    defined = cohorts["definedSignalDates"]
    items = [
        {"id": "PIT_FINANCIAL_STATEMENT_VISIBILITY", "state": "PASS",
         "evidence": "pipeline/us_cash_profitability.features_as_of uses a filing only strictly after max(availableFrom, acceptedDate) "
                     "and the latest visible period end, stale over 180 days; raw filings are read blob-verified from fundamentals "
                     f"commit {report['identities']['fundamentalsCommit']}; restatements arrive as their own filing",
         "residualRisk": "as-reported (first) vintages only; no restated-value look-ahead path exists in the store"},
        {"id": "UNIVERSE_MEMBERSHIP_AND_IDENTITY", "state": "CONDITIONAL",
         "evidence": {"membershipSnapshots": us["membershipSnapshots"]["count"], "maxSnapshotGapDays": us["membershipSnapshots"]["maxGapDays"],
                      "gapsOver45Days": us["membershipSnapshots"]["gapsOver45Days"], "verifiedRenames": us["identity"]["categoryCounts"]["SAME_SECURITY_RENAME"],
                      "tickerReuseDifferentIssuer": us["identity"]["categoryCounts"]["TICKER_REUSE_DIFFERENT_ISSUER"],
                      "identityAmbiguousMemberDates": status.get("IDENTITY_AMBIGUOUS", 0)},
         "condition": "a member is taken from the latest snapshot strictly before the signal date; inside the 21 snapshot gaps over 45 days "
                      "the snapshot is stale, and ambiguous identities are excluded, never guessed. Disclosed, not repaired"},
        {"id": "PRICE_AND_CORPORATE_ACTION_CONSISTENCY", "state": "PASS",
         "evidence": f"replay-v16 total-return panel, manifest {report['identities']['replayManifestSha256'][:16]}... verified by "
                     "SealedReader; the traded-value control is withheld when a split falls in its window; a forward return is a ratio "
                     "of total-return closes, so splits and dividends enter through the panel's own adjustment"},
        {"id": "DEPARTED_SECURITIES_AND_TERMINAL_CONSIDERATION", "state": "CONDITIONAL",
         "evidence": {"departedIdentities": us["universe"]["departedMembers"],
                      "departedWithoutPrices": us["sampleSurvivorship"]["noPanelDeparted"],
                      "noPanelPctOfMemberDatesFirstYear": years["2013"]["NO_PANEL"], "noPanelPctOfMemberDatesLastYear": years["2026"]["NO_PANEL"],
                      "noPanelCurrentMembers": us["sampleSurvivorship"]["noPanelCurrent"],
                      "terminatedPanelsInSample": us["terminations"]["terminatedInPanel"],
                      "maturedCohortsWithUnresolvedHeldName": cohorts["unresolvedCohorts"]},
         "condition": "the sample is survivor-conditioned: missing names are ONLY departed ones (informative missingness), which the "
                      "calibration's random missingness does not model. It biases the estimand, not the interval's coverage. No priced "
                      "panel ends inside the window, so the UNRESOLVED rule has nothing to act on and cannot repair this. Owner must "
                      "acknowledge that an ABANDON reading may partly reflect the missing departed names"},
        {"id": "COMPLETE_CASE_SAMPLE", "state": "PASS" if defined >= X.MIN_DEFINED_WEEKS else "BLOCKED",
         "evidence": {"weeklySignalDates": report["weeklySignalDates"]["count"], "definedSignalDates": defined,
                      "datesBelow150": report["floor150"]["datesBelow"], "medianNamesPerDate": names["median"],
                      "maturedDefinedCohorts": cohorts["maturedDefinedCohorts"], "minimumDefinedWeeks": X.MIN_DEFINED_WEEKS}},
        {"id": "CALIBRATED_GEOMETRY", "state": "CONDITIONAL" if below_cal else "PASS",
         "evidence": {"calibratedMinimumNamesPerDate": CALIBRATED_MIN_NAMES, "definedDatesBelowIt": below_cal,
                      "byYear": {y: v for y, v in geometry["byYear"].items() if v}},
         "condition": "the calibration licenses CT_SN by weeks (>= 260) and evaluated 245-330 names per date; defined dates with 150-244 "
                      "names are inside the protocol floor but outside the evaluated geometry"},
        {"id": "H63_OUTCOME_CONSTRUCTION", "state": "PASS",
         "evidence": "entry at the close of the first session after the signal date, exit 63 sessions later; S_t = sum w (C[exit]/C[entry] - 1); "
                     "SPY cancels because weights sum to zero within sector; a held name without a close at entry or exit makes the "
                     "cohort UNRESOLVED (never zero, never last price) and > 10% unresolved is NOT_EVALUABLE; tested on synthetic data"},
        {"id": "CT_SN_INFERENCE_CONTRACT", "state": "PASS",
         "evidence": "alpha_inference_calibration_v4.calendar_time_sn_interval with U1 28.31 on the compounded calendar-week series, which "
                     "equals v4's calendar_time_series on additive uniform data and sums exactly to the signal-date statistic (tested)"},
        {"id": "FROZEN_DEFINITIONS_NO_LEAKAGE", "state": "PASS" if report["phase3Reproduction"]["reproduces"] and not report["counters"]["outcomeReads"] else "BLOCKED",
         "evidence": {"phase3ReproductionOn55Dates": report["phase3Reproduction"]["reproduces"], "outcomeReads": report["counters"]["outcomeReads"],
                      "intervalComputations": report["counters"]["intervalComputations"]}},
        {"id": "OUTCOME_EXPOSURE_AND_BUDGET", "state": "CONDITIONAL",
         "evidence": "this statistic was never computed on US outcomes; the same 2013-2026 history is exposed through other features "
                     "(four-factor value sleeve incl. fcfYield, quality, momentum, low-vol; the 31-feature regional model without cash flow)",
         "condition": "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_US_HISTORY only: one run, futility screen only, never confirmation"},
        {"id": "OWNER_AUTHORIZATION", "state": "BLOCKED", "evidence": "no authorization record exists (by design)",
         "remedy": "owner commits docs/us-readiness/us-cash-profitability-exploratory-authorization-v1.json pinning every identity in the preflight"},
        {"id": "DURABLE_ONE_SHOT_LOCK", "state": "BLOCKED",
         "evidence": "local guards only (no committed result, new output path); no workflow and no study-level git ref",
         "remedy": "owner-approved manual workflow on merged main that creates refs/tags/us-cash-profitability-signal-v1-exploratory-lock "
                   "atomically before the first outcome read and refuses if any ref under that prefix exists"},
    ]
    fc = report["fundamentalsCollection"]["byCollectionDay"]
    late = {d: c for d, c in fc.items() if d > LAST_PANEL_SESSION}
    observations = [{"id": "PROSPECTIVE_FUNDAMENTALS_BALANCE_SHEET_GAP", "gatesP4": False, "gatesProspective": True,
                     "evidence": {"filingsCollectedAfterPanelEnd": sum(sum(c.values()) for c in late.values()),
                                  "ofWhichWithBalanceSheet": sum(c.get("bsCf", 0) + c.get("bsNoCf", 0) for c in late.values()),
                                  "byCollectionDay": late, "lastMaturedSignalDate": report["lastMaturedSignalDate"],
                                  "visibleBeforeLastMaturedSignal": len(report["fundamentalsCollection"][
                                      "lateCollectedWithoutBalanceSheetVisibleBeforeLastMaturedSignal"]),
                                  "undefinedUnmaturedSignalDates": [d for d in report["floor150"]["belowDates"] if d > "2026"]},
                     "reading": report["fundamentalsCollection"]["reading"],
                     "remedy": "separate source diagnostic of the Finnhub financials-reported collector before any prospective registration; "
                               "cause not determined here (the collector's history is not visible in this checkout)"}]
    states = {item["state"] for item in items}
    science = [i for i in items if i["id"] not in ("OWNER_AUTHORIZATION", "DURABLE_ONE_SHOT_LOCK")]
    sci_states = {i["state"] for i in science}
    worst = lambda st: "BLOCKED" if "BLOCKED" in st else ("CONDITIONAL" if "CONDITIONAL" in st else "PASS")  # noqa: E731
    return {"contract": X.CONTRACT, "study": X.STUDY_ID, "authorizes": "NOTHING", "executed": False,
            "overall": worst(states), "scientificReadiness": worst(sci_states), "executionReadiness": worst({i["state"] for i in items if i not in science}),
            "items": items, "observationsNotGatingP4": observations, "preflight": str(PREFLIGHT_OUT.relative_to(ROOT))}


def close_reader(tickers: list[str], session_dates: list[str]) -> np.ndarray:
    """Total-return closes (replay-v16 panel) on exactly these sessions; NaN where the panel has no row."""
    panel = STATE["panel"]
    days = np.array(session_dates, dtype="datetime64[ns]")
    out = np.full((len(session_dates), len(tickers)), np.nan)
    for k, t in enumerate(tickers):
        h = panel.get(t)
        if h is None:
            continue
        pos = np.searchsorted(h.dates, days)
        ok = (pos < len(h.dates)) & (h.dates[np.minimum(pos, len(h.dates) - 1)] == days)
        out[ok, k] = h.close[pos[ok]]
    return out


def execute(args) -> int:
    if RESULT.exists():
        raise SystemExit("ONE_SHOT_ALREADY_SPENT: " + str(RESULT))
    if args.output is None or args.output.exists() or str(args.output.resolve()).startswith(str((ROOT / "docs").resolve())):
        raise SystemExit("OUTPUT_MUST_BE_A_NEW_EXPLICIT_PATH_OUTSIDE_docs")
    ident = identities()
    permit = X.authorize(AUTHORIZATION, ident)          # raises OutcomeAccessRefused unless the owner has authorized this exact run
    load_state(args.workspace)
    sessions = us_sessions()
    cohorts = build_all(args.workers, None)
    counters = X.Counters(featureBuilds=sum(c["featureBuilds"] for c in cohorts))
    result = X.execute_study(cohorts, sessions, LAST_PANEL_SESSION, close_reader, permit, counters)
    record = {"contract": X.CONTRACT, "evidenceClass": X.EVIDENCE_CLASS, "identities": ident, "counters": counters.as_dict(),
              "result": result, "authorizationSha256": permit.authorizationSha256}
    args.output.write_text(json.dumps(record, indent=1, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(result, indent=1))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "execute"))
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, help="execute only: a new result path outside docs/")
    parser.add_argument("--cohort-cache", type=Path, help="preflight only, development: reuse outcome-free cohorts built by identical code")
    args = parser.parse_args(argv)
    if args.extract:
        A.extract(args.workspace, A.FUNDAMENTALS_COMMIT)
    return preflight(args) if args.mode == "preflight" else execute(args)


if __name__ == "__main__":
    raise SystemExit(main())
