# S4 · 시장구조 식별 연구

2026-11-27 KST · `market-structure-discovery-s4-v1` · `EXPLORATORY` · `AUTHOR_VALIDATION_ONLY`

**관측한 것은 걸프 연안의 정유 투입 감소, 지역별 휘발유 재고 변화, 그리고 두 폭풍 뒤 실제 설비 중단입니다.** 2010–2025년 공식 계열에서 걸프 연안 허리케인 13개를 찾았습니다. 날짜가 가까운 폭풍을 묶으면 9개 후보 군집이고, DOE가 정유소 중단 규모를 확인한 군집은 2개입니다. 폭풍이 가격을 통해 생산에 미친 효과, 정유 중단이 동부에 미친 순효과, 6–12개월 투자 우위는 이 관측으로 식별되지 않습니다. **판정은 원천 심사 `KEEP`, 전달효과 `INCONCLUSIVE`입니다.** [수치와 재현 코드](results/diagnostics.json) · [다음 실험](EXPERIMENT-ko.md)

## 연구 범례와 범위

| 표기 | 근거의 범위 |
| --- | --- |
| `EXPLORATORY` | 확보한 공식 원천에서 실측 또는 출처 간 대조. 개발 단계의 기간·지역·사건 선택과 현재 빈티지를 포함합니다. |
| `MATHEMATICAL` | 명시된 가정에서 성립하는 식, 상·하한 또는 반례. 실제 관측값을 대입해도 숨은 상태는 예시입니다. |
| `HYPOTHESIS` | 필요한 추가 자료와 기각 조건이 있는 경쟁 설명. |
| `REPACKAGED_DUPLICATE` | 기존과 관측변수, 메커니즘, 대상·기간, 검증이 실질적으로 같은 제안. |
| `SOURCE_BLOCKED` / `NOT_EXECUTED` | 전자는 필요한 자료·단위·빈티지·적격성의 공백, 후자는 실제 분석 또는 실행이 이루어지지 않은 상태입니다. |

#292 [작업 선언](https://github.com/jaehojung1879-netizen/Investment/issues/292#issuecomment-7209052551), main `3150c70017432e3b73321fbda47ebea226bf8d2b`, root / research `AGENTS.md` 및 공통 연구 계약을 적용했습니다. [Evidence Registry](https://github.com/jaehojung1879-netizen/Investment/blob/3150c70017432e3b73321fbda47ebea226bf8d2b/research/next_alpha_program_v1/EVIDENCE-MAP-ko.md)와 [#376 통합 계보](https://github.com/jaehojung1879-netizen/Investment/blob/3150c70017432e3b73321fbda47ebea226bf8d2b/research/research_integration_audit_20261124/REPORT-ko.md), [#343–369의 실제 PR HEAD 27개](results/pr-lineage.json)를 대조했습니다. 기존 원장 보호 범위에 따라 S4 등록 기록은 이 문서에 둡니다. S4 계산의 입력은 공개 경제·기상 관측입니다.

## 기존 원천의 적격 대사

