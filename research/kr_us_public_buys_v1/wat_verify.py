"""Cross-check WAT and shared cap overlays against retained schedules and outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.kr_us_public_buys_v1 import wat, wat_sources
from research.kr_us_replica_filter_v1 import us as replica
from research.kr_us_strategy_batch_v1 import us as batch

HERE = Path(__file__).resolve().parent


def prior_checks(out, p):
    cohort = pd.read_csv(out/"cohorts.csv.gz", parse_dates=["date"])
    changes = pd.read_csv(out/"target-weight-deltas.csv.gz", parse_dates=["date"])
    old_copy = cohort.loc[cohort.case.eq("WAT_UNIT_ONLY")]
    rows = {}
    for h in wat.HORIZONS:
        root = replica.HERE/"results/US"
        before = pd.read_csv(root/f"cohorts-{h}.csv.gz", parse_dates=["date"]).set_index("date")
        prior = pd.read_csv(replica.PRIOR/"results/US"/f"cohorts-{h}.csv.gz", parse_dates=["date"])
        prior = prior.loc[prior.config.eq("U1")].set_index("date")
        raw = pd.read_csv(batch.HERE/"results/US"/f"cohorts-net-{h}.csv.gz", index_col=0, parse_dates=True)
        expected = {"B":before.netExcess, "U1_NATIVE":raw["US:NATIVE_U1"]-raw["US:SPY"],
                    "U1_20":prior.legacy, "U1_FUNDED":prior.funded}
        diffs = {}
        for k, exp in expected.items():
            b = old_copy.loc[old_copy.horizon.eq(h)&old_copy.book.eq(k)].set_index("date")
            cmp = exp.reindex(b.index)
            assert cmp.notna().equals(b.oldNetExcessSPY.notna())
            error = (cmp-b.oldNetExcessSPY).abs().max()
            assert error < 1e-12
            diffs[k] = {"sameMaturityAndMissingness": True, "originalParityMaxError": error}
        valid = cohort.loc[cohort.horizon.eq(h)&cohort.netChange.notna()].set_index(["case","book","date"]).netChange
        trace = changes.loc[changes.date.isin(valid.index.get_level_values("date"))].copy()
        q = p["net_asset"][h].stack().rename("quote").rename_axis(["date","ticker"])
        trace = trace.merge(q, left_on=["date","ticker"], right_index=True, how="left")
        trace["delta"] = trace.weightChange*trace.quote
        grp = trace.groupby(["case","book","date"]).delta
        computed = grp.sum(min_count=1).reindex(valid.index, fill_value=0.)
        assert np.allclose(computed, valid, atol=1e-10, rtol=0)
        rows[str(h)] = {"priorCohorts": diffs,
                        "deltaFromTargetChangesMaxError": float((computed-valid).abs().max())}
    weight_error = changes.groupby(["case","book","date"]).weightChange.sum().abs().max()
    assert weight_error < 1e-10
    return rows, weight_error


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=HERE/"results/WAT")
    ap.add_argument("--private", type=Path, default=Path("/workspace/batch-inputs/us"))
    ap.add_argument("--inputs", type=Path, default=Path("/workspace/exposure-inputs/us"))
    a = ap.parse_args(argv)
    p, _, hashes = replica.load_frozen(a.private, a.inputs)
    caps = pd.read_csv(a.out/"corrected-caps.csv", parse_dates=["date"])
    assert not caps[["date","ticker"]].duplicated().any()
    days = {d: wat_sources.decision_close(d) for d in caps.date.unique()}
    assert all(pd.Timestamp(r.acceptedET) < days[r.date] for r in caps.itertuples(index=False))
    state = json.loads((a.out/"summary.json").read_text())
    assert len(caps) == state["correctedCapRows"]
    assert state["inputSha256"] == hashes
    checks, weights = prior_checks(a.out, p)
    batch.save(a.out/"verification.json", {"availabilityChronologyCheckedRows": len(caps), "horizons": checks,
               "weightSumMaxError": weights, "inputSha256": hashes})
    print("Source cutoff, all four prior cohort books and per-date P&L decomposition verified.")


if __name__ == "__main__":
    main()
