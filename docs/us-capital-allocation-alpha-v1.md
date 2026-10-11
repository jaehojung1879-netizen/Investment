# 미국 자본배분 알파 v1 — us-capital-allocation-alpha-v1 (전향적 연구 등록)

**증거 등급:** 커버리지·정의·중복 감사는 `OUTCOME_BLIND`(수익률·라벨·모델 출력·미래 가격을 읽지 않음). 선택 규칙은 **연구 전용**이며
`RESEARCH_US_CAPITAL_ALLOCATION_ALPHA_V1` 네임스페이스에만 기록된다. **역사적 성과 분석은 실행하지 않았다.**
`weekly-passive-first-v1` 공식 주간 판단, `config.json`의 공식 벤치마크(`benchmarks.US = SPY`), 봉인된 KR/US 결과는 바뀌지 않는다.
상태는 `REGISTERED_PENDING_OWNER_APPROVAL`이다. 승인 전에는 실제(LIVE) 영수증을 만들 수 없다(`REGISTERED_AUTHORIZATION = None`).

| 산출물 | 경로 |
|---|---|
| 등록 사양(코드와 1:1) | [`docs/us-capital-allocation/us-capital-allocation-alpha-v1-registration.json`](us-capital-allocation/us-capital-allocation-alpha-v1-registration.json) (설계 다이제스트 `73c347a3…`) |
| 보호 대상 공식 파일 해시 | [`docs/us-capital-allocation/protected-official-files.json`](us-capital-allocation/protected-official-files.json) |
| 주간 PIT 커버리지 감사 | [`docs/us-readiness/us-capital-allocation-weekly-coverage-v1.json`](us-readiness/us-capital-allocation-weekly-coverage-v1.json) + `data/research/us-capital-allocation-alpha-v1/weekly-funnel-by-date.csv.gz` |
| 정의 감사 | [`docs/us-readiness/us-capital-allocation-definition-audit-v1.json`](us-readiness/us-capital-allocation-definition-audit-v1.json) |
| 기존 피처와의 중복 감사 | [`docs/us-readiness/us-capital-allocation-feature-overlap-v1.json`](us-readiness/us-capital-allocation-feature-overlap-v1.json) |
| S&P 500 스냅샷별 섹터 증거(195/195 해시 검증) | `data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz` |
| 코드 | `pipeline/us_capital_allocation_{policy,coverage,weekly,receipts,evaluation}.py` |
| 감사·등록 스크립트 | `scripts/audit_us_capital_allocation_{coverage,definitions,overlap}.py`, `scripts/acquire_us_sp500_snapshot_sectors.py`, `scripts/build_us_capital_allocation_registration.py` |

결과 파일은 `docs/results/`가 아닌 `docs/us-readiness/`, `docs/us-capital-allocation/`에 둔다 — Phase C 등록이 `docs/results/` 전체를 고정하기 때문.
`.github/workflows/tests.yml`, 워크플로 파일, `AGENTS.md`, `probes.yml`, `workflow-inventory.md`, `research_specs/`는 건드리지 않았다.

## 1. 결론 먼저

1. **질문:** "미래 순수익이 SPY나 QQQ를 들고 있는 것보다 나을 것으로 정당화되는 미국 종목을 최대 5개까지 찾을 수 있는가?"
   이 PR은 그 질문에 **답하지 않는다.** 답을 얻을 수 있는 전향적 실험을 사전 등록하고, 기록·평가 장치를 만든다.
2. **주간 PIT 피처 가용성은 낮다.** 715개 주간 신호일 × S&P 500 구성원 = 359,526 멤버-일 중 네 개 핵심 피처가
   **동시에 측정된 비율은 17.9%** (공시가 보이는 멤버-일 기준 21.6%). 가장 큰 손실은 정확한 개념(exact concept) 규칙에서 온다
   (§6). 2016년부터는 매주 측정 종목이 49개 이상이라 최소 40개 바닥을 넘는다. 2013~2015년 110주는 바닥 미만(BLOCKED).
3. **희석(dilution)은 검증할 수 없다.** 기말 발행주식수가 있는 공시가 1.8%뿐이라 `sharesOutstandingChangeYoY`는 전 기간 `BLOCKED`.
   가설의 "과도한 희석 없음" 부분은 **등록하되 게이트로 쓰지 않고 `UNVERIFIED_SOURCE_BLOCKED`로 명시**한다. 연구 결과를 "희석 조정" 주장으로 읽을 수 없다.
