# 미국 이탈 식별자 공개 가격 복구 v1

기준 main `0a9fb1d96219f4402d9eb341cabbb616f786e52d`. 원본 감사의 **212개 noPanel 식별자**를 그대로 사용했다. 212개 모두가 법적으로 상장폐지된 종목이라는 뜻은 아니다. 이 작업은 실제 공개 원자료 수집과 가격 관측 존재 감사이며 P4·H63 forward return·IC·전략 성과를 계산하지 않았다.

## 실제 확보 결과

- Source A **175/175 CSV** 실제 다운로드. 전체 공개 아카이브에서 **193개 식별자, 409개 출처별 가격 파일, 993,392행** 확보. 비교용 5개 종목 × 5개 출처 25파일은 이 수치에서 제외했다.
- FULL **5**, PARTIAL **170**, NONE **37**. FULL은 관측된 회원 기간의 모든 세션에 양의 종가가 있다는 뜻이며 연구 준비 완료를 뜻하지 않는다.
- 회원 기간의 결측 **256,402세션 → 69,492세션**. 186,910세션(72.90%)에 후보 가격 관측을 확보했다. 출처별 중복을 포함한 별도 후보 패널은 **268,041행**이다.
- 모든 raw 후보 날짜: **1970-01-02–2023-10-10**. 이름·회원기간을 통과한 관측: **2013-01-02–2023-03-27**. **2024–2026 관측 개선은 0**이다.
- 기업명/시기를 상호 확인한 후보 175개이며 영구 security ID/CIK 기반 완전 검증으로 주장하지 않는다. 파일명 일치 193개와 구분한다.

## 연도별 결측률

분모와 before는 봉인 감사의 주간 member-date를 정확히 재현한다. after는 같은 날짜에 후보 양의 종가가 없는 비율이다. 기존 패널의 기타 결측이나 총수익률·20일 volume gate까지 해결됐다는 뜻은 아니다. 일별 회원 세션 수와 OHLCV 지원 수는 JSON에 별도로 보존했다.

| 연도 | before | 후보 after | 회복 주간 member-date |
|---|---:|---:|---:|
| 2013 | 30.3231% | 8.8923% | 5,572 |
| 2014 | 28.4539% | 2.8646% | 6,655 |
| 2015 | 26.8223% | 2.8258% | 6,301 |
| 2016 | 22.4769% | 1.5112% | 5,480 |
| 2017 | 20.2126% | 2.5447% | 4,638 |
| 2018 | 17.7723% | 8.0503% | 2,553 |
| 2019 | 17.0297% | 8.3168% | 2,288 |
| 2020 | 12.9199% | 4.8123% | 2,170 |
| 2021 | 9.1203% | 3.7357% | 1,414 |
| 2022 | 8.6374% | 3.2447% | 1,416 |
| 2023 | 4.1260% | 3.1165% | 264 |
| 2024 | 2.8715% | 2.8715% | 0 |
| 2025 | 1.7932% | 1.7932% | 0 |
| 2026 | 0.5374% | 0.5374% | 0 |

## 출처와 검증

| 출처 | 파일 | 원자료 행 | 해석 |
|---|---:|---:|---|
| A | 175 | 150,510 | 조정 OHLCV 의도, WIKI 우선/Yahoo fallback; 원래 배당·분할 필드 삭제 |
| D | 60 | 8,525 | 2020 Yahoo OHLCV + 별도 Adj Close, 당시 기업명 목록 있음 |
| E | 31 | 113,187 | 2023-03-27까지 Yahoo 종가, 2자리 반올림; OHLCV 없음 |
| F | 55 | 237,211 | Yahoo OHLCV/Adj Close, 2000–2020 자료 포함 |
| G | 88 | 483,959 | 일부 2023-10-10까지 숫자 행. 원공급자/조정 기준 미확인: 커버리지 개선 수치에서 제외 |

정확한 URL·Git revision·SHA-256·취득 UTC 시각은 파일별 JSON acquisition에 있다. 실제 컬럼·최초/최후 세션·행 수·기대 세션·gap·duplicate·가격/volume 오류를 모두 기록했다. 누락 volume은 None이며 0으로 만들지 않는다. 중복 날짜는 격리하고 OHLC 모순/비거래일/비양수 가격을 세션 개선에서 제외한다. LIFE/WLP의 slash dates는 파일에 day>12인 증거가 있어 US MDY로 명시 처리했고, LIFE는 회원 기간 이후의 다른 역사여서 복구에서 제외했다.

