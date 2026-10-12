# US cash profitability H63 P4 — 수동 일회 실행 운영 절차

**휴면 infrastructure다. 실행·승인 발급·원격 lock 생성은 하지 않았다.**
시작 main `3c0f4794ae6e86cde395025a738759e6dc35f053`, Tests CI 성공.
기존 P4 정의·P3 보정·preflight/readiness·역사 입력은 그대로 보존한다.
692개 성숙·정의 코호트, 163개 작은 단면 날짜, 212개 이탈 식별자 가격 부재는
기존 outcome-free 보고서의 제약이다. 최근 총자산 소스 문제는 P4 gate에 추가하지 않는다.

## 실행 경로와 잠금

봉인된 workflow census·inventory를 바꾸지 않기 위해 기존 수동 전용
`kr-corporate-action-collection.yml`에 별도 `us-p4` job을 추가했다.
기존 기본값과 KR job의 원래 steps는 보존한다. `us_p4_action=none` 또는 구형
입력의 빈 값이면 기존 동작, `validate/execute`이면 **모든 KR job을 제외**한다.
새 workflow 이름을 등록하려고 frozen inventory/검증 테스트를 수정하지 않았다.
P4 route는 workflow_dispatch + main만 허용한다. PR·schedule trigger는 없다.
기존 workflow 이름의 Actions 메뉴를 사용한다는 운영상 제약은 명시적으로 남긴다.

순서: owner dispatch·현재 main·커밋된 승인 → 정확한 데이터/코드/보정 hash →
미사용 lock 확인 → 원격 단일 study ref의 atomic POST → 원격 lock·main 재확인 →
원래 CLI의 데이터 적재·코호트 구성 → guarded forward reader → 원래 P4 계산.
데이터 패널 적재 자체도 lock 뒤다. Python source/requirements와 tracked research
JSON metadata, 원본 replay manifest bytes, 모든 replay object와 fundamentals blob의
집계 SHA를 다시 계산한다. 승인·acceptance 자체는 순환 hash에서 제외하고 별도
exact SHA로 고정한다. 커밋된 P4 결과가 이미 있으면 읽지 않고 새 실행을 거부한다. lock 전에는 Git blob/압축 해제 raw bytes의
SHA 검증만 하며 price JSON을 파싱하거나 수익률을 만들지 않는다.

고정 ref는 `refs/tags/us-cash-profitability-signal-v1-exploratory-lock`이다.
기존 GitHub `/git/matching-refs` GET + `/git/refs` POST conventions를 재사용한다.
contents:write token으로 **exact study ref 하나를 최초 생성**한다. 버전별 다른
ref로 예산을 우회하지 않고 prefix 아래 어떤 ref가 있어도 거부한다.
concurrency는 study 그룹, cancel-in-progress:false지만 exactly-once는 atomic ref 생성이 보장한다.
실행 코드는 PATCH/DELETE/force-push를 제공하지 않는다. POST 성공 여부가 불명확하거나
확인 실패여도 원격 상태를 owner가 검증하기 전 재시도하지 않는다. 생성 뒤 실패는 영구 소비다.
workflow rerun attempt>1도 거부한다. API/태그 ruleset이 생성 자체를 금지하면
outcome reader는 0회이며 owner가 저장소 tag 권한을 검토해야 한다.

remote main은 승인·lock 직전·lock 확인 뒤·forward reader 직전에 확인한다.
GitHub에는 서로 다른 두 ref를 함께 CAS하는 API가 없으므로 owner는 실행 중 main을
변경하지 않아야 한다. 확인 사이 main이 이동하면 lock을 소비한 채 중단할 수 있다.
잠금은 태그를 삭제할 권한이 있는 관리자까지 막는 서명이 아니므로 해당 ref의
삭제/갱신 제한을 owner가 운영 규칙/ruleset으로 보호해야 한다.

## 보충 calibration 연결 계약

Claude의 unmerged branch는 읽거나 의존하지 않는다. 현재 P3 결과를 최종 보충
결과로 하드코딩하지 않았다. 별도 **비승인 acceptance record**가 최종 결과·protocol
경로와 SHA, preflight SHA, 전체 verdict 및 geometry 증거의 JSON pointers를 고정한다.
실제 파일은 `docs/us-readiness/us-h63-supplemental-calibration-acceptance-v1.json`이며
이번 PR에는 없다. template은 accepted:false / authorizes:NOTHING이다.

전체 verdict는 top-level `/verdict`, `/overallVerdict`, `/status` 중 하나이며
PASS 또는 CALIBRATION_PASSED만 허용한다. 한 passing cell을 전체 통과로 선택할 수 없다.
추가 proof는 H63, CT_SN, frozen critical 28.31, 최소 150 이하·최대 244 이상의
평가 범위, 163개 미보정 날짜의 연결, 실제 historical outcome reads=0을 확인한다.
proofPointers 값은 문자열(pointer, result에서 읽음) 또는
`{"source":"result|protocol|preflight","pointer":"/actual/field"}`다.
preflight source는 underCalibratedDates에만 사용할 수 있다.
결과/프로토콜의 실제 스키마·전체 판정·geometry 의미는 Claude merge 후 리뷰해야 한다.
실제 결과가 주장하는 protocol identity와 producer Python 파일 해시도 현재 커밋과
일치해야 한다. protocolIdentityPointer는 raw 파일 또는 canonical JSON SHA를 가리키며
protocolIdentityKind로 구분한다. producerCodePointers는 원래 producer가 선언한
모든 코드 경로→실제 result SHA pointer를 owner가 리뷰해 명시한다(비어 있으면 차단).
새 결과가 이 gate 계약과 맞지 않으면 승인·실행을 차단하며 작은 adapter 계약 조정을
먼저 리뷰한다. 실패·INCONCLUSIVE·미정·hash mismatch를 acceptance로 우회할 수 없다.
미래 SHA나 판정은 template에 채우지 않았다.

