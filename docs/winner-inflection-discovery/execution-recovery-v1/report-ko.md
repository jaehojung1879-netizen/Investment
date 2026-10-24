# WID 역사 실행 복구 — 2026-10-24

**실제 진전:** 고정 WID 입력의 Git 결손을 재현하고, 기존 캐시만으로 필수 **398/398 객체**를
주소 지정할 수 있게 복구했다. 라벨·모델 실행 승인은 별개이며 현재 7개 source review가 남아 있다.
코드/합성 검증/실제 Git 메타데이터 검증을 수행했고 정식 역사 연구는 실행하지 않았다.

출발 main: `591f182955ab85bc527ddedc41c2d77d1fd24eaa`.
현재 signal-history 확인: `38ea768eab6d58cf0a4963ddf177959ad5977aae`.
증거 원본과 검증 수치는 [evidence.json](evidence.json)에 있다.

## 실제 수정 및 재현

기존 `source_preflight`는 필수 커밋을 찾지 못하면 원인을 `CalledProcessError`로만 보고했다.
따라서 커밋/트리 경로 결손과 시장 데이터 결손을 구별하기 어려웠다. 이 환경에서도 실제 재현했다.

- `pipeline/winner_inflection_local_git.py`: donor의 원격/참조/replace 설정을 물려받지 않는
  임시 bare 객체 뷰와 **명시적 로컬 donor 메타데이터 복구**.
- `source_preflight`: 누락 커밋을 `PINNED_COMMIT_METADATA_MISSING`으로 분리하고 로컬 뷰에서 검사.
  기존 등록 manifest와 398개 허용 목록/해시/가용성 기준은 유지한다.
- `scripts/prepare_winner_inflection_git.py`: 기본값은 검사, 복구에는 로컬 `--donor`가 필요하다.
  fetch·가격/공시 본문 복구·권리 승인·원격 태그 생성 기능은 없다.
- 새 모듈은 실행 request의 `CLOSURE`에 추가했다. 변경된 코드로 과거 승인 manifest를 재사용할 수 없다.

실제 고정 커밋 `1bf68f59cffa20239977e2cfaa0f35a07d0ec884`와
`002b56434e3aa3e845798ec2ea7ca6d9267e3f7a`에서 커밋 2개·트리 202개·검증된 manifest 1개를
**658,294 bytes**로 복구했다. 시장 payload blob은 0개다.

| 실제 검증 대상 | 결과 |
|---|---|
| 복구 전 현재 clone | 고정 커밋 경로를 찾지 못해 BLOCKED |
| 빈 bare 대상 + 메타데이터만 복구 | 398개 중 **398개 결손**, 계속 BLOCKED |
| 이번 작업 전부터 있던 pack 두 개만 연결 + 동일 메타데이터 | **398개 중 결손 0**, SOURCE READY |
| 현재 원래 실행기의 preview | Git READY, 7개 source review 때문에 전체 BLOCKED |

**작업 중 설명 정정:** 최초 일반 Git `fetch --filter=blob:none` 복구에서는 약 3.35GB의 추가 pack
(blob 10,928개 포함)도 수신했다. 이를 metadata-only라고 주장하지 않는다. 격리된 합성 promisor
실험에서는 기존 preflight가 fetch하지 않았으므로 그 코드의 lazy-fetch 결함이라고 단정하지 않는다.
새 도구는 로컬 donor만 쓰며, 앞서 받은 큰 pack을 제외한 작업 전 캐시만으로도 398개가 충족됨을
별도로 증명했다. 금융 payload를 해석하거나 신규 실제 수익 라벨을 계산하지 않았다.

## 이용 가능한 범위와 서로 다른 차단

다음 준비도는 이미 공개된 #250의 **입력 측정 결과**를 인용한다. 이번에 census/역사 검정을 반복하지 않았다.

| 범위 | KR | US |
|---|---|---|
| 보존 가격 테이프 | 2011-01-03~2026-09-14 | 2011-01-03~2026-09-14 |
| 완료 주간 입력 | 2013-01-04~2026-09-11, 714주 | 같은 범위, 715주 |
| 모집단·분모 | 당시 Top120, 85,680 member-dates | 엄격 이전 재구성 S&P500, 359,526 member-dates |
| WID A 성장 가속 측정 | 25,167 / 29.373% | 166,040 / 46.183% |
| WID B 현금/수익성 전환 측정 | 28,250 / 32.972% | 197,088 / 54.819% |
| WID C 산업 상대강도 변화 측정 | 59,550 / 69.503% | 294,395 / 81.884% |
| A/B 최초 측정 | 2018-05-04 | A 2014-01-31, B 2013-02-01 |

