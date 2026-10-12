# Finnhub 재무상태표 라이브 프로브 — 소유자 실행 안내 (v1)

**상태: `PENDING_OWNER_DISPATCH`. 실제 공급자 응답은 아직 측정되지 않았다.** 이 문서와 PR은 실행 경로를 준비했을 뿐이다. 판정을 지어내지 않았고,
수집·백필·알파 계산도 하지 않았다.

PR #233이 남긴 질문은 이것이다. 2026-10-07부터 처음 서빙된 Finnhub 공시 619건에 재무상태표가 없는 이유가 (A) 공급자가 빼서 보냈기 때문인가,
(B) 공급자가 수집기가 읽지 않는 키로 옮겼기 때문인가, (C) 공급자가 나중에 채웠는데 수집기가 버렸기 때문인가? 저장본으로는 가를 수 없다. 진짜 응답
한 번이 가른다.

## 0. 왜 아직 실행되지 않았는가

1. **워크플로가 `main`에 없다.** 비밀(`FINNHUB`)을 쓰는 코드는 검토되지 않은 PR 브랜치에서 돌릴 수 없다. 이 PR의 변경은 병합된 뒤에만
   dispatch 대상이 되고, 잡 자체도 `main`이 아닌 ref에서는 건너뛴다.
2. **이 작성 환경에는 키도, `finnhub.io`로 가는 경로도 없다.** 그리고 이 세션의 토큰으로는 `workflow_dispatch`가 403이다(이전 PR에서도 같았다).
3. 실행을 명시적으로 승인받지 않았다.

그래서 이 PR은 소유자 승인 문턱에서 멈춘다. 같은 저장된 레코드로 만든 **계획 전용(호출 0회) 결과**만 포함한다:
`docs/us-readiness/us-finnhub-balance-sheet-probe-plan-v1.json` (`verdict: PENDING_NO_CALLS_MADE`).

## 1. 왜 새 워크플로 파일이 아니라 `fundamentals.yml` 확장인가

- **새 워크플로 파일은 봉인 의존성을 깬다.** `tests/test_kr_alpha_atlas_price_repair_workflow_inventory.py`(해시 고정)는 `.yml`·`.yaml`
  모두에 대해 "디스크의 워크플로 == 고정된 네 인벤토리 문서의 ACTIVE 표"를 정확히 요구한다. 그 문서와 테스트는 봉인된 사양이 해시로 고정해서
  고칠 수 없으므로, 어떤 새 파일이든 이 테스트를 깬다. `.yaml` 확장자 우회도 막혀 있다.
- **`probes.yml`은 확장할 수 없다.** 봉인된 사양 두 곳이 그 해시(`2c00464e…`)를 고정한다.
- **`fundamentals.yml`은 고정되어 있지 않고, 이미 같은 방식의 선례가 있다.** `target=raw-*`가 일일 수집기를 건너뛰고 별도 잡 `kr-raw`만 돌린다.
  같은 방식으로 `region` 선택지에 `finnhub-bs-probe`를 하나 추가했다. 기존 `kr`·`us`·`kr-raw` 잡의 조건식은 한 글자도 바뀌지 않았고,
  새 값은 어느 수집기의 조건과도 맞지 않는다. 그래서 이 선택지로는 수집이 시작될 수 없다(테스트가 모든 이벤트·ref 조합을 계산해 확인한다).

## 2. 안전장치

