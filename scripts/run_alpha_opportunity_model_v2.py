"""alpha-opportunity-model-v2: print readiness, or execute only after every gate.

Order is fixed and fail-closed:
  1. reviewed external seal == sidecar == canonical spec; v1 seal re-verified
  2. merged main, clean checkout, explicit review acknowledgement
  3. sealed raw-input identities (no extra shards)
  4. features, tradability and survivorship eligibility — NO labels yet
  5. pre-label gates: region-year eligibility, coverage, calendar depth
  6. only then labels, walk-forward fits, decisions and evidence
No positions, weights, NAV or production writes are ever produced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_v2_spec as S  # noqa: E402


class PreLabelStop(Exception):
    """A registered pre-label gate failed; no label has been constructed."""

    def __init__(self, status, detail):
        super().__init__(status)
        self.status, self.detail = status, detail


def verify_inputs(spec, root):
    root = Path(root)
    for rel, blob in spec["inputFiles"].items():
        data = (root / rel).read_bytes()
        got = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if got != blob:
            raise ValueError("INPUT_SNAPSHOT_CHANGED: " + rel)
    manifest = S.read_json(root / "ledger/historical/replay-v16/inputs.json")
    if S.digest({k: v for k, v in manifest.items() if k != "sha256"}) != spec["snapshots"]["replayManifestSha256"]:
        raise ValueError("REPLAY_MANIFEST_CHANGED")
    for folder, pattern in (("fundamentals/us", "finnhub-*.jsonl.gz"),
                            ("fundamentals/kr", "dart-*.jsonl.gz"),
                            ("universe/kr", "krx-universe-*.jsonl.gz")):
        for path in (root / "ledger" / folder).glob(pattern):
            if str(path.relative_to(root)) not in spec["inputFiles"]:
                raise ValueError("UNSEALED_RAW_SHARD")
    return {"snapshotFiles": True, "replayManifest": True}


def tradability_frame(prices, frame, region, window):
    """PIT tradability + vouched flags per (date, ticker); never reads past a date."""
    import numpy as np
    import pandas as pd
    from pipeline import replay_calendar as RC
    rows = frame.loc[frame.region.eq(region), ["date", "ticker"]]
    days = RC.sessions("2012-01-01", str(rows.date.max()), region)
    out = []
    for ticker, group in rows.groupby("ticker"):
        f = prices.get(ticker)
        dates = pd.to_datetime(group.date)
        if f is None or "Close" not in f or "Volume" not in f:
            out.append(pd.DataFrame({"date": group.date, "ticker": ticker, "vouched": False,
                                     "tradable": False, "tradabilityReason": "NO_SEALED_PRICE_PANEL"}))
            continue
        panel = f.reindex(days)
        close = pd.to_numeric(panel.Close, errors="coerce")
        volume = pd.to_numeric(panel.Volume, errors="coerce")
        good_close = (close > 0) & np.isfinite(close)
        good = good_close & (volume > 0) & np.isfinite(volume)
        full = good.astype(int).rolling(window, min_periods=window).sum().eq(window)
        vouched = good_close.reindex(dates, fill_value=False).to_numpy(bool)
        tradable = full.reindex(dates, fill_value=False).to_numpy(bool)
        reason = np.where(tradable, "TRADABLE",
                          np.where(vouched, "NOT_CONTINUOUSLY_TRADED_IN_WINDOW", "NO_SIGNAL_DATE_PRICE"))
        out.append(pd.DataFrame({"date": group.date.to_numpy(), "ticker": ticker,
                                 "vouched": vouched, "tradable": tradable, "tradabilityReason": reason}))
    return pd.concat(out, ignore_index=True).assign(region=region)


def eligibility(frame, spec):
    """Region-year survivorship eligibility: unvouched PIT-member share <= tolerance."""
    tol = spec["survivorship"]["regionYearUnvouchedTolerancePct"]
    table = (frame.assign(year=frame.date.str[:4])
             .groupby(["region", "year"]).vouched.agg(["size", "sum"]).reset_index())
    table["unvouchedPct"] = 100.0 * (1 - table["sum"] / table["size"])
    table["eligible"] = table.unvouchedPct <= tol
    return [{"region": r.region, "year": r.year, "memberDates": int(r.size),
             "unvouchedPct": float(r.unvouchedPct), "eligible": bool(r.eligible)}
            for r in table.itertuples()]


def pre_label_gates(frame, registry, spec):
    """Coverage and calendar depth, from features and calendars only."""
    from pipeline import alpha_opportunity_features as F
    from pipeline import alpha_opportunity_v2_evaluation as E
    cov_cfg = spec["coverageGate"]
    eligible = frame.loc[frame.eligibleRegionYear & frame.tradable]
    coverage = F.coverage(eligible, registry)
    failures = [c for c in coverage if int(c["year"]) >= cov_cfg["firstEvaluationYear"]
                and c["coverage"] < (cov_cfg["price"] if c["feature"] in F.PRICE + F.ATTENTION
                                     else cov_cfg["accounting"])]
    if failures:
        raise PreLabelStop("BLOCKED_BY_DATA_INTEGRITY", {"coverageFailures": failures})
    depth = {}
    for region in spec["regions"]:
        dates = eligible.loc[eligible.region.eq(region)].drop_duplicates("date")
        by_year = dates.date.str[:4].value_counts().to_dict()
        depth[region] = E.calendar_depth(by_year, spec)
        if depth[region]["status"] != "SUFFICIENT_UPPER_BOUND":
            raise PreLabelStop("BLOCKED_BY_SAMPLE_DEPTH", {"calendarDepth": depth})
    return coverage, depth


def execute(spec, registry, input_root, us_membership, output):
    import pandas as pd
    from pipeline import alpha_opportunity_features as F
    from pipeline import alpha_opportunity_evaluation as V1E
    from pipeline import alpha_opportunity_v2_decision as D
    from pipeline import alpha_opportunity_v2_evaluation as E
    from pipeline import alpha_opportunity_v2_model as M
    from pipeline import regional_alpha_features as sources
    from pipeline import replay_calendar as RC

    output = Path(output).resolve()
    if output.exists() or output.is_relative_to(ROOT) or output.is_relative_to(Path(input_root).resolve()):
        raise ValueError("OUTPUT_MUST_BE_NEW_AND_OUTSIDE_SOURCE_AND_INPUTS")
    manifest, prices, _, _ = sources.load_inputs(Path(input_root) / "ledger")
    if manifest["sha256"] != spec["snapshots"]["replayManifestSha256"]:
        raise ValueError("INPUT_MANIFEST_MISMATCH")
    if S.file_hash(us_membership) != spec["snapshots"]["usMembershipSha256"]:
        raise ValueError("MEMBERSHIP_SNAPSHOT_CHANGED")
    memberships = sources.load_memberships(Path(input_root) / "ledger", us_membership)
    raw, shares = F.load_raw(Path(input_root) / "ledger")
    frame = F.build_matrix(prices, memberships, raw, shares,
                           start=spec["walkForward"]["featureStart"], through=spec["dataCutoff"])
    window = spec["tradabilityGuard"]["windowSessions"]
    guard = pd.concat([tradability_frame(prices, frame, r, window) for r in spec["regions"]],
                      ignore_index=True)
    frame = frame.merge(guard, on=["date", "region", "ticker"], how="left", validate="one_to_one")
    if frame.tradable.isna().any():
        raise ValueError("TRADABILITY_UNRESOLVED")
    frame["tradable"] = frame.tradable.astype(bool)
    frame["vouched"] = frame.vouched.astype(bool)
    eligible_years = eligibility(frame, spec)
    ok = {(e["region"], e["year"]) for e in eligible_years if e["eligible"]}
    frame["eligibleRegionYear"] = [(r, d[:4]) in ok for r, d in zip(frame.region, frame.date)]
    unvouched_by_date = (1 - frame.groupby(["region", "date"]).vouched.mean()).to_dict()
    base = {"studyId": S.STUDY, "specSha256": S.digest(spec), "evidenceClass": "DISCOVERY_ONLY",
            "promotionEligible": False, "regionYearEligibility": eligible_years}
    try:
        coverage, depth = pre_label_gates(frame, registry, spec)
    except PreLabelStop as stop:
        report = {**base, "status": stop.status, "stoppedBeforeLabels": True, "detail": stop.detail,
                  "results": [], "folds": [], "coverage": None, "ownershipOverlay": spec["ownershipOverlay"]["status"]}
        S.validate_result(report, None, spec)
        output.mkdir(parents=True)
        (output / "research-results.json").write_bytes(S.canonical(report) + b"\n")
        return report

    # ---- Labels exist only past this line. ------------------------------
    predictions, fold_records, failures, results = [], [], [], []
    for region in spec["regions"]:
        sessions = RC.sessions("2012-01-01", "2027-12-31", region)
        regional = frame.loc[frame.region.eq(region) & frame.eligibleRegionYear & frame.tradable].copy()
        regional["roundTripCost"] = [D.dated_round_trip_cost(region, d, spec) for d in regional.date]
        schedule = sorted(regional.date.unique())
        for horizon in spec["horizons"]:
            labels = pd.DataFrame([E.target_from_sessions(sessions, prices, spec["benchmarks"][region],
                                                          t, d, horizon, spec["dataCutoff"])
                                   for t, d in zip(regional.ticker, regional.date)])
            data = E.attach_labels(regional, labels)
            out, folds, fails = M.predict_cell(data, schedule, region, horizon, spec, S.digest(spec))
            predictions.extend(out)
            fold_records.extend(folds)
            failures.extend(fails)
    combined = pd.concat(predictions, ignore_index=True) if predictions else None
    for region in spec["regions"]:
        for horizon in spec["horizons"]:
            cell = (combined.loc[combined.region.eq(region) & combined.horizon.eq(horizon)
                                 & combined.family.eq("LINEAR")] if combined is not None else None)
            results.append(E.evaluate_cell(
                cell, [f for f in fold_records if f["region"] == region and f["horizon"] == horizon],
                [f for f in failures if f["region"] == region and f["horizon"] == horizon],
                unvouched_by_date, spec, region=region, horizon=horizon))
    report = {**base, "status": "EXECUTED", "stoppedBeforeLabels": False, "results": results,
              "folds": fold_records, "coverage": coverage, "calendarDepth": depth,
              "numericalFailures": failures, "ownershipOverlay": spec["ownershipOverlay"]["status"],
              "familyDisagreement": [{"region": r, "horizon": int(h), "diagnostics": V1E.family_disagreement(g)}
                                     for (r, h), g in combined.groupby(["region", "horizon"])]
              if combined is not None else []}
    S.validate_result(report, combined, spec)
    output.mkdir(parents=True)
    (output / "research-results.json").write_bytes(S.canonical(report) + b"\n")
    if combined is not None:
        combined.to_json(output / "predictions.jsonl.gz", orient="records", lines=True,
                         compression={"method": "gzip", "mtime": 0})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=S.DEFAULT_SPEC)
    parser.add_argument("--sealed-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reviewed", action="store_true")
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--us-membership", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    spec, registry = S.load_sealed(args.spec, expected_hash=args.sealed_sha256)
    report = S.readiness(spec, args.sealed_sha256)
    if not args.execute:
        print(json.dumps(report, sort_keys=True))
        return 0
    S.require_execution(spec, reviewed=args.reviewed, branch=os.environ.get("GITHUB_REF"),
                        prerequisites={"sealed": True})
    if any(x is None for x in (args.input_root, args.us_membership, args.output)):
        raise ValueError("EXECUTION_INPUTS_REQUIRED")
    subprocess.run(["git", "merge-base", "--is-ancestor", "HEAD", "origin/main"], cwd=ROOT, check=True)
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                               cwd=ROOT, text=True).strip():
        raise ValueError("DIRTY_EXECUTION_CHECKOUT")
    prerequisites = verify_inputs(spec, args.input_root)
    S.require_execution(spec, reviewed=args.reviewed, branch=os.environ.get("GITHUB_REF"),
                        prerequisites=prerequisites)
    execute(spec, registry, args.input_root, args.us_membership, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
