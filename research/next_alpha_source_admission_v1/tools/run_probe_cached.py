"""Run #373 source_probe (fetched with git show, unmodified) with a raw-response cache and the D-filter fix.

Usage: python run_probe_cached.py RAW_DIR   (needs DART_API_KEY; 10 list + <=10 document calls)"""
import hashlib
import json
import os
import sys


def fix_detail_filter(params):
    """DART ignores pblntf_detail_ty when pblntf_ty is also sent (measured 2026-11-26); send the detail type alone."""
    if params.get("pblntf_detail_ty"):
        params = {k: v for k, v in params.items() if k != "pblntf_ty"}
    return params


def main(raw_dir):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import source_probe_373 as P
    calls, orig = [], P.request_bytes

    def cached(endpoint, params):
        params = fix_detail_filter(params)
        data = orig(endpoint, params)
        h = hashlib.sha256(data).hexdigest()
        with open(os.path.join(raw_dir, h + "." + endpoint.split(".")[1]), "wb") as f:
            f.write(data)
        calls.append({"endpoint": endpoint, "params": {k: v for k, v in params.items() if k != "crtfc_key"}, "sha256": h, "bytes": len(data)})
        return data

    P.request_bytes = cached
    rc = P.main(["--live", "--documents-per-detail", "5", "--output", os.path.join(raw_dir, "..", "probe-output.json")])
    with open(os.path.join(raw_dir, "..", "calls.json"), "w") as f:
        json.dump(calls, f, ensure_ascii=False, indent=1)
    print("rc", rc, "calls", len(calls))


if __name__ == "__main__":
    main(sys.argv[1])
