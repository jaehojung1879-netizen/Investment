# 한국 입력·구현 가용성 조사 — 새 성과 계산 전

기준 PR #350 `36ac329261f8f9000935e524d8a28c2005524c10`. 2026-11-18 KST. 이 조사는 입력·기존 코드·기존 결과와 가격 존재 여부만 읽었고 새 전략 수익·새 가설 검정은 계산하지 않았다.

## 1. 기존 입력과 재사용

- `/workspace/s2-inputs/matrix.pkl`: 기존 matrix와 identity. 원 digest `32e49b57a7541eea66f76373baef50c6302a394247b313f6099f718d46d54b0c`.
- `/workspace/s2-inputs/dataset.pkl`: df 85,680×93, closes 3,364×262, sessions 2013-01-02~2026-09-14. 2018년 이후 원 판단일은454주다.
- `macro_panel.pkl`, `vix_fx.pkl`, `sg1-random-setup.pkl` 및 raw `ledger/universe/kr/krx-universe-{2013..2026}.jsonl.gz`가 있다.
- 기존 `research.kr_us_strategy_batch_v1.kr.RC.setup`을 호출하면 final-session 정정과 OCI 정정 가격·기존 ctx·원 S2/적격 집합을 재사용한다. cache가 있으므로 원 모델 fitting 경로를 다시 실행할 필요가 없다.
- 재개용 `/workspace/s2-inputs/kr-us-batch-v1-prepared.pkl`은 source 모듈을 먼저 import한 뒤 읽어야 한다. 일반 pickle 단독 로드는 동적 모듈 `amd_analyze`를 못 찾는다. 기존 `kr.py --stage summary|ledgers`가 이 순서를 이미 따른다.

### 주 선택력 검정에서 재사용할 원본

`research/kr_us_strategy_batch_v1/results/KR/`의 다음 파일을 읽는다.

- `cohorts-{126,252}.csv.gz`: 모든454주와 각 책의 net/gross/cost/ETF excess.
- `matched-{126,252}.csv`: 신호별 selection/replacement/peerNet/actual/matchComplete.
- `matching-audit.csv.gz`: 모든 leg의 held/peer·cap·거리·실패 사유.
- `books.json.gz`, `matched-books.json.gz`, `asset-payoffs.csv.gz`: 실제 책과 계산 입력의 유도 결과.
- `summary.json`: own paired 통계, 분모·매칭률·weighted leg coverage·실패 사유가 이미 있다. 이번에는 own 마스크를 주 검정으로 사용하고 새 검정 가족만 계산 전에 고정하면 된다.

아래는 새 결과가 아니라 #350의 기존 표본 재고다. 매칭률은 만기 비어 있지 않은 판단일 분모이며 6/12개월 만기427/400주다.

|신호|own n6/12|블록 근사 n/25, n/50|매칭률6/12|
|---|---|---|---|
|S2|324/298|12.96/5.96|75.88%/74.50%|
|VALUE_ORIGINAL|402/375|16.08/7.50|94.15%/93.75%|
|VALUE_COMPLETE|382/355|15.28/7.10|89.46%/88.75%|
|CONFIRM_NEUTRAL|258/242|10.32/4.84|60.42%/60.50%|
|FOUR_FACTOR|281/258|11.24/5.16|65.81%/64.50%|

주 탈락 사유는 시총½~2배 안 peer 없음이다. 4요인에는 업종 미측정(6/12 모두32 leg), 같은 업종 unused peer 없음(23 leg)도 있다. 서로 다른 신호의 평균 차이는 두 신호의 공통 유효 날짜에서 다시 차분해야 한다.

## 2. 실제 KODEX200 과거 구성 자료

저장소·작업공간과 signal-history `4ea107ed` tree에서 실제 ETF 과거 holdings는 찾지 못했다. 그 tree에는 `ledger/benchmarks/069500.KS.jsonl.gz`가 있다. 기존 `pipeline.kr_integrated_alpha_portfolio_postoutcome_audit.concentration_snapshots`와 `kr_followup/s2_decomposition.py:proxy_weights`는 **월별 PIT Top120 총시총 proxy**를 쓴다. 이를 실제 KODEX200/KOSPI200 비중으로 부르지 않는다는 기존 문구를 유지해야 한다.

그러나 이번 입력-only 공개 원천 조사에서 공식 Samsung endpoint의 과거 조회를 확인했다.

