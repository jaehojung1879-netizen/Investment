"""ONE immutable candidate economic-experiment readiness packet for the fixed KR C0 structural REENTRY-BASE contrast (#289).

It READS the registered proposal (never retypes it) and records what must be true before an owner could even review the SCOPE of a
historical run. It runs nothing: no C0/C1/arm return, state, signal or replay is computed, no threshold is chosen and no source
right is granted. Every unapproved threshold stays null.

Status vocabulary, decided by `readiness_status`:
  SOURCE_BLOCKED                   at least one SOURCE prerequisite (rights, PIT/vintage, investability, funded-investor reading)
                                   is not VERIFIED. Today's state.
  READY_FOR_OWNER_SCOPE_REVIEW     every source prerequisite is VERIFIED. Unset thresholds and owner criteria may remain null:
                                   scope review is where an owner sets them. It is NOT approval to execute.

Immutability: the packet carries sha256 identities of the code, inputs, registered contract and source evidence it was built
from, plus its own digest. `verify` recomputes every identity from disk. A legitimate change to any listed file means cutting a
NEW packet version, never editing this one; the committed-packet test fails loudly to say so.
"""
from __future__ import annotations

import hashlib
import json

from . import market_research_c1c_contract as CONTRACT
from . import market_research_c1c_source_evidence as EVIDENCE

STUDY = "market-research-c1c-economic-readiness-packet-v3"
ROOT = EVIDENCE.ROOT
OUTPUT = ROOT / "docs" / "research-program" / "proposals" / "market-research-c1c-economic-readiness-packet-v3.json"
EVIDENCE_JSON = "docs/research-program/proposals/market-research-c1c-source-evidence-v1.json"
RESOLUTION_JSON = "docs/research-program/proposals/market-research-c1c-source-resolution-v1.json"
CODE_FILES = (
    "pipeline/market_research_c1c.py", "pipeline/market_research_c1c_contract.py", "pipeline/market_research_c1c_decisions.py",
    "pipeline/market_research_c1c_diagnostics.py", "pipeline/market_research_reentry_structure.py",
    "pipeline/market_research_c1c_source_evidence.py", "pipeline/market_research_c1c_xls_cells.py",
    "pipeline/market_research_c1c_source_resolution.py",
    "docs/research-program/proposals/market-research-c1c-v2.json",
)
SIGNAL_INPUT_FILES = (  # the retained normalized series the frozen state rules read; a future run must re-pin its own inputs
    "data/kr-market-risk-anatomy-v1/sources/FDR_KS200/normalized.csv",
    "data/kr-market-risk-anatomy-v1/sources/FRED_VIXCLS/normalized.csv",
    "data/kr-market-risk-anatomy-v1/sources/FRED_DGS10/normalized.csv",
    "data/kr-market-risk-anatomy-v1/sources/FRED_DGS3MO/normalized.csv",
)
VERIFIED = "VERIFIED"
SUPERSEDES = {
    "packet": "market-research-c1c-economic-readiness-packet-v2",
    "packetSha256": "688a7f65a4b0602046739af672a9fa3d4acb467cc4d0e6030355b3bae439d747", "committedAt": "2cddd6a0eae4b746246393c1259d3dc6798756d1",
    "reason": "adds the source-resolution evidence: the trust-deed payment rule bounds 24 of the 26 unresolved payment lags, the applicable source-use terms "
              "were read for the five inputs, the issuer's retention restriction is reported, and the cash options are recorded. Several statuses are corrected "
              "to what the terms say. The blocker count is unchanged. v2 was never consumed or approved.",
    "earlierVersions": [{"packet": "market-research-c1c-economic-readiness-packet-v1",
                         "packetSha256": "329371a76369efdcaadd5aba2d323b5249b03b94db34ffc3bacc50edb46cff28", "committedAt": "f5d0c51bee514fbba43cbf5a328ba185a4167fa8",
                         "reason": "verify() derived the status from the packet's own prerequisites, so a forged READY packet with a recomputed digest passed"}]}
