# 미국 이중 벤치마크 기반 — us-dual-benchmark-foundation-v1 (SPY + QQQ)

**증거 등급:** ETF 비교는 `DESCRIPTIVE_ETF_COMPARISON_NOT_ALPHA`(기술 통계), 데이터·멤버십·커버리지 감사는
`OUTCOME_BLIND`(종목 수익률·라벨·모델 출력을 읽지 않음). **새 알파 연구는 실행하지 않았다.**
`weekly-passive-first-v1`, 주간 영수증, `config.json`의 공식 벤치마크(`benchmarks.US = SPY`)는 바뀌지 않는다.

| 산출물 | 경로 |
|---|---|
| SPY·QQQ 총수익 스냅샷(연구용, 봉인 입력 아님) | `data/research/us-dual-benchmark-v1/spy-qqq-total-return.csv.gz` + `manifest.json` |
| 데이터 무결성 감사 | [`docs/us-readiness/us-dual-benchmark-v1-data-audit.json`](us-readiness/us-dual-benchmark-v1-data-audit.json) |
| SPY/QQQ 비교(JSON·차트) | [`us-spy-qqq-comparison-v1.json`](us-readiness/us-spy-qqq-comparison-v1.json), [`.svg`](us-readiness/us-spy-qqq-comparison-v1.svg) |
| 나스닥100 PIT 멤버십 감사 | [`nasdaq100-pit-membership-v1.json`](us-readiness/nasdaq100-pit-membership-v1.json) |
| S&P 500 ∪ 나스닥100 커버리지 갭 | [`us-universe-coverage-gap-v1.json`](us-readiness/us-universe-coverage-gap-v1.json) + 종목별 `us-universe-coverage-manifest.csv.gz` |
| 연구 어댑터 | `pipeline/us_dual_benchmark_adapter.py` |
| 재현 | `python scripts/build_us_dual_benchmark_foundation.py` (`--stage compare`는 커밋된 파일만 읽음) |

결과 파일은 `docs/results/`가 아닌 `docs/us-readiness/`에 둔다 — Phase C 등록이 `docs/results/` 전체를 고정하기 때문.

## 1. 결론 먼저

1. **QQQ 데이터는 새로 받지 않았다. 이미 봉인돼 있었다.** QQQ는 `config.json universe.US`의 구성원이라 `replay-v16`
   봉인 입력(`signal-history@704d7db6`, manifest `f0781292…`)의 가격 패널에 SPY와 **같은 벤더 경로**
   (`YAHOO_UNADJUSTED_WITH_ACTIONS`)와 **같은 조정**(`as-traded-forward-total-return-v1`)으로 들어 있다.
   두 다리를 같은 봉인 매니페스트에서 꺼내는 것이 "같은 기준"을 보장하는 가장 강한 방법이다. → `QQQ_DATA_READY`
2. **같은 기간·같은 세션에서 QQQ의 역사적 수익은 SPY보다 높았고, 변동성과 상대 낙폭도 컸다.** 이것은 한 표본의
   기술 통계이며 미래 비중의 근거가 아니다. → `SPY_QQQ_COMPARISON_READY`
3. **나스닥100 PIT 멤버십은 PARTIAL.** 무료로 재현 가능한 유일한 원천은 파생(비공식) 기록이다. 발표일이 없고
   증권 식별자가 없다. 공식 원천은 이 환경에서 닿지 않았다. → `NASDAQ100_PIT_STATUS_EXPLICIT`
4. **이중 벤치마크 연구 어댑터는 준비됐고, 알파 연구는 실행하지 않았다.** → `US_DUAL_BENCHMARK_ADAPTER_READY`,
   `FUTURE_US_ALPHA_STUDY_NOT_EXECUTED`

## 2. QQQ·SPY 데이터 (사실)

