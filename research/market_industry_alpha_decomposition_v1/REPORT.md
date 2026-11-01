# Market & Industry Alpha Decomposition v1

## 네 질문의 답

1. **BLOCKED — 반도체 귀속.** KR C2의2025~2026 저장 관측 구간(2024-12-27~2026-09-14) 수익 차이는 -103.3423pp, 연환산 -39.0395pp다. 최근 31개 고유 목표 블록에서 삼성전자·SK하이닉스 직접 목표는0이지만, 공식ETF 구성·실현 보유·기여 장부가 없어 이 열세 중 반도체에 귀속할 수 있는 pp는 **UNKNOWN(null)**이다. 검증 불가를0pp 또는0%기여로 보고하지 않는다. ELECTRONICS_ELECTRICAL도 반도체만의 분류가 아니다.

2. **INCONCLUSIVE — 베타·복리.** 실제 주간 수익 714개에서 DESCRIPTIVE β=0.6300, HAC26 95%구간 [0.5097,0.7503], 상관 0.7591. raw 회귀 절편은 연 산술 +6.1246pp, 구간 [+1.4215,+10.8276]; 한 요인 회귀만으로 전체기간 우위가 사라지지는 않았지만 현금·누락 요인·비용·주주수익·사후 선택을 통제한 투자 알파는 아니다. #309의 Jensen 비중 37.44%는 기존 결과로 재사용하며 새 발견으로 주장하지 않는다.

3. **DESCRIPTIVE — 가장 큰 양의 H126 산업 연관 후보와 한계.** 기존 산업 중앙 OCF-yield IC +0.1364, HAC SE 0.0669, 유효날짜 337/유효지지 대용 13.37. 다중검정·독립 OOS를 통과한 투자 알파가 아니다. 통합D의 전자·전기 보유종목은 D−A gross 기여 차이의 71.11%를 설명하지만 이는 Brinson 업종배분 효과가 아니다. D 자체 gross의 98.25%가2025~26에 집중됐고, D는 다른 원천 기준의 passive를 전체기간 앞서지 못했다.

4. **BLOCKED — 가장 큰 단일 증거 공백.** 동일 날짜·주주수익·비용 기준의 `C2 실현 보유/종목별 P&L + KODEX200 공식 구성·업종별 가중/수익` 결합 패널이 없다. 이 한 결합 원천이 있어야 반도체 미보유의 기회비용, 업종배분, 업종 내 선택, 상호작용을 구분할 수 있다. 목표 비중31개나 PIT Top120 proxy는 이를 대신하지 못한다. 현금 수익도 미승인이므로 실제 beta-matched 비교를 실행하지 않았다.

## E1 — 기록된 목표와 실제 귀속의 경계

| 연도 | carry-in 포함 블록 | 커버 일수 | 직접 삼성/SK 목표% | ETF 잔여 목표% · 일수 가중 |
|---|---:|---:|---:|---:|
|2024|12|366|0.0000|38.0200|
|2025|13|365|0.0000|36.5764|
|2026|8|256|0.0000|38.2343|

C2 Study ID: `weekly-passive-first-v1-replay-corrected-benchmark`. 저장 CHAMPION+잔여ETF 경로이며 정식 Market-risk C1/C2와 다른 연구다.

이는 원래155개 원장의 재조정 목표다. 새 목표/상한을 만들지 않았으며 실제 시가 비중 평균이나 체결 확정이 아니다. carry-in을 포함하고 연도별 겹치는 블록을 독립 관측으로 더하지 않았다. 내부 sectorByTicker는 Unclassified를 보존한 원 기록 라벨이지 PIT 인증 업종이 아니다.

If named direct target=0, modeled pair target exposure=wETF*wETF_pair and active pair weight=(wETF-1)*wETF_pair. wETF_pair unknown; no number or causal return inferred. Other semiconductor names are not excluded by this identity.

