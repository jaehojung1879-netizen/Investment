# 미국 주주 분배 피처 기반 v1

**범위:** 데이터·피처 엔지니어링·입력 품질 검증. 연구 전용이며 운영 경로에서 읽지 않는다.
수익률, 미래 라벨, 가격, 모델 학습, 백테스트, 투자 추천을 사용하거나 생성하지 않았다.
`main`을 원격에서 확인한 시작 SHA는 `7ea46928eb1e154bf502cabc9030f8fbf47acb68`이다.
Claude의 미병합 브랜치를 읽거나 의존하지 않았다. 공용 코드·설정·CI·과거 연구 결과·실행 잠금·영수증을 변경하지 않았다.

## 인터페이스와 피처 정의

`pipeline.us_shareholder_distribution.derive_features(ticker, as_of, filings, metadata)`는
`FeatureSnapshot`을 반환한다. 여러 날짜에는 같은 입력을 복사·준비하는 `FeatureEngine(...).as_of(date)`를 쓴다.
`SourceMetadata`는 출처, 스냅샷 ID, USD, 회계연도 누적 규약과 그 증거를 명시적으로 요구한다.
각 피처에는 값, 상태, 단위, 계산 방식, 원시 입력 값·개념·공시 ID·가용일·접수 시각·수집 관측일·회계 기간이 따라온다.
버전은 `US_SHAREHOLDER_DISTRIBUTION_V1`이며 정렬된 canonical JSON의 SHA-256으로 digest를 만든다.

| 피처 | 정의 / 단위 |
|---|---|
| `cashDividendsPaidTTM` | **보통주** 현금배당 지급의 TTM, USD. 일반 전체배당의 대체값은 사용하지 않음 |
| `cashDividendsPaidTTMChangeYoY` | 동일 회계 단계의 현재/전년 TTM − 1, 소수 비율 |
| `commonStockRepurchasesTTM` | 집행된 보통주 매입 지출의 TTM, USD |
| `repurchasesTTMChangeYoY` | 동일 회계 단계의 매입 TTM 증가율, 소수 비율 |
| `totalCashDistributionTTM` | 보통주 현금배당 TTM + 보통주 매입 TTM, USD |
| `totalCashDistributionChangeYoY` | 두 구성 요소 모두 관측된 동일 회계 단계 총분배 증가율 |
| `operatingCashFlowTTM` | 전체 영업활동 현금흐름 TTM, USD |
| `distributionToOCF` | 총분배 / 양수 OCF, 소수 비율 |
| `distributionCoverageByOCF` | 양수 OCF / 양수 총분배, 소수 비율 |
| `capitalExpendituresTTM` | PP&E 취득 지급 TTM, USD. 다른 생산자산·개량 지출을 섞지 않음 |
| `cashAndCashEquivalents` | 해당 공시의 현금·현금성자산 기말 수준, USD. TTM이나 유동성 점수는 아님 |
| `sharesOutstandingChangeYoY` | 근거가 있는 동일 단계 기말 보통주 수의 전년 대비 변화. 실제 저장소에서는 `BLOCKED` |
| `shareCountReductionIndicator` | 위 변화율 < 0. 실제 저장소에서는 `BLOCKED` |

증가율의 전년 값은 **양수**여야 한다. 0에서 지급을 시작한 사례는 관측된 0을 입력에 보존하고,
정의할 수 없는 증가율은 `NOT_APPLICABLE`로 둔다. 임의의 100% 증가나 0 증가로 채우지 않는다.
OCF가 0/음수이면 관측값 자체는 보존하되 지원 비율은 계산하지 않는다. 분배가 0이면
양수 OCF에 대한 `distributionToOCF=0`은 유효하나 역수는 무한대 대신 `NOT_APPLICABLE`이다.
두 지원 비율은 대수적 역수이므로 독립된 정보 발견 두 건이 아니다.

