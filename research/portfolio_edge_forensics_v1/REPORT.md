# Portfolio Edge Forensics v1 — 투자위원회 독해

**결론: INCONCLUSIVE — 저장 경로의 우위가 집중된 기간과 복리 구조는 측정했지만 종목선정 알파는 식별하지 못했다.**

## 먼저 답할 네 질문

1. **어디서 앞섰나?** KR C2 전체 14.4326% vs ETF 12.6144%, 차이 +1.8181pp는 기존 사실이다. 새 진단: 누적 로그 초과 0.218985 중 상위3 연도 2018, 2022, 2014가 0.512789 (234.2%)를 제공했다. 이 세 관측 연도 구간을 양쪽에서 제거하면 남은 로그 초과 -0.293803, 남은 시간 기준 CAGR 차이 -3.3148pp다. 음의 다른 기간 때문에 기여율은100%를 넘는다. 사후 민감도이지 거래 가능한 새 전략이나 OOS가 아니다.

2. **최근 왜 뒤졌나?** 2024~2026 관측 구간(2023-12-29~2026-09-14) 후보 142.1506% vs ETF 206.9720%, 차이 -64.8214pp; 연환산 차이 -12.6735pp. 어느 기간의 상대자산이 감소했는지는 아래 표로 입증된다. 종목·산업·베타·현금 대체·교체비용 각각이 이 감소를 얼마나 만들었는지는 matching executed leg P&L이 없어 UNKNOWN이다.

3. **유지·개선·중단에 필요한 증거는?** 기존 C2는 연구 대조군으로 보존하며 운영 기본 ETF를 바꾸지 않는다. 유지/승격에는 권리·주주수익 적격성과 동일 노출·비용 대조, 독립 표본이 필요하다. 개선에는 먼저 비용/거래 장부나 고정 노출 통제에서 증분 원인이 식별돼야 한다. 중단은 등록된 경제적 기각 기준을 충족할 때 판단해야 하며, 이번 사후 특정 연도 제거만으로 규칙을 바꾸거나 중단하지 않는다.

4. **다음 단 하나의 가설은?** 기존 제안 `c2-fixed-exposure-attribution-v1`만 재사용: 원래 선택·날짜·비중을 고정한 C2가 당시까지의 자료로 정한 거래 가능한 ETF+KRW 현금 노출 대조군을 넘는 비용 후 산술 기여를 남기는가? 새 arm·종목 수·최적 임계값을 만들지 않는다. 권리, 전체 주주수익, 253개 과거 종가, 교정 ETF warmup, 현금 기준을 먼저 증빙하고 독립 검토·정확한 소유자 실행 승인이 필요하다. 이번에는 실행하지 않았다.

## 새로운 측정과 수학적 원인

동일 첫 관측 원금1 기준 최종자산: 후보 6.317645, ETF 5.075176. 기간 2013-01-11~2026-09-14, 715관측/714수익 구간, KRW, NET_ALREADY_CHARGED. 초기2013-01-07 자본점은 덧붙이지 않았다.

정확한 항등식: 연 로그 성장률 차이 1.601577 log-points = 관측 구간 산술 active 1.002013pp + Jensen 차이 0.599564 log-points. Jensen 항은 로그 우위의 37.44%다. (Jensen=Σ[log(1+r)−r]; 모든 고차 모멘트 포함.) 이를 ETF 성장률 수준에서 지수변환하면 CAGR 차이 +1.8181pp가 된다. **산술 active는 노출·산업·시점·비용을 포함하며 종목선정 알파가 아니다. Jensen도 낮은 분산의 인과 효과로 단정하지 않는다.** 기존 일별 요약의 +0.620/+1.131pp를 주간 분해의 새 결과로 재발표하지 않는다.

| 달력 창 | 유효/예정 | 후보 평균 수익% | ETF 평균 수익% | 평균 차이pp | 평균 상대자산 증가% | ETF 결합항pp | 비중첩 시간 블록 |
|---|---:|---:|---:|---:|---:|---:|---:|
|CALENDAR_6M|688/715|8.2682|8.7875|-0.5193|+1.1553|-1.6746|26|
|CALENDAR_12M|662/715|16.6330|17.5134|-0.8804|+3.2104|-4.0908|13|

W=(1+Rc)/(1+Re)−1이면 Rc−Re=W+Re×W. 위 결합항은 mean(Re×W)다. ETF가 강한 구간의 미참여가 수익률 차이에 더 큰 금액 가중을 주므로 평균 상대자산 증가가 양수여도 평균 pp 차이는 음수일 수 있다. 전체기간 복리, 중첩 창의 동일가중 평균, 평균 상대자산 증가는 서로 다른 추정량이다. 겹친 창은 독립 시행이 아니고 비중첩 블록도 독립성을 보장하지 않는다.

### 같은 방법의 KR/US 요약 — 모두 저장 KRW 경로

| 경로 | 후보/ETF CAGR% | 차이pp | 연 산술 active pp | 연 Jensen log-points | 관측 연환산 SD 후보/ETF% | 관측 MDD 후보/ETF% |
|---|---|---:|---:|---:|---|---|
|KR/C2-P0|14.4326/12.6144|+1.8181|+1.0020|+0.5996|16.4612/19.8331|-27.9568/-34.2757|
|US/C1-P0|7.2288/16.7064|-9.4776|-8.9525|+0.4828|11.4809/14.9698|-23.1345/-28.5506|
|US/C2-P0|12.9877/16.7064|-3.7187|-3.1081|-0.1301|15.8385/14.9698|-32.4759/-28.5506|

