"""Fetch an immutable, verified subset; never write an existing sealed ledger."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "b71d8cb5ce21815980d28b606852f9294d43cc53"
MANIFEST_DIGEST = "f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2"
BASE = f"https://raw.githubusercontent.com/jaehojung1879-netizen/Investment/{COMMIT}/"


def fetch(path):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(BASE + path, timeout=90) as response:
                return response.read()
        except OSError:
            if attempt == 2:
                raise


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    root = args.destination
    if root.exists():
        raise ValueError("destination must be new; existing ledger writes forbidden")
    path = "ledger/historical/replay-v16/inputs.json"
    data = fetch(path)
    manifest = json.loads(data)
    raw = json.dumps({k: v for k, v in manifest.items() if k != "sha256"},
                     sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    if manifest["sha256"] != MANIFEST_DIGEST or hashlib.sha256(raw).hexdigest() != MANIFEST_DIGEST:
        raise ValueError("input manifest digest mismatch")
    target = root/path
    target.parent.mkdir(parents=True)
    target.write_bytes(data)
    refs = sorted({ref for name, refs in manifest["components"].items()
                   if name.startswith(("price/", "benchmark/", "fx/"))
                   or name in ("universe", "fundamentals", "corporate-events/source") for ref in refs})
    sources = json.loads((ROOT/"data/research/regional-alpha-model-v1/source-files.json").read_text())
    jobs = [(f"ledger/replay-inputs/objects/{ref}.json.gz", ref, None) for ref in refs]
    jobs += [(row["path"], None, row["gitBlob"]) for row in sources]

    def download(job):
        path, digest, blob = job
        content = fetch(path)
        if digest and hashlib.sha256(gzip.decompress(content)).hexdigest() != digest:
            raise ValueError("content digest mismatch: " + path)
        if blob and git_blob(content) != blob:
            raise ValueError("source blob mismatch: " + path)
        target = root/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    with ThreadPoolExecutor(max_workers=16) as pool:
        for i, _ in enumerate(pool.map(download, jobs)):
            if i % 100 == 0:
                print(f"verified {i + 1}/{len(jobs)}", flush=True)


if __name__ == "__main__":
    main()
