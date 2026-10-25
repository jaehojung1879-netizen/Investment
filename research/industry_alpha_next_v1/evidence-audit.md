# 데이터·증거 감사

감사 기준: main `b589d658eedd3c47f555df20db86f37792ee3358`(2026-10-24 UTC).
권위 순서는 정확한 봉인 결과/출처 → 후속 최종 판정과 병합 상태 → 설계 문서다.
초기 설계의 “아직 실행 안 함”, “benchmark unresolved”, “Draft” 문구를 현재
상태로 복사하지 않는다. 기존 결과를 읽고 SHA를 확인했으며 어떤 실험도 재실행하지 않았다.

## 기존 계층과 원천

[market-industry-stock foundation](../../docs/market-industry-stock-data-foundation-v1.md)은
시장(위험 예산), 산업(산업−시장), 종목(종목−산업)을 별도 질문으로 정의한다.
동일 구간 단순수익률의 차이는 정확히 더해지지만 베타 중립화나 인과 분해는 아니다.
산업 바스켓은 신호 시점 모집단/가중치를 동결하고 하나라도 종결 대가가 없으면
결과가 미해결이다. 후속 산업 연구도 이 구별을 유지한다.

`pipeline/sectors.py`의 정적/현재 Yahoo 분류와 ETF rotation은 역사 산업 소속의
근거가 아니다. KR은 strictly prior KRX Top120 스냅샷(260 ever-members) 범위이며
한국 전체 산업을 대표한다고 주장할 수 없다. US는 보존 S&P 500 스냅샷부터 감사한다.

## 분류 v1~v4: 읽은 결과와 한계

| 버전 | 측정한 사실 | 판정/해석 |
| --- | --- | --- |
| [v1](../../docs/kr-industry-membership-foundation-v1.md) | 413 DART receipt 수집, 엄격 증거 계약에 admitted 0, 73,200 name-date 분모 유지 | DATA_FOUNDATION_INSUFFICIENT; 당시 분류가 없었다는 뜻 아님 |
| [v2](../../docs/kr-industry-membership-foundation-v2.md) | 2,946 receipt, 79 관측/6증권, 2,876/73,200(3.93%); 종료 0/2,345 | DATA_FOUNDATION_INSUFFICIENT_V2; sparse last-known-public 상태 |
| [v3](../../docs/kr-industry-membership-foundation-v3.md) | 현재 앵커 232/260, 변경 공지 80/81, 분류 68,807(93.999%) | DATA_FOUNDATION_INSUFFICIENT_V3; no-change 추론 54,173, demonstrably public event 1,798 |
| [v4](../../docs/kr-industry-membership-foundation-v4.md) | 우선주 4개/949 name-date 추가, 분류 69,756/73,200(95.295%), UNKNOWN 3,444 | DATA_FOUNDATION_INSUFFICIENT_V4; 종료 22개 0/2,345, taxonomy selected=null |

v4의 14 경제 그룹 crosswalk는 존재하지만 398/610일에서 충분한 그룹(5명 이상)에
속한 classified 비율이 90% 미만(최저 78.8%)이다. “14개 산업으로 정식 적격성 통과”가
아니다. 분류 없음, 역사 분류를 추론함, 종결 주주 대가 미해결은 서로 다른 문제다.
압축된 v3/v4 audit 바이트를 독립적으로 읽어 위 숫자와 상태 분포를 확인했다.

## 이미 측정된 산업 결과: 봉인 결과만 인용

[산업 anatomy 봉인](../../docs/kr-industry-opportunity-anatomy-v1-result-seal.md),
[전체 보고서](../../docs/results/kr-industry-opportunity-anatomy-v1-report.md).
run 37182657697, SPENT. 결과 SHA
`71a960e3c19ce443d058508c4ec66576e3e5fcbd7a45dc851cf8b832bff62a08`를 확인했다.
원래 시장은 069500.KS, 수익은 **부분 분배 포함 조정 지수**이며 완전 주주 총수익이 아니다.

CAP_WEIGHTED H126의 기존 기술통계:

| 특징 | 평균 IC | 삼분위 차이 | 유효 IC 날짜 |
| --- | ---: | ---: | ---: |
| REL_MOM_126 | +0.066 | +5.4%p | 404 |
| BREADTH_ABOVE_MA_126 | +0.059 | +3.2%p | 405 |
| MEDIAN_ocfYieldProxy | +0.136 | +4.7%p | 337 |
| MEDIAN_netIncomeImprovementToAssets | −0.185 | −10.1%p | 248 |
| MEDIAN_bookToMarketProxy | −0.059 | −0.3%p | 434 |
| TOP1_CAP_SHARE | −0.054 | +1.3%p | 565 |

