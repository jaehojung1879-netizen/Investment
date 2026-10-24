# WID source admission: Codex 조건부 기술 검토 v2

출발 main `591f182955ab85bc527ddedc41c2d77d1fd24eaa`, 이전 복구 HEAD `18f7ed6b25f6dea5274c92f05b8f946b0f229361`.
기존 실행 명세/기본 UNRESOLVED review/결과/봉인은 변경하지 않았다. 이 폴더는 소유자가 검토할 **별도 review**다.
법적 권리, 실제 미래 수익, 정식 WID 실행 또는 production 승인을 생성하지 않는다.

## 실제로 진행한 admission

고정 보존 공시 FY2011~2021 **23,940건·753 ticker**, 날짜별 구성원/산업/CIK metadata를 직접 감사했다.
quote panel·H126/H252 label·모델·WID 정식 실행은 열거나 호출하지 않았다. source receipt SHA와 code closure SHA는
`source-audit.json`에 있다. source admission 입력은 `review.json`, 실제 preflight는 `preflight.json`이다.

| 항목 | 새 판정과 정확한 의미 |
|---|---|
| membershipIndustry | **REVIEWED_ACCEPTED, 조건부**. strictly-earlier community snapshot 및 고정 taxonomy 허용 목록/제외 정책을 검토. 공식 당시 S&P/산업 관측이나 동시점 수집 인증 아님 |
| size | **REVIEWED_ACCEPTED, proxy만**. 공시 가중평균 주식 수×복원 가격, 분할 교차 보류·결측 보류를 검증. 실제 시가총액/주식수 context/가격 진실성 인증 아님. returnBasis 전역 차단 유지 |
| vintage | **REVIEWED_ACCEPTED, 소급 재구성 범위만**. 2026년 취득 자료라는 한계, 두 공개 시각의 최댓값보다 엄격히 이후, 180일 공시 age 정책을 검토. 원래 vintage/당시 관측 인증 아님 |
| terminal | **REVIEWED_ACCEPTED, fail-closed 정책만**. 미확인·지연·주식교환 대가는 unresolved 유지. 검증된 현금에는 신원/통화/주당 기준 필요. 실제 종결 대가를 새로 확정한 것은 없음 |
| rights | **UNRESOLVED**. 기존 Git/코드 라이선스/공개 접근은 Yahoo/Finnhub/구성원 자료의 보존·재사용 grant가 아님. 무료 Tiingo 우회 없음 |
| identity | **UNRESOLVED**. 날짜 있는 CIK 비교 규칙은 존재하지만 과거 가격 파일 issuer/share class까지 검증됐다고 볼 수 없음 |
| returnBasis | **UNRESOLVED**. 주식과 SPY의 원가격·주당/통화·분배 누락을 독립적으로 대조하지 못함. 수학 산식 합성 통과를 실데이터 총수익 인증으로 바꾸지 않음 |

조건부 기술 검토 네 건을 원천 경제/법률 사실의 완전 해결이라고 해석하지 않는다. 이 검토를 명시적으로
선택한 실제 preflight는 **7개 차단에서 3개(rights/identity/returnBasis)로 줄었지만 전체 BLOCKED**다.
원래 기본 review는 여전히 7개 UNRESOLVED다. 소유자는 앞으로 승인할 exact request에서 이 조건부 범위를 수용해야 한다.

## 실제 데이터 결함 하나 수정

보존 원천 `TFC|0000092230-14-000014`는 `availableFrom=2014-02-26`이고 `acceptedDate`가 없다.
기존 공통 helper는 하나의 날짜로 fallback할 수 있었다. 그 공통 코드/봉인 의존성을 바꾸지 않고,
WID의 `reviewed_filings`에서 **두 날짜가 모두 유효하지 않은 filing만 보류**한다. 종목·모집단 행을 삭제하지 않는다.
보류 metadata는 향후 승인된 실행의 결과에도 이유와 ID로 남긴다. 기존 계약의 두 시각 요건을 구현한 것이며
새 threshold/모형/성과 최적화가 아니다. source audit에서 23,939건 accepted / 1건 withheld를 확인했다.
실제 WID 학습·예측 결과는 이번에 계산하지 않았다.

## 재현 및 실행 경계

```bash
python scripts/review_winner_inflection_admission.py --materialize-review
python scripts/run_winner_inflection.py preview --review docs/winner-inflection-discovery/admission-review-v2/review.json
python -m pytest -q tests/test_winner_inflection_source_review.py tests/test_winner_inflection_local_git.py tests/test_winner_inflection_execution.py tests/test_winner_inflection.py tests/test_experiment_workbench.py
```

materialize는 감사 JSON만 기존 `/workspace/wid-inputs/evidence`에 **내용 주소 SHA 파일명**으로 복사한다.
소유자 승인 파일/댓글/시도 태그/연구 원장을 만들지 않는다. 가격 원천을 복구하거나 외부 API를 호출하지 않는다.
review 자체와 근거 SHA가 exact request에 고정되고, 코드 변경 시 기존 request/승인을 재사용할 수 없다.
실제 실행은 남은 세 항목의 증거 검토와 소유자의 `APPROVE WID_EXECUTION <request.sha256>` 확인 후에만 가능하다.
현재 GitHub API 접근이 Forbidden이라 원격 댓글 확인·attempt ref·PR 생성은 별도 접근 가능한 환경이 필요하다.

123개 관련 합성/가용성/승인 회귀 통과. 실제 source review에서 outcome/model 카운터 0,
입력 Git 준비 398/398 READY를 확인했다. 전체 pytest는 실제 봉인 결과를 재계산하는 기존 테스트 때문에 실행하지 않았다.
C1/Claude 담당 PR/운영 정책/Workflow/Secret/봉인 원천·결과는 변경하지 않았다.
독립 감사에서는 네 조건부 수용의 제한, 두 날짜 필터의 누락 종목 보존, 증거 tamper 거부,
세 미해결 항목으로 인한 전체 BLOCKED, 소유자 승인 분리를 확인해야 한다.