이는 사건 양성 수·정확한 신원·만기 수익·권리 승인 수가 아니다. 원 분모에서 관측 불가능 종목을
지우지 않는다. 전체 KRX/미국 시장으로 일반화하지 않는다.

- **데이터 측정 결손:** 별개 Track A0의 H1/H2/H3 측정률은 KR 37.941/37.593/35.978%,
  US 58.127/58.092/1.030%다. WID A/B/C와 정의/분모가 다르다. US A1은 `NO_GO`,
  KR A1은 `GOVERNANCE_CLOSED`, MDE 미해결이다. 이 수치를 WID 실행 승인으로 바꾸지 않는다.
- **신원·종료·총수익:** WID US는 own-panel 및 removed-but-still-trading의 날짜 있는 CIK
  일치 범위만 조건부 후보다. ticker 재사용/개명/종결 대가 미확인은 해결되지 않는다.
  가격의 현금 재투자 기준·배당 통화/주당 단위·기업행동 누락 검증이 별도로 필요하다.
- **기존 US 이탈 가격 후보:** 공개 admission 기록은 212 identities, 후보 175개,
  186,910 후보 세션, 최종 admitted 0개다. 신원/단일 basis/기업행동/CIK 연결이 남아 있다.
  예상 비공개 원본 경로 `/workspace/pr241-nonpublic-preservation`은 이 환경에 없고 정확한
  archive 이름도 발견하지 못했다. 과거 보고서의 checksum 검증을 이번 실재 파일 검증으로 주장하지 않는다.
  제거된 공개 commit/blob은 요청하지 않았다.
- **법적 보존 권리:** #259의 Starter Tiingo 원본/파생 영구 저장 NO-GO는 유지한다.
  Tiingo `--run`, 새 구독/Secret/비공개 저장소를 만들지 않았다. 코드의 공개 라이선스나
  Git 객체 보유는 upstream 데이터의 연구/보존 허가가 아니다.
- **실행 환경:** 로컬 Python/Git 합성 테스트는 가능하지만 이 환경의 GitHub API는 `Forbidden`이다.
  소유자 댓글 검증·시도 태그 등록·PR 생성은 API 접근 가능한 기존 소유자 환경이 필요하다.

무료 대안의 우선순위는 이미 보유한 own-panel 조건부 표본의 근거 검토와 기존 공시/SEC accession을
이용한 issuer·share-class 연결이다. SEC 직접 접근 가능 여부와 보존 조건은 별도 확인해야 한다.
이는 과거 상폐 가격·종결 대가 전체를 무료로 복구한다는 약속이 아니며, source admission 전에는
이 최소 표본도 합법적 실행이 확인됐다고 표시하지 않는다.

## 최초 후속 실험과 승인

가장 짧은 경로는 이미 구현된 **US B / H126 / 2020 validation fold**다. 고정 원천은 가격/행동
2011-01~2021-07-06 및 FY2011~2021 공시다. 2013년부터 과거-only 학습 후보를 만들고,
학습 라벨은 2019-11-29 이전 공개/만기, proper-fit/보정 구간을 다시 purge한다.
최소 36개월·100발행인·500행 및 클래스별 최소 수를 통과해야 한다. 실제 적격 학습/승자/손실 수는
아직 라벨을 열지 않았으므로 **미확정**이다. 실패하면 그 상태로 보고한다.

고정 사건 규칙 → L2 승자/대형손실 Logistic → Ridge를 동일 표본에서 비교한다.
현재 수익성·252일 모멘텀·규모 대용치 기준에 B의 4개 변화 특징을 추가한다.
같은 날짜·산업·규모 대조군, Brier/PR-AUC/수익 오차, 비중첩 H126 Top5의 비용 차감 SPY 비교를
한 번에 얻는다. **가치 팩터는 이 baseline에 없으므로 가치와 독립적인 알파라고 주장할 수 없다.**
QQQ와의 비교도 이 SPY 고정 실험의 결론이 아니다. 비선형 모델이나 A/C 확장은 이번 변경에 없다.

KR A/B의 최초 후보 fold는 36개월 관측 조건상 H126 2022년/H252 2023년 이후다.
기존 KR Atlas/Overlay를 다시 실행하는 것이 아니라 별도 명칭·사양·노출 등급이 필요하다.
Atlas의 38변수/73평가/574학습·지명 0/Level4 미실행과 Overlay의 `DEVELOPMENT_REJECT`는 그대로다.
Phase D는 그 프로그램을 종료했고, 새 소유자 지시의 별도 탐색을 전면 금지하는 것으로 해석하지 않는다.
기존 결과를 구제하거나 새로운 독립 OOS로 위장하지 않는다.

