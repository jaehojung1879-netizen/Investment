# Investment Research Dashboard — v3 (paperTrading 기본)

출처가 분명하고 시점이 일치하며 사후 검증 가능한 투자 **리서치** 대시보드입니다. 종목을 많이 추천하는 사이트가 아니라, 세계적 자산운용사·매크로 전략가가 쓰는 방식(국면→위험예산→지역별 팩터 리서치→진입상태→사후검증)에 가깝게 설계했습니다.

## 실행 상태(runMode)와 데이터 모드(dataMode)

- **runMode**: `researchOnly` · `paperTrading`(기본) · `liveValidated`. 기본값은 `paperTrading`이며, **`liveValidated`는 config만으로 절대 부여되지 않습니다** — paper signal ledger에 충분한 검증 이력이 쌓여야 합니다.
- **dataMode**: `live` · `seed` · `stale` · `synthetic`. 화면에 데이터 모드와 **빌드 커밋 SHA**를 항상 표시합니다.
- README·빌드·검증 코드·화면 문구가 **동일한 안전 상태**를 표현합니다. (과거의 “README는 PAPER ONLY인데 build는 paperOnly=false” 불일치를 제거했습니다.)

화면은 `오늘의 결론 → 포트폴리오 상세 → 기회·경고 레이더 → 선정 과정 → 리서치 후보 → 시장·국면 → 검증·방법론(Validation Lab 포함)` 일곱 블록입니다. 첫 화면은 **보유 3~5종목과 각 종목의 무효화 조건**으로 시작하고, 근거 자료는 전부 접힌 fold 한 줄로 내려가 목록이 결론을 덮지 않습니다. 기술 상태 코드는 상세에서만 보여주고 기본 화면에는 `검증 데이터 축적 중`, `Paper 운용 중`, `안전 차단` 같은 사용자용 상태를 표시합니다. `선정 과정` 블록의 **방법론 적용 현황**은 어떤 층이 실제로 켜져 있고 어떤 층이 왜 아직 아닌지를 그대로 나열합니다. 글로벌 마켓 카드는 현재값·1일 등락과 **3M 추이·3M 수익률**을 분리하며, 상세 차트 기본 기간도 3M입니다.

## 정직성 원칙

- 모든 산출물에 `schemaVersion`, `modelVersion`, `buildCommitSha`, `generatedAt`, `marketAsOf`, `sourceAsOf`, `runMode`, `dataMode`를 기록합니다(`provenance`).
- `recommendationsBlocked=true`이면 단기 아이디어뿐 아니라 **장기 picks/holdings·슬리브 비중·entryState·행동성 사유를 모두 차단**합니다. 화면에는 “데이터 검증 전으로 진입 판단을 제공하지 않습니다”라는 비행동성 상태만 표시됩니다.
- seed/synthetic/stale 데이터는 실데이터처럼 보일 수 없도록 dataMode로 명확히 구분하고, production 검증에서 non-zero exit로 실패시킵니다.
- ‘추천 비중’ 대신 **modelSleeveWeight**(완전 투자된 가상 모델 슬리브 내 비중)라고 표기합니다 — 개인 포트폴리오 추천 비중이 아닙니다.

## 장기 종목선정 엔진 v2

- KR·US를 **지역별로 독립 z-score** 산출(서로 직접 비교 금지). 지역 배분은 매크로 위험예산 레이어가 담당합니다.
- ETF·벤치마크(QQQ, SPY 등)는 개별주식 랭킹에서 제외.
- 팩터(모멘텀·밸류·퀄리티·저변동)는 **섹터 내 중립화** z-score 우선. 금융·유틸리티 등은 레버리지 페널티 예외 처리.
- `evidenceCoverage`·`dataCompleteness`·`sourceQuality`를 별도 산출해 근거가 약한 알파를 축소합니다. 이 값은 예측확률이나 통계적 신뢰도가 아니며, 실증 이력은 `empiricalValidationStatus`로 별도 표시합니다. 3개 슬리브·최소 재무 완전성 미달 시 `DATA_INSUFFICIENT`입니다.
- 리서치 슬리브는 **6~12종목 + 단일종목 상한 + 업종 상한 + 현금 하한**의 후보 목록입니다. 실제 보유는 여기서 다시 3~5종목으로 좁힙니다(아래 참조).
- 위험지표(하방변동성·최대낙폭·CVaR·베타)를 알파와 **분리 표기**. 알파와 위험·진입 페널티를 한 점수로 섞지 않습니다.
- **무효화 조건은 종목마다 다르게 계산합니다.** 상대 순위는 rank buffer의 편출선, 논리를 떠받치는 팩터는 그 팩터의 중앙값, 추세는 12-1M·200일선, 꼬리위험·최대낙폭은 **해당 지역 횡단면 분포**(90/10퍼센타일), 데이터는 슬리브·재무 커버리지 하한이 기준선입니다. 이미 넘긴 조건은 `BREACHED`로 표시합니다.

