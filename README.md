# Investment Research Dashboard — v2.3 (paperTrading 기본)

출처가 분명하고 시점이 일치하며 사후 검증 가능한 투자 **리서치** 대시보드입니다. 종목을 많이 추천하는 사이트가 아니라, 세계적 자산운용사·매크로 전략가가 쓰는 방식(국면→위험예산→지역별 팩터 리서치→진입상태→사후검증)에 가깝게 설계했습니다.

## 실행 상태(runMode)와 데이터 모드(dataMode)

- **runMode**: `researchOnly` · `paperTrading`(기본) · `liveValidated`. 기본값은 `paperTrading`이며, **`liveValidated`는 config만으로 절대 부여되지 않습니다** — paper signal ledger에 충분한 검증 이력이 쌓여야 합니다.
- **dataMode**: `live` · `seed` · `stale` · `synthetic`. 화면에 데이터 모드와 **빌드 커밋 SHA**를 항상 표시합니다.
- README·빌드·검증 코드·화면 문구가 **동일한 안전 상태**를 표현합니다. (과거의 “README는 PAPER ONLY인데 build는 paperOnly=false” 불일치를 제거했습니다.)

첫 화면은 `현재 주식·현금 비중 → 지금 분할 매수 가능한 종목 → 상위 보유 비중`을 먼저 보여줍니다. 시장·후보·데이터 기준은 작은 보조 카드로 압축하고, 전체 투자 후보는 접어두지 않습니다. 화면에는 `기본 비중 제공 중`, `성과 보정 대기`, `안전 차단`처럼 뜻이 바로 드러나는 문구를 사용합니다. 계산식·데이터 출처·한계는 별도 `methodology.html` 페이지에서 설명합니다.

미국 장 마감 데이터는 **매일 07:10 KST**에 확인·배포를 시작하고, 한국 시장은 평일 17:15 KST에 다시 갱신합니다. 화면의 미국 날짜는 한국 날짜가 아니라 미국 거래소 기준일입니다(예: 한국시간 8월 4일 오전에 반영된 종가는 미국 거래일 8월 3일). 미국 동부 16:45 이후에는 방금 끝난 세션을 기대하며, 전 거래일 값이면 `업데이트 지연`으로 표시하고 가능한 지수는 Stooq로 재확인합니다.

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
- 슬리브는 **8~12종목 + 단일종목 상한 + 업종 상한 + 현금 하한**의 실제 포트폴리오 구성. 5종목×20%(사실상 등가중) 오류를 제거했습니다.
- 위험지표(하방변동성·최대낙폭·CVaR·베타)를 알파와 **분리 표기**. 알파와 위험·진입 페널티를 한 점수로 섞지 않습니다.

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

`validationStatus`는 paperDays·21/63/126/252일별 만기 신호 수·eligibleDates·지역별 IC·비용 차감 초과수익·MDD/CVaR를 표시합니다. 화면은 21일 초기 확인, 63일 중간 확인, 126일 비중 보정 검토, 252일 최종 사용 검토로 진행률을 나눠 보여줍니다. Kelly 추정과 활성화는 하나의 gate를 공유하며 기본 기준은 paper 252영업일, 만기 신호 100개, HAC 유효 날짜 30개, 관측 날짜 63개입니다. 조건이 채워져도 자동으로 `liveValidated`로 승격하지 않습니다.

## 제약형 Fractional Kelly 모델 포트폴리오 (shadow)

기존 역하방변동성 슬리브를 기본값으로 유지하면서, 검증된 paper ledger가 충분할 때만 제약형 포트폴리오 Kelly를 25% 혼합합니다. 기본식은 `75% × 기존 위험가중 비중 + 25% × 제약형 Kelly 비중`이며, Full Kelly가 아니라 기본 0.25 Fractional Kelly를 사용합니다.

