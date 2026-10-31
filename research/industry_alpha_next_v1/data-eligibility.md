# 한국·미국 산업 데이터 적격성과 복구

현재 판정: **KR strict PIT / total-return industry model = BLOCKED;
US uniform dated sector panel / total-return model = BLOCKED.**
무료·합법 경로와 보존 원천을 우선한다. 신규 구독, 인증 우회, 무제한 재탐색을 요청하지 않는다.
접근 가능성과 보존·재사용 권한은 별도 필드로 확인한다.

## 증거 등급을 분리한다

행 계약은 security_id, issuer_id, share_class, market, taxonomy_id/version/level,
industry_id, valid_from/to, published_at, known_to, acquired_at, source_url,
raw_sha256, parser_version, identity_proof, evidence_class다. 공시 접수와 실제 효력은
별개이며 published_at < signal, valid_from ≤ signal < valid_to 모두 충족해야 한다.
획득 시각은 당시 공개의 증명이 아니다. 최초 분류와 정정본을 덮어쓰지 않는다.

| 등급 | 인정 범위 | 다음 연구에서의 사용 |
| --- | --- | --- |
| PIT_CONFIRMED | dated security/분류 수준/효력/당시 공개를 모두 증빙 | strict 후보 패널만 가능 |
| EVENT_RECONSTRUCTED | 전후 분류 연결은 있으나 과거 공개·시작점 증명 불충분 | 독립 기술 감사, strict와 풀링 금지 |
| STABLE_NO_CHANGE_INFERRED | 현재 앵커와 검색된 공지 부재로 역추론 | 재구성 개발 자료만 |
| CURRENT_ONLY | 현재 스냅샷 | 수집일 이후 전향 후보, 과거 소급 금지 |
| UNKNOWN_IDENTITY / UNKNOWN_CLASSIFICATION | 신원 단절 또는 분류 없음 | 원 모집단 분모에 유지, 임의 그룹/승계 금지 |
| UNKNOWN_TERMINAL_ECONOMICS | 합병·교환·분배 대가/가격 연결 불명 | 분류 유무와 무관하게 결과 경로 차단 |

과거 명칭의 VERIFIED_KRX_KIND_CHANGE_EVENT는 위 strict 등급의 동의어가 아니다.
v3의 demonstrably public 1,798 event name-date도 신원·분류 수준·기간까지 추가 검증해야 한다.
우선주를 보통주에 연결할 때 산업은 공유할 수 있어도 가격·배당·청산권은 별도다.

## KR: 숫자로 확인한 공백과 우선 복구

v4 상태 분포(전체 73,200 name-date): no-change 추론 54,173,
current anchor 7,558, event 7,076, 우선주 연결 949,
UNKNOWN 3,442 + UNKNOWN_IDENTITY_TERMINATED 2. 합계가 전체 분모와 일치한다.
종료 종목 name-date 2,345는 모두 미분류다. UNKNOWN 전체와 종료 분모는 겹치므로
더해서 결측 수로 보고하지 않는다. 신원 단절 횟수 22도 독립 종목 수와 구분한다.

1. 메타데이터에 열거된 종료 22증권과 미해결 우선주 005385/005387부터 **각각**
   identity / classification / terminal consideration / dividends / trading marks
   복구표를 만든다. 분류만 복구됐다고 지급액이 해결된 것으로 처리하지 않는다.
2. 보존된 DART 원본/정정 계보, KIND 변경·합병·상장폐지 공지와 거래소 자료를
   receipt/security 코드로 대조한다. successor 산업을 predecessor로 이식하지 않는다.
   원천에 있는 실제 교환비율·현금·효력일·권리 지급일·중단/재개를 별도 보존한다.
