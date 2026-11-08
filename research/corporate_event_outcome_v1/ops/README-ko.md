# 운영 정상화 기록 (2026-11-08)

연구 코드, 등록 사양, 승인 해시는 바꾸지 않았다. 역사 outcome은 읽지 않았다.

## 1. 기업공시 LIVE writer — 격리 검증

검증 방법은 `verify_live_flow.py`다. **등록 커밋 `8aee189`의 `live_run.main`을 그대로** 로컬 bare `origin`에 대해 실행했다. 대체(stub)한 것은 영수증 내용(`live_append`), 시계, DART·유니버스 판독기뿐이다. 실행 직후 `cleanup_pushed_worktrees.sh`(push 확인된 worktree만 삭제)를 돌렸다. 결과는 `verify-live-flow-result.jsonl`에 있다.

| 시나리오 | 결과 | 정리 | origin 영수증 |
|---|---|---|---|
| 첫 실행 11-09 | OK | 그날 worktree만 삭제 | 11-09 |
| 두 번째 실행 11-10 | OK | 삭제 | 11-09, 11-10 |
| 같은 날 중복 실행 | `ALREADY_RECORDED` | 삭제 | 변화 없음 |
| push 거부 11-11 | `PUSH_FAILED_AFTER_5_ATTEMPTS` | **보존**(push 안 된 커밋) | 변화 없음 |
| 다음 날 11-12 | OK | 11-12 삭제, 11-11 **보존** | 11-09, 11-10, 11-12 (11-11은 소급하지 않음) |

이틀째 `checkout -B` 충돌은 git 2.43(이 컨테이너)에서 재현되지 않았다. git 2.44 이상은 이 경우를 거부하므로, 정리 규칙은 git이 업그레이드될 때를 대비한 것이다.

**예약 작업 설정 변경: 실패 — 변경되지 않았다.** `update_trigger`는 "이 작업이 기록되는 원래 대화에서만 프롬프트를 바꿀 수 있다"며 거부했다. Owner가 아래 프롬프트를 원래 세션(`session_01UtFTvhsc62UJBfDJZ6qQZv`)에 붙여넣고 "이 예약 작업 프롬프트를 이것으로 교체해"라고 요청해야 한다. 교체 후 `get_trigger`로 프롬프트를 확인할 것.

```
Scheduled LIVE writer run for the registered study kr-corporate-information-events-v1 (owner-authorized 2026-11-07; registered commit 8aee189ff453d9bd624a67df5e1e5975bd7d211c). Worktree-cleanup rule owner-approved 2026-11-08 (Issue #292): remove ONLY a dated worktree whose commit is already on origin/signal-history and that holds no uncommitted change; keep and report anything else. Do exactly this:
1. `cd /home/user/Investment && git fetch origin research/corporate-event-readiness-v1` and ensure `pip install -q -r requirements.txt` has been done in this container.
2. Pre-run cleanup (pushed-only); report every KEEP line verbatim:
   cd /home/user/Investment && git fetch -q origin signal-history && for W in /tmp/kr-event-live-work-*/signal-history; do [ -d "$W" ] || continue; if [ -n "$(git -C "$W" status --porcelain)" ]; then echo "KEEP $W uncommitted-change"; elif git merge-base --is-ancestor "$(git -C "$W" rev-parse HEAD)" FETCH_HEAD; then git worktree remove --force "$W" && rm -rf "$(dirname "$W")" && echo "REMOVED $W"; else echo "KEEP $W unpushed-commit"; fi; done; git worktree prune
3. `rm -rf /tmp/kr-event-live-code && git worktree prune && git worktree add --detach /tmp/kr-event-live-code 8aee189ff453d9bd624a67df5e1e5975bd7d211c`
4. `cd /tmp/kr-event-live-code && python -m research.corporate_event_readiness_v1.cohort.live_run --workdir /tmp/kr-event-live-work-$(date -u +%Y%m%d)`
5. If step 4 printed RECORDED: `cd /home/user/Investment && git fetch -q origin signal-history && git show FETCH_HEAD:ledger/research-strategies/kr-corporate-information-events-v1/receipts.jsonl | tail -1` and confirm signalDate, eventCount and receiptSha256 equal step 4's output. Report MATCH or MISMATCH.
6. Repeat the step-2 bash exactly, then `cd /home/user/Investment && git worktree remove --force /tmp/kr-event-live-code; git worktree prune`.
7. Tell the user in one short Korean sentence: the status JSON, MATCH/MISMATCH, and any KEEP lines.
Never edit, re-date, backfill or rewrite a receipt; never read or compute a return, price, NAV or outcome; never change the commit, spec or authorization; never delete a worktree the step-2 rule keeps. If live_run raises, report the exact error and stop; the worktree stays and a missed session stays missed.
```

**첫 영수증(11-09 신호, 11-10 10:40 UTC 이후) 확인 방법**

```bash
git fetch origin signal-history
```

```bash
git show FETCH_HEAD:ledger/research-strategies/kr-corporate-information-events-v1/receipts.jsonl | python3 -c "import sys,json;[print(json.loads(l)['signalDate'],json.loads(l)['eventCount'],json.loads(l)['receiptSha256'],json.loads(l)['evidenceClass'],json.loads(l).get('identitySnapshotStale')) for l in sys.stdin]"
```

확인할 것:
- `signalDate` = 2026-11-09
- `evidenceClass` = `PROSPECTIVE_PAPER`
- `receiptSha256`이 예약 세션이 보고한 값과 같을 것
- `identitySnapshotStale` = **false**일 것. 유니버스는 2026-11-08 복구됐다(아래 1a절).

