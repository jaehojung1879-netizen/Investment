# A1/B1 역사 outcome 실행 하네스 — 승인 직전 단계

**상태: `PREPARED_BLOCKED_BY_SOURCE`.**
- 역사 가격·수익률·라벨은 0회 읽었다. 실행 승인이 없고 필수 원천 8개 중 0개가 admission됐다.
- 그래서 경제성 숫자는 모두 `NOT_EXECUTED` 또는 `SOURCE_BLOCKED`다.
- 검증된 알파: **KR 0 / US 0 (변동 없음)**.
- 작성자 자체 검증(`AUTHOR_VALIDATION_ONLY`)일 뿐 비작성자 독립 승인이 아니다.

이 하네스는 등록된 `kr-corporate-information-events-v1`(전향 기록 범위로 등록됨)의 **역사 1회 실행**에 쓰일 코드다. Owner 계약(Issue #292 comment 6671600416, C0~D)을 그대로 구현했고, 등록 사양이 고정한 23개 코드·10개 입력은 바이트 그대로다(테스트로 확인). Codex 원천 레인(가격·배당·기업행동)과 #317 현금·세금 adapter는 만들지 않고, 받아들일 **입력 계약**만 정의했다.

## 1. 무엇이 실행되는가 (승인 시)

| 구성 | 파일 | 등록 계약 대응 |
|---|---|---|
| 자금 일치 사전 β 연구 책 | `engine.py` | 활성 사건마다 동일 목표자본. 슬롯 = q 주식 + (1−q) 현금, 대조 = qβ ETF(069500) + (1−qβ) 현금, q=1/max(1,β). 진입·만기 날에만 재조정하고 그 외에는 drift한다. 사건이 없으면 양쪽 모두 ETF 100% |
| β | `engine.estimate_beta` | 신호 세션까지 252개 일 총수익, 공동 200쌍 이상. 음수·추정 불가 β는 투자 대상에서 제외하고 집계 |
| 비용 | `contract.COSTS` | `pipeline/benchmark_alpha.py` KR 일자별 거래세(30→25→23→20→18→15→20bp), 수수료 1.5bp, half spread 4bp. ETF 매도세 0. 1x/2x/3x. 실제 체결이 없으므로 `MODEL_COST_NO_REAL_FILLS` |
| 종결 | `engine.simulate` | 보유 종목의 가격이 없고 인용된 종결대가도 없으면 경로 미완료 → `SOURCE_BLOCKED`. 0·최종가로 채우지 않는다 |
| 추론 | `inference.py` | 동기화 이동블록 bootstrap(H126 252 / H252 504, B=9999, seed 319320), basic CI, 양측 p. Bartlett HAC lag 125/251. 블록 민감도 126·504 / 252·756 |
| 다중검정 | `study.py` | Holm 3슬롯(A1, B1, H3=p 1), 동시 98.333% 구간 |
| 판정 | `decision.py` | SOURCE_BLOCKED → REJECT_ECONOMIC_EFFECT(동시 상한 < 3pp) / FAIL_COST_ROBUSTNESS(2x 점추정 ≤ 0) → DEVELOPMENT_SUPPORT(모든 관문) → UNCERTAIN. 측정 못 한 점검은 통과할 수 없다 |
| 국면·산업·매칭 | `study.py` | Value-up 전/후, 2025~26 제외, 최대 PIT 산업 제외(사전 고정: A1 `FINANCIALS`, B1 `CAPITAL_GOODS_DEFENSE`), 3-peer 매칭(B1은 산업 일치 매칭 필수) |
| 분해 | `study.py` | ETF 단순 초과 = 선택(책−대조) + 노출(대조−ETF). 사건 단위 H 보유 차이와 발행사×진입주 two-way 군집 SE |
| A2 | `study.py` | 비소각 취득·신탁 책과 A1−A2 차이. 기술 통계일 뿐 판정에 쓰지 않는다 |

결정 전에 공개할 엔지니어링 선택 11개는 패킷의 `engineeringChoicesForOwnerReview`에 있다. 결과로 고른 것은 없다(결과가 없다).

## 2. A. 데이터 — 최종 실증 적격 사건 (outcome-free, `execution-readiness-v1.json`)

| 집합 | 독립 사건 | 발행사 | 원장 끝(2026-10-30)까지 성숙 | 성숙 중 원장 공백 세션 포함 | 실제 종결(대가 미해결) | Value-up 전/후 | 2025~26 진입 |
|---|---:|---:|---:|---:|---:|---:|---:|
| A1 H126 | 323 | 145 | **265** | 12 | 5 | 121 / 202 | 169 |
| A1 H252 | 252 | 145 | 164 | 2 | 4 | 99 / 153 | 128 |
| B1 H126 | 464 | 117 | **441** | 7 | 2 | 337 / 127 | 93 |
| B1 H252 | 346 | 117 | 312 | 8 | 3 | 251 / 95 | 66 |
| A2 H126 | 522 | 203 | 502 | 3 | 3 | 406 / 116 | 76 |

- 가격 존재(`price-admission-v1`): 전 기간 거래 A1 H126 238건, B1 H126 420건. 정지·공백은 각각 19건, 17건이다.
- **원장 공백 결함:** `ledger/prices/kr`에서 2026-09-15, 2026-09-16, 2026-10-01이 전 종목 누락돼 있다. 이 세션이 보유창에 걸린 성숙 사건은 A1 12건, B1 7건이다. 운영 가격 수집기를 보완하기 전에는 이 사건이 포함된 경로를 계산할 수 없다(경로 전체가 SOURCE_BLOCKED가 된다).
- **실제 검정 가능 기간:** A1 H126 2013-04-29 ~ 2026-10-27, 3,310세션 = 252세션 블록 **13.1개**. B1 H126 3,387세션 = **13.4개**. H252는 6.5~6.7개다. 독립 시간 블록이 13개 남짓이라는 점이 사건 수보다 더 큰 정보량 제약이다.

## 3. 새로 측정한 경제적 사실 (결과 전, 메타데이터만)

1. **A1은 금융업 집중이다.** PIT 산업 라벨이 있는 252건 중 90건(35.7%)이 `FINANCIALS`다. Value-up 이후로 좁히면 158건 중 62건(39%)이다. Value-up 이전에는 28건이었다. A1 역사 결과는 '소각 효과', 'Value-up 국면', '금융주 재평가'가 같은 시기에 겹친다. 그래서 금융업 제외 점검을 결과 전에 고정했다.
2. **B1은 방산·조선(자본재)과 건설·플랜트 집중이다.** 라벨이 있는 332건 중 `CAPITAL_GOODS_DEFENSE` 116건, `CONSTRUCTION_ENGINEERING` 78건으로 합계 58%다. B1은 A1과 반대로 Value-up 이전 사건이 337/464건이다. 상위 10개 발행사가 27.8%이고, 한 발행사의 최대 사건 수는 16건이다.
3. **산업 라벨 공백:** v4 PIT 산업 라벨은 Top120 유니버스만 다룬다. 그래서 B1 132건(28%), A1 71건(22%)에 라벨이 없다. 등록 계약상 B1의 최종 지지는 산업 일치 매칭이 필요하므로, 이 공백이 해소되기 전 B1은 `DEVELOPMENT_SUPPORT`에 도달할 수 없다.
4. **배당 기준이 A1 판정을 좌우한다.** 성숙한 A1 H126 265건 중 148건은 보유창 안에 배당기준일이 있다. 이 사건들은 배당락일 규칙이 필요하다(발행사가 규칙을 직접 진술한 경우는 20건뿐). B1은 441건 중 110건이다. 소각 기업은 대체로 고배당 금융주라서, 가격수익만으로 A1을 평가하면 ETF(총수익) 대비 체계적으로 불리해진다. 그러니 가격수익 대체는 금지다.
5. **#320의 배당락일 후보 규칙은 비거래일 기준일에서 1세션 늦다.**
   - `dividends.ex_date_candidate`는 기준일보다 '엄격히 이전'인 세션으로 계산한다. 그래서 12-31처럼 기준일이 거래일이 아니면 배당락일을 하루 늦게 잡는다.
   - 공개 보도로 확인했다. 2023년은 폐장 12-28, 배당락 12-27이다([경향](https://www.khan.co.kr/article/202312141411001), [뉴시스](https://www.newsis.com/view/NISX20231226_0002570439)). 2022년은 폐장 12-29, 배당락 12-28이다([파이낸셜뉴스](https://www.fnnews.com/news/202212151630345260)). #320 규칙은 각각 12-28, 12-29를 준다.
   - 영향: 공시 진술 등급 593건 중 397건이 1세션 늦다(기준일이 거래일인 196건은 일치).
   - 고정 XKRX 달력에서 위 보도 날짜를 재현하는 시장 규칙 후보를 `ex_date.py`에 추가했다. 규칙: 배당락일 = '기준일 이전 마지막 세션'의 직전 세션. **봉인하지 않았다.** 공식 KRX/KSD 원문으로 봉인하는 것은 Owner 결정이다.
   - #320 데이터 파일은 그 PR의 receipt가 고정하므로 여기서 다시 쓰지 않았다. 수정은 #320 레인 몫이다. 기존 테스트 `test_ex_date_candidate_only_with_stated_rule_and_never_resolved`가 이 결함(2012-12-31 → 12-28)을 그대로 기대값으로 담고 있다.
   - **이 규칙을 봉인하면:** 성숙한 A1 H126 265건 중 261건(배당 없음 96건 + 배당락일·주당배당금 모두 확정 165건)의 배당 기준이 결정된다. B1 H126은 441건 중 440건이다. 남는 것은 주당배당금 미파싱 A1 4건, B1 1건이다. 단, '창 안에 배당락 없음'은 해당 발행사의 배당결정 공시가 수집된 범위 안에서의 사실이다.
6. **β 대조의 drift:** 합성 무알파·무잡음 시장에서도 재조정 사이에 주식 다리와 β 일치 ETF 다리가 서로 다르게 drift한다. 이 때문에 일별 차이는 최대 약 1.4e-4, δ126은 2e-3 미만이 생긴다(2차 항). 계약이 말한 '사후 노출 차이'의 실제 크기이며 결과에서 따로 보고한다.

## 4. B. 경제성 — 이번에 계산하지 않은 값

| 항목 | 상태 |
|---|---|
| ETF 대비 초과수익 (H126/H252) | NOT_EXECUTED (승인 없음) · SOURCE_BLOCKED (주식 총수익, 069500 정합성) |
| 거래비용 후 1x/2x/3x | NOT_EXECUTED · SOURCE_BLOCKED |
| β·현금 자금 일치 선택 항 | NOT_EXECUTED · SOURCE_BLOCKED (투자 가능 원화 현금) |
| 산업 효과 제거 / 산업 일치 매칭 | NOT_EXECUTED · SOURCE_BLOCKED (Top120 밖 PIT 산업) |
| 규모·가치·모멘텀 매칭 | NOT_EXECUTED · SOURCE_BLOCKED (PIT B/M) |
| 신뢰구간·유효 표본·검정력 | MDE만 계산함(σ 미측정 조건부). 성숙 N, σ=20%, D=2 기준 A1 H126 5.62pp, B1 H126 4.36pp. 둘 다 POWER_MARGINAL(MEE 3pp) |

## 5. C. 투자전략

- **검증된 신호가 있는가:** 아직 판별 불가(`NOT_EXECUTED`). 실패도 성공도 아니다.
- **운영 가능 여부:** 판단 대상이 아니다. 0~5종목 구현은 `DEVELOPMENT_SUPPORT` 이후에 별도 사전등록이 필요하다. 하네스는 `portfolioStep: NOT_REACHED`를 출력한다. 적격 사건이 없으면 ETF 100%이고, 종목 수 고정 규칙은 없다.
- **사전 경고:** 검정력이 MARGINAL이고 시간 블록이 13개라 가장 그럴듯한 결과는 `UNCERTAIN`이다. 효과가 있더라도 DEVELOPMENT_SUPPORT에 이르려면 δ126 하한 > 0이면서 점추정 ≥ 3pp여야 한다.
- **다음 정보축:** 이 결과와 무관하게 전향 영수증(2026-11-09 시작)이 유일하게 오염되지 않은 증거다. 역사 결과가 UNCERTAIN이면 같은 역사로 재튜닝하지 않는다.

## 6. D. 승인 필요 사항 (정확 해시)

- 패킷: `historical-execution-packet-v1.json`. SHA256은 `historical-execution-packet-v1.sha256`에 있다.
- 등록 사양: `kr-corporate-information-events-v1-candidate.json`, SHA256 `1692b5b3131a76ab6dd8a5198ef0fd262fffa4ec7cf0925444cf344aacbd61d4`.
- 승인 문구(패킷 SHA 포함): `APPROVE KR_PHASE_D_NEW_AXIS_EXCEPTION kr-corporate-information-events-v1 <registeredSpecSha256> PACKET <packetSha256>`.

**지금은 승인하지 마라.** 아래 4개 사전조건이 충족되지 않아 실행은 어차피 거부된다.

1. 원천 8개 admission
   - 주식 총수익: 배당락일 규칙 봉인
   - 069500 총수익 정합성
   - 투자 가능 원화 현금
   - 종결대가: A1 5건, B1 2건
   - 거래 가능성
   - Top300 PIT 산업
   - 매칭 특성(PIT B/M)
   - 계좌·세금 계약

   각 원천은 별도 원천 PR과 비작성자 감사를 거쳐야 한다. 가격 원장의 2026-09/10 공백 세 세션도 보완돼야 한다.
2. 이 하네스의 정확 해시에 대한 비작성자 독립 리뷰.
3. merged main에서 durable lock ref를 갖는 workflow로만 실행한다. 이 workflow는 원천 PR과 함께 추가한다.
4. 위 문구로 패킷 SHA를 고정한 Owner 승인 파일.

Owner가 지금 내릴 수 있는 결정(실행 승인이 아닌 원천 결정):

- (a) 배당락일 규칙: `ex_date.py`의 시장 규칙(배당락일 = 기준일 이전 마지막 세션의 직전 세션)을 공식 KRX/KSD 원문으로 봉인할지. 공시 진술 등급(#320 후보)은 비거래일 기준일에서 틀리므로 그대로 받아들이면 안 된다.
- (b) Top120 밖 PIT 산업 원천의 수집 범위.
- (c) 계좌·세금 계약 1개 고정.

## 7. 재현

```bash
python -m research.corporate_event_outcome_v1.readiness   # outcome-free, 바이트 고정
python -m research.corporate_event_outcome_v1.run          # 패킷·등록·코드 해시 검증
python -m pytest -q tests/test_corporate_event_historical_outcome.py
```

`--execute`는 승인 파일·원천 admission·main workflow 조건을 시장 파일을 읽기 전에 검사하고, 하나라도 빠지면 종료 코드 2로 거부한다.
