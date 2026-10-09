# KR Alpha Atlas Phase C — 최종 실행 전 무결성 감사

정식 실행 전에 **등록 개정 여부를 사람이 결정해야 한다**. 운영 준비 함수는 실제 고정 입력을 끝까지 재구성할 수 있다. 그러나 공식 ETF 시장가격·분배금으로 대조한 2022–2026의 벤치마크는 모두 등록된 0.50pp 기준에 실패했다. 현재 v1을 바꿔 통과시키거나, 새로운 실험을 등록하거나, 정식 실행을 승인하지 않았다.

## 감사 경계와 고정 파일

기준 main은 `c9c636ec06a6118718ba009b12262d600cecbbfb`다. AGENTS.md와 병합된 계약을 확인했다. 과학 등록 SHA-256은 `b57be30ce54abf1dd26388954053e99d4b1bf71fa06f3598787317e953988db0`, 의존성 manifest SHA-256은 `5e71455a3f01c1796ac99d5e7b66b30baa7c2982c62cb5ea1013201892f91820`다. 의존성 113개와 기존 보호 파일 235개의 해시를 보존했다.

이번 사용자의 명시적 지시가 허용한 범위는 다음 두 가지다.

- A: 고정 입력의 동일성, PIT 특성 및 실제 준비 객체 재구성. 가격 파일과 기존 과거창 특성 계산은 허용하지만 미래 목표·성과 평가에는 사용하지 않는다.
- B: 069500.KS만 사용하는 독립 벤치마크 무결성 대조. 이 문서의 실제 수익률 숫자는 모두 이 범위다.

개별 종목 미래 수익률, 종목-벤치마크 alpha, 지도학습 예측모형의 역사적 적합, IC, 스프레드, 포트폴리오 backtest는 실행하지 않았다. 기존 봉인 alpha 결과를 열어 정의나 기준을 선택하지 않았다. 정식 실행 dispatcher, 승인 파일, 실제 잠금 및 공식 연구 결과는 생성하지 않았다.

새 도구는 `pipeline/kr_alpha_atlas_phase_c/` 밖에 있고 기존 엔진에서 import되지 않는다. 증거는 `docs/audits/kr-alpha-atlas-phase-c-integrity/`에 두어 `research_specs/`와 `docs/results/`의 기존 보호 집합도 변경하지 않는다. Pages workflow는 고정 의존성·보호 집합 밖임을 확인했다.

## 벤치마크 원자료와 경제 정의

벤치마크는 그대로 **069500.KS, KODEX 200 ETF**다. KOSPI200 가격지수로 바꾸지 않았다.

| 원천 | 이번 감사에서의 역할 | 한계 |
| --- | --- | --- |
| 고정 replay-v16 `benchmark/*` 객체와 `benchmark/source` | 실제 등록된 Close와 원본 계보 | source는 `krx-total-return`이지만 실제 경로는 네이버/FDR 세션과 Yahoo actions를 합친 조정 값이다. 이름만으로 공식 KRX 총수익이라고 해석하면 안 된다. |
| 삼성자산운용 `excel_standar.do`, fund ID `2ETF01` | 2002–2026 공식 ETF 시장 종가, NAV와 과표기준가 | 종가·NAV는 그 자체로 분배금 재투자 총수익이 아니다. 다운로드에는 cutoff 뒤 날짜도 있으나 모든 수익률 계산 전에 2026-09-14에서 자른다. |
| 삼성자산운용 `divid-info.do` JSON 및 `excel-divid-list.do` | 공식 gross 분배액, 기준일·지급일의 두 형식 대조 | 반환된 최근 20건은 2021-10부터다. 이전 지급액을 0으로 가정하지 않는다. 과세 대상 분배액은 투자자 세후 현금과 다르며 gross 분배액을 사용한다. |
| 네이버 `siseJson.naver`, 종목 069500만 | 기존 원본 vendor의 조정 방식 진단 | 새로 캡처한 자료다. 기존 pinned snapshot으로 재명명하지 않는다. 원래와 같은 vendor이므로 독립 검증 원천으로 인정하지 않는다. |