- 상품: `https://www.samsungfund.com/etf/product/view.do?id=2ETF01`.
- 공식 product.js가 호출하는 원 endpoint: `https://www.samsungfund.com/api/v1/kodex/product-pdf/2ETF01.do?gijunYMD=YYYY.MM.DD`.
- `pdf.gijunYMD`, `totalCnt`, `nowCnt`, `pdfExcelDownloadUrl`, `list`를 반환한다. 각 행은 `itmNo`, `secNm`, `evalA`, `applyQ`, `ratio`를 담는다.
- 전체 XLS 경로는 응답의 `/excel_pdf.do?fId=2ETF01&gijunYMD=YYYYMMDD`다. UI의100개 노출 문구와 달리 조사한 JSON은 전체 행 수와 list 길이가 같았다.

|요청일|반환일|전체 행 수|원 JSON SHA-256|
|---|---|---|---|
|2018.01.04|20180104|199|0c5a2e2593008cd10e599533322e83b842541d313cb8f590a6279f07fb376657|
|2021.01.07|20210107|198|006c017b58d26361279192ad748b49b793ce28ecac9a563c1f486c1af8f4dfb8|
|2026.09.10|20260910|202|cbf3992bf5c64c027a0196ef3eb350aee41640aef47cb850e59ee40b8cb12da3|

이 원문은 `/tmp/kr-kodex-inventory/`에 저장했다. 같은 폴더에 `product.html`(SHA `2d430cf315e26d7668b04e827b489e80661b4246ad11562bf2f804c9ac58cda4`)과 `product.js`(SHA `dc1124b703158a0b477d154b8ddf97db851c56c6342d8b038cc25c34e674c728`)가 있다. 전체454주 수집을 시도했으나22개 성공 뒤 HTTP429가 발생했다. 요청 간격을 둔 단일 재시도도 첫 요청429였으므로 즉시 중단했다. 기존2021/2026 probe 두 개를 합쳐 **서로 다른24개 snapshot**을 `/workspace/exposure-inputs/kr/kodex-pcf/`에 보존했다. `manifest.json`은 요청일·반환일·SHA·원본문 경로·성공/실패와 재시도 보류 상태를 담는다. `Retry-After`는 응답에 없었으며 추가 요청은 보류했다. 첫22개 receipt에는 HTTP Date와 관측 UTC가 있고 기존 probe 두 개에는 원 HTTP 시각이 남지 않아 파일 mtime만 별도 표시한다. 유료 파일이 필요한 상황은 아니지만 전체 과거 공시 수집은 미완료다.

### 분모·분류·시점 주의

1. 공식 JS 문구는 “구성종목(PDF)의 비중은 국내외 현금성 자산과 예금 비중을 제외하여 계산”이다. `ratio` 합이 약100%여도 현금이 있다. 경제적 총자본 노출에는 `evalA` 총액을 확인하고 현금도 분리해야 한다. 조사한2018/2021/2026 snapshot의 현금은 각각1.6132%/1.7351%/0.0849%다.
2. 2018 삼성의 published ratio는27.53%지만 전체 evalA 분모로는27.0870%다. 2021은32.81% 대32.2393%다. 현금 제외 ratio를 ETF 전체 비중으로 쓰지 않는다.
3. KRX 코드는 숫자6자리만이 아니다. `0126Z0`(삼성에피스홀딩스), `0220W0`(한화머시너리앤서비스홀딩스)도 실제 주식행이다. 현금 `KRD010010001`과 구별하고 선행0·영문자를 보존한다.
4. 20180104 PDF 삼성 evalA/applyQ=2,581,000은 봉인 KRX2018-01-03 종가와 같으며 당일1/4종가2,554,000과 다르다. 20210107도82,200=1/6종가이며1/7종가82,900과 다르다. 표시일 D의 전세션 평가가격을 담은 PDF로 관측됐다. 이 비교는 `4ea107ed:ledger/prices/kr/krx-prices-{2018,2021}.jsonl.gz`를 읽었다.
5. 오늘 조회한 역사적 공시이고 당시 배포시각·수정 빈티지를 입증하는 archive는 없다. 판단일 이전 gijun의 보수적 lag를 사전 정의하고, `RETRIEVED_HISTORICAL_ISSUER_PDF`, `RELEASE_TIMESTAMP_UNVERIFIED`를 구분해야 한다. 현재 holdings를 과거에 대입하는 방식은 아니다.

### 실제 복제 가격·업종의 커버리지

세 입력 snapshot의 evalA 총액 분모에서 확인한 존재 여부다. 수익은 계산하지 않았다.

|snapshot|주식 비중|기존 closes열이 있는 주식 비중|판단일 Top120 업종 기지 비중|
|---|---|---|---|
|2018.01.04|98.3868%|96.7752%|91.9361%|
|2021.01.07|98.2649%|97.5129%|93.6796%|
|2026.09.10|99.9151%|99.6032%|97.8044%|

