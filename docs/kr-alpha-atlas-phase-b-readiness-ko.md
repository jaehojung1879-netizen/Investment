# 한국 주식 알파 아틀라스 — Phase B 데이터 준비 보고서

**이 문서는 데이터가 충분한지만 말합니다. 어떤 특성이 수익을 예측하는지는 전혀 계산하지 않았고(미래 수익률·라벨·모형 학습 없음), 투자 판단이나 매매도 바꾸지 않았습니다.**
기계 판독용 원본은 `docs/results/kr-alpha-atlas-phase-b-readiness.json`이며, 이 문서는 그 파일에서 자동으로 만들어집니다.

## 한눈에 보기

- 판정: **Phase C 사전등록으로 진행 가능** — 알파 후보가 행의 60% 이상에서 측정되고 평가 가능한 주가 52주 이상인 정보군이 8개(A, B, C, D, E, F, H, J)입니다.
- 기준 유니버스: 시점 기준 KRX 시가총액 상위 120종목, 매주 신호일 714개(2013-01-04 ~ 2026-09-11), 종목·날짜 85,680건, 서로 다른 종목 260개.
- 계산한 특성 76개 / 등록 106개. 나머지는 이유와 함께 아래에 기록했습니다.
- 시점(PIT) 점검: 공시가 신호일 이전에 공개된 칸 805,676개를 검사했고 위반 0건, 유니버스 스냅샷 위반 0건 — 통과.
- 거래대금은 **종가×거래량 대용치** 입니다(공식 KRX 거래대금 파일은 Actions 산출물에만 있어 이 환경에서 읽지 못했습니다).

## 상태 구분 (코드 구현 / 실제 데이터로 검증 / 미달 / 차단)

특성마다 서로 다른 네 가지를 따로 적습니다: ① 등록 당시 상태(설계 시점의 예상, 수정하지 않음) ② 구현 상태(이번에 코드로 계산했는지) ③ 측정 판정(실제 매트릭스의 커버리지) ④ 진짜 출처 장애(계산하지 못한 특성에만 붙음). **계산한 특성은 등록 당시 상태가 '데이터 구축 필요'였더라도 출처 장애가 아니며**, 커버리지 판정만 가집니다.

- **실제 데이터로 측정 완료·사용 가능** (코드 구현됨 + 실제 입력으로 계산, 커버리지 기준 통과): A01_return1d, A02_return5d, A03_return21d, A04_return63d, A05_relative126, A06_return252d, A07_momentum12_1, A08_momentum6, A09_industryRelativeMomentum126, A10_residualMomentum126, A11_distance52wHigh, A12_momentumPersistence, A13_momentumAcceleration21, A14_ma200Distance, B01_bookToMarket, B02_earningsYield, B03_ocfYield, B04_freeCashFlowYield, B05_industryRelativeValue, B06_ownHistoryValuation, B07_valuationChange126, B08_valueBusinessConfirmation, C01_returnOnAssets, C02_returnOnEquity, C05_ocfToAssets, C07_negativeAccruals, C08_netIncomeMinusOcf, C09_assetGrowth, C10_liabilityGrowth, C11_shareDilution, C12_profitabilityPersistence, C14_ocfImprovement, D01_volumeSurge5_60, D02_logVolumeShock60, D03_tradingValueShock5_60, D04_shockPersistence5d, D05_turnoverToMarketCap60, D06_priceVolumeDivergence, D07_volumePriceAlignment, D08_abnormalVolumeUpClose, D09_abnormalVolumeDownClose, D10_liquidityAcceleration, D11_accumulationDistributionProxy, E01_amihudIlliquidity60, E02_logAdv60, E03_capacityMedianTradedValue60, E04_tradabilityGuard20, E05_highLowSpreadProxy, E06_volatilityConditionalOnVolume, E07_suspensionStaleRisk, F01_totalVolatility63, F02_downsideVol126, F03_beta252, F04_idiosyncraticVol, F05_maxDrawdown252, F06_crashExposure, F07_benchmarkCorrelation252, H01_industryRelMom126, H02_industryRelMom63, H03_industryBreadthAboveMA126, H04_withinIndustryDispersion126, H05_crossIndustryDispersion, H06_industryConcentrationTop1, H07_leadershipPersistence, H08_equalVsCapWeightIndustry, H09_marketBreadth, H10_marketConcentrationTop2, H12_industryValuationContext, I01_kospiTrendVolState, J01_periodicFilingEvent, J05_shortSellingRegime
- **코드는 구현됐지만 커버리지 기준 미달 (NOT_READY)**: C03_operatingMargin(54.203364%), C04_profitMargin(55.17737%), C06_cashConversion(56.62844%), C15_capexIntensity(52.896024%), H11_industryEarningsContext(58.437309%)
- **출처 차단 (SOURCE_BLOCKED)**: G01_foreignNetBuying, G02_institutionalNetBuying, G03_retailNetBuying, G04_investorTypePersistence, G05_flowMomentumConfirmation, G08_shortSellingVolume, G09_shortBalanceChange
- **시점 안전성 없음 (PIT_UNSAFE)**: I03_krTermSpread, I06_krInflation, I07_krExportsActivity, I08_usdKrw, I09_fxBeta26w, I11_globalFinancialConditions
- **데이터 구축 필요 / 구할 수 없음 (계산하지 않음)**: C16_grossProfitability, E08_trueBidAskSpread, G06_largeHolderAccumulation, G07_largeHolderReduction, I04_krPolicyRate, I05_krCreditSpread, I10_semiconductorCycleSOX, I12_commodityExposure, J02_dividendPolicyChange, J03_buybackAnnouncement, J04_materialDisclosure, J06_searchAttention, J07_newsTextSentiment, J08_analystRevisions
- **기존 연구 결과만 인용(재계산 안 함)**: C13_fundamentalAcceleration, I02_vixLevel
- 사전 수정(결과를 보기 전): B08_DENOMINATOR_IS_THE_H2_CONTRACTS_OWN_ELIGIBLE_SET — 자세한 내용은 JSON의 `preOutcomeRevisions`.

