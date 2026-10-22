# Weekly Decision Session Integrity v1

이 변경은 세션 안전성 수정안이다. 배포·워크플로 실행·원장 수정·정책 비중 변경을 하지 않는다.
기준 main `002b56434e3aa3e845798ec2ea7ca6d9267e3f7a`.

## 재현한 결함

`signal-history` 커밋 `1bf68f59cffa20239977e2cfaa0f35a07d0ec884`의
`ledger/weekly-decisions/receipts.jsonl`을 읽었다. 3개 final 중 다음 1개가 미완료 세션을 사용했다.

| 필드 | 보존된 값 |
|---|---|
| receiptId | `weekly-passive-first-v1\|KR\|2026-10-16` |
| generatedAt | `2026-10-16T04:44:48.202397+00:00` = 13:44:48 KST |
| expectedSession | `2026-10-15` |
| observedSession / weekStatus | `2026-10-16` / `FINAL_WEEKLY` |
| digest | `6016869578c3eb89202b658222f233adbc2974e1ea1898fd76c2542c35d90138` |

`freshness`는 `observed < expected`만 검사했다. 그러므로 미래 날짜도 FRESH였고,
`is_week_end_session`은 다음 세션이 다음 ISO 주에 있다는 사실만으로 열린 금요일을 final로 만들었다.
`weekly_publish.validate`와 append 단계에도 별도 세션 검증이 없었다.
`indices`는 Yahoo/FDR 등 일봉의 인덱스를 날짜로 정규화하고 마지막 행을 `asOf`로 노출한다.
당일 행이 있다는 사실은 종가 확정 증거가 아니다. 원 공급자의 당시 응답/취득 로그가 없어
어느 공급자가 미완료 행을 보냈는지는 확정하지 않는다. 공급자 날짜를 완료 시각으로 간주한 소비자 결함은 재현됐다.

## 수정 경계

- timezone-aware 생성 시각을 필수로 하며, 발행은 site `generatedAt`으로 재현한다. wall clock을 섞지 않는다.
- 기존 `replay_calendar.sessions`의 휴장일/추가 KRX 휴장일을 유지한다.
- XNYS의 실제 `session_close + 60분`: DST와 13시 조기 폐장도 반영한다.
- KRX는 schedule close + 60분과 기존 `prospective_receipt_core.KR_CLOSE_FINAL_UTC` 중 늦은 시각이다.
  즉 최소 **18:00 KST**다. 기존 16:30 KST보다 보수적으로 바뀌는 안전성 경계이며 선택 규칙 변경은 아니다.
  pinned exchange-calendars 4.11.1은 2025-11-13 수능일의 지연 마감을 담지 않은 것으로 회귀 테스트에서 확인됐다.
  이미 저장소가 채택한 18시 경계를 재사용해 미래 수능일 누락을 날짜 추정으로 보수하지 않는다.
- 공급자 날짜가 예상 완료일보다 미래면 휴장일 정규화 **이전**에 INVALID로 차단한다.
  과거 휴장일을 직전 세션에 매핑하는 기존 호환성은 유지하고 sourceDate를 남긴다.
  공급자별 날짜 의미가 검증되지 않은 신규 어댑터는 별도 admission이 필요하다.
- 예상일과 일치한 완료 세션만 새로운 판단을 만들며, 다음 거래일이 같은 주면 preview다.
- 후보 개별 시세도 완료된 기준 세션과 같아야 한다. 미래 날짜나 미래 휴일 날짜를 과거 세션으로
  정규화해 편입시키지 않는다. 불일치 후보는 기존 시세 부적격 코드로 제외한다.
- publisher와 append에도 원 생성 시각 기준 final 검증을 둔다. 과거 잘못된 final은 시간이 흘러도 유효해지지 않는다.

## 기존 기록의 영향과 정정 절차

10/16 기록은 정상 종가 기준의 주간 final 또는 전향 검증 증거로 사용할 수 없다.
해당 기록의 투자 성과·종목 선택은 이번 작업에서 평가하지 않았다. 원장은 삭제/편집하지 않았다.
10/08 KR 및 10/09 US의 다른 두 final은 세션 시각 검사를 통과한다.

읽기 전용 `receipt_session_error`가 `OBSERVATION_AFTER_COMPLETED_SESSION`을 반환한다.
새 발행물의 별도 `receiptIntegrity` 목록은 ID/digest/`INVALID_SESSION`/사유만 표시한다.
무효 기록은 `latest_final`, 이력, incumbent 기준에서 제외한다. 동일 ID의 유효 재계산이
무효 원본과 충돌하면 SOURCE_INCOMPLETE로 보이며 allocation과 새 영수증은 발행하지 않는다.
이 코드는 원본 digest나 내용, 이미 배포된 파일을 수정하지 않는다.

