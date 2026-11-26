# Codex 실행 프롬프트 (작업 A~D)

## 공통

- **저장소 규칙**: AGENTS.md를 따른다.
- **변경 후 검사**: `ruff check .`, `python -m compileall pipeline`, `pytest -q`, `python scripts/make_seed.py`, `python -m pipeline.validate data/site-data.json --allow-seed`
- **금지**
  - 봉인 사양·결과·기존 전향 기록·운영 전략 변경
  - main 직접 병합
  - 유료 구매
  - 테스트 건너뛰기
- 비공개 입력(가격·특징 pkl)은 git 밖에 둔다. 경로는 인자로 받는다.

### 의존성과 병합 순서

```
A(계보 정정) ──▶ B(#355 보고서 정정) ──▶ (#355 병합 판단)
C(데이터 타당성) ─────────────────────────▶ (반도체 파일럿 착수 판단)
D(전향 기록 구조) — C의 원천 목록을 입력으로 쓰지만, 코드는 독립. 실행은 사용자 승인 후
```

- A와 C는 병렬로 진행할 수 있다.
- B는 A의 영향 목록이 확정된 뒤 진행한다.
- D의 워크플로 정기 실행은 사용자 결정 3번 이후다.

---

## 작업 A — #353 정정의 공용 입력 반영과 재현성 검증

**배경**
- #354·#355가 읽은 미국 `features.pkl`(sha `49062dba…`)은 #353이 공시로 검증한 943행(`research/kr_us_public_buys_v1/results/WAT/corrected-caps.csv`, sha `90876398…`)을 반영하지 않았다.
- Codex 쪽 #350~#353은 다른 특징 파일(sha `b0092244…`)을 썼다.
- 감사: `research/investment_decision_alpha_v1/AUDIT-ko.md` §1.

**할 일**

1. **두 특징 파일의 행 단위 비교**(`b0092244…` 대 `49062dba…`)
   - 키는 `(date, ticker)`다.
   - 열별로 다른 셀 수와 최대 차이를 기록한다.
   - 결과는 `research/lineage_audit_v1/features-diff.json`.
   - 두 파일을 모두 확보하지 못하면 그 사실만 기록하고 2단계로 간다.
