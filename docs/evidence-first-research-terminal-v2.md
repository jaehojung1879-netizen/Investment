# Evidence-first research terminal v2

## 작업 기준과 교체 전 필드 출처 목록

기준 main: `8f45870cf8a0c41c5d32c3ec1296417de23c5db1`.
2026-10-11 확인 시 #220은 main에 있고 #221은 OPEN / Draft / 미병합이다.
#221 브랜치와 자료를 읽거나 가져오지 않는다. QQQ 그래프도 만들지 않는다.

교체 전 실제 화면은 주간 판단·보유안·관찰·과거 성과·한미 비교 뒤에 결합 Kelly,
시장 지표, 13F/국민연금, 레이더, 선정 과정, 장기 후보와 13개 열린 상세 패널을 렌더링했다.
표시 어댑터는 아래 출처만 사용한다. 연구 결과를 계산하는 함수를 호출하지 않는다.

| 화면 필드 | 권위 있는 출처 / 실제 필드 | 증거 분류 및 표시 조건 |
|---|---|---|
| 시장·신호일·보유 종목·비중 | signal-history `ledger/weekly-decisions/receipts.jsonl`: region, asOfDate, holdings, weights, stockCount, stockWeightPct, benchmarkWeightPct | FINAL_WEEKLY 영수증만. latest.json은 현재 게시 상태 확인용이며 배분 권위가 아님 |
| 미편입 이유·문턱·후보 설명 | 같은 영수증: noTradeReason, costs, holdings.reasonKo, watchlist | 공식 가상 판단 / 검증 미완료. 관찰 후보는 매수나 보유로 표시하지 않음 |
| 게시·시세 신선도 | 같은 commit의 latest.json: generatedAt, blocked, unsafeReason, regions.*.freshness; publication-status.json: status, siteGeneratedAt, attemptedAt | 거부·불일치·3일 초과 생성본·누락은 UNAVAILABLE_OR_BLOCKED. 이전 비중을 현재로 승계하지 않음 |
| 원문·다이제스트 | 영수증 receiptId, digest, inputs; signal-history 조회 commit | 원문 행의 숫자 표기를 보존해 Python canonical receipt SHA-256 확인. 원문 링크는 commit 고정 |
| KR 주간 P0/P1 지표·NAV | `docs/weekly-decision/weekly-passive-first-v1-weekly-replay-corrected-benchmark.json`: regions.KR.paths, weeklyNav | 과거 탐색. 같은 713회 주간 달력·KRW·비용 반영. benchmarkBasis=phase-c-corrected 필수 |
| KR 종목 선택 이력 | 같은 자료: regions.KR.decisions (date, signalDate, holdings, stockCount) | 실제 기록에서 4회 도출. 개별 회차 비중은 자료에 없어 표시하지 않음 |
| KR 21세션 P0/P1/C1/C2 | `docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json`: regions.KR.paths, weeklyNav | 155회 별도 탐색. C2의 기록 excessCagrPp=1.752는 사후 탐색 / 독립 검증 미완료 |
| US 주간 P0/P1·KRW NAV | 주간 corrected JSON의 regions.US | 713회 모두 종목 0개, 경로 동일. 생존편향·퇴출 시세 결손 한계. 미국 종목선택 성과로 해석하지 않음 |
| US USD CAGR | `docs/us-readiness/weekly-passive-first-v1-weekly-us-local-currency.json`: paths.P0/P1.cagrPct | 주간 문맥의 별도 USD 요약. USD NAV가 없어 KRW NAV를 USD로 재표기하지 않음 |
| US 기존 USD 21세션 요약 | `docs/us-readiness/weekly-passive-first-v1-us-local-currency.json` | 내용·통화 확인만. 주간 화면의 출처로 사용하지 않음 |
| 지수 및 종목 가격 한계 | `docs/weekly-decision/kodex200-benchmark-audit.md`, corrected accounting protocol | KODEX 분배 이중 반영된 구형 수치를 제외. 종목 시세 감사는 6종목 표본, 보정 원장은 구형 지수 기준 |
| SPY/QQQ·Nasdaq 구성 | main에 없으므로 사용하지 않음 | #221 병합 후 별도 출처/통화/기간/비용/외부 대조 검증 필요 |
| 결합 Kelly·확률·레이더·13F·후보 점수 | 기존 data/site-data.json 및 구형 app.js | 현재 판단을 설명하지 않는 실험·진단. main 공개 화면과 fetch/render 경로에서 제거. 코드와 기존 계약 테스트는 docs/archive/dashboard-v1 보존 |

