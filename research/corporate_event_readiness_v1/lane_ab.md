# A/B — 고정 원문과 파서

공식 DART 공개 viewer 원문 **13건, 7개 index 발행사, 2012~2026년, 221,619 bytes**를 확보했다. 2012년 표본은 구형 서식 회귀용이며 2013년 이후 연구 표본수에 합산할 근거가 아니다. 40건을 확보했다고 주장하지 않는다. 결과 수익률, NAV, 라벨, IC를 조회하거나 계산하지 않았다.

- `evidence/filing-samples.json`: #316 고정 commit `75aab7bc7096b551543bc1582c1e7fd288e94e59`의 I index 경로·blob, 실제 receipt, viewer URL·dcm 인수, 수집 시각, bytes/SHA256. 새 API key 없이 public main/viewer를 총 **30 HTTP 요청**했다(중복 탐색 포함). 이 계획의 호출은 종료했다.
- `filings.py`: main의 `kr_corporate_action_events.receipt_date`·`is_amendment` 재사용. #316 내부자 파서의 UTF-8→CP949 접근을 확인하고 동일 인코딩 정책을 적용했다. 그 파서의 내부자 전용 AUNIT enum을 다른 서식으로 추정 전용하지 않았다.
- `evidence/parsed-filing-samples.json`: 7개 자본배분 종류, 공급체결·해지·정정의 현재 확보 bytes 재현 결과. 원문은 건별 하나만 저장했다. 원문 table을 결과 JSON에 중복하지 않는다.
- `tests/test_corporate_event_filings.py`: 실제 bytes 검증과 안전 경계 **24 PASS**. 테스트 수는 신호·표본수나 G1/G2가 아니다.

| 확인한 서식 | 실제 receipt 예 | 검증한 필드 / 남은 공백 |
|---|---|---|
| 직접 취득 | 20121112800006, 20260804800356 | 수량/금액/목적/결정/취득예정기간. 보유 자사주 비율을 새 취득비율로 쓰지 않음 |
| 신탁 | 20170427800211 | 계약금액 50억원/기간/목적. 신탁계약액에서 주식수를 만들지 않음 |
| 소각 | 20241002800232 | 예정 수량 3,209,009/당시 명시 발행주식수 20,703,283. 취득 예정기간을 소각 실행일로 쓰지 않음; 완료 미관측 |
| 처분 | 20131024800337 | 예정 수량/금액/기간/목적. 옵션 행사 완료로 바꾸지 않음 |
| 유증 | 20170531800614 | 신주수/증자 전 발행주식수/납입/결정. 종속회사 이벤트를 상장 모회사 희석으로 승격 금지 |
| CB | 20160217800701 | 사채액/납입/결정/자금목적. 전환가능 주식수는 명시값 없음으로 보존 |
| EB | 20260911800557 | 사채액/교환대상 주식수/납입/결정. 실제 대상은 모회사와 다른 증권; identity unresolved |
| 공급 | 20130424800010, 20200302800563, 20141224800064 | 계약금액·원문 매출액·표시 비율·재계산·계약기간·상대방·공급지역. 2020 공시는 **2018년말 연결** 매출액으로 확인. 2013 공시는 회계연도가 명시되지 않아 미확정 |
| 해지/정정 | 20191002800414, 20261030800168 | 각각 별도 vintage로 보존. 정정은 2023 매출 기준 명시; 현재 금액을 원공시일로 소급하지 않음 |

**원천 확인 완료:** 공개 DART body와 고정 index 계보, 내용해시. 공개 열람 가능은 대량 수집·재배포 권리나 원문 당시 가용성 검증을 뜻하지 않는다.

**파서 검증 완료:** 위 13개 고정 bytes의 지원 필드와 격리 회귀. 모든 필드가 모든 서식에 존재하는 것은 아니다. 금액·수량 누락/음수, 애매한 반복 label, 비율 불일치, 회계연도 미명시, 종속회사, 정정 및 해지 chain 미해결을 구분한다. 타임존을 반영하는 as-of와 깊은 복사로 후속값의 미래정보·원본 변경을 막는다.

**데이터 적격성 검증 완료:** 아니다. index의 현재 이름과 stock code를 당시 거래 가능 증권으로 확정하지 않았다. 이름변경/상장종료/발행사-자회사/EB 대상증권은 PIT identity 구간 원천이 필요하다. 공개·접수 clock은 관측되지 않아 null이다. 보수적 다음 세션 규칙을 적용할 달력도 여기서 입증하지 않았다. 현재 dcm별 body bytes는 확보했지만 그 bytes가 접수 당시의 바로 그 문서였다는 역사 vintage 증거는 별도다. `rm=유정` 원본 후보 역시 정정 존재 표시를 격리한다. **모든 행 `source_version_verified=false`, `data_eligibility=BLOCKED`**다.

**실제 경제성 실증 가능:** 아니다. 정정/해지의 원접수 체인, PIT 거래 가능 신원/산업, 주가·기업행동·종결대가 및 승인된 연구 계약이 필요하다. 실제 MDE를 확정할 표본수를 만들지 않았다.

특히 날짜만으로 체인을 연결하면 안 된다. 해지 본문에 나온 2014-12-24를 이용해 같은 발행사 원공시 `20141224800064`를 조회했으나 계약명은 **가좌주공 재건축**, 해지는 **두산연구단지**였다. `rejected-chain-candidate.json`은 그 두 원문 해시와 연결 거부를 남긴다. 원공시 식별은 계속 `UNRESOLVED`이고, 이 실패를 정정 성공이나 중복 제거 완료로 세지 않는다.

Opus 인계: 13건은 목적 표집된 파서 회귀 표본이다. 7개 category의 직접 상장증권 사건이 모두 확보됐다는 뜻이 아니다. 먼저 추가 원문 권리/예산을 확정하고, 정정 원접수 receipt 증거·과거 identity·누락 필드 원천을 보완한 후 동일 정의로 전체 표본을 만들어야 한다. #319 가설/기준을 결과에 맞춰 변경하거나 Phase D 예외·G1/G2 통과로 해석하지 않는다.

13건 고정 원문은 전체 I 제목 인벤토리 10,615건과 별개다. 제목 빈도·공시건수는 독립 사건수도 실증 적격 표본수도 아니다.

네트워크 없는 결과 재생성(저장된 raw 13개만 읽음):

```bash
python - <<'PY'
import json
from pathlib import Path
from research.corporate_event_readiness_v1.filings import parse_filing
p = Path('research/corporate_event_readiness_v1/evidence')
manifest = json.loads((p / 'filing-samples.json').read_text())
rows = []
for sample in manifest['samples']:
    row = parse_filing((p / sample['file']).read_bytes(), sample)
    row.pop('raw_table_rows', None)
    rows.append(row)
(p / 'parsed-filing-samples.json').write_text(
    json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
PY
```
