# rp1-c1 US 실행 직전 소유자 패킷 (비승인 문서)

**이 문서는 아무것도 승인하지 않는다.** 실행 승인은 §3의 승인 파일을 소유자가 직접 작성해 검토된 PR로 병합하고, 그 SHA-256을 execute dispatch에 입력할 때에만 생긴다. 이 문서는 동결 연구(`rp1-c1-us-exposure-ladder-replication-v1`)의 사양, 원천 동결 #255, 실행기, 해석표를 하나도 바꾸지 않는다. 데이터 원천, 임계값, 비용, 기간도 바꾸지 않는다. 동결 연구 문서 [`rp1-c1-us-exposure-ladder-replication.md`](rp1-c1-us-exposure-ladder-replication.md)는 사양에 해시로 고정돼 있으므로 이 문서로 보충한다.

기준 시점: 2026-10-22, `main` `7b0dbad`. 미국 가격·수익률·상태·경로는 읽지 않았다.

## 1. 실행 준비 판정

**`READY_EXCEPT_OWNER_ACTIONS`.** 기계 쪽 차단 요인은 없다. 남은 것은 소유자 행위 세 가지다: §4의 위험예산 결정 기록, §3의 승인 파일, 최신 dry-run과 execute의 dispatch.

| 항목 | 상태 | 근거 |
|---|---|---|
| 사양 신원 | `VERIFIED` | `run_rp1_c1_us_exposure.py verify`를 현재 main에서 실행했다. spec `4106709c…0127`, scientific `ad454ebb…5252`, 의존 파일 84개 해시 일치, `usSnapshotPinned: true`, US 값 카운터 0 |
| 사양 재생성 | `SPEC_REPRODUCED` | `build_rp1_c1_us_exposure_spec.py --check` |
| 원천 동결 | `FROZEN` | 매니페스트 `sources/rp1-c1-us-source-freeze-39080239146.json`, sha256 `de23b67b…1ed0`, 동결 당시 readiness READY, blocker 0 |
| #255 이후 하네스 변경 | 없음 | `9b237ca..main` 사이에 `pipeline/rp1_c1_us_*.py`, `scripts/run_rp1_c1_us_wp4d.py`, 호스트 워크플로, 사양, 원천, 승인 디렉터리 변경 0건 |
| KR 동등성 | `EXACT` | 현재 main의 로컬 dry-run |
| 승인 파일 | `NOT_ISSUED` | 템플릿(`authorizes: NOTHING`)만 있다 |
| 결과·마커 | 없음 | `docs/research-program/results/`에 rp1-c1 결과·마커 없음 |
| 잠금 ref | 없음 | `git ls-remote origin 'refs/tags/rp1-c1*'` 결과 0건 |
| C1 테스트 | 통과 | `pytest -q tests/test_rp1_c1_us_wp4d.py tests/test_rp1_c1_us_exposure.py` |

## 2. dry-run 증거

### 2.1 실제 재취득 dry-run: run 39081014704 (#255 병합 시 자동 실행, SUCCESS)

