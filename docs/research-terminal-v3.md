# Research Terminal v3 — 현재 전략과 시장 맥락

최종 기준 main: `82b1aac4b2441f076064830b6af776f1cda1b0fe`.
처음 확인한 main은 `b50b7c308105b4964fc6d03cfdb700b473e0cde6`였으며,
작업 중 병합된 #224를 확인하고 최종 기준에 반영했다. #221의 SPY/QQQ 원천은
이미 병합돼 있다. #224의 자본배분 정책을 C1/C2에 연결하지 않는다.

## 현재 판단의 의미

세 카드와 KR/US 선택을 제공한다. 관찰 종목, 현재 선택된 보유, 과거 백테스트
보유는 서로 다른 목록이다. C1/C2는 실전 권고가 아닌 현재 관측 연구 변형이다.

| 카드 | 계산 및 원천 | 잔여 자산 | 시간 주기 |
|---|---|---|---|
| P1 | 기존 공식 `weekly-passive-first-v1` 영수증 그대로 | KR `069500.KS`, US `SPY` | 확정 주간 영수증 |
| C1 | 원래 CHAMPION selection/baseline 함수, 지역별 독립 입력 | CASH | 현재 완료 세션 관측 |
| C2 | C1의 종목과 종목 비중을 그대로 복사 | KR `069500.KS`, US `SPY` | C1과 동일 |

P1의 정책, digest 제외 필드, 검증 함수, 관찰 목록은 유지한다. 프런트엔드는
정책 비중을 계산하지 않는다. 현재 판단, 시장·거시, 과거 성과, 13F, 관찰 종목,
연구 근거를 6개 탐색 구역으로 배치한다.

### C1/C2 방법론과 재현 범위

`pipeline/current_champion_decisions.py`는 `kelly_portfolio.selection_and_baseline`
을 호출한다. 이 경로의 `conviction_scores`, `select_portfolio`, `baseline_weights`를
그대로 사용한다. 결합 KR+US Kelly 최종 비중, Kelly 최적화, 기대수익 추정은
입력으로 쓰지 않는다. C2는 C1의 직렬화된 종목 비중을 복사하고 현금만 바꾼다.

conviction은 `(alphaPercentile - 50)/50`, 실제 하방 변동성, 근거 범위, 원래
상태 배율에 따른 순위 점수다. 확률이나 미래 수익 예측이 아니다. 원래 팩터
적격성, 역하방 위험 배분 및 순위 기울기, 섹터·이름·지역 한도와 현금 하한을
그대로 적용한다. 원래 지역당 최대 3개와 지역 비중 65% 제약도 유지한다.
현재 거시 위험예산이 더 낮으면 그 예산이 구속한다. 종목별 임의 15% 배분은 없다.

버전 `current-champion-decisions-v1`은 엔진 및 현재 원래 설정의 바이트를 등록한다.

- 엔진: `6a4bd54be11e35e7348f64d0c99e7764635c4efcea62306da0b6ca81bfb3b06c`
- config.json: `d1169e1e4a84ded1385e11e591ea01a4b383e7a625960ece9278a0bde3c15273`

둘 중 하나가 바뀌면 이 버전은 계산을 거부한다. 새로운 설정을 묵시적으로
과거 정책과 동일하다고 인정하지 않는다.

[선택 앵커 감사](ui-verification/research-terminal-v3/champion-anchor-parity.json)는
봉인된 `regional-standalone-paths.json.gz`의 지역별 첫·중간·마지막 앵커
(0, 77, 154)을 고정해 사용했다. 2013-01-04, 2019-10-18, 2026-08-07의 선택된
입력에서 종목 비중, 현금 비중, conviction 점수 **6/6 일치**를 확인했다.
계산에는 선택/배분 입력만 투영했고 미래 수익을 다시 계산하지 않았다.

전체 과거 후보군은 이 산출물에 없으므로 재선정 순서의 완전한 재현은 아니다.
기록된 선택 집합에서 POSITIVE 적격 상태를 전제하는 제한된 검사다. 과거의
price-sleeve proxy 후보, 21세션 실행 순서와 현재 production 전체 팩터 후보·거시
예산은 다르다. 따라서 근거 등급은
`PROSPECTIVE_RESEARCH_ONLY_CURRENT_CHAMPION_VARIANT`다.
과거 실행 순서 또는 독립 검증된 알파와의 동등성을 주장하지 않는다.

