"""Independent synthetic checks against exact #316 code, never ``execute``.

Requires the pinned Git objects locally. No ref checkout, network, real saved
outcomes or ledger access occurs. AST extraction makes the original outcome
entry point unavailable even to these regression checks.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType

from .source_audit import pinned_bytes


def synthetic_audit(repo: Path) -> dict:
    pins = json.loads(Path(__file__).with_name("reference-pins.json").read_text())
    calculator_raw = pinned_bytes(repo, pins["calculator"])
    runner_raw = pinned_bytes(repo, pins["runner"])
    name = "_fixed_c2_synthetic_audit_calculator"
    module = ModuleType(name)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(compile(calculator_raw, "<pinned-c2-calculator>", "exec"), module.__dict__)
        tree = ast.parse(runner_raw)
        allowed = {"sha256", "authorization_ok", "returns_from_closes", "cash_growth",
                   "window_closes", "build_blocks", "attribute_all", "path_returns", "analyse"}
        functions = ast.Module(body=[node for node in tree.body
                                     if isinstance(node, ast.FunctionDef) and node.name in allowed],
                               type_ignores=[])
        env = {"A": module, "json": json, "math": math, "Path": Path,
               "hashlib": hashlib, "ETF": "069500.KS"}
        exec(compile(functions, "<pinned-c2-pure-functions>", "exec"), env)
        if "execute" in env or "main" in env:
            raise RuntimeError("OUTCOME_ENTRY_POINT_PRESENT")

        # Fixture 1: a self-authored UNTRACKED file satisfies the promised owner gate.
        # Fake SHA only; no real authorization file or exception is constructed.
        with TemporaryDirectory(prefix="c2-synthetic-approval-") as folder:
            root = Path(folder)
            calc, run, auth = (root / n for n in ("c2_attribution.py", "runner.py", "auth.json"))
            calc.write_bytes(calculator_raw)
            run.write_bytes(runner_raw)
            fake_sha = "SYNTHETIC_NOT_A_REAL_SPEC_SHA"
            auth.write_text(json.dumps({
                "phrase": "APPROVE KR_PHASE_D_EXCEPTION c2-fixed-exposure-attribution-v1 " + fake_sha,
                "codeSha256": {"c2_attribution.py": hashlib.sha256(calculator_raw).hexdigest(),
                               "c2_attribution_run.py": hashlib.sha256(runner_raw).hexdigest()}}))
            env.update(HERE=root, AUTH=auth, __file__=str(run))
            auth_result = env["authorization_ok"](fake_sha)
        assert auth_result == (True, "AUTHORIZED")

        # Fixture 2: only eight of 100 blocks are attributable, all planted negative.
        rows = []
        for i in range(100):
            gross = 0.6 * 0.98 + 0.4 * 1.001 - 1
            rows.append({"date": f"SYN{i:03}", "endDate": f"SYN{i + 1:03}",
                         "signalDate": "SYN_SIGNAL", "weights": {t: 0.2 for t in ("A", "B", "C")},
                         "terminalWeights": {t: 0.2 * 0.98 / (1 + gross) for t in ("A", "B", "C")},
                         "grossReturn": gross + (0.05 if i >= 8 else 0),
                         "dailyRiskFreeNav": [1.0, 1.001],
                         "dailyDates": ["2030-01-02", "2030-01-31"]})
        closes = [100.0]
        for i in range(252):
            closes.append(closes[-1] * (1 + (-1) ** i * (i + 1) / 100_000))
        analysed = env["analyse"](rows, lambda day: 1.0, lambda ticker, signal: (closes, closes),
                                  lambda *args: 0.001, 10.0)
        assert len(analysed["failures"]) == 92
        assert analysed["byCost"]["1x"]["attributed"] == 8
        assert analysed["verdict"] == "SELECTION_NEGATIVE_AFTER_FIXED_EXPOSURE"

        # Fixture 3: changed net costs cannot change the current gross-selection CI.
        all_gross = [module.BlockResult(str(i), "ATTRIBUTED", by_cash={
            k: {"selection": 0.01} for k in module.CASH_SCENARIOS}) for i in range(24)]
        cheap = module.summarize(all_gross, [0.009] * 24,
                                 {k: [0.001] * 24 for k in module.CASH_SCENARIOS},
                                 [0.0] * 24, 2.0, 12.0)
        expensive = module.summarize(all_gross, [-0.03] * 24,
                                     {k: [0.001] * 24 for k in module.CASH_SCENARIOS},
                                     [0.0] * 24, 2.0, 12.0)
        key = module.CASH_SCENARIOS[0]
        assert cheap["scenarios"][key]["selectionAnnualized"] == expensive["scenarios"][key]["selectionAnnualized"]
        assert cheap["scenarios"][key]["c2VsControl"]["arithmeticActive"] > 0
        assert expensive["scenarios"][key]["c2VsControl"]["arithmeticActive"] < 0

        # Fixture 4: the original identities, ex-ante beta window and cash scenarios
        # continue to work without a new attribution engine.
        stock = [(-1) ** i * (i + 1) / 100_000 for i in range(252)]
        beta, n = module.ols_beta([0.6 * x for x in stock], stock)
        assert n == 252 and abs(beta - 0.6) < 1e-10
        block = module.Block("SYN_START", "SYN_END", "SYN_SIGNAL", {"SYN": 0.6},
                             {"SYN": 1.02}, {"SYN": 0.6}, 1.03,
                             {k: 1.001 for k in module.CASH_SCENARIOS}, 1 / 12)
        attributed = module.attribute_block(block)
        assert all(abs(v["selection"] + v["exposure"] -
                       (attributed.c2_gross - attributed.etf)) < 1e-12
                   for v in attributed.by_cash.values())

        return {"referencePins": {k: pins[k] for k in ("contract", "calculator", "runner")},
                "fixtures": {
                    "uncommittedSelfAuthoredFileAccepted": True,
                    "over10PercentUnattributableStillReturnsNegative": True,
                    "selectionCiUnaffectedByNetCostInputs": True,
                    "originalSyntheticIdentityAndBeta": "PASS"},
                "executionCountOrConsumedGatePresent": any(
                    name in runner_raw.decode().lower() for name in ("consumed", "flock", "o_excl")),
                "realHistoricalInputsRead": False, "realHistoricalOutcomesComputed": 0,
                "outcomeEntryPointAvailable": False, "outcomeExecutionAuthorized": False}
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = synthetic_audit(args.repo)
    # A new audit result must not overwrite an earlier evidence record.
    with args.out.open("x") as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
