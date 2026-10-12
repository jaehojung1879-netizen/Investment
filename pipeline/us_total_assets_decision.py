"""The ranking of candidate US total-assets sources, as DATA with the evidence class of every line stated. Nothing here is measured at import.

`evidenceBasis` is one of:
  TESTED_IN_REPOSITORY       a dated run recorded in docs/ (cited)
  DOCUMENTED_SECONDARY       read from vendor/SEC documentation or third-party summaries during authoring; the authoring sandbox cannot reach these hosts
  NOT_TESTED                 nobody has asked the source this question with this key/runner

A route whose accessibility is NOT_TESTED can be RANKED (the ranking is a statement about what is known) but is never described as accessible, and the
recommendation names the exact approval that would test it. `validate` refuses a decision that breaks that.
"""
from __future__ import annotations

CONTRACT = "US_TOTAL_ASSETS_SOURCE_DECISION_V1"
RUN_38250579358 = "Actions run 38250579358: Finnhub financials-reported, 12 requests, VENDOR_OMITS_BALANCE_SHEET_ENDPOINT_WIDE (reported by the owner; not re-read here)"

ROUTES = [
    {
        "id": "A", "name": "SEC direct API (data.sec.gov companyconcept/companyfacts) from a GitHub-hosted runner",
        "testedAccessibility": {
            "status": "BLOCKED_AS_LAST_MEASURED_RETEST_PENDING_OWNER_DISPATCH", "evidenceBasis": "TESTED_IN_REPOSITORY",
            "evidence": ["2026-09-04 egress-address and header-isolation probes: every SEC host, every header set refused",
                         "2026-09-13 four hosts incl. efts.sec.gov and apex: 403, two block pages (4,819 B / 1,925 B)",
                         "2026-09-17 Probes run #8: data.sec.gov submissions, Archives and quarterly ZIPs, 5 of 5 HTTP 403, no redirect, under 0.4 s"],
            "thisPullRequest": "NOT_RUN: the gated diagnostic is prepared (region=total-assets-source-probe, probe_sources=sec) and waits for the owner's dispatch on main"},
        "entitlementAndCost": {"entitlement": "none; SEC fair-access policy requires a descriptive User-Agent with a contact the owner supplies; published maximum 10 requests/second",
                               "cost": "free", "evidenceBasis": "DOCUMENTED_SECONDARY"},
        "totalAssetsCoverage": {"claim": "every XBRL filer's us-gaap/Assets with the accession of each filing that stated it, including later filings' comparatives; XBRL since 2009",
                                "measuredForSample": "NOT_TESTED", "evidenceBasis": "DOCUMENTED_SECONDARY"},
        "pitSuitability": {"grade": "BEST", "why": "each fact carries `accn`, `form`, `filed`, `end`: an exact accession join to the stored filing, the filing date of that accession, and the original separable from a later restatement by accession",
                           "limit": "companyconcept gives a filing DATE, not the acceptance timestamp (that is in the submissions document); a same-day after-hours filing is dated by SEC's filing date"},
        "acquisitionAndStorageRestrictions": "public SEC data; declare a User-Agent; stay under the rate limit; no bulk scraping; nothing stored beyond Assets rows keyed by accession",
        "operationalComplexity": "LOW if reachable: about 400 CIK documents cover the 619 recently missing filings; a quarterly top-up is one document per S&P 500 CIK",
        "unresolvedBlocker": "GitHub-hosted runner egress is refused by SEC on every host in three measurements; only a live HTTP 200 with valid data from data.sec.gov on an Actions run clears it"},
    {
        "id": "B", "name": "SEC official bulk Financial Statement Data Sets, fetched on an owner-authorized persistent host",
        "testedAccessibility": {
            "status": "NOT_TESTED_FROM_ANY_NON_ACTIONS_HOST", "evidenceBasis": "NOT_TESTED",
            "evidence": ["from Actions: 2025q2/2013q1 (2026-09-04) and 2026q2/2025q4 (2026-09-17) quarterly ZIPs HTTP 403, 1,925 B block page"],
            "thisPullRequest": "NOT_RUN: no such host is registered with this repository; nothing here can test it"},
        "entitlementAndCost": {"entitlement": "none beyond the same User-Agent policy", "cost": "free data; the host is the owner's own (not priced here)", "evidenceBasis": "DOCUMENTED_SECONDARY"},
        "totalAssetsCoverage": {"claim": "quarterly sub.txt (adsh, cik, period, filed, accepted, form, prevrpt) and num.txt (tag Assets, ddate, qtrs, uom) since 2009; the Assets rows of the stored population are a small extract",
                                "measuredForSample": "NOT_TESTED", "evidenceBasis": "DOCUMENTED_SECONDARY"},
        "pitSuitability": {"grade": "BEST", "why": "adsh is the accession; `filed` and the `accepted` timestamp are stated; `prevrpt` marks a submission that was later amended, so original and correction are separable",
                           "limit": "a quarterly release lags the filings it contains; how long after quarter end the newest quarter appears is unmeasured here and decides whether the newest filings are covered"},
        "acquisitionAndStorageRestrictions": "public SEC data; one ZIP per quarter downloaded once; keep only Assets rows keyed by accession; the ZIPs are not committed",
        "operationalComplexity": "MEDIUM: a host SEC does not block, about 55 quarterly ZIPs for 2013 onward, a small extractor, and a sidecar keyed by accession that never mutates the Finnhub raw shards",
        "unresolvedBlocker": "no host that SEC answers has been designated or tested; release latency for the newest quarter is unmeasured"},
    {
        "id": "C", "name": "Finnhub standardized /stock/financials (statement=bs, freq=quarterly)",
        "testedAccessibility": {
            "status": "NOT_TESTED", "evidenceBasis": "NOT_TESTED",
            "evidence": [RUN_38250579358, "that run asked `financials-reported` only; no alternative balance-sheet or Assets key was found in it"],
            "thisPullRequest": "NOT_RUN: prepared (probe_sources=vendors); the first request doubles as the entitlement check and stops the vendor on 401/402/403"},
        "entitlementAndCost": {"entitlement": "the vendor's page describes the endpoint as premium; whether the repository's FINNHUB key is entitled is unknown", "cost": "plan price not verified here",
                               "evidenceBasis": "DOCUMENTED_SECONDARY"},
        "totalAssetsCoverage": {"claim": "documented as standardized statements for global companies, 30+ years", "measuredForSample": "NOT_TESTED", "evidenceBasis": "DOCUMENTED_SECONDARY"},
        "pitSuitability": {"grade": "WEAK_UNTIL_MEASURED", "why": "the documented response is period-keyed; no accession or filing date is documented for it, so a value joins only by CIK and period end (a WEAK identity) and cannot be shown to be the original filing's",
                           "limit": "it may be derived from the same feed that stopped sending `bs`; the probe records which fields actually arrive (`fieldsSeen`) before any claim is made"},
        "acquisitionAndStorageRestrictions": "vendor licence terms were not read for this task; no value from it may be written into the PIT ledger without an accession join",
        "operationalComplexity": "LOW to call, HIGH to trust: one request per ticker, then a join that the response cannot support by itself",
        "unresolvedBlocker": "entitlement of the existing key; absence of accession and filing date in the documented schema"},
    {
        "id": "D", "name": "Massive /stocks/financials/v1/balance-sheets (the new fundamentals API)",
        "testedAccessibility": {
            "status": "NOT_TESTED", "evidenceBasis": "NOT_TESTED",
            "evidence": ["the sunset /vX/reference/financials endpoint (HTTP 404 since 2026-06-22 per a third-party report) is never used",
                         "2026-09-13 Probes run #2: the MASSIVE key authenticated against the OLD endpoint; that says nothing about the new one"],
            "thisPullRequest": "NOT_RUN: prepared (probe_sources=vendors)"},
        "entitlementAndCost": {"entitlement": "documented as requiring the Financials and Ratios add-on or a Stocks Advanced-or-higher plan; the repository key's plan is unknown",
                               "cost": "paid add-on; price not verified here", "evidenceBasis": "DOCUMENTED_SECONDARY"},
        "totalAssetsCoverage": {"claim": "40 balance-sheet fields including total_assets, quarterly and annual, oldest period ending April 2009", "measuredForSample": "NOT_TESTED", "evidenceBasis": "DOCUMENTED_SECONDARY"},
        "pitSuitability": {"grade": "NOT_PIT_SAFE_AS_DOCUMENTED", "why": "`filing_date` is documented (by a provider integration and the vendor's knowledge base) as the LATEST filing that included the period, so for an old period it is not the date the value first became visible; no accession is documented",
                           "limit": "the probe compares the stated filing date with the stored accession's filed date; agreement on the recent-missing group and disagreement on older periods would confirm it"},
        "acquisitionAndStorageRestrictions": "vendor licence terms were not read for this task",
        "operationalComplexity": "LOW to call; the join cannot be made exact",
        "unresolvedBlocker": "plan entitlement unknown; filing date is not the first-visibility date; no accession"},
    {
        "id": "E", "name": "FMP /stable/balance-sheet-statement (existing key)",
        "testedAccessibility": {
            "status": "REACHABLE_BUT_SHALLOW_AS_LAST_MEASURED", "evidenceBasis": "TESTED_IN_REPOSITORY",
            "evidence": ["2026-09-05 / 2026-09-13: /stable serves statements WITH filingDate; `limit` capped at 5 quarters (earliest period 2025-06); departed names refused on a subscription symbol restriction"],
            "thisPullRequest": "NOT_RUN: prepared (probe_sources=vendors); request 0 is the known-served 5-quarter baseline, request 1 asks the deep window once"},
        "entitlementAndCost": {"entitlement": "the current key; free-tier symbol restriction (a cut universe) was measured on four departed names, and S&P 500 coverage was not", "cost": "current plan; an upgrade price was not verified here",
                               "evidenceBasis": "TESTED_IN_REPOSITORY"},
        "totalAssetsCoverage": {"claim": "about the last five quarters per served symbol, which is exactly the window of the recently missing filings; 2013 history is out of reach on this plan",
                                "measuredForSample": "NOT_TESTED", "evidenceBasis": "TESTED_IN_REPOSITORY"},
        "pitSuitability": {"grade": "MODERATE_IF_LINK_PARSES", "why": "filingDate, acceptedDate and a SEC link are returned; the accession can be read from the link and compared with the stored one, which would make the join exact",
                           "limit": "whether the link carries the accession for every row, and whether a later restatement overwrites the original row, is measured only by the diagnostic"},
        "acquisitionAndStorageRestrictions": "vendor licence terms were not read for this task; the stored sidecar would hold Assets keyed by accession only",
        "operationalComplexity": "LOW for a bounded recent window: one request per ticker, about 500 per quarter",
        "unresolvedBlocker": "history before 2025-06 is unreachable on this plan; S&P 500 symbol coverage on the current plan is unmeasured"},
]

