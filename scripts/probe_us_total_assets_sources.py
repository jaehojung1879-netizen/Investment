"""Bounded, owner-approved diagnostic: where can US quarterly TOTAL ASSETS come from, with provenance? NOT RUN IN THE AUTHORING ENVIRONMENT.

    python scripts/derive_us_total_assets_sample.py --from-git origin/signal-history   # rewrites the fixed sample (offline, no vendor)
    python scripts/probe_us_total_assets_sources.py --sample SAMPLE --sources sec,finnhub,massive,fmp --max-calls 0 --output plan.json
    SEC_CONTACT=... FINNHUB_API_KEY=... python scripts/probe_us_total_assets_sources.py --sources finnhub --max-calls 20 --output out.json

    --max-calls 0   PLAN ONLY: prints and records the exact requests it WOULD make. Needs no key, no contact, and calls nothing.

In Actions it runs only through `fundamentals.yml` -> Run workflow -> region=total-assets-source-probe (job `us-total-assets-source-probe`:
main-only for anything live, `contents: read`, each vendor key present in exactly one step). See docs/us-total-assets-source-rescue-ko.md.

What it asks, and why these questions:

  A. SEC, three request categories, conservative pacing, ONE identifying User-Agent the owner supplies (`SEC_CONTACT`; never invented here),
     no retries, no proxies, and each host stops being asked after two consecutive block pages:
       data.sec.gov companyconcept us-gaap/Assets  - one document per CIK, every fact with its own accession and filing date
       data.sec.gov companyfacts                   - the same facts as one document per company (two companies only)
       www.sec.gov  a small public resource        - reachability of the other host family, without any bulk archive
  B. Finnhub standardized `/stock/financials?statement=bs`, Massive `/stocks/financials/v1/balance-sheets`, FMP `/stable/balance-sheet-statement`:
     the first request of each is also the entitlement question. A 401/402/403 or a rate-limit stops that vendor: the question is "what does this
     key entitle us to", and hammering a refusal answers a different one.
  C. For the fixed sample (docs/us-readiness/us-total-assets-source-sample-v1.json) every source's observations are held against the data
     contract in pipeline/us_total_assets_source.py: identity by accession, filing date of that accession, original versus correction.

It reads only the responses, writes nothing into any store, keeps no raw vendor body, and never prints or records a credential. The report names
the request (host, path, non-secret parameters), the status, a category, size and timestamp - not the key and not the vendor's payload.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import sec_access  # noqa: E402
from pipeline import us_total_assets_source as TA  # noqa: E402

SAMPLE = ROOT / "docs/us-readiness/us-total-assets-source-sample-v1.json"
HARD_CEILING = 20
SEC_SPACING_SECONDS = 0.5            # 2 requests/second, a fifth of SEC's published 10/second maximum
VENDOR_SPACING = {"finnhub": 1.1, "massive": 1.0, "fmp": 0.5}
SEC_BLOCK_STOP_AFTER = 2             # consecutive block pages from one host before that host is no longer asked
SEC_CONCEPT_CIKS = 8
SEC_FACTS_CIKS = 2
SEC_FACTS_BYTE_CAP = 30_000_000
SEC_SMALL_BYTE_CAP = 5_000_000
VENDOR_BYTE_CAP = 8_000_000
TIMEOUT = 40
SOURCES = ("sec", "finnhub", "massive", "fmp")

KEY_ENV = {"finnhub": "FINNHUB_API_KEY", "massive": "MASSIVE_API_KEY", "fmp": "FMP_API_KEY"}
SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/us-gaap/Assets.json"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
FINNHUB_URL = "https://finnhub.io/api/v1/stock/financials"
MASSIVE_URL = "https://api.massive.com/stocks/financials/v1/balance-sheets"
FMP_URL = "https://financialmodelingprep.com/stable/balance-sheet-statement"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_sample(path: Path = SAMPLE) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def probe_tickers(sample: dict) -> list[dict]:
    """The ordered tickers (with CIK) the vendor and SEC requests are built from: fixed by the sample, never chosen at run time."""
    return list(sample.get("probeTickers") or [])


# ---- the plan: pure, keyless, deterministic ----------------------------------------------------------------------------------------------
def plan_requests(sample: dict, sources: list[str], max_calls: int) -> dict:
    cap = max(0, min(int(max_calls), HARD_CEILING))
    tickers = probe_tickers(sample)
    plan: dict[str, list[dict]] = {}
    if "sec" in sources:
        sec = [{"kind": "SEC_WWW_SMALL_RESOURCE", "host": "www.sec.gov", "url": SEC_TICKER_URL, "params": {}, "byteCap": SEC_SMALL_BYTE_CAP}]
        sec += [{"kind": "SEC_COMPANYCONCEPT_ASSETS", "host": "data.sec.gov", "url": SEC_CONCEPT_URL.format(cik10=str(t["cik"]).zfill(10)),
                 "params": {}, "cik": str(t["cik"]), "ticker": t["ticker"], "byteCap": SEC_SMALL_BYTE_CAP} for t in tickers[:SEC_CONCEPT_CIKS]]
        sec += [{"kind": "SEC_COMPANYFACTS", "host": "data.sec.gov", "url": SEC_FACTS_URL.format(cik10=str(t["cik"]).zfill(10)), "params": {},
                 "cik": str(t["cik"]), "ticker": t["ticker"], "byteCap": SEC_FACTS_BYTE_CAP} for t in tickers[:SEC_FACTS_CIKS]]
        plan["sec"] = sec[:cap]
    if "finnhub" in sources:
        plan["finnhub"] = [{"kind": "FINNHUB_STANDARDIZED_BS_QUARTERLY", "host": "finnhub.io", "url": FINNHUB_URL,
                            "params": {"symbol": t["ticker"], "statement": "bs", "freq": "quarterly"}, "cik": str(t["cik"]), "ticker": t["ticker"],
                            "byteCap": VENDOR_BYTE_CAP} for t in tickers][:cap]
    if "massive" in sources:
        plan["massive"] = [{"kind": "MASSIVE_V1_BALANCE_SHEETS", "host": "api.massive.com", "url": MASSIVE_URL,
                            "params": {"cik": str(t["cik"]), "timeframe": "quarterly", "limit": "100", "sort": "period_end.desc"},
                            "cik": str(t["cik"]), "ticker": t["ticker"], "byteCap": VENDOR_BYTE_CAP} for t in tickers][:cap]
    if "fmp" in sources:
        # Request 0 is the baseline the plan is known to serve (5 quarters); request 1 asks the SAME ticker for the deep window, so a refusal there is the
        # depth answer rather than an entitlement stop; the rest ask for whichever depth that answered.
        rows = []
        for i, t in enumerate(tickers):
            if i == 0:
                rows.append(("5", t))
            rows.append(("120" if i == 0 else "5", t))
        plan["fmp"] = [{"kind": "FMP_STABLE_BALANCE_SHEET", "host": "financialmodelingprep.com", "url": FMP_URL,
                        "params": {"symbol": t["ticker"], "period": "quarter", "limit": limit}, "cik": str(t["cik"]),
                        "ticker": t["ticker"], "byteCap": VENDOR_BYTE_CAP} for limit, t in rows][:cap]
    return plan


# ---- transport ---------------------------------------------------------------------------------------------------------------------------
def http_get(request: dict, headers: dict) -> dict:
    """One GET. Never raises; the failure kind is data. The URL (which may carry a query key) is not returned."""
    url = request["url"]
    params = dict(request.get("params") or {})
    if request.get("queryKey"):
        params[request["queryKey"][0]] = request["queryKey"][1]
    if params:
        url += "?" + urllib.parse.urlencode(params)
    started = time.monotonic()
    req = urllib.request.Request(url, headers=headers)
    cap = int(request.get("byteCap") or VENDOR_BYTE_CAP)
    status, body, truncated, error_kind, text = None, b"", False, None, ""
    response_headers: dict = {}
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:  # noqa: S310 - fixed https hosts above
            status = response.status
            body = response.read(cap + 1)
            response_headers = dict(response.headers.items())
    except urllib.error.HTTPError as error:
        status = error.code
        try:
            body = error.read(cap + 1)
            response_headers = dict(error.headers.items()) if error.headers else {}
        except Exception:  # noqa: BLE001 - a body we cannot read is still a status
            body = b""
    except urllib.error.URLError as error:
        reason = str(getattr(error, "reason", error))
        error_kind = "proxy" if any(w in reason.lower() for w in ("tunnel", "proxy")) else "network"
        text = reason[:160]
    except (socket.timeout, TimeoutError):
        error_kind, text = "network", "timeout"
    except Exception as error:  # noqa: BLE001
        error_kind, text = "network", type(error).__name__
    if len(body) > cap:
        body, truncated = body[:cap], True
    body = sec_access.decode_body(body, response_headers.get("Content-Encoding") or response_headers.get("content-encoding"))
    return {"status": status, "body": body, "truncated": truncated, "errorKind": error_kind, "errorText": text,
            "elapsedMs": int((time.monotonic() - started) * 1000), "contentType": response_headers.get("Content-Type") or response_headers.get("content-type")}


def scrub(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret and len(secret) >= 6:
            text = text.replace(secret, "<redacted>")
    return text


def parse_json(body: bytes):
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return None


# ---- readers per request kind ------------------------------------------------------------------------------------------------------------
def read_for(request: dict, payload):
    kind = request["kind"]
    if kind == "SEC_COMPANYCONCEPT_ASSETS":
        return TA.read_sec_company_concept(payload)
    if kind == "SEC_COMPANYFACTS":
        return TA.read_sec_company_facts(payload)
    if kind == "SEC_WWW_SMALL_RESOURCE":
        return TA.read_sec_ticker_file(payload)
    if kind == "FINNHUB_STANDARDIZED_BS_QUARTERLY":
        return TA.read_finnhub_standardized(payload, request.get("ticker"))
    if kind == "MASSIVE_V1_BALANCE_SHEETS":
        return TA.read_massive_balance_sheets(payload)
    if kind == "FMP_STABLE_BALANCE_SHEET":
        return TA.read_fmp_balance_sheet(payload, request.get("ticker"))
    raise ValueError(kind)


def headers_for(source: str, key: str | None, user_agent: str | None) -> dict:
    if source == "sec":
        return {"User-Agent": user_agent or "", "Accept-Encoding": "gzip, deflate", "Accept": "application/json"}
    base = {"User-Agent": "InvestmentResearchDiagnostic/1.0", "Accept": "application/json"}
    if source == "finnhub" and key:
        base["X-Finnhub-Token"] = key
    if source == "massive" and key:
        base["Authorization"] = f"Bearer {key}"
    return base


def execute_source(source: str, requests: list[dict], *, transport, sleep, key: str | None, user_agent: str | None, secrets: list[str]) -> dict:
    """Walk one source's requests under its stop rules. Returns the request log and every observation parsed (no raw body kept)."""
    log: list[dict] = []
    observations: list[dict] = []
    reader_facts: list[dict] = []
    consecutive_blocks: dict[str, int] = {}
    stopped: str | None = None
    for index, request in enumerate(requests):
        host = request["host"]
        record = {"index": index, "kind": request["kind"], "host": host, "path": urllib.parse.urlparse(request["url"]).path,
                  "params": request.get("params") or {}, "ticker": request.get("ticker"), "cik": request.get("cik")}
        if stopped:
            record.update({"category": TA.SKIPPED_AFTER_BLOCK, "stopReason": stopped})
            log.append(record)
            continue
        if source == "sec" and consecutive_blocks.get(host, 0) >= SEC_BLOCK_STOP_AFTER:
            record.update({"category": TA.SKIPPED_AFTER_BLOCK, "stopReason": f"{host} answered {SEC_BLOCK_STOP_AFTER} block pages in a row; not asked again"})
            log.append(record)
            continue
        if index:
            sleep(SEC_SPACING_SECONDS if source == "sec" else VENDOR_SPACING[source])
        call = dict(request)
        if source == "fmp" and key:
            call["queryKey"] = ("apikey", key)
        started = now()
        result = transport(call, headers_for(source, key, user_agent))
        payload = parse_json(result["body"]) if result["status"] == 200 and not result["truncated"] else None
        read = read_for(request, payload) if payload is not None else {"valid": False, "reason": "NOT_JSON_OR_TRUNCATED" if result["status"] == 200 else None, "observations": []}
        classified = TA.classify_exchange("sec" if source == "sec" else "vendor", result["status"], result["body"], result["errorKind"],
                                          bool(read.get("valid")) if result["status"] == 200 else None)
        evidence = classified["evidence"]
        if result["errorText"]:
            evidence["errorText"] = scrub(result["errorText"], secrets)
        for key_name in ("sentence", "entitlementSentence", "vendorSentence"):
            if key_name in evidence:
                evidence[key_name] = scrub(evidence[key_name], secrets)
        record.update({"category": classified["category"], "evidence": evidence, "startedAt": started, "elapsedMs": result["elapsedMs"],
                       "contentType": result["contentType"], "truncated": result["truncated"], "payloadValid": bool(read.get("valid")) if result["status"] == 200 else None,
                       "payloadReason": read.get("reason"), "observationsParsed": len(read.get("observations") or [])})
        for extra in ("fieldsSeen", "nextUrlPresent", "malformedFacts", "rows", "vendorMessage"):
            if read.get(extra) not in (None, [], False):
                record[extra] = read[extra]
        log.append(record)
        if classified["category"] == TA.HTTP_200_VALID:
            observations.extend(read.get("observations") or [])
            reader_facts.append({"kind": request["kind"], "ticker": request.get("ticker")})
            consecutive_blocks[host] = 0
        elif classified["category"] == TA.HTTP_403_SEC_BLOCK:
            consecutive_blocks[host] = consecutive_blocks.get(host, 0) + 1
        elif source == "fmp" and index == 1 and request["params"].get("limit") == "120":
            depth_ok = classified["category"] == TA.HTTP_200_VALID
            record["depthQuestion"] = "DEEP_WINDOW_SERVED" if depth_ok else "DEEP_WINDOW_REFUSED_PLAN_DEPTH_CAP"
            for later in requests[2:]:
                later["params"] = dict(later.get("params") or {}, limit="120" if depth_ok else "5")
        elif source != "sec" and classified["category"] in (TA.HTTP_401, TA.HTTP_402_PLAN, TA.HTTP_403_OTHER, TA.HTTP_429):
            stopped = f"{classified['category']} on request {index + 1}: the question became the entitlement or the rate limit, so the vendor is not asked again"
    return {"requests": log, "observations": observations, "stopped": stopped}


