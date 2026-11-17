# 한국·미국 전략 일괄 비교 — 새 전략 성과 계산 전 고정 설계

작성: 2026-11-18 KST. 기준 한국 #349 `d9ac3ed53e522e51d93b496bf4c26b63b61e3207`, 미국·기존 비교 #348 `3a3e9d8e`. 상태 `DEVELOPMENT_ON_REPEATEDLY_EXPOSED_HISTORY`.

기존 과거 성과는 이미 읽었다. 이번에도 결과를 보며 후보·시총 범위·ETF 비중·선택 규칙을 바꾸지 않는다. 이 문서와 registry를 먼저 커밋한 뒤 새 전략 성과를 계산한다. 입력 복구와 신호 가용성 조사는 성과 계산과 분리한다. 두 시장은 독립 준비·계산·출력을 사용하고 한쪽 미확보가 다른 쪽을 멈추지 않는다. 최종 전달은 하나의 PR이다.

## 1. 입력과 재현 기준

- 한국: 기존 `/workspace/s2-inputs`의 matrix/dataset/macro/vix_fx/sg1 cache, signal-history `4ea107ed`, 기존 final-session/OCI 정정과 비용·KODEX 200 총수익을 그대로 쓴다. 2018-01-05~2026-09-11의 454개 기존 판단일을 유지한다. 가용 source identity와 S2 수치를 대조한다.
- 미국: 원 TR·재무는 `704d7db6d5b00def771aba5d2665d0846d6bc776` / replay manifest `f0781292…`에서 복구한다. 원 Yahoo 캐시·features가 없으므로 원 생성기를 현재 응답으로 재실행하되 **새 capture/vintage**로 기록하고 원 종목별 status/유니버스·기준 수치와 대조한다. 봉인 TR+분배·분할의 원종가 역산은 독립 복구 검사이며 admission을 결과에 맞게 바꾸지 않는다. 원 source의 미확보/불일치는 별도 상태·숫자로 공개하고 동일 빈티지·완전 PIT라고 부르지 않는다. 기존 654개 주간 판단일(2014-02-14~2026-08-21)의 재현 여부를 확인한다.
- 미국 공시 C2 원 신호(`nport/round8/C2.pkl`)가 없으면 OW/OW_RESID 새 계산은 미확보로 남긴다. 기존 집계는 출처/표본을 붙여 reference로 인용한다. 가격·비용·종목 수가 다른 집계를 새 비교로 대체하지 않는다. 추가 구매하지 않는다.
- 각 시장은 후보 프레임·신호·일별 가격·자산별 126/252 순수익·거래비용을 한 번 준비해 모든 후보에 공유한다. 입력·가격 상태·실패 사유·코드·캐시 hashes를 보존한다.

## 2. 닫힌 후보 목록

### 한국 7개

1. `S2`: 원 confirmed B08 가치 순위, 원 적격·WITHHELD·ticker tie 그대로.
2. `VALUE_ORIGINAL`: 이미 구현된 확인 필터 없는 B08 TOP5. 확인 미측정도 포함될 수 있음을 표시.
3. `VALUE_COMPLETE`: 품질·B08·사업확인 원시 세 필드(C01/C05/C14)가 모두 측정된 공통 pool의 B08 순위.
4. `QUALITY_NEUTRAL`: 위 완전관측 pool에서 날짜별 고정 SHA256 순서.
5. `CONFIRM_NEUTRAL`: 같은 pool·같은 hash 순서에서 사업 세 조건이 양수인 이름만 남김. B08 점수 크기로 정렬하지 않음.
6. `INDUSTRY_MOMENTUM`: 원 S1.
7. `FOUR_FACTOR`: 원 S3.

S2가 완전관측+사업양수 pool에서 원 순위를 그대로 유지하는지 검산한다. SHA256 키는 `20261118|시장|YYYY-MM-DD|ticker`, 오름차순, 동점 ticker다. 이 두 neutral은 순위가 없던 기존 confirmation EW 집합을 1~5개로 만드는 **새 구성**이지 원부터 있던 독립 점수가 아니다. 무작위 null 통과 주장은 하지 않는다. 기존 confirmation-only EW는 5종목을 넘을 수 있어 정의·이전 결과만 legacy로 남기며 0~5 운용 후보로 가장하지 않는다.