## 후보에서 보유로 — 3~5종목 집중

리서치 후보를 그대로 담으면 24종목짜리 지수 흉내가 됩니다. 포트폴리오는 별도의 선정 단계를 거칩니다.

1. **컨빅션 점수** `= (알파 백분위 − 50) ÷ 50 ÷ 하방변동성 × 근거 커버리지 × 진입상태 배율`. 알파 백분위는 횡단면 순위이므로 이 값도 **랭킹 점수이며 기대수익률·샤프비율 예측이 아닙니다**. 근거 커버리지와 진입상태 배율은 점수를 줄이기만 합니다.
2. **자격 필터** — 알파 백분위 하한(기본 66p), 진입상태·리서치 상태, 팩터 근거 유무.
3. **분산 상한** — 동일 업종 최대 2종목, 동일 지역 최대 3종목.
4. **목표 종목 수 절단** — 기본 5종목. 탈락 종목도 `selection.ranking`에 사유(`SECTOR_NAME_LIMIT`, `BELOW_TARGET_COUNT_CUTOFF` 등)와 함께 남습니다.
5. **비중** — 하방변동성 역가중 + 컨빅션 순위 0.5~1.5배 선형 틸트 → 단일종목 30%·업종 45%·테마 45%·지역 상한 적용.

현금 하한은 `max(설정값, 국면별 하한, 100 − 매크로 주식예산 상한)`입니다. 매크로 위험예산이 주식 20~45%면 포트폴리오도 45%를 넘지 않으므로, 두 층이 한 화면에서 다른 숫자를 말하는 일이 없습니다.

집중의 대가는 `concentration`으로 함께 발표합니다: **유효 종목수 = 1 ÷ 주식비중 허핀달지수**, 상위 1·3종목 비중, 그리고 종목 수 3 이하·유효 종목수 2.5 미만·1위 종목 40% 초과 시의 경고. 이 배분은 Kelly가 켜지기 전에도 작동하며, Kelly가 활성화되면 같은 보유 집합 위에 25%로 혼합됩니다.

## ‘좋은 종목’과 ‘지금 살 종목’ 분리

- `longTermResearchView`: `POSITIVE` · `NEUTRAL` · `NEGATIVE` · `DATA_INSUFFICIENT`
- `entryState`: `ACCUMULATE_GRADUALLY` · `WATCH` · `WAIT_FOR_PULLBACK` · `EVENT_RISK` · `AVOID` (추세·이격·유니버스 내 과열 백분위·변동성 급등·갭·실적 이벤트·집중도 반영)
- 회전율을 줄이는 **rank buffer**(config.longterm.rankBuffer): 신규 편입은 상위 enterPct, 기존 편입은 exitPct 아래로 내려갈 때까지 유지.
- 이전 holdings와 priorRegime은 저장소의 preview JSON이 아니라, production 검증과 Pages 배포가 모두 성공한 뒤 `signal-history:state/latest.json`에 기록된 상태만 사용합니다. 상태 없음·synthetic·버전 불일치는 빈 prior로 안전하게 동작하며 `priorState.available=false`와 이유를 artifact에 기록합니다.

## 매크로 방향·국면 엔진