상태는 `VALID`, `REPORTED_ZERO`, `NOT_REPORTED`, `NOT_APPLICABLE`, `INVALID`,
`INSUFFICIENT_HISTORY`, `AMBIGUOUS_ACCOUNTING`, `BLOCKED`를 분리한다.
항목 부재는 비지급의 증거가 아니며 항상 결측이다. 0은 해당 개념에 실제 보고된 유효 숫자에서만 나온다.
일반 배당·계속영업 OCF 등 관련 항목만 있으면 개념을 대체하지 않고 `AMBIGUOUS_ACCOUNTING`으로 둔다.
매입 승인 발표는 지급 개념이 아니므로 사용하지 않는다. 매입 지출이 있어도 주식 수가 늘 수 있다.

## 원천 계약과 개념 인벤토리

기존 `finnhub_fundamentals`의 namespace·공시 내부 unit 해석을 재사용한다.
해당 규약은 라벨 이름만 읽는 단순 prefix 판단과 다르며 generated unit은 같은 공시의 알려진 anchor로만 해석한다.
명시적 EUR·USD/주·불명 단위·스케일이 불명인 USD millions, 비수치·NaN·무한대·bool은 거부한다.
지급 항목과 현금 잔액의 음수는 거부하며 OCF의 음수는 실제 관측 상태로 보존한다.
같은 개념의 충돌하는 복수 행도 합산하거나 첫 행을 택하지 않는다.

| 가족 | 피처에 허용한 정확한 개념 | 섹션 / 규약 | 인벤토리만 기록한 관련 개념 |
|---|---|---|---|
| 배당 | `PaymentsOfDividendsCommonStock` | `cf`, USD, fiscal YTD | `PaymentsOfDividends`, `PaymentsOfOrdinaryDividends`, 우선주 배당 |
| 매입 | `PaymentsForRepurchaseOfCommonStock` | `cf`, USD, fiscal YTD | 승인 발표는 입력 목록에 없음 |
| OCF | `NetCashProvidedByUsedInOperatingActivities` | `cf`, USD, fiscal YTD | `...ContinuingOperations`는 전체와 구분 |
| capex | `PaymentsToAcquirePropertyPlantAndEquipment` | `cf`, USD, fiscal YTD | 생산자산·개량·기타 PP&E 지급 |
| 현금 | `CashAndCashEquivalentsAtCarryingValue` | `bs`, USD, 기말 수준 | 제한 현금·포괄 현금·단기 투자 |
| 주식 수 | `CommonStockSharesOutstanding` | `bs`, shares; 기말·분할·종류 확인 필요 | DEI 커버 수치, 기본/희석 가중평균은 대체하지 않음 |
| 주당배당 | 사용하지 않음 | 보고 메커니즘 불안정 | declared/cash-paid를 보고율 비교에만 사용 |

개념별 원문 이름, 단위 분포, 섹션, 단계, 연도, 첫/마지막 가용일, 양수/0/음수/비수치 상태,
정정 행 수, 출처, 사용 규약과 유효성 제약은
[`us-shareholder-distribution-feature-audit.json`](us-readiness/us-shareholder-distribution-feature-audit.json)의 `fieldInventory`에 있다.
의미의 근거는 기존 원천 계약·실제 섹션/단위/기간·아래의 값 비율 검증이다. 공식 FASB 2025 문서
`https://xbrl.fasb.org/us-gaap/2025/elts/us-gaap-doc-2025.xml` 직접 조회는 HTTP 403으로 실패하여 읽었다고 주장하지 않는다.
Finnhub가 각 XBRL 행의 context 날짜·주식 종류·연결 범위 정보를 평탄화하므로 원 공시와의 독립 대사는 남아 있다.
코드는 모든 결과에 `VENDOR_FLATTENED_CONTEXTS_NOT_INDEPENDENTLY_RECONCILED` 경고를 제공한다.
이 구현은 **선택한 저장소 공시 버전에 대한 PIT 필터**이며 SEC 원본과 독립 대사된 `PIT_EXACT` 인증이 아니다.

## 누적 회계 처리와 시점 정합성

분기 합산·연율화 없이 기존 `finnhub_derive.trailing_twelve_months`를 직접 호출한다.
각 정확한 개념에서 검증한 scalar를 지역 어댑터로 전달하며 `FLOWS` 전역 registry를 변경하지 않는다.