## 정보군별 결과

| 정보군 | 등록 | 사용 가능 후보 | 사용 가능 특성 |
|---|---:|---:|---|
| A 가격·모멘텀·반전 | 14 | 11 | A01_return1d, A02_return5d, A03_return21d, A04_return63d, A06_return252d, A08_momentum6, A10_residualMomentum126, A11_distance52wHigh, A12_momentumPersistence, A13_momentumAcceleration21, A14_ma200Distance |
| B 가치 | 8 | 4 | B04_freeCashFlowYield, B06_ownHistoryValuation, B07_valuationChange126, B08_valueBusinessConfirmation |
| C 수익성·회계 품질 | 16 | 5 | C02_returnOnEquity, C09_assetGrowth, C10_liabilityGrowth, C11_shareDilution, C12_profitabilityPersistence |
| D 거래량·거래 활동 | 11 | 11 | D01_volumeSurge5_60, D02_logVolumeShock60, D03_tradingValueShock5_60, D04_shockPersistence5d, D05_turnoverToMarketCap60, D06_priceVolumeDivergence, D07_volumePriceAlignment, D08_abnormalVolumeUpClose, D09_abnormalVolumeDownClose, D10_liquidityAcceleration, D11_accumulationDistributionProxy |
| E 유동성·미시구조 | 8 | 2 | E01_amihudIlliquidity60, E06_volatilityConditionalOnVolume |
| F 위험 특성 | 8 | 3 | F01_totalVolatility63, F03_beta252, F04_idiosyncraticVol |
| G 투자자 수급·지분 | 9 | 0 | — |
| H 산업·횡단면 구조 | 12 | 1 | H08_equalVsCapWeightIndustry |
| I 거시·환율·글로벌 | 12 | 0 | — |
| J 이벤트·대체 정보 | 8 | 1 | J01_periodicFilingEvent |

사용 가능 후보는 '알파 후보' 역할이면서 기준(행의 60% 이상, 30개 이상 종목, 52주 이상)을 넘은 특성입니다. 위험·비용·적격성 지표는 후보에 넣지 않습니다.

## 특성별 커버리지 (계산한 특성)

