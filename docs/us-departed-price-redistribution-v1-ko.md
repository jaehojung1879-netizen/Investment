# 이탈 가격 후보 재배포·보존 감사

2026-10-14, #241의 기존 취득 증거만 검토했다. 공개 접근은 이용·저장·재배포 허가가 아니며 아래 결과는 법률상 권리 확정이 아니다. [출처별 revision·라이선스 확인 기록](us-readiness/us-departed-price-redistribution-audit-v1.json)을 함께 보관한다.

| 출처 | 확인한 권리 근거 | 원자료 / 세션별 파생 데이터 |
|---|---|---|
| A teddykoker/survivorship-free-spy | pinned tree에 LICENSE 없음; WIKI 우선, Yahoo fallback | 모두 UNVERIFIED, 공개 배포 차단 |
| B WIKI 직접 API | CONNECT 403, 가격 취득 0; vendor terms/저장 grant 미확인 | 모두 UNVERIFIED |
| B omarkhursheed 카탈로그 | 라이선스 파일 없음; 카탈로그도 제3자 metadata | 모두 UNVERIFIED |
| B VermeirJellen 보조 카탈로그 | GPL-3.0/LGPL-3.0 코드 라이선스 존재; WIKI 데이터 권리 입증 아님 | 모두 UNVERIFIED |
| C Acelogic Wayback scraper | LICENSE 없음; 코드/README만 취득, archive 가격 0 | 모두 UNVERIFIED |
| D hackingthemarkets | LICENSE 없음; yfinance 기반 Yahoo 가격 | 모두 UNVERIFIED |
| E IanLKaplan | Apache-2.0 코드 라이선스; upstream Yahoo 데이터 grant 미확인 | 모두 UNVERIFIED |
| F jcwill415 | LICENSE 없음; Yahoo pandas_datareader 가격 | 모두 UNVERIFIED |
| G Stonks | LICENSE 없음; upstream API·조정 기준도 미확인 | 모두 UNVERIFIED |
| Stooq probe | CONNECT 403, 가격 취득 0 | 모두 UNVERIFIED |
| 기존 봉인 Yahoo 비교 자료 | pinned commit을 read-only 사용; vendor 권리 재확정 안 함 | 새 가격 payload 공개 없음 |

원자료 archive에는 가격 외에 기업명 카탈로그, code/README, controls와 보조 샘플도 포함되어 있어 **archive 전체**를 공개 이력에서 제외한다. 가격 정규화·회원기간 필터·조정 가격 변환은 upstream 권리 문제를 제거하지 않으므로 파생 패널도 제외한다. 공개 문서는 세션별 가격을 제공하지 않고 기존 취득의 집계 사실·오류 통계·출처 URL/revision/hash를 유지한다. 공급자 terms 원문/원 권리자의 데이터 grant는 확보하지 못했다. 코드 라이선스 또는 접근 성공으로 이를 추정하지 않는다.

## 보존 및 재현 한계

원자료 SHA `0fa0b576d04693cda88611b3ec19d2415d868c1af2189f0e29944f2d7ae835f4`, 파생 패널 SHA `41ef2da7e8bc6ee7a07ec58635e08a25452c7228cfb33d269a22e266f0b7aa59`는 로컬 사본과 대조했다. 원래 PR bundle도 검증했다. 접근 제한된 `/workspace/pr241-nonpublic-preservation/`와 기존 checkout 외부 취득 staging에 보존한다. **작업 공간 소멸 시 사본을 잃을 수 있다. 영구 비공개 저장소/백업 생성 또는 비용 지출은 하지 않았다.**

소유자는 작업 공간을 종료하기 전에 기존 소유자 통제 private dataset repository 또는 승인한 object storage로 원자료·패널·원래 manifest·bundle을 비공개 이전하고 SHA를 재검증해야 한다. private 저장 자체도 원공급자 이용·보관 조건 확인이 필요하다. 원자료를 새 public repository, release 또는 공개 Actions artifact로 업로드하지 않는다. 공개 URL 재수집의 현재 성공 여부는 재검사하지 않았으며 삭제·접근 제한·변경 가능성이 있다. 따라서 공개 PR만으로 exact-byte 실자료 재현을 보장하지 않는다. CI는 합성 checksum/관측 검증을 수행한다.

## 공개 이력 정리와 서버 잔존

기존 PR의 두 커밋 `746280552c06d7e6d5cf0d1fe35a05191f8b57db`, `a6da327fee14b39e2cbdd7fe3dc0a0380f5b3f51`을 포함하지 않는 새 이력으로 같은 브랜치를 갱신한다. 가격 압축 파일이 들어간 삭제 커밋을 덧붙이는 방법은 사용하지 않는다. P4 baseline 테스트 교정은 유지하고 production workflow·봉인 입력·결과·P4 identity는 수정하지 않는다.

**브랜치 rewrite는 GitHub의 기존 SHA 주소, PR cached diff/refs, CDN cache 및 외부 clone 삭제를 보장하지 않는다.** 소유자는 GitHub Support에 #241, 위 두 SHA 및 원래 `candidate_data/us-departed-public-price-v1/`의 raw/observations 압축 경로를 제공하고, 권리 미확인 데이터의 cached views 및 dangling PR refs 제거 가능성을 요청해야 한다. 이 작업에서 Support에 메시지를 보내거나 기존 CI 기록을 삭제하지 않는다. 서버 잔존 확인 결과와 최종 CI는 PR 본문/최종 보고에 제공한다. purge 확인 전 공개 제거 완료로 주장하지 않는다.

## 독립 연구 데이터셋의 다음 단계

212개 중 193개 source 파일, 175개 회원기간 후보, FULL 5 / PARTIAL 170 / NONE 37, 결측 256,402세션 중 186,910세션 후보 관측이라는 측정값은 유지한다. 새 데이터셋 검토의 근거로 유용하지만 권리·issuer/share class·조정 basis·기업 행동·terminal consideration 검증이 남아 있다. 비공개 영구 보존과 이용 권리를 먼저 확정하고 독립 candidate revision을 검증해야 한다. 기존 replay-v16/H63/P4 입력에 연결하거나 outcomes를 실행하지 않는다.
