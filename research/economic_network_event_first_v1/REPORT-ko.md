# S2 경제 충격에서 기업으로 역추적한 원천 연구

2026-11-27 KST · Investment · `SOURCE_ONLY` · 기준 main `3150c70017432e3b73321fbda47ebea226bf8d2b`

## 결론

**FDA 의료기기 기록이 가장 확장성이 높은 원천입니다.** 2019~2025년 의료기기 Class I 리콜 **561개 FDA 사건 ID**를 동일 법인 또는 시설 식별자와 동일 허가번호 또는 리콜 사유에 따라 묶으면 **521개 후보 군집**입니다. 이 중 사건 전에 공시된 SEC 등록회사·자회사 관계와 제품 허가번호가 함께 있는 것은 **66개 후보 군집**입니다. 허가 신청자와 리콜 법인 이름까지 같은 경우는 **45개 군집**입니다. 기관 데이터의 현재 판본으로 복원한 관측치입니다. 처음부터 외생 충격·역사적 최초 공개·기업 간 전달을 모두 입증한 표본의 크기는 아직 산출할 수 없으며, 확증 연구 적격 건수는 0입니다. [openFDA Enforcement](https://open.fda.gov/apis/device/enforcement/) · [제품 리콜](https://open.fda.gov/apis/device/recall/) · [FDA 510(k)](https://open.fda.gov/apis/device/510k/)

**실제 전달경로를 보여 준 새 사례 네 건**은 Philips 호흡기, Abbott Sturgis 분유, Medtronic HVAD, BD BACTEC입니다. 제품·고객 유형 또는 실제 대체 제약을 공식 공지에서 확인했습니다. Baxter North Cove는 S1의 동일 사건이므로 신규 건수에서 제외했습니다. 개별 기업 구매 배분·실제 대체 용량은 대부분 미확인입니다. S1에서 확인한 공급관계, 고정자본 교체 지연과 공통 병목은 별도로 보존했습니다.

**50~100개 규모의 원천 심사는 진행할 수 있습니다.** 기업·제품 조인이 있는 66개가 검토 모집단입니다. 180일 중복 기준에서는 63개, 동일 법인까지 요구하고 180일 기준을 쓰면 42개입니다. 66개 중 20개가 Medtronic에 귀속되어, 해당 발행사를 통째로 제외하면 46개입니다. 50~100개의 독립·적격 충격을 확보했다는 판정은 이 단계에서 내릴 수 없습니다.

## 실제 수집과 사건 수

| 원천·범위 | 확보한 표본 | 사건 단위와 제한 |
|---|---|---|
| FDA 리콜 2019~2025, 개시일 기준 | 3개 공공 원본 88,453행 전량 스캔. 기간 안에서 키 결측 1행을 제외한 제품 행 37,641개, 의료기기 6,464·의약품 2,251·식품 3,341개 FDA ID | 도메인과 사건 ID로 제품 행을 접어 **총 12,056개**로 기록. 공통 제조 라인, 후속 리콜, 재게시, 동일 공장 확산, 도메인 간 공통 원인은 남아 있으므로 12,056개를 독립 사건으로 사용하지 않습니다. |
| FDA 보강 자료 | 의료기기 리콜 59,705개 제품 기록과 510(k) 176,747건을 스캔. 의료기기 Enforcement 제품 키 **18,884/18,892**를 회수 번호와 사건 ID로 대응. 공개 의료기기 품목분류·시설 등록 파일도 수집 | Class I 사건 중 제품코드 559/561, 의료기기 목록 게시일 508/561, 개시 90일 전 제품 허가 405/561. 같은 법인명이 일치하는 185개 ID는 160개 90일 후보 군집. 개별 생산량·공장 가동률 없음. |
| FDA 의약품 부족 | 공식 공개 자료 1,577행 중 기간 내 최초 게시일이 있는 793개 제품·포장 행. 날짜와 현재 상태·사유를 분리 | 한 성분의 회사·NDC 여러 행과 여러 달의 상태 업데이트가 공통 부족을 설명할 수 있습니다. 확인된 신규 독립 사건 수에 합산하지 않았습니다. |
| BLS | S1 작업중단 94행·분쟁 에피소드 91개 원장 재사용. 91개 전체에 역검색 상태를 표시. 5개는 S1의 사건별 근거 유지, 18개는 추가 상장사 후보, 68개는 미연결 | Textron과 Pratt & Whitney는 공식 공지에서 운영자와 정지 경계를 확인. 고객사 제품·공장별 사전 범위 추가 필요. 복수 고용주나 동일 교섭의 확대는 한 에피소드. |
| USAspending | 2024년 10월 조치일, 계약 A~D, 발주기관 DOE 635·HHS 2,583·NASA 1,273건. 거래키 4,491개, 계약키 4,115개. 별도 DoD 항공기 계약에서 전체 거래 207건 확보 | 3,551행은 변경번호가 있고 616행의 의무액이 음수입니다. 명시적 해지·취소는 계약 6개. 근거 공지와 프로그램 검토 전에는 사건 후보입니다. 동일 계약의 변경 거래와 계약 의무액을 각각 독립 충격이나 기업 매출로 계산하지 않았습니다. |
| SEC 기업 공시 | EDGAR 연차공시 후보 214건, 등록기관 명칭 164건 판독 및 첨부 174건 확보. 별도로 설비·생산·계약 8-K 원문 7건의 accession과 접수 시각 검증 | 설비 폐쇄 의도·이사회 의결·실제 공장중단·계약 효력일·공개일을 분리. 표본은 실제 문서 목적 표집입니다. 전체 SEC 8-K 사건 수로 외삽하지 않습니다. |

FDA 2019~2025는 현재 구할 수 있는 공공 파일의 고정한 개시일 범위입니다. 공개 원본의 판본은 Enforcement와 의료기기 리콜 2026-11-25, 510(k) 2026-11-24, 의약품 부족 2026-11-26입니다. 최신에 알려진 분류가 2025년 말 뒤에 주간 보고에 나타난 Class I 의료기기 ID가 7개 있습니다. FDA 의료기기 Class I의 **개시 → 최초 관측 FDA 목록 날짜**는 중앙값 39일, 90분위 68일입니다. FDA 규정상 리콜은 게시 이후에도 분류·상태가 수정됩니다. 공지 원문이 확보된 사건에서는 회사 공지와 FDA 게시, 주간 보고의 각 시계를 보존했습니다. [FDA Enforcement 설명](https://www.fda.gov/safety/enforcement-reports/enforcement-report-information-and-definitions) · [FDA 변경 이력](https://www.fda.gov/safety/enforcement-reports/enforcement-report-history-feature)

66개 후보의 FDA 조치 설명도 일괄 선별했습니다. 유통·판매 중단 문구는 4개 군집, 반품·격리 문구는 35개, 현장 수정·업데이트 문구는 12개에서 나왔습니다. 범주는 겹칠 수 있습니다. 문구는 우선 확인할 원문을 고르는 근거입니다. 실제 판매·생산 중단이나 누락이 없었다는 판정에는 사용하지 않습니다.

## 공식 문서에서 확인한 전달경로

| 사건 | 발생과 공개 증거 | 사전 노출과 대체 제약 |
|---|---|---|
| Philips 호흡기 리콜 | 리콜 개시·회사 최초 확인 발표 2021-06-14. FDA 회사 발표 재게시 06-15. 두 의료기기 목록 날짜 07-13/15, 주간 보고 07-21. FDA ID 88058과 88071은 동일 공통 원인의 한 군집으로 묶었습니다. 물리적 결함 발생일은 미확인. | 기존 기기 이용자와 의료기기 공급업체에 닿는 경로. 회사 공지는 일부 기존 사용자가 즉시 사용할 대안을 구하기 어렵다고 기록합니다. 실제 교체량과 인도 시간은 별도 측정 대상입니다. [FDA 원문](https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/philips-issues-recall-notification-mitigate-potential-health-risks-related-sound-abatement-foam) |
| Abbott Sturgis | 2022-02-17 FDA와 회사 공지, ID 89629의 주간 보고 03-16. 오염이 처음 발생한 시각 미확인. | Sturgis 공장→분유 유통·소비자. FDA가 대체 공급을 위한 후속 조치를 문서화했습니다. 특히 특수 분유의 대체 제한과 일반 분유를 함께 세지 않습니다. [원 리콜](https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/abbott-voluntarily-recalls-powder-formulas-manufactured-one-plant) · [후속 FDA 조치](https://www.fda.gov/food/infant-formula-guidance-documents-regulatory-information/enforcement-discretion-manufacturers-increase-infant-formula-supplies) |
| Medtronic HVAD | 2021-06-03 신규 판매·유통 중단과 회사 공지. ID 88197은 08-18 주간 보고. | 기존 허가와 설치 기반이 있는 제품입니다. 회사는 신규 시술 대안으로 Abbott의 HeartMate 3를 명시했습니다. 기존 환자 기기의 교체와 신규 매출의 전환은 다른 전달 경로입니다. [회사 원문](https://news.medtronic.com/2021-06-03-Medtronic-to-Stop-Distribution-and-Sale-of-HVAD-TM-System) · [FDA 허가](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?id=P100047) |
| BD BACTEC | 고객 안내 2024-06-11은 CDC 문서에 소급 기록. 이번 조사에서 확보한 공공 공지는 07-10 CDC·BD입니다. 최초 발생일과 과거 고객 안내의 일반 공개 여부는 미확인. | 외부 공급 문제→BD 병→BACTEC 장비를 사용하는 검사실. 소모품의 규제 분류나 다른 회사의 공급 여부와 이미 설치된 장비에 맞는지 여부를 구분해야 합니다. [CDC](https://www.cdc.gov/locs/php/messages/2024/2024-07-10-impending-shortage-blood-culture-media-bottles.html) · [BD](https://news.bd.com/2024-07-10-BD-Statement-on-Supplier-Issue-Impacting-BD-BACTEC-TM-Blood-Culture-Vials) |
| Baxter North Cove | S1과 동일. 2024-09-29 기업 발표 및 후속 CDC 공지. | 공장→정맥주입액·투석액→병원. 특정 병원 계약이나 대체 구매량은 미확인. 중복 원천은 동일 사건 한 건에 귀속했습니다. [기업 공시](https://www.sec.gov/Archives/edgar/data/10456/000162828024041545/bax-20240929xex991.htm) · [CDC](https://www.cdc.gov/healthcare-associated-infections/bulletins/shortage-of-iv-and-peritoneal-dialysis-solutions.html) |
| Textron·Pratt & Whitney 파업 | Textron 2024-09-21 18:34 CDT 회사 공지, BLS 중단 시작 09-23. Pratt & Whitney 2025-05-04 노조 발표, BLS 중단 05-05. | 양쪽 모두 운영자·시설의 분쟁을 관측했습니다. 가동 영향을 받은 항공기·엔진 프로그램의 거래처와 대체 설비를 현재 표본에 소급 배정하지 않았습니다. [Textron](https://media.txtav.com/241569-textron-aviation-news-update/) · [Pratt 노조 발표](https://ctaflcio.org/press-room/strike-machinists-pratt-whitney-going-strike) |
| Alcoa·Rogers 설비 | Alcoa 2024-01-08 미국 날짜 공지, 2024년 6월까지 Kwinana 전면 감산, 2025-09-29 영구 폐쇄 결정. Rogers 2024-06-06 조건부 제조 중단 발표. | Kwinana의 2025년 폐쇄를 두 번째 물리적 중단으로 세지 않았습니다. Rogers는 중국·미국 생산설비를 통한 지원 계획을 명시했으나 실제 대체 투입량은 미측정입니다. [Alcoa 최초 공지](https://investors.alcoa.com/press-releases/press-release-details/2024/Alcoa-announces-curtailment-of-Kwinana-Alumina-Refinery-in-Western-Australia/default.aspx) · [Rogers 8-K](https://www.sec.gov/Archives/edgar/data/84748/000008474824000043/rog-20240606.htm) |
| MP Materials 계약 | 2025-07-09 DoD 계약, 07-10 10:31:07 UTC EDGAR 접수. | 가격 하한, 자금 조달, 구매 약정, 10X 설비 계획이 같은 프로그램에 담겨 있습니다. 다른 문서·거래 행으로 발견돼도 경제적 기점 한 건입니다. 미래 조건부 금액은 매출 인식과 분리합니다. [8-K](https://www.sec.gov/Archives/edgar/data/1801368/000119312525157310/d43796d8k.htm) |

## 기업 연결, 독립성, 대체 가능성

1. **사건을 먼저 수집했습니다.** FDA 공개 ZIP에서 도메인×사건 ID×회수번호를 먼저 고정하고, FDA 의료기기 파일의 제품코드·FEI·허가번호를 붙였습니다. 이후 사건 이름에서 검토할 상장 법인 후보 30곳을 선정했습니다. 사건 전 550일 안에 SEC 원본 등록회사 또는 자회사 첨부의 법인명이 일치하고 CIK 후보가 하나인 경우에만 연결했습니다. 115개 FDA ID·111개 군집에서 기업 연결을 확보했습니다. 이 중 70개 ID·66개 군집은 연결된 제품의 90일 전 510(k)를 확보했습니다. 모회사 내 회수 법인과 신청자가 같은 48개 ID·45개 군집을 별도 표시했습니다. 회계기간·법인명이 확인되어도 공시일부터 이후 사건까지의 지배구조 변동과 증권 연결은 다시 검토해야 합니다.
2. **기계적 군집과 독립성 판정은 별도입니다.** 같은 정규화 법인 또는 FEI 및 동일 510(k) 번호 또는 완전한 정규화 리콜 사유에서 30/90/180일을 바꿔 민감도를 확인했습니다. Class I 전체 540/521/494개, 상장사·제품 허가 연결 68/66/63개, 같은 법인까지 46/45/42개입니다. 연쇄로 이어지는 기록은 함께 묶습니다. 서로 다른 조직의 공통 공급사, 공통 공장 중단 및 정책 변화는 처음 집계에서 자동 추정하지 않았습니다. 수작업 사례 원장의 공통 원인 증거가 기계적 군집에 우선합니다.
3. **대체 후보의 앱 목록과 실제 대체량을 구분했습니다.** 같은 FDA 제품코드 안에서 90일 이상 이전에 허가 결정을 받은 다른 법인명 수를 보조 열에 저장했습니다. 559개 코드 연결 사건의 중앙값은 59개 이름입니다. 오래된 허가, 같은 모회사, 기기 호환성, 재고, 당시 판매 중단과 실제 여유 생산능력이 해결되지 않아 이 수를 대체 가능 회사 수로 해석할 수 없습니다. 반대로 HVAD 원문처럼 대체품이 명시된 사건에서는 신규 구매와 설치 기반의 전환을 나눠 관측할 수 있습니다. FDA 목록 공개일의 최초 판본이 없는 경우 510(k) 결정일에서 90일을 보수적으로 띄워도 역사적 PIT 확정은 아닙니다.
4. **USAspending의 최초 보고 약한 대용값은 보류했습니다.** 4,491건 전부에서 `initial_report_date` 열은 채워졌지만 2,160건은 조치일보다 이릅니다. 이 열, 조치일, 최종 수정일을 보존했습니다. 최초 시장 공개는 기관 공지·계약 공지·당시 캡처에서 별도로 확인해야 합니다. 의무액·행사된 옵션 및 전체 옵션 포함 가치는 각기 다른 공공 계약 필드이며 회사 확정 매출로 사용하지 않습니다. [USAspending 데이터 설명](https://www.usaspending.gov/data/about-the-data-download.pdf) · [API](https://api.usaspending.gov/docs/endpoints)

## 원천 유지와 다음 심사 기준

- **KEEP** · FDA Class I 사건의 발생·공지 시계 차이와 공통 병목, 설치 기반과 신규 주문의 대체 속도 차이를 주 사전 원천 후보로 유지합니다. S1 공급관계 ZIP은 기존 SHA-256 그대로 보존했습니다. S1에서 기업→사건으로 찾아낸 경로를 S2의 공식 ID와 교차할 때 의도적인 사건 수 중복을 제거했습니다.
- **INCONCLUSIVE** · 50~100개의 독립 충격 확보 가능성은 충분히 심사할 만합니다. 필요한 다음 관측은 66개 군집 가운데 과거의 첫 원문·공통 제조기점·영향 프로그램/고객·대체 가능성을 증명할 수 있는 수입니다. Codex의 최소 후속 작업은 미리 고정한 66개를 모두 심사하고 같은 모회사·공장·공급기점의 의존성과 탈락 사유를 원장에 남기는 것입니다.
- **계약·설비 보조군 유지** · 공개 사건 수가 충분해도 재무적 계약 변경과 실제 공급 차질은 인과 구조가 다릅니다. 확증에는 정식 등록과 해당 정확한 입력·코드 해시, 별도 소유자 승인, 독립 검토가 필요합니다. 기간 중 투자 성과, 가격, 라벨, 포트폴리오 경로는 조회하지 않았습니다. [증거 원장](../next_alpha_program_v1/EVIDENCE-MAP-ko.md) · [#292](https://github.com/jaehojung1879-netizen/Investment/issues/292)
