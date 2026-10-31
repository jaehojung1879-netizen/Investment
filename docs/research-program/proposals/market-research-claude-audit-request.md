# Claude 독립 설계 감사 요청 — #289

대상은 **#289의 현재 정확한 HEAD**다. GitHub/`git rev-parse`로 SHA를 먼저 기록하고, 결과 열람·실행·
병합·APPROVE 없이 감사한다. 이 파일은 저자의 독립 감사 완료 주장이나 소유자의 실행 승인이 아니다.

1. 원 B/C 및 공유 의존성 94개가 `market-research-preserved-sha256.json`과 byte-identical인지 확인한다.
   `market_research_c1c` 외의 봉인 함수/파라미터/권한을 바꾸지 않았는지 확인한다. C1/KR 정식 실행기는 호출하지 않는다.
2. 2×2의 각 arm이 원 C1 지도에서 한 요소만 움직이는지, FAST=2의 복귀 veto, 주간 판단/다음 종가,
   당일 제외 20세션 창·중간 세션 누락·동일 종가 tie·결측 완성/hold·첫 목표 거부를 반례로 검토한다.
3. 알려진 시각/장중 FAST 거부/4일 lag·14일 staleness/미래 macro 및 가격 poison/휴장·조기 폐장·
   gap-down·gap-up을 검토한다. `sealed_states`가 새 PIT vintage를 인증하지 않는다는 한계를 확인한다.
4. US 가격지수/zero-cash 복제와 SPY/DTB3 경제성을 혼합하지 않는지, KR 봉인 비용과 ETF 면세 비용을
   별도로 표시하는지, 초기·최종 비용·현금의 직전 알려진 금리/경과 일수·no-leverage·cash gap을 확인한다.
5. S0 대비 세 대비만 주 가족인지, 사후 평균 노출/공분산을 거래 가능한 타이밍 알파로 부르지 않는지,
   STATIC_40/70·전체 1/2/3배 비용·censoring·false-alarm/whipsaw/pending을 모두 보고하는지 확인한다.
6. B의 원 상태/신호 효과와 C의 노출 효과가 독립이고 B-H2 p=1 차단이 유지되는지, Industry/Stock
   연구를 C의 성공으로 가로막지 않는지, 시장 배수 인터페이스가 중복 적용/생산 연결을 거부하는지 확인한다.
7. 기존 노출 역사를 EXPLORATORY로 유지하며, `verify/synthetic`만 있고 역사 입력·execute·승인/lock
   작성 경로가 없는지 확인한다. 미래 실제 실행의 숫자·권리·기간·공통 표본·manifest/owner 승인 관문을 검토한다.

최소 재현:

```bash
python scripts/check_market_research.py verify
python -m pytest -q tests/test_market_research_c1c.py tests/test_rp1_b_h1_state.py
python scripts/check_market_research.py synthetic --market US
python scripts/check_market_research.py synthetic --market KR
```

최신 HEAD의 CI와 합성 결과만 검토한다. 기존 실자료 KR equivalence 테스트나 C1 execute를 실행하지 않는다.
지적은 정확한 HEAD, 최소 합성 반례, 위험, 최소 수정으로 남긴다. 독립 감사 전 `DESIGN_VERIFIED`를
`EMPIRICALLY_SUPPORTED`·`READY_TO_EXECUTE`·`OWNER_APPROVED`로 바꾸지 않는다.