| 항목 | SPY | QQQ |
|---|---|---|
| 원천 위치 | `benchmark/<YYYY-MM>` | `price/<YYYY-MM>` |
| 기간 | 2011-01-03 ~ 2026-09-14 | 2011-01-03 ~ 2026-09-14 |
| 세션 | 3,947 | 3,947 |
| XNYS 대비 누락/초과 | 0 / 0 | 0 / 0 |
| 중복·비양수 종가 | 0 | 0 |
| 분할 | 없음 | 없음 |
| 분배금 이벤트(봉인) | **0 — 봉인되지 않음** | 64 |
| 분배 적용 배수 | 검증 불가 | 64건 모두 **1.000** |

- **이중 반영 방지:** `apply_distributions`는 `SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED` 종가만 받는다. 이미 총수익인
  종가(야후 `auto_adjust=True`, 이 저장소의 `Close`)에 분배를 다시 곱하는 호출은 `DoubleCountRefused`로 거부된다.
  `reconstruct_raw_close`가 전방 레시피를 역산해 원 종가를 복원하고, 분배락일마다 계수가 몇 번 들어 있는지 측정한다.
  KODEX 200 결함은 2.0이었고 QQQ는 1.000이다. QQQ 첫 세션(2011-01-03) 종가 55.31은 인쇄된 원 종가다(전방 앵커 확인).
  QQQ 총수익 CAGR − 가격 CAGR = 연 1.00%p로, 연도별 분배수익률 0.25–1.67%와 같은 크기다(두 번이 아니라 한 번).
- **SPY의 한계(명시):** SPY는 `benchmark_source._yahoo_close` 경로로 들어와 재조정된 `Close`만 남았고 분배 이벤트는
  봉인되지 않았다. QQQ를 만든 것과 같은 `fetch_prices(total_return=True) → to_total_return` 경로이지만 SPY 자체의
  단일 반영은 봉인 데이터만으로 **증명할 수 없다.**
- **일관성 점검(독립 대조 아님):** 봉인 SPY는 `ledger/benchmarks/SPY.jsonl.gz` 스냅샷과 3,947세션에서 완전히 일치한다
  (같은 벤더 계보). 공식 주간 재현의 SPY(P1) USD CAGR 14.734%를 이 스냅샷이 14.740%로 재현한다(차 0.006%p; 공식 경로는
  진입 비용과 주간 블록 연결을 포함).
- **외부 대조: 수행하지 못함.** 이 환경의 프록시는 Yahoo·Nasdaq·Stooq·SEC를 거부한다. 이 에이전트에게는 Actions
  dispatch 권한이 없다(HTTP 403). PR 트리거로 프로브를 돌리는 우회는 권한 정책으로 거부돼 하지 않았다.
  `scripts/probe_nasdaq100_sources.py`(표준 라이브러리만, URL 고정, 1회 시도, 자격증명 없음)가 Nasdaq의 원 종가·분배금
  (QQQ·SPY)과 멤버십 후보 원천을 받아 대조하도록 준비돼 있다. 다만 `.github/workflows/probes.yml`은 봉인된 KR 명세 2건
  (`kr-industry-membership-foundation-v1`, `market-industry-stock-data-foundation-v1`)이 해시로 고정하고 있어
  드롭다운 옵션을 추가하지 않았다(추가하면 그 봉인이 깨진다). 실행 방법(재봉인 또는 다른 실행 환경)은 소유자 결정이다.
- **SPY의 레거시 이력은 다시 쓰지 않았다.** `signal-history`에 아무것도 쓰지 않았다. 스냅샷은 연구 데이터셋이며 봉인 입력과 분리된다.
- **결정성:** 같은 입력으로 두 번 빌드하면 모든 산출물이 바이트 단위로 같다. 스냅샷 SHA-256 `a82c64b9…`.

## 3. SPY vs QQQ — 같은 날짜, 같은 기준 (기술 통계)