# The 13 blockers of the previous packet, copied from its committed file, so the before/after comparison is computed and not asserted.
PREVIOUS_BLOCKERS = (
    "KS200 signal index:rights:NOT_RETAINED", "KS200 signal index:pitVintage:NOT_ESTABLISHED", "VIX:rights:NOT_RETAINED", "VIX:pitVintage:NOT_ESTABLISHED",
    "Treasury 10y and 3m:rights:PARTIAL_BOARD_POLICY_CITED_NOT_RETAINED_IN_REPO", "Treasury 10y and 3m:pitVintage:NOT_ESTABLISHED",
    "069500.KS (KODEX 200):rights:NOT_RETAINED", "069500.KS (KODEX 200):pitVintage:PARTIAL", "069500.KS (KODEX 200):investability:NOT_VERIFIED",
    "KRW cash:rights:NOT_RETAINED", "KRW cash:pitVintage:NOT_ESTABLISHED", "KRW cash:investability:MISSING", "F_FUNDED_INVESTOR:BLOCKED")


def blocker_comparison(blockers):
    """Before/after by (input, dimension), computed from the lists: what was removed, what only changed its status, what is new."""
    key = lambda b: b.rsplit(":", 1)[0]
    before, after = {key(b): b for b in PREVIOUS_BLOCKERS}, {key(b): b for b in blockers}
    return {"before": len(before), "after": len(after), "removed": sorted(set(before) - set(after)), "added": sorted(set(after) - set(before)),
            "statusChanged": [{"blocker": k, "before": before[k].rsplit(":", 1)[1], "after": after[k].rsplit(":", 1)[1]}
                              for k in sorted(set(before) & set(after)) if before[k] != after[k]]}


def _identity(rel):
    return {"path": rel, "sha256": EVIDENCE.sha256(ROOT / rel)}


def _need(status, smallest, evidence=None):
    """`evidence` lists {path, sha256} of retained files. A VERIFIED status without it does not count."""
    return {"status": status, "smallestMissingEvidence": smallest, "evidence": list(evidence or [])}


def _has_evidence(entry):
    items = entry.get("evidence")
    return bool(items) and all(isinstance(i, dict) and i.get("path") and len(str(i.get("sha256", ""))) == 64 for i in items)


def _has_owner_decision(entry):
    """A RIGHTS entry is VERIFIED only with a recorded owner decision ({path, sha256}); an observation of the terms is never a grant."""
    record = entry.get("ownerDecision")
    return isinstance(record, dict) and bool(record.get("path")) and len(str(record.get("sha256", ""))) == 64


