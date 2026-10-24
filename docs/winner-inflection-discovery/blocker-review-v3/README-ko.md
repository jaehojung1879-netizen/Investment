# #287 원천 결함 수정과 미해결 admission

기준 HEAD `fb60528dd7b28b0d574f9bf8a2040e62615f160e`. 기본 명세·7개 미해결 review 및 별도 v2 review는
보존했다. `metadata.json`은 원래 고정된 Git 원천의 **가격 외 metadata만** 직접 조사한 새 증거다.
가격 패널·실제 미래 수익 라벨·모델·정식 WID 실행을 열지 않았다.

| 항목 | 이번에 실제 확인한 것 | 상태 |
|---|---|---|
| rights | vendor/recipe lineage는 보존·재사용 허가서가 아님. 조사한 기존 metadata에 이 사용 범위의 affirmative grant가 없음. 공개 접근·Git 보유·코드 라이선스·Tiingo 무료 대체는 허가 근거가 아님 | **BLOCKED** |
| identity | 후보 category 593개는 issuer CIK 검사를 할 수 있으나 quote의 issuer/share class 증거와 다름. 결측/0/잘못된 CIK가 동일 신원으로 일치하는 합성 반례를 수정. 원천의 AOS 16자리 CIK(2023-08-03)는 별도로 기록하되 이 2020 실험의 실제 편입 결함이라고 주장하지 않음 | **BLOCKED** |
| returnBasis | 고정 기간의 127개 월별 action component에 SPY 이벤트 **0건**. 기존 역산은 빈 action 목록에서 총수익 지수를 그대로 반환하므로 이를 원종가로 인증할 수 없음. loader에 명시적 거부 추가 | **BLOCKED** |

SPY 배당 한 건을 넣는 것은 완전한 복구가 아니다. 원종가·배당 currency/share units·분할·배당 누락을
독립 근거로 대조해야 한다. 총수익 지수에서 누락 배당을 역으로 추정하거나, SPY를 price-only로 바꾸거나,
주식과 ETF에 서로 다른 기준을 쓰지 않는다. 다른 원천을 쓰려면 별도 명세·권리·승인이 필요하다.
이번 수정은 실험을 실행 가능하다고 표시하는 대신, 잘못된 기준으로 실행되는 경로를 실제로 막는다.

신원 음성 검사는 모든 CIK가 `None`일 때 종목 행을 보존하면서 `UNRESOLVED`/비적격으로 처리한다.
원래 자료의 visible filing CIK는 모두 정상 형식이므로 실제 과거 종목 수익 결과가 바뀌었다고 주장하지 않는다.
CIK 일치는 발행사 수준 보조 증거이며 가격 파일의 증권 신원 증명이 아니다.

```bash
python scripts/inspect_wid_blockers.py                    # PLAN_ONLY, 원천 미열람
python scripts/inspect_wid_blockers.py --inspect          # 고정 action/identity/lineage metadata만
python scripts/run_winner_inflection.py preview --review docs/winner-inflection-discovery/admission-review-v2/review.json
python -m pytest -q tests/test_winner_inflection_source_review.py tests/test_winner_inflection_local_git.py tests/test_winner_inflection_execution.py tests/test_winner_inflection.py tests/test_experiment_workbench.py
```

v2 보고서의 code hash는 그 당시 코드에 대한 역사 증거다. 이번 코드에는 그 실행 request/승인을 재사용할 수 없다.
네 조건부 기술 검토가 실제 법적 권리·증권 신원·총수익 인증으로 확대되지 않는다. 남은 세 항목을 입증하고
새 exact-HEAD manifest를 검토한 소유자의 `APPROVE WID_EXECUTION <request.sha256>`가 있어야 한 번의 실행을 시작할 수 있다.
현재 **NOT APPROVED FOR EXECUTION**이며 시도 태그·승인 댓글을 만들지 않았다.

다음 경제 가설은 기존 고정 US B/H126/2020의 영업이익 양전환과 현금흐름 마진 개선이다. KR 장중 가설의
사후 구제가 아니다. 기준선 대비 증가분, 같은 날짜/산업/규모 통제, 큰 손실 구분, 공통 유효 표본 및
최대 5종목 비용 후 SPY 순경제성을 함께 본다. 파라미터/2020 검증 구간을 결과에 맞춰 변경하지 않는다.
이미 노출된 역사에 대한 EXPLORATORY 연구이며 12개월 확장·새 표본은 별도 사전 명세/승인 대상이다.

`regression-evidence.json`의 전/후 합성 대조에서는 결측 CIK 314행의 잘못된 적격 판정이 **314→0**으로
감소하고 분모 314행을 그대로 보존한다. 관련 테스트 **136개 통과**(SciPy deprecation warning 44개).
전체 pytest의 기존 봉인 실자료 재계산은 로컬에서 실행하지 않았다. Lint/compile 및 임시 경로의 합성
seed/validation을 확인한다. 독립 감사 최종 판정과 새 HEAD의 GitHub CI는 별도 게이트이며 성공을 추정하지 않는다.
