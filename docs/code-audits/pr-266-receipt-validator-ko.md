# PR #266 Track C preview 검증기 독립 감사

대상 HEAD: `bd86901d12168a4ada40e6d0f075e9d9953b2538`.
기존 `claude/rp1-c-kr-risk-state-receipt-preview` 브랜치에만 수정한다.

## 재현한 결함

기존 검증기는 multiplier의 허용 집합과 digest만 확인하고, 받은 layers에서
그 배율을 독립 재계산하지 않았다. 따라서 digest를 다시 계산할 수 있는
상위 코드나 외부 입력은 모델과 불일치하는 preview도 통과시킬 수 있었다.
다음 회귀 테스트를 **수정 전에 실행해 3 failed / 6 passed**를 확인했다.

- C0를 다른 허용 배율로 변경하고 digest 재계산.
- 유효한 FAST 상태를 변경하되 multipliers는 그대로 두고 digest 재계산.
- 결측 결과가 있는데 undeterminedCandidates를 비우고 digest 재계산.

세 경우 모두 `DID NOT RAISE`로 실패했다. 기존 6개 테스트는 통과했다.

## 수정

- 외부 receipt는 객체, 정확한 v1 필드 집합, 정수 schemaVersion, 고정 studyId /
  modelVersion / evidenceClass / region, `ledgerWritten is False`를 요구한다.
- signalDate는 정규 `YYYY-MM-DD` 문자열이며 기존 KR 달력의 주간 의사결정
  세션이어야 한다. timestamp·숫자·휴장일·비주간일·달력 밖 날짜는 거절한다.
  금요일이 휴장인 경우 목요일이 의사결정일일 수 있어 요일로 대체하지 않는다.
- layers 키를 정확히 검사하고 각 값을 봉인된 `K.STATE_VALUES` 도메인과 대조한다.
  None만 명시적 결측이며 bool·문자·컨테이너·분수·NaN·무한대·범위 밖 숫자는 거절한다.
- `K.multiplier()` 자체를 C0~C3 각각에 호출한다. 허용 배율 집합 소속만으로
  통과시키지 않고 받은 multipliers가 재계산 결과와 정확히 같은지 확인한다.
- undeterminedCandidates는 재계산 결과가 None인 후보의 고정 순서 목록과
  정확히 같아야 한다. 누락·중복·추가·잘못된 순서를 거절한다.
- 비정상 JSON 자료형과 비정상 digest는 ValueError로 거절한다. bool은 숫자
  0/1과 같게 비교되는 Python 동작에 기대지 않는다. 오차 허용 비교도 하지 않는다.
- 정상 builder의 NaN→None·정수형 상태 정규화, 필드와 출력 스키마는 유지한다.
  잘못된 bool·컨테이너 등의 builder 상태 입력도 명확히 거절한다.

검증은 receipt를 수정하지 않으며 builder를 호출해 자신을 검증하지 않는다.
봉인된 모델 규칙·임계값·LEVELS, 공통 calendar/core, US C1, 다른 연구 PR,
실행 경로·ledger·workflow·보호 규칙은 변경하지 않는다.

## 합성 검증

Focused: **351 passed (17.55초)**; Ruff와 pipeline compileall 통과.

- 완전 관측 12개 + 결측 포함 총 36개 상태 조합을 외부 JSON으로 검증.
- 각 상태×C0~C3에서 다른 허용 배율 또는 None으로 바꾸고 재서명해 거절 확인.
- SLOW·TRANSITION·FAST 각각의 유효 도메인 내 변조와 domain/type 위반을 검증.
- 모든 상태 조합의 잘못된 None 후보 목록 및 개별 필수 필드 누락 검증.
- 잘못된 버전·신원·날짜·bool·문자·컨테이너·NaN·무한대·거대 정수 검증.
- 지정 HEAD의 정상 builder와 모든 36개 상태의 canonical 출력이 바이트 단위로 동일함을 확인.
- validator가 builder에 위임하지 않고 봉인된 multiplier를 네 번 직접 호출하는지 확인.

```sh
.venv/bin/python -m pytest -q tests/test_rp1_c_risk_state_receipt.py
.venv/bin/ruff check .
.venv/bin/python -m compileall -q pipeline
```

전체 CI는 최종 커밋에서 기존 Tests 조건(Python 3.11, pinned requirements,
BLAS/OMP thread=1, 전체 pytest, entry-point import/script compile)으로 별도 실행한다.
기존 workflow의 60분 예산을 늘리지 않는다. 완료/실패/timeout과 GitHub 호스팅
상태는 focused 결과와 구분해 최종 보고한다. 전체 결과는 이 문서의 focused
통과 숫자로 대체하지 않는다. GitHub API가 proxy Forbidden이므로 호스팅
check 조회와 댓글 게시가 막힌 경우에도 성공으로 추정하지 않는다.

## 남은 위험과 병합 전 확인

Digest는 서명이 아니다. 상태·날짜·배율·결측 목록을 모두 모델과 일관되게
새로 구성한 자기일관적 입력의 관측 진위는 이 검증기로 증명할 수 없다.
이 수정은 **모델과 불일치하는 외부 입력**을 막으며 출처 인증을 추가하지 않는다.
PREVIEW는 실제 영수증이 아니고 관측 시각·세션 최종성·실행 승인·원장 기록 권한을
부여하지 않는다. None을 임의의 이전 보유 비중으로 대체하지 않는다.

병합 전 owner/reviewer는 최종 head의 전체 Tests 상태, 고정 모델/타 연구 PR이
변경되지 않았음, 정상 출력 호환성 및 위 preview 한계를 확인해야 한다.
실제 자료 조회·수집·저장·성과 열람·역사 재실험·새 ledger 기록은 하지 않았다.
CI green은 과학적 승인·US C1 실행 승인·main 병합 승인이 아니다.