Brinson allocation / selection / interaction / cost: 모두 **UNAVAILABLE**. 공식 ETF 구성·sector return·동일 시점 실행 보유/비용이 없으므로 정합 검사를 통과한 실제 Brinson 수치는 없다. 대신 E3의 완전한 저장 산업 기여 합을 총 gross−cost=net과 대조했다. 그 부분 진단을 Brinson으로 부르지 않는다.

## E2 — 사후 시장 민감도와 포착률

회귀식 Rc=a+βRe는 **같은 주의 raw 저장 net수익**에 대한 사후 통계다. C2 목표의 잔여는 현금이 아니라 ETF로, 명목상 개별주+ETF 합계100%다. β0.63을 주식 보유비중63%나 현금37%로 해석하지 않는다. cash excess-return CAPM이 아니고 현금0을 채택하지 않는다. 절편을 기하 CAGR로 지수변환하지 않는다. CI는 Bartlett Newey–West, 고정26관측주 지연/52관측주 민감도, n/(n−2) 보정, pointwise t 근사다. H126/H252 거래 세션과 동일하다고 부르지 않는다. 다수 구간의 CI는 동시구간·사후 선택 보정이 아니다.

| 구간 | n | β [HAC26 CI] | raw 절편 연산술pp [CI] | 상관 | TE 연환산% |
|---|---:|---|---|---:|---:|
|FULL|714|0.6300 [0.5097,0.7503]|+6.1246 [+1.4215,+10.8276]|0.7591|12.9876|
|OBSERVED_2017_2024|417|0.7391 [0.6676,0.8106]|+4.9532 [-1.0877,+10.9941]|0.7739|11.7591|
|OBSERVED_2025_2026|90|0.4761 [0.3442,0.6081]|+15.5124 [-3.6627,+34.6874]|0.7489|23.4936|
|2024|52|0.8521 [0.4420,1.2622]|+12.8959 [-17.2789,+43.0708]|0.6265|19.3095|
|2025|52|0.6258 [0.4065,0.8450]|+18.4694 [+0.5588,+36.3800]|0.7093|14.2010|
|2026|38|0.4469 [0.2920,0.6018]|+0.5109 [-16.3445,+17.3662]|0.7885|32.1589|

| 同一期 사후 회귀 mean bridge | 산술 active pp/년 | (β−1) ETF항 pp/년 | raw 절편 pp/년 | Jensen log-points/년 | 평균 잔차 pp/년 |
|---|---:|---:|---:|---:|---:|
|FULL|+1.0020|-5.1225|+6.1246|+0.5996|-5.33e-15|
|OBSERVED_2017_2024|+3.3358|-1.6174|+4.9532|+0.1491|8.88e-16|
|OBSERVED_2025_2026|-25.0704|-40.5827|+15.5124|+3.7653|-2.66e-14|
|2024|+14.0789|+1.1830|+12.8959|-1.2395|-1.78e-15|
|2025|-6.0817|-24.5511|+18.4694|+0.4870|3.55e-15|
|2026|-51.4516|-51.9624|+0.5109|+8.3199|-7.44e-15|

mean(Rc−Re)=a+(β−1)mean(Re)+mean(error). 절편이 있는 OLS는 평균 잔차를0으로 강제하므로 이 정합은 인과 설명의 완결이나 선택 알파 식별이 아니다. ETF항은 같은 표본에서 맞춘 노출 연관이며 반도체 기여로 재명명하지 않는다. 산술 pp, 연 로그 차이, 기하 CAGR은 서로 다른 단위다.


104개 관측 수익/13개 간격 rolling β: 0.4836~0.8283. 창은 서로 중첩되며 독립 시행이 아니다. 각 시점 CI·지원 분모·HAC52 결과는 results.json에 있다. full-sample β를 과거에 알았던 거래 비중으로 사용하지 않는다. 연간 구간 n=38~52에서 지연26의 비중이 크므로 유한표본95%포함률을 인증하지 않는 근사다. 부족한 HAC52 지원은 지연을 줄이지 않고 BLOCKED로 보존한다.