정확한 URL·캡처 시각·바이트 수·SHA-256은 [source manifest](audits/kr-alpha-atlas-phase-c-integrity/sources/sources.json)에 있다. 공식 raw XLS/JSON도 함께 보존한다. [상품 원천](https://www.samsungfund.com/etf/product/view.do?id=2ETF01), [공식 분배금 설명](https://www.samsungfund.com/etf/product/distribution.do).

독립 대조는 공식 ETF 시장 종가와 공식 gross 분배금에 **현재 코드와 동일한 Yahoo 조정 식** `Close[t] / (Close[t-1] - D[t])`를 적용한다. 분배락 세션은 기준일 직전의 등록 KRX 세션이며 지급일로 바꾸지 않는다. 모든 비교는 동일한 연말 전 세션에서 다음 연말까지이며 2026은 cutoff까지다. 수수료·투자자 세금은 대조 수익률에 넣지 않고, ETF 자체 비용은 가격에 포함돼 있다. 등록된 투자 실행의 benchmark 비용 15bp씩은 변경하지 않았다.

경제적 현금 재투자 식 `(Close[t]+D[t])/Close[t-1]`은 별도 진단으로 남긴다. 통과하는 식을 찾으려고 선택하지 않았다. NAV 가격 수익률, ETF 가격 수익률, KOSPI200 PR/TR/NTR, vendor adjusted close는 혼용하지 않는다. 가격-only와 NAV-only 대조는 `NOT_COMPARABLE`이다.

## 연간 독립 대조

[기계 판독 대조 보고서](audits/kr-alpha-atlas-phase-c-integrity/benchmark-reconciliation.json)는 모든 연도의 source identity·정의·anchor·종료일·일치 세션·수익률·차이·상태를 보존한다. 차이는 내부 minus 독립이며, 단위는 percentage point다.

| 연도 | 일치 세션 | 내부 수익률 % | 공식 가격·분배금 동일 식 % | 차이 pp | 상태 |
| --- | ---: | ---: | ---: | ---: | --- |
| 2013 | 247 | 2.244386 | — | — | INSUFFICIENT_DATA |
| 2014 | 245 | -5.472912 | — | — | INSUFFICIENT_DATA |
| 2015 | 248 | 1.400312 | — | — | INSUFFICIENT_DATA |
| 2016 | 246 | 12.759838 | — | — | INSUFFICIENT_DATA |
| 2017 | 243 | 30.307927 | — | — | INSUFFICIENT_DATA |
| 2018 | 244 | -15.368336 | — | — | INSUFFICIENT_DATA |
| 2019 | 246 | 17.307552 | — | — | INSUFFICIENT_DATA |
| 2020 | 248 | 38.956978 | — | — | INSUFFICIENT_DATA |
| 2021 | 248 | 5.339274 | — | — | INSUFFICIENT_DATA |
| 2022 | 246 | -22.272718 | -24.145912 | +1.873194 | FAIL |
| 2023 | 245 | 27.732661 | 24.844082 | +2.888579 | FAIL |
| 2024 | 244 | -7.222691 | -9.367773 | +2.145082 | FAIL |
| 2025 | 242 | 98.717700 | 94.235713 | +4.481987 | FAIL |
| 2026, cutoff까지 | 172 | 75.730462 | 74.410307 | +1.320155 | FAIL |

2013–2021은 시장가격 자체를 확인했지만 완전한 연간 공식 분배 이력이 없으므로 독립 총수익 칸을 비워 둔다. 필요한 평가 연도 2016–2026은 6개 이력 부족, 5개 FAIL이고 aggregate는 **FAIL**이다. 기준을 완화하거나 결측 지급액을 생성하지 않았다.

관측 원인은 ETF 분배 조정의 **추가 반영**이다. 공식 최근 20회 분배락의 시장가격과 네이버 값을 비교하면 네이버 값 자체에 이미 한 번의 분배금 조정 효과가 있다. 등록된 내부 값에는 그 위에 추가 효과가 있다. `datafeed._naver_range_frame` → `korea_prices.acquire` → `price_adjustment.to_total_return` 경로가 가격을 배당 미조정이라고 취급하고 Yahoo 분배금을 다시 반영하는 코드와 일치한다. 2026-07-30 예에서 공식 한 번의 factor는 1.002046476, 네이버/공식 raw 성장률 factor는 1.002012860, 내부/raw는 1.004067591이며 내부/네이버도 1.002050604다. 모든 20건의 숫자는 보고서에 남겼다.

고정 benchmark Close를 가져오는 함수가 actions 열을 버려 봉인된 benchmark corporate-event 행은 0개다. 이는 지급이 없었다는 뜻이 아니다. 원래 Yahoo의 benchmark 지급액·원가격을 전부 보존하지 않아 예전 acquisition을 바이트 단위로 완전히 분해할 수 없는 별도 추적성 한계다. 현재 네이버 캡처는 새 vintage이므로 원본을 대체하는 증거가 아니다. 개별 종목 가격의 동일 결함 여부는 이번 감사에서 시험하지 않았으며 benchmark 관측을 종목 전체로 확대하지 않는다.

## 전체 실입력 준비와 실행 안전성

[실입력 preflight 증거](audits/kr-alpha-atlas-phase-c-integrity/full-input-preflight.json)는 기존 `preflight.prepare(root, spec, None, work)`를 그대로 호출한 결과다. 별도 간이 행렬이나 목표 엔진은 없다. 원래 outcome firewall에 더해 목표·적합·통계·포트폴리오·formal permit·lock claim을 거부하는 장치를 적용했다.

검증한 층위는 actual main과 조상 관계, frozen 등록/113 dependency/235 protected hashes, source Git 객체 및 첫 행 schema, exact runtime, 달력과 maturity, 전체 입력 복원, matrix digest, PIT/결측 사유, StudyData 변환과 `validate_features`, 자원 및 immutable persistence probe다. 승인·잠금·실제 목표·성과·공식 결과 업로드는 검증 대상에서 제외한다. 합성 전체 연구는 별도의 기존 테스트에서 실행한다.

등록 및 실제 digest 모두 `32e49b57a7541eea66f76373baef50c6302a394247b313f6099f718d46d54b0c`다. 85,680행·76열·714일·260종목·후보 38개, 공시 기반 805,676셀 PIT 위반 0, 결측 1,542,935셀 사유 누락 0이다. 거래대금은 `PROXY_ASTRADED_CLOSE_X_VOLUME` 그대로다. 이전 Actions 원본 ZIP은 lineage이며 이번 실행의 필수 입력이 아니다.

Python 3.11.16 및 등록된 package/thread 설정에서 최종 감사 도구로 전체 준비가 통과했다. 측정 시간은 **1,001.518초**, 최대 RSS는 **1,742,995,456 bytes(약 1.62GiB)**였다. 호스트 memory capacity는 8GiB, 시작 시 가용 메모리는 약 4.34GiB·디스크는 약 3.80GiB였다. 이는 Debian 13 감사 호스트의 측정이며 GitHub Ubuntu runner에서 전체 준비를 실행했다고 주장하지 않는다. 전체 alpha 연구의 실행시간을 측정했다는 뜻도 아니다. 등록된 연구 예산 90분·8GiB·최대 예측 적합 574회와 Actions 110분 제한은 그대로다. formal 예산은 준비부터 측정되므로 준비 시간을 포함하며, workflow의 선행 테스트·설치 시간은 별도로 고려해야 한다.

B4의 약 44.3%는 **2016-04-01–2026-09-11 공통 usable range**의 완전 관측률이다. 해당 65,400행에서 **44.319571865%**를 재현했으며 등록 수치 44.319572%와 반올림까지 일치한다. 전체 2013–2026 행렬의 완전 관측률 33.829365079%와 분모가 다르다. preflight는 두 분모를 명시한다. 완전 관측 행만 남기는 새 정책은 없고, 등록된 훈련 전용 결측 대체·지표·척도와 비교별 동일 결과 mask를 유지한다.

one-shot 코드의 순서는 승인·actual main·spec/code·이전 결과/잠금 확인 → 입력 복원/identity/PIT/runtime/합성/기록 준비 → 영구 잠금 → 최초 역사 결과 접근 → 한 번의 연구 → 정확한 바이트 기록이다. 준비 단계의 Git·artifact·checksum·matrix·Python·dependency·메모리·시간·합성 실패는 잠금을 소비하지 않는다. API 첫 ref만 생성한 부분 실패, 잠금 상태 불명, 잠금 뒤 결과 기록 실패는 재실행 권한을 주지 않는다. 잠금 생성 두 요청 전체가 단일 transaction은 아니며 부분 생성도 보수적으로 소비된다. 이미 쓴 파일/로그만 복구하고, 강제 종료·OOM·artifact 업로드 실패 뒤 새 연구 실행은 금지된다.

이 실패들은 실제 ref를 만들지 않는 simulation 및 static inspection으로 확인한다. 로컬 출력은 audit 전용 파일에만 기록한다. Actions artifact는 정식 실행 후 90일 보존이므로 별도의 영구 exact-byte sealing을 완료해야 한다.

## CI 수정과 검토 결과

기존 [main Tests](https://github.com/jaehojung1879-netizen/Investment/actions/runs/37890444648)는 4,112 passed, 1 skipped, 4 xfailed였고 lint/import도 성공했다. [main Phase C validate](https://github.com/jaehojung1879-netizen/Investment/actions/runs/37891013772)는 등록/소스/달력 및 합성 24개 통과, execute와 결과 업로드는 SKIPPED다.

[Pages 실패](https://github.com/jaehojung1879-netizen/Investment/actions/runs/37890444650)의 14개 실패는 얕은 checkout과 누락된 고정 커밋/ancestry 문제였다. Pages에 `fetch-depth: 0`과 기존 Tests와 동일한 두 source commit fetch를 테스트 앞에 추가했다. 테스트를 제거하거나 봉인 identity/ancestry 검사를 약화하지 않았다. 거래/배포 로직·credentials·Phase C workflow는 수정하지 않았다. PR에서 Pages를 실제 배포하지 않으며, checkout 수정의 효과는 동일 입력을 가져오는 PR Tests와 설정 검증으로 확인한다.

새 감사 시험은 발명한 benchmark 경로, 0.005 경계, 현금·결측·동일 세션·cash coverage·cutoff, snapshot mutation, outcome/fit/lock 거부, immutable 기록, 준비 실패 9종 및 잠금 이후 실패 3종을 포함한다. CI에서는 실제 benchmark 수익률도 재계산하지 않고 snapshot의 opaque hash만 확인한다. 실제 benchmark 대조는 이 작업에서 명시적으로 허용된 별도 audit 명령으로 수행했다. 최종 pytest/lint/CI 기록은 PR 설명과 완료 보고에 남긴다.

감사 도구의 재현 명령은 다음과 같다. 등록된 Python 3.11.16 환경에서 감사용 requirements를 설치하고, `VERIFIED_MAIN_SHA`는 먼저 확인한 실제 main으로 바꾼다. `/tmp` 출력은 새 디렉터리·새 파일이어야 한다. 둘 다 정식 실행 명령이 아니며 승인·영구 잠금 생성 기능은 없다. benchmark 명령은 벤치마크 수익률 계산을 명시적으로 허용받은 감사에만 사용한다.

```bash
python -m pip install -r requirements-kr-alpha-atlas-integrity-audit.txt
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python scripts/audit_kr_alpha_atlas_preflight.py \
  --expected-main VERIFIED_MAIN_SHA --work /tmp/atlas-input-audit
python scripts/audit_kr_alpha_atlas_benchmark.py \
  --sources docs/audits/kr-alpha-atlas-phase-c-integrity/sources \
  --output /tmp/atlas-benchmark-audit.json
```

## 사람의 다음 결정

현재 `benchmarkIntegrity.claimGate=BLOCKED_UNVERIFIED`는 보존한다. 새로운 audit의 FAIL은 외부 증거이며 v1 JSON을 수정한 상태값이 아니다.

원래 v1은 **제한된 DEVELOPMENT 정보 평가**로 실행할 수 있다. 동일 날짜의 benchmark 상수 차감이 소거되는 순위·스프레드·날짜 중심화 목표와 동일 표본 대조는 여전히 의미가 있다. 개별·추가·조건부 근거와 차단 사유를 따로 공개한다. 다만 benchmark 파생 momentum·beta·시장 국면까지 온전한 시장 정보라고 주장할 수 없고 절대 경제 성과와 최종 투자 후보는 차단된다. 0 후보를 이유로 다시 실행하지 않는다.

검증된 경제 판단을 이 한 번의 최종 연구에 포함하려면 **별도의 명시적 사전결과 등록 개정 지시**가 먼저 필요하다. 다음을 검토해야 하며 이번 PR에서는 구현하지 않는다.

1. ETF 분배금의 중복 조정을 제거하는 정확한 benchmark basis와 완전한 독립 대조 이력. 현재 공식 지급 자료만으로 2016–2021을 검증했다고 주장할 수 없다.
2. 새 benchmark source identity·snapshot hash와 그 영향을 받는 PIT matrix digest. 원본으로 재명명하거나 기존 snapshot에 끼워 넣지 않는다.
3. 변경될 benchmark integrity/target-basis 설명, 필요한 source loader/preflight/검증 code 및 transitive manifest hashes. 후보·기간·모형·통계·비용·포트폴리오 문턱은 유지한다.
4. v1 JSON·sidecar·봉인 결과와 잠금을 그대로 남기는 versioned amendment 기록. 같은 연구의 기존 one-shot lock namespace를 유지해 원래 버전과 개정 버전의 이중 실행을 허용하지 않는다.

이 결정은 종목 alpha 결과가 한 번도 접근되지 않은 지금 할 수 있다. 모든 한국 과거 결과는 이미 노출된 DEVELOPMENT라는 분류도 바뀌지 않는다. 실제 실행 승인 파일은 지금 만들지 않는다. 사람이 현재 제한을 명시적으로 수용하거나 위 개정을 별도로 지시한 뒤, 소유자의 정확한 hash 승인 커밋과 main의 단 한 번 수동 execute가 이어져야 한다. 그때도 모든 preflight가 잠금 전에 다시 통과해야 한다. Phase D는 결과와 관계없이 한국 역사 탐색을 닫는다.

REGISTRATION_AMENDMENT_DECISION_REQUIRED