| 항목 | 내용 |
|---|---|
| 실행 주체 | `workflow_dispatch`만. 스케줄은 `region`을 보내지 않으므로 이 잡을 절대 고르지 못한다. |
| 실행 ref | `main`만. 다른 ref는 `if`에서 건너뛴다. 병합되지 않은 코드에는 비밀이 가지 않는다. |
| 권한 | 잡 자체의 `contents: read`(워크플로 기본값은 `write`). 두 번의 체크아웃 모두 `persist-credentials: false`. |
| 저장소 쓰기 | 없음. 이 잡에는 `git push/commit/add/config`가 없고, signal-history는 `ledger/fundamentals/us`만 sparse로 읽는다. |
| 비밀 | `secrets.FINNHUB`가 **한 단계의 환경변수**에만 간다. `max_calls=0`이면 그 값도 비운다. 로그는 GitHub이 마스킹하고, 스크립트도 출력에 키가 있으면 쓰기를 거부한다. |
| 입력 | `max_calls`는 쉘에 보간하지 않고 환경변수로 받아 숫자만 허용한다. 자유 인자(`args`)는 없다. |
| 호출 수 | 기본 12회, 하드 상한 20회(스크립트가 강제). 요청 한 번이라도 거부(HTTP 4xx/5xx, 속도 제한)되면 바로 멈춘다. |
| 샘플 | 저장된 레코드에서 정한다: 같은 응답 창에 "재무상태표 있는 Q1"과 "없는 Q2"가 함께 오는 종목 10개(분기 요청)와 "없는 10-K" 종목 2개(연간 요청). 종목은 티커의 솔트 해시 순서(고정된 의사난수)로 골라 손으로 고르지 않는다. |
| 증거 | 정제된 보고서(`finnhub-bs-probe-report`, 90일)와 원본 응답(`finnhub-bs-probe-raw-restricted`, **7일**)을 **별도 아티팩트**로 올린다. 요약에는 값이 없다. |
| 동시성 | 워크플로 전체의 그룹(`signal-history-fundamentals`)을 공유한다. 야간 수집과 겹치면 뒤에 대기하고, 대기 중 새 실행이 오면 대기분이 취소될 수 있다. |

한계를 숨기지 않는다. GitHub 아티팩트는 개별 접근 제어가 없어서 저장소 읽기 권한자는 원본 응답을 받을 수 있다. 그래서 7일 보존과 별도 아티팩트로
줄였고, 응답 본문에는 키가 들어 있지 않다(키는 URL 쿼리에만 있고 저장하지 않는다). 공급자 약관상 재배포가 문제라면 원본 아티팩트를 받은 뒤 지워도 된다.

## 3. 소유자가 할 일 (병합 후)

1. 이 PR을 검토하고 병합한다. 병합은 소유자의 결정이다. 병합해도 수집은 시작되지 않는다. (참고: 병합하면 이전 PR의 건전성 기록도 다음 야간 수집부터 같이 켜져 있다.)
2. **계획 확인(키를 쓰지 않음):** Actions → *Collect fundamentals* → Run workflow →
   `region = finnhub-bs-probe`, `target = auto`, `max_calls = 0`. 저장 데이터를 읽어 실제로 보낼 요청 12개를 보고서에 적고 끝난다. 호출 0회, 비밀 0회.
3. **실제 측정:** 같은 화면에서 `max_calls`를 **비워서**(기본 12회) 실행한다. 약 1분이 걸린다.
4. 실행이 끝나면 아티팩트 `finnhub-bs-probe-report`의 `probe-report.json`에서 `verdict`, `category`, `evidence`, `nextRepairPath`를 확인한다.
   원본(`…-raw-restricted`)은 이후 파서 수정이 필요한 경우의 근거이므로 7일 안에 필요하면 받아 둔다.
5. 결과를 알려 주면 아래 표의 경로 가운데 **정확히 하나**를 다음 PR로 진행한다.

## 4. 판정과 다음 경로