def source_verdict(source: str, log: list[dict], checks: list[dict]) -> dict:
    cats = [r.get("category") for r in log]
    if not log:
        return {"verdict": TA.NOT_TESTED, "reason": "NO_REQUEST_MADE"}
    ok = [r for r in log if r.get("category") == TA.HTTP_200_VALID]
    if source == "sec":
        data_ok = [r for r in ok if r["host"] == "data.sec.gov"]
        if data_ok:
            summary = TA.summarize_source(checks)
            return {"verdict": "SEC_DATA_HOST_REACHABLE", "pitProvenFilings": summary["pitProven"], "wwwReachable": any(r["host"] == "www.sec.gov" for r in ok)}
        if any(c == TA.HTTP_403_SEC_BLOCK for c in cats):
            return {"verdict": "SEC_BLOCK_PERSISTS_ON_ACTIONS_RUNNER",
                    "hostsBlocked": sorted({r["host"] for r in log if r.get("category") == TA.HTTP_403_SEC_BLOCK})}
        return {"verdict": "SEC_NOT_REACHED_NO_BLOCK_PAGE", "categories": sorted({str(c) for c in cats})}
    if TA.HTTP_401 in cats:
        return {"verdict": "KEY_REJECTED", "reason": "the vendor does not accept the credential on this endpoint"}
    if TA.HTTP_402_PLAN in cats or TA.HTTP_403_OTHER in cats:
        sentence = next((r["evidence"].get("entitlementSentence") or r["evidence"].get("vendorSentence") for r in log if r.get("evidence")), None)
        return {"verdict": "NOT_ENTITLED_ON_THIS_KEY", "vendorSentence": sentence}
    if TA.HTTP_429 in cats and not ok:
        return {"verdict": "RATE_LIMITED_BEFORE_MEASURED"}
    if not ok:
        return {"verdict": "NO_VALID_RESPONSE", "categories": sorted({str(c) for c in cats})}
    summary = TA.summarize_source(checks)
    fields = sorted({f for r in ok for f in (r.get("fieldsSeen") or [])})
    if not any(c.get("totalAssetsStated") for c in checks):
        return {"verdict": "ACCESSIBLE_BUT_NO_TOTAL_ASSETS_FOR_THE_SAMPLE", "fieldsSeen": fields[:40], **{"matched": summary["matched"]}}
    if summary["pitProven"] == 0:
        return {"verdict": "ACCESSIBLE_VALUES_BUT_NO_PIT_PROOF", "fieldsSeen": fields[:40], "matched": summary["matched"], "exactAccession": summary["exactAccession"]}
    return {"verdict": "ACCESSIBLE_WITH_PIT_PROOF_FOR_SOME_FILINGS", "pitProvenFilings": summary["pitProven"], "matched": summary["matched"]}


