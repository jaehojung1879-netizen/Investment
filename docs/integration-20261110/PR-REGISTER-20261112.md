# PR 정리 후속 등록부 — 2026-11-12

기존 [#328 등록부](https://github.com/jaehojung1879-netizen/Investment/blob/3b3edb13164ad38f8393c87432bb166f75068291/docs/integration-20261110/PR-REGISTER.md)의 단일 후속이다. #315/#323의 이전 종료 검증은 재사용했고 다시 조치하지 않았다. 새 연구/감사 PR은 만들지 않고 #335를 재사용했다.

**실적: 열린 23 → 17, 실제 종료6: #299 #306 #320 #322 #327 #330.** 후속 #307/#314/#328/#332는 HEAD 변경 없이 base를 main으로 전환했다. 모든 브랜치·태그·원본 커밋·토론·실행 잠금을 보존했다.

전체 제목·40자리 HEAD/base·원래 변경 규모·모든 변경 path와 blob SHA·main 누적 범위·ancestry·CI·승인·보존 조건은 [기계 판독 증거](../../audits/desk_preflight_20261111/consolidation-20261112.json.gz)에 있다. 아래 규모는 **정리 전 base 기준 파일수 / main 누적 파일수, +추가/−삭제 줄수**다. retarget 후 전체 범위와 혼동하지 않는다.

| PR·HEAD | 분류·규모 | 고유 역할·대체/후속 조치 | 승인·증거 경계 |
|---|---|---|---|
| [#299](https://github.com/jaehojung1879-netizen/Investment/pull/299) `4d7fbbd83afb` | SUPERSEDED_CLOSE<br>6/6 +375/−4 | 4개 원천 고정 연구 트랙·동일 renderer의 HTML/MD/JSON export<br>#307 인수; 35 Node 회귀 PASS. 6파일 모두 후속 확장; 원 네 트랙/6개 섹션 보존 | 읽기 전용; 독립 연구 원천 핀<br>과거 탐색·설계·차단 증거이며 새 알파 결과 아님 |
| [#306](https://github.com/jaehojung1879-netizen/Investment/pull/306) `49e35ace1cd3` | SUPERSEDED_CLOSE<br>54/54 +22073/−0 | entry-state shadow ledger와 economic readout 연결·두 장부 수정<br>#314 인수; 54파일 중51 동일, 3개는 검증/ETF 기준일/기존 장부 보존 확장 | 운영 ledger 스케줄 hook·전향 paper 쓰기는 #314에서 별도 승인<br>실제 0 fills/0 NAV 당시 기록·기존 개발/합성 결과 보존 |
| [#307](https://github.com/jaehojung1879-netizen/Investment/pull/307) `03a72544c513` | NEEDS_REPAIR<br>11/11 +357/−4 | 네 트랙 + 저장 비교12개/차단90개·통화/표본/비용 표시<br>#299 포함; #334와 app.js/index.html 충돌. 두 기능을 보존하는 최소 해소 후 결합 CI | 읽기 전용 UI; 게시 승인은 별도<br>새 연구 계산 없음; #305 저장 성과/미성숙/UNKNOWN 보존 |
| [#314](https://github.com/jaehojung1879-netizen/Investment/pull/314) `26a40921aced` | MERGE_CANDIDATE<br>11/62 +1219/−25 | 일일 브리핑의 현재 운영 판단·전향 paper 경로·ETF 기준일 수정<br>#306 포함; main base로 전환. 전체62파일·shadow hook 인수 범위로 재검토 | Owner의 main/Pages 및 전향 shadow-hook 활성화 승인·비저자 리뷰·exact CI 필요<br>과거/전향/실계좌 성과 분리; 실계좌 검증 없음·미축적은 UNKNOWN |
| [#316](https://github.com/jaehojung1879-netizen/Investment/pull/316) `75aab7bc7096` | KEEP_BLOCKED<br>595/595 +34494/−0 | master program·outcome-blind alpha evidence sprint<br>#325의 조상이지만 등록/실행 승인 경계와 광범위 원천 증거는 별도. #325가6개 파일 변경 | 등록·봉인·exact-hash 실행/독립 재감사 경계 유지<br>NO_EVIDENCE KR0/US0; 신규 역사 실행 없음 |
| [#317](https://github.com/jaehojung1879-netizen/Investment/pull/317) `a3ee7a716e56` | MERGE_CANDIDATE<br>34/34 +5835/−0 | KR/US 원천 복구·경제 비교 입력·퇴출/SEC 원천 증거<br>다른 열린 HEAD에 흡수되지 않은34파일. #321 이후 source review와 exact CI | 원천 admission 검토·Owner main/Pages 승인<br>실제 원천/coverage 증거; 전략 승격 아님 |
| [#318](https://github.com/jaehojung1879-netizen/Investment/pull/318) `9d2c93a0e9a9` | KEEP_BLOCKED<br>16/16 +4690/−0 | master integration adapters·합성 영수증·readiness<br>고유16파일; #328에0파일 흡수. 정정 원천/independent readiness 검증 대기 | 합성 성공을 실제 실행 승인으로 해석 금지<br>미실행 설계/합성 증거, 새 투자 성과 없음 |
| [#319](https://github.com/jaehojung1879-netizen/Investment/pull/319) `a5bca7c16425` | KEEP_BLOCKED<br>5/5 +792/−0 | 연구 우선순위 결정·outcome-free 검정력 계산<br>고유5파일(power.py·priority-decisions·회귀 포함); 다른 스택에 흡수되지 않음 | Owner의 실제 우선순위/원천 조건 대기; 역사 재개 권한 없음<br>미실행 우선순위와 계산; 동일한 보고서만 복제한 PR은 아님 |
| [#320](https://github.com/jaehojung1879-netizen/Investment/pull/320) `9a47f478a407` | SUPERSEDED_CLOSE<br>107/107 +46549/−0 | 한국 공시 사건 parser·원문/정정·원천 readiness<br>#328 인수; 107중102 동일. 나머지5는 공개된 ex-date 후보/receipt 정정 | 원문·기존 등록/승인·차단 상태를 ancestry와 원문 캐시에서 보존<br>고유 원천은 보존, 정정 후보를 DIRECT/PIT 인증으로 승격하지 않음 |
| [#321](https://github.com/jaehojung1879-netizen/Investment/pull/321) `cd2892eb6d66` | MERGE_CANDIDATE<br>29/29 +1777/−55 | 일반 CI pins + 기존 Pages state publisher + 봉인 read-only 진단<br>#315 포함. exact HEAD plain merge만 제안; Owner 승인 전 병합 금지 | A 의존성 / B deploy 후 state/latest 단일 경로 writer / C closed provenance 모두 승인 범위<br>새 연구 없음; consumed study 재실행·잠금 해제 없음 |
| [#322](https://github.com/jaehojung1879-netizen/Investment/pull/322) `f3b1aa9d75fc` | SUPERSEDED_CLOSE<br>58/160 +11728/−15 | A1/B1 historical harness·입력·봉인/승인 packet<br>#328에서 변경58파일 전부 동일 blob; 원 v1 경로와 SHA 유지 | 역사 실행·승인/소스 경계 보존<br>SOURCE_BLOCKED와 고정 historical evidence 보존 |
| [#324](https://github.com/jaehojung1879-netizen/Investment/pull/324) `d96c11bbc53a` | MERGE_CANDIDATE<br>16/16 +1269/−25 | KRX 수집기 무결성·경제 입력 qualification<br>고유16파일. #328에 같은 변경0개; 공통 수집기4경로는 서로 다른 blob | 수집 운영 영향·source review·Owner main/Pages 승인; 실제 수집/dispatch 미실행<br>원천 qualification, 새 역사 성과 아님 |
| [#325](https://github.com/jaehojung1879-netizen/Investment/pull/325) `9dc2928d3c21` | KEEP_BLOCKED<br>10/599 +1586/−94 | C2 fixed-exposure attribution·F1~F6 수리·exact packet<br>#316 포함이나 C2 독립 재감사/실행 경계는 별도. 제목 NOT EXECUTED로 권한 판단 금지 | 현재 annotated claim tag4944827a가9dc2928d를 가리킴. 재실행/삭제/잠금 해제 금지<br>준비/승인/claim 증거 보존; 이번 새 outcome 실행0; tag 존재를 성공 결과로 해석하지 않음 |
| [#326](https://github.com/jaehojung1879-netizen/Investment/pull/326) `ba414836a3d7` | KEEP_BLOCKED<br>1/1 +148/−1 | DO NOT MERGE branch-only C2 dispatcher 경로<br>어떤 PR에도 흡수되지 않은 workflow1파일; 검증 실패8건은 공통 pin 외 독자 원인 | 병합·dispatch·workflow 우회·consumed lock 해제 절대 금지<br>실행 경계 증거만 보존 |
| [#327](https://github.com/jaehojung1879-netizen/Investment/pull/327) `1e0289d09ba3` | SUPERSEDED_CLOSE<br>21/181 +11288/−0 | 실제 실행된 KR 사건 11개 책·historical outcome·전향 recorder<br>#328 인수; 21중18 동일. 변경3은 prospective recorder/테스트/설명; 결과/사양 불변 | 원 실행 결과/부정적 판정 보존; v2 활성화 별도<br>1차 지지0·INCONCLUSIVE/SOURCE_BLOCKED를 삭제하지 않음 |
| [#328](https://github.com/jaehojung1879-netizen/Investment/pull/328) `3b3edb13164a` | NEEDS_REPAIR<br>40/218 +7662/−27 | KR 주주수익 v2·공식 원천 정정·prospective recorder·이전 등록부<br>#320/#322/#327 포함, main대비218파일. identity 없는 CI rebase 실패를 fixture에서 수리 | 전체 스택 인수·source admission·v2 writer/Owner 승인 별도; 현재 비활성<br>실행 결과/원문 보존. #324·#317~319·ML/US 스택은 포함하지 않음 |
| [#329](https://github.com/jaehojung1879-netizen/Investment/pull/329) `0a1f49417157` | KEEP_BLOCKED<br>55/55 +127131/−0 | ML v1 탐색141개 + Adaptive macro/industry 연구<br>최신 Adaptive 추가분은 #332 조상이 아님. ML v1 subtree만 동일949478eb… | 원천/회계/통계 review·실패 판정 유지; 투자 승격 금지<br>탐색 ML 결과와 예측력/경제성 실패·위상 의존 후보 그대로 |
| [#330](https://github.com/jaehojung1879-netizen/Investment/pull/330) `8657acd5dd84` | SUPERSEDED_CLOSE<br>29/73 +18217/−0 | ML v1 독립 수익 경로 검산·원천/회계 FAIL<br>#332에서 감사29파일 전부 동일 blob. 감사 범위는 옛 #329 17404f86 | 닫힌 독립감사/FAIL 원문·SHA 보존; Adaptive 감사로 소급 확대 금지<br>독립 실패 증거가 회계 수리 결과와 함께 계속 남음 |
| [#331](https://github.com/jaehojung1879-netizen/Investment/pull/331) `49c3aa891b1e` | KEEP_BLOCKED<br>45/45 +10839/−0 | US Macro/Multi-Asset Track A·퇴출원천 Track B·FX errata<br>현재49c3aa89는 원래 결과를 유지하고 별도 errata5파일만 추가; #333 이후 delta 확인 | FX/PIT·동일위험/독립 가격 한계·외부 source review 대기<br>KRW no-look-ahead 철회와 USD 원래 결과·원시 원천 보존 |
| [#332](https://github.com/jaehojung1879-netizen/Investment/pull/332) `0f39c2fef93a` | KEEP_BLOCKED<br>95/168 +4412/−0 | ML v2 회계 정정·cash-scope 결과·SOURCE_BLOCKED<br>#330 포함; 최신 #329 Adaptive는 미포함. base main으로 전환 | 독립 비작성자 금융/회계 source admission 검토 미완료<br>원 탐색·감사 FAIL·정정 cash scope·SOURCE_BLOCKED를 함께 보존 |
| [#333](https://github.com/jaehojung1879-netizen/Investment/pull/333) `61d0d3f6b003` | MERGE_CANDIDATE<br>40/40 +8707/−0 | 통합 계보·CI 결정·KR/US 정정과 독립 검토 기록<br>고유40파일; #335가 이를 링크하며 대체 복제하지 않음 | Owner main/Pages 승인; 감사 기록 병합은 연구 승격/실행 승인 아님<br>기존 통합감사와 검증 한계·부정 결과 보존 |
| [#334](https://github.com/jaehojung1879-netizen/Investment/pull/334) `645d9fe0b369` | MERGE_CANDIDATE<br>93/93 +30562/−0 | 읽기 전용 Decision Desk·Evidence-First·새 4군 전향 초안<br>최신645d9fe0에서 G14/G16 반례3개 PASS, 독립49 PASS/2 XFAIL, 변경영역113 PASS. #321 이후 merge-main/원격CI·별도 게시 승인 필요 | 화면 게시와 writer/BX/production 승인은 분리. G1/G2는 legacy B2에 한정<br>학술 ROE E1·0 검증 전략·오염된11월 원본6행 보존 |
| [#335](https://github.com/jaehojung1879-netizen/Investment/pull/335) `b4fb08556a0d` | MERGE_CANDIDATE<br>33/33 +1106/−0 | 독립 음성 테스트·CI/Pages preflight와 이번 정리 후속<br>기존 감사 브랜치만 갱신; 새 감사 PR0. 옛 결과는 과거 HEAD로 명시 | Owner main/Pages 승인; 감사 PASS는 실전/알파 승인 아님<br>새 투자 연구 없음; 현재 검증/실패/미확인 분리 |

## 실제 대체 증명과 보존 경계

- #299→#307: 실제 조상, 네 트랙·원 export·6개 기존 섹션 유지, 후속 UI Node35 PASS. #306→#314: 실제 조상,51/54 동일 blob, 나머지는 보존/정확성 확장. shadow/readout57 PASS, 일일/관측/hook45 PASS. 각 native CI는 아래 증거처럼 별도로 취급한다.
- #320→#322→#327→#328: 실제 조상. #322 변경58파일 전부 동일. #327 결과·사양18파일 동일, recorder 관련3파일만 확장. #320 원시 원문/캐시는 보존됐고5개 파생/정정 변경의 옛 blob도9a47f478에서 계속 조회 가능하다. ex-date 정정과 원래 부정 결과를 숨기지 않는다.
- #330→#332: 감사29파일 전부 동일. #329 현재 HEAD는 #332 조상이 아니며 Adaptive11파일은 별도다. ML v1 subtree는 양쪽 모두 `949478eb852c4f4bd15d55685fafac92f6b7c187`이다.
- #330의 실제 base 브랜치 HEAD는 최신 #329 `0a1f494171576af6928fe531145a8c8f050253fd`, diff merge-base는 `17404f86535f0b8a8992da451dc7667f00539dd6`다. 커넥터의 normalized base_sha가 후자를 반환한 것을 실제 git ls-remote/merge-base로 구분해 증거에 함께 남겼다.
- #316은 #325 조상이지만 C2 등록/실행 packet이6개 부모 파일을 바꾸며 독립 승인 경계가 남는다. 실행권/봉인을 한 PR 범위로 합치지 않고 KEEP_BLOCKED. #326은 독자 workflow 보호 실패가 있으며 DO NOT MERGE 그대로다.
- C2 claim은 현재 원격 annotated tag `4944827ad01568db10f3ac2c6229beda683930cc` → `9dc2928d3c2110a90ea911a74372cd75372a5d2e`로 존재한다. #292의 과거 claim push403/당시 부재 기록을 현재 상태로 승계하지 않는다. tag/승인 필드 NOT_YET_EXECUTED는 성공 결과나 재시도 권한이 아니다. 이 claim과 Atlas consumed refs는 손대지 않았다.
- #328은 #324를 포함하지 않는다(같은 수집기4경로는 다른 blob, 동일 수정0). #317/#318/#319/ML/US/통합감사 역시 #328에 흡수되지 않았다. 고유 실패/원천 증거를 정리 건수 때문에 닫지 않았다.

## 기능 소유권과 UI 통합

| 기능 | 보존할 소유권 | #334와의 차이/통합 조건 |
|---|---|---|
| 데일리 브리핑·현재 판단/신선도·실계좌/전향 구분 | #314 (+#306) | #334는 일일 export/비교기·shadow 상태를 대체하지 않는다 |
| 네 트랙 연구·저장 포트폴리오12개 비교/차단90개 | #307 (+#299) | #334의 ML/US/정정 역사와 범위가 다름; app.js/index.html 충돌 해소 필요 |
| KR/US 현재 운영 판단 | 기존 weekly receipt + #314 일일 투영 | #334 production은 읽기 전용 복사; 정책의 단일 원천은 기존 pipeline/weekly_decision |
| 모델별 과거 성과 | 기존 terminal 6개 섹션 | #334가 유지, 기존 수치를 새 추천으로 재해석하지 않음 |
| census·선행연구·정정/SOURCE_BLOCKED·AI 가상·4군 초안 | #334 | E1/UNVERIFIED와 검증된 추천0개를 분리 |
| 기존 Paper/Shadow·H126/H252 | #314 shadow/readout | #334 새 월간 가상 코호트와 다른 모집단·원장; 합산 금지 |
| 새 월간4군·126/252세션 평가 | #334 prospective draft | Owner 승인/실제 recording adapter·공개 관측/평가 연결 검증 전 비활성 |
| Pages 데이터·state/latest 게시 | #321의 기존 단일 Pages 경로 | UI에 또 다른 publisher/platform을 만들지 않음 |

장기적으로 현재 판단은 기존 receipt, 과거 성과는 고정 원천 projection, 화면은 기존 terminal 한 곳에서 관리한다. #307 두 충돌 파일을 해소할 때 네 트랙/12개 저장 비교와 #334 desk를 함께 유지한다. 이번 작업은 기능 삭제·교체를 하지 않았다. #314는 #321+#334 tree와 conflict0이며 #307은2파일 conflict다.

## CI·출시 경로

main `37f8cbf6b1c066f6b3c65235953648d17ebf2f69`; #321 `cd2892eb6d6623c2527eeda690959d18839acc4d`; #334 `645d9fe0b3693a219693234468b70f43bc7f0bd2`. 격리 결합 commit `c697056b5381faa7ba0c98950f0914a546d54bc6`, parents #334/#321, tree `4b6ede8d3324b1ae03d09e57192a6004ef545729`. 역순 merge-tree와 같고 #315 조상23522002를 포함한다. 원격 브랜치에 이 merge를 게시하지 않았다.

- #321 exact 원격 Tests42369756685:6521 PASS; Pages42369756681: diagnostic SUCCESS, build/deploy SKIPPED.
- #334 최신645d9fe0 원격 Tests43203465272는 IN_PROGRESS다. 이전2e1cef59의43131341576은6516 PASS/1 FAIL(threadpoolctl3.8.0)이며 새 HEAD의 결과로 승계하지 않는다.
- 최신 main 일반 Pages43150678545(11-12 03:48Z):6423 PASS/1 FAIL(동일 pin), 정상 build/deploy/state 모두 SKIPPED. 옛 main Tests의 녹색(10-31)과 현재 환경을 혼동하지 않는다.
- #327/#328은 별도로 committer identity 없는 임시 clone의 rebase 테스트가 실패한다. 재현시 `Committer identity unknown`; identity가 있으면 PASS. fixture에 로컬 identity를 명시하고 assertion은 유지할 최소 수리 댓글을 #328에 남겼다.
- #326은 common pin 외 workflow 보호 실패8개가 있다. #321로 모든 PR이 자동 녹색이 된다는 주장은 하지 않는다.
- 최신 로컬 독립49 PASS/2 strict XFAIL(G1/G2 legacy 잔여), runxfail2 FAIL/49 PASS. G14/G16 동일3반례는 이전2e1cef59에서FAIL, 최신645d9fe0에서PASS. 최신 변경영역113 PASS. 이전2e1cef59 전체 suite는6612 PASS/2 historical-blob FAIL(보충 후2/2 PASS)이며 최신 전체 PASS로 표기하지 않는다. G15 실제 dossier40개 재무 fact 날짜 PASS. 운영/보호128 PASS, lint/compile PASS; 전체 결합 suite와 브라우저 최종 결과는 #335의 이번 verification을 따른다.
- 배포·state/ledger 실증은 미실행. 로컬 브라우저 KR/US×1280/390에서 기존6섹션/desk·오염/차단/미검증 표시를 점검했다. 고정 공개 snapshot의 KR FINAL은 ETF100, US PREVIEW는 현재 판단 불가로 남는다. 이를 현재 실서버 배포 PASS로 세지 않는다.

최소 경로: (1) Owner가 #321 exact HEAD의 A 의존성/B state publisher/C read-only provenance를 함께 승인 → plain merge → 새 main Tests와 **정상** Pages validation→deploy→state 게시를 확인. (2) 현재645d9fe0의 G14/G16 수리 검증을 보존하고 작성자가 새 main을 일반 merge → 새 exact combined remote CI. (3) 새 exact HEAD의 읽기 전용 게시만 별도 승인·plain merge. 달력 날짜로 게시를 약속할 수 없고 이 순서의 관문이 완료되는 때가 게시 가능 시점이다.

실패하면 다음 merge/활성화를 중단한다. publisher는 배포 뒤에만 state를 쓰고 freshness 회귀/동일시각 충돌/권한 실패에서 fail closed, ref 충돌은 최신 tree 기준 force:false로 재시도한다. deploy 실패는 state를 갱신하지 않는다. 배포 성공 뒤 state 실패는 기존 유효 state를 보존하고 원인을 공개하며 강제 push/ledger 되감기/lock 초기화를 하지 않는다. UI 회귀는 검토된 새 revert PR로 복구하며 연구 원본을 수정하지 않는다.

## Owner 결정 패킷 — 현재 실행 가능한 요청1개

**#321 exact `cd2892eb6d6623c2527eeda690959d18839acc4d` plain merge 승인 여부.** A 일반 설치 threadpoolctl3.7.0/joblib1.6.0, B 기존 deploy 후 state/latest 단일 writer, C closed-study read-only provenance 전체를 포함한다. main push가 정상 Pages를 자동 시작한다. top-level 권한은 contents/pages/id-token write 그대로, 진단 job은 contents read, Owner-only formal job bytes/dispatch 조건은 불변이다. 수치 재현 함수·허용오차는 불변이고 workflow assertion 한 함수만 명시된 유지보수 verifier로 변경됐다.

근거: exact 원격6521 PASS, 로컬128 운영/보호 PASS, 보호235해시/등록/결과/requirements와 formal job 불변, #315 실제 조상·원 역사 객체 보존. 승인 후 draft/review/required checks를 확인하고 exact HEAD가 같을 때만 merge한다. 이후 새 main Tests→정상 Pages→state 경로 한 곳 변경·marketAsOf/generatedAt 비퇴행·ledger tree/동시 append 보존을 실제 확인한다. 어느 관문이든 실패하거나 HEAD가 달라지면 중단하고 재검토한다.

#334 현645d9fe0의 G14/G16은 수정 확인됐지만, #321 정상화와 새 exact combined remote CI 전에는 병합/게시하지 않는다. 읽기 전용 게시 승인은 그 후의 정확한 HEAD로 별도 요청한다. 전향 원장·BX·production 정책·유료 원천·봉인 실행 승인도 요청하지 않는다. #314 shadow hook, #328 v2 writer는 각각 별도 운영 승인 없이는 활성화하지 않는다.

## 이후 관리 원칙

1. 목적 하나에 활성 개발 PR 하나. 후속 수리는 기존 PR에 추가하고 새 PR 전에 등록부를 확인한다.
2. 독립감사는 원 개발 PR과 분리하되 같은 감사 브랜치/PR을 갱신한다.
3. 실패·SOURCE_BLOCKED도 날짜/상태/해시로 보존한다. 완전 흡수는 ancestry+blob/diff와 대체 댓글을 남겨 종료하고 브랜치/태그를 삭제하지 않는다.
4. 원천·실증 결과·전향 기록·운영 변경의 승인/실행 경계를 구분한다. 서로 다른 봉인 연구를 squash로 합치지 않는다.
5. stacked PR은 base·누적 diff·통합 순서를 명시한다. 부모를 닫기 전에 살아남는 인수 PR을 main 기준으로 전환하고 부모 객체를 보존한다.
6. HOLD는 원천/실행/승인/담당자의 구체적인 대기 조건을 적는다. 설계 완료를 실제 결과나 승인으로 세지 않는다.
7. 공통 CI 원인은 #321 한 곳에서 고치고 각 PR에 같은 workflow 수리를 복제하지 않는다. 독자 실패는 별도로 등록한다.
8. 이 후속 등록부와 기존 #328 원본을 링크한다. 다른 폴더에 동일 관리 문서를 복제하지 않는다.
