# kr-selection-challenger-v2-accounting — 시점 정합 회계 정보 전향 Challenger (사전등록)

- **상태:** `PREREGISTERED_PROSPECTIVE_PAPER`. 결과는 아직 없다.
- **고정 명세:** `docs/research-program/specs/kr-selection-challenger-v2-accounting.json`
- **구현:** `pipeline/kr_selection_challenger_v2.py`, `scripts/record_kr_selection_challenger_v2.py`
- **실행:** `scripts/update_ledger.py`가 v1 기록기 다음에 `run_all`을 호출한다. workflow는 바꾸지 않는다.
- **기록:** signal-history `ledger/research-strategies/kr-selection-challenger-v2-accounting/`
- **효과:** `productionEffect: NONE`. 공식 주간 판단, 주문, 실거래 비중과 무관하다.

## 왜 필요한가

v1은 가격 정보(저변동성, 52주 고가)만 쓴다. 현재 생산 빌드는 Yahoo 현재 스냅샷을 쓰며, 시점 정합(PIT) DART 회계를 쓴 적이 없다. 이 연구는 그 회계 정보를 전향적으로 기록한다.

규칙은 `kr_alpha_signal_v2`의 H2다. 적합 모수 없이 다음 두 조건을 본다.
- **저평가:** 업종(섹터) 안에서 순자산/시가총액과 순이익/시가총액의 평균 백분위가 상위 1/3이다.
- **확인:** 순이익, 영업현금흐름, 영업현금흐름 개선(모두 자산 대비)이 모두 0보다 크다.

역사 표본에서 같은 계열(X1)이 측정되었지만, 이 연구는 그 표본을 다시 읽지 않는다.

## 장부

| 장부 | 역할 |
|---|---|
| `CH_VALUE_CONFIRMED` | 저평가 + 확인. 가치 백분위 상위 5종목, 섹터당 최대 2종목 |
| `CTRL_CHEAP_UNCONFIRMED` | 저평가이지만 확인되지 않은 종목. 확인이 수익을 내는지 보는 메커니즘 대조군 |
| `CTRL_MODEL5` | 같은 적격 집합에서 생산 alpha 상위 5종목 |
| `CTRL_ETF` | 069500.KS |

## 입력 (모두 신호 시점의 사실)

- **회계:** `ledger/fundamentals/kr-canonical-v2`의 공시만 쓴다. 신호일보다 엄격히 이전에 공개된 것만 반영하며(`visible_filings`), TTM은 `accounting_values`로 계산한다.
  - 일일 `kr` 저장소는 쓰지 않는다. 2026-10-16 생산 KR 119종목 기준으로 순이익 TTM이 `kr`에서는 24종목, 정규화 저장소에서는 115종목에만 있다.
- **시가총액·섹터:** 생산 cross-section의 값을 쓴다. KRX 종목 시가총액과 등록 업종을 대신하는 명시적 대용치다.
- **우선주:** 종목코드 끝자리가 0이 아니면 우선주로 보고 부적격 처리한다.
- **유동성:** 벤더 일봉을 거래소 달력에 맞춰 판단한다(`kr_bar_integrity`).
  - 최근 20세션을 모두 거래해야 한다.
  - 최근 60세션의 종가×거래량 중앙값이 10억 원 이상이어야 한다.
  - 결측이거나 정지된 세션은 거래한 세션으로 세지 않는다.
- **보유 불가 처리:** 커버리지가 60% 미만이면 모든 장부가 069500.KS만 보유한다(`BLOCKED_COVERAGE`).
- **다운로드 실패:** 일봉을 받은 종목이 절반 미만이면 receipt를 쓰지 않는다. 같은 기록 창의 다음 실행이 다시 시도한다.
- **유동성 근거 기록:** 각 receipt의 `liquidityDiagnostics`에 종목별 20세션 거래 수, 60세션 중앙 거래대금, 60세션의 세션 상태(`SESSION_MISSING` = 거래소는 열렸는데 벤더 행이 없음, `SUSPENDED` = 거래량 0), 휴장일에 찍힌 벤더 행 수(세션으로 세지 않고 버림)를 남긴다. `summary`는 횡단면 집계다. 규칙은 바뀌지 않으며, 첫 실데이터 기록이 유동성 관문을 스스로 검증할 수 있게 하는 기록이다.
- **실행 상태:** v1과 같은 방식이다. 단계마다 `publication-status.<record|outcomes|assess>.json`을 따로 쓰고, `publication-status.json`은 그 셋을 모은 집계다(`failedSteps`, `signalRecordState`). 뒤 단계가 성공해도 앞 단계의 거부나 예외는 남는다.

## 판정 (결과 전 고정, v1과 동일한 틀)

- 해악 중단은 첫 52개 receipt를 H126 기준으로 본다.
- 주판정은 첫 104개 receipt를 쓴다. 다섯 조건을 모두 충족해야 `SUPPORTED`다.
  1. H252 순초과의 단측 97.5% 하한이 0보다 크다.
  2. H126 평균이 0보다 크다.
  3. 기존 모델(`CTRL_MODEL5`)보다 평균이 높다.
  4. **확인되지 않은 저평가 종목(`CTRL_CHEAP_UNCONFIRMED`)보다 평균이 높다.**
  5. 위험 경로의 Sharpe가 069500.KS 이상이고, |MDD|가 069500.KS의 1.25배 이하다.
- 중간 결과는 공개하지 않는다.

## 운영상 확인된 사항

- **정규화 저장소 갱신은 수동이다.** `kr-canonical-v2`는 fundamentals workflow의 `raw-statements` 대상을 수동 실행할 때만 다시 만들어진다. 현재 최신 공시일은 2026-09-16이다.
- **오래된 회계는 미래값으로 채우지 않는다.** 시점 정합성은 유지되고, 각 receipt가 `accountingStore.newestAvailableFrom`을 기록한다.
- **3분기 보고서 이후 갱신이 필요하다.** 3분기 보고서는 11월 중순에 마감된다. 마감 후 소유자가 `raw-statements`를 실행해야 다음 분기 회계가 반영된다.
