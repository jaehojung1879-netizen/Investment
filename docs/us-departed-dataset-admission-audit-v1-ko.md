# 미국 이탈 가격 데이터셋 admission 감사 v1

**판정: BLOCKED / NOT_ADMITTED. 복구 후보 186,910세션 중 현재 multifactor 결과 검증에 승인된 세션은 0개다.** 데이터가 사라진 것은 아니다. 소유자가 요청한 기존 로컬 사본 검증·진단 감사를 수행했으며, 영구 비공개 보관 조건과 데이터 이용 권리는 아직 확정되지 않았다. US-MF-1 실행을 승인하지 않는다.

기준 main `f7e22d0dc91b92bab0b3efa78a747e1e3d991c59`는 #241·#242를 포함한다. #242의 `US_MF1_DATASET_ADMISSION_V1` AD1–AD8을 적용했다. [기계 판독 보고서](us-readiness/us-departed-dataset-admission-audit-v1.json), [감사 엔진](../pipeline/us_departed_dataset_admission.py), [CLI](../scripts/audit_us_departed_dataset_admission.py), [합성 테스트](../tests/test_us_departed_dataset_admission.py)를 제공한다.

## 원본 증거와 재현

`/workspace/pr241-nonpublic-preservation/`에 원자료 archive와 출처별 후보 패널이 실제 남아 있었다. main의 manifest와 압축 바이트 수·SHA-256 및 패널의 해제 후 SHA를 모두 대조했다.

- raw SHA: `0fa0b576d04693cda88611b3ec19d2415d868c1af2189f0e29944f2d7ae835f4`
- panel SHA: `41ef2da7e8bc6ee7a07ec58635e08a25452c7228cfb33d269a22e266f0b7aa59`
- 각 후보 행을 archive의 해당 source/ticker CSV와 필드별 대조했다. 원본 날짜·종가·volume을 합치거나 채우지 않았다.
- **212 identities, 후보 175, FULL 5 / PARTIAL 170 / NONE 37, 원래 결측 256,402세션, 복구 186,910세션, 잔여 후보 결측 69,492세션**을 재현했다. 출처별 중복 관측 268,041행은 고유 세션과 구분한다.
- D/F가 있는 식별자 59, A-only 113, E-only 3도 재현했다. 고정 publisher 우선순위는 F → D → A → E이며 결과/수익률을 사용해 선택하지 않았다.
- 두 독립 실행의 public aggregate 보고서는 byte-for-byte 동일했다. 입력 manifest SHA `b03621b69a410b1b00958a76958db7a511d731a32d1574f1e309240e2101c9e7`, 가격이 없는 비공개 session table SHA `14d96bda6680a51f939d49f1abce276e86687fe91e766f3ab15f9c7d8cd76248`이다.

세션별 표는 checkout 밖에만 저장했다. 공개 PR에는 원자료·파생 가격·세션별 관측 표가 없고 집계·issuer/source 증거·hash·코드만 있다. 제거된 GitHub commit/blob은 조회하지 않았다. 원본 사본은 여전히 일시적 작업 공간에 있으므로 영구 보관으로 주장하지 않는다.

## 실제 품질 관문

아래는 서로 독립적으로 평가한 candidate 세션의 통과 수다. 한 관문 통과가 dataset admission을 뜻하지 않는다. 모든 관문을 누적 적용한 수는 0이다.

| 관문 | 통과 세션 | 현재 해석 |
|---|---:|---|
| source provenance / 선택 publisher 존재 | 164,408 | 고정 source URL/revision/취득 시각/hash로 확인 |
| dated membership | 186,910 | 기존 strictly-earlier snapshot 규칙; 공식 effective date 아님 |
| AD2 issuer/share-class identity | 0 | 기업명·ticker 일치는 price-file issuer/CIK 검증이 아님 |
| AD3 검증된 단일 as-traded basis | 0 | 단일 publisher는 지켰지만 경제적 basis는 미검증 |
| AD4 split/dividend lineage | 0 | dated event chain 및 rebuilt-level 검증 없음 |
| AD5 H63 endpoint 존재 | 151,424 | 날짜 존재만 확인; 수익률/terminal payoff 계산 아님 |
| AD6 PIT filing–issuer CIK 연결 | 0 | filing 존재와 역사적 price issuer 연결을 구분 |
| 최종 ADMITTED | **0** | US-MF-1 historical development 시작 불가 |

AD1은 기존 후보 checksum을 검증했지만 새 admitted replay generation을 만들지 않았고 owner-controlled durable storage도 확인되지 않았다. AD7 잔여 결측률을 전 연도에 공개했다. AD8은 outcome/label/model/portfolio 읽기 모두 0이며, 엔진에 outcome reader나 가격 수준 입력 자체가 없다. 합성 spy/AST 테스트가 외부 읽기와 미승인 import를 막는다.

후보 세션의 선택 basis는 D/F vendor Close + 별도 Adj Close **71,665**, A back-adjusted **91,770**, E rounded/adjustment-unknown **973**, 선택 publisher 공백 **22,502**다. D/F 컬럼 이름의 “Close”는 원거래 가격 보증이 아니다. 다른 출처가 공백을 메워도 하나의 시계열로 splice하지 않았다. A/E를 as-traded로 재명명하지 않는다.

주 상태는 NO_OBSERVATION → IDENTITY_HOLD → NAME_ONLY → BASIS_UNRESOLVED → QUALITY_UNRESOLVED → ADMITTED 순의 첫 실패를 기록한다. 현재 NAME_ONLY 186,910 / NO_OBSERVATION 69,492이고 다른 상태는 0이다. 이는 basis/lineage 문제가 없다는 뜻이 아니다. 각 세션의 실패 관문과 독립 통과 수를 별도로 기록했다. 원래 8개 identity hold는 해당 identity에 표시되지만 qualified 패널에는 관측이 없어 주 상태는 NO_OBSERVATION이다.