US는 KRW·환율 포함이며 USD 결과가 아니다. 이 표의 숫자는 source의 유효 주주수익/라이선스 승인을 뜻하지 않는다. 주식 부분 배당·교정ETF gross 분배 기준 차이와 미국 생존편향을 계승한다. NET_ALREADY_CHARGED는 원 거래비용이 이미 반영됐다는 뜻이며 배당세·누락된 기업행동까지 검증했다는 뜻이 아니다. 비용을 추가로 빼지 않았다. 종목 수는 새로 고정하지 않았고 역사3·5종목은 대조군일 뿐이다.

## 국가별 기간·위험·열세와 민감도

각 연도는 수익 구간의 종료 관측일로 배정한다. 연도 경계를 넘는 한 주 전체를 종료 연도에 귀속하며, 정확한12/31 가격을 만들지 않는다. 2013과2026은 부분 연도다. CSV에 실제 시작/종료와 원본 포인터를 남긴다. 기존 일별 연수익 요약과 경계가 달라 값이 같을 필요는 없다.

### KR/C2-P0 — KRW / FX 포함 False

Study ID: `weekly-passive-first-v1-replay-corrected-benchmark`. C1/C2는 이 저장 CHAMPION 연구의 경로명이며 Market C1 정식 연구가 아니다.

DEFINITION_INTERNAL_REPLAY_V16 · POST_OUTCOME_EXPOSED_DESCRIPTIVE_SAVED_NAV_FORENSICS_NOT_ALPHA · REPLAY_STOCK_AND_CASH_OR_ETF_MIX_PARTIAL_SHAREHOLDER_ECONOMICS vs PHASE_C_RECONCILED_GROSS_ETF_TOTAL_RETURN · NET_ALREADY_CHARGED

| 종료 관측 연도 | 실제 시작 ~ 종료 | 후보% | ETF% | 차이pp | 로그 초과 |
|---|---|---:|---:|---:|---:|
|2013|2013-01-11 ~ 2013-12-27|12.5902|0.8106|+11.7796|+0.110512|
|2014|2013-12-27 ~ 2014-12-26|11.0269|-4.9375|+15.9644|+0.155238|
|2015|2014-12-26 ~ 2015-12-31|7.3369|-1.4751|+8.8120|+0.085663|
|2016|2015-12-31 ~ 2016-12-30|5.2558|10.1870|-4.9312|-0.045785|
|2017|2016-12-30 ~ 2017-12-29|25.1921|27.1001|-1.9080|-0.015125|
|2018|2017-12-29 ~ 2018-12-28|0.1994|-17.3210|+17.5204|+0.192197|
|2019|2018-12-28 ~ 2019-12-27|3.5608|14.8028|-11.2419|-0.103056|
|2020|2019-12-27 ~ 2020-12-31|25.5320|35.0566|-9.5247|-0.073134|
|2021|2020-12-31 ~ 2021-12-31|11.7448|2.9991|+8.7457|+0.081498|
|2022|2021-12-31 ~ 2022-12-30|-10.5112|-24.1499|+13.6387|+0.165354|
|2023|2022-12-30 ~ 2023-12-29|13.2813|24.8424|-11.5611|-0.097178|
|2024|2023-12-29 ~ 2024-12-27|3.2727|-9.1313|+12.4040|+0.127957|
|2025|2024-12-27 ~ 2025-12-26|77.8194|88.0156|-10.1962|-0.055757|
|2026|2025-12-26 ~ 2026-09-14|31.8624|79.6761|-47.8137|-0.309397|

연도 차이 분포: {
  "lossCount": 7,
  "meanPp": -0.5937188085885233,
  "n": 14,
  "p05Pp": -24.249516737088026,
  "status": "MEASURED_DESCRIPTIVE_NO_INFERENTIAL_CI",
  "tailCount": 1,
  "tieCount": 0,
  "winRatePct": 50.0,
  "worst5PctMeanPp": -47.81373876242182
}

| 고정 구간 | 실제 시작 ~ 종료 | 후보 CAGR% | ETF CAGR% | 차이pp |
|---|---|---:|---:|---:|
|FULL|2013-01-11 ~ 2026-09-14|14.4326|12.6144|+1.8181|
|FIRST_EQUAL_TIME_HALF|2013-01-11 ~ 2019-11-08|8.6963|2.5879|+6.1083|
|SECOND_EQUAL_TIME_HALF|2019-11-15 ~ 2026-09-14|20.4586|23.3792|-2.9206|
|RECENT_2024_2026|2023-12-29 ~ 2026-09-14|38.5803|51.2538|-12.6735|

반기 사이 따로 정산한1개 구간: {
  "benchmarkCagrPct": 117.38859325148448,
  "benchmarkLogWealth": 0.01488220628389748,
  "benchmarkReturnPct": 1.4993497717826543,
  "benchmarkWealthFromOne": 1.0149934977178265,
  "cagrGapPp": -101.0649135968773,
  "candidateCagrPct": 16.32367965460718,
  "candidateLogWealth": 0.002897924607182553,
  "candidateReturnPct": 0.29021276497498416,
  "candidateWealthFromOne": 1.0029021276497498,
  "elapsedObservedDays": 7,
  "excessReturnPp": -1.2091370068076701,
  "from": "2019-11-08",
  "intervals": 1,
  "logExcess": -0.011984281676714927,
  "relativeWealthReturnPct": -1.1912756185397912,
  "through": "2019-11-15",
  "years": 0.019165349048919554
}