위 목록을 작성한 뒤 UI 교체를 시작했다. 초기 신호 원장 확인 commit:
`6a6b7e753814cc9adf56811ca78abdcaef0d69ea`.
FINAL 영수증 2건: KR 2026-10-08, US 2026-10-09, 각각 종목 0개·지수 100%.
전향 기록과 2013–2026 과거 시뮬레이션을 합치지 않는다.

## 배포 및 안전 계약

Pages는 `python -m pipeline.build` → production validate → index.html/styles.css/app.js와
site-data.json을 `_site`에 복사한다. build.py, validate.py, pages.yml은 봉인 연구의 byte-pinned
파일이다. 수정하지 않는다. 새 라이브 화면은 이 세 정적 파일만으로 동작한다.
원본 성과 JSON은 위 main commit의 raw.githubusercontent.com URL에서 SHA-256을 확인해 읽는다.
복제 성과 JSON이나 새 프레임워크·차트 CDN은 없다. 주간 원장은 GitHub API로 branch HEAD를
확인한 뒤 세 파일을 **동일 commit**에서 읽는다. 어느 필수 조회라도 실패하면 현재 배분을 차단한다.
3일 생성본 지연 한도는 기존 사이트의 기준을 유지하며, 거래소 휴장일 계산을 새로 만들지 않는다.

구형 계약 테스트는 보존된 파일을 대상으로 그대로 검사한다. 새 공개 화면의 기능·수치·안전·
XSS·실제 브라우저 검증은 별도 terminal 테스트가 담당한다. 아카이브는 Pages에 복사하지 않는다.
연구 모듈, publication 정책, 과거 결과, 원천 스냅샷, execution lock, signal-history는 수정하지 않는다.

## 검증 기록

- Ruff 전체 lint PASS, pipeline compileall PASS.
- focused pytest **122 passed** (4.63초); 새 Node 계약 **19 passed**가 pytest에서도 실행된다.
  범위: terminal, 보존 frontend/evidence/explainability 계약, weekly_decision,
  weekly_publish, US source readiness와 수정된 기타 frontend assertion / Pages 순서 계약.
  기존 assertion은 제거하지 않고 보존된 v1 경로만 지정했다.
- Chromium **154.0.8037.57**, 실제 렌더링 **16개 viewport 상태 PASS**:
  KR/US 각각 375/390/768/1280px, KR 21세션 각 폭과 연간 표/방법론 펼친 각 폭.
  document 가로 초과 0px, application/console 오류 0건.
- 현재 기록의 지수 100% 상태, 시장 전체 전환·세션 유지, 네 섹션, 네 종목 선택 주
  티커 펼침, 그래프 경로 toggle, 두 연구 주기 분리, C2 +1.752%p 표시를 확인했다.
  1–5개 정확한 종목 비중 / 잔여 지수는 **합성 영수증 안전 테스트**이며 성과를 생성하지 않았다.
  거부·지연·차단·미리보기·영수증 없음·digest 불일치 모두 현재 배분/관찰 출력을 차단했다.
- 실제 GitHub API 및 raw 자료 조회도 **PASS (전송 TLS 검증 유지)**.
  클라우드 Chromium의 CA store에 session proxy CA가 없어, 검증용 Playwright APIRequestContext가
  관리 프록시와 NODE_EXTRA_CA_CERTS를 사용해 실제 HTTPS 응답을 브라우저에 전달했다.
  ignore-certificate-errors / ignoreHTTPSErrors를 사용하지 않았다. 사이트 코드에 이 전송 경로는 없다.
