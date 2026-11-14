# decision-desk-v1 — 연구를 날짜가 찍힌 투자 판단과 검증으로 연결

**상태:** 연구·가상 판단, dry-run.
- production 비중, 영수증, `signal-history`는 바꾸지 않았다.
- 전향 원장 활성화와 실제 게시(Pages)에는 Owner 승인이 필요하다.

**이번 작업 전과 달라진 점:** 누구나 아래 다섯 가지를 확인할 수 있다.
1. 오늘 기준 KR/US에서 어떤 종목을 왜 골랐는지(또는 왜 0개인지)
2. 어떤 데이터를 썼는지(해시)
3. 언제 틀렸다고 인정할지(훼손 조건)
4. 그 판단이 판단 시점에 공개됐다는 증거(커밋 시각 < 실행 시각)
5. 6·12개월 뒤 비용 차감 성과를 채울 원장

## A. 현재 알고 있는 사실과 한계 (1페이지)

| | 한국 (KR) | 미국 (US) |
|---|---|---|
| **현재 production 판단** | 069500.KS 100% (2026-11-06 FINAL_WEEKLY). 알파 순위의 수익 정렬 미확인(rank IC t 0.68) | SPY 100% (2026-11-06 FINAL, 11-10 주중 미리보기). 정렬 미확인(t 0.17). QQQ는 비교 기준 |
| **시장 상태 (관측)** | KOSPI는 252일 고점 대비 −44%, 63일 −20%, 변동성 47%, 200일선 아래. 069500도 고점 대비 −46.7%로 일치 | SPY는 200일선 위, 고점 대비 −5.6%. 63일 −4.9%, VIX 28. QQQ가 63일간 SPY보다 −4.1%p |
| **검증된 사실** | ML v1 141개는 검증된 ETF 초과성과 없음. v2 정정에서 ETF 회계(17.92%)만 범위 인증되고 주식 후보 3개는 SOURCE_BLOCKED. 산업모멘텀 우위는 위상 의존(네 위상 −9.40~+2.58%p) | 동적 ETF 배분 6종 모두 비용 후 정적 S4 미달. 추세 규칙의 낙폭 방어는 동일위험 대조 후에도 **2008년 한 사건**에서만 남고, 2016년 이후는 열위(아래 F1) |
| **탐색적 주장 (승격 불가)** | 전략 모멘텀(+15.5%p, 위상0만. 6정책 Holm p=.186), S2 가치·확인(비용 2배 +0.04%p, 2025년 제외 +0.0015%p) | 확장 기간 D1/D3/D6의 위기 방어 |
| **미확정·차단** | 154개 중 62종목·135사건의 기업행동 미복구. 069500 2026-07-31 +24.17% 일간수익의 설명 미해결. Holm 보정 누락 정정 필요 | 퇴출 324개 중 212개 무가격(개별주 과거 성과 차단). 비주식 ETF 6종은 단일 공급자. KRW 환산의 "no-look-ahead" 주장 철회(H.10 공표 시점) |
| **판단 한계** | 현재 후보 재무값은 현재 스냅샷이다(전향에서는 판단 시점 값). 12개 후보 중 11개는 사전 관문 미통과 | AI(B2)의 TRV 선택은 정성 종합판단이다. 확률·목표수익을 만들지 않았다 |

## B. 사이트의 읽기 전용 판단 화면

- 위치: 기존 사이트 `#decision` 섹션 안의 `#desk`("연구 판단 데스크", 요청 시 로드). 기존 6개 섹션 계약은 그대로다.
- 데이터: [`desk.json`](desk.json). 커밋 `ea57a40a`에 SHA-256으로 고정했고, 기존 원천과 같은 raw+해시 검증 패턴을 쓴다.
- 화면 구성:
  - ① 지역별 판단: production 판단, 신선도, 연구 모델별 기록과 날짜, B2 근거·위험·훼손 조건, 차단 상태
  - ② 사실과 한계
  - ③ 전략별 과거 성과: 유형 배지로 탐색·정정·차단을 구분하고, 차단 행은 숫자를 표시하지 않음
  - ④ 전향 기록 원장
