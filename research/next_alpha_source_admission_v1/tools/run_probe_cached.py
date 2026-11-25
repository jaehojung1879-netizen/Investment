import hashlib, json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import source_probe_373 as P
RAW = sys.argv[1]; calls = []
orig = P.request_bytes
def cached(endpoint, params):
    data = orig(endpoint, params)
    h = hashlib.sha256(data).hexdigest()
    open(os.path.join(RAW, h + "." + endpoint.split(".")[1]), "wb").write(data)
    calls.append({"endpoint": endpoint, "params": {k: v for k, v in params.items() if k != "crtfc_key"}, "sha256": h, "bytes": len(data)})
    return data
P.request_bytes = cached
rc = P.main(["--live", "--documents-per-detail", "5", "--output", os.path.join(RAW, "..", "probe-output.json")])
json.dump(calls, open(os.path.join(RAW, "..", "calls.json"), "w"), ensure_ascii=False, indent=1)
print("rc", rc, "calls", len(calls))
