# Stock working capital v1 — 입력 복구와 합성 검증

**새로 알게 된 사실:** 기존 요약의 “매출채권·재고가 수집되지 않았다”는 설명은 현재 보존 원문 전체에는
맞지 않는다. 선별된 `dart_fundamentals` 계정 집합에는 없지만, 별도로 보존한 `kr-raw` 전체 응답과 미국
Finnhub 원문에는 있다. 이번 변경은 **새 정보축 두 개를 실제 원천에서 읽을 수 있게 한 것**이다.
새 초과수익 관계를 발견하거나 역사 라벨을 실행한 것은 아니다.

기존 #286에 이 독립 경로만 추가했다. `stock-working-capital-v1`은
`PROPOSED_NOT_REGISTERED_NOT_AUTHORIZED`, 과거 노출 표본의 탐색 후보다. 기존 연구의 종료·잠금·결과·명세,
미국 C1, Industry #290, Portfolio D를 바꾸지 않는다. 기존 원본 50개 SHA와 C1 고정 의존성 바이트 보존을 검사한다.

## 1. 두 가설과 우선순위

| 후보 | 고정된 입력 정의(높을수록 유리하다는 가설) | 기존 연구와 다른 정보 | 반증·한계 |
|---|---|---|---|
| WC2 재고 부담 완화 — 데이터 복구 우선 | 전년 재고/전년 매출 − 당년 재고/당년 매출 | NI−OCF 총발생액에 합쳐져 보이지 않는 재고 구성요소. 기존 4팩터 가중치 조합이 아님 | 재고 감소가 효율 대신 품절·감액·매각일 수 있음. 매출원가 부재로 재고회전일수라고 부르지 않음 |
| WC1 매출채권 부담 완화 | 전년 순수 유동 매출채권/전년 매출 − 당년 동 비율 | 고객 신용·회수 과정. 기존 이익/OCF 수준과 전환만으로 특정되지 않는 계정 | 팩토링·대손·인수합병·매출 분모 성장으로도 개선됨. 현금회수/경쟁력 향상으로 단정 금지 |

순위는 **커버리지에 따른 개발 우선순위**이며 수익률 순위가 아니다. 두 신호 모두 역사적 예측력 근거는 아직 없다.
자본배분은 기존 US capital-allocation/WID와 중복되고 권한·주식수·배당 문제가 남아 세 번째 가설로 재등록하지 않는다.
회계 가속도나 상대 가치의 가중치 변경을 새로운 발견이라고 부르지 않는다.

두 신호는 매출 성장만으로도 좋아질 수 있다. 따라서 매출 성장, 해당 계정의 현재 수준, 이익률, 총발생액,
가치·모멘텀·규모·유동성 및 같은 산업 조건을 기준선에 넣은 **추가 정보**가 질문이다. 이 통제를 생략한 양(+) 상관은
새 알파의 증거가 아니다. 원천에 값이 있다는 사실은 계정 간 독립 예측력의 증명이 아니다.

## 2. 기존 결과의 재평가 — 재실행 없이 커밋된 결과만 열람

| 구분 | 이미 존재하는 근거 | 이번 결정 |
|---|---|---|
| 등록 기준 실패 | [Phase D](../../docs/kr-alpha-research-final-development-assessment.md): 38변수/73평가/574fit, 34 NO_DEVELOPMENT_EVIDENCE, 4 BLOCKED, 지명 0. B4 오차는 모든 기간 B0보다 증가. X1 가치×건전성 p=.9895 | 재가중·기간 변경으로 구제하지 않음. Level4는 NOT_TRIGGERED이지 포트폴리오 실패 실측이 아님 |
| 통합 종목선택 시스템 실패 | [Model Overlay 봉인 보고](../../docs/kr-model-overlay-portfolio-v1-final-postmortem.md): DEVELOPMENT_REJECT; H126 MSE와 순경제성 모두 음의 방향 | 시스템 전체의 실패. 모든 개별 정보축이 무효라는 증거로 확대하지 않음 |
| 가능성은 있으나 확인 아님 | [산업 내 분석](../../docs/results/kr-stock-within-industry-anatomy-v1-report.md): 장부가 저평가 H126 IC +.086은 노출 역사 기술통계. 기반 membership은 DATA_FOUNDATION_INSUFFICIENT_V4 | 산업·2025/26·대형주 집중을 제거한 독립 증거로 취급하지 않음 |
| 검정력·안정성 한계 | [4팩터](../../docs/four-factor-signal-attribution-audit-v1.md): 4개 pooled H126 CI 모두 0 포함. [수익성 가속도](../../docs/fundamental-acceleration-discovery-v1.md): KR IC +.0361, CI [−.0502,+.1224], 유효 독립 18, 지역·기간 부호 불안정 | “약해서 참”도 “무조건 무효”도 아님. 같은 입력을 새 가설로 재명명하지 않음 |
| 불완전 경제 경로 | #286: NO STABLE ADDED ALPHA; H126 장중/모멘텀 19/24 유효 쌍의 +1.99%p, CI [−8.41,+16.69]는 기업행동 의존 complete-case 기술통계 | 전체 모집단 효과는 식별되지 않음. 009830/012450 권리와 일별 mark, 주식 부분분배/ETF 총배당 비대칭을 유지 |
| 측정 불가 | #287: rights / issuer-share-class identity / stock-SPY returnBasis BLOCKED. 수급·종결 대가도 미해결 | 모델 결과가 없으므로 실패한 알파라고 분류하지 않음 |
| 이번에 복구한 입력 | 아래 원문 매출채권·재고 | 기존 [정보 지도 §8](../../docs/alpha-information-inventory-v1-data-map.md)의 derived-field 부재와 raw-response 존재를 구분. 원 문서는 수정하지 않음 |

