# FRED 장애 내성과 단기 ML 모델 식별 (Issue #279) — 구현 완료, 운영 연결 보류

**상태:** `IMPLEMENTED_INACTIVE_WIRING_REQUIRES_OWNER_DECISION`
**코드:** [`pipeline/fred_resilience.py`](../pipeline/fred_resilience.py) · **시험:** [`tests/test_fred_resilience.py`](../tests/test_fred_resilience.py) (29개, 외부 네트워크 없음)
**기준:** `main` `7b0dbad53c46382291699887e1d5ee9364a33d49`

이 변경은 운영 경로를 하나도 바꾸지 않는다. 아래 연결 작업이 봉인 연구를 건드려야 하기 때문이다(§3). 그래서 새 모듈과 시험만 추가한다. 주간 투자 판단, 영수증, 원장, 봉인 연구, workflow, modelVersion, 단기 ML의 feature·창·임계값은 모두 그대로다.

## 1. #279의 사실을 다시 확인했다

| # | 주장 | 확인 방법 | 결과 |
|---|---|---|---|
| 1 | FRED가 없으면 ML 입력이 달라진다 | 운영 `features.build_features` → `feature_columns`를 합성 가격에 실행 | **재현됨.** 전체 FRED 구성은 60개 열, FRED 없음은 48개 열. 12개는 `Treasury_2Y`, `HY_Spread`, `IG_Spread` 등 ML 거시 열이다. 시험 `test_reference_feature_set_matches_the_full_production_config` |
| 2 | 학습 시작이 약 3년으로 잘린다 | 운영 `walk_forward`/`current_signal`의 `dropna`와 같은 규칙. 합성 거시에서 HY/IG만 2023-09-18에 시작 | **기전 재현.** 학습 시작이 2023-09-19가 된다. 거시는 `shift(1)` 뒤 들어오므로 하루 늦다. 실제 FRED의 ICE BofA 제공 기간 정책은 이 환경에서 확인하지 못했다(API 키 없음). |
| 3 | 결측 시 상수 대체 | `features.py:116-121` 원문, 시험 | **재현됨.** `Treasury_10Y = 3.0`, `Yield_Curve = 0.5`가 전 구간에 들어간다. |
| 4 | 같은 modelVersion으로 다른 모델 기록 | `signal-history`의 `ledger/portfolio-signals.jsonl` | **확인됨.** 2026-10-22 기록은 regime "Transition/Low confidence"인데 modelVersion은 정상 세대와 같다(`longterm-v2.2+regime-v2.1+…`). 10-15와 10-19에도 같은 regime이 있으나, FRED 장애 때문인지는 확인하지 않았다. |
| 5 | 장애 때 재학습과 실행시간 증가, timeout 없음 | 설치된 `fredapi` 0.5.2 원문, Actions run `39722662150` | **확인됨.** `fredapi`는 `urlopen(url)`을 timeout 없이 부르고, `fetch_macro`에는 retry가 없다. 해당 run의 "Build today's artifact"는 04:34–06:24Z(약 6,630초)였다. 오류 본문 XML에 `message`가 없으면 `ValueError(None)`이 되어 로그에 "failed: None"이 남는다. |
| 6 | dataSource 불일치 | `build.py:1107` | **확인됨.** 문구는 `cfg.has_fred`(키 존재 여부)만 본다. 실제 수집 성공과 무관하다. |

차이도 하나 있다. #279는 "26개 계열"이라고 했지만, 현재 `config.json`의 구성은 27개(US 24 + KR 3)다. 실제 로그의 실패 건수는 다시 세지 않았다.

## 2. 구현한 것 (`pipeline/fred_resilience.py`)

