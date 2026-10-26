# KR22 원천 수집: 이미 있는 것, 남은 것, 소유자 실행 방법 (2026-10-26)

**상태:** 원천만 다룬다. 이번 세션에서 새로 확보한 원본은 **0건**이다. 결과·가격·라벨은 하나도 읽지 않았다.

- 이 환경에서는 DART·KRX·KIND 호스트(`opendart.fss.or.kr`, `dart.fss.or.kr`, `kind.krx.co.kr`)가 모두 CONNECT 403으로 막혀 있다. `DART_API_KEY`도 없다. 우회하지 않았다.
- 숫자는 `kr22-repository-originals.json`(`kr22_repository_originals.py`)에서 나온다.

## 1. 이미 저장소에 있다: 다시 요청하지 않는다

산업 재단 v2는 이미 두 가지를 해 두었다.

- 모든 Top120 발행사에 대해 list.json A001(사업보고서) 조회를 마쳤다.
- 각 회계연도의 **최초 비정정 원본**을 공개 뷰어로 받아 `data/kr-industry-membership-foundation-v2`에 보존했다(v1 보존분 재사용 포함, 2,946 접수).

| `kr22-collection-plan.json` 요청 | 계획 수 | 저장소가 이미 답한 수 |
|---|---:|---:|
| 사업보고서 목록 조회(회계연도 칸) | 56 | **56** (선택 원본 또는 "목록상 원본 없음", 페이지 완료) |
| 연구 구간 16종목 최초 원본 사업보고서 | 140 | **140** 보존 (회사 개요·사업의 내용 본문 포함, corp code 정확 일치) |
| 계획이 '보유'로 적은 kr-raw 접수 32건 | 32 | 그 회계연도의 원본이 31건 보존 |

- 남는 1건은 010620 FY2020이다. kr-raw에는 접수 `20210312001202`가 있지만 v2 A001 목록에는 그해 원본이 없다. 정정 공시만 남은 연도로 보인다. 수치를 고치지 않고 불일치로 기록한다.
- **정정:** 앞선 보고에서 "가장 가치 높은 다음 과제 = 사업보고서 수집"이라고 한 것은 틀렸다. 사업보고서는 이미 저장소에 있다.

## 2. 보존된 원문에서 산업 분류를 다시 검증한 결과

- **명시적 KSIC 진술이 있는 종목은 012510(더존비즈온) 하나다.** FY2013–2020 사업보고서 8건에 `(나) 공시대상 사업부문의 구분 / 한국표준산업분류 : 응용 소프트웨어 개발 및 공급업 (J58222)`이 있다.
- **8건 모두 변경 없는 `kr_industry_membership_v2.admit`의 기계 검증을 통과한다.**
  - 원천 해시, 고유 locator, `openCorpInfoNew('00172291',` 식별자, 제목의 공시일을 확인했다.
  - known_from은 2014-03-31부터다.
- **그래도 채택되지 않는 이유는 두 가지다.**
  1. **v2 템플릿:** 동결된 템플릿은 "당사는 …" 같은 발행사 주어 문장만 읽는다. 표 형식 진술은 읽지 않는다. 그래서 v2 관측은 0건이다.
  2. **v4 크로스워크:** 보고된 라벨 `응용소프트웨어개발및공급업`은 동결된 v4 크로스워크에 없다. 같은 공시에 적힌 소분류 행 `582 소프트웨어개발및공급업`만 크로스워크(`COMMUNICATION_MEDIA_SOFTWARE`)와 정확히 일치한다.
- **채택하면:** 012510의 연구 구간 28개 구성원-월이 모두 분류된다. 16종목 전체 535개 중 28개다. 22종목 분모 기준 산업 적격은 0 → 1이 될 수 있다.
- **나머지 15종목:** 보존 원본 127건(회사 개요·사업의 내용 절) 어디에도 `표준산업분류`라는 낱말 자체가 없다.
  - 4개사(042670, 057050, 003600, 003450)는 계열회사 표에 자사 행과 업종이 있다.
  - 이 형식은 템플릿도 크로스워크도 정해진 적이 없어 후보로 세지 않았다.

## 3. 실제로 남은 요청