| 판정(`category`) | 어떤 응답이 이것을 만드는가 | `verdict` | 다음 경로 |
|---|---|---|---|
| `VENDOR_OMITTED` (공급자가 뺐다) | 같은 응답에서 Q1은 재무상태표가 있고 Q2는 `bs`가 비었거나 없으며, 어디에도 재무상태표 같은 키나 `Assets`가 없다 | `VENDOR_OMITS_BALANCE_SHEET_FOR_NEWLY_SERVED_FILINGS_ONLY` | **S3_BLOCKED_SOURCE.** 값은 복구하지 않는다. Finnhub에 새로 서빙된 공시의 `bs` 누락과 백필 계획을 묻고, 필요하면 재무상태표만 주는 두 번째 공급자를 평가한다. 전향 신호는 계속 측정 불가. |
| `VENDOR_OMITTED` | Q1도 이제 `bs`가 없다. 9월에는 있던 공시까지 빠졌다 | `VENDOR_OMITS_BALANCE_SHEET_ENDPOINT_WIDE` | **S3_BLOCKED_SOURCE.** 엔드포인트 전체의 변경이다. 같은 문의와 대체 소스 평가. 야간 수집기는 손익·현금흐름만 계속 저장한다. |
| `VENDOR_MOVED_FIELD` (공급자가 옮겼다) | Q2에 `bs`가 없는데 재무상태표 같은 키가 있거나 `Assets`가 다른 섹션에 있다 | `BALANCE_SHEET_FOUND_UNDER_ANOTHER_KEY` | **S2_SUPPLEMENT.** 먼저 별도 검토 PR로 `build_record`가 그 키를 읽게 고친다(원본 응답을 근거로 한 테스트 포함). 그다음 유계 보완 수집(≤700콜)을 새 append-only 가족에 쓴다. 저장된 샤드는 건드리지 않는다. |
| `VENDOR_LATER_COMPLETED` (나중에 채워졌다) | 저장본에는 비어 있던 Q2를 이번 응답이 재무상태표와 함께 준다 | `SERVED_NOW_COMPLETION_AVAILABLE` | **S2_SUPPLEMENT.** 보완 수집기를 만들어 보완 행을 새 가족에 쓴다. 보완 행은 공급자가 서빙한 날부터만 보이고(공시일로 소급하지 않음) 동결된 특징 경로는 읽지 않는다. 쓰려면 새 특징 계약 버전(P5)이 필요하다. |
| `INSUFFICIENT_EVIDENCE` (증거 부족) | 거부·속도 제한·비JSON으로 중간에 멈췄거나, 저장본과 짝이 되는 공시가 응답에 없었다 | `INCONCLUSIVE` | S2를 시작하지 않는다. 같은 절차를 다른 표본(또는 호출 수 상향, 상한 20)으로 한 번 더 한다. |
| `PENDING_OWNER_DISPATCH` | 아직 호출하지 않았다(지금 상태) | `PENDING_NO_CALLS_MADE` | 위 3단계. |

## 5. 하지 않은 것 (그리고 하지 않을 것)

- 프로덕션 백필, 자동 수집, signal-history·프로덕션 재무 쓰기, 보완 행 작성.
- 특징 계산(`us_cash_profitability.py`)·PIT 가시성·역사 데이터의 변경. 해당 파일의 해시는 불변이다.
- 알파·IC·수익률 계산. 봉인 결과와 Codex의 가격 수집기·진단 파일 수정.
- 키를 우회하거나 출력하는 일. 이 세션은 어떤 호출도 하지 않았다.

## 6. 검증

`tests/test_finnhub_balance_sheet_probe_workflow.py`가 다음을 고정한다.

- 모든 이벤트·ref·입력 조합에서 어떤 잡이 도는지를 조건식으로 계산한다. 야간 실행과 기본 dispatch는 그대로이고, 프로브 선택지로는 `main`의 프로브 잡만 돈다.
- 프로브 잡의 읽기 전용 권한, 키가 가는 단계 하나, 쉘 보간 없음, 아티팩트 분리와 보존 기간.
- 통제된 응답으로 네 가지 결과가 각각 도달 가능함, 한 번의 거부로 멈춤, 증거 부족은 추측이 아님.
- 키가 출력에 들어가면 쓰기를 거부함, 저장소 바이트 불변, 호출 상한 12/20.
- `fundamentals.yml` 변경은 `region` 선택지 한 줄과 새 잡뿐이고, `probes.yml`·인벤토리 문서·봉인 파일은 그대로임.