`TTM(Y,Q) = FY(Y−1) − cum(Y−1,Q) + cum(Y,Q)`; FY는 실제 연간 지급/현금흐름을 쓴다.
누적 Q1/Q2/Q3는 기존 `quarter_stage`의 기간 길이와 실제 fiscalQuarter/form/date를 함께 검증한다.
연간 anchor는 350–380일, 동일 단계의 전년 기간 종료 차이는 350–380일,
같은 단계 기간 길이 차이는 14일 이내로 제한한다. fiscal-year start/annual-end 경계도 확인한다.
변경된 회계연도·전환 보고·분기와 누적 기간 혼합은 거부한다. 전년도 anchor가 없으면 결측이다.
YoY는 전년 **같은 단계의 별도 TTM**을 계산하므로 분기 YoY는 두 해 이전 FY/동기까지 필요할 수 있다.

신호 날짜 T에는 `max(availableFrom 날짜, 알려진 acceptedDate 날짜) < T`인 공시만 선택한다.
이는 `<= T`보다 보수적인 기존 연구 규약이다. 같은 날의 date-only 공시는 쓰지 않는다.
가용일·접수일·기간 종료가 모순이면 거부한다. 원 공시 날짜, 기간, accepted 시각,
`collectedAt` 연구 관측 시각을 서로 대체하지 않는다. 수집 시각으로 과거 가용성을 창작하지 않는다.

필터를 **먼저** 적용한 후 회계 슬롯별 최신 관측 공시를 선택한다. 최신 기간이 current이며
뒤늦게 도착한 오래된 기간이 current를 대체하지 않는다. 정정 공시가 보인 이후에만 해당 슬롯을 대체한다.
정정에 항목이 없어졌다면 원 공시 값으로 되돌아가지 않는다. 충돌 ID/기간/동시 공시는 안전하게 거부한다.
동일 ID의 동일 내용 중복은 멱등이다. 원시 배열 순서에 선택 결과가 의존하지 않는다.
새 스냅샷의 물리 ID는 digest에서 제외하며 선택된 값/출처/기간/상태와 규약을 해시한다.
나중 공시를 삽입해도 동일 과거 as-of의 피처와 digest는 그대로다.

주식 수 피처는 정확한 prior/current 공시 쌍과 기말 context·분할·주식 종류 비교 가능성에 대한
`SharesBasisEvidence`가 있을 때만 계산한다. 이 증거의 가용일도 T보다 **이전**이어야 한다.
현재 원시 저장소에는 그 증거가 없으므로 모든 실제 회사-날짜에서 차단한다.
합성 테스트는 증거가 있는 비교, 매입 중 순희석, 순감소, 미래 증거의 누출 방지를 검증한다.

## 실데이터 감사와 한계

새 수집 없이 기존 `signal-history`의 고정 커밋 `704d7db6d5b00def771aba5d2665d0846d6bc776`에서
`ledger/fundamentals/us/finnhub-*.jsonl.gz` **17개**만 읽었다. 원본 branch에는 쓰지 않았다.
추출한 commit/blob manifest를 검증하고 각 샤드 Git blob ID·SHA-256을 결과에 보존한다.
감사 범위는 40,000건 / 압축 128 MiB 이내이며 초과·빈 입력·파일/해시 불일치는 부분 성공 없이 실패한다.
같은 입력에 대한 안전한 실패 처리 보완 후 같은 감사 결과를 재생성했으며 후보를 수익률로 선택하지 않았다.

- 원시 공시 **34,945건**, 회사 **782개**. 잘못된 회계연도 **4건**을 따로 기록한다.
  기존 감사의 34,941건은 이 4건을 제외한 수와 일치한다. 접수 timestamp가 없는 공시 1건도 기록한다.
- 기간 종료 이전 가용 공시 **0건**. 중복/충돌 원시 ID **0건**.
- 회사별 유효 publication 날짜 + 1 **달력일**을 이벤트 날짜로 썼다. 34,905개 회사-날짜이며
  거래일 grid, 당시 지수 구성종목, 미래 투자 대상의 분모로 주장하지 않는다.
- 공동 준비 **6,174 / 34,905 = 17.69%**: 보통주 배당·매입·전체 OCF TTM,
  총분배 YoY, 양수 OCF 대비 분배 비율이 모두 있는 이벤트 회사-날짜.