RANKING = ["B", "A", "E", "C", "D"]
RECOMMENDATION = {
    "primary": {"route": "B", "why": "the only route whose number is tied to an accession, a filing date and an original-versus-amended flag by construction, whose cost is the owner's own host rather than a vendor plan, and which does not depend on a vendor keeping a field that has already disappeared once",
                "condition": "an owner-designated host that SEC answers; until one is tested it is a plan, not an accessible source"},
    "fallback": {"route": "E", "why": "already reachable with an existing key, returns filing dates and a SEC link from which the accession can be compared, and its five-quarter window is exactly the window of the 619 missing filings",
                 "condition": "admitted only for filings where the accession read from the link equals the stored accession and the filing date equals the stored one; it cannot recover history and carries no claim about 2013-2025"},
    "optionalUpgrade": {"route": "A", "why": "if the gated diagnostic returns a live HTTP 200 with valid data from data.sec.gov on an Actions run, A becomes primary: same provenance, no host to run"},
}
OWNER_APPROVALS = [
    "Merge this pull request (it changes only fundamentals.yml's dispatch-only inputs and one new read-only job, plus code, tests and documents).",
    "Dispatch Collect fundamentals from main with region=total-assets-source-probe, probe_sources=sec and sec_contact set to an address you monitor: 11 SEC requests, no key. It answers whether the SEC block persists.",
    "Dispatch again with probe_sources=vendors (blank max_calls): at most 8 Finnhub + 8 Massive + 9 FMP requests, one key per step. It answers entitlement and provenance fields.",
    "Decide whether to designate a persistent host for route B, or to run one manual download from your own machine; this pull request builds neither.",
]
NOT_DONE = ["no collection, backfill or schedule", "no write to signal-history or to the Finnhub raw shards", "no alpha, IC or outcome calculation", "frozen H63/P4 results untouched",
            "no live request was made by this change", "the Finnhub financials-reported probe is not repeated"]


