"""us-tiingo-price-recovery-pilot-v1 -- can a free Tiingo account fill the missing US price histories? Feasibility only.

Twenty audit identifiers are fixed in a committed plan before any provider is asked (10 with no candidate price, 8 partial, 2
FULL controls). A run asks Tiingo for each one's metadata and in-window daily rows, asks SEC EDGAR and OpenFIGI for independent
identity evidence, and compares what came back with what the existing candidate set (#241/#243) already holds. It measures
existence, identity and event-field coverage. It never computes a return, a label, a CAGR or an IC, and every identity stays
NOT_ADMITTED: admission needs the identity, corporate-action, terminal-consideration, PIT and storage-rights gates of
`us_departed_dataset_admission`, none of which a single vendor's answer can pass.

Standard library only (plus the stdlib-only `us_departed_price_recovery`), so the owner's Windows Python runs it with no install.
The provider is reached through an injected `fetch` so every failure mode is tested offline; nothing here opens a socket.

Endpoint shapes, field names and plan limits are NOT verified from official documentation in the authoring environment (every
official host was unreachable from it). They are the shapes public client libraries use, and each run validates the response
schema it actually receives and stops on anything else rather than guessing.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import time
import zipfile

from pipeline import us_departed_price_recovery as R

VERSION = "US_TIINGO_PRICE_RECOVERY_PILOT_V1"
STUDY = "us-tiingo-price-recovery-pilot-v1"
PLAN_PATH = "docs/us-readiness/us-tiingo-price-recovery-pilot-v1-plan.json"
REPORT_JSON = "docs/us-readiness/us-tiingo-price-recovery-pilot-v1-report.json"
REPORT_MD = "docs/us-readiness/us-tiingo-price-recovery-pilot-v1-report.md"
ADMISSION = "NOT_ADMITTED"
# The private session table of us-departed-dataset-admission-audit-v1 (#243): canonical JSON rows, gzip-compressed.
EXISTING_SESSION_TABLE_SHA256 = "14d96bda6680a51f939d49f1abce276e86687fe91e766f3ab15f9c7d8cd76248"

TIINGO = "https://api.tiingo.com"
TIINGO_SUPPORTED_TICKERS = "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"
TIINGO_DOCUMENT_PAGES = {"pricing": "https://www.tiingo.com/about/pricing", "endOfDayDocumentation": "https://www.tiingo.com/documentation/end-of-day"}
SEC_CIK_LOOKUP = "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
OPENFIGI = "https://api.openfigi.com/v3/mapping"

# Hard per-run budgets and pacing. The free limits are not verified, so the budget is set far below every figure seen in secondary
# sources and a run never retries: one refusal ends that source for the run.
BUDGET = {"tiingo": 42, "tiingoMedia": 1, "tiingoDocs": 2, "sec": 30, "openfigi": 2}
PACING_SECONDS = {"tiingo": 2.0, "tiingoMedia": 0.0, "tiingoDocs": 1.0, "sec": 0.25, "openfigi": 3.0}
MAX_BYTES = {"tiingo": 8 << 20, "tiingoMedia": 32 << 20, "tiingoDocs": 4 << 20, "sec": 160 << 20, "openfigi": 1 << 20}
TIMEOUT_SECONDS = 30
STOP_STATUSES = {401: "AUTH_REJECTED", 403: "ACCESS_FORBIDDEN", 429: "RATE_LIMITED"}
OPENFIGI_JOBS_PER_REQUEST = 10
ADJUSTMENT_TOLERANCE = 5e-4          # relative change of adjClose/close treated as an adjustment step (level ratio, never a return)
PRICE_FIELDS = ("open", "high", "low", "close", "volume", "adjOpen", "adjHigh", "adjLow", "adjClose", "adjVolume",
                "divCash", "splitFactor")
FORBIDDEN_REPORT_KEYS = {"open", "high", "low", "close", "adjclose", "adjopen", "adjhigh", "adjlow", "volume", "adjvolume",
                         "divcash", "splitfactor", "price", "prices", "return", "returns", "cagr", "ic", "label"}

STRATA = {"NONE": 10, "PARTIAL": 8, "FULL": 2}
FULL_CONTROLS = ("JWN", "ADS")       # the first two securities of us-price-evidence-pilot-v1 (#244), chosen there by name order


class Refused(RuntimeError):
    pass


class NetworkBlocked(RuntimeError):
    """The request never reached the provider (proxy CONNECT refusal, DNS failure, TLS interception). Never bypassed."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


# =======================================================================================================================================
# Pre-registered selection (membership and coverage facts only; no price, return or outcome)
# =======================================================================================================================================
def hold_reason(item):
    reasons = []
    if item["identityHold"]:
        reasons.append("SEALED_IDENTITY_HOLD")
    if item["symbolReuseFlagFromSealedAudit"]:
        reasons.append("TICKER_REUSED_IN_SEALED_AUDIT")
    return reasons