- 업종/섹터 커버리지 **NOT_MEASURED**: 신뢰할 만한 날짜별 분류가 선택한 원천에 없으므로 현재 분류를 소급하지 않았다.
  회사별 보고율, history 기간·distinct fiscal periods, 피처별 상태와 준비 날짜 수는 `byCompany`에 있다.

| 피처 | 유효 값(보고된 0 포함) / 34,905 | 비율 |
|---|---:|---:|
| 보통주 현금배당 TTM | 12,528 | 35.89% |
| 현금배당 TTM YoY | 10,699 | 30.65% |
| 보통주 매입 TTM | 20,207 | 57.89% |
| 매입 TTM YoY | 16,186 | 46.37% |
| 총분배 TTM | 8,855 | 25.37% |
| 총분배 YoY | 7,244 | 20.75% |
| 전체 OCF TTM | 25,840 | 74.03% |
| 분배 / OCF | 7,436 | 21.30% |
| OCF / 분배 | 7,422 | 21.26% |
| PP&E 지급 TTM | 20,885 | 59.83% |
| 현금·현금성자산 수준 | 30,403 | 87.10% |
| 주식 수 변화/순감소 지표 | 0 (BLOCKED) | 0% |

단일 지급 가족도 누적 규약을 값으로 재검증했다. Q2/Q1, Q3/Q1 중앙값은 각각
보통주 배당 **2.000 / 3.004**, 보통주 매입 **1.870 / 2.737**, 전체 OCF **2.129 / 3.445**,
PP&E 지급 **2.069 / 3.210**이다. 두 비율 모두 기존 cumulative band와 최소 30 ticker-year를 충족한다.
이는 벤더 규약의 집계적 근거이며 개별 context를 검증한 것은 아니다.

주당배당의 namespace 등가 표기를 모두 읽은 보고율은 **2018년 51.22% → 2019년 19.36%**,
2025년 10.81%다. 단절 메커니즘은 **NOT_MEASURED**이며 주 피처로 사용하지 않는다.
기존 감사는 정확한 `us-gaap_...` 문자열만 세었다. 이번 감사는 기존 `strip_namespace`로
등가 unprefixed 표기를 함께 읽으므로 2012년 OCF 등 기존 낮은 보고율도 그대로 가져오지 않는다.
관련 개념을 합친 가족 보고율과 **피처에 허용한 정확한 개념의 커버리지**도 서로 다른 수치다.
현금 가족의 2025→2026 보고율 하락 **94.12% → 56.54%**도 기록했다. 2026년은 미완결 연도이며
표본 구성/계절성/매핑 원인은 미측정이다. 이를 경제적 현금 고갈로 해석하지 않는다.

시장가치·가격 분모를 만들지 않았다. 역사 market cap·economic shareholder yield·배당 수익률은
차단된 가족이다. 전체배당, 계속영업 OCF, 광의 capex/현금은 별도 정의·원본 대사 없이는 대체하지 않는다.

## 후속 연구 설계 — 실행/등록 승인 아님

제안 가설: “영업현금흐름으로 지지되고 과도한 희석 없이 늘어나는 주주 분배는 기존 가격·가치·품질
요인 이상으로 미래 벤치마크 상대 수익에 추가 정보를 포함할 수 있다.”
정책/자본배분 변화, 현재 수익성·Quality 수준, 모멘텀, 섹터/성장 집중, 주식 수 희석,
현금흐름 지속 가능성을 별개로 다룬다. 지급 증가는 이사회 정책 발표의 직접 관측이나 지속 가능성의 증명이 아니다.

미래 primary horizon 제안은 **126 US 거래 세션**이다. 21 세션은 선택적 설명 진단만 제공하며
두 번째 독립 primary 발견으로 취급하지 않는다. 같은 봉인 피처/digest를 SPY와 QQQ에 평가한다.
두 benchmark의 상대 수익은 같은 종목 수익을 공유하므로 독립 확인 두 번으로 부풀리지 않고,
후속 등록에서 claim family와 multiplicity를 미리 정해야 한다. 벤치마크를 바꾸어 좋은 결과를 선택하지 않는다.
가격·membership·label/endpoint 계약은 별도 adapter의 책임이며 이 모듈은 ETF 이름을 입력받지 않는다.