def build() -> dict:
    return {"contract": CONTRACT, "routes": ROUTES, "ranking": RANKING, "recommendation": RECOMMENDATION, "ownerApprovals": OWNER_APPROVALS, "notDone": NOT_DONE,
            "criticalQuestion": {"question": "Can we obtain accurate, provenance-backed quarterly total assets for the S&P 500 without losing PIT integrity?",
                                 "answer": "Only from SEC filings keyed by accession; no vendor route has been shown, by test or by its documented schema, to give the original filing's value with its own filing date. "
                                           "Whether SEC can be reached from a machine this repository can run is the unresolved fact, and it is not settled by this change."}}


def validate(decision: dict) -> list[str]:
    problems: list[str] = []
    ids = [r["id"] for r in decision["routes"]]
    if ids != ["A", "B", "C", "D", "E"] or sorted(decision["ranking"]) != sorted(ids):
        problems.append("ROUTES_OR_RANKING_INCOMPLETE")
    required = ("testedAccessibility", "entitlementAndCost", "totalAssetsCoverage", "pitSuitability", "acquisitionAndStorageRestrictions", "operationalComplexity", "unresolvedBlocker")
    for route in decision["routes"]:
        for field in required:
            if not route.get(field):
                problems.append(f"{route['id']}:{field}_MISSING")
        tested = route["testedAccessibility"]
        if tested["evidenceBasis"] == "NOT_TESTED" and not tested["status"].startswith("NOT_TESTED"):
            problems.append(f"{route['id']}:UNTESTED_ROUTE_DESCRIBED_AS_ACCESSIBLE")
        if "NOT_RUN" not in tested.get("thisPullRequest", ""):
            problems.append(f"{route['id']}:A_LIVE_RESULT_IS_CLAIMED_FOR_THIS_PULL_REQUEST")
        if route["totalAssetsCoverage"]["measuredForSample"] != "NOT_TESTED":
            problems.append(f"{route['id']}:SAMPLE_COVERAGE_CLAIMED_WITHOUT_A_RUN")
    rec = decision["recommendation"]
    if rec["primary"]["route"] == rec["fallback"]["route"] or rec["primary"]["route"] not in ids or rec["fallback"]["route"] not in ids:
        problems.append("PRIMARY_AND_FALLBACK_MUST_BE_TWO_DIFFERENT_ROUTES")
    return problems
