"""Decrypt an existing-account transfer locally; the key never enters GitHub."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from research.us_historical_market_recovery_v1.collect import private_root, canonical


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--name", choices=("authenticated", "supplement"), required=True)
    args = parser.parse_args(argv)
    private = private_root(args.private_root)
    payload = json.loads(args.input.read_bytes())
    ciphertext = base64.b64decode(payload["cms_base64"], validate=True)
    if hashlib.sha256(ciphertext).hexdigest() != payload["cms_sha256"]:
        raise ValueError("CIPHERTEXT_CHECKSUM_MISMATCH")
    with tempfile.TemporaryDirectory(dir=private) as temp:
        src, dest = Path(temp) / "responses.cms", Path(temp) / "responses.gz"
        src.write_bytes(ciphertext)
        subprocess.run(["openssl", "cms", "-decrypt", "-binary", "-inform", "DER", "-in", str(src),
                        "-inkey", str(args.private_key.resolve()), "-out", str(dest)], check=True, capture_output=True)
        raw = dest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != payload["plaintext_sha256"]:
        raise ValueError("PLAINTEXT_CHECKSUM_MISMATCH")
    rows = json.loads(gzip.decompress(raw))
    for row in rows:
        if row.get("body_b64") and hashlib.sha256(base64.b64decode(row["body_b64"], validate=True)).hexdigest() != row["sha256"]:
            raise ValueError("RESPONSE_CHECKSUM_MISMATCH")
    (private / (args.name + "-responses.json.gz")).write_bytes(raw)
    (private / (args.name + "-public-receipts.json")).write_bytes(canonical(payload["requests"]))
    print("Verified and decrypted private responses:", len(rows))


if __name__ == "__main__":
    main()
