# Investment Insight — PAPER ONLY 안전 모드

이 저장소는 공개 데이터 기반 투자 분석 대시보드입니다. **현재 기본값은 `PAPER_ONLY=true`이며 실제 매매 추천, STRONG BUY/SELL, 상승확률 단정, 켈리 비중 추천은 비활성화**되어 있습니다.

## 안전 원칙

- seed/stale/modelsTrained=0/coverage<95/품질 게이트 미통과 상태에서는 추천 영역을 렌더링하지 않습니다.
- 모델 출력은 품질 게이트를 통과하기 전까지 `상승확률`이 아니라 `모델 점수`로 표시합니다.
- `core`는 공개 저장소에 수량·평균단가·총자산이 없으므로 “보유종목”이 아니라 “추적 종목”입니다.
- 포트폴리오 정보가 없는 공개 Pages 산출물에는 `suggestedWeightPct`를 노출하지 않습니다.
- 현재 구성종목 기반 유니버스는 생존편향이 있으며 Yahoo Finance 데이터 품질 한계가 있습니다.
- FRED 매크로 데이터는 vintage/point-in-time 데이터가 아니므로 과거 검증에는 revision bias 가능성이 있습니다.

## 품질 게이트

각 ticker/horizon은 최소 OOS 252개, threshold 초과 signal 30개, precision lift > 5%p, lift 신뢰구간 하한 > 0, Brier Skill Score > 0, 최근/전체 OOS 방향 일치, calibration 안정성 등을 통과해야 합니다. 통과하지 못하면 `qualityGrade=REJECT`이며 추천 테이블에서 제외됩니다.

## 실행

```bash
pip install -r requirements.txt
pytest
python -m pipeline.build
python -m pipeline.validate data/site-data.json
```

`python -m pipeline.validate`는 production 배포에서 seed/stale/모델 0/낮은 커버리지를 non-zero exit로 실패시킵니다.

## 감사 산출물

빌드마다 `data/audit.json`에 generatedAt, meta, fold 경계, OOS metrics, eligibility, warning/block reason을 기록합니다. GitHub Actions는 테스트와 validation이 통과한 뒤에만 Pages 배포를 진행해야 합니다.

## 실전 활성화 조건

실전 추천은 최소 3~6개월 paper trading, 50건 이상 시간순 신호, 비용 차감 후 양의 기대성과, 벤치마크 대비 개선, 허용 가능한 MDD, 섹터/기간 집중도 완화, calibration/OOS 품질 유지가 확인되기 전까지 활성화하지 않습니다.