| 특성 | 역할 | 전체 커버리지 | 사용 범위 내 커버리지 | 사용 가능 기간 | 상태 |
|---|---|---:|---:|---|---|
| A01_return1d | ALPHA_CANDIDATE | 92.51634% | 99.934443% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| A02_return5d | ALPHA_CANDIDATE | 92.489496% | 99.905446% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| A03_return21d | ALPHA_CANDIDATE | 92.347106% | 99.751639% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| A04_return63d | ALPHA_CANDIDATE | 91.860411% | 99.22592% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| A05_relative126 | CONTROL | 94.940476% | 98.528343% | 2013-07-05 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| A06_return252d | ALPHA_CANDIDATE | 89.933473% | 97.144478% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| A07_momentum12_1 | CONTROL | 89.968487% | 97.1823% | 2014-01-10 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| A08_momentum6 | ALPHA_CANDIDATE | 91.19281% | 98.504791% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| A09_industryRelativeMomentum126 | ALPHA_CANDIDATE | 67.676237% | 70.233769% | 2013-07-05 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| A10_residualMomentum126 | ALPHA_CANDIDATE | 89.933473% | 97.144478% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| A11_distance52wHigh | ALPHA_CANDIDATE | 89.940476% | 97.152042% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| A12_momentumPersistence | ALPHA_CANDIDATE | 89.933473% | 97.144478% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| A13_momentumAcceleration21 | ALPHA_CANDIDATE | 92.099673% | 99.484367% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| A14_ma200Distance | ALPHA_CANDIDATE | 90.433007% | 97.684065% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| B01_bookToMarket | CONTROL | 63.704482% | 83.458716% | 2016-04-01 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| B02_earningsYield | CONTROL | 51.434407% | 67.383792% | 2016-04-01 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| B03_ocfYield | ALPHA_CANDIDATE | 51.073763% | 66.911315% | 2016-04-01 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| B04_freeCashFlowYield | ALPHA_CANDIDATE | 47.546685% | 62.29052% | 2016-04-01 ~ 2026-09-11 | 측정 완료·사용 가능 (얇음) |
| B05_industryRelativeValue | ALPHA_CANDIDATE | 53.336835% | 69.876147% | 2016-04-01 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| B06_ownHistoryValuation | ALPHA_CANDIDATE | 42.376284% | 68.609221% | 2018-04-06 ~ 2026-09-11 | 측정 완료·사용 가능 |
| B07_valuationChange126 | ALPHA_CANDIDATE | 57.561858% | 79.342021% | 2016-10-07 ~ 2026-09-11 | 측정 완료·사용 가능 |
| B08_valueBusinessConfirmation | ALPHA_CANDIDATE | 53.551864% | 69.067578% | 2016-04-01 ~ 2026-09-11 | 측정 완료·사용 가능 |
| C01_returnOnAssets | CONTROL | 51.547619% | 67.53211% | 2016-04-01 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| C02_returnOnEquity | ALPHA_CANDIDATE | 48.499066% | 63.538226% | 2016-04-01 ~ 2026-09-11 | 측정 완료·사용 가능 (얇음) |
| C03_operatingMargin | ALPHA_CANDIDATE | 41.373716% | 54.203364% | 2016-04-01 ~ 2026-09-11 | 측정했으나 기준 미달 |
| C04_profitMargin | ALPHA_CANDIDATE | 42.11718% | 55.17737% | 2016-04-01 ~ 2026-09-11 | 측정했으나 기준 미달 |
| C05_ocfToAssets | CONTROL | 51.206816% | 67.085627% | 2016-04-01 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| C06_cashConversion | ALPHA_CANDIDATE | 43.22479% | 56.62844% | 2016-04-01 ~ 2026-09-11 | 측정했으나 기준 미달 |
| C07_negativeAccruals | ALPHA_CANDIDATE | 49.915966% | 65.394495% | 2016-04-01 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| C08_netIncomeMinusOcf | ALPHA_CANDIDATE | 49.915966% | 65.394495% | 2016-04-01 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| C09_assetGrowth | ALPHA_CANDIDATE | 55.30112% | 80.238821% | 2017-04-07 ~ 2026-09-11 | 측정 완료·사용 가능 |
| C10_liabilityGrowth | ALPHA_CANDIDATE | 55.361811% | 80.326897% | 2017-04-07 ~ 2026-09-11 | 측정 완료·사용 가능 |
| C11_shareDilution | ALPHA_CANDIDATE | 43.516573% | 63.150407% | 2017-04-07 ~ 2026-09-11 | 측정 완료·사용 가능 (얇음) |
| C12_profitabilityPersistence | ALPHA_CANDIDATE | 41.538282% | 61.025377% | 2017-05-19 ~ 2026-09-11 | 측정 완료·사용 가능 (얇음) |
| C14_ocfImprovement | ALPHA_CANDIDATE | 43.450047% | 63.040312% | 2017-04-07 ~ 2026-09-11 | 기존 검증·비교용 계산 (얇음) |
| C15_capexIntensity | ALPHA_CANDIDATE | 40.375817% | 52.896024% | 2016-04-01 ~ 2026-09-11 | 측정했으나 기준 미달 |
| D01_volumeSurge5_60 | ALPHA_CANDIDATE | 96.653828% | 98.30603% | 2013-03-29 ~ 2026-09-11 | 측정 완료·사용 가능 |
| D02_logVolumeShock60 | ALPHA_CANDIDATE | 96.653828% | 98.30603% | 2013-03-29 ~ 2026-09-11 | 측정 완료·사용 가능 |
| D03_tradingValueShock5_60 | ALPHA_CANDIDATE | 96.653828% | 98.30603% | 2013-03-29 ~ 2026-09-11 | 측정 완료·사용 가능 |
| D04_shockPersistence5d | ALPHA_CANDIDATE | 96.418067% | 98.206134% | 2013-04-05 ~ 2026-09-11 | 측정 완료·사용 가능 |
| D05_turnoverToMarketCap60 | ALPHA_CANDIDATE | 96.590803% | 98.241928% | 2013-03-29 ~ 2026-09-11 | 측정 완료·사용 가능 |
| D06_priceVolumeDivergence | ALPHA_CANDIDATE | 95.669935% | 97.862942% | 2013-04-26 ~ 2026-09-11 | 측정 완료·사용 가능 |
| D07_volumePriceAlignment | ALPHA_CANDIDATE | 96.652661% | 98.304843% | 2013-03-29 ~ 2026-09-11 | 측정 완료·사용 가능 |
| D08_abnormalVolumeUpClose | ALPHA_CANDIDATE | 95.612745% | 97.804441% | 2013-04-26 ~ 2026-09-11 | 측정 완료·사용 가능 |
| D09_abnormalVolumeDownClose | ALPHA_CANDIDATE | 95.612745% | 97.804441% | 2013-04-26 ~ 2026-09-11 | 측정 완료·사용 가능 |
| D10_liquidityAcceleration | ALPHA_CANDIDATE | 93.521242% | 96.914611% | 2013-06-28 ~ 2026-09-11 | 측정 완료·사용 가능 |
| D11_accumulationDistributionProxy | ALPHA_CANDIDATE | 98.661298% | 99.217136% | 2013-02-01 ~ 2026-09-11 | 측정 완료·사용 가능 |
| E01_amihudIlliquidity60 | ALPHA_CANDIDATE | 96.626984% | 98.278727% | 2013-03-29 ~ 2026-09-11 | 측정 완료·사용 가능 |
| E02_logAdv60 | CONTROL | 96.751867% | 98.405745% | 2013-03-29 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| E03_capacityMedianTradedValue60 | COST_CAPACITY | 96.653828% | 98.30603% | 2013-03-29 ~ 2026-09-11 | 측정 완료·사용 가능 |
| E04_tradabilityGuard20 | ELIGIBILITY_FILTER | 99.326564% | 99.88615% | 2013-02-01 ~ 2026-09-11 | 측정 완료·사용 가능 |
| E05_highLowSpreadProxy | COST_CAPACITY | 98.670635% | 99.226526% | 2013-02-01 ~ 2026-09-11 | 측정 완료·사용 가능 |
| E06_volatilityConditionalOnVolume | ALPHA_CANDIDATE | 96.603641% | 98.254986% | 2013-03-29 ~ 2026-09-11 | 측정 완료·사용 가능 |
| E07_suspensionStaleRisk | ELIGIBILITY_FILTER | 99.326564% | 99.88615% | 2013-02-01 ~ 2026-09-11 | 측정 완료·사용 가능 |
| F01_totalVolatility63 | ALPHA_CANDIDATE | 91.860411% | 99.22592% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| F02_downsideVol126 | CONTROL | 94.940476% | 98.528343% | 2013-07-05 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| F03_beta252 | ALPHA_CANDIDATE | 89.933473% | 97.144478% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| F04_idiosyncraticVol | ALPHA_CANDIDATE | 89.933473% | 97.144478% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| F05_maxDrawdown252 | RISK_CONSTRUCTION | 89.940476% | 97.152042% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| F06_crashExposure | RISK_CONSTRUCTION | 89.933473% | 97.144478% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| F07_benchmarkCorrelation252 | RISK_CONSTRUCTION | 89.917134% | 97.126828% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| H01_industryRelMom126 | CONTROL | 67.507003% | 70.05814% | 2013-07-05 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| H02_industryRelMom63 | ALPHA_CANDIDATE | 74.848273% | 76.236329% | 2013-04-05 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| H03_industryBreadthAboveMA126 | ALPHA_CANDIDATE | 69.255369% | 71.872578% | 2013-07-05 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| H04_withinIndustryDispersion126 | CONTEXT_CONDITIONING | 69.180672% | 71.795058% | 2013-07-05 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| H05_crossIndustryDispersion | CONTEXT_CONDITIONING | 61.344538% | 67.697063% | 2013-07-05 ~ 2025-11-28 | 측정 완료·사용 가능 |
| H06_industryConcentrationTop1 | CONTEXT_CONDITIONING | 81.666667% | 81.666667% | 2013-01-04 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| H07_leadershipPersistence | CONTEXT_CONDITIONING | 54.481793% | 62.140575% | 2013-08-02 ~ 2025-08-01 | 측정 완료·사용 가능 (얇음) |
| H08_equalVsCapWeightIndustry | ALPHA_CANDIDATE | 67.507003% | 70.05814% | 2013-07-05 ~ 2026-09-11 | 측정 완료·사용 가능 |
| H09_marketBreadth | CONTEXT_CONDITIONING | 92.577031% | 100.0% | 2014-01-10 ~ 2026-09-11 | 측정 완료·사용 가능 |
| H10_marketConcentrationTop2 | CONTEXT_CONDITIONING | 100.0% | 100.0% | 2013-01-04 ~ 2026-09-11 | 측정 완료·사용 가능 |
| H11_industryEarningsContext | ALPHA_CANDIDATE | 44.605509% | 58.437309% | 2016-04-01 ~ 2026-09-11 | 기존 검증·비교용(기준 미달) |
| H12_industryValuationContext | ALPHA_CANDIDATE | 51.890756% | 67.981651% | 2016-04-01 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| I01_kospiTrendVolState | CONTEXT_CONDITIONING | 94.117647% | 100.0% | 2013-10-25 ~ 2026-09-11 | 기존 검증·비교용 계산 |
| J01_periodicFilingEvent | ALPHA_CANDIDATE | 69.227358% | 83.766949% | 2015-05-22 ~ 2026-09-11 | 측정 완료·사용 가능 |
| J05_shortSellingRegime | CONTEXT_CONDITIONING | 100.0% | 100.0% | 2013-01-04 ~ 2026-09-11 | 측정 완료·사용 가능 |