`VALUE_COMPLETE → S2`는 가치 정렬에서 사업 확인 필터, `CONFIRM_NEUTRAL → S2`는 확인 pool에서 가치 정렬, `QUALITY_NEUTRAL → CONFIRM_NEUTRAL`은 가치 없는 순서에서 확인 필터다. 사업 미측정은 음수/실패와 구분한다. 원 VALUE와 complete VALUE 차이도 공개한다.

### 미국 12개 슬롯

`PRICE`, `PRICE_CONFIRMED`, `QUALITY_NEUTRAL`, `CONFIRM_NEUTRAL`, `VALUE`, `VALUE_CONFIRMED`, `CASH_PROFITABILITY`, `SECTOR_MOMENTUM`, `COCKTAIL`, `U1`, `OW`, `OW_RESID`.

기존 `EV.common/score/book`의 당시 S&P 구성·CIK·필수 회계/가격·최소30개·금융/부동산 제외를 그대로 호출한다. 단일 TOP5는 기존 업종당 최대2개·ticker tie를 유지한다. neutral 둘은 같은 complete common pool의 고정 hash 순서에 같은 업종 cap을 적용하고 confirmed Boolean만 다르게 한다. VALUE/현금수익성/산업모멘텀/고정25% 칵테일/U1의 원 정의를 호출한다. U1은 top5-only가 아니라 cap top5+기존 칵테일이며, 원 ETF residual도 별도 기록한다. 공시 둘은 C2 입력 있을 때만 기존 정정 경로로 호출한다. 미확보 슬롯을 결과를 본 뒤 다른 후보로 대체하지 않는다.

## 3. 구성 grid와 비교 기준

- 한국: 각 7신호, k=1..5에 `SLOT20`(이름당20%, 나머지ETF)와 `FIXED20`(총주식20%를 실제 m=min(k,적격수)개에 .2/m, 나머지80%ETF). m=0이면ETF100%. k=0은 공통 `KR:ETF` 한 개. 실제 수와 부족 주차를 저장한다. 고정보유에서 FIXED20 초과가 SLOT20 초과/m인지 검산한다. 운용 NAV를 단순 축소하지 않는다.
- 미국: stock sleeve의 기존 상대 비중을 보존하고 SPY/현금 부분을 제거해 주식 합1로 정규화한다. 총주식 q∈{.2,.5,1}, SPY 잔여. 주식이 없으면SPY100%, 부족 count는 공개한다. 주 기준 SPY TR, 보조 QQQ TR(기존 누락 분배 한 번 정정). 원 `NATIVE_COCKTAIL`, `NATIVE_U1`도 별도 기준으로 보존하여 normalization 효과를 숨기지 않는다. q=.2/.5/1을 보고 바꾸지 않는다.
- 한국 reference: 원 `K2`, `MIX_PRE`, `MIX_EXP`를 호출/재사용한다. 원 K2의 2018+ prior-date 제한·게이트 첫 정의일을 바꾸지 않는다. #348 FULL 및 gate-defined 집계와 장부를 검산하고 새 공통 표본만 재집계한다. 4주 cadence·OCI 정정 전 옛 ablation을 새 6/12 표에 섞지 않는다.
- 날짜·체결: 각 시장 원 판단일, 다음 세션 종가 진입, 126/252세션 고정보유. 한국 원 dated C.cost_rate, 미국 원 EV.net(8.0/8.3bp)·UP.simulate. 가격 미해결 때문에 보유 종목을 바꾸거나 ETF/0으로 채우지 않는다.

## 4. 같은 업종·시총 대조군

주 비교는 위 후보의 `FIXED20 k5`(한국) / q=.2(미국)다. 같은 판단일·실제 이름 수·각 이름 비중·ETF 비중을 유지한다. 한국 peer pool은 원 품질 적격 Top120(WITHHELD 제외), 미국은 원 common pool이다.

