# MVMA-v1 · 데이터 등록부 (DATA-REGISTER)

기준 `main` `4f4497b`. 수집·측정 시각 2026-11-22 (UTC). 수익률·NAV·성과는 계산하지 않았다.

- 원천 실측: [`evidence/source-probe.json`](evidence/source-probe.json) (`source_probe.py`)
- 보존 입력: [`data/research/mvma-v1/manifest.json`](../../data/research/mvma-v1/manifest.json) (`collect_inputs.py`)
- 판단일 신호 원장·준비도: [`evidence/us-signal-readiness.json`](evidence/us-signal-readiness.json) / `.csv` (`build_signals.py`)

## 0. 원천 확보 원칙

1. 저장소에 보존된 원본 재사용 → 2. 기존 Actions Artifact·브랜치 객체 재사용 → 3. 기존 `workflow_dispatch` 경로의 Secret 기반 수집 → 4. 인증·접근·원천 제공 범위가 **실제로** 거부했을 때만 `SOURCE_BLOCKED`.

- 개발 컨테이너에 API 키가 없다는 사실은 차단 근거가 아니다. Secret은 main의 검토된 워크플로만 읽고, 출력·복사·커밋하지 않으며, 미검토 PR 코드에 주입하지 않는다.
- 이 세션의 토큰으로 `probes.yml` dispatch를 시도하면 `403 Resource not accessible by integration`이 돌아온다. 이것은 원천 차단이 아니라 이 세션의 권한 문제다. Secret이 필요한 실행은 아래 §4에 정확한 경로와 입력으로 남긴다.
- 기존 봉인 워크플로는 수정하지 않았고, 새 워크플로도 만들지 않았다.

## 1. 미국 — 확보 완료

| 입력 | 경로(우선순위) | 보존 위치 | 실측 | 증거 등급 |
|---|---|---|---|---|
| SPY 총수익 | ① 저장소 | `data/research/us-dual-benchmark-v1/spy-qqq-total-return.csv.gz` (sha256 `a82c64b9…`) | 2011-01-03 ~ 2026-09-14, 3,947세션, #341에서 SSGA 분배금 대조 | 결과 원천. 이번 PR에서는 날짜·종목 열과 D1용 `rawClose`만 읽음 |
| Shiller 월간 P·E·D·CPI·CAPE | ③ 공개 원천(키 불필요) | `raw/shiller-ie_data-20240904.xls.gz` (원본 sha256 `59532175…`, Last-Modified 2024-09-04), 같은 2023-10-17 빈티지(`0df9392b…`), 추출 CSV 2개 | 1871-01 ~ 2024-09. 마지막 E는 2024-06(빈티지 날짜보다 2.17개월 앞), 구 빈티지는 2023-06(3.58개월). 두 빈티지 사이 E 차이는 2023-04~06 세 달뿐(≤0.09%), D 차이 0, P는 구 파일의 부분월 1건 | `REVISED_HISTORY_SINGLE_VINTAGE` + 고정 4개월 분기말 지연 |
| BAA, GS10 (신용 스프레드) | ③ 공개 ALFRED CSV(키 불필요, Actions의 `FRED_API_KEY` 경로와 같은 빈티지) | `alfred-BAA-asof-decisions.csv`, `alfred-GS10-asof-decisions.csv`, 현재 계열 원본 `raw/fred-*-current.csv.gz` | 판단일 212개(2007-01-31 ~ 2024-08-30) 모두 빈티지 제공, 결측 0. 각 판단일의 **전날** 빈티지의 최신 관측치. BAA는 2016-11 ~ 2017-02 판단일에 빈티지가 2016-09 관측치에 머물렀다(그 4개월 스프레드는 등록 규칙상 결측). 이후 개정된 BAA 관측치 1건(2008-12-31 판단일의 2008-11 값) | `PIT_EXACT_ALFRED_VINTAGE` |
| BIL 원가격·분배 이벤트 | ② #331 브랜치 객체 재사용 | `raw/yahoo-BIL-chart-20261110.json.gz` (git blob `76007013…`, 비압축 sha256 `5d0b7e05…`, 바이트 동일) | 4,894세션, 2007-05-30 ~ 2026-11-09, 분배 128건, 2017-11-30 1:2 병합 | 원가격만 사용, 분배금은 아래 발행사본 |
| BIL 공식 분배금 | ③ 공개 원천(SSGA) | `raw/ssga-spdr-historical-distributions-20261122.xlsx` (sha256 `0008b3cc…`), `ssga-BIL-distributions.csv` | 233행, 2007-07-02 ~ 2026-11-02 | 발행사 원본 |
| 현금 참조금리 | ① 저장소 | `data/research/us-dual-benchmark-v1/rates.json` (Fed funds 2011~), `data/kr-market-risk-anatomy-v1/sources/FRED_DGS3MO` | — | `REFERENCE_RATE_NOT_INVESTABLE` 민감도 전용 |

