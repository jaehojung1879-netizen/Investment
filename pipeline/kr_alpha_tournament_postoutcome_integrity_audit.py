"""kr-alpha-discovery-tournament-v1 post-outcome integrity audit — why four registered paths were incomplete.

POST_OUTCOME_FORENSIC_DIAGNOSTIC. The formal execution (run 37535814142, commit eac50fdf, spec a8acb44c...) is CONSUMED and SEALED with the frozen
verdict BLOCKED_BY_DATA_INTEGRITY (`pathsComplete: false`). This module is not an execution, a rerun, a model rescue or a promotion step: it never
claims or reads a lock as an authorisation, never writes a marker, never writes or edits the sealed result, and changes no model, target,
hyperparameter, recency rule, allocation, cost or data exclusion. Every outcome it reconstructs is POST_OUTCOME_FORENSIC evidence only.

Two evidence classes, never blended:

* POST_OUTCOME_MODEL_FREE_DATA_SCAN — reads only the hash-verified replay-v16 price panels and the pinned PIT Top120 membership. It needs no model
  and no forecast, and establishes WHICH (ticker, session) pairs could ever make a held mark unresolvable inside the formal replay window.
* POST_OUTCOME_FORENSIC_RECONSTRUCTION — replays the frozen process read-only on the exact preserved raw-input artifact with the frozen functions
  (`build_signal_bundle`, `run_process`, `make_decider`, `kr_alpha_tournament_portfolio.replay`). Tracing wrappers OBSERVE the mark, decision and
  execution calls; they return exactly what the wrapped functions return. Nothing is attributed unless the reconstruction first reproduces the
  sealed result (`complete`, every complete path's metrics, the process summary, the prediction diagnostics and the evidence block); otherwise the
  status is RECONSTRUCTION_MISMATCH with the first divergence and no attribution.
"""
from __future__ import annotations

import bisect
import hashlib
import inspect
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import kr_alpha_tournament as T
from . import kr_alpha_tournament_portfolio as P

STUDY = "kr-alpha-discovery-tournament-v1"
AUDIT_ID = STUDY + "-postoutcome-integrity-audit"
EVIDENCE_CLASS_SCAN = "POST_OUTCOME_MODEL_FREE_DATA_SCAN"
EVIDENCE_CLASS_RECONSTRUCTION = "POST_OUTCOME_FORENSIC_RECONSTRUCTION"
STATUS = "POST_OUTCOME_FORENSIC_DIAGNOSTIC_NOT_CONFIRMATORY"

FORMAL = {
    "executionRunId": 37535814142,
    "executionSha": "eac50fdf725ac797e5c37044246e2a7ffa9b1e64",
    "specSha256": "a8acb44c4b685e06ce7692e44461147110e2e2d32a119adef0dd216476f50e7f",
    "resultArtifactName": "kr-alpha-discovery-tournament-v1-results-37535814142",
    "resultArtifactId": 11449586098,
    "resultArtifactDigest": "sha256:2079eb4adff331be02126c163084b92737828eb6be9aa49ece832b23f749ae85",
    "resultPath": "docs/results/kr-alpha-discovery-tournament-v1-result.json",
    "resultSha256": "4a117ed23d30f9d716c87dbd987e1b80798484b0ab3558638379bf65cf9ccc5d",
    "rawInputArtifactName": "kr-model-raw-inputs-36844599518",
    "rawInputArtifactId": 11157875265,
    "rawInputRunId": 36844599518,
    "rawInputArtifactDigest": "sha256:42eeb18b7a5c88816629036f472a93057b6a9be4768ad47292ba0d2750b4cce7",
    "inputIdentitySha256": "233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7",
    "replayManifestSha256": "f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2",
    "lockRefs": ["refs/tags/kr-alpha-discovery-tournament-v1-execution-lock",
                 "refs/tags/kr-alpha-discovery-tournament-v1-execution-lock-a8acb44c4b685e06ce7692e44461147110e2e2d32a119adef0dd216476f50e7f"],
    "verdict": "BLOCKED_BY_DATA_INTEGRITY",
    "incompletePaths": ["DECISION_FOCUSED_CHALLENGER:BASE", "PRIMARY_ROBUST_KELLY:BASE", "PRIMARY_ROBUST_KELLY:EXECUTION_DELAY_ONE_SESSION",
                        "PRIMARY_ROBUST_KELLY:LIQUIDITY_HAIRCUT_HALF_ADV"],
}
TERMINAL_INVENTORY = "docs/results/kr-termination-inventory.json"
TERMINAL_RECONSTRUCTION = "docs/results/kr-terminal-action-reconstruction-v2.json"
COMPLETED_RECORD = "docs/results/" + AUDIT_ID + ".json"
FLOAT_TOLERANCE = 1e-9

