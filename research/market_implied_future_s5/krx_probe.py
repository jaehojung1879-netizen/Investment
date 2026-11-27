"""One unauthenticated probe of the documented KRX index endpoint, source only."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from .acquire import NoRedirect
from .snapshot import encode

URL = "https://data-dbg.krx.co.kr/svc/apis/idx/kospi_dd_trd?basDd=20261125"


def probe():
    opener = build_opener(NoRedirect())
    try:
        response = opener.open(Request(URL), timeout=15)
    except HTTPError as error:
        response = error
    with response:
        clock = datetime.now(timezone.utc)
        metadata = {"httpStatus": response.status, "httpDate": response.headers.get("Date"),
                    "contentType": response.headers.get("Content-Type")}
        raw = response.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024:
        raise ValueError("KRX_RESPONSE_TOO_LARGE")
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = {}
    auth = isinstance(payload, dict) and str(payload.get("respCode")) == "401"
    return {"status": "SOURCE_BLOCKED" if auth or metadata["httpStatus"] in {401, 403, 429} else "RESPONSE_REQUIRES_REVIEW",
            "reason": "KRX_API_KEY_REQUIRED" if auth else None, "url": URL, "retrievedAtUtc": clock,
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), **metadata,
            "officialVkospiDailyRowsAdmitted": 0, "officialKrxDerivativeRowsAdmitted": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.report.write_text(encode(probe()), encoding="utf-8")
