# rp1-c1 · 미국 ETF 위험 노출 동결 복제 (WP4a~WP4c)

**상태:** `PREREGISTRATION_AND_DATA_FOUNDATION_NO_OUTCOME_COMPUTED` · 증거 등급 `FROZEN_RULE_REPLICATION_ON_PUBLICLY_KNOWN_US_HISTORY`
**기계 판독 사양:** [`specs/rp1-c1-us-exposure-ladder-replication-v1.json`](specs/rp1-c1-us-exposure-ladder-replication-v1.json) (+ `.sha256`, 과학 내용 전용 `.scientific.sha256`)
**이 변경에서 하지 않은 것:** 미국 가격·수익률·금리 값 열람, 상태·경로 계산, 잠금, 정식 실행(WP4d). Study A/B와 독립이며 그 진행을 막지 않는다.

## 1. 무엇을 하는가

봉인된 `kr-market-risk-model-v1`의 노출 규칙(PASSIVE, C0, C1, C2, C3; 배수 1.0/0.7/0.4)을 **규칙·임계값·창·지연·결정 규칙 하나도 바꾸지 않고** S&P 500에 적용한다. 바뀌는 것은 다섯 가지뿐이며 사양 `model.differencesFromKr`에 고정했다.

| 항목 | KR 봉인 | US C1 |
|---|---|---|
| 거래소 달력 | XKRX | XNYS (같은 산식에 인자로 전달) |
| 기준 지수·FAST 입력 | FDR_KS200 가격지수 | YAHOO_GSPC 가격지수 |
| SLOW·TRANSITION 입력 | FRED DGS10·DGS3MO·VIXCLS | **같은 보존 바이트**(재획득 없음, KR 사양 해시와 대조) |
| 비용 | 매수 15bp / 매도 45bp | 매수 8bp / 매도 8.3bp (저장소 미국 비용표) |
| 평가 창 | 2007-01-01 ~ 2026-09-17 | 1993-02-01 ~ 2026-09-17 (종료일은 KR 상속) |

이미 아는 결과: KR 25% 변동성 임계값은 그대로라서 변동성이 낮은 미국에서는 FAST 변동성 다리가 덜 켜진다. 이를 조정하지 않고 보고한다.

## 2. 재사용과 동등성 (실측)

- 상태기계, 후보 규칙, 결측 처리, 경로 재현, 지표, 파레토 결정은 `kr_market_risk_model`·`kr_market_risk_anatomy`에서 **임포트**했다. KR 달력을 직접 부르는 두 함수(`period_end_sessions`, `decision_schedule`)만 달력 인자를 받는 같은 산식으로 다시 썼다.
- `rp1_c1_us_exposure_spec.equivalence_audit` 결과 **EXACT**([`results/rp1-c1-kr-equivalence-v1.json`](results/rp1-c1-kr-equivalence-v1.json)):
  - XKRX 주말·월말 표본일과 결정 일정이 봉인 함수와 날짜 단위로 같다.
  - 보존 KR 바이트로 계산한 층 상태 표가 봉인 함수와 프레임 단위로 같다.
  - 현금 수익 0의 현금 포함 재현 경로가 봉인 재현 경로와 같다(후보 4개).
  - 봉인 KR 결과의 `decision`·`window`·`passive`·`candidates`가 최대 절대 오차 **0.0**으로 재현된다.
- KR 동등성은 봉인된 KR 결과에 이미 있는 숫자만 비교하며 새로운 결과를 열지 않는다.

## 3. 원천과 데이터 품질 관문 (결과 열람 전 고정)

| 원천 | 역할 | 기준(basis) | 관문 |
|---|---|---|---|
| YAHOO_GSPC `^GSPC` | 1차 독해 자산, FAST 입력 | 가격지수 | FAST 준비 201세션부터 분석 종료까지 XNYS 세션 **누락 0**. 위기 창(2000-02, 2007-09, 2019H2-2020) 커버리지 ≥0.99. 신원·중복·무효행 ≤0.5% |
| FRED_SP500 | 같은 지수의 공급자 교차검증 | 가격지수(2016~) | 같은 날짜 수준 상대차 >0.5%인 날 비중 ≤1%. CONFLICT 또는 겹침 부족이면 차단 |
| YAHOO_SPY adjclose | 경제적 독해 자산 | 공급자 조정 총수익(**외부 대조 미완료**) | 평가 세션 누락 0. 실패하면 경제적 독해만 `UNRESOLVED` |
| FRED_DTB3 | 경제적 독해 현금 | 할인 수익률, 연 % | 평가 세션마다 알려진 금리(지연 4일, 14일 정체 규칙). 실패하면 경제적 독해만 `UNRESOLVED` |
| FRED_VIXCLS·DGS10·DGS3MO | SLOW·TRANSITION | 시장 관측, 비개정 | KR 봉인 바이트 그대로 |