회원 기간은 195개 dated snapshot의 strictly-earlier 규칙이다. 45일 초과 공백 21개, 최대 769일의 기존 한계를 그대로 공개한다. 권위 있는 실제 index 편입/제외 effective date라는 뜻이 아니다. 각 행에 독립 audit security key, 원래 ticker, 모든 dated 역사 이름/확인된 CIK, 각 회원 episode, 필요 가격 기간, 재사용 flag, 검증 상태를 기록했다. 서로 다른 ticker/share class를 합치지 않았다.

CA/CDAY/DV/HAR/HOT/JCP/RDC의 명시적 기업명 약칭 대응은 코드의 고정 NAME_ALIASES와 JSON에 공개한다. 다른 ticker의 가격을 이어 붙이는 rename join이 아니다. DeVry/LIFE처럼 회원 기간 이후의 이력은 이름이 맞아도 계속 차단됐다.

AAPL/MSFT/AMZN/JNJ/XOM의 6,014개 겹치는 세션을 archived Yahoo Adj Close 및 기존 봉인 Yahoo total-return **가격 수준**과 각각 교차 확인했다. 동일 날짜 비율을 고정 scale로 비교했으며, 시간차 수익률은 계산하지 않았다. 5개 모두 상대 비율 편차 p95≤1%였지만 Source A의 Yahoo fallback 때문에 독립 공급자 검증이 완전히 증명된 것은 아니다. 이 비교는 가격 연속성 확인이며 새 총수익률 만들기/혼합 허가는 아니다.

## 접근 차단과 남은 식별자

Nasdaq WIKI의 공개 카탈로그 mirror는 실제 3,194행(사용자 언급 3,199행과 다른 보존 버전), 191 ticker match였다. 175 Source A 후보는 이 안에 있다. **카탈로그는 가격 복구가 아니다.** 직접 Nasdaq API, Wayback CDX(CTXS), Stooq는 각각 프록시 CONNECT 403에서 멈췄다. 공급자 HTTP 응답/유료 entitlement로 오해하지 않았다. Nasdaq key 변수들은 없지만 API에 도달하지 못했으므로 key 필요 여부 자체는 NOT_MEASURED다. Wayback scraper는 실행하지 않았고 차단 후 다른 경로로 우회하지 않았다. 이미 유료인 것으로 입증된 다른 공급자는 재탐색하지 않았다.

추가 보충수집으로 2018–2023 관측을 실제 얻었으며 2024–2026 무료 수집 성공은 주장하지 않는다.

**NONE 37개:** ACT, AGN, ANDV, ANR, BHGE, BIG, BMC, BTU, CBE, CHK, CPGX, CTRA, CVH, DAY, DV, DWDP, FII, GCI, HNZ, IGT, JDSU, KFT, LIFE, LTD, LXK, MHP, MOLX, NE, NYX, PCS, RRD, S, SAI, SHLD, TIE, WPI, WPO.

**entity/share-class 검증 hold:** AGN, BTU, CHK, CTRA, GCI, IGT, NE, S. 그 밖의 NONE은 원자료 부재, 기업명 불명확(ANDV/BHGE/DWDP의 Untitled 카탈로그 등), 후기 다른 ticker 역사, 회원기간 불일치 또는 G upstream 불명확이다. 세부 원인은 식별자별 JSON에 있다.

기업 행동 lineage와 원주식 기준/terminal-consideration 판정은 212개 모두 아직 미해결/미분류다. 이것이 212개 실제 delisting event라는 주장은 아니다. split/dividend가 보고되지 않은 것을 0으로 가정하지 않았고 매수기업 가격·마지막 가격·0으로 종료를 채우지 않았다. 가격 FULL 5개는 ABMD, ADS, ENDP, FBHS, JWN이며 이것도 종료 대가나 H63 가격 준비 판정이 아니다.

## 별도 후보 저장소와 재현

공개 PR에는 **원자료와 세션별 파생 가격 payload를 포함하지 않는다**. 기존 두 커밋을 대체하여 PR 브랜치의 전체 제안 이력에서도 압축 파일을 제거한다. `candidate_data/us-departed-public-price-v1/manifest.json`에는 기존 파일명·바이트 수·SHA-256·측정 수치만 남긴다. 공개 감사 JSON의 수치는 이미 수행한 실제 취득 결과이며 최종 CI가 실자료를 다시 다운로드했다는 뜻이 아니다.