# Mechanism vocabulary (a held mark that `kr_integrated_alpha_portfolio_replay.mark_price` could not resolve)
TERMINAL_AFTER_SUSPENSION = "RAW_PRICE_ABSENT_AFTER_LAST_TRADING_DATE_HELD_THROUGH_PRE_TERMINAL_TRADING_SUSPENSION"
TERMINAL_NO_SUSPENSION = "RAW_PRICE_ABSENT_AFTER_LAST_TRADING_DATE"
MID_SERIES_GAP = "RAW_PRICE_ABSENT_MID_SERIES_GAP"
BENCHMARK_GAP = "BENCHMARK_PRICE_ABSENT"


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_sealed_result(root):
    """The sealed result is read, never written: its bytes must still be the sealed bytes."""
    path = Path(root) / FORMAL["resultPath"]
    if sha256_file(path) != FORMAL["resultSha256"]:
        raise ValueError("SEALED_RESULT_BYTES_CHANGED")
    result = json.loads(path.read_text())
    if result["specSha256"] != FORMAL["specSha256"] or result["lockedMainSha"] != FORMAL["executionSha"]:
        raise ValueError("SEALED_RESULT_IDENTITY_MISMATCH")
    if result["verdict"]["verdict"] != FORMAL["verdict"]:
        raise ValueError("SEALED_VERDICT_MISMATCH")
    incomplete = sorted(k for k, v in result["complete"].items() if not v)
    if incomplete != FORMAL["incompletePaths"]:
        raise ValueError("SEALED_INCOMPLETE_PATHS_MISMATCH")
    return result


# --------------------------------------------------------------------------- #
# Evidence class 1: model-free data scan (no model, no forecast)
# --------------------------------------------------------------------------- #
def _priced(frame):
    if frame is None or frame.empty:
        return []
    close = pd.to_numeric(frame["Close"], errors="coerce")
    return [str(i.date()) for i, c in zip(frame.index, close) if np.isfinite(c) and c > 0]


def gap_events(frames, signal_members, window, benchmark=T.BENCHMARK):
    """Every run of sessions in `window` with no positive Close for a name that was in the PIT Top120 at some signal on or before the run.
    `frames`: {ticker: frame indexed by session with Close}; `signal_members`: {signal date: [tickers]}. Returns the benchmark's missing sessions too.
    A run that never resumes inside the window is a terminal end of series; one that resumes is a mid-series gap."""
    window = sorted(window)
    first_signal = {}
    for signal in sorted(signal_members):
        for t in signal_members[signal]:
            first_signal.setdefault(t, signal)
    bench = set(_priced(frames.get(benchmark)))
    events = []
    for t in sorted(first_signal):
        priced = set(_priced(frames.get(t)))
        ordered = sorted(priced)
        run = None
        for d in window:
            if d < first_signal[t]:
                continue
            if d not in priced:
                run = run or {"ticker": t, "firstMissing": d, "sessions": 0}
                run["lastMissing"], run["sessions"] = d, run["sessions"] + 1
            elif run is not None:
                events.append(dict(run, resumes=True))
                run = None
        if run is not None:
            events.append(dict(run, resumes=False))
        for ev in events:
            if ev["ticker"] == t and "lastPricedBefore" not in ev:
                i = bisect.bisect_left(ordered, ev["firstMissing"])
                ev["lastPricedBefore"] = ordered[i - 1] if i else None
                prior = [s for s in signal_members if s < ev["firstMissing"] and t in signal_members[s]]
                ev["lastTop120SignalBefore"] = max(prior) if prior else None
    return {"benchmarkMissingSessions": [d for d in window if d not in bench], "events": events,
            "midSeriesGaps": [e for e in events if e["resumes"]], "terminalEnds": [e for e in events if not e["resumes"]]}


