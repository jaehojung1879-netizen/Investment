# Alpha Evidence Sprint v2 — 한국·미국 6~12개월 ETF 대비 초과수익 근거 판정

**최종 판정: `NO_EVIDENCE`** — 입증된 알파 0개(한국 0, 미국 0). 지역별로는 한국 `NO_EVIDENCE`(시험됐고 통과 0), 미국 `SOURCE_BLOCKED`(생존편향·권리·접근 때문에 시험 자체가 막힘).
**증거 등급:** 모든 신규 측정은 `OUTCOME_BLIND`(수익률·라벨·NAV 값·가격 이후 정보를 읽지 않음). 새 역사 outcome 실행 0건. 기준 `main` = `37f8cbf6`.

이 스프린트는 무엇이 증명됐는지와 무엇을 아직 계산할 수 없는지를 분리한다. 실행하지 않은 실증은 실행한 것처럼 보고하지 않는다.

| 질문 | 답 | 근거 |
|---|---|---|
| 한국 알파 | **0개** 입증 | Phase C/D BY·Holm 통과 0, 지명 0, Level 4 미실행 (`docs/kr-alpha-research-final-development-assessment.md`) |
| 미국 알파 | **0개** 입증 | 31변수 모델 `NO_MODEL_EVIDENCE`, US A1 `NO_GO`, #287 권리·식별·수익기준 `BLOCKED`, US 가격 패널 생존편향 |
| KR C2 +1.8pp CAGR은 종목선정인가 | **미확정** — 고정노출 귀속은 원천 일부가 막혀 있고 실행은 Owner 승인 대상 | Package B |
| 다음 단일 실증 | `kr-insider-open-market-purchase-v1` (사전등록·코드·테스트 완료, 미실행) | Package C |
| 운영 | 한국 `069500.KS` 100%, 미국 `SPY` 기준(보조 `QQQ`) 유지. 강제 추천 없음 | Package D |

---

## Package A — Research Reality Check

### A1. 레인별 재분류 (상세: `evidence/research-tracks.md`, `.json`)

| 레인 | 분류 | 핵심 근거 |
|---|---|---|
| A Market (B+C overlay) | **EMPIRICAL_FAIL** | KR `NO_CANDIDATE_NOMINATED_CONTROL_RETAINED` (C0 6.73%, C1 7.14% vs passive 9.73%); US 재현 동일 (passive 8.82% vs C0 7.77%). 위험축소는 알파가 아님. #289 설계 미승인, B-H1 수신기록 첫 H63 만기 2027-02-02, #312/#313 원천 접근 차단 |
| B Industry | **PARTIAL** | #290 `PREPARED_NOT_AUTHORIZED`; KR 산업 멤버십 `DATA_FOUNDATION_INSUFFICIENT_V4`; #300 검정력 23% `NO_GO`; #302 `REJECTED`; #310 H1은 매출 예측(수익 아님), 89% 금융 |
| C Stock-KR | **EMPIRICAL_FAIL** | Phase C/D 0 통과; #286 "NO STABLE ADDED ALPHA"; #304 `CONTAINS_ZERO` |
| C Stock-US | **SOURCE_BLOCKED** | #287 권리·식별·수익기준 `BLOCKED`; 31변수 `NO_MODEL_EVIDENCE`; 212개 퇴출 종목 가격 부재 |
| D Portfolio | **PARTIAL** | `BLOCKED_NO_VALIDATED_SELECTION_INPUT`; 통합 D +15.01%/yr < passive +20.24%/yr; #305/#309/#311 결론 `INCONCLUSIVE` |