**실제 라벨 열람 전:** rights, identity, membershipIndustry, returnBasis, terminal, size, vintage의
7개 근거를 검토하고 `source-admission-v1.json` 형식의 별도 review에 문서 SHA를 고정해야 한다.
현재 모두 UNRESOLVED이므로 `approvalText`는 null이다. 근거가 준비된 뒤 clean HEAD/런타임/출력 경로를
묶은 request를 생성하고 소유자의 정확한 `APPROVE WID_EXECUTION <request.sha256>` 댓글을 확인한다.
소유자 확인과 새 durable attempt ref가 성공해야 입력을 연다. 이번 작업은 댓글·시도 태그·승인 파일을 만들지 않았다.

## KR 전향 연결: 읽기 전용 확인

#277/#278은 병합돼 있고 codeFileHashes의 3/2개 파일은 main과 일치한다. 첫 신호 바닥은 2026-10-30.
작성 창은 10/30 18:00 KST~11/2 09:00 KST 미만이며 10/31 오전 daily ledger가 첫 예정 기회다.
아직 그 날짜 전이므로 status/receipt 부재 자체는 결함이 아니다. 새 영수증은 생성하지 않았다.

현재 배포 snapshot은 10/24 04:17 UTC, build `591f182955ab`, marketAsOf 10/23,
live/non-seed/productionValidation PASS다. 이것이 종목별 Yahoo 연속 관측 창이나 연구 hook 성공을
보증하지 않는다. KR weekly publication은 여전히 10/23 `SOURCE_INCOMPLETE`이며 최신 FINAL로 간주할 수 없다.
canonical DART FY2026은 483건·242종목·최신 availableFrom 9/16이고, daily kr 업데이트는 canonical
자동 갱신 증거가 아니다. 날짜만으로 공시가 잘못됐다고 단정하지 않으며 첫 신호 전 관련 신규 공시를 대조해야 한다.
가용성·권리·수익 기준이 불명확하면 연구 자체의 거부 규칙을 적용하고 사후 보충하지 않는다.
첫 기록 전에는 v1의 253개 KRX 관측 창, v2의 최신 20/60세션 가격·거래량/유동성 및 업종 peer/회계
coverage를 실제 입력으로 확인해야 한다. `availableFrom < signal`과 기업행동 기준, 단계별 publication
상태·정확한 code digest를 그대로 적용한다. 이번 점검은 새 vendor 다운로드를 수행하지 않아 이
종목별 가용성은 INCONCLUSIVE이며 main Actions의 녹색 상태로 대체하지 않는다.

## 재현·검증·독립 감사

```bash
python scripts/prepare_winner_inflection_git.py inspect
python scripts/prepare_winner_inflection_git.py restore-metadata --repo /path/to/target --donor /path/to/existing/local/repository
python scripts/run_winner_inflection.py preview
python -m pytest -q tests/test_winner_inflection_local_git.py tests/test_winner_inflection_execution.py tests/test_winner_inflection.py tests/test_experiment_workbench.py
```

118개 합성 테스트, 전역 ruff, pipeline/scripts compileall, /tmp seed 생성/검증 통과.
실제 봉인 KR 결과를 재계산하는 테스트가 있어 전체 pytest는 실행하지 않았다.
base main Tests [40058393739](https://github.com/jaehojung1879-netizen/Investment/actions/runs/40058393739),
#250 Tests [38982117107](https://github.com/jaehojung1879-netizen/Investment/actions/runs/38982117107),
#253 Tests [39004310097](https://github.com/jaehojung1879-netizen/Investment/actions/runs/39004310097)는 SUCCESS다.
이 결과를 새 브랜치 CI로 재사용하지 않는다.

독립 감사에서는 metadata pack의 blob 허용 목록이 manifest 단 하나인지, source-view에서 원격이
배제되는지, 기존 코드 request가 새 closure를 우회하지 못하는지, 398/398 준비가 source admission을
자동 승인하지 않는지 확인해야 한다. 과학적 실행/소유자 승인/권리 검토는 이 PR과 별도다.
Claude 담당 #285/#284/#280/#283, C1, 봉인·결과·명세·원장·보호 설정·운영 정책은 변경하지 않았다.