4. **기존 가격·품질 피처와의 중복은 없다**(어느 쌍도 |평균 순위상관| ≥ 0.70이 아님). 다만 가치(value) 피처는 기존 행렬이
   스스로 제외하고 있어 **측정하지 못했다**(`NOT_MEASURED`).
5. **등록한 규칙은 사실상 항상 5종목을 고른다**(BLOCKED가 아닌 605주 모두 5종목). 임계값은 개수를 보기 전에 고정했다. 이것을 숨기지 않고
   소유자 결정 사항(D2)으로 올린다.
6. **SPY와 QQQ는 같은 종목·같은 평가일·같은 순위로 비교**한다. QQQ 상대 알파는 SPY 상대 알파에서 (R_QQQ − R_SPY)를 뺀 항등식이므로
   순위·IC는 벤치마크에 불변이다. 벤치마크 변경을 종목 선택 알파로 해석하지 않는다.
7. **공식 주간 판단은 승격하지 않는다.** 후보 신호는 별도 네임스페이스·별도 원장에만 쌓인다.
8. **소유자 승인 준비 상태:** 검토 가능(READY FOR OWNER REVIEW), 단 §11의 결정 6건이 필요하다. LIVE 권한은 등록되지 않았고 예약 발행은 시작되지 않았다.

## 2. 등록 가설 (H126)

- **경제 가설:** 주주 현금 분배(배당 + 자사주 매입)를 **실질적으로** 늘린 기업은, 그 증가가 영업현금흐름(OCF)으로 뒷받침되고 과도한 희석이 없다면,
  기존 가격 모멘텀·가치·품질에 이미 담기지 않은 정보를 가져, **다음 126세션 동안 패시브 지수 대비 수익률**에 대한 정보를 가질 수 있다.
- **단일 주 가설(primary):** 사전 선언한 정책 `P1_STOCKS`가 비용 차감 후 126세션 수익률에서 **SPY와 QQQ를 모두** 이긴다(같은 신호 주, 같은 선택 종목).
- **주장하지 않는 것:** 희석 조정 분배 성장, 21세션 주장(기술 통계만), SPY→QQQ 변경에서 오는 선택 알파.
- **신호일:** 완료된 각 달력 주의 마지막 미국 거래일 종가. **진입** 다음 거래일 종가(실행 세션 0), **청산** 실행 세션 이후 126번째 거래일 종가.
  수익률 기준은 as-traded 순방향 총수익(`price_adjustment.to_total_return`), 원천징수 세금 전.
- **유니버스:** 신호일 *이전*의 최신 S&P 500 스냅샷(PIT, 동일일 사용 안 함). 퇴출 종목은 구성원이던 동안 단면에 남는다.
  나스닥100 완전 구성원은 필요 없다(S&P 500 유니버스는 SPY·QQQ 양쪽 비교에 유효).

## 3. 피처 정의 (#220 `US_SHAREHOLDER_DISTRIBUTION_V1`, 변경 없음)

| 피처 | 정의 |
|---|---|
| `totalCashDistributionTTM` (D) | 배당 지급(`PaymentsOfDividendsCommonStock`) + 자사주 매입(`PaymentsForRepurchaseOfCommonStock`) 의 TTM. 두 개념 모두 **정확히 일치하는 개념만** 허용, 한쪽이라도 없으면 측정 안 함 |
| `totalCashDistributionChangeYoY` (g) | 같은 회계 단계의 현재 TTM / 전년 TTM − 1. 전년 TTM이 0이면 `NOT_APPLICABLE`(+100%도 0%도 아님) |
| `operatingCashFlowTTM` | `NetCashProvidedByUsedInOperatingActivities` TTM. OCF ≤ 0이면 비율을 만들지 않음 |
| `distributionToOCF` | D / OCF |
| 파생 `incrementalDistributionOverOCF` | (D − D/(1+g)) / OCF = `distributionToOCF` × g / (1+g) — **증가분이 OCF의 몇 %인가** |
| 희석 `sharesOutstandingChangeYoY` | `BLOCKED` (원천에 기말 주식수 문맥이 없음). 게이트 아님 |

