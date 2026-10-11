# 주간 투자 판단 — 운영 안내

정책: [`weekly-passive-first-v1`](weekly-passive-first-v1.md) · 사양: [`docs/weekly-decision/weekly-passive-first-v1.json`](weekly-decision/weekly-passive-first-v1.json)

## 매주 무엇이 나오는가

두 가지 출력이 지역마다 따로 나옵니다.

- **A. 이번 주 모델 보유안** — 아래 규칙의 결과. 비중이 있는 유일한 출력.
- **B. 이번 주 주목 종목 TOP 5** — production 리서치 순위(`longTerm.regions.<R>.researchTable`) 상위 5개를
  설명만 합니다. 라벨: "관찰 후보 — 통계적으로 검증된 매수 추천이 아님". 비중·확률·기대수익률을 붙이지 않고
  (발행 검증기가 그런 키를 거부), 강점/약점, 가격·모멘텀, 가치·수익성(현재 스냅샷 여부 표시), 하방위험,
  보정 우위 근거 유무, 데이터 범위, 보유안 제외 사유, 직전 확정 기록 대비 순위 변화를 보여 줍니다.
  관찰 후보는 영수증에 함께 기록되어(다이제스트 포함) 다음 주 순위 변화의 기준이 됩니다.

A의 규칙: 한국(`069500.KS` KODEX 200)과 미국(`SPY`) 각각에 대해, 서로 독립적으로:

- **지수 100%** — 비용을 넘는 방어 가능한 우위가 확인된 종목이 없을 때(기본값), 또는
- **1–5개 종목 × 15% + 나머지 지수** — 과거 보정 기대초과(126거래일)에서 종목·ETF 왕복비용을 뺀 순우위가 양수인 종목만.

비중 합계는 항상 100%이고 현금 목표는 없습니다. 근거가 없으면 "추정 불가"로 표시하며 0으로 채우지 않습니다.

## 언제 갱신되는가

`Append paper-signal ledger`(`ledger.yml`)가 매일 00:10 UTC(09:10 KST)에 production 산출물을 새로 만들고 검증한 뒤 판단을 계산합니다.

| 지역 | 판단 기준일 | 주간 확정(FINAL) 시점 |
|---|---|---|
| KR | 그 주 마지막 KRX 거래일(휴장 반영, 예: 2026-10-09 한글날이면 목요일) | 그 다음 실행(보통 토요일 09:10 KST) |
| US | 그 주 마지막 NYSE 거래일 | 토요일 09:10 KST(미국 동부 종가 + 1시간 이후) |

- 거래소 마감시각은 각 거래소 시간대로 계산하므로 서머타임에 흔들리지 않습니다. 기준 시각은 원본 산출물의 `generatedAt`이라 같은 산출물은 항상 같은 영수증을 만듭니다.
- 지역의 거래일 증거는 **그 지역 지수 시세**(`indices`의 `^KS11` / `^GSPC` `asOf`)입니다. 첫 버전은 지역 내 아무 종목의
  가장 최근 `asOf`를 썼기 때문에, 종목 하나만 최신이어도 나머지가 오래된 횡단면이 최신처럼 보였습니다(수정).
- 종목별로도 확인합니다. 자기 시세가 지역 기준 거래일보다 오래된 후보는 `STALE_CANDIDATE_DATA`로 표시되고 편입될 수 없습니다.

| 상태 | 뜻 | 비중 | 영수증 |
|---|---|---|---|
| `STOCKS_SELECTED` | 비용 차감 후 기대 우위가 양(+)인 종목 1–5개 + 나머지 지수 | 있음 | 기록 |
| `PASSIVE_NO_DEFENSIBLE_EDGE` | 데이터는 최신이나 방어 가능한 우위 없음 → 지수 100% | 지수 100% | 기록 |
| `NO_CANDIDATES` | 리서치 후보 풀이 비어 있음 → 지수 100% | 지수 100% | 기록 |
| `STALE_DATA` | 지역 지수 시세가 마지막 완료 거래일보다 오래됨(또는 없음) | 없음(직전 확정 표시) | 없음 |
| `SOURCE_INCOMPLETE` | 지수는 최신이나 보정 자료가 없거나 모든 후보 시세가 지연 | 없음(직전 확정 표시) | 없음 |
| `DATA_BLOCKED` | 원본 산출물이 차단·seed·synthetic·stale | 없음, 관찰 후보도 없음 | 없음 |
- 주중 실행은 `INTRA_WEEK_PREVIEW`(미리보기)로 표시되며 영수증으로 기록되지 않습니다. 주의 마지막 거래일 데이터로 만든 판단만 `FINAL_WEEKLY` 영수증이 됩니다.

## 파이프라인

```
ledger.yml (매일 00:10 UTC)
  python -m pipeline.build → pipeline.validate → scripts/update_ledger.py (기존)
  python -m pipeline.weekly_publish (추가, 실패해도 페이퍼 원장은 계속)
    → signal-history: ledger/weekly-decisions/latest.json   (사이트가 읽는 현재 판단)
    → signal-history: ledger/weekly-decisions/receipts.jsonl (추가 전용 영수증)
    → signal-history: ledger/weekly-decisions/publication-status.json (성공·거부 모두 기록)
사이트(app.js) → data/weekly-decision.json(있으면) 또는
  raw.githubusercontent.com/<owner>/<repo>/signal-history/ledger/weekly-decisions/latest.json
```

