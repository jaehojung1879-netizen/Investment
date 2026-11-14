"""ml-strategy-tournament-v1 — step 1: materialise the PIT feature matrix by CALLING the existing Phase B builder.

No new feature arithmetic lives here. `kr_alpha_atlas_inputs.load_inputs` verifies every pinned input (git blob / content hash) at the
pinned signal-history commit, and `kr_alpha_atlas_matrix.build_matrix` produces the outcome-blind (signal_date, ticker) matrix. The
matrix digest is printed so the run can be compared with the Phase B / Phase C v4 registered digests.

    python research/ml_strategy_tournament_v1/build_features.py --scratch <dir> --out <dir>/matrix.pkl
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline import kr_alpha_atlas_inputs as AI  # noqa: E402
from pipeline import kr_alpha_atlas_matrix as M  # noqa: E402
from pipeline import regional_alpha_features as RAF  # noqa: E402

PINNED_COMMIT = "4ea107ed0cde289f0a049a65ff13d2441a786710"
FEATURE_START, CUTOFF = "2013-01-01", "2026-09-14"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    t0 = time.time()
    inputs = AI.load_inputs(PINNED_COMMIT, a.scratch)
    dates = RAF.weekly_grid(FEATURE_START, CUTOFF, "KR")
    counters = {}
    matrix = M.build_matrix(inputs, dates, counters)
    Path(a.out).write_bytes(pickle.dumps({"matrix": matrix, "identity": inputs.identity, "tradingValueBasis": inputs.trading_value_basis}))
    print(json.dumps({"rows": len(matrix.rows), "columns": matrix.values.shape[1], "matrixDigest": matrix.digest(),
                      "inputIdentitySha256": inputs.identity["sha256"], "seconds": round(time.time() - t0, 1), "counters": counters}, default=str))


if __name__ == "__main__":
    main()
