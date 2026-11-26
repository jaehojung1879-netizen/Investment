"""Korean provisional-earnings disclosure dates: DART list.json rows whose report name is an (consolidated) 영업(잠정)실적 fair disclosure.

    python -m research.kr_us_earnings_expectations_v1.collect_kr_prelim --private <dir with data/raw/accounting> --out <dir>

Reads the documented OpenDART list.json endpoint (key from DART_API_KEY, never written) per corp_code over 2015-01-01..today, all pages.
Keeps every row (raw) so the selection rule can be audited; the selection is done later, not here.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "research audit"}


def get(params):
    params = dict(params, crtfc_key=os.environ["DART_API_KEY"])
    url = "https://opendart.fss.or.kr/api/list.json?" + urllib.parse.urlencode(params)
    for k in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(2 * (k + 1))
    raise err


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--end", default=time.strftime("%Y%m%d"))
    a = ap.parse_args(argv)
    corps = {}
    for p in sorted((Path(a.private) / "data" / "raw" / "accounting").glob("dart-*.jsonl.gz")):
        for line in gzip.open(p, "rt"):
            r = json.loads(line)
            corps[r["corpCode"]] = r["ticker"]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res, status, calls = {}, {}, 0
    for n, (cc, t) in enumerate(sorted(corps.items())):
        rows, page = [], 1
        # list.json limits a corp query window; walk year by year
        for y in range(2015, int(a.end[:4]) + 1):
            page = 1
            while True:
                d = get({"corp_code": cc, "bgn_de": f"{y}0101", "end_de": min(f"{y}1231", a.end), "pblntf_ty": "I",
                         "page_no": page, "page_count": 100})
                calls += 1
                st = d.get("status")
                if st == "013":
                    break
                if st != "000":
                    status[cc] = f"{st}:{d.get('message')}"
                    break
                rows += [x for x in d["list"] if "잠정" in x["report_nm"] and "실적" in x["report_nm"]]
                if page >= int(d.get("total_page", 1)):
                    break
                page += 1
                time.sleep(0.15)
            time.sleep(0.15)
        res[t] = {"corpCode": cc, "rows": rows}
        if n % 20 == 0:
            print(n, t, len(rows), calls, flush=True)
    (out / "kr-prelim-list.json").write_text(json.dumps({"tickers": res, "status": status, "calls": calls}, ensure_ascii=False))
    print("done", len(res), calls, sum(len(v["rows"]) for v in res.values()), status)


if __name__ == "__main__":
    main()
