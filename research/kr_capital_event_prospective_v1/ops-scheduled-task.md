# 예약 작업 절차 — kr-capital-event-prospective-v1 LIVE 기록

평일 19:45 KST, 매회 새 세션. `<REGISTERED_COMMIT>`은 승인 파일이 들어간 커밋이다. 첫 실패에서 멈춘다.

1. 저장소가 없으면 add_repo(jaehojung1879-netizen/Investment, push) 후 clone, register_repo_root. `pip install -q -r requirements.txt`. `echo ${DART_API_KEY:+set}`이 set이 아니면 실패.
2. `git fetch -q origin claude/trusting-tesla-ob0jym && rm -rf /tmp/kr-capital-event-code && git worktree prune && git worktree add --detach /tmp/kr-capital-event-code <REGISTERED_COMMIT>`
3. `cd /tmp/kr-capital-event-code && python -m research.kr_capital_event_prospective_v1.recorder --mode LIVE` 의 JSON 한 줄을 보관한다.
4. `cd /home/user/Investment && git worktree remove --force /tmp/kr-capital-event-code; git worktree prune`
5. 결과를 한국어 한 문장으로 보고한다: RECORDED(remote MATCH) / ALREADY_RECORDED / NO_RECEIPT_DUE(휴장일만 정상). `missedSessions`가 비어 있지 않으면 그대로 보고한다.
6. 3단계가 0이 아닌 코드로 끝나면 정확한 오류를 PushNotification으로 보내고 멈춘다.

금지: 영수증 수정·날짜 변경·소급 작성, 수익률·가격·NAV·outcome 열람, 등록 커밋·사양·승인 변경, `kr-corporate-information-events-v1` 원장·코드 접근.