- 결과 열람 전에 읽는 값은 교차검증용 두 지수의 같은 날짜 **수준**뿐이다(KR 원천 계약과 같다). 수익률은 계산하지 않는다.
- 설계 확인(결과 없음, 참조 지수를 XNYS 전 세션 관측으로 가정):
  - 결정일 1,754개(1993-02-05~2026-09-11). 네 후보 모두 100% 결정 가능하다.
  - VIX 백분위는 1992-12-31부터 정의된다.

## 4. 고정 사양과 중단 기준 (`stopRules`)

- **잠금 전 거부:**
  - 사양·과학 내용·임포트 클로저가 다르다.
  - KR 봉인 핀이나 재사용 원천 바이트가 다르다.
  - 동등성이 EXACT가 아니다.
  - 미국 스냅샷이 없거나 기준 지수 세션이 누락됐다.
  - 교차검증이 CONFLICT다.
  - 어느 후보든 결정일 99% 미만에서 결정 가능하거나 첫 결정일에 결정 불가하다.
  - 결과, 마커 또는 잠금이 이미 있다.
- **실패 후 금지:** 관문 완화, 창 변경, 공급자 교체·접합, 누락 세션 채우기.
- **잠금 후 실패:** 연구를 소진한다. 재실행하지 않고 시도 산출물을 보존한다.
- **결정 규칙:** KR 봉인 파레토 규칙을 그대로 쓴다.
  - 1차 독해(미국 비용 1×)에 적용한다. 경제적 독해는 결정을 바꿀 수 없다.
  - 절차: 지배 제거 → C0 대비 비열등(수익 −0.50pp, |MDD| ×1.10) → 의미 있는 개선(수익 +0.50pp 또는 |MDD| ×0.90).
  - 생존자 1개면 지명, 0개면 C0 유지, 복수면 트레이드오프로 기록한다.

## 5. 결과 열람 이후 해석 기준 (`interpretation`, 사전 고정)

| 미국 결과 | 판독 | 프로그램 결론 |
|---|---|---|
| `NO_CANDIDATE_NOMINATED_CONTROL_RETAINED` | `REPLICATED_CONTROL_RETAINED` | 노출층은 수익원이 아니라 위험 선호 선택지. 기본값은 지수 100%, C0는 명시적 위험 예산이 있을 때만. 이 층에서 추가 규칙 탐색 종료 |
| C1·C2·C3 지명 | `NOT_REPLICATED_US_NOMINATION` | 시장 간 불일치 → 승격 없음, C0와 미국 지명 후보를 전향 기록에 함께 둔다 |
| 트레이드오프 | `NOT_REPLICATED_US_TRADEOFF` | 어느 시장에도 지명 없음. 모든 후보 전향 기록 |
| 수동 대비 MDD를 줄이는 후보 없음 | `NO_PROTECTION_IN_US` | 미국 노출층 없음 |

**측정하는 질문과 해당 지표:**

| 질문 | 지표 |
|---|---|
| 위험이 높을 때 비중 축소가 실제로 도움이 되는가 | MDD, 월간 CVaR95, 최악 롤링 H63/H126 (1차·경제적 독해 모두) |
| 손실 감소를 위해 포기한 상승 수익은 얼마인가 | `upMarketCostPerYear`와 `downMarketSavingPerYear`, `reboundMissedH63/H126`, `sessionsUntilFullExposure` |
| 수익률을 개선했는가, 변동성·MDD만 줄였는가 | 순 연율수익 대 수동, 경제적 독해의 현금 초과 Sharpe |
| 국면 판단 오류는 어떤 사례였는가 | `falseAlarmList`(날짜·H63 이후 최저 손실), `protectionByEpisode`의 `UNPROTECTED` 낙폭 |
| 종목 선택 모델 위에 쓸 가치가 있는가 | C1은 지수 결과만 말한다. 종목 책 효과는 그 책의 베타·상관에 달렸으므로 별도 연구(C2)다 |

**결론으로 쓰지 않는 문장:** 위기를 예측한다, 검증됐다, 임계값을 바꿔야 한다, 미국 결과가 KR 봉인을 구제·번복한다.