def leak_check(text: str, secrets: list[str]) -> list[str]:
    return [f"a credential of length {len(s)} appears in the report" for s in secrets if s and len(s) >= 6 and s in text]


def sec_block_status(sources: dict) -> dict:
    """Whether the earlier SEC block is shown to have disappeared. Only a live HTTP 200 with a valid payload from data.sec.gov says so."""
    sec = sources.get("sec")
    if not sec:
        return {"claim": False, "basis": "SEC was not asked in this report; nothing here bears on the earlier block"}
    if sec.get("verdict") == "SEC_DATA_HOST_REACHABLE":
        return {"claim": True, "basis": "a live HTTP 200 with a valid payload from data.sec.gov in THIS run"}
    return {"claim": False, "basis": "no live HTTP 200 from data.sec.gov in this run; the earlier block is not shown to have disappeared"}


def run(sample: dict, sources: list[str], max_calls: int, *, contact: str | None, env: dict | None = None, transport=None, sleep=time.sleep) -> dict:
    environ = os.environ if env is None else env
    transport = transport or http_get
    plan = plan_requests(sample, sources, max_calls if max_calls > 0 else HARD_CEILING)   # plan-only describes the full plan, not an empty one
    keys = {s: (environ.get(KEY_ENV[s]) or None) for s in KEY_ENV}
    secrets = [v for v in keys.values() if v]
    report: dict = {"contract": TA.CONTRACT, "mode": "PLAN_ONLY" if max_calls <= 0 else "LIVE", "sources": {}, "hardCeilingPerSource": HARD_CEILING,
                    "sampleDigest": sample.get("digest"), "sampleFilings": len(sample.get("filings") or []), "secUserAgentContactSupplied": bool(contact)}
    if max_calls <= 0:
        for source in sources:
            report["sources"][source] = {"verdict": "PENDING_OWNER_DISPATCH", "plannedRequests": [
                {k: v for k, v in r.items() if k in ("kind", "host", "url", "params", "ticker", "cik")} for r in plan.get(source, [])],
                "keyRequired": source in KEY_ENV, "keyPresentInThisProcess": False}
        return report
    observed_at = now()
    report["observedAt"] = observed_at
    report["checks"] = {}
    for source in sources:
        requests = plan.get(source, [])
        if source == "sec":
            problem = TA.sec_contact_problem(contact)
            if problem:
                report["sources"][source] = {"verdict": "NOT_RUN", "reason": problem, "requests": []}
                continue
            outcome = execute_source(source, requests, transport=transport, sleep=sleep, key=None, user_agent=TA.sec_user_agent(contact or ""), secrets=secrets)
        else:
            if not keys[source]:
                report["sources"][source] = {"verdict": "NOT_RUN", "reason": f"{KEY_ENV[source]} IS ABSENT IN THIS PROCESS", "requests": []}
                continue
            outcome = execute_source(source, requests, transport=transport, sleep=sleep, key=keys[source], user_agent=None, secrets=secrets)
        checks = [TA.check_filing(f, outcome["observations"], observed_at) for f in sample.get("filings") or []] if outcome["observations"] else []
        entry = {"requests": outcome["requests"], "stopped": outcome["stopped"], "summary": TA.summarize_source(checks) if checks else None}
        entry.update(source_verdict(source, outcome["requests"], checks))
        report["sources"][source] = entry
        report["checks"][source] = checks
    report["secBlockCleared"] = sec_block_status(report["sources"])
    problems = leak_check(json.dumps(report, ensure_ascii=False), secrets)
    if problems:
        raise SystemExit("LEAK_GUARD: " + "; ".join(problems))
    return report


