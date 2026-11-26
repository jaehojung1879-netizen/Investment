# 전체 이동블록 결과표

수익률과 수익 차이는 % 또는 %p다. 대괄호는 명목 95% 구간이며, 원 주간축의 유효 날짜를 평가했다. 각 행의 식별자는 시장별 원본 JSON 경로다. 다중비교 처리는 한국의 6개월 주 가설 세 개에 적용한다.

[첫 장 핵심 비교](REPORT-ko.md) · [미국 귀속 세부](US-ko.md) · [한국 필터 세부](KR-ko.md)

## US

|원본 결과 경로|유효 주|주÷블록 길이|평균 [95% 구간]|
|---|---|---|---|
|horizons/126/baseline/dateTiming/decisionCloseMinusNextCloseNet|630|25.2|-0.01 [-0.02, +0.00]|
|horizons/126/baseline/dateTiming/decisionCloseNetExcess|630|25.2|+0.52 [+0.27, +0.81]|
|horizons/126/baseline/dateTiming/netExcess|630|25.2|+0.53 [+0.28, +0.82]|
|horizons/126/baseline/netExcessVsQQQ|630|25.2|-2.35 [-4.07, -0.59]|
|horizons/126/baseline/netGross/costNetMinusGross|630|25.2|-0.00 [-0.00, -0.00]|
|horizons/126/baseline/netGross/grossB|630|25.2|+7.56 [+4.84, +10.16]|
|horizons/126/baseline/netGross/grossExcess|630|25.2|+0.53 [+0.28, +0.83]|
|horizons/126/baseline/netGross/grossSPY|630|25.2|+7.03 [+4.33, +9.58]|
|horizons/126/baseline/netGross/netB|630|25.2|+7.39 [+4.67, +9.98]|
|horizons/126/baseline/netGross/netExcess|630|25.2|+0.53 [+0.28, +0.82]|
|horizons/126/baseline/netGross/netSPY|630|25.2|+6.86 [+4.16, +9.40]|
|horizons/126/baseline/netGross/originalPriceConfirmedActive|630|25.2|+0.04 [-0.31, +0.36]|
|horizons/126/baseline/netGross/originalPriceConfirmedFunded|630|25.2|+0.57 [+0.15, +0.95]|
|horizons/126/baseline/spyOnlySealedMinusYahooAdjusted|630|25.2|-0.00 [-0.00, +0.00]|
|horizons/126/baseline/yahooPaths/grossExcess|630|25.2|+0.53 [+0.28, +0.83]|
|horizons/126/baseline/yahooPaths/grossMinusYahooAdjusted|630|25.2|-0.00 [-0.01, -0.00]|
|horizons/126/baseline/yahooPaths/grossMinusYahooRaw|630|25.2|+0.04 [+0.01, +0.07]|
|horizons/126/baseline/yahooPaths/sealedMinusYahooAdjustedB|630|25.2|-0.00 [-0.01, -0.00]|
|horizons/126/baseline/yahooPaths/sealedMinusYahooAdjustedSPY|630|25.2|-0.00 [-0.00, +0.00]|
|horizons/126/baseline/yahooPaths/yahooAdjustedExcess|630|25.2|+0.54 [+0.28, +0.83]|
|horizons/126/baseline/yahooPaths/yahooDistributionB|630|25.2|+0.94 [+0.85, +1.02]|
|horizons/126/baseline/yahooPaths/yahooDistributionGap|630|25.2|+0.04 [+0.01, +0.08]|
|horizons/126/baseline/yahooPaths/yahooDistributionSPY|630|25.2|+0.89 [+0.83, +0.96]|
|horizons/126/baseline/yahooPaths/yahooPriceOnlyExcess|630|25.2|+0.49 [+0.23, +0.80]|
|horizons/126/bridge/allBaseline|630|25.2|+0.53 [+0.28, +0.82]|
|horizons/126/bridge/endpointObserved/components/megaWithinSectorWeight|329|13.16|+0.11 [+0.01, +0.22]|
|horizons/126/bridge/endpointObserved/components/proxyNetExcess|329|13.16|+0.36 [+0.01, +0.77]|
|horizons/126/bridge/endpointObserved/components/proxyOutsideCommon|329|13.16|-0.07 [-0.20, +0.08]|
|horizons/126/bridge/endpointObserved/components/reportNamesOutsideProxy|329|13.16|+0.12 [-0.18, +0.46]|
|horizons/126/bridge/endpointObserved/components/reportResidual|329|13.16|+0.05 [-0.32, +0.43]|
|horizons/126/bridge/endpointObserved/components/sectorAndMegaWeight|329|13.16|+0.16 [-0.11, +0.45]|
|horizons/126/bridge/endpointObserved/components/sectorWeightOnly|329|13.16|+0.05 [-0.17, +0.27]|
|horizons/126/bridge/endpointObserved/components/withinCellWeight|329|13.16|+0.10 [-0.09, +0.32]|
|horizons/126/bridge/endpointObserved/fullOriginalSampleAttribution/outsideBridge|301|12.04|+0.71 [+0.41, +1.14]|
|horizons/126/bridge/strict/components/megaWithinSectorWeight|329|13.16|+0.11 [+0.01, +0.22]|
|horizons/126/bridge/strict/components/proxyNetExcess|329|13.16|+0.36 [+0.01, +0.77]|
|horizons/126/bridge/strict/components/proxyOutsideCommon|329|13.16|-0.07 [-0.20, +0.08]|
|horizons/126/bridge/strict/components/reportNamesOutsideProxy|329|13.16|+0.12 [-0.18, +0.46]|
|horizons/126/bridge/strict/components/reportResidual|329|13.16|+0.05 [-0.32, +0.43]|
|horizons/126/bridge/strict/components/sectorAndMegaWeight|329|13.16|+0.16 [-0.11, +0.45]|
|horizons/126/bridge/strict/components/sectorWeightOnly|329|13.16|+0.05 [-0.17, +0.27]|
|horizons/126/bridge/strict/components/withinCellWeight|329|13.16|+0.10 [-0.09, +0.32]|
|horizons/126/bridge/strict/fullOriginalSampleAttribution/outsideBridge|301|12.04|+0.71 [+0.41, +1.14]|
|horizons/126/bridge/withPublishedReport|329|13.16|+0.36 [+0.01, +0.77]|
|horizons/126/bridge/withoutPublishedReport|301|12.04|+0.71 [+0.41, +1.14]|
|horizons/126/sensitivity/scenarios/entry2021Only|52|2.08|+0.32 [-0.56, +0.85]|
|horizons/126/sensitivity/scenarios/maxEntryYearOnly|52|2.08|+1.78 [+0.83, +2.44]|
|horizons/126/sensitivity/scenarios/maxTickerActiveContribution|630|25.2|+0.38 [+0.16, +0.67]|
|horizons/126/sensitivity/scenarios/megaContribution|630|25.2|+1.37 [+0.64, +2.18]|
|horizons/126/sensitivity/scenarios/no2021Entry|578|23.12|+0.55 [+0.29, +0.86]|
|horizons/126/sensitivity/scenarios/noMaxEntryYear|578|23.12|+0.42 [+0.19, +0.69]|
|horizons/126/sensitivity/scenarios/noMaxTickerContribution|630|25.2|+0.15 [-0.22, +0.50]|
|horizons/126/sensitivity/scenarios/noMegaContribution|630|25.2|-0.84 [-1.50, -0.23]|
|horizons/252/baseline/dateTiming/decisionCloseMinusNextCloseNet|604|12.08|-0.01 [-0.03, -0.00]|
|horizons/252/baseline/dateTiming/decisionCloseNetExcess|604|12.08|+1.01 [+0.44, +1.70]|
|horizons/252/baseline/dateTiming/netExcess|604|12.08|+1.03 [+0.46, +1.72]|
|horizons/252/baseline/netExcessVsQQQ|604|12.08|-5.08 [-8.78, -1.33]|
|horizons/252/baseline/netGross/costNetMinusGross|604|12.08|-0.00 [-0.00, -0.00]|
|horizons/252/baseline/netGross/grossB|604|12.08|+15.50 [+9.96, +21.25]|
|horizons/252/baseline/netGross/grossExcess|604|12.08|+1.03 [+0.46, +1.72]|
|horizons/252/baseline/netGross/grossSPY|604|12.08|+14.47 [+9.13, +20.14]|
|horizons/252/baseline/netGross/netB|604|12.08|+15.31 [+9.78, +21.05]|
|horizons/252/baseline/netGross/netExcess|604|12.08|+1.03 [+0.46, +1.72]|
|horizons/252/baseline/netGross/netSPY|604|12.08|+14.28 [+8.95, +19.95]|
|horizons/252/baseline/netGross/originalPriceConfirmedActive|604|12.08|-0.11 [-0.92, +0.49]|
|horizons/252/baseline/netGross/originalPriceConfirmedFunded|604|12.08|+0.91 [-0.07, +1.71]|
|horizons/252/baseline/spyOnlySealedMinusYahooAdjusted|604|12.08|+0.00 [-0.00, +0.00]|
|horizons/252/baseline/yahooPaths/grossExcess|604|12.08|+1.03 [+0.46, +1.72]|
|horizons/252/baseline/yahooPaths/grossMinusYahooAdjusted|604|12.08|-0.01 [-0.02, -0.00]|
|horizons/252/baseline/yahooPaths/grossMinusYahooRaw|604|12.08|+0.08 [-0.01, +0.16]|
|horizons/252/baseline/yahooPaths/sealedMinusYahooAdjustedB|604|12.08|-0.01 [-0.02, -0.00]|
|horizons/252/baseline/yahooPaths/sealedMinusYahooAdjustedSPY|604|12.08|+0.00 [-0.00, +0.00]|
|horizons/252/baseline/yahooPaths/yahooAdjustedExcess|604|12.08|+1.04 [+0.46, +1.73]|
|horizons/252/baseline/yahooPaths/yahooDistributionB|604|12.08|+2.00 [+1.76, +2.22]|
|horizons/252/baseline/yahooPaths/yahooDistributionGap|604|12.08|+0.09 [-0.01, +0.18]|
|horizons/252/baseline/yahooPaths/yahooDistributionSPY|604|12.08|+1.91 [+1.71, +2.08]|
|horizons/252/baseline/yahooPaths/yahooPriceOnlyExcess|604|12.08|+0.95 [+0.38, +1.66]|
|horizons/252/bridge/allBaseline|604|12.08|+1.03 [+0.46, +1.72]|
|horizons/252/bridge/endpointObserved/components/megaWithinSectorWeight|303|6.06|+0.15 [-0.03, +0.33]|
|horizons/252/bridge/endpointObserved/components/proxyNetExcess|303|6.06|+0.41 [-0.11, +1.04]|
|horizons/252/bridge/endpointObserved/components/proxyOutsideCommon|303|6.06|-0.06 [-0.23, +0.16]|
|horizons/252/bridge/endpointObserved/components/reportNamesOutsideProxy|303|6.06|-0.13 [-0.69, +0.48]|
|horizons/252/bridge/endpointObserved/components/reportResidual|303|6.06|+0.38 [-0.19, +0.88]|
|horizons/252/bridge/endpointObserved/components/sectorAndMegaWeight|303|6.06|+0.26 [-0.29, +0.80]|
|horizons/252/bridge/endpointObserved/components/sectorWeightOnly|303|6.06|+0.11 [-0.32, +0.55]|
|horizons/252/bridge/endpointObserved/components/withinCellWeight|303|6.06|-0.05 [-0.37, +0.23]|
|horizons/252/bridge/endpointObserved/fullOriginalSampleAttribution/outsideBridge|301|6.02|+1.66 [+0.88, +2.77]|
|horizons/252/bridge/strict/components/megaWithinSectorWeight|303|6.06|+0.15 [-0.03, +0.33]|
|horizons/252/bridge/strict/components/proxyNetExcess|303|6.06|+0.41 [-0.11, +1.04]|
|horizons/252/bridge/strict/components/proxyOutsideCommon|303|6.06|-0.06 [-0.23, +0.16]|
|horizons/252/bridge/strict/components/reportNamesOutsideProxy|303|6.06|-0.13 [-0.69, +0.48]|
|horizons/252/bridge/strict/components/reportResidual|303|6.06|+0.38 [-0.19, +0.88]|
|horizons/252/bridge/strict/components/sectorAndMegaWeight|303|6.06|+0.26 [-0.29, +0.80]|
|horizons/252/bridge/strict/components/sectorWeightOnly|303|6.06|+0.11 [-0.32, +0.55]|
|horizons/252/bridge/strict/components/withinCellWeight|303|6.06|-0.05 [-0.37, +0.23]|
|horizons/252/bridge/strict/fullOriginalSampleAttribution/outsideBridge|301|6.02|+1.66 [+0.88, +2.77]|
|horizons/252/bridge/withPublishedReport|303|6.06|+0.41 [-0.11, +1.04]|
|horizons/252/bridge/withoutPublishedReport|301|6.02|+1.66 [+0.88, +2.77]|
|horizons/252/sensitivity/scenarios/entry2021Only|52|1.04|-0.04 [구간 미측정]|
|horizons/252/sensitivity/scenarios/maxEntryYearOnly|52|1.04|+3.28 [구간 미측정]|
|horizons/252/sensitivity/scenarios/maxTickerActiveContribution|604|12.08|+0.82 [+0.30, +1.51]|
|horizons/252/sensitivity/scenarios/megaContribution|604|12.08|+2.95 [+1.63, +4.43]|
|horizons/252/sensitivity/scenarios/no2021Entry|552|11.04|+1.13 [+0.52, +1.83]|
|horizons/252/sensitivity/scenarios/noMaxEntryYear|552|11.04|+0.82 [+0.32, +1.42]|
|horizons/252/sensitivity/scenarios/noMaxTickerContribution|604|12.08|+0.21 [-0.74, +1.15]|
|horizons/252/sensitivity/scenarios/noMegaContribution|604|12.08|-1.92 [-3.22, -0.71]|