def prerequisites():
    """Per fixed input: rights, PIT/vintage, investability. A retained checksum or an HTTP 200 is never a licence grant, so no
    entry reads VERIFIED unless an affirmative grant / dated publication evidence is retained in this repository."""
    record = [_identity(RESOLUTION_JSON)]   # retained observations of the terms read; pointing at them is not a grant
    return [
        {"input": "KS200 signal index", "role": "FAST/regime state price series",
         "retained": "FinanceDataReader 0.9.110 route, KOSPI 200 price index levels 1990-01-03..2026-09-17, vintageClass "
                     "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY, the upstream provider behind the route is not recorded in the retained audit",
         "rights": _need("UPSTREAM_UNRECORDED_KRX_SITE_TERMS_RESTRICT_AUTOMATED_COLLECTION",
                         "the upstream behind the FinanceDataReader route, and written terms from the index owner (KRX) or an authorised vendor permitting internal "
                         "research use and retention of daily KOSPI 200 closes; the KRX site terms prohibit copying and automated collection without prior permission", record),
         "pitVintage": _need("NOT_ESTABLISHED", "a dated publication/finality statement for closing index levels, or contemporaneous captures"),
         "investability": _need("NOT_APPLICABLE_SIGNAL_ONLY", "none; a signal series is not traded")},
        {"input": "VIX", "role": "transition state (VIXCLS via FRED)",
         "retained": "FRED VIXCLS 1990..2026-10-01; series note: Cboe copyright 'reprinted with permission'",
         "rights": _need("THIRD_PARTY_OWNER_PERMISSION_REQUIRED_BY_FRED_TERMS",
                         "Cboe's written permission for research use and retention of VIX values: FRED's terms say third-party series (notes containing 'Copyright', "
                         "which VIXCLS's do) need the data owner's permission beyond personal use and that FRED cannot grant it", record),
         "pitVintage": _need("NOT_ESTABLISHED", "vintage coverage for VIXCLS or a documented, tested justification of the frozen 4-calendar-day lag"),
         "investability": _need("NOT_APPLICABLE_SIGNAL_ONLY", "none; a signal series is not traded")},
        {"input": "Treasury 10y and 3m", "role": "slow state spread (DGS10, DGS3MO via FRED, origin H.15)",
         "retained": "FRED DGS10/DGS3MO 1990..2026-10-01; a check of one H.15 release (2012-01-03) on 8 values is reported in PR #289 comment "
                     "6540961783 but its receipt is NOT retained in this repository, so it cannot be verified from here",
         "rights": _need("PARTIAL_PUBLISHER_PUBLIC_DOMAIN_STATEMENT_RECORDED_FRED_TERMS_BYTES_NOT_RETAINED",
                         "the Board statement (public domain unless otherwise indicated, cite the Board) is recorded with its page hash and the series notes carry no "
                         "'Copyright' marker; the FRED API terms bytes are not retained (the host refuses this environment) and the owner has not recorded a decision", record),
         "pitVintage": _need("NOT_ESTABLISHED", "availability at decision time was UNKNOWN for the one release checked (PDF 2012-01-03 vs HTTP "
                                                "Last-Modified 2012-01-09); needs vintage coverage or a published revision statement for 2012-2026"),
         "investability": _need("NOT_APPLICABLE_SIGNAL_ONLY", "none; a signal series is not traded")},
        {"input": "069500.KS (KODEX 200)", "role": "traded asset, funded total return",
         "retained": "issuer as-traded closes 3,612 sessions reconciled to the corrected index; 46 distributions (20 with official payment date); "
                     "captured under a benchmark-audit authorisation label, which is not a licence",
         "rights": _need("EXPLICITLY_RESTRICTED_WITHOUT_PRIOR_PERMISSION",
                         "the issuer's written permission for research use and retention of the price and distribution files: the KODEX site states that using or "
                         "databasing its data without prior permission may carry civil and criminal liability, and the repository retains such files", record),
         "pitVintage": _need("PARTIAL_RULE_BOUNDED_26_EXACT_DATES_AND_TAXABLE_BASES_UNRESOLVED",
                             "an official per-event document (the exchange disclosure) with the exact payment date and taxable base for each of the 26 events; the trust "
                             "deed's payment rule bounds the lag for 24 of them (2 are record-date-rule only); the issuer endpoints serve a recent window only", record),
         "investability": _need("NOT_VERIFIED", "the actual investor tax treatment for 2012-2026 (the 15.4% rate is an unretained assumption) "
                                                "and the 26 payment dates")},
        {"input": "KRW cash", "role": "residual cash return of the funded-investor reading",
         "retained": "BOK base-rate step function (non-investable proxy); retained ECOS evidence lists 9 macro series (base rate 722Y001/0101000, "
                     "3-year Treasuries and others) and none is an investable deposit, CD or bill return; REVISED_HISTORY, no release vintage",
         "rights": _need("NOT_RETAINED", "terms for whichever series the owner names"),
         "pitVintage": _need("NOT_ESTABLISHED", "dated release evidence for the named series"),
         "investability": _need("MISSING", "an owner-named investable KRW instrument or rate with a dated source; the BOK base rate is not one, and "
                                           "the registered ZERO cash is an opportunity-cost scenario only; a listed bond ETF would need the same per-event "
                                           "distribution evidence this packet cannot yet obtain", record)},
    ]


def accounting_readings(evidence):
    """Two readings that are never merged: a descriptive registered scenario, and the genuine funded-investor reading."""
    distributions = evidence["confirmedSourceFacts"]["distributions"]
    return {
        "R_REGISTERED_SCENARIO": {
            "status": "DESCRIPTIVE_SCENARIO_NOT_A_FUNDED_INVESTOR_RESULT",
            "basis": "gross corrected 069500 index, distributions reinvested at the ex-date close, ZERO cash, registered 5.5bp costs at 1x/2x/3x",
            "constructibleFromRetainedBytes": True, "admitted": False,
            "why": "every input is retained, but no right, vintage or investability evidence is VERIFIED, so it cannot run; the corrected index is built from the "
                   "issuer's as-traded closes, so the issuer's retention restriction applies to this reading as well"},
        "F_FUNDED_INVESTOR": {
            "status": "BLOCKED",
            "requires": [f"{distributions['paymentDateUnresolved']} of {distributions['records']} official payment dates",
                         "taxable base for the earlier distributions and a verified 2012-2026 tax treatment (15.4% is an assumption)",
                         "an owner-named investable KRW cash series with dated evidence"],
            "hypotheticalScenariosAreNotEvidence": "the mixed-lag range (rule-bounded 2-9 sessions for 24 events, hypothetical 2-10 for 2) and the assumed tax rate are "
                                                   "sensitivities, not certified payment dates or a verified tax treatment"},
        "separation": "R and F are reported side by side in any future run and never substituted for each other",
    }