KR/US A0는 측정성 판정이며 알파 결과가 아니다. 기존 WID의 성장/현금흐름 전환 가설과 이번 구성요소의
차이를 유지한다. 어느 기존 결과도 이번 후보의 미래 수익 관계를 측정하지 않았다.

## 3. 실제 입력 측정 결과와 적격 표본의 차이

원천 Git `1bf68f59cffa20239977e2cfaa0f35a07d0ec884`, 보존된 회계 shard **26개**만 로컬 `cat-file`로 읽었다.
`GIT_NO_LAZY_FETCH=1`로 누락 객체의 자동 다운로드를 막았다. 가격·수익률·봉인 결과를 census에서 읽지 않는다.
`input-census.json`에 각 원천 SHA-256/바이트 크기, 연도별 분모와 비배타 결측 사유가 있다.
공식 원천은 [OpenDART 전체 재무제표](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020).
공식 API의 공개 접근과 특정 보존·재배포 권리를 동일시하지 않는다.

| FY | raw 연차 issuer 분모 | WC1 계산 가능 쌍 | WC2 계산 가능 쌍 |
|---|---:|---:|---:|
| 2015 | 175 | 0 | 0 |
| 2016 | 175 | 5 | 161 |
| 2017 | 183 | 5 | 161 |
| 2018 | 188 | 77 | 171 |
| 2019 | 193 | 5 | 5 |
| 2020 | 199 | 91 | 186 |
| 2021 | 206 | 93 | 194 |
| 2022 | 207 | 98 | 197 |
| 2023 | 238 | 44 | 191 |
| 2024 | 242 | 71 | 196 |
| 2025 | 242 | 97 | 201 |

한국 원문 8,343공시/246 ticker에서 WC1 **586 issuer-year 쌍·114 ticker**, WC2 **1,663쌍·209 ticker**를
계산할 수 있었다. **수익률 표본 수가 아니다.** 과거 실행 제안인 FY2016–2024만 세면 각각 **489 / 1,462쌍**이다.
FY2025는 2026년 공시된 입력도 포함하며 H126/H252 성숙을 확인한 것이 아니다.
최초 계산 가능한 입력 공개 다음 달력일은 WC1 2017-04-01, WC2 2017-03-25이고, 실제 거래일·신호일은 별도다.
휴장일을 다음 개장일 가격으로 대체하지 않았다. FY2019의 급락은 `ifrs_`→`ifrs-full_` 계정 변경도
**동일 기준이라고 가정하지 않고 거부한 결과**다. 매출채권+기타채권을 순수 매출채권으로 넓히지 않았다.

미국 FY2011–2025 **33,484공시·778 ticker**의 원문 BS에 정확한 `us-gaap_AccountsReceivableNetCurrent`
13,925건, `us-gaap_InventoryNet` 13,774건이 남아 있었다. **단일 공시의 개념 존재**이며 두 기간 정합성,
PIT/issuer 신원·보존권·수익 기준을 통과한 쌍이 아니다. 기존 #287 FY2011–2021 23,940건과는 기간이 다르다.
US 숫자 특징/가격/수익률/모델은 계산하지 않았다. 미국 실행은 계속 BLOCKED다.

**현재 완전히 source-admitted된 새 역사 표본은 KR/US 모두 0개다.** 연간 보고서라는 표시만으로 정확히 12개월인
동일 결산 창, 원래 공시 vintage, M&A/감액/팩토링 비교 가능성을 인증할 수 없다. raw store에 없는 종목은 위 공시 분모 밖이다.
신호 시점 Top120 모집단과 산업·규모의 결합 표본/커버리지는 아직 측정하지 않았으며 위 ticker 수로 대체하지 않는다.

## 4. 구현·검증 범위

`features.py`: 당해/전년 별도 공시, 공개일 엄격 이전, exact stock/corp identity, 동일 CFS/OFS, 단일 정확 계정,
KRW/차원·행 출처를 검사한다. 후속 보고서의 비교 열·결합 계정·결측 0 대체·가변 임계값은 사용하지 않는다.
`visible_pair`는 공시 수신 순서 대신 fiscal-year 순서로 선택하고 중복 버전·오래된 결산을 거부한다.
이 검사는 **입력 후보 계산**이며 원래 vintage나 연간 결산 창을 인증하는 기능은 아니다.