- 계약([`validate_desk.py`](validate_desk.py), JS `validDesk`). 다음 항목은 표시하지 않고 거부한다.
  - 차단 행의 숫자
  - 실행 뒤에 생성된 배분을 "연구 배분 기록"으로 표시하는 것
  - 과거 재구성을 현재 추천으로 표시하는 것
  - 확률·목표가 필드
- 날짜가 10일 넘게 지난 기록에는 "과거 기록, 현재 추천 아님" 표시가 자동으로 붙는다.
- US 2026-10-30 칵테일 배분은 실행 뒤에 생성된 과거 재구성으로만 표시한다.
- **배포:** Pages는 #321 승인·병합·운영 복구 후에 반영된다. 이 PR은 workflow를 건드리지 않는다.

## C. 현재 적격 데이터로 만든 연구용 선택 (2026-11 코호트, dry-run)

입력은 production FINAL_WEEKLY 영수증 2026-11-06(`signal-history@6398e94f`)이다. 영수증 digest는 production 함수로 재검증했다. 시장·거시 관측은 마감일에서 잘라 해시로 고정했다. [`evidence-pack.json`](inputs/2026-11/evidence-pack.json)

| 지역 | B0 ETF | B1 기존 규칙(production 복사) | B2 AI 종합판단 | 실행 예정 |
|---|---|---|---|---|
| KR | 069500 100% | 069500 100% | **0개 → 069500 100%** | 2026-11-12 종가 |
| US | SPY 100% | SPY 100% | **TRV 10% + SPY 90%** | 2026-11-11 종가 |

- **KR이 0개인 이유:** 12개 후보 중 11개가 사전 관문에서 탈락했다(AVOID, 하락 추세, 위험·데이터 부족).
  - 남은 코웨이는 지지 층이 2개(기업, 위험)뿐이다.
  - 베타 0.11의 방어력은, 고점 대비 −44% 이후 반등이 오면 ETF에 크게 뒤처질 이유이기도 하다.
- **US가 TRV인 이유:**
  - ROE 약 27%, 부채비율 약 34의 보험사가 지수보다 낮은 PER에 거래된다.
  - 베타가 0에 가깝고 낙폭 −10%로, SPY 90% 잔여분을 분산한다.
  - 진입 상태가 ACCUMULATE_GRADUALLY이고, 관문 위반이나 반박 층이 없다.
- **US 제외:**
  - MPC: 위험 층이 반박(변동성 37%, 정점 사이클 이익)
  - SPG: 지지 층 1개(ROE는 회계 왜곡, FFO 없음, 금리 상승 역풍)
- **TRV 훼손 조건:**
  - 200일선 아래 + 63일 수익 음수
  - 진입 상태가 AVOID로 바뀜
  - 단일 재해로 설명되지 않는 언더라이팅 적자 분기
  - 126세션 전 어느 월말에든 비용 차감 SPY 대비 −10%p 초과
- 모든 근거·위험·미확인 정보는 [원장의 B2 기록](dry-run/ledger.jsonl)에 있다. AI 학습 시점 이후 뉴스는 읽지 않았다.

## D. AI 종합판단 실험(B2) — 사전 고정 규칙·데이터 계약·dry-run

- **규칙:** [`protocol.json`](protocol.json). 첫 기록과 같은 커밋 `860a1845`(12:30:49Z)로 고정했고, 두 실행 시각보다 앞선다.
  - 7개 층(시장·산업·기업·가격·거시·기존 연구·위험)을 SUPPORTS / NEUTRAL / CONTRADICTS로 판정한다.
  - 관문 G1~G6을 통과해야 한다.
  - 지지 층이 3개 이상이고, 기업·가격·위험 층에 반박이 없어야 한다.
  - 시장 층이 반박이면 그 지역은 최대 2종목이다.
  - 종목당 10% 고정, 잔여는 ETF이다(AI가 비중을 정하지 않음). 0개도 허용한다.