def terminal_window(frame, days, anchors):
    """The final zero-volume run before a name's last priced session (KRX shows a pre-delisting trading suspension as an unchanged Close with zero
    volume). `anchors`: [(anchor day, signal)] of the outer process. Returns the suspension start, the anchors that fall before / inside it."""
    priced = frame[pd.to_numeric(frame["Close"], errors="coerce") > 0]
    rows = list(zip([str(i.date()) for i in priced.index], pd.to_numeric(priced.get("Volume", pd.Series(np.nan, index=priced.index)),
                                                                          errors="coerce")))
    if not rows:
        return None
    i = len(rows) - 1
    while i >= 0 and rows[i][1] == 0:
        i -= 1
    last = rows[-1][0]
    suspension = rows[i + 1][0] if i + 1 < len(rows) else None
    after = [d for d in days if d > last]
    before = [a for a in anchors if suspension is not None and a[0] < suspension]
    return {"lastPositiveVolumeSession": rows[i][0] if i >= 0 else None, "suspensionStart": suspension,
            "suspendedSessions": len(rows) - 1 - i, "lastPricedSession": last, "firstUnpricedSession": after[0] if after else None,
            "lastOuterAnchorBeforeSuspension": list(before[-1]) if before else None,
            "outerAnchorsDuringSuspension": [list(a) for a in anchors if suspension is not None and suspension <= a[0] <= last]}


def terminal_foundation(root, tickers):
    """What the repository's terminal foundation says about each ticker (read only; nothing here is repaired)."""
    inventory = {s["code"]: s for s in json.loads((Path(root) / TERMINAL_INVENTORY).read_text())["securities"]}
    recon_doc = json.loads((Path(root) / TERMINAL_RECONSTRUCTION).read_text())
    recon = {s["code"]: s for s in recon_doc["securities"]}
    out = {}
    for t in tickers:
        i, r = inventory.get(t, {}), recon.get(t, {})
        out[t] = {"inTerminatedSecurityInventory": t in inventory, "krxName": i.get("krxName"), "lastTradingDate": i.get("lastTradingDate"),
                  "lastMembershipDate": i.get("lastMembershipDate"), "inventoryTerminationType": i.get("terminationType"),
                  "reconstructionTerminationType": r.get("terminationType"),
                  "reconstructionCompleteness": {k: v for k, v in sorted(r.get("completeness", {}).items())},
                  "foundationStatus": recon_doc.get("foundationStatus")}
    return out


def load_scan_inputs(replay_root, root):
    """Price panels and PIT Top120 membership for the model-free scan, verified exactly as `kr_model_portfolio_execution.load_sources` verifies
    them: the replay manifest digest must be the formal pin, every object is read through `InputStore` (hash-checked), every universe shard must
    match its pinned git blob. `replay_root` holds `ledger/historical/replay-v16/inputs.json`, `ledger/replay-inputs/objects/` and
    `ledger/universe/kr/` (the raw-input artifact, or the same blobs from `signal-history`)."""
    from . import historical_store as HS
    from . import kr_model_portfolio_execution as X
    from . import kr_repaired_accounting_snapshot as K
    from . import replay_inputs as RI

    replay_root = Path(replay_root)
    v1_spec, _ = X.load_spec(Path(root))
    manifest = json.loads((replay_root / "ledger/historical/replay-v16/inputs.json").read_text())
    if (RI.digest({k: v for k, v in manifest.items() if k != "sha256"}) != manifest.get("sha256")
            or manifest["sha256"] != FORMAL["replayManifestSha256"] or v1_spec["inputs"]["replayManifestSha256"] != FORMAL["replayManifestSha256"]):
        raise ValueError("REPLAY_MANIFEST_CHANGED")
    store = RI.InputStore(replay_root / "ledger", "replay-v16", manifest["dataVersion"])
    rows = {}
    for component in sorted(manifest["components"]):
        if not RI.is_price_panel(component):
            continue
        for row in store.load_component(component, manifest):
            ticker = row.get("ticker")
            if ticker and ticker.endswith(".KS"):
                rows.setdefault(ticker, {})[row["date"]] = {k: v for k, v in row.items() if k != "ticker"}
    frames = {t: RI.rows_frame(list(by_date.values())) for t, by_date in rows.items()}
    grouped = {}
    for rel, sha in v1_spec["inputs"]["universeBlobs"].items():
        path = replay_root / rel
        if not path.is_file() or K.git_blob_sha1(path.read_bytes()) != sha:
            raise ValueError("PIT_UNIVERSE_MISSING_OR_CHANGED")
        for row in HS.read_jsonl(path):
            grouped.setdefault(row["date"], []).append(row)
    snapshots = sorted(grouped)
    members = {d: sorted(r["ticker"] for r in sorted(rs, key=lambda r: (r["rank"], r["ticker"]))[:120]) for d, rs in grouped.items()}

    def members_on(date):
        i = bisect.bisect_right(snapshots, date) - 1
        return members[snapshots[i]] if i >= 0 else []
    return frames, members_on, {"replayManifestSha256": manifest["sha256"], "universeBlobs": v1_spec["inputs"]["universeBlobs"]}


