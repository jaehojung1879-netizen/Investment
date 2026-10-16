# 02 · 실제 사용 가능한 데이터·차단 데이터 매트릭스

**상태:** `DESIGN_ONLY_OUTCOME_BLIND`. 모든 상태는 커밋된 저장소 문서·감사 JSON에서 읽었다. 이번 작업에서 새로 수집하거나 프로브하지 않았다.

## 상태 어휘

| 상태 | 뜻 |
|---|---|
| `READY` | 커밋된 PIT 데이터와 코드가 있고 감사 기록이 있다 |
| `READY_WITH_CAVEATS` | 사용 가능하나 공개해야 할 한계가 결과 해석을 바꾼다 |
| `DATA_BUILD_REQUIRED` | 소스 접근은 확인됐거나 기존 키로 가능하지만 수집·파생이 없다 |
| `SOURCE_BLOCKED` | 소스가 거부·유료·이용권 미확인 |
| `PIT_UNSAFE` | 값은 있으나 당시 공개본(빈티지)을 재구성할 수 없다 |
| `GOVERNANCE_CLOSED` | 데이터와 무관하게 기존 결정이 해당 역사 사용을 닫았다 |
| `NOT_FEASIBLE` | 이 저장소에서 합리적 비용으로 얻을 경로가 없다 |

## 1. 원천 데이터 매트릭스

