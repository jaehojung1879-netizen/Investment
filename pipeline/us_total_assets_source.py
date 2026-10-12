"""What a total-assets observation has to carry before this repository may believe it. Shared vocabulary, not a fetcher.

The US value/quality sleeves need `Assets` for every S&P 500 quarterly filing. The Finnhub `financials-reported` feed stopped sending the
balance sheet for filings first served from 2026-10-07 (VENDOR_OMITS_BALANCE_SHEET_ENDPOINT_WIDE, Actions run 38250579358), so a different
source has to be found. A different source is only acceptable if its number can be tied to ONE filing and to the day that filing became
visible; this module is where that is decided, once, for every candidate source.

Three rules decide everything here and none of them is a tolerance:

  * IDENTITY. A value belongs to a stored filing only through its accession number. A vendor row that states only a CIK and a period end is
    a WEAK identity: it can check a value, it can never license a point-in-time claim. A row joined on a ticker alone or a period end alone is
    REJECTED, because tickers are reused and a period end is shared by every filer with the same fiscal calendar.
  * VISIBILITY. A value is visible from the filing date of ITS OWN accession, not from the day somebody fetched it. `observedAt` is recorded and
    is never an availability date: an observation made today cannot stand in for what was known on a historical signal date.
  * ORIGINALITY. A later filing repeats earlier periods as comparatives and a restatement changes them. A source that cannot say WHICH
    accession a number came from cannot say whether it is the original or a correction, and that is reported, not assumed away.

Nothing here makes a request, reads a key or computes a return.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

from pipeline import sec_access

CONTRACT = "US_TOTAL_ASSETS_SOURCE_FEASIBILITY_V1"

# ---- what an HTTP exchange MEANS ---------------------------------------------------------------------------------------------------------
HTTP_200_VALID = "HTTP_200_VALID_DATA"
HTTP_200_INVALID = "HTTP_200_INVALID_PAYLOAD"
HTTP_403_SEC_BLOCK = "HTTP_403_SEC_CDN_BLOCK"
HTTP_403_OTHER = "HTTP_403_OTHER"
HTTP_401 = "HTTP_401_KEY_REJECTED"
HTTP_402_PLAN = "HTTP_402_PLAN_REQUIRED"
HTTP_429 = "HTTP_429_RATE_LIMITED"
HTTP_OTHER = "HTTP_OTHER_ERROR"
NETWORK_ERROR = "NETWORK_ERROR"
PROXY_ERROR = "PROXY_ERROR"
SKIPPED_AFTER_BLOCK = "SKIPPED_AFTER_BLOCK"
NOT_TESTED = "NOT_TESTED"

ENTITLEMENT_WORDS = ("not entitled", "not authorized", "upgrade", "subscription", "plan", "premium", "access to this resource",
                     "don't have access", "do not have access", "restricted")

# ---- identity strength -------------------------------------------------------------------------------------------------------------------
EXACT_ACCESSION = "EXACT_ACCESSION"
WEAK_CIK_PERIOD_END = "WEAK_CIK_AND_PERIOD_END_NO_ACCESSION"
REJECTED_IDENTITY = "REJECTED_TICKER_OR_PERIOD_ONLY_OR_CONFLICT"

# ---- point-in-time verdicts --------------------------------------------------------------------------------------------------------------
PIT_PROVEN = "PIT_PROVEN_ORIGINAL_FILING"
PIT_NO_ACCESSION = "PIT_NOT_PROVABLE_NO_ACCESSION"
PIT_NO_FILING_DATE = "PIT_NOT_PROVABLE_NO_FILING_DATE"
PIT_DATE_CONFLICT = "PIT_CONFLICT_FILING_DATE_DIFFERS_FROM_STORED"
PIT_NOT_ORIGINAL = "PIT_FILING_DATE_IS_NOT_THE_ORIGINAL_FILING"
PIT_NO_MATCH = "NO_OBSERVATION_FOR_THIS_FILING"

ACCESSION_RE = re.compile(r"(\d{10})-?(\d{2})-?(\d{6})")
PLACEHOLDER_DOMAINS = ("example.com", "example.org", "example.net", "localhost", "users.noreply.github.com")
CONTACT_RE = re.compile(r"^[^@\s<>()]+@[^@\s<>()]+\.[A-Za-z]{2,}$")


def normalize_accession(value: Any) -> str | None:
    """`0000320193-24-000123` from either dashed or bare digits; None when it is neither."""
    match = ACCESSION_RE.search(str(value or ""))
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else None


def normalize_cik(value: Any) -> str | None:
    text = str(value if value is not None else "").strip()
    if not text.isdigit():
        return None
    return str(int(text)) if int(text) > 0 else None


def sec_contact_problem(contact: Any) -> str | None:
    """Why this is not an identity SEC could use to reach us, or None. The owner supplies it; nothing here ever invents one."""
    text = str(contact or "").strip()
    if not text:
        return "SEC_CONTACT_MISSING"
    if not CONTACT_RE.match(text):
        return "SEC_CONTACT_NOT_AN_EMAIL_ADDRESS"
    domain = text.rsplit("@", 1)[1].lower()
    if any(domain == d or domain.endswith("." + d) for d in PLACEHOLDER_DOMAINS):
        return "SEC_CONTACT_IS_A_PLACEHOLDER_OR_NOREPLY_ADDRESS"
    return None


def sec_user_agent(contact: str) -> str:
    problem = sec_contact_problem(contact)
    if problem:
        raise ValueError(problem)
    return f"InvestmentResearchDiagnostic/1.0 {contact.strip()}"


def to_date(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


# ---- classify one exchange ---------------------------------------------------------------------------------------------------------------
def classify_exchange(host_kind: str, status: int | None, body: bytes, error_kind: str | None, payload_ok: bool | None) -> dict:
    """Category, plus the non-sensitive evidence that decided it.

    `host_kind` is "sec" or "vendor". `error_kind` is "proxy", "network" or "timeout" when no HTTP exchange completed. `payload_ok` is the
    caller's validation of a 200 body (None when not validated). A 200 carrying a SEC block page is a BLOCK, not data.
    """
    head = (body or b"")[:600].decode("utf-8", "replace")
    evidence: dict[str, Any] = {"status": status, "bodyBytes": len(body or b"")}
    if error_kind:
        category = PROXY_ERROR if error_kind == "proxy" else NETWORK_ERROR
        evidence["errorKind"] = error_kind
        return {"category": category, "evidence": evidence}
    if host_kind == "sec":
        verdict, marker = sec_access.classify(status, body or b"")
        if verdict == sec_access.BLOCKED and marker and marker != "200 with a non-JSON body":
            evidence["blockMarker"] = marker
            return {"category": HTTP_403_SEC_BLOCK, "evidence": evidence}
    if status == 200:
        category = HTTP_200_VALID if payload_ok else HTTP_200_INVALID
        return {"category": category, "evidence": evidence}
    if status == 401:
        category = HTTP_401
    elif status == 402:
        category = HTTP_402_PLAN
    elif status == 403:
        category = HTTP_403_SEC_BLOCK if host_kind == "sec" else HTTP_403_OTHER
    elif status == 429:
        category = HTTP_429
    else:
        category = HTTP_OTHER
    lowered = head.lower()
    if host_kind != "sec" and any(word in lowered for word in ENTITLEMENT_WORDS):
        evidence["entitlementSentence"] = vendor_sentence(head)
    elif host_kind != "sec" and head.strip():
        evidence["vendorSentence"] = vendor_sentence(head)
    return {"category": category, "evidence": evidence}


def vendor_sentence(text: str, limit: int = 240) -> str:
    """The vendor's own words, kept (a refusal body is evidence), trimmed, and never allowed to carry a credential-shaped token."""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            for key in ("error", "message", "Error Message", "detail", "status"):
                if parsed.get(key):
                    text = str(parsed[key])
                    break
    except ValueError:
        pass
    text = re.sub(r"(?i)(apikey|api_key|token|authorization)[=:\"' ]+[A-Za-z0-9_\-]{8,}", r"\1=<redacted>", text)
    return " ".join(text.split())[:limit]


