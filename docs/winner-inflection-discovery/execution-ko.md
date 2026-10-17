# US B · H126 · 2020 역사 탐색 실행

[고정 실행 사양](execution-us-b-h126-2020-v1.json)을 기존 `experiment_workbench`, `winner_inflection`, `winner_inflection_exploration`에 연결했다. 현재 승인 범위는 코드·합성 검증까지다. **실제 미래 라벨 열람·역사 학습은 아직 승인되지 않았다.** 원천 admission과 아래의 소유자 승인 모두 통과해야 실제 입력을 연다. KR 봉인·운영 정책·Claude의 ETF 연구에는 연결하지 않는다.

## 고정된 계산

- US, B(영업이익 양전환 AND OCF margin 증가), H126, 2020년 한 validation fold, seed 19. 신호는 매주 실제 마지막 거래일 마감+60분, 체결은 다음 XNYS 거래일 종가, 만기는 체결일로부터 126거래일 후다. 마지막 2020 신호의 만기는 2021-07-06이다.
- 2013년부터의 신호로 expanding 학습 후보를 만든다. 학습 라벨은 2019-11-29 00:00Z 전에 만기·공개되어야 한다. 최소 36개월·100발행인·500행, proper-fit의 클래스별 최소 50행을 요구한다. 학습 날짜의 마지막 20%는 확률 보정용이며 proper-fit 라벨의 만기·공개가 보정 구간 시작보다 앞서도록 다시 purge한다. 보정 최소 표본이 부족하면 보정 수치는 `UNRESOLVED`다. 2020 라벨로 재학습하거나 임계값을 고르지 않는다.
- 동일 적격 표본에서 사건 규칙, L2 승자/대형손실 로지스틱 두 개, Ridge를 비교한다. 현재 영업·OCF margin/252일 모멘텀/log 규모 대용치 기준과 B 네 특징 추가 모델을 비교한다. 현재 실제 시총으로 규모를 소급하지 않는다.
- 승자는 같은 신호일의 **해결된 적격 코호트** 상위 10%이면서 SPY 초과수익>0, 대형손실은 하위 10%이면서 초과수익<0이다. 동률을 포함하며 최소 30종목이 필요하다. 해결되지 않은 결과를 중립으로 분류하지 않는다. 통제군은 결과를 보기 전에 같은 날짜·당시 산업·규모 대용치 3분위로 정한다.
- 확률은 Brier·average-precision 방식 PR-AUC·신뢰도 구간/ECE, 수익은 평균·중앙 초과수익·Ridge MAE를 보고한다. 공통 예측·해결 표본 해시, 기본 확률, 주간 Top 5 적중·손실 사례를 함께 출력한다. 중첩된 주간 H126 관측을 독립 표본으로 주장하지 않는다.
- 투자 경로는 **겹치지 않는 H126 Top 5 동일 비중**이다. 청산일 이후 첫 완료 주간 신호의 다음 거래일에 재진입한다. 2020년에 시작한 마지막 보유분의 2021년 만기까지 평가한다. 기존 selector와 `us_decision_pilot.simulate/metrics/rebalance`를 재사용한다. 매수 8bp, 매도 8.3bp이며 현금은 명시적으로 무이자 USD다. 연속 SPY 보유와 같은 H126/현금 간격의 SPY 경로를 모두 비교한다. 주간 Top 5 라벨을 연이어 복리화하지 않는다.

## 원천 admission: 아직 남은 정확한 항목

[원천 검토 양식](source-admission-v1.json)의 일곱 항목은 현재 모두 `UNRESOLVED`다. 검토자는 원천·근거·제한을 확인한 문서를 `/workspace/wid-inputs/evidence/`에 두고 항목별 `reviewer`, `citations: [{reference, sha256}]`, `REVIEWED_ACCEPTED`를 기록한다. admission은 그 문서의 내용 해시와 범위를 검증하며 법적 권리나 원천의 진실성을 자동 인증하지 않는다. 허위 승인 필드를 만들어 실행하지 않는다.

| 항목 | 실행 전에 확인할 근거·허용 범위 |
|---|---|
| rights | 주식·SPY·기업행동, Finnhub 공시, 구성원·산업의 내부 연구 재사용 권리. 예전 수집·pilot 승인은 이번 권리를 대신하지 않는다. 원천 데이터 재배포·운영 승격은 금지한다. |
| identity | own-panel 분류, 날짜 있는 구성원 CIK, 신원 CSV CIK, 공개된 공시 CIK가 일치하는 범위. 개명·재사용·모호한 종목은 분모에 남기고 제외한다. |
| membershipIndustry | 엄격히 이전 날짜의 공개 재구성 스냅샷을 조건부로 수용하는지. 공식 당시 S&P 관측이라고 부르지 않으며 현재 산업으로 채우지 않는다. 금융·부동산은 제외한다. |
| returnBasis | 아래 현금 재투자 산식에 필요한 복원 as-traded 가격, 배당 통화·분할 후 주당 단위, 이벤트 누락 여부. 검증하지 못한 원천을 검증 완료로 표시하지 않는다. |
| terminal | 미확인 종결 대가·누락 가격을 해결 불가로 유지하는 범위. 현금 종결 자료를 추가한다면 신원·주당 기준·USD·정산일·당시 공개 시점·근거를 고정한다. |
| size | 공시 가중평균 주식수×당시 거래 가격을 **규모 대용치**로 수용하는지. 가시 시점과 주식분할을 검사하며 실제 시총이라고 부르지 않는다. |
| vintage | 2026년에 수집된 과거 자료의 공개일 재구성을 수용하는지. 2013~2020년에 실제 전향 수집한 자료라는 주장은 금지한다. |

