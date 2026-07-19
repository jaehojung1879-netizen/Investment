# 방법론 · 출처 · 안전 체크리스트

## 무엇을 하고, 무엇을 하지 않는가

- 이 대시보드는 **리서치 도구**이며 매매 지시가 아닙니다. 기본 runMode는 `paperTrading`입니다.
- ‘좋은 종목’(장기 리서치 관점)과 ‘지금 살 종목’(진입상태)을 **분리**합니다.
- ‘추천 비중’ 대신 **modelSleeveWeight**(완전 투자된 가상 슬리브 내 비중)만 제시합니다.
- 매크로는 개별 종목 알파에 더하지 않고 **위험예산·현금범위·스타일 틸트**만 조정합니다.
- 검증 이력이 충분하기 전에는 **LIVE VALIDATED**라고 표시하지 않습니다.

## 장기 팩터 엔진 (지역별 · 섹터중립)

- 팩터: 모멘텀(12-1M, Jegadeesh-Titman) · 밸류(이익수익률·선행이익수익률·장부수익률·FCF수익률, Fama-French) · 퀄리티(ROE·마진·이익성장·저부채, Novy-Marx/QMJ) · 저변동(Ang et al.).
- KR·US는 **지역별로 독립 z-score**를 산출하며 서로 직접 비교하지 않습니다.
- z-score는 **섹터 내 중립화**를 우선하여, 은행의 P/B·부채를 산업재와 같은 잣대로 재지 않습니다. 금융·유틸리티·리츠는 레버리지 페널티에서 예외입니다.
- 팩터 커버리지·재무 커버리지·소스 품질로 **신뢰도**를 계산해 알파를 페널티(0 방향 수축)합니다.
- 위험지표(하방변동성·최대낙폭·CVaR·베타)와 진입 페널티는 알파와 **분리 표기**합니다 — 하나의 점수로 섞지 않습니다.

## 진입상태

추세(20·50·200일)·200일선 이격·**유니버스 내 과열 백분위**(절대 RSI가 아님)·20/60일 변동성 급등·갭·실적 이벤트·거래량·섹터/포트폴리오 집중도를 반영해 `ACCUMULATE_GRADUALLY / WATCH / WAIT_FOR_PULLBACK / EVENT_RISK / AVOID`로 구분합니다. 회전율은 **rank buffer**로 낮춥니다.

## 매크로 국면 (6축 방향 엔진)

성장·물가·유동성·금융여건·위험선호·이익/신용의 방향을 확장 z-score로 읽어 `Goldilocks / Reflation / Stagflation / Deflation·Slowdown / Transition`을 판정합니다. 월별·분기 지표는 **발표 시차(release lag)**를 적용해 point-in-time로 사용합니다. 데이터가 없으면 임의 중립·강세로 바꾸지 않고 confidence를 낮춥니다.

## 사후 검증 (paper signal ledger)

오늘부터의 모든 신호를 변경 불가능한 ledger에 누적하고(과거를 현재 모델로 덮어쓰지 않음) 21/63/126/252영업일 수익률·초과수익·rank IC로 평가합니다. 가격기반 팩터는 생존편향을 명시한 walk-forward로 검증하고, value/quality는 point-in-time 데이터가 없어 자체 백테스트를 주장하지 않습니다.

## 출처

- 미국 매크로: FRED/ALFRED (Core CPI/PCE, 실업률, 신규실업수당, CFNAI, NFCI/ANFCI, 2Y·10Y·실질금리·기대인플레, HY/IG 스프레드, Fed 대차대조표·RRP·TGA, 달러지수, VIX, 유가 등).
- 한국 매크로: 한국은행 ECOS 우선 (기준금리·국고채·물가·산업생산·수출·M2·원달러). 키가 없거나 오래되면 coverage·confidence를 낮춥니다.
- 전문가 컨센서스: 검증된 house view만 집계 (BlackRock BII, J.P. Morgan AM/Global Research, Morgan Stanley, PIMCO, 한국은행, KDI, 산업연구원). 원문 검증 전에는 내용을 만들지 않습니다.
- 가격: Yahoo Finance. 유니버스는 현재 상장/구성 종목이라 생존편향이 남습니다.

## 안전 체크리스트

- seed/synthetic/stale, 모델 0, 커버리지 부족이면 매매 사용 금지 — production 검증에서 non-zero exit로 실패합니다.
- 차단(blocked) 상태면 단기 아이디어와 **장기 슬리브 비중·핵심 액션**이 모두 숨겨집니다.
- 데이터 모드와 빌드 SHA를 항상 확인하세요. 단기 방향 예측은 참고용이며 분산·표본수·근거를 함께 보세요.