# ---- observations ------------------------------------------------------------------------------------------------------------------------
def observation(source: str, **fields: Any) -> dict:
    base = {"source": source, "cik": None, "ticker": None, "periodEnd": None, "accession": None, "filedDate": None, "acceptedAt": None,
            "totalAssets": None, "unit": None, "currency": None, "form": None, "fiscalYear": None, "fiscalPeriod": None,
            "filingDateSemantics": "STATED_OR_ABSENT"}
    base.update(fields)
    base["cik"] = normalize_cik(base["cik"])
    base["accession"] = normalize_accession(base["accession"])
    return base


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def read_sec_company_concept(payload: Any) -> dict:
    """`/api/xbrl/companyconcept/CIK##########/us-gaap/Assets.json`: every fact with its own accession, form and filing date."""
    if not isinstance(payload, dict):
        return {"valid": False, "reason": "NOT_AN_OBJECT", "observations": []}
    units = payload.get("units")
    usd = units.get("USD") if isinstance(units, dict) else None
    if payload.get("tag") != "Assets" or payload.get("taxonomy") != "us-gaap" or not isinstance(usd, list):
        return {"valid": False, "reason": "NOT_US_GAAP_ASSETS_USD", "observations": [],
                "keysSeen": sorted(payload)[:12]}
    out, bad = [], 0
    for fact in usd:
        if not isinstance(fact, dict) or not all(k in fact for k in ("end", "val", "accn", "form", "filed")) or _number(fact.get("val")) is None:
            bad += 1
            continue
        out.append(observation("sec_companyconcept", cik=payload.get("cik"), periodEnd=str(fact["end"])[:10], accession=fact["accn"],
                               filedDate=str(fact["filed"])[:10], totalAssets=_number(fact["val"]), unit="USD", currency="USD",
                               form=fact.get("form"), fiscalYear=fact.get("fy"), fiscalPeriod=fact.get("fp"),
                               filingDateSemantics="FILING_DATE_OF_THE_ACCESSION"))
    return {"valid": bool(out), "reason": None if out else "NO_USABLE_FACT", "observations": out, "malformedFacts": bad,
            "entity": payload.get("entityName")}


