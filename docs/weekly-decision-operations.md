# 주간 투자 판단 — 운영 안내

정책: [`weekly-passive-first-v1`](weekly-passive-first-v1.md) · 사양: [`research_specs/weekly-passive-first-v1.json`](../research_specs/weekly-passive-first-v1.json)

## 매주 무엇이 나오는가

한국(`069500.KS` KODEX 200)과 미국(`SPY`) 각각에 대해, 서로 독립적으로:

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
- 그 지역의 데이터가 마지막 완료 거래일보다 오래되면 새 판단을 내지 않고(`STALE_DATA_NO_NEW_DECISION`) 직전 확정 판단을 실제 기준일과 함께 보여 줍니다.
- 주중 실행은 `INTRA_WEEK_PREVIEW`(미리보기)로 표시되며 영수증으로 기록되지 않습니다. 주의 마지막 거래일 데이터로 만든 판단만 `FINAL_WEEKLY` 영수증이 됩니다.

## 파이프라인

```
ledger.yml (매일 00:10 UTC)
  python -m pipeline.build → pipeline.validate → scripts/update_ledger.py (기존)
  python -m pipeline.weekly_publish (추가, 실패해도 페이퍼 원장은 계속)
    → signal-history: ledger/weekly-decisions/latest.json   (사이트가 읽는 현재 판단)
    → signal-history: ledger/weekly-decisions/receipts.jsonl (추가 전용 영수증)
사이트(app.js) → data/weekly-decision.json(있으면) 또는
  raw.githubusercontent.com/<owner>/<repo>/signal-history/ledger/weekly-decisions/latest.json
```

`pages.yml`, `pipeline/build.py`, `pipeline/validate.py`, 워크플로 인벤토리 문서·테스트는 봉인 연구
(alpha-opportunity-model-v1, kr-alpha-atlas Phase C v1–v4)가 바이트 해시로 고정하므로 수정하지 않았고,
새 워크플로 파일도 추가하지 않았습니다. 그래서 판단은 Pages 산출물이 아니라 공개 signal-history 브랜치에서 읽습니다.

## 안전 규칙

- 원본 site-data가 차단(`recommendationsBlocked`)·seed·synthetic·stale이면 두 지역 모두 `BLOCKED`, 종목·비중 없음.
- 영수증 식별자 = (정책 버전, 지역, 기준일). 같은 식별자로 내용이 다른 판단이 오면 첫 기록을 유지하고 나중 것을 거부합니다.
- 종목 매매·알림 발송은 하지 않습니다. 영수증은 향후 알림에 쓸 수 있는 형태로만 저장합니다.
- 실시간 검증(`liveValidated`)은 어떤 경우에도 자동으로 켜지지 않습니다.

## 수동 실행

Actions → **Append paper-signal ledger** → Run workflow. 판단 단계가 검증에 실패하면 경고만 남기고 아무것도 쓰지 않으며,
페이퍼 원장 기록은 그대로 진행됩니다.
