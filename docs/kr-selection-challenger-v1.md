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

## 7. 독립 감사(2026-10-22) 이후 보강

결과가 나오기 전의 변경이며, 판정 임계값(52/104개 receipt, z, 결측 허용 5/10개, 낙폭 1.25배)은 바꾸지 않았다.

- **등록 확인은 main 기준이다.** 병합 시각은 `origin/main`의 first-parent 이력에서 명세를 추가한 커밋으로 정한다. HEAD 기준이 아니다.
  - 병합되지 않은 브랜치에서 명세를 추가한 커밋은 인정하지 않는다(`SPEC_NOT_ON_MAIN`).
  - 실행 중인 코드가 그 커밋을 포함하지 않아도 거부한다(`RUNNING_CODE_DOES_NOT_CONTAIN_REGISTRATION`).
  - 합성 fixture는 병합 시각을 직접 넘기고 git을 읽지 않는다. LIVE 기록기만 git을 읽는다.
- **특징 관측 창은 거래소 달력으로 증명한다.**
  - 생산 정의는 벤더 행 수로 창을 센다. `downside_vol_252`는 `close.dropna()`의 마지막 252개 수익률, `price_52w_high`와 `ma200`은 행 기준 `rolling(252)`/`rolling(200)`이다. 그래서 행이 330개 넘게 있어도 지난 1년 안에서 KRX 개장일이 1~2개 빠지면 "252세션" 값이 실제로는 253~254세션에 걸친다. 이전 보강의 `mom12_1Pct` 조건(종가 273개 이상)은 이 경우를 통과시켰다(감사 반례).
  - 이제 기록 시점에 생산 빌드와 같은 호출(`fetch_prices`, auto_adjust)로 새로 내려받은 프레임을 `kr_bar_integrity.calendar_frame`으로 KRX 달력에 맞춘다. `window_complete`로 창 전체(`CH_LOWVOL` 253개 종가, `CH_HIGH52` 252개)가 거래 세션인지 확인하고, 창 안에 휴장일 행이 없는지도 본다. 그다음 그 프레임으로 종가·특징값·`ma200`을 다시 계산해 artifact 값과 반올림 단위 안에서 같은지 확인한다.
  - 창이 불완전하면 `FEATURE_WINDOW_INCOMPLETE`, 값이 재현되지 않으면 `FEATURE_VALUE_MISMATCH`로 그 책에서만 제외한다. 증명이 필요한 종목의 프레임이 아예 없으면 receipt 전체를 거부한다(`PRICE_FETCH_INCOMPLETE`). 같은 창 안의 다음 실행이 다시 시도한다. 부분 다운로드가 우연히 돌려준 종목만으로 책을 만들지 않기 위해서다.
- **결측 관문은 모든 계열에 적용한다.** 결측 10개 허용은 H252, H126, `CTRL_MODEL5`와의 짝 비교 각각에 적용한다(`seriesShortOfCohort`). 유효 표본이 2개뿐인 계열로는 `SUPPORTED`가 나올 수 없다. Sharpe나 MDD가 정의되지 않으면 `INCONCLUSIVE_DATA`다.
- **outcome 재시도: 공급자 장애와 경제적 미해결을 나눈다.**
  - 공급자 미확보(`PROVIDER_DATA_UNAVAILABLE`): 벤치마크나 보유 종목의 프레임이 없거나, 세션 행이 없거나, 종가가 무효인 경우다. 빈 응답이나 부분 응답이 여기에 해당한다. 날짜와 상관없이 기록하지 않고(`DEFERRED`), 이후 실행이 새 다운로드로 다시 채점한다. 재시도 상태는 append-only 원장 밖의 `outcome-pending.json`에 남긴다. 처음 보류된 시각과 시도 횟수를 담고, 증거가 아니다. Yahoo의 빈·부분 응답을 상장폐지나 종결로 확정하지 않는다.
  - 경제적 미해결(`ECONOMIC_UNRESOLVED`): 벤더가 만기 세션을 제공했고 그 세션 거래량이 0인 경우다. 실행일 후 (만기 + 5)번째 세션이 확정될 때까지 보류하고, 그 뒤 `FINAL_UNRESOLVED_AFTER_RETRY`로 기록해 None으로 센다.
  - 공급자 사유가 하나라도 섞인 기록은 최종 기록이 될 수 없다(`OUTCOME_PROVIDER_GAP_IS_NEVER_FINAL`). 이미 기록된 receipt와 outcome은 바뀌지 않는다.
  - 남는 결정: 공급자가 끝내 제공하지 않는 종목이 있으면 그 코호트는 채점되지 않은 채 남는다. 독립 출처로 종결을 확인해 닫는 규칙은 연구 규칙 변경이므로 소유자 승인 사항이다.
