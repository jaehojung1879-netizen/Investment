# Research Terminal v3.1 — 한국어 UX와 실제 공개 판단 확인

기준 main: `8a1256f74a541d684100979cefb6dbc1759a620b`.
#225는 `2026-10-12T01:16:57Z`, #226은 `01:17:11Z`에 병합되었다.
새 UI는 이 main의 기존 출처 파일을 SHA-256 검증 후 사용한다. 출처 파일의
등록 해시, 내부 `receipt`/`digest` 필드, 파일 경로와 숫자 정규화 규칙은 그대로다.

## 표시 변경

- ‘영수증’ → ‘투자 판단’, ‘확정 영수증’ → ‘확정된 투자 판단’.
- ‘영수증 이력’ → ‘투자 판단 이력’, ‘원장’ → ‘판단 이력’/‘데이터 근거’.
- 무결성 오류 → ‘투자 판단 데이터 검증 실패’, 해시 → ‘기록 무결성 검증값’.
- 미등록, 조회 실패, 게시 차단, 입력 확인 필요, 데이터 검증 실패를 구분한다.
  완전한 Git 파일 목록을 확인한 경우에만 ‘투자 판단 미등록’으로 표시한다.
  불완전한 목록/네트워크 실패를 미등록 증거로 사용하지 않는다.
- 운영·공시의 상태 코드는 한글 설명으로 표시한다. 원문 코드와 SHA-256,
  세부 선정 점수·제외 사유는 펼쳐 보는 데이터 근거에 보존한다.

P1은 공식 주간 지수 우선 정책의 **가상 판단**이다. C1은 기존 CHAMPION으로
선정한 종목/비중과 잔여 현금, C2는 **동일한 종목/비중**과 잔여 지역 지수 ETF다.
C1/C2는 현재 관측을 사용하는 전향적 연구 변형이며 실전 검증/과거 21거래일
실행 순서의 동일 재현을 뜻하지 않는다. 종목별 비중과 잔여 자산은 검증된
공개 기록에서만 표시한다. 미등록/차단 시 0%, 100% 또는 과거 비중을 만들지 않는다.

판단 기준일은 완료 거래일이다. 자료 관측은 기록에 있는 `generatedAt` 또는
P1의 `inputs.siteGeneratedAt`이다. ‘게시 시도’는 **실제 기록된**
`publication.attemptedAt`만 사용한다. 이는 Git 푸시 완료 시각이 아니다.
현재 연구 게시 형식에는 별도 게시 시도 시각이 없으므로 ‘미확인’으로 남긴다.
이를 자료 관측 시각으로 대체하지 않는다. 게시 상태 확인과 시각 기록은 별개다.

## 실제 공개 관측 — 읽기 전용

[실제 입력 검증 결과](ui-verification/research-terminal-v3-1/publication-audit.json)는
2026-10-12 UTC 관측이며, `signal-history`의
`8ba3cbab22e88a1b104328899396723707bf073b`에 고정했다.
완전한 Git tree와 commit의 tree 연결을 확인하고, P1 세 파일의 Git blob SHA-1과
원문 SHA-256을 확인했다. 그 후 기존 브라우저 정규화/무결성·비중 검증기를
그대로 적용했다. 원문 기록 2건 모두 무결성 검증에 통과했다.

| 지역 | 현재 유효 P1 기준일 | P1 공개 기록 | C1 / C2 |
| --- | --- | --- | --- |
| KR | 2026-10-08 | KODEX 200 (`069500.KS`) 100%, 개별 종목 0개 | 연구 판단 미등록 |
| US | 2026-10-09 | SPY 100%, 개별 종목 0개 | 연구 판단 미등록 |

P1 자료 관측은 `2026-10-11T05:58:26.805659+00:00`, 게시 시도는
`2026-10-11T06:00:58.145116+00:00`이다. 공개 상태는 `PUBLISHED`, 각 지역의
관측/기대 거래일은 기준일과 같고 `FRESH`다. 이는 기존 발행기의 신선도/3일
게시 유효 범위를 충족한다는 의미다. 종목 미선정 사유는 두 지역 모두
`ORDERING_NOT_ESTABLISHED`이며 현재 종목 순위의 수익 정렬 근거가 부족하다.

