# rp1-c1 · 미국 ETF 위험 노출 동결 복제 (WP4a~WP4d)

**상태:** `PREREGISTRATION_AND_DATA_FOUNDATION_NO_OUTCOME_COMPUTED` · 증거 등급 `FROZEN_RULE_REPLICATION_ON_PUBLICLY_KNOWN_US_HISTORY`
**기계 판독 사양:** [`specs/rp1-c1-us-exposure-ladder-replication-v1.json`](specs/rp1-c1-us-exposure-ladder-replication-v1.json) (+ `.sha256`, 과학 내용 전용 `.scientific.sha256`)
**아직 일어나지 않은 것:** 미국 가격·수익률·금리 값 열람, 상태·경로 계산, 잠금, 정식 실행. WP4d 기계(원천 동결·소유자 승인·1회 실행·독립 검증기·비교 보고서)는 구현됐지만 소유자 승인 없이는 미국 값을 읽지 않는다. Study A/B와 독립이며 그 진행을 막지 않는다.

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

## 6. WP4d 실행 경로와 실제 실행 전 최종 확인 사항

### 6.1 워크플로 경로 (봉인 우회 없음)

- 모든 인벤토리 문서와 두 census 테스트가 Phase C 봉인 사양에 해시로 고정돼 있어, 새 워크플로 파일은 봉인을 깨지 않고는 추가할 수 없다(직접 확인). 새 인벤토리 계층도 같은 이유로 불가능하다. 고정된 census 테스트가 읽는 문서 목록 자체가 고정돼 있기 때문이다.
- 그래서 저장소 선례(`fundamentals.yml`의 Finnhub 탐침, `kr-corporate-action-collection.yml`의 US P4)와 같이 **기존 워크플로에 입력 하나로 경로를 둔다.** 호스트는 `seal-kr-factor-anatomy-v1.yml`이다. 어떤 봉인 사양에도 고정돼 있지 않고(테스트로 확인), 원래 작업은 이미 끝난 일회용 봉인이다.
- `rp1_c1_action` 기본값 `none`이면 원래 봉인 작업만 돈다. 원래 작업은 `if:` 한 줄 외에는 main과 바이트 단위로 같다(테스트).
- 작업: `rp1-c1-source-probe`(이 PR 브랜치의 pull_request 전용, 날짜만 보는 리허설, 원본 미보관) · `freeze-sources`(main 전용) · `dry-run` · `execute`(소유자 1회).

### 6.2 원천 저장 규칙 (라이선스)

| 원천 | 권리 분류 | 저장 |
|---|---|---|
| YAHOO_GSPC, FRED_SP500, YAHOO_SPY | `RESTRICTED_NO_REDISTRIBUTION`(S&P 지수 저작권, Yahoo 개인·비상업 이용 조건) | 공개 Git·로그·비암호 산출물 금지 |
| FRED_DTB3 | `PUBLIC_DOMAIN_CITATION_REQUESTED`(연준 H.15) | 규칙을 하나로 두려고 같은 암호화 스냅샷에 둔다 |
| FRED_VIXCLS·DGS10·DGS3MO | 봉인된 KR 스냅샷에 이미 커밋됨(VIXCLS는 Cboe 저작권) | 다시 복사하지 않고 그 자리에서 재사용. 봉인 바이트라 수정하지 않는다 |

- 새로 받은 원본 바이트는 **암호화된 Actions 산출물 하나**에만 존재한다(`openssl` AES-256-CBC, PBKDF2 60만 회, 저장소 비밀 `RP1_C1_SNAPSHOT_KEY`, 보존 90일).
- Git에는 날짜·건수·해시만 담은 매니페스트(`docs/research-program/sources/rp1-c1-us-source-freeze-<runId>.json`)가 들어가고 사양이 그것을 고정한다.
- 결과물은 집계 통계뿐이며 일별 가격·지수·NAV 계열은 공개하지 않는다.
- 이 분류는 공급자가 공개한 조건을 읽은 요약이며 법률 자문이 아니다. 불명확하면 제한으로 다룬다.

### 6.3 품질·동일성 관문 (결과 열람 전, 날짜만)

