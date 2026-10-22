# kr-selection-challenger-v1 — 한국 종목선택 전향 Challenger (사전등록)

- **상태:** `PREREGISTERED_PROSPECTIVE_PAPER`
- **고정 명세:** `docs/research-program/specs/kr-selection-challenger-v1.json`
- **구현:** `pipeline/kr_selection_challenger.py`, `pipeline/kr_bar_integrity.py`, `scripts/record_kr_selection_challenger.py`
- **실행:** `scripts/update_ledger.py`(ledger.yml의 paper-ledger 단계)가 자기 작업 뒤 `run_all`을 호출한다. 예외는 잡아서 paper ledger에 영향을 주지 않는다. workflow 파일은 바꾸지 않았다(`.github/workflows` 트리는 `rp1-wp2-us-universe-v1`이 hash로 고정).
- **예상 주기:** 00:10 cron은 실제로 04:30 UTC 전후(평일 KRX 장중)에 시작하므로 평일 실행은 기록하지 않는다. 토요일 실행이 금요일 세션을 기록하고, 일요일 실행이 같은 기록 창의 예비다.
- **기록 위치:** signal-history `ledger/research-strategies/kr-selection-challenger-v1/` (`receipts.jsonl`, `outcomes.jsonl`, `assessment.json`, `publication-status.json`)
- **실행 상태:** 단계마다 `publication-status.<record|outcomes|assess>.json`을 따로 쓰고, `publication-status.json`은 그 셋을 모은 집계다(`failedSteps`, `signalRecordState`). 뒤 단계가 성공해도 앞 단계의 거부나 예외는 남는다. 연구 단계가 0이 아닌 코드로 끝나거나 예외가 새면 `update_ledger.py`가 workflow 경고를 남기지만, paper ledger의 종료 코드는 바뀌지 않는다.

결과는 아직 없다. 이 연구의 어떤 장부도 공식 주간 판단, 주문, 실거래 비중에 들어가지 않는다(`productionEffect: NONE`).

## 1. 무엇이 새로운가

새로운 것은 정보가 아니라 **증거**다.
- 두 가설의 정보 계열은 종료된 한국 역사 연구(kr-alpha-atlas, Phase D 지명 0건)가 이미 측정했다. 저변동성(F01/F02)과 52주 고가 근접(A11)이며, 판독은 결론 없음이었다.
- KR lowvol은 지역 단독 판독 중 유일하게 0을 넘었다(v2.21, 보조 판독이지 발견이 아님).
- 역사 표본은 이미 소진되었고 이 연구는 그것을 다시 읽지 않는다.
- 모든 신호는 그 신호가 설명하는 종가 시점에 기록되고, 지평이 만기된 뒤에만 채점된다. 두 가설이 만들어질 때 존재하지 않던 표본이다.

## 2. 장부 (매주 KR 주간 판단 세션, 같은 산출물·같은 유니버스)

| 장부 | 역할 | 규칙 |
|---|---|---|
| `CH_LOWVOL` | Challenger | 252일 하방변동성(`risk.downsideVolPct`)이 가장 낮은 5종목 |
| `CH_HIGH52` | Challenger | 200일 평균 위 종목 중 종가/52주 최고가(`pct52wHigh`)가 가장 높은 5종목 |
| `CTRL_MODEL5` | 기존 모델 대조군 | 생산 4-sleeve alpha 상위 5종목(동일 유니버스·동일 상한) |
| `CTRL_ETF` | 수동 대조군 | 069500.KS |

- **공통 규칙**
  - 장부는 5개 동일 슬롯으로 구성하고, 섹터당 최대 2종목이다. 빈 슬롯은 069500.KS로 채운다.
  - 적격 종목이 30개 미만이면 종목을 담지 않는다(`THIN_CROSS_SECTION`).
  - 순위가 같으면 종목코드 오름차순으로 정한다.
- **유니버스**
  - 생산 산출물 `longTerm.regions.KR.validationCrossSection`을 쓴다. 실데이터 최근 거래일 기준 118종목이다.
  - 신호일 시세가 아니거나 종가·특징이 없는 종목은 그 장부에서만 제외하고 사유별로 센다. 대체하거나 0으로 채우지 않는다.
- **산출물 조건**
  - `^KS11` 세션은 산출물 생성 시점에 최종(18:00 KST)이던 마지막 세션과 같아야 한다.
  - 기록 시각은 기록자 자신의 시계로 신호 세션 18:00 KST 이후, 다음 세션 개장 전이어야 한다.
- **승인 시점**
  - 이 명세를 추가한 PR의 병합이 곧 승인이다.
  - 첫 신호는 병합한 KST 날짜보다 뒤의 첫 주간 판단 세션이며, 등록 하한 2026-10-30보다 이르지 않다.
  - 병합 시각은 main의 first-parent 이력에서 읽는다. 이력을 읽지 못하면 기록을 거부한다.