기존 가격에 없는 예는2018 동국제강001230/이노션214320/동아에스티170900,2026 달바글로벌483650/이수스페셜티케미컬457190/DN오토모티브007340 등이다. 정확한 tail 가격·기업행위·당시 업종이 없으면 **실제 전체 ETF 복제 성과**라고 표시할 수 없다. 미측정 tail을0 또는 ETF로 조용히 채우지 않는다. 실제 구성 공시의 노출 감사와 Top120/covered-holdings proxy의 성과는 별도로 보고할 수 있다.

전체 Top120을 고정보유하는 기준책도 가격가용성을 새로 점검해야 한다. raw dataset 및 교정 후 I2의 entry/exit 양 끝 존재 검사에서 모두6개월269/427주,12개월130/400주가 전체 가격을 갖췄다. 실패는000030,079440,003410,010620,000060,008560에 몰린다. 이 수는 거래가능성·중간 상태 검증 전의 가용성 상한이며, 미래 가격이 없는 종목을 사전에 선택하지 않는 규칙으로 써서는 안 된다.

## 3. 같은 신호로 노출을 유지하는 방법의 수학

기준 ETF의 당시 관측 보유 비중을 b, 동일한 신호 주식 q와 정규화 선택 비중을 S라 두면 기존 방식은 `(1−q)b+qS`다. 순수한 ETF(1−q)+같은 주식 q만 고정하면 업종·주도주 노출 차이는 `q(S−b)`로 이미 결정된다. 모든 노출을 추가로 보존할 자유도가 없다.

직접복제 모사는 `w=b−d+qS`, `0≤d≤b`, `sum d=q`인 donor d를 정해 구현할 수 있다. 업종·주도주 combined group의 donor 마진이 신호의 마진과 같으면 그 노출은 보존된다. donor에 선정 종목을 포함할 수 있고 그 경우 거래는 반드시 netting한다. 명목 신호 q, 실제 active weight `0.5*sum|w−b|`, 개별 주식 수와 상장 ETF 비중을 따로 보존해야 한다.

- 업종 s에서 필요한 donor 총액은 `T_s=q*S_s`다. 이 값이 기준 업종 비중 B_s보다 크면 정확 업종 보존은 long-only에서 불가능하다.
- 두 반도체 묶음의 donor를 업종별 m_s라 하면 `max(0,T_s−B_s_nonmega)≤m_s≤min(T_s,B_s_mega)`이고 `sum m_s=q*S_mega`여야 한다.
- 각 삼성/하이닉스 이름을 개별로 정확 고정하면 그 이름의 신호 active weight가 상쇄될 수 있다. combined 묶음 보존과 개별 이름 보존을 구별한다.
- 정확 불가능한 날짜에는 q 축소·rerank를 하지 않고 실패를 기록한다. q를 유지하는 가장 가까운 노출 LP를 보조로 택하려면 그 목적함수·우선순위를 결과 전에 고정한다. `d=q*b`는 기존 방식의 feasible donor라서 최적화의 노출 손실이 이 기준보다 커지지 않는지 검산할 수 있다.
- 실제 ETF+long 주식으로 같은 w를 일반적으로 만들 수 없다. ETF 내부 donor를 직접 파는 것은 불가능하기 때문이다. ETF+long selected+short donor overlay에는 공매도 대차·담보·금융비용이 필요한데 기존 비용 입력은 이를 모형화하지 않는다. 이 경로를 실현 가능한 기존 long-only ETF 책으로 부르지 않는다.

### 비용과 대조의 분리

직접복제에는 ETF 자체의2.5bp 비용이 아니라 원 주식5.5bp 매수/매도+dated sell tax를 적용하고 net positions만 거래해야 한다. 원 ETF 책과 원형 ETF 대체 책은 #350 장부를 그대로 재사용한다. 새 복제 기준책 `b`, 같은 구현의 `b−d+qS`를 둘 다 계산하고 다음을 따로 보고하면 기준 차이를 숨기지 않는다.

`aligned−actual ETF = (aligned−costed replica b) + (costed replica b−actual ETF)`.

두 번째 항에는 coverage·고정보유/ETF내부 재구성·분배/기업행위·운용비 차이가 있다. 이 항을 선택력에 할당하지 않는다. proxy라면 동일 Top120 시총 proxy와 비교했다고 표시하고 실제 ETF 노출 일치를 주장하지 않는다.

