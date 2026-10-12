# US Real-Source Connectivity & Collection Preflight v1

## 범위와 기준

기준 main은 `b656f852a29b475bdb697b0b2a6752f7a559fbe4`이다. PR #229와 #230의 병합 및 AGENTS.md를 확인했다. 기존 US collector·source adapter·CLI와 [#229 source audit](us-readiness/us-prospective-daily-market-data-source-audit-v1.json)을 읽었다. #229의 CONNECT 403은 작성 환경 프록시 관측이며 GitHub-hosted runner의 Yahoo 접근 가능성을 측정한 결과가 아니다. 이 진단은 다른 실행 환경에서의 단일 실제 소스 점검이다.

모델·미래 수익률·알파·연구 결과·실행 잠금·production policy를 읽거나 변경하지 않는다. signal-history checkout/쓰기, daily schedule, 워크플로 dispatch, 공급자 자동 전환·접근 우회는 없다. 출력은 Git 체크아웃 밖의 `$RUNNER_TEMP`로 한정한다. PASS는 작은 진단 범위에 한정되며 전 종목 운영 준비 완료가 아니다.

## 워크플로 제약과 허용 경로

새 워크플로 파일은 현재 동결된 census와 충돌한다. 원 inventory, addendum, Phase C amendment 및 price-repair inventory뿐 아니라 두 census 테스트도 v1/v2/v3 연구 등록의 SHA에 고정되어 있다. 이를 수정하거나 등록을 재생성하지 않는다.

기존 `tests.yml`은 `historical-workflow-provenance-v1.json` 및 기존 validator가 등록 commit `8c3611116c5103a1e860173b180d0094e45b3074`의 원본 bytes로 역사적 출처를 검증하는 **현재 운영 CI**다. 이 파일에 별도 read-only job 두 개만 append하며 기존 pytest job·60분 timeout·lint·pinned-input fetch·entry-point import의 bytes를 그대로 유지한다. 새 workflow filename이 없으므로 동결된 census도 그대로 통과한다.

동결되지 않은 `test_historical_workflow_provenance.py`의 현재 운영 구성 검사는 원 파일 전체가 timeout 변경 외에는 동일해야 한다는 비교에서, **기존 원본 prefix 전체의 exact-byte 비교**로 갱신한다. 새 테스트가 허용된 추가 job 두 개만 존재하는지와 권한·branch·event·attempt·timeout·artifact 계약을 확인한다. 역사적 hash 검증·과학 코드·sealed spec·실행 권한·전체 pytest 검사를 약화하거나 제외하지 않는다.

네트워크 job 조건은 전부 충족되어야 한다:

- `pull_request`, action `opened`, 같은 저장소의 head.
- head branch `diagnostic/us-real-source-preflight-v1`, run attempt 1.
- `ubuntu-latest`, contents read, persist-credentials false, head SHA 직접 checkout.
- 10분 job timeout, 기존 pinned requirements, secrets 사용 없음.

synchronize/reopened/main push/다른 PR/fork/rerun에는 수집하지 않는다. 이 PR의 source evidence 생성 뒤 문서 갱신 시 일반 CI만 실행된다. source job과 전체 workflow의 결론은 별도로 보고한다. 이후 head 갱신으로 첫 전체 workflow가 취소되더라도 완료된 source job을 취소된 전체 CI의 성공으로 표현하지 않는다. 최종-head CI는 별도 실제 결론을 확인한다.

## 제한적 요청과 보존

1. 기존 adapter의 현재 S&P 500 CSV를 Git commit에 고정하여 원문과 취득 시각을 저장한다. membership가 거절되면 목록을 대체하지 않고 BLOCKED로 종료한다. 이 경우 Yahoo 연결은 미측정이다.
2. 계획을 소스 요청 전에 저장하고 SPY·QQQ를 각각 한 번 점검한다. 최근 완료 XNYS 세션 7개만 조회한다.
3. 둘 다 성공하면 실제 현재 목록의 AAPL·JPM·BRK-B/BF-B를 우선하여 최대 3개를 점검한다. 누락 시 목록의 식별자 순서로 대체하고, unusual class가 있으면 포함한다. 가격·성과 기반 선택은 없다.
4. 어댑터 호출 상한 5회, 다음 호출 시작 전 180초 예산 검사, 기존 공급자 timeout 20초. yfinance 내부 cookie/timezone HTTP 요청 수와 어댑터 호출 수는 다르다.
5. 기존 `price_records`·`ObservationStore`를 재사용하여 통화·심볼·ETF/equity 유형·뉴욕 날짜·필수 기업행동·전체 세션 창을 검증하고 불변 저장한다. 같은 취득 rows를 다시 append하여 bytes·경제 ID·원 소스 참조·가용시점·가격 기준을 검증하며 **재요청은 하지 않는다**.

Yahoo split-adjusted/dividend-unadjusted 원 패널과 as-traded OHLCV를 구분한다. strictly-after split factor로 가격·주당 배당은 곱하고 거래량은 나눈다. 분할 당일을 다시 조정하지 않고 Adj Close/총수익률을 생성하지 않는다. 실제 nonzero dividend/split 수를 보고하며, 0건일 때 실제 event 처리가 검증됐다고 주장하지 않는다. 합성 event 테스트는 별도 근거다.

전체 현재 membership 원문·snapshot, 요청된 가격 원 패널·source metadata·취득 ID·버전·digest, 일별 청크, 계획, report, 파일별 SHA-256을 90일 Actions artifact에 보존한다. GitHub run/head/runner environment 및 관련 코드·workflow hash를 report에 포함한다. credentials/proxy 환경 전체는 출력하지 않는다. report digest와 artifact archive digest는 다른 검증값이다. 원문은 artifact가 기준이며 PR의 audit 파일은 그 실행을 가리키는 출처 기록이다.