| 종료 관측 연도 | up n / capture% | down n / capture% | up/down 연 산술 기여pp |
|---|---|---|---|
|2013|26 / 74.10|24 / 47.07|-11.7941 / +23.1126|
|2014|27 / 71.75|25 / 30.12|-8.4415 / +23.9990|
|2015|27 / 83.55|26 / 62.06|-6.0991 / +14.3222|
|2016|28 / 80.17|23 / 91.85|-7.1471 / +2.0935|
|2017|31 / 67.89|19 / 38.12|-13.5427 / +10.8280|
|2018|25 / 84.66|27 / 52.97|-5.0593 / +23.9462|
|2019|32 / 60.02|20 / 73.68|-20.0548 / +9.3019|
|2020|33 / 75.93|20 / 75.25|-23.9384 / +16.1392|
|2021|30 / 93.08|22 / 72.26|-2.9787 / +10.7512|
|2022|19 / 68.30|33 / 55.57|-10.5129 / +26.4385|
|2023|29 / 68.78|23 / 77.07|-17.3234 / +7.3637|
|2024|26 / 110.74|26 / 83.76|+5.0874 / +8.9915|
|2025|38 / 82.82|14 / 66.43|-16.7072 / +10.6255|
|2026|21 / 45.36|17 / 45.47|-109.4276 / +57.9760|

Capture=같은 조건(ETF 주간 수익>0 또는<0)의 후보 평균/ETF 평균×100. 사후 up/down이며 예측 가능한 상태가 아니다. 연도 경계를 넘는 주는 종료 관측 연도로 배정하고 실제 구간을 JSON에 보존했다. 관측 주간 TE/상대 drawdown은 일별 수치가 아니다.

기존 #309 상대 drawdown: {"longestUnderwaterEpisode": {"calendarDays": 1260, "endDate": "2022-06-17", "peakDate": "2019-01-04", "recovered": true}, "mddPct": -49.857324490419195, "peakDate": "2025-07-04", "peakToLastObservationDays": 437, "peakToRecoveryDays": null, "recoveryDate": null, "status": "UNRECOVERED_THROUGH_LAST_OBSERVATION", "troughDate": "2026-06-26"}

실제 funded fixed-exposure 비교: **BLOCKED**. 보존 현금 자료가 아예 없는 것은 아니다. #300이 사용한 BOK 기준금리와 원장 dailyRiskFreeNav는 정책금리/모델 경로이며, 실제 투자 가능한 KRW 현금 계정의 순수익 승인이 아니다. cash·과거에 정한 실행 beta·비용 입력이 승인되지 않았다. 가격/현금 보간, fitted comparator NAV, 레버리지 clipping, 원천 교정 및 새 전략을 만들지 않았다.

## E3 — 산업 효과와 개발 성과를 분리

| 기존 H126 CAP IC | mean | HAC SE | 유효날짜 / 지지 대용 | PRE_2025 완료창 | 2025 이후 닿는창 |
|---|---:|---:|---:|---|---|
|REL_MOM_126|+0.0662|0.0561|404 / 16.03|+0.0619 (389)|+0.1778 (15)|
|MEDIAN_ocfYieldProxy|+0.1364|0.0669|337 / 13.37|+0.1969 (278)|-0.1485 (59)|
|BREADTH_ABOVE_MA_126|+0.0587|0.0497|405 / 16.07|+0.0450 (389)|+0.3913 (16)|
|TOP1_CAP_SHARE|-0.0538|0.0532|565 / 22.42|-0.0165 (486)|-0.2832 (79)|

이 표는 기존 결과를 읽었고 새 산업 IC/회귀/검정을 돌리지 않았다. PRE_2025는2015~24까지 포함할 수 있어2017~24로 재명명하지 않는다. 별도의2017~24/2025~26 signal-year 날짜 가중 평균과 빠진 연도를 JSON에 명시했다. momentum·breadth의 최근 창은15~16개뿐이며2026 지원이 없다. 최근 OCF와 momentum의 요약 방향은 엇갈리지만 유효날짜가 달라 동일 표본에서의 신호 불일치로 단정할 수 없다. concentration과 momentum도 서로 다른 변수다.

