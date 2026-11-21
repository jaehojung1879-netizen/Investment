"""US earnings-release timestamps: 8-K filings carrying Item 2.02 (Results of Operations), from data.sec.gov submissions metadata.

    python -m research.kr_us_earnings_expectations_v1.collect_us_8k --private <dir with us/filings.pkl> --out <dir>

Only the public submissions index is read (form, items, filingDate, acceptanceDateTime, accessionNumber, reportDate); no 8-K document is
downloaded (www.sec.gov refuses this environment). One request per CIK plus one per older-filings page, paced well under SEC's 10/s.
"""
from __future__ import annotations

import argparse
import json
import pickle
import time
import urllib.request
from pathlib import Path

UA = {"User-Agent": "research audit"}


def get(url):
    for k in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(2 * (k + 1))
    raise err


def rows_of(block):
    out = []
    for i, form in enumerate(block["form"]):
        if form in ("8-K", "8-K/A") and "2.02" in (block["items"][i] or ""):
            out.append({"form": form, "items": block["items"][i], "filingDate": block["filingDate"][i],
                        "acceptanceDateTime": block["acceptanceDateTime"][i], "accession": block["accessionNumber"][i],
                        "reportDate": block["reportDate"][i]})
    return out


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
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res, fail = {}, {}
    for n, (t, cik) in enumerate(sorted(ciks.items())):
        try:
            s = get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
            rows = rows_of(s["filings"]["recent"])
            for f in s["filings"].get("files", []):
                if f.get("filingTo", "") >= "2012-01-01":
                    rows += rows_of(get(f"https://data.sec.gov/submissions/{f['name']}"))
                    time.sleep(0.25)
            res[t] = {"cik": cik, "rows": rows}
        except Exception as e:  # noqa: BLE001
            fail[t] = str(e)
        time.sleep(0.25)
        if n % 50 == 0:
            print(n, t, len(res), len(fail), flush=True)
    (out / "us-8k-202.json").write_text(json.dumps({"tickers": res, "failures": fail}))
    print("done", len(res), len(fail), sum(len(v["rows"]) for v in res.values()))


if __name__ == "__main__":
    main()