같은 업종·시총 peer의 mega 분류가 선정 종목과 다르면 두 책의 노출 보존 funding이 달라질 수 있다. 기존 주 선택력(업종+cap)과 노출 보존 후의 대조(업종+mega 또는 residual 차이)를 구분하고, 같은 donor를 쓸 수 있는 비교에서는 funding이 상쇄되어 `q*(S−P)`가 남는지 검산하는 것이 유용하다.

## 4. 사업 확인 단독의 해시 의존

원 `CONFIRM_NEUTRAL`은 complete pool에서 C01/C05/C14>0인 이름을 원 seed20261118의 날짜별 SHA256 순서로5개 고른 새 구성이다. 원 독립 사업 점수가 아니다.

계산 전에16~32개 고정 seed를 정해 원 k=5·총주식20% 선택력만 반복하면 효과가 최고 seed 하나에 기대는지 볼 수 있다. 각 seed의 모든 판단일·actual count·동일 시총 범위1:1 matching·탈락 사유를 저장한다. 각 own paired 평균/CI/블록 수와 원 seed와의 쌍별 공통 날짜 차이를 함께 보존하고 seed×date를 독립 표본으로 쌓지 않는다. 최고 seed를 운용 후보로 택하지 않는다. seed 평균 통계를 만들면 날짜별 seed coverage가 변하는 한계와 조건부 표본을 명시해야 한다.

모든 확인 후보 EW는 다른 종목 수가 되고 industry 전체를 덮으면 미보유 peer가 사라질 수 있으므로, 이를0~5 actual book의 동일 대조라고 부르지 않는다. 별도 전체 후보 교차단면 진단으로만 정의하거나 위 다중 고정 seed를 우선하는 편이 비교 조건이 분명하다.

## 5. 기업행위·운용 엔진

기존 `asset_payoff`는 원 C.cost_rate와 corrigendum 가격을 사용하고, interior carry를 허용하되 unresolved terminal/end price는 미측정이다. FOUR_FACTOR 일부2018~19/2022 창의 가격 미해결을 종목 교체·0 수익으로 채우지 않는다.

원 `A.multi_account`/`C.simulate`는 L26/L52 equal-initial-capital 계정이고 계정 사이 리밸런싱은 없다. 비용/회전율 영수증을 얻기 위해 prefix를 재실행하는 구조라 새 복제 책 수가 늘수록 시간이 든다. 직전 연구의 재개 캐시 `results/KR/ledger-cache`134개를 읽을 수 있으며 동일한 전체 목표 책 해시만 재사용하는 방식을 유지한다. seed robustness는 fixed6/12만 계산하고 원 seed의 운용 구성을 메인으로 두면 중복 NAV 계산을 줄일 수 있다. 엔진의 terminal-zero가 생긴 raw NAV는 조건부이며 위험 개선 판정에서 제외한다.


## 5. 공식 PCF의 의미를 실제 펀드 보유와 구분

공식 JS 영문은 PDF를 **Portfolio Deposit File**로 부른다. 단순 보유 구성과 설정·환매용 basket이 같은지는 검증되지 않았다. 특히 입력만으로 다음 예외가 확인됐다.

|공시 표시일|삼성전자 행|삼성전자 PCF evalA 비중|원화예금 PCF evalA 비중|
|---|---|---|---|
|2018-04-26|있음|26.2077%|1.7257%|
|2018-05-03|없음|행 미제공|27.9025%|
|2018-05-10|있음|26.8208%|0.5289%|

5월3일은 삼성 액면분할 거래정지 기간이며 해당 PCF에는 삼성 행이 없고 현금이 커진다. PCF 현금 대체 가능성을 배제할 수 없다. 따라서 앞의 evalA 정규화는 **PCF basket 전체 평가액 대비 비중**이며 실제 펀드 총자산의 투자 비중이라고 주장하지 않는다. 관련 원문 발췌와 byte 위치는 `kodex-pcf/evidence/semantics.json`에 보존했다. `holdings-normalized.csv.gz`의 열 이름은 `pcfEvalWeight`이며 실제 full holdings로 오인할 이름을 쓰지 않는다. 이 파일을 전략 복제 수익의 기준 b로 바로 사용하지 않는다.

24개 snapshot은2018-01-04~2018-05-31의22개와2021-01-07,2026-09-10이다. 이전 공시만 사용하고 최대120일을 적용한 입력 가용성은454판단일 중58일이다(`asof-audit-availability.csv`). 나머지396일은 stale/미측정이며2018자료를2026으로 carry하지 않는다. 이58일도 원 배포시각/수정 빈티지 미검증과 PCF 의미 제한이 남는다.