def readiness_status(prereqs, readings):
    """READY_FOR_OWNER_SCOPE_REVIEW only when every source prerequisite is VERIFIED and the funded-investor reading is constructible."""
    blockers = []
    for item in prereqs:
        for dimension in ("rights", "pitVintage", "investability"):
            state = item[dimension]["status"]
            if state == VERIFIED and not _has_evidence(item[dimension]):
                blockers.append(f"{item['input']}:{dimension}:VERIFIED_WITHOUT_RETAINED_EVIDENCE")
            elif state == VERIFIED and dimension == "rights" and not _has_owner_decision(item[dimension]):
                blockers.append(f"{item['input']}:{dimension}:VERIFIED_WITHOUT_OWNER_DECISION_RECORD")
            elif state not in (VERIFIED, "NOT_APPLICABLE_SIGNAL_ONLY"):
                blockers.append(f"{item['input']}:{dimension}:{state}")
    if readings["F_FUNDED_INVESTOR"]["status"] != "CONSTRUCTIBLE_AND_VERIFIED":
        blockers.append("F_FUNDED_INVESTOR:" + readings["F_FUNDED_INVESTOR"]["status"])
    return ("SOURCE_BLOCKED" if blockers else "READY_FOR_OWNER_SCOPE_REVIEW"), blockers


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def build():
    evidence = json.loads((ROOT / EVIDENCE_JSON).read_text())
    contract = CONTRACT.contract()
    proposal = contract["economicExperimentProposal"]
    prereqs = prerequisites()
    readings = accounting_readings(evidence)
    status, blockers = readiness_status(prereqs, readings)
    packet = {
        "studyId": STUDY, "status": status, "sourceBlockers": blockers,
        "historicalExecutionAuthorized": False, "evidenceClass": "READINESS_PACKET_NO_OUTCOME_COMPUTED",
        "experiment": {k: proposal[k] for k in ("primaryContrast", "primaryHorizonSessions", "secondaryHorizonSessions", "market", "benchmark",
                                                 "calendar", "valuation", "buyCost", "sellCost", "costStress", "window", "sampleClass")},
        "unapprovedThresholdsLeftNull": {k: None for k in sorted(k for k, v in proposal.items() if v is None)},
        "identities": {
            "registeredContractSha256": CONTRACT.contract_digest(), "implementationDigest": CONTRACT.implementation_digest(),
            "codeAndProposalFiles": [_identity(p) for p in CODE_FILES],
            "sourceEvidenceJson": _identity(EVIDENCE_JSON), "sourceResolutionJson": _identity(RESOLUTION_JSON),
            "sourceEvidenceInputs": [{"path": p, "sha256": d} for p, d in sorted(EVIDENCE.PINS.items())],
            "signalInputFiles": [_identity(p) for p in SIGNAL_INPUT_FILES],
            "checkMarketResearchProtectedFiles": 94},
        "blockerComparison": blocker_comparison(blockers),
        "accountingReadings": readings,
        "sourcePrerequisites": prereqs,
        "ownerDecisionsUnresolved": list(EVIDENCE.OWNER_DECISIONS),
        "supersedes": SUPERSEDES,
        "historicalDataReads": {
            "strategyPathReturnsComputed": 0, "stateOrSignalValuesComputed": 0, "armReturnsComputed": 0, "labelsOrOutcomesRead": 0,
            "benchmarkSeriesRead": "069500 as-traded closes and the corrected total-return index (distribution-timing and tax sensitivities) and "
                                   "KS200 index levels (annual reconciliation with the index), all retained files; the benchmark itself, not a "
                                   "strategy path; history is outcome-exposed",
            "ratesAndCashAmountsRead": "data/bok-policy-rates.json (cash-proxy mean rate) and the issuer dividend JSON and spreadsheet (record and "
                                       "payment dates, cash amounts, taxable bases): rates and cash amounts, not returns",
            "officialPagesAndDocumentsRead": "the issuer's own site scripts, its product-document and distribution endpoints, its fund-disclosure board and 12 trust-deed "
                                             "amendment notices, the KRX data-site terms, the Board disclaimer, the Cboe market-data policy and the FRED API terms; the "
                                             "downloaded PDFs are not committed (issuer retention restriction), only identities and short quotes",
            "notCoveredByTheProtectedFileCounter": "check_market_research.py realNumericValueReads does not cover these modules; this field is the record",
            "claim": "no unregistered strategy return was read; benchmark price relatives and the files above were read for accounting sensitivities only"},
        "signConvention": evidence["approximateAccounting"]["contrastPer10ppExposureGap"]["unit"],
        "smallestNextStep": "ONE owner action: obtain Samsung Asset Management's written permission for research use and retention of the KODEX 200 price and "
                            "distribution data, or decide the research cannot use it. It gates both readings, because the corrected index is built from the issuer's closes. "
                            "Cboe's permission for VIX and the KS200 upstream follow; the cash convention is a separate decision for reading F.",
    }
    packet["packetSha256"] = hashlib.sha256(canonical({k: v for k, v in packet.items() if k != "packetSha256"}).encode()).hexdigest()
    return packet