TTM은 회계연도 누적(fiscal-YTD) 롤포워드(`finnhub_derive.trailing_twelve_months`)로만 만들고 최근 4개 분기를 더하지 않는다.
누락 ≠ 0: `NOT_REPORTED`, `REPORTED_ZERO`, `AMBIGUOUS_ACCOUNTING`, `INSUFFICIENT_HISTORY`, `BLOCKED`는 서로 다른 상태로 유지된다.

### 정의 감사 결과 (`us-capital-allocation-definition-audit-v1.json`, 정의 변경 제안 없음)

- **정정 공시 연대기:** 288개 슬롯(같은 회계기간에 둘 이상의 공시) 전부 검사. 실패 0. `as_of(T)`는 `max(availableFrom, acceptedDate) < T`인 공시만 보고,
  나중 공시는 *보이게 된 뒤에야* 같은 슬롯을 대체한다. 같은 날 쌍 19건은 수락 시각 순서로 처리.
- **누적 의미:** OCF·배당·자사주 개념 모두 `CUMULATIVE_CORROBORATED`(Q2/Q1, Q3/FY 등 비율의 중앙값이 누적 의미와 일치).
- **배당:** 공시의 약 41%만 정확한 보통주 개념(`EXACT_COMMON` 35.6%, 우선주 병기 포함 5.7%). 27.0%는 `ONLY_GENERAL`(일반 지급 개념만), 26.7%는 개념 없음.
  일반 개념은 *허용하지 않았다*(보통주 배당과 다를 수 있음).
- **자사주:** 정확한 개념이 68.7%. 다른 매입 태그는 있지만 허용하지 않았고, 정확한 태그가 없으면 `NOT_REPORTED`이지 0이 아니다.
- **OCF:** 86.5% 정확, 12.6%는 계속사업 OCF만 있음(허용하지 않음), 0.9% 없음.
- **희석:** 기말 주식수 공시 619건(1.77%), 가중평균 주식수 공시 74.3%. 가중평균은 대체재가 아니다. 최소 보완책은 *문맥(기말일·주식 종류·분할 기준)이 있는 공시별 기말 주식수 원천*을 커밋 고정·해시로 확보하는 것.

## 4. 선택 정책 `US_CAPITAL_ALLOCATION_SELECTION_V1` (결정론적, 0~5종목)

게이트는 순서대로 적용하며 처음 실패한 단계를 기록한다.

| 순서 | 게이트 | 규칙 |
|---|---|---|
| 1 | `NOT_PRICED_OR_STALE_PRICE` | 신호일 이전 또는 당일 양의 종가, 10일 이내, 이전 272세션 이상 |
| 2 | `SECTOR_UNKNOWN` | 멤버십 스냅샷(또는 이전 스냅샷)이 11개 섹터명 중 하나를 게시 |
| 3 | `SECTOR_EXCLUDED` | 금융·부동산 제외(OCF·분배 정의가 다름) |
| 4 | `REPORT_ABSENT_OR_STALE` | 신호일 이전 공시가 보이고 보고기간 종료 후 180일 이내 |
| 5 | `FEATURES_NOT_MEASURED` | 네 피처 모두 측정, OCF > 0 |
| 6 | `DISTRIBUTION_INCREASE_NOT_MATERIAL` | g ≥ 0.10 **그리고** `incrementalDistributionOverOCF` ≥ 0.02 |
| 7 | `DISTRIBUTION_NOT_COVERED_BY_OPERATING_CASH_FLOW` | D/OCF ≤ 1.0 |

순위는 `incrementalDistributionOverOCF` 내림차순, 동률은 티커 오름차순. 종목당 15%(최대 5종목), 같은 섹터 최대 2종목, 나머지는 **잔여자산 SPY**
(현금 없음, 유지 보너스 없음, 최적화한 모수 없음). 한 주에 측정 종목이 40개 미만이면 `BLOCKED`(영수증에 개수만 기록, 종목별 신호·비중 없음; 평가에서는 100% SPY로 취급).

**임계값(0.10, 0.02, 1.0, 180일, 40개)은 과거 수익률을 보기 전에 고정했고 과거 승자에 맞춰 조정하지 않았다.** 커버리지 감사는 개수만 센다.

**세 가지 대안(동일 신호 주·동일 선택 종목·동일 평가일):**
`P0_SPY` 100% SPY / `P0_QQQ` 100% QQQ / `P1_STOCKS` 0~5종목 15%씩 + 잔여 SPY. 순위 계산은 한 번만 하고 두 벤치마크가 공유한다.

