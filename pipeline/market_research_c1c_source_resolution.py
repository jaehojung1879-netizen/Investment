"""Source resolution for the 26 unresolved KODEX 200 (069500.KS) distributions, rights terms and cash options (#289).

An EVIDENCE ADAPTER over the retained 46-event chain. It computes no strategy return, changes no registered rule, threshold,
population or sealed file, and grants no source right. Two kinds of content are kept apart:

  RECORDED OBSERVATIONS  what an official page, notice or document said on a stated retrieval date, with the sha256 of the
                         bytes where bytes were retrieved. They cannot be recomputed offline; the module and its tests only
                         guarantee they are well formed and are never promoted beyond what they say.
  RECOMPUTED CHECKS      statements that follow from the retained chain and are re-derived on every build (record dates against
                         the deed's rule, the rule-bounded timing interval, the per-event table).

This module NEVER emits a source-verified status. `classify_event` can return at most SHAPE_VALID_UNVERIFIED for a caller-supplied
source: a well-formed object whose URL is on an allow-listed official host and whose retained bytes hash to the stated digest. That
proves structure and a file hash only, not that the bytes are the official document or that the stated date and base are in them;
promotion to a verified state needs a human-reviewed record of the content (or independently authenticated extraction) that this
code does not model. A rule, a uniform lag or the gross cash amount can never produce even the shape-valid state. Today no event
has a source at all.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from . import market_research_c1c_source_evidence as S

STUDY = "market-research-c1c-source-resolution-v1"
OUTPUT = S.ROOT / "docs" / "research-program" / "proposals" / "market-research-c1c-source-resolution-v1.json"
RETRIEVED_ON = "2026-10-31"
BOARD_BASE = "https://www.samsungfund.com/fund/download.do?fileNo=1&fileSeq="

# Dated amendments of the KODEX 200 trust deed listed on the issuer's own fund-disclosure board (category 약관), with the sha256 of the
# attachment (fileNo=1, the amendment notice) as retrieved. The notice carries an old-versus-new clause table. fileNo=2 of the 2024 and
# 2026 entries is byte-identical to the CURRENT deed, so the attachments are NOT version-specific: only the notices are historical.
DEED_AMENDMENTS = (
    {"no": "12773", "date": "2010-04-13", "pages": 2, "sha256": "d2b52ac9895cf33607aeea9cc19c769f1c58b1483791ec006e613f3001600b08"},
    {"no": "27094", "date": "2012-12-17", "pages": 6, "sha256": "6071de9b77e15ae11db5b39496b060d5a8795418bb1254f91ee83204a6ed35fc"},
    {"no": "29110", "date": "2013-02-25", "pages": 1, "sha256": "597e302034da3b235d5aaaf8562be646b6c47b1a9e5adac61693eb9e999e8835"},
    {"no": "30727", "date": "2013-05-02", "pages": 2, "sha256": "062491dcfa4bc2c4cbdb15367bed40e32c968603acf56510ec9788bd40f87658"},
    {"no": "37998", "date": "2014-02-10", "pages": 7, "sha256": "9d2a57f5332764a8ea94d5c5afd1aed9809d21867186caaa750704af7db00e59"},
    {"no": "47561", "date": "2015-01-16", "pages": 2, "sha256": "150eeb71d99647252ba6978ac664e8220b77b7c169fce2c5b6d11ab114af8bb7"},
    {"no": "61960", "date": "2016-02-04", "pages": 2, "sha256": "b4062592cdf41cbc40d3ce105f0156eff5f7920e73bddeb1b080a3a29e98f566"},
    {"no": "75221", "date": "2016-08-19", "pages": 1, "sha256": "903641809b4310f6f0b386f355e9fc03809e4b92de5f1c136686b477233d1960"},
    {"no": "75207", "date": "2016-09-30", "pages": 1, "sha256": "903641809b4310f6f0b386f355e9fc03809e4b92de5f1c136686b477233d1960"},
    {"no": "168154", "date": "2020-04-08", "pages": 4, "sha256": "2bf436bb0d44eb9ec0867b0ceddcc5ccb91a4b7e54391c98a657d0eb88cdbdb1"},
    {"no": "222782", "date": "2024-03-21", "pages": 7, "sha256": "b99550695b2f1d4677a3b97c234f0297c36fe2730b380137b6d06629ad805653"},
    {"no": "243056", "date": "2026-07-16", "pages": 2, "sha256": "548841b9f058a9c2976a4352a8ef4312ff90298c8a2d80591be0aa08ec04e297"},
)
CURRENT_DEED_SHA256 = "6a9b4156e4f814d52b71969243519ea430300b5ab20325732fde99537994d72f"

# The payment-timing rule was read in the CURRENT deed (article 41-2). No amendment notice from 2012-12-17 onward lists an edit to it
# (every notice from 2012-12-17 to 2026-07-16 was read; only 2012-12-17, 2015-01-16, 2024-03-21 and 2026-07-16 touch the distribution
# article, and none edits the payment-timing item). That makes it RULE_BOUNDED from that date on, by inference from a complete notice
# chain, not by reading each historical version. Events before it only have the record-date rule read.
RULE_READ_FROM = pd.Timestamp("2012-12-17")
CLAUSE = {
    "article": "신탁계약서 제41조의2 (before 2026-07-16: 제41조)",
    "recordDate": "지급기준일: 1월, 4월, 7월, 10월 마지막 영업일 및 회계기간 종료일 (종료일이 영업일이 아니면 직전 영업일)",
    "paymentTiming": "지급시기: 지급기준일 익영업일로부터 제7영업일 이내",
    "exchangeDisclosure": "투자신탁분배금의 지급기준일로부터 제3영업일전까지 구체적인 사항을 증권시장에 공시",
    "discretion": "지급할 수 있다 (distribution is permitted, not mandatory)",
    "priorWording2012": "정정전 지급기준일: 1월, 4월, 7월, 10월 마지막일 및 회계기간 말일의 익영업일",
}
# Sessions after the ex-date. Ex-date is the session before the record date on 46/46 events. The earliest payment is the business day
# after the record date (= ex + 2). The latest is the 7th business day counted from that day: record + 7 or record + 8 depending on
# whether the first day counts, i.e. ex + 8 or ex + 9; the conservative reading is used.
RULE_LAG_AFTER_EX = (2, 9)
HYPOTHETICAL_LAG_AFTER_EX = (2, 10)


def record_date_rule_holds(record, sessions):
    """True when `record` is the last session of its month and the month is January, April, July or October."""
    month_sessions = sessions[(sessions.year == record.year) & (sessions.month == record.month)]
    return bool(len(month_sessions) and month_sessions[-1] == record and record.month in (1, 4, 7, 10))


OFFICIAL_HOSTS = ("samsungfund.com", "kind.krx.co.kr", "data.krx.co.kr", "opendart.fss.or.kr", "dart.fss.or.kr")
SHAPE_VALID = "SHAPE_VALID_UNVERIFIED"


def _official_https(url):
    match = re.fullmatch(r"https://([a-z0-9.-]+)(?::443)?(?:/\S*)?", str(url))
    host = match.group(1) if match else ""
    return any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS)


def classify_event(event, source=None, root=S.ROOT):
    """Per-event status. Returns SHAPE_VALID_UNVERIFIED (never a verified state) for a well-formed source; nothing derived counts.

    Checks structure only: official-host https URL, retained file under `root` whose bytes hash to `source.sha256`, payment after the
    record date, cash equal to the chain. `origin` is a declaration and the bytes are not parsed, so this cannot show that the document
    is the official one or that it states the date and base. Do not connect it to automated source admission."""
    if source is not None:
        required = ("documentIdentifier", "url", "retrievedAtUtc", "sha256", "retainedPath", "paymentDate", "taxableBasePerUnit", "cashPerUnit", "origin")
        missing = [k for k in required if source.get(k) in (None, "", 0)]
        if missing:
            raise ValueError("EVENT_SOURCE_INCOMPLETE:" + ",".join(missing))
        if source["origin"] != "OFFICIAL_PER_EVENT_DOCUMENT":
            raise ValueError("EVENT_SOURCE_NOT_AN_OFFICIAL_PER_EVENT_DOCUMENT:" + str(source["origin"]))
        if not re.fullmatch(r"[0-9a-f]{64}", str(source["sha256"])):
            raise ValueError("EVENT_SOURCE_HASH_INVALID")
        if not _official_https(source["url"]):
            raise ValueError("EVENT_SOURCE_URL_NOT_AN_ALLOW_LISTED_OFFICIAL_HTTPS_HOST")
        target = (Path(root) / str(source["retainedPath"])).resolve()
        try:
            target.relative_to(Path(root).resolve())
        except ValueError:
            raise ValueError("EVENT_SOURCE_RETAINED_PATH_OUTSIDE_REPOSITORY") from None
        if not target.is_file() or S.sha256(target) != source["sha256"]:
            raise ValueError("EVENT_SOURCE_BYTES_NOT_RETAINED_OR_HASH_DIFFERS")
        if pd.Timestamp(source["paymentDate"]) <= pd.Timestamp(event["record"]):
            raise ValueError("EVENT_PAYMENT_NOT_AFTER_RECORD_DATE")
        if float(source["cashPerUnit"]) != float(event["cash"]):
            raise ValueError("EVENT_SOURCE_CASH_DISAGREES_WITH_CHAIN")
        return SHAPE_VALID
    if not event["recordDateRuleHolds"]:
        return "UNRESOLVED"
    return "PARTIAL_RULE_BOUNDED" if pd.Timestamp(event["record"]) >= RULE_READ_FROM else "PARTIAL_RECORD_RULE_ONLY"


def event_table(quotes, chain, official):
    sessions = quotes.index
    resolved = set(official.record)
    rows = []
    for r in chain.itertuples():
        if r.record in resolved:
            continue
        event = {"exDate": str(r.ex.date()), "record": r.record, "recordDate": str(r.record.date()), "cash": float(r.cash),
                 "recordDateRuleHolds": record_date_rule_holds(r.record, sessions)}
        status = classify_event(event)
        bounded = status == "PARTIAL_RULE_BOUNDED"
        rows.append({
            "exDate": event["exDate"], "recordDate": event["recordDate"], "cashKrwPerRetainedUnit": event["cash"],
            "recordDateRuleHolds": event["recordDateRuleHolds"],
            "paymentDate": "UNRESOLVED", "taxableBasePerUnit": "UNRESOLVED",
            "paymentLagSessionsAfterEx": list(RULE_LAG_AFTER_EX if bounded else HYPOTHETICAL_LAG_AFTER_EX),
            "paymentLagBasis": ("TRUST_DEED_RULE_FROM_COMPLETE_AMENDMENT_NOTICE_CHAIN" if bounded else "HYPOTHETICAL_SCENARIO_RULE_NOT_READ_FOR_THIS_VERSION"),
            "originalSourceNeeded": "exchange (KRX) disclosure of the distribution, filed no later than 3 business days before the record date",
            "status": status})
    return rows


def rule_bounded_interval(price, chain, official, table):
    """Mixed-lag funded-minus-registered effect (B - A), pp/yr per 100% ETF weight: 20 known fixed; rule-bounded events over 2..9 sessions
    after ex, the two earlier events over the hypothetical 2..10. First-order, zero return on cash while awaiting payment."""
    sessions = price.index
    years = S.years_between(sessions[0], sessions[-1])
    paid = chain.merge(official[["record", "pay"]], on="record", how="left")
    status = {row["recordDate"]: row["status"] for row in table}
    known_total, lower, upper = 0.0, 0.0, 0.0
    for r in paid.itertuples():
        if pd.notna(r.pay):
            known_total += S._timing_term(price, r.ex, r.cash, sessions.get_loc(r.pay) - sessions.get_loc(r.ex))
            continue
        lags = range(RULE_LAG_AFTER_EX[0], RULE_LAG_AFTER_EX[1] + 1) if status[str(r.record.date())] == "PARTIAL_RULE_BOUNDED" \
            else range(HYPOTHETICAL_LAG_AFTER_EX[0], HYPOTHETICAL_LAG_AFTER_EX[1] + 1)
        terms = [S._timing_term(price, r.ex, r.cash, lag) for lag in lags]
        lower, upper = lower + min(terms), upper + max(terms)
    scale = 100 / years
    lo, hi = (known_total + lower) * scale, (known_total + upper) * scale
    return {"unit": "pp/yr per 100% ETF weight, funded minus registered (B - A)", "knownFixedPpPerYear": round(float(known_total * scale), 5),
            "signedInterval": {"lowerPpPerYear": round(float(lo), 5), "upperPpPerYear": round(float(hi), 5)},
            "boundOnAbsoluteEffectPpPerYear": round(float(max(abs(lo), abs(hi))), 5),
            "status": "CONDITIONAL_FIRST_ORDER_RULE_BOUNDED_NOT_CERTIFIED_PAYMENT_DATES"}


def fred_note_flags(root=S.ROOT):
    """Whether each retained FRED series' own notes contain the word 'Copyright' (FRED's marker for third-party series)."""
    flags = {}
    for series in ("FRED_VIXCLS", "FRED_DGS10", "FRED_DGS3MO"):
        raw = json.loads((root / f"data/kr-market-risk-anatomy-v1/sources/{series}/raw_series.json").read_text())
        flags[series] = "Copyright" in raw["seriess"][0].get("notes", "")
    return flags


def rights_matrix(flags):
    """What the applicable terms SAY. No entry is a grant: an HTTP 200 or a checksum is not permission."""
    return [
        {"input": "069500 issuer price and distribution files (KODEX)",
         "term": {"url": "https://www.samsungfund.com/etf/main.do", "retrievedOn": RETRIEVED_ON, "bytesSha256": "d6042e12c4ae76c5a407e8a61b516ad1f1253553b82e66adb16d8b61612f44e8",
                  "quote": "본 웹사이트의 자료를 사전 허가없이 무단으로 사용하거나 데이터베이스화 할 경우, 민형사상 법적 책임을 질 수 있습니다."},
         "researchUse": "EXPLICITLY_RESTRICTED_WITHOUT_PRIOR_PERMISSION_(USE_OR_DATABASING)",
         "retention": "EXPLICITLY_RESTRICTED_WITHOUT_PRIOR_PERMISSION", "redistribution": "EXPLICITLY_RESTRICTED_WITHOUT_PRIOR_PERMISSION",
         "repositoryRetainsCoveredData": True, "permissionDocumentRetained": False,
         "note": "the notice restricts use as well as databasing ('사용하거나 데이터베이스화'); no research-use exception is stated. The retained issuer files were captured under an internal benchmark-audit authorisation label, which is not a licence from the issuer; "
                 "the notice also says the index and yield information is supplied to the issuer by KOSCOM and the administrator"},
        {"input": "KS200 index levels",
         "term": {"url": "https://data.krx.co.kr/contents/MDC/INFO/informationController/MDCINFO003.cmd", "retrievedOn": RETRIEVED_ON,
                  "bytesSha256": "35882efb42891bbb22ea1b8b29fdbbe73737ee573a3cc3b823f860915ac41f69",
                  "quote": "이용자는 당 사이트의 정보를 거래소의 사전 허락 없이 복사·복제·배포·전송·공중송신하여서는 아니 됩니다. / 자동화 수단을 이용하여 정보를 무단 수집·복제·배포하는 행위"},
         "researchUse": "UNKNOWN", "retention": "UNKNOWN_FOR_THE_RETAINED_ROUTE",
         "redistribution": "EXPLICITLY_RESTRICTED_WITHOUT_PRIOR_PERMISSION_ON_THE_KRX_SITE",
         "note": "these terms govern the KRX data site; the retained series came through FinanceDataReader 0.9.110 whose upstream provider is not recorded, so which "
                 "terms apply to the retained bytes is unknown. Any automated collection from the KRX sites (including KIND disclosures) is prohibited without permission"},
        {"input": "VIX (FRED VIXCLS)",
         "term": {"url": "https://fred.stlouisfed.org/docs/api/terms_of_use.html", "retrievedOn": RETRIEVED_ON, "bytesSha256": None,
                  "quote": "Before using data series owned by third parties for anything other than your own personal use, you must contact the data owner to obtain permission. "
                           "The Federal Reserve Bank of St. Louis cannot give you such permission and making the data series available through the FRED® API does not constitute such permission."},
         "retainedSeriesNotesContainCopyright": flags["FRED_VIXCLS"],
         "researchUse": "THIRD_PARTY_OWNER_PERMISSION_REQUIRED_BEYOND_PERSONAL_USE", "retention": "NOT_ADDRESSED_FOR_DATA_IN_THE_PAGE_READ",
         "redistribution": "THIRD_PARTY_OWNER_PERMISSION_REQUIRED",
         "secondTerm": {"url": "https://cdn.cboe.com/resources/membership/Market_Data_Policies.pdf", "retrievedOn": RETRIEVED_ON,
                        "bytesSha256": "a2b9204b68740e6a4bd233569a42e66ea91a1fc4c50bc830e9440ed3a8082633",
                        "quote": "Data Recipients receiving Real-time or Delayed Data may store the data and subsequently use the Historical Data internally within their own "
                                 "organization, including Affiliates, for a fee when applicable. Before a firm can redistribute Historical Data to non-Affiliates, the firm must first "
                                 "sign a Data Agreement"},
         "note": "the FRED page text was read through a fetch tool and its bytes are NOT retained (the host refuses this environment's direct requests). A search summary "
                 "mentioned a 2024 ban on caching FRED content; that sentence was NOT found in the page text read, so it is not relied on either way. The Cboe policy "
                 "addresses Cboe's Data Recipients; whether a research user of FRED-served VIXCLS is one is not established"},
        {"input": "Treasury 10y and 3m (FRED DGS10, DGS3MO; origin Board H.15)",
         "term": {"url": "https://www.federalreserve.gov/disclaimer.htm", "retrievedOn": RETRIEVED_ON, "bytesSha256": "6fd9c6703a144d763e72ed70bc9378f7a855dbb1ad12c46197c3e3161b5d3e3e", "bytesNote": "a retrieval-time observation; a later independent fetch hashed differently (dynamic page) while the quoted sentence was unchanged",
                  "quote": "Unless otherwise indicated, information on Board's website is in the public domain and may be copied and distributed without permission. "
                           "Please cite to the Board as the source of the information."},
         "retainedSeriesNotesContainCopyright": {"DGS10": flags["FRED_DGS10"], "DGS3MO": flags["FRED_DGS3MO"]},
         "researchUse": "PUBLIC_DOMAIN_PER_PUBLISHER_STATEMENT_FOR_BOARD_PUBLISHED_INFORMATION", "retention": "PUBLIC_DOMAIN_PER_PUBLISHER_STATEMENT_FOR_BOARD_PUBLISHED_INFORMATION",
         "redistribution": "PUBLIC_DOMAIN_PER_PUBLISHER_STATEMENT_FOR_BOARD_PUBLISHED_INFORMATION",
         "note": "the statement covers information on the Board's own website unless otherwise indicated; the retained bytes came through the FRED API, whose terms bytes "
                 "are not retained, and the series notes carry no 'Copyright' marker (FRED's own flag for third-party series). Credit to the Board is required. "
                 "This is the strongest rights basis among the five inputs and is still not recorded as a grant"},
    ]


def cash_options(flags):
    """Options for the owner. No return is computed or assumed for any of them."""
    return {
        "A_REGISTERED_ZERO": {"status": "OPPORTUNITY_COST_SCENARIO_NOT_INVESTABLE", "usableFor": "reading R only (never the funded-investor reading)"},
        "B_LISTED_KRW_SHORT_BOND_OR_MONEY_MARKET_ETF": {
            "status": "INVESTABLE_IN_PRINCIPLE_HISTORY_NOT_BUILDABLE_FROM_RETAINED_OR_ISSUER_SOURCES",
            "why": "its total return needs as-traded closes AND every distribution with payment dates and taxable bases, the same evidence gap as the 26 events; the issuer's own endpoints serve "
                   "only a recent window (KODEX 200: 20 records from 2021-10; the document library's per-product distribution list ranges 0 to 23 entries across the 20 products on its first "
                   "page and is identical for every reference date tested); the exchange disclosures are behind KRX sites whose terms prohibit automated collection",
            "evidenceNeededFromOwner": "a named instrument, its issuer terms for research use, and its per-event distribution disclosures"},
        "C_BANK_DEPOSIT_CMA_RP": {"status": "NO_DATED_FREE_HISTORICAL_SERIES_RETAINED_OR_IDENTIFIED", "evidenceNeededFromOwner": "account statements or a rights-cleared published series"},
        "D_BOK_BASE_RATE": {"status": "NON_INVESTABLE_PROXY_BRACKET_ONLY", "usableFor": "an upper-side sensitivity, never relabelled as the investor's cash"},
        "funded_investor_reading": "BLOCKED until B or C is named and its evidence is retained; no return is fabricated",
        "retainedEcosEvidence": "base rate 722Y001/0101000 and 3-year Treasuries among 9 macro series; none is an investable deposit, CD or bill return",
        "ownerDecision": "name the cash convention for reading F (B, C, or accept that F stays blocked), separately from reading R",
    }


def issuer_endpoint_observations():
    return {
        "retrievedOn": RETRIEVED_ON,
        "distributionEndpoint": {"url": "https://www.samsungfund.com/api/v1/kodex/divid-info.do?id=2ETF01", "parameters": "id only (read from the site's own script)",
                                 "records": 20, "oldestRecord": "2021-10-29", "payDateAndTaxableBaseFields": True},
        "documentLibraryEndpoint": {"url": "https://www.samsungfund.com/api/v1/kodex/product-document.do", "kodex200DistributionRecords": 12, "oldestRecord": "2024-01-31",
                                    "identicalAcrossReferenceDatesTested": ["2014-03-31", "2015-03-31", "2016-03-31", "2017-03-31", "2018-03-30", "2019-03-29", "2020-03-31", "2021-03-31", "2022-03-31"],
                                    "note": "the reference date only changes which archived portfolio files are linked; it does not return older distributions"},
        "fundDisclosureBoard": {"url": "https://www.samsungfund.com/etf/lounge/announcement.do?seq=1",
                                "finding": "carries trust-deed, prospectus and personnel amendments; no per-event distribution notice and no management report for KODEX 200"},
        "archivedProductSheets": "the retained annual sheets (2014-2022) list the record date (지급기준일) and amount, not the payment date",
        "kind": "kind.krx.co.kr answered HTTP 403 from this environment; its terms-of-use text prohibits automated collection without permission",
        "outOfWindowObservation": {"recordDate": "2026-10-30", "paymentDate": "2026-11-03", "cashPerUnit": 136, "taxableBasePerUnit": 136,
                                   "note": "a distribution after the fixed study window (ends 2026-09-14); not added to the 46-event population"},
    }


def build():
    S.verify_pins()
    quotes, chain, endpoint = S.load_chain()
    official = S.load_official_payments()
    price = S.as_traded_prices(quotes, chain, endpoint)
    table = event_table(quotes, chain, official)
    sessions = quotes.index
    flags = fred_note_flags()
    return {
        "studyId": STUDY, "evidenceClass": "OFFICIAL_SOURCE_OBSERVATIONS_AND_OFFLINE_CHECKS_NO_STRATEGY_RETURN",
        "inputs": {"source-evidence": S.sha256(S.ROOT / "docs/research-program/proposals/market-research-c1c-source-evidence-v1.json"), **S.PINS},
        "events": {"population": int(len(chain)), "officialPaymentDates": int(len(official)), "unresolved": len(table),
                   "verifiedCount": 0,   # this module has no verified state; see the module docstring
                   "shapeValidUnverifiedCount": sum(1 for r in table if r["status"] == SHAPE_VALID),
                   "partialRuleBounded": sum(1 for r in table if r["status"] == "PARTIAL_RULE_BOUNDED"),
                   "partialRecordRuleOnly": sum(1 for r in table if r["status"] == "PARTIAL_RECORD_RULE_ONLY"),
                   "unresolvedNoRule": sum(1 for r in table if r["status"] == "UNRESOLVED"),
                   "recordDatesMatchingTheDeedRule": sum(1 for r in chain.itertuples() if record_date_rule_holds(r.record, sessions)),
                   "table": table},
        "trustDeed": {"issuerBoard": "https://www.samsungfund.com/etf/lounge/announcement.do?seq=1 (category 약관, search KODEX200증권상장지수투자신탁[주식])",
                      "amendmentNotices": list(DEED_AMENDMENTS), "currentDeedSha256": CURRENT_DEED_SHA256, "downloadPattern": BOARD_BASE + "<no>",
                      "attachmentsAreNotVersionSpecific": "fileNo=2 of the 2024-03-21 and 2026-07-16 notices equals the current deed byte for byte",
                      "clause": CLAUSE, "ruleReadFrom": str(RULE_READ_FROM.date()), "ruleLagSessionsAfterEx": list(RULE_LAG_AFTER_EX),
                      "lagReading": "earliest = the business day after the record date (ex + 2); latest = the 7th business day counted from it (ex + 8 or ex + 9; the conservative reading is used)",
                      "retention": "the downloaded PDFs are NOT committed (issuer retention restriction); only identities and short clause quotes are recorded",
                      "ruleBoundedInterval": rule_bounded_interval(price, chain, official, table)},
        "issuerEndpoints": issuer_endpoint_observations(),
        "rightsTerms": rights_matrix(flags),
        "cashOptions": cash_options(flags),
        "remainingGap": "an official per-event document with the exact payment date and taxable base for each of the 26 events; the exchange disclosure is the identified source and sits behind KRX sites",
    }


def main():
    evidence = build()
    text = json.dumps(evidence, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    if OUTPUT.exists() and OUTPUT.read_text() != text:
        raise SystemExit("REFUSING_TO_OVERWRITE_DIFFERENT_COMMITTED_EVIDENCE")
    OUTPUT.write_text(text)
    print(json.dumps(evidence["events"] | {"table": "..."}, ensure_ascii=False))


if __name__ == "__main__":
    main()