### 입력 차단과 별도 원장

다음 조건을 만족해야 현재 C1/C2를 계산한다.

- 실제 production 모드이며 seed/synthetic/stale/안전 차단 상태가 아님
- 장기 입력 `weightsWithheld == false`
- 지역 지수 테이프가 원래 거래소 달력의 최신 완료 세션이고 `CURRENT`
- 해당 지역 후보 목록이 존재하고 비어 있지 않음
- 후보 ticker/region/백분위/근거 범위/실제 양수 하방 위험/연구 상태/진입 상태가 유효
- 모든 후보의 시세 기준 세션이 지역 기준과 일치
- 거시 국면, 유효 신뢰도와 위험자산 예산이 존재
- 엔진/config 바이트가 등록 버전과 일치

누락된 후보 풀은 현금 100%로 바꾸지 않는다. 입력이 완전하지만 적격 종목이
0개인 경우에만 C1 현금 100%, C2 지역 ETF 100%가 가능하다. 불완전한 지역은
`BLOCKED`와 이유 코드만 낸다. 다른 지역의 후보나 13F/NPS는 선택 입력이 아니다.
공통 거시 환경이 공유되는 사실은 감추지 않는다.

연구 원장은 `ledger/research-strategies/current-champion-decisions-v1/` 아래
`receipts.jsonl`, `latest.json`, `publication-status.json`으로 분리된다.
영수증 식별자는 버전·지역·완료 세션으로 고정한다. 같은 세션의 지역 입력이
달라지면 과거 행을 덮어쓰지 않고 그 지역 게시를 차단한다. 기존 JSONL 바이트는
그대로 두고 새 행만 추가한다. 동일 지역 입력은 최초 영수증을 재사용한다.

영수증은 선택 사유, 점수, 개별/잔여/총 비중, 제외, 한계, 원천 artifact SHA,
지역 입력 SHA, engine/config SHA, build commit을 기록한다. 직렬화 digest는
정렬된 JSON이며 `digest`와 부가적인 `previousObservationChange`만 제외한다.
변경 설명은 판정 본문과 달리 digest로 인증된 항목이 아니다. 프런트엔드의
숫자 토큰 보존 검증을 재사용해 Python의 `100.0`도 정확히 검증한다.

독립 CLI는 기존 파일만 사용한다.

```sh
python scripts/build_current_champion_decisions.py EXISTING_SITE_JSON OUTPUT_DIR
```

먼저 기존 production validator를 통과해야 한다. 이 명령은 자료를 수집하거나
모델을 적합하거나 역사 재생을 실행하지 않는다.

`weekly_publish.main`의 기존 정상 종료 직전에 19행의 별도 게시 훅을 추가했다.
기존 `ledger/weekly-decisions` 경로 호출만 인식한다. 기존 원장 워크플로는
production 검증 후 이 명령을 호출하며 `git add ledger`로 연구 경로도 게시할 수
있다. 워크플로 수정은 필요하지 않다. 연구 게시 실패는 별도 REFUSED 상태를
쓰고 P1의 이미 작성된 결과와 정상 종료를 유지한다. 일반 4/5경로 CLI 계약도
유지한다. 이전 `weekly_publish.py` 바이트에서 훅만 제거하면 원본과 정확히
같다는 보호 검사를 유지했고, 정상 P1 영수증 두 행의 바이트 동일성도 검사한다.

이번 작업은 signal-history에 직접 쓰거나 원장 워크플로를 dispatch하지 않았다.
첫 현재 연구 영수증은 소유자 병합 후 **기존 정기 원장 실행**이 현재 입력 검증을
통과할 때 생성된다. 미게시 경로는 Git tree 메타데이터로 확인하며 세 번의
불필요한 404 조회를 하지 않는다. 브라우저는 최신 원장 commit·게시 시각·거래
세션·digest·C1/C2 동일성·총 100%를 확인한다. 실패하면 오래된 비중을 현재로
대체하지 않는다. 동일 세션 재작성 차단은 수정된 입력을 자동 복구하지 않으므로
원인 검토 또는 다음 세션의 정상 관측이 필요하다.