def read_sec_company_facts(payload: Any) -> dict:
    """`/api/xbrl/companyfacts/CIK##########.json`: the same facts, one document per company; only us-gaap/Assets is read."""
    if not isinstance(payload, dict) or not isinstance(payload.get("facts"), dict):
        return {"valid": False, "reason": "NOT_COMPANY_FACTS", "observations": []}
    assets = (payload["facts"].get("us-gaap") or {}).get("Assets")
    if not isinstance(assets, dict):
        return {"valid": False, "reason": "NO_US_GAAP_ASSETS", "observations": [], "taxonomies": sorted(payload["facts"])[:6]}
    return read_sec_company_concept({"cik": payload.get("cik"), "taxonomy": "us-gaap", "tag": "Assets", "units": assets.get("units"),
                                     "entityName": payload.get("entityName")})


def read_sec_ticker_file(payload: Any) -> dict:
    """`www.sec.gov/files/company_tickers.json`: a small public resource. It proves reachability and nothing about Assets."""
    if not isinstance(payload, dict) or len(payload) < 1000:
        return {"valid": False, "reason": "TOO_SMALL_OR_NOT_AN_OBJECT", "observations": []}
    sample = next(iter(payload.values()))
    if not isinstance(sample, dict) or not {"cik_str", "ticker", "title"} <= set(sample):
        return {"valid": False, "reason": "ROW_SHAPE", "observations": []}
    return {"valid": True, "reason": None, "observations": [], "rows": len(payload)}


# Candidate field names, never asserted: the probe reports which one answered (`fieldsSeen`), as every vendor probe in this repository does.
FINNHUB_VALUE_KEYS = ("totalAssets", "TotalAssets", "assets", "Assets", "total_assets")
FINNHUB_ACCESSION_KEYS = ("accessNumber", "accessionNumber", "accession", "accn")
FINNHUB_FILED_KEYS = ("filedDate", "filingDate", "filed")
FINNHUB_ACCEPTED_KEYS = ("acceptedDate", "acceptanceDateTime")


