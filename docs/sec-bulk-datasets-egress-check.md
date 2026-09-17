# SEC 대량 재무제표 ZIP — GitHub Actions에서 접근 가능한가, 다시 잰다

## 왜 다시 재는가

이 테스트는 **이미 한 번 돌았다.** 2026-09-04 04:50 UTC, `Probe SEC bulk financial
statement datasets` 워크플로가 정확히 `www.sec.gov/files/dera/data/financial-statement-data-sets/{quarter}.zip`
경로로 `2025q2`와 `2013q1`을 요청했고, 둘 다 실제 `HTTP 403`을 받았다:

```
SEC.gov | Request Rate Threshold Exceeded
```

fair-access User-Agent(`InvestmentResearchDashboard/1.1 jaehojung1879-netizen@users.noreply.github.com`)를
썼고, 재시도 3회 모두 같은 응답이었다. 이건 진짜 측정이었다 — 추측이 아니다.

그런데 이 측정은:

- **12일 전이다.** SEC 접근은 시점에 따라 바뀐다는 게 이미 이 리포지토리 자체의 기록이다
  — `data/institutional_13f_cache.json`은 2026-08-15 23:00 UTC에 `data.sec.gov`가
  `LIVE_SEC`로 이 리포를 서빙했다고 남겨져 있고, 3주 뒤엔 같은 호스트가 막혀 있었다.
- **redirect chain, 응답 헤더, egress IP, ZIP 매직바이트 확인, 같은 실행 안에서의
  3원 비교(ZIP vs data.sec.gov vs Archives) 중 아무것도 기록하지 않았다.** 판정에 필요한
  근거가 "403이었다" 한 줄뿐이다.
- **User-Agent를 하나만 썼다.** header-isolation 프로브가 이미 UA 형태 4가지를 두
  호스트에 대해 다 막힌다고 쟀지만, 그건 `data.sec.gov`/`company_tickers.json`이지
  이 ZIP 경로는 아니었다.

그래서 **재검증할 가치가 있다**고 판단했고, 별도 확인 없이 바로 진행했다.

## 이번에 무엇을 쟀나

`scripts/probe_sec_bulk_datasets.py` (기존 프로브를 확장, 새 파일 아님)가 한 실행 안에서:

1. **분기 ZIP에 요청 두 번, 재시도 없이.**
   - 요청 1: User-Agent를 아예 안 보냄 (urllib 기본값 — SEC가 부르는 정확히 그
     "Undeclared Automated Tool" 모양)
   - 요청 2: fair-access User-Agent로
   - 둘 다 실패하면 확실히 존재하는 다른 분기(`2025q4`)로 한 번 더 교차검증
2. **매 요청마다 기록**: 최종 URL, redirect chain(각 hop의 상태·Location),
   응답 상태, 관련 헤더(Content-Type·Content-Length·Server·Cache-Control 등),
   실제 다운로드 바이트, 응답 앞부분이 ZIP 매직바이트(`PK\x03\x04`)인지 SEC 차단
   HTML인지, 사용한 User-Agent, 요청 시작/종료 시각.
3. **같은 실행에서 3원 비교**: `data.sec.gov/submissions/CIK0000320193.json`(작은 JSON),
   `www.sec.gov/Archives/edgar/data/320193/index.json`(Archives, 작은 JSON) — SEC
   전체가 막힌 건지 이 ZIP 경로만인지 가른다.
4. **runner의 egress IP** — 외부 IP 에코 서비스로, SEC에 낭비되는 요청 없이.
5. **ZIP이 실제로 오면**: 압축 해제 가능 여부, `sub.txt`/`num.txt`/`tag.txt`/`pre.txt`
   존재 여부와 크기, 무결성(`testzip()`) — 전부 메모리에서만, 디스크에 아무것도
   쓰지 않고 프로세스 종료 시 버려진다. 리포지토리에 커밋되는 바이너리는 없다.

## 판정 기준

- **A. VIABLE** — 어느 쪽이든 ZIP이 실제로 왔다.
- **B. PARTIALLY_VIABLE** — ZIP은 막혔지만 `data.sec.gov`나 Archives 중 하나는 서빙됐다.
- **C. BLOCKED** — 셋 다 첫 요청부터 막혔다.

## 결과

**2026-09-17T00:01Z, Probes 워크플로 run #8 (`main`, `sec-bulk-datasets`)에서 실제로 측정됨.**
egress IP `20.168.93.149`, fair-access UA
`InvestmentResearchDashboard/1.1 jaehojung1879-netizen@users.noreply.github.com`.

| 요청 | 최종 URL | 상태 | 바이트 | 소요 | 판정 |
|---|---|---|---|---|---|
| `2026q2.zip`, UA 없음, 재시도 없음 | `.../financial-statement-data-sets/2026q2.zip` (리다이렉트 없음) | 403 | 1,925B | 0.127s | BLOCK_PAGE |
| `2026q2.zip`, fair-access UA, 재시도 없음 | 동일 (리다이렉트 없음) | 403 | 1,925B | 0.038s | BLOCK_PAGE |
| `2025q4.zip`, fair-access UA, 교차검증 | — | 403 | 1,925B | 0.062s | BLOCK_PAGE |
| `data.sec.gov/submissions/CIK0000320193.json` | — | 403 | 4,819B | 0.079s | BLOCK_PAGE |
| `www.sec.gov/Archives/edgar/.../index.json` | — | 403 | 4,819B | 0.064s | BLOCK_PAGE |

다섯 요청 모두 리다이렉트 없이 요청한 URL에서 바로 403 차단 페이지를 받았다(1,925B는 ZIP 경로용, 4,819B는
JSON 경로용 차단 페이지 — 경로별로 다른 템플릿이지만 둘 다 `pipeline.sec_access.BLOCK_MARKERS`에 걸림).
UA 유무는 결과를 바꾸지 않았고, 분기(`2026q2` vs `2025q4`)도 바꾸지 않았다. 전체 5요청이 8초 워크플로 실행
시간 중 0.4초 미만에 끝났다 — SEC 쪽에서 바디를 조립하지 않고 엣지에서 즉시 거부한다는 뜻이다(레이턴시로도
구분됨).

**판정: C. BLOCKED.** 분기 ZIP, `data.sec.gov`, Archives 세 경로 모두 첫 요청부터 막혔다. 이 워크플로 파일의
`판정` 로직이 BLOCKED를 exit code 1로 반환하도록 설계되어 있어 GitHub Actions UI에는 이 실행이 "failure"로
표시되지만, 이건 스크립트 오류가 아니라 **의도된 종료 코드로 보고된 실제 측정 결과**다 — Probe 스텝 로그에
전체 진단이 그대로 찍혀 있다.

PR 본문에도 같은 요약이 있다.
