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

*(이 아래는 실제 워크플로 실행 후 채워진다 — PR 본문에도 같은 요약이 있다.)*