def read_finnhub_standardized(payload: Any, ticker: str | None = None) -> dict:
    """`/stock/financials?statement=bs&freq=quarterly`. The documented response is standardized and, per the vendor's own page, premium."""
    if not isinstance(payload, dict):
        return {"valid": False, "reason": "NOT_AN_OBJECT", "observations": [], "fieldsSeen": []}
    rows = payload.get("data") if isinstance(payload.get("data"), list) else payload.get("financials")
    if not isinstance(rows, list):
        return {"valid": False, "reason": "NO_DATA_LIST", "observations": [], "fieldsSeen": sorted(payload)[:12],
                "vendorMessage": vendor_sentence(json.dumps(payload))[:240] if payload.get("error") else None}
    fields_seen: set[str] = set()
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        fields_seen.update(str(k) for k in row)
        value, unit, label_used = None, None, None
        for key in FINNHUB_VALUE_KEYS:
            if _number(row.get(key)) is not None:
                value, label_used = _number(row[key]), key
                break
        if value is None and isinstance(row.get("v"), list):
            for entry in row["v"]:
                if not isinstance(entry, dict):
                    continue
                concept = str(entry.get("concept") or "").lower().replace("us-gaap_", "").replace("us-gaap:", "")
                label = str(entry.get("label") or "").strip().lower()
                if concept in ("assets", "totalassets") or label in ("total assets", "assets, total"):
                    value, unit, label_used = _number(entry.get("value")), entry.get("unit"), f"v[{entry.get('concept') or entry.get('label')}]"
                    break
        first = lambda keys: next((row[k] for k in keys if row.get(k) not in (None, "")), None)  # noqa: E731
        out.append(observation("finnhub_standardized", cik=row.get("cik") or payload.get("cik"), ticker=ticker or payload.get("symbol"),
                               periodEnd=str(row.get("period") or row.get("endDate") or "")[:10] or None, accession=first(FINNHUB_ACCESSION_KEYS),
                               filedDate=(str(first(FINNHUB_FILED_KEYS))[:10] if first(FINNHUB_FILED_KEYS) else None),
                               acceptedAt=first(FINNHUB_ACCEPTED_KEYS), totalAssets=value, unit=(unit or None), currency=row.get("currency"),
                               form=row.get("form"), fiscalYear=row.get("year"), fiscalPeriod=row.get("quarter"), fieldUsed=label_used))
    return {"valid": any(o["totalAssets"] is not None for o in out), "reason": None if any(o["totalAssets"] is not None for o in out) else "NO_TOTAL_ASSETS_FIELD",
            "observations": out, "fieldsSeen": sorted(fields_seen)[:30]}