**6축 진단**(성장·물가·유동성·금융여건·위험선호·이익/신용)을 표시하되, 국면 라벨은 성장×물가로 판정하고 금융여건·위험선호는 위험예산만 보정합니다. CPI/PCE는 가격지수 수준이 아니라 YoY 및 3개월 연율 인플레이션율의 방향, 고용·실업·청구·M2/Fed assets·스프레드·VIX·커브·WTI는 지표별 변환 레지스트리를 사용합니다. flat/상쇄 신호는 `Transition/Low confidence`입니다. confidence는 coverage·freshness·agreement로 분해하고 평가 as-of 기준으로 계산합니다.

미국 종목 추천은 구성종목 제공 순서와 무관하게 S&P 500 전체를 스크리닝합니다. 전체 목록을 확보하지 못하면 일부 알파벳 구간이나 정적 목록만으로 추천하지 않고 빌드를 실패 처리합니다. `universeSize` 제한은 시가총액순 KOSPI 스크리닝에만 적용됩니다.

팩터 계산 전 티커 순서를 canonicalize하고, 후보·Kelly 절단은 기대 초과수익→알파 백분위→근거 커버리지→데이터 완전성→하방변동성→티커 순의 명시적 tie-break를 사용합니다. 티커는 투자 판단이 아니라 마지막 재현성 기준일 뿐입니다. artifact의 `universeDiagnostics`에는 지역별 확보 수·소스·전체목록 여부·ETF 제외 수·데이터 부족 제외 수·실제 랭킹 수를 기록합니다.

월별·분기 지표에는 보수적인 고정 발표시차를 적용하지만 이는 실제 release calendar를 완전히 재현하지 않습니다. 과거 판정은 ALFRED vintage가 아닌 최신 개정 시계열을 사용할 수 있으므로 완전한 실시간 빈티지 백테스트를 주장하지 않습니다.

## 전문가 컨센서스(반자동, 날조 없음)

`data/expert_sources.json`(기관 레지스트리)와 `data/expert_views.json`(사람이 검증한 요약)에서 **verified=true**이고 stale 하지 않은 의견만 집계합니다. 단순 평균이 아닌 **weighted median + 의견 분산**을 계산하고, 기업 IR은 독립 의견으로 취급하지 않습니다(가중치 하향). 원문 검증 전에는 내용을 만들지 않고 “검증 대기”로만 표시합니다.

## 사후 검증(paper signal ledger)

오늘부터 생성되는 검증용 **전체 eligible cross-section**(UI 상위 15개와 분리)을 변경 불가능한 ledger에 누적합니다. ID는 date×region×ticker×modelVersion이므로 새 모델이 과거 신호를 덮어쓰지 않습니다. US는 SPY, KR은 KOSPI200 계열 벤치마크를 사용하고 동일한 종료 달력일에서 초과수익을 계산합니다. rank IC는 non-overlapping 표본의 각 date×region 횡단면에서 Spearman으로 계산한 뒤 평균·중앙값·hit ratio를 집계합니다. GitHub Actions는 **별도 `signal-history` 브랜치**를 사용해 main 재귀 빌드를 유발하지 않습니다.

`validationStatus`는 paperDays·maturedSignals·eligibleDates·지역별 IC·비용 차감 초과수익·MDD/CVaR·미달 사유를 표시합니다. Kelly 추정과 활성화는 하나의 gate를 공유하며 기본 기준은 paper 252영업일, 만기 신호 100개, HAC 유효 날짜 30개, 관측 날짜 63개입니다. 조건이 채워져도 자동으로 `liveValidated`로 승격하지 않습니다.

## 과거 Point-in-Time 재현 (Historical OOS Evidence)

**과거를 쓰지 않는 것이 정직한 것이 아니라, 과거에서 미래를 보지 않는 것이 정직한 것입니다.** 새 데이터가 1년 쌓일 때까지 기다리는 대신, 2013년부터 오늘까지의 날짜 그리드를 하루씩(기본 주 단위) 다시 살아가며 **그 시점에 실제로 알 수 있었던 정보만으로** 모델을 실행하고 판단을 동결합니다.