## Owner 작업 순서

1. Claude의 보충 보정 PR을 먼저 리뷰·병합한다. 전체 primary CT_SN 판정과
   150–244 names/date 평가, 163개 날짜의 geometry 연결을 확인한다.
2. 이 infrastructure PR을 그 main에 rebase/merge한다. 병합 충돌을 해결하고
   focused/full CI, 원래 P4 정의·봉인 hash·workflow census 보존을 확인한다.
3. 최종 calibration 스키마·SHA와 code identity를 확인하고 acceptance template을
   실제 acceptance 경로로 작성·커밋한다. 이는 실행 승인이 아니다.
4. **명시적으로 owner 승인을 요청하고 얻는다.** 결과 노출 역사에 대한 탐색,
   생존 조건부 표본과 212개 가격 부재, snapshot/ID 한계, 최종 보정 정체성,
   정확한 데이터·통계·코드 hash, 실패 후에도 소비되는 일회 예산, ABANDON 또는
   CONTINUE_TO_PROSPECTIVE_REGISTRATION_REVIEW 한정 해석을 승인 범위로 제시한다.
5. 최종 병합 main의 checkout에서 pinned input Git commit을 확보한 후
   `python scripts/run_us_p4_owner_gated.py pins --work /tmp/us-p4-candidate-pins`로
   hash를 계산한다. raw price bytes를 검증하지만 forward reader/실험/lock은 호출하지 않는다.
   non-authorizing owner template을 실제 `us-cash-profitability-exploratory-authorization-v1.json`
   경로로 작성하고 exact pinnedIdentities/executionPins, 실제 ownerLogin과 승인된
   acknowledgment를 넣어 커밋한다. **이번 PR의 template은 승인 파일이 아니다.**
   `sha256sum docs/us-readiness/us-cash-profitability-exploratory-authorization-v1.json`을
   별도 owner 리뷰한 dispatch 입력으로 등록한다. 승인은 working tree가 아닌 HEAD에 있어야 한다.
6. repo owner가 현재 merged main에서 **한 번** dispatch한다.
   `gh workflow run kr-corporate-action-collection.yml --ref main -f us_p4_action=execute -f us_p4_authorization_sha256=OWNER_REVIEWED_SHA256`
   필요 시 그 전에 `us_p4_action=validate`로 같은 gate를 검증한다(lock/outcome 없음).
   실행 중 merge/main 갱신을 중지한다. attempt/result artifact를 반드시 보존한다.
7. artifact의 attempt.json·result.json·authorization SHA·input/code/calibration pins·원격
   lock target과 outcome reader counter를 검증하고 **별도 리뷰 PR**로 exact bytes를 seal한다.
   장애·타임아웃·artifact 손실도 재실행 사유가 아니다. 이미 작성된 바이트 복구만 검토한다.
   artifact는 90일 만료이므로 별도 승인된 장기 보존 위치로 옮긴다.
8. 원래 P4의 ABANDON_BEFORE_PROSPECTIVE_COLLECTION은 운영 보고에서 ABANDON으로
   요약한다. CONTINUE는 전향 등록 리뷰로 갈 근거일 뿐 확증·live 채택이 아니다.
   NOT_EVALUABLE은 기술적 불가/진단 상태로 남기며 두 긍정적 선택 중 하나로 바꾸지 않는다.

이번 PR은 원래 `scripts/run_us_cash_profitability_exploratory.py.execute`를 호출하는
orchestration일 뿐 새 연구 엔진이 아니다. 결과 artifact 자동 업로드만 하며
result commit/seal, signal-history, 전략 추천·portfolio 승격을 구현하지 않는다.
실제 보충 evidence·acceptance·owner 승인·원격 tag 권한은 모두 아직 미확인/미발급이다.
새 테스트는 synthetic JSON, mock reader, local/bare Git만 사용한다.


### 권한 확인과 보장 범위

이번 작업에서 matching-refs GET으로 해당 US study prefix의 원격 ref가 0개임을
확인했으며 생성하지 않았다. 현재 rulesets 목록은 비어 있었다. Actions 기본
workflow permissions API는 integration 접근 403으로 읽지 못했으므로 실제
실행 token/tag 정책은 **owner 확인이 필요**하다. job의 contents:write 선언과
기존 one-shot POST 패턴은 호환되지만 허가 성공을 실제 태그 생성으로 시험하지 않았다.
원래 P4 CLI는 로컬 승인만 검사하는 기존 코드이므로 **직접 execute하지 않는다**.
이 PR의 exactly-once 보장은 새 orchestration 경로에 대한 것이며 임의 Python 실행이나
owner의 태그 삭제를 막는 전역 보안 경계가 아니다. 전역 reader 정책 변경이 필요하면
frozen harness 수정이 필요하므로 이번 작업에서는 그 부분을 진행하지 않는다.