- **데이터 계약:**
  - AI 리뷰에는 판정 라벨과 해석 문장만 쓴다.
  - 관측 수치는 `judgment.py`가 증거 묶음에서 복사한다. 그래서 리뷰가 증거에 없는 숫자를 인용할 수 없다.
  - 리뷰는 증거 묶음 해시에 묶여 있다.
- **거부:** 관문에서 탈락한 종목 선택, 규칙 미달, 확률·목표가·기대수익 필드, 다른 증거 묶음에 근거한 리뷰.
- **비교:**
  - B0 ETF / B1 production 규칙 / B2 AI를 같은 실행일·비용·지평으로 비교한다.
  - 관찰 비교군: KR `kr-selection-challenger-v2-accounting` CH_VALUE_CONFIRMED(기존 전향 기록). 기각된 ML은 승격하지 않는다.
- **알려진 한계:**
  - 이번 B2 해석문은 영어로 기록됐다. 원장이 append-only라 그대로 두고, 다음 코호트부터 한국어로 쓴다.
  - 저자는 규칙을 고정하기 전에 후보 이름과 진입 상태를 봤다(`authorExposureDisclosure`).

## E. 6·12개월 전향 성과 원장 — [`ledger.py`](ledger.py)

- 기록 형식은 `RESEARCH_DECISION_RECORD_V1`이다. 사용자가 요구한 필드를 모두 담고, 여기에 다음을 더했다.
  - `plannedExecutionCloseUtc`, `costs`
  - 해시 체인(`prevDigest`, `digest`)
- 기록은 수정하지 않는다. 성과는 별도 `OUTCOME` 행으로 추가하며, 지평 종료 세션이 실제로 지난 뒤에만 SCORED가 된다.
- 기업행동이 미확인이거나 가격이 없으면 SOURCE_BLOCKED로 둔다. 0%로 대체하지 않는다.
- 중복 코호트, 편집·삭제(체인 단절), 시간 순서 위반, 실행 후 공개, 6종목 이상은 거부한다.
- `dry-run/` 밖에 쓰려면 Owner 승인이 필요하다.
- 과거 154개 기업행동 복구와 독립적으로 지금부터 기록할 수 있다.

## F. 후속 연구 — 기존 연구 분류와 선정 2건

| 분류 | 대상 |
|---|---|
| 재검증 가치 있음 | S2 가치·확인(이미 전향 기록 중). 018880·005930 기업행동 패키지 복구 후 v2 주식 경제성 |
| 경제적 가능성 낮아 종료 | KR ML 141개 그리드 재탐색, KR 거시 상태 학습형 선택(OOS R² 9개 모두 음수), US 동적 ETF 신호 변형 추가, 4요인 알파 가중치 재조정 |
| 데이터로 보류 | US 개별주 과거 성과(212 무가격), KR 2018 비상장 권리(006800) 경제성, 투자자 수급(KRX 접근 거부) |
| 전향 기록이 가장 합리적 | B2 AI 종합판단, US 추세 위기 방어(D1/D3), KR 전략 모멘텀, S2 |
| 새 정보축 확보 시에만 | DART 대량보유 공시(2024-09~ 전향만), 투자자 수급, 애널리스트 추정치 수정 |