3. 기존 무료 공식 KRX/KIND 경로는 LOGOUT/403 또는 검색 폼만 수집된 실패 기록을
   먼저 재사용한다. 새로운 요청은 endpoint·정확한 대상·상한·권한·실패 보존·중단 조건을
   별도 source-only 계획으로 고정한 뒤 시행한다. 이번 PR에서는 새 KR probe를 하지 않는다.
4. 54,173 no-change 행은 이름 검색 부재를 역사 불변으로 인정하지 않는다. 공식 dated
   분류/독립 코드 기반 변경 목록으로 기간을 검증하거나 재구성 lane에 남긴다.
   미래 앵커를 끊어도 과거 strict 행이 바뀌지 않는 prefix test를 요구한다.
5. taxonomy/version/level을 먼저 동결한다. v4 crosswalk를 소급 수정하지 않는다.
   새 coarse taxonomy 필요 시 수익을 보지 않는 구조 감사로만 선택하고 새 ID에 등록한다.

수집/분류 복구만의 산출물은 산업×연도×유동성×증거등급의 full/known/missing 분모,
각 신원별 원천과 remaining blocker, 그룹 크기/유효 그룹 수, 상위1·2 비중/HHI,
구성 변경·중단·상장종료 수다. 회사명·현재 산업·현재 생존 여부로 표본을 줄이지 않는다.
Top120 밖 확대는 별도 자료·모집단 승인 없이는 하지 않는다.

## US: 가용 시점별 자료부터 시작

보존 `sp500-snapshot-sectors.json.gz` SHA
`f49c15a0ebcd371c9a407118abb6ef350bba2060227ca40d61ba210fc4f81a74`를 읽었다.
195 snapshots, 98,094 stored rows, collector failures 0이다. 이는 시점별 Git dataset
라벨이지 지수 제공자의 PIT GICS 인증 파일이 아니다. 동일 날짜에 여러 sourceCommit이
있으므로 `(date, sourceCommit, rawCsvSha256)`가 정체성이다.

