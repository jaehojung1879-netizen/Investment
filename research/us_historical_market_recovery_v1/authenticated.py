"""Bounded existing-account collection in the read-only Probes runner.

Raw responses are CMS-encrypted to the owner's workspace certificate before
leaving the runner. No API credential or plaintext vendor payload is published.
Default probes and all workflows remain unchanged.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib import error, parse, request

HERE = Path(__file__).resolve().parent
AS_OF = "2026-11-13"


def acquire(url, key, provider):
    headers = {"User-Agent": "InvestmentResearchData/1.0"}
    if provider == "FINNHUB":
        headers["X-Finnhub-Token"] = key
        actual = url
    else:
        actual = url + "&apikey=" + parse.quote(key)
    try:
        with request.urlopen(request.Request(actual, headers=headers), timeout=20) as response:
            status, raw = response.status, response.read(8 * 1024 * 1024 + 1)
    except error.HTTPError as exc:
        status, raw = exc.code, exc.read(8192)
    except (error.URLError, TimeoutError, OSError) as exc:
        return {"status": "TRANSPORT_ERROR", "error": type(exc).__name__, "url": url}
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("RESPONSE_BYTE_LIMIT")
    # Response bodies must not echo credentials into even the encrypted dataset.
    raw = raw.replace(key.encode(), b"REDACTED_CREDENTIAL")
    return {"status": status, "url": url, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "body_b64": base64.b64encode(raw).decode(), "observed_at": datetime.now(timezone.utc).isoformat()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-recovery", action="store_true")
    parser.add_argument("--supplement", action="store_true", help="Only action histories and verified-rename quote supplements")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    requests = json.loads((HERE / "inputs/requests.json").read_bytes())
    if len(requests) != 212 or len({r["audit_identifier"] for r in requests}) != 212:
        raise ValueError("INVALID_COHORT")
    responses, summary = [], []

    def record(provider, endpoint, ticker, start, end, control=False):
        if provider == "FINNHUB":
            query = {"symbol": ticker}
            if endpoint in {"dividend", "split"}:
                query.update({"from": start, "to": end})
            elif endpoint == "candle":
                query.update(resolution="D", **{"from": int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp()),
                                               "to": int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp())})
            url = "https://finnhub.io/api/v1/stock/" + endpoint + "?" + parse.urlencode(query)
        else:
            url = "https://financialmodelingprep.com/stable/" + endpoint + "?" + parse.urlencode(
                {"symbol": ticker, "from": start, "to": end})
        key = os.environ.get("FINNHUB_API_KEY" if provider == "FINNHUB" else "FMP_API_KEY", "")
        if not key:
            result = {"status": "NO_KEY", "url": url}
        else:
            result = acquire(url, key, provider)
        result.update(provider=provider, endpoint=endpoint, ticker=ticker, requested_start=start,
                      requested_end=end, control=control)
        responses.append(result)
        public = {k: v for k, v in result.items() if k not in {"body_b64"}}
        if result.get("status") == 200:
            try:
                body = json.loads(base64.b64decode(result["body_b64"]))
                public["rows"] = len(body) if isinstance(body, list) else int(bool(body))
            except (ValueError, KeyError):
                public["schema_error"] = True
        summary.append(public)
        print(json.dumps({k: public[k] for k in ("provider", "endpoint", "ticker", "status")}), flush=True)
        time.sleep(1.25)
        return result.get("status")

    # A missing entitlement is checked separately for every endpoint, not inferred
    # from the working fundamentals key or from a rejected candle call.
    for endpoint in (() if args.supplement else ("candle", "dividend", "split", "profile2")):
        status = record("FINNHUB", endpoint, "AAPL", "2013-01-01", AS_OF, True)
        if status != 200:
            for r in requests:
                summary.append({"provider": "FINNHUB", "endpoint": endpoint, "ticker": r["audit_identifier"],
                                "status": "NOT_REQUESTED_CONTROL_REFUSED", "control_status": status})
            continue
        for r in requests:
            status = record("FINNHUB", endpoint, r["audit_identifier"],
                            r["requested_window_start_252_session_warmup"], min(AS_OF, r["requested_window_end_252_session_followup"]))
            if status in {401, 403, 429, "NO_KEY", "TRANSPORT_ERROR"}:
                break

    if args.supplement:
        for ticker in ("COR", "BALL", "LUMN", "META"):
            record("FMP", "historical-price-eod/full", ticker, "2011-12-29", AS_OF)
        for endpoint in ("dividends", "splits"):
            status = record("FMP", endpoint, "AAPL", "2011-12-29", AS_OF, True)
            if status != 200:
                continue
            for ticker in ("ATVI", "MRO", "TWTR", "VIAC", "WBA", "COR", "BALL", "LUMN", "META"):
                status = record("FMP", endpoint, ticker, "2011-12-29", AS_OF)
                if status in {401, 429, "NO_KEY", "TRANSPORT_ERROR"}:
                    break
    else:
        status = record("FMP", "historical-price-eod/full", "AAPL", "2013-01-01", AS_OF, True)
        if status == 200:
            for r in requests:
                status = record("FMP", "historical-price-eod/full", r["audit_identifier"],
                                r["requested_window_start_252_session_warmup"], min(AS_OF, r["requested_window_end_252_session_followup"]))
                # 402 is a symbol-specific scope refusal and is retained per security.
                if status in {401, 429, "NO_KEY", "TRANSPORT_ERROR"} or isinstance(status, int) and status >= 500:
                    break
    plaintext = gzip.compress(json.dumps(responses, sort_keys=True, separators=(",", ":")).encode(), mtime=0)
    with tempfile.TemporaryDirectory() as work:
        src, dest = Path(work) / "responses.gz", Path(work) / "responses.cms"
        src.write_bytes(plaintext)
        subprocess.run(["openssl", "cms", "-encrypt", "-binary", "-aes-256-gcm", "-in", str(src),
                        "-outform", "DER", "-out", str(dest), str(HERE / "inputs/transfer-cert.pem")], check=True,
                       capture_output=True)
        encrypted = dest.read_bytes()
    out = {"schema": "PRIVATE_MARKET_RECOVERY_TRANSFER_V1", "requests": summary,
           "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(), "cms_sha256": hashlib.sha256(encrypted).hexdigest(),
           "cms_base64": base64.b64encode(encrypted).decode()}
    args.output.write_text(json.dumps(out, sort_keys=True))
    # The fallback transfer is ciphertext only; it is useful when an artifact
    # download host is unavailable. The private decryption key never leaves the
    # user's workspace or enters this repository, workflow, artifact, or log.
    print("RECOVERY_CMS_BEGIN")
    print(out["cms_base64"])
    print("RECOVERY_CMS_END")
    print("Encrypted responses:", len(responses), "ciphertext bytes:", len(encrypted))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