보존 원천은 signal-history `1bf68f59cffa20239977e2cfaa0f35a07d0ec884`, 메타데이터는 `002b56434e3aa3e845798ec2ea7ca6d9267e3f7a`로 고정했다. manifest SHA와 모든 읽은 Git/component SHA를 확인한다. 기존 `Sources`의 로컬 Git 허용 목록만 사용하고 네트워크 자동 fetch·외부 수집·새 구독을 하지 않는다. **현재 로컬 partial clone에서는 필수 Git 객체 398개 중 254개가 없다.** `preview/admit/request`는 manifest와 `git cat-file --batch-check`의 객체 유형/크기만 확인하고 원천 본문을 열지 않는다. 소유자 댓글/시도 태그 생성 전에 동일 검사를 다시 적용하므로 캐시 결손으로 실행 승인을 소비하지 않는다. 필요한 보존 객체가 있는 실행 환경을 먼저 준비해야 하며 이번 PR에서는 가격 객체를 자동 복원하거나 수익률을 읽지 않았다. 가격/기업행동은 KR·범위 밖 종목도 포함하는 2011-01~2021-07 월간 객체 단위로 읽되 US 대상만 계산에 남긴다. 따라서 2021-07-06 이후 값도 같은 원본 객체 안에는 있으나 계산에는 쓰지 않는다. 공시는 2011~2021 회계연도 원본을 읽고 매 신호일 공개 prefix를 적용한다.

**가격 기준에서 확인한 구현상 차이:** 기존 replay 조정 지수의 배당 계수는 `1/(1-D/P_prev)`다. 이는 현금 배당을 그날 종가에 재투자한 경제적 수익과 일반적으로 같지 않다. 기존 코드는 변경하지 않고 `as_traded_from_total_return`로 원래 가격을 복원한 다음 주식과 SPY 양쪽에 `split × (P_t + D_post_split)/P_prev`를 적용한다. 세전·배당락일 종가 재투자 기준이며 ETF 비용은 원천 가격에 내재한다. 가격 결측·거래량 0은 장벽으로 남기고 교차하는 창을 보류한다. SPY는 보존 벤치마크 종가에 따른 유동 ETF 체결 가정을 사용하며 거래량을 만들어내지 않는다. vendor 계열·SPY symbol·조정 recipe lineage가 다르면 가격 본문을 열기 전에 중단한다. 단순 조정식 일치만으로 원천 가격/배당의 경제적 검증이 끝났다고 보지 않는다.

**조건부 범위:** `CURRENT_MEMBER_OWN_PANEL` 또는 `REMOVED_FROM_INDEX_STILL_TRADING`이며 날짜 있는 CIK가 일치하는 종목만 학습·평가한다. 당시 전체 구성원은 먼저 원장에 보존한다. 이 범위의 결과는 생존자/자체 가격 패널 조건부 탐색이다. 제외·결측 사유, 결과 미해결 수, 승자·손실률의 결측 경계, 통제군 탈락을 출력한다. 전체 시장의 수익 효과·상폐 민감도를 식별할 수 없으면 `UNRESOLVED`로 남긴다. 추가로 신원·종결 대가가 검증된 모집단 없이 그 편향이 해소됐다고 주장하지 않는다.

선택 사항인 `terminalSource`는 `/workspace/wid-inputs/` 아래 JSON의 `{path, sha256}`이다. ticker별 레코드에 `date`, `settlementDate`, `publicAt`, `kind: CASH`, `cashPerShare`, `verified: true`, `citation`, `securityIdentity`, `currency: USD`, `shareBasis: AS_TRADED_LAST_PRE_TERMINAL_SHARE`가 필요하다. 정산·공개가 라벨 경계를 넘거나 중간 주식수/배당 경로가 끊기면 해결하지 않는다. 검증된 현금 대가 0은 실제 전액 손실이며 누락치의 0 대체와 구분한다. 주식교환·혼합 합병·후속 ticker 대체는 지원하지 않는다. 현금 종결로 만기 자산이 확인돼도 일별 가격이 없으면 일별 MDD는 별도로 해결 불가다. 강제 현금 상환에는 재량 매도 비용을 붙이지 않는다고 명시한다.

