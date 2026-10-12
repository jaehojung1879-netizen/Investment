# US 전체 관측 구성종목 실소스 dry-run v1

**PASS — 한 세션의 전체 관측 목록 수집은 기술적으로 가능했다.**
시작 main: `8639f8d7d2133769e23bb33736efc4c425873e38` (#231·#232·#233 포함).
실제 GitHub-hosted ubuntu-latest runner의 원본 실행 커밋은
`394f0830936a3b88abe4375fd91d9694ea13a86f`다.

[실측 실행 38228554292](https://github.com/jaehojung1879-netizen/Investment/actions/runs/38228554292),
[원본 staging artifact 11737957109](https://github.com/jaehojung1879-netizen/Investment/actions/runs/38228554292/artifacts/11737957109).
상세 관측값·소스 ID·원본 커밋 파일 해시는
[실소스 증거 JSON](us-readiness/us-full-universe-real-dry-run-actions-evidence-v1.json)에 보존했다.

| 항목 | 실제 관측 |
|---|---:|
| 최근 완료 XNYS 세션 | 2026-10-09 |
| 관측 구성 증권 / 발행사 CIK | 503 / 500 |
| ETF 포함 예상 / 유효 수집 | 505 / 505 |
| 구성종목 유효 수집 | 503 |
| SPY / QQQ | 각각 VALID |
| 전체 수집 완전성 | 100% |
| 가격 어댑터 호출 / 실제 curl HTTP 요청 | 505 / 1,012 |
| 구성 소스 HTTP 요청 | 별도 2 |
| 수집·검증 경과 시간 | 505.492초 |
| 비영(非零) 배당 / 비항등 분할 | 9 / 0 |
| 필수 액션 열 검증 | 505건 |
| 최종 실패 / 누락 / 미해결 액션 거부 | 0 / 0 / 0 |
| HTTP 상태 | 200: 1,011회; 404: 1회 |
| 비표준 공유 클래스 기호 | BF.B→BF-B, BRK.B→BRK-B 모두 VALID |

수집 시간은 구성 CSV 획득 이후부터다. source step 전체는 09:14:42–09:23:09 UTC다.
실제 404는 비종결 요청 1회이며 요청 엔드포인트를 기록하지 않아 정확한 원인은
미확정이다. 특정 쿠키 요청이었다고 추정하지 않는다. 가격 거부·429는 없었으며
505건이 기존 OHLCV/USD/NYSE 세션/가격·액션·기호 계약을 통과했다.
공급자를 전환하거나 프록시·TLS 제한을 우회하지 않았다.

원본 구성은 기존 어댑터가 관측한 datasets/s-and-p-500-companies 커밋
`36472b57910842f4025e8ca8303b93a692d2bbae`의 전체 CSV다.
축소 샘플·수동 종목 목록·과거 구성 재구성은 사용하지 않았다.
원본 CSV SHA-256은 증거 JSON과 staging의 snapshot manifest에 보존되어 있다.

기존 수집기의 split-adjusted 원본에서 as-traded OHLCV/배당으로의 변환을
505건 검증했고, 동일 획득값 505건의 반복 저장은 파일 바이트를 변경하지 않았다.
소스 참조를 재검증했으며 최초 획득 이전 as-of 조회에는 가격이 없었다.
반복 검증에는 추가 공급자 요청이 없었다. 전체 수집기·Finnhub·H63·P4는 수정하지 않았다.

## 실행 범위와 최종 상태

최초 PR opened / 지정 branch / 동일 repo / attempt 1만 허용한 임시 Tests job이
실제로 실행되어 PASS 증거와 artifact를 보존했다. 이후 임시 job은 제거했으며
`tests.yml`과 기존 보호 테스트 세 파일은 시작 main의 정확한 바이트로 복원했다.
새 workflow는 없고 최종-head CI는 실소스 네트워크 테스트를 반복하지 않는다.
원본 실행 workflow 해시는 원본 Git 커밋에 대한 역사 증거이며 현재 workflow와
동일해야 한다는 주장이 아니다. #231의 원본 35건 증거는 변경하지 않았다.

최종 코드는 vendor의 일반 Exception 처리로 429 중단이 흡수되지 않도록
별도 중단 예외를 사용한다. curl 요청 상한 2,000도 추가했다. 이 보강은 합성
테스트로 검증했으며 원본 실측 실행과 구분한다. 실측을 두 번째 실행하지 않았다.

CLI: `python scripts/dry_run_us_full_universe.py --output /outside/checkout/fresh-stage`.
현재 관측 구성 전체와 SPY/QQQ, XNYS 종료 +60분 뒤 최근 세션 하루만 요청한다.
두 ETF가 유효해야 구성종목으로 진행한다. 가격 어댑터 호출 간격은 최소 1초,
상한 552회, 시간 예산 1,200초다. 기존 history 요청 timeout은 20초이고
vendor 내부 세션/쿠키 요청은 pinned adapter의 timeout을 따른다. 시간 예산은
요청 사이에 검사하므로 진행 중 요청의 timeout 및 마지막 저장 비용이 추가될 수 있다.
429는 다음 HTTP 요청이나 종목으로 진행하지 않고 중단한다. 성공 건은 즉시 저장해
예산·rate-limit 중단 시 부분 가격 및 기존 collector manifest를 보존한다.

출력은 checkout 밖 새 디렉터리만 허용한다. source-audit.json,
attempts.json, provider-http-attempts.json, evidence-hashes.json 및 기존 수집기의
불변 가격/구성/획득/manifest를 보존한다. archive SHA-256은 GitHub API 선언값이다.
작성 환경에서 archive를 다운로드·독립 재해시하지 않았으며 보고서 관측값은
원본 source job의 controlled notice를 표준 GitHub check-run annotations API로 읽었다.
원본 전체 manifest/runtime는 artifact에 있고, 저장된 notice projection만으로
전체 source-audit digest를 다시 계산할 수는 없다.

## 운영 판단과 최소 다음 단계

503개 증권의 한 세션 수집은 GitHub-hosted runner에서 기술적으로 가능했다.
반복 일일 운영의 안정성, 공급자 이용조건·서비스 보장, 장기 액션 전체성은
이번 한 번의 성공으로 입증되지 않았다. 구성 CSV는 보조 소스이며 공식 편입
유효일·역사적 PIT 구성·공식 전체성을 증명하지 않는다. CIK는 발행사 식별자이며
공유 클래스 영구 ID가 아니다. 0건 분할은 이 세션에 보고된 값이며 스핀오프,
특별 분배, 향후 정정이나 누락이 없다는 증명이 아니다.

최소 다음 단계는 owner가 공급자 이용조건과 보존 책임을 확인하고, 별도 승인한
수동 일일 staging 실행에서 완전성·429·액션 정정·구성 변경을 누적 점검하는 것이다.
이번 PR에는 이를 실행하는 영구 workflow나 일정·production 승격을 넣지 않았다.
기존 수집기의 불변 저장소에서 재개/정정 격리 정책을 운영해야 한다.
원본 artifact 보존 기한은 2027-01-10이므로 만료 전 승인된 보존 위치로 옮겨야 한다.

실험·수익률·모델·자동 일정·production signal-history 쓰기·게시 변경은 수행하지 않았다.
