"""Read SEC original cover-page class counts; never EPS average shares."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import threading
import time

from lxml import etree
import requests


def extract(raw):
    root = etree.fromstring(raw, etree.XMLParser(recover=True, huge_tree=True))
    contexts = {}
    for node in root.iter():
        if not isinstance(node.tag, str) or node.tag.rsplit("}", 1)[-1].lower() != "context":
            continue
        days, dims = [], []
        for part in node.iter():
            tag = part.tag.rsplit("}", 1)[-1]
            if tag == "instant":
                days.append(part.text)
            elif tag in ("explicitMember", "typedMember"):
                dims.append({"axis": part.get("dimension"), "member": "".join(part.itertext())})
        contexts[node.get("id")] = {"end": days[0] if len(days) == 1 else None, "dims": dims}
    out = []
    for node in root.iter():
        name = node.get("name") or ""
        if not ("SharesOutstanding" in name and "WeightedAverage" not in name):
            continue
        context = contexts.get(node.get("contextRef"), {})
        if not context.get("end"):
            continue
        value = "".join(node.itertext()).replace(",", "").replace("\xa0", "").strip()
        try:
            value = float(value) * 10 ** int(node.get("scale", "0"))
        except ValueError:
            continue
        if node.get("sign") == "-":
            value = -value
        out.append({"tag": name, "value": value, **context})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--since", default="2022-10-01")
    args = ap.parse_args()
    dest = args.private / "sec-filings"
    dest.mkdir(exist_ok=True)
    targets = {int(r["cik"]) for r in json.loads((args.private / "no-standard-shares.json").read_text())}
    targets -= {1391407}  # Identified conflicting issuer, not an admissible mapping.
    targets.add(1652044)
    throttle, last = threading.Lock(), [0.0]

    def get(url, path):
        if path.exists():
            return gzip.decompress(path.read_bytes()), 200
        with throttle:
            time.sleep(max(0, last[0] + 0.30 - time.monotonic()))
            last[0] = time.monotonic()
        response = requests.get(url, timeout=60, headers={
            "User-Agent": "InvestmentResearchData/1.0 research@investment.example"})
        if response.status_code == 200:
            path.write_bytes(gzip.compress(response.content, mtime=0))
        return response.content, response.status_code

    def collect(cik):
        url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
        raw, status = get(url, dest / f"{cik}-submissions.json.gz")
        if status != 200:
            return [{"cik": cik, "url": url, "status": status}]
        submissions = json.loads(raw)
        panels = [submissions["filings"]["recent"]]
        for old in submissions["filings"]["files"]:
            if old["filingTo"] >= args.since:
                raw, status = get("https://data.sec.gov/submissions/" + old["name"], dest / (old["name"] + ".gz"))
                if status == 200:
                    panels.append(json.loads(raw))
        records = []
        for panel in panels:
            for i, form in enumerate(panel["form"]):
                filed = panel["filingDate"][i]
                if form not in ("10-K", "10-Q", "20-F", "40-F") or not args.since <= filed < "2026-09-11":
                    continue
                accn = panel["accessionNumber"][i]
                primary = panel["primaryDocument"][i]
                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{primary}"
                raw, status = get(url, dest / (accn + ".htm.gz"))
                record = {"cik": cik, "filed": filed, "accn": accn, "url": url,
                          "status": status, "bytes": len(raw), "form": form}
                if status == 200:
                    record.update(sha256=hashlib.sha256(raw).hexdigest(), facts=extract(raw))
                records.append(record)
        print(f"SEC class covers CIK {cik}: {len(records)} filings", flush=True)
        (dest / f"{cik}-facts.json").write_text(json.dumps(records, indent=2) + "\n")
        return records

    records = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(collect, cik) for cik in sorted(targets)]):
            records.extend(future.result())
    (args.private / "sec-class-filings.json").write_text(json.dumps(records, indent=2) + "\n")
    print({"companies": len(targets), "filings": len(records),
           "ok": sum(r["status"] == 200 for r in records)}, flush=True)


if __name__ == "__main__":
    main()