Finnhub `704d7db6…`의 fundamentals shard만 Git blob/SHA 검증 후 metadata를 읽었다. 원래 availableFrom-window 분류인 **160 membership 내 filing 존재 / 41 없음 / 11 membership 밖**을 재현했으나 AD6 승인 수와 혼동하지 않는다. feature 값을 산출하지 않았다. filing은 `max(availableFrom, acceptedDate)`의 날짜보다 **엄격히 뒤**이고 member issuer CIK가 맞아야 한다. 뒤늦은 CIK snapshot을 과거에 backfill하지 않는다. 동일 날짜 snapshot multiplicity는 2013-05-05 3개, 2014-02-25 2개, 2014-12-07 2개다. 기존 membership 분모의 stable order는 보존하되 상충하는 issuer 증거는 합치지 않는다.

## H63 존재 검사와 잔여 커버리지

후보 시작 세션 186,910개 기준으로, 선택 publisher의 H63 전체 날짜 관측이 있는 창은 151,424개다. 미해결 35,486개는 선택 publisher 시작 공백 22,502 / 창 내부 gap 2,581 / 시작 관측은 있으나 마지막 quote 뒤로 넘어가는 창 10,403으로 분리된다. 시작 공백을 무시하고 마지막 quote를 넘는 모든 창은 **29,518개**이며 모두 UNRESOLVED다. 시작 공백을 제외한 endpoint 분류와 underlying quote-window 존재 분류를 JSON에 함께 보관했다. 마지막 quote를 payoff로 사용하지 않았다. 212개 모두 기업 행동 lineage와 terminal consideration triage가 미해결이며, 212개가 모두 실제 delisting이라는 뜻은 아니다.

| 연도 | 원래 결측 세션 | 복구 후보 세션 | ADMITTED | 잔여 결측 세션 |
|---|---:|---:|---:|---:|
| 2013 | 38,181 | 27,002 | 0 | 38,181 |
| 2014 | 35,840 | 32,271 | 0 | 35,840 |
| 2015 | 33,502 | 29,965 | 0 | 33,502 |
| 2016 | 28,477 | 26,583 | 0 | 28,477 |
| 2017 | 25,621 | 22,366 | 0 | 25,621 |
| 2018 | 22,516 | 12,339 | 0 | 22,516 |
| 2019 | 21,672 | 11,088 | 0 | 21,672 |
| 2020 | 16,452 | 10,344 | 0 | 16,452 |
| 2021 | 11,628 | 6,845 | 0 | 11,628 |
| 2022 | 10,964 | 6,839 | 0 | 10,964 |
| 2023 | 5,197 | 1,268 | 0 | 5,197 |
| 2024 | 3,639 | 0 | 0 | 3,639 |
| 2025 | 2,241 | 0 | 0 | 2,241 |
| 2026 | 472 | 0 | 0 | 472 |

범위는 원본 audit의 2013-01-01–2026-09-14다. 오늘까지 확장한 분모가 아니다. 전체 universe daily/weekly member-date 분모 및 before/candidate-after/admitted-after 비율을 JSON에 보관했다. admitted-after 주간 결측률은 모든 연도에서 before와 동일하다. 2024–2026 개선은 0이며 후보 창이 없을 때 UNRESOLVED 비율은 None이다.

## 재사용과 다음 데이터 문제

```bash
python scripts/audit_us_departed_dataset_admission.py \
  --private-artifacts /owner/local/nonpublic-artifacts \
  --report /tmp/admission-audit.json \
  --private-session-table /tmp/admission-session-table.json.gz
```

정확한 버전 재현은 이 감사 코드의 hash와 입력 manifest를 사용한다. CLI는 기존 출력 덮어쓰기와 Git checkout 안의 session table 저장을 거부한다. 파일이 없으면 **DATA_UNAVAILABLE**, measured admission 수는 None으로 보고하고 필요한 두 파일의 정확한 이름/hash를 제공한다. missing payload를 public dangling object에서 복원하지 않는다. 원본·봉인 결과·P4 입력과 lock·production workflow는 수정하지 않는다.

엔진은 checksum 검증된 adapter의 명시적 issuer/share-class·basis·dated lineage·terminal·filing 증거를 받아 합성 환경에서 admission을 검증할 수 있다. 실제 adapter는 존재하지 않는 증거를 생성하거나 성공 flag로 덮어쓰지 않는다. 현재 복구분은 **가격/momentum, profitability, cash flow, investment, leverage, valuation, share-count 어느 가족의 multifactor 결과 검증에도 admitted 입력을 제공하지 못한다**. 이미 존재하던 다른 종목의 feature를 계산할 수 없다는 주장은 아니다.

가장 가치가 큰 다음 문제는 더 많은 ticker CSV 확보가 아니라 **D/F 59 identities의 71,665세션에 대해 역사적 price issuer/share class–CIK 연결과 원거래 basis·split/dividend lineage를 검증하는 것**이다. 동시에 owner가 기존 사본을 승인된 영구 비공개 보관소에 보존하고 원공급자 이용 권리를 확정해야 한다. 종료 이벤트/대가 증거가 없는 창은 계속 UNRESOLVED로 남는다. 이를 해결한 새 입력 revision만 별도 admission을 받아야 하며, 현재 P4·replay-v16에 연결하지 않는다.

Focused/static/full pytest 및 최종-head GitHub CI의 실제 완료 결과는 PR 본문에 기록한다. 실자료 감사 수치와 합성 테스트를 구분하며, CI가 private 원자료를 취득하거나 US-MF-1 결과를 실행했다는 뜻이 아니다.
