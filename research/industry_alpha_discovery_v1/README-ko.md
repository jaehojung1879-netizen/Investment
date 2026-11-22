# industry-alpha-discovery-v1 — 산업 실물정보 기반 알파 발굴

기준 브랜치: `research/next-alpha-program-v1`(#356, `6b1f1d57`). #356의 산업부 월간 수출 수집기(`research/industry_first_release_v1/collect_kr_trade.py`)를 **그대로 import해서** 재사용하고, 빠진 부분(2013~2023 HWP 보도자료, 관세청 10·20일 속보, 산업활동동향)만 보탰다.

| 단계 | 문서·파일 |
|---|---|
| A. 메커니즘 | `MECHANISM-ko.md` |
| A. 데이터 적격성 | `data/eligibility.json`, `DATA-ELIGIBILITY-ko.md` |
| B. 사전등록 | `PREREGISTRATION.md`, `protocol.json`, `protocol.sha256` (수익률 계산 전 커밋) |
| C. 실행 승인 | `authorization.json` (프로토콜·코드·입력 해시) |
| C. 결과 | `results/result.json`, `REPORT-ko.md` |

## 코드

| 파일 | 역할 | 가격을 읽는가 |
|---|---|---|
| `collect_releases.py` | KDI 경제정보센터 목록에서 산업부 월간·관세청 속보·산업활동동향 첨부(PDF·HWP·HWPX)를 내려받는다 | 아니오 |
| `hwp_text.py` | HWP5(OLE+zlib 레코드)·HWPX(zip XML) 문단 텍스트 추출. 외부 변환기 없음 | 아니오 |
| `parse_motie_hwp.py` | HWP 품목표: 머리글의 월 라벨 → 열, 금액 다음 증감률 | 아니오 |
| `parse_all.py` | 모든 보도자료 → `data/*.csv`, `parse-log.json` | 아니오 |
| `signals.py` | 시점 기준(as-of) G3·가속도, 개정 반전, 속보 서프라이즈 | 아니오 |
| `eligibility.py` | 범위·결측·공표 시차·개정·검정력(σ 단위) | 아니오 |
| `fetch_prices.py` | Yahoo 일별 수정종가(가격은 git 밖, 해시만 커밋) | 가격 수집만 |
| `engine.py` | 초과수익, Newey-West, 블록 부트스트랩, Holm, 30% 틸트 경로·비용 | 예 |
| `execute.py` | 승인 확인 후 1회 실행 | 예 |

## 재실행

```bash
python -m research.industry_alpha_discovery_v1.collect_releases --raw <git 밖> --list <kdi-list.json> --families MOTIE,FLASH10,FLASH20
```

```bash
python -m research.industry_alpha_discovery_v1.collect_releases --raw <git 밖 iip> --list <kdi-list.json> --families IIP
```

```bash
python -m research.industry_alpha_discovery_v1.parse_all --raw <git 밖> --raw-iip <git 밖 iip>
```

```bash
python -m research.industry_alpha_discovery_v1.eligibility
```

```bash
python -m research.industry_alpha_discovery_v1.fetch_prices --private <git 밖>
```

`execute.py`는 `results/result.json`이 이미 있으면 실행을 거부한다(1회 실행 규칙).