## KR

|원본 결과 경로|유효 주|주÷블록 길이|평균 [95% 구간]|
|---|---|---|---|
|horizons/126/whole/matched20/etfNet|414|16.56|+12.73 [+1.59, +26.57]|
|horizons/126/whole/matched20/passNet|414|16.56|+12.33 [+1.88, +25.19]|
|horizons/126/whole/matched20/failNet|414|16.56|+11.79 [+1.51, +24.40]|
|horizons/126/whole/matched20/selection|414|16.56|+0.54 [-0.53, +1.52]|
|horizons/126/whole/matched20/replacement|414|16.56|-0.93 [-2.59, +0.39]|
|horizons/126/whole/matched20/total|414|16.56|-0.39 [-1.69, +0.69]|
|horizons/126/whole/matched100/etfNet|414|16.56|+12.73 [+1.59, +26.57]|
|horizons/126/whole/matched100/passNet|414|16.56|+10.76 [+2.48, +20.60]|
|horizons/126/whole/matched100/failNet|414|16.56|+8.06 [-0.39, +17.50]|
|horizons/126/whole/matched100/selection|414|16.56|+2.70 [-2.65, +7.60]|
|horizons/126/whole/matched100/replacement|414|16.56|-4.67 [-12.97, +1.96]|
|horizons/126/whole/matched100/total|414|16.56|-1.96 [-8.47, +3.45]|
|horizons/126/whole/allPass20/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/whole/allPass20/passNet|427|17.08|+11.39 [+1.55, +24.50]|
|horizons/126/whole/allPass20/total|427|17.08|-0.73 [-2.04, +0.25]|
|horizons/126/whole/allPass20/stockOnlyTotal|427|17.08|-3.64 [-10.19, +1.26]|
|horizons/126/whole/allPass20OnMatchedDates/etfNet|414|16.56|+12.73 [+1.59, +26.57]|
|horizons/126/whole/allPass20OnMatchedDates/passNet|414|16.56|+11.98 [+1.58, +24.63]|
|horizons/126/whole/allPass20OnMatchedDates/total|414|16.56|-0.75 [-2.06, +0.26]|
|horizons/126/whole/allPass20OnMatchedDates/stockOnlyTotal|414|16.56|-3.74 [-10.32, +1.30]|
|horizons/126/whole/allPass20OnK5Dates/etfNet|60|2.4|+23.67 [+3.59, +44.95]|
|horizons/126/whole/allPass20OnK5Dates/passNet|60|2.4|+22.75 [+4.14, +41.54]|
|horizons/126/whole/allPass20OnK5Dates/total|60|2.4|-0.93 [-3.70, +1.06]|
|horizons/126/whole/allPass20OnK5Dates/stockOnlyTotal|60|2.4|-4.63 [-18.48, +5.28]|
|horizons/126/whole/matched20OnK5Dates/etfNet|60|2.4|+23.67 [+3.59, +44.95]|
|horizons/126/whole/matched20OnK5Dates/passNet|60|2.4|+23.14 [+4.54, +42.07]|
|horizons/126/whole/matched20OnK5Dates/failNet|60|2.4|+21.52 [+3.49, +39.99]|
|horizons/126/whole/matched20OnK5Dates/selection|60|2.4|+1.62 [+0.43, +2.56]|
|horizons/126/whole/matched20OnK5Dates/replacement|60|2.4|-2.15 [-5.28, +0.12]|
|horizons/126/whole/matched20OnK5Dates/total|60|2.4|-0.54 [-3.49, +1.75]|
|horizons/126/whole/matched20OnFullyMatchedDates/etfNet|0|0.0|미측정|
|horizons/126/whole/matched20OnFullyMatchedDates/passNet|0|0.0|미측정|
|horizons/126/whole/matched20OnFullyMatchedDates/failNet|0|0.0|미측정|
|horizons/126/whole/matched20OnFullyMatchedDates/selection|0|0.0|미측정|
|horizons/126/whole/matched20OnFullyMatchedDates/replacement|0|0.0|미측정|
|horizons/126/whole/matched20OnFullyMatchedDates/total|0|0.0|미측정|
|horizons/126/whole/exLeadersDates/etfNet|350|14.0|+13.87 [+1.06, +30.25]|
|horizons/126/whole/exLeadersDates/passNet|350|14.0|+13.29 [+1.22, +28.41]|
|horizons/126/whole/exLeadersDates/failNet|350|14.0|+12.53 [+0.74, +27.27]|
|horizons/126/whole/exLeadersDates/selection|350|14.0|+0.75 [-0.31, +1.75]|
|horizons/126/whole/exLeadersDates/replacement|350|14.0|-1.34 [-3.21, +0.09]|
|horizons/126/whole/exLeadersDates/total|350|14.0|-0.59 [-1.98, +0.64]|
|horizons/126/whole/leaderDatesOnly/etfNet|64|2.56|+6.45 [-3.23, +20.08]|
|horizons/126/whole/leaderDatesOnly/passNet|64|2.56|+7.12 [-1.78, +19.25]|
|horizons/126/whole/leaderDatesOnly/failNet|64|2.56|+7.75 [-2.38, +22.24]|
|horizons/126/whole/leaderDatesOnly/selection|64|2.56|-0.63 [-3.19, +0.87]|
|horizons/126/whole/leaderDatesOnly/replacement|64|2.56|+1.30 [-0.27, +2.74]|
|horizons/126/whole/leaderDatesOnly/total|64|2.56|+0.67 [-1.15, +1.68]|
|horizons/126/whole/exLeadersPairs/etfNet|414|16.56|+12.73 [+1.59, +26.57]|
|horizons/126/whole/exLeadersPairs/passNet|414|16.56|+12.37 [+1.91, +25.24]|
|horizons/126/whole/exLeadersPairs/failNet|414|16.56|+11.75 [+1.47, +24.36]|
|horizons/126/whole/exLeadersPairs/selection|414|16.56|+0.62 [-0.46, +1.59]|
|horizons/126/whole/exLeadersPairs/replacement|414|16.56|-0.98 [-2.62, +0.34]|
|horizons/126/whole/exLeadersPairs/total|414|16.56|-0.36 [-1.67, +0.74]|
|horizons/126/whole/semiLed/etfNet|199|7.96|+19.76 [+2.30, +42.84]|
|horizons/126/whole/semiLed/passNet|199|7.96|+18.32 [+2.26, +39.62]|
|horizons/126/whole/semiLed/failNet|199|7.96|+17.19 [+1.65, +37.67]|
|horizons/126/whole/semiLed/selection|199|7.96|+1.13 [+0.29, +2.11]|
|horizons/126/whole/semiLed/replacement|199|7.96|-2.58 [-5.56, -0.12]|
|horizons/126/whole/semiLed/total|199|7.96|-1.44 [-3.51, +0.25]|
|horizons/126/whole/nonSemiLed/etfNet|203|8.12|+7.40 [-3.61, +19.35]|
|horizons/126/whole/nonSemiLed/passNet|203|8.12|+7.99 [-2.70, +19.56]|
|horizons/126/whole/nonSemiLed/failNet|203|8.12|+7.99 [-3.54, +20.55]|
|horizons/126/whole/nonSemiLed/selection|203|8.12|+0.00 [-1.91, +1.76]|
|horizons/126/whole/nonSemiLed/replacement|203|8.12|+0.59 [-0.22, +1.53]|
|horizons/126/whole/nonSemiLed/total|203|8.12|+0.59 [-0.66, +1.87]|
|horizons/126/whole/unknownSemi/etfNet|12|0.48|-13.91 [구간 미측정]|
|horizons/126/whole/unknownSemi/passNet|12|0.48|-13.46 [구간 미측정]|
|horizons/126/whole/unknownSemi/failNet|12|0.48|-13.33 [구간 미측정]|
|horizons/126/whole/unknownSemi/selection|12|0.48|-0.13 [구간 미측정]|
|horizons/126/whole/unknownSemi/replacement|12|0.48|+0.58 [구간 미측정]|
|horizons/126/whole/unknownSemi/total|12|0.48|+0.45 [구간 미측정]|
|horizons/126/whole/exTopEntryYear/etfNet|362|14.48|+4.19 [-1.48, +11.19]|
|horizons/126/whole/exTopEntryYear/passNet|362|14.48|+4.24 [-1.14, +10.81]|
|horizons/126/whole/exTopEntryYear/failNet|362|14.48|+4.10 [-1.76, +11.40]|
|horizons/126/whole/exTopEntryYear/selection|362|14.48|+0.14 [-0.93, +1.08]|
|horizons/126/whole/exTopEntryYear/replacement|362|14.48|-0.09 [-0.97, +0.72]|
|horizons/126/whole/exTopEntryYear/total|362|14.48|+0.05 [-0.76, +0.84]|
|horizons/126/whole/exTopTotalEntryYear/etfNet|361|14.44|+14.54 [+2.15, +30.48]|
|horizons/126/whole/exTopTotalEntryYear/passNet|361|14.44|+13.67 [+2.09, +28.44]|
|horizons/126/whole/exTopTotalEntryYear/failNet|361|14.44|+13.37 [+1.95, +27.47]|
|horizons/126/whole/exTopTotalEntryYear/selection|361|14.44|+0.30 [-0.86, +1.29]|
|horizons/126/whole/exTopTotalEntryYear/replacement|361|14.44|-1.17 [-3.06, +0.28]|
|horizons/126/whole/exTopTotalEntryYear/total|361|14.44|-0.87 [-2.16, +0.13]|
|horizons/126/whole/ownExLeadersDates/etfNet|146|5.84|+4.97 [-3.63, +17.13]|
|horizons/126/whole/ownExLeadersDates/passNet|146|5.84|+4.87 [-3.08, +16.13]|
|horizons/126/whole/ownExLeadersDates/total|146|5.84|-0.10 [-1.27, +1.06]|
|horizons/126/whole/ownExLeadersDates/stockOnlyTotal|146|5.84|-0.50 [-6.36, +5.31]|
|horizons/126/whole/ownSemiLed/etfNet|199|7.96|+19.76 [+2.30, +42.84]|
|horizons/126/whole/ownSemiLed/passNet|199|7.96|+18.08 [+2.17, +39.29]|
|horizons/126/whole/ownSemiLed/total|199|7.96|-1.68 [-3.89, +0.06]|
|horizons/126/whole/ownSemiLed/stockOnlyTotal|199|7.96|-8.42 [-19.47, +0.32]|
|horizons/126/whole/ownNonSemiLed/etfNet|203|8.12|+7.40 [-3.61, +19.35]|
|horizons/126/whole/ownNonSemiLed/passNet|203|8.12|+7.47 [-3.16, +18.99]|
|horizons/126/whole/ownNonSemiLed/total|203|8.12|+0.06 [-0.90, +0.97]|
|horizons/126/whole/ownNonSemiLed/stockOnlyTotal|203|8.12|+0.32 [-4.51, +4.84]|
|horizons/126/whole/ownUnknownSemi/etfNet|25|1.0|-10.46 [구간 미측정]|
|horizons/126/whole/ownUnknownSemi/passNet|25|1.0|-10.02 [구간 미측정]|
|horizons/126/whole/ownUnknownSemi/total|25|1.0|+0.44 [구간 미측정]|
|horizons/126/whole/ownUnknownSemi/stockOnlyTotal|25|1.0|+2.19 [구간 미측정]|
|horizons/126/whole/ownExTopEntryYear/etfNet|374|14.96|+13.78 [+2.02, +30.20]|
|horizons/126/whole/ownExTopEntryYear/passNet|374|14.96|+12.65 [+1.71, +27.73]|
|horizons/126/whole/ownExTopEntryYear/total|374|14.96|-1.13 [-2.51, -0.19]|
|horizons/126/whole/ownExTopEntryYear/stockOnlyTotal|374|14.96|-5.66 [-12.54, -0.97]|
|horizons/126/k5/own/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/k5/own/passNet|427|17.08|+11.57 [+1.69, +24.82]|
|horizons/126/k5/own/total|427|17.08|-0.55 [-1.84, +0.49]|
|horizons/126/k5/own/stockOnlyTotal|427|17.08|-2.74 [-9.21, +2.45]|
|horizons/126/k5/paired/etfNet|60|2.4|+23.67 [+3.59, +44.95]|
|horizons/126/k5/paired/passNet|60|2.4|+23.17 [+4.41, +42.19]|
|horizons/126/k5/paired/failNet|60|2.4|+21.87 [+3.70, +40.36]|
|horizons/126/k5/paired/selection|60|2.4|+1.29 [-0.25, +2.43]|
|horizons/126/k5/paired/replacement|60|2.4|-1.80 [-4.81, +0.60]|
|horizons/126/k5/paired/total|60|2.4|-0.50 [-3.34, +1.79]|
|horizons/126/k5/wholeCommon/etfNet|60|2.4|+23.67 [+3.59, +44.95]|
|horizons/126/k5/wholeCommon/passNet|60|2.4|+23.17 [+4.41, +42.19]|
|horizons/126/k5/wholeCommon/failNet|60|2.4|+21.87 [+3.70, +40.36]|
|horizons/126/k5/wholeCommon/selection|60|2.4|+1.29 [-0.25, +2.43]|
|horizons/126/k5/wholeCommon/replacement|60|2.4|-1.80 [-4.81, +0.60]|
|horizons/126/k5/wholeCommon/total|60|2.4|-0.50 [-3.34, +1.79]|
|horizons/126/k5/deltaSelectionVsWholeOnCommonDates|60|2.4|-0.32 [-1.11, +0.30]|
|horizons/126/k5/deltaOwnTotalVsWholeOnCommonDates|427|17.08|+0.18 [-0.06, +0.43]|
|horizons/126/k5/exLeadersDates/etfNet|58|2.32|+23.58 [+2.67, +45.60]|
|horizons/126/k5/exLeadersDates/passNet|58|2.32|+23.13 [+3.48, +42.77]|
|horizons/126/k5/exLeadersDates/failNet|58|2.32|+21.45 [+2.44, +40.57]|
|horizons/126/k5/exLeadersDates/selection|58|2.32|+1.68 [+0.43, +2.67]|
|horizons/126/k5/exLeadersDates/replacement|58|2.32|-2.13 [-5.13, +0.16]|
|horizons/126/k5/exLeadersDates/total|58|2.32|-0.45 [-3.39, +1.96]|
|horizons/126/k5/leaderDatesOnly/etfNet|2|0.08|+26.33 [구간 미측정]|
|horizons/126/k5/leaderDatesOnly/passNet|2|0.08|+24.20 [구간 미측정]|
|horizons/126/k5/leaderDatesOnly/failNet|2|0.08|+34.05 [구간 미측정]|
|horizons/126/k5/leaderDatesOnly/selection|2|0.08|-9.86 [구간 미측정]|
|horizons/126/k5/leaderDatesOnly/replacement|2|0.08|+7.73 [구간 미측정]|
|horizons/126/k5/leaderDatesOnly/total|2|0.08|-2.13 [구간 미측정]|
|horizons/126/k5/exLeadersPairs/etfNet|60|2.4|+23.67 [+3.59, +44.95]|
|horizons/126/k5/exLeadersPairs/passNet|60|2.4|+23.17 [+4.42, +42.17]|
|horizons/126/k5/exLeadersPairs/failNet|60|2.4|+21.87 [+3.73, +40.41]|
|horizons/126/k5/exLeadersPairs/selection|60|2.4|+1.30 [-0.30, +2.46]|
|horizons/126/k5/exLeadersPairs/replacement|60|2.4|-1.80 [-4.81, +0.60]|
|horizons/126/k5/exLeadersPairs/total|60|2.4|-0.51 [-3.34, +1.79]|
|horizons/126/k5/semiLed/etfNet|30|1.2|+33.56 [구간 미측정]|
|horizons/126/k5/semiLed/passNet|30|1.2|+30.14 [구간 미측정]|
|horizons/126/k5/semiLed/failNet|30|1.2|+28.96 [구간 미측정]|
|horizons/126/k5/semiLed/selection|30|1.2|+1.18 [구간 미측정]|
|horizons/126/k5/semiLed/replacement|30|1.2|-4.59 [구간 미측정]|
|horizons/126/k5/semiLed/total|30|1.2|-3.41 [구간 미측정]|
|horizons/126/k5/nonSemiLed/etfNet|28|1.12|+15.72 [구간 미측정]|
|horizons/126/k5/nonSemiLed/passNet|28|1.12|+18.18 [구간 미측정]|
|horizons/126/k5/nonSemiLed/failNet|28|1.12|+16.66 [구간 미측정]|
|horizons/126/k5/nonSemiLed/selection|28|1.12|+1.53 [구간 미측정]|
|horizons/126/k5/nonSemiLed/replacement|28|1.12|+0.94 [구간 미측정]|
|horizons/126/k5/nonSemiLed/total|28|1.12|+2.46 [구간 미측정]|
|horizons/126/k5/unknownSemi/etfNet|2|0.08|-13.26 [구간 미측정]|
|horizons/126/k5/unknownSemi/passNet|2|0.08|-11.69 [구간 미측정]|
|horizons/126/k5/unknownSemi/failNet|2|0.08|-11.42 [구간 미측정]|
|horizons/126/k5/unknownSemi/selection|2|0.08|-0.27 [구간 미측정]|
|horizons/126/k5/unknownSemi/replacement|2|0.08|+1.84 [구간 미측정]|
|horizons/126/k5/unknownSemi/total|2|0.08|+1.57 [구간 미측정]|
|horizons/126/k5/exTopEntryYear/etfNet|45|1.8|+5.48 [구간 미측정]|
|horizons/126/k5/exTopEntryYear/passNet|45|1.8|+6.20 [구간 미측정]|
|horizons/126/k5/exTopEntryYear/failNet|45|1.8|+5.55 [구간 미측정]|
|horizons/126/k5/exTopEntryYear/selection|45|1.8|+0.65 [구간 미측정]|
|horizons/126/k5/exTopEntryYear/replacement|45|1.8|+0.07 [구간 미측정]|
|horizons/126/k5/exTopEntryYear/total|45|1.8|+0.72 [구간 미측정]|
|horizons/126/k5/exTopTotalEntryYear/etfNet|50|2.0|+27.35 [+4.27, +50.72]|
|horizons/126/k5/exTopTotalEntryYear/passNet|50|2.0|+25.82 [+4.02, +46.98]|
|horizons/126/k5/exTopTotalEntryYear/failNet|50|2.0|+25.03 [+4.58, +45.65]|
|horizons/126/k5/exTopTotalEntryYear/selection|50|2.0|+0.79 [-0.84, +2.01]|
|horizons/126/k5/exTopTotalEntryYear/replacement|50|2.0|-2.32 [-5.58, +0.53]|
|horizons/126/k5/exTopTotalEntryYear/total|50|2.0|-1.53 [-4.22, +0.56]|
|horizons/126/k5/ownExLeadersDates/etfNet|350|14.0|+11.73 [+1.78, +25.45]|
|horizons/126/k5/ownExLeadersDates/passNet|350|14.0|+10.98 [+1.88, +23.46]|
|horizons/126/k5/ownExLeadersDates/total|350|14.0|-0.75 [-2.30, +0.48]|
|horizons/126/k5/ownExLeadersDates/stockOnlyTotal|350|14.0|-3.74 [-11.49, +2.42]|
|horizons/126/k5/ownSemiLed/etfNet|199|7.96|+19.76 [+2.30, +42.84]|
|horizons/126/k5/ownSemiLed/passNet|199|7.96|+18.33 [+2.32, +39.70]|
|horizons/126/k5/ownSemiLed/total|199|7.96|-1.44 [-3.43, +0.18]|
|horizons/126/k5/ownSemiLed/stockOnlyTotal|199|7.96|-7.18 [-17.13, +0.90]|
|horizons/126/k5/ownNonSemiLed/etfNet|203|8.12|+7.40 [-3.61, +19.35]|
|horizons/126/k5/ownNonSemiLed/passNet|203|8.12|+7.59 [-2.96, +18.93]|
|horizons/126/k5/ownNonSemiLed/total|203|8.12|+0.19 [-1.11, +1.46]|
|horizons/126/k5/ownNonSemiLed/stockOnlyTotal|203|8.12|+0.94 [-5.53, +7.32]|
|horizons/126/k5/ownUnknownSemi/etfNet|25|1.0|-10.46 [구간 미측정]|
|horizons/126/k5/ownUnknownSemi/passNet|25|1.0|-9.92 [구간 미측정]|
|horizons/126/k5/ownUnknownSemi/total|25|1.0|+0.54 [구간 미측정]|
|horizons/126/k5/ownUnknownSemi/stockOnlyTotal|25|1.0|+2.69 [구간 미측정]|
|horizons/126/k5/ownExTopEntryYear/etfNet|374|14.96|+13.78 [+2.02, +30.20]|
|horizons/126/k5/ownExTopEntryYear/passNet|374|14.96|+12.77 [+1.77, +27.97]|
|horizons/126/k5/ownExTopEntryYear/total|374|14.96|-1.01 [-2.31, -0.09]|
|horizons/126/k5/ownExTopEntryYear/stockOnlyTotal|374|14.96|-5.07 [-11.57, -0.43]|
|horizons/126/seedCommon/selection|0|0.0|미측정|
|horizons/126/seedCommon/replacement|0|0.0|미측정|
|horizons/126/seedCommon/total|0|0.0|미측정|
|horizons/126/seedCommon/ownTotal|427|17.08|-0.65 [-1.95, +0.34]|
|horizons/126/seedAvailable/selection|265|10.6|+0.73 [-0.31, +1.66]|
|horizons/126/seedAvailable/replacement|265|10.6|-1.67 [-3.78, +0.03]|
|horizons/126/seedAvailable/total|265|10.6|-0.95 [-3.04, +0.79]|
|horizons/126/seedAvailable/ownTotal|427|17.08|-0.65 [-1.95, +0.34]|
|horizons/126/seeds/seed=20261118/paired/etfNet|60|2.4|+23.67 [+3.59, +44.95]|
|horizons/126/seeds/seed=20261118/paired/passNet|60|2.4|+23.17 [+4.41, +42.19]|
|horizons/126/seeds/seed=20261118/paired/failNet|60|2.4|+21.87 [+3.70, +40.36]|
|horizons/126/seeds/seed=20261118/paired/selection|60|2.4|+1.29 [-0.25, +2.43]|
|horizons/126/seeds/seed=20261118/paired/replacement|60|2.4|-1.80 [-4.81, +0.60]|
|horizons/126/seeds/seed=20261118/paired/total|60|2.4|-0.50 [-3.34, +1.79]|
|horizons/126/seeds/seed=20261118/pairedCommon/etfNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261118/pairedCommon/passNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261118/pairedCommon/failNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261118/pairedCommon/selection|0|0.0|미측정|
|horizons/126/seeds/seed=20261118/pairedCommon/replacement|0|0.0|미측정|
|horizons/126/seeds/seed=20261118/pairedCommon/total|0|0.0|미측정|
|horizons/126/seeds/seed=20261118/own/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261118/own/passNet|427|17.08|+11.57 [+1.69, +24.82]|
|horizons/126/seeds/seed=20261118/own/total|427|17.08|-0.55 [-1.84, +0.49]|
|horizons/126/seeds/seed=20261118/own/stockOnlyTotal|427|17.08|-2.74 [-9.21, +2.45]|
|horizons/126/seeds/seed=20261118/ownCommon/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261118/ownCommon/passNet|427|17.08|+11.57 [+1.69, +24.82]|
|horizons/126/seeds/seed=20261118/ownCommon/total|427|17.08|-0.55 [-1.84, +0.49]|
|horizons/126/seeds/seed=20261118/ownCommon/stockOnlyTotal|427|17.08|-2.74 [-9.21, +2.45]|
|horizons/126/seeds/seed=20261119/paired/etfNet|59|2.36|+20.42 [+2.01, +40.36]|
|horizons/126/seeds/seed=20261119/paired/passNet|59|2.36|+19.55 [+2.61, +37.75]|
|horizons/126/seeds/seed=20261119/paired/failNet|59|2.36|+18.98 [+2.01, +36.97]|
|horizons/126/seeds/seed=20261119/paired/selection|59|2.36|+0.56 [-0.86, +1.82]|
|horizons/126/seeds/seed=20261119/paired/replacement|59|2.36|-1.43 [-3.87, +0.55]|
|horizons/126/seeds/seed=20261119/paired/total|59|2.36|-0.87 [-3.13, +0.99]|
|horizons/126/seeds/seed=20261119/pairedCommon/etfNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261119/pairedCommon/passNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261119/pairedCommon/failNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261119/pairedCommon/selection|0|0.0|미측정|
|horizons/126/seeds/seed=20261119/pairedCommon/replacement|0|0.0|미측정|
|horizons/126/seeds/seed=20261119/pairedCommon/total|0|0.0|미측정|
|horizons/126/seeds/seed=20261119/own/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261119/own/passNet|427|17.08|+11.54 [+1.74, +24.58]|
|horizons/126/seeds/seed=20261119/own/total|427|17.08|-0.58 [-1.88, +0.39]|
|horizons/126/seeds/seed=20261119/own/stockOnlyTotal|427|17.08|-2.88 [-9.40, +1.93]|
|horizons/126/seeds/seed=20261119/ownCommon/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261119/ownCommon/passNet|427|17.08|+11.54 [+1.74, +24.58]|
|horizons/126/seeds/seed=20261119/ownCommon/total|427|17.08|-0.58 [-1.88, +0.39]|
|horizons/126/seeds/seed=20261119/ownCommon/stockOnlyTotal|427|17.08|-2.88 [-9.40, +1.93]|
|horizons/126/seeds/seed=20261120/paired/etfNet|51|2.04|+20.07 [+1.75, +42.07]|
|horizons/126/seeds/seed=20261120/paired/passNet|51|2.04|+18.68 [+2.06, +38.30]|
|horizons/126/seeds/seed=20261120/paired/failNet|51|2.04|+17.90 [+1.51, +37.32]|
|horizons/126/seeds/seed=20261120/paired/selection|51|2.04|+0.78 [-0.31, +1.78]|
|horizons/126/seeds/seed=20261120/paired/replacement|51|2.04|-2.16 [-4.93, -0.17]|
|horizons/126/seeds/seed=20261120/paired/total|51|2.04|-1.39 [-4.10, +0.57]|
|horizons/126/seeds/seed=20261120/pairedCommon/etfNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261120/pairedCommon/passNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261120/pairedCommon/failNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261120/pairedCommon/selection|0|0.0|미측정|
|horizons/126/seeds/seed=20261120/pairedCommon/replacement|0|0.0|미측정|
|horizons/126/seeds/seed=20261120/pairedCommon/total|0|0.0|미측정|
|horizons/126/seeds/seed=20261120/own/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261120/own/passNet|427|17.08|+11.41 [+1.60, +24.35]|
|horizons/126/seeds/seed=20261120/own/total|427|17.08|-0.71 [-2.12, +0.31]|
|horizons/126/seeds/seed=20261120/own/stockOnlyTotal|427|17.08|-3.53 [-10.58, +1.53]|
|horizons/126/seeds/seed=20261120/ownCommon/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261120/ownCommon/passNet|427|17.08|+11.41 [+1.60, +24.35]|
|horizons/126/seeds/seed=20261120/ownCommon/total|427|17.08|-0.71 [-2.12, +0.31]|
|horizons/126/seeds/seed=20261120/ownCommon/stockOnlyTotal|427|17.08|-3.53 [-10.58, +1.53]|
|horizons/126/seeds/seed=20261121/paired/etfNet|59|2.36|+22.47 [+1.19, +46.10]|
|horizons/126/seeds/seed=20261121/paired/passNet|59|2.36|+20.93 [+1.47, +42.12]|
|horizons/126/seeds/seed=20261121/paired/failNet|59|2.36|+19.96 [+0.77, +40.74]|
|horizons/126/seeds/seed=20261121/paired/selection|59|2.36|+0.96 [-0.27, +2.35]|
|horizons/126/seeds/seed=20261121/paired/replacement|59|2.36|-2.51 [-5.54, -0.02]|
|horizons/126/seeds/seed=20261121/paired/total|59|2.36|-1.55 [-4.41, +1.22]|
|horizons/126/seeds/seed=20261121/pairedCommon/etfNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261121/pairedCommon/passNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261121/pairedCommon/failNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261121/pairedCommon/selection|0|0.0|미측정|
|horizons/126/seeds/seed=20261121/pairedCommon/replacement|0|0.0|미측정|
|horizons/126/seeds/seed=20261121/pairedCommon/total|0|0.0|미측정|
|horizons/126/seeds/seed=20261121/own/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261121/own/passNet|427|17.08|+11.66 [+1.71, +25.06]|
|horizons/126/seeds/seed=20261121/own/total|427|17.08|-0.46 [-1.65, +0.53]|
|horizons/126/seeds/seed=20261121/own/stockOnlyTotal|427|17.08|-2.30 [-8.26, +2.63]|
|horizons/126/seeds/seed=20261121/ownCommon/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261121/ownCommon/passNet|427|17.08|+11.66 [+1.71, +25.06]|
|horizons/126/seeds/seed=20261121/ownCommon/total|427|17.08|-0.46 [-1.65, +0.53]|
|horizons/126/seeds/seed=20261121/ownCommon/stockOnlyTotal|427|17.08|-2.30 [-8.26, +2.63]|
|horizons/126/seeds/seed=20261122/paired/etfNet|56|2.24|+23.88 [+4.49, +44.56]|
|horizons/126/seeds/seed=20261122/paired/passNet|56|2.24|+22.34 [+4.89, +40.55]|
|horizons/126/seeds/seed=20261122/paired/failNet|56|2.24|+21.46 [+4.13, +39.47]|
|horizons/126/seeds/seed=20261122/paired/selection|56|2.24|+0.87 [-1.19, +2.60]|
|horizons/126/seeds/seed=20261122/paired/replacement|56|2.24|-2.41 [-5.22, +0.19]|
|horizons/126/seeds/seed=20261122/paired/total|56|2.24|-1.54 [-4.29, +0.94]|
|horizons/126/seeds/seed=20261122/pairedCommon/etfNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261122/pairedCommon/passNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261122/pairedCommon/failNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261122/pairedCommon/selection|0|0.0|미측정|
|horizons/126/seeds/seed=20261122/pairedCommon/replacement|0|0.0|미측정|
|horizons/126/seeds/seed=20261122/pairedCommon/total|0|0.0|미측정|
|horizons/126/seeds/seed=20261122/own/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261122/own/passNet|427|17.08|+11.61 [+1.82, +24.63]|
|horizons/126/seeds/seed=20261122/own/total|427|17.08|-0.51 [-1.86, +0.51]|
|horizons/126/seeds/seed=20261122/own/stockOnlyTotal|427|17.08|-2.54 [-9.30, +2.53]|
|horizons/126/seeds/seed=20261122/ownCommon/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261122/ownCommon/passNet|427|17.08|+11.61 [+1.82, +24.63]|
|horizons/126/seeds/seed=20261122/ownCommon/total|427|17.08|-0.51 [-1.86, +0.51]|
|horizons/126/seeds/seed=20261122/ownCommon/stockOnlyTotal|427|17.08|-2.54 [-9.30, +2.53]|
|horizons/126/seeds/seed=20261123/paired/etfNet|53|2.12|+19.39 [+2.76, +39.57]|
|horizons/126/seeds/seed=20261123/paired/passNet|53|2.12|+18.18 [+3.28, +36.02]|
|horizons/126/seeds/seed=20261123/paired/failNet|53|2.12|+17.06 [+2.13, +34.89]|
|horizons/126/seeds/seed=20261123/paired/selection|53|2.12|+1.12 [+0.29, +1.99]|
|horizons/126/seeds/seed=20261123/paired/replacement|53|2.12|-2.33 [-4.68, -0.31]|
|horizons/126/seeds/seed=20261123/paired/total|53|2.12|-1.21 [-3.78, +0.87]|
|horizons/126/seeds/seed=20261123/pairedCommon/etfNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261123/pairedCommon/passNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261123/pairedCommon/failNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261123/pairedCommon/selection|0|0.0|미측정|
|horizons/126/seeds/seed=20261123/pairedCommon/replacement|0|0.0|미측정|
|horizons/126/seeds/seed=20261123/pairedCommon/total|0|0.0|미측정|
|horizons/126/seeds/seed=20261123/own/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261123/own/passNet|427|17.08|+11.62 [+1.73, +24.92]|
|horizons/126/seeds/seed=20261123/own/total|427|17.08|-0.50 [-1.67, +0.44]|
|horizons/126/seeds/seed=20261123/own/stockOnlyTotal|427|17.08|-2.51 [-8.35, +2.18]|
|horizons/126/seeds/seed=20261123/ownCommon/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261123/ownCommon/passNet|427|17.08|+11.62 [+1.73, +24.92]|
|horizons/126/seeds/seed=20261123/ownCommon/total|427|17.08|-0.50 [-1.67, +0.44]|
|horizons/126/seeds/seed=20261123/ownCommon/stockOnlyTotal|427|17.08|-2.51 [-8.35, +2.18]|
|horizons/126/seeds/seed=20261124/paired/etfNet|56|2.24|+25.10 [+0.53, +50.33]|
|horizons/126/seeds/seed=20261124/paired/passNet|56|2.24|+23.31 [+1.31, +45.15]|
|horizons/126/seeds/seed=20261124/paired/failNet|56|2.24|+22.60 [+0.54, +44.67]|
|horizons/126/seeds/seed=20261124/paired/selection|56|2.24|+0.71 [-0.82, +2.08]|
|horizons/126/seeds/seed=20261124/paired/replacement|56|2.24|-2.50 [-5.65, +0.29]|
|horizons/126/seeds/seed=20261124/paired/total|56|2.24|-1.79 [-5.73, +1.38]|
|horizons/126/seeds/seed=20261124/pairedCommon/etfNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261124/pairedCommon/passNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261124/pairedCommon/failNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261124/pairedCommon/selection|0|0.0|미측정|
|horizons/126/seeds/seed=20261124/pairedCommon/replacement|0|0.0|미측정|
|horizons/126/seeds/seed=20261124/pairedCommon/total|0|0.0|미측정|
|horizons/126/seeds/seed=20261124/own/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261124/own/passNet|427|17.08|+11.29 [+1.50, +24.23]|
|horizons/126/seeds/seed=20261124/own/total|427|17.08|-0.82 [-2.34, +0.23]|
|horizons/126/seeds/seed=20261124/own/stockOnlyTotal|427|17.08|-4.12 [-11.68, +1.13]|
|horizons/126/seeds/seed=20261124/ownCommon/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261124/ownCommon/passNet|427|17.08|+11.29 [+1.50, +24.23]|
|horizons/126/seeds/seed=20261124/ownCommon/total|427|17.08|-0.82 [-2.34, +0.23]|
|horizons/126/seeds/seed=20261124/ownCommon/stockOnlyTotal|427|17.08|-4.12 [-11.68, +1.13]|
|horizons/126/seeds/seed=20261125/paired/etfNet|55|2.2|+20.45 [-0.84, +47.95]|
|horizons/126/seeds/seed=20261125/paired/passNet|55|2.2|+18.95 [-0.02, +43.39]|
|horizons/126/seeds/seed=20261125/paired/failNet|55|2.2|+18.41 [-0.88, +43.20]|
|horizons/126/seeds/seed=20261125/paired/selection|55|2.2|+0.53 [-0.39, +1.49]|
|horizons/126/seeds/seed=20261125/paired/replacement|55|2.2|-2.04 [-4.86, +0.19]|
|horizons/126/seeds/seed=20261125/paired/total|55|2.2|-1.51 [-4.69, +1.07]|
|horizons/126/seeds/seed=20261125/pairedCommon/etfNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261125/pairedCommon/passNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261125/pairedCommon/failNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261125/pairedCommon/selection|0|0.0|미측정|
|horizons/126/seeds/seed=20261125/pairedCommon/replacement|0|0.0|미측정|
|horizons/126/seeds/seed=20261125/pairedCommon/total|0|0.0|미측정|
|horizons/126/seeds/seed=20261125/own/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261125/own/passNet|427|17.08|+11.25 [+1.28, +24.53]|
|horizons/126/seeds/seed=20261125/own/total|427|17.08|-0.87 [-1.98, -0.02]|
|horizons/126/seeds/seed=20261125/own/stockOnlyTotal|427|17.08|-4.35 [-9.92, -0.12]|
|horizons/126/seeds/seed=20261125/ownCommon/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261125/ownCommon/passNet|427|17.08|+11.25 [+1.28, +24.53]|
|horizons/126/seeds/seed=20261125/ownCommon/total|427|17.08|-0.87 [-1.98, -0.02]|
|horizons/126/seeds/seed=20261125/ownCommon/stockOnlyTotal|427|17.08|-4.35 [-9.92, -0.12]|
|horizons/126/seeds/seed=20261126/paired/etfNet|66|2.64|+19.89 [+1.03, +39.97]|
|horizons/126/seeds/seed=20261126/paired/passNet|66|2.64|+19.32 [+2.15, +36.88]|
|horizons/126/seeds/seed=20261126/paired/failNet|66|2.64|+17.63 [+0.63, +35.44]|
|horizons/126/seeds/seed=20261126/paired/selection|66|2.64|+1.69 [+0.27, +2.93]|
|horizons/126/seeds/seed=20261126/paired/replacement|66|2.64|-2.26 [-4.72, -0.23]|
|horizons/126/seeds/seed=20261126/paired/total|66|2.64|-0.57 [-3.65, +1.83]|
|horizons/126/seeds/seed=20261126/pairedCommon/etfNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261126/pairedCommon/passNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261126/pairedCommon/failNet|0|0.0|미측정|
|horizons/126/seeds/seed=20261126/pairedCommon/selection|0|0.0|미측정|
|horizons/126/seeds/seed=20261126/pairedCommon/replacement|0|0.0|미측정|
|horizons/126/seeds/seed=20261126/pairedCommon/total|0|0.0|미측정|
|horizons/126/seeds/seed=20261126/own/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261126/own/passNet|427|17.08|+11.30 [+1.46, +24.23]|
|horizons/126/seeds/seed=20261126/own/total|427|17.08|-0.82 [-2.36, +0.36]|
|horizons/126/seeds/seed=20261126/own/stockOnlyTotal|427|17.08|-4.09 [-11.82, +1.78]|
|horizons/126/seeds/seed=20261126/ownCommon/etfNet|427|17.08|+12.12 [+1.54, +26.29]|
|horizons/126/seeds/seed=20261126/ownCommon/passNet|427|17.08|+11.30 [+1.46, +24.23]|
|horizons/126/seeds/seed=20261126/ownCommon/total|427|17.08|-0.82 [-2.36, +0.36]|
|horizons/126/seeds/seed=20261126/ownCommon/stockOnlyTotal|427|17.08|-4.09 [-11.82, +1.78]|
|horizons/252/whole/matched20/etfNet|387|7.74|+26.93 [+2.50, +65.44]|
|horizons/252/whole/matched20/passNet|387|7.74|+26.28 [+3.16, +62.31]|
|horizons/252/whole/matched20/failNet|387|7.74|+24.95 [+2.50, +58.97]|
|horizons/252/whole/matched20/selection|387|7.74|+1.33 [-0.99, +4.14]|
|horizons/252/whole/matched20/replacement|387|7.74|-1.98 [-6.60, +1.07]|
|horizons/252/whole/matched20/total|387|7.74|-0.65 [-3.47, +1.58]|
|horizons/252/whole/matched100/etfNet|387|7.74|+26.93 [+2.50, +65.44]|
|horizons/252/whole/matched100/passNet|387|7.74|+23.68 [+3.22, +53.12]|
|horizons/252/whole/matched100/failNet|387|7.74|+17.03 [+0.43, +37.34]|
|horizons/252/whole/matched100/selection|387|7.74|+6.65 [-4.97, +20.70]|
|horizons/252/whole/matched100/replacement|387|7.74|-9.90 [-32.99, +5.35]|
|horizons/252/whole/matched100/total|387|7.74|-3.25 [-17.35, +7.91]|
|horizons/252/whole/allPass20/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/whole/allPass20/passNet|400|8.0|+24.65 [+2.53, +61.92]|
|horizons/252/whole/allPass20/total|400|8.0|-1.09 [-3.63, +0.65]|
|horizons/252/whole/allPass20/stockOnlyTotal|400|8.0|-5.47 [-18.16, +3.26]|
|horizons/252/whole/allPass20OnMatchedDates/etfNet|387|7.74|+26.93 [+2.50, +65.44]|
|horizons/252/whole/allPass20OnMatchedDates/passNet|387|7.74|+25.86 [+2.60, +62.05]|
|horizons/252/whole/allPass20OnMatchedDates/total|387|7.74|-1.07 [-3.63, +0.66]|
|horizons/252/whole/allPass20OnMatchedDates/stockOnlyTotal|387|7.74|-5.34 [-18.16, +3.31]|
|horizons/252/whole/allPass20OnK5Dates/etfNet|53|1.06|+53.91 [구간 미측정]|
|horizons/252/whole/allPass20OnK5Dates/passNet|53|1.06|+52.19 [구간 미측정]|
|horizons/252/whole/allPass20OnK5Dates/total|53|1.06|-1.72 [구간 미측정]|
|horizons/252/whole/allPass20OnK5Dates/stockOnlyTotal|53|1.06|-8.60 [구간 미측정]|
|horizons/252/whole/matched20OnK5Dates/etfNet|53|1.06|+53.91 [구간 미측정]|
|horizons/252/whole/matched20OnK5Dates/passNet|53|1.06|+52.62 [구간 미측정]|
|horizons/252/whole/matched20OnK5Dates/failNet|53|1.06|+49.24 [구간 미측정]|
|horizons/252/whole/matched20OnK5Dates/selection|53|1.06|+3.38 [구간 미측정]|
|horizons/252/whole/matched20OnK5Dates/replacement|53|1.06|-4.67 [구간 미측정]|
|horizons/252/whole/matched20OnK5Dates/total|53|1.06|-1.29 [구간 미측정]|
|horizons/252/whole/matched20OnFullyMatchedDates/etfNet|0|0.0|미측정|
|horizons/252/whole/matched20OnFullyMatchedDates/passNet|0|0.0|미측정|
|horizons/252/whole/matched20OnFullyMatchedDates/failNet|0|0.0|미측정|
|horizons/252/whole/matched20OnFullyMatchedDates/selection|0|0.0|미측정|
|horizons/252/whole/matched20OnFullyMatchedDates/replacement|0|0.0|미측정|
|horizons/252/whole/matched20OnFullyMatchedDates/total|0|0.0|미측정|
|horizons/252/whole/exLeadersDates/etfNet|323|6.46|+30.74 [+1.85, +76.55]|
|horizons/252/whole/exLeadersDates/passNet|323|6.46|+29.33 [+1.89, +73.23]|
|horizons/252/whole/exLeadersDates/failNet|323|6.46|+27.56 [+0.96, +68.51]|
|horizons/252/whole/exLeadersDates/selection|323|6.46|+1.77 [-0.72, +4.96]|
|horizons/252/whole/exLeadersDates/replacement|323|6.46|-3.17 [-8.40, +0.01]|
|horizons/252/whole/exLeadersDates/total|323|6.46|-1.40 [-4.35, +0.57]|
|horizons/252/whole/leaderDatesOnly/etfNet|64|1.28|+7.72 [구간 미측정]|
|horizons/252/whole/leaderDatesOnly/passNet|64|1.28|+10.88 [구간 미측정]|
|horizons/252/whole/leaderDatesOnly/failNet|64|1.28|+11.76 [구간 미측정]|
|horizons/252/whole/leaderDatesOnly/selection|64|1.28|-0.87 [구간 미측정]|
|horizons/252/whole/leaderDatesOnly/replacement|64|1.28|+4.03 [구간 미측정]|
|horizons/252/whole/leaderDatesOnly/total|64|1.28|+3.16 [구간 미측정]|
|horizons/252/whole/exLeadersPairs/etfNet|387|7.74|+26.93 [+2.50, +65.44]|
|horizons/252/whole/exLeadersPairs/passNet|387|7.74|+26.34 [+3.23, +62.37]|
|horizons/252/whole/exLeadersPairs/failNet|387|7.74|+24.92 [+2.46, +58.93]|
|horizons/252/whole/exLeadersPairs/selection|387|7.74|+1.42 [-0.94, +4.24]|
|horizons/252/whole/exLeadersPairs/replacement|387|7.74|-2.01 [-6.61, +1.05]|
|horizons/252/whole/exLeadersPairs/total|387|7.74|-0.59 [-3.45, +1.70]|
|horizons/252/whole/semiLed/etfNet|252|5.04|+36.03 [+6.58, +90.31]|
|horizons/252/whole/semiLed/passNet|252|5.04|+34.49 [+6.42, +86.16]|
|horizons/252/whole/semiLed/failNet|252|5.04|+32.17 [+5.79, +80.26]|
|horizons/252/whole/semiLed/selection|252|5.04|+2.32 [+0.14, +5.84]|
|horizons/252/whole/semiLed/replacement|252|5.04|-3.85 [-10.55, +0.62]|
|horizons/252/whole/semiLed/total|252|5.04|-1.54 [-5.55, +1.34]|
|horizons/252/whole/nonSemiLed/etfNet|129|2.58|+10.94 [-14.01, +48.64]|
|horizons/252/whole/nonSemiLed/passNet|129|2.58|+11.92 [-12.02, +49.07]|
|horizons/252/whole/nonSemiLed/failNet|129|2.58|+12.47 [-13.42, +50.46]|
|horizons/252/whole/nonSemiLed/selection|129|2.58|-0.55 [-4.30, +4.55]|
|horizons/252/whole/nonSemiLed/replacement|129|2.58|+1.53 [-0.16, +3.11]|
|horizons/252/whole/nonSemiLed/total|129|2.58|+0.98 [-1.48, +4.50]|
|horizons/252/whole/unknownSemi/etfNet|6|0.12|-11.27 [구간 미측정]|
|horizons/252/whole/unknownSemi/passNet|6|0.12|-9.73 [구간 미측정]|
|horizons/252/whole/unknownSemi/failNet|6|0.12|-10.14 [구간 미측정]|
|horizons/252/whole/unknownSemi/selection|6|0.12|+0.41 [구간 미측정]|
|horizons/252/whole/unknownSemi/replacement|6|0.12|+1.13 [구간 미측정]|
|horizons/252/whole/unknownSemi/total|6|0.12|+1.54 [구간 미측정]|
|horizons/252/whole/exTopEntryYear/etfNet|352|7.04|+11.29 [-1.10, +27.08]|
|horizons/252/whole/exTopEntryYear/passNet|352|7.04|+11.75 [-0.29, +27.32]|
|horizons/252/whole/exTopEntryYear/failNet|352|7.04|+11.27 [-1.04, +26.92]|
|horizons/252/whole/exTopEntryYear/selection|352|7.04|+0.47 [-1.44, +2.44]|
|horizons/252/whole/exTopEntryYear/replacement|352|7.04|-0.02 [-1.71, +1.71]|
|horizons/252/whole/exTopEntryYear/total|352|7.04|+0.46 [-1.12, +2.44]|
|horizons/252/whole/exTopTotalEntryYear/etfNet|334|6.68|+26.84 [+1.55, +71.10]|
|horizons/252/whole/exTopTotalEntryYear/passNet|334|6.68|+25.15 [+1.29, +66.80]|
|horizons/252/whole/exTopTotalEntryYear/failNet|334|6.68|+24.40 [+1.06, +63.66]|
|horizons/252/whole/exTopTotalEntryYear/selection|334|6.68|+0.75 [-1.40, +3.44]|
|horizons/252/whole/exTopTotalEntryYear/replacement|334|6.68|-2.44 [-7.75, +0.64]|
|horizons/252/whole/exTopTotalEntryYear/total|334|6.68|-1.69 [-4.61, +0.07]|
|horizons/252/whole/ownExLeadersDates/etfNet|146|2.92|+18.75 [+4.48, +44.89]|
|horizons/252/whole/ownExLeadersDates/passNet|146|2.92|+19.11 [+6.60, +43.18]|
|horizons/252/whole/ownExLeadersDates/total|146|2.92|+0.36 [-1.92, +3.49]|
|horizons/252/whole/ownExLeadersDates/stockOnlyTotal|146|2.92|+1.82 [-9.61, +17.46]|
|horizons/252/whole/ownSemiLed/etfNet|252|5.04|+36.03 [+6.58, +90.31]|
|horizons/252/whole/ownSemiLed/passNet|252|5.04|+34.31 [+6.33, +85.73]|
|horizons/252/whole/ownSemiLed/total|252|5.04|-1.72 [-5.40, +0.65]|
|horizons/252/whole/ownSemiLed/stockOnlyTotal|252|5.04|-8.58 [-26.99, +3.27]|
|horizons/252/whole/ownNonSemiLed/etfNet|129|2.58|+10.94 [-14.01, +48.64]|
|horizons/252/whole/ownNonSemiLed/passNet|129|2.58|+11.03 [-13.09, +47.80]|
|horizons/252/whole/ownNonSemiLed/total|129|2.58|+0.09 [-1.81, +2.44]|
|horizons/252/whole/ownNonSemiLed/stockOnlyTotal|129|2.58|+0.44 [-9.04, +12.18]|
|horizons/252/whole/ownUnknownSemi/etfNet|19|0.38|-10.15 [구간 미측정]|
|horizons/252/whole/ownUnknownSemi/passNet|19|0.38|-10.99 [구간 미측정]|
|horizons/252/whole/ownUnknownSemi/total|19|0.38|-0.84 [구간 미측정]|
|horizons/252/whole/ownUnknownSemi/stockOnlyTotal|19|0.38|-4.22 [구간 미측정]|
|horizons/252/whole/ownExTopEntryYear/etfNet|347|6.94|+25.48 [+1.34, +70.70]|
|horizons/252/whole/ownExTopEntryYear/passNet|347|6.94|+23.64 [+1.00, +66.14]|
|horizons/252/whole/ownExTopEntryYear/total|347|6.94|-1.84 [-4.62, -0.34]|
|horizons/252/whole/ownExTopEntryYear/stockOnlyTotal|347|6.94|-9.19 [-23.08, -1.72]|
|horizons/252/k5/own/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/k5/own/passNet|400|8.0|+25.13 [+2.79, +63.10]|
|horizons/252/k5/own/total|400|8.0|-0.62 [-2.67, +1.12]|
|horizons/252/k5/own/stockOnlyTotal|400|8.0|-3.08 [-13.33, +5.60]|
|horizons/252/k5/paired/etfNet|53|1.06|+53.91 [구간 미측정]|
|horizons/252/k5/paired/passNet|53|1.06|+52.86 [구간 미측정]|
|horizons/252/k5/paired/failNet|53|1.06|+49.01 [구간 미측정]|
|horizons/252/k5/paired/selection|53|1.06|+3.86 [구간 미측정]|
|horizons/252/k5/paired/replacement|53|1.06|-4.90 [구간 미측정]|
|horizons/252/k5/paired/total|53|1.06|-1.05 [구간 미측정]|
|horizons/252/k5/wholeCommon/etfNet|53|1.06|+53.91 [구간 미측정]|
|horizons/252/k5/wholeCommon/passNet|53|1.06|+52.86 [구간 미측정]|
|horizons/252/k5/wholeCommon/failNet|53|1.06|+49.01 [구간 미측정]|
|horizons/252/k5/wholeCommon/selection|53|1.06|+3.86 [구간 미측정]|
|horizons/252/k5/wholeCommon/replacement|53|1.06|-4.90 [구간 미측정]|
|horizons/252/k5/wholeCommon/total|53|1.06|-1.05 [구간 미측정]|
|horizons/252/k5/deltaSelectionVsWholeOnCommonDates|53|1.06|+0.47 [구간 미측정]|
|horizons/252/k5/deltaOwnTotalVsWholeOnCommonDates|400|8.0|+0.48 [-0.21, +1.40]|
|horizons/252/k5/exLeadersDates/etfNet|51|1.02|+55.47 [구간 미측정]|
|horizons/252/k5/exLeadersDates/passNet|51|1.02|+54.39 [구간 미측정]|
|horizons/252/k5/exLeadersDates/failNet|51|1.02|+50.16 [구간 미측정]|
|horizons/252/k5/exLeadersDates/selection|51|1.02|+4.23 [구간 미측정]|
|horizons/252/k5/exLeadersDates/replacement|51|1.02|-5.31 [구간 미측정]|
|horizons/252/k5/exLeadersDates/total|51|1.02|-1.07 [구간 미측정]|
|horizons/252/k5/leaderDatesOnly/etfNet|2|0.04|+14.22 [구간 미측정]|
|horizons/252/k5/leaderDatesOnly/passNet|2|0.04|+13.85 [구간 미측정]|
|horizons/252/k5/leaderDatesOnly/failNet|2|0.04|+19.66 [구간 미측정]|
|horizons/252/k5/leaderDatesOnly/selection|2|0.04|-5.80 [구간 미측정]|
|horizons/252/k5/leaderDatesOnly/replacement|2|0.04|+5.43 [구간 미측정]|
|horizons/252/k5/leaderDatesOnly/total|2|0.04|-0.37 [구간 미측정]|
|horizons/252/k5/exLeadersPairs/etfNet|53|1.06|+53.91 [구간 미측정]|
|horizons/252/k5/exLeadersPairs/passNet|53|1.06|+52.83 [구간 미측정]|
|horizons/252/k5/exLeadersPairs/failNet|53|1.06|+49.04 [구간 미측정]|
|horizons/252/k5/exLeadersPairs/selection|53|1.06|+3.80 [구간 미측정]|
|horizons/252/k5/exLeadersPairs/replacement|53|1.06|-4.87 [구간 미측정]|
|horizons/252/k5/exLeadersPairs/total|53|1.06|-1.07 [구간 미측정]|
|horizons/252/k5/semiLed/etfNet|40|0.8|+65.79 [구간 미측정]|
|horizons/252/k5/semiLed/passNet|40|0.8|+64.05 [구간 미측정]|
|horizons/252/k5/semiLed/failNet|40|0.8|+59.14 [구간 미측정]|
|horizons/252/k5/semiLed/selection|40|0.8|+4.90 [구간 미측정]|
|horizons/252/k5/semiLed/replacement|40|0.8|-6.65 [구간 미측정]|
|horizons/252/k5/semiLed/total|40|0.8|-1.75 [구간 미측정]|
|horizons/252/k5/nonSemiLed/etfNet|13|0.26|+17.34 [구간 미측정]|
|horizons/252/k5/nonSemiLed/passNet|13|0.26|+18.45 [구간 미측정]|
|horizons/252/k5/nonSemiLed/failNet|13|0.26|+17.81 [구간 미측정]|
|horizons/252/k5/nonSemiLed/selection|13|0.26|+0.64 [구간 미측정]|
|horizons/252/k5/nonSemiLed/replacement|13|0.26|+0.47 [구간 미측정]|
|horizons/252/k5/nonSemiLed/total|13|0.26|+1.11 [구간 미측정]|
|horizons/252/k5/unknownSemi/etfNet|0|0.0|미측정|
|horizons/252/k5/unknownSemi/passNet|0|0.0|미측정|
|horizons/252/k5/unknownSemi/failNet|0|0.0|미측정|
|horizons/252/k5/unknownSemi/selection|0|0.0|미측정|
|horizons/252/k5/unknownSemi/replacement|0|0.0|미측정|
|horizons/252/k5/unknownSemi/total|0|0.0|미측정|
|horizons/252/k5/exTopEntryYear/etfNet|43|0.86|+22.62 [구간 미측정]|
|horizons/252/k5/exTopEntryYear/passNet|43|0.86|+23.53 [구간 미측정]|
|horizons/252/k5/exTopEntryYear/failNet|43|0.86|+21.51 [구간 미측정]|
|horizons/252/k5/exTopEntryYear/selection|43|0.86|+2.02 [구간 미측정]|
|horizons/252/k5/exTopEntryYear/replacement|43|0.86|-1.10 [구간 미측정]|
|horizons/252/k5/exTopEntryYear/total|43|0.86|+0.91 [구간 미측정]|
|horizons/252/k5/exTopTotalEntryYear/etfNet|43|0.86|+54.84 [구간 미측정]|
|horizons/252/k5/exTopTotalEntryYear/passNet|43|0.86|+52.25 [구간 미측정]|
|horizons/252/k5/exTopTotalEntryYear/failNet|43|0.86|+49.35 [구간 미측정]|
|horizons/252/k5/exTopTotalEntryYear/selection|43|0.86|+2.90 [구간 미측정]|
|horizons/252/k5/exTopTotalEntryYear/replacement|43|0.86|-5.49 [구간 미측정]|
|horizons/252/k5/exTopTotalEntryYear/total|43|0.86|-2.59 [구간 미측정]|
|horizons/252/k5/ownExLeadersDates/etfNet|329|6.58|+23.74 [+4.18, +56.28]|
|horizons/252/k5/ownExLeadersDates/passNet|329|6.58|+22.88 [+4.38, +53.71]|
|horizons/252/k5/ownExLeadersDates/total|329|6.58|-0.86 [-3.40, +1.14]|
|horizons/252/k5/ownExLeadersDates/stockOnlyTotal|329|6.58|-4.32 [-17.01, +5.68]|
|horizons/252/k5/ownSemiLed/etfNet|252|5.04|+36.03 [+6.58, +90.31]|
|horizons/252/k5/ownSemiLed/passNet|252|5.04|+35.05 [+6.66, +87.51]|
|horizons/252/k5/ownSemiLed/total|252|5.04|-0.98 [-3.79, +0.85]|
|horizons/252/k5/ownSemiLed/stockOnlyTotal|252|5.04|-4.90 [-18.96, +4.24]|
|horizons/252/k5/ownNonSemiLed/etfNet|129|2.58|+10.94 [-14.01, +48.64]|
|horizons/252/k5/ownNonSemiLed/passNet|129|2.58|+11.05 [-13.03, +47.96]|
|horizons/252/k5/ownNonSemiLed/total|129|2.58|+0.12 [-2.60, +3.99]|
|horizons/252/k5/ownNonSemiLed/stockOnlyTotal|129|2.58|+0.58 [-12.98, +19.96]|
|horizons/252/k5/ownUnknownSemi/etfNet|19|0.38|-10.15 [구간 미측정]|
|horizons/252/k5/ownUnknownSemi/passNet|19|0.38|-10.89 [구간 미측정]|
|horizons/252/k5/ownUnknownSemi/total|19|0.38|-0.74 [구간 미측정]|
|horizons/252/k5/ownUnknownSemi/stockOnlyTotal|19|0.38|-3.70 [구간 미측정]|
|horizons/252/k5/ownExTopEntryYear/etfNet|347|6.94|+25.48 [+1.34, +70.70]|
|horizons/252/k5/ownExTopEntryYear/passNet|347|6.94|+24.05 [+1.28, +67.29]|
|horizons/252/k5/ownExTopEntryYear/total|347|6.94|-1.43 [-3.56, -0.08]|
|horizons/252/k5/ownExTopEntryYear/stockOnlyTotal|347|6.94|-7.13 [-17.82, -0.39]|
|horizons/252/seedCommon/selection|0|0.0|미측정|
|horizons/252/seedCommon/replacement|0|0.0|미측정|
|horizons/252/seedCommon/total|0|0.0|미측정|
|horizons/252/seedCommon/ownTotal|400|8.0|-0.95 [-3.44, +0.83]|
|horizons/252/seedAvailable/selection|239|4.78|+2.10 [-0.86, +5.49]|
|horizons/252/seedAvailable/replacement|239|4.78|-3.71 [-10.28, +0.69]|
|horizons/252/seedAvailable/total|239|4.78|-1.61 [-6.00, +1.62]|
|horizons/252/seedAvailable/ownTotal|400|8.0|-0.95 [-3.44, +0.83]|
|horizons/252/seeds/seed=20261118/paired/etfNet|53|1.06|+53.91 [구간 미측정]|
|horizons/252/seeds/seed=20261118/paired/passNet|53|1.06|+52.86 [구간 미측정]|
|horizons/252/seeds/seed=20261118/paired/failNet|53|1.06|+49.01 [구간 미측정]|
|horizons/252/seeds/seed=20261118/paired/selection|53|1.06|+3.86 [구간 미측정]|
|horizons/252/seeds/seed=20261118/paired/replacement|53|1.06|-4.90 [구간 미측정]|
|horizons/252/seeds/seed=20261118/paired/total|53|1.06|-1.05 [구간 미측정]|
|horizons/252/seeds/seed=20261118/pairedCommon/etfNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261118/pairedCommon/passNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261118/pairedCommon/failNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261118/pairedCommon/selection|0|0.0|미측정|
|horizons/252/seeds/seed=20261118/pairedCommon/replacement|0|0.0|미측정|
|horizons/252/seeds/seed=20261118/pairedCommon/total|0|0.0|미측정|
|horizons/252/seeds/seed=20261118/own/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261118/own/passNet|400|8.0|+25.13 [+2.79, +63.10]|
|horizons/252/seeds/seed=20261118/own/total|400|8.0|-0.62 [-2.67, +1.12]|
|horizons/252/seeds/seed=20261118/own/stockOnlyTotal|400|8.0|-3.08 [-13.33, +5.60]|
|horizons/252/seeds/seed=20261118/ownCommon/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261118/ownCommon/passNet|400|8.0|+25.13 [+2.79, +63.10]|
|horizons/252/seeds/seed=20261118/ownCommon/total|400|8.0|-0.62 [-2.67, +1.12]|
|horizons/252/seeds/seed=20261118/ownCommon/stockOnlyTotal|400|8.0|-3.08 [-13.33, +5.60]|
|horizons/252/seeds/seed=20261119/paired/etfNet|52|1.04|+38.91 [구간 미측정]|
|horizons/252/seeds/seed=20261119/paired/passNet|52|1.04|+37.36 [구간 미측정]|
|horizons/252/seeds/seed=20261119/paired/failNet|52|1.04|+35.72 [구간 미측정]|
|horizons/252/seeds/seed=20261119/paired/selection|52|1.04|+1.64 [구간 미측정]|
|horizons/252/seeds/seed=20261119/paired/replacement|52|1.04|-3.19 [구간 미측정]|
|horizons/252/seeds/seed=20261119/paired/total|52|1.04|-1.55 [구간 미측정]|
|horizons/252/seeds/seed=20261119/pairedCommon/etfNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261119/pairedCommon/passNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261119/pairedCommon/failNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261119/pairedCommon/selection|0|0.0|미측정|
|horizons/252/seeds/seed=20261119/pairedCommon/replacement|0|0.0|미측정|
|horizons/252/seeds/seed=20261119/pairedCommon/total|0|0.0|미측정|
|horizons/252/seeds/seed=20261119/own/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261119/own/passNet|400|8.0|+24.83 [+2.82, +61.66]|
|horizons/252/seeds/seed=20261119/own/total|400|8.0|-0.91 [-3.76, +1.10]|
|horizons/252/seeds/seed=20261119/own/stockOnlyTotal|400|8.0|-4.55 [-18.78, +5.48]|
|horizons/252/seeds/seed=20261119/ownCommon/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261119/ownCommon/passNet|400|8.0|+24.83 [+2.82, +61.66]|
|horizons/252/seeds/seed=20261119/ownCommon/total|400|8.0|-0.91 [-3.76, +1.10]|
|horizons/252/seeds/seed=20261119/ownCommon/stockOnlyTotal|400|8.0|-4.55 [-18.78, +5.48]|
|horizons/252/seeds/seed=20261120/paired/etfNet|46|0.92|+46.37 [구간 미측정]|
|horizons/252/seeds/seed=20261120/paired/passNet|46|0.92|+43.66 [구간 미측정]|
|horizons/252/seeds/seed=20261120/paired/failNet|46|0.92|+43.06 [구간 미측정]|
|horizons/252/seeds/seed=20261120/paired/selection|46|0.92|+0.60 [구간 미측정]|
|horizons/252/seeds/seed=20261120/paired/replacement|46|0.92|-3.31 [구간 미측정]|
|horizons/252/seeds/seed=20261120/paired/total|46|0.92|-2.71 [구간 미측정]|
|horizons/252/seeds/seed=20261120/pairedCommon/etfNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261120/pairedCommon/passNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261120/pairedCommon/failNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261120/pairedCommon/selection|0|0.0|미측정|
|horizons/252/seeds/seed=20261120/pairedCommon/replacement|0|0.0|미측정|
|horizons/252/seeds/seed=20261120/pairedCommon/total|0|0.0|미측정|
|horizons/252/seeds/seed=20261120/own/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261120/own/passNet|400|8.0|+24.83 [+2.60, +62.62]|
|horizons/252/seeds/seed=20261120/own/total|400|8.0|-0.92 [-2.94, +0.55]|
|horizons/252/seeds/seed=20261120/own/stockOnlyTotal|400|8.0|-4.58 [-14.69, +2.73]|
|horizons/252/seeds/seed=20261120/ownCommon/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261120/ownCommon/passNet|400|8.0|+24.83 [+2.60, +62.62]|
|horizons/252/seeds/seed=20261120/ownCommon/total|400|8.0|-0.92 [-2.94, +0.55]|
|horizons/252/seeds/seed=20261120/ownCommon/stockOnlyTotal|400|8.0|-4.58 [-14.69, +2.73]|
|horizons/252/seeds/seed=20261121/paired/etfNet|52|1.04|+33.46 [구간 미측정]|
|horizons/252/seeds/seed=20261121/paired/passNet|52|1.04|+31.98 [구간 미측정]|
|horizons/252/seeds/seed=20261121/paired/failNet|52|1.04|+30.89 [구간 미측정]|
|horizons/252/seeds/seed=20261121/paired/selection|52|1.04|+1.09 [구간 미측정]|
|horizons/252/seeds/seed=20261121/paired/replacement|52|1.04|-2.57 [구간 미측정]|
|horizons/252/seeds/seed=20261121/paired/total|52|1.04|-1.48 [구간 미측정]|
|horizons/252/seeds/seed=20261121/pairedCommon/etfNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261121/pairedCommon/passNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261121/pairedCommon/failNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261121/pairedCommon/selection|0|0.0|미측정|
|horizons/252/seeds/seed=20261121/pairedCommon/replacement|0|0.0|미측정|
|horizons/252/seeds/seed=20261121/pairedCommon/total|0|0.0|미측정|
|horizons/252/seeds/seed=20261121/own/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261121/own/passNet|400|8.0|+24.76 [+2.58, +62.14]|
|horizons/252/seeds/seed=20261121/own/total|400|8.0|-0.99 [-3.45, +0.95]|
|horizons/252/seeds/seed=20261121/own/stockOnlyTotal|400|8.0|-4.93 [-17.26, +4.77]|
|horizons/252/seeds/seed=20261121/ownCommon/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261121/ownCommon/passNet|400|8.0|+24.76 [+2.58, +62.14]|
|horizons/252/seeds/seed=20261121/ownCommon/total|400|8.0|-0.99 [-3.45, +0.95]|
|horizons/252/seeds/seed=20261121/ownCommon/stockOnlyTotal|400|8.0|-4.93 [-17.26, +4.77]|
|horizons/252/seeds/seed=20261122/paired/etfNet|51|1.02|+54.34 [구간 미측정]|
|horizons/252/seeds/seed=20261122/paired/passNet|51|1.02|+50.94 [구간 미측정]|
|horizons/252/seeds/seed=20261122/paired/failNet|51|1.02|+48.05 [구간 미측정]|
|horizons/252/seeds/seed=20261122/paired/selection|51|1.02|+2.89 [구간 미측정]|
|horizons/252/seeds/seed=20261122/paired/replacement|51|1.02|-6.29 [구간 미측정]|
|horizons/252/seeds/seed=20261122/paired/total|51|1.02|-3.40 [구간 미측정]|
|horizons/252/seeds/seed=20261122/pairedCommon/etfNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261122/pairedCommon/passNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261122/pairedCommon/failNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261122/pairedCommon/selection|0|0.0|미측정|
|horizons/252/seeds/seed=20261122/pairedCommon/replacement|0|0.0|미측정|
|horizons/252/seeds/seed=20261122/pairedCommon/total|0|0.0|미측정|
|horizons/252/seeds/seed=20261122/own/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261122/own/passNet|400|8.0|+24.91 [+2.92, +61.90]|
|horizons/252/seeds/seed=20261122/own/total|400|8.0|-0.83 [-3.57, +1.08]|
|horizons/252/seeds/seed=20261122/own/stockOnlyTotal|400|8.0|-4.17 [-17.85, +5.42]|
|horizons/252/seeds/seed=20261122/ownCommon/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261122/ownCommon/passNet|400|8.0|+24.91 [+2.92, +61.90]|
|horizons/252/seeds/seed=20261122/ownCommon/total|400|8.0|-0.83 [-3.57, +1.08]|
|horizons/252/seeds/seed=20261122/ownCommon/stockOnlyTotal|400|8.0|-4.17 [-17.85, +5.42]|
|horizons/252/seeds/seed=20261123/paired/etfNet|46|0.92|+41.18 [구간 미측정]|
|horizons/252/seeds/seed=20261123/paired/passNet|46|0.92|+38.63 [구간 미측정]|
|horizons/252/seeds/seed=20261123/paired/failNet|46|0.92|+36.22 [구간 미측정]|
|horizons/252/seeds/seed=20261123/paired/selection|46|0.92|+2.41 [구간 미측정]|
|horizons/252/seeds/seed=20261123/paired/replacement|46|0.92|-4.96 [구간 미측정]|
|horizons/252/seeds/seed=20261123/paired/total|46|0.92|-2.55 [구간 미측정]|
|horizons/252/seeds/seed=20261123/pairedCommon/etfNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261123/pairedCommon/passNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261123/pairedCommon/failNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261123/pairedCommon/selection|0|0.0|미측정|
|horizons/252/seeds/seed=20261123/pairedCommon/replacement|0|0.0|미측정|
|horizons/252/seeds/seed=20261123/pairedCommon/total|0|0.0|미측정|
|horizons/252/seeds/seed=20261123/own/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261123/own/passNet|400|8.0|+24.71 [+2.65, +61.56]|
|horizons/252/seeds/seed=20261123/own/total|400|8.0|-1.03 [-3.95, +0.98]|
|horizons/252/seeds/seed=20261123/own/stockOnlyTotal|400|8.0|-5.16 [-19.73, +4.89]|
|horizons/252/seeds/seed=20261123/ownCommon/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261123/ownCommon/passNet|400|8.0|+24.71 [+2.65, +61.56]|
|horizons/252/seeds/seed=20261123/ownCommon/total|400|8.0|-1.03 [-3.95, +0.98]|
|horizons/252/seeds/seed=20261123/ownCommon/stockOnlyTotal|400|8.0|-5.16 [-19.73, +4.89]|
|horizons/252/seeds/seed=20261124/paired/etfNet|49|0.98|+51.05 [구간 미측정]|
|horizons/252/seeds/seed=20261124/paired/passNet|49|0.98|+49.51 [구간 미측정]|
|horizons/252/seeds/seed=20261124/paired/failNet|49|0.98|+46.19 [구간 미측정]|
|horizons/252/seeds/seed=20261124/paired/selection|49|0.98|+3.32 [구간 미측정]|
|horizons/252/seeds/seed=20261124/paired/replacement|49|0.98|-4.87 [구간 미측정]|
|horizons/252/seeds/seed=20261124/paired/total|49|0.98|-1.55 [구간 미측정]|
|horizons/252/seeds/seed=20261124/pairedCommon/etfNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261124/pairedCommon/passNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261124/pairedCommon/failNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261124/pairedCommon/selection|0|0.0|미측정|
|horizons/252/seeds/seed=20261124/pairedCommon/replacement|0|0.0|미측정|
|horizons/252/seeds/seed=20261124/pairedCommon/total|0|0.0|미측정|
|horizons/252/seeds/seed=20261124/own/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261124/own/passNet|400|8.0|+24.48 [+2.60, +61.22]|
|horizons/252/seeds/seed=20261124/own/total|400|8.0|-1.27 [-4.23, +0.65]|
|horizons/252/seeds/seed=20261124/own/stockOnlyTotal|400|8.0|-6.33 [-21.13, +3.24]|
|horizons/252/seeds/seed=20261124/ownCommon/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261124/ownCommon/passNet|400|8.0|+24.48 [+2.60, +61.22]|
|horizons/252/seeds/seed=20261124/ownCommon/total|400|8.0|-1.27 [-4.23, +0.65]|
|horizons/252/seeds/seed=20261124/ownCommon/stockOnlyTotal|400|8.0|-6.33 [-21.13, +3.24]|
|horizons/252/seeds/seed=20261125/paired/etfNet|46|0.92|+38.12 [구간 미측정]|
|horizons/252/seeds/seed=20261125/paired/passNet|46|0.92|+36.37 [구간 미측정]|
|horizons/252/seeds/seed=20261125/paired/failNet|46|0.92|+33.72 [구간 미측정]|
|horizons/252/seeds/seed=20261125/paired/selection|46|0.92|+2.66 [구간 미측정]|
|horizons/252/seeds/seed=20261125/paired/replacement|46|0.92|-4.41 [구간 미측정]|
|horizons/252/seeds/seed=20261125/paired/total|46|0.92|-1.75 [구간 미측정]|
|horizons/252/seeds/seed=20261125/pairedCommon/etfNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261125/pairedCommon/passNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261125/pairedCommon/failNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261125/pairedCommon/selection|0|0.0|미측정|
|horizons/252/seeds/seed=20261125/pairedCommon/replacement|0|0.0|미측정|
|horizons/252/seeds/seed=20261125/pairedCommon/total|0|0.0|미측정|
|horizons/252/seeds/seed=20261125/own/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261125/own/passNet|400|8.0|+24.39 [+2.02, +61.85]|
|horizons/252/seeds/seed=20261125/own/total|400|8.0|-1.35 [-3.70, +0.25]|
|horizons/252/seeds/seed=20261125/own/stockOnlyTotal|400|8.0|-6.76 [-18.50, +1.26]|
|horizons/252/seeds/seed=20261125/ownCommon/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261125/ownCommon/passNet|400|8.0|+24.39 [+2.02, +61.85]|
|horizons/252/seeds/seed=20261125/ownCommon/total|400|8.0|-1.35 [-3.70, +0.25]|
|horizons/252/seeds/seed=20261125/ownCommon/stockOnlyTotal|400|8.0|-6.76 [-18.50, +1.26]|
|horizons/252/seeds/seed=20261126/paired/etfNet|59|1.18|+52.38 [구간 미측정]|
|horizons/252/seeds/seed=20261126/paired/passNet|59|1.18|+51.43 [구간 미측정]|
|horizons/252/seeds/seed=20261126/paired/failNet|59|1.18|+45.82 [구간 미측정]|
|horizons/252/seeds/seed=20261126/paired/selection|59|1.18|+5.60 [구간 미측정]|
|horizons/252/seeds/seed=20261126/paired/replacement|59|1.18|-6.56 [구간 미측정]|
|horizons/252/seeds/seed=20261126/paired/total|59|1.18|-0.95 [구간 미측정]|
|horizons/252/seeds/seed=20261126/pairedCommon/etfNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261126/pairedCommon/passNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261126/pairedCommon/failNet|0|0.0|미측정|
|horizons/252/seeds/seed=20261126/pairedCommon/selection|0|0.0|미측정|
|horizons/252/seeds/seed=20261126/pairedCommon/replacement|0|0.0|미측정|
|horizons/252/seeds/seed=20261126/pairedCommon/total|0|0.0|미측정|
|horizons/252/seeds/seed=20261126/own/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261126/own/passNet|400|8.0|+25.13 [+2.65, +62.93]|
|horizons/252/seeds/seed=20261126/own/total|400|8.0|-0.62 [-2.94, +1.39]|
|horizons/252/seeds/seed=20261126/own/stockOnlyTotal|400|8.0|-3.08 [-14.71, +6.95]|
|horizons/252/seeds/seed=20261126/ownCommon/etfNet|400|8.0|+25.74 [+2.50, +64.92]|
|horizons/252/seeds/seed=20261126/ownCommon/passNet|400|8.0|+25.13 [+2.65, +62.93]|
|horizons/252/seeds/seed=20261126/ownCommon/total|400|8.0|-0.62 [-2.94, +1.39]|
|horizons/252/seeds/seed=20261126/ownCommon/stockOnlyTotal|400|8.0|-3.08 [-14.71, +6.95]|
|primary6/wholePassVsFail|414|16.56|+2.70 [-2.65, +7.60]|
|primary6/originalK5PassVsFail|60|2.4|+1.29 [-0.25, +2.43]|
|primary6/originalK5PassVsETF|60|2.4|-0.50 [-3.34, +1.79]|

[기계판독 전체 통계](results/estimates.csv) · [미국 전체 요약](results/US/summary.json) · [한국 전체 요약](results/KR/summary.json) · [미국 날짜별 원본](results/US/) · [한국 날짜별 원본](results/KR/)