## 6개 상호작용 (Level 3) — 미래 수익률은 보지 않고 표본 충분성만 판정

| 상호작용 | 판정 | 평가 가능 주 | 결합 커버리지 | 사유 |
|---|---|---:|---:|---|
| X1_valueByBusinessConfirmation | 준비됨 | 447 | 53.486719% | 평가 가능 447주(기준 52주), 평가 구간 내 결합 커버리지 75.873184%(기준 60%), 표본 구간 2017-04-07 ~ 2026-09-11 |
| X2_momentumByAbnormalVolume | 준비됨 | 686 | 93.907563% | 평가 가능 686주(기준 52주), 평가 구간 내 결합 커버리지 97.456395%(기준 60%), 표본 구간 2013-07-05 ~ 2026-09-11 |
| X3_industryLeadershipByStockStrength | 준비됨 | 616 | 67.507003% | 평가 가능 616주(기준 52주), 평가 구간 내 결합 커버리지 70.036443%(기준 60%), 표본 구간 2013-07-05 ~ 2026-08-28 |
| X4_priceLeadershipByInvestorAccumulation | 출처 차단 | — | — | 구성 특성 G01_foreignNetBuying의 출처가 차단됨 — OHLCV 매집 지표(D11)로 대체하지 않음 |
| X5_volatilityByLiquidity | 준비됨 | 661 | 90.923203% | 평가 가능 661주(기준 52주), 평가 구간 내 결합 커버리지 98.213565%(기준 60%), 표본 구간 2014-01-10 ~ 2026-09-11 |
| X6_marketRegimeByRelativeMomentum | 준비됨 | 293 | 92.70775% | 평가 가능 293주(기준 52주), 평가 구간 내 결합 커버리지 98.501984%(기준 60%), 표본 구간 2013-10-25 ~ 2026-09-11 |