def verify(packet):
    """Recompute every identity from disk and the status from the prerequisites. Raises on any difference."""
    problems = []
    body = {k: v for k, v in packet.items() if k != "packetSha256"}
    if hashlib.sha256(canonical(body).encode()).hexdigest() != packet["packetSha256"]:
        problems.append("PACKET_DIGEST_MISMATCH")
    ident = packet["identities"]
    if ident["registeredContractSha256"] != CONTRACT.contract_digest():
        problems.append("REGISTERED_CONTRACT_CHANGED")
    if ident["implementationDigest"] != CONTRACT.implementation_digest():
        problems.append("IMPLEMENTATION_CHANGED")
    for group in ("codeAndProposalFiles", "signalInputFiles"):
        for item in ident[group]:
            if EVIDENCE.sha256(ROOT / item["path"]) != item["sha256"]:
                problems.append("FILE_CHANGED:" + item["path"])
    if EVIDENCE.sha256(ROOT / ident["sourceEvidenceJson"]["path"]) != ident["sourceEvidenceJson"]["sha256"]:
        problems.append("SOURCE_EVIDENCE_CHANGED")
    if EVIDENCE.sha256(ROOT / ident["sourceResolutionJson"]["path"]) != ident["sourceResolutionJson"]["sha256"]:
        problems.append("SOURCE_RESOLUTION_CHANGED")
    for item in ident["sourceEvidenceInputs"]:
        if EVIDENCE.sha256(ROOT / item["path"]) != item["sha256"]:
            problems.append("INPUT_CHANGED:" + item["path"])
    status, blockers = readiness_status(packet["sourcePrerequisites"], packet["accountingReadings"])
    if (status, blockers) != (packet["status"], packet["sourceBlockers"]):
        problems.append("STATUS_NOT_DERIVED_FROM_PREREQUISITES")
    if any(v is not None for v in packet["unapprovedThresholdsLeftNull"].values()):
        problems.append("THRESHOLD_NOT_NULL")
    if packet["historicalExecutionAuthorized"] is not False:
        problems.append("EXECUTION_FLAG_NOT_FALSE")
    rebuilt = build()
    for key in rebuilt:
        if key != "packetSha256" and packet.get(key) != rebuilt[key]:
            problems.append("FIELD_DIFFERS_FROM_REBUILD:" + key)
    for key in packet:
        if key not in rebuilt:
            problems.append("UNKNOWN_FIELD:" + key)
    if problems:
        raise ValueError("READINESS_PACKET_VERIFY_FAILED:" + ",".join(problems))
    return packet["status"]


def main():
    packet = build()
    text = json.dumps(packet, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    if OUTPUT.exists():
        raise SystemExit("PACKET_IS_IMMUTABLE_CUT_A_NEW_VERSION_INSTEAD_OF_OVERWRITING")
    OUTPUT.write_text(text)
    verify(json.loads(text))
    print(packet["status"], packet["packetSha256"])


if __name__ == "__main__":
    main()