def read_massive_balance_sheets(payload: Any) -> dict:
    """`/stocks/financials/v1/balance-sheets` (the v1 endpoint; the old `/vX/reference/financials` was sunset in June 2026 and is never used)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return {"valid": False, "reason": "NO_RESULTS_LIST", "observations": [], "fieldsSeen": sorted(payload)[:12] if isinstance(payload, dict) else [],
                "vendorMessage": vendor_sentence(json.dumps(payload))[:240] if isinstance(payload, dict) and (payload.get("error") or payload.get("message")) else None}
    fields_seen: set[str] = set()
    out = []
    for row in payload["results"]:
        if not isinstance(row, dict):
            continue
        fields_seen.update(str(k) for k in row)
        tickers = row.get("tickers") if isinstance(row.get("tickers"), list) else []
        out.append(observation("massive_balance_sheets", cik=row.get("cik"), ticker=(tickers[0] if tickers else row.get("ticker")),
                               periodEnd=str(row.get("period_end") or "")[:10] or None,
                               accession=row.get("accession_number") or row.get("accession") or row.get("accn"),
                               filedDate=str(row.get("filing_date") or "")[:10] or None, totalAssets=_number(row.get("total_assets")),
                               unit=None, currency=row.get("currency") or row.get("reported_currency"), form=row.get("form"),
                               fiscalYear=row.get("fiscal_year"), fiscalPeriod=row.get("fiscal_quarter"), timeframe=row.get("timeframe"),
                               # Secondary documentation (ml4t/data#61, Massive's knowledge base): `filing_date` is the LATEST filing that included the
                               # period, so it is a visibility date only for the first filing of that period. Carried as a property of the source and
                               # confirmed or refuted by the live comparison against the stored accession's filed date.
                               filingDateSemantics="DOCUMENTED_LATEST_FILING_INCLUDING_PERIOD"))
    ok = any(o["totalAssets"] is not None for o in out)
    return {"valid": ok, "reason": None if ok else "NO_TOTAL_ASSETS_FIELD", "observations": out, "fieldsSeen": sorted(fields_seen)[:60],
            "nextUrlPresent": bool(payload.get("next_url"))}


def read_fmp_balance_sheet(payload: Any, symbol: str | None = None) -> dict:
    """`/stable/balance-sheet-statement`: carries `filingDate`, `acceptedDate`, `cik` and a SEC link from which the accession can be read."""
    if not isinstance(payload, list):
        message = vendor_sentence(json.dumps(payload)) if isinstance(payload, dict) else None
        return {"valid": False, "reason": "NOT_A_LIST", "observations": [], "fieldsSeen": [], "vendorMessage": message}
    fields_seen: set[str] = set()
    out = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        fields_seen.update(str(k) for k in row)
        link = row.get("finalLink") or row.get("link")
        out.append(observation("fmp_balance_sheet", cik=row.get("cik"), ticker=row.get("symbol") or symbol, periodEnd=str(row.get("date") or "")[:10] or None,
                               accession=normalize_accession(link), filedDate=str(row.get("filingDate") or "")[:10] or None,
                               acceptedAt=row.get("acceptedDate"), totalAssets=_number(row.get("totalAssets")), unit=None,
                               currency=row.get("reportedCurrency"), form=None, fiscalYear=row.get("fiscalYear"), fiscalPeriod=row.get("period"),
                               filingDateSemantics="STATED_OR_ABSENT"))
    ok = any(o["totalAssets"] is not None for o in out)
    return {"valid": ok, "reason": None if ok else "NO_TOTAL_ASSETS_FIELD", "observations": out, "fieldsSeen": sorted(fields_seen)[:40]}


# ---- the data contract, one sample filing against one source's observations --------------------------------------------------------------
def identity_of(sample: dict, obs: dict) -> str:
    s_acc, o_acc = normalize_accession(sample.get("accession")), obs.get("accession")
    s_cik, o_cik = normalize_cik(sample.get("cik")), obs.get("cik")
    if o_acc:
        if o_acc == s_acc and (o_cik is None or o_cik == s_cik):
            return EXACT_ACCESSION
        return REJECTED_IDENTITY
    if o_cik and o_cik == s_cik and obs.get("periodEnd") == sample.get("periodEnd"):
        return WEAK_CIK_PERIOD_END
    return REJECTED_IDENTITY


def candidates_for(sample: dict, observations: list[dict]) -> list[dict]:
    """Observations that could be this filing: same accession, else same CIK and period end. Never a ticker-only or period-only match."""
    ranked = []
    for obs in observations:
        strength = identity_of(sample, obs)
        if strength != REJECTED_IDENTITY:
            ranked.append((0 if strength == EXACT_ACCESSION else 1, obs, strength))
    ranked.sort(key=lambda item: (item[0], str(item[1].get("filedDate") or "")))
    return [{"strength": s, "observation": o} for _, o, s in ranked]


def check_filing(sample: dict, observations: list[dict], observed_at: str) -> dict:
    """The nine items the data contract asks for, for one stored filing and everything one source returned about it."""
    matches = candidates_for(sample, observations)
    result: dict[str, Any] = {"filingId": sample.get("id"), "group": sample.get("group"), "ticker": sample.get("ticker"),
                              "storedAccession": normalize_accession(sample.get("accession")), "observedAt": observed_at}
    if not matches:
        result.update({"identity": REJECTED_IDENTITY, "pit": PIT_NO_MATCH, "usableAsOriginalAtFilingDate": False, "reasons": ["NO_OBSERVATION_JOINS_BY_ACCESSION_OR_CIK_AND_PERIOD_END"]})
        return result
    best = matches[0]
    obs, strength = best["observation"], best["strength"]
    reasons: list[str] = []
    stored_filed, obs_filed = to_date(sample.get("availableFrom")), to_date(obs.get("filedDate"))
    stored_assets = sample.get("storedAssets")
    value_match = None
    if stored_assets is not None and obs.get("totalAssets") is not None:
        value_match = abs(float(stored_assets) - float(obs["totalAssets"])) <= max(1.0, abs(float(stored_assets)) * 1e-9)
    if strength == EXACT_ACCESSION:
        if obs_filed is None:
            pit = PIT_NO_FILING_DATE
        elif stored_filed is not None and obs_filed != stored_filed:
            pit = PIT_DATE_CONFLICT
            reasons.append(f"filed {obs_filed.isoformat()} vs stored {stored_filed.isoformat()}")
        else:
            pit = PIT_PROVEN
    else:
        pit = PIT_NO_ACCESSION
        if obs_filed is not None and stored_filed is not None and obs_filed != stored_filed:
            pit = PIT_NOT_ORIGINAL
            reasons.append(f"vendor filing date {obs_filed.isoformat()} vs stored {stored_filed.isoformat()}")
        reasons.append("A VALUE WITHOUT AN ACCESSION CANNOT BE SHOWN TO BE THE ORIGINAL FILING'S")
    distinct = {o["accession"] for o in observations if o.get("periodEnd") == sample.get("periodEnd") and o.get("accession")}
    result.update({
        "identity": strength,
        "cikMatches": (obs.get("cik") == normalize_cik(sample.get("cik"))) if obs.get("cik") else None,
        "periodEndMatches": obs.get("periodEnd") == sample.get("periodEnd"),
        "accessionStated": obs.get("accession") is not None,
        "filedDateStated": obs.get("filedDate") is not None,
        "filedDateEqualsStored": (obs_filed == stored_filed) if obs_filed and stored_filed else None,
        "totalAssetsStated": obs.get("totalAssets") is not None,
        "unitStated": obs.get("unit") is not None, "currencyStated": obs.get("currency") is not None,
        "valueEqualsStoredReported": value_match,
        "provenanceFields": sorted(k for k in ("accession", "filedDate", "acceptedAt", "form", "fiscalYear", "fiscalPeriod") if obs.get(k) not in (None, "")),
        "correctionsDistinguishable": len(distinct) > 1 or strength == EXACT_ACCESSION,
        "distinctAccessionsForPeriodEnd": len(distinct),
        "filingDateSemantics": obs.get("filingDateSemantics"),
        "pit": pit, "usableAsOriginalAtFilingDate": pit == PIT_PROVEN, "reasons": reasons,
        "totalAssets": obs.get("totalAssets"), "periodEnd": obs.get("periodEnd"), "filedDate": obs.get("filedDate"),
    })
    return result


def visible_at(check: dict, signal_date: str) -> bool:
    """May this value be used at `signal_date`? Only through its own accession's filing date; `observedAt` never counts."""
    filed, signal = to_date(check.get("filedDate")), to_date(signal_date)
    return bool(check.get("usableAsOriginalAtFilingDate") and filed and signal and filed <= signal)


def summarize_source(checks: list[dict]) -> dict:
    """Counts only. A source's verdict is read from these by `decision`, never from the number of rows it returned."""
    total = len(checks)
    by_group: dict[str, dict[str, int]] = {}
    for check in checks:
        bucket = by_group.setdefault(str(check.get("group")), {"filings": 0, "matched": 0, "exactAccession": 0, "pitProven": 0, "valueEqualsStored": 0, "valueCompared": 0})
        bucket["filings"] += 1
        bucket["matched"] += int(check.get("pit") != PIT_NO_MATCH)
        bucket["exactAccession"] += int(check.get("identity") == EXACT_ACCESSION)
        bucket["pitProven"] += int(bool(check.get("usableAsOriginalAtFilingDate")))
        if check.get("valueEqualsStoredReported") is not None:
            bucket["valueCompared"] += 1
            bucket["valueEqualsStored"] += int(bool(check["valueEqualsStoredReported"]))
    return {"filings": total, "byGroup": by_group,
            "matched": sum(b["matched"] for b in by_group.values()), "exactAccession": sum(b["exactAccession"] for b in by_group.values()),
            "pitProven": sum(b["pitProven"] for b in by_group.values())}