같은 업종과 `peer cap / held cap∈[.5,2]`를 먼저 요구한다. 현재 보유 이름 전부·이미 쓴 peer 제외 후 절대 log-cap 차이 최소, tie ticker로 greedy 선택한다. 한국은 신호 순위 순서, 미국은 (-target weight,ticker) 순서다. 이전 #349의 caliper 없는 percentile matcher를 동일하다고 부르지 않는다. 미매칭이면 책 전체 peer 비교는 미측정이며 자기 자신·ETF로 대신하지 않는다. 불가 사유/부분 leg/가중 coverage·전체 매칭률·시총 거리 모두 보존한다.

신호별 유효 paired 표본과 모든 준비된 신호의 공통 matched 표본을 둘 다 낸다. 후자가 2블록 미만이면 공통 통계는 None이다. 서로 다른 날짜의 신호별 평균만으로 순위를 정하지 않는다. 실제 이름 0개인 책은 선택력 증거가 아니며 선택 비교에서 제외한다. 순위/필터 기여 핵심 차이는 양쪽 5이름인 공통 날짜에서 계산한다.

## 5. 통계와 사전 고정 핵심 주장

- 모든 원 주간 시간축을 유지하고 마스크를 적용한 paired 이동 블록: 4,000회, seed20261118, 블록25/50주. 미측정/미만기는 구분하고 2블록 미만 구간은None. p는 기존 방식의 bootstrap tail 근사임을 표시한다.
- portfolio 기준 주 표는 각 시장 모든 준비된 grid가 가격 해결된 공통 날짜, own 표본도 병기. matching 공통 마스크를 portfolio 성과에 몰래 적용하지 않는다. CAGR은 일수익 차이 연율과 복리 잔여를 함께 보고한다.
- **core family 41개 고정, 한 번의 Holm:** (A) 신호별 선택력19개(KR7+US12), (B) ETF 대비8개(KR S2 SLOT5/FIXED5, US PRICE_CONFIRMED/COCKTAIL/U1 각q.2/q1), (C) 신호 기여5개(KR 위 factorial3, US confirmed−price와confirmed-neutral−neutral), (D) 구성 차이5개(KR FIXED5−SLOT5와FIXED5−FIXED1, US 위3신호q.2−q1), (E) 연간 walk-forward 정책4개.
- **broad grid ETF family 115개 고정, 별도 Holm:** KR70, US36, KR reference3, US native2, 정책4. 동일한 별칭 결과도 사후 가족 수를 줄이는 데 쓰지 않는다. 미확보 US/공시/측정 불가 주장은 p=1 슬롯을 유지한다. 모든 실행 후보의 원 평균·구간·p·Holm을 남긴다. 보조12개월·분할·사후 민감도를 새 주 주장으로 바꾸지 않는다.
- 탐색적 과거수익 근거: 6개월 positive+core Holm<.05, 12개월 평균positive, 고정 시기 양쪽 평균positive를 구분해서 표시. ETF 대비 운용 CAGR 양수·MDD 비열등/엄격 개선도 별도로 판정한다. "수익과 위험 개선"에는 L26/L52 모두 CAGRgap>0 및 MDD가ETF보다 얕음을 요구한다. 같은MDD는 risk-not-worse이지 위험 개선이 아니다. 입력 무결성/조건부 shareholder basis 한계가 남으면 실운용 승격으로 부르지 않는다.

## 6. 판단일에 적용하는 규칙

각 시장 두 정책: 한국 `WF_S2_LCB`(S2의10구성만), `WF_ALL_LCB`(7신호70grid); 미국 `WF_PC_LCB`(PRICE_CONFIRMED q3), `WF_ALL_LCB`(준비된12신호grid). 앵커·native reference는 선택 후보에 넣지 않는다.