[job 117537771295](https://github.com/jaehojung1879-netizen/Investment/actions/runs/39081014704/job/117537771295), 2026-10-17T23:58Z, head `9b237ca`. 하네스 바이트는 현재 main과 같다.

- 재취득: 4개 원천 모두 HTTP 200. YAHOO_GSPC 9,245행, FRED_SP500 2,493행, YAHOO_SPY 8,466행, FRED_DTB3 9,184행.
- `verify-snapshot`:
  - `PRIMARY: MATCHED`
  - `CASH_ECONOMIC: MATCHED`
  - **`VENDOR_ECONOMIC: BLOCKED_HASH_MISMATCH`**
  - FRED_SP500 교차검증 `CONSISTENT`(공통일 2,493, 불일치 0.0)
- dry-run 결과:
  - readiness `READY_FOR_RP1_C1_FORMAL_EXECUTION`, blocker 0, `snapshotIdentity: MATCHES_THE_FROZEN_MANIFEST`
  - 동등성 `EXACT`
  - 합성 파이프라인 검증기 236개 대조 `CONSISTENT`
  - `lockClaimed: false`, `usValueReads: 0`, 모든 카운터 0
  - `readyToExecute: false`(승인 파일 `NOT_ISSUED`)

`VENDOR_ECONOMIC` 불일치의 의미: 정식 실행에서 원래 vendor 경제성 독해(SPY adjclose + DTB3)는 실행기 규칙상 `ECONOMIC_READING_UNRESOLVED`가 된다(`readiness_audit`의 scope 처리). PRIMARY와 CASH_ECONOMIC은 영향을 받지 않는다. 결과를 보기 전에 재동결해 이 독해를 살리려 하지 않는다(§4 D7).

### 2.2 현재 main의 로컬 점검 (2026-10-22)

- `run_rp1_c1_us_wp4d.py dry-run`(스냅샷 없음, 이 환경은 공급자에 접근할 수 없다):
  - 동등성 `EXACT`, 합성 236개 대조 `CONSISTENT`
  - readiness는 의도대로 `NO_SNAPSHOT_DIRECTORY_GIVEN`
  - 카운터 전부 0
- **정식 실행이 실제로 탈 경로의 합성 점검.** 공식 dry-run은 합성 값에서 vendor 경제성을 켠 경로만 돈다. 실제 실행은 2.1 때문에 `economic_ready=False` 경로를 타고, CASH 경로에서 `cash_reinvestment_close`를 거친다. 이 경로는 잠금 뒤에 실행되며, 여기서 오류가 나면 PRIMARY 결과도 쓰이기 전에 연구가 소진된다. 그래서 잠금 뒤 구간(`evaluate_and_validate(economic=False)` → `cash_reinvestment_close` → `cash_economic_result` → `interpretation` → 금지 키 검사 → `render_report`)을 지어낸 값으로 돌렸다. 지어낸 값은 실제 XNYS 1993-01-29~2026-09-17 세션 8,466개, 배당 135건, 분할 0건이다. 결과: PRIMARY 검증 `CONSISTENT`, CASH `MEASURED`, CASH 검증 236개 `CONSISTENT`, 보고서 섹션 4개(PRIMARY, CASH, 재진입, 결정). 시장에 대한 결과가 아니다.

### 2.3 최신 dry-run dispatch: 이 세션에서는 불가

`rp1_c1_action=dry-run` dispatch가 `403 Resource not accessible by integration`으로 거부됐다. 이 세션 토큰의 권한 문제이며 원천이나 설계의 차단 요인이 아니다. 소유자가 §5 1단계로 실행한다.

## 3. 승인 파일 작성 절차 (소유자 전용)

현재 pin(`authorization-draft --owner jaehojung1879-netizen` 출력, **비승인 초안**). 정본은 소유자가 실행할 때 명령이 내는 출력이다. 아래 표는 대조용이다.

| pin | 값 |
|---|---|
| `specSha256` | `4106709c48690a230e6ee07c782a5ea2d3374b3e8780bf31ecbdad97b0a00127` |
| `scientificSha256` | `ad454ebbf2d7f0834b9de8ac136ba7842855d49146dbf1b123e1538fdc615252` |
| `cashEconomicScientificSha256` | `50f1bbbdf671eeb5616e30ffef0475ec7a01bd171480cbb740052a4b748fc3e5` |
| `sourceFreeze.manifestSha256` | `de23b67b75ad3d33b3ca1d62d98a42d9e7c8f103e347df4759dd7140472f1ed0` (run `39080239146`) |
| harness `.github/workflows/seal-kr-factor-anatomy-v1.yml` | `dcf93e3d19f0372ad7fd6d29efee6fd7f932156bf6095789e6601e0693e5edcf` |
| harness `pipeline/rp1_c1_us_execution.py` | `3790c0ee359dd14cf93ffee82d714af374b724569e8b26620d1596d3283102e0` |
| harness `pipeline/rp1_c1_us_validator.py` | `9d434932d494f7d8835cd4b6a1b86f4d3f62e60cfe85e28e1b642bcb06444e19` |
| harness `scripts/run_rp1_c1_us_wp4d.py` | `d2f14e8c7b682188e63673d88fa44166e9bccf0a62bba729a779b795b0ffd5d7` |

`sourceFreeze`에는 위 값 외에 `analysisFiles`(17개), `scopedInputs`(PRIMARY / VENDOR_ECONOMIC / CASH_ECONOMIC), `normalization`(계약과 코드 해시 11개)이 함께 들어간다. 손으로 옮기지 말고 명령 출력을 그대로 쓴다.

**확인사항 8개.** 초안에서는 모두 `false`다. 소유자가 각각 읽고 직접 `true`로 바꾼다.

| 키 | 소유자가 확인하는 내용 |
|---|---|
| `frozenRuleReplicationNotValidation` | 이 실행은 동결 규칙의 복제이며 검증이 아니다 |
| `publiclyKnownUsHistory` | 1993~2026 미국 역사는 이미 공개된 표본이다. 독립 OOS가 아니다 |
| `oneShotFailureAfterTheLockConsumesTheStudy` | 잠금 뒤 실패는 연구를 소진하며 재시도하지 않는다 |
| `noThresholdWindowRuleOrCandidateChangeAfterTheResult` | 결과를 본 뒤 임계값, 창, 규칙, 후보를 바꾸지 않는다 |
| `noProductionOrPortfolioChange` | 결과가 운영 시스템이나 실사용 포트폴리오를 바꾸지 않는다 |
| `licensedSourceBytesStayRunnerTemporaryAndNeverPublished` | Yahoo/S&P 원자료는 runner 임시 저장소에만 있고 게시하지 않는다 |
| `economicReadingIsDescriptiveAndCannotChangeTheDecision` | 경제적 독해는 서술용이며 결정을 바꿀 수 없다 |
| `separateCashEconomicSpecReviewed` | 별도 CASH 정의(`rp1-c1-spy-cash-reinvestment-economic-v1`, 분할 부재 요구, 외부 총수익 미대조)를 검토했다 |

절차:

1. 최신 main에서 실행한다: `python scripts/run_rp1_c1_us_wp4d.py authorization-draft --owner jaehojung1879-netizen --output /tmp/auth.json`. 그 pin을 위 표, 그리고 §5 1단계에서 받은 최신 dry-run 결과와 대조한다.
2. 8개 키를 직접 `true`로 바꾼다. `ownerLogin`은 dispatch할 계정과 정확히 같아야 하고(`OWNER_DISPATCH_REQUIRED`), `authorizes`는 `ONE_FORMAL_EXECUTION` 그대로 둔다. 다른 필드는 건드리지 않는다.
3. `docs/research-program/authorizations/rp1-c1-us-exposure-execution-authorization.json`에 저장하고 검토된 PR로 병합한다. §4의 결정 기록도 같은 PR이나 그 이전 PR에 넣는다. 템플릿 파일은 그대로 둔다.
4. 병합 뒤 main에서 `sha256sum docs/research-program/authorizations/rp1-c1-us-exposure-execution-authorization.json`을 실행하고 그 값을 기록한다.
5. 승인 PR 병합과 execute dispatch 사이에 main에 **다른 병합이 없어야 한다.** 실행기는 dispatch 커밋이 main 끝인지, 승인 파일과 사양이 그 커밋에 있는지 확인한다. 하네스, 사양, 원천 매니페스트 중 하나라도 바뀌면 pin이 어긋나 잠금 전에 거부된다. 이때 소진은 없지만 승인 파일을 다시 써야 한다.

## 4. 결과 열람 전 소유자 결정 사항 (미기입)

동결 해석표의 첫 행(`REPLICATED_CONTROL_RETAINED`)은 "기본값은 지수 100%, C0는 명시적 위험 예산이 있을 때만"이다. 위험예산은 결과를 보기 전에 적혀 있어야 의미가 있다. 아래 칸은 **소유자만 채운다.** 비어 있으면 미결정이다. 미결정 상태로 실행하면 D2를 "없음"으로 읽는 것을 권장 기본 해석으로 둔다(소유자가 다르게 기입하면 그것이 우선). 권장안은 판단 근거일 뿐 결정이 아니다.

| ID | 결정 | 선택지 | 권장(근거) | 소유자 기입 |
|---|---|---|---|---|
| D1 | 미국 지수 노출 기본값 | PASSIVE 1.0(지수 100%) / 기타 | PASSIVE 1.0. 해석표의 모든 행이 이것을 기본값으로 둔다 | |
| D2 | 명시적 위험예산이 있는가 | 없음 / 있음 | 소유자 판단. 없으면 결과와 무관하게 C0를 적용하지 않고, 결과는 정보와 전향 기록용이다 | |
| D3 | (D2=있음) 예산의 형식과 수치 | (a) 허용 최대낙폭 \|MDD\| ≤ L% (b) 수용 가능한 연 상승장 비용 ≤ U %p/yr (c) 둘 다 | 둘 다 숫자로 쓴다. 해당 지표는 보고서에 이미 있다(MDD, `upMarketCostPerYear`) | L= / U= |
| D4 | 예산을 어느 독해로 판정하나 | PRIMARY(가격지수, 현금 0%) / CASH_ECONOMIC(SPY 현금배당 재투자 + DTB3) | CASH_ECONOMIC. 실제 자금의 경제성은 배당과 현금 수익을 포함한다. 동결 결정은 계속 PRIMARY만 쓴다 | |
| D5 | D4 독해가 UNRESOLVED일 때 | 예산 판정 UNRESOLVED(C0 미적용) / PRIMARY로 대체 | UNRESOLVED. 유리한 독해 고르기를 금지하는 C.9와 같은 원칙 | |
| D6 | 적용 범위 | 미국 지수/ETF 부분만 / 종목 책 포함 | 지수/ETF만. 종목 책은 C2 별도 연구이고 배수는 {1.0, 0.7, 0.4}, 레버리지 없음 | |
| D7 | 원래 vendor 경제성 UNRESOLVED 수용 | 수용 / 실행 전 재동결 | 수용. adjclose는 공급자가 소급 재조정하는 계열이며 동결(run 39080239146) 약 13분 뒤 재취득에서 이미 불일치했다. CASH_ECONOMIC이 그 대체로 별도 고정돼 있다 | |
| D8 | `NO_PROTECTION_IN_US` 조건과 다른 판독이 함께 나올 때 | 미국 노출층 없음 우선 / 판독 문자열 우선 | 노출층 없음 우선. 수동보다 MDD를 줄이는 후보가 없으면 예산으로 살 보호가 없다. 실행기는 판독 옆에 `noProtectionInUs`를 따로 보고한다 | |
| D9 | 결과 이후 실사용 반영 | 별도 결정과 전향 기록(C1d) 후 / 즉시 | 별도 결정. 승인 확인사항 `noProductionOrPortfolioChange`와 해석표의 "never production"에 따른다 | |

해석표를 기계적으로 적용한 결과(D 결정과 독립):

| 동결 판독 | 프로그램 결론 | 위험예산의 역할 |
|---|---|---|
| `REPLICATED_CONTROL_RETAINED` | 노출층은 위험 선호 선택지다. 이 층의 규칙 탐색을 종료한다 | D2=있음이고 D3 한도를 D4 독해로 충족할 때만 C0가 적용 **후보**가 된다(D9) |
| `NOT_REPLICATED_US_NOMINATION` | 승격 없음. C0와 미국 지명 후보를 함께 전향 기록한다 | 없음 |
| `NOT_REPLICATED_US_TRADEOFF` | 지명 없음. 모든 후보를 전향 기록한다 | 없음 |
| `noProtectionInUs: true` | 미국 노출층 없음(D8) | 없음 |

## 5. PRIMARY와 경제성 독해의 분리

| 독해 | 자산 / 현금 | 결정 권한 | 정식 실행에서의 예상 상태 | 쓰지 않는 문장 |
|---|---|---|---|---|
| PRIMARY | ^GSPC 가격지수 / 현금 0% | **유일한 결정 근거**(동결 파레토 규칙, 미국 비용 1×) | 해시 `MATCHED`, readiness READY | "투자 가능한 수익률", "ETF 경제성 검증 완료" |
| 원래 vendor 경제성 | SPY Yahoo adjclose / DTB3 | 없음(서술) | `ECONOMIC_READING_UNRESOLVED`(2.1) | 이 독해의 부재를 실패나 PRIMARY 결함으로 읽는 것 |
| CASH_ECONOMIC | SPY 원종가 + ex-date 현금배당 재투자 / DTB3(지연 4일, 14일 정체 규칙) | 없음(서술). 다만 §4 D4의 위험예산 판정 근거로 지정할 수 있다 | `MATCHED`, `CASH_ECONOMIC_READY` | "SPY 총수익과 일치", "vendor 오류", 외부 총수익 대조 완료 |

두 독해의 표는 보고서에서 별도 섹션으로 나온다. 하나를 다른 하나로 대체하거나 둘을 섞어 평균하지 않는다. 현금 0%와 T-bill 결과 중 유리한 쪽만 인용하지 않는다(C.9).

## 6. 실제 execute까지 남은 단계

1. **최신 dry-run(소유자, 비소진).** Actions → `Seal KR factor anatomy v1 result` → Run workflow → branch `main` → `rp1_c1_action = dry-run` → 승인 SHA 칸은 비워 둔다. 통과 조건(job 로그):
   - `verify-snapshot`: `PRIMARY: MATCHED`, `CASH_ECONOMIC: MATCHED`, 교차검증 `CONSISTENT`
   - dry-run: readiness `READY_FOR_RP1_C1_FORMAL_EXECUTION`, 동등성 `EXACT`, 합성 `CONSISTENT`, `usValueReads: 0`
   - `VENDOR_ECONOMIC: BLOCKED_HASH_MISMATCH`는 예상된 상태다.

   PRIMARY나 CASH가 불일치하면 거기서 멈춘다. 재동결, 허용 오차, 원천 대체는 자동으로 하지 않으며 별도 판단 사항이다.
   **`none`(기본값)을 고르지 않는다.** `none`은 원래 KR 봉인 작업을 돌린다.
2. **결정 기록과 승인 파일(소유자).** §4를 채운다. §3 절차로 승인 파일을 만들어 검토된 PR로 병합한 뒤 SHA-256을 기록한다.
3. **execute(소유자 1회).**
   - 설정: 같은 워크플로, branch `main`, `rp1_c1_action = execute`, `rp1_c1_authorization_sha256 = <4단계 값>`.
   - 조건: 저장소 소유자 계정이 첫 시도로 실행한다. 승인 병합 직후, 다른 병합이 끼기 전이어야 한다.
   - 실행 순서: 승인 확인 → 재취득 → exact hash → readiness와 동등성 → 원자적 잠금 ref 2개 → 마커 → 실제 값.
   - 잠금 전 거부는 아무것도 소진하지 않는다. 잠금 뒤 실패는 연구를 소진하며 재실행하지 않는다.
   - job 요약의 `STUDY LOCKED` / `Stopped before the lock`으로 어느 쪽인지 확인한다.
4. **결과 봉인.** `rp1-c1-us-exposure-results-<run>` artifact(90일)와 로그의 gzip+base64 사본을 정확한 바이트로 봉인하는 Draft PR을 연다. 판독은 해석표와 §4 결정으로 기계적으로 적용한다. 임계값 수정, 자동 승격, 운영 변경은 없다.

남은 잔여 위험(설계상 수용):
- 공급자가 1990~2026-09-17 구간을 소급 수정하거나 접근을 거부할 수 있다. 이 경우 잠금 전에 거부된다.
- CASH 경로는 잠금 뒤에 계산되며, 오류가 나면 PRIMARY 결과도 쓰이기 전에 소진된다. 2.2의 합성 점검으로 실제 형태의 경로가 통과함을 확인했다.