def model_free_scan(replay_root, root):
    """Evidence class 1, end to end: which (ticker, session) pairs could ever leave a held mark unresolved inside the formal replay window."""
    from . import kr_alpha_tournament_execution as E
    from . import kr_alpha_tournament_walkforward as W

    frames, members_on, provenance = load_scan_inputs(replay_root, root)
    days, _, anchors = E.calendar_facts()
    outer = [tuple(a) for f in W.outer_folds(anchors) for a in f["anchors"]]
    first = outer[0][0]
    window = [d for d in days if first <= d <= T.DEVELOPMENT_CUTOFF]
    signal_members = {s: members_on(s) for _, s in outer}
    scan = gap_events(frames, signal_members, window)
    names = sorted({e["ticker"] for e in scan["terminalEnds"]})
    windows = {t: terminal_window(frames[t], days, outer) for t in names}
    reachable = sorted(t for t in names if windows[t]["lastOuterAnchorBeforeSuspension"] is not None
                       and t in signal_members.get(windows[t]["lastOuterAnchorBeforeSuspension"][1], []))
    return {"auditId": AUDIT_ID, "evidenceClass": EVIDENCE_CLASS_SCAN, "status": STATUS, "provenance": provenance,
            "replayWindow": {"firstOuterAnchor": first, "cutoff": T.DEVELOPMENT_CUTOFF, "sessions": len(window), "outerAnchors": len(outer)},
            "namesInTop120AtAnOuterSignal": len({t for m in signal_members.values() for t in m}),
            **scan, "terminalWindows": windows, "terminalFoundation": terminal_foundation(root, names),
            "top120AtTheLastOuterSignalBeforeSuspension": reachable,
            "note": "a model-free bound only: it names every session on which ANY path could have failed, and cannot say which path held what"}


# --------------------------------------------------------------------------- #
# Evidence class 2: tracing wrappers around the frozen ledger (observe, never alter)
# --------------------------------------------------------------------------- #
def _replay_locals():
    """The live locals of the frozen `P.replay` frame that is calling us (read only)."""
    frame = inspect.currentframe()
    try:
        while frame is not None:
            if frame.f_code is P.replay.__code__:
                return frame.f_locals
            frame = frame.f_back
        return None
    finally:
        del frame


