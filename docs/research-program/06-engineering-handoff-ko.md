# 06 · Engineering Handoff (Codex 구현 명세)

**이 문서는 구현 지시이지 실행 승인이 아니다.** 각 작업 패키지(WP)는 별도 PR이며, 결과를 읽는 WP는 소유자가 승인 파일을 커밋하고 `main`에서 수동 dispatch할 때만 실행된다. 어떤 WP도 자동 실행·자동 승격·production 변경을 하지 않는다.

## 0. 모든 WP 공통 규칙

1. **새 파일 위치:** 코드 `pipeline/rp1_*.py`, 스크립트 `scripts/rp1_*.py`, 테스트 `tests/test_rp1_*.py`, 사양 `docs/research-program/specs/`, 결과 `docs/research-program/results/`. **`research_specs/`·`docs/results/`에 파일 추가 금지**(Phase C 폴더 보호 해시).
2. **봉인 파일 수정 금지.** 특히 `pipeline/kr_market_risk_model.py`, `pipeline/alpha_inference_calibration_v4.py`, Phase C·#245 관련 파일, replay-v16 매니페스트. 필요하면 **임포트해서 감싼다**. 봉인 사양의 의존성 클로저에 든 파일 목록은 각 봉인 사양의 `dependencyHashes`/`sealedDataInputs`로 확인하고, 변경 전 `git diff --stat`으로 그 목록과 교집합이 없음을 테스트로 확인한다.
3. **결과 접근 카운터:** 결과(미래 가격·라벨·NAV)를 읽는 모든 함수는 호출 지점에서 카운터를 올린다. "결과 없음" WP의 테스트는 해당 함수를 예외를 던지는 스파이로 바꾸고도 통과해야 한다.
4. **검증 명령(AGENTS 체크리스트):** `ruff check .` · `python -m compileall pipeline` · `pytest -q` · 시드 생성 · 아티팩트 검증. 실패를 숨기지 않는다.
5. **커밋 금지 항목:** 개별 종목 가격·라벨 payload, 비공개 일간 경로, 자격 증명.
6. **PR은 Draft.** `main`에 직접 병합 금지.
7. **공통 연구 환경 v1(#247) 위에 짓는다.** 표본 키·계층·라벨 시간·경제적 전제는 `pipeline/experiment_workbench.py`의 `Key`, `Cell`, `Observation`, `sample_identity`, `filing_prefix`, `LabelReference`, `Fold`, `Economics`, `preview_manifest`를 쓴다. 입력 준비도는 `scripts/inspect_experiment_sources.py`를 **확장**하며 새 특징 행렬 엔진·새 키·새 비용 공식을 만들지 않는다. 이 타입에 필요한 필드가 없으면 `experiment_workbench.py`에 추가하는 별도 작은 PR로 처리하고 기존 테스트를 약화하지 않는다.

## WP0 — 가격·벤치마크 수익 기준 admission (결과 없음, A1의 전제)

- **목적:** #247 `Economics.blockers()`의 `RETURN_BASIS_MISMATCH`·`BENCHMARK_UNRESOLVED`를 미국 종목·SPY에 대해 해소하거나, 해소 불가를 확정해 A1을 `BLOCKED_OUTCOME_ECONOMICS`로 닫는다.
- **방법:** 종목·SPY 양쪽 가격 레그에 같은 경제적 수익 정의(총수익, 배당 재투자 시점 규칙)를 고정하고, 외부 독립 원천과 **수준이 아니라 배당·분할 이벤트 목록과 일간 수익률 차이 분포**로 대조한다. KODEX 200 감사(`docs/weekly-decision/kodex200-benchmark-audit.md`)의 방식 재사용. 가격 수준·미래 수익·라벨을 열지 않는다는 점은 카운터로 증명(대조는 과거 일간 수익 동일성 검사이지 신호-결과 관계가 아님).
- **판정(사전 고정):** 표본 종목의 연간 수익 차이 |Δ| ≤ 0.25%p 비율 ≥ 95% **그리고** SPY 연간 |Δ| ≤ 0.10%p → `VERIFIED`. 아니면 `UNRESOLVED`로 남기고 A1은 실행하지 않는다(문턱을 낮춰 재시도 금지).
- **산출:** `docs/research-program/results/rp1-wp0-price-basis-admission-v1.json`.
- 외부 원천에 접근할 수 없으면 `SOURCE_BLOCKED`로 기록하고 A1은 전향(A2)만 남긴다.

## WP1 — H252(KR·US)와 US H126 추론 보정 (결과 없음)

- **목적:** 6~12개월 1차 통계량의 구간 포함확률을 합성 데이터로 검증.
- **입력:** 없음(합성 DGP만). 엔진은 `pipeline/alpha_inference_calibration_v4.py`의 `calendar_time_series`, `calendar_time_sn_interval`, `_centred_rank_weights`를 **임포트**.
- **산출:** `docs/research-program/specs/rp1-inference-calibration-v1.json`(사전 고정 프로토콜), 결과 `docs/research-program/results/rp1-inference-calibration-v1-result.json`.
- **설정(사전 고정):** 셀 = {KR H252, US H126, US H252} × {78주, 312주, 실제 표본 주수} × 기존 v4 DGP 세트(지속 예측변수 DGP 포함). 반복 R = 8,000(v5의 정밀도 규칙 그대로). 결정: Clopper–Pearson 일측 경계로 PASS/FAIL/INCONCLUSIVE(v4 개정 2 규칙 그대로). 새 시드 1개를 결과 전 고정.
- **수용 기준:** 기존 v4 엔진과 같은 프로토콜에서 셀 결과 동일(테스트), 사양 키 분류 테스트(`semantic_differences` 방식), 시드가 기존 닫힌 프로토콜 시드와 다름.
- **판정 후 규칙:** PASS 셀만 1차 지평으로 사용. INCONCLUSIVE/FAIL이면 해당 지평은 기술통계로 고정되고 재시드·재실행 금지.
- **예상 계산:** Actions 4 workers 약 1~3시간.

## WP2 — Study A 미국 신원·유니버스 규칙 고정 (결과 없음)

- **목적:** A0/A1에 쓸 미국 유니버스 신원 규칙을 커버리지만 보고 하나로 고정.
- **후보 규칙(둘 중 하나):** R-a = #245 파일럿 신원 규칙(CIK 일치, 2023-04 이전 사실상 공백) / R-b = replay-v16 신원 규칙(2013~, 생존 조건부, 신원 위험 공개).
- **산출:** 연도별 적격 구성원-일, 비금융 비율, 무가격 퇴출 비율, PARA 등 신원 의심 패널 목록. **수익·라벨·가격 변화율을 계산하지 않는다**(가격 존재 여부만).
- **결정 규칙(사전 고정):** 2013~2025 각 연도 적격 구성원-일 ≥ 50%를 만족하는 규칙을 선택. 둘 다 만족하면 R-a, 둘 다 미달이면 Study A-US는 `DATA_INSUFFICIENT`로 A2(전향)만.
- **테스트:** 출력 스키마에 수익 키 없음(스캐너), 결과 함수 스파이.

## WP3 — 미국 ALFRED 빈티지 측정 (결과 없음, Study B 전제)

- **목적:** Study B 거시 팔 후보 열(CPI, INDPRO, UNRATE, PAYEMS)의 첫 빈티지와 Study 창 시작일 재구성 커버리지 측정.
- **방법:** 기존 `probe_alfred_macro_vintages`와 `pit_data.vintage_column` **재사용**(재구현 금지), `series/vintagedates` 우선.
- **산출:** 열별 `firstVintage`, 시작일 재구성 성공 여부, 정의 변경 의심(`WTREGEN` 사례) 플래그. `config.json`의 `macroVintageSeries`는 **이 WP에서 변경하지 않는다**(운영 영향).
- **결정 규칙:** 첫 빈티지가 Study B 창 시작보다 늦은 열은 제외. 남는 열이 0이면 Study B 거시 팔은 `PIT_UNSAFE`로 종료.

## WP4 — C1 미국 노출층 동결 복제 (최우선 실험)

### 4a. 데이터 스냅샷 구축 (결과 없음)

- **입력 수집:** ^GSPC 일간 종가(1990-01-02~), SPY 수정종가(1993-01-29~), FRED `DGS10`, `DGS3MO`, `VIXCLS`, `DTB3`. 각 시계열은 단일 공급자 경로, 이어붙이기 금지.
- **저장:** 내용 해시 매니페스트가 있는 불변 스냅샷(기존 `ObservationStore`/매니페스트 패턴 재사용). Git에 넣기 어려운 크기는 아니지만 원본 CSV와 획득 시각·공급자·버전을 함께 보존.
- **품질 관문(사전 고정):** XNYS 세션 대비 결측 ≤ 0.5%, 비달력 날짜 0, 음수·0 종가 0. 실패 시 `DATA_INSUFFICIENT`(관문 완화 금지).
- **테스트:** 결측·비달력·이어붙이기 감지 합성 테스트.

### 4b. 달력 일반화 래퍼와 KR 동등성 증명 (결과 없음)

- `pipeline/kr_market_risk_model.py`의 `period_end_sessions`와 `decision_schedule`는 내부에서 KR 세션(`M.kr_sessions`)을 호출한다. **이 파일을 수정하지 말고** `pipeline/rp1_exposure_replication.py`에 달력 인자를 받는 동등 함수를 만든다. `rule`, `multiplier`, `mapping_table`, `fast_states`, `slow_states`, `transition_states`, `trade_to_target`, `replay_path`, 지표 함수(`annualized`, `max_drawdown`, `participation`, `episode_capture`, `rebound_cost`, `false_alarm_profile`, `path_summary` 등)는 **그대로 임포트**한다.
- 상수(200, 63, 25%, 504, 0.80, 156, FRED 4일 지연, 14일 정체, 배수 1.0/0.7/0.4, 결정 밴드 0.50pp·1.10·0.90)는 KR 봉인 사양에서 읽고 재기술하지 않는다.
- **동등성 테스트(필수, 실행 차단 조건):**
  1. 래퍼에 XKRX 달력을 넣으면 `period_end_sessions`/`decision_schedule`가 봉인 함수와 날짜 단위로 동일(합성 세션).
  2. KR 봉인 결과 재현: 봉인 실행과 같은 KR 입력 스냅샷이 접근 가능할 때, 래퍼 경로로 계산한 `decision` 블록이 `docs/results/kr-market-risk-model-v1-result.json`과 1e-12 이내 동일. 입력에 접근할 수 없으면 이 테스트는 Actions 워크플로의 사전 단계로 실행하고, 불일치면 4d 실행을 거부.
  3. 끝날짜 불변성: 입력을 주 중간·월 중간에서 자른 경우에도 이전 날짜의 상태가 같음.
- **미국 적용 시 달라지는 것 목록(사양에 명시):** 달력 XNYS, 기준 지수 ^GSPC, 비용 미국값, 경제적 독해의 현금 DTB3. 그 외 차이 0개를 테스트로 확인(사양 키 분류).

### 4c. 사양 봉인과 준비도 (결과 없음)

- `docs/research-program/specs/rp1-c1-us-exposure-ladder-replication-v1.json`: 입력 스냅샷 해시, 코드 해시, 상속 상수의 출처 해시(KR 사양), 창, 판정 규칙 출처, 해석표(문서 03 §C.7) 전문.
- 준비도: 날짜 존재 대용값(1.0)을 같은 상태기계에 넣어 각 후보가 결정 가능한 첫 날짜와 결정 수를 측정(KR v1 방식). 결과 카운터 0.

### 4d. 일회성 실행과 봉인 (결과 열람)

- 워크플로 `.github/workflows/rp1-c1-us-exposure-replication.yml`: `workflow_dispatch` 전용, `main`만, 소유자 승인 파일(사양 해시·코드 해시 고정) 필수, 결과·잠금 ref 부재 확인 → `refs/tags/rp1-c1-us-exposure-ladder-replication-v1-execution-lock` 원자적 생성(POST만) → 그 후에만 값 읽기 → 결과 아티팩트 → 정확 바이트 Draft 봉인 PR(표준 라이브러리만, 실제 하위 프로세스 테스트).
- 워크플로 인벤토리는 `docs/workflow-inventory-addendum.md`에 추가(봉인된 `docs/workflow-inventory.md` 수정 금지).
- **산출:** 후보별 문서 03 §C.5 지표, 1차(가격지수·현금 0%)와 경제적 독해(SPY TR·DTB3), 하위구간 기술통계, 판정, 해석표 결과.
- **금지:** 잠금 후 재실행, 파라미터 변경, 결과 후 하위구간 선택.

## WP5 — A0 Study A 측정성·MDE 사전검사 (결과 없음)

- **입력:** 미국 WP2 규칙의 유니버스·재무(#247 `filing_prefix` 경유), KR Phase B 매트릭스(측정성만, KR은 A0까지만). `inspect_experiment_sources.py`의 census에 A-H1~H3 사건 필드를 추가하는 방식으로 구현하고, 결합 입력의 정의는 census와 같은 원천 커밋·허용 목록을 쓴다.
- **계산:**
  1. A-H1~H3 사건 유병률(날짜별), 측정 가능 비율, 날짜당 S=1 종목 수, 층(업종×규모×수익 삼분위) 셀 크기 분포.
  2. 구별성: A-H1 플래그와 기존 연속 특징의 날짜 내 순위 상관.
  3. MDE: WP1 엔진의 합성 DGP에 실제 유병률·층 구조·코호트 수를 넣어 `Δ`의 80% 검정력 최소검출효과 산출.
- **산출:** `docs/research-program/results/rp1-a0-measurability-v1.json`.
- **판정:** 문서 03 §A.7 A0 기준. 가설별로 `PROCEED_TO_A1` / `PROSPECTIVE_ONLY` / `DROPPED_REDUNDANT`.
- **테스트:** 라벨·전방 가격 함수 스파이, 출력 스키마에 수익 키 없음.

## WP6 — A2 전향 기록 (KR 먼저)

- `pipeline/prospective_receipt_core`를 그대로 사용(정규 JSON, 다이제스트, JSONL 원장, `PROSPECTIVE_PAPER`, 백데이트 금지 창, 18:00 KST 최종성).
- 영수증 내용: 신호일, 지역, 종목, A-H1~H3 플래그, 입력 가용일, 층 키, 모델 버전, 사양 해시. **비중·매수 권고 없음.**
- 영수증 키(date, region, ticker, modelVersion)와 #247 `Key`(market, signal_date, security_identity)는 별도 매핑 테이블로 연결한다. 기존 키·다이제스트를 다시 쓰지 않는다.
- 결과 기록은 만기(H252 세션 후, 18:00 KST 이후) 이후 별도 파일로만.
- 미국은 일간 가격 영속 수집 승인(소유자)과 재무상태표 소스 해결 전까지 `BLOCKED` 상태로 코드만 준비.
- 첫 판정 시점은 문서 03 §A.7(36개월). 그 전에는 누적 수만 보고.

## WP7 — A1 미국 역사 단회 검정 (조건부, 결과 열람)

- **진입 조건:** WP0 `VERIFIED`, WP1에서 1차 지평 PASS, WP5에서 해당 가설 `PROCEED_TO_A1`, 소유자 승인. 라벨은 `LabelReference`, 폴드는 `Fold`로 만들고 `training_reason`이 `None`이 아닌 라벨은 학습에서 빠진 사유와 함께 집계한다.
- 문서 03 §A.5 추정량, 두 생존 독해, 층 순열 귀무, Holm, 전·후반 안정성.
- 모델은 A-M0만. A-M1은 A-M0 개발 지지 시 같은 실행 안에서 사전 고정 설정으로만(별도 실행 금지).
- 일회성 잠금, 정확 바이트 봉인, WP4d와 같은 절차.

## 의존 관계와 순서

```
WP0 (가격 기준 admission) ─────┐
WP1 (보정, 합성) ─────────────┤
WP2 (US 신원 규칙) ── WP5 (A0) ┴── WP7 (A1, 조건부)
WP3 (ALFRED) ── Study B 기술통계(후순위)
WP4a → WP4b → WP4c → WP4d (C1, 최우선 결과 실험)
WP6 (KR 전향 기록) — 독립, 언제든
```

권장 PR 순서: **WP4a+4b(동등성 증명 포함) → WP4c → 소유자 승인 후 WP4d**, 병행으로 WP1 → WP2 → WP5 → WP0, 그리고 WP6. WP0은 A0가 `PROCEED_TO_A1` 가설을 하나라도 낼 때만 비용을 들일 가치가 있다.

## 완료 정의(각 WP 공통)

- 위 수용 기준 테스트 통과, AGENTS 체크리스트 통과 출력 첨부.
- 결과 없는 WP는 카운터 0을 결과 파일에 기록.
- 결과 WP는 잠금 ref·아티팩트 다이제스트·사양 해시·코드 해시를 봉인 문서에 기록.
- 판정 문구는 사전 고정 어휘만 사용.