| 요구 | 구현 |
|---|---|
| 요청별 명시적 timeout | `timeout_fred`: fredapi의 비공개 `__fetch_data`만 바꿔 `urlopen(url, timeout=…)`을 쓴다. URL 구성, `"."`→NaN, 날짜 해석은 fredapi 그대로다. 그래서 정상 응답은 운영 `datafeed.fetch_macro`와 **같은 frame**이 나온다(시험이 `assert_frame_equal`로 확인). |
| 제한된 retry와 오류 분류 | `fetch_series`는 HTTP 상태를 보존하는 `FredRequestError`를 쓴다. 429→`RATE_LIMITED`, 5xx→`SERVER_ERROR`, timeout→`TIMEOUT`, 연결 실패→`NETWORK_ERROR`는 재시도한다. 4xx→`CLIENT_ERROR`, XML 오류→`MALFORMED`, 빈 계열→`EMPTY`는 재시도하지 않는다. 기본값은 3회 시도, 대기 2초·4초. |
| 공급자 장애 시 시간 제한 | 연속된 공급자 수준 실패 3개에서 멈춘다. 남은 계열은 `NOT_ATTEMPTED_PROVIDER_UNAVAILABLE`로 기록된다. 전면 장애는 약 9회 요청에서 끝난다(27 × 3 × 30초가 아니다). |
| 요청·성공·실패·사용 가능 시작일 추적 | `availability`: `requested`, `fetched`, `failedSeries`, 계열별 시도 수·HTTP 상태·메시지·첫/마지막 유효일·관측 수. ML 거시 계열의 공통 구간(`allPresentFrom`~`allPresentThrough`)과 그 경계를 정하는 계열(`limitingSeries`, `stalestSeries`)도 기록한다. 이 공통 구간은 **모든** ML 계열이 존재하고 유효 구간이 겹칠 때만 채운다(`overlapVerified`). 그렇지 않으면 `None`이다. 요청 성공(`FULL`)과 학습 입력으로 사용 가능함은 다른 사실로 구분한다. |
| 기계 판독 상태 | `status` ∈ `FULL` / `PARTIAL` / `UNAVAILABLE` / `DISABLED`, 그리고 `dataDegraded`. `data_source_label`은 실제 수집 결과로 문구를 만든다. |
| 실제 feature set 식별자 | `feature_set_digest`(정렬된 열 이름의 SHA-256). 등록 feature set은 `reference_feature_columns`가 **운영 feature 코드를 직접 실행해** 얻는다. 손으로 쓴 목록이 없어서 운영 정의와 어긋날 수 없다. |
| 모델별 실제 학습 시작일 | `training_start`는 운영 `dropna` 규칙과 같은 첫 학습 행을 낸다. `model_identity`가 earliest·latest·모델별 값을 기록한다. |
| 정상 모델과 데이터 부족 모델의 구분 | `model_identity`가 `REGISTERED_FEATURE_SET`을 주려면 네 조건이 모두 필요하다: feature set이 등록본과 같음, 상수 대체 없음, 수집이 `FULL`, `ml_input_coverage`가 입력을 **사용 가능**으로 검증. 사용 가능 판정은 세 가지다: ML 거시 계열이 모두 존재하고 유효 구간이 겹침, 최신성(`maxStalenessDays`), 겹치는 관측 수(`minOverlapObservations`). 여기에 학습 시작일이 등록 창(`latestAllowedTrainingStart`)을 넘지 않아야 한다. 이름만 같으면 등록 모델이 아니다. 기준이 미등록(`COVERAGE_POLICY = None`)이면 `COVERAGE_UNVERIFIED`이고, 기준을 어기면 `DEGRADED_FEATURE_SET`이다. 이 둘의 `effectiveModelId`는 각각 `<modelVersion>#unverified-<digest12>`, `<modelVersion>#degraded-<digest12>`이며 등록 버전 문자열과 같아질 수 없다. |
| 동일 모델 기록 금지 | `recording_decision`: 등록 모델만 `RECORD_UNDER_REGISTERED_MODEL_VERSION`이다. `DEGRADED_POLICY = None`이면 **HOLD**(fail-closed). `provenance_errors`는 FRED를 주장하는데 계열이 0개인 경우와, 저하 모델이 등록 버전으로 기록된 경우를 거부한다(validator용 규칙). |
| 주간 판단과 연구 원장의 격리 | 코드 변경 없음. 시험으로 고정했다. `weekly_decision`/`weekly_publish`/`weekly_history`는 datafeed·macro·regime·features·model을 import하지 않는다. `entry_features`와 `risk.diagnose`는 거시가 있을 때와 없을 때 출력이 같다. |

## 3. 왜 운영에 연결하지 않았나: 봉인 고정

`pipeline.build`의 import 범위 39개 모듈은 **모두** 봉인 사양에 바이트 해시로 고정돼 있다. workflow 트리도 `rp1-wp2-us-universe-v1`의 `protectedTreeSha256`에 묶여 있다. 고쳐야 할 파일과 영향은 다음과 같다.

| 파일 | 고정한 봉인 | 수정하면 |
|---|---|---|
| `pipeline/datafeed.py` | `alpha-opportunity-model-v1`, `market-industry-stock-data-foundation-v1` | `tests/test_alpha_opportunity.py::test_real_seal_and_readiness`가 `SEALED_DEPENDENCY_CHANGED`로 실패한다. 이 시험은 main의 필수 `pytest`에 속해 병합이 막힌다. |
| `pipeline/build.py`, `features.py`, `model.py`, `validate.py`, `ledger.py`, `provenance.py` | `alpha-opportunity-model-v1` 등 | 위와 같다. |
| `.github/workflows/ledger.yml`, `pages.yml` (`timeout-minutes`) | `rp1-wp2-us-universe-v1` | 봉인 결과가 고정한 트리 해시가 바뀐다. |

따라서 운영 연결은 **소유자의 봉인 처리 결정**이 먼저 필요하다. 이 문서는 그 결정을 대신하지 않는다.

## 4. 연결 계획 (승인 후 별도 PR, 범위 고정)

