"""Cache public SEC companyfacts with a receipt, outside the repository."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import threading
import time

import requests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--targets", default="cik-targets.json")
    ap.add_argument("--receipt-name", default="sec-companyfacts-receipts.json")
    args = ap.parse_args()
    target = args.private / "sec-companyfacts"
    target.mkdir(exist_ok=True)
    ciks = json.loads((args.private / args.targets).read_text())
    lock = threading.Lock()
    last = [0.0]

    def get(cik):
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
        dest = target / f"{cik}.json.gz"
        if dest.exists():
            raw = gzip.decompress(dest.read_bytes())
        elif (target / f"{cik}.json").exists():
            raw = (target / f"{cik}.json").read_bytes()
            dest.write_bytes(gzip.compress(raw, mtime=0))
        else:
            with lock:
                time.sleep(max(0, last[0] + 0.29 - time.monotonic()))
                last[0] = time.monotonic()
            response = requests.get(url, timeout=60, headers={
                "User-Agent": "InvestmentResearchData/1.0 research@investment.example",
                "Accept-Encoding": "gzip, deflate",
            })
            if response.status_code != 200:
                return {"cik": cik, "url": url, "status": response.status_code,
                        "bytes": len(response.content)}
            raw = response.content
            if int(json.loads(raw)["cik"]) != cik:
                raise ValueError("SEC_IDENTITY_MISMATCH")
            dest.write_bytes(gzip.compress(raw, mtime=0))
        return {"cik": cik, "url": url, "status": 200,
                "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                "object": str(dest.relative_to(args.private))}

    receipts = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(get, cik) for cik in ciks]
        for i, future in enumerate(as_completed(futures), 1):
            receipts.append(future.result())
            if i % 50 == 0:
                print(f"SEC companyfacts {i}/{len(ciks)}", flush=True)
    (args.private / args.receipt_name).write_text(
        json.dumps(sorted(receipts, key=lambda r: r["cik"]), indent=2) + "\n")
    print({"targets": len(ciks), "ok": sum(r["status"] == 200 for r in receipts)}, flush=True)


if __name__ == "__main__":
    main()