def merge_parts(parts: list[dict]) -> dict:
    """Combine per-source reports (each secret-bearing step wrote its own) into one. Pure; reads no key."""
    merged: dict = {"contract": TA.CONTRACT, "mode": "LIVE", "sources": {}, "checks": {}}
    for part in parts:
        merged["sources"].update(part.get("sources") or {})
        merged["checks"].update(part.get("checks") or {})
        for key in ("observedAt", "sampleDigest", "sampleFilings", "secUserAgentContactSupplied", "hardCeilingPerSource"):
            if key in part:
                merged.setdefault(key, part[key])
    merged["secBlockCleared"] = sec_block_status(merged["sources"])    # recomputed from the merged sources, never taken from whichever part came first
    if any(p.get("mode") == "PLAN_ONLY" for p in parts) and not any(p.get("mode") == "LIVE" for p in parts):
        merged["mode"] = "PLAN_ONLY"
    return merged


def digest_of(sample: dict) -> str:
    body = {k: v for k, v in sample.items() if k != "digest"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=Path, default=SAMPLE)
    parser.add_argument("--sources", default=",".join(SOURCES))
    parser.add_argument("--max-calls", type=int, required=False, default=0)
    parser.add_argument("--sec-contact", default=os.environ.get("SEC_CONTACT", ""))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--merge", nargs="*", type=Path, help="combine per-source reports; makes no request")
    args = parser.parse_args(argv)
    if args.merge:
        report = merge_parts([json.loads(p.read_text(encoding="utf-8")) for p in args.merge])
    else:
        sources = [s for s in args.sources.split(",") if s]
        unknown = [s for s in sources if s not in SOURCES]
        if unknown:
            raise SystemExit(f"unknown source(s): {unknown}")
        if not 0 <= args.max_calls <= HARD_CEILING:
            raise SystemExit(f"--max-calls must be 0..{HARD_CEILING}")
        sample = load_sample(args.sample)
        if sample.get("digest") != digest_of(sample):
            raise SystemExit("SAMPLE_DIGEST_MISMATCH: the fixed sample was edited after it was sealed")
        report = run(sample, sources, args.max_calls, contact=args.sec_contact or None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name, entry in sorted(report["sources"].items()):
        print(f"{name:8s} {entry.get('verdict')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
