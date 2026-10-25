# 실행에 필요한 명시적 승인 조건

이번 Draft 작성·기존 결과 읽기·메타데이터 감사·합성 테스트는 요청 범위에서
수행했다. 아래는 **나중에 필요한 조건**이며 지금 소유자에게 실행 승인을 요청하거나
승인 파일/잠금/실행기를 만들지 않는다. Draft PR 병합도 결과 실행 허가가 아니다.

## 단계별 허용 범위

| 단계 | 허용/금지 | 출구 조건 |
| --- | --- | --- |
| 현재 DESIGN | 기존 문서·봉인 SHA·분류 메타데이터 읽기, 합성 계약 | 신규 라벨/fit/역사 수익률 0, 기존 파일 불변 |
| DATA_ONLY 후속 | 별도 고정 source inventory와 합법 접근/재사용 권한 아래 identity·분류·기업행동 복구/coverage | 경제적 결과 접근 없음, 원천·빈티지·등급·full 분모 감사, 유료 구독 없음 |
| 새 역사 결과 | 별도 Study ID + immutable 사전등록 + 독립 감사 + 소유자 exact-hash 명시 승인 뒤에만 가능 | 아래 모든 조건 필요, 기존 산업 실험 절대 재실행 금지 |
| PROSPECTIVE | 별도 미래 기록 권한·코드·no-backdating 창으로 신호를 미리 봉인 | 미래 maturity 뒤 결과 연결, 역사 개발과 분리 |
| PRODUCTION | 이 설계의 권한 밖 | 별도 검증·승인 필요 |

## 결과 실행 전 체크리스트(현재 전부 미승인)

- [ ] Study ID를 확정한다. 예약명 `industry-alpha-kr-next-v1`,
  `industry-alpha-us-next-v1`은 아직 active study가 아니다. 단일 실행 범위와
  H1/H2/H3 중 허용 단계를 manifest에 명시한다. 단계 추가는 별도 승인이다.
- [ ] **KR 역사 종료 예외의 명시적 승인**: #217/Atlas 종료를 유지하면서 새 질문에
  한정된 새 개발 예산을 허용한다는 소유자 결정을 별도 기록한다. “독립 축 복원”이라는
  이번 설계 요청을 역사 수익률 실행 허가로 해석하지 않는다. 예외가 없으면 전향만 준비한다.
- [ ] 기존 봉인 산업/within-industry/Atlas와의 질문·정보·모집단 중복표를 감사하고
  동일 marginal 관계의 재측정·실패 모델 구제를 범위에서 제거한다.
- [ ] KR/US별 PIT taxonomy/level·증권/issuer/class identity, UNKNOWN/재구성 비중,
  종료/배당/총수익·benchmark·유동성·원천 권리가 적격하다. 미달을 survivors로
  통과시키지 않는다. classified-only exploratory scope가 필요하면 축소된 estimand와
  생존/분류 조건부 한계를 별도 등록·승인한다. strict 검정과 동일 결과로 부르지 않는다.
- [ ] 정확한 역사 날짜·신호/실행/비중첩 원점·기간·cutoff·36 슬롯·특징·ridge·
  transformations·OOF·inference·비용·정책·대체benchmark·실행 상한을 동결한다.
- [ ] 가격·공시·분류·기업행동·소스 raw SHA, selected snapshot과 original lineage,
  code/dependency closure, runtime/seed, output schema, 저장/회수 경로를 해시로 묶는다.
- [ ] 작성자와 별개인 독립 감사가 source/PIT/샘플/누설/통계/비용/합성/lock 계약을
  검토한다. named reviewer·정확한 commit/spec/inputs hash·미해결 지적·감사 evidence
  URL을 남긴다. 자기 점검이나 합성 pass를 독립 감사로 표시하지 않는다.
- [ ] owner가 exact 실행 묶음에 대해 별도 commit/서명 기록으로
  `APPROVE INDUSTRY_ALPHA_EXECUTION <studyId> <executionManifestSha256>`를 명시한다.
  이 문자열은 **제안된 승인 형식**이며 아직 어떤 코드도 인식하지 않는다.
  승인 artifact는 actual owner 신원/시각/commit와 묶고 agent가 생성하지 않는다.
- [ ] main 병합·동일 head CI·해시·no-prior-result/marker/lock·권한·자원/영속화
  확인 후, 구현된 별도 실행기가 첫 outcome 전에 atomic one-shot lock을 취한다.
  post-lock 실패는 소비이며 수정 후 재시도 금지; 기존 결과의 정확한 바이트 회수만 허용한다.

무료 원천이 막히면 BLOCKED와 원천 오류를 보고한다. 유료 서비스 구매, secret 추가,
차단 우회, 연구 표본의 조용한 축소를 대안으로 삼지 않는다. 실제 새 실행기는 이 PR에 없다.

승인 뒤에도 모든 역사 성과는 `EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_HISTORY`다.
양의 개발 결과·정확한 재현·H1 통과가 production이나 독립 미래 확증을 자동 허용하지 않는다.
#286·#287의 실행 manifest, 진행·중단 여부, 모델 판정과 승인은 본 연구의 권한 밖이다.