'얇음'은 기준을 통과했지만 여유가 5%p 미만이거나 평가 가능 주가 104주 미만이라는 뜻입니다.

## 비교 기준선 (Level 2)

| 기준선 | 판정 | 기준 미달 구성원 | 구성원 전부가 있는 비율(공통 기간) |
|---|---|---|---:|
| B0_MARKET_INDUSTRY_PRICE_REFERENCE | 준비됨 | — | 69.748062% |
| B1_VALUE_PROFITABILITY | 준비됨 | — | 65.206422% |
| B2_PRICE_MOMENTUM | 준비됨 | — | 97.144478% |
| B3_VOLUME_LIQUIDITY | 준비됨 | — | 98.214625% |
| B4_COMBINED_SIMPLE | 준비됨 | — | 44.319572% |

## 계산했지만 등록 당시 '데이터 구축 필요'였거나 기준에 못 미친 특성 (출처 장애 아님)

| 특성 | 등록 당시 상태 | 구현 | 측정 판정 | 사용 범위 내 커버리지 | 출처 장애 |
|---|---|---|---:|---:|---|
| B04_freeCashFlowYield | DATA_BUILD_REQUIRED | IMPLEMENTED | 측정 완료·사용 가능 (얇음) | 62.29% | 없음 |
| C03_operatingMargin | READY | IMPLEMENTED | 측정했으나 기준 미달 | 54.20% | 없음 |
| C04_profitMargin | READY | IMPLEMENTED | 측정했으나 기준 미달 | 55.18% | 없음 |
| C06_cashConversion | DATA_BUILD_REQUIRED | IMPLEMENTED | 측정했으나 기준 미달 | 56.63% | 없음 |
| C15_capexIntensity | DATA_BUILD_REQUIRED | IMPLEMENTED | 측정했으나 기준 미달 | 52.90% | 없음 |
| H11_industryEarningsContext | ALREADY_TESTED | COMPUTED_ALREADY_TESTED | 기존 검증·비교용(기준 미달) | 58.44% | 없음 |

