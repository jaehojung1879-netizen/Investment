# A1/B1 경제성 입력 검증 — 미등록·outcome 실행 불가

기준 main `37f8cbf6`, Claude 원천 `#320@9a47f478`, 가격 원장
`signal-history@73b3907a`. C2는 SOURCE_BLOCKED로 보존한다.

## 실제로 확보한 자료

SEIBro 공개 기간별 일정 화면의 **명시적 권리락일** 응답을 확보했다.
2026년 3·6·9월 286행 중 현금배당 269행, 발행체 241개다.
DART 원공시와 발행체 코드 후보·기준일이 맞는 것은 140건이다.
그중 116건에는 기존 배당락 후보가 없었다. 기존 593개 상대 날짜 후보와
구분하며 Claude의 파서·사양·등록 파일은 수정하지 않는다.

이 응답의 5자리 발행체 코드는 실제 6자리 증권 코드가 아니다. 조회 시점의
수정 가능 자료이며 과거 공개 빈티지가 아니다. 주식 종류·분배액·원공시 및
정정 계보·전 보유기간의 기업행동 완전성까지 검증한 총수익 자료가 아니다.
**경제성 검정에 완전히 적격한 사건 증가분은 0**이다.

작은 공식 원문 1건만 fixture로 보존하고 나머지는 원문 해시를 고정한다.
대량 재수집·재배포 권리 및 원문 확대 수집은 별도 판단 사항이다.

## 가격 결함 및 복구 경계

세 날짜 2026-09-15/16, 10-01은 기존 달력에서 거래일이나 원장 바가 0개이고
done 마커는 존재한다. 공식 발행사 153130 시세 원문에도 세 날짜의 양수
거래량이 있다. KRX 공식 휴장일 페이지는 Access Denied, 공개 시세는 LOGOUT:
공식 KRX 달력의 독립 확인을 완료했다고 주장하지 않는다.

수집기는 빈 응답을 무조건 휴장으로 완료했다. 요청일/응답일 불일치도
완료할 수 있었고 일부 성공 후 오류가 나도 CLI 성공을 반환했다.
수정은 **미봉인 수집기 한 파일**에 국한한다. 거래일 빈 응답은 재시도,
완료 마커와 실제 바 대조, 원문 날짜·유지 종목 검증, 관측 수정 거부,
원자적 샤드 쓰기와 최종 완료 저장, source 오류의 비정상 종료를 검증한다.
예산 소진은 정상 재개 가능한 부분 수집으로 구분한다.

기존 `pipeline/krx_prices.py`·달력·워크플로·봉인 파일은 불변이다.
복구 도구는 **새 디렉터리만** 받으며 이전 행이 단 하나라도 바뀌면 거절한다.
원본 원장에 대한 쓰기나 수집기 운영 적용을 수행하지 않았다.

```bash
python -m research.a1b1_economic_inputs_v1.repair capture /tmp/krx-three-dates-raw
python -m research.a1b1_economic_inputs_v1.repair recover ORIGINAL RAW NEW_ISOLATED_OUTPUT
python -m research.a1b1_economic_inputs_v1.admission --out before.json
python -m research.a1b1_economic_inputs_v1.admission --repaired NEW_ISOLATED_OUTPUT --out after.json
python -m research.a1b1_economic_inputs_v1.dividends --raw RAW --decisions COHORT_DIVIDENDS_GZ --out dividend-joins.json
```

첫 명령만 기존 승인된 KRX 키로 정확히 3회 공식 조회한다. 다른 명령은
로컬 원문과 고정 Git 객체만 읽는다. 조회 권한·실제 바가 없으면 복구 성공을
선언할 수 없다. `admission`은 Claude의 정확한 기존 함수를 재사용하고
가격 수치를 보존하지 않는다. 정지·결측·말소는 별도 원천 없이 단정하지 않는다.

## 경제성 계산 범위

`prepare_event`는 기존 A1/B1 신호·진입일 계약과 H126/H252 만기를 확인한다.
미성숙 사건을 제거하지 않으며 정책 해시가 없으면 BLOCKED다.
`synthetic_payoff/pair`는 **SYN_ 증권의 합성 입력만** 받는다.
#317의 고정 코드에서 만기·실제 거래 leg 비용 함수를 재사용한다.
주식 수·현금·미지급 청구권을 분리하고 배당 지급 전 현금을 재투자하지 않는다.
분할·병합, 자기자본 범위 내 진입 비용, 실제 청산 명목액, 명시적 세금,
동일 기간 ETF 비교 및 원문 해시의 계산·거절을 시험한다.
권리 증자·승계 주식·불명확한 종결·비거래일 지급에 필요한 달력 현금 원장은
현재 이 작은 계산기의 지원 범위를 벗어나므로 차단한다.

기존 `price_adjustment` 조정지수는 합성 100→95, 배당 10에서 5.5556%다.
현금 보유 주주의 직접 손익은 (95+10)/100−1 = 5%다. 이를 동일한 funded
주주 총수익으로 취급하지 않는다. 기존 봉인 조정식은 변경하지 않았다.

합성 회계 정책은 연구 정책 승인이 아니다. 등록된 calendar-time book,
사전 베타 대조군, 현금·재투자·계좌별 세금·비용 정책, 추론은 Claude가
고정하고 별도 정확 해시 승인·독립 감사를 받아야 한다. 역사 실행 경로는 없다.

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python -m pytest -q \
 tests/test_a1b1_economic_inputs.py tests/test_krx_price_completion_integrity.py tests/test_krx_price_collection.py
```
