# Decision Optionality Research v1

**합성 의사결정 검증 완료 / 새 역사 성과 실행 미승인 / 실전 추천 아님.**

좋은 종목을 찾는 문제와 같은 후보를 언제 매수·유지·교체할지를 분리한다. 이번에 가장
추가 정보가 필요한 지점은 **보유종목의 남은 우위와 대체 후보의 우위 차이**다. 종목 수를
유연하게 고르는 기능 자체는 이미 구현되어 있다. 거래 감소가 경제적 개선이라는 결론도
아직 없다. 새 allocator·팩터·학습기·역사 backtester는 만들지 않았다.

기준은 최신 main `a92b0808197fbc272b450ea631836fb613c47c84`(#250 병합)이다. 독립 브랜치
`research/decision-optionality-v1`에서 작업했다. Claude의 시장위험·ETF 노출(#249) 및
Winner & Inflection Discovery(#250)의 코드·브랜치·결과 경로를 변경하거나 의존성으로
삼지 않는다. 공통 기반 #247과 연구 계약 #248만 재사용한다. production 선택기·비중·주간
영수증·workflow·봉인 사양·기존 결과 파일은 모두 그대로다.

## 결과 전 고정과 증거 경계

- [protocol-v1.json](protocol-v1.json)과 [SHA-256](protocol-v1.sha256)을 `d9247d7`에서 먼저
  커밋한 뒤 새 합성 비교를 실행했다. D1/D3/D4가 1차 가족이고 D2는 이미 연구된 기제의
  기술적 재현이다. 공통 계약의 Study당 1차 가설 상한 3개를 유지한다.
- 작성 전에 기존 공개 연구 결과를 읽었다. 따라서 이 설계는
  `DESIGN_AFTER_PUBLIC_RESULT_EXPOSURE`이며 untouched 사전등록·독립 OOS가 아니다.
- 새 역사 가격·미래 수익률·백테스트 outcome은 읽지 않았다. 아래 역사 숫자는 기존 공개
  문서의 집계 인용이다. 원 ledger를 열어 재계산하지 않았다. CI가 요구하는 고정 Git 입력
  객체 준비와 기존 회귀 검증은 새 정책의 역사 성과 실행과 구별한다.
- 실행 함수는 입력 검사보다 먼저 `scope != SYNTHETIC`을 거절한다. 실제 증권 키도
  거절한다. 역사 입력 reader/fitter·영수증 writer·실행 승인·잠금·자동 승격 경로가 없다.

## 이미 구현된 자유와 빈칸

| 자산 | 현재 구현 | 이번 연구가 더 측정할 것 |
|---|---|---|
| `weekly_decision.decide/score_candidates` | 지역별 0~5종목, 각 15%, 잔여 SPY/069500.KS. usable 보정과 양의 순우위가 없으면 ETF 100% | 진입을 거절한 시점의 ETF 기회비용과 강제 편입의 손익을 동일 정보로 비교 |
| 같은 모듈의 incumbent credit | `switchCostPct`를 incumbent 점수에 가산. **자격 판정 뒤** 적용해 미적격 보유를 구제하지 않음 | 순위 크레딧과 실제 두 종목 간 교체 한계가치는 다름. 남은 alpha·불확실성·양쪽 비용을 분리 |
| `kelly_portfolio.select_portfolio_by_scores` | 기존 종목/섹터/지역 제약, 결정론적 tie break | 그대로 호출. 후보 발굴·상한·가중을 바꾸어 정책 효과로 세지 않음 |
| `benchmark_alpha`, `switch_hurdle` | 날짜별 비용 차감, 신규 후보 비용과 보유자 매도비용 크레딧. 별도 연구의 SE 문턱 | 과거 성공을 새 정책의 증거로 전용하지 않고 대조군 차이와 불확실성을 기록 |
| 주간 관측·append-only receipt | 새 영수증과 stale/no-decision 구별. 매주 신호를 보되 이전 보유 집합을 전달 | `decide`는 목표 비중을 매번 15%로 복원. 실제 drift를 받아 HOLD/REDUCE/교체/단순 복원을 구별 |
| `selection_value.decompose_edge/decompose_turnover` | 산술 선택/복리, 종목 변경/비중 재조정 분해 | 새 역사 executor가 이 평가기를 재사용하도록 계약. 지금은 연율 경로를 만들지 않음 |

0종목은 현금 보유가 아니다. 위험 ETF에 100% 남을 수 있으므로 시장 하락 회피 기능으로
설명하지 않는다. 시장 노출·위기 방어 규칙을 더하는 것은 이번 연구 밖이다. 보유기간은 이미
고정 만기 청산이 아니며, 이번에 새로 주장하는 자유는 관측·목표·실제 주문을 분리하는 것이다.

## D1~D4: 고정 비교와 검증 가능성

| 가설 | 같은 정보로 바꾸는 한 축 | 중복과 새 가치 | 현재 평가 가능성 |
|---|---|---|---|
| D1 선택적 진입 | ETF / CURRENT / FORCED_FIVE. 강제군은 `EXPECTED_NET_ADVANTAGE_NOT_POSITIVE`만 제거 | 0~5 자체는 기존 기능. 강제 슬롯 대비 **진입 거절의 가치**가 새 비교 | 합성 검증. 신뢰 가능한 기대값이 없는 강제 편입은 수행하지 않음. 5개 미만이면 shortfall |
| D2 보유 유지 | CURRENT / NO_CREDIT. 점수의 유지 크레딧만 제거 | switch-hurdle·alpha-reliability와 중복. 새 성과 발견으로 세지 않음. 실제 교체의 남은 alpha 차이 audit가 추가 | 기존 공개 집계와 합성. 남은 alpha가 없어 역사 한계가치 미측정 |
| D3 매수·매도 비대칭 | SYMMETRIC / ASYMMETRIC. 같은 진입 문턱·순위·구조적 자격, 보유의 경제적 문턱만 변경 | 유지 크레딧은 순위만 바꾸지만 D3는 기존 보유의 자격 문턱을 분리 | 합성만. 동일 forward H126의 남은 기대초과수익·불확실성·당시 thesis 상태 공급자가 필요 |
| D4 관측과 거래 분리 | CURRENT / EVENT_ONLY. 선택 집합이 같으면 drift 유지, 이름 변경 때는 같은 현재 목표 | retarget 회피는 기존 turnover 분해의 작은 구성요소. 고정 보유기간을 새로 최적화하지 않음 | 합성 검증. 15%를 넘은 drift는 두 군 모두 cap 복원. 실제 거래·NAV 경로는 후속 승인 |

D3의 양 군 신규 매수는 `remainingExpectedExcess - radius > fullSwitchCost`다.
SYMMETRIC은 보유에도 같은 문턱을 요구하고 ASYMMETRIC은
`remainingExpectedExcess - radius > -(stockSell + ETFBuy)`이면 보유할 수 있게 한다.
투자 가설이 false면 양 군 모두 청산하고, unknown이면 비교를 `NOT_ESTIMABLE`로 차단한다.
조건을 통과해도 순위·섹터 제약에 의해 교체될 수 있어 무조건 보유 우대가 아니다.

EVENT_ONLY의 이벤트는 **선택된 이름 집합의 변경**이다. 새로운 정보의 경제적 중요도를
판단하는 모델을 추가한 것이 아니며, 정보가 바뀌어도 이름 집합이 같으면 비중 복원을
생략한다. 정보 hash와 보유 hash를 별도로 남겨 후속 연구가 이 둘을 혼동하지 않게 했다.

`radius`는 합성에서 주어진 보수적 오차 반경이다. 표준오차/신뢰구간이라고 부르거나 통계적
보장으로 해석하지 않는다. 역사 적용에는 별도로 검증된 정의·포괄확률이 필요하다. 두 후보의
오차 공분산이 없으므로 교체 audit는 두 radius의 합을 차감하며 가짜 차이의 SE를 만들지 않는다.
현재 production 보정의 비용조정·universe carry/보수적 spread 기준도 **실제 gross ETF 초과수익과
자동으로 같지 않다**. 이를 확정하지 않고 D3 공급자로 사용하거나 다시 비용을 중복 차감하지 않는다.

## 최소 실행 인터페이스

코드는 [decision_optionality.py](../../pipeline/decision_optionality.py), 실행기는
[run_decision_optionality.py](../../scripts/run_decision_optionality.py)다.

`Frame`은 공통 `experiment_workbench.Observation/Key/Source`와 후보, 실제 drift 비중,
기존 보정, 선택적으로 `RemainingForecast`를 받는다. 모델 예측은 발견 점수와 별도다.
각 정책 결과에는 다음이 함께 있다.

- 결정시각·지역 신호일·그 지역의 다음 거래 가능 세션, 공통 sample/information hash
- 후보·보유자의 당시 정보, 기존 bucket 추정과 별도 남은 기대초과수익/불확실성 또는 부재 사유
- 거래 전 보유와 거래 후 목표, `WAIT_ETF/BUY/HOLD/REDUCE/EXIT/REPLACE`, 판단 이유
- 매도와 매수의 identity 정렬 짝에 대한 교체 audit. 짝짓기는 **사후 기여 분류**이며 선택 알고리즘 아님

실제 비용·ETF 기회수익은 결정 시점 필드에 채우지 않는다. `evaluate`가 **그 뒤** 별도 합성
수익률을 받아 다음 세션 날짜의 주식/ETF 각 leg를 기록한다. 비용률은
`weekly_decision.trade_cost_fraction`, 비용·편도 회전율·종목 거래 합계는 기존 주간 replay의
`_leg_cost`와 일치해야 한다. ETF 순수 보유도 초기 매수비용을 지불한다.

각 leg에는 비용 합계와 별도로 당시 기본 commission·half-spread·sell-tax bp를 기록한다.
스트레스 배수는 보고서의 `costMultiplier`이며 기본 bp를 정책의 다른 비용표로 바꾸지 않는다.
`stockOrderLegs`는 비중 복원까지 포함하고 `nameTrades`는 이름 entry/exit만 세므로 서로 다르다.

현재 evaluator는 발명한 **한 구간**만 검증한다. `before`는 이 합성 체결 직전 비중이고,
신호일~체결일의 가격 drift는 가정하지 않는다. 실제 역사에서는 수량·가격으로 체결 직전
비중을 새로 표시해야 한다. 다일 NAV·MDD·연율·검정은 구현하지 않았다. 이 빈칸을 가짜
성과표나 고정 기간 CAGR로 채우지 않는다.

한국 날짜별 거래세와 ETF 거래세 면제를 재사용한다. 미국 0.30bp는 기존 regulatory-fee proxy다.
개인별 양도소득·배당·환전 세금은 **미측정**이며 0이라고 추정하지 않는다. 개인별 세후
최적화나 실현손익 절세를 주장하지 않는다. 기존 매입 원가·세금 lot가 없으므로 세금 때문에
보유해야 한다는 실전 판단도 하지 않는다.

## 합성 검증 결과

[synthetic-results-v1.json](synthetic-results-v1.json)은 양 시장 8개 시나리오의 압축 출력이다.
입력·코드·사양 hash와 전체 시나리오 digest를 보존했다. 가상의 다음 구간 주식수익 +10%/−10%,
ETF +2%를 같은 결정 뒤에 각각 적용한다. 미래 수익이 바뀌어도 결정은 변하지 않는다.

| 검증 | 확인된 행동 |
|---|---|
| D1 작은 우위 | CURRENT는 ETF 100%, 강제군은 5개. 보정 부재·차단 진입상태를 강제로 통과시키지 않음 |
| D2 경계 순위 | 크레딧은 incumbent를 유지, 제거군은 SYN5로 교체. 같은 기대 alpha의 미국 교체 audit는 비용 −0.163pp, radius 합까지 −0.363pp |
| D3 작은 남은 우위 | 대칭군은 EXIT, 비대칭군은 HOLD. thesis false면 양 군 EXIT. 필요한 추정/상태 부재면 목표 자체를 발행하지 않음 |
| D4 14%→15% 복원 | CURRENT는 1% 매수와 ETF 매도, EVENT_ONLY는 HOLD·비용 0. 이후 주가가 오르면 순수익이 오히려 낮고 내리면 높음 |
| 16% drift | EVENT_ONLY도 15%로 REDUCE. 노출 상한을 매매 회피 명분으로 넘기지 않음 |
| 공통 표본 | ETF 정책도 미선택 후보의 수익이 빠지면 평가 거절. 정책별로 유리한 결과 마스크를 만들지 않음 |
| 정보·시점 | 자기 거래소 휴일·다음 세션 사용, 미래 forecast·미완료 신호·실제 증권 identity 거절 |
| 부작용 | 동일 입력 재현, 후보 순서 무관, KP의 nested exclusion-list 변경으로 원본 입력이 오염되지 않음 |

0~5종목 경로 각각을 합성으로 실행했다(각 1개). 이것은 역사 선택 빈도나 현금 대기 확률이
아니다. 1×/2×/3×의 실제 leg 비용 배율도 테스트했지만, 비용 변화에 따라 정책까지 재결정한
역사 스트레스 결과를 주장하지 않는다. 모든 결과는 추천이 아니며 production 연결도 없다.

```bash
cd /workspace/Investment
source /workspace/.venvs/investment/bin/activate
python -m scripts.run_decision_optionality --summary
pytest -q tests/test_decision_optionality.py
```

## 재사용한 공개 경제적 근거

아래는 기존 표를 읽은 근거 목록이다. 새 역사 실행이 아니며 시장·시기·정책이 다른 값을
하나의 메타분석으로 합치지 않는다.

| 출처 | 기존 공개 관측 | 이번 설계의 함의와 한계 |
|---|---|---|
| [weekly-passive-first-v1](../weekly-passive-first-v1.md) | KR 주간 713회 중 709회 ETF 100%. 공식 대조 ETF 기준 P1 순 CAGR 12.04%, P0 12.51%(약 −0.46pp). US 종목 편입 0회 | 선택적 진입은 이미 있음. 유연성이 있다는 것과 경제적 우월성은 다름. 활성 4주만으로 안정적 정책 효과를 추정하기 어려움 |
| [selection-value](../results/selection-value-report.md), AGENTS v2.11 | 기존 challenger +0.340pp 총 기하차 중 산술 선택 +0.040, 복리 +0.300. turnover 92~93%가 이름 변경 | D4 단순 retarget 절감의 상한이 작을 가능성. CAGR 개선을 선택 알파라고 부르지 않음 |
| [switch-hurdle](../results/switch-hurdle-report.md) | 자체 동일-loop control 대비 순초과 차이 +2.757pp, 95% 구간 [0.122,5.732]. 비용 drag 절감 +0.270pp, 산술 선택 +2.157pp. 1SE군 MDD −35.036% | D2의 기계적 수수료 절감 밖 경로가 유망한 이유. 그러나 단일 노출 역사·여러 시도·다중성 보정 부재. 기존 published control과 harness 차이도 있음. 더 강한 보유 우대는 반례 |
| [alpha-reliability](../alpha-reliability-v1.md), AGENTS v2.13 | 같은 alpha swap은 arriving−departing −2.601%/21일 블록(n=39), 구간 [−5.510,+0.024]. 신호 hysteresis는 turnover 4.535→2.955배·cost drag 1.330→0.847pp, 추가 순차이 +0.288pp 구간 [−4.430,+5.416] | 오차 반경·남은 alpha를 기록할 동기. 행동 변화와 순성과 지지를 구분하며 두 구간 모두 0 포함 |
| [동적 breadth](../../AGENTS.md) v2.15 | 고정5 대비 dynamic 3~10의 순차이 −0.317pp, 구간 [−2.133,+1.425] | 종목 수를 유연하게 바꾸는 것만으로 개선되지 않음. 현재 0~5에 그대로 이전할 수 없음 |
| [#245 미국 파일럿](../us-decision-pilot-v1-ko.md) | B2 순16.95% vs SPY21.05%, 강제5 B2 12.77%; 양방향 turnover B2 6.59배 vs 강제5 13.07배 | 집중·교체·가중·유니버스를 함께 바꾼 비교라 D1 인과 증거 아님. 강제5가 개인투자자에게 유리하다고 가정하지 않음 |
| [#245 감사 부록](../us-decision-pilot-v1-audit-appendix-ko.md) | B2−SPY −3.446 로그pp/년. 동일가중+가격가용 집합 전환 −5.92, 자기 완전사례 안 선택 +4.12(업종 +2.09/내 +2.03), 비용 −0.54 로그pp | 중간 바스켓·무작위 seed·원 계산물 미확보인 **감사 보고값**. 끝점과 감사의 재현 범위를 구별. SPY 미달을 곧바로 발견 모델 실패로 돌리지 않음 |

#245의 무작위5 평균 16.19%, 실제 약40백분위는 **비용 전** 비교다. 비용 후 12.77%를 그
분포에 대입하지 않는다. 수익성 두 군의 상관 0.78·명목40% 중복, PARA 정체성, 미국 BS 결손,
survivor-conditioned 표본과 내부 재구성 총수익 기준도 그대로 남는다. 감사 원 계산물이
없으므로 새 독립 재현·선택 알파 발견으로 승격하지 않는다.

## 후속 실제 비교의 측정 정의

1차는 **동일 달력기간의 연 산술 순활성수익 차이**(정책−대조)다. 각 arm의 지역 ETF 대비
순활성수익도 함께 제시한다. gross 차이와 비용 차감에 따른 NAV drag를 분리한다. 비용을
0으로 둔 회계 shadow는 **같은 결정 tape**를 유지하며 다시 선택하지 않는다. 비용 절감만큼
좋아졌는지, 보유를 바꾸어 생긴 gross 손익도 좋은지 구별한다.

| 지표 | 정의/필수 분모 |
|---|---|
| 연 거래·교체 | 주식 주문 leg 수/실제 경과 연수. 최초 funding 별도. 주간 departing/직전 보유 수와 entering 수를 모두 보고, 기존 보유 0이면 교체율 부재 |
| turnover | 전체 자산 절대 비중 변화 합의 1/2. 종목 entry/exit와 공통 종목 retarget 분리, ETF leg 별도. 주식만의 L1과 혼용 금지 |
| 교체 비용 | 실제 체결일의 departing sell + arriving buy. ETF 재조정과 개인세 미측정은 별도. 초기 편입을 교체 절감으로 세지 않음 |
| 선택 빈도 | 결정 가능 날짜 분모에서 0~5 각각. blocked/missing 날짜 수와 공통 비교 가능 날짜를 별도 공개 |
| ETF 대기 | 세션별 실제 ETF 비중 시간가중 평균. ETF100% 연속 spell의 세션/달력기간, 우측 검열 여부 |
| 유연한 보유기간 | 실제 entry~exit 세션, 아직 보유 중이면 검열. H126 강제 청산을 이번 비교에 추가하지 않음 |
| 조기 매도 regret | 체결 뒤 고정 forward H126에서 매도한 이름−실제 대안(신규 이름 또는 ETF)의 순기회손익. 양/음 모두, 표본 수와 미해결 사유 |
| 늦은 매도 regret | 같은 고정 H126에서 유지한 이름−ETF의 signed 손익과 음의 부분. 계속 HOLD한 주를 독립 표본으로 합산해 가상의 누적 손실로 만들지 않음 |
| 회피 거래의 가치 | 같은 시작 보유에서 actual decision과 control의 순 NAV 차이, gross 및 fee drag 별도. 사후 불리했던 거래만 골라 피할 수 있었다고 주장하지 않음 |
| 위험조정 | 연속 수량 NAV의 MDD/vol/downside/ETF 상대 노출. 복리 항과 산술 선택 별도. 위험을 줄이고 수익을 잃으면 tradeoff로 표시 |

대조군마다 자신의 보유 경로가 달라지는 **총 정책 효과**와 같은 시작 보유로 리셋한 **단일
결정 효과**를 별도 표에 둔다. 후자를 이어 실제 투자 가능 NAV처럼 보이지 않는다. 사후 최적
행동은 diagnostic regret에만 쓰고, 입력·점수·문턱에 들어갈 수 없다.

## 역사 실행 또는 전향 비교를 시작하려면

현재 실행 승인은 없다. 프로토콜의 `historyPrerequisites`가 체크리스트이며 이 PR 병합으로
해제되지 않는다.

1. 별도 owner 승인 실행 PR에서 코드/사양/의존성/원천/표본 hash, 시장·기간·fold·H126·seed,
   결측·검열·민감도·시도 예산을 고정한다. 결과 열람 전 MDE와 이 정책 추정량의 합성 구간
   포괄확률을 검증한다. 미보정 시장·추정량은 기술통계만 허용한다. D1/D3/D4 Holm .05,
   평가 불가 슬롯 p=1, D2 기제·보조 구분을 유지한다.
2. KR 닫힌 역사 연구를 새 이름으로 재개하지 않는다. 기존 정책-only 데이터 재사용의 범위도
   명시적 owner 판단이 필요하다. 허용되지 않으면 새 전향 paper 기록만 진행한다. 이미
   노출된 미국 역사도 chronological split만으로 독립 확증이 되지 않는다.
3. 승인된 expected-excess/uncertainty 공급자와 보유종목 **남은** forward H126 예측을 마련한다.
   새 팩터·재보정 연구와 결합하지 않는다. thesis 사건도 당시 가용시각과 출처가 있어야 한다.
4. #247 `LabelReference/Fold/Economics`, #248의 최초 공개·다음 세션·purge·공통 표본 계약을
   재사용한다. 실제 evaluator는 기존 `replay_valuation`, `portfolio_validation`,
   `selection_value`를 연결한다. 결과 가용성으로 후보 순위를 뒤늦게 바꾸지 않는다.
5. US departed/재사용 신원·KR 종결22개 등 미해결 대가, 주식과 ETF 양쪽 분배/기업행동/총수익
   정의를 admission한다. #245/#247의 생존편향·외부 benchmark 대조 미완료를 면제하지 않는다.
   결측 보유를 마지막 가격·0·ETF 수익으로 바꾸지 않는다.
6. preview는 #247 `preview_manifest`로만 작성하고 승인으로 해석하지 않는다. 실행 전 원자적
   one-shot lock, 결과·시도 보존, 실패 후 정확 바이트 복구 조건을 구현한다. workflow census가
   봉인된 상태이므로 새 workflow는 owner의 별도 버전 census 결정 없이는 추가하지 않는다.
7. 전향 경로도 실제 수집/저장 이용권·영속 root·secure binding·append-only emitter 승인과 실제
   관측시각이 필요하다. 지금은 vendor 수집·주문·receipt 발행을 활성화하지 않았다.

## 우선순위와 반증

**우선 D2의 ‘교체에 경제적 이유가 있었는가’ 진단, 다음 D3의 진입/청산 경계 분리**다.
D2는 이미 비용 절감보다 큰 gross 선택 차이가 보고되어 추가 질문의 근거가 가장 구체적이다.
같은 alpha인 swap이 왜 일어났는지를 남은 예측과 오차에 연결하면 순위와 의사결정의 구분을
검증할 수 있다. 다만 D2 자체의 새 역사 우월성 실험으로 재포장하지 않으며, 이번 audit는
정확한 pairwise 최적 교체 정책을 실행하는 것이 아니다.

D3는 이미 지불한 진입비용과 앞으로 드는 청산비용을 구분할 수 있는 새 정책 축이다. 잠재
경제적 규모는 있지만 남은 alpha와 thesis가 검증되지 않아 **현재 실증 순위를 매길 수 없다**.
투자 가설이 유효하다는 판단만으로 기대수익을 양수로 생성하지 않는다.

반증은 명확하다. 유지로 놓친 신규 종목의 상승이나 지연 청산의 손실이 절감 비용보다 크고,
paired 순활성수익이 0 이하이거나 MDD가 악화되면 제안된 경제적 개선을 지지하지 않는다.
거래가 감소해도 그 판정을 바꾸지 않는다. 0 포함 구간은 `CONTAINS_ZERO`, 음의 점추정은
음수 그대로 보고한다. D1의 활성 결정이 거의 없으면 미식별/저검정력이며 성공으로 세지 않는다.
D4는 기존 비용 분해상 기대 규모가 작고, 합성 반례도 있으므로 우선순위가 낮다.

## 검증 기록

Python 3.12.14, pandas 2.3.0, NumPy 2.3.1, exchange-calendars 4.11.1, pytest 8.4.1,
ruff 0.15.8을 저장소의 고정 requirements로 별도 venv에 설치했다. 필수 전체 검사와 실행
결과는 [validation.md](validation.md)에 기록한다. 합성 결과를 production artifact에 쓰지 않았다.

과학 규칙의 사후 변경은 없었다. 구현 검토에서 control 반환 필드, 빈 초기 funding의 ETF
target, 전체 후보 exclusion audit, 초기 ETF 비용 비교, 하드코딩 계수 대신 reader/fitter
접근 금지 테스트 및 상속된 OOS 설명의 합성 표기를 보완했다. 이들은 고정된 v1 계약을 구현하는 수정이며 새 문턱·후보·모형을
탐색한 것이 아니다. 결과를 보고 과학 규칙을 바꾸는 경우에는 v2와 변경 사유가 필요하다.