- 현재의 `alpha`, `rawAlpha`, `alphaPercentile`은 기대수익률이 아닙니다. 과거 신호 시점에 고정된 percentile 구간과 만기된 126영업일 OOS 초과수익을 연결한 뒤, 거래비용을 차감하고 유효표본 수에 따라 0 방향으로 수축합니다. 같은 날 종목 횡단면은 한 날짜로 군집화하고, 겹치는 126일 forward return은 Bartlett kernel Newey–West/HAC(`lag=horizon-1`)로 보정합니다. alpha bucket 단조성이 깨지면 weighted isotonic calibration을 적용하고 경고를 남깁니다.
- 기대수익과 위험의 단위를 맞추기 위해 **KR·US를 별도로 최적화**합니다. 기대수익은 해당 지역 벤치마크 대비 초과수익, 공분산은 `종목 일수익률 - 지역 벤치마크 일수익률`의 regional active covariance입니다. 지역별 결과는 기존 위험예산과 지역 상한으로 결합하며, KR·US 절대수익률을 한 행렬에 섞지 않습니다.
- 표본이 부족하거나 Ledoit–Wolf 공분산을 계산할 수 없으면 기대수익이나 상관관계를 임의로 만들지 않습니다. 상태를 `SHADOW_INSUFFICIENT_HISTORY`로 기록하고 기존 역하방변동성 포트폴리오만 유지합니다.
- 종목 10%, 업종 25%, 테마 20%, 지역 상한, 최소 현금 10%, 최대 회전율 25%를 적용합니다. `EVENT_RISK`·`AVOID`·value trap은 신규 Kelly 비중 0, `WATCH`와 `WAIT_FOR_PULLBACK`은 각각 haircut을 받습니다. 제약 때문에 남은 금액은 다른 종목에 억지로 배분하지 않고 현금으로 둡니다.
- 매크로는 종목 기대수익에 더하지 않고 Kelly fraction과 최소 현금만 조정합니다. 낮은 confidence는 Kelly 위험예산을 추가 축소합니다.
- 거래비용은 지역별 수수료·세금·스프레드, 예상 회전율, 리밸런싱 주기, 예상 거래대금을 구조화해 계산합니다. 종목별 유동성 자료가 없으면 config의 보수적 기본 스프레드를 사용하고 fallback 여부를 기록합니다.
- 기준통화 기본값은 KRW입니다. 현재 종목 active covariance에는 환율 수익률과 환헤지를 넣지 않으므로 `currencyPolicy`와 화면에 이 한계를 명시하고 환율 위험은 지역 배분 레이어에서만 표시합니다.
- 대시보드는 **Base Kelly fraction**, **매크로 조정 applied fraction**, **최종 blend weight**를 구분합니다. 실제 영향도는 최종 비중과 위험가중 기준 비중(현금 포함)의 절대 배분 차이인 `kellyAllocationImpactPct`로 표시합니다. fallback이면 Kelly 종목 비중을 공개하지 않습니다.

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
```

`data/site-data.json`과 `data/audit.json`은 workflow/로컬 명령이 만드는 생성물이며 Git에서 추적하지 않습니다. 테스트용 최소 예시는 `tests/fixtures/site-data.synthetic.json`에 있고 파일명과 내부 `dataMode` 모두 synthetic임을 명시합니다. regional active Kelly·universe diagnostics·run-to-run diff가 추가된 스키마는 `2.3.0`입니다.

`FRED_API_KEY`(및 KR 매크로용 `ECOS_API_KEY`)는 GitHub Actions Secret으로만 주입합니다. 네트워크가 막힌 환경에서는 실데이터 빌드가 불가능하며, 그 경우 seed로 성공한 척하지 않고 차단 원인을 보고합니다.

## 실전(liveValidated) 활성화 조건

최소 1년(252영업일) paper tracking과 공통 표본 gate, 시간순 신호 축적, 비용 차감 후 양의 rank IC/초과수익, 벤치마크 대비 개선, 허용 가능한 MDD/CVaR, 섹터·기간 집중도 완화가 확인되기 전까지 `liveValidated`는 부여되지 않습니다.
