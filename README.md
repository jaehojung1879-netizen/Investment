# Investment Research Dashboard — v2 (paperTrading 기본)

출처가 분명하고 시점이 일치하며 사후 검증 가능한 투자 **리서치** 대시보드입니다. 종목을 많이 추천하는 사이트가 아니라, 세계적 자산운용사·매크로 전략가가 쓰는 방식(국면→위험예산→지역별 팩터 리서치→진입상태→사후검증)에 가깝게 설계했습니다.

## 실행 상태(runMode)와 데이터 모드(dataMode)

- **runMode**: `researchOnly` · `paperTrading`(기본) · `liveValidated`. 기본값은 `paperTrading`이며, **`liveValidated`는 config만으로 절대 부여되지 않습니다** — paper signal ledger에 충분한 검증 이력이 쌓여야 합니다.
- **dataMode**: `live` · `seed` · `stale` · `synthetic`. 화면에 데이터 모드와 **빌드 커밋 SHA**를 항상 표시합니다.
- README·빌드·검증 코드·화면 문구가 **동일한 안전 상태**를 표현합니다. (과거의 “README는 PAPER ONLY인데 build는 paperOnly=false” 불일치를 제거했습니다.)

## 정직성 원칙

- 모든 산출물에 `schemaVersion`, `modelVersion`, `buildCommitSha`, `generatedAt`, `marketAsOf`, `sourceAsOf`, `runMode`, `dataMode`를 기록합니다(`provenance`).
- `recommendationsBlocked=true`이면 단기 아이디어뿐 아니라 **장기 슬리브 비중·핵심 액션도 모두 차단**됩니다(리서치 관점만 유지).
- seed/synthetic/stale 데이터는 실데이터처럼 보일 수 없도록 dataMode로 명확히 구분하고, production 검증에서 non-zero exit로 실패시킵니다.
- ‘추천 비중’ 대신 **modelSleeveWeight**(완전 투자된 가상 모델 슬리브 내 비중)라고 표기합니다 — 개인 포트폴리오 추천 비중이 아닙니다.

## 장기 종목선정 엔진 v2

- KR·US를 **지역별로 독립 z-score** 산출(서로 직접 비교 금지). 지역 배분은 매크로 위험예산 레이어가 담당합니다.
- ETF·벤치마크(QQQ, SPY 등)는 개별주식 랭킹에서 제외.
- 팩터(모멘텀·밸류·퀄리티·저변동)는 **섹터 내 중립화** z-score 우선. 금융·유틸리티 등은 레버리지 페널티 예외 처리.
- 팩터 커버리지·재무 커버리지·소스 품질을 별도 산출하고 **신뢰도 페널티**를 적용. 3개 슬리브·최소 재무 커버리지 미달 시 `DATA_INSUFFICIENT`.
- 슬리브는 **8~12종목 + 단일종목 상한 + 업종 상한 + 현금 하한**의 실제 포트폴리오 구성. 5종목×20%(사실상 등가중) 오류를 제거했습니다.
- 위험지표(하방변동성·최대낙폭·CVaR·베타)를 알파와 **분리 표기**. 알파와 위험·진입 페널티를 한 점수로 섞지 않습니다.

## ‘좋은 종목’과 ‘지금 살 종목’ 분리

- `longTermResearchView`: `POSITIVE` · `NEUTRAL` · `NEGATIVE` · `DATA_INSUFFICIENT`
- `entryState`: `ACCUMULATE_GRADUALLY` · `WATCH` · `WAIT_FOR_PULLBACK` · `EVENT_RISK` · `AVOID` (추세·이격·유니버스 내 과열 백분위·변동성 급등·갭·실적 이벤트·집중도 반영)
- 회전율을 줄이는 **rank buffer**(config.longterm.rankBuffer): 신규 편입은 상위 enterPct, 기존 편입은 exitPct 아래로 내려갈 때까지 유지.

## 매크로 방향·국면 엔진

고정 임계값(10Y 4.5%, 원/달러 1,400) 대신 **6축 방향 엔진**(성장·물가·유동성·금융여건·위험선호·이익/신용)으로 `Goldilocks / Reflation / Stagflation / Deflation·Slowdown / Transition`을 판정하고 confidence·이전 국면·근거·반대 근거를 함께 제공합니다. 월별·분기 지표는 **발표 시차(release lag)**를 적용해 point-in-time로 사용하며, 데이터가 없으면 임의 중립·강세로 바꾸지 않고 confidence를 낮춥니다. 매크로는 개별 알파에 가산하지 않고 **위험예산·현금범위·스타일 틸트**만 조정합니다.

## 전문가 컨센서스(반자동, 날조 없음)

`data/expert_sources.json`(기관 레지스트리)와 `data/expert_views.json`(사람이 검증한 요약)에서 **verified=true**이고 stale 하지 않은 의견만 집계합니다. 단순 평균이 아닌 **weighted median + 의견 분산**을 계산하고, 기업 IR은 독립 의견으로 취급하지 않습니다(가중치 하향). 원문 검증 전에는 내용을 만들지 않고 “검증 대기”로만 표시합니다.

## 사후 검증(paper signal ledger)

오늘부터 생성되는 모든 종목선정 결과를 **변경 불가능한 ledger**에 누적합니다(과거 결과를 현재 모델로 덮어쓰지 않음). 이후 21/63/126/252영업일 수익률·초과수익·MFE/MAE를 계산하고, hit rate뿐 아니라 rank IC·초과수익·국면별 성과로 평가합니다. GitHub Actions는 **별도 `signal-history` 브랜치**에 누적해 main 재귀 빌드를 유발하지 않습니다(`.github/workflows/ledger.yml`). 가격기반 팩터는 생존편향을 명시한 walk-forward(`pipeline.validation_lt`)로 검증하고, value/quality는 point-in-time 데이터가 없어 자체 백테스트를 주장하지 않습니다.

## 실행

```bash
pip install -r requirements.txt
python -m compileall pipeline
pytest -q
python -m pipeline.build                       # 실데이터 (Yahoo/FRED 네트워크 + FRED_API_KEY 필요)
python -m pipeline.validate data/site-data.json
# 오프라인 미리보기(합성 데이터):
python3 scripts/make_seed.py
python -m pipeline.validate data/site-data.json --allow-seed
```

`FRED_API_KEY`(및 KR 매크로용 `ECOS_API_KEY`)는 GitHub Actions Secret으로만 주입합니다. 네트워크가 막힌 환경에서는 실데이터 빌드가 불가능하며, 그 경우 seed로 성공한 척하지 않고 차단 원인을 보고합니다.

## 실전(liveValidated) 활성화 조건

최소 6개월(≈126영업일) 이상 paper tracking, 시간순 신호 축적, 비용 차감 후 양의 rank IC/초과수익, 벤치마크 대비 개선, 허용 가능한 MDD/CVaR, 섹터·기간 집중도 완화가 확인되기 전까지 `liveValidated`는 부여되지 않습니다.