- **같은 모델을 재현합니다.** 팩터 정의는 `longterm.score_cross_section`, 진입상태는 `pipeline.entry`, 국면은 `pipeline.regime`을 **그대로 호출**합니다. 재현용 알파 공식을 따로 만들지 않습니다 — 그러면 아무도 운영하지 않는 모델을 검증하게 됩니다.
- **속도와 정확성을 동시에.** 종목별 시계열을 NumPy 배열로 한 번 변환한 뒤 T 시점까지의 후행 윈도로 계산합니다. 모든 지표가 후행 전용(`shift(-n)`·미래 `cummax` 없음)이므로 "잘라서 다시 계산"과 **산술적으로 동일**하며, 그 동치성은 `tests/test_historical_replay.py`가 pandas 원본 함수와 대조해 고정합니다.
- **가격**은 시점 정합적이지만 배당·액면 조정이 현재 기준이므로 `PIT_APPROXIMATE`입니다.
- **재무**는 report period / filing date / **available-from date**를 구분합니다. 무료 소스에는 발표일 이력이 없으므로 현재 스냅샷을 과거에 소급 적용하지 않고 **밸류·퀄리티 슬리브를 제외**합니다(`CURRENT_SNAPSHOT_ONLY`). 팩터 커버리지가 떨어지면 알파는 그만큼 수축합니다.
- **매크로**는 고정 발표시차로 "그날 공개됐는가"는 막지만 개정 이전 값(ALFRED vintage)은 확보하지 못해 `REVISED_HISTORY`입니다.
- **유니버스**는 과거 구성종목 파일이 있으면 상장·상장폐지를 반영하고, 없으면 모든 관측치에 `SURVIVORSHIP_BIAS_UNRESOLVED`를 기록하고 증거 가중치를 낮춥니다.
- 관측치마다 `pitCoverage`·`pitQuality`·`lookAheadCheckPassed`·`survivorshipRisk`를 남기고, PIT 품질이 낮은 관측치는 **Kelly calibration에서 제외**합니다. 다만 커버리지는 *실제로 사용된* 소스에 대해서만 계산합니다 — 쓰지 않은 슬리브의 부재는 leakage가 아니라 커버리지 문제이고, 그 페널티는 `evidenceCoverage`와 증거 가중치에서 별도로 부과합니다.
- **ledger는 완전히 분리**합니다: `ledger/historical/<replayVersion>/`(HISTORICAL_OOS) vs `signals.jsonl`·`outcomes.jsonl`(PROSPECTIVE_PAPER). 두 증거는 절대 한 파일·한 표에 섞이지 않습니다.
- **historical ledger는 월 단위로 쪼개 gzip으로 저장**합니다(`signals-YYYY-MM.jsonl.gz`). 10년치 주간 단면은 단일 JSONL로 쓰면 900MB라 GitHub의 100MB blob 제한에 걸려 push 자체가 거부됩니다 — 실제로 replay 잡이 이틀 연속 계산을 마치고 전량 유실했습니다. 샤드는 결정적으로 직렬화되므로(gzip mtime 고정·행 정렬) 내용이 안 바뀐 샤드는 git이 변경으로 보지 않고, 매일 커밋되는 양은 새로 생긴 샤드뿐입니다. 크기 한계는 push 전에 `historical_store.assert_pushable`이 먼저 잡습니다.
- 기록은 **append-only**이며 `modelVersion`·`replayVersion`·`featureVersion`·`dataVersion`을 함께 남깁니다. 모델을 바꾸면 새 세대가 별도로 쌓이고 기존 기록은 보존됩니다. CI는 **증분 실행**이라 이미 있는 날짜는 다시 계산하지 않습니다.
- 재현에서 빠진 것도 숨기지 않습니다: 단기 LightGBM 점수는 비용 문제로 재현하지 않고 `null`, 실적 캘린더가 없어 `EVENT_RISK` 분기 일부가 비활성, 섹터 로테이션은 ETF RRG가 아닌 구성종목 상대강도 프록시입니다.

### Phase 현황 — 각 Phase는 단독으로 테스트 가능합니다