## 복원한 시장 맥락

시장 카드는 `site-data.json.indices`의 실제 가용 기호만 표시한다. KR/US 지수와
가용 ETF·변동성 지수, 공통 FX/원자재/가상자산을 같은 계약으로 읽는다. 현재
기본 원천에 ETF 행이 없으면 추가하지 않는다. 값·1일 변화·as-of·단위·원천·
신선도와 실제 날짜가 있는 history를 사용한다. 날짜 없는 spark 배열은 쓰지 않는다.
상세는 1M/3M/6M/1Y를 제공하고 가용 구간과 관측 수를 표시한다. 누락된 현재
값을 history의 마지막 값으로 채우지 않는다. 외부 차트 CDN은 필요 없다.

거시는 `macro`, `macroRegime`, `marketDataHealth` 원천을 사용한다. growth/inflation
그룹은 펼치고 나머지 가용 그룹은 접어둔다. 원천이 제공하는 물가·금리·국채·
신용·성장·유동성 지표를 렌더링하고, 없는 지표나 빈 과거 시계열을 만들지 않는다.
1Y/3Y/5Y/10Y는 제공 관측을 날짜로 자른다. 실제 제공 구간이 짧으면 그 사실을
표시한다. 단위·변환·발표 시차·관측일·원문·가용 빈도와 PIT/개정 한계를 남긴다.
원천에 빈도가 없으면 미기록으로 표시한다. 국면/예산은 종목 선택 알파가 아니다.

13F는 NPS/Berkshire/Duquesne/Bridgewater/Tiger Global/Appaloosa/Scion 7개를
복원했다. 제출일과 보고 분기말은 분리한다. USD 보고대상 평가액, 포지션 수,
상위 보유의 공시 비중·수량·원래 share type, 분기 간 수량 변화, 신규/제외 및
SEC 원문을 상세에서 확인한다. 보유 상세는 저장된 상위 10개이며 전체 공시
포지션을 모두 저장했다고 표시하지 않는다. 증가는 거래일을 알려주지 않는다.
공시 평가액 상승을 매수로 해석하지 않고 현금·숏·전체 자산 범위로 확장하지 않는다.

production 자료가 없으면 고정 main의 공식 캐시 바이트를 SHA-256 확인 후 읽는다.
원천의 LIVE 상태를 재사용하지 않고 **CACHED_OFFICIAL**로 표시한다. 보고일,
제출일, 실제 수집일을 유지한다. 미보고/불완전 캐시는 AVAILABLE로 승격하지 않는다.
이 화면 자료는 C1/C2 선택에 들어가지 않는다.

국민연금 **전체 기금**은 NPS 미국 13F 증권과 별개다. 실제 캐시는 2026년 5월말,
1,848.7조 원, 6개 자산군이며 2026-08-15 수집이다. 원래 조 원 단위와 반올림
비중을 유지하며 합계 100.1%를 임의 정규화하지 않는다.

## 과거 성과와 복원하지 않은 항목

과거 성과는 해당 구역 요청 때만 불러온다. 시장/13F를 보기 위해 대형 수익률
자료를 먼저 읽지 않는다. KR P0 12.507%, 주간 P1 12.043%, 21세션 C1 10.395%,
C2 14.258%, C2–P0 +1.752%p를 원천 그대로 유지한다. 주간과 21세션을 구분하고
사후 탐색·독립 검증 미완료 표시는 유지한다.

US SPY는 공식 기준이다. #221의 QQQ는 별도 빈티지의 수동 ETF 비교로 접힌
상세에 제공한다. 새 원천 USD CAGR SPY 14.740%, QQQ 19.838%를 기존 P1 원천의
USD 14.734%/KRW 16.698%와 섞지 않는다. 외부 총수익 대조·SPY 분배금 단일 반영
검증의 미해결 한계를 표시한다. US 종목선택 검증 성과나 QQQ 자동 잔여 비중을
새로 만들지 않는다.

