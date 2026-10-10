# Phase C — 006800 원천 복원과 v3 결과 접근 전 addendum

이 문서는 병합된 PR #214 이후 남은 006800.KS 원천 복원을 기록한다. 작업 도중 #214가 main `b4ff60b4af19a9267313c50efbfe1f177cb7cfc6`에 병합되어, 사용자의 수정 지시에 따라 새 Draft PR에 신규 delta만 제출한다. 조사 중 원천 증거 commit `021c185`와 모든 미커밋 작업을 보존하고 최신 main을 포함한 `fix/kr-atlas-006800-source-integrity` 브랜치로 옮겼다. 기존 병합 내용을 cherry-pick하거나 재작성하지 않았다.

기존 [v2 문서](kr-alpha-atlas-phase-c-v2-input-repair-ko.md)와 당시 차단 receipt를 수정하지 않는다. v1/v2 등록·sidecar·의존성 및 보호 결과는 그대로 보존한다. 유효 계약은 별도의 [v3 addendum](../research_specs/kr-alpha-atlas-phase-c-v3-price-repair.json)과 exact-byte sidecar로 식별한다. 개별 주식 미래 라벨·alpha·IC·모형·포트폴리오 결과에 접근하지 않았다.

## 공식 원천이 설명하는 두 사건

**2018년:** 기존 3월 28일의 약 2.3512% 잔차 최대치는 사건일이 아니다. 원래 KRX/재생 입력의 동일 세션 OHLC 척도를 추적하면 첫 주요 미등록 변화는 **2018-01-23 권리락**이며 Close 척도 step은 `1.022910551121474`다. 2017-12-15 발표된 신주 발행은 기존 보통주 006800의 분할이 아니라 **신규 비전환 우선주 00680K** 1억4천만주 유상증자다. 보통주/우선주 기존 주주에게 우선주 청약권을 배정했다. 초기 배정비율 `0.1979513092`는 최종 투자설명서에서 `0.1979557317`로 확정됐다. 기준일은 1월 24일이다.