class PathTrace:
    """Observes one replay: the held book at the start of every session, each executed trade, each decision and the first failed mark.
    Every wrapper returns exactly what it wraps (or re-raises exactly what it raised)."""

    def __init__(self, key, mark, executable, adv_of, decide, execute=P.execute):
        self.key, self._mark, self._executable, self._adv_of, self._decide, self._execute = key, mark, executable, adv_of, decide, execute
        self.held = {}            # session -> {ticker: weight} at the START of the session (end of the previous session, before drift)
        self.trades = []          # [{day, decisionDay?, before, target, fixed, after, navFactor, costFraction}]
        self.decisions = {}       # decision day -> target {ticker: weight} (None = no decision)
        self.failure = None
        self.skippedOrderLookups = []

    def mark(self, ticker, day, previous):
        if day not in self.held:
            loc = _replay_locals()
            if loc is not None and "weights" in loc:
                self.held[day] = {t: float(w) for t, w in loc["weights"].items()}
        try:
            return self._mark(ticker, day, previous)
        except ValueError as error:
            # Only a HELD position's daily mark (previous price known) stops a path. The trade loop's own price lookup for a new name passes
            # previous=None and the ledger itself skips that order on failure, so it is recorded separately and never as the path's failure.
            if previous is None:
                self.skippedOrderLookups.append({"day": day, "ticker": ticker, "reason": str(error)})
            elif self.failure is None and P.UNRESOLVED in str(error):
                loc = _replay_locals() or {}
                self.failure = {"day": day, "ticker": ticker, "reason": str(error), "previousMark": previous,
                                "heldBefore": dict(self.held.get(day, {})), "navBefore": float(loc.get("nav", float("nan")))}
            raise

    def executable(self, ticker, day):
        return self._executable(ticker, day)

    def adv_of(self, ticker, day):
        return self._adv_of(ticker, day)

    def decide(self, day, weights, nav_krw):
        target = self._decide(day, weights, nav_krw)
        if target is not None:
            self.decisions[day] = dict(target)
        return target

    def execute(self, before, target_stock, adv, nav_krw, stress=1.0, fixed=()):
        out = self._execute(before, target_stock, adv, nav_krw, stress, fixed=fixed)
        loc = _replay_locals() or {}
        self.trades.append({"day": loc.get("day"), "before": {t: float(w) for t, w in before.items()},
                            "target": {t: float(w) for t, w in target_stock.items()}, "fixed": sorted(fixed),
                            "after": {t: float(w) for t, w in out["weights"].items()}, "navFactor": out["navFactor"],
                            "costFraction": out["costFraction"]})
        return out


def traced_replay(key, days, start, end, mark, executable, adv_of, decide, stress=1.0, delay=0):
    """`P.replay` itself, called with tracing wrappers; `P.execute` is observed by swapping the module attribute for the duration of the call."""
    trace = PathTrace(key, mark, executable, adv_of, decide)
    original = P.execute
    P.execute = trace.execute
    try:
        out = P.replay(days, start, end, trace.mark, trace.executable, trace.adv_of, trace.decide, stress=stress, delay=delay)
    finally:
        P.execute = original
    return out, trace


def trace_paths(forecasts, data, risk, days, start, end, mark, executable, adv_of, counters=None):
    """Exactly `kr_alpha_tournament_study.run_paths` (same translators, stresses, order, arguments and counter increments), with every replay
    traced. Returns ({(kind, stress): replay output}, {"KIND:STRESS": PathTrace})."""
    from . import kr_alpha_tournament_study as ST

    paths, traces = {}, {}
    for kind in ST.TRANSLATORS:
        if counters is not None:
            counters["ledgerReplays"] = counters.get("ledgerReplays", 0) + 1
        decider = ST.make_decider(kind, forecasts, data, risk, counters=counters)
        paths[(kind, "BASE")], traces[kind + ":BASE"] = traced_replay(kind + ":BASE", days, start, end, mark, executable, adv_of, decider)
    for name, stress in T.STRESSES.items():
        if name == "BASE":
            continue
        if counters is not None:
            counters["ledgerReplays"] = counters.get("ledgerReplays", 0) + 1
        decider = ST.make_decider("PRIMARY_ROBUST_KELLY", forecasts, data, risk, stress["costMultiplier"], stress["advFractionMultiplier"],
                                  counters=counters)
        key = "PRIMARY_ROBUST_KELLY:" + name
        paths[("PRIMARY_ROBUST_KELLY", name)], traces[key] = traced_replay(key, days, start, end, mark, executable, adv_of, decider,
                                                                           stress=stress["costMultiplier"],
                                                                           delay=stress["executionDelaySessions"])
    return paths, traces


