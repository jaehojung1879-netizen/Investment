# Market Structure Discovery S2 · 제도적 제약과 자본 흐름 — 1차 보고

상태: `SOURCE_AND_DESIGN_ONLY` · 측정일 2026-11-26 (UTC) · 기준 main `3150c700`

이 작업은 미래 수익률·초과수익·IC·NAV를 한 번도 계산하지 않았다. 가격에서 유도한 값은 사건 20세션 **이전** 60세션의 중앙 거래대금(종가 × 거래량) 하나뿐이며, 거래 압력의 분모로만 쓴다.

## 1. 결론

- **제도적 강제 거래 사건 원장을 실제 원천으로 구축했다.** 미국 S&P 500 변경(발표 ET 시각·효력일)은 2012-07~2026-11에서 편입 233·편출 207건이다. 한국 KOSDAQ 150은 정기변경 5회(편입 64·편출 63)다. 한국 신용 반대매매 급증의 독립 국면은 1998~2026에서 46건이다.
- **KOSPI 200 공식 구성 이력은 이 저장소에 처음 생겼지만 정기변경 구간은 0회 확보다.** KODEX 200 PDF API(기준일별 과거 응답)를 찾았다. 그러나 약 550회 호출 뒤 발행사가 Cloudflare 챌린지를 걸었고, 우회하지 않고 중단했다. 남은 작업은 54회 호출이다.
- **PASS_TO_PREREG 0건, 사전등록 초안 1건(A1).** 6~12개월 지평에서 검정력이 충분한 가설은 없다. 지수 변경의 H126 MDE는 3.7~9.7%p로, 선행연구가 보고하는 현재 효과(수 % 이하, 미국은 거의 0)보다 크다.
- **판정: INCONCLUSIVE(원천 부분 확보) + A1 원천 보완 후 진행.** S2의 현실적 용도는 독립 알파보다 기존 중장기 후보의 **진입·청산 시점 보조**다.

## 2. 근거

### 2.1 기존 연구와의 차별성 ([Stage 0](STAGE-0-LITERATURE-ko.md))

- 저장소는 지수 변경·펀드 흐름·반대매매를 한 번도 측정하지 않았다(코드·문서 검색 결과 S2 외 0건).
- #347·#348은 기관의 **선택 능력**을 봤고, S2는 규칙이 강제한 **비정보 거래**를 본다.
- 재실험하지 않은 것: 기관 보유 추종, 외국인·기관 순매수 모멘텀(원천 차단), 내부자 매수(A), 시장 낙폭 규칙(A).
- 문헌상 미국 편입 효과는 소멸했다(Greenwood & Sammon 2025). 그래서 미국은 대조 시장으로만 쓴다.

### 2.2 실제 확보 원천 ([source-manifest.json](results/source-manifest.json))

| 원천 | 결과 | 규모·해시 |
|---|---|---|
| KRX 정보데이터시스템(투자자별·지수구성·공매도) | **차단 유지**. 세션·Referer 포함 3건 모두 `HTTP 400 LOGOUT`. 로그인 우회 안 함 | 응답 6바이트 sha256 `377b375a…` |
| KRX 홈페이지·KIND | 차단(AccessDenied, 403) | — |
| KODEX 200 / KOSDAQ 150 PDF | 기준일별 과거 응답 확인. 2010~2012는 135~137종목 부분복제, 완전복제는 2018-01-12부터 확인. 이후 스로틀 | `data/kodex200_pdf.jsonl` 응답 247건(고유 기준일 242), `kosdaq150_pdf.jsonl` 응답 221건(고유 기준일 214), 실패 기록 10·11건. 응답별 sha256 보존 |
| S&P DJI 보도자료(PR Newswire) | 수집 | 목록 1,333건, 본문 303건 |
| Wikipedia S&P 500 구성종목 | 교차검증 | sha256 `c2d80d1e…` |
| KOFIA FreeSIS 신용공여 잔고·증시자금 | 수집(시장 전체) | 7,246행 / 7,245행, 1998~2026-11-25 |
| Fed Z.1 F.223 | 수집(분기, 개정 이력 없음) | zip sha256 `b63af975…` |
| signal-history KRX 일별(KOSPI) | 읽기 전용, 거래대금 분모만 | `394fc9f6` |
| SEC·FINRA | 차단(403) | — |
| 국민연금 | 현재 스냅샷만, 접속 불안정 | — |