공식 [1월 22일 투자설명서](https://kind.krx.co.kr/external/2018/01/22/000742/20180122001829/10601.htm), [2월 19일 최종 투자설명서](https://kind.krx.co.kr/external/2018/02/19/000713/20180219001912/10601.htm), [최종 발행 결정](https://kind.krx.co.kr/external/2018/02/19/000651/20180219001785/11306.htm)은 청약권의 거래소 비상장과 양도 가능성을 명시한다. 2월 21–22일 청약, 3월 2일 납입, 3월 13일 교부, 3월 14일 상장은 설명서의 **예정 일정**이며 실제 완료 증명으로 표현하지 않는다. 발행가 5,000원이나 관측 주가 변화는 청약권의 경제적 가치가 아니다. 공식 권리 가치/기준가 계수를 확보하지 못했으므로 그 계수는 `null`을 유지한다. 3월 잔차에는 1월의 권리 척도와 기존 현금배당 환산의 vendor/raw 분모 차이가 함께 남는다.

**2026년:** [3월 13일 KRX 주식배당 공시](https://kind.krx.co.kr/external/2026/03/13/000897/20260313000999/61474.htm)는 보통주 1주당 **0.0073206주**를 확정한다. 2월 24일 이사회 결정, 3월 16일 배당락, 3월 17일 기준일, 3월 24일 승인/발행, 4월 22일 보통주 4,250,472주 추가 상장 자료를 구분한다. [회사 배당 IR](https://securities.miraeasset.com/newir/view/pc/kr/investor/dividendPaid.jsp)과 [회사 4월 소식](https://webzine.securities.miraeasset.com/webzine2604/vol2604_page31.php)은 별도의 보통주 **현금 300원**과 주식배당을 확인한다. 현금의 실제 지급일은 독립 확인되지 않았다. 고정된 ex-date 부분 분배지수의 원천 복원에 지급일을 임의 대입하지 않는다.

배당 직전 KRX 종가 69,500원에 대한 현금 factor는 `69,500 / 69,200 = 1.004335260115607`이다. vendor/raw 척도에는 이미 현금 factor가 반영돼 있다. 공유 조정기가 현금을 다시 반영한 내부 척도 step은 `1.0086763533363132`이고, 이 사건에서는 vendor가 주식 권리를 이미 조정했다는 가정도 맞지 않았다. 현금 중복과 주식 권리 누락은 별개의 결함이다. 파생상품 계약 승수 조정은 주주가 받는 보통주 비율과 다르므로 대체하지 않는다.

vendor 대조는 명시된 신규 capture vintage와 원래 고정 replay의 동일 세션 진단이다. 과거 취득 시점의 vendor 원응답 전부가 보존되지 않았으므로 당시 취득을 byte 단위로 완전히 복원했다는 주장은 하지 않는다. 공유 조정 경로와 관측 factor의 일치가 중복 처리 메커니즘을 뒷받침한다. 새 입력은 그 vendor 가정을 재사용하지 않고 원래 KRX raw quote와 독립적으로 확인된 권리 사실로 재구성한다.

공시 원응답·압축 저장 byte·capture 시각·SHA-256은 [source manifest](audits/kr-alpha-atlas-phase-c-integrity/mirae-source-recovery/sources.json)에 있다. 2018 최종 설명서 원응답 SHA-256은 `4a8a1e51c729a99956ccabc412907ef592e10ddc159c8218cf7328afedd91933`이다. [동일 세션 OHLCV 진단](audits/kr-alpha-atlas-phase-c-integrity/mirae-source-recovery/source-diagnostic.json)은 원래 고정 Git blob identities와 두 이벤트의 원시 전후 quote를 보존한다.

## 검증된 연결 구간 복원, 미확인 권리 경계 차단

선택은 사용자가 허용한 **Option B**다. 청약권 payoff까지 확보한 전체 wealth path 복원이 아니다. 고정 source commit `4ea107ed0cde289f0a049a65ff13d2441a786710`의 14개 KRX 원자료에서 006800의 **3,364세션** OHLCV를 가져온다. 모두 양의 거래량과 정상 OHLC 순서다. 최신 vendor 재취득 자료로 원래 pin을 바꾸지 않는다.

기존 개별 주식의 **부분 분배지수 정의**를 유지한다. 등록 현금 `D_t`, 직전 raw KRX 종가 `P_(t-1)`, 보통주 entitlement `r_t`에 대해 `q_t = q_(t-1) × r_t / (1 − D_t/P_(t-1))`이며 OHLC 모두 `raw_OHLC_t × q_t`다. 등록되지 않은 분배금이 존재하지 않는다고 주장하지 않는다. 이 식은 ETF의 별도 gross shareholder total-return 정의와 구분하며, 종목 전체 분배금의 완전성을 인증하지 않는다.

2026-03-16에는 현금 300원을 한 번, `r_t = 1.0073206`을 한 번 적용한다. 주식 단위 `u_t = u_(t-1) × r_t`에 대한 volume은 `raw_volume_t / u_t`다. 현금과 다른 종류주식 청약권은 보통주 volume 단위를 조정하지 않는다. 가격·거래량 역변환은 원래 KRX quote와 대조한다. 거래대금 proxy/용량은 기존 원시 KRX bar와 원래 규칙을 유지한다.

**2018-01-23 OHLC는 NaN**으로 남기고 이후 연결 구간을 독립 정규화한다. raw 거래량, PIT membership와 회계 정보는 보존한다. 경계를 건너는 모든 관련 가격 창/보유 창은 무효다. 권리 가치나 합성 quote를 만들지 않고, 두 구간의 정규화 척도를 나누어 수익률을 만들지 않는다. 원천 정책은 수정 커버리지를 보기 전에 commit `021c1852375f0512e4e7317dd13f94af52041973`에 고정했다. 경계는 60%를 통과하는 날짜를 찾은 결과가 아니다.

기존 H01/H08 industry 정의는 모든 constituent의 동일 trailing 창을 요구한다. 따라서 유효하지 않은 006800 창은 해당 날짜 FINANCIALS reference와 구성원에게 전파돼야 한다. 생존 종목만으로 재정규화하지 않는다. 반면 전체 714일의 FINANCIALS나 무관한 업종을 차단할 이유는 없다. 기존 industry 함수가 양 끝 quote만 검사하는 부분에는 **006800에 한정된 중간 세션 유효성 guard**를 추가했다. VQ endpoint 읽기와 가격을 사용하는 OHLCV 함수에도 동일 원천 경계를 적용하며 순수 volume/capacity/회계 입력은 보존한다. 원래 label engine의 모든 보유 세션 유한값 검사를 그대로 사용한다. 이 PR의 label 시험은 가상 가격뿐이다.

2026 주식 권리는 ex-date부터 forward 적용한다. 4월 상장은 사후 원천 확인이며 이를 과거 신호에서 알았다고 취급하지 않는다. 이후 기업행위 수정이 과거 가격 prefix를 바꾸지 않는 합성 검사를 포함한다. 원래 legacy 분배금/기업행위 vintage 한계가 없어졌다고 주장하지 않는다.

## 실제 커버리지 전파

동일 usable range는 2013-07-05–2026-09-11, **82,560 name-date 관측**이다. H01/H08의 availability mask는 같다. 수치 아래의 measured rows에는 실제 미래 수익률이 포함되지 않는다.

| 원천 상태 | H01 usable coverage | H08 usable coverage | H01/H08 측정 관측 | B0/B4 | X3 |
| --- | ---: | ---: | ---: | --- | --- |
| 원래 Phase B reference | 70.058140% | 70.058140% | 57,840 | READY | READY |
| 보존된 v2 전 기간 거부 | 53.748789% | 53.748789% | 44,375 | INSUFFICIENT_COVERAGE | INSUFFICIENT_COVERAGE |
| 공식 원시 구간 복원 v3 | **69.107316%** | **69.107316%** | **57,055** | **READY** | **READY** |

v2에서 잃었던 FINANCIALS 45종목·565신호일·13,465관측 중 **45종목·538신호일·12,680관측**을 복원한다. 원래 reference 대비 **2018-01-26–2018-07-27의 30종목·27신호일·785관측**은 원천 경계를 포함하여 잃는다. 126-session 창의 실제 달력 전파이며 커버리지에 맞춘 임의 기간이 아니다. 무관한 업종의 추가 결측은 **0**이다. 해당 년도/업종별 손실·복원과 원인 코드는 전체 준비 receipt의 `coveragePropagation`에 있다. 006800 자체의 714 PIT 행은 유지된다.

전체 구조는 714신호일·85,680행·76열·260종목 그대로다. 신규 행렬 digest는 `c3d66a99f1e1a1c525a9a659b0bee3cc1bf04109796234b310f0513b222187e7`다. 최초 원천 재구성은 938.698초, 최대 RSS 1,804,505,088 bytes였고, 회계 visibility 805,676셀의 위반 0 및 결측 1,550,874셀의 reason 누락/어휘 오류 0을 확인했다. 해시 고정 뒤 **별도 fresh 전체 준비 경로 재현**의 결과는 아래 최종 receipt로 확인한다.

고정 계약과 원래 `preflight.prepare`를 사용하는 독립 fresh 재현은 main `b4ff60b4af19a9267313c50efbfe1f177cb7cfc6`에서 **PASS_OUTCOME_FREE_CORRECTED_PREPARATION**이다. 예상/실제 digest가 일치했고 941.494초·최대 RSS **1,806,888,960 bytes**였다. cgroup capacity는 8GiB, 시작 disk 여유는 29,090,267,136 bytes였다. 네트워크 main/잠금 재확인, 41개 Git object identities, 실제 원천 schema, 원래 runtime/packages/thread 설정, 전체 원래 PIT/결측 규칙, 동일 준비 경로, 파일 쓰기와 exact-byte 재저장/다른 bytes 거부를 검사했다. receipt SHA-256은 `0fdf87324c5542a5186d446966a4ef6bd83368b20b0670d2e5dbd12fbdb119b6`다.

B4의 같은 2016-04-01 이후 65,400행 complete-case 비율은 Phase B **44.319572%**, 차단 v2 **38.261468%**, 복원 v3 **43.931193%**다. 전체 기간 비율 33.532913%와 공통 기간 비율을 혼동하지 않는다. complete-case만 골라 유리한 종목을 비교하지 않는다. 원래 training-only percentile/median 처리와 missingness indicators, 동일 outcome-validity/common sample 및 연간 chronology를 유지한다. source-ready는 실측 모형 개선이나 nomination을 뜻하지 않는다.

처음 fresh 검증을 시작할 때 원격 main이 바뀌어 준비 전에 `LATEST_MAIN_CHANGED`로 거부된 기록도 남긴다. 이는 외부의 #214 병합 때문이었고 입력 준비/잠금/결과 경계에 도달하지 않았다. AGENTS.md와 보호된 v1 엔진의 변경이 없음을 확인한 뒤 새 main에서 fresh 디렉터리로 검증했다. 과학 실패를 반복 실행한 것이 아니다.

## 버전·실행 보호와 검증

신규 addendum은 원래 38후보/73 feature-horizon readings, B0–B4/30 family comparisons, X1–X6, H21/H126 추론·H63/H252 기술통계, BY/Holm, 비용/용량/최대 5종목 및 90분/8GiB/574 fits를 유지한다. X4는 기존 source block이다. 235종목 마지막 세션 복원과 3종목 거부, 기존 terminal consideration 거부도 유지한다.

v1 `b57be30ce54abf1dd26388954053e99d4b1bf71fa06f3598787317e953988db0`, v2 `ca2564703dc018474a3d041f95d86bf16aa053a91ca4453cb975801c17a577bb`의 바이트와 의존성은 보존한다. 069500.KS의 2013–2026 gross shareholder benchmark reconciliation은 변경하지 않는다. 매년 기존 0.50pp 기준을 통과했고 최대 차이는 0.023663pp다. 원래 v1 BLOCKED_UNVERIFIED와 당시 v2 전체 종목 차단 receipt도 역사적으로 남는다.

최초 로컬 전체 검증은 4,186 passed·1 UTF-8 source encoding 실패·1 skipped·4 xfailed였다. 공식 비-UTF-8 원응답을 editable `.html`로 저장한 것이 원인이었다. 기존 검사를 수정하거나 예외 처리하지 않고 원응답을 그대로 gzip으로 포장했다. 원래 raw SHA-256/capture 시각·006800 입력 identity·행렬 digest·가격 규칙은 불변이다. [포장 전 authoring archive](audits/kr-alpha-atlas-phase-c-integrity/mirae-source-recovery/authoring-before-capture-packaging/packaging-erratum.json)에 최초 등록 `d681eedf76f783eb37c01b9560fefc3a2972eb4c6f3ce4c3d415218ff517f7d9`, module bytes, source manifest/diagnostic 및 첫 fresh receipt를 보존했다. 이들은 현재 149개 의존성의 일부다. 과학적 재탐색이나 v1/v2 덮어쓰기가 아닌 **결과 접근 전·최초 출판 전 저장 형식 erratum**이다.

최종 v3 파일 해시는 `64c742408331d7da91e8def6a6eba6fde52d5f19734b011e1287e8a7622c8198`, effective contract는 `b8e436b24da0907d3bd7fc802984628a912516f592f7968d7adf33bb2d2a6361`이다. 최종 포장 해시로 [독립 fresh 준비 receipt](audits/kr-alpha-atlas-phase-c-integrity/mirae-source-recovery/full-input-preflight-packed.json)를 추가하며 앞선 receipt는 덮어쓰지 않는다. owner는 보존된 초안 해시를 승인하는 것이 아니라 최종 addendum/effective/dependency 세 가지 정확한 해시를 별도 지시 후 승인해야 한다.

최종 포장 계약의 독립 fresh 준비도 **PASS**다. 준비 923.205초·최대 RSS 1,808,793,600 bytes이며 입력 identity `d0b9746c26397f604474515e46bd1bdc06183aadb6c4119d703a56826cb7c3c2` 및 동일 행렬 digest를 재현했다. 최종 receipt SHA-256은 `3f4b6978cba8c249ec817939f0f4fa03b2ad69ac359567b02eb0b325618f3aa9`, dependency manifest SHA-256은 `3109afd5256d6af6b83c9d4a0ca4a61faceac2b21fcb0d9495892fd6b5787e9a`다. 실제 alpha outcome/forward label/model fit/stock outcome analysis/backtest/formal dispatch/permanent lock 카운터는 모두 0이고 방화벽 금지 호출도 없다. 이 시간은 실제 연구 성과 분석의 runtime 측정이 아니다.

새 effective contract는 기존 `prepare`/matrix/readiness/label/model/economic 함수를 사용하며, 수정된 006800 source overlay와 유효성 guard만 추가한다. 신규 수동 workflow는 `.yaml`이고 기존 `.yml` inventory 보호를 보존하면서 별도 전체 `.yml`/`.yaml` census로 관리한다. 자동 정식 실행은 없다.

최종 로컬 전체 검증은 **4,187 passed·1 skipped·4 xfailed·0 failed**, 1,327.40초다. ruff, pipeline compileall, 전체 entry-point import/script compile, seed 생성/명시적 seed validation, 106개 등록 map 검증도 통과했다. 원래 합성 시나리오 A–N과 신규 원천/경계/버전 검사를 포함한다. 최종 계약을 사용한 전체 합성 실행은 73개 feature-horizon readings·30개 family comparisons·6개 interactions·196개 **합성** fits·43,392개 **합성** labels를 처리했다. canonical digest는 `49e7c4d637aa5a4f0732c5b9b2809ae49350ffaf34069a8ca37c504c966605d5`이며 실제 투자 evidence가 아니다. main `b4ff60b`의 Tests run `38005460120`과 Pages run `38005460166`은 모두 SUCCESS다. 새 PR의 정확한 head CI는 제출 후 별도로 확인하고 PR handoff에 기록한다.

모든 버전은 연구 ID, 결과 경로, artifact prefix와 **`refs/tags/kr-alpha-atlas-phase-c-v1-execution-lock`**을 공유한다. 별도의 exact v3 addendum/effective/dependency hashes를 담은 owner commit과 owner/main 수동 dispatch 없이는 정식 경계에 도달할 수 없다. source/runtime/PIT/matrix/readiness/합성/budget/쓰기 probe는 atomic claim보다 먼저다. partial claim/API 실패와 상태 불명은 소비/독립 확인 대상으로 남기고 재시도하지 않는다. post-lock 저장 실패는 이미 만들어진 exact byte만 복구하며 연구 재실행을 허용하지 않는다.

검증 명령은 Python 3.11.16과 고정 requirements, `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1`에서 실행한다.

```bash
python scripts/run_kr_alpha_atlas_phase_c_price_repair.py validate
python scripts/run_kr_alpha_atlas_phase_c_price_repair.py preflight \
  --expected-main VERIFIED_MAIN_SHA --work /tmp/atlas-v3-new-source-preflight
python scripts/run_kr_alpha_atlas_phase_c_price_repair.py synthetic \
  --work /tmp/atlas-v3-invented-market
```

실제 source reconstruction/커버리지/시간/RSS/PIT 및 검증 결과는 별도 최종 [준비 receipt](audits/kr-alpha-atlas-phase-c-integrity/mirae-source-recovery/full-input-preflight-packed.json)와 [handoff receipt](audits/kr-alpha-atlas-phase-c-integrity/mirae-source-recovery/validation.json)에 기록한다. alpha 검증 결과로 해석하지 않는다.

## 이후 사람의 조치

모든 원래 source gate와 실제 fresh preflight 및 새 PR-head CI 통과를 확인한 뒤 사람이 후속 source 복원 addendum을 검토/병합할 수 있다. 이 문서는 병합 또는 실행 승인이 아니다. 병합 뒤 actual main에서 신규 workflow의 **action=preflight만** 실행하여 runner receipt를 확인한다. 이후 별도 지시로 owner가 `research_specs/kr-alpha-atlas-phase-c-v3-execution-authorization.json`에 exact hashes를 commit하고, 동일 owner가 main에서 action=execute를 단 한 번 dispatch해야 한다. 현재 어느 버전의 승인 파일·영구 잠금·정식 결과도 만들지 않는다. 청약권 경계를 건너는 관측과 미확인 terminal economics는 정식 평가에서도 그대로 무효/차단된다.