기업 OCF-yield의 같은 표본472날짜에서, 산업−시장 연관은+0.0721(SE0.0247), 기업−산업은−0.0023(SE0.0233), 기업−시장은+0.0425(SE0.0250)였다. 이는 다른 산업 중앙값337날짜 통계와 다르며, Rank IC는 가법적이지 않아 세 값을 더해 기여도로 만들지 않는다.

| 통합D−A 저장 기여 bridge | Δgross NAV단위 | 전자·전기 Δgross | 비중% | Δcost | Δnet | 정합 잔차 |
|---|---:|---:|---:|---:|---:|---:|
|A_2017_to_2024|+0.055176|-0.039936|-72.38|+0.102877|-0.047701|3.00e-12|
|B_2025|+0.664131|+0.316987|47.73|+0.023649|+0.640481|4.00e-12|
|C_2026_to_cutoff|+1.623856|+1.389126|85.54|+0.078900|+1.544956|-2.00e-12|
|D_full_window|+2.343163|+1.666177|71.11|+0.205427|+2.137736|1.00e-12|

이는 같은 원금 NAV 단위의 보유종목 산업별 총기여다. Δgross−Δcost=Δnet을 정합 확인했으나 업종배분/선택/상호작용의 인과 분해는 아니다. 기간별 NAV단위 기여는 복리로 커진 후반 자본의 영향을 받으므로 기간 자체 수익률과 구분한다. 단순 sector label을 반도체 테마로 재분류하지 않았다.

| 통합D 고정 원 구간 | D 수익% | A 수익% | 저장 passive 수익% | D 최상위업종 평균 비중% |
|---|---:|---:|---:|---:|
|A_2017_to_2024|-17.34|-12.57|69.90|59.99|
|B_2025|132.28|51.81|98.72|68.14|
|C_2026_to_cutoff|101.04|29.77|75.73|83.51|
|D_full_window|286.02|72.25|493.29|62.60|

통합D 전자·전기 gross 비중59.51%, 상위5종목87.08%, 삼성+SK 직접 gross9.16%(삼성+0.531238, SK−0.235633 NAV단위)는 기존 발견이다. 두 종목을 빼도 좋아졌던 원 등록 민감도를 재실행하지 않았다. D는 두 종목보다 넓은 전자·전기 업종의 특정 시기에 집중됐다.

통합D는2017-01-16 시작/구형 미해결 ETF 구성이고, 이번 C2는2013-01-11 저장 시작/교정 ETF다. 통합D passive20.24% vs D15.01%와 C2의14.43%를 직접 순위 비교하지 않는다. Phase D는73평가·574fit 중 다중검정 통과0, prospective 지명0, Level4 NOT_TRIGGERED였다. 누락·생존편향·요인 중복이 이 실패의 입증된 원인이라고 단정하지 않는다.

기존 alpha-reliability/risk-dominance는 점수 분모인 downside risk와 무차별 캘리브레이션의 영향, 교체불안정을 기록했다. 해당 다른 selector/표본의 결과를 C2 주간 경로에 대한 인과 판정으로 옮기지 않았다. OCF의 conditional study는 #300 원 power gate NO_GO로 남아 있으며 재실행하지 않았다.

#300의 기존 **합성** power gate: 의미있는 rho에서 검출률 22.95%, 등록 floor 80%, size gate도 미충족. 이는 실제 OCF 성과나 이번 회귀의 검정력이 아니다. 독립 표본에서 Market+Stock 대비 Industry의 추가 순경제성은 여전히 미검증이다.

## 문헌의 적용과 한계

