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

## CI(Tests) 타임아웃 — 측정된 진단 (2026-10-11)

이 절의 실행 시간은 당시의 측정 기록입니다. 30분 제한과 새 해시 등록 제안은
[CI timeout/provenance v1](ci/pytest-timeout-and-provenance-v1.md)에서 해결했습니다.
현재 제한은 60분이며, 원본 연구 명세를 다시 생성하지 않고 등록 커밋의 과거
workflow와 검증기 바이트를 확인합니다. 30분 제한 때문에 반복 재시도하던 운용을 대체합니다.

- **느린 테스트는 이 PR과 무관하며 main에 이미 있습니다.** 전체 스위트(4,260개)를 `--durations`로 로컬 측정(34분 17초)한 결과 가장 느린 것은
  모두 봉인된 Phase C 테스트입니다: `test_kr_alpha_atlas_phase_c.py::test_M_complete_determinism_full_schema_and_durable_bytes` 224초,
  같은 파일 `test_A_true_standalone_direction` 준비 단계 206초, `test_full_size_safe_synthetic_memory_and_masks` 86초,
  `test_kr_alpha_atlas_mirae_repair.py::test_complete_synthetic_study_uses_the_same_repaired_contract` 215초. 5초 넘는 62개 항목 합계 1,641초 중
  `phase_c.py` 635초 + `mirae_repair` 234초가 53%입니다. CI 로그에서 41%→42% 구간이 6분(빠른 러너)에서 11분(느린 러너)으로 늘어난 바로 그 위치입니다
  (collect 순서상 `mirae_repair`·`phase_b`·`phase_c`가 41–44%).
- **이 PR이 더한 테스트는 `tests/test_us_source_readiness.py`(8개) 하나이고 0.44초입니다.** main과 PR의 `tests/`·`.github/` diff는 이 파일뿐입니다.
- **러너 편차가 크고 30분 제한 안팎에서 갈립니다.** 같은 pytest 내용의 최근 실행: 성공 17.5분(main 38036614239), 19분(38097353800), 22.6분(38098935635),
  20분(38106217306); 30분 제한 취소 38097268802, 38099014804, 38106151051(main), 38107321054(모두 70% 안팎, 실패 0건). 즉 최근 8회 중 4회가 취소입니다.
- **고칠 수 없는 이유(우회하지 않음):** 느린 테스트 파일은 `research_specs/kr-alpha-atlas-phase-c-v1.json`(`tests/test_kr_alpha_atlas_phase_c.py`
  sha256 `186ab58a…`)과 `kr-alpha-atlas-phase-c-v3-price-repair.json`(`tests/test_kr_alpha_atlas_mirae_repair.py` sha256 `b707fd1b…`)이 바이트 해시로 고정하고,
  공유 `tests/conftest.py`는 `market-industry-stock-data-foundation-v1.json`이 고정합니다. 합성 입력 캐싱 등으로 줄이려면 이 파일들을 고쳐야 해서 봉인 계약이 깨집니다.
  `tests.yml`도 `kr-alpha-atlas-phase-c-v1.json`의 `dependencyHashes`(sha256 `1f270bcd…`)로 고정되어 제한 시간을 바꿀 수 없습니다.
- **가장 작은 소유자 승인 변경:** Phase C 계약 개정(pre-outcome addendum)으로 `tests.yml`의 `timeout-minutes: 30`을 60으로 올리는 한 줄 변경과 새 해시 등록.
  (대안: 위 두 테스트 파일의 합성 입력 생성 캐싱 — 두 봉인 해시 모두 개정 필요, 변경 범위가 더 큼.) 그 전까지는 취소된 실행을 "Re-run jobs"로 다시 돌리는 것이 유일한 방법이며
  빠른 러너에서는 약 20분에 통과합니다.

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