- 기준 지수: XNYS 세션 누락 0, 위기 창 커버리지, 중복·무효행, 신원(심볼·통화·시간대·`instrumentType` INDEX). 등록된 XNYS 휴장일(2001-09-11~14, 2012-10-29·30 등)이 달력상 세션이 아닌지와 기준 지수 행이 그날에 없는지 확인한다.
- 교차검증: `^GSPC`와 FRED SP500의 같은 날짜 수준(2016년 이후).
- SPY 기업행동: 배당 이벤트 날짜가 SPY가 호가한 XNYS 세션에 있는지, 분할 이벤트가 없는지 확인한다(날짜만). 금액과 조정 종가를 종가+배당과 맞춰 보는 대조는 잠금 이후의 고정 진단(`spyBasisDiagnostic`)이다.
- 현금: DTB3 단위 `Percent`, 빈도 `Daily`, 평가 세션마다 알려진 금리.
- 실패 시 기준 지수·교차검증은 실행 차단, SPY·DTB3·기업행동은 경제적 독해만 `UNRESOLVED`(사전 고정 중단 기준 그대로).

### 6.4 실행 순서와 사람이 할 일

1. **소유자:** 저장소 비밀 `RP1_C1_SNAPSHOT_KEY`를 만든다(무작위 32바이트 이상). 없으면 동결·드라이런·실행이 모두 거부된다.
2. 이 PR 병합 후 `rp1_c1_action=freeze-sources`로 main에서 실행한다. 준비도가 READY일 때만 암호화 산출물을 올리고 매니페스트와 다시 고정한 사양을 담은 Draft PR을 하나 연다. 그 PR을 검토하고 병합한다.
3. `rp1_c1_action=dry-run`: 고정 스냅샷 복호화·해시 검증, 준비도 READY, 동등성 EXACT, 승인 상태를 확인하고 꾸며낸 값으로 전체 평가·검증기·보고서를 돌린다. 잠금 없음, 미국 값 열람 없음.
4. **소유자 승인:** `python scripts/run_rp1_c1_us_wp4d.py authorization-draft --owner <login>`이 사양·과학 다이제스트·원천 동결·하네스 파일 해시를 출력한다. 소유자가 검토하고 확인 항목 7개를 직접 `true`로 바꿔 `docs/research-program/authorizations/rp1-c1-us-exposure-execution-authorization.json`으로 커밋한다(검토된 PR). 템플릿은 `NOTHING`만 승인한다.
5. **소유자 실행:** main에서 `rp1_c1_action=execute`, `rp1_c1_authorization_sha256` = 커밋된 승인 파일의 SHA-256. 첫 시도, 소유자 계정, main 최신 커밋에서만 진행된다. 순서: 승인 → 스냅샷 해시 → 준비도 READY → 동등성 EXACT → **원자적 잠금 ref 2개** → 마커 → 첫 미국 값 열람 → 평가 → 독립 검증기 → 보고서.
6. 잠금 이후 실패는 연구를 소진한다. 재시도하지 않는다. 결과는 산출물(90일)과 작업 로그(gzip+base64)에 함께 남는다.
- 산출물이 만료되면 새 동결(새 매니페스트·사양 해시·승인)이 필요하다. 옛 고정 아래 다시 받는 일은 없다.

### 6.5 독립 검증기와 비교 보고서

- `pipeline/rp1_c1_us_validator.py`는 평가 모듈의 함수를 쓰지 않고 거래 규칙(목표 × 비용 차감 NAV, 비용은 현금에서)을 다시 유도해 모든 경로를 자체 루프로 재현한다. CAGR, MDD, 월간 CVaR 5%·최악 월, 총비용과 비용 손실(총-순 CAGR), 축소 세션 비중, 평균 주식 비중, 상승장 비용·하락장 절감(연), ≥15% 낙폭별 반등 놓침 H63/H126, 완전 노출까지 세션, 회복 기회비용을 상대오차 1e-9로 대조한다. 하나라도 어긋나면 결과를 검증된 것으로 내지 않는다.
- 공유하는 것은 상태 규칙(층 상태, 결정 일정, 후보 목표, 현금 금리 지연)뿐이며, 이것은 KR 동등성이 봉인 연구와 같음을 증명한다.
- 보고서(`report.md`)는 PASSIVE와 C0~C3를 1차 독해(가격지수, 현금 0)와 경제적 독해(SPY 총수익, DTB3)에서 같은 지표로 나란히 놓고, 동결 결정과 사전 고정 해석표의 판독을 기계적으로 적는다.
- 꾸며낸 값의 드라이런(합성 표시)에서 검증기 236개 대조가 모두 일치했다. 이것은 기계 점검이며 시장에 대한 결과가 아니다.

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
python scripts/run_rp1_c1_us_wp4d.py dry-run --output /tmp/rp1-dry   # 잠금·미국 값 없이 전체 파이프라인(합성 값)
pytest -q tests/test_rp1_c1_us_exposure.py tests/test_rp1_c1_us_wp4d.py
```