- **Moskowitz & Grinblatt (1999)** — Do Industries Explain Momentum?. 읽은 범위: 저널 초록의 RePEc 게재본. 출판사 전문 접근403; 전문 열람 주장 안 함.. 산업 모멘텀 통제의 필요성을 제시하나 이 KR 발전표본의 재현·순수익을 보장하지 않는다. 업종 수익과 업종 내 종목 선택을 구분한다. 원문/초록: https://ideas.repec.org/a/bla/jfinan/v54y1999i4p1249-1290.html · DOI 10.1111/0022-1082.00146 · 조회 바이트 SHA256 `5f80036e8dc6621fc407b087a1c70e9f2adb97d8eace59ba9a13d2f79e935370`
- **Daniel & Moskowitz (2016)** — Momentum Crashes. 읽은 범위: NBER WP20439 (2014 working version): 초록·결론 및 panic/rebound 논의. 2016 저널과 버전 구분.. 시장 하락 뒤 고변동·급반등에서 모멘텀 crash가 가능하다. 하지만 C2=순수 모멘텀이라고 추정하거나 사후 반등을 신호로 쓰지 않는다. 원문/초록: https://www.nber.org/system/files/working_papers/w20439/w20439.pdf · DOI 10.1016/j.jfineco.2015.12.002 · 조회 바이트 SHA256 `bdbb346566311d9e08a5dbddc0f94c9d9567f1fc7cd5f0fba6e232ca26fea7b0`
- **Fama & French (2015)** — A five-factor asset pricing model. 읽은 범위: 저널 초록의 RePEc 게재본. 원문 출판사 경로403; 전문 열람 주장 안 함.. 시장 외 size/value/profitability/investment 노출이 절편에 남을 수 있다. 수익성/OCF IC나 한 요인 raw 절편을 독립 alpha로 인증하지 않는다. 원문/초록: https://ideas.repec.org/a/eee/jfinec/v116y2015i1p1-22.html · DOI 10.1016/j.jfineco.2014.10.010 · 조회 바이트 SHA256 `4364640b70c8768911779149b10d917f41b8e919131803825403ec180aad6530`
- **Moreira & Muir (2017)** — Volatility-Managed Portfolios. 읽은 범위: NBER WP22208 (2016 revised working version): 초록·도입·결론; 저널 초록도 대조.. 고변동 시 노출을 낮춘 경로의 Sharpe/회귀 절편 향상 가능성이 연구 동기다. 위험 감소·선택·복리 차이를 분리하고 현재 backtest를 검증됐다고 하지 않는다. 원문/초록: https://www.nber.org/system/files/working_papers/w22208/w22208.pdf · DOI 10.1111/jofi.12513 · 조회 바이트 SHA256 `be1ea92102e1394e9ddec9545489902f45e5a07b42bd4c42faf8ee372e99fa7a`
- **Cederburg et al. (2020)** — On the performance of volatility-managed portfolios. 읽은 범위: 저널 초록의 RePEc 게재본. 출판사 전문 경로403; 전문 열람 주장 안 함.. 103개 전략의 positive spanning alpha가 실시간 구현 가능한 OOS 우위로 이어지지 않을 수 있고 구조 불안정성이 중요하다. full-sample beta 통제는 사후 통계로만 사용한다. 원문/초록: https://ideas.repec.org/a/eee/jfinec/v138y2020i1p95-117.html · DOI 10.1016/j.jfineco.2020.04.015 · 조회 바이트 SHA256 `156e1c4ba8d83b9dc77aca984db42a5f619541f3b3365cdc6cbfa643b946c6af`
- **Bailey et al. (2017)** — The probability of backtest overfitting. 읽은 범위: 저자 공개2015 working version PDF 초록·PBO 정의·CSCV/결론; 2017 출판 metadata 대조.. 많은 전략을 본 뒤 선택한 성과는 holdout만으로 해결되지 않을 수 있다. 새 arm/grid/최적화 없이 고정 분석을 하고, 필요한 trial matrix 없이 이 프로젝트의 PBO 숫자를 발명하지 않는다. 원문/초록: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf · DOI 10.21314/JCF.2016.322 · 조회 바이트 SHA256 `d8bfbadaaedb430d9dec929646d92f3580fdf18238f34121ae7738fa1c69a63d`
- **Hou, Xue & Zhang (2020)** — Replicating Anomalies. 읽은 범위: 출판사 제공 저널 초록(Crossref metadata). 전문 미열람.. 452개 anomaly에서 microcap·value weighting·다중검정에 따른 재현 실패를 문헌 근거로만 사용한다. 미국 논문의 수치 임계값을 KR 연구의 새 승인 기준으로 채택하지 않는다. 원문/초록: https://doi.org/10.1093/rfs/hhy131 · DOI 10.1093/rfs/hhy131 · 조회 바이트 SHA256 `1b0f9aa19e83e8a92f53a3bbd5041084c5179ef5fdae31c63fe59705e654cbd2`