주간 관측은 중첩되며 다중검정 보정이 없다. IC와 삼분위 분모도 다르다.
FULL 산업 적격 5,818/8,540 industry-date, H126 target finite 5,644;
최대 구성원 제거 시 적격 4,586으로 줄어든다. 따라서 FULL과 제거 결과의 차이가
순수 대형주 효과라고 분리되지 않는다. REL_MOM_126은 largest-out IC +0.071,
spread +0.1%p(200/98일)이고 두 이름만 제거하면 +0.071/+5.4%p(404/294일)다.
**삼성·하이닉스 제외와 각 산업 최대종목 제외는 다른 질문**이며 같은 표본 검정이 필요하다.
CAP H252 상대 모멘텀 IC −0.010, OCF yield pre-2025 +0.197/후기 −0.149처럼
기간·국면 안정성도 확인되지 않았다. 이 숫자로 새로운 음의 특징을 선택하지 않는다.

[종목-within-industry 봉인](../../docs/kr-stock-within-industry-anatomy-v1-result-seal.md),
[보고서](../../docs/results/kr-stock-within-industry-anatomy-v1-report.md).
run 37196246044, SPENT. 결과 SHA
`3862c390a52f6f19abaa7849e41620858cd154735136647ee36c958624c2739f` 확인.
H126 within-rank vs stock−LOO-industry IC는 book-to-market +0.086,
earnings yield +0.073, relative126 +0.028, momentum121 +0.010이다.
이는 산업 내 기술적 연관성이고 산업 선택 모형의 추가 비용 차감 예측력 검정은 아니다.
봉인 stock−market A와 새 same-sample A′가 다르므로 A 대비 크기 비율을 독립성으로
해석할 수 없다. 금융업 배당·부분 분배, small peers, 종료 미분류 한계가 남는다.

## 결합 연구와 Atlas의 최종 판정

[결합 포트폴리오 후속 감사](../../docs/kr-integrated-alpha-portfolio-v1-postoutcome-concentration-audit.md)의
정식 판정은 INDUSTRY_LAYER_DEVELOPMENT_SUPPORTED,
NO_UNAMBIGUOUS_FINAL_ARCHITECTURE, MARKET_LAYER_PARETO_TRADE_OFF다.
후속 기술 감사에서 D는 2024년까지 A에 뒤졌고, gross 기여 98.2%가 2025/2026에,
59.5%가 전자·전기에 몰렸다. 두 초대형 종목 직접 기여는 9.2%; 두 종목 제외
민감도는 같은 산업의 다른 종목으로 이동했다. 당시 감사의 passive CAGR 20.24%는
미해결 benchmark 계열의 값이므로 새 연구의 검증된 성과 기준으로 재사용하지 않는다.
이 관측들은 선도주→후발주 **확산 인과/예측**의 측정이 아니다.

[Atlas 최종 Phase D](../../docs/kr-alpha-research-final-development-assessment.md):
38 후보, 73 feature/horizon, 30 가족 비교, 6 조건 가설, 574 fit;
34 NO_DEVELOPMENT_EVIDENCE, 4 BLOCKED, BY/Holm 통과 0, nominations=[]이다.
H126 B0 MSE .093059 vs B4 .093677은 예측오차이며 투자수익률이 아니다.
X3 산업 리더십×종목 강도 p=.4125/전체 BLOCKED는 동적 확산의 독립 검정이 아니다.
Level4 NOT_TRIGGERED이므로 비용 차감 성과를 0 또는 음의 실측으로 쓰지 않는다.
최종 기록의 benchmark는 RECONCILED_DEFINITION_COMPATIBLE/VERIFIED다.
초기 문서의 미검증 상태와 섞지 않으며, 개별 종목 배당 완전성까지 인증한 것도 아니다.

문서 제목의 Draft와 달리 **PR #217은 2026-10-10 병합**(merge `6a40238d`)됐다.
한국 역사 탐색 종료 결정은 유효하다. 이 PR은 그 결정을 수정하지 않는다.

## 최신 PR 격리와 미측정 항목