관측 구간 위험: 후보/ETF 연환산 SD 16.4612/19.8331%, downside RMS 10.5463/12.7060%. 관측 빈도 연환산이며 일별 위험/CVaR로 부르지 않는다.

관측 MDD 후보 -27.9568% / ETF -34.2757%. 상대자산 최악 낙폭/회복: `{"mddPct": -49.857324490419195, "peakDate": "2025-07-04", "troughDate": "2026-06-26", "recoveryDate": null, "status": "UNRECOVERED_THROUGH_LAST_OBSERVATION", "peakToRecoveryDays": null, "peakToLastObservationDays": 437, "longestUnderwaterEpisode": {"peakDate": "2019-01-04", "endDate": "2022-06-17", "calendarDays": 1260, "recovered": true}}`.

양·음 로그 기여 상위5개 관측 구간:

| 방향 | 시작 ~ 종료 | 후보% | ETF% | 로그 초과 |
|---|---|---:|---:|---:|
|양|2026-07-31 ~ 2026-08-07|-1.5978|-9.8603|+0.087702|
|양|2024-01-26 ~ 2024-02-02|14.7701|5.5385|+0.083855|
|양|2020-08-28 ~ 2020-09-04|8.2565|-0.2400|+0.081736|
|양|2026-06-26 ~ 2026-07-03|3.1988|-4.6368|+0.078964|
|양|2024-11-22 ~ 2024-11-29|4.5836|-2.1142|+0.066186|
|음|2026-02-20 ~ 2026-02-27|-0.3144|9.0614|-0.089889|
|음|2026-08-07 ~ 2026-08-14|2.6289|12.2031|-0.089190|
|음|2026-06-12 ~ 2026-06-19|4.0504|13.6459|-0.088212|
|음|2026-05-01 ~ 2026-05-08|6.7873|15.9201|-0.082062|
|음|2026-05-22 ~ 2026-05-29|1.0405|9.2947|-0.078526|

사후 leave-period-out: 양쪽의 같은 관측 구간과 경과일을 제거한 성장연산자 진단. 원 시간에 현금·0수익을 삽입한 새 NAV가 아니다.

| 제거 | 연도 | 남은 로그 초과 | 남은 시간 CAGR 차이pp |
|---|---|---:|---:|
|LEAVE_ONE_YEAR_OUT|2013|+0.108474|+0.9729|
|LEAVE_ONE_YEAR_OUT|2014|+0.063747|+0.5754|
|LEAVE_ONE_YEAR_OUT|2015|+0.133322|+1.2050|
|LEAVE_ONE_YEAR_OUT|2016|+0.264771|+2.3815|
|LEAVE_ONE_YEAR_OUT|2017|+0.234111|+2.0791|
|LEAVE_ONE_YEAR_OUT|2018|+0.026789|+0.2441|
|LEAVE_ONE_YEAR_OUT|2019|+0.322042|+2.8931|
|LEAVE_ONE_YEAR_OUT|2020|+0.292119|+2.5915|
|LEAVE_ONE_YEAR_OUT|2021|+0.137488|+1.2370|
|LEAVE_ONE_YEAR_OUT|2022|+0.053631|+0.4926|
|LEAVE_ONE_YEAR_OUT|2023|+0.316163|+2.8209|
|LEAVE_ONE_YEAR_OUT|2024|+0.091028|+0.8254|
|LEAVE_ONE_YEAR_OUT|2025|+0.274742|+2.3695|
|LEAVE_ONE_YEAR_OUT|2026|+0.528382|+4.5100|
|REMOVE_LARGEST_POSITIVE_LOG_YEARS_1|2018|+0.026789|+0.2441|
|REMOVE_LARGEST_POSITIVE_LOG_YEARS_3|2018,2022,2014|-0.293803|-3.3148|
|REMOVE_MOST_NEGATIVE_LOG_YEARS_1|2026|+0.528382|+4.5100|