| Phase | 내용 | 상태 | 무엇이 막고 있나 |
|---|---|---|---|
| **1. Replay Infrastructure** | time-safe replay engine, price-only PIT, historical signal ledger, outcomes, leakage 탐지 | **완료 · 가동** | — |
| **2. PIT Fundamentals / Macro** | publication-aware 재무, vintage-aware 매크로, historical universe | **인터페이스 완료 · 데이터 대기** | 무료 소스에 발표일 이력·ALFRED vintage·과거 구성종목이 없음. `pit_data.FundamentalStore.from_jsonl` / `UniverseHistory.from_json`에 파일만 넣으면 즉시 활성화되고 PIT 커버리지가 올라갑니다. |
| **3. Historical Calibration** | alpha bucket calibration, historical Kelly prior, shrinkage | **완료 · 가동** | 실데이터 replay ledger가 CI에서 채워지면 자동으로 켜집니다 |
| **4. ML Opportunity / Warning** | change feature dataset, walk-forward ML, calibrated probability, radar | **완료 · acceptance gate 대기** | gate 통과 전까지 규칙 기반 점수 사용 (설계된 동작) |
| **5. Prospective Bayesian Update** | historical + live posterior, drift 감지, Kelly 영향도 적응 | **완료 · 가동** | prospective ledger가 쌓이면 자동으로 비중이 이동 |

Phase 2가 비어 있어도 Phase 1·3·5는 정상 동작합니다. price-only 재현의 알파는 모멘텀·저변동 슬리브만으로 만들어지고, 빠진 밸류·퀄리티는 `evidenceCoverage` 축소와 증거 가중치 할인으로 이미 반영됩니다.

## Alpha Calibration과 Kelly 기대수익 posterior

`alpha`·`rawAlpha`·`alphaPercentile`은 여전히 **기대수익률이 아닙니다.** 대신 과거 OOS ledger에 실증적으로 묻습니다: *"이 모델이 미래를 보지 않고 KR 90~95p에 넣었던 종목은 이후 126일 동안 KOSPI200 대비 실제로 어땠는가?"*

- 같은 날 수백 종목은 **날짜 단위로 군집화**하고, 겹치는 126일 forward return은 Bartlett kernel Newey–West/HAC(`lag=horizon-1`)로 보정합니다. 낙폭·CVaR 같은 **경로 의존 지표는 겹치지 않는 표본에서만** 계산합니다(겹친 수익률을 이어 붙이면 존재하지 않는 낙폭이 만들어집니다).
- 표본이 얇으면 `eff/(eff+prior)`로 0을 향해 수축하고, 버킷 단조성이 깨지면 가중 isotonic으로 복원합니다.
- **과거 증거 할인율**: 기본 `0.6`(0.5~0.8 구간의 중간). 과거 재현은 시점상 진짜 out-of-sample이지만, **모델 설계 자체가 그 시기를 겪은 뒤에 만들어졌다**는 점은 어떤 replay로도 제거할 수 없습니다. 실시간 증거(1.0)보다 낮되, 비어 있는 실시간 ledger를 이기기에는 충분한 값입니다. 여기에 PIT 커버리지 부족·생존편향·매크로 개정·재무 근사·표본 부족·국면 집중·섹터 집중·fold 불안정이 있으면 각각 추가 할인됩니다.
- **결합은 정밀도 가중**입니다: `mu_post = Σ(w_i/se_i² · mu_i) / (Σ w_i/se_i² + 1/τ²)`. 0을 중심으로 하는 사전분포(τ=3%)가 얇은 추정치를 수축시킵니다. 실시간 표본이 쌓일수록 정밀도가 커져 **자동으로** 실시간 비중이 올라갑니다 — 전환 시점을 하드코딩하지 않습니다.
- **비대칭이 의도적입니다.** 실시간 성과가 과거보다 크게 낮으면 Kelly fraction을 축소하고, 반대 방향은 작동하지 않습니다. 실시간 성과가 나쁘다고 기대수익을 올리는 일은 절대 없습니다.
- Kelly 활성화 상태는 단일 코드가 아니라 **증거 사다리**입니다: `NO_EVIDENCE` → `HISTORICAL_PRIOR_ONLY` → `HISTORICAL_OOS_SUPPORTED` → `PROSPECTIVE_EARLY` → `PROSPECTIVE_CONFIRMED` → `ACTIVE_PAPER` → `ACTIVE_VALIDATED`. 화면에는 "과거 OOS 검증 활용 중", "실시간 검증 축적 중"처럼 표시합니다.

