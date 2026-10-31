# Stock A 원본 원천 복구 — 2026-10-26 KST

실측 증가량은 **0**이다. ZIP 0/68, ZIP 내부 원 공시 신원 검증 0/68,
WC2/WC1 두 연차 원 재무 수치 검증 및 연구 적격 관측은 각각 **0/51,360 (0%)**다.
원본 listing/main의 접수번호·기업·기재 결산월 metadata는 68/68 확인했다.
이는 ZIP의 신원·수치 검증과 다르다. 원천 부재로 판정한 건수도 0이다.

## 실제 접근 상태와 필요한 사용자 조작

main `0877ef2d125764a7f71e0dc0d5ccac0008653b0d`, #286의 작업 시작 HEAD
`69cb205ca27ff270ba9b7386dc3aa4b9ac8b124a`다. #292 최신 지시
[6403313893](https://github.com/jaehojung1879-netizen/Investment/issues/292#issuecomment-6403313893)를 확인했다.

저장된 Investment 환경 초안 revision 1에는 `dart.fss.or.kr`, `opendart.fss.or.kr`이 있다.
그러나 현재 runtime revision 1의 custom 허용 목록은 비어 있고, policy state는 `unknown`이다.
현재 환경에 적용됐다는 증거가 없다. 도구에 전체 Publish 이력이 노출되지 않으므로 다른 환경까지
미발행이라고 단정하지 않는다. `environment-evidence.json`에 정확한 draft/base/version을 남겼다.
이전 공식 접속 시험은 `curl: (56) CONNECT tunnel failed, response 403`이었다.
정책 변화가 없으므로 같은 접속을 반복하지 않았다. 이번 target HTTP 요청은 **0회**, 68건 모두
`NOT_ATTEMPTED_ENVIRONMENT_NETWORK_BLOCKED`다. 68회 다운로드 실패가 아니다.

필요한 UI 조작은 다음과 같다. 저장소나 #293 화면의 Publish가 아니다.

1. 제품에서 **Investment 클라우드 환경 설정**을 연다.
2. 네트워크의 사용자 허용 도메인에 `dart.fss.or.kr`, `opendart.fss.or.kr`이 있는지 확인한다.
   hostname만 입력하며 기존 package-manager preset은 보존한다. 이 공개 경로에는 API Secret이 필요 없다.
3. 초안을 검토·저장한 뒤 환경을 **Publish**한다. 재연결/갱신 후 해당 작업의 실제 접속을 다시 확인한다.
   저장 또는 Publish 버튼 완료만으로 현재 task에 적용됐다고 간주하지 않는다.

이는 cloud-environment-onboarding setup의 “Saving persists configuration; it does not execute
scripts, apply runtime changes, or publish.” 계약 때문이다. 이번에는 이미 저장된 초안을 변경하지 않았다.

## 워크플로를 건드리지 않는 독립 수집 경로

`portable_collection.py`와 `xbrl_recovery_v2/portable-plan.json.gz`를 추가했다. 계획은 고정된 68개
접수번호·문서번호·main 원 바이트 및 SHA, 수집 코드 SHA를 포함한다. **원 XBRL ZIP은 포함하지 않는다.**
원본 metadata를 다시 검증한 환경에서 export하고, 수신 환경은 같은 코드와 이 파일만으로 실행할 수 있다.
수집 시 과거 Git 객체를 요구하지 않는다. 합성 회귀 검증에서 Git 호출을 금지한 채 실행했으며,
다른 receipt/issuer/FY/공개일/main/코드 hash와 중복·권한 플래그 변조는 네트워크 요청 전에 거부했다.

소유자가 DART에 정상 접속할 수 있는 본인 PC 등 **독립적으로 허용된 환경**에서 같은 #286 HEAD를
사용할 수 있다. 이 클라우드의 통제를 중계·터널·proxy 변경으로 우회하는 경로가 아니다.
아래 경로의 실제 외부 HTTP 성공은 아직 검증하지 못했다. 합성 정상 수집과 실제 접근 차단은 구분한다.

```bash
python -m research.stock_working_capital_v1.portable_collection --verify-plan research/stock_working_capital_v1/xbrl_recovery_v2/portable-plan.json.gz
python -m research.stock_working_capital_v1.portable_collection --collect-plan research/stock_working_capital_v1/xbrl_recovery_v2/portable-plan.json.gz --output /path/to/new-wc-acquisition
```

새 디렉터리에 순차 수집하고 원 main→공식 다운로드 창→동일 문서/receipt ZIP의 SHA 연결을 보존한다.
기존 수집기와 TLS·proxy 설정을 사용한다. 전송 오류 후 나머지는 중단하며, 원천 부재로 바꾸지 않는다.
기본적으로 성공 시 요청은 각 receipt의 창+ZIP 두 번, 총 136번이다. 재시도 폭주나 다른 공시 대체는 없다.
완료 후 원 디렉터리를 로컬 근거로 보존하고, 무단 raw 배포 없이 검증 환경에 전달해야 한다.
획득은 `ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP`일 뿐 financial admission이 아니다.

기존 `signal-history` `9d89baaa710453e20bcf918e86e42d85430e4eb6`의 original-XBRL 저장소도 직접 검사했다.
FY2015 Q1/H1/Q3 각각 175건, 합계 **525건**이며 이번 접수번호 교집합은 **0/68**이다.
같은 종목의 오래된 분기 추출 수치나 ZIP digest를 이번 연차 원본으로 대체하지 않았다.
이 검사는 해당 저장소의 조사이며 외부의 모든 원본 저장소가 없다는 주장은 아니다.

## 고정 분모와 미검증 원인

현재 코드에 대한 `pit_measurement_v2` 영수증 검증 후 원천 진단을 다시 계산했다.
각 신호의 분모 51,360행, 종결·결측 행과 원래 진단 순서를 보존했다. 새 보고서는
`xbrl_recovery_v2/source-quality-v2.json`, 기존 보고서는 그대로다.

| 첫 미충족 조건 | WC2 | WC1 |
|---|---:|---:|
| snapshot·신호일 종결·bar 문제 | 518 | 518 |
| raw 연차 입력 결측/비교 불가 | 19,870 | 41,270 |
| 원 receipt/main 쌍 미일치 | 19,419 | 4,935 |
| dated 기업 신원/명칭 미해결 | 1,654 | 504 |
| dated 산업의 기업 신원 미해결 | 7,733 | 3,445 |
| 나머지 조건 통과, 우선 원본 ZIP 미확보 | 2,166 | 688 |
| 전체 | **51,360** | **51,360** |

순서는 결측 진단용이며 탈락시켜 분모를 줄이는 규칙이 아니다. 원본 확보 후에도 CFS/OFS,
issuer, KRW/단위, 정확한 계정·수치, 두 연차 fiscal context/인접성, original/amendment vintage를
통과해야 한다. 2019 taxonomy는 여전히 **UNRESOLVED**이며 `ifrs_`→`ifrs-full_` 치환을 하지 않았다.
F1 날짜별 캐시는 69cb205 수정 상태를 보존하고 날짜 음성 테스트를 다시 실행했다.

## F2: 단순 90일도 지금 확정하면 안 되는 실제 이유

고정 68건의 공개일과 **기재 결산월 말일을 가정한 진단**의 간격은 66–92일이다.
13건은 90일을 초과한다. 7건은 2018-04-02(단순 90일째 2018-03-31 토요일),
6건은 2019-04-01(2019-03-31 일요일)이다. `fiscal-age-evidence-v1.json`에 원 receipt별로 남겼다.
이것은 법정 휴일 예외와 일치하는 정황이지, 법정 기한·실제 fiscal end를 인증한 것이 아니다.

공식 FSS guide `https://dart.fss.or.kr/introduction/content2.do`는 같은 host 차단으로 원문을
이번에 취득하지 못했다. 과거 적용 자본시장법 159조, 휴일/공휴일 기한 처리, issuer별 연장 및
해당 COVID 조치, 결산기 변경·단기 회계연도의 공식 증거 검토는 **미완료**다.
따라서 법적 예외 검토를 마쳤거나 등록 준비가 끝났다고 주장하지 않는다.

| 사전등록 후보 | 성과와 무관한 근거/필요 조건 |
|---|---|
| 차기 연차보고서의 적용 제출기한 | 연간 공시 주기. 실제 fiscal 창과 과거 법령·휴일·개별 연장을 먼저 증명해야 함 |
| 기존 고정 550일 | 구현의 진단 경계 재현. 추가 유예의 과학적 정당성은 미확립 |
| 고정 365일 | 보수적 연간 경계. 정상 연말~공시 공백도 막으며 윤년 영향이 있음 |

기존 정책 JSON, 550 reference와 `selectedPolicy=null`은 변경하지 않았다. 소유자/비저자 검토로
정확한 규칙과 예외를 결과 열람 전에 고정해야 한다. 법정 기한은 실제 공시 가용일의 대체값이 아니다.
정책이 미등록인 동안 실제 입력 admission은 계속 차단한다. 원본 수집은 정책 결정을 기다릴 필요가 없다.

## CI·독립 감사 인계

#286 시작 HEAD 69cb205의 [40189159045](https://github.com/jaehojung1879-netizen/Investment/actions/runs/40189159045)는 SUCCESS다.
#293 `ca0be4b83dc8523132e1355ca151087ef295e33b`의 [40196789845](https://github.com/jaehojung1879-netizen/Investment/actions/runs/40196789845)는 FAILURE다.
#293의 workflow/핀/봉인 테스트 6개는 변경하지 않았다. 새 경로는 기존 workflow와 census를 수정하지 않는다.
같은 6개 guard를 **#286 변경본에서** 실행해 모두 통과했다. #293 실패를 고친 것으로 주장하지 않는다.

재현은 `python -m pytest -q research/stock_working_capital_v1`과 `pit_join --verify .../pit_measurement_v2`다.
합성/원천 영수증 검사만 수행했다. 전체 local suite는 봉인 실데이터 재계산을 포함하므로 실행하지 않았다.
새 commit의 전체 GitHub CI는 push 이후 그 SHA의 결과로 별도 확인해야 한다. 이전 녹색을 재사용하지 않는다.
검증/해시 목록은 `xbrl_recovery_v2/validation-v2.json`에 남긴다.

**NON-AUTHOR REVIEW REQUEST → Claude:** 이 PR의 새 exact HEAD에서 전달용 계획의 고정68 identity,
코드/main 변조 거부, Git 객체 없는 수집 경계, 원 ZIP/metadata/원 수치의 구분, 고정51360 분모,
F2 13건의 휴일 경계 진단 및 미등록 차단, 봉인 원천·결과·워크플로 불변을 독립 감사해 달라.
이 구현자의 테스트는 AUTHOR_VALIDATION_ONLY이며 독립 승인·병합 승인이 아니다.

다음 실행 가능한 작업은 허용 환경에서 68개 원본을 수집하고 수치/빈티지를 검증하는 **입력 전용 작업**이다.
지금 신규 역사 수익률 실험은 실행할 수 없다. 68건은 14 issuer의 복구 목록이며 모집단 또는
훈련 최소 표본을 낮추는 근거가 아니다. 미래 수익률, 기존 봉인 연구, production은 읽거나 실행·변경하지 않았다.