def select_pilot(inventory):
    """The 20 identifiers, by fixed rules that read only the published membership/coverage audit.

    NONE (10): the 7 largest missing windows without a hold flag, plus the 3 largest with one (they test the HOLD path and are
    never linked on the ticker alone). PARTIAL (8): no hold flag, 4 whose membership window ends on or before 2020-12-31 and 4
    after it (the free-source era split #241 measured), largest missing windows first. FULL (2): the #244 controls.
    Ties break on the identifier. A larger missing window is chosen because it is where a recovery would matter most.
    """
    rows = sorted(inventory, key=lambda i: (-i["missingSessions"], i["auditIdentifier"]))
    by = lambda state: [i for i in rows if i["qualifiedPriceCoverage"] == state]  # noqa: E731
    none = by("NONE")
    picked = [(i, "NONE", "LARGEST_MISSING_WINDOW_NO_HOLD") for i in [i for i in none if not hold_reason(i)][:7]]
    picked += [(i, "NONE", "LARGEST_MISSING_WINDOW_WITH_HOLD_TESTS_HOLD_PATH") for i in [i for i in none if hold_reason(i)][:3]]
    partial = [i for i in by("PARTIAL") if not hold_reason(i)]
    early = [i for i in partial if i["expectedPricingWindow"]["last"] <= "2020-12-31"][:4]
    late = [i for i in partial if i["expectedPricingWindow"]["last"] > "2020-12-31"][:4]
    picked += [(i, "PARTIAL", "LARGEST_MISSING_WINDOW_ENDING_BY_2020") for i in early]
    picked += [(i, "PARTIAL", "LARGEST_MISSING_WINDOW_ENDING_AFTER_2020") for i in late]
    full = {i["auditIdentifier"]: i for i in by("FULL")}
    picked += [(full[t], "FULL", "CONTROL_FIRST_TWO_SECURITIES_OF_US_PRICE_EVIDENCE_PILOT_V1") for t in FULL_CONTROLS]
    if Counter(s for _, s, _ in picked) != Counter(STRATA) or len({i["auditIdentifier"] for i, _, _ in picked}) != 20:
        raise ValueError("PILOT_SELECTION_DOES_NOT_MATCH_THE_REGISTERED_STRATA")
    return picked


def runs(days, calendar):
    """Contiguous runs of `days` in the session calendar, as [first, last, sessions]."""
    position = {d: i for i, d in enumerate(calendar)}
    out = []
    for day in sorted(days, key=position.__getitem__):
        if out and position[day] == position[out[-1][1]] + 1:
            out[-1][1], out[-1][2] = day, out[-1][2] + 1
        else:
            out.append([day, day, 1])
    return out


def share_class_note(names):
    text = " ".join(names).lower()
    match = re.search(r"\b(class|series)\s+([a-z])\b", text)
    return f"NAME_STATES_{match.group(1).upper()}_{match.group(2).upper()}" if match else "NOT_STATED_COMMON_NOT_VERIFIED"


def plan_entry(item, stratum, reason, expected, calendar, prior_ciks):
    holds = hold_reason(item)
    missing = None
    if stratum == "NONE":
        missing = runs(expected, calendar)
    elif stratum == "FULL":
        missing = []
    ciks = sorted(set(item["historicalCiksWhereReported"]) | set(prior_ciks.get(item["auditIdentifier"], [])))
    return {
        "auditIdentifier": item["auditIdentifier"], "securityId": item["securityId"], "stratum": stratum, "selectionReason": reason,
        "historicalIssuerNames": item["historicalIssuerNames"], "candidateCiks": ciks,
        "cikProvenance": "historicalCiksWhereReported (#241) plus us-price-evidence-pilot-v1 candidate CIKs (#244); not an official link",
        "shareClass": share_class_note(item["historicalIssuerNames"]),
        "membershipIntervals": item["membershipIntervals"], "expectedPricingWindow": item["expectedPricingWindow"],
        "expectedSessionRuns": runs(expected, calendar),
        "existing": {"qualifiedPriceCoverage": item["qualifiedPriceCoverage"], "coveredSessions": item["coveredSessions"],
                     "missingSessions": item["missingSessions"],
                     "missingSessionRuns": missing,
                     "missingSessionRunsNote": None if missing is not None else "PRIVATE_SESSION_TABLE_REQUIRED_FOR_EXACT_RANGES",
                     "candidateSources": sorted({s["source"] for s in item["candidateSources"] if s["countedInQualifiedCoverage"]}),
                     "corporateActionState": item["corporateActionState"], "terminalConsideration": item["terminalConsideration"]},
        "holdReasons": holds, "pilotDisposition": "HOLD_NEVER_LINKED_ON_TICKER" if holds else "ELIGIBLE_FOR_LINKING_IF_IDENTITY_AGREES",
        "admission": ADMISSION,
    }


def build_plan(inventory, expected_by_ticker, calendar, prior_ciks, provenance):
    entries = []
    for item, stratum, reason in select_pilot(inventory):
        expected = expected_by_ticker[item["auditIdentifier"]]
        if len(expected) != item["coveredSessions"] + item["missingSessions"] or len(expected) != item["expectedPricingWindow"]["sessions"]:
            raise ValueError("EXPECTED_SESSIONS_DO_NOT_REPRODUCE_THE_PUBLISHED_AUDIT: " + item["auditIdentifier"])
        entries.append(plan_entry(item, stratum, reason, expected, calendar, prior_ciks))
    return {"studyId": STUDY, "version": VERSION, "status": "PRE_REGISTERED_BEFORE_ANY_PROVIDER_REQUEST", "admission": ADMISSION,
            "provenance": provenance, "selectionRule": select_pilot.__doc__.strip(), "calendar": {"name": "XNYS", "sessions": list(calendar)},
            "identities": entries, "outcomesRead": 0, "returnsComputed": 0}


def expected_sessions(entry, calendar):
    position = {d: i for i, d in enumerate(calendar)}
    out = set()
    for first, last, count in entry["expectedSessionRuns"]:
        span = calendar[position[first]:position[last] + 1]
        if len(span) != count:
            raise ValueError("PLAN_SESSION_RUN_CORRUPT")
        out.update(span)
    return out


