# c2-fixed-exposure-attribution-v1 — Owner 승인 패킷 rev2 (2026-11-09)

상태: **READY_FOR_INDEPENDENT_REAUDIT** — Owner 승인 대상 아님.
Codex가 이 패킷의 코드 커밋을 재감사하기 전에는 승인하지 말 것. 아래 해시가 바뀌면 이 패킷도 폐기된다.

- 역사 outcome·수익률·NAV·베타 계산: **0회**.
- `AUTHORIZATION-c2.json`: 만들지 않았다.
- rev1(해시 `f83035d8…`/`933f05b2…`/`50df18fe…`)은 폐기한다.

## 1. 정확 해시

| 대상 | SHA256 |
|---|---|
| 연구 계약 `c2-fixed-exposure-attribution-v1.json` | `75e3c096fc608bba2c57559e07acbb98b6f3371c79e7f20b79ca97863b6898af` |
| `c2_attribution.py` | `da1e4fa6d16d388310e29305c725aca43aa6b830f80941220a3741a8dd200caa` |
| `c2_attribution_run.py` | `7cdb9aa699fe26d4dbb611db9ee901756aeafb93c6185d5740d0bd653974be40` |
| replay-v16 매니페스트 | `f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2` (blob `76556e94…`, `signal-history` `4b6f8b71` = `0b3025d9`) |
| BASIS 프로토콜 (신규 고정) | `a08f92b06aab6de4959b52d0a5bc0fd2c6b21851c53deca114167898e97a8fe6` |
| 069500 교정 TR 파일 / 필드 | `58580c4370ec2c5afa124f849afbc4fa7b5c879012e75ebbd48ee7c7a0e659a9` / `correctedBenchmarkQuotes` |
| 저장 C2 목표 비중 `regional-standalone-paths.json.gz` | `7a09751f99f5d892821cac6bbb4f28359049d58364cb40db1814fac4f93210cb` |
| 재현 대상 replay 결과 | `901b3aee7d3bc06eed3fd2bd14b07a0d4ca4da23745b861a877203c48772b8d2` |
| BOK 정책금리 | `a7edf0e532c7b54da9d962ebf12ff2552c90c783439fef99d7c761c5b9ea69ff` |
| 종료 종목 목록 | `b58ecb2c4500302c40784613318c8451beee663ece5ee76ada26873a4292f93f` |

비용·캘린더·입력저장·평가 코드의 의존 closure 24개 파일 해시는 계약 `dependencyClosure.files`에 있다. 하나라도 바뀌면 실행이 거부된다.

## 2. outcome-free preflight (`evidence/c2-preflight.json`)

- 155/155 블록 적격, 최소 공동 베타 쌍 250 (하한 200).
- 새 ETF·closure 고정 검증을 실제 입력에서 통과했다.
- 가격 패널 전체를 메모리에 적재하지만 날짜 존재만 확인하며, 수익률·베타는 계산하지 않는다.

## 3. 결과 전에 Owner가 정해야 하는 방법론 결정

계약 해시를 승인하는 것이 곧 이 결정들을 승인하는 것이다.

- **D1 = R2 (기존):** SURVIVES 판정에 비용 1x 순수익 C2−대조군 95% 하한 > 0을 요구한다.
- **D2 = R4 (신규 제안):** SURVIVES 판정에 clipping 전 이론적 선택효과 95% 하한 > 0도 요구한다.
  - 0~100% ETF clip이 남긴 시장노출(`clipTransfer`)이 생존 판정을 만들 수 없게 한다.
  - 강화 방향이다(SURVIVES를 지울 수만 있다).
  - 거부하면 R4를 빼고 계약을 재발행한다. 어느 경우든 `verdictWithoutR4`도 함께 기록된다.
- **D3 lag 5:** 유지(변경 없음). C2에 대해 검증된 값이 아니다.
  - 합성 AR(1) φ=0.8에서 SE 비율은 0.673이다.
  - 커버리지 연구를 원하면 결과 전에 별도로 결정해야 한다.
- **D4 현금:** ZERO / BOK_POLICY_PROXY / BOK_POLICY_PLUS_100BP. 세 시나리오가 모두 같은 판정일 때만 조건부 결론을 낸다. 투자 가능한 현금수익률을 확인한 것이 아니다.
- **D5 Owner 인증의 한계:** 아래 승인 절차는 작성자 이메일과 해시에 묶인 절차적 게이트다.
  - 이 프로젝트에서는 에이전트도 Owner 계정으로 커밋하고 댓글을 단다.
  - 따라서 코드는 Owner 본인을 인증할 수 없다. Owner가 대화에서 직접 확인해야 승인으로 본다.

## 4. 실행 (재감사와 승인 이후)

```bash
git worktree add --detach /tmp/sh-c2 4b6f8b7137521a148d9cd2c9e3c2fdfdcb5ae71a
python research/alpha_evidence_sprint_v2/c2_attribution_run.py execute /tmp/sh-c2/ledger
```

순서:

1. 승인 확인
2. one-shot 확인 (로컬 결과·claim, git 이력, 원격 `refs/tags/c2-fixed-exposure-attribution-v1-execution*`)
3. closure·입력·ETF 확인
4. 원격 태그를 강제하지 않는 push로 생성 → 이 시점부터 연구는 소비된다
5. 계산
6. `c2-fixed-exposure-attribution-v1-result.json`을 O_EXCL로 1회 기록

Phase C 잠금은 읽지도, 재사용하지도 않는다.

## 5. AUTHORIZATION-c2.json (재감사 통과 후 Owner가 직접 커밋할 내용 — 지금 만들지 말 것)

```json
{
 "phrase": "APPROVE KR_PHASE_D_EXCEPTION c2-fixed-exposure-attribution-v1 75e3c096fc608bba2c57559e07acbb98b6f3371c79e7f20b79ca97863b6898af",
 "codeSha256": {
  "c2_attribution.py": "da1e4fa6d16d388310e29305c725aca43aa6b830f80941220a3741a8dd200caa",
  "c2_attribution_run.py": "7cdb9aa699fe26d4dbb611db9ee901756aeafb93c6185d5740d0bd653974be40"
 },
 "decisions": {"D1_R2": "ACCEPT", "D2_R4": "ACCEPT", "D3_lag5": "KEEP", "D4_cashBand": "ACCEPT"},
 "scope": "one-shot historical attribution of the fixed saved KR C2 path; KR Phase D exception for this study only; no promotion, no production change"
}
```