**중요 스키마 발견:** 2023-03-07 / commit
`1271ae092ab591aaa98d0fb5950e5144f4d1ad73`의 `Sector`는 502행/123개 라벨이며
Semiconductors·Regional Banks·Industrial Conglomerates 등 세부 업종이다.
[고정 원본 CSV](https://github.com/datasets/s-and-p-500-companies/blob/1271ae092ab591aaa98d0fb5950e5144f4d1ad73/data/constituents.csv)의
header/행을 직접 대조했다. 다른 snapshot의 GICS Sector 11개와 그대로 합칠 수 없다.

전체에서 현재 11개 표준 섹터 어휘 밖 행은 30 snapshots/675행(그 중 공란 19행)이다.
여기에는 과거 Telecommunications Services 같은 **합법적 구 명칭도 포함**된다.
675행 모두가 오류라는 판정은 하지 않는다. 현재 어휘 비교는 스키마 경고일 뿐,
과거 분류를 현재 11개에 매핑한 결과가 아니다. 176/195 snapshots에
membersWithoutRow가 있고 BRK-B/BF-B 표기 연결 문제가 보인다. 누락 증권을
제거하거나 자동 점/하이픈 치환해서 해결했다고 하지 않는다.

복구 순서:

1. 보존 snapshot별 source column, level, taxonomy edition, 공개 커밋 시각,
   관측 공백/노후화, issuer/security/class identity를 확인한다. snapshot은 strictly
   prior 및 다음 지역 세션 이후에만 사용한다. stale snapshot을 exchange-effective로 부르지 않는다.
2. 2023-03-07 분류 수준 이상은 versioned codebook과 원래 upstream 근거가 확보될 때까지
   UNKNOWN_SCHEMA로 격리한다. 나머지 이름 변경도 시행일이 있는 crosswalk로만 처리한다.
   GICS 2016 부동산 분리·2018 communication 재편을 현재 소속으로 과거에 덮지 않는다.
3. 가용 sector만으로 시작하면 Study ID/대상 이름을 **sector selection**으로 제한한다.
   subindustry 모델은 아직 가용하다고 주장하지 않는다. 섹터 수준과 산업 수준 성과를 풀링하지 않는다.
4. SEC EDGAR 원본 header/SUB의 filing-date SIC는 무료 공식 대안이다. GICS와 다른
   taxonomy로 별도 검토한다. accepted 시각, accession, 당시 SIC, CIK→share class,
   13f/ADR/합병·delisted identity와 재사용 권한을 확인해야 한다. 기존 SEC 403 기록은
   먼저 읽고 bounded source 계획 없이 재시도하지 않는다.
5. 기존 합법적 entitlement가 입증된 historical GICS가 있으면 sample을 먼저 감사한다.
   데이터셋 광고만으로 READY로 만들지 않는다. 새 유료 구독은 요청하지 않는다.

기존 #287의 조건부 membershipIndustry는 공개 소급 재구성이며 위 strict 인증과 다르다.
rights, identity, returnBasis도 해당 연구에서 미해결이다. 본 PR은 그 코드를 수정하거나
승인 상태를 변경하지 않는다. Finnhub 공시의 filedDate/acceptedDate와 원정정 계보,
시총용 기말 shares(가중평균 shares 아님), delisting/distribution/분할 연쇄를 따로 감사한다.

## 결과 왜곡을 어떻게 측정할 것인가

이번에 측정한 것은 누락 **정도/위치와 기존 민감도**다. 신규 복구 전후의 산업 수익률
편향 크기는 **아직 미측정**이며 다음 역사 결과 승인 없이는 계산하지 않는다.

결과 접근 전 DQ 단계: 원 모집단 분모 고정 → 증거등급/기업행동 결측의
산업별 수·cap 비중·유동성 비중, eligible-group 손실, exposure/coverage 차이,
행 다대다 join/중복·빈티지 역전·taxonomy 혼합 검사. 산업이 모르는 UNKNOWN의
산업별 실제 배치는 추정하지 않고, 각 산업에 배치될 수 있는 최소/최대 구성원·cap
노출 범위만 보수적으로 공개한다. 현재 산업으로 배분하는 것은 금지한다.

결과 승인 후에만: 신호 시점에 동결한 동일 intended population에 대해
strict vs reconstructed, 원본 vs 별도 repaired input의 공통 유효 결과 비교와
전체 intended 결과 차단률을 함께 낸다. 산업 수익/IC/오차/순경제의 paired 변화,
산업별·연도별 attrition을 보존한다. missing consideration을 0, 마지막 가격, survivor
renormalization으로 채우지 않는다. 근거 없는 payoff에 유한 편향 bound를 만들지 않는다.
분류 불명 배치 시나리오는 가정 범위의 민감도이며 편향 교정치가 아니다.

## 수익·유동성·생존편향의 공통 출구 조건

각 지역 full intended universe, 신호일 구성원 수(최소5), 그룹 최소8, EW/CW 양쪽
coverage와 group drop 이유를 공개한다. ADV60은 as-traded 종가×거래량 proxy와
공식 거래대금을 구분한다. 분할조정 지수×거래량을 통화 거래대금으로 쓰지 않는다.
free-float 근거 없으면 issue-cap proxy라 부른다. 동일 issuer의 복수 share class는
issuer concentration도 따로 낸다.

주주 총수익 판정은 모든 구성원의 현금·주식 배당/분할·권리/스핀오프/합병 대가와
동일 기준 benchmark까지 통과해야 한다. PRICE_RETURN 진단은 별도 라벨·별도 동기화된
benchmark를 쓴다. 부분 분배 구성원을 합쳐 TOTAL_RETURN이라 부르지 않는다.
선택은 결과 유효성을 보기 전에 고정한다. 한 selected name/required peer가
미해결이면 해당 경로와 짝 비교를 차단하며 더 좋은 다음 종목으로 교체하지 않는다.