문헌은 통제·반례의 동기이며 이 개발 backtest의 검증이 아니다. 새 산업/요인/규칙 grid나 factor 재학습은 하지 않았다. 논문 전문 미확보 항목은 초록을 읽었다고 명시했고 전문을 읽었다고 주장하지 않는다. 논문 PDF/출판사 payload는 공개 저장소에 재배포하지 않았다.

## 재현과 경계

```sh
python research/market_industry_alpha_decomposition_v1/analyze.py --repo .
python research/market_industry_alpha_decomposition_v1/analyze.py --repo . --check
python -m pytest -q research/market_industry_alpha_decomposition_v1/test_analysis.py
```

numpy/scipy는 기존 requirements를 사용한다. 필요한 고정 Git 객체가 없으면 source-manifest.json의 exact SHA를 정상 fetch한다. CLI는 네트워크나 fetch를 수행하지 않는다. #309의 해시 검증된 순수함수만 재사용하며 그 연구 CLI/build/전략을 호출하지 않는다. 원본·워크플로·원장·보호 해시·생산 배분은 수정하지 않았다. 종목 수의 새로운3/5 상한이나 선택목표는 없다. 승인된 알파·독립 OOS·승격은 없다.

단일 다음 증거: 위의 시점별 C2/공식ETF 결합 패널. 이번 bounded 분석은 여기서 끝내며, 새 전략/연구 실행을 승인하지 않는다.

고정 원본:

