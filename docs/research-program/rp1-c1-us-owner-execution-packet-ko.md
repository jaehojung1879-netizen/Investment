# rp1-c1 US 소유자 승인 패킷

이 PR에는 승인 파일 **초안**이 들어 있다. 8개 확인사항이 모두 `false`라서 아직 아무것도 승인하지 않는다(`authorize`는 `OWNER_SCOPE_OR_ACKNOWLEDGMENT_MISSING`으로 거부한다). 실행 승인이 생기는 조건은 세 가지다.

1. 소유자가 8개 값을 직접 `true`로 바꾼다.
2. 이 PR을 병합한다.
3. 그 파일의 SHA-256을 execute dispatch에 직접 입력한다.

동결 연구(`rp1-c1-us-exposure-ladder-replication-v1`)의 사양, 원천 동결, 실행기, 임계값, 해석표는 바꾸지 않는다. 미국 가격, 수익률, 상태, 경로도 읽지 않았다.

## 1. 현재 상태 (main `95c56e1`, 2026-10-24)

| 항목 | 상태 | 근거 |
|---|---|---|
| dry-run | 통과 | [run 40048379478](https://github.com/jaehojung1879-netizen/Investment/actions/runs/40048379478) (소유자 dispatch, head `95c56e1`) |
| 원천 재취득 | 4개 모두 HTTP 200 | GSPC 9,245행, FRED_SP500 2,488행, SPY 8,466행, DTB3 9,184행 |
| `verify-snapshot` | `PRIMARY: MATCHED`, `CASH_ECONOMIC: MATCHED`, FRED_SP500 교차검증 `CONSISTENT` | 같은 run |
| 원래 vendor 경제성 | `VENDOR_ECONOMIC: BLOCKED_HASH_MISMATCH` | 미해결로 둔다(결정 D7) |
| readiness | `READY_FOR_RP1_C1_FORMAL_EXECUTION`, blocker 0 | snapshot `MATCHES_THE_FROZEN_MANIFEST` |
| KR 동등성 | `EXACT` | |
| 합성 검증 | 236개 대조 `CONSISTENT` | |
| 카운터 | `usValueReads` 0, `lockClaimed: false` | |
| 사양 | `verify` `VERIFIED` (spec `4106709c…0127`), `--check` `SPEC_REPRODUCED` | 로컬, main `95c56e1` |
| 원천 동결 | `FROZEN` | manifest `sources/rp1-c1-us-source-freeze-39080239146.json`, `de23b67b…1ed0` |
| 잠금 ref | 0개 | `refs/tags/rp1-c1*` |
| 결과·마커 | 없음 | |

## 2. 결과 열람 전 결정 기록

소유자가 제시한 권고안을 정리한 것이다. **이 PR이 병합되는 시점에 소유자의 결정으로 확정된다.** 병합 시각은 git 기록에 남고, 잠금과 결과보다 앞선다. 결과를 본 뒤에는 바꾸지 않는다.

| ID | 결정 | 확정 내용 |
|---|---|---|
| D1 | 미국 지수 노출 기본값 | 미국 지수 ETF 100%(PASSIVE 1.0) |
| D2 | 별도 위험예산 | **없음.** 어떤 결과가 나와도 C0를 실사용에 적용하지 않는다 |
| D3 | 예산 수치 | 해당 없음(D2) |
| D4 | 판정 근거 | **PRIMARY만이 동결 규칙의 유일한 판정 근거.** CASH_ECONOMIC은 보조 경제성 독해이며 판정을 바꾸지 않는다 |
| D5 | 판정 독해가 UNRESOLVED일 때 | 해당 없음(D2). PRIMARY가 미해결이면 동결 규칙대로 결론을 내지 않는다 |
| D6 | 적용 범위 | 해당 없음(D2) |
| D7 | 원래 vendor 경제성 | `ECONOMIC_READING_UNRESOLVED`를 수용한다. 실행 전 재동결하지 않는다 |
| D8 | `NO_PROTECTION_IN_US`가 성립할 때 | 다른 판독보다 **미국 노출층 없음**이 우선한다 |
| D9 | 실제 포트폴리오 반영 | 결과가 무엇이든 **별도 승인 이후에만** 가능하다. 이 실행으로는 아무것도 바뀌지 않는다 |

이 결정을 해석표에 적용하면 다음과 같다.

| 동결 판독 | 프로그램 결론 |
|---|---|
| `REPLICATED_CONTROL_RETAINED` | 노출층은 위험 선호 선택지로 남는다. 예산이 없으므로 C0는 적용하지 않고, 이 층의 규칙 탐색을 종료한다 |
| `NOT_REPLICATED_US_NOMINATION` / `..._TRADEOFF` | 승격하지 않는다. 후보를 전향 기록한다 |
| `noProtectionInUs: true` | 미국 노출층 없음(D8) |

## 3. 소유자가 확인할 8개 항목

모두 `false`로 두었다. 소유자만 읽고 직접 `true`로 바꾼다.

| 키 | 뜻 |
|---|---|
| `frozenRuleReplicationNotValidation` | 이 실행은 동결 규칙의 재현이다. 검증이 아니다 |
| `publiclyKnownUsHistory` | 1993~2026 미국 역사는 이미 알려진 표본이다. 독립 표본이 아니다 |
| `oneShotFailureAfterTheLockConsumesTheStudy` | 잠금 뒤 실패하면 연구가 소진되고 재시도는 없다 |
| `noThresholdWindowRuleOrCandidateChangeAfterTheResult` | 결과를 본 뒤 임계값, 기간, 규칙, 후보를 바꾸지 않는다 |
| `noProductionOrPortfolioChange` | 이 결과로 운영 시스템이나 실제 포트폴리오를 바꾸지 않는다 |
| `licensedSourceBytesStayRunnerTemporaryAndNeverPublished` | Yahoo/S&P 원자료는 실행 서버 임시 공간에만 두고 공개하지 않는다 |
| `economicReadingIsDescriptiveAndCannotChangeTheDecision` | 경제성 독해는 설명용이며 판정을 바꿀 수 없다 |
| `separateCashEconomicSpecReviewed` | 별도 CASH 경제성 정의(SPY 현금배당 재투자 + DTB3)를 검토했다 |

## 4. 아이폰에서 승인하고 병합하는 방법

1. Safari로 이 PR을 연다. GitHub 앱에서 파일 편집이 안 되면 Safari에서 하면 된다.
2. **Files changed**에서 `docs/research-program/authorizations/rp1-c1-us-exposure-execution-authorization.json`을 찾는다. `⋯`(또는 연필 아이콘)를 누르고 **Edit file**을 선택한다.
3. 위쪽 `"acknowledgments"` 안의 8줄에서 `false`를 `true`로 바꾼다. **다른 글자는 하나도 건드리지 않는다.** 공백, 줄바꿈, `ownerLogin`, `instructions`, pin 값도 그대로 둔다.
4. **Commit changes**를 누르고 "Commit directly to the `claude/us-c1-execution-readiness-orl8bh` branch"를 선택한다.
5. PR의 `pytest` 체크가 초록색이 될 때까지 기다린다. 이 테스트는 승인 파일이 생성기 출력과 8개 확인사항 값만 다른지 검사한다. 다른 곳을 고쳤다면 빨간색이 된다.
6. **Ready for review** → **Merge pull request**. 병합하면 §2 결정 기록도 함께 확정된다.

## 5. 병합 후 SHA-256 확인과 execute 입력값

**① SHA 확인 (dry-run 다시 실행, 소진 없음)**

1. Actions → `Seal KR factor anatomy v1 result` → **Run workflow**를 연다.
2. Branch는 `main`, `rp1_c1_action`은 `dry-run`으로 둔다. SHA 칸은 비운다.
3. 작업 `rp1-c1-dry-run` → 단계 "Every pre-lock check…" 로그의 `"authorization"` 블록을 본다. 다음 세 가지를 확인한다.
   - `"status": "ISSUED_PINS_MATCH"`
   - `"sha256": "…"`가 아래 예상값과 같은지
   - 같은 로그에 `PRIMARY: MATCHED`, `CASH_ECONOMIC: MATCHED`, readiness `READY…`, equivalence `EXACT`, `readyToExecute: true`

| | SHA-256 |
|---|---|
| 지금 초안(8개 `false`) | `1336c60f81e73a33c696d9c8ac9bc98b73ab117a9662506fd821b62b2cc8e16c` |
| 8개 값만 `true`로 바꿨을 때 예상값 | `cf53d08c70216ea02321688a07a53ba9b4f9dfc1cf47a2e3591d49a4890aba48` |

예상값과 다르면 3단계 외의 바이트가 바뀐 것이다. 그때는 실행하지 말고 원인부터 확인한다. 정본은 dry-run 로그의 `sha256`이다.

**② execute (소유자 1회)**

| 입력 | 값 |
|---|---|
| Branch | `main` |
| `rp1_c1_action` | `execute` |
| `rp1_c1_authorization_sha256` | ①에서 확인한 값(예상: `cf53d08c70216ea02321688a07a53ba9b4f9dfc1cf47a2e3591d49a4890aba48`) |

- 저장소 소유자 계정으로, 첫 시도로 실행한다(재실행 버튼은 거부된다).
- dispatch 시점의 main 끝 커밋에서 실행된다. 승인 병합과 execute 사이에 C1 하네스, 사양, 원천 파일을 바꾸는 병합이 있으면 잠금 전에 거부된다. 소진은 없지만 승인 파일을 다시 써야 한다.
- 잠금 전 거부는 아무것도 소진하지 않는다. 잠금 뒤 실패는 연구를 소진하며 재실행하지 않는다. job 요약의 `STUDY LOCKED` 또는 `Stopped before the lock`으로 어느 쪽인지 알 수 있다.

## 6. 실행 뒤

- 결과 artifact `rp1-c1-us-exposure-results-<run>`과 로그의 정확한 바이트를 봉인하는 Draft PR을 별도로 연다. 판독은 해석표와 §2 결정으로 기계적으로 적용한다. 임계값 수정, 자동 승격, 운영 변경은 없다.
- 알려둘 점: `tests/test_rp1_c1_us_exposure.py`의 `test_design_readiness_is_determinable_and_is_never_the_formal_gate`는 결과와 마커가 없다고 가정한다. 그래서 결과 봉인 PR에서는 이 테스트가 실패한다. 실행 자체에는 영향이 없다. 봉인 PR에서 이 테스트를 생명주기에 독립적으로 고친다.