### BIL 분배금 계보 대조 (가격 미사용)

Yahoo 금액은 현재 주식 기준으로 소급 재표시되므로, 2017-11-30 병합 이전 금액은 ½로 되돌려 비교했다.

- 같은 날짜 128건이 모두 일치했다(허용 0.002달러). 예외는 **2022-03-01** 한 건(발행사 0, Yahoo 0.022)이다.
- 발행사에만 있는 105행 중 104행은 **0달러 분배 행**(제로금리 기간)이다. 누락이 아니다. 실제 지급인데 Yahoo에 없는 것은 창 밖의 2026-11-02 한 건이다.
- 판정 `USE_ISSUER_DISTRIBUTIONS`. Phase 2의 BIL 총수익은 원가격 + 발행사 분배금으로만 만든다.
- 처음 대조에서는 병합 조정과 0원 행을 구분하지 않아 "105건 누락, 45건 불일치"로 잘못 읽혔다. 원인을 확인해 정정했고, 정정 전 수치는 사용하지 않는다.

## 2. 미국 — 확보하지 못한 것과 그 근거

| 입력 | 시도한 경로 | 결과 | 판정 |
|---|---|---|---|
| 예상 PER·예상 EPS 원장 | 저장소 Secret(FMP, Finnhub, SimFin, Polygon/MASSIVE, AlphaVantage)과 Artifact 검토 | 이 키들이 연결된 경로는 개별 기업 재무·가격이다. 지수 컨센서스 시계열을 제공하는 기존 수집기·Artifact는 없다 | `SOURCE_BLOCKED`(원천 범위). FactSet Insight 공개 글 836개 슬러그 중 `earningsinsight`는 2017년 32개·2012년 1개뿐이고 추출·권리 미검증 → 후보로만 기록 |
| ICE BofA HY/IG 스프레드 | FRED 공개 CSV, 그리고 `FRED_API_KEY`로 수집된 저장소 스냅샷(`kr-market-risk-anatomy-v1`, Actions 수집) | 두 경로 모두 첫 관측치 2023-10~11. 키 여부와 무관한 원천 제공 범위 제한 | 역사 원천으로 불가(대체 아님, 미사용) |
| BAA10Y 일별 | ALFRED | 2014-06 이전 빈티지 없음 | 2019년 이후 강건성용 |
| Shiller 최신 유지본 | shillerdata.com | 이 환경에서 연결 재설정 | 전향 기록용 미확보. Actions 러너에서 재측정 필요 |
| S&P DJI EPS 통합 문서 | spglobal.com | 이 환경에서 403 | 전향 기록용 미확보. Actions 러너에서 재측정 필요 |

## 3. 한국 — 원천 상태 (역사 결과 검정은 Phase D로 `NOT_RUN`)