- **위험 경로의 실행 불가 처리.** 리밸런스 세션에 새로 고른 종목이 정지(행은 있고 거래량 0)면 그 기간 그 슬롯은 069500.KS로 보유한다. 코호트 outcome의 `NOT_EXECUTABLE_HELD_AS_BENCHMARK`와 같은 규칙이고 거래비용도 같게 부과한다. 이전에는 이 경우 경로 전체가 `INCOMPLETE`가 되어 위험 조건 하나 때문에 1차 판정이 `INCONCLUSIVE_DATA`로 갈 수 있었다(소유자 감사 2026-10-23). 행 누락·무효 종가, 이미 보유한 종목의 미거래는 그대로 `INCOMPLETE`다.
- **과학적 의존성 계약.** 규칙은 이 연구의 세 파일에만 있지 않다. 그래서 의존성도 함께 고정한다(소유자 감사 2026-10-23, #278 comment 6355563725).
  - 직접 호출하는 연구용 규칙 모듈(`prospective_receipt_core`)은 바이트로 고정한다(`scientificDependencies.fileHashes`).
  - 생산 빌드와 공유하는 도우미는 동작으로 고정한다. 대상은 KR 거래비용, 세션 확정 시각과 `^KS11`, Newey-West, `downside_vol_252`, 2026-10-01~2029-12-31 KRX 달력이다. 고정된 합성 입력에 대한 출력을 해시한 값이 `conformanceDigest`다. 그 모듈의 무관한 수정은 영향이 없고, 이 연구가 쓰는 계산이 바뀌면 LIVE의 record·outcomes·assess가 `SCIENTIFIC_DEPENDENCY_CHANGED`로 거부한다.
  - 정당한 변경(KRX 달력 정정 포함)은 새 연구 버전으로 등록한다. 이 버전을 다시 고정하지 않는다. 합성 fixture는 계약을 읽지 않는다.
  - 계약 밖에 두는 것: 생산 artifact 자체(`CTRL_MODEL5`는 정의상 생산 모델이며 `modelVersion`으로 기록된다)와 저장소 공통 안전 관문 `weekly_publish.unsafe_reason`.
- **거래량을 모르는 세션은 거래 세션이 아니다.** 거래량이 없거나 NaN·±무한대·음수인 행은 OHLC가 그럴듯해도 `VOLUME_INVALID`로 분류하고 종가를 버린다(소유자 감사 2026-10-23, #277 comment 6359555396). 이전에는 이런 행이 `VALID`로 통과해 관측 창과 outcome의 거래 세션으로 셌다. 벤더가 0이라고 밝힌 정지(`SUSPENDED`)와는 구분한다. 만기의 `VOLUME_INVALID`는 공급자 미확보로 보류되고 경제적 미해결로 확정되지 않는다. 리밸런스의 `VOLUME_INVALID`는 실행 불가 대체가 아니라 `INCOMPLETE`다.
- **아직 남은 비P1 지적.**
  - 실행일 거래량 0을 정지로 보는 규칙은 벤더의 주장에 의존한다(감사 지적 2).
  - 허용된 None은 평균에서 빠지므로, 그것이 상장폐지라면 생존편향 방향으로 작용할 수 있다(감사 지적 4).