def holding_history(trace, ticker):
    """Entry and last-trade facts for `ticker` in one traced path, from the executed-trade log (the held book is the ledger's own)."""
    entries, changes, deferred = [], [], []
    for tr in trace.trades:
        b, a = tr["before"].get(ticker, 0.0), tr["after"].get(ticker, 0.0)
        if b <= 0 < a:
            entries.append(tr["day"])
        if ticker in tr["fixed"]:
            deferred.append({"day": tr["day"], "heldWeight": b, "targetWeight": tr["target"].get(ticker, 0.0)})
        elif abs(a - b) > 1e-12:
            changes.append({"day": tr["day"], "before": b, "after": a})
    last_entry = entries[-1] if entries else None
    return {"entryTradeDay": last_entry, "allEntryTradeDays": entries, "lastTradeChangingWeight": changes[-1] if changes else None,
            "deferredAtTrades": deferred}


def holding_on(trace, ticker, day):
    return trace.held.get(day, {}).get(ticker, 0.0)


def classify_failure(failure, window, market_quote):
    """Mechanism of the first failed mark from the model-free terminal window and the KRX quote on the failure session."""
    if failure["ticker"] == T.BENCHMARK:
        return BENCHMARK_GAP
    if window is None or window["firstUnpricedSession"] != failure["day"]:
        return MID_SERIES_GAP
    if window["suspensionStart"] is not None and window["suspendedSessions"] > 0:
        return TERMINAL_AFTER_SUSPENSION
    return TERMINAL_NO_SUSPENSION


def failure_report(trace, windows, foundation, quote_at, signal_tradable, label_ineligible, signal_of_anchor):
    """Everything Q1 asks for one incomplete path. `quote_at(ticker, day)` reads the KRX store (None when absent); `signal_tradable(ticker, signal)`
    is the decision's own signal-time `tradable` flag; `label_ineligible` is the set of (signal, ticker) whose MATURED label the sealed terminal
    rule withholds (a hindsight label rule the decider never reads)."""
    f = trace.failure
    if f is None:
        return None
    t, day = f["ticker"], f["day"]
    hist = holding_history(trace, t)
    window = windows.get(t)
    entry_signal = signal_of_anchor.get(hist["entryTradeDay"]) if hist["entryTradeDay"] else None
    decision_targets = {d: tgt.get(t, 0.0) for d, tgt in sorted(trace.decisions.items())
                        if hist["entryTradeDay"] and d >= min(hist["allEntryTradeDays"])}
    return {"path": trace.key, "firstFailingSession": day, "ticker": t, "markFailureReason": f["reason"],
            "heldWeightImmediatelyBeforeFailure": f["heldBefore"].get(t), "heldBookImmediatelyBeforeFailure": f["heldBefore"],
            "entryTradeDay": hist["entryTradeDay"], "entrySignalDate": entry_signal, "lastTradeChangingWeight": hist["lastTradeChangingWeight"],
            "deferredAtTrades": hist["deferredAtTrades"], "decisionTargetsSinceEntry": decision_targets,
            "heldWeightLast40Sessions": [[d, trace.held[d].get(t, 0.0)] for d in sorted(trace.held) if d <= day][-40:],
            "krxQuoteOnFailureSession": quote_at(t, day), "krxQuoteOnLastPricedSession": quote_at(t, window["lastPricedSession"]) if window else None,
            "terminalWindow": window, "mechanism": classify_failure(f, window, quote_at(t, day)),
            "terminalFoundation": foundation.get(t),
            "signalTimeTradableAtEntrySignal": signal_tradable(t, entry_signal) if entry_signal else None,
            "labelWithheldByHindsightTerminalRuleAtEntrySignal": (entry_signal, t) in label_ineligible if entry_signal else None,
            "terminationInformationAvailableToTheFrozenProcess": False,
            "terminationInformationNote": "no registered information class carries a corporate-action / delisting announcement (DART events are "
                                          "excluded as not PIT-ready); the terminal label rule is a hindsight LABEL rule the decider never reads"}


def exposure_table(traces, windows):
    """Held weight of every traced path in every terminal name at its suspension start and on its last priced session (None when the path had
    already stopped before that session)."""
    out = {}
    for key, trace in sorted(traces.items()):
        stop = trace.failure["day"] if trace.failure else None
        row = {}
        for t, w in sorted(windows.items()):
            if w is None:
                continue
            row[t] = {}
            for label in ("suspensionStart", "lastPricedSession"):
                d = w[label]
                row[t][label] = None if d is None or (stop is not None and d > stop) else holding_on(trace, t, d)
        out[key] = row
    return out