- [AGENTS.md](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/AGENTS.md) · `3211c5ebb2ebd591eb01b9486fe8baf475bec5f1ad67b8ea7bc384d7cc0ae7f2`
- [docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json) · `901b3aee7d3bc06eed3fd2bd14b07a0d4ca4da23745b861a877203c48772b8d2`
- [docs/weekly-passive-first-v1.md](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/weekly-passive-first-v1.md) · `990b84c518080f4dc31aaf4885adcf80b9dba3b85095d0eb7f174cd561765118`
- [scripts/run_weekly_passive_first_replay.py](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/scripts/run_weekly_passive_first_replay.py) · `58bc5ca3f2e313baeb3b8ddbf31534f4fb0909efd69fb7460711ce0a51969592`
- [docs/results/regional-standalone-paths.json.gz](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/results/regional-standalone-paths.json.gz) · `7a09751f99f5d892821cac6bbb4f28359049d58364cb40db1814fac4f93210cb`
- [docs/kr-integrated-alpha-portfolio-v1-postoutcome-concentration-audit.md](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/kr-integrated-alpha-portfolio-v1-postoutcome-concentration-audit.md) · `951a73b663728fed778fddf214b26c36156d130308ae2f108ceaa8bc98b37f28`
- [docs/results/kr-integrated-alpha-portfolio-v1-postoutcome-completed-audit.json](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/results/kr-integrated-alpha-portfolio-v1-postoutcome-completed-audit.json) · `4349b4400946559190eec104bd4986a5a799c73925146937d92d471c37c7f5e4`
- [docs/results/kr-industry-opportunity-anatomy-v1-report.md](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/results/kr-industry-opportunity-anatomy-v1-report.md) · `d3cd184e14816e63cd008450f9cfa51709f14dbc865fea0f575b7fea775bc3f6`
- [docs/results/kr-industry-opportunity-anatomy-v1-result.json](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/results/kr-industry-opportunity-anatomy-v1-result.json) · `71a960e3c19ce443d058508c4ec66576e3e5fcbd7a45dc851cf8b832bff62a08`
- [docs/results/kr-stock-within-industry-anatomy-v1-report.md](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/results/kr-stock-within-industry-anatomy-v1-report.md) · `cd4c7ffda6ff229538b327dd666ce802eafd121caa30323fd0089ff555392384`
- [docs/results/kr-stock-within-industry-anatomy-v1-result.json](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/results/kr-stock-within-industry-anatomy-v1-result.json) · `3862c390a52f6f19abaa7849e41620858cd154735136647ee36c958624c2739f`
- [docs/kr-alpha-research-final-development-assessment.md](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/kr-alpha-research-final-development-assessment.md) · `9c77f6e1ef18386f61a7d91b286c53e600a9beca57de83a9f75d33039a722714`
- [docs/results/alpha-reliability-report.json](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/results/alpha-reliability-report.json) · `15284a0dade2ea9483c1a00a509d55ae8143b5e0c82f4d30724099d0e6b535bf`
- [docs/results/selection-value-report.json](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/results/selection-value-report.json) · `a61e992a3013ac068ee91f2c53f6ebde2c9769e4ca9b7cf73a4c0a6392c5302c`
- [research/portfolio_edge_forensics_v1/run.py](https://github.com/jaehojung1879-netizen/Investment/blob/84fe989f92d348e88243090bcad5d7a1fe891a02/research/portfolio_edge_forensics_v1/run.py) · `2b9419d92c8f0a26e387063e275afab69f1a71c0cbd3adecdb8452dca4fc04ef`
- [research/portfolio_edge_forensics_v1/results.json](https://github.com/jaehojung1879-netizen/Investment/blob/84fe989f92d348e88243090bcad5d7a1fe891a02/research/portfolio_edge_forensics_v1/results.json) · `d0cf9594bc5c179adadf5d642b796cc8c7ea5f8b4d0beccbc417c29b62c35b4a`
- [research/economic_path_readout_v1/results.json](https://github.com/jaehojung1879-netizen/Investment/blob/e46024ca92be16b5ded9c459797a7027c1d81d23/research/economic_path_readout_v1/results.json) · `1267f449b4c2be285f95fa12bfb5f3e093ff05b81c805ff7830bea39343a7431`
- [research/economic_path_readout_v1/source-pins.json](https://github.com/jaehojung1879-netizen/Investment/blob/e46024ca92be16b5ded9c459797a7027c1d81d23/research/economic_path_readout_v1/source-pins.json) · `b4571cd50787e4c9b6ed248702ad9b04c1f7460c0dc2661d89e54c45decdf98e`
- [research/c2_aggregate_evidence_v1/result-v2.json](https://github.com/jaehojung1879-netizen/Investment/blob/97aa2cfe2cabace05796f9179f2711cf83698d42/research/c2_aggregate_evidence_v1/result-v2.json) · `847aa910c9ea0bdcce3d930f80d4600942199e03f353afea8d2ef6bd26bbfee6`
- [research/industry_ocfyield_conditional_v1/power-gate-result.json](https://github.com/jaehojung1879-netizen/Investment/blob/e580cde917673a0bd2d6a1ca21b010916721fa22/research/industry_ocfyield_conditional_v1/power-gate-result.json) · `2d7f498020dd6f39f03543df80a2f8863f3a5fc14f60c424a5f23aaaa9ce3e64`
- [research/industry_ocfyield_conditional_v1/protocol.json](https://github.com/jaehojung1879-netizen/Investment/blob/e580cde917673a0bd2d6a1ca21b010916721fa22/research/industry_ocfyield_conditional_v1/protocol.json) · `e20414abaf90502c5aa627d1168896f769a4294f6fe54c23d67f242dba9d6973`
- [research/independent_audit_c2_marketc_v1/c2-beta-audit.json](https://github.com/jaehojung1879-netizen/Investment/blob/e580cde917673a0bd2d6a1ca21b010916721fa22/research/independent_audit_c2_marketc_v1/c2-beta-audit.json) · `5037cd9075698c04940cd280f93a396f7fec931aedcc1dd039ee38d46ea53f18`
