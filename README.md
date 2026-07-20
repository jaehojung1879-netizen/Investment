# Investment Research Dashboard — v2 (paperTrading 기본)

출처가 분명하고 시점이 일치하며 사후 검증 가능한 투자 **리서치** 대시보드입니다. 종목을 많이 추천하는 사이트가 아니라, 세계적 자산운용사·매크로 전략가가 쓰는 방식(국면→위험예산→지역별 팩터 리서치→진입상태→사후검증)에 가깝게 설계했습니다.

## 실행 상태(runMode)와 데이터 모드(dataMode)

- **runMode**: `researchOnly` · `paperTrading`(기본) · `liveValidated`. 기본값은 `paperTrading`이며, **`liveValidated`는 config만으로 절대 부여되지 않습니다** — paper signal ledger에 충분한 검증 이력이 쌓여야 합니다.
- **dataMode**: `live` · `seed` · `stale` · `synthetic`. 화면에 데이터 모드와 **빌드 커밋 SHA**를 항상 표시합니다.
- README·빌드·검증 코드·화면 문구가 **동일한 안전 상태**를 표현합니다. (과거의 “README는 PAPER ONLY인데 build는 paperOnly=false” 불일치를 제거했습니다.)

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

월별·분기 지표에는 보수적인 고정 발표시차를 적용하지만 이는 실제 release calendar를 완전히 재현하지 않습니다. 과거 판정은 ALFRED vintage가 아닌 최신 개정 시계열을 사용할 수 있으므로 완전한 실시간 빈티지 백테스트를 주장하지 않습니다.

## 전문가 컨센서스(반자동, 날조 없음)

`data/expert_sources.json`(기관 레지스트리)와 `data/expert_views.json`(사람이 검증한 요약)에서 **verified=true**이고 stale 하지 않은 의견만 집계합니다. 단순 평균이 아닌 **weighted median + 의견 분산**을 계산하고, 기업 IR은 독립 의견으로 취급하지 않습니다(가중치 하향). 원문 검증 전에는 내용을 만들지 않고 “검증 대기”로만 표시합니다.

## 사후 검증(paper signal ledger)

오늘부터 생성되는 검증용 **전체 eligible cross-section**(UI 상위 15개와 분리)을 변경 불가능한 ledger에 누적합니다. ID는 date×region×ticker×modelVersion이므로 새 모델이 과거 신호를 덮어쓰지 않습니다. US는 SPY, KR은 KOSPI200 계열 벤치마크를 사용하고 동일한 종료 달력일에서 초과수익을 계산합니다. rank IC는 non-overlapping 표본의 각 date×region 횡단면에서 Spearman으로 계산한 뒤 평균·중앙값·hit ratio를 집계합니다. GitHub Actions는 **별도 `signal-history` 브랜치**를 사용해 main 재귀 빌드를 유발하지 않습니다.

`validationStatus`는 paperDays·maturedSignals·eligibleDates·지역별 IC·비용 차감 초과수익·MDD/CVaR·미달 사유를 표시합니다. 최소 126영업일 전에는 `liveValidationEligible=false`이며, 이번 버전은 조건이 채워져도 자동으로 `liveValidated`로 승격하지 않습니다.

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

`data/site-data.json`과 `data/audit.json`은 workflow/로컬 명령이 만드는 생성물이며 Git에서 추적하지 않습니다. 테스트용 최소 예시는 `tests/fixtures/site-data.synthetic.json`에 있고 파일명과 내부 `dataMode` 모두 synthetic임을 명시합니다. 스키마는 v2.1에서 `2.1.0`으로 올랐으며 frontend는 v2.0의 `confidence`/`financialCoverage`가 남은 artifact도 데이터 품질 레이블로만 fallback 렌더링합니다.

`FRED_API_KEY`(및 KR 매크로용 `ECOS_API_KEY`)는 GitHub Actions Secret으로만 주입합니다. 네트워크가 막힌 환경에서는 실데이터 빌드가 불가능하며, 그 경우 seed로 성공한 척하지 않고 차단 원인을 보고합니다.

## 실전(liveValidated) 활성화 조건

최소 6개월(≈126영업일) 이상 paper tracking, 시간순 신호 축적, 비용 차감 후 양의 rank IC/초과수익, 벤치마크 대비 개선, 허용 가능한 MDD/CVaR, 섹터·기간 집중도 완화가 확인되기 전까지 `liveValidated`는 부여되지 않습니다.
