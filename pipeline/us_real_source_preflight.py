"""Bounded source-only diagnostic, never a full-universe collection or signal."""
from datetime import timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time

from . import us_daily_market_data as D
from . import us_daily_market_sources as S

VERSION = "us-real-source-preflight-v1"
MAX_PROVIDER_CALLS = 5
MAX_SECONDS = 180


def classify(exc, reply=None):
    message = str(exc)
    if re.search(r"CONNECT.*403", message, re.I | re.S):
        return "PROXY_CONNECT_403"
    if re.search(r"429|too many requests|rate.?limit", message, re.I):
        return "PROVIDER_RATE_LIMIT"
    if re.search(r"401|unauthorized|invalid crumb|authentication", message, re.I):
        return "PROVIDER_AUTHORIZATION"
    if re.search(r"403|forbidden", message, re.I):
        return "PROVIDER_OR_GATEWAY_FORBIDDEN_UNRESOLVED"
    code = getattr(exc, "code", "UNEXPECTED_EXCEPTION")
    if code == "MISSING_PRICE_OR_ACTION_COLUMNS" and reply is not None:
        if not {"Dividends", "Stock Splits"}.issubset(reply.frame.columns):
            return "MISSING_CORPORATE_ACTIONS"
    if code == "INVALID_OR_MISSING_VALUE" and reply is not None:
        if reply.frame[["Dividends", "Stock Splits"]].isna().any().any():
            return "MISSING_CORPORATE_ACTIONS"
    if code in ("EMPTY_OR_REFUSED_DOWNLOAD", "STALE_TRUNCATED_OR_FUTURE_DOWNLOAD"):
        return "INCOMPLETE_FRAME"
    if code == "PRICE_SOURCE_IDENTITY_OR_UNIT" and reply is not None:
        return "INVALID_CURRENCY_UNIT" if reply.metadata.get("currency") != "USD" else "IDENTITY_OR_SOURCE_CONTRACT_PROBLEM"
    if code.startswith(("MEMBERSHIP_", "STALE_OR_FUTURE_UNIVERSE", "FUTURE_SOURCE_REVISION")):
        return "MEMBERSHIP_SOURCE_UNAVAILABLE_OR_INVALID"
    if code in ("YAHOO_PROVIDER_REFUSAL", "MEMBERSHIP_TRANSPORT_REFUSAL"):
        return "TRANSPORT_OR_PROVIDER_ERROR_UNRESOLVED"
    if code in ("CALL_BUDGET", "TIME_BUDGET"):
        return code
    return "SCHEMA_OR_INTEGRITY_VIOLATION" if isinstance(exc, D.Refused) else "DIAGNOSTIC_INFRASTRUCTURE_ERROR"


def failure(ticker, phase, exc, reply=None):
    return {"ticker": ticker, "phase": phase, "failureClass": classify(exc, reply),
            "sourceCode": getattr(exc, "code", None), "collectorOutcome": getattr(exc, "outcome", None),
            "exceptionType": type(exc).__name__, "originalMessage": str(exc)}


def select_sample(snapshot):
    """Fixed identity-only selection; never rank observed prices or outcomes."""
    members = {m["ticker"]: m for m in snapshot["members"]}
    ordinary = [members[t] for t in ("AAPL", "JPM") if t in members]
    unusual = next((members[t] for t in ("BRK-B", "BF-B") if t in members), None)
    if unusual is None:
        unusual = next((m for m in snapshot["members"] if "." in m["sourceSymbol"] or "-" in m["ticker"]), None)
    for m in snapshot["members"]:
        if len(ordinary) >= 2:
            break
        if m not in ordinary and m != unusual:
            ordinary.append(m)
    return ordinary + ([unusual] if unusual is not None else [])


def runtime_identity():
    # Explicit allowlist only: never print credentials or proxy environment.
    keys = ("GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "PREFLIGHT_RUNNER_ENVIRONMENT", "RUNNER_OS", "RUNNER_ARCH", "ImageOS", "ImageVersion",
            "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "PREFLIGHT_HEAD_SHA", "GITHUB_WORKFLOW")
    value = {k: os.environ.get(k) for k in keys}
    value["githubHostedClaim"] = value["GITHUB_ACTIONS"] == "true" and (value["PREFLIGHT_RUNNER_ENVIRONMENT"] or value["RUNNER_ENVIRONMENT"]) == "github-hosted"
    root = Path(__file__).resolve().parents[1]
    value["codeSha256"] = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in (
        "pipeline/us_real_source_preflight.py", "scripts/preflight_us_real_sources.py",
        "pipeline/us_daily_market_data.py", "pipeline/us_daily_market_sources.py", ".github/workflows/tests.yml")}
    return value