# =======================================================================================================================================
# Acquisition (injected transport; bounded, paced, no retries; the token travels only in a request header)
# =======================================================================================================================================
class Session:
    """One run's requests. `fetch(method, url, headers, body, timeout) -> (status, headers, bytes)`; raises NetworkBlocked."""

    def __init__(self, fetch, raw_dir, *, token=None, sec_user_agent=None, sleep=time.sleep, clock=time.time):
        self.fetch, self.raw_dir, self.token, self.sec_user_agent = fetch, Path(raw_dir), token, sec_user_agent
        self.sleep, self.clock = sleep, clock
        self.calls, self.stopped, self.records = Counter(), {}, []
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def request(self, source, purpose, url, *, method="GET", body=None):
        if source in self.stopped:
            return None
        if self.calls[source] >= BUDGET[source]:
            self.stopped[source] = "CALL_BUDGET_EXHAUSTED"
            return None
        headers = {"Accept": "application/json, text/plain, */*", "User-Agent": "Investment-us-tiingo-price-recovery-pilot-v1"}
        if source == "tiingo":
            headers["Authorization"] = "Token " + self.token
        if source == "sec":
            if not self.sec_user_agent:
                self.stopped[source] = "NOT_RUN_NO_CONTACT_USER_AGENT"
                return None
            headers["User-Agent"] = self.sec_user_agent
        if source == "openfigi":
            headers["Content-Type"] = "application/json"
        if self.calls[source]:
            self.sleep(PACING_SECONDS[source])
        self.calls[source] += 1
        record = {"source": source, "purpose": purpose, "method": method, "url": url, "requestedAt": round(self.clock(), 3)}
        try:
            status, response_headers, raw = self.fetch(method, url, headers, body, TIMEOUT_SECONDS)
        except NetworkBlocked as error:
            record.update(outcome="ACCESS_BLOCKED_BEFORE_PROVIDER", detail=self.scrub(str(error))[:300])
            self.stopped[source] = "ACCESS_BLOCKED_BEFORE_PROVIDER"
            self.records.append(record)
            return None
        except Exception as error:  # timeouts, resets: recorded once, never retried
            record.update(outcome="TRANSPORT_ERROR", detail=self.scrub(type(error).__name__ + ": " + str(error))[:300])
            self.stopped[source] = "TRANSPORT_ERROR"
            self.records.append(record)
            return None
        kept = {k: v for k, v in (response_headers or {}).items()
                if k.lower() in ("content-type", "date") or "ratelimit" in k.lower() or "retry-after" in k.lower()}
        record.update(status=status, bytes=len(raw), responseHeaders=kept)
        if len(raw) > MAX_BYTES[source]:
            record["outcome"] = "BYTE_BUDGET_EXCEEDED"
            self.stopped[source] = "BYTE_BUDGET_EXCEEDED"
        elif status in STOP_STATUSES or status >= 500:
            record["outcome"] = STOP_STATUSES.get(status, "PROVIDER_ERROR")
            record["bodySha256"] = digest(raw)
            self.stopped[source] = record["outcome"]
        else:
            record["outcome"] = "ANSWERED"
            record["sha256"] = digest(raw)
            path = self.raw_dir / (record["sha256"] + ".bin")
            if not path.exists():
                path.write_bytes(raw)
        self.records.append(record)
        return (status, raw) if record["outcome"] == "ANSWERED" else None

    def scrub(self, text):
        return text.replace(self.token, "[REDACTED]") if self.token else text


def tiingo_meta_url(ticker):
    return f"{TIINGO}/tiingo/daily/{ticker.lower()}"


def tiingo_prices_url(ticker, first, last):
    return f"{TIINGO}/tiingo/daily/{ticker.lower()}/prices?startDate={first}&endDate={last}&format=json&resampleFreq=daily"


def acquire(plan, session):
    """Every request of one run, in a fixed order. Returns {key: (status, raw)} for answered requests only."""
    answers = {}

    def ask(key, source, purpose, url, **kw):
        out = session.request(source, purpose, url, **kw)
        if out is not None:
            answers[key] = out

    ask("tiingo:supported", "tiingoMedia", "SUPPORTED_TICKERS_LIST", TIINGO_SUPPORTED_TICKERS)
    for entry in plan["identities"]:
        ticker, window = entry["auditIdentifier"], entry["expectedPricingWindow"]
        ask(f"tiingo:meta:{ticker}", "tiingo", "META", tiingo_meta_url(ticker))
        ask(f"tiingo:prices:{ticker}", "tiingo", "DAILY_ROWS_IN_MEMBERSHIP_WINDOW", tiingo_prices_url(ticker, window["first"], window["last"]))
    ask("sec:ciklookup", "sec", "CIK_NAME_LOOKUP", SEC_CIK_LOOKUP)
    lookup = parse_cik_lookup(answers["sec:ciklookup"][1]) if "sec:ciklookup" in answers else {}
    for cik in sorted({c for e in plan["identities"] for c in sec_candidate_ciks(e, lookup)}, key=int):
        ask(f"sec:submissions:{int(cik)}", "sec", "SUBMISSIONS_NAMES_AND_TICKERS", SEC_SUBMISSIONS.format(cik=int(cik)))
    tickers = [e["auditIdentifier"] for e in plan["identities"]]
    for start in range(0, len(tickers), OPENFIGI_JOBS_PER_REQUEST):
        jobs = [{"idType": "TICKER", "idValue": t, "exchCode": "US"} for t in tickers[start:start + OPENFIGI_JOBS_PER_REQUEST]]
        ask(f"openfigi:{start}", "openfigi", "TICKER_MAPPING", OPENFIGI, method="POST", body=json.dumps(jobs).encode())
    for name, url in TIINGO_DOCUMENT_PAGES.items():
        ask(f"tiingo:docs:{name}", "tiingoDocs", "PUBLIC_TERMS_PAGE_CAPTURE_FOR_OWNER_REVIEW", url)
    return answers


