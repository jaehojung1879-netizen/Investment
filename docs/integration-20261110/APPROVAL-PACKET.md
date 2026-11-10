# Owner 승인 패킷 — 미실행

현재 역사 정정은 SOURCE_BLOCKED, 전향 기록은 미승인·외부 설치 미확인이다. 이 문서는 승인 파일이 아니다. 이전 승인 문구를 재사용하지 않는다.

| 대상 | 정확 SHA-256 | 상태 |
|---|---|---|
| spec-v2.json | 2a73e28a4b837e828a50becd8e4d668b346ef772816b333589062af4b303ecf3 | 코드/합성 검증 준비, LIVE 미시작 |
| execution-packet-v2.json | 742fb6d764a405b7ce27db15bf981916388f1376a32749e7df557d75d2507394 | 원천 결측으로 실행 승인 불가 |

원래 A1/B1 전향 코드 23개 고정은 모두 일치한다. 원래 broad-alpha 결과·계약·claim·코드와 v1 사양도 보존했다.

**현재 Owner 결정은 병합 순서 확인 한 건으로 모은다:** #321의 검증된 Pages/CI 운영 정비를 먼저 수동 검토·병합하고, 이후 KR 의존 스택과 통합 PR의 정확 HEAD CI를 확인한다. 이 작업은 main 병합이나 자동 병합을 하지 않는다. CI·원천 BLOCKED를 승인으로 우회하지 않는다.

LIVE 운영 조건을 갖춘 뒤 사용할 정확 문구:

APPROVE KR_CAPITAL_EVENT_PROSPECTIVE_V2 2a73e28a4b837e828a50becd8e4d668b346ef772816b333589062af4b303ecf3 RECORDING_ONLY

이는 매매·역사 평가·다른 LIVE 연구 변경을 승인하지 않는다. 공개 Owner 승인 댓글의 ID/본문SHA/게시시각, 위 사양SHA, PROSPECTIVE_RECORDING_ONLY scope와 첫 적격 세션을 신규 AUTHORIZATION-v2-prospective-recording.json에 고정해 커밋해야 한다. 스케줄러·DART 자격증명·push 권한 확인 전에는 실행하지 않는다.

역사 원천이 완비되고 새 admission을 고정한 뒤 사용할 문구의 형식은 APPROVE KR_EVENT_CORRECTION_V2 <NEW_PACKET_SHA256>이다. 현재 해시를 실행 승인해 달라고 요청하지 않는다. admission이 바뀌면 해시와 승인을 새로 받아야 한다. 공식 회계연도·기업행동·종결대가·전체 C2 원장을 추정해 채우지 않는다.

역사·전향 승인 파일, 새 claim/실행 태그, LIVE 영수증, 예약 작업, 실제 매매를 만들지 않았다.