**헤드라인 기간은 QQQ 수치를 보기 전에 기존 미국 주간 재현의 실행 기간으로 고정했다**: 2013-01-07 ~ 2026-09-14,
일치 세션 3,442, 13.68년. 전체 봉인 중첩(2011-01-03~)은 보조로만 함께 싣는다.

| USD (총수익, 세전) | SPY | QQQ |
|---|---:|---:|
| 누적 수익 | +556.4% | +1,089.8% |
| CAGR | **14.74%** | **19.84%** |
| 연 변동성 | 16.77% | 20.84% |
| 최대 낙폭 | −33.72% (2020-02-19→03-23) | −35.12% (2021-12-27→2022-11-03) |
| 낙폭 회복 | 2020-08-10 | 2023-12-13 |
| 샤프(초과: 연방기금 실효금리 DFF, ACT/360) | 0.80 | 0.89 |
| 매매비용 차감 CAGR(진입 0.15%, 청산 0.18%, 동일 적용) | 14.71% | 19.81% |

- **상대 경로:** QQQ/SPY 부(富) 비율은 1.81배로 끝났다. 그 사이 QQQ의 최대 **상대** 열위는 −21.1%였다
  (2021-11-30 → 2023-01-05). 일간 상관 0.930, 추적오차 8.08%, SPY 대비 베타 1.16.
- **연도별(완전한 12년):** QQQ 우위 9년, **SPY 우위 2016(−4.9%p)·2021(−1.3%p)·2022(−14.4%p)**. 2013(1/7 시작)과
  2026(9/14까지)은 부분 연도로 표시했고 둘 다 QQQ 우위다. 약한 해도 빼지 않았다.
- **롤링:** 1년 창에서 QQQ 우위 비율 78.2%(최악 −19.0%, 2022-12-27 종료). 3년 창 93.0%(최악 −3.8%).
  창이 겹치므로 이 비율은 서술이지 독립 표본 확률이 아니다.
- **원화 투자자 관점(H.10 DEXKOUS, 세션별 같은 환율):** SPY 16.70%, QQQ 21.89%. USD/KRW는 1,062.5 → 1,340.3(+26.1%)이었다.
  환율은 두 ETF에 같은 배수를 곱하므로 수준과 변동성은 바꾸지만 **QQQ/SPY 비율은 바꿀 수 없다**(검증 오차 0.0).
  원화 기준 낙폭이 더 얕은 것(SPY −29.6%)은 2020년 급락기 원화 약세 때문이며 자산 성과가 아니다.
- **보수:** ETF 보수는 시장가 총수익 안에 이미 들어 있어 다시 빼지 않았다. 이 PR에서 보수율 수치는 공식 문서로
  확인하지 못했다(미검증).
- **보조(2011-01-03~):** SPY 14.05%, QQQ 18.65%.

**말할 수 없는 것:** 이 표본에서 QQQ가 높았다는 사실은 앞으로의 QQQ 비중, 종목 선택 능력, QQQ의 지속 우위
어느 것의 근거도 아니다. 2013–2026은 대형 기술주가 유난히 강했던 한 구간이다.

## 4. 수학적 단순화 — 벤치마크를 바꿔도 새 발견은 생기지 않는다

같은 날짜·지평·유니버스에서 `alpha_QQQ(i,t) = alpha_SPY(i,t) − [R_QQQ(t) − R_SPY(t)]`이고, 괄호 항은
그날 모든 종목에 같다. 그래서:

- 날짜 내 순위, 스피어만 순위 IC, 순위 기반 상·하위 그룹은 **동일**하다(셀 단위 오차 <1e-15, IC 차이 <1e-12, 테스트 고정).
- 바뀌는 것은 **수준**이다: 기대 초과수익, 비용 차감 문턱, 양(+)의 비율, 즉 "ETF를 종목으로 바꿀 가치가 있는가".
- 어댑터는 순위 통계를 **한 번만** 계산해 `benchmarkInvariant`로 표시한다. 벤치마크 스프레드는 날짜 단위 계열 하나로
  다루며 N개 종목 관측으로 부풀리지 않는다. SPY→QQQ 차감은 새 특징군도, 새 발견 기회도 아니다.

