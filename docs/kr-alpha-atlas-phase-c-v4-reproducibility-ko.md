# Phase C v4 — 실행 전 계산 재현성 수정

Main `b26390140eaacb82e100ace1087036c4b397f82d`의 v3 preflight run [38016613251](https://github.com/jaehojung1879-netizen/Investment/actions/runs/38016613251)은 등록·원천·67개 합성 테스트를 통과한 뒤 matrix digest를 거절했다. 실제 digest는 로그에 기록되지 않았고 업로드 artifact도 0개여서 그 run의 값을 복구하거나 추정하지 않는다.

## 재현된 원인

패키지 버전과 단일 thread만으로 NumPy/OpenBLAS의 CPU 계산 경로는 고정되지 않는다. 같은 원천 비트·멤버십·달력·회계·행·결측 사유에서 다음 차이를 재현했다.

| 기존 계산 | 고정 계산 | canonical 차이 |
| --- | --- | --- |
| 로컬 AVX512 NumPy log/exp 경로 | AVX2 경로 | E05 Corwin–Schultz 37개 셀 |
| 로컬 SkylakeX OpenBLAS dot product | Haswell 경로 | A09 과거 leave-one-out 산업 모멘텀 9개 셀 |

합성 OHLC의 한 변수 통제에서 NumPy 경로만 바꾸면 E05 hash가 달라지고 BLAS만 바꾸면 E05 hash는 유지된다. 전체 실입력 bar 열은 GitHub AVX2와 로컬 고정 경로에서 동일하다. 12자리 직렬화에서 달라진 총 46개 셀만 독립적으로 계산한 기존 경로 값으로 복원하면 **기존 v3 hash 전체가 정확히 재현된다**. 나머지 matrix 바이트를 바꾸거나 gate 허용오차를 늘리지 않았다.

이는 원천 빈티지·가격 조정·기업행동·금융 정의 변경이 아니다. 미래 수익률이나 모델 성과를 사용해 계산 경로를 선택하지 않았다. [기계 증거](audits/kr-alpha-atlas-phase-c-reproducibility/root-cause.json)에 원천/열별/결측 hash, runtime, 46개 변경 셀과 canonical bridge를 보존했다.

## 명시적 v4 addendum

- v1, v2, v3 등록·sidecar·코드·과거 receipt는 그대로 보존한다.
- NumPy import 전에 `NPY_DISABLE_CPU_FEATURES=AVX512F,AVX512CD,AVX512_SKX,AVX512_CLX,AVX512_CNL,AVX512_ICL`, `OPENBLAS_CORETYPE=Haswell`, `PYTHONHASHSEED=1`을 고정한다. 기존 thread 1, Python 3.11.16, 수치 패키지 버전도 유지한다. 잘못된 CPU/BLAS/환경은 입력 준비 전에 거절한다.
- 원래 scientific functions와 preflight/lifecycle을 재사용한다. observer가 원래 matrix를 그대로 반환하며 원래 exact-digest gate가 계속 실행된다. gate 실패 전에 실제/기대 hash, 행 식별, 열별 값/결측 hash, 준비 입력 비트와 runtime을 durable artifact에 쓴다.
- 원천 입력 SHA `d0b9746c26397f604474515e46bd1bdc06183aadb6c4119d703a56826cb7c3c2`는 v3와 동일하다.
- 원래 v3 matrix `c3d66a99f1e1a1c525a9a659b0bee3cc1bf04109796234b310f0513b222187e7`는 수정하지 않는다.
- v4 matrix `d139565af140890472510e0a894005b7ea725d7076e35f69d9a6ef079be57e1b`를 별도 등록한다.
- v4 addendum SHA `50e9d761cfe282f2fa8ec07c1c697e5486af62538419efe0f073dca42f916e00`.
- effective contract SHA `a6d19b9477205c193111a42f194f94f92b93eba3ff7016affaf4d37d9c206015`.
- dependency manifest SHA `cb49a8bb55ef71b9b66f4a46f7a601f94120ddd594ee16a58446ddf161b4f1c2`: 158개 파일, 기존 protected 235개.
- 38 후보·73 feature/horizon readings·B0–B4·30 family comparisons·X1–X6·horizon·추론·비용·포트폴리오·cutoff·벤치마크·source coverage floor는 그대로다.
- benchmark reconciliation의 2013–2026 PASS 및 원래 0.50pp 기준은 그대로다. 006800의 기존 source quarantine과 source validity도 그대로다.

## 권한과 one-shot

동일한 연구 ID, result/artifact namespace 및 `refs/tags/kr-alpha-atlas-phase-c-v1-execution-lock`을 공유한다. 두 버전이 각자 실행하는 것은 불가능하다. v4에도 새 exact-hash owner 승인 commit이 필요하다. 이 변경과 PR merge는 실행 승인이 아니다.

기존 동결 workflow census를 바꾸지 않고 Pages workflow에 별도 job을 둔다. PR/preflight job은 contents/actions **read**만 가지며 outcome firewall로 전체 준비를 실행한다. Pages 배포는 PR 또는 matrix action에서 실행되지 않고 기존 기본 Pages/push/schedule 동작은 유지한다. formal job은 main의 owner workflow_dispatch `matrix-execute`에만 열리며 코드가 다시 exact owner 승인·merged main·입력·runtime·합성·영속화·atomic global lock 순서를 검사한다. 자동 재시도·잠금 삭제·실패 후 두 번째 실험은 허용하지 않는다.

## 검증 기록과 다음 사람의 행동

현재 authoring 재현은 원래 v3 gate가 정상 거절했고 actual `d139565af140890472510e0a894005b7ea725d7076e35f69d9a6ef079be57e1b`를 남겼다. PIT 805,676 filing 셀의 위반 0, 결측 1,550,874 셀의 무사유/허용 밖 사유 0이다. 원래 matrix와 동일한 714 dates, 85,680 rows, 76 columns, 260 securities를 검증한다. 검증 checkpoint는 [validation.json](audits/kr-alpha-atlas-phase-c-reproducibility/validation.json)에 기록하며 최종 head의 CI는 [PR #216](https://github.com/jaehojung1879-netizen/Investment/pull/216)의 Checks와 durable artifact에서 확인한다. 실제 전체 실입력 [PR preflight 38023180733](https://github.com/jaehojung1879-netizen/Investment/actions/runs/38023180733)은 871.102초·최대 RSS 1,863,766,016 bytes로 PASS, 새 디렉터리의 로컬 준비도 1,010.268초로 PASS였다. 76개 열 값/결측 및 준비 원천 비트 hash가 모두 같다. H01/H08 69.1073159%, B0–B4/X3 READY, X4 SOURCE_BLOCKED를 유지한다. 로컬 전체 pytest는 4,201 passed·1 skipped·4 xfailed였고 합성 전체 study·lint·compile/import·seed/map 검사도 통과했다. 메타데이터 또는 unit test만으로 readiness를 선언하지 않는다.

일반 Tests CI의 첫 run은 30분 한도에서 중단되었고, Python 3.11.17에서 환경 거절을 검사하던 새 unit fixture가 Python 3.11.16의 선행 거절에 걸렸다. 통제 재현 후 두 거절 guard를 각각 검사하도록 **test fixture만** 수정했다. 정식 runtime은 여전히 3.11.16이며 생산 코드·입력·matrix는 바뀌지 않는다. 첫 Draft v4 등록은 [정확한 이전 바이트](audits/kr-alpha-atlas-phase-c-reproducibility/v4-first-draft.json)와 Git commit d2d2167에 보존하고, 변경한 test dependency 및 새 effective hash는 [authoring erratum](audits/kr-alpha-atlas-phase-c-reproducibility/authoring-erratum.json)에 기록한다. 이미 merged된 v1/v2/v3를 재동결하지 않는다. 최종 exact hash 승인은 위 새 값에만 적용된다.

1. 최종 실입력/CI 기록을 검토하고 이 Draft PR과 v4 등록을 사람이 승인·merge한다.
2. 승인 파일 없이 main의 `pages.yml`을 `atlas_action=matrix-preflight`로 source-only 확인할 수 있다.
3. 실행을 원할 때 owner가 **별도 commit**으로 `research_specs/kr-alpha-atlas-phase-c-v4-execution-authorization.json`에 기존 driver의 정확한 8개 필드를 승인한다: studyId/action/authorizedBy/originalSpecFileSha256/parentV2FileSha256/repairAddendumFileSha256/effectiveContractSha256/dependencyManifestSha256. v4 승인에 들어가는 repairAddendum/effective/dependency hash는 위 값이다. parent v3 identity는 이 addendum에 묶여 있다.
4. owner가 main에서 `pages.yml`, `atlas_action=matrix-execute`를 **한 번만** dispatch한다. 이 작업에서는 그 승인 파일·dispatch·lock을 만들지 않았다.

모든 한국 역사 결과는 DEVELOPMENT이다. 합성 성공은 실제 alpha 증거가 아니다. 실제 forward labels·historical fits·alpha/portfolio 결과는 이 수정에서 만들지 않는다.
