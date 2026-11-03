"""Strict publication-aware adapters around the existing industry foundation.

This module loads no prices and executes no historical return research. SEC
classification is issuer-level evidence, never an inferred share-class join.
The optional return diagnostic delegates to the existing synthetic-only engine.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import math
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pipeline import industry_foundation as F
from pipeline import kr_industry_membership_v3 as KIND

SOURCE_BASE = "37f8cbf6b1c066f6b3c65235953648d17ebf2f69"
PINNED_INPUT_SHA256 = {
    "data/kr-industry-membership-foundation-v3/state/events.json.gz": "ab5f85e5130eb1eb95ce0756069ece78798c76acac115db1f51b903965fd0f64",
    "data/kr-industry-membership-foundation-v3/events-rev4/manifest.json": "882120001bf4ee7711931ff4f60b1f1e7ff7fd23a17e5b3e1df1a95cf72d3777",
    "data/kr-industry-membership-foundation-v1/top120-inputs.json": "d7c464973ad029bf08886c4bdf2517d1b3ece04cce87bcc63706f1230ed53cd0",
    "data/kr-industry-membership-foundation-v3/state/audit.json.gz": "8ad466de34144d7e9863798bd43cd42b192ec92e00fcfd80c0cbaf9b4ddd6104",
    "data/kr-industry-membership-foundation-v4/state/audit.json.gz": "4135846f16dcf59fe4ff89ab83b3b5aec288dea20fed36172b17abf768d44036",
    "research_specs/kr-industry-membership-foundation-v2/criteria.json": "fcf7da7207d2e1c666895743b93d21fb3d50c64002c60ad5f9ebffc0361acf6a",
    "research_specs/kr-industry-membership-foundation-v4/protocol.json": "955fb27793ce8016755b3d0c2e68ec292cad19c9ec84334a50c21d95f9b2d0ce",
}


def _pinned(root, relative):
    return _verified((root / relative).read_bytes(), PINNED_INPUT_SHA256[relative])


def _verified(raw: bytes, expected: str) -> bytes:
    if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("INDUSTRY_SOURCE_MISSING_OR_CHANGED")
    return raw


@dataclass(frozen=True)
class SECIssuerIndustry:
    cik: str
    sic: str
    accession: str
    accepted_at_utc: str
    filed_on: str
    source_sha256: str
    source_url: str
    taxonomy: str = "SEC_REPORTED_SIC_4_DIGIT"
    taxonomy_edition: str = "UNVERIFIED"
    effective_change_date: None = None

    def __post_init__(self):
        if (not re.fullmatch(r"\d{10}", self.cik)
                or not re.fullmatch(r"\d{4}", self.sic)
                or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", self.accession)
                or not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256)):
            raise ValueError("INVALID_SEC_INDUSTRY_IDENTITY")
        F.day(self.filed_on)
        stamp = datetime.fromisoformat(self.accepted_at_utc)
        if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
            raise ValueError("UTC_ACCEPTANCE_REQUIRED")
        if stamp.astimezone(ZoneInfo("America/New_York")).date().isoformat() > self.filed_on:
            raise ValueError("ACCEPTANCE_AFTER_FILING_DATE")
        if (self.taxonomy != "SEC_REPORTED_SIC_4_DIGIT" or self.taxonomy_edition != "UNVERIFIED"
                or self.effective_change_date is not None):
            raise ValueError("SIC_EDITION_OR_CHANGE_DATE_NOT_ESTABLISHED")
        url = urlsplit(self.source_url)
        match = re.fullmatch(r"/Archives/edgar/data/(\d+)/(\d{18})/([^/]+)", url.path)
        if (url.scheme != "https" or url.netloc != "www.sec.gov" or url.query or url.fragment
                or match is None):
            raise ValueError("SEC_ARCHIVE_SOURCE_REQUIRED")
        if (int(match[1]) != int(self.cik) or match[2] != self.accession.replace("-", "")
                or match[3] not in {self.accession + ".hdr.sgml", self.accession + ".txt"}):
            raise ValueError("SEC_ARCHIVE_CITATION_IDENTITY_MISMATCH")


def parse_sec_header(raw: bytes, *, expected_sha256: str, source_url: str) -> SECIssuerIndustry:
    """Read a single-filer SEC SGML header; reject subject-company ambiguity.

    Both modern tagged .hdr.sgml and legacy complete-submission headers work.
    SIC is the issuer's reported SIC at this filing, not GICS or an effective-
    change history. Acceptance is Eastern wall time (DST aware), not UTC.
    """
    text = _verified(raw, expected_sha256).decode("ascii")
    filers = re.findall(r"<FILER>(.*?)</FILER>", text, re.S | re.I)
    if filers:
        if len(filers) != 1:
            raise ValueError("AMBIGUOUS_SEC_FILERS")
        body = filers[0]
    else:
        legacy = re.findall(r"(?m)^FILER:\s*$(.*?)(?=^\S|\Z)", text, re.S | re.M)
        if len(legacy) != 1:
            raise ValueError("EXACT_SEC_FILER_REQUIRED")
        body = legacy[0]

    def one(pattern, source=text):
        values = re.findall(pattern, source, re.I | re.M)
        if len(values) != 1:
            raise ValueError("UNIQUE_SEC_HEADER_FIELD_REQUIRED")
        return values[0]

    cik = one(r"(?:<CIK>|CENTRAL INDEX KEY:\s*)(\d{1,10})(?:\s|$)", body).zfill(10)
    sic = one(r"(?:<ASSIGNED-SIC>(\d{4})|STANDARD INDUSTRIAL CLASSIFICATION:[^\n]*\[(\d{4})\])", body)
    if isinstance(sic, tuple):
        sic = next(value for value in sic if value)
    acceptance = one(r"<ACCEPTANCE-DATETIME>(\d{14})(?:\s|$)")
    accepted = datetime.strptime(acceptance, "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo("America/New_York"))
    filed = one(r"(?:<FILING-DATE>|FILED AS OF DATE:\s*)(\d{8})(?:\s|$)")
    accession = one(r"(?:<ACCESSION-NUMBER>|ACCESSION NUMBER:\s*)(\d{10}-\d{2}-\d{6})(?:\s|$)")
    return SECIssuerIndustry(cik, sic, accession, accepted.astimezone(timezone.utc).isoformat(),
                            datetime.strptime(filed, "%Y%m%d").date().isoformat(), expected_sha256, source_url)


def sec_issuer_at(facts, cik: str, signal_date: str):
    """Last disclosed issuer fact, usable after its conservative filing date.

    A date-only query never uses a filing on its filing date. No security-level
    membership is produced: a separately dated, evidence-backed CIK/security/
    share-class link and termination boundaries are still required.
    """
    F.day(signal_date)
    if not re.fullmatch(r"\d{10}", cik):
        raise ValueError("CANONICAL_CIK_REQUIRED")
    visible = [fact for fact in facts if fact.cik == cik and fact.filed_on < signal_date]
    if not visible:
        return None
    latest = max(fact.accepted_at_utc for fact in visible)
    cohort = [fact for fact in visible if fact.accepted_at_utc == latest]
    if len({fact.sic for fact in cohort}) != 1:
        raise ValueError("CONFLICTING_PUBLIC_SEC_SIC")
    return min(cohort, key=lambda fact: fact.accession)


def kind_dated_memberships(events, sources):
    """Forward public-state observations from verified KIND bodies and listings.

    No current anchor or absence-of-change inference is accepted. Each event
    requires three retained hashes: listing, document, identity viewer. Only
    the stated AFTER label is admitted after both publication and effectiveness.
    The first event supplies no prior history. A delayed filing never rewrites
    earlier signals. Literal labels deliberately assert no KSIC edition.
    """
    by_security, listing_cache = defaultdict(list), {}
    for event in events:
        for field in ("document_sha256", "viewer_sha256", "listing_sha256"):
            _verified(sources.get(event.get(field)), event.get(field))
        listing_sha = event["listing_sha256"]
        if listing_sha not in listing_cache:
            listing_cache[listing_sha] = KIND.parse_kind_listing(sources[listing_sha])
        listing = listing_cache[listing_sha]
        rows = [row for row in listing["rows"] if row["receipt_no"] == event["receipt_no"]]
        if listing["status"] != "PARSED" or len(rows) != 1 or rows[0]["time"][:10] != event["notice_date"]:
            raise ValueError("KIND_PUBLICATION_UNPROVEN")
        parsed = KIND.parse_notice(KIND.decode(sources[event["document_sha256"]])[0],
                                   KIND.decode(sources[event["viewer_sha256"]])[0])
        if (parsed["status"] != "PARSED" or event.get("status") != "PARSED"
                or any(parsed[key] != event.get(key) for key in ("before_label", "after_label", "effective_date"))
                or parsed["identity"]["stock_code"] != event["ticker"].split(".")[0]):
            raise ValueError("KIND_STATED_ASSIGNMENT_OR_IDENTITY_CHANGED")
        F.day(event["notice_date"])
        F.day(event["effective_date"])
        by_security[event["ticker"]].append(event)
    result = []
    for ticker, records in sorted(by_security.items()):
        records.sort(key=lambda event: (event["notice_date"], event["effective_date"], event["receipt_no"]))
        if len({event["notice_date"] for event in records}) != len(records):
            raise ValueError("AMBIGUOUS_SAME_DAY_KIND_ASSIGNMENTS")
        for index, event in enumerate(records):
            known_to = None
            if index + 1 < len(records):
                successor = records[index + 1]
                if (event["after_label"] != successor["before_label"]
                        or event["effective_date"] >= successor["effective_date"]):
                    raise ValueError("KIND_PUBLIC_STATE_CHAIN_CONFLICT")
                last_old_day = (date.fromisoformat(successor["effective_date"]) - timedelta(days=1)).isoformat()
                known_to = max(successor["notice_date"], last_old_day)
            release = event["notice_date"]
            result.append(F.Membership(
                security_id="KRX:" + ticker, ticker=ticker, region="KR", taxonomy_id="KIND_LITERAL",
                taxonomy_version="REPORTED_UNVERSIONED", industry_id="KIND:" + "".join(event["after_label"].split()),
                valid_from=event["effective_date"], valid_to=None, source_date=release, release_date=release,
                known_to=known_to, source=event["document_url"], source_sha256=event["document_sha256"],
                evidence_kind="DATED_ASSIGNMENT",
                identity_provenance=F.digest({"viewer": event["viewer_sha256"], "listing": listing_sha,
                                              "receipt": event["receipt_no"], "statedTicker": ticker})))
    return tuple(result)


def load_retained_kind(root):
    """Verify existing retained classification bytes without copying the dataset.

    Returns strict forward observations and a compact source audit. This does
    not revise v1-v4 audits, choose a taxonomy, or calculate a price outcome.
    """
    import gzip
    import json
    from pathlib import Path

    root = Path(root)
    base = root / "data/kr-industry-membership-foundation-v3"
    event_path = base / "state/events.json.gz"
    event_raw = _pinned(root, "data/kr-industry-membership-foundation-v3/state/events.json.gz")
    events = json.loads(gzip.decompress(event_raw))
    sources, receipt_sources = {}, {}
    manifest = json.loads(_pinned(root, "data/kr-industry-membership-foundation-v3/events-rev4/manifest.json"))
    for recorded in manifest["results"]:
        source_sha = recorded["sha256"]
        path = base / "events-rev4" / (source_sha + ".bin")
        raw = _verified(path.read_bytes(), source_sha)
        listing = KIND.parse_kind_listing(raw)
        if listing["status"] != "PARSED":
            continue
        sources[source_sha] = raw
        for row in listing["rows"]:
            if row["receipt_no"] in receipt_sources:
                raise ValueError("DUPLICATE_RETAINED_KIND_RECEIPT")
            receipt_sources[row["receipt_no"]] = source_sha
    evidence = []
    enriched = []
    for event in events:
        if event["receipt_no"] not in receipt_sources:
            raise ValueError("RETAINED_KIND_LISTING_MISSING")
        copy = dict(event, listing_sha256=receipt_sources[event["receipt_no"]])
        for field in ("document_sha256", "viewer_sha256"):
            sha = event[field]
            sources[sha] = _verified((base / "notices" / (sha + ".bin")).read_bytes(), sha)
        enriched.append(copy)
        evidence.append({key: copy[key] for key in ("receipt_no", "ticker", "notice_date", "effective_date",
                                                    "document_sha256", "viewer_sha256", "listing_sha256")})
    memberships = kind_dated_memberships(enriched, sources)
    return memberships, {"status": "PARTIAL", "inputPath": str(event_path.relative_to(root)),
                         "inputSha256": hashlib.sha256(event_raw).hexdigest(),
                         "verifiedNoticeCount": len(memberships), "securities": len({row.security_id for row in memberships}),
                         "publicationPolicy": "NEXT_CALENDAR_DAY_AND_NOT_BEFORE_STATED_EFFECTIVE_DATE",
                         "admittedPriorHistoryBeforeFirstNotice": False, "currentAnchorsAdmitted": False,
                         "taxonomyEditionVerified": False, "historicalOutcomeComputed": False, "notices": evidence}


def build_industry_source_audit(root):
    """Reproduce source coverage and prior decisions; never read return data."""
    import gzip
    import json
    from pathlib import Path

    from pipeline.kr_industry_membership import top120_schedule

    root = Path(root)
    memberships, admitted = load_retained_kind(root)
    paths = ["data/kr-industry-membership-foundation-v3/state/audit.json.gz",
             "data/kr-industry-membership-foundation-v4/state/audit.json.gz",
             "data/kr-industry-membership-foundation-v1/top120-inputs.json",
             "research_specs/kr-industry-membership-foundation-v4/protocol.json",
             "research_specs/kr-industry-membership-foundation-v2/criteria.json"]
    hashes, objects = {}, {}
    for path in paths:
        raw = _pinned(root, path)
        hashes[path] = hashlib.sha256(raw).hexdigest()
        objects[path] = json.loads(gzip.decompress(raw) if path.endswith(".gz") else raw)
    v3, v4, top120, protocol, criteria = [objects[path] for path in paths]
    schedule, _ = top120_schedule(top120)
    covered = F.coverage_audit(memberships, schedule, region="KR", taxonomy_id="KIND_LITERAL",
                               taxonomy_version="REPORTED_UNVERSIONED")
    classified = sum(row["classifiedCount"] for row in covered["dates"])
    denominator = sum(row["universeCount"] for row in covered["dates"])
    terminal_ids = {"KRX:" + name for name in protocol["absentSecurities"]["terminal22"]}
    terminal_denominator = sum(len(set(names) & terminal_ids) for names in schedule.values())
    terminal_observations = len({row.security_id for row in memberships} & terminal_ids)
    minimum_size = criteria["minimumGroupSize"]
    deficient_dates = sum(
        row["classifiedCount"] == 0
        or sum(count for count in row["groupCounts"].values() if count >= minimum_size) / row["classifiedCount"]
        < criteria["minimumFractionInSufficientGroups"] for row in covered["dates"])
    return {"version": "cross-market-industry-foundation-v1", "sourceBaseCommit": SOURCE_BASE,
            "status": "PARTIAL", "sourceInputHashes": hashes,
            "priorDecisionsUnchanged": {"v3": v3["decision"], "v4": v4["decision"]},
            "reconstructedV4": {"classifiedNameDates": v4["classifiedNameDates"], "nameDates": v4["nameDates"],
                                "coveragePct": v4["classifiedPct"], "terminalCoveragePct": v4["terminalCoveragePct"],
                                "datesBelowGroupFractionGate": v4["fractionInSufficientGroups"]["datesBelowThreshold"],
                                "inferenceOnlyNameDatesV3": v3["nameDateStatus"]["RECONSTRUCTED_STABLE_NO_CHANGE_EVENT"],
                                "oldAuditPitKnownEventNameDates": v3["pitKnownEventNameDates"],
                                "notAnExactPitCoverageRate": True},
            "strictLastPublicObservationInput": {
                "dates": len(schedule), "nameDates": denominator, "classifiedNameDates": classified,
                "classificationCoveragePct": 100 * classified / denominator,
                "minimumSignalCoveragePct": 100 * min(row["coverageFraction"] for row in covered["dates"]),
                "maximumSignalCoveragePct": 100 * max(row["coverageFraction"] for row in covered["dates"]),
                "uniqueScheduledSecurities": len(set(name for names in schedule.values() for name in names)),
                "terminalNameDates": terminal_denominator, "terminalSecuritiesWithObservation": terminal_observations,
                "datesBelowGroupFractionGate": deficient_dates,
                "notPitExact": "Scoped name-discovery may miss filings; last-public observations do not prove unchanged economic classification.",
                "empiricalReadiness": "SOURCE_BLOCKED"},
            "terminal22": {name: v4["absent28"]["perSecurity"][name]
                           for name in protocol["absentSecurities"]["terminal22"]}, "kindAdmission": admitted,
            "blockers": ["KR_TERMINAL_22_CLASSIFICATION_UNRESOLVED", "KR_CLASSIFICATION_COVERAGE_INSUFFICIENT",
                         "KR_MINIMUM_GROUP_SIZE_INSUFFICIENT", "CLASSIFICATION_TAXONOMY_EDITION_UNVERIFIED",
                         "US_SECURITY_SHARE_CLASS_PIT_LINK_NOT_ADMITTED", "US_HISTORICAL_SIC_PANEL_MISSING"],
            "historicalOutcomeComputed": False}


@dataclass(frozen=True)
class Investability:
    available: bool | None
    observed_on: str
    released_on: str
    source_sha256: str
    valid_through: str
    validity_source_sha256: str
    terminated_on: str | None = None

    def usable(self, signal_date):
        return (self.available is True and F.day(self.observed_on) <= F.day(self.released_on) < signal_date
                and signal_date <= F.day(self.valid_through)
                and (self.terminated_on is None or signal_date < F.day(self.terminated_on))
                and all(bool(re.fullmatch(r"[0-9a-f]{64}", sha))
                        for sha in (self.source_sha256, self.validity_source_sha256)))


def industry_plan(rows, universe, signal_date, *, region, taxonomy_id, taxonomy_version,
                  industry_id, minimum_constituents, weighting, currency,
                  investability, capitalizations=None):
    """Outcome-free cohort, investment eligibility and concentration diagnostics.

    Existing cohort and weighting semantics are reused. Any missing full-
    universe classification or member eligibility blocks the plan; no weights
    escape a blocked result. Leave-largest-out is a diagnostic, not permission
    to delete an inconvenient constituent from the actual research universe.
    """
    cohort = F.freeze_cohort(rows, universe, signal_date, region=region, taxonomy_id=taxonomy_id,
                             taxonomy_version=taxonomy_version, industry_id=industry_id,
                             minimum_constituents=minimum_constituents)
    unknown = [name for name in cohort.security_ids
               if not isinstance(investability.get(name), Investability)
               or not investability[name].usable(signal_date)]
    result = {"status": "SOURCE_BLOCKED", "cohort": asdict(cohort), "weights": None,
              "hhi": None, "effectiveMemberCount": None, "largestRemoval": None,
              "missingInvestability": unknown, "missingCapitalizations": [], "historicalOutcomeComputed": False}
    if not cohort.ready or unknown:
        return result
    # The original foundation owns weighting economics; this adapter adds no
    # alternative missing-cap or renormalisation convention.
    weights, missing = F._weights(cohort, weighting, capitalizations or {}, currency)
    result["missingCapitalizations"] = missing
    if missing:
        return result
    hhi = math.fsum(value * value for value in weights.values())
    largest = min(weights, key=lambda name: (-weights[name], name))
    rest = {name: value for name, value in weights.items() if name != largest}
    denominator = math.fsum(rest.values())
    if denominator <= 0:
        raise ValueError("NO_REMAINING_INDUSTRY_WEIGHT")
    remainder = {name: value / denominator for name, value in rest.items()}
    result.update(status="READY_RESEARCH_INPUT", weights=weights, hhi=hhi, effectiveMemberCount=1 / hhi,
                  largestRemoval={"removedSecurityId": largest, "removedWeight": weights[largest],
                                  "remainingCount": len(rest), "minimumSizeSatisfied": len(rest) >= minimum_constituents,
                                  "hhi": math.fsum(value * value for value in remainder.values())})
    return result


def paired_synthetic_attribution(cohort, observations, subject, market, *, entry_date,
                                 exit_date, currency, regime, regime_observed_on, regime_released_on,
                                 regime_sha256, scope, weighting="EQUAL_WEIGHT", capitalizations=None):
    """Three disjoint arithmetic components with an as-of market regime.

    This is deliberately only the existing synthetic engine plus a stricter
    total-shareholder-return and regime contract, not a new backtest runner.
    """
    if scope != "SYNTHETIC":
        raise ValueError("HISTORICAL_RETURN_EXECUTION_NOT_AUTHORIZED")
    if (not isinstance(regime, str) or not regime.strip()
            or not F.day(regime_observed_on) <= F.day(regime_released_on) < cohort.signal_date
            or not re.fullmatch(r"[0-9a-f]{64}", regime_sha256)):
        raise ValueError("PIT_MARKET_REGIME_REQUIRED")
    basis = "TOTAL_SHAREHOLDER_RETURN"
    industry = F.aggregate_industry(cohort, observations, weighting=weighting, scope=scope,
                                    entry_date=entry_date, exit_date=exit_date, basis=basis,
                                    currency=currency, capitalizations=capitalizations)
    stock = observations.get(subject)
    if stock is None:
        return {"status": "SOURCE_BLOCKED", "components": None}
    result = F.decompose(cohort, subject, stock, industry, market, scope=scope)
    if result["status"] != "READY":
        return {"status": "SOURCE_BLOCKED", "components": None}
    components = result["components"]
    disjoint = {key: components[key] for key in ("market_return", "industry_excess_return", "stock_within_industry_return")}
    return {"status": "SYNTHETIC_ONLY", "scope": scope, "components": disjoint,
            "stockReturn": compose_disjoint_attribution(disjoint), "regime": regime,
            "regimeSourceSha256": regime_sha256,
            "selfInclusion": result["selfInclusion"], "historicalOutcomeComputed": False}


def compose_disjoint_attribution(components):
    if set(components) != {"market_return", "industry_excess_return", "stock_within_industry_return"}:
        raise ValueError("OVERLAPPING_OR_MISSING_ATTRIBUTION_COMPONENTS")
    if any(type(value) not in {int, float} or not math.isfinite(value) for value in components.values()):
        raise ValueError("MEASURABLE_ATTRIBUTION_COMPONENTS_REQUIRED")
    return math.fsum(components.values())