**비용 가정**(`benchmark_alpha.REALISTIC_COSTS['US']`, 공식 주간 정책의 `switchCost` 관례): 수수료 편도 5bp, 스프레드 6bp, 매도세 0.3bp →
왕복 16.3bp. 종목 1단위 전환 비용 = 종목 왕복 + 대체되는 ETF 왕복 = 32.6bp.

## 5. SPY / QQQ 비교 평가 설계

- 공식 벤치마크는 **SPY**, QQQ는 **추가 패시브 대안**. 둘 다 같은 봉인 매니페스트(`replay-v16`, #221의 `SealedReader`)에서 읽는다.
- 항등식: `alpha_QQQ = alpha_SPY − (R_QQQ − R_SPY)`. 같은 날짜 안에서 상수이므로 순위·IC는 벤치마크에 불변이다.
  따라서 `theta_QQQ = theta_SPY − mean(R_QQQ − R_SPY)`; 수동 성장 스프레드는 따로 보고하며 재순위화하지 않는다.
- **단일 주장 = 두 단측 검정의 교집합.** 각각 5%에서 둘 다 통과해야 하므로 가족 오류율은 5% 이하 → 이 주장에 다중비교 보정은 필요 없다.
  보조 진단(분해, 성장 적재량, 선택 귀무, 순위 정보, H21 기술 통계)은 서로 Holm 보정하며 **판정 권한이 없다.**
- **겹치는 창 보정:** 인접한 주간 126세션 창은 121세션을 공유한다. 주 단위 평균의 **원형 이동 블록 부트스트랩**(블록 26주, 10,000회, 시드 20261011, 단측 95%).
  독립 창 수 = 성숙한 주 // 26.
- **성숙 게이트:** 성숙 신호 ≥ 100, 독립 창 ≥ 12(≈ 6년 이상), 모의 거래일 ≥ 252. 그 전에는 `NOT_YET_EVALUABLE`이며 통계는 기술용.
  **첫 공식 판정은 약 2033년경**, 달력 한도는 2035-12-31.
- **판정:** SUCCESS = 두 하한 > 0, 미해결 종료 결과 없음, 성숙 주의 10% 이상에서 1종목 이상 보유. FAILURE = 어느 한 상한 < 0.
  그 외 INCONCLUSIVE(미해결 종료 결과가 있으면 판정 보류). **단일 판독:** 게이트에서의 첫 판정이 판정이다.
- **상장폐지·미해결:** 보유 종목이 청산가 없이 거래 중단되면 포트폴리오 결과는 `None`(마지막 가격도 0도 아님). 종료 대가가 인용될 때만 `TERMINAL_CONSIDERATION_CITED`.

## 6. 주간 PIT 커버리지 (715주, 359,526 멤버-일, 2013-01-04 ~ 2026-09-11)

단위는 *공시 이벤트가 아니라 주간 관측일 × 해당 시점 S&P 500 구성원*이다. 한 멤버-일은 아래 퍼널에서 **처음 실패하는 단계 하나**로만 분류된다.
같은 `classify_member`가 향후 주간 영수증에도 쓰이므로 감사된 커버리지와 전향적 결정이 어긋날 수 없다.

| 처음 실패한 단계 | 멤버-일 | % |
|---|---|---|
| 식별 모호(티커 재사용·CIK 불일치 등) (`IDENTITY_AMBIGUOUS`) | 7,260 | 2.0193 |
| 가격 패널 없음 (`NO_PRICE_PANEL`) | 46,934 | 13.0544 |
| 가격 이력 272세션 미만 (`PRICE_HISTORY_INSUFFICIENT`) | 3,143 | 0.8742 |
| 마지막 가격이 10일 초과 (`PRICE_STALE`) | 0 | 0.0 |
| 펀더멘털 기록 없음 (`NO_FUNDAMENTAL_RECORD`) | 297 | 0.0826 |
| 신호일 이전 공시 없음 (`NO_VISIBLE_FILING`) | 3,764 | 1.0469 |
| 보고기간 종료 후 180일 초과 (`REPORT_STALE_OVER_180_DAYS`) | 6,409 | 1.7826 |
| 네 핵심 피처 중 하나 이상 미측정 (`FEATURES_NOT_MEASURED`) | 227,310 | 63.2249 |
| **네 피처 동시 측정** (`JOINT_MEASURED`) | 64,409 | 17.915 |

공시가 보이는 멤버-일(분모 298,128) 기준 동시 측정 비율 = **21.6045%**. 가격 적격 멤버-일은 302,189.

미측정(`FEATURES_NOT_MEASURED`)의 주된 이유(첫 막힌 피처):

| 이유 | 멤버-일 |
|---|---|
| `totalCashDistributionTTM:AMBIGUOUS_ACCOUNTING` | 104,004 |
| `totalCashDistributionTTM:NOT_REPORTED` | 88,576 |
| `operatingCashFlowTTM:AMBIGUOUS_ACCOUNTING` | 9,898 |
| `totalCashDistributionChangeYoY:INSUFFICIENT_HISTORY` | 6,949 |
| `totalCashDistributionTTM:INSUFFICIENT_HISTORY` | 6,007 |
| `totalCashDistributionChangeYoY:NOT_REPORTED` | 5,273 |
| `totalCashDistributionTTM:INVALID` | 3,856 |
| `totalCashDistributionChangeYoY:AMBIGUOUS_ACCOUNTING` | 1,450 |

### 연도별

| 연도 | 멤버-일 | JOINT_MEASURED % | FEATURES_NOT_MEASURED % | NO_PRICE_PANEL % | IDENTITY_AMBIGUOUS % | 주간 측정 종목 중앙값 | BLOCKED 주 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2013 | 26000 | 0.7923 | 64.7385 | 25.9 | 4.4231 | 5 | 52 |
| 2014 | 26007 | 7.8248 | 58.9495 | 24.2973 | 4.345 | 35 | 42 |
| 2015 | 26258 | 11.0785 | 57.3235 | 23.1015 | 3.9226 | 49 | 16 |
| 2016 | 26138 | 13.6009 | 59.029 | 19.6993 | 2.9765 | 58 | 0 |
| 2017 | 26251 | 14.8985 | 60.771 | 18.1631 | 2.2475 | 60 | 0 |
| 2018 | 26260 | 16.6222 | 61.8241 | 16.0891 | 1.8812 | 68 | 0 |
| 2019 | 26260 | 20.4037 | 59.4935 | 15.4455 | 1.7822 | 84 | 0 |
| 2020 | 26765 | 22.7312 | 61.3264 | 11.8438 | 1.2741 | 92 | 0 |
| 2021 | 26260 | 23.2369 | 64.8363 | 8.3283 | 0.9063 | 94 | 0 |
| 2022 | 26258 | 24.0155 | 63.4816 | 7.8528 | 0.7845 | 97 | 0 |
| 2023 | 26151 | 24.5 | 66.2804 | 3.8737 | 0.8604 | 97 | 0 |
| 2024 | 26154 | 23.1246 | 67.0643 | 2.6726 | 0.9444 | 91 | 0 |
| 2025 | 26155 | 23.4754 | 71.6957 | 1.5943 | 0.7953 | 92 | 0 |
| 2026 | 18609 | 26.7774 | 70.5089 | 0.3708 | 0.8329 | 98 | 0 |

### 섹터별

| 섹터 | 멤버-일 | JOINT_MEASURED % | FEATURES_NOT_MEASURED % | NO_PRICE_PANEL % | IDENTITY_AMBIGUOUS % |
| --- | --- | --- | --- | --- | --- |
| Communication Services | 9949 | 5.3674 | 56.478 | 21.7409 | 10.6945 |
| Consumer Discretionary | 50728 | 15.5102 | 62.5572 | 14.972 | 3.3492 |
| Consumer Staples | 25841 | 20.2314 | 63.705 | 13.5715 | 0.0503 |
| Energy | 21773 | 18.5229 | 45.5381 | 26.3216 | 6.5953 |
| Financials | 52807 | 22.6296 | 61.4085 | 9.4022 | 1.0699 |
| Health Care | 42670 | 15.9597 | 63.6419 | 16.9182 | 0.4523 |
| Industrials | 50200 | 27.1952 | 61.0717 | 8.8028 | 1.1255 |
| Information Technology | 49467 | 13.8658 | 67.447 | 13.605 | 2.3288 |
| Materials | 19437 | 22.8585 | 56.4439 | 16.2319 | 0.0 |
| Real Estate | 15348 | 5.675 | 78.5119 | 3.7725 | 0.4431 |
| UNCLASSIFIED | 146 | 0.0 | 42.4658 | 41.7808 | 0.0 |
| Utilities | 21160 | 10.2127 | 79.8251 | 3.828 | 2.3866 |

### 피처 계열·피처별 상태(공시가 보이는 신선한 보고서 기준)

| 계열 | 피처 | VALID | REPORTED_ZERO | NOT_REPORTED | AMBIGUOUS_ACCOUNTING | INSUFFICIENT_HISTORY | INVALID | NOT_APPLICABLE | BLOCKED |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| capexAndCash | capitalExpendituresTTM | 62.8% | 0.0% | 10.9% | 22.5% | 2.7% | 1.2% | - | - |
| capexAndCash | cashAndCashEquivalents | 86.1% | 0.0% | 13.4% | 0.0% | - | 0.4% | - | - |
| dilution | shareCountReductionIndicator | - | - | - | - | - | - | - | 100.0% |
| dilution | sharesOutstandingChangeYoY | - | - | - | - | - | - | - | 100.0% |
| dividends | cashDividendsPaidTTM | 42.4% | 0.1% | 18.7% | 35.7% | 2.1% | 1.1% | - | - |
| dividends | cashDividendsPaidTTMChangeYoY | 37.0% | 0.3% | 19.3% | 36.3% | 5.8% | 1.3% | 0.1% | - |
| operatingCashFlow | operatingCashFlowTTM | 80.0% | 0.0% | 0.9% | 14.1% | 3.8% | 1.2% | - | - |
| repurchases | commonStockRepurchasesTTM | 63.0% | 2.8% | 29.8% | - | 2.6% | 1.8% | - | - |
| repurchases | repurchasesTTMChangeYoY | 54.4% | 0.2% | 34.0% | - | 7.7% | 2.3% | 1.3% | - |
| support | distributionCoverageByOCF | 25.9% | - | 25.4% | 43.1% | 3.8% | 1.5% | 0.2% | - |
| support | distributionToOCF | 25.9% | 0.0% | 30.4% | 40.1% | 2.1% | 1.3% | 0.2% | - |
| totalDistribution | totalCashDistributionChangeYoY | 25.6% | 0.0% | 32.2% | 36.1% | 4.4% | 1.6% | 0.0% | - |
| totalDistribution | totalCashDistributionTTM | 30.6% | 0.0% | 30.4% | 35.7% | 2.1% | 1.3% | - | - |

**읽는 법.** `VALID`가 아닌 상태는 모두 "값 없음"이다. `NOT_REPORTED`(원천에 정확한 개념이 없음)와 `REPORTED_ZERO`(0으로 보고)를 섞지 않았고,
`AMBIGUOUS_ACCOUNTING`(예: 보통주 배당을 일반 지급 개념과 구분할 수 없음)과 `INSUFFICIENT_HISTORY`(전년 TTM 연결에 필요한 앵커 부족)도 분리해 보관한다.

### 기업별

구성원이었던 기업 827개 중 **한 주도 측정되지 않은 기업 591개**, 그 첫 실패 단계: `FEATURES_NOT_MEASURED` 214, `NO_PRICE_PANEL` 183, `REPORT_STALE_OVER_180_DAYS` 121, `IDENTITY_AMBIGUOUS` 38, `PRICE_HISTORY_INSUFFICIENT` 26, `NO_VISIBLE_FILING` 9.

구성원 기간 52주 이상인 771개 중 절반 이상의 주에서 측정된 기업은 106개. 측정 주 수 상위: ADI(668/715), EMR(656/715), LMT(656/715), TEL(656/715), COF(655/715), TMO(642/715), MCK(637/715), PRU(629/715), GWW(623/715), NTRS(620/715).


전 종목의 주 단위 분류는 JSON의 `summary.companies`에 있다(첫 실패 단계, 주 수, JOINT_MEASURED 주 수).

### 선택 가능성(결과 없음, 개수만)

| 항목 | 값 |
|---|---|
| 주간 결정 | BLOCKED 110, CANDIDATE_PORTFOLIO 605 |
| 주당 선택 종목 수 | 0종목 110주, 5종목 605주 |
| 게이트 통과 종목/주 | 중앙값 19, 최대 54 |
| 섹터 상한으로 건너뛴 종목 | 344 |
| 선택된 종목의 섹터 분포 | Industrials 858, Health Care 469, Consumer Staples 415, Consumer Discretionary 408, Information Technology 332, Energy 299, Materials 171, Utilities 42, Communication Services 31 |

개수만 센 것이며, 규칙은 어떤 수익률도 보지 않았다. 설계 다이제스트 `73c347a3…`.


## 7. 기존 가격·가치·품질 피처와의 중복 (수익률 없이)

신호일 13주마다 1개(50개 날짜, 4,960행)에서 후보 피처와 기존 `regional_alpha_features`/`fundamental_acceleration` 피처의 **단면 순위상관**과 순위 R²를 계산했다.
어떤 수익률·라벨·미래 가격도 읽지 않는다(기존 피처 함수가 신호일 이후 가격을 거부).

- 플래그(|평균 ρ| ≥ 0.70)된 쌍: **없음.**
- 후보 `incrementalDistributionOverOCF`의 순위가 모든 기존 피처 순위로 설명되는 비율(조정 R²) **약 6.5%**. `distributionToOCF`는 약 20%(대부분 품질 계열 19%).
- 품질 계열과의 가장 큰 상관은 `earningsGrowth`(ρ ≈ 0.20), `roe`(≈ 0.13); 가격 모멘텀·위험·리더십과는 |ρ| < 0.05.
- **가치:** `NOT_MEASURED`. 기존 행렬이 earningsYield/bookYield/fcfYield(주당 분자의 가격 기준 미해결)와 시가총액(PIT 아님)을 스스로 제외한다. 후보 피처는 OCF 대비 비율이라 가격 기준 가치 비율이 아니다.
- 선택 규칙이 고른 종목의 기존 피처 백분위 프로파일은 대체로 0.5 근처(기술용).

상관이 낮다는 것은 *다른 정보를 담았다*는 뜻일 뿐, *예측력이 있다*는 뜻이 아니다.

## 8. 전향적 영수증과 평가 준비 상태

- **영수증**(`pipeline/us_capital_allocation_receipts.py`): 추가 전용 JSONL `ledger/research/us-capital-allocation-alpha-v1/receipts.jsonl`. 신호일마다 한 행.
  입력 정체성(펀더멘털 샤드, 멤버십 스냅샷, 가격 스냅샷, 섹터 증거), 선택된 종목의 **PIT 증거**(모든 입력 공시의 `availableFrom`/`acceptedAt`, 피처 다이제스트),
  선택 상태·사유·탈락 사유, **관측 시점에 이용 가능한 가격**(신호 세션 종가만, 종가 이후·영수증 이전에 조회), 비용 가정, 코드·사양 해시를 담는다.
  `officialWeeklyDecisionAffected = false`, `weekly-decisions` 경로 쓰기는 거부된다.
- **LIVE vs SYNTHETIC:** 실제 경로는 `REGISTERED_AUTHORIZATION`(현재 `None`)을 요구하고 사양·코드·데이터 해시를 git에서 직접 검증한다. 합성 경로는 테스트 전용이며 증거 등급이 다르다.
- **타이밍:** 신호일은 미국 거래일·주간 신호 세션이어야 하고, 영수증은 종가 확정 이후, 다음 세션 개장 이전이어야 하며, 병합일은 제외하고 그다음 세션부터 전향적이다.
- **평가**(`pipeline/us_capital_allocation_evaluation.py`): 성숙 전에는 결과 레코드 생성을 거부한다. 존재하지 않는 결과를 만들지 않는다. 쌍별 비교(`P1` vs `P0_SPY`, `P0_QQQ`),
  블록 부트스트랩, 성장 적재량, 선택 귀무를 갖췄고, 합성 입력 테스트만 통과했다.
- **주간 조립**(`pipeline/us_capital_allocation_weekly.py`): `observe_week`가 감사와 같은 `classify_member`로 결정을 만들고, `price_row`가 신호 세션 종가를 영수증용으로 포장한다(없는 세션은 이전 종가로 대체하지 않음).

## 9. 한계 (숨기지 않는다)

1. **측정 가능 비율이 낮다**(17.9% / 21.6%). 정확한 개념 규칙은 보수적이다. 자사주만 하는 기업과 배당 개념이 모호한 기업은 구조적으로 측정되지 않는다 — 즉 가설은 **"측정 가능한 하위 모집단"**에만 해당한다.
2. **희석 미검증**(§1-3).
3. **2013~2015년 110주는 BLOCKED**(측정 종목 40개 미만). 그 전 구간은 이 연구의 전향적 관측과 무관하지만 커버리지 이력으로 보고한다.
4. **규칙이 거의 항상 5종목을 고른다**(605/605). 변별력이 낮을 수 있다. 임계값을 개수를 보고 바꾸지 않았다.
5. **섹터 라벨**: 3,489 멤버-일은 이전 스냅샷에서 이월(미래 스냅샷은 읽지 않음), 146 멤버-일은 라벨 없음(`SECTOR_UNKNOWN`).
6. **식별 모호 종목**(ticker 재사용, CIK 불일치 등)은 후보가 아니다(`IDENTITY_AMBIGUOUS`, 2.0%). 퇴출·상장폐지 종목은 구성원 기간 동안 단면에 남지만 가격 패널이 없는 종목은 `NO_PRICE_PANEL`(13.1%)로 남는다 —
   **상장폐지로 사라진 종목의 누락을 무시하지 않았고, 생존 편향은 이 숫자들에 그대로 남아 있다.**
7. **전향 데이터 의존:** 주간 실행에는 (a) Finnhub 일일 수집(`fundamentals.yml`), (b) S&P 500 멤버십 스냅샷 갱신, (c) 종가 조회가 필요하다. 이 PR은 새 워크플로를 만들지 않았다(워크플로 센서스가 고정되어 있음).
8. **첫 판정은 2033년경**이다. 그때까지의 숫자는 기술용이다.
9. 이 환경에서 실제 CI 전체를 완주하지는 못했다(별도 에이전트가 30분 타임아웃을 수정 중). 보고는 §12 참조.

## 10. 하지 않은 것

- `regional-alpha-model-v1` 재실행, 과거 알파 탐색 재개, 봉인된 KR/US 결과 수정, 과거 승자에 맞춘 피처·임계값 조정, 포트폴리오 정책 반복 시도 → 없음.
- 후보를 공식 주간 포트폴리오로 승격 → 없음. 예약 발행 활성화 → 없음. 과거 성과(outcome) 분석 → 없음. 새 데이터 대량 취득 → 없음
  (섹터 증거만 195개 스냅샷당 요청 1회, 고정 커밋의 해시 검증 후 저장).

## 11. 소유자 승인 체크리스트

| ID | 결정 | 권고 |
|---|---|---|
| D1 | 희석을 `UNVERIFIED_SOURCE_BLOCKED`로 두고 진행할지(희석 조정 주장 불가) | 수용. 기말 주식수 원천은 별도 작업 |
| D2 | 규칙이 사실상 항상 5종목을 고른다는 점. 승인 *전에* 임계값을 강화할지(새 등록 필요) 또는 그대로 갈지 | 변별력이 우려되면 승인 전에 강화. 승인 후에는 변경 불가(새 연구 ID) |
| D3 | 정확한 개념 규칙의 낮은 커버리지를 수용할지, 별도 V2 피처 정의 연구를 승인할지 | 수용 + V2는 별도 사전 등록 |
| D4 | 성숙 게이트(독립 창 12개 ≈ 6년+, 첫 판정 ≈ 2033년)를 수용할지 | 수용. 더 빠른 판정은 증거 기준을 낮추는 것 |
| D5 | 권한 등록(`REGISTERED_AUTHORIZATION`)과 주간 작업을 기존 `ledger.yml`의 한 단계로 추가(새 워크플로 파일은 센서스 때문에 불가) | 승인 시 별도 PR로 |
| D6 | 주간 라이브 입력 3종(Finnhub 일일 수집, 멤버십 갱신, 종가 조회)의 소유와 실패 시 처리 | 실패 주는 영수증 없음이 아니라 BLOCKED 기록 |

등록 커밋이 결과 커밋보다 앞서야 한다 — 이 PR은 등록이고 결과가 아니다.

## 12. 검증

- 신규 테스트: 정책·영수증·평가·주간 조립(합성 종단)·감사 일관성 — `pytest tests/test_us_capital_allocation_*.py`.
- 정적 검사: 신규 코드가 outcome/라벨/모델 코드를 import하지 않음(테스트), 공식 주간 판단 파일 7개의 SHA-256이 `f81be25d…` 기준과 동일함(테스트).
- 재현: `python scripts/audit_us_capital_allocation_coverage.py --workspace <dir> --extract` (약 10분, 결정론적; 행렬 SHA-256이 실행마다 동일), `scripts/audit_us_capital_allocation_definitions.py`, `scripts/audit_us_capital_allocation_overlap.py --matrix …`,
  `python scripts/build_us_capital_allocation_registration.py --check`.