- **PASS:** 양 벤치마크 및 계획된 작은 표본이 유효하고 저장·반복·기준·availability 검사가 모두 성공.
- **PARTIAL:** 일부 유효 관측을 보존했지만 벤치마크/표본/무결성에 미해결 문제가 존재.
- **BLOCKED:** 유효 가격 관측 0건. membership 단계에서 막히면 Yahoo 접근의 실패라고 주장하지 않음.

분류: proxy CONNECT 403, provider authorization, rate limit, 원인 미확인 provider/gateway 403, incomplete frame, missing corporate actions, currency/unit, identity/source contract, schema/integrity, budget 및 diagnostic infrastructure. 원 오류 문자열을 보존하며 403만으로 프록시 또는 Yahoo 자체 거절을 단정하지 않는다. 공급자 거절은 측정된 verdict로 job 자체는 성공할 수 있다. 구현/실행 인프라 오류는 CI 실패다.

## 실패 시 공급자 검토안

아래는 자동 fallback 또는 검증 완료 adapter가 아니다. **현재 가격·계약·접근·정확한 field basis는 미검증**이며 공식 문서/견적과 소규모 별도 승인이 필요하다. Yahoo/yfinance는 무료 접근 경로지만 공식 지원 API/SLA가 없고 일회 성공은 반복 운영 신뢰성·재배포 권리의 증명이 아니다.

| 후보 / 공식 확인 경로 | 검토 범위·과거 생존편향 | 가격·운영·통합 비용 |
|---|---|---|
| [Tiingo](https://www.tiingo.com/products/end-of-day-stock-price-data) / [pricing](https://www.tiingo.com/about/pricing) | 미국 주식·ETF EOD 후보. 원 OHLCV와 adjusted 값·dividend·split 계약 및 SPY/QQQ, 상장폐지/심볼 변경 coverage 확인 필요. 현재 constituents만으로 과거 universe를 구성할 수 없음. | API key와 사용량/이용 목적별 구독 조건 확인; 현재 금액 NOT_VERIFIED. REST adapter·rate-limit 처리·as-traded basis mapping·식별자·PIT membership 보완 필요. |
| [Massive/Polygon](https://massive.com/docs/rest/stocks/overview) / [pricing](https://massive.com/pricing) | 미국 주식/ETF aggregate 및 corporate-action endpoints 후보. adjusted 옵션의 정확한 의미, inactive securities·ticker events·분할/배당 가용시점 별도 확인 필요. 현재 심볼 조회만으로 survivorship 해결 안 됨. | API key, tier별 EOD/실시간/과거 깊이·사용량/라이선스 조건 확인; 현재 금액 NOT_VERIFIED. 복수 endpoint joins·action revision provenance·symbol mapping 비용. |
| [Nasdaq Data Link Sharadar](https://data.nasdaq.com/databases/SEP) | US equity daily panel 및 historical/delisted coverage 후보. ETF SPY/QQQ 포함 여부와 corporate-action/basis·permanent security ID를 계약으로 확인해야 하며 필요하면 ETF 별도 라이선스. PIT S&P 500 membership은 별도. | 유료 dataset/용도별 견적; 현재 금액 NOT_VERIFIED. bulk/table adapter·별도 action 연계·ETF 범위 보완·라이선스 검토 비용. |
| [Databento](https://databento.com/docs) / [pricing](https://databento.com/pricing) | 미국 거래소 market data·reference/security mapping 후보. 필요한 EOD OHLCV 생성/coverage, point-in-time symbology·상장폐지와 corporate-action 제품을 각각 확인. 가격과 membership를 한 계약이라고 가정하지 않음. | dataset/use-based 비용·거래소/상업 이용 조건 및 필요한 reference 상품 확인; 현재 금액 NOT_VERIFIED. venue/EOD 집계·calendar·reference/actions joins가 필요해 통합 범위가 상대적으로 큼. |

어느 후보도 기존 가격 기준과 영구 신원·공식 PIT membership를 자동 해결한다고 판단하지 않는다. 비교는 공급자 문서·라이선스·coverage와 운영 요구에 기반하며 미래 수익률을 사용하지 않는다. 이 PR에는 대체 공급자 요청·키 설정·adapter 변경이 없다.

## 최소 후속 단계

PASS라도 운영 활성화는 별도 owner 승인이다. 작은 표본 성공 이후 허용된 환경에서 현재 전체 constituent+SPY+QQQ의 bounded dry-run과 실제 action/identity/revision 검증을 먼저 수행한다. 이후 전용 수집 스케줄·isolated stage→허용된 가격/구성종목 namespace만 append하는 publisher를 별도 승인 PR로 추가한다. 이 PR은 production write와 daily scheduling을 포함하지 않는다.

PARTIAL/BLOCKED이면 해당 실행의 원 오류·환경·provider status를 먼저 검토하고 지원되는 source/라이선스 또는 표준 접근 환경을 선택한다. 쿠키·프록시·TLS·엔드포인트 우회나 전체 종목 재시도는 하지 않는다. 추가 요청은 이 결과와 정확한 변경 이유를 바탕으로 별도로 승인한다.

실제 Actions verdict·run/job/artifact 출처와 최종 테스트 결과는 진단 후 audit 및 PR 설명에 기록한다. 합성 테스트 통과를 실제 연결 성공으로 표현하지 않는다.
