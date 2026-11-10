# PR 정리 등록부 — 2026-11-10

실제 GitHub 시작 상태는 열린 PR17개, main 37f8cbf6b1c066f6b3c65235953648d17ebf2f69다. 전체 SHA/base/CI run/변경 파일은 github-inventory-initial.json에 있다. KEEP은 독립적으로 필요한 변경이며 병합 승인이나 독립 성과 인증은 아니다.

| PR | 판정 | 확인 HEAD | 의존·근거·조치 |
|---|---|---|---|
| [#299](https://github.com/jaehojung1879-netizen/Investment/pull/299) | KEEP | 4d7fbbd83afb | 고정 연구 UI; #307의 기반 |
| [#306](https://github.com/jaehojung1879-netizen/Investment/pull/306) | KEEP | 49e35ace1cd3 | 고유 shadow/readout 코드·결과; #314의 기반 |
| [#307](https://github.com/jaehojung1879-netizen/Investment/pull/307) | KEEP | 03a72544c513 | #299 이후 저장 성과 표시 |
| [#314](https://github.com/jaehojung1879-netizen/Investment/pull/314) | KEEP | 26a40921aced | #306 이후 일일 판단·기준일 결함 수정 |
| [#315](https://github.com/jaehojung1879-netizen/Investment/pull/315) | CLOSE | 23522002dcd2 | #321 cd2892eb가 23522002를 완전히 포함. #321 base를 main으로 전환 후 대체 댓글과 종료; 브랜치 보존 |
| [#316](https://github.com/jaehojung1879-netizen/Investment/pull/316) | HOLD | 75aab7bc7096 | 고유 등록·결과와 #325의 기반. 실행·독립 감사 경계 유지 |
| [#317](https://github.com/jaehojung1879-netizen/Investment/pull/317) | KEEP | a3ee7a716e56 | KR/US 원천·종결자료의 고유 증거. 별도 리뷰 경계 |
| [#318](https://github.com/jaehojung1879-netizen/Investment/pull/318) | HOLD | 9d2c93a0e9a9 | 고유 preflight/합성 영수증. 정정 원천·독립 검증 대기 |
| [#319](https://github.com/jaehojung1879-netizen/Investment/pull/319) | HOLD | a5bca7c16425 | 고유 우선순위/검정력 정의. 역사 재개 권한 아님 |
| [#320](https://github.com/jaehojung1879-netizen/Investment/pull/320) | HOLD | 9a47f478a407 | KR 스택 기반·기존 등록/LIVE 승인 근거 보존 |
| [#321](https://github.com/jaehojung1879-netizen/Investment/pull/321) | KEEP | cd2892eb6d66 | Pages/CI 독립 운영 정비; #315 완전 포함; Tests/Pages 성공 이력 |
| [#322](https://github.com/jaehojung1879-netizen/Investment/pull/322) | HOLD | f3b1aa9d75fc | #320 이후 경제 입력·봉인 결과 기반; v1 경로 보존 |
| [#323](https://github.com/jaehojung1879-netizen/Investment/pull/323) | CLOSE | 4349aa26fd45 | 변경 문서 두 파일을 정확 바이트로 통합 PR에 흡수; root AGENTS 보존 |
| [#324](https://github.com/jaehojung1879-netizen/Investment/pull/324) | KEEP | d96c11bbc53a | KRX 수집 무결성·경제 원천 보완. 독립 운영 경계 |
| [#325](https://github.com/jaehojung1879-netizen/Investment/pull/325) | HOLD | 9dc2928d3c21 | C2 독립 재감사 미완료. 본문 NOT EXECUTED로 실행권 판단 금지. 역사 실행 금지 |
| [#326](https://github.com/jaehojung1879-netizen/Investment/pull/326) | HOLD | ba414836a3d7 | DO NOT MERGE 실행 경로 증거. 병합·재실행·잠금 삭제 금지 |
| [#327](https://github.com/jaehojung1879-netizen/Investment/pull/327) | HOLD | 1e0289d09ba3 | 최신 1e0289d0 인수. 역사 결과·사양 유지; v2는 새 통합 PR |

정리 완료: 새 통합 PR #328 공개 뒤 #315/#323을 대체 댓글과 함께 닫았고 #321 base를 main으로 전환했다. 실제 state/댓글 링크는 pr-cleanup-result.json과 PR Conversation에 있다. 다른15개 원본 PR과 원격 브랜치는 보존했으며 신규 #328을 포함해 열린 PR은16개다.

의존: #320→#322→#327→새 통합 PR. #315를 포함한 #321은 main 기준의 독립 Pages/CI PR로 정리한다. #325는 #316 위의 보호 작업, #326은 병합 대상 아님. UI는 #299→#307, #306→#314를 유지한다. 독립 보호 연구·운영 변경을 하나의 diff에 억지로 합치지 않는다.

CI: #321은 Tests/Pages 성공 이력이 있다. KR 스택의 알려진 실패는 일반 CI의 수치 라이브러리 드리프트다. 관련 테스트도 봉인된 추가 의존성이므로 원본 바이트로 유지했다. 이미 준비된 #321 경로를 사용하며 테스트·워크플로·등록 런타임을 완화하지 않는다. 새 통합 PR의 정확 HEAD CI 결과는 별도로 보고한다.

역사 실행·기존 C2·LIVE·스케줄 설치·실제 매매·main push/자동 병합은 하지 않는다. 고유 자료가 있는 연구 PR을 숫자 축소 목적으로 닫지 않는다.