| # | 데이터 | 한국 | 미국 | 근거 문서 | 이 프로그램의 사용 |
|---|---|---|---|---|---|
| 1 | 구성종목 일간 가격·거래량 | `READY` PIT Top120 2013~2026, 260개 증권. 거래대금은 종가×거래량 대용치 | `READY_WITH_CAVEATS` S&P 500 생존자 패널 615개, 거래 종료 패널 0개, PARA 신원 문제 | `kr-alpha-atlas-phase-b-readiness-ko.md`, `us-factor-research-reboot-v1-ko.md`, `us-decision-pilot-v1-ko.md` | Study A 특징·라벨 |
| 2 | 벤치마크 총수익 | `READY_WITH_CAVEATS` 069500.KS(등록 총배당 정의 대조 VERIFIED, replay-v16 레시피는 연 +1.11~+4.51%p 과대) | `READY_WITH_CAVEATS` SPY 내부 재구성 총수익(외부 대조 미완료) | `kr-alpha-research-final-development-assessment.md`, `weekly-passive-first-v1.md` | 모든 Study의 기준 |
| 3 | 장기 지수(1990~) | `READY` FDR_KS200 가격지수 1990~(봉인 해부 v2 원천) | `DATA_BUILD_REQUIRED` ^GSPC 가격지수·SPY 1993~ 장기 일간 스냅샷 없음(벤치마크 원장은 리플레이 기간만) | `kr-market-risk-anatomy-v2-final-result.md` | Study C1 |
| 4 | PIT 지수 구성 | `READY` KRX 월간 스냅샷 | `READY_WITH_CAVEATS` Git 스냅샷 관측일 기준, 경과일 중앙 54일·최대 767일, CIK는 2023-04 이후만 | 미국 재정비 §4 | 분모 정의 |
| 5 | 상장폐지·종결 대가 | `SOURCE_BLOCKED`(사실상) 22개 종결 증권 종결 대가 미해결 → 라벨 보류(v4 대칭 규칙) | `SOURCE_BLOCKED` 퇴출 324개 중 212개 무가격, 데이터셋 관문 `NOT_ADMITTED` | `us-departed-dataset-admission-audit-v1.json`, AGENTS v2.31 | 좌측 꼬리 한계, 두 독해 경계 |
| 6 | 분기 재무 PIT | `READY_WITH_CAVEATS` DART 2015~, 접수일+1일, 2016 성장 계열 구조적 공백, 금융업 매출·영업이익 결측 다수 | `READY_WITH_CAVEATS`(역사) Finnhub 2011~, `max(availableFrom, acceptedDate)`+1일 · `SOURCE_BLOCKED`(전향) 2026-10-07 이후 재무상태표 누락 | Phase B 보고, 미국 파일럿 감사 B | Study A 변곡점 |
| 7 | 주식수·시가총액 | `READY_WITH_CAVEATS` DART 주식수(분기 누락 시 이전값 이월 표기) | `SOURCE_BLOCKED` 검증된 기말 주식수는 SEC 필요(403). 가중평균만 | AGENTS PIT v2.9, 미국 인벤토리 E06 | 규모 매칭(US는 거래대금 대용) |
| 8 | 실적 발표 시각 | `DATA_BUILD_REQUIRED` DART `list.json` 영업(잠정)실적 공시 접수 시각. 본문 구조화 필드는 미확인 | `SOURCE_BLOCKED` 8-K 차단. 10-Q `acceptedDate`는 발표보다 늦음 | 미국 인벤토리 G03, DART 엔드포인트 기록 v2.28 | 방법론 C(후보) |
| 9 | 애널리스트 컨센서스·수정 | `SOURCE_BLOCKED` FnGuide 이용약관 | `SOURCE_BLOCKED` Finnhub 역사 추정치 유료 | 미국 인벤토리 G01/G02, AGENTS v2.23 | 사용 안 함 |
| 10 | 산업 분류 | `READY_WITH_CAVEATS` KRX 산업 소속 재구성 v4 | `READY_WITH_CAVEATS` GICS 섹터 11개만(하위산업 없음) | `kr-industry-membership-foundation-v4.md` | Study A 매칭·D 가설 |
| 11 | 공급망 연결 | `NOT_FEASIBLE` | `SOURCE_BLOCKED` SEC 고객 공시 | — | 사용 안 함 |
| 12 | 투자자 수급·공매도 | `SOURCE_BLOCKED` KRX `LOGOUT` 거부 | `SOURCE_BLOCKED` 13F/Form 4 SEC 차단 | AGENTS v2.25 | 사용 안 함 |
| 13 | 5% 대량보유 | `DATA_BUILD_REQUIRED` 2024-09-24부터 전향만 | `SOURCE_BLOCKED` | AGENTS v2.23 | 사용 안 함 |
| 14 | 시장 관측 금리·변동성(VIXCLS, DGS10, DGS3MO, DGS2, DTB3) | `READY`(미국 시계열을 KR 층 입력으로 사용, FRED 4일 지연 규칙) | `READY` | `kr-market-risk-model-v1-design.md` §3 | Study B·C |
| 15 | 신용 스프레드 | ICE HY/IG(FRED)는 2023-10 이후만 유효 → `SOURCE_BLOCKED`(역사) | 같음. 대안 Moody's BAA/AAA 수익률(시장 관측)은 `DATA_BUILD_REQUIRED` | KR 시장위험 설계 §3 | Study B 보조 |
| 16 | 실질 거시(물가·생산·고용) | `PIT_UNSAFE` ECOS 빈티지 없음. 지금부터 자체 빈티지 기록은 가능 | `DATA_BUILD_REQUIRED` 28열 중 18열 ALFRED 빈티지 존재, 10열 없음(`PIT_UNSAFE`), `macroVintageSeries` 비어 있음 | AGENTS v2.9 거시 빈티지, `config.json` | Study B 거시 팔(미국만) |
| 17 | 환율 | `READY_WITH_CAVEATS` DEXKOUS는 뉴욕 정오 → 같은 날 KRX 종가 회귀에 부적합, 주간 지연 사용만 | — | AGENTS v2.23 | Study B 보조 |
| 18 | 현금 수익 | `READY_WITH_CAVEATS` BOK 기준금리 대용(투자 가능 수익 아님), CD91 미등록 | `READY` DTB3(시장 관측, 비개정) | AGENTS v2.45 | Study C 현금 자산 |
| 19 | 거래비용 | `READY` `benchmark_alpha.REALISTIC_COSTS` 수수료 1.5bp·스프레드 8bp·연도별 거래세(2026 20bp). 국내 주식형 ETF 거래세 면제 | `READY` 수수료 5bp·스프레드 6bp·매도 0.30bp | `pipeline/benchmark_alpha.py` | 모든 Study |
| 20 | 전향 일간 가격 원장 | `READY` 주간 운영 파이프라인·`prospective_receipt_core` | `SOURCE_BLOCKED` 소유자 승인·이용권 미확인으로 영속 수집 비활성 | `us-persistent-daily-collection-v1.md` | Study A 전향 기록 |

