# PR #343~#356 의존관계와 병합·종결 경로 (2026-11-22)

## 1. 실제 의존 구조

GitHub의 base 브랜치와 `git merge-base --is-ancestor`로 확인했다. main은 `4f4497bc`(2026-11-14)에서 움직이지 않았고, 모든 브랜치가 main보다 앞서 있으며 뒤처진 커밋은 0개다.

```
main 4f4497bc
 └─ #343 claude/alpha-mechanism-decomposition-y9sqg4
     └─ #345 claude/selection-effect-followup-d31e8ebb
         └─ #346 claude/s2-decomposition-us-cocktail-6dd8a20
             └─ #347 claude/active-fund-disclosure-74cfe61
                 └─ #348 claude/us-kr-followup-91a6584
                     └─ (PR 없음) research/kr-s2-rank-ladder-afb3ea3   ← 3커밋, 리뷰 대상에서 빠져 있음
                         └─ #349 research/kr-s2-single-slot-matched
                             └─ #350 research/kr-us-strategy-batch-v1
                                 └─ #351 research/kr-us-exposure-preserving-v1
                                     └─ #352 research/kr-us-replica-filter-v1
                                         └─ #353 research/kr-us-public-buys-v1
                                             └─ #354 research/kr-us-earnings-expectations-v1
                                                 └─ #355 research/investment-decision-alpha-v1
                                                     └─ #356 research/next-alpha-program-v1
#344 codex/us-topk-market-cap-20261115 (main 직접, 독립)
```

- 모두 draft이고, 마지막 HEAD 기준 CI(pytest)는 전부 성공이다.
- #353의 943건 정정이 #352 위에 있으므로, #352가 병합되지 않으면 #353 이후 어떤 PR도 main에 들어갈 수 없다.
- **문제 1.** #349의 base인 `research/kr-s2-rank-ladder-afb3ea3`에는 PR이 없다. 그 3커밋(사전 고정 사다리와 입력 계보)은 어떤 리뷰도 거치지 않은 채 #349 이후 PR에 딸려 들어간다.

## 2. PR별 병합 전 조건

| PR | 내용 | 병합 전 필요한 것 |
|---|---|---|
| #343·#345·#346·#347·#348 | 1~7차 라운드 연구 | **#346·#347·#348의 미국 수치 중 시총 비중·3분위를 쓰는 것**(U1, 칵테일, 시총 필터, 업종·시총 통제)은 #353 정정과 CTVA 분할 정정 전 입력에 조건부다. 숫자는 그대로 두고 보고서 첫 장에 조건부 고지를 한 줄 단다 |
| rank-ladder | S2 순위 사다리 사전 고정 | PR을 연다. 또는 #349의 base를 #348 브랜치로 바꿔 #349가 이 3커밋을 함께 보이게 한다 |
| #349~#352 | Codex 계열(한국 S2 분해, 전략 일괄, 노출 유지, 복제 필터) | Codex 소관이다. 미국 입력은 Codex 계열(`b0092244`, CTVA 정정 포함)이라 이번 CTVA 문제는 없다 |
| #353 | WAT 등 943건 정정 + 공개 장내매수 | 정정 자체는 독립 재현됐다(Codex 감사, 이 저장소 PIT 검사 위반 0). #352 다음에 병합한다 |
| #354 | 실적 기대 변화 | 미국 결과는 정정 전 입력에 조건부다. v3 입력 재계산(`investment_decision_alpha_v1/results/354-us-v3/`)과 판정 비교를 #355에 둔다 |
| #355 | 투자 의사결정 1차 + 감사 + **이번 정정** | S2 v1·S3 v1의 비례 대조는 INVALIDATED로 표시했고 v2 결과가 대체한다. `CORRECTIONS-2026-11-22-ko.md` 참조 |
| #356 | 로드맵 문서 + 산업 원공표 데이터셋 | #355 다음 |

## 3. 안전한 병합·종결 경로 (권고)

1. **스택을 아래에서부터 순서대로 병합한다.**
   - #343 → #345 → #346 → #347 → #348 → rank-ladder(PR 신설) → #349 → … → #356
   - 각 단계에서 main으로 base를 바꾼 뒤 CI를 다시 확인한다. GitHub은 아래 PR이 병합되면 위 PR의 base를 자동으로 바꾸지 않는 경우가 있다.
   - 이 경로는 각 연구의 사전등록 커밋 순서를 그대로 보존한다.
   - 각 PR이 이미 CI를 통과했고 연구 파일만 추가하므로 충돌 위험이 작다.
2. **대안: 묶음 병합**
   - #356 HEAD를 main으로 직접 보내는 PR 하나를 만들고, #343~#355는 "#356에 포함되어 병합됨"으로 닫는다.
   - 리뷰 단위가 70커밋으로 커지는 대가로 13번의 base 변경과 CI 대기를 줄인다.
   - 사전등록 커밋 해시는 그대로 이력에 남는다.
3. **종결 권고(병합 없이 닫을 것)**: 없다. 모든 PR이 다음 PR의 base이고, 실패한 연구도 실패 기록 자체가 증거다.
   - 주의: #344는 독립이고 main 직접 대상이다. 스택과 순서 제약이 없다.
4. **병합 금지 조건**: 어느 단계에서든 CI가 실패하면 그 위 PR을 병합하지 않는다.

**어느 경로든 병합 결정은 사용자의 것이다.** 이 문서는 순서와 조건만 정리한다.