## 5. 나스닥100 PIT 멤버십 — PARTIAL

| 후보 원천 | 실제 시험 | 결과 |
|---|---|---|
| Nasdaq 공식 보도자료(연례 재구성·교체) | 웹 검색으로 제목·URL 확인, 본문 미수집 | 최선의 공식 경로. 이 환경에서는 차단, Actions 미측정 |
| Nasdaq Global Index Watch 이력 파일 | 미시험 | 유료(가격 미확인·미구매) → `BLOCKED_PAID_SOURCE` |
| Nasdaq API 현재 목록 / Invesco QQQ 보유 | 이 환경 차단 | 오늘 목록뿐 → 역사용 불가(생존편향 100%) |
| SEC QQQ N-PORT 분기 보유 | 기존 측정 인용 | CUSIP이 있는 최선의 신원 대조. SEC가 Actions egress를 차단 |
| 위키백과 개정 이력 | 이 환경 차단(프로브 준비) | 비공식, CC BY-SA. 아래 원천의 상류 |
| **n100tickers** (`jmccarrell/n100tickers@ec99dfb8`, MIT) | **수집·고정(raw.githubusercontent.com 접근 가능)** | **사용 — 파생·비공식** |
| 상용 API(Norgate·EODHD·Eulerpool) | 미시험 | 유료 → `BLOCKED_PAID_SOURCE` |

- **재구성:** 2013-01-01 기준 목록에서 87개의 날짜별 변경을 **효력일 순서로만** 적용한다. 2007–2026 연도 파일 20개를
  SHA-256과 함께 고정했다. 연간 연결 일관성(전년 변경 적용 = 다음 해 1월 1일 목록) 19/19년 일치.
  2013–2025 연례 재구성 13회 모두 검출(연도 공백 0). 구성 수 100–105. 역대 구성 심볼 233개.
- **정보 가용성 규칙:** 발표일이 있으면 발표일, 없으면 효력일부터 사용한다. 지수 변경은 항상 효력 전에 발표되므로
  이 대체는 정보를 더 늦게 쓸 뿐 미래를 엿보지 않는다. 발표되었으나 아직 효력 전인 변경은 `pending`으로만 둔다.
  오늘 목록을 과거로 채우지 않는다. 나스닥 상장은 지수 편입을 뜻하지 않는다.
- **신원:** 증권 식별자가 없다. 1대1 교체 57건 중 Finnhub CIK로 **다른 회사 교체**가 증명된 것 29건, 원천 주석상
  티커 변경(미검증) 3건, 식별 불가 25건(FB→META, PCLN→BKNG 포함). 원천이 Comcast CMCSK(2014-12-22) 누락을 스스로
  밝히고 있다.
- **대조(본문 미수집):** 검색으로 드러난 공식 보도 제목 7건(2014-12-22 연례, 2020 DXCM·DOCU·MRNA, 2024 SMCI,
  2026 LITE·SPCX)과 효력일·편입·편출이 모두 일치했다.
- **판정 PARTIAL인 이유:** 단일 파생 원천, 발표일 없음, 식별자 없음, 알려진 누락, 공식 원천 미대조.

## 6. 커버리지·갭 (2013-01-01 ~ 2026-09-14, 종목별 매니페스트)

| 집합 | 심볼 | READY | 신원 수리 | 유료 원천 차단 | 가격 필요 |
|---|---:|---:|---:|---:|---:|
| 역대 S&P 500 | 827 | 606 | 38 | 183 | 0 |
| 역대 나스닥100 | 233 | 132 | 12 | 31 | 58 |
| 나스닥100 전용 | 58 | 0 | 0 | 0 | 58 |
| 합집합 | 885 | 606 | 38 | 183 | 58 |

