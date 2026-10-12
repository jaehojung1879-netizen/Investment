# US 일일 시장가격 영속 수집 기반 v1

구현은 준비했으나 **실제 반복 수집 활성화는 차단 상태**다. 반복 취득·저장
이용권, owner 승인, 영속 저장소와 반복 운영 검증이 남았다. 이번 PR에서
시장 소스를 호출하거나 일정·production·signal-history를 활성화하지 않았다.

시작 main: `199898a9ec137629a78ab78a5925985c0261a7a3` (#234·#235 포함).
#235의 실제 GitHub-hosted 2026-10-09 세션 505/505 PASS는 기존
[증거](us-readiness/us-full-universe-real-dry-run-actions-evidence-v1.json)와
[artifact](https://github.com/jaehojung1879-netizen/Investment/actions/runs/38228554292/artifacts/11737957109)에 그대로 보존한다.
503개 구성 증권·SPY·QQQ의 **한 번의 성공**이며 다일 안정성 증거가 아니다.
새 다일·중단·정정 테스트는 명시적인 SYNTHETIC_FIXTURE다.

## 구현과 저장 계약

새 `pipeline/us_persistent_daily_collection.py`는 기존 소스·가격 엔진·불변
ObservationStore를 재사용한다. 기존 collector/Finnhub/H63/P4/봉인 연구/CI
workflow·보호 테스트는 변경하지 않는다. 새 workflow도 없다.

외부 owner 지정 영속 root 아래 기존 `prices/us/<version>`과
`universe/us/<version>`을 유지하며 `collection-control/<foundation-version>`에
시도·수집 기록·완료 표시·HTTP 감사 기록을 내용 해시별 불변 JSON으로 추가한다.
합성은 모두 `-fixtures` namespace다. 원본 CSV, 관측된 구성, 획득 시각,
공급자·버전·옵션·가격/액션 원본 패널과 as-traded 값은 기존 저장 계약을 따른다.
메타데이터에는 완료 세션, source snapshot/manifest 참조, 승인 hash와 code digest,
실제 어댑터 시도·재시도, 중단 이유를 남긴다. CLI의 HTTP 감사 기록은 credential,
cookie, URL을 저장하지 않고 실제 curl 호출과 응답 상태를 보존한다.

- 일일 기본값: 최근 완료 XNYS 세션 하나. 종료 +60분 규칙 유지.
- 수동 누락 복구·정정 확인: 최근 7개 완료 세션 중 하나를 명시. 이를 넘는
  중단/과거 재수집은 자동 backfill하지 않고 별도 설계·권리 검토가 필요하다.
- 기본 어댑터 총 예산 600회 / 1,200초, 호출 시작 간격 최소 1초.
  제한값은 재시도까지 포함한다. 기존 HTTP 계층은 최대 2,000회 / 1,200초다.
  시간은 요청 사이에서 검사하므로 in-flight timeout/저장 비용이 추가될 수 있다.
- 일시적 network/timeout만 종목당 최대 1회, 최소 5초 backoff 후 재시도한다.
  schema·단위·빈 frame·기업행동 결측은 추측 수선하거나 반복 retry하지 않는다.
- 429·401·CONNECT 403·미해결 403은 전체 호출을 중단한다. 429는 vendor 일반
  Exception 처리에도 흡수되지 않는다. 429 후 최소 15분 cooldown을 불변 기록에
  남겨 새 프로세스의 즉시 재개도 차단한다. 이후에도 자동 retry는 하지 않는다.
- 유효 건은 1건씩 즉시 저장한다. idempotent resume은 이미 검증된 날짜·증권
  ID를 재요청하지 않는다. ETF의 기존 유효 기록 또는 이번 검증을 gate로 삼으며
  두 ETF 미충족 상태에서는 구성종목 fanout을 진행하지 않는다.
- `--recheck`는 별도 owner 허용을 요구한다. 새 관측 시각의 소스로 재취득하며
  같은 경제 값은 반복으로 처리하고 변경 값은 원본을 덮지 않고 quarantine한다.
  최초 관측 이전 as-of 정보가 생기거나 이후 정정이 과거 조회를 바꾸지 않는다.
- 저장소 락 안에서 수집·manifest 검증·완료 표시를 처리한다. 기존 엔진의
  `_collect_locked`를 사용하므로 이 private interface 변경 시 호환성 재검증과
  새 code-digest 승인이 필요하다. 코드 승인 hash가 그 의존성도 포함한다.
- 완료 표시는 그 시점의 역사 기록이다. 이전 완료 표시가 있어도 최신 revision
  conflict/identity block을 지우지 않는다. 현재 준비 상태의 대용으로 사용하면 안 된다.
  manifest, 연결된 시도 기록, 원본 CSV·소스 참조를 검증하지 못하면 새 취득 전에
  차단한다. 중단 시 부분 가격·manifest·수집 기록을 유지하고 완료 표시를 쓰지 않는다.

root는 모든 Git checkout 밖이어야 한다. namespace symlink 탈출을 거부한다.
파일은 fsync 후 exclusive hard-link publication을 사용하며 기존 바이트는
불변이다. 로컬 POSIX 파일시스템·flock을 전제한다. 원격 객체 저장소의 atomicity,
NFS 락, 다중 writer 서비스와 영속 볼륨 운영은 검증되지 않았다. 무결성 hash는
암호학적 서명이나 관리자 삭제를 막는 수단이 아니므로 외부 backup/보존 ACL이 필요하다.
`verify`는 락을 잡으며 새 root에서는 빈 lock namespace를 생성할 수 있다.
현재 검증은 전체 저장 이력도 읽으므로 장기 규모의 시간·비용은 미측정이다.

## 이용조건·운영 한계 검토

2026-10-12 UTC에 표준 GitHub API로 다음 문서를 읽었다. **가격을 재수집하지 않았다.**

- [yfinance 공식 README](https://github.com/ranaroussi/yfinance/blob/main/README.md)
  관측 Git blob `00cf0d8d3ab5d281ef7a75afe3169f3e1699159c`.
  “Yahoo! finance API is intended for personal use only.” 및
  “not affiliated, endorsed, or vetted by Yahoo”를 명시한다.
  Apache 코드 라이선스는 Yahoo·거래소 가격 데이터의 반복 취득·영속 보관·재배포
  이용권이 아니다. 연구 목적이라는 말만으로 권리가 확인됐다고 하지 않는다.
- [Yahoo 이용조건 원문](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html)을
  표준 프록시로 읽으려 했으나 CONNECT 403이었다. 우회하지 않았다. 원문 현행
  계약, 자동/반복 요청 허용, 내부 연구 저장·보존 기간, 조직/상업 이용, 거래소
  라이선스·재배포 권리는 **미확정**이다. 실측 505 PASS가 권리 허가가 아니다.
- [구성 데이터 metadata](https://github.com/datasets/s-and-p-500-companies/blob/main/datapackage.json)
  관측 Git blob `975e770b30fca2b7b0f9af9338b553e7b7b87808`은
  ODC-PDDL-1.0을 선언하고 Wikipedia를 출처로 명시한다. 공급자 선언은
  공식 S&P 편입 기록·제3자 권리 보증이 아니다. 필요한 원출처 조건도 확인해야 한다.
- Yahoo/yfinance에는 이번 코드가 의존할 확정 SLA·공식 무료 요청 quota가 없다.
  1초 pacing과 위 예산은 내부 보수적 설정이며 공급자 승인 한도라는 뜻이 아니다.
  예전 비종결 HTTP 404 1회의 정확한 endpoint/원인은 미확정 상태를 유지한다.

현재 목록은 **관측 시점의 잠정 구성**이다. 과거 세션 가격을 받아도 과거 편입을
증명하지 않는다. CIK+symbol은 잠정 증권 ID이며 영구 share-class ID가 아니다.
이름 변경·symbol 재사용·미확정 이탈은 계속 차단하며 별도 identity 검토가 필요하다.
기업행동 원본 열을 보존해도 특별 배당·스핀오프·지연 정정의 전체성을 보증하지 않는다.
장기 저장·반복 신뢰도·큰 이력의 성능은 NOT_MEASURED다.

## 정확한 승인·수동 활성화 절차

1. owner가 반복 취득과 intended persistent storage 권리를 현행 Yahoo/거래소
   이용조건 또는 서면 계약으로 검토하고 근거·검토자·허용 범위를 기록한다.
   미확정이면 아래 승인 template의 false 상태를 유지한다. 공급자를 몰래 전환하지 않는다.
2. owner가 backup/복구·보존·디스크 여유·ACL을 갖춘 POSIX 영속 volume을 지정한다.
   GitHub-hosted `$RUNNER_TEMP`나 90일 artifact만으로 일일 영속 저장을 운영하지 않는다.
   실측 연결성은 GitHub-hosted 일회성 runner에서만 확인했다. 영속 volume을 갖춘
   실제 운영 host의 연결성은 미측정이며 별도 승인 후 확인해야 한다. 현재 코드는
   mounted POSIX volume을 전제하고 객체 저장소/Actions artifact의 자동 복원·승격을 구현하지 않는다.
3. owner 리뷰 후 병합한 코드에서 아래 network-free plan을 실행한다.
   `python scripts/collect_us_daily_persistent.py /durable/us-staging --mode plan`
   output의 절대 root, codeDigest, budgets를 확인한다. `--session YYYY-MM-DD`,
   필요 시 `--recheck`로 해당 실행 계획을 명시할 수 있다.
4. [차단된 승인 template](us-readiness/us-persistent-daily-approval-template-v1.json)을
   checkout 밖 owner 관리 위치로 복사해 실제 승인자·UTC 기간(최대 30일), 명시적
   first/lastSession, 검토 근거를 채운다. 실제 반복·저장 권리 검토가 해결된 경우에만
   두 usageReview permission과 approved를 true로 바꾼다. 재배포·일정은 false 유지다.
   만료까지 실행 예산+120초 이상이 남아야 하며 첫 세션은 승인 당시 최근 7세션보다
   앞설 수 없다. recheck 필요 시 owner가 allowRecheck도 명시한다.
5. owner가 파일 **원본 바이트**의 SHA-256을 별도 리뷰·등록하고 권한을 제한한다.
   `sha256sum /owner/approvals/us-daily.json`
   gate는 owner 서명·GitHub 사용자 신원을 자동 인증하지 않는다. 파일/hash를 모두
   조작할 수 있는 운영자를 막지 못하므로 보호된 owner 리뷰 채널·ACL이 신뢰 기반이다.
6. owner만 수동으로 다음 명령을 실행한다. **이번 PR에서는 실행하지 않는다.**
   `python scripts/collect_us_daily_persistent.py /durable/us-staging --mode collect --approval /owner/approvals/us-daily.json --approval-sha256 OWNER_REVIEWED_SHA256`
   코드/root/budget/기간/session/이용권 검토가 다르면 소스 요청 전에 차단한다.
   기본 mode는 plan이며 자동 일정·workflow dispatch·production 쓰기는 없다.
7. 실행 후 `--mode verify`와 최신 manifest에서 예상/유효/누락, 액션, 기호·구성
   차이, 정정 quarantine, 실패 원인·예산을 확인하고 외부 backup을 검증한다.
   partial이면 완료를 주장하지 않는다. transient 누락은 같은 root에 명시적으로
   재개한다. 429는 cooldown을 존중하고 source 권한·schema 문제를 먼저 해결한다.
8. 이후 일일 실행도 이 승인 범위 안에서 수동으로 진행한다. 다일 데이터와 실패·복구
   로그로 안정성을 확인한 뒤 별도의 owner 승인 PR에서 운영 자동화 필요성을 검토한다.
   닫힌 workflow inventory 때문에 영구 workflow 추가는 별도 검토 대상이다.

**매 거래일 실제 가격을 안전하게 쌓기 전에 남은 것:** 이용권 확인, 실제 owner 승인,
영속 volume/backup·복구 검증, 제한적인 수동 다일 운영과 실패 대응, identity·기업행동
한계 관리다. 이 PR은 이를 준비하는 구현과 합성 검증이며 실운영 승인이 아니다.