## 단일 승인 절차

저장소 루트, 의존성이 설치된 Python 환경에서 실행한다. 모든 기본 명령은 preview다.

```bash
python scripts/run_winner_inflection.py
python scripts/run_winner_inflection.py synthetic
python scripts/run_winner_inflection.py admit --review /workspace/wid-inputs/review.json
```

1. 근거 검토가 끝난 `review.json`과 필요한 로컬 보존 객체로 `admit`를 통과시킨다. 코드 commit/worktree는 깨끗해야 한다. 실제 outcome 파일을 검토 근거로 열지 않고 원천 메타데이터·단위·이용권을 먼저 확인한다.
2. 다음 명령으로 검토할 **하나의 manifest**를 만든다. 차단 상태면 `approvalText`는 null이며 실행 승인 대상이 아니다.

```bash
python scripts/run_winner_inflection.py request \
  --review /workspace/wid-inputs/review.json \
  --run-root /workspace/wid-executions/us-b-h126-2020-v1 \
  > /workspace/wid-inputs/execution-request.json
```

3. 소유자가 manifest 전체와 근거 문서를 검토하고 이 저장소 PR/issue에 출력된 문구 **`APPROVE WID_EXECUTION <request.sha256>`만** 댓글로 남긴다. 이것이 실제 라벨 열람·고정 모델 학습에 대한 단일 명시적 승인이다. 코딩 승인·PR 승인·옛 봉인은 이 문구를 대신하지 않는다.
4. 댓글의 숫자 ID로 한 번 실행한다. `request` 출력 파일을 그대로 입력한다.

```bash
python scripts/run_winner_inflection.py execute \
  --request /workspace/wid-inputs/execution-request.json \
  --approval-comment OWNER_COMMENT_ID
```

실행 전 GitHub API로 소유자 계정·OWNER 관계·정확한 댓글·작성 시각을 확인한다. manifest는 전체 사양/근거 SHA, clean commit/코드 SHA, 런타임 버전, 기존 WID 시도 이력, 별도 출력 경로를 묶고 7일 내에만 유효하다. 이후 변경되면 새 manifest와 승인이 필요하다. 승인 후 새 `wid-exploration-attempt-<spec.id>` 태그를 원자적으로 한 번 생성한 다음 입력을 연다. 기존 봉인·태그·영수증은 수정하지 않는다. 이 준비 PR은 승인 댓글·시도 태그를 생성하지 않는다.

출력은 `/workspace/wid-executions/<run>/`의 `universe/`, `features/`, `labels/`, `decisions/`, `evaluation/`로 분리하고 덮어쓰지 않는다. 원천 영수증·시작/완료/실패 기록을 남기며 2020 예측을 먼저 고정·저장한 다음 평가 라벨을 계산한다. CPU 1,800초·주소 공간 8GiB가 상한이다. 입력/표본 관문 실패도 시도로 기록한다. 강제 종료 시 완료 기록이 없어도 시작 기록·원격 태그가 남아 재실행을 차단한다. 자동 재시도·임계값 완화·원천 대체는 없다.

후속 A/C 또는 사후 변경은 다른 spec ID·변경 이유·새 승인을 사용한다. 기존 WID 시도 태그가 하나라도 있으면 다음 사양은 `resultInformed: true`여야 한다. 같은 역사를 독립 OOS로 부르지 않는다. 예상 비용은 원격 승인 검증·시도 태그 등록 외 데이터 API/구독 비용 0이며 실제 CPU/메모리는 승인 실행의 상한 내에서만 측정한다. 연구 결과는 자동으로 실전 신호가 되지 않는다.

## 검증

합성 입력에서 다음 거래일/휴장/DST/조기 마감, 126거래일 만기, 공개 전 라벨 차단, proper-fit/보정 purge, 미래 가격·공시·라벨 오염 불변성, 신원/중복, 주식분할·배당·비용 계산, 종결 0과 결측의 구분, 동일 표본 비교, 별도 파일 계층, 소유자 승인·변경/재실행 차단을 검사한다. 실제 성과 수치는 이 문서에 없다. 실행 후 검증 가능한 지표만 출력하며 설명 가능한 실패도 탐색 결과로 기록한다.

전체 회귀 1회는 5,205 passed / 1 skipped / 4 xfailed였다. 이후 보완한 관문을 포함한 실행기·기존 WID/Workbench 합성/승인 회귀 111개도 통과했다. 36개 가상 기업을 쓰는 CLI 리허설은 약 22.24초·최대 RSS 230.39MiB였으며 실제 데이터 비용 추정치나 연구 성과가 아니다. `ruff`, compileall, seed 생성/preview 검증, synthetic seed의 production 거부도 확인했다. 실제 역사 라벨 파생·학습은 0회다.
