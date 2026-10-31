# Market C — owner rights and scope handoff (v1)

Status: **SOURCE_BLOCKED**, 13 blockers, nothing newly verified. This page summarises what the terms read so far say; it is not legal advice and
records no grant. Quotes and hashes: `market-research-c1c-source-resolution-v1.json` (`rightsTerms`). Every "NOT ADDRESSED" below means the
text read does not say, not that the use is allowed.

## 1. Permission request matrix

Columns are the four uses you asked to keep apart. **Personal** = you alone, private, not for others. **Internal model** = your own systematic model
research, private. **Retained raw** = the files stay on disk or in the private repository. **Public GitHub** = bytes or derived rows visible to others.

| Source and product (dates) | Personal | Internal model | Retained raw | Public GitHub | What you must confirm |
|---|---|---|---|---|---|
| **Samsung AM / KODEX 200 (069500)** closes 2012-01-02..2026-09-14 and the 46 distribution records (record dates 2012-04-30..2026-07) | NOT ADDRESSED (the notice names "사용" and "데이터베이스화" without defining personal use) | RESTRICTED without prior permission (notice text) | RESTRICTED without prior permission; the repository already retains issuer files | RESTRICTED; personal permission would not cover it | written statement that **research use, retention and derived-statistic publication** of daily closes and distribution records (record/ex/payment dates, cash and taxable base per unit) are permitted, for 2012-2026 |
| **KRX / KOSPI 200 index** levels 1990-01-03..2026-09-17 retained; study uses 2012-01-02..2026-09-14. Retained route: FinanceDataReader 0.9.110, **upstream unknown** | UNKNOWN for the retained route | UNKNOWN | UNKNOWN; KRX site terms bar copying and automated collection without prior permission | RESTRICTED on the KRX site | which provider actually supplied the bytes; the index owner's (KRX) or an authorised vendor's terms for internal research use and retention of daily closes |
| **Cboe VIX via FRED VIXCLS** 1990..2026-10-01 (series note: Cboe copyright) | FRED: personal non-commercial use allowed for copyrighted series | Owner (Cboe) permission required beyond personal use; FRED cannot grant it | FRED API terms: **storing, caching or archiving FRED content is prohibited** | PROHIBITED to pass stored FRED content to third parties; Cboe policy requires a Data Agreement to redistribute Historical Data to non-Affiliates | Cboe's written permission for internal research use and retention; **review flag**: FRED API terms also prohibit use "in connection with the development or training of any software program or system or machine learning" — whether a rule-based model is covered is a legal reading, not decided here |
| **Federal Reserve H.15** (DGS10, DGS3MO) 1990..2026-10-01, retained via the FRED API | Board: public domain for information on its site | Board: public domain; but the FRED API route is storage- and ML-restricted | Board direct route: public domain statement; **FRED route: restricted** | Board direct: "may be copied and distributed without permission", cite the Board; FRED route: prohibited | decide to obtain H.15 **directly from the Board** (not FRED) and cite it; the sealed retained FRED files stay untouched |

Flag for you: the repository retains FRED-API-obtained files (`data/kr-market-risk-anatomy-v1/sources/FRED_*`) and issuer files in a sealed audit directory.
They were not modified or deleted here. The FRED terms were read through a fetch tool, verbatim, and their bytes are not retained.

## 2. What the gate now guarantees

`classify_event` returns at most `SHAPE_VALID_UNVERIFIED`. Reviewed counterexample (`example.invalid` URL, hash of an unrelated repository JSON,
`origin` self-declared): the previous gate (`0d3696f`) returned `VERIFIED`; the repaired gate refuses it, and the same fixture on an official host is
only shape-valid. Five layers stay separate (`admission_layers`): metadata complete, retained bytes match hash, official provenance and field content,
source-use rights, economic admission. Only the first two can ever be true in code; the other three need a reviewed record and your decision.
A privately retained original with an independently signed or manually reviewed manifest may be proposed later; it is not modelled and nothing here claims
authentication.

## 3. Results preserved

26 KODEX distributions still have no confirmed payment date or taxable base. 24 are bounded by the trust-deed rule (ex+2..9 sessions, inferred
continuity from 2012-12-17), 2 only by the record-date rule, 0 verified. Timing interval `[-0.02308, +0.01524]` pp/yr per 100% ETF weight is
conditional and first-order. No exact payment date was inferred. Cash options record no return; the 15.4% rate is an unretained assumption and is not
used as a universal investor tax.

## 4. Readings R and F

- **R** (descriptive, `admitted: false`): gross corrected index, ex-date reinvestment, zero cash, 1x/2x/3x costs.
- **F** (genuine funded investor) is blocked for: (1) a named investable KRW cash instrument and rights to its price and distribution data; (2) the
  investor's actual tax treatment (account type, residency, dividend withholding), not an assumed rate; (3) exact payment dates and taxable bases for
  the 26 events; (4) point-in-time publication evidence for KS200, VIX and the Treasury series; (5) the rights above. The BOK base rate is not investable
  and is never substituted.
- **Narrowest separately authorisable exploratory measurement** (not run, not authorised here): KR, 069500.KS, C0 ORIGINAL_STRUCTURAL
  REENTRY−BASE, H126 primary and H252 secondary, C1 auxiliary, costs 1x/2x/3x, reading R only, labelled non-confirmatory development evidence on an
  outcome-exposed sample and not a funded-investor result. It needs the Section 1 permissions for the sources it reads, H.15 from the Board directly, and
  your separate written authorisation. The +0.50 pp threshold is not approved.

## 5. One decision (한국어)

**결정 요청 (하나):** KODEX 200(삼성자산운용) 시세·분배금 데이터의 *연구 사용·보관 서면 허가*를 요청하는 경로를 승인하시겠습니까, 아니면 이 데이터를 쓰지 않기로 하시겠습니까?
허가가 기록되기 전에는 R·F 모두 실행하지 않으며, KRX 지수 출처·Cboe VIX 허가와 H.15의 Board 직접 수집 전환은 그 다음 순서입니다.
FRED로 받은 파일의 보관과 머신러닝·소프트웨어 개발 사용 제한 문제는 별도로 검토해 주십시오(이 문서는 법률 판단을 하지 않습니다).
