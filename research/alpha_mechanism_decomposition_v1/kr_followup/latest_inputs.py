"""Latest KR inputs for the four-book record: the sealed Phase B inputs, extended past 2026-09-14 under explicit, checked rules.

    python research/alpha_mechanism_decomposition_v1/kr_followup/latest_inputs.py --raw <pinned raw dir> --tip <signal-history commit> --out <dir>

WHY A SECOND LOADER. `kr_alpha_atlas_inputs.load_inputs` refuses every commit but the pinned 4ea107ed (COMMIT_IS_NOT_THE_PINNED_SOURCE_COMMIT), and the replay
panel it reads ends on 2026-09-14. This loader does not edit or bypass it: it CALLS it for the sealed base, then appends only what the newer signal-history
commit adds, and records every appended byte by git blob.

EXTENSION RULES (each is a check that raises, or a label that travels with the data)
  PREFIX_STABILITY       every pinned KRX bar row and universe row is byte-for-byte identical at the tip; the tip only appends later dates.
  PRICE_EXTENSION        a ticker's replay close after its last replay date = last replay close x (KRX as-traded close / KRX close on that same date).
                         AS_TRADED_NO_DISTRIBUTIONS: any dividend after 2026-09-14 is missing from the extension (labelled, never filled).
  BENCHMARK_EXTENSION    069500.KS is not in the KRX stock-bar ledger and the repository benchmark ends 2026-09-15 even at the tip, so its extension uses
                         Yahoo's 069500.KS close (VENDOR_YAHOO_UNVERIFIED). H01 subtracts the same benchmark from every industry, so book DECISIONS do
                         not depend on it; only NAV marks of the 069500 slot do.
  FUNDAMENTALS / INDUSTRY  unchanged pinned versions (no post-pin DART filing is read here: no key); stated, not hidden.
Nothing here is a receipt or prospective evidence.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import pickle
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from pipeline import kr_alpha_atlas_inputs as AI  # noqa: E402
from pipeline import kr_alpha_atlas_matrix as M  # noqa: E402
from pipeline import regional_alpha_features as RAF  # noqa: E402

PINNED = "4ea107ed0cde289f0a049a65ff13d2441a786710"
LAST_PINNED = "2026-09-14"
BENCH = "069500.KS"


def blob(commit, path):
    return subprocess.check_output(["git", "cat-file", "blob", f"{commit}:{path}"], cwd=ROOT)


def jsonl(raw):
    return [json.loads(x) for x in gzip.decompress(raw).decode().splitlines() if x.strip()]


def prefix_stable(pinned_rows, tip_rows, key, cutoff):
    a = {key(r): r for r in pinned_rows if r["date"] <= cutoff}
    b = {key(r): r for r in tip_rows if r["date"] <= cutoff}
    if a != b:
        raise ValueError("PREFIX_STABILITY_BROKEN: %d pinned rows changed or vanished at the tip" % sum(1 for k in a if a[k] != b.get(k)))
    return len(a), sum(1 for r in tip_rows if r["date"] > cutoff)


def yahoo_bench(start, end):
    import yfinance as yf
    d = yf.download(BENCH, start=start, end=end, auto_adjust=False, progress=False)
    s = d["Close"]
    s = s.iloc[:, 0] if isinstance(s, pd.DataFrame) else s
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s.dropna()


def load_latest(raw_root, tip, bench_series=None):
    base = AI.load_inputs(PINNED, raw_root)                 # the sealed loader, unchanged, verifies every pinned input
    ident = {"base": base.identity, "tipCommit": tip, "extensions": {}}
    # ---- bars ------------------------------------------------------------------------------------------------------------- #
    path = "ledger/prices/kr/krx-prices-2026.jsonl.gz"
    pin_rows, tip_raw = jsonl(blob(PINNED, path)), blob(tip, path)
    tip_rows = jsonl(tip_raw)
    kept, added = prefix_stable(pin_rows, tip_rows, lambda r: (r["ticker"], r["date"]), LAST_PINNED)
    ident["extensions"]["krxBars2026"] = {"path": path, "tipGitBlobSha1": subprocess.check_output(["git", "rev-parse", f"{tip}:{path}"], cwd=ROOT).decode().strip(),
                                          "pinnedRowsIdenticalAtTip": kept, "rowsAppended": added, "lastDate": max(r["date"] for r in tip_rows)}
    # ---- universe ------------------------------------------------------------------------------------------------------------ #
    upath = "ledger/universe/kr/krx-universe-2026.jsonl.gz"
    u_pin, u_tip_raw = jsonl(blob(PINNED, upath)), blob(tip, upath)
    u_tip = jsonl(u_tip_raw)
    ukept, uadded = prefix_stable(u_pin, u_tip, lambda r: (r["ticker"], r["date"]), "2026-09-01")
    new_snaps = sorted({r["date"] for r in u_tip if r["date"] > "2026-09-01"})
    ident["extensions"]["universe2026"] = {"path": upath, "pinnedRowsIdenticalAtTip": ukept, "rowsAppended": uadded, "snapshotsAppended": new_snaps}
    grouped = {}
    for r in u_tip:
        if r["date"] in new_snaps:
            grouped.setdefault(r["date"], []).append(r)
            base.universe_rows.setdefault(r["date"], []).append({k: r.get(k) for k in ("ticker", "rank", "marketCap", "name")})
            base.names[r["ticker"]] = r.get("name") or base.names.get(r["ticker"])
    snaps = list(base.memberships.snapshots) + [{"date": d, "members": sorted(x["ticker"] for x in sorted(rows, key=lambda x: (x["rank"], x["ticker"]))[:120])}
                                                for d, rows in sorted(grouped.items())]
    base.memberships = RAF.MembershipSnapshots(snaps)
    # ---- rebuild bars for every ticker ever seen, pinned history + tip 2026 --------------------------------------------------- #
    ever = {t for s in snaps for t in s["members"]}
    rows_by = {}
    for year in range(2013, 2026):
        for r in jsonl(blob(PINNED, f"ledger/prices/kr/krx-prices-{year}.jsonl.gz")):
            if r["ticker"] in ever:
                rows_by.setdefault(r["ticker"], []).append(r)
    for r in tip_rows:
        if r["ticker"] in ever:
            rows_by.setdefault(r["ticker"], []).append(r)
    base.bars = AI._bar_frames(rows_by, base.calendar, ever, None)
    # ---- price panel extension ------------------------------------------------------------------------------------------------ #
    bars_close = {t: pd.Series({pd.Timestamp(r["date"]): float(r["close"]) for r in rs if r.get("close")}) for t, rs in rows_by.items()}
    ext_n, missing = 0, []
    for t in sorted(ever):
        frame = base.prices.get(t)
        bc = bars_close.get(t)
        if bc is None or bc.empty:
            missing.append(t)
            continue
        if frame is None or frame.empty:
            missing.append(t)                                  # a name with no replay history is left without a panel, never seeded from bars
            continue
        last = frame.index.max()
        if last not in bc.index:
            missing.append(t)
            continue
        f = float(frame.loc[last, "Close"]) / bc.loc[last]
        after = bc[bc.index > last]
        if after.empty:
            continue
        vol = pd.Series({pd.Timestamp(r["date"]): float(r["volume"]) for r in rows_by[t]}).reindex(after.index)
        ext = pd.DataFrame({"Close": after * f, "High": after * f, "Low": after * f, "Open": after * f, "Volume": vol})
        base.prices[t] = pd.concat([frame, ext[[c for c in frame.columns if c in ext.columns]]])
        ext_n += len(after)
    if bench_series is not None:
        frame = base.prices[BENCH]
        last = frame.index.max()
        f = float(frame.loc[last, "Close"]) / float(bench_series.loc[last])
        after = bench_series[bench_series.index > last]
        ext = pd.DataFrame({"Close": after * f, "High": after * f, "Low": after * f, "Open": after * f, "Volume": 1.0})
        base.prices[BENCH] = pd.concat([frame, ext[[c for c in frame.columns if c in ext.columns]]])
        ident["extensions"]["benchmark"] = {"source": "VENDOR_YAHOO_UNVERIFIED (069500.KS Close)", "chainedAt": str(last.date()),
                                            "lastDate": str(after.index.max().date()), "sessionsAppended": len(after)}
    ident["extensions"]["pricePanel"] = {"rule": "AS_TRADED_NO_DISTRIBUTIONS", "sessionsAppendedAcrossTickers": ext_n, "tickersWithoutExtension": missing}
    ident["sha256"] = hashlib.sha256(json.dumps(ident, sort_keys=True, default=str).encode()).hexdigest()
    base.identity = ident
    return base


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--tip", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    bench = yahoo_bench("2026-09-01", "2026-11-14")
    inp = load_latest(a.raw, a.tip, bench)
    dates = [d for d in RAF.weekly_grid("2026-08-01", "2026-10-30", "KR") if d >= "2026-09-11"]
    counters = {}
    matrix = M.build_matrix(inp, dates, counters)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest-matrix.pkl").write_bytes(pickle.dumps({"matrix": matrix, "identity": inp.identity, "dates": dates}))
    pickle.dump({"prices": inp.prices, "universe_rows": inp.universe_rows}, open(out / "latest-prices.pkl", "wb"))
    print(json.dumps({"dates": dates, "rows": len(matrix.rows), "identity": inp.identity["extensions"]}, default=str, indent=1)[:3000])


if __name__ == "__main__":
    main()