- [기계 검증 기록](ui-verification/research-terminal-v2/browser-verification.json),
  [KR desktop](ui-verification/research-terminal-v2/kr-1280.png),
  [KR mobile](ui-verification/research-terminal-v2/kr-390.png),
  [KR 21세션](ui-verification/research-terminal-v2/kr-21-session-1280.png),
  [US desktop](ui-verification/research-terminal-v2/us-1280.png).

재현(Playwright는 저장소 밖에 설치; 새 production 의존성 없음):

```bash
git fetch --no-tags --depth=1 --filter=blob:none origin 6a6b7e753814cc9adf56811ca78abdcaef0d69ea
mkdir -p /tmp/terminal-receipts
for name in latest.json publication-status.json receipts.jsonl; do
  git show "6a6b7e753814cc9adf56811ca78abdcaef0d69ea:ledger/weekly-decisions/$name" > "/tmp/terminal-receipts/$name"
done
npm install --cache /tmp/terminal-npm-cache --prefix /tmp/terminal-browser playwright@1.58.2
NODE_PATH=/tmp/terminal-browser/node_modules \
TERMINAL_RECEIPT_DIR=/tmp/terminal-receipts \
node scripts/verify_research_terminal.cjs
# 현재 실제 HTTP 자료도 확인할 때 --live 추가. 관리 환경에서는 proxy/CA 설정을 보존한다.
node --test tests/research_terminal.test.cjs
python -m pytest -q tests/test_research_terminal.py tests/test_frontend_contract.py \
  tests/test_evidence_contract.py tests/test_explainability_v21.py \
  tests/test_weekly_decision.py tests/test_weekly_publish.py tests/test_us_source_readiness.py
```

### 전체 빌드 및 CI의 실제 범위

변경 후 Pages의 **실제 staging 파일 목록으로** 새 HTML/CSS/JS를 복사해 HTTP server에서 검사했다.
필요한 성과 JSON은 복제 없이 검증된 고정 raw URL로 조회되므로 Pages의 docs 복사 목록을 바꾸지 않았다.
`python -m pipeline.build`는 기존 current_signal / walk_forward 모델 학습과 live construction을
호출한다(build.py 781/800행). 사용자의 모델 fitting 금지에 따라 이번 작업에서는 실행하지 않았다.
seed 생성도 가상 성과를 만들므로 실행하지 않았다. 모델·봉인 결과·publication 정책은 byte 검증으로
원본과 동일함을 확인했다. 새 PR에서 전체 production build/deploy 성공을 주장하지 않는다.

기준 main의 기존 실제 Pages 실행
[38123572487](https://github.com/jaehojung1879-netizen/Investment/actions/runs/38123572487)은
2026-10-11 완료 / SUCCESS로 읽기 전용 확인했다. 새 UI는 아직 Draft라 배포하지 않았다.
이 환경에서 Pages artifact의 Azure blob 및 공개 Pages URL 다운로드는 HTTP 403이었다.
보호된 workflow / 30분 테스트 timeout을 수정하거나 수동 실행하지 않았다.
새 Draft PR의 CI 상태는 PR checks를 기준으로 최종 보고한다. 취소/실행 중 상태는 PASS가 아니다.

### 통합과 검토

주간 원장 조회에는 공개 GitHub API와 raw.githubusercontent.com의 가용성이 필요하다.
API 제한·네트워크 실패 시 과거 영수증을 현재 배분으로 쓰지 않고 차단한다. 정적 성과 자료는
기준 commit과 SHA-256에 고정되며 업데이트에는 표시 출처의 명시적 검토가 필요하다.
runtime 신규 dependency / #220 모듈 import / 미병합 #221 의존성은 없다.
#221 병합 후에도 QQQ를 production benchmark로 바꾸지 않는다. 추가 ETF 비교는 별도의
원문 JSON·USD 기간·분배/비용 기준·SPY 외부 대조 한계·PARTIAL Nasdaq 구성 상태를 확인한 뒤 연결해야 한다.
CI 완료와 owner의 화면/근거 검토 후 병합을 검토한다. 이 작업에서는 병합하거나 ready로 바꾸지 않는다.
