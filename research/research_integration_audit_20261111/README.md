# Research Integration Audit — 2026-11-11

[한국어 결정 보고서](REPORT-ko.md). 감사 전용, main@37f8cbf6 기준의 추가 파일이다. 기존 PR·workflow·production·봉인·소비된 lock을 변경하지 않는다.

- `evidence/github-snapshot.json`: 여섯 PR의 정확 HEAD/base, 자체 변경 파일, 동일 HEAD CI.
- `evidence/lineage.json`: 실제 ancestry, base 대비/main 대비 범위, 경로 중복 및 가상 merge-tree 검사. ref/index/working tree 병합이나 원격 merge는 아니다.
- `evidence/ci-job-*.log.gz`: 실제 지정 run과 최근 완료 Pages의 public decoded 로그. CR/마지막 newline 정규화 후 저장했고 ZIP 원문 해시라고 주장하지 않는다.
- `evidence/protected-321.json`: 등록 protected 파일235개·formal job·requirements 보존.
- `reviews/`: KR/US와 같은 팀 #332 second reader 상세 검토. Lead의 #332 판단은 AUTHOR_REVIEW이고 외부 비작성자 승인은 미완료다.
- `evidence/*checks.json`, `v2-*.json`: 결과/원천/원장 산술. 새 전략·모델 적합·백테스트가 아니다.
- `checks/*.py.txt`: 해당 검산에 실제 사용한 검사 원문. 감사 당시 scratch 경로를 보존한 실행 기록이며 전략 모듈의 배포 코드가 아니다. 입력은 각 검토의 고정 HEAD에서 `git archive`한 연구 폴더와 기존 공식 자료다. `/workspace/Investment`는 고정 #332 checkout, `/workspace/integration-review-notes/{kr,us}`는 HEAD별 추출 디렉터리였다. 새 clone에서는 이 경로를 재구성하거나 경로만 조정한 후 검사한다. 경로를 바꾼 코드를 기존 source hash로 주장하지 않는다.
- `evidence/official-issuer-retrieved-20261111.xls.gz`: 같은 공식 URL에서 새로 취득한 XLS. 원시 SHA와 공통세션 대조는 kr-checks에 있다. 원 연구 종료일 이후 추가 행을 미래 추천에 사용하지 않았다.
- `submission-verification.json`, `manifest-sha256.json`: 실제 검사 결과와 최종 감사 파일 해시. 전체 연구의 경제성 인증은 아니다.

## 재현 범위

필요 Git commit은 lineage.json의 main/HEAD/base와 #321 역사 parent23522002, consumed09ba076f 및 원래 source commit4ea107ed다. 얕은/partial clone은 exact historical blob을 먼저 읽기 전용으로 확보해야 한다. 이 과정이 빠진 최초 운영 검사 34fail/73pass와 blob 확보 후107pass를 모두 보존한다. Git history를 없애는 squash/rebase와 오브젝트 준비는 서로 별도 위험이다.

```bash
# 새 실행은 Git 계보 검사뿐이며 전략·학습·원래 연구 runner를 호출하지 않는다.
python research/research_integration_audit_20261111/check_lineage.py
```

merge-tree의 누적 부모용 commit-tree는 author/date를 고정한 **ref 없는 감사 객체**다. 같은 입력에서 출력JSON byte 일치를 확인했다. 그 객체를 어떤 브랜치에도 게시하지 않았다.

#321 격리 detached checkout에서 운영 관련107개 테스트를 실행했다. 원본 main 전체 suite를 이번 문서 전용 PR에서 다시 통과했다고 주장하지 않는다. 여섯 원격 HEAD의 실제 CI와 실패 로그는 별도 보존한다. 자동 PR CI는 일반 main 설치 정책의 영향을 받으며 #321 승인·통합과 구분한다.

공식 H10/FRED 공표 근거는 원문 URL과 짧은 인용으로 기록했다. 보존된 문서/데이터만으로 검증 불가능한 일별 전략 NAV·예측/label·독립 vendor·기업행동/종결 완전성은 보고서에 명시했다. reviewer 노트 복사본의 링크 표기만 감사 디렉터리에 맞춰 정리했으며 원래 연구 파일은 손대지 않았다.