def files(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def probe(root, membership_response, fetch_price, *, now, runtime=None, monotonic=time.monotonic):
    """Injectable for invented fixtures; the CLI has only the real-source path.

    Each symbol is fetched at most once. Repeat-write verification reuses the
    exact acquired rows, and never issues another provider request.
    """
    store = D.ObservationStore(root, membership_response.source_kind)
    root = store.root
    at = D.stamp(now)
    result = {"schema": "US_REAL_SOURCE_PREFLIGHT_V1", "diagnosticVersion": VERSION,
              "version": D.VERSION, "sourceKind": membership_response.source_kind,
              "startedAt": at, "runtime": runtime or {}, "verdict": "BLOCKED", "calls": 0,
              "maxProviderAdapterCalls": MAX_PROVIDER_CALLS, "maxSeconds": MAX_SECONDS,
              "fullUniverseCollectionAttempted": False, "fullUniverseReady": False,
              "collectionComplete": False, "productionWritePerformed": False, "scheduleActivated": False,
              "totalReturnComputed": False, "failures": [], "observations": [], "scopeComplete": False}
    with store.locked():
        try:
            snapshot = D.membership_snapshot(membership_response, at)
            store.save_snapshot(snapshot, membership_response.raw)
        except D.Refused as exc:
            result["failures"].append(failure(None, "MEMBERSHIP", exc))
            return finish(store, result)
        dates = D.completed_sessions(at)
        targets, _ = D.target_members(snapshot)
        benchmarks = [next(m for m in targets if m["ticker"] == t) for t in D.BENCHMARKS]
        sample = select_sample(snapshot)
        result["membership"] = {k: snapshot[k] for k in ("source", "sourceIdentity", "sourceRawSha256", "memberCount", "observedAt",
                                                        "effectiveMembershipDate", "officialCompletenessVerified", "pitCompleteHistoricalUniverse")}
        result["membership"]["issuerCikCount"] = len({m["issuerCik"] for m in snapshot["members"]})
        result["plan"] = {"sessions": dates, "benchmarks": list(D.BENCHMARKS),
                          "conditionalSample": sample, "selectionRule": "AAPL,JPM,BRK-B/BF-B when present; otherwise deterministic identity-only fallback",
                          "sampleRequiresBothBenchmarks": True, "membershipApplicability": "OBSERVED_QUERY_SET_NOT_ASSERTED_SESSION_MEMBERSHIP"}
        # Publish the plan before the first Yahoo call.
        (root / "preflight-plan.json").write_bytes(D.canonical(result["plan"])+b"\n")
        started = monotonic()
        acquired = []
        def get(member, phase):
            reply = None
            try:
                if result["calls"] >= MAX_PROVIDER_CALLS:
                    raise D.Refused("CALL_BUDGET", "Fixed provider adapter budget exhausted")
                if monotonic()-started >= MAX_SECONDS:
                    raise D.Refused("TIME_BUDGET", "No further source request after the wall-time budget")
                result["calls"] += 1
                reply = fetch_price(member["ticker"], dates[0], dates[-1])
                rows = D.price_records(reply, member, snapshot, dates, at)
                append = store.append_prices(rows)
                if append["conflicts"] or append["appended"] != len(rows):
                    raise D.Refused("UNEXPECTED_EXISTING_OBSERVATION", "Use a fresh isolated stage for this one-shot diagnostic")
                acquired.extend(rows)
                result["observations"].append({"ticker": member["ticker"], "phase": phase, "rowCount": len(rows),
                    "securityId": member["securityId"], "identityStatus": member["identityStatus"],
                    "availableFrom": rows[0]["availableFrom"], "sourceVersion": reply.source_version,
                    "sourceAcquisitionId": rows[0]["sourceAcquisitionId"], "sourcePanelDigest": rows[0]["sourcePanelDigest"],
                    "currency": reply.metadata["currency"], "instrumentType": reply.metadata["instrumentType"],
                    "writtenChunks": append["files"]})
                return True
            except Exception as exc:
                result["failures"].append(failure(member["ticker"], phase, exc, reply))
                return False
        bench_ok = [get(m, "BENCHMARK") for m in benchmarks]
        result["bothBenchmarksSucceeded"] = all(bench_ok)
        if all(bench_ok):
            for member in sample:
                get(member, "CONSTITUENT_SAMPLE")
        else:
            result["sampleNotRequestedReason"] = "BENCHMARK_PREFLIGHT_FAILED"
        if acquired:
            try:
                before = files(root)
                repeated = store.append_prices(acquired)
                unchanged = before == files(root)
                stored = store.observations(dates)
                checks = []
                for row in acquired:
                    raw = next(r for r in row["sourcePanel"] if r["date"] == row["core"]["date"])
                    factor = row["splitFactorStrictlyAfterSession"]
                    core = row["core"]
                    checks.append(all(math.isclose(core[k], raw[k]*factor) for k in ("Open", "High", "Low", "Close")) and
                                  math.isclose(core["Volume"], raw["Volume"]/factor) and
                                  math.isclose(core["cashDividendAsTraded"], raw["Dividends"]*factor))
                first = min(D.utc(r["availableFrom"]) for r in acquired)
                latest = max(D.utc(r["availableFrom"]) for r in acquired)
                result["integrity"] = {"sameAcquisitionRepeatRequests": 0, "repeatCount": repeated["repeated"],
                    "appendOnlyBytesUnchanged": unchanged, "storedRecordCount": len(stored),
                    "allSourceReferencesVerified": len(stored) == len(acquired), "asTradedBasisVerified": all(checks),
                    "noPricesBeforeFirstAcquisition": not store.prices_at(first-timedelta(microseconds=1)),
                    "observableRecordCountAtLatestAcquisition": len(store.prices_at(latest)),
                    "nonzeroDividendsObserved": sum(r["core"]["cashDividendAsTraded"] > 0 for r in acquired),
                    "nonidentitySplitsObserved": sum(r["core"]["splitRatio"] != 1 for r in acquired)}
                check = result["integrity"]
                if not (unchanged and repeated["repeated"] == len(acquired) and check["allSourceReferencesVerified"] and
                        check["asTradedBasisVerified"] and check["noPricesBeforeFirstAcquisition"]):
                    raise D.Refused("PREFLIGHT_INTEGRITY_FAILED", "Actual repeat/provenance/basis/availability checks did not all pass")
            except Exception as exc:
                result["failures"].append(failure(None, "STORAGE_INTEGRITY", exc))
        result["scopeComplete"] = all(bench_ok) and len(result["observations"]) == len(benchmarks)+len(sample) and not result["failures"]
        result["verdict"] = "PASS" if result["scopeComplete"] else "PARTIAL" if acquired else "BLOCKED"
        return finish(store, result)


def finish(store, result):
    result["failureClasses"] = sorted({f["failureClass"] for f in result["failures"]})
    result["validPriceRecordCount"] = sum(o["rowCount"] for o in result["observations"])
    result["unresolvedLimitations"] = ["SECONDARY_MEMBERSHIP_NOT_OFFICIAL_EFFECTIVE_HISTORY", "PROVISIONAL_SECURITY_ID_NOT_PERMANENT_SHARE_CLASS_ID",
                                      "SMALL_SAMPLE_NOT_FULL_UNIVERSE_OR_DAILY_RELIABILITY_PROOF", "YAHOO_UNOFFICIAL_PROVIDER_NO_SLA"]
    store.save_manifest(result)
    store.manifests()
    payload = D.sealed(result)
    (store.root / "preflight.json").write_bytes(D.canonical(payload)+b"\n")
    inventory = files(store.root)
    (store.root / "evidence-hashes.json").write_bytes(D.canonical(inventory)+b"\n")
    return payload


def summary(result):
    counts = {o["ticker"]: o["rowCount"] for o in result["observations"]}
    sample = sum(o["phase"] == "CONSTITUENT_SAMPLE" for o in result["observations"])
    failures = "+".join(result["failureClasses"]) or "NONE"
    return f'{result["verdict"]} SPY={counts.get("SPY",0)} QQQ={counts.get("QQQ",0)} sample={sample} rows={result["validPriceRecordCount"]} failures={failures}'


def main(output):
    # Direct production/Git destination refusal happens before any source request.
    store = D.ObservationStore(output)
    if store.prices.exists() or store.universe.exists():
        raise D.Refused("FRESH_STAGE_REQUIRED", "Do not repeat network acquisition into a prior diagnostic stage")
    identity = runtime_identity()
    try:
        membership = S.current_sp500()
    except Exception as exc:
        with store.locked():
            result = finish(store, {"schema": "US_REAL_SOURCE_PREFLIGHT_V1", "diagnosticVersion": VERSION,
                "version": D.VERSION, "sourceKind": D.LIVE, "startedAt": S.now_utc(), "runtime": identity,
                "verdict": "BLOCKED", "calls": 0, "observations": [], "failures": [failure(None,"MEMBERSHIP",exc)],
                "scopeComplete": False, "collectionComplete": False, "fullUniverseCollectionAttempted": False,
                "fullUniverseReady": False, "productionWritePerformed": False, "scheduleActivated": False, "totalReturnComputed": False})
    else:
        result = probe(output, membership, S.yahoo_daily, now=S.now_utc(), runtime=identity)
    # GitHub output names contain only controlled classification/count values.
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
            stream.write("verdict="+result["verdict"]+"\nsummary="+summary(result)+"\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
            stream.write("## US real-source preflight\n\n"+summary(result)+"\n\nNo production writes or scheduling. See immutable artifact evidence.\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    # Provider refusal is a measured diagnostic verdict; infrastructure is a CI failure.
    return 1 if "DIAGNOSTIC_INFRASTRUCTURE_ERROR" in result["failureClasses"] else 0