def cost_x2_explanation(traces, failures):
    """Q2: for every ticker that stopped a path, what COST_X2 held and decided over the same window."""
    x2 = traces.get("PRIMARY_ROBUST_KELLY:COST_X2")
    base = traces.get("PRIMARY_ROBUST_KELLY:BASE")
    out = []
    if x2 is None:
        return out
    for rep in failures:
        if rep is None:
            continue
        t, day = rep["ticker"], rep["firstFailingSession"]
        entry = rep["entryTradeDay"]
        hist = holding_history(x2, t)
        out.append({"failingPath": rep["path"], "ticker": t, "failingSession": day,
                    "costX2HeldWeightOnFailingSession": holding_on(x2, t, day),
                    "costX2HeldWeightOnSuspensionStart": holding_on(x2, t, rep["terminalWindow"]["suspensionStart"]) if rep["terminalWindow"] else None,
                    "costX2EverEntered": bool(hist["allEntryTradeDays"]), "costX2EntryTradeDays": hist["allEntryTradeDays"],
                    "costX2TargetAtFailingPathEntryDecision": (x2.decisions.get(entry) or {}).get(t) if entry else None,
                    "baseTargetAtEntryDecision": (base.decisions.get(entry) or {}).get(t) if base and entry else None,
                    "costX2LastTradeChangingWeight": hist["lastTradeChangingWeight"]})
    return out


# --------------------------------------------------------------------------- #
# Reproduction gate (nothing is attributed unless the sealed result is reproduced)
# --------------------------------------------------------------------------- #
def _first_divergence(a, b, path="", tol=FLOAT_TOLERANCE):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return path + "/" + str(k) + " (missing on one side)"
            d = _first_divergence(a[k], b[k], path + "/" + str(k), tol)
            if d:
                return d
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return path + " (length %d vs %d)" % (len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b)):
            d = _first_divergence(x, y, path + "[%d]" % i, tol)
            if d:
                return d
        return None
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None or isinstance(a, str) or isinstance(b, str):
        return None if a == b else path + " (%r vs %r)" % (a, b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol):
            return None
        return path + " (%r vs %r)" % (a, b)
    return None if a == b else path + " (%r vs %r)" % (a, b)


REPRODUCED_KEYS = ("complete", "paths", "process", "prediction", "evidence", "verdict", "outerAnchors", "signalCoveragePercent",
                   "inputIdentitySha256")


def reproduction_check(reconstructed, sealed):
    """{status, firstDivergence}: every registered key must agree (floats within 1e-9); counters except the marker write must agree."""
    for key in REPRODUCED_KEYS:
        d = _first_divergence(reconstructed.get(key), sealed.get(key), key)
        if d:
            return {"status": "RECONSTRUCTION_MISMATCH", "firstDivergence": d}
    counters = {k: v for k, v in sealed["counters"].items() if k != "markerWrites"}
    mine = {k: v for k, v in reconstructed["counters"].items() if k != "markerWrites"}
    d = _first_divergence(mine, counters, "counters")
    if d:
        return {"status": "RECONSTRUCTION_MISMATCH", "firstDivergence": d}
    return {"status": "RECONSTRUCTION_REPRODUCES_THE_SEALED_RESULT", "firstDivergence": None, "keysCompared": list(REPRODUCED_KEYS) + ["counters"]}


