# RESEARCH_OPPORTUNITY_REGISTER (generated; edit lane register-entries.json)

| # | ID | 지역 | 영역 | 증거 등급 | 상태 | 통과/실패 관문 | 우선 | 점수 | Owner 승인 | 다음 실행 단위 |
|---:|---|---|---|---|---|---|---|---:|---|---|
| 1 | S4-KR-INSIDER | KR | STOCK | PREPARED_NOT_EXECUTED | ACTIVE | G1/- | P1 | 16 | 예 | outcome-blind collection of insider originals for the remaining 230 issuers (~49,000 document calls, ~3 DART days) so G2 is measured on the PIT Top-120 itself instead of projected from ~10 sampled members per anchor; owner to note that 115 of 128 quarantined filings are open-market rows dated 1-4 days after receipt (settlement-date shape) |
| 2 | S4-KR-BUYBACK-CANCELLATION | KR | STOCK | NOT_STARTED | ACTIVE | G1/- | P1 | 14 | 아니오 | outcome-blind parse of acquisition size (% of shares) and purpose on a 40-filing sample, then a pre-registration with its own density gate |
| 3 | P-P0-P5-COMPARISON | COMMON | PORTFOLIO | PREPARED_NOT_EXECUTED | ACTIVE | G1/- | P1 | 13 | 예 | owner decides whether to start research-only P0..P5 receipts with UNVALIDATED inputs flagged non-displayable |
| 4 | S5-KR-SUPPLY-CONTRACT | KR | STOCK | NOT_STARTED | ACTIVE | G1/- | P1 | 13 | 아니오 | parse probe of contract size (% of revenue) on 40 sampled filings; then a pre-registration |
| 5 | M-KR-TIMING-PROSPECTIVE | KR | MARKET | PREPARED_NOT_EXECUTED | ACTIVE | G0/- | P1 | 12 | 예 | build the weekly KR SLOW/TRANSITION + C0-C3 multiplier writer against kr_market_risk_model_receipts and register the contract |
| 6 | P-C2-FIXED-EXPOSURE | KR | PORTFOLIO | PREPARED_NOT_EXECUTED | ACTIVE | G1/- | P1 | 12 | 예 | owner authorization or ECOS CD91 validation probe |
| 7 | M-US-TIMING-PROSPECTIVE | US | MARKET | PREPARED_NOT_EXECUTED | ACTIVE | G0/- | P2 | 13 | 예 | implement a US weekly state/multiplier recorder reusing rp1_c1_us_exposure.layer_states(market='US') and prospective_receipt_core |
| 8 | S4-US-FORM4 | US | STOCK | SOURCE_BLOCKED | SOURCE_BACKLOG | G0/G1 | P2 | 13 | 예 | owner decision: permitted SEC contact + egress route |
| 9 | I-US-INDUSTRY-PROSPECTIVE | US | INDUSTRY | PREPARED_NOT_EXECUTED | ACTIVE | G0/- | P2 | 12 | 예 | build the weekly US sector receipt writer on us_sector_membership + industry_relative |
| 10 | P-MARKET-MULTIPLIER-INCREMENT | COMMON | PORTFOLIO | PREPARED_NOT_EXECUTED | ACTIVE | G0/- | P2 | 12 | 아니오 | join with market timing contract receipts once recording |
| 11 | S1-KR-DIVIDEND-POLICY-CHANGE | KR | STOCK | NOT_STARTED | ACTIVE | G1/- | P2 | 12 | 아니오 | parse the decision's per-share amount for the 24-issuer sample (outcome-blind) and measure change density |
| 12 | S4-KR-EQUITY-ISSUANCE-CB | KR | STOCK | NOT_STARTED | ACTIVE | G1/- | P2 | 12 | 아니오 | fold into a net-issuance event study only after buyback density is measured |
| 13 | X-B-H1 | KR | MARKET | PROSPECTIVE_PENDING | ACTIVE | G1/- | P2 | 12 | 예 | register the outcome contract before first maturity |
| 14 | D-US-SECTOR-FOUNDATION | US | DATA | PREPARED_NOT_EXECUTED | ACTIVE | G0/- | P2 | 11 | 아니오 | freeze us_sector_membership as the US industry receipt classifier and pin the dataset commit per receipt |
| 15 | I-KR-INDUSTRY-PROSPECTIVE | KR | INDUSTRY | PREPARED_NOT_EXECUTED | ACTIVE | G0/- | P2 | 11 | 예 | owner decides small-group rule, then build the weekly KR industry receipt writer from industry-relative-prospective-contract-v1 |
| 16 | S4-KR-LARGE-HOLDER-5PCT | KR | STOCK | NOT_STARTED | ACTIVE | G0/- | P2 | 11 | 아니오 | parse probe on 30 sampled 5% originals |
| 17 | I-KR-EXPORT-HS-DIFFUSION | KR | INDUSTRY | NOT_STARTED | SOURCE_BACKLOG | NONE/- | P2 | 10 | 예 | outcome-free source probe of release dates and revision behaviour |
| 18 | X-KR-CHALLENGERS | KR | STOCK | PROSPECTIVE_PENDING | ACTIVE | G1/- | P2 | 9 | 아니오 | keep recording; score only at maturity |
| 19 | S1-KR-ACCRUAL-CASH-QUALITY | KR | STOCK | NOT_STARTED | CLOSED | NONE/G0 | P3 | 11 | 아니오 | none: closed |
| 20 | S1-KR-VALUE-QUALITY-RECOMBINATION | KR | STOCK | NOT_STARTED | CLOSED | NONE/G0 | P3 | 10 | 아니오 | none: closed (Phase D) |
| 21 | S3-KR-MOMENTUM-VARIANTS | KR | STOCK | NOT_STARTED | CLOSED | NONE/G0 | P3 | 10 | 아니오 | none |
| 22 | X-C1C-ASYMMETRIC-EXIT | KR | MARKET | PREPARED_NOT_EXECUTED | PARKED | G0/G1 | P3 | 10 | 예 | fix audit items B1/B3/B5/B7 before any registration |
| 23 | I-KR-INVENTORY-CYCLE | KR | INDUSTRY | NOT_STARTED | SOURCE_BACKLOG | NONE/- | P3 | 9 | 아니오 | outcome-free field-presence count of inventory accounts in kr-raw |
| 24 | S1-US-CAPITAL-ALLOCATION | US | STOCK | PROSPECTIVE_PENDING | PARKED | NONE/G0 | P3 | 9 | 아니오 | none here: owned by us-capital-allocation-alpha-v1 |
| 25 | S2-KR-MANAGEMENT-GUIDANCE | KR | STOCK | NOT_STARTED | PARKED | G0/- | P3 | 9 | 아니오 | outcome-blind parse probe on 30 sampled guidance filings |
| 26 | S2-US-ESTIMATE-REVISIONS | US | STOCK | SOURCE_BLOCKED | SOURCE_BACKLOG | G0/G1 | P3 | 9 | 아니오 | none until purchased |
| 27 | S3-KR-SHORT-SELLING | KR | STOCK | SOURCE_BLOCKED | SOURCE_BACKLOG | G0/G1 | P3 | 9 | 아니오 | one permitted Probes re-run |
| 28 | S3-KR-VOLUME-ATTENTION-VARIANTS | KR | STOCK | NOT_STARTED | CLOSED | NONE/G0 | P3 | 9 | 아니오 | none |
| 29 | S3-US-SHORT-INTEREST | US | STOCK | SOURCE_BLOCKED | SOURCE_BACKLOG | G0/G1 | P3 | 9 | 아니오 | source probe |
| 30 | S4-KR-TREASURY-DISPOSAL | KR | STOCK | NOT_STARTED | PARKED | G1/- | P3 | 9 | 아니오 | none (parked) |
| 31 | S5-KR-NEW-FACILITY-INVESTMENT | KR | STOCK | NOT_STARTED | CLOSED | NONE/G0 | P3 | 9 | 아니오 | none |
| 32 | S5-US-8K-EVENTS | US | STOCK | SOURCE_BLOCKED | SOURCE_BACKLOG | G0/G1 | P3 | 9 | 아니오 | none |
| 33 | X-ENTRY-STATE-SHADOW | COMMON | STOCK | PREPARED_NOT_EXECUTED | ACTIVE | G1/- | P3 | 9 | 예 | independent review of #306 |
| 34 | I-SUPPLY-CHAIN-LINKS | COMMON | INDUSTRY | SOURCE_BLOCKED | SOURCE_BACKLOG | NONE/- | P3 | 8 | 예 | none until a structured source is identified |
| 35 | I-US-SECTOR-PIT | US | INDUSTRY | SOURCE_BLOCKED | PARKED | NONE/- | P3 | 8 | 예 | none until departed-name prices exist; use I-US-INDUSTRY-PROSPECTIVE instead |
| 36 | S1-US-CASH-PROFITABILITY | US | STOCK | NOT_STARTED | CLOSED | NONE/G0 | P3 | 8 | 아니오 | none here |
| 37 | S2-KR-ANALYST-REVISIONS | KR | STOCK | SOURCE_BLOCKED | SOURCE_BACKLOG | G0/G1 | P3 | 8 | 아니오 | none until a licensed source exists |
| 38 | S2-KR-ANNOUNCEMENT-TIMING | KR | STOCK | NOT_STARTED | CLOSED | NONE/G0 | P3 | 8 | 아니오 | none: in Phase C |
| 39 | S2-KR-PRELIMINARY-EARNINGS | KR | STOCK | NOT_STARTED | CLOSED | NONE/G0 | P3 | 8 | 아니오 | none: closed as re-expression |
| 40 | S3-US-INDEX-MEMBERSHIP-CHANGE | US | STOCK | NOT_STARTED | PARKED | G0/- | P3 | 8 | 아니오 | none |
| 41 | S4-KR-INVESTOR-FLOW | KR | STOCK | SOURCE_BLOCKED | SOURCE_BACKLOG | G0/G1 | P3 | 8 | 아니오 | one permitted Probes re-run |
| 42 | S4-KR-KRX-MAJOR-HOLDER-FILING | KR | STOCK | NOT_STARTED | CLOSED | NONE/G0 | P3 | 8 | 아니오 | use to cross-check insider parse coverage |
| 43 | S5-KR-CUSTOMER-SUPPLIER-LINKS | KR | STOCK | SOURCE_BLOCKED | SOURCE_BACKLOG | G0/G1 | P3 | 8 | 아니오 | revisit after S5-KR-SUPPLY-CONTRACT parse |
| 44 | S3-KR-INDEX-RECONSTITUTION | KR | STOCK | SOURCE_BLOCKED | SOURCE_BACKLOG | G0/G1 | P3 | 7 | 아니오 | none |
| 45 | S5-KR-VALUE-UP-PLAN | KR | STOCK | PROSPECTIVE_PENDING | PARKED | G1/- | P3 | 7 | 아니오 | prospective receipts only |
| 46 | X-INDUSTRY-OCF | KR | INDUSTRY | SOURCE_BLOCKED | CLOSED | G1/G2 | P3 | 7 | 아니오 | none |
| 47 | S2-US-SUE-WITHOUT-CONSENSUS | US | STOCK | NOT_STARTED | CLOSED | NONE/G0 | P3 | 6 | 아니오 | none |
| 48 | S4-US-13F | US | STOCK | SOURCE_BLOCKED | SOURCE_BACKLOG | G0/G1 | P3 | 6 | 아니오 | none |
| 49 | S5-KR-SEMICONDUCTOR-CYCLE | KR | STOCK | NOT_STARTED | CLOSED | NONE/G0 | P3 | 6 | 아니오 | hand to industry lane |
| 50 | X-M3-BACKLOG | US | INDUSTRY | EMPIRICAL_FAIL | CLOSED | G2/G3 | P3 | 6 | 아니오 | none |
| 51 | X-OPPORTUNITY-V5 | KR | STOCK | EMPIRICAL_FAIL | CLOSED | G2/G3 | P3 | 4 | 아니오 | none |
| 52 | X-PHASE-CD | KR | STOCK | EMPIRICAL_FAIL | CLOSED | G2/G3 | P3 | 4 | 아니오 | none |
| 53 | X-REGIONAL-31 | COMMON | STOCK | EMPIRICAL_FAIL | CLOSED | G2/G3 | P3 | 4 | 아니오 | none (must not be rerun) |
| 54 | D-KR-INDUSTRY-TERMINAL-COVERAGE | KR | DATA | SOURCE_BLOCKED | SOURCE_BACKLOG | NONE/- | P3 | 3 | 아니오 | none unless an official delisted-company industry source is found |
