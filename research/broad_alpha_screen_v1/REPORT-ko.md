# Broad Alpha Discovery Sprint — 결과 보고 (2026-11-09)

**상태: `PREPARED_NOT_EXECUTED`. 이번 주기에 새로 계산한 역사 수익률은 0건이다.**
새 역사 outcome 읽기는 Owner 전용 결정(Issue #292 §8, 실행 로드맵의 KR 종결 규칙)이라 우회하지 않았다. 대신 계산 가능한 KR 후보 전체를 **계약 1개·승인 문구 1줄**로 묶었고, 승인 즉시 한 번에 실행되도록 실행기를 실제 입력으로 사전점검까지 마쳤다.

승인 문구(이 한 줄이면 KR 11개 책 × H126/H252 × 비용 1·2·3배가 한 번에 계산된다):

```
APPROVE BROAD_ALPHA_SCREEN_V1 EXPLORATORY_ONE_SHOT edc691a3e7483c8a902db9ae11bc220946dff62e7071846a5effd027f938635f
```

## 1쪽 표

초과수익 = 069500.KS(공식 분배금 반영 총수익) 대비 자금 일치 베타조정 선택 수익(δ_H). N = 독립 사건 수(H126) → 그중 보유창 전체에 가격이 있는 성숙 사건 수. "신뢰구간" 열은 결과 전 정밀도다: 2차 모멘트만으로 잰 δ126 표준오차와 검출 가능 최소 효과(MDE, 하한).

| 가설 | 데이터 적격성 | N | H126 초과수익 | H252 초과수익 | 비용 후 효과 | 신뢰구간 | 강건성 | 판정 | 다음 행동 |
|---|---|---|---|---|---|---|---|---|---|
| **P1 주주환원 통합** (소각+취득·신탁+배당 증액) — 1차 | 적격 (탐색 등급) | 1,094 → 982 | NOT_EXECUTED | NOT_EXECUTED | NOT_EXECUTED | SE 0.97%p, MDE 3.14%p (검정력 76%) | 미측정. 2025~26 진입 22% | NOT_EXECUTED (승인 대기) | 승인 문구 1줄 |
| **P2 희석 통합** (유상증자+CB·EB·BW, 회피 신호) — 1차 | 적격 (제목 수준, 조건 미파싱) | 369 → 312 | NOT_EXECUTED | NOT_EXECUTED | NOT_EXECUTED | SE 1.58%p, MDE 5.11%p (31%) | 미측정 | NOT_EXECUTED | 같은 승인 |
| **K3 공급계약 ≥ 매출 10%** — 1차 | 적격 (본문 파싱) | 464 → 389 | NOT_EXECUTED | NOT_EXECUTED | NOT_EXECUTED | SE 1.34%p, MDE 4.34%p (44%) | 미측정. 방산·조선+건설 58% | NOT_EXECUTED | 같은 승인 |
| K1 자사주 소각 (구성요소) | 적격 | 323 → 252 | NOT_EXECUTED | NOT_EXECUTED | NOT_EXECUTED | SE 2.36%p, MDE 7.64%p (13%) | 금융 36%, 2025~26 진입 52% | NOT_EXECUTED (단독 판정 없음) | 같은 승인, 기술 통계 |
| K2 비소각 자사주 취득·신탁 | 적격 | 522 → 469 | NOT_EXECUTED | NOT_EXECUTED | NOT_EXECUTED | SE 1.18%p, MDE 3.82%p (56%) | 미측정 | NOT_EXECUTED | 같은 승인 |
| K7 결산배당 +25% 이상 증액 | 적격 (2014~, 주식수 변동 건 제외) | 460 → 450 | NOT_EXECUTED | NOT_EXECUTED | NOT_EXECUTED | SE 2.06%p, MDE 6.67%p (17%) | 2~3월 집중, 빈 세션 702 | NOT_EXECUTED | 같은 승인 |
| K4 유상증자 결정 | 적격 (제목 수준) | 247 → 203 | NOT_EXECUTED | NOT_EXECUTED | NOT_EXECUTED | SE 1.84%p, MDE 5.95%p (22%) | 미측정 | NOT_EXECUTED | 같은 승인 |
| K5 CB·EB·BW 발행 결정 | 적격 (제목 수준) | 141 → 125 | NOT_EXECUTED | NOT_EXECUTED | NOT_EXECUTED | SE 2.75%p, MDE 8.90%p (10%) | 미측정 | NOT_EXECUTED | 같은 승인 |
| K6 공급계약 해지 | 적격 (제목 수준) | 106 → 96 | NOT_EXECUTED | NOT_EXECUTED | NOT_EXECUTED | SE 2.57%p, MDE 8.32%p (11%) | 발행사 47개뿐 | NOT_EXECUTED | 같은 승인 |
| K8 결산배당 −25% 이상 감액 | 적격 (2015~) | 229 → 223 | NOT_EXECUTED | NOT_EXECUTED | NOT_EXECUTED | SE 2.36%p, MDE 7.64%p (13%) | 미측정 | NOT_EXECUTED | 같은 승인 |
| K9 5% 대량보유 1%p 이상 증가 | 부분 적격: 2024-09 이후만, 보유목적 필드 없음 | 285 → 224 | NOT_EXECUTED | NOT_EXECUTED | NOT_EXECUTED | 시간 블록 2.0개 → 추론 불가 | 해당 없음 | 실행해도 `DESCRIPTIVE_ONLY` | 전향 누적 |
| KR 공급계약 규모(매출 대비 %) 용량반응 | 적격 (K3 내부 분해) | 464 | NOT_EXECUTED | NOT_EXECUTED | NOT_EXECUTED | — | — | K3의 분해로만 보고 | 같은 승인 |
| KR 내부자 순매수·군집매수 | **차단: 미수집** (임원·주요주주 소유보고 수집기 없음) | 0 | DATA_NOT_COLLECTED | DATA_NOT_COLLECTED | — | — | — | SOURCE_BLOCKED | 기존 DART 키로 밀도 probe 1회 |
| KR 5% 보유목적(경영참가) | **차단**: `majorstock` 응답에 목적 필드 없음, 이력 2024-09~ | 0 | FIELD_MISSING | FIELD_MISSING | — | — | — | SOURCE_BLOCKED | 본문 파싱 필요, 보류 |
| KR 공시 후 지연 반응(잠정실적) | 종결 (#308) | — | 미실행 (6~12M에는 타이밍 정보뿐) | 미실행 | — | — | — | 종결, 재개 안 함 | 없음 |
| KR 경쟁사·협력사 정보 전이 | 종결 (#310): H1 매출 예측 개선은 금융업 89%, H2 DATA_BLOCKED | — | 미실행 (수익률 검정 아님) | 미실행 | — | — | — | 공급망 연결 원천 없음 | 보류 |
| KR 투자자 수급·공매도 | 차단: KRX `LOGOUT` 거부 | 0 | SOURCE_BLOCKED | SOURCE_BLOCKED | — | — | — | SOURCE_BLOCKED | 재probe 1회만 |
| US 순주주환원·현금흐름 기반 자사주 | 전향 등록만 있음. 역사 패널은 생존편향 | 605주 | NOT_EXECUTED: 퇴출 324개 중 212개 가격 없음 | NOT_EXECUTED | — | — | — | SOURCE_BLOCKED (역사) | LIVE 시작 승인(기존 건) |
| US 순발행(주식수 변화) | **차단**: 기말 주식수 있는 공시 1.8% (SEC 403) | 0 | SOURCE_BLOCKED | SOURCE_BLOCKED | — | — | — | SOURCE_BLOCKED | 원천 없음 |
| US 수익성 × 투자 | 특성 계산 가능(현금 수익성 92%), 패널 생존편향 | 692 코호트(H63) | NOT_EXECUTED | NOT_EXECUTED | — | — | — | 기존 P4 승인 건 대기 | Owner가 P4 실행 여부 결정 |
| US 실적정보 지연 반영(PEAD) | 추정치 원천 없음(유료). 계절 SUE는 미구축 | 0 | NOT_EXECUTED | NOT_EXECUTED | — | — | — | SOURCE_BLOCKED | 보류 |
| US 산업 간 정보 전이 | 섹터 스냅샷 195개 있음. 패널 생존편향 | 0 | NOT_EXECUTED | NOT_EXECUTED | — | — | — | NOT_EXECUTED | 퇴출 가격 원천 결정 이후 |

## 1. 실제로 경제성을 계산한 가설 수

**0개.** 이번 주기에 새 역사 수익률·NAV·라벨은 한 번도 읽지 않았다. 계산한 것은 결과와 무관한 값뿐이다: 사건 6,190행(구성요소 3,973 + 통합 2,217), 보유창 가격 존재 여부, 2차 모멘트 기반 정밀도.

실행 준비가 끝난 것은 KR 11개 책(1차 3 + 구성요소 8)이다. 승인 뒤 한 번의 실행으로 표의 `NOT_EXECUTED` 칸이 채워진다.

## 2. 데이터 문제로 계산하지 못한 가설과 원인

| 가설 | 원인 |
|---|---|
| KR 내부자 순매수 | 수집한 적이 없다. 저장소의 DART 수집은 주요사항보고서·거래소공시(B/I001)와 `majorstock`뿐이다 |
| KR 5% 보유목적 | `majorstock.json`이 목적을 주지 않고, 이력이 2024-09-24부터라 시간 블록이 2개다 |
| KR 수급·공매도 | KRX 포털이 `HTTP 400 LOGOUT`으로 거부한다 (2026-09-24 실측, 변동 없음) |
| KR 정보 전이 | 공급망 연결 원천이 없다 (#310 H2) |
| US 전체 5개 군 | 역사 패널에 퇴출 종목 212개 가격이 없어 SPY 대비 비교가 위로 편향된다. 순발행은 주식수 원천(SEC)이 403이다 |

합계: 계산 불가 10개 군(KR 4, US 5, 종결 1). KR 4개 중 승인만으로 풀리는 것은 없다.

## 3. 유망한 후보 (정량 근거는 검정력뿐, 수익률 근거는 아직 없음)

수익률을 읽지 않았으므로 "유망"은 **판정이 가능한가**의 순위다.

1. **P1 주주환원 통합.** 독립 사건 1,094건(발행사 269개), 성숙·가격 완비 982건. δ126 표준오차 0.97%p, MDE 3.14%p, 3%p 효과에 대한 검정력 76%. 소각 단독(K1)은 MDE 7.64%p·검정력 13%로 Owner가 중단시킨 건인데, 같은 메커니즘의 세 공시를 묶어 처음으로 판정 가능한 수준이 됐다. 평균 동시 보유 39건이라 0~5종목 책으로 줄이는 규칙(선착순 5종목)도 계약에 넣었다.
2. **K3 공급계약.** 441건 성숙, MDE 4.34%p, 검정력 44%. 효과가 4%p 이상일 때만 잡힌다. 방산·조선과 건설이 58%라 최대 산업 제외 점검이 판정 조건이다.
3. **K2 비소각 자사주 취득·신탁.** 구성요소 중 가장 정밀하다(SE 1.18%p). 단독 판정은 없지만 P1 결과가 어느 구성요소에서 왔는지 보여준다.

## 4. 폐기·보류할 후보

| 후보 | 결정 | 이유 |
|---|---|---|
| K1 소각 단독 판정 | 폐기 (P1의 구성요소로만 유지) | MDE 7.64%p, 2025~26년 진입 52%·금융업 36%로 Value-up 국면과 분리 불가 |
| K5·K6·K8 단독 판정 | 폐기 (기술 통계만) | MDE 7.6~8.9%p. 어떤 결과가 나와도 결론을 바꾸지 못한다 |
| K9 5% 지분 증가 (역사) | 폐기, 전향만 | 2년 표본, 시간 블록 2개 |
| 잠정실적 지연 반응 | 종결 유지 | #308: 6~12개월 정보가 아니라 타이밍 정보 |
| Atlas-106, 31변수, C2 변형, Phase C | 재실행 금지 유지 | 이번 계약의 어떤 사건도 이 특성들을 쓰지 않는다 |

## 5. 다음 실행 가능한 연구

**KR (승인 1건).** 위 문구로 `broad-alpha-screen-v1`을 1회 실행한다. 판정 규칙은 계약에 고정돼 있다.
- 1차 3개만 Holm 보정 판정을 받는다: 동시 구간 방향 상한 < 3%p면 `EXPLORATORY_REJECT`, 모든 관문(Holm, 점추정 ≥ 3%p, 비용 2배 후 부호 유지, −100% 종결 스트레스 후 부호 유지, Value-up 전·후와 2025~26 제외와 최대 산업 제외에서 부호 유지, 현금 3개 시나리오)을 통과하면 `EXPLORATORY_SUPPORT_NOT_VERIFIED`, 그 외 `INCONCLUSIVE`.
- 어떤 결과도 VERIFIED가 아니다. KR 역사는 이미 노출된 표본이라 지지 판정이 나와도 다음 단계는 전향 영수증(A1/B1은 2026-11-09 시작)이다.
- 솔직한 예상: P1만 판정력이 있고 나머지는 `INCONCLUSIVE`일 가능성이 높다.

**KR (승인 불필요).** 내부자 소유보고 밀도 probe 1회(기존 `Probes` 워크플로와 DART 키). Top300에서 연 사건 수가 P1 수준이 되는지만 본다.

**US.** 새 계산을 제안하지 않는다. 역사 판정은 퇴출 종목 가격 원천(유료) 결정 전에는 어떤 설계로도 위로 편향된다. 기존에 대기 중인 Owner 결정 2건만 남아 있다: `us-capital-allocation-alpha-v1` LIVE 시작, cash-profitability P4 실행 여부.

## 6. 실제로 재사용한 범위

| 재사용 | 출처 |
|---|---|
| A1/A2/B1 봉인 코호트, Top300 발행사 공시 색인 27,322행, 배당결정 5,094건 | #320 |
| 달력시간 자금 일치 베타 책·대조군·일자별 거래세 비용, 블록 bootstrap, two-way 군집 | #322 `engine.py`, `inference.py`, `contract.py` (수정 없음) |
| 주식 총수익 지수(분할·배당), 069500 공식 총수익, 현금 3개 시나리오 | #322 `b1_inputs.py` (Owner 2026-11-08 결정 그대로) |
| 2차 모멘트 검정력 | #322 `power_calibration.py` |
| KRX 일봉 14개 연도 샤드, PIT Top300 스냅샷, 5% 보고 2,496건 | `signal-history` `c430e98a` |

새로 쓴 코드는 3개 파일(사건 매핑 `hypotheses.py`, 반복 실행기 `screen.py`, 사전점검 `prepare.py`)과 합성 테스트 8개다. 새 엔진은 없다.

## 알려진 한계 (계약 `knownLimits`)

- 사건 시점은 접수일 기준(`DATE_ONLY_CONSERVATIVE`)이고 진입은 접수 다음다음 세션 종가다.
- K4·K5·K6는 공시 제목으로만 분류했다. 제3자배정·주주배정, 발행 규모는 구분하지 않는다.
- 배당락일은 조건부 승인된 시장 규칙이고 공식 봉인이 아니다. 현금은 기준금리 대용이다.
- 종결대가 미확정 사건(P1 H126 7건)은 주 경로에서 빼고 −100% 하한으로만 넣는다. 무확인 기업행동이 보유창에 있는 7건은 제외한다.
- 유니버스는 PIT KOSPI Top300뿐이다. Top120 밖 산업 라벨은 PIT가 아니다.
- 작성자 자체 검증(`AUTHOR_VALIDATION_ONLY`)이다. 비작성자 감사는 받지 않았다.

## 재현

```bash
python -m research.broad_alpha_screen_v1.prepare --signal-history <ledger 경로> --commit c430e98a40b6b4b023e3007ccb396e594bf0fccb
```

```bash
python -m pytest -q tests/test_broad_alpha_screen.py
```

승인 후 실행 순서: `AUTHORIZATION.json`에 문구 기록 → `--mode claim` → 커밋·push → `--mode execute`.