### 2.3 제도적 거래 사건 원장 ([institutional-event-ledger.json](results/institutional-event-ledger.json), [요약](results/ledger-summary.json))

| 원장 | 사건 | 독립 날짜 | 품질 확인 |
|---|---|---|---|
| S&P 500 | 편입 233, 편출 207. 분기 리밸런스 편입 60. 발표→효력일 중앙 7일(0~18) | 효력일 190 | 위키 현 구성종목 대비 70.6%. 2022~2026 ≥92%, 2012~2021 약 50% |
| KOSDAQ 150 | 정기 편입 64·편출 63, 수시 편입 13·편출 10, 기존 종목 비중 조정 45(정기) | 정기변경 5회 | PDF 일시 제외 13행 분리. 관측 공백 3구간 명시 |
| KOSPI 200 | 수시 편입 2·편출 4(셀트리온 이전상장 2018-03, LG에너지솔루션 2022) | 4 | PDF 일시 제외 8행 분리. 정기변경 0회. 관측 공백 2018-06~2022-01 |
| 반대매매 급증 | 99백분위 초과 135세션 → 독립 국면 46 | 46 | 시장 전체 수준만 |

KOSPI 200 사전 압력(편입 비중 × 1조 원 / 평상시 거래대금): 평가 가능 4건, 중앙 0.17일. 추종 자산이 수십조 원이면 평상시 거래대금 수일 분이다. 추종 자산 규모는 가정이며 관측값이 아니다.

### 2.4 구조적 제약 지도 ([CONSTRAINT-MAP-ko.md](CONSTRAINT-MAP-ko.md))

- 거래가 강제되고, 규모를 사전에 알 수 있고, 원천이 있는 제약은 **지수 추종 자금**과 **반대매매(시장 수준)** 둘뿐이다.
- 연기금 리밸런싱은 규칙은 공개돼 있으나 실제 매매가 비공개다. 펀드 환매·ETF 설정환매·종목별 신용·대차는 한국에서 원천이 차단돼 있다.

### 2.5 가설별 판정 ([HYPOTHESES-ko.md](HYPOTHESES-ko.md), [power-mde.json](results/power-mde.json))

| ID | 내용 | 독립 N | MDE H21 / H126 | 판정 |
|---|---|---|---|---|
| A1 | KOSPI 200 정기변경 압력·반전 | 27(설계) | 2.3%p / 6.4%p | 원천 보완 후 사전등록 초안 |
| A2 | KOSDAQ 150 정기변경 | 5(관측) / 22(설계) | 7.0 / 20.4%p (관측) | SOURCE_ONLY |
| A3 | S&P 500 | 190 | 1.3 / 3.7%p | 대조 시장 전용 |
| A4 | 특례편입 | 15~25(추정) | ≥6%p | 서술·전향 |
| B1 | 미국 펀드 흐름 유발 거래 반전 | 약 14 | — / 4.5%p | 원천 재접근(GCAP) 필요 |
| C1 | 국민연금 비중 이탈 | 10 미만 | — / 약 15%p | 서술·전향 |
| D1 | 반대매매 급증 후 반등 | 46 | 2.9 / 7.0%p | 서술·조건부(시장위험 A와 독립성 검사 선행) |
| B2·D2·E2 | ETF 흐름·종목별 신용·MSCI | — | — | BLOCKED / SOURCE_ONLY |
| D3·F1 | 레버리지 ETF·월말 흐름 | — | H1~H5 | REJECT_HORIZON |

σ·ρ는 가정이다. 수익률을 읽어 정하지 않았다.

### 2.6 검증 가능한 경제적 관계와 예상 전달 시차

| 관계 | 예상 시차 | 측정 가능 여부 |
|---|---|---|
| 편입 비중 × 추종 자산 → 효력일 종가 수요 | 발표(미국 중앙 7일 전, 한국 미확보) → 효력일 종가 | 미국 가능, 한국은 효력일만 |
| 효력일 이후 유동성 공급자 재고 정리 → 반전 | T+1 ~ T+21 | A1 사전등록 대상 |
| 담보 부족 → 반대매매 | 하락 당일 → 다음 영업일 개장 | KOFIA 일별(시장 전체) |
| 국민연금 비중 이탈 → 매도 | 월말·연말, 정책 변경 | 실제 거래 미관측 |
| 펀드 순유출 → 보유 종목 매도 → 6~18개월 회복 | 분기 | GCAP N-PORT 재접근 시 |