| 요청 | 건수 | 경로 | 키 필요 | 실행할 코드 |
|---|---:|---|---|---|
| 배당결정 공시 본문 | 141 (15종목) | `opendart.fss.or.kr` document.xml | **예** | `kr22_repository_originals collect-remaining`. 기존 `kr22_collection_plan.collect`와 `verify`를 그대로 쓰는 축소 계획이다(`kr22-remaining-plan.json`, digest `6eb1f93a…`) |
| 종결 공시 본문 | 35 (11종목) | `dart.fss.or.kr` 공개 뷰어 | 아니오 | **저장소에 없다.** v2 수집기(`scripts/collect_kr_industry_membership_v2.py`)는 사업보고서의 두 절만 받는다. #286 `xbrl_recovery`는 고정 68건의 IFRS 첨부만 받는다. 어느 쪽을 일반화할지는 소유자 결정이다(#286은 Codex 범위) |

## 4. 소유자가 고를 실행 방법

**A. 이 Claude 클라우드 환경에서 실행한다**

1. 환경 설정에서 Network access의 Allowed domains에 `opendart.fss.or.kr`과 `dart.fss.or.kr`을 추가한다. 설정은 세션 제목 표시줄의 클라우드 환경 메뉴 → Edit에 있다.
   - #286의 `network-block-evidence.json`에는 이 두 도메인을 담은 저장된 초안 `22b82dfb-2ffd-459c-808c-6695efefb2b8~cecfgdraft_6adde0d54bdc8199a16cef976f9faf74`이 기록되어 있다. "Publish 필요"로 표시되어 있다. 이 세션은 그 초안을 보거나 게시할 수 없다.
2. **배당결정 141건에만** `DART_API_KEY`를 환경의 Network secrets 또는 환경 변수로 넣는다. 키를 대화에 붙여 넣지 않는다. 공개 뷰어(종결 35건)는 키가 필요 없다.
3. 새 세션에서 실행한다.
   ```
   python -m research.industry_alpha_next_v1.kr22_repository_originals collect-remaining --output <빈 디렉터리> --max-calls 200
   python -m research.industry_alpha_next_v1.kr22_repository_originals verify-remaining --input <디렉터리>
   python -m research.industry_alpha_next_v1.kr22_repository_originals extract-remaining --input <디렉터리>
   ```

**B. 소유자 PC에서 실행한다**

- `research/industry-alpha-next-v1` 브랜치에서 `DART_API_KEY`를 설정하고 위 세 명령을 그대로 실행한다.
- 결과 디렉터리(raw/, manifest.json)를 PR로 커밋하면 이 세션이 검증과 재계산을 이어 받는다.

**C. GitHub Actions로 실행한다**

- 저장소 비밀 `DART`가 있고, 일일 `fundamentals` 작업이 DART에 닿는다(오늘 `signal-history` c6416ba).
- 그러나 새 작업을 넣으면 다른 연구의 워크플로 census 가드에 걸린다. #293이 같은 이유로 6개 실패했다. 소유자의 거버넌스 결정이 필요하다.
- 이 세션은 workflow dispatch 권한도 없다(403).

## 5. 수집해도 바뀌지 않는 것

- **배당락일 의미:** 현금배당결정 양식은 배당기준일을 적는다. 배당락일 항목은 없는 것으로 예상한다. 저장소 규칙은 DIRECT만 인정하므로, 141건을 모두 받아도 0/22일 가능성이 높다.
  - 바꾸려면 날짜가 붙은 KRX 결제 주기·배당락 규칙의 공식 출처를 소유자가 제공하고 봉인해야 한다.
  - 출처 후보는 KRX 유가증권시장 업무규정이다. 이 세션에서는 `law.krx.co.kr`, `law.go.kr`도 막혀 있다.
- **총수익 라벨 적격:** 산업과 배당락일이 모두 필요하므로, 위 두 결정 없이 0/22에서 움직이지 않는다.
- **종결 실행 확인:** 3건(000060·008560·057050)은 승계 회사 상장주식 증가가 관측되지만, 보존 문서에 신주 수가 없다. 승계 회사의 보존 사업보고서에서도 그 수치를 찾지 못했다. 종결 공시 35건에 들어 있을 가능성이 크다.