**선정 1 — US 추세 위기 방어의 동일위험 대조 (실측 완료, PR #331 errata E4)**
- 기존 판단: 추세 규칙의 낙폭 방어가 "위험을 낮춘 효과"보다 큰지 확인되지 않았다(#333).
- 실측 방법: 평균비중 쌍둥이를 실현 변동성이 같도록 BIL로 디레버리지했다.
- 확장 기간 결과(D1, D3, D6):
  - MDD −16~−18% 대 −20~−21%
  - D1의 GFC 낙폭 −3.2% 대 −20.2%
  - CAGR 격차 +0.37~+0.49%p, 구간은 0 포함
- 2016년 이후 결과: CAGR −0.35~−1.35%p로 열위이고, MDD도 더 깊다.
- **판단: 방어는 사실상 2008년 한 사건이다.** 승격하지 않고 전향 기록 후보로 둔다.

**선정 2 — US 데이터 무결성: 환율 공표 시점과 독립 가격 (실측·차단 표시 완료, errata E1/E2/E5)**
- 환율 공표 시점:
  - H.10 공표 규칙(다음 월요일 16:15 ET)을 구현했다.
  - 10-30 종가 시점에 공개된 값은 10-23의 1,325.06, 같은 날 관측치는 1,333.99, 원래 잘못 쓴 값은 11-02의 1,344.51이다.
  - 원화 성과는 두 정의로 다시 계산했다. 주 기간 S4는 회계(같은 날 관측치) 기준 10.74%, 공표 기준 10.68%, 원값 10.63%다.
- 평균비중 쌍둥이의 분모를 130개로 정정했다.
- 2차 가격 공급자(Nasdaq, Stooq)는 접속이 불가해 `INDEPENDENT_VENDOR_UNREACHABLE`로 남겼다.
  - FRED 금리 기반 개연성 점검: IEF 상관 0.992, SHY 0.987, BIL 0.957
  - 가격 검증은 아니다.

**실행하지 않은 것과 이유**
- 봉인 결과 재실행, 역사 탐색 예산 확대, 보호 데이터 수정은 하지 않았다.
- KR 018880·005930 기업행동 패키지는 원천 담당과 외부 회계 reviewer의 일이다(#333 G 우선순위 1·2).
- US 유료 원천:
  - Norgate Platinum 연 US$630: 퇴출 종목과 역사 구성원을 포함하지만, 구독 종료 시 추출본 삭제 조항이 보고돼 있다.
  - Sharadar Bundle 연 US$499: 개인용 라이선스.
  - 둘 다 구독·결제는 하지 않았다. 상세 비교는 #331 README §9에 있다.

## G·H. 변경 범위와 승인 필요 항목

- 새 파일은 `research/decision_desk_v1/` 아래와 `tests/decision_desk.test.cjs`다. 수정한 파일은 `app.js`, `index.html`, `styles.css`(추가만)다.
- 수정하지 않은 것: workflow, `pipeline/`, KR 연구 파일, 봉인 사양, `docs/results/`, `research_specs/`.
- 승인·담당이 필요한 항목은 `desk.json`의 `approvalsNeeded`에 있고 화면에도 표시된다.
  - #321 병합과 Pages 복구
  - 전향 원장 활성화
  - 월간 B2 작성 담당
  - 유료 원천 구매
  - KR 기업행동 패키지

## 재현

```bash
python research/decision_desk_v1/evidence.py --signal-commit 6398e94feddd4f552910d31b36bc8db0766576af --month 2026-11   # 증거 묶음 (--fetch는 원시 재취득)
python research/decision_desk_v1/build_desk.py            # desk.json (계약 검증 포함)
python -m pytest -q research/decision_desk_v1             # Python 계약 + Node 화면 계약
node --test tests/decision_desk.test.cjs
```

## v2 후속 개선 (2026-11-11) — PIT 정정·단계 분리·평가기

### 1. PIT 정정과 영향 ([`audits/2026-11-pit-review.json`](audits/2026-11-pit-review.json))

공표 시점은 연준 페이지에서 직접 확인했다(2026-11-11 22:23Z).
- **H.10:** "On Mondays at 4:15 p.m. … for the previous business week"
- **H.15:** "posted daily Monday through Friday at 4:15pm". 11-10 공표분에 11-09 자료까지 들어 있다.

v1 증거 묶음은 정보 마감 시점에 아직 공개되지 않은 값을 읽었다. KR 8건, US 4건이다.

| 입력 | 실제 공표 | KR 마감 06:30Z | US 마감 21:00Z | v1 값 → 공개되어 있던 값 |
|---|---|---|---|---|
| USD/KRW H.10 2026-11-05 | 11-09 21:15Z | 미공개 | (미사용) | 1,352.95 → 1,333.99 (10-30 관측) |
| DGS10 2026-11-05 | 11-06 21:15Z | 미공개 | 미공개(15분 후) | 4.84% → 4.90%, 63일 변화 +0.15 → +0.27%p |
| VIXCLS 2026-11-05 (보수 규칙) | 11-06 21:15Z | 미공개 | 미공개 | **28.18 → 16.61** |
| GLD/UUP/IEF 11-06 종가 | 11-06 21:00Z | 미공개 | 공개 | UUP 126일 +6.55% → +5.51% (KR) |
| Yahoo KRW=X 일봉 | 확인 불가 | 제외 | — | — |

**판단 영향**
- 관문 G1~G6와 B0/B1은 production 영수증만 읽으므로 그대로다.
- 하지만 AI(B2)의 시장·거시 판정 라벨과 근거 문장은 오염된 값을 보고 쓰였다. 특히 US 시장 해석, TRV 근거 2, 6개월 가설의 "VIX 28"이 그렇다.
- KR 코웨이는 지지 층이 2개였다. 거시 층이 SUPPORTS였다면 선택 가능했으므로, KR 0개 판단은 오염된 입력 위에서 정해진 라벨에 의존했다.
- 깨끗한 값으로 다시 리뷰하면 이미 결과 기간에 들어선 뒤의 사후 판단이 된다. 그래서 다시 생성하지 않는다.
- **조치:**
  - 2026-11 기록 6건은 바이트 그대로다. 테스트로 해시를 고정했다.
  - 두 B2 기록에 `PIT_CONTAMINATED` 주석 행을 추가했다. 채점은 하되 주 비교에서는 제외한다.
  - 6건 모두 `PUBLICATION_VERIFIED`다. git 커밋 `860a1845`(12:30:49Z)가 두 실행 마감보다 앞서고 원격 브랜치에 공개되어 있다.

### 2. 단계 분리 (protocol v2, [`protocol-v2.json`](protocol-v2.json))

| 단계 | 명령 | 다음 단계로 넘어가는 조건 |
|---|---|---|
| 1 봉인 | `protocol-v2.json`·`reviewers.json` 커밋 (`6e4d1f66`) | 미커밋·수정 상태면 packet 거부 |
| 2 증거 패킷 | `desk.py packet` | 모든 관측값이 공표 시점(`availableAtUtc`) ≤ 지역 마감. 실행일과 등록 마감을 여기서 고정한다(봉인 + 48시간 뒤 첫 세션의 시가) |
| 3 AI 리뷰 | `review-template` → (작성) → `check-review` → `commit-review`(약속 해시 먼저 커밋) → 리뷰 커밋 | 패킷만 읽음. 약속이 공개보다 먼저면 `INDEPENDENT_BY_COMMIT_ORDER` |
| 4 판단 생성 | `desk.py decide` | 패킷·리뷰가 커밋돼 있고 등록 마감 전이어야 한다. B0·B1·B2(primary)·BX(비교군) 기록을 만든다. 주 리뷰가 없으면 `B2_NO_REVIEW`(소급 금지) |
| 5 공개 | `git push` 후 `desk.py verify-publication` | 기록 줄을 처음 담은 커밋이 원격에 있고 시각 < 마감 → `PUBLICATION_VERIFIED`, 아니면 `_LATE` |
| 6 평가 | `desk.py evaluate --fetch` | 126·252세션 종료 세션이 실제로 지난 뒤에만 SCORED. 아니면 PENDING(원장에 쓰지 않음) |

`desk.py status`는 각 코호트가 어느 단계에서 무엇을 기다리는지 보여준다.

### 3. 평가기 ([`evaluate.py`](evaluate.py))

- 진입은 실행일 종가(종가 단일가), 청산은 126·252번째 거래소 세션 종가다.
- 배당은 배당락일 종가에 재투자하고, 기준은 069500.KS / SPY 같은 기준이다. 비용은 영수증의 왕복 비용(2배 스트레스 별도)이다.
- `SOURCE_BLOCKED` 조건:
  - 세션 종가 누락
  - 거래량 0(거래정지)
  - 검증 목록에 없는 분할·병합
  - KR 30% / US 50% 초과 변동
  - 청산 세션 종가 없음(상장폐지)
- 0%로 대체하지 않는다. 검증된 기업행동은 [`verified-corporate-actions.json`](verified-corporate-actions.json)에 공식 출처와 함께 넣어야 허용된다.

### 4. AI 비교군과 소급 금지

- B0/B1/B2 구조는 그대로다. [`reviewers.json`](reviewers.json)의 다른 리뷰어는 `BX:<id>` 비교군으로만 기록되며, B2를 대체하거나 승격하지 않는다.
- `gpt`, `claude-independent`는 `PENDING_OWNER_APPROVAL` 상태다. 해당 월 패킷 봉인 전에 ENABLED로 커밋해야 참여한다.
- 마감 뒤의 판단은 원장이 `REGISTRATION_CLOSED`로 거부한다. 2026-11의 B2 자리는 이미 claude 기록이 차지하고 있다.
  - 대화 중 나온 종목 아이디어(예: 삼성전기 009150.KS)도 2026-11 코호트로 넣을 수 없다. 테스트로 확인했다.
  - 이 저장소에 삼성전기 기록은 없다.

## 다음 월간 판단(2026-12) 실행 절차

```bash
# 0. 12월 첫 FINAL_WEEKLY 영수증(예상 asOf 2026-12-04, 생성 12-05 토요일 KST 오후)이 signal-history에 올라온 뒤
git fetch origin signal-history && SH=$(git rev-parse origin/signal-history)
python research/decision_desk_v1/desk.py status --month 2026-12          # AWAITING_PACKET

# 1. 증거 패킷(봉인). 이 시각 + 48시간 뒤 첫 세션 시가가 등록 마감이 된다
python research/decision_desk_v1/desk.py packet --month 2026-12 --signal-commit $SH --fetch
git add research/decision_desk_v1/cohorts/2026-12 && git commit -m "desk: 2026-12 evidence packet (stage 2)" && git push

# 2. AI 리뷰(에이전트 세션이 패킷만 읽고 작성; 자동 호출 불가)
python research/decision_desk_v1/desk.py review-template --month 2026-12 --reviewer claude
#    cohorts/2026-12/reviews/claude.json 의 TODO를 모두 채운다(한국어, 확률·목표가 금지)
python research/decision_desk_v1/desk.py check-review --month 2026-12 --reviewer claude
python research/decision_desk_v1/desk.py commit-review --month 2026-12 --reviewer claude
git add research/decision_desk_v1/cohorts/2026-12/commitments && git commit -m "desk: 2026-12 review commitment" && git push
git add research/decision_desk_v1/cohorts/2026-12/reviews && git commit -m "desk: 2026-12 claude review (stage 3)" && git push

# 3. 판단 생성 → 공개 → 검증 (모두 등록 마감 전)
python research/decision_desk_v1/desk.py decide --month 2026-12
git add research/decision_desk_v1/dry-run/ledger.jsonl && git commit -m "desk: 2026-12 decisions (stage 4)" && git push
python research/decision_desk_v1/desk.py verify-publication --month 2026-12
python research/decision_desk_v1/build_desk.py                           # desk.json 재생성 후 app.js DESK 고정값 갱신
git add -A research/decision_desk_v1 app.js && git commit -m "desk: 2026-12 publication verified" && git push

# 4. 평가 (2027-05-14 US / 2027-05-19 KR 이후 첫 실행부터 2026-11 126세션 채점)
python research/decision_desk_v1/desk.py evaluate --fetch
```

등록 마감을 놓치면 `decide`가 `REGISTRATION_CLOSED`로 거부하고, 그 달은 B0/B1만 기록된다. 마감 시각은 패킷의 `schedule.registrationDeadlineUtc`와 `desk.py status`에 표시된다.