`design_checks.py`: 합성 데이터에서 intended-cohort/calendar digest, 개별 비교쌍 수·모든 결측 사유,
거래소 세션 기준 H126/H252 성숙, 실제 label end의 21세션 purge, train-only 결측대체/표준화·고정 Ridge,
사전 지정 집중도 민감도, 다음 시가/비용/완전 shareholder-wealth 경로, Holm·MDE·표본 부족을 검증한다.
104개 중 유효 쌍 2개, 사후 cohort 재봉인, 결측 블록 연결, 탈락 종목 삭제, 미해결 인적분할/거래정지 청산을 거부한다.
원천 입력 복구를 제외한 비교 함수는 **SYNTHETIC_ONLY rehearsal**이다. domain 표시는 보안 인증이 아니고,
독립적인 실제 승인·원천 어댑터가 없다. 실제 모델·포트폴리오 실행기를 완성했다고 주장하지 않는다.

**71개 테스트 통과**, 저장소 ruff·compile 통과, 임시 `/tmp` 경로 seed/validation 통과.
기존 봉인 실자료 재계산을 포함한 전체 로컬 pytest는 실행하지 않았다. GitHub 기존 CI는 별도다.
자세한 검증 SHA는 `validation.json`. 새로운 실행 권한이 생기지 않도록 proposal 상태도 테스트한다.

```bash
python -m pytest -q research/stock_working_capital_v1/test_study.py
ruff check .
python -m compileall -q pipeline research/stock_working_capital_v1
python -m research.stock_working_capital_v1.census             # PLAN_ONLY, 원천 읽기 0
python -m research.stock_working_capital_v1.census --inspect   # 이미 있는 회계 Git 객체만, stdout
```

## 5. 다음 실제 작업과 승인 경계

가장 정보가치가 큰 다음 개발은 **WC2의 FY2016–2024 원문을 신호 시점 Top120·동일 산업에 결합하고,
결산 창/공시 vintage/issuer 변화를 판정하는 outcome-free admission 어댑터**다. 동시에 원문 회계 계정 변경의
동등성을 독립 검증하면 FY2019의 구조적 커버리지 손실을 수익률을 보지 않고 해결할 수 있다.
이는 기존 장중 가설 구제가 아니며, 모든 eligible/ineligible 이름을 신호 전에 고정해야 한다.

이후 새 raw→shareholder wealth 어댑터가 009830/012450 등 권리와 완전 분배·종결·정지 경로를 증명해야 한다.
기존 부분 분배 adjusted index를 완전 총수익으로 바꾸어 부르지 않는다. 매수·매도 각 11.5bp와 날짜별 매도세,
ETF 세금 구분·2배 비용은 `proposal.json`의 **새 연구 비용 제안**이며 기존 #286의 모순된 spec을 바꾸지 않는다.
미국은 권리·신원·SPY 분배 이력이 독립 입증되기 전까지 이 단계에 들어갈 수 없다.

소유자에게 지금 요청할 것은 모호한 “실행 허가”가 아니다. `proposal.json`은 질문·기간·2가설·H126/H252·대조군·비용·
중단 조건을 구체화했지만 **실행 승인 요청은 아직 차단**되어 있다. 위 admission/실행 어댑터와 독립 감사가 끝난 뒤에만
정확한 HEAD, 원천/명세/코드/runtime SHA와 단회 실행 범위에 대한 승인을 요청한다. **승인만으로 현재 코드를 실행할 수 없다.**
FY2016–2024는 최대 9개 연도 cluster이고 시간순 평가/누락 후 더 줄어든다. 최소 독립 표본 10을 못 채우면
추론/신호 지명은 INCONCLUSIVE로 유지하며, 승인된 탐색은 기술적 효과와 결측률까지만 보고한다.
미국 확대와 H252/산업 대조군을 유리한 대체 primary로 선택하지 않는다. 예측력과 순경제성이 확보되기 전 D로 넘길 신호는 없다.

## 협업 인계

CLAIM: Stock-KR #286, 시작 HEAD `4fcfaf6a3581c3fb2d9b88cb56faef1a71be05aa`, Codex,
수정 범위 `research/stock_working_capital_v1/**`만. #292의 마지막 원격 CLAIM은 Market/Industry였고 Stock 경로는 충돌하지 않았다.
#292에 CLAIM을 게시하려 한 REST 요청은 `Post https://api.github.com/.../comments: Forbidden`으로 거부됐다.
같은 실패를 반복하거나 게시 성공으로 표시하지 않았다. 사용자의 직접 개발 지시 범위에서 이 격리 경로를 구현했으며,
GitHub API 게시 제한과 정상 Git/code/test 환경을 구분한다. 독립 감사는 미실시, 이 결과는 AUTHOR_VALIDATION_ONLY다.
새 PR·main 병합·기존 연구 재실행·운영 변경은 없다.