## Opportunity · Warning Radar

Core Portfolio는 "위험 대비 지금 안정적으로 보유할 3~5종목"을 답합니다. 레이더는 **다른 질문**에 답합니다: *"최근 무엇이 달라졌는가?"* 두 층은 **하나의 점수로 합치지 않습니다.**

- 그래서 **변화(change) 피처**가 수준(level) 피처만큼 중요합니다: 알파 백분위 Δ, 20/60일 모멘텀 가속, 상대강도 Δ, 거래량 가속, 진입상태 전환, 섹터 로테이션 전환, 변동성 국면 전환, 200일선 돌파/이탈. **2년 내내 95p였던 종목은 기회가 아닙니다 — 아무 일도 일어나지 않았습니다.**
- ML은 복잡성보다 검증 가능성을 우선합니다. 로지스틱 baseline이 항상 후보에 있고, **OOS에서 baseline을 못 이기면 채택하지 않습니다.** target도 4종(양의 초과수익 / +5% 초과 / 횡단면 상위 20% / 비대칭 MFE-MAE)을 validation 안에서 비교하며, 사후에 가장 예뻐 보이는 것을 고르지 않습니다.
- 평가는 정확도가 아니라 **점수 구간별 실제 미래 초과수익의 단조성**과 상위 구간 실측 초과수익이 결정합니다. AUC·PR-AUC·Brier·calibration error·precision@K·turnover·MDD·CVaR는 맥락으로 함께 봅니다.
- **과최적화 방지**: nested walk-forward(선택은 validation에서만), purge+embargo, 시도한 variant 수와 grid 크기 기록, fold별 안정성, date-block bootstrap, Deflated Sharpe Ratio, PBO 추정, 그리고 **모델 확정 전까지 손대지 않는 최종 홀드아웃**(기본 2023~). 홀드아웃은 봉인 상태에서 접근하면 예외를 던집니다.
- **실패 조건을 명시적으로 구현합니다**(§37). baseline 미달·단조성 없음·비용 후 edge 소멸·fold 불안정·PIT 커버리지 부족·국면/섹터 집중·홀드아웃 붕괴 중 하나라도 걸리면 **모델을 적용하지 않고** 투명한 규칙 기반 변화 점수를 유지하며, 화면에 그 사실을 표시합니다.
- 3단계 등급: **검증된 기회**(과거 OOS 검증 통과 + 신호 수렴), **관찰 필요한 변화**(변화는 강하나 검증 부족 — 리서치 전용), **관심 목록**. 검증 모델이 없으면 "검증된 기회"는 **구조적으로 도달할 수 없습니다**(validator가 강제).
- **거래량 급증 + 가격 하락은 기회로 분류하지 않습니다.** 분배(distribution)이지 매집이 아닙니다.
- Warning은 기회 점수의 반대값이 아니라 **별도 점수·별도 모델**입니다. 변동성 급등처럼 기회 쪽에 짝이 없는 항이 있고, 조용한 종목이 조용하다는 이유로 위험해 보이면 안 되기 때문입니다. **보유 종목의 경고는 최상단**에 배치합니다.
- 오늘의 변화 알림은 **state transition 기반**입니다. 어제부터 HIGH였다면 오늘 다시 신규 알림을 만들지 않습니다.
- **과거 유사 사례**(historical analogue)는 설명·리서치 도구이며 주 예측모델이 아닙니다. 스케일링 후 같은 지역 안에서만 거리를 계산하고, 표본이 얇으면 수치를 노출하지 않습니다.

## 제약형 Fractional Kelly 모델 포트폴리오 (shadow)

