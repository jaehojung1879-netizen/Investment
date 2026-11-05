# Master research integration preflight — PREPARED / 실제 실증 BLOCKED

근거 handoff: [Issue292 댓글6655209199](https://github.com/jaehojung1879-netizen/Investment/issues/292#issuecomment-6655209199). main `37f8cbf6b1c066f6b3c65235953648d17ebf2f69`에서 격리 작업했다. #314/#315·운영 workflow·연구 봉인·등록·잠금은 변경하지 않았다. 새 역사 성과·모델·가격 수집·production 기록·main 병합·활성화는0이다.

## 1. 판정과 구현

| 범위 | 상태 | 근거 |
|---|---|---|
| 두 PR interface/evidence 대조 | PASS | 고정 파일/행/해시는 [interface-map.json](evidence/interface-map.json), path/blob 감사는 [source-audit.json](evidence/source-audit.json) |
| 연구 전용 prepared receipt·합성 scratch append | PASS | [receipt.py](receipt.py), 기존 main `prospective_receipt_core` codec·append·KR timing 및 지역 달력 재사용 |
| 서로 다른 P0~P5 평가 엔진 자동 변환 | BLOCKED | 비용·재조정·결측·만기 estimand가 다름. 어댑터는 INCOMPATIBLE을 반환 |
| 실제 forward receipt 발생/운영 활성화 | BLOCKED | 별도 Owner release 승인과 정상 운영 source/codec 필요. 이번 실제 쓰기0 |
| H126/H252 경제성·독립 투자 alpha | UNOBSERVED | 합성 검증·calendar 경과는 실제 관측이나 alpha 증거가 아님 |

병렬 담당이 수집한 근거와 부분 adapter 코드를 회수한 뒤, 사용량 제한으로 중단된 나머지 구현은 주 담당이 완료했다. 이 자료는 **작성자 검증**이다. Codex가 #317을 작성했으며, 이후 비저자 독립 감사·Owner 승인이 별도로 필요하다. CI 성공을 연구 validation으로 부르지 않는다.

## 2. 한 canonical 후보와 중복 책임 정리

**canonical 후보는 #316의 named prospective proposal `portfolio-d-p0-p5-comparison-v1`로 한정한다.** 원본 SHA256 `eecdb60753efa8e9600a3d0595109914a56851be236ebfb037d6ca102db3021c`를 확인한다. 원문이 PREREGISTERED라고 적어도 이 통합 prototype은 PREPARED이며 실제 등록·실행 승인을 주장하지 않는다.

새 valuation/선정/통계 엔진을 만들지 않았다. receipt의 canonical JSON·digest·append·시간 경계는 기존 main core를 사용한다. 운영 주간 영수증은 기존 `weekly_decision.receipt_digest`와 `receipt_session_error`에 위임해 읽기만 한다. #306 shadow accounting codec이나 ledger writer를 복제하지 않는다. 기존 운영 writer는 별도 release 경로로 유지한다.

| 주제 | #316@75aab7bc | #317@a3ee7a71 | 이번 처리 |
|---|---|---|---|
| 비용/재조정 | `portfolio/comparison.py:76`, contract:19/23 — drifted book·21세션 블록 | `comparison.py:324` — 자기금융 entry/terminal liquidation 합성 | 수익·비용 변환 거부; 공통 policy hash만 대조 |
| universe/PIT | contract:16/17 — common mask·시점 계약 선언 | comparison:144/159 — 동일 구성·availability/vintage 검사 | 모든 arm의 universe/cost/execution/basis/calendar/cutoff identity 일치 요구 |
| 결측 | comparison:122 — arm None 및 pair별 None 제거 | comparison:300 — 전체 paired block 거부 | 표본이 같다고 가정하지 않음. 새로운 승인 계약 전 실평가 불가 |
| receipt/권리 | comparison:174 — UNVALIDATED라도 targets 포함, writer clock/rights 검증 없음 | comparison:238/256 — 기존 record의 identity view | #316 helper를 운영 writer로 직접 호출하지 않음. blocked 출력은 targets/weights 없음 |
| horizon | contract:23/24 — 21세션 블록과H126/H252 | comparison:107 — 지역 실제 세션 maturity | calendar만 검사하고 성과는 항상None |
| industry | `market_industry/us_sector_membership.py:1` — dataset-published sector | `cross_market_foundation_v1/industry.py:43` — SEC issuer SIC | 다른 분류·신원·공개 시점. GICS/SIC를 소급 치환하지 않음 |

모든 경로는 원본 각 commit의 `research/master_research_program_v1/` 또는 `research/cross_market_foundation_v1/` 아래다. 완전한 GitHub URL·commit·파일 SHA256·행 번호는 mapping JSON에 있다. 이는 제3 엔진을 추가하는 대신 **하나의 prepared 입력 계약과 명시적 비호환 경계**를 두는 처리다. 실제 비교를 시작하려면 초기 자본·종료 매도·재조정·결측 표본 규칙을 하나로 승인하고 기존 helper의 실행 경계를 별도로 심사해야 한다.

## 3. 595경로와513개 원천의 처리

#316 changed paths595, #317 changed paths34, 직접 겹침0이다. 의미 중복이 없다는 뜻은 아니다. #316의513 data경로는 부모 #308 commit `f48b6f29993cf572d191f9724d19d2543f375f6c`와 path/mode/blob이 전부 같다. GitHub tree metadata 기준3,674,375B(약3.50MiB), unique blob513이며 main/#317과 같은blob은0이다. **물리적 중복 데이터라고 단정하지 않는다.** raw payload 가용성·내용 SHA256·사용권을 이번에 인증하지 않았다. partial clone의 `BAD` size도0으로 대체하지 않았다.

이 prototype에는513 raw파일이 필요 없어 복사·checkout하지 않았다. metadata manifest만 추가했다. 향후 #316 일부를 통합할 때에는 원 parent/source commit과 path/blob을 보존하고, 실제 helper 의존성과 사용권을 확인한 소수 입력만 고정 ref로 읽는다. source ref의 영속 보존도 Owner가 보장해야 한다. 정적 reference가 없다는 이유만으로 파일을 불필요하다고 삭제하거나, closed #308 ancestry를 blind squash/recommit하지 않는다. 원 #316/#317 브랜치와 기존 원천 파일은 무변경이다.

## 4. runnable prototype의 경계

- `adapters.adapt_synthetic_inputs`: 모든 six-arm common identity, raw fixture SHA256, timezone/PIT/vintage/rights, S1–S5 상태를 검사한다. ADMITTED 문자열이나 실제 입력은 받아들이지 않는다.
- `adapters.adapt_foundation_plan`: #317 plan의 로컬 digest/공통 identity를 확인하되 targets는 버리고 INCOMPATIBLE을 반환한다. digest는 source 권리·과학 admission 인증이 아니다.
- `receipt.prepare_receipt`: weekly FINAL·지역 휴장·실제 writer clock과 creation 일치·신호 마감/다음 개장 경계를 검사한다. KR은 기존 core를 호출하고 US는 기존 지역 달력/XNYS session 시간을 사용한다. 승인 경계는 **synthetic fixture boundary**이며 Owner 승인으로 가장하지 않는다.
- P0는 ETF 정책 baseline, P1–P5는 BLOCKED다. KR0~5 dynamic 정책과 US SPY/보조QQQ 식별만 기록한다. 종목 선택·weights·factor score·성과0은 만들지 않는다. 입력 불충분은 UNOBSERVED/SOURCE_BLOCKED다.
- `append_synthetic_receipt`는 미리 만든 외부 test directory와 `.synthetic-preflight-store` 표식이 필수다. 모든 Git worktree·ledger/state/.git 경로, symlink/hardlink를 거부한다. 기존 core append와 local exclusive lock을 사용하고 동일 주 재조회는0건, 원천 개정 충돌·tamper는거부한다. production store를 초기화하는 API는 없다. 이 test lock/append는 운영 checkpoint/복구 프로토콜을 대체하지 않는다.
- `maturity_readiness`는 H126/H252 거래일 경과만 구분한다. 경과 후에도 데이터미관측·성과None·미인증이다. 과거 fixture는 SYNTHETIC_PREFLIGHT이며 진짜 PROSPECTIVE_PAPER 영수증이 아니다.

## 5. 실제 observation readiness와 release gate

[actual-readiness.json](evidence/actual-readiness.json)은 source `5ad82b5bbfdbb624cd24c05d06b2ca277e4c2b05`의 허용 네 경로만 읽었다. Portfolio D production store는 ABSENT이며 실제 첫 receipt 미관측이다. champion 생성11/01과 weekly 생성11/05가 달라 pair를 인증할 수 없다.

주간 ledger8행 중 기존 codec 통과7행, KR2026-10-16 FINAL1행은 생성04:44UTC가 종가 완료 전이라 거부된다. byte SHA는확인됐지만 세션 검증은 별개다. 원문3행 SHA256 `f5cef9cb978e04181a7cc41235253daa7aa6b4e3fc98200a5c1e819eb08b82ff`를 남겼다. 이 과거 행을 지우거나 시각을 고쳐 정상화하지 않았다. 최신 유효FINAL과 legacy거부 이력은 분리해 심사해야 한다.

운영 연결은 #306→#314 및 #299→#307의 기존 append-only hook을 그대로 사용해야 한다. 부모 병합 후 child base를 main으로 바꾸는 절차, 최신 정확 HEAD CI와 비저자 리뷰, Owner merge/deploy/activation 승인, 동일 generation의 유효FINAL·신호/실행지역달력·공개 가격·비용1회·동일 시작 ETF·재시작/개정 거부가 필요하다. 코드/승인만으로 source 불일치를 면제할 수 없다. 운영 기록 시작과 훗날 H126/H252 독립경제검증은 다른 단계다.

## 6. 별도 Pages P0

#315 `23522002dcd2d9e0e16dfb9d325a235aef664f0c`: [Tests41976317313 SUCCESS](https://github.com/jaehojung1879-netizen/Investment/actions/runs/41976317313), [Pages41976318202 FAILURE](https://github.com/jaehojung1879-netizen/Investment/actions/runs/41976318202). 소비된 연구의 formal preflight guard `AUDIT_REQUIRES_UNAUTHORIZED_UNCONSUMED_STUDY`가정당하게거부한다. 운영 state-only publisher 문제와분리한다. 허용된 state-publication 예외는5992B 연구prefix 내진단 변경을승인하지않는다.

최소 후속선택은 (a) 원본등록/결과/원천/잠금 보존을검증하는 PR한정closed-study provenance 진단의새버전범위를Owner에게승인받은뒤독립구현·심사하거나, (b) #315를보류하고기존main Pages를유지한분리출시의잔여디스크위험을Owner가판단하는것이다. skip/xfail/해시교체로녹색을만들지않았고 이P0수정을연구코드로옮기지않았다. 원문승인·실패로그는기존release packet과PR에있다.

## 7. 재현·검증·Owner 경계

```bash
python -m pytest -q tests/test_master_integration_*.py
python -m research.master_integration_preflight_v1.audit_sources
python -m research.master_integration_preflight_v1.preflight --source-ref 5ad82b5bbfdbb624cd24c05d06b2ca277e4c2b05
ruff check .
python -m compileall -q pipeline research/master_integration_preflight_v1
python -m pytest -q
```

고정 Git 객체는 별도 acquisition에서 확보해야 한다. 위 CLI는 implicit fetch나 production 쓰기를 하지 않는다. actual preflight의 BLOCKED는검사가실행됐다는뜻이며준비완료가아니다. 새로운 fixture54개검증과source 감사의원천/로그/코드hash는 evidence 및PR검증결과로대조한다. 전체suite/최종HEAD/자동CI는통합Draft PR의정확head결과를확인한다.

Owner 결정: canonical 실험의 비용·재조정·결측 규칙 및 정식등록/입력admission, 원천보존·사용권, production release/activation, 역사outcome 실행이필요하면별도exact-hash 승인, Pages별도유지보수범위. 본PR은어느승인도대신하지않는다. 실증alpha는여전히KR0/US0이며미검증Stock-S4를주전략이나매수추천으로승격하지않는다.