명시적 정정 원장은 **설계만** 한다. 후속 owner 검토에서 별도 append-only
`ledger/weekly-decisions/corrections.jsonl`에 `correctionId`, 원 `receiptId`/`digest`,
`status=INVALIDATED_SESSION`, 사유, 검토자, 승인 커밋과 UTC 기록시각을 추가한다.
유효 종가/공급자 vintage/생성시각 근거를 확보하지 못하면 `replacementStatus=UNRESOLVED`다.
replacement가 필요하면 새로운 correction ID와 원본 digest 참조를 사용하고 같은 receiptId를 덮지 않는다.
사후 재계산을 당시 전향 예측으로 바꾸지 않는다. sidecar writer·실제 correction·과거 산출물 재평가는
이번 PR에 없으며 별도 검토가 필요하다.

## 검증

신규 테스트는 합성 입력만 사용하며 역사 결과 reader를 stub한다. KR/US 금요일 장중,
마감/buffer 경계, DST, 미국 조기 폐장, 수능 지연일, 휴장일, 연말, 미래 휴일 날짜,
naive 시각, 원본 불변·중복 append, 무효 final 재발행 차단과 동일 입력 결정성을 확인한다.
기존 테스트의 휴장일 미래 날짜 허용 기대와 16:30 KST 기대는 안전성 계약에 맞게 수정했다.

전체 검사에서 UI PR의 두 바이트 불변 검사가 이번에 승인된 두 주간 파일 수정을 거부했다.
해당 검사만 `weekly-session-integrity-v1-pins.json`의 정확한 새 hash로 고정했다.
봉인 연구의 dependencyHashes, 기존 결과·사양 hash와 다른 production 파일의 검사는 유지한다.
별도 AST 비교가 비용·우위 추정·점수·선택·digest 함수 11개의 main 대비 동일성을 검증한다.

로컬 검증 환경: Python 3.12.14, requirements.txt와 requirements-dev.txt의 직접 의존성 pin.
전체 pytest 1회에서 5,064 passed / 1 skipped / 4 xfailed와 위 보호 검사 2개 실패를 확인했다.
보호 검사 수정 후 실패 범위 및 주간 회귀를 합친 최종 78개를 재검증했다.
ruff, compileall, /tmp의 합성 seed 생성·allow-seed 검증과 production 거부도 확인했다.
비용이 큰 전체 suite를 같은 이유로 다시 실행하지 않았다. 최종 PR의 기존 CI는 별도 결과다.

## 후속: 지연된 예약 실행의 게시 보류 (#273)

`Append paper-signal ledger`의 cron은 00:10 UTC지만, 2026-10-11 이후 실제 시작은 04:30~07:00 UTC
(13:30~16:00 KST)였다. 평일 빌드는 KRX 장중에 만들어져 `^KS11`·종목 시세에 미완성 당일 행이 들어간다.
기존 게이트는 이를 `OBSERVATION_AFTER_COMPLETED_SESSION`(INVALID)으로 정확히 거부했다. 그러나
그 결과를 `SOURCE_INCOMPLETE`로 게시해 마지막 정상 게시를 덮어썼다. 2026-10-21 실행이 재현 사례다
(expected 2026-10-20, observed 2026-10-21).

`weekly_publish.unfinished_sessions`는 지역 지수 행이 이미 개장했지만 아직 최종이 아닌 세션을 가리키는지
판정한다. KR 최종성 기준은 18:00 KST 그대로다. 해당하면 `main`은 이전 `latest.json`·receipts·
`publication-status.json`을 바이트 그대로 다시 내보낸다. 그래서 그 빌드에서는 아무것도 게시하거나 기록하지 않고,
최종성 이후 실행이 정상 게시한다.

- `freshness`·`build_from_site`·`validate`는 바꾸지 않았다.
- 휴장일 날짜 행·개장 전 당일 행·미래 날짜 행은 진행 중 세션이 아니므로 기존대로 INVALID다.
- 이전 게시 파일이 없으면 기존 거부 경로를 쓴다.
- 금요일 장중 빌드는 보류되어 조기 FINAL이 생기지 않는다. 주말 실행이 금요일 FINAL을 기록한다.
- 보류일에는 같은 실행의 연구 namespace(champion) 게시도 건너뛴다.
- `weekly_publish.py`의 새 hash만 pins 파일에 반영했다. `weekly_decision.py`, workflow, 연구 결과는 그대로다.