매년 첫 판단일에만 다시 고르고 연중 구성 ID를 고정한다(종목 신호는 각 판단일 새로 계산). 학습에는 **exit < 해당 fit 판단일**인 6개월 코호트만 넣는다. 최소104개 공통 만기 주, 그 전ETF다. 각 후보의 같은 학습 날짜 순초과 95% 블록 하한과 **비용 차감 고정보유 창 최대낙폭 평균**을 계산한다. 후보의 과거 평균 코호트MDD가 ETF보다 깊지 않고 하한>0인 후보 중 하한 최대, tie는 주식 비중이 낮고 이름 수가 적은 구성·ID 순으로 고른다. 없으면ETF. 미래의 미만기 NAV·12개월 미래값·사후 주도기·후보 최대 기여 종목/년은 입력하지 않는다. cutoff·전 후보 점수·위험 가드·선택·마지막 학습 exit·warmup을 날짜별로 저장한다.

코호트 MDD는 기존 고정보유 순수익과 동일한 entry/exit 비용의 daily wealth에서 측정한다. 중간 정지는 기존 carry mark, 미해결 종료는 미측정이다. 이는 완전히 만기 된 창만의 통계이며, 겹친 운용장부 MDD와 다르다. 미래 운용 낙폭 보장이 아니다.

정책 평가는 첫 충분한 연간 fit 이후의 공통 만기 entry cohort로 하고, 고정 후보도 같은 날짜로 비교한다. L26/L52 전체 NAV와 같은 post-fit 재기준 창을 공개한다. 후자는 기존 보유를 이어받은 창이며 fresh reset으로 가장하지 않는다. 이미 들여다본 역사에서의 시간순 causal replay이지 untouched OOS/전향 증거가 아니다. 이전 S2 expanding-mean 실패는 원 결과를 legacy로 보존하며 지우거나 재튜닝하지 않는다.

## 7. 주도주·시기 민감도

고정 이름은 KR {005930.KS,000660.KS}, US {AAPL,MSFT,NVDA,AMZN,GOOGL,GOOG,META,AVGO,TSLA}. 각 코호트에서 이름별 `w×(자산 순수익−ETF 순수익)`을 더해 전체 순초과와 정확 일치시킨다. gross 기여·직접 선택 주식 비중·ETF 비중·업종·판단일 cap top5 노출도 따로 보존한다. 직접 주식 노출을 ETF까지 look-through한 실제 전체 노출이라고 부르지 않는다. proxy look-through를 쓰면 원 Top120/common cap proxy임을 표시한다.

각 후보·horizon의 최대 순초과 기여 이름과 진입 calendar-year를 **사후** 식별한다. (i) 고정 주도주 집합의 비중을 ETF로 되돌림, (ii) 사후 최대 기여 이름 비중을 ETF로 되돌림, (iii) 사후 최대 기여 진입년 전체 제외, (iv) 주도주를 직접 보유한 코호트 제외를 계산해 n·구간·남는 성과를 보고한다. 새 거래 규칙/재선택이 아니다. 연도별·종목별 전체 기여 표를 보존해 한 번의 큰 구간 의존을 숨기지 않는다.

KR 원 SEMI_LED 보유 창 라벨/미정, 신호2022전후; US entry2023전후/exit2022까지를 그대로 보여준다. 미래 수익으로 분할한 구간은 사후 진단이며 정책 입력이 아니다.

## 8. 전달과 무결성

L26/L52는 각 시장 frozen 엔진, 원 모든 판단일의 equal initial capital 계정이며 계정 간 NAV 재배분 없음. 전체 후보의 fixed 결과·실패·matching·연도/이름 기여·NAV·CAGR/MDD/회전율/비용·이름 교체/유지 자산 비중 재설정을 보존한다. 입력과 성과 계산은 시장별로 병렬·캐시 재사용한다. 원 KR S2 및 K2/혼합과 원 US COCKTAIL/U1 full 수치를 검산하고 모든 harness/vintage 차이를 보고한다.

기존 전향 기록의 원 파일·상태·기술적 blocker를 별도로 점검·보존한다. 과거 분석이나 preview를 전향 관측으로 소급하지 않는다. 부족한 파일은 정확 경로로 적고, 다른 시장을 끝까지 계산·보고한다. 결과·명령·검증 기록을 하나의 GitHub draft PR로 공유하며 main 병합·승격·운영 변경은 하지 않는다.
