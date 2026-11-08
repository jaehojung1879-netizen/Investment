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

## 2. KR 시장 위험모델 전향 기록 — 실행안 (승인 필요, 미가동)

**현재 상태:** 사양 `prospective.status = DESIGNED_NOT_RUNNING`. 영수증은 0건이다.

**DRY 확인** (`kr-market-risk-model-dry-receipt-2026-11-06.json`, 원장에 쓰지 않음, 증거 아님)
- 봉인된 `layer_states`와 `build_receipt`를 현재 데이터로 실행했다. 입력은 FinanceDataReader KS200, FRED DGS10·DGS3MO·VIXCLS 공개 CSV이고, 입력 SHA256을 영수증에 기록했다.
- 2026-11-06 상태: FAST=2(추세·변동성 악화, vol63 0.5154), SLOW=1(10y-3m 재가팔라짐), TRANSITION=0(VIX 백분위 0.706 < 0.80).
- C0~C3 배수: **모두 0.4**. FAST=2이면 규칙상 모든 후보가 최소 노출이다.
- vol63 0.5154는 LIVE B-H1 영수증의 같은 날 값과 일치한다. 두 독립 경로가 같은 입력을 읽는다는 교차검증이다.

**이것은 투자 권고가 아니다.** 봉인된 역사 결과에서 C0/C1의 위험조정 우위는 입증되지 않았다. 하방위험당 수익은 전액 노출 0.58, C0 0.52, C1 0.53이다.

**실행안 (정확 해시 승인 대상)**
1. `scripts/record_kr_market_risk_model.py`를 하나 추가하고, `scripts/update_ledger.py`의 기존 훅 목록(B-H1 옆)에 연결한다. 실행 위치는 main `ledger.yml`이고, 기존 `FRED_API_KEY` Secret을 쓴다.
2. 재사용하는 것:
   - `kr_market_risk_model.layer_states`
   - `kr_market_risk_model_receipts.build_receipt` / `append_receipt`(append 전용, 중복·역순·사양 변경 거부)
   - B-H1의 KS200 경로와 `prospective_receipt_core` 타이밍 창
3. 매주 결정 세션마다 영수증 1건을 쓴다. 내용은 FAST·SLOW·TRANSITION 상태와 입력 해시, C0~C3 배수다. SLOW·TRANSITION은 사양의 FRED 공개 지연(`FRED_LAG_DAYS`)을 적용한 당시 이용 가능 값이다.
4. 대조군은 다음 두 가지다.
   - ETF 100%(배수 1.0)
   - **고정 0.7**(모델의 기존 REDUCED 수준이므로 새 파라미터가 아님)
   
   두 대조군은 결정적이므로 영수증에 명시만 한다.
5. 성과 평가는 H21/63/126 성숙 후에만 하고, 별도로 등록한다.
6. 거래, 운용 비중 변경, 승격은 없다. `productionEffect: NONE`.

필요한 승인:
- (a) 위 기록기 코드의 정확 해시
- (b) 사양 `prospective` 블록을 `REGISTERED_PROSPECTIVE_RECORDING`으로 바꾸는 새 등록. 기존 봉인 사양은 수정하지 않고 별도 등록 파일로 한다.
- (c) main 병합과 첫 기록일

현재 FAST=2로 모든 후보가 같으므로, 후보 간 차이를 보는 정보는 FAST가 1로 내려간 이후에야 생긴다.