가설군(#308/#310): A 실적정보 PARTIAL(전향 등록만, 수익 0회 조회) · B 산업확산 PARTIAL(매출 예측만) · C 투자자 수급 SOURCE_BLOCKED(KRX `LOGOUT`).

### A2. 중복 관계 (상세: `evidence/feature-overlap.md`)

- Phase C 38 ⊂ Atlas 106. 31변수 지역모델, 생산 13 하위입력, 레이더 28변수는 대부분 Atlas에 이미 baseline으로 들어가 있다.
- 같은 정보의 재표현: 모멘텀 3변형 순위상관 ≈0.99, 거래량 충격 2변형 ≈0.97, 잠정실적 매출의 97.5%가 정식공시와 1% 이내, 가격 기반 산업확산은 X3/A09/A10/H 계열의 재표현.
- 따라서 "106개를 시험했다"는 독립 정보축 수가 아니다. 실제 독립 축은 가격·추세 / 재무수준 / 재무변화 / 산업 재구성 4개 정도이며, **소유·거래 행동(insider/flow)과 매크로 상호작용은 한 번도 측정되지 않았다.**

### A3. KR C2: 전체 CAGR +1.8pp인데 6/12개월 평균은 왜 열세인가 (기존 증거만 사용)

저장 일별 경로(`weekly-passive-first-v1-replay-corrected-benchmark.json` `regions.KR.paths.C2`, 이미 공개된 값):

| 구성요소 | 값 | 출처 | 해석 |
|---|---:|---|---|
| CAGR C2 / ETF | 14.258% / 12.507% (+1.752pp) | 저장 경로 | #309 주간 표본은 +1.8181pp(2013-01-11 시작) |
| 순 산술 active | +0.62pp/yr | 저장 경로 | 비용 차감 후 |
| 복리(기하−산술) | +1.131pp | 저장 경로 | CAGR 우위의 약 65%가 변동성 차이(17.0% vs 22.3%)에서 오는 복리 효과 |
| 비용 drag | 1.652%/yr, 회전율 4.195x/yr | 저장 경로 | 총(비용 전) 산술 우위는 대략 +2.3pp/yr |
| 시장 노출 | 사후 β 0.63 [0.51, 0.75], (β−1)·ETF 항 −5.12pp/yr, 절편 +6.12pp/yr | #311 | **사후 전체표본 회귀**: 거래 가능한 노출이 아니며 선택 알파로 인증 불가 |
| 연도 집중 | 상위 3년(2018, 2022, 2014)이 로그 초과의 234.2% | #309 | 세 해를 빼면 −3.31pp |
| 최근 | 2024–26 −12.67pp/yr | #309 | ETF 급등기 미참여 |
| 산업 효과 | **UNAVAILABLE** | #311 | 공식 KODEX200 구성·업종 가중 이력 부재 |

6/12개월 평균 차이(−0.52pp / −0.88pp)가 음수인데 승률(59.6% / 61.2%)과 평균 상대자산 증가(+1.16% / +3.21%)는 양수인 이유는 산술 항등식 `Rc−Re = W + Re·W`이다(#309). β≈0.63인 경로는 ETF가 크게 오를 때 덜 오르므로, 강세 창의 결합항 `Re·W`(−1.67pp / −4.09pp)가 평균을 끌어내린다. 즉 **C2는 자주 이기지만 큰 상승장에서 크게 지는 저베타·방어형 경로**이고, 장기 CAGR 우위의 대부분은 낮은 변동성의 복리 효과다. 종목선정 효과는 아직 분리되지 않았다(Package B).

### A4. 입증된 알파 수 (상세: `evidence/proven-alpha-count.md`)

기준: 사전등록 + 다중검정 보정 + 표본외 또는 전향 + 비용 후.
**KR 0, US 0.** 가장 근접했지만 탈락한 것: KR lowvol IC(+0.0511, 지역 단독이며 pooled Holm p 0.44), 산업 OCF-yield IC(+0.1364, 2025 이후 부호 반전, 검정력 23%), #310 H1(매출 예측일 뿐 수익률 아님), C2(+1.8pp, 사후·집중·저베타).

---

## Package B — C2 Economic Validation (`c2-fixed-exposure-attribution-v1`)

C2의 선택·날짜·비중은 바꾸지 않았다. 아래는 **실제 원천 재고**와 **결정적 계산 코드**이며, 실제 C2 outcome으로 귀속을 계산하지는 않았다. Phase D 종료 계약(§7)상 새 KR 역사 outcome 작업에는 Owner의 정확한 해시 승인이 필요하다.

### B1. 원천 재고 (outcome-blind; 상세 `evidence/c2-source-inventory.{md,json}`, `evidence/c2-price-coverage.json`, `c2-readiness.json`)

| # | 항목 | 판정 | 증거 |
|---|---|---|---|
| 1 | 블록별 목표 보유·비중 | **PRESENT** | `docs/results/regional-standalone-paths.json.gz` sha256 `7a09751f…`(내용 digest `d92f7e14…` = replay `regionalPathsSha256`), 155/155 블록, 매 블록 3종목, 주식 비중 0.418–0.650, 72종목. C2 = 이 비중 + 잔여 069500.KS |
| 2 | 실제 체결·주문 장부 | **ABSENT** | 목표 비중 재생뿐. 실현 체결 기록 없음 |
| 3 | 종목 일별 주주수익 가격 | **PRESENT / 배당 PARTIAL** | replay-v16 manifest `f0781292…`: 72종목 모든 보유 세션 가격 존재. 기준 = 체결가 + Yahoo 분배 누적(부분). 배당 이벤트 0인 보유종목 5개(000030, 000060, 002550, 047040, 207940) |
| 4 | 첫 기준일 이전 253세션 | **PARTIAL** | 종목은 모두 ≥499 종가. 교정 ETF는 2012-01-02 시작으로 2013-01-07 이전 251개(초기 β 창 ETF 수익 ≤250개, 200개 하한은 통과) |
| 5 | 상장폐지 보유 | **PRESENT, 종결대가 불필요** | 22개 중 3개 보유(000030, 000060, 002550), 모두 상장폐지 1.5년 이상 전 매도. 배당 연혁은 BLOCKED |
| 6 | 069500.KS | **총수익 PRESENT / 공식 NAV·구성 ABSENT** | `benchmark-reconciliation-corrected.json` sha256 `58580c43…` PASS, 46개 분배. KODEX200 NAV·구성·업종 가중 이력 없음 → Brinson 불가 |
| 7 | 투자 가능한 KRW 현금 | **SOURCE_BLOCKED** | BOK 기준금리 proxy(`data/bok-policy-rates.json` `a7edf0e5…`, 2026-09-07까지 검증)만 존재. CD91·KOFR·MMF 미등록 |
| 8 | 거래비용 | **PRESENT(가정)** | `weekly_decision.trade_cost_fraction`: 수수료 1.5bp + 스프레드 8bp의 절반, 주식 매도 시 날짜별 거래세, ETF 매도세 0 |
| 9 | 미국 유사 경로 | **PARTIAL** | SPY·126종목 가격 존재. 현금은 DFF proxy. 체결 없음. 생존편향 라벨 모순(replay `SURVIVORSHIP_BIASED_PARTIAL` vs standalone `LOW`) |

### B2. 계산 계약과 코드 (실행 전 고정)

- 사전등록: `c2-fixed-exposure-attribution-v1.json`. 입력 5개 파일과 replay manifest는 sha256으로 고정했다.
- 블록 항등식(코드에서 매 블록 단언): `C2 − ETF = SELECTION + EXPOSURE`.
  - `SELECTION = s·(R_S − b·R_E − (1−b)·R_F)`
  - `EXPOSURE = s·(b−1)·(R_E − R_F)`
- `b`는 신호일까지의 252개 일수익 OLS β만 사용한다. 전체표본 β(#311의 0.63)는 쓰지 않는다. 레버리지가 필요한 대조군은 ETF 100%로 상한 처리하고 그 횟수를 기록한다.
- 현금은 측정값이 아니라 시나리오 대역 {0, BOK proxy, BOK+100bp}이다. 판정은 세 시나리오가 모두 일치할 때만 내린다.
- 비용 1x/2x/3x, 회전율은 종목 교체와 비중 재조정으로 분리한다. H126/H252는 6·12블록 창, 복리는 산술 active + Jensen 항등식, MDD는 블록 말 기준이다.
- 판정은 `SELECTION_SURVIVES_FIXED_EXPOSURE` / `NO_SELECTION_EVIDENCE_CI_CONTAINS_ZERO` / `SELECTION_NEGATIVE_AFTER_FIXED_EXPOSURE` / `SOURCE_OR_SAMPLE_INSUFFICIENT` 중 하나다. 어떤 결과도 C2를 승격하지 않는다.
- 코드: `c2_attribution.py`(순수 함수), `c2_attribution_run.py`.
  - `readiness`: outcome-free, 실행 완료.
  - `execute`: `AUTHORIZATION-c2.json`의 정확한 문구와 코드 해시가 없으면 거부.
- 합성 테스트 21개: 순수 β 장부의 선택 0, 심은 알파 복원, 무작위 500블록 항등식, 레버리지 클립, β 결측 fail-closed, 신호일 이후 미참조, 저장 행 buy-and-hold 항등식, 승인 없는 실행 거부.
- 독립 감사 기준은 사양 `independentAuditCriteria`에 있다.

### B3. 이번에 계산하지 않은 것

실제 블록별 SELECTION·EXPOSURE 값, C2 대 대조군 CAGR, H126/H252 분포는 계산하지 않았다. 이유는 (1) Phase D 종료 계약상 Owner 승인이 필요하고, (2) 투자 가능한 KRW 현금 원천이 `SOURCE_BLOCKED`이기 때문이다. 산업 귀속(Brinson)은 공식 ETF 구성 부재로 승인 후에도 `UNAVAILABLE`이다.

---

## Package C — Next Alpha Thesis: `kr-insider-open-market-purchase-v1`

### C1. 후보 2개의 원천 적격성 비교 (outcome-blind 실측)

| 기준 | KR 임원·주요주주 장내매매 (DART) | US 내부자 매수 (SEC Form 4) |
|---|---|---|
| 기존 연구와의 중복 | Atlas·Phase C·31변수·생산 요인에 없음 | 저장소에서 수집된 적 없음 |
| PIT | DART 접수일 → 다음 KRX 세션 | FILING_DATE, 2013Q1 지연 중앙값 2일(p90 7일) |
| 이력 | list.json 2013–2026: 표본 24개 발행사에서 원본·정정 5,258건, 연도마다 17~22/24개사 공시, 호출 오류 0 | 2006+ 분기 데이터셋 |
| 구조화 | 원본 XML 속성(`RPT_RSN`, `MDF_DM`, `STR_KND`, `MDF_STK_CNT`, `ACI_AMT2`); 표본 원본 42건 중 42건 파싱(parser v2; v1은 가격 셀 형식 때문에 40/42), 21건에 장내 매매 행 존재 | TSV `TRANS_CODE='P'` 명시. 2013Q1 S&P 500 매수 261행·82개사 |
| 자동 접근 | 이 환경과 CI 모두 DART 키로 작동 | 연락처 주소를 밝히지 않은 요청에 SEC가 403; Actions egress는 기존에 거부 → `ACCESS_CONDITIONAL` |
| 가격 패널 | KR 260종목 전부 가격 존재, 종결 22개는 v4 라벨 적격 규칙 | 퇴출 212개 신원 가격 부재 → 역사 outcome `BLOCKED_BY_DATA_INTEGRITY` |
| 종료 계약 | KR 역사 종료(Phase D): 실행에는 Owner 예외 필요 | US는 열려 있으나 생존편향 표본 |
| **결정** | **채택(1개)** | 미국 대응 연구로 보류(별도 등록) |

구조화 엔드포인트 `elestock.json`은 약 2년만 제공한다(삼성전자 3,368행, 2024-11-11~2026-11-03). 따라서 역사 구축에는 원본 공시 파싱이 필수다. 첫 실측 실행에서 `pblntf_detail_ty=D002` 필터가 적용되지 않아 5% 대량보유 보고가 섞였다. 그 결과는 폐기했고, 보고서명 필터와 전 페이지 순회로 다시 측정했다(`kr_insider_probe.py` 독스트링에 기록).

### C2. 사전등록 요약 (`kr-insider-open-market-purchase-v1.json`)

- **메커니즘:** 임원·주요주주의 재량적 장내 매수는 장기 기업가치에 대한 사적 정보를 담는다. 공시되지만 대형주에서 주목도가 낮아 과소반응이 있다면 6~12개월에 걸쳐 누적될 수 있다. 소형주 중심 해외 문헌이 대형 KR Top-120에서도 재현된다는 보장은 없다.
- **정보:** 원본 공시의 `장내매수(+)` / `장내매도(-)` 보통주 행만 센다. 증여·상속·스톡옵션·신규선임·유상신주·장외 거래는 기록만 하고 세지 않는다. 사유 코드를 추측해 번역하지 않는다.
- **상태:** 기준일까지 이용 가능한 공시의 최근 63세션 순 장내 주식수 → `NET_BUYER` / `NET_SELLER` / `NO_OPEN_MARKET_TRADE`. 가격을 쓰지 않는다.
- **유니버스·시점:** PIT KRX Top-120 보통주, C2와 같은 155개 21세션 기준일.
- **라벨:** 다음 세션 종가부터 H126/H252 주주 총수익. v4 라벨 적격 계약을 따르며, 부적격 종목은 두 바스켓 분모에서 모두 제외한다.
- **1차 통계:** 기준일별 `NET_BUYER` 동일가중 − `NO_OPEN_MARKET_TRADE` 동일가중 스프레드. 매수자 5개 미만 또는 대조 20개 미만인 기준일은 값을 내지 않는다.
- **추론:** Newey–West(lag 5 / 11), 두 1차 주장에 Bonferroni 97.5%.
- **경제성:** 롱온리 `NET_BUYER` 바스켓 대 069500.KS, 비용 1x/2x/3x, CAGR·H126/H252·MDD·회전율(교체/재조정 분리)·Jensen.
- **효과크기:** MDE = 3.08·σ_S/√N_eff(H126 약 0.62σ, H252 약 0.89σ). σ_S는 outcome이라 추정하지 않았다. 구간 폭이 ±3pp보다 넓으면 `UNDERPOWERED_NOT_NEGATIVE`로 판정한다.
- **실패 기준:** 파싱 실패 > 5% → `SOURCE_BLOCKED`; 밀도 게이트(기준일 60%에서 매수자 ≥5 및 대조 ≥20) 미충족 → `POWER_BLOCKED`; H126 구간에 0 포함 → `NO_EVIDENCE`(H252로 구제 불가).
- **사후 구제 금지:** 창·임계값·라벨·유니버스·기간·비용·최소 바스켓 크기를 결과를 본 뒤 바꾸지 않는다.
- **코드:** `kr_insider.py`(원본 XML 속성 파서, 장내 순매매, PIT 가용 세션, 상태, 기준일 스프레드), `test_kr_insider.py`(합성 9개). 실제 공시 1건에서 3행·순 −8,584주를 읽었고, 이는 공시 자체의 합계행(−8,584)과 일치한다.

### C3. 데이터 준비율 (6/12개월 실증 기준)

데이터 준비율은 라벨 없이 측정했다. 수익률은 0회 읽었다.

| 필요 항목 | 상태 | 준비율 / 근거 |
|---|---|---|
| PIT 유니버스(Top-120 스냅샷) | READY | ledger/universe/kr 164개 스냅샷(#308 수집 기록), DART 발행사 254/260 해석 |
| 내부자 공시 목록(2013–2026) | PARTIAL | 254개 중 24개 발행사(9.4%) 전 연도 수집. 표본 5,258건 → 전체 약 55,600건 (선형 투영, 측정값 아님) |
| 공시 원문 파싱 | READY(표본) | 42/42 (100%, parser v2). 사유 코드 `01`=`장내매수(+)`, `02`=`장내매도(-)`가 라벨과 함께 관측됐으나 판정은 라벨만 사용. 1건은 거래일이 접수일보다 212일 늦은 입력 오류였고, PIT는 접수일 기준이라 영향 없음 |
| 공시 지연 | MEASURED | 접수일 − 최근 거래일 중앙값 3일, 최대 28일 (n=42) |
| 밀도 게이트(기준일 60%에서 매수자 ≥5) | UNKNOWN | 전체 수집 전에는 판정 불가. 표본 원본의 52.4%(22/42)는 장내 순매매 0 |
| 가격·주주수익 라벨 | READY(조건부) | replay-v16 KR 260종목. 종결 22개는 v4 라벨 적격 규칙으로 제외 |
| 069500.KS 총수익 | READY | 교정 시계열 sha256 `58580c43…` |
| 비용 모델 | READY | `weekly_decision.trade_cost_fraction` |
| 실행 승인 | ABSENT | Owner 정확한 해시 승인 + KR Phase D 예외 필요 |

**요약:** 필요한 데이터 구성요소 8개 중 6개 READY, 1개 PARTIAL(공시 수집 9.4%), 1개 UNKNOWN(밀도 게이트). 실행 승인은 없다. 전체 수집에는 약 55,600건의 원문 호출이 필요하며, DART 일일 한도 20,000건 기준으로 약 3일이 걸린다.

---

## Package D — Evidence-to-Decision

| 구분 | 과거 결과(이미 노출된 역사) | 미래에 검증할 가설 |
|---|---|---|
| KR | Phase C/D 0 통과; C2 +1.8pp는 사후·저베타·복리·집중 | C2 고정노출 귀속(승인 대상); 내부자 장내매수(수집 → 승인 → 실행 → 전향 확인) |
| US | 31변수 0; 오버레이는 위험 대 수익 교환; 패널 생존편향 | 내부자 Form 4(접근 조건과 생존편향 해결 후 별도 등록) |

**리포트 표시 계약** (기존 #314 일일 브리프의 규칙을 바꾸지 않고 재확인):

1. 검증 통과 모델이 없으면 KR은 **"0개 · 069500.KS 100%"**, US는 **"0개 · SPY 100%"**로 표시한다. QQQ는 보조 비교 행이며 기본값이 아니다. 종목명·비중은 표시하지 않는다.
2. 종목 0~5개는 투자 승인 레지스트리에 등록된 신호가 사전등록 판정을 통과했을 때만 표시한다. 현재 등록 항목은 0개다.
3. 성과는 세 가지를 분리해 표시한다: 실계좌(없음, 0%로 표시하지 않음) / 전향 페이퍼(`PROSPECTIVE_PAPER`) / 역사 탐색(`HISTORICAL_DEVELOPMENT`, 브리프에 넣지 않음).
4. C2와 내부자 가설은 "연구 중 · 미검증"으로만 언급하고 매수 후보로 나열하지 않는다.
5. 실증 알파 없이 종목을 강제로 추천하는 기능은 만들지 않았다.

---

## 재현

```sh
python research/alpha_evidence_sprint_v2/c2_attribution_run.py readiness --out /tmp/c2-readiness.json   # outcome-free
DART_API_KEY=... python research/alpha_evidence_sprint_v2/kr_insider_probe.py --out <dir> --issuers 24 --docs-per-year 3
DART_API_KEY=... python research/alpha_evidence_sprint_v2/kr_insider_probe.py --out <dir> --reparse <dir>/kr-insider-probe.json.gz
python research/alpha_evidence_sprint_v2/us_insider_probe.py --out <dir> --from-zip <2013q1.zip>
python -m pytest -q research/alpha_evidence_sprint_v2/
```

`#315`, `#306`, `#314`, `#299`, `#307`, 운영 코드, 봉인, 실행 잠금, `research_specs/`, `docs/results/`는 수정하지 않았다. 이 브랜치는 PR #308(종료·보존)의 두 커밋 위에 쌓였으며, 그 파일은 그대로 남아 있다.

## Owner 결정이 필요한 항목만

1. **C2 귀속 실행:** `AUTHORIZATION-c2.json`(문구 `APPROVE KR_PHASE_D_EXCEPTION c2-fixed-exposure-attribution-v1 <사양 sha256>` + 두 코드 파일 sha256) 커밋 여부. 투자 가능한 KRW 현금 원천이 없어 결과는 현금 대역 판정만 가능하다.
2. **투자 가능한 KRW 현금 원천:** CD91 또는 KOFR 시계열(ECOS 항목코드)을 등록할지 여부. 등록 전까지 `SOURCE_BLOCKED`.
3. **내부자 공시 전체 수집**(outcome-free, 약 수만 건 DART 호출): 진행 여부. 수집 후 파싱률과 밀도 게이트를 라벨 없이 판정한다.
4. **내부자 가설 역사 실행:** 수집·게이트 통과 후 KR Phase D 예외로 실행할지, 전향 기록만 할지.
5. **US Form 4:** SEC에 신고할 연락처를 포함한 수집 방식(Actions egress 불가)을 허용할지 여부.