## 2. 추론 보정 기하 (데이터만큼 중요한 제약)

| 지역·지평 | 상태 | 근거 |
|---|---|---|
| KR H21, H126 | `READY` 달력시간 SN 구간 보정 완료(v4 PASS 22 / INCONCLUSIVE 2, v5 정밀 재현 run `36499870415` PASS 24/24 — Actions 기록 인용) | AGENTS v2.37–v2.38, `alpha-opportunity-model-v5-preregistration.md` |
| KR H63, H252 | **미보정** — Phase C에서도 기술통계 | AGENTS v2.55 |
| US H63 | `READY`(P3 보정, 상단 기하 331–371 종목/날짜 미보정) | 미국 재정비 §9 |
| US H126, H252 | **미보정** | 같음 |

**결과:** 사용자 목표(6~12개월)와 정확히 맞는 H252는 두 지역 모두 추론 구간의 포함확률이 검증되지 않았다. 결과를 열람하기 전에 합성 데이터만으로 보정해야 하며(핸드오프 WP1), 실패하면 H252는 기술통계로 남는다.

## 3. Study별 데이터 현실성 요약

| Study·팔 | 한국 | 미국 |
|---|---|---|
| A 역사 검정 | `GOVERNANCE_CLOSED` Phase D가 동일 정보 집합의 KR 역사 탐색을 종료. 새 정보축(잠정실적 시각) 없이 재개 불가 | `READY_WITH_CAVEATS` 생존 조건부 개발 증거만. 좌측 꼬리 절단(212 무가격), 2013년 회계 군 대부분 공백 |
| A 전향 기록 | `READY` (주간 파이프라인 + 영수증 코어) | `SOURCE_BLOCKED` 일간 가격 영속 수집과 재무상태표 소스 해결 전 불가 |
| B 시장 관측 상태 | `READY` | `READY` |
| B 진짜 거시 | `PIT_UNSAFE` → **KR 경기 국면 주장 금지** | `DATA_BUILD_REQUIRED` ALFRED 빈티지 18열 측정 후 선택 |
| B 신호×상태 추론 | 상태별 비중첩 블록 부족 → 기술통계 | 같음 |
| C 지수 노출층 | 이미 봉인(`kr-market-risk-model-v1`, C0 유지) — 재실행 금지 | `DATA_BUILD_REQUIRED`(경미) ^GSPC·SPY·FRED 장기 스냅샷만 있으면 `READY` |
| C 종목 책 노출층 | Study A 후보 없음 → 대기 | 같음 |

## 4. 결측이 무작위가 아니라는 점

- **좌측 꼬리 결측.** 미국 무가격 퇴출 신원은 2013년 구성원-일의 30.3%에서 2026년 0.54%로 줄어든다. 결측이 오래된 해와 퇴출 종목에 몰려 있어 "대형손실" 기저율과 승자 대조군 모두 편향된다. 모든 1차 통계량은 두 독해(미해결 제외 / 최악 그럴듯한 값 배정)로 보고하고 부호가 같을 때만 주장한다.
- **재무 결측.** KR 금융업(구성원-일의 약 20%)은 매출·영업이익 정의가 다르고 대부분 없다. 변곡점 사건은 비금융 종목에만 정의하고, 금융업은 분모에서 `DEFINITIONALLY_EXCLUDED`로 별도 집계한다(0으로 채우지 않음).
- **미국 표본 시작 문제.** #245 파일럿은 CIK 관문 때문에 2013~2022가 비었다(주간 날짜 75.38% 미측정). replay-v16 미국 재무는 2013년부터 있으나 신원 검증 수준이 다르다. Study A-US는 어느 신원 규칙을 쓸지 사전 고정해야 하며(핸드오프 WP2), 그 결정은 커버리지만 보고 결과를 보지 않는다.
