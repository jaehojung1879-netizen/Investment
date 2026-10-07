"""kr-alpha-discovery-tournament-v1 post-outcome integrity audit: tracing wrappers observe the frozen ledger without altering it, the first failure
is attributed with the held book, entry and deferral facts, the model-free scan finds terminal ends and gaps, the reproduction gate refuses any
divergence, and nothing here can reach a lock, a marker, the formal execute path or the sealed result. Synthetic ledgers only, plus the committed
sealed files."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_alpha_tournament as T
from pipeline import kr_alpha_tournament_portfolio as P
from pipeline import kr_alpha_tournament_postoutcome_integrity_audit as A

ROOT = Path(__file__).resolve().parents[1]
B = T.BENCHMARK
SCAN = ROOT / "docs/results/kr-alpha-discovery-tournament-v1-postoutcome-integrity-audit-model-free-scan.json"
WORKFLOW = ROOT / ".github/workflows/kr-alpha-discovery-tournament-v1-postoutcome-integrity-audit.yml"
AUDIT_FILES = [ROOT / "pipeline/kr_alpha_tournament_postoutcome_integrity_audit.py",
               ROOT / "scripts/run_kr_alpha_discovery_tournament_v1_postoutcome_integrity_audit.py"]


# --------------------------------------------------------------------------- #
# A tiny synthetic ledger world: S1 is bought, suspended (no executable quote), then has no price at all
# --------------------------------------------------------------------------- #
class World:
    def __init__(self, n=24, last_priced=None, suspended_from=None, unpriced=None):
        rng = np.random.default_rng(5)
        self.days = ["2021-03-%02d" % (i + 1) for i in range(n)]
        self.px = {t: 100 * np.cumprod(1 + rng.normal(0, 0.01, n)) for t in (B, "S1", "S2", "S3")}
        self.last_priced = last_priced or {}
        self.suspended_from = suspended_from or {}
        self.unpriced = unpriced or set()

    def _priced(self, t, day):
        i = self.days.index(day)
        return (t, day) not in self.unpriced and (t not in self.last_priced or i <= self.last_priced[t])

    def mark(self, t, day, previous):
        if not self._priced(t, day):
            raise ValueError(P.UNRESOLVED + ": " + t + ":" + day)
        return float(self.px[t][self.days.index(day)])

    def executable(self, t, day):
        i = self.days.index(day)
        return self._priced(t, day) and not (t in self.suspended_from and i >= self.suspended_from[t])

    def adv(self, t, day):
        return 5e10


def decider(targets):
    return lambda day, weights, nav: targets.get(day)


def run_both(world, targets, **kw):
    plain = P.replay(world.days, world.days[0], world.days[-1], world.mark, world.executable, world.adv, decider(targets), **kw)
    traced, trace = A.traced_replay("X:BASE", world.days, world.days[0], world.days[-1], world.mark, world.executable, world.adv,
                                    decider(targets), **kw)
    return plain, traced, trace


def test_tracing_never_changes_a_complete_path():
    w = World()
    targets = {w.days[2]: {"S1": 0.2, "S2": 0.1}, w.days[12]: {"S2": 0.3}}
    plain, traced, trace = run_both(w, targets)
    assert plain["complete"] and traced["complete"]
    assert json.dumps(plain, sort_keys=True) == json.dumps(traced, sort_keys=True)
    assert trace.failure is None and len(trace.trades) == 2 and P.execute.__name__ == "execute"
    assert trace.held[w.days[3]]["S1"] > 0 and w.days[0] in trace.held


def test_a_name_held_into_a_suspension_is_deferred_and_then_stops_the_path():
    w = World(last_priced={"S1": 15}, suspended_from={"S1": 9})
    targets = {w.days[2]: {"S1": 0.2, "S2": 0.1}, w.days[12]: {"S2": 0.3}}
    plain, traced, trace = run_both(w, targets)
    assert not plain["complete"] and json.dumps(plain, sort_keys=True) == json.dumps(traced, sort_keys=True)
    f = trace.failure
    assert f["day"] == w.days[16] and f["ticker"] == "S1" and P.UNRESOLVED in f["reason"] and f["previousMark"] is not None
    assert 0.15 < f["heldBefore"]["S1"] < 0.25
    hist = A.holding_history(trace, "S1")
    assert hist["entryTradeDay"] == w.days[2] and hist["allEntryTradeDays"] == [w.days[2]]
    assert hist["deferredAtTrades"] and hist["deferredAtTrades"][0]["day"] == w.days[12] and hist["deferredAtTrades"][0]["targetWeight"] == 0.0
    frame = pd.DataFrame({"Close": [w.px["S1"][i] for i in range(16)], "Volume": [1e5] * 9 + [0.0] * 7},
                         index=pd.to_datetime(w.days[:16]))
    window = A.terminal_window(frame, w.days, [(w.days[2], w.days[1]), (w.days[12], w.days[11])])
    assert window["suspensionStart"] == w.days[9] and window["lastPricedSession"] == w.days[15]
    assert window["firstUnpricedSession"] == w.days[16] and window["lastOuterAnchorBeforeSuspension"] == [w.days[2], w.days[1]]
    assert window["outerAnchorsDuringSuspension"] == [[w.days[12], w.days[11]]]
    report = A.failure_report(trace, {"S1": window}, {"S1": {"inTerminatedSecurityInventory": True}}, lambda t, d: None,
                              lambda t, s: True, {(w.days[1], "S1")}, {w.days[2]: w.days[1], w.days[12]: w.days[11]})
    assert report["mechanism"] == A.TERMINAL_AFTER_SUSPENSION and report["entrySignalDate"] == w.days[1]
    series = dict(report["heldWeightLast40Sessions"])
    assert series[w.days[16]] == report["heldWeightImmediatelyBeforeFailure"] and series[w.days[1]] == 0.0 and series[w.days[10]] > 0
    assert report["labelWithheldByHindsightTerminalRuleAtEntrySignal"] is True and report["terminationInformationAvailableToTheFrozenProcess"] is False


def test_a_failed_price_lookup_for_a_new_order_is_never_the_paths_failure():
    w = World(unpriced={("S3", "2021-03-03")})
    w.executable = lambda t, day: True                  # a positive-volume quote but no replay close: the ledger skips the order
    targets = {w.days[2]: {"S3": 0.2, "S2": 0.1}}
    plain, traced, trace = run_both(w, targets)
    assert plain["complete"] and traced["complete"] and trace.failure is None
    assert trace.skippedOrderLookups == [{"day": w.days[2], "ticker": "S3", "reason": P.UNRESOLVED + ": S3:" + w.days[2]}]


def test_cost_x2_explanation_reads_holdings_and_decisions_of_both_paths():
    w = World(last_priced={"S1": 15}, suspended_from={"S1": 9})
    _, _, base = run_both(w, {w.days[2]: {"S1": 0.2}})
    _, _, x2 = run_both(w, {w.days[2]: {"S2": 0.1}})
    base.key, x2.key = "PRIMARY_ROBUST_KELLY:BASE", "PRIMARY_ROBUST_KELLY:COST_X2"
    window = {"suspensionStart": w.days[9]}
    rep = {"path": base.key, "ticker": "S1", "firstFailingSession": base.failure["day"], "entryTradeDay": w.days[2], "terminalWindow": window}
    out = A.cost_x2_explanation({base.key: base, x2.key: x2}, [rep])
    assert out[0]["costX2EverEntered"] is False and out[0]["costX2HeldWeightOnFailingSession"] == 0.0
    assert out[0]["baseTargetAtEntryDecision"] == 0.2 and out[0]["costX2TargetAtFailingPathEntryDecision"] is None
    table = A.exposure_table({base.key: base, x2.key: x2}, {"S1": {"suspensionStart": w.days[9], "lastPricedSession": w.days[15]}})
    assert table[base.key]["S1"]["suspensionStart"] > 0 and table[x2.key]["S1"] == {"suspensionStart": 0.0, "lastPricedSession": 0.0}


# --------------------------------------------------------------------------- #
# Model-free scan
# --------------------------------------------------------------------------- #
def _frame(days, closes, volumes=None):
    return pd.DataFrame({"Close": closes, "Volume": volumes if volumes is not None else [1.0] * len(closes)}, index=pd.to_datetime(days))


def test_gap_events_separate_terminal_ends_from_mid_series_gaps_and_ignore_names_before_membership():
    days = ["2021-01-%02d" % d for d in range(4, 16)]
    frames = {B: _frame(days, [1.0] * 12),
              "T1": _frame(days[:6], [1.0] * 6),                          # ends after day 5
              "G1": _frame(days[:3] + days[5:], [1.0] * 10),              # two-session hole
              "L1": _frame(days[8:], [1.0] * 4)}                          # listed later; member only from day 9
    members = {days[0]: ["T1", "G1"], days[8]: ["T1", "G1", "L1"]}
    out = A.gap_events(frames, members, days)
    assert out["benchmarkMissingSessions"] == []
    assert [(e["ticker"], e["firstMissing"], e["resumes"]) for e in out["events"]] == [("G1", days[3], True), ("T1", days[6], False)]
    assert out["terminalEnds"][0]["lastPricedBefore"] == days[5] and out["midSeriesGaps"][0]["sessions"] == 2


def test_committed_model_free_scan_is_internally_consistent_with_the_terminal_inventory():
    scan = json.loads(SCAN.read_text())
    assert scan["evidenceClass"] == A.EVIDENCE_CLASS_SCAN and scan["provenance"]["replayManifestSha256"] == A.FORMAL["replayManifestSha256"]
    assert scan["benchmarkMissingSessions"] == [] and scan["midSeriesGaps"] == []
    assert scan["replayWindow"] == {"cutoff": T.DEVELOPMENT_CUTOFF, "firstOuterAnchor": "2018-01-29", "outerAnchors": 101, "sessions": 2116}
    terminal = {e["ticker"] for e in scan["terminalEnds"]}
    assert len(terminal) == 8 and terminal == set(scan["terminalWindows"]) == set(scan["terminalFoundation"])
    for t, w in scan["terminalWindows"].items():
        f = scan["terminalFoundation"][t]
        assert f["inTerminatedSecurityInventory"] and f["lastTradingDate"] == w["lastPricedSession"]
        assert f["reconstructionCompleteness"]["terminalActionChainResolved"] == "BLOCKED"
        assert w["suspensionStart"] < w["lastPricedSession"] < w["firstUnpricedSession"] and w["suspendedSessions"] >= 12
    assert scan["top120AtTheLastOuterSignalBeforeSuspension"] == ["000030.KS", "000060.KS", "003410.KS", "008560.KS", "010620.KS", "079440.KS"]


# --------------------------------------------------------------------------- #
# Reproduction gate and the sealed result
# --------------------------------------------------------------------------- #
def test_reproduction_gate_refuses_any_divergence_and_ignores_only_the_marker_counter():
    sealed = json.loads((ROOT / A.FORMAL["resultPath"]).read_text())
    same = json.loads(json.dumps(sealed))
    same["counters"]["markerWrites"] = 0
    assert A.reproduction_check(same, sealed)["status"] == "RECONSTRUCTION_REPRODUCES_THE_SEALED_RESULT"
    moved = json.loads(json.dumps(sealed))
    moved["paths"]["PRIMARY_ROBUST_KELLY:COST_X2"]["cagr"] += 1e-6
    out = A.reproduction_check(moved, sealed)
    assert out["status"] == "RECONSTRUCTION_MISMATCH" and out["firstDivergence"].startswith("paths/PRIMARY_ROBUST_KELLY:COST_X2/cagr")
    flipped = json.loads(json.dumps(sealed))
    flipped["complete"]["PRIMARY_ROBUST_KELLY:BASE"] = True
    assert A.reproduction_check(flipped, sealed)["firstDivergence"].startswith("complete/PRIMARY_ROBUST_KELLY:BASE")
    fewer = json.loads(json.dumps(sealed))
    fewer["counters"]["allocatorSolves"] -= 1
    assert A.reproduction_check(fewer, sealed)["firstDivergence"].startswith("counters/allocatorSolves")


def test_the_sealed_result_is_read_not_written(tmp_path):
    result = A.verify_sealed_result(ROOT)
    assert result["verdict"]["verdict"] == "BLOCKED_BY_DATA_INTEGRITY"
    assert hashlib.sha256((ROOT / A.FORMAL["resultPath"]).read_bytes()).hexdigest() == A.FORMAL["resultSha256"]
    copy = tmp_path / A.FORMAL["resultPath"]
    copy.parent.mkdir(parents=True)
    shutil.copy(ROOT / A.FORMAL["resultPath"], copy)
    copy.write_bytes(copy.read_bytes().replace(b'"code":"E"', b'"code":"A"'))
    with pytest.raises(ValueError, match="SEALED_RESULT_BYTES_CHANGED"):
        A.verify_sealed_result(tmp_path)
    from scripts import run_kr_alpha_discovery_tournament_v1_postoutcome_integrity_audit as S
    with pytest.raises(ValueError, match="REFUSING_TO_WRITE_THE_SEALED_RESULT"):
        S._write(ROOT / A.FORMAL["resultPath"], {})


def test_the_formal_execution_artifacts_and_locks_are_untouched_by_this_audit():
    provenance = json.loads((ROOT / "docs/results/kr-alpha-discovery-tournament-v1-seal-provenance.json").read_text())
    for rel, meta in provenance["committedFiles"].items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == meta["sha256"], rel
    assert provenance["lockRefs"] == A.FORMAL["lockRefs"] and provenance["executionRunId"] == A.FORMAL["executionRunId"]
    assert provenance["artifactId"] == A.FORMAL["resultArtifactId"] and provenance["artifactGithubDigest"] == A.FORMAL["resultArtifactDigest"]


# --------------------------------------------------------------------------- #
# Nothing here can reach a lock, a marker, the formal execute path or a write to GitHub
# --------------------------------------------------------------------------- #
FORBIDDEN = {"claim_execution_lock", "write_marker", "authorize_execution", "lock_exists", "github_api", "require_lock", "require_permit",
             "ExecutionLock", "ExecutionPermit", "atomic_write", "seal"}


@pytest.mark.parametrize("path", AUDIT_FILES, ids=lambda p: p.name)
def test_audit_code_never_references_a_lock_marker_or_the_formal_execute(path):
    tree = ast.parse(path.read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & FORBIDDEN, names & FORBIDDEN
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "E":
            assert node.attr != "execute"
    text = path.read_text()
    assert "urllib" not in text and "requests" not in text and "subprocess" not in text


def _top_level_block(text, key):
    """The lines of one top-level YAML block (`key:` at column 0) up to the next top-level key (no YAML library is a dependency here)."""
    lines = text.splitlines()
    i = lines.index(key + ":")
    out = []
    for line in lines[i + 1:]:
        if line and not line.startswith((" ", "#")):
            break
        out.append(line)
    return [line for line in out if line.strip() and not line.strip().startswith("#")]


def _github_scripts(text):
    """Every `script: |` body, de-indented, read from the workflow text."""
    lines, out = text.splitlines(), []
    for i, line in enumerate(lines):
        if line.strip() == "script: |":
            indent = len(line) - len(line.lstrip())
            body = []
            for nxt in lines[i + 1:]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                body.append(nxt)
            width = min(len(b) - len(b.lstrip()) for b in body if b.strip())
            out.append("\n".join(b[width:] for b in body))
    return out


def test_workflow_is_manual_read_only_and_never_executes_or_writes():
    text = WORKFLOW.read_text()
    on = _top_level_block(text, "on")
    assert [line.strip() for line in on if len(line) - len(line.lstrip()) == 2] == ["workflow_dispatch:"]
    assert "required: true" in "\n".join(on) and "audit_ref:" in "\n".join(on)
    assert [line.strip() for line in _top_level_block(text, "permissions")] == ["contents: read", "actions: read"]
    code = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    assert sum("permissions:" in line for line in code) == 1             # top level only: no job widens it
    for bad in ("--mode execute", "contents: write", "git push", "createRef", "POST /git/refs", "deleteRef", "updateRef", "mode: seal",
                "pull_request", "schedule:", "push:"):
        assert not any(bad in line for line in code), bad
    assert "--mode scan" in text and "--mode full" in text and A.FORMAL["rawInputArtifactName"] in text


def test_workflow_github_script_compiles_with_the_injected_names(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    scripts = _github_scripts(WORKFLOW.read_text())
    assert len(scripts) == 1 and "listMatchingRefs" in scripts[0]
    for i, body in enumerate(scripts):
        src = tmp_path / ("s%d.js" % i)
        src.write_text("const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;\n"
                       "new AsyncFunction('require','__original_require__','github','context','core','exec','glob','io','getOctokit','octokit', "
                       + json.dumps(body) + ");\n")
        subprocess.run([node, str(src)], check=True)


# --------------------------------------------------------------------------- #
# The traced path loop is the frozen run_paths: identical outputs and counters on the invented tournament world
# --------------------------------------------------------------------------- #
def test_traced_paths_reproduce_run_paths_exactly_on_the_invented_tournament_world():
    from pipeline import kr_alpha_tournament_execution as E
    from pipeline import kr_alpha_tournament_features as F
    from pipeline import kr_alpha_tournament_study as ST
    from pipeline import kr_alpha_tournament_walkforward as W
    world = ST.SyntheticWorld(names=24, industries=4)
    rows = world.signal_rows()
    data = W.prepare_data(F.represent(rows))
    labels = W.align_labels(data, ST.build_labels(rows, world.calendar, world.close_at, world.through))
    risk = world.risk()
    process = W.run_process(data, labels, world.anchors, ST.synthetic_registry(False), risk, world.calendar, {})
    first = W.outer_folds(world.anchors)[0]["anchors"][0][0]
    frozen_counters, traced_counters = {}, {}
    frozen = ST.run_paths(process["anchors"], data, risk, world.days, first, world.through, world.mark, world.executable, world.adv_of,
                          frozen_counters)
    traced, traces = A.trace_paths(process["anchors"], data, risk, world.days, first, world.through, world.mark, world.executable,
                                   world.adv_of, traced_counters)
    assert list(frozen) == list(traced) and frozen_counters == traced_counters
    assert E.json_safe({"%s:%s" % k: v for k, v in frozen.items()}) == E.json_safe({"%s:%s" % k: v for k, v in traced.items()})
    assert set(traces) == {"%s:%s" % k for k in frozen} and all(t.failure is None for t in traces.values())
    primary = traces["PRIMARY_ROBUST_KELLY:BASE"]
    assert primary.trades and all(tr["day"] is not None for tr in primary.trades)
    assert len(primary.held) == len([d for d in world.days if first <= d <= world.through])
    a = ST.assemble(process, frozen, labels, 100.0)
    b = ST.assemble(process, traced, labels, 100.0)
    assert A.reproduction_check(E.json_safe(dict(a, counters={})), E.json_safe(dict(b, counters={})))["status"].startswith("RECONSTRUCTION_REPRODUCES")