## 6. 실제 실행 전 최종 확인 사항 (WP4d 전에 모두 참이어야 함)

1. **[차단] 워크플로 인벤토리가 동결돼 있다.**
   - 모든 인벤토리 문서(`docs/workflow-inventory*.md`)와 두 census 테스트가 Phase C 봉인 사양에 해시로 고정돼 있다.
   - 이 환경에서 직접 확인했다. 새 `.yml`/`.yaml` 파일은 고정된 census 테스트를 실패시키고, 고정된 테스트를 고치면 봉인된 Phase C amendment 검증(`test_preserved_v1_and_exact_versioned_amendment`)이 실패한다.
   - 따라서 원천 수집 워크플로도, WP4d 실행 워크플로도 추가할 수 없다. 소유자가 "Phase C 이후 워크플로용 버전 census 계층"을 결정해야 한다.
2. **미국 원천 스냅샷.**
   - 이 작성 환경에서는 Yahoo·FRED가 CONNECT 403이고 FRED 키도 없어 아무것도 획득하지 않았다.
   - 대안: 소유자가 네트워크와 `FRED_API_KEY`가 있는 환경에서 `python scripts/acquire_rp1_c1_us_sources.py`를 실행하고 `data/rp1-c1-us-exposure/sources/`를 커밋한다. 출처는 운영자 기기이며 `audit.json`에 기록된다. 또는 1번 결정 후 Actions에서 실행한다.
   - 그다음 `python scripts/build_rp1_c1_us_exposure_spec.py`를 실행한다. 과학 내용이 1바이트라도 바뀌면 빌더가 거부한다.
3. `python scripts/run_rp1_c1_us_exposure.py readiness` → `READY_FOR_RP1_C1_FORMAL_EXECUTION`, 카운터 전부 0.
4. `python scripts/run_rp1_c1_us_exposure.py equivalence` → `EXACT`.
5. 임포트 클로저(58개 운영 모듈 포함)가 바뀌었으면 사양을 다시 빌드한다. 과학 다이제스트는 같아야 한다.
6. WP4d PR:
   - 실행 하네스를 사양 클로저 밖에 둔다(v4/v5 선례).
   - 소유자 승인 파일에 사양·코드 해시를 고정한다.
   - `workflow_dispatch`는 main에서만, 원자적 잠금 ref 생성 후에만 미국 값을 읽는다(마커 `valuesReadBeforeThisMarker == 0`).
   - 정확 바이트 Draft 봉인 PR까지 포함한다.

## 7. 별도로 실험할 가치가 있는 위험관리 가설 (`newHypotheses`, C1 결과로 선택하지 않음)

| ID | 질문 | 제약 |
|---|---|---|
| C1b-VOL-TARGET | 연속 역변동성 조절(목표 = 과거전용 확장 중앙값 vol63, 상한 1.0)이 이산 C0보다 같은 상승장 비용으로 MDD를 더 줄이는가 | 목표 규칙은 그 연구의 결과 전 고정. Moreira–Muir 대 Cederburg 외·Barroso–Detzel |
| C2-STOCK-BOOK-OVERLAY | 고정된 0~5종목 책에 봉인 시장 배수를 씌우면 책의 베타를 감안해 MDD·CVaR 감소가 상승장 비용을 넘는가 | 다른 연구(예: Study A)의 동결 책 필요. 서로 기다리지 않음 |
| C1c-REENTRY-SPEED | 축소 비용의 대부분이 늦은 재진입인가: 진입 규칙 고정, 재진입만 바꾼다(기억 없음 대 주당 한 단계 복귀) | 구조 스위치 하나, 조정값 아님 |
| C1d-PROSPECTIVE-RECEIPTS-US | 미래 날짜부터 모든 후보의 미국 배수를 주간 기록 | 유일한 증거 경로. 미국 일간 가격 수집 승인 필요 |

## 8. 실행 명령 (결과 없음)

```bash
python scripts/run_rp1_c1_us_exposure.py verify
python scripts/run_rp1_c1_us_exposure.py equivalence          # EXACT 필요
python scripts/run_rp1_c1_us_exposure.py design-readiness     # 참조 지수 완전 관측 가정, 설계 확인
python scripts/run_rp1_c1_us_exposure.py readiness            # 스냅샷 전에는 DATA_BLOCKED(US_SOURCE_SNAPSHOT_NOT_ACQUIRED)
python scripts/build_rp1_c1_us_exposure_spec.py --check
pytest -q tests/test_rp1_c1_us_exposure.py
```
