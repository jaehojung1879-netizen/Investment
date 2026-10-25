# Research Program v1 — Track A/B/C/D 실행 로드맵

**2026-10-25 보완:** Study B·C의 상위 관리는 [Market Research](market-research-program-v1-ko.md)에서 함께 추적한다.
Study ID·봉인·원장·판정은 독립이다. #285 B-H1은 병합되어 10/30 첫 상태 신호를 기다리며, US C1 단회 실행은
완료됐고 #288은 결과 보존 Draft다. #289의 새 C1c는 구현/합성·독립 감사 단계이며 역사 실행 승인이 아니다.
아래 10/18 시점 기록은 당시의 증거로 유지한다. 시장 모델의 성공은 Industry/Stock 연구의 선행 조건이 아니다.

**목표:** KR/US의 향후 6~12개월 초과수익·불확실성을 검증하고, 최종적으로 0~5종목·지역 ETF·현금을 비교한다. 현재 기본값은 기존 passive ETF 정책이다. 이 문서는 실행 순서를 갱신하며 가설·임계값·봉인·운영 정책·실행 권한을 바꾸지 않는다.

**확인 기준:** 2026-10-18 KST, GitHub `main` `786ae1269cc0c94076272e1a56d8e0028c5ed0e2`. [main Tests SUCCESS](https://github.com/jaehojung1879-netizen/Investment/actions/runs/39109316916). 아래의 입력 점검은 미래 라벨·종목 성과·모델·실행 잠금 없이 수행했다. 현재 시점의 실시간 데이터 준비를 인증하는 보고서는 아니다.

## 원 계약과 최신 증거

원 정의는 [03 A/B/C](03-studies-abc-ko.md), [04 공통 계약](04-common-research-contract-ko.md), [06 WP0~WP7](06-engineering-handoff-ko.md), [#247 Workbench](../experiment-workbench/README.md)를 따른다. [01 근거](01-methodology-evidence-ko.md)·[02 매트릭스](02-data-availability-matrix-ko.md)·[05 원 우선순위](05-priority-first-experiment-stop-list-ko.md)의 초기 미보정/미수집 상태는 다음 완료 증거로 보완한다.

- **WP1 [#257](https://github.com/jaehojung1879-netizen/Investment/pull/257), WP2 [#256](https://github.com/jaehojung1879-netizen/Investment/pull/256): 병합 완료.** [합성 보정](results/rp1-inference-calibration-v1-result.json)은 KR H252·US H126/H252 `CALIBRATED`, Study A 주 지평 H252. MDE80 약 4.1~4.3 × 추정량 SD는 실제 연 %p가 아니다. [US 모집단](results/rp1-wp2-us-universe-v1-ko.md)은 R-b 선택·각 연도 50% 관문 통과, 신원은 여전히 `PROVISIONAL`이다.
- **US A0 [#260](https://github.com/jaehojung1879-netizen/Investment/pull/260):** `a3021f3`, Draft·MERGEABLE, [Tests SUCCESS](https://github.com/jaehojung1879-netizen/Investment/actions/runs/39115532339). H1/H2/H3 측정률 58.127% / 58.092% / 1.030%, 모두 `PROSPECTIVE_ONLY`, A1 `NO_GO`, `MDE_UNRESOLVED`. 아직 main 결과가 아니다.
- **KR [Phase D #217](https://github.com/jaehojung1879-netizen/Investment/pull/217):** 2026-10-10 병합, [§7 종료 결정](../kr-alpha-research-final-development-assessment.md#7-공식-결정과-후속-범위). KR 역사 알파 탐색 종료. C1-KR도 봉인·종료. 입력 측정성과 미래 영수증 준비만 가능하다.

**A-KR → A2**, **B-KR → 상태 영수증**, **C-US → 승인된 C1 단회 실행**은 독립이다. D의 경제성 검증만 자격 있는 입력을 기다린다. US 데이터 복구는 KR 진전이나 C1의 선행 조건이 아니다.

## 트랙별 준비도와 다음 결정

| 트랙 | 구현·완료 / 종료 | 지금 실행 가능한 범위 | 차단 및 최소 독립 후속 PR | 다음 결과가 바꾸는 결정 |
|---|---|---|---|---|
| **A — KR 우선** | #247 PIT·계층·누설 계약, #250 KR 재무/산업 특징, #253 합성 실행기, 공통 전향 영수증 코어. **KR A1 역사 검정은 종료**. | 보존 입력으로 등록 A-H1~H3의 KR A0 측정. 충분히 관측되는 가설은 WP6 A2 영수증을 preview로 준비. | 정식 KR 사건률·26주 유지·H2 적격 분모·C13 구별성은 미측정. KR 전용 A0+WP6 preview PR. 실제 기록은 새 등록·승인 및 현재 입력 가용성/권리 확인 후. | 어떤 원 가설을 실제로 기록할 수 있는지, 무엇이 결측인지 결정. 과거 알파·종목 매수 여부를 판단하지 않는다. |
| **B — 독립 KR 시장 상태** | 기존 `MARKET_OBSERVED` FAST/SLOW/TRANSITION 및 B-H1 정의. 새 거시 모델 불필요. | 상태별 H63 비중첩 블록·입력 가용성 점검과 전향 상태 영수증 준비. B-H1은 A/C 결과 불필요. | 아래 블록 수는 충분해도 **Phase D 종료가 역사 모멘텀 성과 재검정을 허가하지 않는다**. 최소 PR은 B-H1 상태 영수증 preview, A/C와 별도 브랜치. B-H2만 지지된 A 신호를 기다린다. | 미래에 상태 조건부 비교가 가능한 표본을 쌓을 수 있는지 결정. 현재 비중 조절의 유효성을 주장하지 않는다. |
| **C — US C1 마무리** | #249~#255의 KR 동등성 `EXACT`, 원천 해시 freeze, refetch·검증기·단회 실행기 구현. **KR C 재실행 금지**. | 승인·해시·권리·원천 상태를 읽기 전용 확인. 새 수집 엔진은 필요 없다. | owner 실행 승인 파일 없음. 최신 재취득 관문은 실제 실행 때 다시 통과해야 한다. 최소 후속 PR은 소유자가 검토한 기존 형식의 승인 파일뿐이며 새 연구 설계는 없다. | 같은 자산에서 C0~C3의 손실 감소가 포기한 상승·재진입·비용을 정당화하는지 판단. 결과 자동 승격 없음. |
| **D — 결합·배분** | 공통 계약의 최대 5종목·비용·ETF 기본값, C2의 동일 종목 책 비교, 기존 passive 정책 재사용. 아래 최소 계약을 먼저 명시. | 입력 자격과 증거 연결을 설계. 투자 비중이나 실제 결합 성과는 만들지 않는다. | 검증된 A 선택 신호와 보정된 기대 순초과수익 없음. B/C의 중복 효과 미검증. 추후 최소 PR은 자격 검사+합성 composition adapter이며 최적화기가 아니다. | 검증된 신호를 추가해도 ETF보다 비용 차감 후 유용한지, C가 위험만 줄이는지 각각 검증할 자격을 결정. |

## A — KR A0를 측정할 근거는 있음, 통과는 미확정

기존 [#250 census](../winner-inflection-discovery/readiness.json)는 714주·85,680 Top120 구성원-주, 마지막 가격 연결일 **2026-09-11**이다. 탐색 Pattern B의 59/120 가용률은 등록 A-H1 측정률이 아니다. 영업이익 수준과 YoY 증가율의 부호 전환도 다르다.

이번 spot check는 #247 고정 원천 `signal-history@1bf68f59cffa20239977e2cfaa0f35a07d0ec884`의 DART/유니버스 허용 목록만 읽었다. `filing_prefix`와 기존 DART TTM·CFS/OFS·180일 정체 검사를 재사용했다. 2026-09-04와 09-11 각각 엄격 이전인 09-01 Top120에서, **120개 중 93개**에 H1의 필요 TTM 연쇄(현재·전년·직전 단계·그 전년 영업이익과 현재 OCF)가 있었다. 각 날짜 나머지는 연쇄/기준 결측 15, 비양수 YoY 기준값 8, 유효 가시 공시 없음 4다.

이는 적격 분모나 S=1 사건 수가 아니다. 비금융·보통주·유동성·산업, 최초 사건·26주 유지·구별성을 아직 적용하지 않아 **KR A0 `UNRESOLVED`**다. 최근 두 날짜로 전체 역사 또는 현재 전향 가용성을 인증하지 않는다. 다음 PR은 원 H1/H2/H3와 Top120/H2 적격 계약을 그대로 적용한다. 기준은 **유병률 3~50%, 측정률 ≥60%, 날짜당 S=1 ≥5(KR), H1–C13 |ρ|≤0.70**이다. 구별성 집계가 불명확하면 사후 규칙을 만들지 않고 보류한다.

독립적인 경제 단위 분산 근거가 없으면 **MDE_UNRESOLVED**, 연 4%p 통과 주장 금지다. 이는 KR 역사를 다시 열 이유도, A2 입력 기록 준비를 막을 이유도 아니다. 결측은 이유 코드로 남기며 S=0으로 대체하지 않는다.

**WP6 preview:** `prospective_receipt_core`의 정규 JSON·digest·append-only JSONL·18:00 KST 최종성·다음 개장 전 생성·승인 병합 KST 날짜 이후 경계를 재사용한다. 신호일/신원/H1~H3/available_at/observed_at/층/버전·사양·입력 hash와 기존 키↔Workbench Key 매핑을 보존한다. 충분히 관측되는 가설만 기록 준비, 나머지는 명시적 결측이다. 실제 영수증·스케줄은 별도 승인 전 비활성, 백데이트 없음. 결과는 H252 만기 후 별도 계층, 첫 판정은 원 규칙의 36개월이다. 기존 연구 영수증을 A로 재명명하지 않는다.

## B — 블록 수와 역사 종료는 다른 관문

보존 `FDR_KS200/normalized.csv`(SHA-256 `729a94b81dd45d1c5d1ab2ff692ec249bd5c9c4f24598d648d7f88010f193478`)에서 기존 FAST 함수와 **신호일까지의** 24개월 지수 수준만 사용했다. 2013-01-04~2026-09-11의 714개 완료 주간 신호를 점검했으며 모멘텀 종목 스프레드·미래 가격·수익 라벨·추론은 계산하지 않았다.

- B-H1 불리 상태: FAST=2 **또는** 직전 24개월 시장수익 음수. 주간 상태 296 / 다른 상태 418.
- 고정 KR 세션 원점(첫 완료 주 다음 세션), 63세션 간격, 각 진입 직전 완료 주의 상태, 달력상 종료된 블록만 포함: **53블록 = 불리 24 + 기타 29**. FAST=2만 떼면 2블록이다. 원 B-H1의 OR 조건을 FAST=2로 축소하지 않는다.
- 이 숫자는 **상태 기하 진단**이다. 24개월 기준일은 달력 24개월 전 이하 마지막 KR 세션으로 읽었다. 원 문서에 없는 블록 원점/경계의 기계 사양은 성과 열람 전에 확정해야 하며 이 진단이 그 등록을 대신하지 않는다. 비중첩은 통계적 독립성을 보증하지 않는다.
- 두 집단은 수치상 최소 6블록을 넘지만 **역사 추론 GO가 아니다**. KR Phase D와 기존 폐쇄된 모멘텀 연구를 재사용해 B-H1 성과를 다시 검정하지 않는다. 전향 state receipts로 간다. 향후 실제 적격 표본을 붙인 셀이 6블록 미만이면 `DESCRIPTIVE_ONLY_INSUFFICIENT_STATE_BLOCKS`, p=1 유지.

FAST는 같은 고정 지수의 추세·변동성, TRANSITION/SLOW는 원 시장 관측 자료의 4일 지연·14일 정체 규칙을 유지한다. ECOS/FRED 개정 거시를 PIT 경기 국면으로 부르지 않는다. B 영수증은 상태·시각·가용성·출처만 기록하며, 공통 코어를 공유해도 A와 승인·원장·진행을 독립시킨다.

## C — 동결 완료, owner 승인 없음

[원천 #255](https://github.com/jaehojung1879-netizen/Investment/pull/255)는 병합됐고 [Manifest](sources/rp1-c1-us-source-freeze-39080239146.json)는 `HASH_PINNED_REFETCH_RUNNER_TEMP_ONLY`, 당시 readiness READY·blocker 0이다. [실제 source probe](https://github.com/jaehojung1879-netizen/Investment/actions/runs/39076662529/job/117525109912)와 [재취득·합성 dry-run](https://github.com/jaehojung1879-netizen/Investment/actions/runs/39081014704/job/117537771295)은 SUCCESS. freeze run [39080239146](https://github.com/jaehojung1879-netizen/Investment/actions/runs/39080239146)는 Draft PR 생성 단계 FAILURE이므로 전체 성공으로 보고하지 않는다. 생성된 #255와 후속 dry-run은 별도 증거다.

이번 `run_rp1_c1_us_exposure.py verify`는 **VERIFIED**, snapshot pinned, dependency 84개, 미국 값/상태/재현 카운터 0. 기존 KR 동등성 기록 `EXACT`를 확인했으며 KR은 재실행하지 않았다.

- C1 scientific: `ad454ebbf2d7f0834b9de8ac136ba7842855d49146dbf1b123e1538fdc615252`. ^GSPC 가격지수·현금 0% PRIMARY, C0~C3·기간·비용·판정 불변.
- 별도 CASH_ECONOMIC: `50f1bbbdf671eeb5616e30ffef0475ec7a01bd171480cbb740052a4b748fc3e5`. SPY 현금배당 재투자+DTB3. vendor adjclose와 동일하지 않고 외부 SPY 총수익 독립 대조는 미완료다.
- PRIMARY의 ^GSPC/KR exact hash 유지. FRED_SP500 이동 창은 신원·최소 250공통일·일관성을 매번 검사. SPY vendor와 CASH/DTB3는 별도 scope, 불일치는 해당 경제성 `UNRESOLVED`. PRIMARY 통과는 비투자가능 가격지수의 결과이지 ETF 경제성 검증 완료가 아니다.
- **정식 승인 파일·결과·마커 없음, 원격 `rp1-c1` 잠금 ref 없음.** 과거 재취득 성공이 미래 동일성을 보장하지 않는다. Secret/Settings/외부 저장소 추가 0건.

남은 절차는 [기존 §6.4](rp1-c1-us-exposure-ladder-replication.md#64-실행-순서와-사람이-할-일)만 사용한다. 현재 pin·dry-run 증거·결과 열람 전 소유자 결정 기록·승인 절차는 [소유자 승인 패킷](rp1-c1-us-owner-execution-packet-ko.md)에 모았다. 승인 파일 초안의 확인사항 8개는 소유자가 직접 바꾸기 전까지 `false`다(동결 사양·실행기 변경 없음).

1. 기존 `seal-kr-factor-anatomy-v1.yml` / `main` / `rp1_c1_action=dry-run`: 최신 재취득·hash·readiness·동등성·합성 검사. 이번에는 dispatch하지 않았다.
2. `authorization-draft --owner <login>`의 exact pin과 별도 CASH 정의·권리·보존 한계를 소유자가 검토하고 기존 형식 승인 파일 PR을 커밋·병합. 템플릿은 승인 아님.
3. **별도 명시적 execute 승인 후** owner가 `rp1_c1_action=execute`와 승인 파일 SHA-256으로 dispatch. 재취득 exact hash·모든 관문 → 원자적 잠금 → 마커 → 실제 값. drift/접근 거부는 잠금 전 중단, 잠금 뒤 실패는 소진·재실행 금지.
4. 정확 바이트 결과 봉인 Draft PR 검토. 임계값 수정·자동 승격·운영 변경 없음. 원값은 runner 임시 취득·미배포 범위이며 해시는 원자료를 보존하지 않는다.

## D — 최소 결합 계약, 경제성 검증은 증거 이후

- **공통 입력:** Workbench Key/신호시각/available_at/observed_at/증거 등급·창/사양·코드·입력 hash/신원·산업/결측 사유. A는 원 가설과 검증·확률 보정 상태·불확실성·순초과수익 자격, B는 관측 상태와 그 조건부 효과의 검증 상태, C는 지역별 고정 노출 규칙과 그 승인·증거를 참조한다. 단순 A 사건 플래그는 투자 자격이 아니다.
- **기본값:** 적격 A 신호가 없으면 종목 0개, 기존 지역 passive ETF 정책 유지. 보정된 기대 순초과수익이 왕복 비용(종목+ETF 매도)을 넘는다는 근거가 없으면 활성 종목 비중 0. KR/US 합계 최대 5종목·원 섹터/종목 한도·현금/ETF 분리·레버리지 없음은 [04 §7](04-common-research-contract-ko.md#7-비용과-포트폴리오-제약)을 상속한다. KRW/USD를 검증된 환율·자본배분 정의 없이 합산하지 않는다.
- **중복 방지:** B의 조건부 효과가 C와 별개로 검증되지 않았으면 B는 문맥만 제공하고 추가 배수를 만들지 않는다. C는 동일한 고정 종목/ETF 책에 한 번만 적용하는 별도 비교다. 감축분을 ETF로 재투자해 위험 축소를 취소하거나 두 번 현금화하지 않는다. 실제 배분 산식/위험 예산은 경제성 열람 전에 별도 고정한다.
- **진입 증거:** A는 US A0+WP0+승인 A1의 개발 지지 또는 원 KR A2 전향 판정, 이후 확률 보정·비용/불확실성 관문이 필요하다. B를 배분에 쓸 때는 등록된 전향 조건부 효과·충분한 블록·C 대비 증분 증거가 필요하다. C를 쓸 때는 승인된 지역별 C1 해석과 사용자 위험 예산이 필요하다. B/C가 없더라도 자격 있는 A의 독립 경제성 검증을 막지 않는다.
- **나중의 검증:** 같은 날짜·같은 적격 모집단·같은 종목 책으로 ETF → A 책 → 검증된 B 조건부 기능 → C overlay를 한 요소씩 비교한다. ETF/현금 대안, 산술 선택/복리, gross/net·1/2/3배 비용, 교체/재조정 회전율, 하락 위험·상승 미참여·재진입을 분리한다. 종결 대가·수익 기준 미해결은 `UNRESOLVED`, 0 수익 대체 금지. 이미 노출된 역사를 독립 OOS로 재사용하지 않는다.

지금은 결합 검증 `BLOCKED_NO_VALIDATED_SELECTION_INPUT`이다. 이 계약은 주문·권고·비중·production 결정을 생성하지 않는다.

## 실행 큐 — 즉시 구현 PR은 최대 두 개

| 순서 / 담당 | 최소 범위와 독립성 | 완료·중단 조건 / 비용 추정 |
|---|---|---|
| **1. KR 수집기 무결성·저장 권리 — Engineering** | 기존 collector의 개장일 빈 응답/served date/완료 마커 정합성만 합성 검사·최소 수정. 권리 근거를 기존 문서에서 확인하고 불명확한 반복·영구·공개 저장은 보류. 다른 트랙 코드와 별도 브랜치. | 이번 합성 재현에서 2026-10-16(개장일)의 빈 `OutBlock_1`이 `closed`·done으로 기록됨. **보존 자료의 실제 오류를 입증한 것은 아님**. 원장·원천·done 파일 수선/재수집 금지. 봉인 의존 파일이면 수정 대신 비봉인 경계에서 차단. 약 0.5~1일, 외부 API 0. |
| **2. A-KR A0 → WP6 preview — Track A** | 기존 KR PIT 빌더로 원 H1~H3의 적격 분모·측정률·사건률·층·C13 중복성을 측정하고 같은 경로를 미래 receipt preview에 연결. 새 특징 엔진 없음. #260 미병합 코드를 main 완료로 가정하거나 US 복구를 기다리지 않음. | A0 실패는 원인과 `PROSPECTIVE_ONLY/UNRESOLVED`로 기록. 충분히 관측되는 가설만 WP6 기록 준비, 나머지는 명시적 결측. 실제 영수증·스케줄은 별도 승인. 약 1~2일, 기존 로컬 입력·합성 테스트, API 0. |

위 둘은 코드 준비를 병행할 수 있다. 새 실데이터를 쓰는 A/B 전향 기록은 해당 KR 원천의 현재 무결성·저장 권리 확인을 공유한다. 이는 **US 복구나 C1 결과 대기와 무관**하다. B의 독립 state-receipt PR은 슬롯이 비면 착수하며 과학적 선행 조건으로 A를 요구하지 않는다. D는 이 계약을 유지하고 증거 전 코드 확장을 하지 않는다. 이번 roadmap PR 자체는 문서 조정이며 위 구현 둘을 합친 PR이 아니다.

병렬 읽기 전용 점검:

- **C 담당/소유자:** 최신 dry-run 필요성·pin·권리·승인 파일 검토. 승인 파일 부재는 명확한 실행 차단이며 C1 결과를 열어 확인하지 않는다.
- **B 담당:** 위 진단의 원점·24개월 경계와 원 B-H1의 일치성을 기계 사양으로 검토. KR 종료 범위 확인 후 전향 상태 입력/receipt 스키마를 준비한다. 새 거시 수집 없음.
- **US 데이터 담당:** H1 **20개 신원, 2010~2011 filing lookback**만 복구 타당성·권리·공개 시각·TTM 연결을 검토하는 제한 파일럿. 대상은 결과와 무관한 결손 기준으로 먼저 고정한다. API/저장 권리 관문 전 다운로드 없음, 유료 전환·전면 backfill 없음. H2/H3나 연구기간을 변경하지 않으며 이 파일럿만으로 MDE/US A1이 해결된다고 주장하지 않는다.
- **전향 가용성 담당:** KR 가격·공시·산업·관측시각의 최신성 확인. 기존 Collect fundamentals 성공은 이용권·전체 입력 통과의 증거가 아니다. 위 KR 점검의 마지막 입력일을 오늘의 상태로 주장하지 않는다. US는 [기존 영속 수집 계약](../us-persistent-daily-collection-v1.md)의 권리·승인·저장 경계를 유지한다.

[#259 Tiingo](https://github.com/jaehojung1879-netizen/Investment/pull/259)는 별도 담당의 Draft다. 현재 Starter 원본/파생 영구 저장 `NO_GO`, memory-only 경로이며 H1 filing 파일럿의 대체가 아니다. 원본 영구 저장을 허가하는 것으로 해석하거나 실제 API를 실행하지 않는다.

**다음 의사결정:** KR 원 가설을 앞으로 기록할 수 있는가(A), 시장 상태별 미래 비교를 쌓을 수 있는가(B), 기존 위험 축소가 미국에서도 경제적으로 의미 있는가(C)를 각각 판단한다. 근거가 없으면 D와 실제 투자 기본값은 passive ETF에 머문다. 자동 병합·역사 결과 실행·봉인 해제·수집 스케줄·운영 변경은 이 로드맵의 승인 범위가 아니다.