| 원천·HEAD | 변수, 단위, 시점 및 적격성 |
| --- | --- |
| S1 네트워크와 후속 사건 발굴 `f223c1c7` | S1의 BEA Use 및 OECD ICIO는 **상품/국가·산업×사용산업**의 화폐 흐름을 산출액으로 나눈 투입 비중입니다. 수정 표의 기준년·판본과 당시 발행 시각을 별개로 봅니다. 산업 비중에는 기업별 계약량과 고정자본이 빠집니다. SEC/DART/IR 공시는 법인/제품/시설·보고기간, 접수 또는 보도 시계로 경로를 확인할 수 있지만 비공개 배분량이 남습니다. Southwest 737 사례는 산업 중간투입과 설치기반 노출이 다른 사례입니다. |
| S1 사건 발굴 후속 `f223c1c7` | FDA 제품 기록 37,641개 → 도메인×사건 ID 12,056개. 의료기기 Class I ID 561개 중 목록 날짜 508개. 사건 전 법인·510(k) 조인 군집 66개, 법인명까지 같으면 45개, 최대 한 발행인 20개. 승인번호는 미국 허가 이력이고 가동용량·실제 대체량 단위가 없습니다. Philips ID 2개는 같은 제조 원인입니다. BLS 91개는 분쟁 에피소드의 후보이며 시작일이 첫 새 소식일인지는 별도입니다. USAspending의 USD 의무액·수정은 실제 출하·매출과 구별합니다. |
| S2 #384 `46f181f4` | S&P DJI 발표 날짜 178개, 효력 날짜 190개. 공지(ET)·효력일·ETF 표의 기준일을 분리합니다. ETF 공시의 CU당 수량·원화 평가액·비중으로 실제 강제 주문의 방향/크기를 관측하려면 지수 공지·AUM·실제 플로가 필요합니다. KOSPI200 정기변경 확인 0, KOSDAQ150 5. KOFIA 신용·반대매매는 시장 전체 일별 백만원 자료입니다. 135개 피크 일자를 46개 에피소드로 묶었으나 동시 가격 하락·담보 변화로 외생성이 부족합니다. Fed Z.1 F.223은 분기 계절조정 연율의 현재 판본입니다. 분기 자금량과 일별 강제 주문을 조인하지 않습니다. |
| S3 `17a9514e` | 경제 변화 16행, 법적 발행인 6개, 최초 공개 검증 0/16. 삼성 메모리 1Gb 환산 패키지 물량과 100% 보고 가동률에서 역산한 능력은 독립 설비 관측 하나를 더하지 않습니다. USB 과세등가 NIM(%)과 연결 순이익(USD)은 정의·기간을 맞춰도 인과 방향이 다릅니다. 최신 독립 평가 `DESIGN_ONLY`의 100개 기업군은 목표입니다. SPF·WASDE 전망 4개 빈티지는 서로 다른 해소 키 2개입니다. |
| 최신 이전 연구 | #343–353은 종목 선택, 보유·ETF 노출, 공시·자금 정보와 데이터 계보를 다룹니다. #354–356은 기대·실적 시계와 설비·산업 원공표를 구분합니다. #357–359·#364는 가격 기반 밸류에이션/거시 조절과 봉인·비용입니다. #360은 수출·산업 최초공표, #361은 시장 인과 전달입니다. #362–367은 시장위험 사건화·독립성·기준선, #368–369는 시장 충격과 국면 의존성의 기록입니다. 새 정유 자료는 기존 종목·ETF 사건이나 라벨에 조인하지 않았습니다. |