- Finnhub PIT 저장소는 **782종목, 34,945건**으로 측정됐다(준비도 문서의 34,941 + 회계연도 비정상 4건). 합집합 중 785개가
  공시를 갖고 있고(이름 변경 후속 포함), 100개는 없다. 가격이 있는 606개는 모두 공시가 있다. 그래서 `NEEDS_FUNDAMENTALS`는
  1차 상태로 나오지 않지만 `gaps`에는 기록된다.
- **유료 원천 차단 183개:** 무료 벤더에 이미 요청했고 두 번 거부된 상장폐지·피인수 S&P 500 종목이다(polygon
  PLAN_LIMITED, FMP 402). 나스닥100에서도 31개(YHOO, CELG, XLNX, ATVI, WBA 등)가 같은 이유로 막혀 있다.
- **신원 수리 38개:** 지금의 패널이 다른 발행사의 것(티커 재사용) 또는 멤버십보다 늦게 시작하는 경우다
  (DELL, FOX/FOXA, DOW, IR, SNDK, NWSA, FB, PCLN …). EA 등 일부는 v3 감사 분류를 그대로 물려받아 재검토가 필요할 수 있다.
- **나스닥100 전용 58개**(ASML, BIDU, JD, PDD, MELI, TEAM, ZS 등)는 무료 벤더에 **요청된 적이 없다**. 그래서 유료
  차단으로 분류하지 않는다. 다수는 해외 발행사(20-F)라 Finnhub 10-K/10-Q 경로로 재무가 덮이지 않을 수 있다.
- 결측 수익을 0으로 읽지 않으며, 생존 종목만으로 과거 유니버스를 줄이지 않는다.
- **공식 차단: 완전한 나스닥100 역사적 종목 백테스트는 지금 불가능하다**(멤버십 PARTIAL, 상장폐지 31개 유료, 58개 가격 미수집).

## 7. 연구 어댑터 (`pipeline/us_dual_benchmark_adapter.py`)

- `BenchmarkIdentity`(역할·티커·스냅샷 해시·기준·벤더·무결성 상태). 역할과 티커가 엇갈리면 거부한다.
  어느 한쪽이라도 무결성이 `PASS`가 아니면 계산은 하되 `headlineEligible=false`.
- `StudyDesign`: 지평, 유니버스 ID, 비용, 최대 0–5종목, **잔여 자산은 선언 필수**(기본값 없음 — 사후 선택 방지).
- `forward_returns`(한 캘린더, 결측은 NaN), `common_date_mask`, `benchmark_spread`, `identity_error`,
  `rank_ic_by_date`(1회 계산), `replacement_hurdle`(종목 매매비용 − 회피한 ETF 매매비용),
  `per_benchmark_economics`(보유 종목 결측일은 측정 불가, 생존자 재정규화 금지), `paired_evaluation`,
  `alternative_paths`(`P0_SPY`·`P0_QQQ`·`P1_STOCKS`가 **같은 평가 모집단**, 보유 종목 결측 시 경로 중단).
- 프로덕션(`weekly_decision`, `weekly_history`, `weekly_publish`, `benchmark_source`, `historical_replay`)은
  이 모듈을 가져오지 않는다(테스트 고정).

## 8. 다음 미국 연구 — `us-shareholder-distribution-change-v1`

**전향(prospective) 연구로 진행할 수 있다.** 단, 아래 조건에서만이다.

- SPY(공식)와 QQQ(대안)를 두 벤치마크로 쓴다. 신호 날짜의 미래 수익은 신호 이후에만 생기므로, 나스닥100 역사 멤버십의
  PARTIAL 상태는 **S&P 500 유니버스에서 QQQ를 비교 기준으로 쓰는 데 장애가 아니다.**
