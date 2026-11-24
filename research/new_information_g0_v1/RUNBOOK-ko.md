# G0 실행·검증 가이드

## 보안·권한 경계
- 본 브랜치는 main, 보호된 GitHub Actions, 배포/전향 기록을 변경하지 않는다.
- OpenDART 키는 환경변수 DART_API_KEY에서만 읽는다. 프롬프트·Issue·PR·공개 로그에 키, 키 포함 URL을 게시하지 말 것.
- 오리지널 ZIP에 이름/연락처가 포함될 수 있으므로 문서 바이트, 실명, 원문 텍스트를 repository에 커밋하지 않는다. 필요한 경우 안전한 외부 비공개 증거 패킷에 보관한다.
- 대량 수집·유료 구매·시장 성과 계산·서버 스케줄 등록 없음.

## 검증 명령

```bash
python -m pytest -q tests/test_new_information_g0_v1.py tests/test_new_information_g0_iip.py
python -m ruff check research/new_information_g0_v1 tests/test_new_information_g0_v1.py tests/test_new_information_g0_iip.py
```

## 기존 원천 라이브러리와의 통합 필수 확인

- 기존 #320 정확 HEAD `9a47f478`에는 `research/corporate_event_readiness_v1/cohort/dart_client.py`가 이미 존재한다. 기존 운영 키 이름은 `DART_API_KEY`이다.
- #373 `source_probe.py`의 간단한 직접 HTTP 경로는 **단일 한도 확인용 격리 진단**이며 #320의 SHA 기반 원문 캐시, status 014 처리, 재시도/원천 권리 계보를 대체하지 않는다.
- 본 소표본의 실제 원천 admission을 확장하기 전에 #320의 검증된 `DartClient` 및 raw response cache를 **그대로 재사용하는 어댑터 방식으로 통합할 것**. 새로운 상용 수집기나 중복 캐시 체계로 발전시키지 말 것.
- #320은 아직 별도 Draft 브랜치이므로 #373 main 기반 PR에서 해당 모듈을 이미 import 가능하다고 전제하지 않는다. 저장소 레인 소유자가 integration 결정.
- #320의 `filing-samples.json` 13건은 자사주·계약 등 I형 공시 샘플이며 5% 목적 변경 검증 사례는 **0건**이다. #373이 원문 PIT 검증을 마쳤다는 주장을 금지.

## 1. DART 메타데이터/원문 원천 시험

```bash
# 키 값은 안전한 로컬 환경에서 export하거나 기존 Secret 주입 방식을 사용할 것.
# 첫 실행은 목록만: 5개 제도 구간 × 2 공시 유형 = 최대 10 HTTP 요청
python -m research.new_information_g0_v1.source_probe --live --output /tmp/g0-metadata-only.json

# 첫 실행 결과와 호출량을 확인한 뒤 허용된 작은 원문 샘플만.
# 최대 10개 추가 ZIP: 유형별 5개, 각 제도 구간에서 한 건씩 우선 추출
python -m research.new_information_g0_v1.source_probe --live --documents-per-detail 5 --output /tmp/g0-small-original-fingerprints.json

# 데이터가 없는/offline 환경의 파서 검사는 합성/fixture에서만.
python -m research.new_information_g0_v1.source_probe --offline-list /tmp/synthetic-dart-list.json
```

공개 리포트에는 응답 목록의 페이지가 미완료인 경우를 명시. 응답이 100건으로 잘리면 **모집단 건수라고 주장하지 않는다**. 원문에 보유목적 단어가 포함됐다는 것은 자동 판정이 아니며, 현재/직전 원문 비교와 신고인 연결이 필수다.

## 2. 반도체 실물 데이터 진단

```bash
# #360의 파일이 로컬에 있는 경우에만 실행. #360은 main 위에 이미 병합된 파일이 아닐 수 있음.
python -m research.new_information_g0_v1.iip_feasibility research/industry_alpha_discovery_v1/data/iip-industry-yoy.csv --out /tmp/g0-iip-audit.json
```

이 원장의 productionYoy, shipmentYoy, inventoryYoy는 전년동월비 지표이므로 재고/출하 **수준 비율의 분자·분모가 아니다**. N2의 실물가격·수준 레벨 빈티지 확보 없이 투자 신호 실증으로 진행하면 안 된다.

## 제출할 보고
- G0_SOURCE_AUDIT.json: 요청·총보고건·페이징·원본 SHA·원공시 공개일·원본문서 비교 가능성, 개인식별 정보는 제거.
- PARSER_CROSSCHECK.md: 최소 두 제도 구간 이상, 변화/비변화 공시의 수작업 대조. 지분증감과 목적변경을 분리.
- CANDIDATE_GATES.md: 3개 후보 신규성·수집 가능성·독립 사건 수·MDE(계산 불가면 NULL)·GO/STOP.
- 성공하더라도 G1 사전등록은 **후속 Owner 확인**, 수익·미래 NAV는 읽지 않는다.

## 프로젝트 상태
문서·코드·합성 테스트만 추가. 공식 원문 ZIP 실제 다운로드 0, 수익 실험 0. 이 자료가 강제하는 유일한 다음 행동은 원천 적격성 판정이다.