# =======================================================================================================================================
# Parsing (schema-checked; anything unexpected is recorded, never coerced)
# =======================================================================================================================================
def parse_supported_tickers(raw):
    """{TICKER: [rows]} from the zip's single CSV. Several rows for one ticker are evidence of reuse."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError("SUPPORTED_TICKERS_ZIP_NOT_ONE_CSV")
        text = archive.read(names[0]).decode("utf-8-sig")
    lines = [line.split(",") for line in text.splitlines() if line.strip()]
    header = [h.strip() for h in lines[0]]
    if not {"ticker", "exchange", "assetType", "startDate", "endDate"} <= set(header):
        raise ValueError("SUPPORTED_TICKERS_SCHEMA_UNEXPECTED")
    out = {}
    for cells in lines[1:]:
        row = dict(zip(header, (c.strip() for c in cells)))
        out.setdefault(row["ticker"].upper(), []).append({k: row.get(k) or None for k in ("exchange", "assetType", "priceCurrency", "startDate", "endDate")})
    return out


def parse_meta(raw):
    doc = json.loads(raw)
    if not isinstance(doc, dict) or "ticker" not in doc:
        raise ValueError("META_SCHEMA_UNEXPECTED")
    fields = sorted(doc)
    return {"name": doc.get("name"), "exchangeCode": doc.get("exchangeCode"), "startDate": (doc.get("startDate") or None),
            "endDate": (doc.get("endDate") or None), "fields": fields,
            "permanentIdentifierFields": [f for f in fields if "perma" in f.lower() or f.lower() in ("figi", "cik", "isin", "cusip")]}


def parse_prices(raw, calendar_set):
    """Validated rows by session date. Duplicates are quarantined; a missing volume stays None, never zero."""
    doc = json.loads(raw)
    if not isinstance(doc, list):
        raise ValueError("PRICES_SCHEMA_UNEXPECTED")
    rows, invalid, seen, duplicates = {}, Counter(), set(), set()
    fields = sorted({k for row in doc if isinstance(row, dict) for k in row})
    for row in doc:
        try:
            if not isinstance(row, dict):
                raise ValueError("ROW_NOT_AN_OBJECT")
            day = str(row.get("date", ""))[:10]
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError("INVALID_DATE")
            if day not in calendar_set:
                raise ValueError("NON_SESSION_DATE")
            if day in seen:
                duplicates.add(day)
            seen.add(day)
            values = {}
            for name in PRICE_FIELDS:
                value = row.get(name)
                if value is not None:
                    value = float(value)
                    if not math.isfinite(value) or value < 0:
                        raise ValueError("NONFINITE_OR_NEGATIVE_VALUE")
                values[name] = value
            for name in ("close", "adjClose"):
                if values[name] is None or values[name] <= 0:
                    raise ValueError("MISSING_OR_NONPOSITIVE_" + name.upper())
            if all(values[k] is not None for k in ("open", "high", "low")) and (
                    values["low"] > min(values["open"], values["close"]) * (1 + 1e-9) or values["high"] < max(values["open"], values["close"]) * (1 - 1e-9)):
                raise ValueError("OHLC_INCONSISTENT")
            if values["splitFactor"] is not None and values["splitFactor"] <= 0:
                raise ValueError("NONPOSITIVE_SPLIT_FACTOR")
            rows[day] = values
        except (ValueError, TypeError) as error:
            invalid[str(error)] += 1
    for day in duplicates:
        rows.pop(day, None)
    return rows, {"rawRows": len(doc), "validRows": len(rows), "duplicateDates": len(duplicates), "invalidRows": dict(sorted(invalid.items())),
                  "fields": fields, "eventFieldsPresent": {"dividendField": "divCash" in fields, "splitField": "splitFactor" in fields}}


def parse_cik_lookup(raw):
    """SEC cik-lookup-data.txt: 'NAME:CIK:' per line, historical names included. {normalized name: {cik}}."""
    out = {}
    for line in raw.decode("latin-1").splitlines():
        match = re.match(r"^(.*):(\d{1,10}):\s*$", line)
        if match:
            out.setdefault(R.normalized_name(match.group(1)), set()).add(str(int(match.group(2))))
    return out


def sec_candidate_ciks(entry, lookup):
    found = set(entry["candidateCiks"])
    for name in entry["historicalIssuerNames"]:
        found |= lookup.get(R.normalized_name(name), set())
    return sorted(found, key=int)


def parse_submissions(raw):
    doc = json.loads(raw)
    if not isinstance(doc, dict) or "name" not in doc:
        raise ValueError("SUBMISSIONS_SCHEMA_UNEXPECTED")
    former = [{"name": f.get("name"), "from": (f.get("from") or "")[:10] or None, "to": (f.get("to") or "")[:10] or None}
              for f in doc.get("formerNames") or []]
    return {"name": doc.get("name"), "formerNames": former, "tickers": [str(t).upper() for t in doc.get("tickers") or []]}


def parse_openfigi(raw, tickers):
    doc = json.loads(raw)
    if not isinstance(doc, list) or len(doc) != len(tickers):
        raise ValueError("OPENFIGI_SCHEMA_UNEXPECTED")
    out = {}
    for ticker, job in zip(tickers, doc):
        data = job.get("data") if isinstance(job, dict) else None
        out[ticker] = ({"state": "MAPPED", "names": sorted({d.get("name") for d in data if d.get("name")}),
                        "hasShareClassFigi": any(d.get("shareClassFIGI") for d in data)} if data
                       else {"state": "NO_IDENTIFIER", "warning": (job or {}).get("warning") or (job or {}).get("error")})
    return out


# =======================================================================================================================================
# Comparison (identity, sessions, events; counts and dates only)
# =======================================================================================================================================
def names_agree(candidate, historical, ticker):
    if not candidate:
        return False
    target = R.normalized_name(candidate)
    for name in historical:
        known = R.normalized_name(name)
        if target == known or (target, known) in R.NAME_ALIASES.get(ticker, set()) or (known, target) in R.NAME_ALIASES.get(ticker, set()):
            return True
        short, long_ = sorted((set(target.split()), set(known.split())), key=len)
        if len(short) >= 2 and short <= long_:
            return True
    return False


def overlaps(first, last, window):
    return bool(first) and bool(last) and first <= window["last"] and last >= window["first"]


def sec_evidence(entry, submissions):
    """SEC corroborates when a filer's current or former name agrees with a historical issuer name and, for a former name, the
    dates the SEC gives for it overlap the membership window."""
    window, hits = entry["expectedPricingWindow"], []
    for cik, doc in submissions.items():
        if names_agree(doc["name"], entry["historicalIssuerNames"], entry["auditIdentifier"]):
            hits.append({"cik": cik, "via": "CURRENT_NAME", "tickerListed": entry["auditIdentifier"] in doc["tickers"]})
        for former in doc["formerNames"]:
            if names_agree(former["name"], entry["historicalIssuerNames"], entry["auditIdentifier"]) and overlaps(
                    former["from"] or "0000-01-01", former["to"] or "9999-12-31", window):
                hits.append({"cik": cik, "via": "FORMER_NAME_DATED", "tickerListed": entry["auditIdentifier"] in doc["tickers"]})
    ciks = sorted({h["cik"] for h in hits}, key=int)
    return {"state": "NO_SEC_EVIDENCE" if not submissions else "CORROBORATES" if len(ciks) == 1 else
            "CONFLICTING_CIKS" if ciks else "NO_NAME_MATCH", "ciks": ciks, "hits": hits}


def adjustment_steps(rows):
    """Days where adjClose/close moves by more than the tolerance, split into explained (a dividend or split on that day) and not.
    A same-date level ratio, like `us_departed_price_recovery.compare_levels`; no time-difference return is formed."""
    days = sorted(rows)
    explained = unexplained = 0
    for before, day in zip(days, days[1:]):
        f0 = rows[before]["adjClose"] / rows[before]["close"]
        f1 = rows[day]["adjClose"] / rows[day]["close"]
        if abs(f1 / f0 - 1) > ADJUSTMENT_TOLERANCE:
            event = (rows[day]["divCash"] or 0) > 0 or (rows[day]["splitFactor"] not in (None, 1.0))
            explained += event
            unexplained += not event
    return explained, unexplained


def session_comparison(entry, rows, calendar, existing_rows=None):
    expected = expected_sessions(entry, calendar)
    tiingo = expected & set(rows)
    existing = entry["existing"]
    if existing_rows is not None:
        have = existing_rows & expected
        new, basis = len(tiingo - have), "EXACT_FROM_PRIVATE_SESSION_TABLE"
        bounds = [new, new]
    elif entry["stratum"] == "NONE":
        new, basis, bounds = len(tiingo), "EXACT_NO_EXISTING_CANDIDATE", [len(tiingo), len(tiingo)]
    elif entry["stratum"] == "FULL":
        new, basis, bounds = 0, "EXACT_EXISTING_COVERS_ALL", [0, 0]
    else:
        new, basis = None, "BOUNDS_PRIVATE_SESSION_TABLE_ABSENT"
        bounds = [max(0, len(tiingo) - existing["coveredSessions"]), min(len(tiingo), existing["missingSessions"])]
    in_window = sorted(tiingo)
    explained, unexplained = adjustment_steps({d: rows[d] for d in in_window})
    return {"expectedSessions": len(expected), "tiingoSessionsInWindow": len(tiingo),
            "tiingoMissingInWindow": len(expected - tiingo),
            "tiingoFirstInWindow": in_window[0] if in_window else None, "tiingoLastInWindow": in_window[-1] if in_window else None,
            "newlyRecoverableSessions": new, "newlyRecoverableBounds": bounds, "newlyRecoverableBasis": basis,
            "sessionsFrom2024": sum(d >= "2024-01-01" for d in tiingo),
            "dividendEventsInWindow": sum((rows[d]["divCash"] or 0) > 0 for d in in_window),
            "splitEventsInWindow": sum(rows[d]["splitFactor"] not in (None, 1.0) for d in in_window),
            "adjustmentStepsExplainedByEvent": explained, "adjustmentStepsUnexplained": unexplained,
            "volumeMissingInWindow": sum(rows[d]["volume"] is None for d in in_window)}


def listing_overlaps(rows, window):
    """Stock listings in the supported-tickers file whose dates overlap the membership window."""
    return [r for r in rows if (r.get("assetType") or "").lower() == "stock" and overlaps(r.get("startDate"), r.get("endDate"), window)]


def identity_verdict(entry, meta, rows_in_window, sec, figi, supported):
    """Pilot identity states. Every state is NOT_ADMITTED; only a non-HOLD identity whose Tiingo name and dates agree counts
    toward recoverable sessions, and only one with an independent second source counts as corroborated. A ticker listed more
    than once in the window is ambiguous and held; reuse outside the window is recorded, not held."""
    ticker, window = entry["auditIdentifier"], entry["expectedPricingWindow"]
    listing_rows = supported.get(ticker, []) if supported is not None else None
    in_window = None if listing_rows is None else listing_overlaps(listing_rows, window)
    reuse = in_window is not None and len(in_window) > 1
    meta = meta or {}
    name_ok = names_agree(meta.get("name"), entry["historicalIssuerNames"], ticker)
    dates_ok = overlaps((meta.get("startDate") or "")[:10] or None, (meta.get("endDate") or "")[:10] or None, window)
    independent = sec["state"] == "CORROBORATES" or (figi.get("state") == "MAPPED" and any(
        names_agree(n, entry["historicalIssuerNames"], ticker) for n in figi.get("names", [])))
    if entry["holdReasons"] or reuse:
        state = "HOLD_TICKER_REUSE_OR_IDENTITY_CONFLICT"
    elif not meta and not rows_in_window:
        state = "NO_TIINGO_RESPONSE"
    elif not name_ok or not dates_ok:
        state = "HOLD_TIINGO_NAME_OR_DATES_DISAGREE"
    elif independent:
        state = "INDEPENDENT_IDENTITY_CORROBORATED"
    else:
        state = "TIINGO_NAME_AND_DATES_ONLY_UNRESOLVED"
    return {"state": state, "tiingoNameAgrees": name_ok, "tiingoDatesOverlapMembership": dates_ok,
            "supportedTickerRows": None if listing_rows is None else len(listing_rows),
            "supportedTickerRowsOverlappingWindow": None if in_window is None else len(in_window), "supportedTickerAmbiguousInWindow": reuse,
            "secState": sec["state"], "secCiks": sec["ciks"], "openFigiState": figi.get("state", "NOT_ASKED"),
            "countsTowardRecovery": state in ("INDEPENDENT_IDENTITY_CORROBORATED", "TIINGO_NAME_AND_DATES_ONLY_UNRESOLVED"),
            "admission": ADMISSION}


def terminal_state(entry, meta, comparison):
    end = ((meta or {}).get("endDate") or "")[:10] or None
    window = entry["expectedPricingWindow"]
    if not comparison["tiingoSessionsInWindow"]:
        return "UNRESOLVED_NO_OBSERVATION"
    if end and end < window["last"]:
        return "TRADING_ENDS_INSIDE_MEMBERSHIP_TERMINAL_CONSIDERATION_UNRESOLVED"
    return "NO_TERMINAL_EVENT_OBSERVED_INSIDE_MEMBERSHIP_INDEX_EXIT_UNEXPLAINED"


# =======================================================================================================================================
# Report (aggregates only)
# =======================================================================================================================================
def analyze(plan, answers, records, stopped, *, existing_table=None, run_meta=None):
    calendar = plan["calendar"]["sessions"]
    calendar_set = set(calendar)
    errors = Counter()

    def parsed(key, parser, *args):
        if key not in answers:
            return None
        status, raw = answers[key]
        if status != 200:
            errors[f"{key.split(':')[0]}:{key.split(':')[1]}:HTTP_{status}"] += 1
            return None
        try:
            return parser(raw, *args)
        except (ValueError, KeyError, TypeError, zipfile.BadZipFile, UnicodeDecodeError) as error:
            errors[f"{key.split(':')[0]}:{key.split(':')[1]}:{str(error)[:60]}"] += 1
            return None

    supported = parsed("tiingo:supported", parse_supported_tickers)
    lookup = parsed("sec:ciklookup", parse_cik_lookup) or {}
    submissions = {}
    for key in sorted(k for k in answers if k.startswith("sec:submissions:")):
        doc = parsed(key, parse_submissions)
        if doc is not None:
            submissions[key.split(":")[2]] = doc
    tickers = [e["auditIdentifier"] for e in plan["identities"]]
    figi = {}
    for start in range(0, len(tickers), OPENFIGI_JOBS_PER_REQUEST):
        figi.update(parsed(f"openfigi:{start}", parse_openfigi, tickers[start:start + OPENFIGI_JOBS_PER_REQUEST]) or {})
    identities = []
    for entry in plan["identities"]:
        ticker = entry["auditIdentifier"]
        meta = parsed(f"tiingo:meta:{ticker}", parse_meta)
        priced = parsed(f"tiingo:prices:{ticker}", parse_prices, calendar_set)
        rows, quality = priced if priced else ({}, None)
        sec = sec_evidence(entry, {c: submissions[c] for c in sec_candidate_ciks(entry, lookup) if c in submissions})
        identity = identity_verdict(entry, meta, bool(set(rows) & expected_sessions(entry, calendar)), sec, figi.get(ticker, {}), supported)
        existing_rows = None if existing_table is None else existing_table.get(ticker, set())
        comparison = session_comparison(entry, rows, calendar, existing_rows)
        identities.append({
            "auditIdentifier": ticker, "stratum": entry["stratum"], "tiingoMeta": None if meta is None else {
                **{k: meta[k] for k in ("exchangeCode", "startDate", "endDate", "permanentIdentifierFields")}, "nameAgrees": identity["tiingoNameAgrees"]},
            "tiingoPriceResponse": "VALID_ROWS" if rows else "NO_VALID_ROWS" if priced else "NOT_ANSWERED",
            "quality": None if quality is None else {k: quality[k] for k in ("rawRows", "validRows", "duplicateDates", "invalidRows", "eventFieldsPresent")},
            "identity": identity, "sessions": comparison, "terminal": terminal_state(entry, meta, comparison),
            "corporateActionLineage": "SINGLE_VENDOR_EVENT_FIELDS_UNVERIFIED" if comparison["tiingoSessionsInWindow"] else "UNRESOLVED_NO_OBSERVATION",
            "admission": ADMISSION})
    pages = {}
    for name in TIINGO_DOCUMENT_PAGES:
        if f"tiingo:docs:{name}" in answers:
            status, raw = answers[f"tiingo:docs:{name}"]
            pages[name] = {"status": status, "sha256": digest(raw), "termsExcerpts": terms_excerpts(raw), "interpretation": "NONE_OWNER_REVIEW_REQUIRED"}
    report = summarize(plan, identities, records, stopped, errors, existing_table is not None, run_meta or {})
    report["tiingoPublicPages"] = pages
    return report


TERMS_KEYWORDS = ("redistribut", "personal", "commercial", "internal use", "store", "cache", "display", "requests per", "unique symbols")


def terms_excerpts(raw, limit=12):
    """Sentences of a public page that mention use, storage or limits, for the owner to read. Nothing is interpreted."""
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw.decode("utf-8", "replace"), flags=re.S | re.I)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if any(k in sentence.lower() for k in TERMS_KEYWORDS) and sentence.strip()[:280] not in out:
            out.append(sentence.strip()[:280])
        if len(out) >= limit:
            break
    return out


def summarize(plan, identities, records, stopped, errors, exact, run_meta):
    counted = [i for i in identities if i["identity"]["countsTowardRecovery"]]
    lower = sum(i["sessions"]["newlyRecoverableBounds"][0] for i in counted)
    upper = sum(i["sessions"]["newlyRecoverableBounds"][1] for i in counted)
    baseline_missing = sum(e["existing"]["missingSessions"] for e in plan["identities"])
    state = Counter(i["identity"]["state"] for i in identities)
    tiingo_calls = Counter(r.get("outcome") for r in records if r["source"] == "tiingo")
    blocked = {s: v for s, v in stopped.items() if v in ("ACCESS_BLOCKED_BEFORE_PROVIDER", "AUTH_REJECTED", "ACCESS_FORBIDDEN", "RATE_LIMITED")}
    targets = [i for i in identities if i["stratum"] != "FULL" and not plan_hold(plan, i["auditIdentifier"])]
    targets_with_rows = sum(i["sessions"]["tiingoSessionsInWindow"] > 0 for i in targets)
    controls = [i for i in identities if i["stratum"] == "FULL"]
    control_gap = max((i["sessions"]["tiingoMissingInWindow"] / i["sessions"]["expectedSessions"] for i in controls), default=None)
    unexplained = sum(i["sessions"]["adjustmentStepsUnexplained"] for i in identities)
    observed = sum(i["sessions"]["tiingoSessionsInWindow"] for i in identities)
    if "tiingo" in blocked or not tiingo_calls.get("ANSWERED"):
        decision = "STOP_SOURCE_NOT_REACHABLE_OR_REFUSED"
    elif not controls or any(i["tiingoPriceResponse"] != "VALID_ROWS" for i in controls) or control_gap is None or control_gap > 0.01:
        decision = "STOP_CONTROLS_NOT_REPRODUCED"
    elif targets_with_rows < 4:
        decision = "STOP_FREE_COVERAGE_TOO_THIN"
    elif targets_with_rows >= 8 and unexplained <= 0.001 * max(observed, 1):
        decision = "EXPAND_TO_212_FREE_TIER_FEASIBILITY"
    else:
        decision = "LIMITED_VALUE_REVIEW_BEFORE_EXPANSION"
    return {
        "studyId": STUDY, "version": VERSION, "admission": ADMISSION, "planSha256": digest(canonical(plan)),
        "run": run_meta, "liveProviderResponse": "TESTED" if tiingo_calls.get("ANSWERED") else "NOT_TESTED",
        "calls": dict(Counter(r["source"] for r in records)), "outcomesBySource": {s: dict(Counter(r.get("outcome") for r in records if r["source"] == s))
                                                                                   for s in sorted({r["source"] for r in records})},
        "stoppedSources": dict(sorted(stopped.items())), "parseErrors": dict(sorted(errors.items())),
        "questions": {
            "1_identitiesWithTiingoPriceRows": sum(i["tiingoPriceResponse"] == "VALID_ROWS" for i in identities),
            "2_newlyRecoverableSessionsVsExistingMissing": {"lower": lower, "upper": upper, "exact": exact or lower == upper,
                                                           "existingMissingSessionsInPilot": baseline_missing,
                                                           "sessionsFrom2024AmongCounted": sum(i["sessions"]["sessionsFrom2024"] for i in counted)},
            "3_identity": {"independentlyCorroborated": state["INDEPENDENT_IDENTITY_CORROBORATED"],
                           "tiingoOnlyUnresolved": state["TIINGO_NAME_AND_DATES_ONLY_UNRESOLVED"],
                           "hold": state["HOLD_TICKER_REUSE_OR_IDENTITY_CONFLICT"] + state["HOLD_TIINGO_NAME_OR_DATES_DISAGREE"],
                           "noTiingoResponse": state["NO_TIINGO_RESPONSE"]},
            "4_unresolved": {"corporateActionLineageUnresolved": len(identities), "corporateActionLineageVerified": 0,
                             "identitiesWithDividendOrSplitObserved": sum(i["sessions"]["dividendEventsInWindow"] + i["sessions"]["splitEventsInWindow"] > 0 for i in identities),
                             "terminalConsiderationInsideMembership": sum(i["terminal"].startswith("TRADING_ENDS_INSIDE") for i in identities),
                             "noObservation": sum(i["terminal"] == "UNRESOLVED_NO_OBSERVATION" for i in identities)},
            "5_valueForExisting175": {"partialOrFullWithTiingoRows": sum(i["stratum"] != "NONE" and i["tiingoPriceResponse"] == "VALID_ROWS" for i in identities),
                                      "withDividendOrSplitFields": sum(i["stratum"] != "NONE" and bool(i["quality"]) and all(i["quality"]["eventFieldsPresent"].values()) for i in identities),
                                      "adjustmentStepsExplained": sum(i["sessions"]["adjustmentStepsExplainedByEvent"] for i in identities),
                                      "adjustmentStepsUnexplained": unexplained},
            "6_costBenefit": {"tiingoCallsUsed": sum(tiingo_calls.values()), "tiingoCallsFor212AtTwoPerIdentity": 424,
                              "freeTierLimits": "NOT_VERIFIED", "rateLimitHeadersSeen": sorted({k for r in records for k in r.get("responseHeaders", {}) if "ratelimit" in k.lower() or "retry" in k.lower()})},
            "7_decision": decision,
            "8_preAdmissionChecklist": PRE_ADMISSION_CHECKLIST},
        "decisionRule": DECISION_RULE, "nextSourceDecisionTable": NEXT_SOURCE_TABLE,
        "identities": identities,
        "statements": ["Counts and dates only: no price level, adjusted value, dividend amount, split ratio, return or label appears in this file.",
                       "Every identity is NOT_ADMITTED; no replay, sealed dataset, C1, WP1 or WP2 input changed.",
                       "Rights to store or redistribute Tiingo data are NOT_VERIFIED; raw bytes stay outside every git checkout."]}


def plan_hold(plan, ticker):
    return bool(next(e for e in plan["identities"] if e["auditIdentifier"] == ticker)["holdReasons"])


DECISION_RULE = ("Pre-registered before any request. STOP_SOURCE_NOT_REACHABLE_OR_REFUSED: Tiingo blocked, 401, 403 or 429. "
                 "STOP_CONTROLS_NOT_REPRODUCED: either FULL control lacks rows or misses more than 1% of its membership sessions. "
                 "STOP_FREE_COVERAGE_TOO_THIN: fewer than 4 of the 15 non-HOLD targets have any in-window row. "
                 "EXPAND_TO_212_FREE_TIER_FEASIBILITY: at least 8 of the 15 have rows and unexplained adjustment steps are at most "
                 "0.1% of observed sessions. Otherwise LIMITED_VALUE_REVIEW_BEFORE_EXPANSION. No branch admits data.")
PRE_ADMISSION_CHECKLIST = [
    "Owner confirms Tiingo terms permit private local storage for personal research (redistribution stays forbidden in public PRs).",
    "Per-identity issuer/share-class link to a CIK from an official source dated inside the membership window.",
    "As-traded close definition confirmed from the provider's official documentation and cross-checked on the FULL controls.",
    "Dated split and dividend chain reconciled against a second source; adjusted series rebuilt from raw closes and events.",
    "Terminal consideration (cash, stock, bankruptcy) evidenced for every identity whose trading ends inside membership.",
    "PIT visibility: no event or name used before its own public date.",
    "A new content-addressed input revision passes us_departed_dataset_admission AD1-AD8 before any WP0/A1 use.",
    "WP0 return-basis check (|annual delta| thresholds) re-run on the admitted revision; never on pilot data.",
]
NEXT_SOURCE_TABLE = [
    {"ifMeasured": "Tiingo has no rows for most NONE targets (delisted coverage thin)", "reviewFirst": "EODHD",
     "why": "delisted US tickers are a stated product feature; free tier and terms NOT_VERIFIED; costs a key and a paid plan likely"},
    {"ifMeasured": "Tiingo rows exist but identity stays unresolved", "reviewFirst": "SEC_EDGAR_EVIDENCE",
     "why": "free and official; names, former names and filings give the CIK link no price vendor supplies"},
    {"ifMeasured": "identity resolved but corporate actions or terminal consideration unresolved", "reviewFirst": "SEC_EDGAR_EVIDENCE_THEN_QUANTCONNECT",
     "why": "8-K/merger filings give consideration; QuantConnect map/factor files are a cross-check usable inside its platform only (terms NOT_VERIFIED)"},
    {"ifMeasured": "Tiingo blocked, refused or rate limited", "reviewFirst": "NONE_UNTIL_ACCESS_FIXED",
     "why": "an access failure measures the network, not the source; no bypass"},
]


def scan_report(report):
    """Refuses any price-like key anywhere in the public report."""
    def walk(value, path):
        if isinstance(value, dict):
            for key, inner in value.items():
                if str(key).lower() in FORBIDDEN_REPORT_KEYS:
                    raise ValueError("PRICE_LIKE_KEY_IN_PUBLIC_REPORT: " + path + "." + str(key))
                walk(inner, path + "." + str(key))
        elif isinstance(value, list):
            for index, inner in enumerate(value):
                walk(inner, f"{path}[{index}]")
    walk(report, "$")
    return report


def load_existing_table(path):
    """The #243 private session table, verified by its published digest. {ticker: {dates with a candidate observation}}."""
    raw = gzip.decompress(Path(path).read_bytes())
    if digest(raw) != EXISTING_SESSION_TABLE_SHA256:
        raise Refused("EXISTING_SESSION_TABLE_DIGEST_MISMATCH")
    out = {}
    for row in json.loads(raw):
        if row["status"] != "NO_OBSERVATION":
            out.setdefault(row["ticker"], set()).add(row["date"])
    return out
