"""Download/verify the cited official documents into the private input store."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib import error, request

from research.us_historical_market_recovery_v1.collect import private_root, canonical


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    args = parser.parse_args(argv)
    dest = private_root(args.private_root) / "identity-sources"
    dest.mkdir(exist_ok=True)
    rows = json.loads((Path(__file__).parent / "inputs/official-sources.json").read_bytes())
    for row in rows:
        path = dest / row["file"]
        if not path.exists():
            req = request.Request(row["url"], headers={"User-Agent": "InvestmentDataResearch/1.0"})
            try:
                with request.urlopen(req, timeout=40) as response:
                    raw, status = response.read(8 * 1024 * 1024), response.status
            except error.HTTPError as exc:
                raw, status = exc.read(8 * 1024 * 1024), exc.code
            if status != row["status"]:
                raise ValueError("SOURCE_STATUS_CHANGED:" + row["id"])
            path.write_bytes(raw)
            time.sleep(.3)
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("SOURCE_VINTAGE_CHANGED_RETAIN_SEPARATELY:" + row["id"])
    (dest / "public-receipts.json").write_bytes(canonical([{k: v for k, v in r.items() if k != "file"} for r in rows]))
    print("Verified official source receipts:", len(rows))


if __name__ == "__main__":
    main()
