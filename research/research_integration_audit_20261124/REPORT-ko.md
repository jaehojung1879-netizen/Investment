# 연구 계보 통합 감사 — PR #343~#373 (2026-11-24)

감사·병합 준비 전용 기록이다. 새 수익률 실험, 모델 적합, 결과 재계산은 없다. 기준 main은 `4f4497bc`(#342, 2026-11-14)이며 그 뒤 움직이지 않았다.

## 1. 결론

- **텍스트 충돌 0건.** 두 스택과 독립 PR 전부를 한 트리로 합쳐도 충돌이 없다. 모든 PR HEAD는 main보다 뒤처진 커밋이 0개다.
- **봉인 해시를 깨는 사후 수정은 1건**: #360 `industry_alpha_discovery_v1/hwp_text.py`. 이 브랜치(`claude/loving-mendel-g0j796`)에서 승인 당시 바이트로 복원했다.
- **리뷰 공백 1건**: #349의 base `research/kr-s2-rank-ladder-afb3ea3`에 PR이 없다. 3커밋이 리뷰 없이 #349 이후로 딸려 들어간다. 이 통합 브랜치는 그 3커밋을 원 해시 그대로 포함한다.
- **공용 입력 계보**: #353(시총 943행·14종목)·CTVA(6665:1000 분할, 329행) 정정 해시는 재검증 결과 일치한다. 정정 전 미국 입력을 쓴 #343·#345~#348 결과는 재실행되지 않았다. 해당 보고서 본문은 바꾸지 않고 이 원장에 조건부로 기록했다.
- **닫힌 미병합 PR 33건**: 유실 0건. 모든 HEAD가 원격 브랜치에 남아 있다. 다만 main에는 없으며 4건(#320·#322·#327·#330)만 열린 PR(#328·#332)에 포함돼 있다.
- **main 병합은 하지 않았다.** 병합 결정은 소유자에게 있다.

## 2. 실제 의존 구조

```
main 4f4497bc
 ├─ 스택 A: #343 → #345 → #346 → #347 → #348 → [ladder, PR 없음] → #349 → #350 → #351 → #352 → #353 → #354 → #355 → #356 → #360
 ├─ 스택 B: #357 → #358 → #361 → #362 → #363 → #365 → #366 → #367 → #368 → #369
 │                    ├─ #359 (#358 위, 신규 파일 5개)
 │                    └─ #364 (#358 위, 신규 파일 2개)
 └─ 독립: #344, #370, #372, #373
```

- 근거: `git merge-base --is-ancestor` 전수 대조(`evidence/github-snapshot.json`, `evidence/lineage.json`).
- 기존 main 파일을 고치는 PR은 #370뿐이다(`pages.yml`, `app.js`, `pipeline/institutional_13f.py`, 테스트).
- 그룹 간 공유 경로는 #357/#358이 만든 `market_valuation_macro_overlay_v1/**`뿐이다. #359·#364는 신규 파일만 추가한다.
- #371은 PR이 아니라 Issue다(G0 사전심사). 작업 PR은 #373이다.

## 3. PR별 병합 가능 여부

### 3.1 병합 가능 — 순서·draft 해제만 필요

| PR | 상태 | 조건 |
|---|---|---|
| #343, #345~#348 | CI 성공, 충돌 없음, 봉인 위반 없음 | 미국 결과는 정정 전 입력 조건부(§5). 수치는 그대로 둔다 |
| #350~#356 | CI 성공 | #354 미국 결과는 #355에서 v3 입력으로 재실행됨(US E_H1 NOT_SUPPORTED → DIRECTIONAL_ONLY) |
| #357, #358, #361~#363, #365~#369 | CI 성공 | #365의 Stage 2 v1 프로토콜은 #366에서 의도적으로 폐기(§4) |
| #359, #364 | CI 성공, 신규 파일만 | base가 #358이므로 #358 이후 병합 |
| #344 | CI 성공, 독립 | 미국 계보 미검증(§5). 기술적으로는 단독 병합 가능 |

### 3.2 현 브랜치 그대로는 병합 불가

| PR | 사유 | 해소 |
|---|---|---|
| #360 | `authorization.json`이 고정한 `hwp_text.py`(b0379c09…)를 실행(79fdd66) 이후 5d41c43이 수정. `execute.check_authorization()`이 `FILE_CHANGED`로 멈춤(재현) | 이 브랜치 5a70fcd에서 바이트 복원. #360 자체 브랜치에는 미반영 |
| #349 | base가 PR 없는 ladder 브랜치. ladder 3커밋이 리뷰 대상에서 빠짐 | 이 통합 PR이 3커밋을 포함. 또는 ladder PR 신설·#349 base 변경 |
| #345~#369 중 base≠main인 PR | GitHub에서 각자의 base 브랜치로만 병합됨 | 아래에서부터 순서대로 병합·base 변경, 또는 이 통합 PR 1건 |

### 3.3 관여하지 않음 (지시에 따름)

| PR | 읽은 시점 상태 |
|---|---|
| #370 | pytest 실행 중, `matrix-diagnostic` 실패(run 45455608768). production 파일 수정 |
| #372 | pytest 실행 중 |
| #373 (Issue #371) | 미확인 |

- 세 브랜치 모두 통합 트리와 `git merge-tree` 기준 충돌 0건이다. 그 외 검토는 하지 않았다.

## 4. 봉인 해시 전수 검증

- 대상: main 대비 추가·변경된 JSON 217개의 SHA-256 고정값. `check_pins.py`로 재현한다.
- 결과: 일치 432건, git 밖 파일(비공개 scratch) 50건, 불일치 7건(전부 분류됨), 미분류 0건.

| 불일치 | 분류 | 판단 |
|---|---|---|
| #360 `hwp_text.py` | 실행 후 수정 | **복원함**(5a70fcd). 회귀 테스트는 `ALREADY_EXECUTED` 도달을 요구 |
| #365 `protocol-stage2.json` → `stage3_execute.py` | 대체된 프로토콜 | #366이 v1 실행기를 영구 거부로 바꿨고 v2가 `supersedes`로 대체. v1은 승인·실행된 적 없음. 의도된 상태 |
| #343 `first-observation-preview.json` → `recorder.py` | 생성 시점 스냅샷 | `REPLAY_PREVIEW_NOT_PROSPECTIVE_EVIDENCE`. spec.json은 recorder를 고정하지 않음 |
| ladder `results/inputs.json` → `verify.py` | 같은 커밋 내 코드 식별자 차이 | inputs.json은 6eb845b 시점 verify.py를 기록. #349 provenance가 inputs.json을 고정하므로 수정하지 않음 |
| #349 `provenance.json` 4건 | 검사기 오탐 | 키가 ladder 연구 기준 상대경로. ladder 경로로 대조하면 24/24 일치 |

## 5. 공용 입력 계보 (#353 시총, CTVA 분할)

- **#353 정정**: `kr_us_public_buys_v1/results/WAT/corrected-caps.csv`, 943행·14종목(COP 360, GRMN 141, MCD 131, L 69, KO 55, TER 39, PCAR 36, CHD 28, WAT 26, DLR 17, EOG 13, KMI 13, WELL 12, AXP 3). SHA-256 `90876398…`가 #355 `lineage-v3.json`의 기록과 일치한다.
- **CTVA 정정**: 2026-10-01 6665:1000 분할, 329행. 영수증 SHA-256 `db249e46…` 일치. 원 probe 응답(`c8f9f48f…`)은 git 밖에 있다.
- **v3 입력**: 정정 전 `features.pkl`(`49062dba…`) + 위 두 정정. 결과 파일(`d5802c9c…`)은 git 밖이다.

| PR | 미국 입력 | 상태 |
|---|---|---|
| #343, #345, #346, #347, #348 | Claude 계보 `49062dba…` | **정정 전 입력 조건부, 재실행 없음**. 시총을 Top-K·가중·통제·필터에 사용 |
| #350~#352 | Codex 재수집(2026-11-17) + CTVA 정정 | 943행 영향은 #353이 측정. #352 판정 불변 |
| #353 | 정정 원천 | 미확인 플래그 29건은 미확인으로 공개 |
| #354 | 정정 전 | #355에서 v3 재실행, 판정 1건 변경 |
| #355 | v3 | 정정 입력. v1 출력은 보존, v2가 대체 |
| #344 | 별도 계보(SEC dei 주식 수 + 2026-11-14 수집분) | **검증 불가**. 비공개 입력 부재. CTVA 분할 반영 여부와 #353이 찾은 scale-6 태그(EIX) 대조 기록이 없음 |
| ladder, #349, #356, #360, 스택 B | 미국 개별 시총 미사용 | 영향 없음 |

- #355의 `PR-STACK-343-356-ko.md`는 #346~#348 보고서 첫 장에 조건부 고지를 권고했으나 반영되지 않았다.
- 일부 보고서는 manifest가 해시로 고정하므로 본문을 고치지 않았다. 고지는 `evidence/us-input-lineage.json`과 이 문서에 둔다.

## 6. 닫힌 미병합 PR 보존

- 대상: #259~#330 중 미병합 종료 33건. #343~#373에는 닫힌 PR이 없다.
- 유실 0건. 모든 HEAD가 원격 브랜치에 남아 있고 `refs/pull/N/head`도 유지된다.
- main에는 하나도 없다. 열린 PR에 포함된 것은 #320·#322·#327(→#328), #330(→#332)이다.
- 실행 결과가 있는 종료 PR(예: #327 1차 지지 0건, #302 M3 실패, #310 H1 KEEP/H2 DATA_BLOCKED)은 브랜치 삭제 시 접근성이 떨어진다. 해당 브랜치는 삭제하지 않는 것을 권고한다.
- 상세: `evidence/closed-pr-preservation.json`(제목 기준 분류, 본문 재검토는 하지 않음).

## 7. 실무 적용 — 권고 병합 경로

1. **이 통합 PR 1건으로 병합(권고)**
   - 구성: main → #360 HEAD(스택 A+ladder) fast-forward, #369·#359·#364 merge commit, #360 복원 커밋, 이 감사 기록.
   - 모든 PR HEAD의 원 커밋 해시가 이력에 남는다.
   - **squash·rebase 병합 금지.** 봉인 파일이 커밋 해시를 인용한다(ladder `preregistrationCommit 7a6ec28`, #349 `baseCommit afb3ea3` 등).
   - 병합 후 #343·#357은 GitHub가 병합으로 표시한다. 나머지(#345~#369, #359, #364)는 "통합 PR에 포함되어 병합"으로 닫는다.
2. **대안: 스택별 순차 병합**
   - A: #343 → … → #348 → (ladder PR 신설) → #349 → … → #356 → #360(복원 커밋 선반영 필요).
   - B: #357 → #358 → #359·#364 → #361 → … → #369.
   - 각 단계마다 base를 main으로 바꾸고 CI를 다시 확인한다.
3. **#344는 독립 병합 가능**하나 §5의 계보 대조(14개 정정 종목·CTVA) 후 병합을 권고한다.
4. 어느 경로든 CI 실패 시 그 위 PR을 병합하지 않는다.

## 8. 재현

```bash
python research/research_integration_audit_20261124/check_pins.py
python -m pytest -q tests/test_research_integration_audit_20261124.py tests/test_industry_alpha_discovery_v1.py
```

- `check_pins.py`는 커밋된 파일만 읽는다. 가격·결과·비공개 입력을 읽지 않고 아무것도 쓰지 않는다.
- GitHub 상태(HEAD, base, CI)는 2026-11-24 API 조회값이다. 이후 변경은 반영되지 않는다.