## 3. 실무 적용

- **현재 투자 판단에는 쓰지 않는다.** 증거 등급은 원천/설계이며 신규 투자 결과는 없다.
- KOSPI 200 PDF 54회가 확보되면 A1을 등록하고, Owner 승인 후 1회 실행한다. 결과가 지지되더라도 노출된 역사이므로 2026-12 정기변경부터 전향 영수증으로 확인한다.
- 실행 가능한 용도: 기존 KR 0~5종목 후보가 정기변경 편입 예정이면 효력일 종가 이후로 매수를 미루는 진입 시점 규칙(사전등록 대상, 미검증).

## 4. S1(실물 네트워크)과의 결합 가능성

| 결합 | 내용 | 조건 |
|---|---|---|
| 충격 분해 | S2의 비정보 가격 충격(지수 변경·반대매매)을 도구로 써서, S1이 보는 공급망 동조화가 펀더멘털 전달인지 공통 보유 흐름(Anton-Polk)인지 구분 | 같은 사건 달력 공유, 사건 중복 계산 금지 |
| 할인 매수 | S1 펀더멘털 개선 신호가 있는데 S2 강제 매도로 가격이 눌린 종목 | 양쪽 원천의 PIT 시각 정렬 |
| 사건 배제 | S1 실증에서 지수 효력일·반대매매 국면을 통제 변수로 제공 | 이 원장의 효력일·국면 날짜 사용 |

공용 원천 구축이 필요하면 #292에서 작업권을 조율한다. 이번 작업은 S1 경로를 수정하지 않았다.

## 5. 인계(#292 형식)

- 이전 약속: 신규 정보축의 원천·PIT·독립 사건 밀도 확인, 성과 미조회(#371 G0 규칙).
- 검증된 변화: 제도적 사건 원장 4종 신규(위 §2.3). KRX 투자자별 차단 재확인. KOSPI 200 공식 구성 경로 발견(부분 확보).
- 경제적 함의: 6~12개월 독립 알파 후보는 현재 원천·표본으로 검정력이 부족하다. 단기 진입 시점 보조는 검정 가능하다.
- 남은 차단: ① KODEX 200 정기변경 PDF 54회(발행사 스로틀) ② KRX 정기변경 공지(효력일·발표일) ③ GCAP N-PORT 재다운로드(B1) ④ KOSDAQ 거래대금(A2 분모).
- 판정: **INCONCLUSIVE · A1 KEEP(원천 보완 조건) · A3/D3/F1 REJECT(독립 가설) · 나머지 SOURCE_ONLY/BLOCKED.**
- 다음 최소 행동: 스로틀이 없는 환경(예: Owner PC)에서 `python research/market_structure_discovery_s2/collect_kodex_pdf.py 2ETF01 2013-01-01 2026-11-26 research/market_structure_discovery_s2/data/kodex200_pdf.jsonl review 30` 1회 실행 후 `build_ledgers.py` 재실행. 담당: Owner(실행) → 이 세션 계열(원장 재생성).

## 6. 재현

```bash
cd research/market_structure_discovery_s2
python collect_spdji_releases.py 20 data/spdji_listing_pages.jsonl data/spdji_releases.jsonl
python collect_spdji_bodies.py data/spdji_releases.jsonl data/spdji_bodies.jsonl
python parse_spdji.py data/spdji_bodies.jsonl results/sp500_change_events_raw.json
python collect_kofia_freesis.py STATSCU0100000070BO 19980101 20261126 data/kofia_credit_balance.json
python collect_kofia_freesis.py STATSCU0100000060BO 19980101 20261126 data/kofia_market_funds.json
python build_ledgers.py <signal-history checkout>/ledger/prices/kr
python crosscheck_sp500.py && python power_mde.py && python source_manifest.py
```

KOFIA 열 이름(TMPV2~9)은 FreeSIS 화면 배치를 기준으로 해석했다. 화면에서 직접 대조하지 않았으므로 사전등록 전에 확인한다(`DATA-NOTES-ko.md`).