등록부에 적힌 당시의 기대('KR 설비투자 7.74%' 등)는 설계 시점 메모이며, 이번 측정(고정된 후보 병합 저장소)이 그것을 대체합니다. 두 저장소는 서로 다른 대상이라 등록부 메모는 고치지 않았습니다.

## 계산하지 못한 특성과 데이터 출처 (진짜 장애만)

- **G01_foreignNetBuying, G02_institutionalNetBuying, G03_retailNetBuying, G04_investorTypePersistence, G05_flowMomentumConfirmation** — SOURCE_BLOCKED: 출처가 막혀 있어 계산하지 않았고, 다른 지표로 대체하지 않습니다.
- **G08_shortSellingVolume, G09_shortBalanceChange** — SOURCE_BLOCKED: 출처가 막혀 있어 계산하지 않았고, 다른 지표로 대체하지 않습니다.
- **G06_largeHolderAccumulation, G07_largeHolderReduction** — PIT_SAFE_BUT_HISTORY_TOO_SHORT: 시점은 안전하지만 제공 기간이 2024-09부터라 과거 평가가 불가능하고, '행 없음'이 '공시 없음'을 뜻하지 않아 0으로 읽을 수 없습니다. 앞으로 쌓아 가는 대상입니다.
- **J02_dividendPolicyChange, J03_buybackAnnouncement, J04_materialDisclosure** — DATA_BUILD_REQUIRED: 수집·구축이 더 필요해 이번에 계산하지 않았습니다.
- **I04_krPolicyRate** — SOURCE_AVAILABLE_NOT_COMPUTED: 저장소에 날짜가 붙은 정책금리 파일이 있어 시점 안전하게 만들 수 있지만, 등록된 비교가 읽지 않아 계산하지 않았습니다(정책금리 대용치이며 투자 가능한 금리가 아닙니다).
- **I03_krTermSpread, I06_krInflation, I07_krExportsActivity, I08_usdKrw, I09_fxBeta26w, I11_globalFinancialConditions** — PIT_UNSAFE: 수정된 값만 제공되거나 공표 시각이 확정되지 않아 시점 안전하지 않습니다.
- **C16_grossProfitability** — DATA_BUILD_REQUIRED: 수집·구축이 더 필요해 이번에 계산하지 않았습니다.
- **I05_krCreditSpread** — DATA_BUILD_REQUIRED: 수집·구축이 더 필요해 이번에 계산하지 않았습니다.
- **I10_semiconductorCycleSOX, I12_commodityExposure** — DATA_BUILD_REQUIRED: 수집·구축이 더 필요해 이번에 계산하지 않았습니다.
- **E08_trueBidAskSpread, J06_searchAttention, J07_newsTextSentiment, J08_analystRevisions** — NOT_FEASIBLE: 시점 기준으로 쓸 수 있는 출처가 없습니다.