원자료 21,264,444바이트와 파생 패널 6,834,898바이트 및 원래 Git bundle은 checkout 외부 접근 제한 로컬 보존 경로에 SHA 확인 후 유지했다. **이 작업 공간은 영구 보관소가 아니며 소유자 통제 비공개 저장소는 아직 만들지 않았다.** 공개 URL은 사라지거나 접근이 차단될 수 있어 동일 바이트 재수집을 보장하지 않는다. 영구 보존 전에는 공개 checkout만으로 기존 실자료 무결성 검증/감사를 재현할 수 없다.

아래 감사는 별도 보관 파일을 소유자가 확보하고 manifest SHA와 대조한 뒤 checkout 외부 staging에 안전하게 복원했을 때 실행한다. 재수집 코드는 유지하되 원자료·파생 출력 모두 Git checkout 안으로 저장하지 못하게 차단한다.

```bash
python scripts/audit_us_departed_public_prices.py --raw-root /tmp/us-public-recovery --report /tmp/reproduced-audit.json --candidate-panel /tmp/reproduced-panel.json.gz
python scripts/acquire_us_departed_public_prices.py --plan docs/us-readiness/us-departed-public-price-recovery-v1.json --stage /tmp/fresh-us-public-acquisition --source A --budget 175
```

재수집은 pin된 GitHub raw URL만 허용하고 sequential pacing 0.2초, 요청 500개/파일 5MiB 한도와 10/25초 timeout, 401/403/429/5xx 즉시 정지, retry 없음이다. 기대 SHA와 다르면 새 바이트를 보존하되 revisionMismatch로 멈춘다. 실제 최초 수집은 CSV 434호출(controls 포함), 총 243.98초였고 Source A 180호출 중 요청한 departed CSV는 175개다.

## 연구 데이터 migration 계획

이번 개선은 **새 후보 역사 데이터셋을 만드는 근거로 충분히 유용**하다. 그러나 새 역사 연구를 실행할 준비 상태는 아니다.

1. 가격이 있으나 영구 ID/기업 행동이 애매한 security episode를 issuer·share-class 증거로 분리하고 37 NONE을 계속 추적한다.
2. 각 공급자의 원조정 basis/원거래 OHLCV와 event lineage를 확보한다. 특히 A 조정 가격에 배당·분할을 두 번 적용하지 않고 E의 unpinned default/rounded Close 및 volume 부재를 해결한다.
3. delisting 여부와 merger/bankruptcy/share exchange/cash consideration을 증거로 분류한다. 후기 index 이탈을 자동으로 delisting으로 처리하지 않는다.
4. 새 candidate revision을 새 content-addressed input manifest로 별도 검증하고 원래 규칙으로 outcome-blind missingness를 다시 감사한다. 2024–2026 개선 0, informative missingness, stale membership를 남긴다.
5. 원본 v3/replay-v16, signal-history, H63 protocol/결과/lock/기존 14개 P4 identities를 수정하지 않는다. **현재 P4는 이 후보를 사용하지 않는다.** 새 입력을 쓰려면 별도 데이터 리뷰와 새 연구 등록/owner 승인이 필요하다.
6. [재배포 권리 감사](us-departed-price-redistribution-v1-ko.md)에 따라 모든 출처의 원자료·파생 가격 재배포는 UNVERIFIED다. 소유자는 비공개 영구 보존을 먼저 승인하고 원공급자 이용·저장·연구 권리를 확인해야 한다. 권리 확인 전 공개 데이터셋 배포는 차단한다.

## 검증 및 운영 차단

Ruff/compileall, focused recovery/P4/v3/survivorship tests 117개, 모든 pipeline import/script compile, 격리 seed 생성·검증 및 production seed 거부를 확인했다. 최종 전체 pytest/CI 상태는 PR 본문 또는 최종 보고에서 실제 실행 결과로 제공한다.

기준 main의 Tests run 38469867192는 실패였다. 병합된 P4 guard가 들어간 main baseline을 두 번 제거하는 비교 테스트 문제를 로컬에서 재현했다. `tests/test_us_p4_execution.py`의 기준값 처리만 교정했고 원래 workflow/조건/steps·과학 정의는 그대로다.

준비 과정에서 일부 GitHub GET 요청이 CONNECT 403으로 거부됐고 api.github.com / data.nasdaq.com / web.archive.org / stooq.com의 허용 초안을 저장했다. 이후 정상 gh PR API로 Draft #241 생성에 성공했으므로 GitHub 전체 접근 불가로 단정하지 않는다. Nasdaq·Wayback·Stooq는 원래 차단 기록이 남아 있고, 초안 저장은 환경 적용/Publish를 뜻하지 않는다. 네트워크 우회/승인 발급/실제 연구 실행은 하지 않는다.