위 컨빅션 기준 비중을 기본값으로 유지하면서, 검증된 paper ledger가 충분할 때만 제약형 포트폴리오 Kelly를 25% 혼합합니다. 기본식은 `75% × 컨빅션 기준 비중 + 25% × 제약형 Kelly 비중`이며, Full Kelly가 아니라 기본 0.25 Fractional Kelly를 사용합니다. Kelly가 켜져도 보유 종목 집합은 선정 단계가 정한 3~5종목 그대로이고, 바뀌는 것은 그 안의 비중입니다.

- 현재의 `alpha`, `rawAlpha`, `alphaPercentile`은 기대수익률이 아닙니다. 과거 신호 시점에 고정된 percentile 구간과 만기된 126영업일 OOS 초과수익을 연결한 뒤, 거래비용을 차감하고 유효표본 수에 따라 0 방향으로 수축합니다. 같은 날 종목 횡단면은 한 날짜로 군집화하고, 겹치는 126일 forward return은 Bartlett kernel Newey–West/HAC(`lag=horizon-1`)로 보정합니다. alpha bucket 단조성이 깨지면 weighted isotonic calibration을 적용하고 경고를 남깁니다.
- 기대수익과 위험의 단위를 맞추기 위해 **KR·US를 별도로 최적화**합니다. 기대수익은 해당 지역 벤치마크 대비 초과수익, 공분산은 `종목 일수익률 - 지역 벤치마크 일수익률`의 regional active covariance입니다. 지역별 결과는 기존 위험예산과 지역 상한으로 결합하며, KR·US 절대수익률을 한 행렬에 섞지 않습니다.
- 표본이 부족하거나 Ledoit–Wolf 공분산을 계산할 수 없으면 기대수익이나 상관관계를 임의로 만들지 않습니다. 상태를 `SHADOW_INSUFFICIENT_HISTORY`로 기록하고 컨빅션 기준 비중만 유지합니다. 다만 **지역 active covariance는 Kelly와 무관하게 추정**하므로 보유 포트폴리오의 tracking error는 그때도 표시됩니다.
- 종목 30%, 업종 45%, 테마 45%, 지역 상한, 최소 현금 15%(국면·매크로 예산에 따라 상승), 최대 회전율 25%를 적용합니다. `EVENT_RISK`·`AVOID`·value trap은 신규 Kelly 비중 0, `WATCH`와 `WAIT_FOR_PULLBACK`은 각각 haircut을 받습니다. 제약 때문에 남은 금액은 다른 종목에 억지로 배분하지 않고 현금으로 둡니다.
- 매크로는 종목 기대수익에 더하지 않고 Kelly fraction과 최소 현금만 조정합니다. 낮은 confidence는 Kelly 위험예산을 추가 축소합니다.
- 거래비용은 지역별 수수료·세금·스프레드, 예상 회전율, 리밸런싱 주기, 예상 거래대금을 구조화해 계산합니다. 종목별 유동성 자료가 없으면 config의 보수적 기본 스프레드를 사용하고 fallback 여부를 기록합니다.
- 기준통화 기본값은 KRW입니다. 현재 종목 active covariance에는 환율 수익률과 환헤지를 넣지 않으므로 `currencyPolicy`와 화면에 이 한계를 명시하고 환율 위험은 지역 배분 레이어에서만 표시합니다.
- 대시보드는 **Base Kelly fraction**, **매크로 조정 applied fraction**, **최종 blend weight**를 구분합니다. 실제 영향도는 최종 비중과 기준 비중(현금 포함)의 절대 배분 차이인 `kellyAllocationImpactPct`로 표시합니다. fallback이면 Kelly 종목 비중을 공개하지 않습니다.
- 이전 운영 상태가 없으면 회전율을 실제 교체율처럼 보이게 두지 않고 `turnoverBasis=INITIAL_BUILD`로 기록해 화면에 **신규 구축**으로 표시합니다.

Kelly Criterion은 추정된 성장률을 최대화하는 도구일 뿐 만능 공식이 아닙니다. 확률·기대수익·공분산 추정오차에 민감하고, 과거 분포가 미래에도 유지된다는 보장이 없으며, Full Kelly는 큰 낙폭을 만들 수 있습니다. 이 모델은 개인의 자산·소득·부채·투자기간·손실감내도를 반영하지 않는 연구용 가상 포트폴리오입니다.

