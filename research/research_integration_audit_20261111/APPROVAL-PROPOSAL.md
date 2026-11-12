# Owner가 검토할 운영·통합 결정 — 미승인/미실행

이 문서는 승인 요청을 외부에 전송하거나 권한을 부여하지 않는다. 현재 지시는 기존 PR/main/workflow/production/봉인/소비된 lock의 변경·병합을 금지한다. 아래는 이후 Owner가 선택할 수 있는 정확한 범위다.

## 결정 1: #321 운영 복구

- 대상 HEAD: `cd2892eb6d6623c2527eeda690959d18839acc4d`, 현재 main/base: `37f8cbf6b1c066f6b3c65235953648d17ebf2f69`.
- 방식: draft 해제와 필요한 review/check 이후 **plain merge**. squash/rebase/과거 객체 정리 없이 parent `23522002dcd2d9e0e16dfb9d325a235aef664f0c`, reference main, consumed tag/object를 보존한다. 현재 HEAD가 바뀌면 이 검토를 자동 승계하지 않는다.
- exact maintenance record: `docs/operations/pages-yml-maintenance-2.json` 및 sidecar. 현재 Pages SHA `112196a5a53123eae00d8f3ba5d6c15cd109263cbd43ecd1c26869c19bfd0371`, Tests SHA `91e4f2dd587f6cc1a7a1cd0c41f04dcd03c97a4b2af0b6f904fdb1ad2b947124`.
- 포함 범위: 일반 설치 constraints(threadpoolctl3.7.0/joblib1.6.0), closed provenance 진단, 정상 Pages의 deploy 후 state/latest 단일 경로 게시. 종속성 두 줄만의 승인이라고 표현하지 않는다.
- 제외 범위: 투자전략/가중치/허용오차/원래 formal runtime 변경, consumed lock 재사용·해제, 새 역사 실행, 전향 writer 활성화, #328 전체 선행 연구의 동시 병합.
- 승인 후 수용 조건: 새 main 전체 Tests와 production validation→Pages deploy→state publish 성공; marketAsOf/generatedAt 비퇴행; signal-history state/latest 외 tree 보존; 정상 concurrent ledger append 보존. 이는 현재 PR Pages의 diagnostic-only 녹색과 다르다.
- 검토 근거: exact HEAD 원격 Tests6521pass, 격리 운영/음성 테스트107pass, 보호235파일/Owner formal job/원래 requirements 불변. 최초 partial-clone 객체 부족 실패도 보존했다.

## 결정 2: 연구 결과 통합

결정1 이후 #329 작성자가 main을 merge하여 CI 재확인 → #329 plain merge → #330 base/main retarget와 merge-main/CI → #330 merge → #332 동일 처리. 원 17404f86·8657acd5·0f39c2fe와 결과 바이트는 조상/원본으로 유지한다. 새 Adaptive 감사 범위는 이번 통합 보고서로 명시하며 과거 #330을 소급 확대하지 않는다.

#331은 결정1 이후 독립 경로다. FX·twin·지표·배분 생성일 errata를 출처에 연결한 다음 CI/review로 판단한다. #328은 main 대비218파일과 전향 기록기 범위가 별도이므로 새 승인 없이 포함하지 않는다. #332의 vendor 세 파일을 재사용하는 데 #328 전체 병합은 필요하지 않다.

## 결정 3: 게시/전향은 별도

②는 NOT_SUBMITTED다. REPORT F의 네 타입과 실제 시점/차단 계약에 대한 별도 웹 구현·게시 범위를 먼저 승인한다. 오래된 배분은 현재 추천이 아니며, 과거 탐색·정정 현금·SOURCE_BLOCKED를 합산하지 않는다.

6~12개월 무자금 전향 기록은 REPORT J의 기존 후보·목적·비용/리밸런스·타임스탬프·append-only 사양을 먼저 고정하고 별도 활성화 승인을 받는다. #321 merge나 이 감사 PR의 승인은 그 활성화 승인이 아니다. 과거 전체 경제성이 끝내 미인증이어도 새 기록은 별도 프로그램으로 시작할 수 있다.