**정확한 C1/C2 차단 원인:** 관측한 완전한 공개 tree에
`ledger/research-strategies/current-champion-decisions-v1/`의 `latest.json`,
`publication-status.json`, `receipts.jsonl`이 모두 없다. 최신 확인된 성공
일반 ledger 실행은 [38115237709](https://github.com/jaehojung1879-netizen/Investment/actions/runs/38115237709),
`2026-10-11T05:34:47Z` 생성, head `123ce7d8a07740883efd76db954586c7be3b0587`로
#226 발행기 병합 이전이다. 병합 후 현재 연구 판단의 첫 정상 공개가 아직
관측되지 않았다. 따라서 연구 발행 코드가 실패했다고 단정하지 않는다.
`ledger.yml`의 정규 일정은 `10 0 * * *` UTC이며 Actions 실제 시작은 지연될 수 있다.
이 PR에서는 실행을 요청하거나 기록을 쓰지 않았다.

P1과 연구 저장 경로/규칙은 독립적이다. 실제 미등록 상태에서도 P1은 표시됐다.
**실제 C1/C2 종목·비중 일치 및 최신 운영 입력 검증은 NOT_MEASURED**다.
없는 연구 기록을 파생하거나 현재 위치로 채우지 않았다.

운영 `https://jaehojung1879-netizen.github.io/Investment/data/site-data.json`은
이 관리 환경의 네트워크 경로에서 **403**이었다. 이는 이 환경의 접근 제한이며
운영 사이트 장애의 증거는 아니다. 최신 시장/거시 입력의 실자료 검증은 미완료다.
GitHub 원문 P1은 접근 가능했고, 별도 고정 공식 캐시로 13F/NPS 공시 표시를 검증했다.
13F는 2026-06-30 분기말/실제 8월 제출, 국민연금 전체 기금은 2026-05-31 기준이며
현재 보유라고 표시하지 않는다. 원본 공식 캐시와 과거 성과 자료를 수정하지 않았다.

## 검증과 재현

[브라우저 결과](ui-verification/research-terminal-v3-1/browser-verification.json)는
합성 양성 사례와 실제 공개 관측을 별도로 기록한다. C1/C2 정상 카드와 시장/거시
차트의 양성 입력은 `/tmp`의 **합성 검증 자료**이며 화면에 표식이 있다.
실제 P1은 고정 공개 원문, 13F/NPS는 고정 공식 공시다. 실제 네트워크 관측에서는
P1 표시/연구 미등록과 위 403을 별도로 기록한다. 테스트를 실제 연구 공개로 주장하지 않는다.

375/390/768/1280px 지역별 카드, 시장/거시 기간 선택, 기관 상세와 모바일 화면을
검사한다. 실제 공개 상태도 390/1280px에서 확인한다. 정상 합성 검증 콘솔/앱 오류는
0건이며 실자료 관측의 접근 403은 별도 브라우저 오류로 남긴다. 가로 넘침은 없다.
현재 카드/시장/기관 조회 시 과거 수익률 요청을 하지 않는 기존 분리를 유지한다.
과거 성과 수치·기간, QQQ 보조 비교, 기관 7곳, 국민연금 전체 기금은 기존대로 보존된다.

브라우저 실행은 기존 검증기를 확장하며 프로덕션 경로에 쓰지 않는다:

```sh
NODE_PATH=/workspace/terminal-browser/node_modules \
TERMINAL_PYTHON=/workspace/investment-venv/bin/python \
TERMINAL_RECEIPT_DIR=/workspace/terminal-evidence/weekly \
TERMINAL_VERIFICATION_DIR=/workspace/terminal-v31-browser \
node scripts/verify_research_terminal_v3.cjs --live
```

P1 fixture는 기존 v3 검증에 사용한 `6a6b7e753814cc9adf56811ca78abdcaef0d69ea`의
변경 없는 세 파일이다. 실제 네트워크 검증은 실행 당시 공개 브랜치를 새로 읽는다.

읽기 전용 감사 재현:

1. 원하는 관측 시점의 signal-history commit을 확인한다.
2. GitHub commit API 응답을 `commit.json`으로 저장한다. 그 응답의
   `commit.tree.sha`로 **완전한** recursive tree를 요청해 `tree.json`으로 저장한다.
3. 해당 commit의 weekly-decisions 세 원문을 `p1-latest.json`,
   `p1-publication.json`, `p1-receipts.jsonl`로 별도 디렉터리에 저장한다.
4. `node scripts/audit_research_terminal_publication.cjs INPUT_DIR SIGNAL_HISTORY_SHA MAIN_SHA`.
   스크립트는 입력 디렉터리에 쓰지 않으며 결과를 표준 출력으로만 반환한다.
   Git blob 또는 tree 연결이 다르면 실패한다. 현재 연구 기록이 존재하는 경우에는
   존재 확인만 보고하고 별도 현재 입력 검증이 필요하다고 명시한다.

집중 pytest는 기존 P1/연구/프런트엔드 무결성 검사를 유지하며 UI 용어·시각 구분,
미등록/조회 실패/거부의 구분, 잘못된 tree/변조 바이트 거부를 추가했다.
최종 head에서 전체 pytest를 한 번 수행한다. Ruff, compileall, 모든 pipeline
모듈 import, scripts 구문 검사와 **격리된** seed의 비운영 성공/운영 거부도 확인한다.
최종 전체 검사와 CI의 실제 결과는 Draft PR 본문과 완료 보고에 기록한다.

## 별도 운영 후속 확인

다음 정상 운영 실행에서 별도 연구 공개 경로가 생성되는지 확인해야 한다.
등록되지 않으면 실행 로그/거부 상태를 읽어 원인을 좁힌 뒤 별도 운영 수정으로
다룬다. 최신 운영 site-data의 접근과 현재 연구 입력의 신선도 확인, 실제 C1/C2
비중 일치 검증이 필요하다. 별도 게시 시각 필드가 필요하면 그것도 후속 형식
변경으로 다룬다. 이 PR은 scientific pipeline, config, workflow, 봉인 연구
프로토콜/결과/실행 lock, 기존 판단 기록을 변경하지 않는다. 새 연구/학습/백테스트,
운영 발행 또는 거래 정책 변경을 수행하지 않았다.