달력 창(기존 #305 값 재사용 + 새 결합항 귀속):

| 창 | 예정/유효/비중첩 | 평균 차이pp | 승률% | 최하위5% 평균pp | 상태별 분모 |
|---|---|---:|---:|---:|---|
|CALENDAR_6M|715/688/26|-0.5193|59.5930|-47.5337|{"MEASURED": 688, "MATURE_TARGET_NO_STORED_ENDPOINT": 7, "IMMATURE_AT_AS_OF": 20}|
|CALENDAR_12M|715/662/13|-0.8804|61.1782|-95.7270|{"MEASURED": 662, "MATURE_TARGET_NO_STORED_ENDPOINT": 7, "IMMATURE_AT_AS_OF": 46}|

원점 연도별/최근2024 이후 달력6/12개월 분포와 모든 누락·미성숙은 results.json/periods.csv에 보존한다. H126/H252, 일별 MDD, 일별 회복은 이 주간 경로에서 UNAVAILABLE이다.

### US/C1-P0 — KRW / FX 포함 True

Study ID: `weekly-passive-first-v1-replay-corrected-benchmark`. C1/C2는 이 저장 CHAMPION 연구의 경로명이며 Market C1 정식 연구가 아니다.

SURVIVORSHIP_BIASED_PARTIAL · POST_OUTCOME_EXPOSED_DESCRIPTIVE_SAVED_NAV_FORENSICS_NOT_ALPHA · REPLAY_STOCK_AND_CASH_OR_ETF_MIX_PARTIAL_SHAREHOLDER_ECONOMICS vs REPLAY_V16_SPY_IN_KRW · NET_ALREADY_CHARGED

| 종료 관측 연도 | 실제 시작 ~ 종료 | 후보% | ETF% | 차이pp | 로그 초과 |
|---|---|---:|---:|---:|---:|
|2013|2013-01-11 ~ 2013-12-27|10.6275|27.2466|-16.6191|-0.139958|
|2014|2013-12-27 ~ 2014-12-26|8.1421|21.0205|-12.8784|-0.112514|
|2015|2014-12-26 ~ 2015-12-31|8.1979|5.8015|+2.3964|+0.022397|
|2016|2015-12-31 ~ 2016-12-30|6.4322|15.2996|-8.8674|-0.080026|
|2017|2016-12-30 ~ 2017-12-29|0.1168|7.9235|-7.8067|-0.075085|
|2018|2017-12-29 ~ 2018-12-28|10.9919|-1.1896|+12.1815|+0.116255|
|2019|2018-12-28 ~ 2019-12-27|14.0234|38.2595|-24.2362|-0.192729|
|2020|2019-12-27 ~ 2020-12-31|-14.2119|10.3682|-24.5800|-0.251941|
|2021|2020-12-31 ~ 2021-12-31|24.3307|40.8750|-16.5443|-0.124928|
|2022|2021-12-31 ~ 2022-12-30|6.4157|-13.2470|+19.6627|+0.204288|
|2023|2022-12-30 ~ 2023-12-29|4.8103|29.2586|-24.4484|-0.209664|
|2024|2023-12-29 ~ 2024-12-27|14.3020|44.4116|-30.1096|-0.233823|
|2025|2024-12-27 ~ 2025-12-26|9.6609|15.0448|-5.3839|-0.047929|
|2026|2025-12-26 ~ 2026-09-14|-0.2329|3.0537|-3.2866|-0.032412|

연도 차이 분포: {
  "lossCount": 11,
  "meanPp": -10.037140893174223,
  "n": 14,
  "p05Pp": -26.515375305445794,
  "status": "MEASURED_DESCRIPTIVE_NO_INFERENTIAL_CI",
  "tailCount": 1,
  "tieCount": 0,
  "winRatePct": 21.428571428571427,
  "worst5PctMeanPp": -30.109551831883387
}

| 고정 구간 | 실제 시작 ~ 종료 | 후보 CAGR% | ETF CAGR% | 차이pp |
|---|---|---:|---:|---:|
|FULL|2013-01-11 ~ 2026-09-14|7.2288|16.7064|-9.4776|
|FIRST_EQUAL_TIME_HALF|2013-01-11 ~ 2019-11-08|7.9418|15.2190|-7.2773|
|SECOND_EQUAL_TIME_HALF|2019-11-15 ~ 2026-09-14|6.1556|17.9572|-11.8017|
|RECENT_2024_2026|2023-12-29 ~ 2026-09-14|8.5977|21.9432|-13.3455|

반기 사이 따로 정산한1개 구간: {
  "benchmarkCagrPct": 151.17124267867956,
  "benchmarkLogWealth": 0.017650611130665808,
  "benchmarkReturnPct": 1.780730371632977,
  "benchmarkWealthFromOne": 1.0178073037163298,
  "cagrGapPp": 114.20347291823522,
  "candidateCagrPct": 265.37471559691477,
  "candidateLogWealth": 0.024833563491087028,
  "candidateReturnPct": 2.514448485562948,
  "candidateWealthFromOne": 1.0251444848556295,
  "elapsedObservedDays": 7,
  "excessReturnPp": 0.7337181139299709,
  "from": "2019-11-08",
  "intervals": 1,
  "logExcess": 0.00718295236042122,
  "relativeWealthReturnPct": 0.7208811640975051,
  "through": "2019-11-15",
  "years": 0.019165349048919554
}

관측 구간 위험: 후보/ETF 연환산 SD 11.4809/14.9698%, downside RMS 7.8560/10.0573%. 관측 빈도 연환산이며 일별 위험/CVaR로 부르지 않는다.

관측 MDD 후보 -23.1345% / ETF -28.5506%. 상대자산 최악 낙폭/회복: `{"mddPct": -71.19928120343508, "peakDate": "2013-01-18", "troughDate": "2026-05-29", "recoveryDate": null, "status": "UNRECOVERED_THROUGH_LAST_OBSERVATION", "peakToRecoveryDays": null, "peakToLastObservationDays": 4987, "longestUnderwaterEpisode": {"peakDate": "2013-01-18", "endDate": "2026-09-14", "calendarDays": 4987, "recovered": false}}`.

양·음 로그 기여 상위5개 관측 구간:

| 방향 | 시작 ~ 종료 | 후보% | ETF% | 로그 초과 |
|---|---|---:|---:|---:|
|양|2026-06-19 ~ 2026-06-26|4.6253|-2.8332|+0.073957|
|양|2016-07-01 ~ 2016-07-08|8.6660|1.4966|+0.068254|
|양|2026-08-14 ~ 2026-08-21|1.2212|-3.4099|+0.046832|
|양|2020-09-04 ~ 2020-09-11|1.4079|-2.8159|+0.042543|
|양|2018-12-14 ~ 2018-12-21|-3.7485|-7.6985|+0.041904|
|음|2020-04-03 ~ 2020-04-10|1.6012|10.3745|-0.082824|
|음|2022-11-04 ~ 2022-11-11|-2.7146|2.4326|-0.051557|
|음|2016-11-04 ~ 2016-11-11|0.5750|5.5382|-0.048169|
|음|2020-05-29 ~ 2020-06-05|-2.7076|2.0657|-0.047897|
|음|2020-05-15 ~ 2020-05-22|-0.7836|3.6877|-0.044080|

사후 leave-period-out: 양쪽의 같은 관측 구간과 경과일을 제거한 성장연산자 진단. 원 시간에 현금·0수익을 삽입한 새 NAV가 아니다.

| 제거 | 연도 | 남은 로그 초과 | 남은 시간 CAGR 차이pp |
|---|---|---:|---:|
|LEAVE_ONE_YEAR_OUT|2013|-1.018111|-8.9153|
|LEAVE_ONE_YEAR_OUT|2014|-1.045555|-9.2128|
|LEAVE_ONE_YEAR_OUT|2015|-1.180467|-10.4726|
|LEAVE_ONE_YEAR_OUT|2016|-1.078044|-9.5257|
|LEAVE_ONE_YEAR_OUT|2017|-1.082984|-9.6152|
|LEAVE_ONE_YEAR_OUT|2018|-1.274324|-11.3087|
|LEAVE_ONE_YEAR_OUT|2019|-0.965340|-8.4435|
|LEAVE_ONE_YEAR_OUT|2020|-0.906128|-8.0981|
|LEAVE_ONE_YEAR_OUT|2021|-1.033141|-9.0015|
|LEAVE_ONE_YEAR_OUT|2022|-1.362357|-12.1731|
|LEAVE_ONE_YEAR_OUT|2023|-0.948406|-8.3450|
|LEAVE_ONE_YEAR_OUT|2024|-0.924246|-8.0692|
|LEAVE_ONE_YEAR_OUT|2025|-1.110140|-9.7964|
|LEAVE_ONE_YEAR_OUT|2026|-1.125658|-9.7727|
|REMOVE_LARGEST_POSITIVE_LOG_YEARS_1|2022|-1.362357|-12.1731|
|REMOVE_LARGEST_POSITIVE_LOG_YEARS_3|2022,2018,2015|-1.501009|-16.1484|
|REMOVE_MOST_NEGATIVE_LOG_YEARS_1|2020|-0.906128|-8.0981|

달력 창(기존 #305 값 재사용 + 새 결합항 귀속):

| 창 | 예정/유효/비중첩 | 평균 차이pp | 승률% | 최하위5% 평균pp | 상태별 분모 |
|---|---|---:|---:|---:|---|
|CALENDAR_6M|715/688/26|-4.6898|26.4535|-21.6484|{"MEASURED": 688, "MATURE_TARGET_NO_STORED_ENDPOINT": 7, "IMMATURE_AT_AS_OF": 20}|
|CALENDAR_12M|715/662/13|-9.9011|21.6012|-36.6246|{"MEASURED": 662, "MATURE_TARGET_NO_STORED_ENDPOINT": 7, "IMMATURE_AT_AS_OF": 46}|

원점 연도별/최근2024 이후 달력6/12개월 분포와 모든 누락·미성숙은 results.json/periods.csv에 보존한다. H126/H252, 일별 MDD, 일별 회복은 이 주간 경로에서 UNAVAILABLE이다.

### US/C2-P0 — KRW / FX 포함 True

Study ID: `weekly-passive-first-v1-replay-corrected-benchmark`. C1/C2는 이 저장 CHAMPION 연구의 경로명이며 Market C1 정식 연구가 아니다.

SURVIVORSHIP_BIASED_PARTIAL · POST_OUTCOME_EXPOSED_DESCRIPTIVE_SAVED_NAV_FORENSICS_NOT_ALPHA · REPLAY_STOCK_AND_CASH_OR_ETF_MIX_PARTIAL_SHAREHOLDER_ECONOMICS vs REPLAY_V16_SPY_IN_KRW · NET_ALREADY_CHARGED

| 종료 관측 연도 | 실제 시작 ~ 종료 | 후보% | ETF% | 차이pp | 로그 초과 |
|---|---|---:|---:|---:|---:|
|2013|2013-01-11 ~ 2013-12-27|19.4974|27.2466|-7.7492|-0.062833|
|2014|2013-12-27 ~ 2014-12-26|14.5978|21.0205|-6.4227|-0.054531|
|2015|2014-12-26 ~ 2015-12-31|10.0669|5.8015|+4.2654|+0.039524|
|2016|2015-12-31 ~ 2016-12-30|12.3738|15.2996|-2.9259|-0.025704|
|2017|2016-12-30 ~ 2017-12-29|2.3199|7.9235|-5.6036|-0.053319|
|2018|2017-12-29 ~ 2018-12-28|9.7686|-1.1896|+10.9582|+0.105172|
|2019|2018-12-28 ~ 2019-12-27|27.1343|38.2595|-11.1253|-0.083889|
|2020|2019-12-27 ~ 2020-12-31|-6.3952|10.3682|-16.7634|-0.164740|
|2021|2020-12-31 ~ 2021-12-31|40.1498|40.8750|-0.7252|-0.005161|
|2022|2021-12-31 ~ 2022-12-30|0.0196|-13.2470|+13.2665|+0.142300|
|2023|2022-12-30 ~ 2023-12-29|12.9100|29.2586|-16.3486|-0.135224|
|2024|2023-12-29 ~ 2024-12-27|29.9639|44.4116|-14.4477|-0.105411|
|2025|2024-12-27 ~ 2025-12-26|13.8914|15.0448|-1.1534|-0.010076|
|2026|2025-12-26 ~ 2026-09-14|0.1204|3.0537|-2.9334|-0.028877|

연도 차이 분포: {
  "lossCount": 11,
  "meanPp": -4.122008850142253,
  "n": 14,
  "p05Pp": -16.493803612569295,
  "status": "MEASURED_DESCRIPTIVE_NO_INFERENTIAL_CI",
  "tailCount": 1,
  "tieCount": 0,
  "winRatePct": 21.428571428571427,
  "worst5PctMeanPp": -16.763393156411745
}

| 고정 구간 | 실제 시작 ~ 종료 | 후보 CAGR% | ETF CAGR% | 차이pp |
|---|---|---:|---:|---:|
|FULL|2013-01-11 ~ 2026-09-14|12.9877|16.7064|-3.7187|
|FIRST_EQUAL_TIME_HALF|2013-01-11 ~ 2019-11-08|12.9228|15.2190|-2.2962|
|SECOND_EQUAL_TIME_HALF|2019-11-15 ~ 2026-09-14|12.5829|17.9572|-5.3743|
|RECENT_2024_2026|2023-12-29 ~ 2026-09-14|15.6184|21.9432|-6.3248|

반기 사이 따로 정산한1개 구간: {
  "benchmarkCagrPct": 151.17124267867956,
  "benchmarkLogWealth": 0.017650611130665808,
  "benchmarkReturnPct": 1.780730371632977,
  "benchmarkWealthFromOne": 1.0178073037163298,
  "cagrGapPp": 247.02842652803722,
  "candidateCagrPct": 398.19966920671675,
  "candidateLogWealth": 0.030776306892106465,
  "candidateReturnPct": 3.125479349353566,
  "candidateWealthFromOne": 1.0312547934935357,
  "elapsedObservedDays": 7,
  "excessReturnPp": 1.344748977720589,
  "from": "2019-11-08",
  "intervals": 1,
  "logExcess": 0.013125695761440657,
  "relativeWealthReturnPct": 1.3212215837030192,
  "through": "2019-11-15",
  "years": 0.019165349048919554
}

관측 구간 위험: 후보/ETF 연환산 SD 15.8385/14.9698%, downside RMS 10.7463/10.0573%. 관측 빈도 연환산이며 일별 위험/CVaR로 부르지 않는다.

관측 MDD 후보 -32.4759% / ETF -28.5506%. 상대자산 최악 낙폭/회복: `{"mddPct": -39.29367039851902, "peakDate": "2016-07-08", "troughDate": "2026-05-29", "recoveryDate": null, "status": "UNRECOVERED_THROUGH_LAST_OBSERVATION", "peakToRecoveryDays": null, "peakToLastObservationDays": 3720, "longestUnderwaterEpisode": {"peakDate": "2016-07-08", "endDate": "2026-09-14", "calendarDays": 3720, "recovered": false}}`.

양·음 로그 기여 상위5개 관측 구간:

| 방향 | 시작 ~ 종료 | 후보% | ETF% | 로그 초과 |
|---|---|---:|---:|---:|
|양|2016-07-01 ~ 2016-07-08|9.3436|1.4966|+0.074469|
|양|2026-06-19 ~ 2026-06-26|3.5017|-2.8332|+0.063159|
|양|2021-04-30 ~ 2021-05-07|6.0885|1.6519|+0.042719|
|양|2022-02-25 ~ 2022-03-04|3.5631|-0.3071|+0.038087|
|양|2026-05-29 ~ 2026-06-05|4.5733|0.8686|+0.036069|
|음|2020-03-13 ~ 2020-03-20|-15.9940|-11.8059|-0.048653|
|음|2022-11-04 ~ 2022-11-11|-1.8890|2.4326|-0.043106|
|음|2023-07-21 ~ 2023-07-28|-3.4011|0.4957|-0.039547|
|음|2020-05-29 ~ 2020-06-05|-1.8796|2.0657|-0.039421|
|음|2020-04-17 ~ 2020-04-24|-3.6106|0.0223|-0.036997|

사후 leave-period-out: 양쪽의 같은 관측 구간과 경과일을 제거한 성장연산자 진단. 원 시간에 현금·0수익을 삽입한 새 NAV가 아니다.

| 제거 | 연도 | 남은 로그 초과 | 남은 시간 CAGR 차이pp |
|---|---|---:|---:|
|LEAVE_ONE_YEAR_OUT|2013|-0.379936|-3.4107|
|LEAVE_ONE_YEAR_OUT|2014|-0.388237|-3.5099|
|LEAVE_ONE_YEAR_OUT|2015|-0.482293|-4.3970|
|LEAVE_ONE_YEAR_OUT|2016|-0.417065|-3.7816|
|LEAVE_ONE_YEAR_OUT|2017|-0.389450|-3.5527|
|LEAVE_ONE_YEAR_OUT|2018|-0.547940|-5.0022|
|LEAVE_ONE_YEAR_OUT|2019|-0.358880|-3.2143|
|LEAVE_ONE_YEAR_OUT|2020|-0.278028|-2.5467|
|LEAVE_ONE_YEAR_OUT|2021|-0.437608|-3.9025|
|LEAVE_ONE_YEAR_OUT|2022|-0.585069|-5.3884|
|LEAVE_ONE_YEAR_OUT|2023|-0.307544|-2.7748|
|LEAVE_ONE_YEAR_OUT|2024|-0.337358|-3.0137|
|LEAVE_ONE_YEAR_OUT|2025|-0.432693|-3.9206|
|LEAVE_ONE_YEAR_OUT|2026|-0.413891|-3.6924|
|REMOVE_LARGEST_POSITIVE_LOG_YEARS_1|2022|-0.585069|-5.3884|
|REMOVE_LARGEST_POSITIVE_LOG_YEARS_3|2022,2018,2015|-0.729765|-8.1350|
|REMOVE_MOST_NEGATIVE_LOG_YEARS_1|2020|-0.278028|-2.5467|

달력 창(기존 #305 값 재사용 + 새 결합항 귀속):

| 창 | 예정/유효/비중첩 | 평균 차이pp | 승률% | 최하위5% 평균pp | 상태별 분모 |
|---|---|---:|---:|---:|---|
|CALENDAR_6M|715/688/26|-1.7829|40.5523|-13.9204|{"MEASURED": 688, "MATURE_TARGET_NO_STORED_ENDPOINT": 7, "IMMATURE_AT_AS_OF": 20}|
|CALENDAR_12M|715/662/13|-3.9478|32.3263|-23.5254|{"MEASURED": 662, "MATURE_TARGET_NO_STORED_ENDPOINT": 7, "IMMATURE_AT_AS_OF": 46}|

원점 연도별/최근2024 이후 달력6/12개월 분포와 모든 누락·미성숙은 results.json/periods.csv에 보존한다. H126/H252, 일별 MDD, 일별 회복은 이 주간 경로에서 UNAVAILABLE이다.

## 가설별 증거 수준과 남은 원인

| 원인 가설 | 수준 | 판단 |
|---|---|---|
| 몇 시기에 집중된 상대성과 | MEASURED | 연도 로그 합과 고정 제거 민감도로 정확히 확인. 사후 설명이며 재현될 국면 선택 규칙이 아님 |
| 낮은 위험/복리만으로 모든 우위를 설명 | MEASURED / 인과 UNKNOWN | 정확한 Jensen 항과 산술 active를 구분; 둘 모두 존재해 전부 복리라고 단정할 수 없음. 실제 beta는 추정하지 않음 |
| ETF 잔여 치환의 역할 | SUGGESTIVE / 기존 사실 | 원본 C1/C2는 같은 시작 종목 targets. 기존 #286의 C2−C1 gross/net/회전율 대비는 보존하지만 비용·drift·복리의 상호작용을 순수 ETF 기여로 오인하지 않음 |
| 교체 비용 | SUGGESTIVE / 기간 귀속 UNKNOWN | 원 일별 요약에 비용drag·회전율은 있으나 같은 주간 구간의 거래별 비용 경로 없음. 2×/3× 기존 조건부 상한은 이미 계산됐으며 다시 실행하지 않음 |
| 산업/개별 종목 집중 | UNKNOWN | truncated topContributions·평균 holdings 수는 기간 귀속 장부가 아님. P1의 decisions를 C2 보유로 바꾸지 않음 |
| 배당/가격 정의 | SUGGESTIVE / 기존 한계 | 교정 ETF는 고정. 주식 완전 주주수익·역사 신원·권리는 승인되지 않았으며 원 sourceBasis 차이를 계승함 |

## 재현·원본·제한

```sh
python research/portfolio_edge_forensics_v1/run.py --repo .
python research/portfolio_edge_forensics_v1/run.py --repo . --check
python -m pytest -q research/portfolio_edge_forensics_v1/test_forensics.py
```

필요 Git 객체가 없으면 source-pins.json의 정확한 commit을 정상 fetch한 후 재현한다. 스크립트는 fetch하지 않는다. 산출물은 이 디렉터리의 세 파일에만 기록한다. 원본/봉인 결과/원장/가격/배분/파라미터/종목 수는 바꾸지 않는다. 공개 결과의 숫자만 읽고 새 가격·기업행동 원천은 수집하지 않는다.

본 작업은 새 소유자 지시로 허용된 저장 결과의 사후 독해다. 기존 승인 잠금을 소비하거나 봉인 연구를 재실행하지 않았다. 주간 구간의 실제0과 미측정(null/미성숙)을 구분한다. 특정기간 제거는 source 부적격 종목을 빼거나 누락 NAV를 이어 붙이는 작업이 아니다.

#306은 다른 strategy/currency 및 benchmark basis다. US fixed C2는 KRW/FX 포함, #306 USD/QQQ와 종합 순위를 만들지 않는다. QQQ는 이번 fixed C2 입력에서 UNAVAILABLE. 동결 연구의 기존 신호 구분력/저변동성/교체 분석은 source-pins의 이전 보고서이며 이번 발견으로 재명명하지 않는다.

계산 원본(모든 SHA256은 source-pins.json 및 results.json에 있다):

- [docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json) · `901b3aee7d3bc06eed3fd2bd14b07a0d4ca4da23745b861a877203c48772b8d2`
- [docs/weekly-passive-first-v1.md](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/weekly-passive-first-v1.md) · `990b84c518080f4dc31aaf4885adcf80b9dba3b85095d0eb7f174cd561765118`
- [docs/weekly-decision/weekly-passive-first-v1-benchmark-basis-protocol.json](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/weekly-decision/weekly-passive-first-v1-benchmark-basis-protocol.json) · `a08f92b06aab6de4959b52d0a5bc0fd2c6b21851c53deca114167898e97a8fe6`
- [AGENTS.md](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/AGENTS.md) · `3211c5ebb2ebd591eb01b9486fe8baf475bec5f1ad67b8ea7bc384d7cc0ae7f2`
- [research/economic_path_readout_v1/results.json](https://github.com/jaehojung1879-netizen/Investment/blob/e46024ca92be16b5ded9c459797a7027c1d81d23/research/economic_path_readout_v1/results.json) · `1267f449b4c2be285f95fa12bfb5f3e093ff05b81c805ff7830bea39343a7431`
- [research/economic_path_readout_v1/results.windows.json.gz](https://github.com/jaehojung1879-netizen/Investment/blob/e46024ca92be16b5ded9c459797a7027c1d81d23/research/economic_path_readout_v1/results.windows.json.gz) · `ecc53673a0ce4fd741d487f7929bddacbee90784a96dd1b673df2acc6bb5b978`
- [research/economic_path_readout_v1/README.md](https://github.com/jaehojung1879-netizen/Investment/blob/e46024ca92be16b5ded9c459797a7027c1d81d23/research/economic_path_readout_v1/README.md) · `ba7c3182ea728850cd798f26fac6b64117051b6074a144ec637426cbd037570c`
- [research/economic_path_readout_v1/source-pins.json](https://github.com/jaehojung1879-netizen/Investment/blob/e46024ca92be16b5ded9c459797a7027c1d81d23/research/economic_path_readout_v1/source-pins.json) · `b4571cd50787e4c9b6ed248702ad9b04c1f7460c0dc2661d89e54c45decdf98e`
- [research/economic_path_readout_v1/readout-plan.json](https://github.com/jaehojung1879-netizen/Investment/blob/e46024ca92be16b5ded9c459797a7027c1d81d23/research/economic_path_readout_v1/readout-plan.json) · `0c8c723e1c46ce842c84407c5dcc117c7631404bfe1b67987a703f2ff2f76bc8`
- [docs/results/selection-value-report.json](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/results/selection-value-report.json) · `a61e992a3013ac068ee91f2c53f6ebde2c9769e4ca9b7cf73a4c0a6392c5302c`
- [docs/results/signal-persistence-report.json](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/results/signal-persistence-report.json) · `751ef12ff9ce8e813f6845660cfa50ae6820b50993a401121f31d0fe6cfda82d`
- [docs/results/alpha-calibration-resolution-report.json](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/results/alpha-calibration-resolution-report.json) · `9e69be1628d93318c9220c6dcca60dc70ee8dd06ac094173bc6c45e92c815cc2`
- [docs/results/four-factor-signal-attribution-audit-report.json](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/results/four-factor-signal-attribution-audit-report.json) · `d843950b5baee865cfc9bba7965ece9252a0212ef993e9e8ca8efea01cc4850d`
- [docs/kr-integrated-alpha-portfolio-v1-postoutcome-concentration-audit.md](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/kr-integrated-alpha-portfolio-v1-postoutcome-concentration-audit.md) · `951a73b663728fed778fddf214b26c36156d130308ae2f108ceaa8bc98b37f28`
- [research/c2_aggregate_evidence_v1/result-v2.json](https://github.com/jaehojung1879-netizen/Investment/blob/97aa2cfe2cabace05796f9179f2711cf83698d42/research/c2_aggregate_evidence_v1/result-v2.json) · `847aa910c9ea0bdcce3d930f80d4600942199e03f353afea8d2ef6bd26bbfee6`
- [research/entry_state_shadow_v1/readout_connection_v2/connection.json](https://github.com/jaehojung1879-netizen/Investment/blob/98028fe4c8e5ea0c4829d1b1c381dbf730eccf13/research/entry_state_shadow_v1/readout_connection_v2/connection.json) · `ef8c56406bc6baf8df342e6a4de8d430b0371fcb21e594661233c059c2058508`
- [research/entry_state_shadow_v1/readout_connection_v2/README.md](https://github.com/jaehojung1879-netizen/Investment/blob/98028fe4c8e5ea0c4829d1b1c381dbf730eccf13/research/entry_state_shadow_v1/readout_connection_v2/README.md) · `1b1ce8c2e6e07c1cf227d36da8841fe9764f88accc84457128655f576472f3ab`
