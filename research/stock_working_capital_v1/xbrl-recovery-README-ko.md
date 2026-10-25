# 원본 XBRL 수집·원천 검증 v1 — 실제 증가량 0

**원본 확보 0/68건, 두 연차 원 재무 수치 검증 0/51,360행(0%), 증가 0행이다.**
원본이 없다는 판정이 아니다. 현재 클라우드의 DART 호스트 연결 시험이
`curl: (56) CONNECT tunnel failed, response 403`으로 거부됐다. 실행 환경의 실제 허용 목록에는
`dart.fss.or.kr`이 없다. 따라서 target별 HTTP 요청은 **0회**, 68건은
`NOT_ATTEMPTED_ENVIRONMENT_NETWORK_BLOCKED`다. 68번 실패했거나 DART가 68건의 부재를 확인했다고 쓰지 않는다.

최신 main `0877ef2d125764a7f71e0dc0d5ccac0008653b0d`, #286 `8df7f796…`, #292의 최신 지시와 Claude F1/F2를 확인했다.
같은 #286 브랜치에서만 작업했다. 기존 `pit_measurement_v1`은 덮어쓰지 않고,
수정 코드 영수증을 `pit_measurement_v2`에 재생성했다. 기존 한국 결과 50개, C1, 봉인 원천·실행기·잠금은 보존했다.

## 수집 경로와 실제 원천 범위

보존된 **원래 main 페이지가 직접 제공하는** `openPdfDownload(receipt,document)`를 읽어
공개 다운로드 창 → 그 창의 IFRS/XBRL ZIP 링크를 선택하는 경로를 구현했다.
새 API key가 필요 없는 공개 경로이며 인증·네트워크 정책을 우회하지 않는다. 다른 공시/기업/문서 번호,
HTTP·외부 호스트·임의 javascript·모호한 첨부 선택은 거부한다. 원 main·다운로드 창·ZIP의 SHA와 경로를 연결한다.
API key 부재는 현재 OpenDART API 경로의 한계이지만 **이 공개 경로의 필수 조건은 아니다.**

68개 접수번호의 원문 metadata·기업 신원·문서 번호 registry는 모두 기존 원천에서 검증했다.
대상은 **14 issuer, FY2016 9건 / 2017 10 / 2018 9 / 2019 10 / 2020 12 / 2021 10 / 2022 8건**이다.
이는 원 XBRL의 수치 검증 건수와 다르다. 늦은 수정본 숫자를 최초 공개일로 옮기지 않는다.
수집에 성공해도 상태는 `ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP`이며, 원래 receipt/document의
issuer·금액·단위·CFS/OFS·fiscal context를 다시 통과해야 한다.

`xbrl_recovery_v1/manifest.json`은 미시도 상태와 고정 registry다.
`source-quality-v1.json`은 전체 분모의 수치 검증률과 사유를 재계산한 결과다.
원본 숫자·빈티지·결산 창이 검증되지 않았으므로 실제 연구 적격 관측은 WC2/WC1 모두 **0**이다.

## 미검증 사유의 정량 분해

아래는 **고정된 진단 순서의 첫 미충족 조건**이며 합계가 각각 51,360이다. 종목을 제거하는 규칙이 아니다.
기존 비배타 사유별 수량도 coverage에 모두 남아 있다. 첫 조건을 바꾸어 표본을 유리하게 만드는 작업은 하지 않았다.

| 첫 미충족 조건 | WC2 재고 | WC1 매출채권 |
|---|---:|---:|
| 월간 모집단 스냅샷 차단 | 360 | 360 |
| 신호일 이전 종결 | 13 | 13 |
| 신호 bar 결측·비거래 | 145 | 145 |
| raw 연차 입력 결측·비교 불가 | 19,870 | 41,270 |
| 원 접수번호·main 쌍 미일치 | 19,419 | 4,935 |
| dated issuer·명칭 미해결 | 1,654 | 504 |
| dated 산업 issuer 미해결 | 7,733 | 3,445 |
| 나머지 조건을 통과했으나 우선 원본 패키지 미확보 | 2,166 | 688 |
| **전체** | **51,360** | **51,360** |

모든 51,360행, 종결 목록 관련 1,725행, 스냅샷·결측·거래량 0인 행을 보존했다.
월간 최신 공개 Top120 재구성은 당일 시장 전체의 정확한 일별 순위라고 부르지 않는다.

## 2019 IFRS 분류