# --------------------------------------------------------------------------- #
# The full forensic reconstruction (Actions only: needs the exact preserved raw-input artifact)
# --------------------------------------------------------------------------- #
def reconstruct(input_root, root):
    """Read-only replay of the frozen process. Never claims a lock, never writes a marker, never writes the sealed result."""
    from . import kr_alpha_tournament_execution as E
    from . import kr_alpha_tournament_features as F
    from . import kr_alpha_tournament_study as ST
    from . import kr_alpha_tournament_walkforward as W
    from . import kr_model_portfolio_execution as X

    root = Path(root)
    sealed = verify_sealed_result(root)
    spec, sha = E.load_spec(root)
    if sha != FORMAL["specSha256"]:
        raise ValueError("SPEC_SHA_MISMATCH")
    identity_before = X.input_identity(input_root)["sha256"]
    if identity_before != FORMAL["inputIdentitySha256"]:
        raise ValueError("INPUT_IDENTITY_MISMATCH")
    counters = E.new_counters()
    bundle = E.build_signal_bundle(input_root, spec, root, counters)
    real = E.RealContext(bundle)
    rows = bundle["features"]
    rep = F.represent(rows)
    data = W.prepare_data(rep)
    ineligible = E.terminal_ineligible(bundle, root, T.DEVELOPMENT_CUTOFF)
    raw_labels = ST.build_labels(rows[["date", "ticker", "industry", "industryEligible", "marketCap"]], real.calendar, real.close_at,
                                 T.DEVELOPMENT_CUTOFF, ineligible, counters)
    E.cross_check_endpoints(raw_labels, bundle, spec, T.DEVELOPMENT_CUTOFF)
    labels = W.align_labels(data, raw_labels)
    risk = real.risk(bundle["schedule"])
    process = W.run_process(data, labels, bundle["anchors"], T.candidate_registry(), risk, real.calendar, counters)
    outer = W.outer_folds(bundle["anchors"])
    first = outer[0]["anchors"][0][0]
    days = bundle["daysList"]
    paths, traces = trace_paths(process["anchors"], data, risk, days, first, T.DEVELOPMENT_CUTOFF, real.mark, real.executable, real.adv_of,
                                counters)
    coverage, outer_count = E.signal_coverage(rows, bundle["anchors"])
    identity_after = X.input_identity(input_root)["sha256"]
    counters["metricCalls"] += 1
    assessed = ST.assemble(process, paths, labels, coverage, identity_unchanged=identity_after == identity_before)
    reconstructed = E.json_safe({"process": ST.process_summary(process), "outerAnchors": outer_count, "signalCoveragePercent": coverage,
                                 "inputIdentitySha256": identity_before, **assessed, "counters": dict(counters, markerWrites=1)})
    gate = reproduction_check(reconstructed, sealed)
    out = {"auditId": AUDIT_ID, "status": STATUS, "formal": FORMAL, "reproduction": gate, "inputIdentityAfterSha256": identity_after}
    if gate["status"] != "RECONSTRUCTION_REPRODUCES_THE_SEALED_RESULT":
        return out                                               # no attribution without exact reproduction
    window_days = [d for d in days if first <= d <= T.DEVELOPMENT_CUTOFF]
    outer_anchors = [tuple(a) for f in outer for a in f["anchors"]]
    signal_members = {s: bundle["schedule"][s] for _, s in outer_anchors if s in bundle["schedule"]}
    scan = gap_events(bundle["prices"], signal_members, window_days)
    terminal_names = sorted({e["ticker"] for e in scan["terminalEnds"]})
    windows = {t: terminal_window(bundle["prices"][t], days, outer_anchors) for t in terminal_names}
    foundation = terminal_foundation(root, terminal_names)
    signal_of_anchor = dict(outer_anchors)
    rep_idx = {(r.date, r.ticker): bool(r.tradable) for r in data["rep"][["date", "ticker", "tradable"]].itertuples()}
    failures = [failure_report(traces[k], windows, foundation, lambda t, d: real.ctx.market.at(t, d),
                               lambda t, s: rep_idx.get((s, t)), ineligible, signal_of_anchor)
                for k in sorted(traces) if traces[k].failure is not None]
    out.update({
        "evidenceClass": EVIDENCE_CLASS_RECONSTRUCTION,
        "firstFailures": failures,
        "pathsWithoutFailure": sorted(k for k in traces if traces[k].failure is None),
        "modelFreeScan": {"evidenceClass": EVIDENCE_CLASS_SCAN, **scan, "terminalWindows": windows, "terminalFoundation": foundation},
        "terminalExposure": exposure_table(traces, windows),
        "costX2": cost_x2_explanation(traces, failures),
        "tradeCounts": {k: len(v.trades) for k, v in sorted(traces.items())},
    })
    return E.json_safe(out)