결합 KR+US Kelly 권고, 검증되지 않은 실전 확률, 자동 기관 추종 신호, 자료가
없는 현재 차트, 과거 백테스트를 현재 판단으로 대체하는 위젯은 복원하지 않는다.
웹에서 전체 과거 연구 패널을 한꺼번에 펼치지 않는다. 옛 대시보드는 수정하지
않았으며 유용한 차트/상세 표현 계약만 선택적으로 재사용했다.

## 실제 조회와 검증 증거

[Chromium 기록](ui-verification/research-terminal-v3/browser-verification.json)에는
실제 HTTP 상태와 조회 commit도 포함한다. 당시 공식 P1은 KR 2026-10-08
KODEX 200 100%, US 2026-10-09 SPY 100%, 각각 종목 0개였다. 현재 C1/C2 연구
원장은 아직 없었고 Pages site-data는 이 환경의 관리 프록시에서 HTTP 403이었다.
이는 실제 production의 자료 내용이나 장애를 확인한 결과가 아니다. C1/C2의
진짜 현재 비중, 현재 시장·거시 내용은 이 환경에서 확인하지 못했다.

정상 UI 검증은 격리된 합성 C1/C2·시장·거시 입력을 썼으며 화면에 검증용 배너와
합성 이름을 표시했다. P1 바이트와 13F/NPS 캐시는 실제 고정 원천이다. 합성 입력은
/tmp에만 존재하고 production 출력을 게시하지 않는다. 실제 네트워크 조회는 별도
상태로 기록했다. 정상 입력 검증의 application/console 오류는 0이고, 실제 조회는
Pages 403에 따른 브라우저 네트워크 오류 1건이 있다. 이를 성공으로 감추지 않는다.

375/390/768/1280px, 차트 기간 선택, 기관 상세와 모바일 상세에서 넘침을 검사했다.
CI의 Node 계약 검사는 기존과 신규 래퍼가 각각 한 번 실행한다. 새 focused 검사는
원래 배분·지역 독립·누락/차단·digest·동일 C2·P1 바이트와 실패 격리·선택 앵커를
포함한다. Ruff, 전체 pytest, entry-point import/compile, seed validator도 확인한다.
전체 pytest 및 최종 CI 결과는 PR 설명과 GitHub check에 기록한다. tests.yml의
60분 제한, 배포/원장 워크플로, 기존 봉인 연구·결과·execution lock은 변경하지 않는다.

스크린샷:

- [KR 현재](ui-verification/research-terminal-v3/kr-current-1280.png) / [US 현재](ui-verification/research-terminal-v3/us-current-1280.png)
- [시장 카드](ui-verification/research-terminal-v3/market-charts-1280.png) / [시장 상세](ui-verification/research-terminal-v3/market-detail-1280.png)
- [거시 상세](ui-verification/research-terminal-v3/macro-detail-1280.png)
- [13F 기관](ui-verification/research-terminal-v3/institutional-13f-1280.png) / [보유 상세](ui-verification/research-terminal-v3/13f-manager-holdings-1280.png)
- [모바일 현재](ui-verification/research-terminal-v3/mobile-current-390.png) / [모바일 13F](ui-verification/research-terminal-v3/mobile-13f-390.png)
- [실제 조회의 현재 차단 상태](ui-verification/research-terminal-v3/actual-publication-blockers-1280.png)

재현 명령은 production 구축 없이 실행한다. 외부 Playwright 설치와 실제 P1 파일이 필요하다.

```sh
NODE_PATH=/path/to/playwright/node_modules \
TERMINAL_PYTHON=/path/to/venv/bin/python \
TERMINAL_RECEIPT_DIR=/readonly/pinned-p1-files \
TERMINAL_VERIFICATION_DIR=/tmp/terminal-v3-proof \
node scripts/verify_research_terminal_v3.cjs --live
```

배포 시 별도 서버 번들/빌드 목록 변경은 없다. 기존 Pages의 세 프런트엔드 파일과
이미 게시하는 `data/site-data.json`으로 동작한다. 병합 후 첫 정기 연구 게시와 실제
Pages 원천의 신선도를 소유자가 확인해야 하며, 검증 전에 비중을 추정해 채우지 않는다.