| PR | 감사 시 HEAD/상태 | 이 연구와의 경계 |
| --- | --- | --- |
| #286 | 4fcfaf6a / open Draft | 한국 장중·야간 종목 탐색, NO STABLE ADDED ALPHA; 정지/권리·거래세 감사 미해결; 전체 결과 재현 안 함 |
| #287 | e671104f / open Draft | US WID 자료 복구, 기본 preflight BLOCKED; 조건부 membershipIndustry는 PIT 인증 아님; execute 승인 아님 |
| #288 | e88624f8 / open | C1 US exact-byte 회수; 원본 수익 경로를 산업 연구에 사용하지 않음 |
| #289 | e0a88afd / open Draft | C1 비대칭 exit/reentry 설계; 산업 선택 가설과 별개 |
| #283 / #284 / #280 | open | 종목 수·거시·결합 준비 변경; 본 PR은 별도 경로만 추가 |

#286·#287 changed-file 전체 목록을 provenance에 보존했다. 본 PR의 새 경로와
교집합 0을 확인한다. 최신 main의 마지막 병합 #285는 Track B 전향 시장상태 기록이다.
그 상태 관측이 산업 성과를 검증한 것은 아니다. PR 상태는 감사 시점 스냅샷이다.

아직 측정되지 않은 것은 (1) 적격 PIT 산업 모집단의 진정한 총수익 기반 H126/H252
독립 예측력, (2) 동일 표본·집중도 통제 후 각 정보군의 추가 예측력,
(3) 당시 지정된 리더에서 후발주로의 시차 확산, (4) 동결된 국면 조건의 추가 효과,
(5) 동일 종목 모델 대비 비용 차감 우위, (6) 분류/기업행동 복구 전후 결과 왜곡 크기,
(7) 미국의 적격 산업/섹터 패널 검정이다. 원래 실험의 관측과 이 가설을 혼동하지 않는다.

감사 범위는 저장소 증거·계약·봉인 SHA·메타데이터다. 모든 원공시의 경제 의미나
Actions 원본 archive 전체, 외부 지급 내역을 이번 환경에서 새로 인증하지 않았다.

## 검토 범위와 남은 문제

**설계 공유는 한계 명시 조건부 가능(Share with caveats), 역사 결과 실행은 Needs revision.**
요청된 설계 산출물은 Complete, 원천 경제 적격성 검증은 Partial이다.
기존 원천·봉인·코드를 고치지 않았으며 새 설계와 메타데이터 감사만 추가했다.
분모는 다음 표에 정의한 감사 단위 수이며 검증 성공률이 아니다.

| Category | Observed defects | Assessment |
| --- | --- | --- |
| 연구 산출물의 완결성 | 0 / 5 | 예측 가설, 지역별 자료 계획, 기존/미측정 구별, 사전등록·합성 기준, 승인 조건 모두 문서화 |
| 분석 명료성 | 0 / 3 | marginal association / incremental prediction / net economics를 구분; 차단과 부정 판정도 분리 |
| 시각·상호작용 | N/A | 웹/대시보드가 아닌 저장소 연구 설계 |

| Category | Observed defects | Assessment |
| --- | --- | --- |
| 원천 적격성 | 2 / 7 | 7개 증거 사슬(계층, KR분류, US분류, 산업anatomy, 종목anatomy, 결합감사, Atlas) 중 KR/US 분류는 strict 실행 차단; 나머지도 독립 확증 아님 |
| 값·계산 검증 | 0 / 2 | 두 봉인 결과 SHA를 독립 대조; 새 수익 통계 재계산은 금지했고 수행 안 함 |
| 데이터 품질 | 2 / 2 | KR 종료 미분류·재구성, US 분류수준 혼합·identity gap 미해결; 복구 계획은 data-eligibility 참조 |
| 결론 지지 | 0 / 3 | 새 산업모델의 독립 예측력·확산·비용차감 우위는 모두 미검증이라고 유지 |
| 차트 내 일치·source modal | N/A | 해당 시각화 없음 |

우선 문제와 제안: (1) KR strict PIT와 terminal/distribution 복구를 별도 data-only
작업으로 수행, (2) US 2023 snapshot의 분류 수준·공개 시각·share-class 연결을
versioned source로 복구, (3) 같은 표본·비용·순차 가설을 exact-hash 등록 후 독립
감사한다. 세 항목 모두 이 감사의 결과로 자동 실행하거나 기존 연구를 수정하지 않는다.