1. `datafeed.fetch_macro`는 `fred_resilience.fetch_macro_with_availability`를 호출하고 frame과 availability를 함께 반환한다. 정상 frame은 시험으로 동일성이 확인돼 있다.
2. `build.run`에 다음을 추가한다.
   - `meta.macroAvailability`
   - `meta.dataDegraded`
   - `meta.shortTermModelIdentity`(지역별 feature digest, placeholder, 학습 시작일)
   - `dataSource = data_source_label(…)`
3. 저하 정책이 HOLD이면(§5 O2):
   - 단기 ML 학습을 건너뛴다. #279의 3,163회 fit과 6,628초가 사라진다.
   - 단기 신호는 "보류"로 게시한다.
   - Kelly/regime shadow paper signal(`portfolio-signals.jsonl`)은 그날 추가하지 않거나 `effectiveModelId`로 따로 기록한다(정책에 따라).
4. `validate.py`에 `provenance_errors`를 적용한다.
5. workflow에 `timeout-minutes`를 둔다.
6. **바꾸지 않는 것:**
   - `weekly_decision`과 주간 영수증
   - 정상 경로의 feature·학습 창·임계값·modelVersion. 정상일 때는 등록 모델 그대로이므로 버전을 올리지 않는다.

## 5. 소유자 결정과 권고 (모두 미결정)

| ID | 결정 | 권고 | 이유 |
|---|---|---|---|
| O1 | 운영 파일 수정을 위한 봉인 처리 | `alpha-opportunity-model-v1`(이미 `BLOCKED_PREREGISTRATION`)의 의존 해시를 "역사적 인용"으로 바꾸는 정정을 별도 PR로 기록한다. v2.31의 `sourceFoundationCitation` 선례를 따른다. `market-industry-stock-data-foundation-v1`도 같은 방식으로 처리한다. | 지금 상태로는 운영 장애를 영원히 고칠 수 없다. v1은 v2~v5로 대체된 종료 사전등록이다. |
| O2 | 저하일의 처리 | **기본안 HOLD:** 단기 ML·regime 의존 paper signal 기록을 보류하고, 주간 판단은 그대로 진행한다. `RECORD_AS_SEPARATE_VARIANT`는 차선안이다. `REUSE_LAST_REGISTERED_MODEL`은 저장된 모델이 없어 지금 불가능하다. | 다른 모델을 같은 이름으로 기록하지 않는 가장 보수적인 선택이다. |
| O3 | 상수 대체를 결측으로 바꾸기 | 별도 연구 버전에서 검토(새 modelVersion) | 모델 정의가 바뀐다. |
| O4 | HY/IG 스프레드의 3년 절단 | 별도 연구 버전에서 검토. 계열 제거·대체는 지금 하지 않는다. | 정상 운영 모델 자체가 바뀐다. 공급자 정책도 확인이 필요하다. |
| O5 | workflow `timeout-minutes` | O1과 함께 120분 수준을 권고 | 지금 기본값은 360분이다. |
| O7 | 학습 입력 사용 가능성 기준(`COVERAGE_POLICY`: `maxStalenessDays`, `minOverlapObservations`, `latestAllowedTrainingStart`) | 결과를 보기 전에 소유자가 등록. 미등록이면 어떤 날도 `REGISTERED`가 아니며 기록은 보류된다. | 요청 성공은 사용 가능한 학습 입력의 증거가 아니다. 계열 하나가 관측 1개뿐이거나, 오래됐거나, 학습 시작을 크게 늦춰도 이름이 같으면 정상 모델로 기록될 수 있었다(독립 감사, 2026-10-23). |
| O6 | 산출물·paper signal의 추가 필드 | 승인 권고(추가 전용, 기존 필드 불변) | 데이터 계약 변경이므로 승인이 필요하다. |

## 6. 병합 뒤 확인 방법

- **이 PR:** 운영 동작은 바뀌지 않는다. 확인할 것은 두 가지다.
  - CI `pytest`가 녹색이고 봉인 시험(`test_real_seal_and_readiness`)이 통과하는지.
  - 다음 ledger run의 소요 시간과 "FRED … failed" 패턴이 이전과 같은지. 연결 전이므로 같아야 정상이다.
- **연결 PR 이후:**
  1. 다음 ledger run의 `site-data.json`에서 `meta.macroAvailability.status`, `fetched`, `elapsedSeconds`를 확인한다.
  2. 정상일에는 `shortTermModelIdentity.variant = REGISTERED_FEATURE_SET`이어야 한다.
  3. `dataSource`가 실제 수집 결과와 같아야 한다.
  4. FRED 장애일에는 다음을 확인한다.
     - `status ≠ FULL`
     - 빌드 시간이 정상 수준
     - paper signal이 보류됐거나 `#degraded-` ID로 기록됨
     - 주간 영수증이 평소대로 추가됨