원본 ZIP을 못 읽었으므로 **UNRESOLVED**다. API의 `ifrs_`→`ifrs-full_` 접두어 변경을
경제적 동등성으로 자동 치환하지 않았다. 원래 source gate가 표시한 비배타 수량은
WC2 inventory 계정 변경 **3,886행**, sales 변경 **3,668행**이다. 주된 영향은 FY2019 보고서가
공개된 **2020 신호일**의 inventory 2,887 / sales 2,843행에 나타난다. 두 사유는 중복될 수 있다.
원 XBRL의 QName·taxonomy URI·statement/context·숫자·원 receipt 증거가 마련되기 전에는
접두어를 바꿔 커버리지나 연구 결과를 완성하지 않는다.

## Claude F1/F2

**F1 FIXED, 합성 반례 재현:** 이전8df 코드에서 3/21·4/4를 요청하면 cached `asOf`는 3/21 하나였다.
현재 pair 및 metadata 캐시 키는 신호일을 포함한다. 두 `asOf`가 각각 남고, 출력 `pairAsOf`도 해당 신호일과 같다.
날짜에 따라 달라지는 음성 gate를 주입한 테스트에서도 뒤 날짜가 앞 날짜 결과를 재사용하지 않는다.
영수증 검증은 `pairAsOf != signal`을 거부한다. 현재 실제 feature 숫자가 바뀐 것으로 주장하지 않는다.

**F2 OWNER DECISION PENDING:** 550일은 기존 구현의 진단용 상수였으며 등록·승인된 연구 cutoff가 아니었다.
이를 `fiscal-age-decision-v1.json`에 명시하고 미등록 상태에서는 실제 입력 admission을 차단했다.
원 숫자 검증률은 이 정책 gate와 별도로 보고한다. 과거 v1 영수증은 보존하고 현재 코드 해시로 v2를 만들었다.

| 선택안 | 성과와 무관한 근거 | 한계 |
|---|---|---|
| **차기 연차보고서 제출기한 — 권고** | 검증된 fiscal end에서 한 회계연도 후 해당 법정 제출기한까지. 추가 재량 유예 없이, 차기 공시 부재로 설명 | 역사적 법정 90일 규칙·연장 예외 적용을 원문 법령으로 확인해야 함. 이 환경에서는 법령 원문 미취득 |
| 기존 고정 550일 | 기존 소프트웨어 경계 재현, 약 18개월 | 추가 약6개월의 과학적 근거가 확립된 것은 아님. 차기 공시가 늦어져도 오래 유지할 수 있음 |
| 고정 365일 | 보수적인 단순 연간 경계 | 차기 공시 전 정상적인 연말~공시 공백도 차단하며 윤년 영향이 있음 |

소유자·비저자 검토로 **결과 열람 전에** 하나와 예외 처리, 적용 fiscal 기간, 명세/코드 hash를 고정해야 한다.
공개일만 새롭고 fiscal period가 오래된 보고서를 fresh로 바꾸지 않는다. 현재 `selectedPolicy=null`이며,
성과·모델 적합·CAGR를 이용해 선택하지 않았다. 원천 수집은 이 선택을 기다릴 필요가 없다.

## 재현과 다음 실행

```bash
python -m pytest -q research/stock_working_capital_v1
python -m research.stock_working_capital_v1.xbrl_recovery               # PLAN_ONLY
python -m research.stock_working_capital_v1.xbrl_recovery --collect --output /tmp/wc-originals-new
python -m research.stock_working_capital_v1.pit_join --inspect --packages /tmp/wc-originals-new --output /tmp/wc-measurement-new
python -m research.stock_working_capital_v1.pit_join --verify research/stock_working_capital_v1/pit_measurement_v2
```

수집 실패 뒤에는 기존 디렉터리를 덮어쓰지 않는다. 네트워크/전송 거부는 나머지 요청을 중단하고 상태를 보존한다.
기본 CLI·합성 테스트는 외부 호출을 하지 않는다. 기존 연구의 정식 실행·봉인 결과 재계산은 하지 않았다.

현재 바로 가능한 것은 코드·합성·입력 무결성 검사뿐이며 **신규 역사 수익률 실험은 0개 가능**하다.
환경 설정에 DART 두 도메인 허용 초안을 저장했으나 도구가 `requires_publish=true`를 반환했고 런타임에는 미적용이다.
검토·저장·Publish 후 실제 연결을 확인하면, 새 key 없이 위68개 공개 첨부 수집과 수치 검증을 재개할 수 있다.
68개는 14종목의 원천 복구 목록이지 완성된 투자 모집단이 아니다. 기존 최소30종목 비교나50 issuer 훈련 기준을
낮추지 않으며, 더 넓은 원천·산업·기업행동·총수익과 독립 사전 감사/정확 실행 승인이 있어야 역사 검정으로 넘어간다.
