# Track B — B-H1 상태 기록 준비 (비활성)

이 변경은 #264의 PREVIEW를 **입력 검증 → 상태 계산 → receipt 검증 → append-only JSONL → 원장 검증**까지 합성 데이터로 연결한다. 실제 LIVE 원천이나 승인을 등록하지 않는다. `record-live`는 파일을 열기 전에 non-zero로 거부한다. 생산/원장 workflow에서 import하거나 스케줄하지 않는다.

## 원래 연구 질문을 유지한다

[원 B-H1](03-studies-abc-ko.md#b3-사전-고정-가설-1차-2개-holm)의 상태는 **FAST=2 또는 직전 24개월 지수 수익률 < 0**이다. `rp1_b_state_receipt.observe/build_preview`와 봉인 `kr_market_risk_model.fast_states`를 그대로 호출한다. 기존 모듈·공통 core·봉인 spec·역사 결과는 수정하지 않는다. FAST 창·변동성 기준·24개월 기준일·OR/결측 로직을 새로 구현하지 않는다.

현재 기록 대상은 **MARKET_OBSERVED 상태·출처·시각·가용성**이다. 이 상태에서 특정 종목이 초과수익을 낸다는 주장이나 B-H1의 12-1 모멘텀 상위−하위 H63 스프레드를 측정하지 않는다. 후자의 대상 표본·비중첩 블록 원점·비교 시점은 별도 사전등록이 필요하다. A/C 결과나 US 원천 복구는 B-H1 상태 기록의 선행 조건이 아니다.

## #264 preview 이후 구현한 부분

| 영역 | 이번 구현 |
|---|---|
| 입력 | 합성 source envelope의 정확한 필드·지수 신원·basis·날짜/값·digest 검사. 빈 입력, 서버 오류 응답, 미래/중복/역순/휴장일 행 거부 |
| 세션 | 달력상 예상 세션으로 정렬해 빠진 개장일을 NaN 자리로 드러냄. 가격 보충/전일 값 대체 없음. 기존 FAST가 마지막 201세션의 결측/비양수 가격을 DATA_INSUFFICIENT로 처리 |
| 결측 | FAST 부족, 정확한 24개월 기준일 부족, 신호일 종가 부재, 중간 세션 부재, 존재하지만 유효하지 않은 가격을 구별. 관측된 한쪽 조건이 불리하면 OR=True, 그렇지 않고 한쪽이 결측이면 None |
| 시각 | 원천 availableAtUtc ≤ observedAtUtc ≤ createdAtUtc. 관측은 신호일 18:00 KST 이후. 공통 core로 18:00 포함/다음 KRX 개장 09:00 미포함 경계와 승인 병합 KST 날짜 이후 신호일 검사. 합성 경로에서만 시험 시계/시험 병합 시각 제공 |
| 신원 | 고정된 비활성 계약 파일 SHA-256, 실제 디스크의 전이 import closure·CLI·requirements 해시, calendar 버전, 원천 envelope 해시, preview 입력 digest, receipt digest를 보존 |
| validator | 저장 필드와 상태/시각/가용성 일관성 검사. append 직전 원 source로 재계산해 digest만 다시 계산한 가짜 상태도 거부 |
| writer | 기존 바이트를 다시 쓰지 않는 append, exclusive flock, 엄격한 신호일 증가/중복 거부, 해시 체인, 파일/디렉터리 fsync, symlink/hardlink 및 체크아웃 안 경로 거부 |
| 무결성 | 모든 기존 행과 체인·중복·순서·동일 등록 신원을 검사. 독립 보관한 byte SHA-256/길이/행 수 체크포인트와 대조해 삭제·전체 이력 재해시도 감지 |
| 실패 | 소스/계약/코드/digest 불일치 및 I/O 오류는 예외 또는 CLI non-zero. 실패를 성공 요약으로 덮지 않음 |

`codeFiles`는 전이 의존 파일의 **바이트 신원**을 읽는다. 그 안에 역사 평가 코드 파일이 있어도 평가 함수나 결과를 호출/열람하지 않는다. 새 모듈은 역사 replay·outcome 함수·성과 검정·모델 승격을 호출하지 않는다. outcome 키 scanner와 정확한 필드 allowlist를 적용해 결과/비중을 receipt에 섞지 않는다.

## 실행 가능한 범위

```bash
python scripts/record_rp1_b_state.py status
python -m pytest -q tests/test_rp1_b_state_receipt.py tests/test_rp1_b_state_recording.py
python scripts/record_rp1_b_state.py record-live   # 항상 REFUSED, exit 1
```

합성 입력 envelope는 테스트의 `source()`가 보여 준다. 형식은 `schemaVersion`, `evidenceClass=SYNTHETIC_FIXTURE`, `sourceId=instrumentId=SYNTHETIC_KR_INDEX`, `priceBasis=SYNTHETIC_INDEX_CLOSE`, `signalDate`, `availableAtUtc`, `observedAtUtc`, `observations=[{sessionDate,close}]`, `sourceSha256`다. source digest는 `sourceSha256` 자체를 제외한 canonical JSON의 SHA-256이다. close의 null은 결측이며 자동 가격으로 바뀌지 않는다.

시험 원장과 체크포인트는 **체크아웃 밖 임시 디렉터리**만 사용한다. 최초 checkpoint는 `checkpoint()`의 빈 원장 pin이고, 이후에는 성공한 append가 반환한 새 checkpoint를 독립 보관한다.

```bash
python scripts/record_rp1_b_state.py record-synthetic \
  --input /tmp/b-h1-fixture/source.json \
  --ledger /tmp/b-h1-fixture/synthetic.jsonl \
  --checkpoint /tmp/b-h1-fixture/previous-checkpoint.json \
  --merged-at 2026-09-03T10:00:00Z --now 2026-09-11T09:05:00Z

# 위 성공 출력의 checkpoint를 별도로 보관한 뒤 검증:
python scripts/record_rp1_b_state.py validate-synthetic \
  --ledger /tmp/b-h1-fixture/synthetic.jsonl \
  --checkpoint /tmp/b-h1-fixture/current-checkpoint.json
```

이 명령은 임의 실데이터를 자동으로 합성으로 변환하지 않는다. fixture 표기는 신원의 암호학적 증명이 아니므로 실제 자료를 fixture라고 기재해도 실데이터/권리 승인이 되지 않는다. 합성 receipt에는 `PROSPECTIVE_PAPER`를 사용할 수 없고 이를 LIVE로 승격하는 플래그도 없다. 중첩 `preview.ledgerWritten=false`는 재사용한 preview의 속성이며 최상위 합성 row는 시험 writer에 의해 저장된다.

## 첫 실제 영수증까지 남은 승인·개발

비활성 [기계 계약](specs/rp1-b-h1-state-recording-v1.json)은 다음을 **null / BLOCKED**로 남긴다. 이 문서나 PR 병합은 이를 승인하지 않는다.

1. **LIVE source admission:** 고정 KR 지수의 정확한 공급자·instrument·종가 basis·정규화/개정 정책·관측 가능한 공개 시각 증거를 정한다. 보존 FDR/KS200 역사 파일이나 Yahoo 다운로드 성공을 현재 admission으로 취급하지 않는다. 원본 및 파생 상태의 저장/공개 권리를 소유자가 확인해야 한다. 이번 PR에는 네트워크 취득 adapter가 없다.
2. **소유자 등록:** 계약·실행 코드 closure·runtime·원천 adapter·허용 원장 경로를 승인한 실제 main 병합에 고정한다. LIVE builder는 호출자가 주는 hash/승인/시계를 믿지 않고 등록 및 실제 main 조상을 검증하고 자체 시계를 읽도록 별도 구현·감사해야 한다. 현재 `REGISTERED_AUTHORIZATION=None`이며 LIVE builder/writer는 활성 구현되지 않았다. 합성 시험의 `syntheticMergeAtUtc`는 실제 병합 증거가 아니다.
3. **영속 원장:** 현재 시험 writer를 별도 LIVE 경로/증거 등급에 연결하기 전에 원장 위치·접근·외부 체크포인트/공개 시각 증거·원격 동시 쓰기·실패 복구 절차를 승인한다. 파일 잠금은 같은 로컬 파일의 협조적 writer만 직렬화하며 원격 Git push 경쟁을 해결하지 않는다. 파일과 체크포인트를 모두 다시 쓰는 주체를 자체 해시만으로 탐지할 수 없다. fsync 후 응답 전 실패는 기록 여부를 검증 후 복구해야 하며 자동 재작성하지 않는다.
4. **불완전 입력 정책:** 합성 경로는 부분/불명 상태를 구별해 저장을 시험하지만, 실제 입력 부재/장애 시 LIVE 상태 row를 남길지 별도 실패 이벤트를 남길지 사전 결정하지 않는다. 장애 뒤 과거 상태를 사후 보충하거나 missing을 benign으로 바꾸지 않는다. 실제 과거 공개본/PIT 증거 없는 재취득은 제때 쓴 receipt가 아니다.
5. **평가 등록:** 원 B-H1의 H63·상태별 최소 비중첩 6블록·원래 모멘텀 대비·Holm을 유지하되 원점·표본·실제 관측/평가 시점 및 outcome 원장 연결은 결과를 읽기 전에 고정한다. 이번 코드에는 평가기/미래 수익률/새 임계값이 없다. 상태를 모은 것만으로 추론 자격이 생기지 않는다.

코드/계약이 바뀌면 현재 verifier는 기존 버전 identity와 일치하지 않아 거부한다. 실제 기록 시작 전 버전 고정과 이후 버전별 validator 보존 정책도 영속 원장 등록에 포함해야 한다. 이번에는 새 workflow, Secret, 유료 취득, 봉인 KR 재실행, 생산 투자 비중 또는 #277·#278을 변경하지 않는다.