2. **정정본 생성(공용 입력은 덮어쓰지 않는다)**
   - `research/investment_decision_alpha_v1/lineage_353_354.py`의 `audit()`을 그대로 써서 `features-v2-353corrected.pkl`을 만든다.
   - 원본·정정본·정정 파일의 sha256과 바뀐 셀 수(943)를 `research/lineage_audit_v1/manifest.json`에 기록한다.
   - 같은 매니페스트에 FISV 1셀 가격 정정(#351 `research/kr_us_exposure_preserving_v1/inputs/US/fisv-repair-applied.json`)도 별도 항목으로 넣는다.
3. **영향 목록 작성**
   - `marketCap`·`capTercile`·`earningsYield`·`bookYield`를 소비하는 모듈을 정적으로 찾는다(`grep -rn "marketCap" research --include=*.py`).
   - 각 모듈이 만든 커밋된 결과 파일 목록을 `research/lineage_audit_v1/impact.csv`에 쓴다. 열: 모듈, 결과 파일, PR, 소비 방식(비중·3분위·수익률).
4. **재실행**(결과는 새 경로에만 쓴다)
   - #346 칵테일, 6차 U1~U3, #347 시총 필터, #348 업종·시총 통제, #343 미국 선택 규칙을 정정본으로 다시 계산한다. 출력은 `research/lineage_audit_v1/rerun/<원 연구 이름>/`.
   - 원 결과 파일은 수정하지 않는다.
   - 차이표 `research/lineage_audit_v1/REPORT-ko.md`의 열: 원 값, 정정 값, 판정 변화 여부.

**테스트**
- `tests/test_lineage_audit_v1.py`를 추가한다.
  - 정정본은 원본과 정확히 943셀만 다르다.
  - 정정 셀의 SEC 접수 시각 < 판단일 마감(`wat_sources.decision_close`).
  - 정정 전 입력으로 재실행하면 원 결과가 그대로 재현된다(최소 한 연구, 소수 6자리).

**검증 기준**
- 원 입력 재실행 재현 오차 ≤ 1e-9.
- 정정 재실행의 판정 변화가 표에 모두 나타난다.

**중단 조건**
- 원 입력으로 원 결과를 재현하지 못하면 정정 재실행을 하지 않는다. 재현 실패 원인을 먼저 보고한다.
- Codex 특징 파일이 이 저장소의 어떤 커밋에도 해시로 고정돼 있지 않으면, 두 계열의 행 비교는 "확보 불가"로 남긴다.

**PR 경계**: 새 디렉터리 `research/lineage_audit_v1/`와 테스트 1개만 추가한다. 공용 입력의 교체는 이 PR에 넣지 않는다(사용자 결정 2번 이후 별도 PR).

---

## 작업 B — PR #355 보고서 정정

**대상**
- `research/investment_decision_alpha_v1/REPORT-ko.md`
- `research/HANDOFF-2026-11-15.md`의 10차 라운드 절

**할 일**

1. REPORT의 "② 실제 투자 행동" 표에서 일반화된 세 행을 `AUDIT-ko.md` §2·§3·§4의 한정 문장으로 바꾼다.
   - "기계적 회피·축소 규칙을 쓰지 않는다"
   - "기다리지 말고 지금 산다"
   - "이 신호만으로 줄이지 않는다"
2. "무작위 200회보다 모두 나쁨" 문장마다 `INVALIDATED(노출 불일치 대조)`를 표시한다.
3. 각 결론 문장 끝에 AUDIT §6 상태표의 상태를 단다.
   - 상태: VERIFIED, EXPLORATORY, NOT_SUPPORTED, SOURCE_BLOCKED, PROSPECTIVE, INVALIDATED
4. HANDOFF 10차 절의 "BOOM 회피·축소 규칙은 오히려 손해였다"를 "이번 BOOM 규칙의 우위가 확인되지 않았다"로 바꾼다.
5. 작업 A의 영향 목록이 나오면, 거기 든 과거 보고서마다 첫 장에 "정정 전 입력에 조건부" 고지를 단다.
   - 각 보고서에는 한 줄만 추가하고 숫자는 바꾸지 않는다.

**테스트**: 문서 변경뿐이다. 저장소 검사가 그대로 통과하는지 확인한다.

**검증 기준**: REPORT에 AUDIT §6 18개 주장 각각의 상태가 빠짐없이 대응한다.

**중단 조건**: 숫자를 바꿔야 하는 문장이 나오면 문서에서 고치지 말고 작업 A의 재실행 결과를 기다린다.

**PR 경계**: #355 브랜치(`research/investment-decision-alpha-v1`) 위의 커밋으로만 진행한다. 코드 변경은 없다.

---

## 작업 C — 차세대 데이터 타당성 조사

**배경**: `research/next_alpha_program_v1/SEMICONDUCTOR-PILOT-ko.md`의 착수 조건 1~3과 `PRIORITIES-ko.md` §4·§5.

**할 일**

1. **원천 실측 프로브**
   - `scripts/probe_industry_sources.py`를 만든다. 표준 라이브러리만 쓰고, URL을 고정하며, 원천당 1회 시도한다.
   - 기존 `.github/workflows/probes.yml`의 드롭다운에 옵션으로 추가한다(v2.25 규칙: 새 워크플로를 만들지 않는다).
   - 대상과 기록할 것은 다음과 같다.

   | 원천 | 기록할 것 |
   |---|---|
   | 관세청 수출입무역통계: HS 8542 월간, 10일·20일 잠정 | 접근 가능 여부, 시작 월, 단위(금액·물량), 공표일 필드 유무 |
   | 한국은행 ECOS 수출물가지수: D램·플래시 품목 코드 | `pipeline/ecos_macro.py`의 `resolve_spec` 규칙대로 표·항목·주기를 실측으로 확정. `ECOS_API_KEY`는 Secret |
   | 국가데이터처 KOSIS 광업제조업동향: 반도체 생산·출하·재고지수 | 통계표 ID, 시작 월, 개정 공지 |
   | WSTS 역사 청구 보고서(무료 엑셀) | 최신 월, 지연 |
   | FRED/ALFRED `IPG3344S` | 빈티지 날짜 수, 첫 빈티지(기존 `scripts/probe_alfred_macro_vintages.py`의 `series/vintagedates` 방식 재사용) |

2. **개정 폭 측정**
   - 위 원천 중 과거 보도자료가 있는 것을 대상으로 한다(관세청·산업부 월간 수출입 보도자료, 한국은행 수출입물가 보도자료).
   - 같은 월의 최초 공표값과 현재 값을 12개월 이상 비교한다.
   - 결과는 `research/industry_data_feasibility_v1/revisions.json`.
3. **중복 측정**
   - 반도체 지표 월간 변화(가능한 원천만)를 같은 공표일까지의 삼성전자+SK하이닉스 바스켓 − KODEX 200 수익(공식 대조 총수익 정의)으로 회귀하고, R²를 기록한다.
   - **수익 예측 검정은 하지 않는다.** 공표일까지의 동시 설명력만 잰다.
4. **확장 유니버스 점검(성과 계산 금지)**
   - 한국 121~300위:
     - KRX 일봉 원장으로 월별 구성을 재구성할 수 있는지 확인한다.
     - DART 미수집 종목 수를 센다.
     - 상장폐지 수를 센다.
     - 거래대금 분포를 기록한다.
   - 미국 S&P 400: 무료 PIT 구성 원천의 유무만 기록한다.
   - 결과는 `research/industry_data_feasibility_v1/universe.json`.
5. 위 결과로 `research/next_alpha_program_v1/SEMICONDUCTOR-PILOT-ko.md` §1 표의 "미확인" 칸을 실측값으로 바꾼 새 버전을 만든다. 원 표는 남겨 두고 날짜를 붙인다.

**테스트**
- 프로브의 응답 분류에 대한 합성 픽스처 테스트를 만든다(`SERVED`/`EMPTY_BUT_VALID`/`BLOCKED_SOURCE`/`AUTH_REQUIRED`/`SCHEMA_CHANGED`).
- URL에 키가 로그로 나가지 않는지 테스트한다.

**검증 기준**: 각 원천의 상태가 `SERVED` 또는 구체적 거부 사유로 기록된다. "확인함"은 실제 응답 해시가 있을 때만 쓴다.

**중단 조건**
- 원천이 거부하면 우회(UA 변경, 다른 호스트)하지 않는다.
- 개정 폭이 서프라이즈 크기와 비슷하면(사전 고정 문턱: 개정 절대값 중앙값 ≥ 월 변화 절대값 중앙값의 50%) 과거 수익 검정 설계를 멈추고 전향 전용으로 돌린다.

**PR 경계**: 프로브 스크립트 1개, probes.yml 옵션 추가, 결과 JSON, 문서. 수집기·정기 워크플로는 만들지 않는다.

---

## 작업 D — 전향 기록 기반 구축(코드만, 실행은 승인 후)

**설계**: `research/next_alpha_program_v1/PROSPECTIVE-DESIGN-ko.md`

**할 일**

1. **사양**: `research_specs/industry-watch-v1.json`. 원천 목록, 필드, 주기, 해시 규칙을 정의하고 sha256 사이드카를 둔다.
2. **수집기**: `scripts/collect_industry_watch.py`
   - 원본 응답 바이트를 그대로 저장하고 sha256을 기록한다.
   - 같은 기간 재수집 시 `revisionOf`를 연결한다.
   - append-only로 기록하고, 키 충돌 시 배치 전체를 거부한다(v2.22 sealing 규칙과 같다).
   - 성공 여부는 `pipeline.collector_outcomes.run_outcome`으로 분류한다. 거부로 0행이면 비영(非零) 종료 코드다.
3. **R2 산업 BOOM 목록 기록기**
   - `research/investment_decision_alpha_v1/s1_industry_cycle.py`의 `states()`를 **임포트해** 같은 정의를 쓴다. 재구현은 금지한다.
   - 판단일의 BOOM·CUT 목록과 지표값을 기록한다.
4. **워크플로**: `.github/workflows/industry-watch.yml`, `workflow_dispatch` 전용. 정기 실행(cron)은 넣지 않는다.

**테스트**
- 같은 입력 두 번 실행 시 바이트가 동일하다.
- 키 충돌 거부.
- 개정 연결.
- 거부 응답 시 비영 종료.
- 출력에 비중·추천 필드가 사양 없이 생기지 않는다.

**검증 기준**: 합성 응답으로 전체 경로가 돈다. 실제 원천 호출은 하지 않는다.

**중단 조건**: 작업 C에서 `SERVED`가 아닌 원천은 수집 목록에 넣지 않는다.

**PR 경계**: 사양, 수집기, 기록기, 워크플로 1개, 테스트. `signal-history`에 대한 첫 쓰기는 사용자 승인 후 별도 실행으로 한다.
