# Investment 경제 충격 원천 연구

- [S2 결과](REPORT-ko.md)
- [S1 원본 보고서](s1/REPORT-ko.md) · [S1 원본 ZIP](s1/Investment-network-pilot.zip)
- [원천과 이용 조건](NOTICE-ko.md) · [원천 매니페스트](data/source_manifest.json)

## 확인할 파일

| 파일 | 단위 |
|---|---|
| [FDA 사건](data/fda_event_census.csv.gz) · [FDA 제품 연결](data/fda_product_crosswalk.csv.gz) | 2019~2025 도메인별 FDA 사건 ID, 제품 회수번호 및 의료기기 코드·시설·허가 |
| [Class I 후보](data/fda_device_class_i.csv) · [사전 기업 연결](data/fda_issuer_exposure.csv) · [조치 문구](data/fda_action_cues.csv) | 의료기기 사건과 공통 원인 후보군, EDGAR 접수시각, 제품 임시 조인 및 우선 심사 대상 |
| [경로 검토](data/audited_shock_routes.csv) · [BLS 91개](data/bls_event_first_91.csv) · [SEC 8-K](data/sec_event_sources.csv) | 실제 사건 자료와 공지·발생일, 확인된 적용 범위와 대체 근거 |
| [USAspending 거래](data/usa_oct2024_transactions.csv.gz) · [해지 후보](data/usa_termination_candidates.csv) · [DoD 예시 계약](data/usa_example_award_history.csv) | 거래 ID와 계약 ID 및 조치일, 보고일, 의무액과 옵션, 별도 한 계약의 반복 거래 |
| [FDA 의약품 부족](data/fda_drug_shortage_listings.csv) | 현재 스냅샷의 성분·포장·회사별 행 |
| [FDA 집계](data/fda_metrics.json) · [기업 연결 집계](data/issuer_metrics.json) · [조치 집계](data/fda_actions_metrics.json) · [계약 집계](data/usa_metrics.json) | 결과 파일과 대응하는 표본·결측·중복 계수 |

## 재현

자료로 확인할 때는 이 디렉터리에서 `python scripts/verify.py`를 실행하면 됩니다. 외부 요청 없이 기존 원본 ZIP 해시, FDA 제품→사건 키, 90일 전 제품 및 사건 전 SEC 접수, 계약 거래 수와 날짜 비교, 공통 기점 표기를 확인합니다.

원천에서 변환을 다시 하려면 이 디렉터리의 복사본에서 `raw/`와 `build/`를 만들고 Python 3.11 이상, `ijson`, `lxml`을 사용합니다. `data/source_manifest.json`의 경로·URL·POST 요청·SHA-256과 배포 판본을 따릅니다. 최신 FDA URL과 USAspending 주문형 ZIP은 언제든 갱신 또는 만료될 수 있습니다. 새로운 응답의 해시는 새 관측으로 남깁니다. EDGAR 연차공시는 공개 원문 URL·접수번호·문서 역할로 식별합니다. 원본 EDGAR 파일 목록은 [취득된 연차공시 인덱스](data/edgar_annual_filing_index.json)에 있습니다.

- `scripts/acquire_fda.py`는 공식 다운로드 인덱스의 사전 저장본을 읽습니다. `scripts/fda_census.py`는 ZIP을 스트리밍하여 사건과 제품을 다시 계산합니다. `scripts/issuer_join.py`는 `raw/edgar/manifest.json`과 공시 원본으로 기업 노출을 연결합니다. `scripts/screen_fda_actions.py`는 조치 문구를 검토합니다. `scripts/acquire_edgar.py`는 현재 메타데이터에서 같은 절차를 다시 수행하는 취득 코드입니다.
- `scripts/usa_bulk.py`는 기록된 3개 정부 부서 범위에서 다운로드를 재요청합니다. `scripts/procurement_census.py`는 해당 ZIP 및 매니페스트에 기록된 DoD 예시 POST 응답을 처리합니다. `scripts/official_examples.py`와 `scripts/add_cases.py`는 공시·기관 원문을 받고, `scripts/cases.py`는 사례 판독과 S1의 보존 BLS 표를 사용합니다.
- 이 디렉터리의 파일은 원천 심사용입니다. 실제 역사 검정·전향 운용은 별도 승인 경로에 속합니다.

로컬 검산은 자료의 식별자·수치·고정 원본과 연구 스크립트를 대상으로 했습니다. 독립 검토와 저장소 전체 CI를 의미하지 않습니다.