기존 Quality의 ROE/영업·순이익률, 기존 accounting의 OCF/NI·capex intensity·share-count change와
부분 중복한다. OCF 수준은 품질 문맥, 배당/매입 변화는 분배 문맥, 검증된 주식 수 변화는 희석 문맥이다.
나중 구현한다면 redundancy/상관·scaling·missingness/active-column 결정은 **training-only**로 제한한다.
현재 원천의 소액/0 분모, 금융회사 회계 차이, sparse joint coverage와 source-missingness 노출을 별도 보고해야 한다.
분배 회사만 완전 사례로 선정하여 전체 미국 시장 대표성이나 추가 정보를 주장하지 않는다.

`docs/us-source-readiness-v1.md`의 닫힌 역사 탐색 예산을 존중한다. `regional-alpha-model-v1`,
Phase C/D, `alpha-opportunity-model-v5`와 과거 결과를 다시 실행하거나 바꾸지 않았다.
후속 평가의 정식 등록·봉인·소유자 승인·전향 관측은 별도 작업이다. 이 PR은 그 승인이나 실행을 제공하지 않는다.

## 검증·재현·통합

Python 3.12.14에서 저장소의 pinned runtime/dev requirements를 설치하고 `pip check`,
전체 Ruff, `compileall pipeline`, 새 합성 테스트와 기존 Finnhub/PIT 집중 테스트를 실행했다.
최종 새 테스트 **48개**, 기존 검증을 포함한 집중 테스트 **222개** 모두 통과했다.
CI의 Python 3.11 검증 상태는 PR에서 별도로 확인해야 한다.
전체 pytest/seed는 이 작업의 라벨 접근 금지 범위에 맞춰 실행하지 않았다.
기존 전체 suite의 30분 timeout과 CI workflow를 변경하지 않았다.
실제 5개 회사(AAPL/MCD/MSFT/PG/TGT) × 2개 as-of 날짜에서 **32개 원시 숫자 직접 재계산**과
**10개 미래 공시 제거 전/후 digest 비교**도 통과했다. 결과는 새 알파 증거가 아니다.

```bash
cd /workspace/Investment
/workspace/investment-venv/bin/ruff check .
/workspace/investment-venv/bin/python -m pytest -q tests/test_us_shareholder_distribution.py tests/test_finnhub_derive.py tests/test_finnhub_fundamentals.py
/workspace/investment-venv/bin/python scripts/audit_us_shareholder_distribution.py /workspace/us-shareholder-inputs \
  --source-commit 704d7db6d5b00def771aba5d2665d0846d6bc776 --cutoff 2026-10-11 \
  --output docs/us-readiness/us-shareholder-distribution-feature-audit.json
```

감사는 지정 commit/blob manifest와 기존 회계 샤드만 요구한다. 새로운 클라우드 task에 이 외부 입력
디렉터리가 없으면 위 commit의 **회계 blob만** 읽기 전용으로 추출하고 manifest를 만들어야 한다.
outcome/price/replay/신호 파일을 읽는 whole-branch checkout은 필요 없다. 새 수집도 필요 없다.
동작하는 서비스는 없으며 현재 체크아웃을 사용한다. 별도 Git worktree는 요청받은 경우에만 만든다.

Claude adapter가 합쳐지기 전에도 import·테스트·감사가 독립적으로 동작한다.
통합 시 UTC/KST 변환으로 US signal calendar date가 바뀌지 않도록 날짜를 정규화하고,
strict filing-before-day, feature version/digest, 고정 입력 snapshot, 상태별 결측을 보존해야 한다.
당시 universe의 분모/행 선택은 adapter가 별도로 보장하며 이 감사의 이벤트 grid를 그대로 투자 grid로 쓰지 않는다.
주식 수 차단과 낮은 joint coverage, 독립 원본 context 대사 미완료는 통합 시 남는 제한이다.
공유 파일 변경이나 다른 PR의 API를 가정한 선제 wiring은 하지 않았다. 병합/ready 전환 없이 소유자 검토에서 멈춘다.
