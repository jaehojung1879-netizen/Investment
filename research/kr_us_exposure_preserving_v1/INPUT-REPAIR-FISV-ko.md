# 새 성과 계산 전 고정한 FISV 원 가격 공백 복구

기준 PR #350 `36ac329261f8f9000935e524d8a28c2005524c10`. 새 전략·새 대조군 성과를 계산하기 전에 입력만 감사했다. 기존 가격·features·판단일·신호·순위·비용 파일은 바꾸지 않는다.

원 미국 TR 패널 3,947세션×635열의 FISV `2025-11-12` Close 한 칸이 null이다. 기존 cached Yahoo HTTP 원문의 같은 날짜 Close는 `64.37999725341797`이며 원문 SHA-256은 `b525ca5ecee2c73f59c504cc6424e3ac23ac8e40b1dcc0442e3ea43a4d76bb91`이다. 새 공급원 조회나 이전 종가 대체를 하지 않는다.

봉인된 동일 커밋 `704d7db6`의 FISV 기업행위는 2013-12-17·2018-03-20의 각2:1 분할, 배당0이다. 원 `pipeline.price_adjustment.to_total_return`을 이 raw Close와 같은 기업행위에 호출한 TR Close는 `257.5199890136719`다. 기존 nonnull3,943세션을 같은 방식으로 대조한 최대 상대 오차는0이다. cached Yahoo 범위 밖 기존 nonnull 마지막3세션은 검산 범위에서 제외하고 그대로 둔다.

다음 복구만 허용한다.

1. 기존 `/workspace/batch-inputs/us/close.pkl`과 `features.pkl`은 불변이다. 새 `/workspace/exposure-inputs/us/close-repaired.pkl` 사본의 위 null 한 칸만 복구한다.
2. 기존 모든 nonnull 셀 및 다른 ticker·날짜가 같고 변경 셀이 정확히1개인지 assert한다. 원본/사본/source 함수/원문/기업행위 참조와 SHA를 보존한다.
3. 기존 신호를 재생성하거나 점수·적격·순위·가중치를 바꾸지 않는다. FISV 결측을 쓰던 기존 신호의 미측정도 그대로다. 복구는 새 연구의 결과 가격·장부 평가 입력에만 적용한다.
4. 기존 #350의 판단일별 선택·성과가 영향을 받는지 대조하고 영향이 있으면 숨기지 않는다. 기존 산출물을 덮어쓰지 않는다.

이는 FISV를 담는 넓은 기준 복제책의 가격 측정 공백을 복구하는 입력 정정이며 종목 선택 규칙 변경이 아니다. 일반적인 결측 carry나 미해결 상장폐지의 현금화 규칙으로 확장하지 않는다. 전체 감사 근거는 `fisv-repair-proposal.json`, `fisv-reconstruction-comparison.csv.gz`, `fisv_source_audit.py`이며 저장소 밖 `/workspace/exposure-inputs/us/`에서 준비했다.
