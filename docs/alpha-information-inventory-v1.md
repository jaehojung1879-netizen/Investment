# Alpha information inventory v1

> **This is a data/information inventory, not a research study. No Alpha
> model is trained here. No feature is correlated with future returns. No
> IC, no Top-N return, no quintile spread, no backtest is computed. No
> `FACTOR_WEIGHTS`, CHAMPION, selector, Kelly parameter, entry rule, region
> cap, macro multiplier, regional allocation, or production config is
> changed by this PR. `promotionEligible: false` is not applicable because
> nothing here is a promotable candidate — there is no scored ladder in this
> document at all.**

> **CORRECTION (`alpha-research-foundation-v2`, filed after this document was
> written).** Every claim below that `regional-alpha-model-v1` was
> `PENDING_EXECUTION` / "never been run" was WRONG. It was run twice for
> determinism on 2026-09-23 (workflow run
> [35826122755](https://github.com/jaehojung1879-netizen/Investment/actions/runs/35826122755),
> job log verified directly, not re-derived): a frozen 381,899-row feature
> manifest (hash `6261031bf59e725ca58342e4f320a8ed62e5d4e797dc6f580c2d372a830543b7`)
> was built without forward labels, labels were then constructed, and
> independent annual US/KR models were fit (US training rows grew
> 44,456→267,171 from 2016→2026; KR 15,294→75,743). Both runs produced the
> byte-identical classification `{"US": "NO_MODEL_EVIDENCE", "KR":
> "NO_MODEL_EVIDENCE"}`. The report artifact itself
> (`regional-alpha-model-v1-discovery-only`, 179MB) was never committed to
> `docs/results/` — that is why this document read it as unexecuted; it was
> executed and its result was simply never published. The correct status is
> `EXECUTED` / `NO_MODEL_EVIDENCE` (both regions) /
> `HISTORICAL_DISCOVERY_CLOSED_ON_EXISTING_FEATURE_SET` — closed for the
> 31-feature price/trend/risk + fundamental-level + fundamental-change matrix
> specifically, not a claim that no public information anywhere carries
> Alpha. See `docs/alpha-research-foundation-v2-errata.md` for the full
> correction and every passage below it touches; do not re-run this study —
> its one-shot historical-discovery budget for both regions is spent.

Companion documents (read these for full detail; this report summarizes and
cross-references them):

- `alpha-information-inventory-v1-data-map.md` — every information source,
  its Grade (A–E), independence, and time horizon.
- `alpha-information-inventory-v1-research-map.md` — every study already
  run in this repository, its verdict, and whether it needs re-research.
- `alpha-information-inventory-v1-gaps.md` — data gaps ranked by whether
  they block a genuinely new study.
- `alpha-information-inventory-v1-next-hypotheses.md` — up to five
  pre-registered next-study candidates, selected without looking at any
  return relationship.
- `docs/results/alpha-information-inventory-v1.json` — machine-readable
  version of the above.

---

## 요약 (Executive summary, 한국어)

이 문서는 **"우리가 요리할 수 있는 재료가 정확히 무엇인가"**라는 질문 하나에만
답한다. 어떤 재료가 맛있는지(Alpha가 있는지)는 다루지 않는다.

### 우리가 이미 가진 정보

- 프로덕션 4-factor 알파(momentum .30 / value .25 / quality .25 / lowvol
  .20)와 그 raw input 13개.
- 31개 feature로 구성된 지역별(US/KR) research-only 매트릭스
  (`regional_alpha_features.py`) — 가격/추세 21개, 재무 레벨 5개,
  재무 가속도 4개, 지역별 1개(US: 리더십 breadth, KR: 시가총액).
  **이 31개는 프로덕션과 별개의, 아직 한 번도 실행되지 않은 연구용
  feature matrix다.**
- Opportunity 변화탐지 모델의 28개 feature(레벨 19 + 변화 9) — 거래량
  서지, 모멘텀 가속도, alpha/value/quality percentile 등을 이미 ML로
  블렌딩해봤고, **결과는 기각됐다(decile monotonicity가 음수로 나옴).**
- 미국·한국 각각의 PIT(point-in-time) 안전 재무 데이터(Finnhub/DART) —
  단, **실시간(live) 빌드는 이 PIT 데이터를 쓰지 않고 Yahoo 현재값
  snapshot을 쓴다.** PIT 데이터는 replay/검증 경로에만 들어간다.
- 미국/글로벌 6축 매크로 regime 엔진(성장/물가/유동성/금융여건/위험선호/
  이익신용) — 전부 FRED/CBOE 기반, 한국 축은 존재하지 않는다.
- 기관 13F, 국민연금 자산배분, 전문가 컨센서스 — 모두 UI 패널용으로만
  수집되고 알파 스코어링에는 전혀 쓰이지 않는다.

### 가지고 있지만 안 쓴 정보

- `revenueGrowth`, `dividendYield` — 매 빌드마다 수집되지만
  `longterm.py`가 읽지 않는다.
- MACD, Bollinger, RSI-28, 대부분의 VIX/매크로 스트레스 feature — 단기
  ML 모델용으로만 계산되고 4-factor 알파에는 안 들어간다.
- DART/Finnhub의 원시 부채·자산·자본 레벨 — 비율(debt/equity)만
  노출되고 레벨 자체는 저장 후 버려진다. 즉 부채/자산 성장률은
  "데이터가 없어서" 못 만드는 게 아니라 "노출 코드가 없어서" 못 만든다.
- KRX 배당·순매수·공매도 통계는 KRX 공식 포털에 실재하지만, 현재
  구독된 Open API 키로는 닿지 않는다.

### 중요한데 현재 없는 정보

- 한국 투자자별 수급(외국인/기관/개인) — 한국 연구 전체에서 완전히
  부재. 가장 큰 structural gap.
- 한국 매크로(ECOS) — fetch 함수가 **하나도 존재하지 않는다.**
  게다가 `KTB_3Y`와 `CorpBond_3Y`가 동일한 series ID(817Y002)를
  공유하는 실제 버그가 확인됐다.
- 애널리스트 추정치 변경(revision) — 미국은 유료 등급, 한국은
  이용약관상 불가능으로 이미 기각됨.
- 회계 품질(accrual, cash conversion 등) — 원자재는 이미 수집돼 있지만
  파생 필드가 없다. 가장 저비용으로 새로 만들 수 있는 그룹.

### 과거 재현이 가능한 정보

- 한국 대량보유(5%룰) 공시 — DART의 기존 receipt-date PIT 패턴을 그대로
  재사용 가능. **이 인벤토리에서 발견한 가장 저비용의 신규 구축 항목.**
- 미국 배당 변경 — Finnhub PIT 저장소에 원시 필드가 **이미 존재.**
  파생 필드만 추가하면 됨.
- 미국 Form 4(내부자 거래), 공매도(FINRA/Nasdaq) — 공식·무료 소스가
  존재하지만 이 환경에서는 SEC 도메인 전체가 차단돼 있어 접근 불가.

### 과거 재현이 어려운 정보

- 옵션 데이터(개별 종목, historical) — 무료 공식 소스 없음.
- 신용등급 변경 — 무료 공식 소스 없음.
- 과거 시점 섹터 분류 — backfill 가능한 소스를 찾지 못함.
- 시장 미시구조(호가, 체결 단위) — 이 저장소 어디에도 존재하지 않음.

### 이미 연구한 아이디어

- 4-factor sub-factor attribution: 전부 region-sign-unstable, 유의하지
  않음.
- Fundamental acceleration: CASE D, 증거 없음.
- Lowvol 분리, risk denominator 분리, calibration ordinal rescue,
  dynamic breadth, region quota 제거, entry-selection 분리: 전부
  신뢰구간이 0을 포함하거나 통제군보다 나쁨.
- Selection value decomposition: "고르지 말고 스크린만 들고 있자"는
  가설이 **자체 사전등록 테스트에서 기각됨.**
- Opportunity 모델: "거래량 서지 × 모멘텀 가속도 × 재무 건전성"을
  이미 ML로 테스트했고 **기각됐다.**

### 아직 연구하지 않은 이론

- 매크로 regime × 종목 레벨 feature의 상호작용(예: 유동성 축 × 모멘텀
  가속도) — 코드 어디에도 없음, 신규 데이터 불필요.
- 한국 투자자 수급 × 가격 리더십.
- 한국 대량보유 공시 × 소유권 변화.
- 원시(percentile 아닌) 거래량 magnitude × 재무 건전성 조건화 —
  **단, Opportunity 모델과 정보 중복이 크므로 반드시 construction을
  다르게 해야 함.**

### 다음 모델링 전에 반드시 해결할 데이터 공백

**정정 (v2):** `regional-alpha-model-v1`은 이미 2026-09-23에 실행되어
US/KR 모두 `NO_MODEL_EVIDENCE`로 종결됐다. 즉 "실행"은 남은 공백이
아니다 — 기존 31-feature 매트릭스(price/trend/risk + fundamental
level + fundamental change)에 대한 historical discovery는 두 지역
모두 닫혔다. 남은 진짜 공백은:

1. 한국 투자자 수급 접근 경로(KRX Open API 구독 범위 또는 네트워크
   경로) — `NO_MODEL_EVIDENCE`가 나온 매트릭스에는 이 정보군이 전혀
   없었다.
2. ECOS fetch 레이어 구축 + `KTB_3Y`/`CorpBond_3Y` 중복 ID 수정.
3. DART 대량보유(5%룰) 신규 모듈.

### 다음 단계 추천

**CASE B — DATA_BUILD_REQUIRED.** (정정: 이전 버전은 `regional-alpha-
model-v1` 실행 자체를 "신규 데이터 불필요한 다음 행동"으로 추천했으나,
그 연구는 이미 실행·종결되었으므로 더 이상 할 일이 아니다.) 다음
우선순위는 §5 Decision Gate와 next-hypotheses 문서, 그리고
`docs/alpha-research-foundation-v2-errata.md`를 참조.

---

## 1. Scope and method (English)

This PR answers exactly one question: **what raw material does this
repository already have, already use, already collect-but-not-use, or could
acquire, and how reproducible is each piece historically?** It does not
measure whether any of that material predicts returns. Per the task's own
principle (§0): a feature that "looks good" is not evidence of anything
here, because no feature was scored against an outcome to produce this
report. Any number quoted from `AGENTS.md` or a `docs/results/*.md` file
below is cited as `PREVIOUSLY_REPORTED_RESULT` — it was not recomputed.

Six read-only research passes fed this report, each scoped to a cluster of
the repository and cross-checked against `AGENTS.md`'s own invariants
sections (which already encode a large fraction of this repository's prior
findings in a compact, versioned form):

1. Core architecture — ledger schema, replay generations, the "31 features"
   question, `build.py`'s pipeline order.
2. Existing alpha studies — every challenger/ablation module and its
   published verdict.
3. The Opportunity change-detection model and the regime/macro/sentiment/
   rotation engine.
4. Every data-source module in `pipeline/` and whether its output reaches
   any alpha-scoring path.
5. US external-source feasibility (SEC Form 4, short interest, analyst
   estimates, options, corporate events, FRED/ALFRED).
6. KR external-source feasibility (KRX investor flow, short selling, ECOS,
   KOSIS, DART large-holdings, FX).

---

## 2. Core architecture — the load-bearing facts

- **The "31 features" the task named are `regional_alpha_features.feature_manifest()`'s**
  **eligible rows** (`pipeline/regional_alpha_features.py:60-83`) — a
  **research-only module with zero production imports**, not production's
  4-factor score and not the Opportunity radar's 28-column feature set. Both
  regions land on exactly 31 (US: +leadership breadth; KR: +market cap). No
  literal "31" constant exists anywhere in the codebase; this is
  reproducible by counting, not a hard-coded number. See the data map §1.
- **A signal ledger row has 37 top-level keys**, of which a `features`
  sub-block carries 28 (matching `opportunity.FEATURE_COLUMNS` exactly —
  19 level + 9 change features). An outcome row is keyed by horizon
  (21/63/126/252 trading days) with `absoluteReturn`, `benchmarkReturn`,
  `excessReturn`, `costAdjustedExcessReturn`, `mfe`, `mae`, `maxDrawdown`,
  `realizedVol`, `downsideVol`, `cvar95`, `endDate` per horizon. Full field
  list in the core-architecture research (not separately republished here —
  see the data map for the parts that matter to feature inventory).
- **Replay generations run v4 through v16**, each triggered by a specific,
  documented defect fix or coverage expansion (survivorship, Korean vendor
  session gaps, benchmark total-return symmetry, US/KR PIT fundamentals
  opening) — never by a scoring change alone. `provenance.py` is the single
  source of truth for `REPLAY_VERSION`/`FEATURE_VERSION`/`DATA_VERSION`/
  `MODEL_VERSION`, re-exported (never redefined) everywhere else.
- **`build.py`'s pipeline order** resolves universe → fetches prices/macro/VIX
  → per-ticker feature/risk/entry/short-term-model loop → sentiment → regime
  → fundamentals snapshot → 4-factor longterm build → Kelly shadow portfolio
  → Opportunity/warning radars → expert/13F/NPS panels → direction/rotation
  → payload assembly → final safety gate (which, if tripped, strips all
  actionable output per this repository's own blocked-artifact invariant).

---

## 3. The Opportunity model — direct answers to the nine questions this task asked

1. **Q1 (volume shock × momentum acceleration × healthy fundamentals) —**
   this combination has **already been tried, via ML, and rejected.** See
   the research map §5 and the explicit overlap warning carried into
   next-hypotheses H2.
2. **Q2 (fundamental quality) —** yes, `valuePercentile`/`qualityPercentile`
   are two of its 19 level features.
3. **Q3 (macro regime) —** no. Attached to the training row for diagnostics
   only; never passed to the classifier.
4. **Q4 (sector context) —** mostly no. Only a narrow, explicitly-disclaimed
   member-median relative-momentum proxy (`sectorRotationImproved`), not
   `rotation.py`'s ETF-based sector read.
5. **Q5 (investor flow) —** no. Zero flow-derived features anywhere in the
   model.
6. **Q6 (completed historical validation?) —** yes, twice (opportunity +
   warning radars), against `replay-v14`, with LightGBM **actually
   executed** (not merely wired up) across 4 targets, alongside 6 other
   model families.
7. **Q7 (accepted?) —** **no, both rejected.** The opportunity radar failed
   decile monotonicity with a **negative** value (−0.1152) — its
   highest-scored decile underperformed its lowest-scored decile in the
   test period — and failed to beat a plain logistic baseline.
8. **Q8 (live in production today?) —** the radar *code path* runs on every
   build; the *ML score* inside it does not, for two independent reasons:
   the committed model was trained on `replay-v14` while production is now
   on `replay-v16` (a generation mismatch that silently strands it), and
   separately it already failed its own acceptance gate regardless. Every
   build currently serves the transparent rule-based fallback score.
9. **Q9 (overlap with a new Conditional Alpha study) —** substantial, for
   any construction that blends volume shock, momentum acceleration, and
   fundamental quality via a learned model on percentile-only inputs. A new
   study must state explicitly what makes its construction different (see
   next-hypotheses H2).

No `docs/results/opportunity*` report exists — this model has never been
written up despite being executed twice; this report is the first time its
result has been documented outside the raw JSON on the `signal-history`
branch.

---

## 4. Regime/macro engine — what it is and is not

Production's 6-axis regime engine (`regime.py`) is **entirely US/global**
(21 indicators, all FRED or CBOE). Korea has **zero** regime-axis
representation — the only Korean macro numbers reaching the site are four
display-only rows never read by the regime classifier. `sentiment.py` is
confirmed to be a price/breadth-derived Fear & Greed index, **not** news or
search sentiment — no such data source exists anywhere in this repository.
The previously-documented measurement-absence defect in `sentiment.py`
(200-day breadth publishing 0% instead of `None`) is **confirmed fixed** in
the current code.

A region×bucket×macroRegime portfolio-outcome interaction diagnostic
(`historical_calibration.regime_interaction`) already exists and runs on
every build, but its `activate` flag is never consumed downstream — it
influences nothing today. The narrower, stock-level feature×regime
interaction (e.g. momentum acceleration × financial conditions, volume
shock × quality × liquidity regime) is **confirmed genuinely absent** — not
one file combines these anywhere in `pipeline/` or `scripts/`.

One unrelated dead-code finding surfaced during this pass: `direction.py`
reads a `"stance"` key from the macro summary that `macro.py` has not set
since `regime.py` replaced the old threshold system — a descriptive-panel
signal silently always reports "Stable." Not an alpha-scoring defect;
flagged for whoever next touches `direction.py`.

---

## 5. Answers to the 20 specific questions (§44 of the task)

1. **What information groups have we actually used?** Price/momentum
   (production sleeve + ML features), fundamental level (production sleeve,
   live path only — see #4), fundamental acceleration (tested, CASE D),
   volume surge (percentile-only, Opportunity radar), a US/global 6-axis
   macro regime (portfolio-level only, never interacted with stock features
   until this report's H1), and a breadth/momentum-derived sentiment index.
2. **How much of the total investable-information universe did "31
   features" cover?** A narrow slice: price/trend and fundamental-level/
   acceleration only, one region-specific extra field each. No volume
   magnitude, no investor flow, no analyst expectations, no accounting
   quality beyond profitability levels, no macro interaction, no corporate
   events.
3. **How shallow was volume/liquidity usage?** Extremely shallow — exactly
   one ratio (5D/60D volume) exists anywhere in the codebase, always as a
   percentile, never as a magnitude. Everything else in the data map's §4
   volume table is computable from data already stored but not built.
4. **What has the Opportunity model already tried?** See §3 above — a full
   ML blend of price/volume/fundamental-percentile features, executed
   twice, rejected twice.
5. **Why is Opportunity different from Regional Alpha v1?** Opportunity is
   a change-DETECTION classifier (predicts a discrete forward-excess
   target from level+change features via ML); Regional Alpha v1 is a
   region-specific re-RANKING of the cross-section (Ridge/HGBR) over a
   broader, PIT-reconstructible 31-feature matrix. Different question,
   overlapping raw ingredients.
6. **Was Opportunity validated?** Yes, walk-forward + sealed holdout, twice.
   Rejected both times on its own pre-registered acceptance gate.
7. **How far has macro-regime × stock-feature interaction gone?** A
   portfolio-outcome interaction diagnostic exists and is unconsumed; a
   stock-feature interaction has never been coded. See §4.
8. **Is Korean investor-flow data actually reachable back to 2013?** Not
   confirmed either way within this task's no-bulk-download constraint. The
   *source* is real, free, and official; the *current access path* from
   this project's sandbox is blocked. Historical depth back to 2013 was not
   independently verified.
9. **What official US investor-behavior data exists beyond 13F?** Form 4
   insider transactions (SEC's own structured extraction, 2006+) and
   FINRA/Nasdaq short interest (2007/2013+) — both Grade C, both blocked by
   the same SEC-domain-wide access issue for Form 4, and needing a PIT-lag
   correction for short interest.
10. **Can Form 4 be used as historical PIT?** Yes in principle (filing
    timestamps are genuine PIT), but blocked in this environment by the
    proven SEC domain-wide 403; no free alternate vendor was found.
11. **How far can short-interest data be acquired?** Official sources exist
    with adequate depth; the specific "OTC-only before 2021" vs
    "exchange-listed since 2007" discrepancy across sources was not
    resolved live and needs a direct check before building.
12. **Can KRX short-selling/securities-lending data be acquired
    historically?** Access-wise, yes (same mechanism as investor flow); but
    it spans at least three regulatory regimes (two multi-year bans) that
    must be carried forward explicitly, never averaged away.
13. **Is analyst revision data the biggest missing information?** It is the
    largest *named* gap that is also confirmed **not freely closable** —
    Grade D (US) / E (KR). Whether it is the single biggest gap in impact
    terms cannot be answered without measuring performance, which this
    report does not do.
14. **How far can free data take us?** Far enough to build 3 of the 5 next
    hypotheses (H1-US, H3, H4, H5) without paying for anything; analyst
    estimates and per-equity options data are the confirmed exceptions.
15. **What important axis needs paid data?** Analyst estimate revisions
    (both regions); per-equity historical options data; credit rating
    changes.
16. **Can historical sector context be restored?** No backfillable
    point-in-time source was found; today's classification cannot be
    projected onto the past without violating this repository's own PIT
    discipline.
17. **How much does KR macro infrastructure need?** A complete build — the
    ECOS fetch layer is 100% unbuilt, and one of its nine configured series
    IDs is confirmed duplicated/ambiguous.
18. **What does the repo already collect but not use in alpha scoring?**
    See the data map §23 — 13F, NPS allocation, expert consensus,
    `revenueGrowth`/`dividendYield`, most ML technical features, and (for
    the live daily score specifically) the entire PIT fundamentals sleeve.
19. **What minimum new information would make the next study genuinely
    different from prior research?** At least one of: KR investor flow, KR
    macro/regime, raw (non-percentile) volume magnitude with a hand-specified
    interaction, accounting-quality ratios, or KR ownership-disclosure data —
    per the research map's §8 comparison table.
20. **Should Conditional Alpha v2 be built now, or is data-build first?**
    See the Decision Gate below.

---

## 6. Decision gate

### CASE B — DATA_BUILD_REQUIRED

Genuinely new, economically distinct information axes exist and are
identified (KR investor flow, KR macro/regime, KR large-holdings disclosure,
accounting-quality ratios, US dividend-change) — but every one of them
either lacks a working collection pipeline today or needs a schema fix
before it can be used (the data map and gaps document detail exactly which).
None is Grade A (immediately usable, PIT-safe, sufficient history, no
lineage issue) on its own. This is not CASE C
(`NO_MEANINGFUL_NEW_INFORMATION`) — the research map's §8 comparison table
shows real, HIGHLY_DISTINCT candidates that overlap nothing already tried.
It is not CASE A
(`READY_FOR_CONDITIONAL_ALPHA_PREREGISTRATION`) either, because that case
requires at least two independent new axes that are already PIT-safe with
sufficient historical depth on a stable source — and while H1 (US) and H5
need no new collection, neither is, by itself, the kind of broad new
information axis "Conditional Alpha v2" implies; they are narrow additions
(a regime interaction over existing series; one corporate-action field).

**CORRECTED (v2):** the paragraph below, as originally written, recommended
running `regional-alpha-model-v1` as the zero-new-data first action. That
recommendation was based on a factual error: the study had already been run
on 2026-09-23 (see the correction note at the top of this document) and
closed both regions at `NO_MODEL_EVIDENCE`. It must not be run again — its
one-shot historical-discovery budget is spent for both regions. The
corrected recommended order follows.

**Recommended order, none of it decided by this document (that decision
belongs to whoever pre-registers the next study), only sequenced by
data-readiness:**
1. Pre-register and test H1 (US arm) and/or H5 — both need no new data
   collection, and neither re-uses `regional-alpha-model-v1`'s spent
   discovery budget since both are different constructions (a regime
   interaction, a dividend-change derivation), not a re-run of the same
   31-feature matrix.
2. Build the DART large-holdings module (H4) — the cheapest genuine data
   build identified.
3. Build KR investor-flow access (H3) and the KR ECOS layer (blocking H1's
   KR arm) — the two structural gaps that take the longest to close.

---

## 7. Production safety — confirmed unchanged

No file under `pipeline/` was modified. `config.json` was read, never
written. No `FACTOR_WEIGHTS`, CHAMPION, selector, Kelly parameter, entry
rule, region cap, macro multiplier, or regional-allocation value changed.
No historical artifact, signal-history record, or outcome ledger entry was
modified. Six read-only agents performed a handful of `WebSearch`/`WebFetch`
calls for external-source feasibility research and no bulk downloads; every
claim about external sources is marked in the data map with its
verification status (live-checked vs documentation-only-assessment).

## 8. GitHub Actions

**No workflow needs to run for this PR.** This is a documentation-only
change — zero files under `pipeline/`, `scripts/`, or `tests/` were touched;
this PR adds only `docs/*.md`, `docs/results/*.json`, and one new `AGENTS.md`
section. `ruff check .` and `python -m compileall pipeline` were run locally
before this PR and both pass with no findings. `pytest -q` was not run
(no `pytest` install available in this session's environment, and no
Python file changed that would need it); CI's own `tests.yml` will run it
as usual on the PR. No new workflow file was added and none is proposed.