외국인·기관 순매수와 공매도는 최신 기록(2026-09-24T06:23:26Z)에서도 KRX 포털이 접근을 거부해(`REFUSED: HTTP 400: b'LOGOUT'`) **출처 차단**으로 유지합니다. 이번 단계에서 다시 확인하지 않았고, 일봉으로 만든 매집 지표(D11)를 투자자 수급 대용으로 쓰지 않습니다. 한 번 더 확인하려면 Actions의 `Probes` 워크플로우에서 `probe=kr-investor-flow` 또는 `kr-short-selling`을 선택해 실행합니다.

## 더 넓은 유니버스 가능성 (평가만 함, Phase C에는 넣지 않음)

- 판정: **상위 120 기준 유지 — 더 넓은 유니버스는 아직 준비되지 않음** (`BROADER_UNIVERSE_NOT_READY_KEEP_TOP120`)
- 유동성 기준을 통과하는 종목 중 상위 120 밖은 평균 196개이지만, 그 종목-월 중 봉인된 저장소에 보이는 DART 공시가 있는 비율은 34.0%뿐이고, 가격 패널·산업 라벨·상장폐지 대가 자료도 없습니다.
- 유동성 기준(60거래일 거래대금 중앙값 10억 원) 통과 종목 중 상위 120 밖은 연도별로 아래와 같습니다.

| 연도 | 통과 종목(평균) | 상위120 밖(평균) | 밖 종목의 DART 공시 보유 | 밖 종목의 산업 라벨 |
|---|---:|---:|---:|---:|
| 2014 | 256.9 | 139.2 | 0.0% | 34.25% |
| 2015 | 305.7 | 188.1 | 20.69% | 29.51% |
| 2016 | 291.8 | 173.8 | 32.36% | 31.4% |
| 2017 | 278.3 | 163.0 | 36.96% | 36.61% |
| 2018 | 302.1 | 185.3 | 37.05% | 37.46% |
| 2019 | 273.8 | 155.7 | 41.22% | 41.65% |
| 2020 | 328.1 | 209.7 | 35.61% | 36.53% |
| 2021 | 407.7 | 291.5 | 29.96% | 31.28% |
| 2022 | 331.6 | 212.2 | 38.83% | 40.87% |
| 2023 | 309.8 | 191.0 | 42.54% | 43.59% |
| 2024 | 309.2 | 190.7 | 44.71% | 44.32% |
| 2025 | 324.6 | 205.8 | 42.61% | 42.37% |
| 2026 | 358.9 | 240.1 | 39.7% | 39.84% |

- 추가 DART 수집이 필요한 종목 335개(수집기 호출 구조로 계산한 **추정 상한** 약 48,240회, 1회 실행 1,500회 기준 최대 33회 실행). 가격 패널·산업 분류·상장폐지 대가 자료도 별도로 필요합니다.

## 시점·생존편향 한계