## 3. 채점 (만기 후에만, 별도 기록)

- **지평:** H126, H252 세션. 체결은 신호 다음 세션 종가(세션 0)다.
- **가격:** 채점 시점 1회 다운로드한 벤더 수정종가를 양쪽 다리에 쓰고, `kr_bar_integrity`로 거래소 달력에 정렬한다.
- **결측 처리**
  - 체결 세션에 거래정지(거래량 0)인 종목은 살 수 없으므로 해당 슬롯을 069500.KS로 유지한다. 체결 시점에 알 수 있는 사실이다.
  - 다음 경우에는 그 장부·코호트 결과가 None이다. 이전 종가로 대체하거나, 제외하거나, 재정규화하지 않는다.
    - 벤더 자료가 없거나, 행이 없거나, 체결 시 종가가 무효인 경우
    - 만기 세션 자체에 거래되지 않은 경우
- **비용:** `weekly_decision.trade_cost_fraction`의 일자별 KR 비용을 쓴다. 수수료와 스프레드 절반, 주식 매도 시 증권거래세, ETF 매도에는 세금이 없다.
- **순초과수익:** 069500.KS 대조군도 자기 왕복비용을 낸다.

## 4. 판정 규칙 (결과 전 고정)

- **중간 공개 없음:** 등록된 검정 전에는 결과 통계를 공개하지 않는다. 회전율(신호 시점 사실)만 언제든 보고한다.
- **해악 중단**
  - 첫 52개 receipt가 H126에서 모두 채점된 뒤, 069500.KS 대비 평균 순초과의 Newey-West 95% 상한이 0 미만이면 `STOPPED_HARM`이다.
  - None 결과가 5건을 넘으면 `INCONCLUSIVE_DATA`다.
- **주판정 (첫 104개 receipt, 약 3년)**
  - 다음 네 조건을 모두 충족하면 `SUPPORTED`, 하나라도 못 미치면 `NOT_SUPPORTED`다.
    1. H252 평균 순초과의 단측 98.75% 하한(두 challenger Bonferroni)이 0보다 크다.
    2. H126 평균 순초과가 0보다 크다.
    3. `CTRL_MODEL5` 대비 H252 평균이 0보다 크다.
    4. 4주 리밸런스 일별 페이퍼 경로의 Sharpe가 069500.KS 이상이고, |MDD|가 069500.KS의 1.25배 이하다.
  - None이 10건을 넘거나 위험 경로가 불완전하면 `INCONCLUSIVE_DATA`다.
- **판정 이후**
  - `SUPPORTED`도 소유자 결정을 위한 개발 증거일 뿐 자동 승격이 아니다.
  - `NOT_SUPPORTED`나 `STOPPED_HARM`이면 이 버전은 닫힌다. 규칙을 바꾸려면 새 버전이 필요하다.

## 5. 데이터 무결성 (Task 3, `pipeline/kr_bar_integrity.py`)

#263 실데이터 감사(2026-10-21)에서 확인한 결함을 전향 기록의 읽기 경로에서 명시적 결측으로 처리한다. 봉인된 리더(`krx_prices`, `kr_alpha_atlas_bars`)와 저장 원본은 바꾸지 않았다.

| 결함 | 처리 |
|---|---|
| 거래량 > 0인데 OHL = 0 (8행) | `RANGE_UNRESOLVED`: 고가·저가·시가는 결측, 종가는 유지 |
| done이지만 행이 없는 개장일 (2026-09-15·16) | 달력 정렬 시 `SESSION_MISSING`. 그 세션을 포함하는 창은 미완성이며, 행 순서로 창을 늘리지 않는다 |
| 비유한값·음수 거래량·고가<저가 | `CLOSE_INVALID` / `RANGE_UNRESOLVED` |
| 거래정지 (거래량 0) | `SUSPENDED`: 거래 세션이 아니며 종가를 쓰지 않는다 |
| 휴장일 행 | 세션에서 제외하고 `offCalendarRows`로 센다 |

`store_session_gaps`는 수집기 done 마커와 저장 행을 대조해 공백을 보고만 한다. 재수집과 수선은 이용권(B1) 판단에 달린 별도 결정이다.

## 6. 한계

- 생산 유니버스는 현재 시가총액 상위 120이다. 전향적으로는 시점 정합적이지만, `dataInsufficient` 제외를 그대로 물려받는다.
- 펀더멘털은 Yahoo 현재 스냅샷이다. 두 challenger는 가격 정보만 쓴다.
- 수정종가의 배당 기준은 벤더 의존이며 양쪽 다리에 같은 기준을 쓴다.
- 주판정까지 약 3년이 걸린다. 기다리는 동안 규칙을 바꾸면 새 버전이 필요하다.
