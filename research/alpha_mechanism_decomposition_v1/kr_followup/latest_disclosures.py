"""Were the latest weekly decisions made on the periodic reports that were actually public on each decision date?

    python research/alpha_mechanism_decomposition_v1/kr_followup/latest_disclosures.py --latest <dir from latest_inputs.py> --cache <dir outside git>

For every name in the PIT top-120 on each preview signal date, OpenDART `list.json` (periodic reports, pblntf_ty=A, the endpoint
this repository already reads live) gives the latest quarterly/half/annual report received before the decision. A report becomes
visible the session AFTER its receipt date (Phase B rule). The research accounting store the decisions read is compared with it:
  MATCH               the store's latest visible filing is the same fiscal period as DART's latest visible report
  STORE_BEHIND        DART had a later periodic report visible on the decision date that the store did not carry
  STORE_AHEAD         the store carries a period DART lists as received later (would be look-ahead; must be zero)
  NO_DART_REPORT / NO_STORE_FILING   reported as such
Only the receipt list is read (no financial values). Every receipt of a period counts; a period visible only as an amendment ([기재정정]) is tallied apart.
The key is read from the environment and never written anywhere.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import pickle
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
URL = "https://opendart.fss.or.kr/api/list.json"
CODE_MONTH = {"11013": 3, "11012": 6, "11014": 9, "11011": 12}


def fetch(corp, cache: Path, bgn="20250101", end="20261113"):
    path = cache / f"{corp}.json"
    if path.exists():
        return json.loads(path.read_text())
    rows, page = [], 1
    while True:
        q = urllib.parse.urlencode({"crtfc_key": os.environ["DART_API_KEY"], "corp_code": corp, "bgn_de": bgn, "end_de": end,
                                    "pblntf_ty": "A", "page_no": page, "page_count": 100})
        d = json.loads(urllib.request.urlopen(URL + "?" + q, timeout=30).read())
        if d.get("status") == "013":
            break
        if d.get("status") != "000":
            raise RuntimeError("DART_STATUS_%s_%s" % (d.get("status"), d.get("message")))
        rows += [{k: r.get(k) for k in ("rcept_no", "rcept_dt", "report_nm", "corp_name", "stock_code")} for r in d["list"]]
        if page >= int(d["total_page"]):
            break
        page += 1
        time.sleep(0.2)
    path.write_text(json.dumps(rows, ensure_ascii=False))
    time.sleep(0.2)
    return rows


def period_of(name):
    m = re.search(r"\((\d{4})\.(\d{2})\)", name or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--latest", required=True)
    ap.add_argument("--cache", required=True)
    a = ap.parse_args(argv)
    cache = Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)
    mx = pickle.loads((Path(a.latest) / "latest-matrix.pkl").read_bytes())
    receipts = [json.loads(x) for x in (HERE / "preview-receipts.jsonl").read_text().splitlines() if x.strip()]
    rows = mx["matrix"].rows
    acc_dir = Path(a.latest).parent / "data/raw/accounting"
    store = {}
    for p in sorted(acc_dir.glob("dart-*.jsonl.gz")):
        for line in gzip.open(p, "rt"):
            r = json.loads(line)
            store.setdefault(r["ticker"], []).append(r)
    corp = {t: rs[-1]["corpCode"] for t, rs in store.items() if rs and rs[-1].get("corpCode")}
    out = {"label": "DECISION_DATE_DISCLOSURE_CHECK", "endpoint": "OpenDART list.json pblntf_ty=A", "decisions": {}}
    for rec in receipts:
        d = rec["signalDate"]
        members = sorted(rows[rows["date"].astype(str).str[:10] == d]["ticker"])
        held = {t for b in ("B1_S2_ORIGINAL", "B3_H01_INDUSTRIES_S2_SELECTION") for t in rec["books"][b]["weights"] if t.endswith(".KS")}
        tally, behind, ahead = {}, [], []
        for t in members:
            cc = corp.get(t)
            if cc is None:
                tally["NO_CORP_CODE_IN_STORE"] = tally.get("NO_CORP_CODE_IN_STORE", 0) + 1
                continue
            # every receipt of a period counts ([첨부추가] is DART's relabel of an original whose attachments were added;
            # [기재정정] is an amendment); a period first visible only through an amendment is recorded apart
            dart = fetch(cc, cache)
            vis = [r for r in dart if pd.Timestamp(r["rcept_dt"]) < pd.Timestamp(d)]          # visible the session after receipt
            dp = max((period_of(r["report_nm"]) for r in vis if period_of(r["report_nm"])), default=None)
            if dp is not None and all("기재정정" in (r["report_nm"] or "") for r in vis if period_of(r["report_nm"]) == dp):
                tally["DART_LATEST_VISIBLE_ONLY_AS_AMENDMENT"] = tally.get("DART_LATEST_VISIBLE_ONLY_AS_AMENDMENT", 0) + 1
            sv = [r for r in store.get(t, []) if r["availableFrom"] <= d]
            sp = max(((int(r["fiscalYear"]), CODE_MONTH[str(r["reportCode"])]) for r in sv), default=None)
            later = [r for r in dart if pd.Timestamp(r["rcept_dt"]) >= pd.Timestamp(d) and period_of(r["report_nm"]) and sp and period_of(r["report_nm"]) <= sp
                     and period_of(r["report_nm"]) > (dp or (0, 0))]
            if dp is None:
                state = "NO_DART_REPORT"
            elif sp is None:
                state = "NO_STORE_FILING"
            elif sp == dp:
                state = "MATCH"
            elif sp < dp:
                state = "STORE_BEHIND"
                behind.append({"ticker": t, "store": sp, "dart": dp, "heldInBook": t in held})
            else:
                state = "STORE_AHEAD" if later else "STORE_PERIOD_LATER_THAN_DART_LABEL"
                ahead.append({"ticker": t, "store": sp, "dart": dp, "heldInBook": t in held})
            tally[state] = tally.get(state, 0) + 1
        out["decisions"][d] = {"members": len(members), "states": tally, "storeBehind": behind, "storeAhead": ahead,
                               "heldNamesChecked": sorted(held)}
    (HERE / "latest-disclosure-check.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str) + "\n")
    print(json.dumps({d: v["states"] for d, v in out["decisions"].items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