[S1 원 연구](https://github.com/jaehojung1879-netizen/Investment/blob/f223c1c7d8c841500ea99b2caadeaa72f7a0cce7/research/economic_network_event_first_v1/s1/REPORT-ko.md) · [S1 사건 발굴 후속](https://github.com/jaehojung1879-netizen/Investment/blob/f223c1c7d8c841500ea99b2caadeaa72f7a0cce7/research/economic_network_event_first_v1/REPORT-ko.md) · [#384 데이터 노트](https://github.com/jaehojung1879-netizen/Investment/blob/46f181f4c75c4fe0e273fcb288feaebbea24dd12/research/market_structure_discovery_s2/DATA-NOTES-ko.md) · [S3 최신 평가 설계](https://github.com/jaehojung1879-netizen/Investment/blob/17a9514e06cefd5176cc2a6c05453f003f4e9c17/research/market_structure_discovery_s3/independent_evaluation_v1/PROTOCOL-ko.md) · [기계 대사](results/prior-source-audit.json)

| `REPACKAGED_DUPLICATE` | 이유 |
| --- | --- |
| 기존 밸류에이션·신용·거시 변수의 새 점수나 기호식으로 시장 상태/ETF 성과 재검정 | #357–359·#361–369와 변수 및 대상이 같습니다. 기저율, 사건 독립성, 공표 시점 문제도 그대로 남습니다. |
| 설비투자·수출·산업 추세에 비선형 회귀나 SINDy만 추가 | #355·#356·#360의 공표량과 추세에 독립 제조능력·재고·대체량이 추가되지 않습니다. |
| 같은 공시의 재무/AI 해석 경쟁, 같은 목표의 전망 빈티지 추가, 단일 역DCF 격자 | S3 및 #383의 관측 구조입니다. S4의 차이는 외부 물리 보조 관측과, 독립 물리 제약이 부과됐을 때의 공동 가능집합 검정입니다. |
| 기존 FDA 사건을 제품 행마다 세거나 같은 네트워크 특성에 새 전달 점수를 붙임 | S1이 이미 공통 기점, 고정자본 교체·병목과 회사 경로를 다뤘습니다. 공장별 시간·용량이나 제품의 호환성 측정 없이 실질적 증분이 없습니다. |
| S&P/KOSPI 편입·반대매매 피크에 가격 예측기를 적용 | S2와 같은 거래 이벤트이며, 실제 강제 주문·계약별 바인딩·새 독립 대조군이 추가되지 않습니다. |

## EXPLORATORY · 정유 공급과 지역 재고

| 관측 | 원천·단위·시점 |
| --- | --- |
| 금요일 종료 주간의 정유소 상압증류 총 투입 | `WGIRIP32` 걸프 연안(PADD 3), `WGIRIP22` 중서부(PADD 2), `WGIRIP42` 로키산맥(PADD 4). 천 배럴/일. 원유 순투입과 구별합니다. WPSR 주간 추계의 관측일과 다음 공개일은 다릅니다. |
| 지역 총 휘발유 기말 재고 | `WGTSTP31` 걸프, `WGTSTP11` 동부(PADD 1), 금요일 천 배럴. 완제품과 혼합재의 집계라 즉시 판매·이동 가능한 제품별 재고는 보이지 않습니다. |
| 일반 휘발유 표본 소매가격 | `EMM_EPMR_PTE_R30_DPG` 걸프, `EMM_EPMR_PTE_R10_DPG` 동부, 달러/갤런. 월요일 현지 08:00 관측, 2018년 표본 개편, 2025-04부터 화요일 공개 일정. 상품의 관측 가격이며 기업가치나 할인율은 입력에 없습니다. |
| 걸프→동부 실제 수취 물량 | `MBCMXP1P31` 혼합재와 `MGFMXP1P31` 완제품, 천 배럴/월. 원 계열 제목은 파이프라인·유조선·바지선을 합친 수취입니다. 월 합계로 주간·시설·운송수단을 역산할 수 없습니다. |
| 기상과 물리적 중단 | NOAA IBTrACS v4r01 북대서양 `USA_RECORD=L` 및 `USA_STATUS=HU`, USA 최적경로의 시각 UTC, 풍속 knot, 위치 위·경도. DOE 보고의 닫힌 정유소 수·명목 중단용량(천 배럴/일)과 보고 시각. 기상 재분석·출처 공표·시설 실제 중단은 서로 다른 시계입니다. |

[원본 XLS/PDF, NOAA 원본의 투영 사본 및 해시](data/source-manifest.json) · [EIA WPSR](https://www.eia.gov/petroleum/supply/weekly/) · [가격 조사 방식](https://www.eia.gov/petroleum/gasdiesel/gas_proc-methods.php) · [월간 수취 원표](https://www.eia.gov/dnav/pet/pet_move_ptb_dc_R10-R30_mbbl_m.htm) · [EIA 이용 조건](https://www.eia.gov/about/copyrights_reuse.php) · [NOAA IBTrACS v4r01](https://doi.org/10.25921/82ty-9e16)

2010–2025 주간 7개 계열은 각 835개, 월간 2개는 각 192개입니다. 예상 일자 결측·중복은 없었습니다. NOAA는 북대서양 상륙 249행에서 본경로·허리케인·경위도 상자(25.4–31.2°N, 98–87°W)로 17행이 남았습니다. 이 상자는 걸프 연안의 탐색 기준이며 행정 경계, 풍해 투영이나 정유소 피격 기준은 아닙니다. ATCF ID로 13개를 세고, 인접 시작일이 28일 이내인 폭풍을 연쇄로 합쳤습니다. 14/28/42/56일에서 군집 수는 각각 13/9/8/7입니다. 9개 군집의 첫 폭풍에 대해 상륙 UTC 날짜보다 엄격히 뒤인 첫 금요일을 t0로 두었습니다. 주간 평균이나 가격 인과 효과에 상륙한 시각을 분 단위로 배분하지 않았습니다. 이미 폭풍을 예상한 사전 감산과 동일 계절의 공유 위험이 남습니다. [후보 사건 목록, 날짜 총계 및 경로](results/diagnostics.json)

| 관측 | Harvey 2017 | Ida 2021 |
| --- | ---: | ---: |
| 걸프 정유 총 투입, 전주 → t0(백만 배럴/일) | 9.358 → 6.178 (−34.0%) | 9.007 → 7.381 (−18.1%) |
| 중서부 / 로키 정유 총 투입, 전주 대비 | −0.05% / −0.29% | −5.77% / −1.11% |
| 걸프 / 동부 휘발유 재고 변화(백만 배럴) | −0.060 / −2.230 | −3.156 / −3.582 |
| 걸프 소매가, 직전·이후 두 월요일(USD/gal) | 2.118 → 2.156 → 2.506 | 2.803 → 2.774 → 2.826 |
| DOE에서 확인한 중단 | 9월 9일 14:00 EDT, 5곳·1.0693백만 b/d | 9월 2일자, 루이지애나 7곳·약 1.7백만 b/d |

두 사건의 첫 발표 WPSR PDF(2017-09-07, 2021-09-09)와 현 XLS에서 3지역×2개 기준 주×2발표의 **12/12 값이 일치**했습니다. 이전 주 값도 두 PDF의 비교열에 포함되어 있습니다. 해당 여섯 개 최초 공개값은 확인했으며 다른 후보 주나 재고·소매가격의 최초 공개는 검증하지 않았습니다. DOE의 중단은 물리적 공급 경로의 존재를 확인합니다. 보고 시각의 정지 설비 합계는 EIA 주간 가동 감소분의 원인별 기여도와 일대일로 대응하지 않습니다. [공개 표와 대사표](data/document-crosscheck.json) · [DOE Harvey](data/doe-harvey-24.pdf) · [DOE Ida](data/doe-ida-5.pdf)

- **실제 전달 경로의 관측 범위.** Harvey 직후 걸프 휘발유 재고가 거의 유지되어도 동부 재고는 223만 배럴 줄었습니다. EIA는 Colonial 운송 감소와 일부 중단을 기록했습니다. 걸프→동부 혼합재 수취는 2017년 8월 54.265 → 9월 46.432백만 배럴, 완제품은 6.103 → 4.359였습니다. Ida 시기 혼합재는 57.203 → 54.931, 완제품은 1.880 → 2.188로 방향이 갈렸습니다. 월말에 상륙한 사건이라 8월·9월 차이에는 노출 일수, 대체 운송, 수요, 정기보수와 이후 사건이 섞입니다. 동부와 중서부는 연결 시장이므로 깨끗한 비처리군으로 쓸 수 없습니다. [EIA Harvey 해설](https://www.eia.gov/todayinenergy/detail.php?id=32852) · [연준의 DOE 기반 일별 보강 사례](https://www.federalreserve.gov/econres/notes/feds-notes/natural-disasters-and-the-measurement-of-industrial-production-hurricane-harvey-a-case-study-20171011.html)
- **추세 기준선과 제약의 증분.** t−2 지속값과 t−9~t−2 선형추세의 t0 절대오차 평균은 9개 군집에서 각각 824와 1,023천 b/d입니다. 현 빈티지·사건 조건부 기술 비교이며 사전 예측 점수가 아닙니다. 재고 보존식은 같은 제품·측정 범위와 오류 무시 조건에서 총반출 하한을 줍니다. 그 주 Ida의 걸프 집계상 하한은 **315.6만 배럴**, Harvey는 **6만 배럴**입니다. 이 하한은 지역 소비량, 미충족 수요, 개별 시설 재고가 아닙니다. 관측 수취량은 주간 인과 경로를 점으로 복원하기에 거칩니다. 실제 가용성의 미관측 범위가 남아 있어 제약 모형의 추가 예측력은 `NOT_EXECUTED`입니다. [계산](reproduce.py) · [식별 증명과 반례](MATHEMATICS-ko.md)

## 재현

Python 3.11 이상에서 S4 경로를 작업 디렉터리로 사용합니다. 재현에는 커밋된 공식 XLS·PDF와 NOAA 추출본이 충분합니다. NOAA 전체 CSV 55MB는 수집 URL·크기·해시로 식별하고, 기간 내 북대서양 상륙 플래그 전부를 보존했습니다. 원본 빈티지와 SHA-256이 같을 때 `python reproduce.py --project-noaa /path/to/official.csv`로 추출을 다시 만들 수 있습니다.

~~~bash
python -m pip install -r requirements.txt
python reproduce.py --check
~~~

기존 연구 대사는 아래 세 객체를 가져온 뒤 해당 경로에서 `python audit_priors.py --check`를 실행합니다. 대사 결과에는 원천 커밋 SHA가 있습니다. API에서 확인한 선행 PR 메타데이터는 `results/pr-lineage.json`에 보존했습니다.

~~~bash
git fetch origin \
  f223c1c7d8c841500ea99b2caadeaa72f7a0cce7 \
  46f181f4c75c4fe0e273fcb288feaebbea24dd12 \
  17a9514e06cefd5176cc2a6c05453f003f4e9c17
python audit_priors.py --check
~~~