### 1a. PIT 유니버스 복구 확인 (2026-11-08)

Owner가 `Collect universe history`를 #324 브랜치(`d96c11b`)에서 실행했다(run `42529114342`, 성공). signal-history 커밋은 `0b3025d`다.

| 항목 | 전 | 후 |
|---|---|---|
| 최신 스냅샷 | 2026-09-01 | **2026-11-02** |
| 10-01 슬롯 | 행 0, done | 300행, 제공일 10-01 |
| 11-01 슬롯(일요일) | 행 0, done | 300행, 제공일 11-02 |
| 수집 영수증 | 없음 | `krx-universe-collection-receipts.json` 2건, 모두 `SNAPSHOT_ROWS_STORED` |
| 사용 콜 | — | 3 (휴장 1건) |

등록 코드 `8aee189`의 `identity.PitTop300`을 새 샤드에 그대로 돌렸다. 2026-11-09 영수증의 신원 스냅샷은 11-02(7일 전)이다. `MAX_IDENTITY_SNAPSHOT_AGE_DAYS = 62` 이내이므로 stale이 아니다. 예전에는 09-01(69일 전)이어서 stale이었다.

참고로 첫 실행 시각(11-09 10:40 UTC)은 KST 19:40이다. 11-09 세션 최종 마감(18:00 KST) 이후이므로 영수증 대상 신호일은 11-09다.

## 2. KR 시장 위험모델 전향 기록 — 구현 완료, 병합 대기 (Owner 승인 2026-11-08)

**상태:** 코드와 등록 파일은 이 브랜치에 있다. **main에 병합되기 전에는 아무것도 기록하지 않는다.** 등록 파일이 main에 들어간 커밋 시각이 승인 시각이 되고, 그 다음 KR 세션부터가 전향 구간이다.

| 구성 | 파일 |
|---|---|
| 기록기 | `scripts/record_kr_market_risk_model.py` |
| 별도 등록(봉인 사양은 수정하지 않음) | `research_specs/kr-market-risk-model-v1-prospective-registration.json` |
| 훅 | `scripts/update_ledger.py`, B-H1 훅 바로 아래. 자식 프로세스+타임아웃이라 종이 원장을 막거나 실패시키지 못한다 |
| 테스트 | `tests/test_kr_market_risk_model_recorder.py` (합성 입력, 가짜 시계) |
| 원장 | signal-history `ledger/research-strategies/kr-market-risk-model-v1/receipts.jsonl` |

**재사용한 것 (변경 없음):** `layer_states`, `build_receipt`/`append_receipt`(중복·역순·사양 변경·변조 거부), `rp1_b_h1_state.window_at`(쓰기 시계로 어느 세션의 창인지 결정), `prospective_receipt_core.check_timing`(종가 이후, 다음 개장 이전).

**등록이 고정하는 것:** 봉인 사양 SHA, 지정 결과 파일 SHA(`NO_CANDIDATE_NOMINATED_CONTROL_RETAINED`), 최종 구조 C0, 기록기와 의존 모듈 7개의 SHA. 하나라도 바뀌면 `REFUSED`로 멈춘다. 첫 신호 하한은 2026-11-13이다.

**실행안에서 달라진 점 (두 가지):**
1. FRED 입력은 `FRED_API_KEY` 시크릿이 아니라 **공개 fredgraph CSV**를 쓴다. 드라이 영수증과 vol63 교차검증이 같은 경로였고, 시크릿이 필요 없다. 등록 파일 `inputs.deviationFromPlan`에 적었다.
2. 대조군(ETF 100%, 고정 0.7)은 영수증에 필드로 넣지 않고 등록 파일에 명시만 했다. 영수증 스키마를 바꾸지 않기 위해서다.

**실데이터 점검 (드라이, 원장에 쓰지 않음):** 기록기의 상태 계산을 2026-11-06 실제 입력에 돌리니 FAST=2, SLOW=1, TRANSITION=0, vol63 0.5154로 이전 드라이 영수증과 같다. 다만 `vixPercentile`은 0.6887로, 이전 드라이의 0.7064와 다르다. 기록기는 봉인 실행과 같은 격자(KS200 첫 세션 1990-01-03부터)를 쓰고, 이 값은 격자 시작일에 따라 0.67~0.70 사이에서 움직인다. 어느 쪽이든 0.80 미만이라 TRANSITION=0이고 C0~C3 배수(모두 0.4)는 같다. 이전 드라이가 어떤 격자를 썼는지는 확인하지 못했다.

**한계:** 기록기가 실제 FDR·FRED에 붙어 영수증을 쓰는 것은 병합 후 첫 금요일 이후의 `ledger.yml` 실행에서야 확인된다. 영수증이 쓰여도 hash-chain 앵커 검증은 B-H1과 달리 넣지 않았다(append-only와 각 영수증 자체 해시 검증만 있다).

**병합 후 확인 방법** (첫 신호일 2026-11-13, 일요일 11-15 00:10 UTC 실행분까지 포함)

```bash
git fetch origin signal-history
```

```bash
git show FETCH_HEAD:ledger/research-strategies/kr-market-risk-model-v1/receipts.jsonl | python3 -c "import sys,json;[print(r['signalDate'],r['states'],r['candidateMultipliers'],r['evidenceClass'],r['receiptSha256']) for r in map(json.loads,sys.stdin)]"
```

`publication-status.json`이 같은 폴더에 있어 그 주에 무슨 일이 있었는지(RECORDED/SKIPPED/DEFERRED/REFUSED) 읽을 수 있다. 이 기록은 투자 권고가 아니고 운용 노출을 바꾸지 않는다(`productionEffect: NONE`).