## 실행

```bash
pip install -r requirements.txt
python -m compileall pipeline
pytest -q
python -m pipeline.build                       # 실데이터 (Yahoo/FRED 네트워크 + FRED_API_KEY 필요)
python -m pipeline.validate data/site-data.json
# 오프라인 미리보기(합성 데이터; 생성물은 Git에서 무시됨):
python scripts/make_seed.py
python -m pipeline.validate data/site-data.json --allow-seed

# 과거 point-in-time 재현 (증분 — 이미 있는 날짜는 다시 계산하지 않음)
python scripts/run_replay.py <ledger-dir> [--start 2013-01-01] [--frequency W] [--full]
python scripts/train_opportunity.py <ledger-dir>            # 기회 모델 학습·검증
python scripts/train_opportunity.py <ledger-dir> --warning  # 경고 모델 학습·검증

# 합성 데이터로 전체 체인 점검 (기계 검증용 — 투자 결과 아님)
python scripts/demo_replay.py --tickers 40 --years 9
```

빌드는 다음 환경변수로 과거 ledger를 읽습니다(CI가 `signal-history` 브랜치에서 주입): `HISTORICAL_SIGNALS_PATH`, `HISTORICAL_OUTCOMES_PATH`, `HISTORICAL_DIAGNOSTICS_PATH`, `OPPORTUNITY_MODEL_PATH`, `WARNING_MODEL_PATH`. 없으면 과거 prior 없이 정상 동작하며 그 상태를 artifact에 기록합니다.

**계산비용.** 전체 재현은 종목수 × 재현 날짜 수에 비례합니다(주 단위 기준 550종목 × 13년 ≈ 수십 분). 그래서 `.github/workflows/replay.yml`은 **증분**으로 돌고, ML 재학습은 주 1회입니다. 일주일치 새 관측치가 walk-forward 선택을 바꿀 수 없는데 매일 재학습하면 비용만 늘고 **유효 시도 횟수만 부풀립니다**. 재현 주기 선택(`D`/`W`/`M`)의 trade-off는 `config.historicalReplay._notes`에 기록했습니다: 일 단위는 5배 비용에 대부분 겹치는 관측치만 추가되고 HAC 유효표본은 거의 늘지 않으며, 월 단위는 버킷 calibration에 필요한 횡단면 수를 밑돕니다.

`data/site-data.json`과 `data/audit.json`은 workflow/로컬 명령이 만드는 생성물이며 Git에서 추적하지 않습니다. 테스트용 최소 예시는 `tests/fixtures/site-data.synthetic.json`에 있고 파일명과 내부 `dataMode` 모두 synthetic임을 명시합니다. regional active Kelly·universe diagnostics·run-to-run diff가 추가된 스키마는 `2.3.0`이었고, v3에서 `modelPortfolio.selection`, `modelPortfolio.concentration`, `longTerm.*.picks[].invalidation`, `longTerm.*.riskLimits`가 추가되었습니다. **현재 스키마는 `2.4.0`**이며 `historicalValidation`, `prospectiveValidation`, `kellyEvidence`, `opportunityRadar`, `warningRadar`, `radarDiagnostics`, `modelComparison`이 추가되고 `provenance`에 `replayVersion`·`featureVersion`·`dataVersion`이 붙었습니다. 기존 필드는 그대로 유지되므로 2.3.0 소비자는 새 섹션을 무시하면 계속 동작합니다.

`FRED_API_KEY`(및 KR 매크로용 `ECOS_API_KEY`)는 GitHub Actions Secret으로만 주입합니다. 네트워크가 막힌 환경에서는 실데이터 빌드가 불가능하며, 그 경우 seed로 성공한 척하지 않고 차단 원인을 보고합니다.

## 실전(liveValidated) 활성화 조건

최소 1년(252영업일) paper tracking과 공통 표본 gate, 시간순 신호 축적, 비용 차감 후 양의 rank IC/초과수익, 벤치마크 대비 개선, 허용 가능한 MDD/CVaR, 섹터·기간 집중도 완화가 확인되기 전까지 `liveValidated`는 부여되지 않습니다.
