# P0~P5 공통 비교 입력 계약 및 합성 검증

이 산출물은 `hierarchical-vs-direct-selection-comparison-v1`의 **미등록 제안**을 구현한 연구 입력 계약이다. 연구 실행 승인, Portfolio D 운영 정책, 기존 봉인 또는 역사 판정을 변경하지 않았다. 새 실제 가격 패널을 읽거나 역사 P0~P5 수익률을 계산하지 않았다. 실제 입력에 대한 outcome 평가 함수는 제공하지 않는다.

## 기준 및 재사용

| 근거 | 고정 식별자 / 사용 범위 |
|---|---|
| 최신 main | `37f8cbf6b1c066f6b3c65235953648d17ebf2f69` |
| 비교 제안 | [계층 문서 §7](https://github.com/jaehojung1879-netizen/Investment/blob/37f8cbf6b1c066f6b3c65235953648d17ebf2f69/docs/research-program/07-market-industry-stock-portfolio-hierarchy-ko.md#7-향후-비교-계약--산업종목이-직접-종목-선택보다-실제로-더-나은가), Git blob `513c28403dd0990d7fb4212c99eeaaba64dac89f` |
| 기존 공통 영수증 | `pipeline/prospective_receipt_core.py`: canonical JSON, digest, outcome-key 배제, KR 최종 마감 규칙을 그대로 호출 |
| 기존 지역 세션 | `pipeline/replay_calendar.py`: XKRX/XNYS 세션, KR 휴장 보정, `CALENDAR_VERSION` 재사용; US 마감·조기 마감·DST는 동일 pinned exchange-calendars의 XNYS 시각 사용 |
| 기존 통합 연구 | `pipeline/kr_integrated_alpha_portfolio.py`, `pipeline/kr_integrated_alpha_portfolio_receipts.py` 읽기 전용. 기존 six-path 정의를 새 P0~P5로 재명명하거나 다시 실행하지 않음 |
| #306 | `49e35ace1cd3ca03599d8bfc3913a37ec164e5fb`, `pipeline/entry_state_shadow_ledger.py`의 `ENTRY_STATE_SHADOW_DECISION_V1`, `sourceHashes`/`observationSha256`/`sourceArtifactSha256`를 읽는 어댑터 제공. 기존 `decided_digest` 로직을 복제하지 않음 |
| #314 | `26a40921aced2e377287955819d111a809c0da31`을 읽기 전용 확인. `pipeline/daily_decision_report.py`는 이미 읽기 전용 보고 담당이므로 재작성하지 않음 |
| #299 / #307 | `4d7fbbd83afb82d3b83ebca81fc312e962bf41c9` / `03a72544c513bed7d094d2ffb37239ce459ee133`: 기존 readout/report 결과를 새 실행으로 대체하지 않음 |

## 구현 API

코드: `research/cross_market_foundation_v1/comparison.py`. 예제 입력은 `tests/test_cross_market_comparison.py`의 `inputs()`와 `observation_block()`에 있다. 테스트의 종목 A~D, 산업 I1/I2, 요율, 성과는 모두 합성 값이다.

- `prepare_comparison(common, paths)`: 동일 입력·정책·자격 참조와 여섯 경로를 검사해 결정적 `planSha256`을 만든다. `executionEnabled=False`, `deployable=False`가 항상 붙는다. 결함은 예외로 중단하고 ETF 대체 비중이나 연구 판정을 생성하지 않는다.
- `maturity_status(region, execution_date, horizon_sessions, as_of_utc)`: H126/H252를 실제 지역 세션으로 세고 만기일 마감 전 `OBSERVATION_INCOMPLETE`를 반환한다. `performance`는 언제나 `None`이다. 실행일은 session 0이다.
- `read_operational_receipt(receipt, expected_sha256=...)`: 기존 공통 prospective 영수증의 원본 digest를 검증하고 입력 식별자만 읽는다.
- `read_portfolio_d_receipt(receipt, expected_record_sha256=...)`: #306 실제 shadow 스키마를 지원한다. **전체 canonical record** 외부 pin으로 검사하므로 일부 provenance를 제외하는 운영 의미 digest와 혼동하지 않는다. 운영 의미 검증은 기존 소유 모듈의 검증기를 따로 호출해야 한다. 비중·수익률을 복사하거나 장부를 쓰지 않는다.
- `price_execution_legs(common, legs, stress=1)`: 모든 모델에 동일한 STOCK/ETF × BUY/SELL tariff로 실제 leg notional을 가격화한다. 수익률 평가와 체결 시뮬레이터가 아니다.
- `score_synthetic_fixture(plan, block)`: `SYNTHETIC` 계획과 `synthetic:` fixture만 허용한다. 실제 역사·전향 증거 클래스는 `REAL_OUTCOME_EXECUTION_PROHIBITED`로 거부한다. 합성 계산은 과학적 연구 결과로 승격하지 않는다.

## 동등성 및 경로 의미

모든 경로는 같은 `commonSha256`, 신호일, 다음 지역 거래일 진입, 공개 정보 cutoff, 종목 모집단, 분류, 원천 payload 해시, 비용 및 체결 정책을 참조한다. 소스 코드 commit과 데이터 payload hash를 별도로 요구한다. 정보 공개시점과 vintage가 신호일 마감 뒤이면 거부한다. 현재 분류·수정 시계열을 과거 공개 정보로 소급하지 못한다. 다만 이 검증은 **선언된 근거의 구조 검사**이며 원본 원천 적격성과 사용권의 독립 실사까지 대신하지 않는다.

| 경로 | 검사하는 의미 |
|---|---|
| P0 | KR `069500.KS` 또는 US `SPY` 100%; QQQ는 주 비교 ETF가 될 수 없음 |
| P1 | 시장 기준 stock-score 계약; 공통 종목 수·개별 종목·산업 상한 적용 |
| P2 | 선택 산업의 **신호일 전체 구성원**을 신호일 시가총액으로 고정 가중. 일부 승자만 남긴 바스켓 거부 |
| P3 | 선택 산업 외 종목 보유 거부. P1과 같은 이름 수 및 위험 정책 적용 |
| P4 | ETF 잔여 비중의 look-through를 포함한 전체 산업 노출이 P0 산업 비중과 일치해야 함 |
| P5 | 사전에 고정한 같은 단위 가산 점수 계약 및 결합 해시 필요 |

미분류 이름을 P1만 살리거나 P3만 버리는 비대칭 모집단은 허용하지 않는다. 공통 분류 모집단 선정 자체는 별도의 등록·커버리지 공개가 필요하다. 시장 위험 배수는 첫 비교에서 정확히 1이다. 산업/종목 자격 hash가 없으면 `BLOCKED_NO_QUALIFIED_INPUT_OR_POLICY_*`다. hash 존재만으로 자격이 승인됐다고 주장하지 않는다.

P0~P5 목표를 생성하는 새 선택 모델은 구현하지 않았다. 입력 목표가 정책에 맞는지 검증하며, 실제 점수 생성은 기존 모델 또는 향후 적격 builder가 담당한다. P5의 점수 단위·결합 가중치 적격성은 참조한 별도 qualification의 독립 감사 대상이다.

## 총수익·현금흐름·비용

기준은 지역통화 KRW/USD의 배당 재투자 총수익, 분할 한 번 반영, 종결은 근거가 있는 대가만 사용이다. US USD 자산수익과 KRW 환산수익을 혼합하지 않는다. 본 버전은 FX·현금 잔액 경로를 평가하지 않는다. 배당이 이미 포함된 총수익에 분배금을 다시 더하는 계산을 제공하지 않는다.

합성 scorer는 초기 현금 1에서 봉인 비중으로 진입하고 만기에 전량 청산하는 단일 블록만 지원한다. 비용이 없는 가중 총수익을 입력받고 `NET_OF_FEES` 입력은 이중 차감을 막기 위해 거부한다. entry cost coefficient가 `a`이면 매수 투자금은 `1/(1+a)`다. 종목별 exit notional은 이 투자금 × 초기 비중 × `(1+gross_total_return)`이며, 이 금액에 동일 SELL tariff를 적용한다. 진입·청산 비용과 진입 투자금 감소 효과가 모두 반영된다. 비용을 단순히 사후 수익에서 한 번 빼는 방식이 아니다.

`costModel` 전체를 `costPolicySha256`으로 봉인하며 commission/spread/slippage/tax가 각 instrument/side에 모두 명시돼야 한다. 0은 명시 가정일 수 있으나 빠진 항목은 거부한다. 모든 경로의 비용은 같은 tariff에서 산출하므로 `costsByPath` 또는 `tariffsByPath`를 외부에서 넣어 특정 모델을 할인할 수 없다. 1×/2×/3× 스트레스가 필수이며 tariff 유효 기간 밖 체결은 거부한다. stock→ETF→stock 전환은 네 실제 leg에 같은 tariff를 적용하고 별도 switch surcharge를 중복 차감하지 않는다.

스트레스 적용 후 SELL 비용률이 매도대금의 100% 이상이면 `STRESSED_SELL_COST_NOT_SELF_FINANCING`으로 거부한다. 완전 투자·무차입 long-only 경로의 청산 비용이 매도대금을 초과해 음수 NAV를 만드는 계산을 허용하지 않는다. 높은 BUY 요율은 기존 자기금융 진입 투자금 축소 산식을 유지한다.

중간 리밸런싱, 실제 broker fill, 시장 충격·슬리피지 추정, 매수 가능 세부 호가, 배당 재투자 체결 비용은 이 단일 블록 합성 계산기의 실증 범위가 아니다. 실제 경제성에는 원천별 총수익·비용·체결 및 배당 세금 기준을 먼저 적격화하고 기존 운용/공통 엔진에 연결해야 한다. 합성 요율을 실제 KR 연도별 세율로 해석하지 않는다.

종결 미해결, 보유 종목 관측 부재, ETF와 다른 시작/종료일, 미래 관측, 통화/배당 기준 불일치, 중복 security observation은 **전체 공통 쌍 비교를 거부**한다. 0 또는 마지막 가격으로 보간하거나, 결함이 있는 경로를 제거해 유리한 모델만 비교하지 않는다. 실제 0의 종결 대가는 명시된 근거 hash와 함께 허용한다.

## 회귀 검증과 남은 승인

재현 명령:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python -m pytest -q tests/test_cross_market_comparison.py
ruff check research/cross_market_foundation_v1/comparison.py tests/test_cross_market_comparison.py
```

검증 대상은 결정적 해시, 미래 공개·vendor revision, 권리/PIT 미확인, 코드 commit과 payload 식별 분리, 공통 모집단, P2 고정 바스켓, P4 중립, 집중도, ETF 시작일, 명시적 비용 누락/모델별 할인/NET 이중 차감 거부, 자기금융 진입·청산 산식, 실제 4-leg 비용, H126/H252 지역 마감, XNYS 조기마감, 종결 결측, 중복, 실제 outcome 실행 거부, 원본 영수증 불변성이다.

현재 **실증 실행 READY를 뜻하지 않는다**. KR 역사 비교는 원래 문서에서 소진됐으므로 재실행하지 않는다. US 역사는 212개 퇴출 종목·산업 PIT·원천 권리/총수익 적격성 등이 풀려야 하며 이후에도 탐색 증거다. 전향 확증은 등록된 공통 모집단·점수 정책·위험 한도·실행 시각·비용 표·평가 기준 및 Owner 실행 승인을 먼저 받아야 한다. 아직 관측되지 않은 H126/H252는 성과 0 대신 관측 미완료다.