`pages.yml`, `pipeline/build.py`, `pipeline/validate.py`, 워크플로 인벤토리 문서·테스트는 봉인 연구
(alpha-opportunity-model-v1, kr-alpha-atlas Phase C v1–v4)가 바이트 해시로 고정하므로 수정하지 않았고,
새 워크플로 파일도 추가하지 않았습니다. 그래서 판단은 Pages 산출물이 아니라 공개 signal-history 브랜치에서 읽습니다.

## 실패가 보이게

- 판단 단계가 검증에서 거부되면 `latest.json`과 영수증은 그대로 두고 `publication-status.json`만 `REFUSED`(오류 목록, 실행 번호)로
  갱신해 커밋합니다. 사이트는 이 파일의 시도 시각이 현재 판단보다 늦으면 "최근 게시 시도가 거부되어 이전 판단을 유지"를 표시합니다.
- 사이트는 네트워크 실패(일시적, 15분마다 재시도·즉시 재시도 버튼)와 404(아직 게시 없음)를 구분하고, 새로 고침에 실패해도
  마지막으로 받은 파일을 유지합니다. `latest.json`이 3일 넘게 갱신되지 않으면 날짜와 함께 지연을 표시합니다
  (raw.githubusercontent.com 캐시는 최대 약 5분이라 그보다 짧은 지연은 정상 전파 지연입니다).
- 원장 워크플로 앞 단계(빌드·검증)가 실패하면 판단 단계 자체가 실행되지 않으므로, 이 경우는 위의 3일 지연 표시로 드러납니다.

## CI(Tests) 타임아웃 — 현재 차단 사항

- 증상: Tests 워크플로가 30분 제한(`timeout-minutes: 30`)에 걸려 취소됩니다. PR만의 문제가 아니라 **main 자체**(실행 38043294031,
  문서만 바꾼 #217 병합)도 같은 이유로 취소됐습니다.
- 원인: 스위트(약 4,250개)가 빠른 러너에서 17분 30초(실행 38036614239, 같은 날 main 성공)였고, 느린 러너에서는 같은 구간이
  1.6–1.9배 느렸습니다(예: 41→42% 구간 6분 대 11분). 여유가 12분뿐이라 러너 편차만으로 30분을 넘습니다. 이 PR이 더한
  테스트는 약 50개·10초 미만입니다.
- 차단: `.github/workflows/tests.yml`은 `research_specs/kr-alpha-atlas-phase-c-v1.json`의 `dependencyHashes`에
  sha256 `1f270bcd6e19f332595b737286e75c4b611ddb0320c16d2c5b972a26ba057ec5`로 고정되어 있어, 제한 시간을 바꾸면 봉인된
  Phase C v1 등록이 깨집니다. 그래서 이 PR에서는 바꾸지 않았고 테스트를 지우거나 건너뛰지도 않았습니다.
- 제안(소유자 승인 필요): Phase C 계약에 tests.yml 변경을 명시적으로 허용하는 별도 사전 등록 개정 후
  `timeout-minutes: 45`로 올리거나, `pytest-xdist`로 2개 작업에 나눠 실행. 둘 다 새 워크플로 파일 없이 tests.yml만 바꿉니다.

## 안전 규칙

- 원본 site-data가 차단(`recommendationsBlocked`)·seed·synthetic·stale이면 두 지역 모두 `DATA_BLOCKED`, 종목·비중·관찰 후보 없음.
- 영수증 식별자 = (정책 버전, 지역, 기준일). 같은 식별자로 내용이 다른 판단이 오면 첫 기록을 유지하고 나중 것을 거부합니다.
- 종목 매매·알림 발송은 하지 않습니다. 영수증은 향후 알림에 쓸 수 있는 형태로만 저장합니다.
- 실시간 검증(`liveValidated`)은 어떤 경우에도 자동으로 켜지지 않습니다.

## 수동 실행

Actions → **Append paper-signal ledger** → Run workflow. 판단 단계가 검증에 실패하면 경고만 남기고 아무것도 쓰지 않으며,
페이퍼 원장 기록은 그대로 진행됩니다.

## 첫 게시 확인 (2026-10-11 기준)

- #218 병합(`123ce7d8`, 2026-10-11 02:45 UTC) 직후 확인: `signal-history`에 `ledger/weekly-decisions/`가 **아직 없음** →
  사이트는 두 지역 카드를 "미게시"로 표시하고 비중을 그리지 않습니다(`NOT_PUBLISHED_YET`). 이는 정상 상태입니다.
- 원장 워크플로는 예약상 00:10 UTC이지만 실제로는 05:40 UTC 전후에 시작해 왔습니다(최근 4회). 병합 후 첫 예약 실행이
  `main`의 새 단계를 실행하면 `latest.json`, `receipts.jsonl`, `publication-status.json`이 처음 생깁니다.
- 토요일(KST) 실행에서 나온 판단만 `FINAL_WEEKLY` 영수증이 됩니다. 주중 실행 결과는 미리보기로만 표시되고 기록되지 않습니다.
- 수동으로 먼저 확인하려면 Actions → **Append paper-signal ledger** → Run workflow(소유자 실행). 이 세션은 실행하지 않았습니다.
- 확인 순서: ① 실행 로그의 "Weekly decision and append-only receipts" 단계 출력(`regions`·`receipts`) ② signal-history의 세 파일
  ③ 사이트 첫 화면 카드의 기준일·상태 ④ 다음 주 같은 기준일 영수증의 다이제스트가 바뀌지 않았는지.