- 기존 Finnhub PIT 재무(782종목)에서 `cashDividendsPaidTtm`, `buybackTtm`과 전년 동기 대비 변화를 파생한다
  (재수집 없음). 주당배당 항목은 2019년 이후 단절이라 쓰지 않는다.
- **가장 작은 필수 수리:** (1) 파생 필드 정의와 "비지급=0 / 미보고=결측" 규칙 고정, (2) 사전등록 1건(가설·126거래일 지평·
  성공 기준·커버리지 하한·잔여 자산을 결과 전에 봉인), (3) 준비된 프로브로 QQQ·SPY 외부 대조를
  1회 실행(SPY 분배 단일 반영 증명; 실행 경로는 소유자 결정). 나스닥100 **전용** 종목 선택을 원할 때만 공식 멤버십 원천과 58개 가격 수집이 추가로 필요하다.
- 역사 탐색 예산은 닫혀 있다. 역사 백테스트로 특징을 고르지 않는다.

## 9. 거버넌스 기록

- `regional-alpha-model-v1`(NO_MODEL_EVIDENCE)을 재실행하지 않았다. 31개 특징을 다시 열지 않았다. 종목 수준 미래 수익을
  읽지 않았다. 모델을 재학습하지 않았다. 포트폴리오 모수를 최적화하지 않았다.
- **노출 기록:** SPY/QQQ ETF 수익(2011–2026)은 이 PR에서 관찰됐다. 이 구간의 SPY 결과는 기존 주간 재현에서 이미 노출돼 있었다.
  QQQ 결과는 벤치마크 비교로만 노출됐고 어떤 신호 정의에도 쓰이지 않았다.
- 봉인 KR/US 실험, 라이브 거래, 생산 배분, 공식 주간 영수증, `.github/workflows/tests.yml`은 건드리지 않았다.

## 10. 이 연구선의 불변식

`AGENTS.md`는 Phase C 명세가 해시로 고정한 파일이라 수정하지 않았다. 아래 규칙은 이 문서와 테스트
(`tests/test_us_dual_benchmark_foundation.py`)가 고정한다.

- **이름 붙은 벤치마크 둘, 공식은 하나.** `US_MARKET_BENCHMARK = SPY`가 공식, `US_GROWTH_BENCHMARK = QQQ`는 추가 대안이다.
  QQQ는 SPY 기반 과거 증거를 소급 수정하지 않는다. 생산 모듈은 연구 코드를 가져오지 않는다.
- **두 다리는 하나의 봉인 매니페스트에서.** 고정된 `signal-history` 커밋에서 구성요소 해시를 모두 검증하며 읽는다.
  새로 받은 QQQ는 다른 빈티지이므로 섞지 않는다.
- **분배는 한 번만, 그리고 횟수를 잰다.** 미조정 종가가 아니면 분배 적용을 거부한다. SPY의 단일 반영은 외부 대조 전까지 미해결 항목이다.
- **벤치마크 교체는 발견이 아니다.** 순위 통계는 한 번 계산하고, 벤치마크별로는 수준·문턱·부호 비율만 보고한다.
- **ETF 비교는 기술 통계다.** 헤드라인 기간은 QQQ 수치 전에 고정했고, 약한 해를 빼지 않으며, 보수를 이중 차감하지 않는다.
- **나스닥100 멤버십은 PARTIAL이며 이유를 말한다.** 효력일 기준으로만 쓰고, 기준 스냅샷이 없으면 재구성하지 않으며,
  오늘 목록을 과거로 채우지 않는다.
- **P1_STOCKS는 수익을 보기 전에 잔여 자산을 선언한다.** 기본값은 없다. 세 대안은 항상 같은 모집단에서 평가한다.
- **봉인 파일을 건드리지 않는다.** `AGENTS.md`, `.github/workflows/probes.yml`, `docs/workflow-inventory.md`,
  `docs/results/`는 다른 봉인 명세가 해시로 고정한 파일이라 이 PR에서 바꾸지 않았다.
