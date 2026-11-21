"""US industry codes: SIC code and description per issuer from data.sec.gov submissions metadata.

    python -m research.investment_decision_alpha_v1.collect_us_sic --private <dir with us/filings.pkl> --out <dir>

One request per CIK (the CIKs come from the PIT filings already used by #343-#354), paced under SEC's 10/s, generic
User-Agent. The SIC code is the issuer's CURRENT assignment, not a dated one; that limitation is published with every result.
"""
from __future__ import annotations

import argparse
import csv
import pickle
import time
from pathlib import Path

from research.kr_us_earnings_expectations_v1.collect_us_8k import get


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    raw = pickle.load(open(Path(a.private) / "us" / "filings.pkl", "rb"))["raw"]
    ciks = {}
    for t, rs in raw.items():
        c = [r.get("cik") for r in rs if r.get("cik")]
        if c:
            ciks[t] = str(int(c[-1]))
    rows, fail = [], 0
    for n, (t, cik) in enumerate(sorted(ciks.items())):
        try:
            s = get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
            rows.append({"ticker": t, "cik": cik, "sic": s.get("sic") or "", "sicDescription": s.get("sicDescription") or "",
                         "status": "SERVED"})
        except Exception as e:  # noqa: BLE001
            fail += 1
            rows.append({"ticker": t, "cik": cik, "sic": "", "sicDescription": "", "status": f"FAILED:{type(e).__name__}"})
        time.sleep(0.25)
        if n % 100 == 0:
            print(n, t, fail, flush=True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "us-sic.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("done", len(rows), "failed", fail)


if __name__ == "__main__":
    main()