| 입력 | 기존 경로 | 실측·근거 | 상태 |
|---|---|---|---|
| 국고채 3년 | `probes.yml` `ecos-market-context` + `secrets.ECOS`, Actions run [37080934658](https://github.com/jaehojung1879-netizen/Investment/actions/runs/37080934658), 증거 `research_specs/kr-market-context-ecos-evidence-37080934658.json` | `817Y002/010200000`, 일별, 1998-11-13 ~, `LIVE_VALIDATED_SOURCE` | 원천 확인됨. 값 수집 단계 필요 |
| 회사채 3년 AA- | 같은 run의 메타데이터 | `817Y002/010300000`, 일별, 1995-01-03 ~. 등급이 둘(AA-/BBB-)이라 `AMBIGUOUS_SOURCE`였을 뿐 차단 아님 | **AA-를 결과 조회 전 등록**. §4의 dispatch로 검증 |
| KOSPI 200 공식 PER/PBR | KRX Data Marketplace `MDCSTAT00702` | 이 환경 `HTTP 400 LOGOUT`. 같은 포털은 Actions에서도 투자자 수급 요청에 `LOGOUT`(v2.25). `KRX_API_KEY` Open API의 `idx/kospi_dd_trd`는 응답하지만 공개 필드 목록에 PER이 없음(서빙된 행으로 확인 필요) | 공식 지수 PER 경로 미확보 |
| Top-120 합산 PER(대안) | 저장소 보존: KRX `MKTCAP`(`KRX_API_KEY` 수집 유니버스 스냅샷, signal-history), DART TTM 순이익(`secrets.DART` 수집 `kr-candidate-merged`) | 두 입력 모두 이미 수집되어 있다. DART는 2015~, 260개 중 126개 종목 | `DATA_BUILD_FROM_PRESERVED_INPUTS`. 공식 지수 PER과 다른 정의로 별도 등록 필요 |
| 한국 예상 EPS | 저장소 Secret·Artifact 검토 | 컨센서스 원천 없음. FnGuide/FnSpace ToS 차단, DART는 실적만 | `SOURCE_BLOCKED` |
| 원화 현금 | ECOS·KOFR 기존 감사(`cross_market_foundation_v1`) | KOFR 2021-11-26~, CD91은 ECOS 프로브의 검토된 의미 목록에 없음 | 투자 가능 시계열 미등록. 정책금리는 `BOK_POLICY_RATE_PROXY` |
| 069500 총수익 | 저장소 발행사 NAV·분배 원본(`issuer-standard.xls`, sha256 `cbdd7a0c…`) | replay-v16 레시피는 과대 누적 | 발행사 대조본만 허용 |

## 4. 소유자가 실행할 정확한 경로 (이 세션 dispatch 403)

**A. 회사채 AA- 3년 선택 검증 (읽기 전용, 값 저장 없음)**

- 워크플로: `.github/workflows/probes.yml`, ref `main`
- 입력 `probe`: `ecos-market-context`
- 입력 `args`:

```json
{"CorpBond_3Y":{"seriesId":"817Y002","cycle":"D","itemCode":"010300000","semanticName":"CorpBond_3Y","expectedTableName":"1.3.2.1. 시장금리(일별)","expectedItemNames":["회사채(3년, AA-)"],"expectedUnit":"연%"}}
```

- 결과 Artifact: `ecos-market-context-source-metadata-<run_id>`. `validatedConfig.CorpBond_3Y`가 `LIVE_VALIDATED_SOURCE`이면 한국 신용 스프레드(AA- − 국고채 3년)의 원천이 확정된다.

**B. 한국 금리 일별 값 수집**

- ECOS 프로브는 설계상 값을 저장하지 않는다. 일별 값은 `pipeline/ecos_macro.py`를 `secrets.ECOS`로 호출하는 검토된 수집 단계가 필요하다.
- 이 단계는 현재 어느 워크플로에도 없다. 이 PR은 새 워크플로를 만들지 않는다. 필요하면 기존 `probes.yml`에 옵션을 추가하는 별도 PR로 검토받는다.

**C. 전향 기록용 미국 후행 EPS 원천 재측정**

shillerdata.com과 S&P DJI EPS 통합 문서는 이 컨테이너에서만 거부되었다. Actions 러너에서 다시 측정하기 전에는 접근 불가라고 결론 내리지 않는다. 현재 `probes.yml`에는 해당 옵션이 없다.

## 5. 판단일 신호 준비도 (결과 미조회)

미국 창 2012-01-31 ~ 2024-08-30, 152개 판단일 ([`evidence/us-signal-readiness.json`](evidence/us-signal-readiness.json)).

| 항목 | 값 |
|---|---|
| 저평가(PE < 직전 60개월 평균) | 81 |
| 이익 안정(후행 EPS ≥ 3개월 전) | 99 |
| 신용위험 참 / 거짓 / 결측 | 15 / 130 / 7 |
| 20% 낙폭 | 3 (2020-03, 2022-06, 2022-09) |
| 2×2: 저평가·양호 / 저평가·혼합 / **저평가·악화** | 55 / 25 / **1** |
| 2×2: 비저평가·양호 / 비저평가·혼합 / 비저평가·악화 / 결정 불가 | 30 / 27 / 7 / 7 |
| 평균 목표 비중 V1 / M1T / VM1T / D1 | 0.813 / 0.911 / 0.862 / 0.804 |

결과를 보기 전에 다음을 고정했다(`protocol.json` `preOutcomeReadiness`).

- 12개 판단일 미만인 상태 셀은 서술 전용이다.
- 따라서 제안서의 핵심 비교인 "저평가·양호 vs 저평가·악화(가치 함정)"는 미국 창에서 **평가 불가**다. 악화 셀이 1개뿐이다.
- D1은 B1과 3개 판단일만 다르다. 사실상 B1과 같다.
- 월평균 BAA는 다음 달 초에 공표된다. 그래서 2020-03-31 판단일의 신용 신호는 2월 값을 읽고 "위험 아님"이 된다. 이것은 등록된 PIT 동작이며 조정 대상이 아니다.
