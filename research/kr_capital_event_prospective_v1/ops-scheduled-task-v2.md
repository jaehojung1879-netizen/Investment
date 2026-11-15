# 전향 기록기 v2 운영 인수 — LIVE 승인·설치 전

코드와 합성 검증은 준비했지만 이 환경에는 외부 Claude 예약 작업을 생성/조회하는 도구가 없다. **설치 상태는 외부에서 확인되지 않아 BLOCKED**이고, 이 작업에서 예약을 설치하거나 LIVE 영수증을 쓰지 않았다. DART_API_KEY도 현재 환경에 없다. 이전 Claude의 실제 DRY_RUN 실행 성공 여부를 새로 인증한 것은 아니다.

기존 `spec-v1.json`은 그대로 보존한다. 현재 recorder의 기본 사양은 별도 `spec-v2.json`, 승인 파일은 `AUTHORIZATION-v2-prospective-recording.json`이다. 이전 승인 문구·파일을 재사용하지 않는다. 해시는 통합 패킷 `docs/integration-20261110/APPROVAL-PACKET.md`에서 확인한다.

Owner가 새 정확 해시로 기록만 승인하면 공개 Owner 계정의 승인 댓글ID/본문SHA/게시시각을 승인 파일에 고정한다. 댓글에는 다음 정확한 한 줄이 있어야 한다:

`APPROVE KR_CAPITAL_EVENT_PROSPECTIVE_V2 <SPEC_V2_SHA256> RECORDING_ONLY`

승인 파일은 `scope=PROSPECTIVE_RECORDING_ONLY`, studyId, specSha256, authorizedAtUtc(댓글 게시시각), firstEligibleSignalSession, approvalCommentId, approvalCommentSha256를 담아 커밋해야 한다. 첫 신호는 승인일의 한국 날짜 다음 KR 세션이다. 등록 파일만 임의로 만들어서는 LIVE를 통과하지 못한다. GitHub 계정 출처 검증은 계정 뒤의 인간을 암호학적으로 인증한다는 뜻은 아니며 명시적 Owner 지시가 여전히 필요하다.

외부 운영자가 실제 스케줄러를 사용할 수 있을 때 확인할 절차:

1. 승인 파일이 포함된 정확한 코드 커밋과 승인된 사양·전체 코드 closure를 확인한다. 새 전용 임시 경로를 `mktemp -d`로 만들고 그 경로에만 detached code worktree를 생성한다. 기존 `/tmp/kr-capital-event-code`나 다른 worktree를 삭제/강제 정리하지 않는다.
2. 같은 커밋에서 의존성을 설치하고 DART 자격증명 및 이 저장소의 signal-history push 권한을 확인한다. 값은 로그에 출력하지 않는다. 날짜를 지정한 DRY_RUN은 마커가 있는 저장소 밖 경로만 사용하며 실제 LIVE 원장과 섞지 않는다.
3. 평일19:45 KST 새 세션에서 `python -m research.kr_capital_event_prospective_v1.recorder --mode LIVE`를 실행한다. LIVE는 날짜 인자를 거부하고 시스템 시각을 사용한다. 이 문서는 설치 성공의 증거가 아니다.
4. 새 원장만 add/commit하고 비강제 push한다. 이동한 원격은 최대5회 fetch/rebase하며 충돌 시 중단한다. 원격의 모든 행 해시와 해당 신호일의 유일한 해시를 다시 확인한다. 재시도 전과 read-back 후에도 기한을 확인한다.
5. PushNotification·마지막 실행 시각·exit code·remote MATCH·missedSessions가 실제 운영 화면에 기록되는지 첫 유효 실행으로 확인한다. 실패·늦은 공개·누락 세션을 소급 보완하지 않는다. 네트워크가 기한 뒤 완료돼 물리적으로 원격 행이 존재하더라도 전향 적격성으로 인정하지 않는다.
6. 자신이 생성한 임시 worktree만 제거한다. 이전 작업·다른 연구 원장·브랜치·등록·잠금은 변경하지 않는다.

GitHub Actions 봉인 워크플로를 편집해 외부 스케줄러 부재를 우회하지 않는다. 후보 기록은 수익률·매매가 아니며 책은 개별주0, ETF100%, 현금0이다. 회계연도 미확정·기준일 이동 사례는 매수 사건으로 추정하지 않는다. 60개 성숙 사건 이전 outcome 열람·평가 실행은 별도이며 이번 인수에서 하지 않았다.