- 한국 과거 데이터는 모두 이미 결과가 공개된 기간(2026-09-14까지)이라, 이후 평가에서 무엇이 나와도 확인이 아니라 탐색적 개발 증거입니다.
- 산업 라벨은 벤더의 과거 분류가 아니라 현재 분류와 검증된 변경 이력으로 재구성한 것입니다(상장폐지 22개 종목은 분류 없음).
- DART 재무는 2013~2015년이 비어 있고 2016년도 대부분 비어 있습니다. 금융업은 매출·영업이익 계정이 거의 없어 마진·현금전환·설비투자 계열이 기준에 못 미칩니다.
- 유니버스는 신호일보다 앞선 월별 스냅샷의 시가총액 상위 120종목입니다. 오늘 살아남은 종목으로 과거를 채우지 않았습니다.
- 상장폐지 22개 종목은 종결 대가(교환비율 등)가 `BLOCKED`입니다. 수익률 라벨을 만드는 단계에서 이 종목들을 어떻게 다룰지는 Phase C 등록에서 정해야 하며, 이번에 고치지 않았습니다.
- 액면분할은 '가격이 정수 비율로 변했다'는 사실은 당일 알 수 있지만, 상장주식수 갱신이 늦어 확정은 며칠~몇 주 뒤입니다. 확정 전 창은 값을 보정하지 않고 비워 두었습니다(`UNCONFIRMED_CORPORATE_ACTION_IN_WINDOW`).
- 가격 계열(`replay-v16`)은 분할을 사후 확정으로 보정해 만든 것입니다. 같은 이유로 확정 전 창은 비웠지만, 이 입력 자체가 신호일 시점의 재현이 아니라는 점은 남는 한계입니다.
- 벤치마크 `069500.KS`의 외부 대조는 `BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED` 상태입니다.

## Phase C 전에 남은 일

- Phase C registration PR: freeze this manifest's identity, the eligible list, baselines B0-B4, horizons, Level 1-3 statistics, costs and verdict table BEFORE any outcome (docs/kr-alpha-atlas-methodology.md section 9)
- decide, before registering, whether the evaluation runs on the close x volume traded-value proxy used here or on the official KRX ACC_TRDVAL held only in the preserved raw-input artifact; the choice is frozen in the registration, never made after a result
- build the label engine and the date-balanced baseline model OUTSIDE the sealed closures (the same arrangement alpha-opportunity-model-v4/v5 used); none exists yet
- interactions not READY are reported BLOCKED or INSUFFICIENT_COVERAGE in the evaluation, not repaired: X4_priceLeadershipByInvestorAccumulation

## 사람이 직접 실행해야 하는 절차 (필수 아님)

- **OFFICIAL_TRADED_VALUE_RERUN** (필수 여부: ONLY_IF_THE_PHASE_C_REGISTRATION_CHOOSES_OFFICIAL_ACC_TRDVAL) — traded value in this report is the as-traded close x volume proxy; the official KRX ACC_TRDVAL exists only in the preserved raw-input artifact
  - download the Actions artifact kr-model-raw-inputs-36844599518 (artifact id 11157875265, archive sha256 42eeb18b7a5c88816629036f472a93057b6a9be4768ad47292ba0d2750b4cce7, run 36844599518) and extract it to an empty directory <ART>
  - python scripts/build_kr_alpha_atlas_phase_b.py --scratch <ART>   (the loader finds market/ and uses the official values; the git-pinned files it verifies are identical)
  - compare tradingValueBasis and the matrix digest in the new report with this one; commit the new outputs as a separate revision, never over this one silently
- **OPTIONAL_REPROBE_INVESTOR_FLOW** (필수 여부: NO) — latest evidence (signal-history manifest, 2026-09-24) is REFUSED: HTTP 400 LOGOUT with 0 records; it is sufficient, so none was repeated
  - Actions > Probes > Run workflow: probe=kr-investor-flow, args empty (https://github.com/jaehojung1879-netizen/Investment/actions/workflows/probes.yml)
  - anything other than SERVED leaves G01-G05 SOURCE_BLOCKED; at most ONE re-probe per source in Phase B
- **OPTIONAL_REPROBE_SHORT_SELLING** (필수 여부: NO) — same as above for KRX short-selling statistics
  - Actions > Probes > Run workflow: probe=kr-short-selling, args empty