전체 반환 행의 evalA에는24snapshot 모두 알려진 주식 코드 형태와 원화예금 외의 자산이 없었다(미분류 자산 평가액0). 이는 6자리 영숫자 코드의 형식 분류이며 독립적인 security-class 검증을 대체하지 않는다. 알려진 파생 행은0개지만 별도 파생이 펀드에 없다는 증거로 확대하지 않는다.

전 Top120 기준이 아니라260종목 industry foundation 전체를 날짜에 맞춰 조회하면 공식 PCF의 업종 기지 비중은2018-01-04 **95.3497%**,2021-01-07 **97.1003%**,2026-09-10 **99.6032%**다. 기존 TR 열이 있는 비중은96.7752%/97.5129%/99.6032%다. 두 값은 PCF 전체 evalA 분모이고 현금 포함이다. 2018-05-03의 주식 비중72.0975%와 TR열 기지70.5257%를 누락가격 악화라고 해석하지 않는다. 현금 대체 가능성이 분모를 바꾼 예외다.

## 6. 더 넓은 기존 가격·업종 입력의 복구 조사

- frozen replay manifest `raw/ledger/historical/replay-v16/inputs.json` SHA `f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2`의189개 월별 price panel을 전부 해시 검증했다. KR ticker는260개이며 현 corrected closes 밖 새 KR ticker는0개였다. `/workspace/exposure-inputs/kr/replay-price-inventory.json`에 각 ticker row 수와 연도별 종목 수를 보존했다.
- pinned `4ea107ed:ledger/prices/kr/krx-prices-2018.jsonl.gz`는122,112행·510종목의 **as-traded** 가격을 갖고001230 등 현재 TR에 없는 tail도 있다. 이 shard blob은 `1d1316f27d5d4ae79205082a191974facabaa5721`이다. raw quote가 존재한다는 사실은 배당·분할·합병을 정정한 기존 total-return 장부가 있다는 뜻이 아니다. 새 vendor 가격은 받지 않았다.
- `data/kr-industry-membership-foundation-v4/state/intervals.json.gz`는260종목이다.001230/214320/483650/457190 같은 tail은 없다.260종목 전체를 읽어 해당일 Top120 밖 이름의 업종을 복원할 수 있지만 이름으로 업종을 추정하여 나머지를 채우지 않는다. `load_membership_inputs`와 `industry_of`/`membership_table`의 날짜·terminated 규칙을 재사용한다. 이 foundation 자체의 `DATA_FOUNDATION_INSUFFICIENT_V4`, 현재 KIND anchor 재구성 한계도 유지한다.

결론적으로 현재 자료만으로 실제 full200 ETF 복제 성과는 막혀 있다. main 계산은 기존 Top120 시총 proxy라고 분명히 부르고, 공식 PCF는24snapshot/최대120일의 보조 노출 감사로 분리하는 구현이 가능하다. 실제 보유비중을 맞췄다고 부를 수는 없다.

## 7. 입력만으로 정한 NAV coverage suffix

`/workspace/exposure-inputs/kr/quote_hazards.py`는 원 L26/L52 next-session 스케줄에서 전 positive-cap Top120 기준책 b의 **양수 보유 support**만 추적한다. 원 `tradable`과 locked 보유 규칙은 재사용하지만 units·수익·NAV·비용·가격비율은 계산하지 않는다. 미래 quote 존재와 terminal 상태를 입력 가용성 감사에만 쓴다.

|주기|미해결 terminal을 보유한 사건 수|마지막 종목·마지막 quote|마지막 hazard 세션|target 체결불능 사건 수|
|---|---|---|---|---|
|L26|156|010620.KS /2025-12-12|2025-12-15|116|
|L52|312|010620.KS /2025-12-12|2025-12-15|116|

마지막 terminal hazard의 다음 연도 첫 판단일은 **2026-01-02**다. 이를 결과 전 고정한 보조 `NAV_COVERAGE_SUFFIX`로 사용할 수 있다. 데이터는2026-09-14까지이므로 이 창에는12개월 이상의 실제 운용 기간이 없다. 반면 target의 거래불능까지 모두 제거하는 엄격 기준은 마지막000880.KS 체결불능이2026-08-24라 데이터 안에 다음 연도 suffix가 없다. 따라서2026 suffix는 terminal-zero 위험을 피하는 보조창이며 정확 노출의 실물 체결을 보장하는 창은 아니다. 원2018 전체 NAV가 terminal 처리를 해결하지 못하면 미측정 상태를 유지한다. 원 사건과 판정은 `quote-hazards.json`에 있다.
