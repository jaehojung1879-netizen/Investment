'use strict';
const $ = (s) => document.querySelector(s);
const fmt = (v, suf = '', d) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : `${typeof v === 'number' && d !== undefined ? v.toFixed(d) : v}${suf}`;
const sp = (v) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : `${v >= 0 ? '+' : ''}${v}%`;
const pct0 = (v) => fmt((v ?? 0) * 100, '%', 0);
const regCls = (r) => r === 'Bull' ? 'bull' : r === 'Bear' ? 'bear' : 'trans';
const regKo = (r) => r === 'Bull' ? '상승' : r === 'Bear' ? '하락' : '전환';
const mean = (a) => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;

// Reusable user-facing copy. Technical codes remain available in details/title.
const COPY = Object.freeze({
  blocked: '데이터 안전 기준을 충족하지 못해 판단과 비중을 숨겼습니다.',
  entryWithheld: '안전 기준에 따라 진입 판단을 표시하지 않습니다.',
  signalWithheld: '안전 기준에 따라 단기 참고 신호를 표시하지 않습니다.',
  validationPending: '검증 데이터를 축적하고 있습니다.',
  fallback: '모델 신호가 실제 이후 성과로 이어졌는지 확인한 표본이 아직 부족합니다. 현재 비중은 Kelly가 아니라 컨빅션 위험가중으로 정합니다.',
  noChange: '이전 실행 대비 주요 변화 없음',
  disclaimer: '개인 리서치·교육 목적의 정량 도구이며 투자 조언이나 개인화 추천이 아닙니다. 과거 성과는 미래를 보장하지 않습니다. 데이터 모드·검증 상태·출처를 함께 확인하세요.',
});
const USER_STATUS = Object.freeze({
  SHADOW_INSUFFICIENT_HISTORY: '검증 데이터 축적 중',
  SHADOW_READY: '실험적 모델 결과',
  ACTIVE_PAPER: 'Paper 운용 중',
  ACTIVE_VALIDATED: '검증 완료',
  FALLBACK_RISK_WEIGHTED: '데이터 부족',
  OPTIMIZATION_FAILED: '안전 차단',
  BLOCKED: '안전 차단',
  DISABLED: '데이터 부족',
  PENDING_PAPER_HISTORY: '검증 데이터 축적 중',
});
// The allocation rule actually in force — separate from the validation status,
// because "Kelly is not active yet" is not the same as "there is no method".
const ALLOC_METHOD = Object.freeze({
  CONVICTION_TILTED_RISK_PARITY: {
    name: '컨빅션 위험가중',
    how: '알파 순위 대비 하방변동성으로 종목을 고르고, 하방변동성 역가중에 순위 틸트(0.5~1.5배)를 적용합니다.',
  },
  BLENDED_CONSTRAINED_FRACTIONAL_KELLY: {
    name: 'Fractional Kelly 혼합',
    how: '실측 ledger 기대 초과수익과 지역 active 공분산으로 푼 제약 Kelly 해를 기준 비중과 혼합합니다.',
  },
});
const SELECT_EXCLUSION_KO = Object.freeze({
  BELOW_TARGET_COUNT_CUTOFF: '목표 종목 수에서 밀림',
  SECTOR_NAME_LIMIT: '동일 업종 종목 수 상한',
  REGION_NAME_LIMIT: '동일 지역 종목 수 상한',
  ALPHA_BELOW_SELECTION_FLOOR: '알파 백분위 하한 미달',
  ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING: '진입·리서치 상태가 비중 배정 차단',
  NO_FACTOR_EVIDENCE: '팩터 근거 없음',
});
const CONCENTRATION_KO = Object.freeze({
  SINGLE_DIGIT_NAME_COUNT_IDIOSYNCRATIC_RISK: '종목 수가 적어 개별 종목 사고에 그대로 노출됩니다',
  EFFECTIVE_NAMES_BELOW_2_5: '유효 종목수 2.5 미만 — 사실상 2종목 포트폴리오에 가깝습니다',
  TOP_NAME_ABOVE_40PCT_OF_EQUITY: '1위 종목이 주식 비중의 40%를 넘습니다',
});
// Kelly activation ladder. The code says which EVIDENCE CLASS is carrying the
// expected return; the Korean label is what a person reads.
const EVIDENCE_STATUS = Object.freeze({
  NO_EVIDENCE: '검증 근거 없음',
  HISTORICAL_PRIOR_ONLY: '과거 OOS 근거 준비 중',
  HISTORICAL_OOS_SUPPORTED: '과거 OOS 검증 활용 중',
  PROSPECTIVE_EARLY: '실시간 검증 축적 중',
  PROSPECTIVE_CONFIRMED: '실시간 검증 우세',
  ACTIVE_PAPER: 'Paper 운용 중',
  ACTIVE_VALIDATED: '검증 완료',
});
const RADAR_TIER_KO = Object.freeze({
  VALIDATED_OPPORTUNITY: '검증된 기회',
  EMERGING_OPPORTUNITY: '관찰 필요한 변화',
  CRITICAL_WARNING: '즉시 점검',
  ELEVATED_WARNING: '악화 관찰',
  WATCH: '관심 목록',
});
const RADAR_TIER_CLASS = Object.freeze({
  VALIDATED_OPPORTUNITY: 'bull', EMERGING_OPPORTUNITY: 'gold',
  CRITICAL_WARNING: 'bear', ELEVATED_WARNING: 'gold', WATCH: 'trans',
});
const RADAR_NOTE_KO = Object.freeze({
  VOLUME_SURGE_WITH_PRICE_DECLINE_NOT_AN_OPPORTUNITY: '거래량은 늘었지만 가격이 밀리고 있어 기회로 보지 않습니다',
  NO_RECENT_CHANGE_DETECTED: '최근 의미 있는 변화가 없습니다',
  SINGLE_SIGNAL_ONLY: '단일 신호만 감지되어 확신이 낮습니다',
  SIGNAL_CONVERGENCE_BELOW_VALIDATION_BAR: '신호는 모였지만 검증 기준에 미치지 못합니다',
  HISTORICAL_MODEL_NOT_VALIDATED_RESEARCH_ONLY: '과거 검증 모델이 통과 기준을 넘지 못해 리서치 참고로만 표시합니다',
  ENTRY_DOWNGRADE_WITH_TREND_BREAKDOWN: '진입상태 악화와 추세 이탈이 동시에 나타났습니다',
  NO_DETERIORATION_DETECTED: '악화 신호가 없습니다',
});
const ML_STATUS_KO = Object.freeze({
  ACTIVE: '과거 OOS 학습 모델 적용 중',
  NOT_TRAINED: '학습 데이터 없음 — 규칙 기반 변화 점수 사용',
  REJECTED_BY_ACCEPTANCE_GATE: '검증 기준 미달로 모델 미적용 — 규칙 기반 변화 점수 사용',
  DATASET_INSUFFICIENT_FOR_REFIT: '재학습 표본 부족 — 규칙 기반 변화 점수 사용',
  NO_MODEL_FOR_THIS_RADAR: '이 레이더용 학습 모델 없음 — 규칙 기반 변화 점수 사용',
});
const statusLabel = (code, fallback = '검증 데이터 축적 중') => USER_STATUS[code] || EVIDENCE_STATUS[code] || fallback;
const modeLabel = (mode) => ({ live: '실데이터', seed: '예시 데이터', synthetic: '합성 데이터', stale: '지연 데이터' }[mode] || '상태 미상');
const trendCue = (v) => v == null ? '→' : v > 0 ? '▲' : v < 0 ? '▼' : '→';

let NAMES = {};
let DATA = {};
const tkName = (t) => NAMES[t] || t;
const tkSub = (t) => (NAMES[t] ? ` <span class="tk">${t}</span>` : '');
const tkLink = (t) => `<span class="tklink" data-tk="${t}">${tkName(t)}</span>${tkSub(t)}`;

// --- v2 label maps ---
const VIEW = {
  POSITIVE: ['긍정', 'bull'], NEUTRAL: ['중립', 'trans'],
  NEGATIVE: ['부정', 'bear'], DATA_INSUFFICIENT: ['데이터부족', 'na'],
};
const ENTRY = {
  ACCUMULATE_GRADUALLY: ['분할 매수', 'bull'], WATCH: ['관찰', 'trans'],
  WAIT_FOR_PULLBACK: ['되돌림 대기', 'gold'], EVENT_RISK: ['이벤트 위험', 'bear'], AVOID: ['회피', 'bear'],
};
// Worst -> best, matching pipeline.entry.ENTRY_STATES reversed. Used to tell an
// entry upgrade from a downgrade in the daily change bar.
const ENTRY_RANK = { AVOID: 0, EVENT_RISK: 1, WAIT_FOR_PULLBACK: 2, WATCH: 3, ACCUMULATE_GRADUALLY: 4 };
const REGIME_KO = {
  Goldilocks: '골디락스', Reflation: '리플레이션', Stagflation: '스태그플레이션',
  'Deflation/Slowdown': '디플레·둔화', 'Transition/Low confidence': '전환·저신뢰',
};
const REGIME_GUIDE = {
  Goldilocks: {
    one: '성장은 빨라지고 물가는 둔화되는, 위험자산에 가장 우호적인 조합입니다.',
    watch: '기업이익과 고용의 개선이 이어지는지, 물가 둔화가 멈추지 않는지 확인합니다.',
    risk: '좋은 뉴스가 이미 가격에 많이 반영됐거나 물가가 다시 뛰면 빠르게 리플레이션으로 이동할 수 있습니다.',
  },
  Reflation: {
    one: '경기 회복·성장 가속과 물가 상승 압력이 동시에 나타나는 국면입니다.',
    watch: '실물·가치·에너지 업종이 상대적으로 유리할 수 있지만 장기금리와 원가 부담을 함께 봐야 합니다.',
    risk: '물가만 오르고 성장이 꺾이면 스태그플레이션으로 악화될 수 있습니다.',
  },
  Stagflation: {
    one: '성장은 둔화하는데 물가 압력은 커지는, 주식과 채권 모두 까다로운 국면입니다.',
    watch: '퀄리티·저변동·현금흐름과 실물자산 방어력을 우선 확인합니다.',
    risk: '에너지 충격, 임금·서비스 물가, 신용 스프레드 확대가 핵심 위험입니다.',
  },
  'Deflation/Slowdown': {
    one: '성장과 물가가 함께 둔화하는 국면으로 경기민감 자산의 이익 기대가 약해질 수 있습니다.',
    watch: '장기채·퀄리티 방어가 상대적으로 유리할 수 있지만 신용 악화를 확인해야 합니다.',
    risk: '침체가 깊어질 경우 실적 하향과 디폴트 위험이 커집니다.',
  },
  'Transition/Low confidence': {
    one: '성장·물가 신호가 엇갈리거나 데이터 신뢰가 낮아 국면을 단정하지 않는 상태입니다.',
    watch: '한 번의 숫자보다 다음 2~3회 발표에서 같은 방향이 이어지는지 확인합니다.',
    risk: '확신이 낮은 구간에서 과도한 자산배분 변경을 피합니다.',
  },
};
const INDEX_GUIDE = {
  '^KS11': '한국 유가증권시장 대표 지수입니다. 대형 수출주와 반도체 비중이 커 원/달러, 글로벌 제조업, 메모리 업황의 영향을 크게 받습니다.',
  '^KQ11': '한국 성장주·중소형주 비중이 큰 시장 지수입니다. 금리와 유동성, 바이오·2차전지·IT 투자심리에 민감합니다.',
  '^GSPC': '미국 대형주 500개를 담은 대표 지수입니다. 미국 기업이익과 글로벌 위험선호의 핵심 기준입니다.',
  '^IXIC': '기술·성장주 비중이 높은 나스닥 종합지수입니다. 장기금리와 AI·반도체 이익 기대에 민감합니다.',
  '^DJI': '미국 우량 대형주 30개로 구성된 가격가중 지수입니다. 전통 산업과 경기민감주의 흐름을 함께 봅니다.',
  '^SOX': '미국 상장 주요 반도체 기업 지수입니다. AI 투자, 메모리·파운드리 업황, 공급망 사이클을 빠르게 반영합니다.',
  '^VIX': 'S&P 500 옵션이 반영하는 향후 약 30일 기대 변동성입니다. 높을수록 시장 불안이 크지만 방향 예측값은 아닙니다.',
  'KRW=X': '1달러를 사는 데 필요한 원화입니다. 상승은 원화 약세, 하락은 원화 강세를 뜻합니다.',
  'DX-Y.NYB': '주요 통화 대비 미국 달러의 강도를 나타냅니다. 강달러는 글로벌 유동성과 신흥시장에 부담이 될 수 있습니다.',
  'BTC-USD': '비트코인의 미국 달러 가격입니다. 24시간 거래돼 주식시장 휴장 중 위험선호 변화도 반영합니다.',
  'GC=F': '국제 금 선물 가격입니다. 실질금리, 달러, 안전자산 수요의 영향을 받습니다.',
};
const viewBadge = (v) => { const [ko, c] = VIEW[v] || [v, 'trans']; return `<span class="vbadge v-${c}">${ko}</span>`; };
const entryBadge = (e) => { const [ko, c] = ENTRY[e] || [e, 'trans']; return `<span class="ebadge e-${c}">${ko}</span>`; };
const topPct = (p) => p != null ? `상위 ${Math.max(1, Math.round(100 - p))}%` : '—';

const fgLabel = (s) => s == null ? '—' : s < 25 ? '극도의 공포' : s < 45 ? '공포' : s < 55 ? '중립' : s < 75 ? '탐욕' : '극도의 탐욕';
const fgCls = (s) => s == null ? 'g-trans' : s < 45 ? 'g-bear' : s < 55 ? 'g-trans' : 'g-bull';
const regBadgeCls = (s) => s == null ? 'trans' : s < 45 ? 'bear' : s < 55 ? 'trans' : 'bull';

// --- Popover explanations ---
const EXPL = {
  status: ['데이터 상태 · 검증 상태', '<b>runMode</b>(researchOnly·paperTrading·liveValidated)는 사용 방식, <b>dataMode</b>(live·seed·stale·synthetic)는 숫자의 실체를 나타냅니다. liveValidated는 config만으로 부여되지 않고 paper ledger 검증을 거쳐야 합니다. 빌드 커밋 SHA와 marketAsOf/sourceAsOf로 어느 코드가 언제 데이터로 만든 결과인지 추적합니다. 차단(blocked) 상태면 단기·장기 액션과 비중이 모두 숨겨집니다.'],
  regime: ['매크로 국면 · 위험예산', '<b>6축(성장·물가·유동성·금융여건·위험선호·이익/신용)</b>은 진단에 표시하며, 국면 라벨은 성장×물가로 판정하고 금융여건·위험선호로 위험예산만 보정합니다. 지표별 변환과 고정 발표시차를 적용하지만 실제 발표 달력·ALFRED vintage는 사용하지 않습니다. 매크로는 개별 종목 알파에 더하지 않습니다.'],
  consensus: ['기관 리포트 컨센서스', '공식 원문과 발행일을 사람이 확인한 기관 전망만 <b>원문 검증 완료</b>로 집계합니다. 새로 발견했지만 아직 읽지 않은 자료는 <b>검토 대기</b>로 분리합니다. 방향의 중앙값과 의견 차이를 계산하며, 같은 기관·연구팀은 최대 한 표만 반영합니다.'],
  longterm: ['지역별 장기 리서치', 'KR·US를 <b>지역별로 독립 z-score</b> 산출하고(서로 직접 비교하지 않음), 팩터(모멘텀·밸류·퀄리티·저변동)는 <b>섹터 내 중립화</b>합니다. 알파 점수는 <b>신뢰도(팩터·재무 커버리지·소스 품질)로 페널티</b>를 받고, 위험지표·진입상태와 <b>분리 표기</b>됩니다. 3개 슬리브·최소 재무 커버리지 미달은 <b>DATA_INSUFFICIENT</b>로 분류돼 후보에서 제외됩니다.'],
  entry: ['진입상태', '‘좋은 종목’(장기 리서치 관점)과 ‘지금 살 종목’(진입상태)은 다릅니다. 추세(20·50·200일)·200일선 이격·<b>유니버스 내 과열 백분위</b>·변동성 급등·갭·실적 이벤트·섹터 집중도를 반영해 <b>분할매수/관찰/되돌림대기/이벤트위험/회피</b>로 구분합니다. 장기 팩터가 우수해도 과열·이벤트·급변동이면 되돌림 대기 또는 이벤트 위험이 됩니다.'],
  concentration: ['모델 포트폴리오 집중도', '리서치 후보는 넓게 보되 실제 모델 포트폴리오는 <b>3~5종목</b>으로 좁힙니다. 표시 비중은 연구용 가상 포트폴리오 안의 비중이며 개인 자산의 권장 비중이 아닙니다. 단일종목·업종 상한과 현금 하한을 함께 확인하세요.'],
  paper: ['Paper 성과 (signal ledger)', '오늘부터 생성되는 모든 종목선정 결과를 <b>변경 불가능한 ledger</b>에 누적합니다(과거 결과를 현재 모델로 덮어쓰지 않음). 21/63/126/252영업일 수익률·초과수익·MFE/MAE를 계산하고 hit rate뿐 아니라 <b>rank IC·초과수익</b>으로 평가합니다. 별도 history 브랜치에 저장됩니다. 검증 이력이 충분하기 전에는 “LIVE VALIDATED”라고 하지 않습니다.'],
  trade: ['단기 ML 참고자료', '단기 방향 예측은 동전던지기에 가깝고 수백 종목 스캔은 거짓 양성을 만듭니다. 주 판단은 위 장기 리서치·진입상태이며, 이 섹션은 타이밍 참고로만 보세요.'],
  macro: ['매크로 원지표', 'FRED(국외)·ECOS(국내) 원지표 값만 표시합니다. 국면·위험예산 판정은 상단 6축 방향 엔진이 담당합니다.'],
  sentiment: ['공포·탐욕 (정량 심리)', '유니버스 추세 위 비중·상승국면 비중·중앙값 모멘텀 + 매크로를 가중합한 휴리스틱 지수(확률 아님)입니다.'],
  direction: ['모델 위험예산 나침반', '규칙 기반 자산배분 도구를 합성한 <b>참고용</b> 방향성입니다. 개인의 전체 주식비중을 정하지 않으며, ‘모델 위험예산’으로만 제시합니다.'],
  dualmom: ['듀얼 모멘텀 변형', 'Antonacci GEM에서 영감을 받았으나 자산 메뉴·룩백·방어자산 구성이 달라 <b>정확한 GEM이 아닌 변형</b>입니다. 12개월 절대·상대 모멘텀으로 위험/방어 자산을 고릅니다(후행성 있음).'],
  rotation: ['섹터 로테이션 (RRG)', 'Relative Rotation Graph 근사치. 상대강도 비율·모멘텀으로 섹터 순환을 봅니다.'],
  factor: ['팩터 · 스타일 모멘텀', '모멘텀·가치·퀄리티·저변동·소형주 ETF의 S&P500 대비 초과수익입니다.'],
  flows: ['자금 흐름 (자체 프록시)', '거래량 급증 + 상승 종목. 기관/외국인 실제 수급이 아니라 자체 데이터로 만든 프록시입니다.'],
  indices: ['글로벌 마켓', '카드의 등락률은 1일, 스파크라인과 별도 수익률은 최근 3개월입니다. 카드 클릭 시 3개월 상세가 기본으로 열리며 1M·3M·6M·1Y를 바꿔 볼 수 있습니다.'],
  thirteenf: ['SEC 13F 공시', '미국 기관투자자가 SEC에 제출한 <b>분기말 보유 공시</b>입니다. 공개 시점에는 최대 45일의 시차가 있고 현금·공매도·비상장·일부 해외자산은 보이지 않습니다. 따라서 현재 포트폴리오나 매매 신호로 해석하지 않고, 분기별 보유 주식 수 변화와 집중도만 비교합니다.'],
  evidence: ['근거 커버리지', '필요한 팩터 근거 중 실제로 계산 가능한 항목의 비율입니다. 값이 높아도 데이터가 최신이거나 원천 품질이 높다는 뜻은 아닙니다.'],
  completeness: ['데이터 완전성', '팩터·재무 입력이 빠짐없이 채워진 정도입니다. 근거의 방향이나 출처 신뢰도를 뜻하지 않습니다.'],
  source: ['소스 품질', '원천과 시점 확인 수준을 요약합니다. 입력 항목의 개수인 근거 커버리지·완전성과 별개입니다.'],
  prob: ['모델 점수 (보정 확률)', '가격·추세·변동성·매크로 피처를 LightGBM+로지스틱 앙상블에 넣어 보정한 확률입니다. [5%,95%]로 클리핑돼 100%/0%는 불가능합니다.'],
  portfolio: ['모델 포트폴리오', '리서치 후보 전체를 그대로 담지 않고 <b>3~5종목으로 집중</b>합니다. 종목 선정은 <b>알파 백분위 초과분 ÷ 하방변동성</b> 순위(근거 커버리지·진입상태 배율로 감쇠)로 하고, 비중은 <b>하방변동성 역가중 + 순위 틸트</b>로 정합니다. Kelly는 실측 ledger 기대수익이 쌓인 뒤에만 이 위에 얹힙니다.'],
  selection: ['선정 과정', '후보 → 자격 필터(알파 하한·진입상태·근거) → 업종·지역 종목 수 상한 → 목표 종목 수 절단의 순서입니다. 탈락한 종목도 사유와 함께 남겨 어떤 단계에서 밀렸는지 확인할 수 있습니다.'],
  conviction: ['컨빅션 점수', '(알파 백분위 − 50) ÷ 50 ÷ 하방변동성 × 근거 커버리지 × 진입상태 배율. <b>종목 순서를 정하는 랭킹 점수이며 기대수익률이나 샤프비율 예측이 아닙니다.</b> 알파는 횡단면 순위이지 수익률 추정치가 아니기 때문입니다.'],
  invalidation: ['무효화 조건', '이 종목의 논리가 <b>어디서 깨지는지</b>를 종목별 현재 수치와 함께 적습니다. 기준선은 설정된 편출 버퍼, 팩터 중앙값, 200일선·12-1M 모멘텀 정의, 해당 지역 위험 횡단면 분포, 데이터 충족 하한에서 각각 산출합니다.'],
  concentration2: ['집중도', '유효 종목수 = 1 ÷ 주식비중 허핀달지수. 5종목을 균등하게 담으면 5, 한 종목에 쏠릴수록 1에 가까워집니다.'],
  radar: ['기회 · 경고 레이더', 'Core Portfolio가 “위험 대비 지금 안정적으로 보유할 종목”을 답한다면, 레이더는 <b>“최근 무엇이 달라졌는가”</b>를 답합니다. 두 층은 <b>하나의 점수로 합치지 않습니다</b>. 좋은 종목이라도 변화가 없으면 기회가 아니고, 순위가 낮아도 강한 변화가 생기면 관찰 대상입니다.'],
  opportunity: ['기회 레이더', '알파 백분위 변화, 모멘텀 가속, 상대강도 개선, 거래량, 진입상태 전환, 섹터 로테이션 등 <b>변화(change) 피처</b>를 우선합니다. 등급은 <b>검증된 기회</b>(과거 OOS 검증 통과 + 신호 수렴), <b>관찰 필요한 변화</b>(변화는 강하나 검증 부족, 리서치 전용), <b>관심 목록</b>으로 나뉩니다. 거래량이 늘어도 가격이 밀리면 기회로 분류하지 않습니다.'],
  warning: ['경고 레이더', '기존 논리가 깨지는 신호를 별도 모델로 봅니다: 알파 급락, 200일선 이탈, 상대강도 악화, 진입상태 하향, 변동성 급등, 하락 중 거래량 급증. <b>보유 종목의 경고를 최상단에 배치</b>합니다. 기회 점수의 반대값이 아니라 별도 점수입니다.'],
  validationlab: ['Validation Lab', '<b>과거 OOS</b>는 “미래를 보지 않고 과거에 같은 모델을 돌렸다면 어땠는가”, <b>실시간 Paper</b>는 “모델을 더 손대지 않은 상태에서 실제 미래에도 재현되는가”입니다. <b>서로 다른 증거</b>이므로 합산하지 않고 나란히 보여주며, Kelly 기대수익은 두 증거를 정밀도 가중으로 결합한 posterior를 사용합니다.'],
  pitquality: ['PIT 품질', '과거 재현에서 그 시점에 실제로 볼 수 있었던 데이터만 썼는지를 나타냅니다. 가격은 시점 정합적이지만 배당·액면 조정은 현재 기준이고(PIT_APPROXIMATE), 재무는 무료 데이터에 발표일 이력이 없어 과거에 소급 적용하지 않고 <b>제외</b>합니다. 매크로는 발표시차만 반영하고 개정 이전 값(vintage)은 확보하지 못해 REVISED_HISTORY입니다.'],
  survivorship: ['생존편향', '현재 상장된 종목만으로 과거를 재현하면 이미 사라진 실패 사례가 빠져 성과가 좋아 보입니다. 과거 구성종목 파일이 없으면 <b>SURVIVORSHIP_BIAS_UNRESOLVED</b>로 기록하고 과거 증거의 가중치를 낮춥니다.'],
  posterior: ['Kelly 기대수익 posterior', '과거 OOS prior와 실시간 paper 증거를 <b>역분산(정밀도) 가중</b>으로 결합하고, 0을 중심으로 하는 사전분포로 수축합니다. 실시간 표본이 쌓일수록 실시간 쪽 비중이 자동으로 커집니다. 과거 증거는 모델 설계 자체가 그 시기를 겪은 뒤 만들어졌다는 이유로 1.0보다 낮은 가중치를 받습니다.'],
  drift: ['성과 괴리 감지', '과거 OOS 기대수익보다 실시간 성과가 크게 낮으면 Kelly 비중을 <b>축소</b>합니다. 반대 방향은 작동하지 않습니다 — 실시간 성과가 나쁘다고 기대수익을 올리는 일은 없습니다.'],
  analogue: ['과거 유사 사례', '현재 관측치와 과거 특징 벡터의 거리로 가장 비슷했던 시점들을 찾아 그 이후 결과 분포를 보여줍니다. <b>예측 모델이 아니라 설명 도구</b>이며, 유사 사례가 미래를 보장하지 않습니다.'],
};
const pop = $('#pop');
let popKey = null;
const placePop = (target) => {
  const r = target.getBoundingClientRect(); const w = Math.min(420, window.innerWidth - 24);
  pop.style.width = w + 'px';
  let left = Math.min(r.left + window.scrollX, window.scrollX + window.innerWidth - w - 12);
  pop.style.left = Math.max(window.scrollX + 12, left) + 'px';
  const popHeight = pop.getBoundingClientRect().height;
  const below = r.bottom + 6;
  const topInViewport = below + popHeight <= window.innerHeight - 12
    ? below : Math.max(12, r.top - popHeight - 6);
  pop.style.top = (topInViewport + window.scrollY) + 'px';
};
const showPop = (key, target) => {
  const e = EXPL[key]; if (!e) return;
  if (popKey === key && !pop.hidden) return hidePop();
  popKey = key; pop.innerHTML = `<b>${e[0]}</b><p>${e[1]}</p>`; pop.hidden = false; placePop(target);
};
const hidePop = () => { pop.hidden = true; popKey = null; };
const term = (k, l) => `<span class="term" data-x="${k}">${l}</span>`;

const showTickerPop = (ticker, target) => {
  const d = DATA.details && DATA.details[ticker];
  if (!d) return;
  const f = d.fundamentals || {};
  const m = (l, v) => `<div><span>${l}</span><b>${v}</b></div>`;
  const marketCap = (v) => v == null ? '—' : v >= 1e12 ? `${(v / 1e12).toFixed(1)}T` : v >= 1e9 ? `${(v / 1e9).toFixed(1)}B` : v >= 1e6 ? `${(v / 1e6).toFixed(0)}M` : fmt(v);
  const yieldPct = f.dividendYield == null ? null : (Math.abs(f.dividendYield) <= 1 ? f.dividendYield * 100 : f.dividendYield);
  const valuation = [
    m('PER · 최근 12개월', fmt(f.trailingPE, '배', 1)), m('PER · 예상', fmt(f.forwardPE, '배', 1)),
    m('PBR', fmt(f.priceToBook, '배', 1)), m('배당률', fmt(yieldPct, '%', 2)),
    m('시가총액', `${marketCap(f.marketCap)}${f.currency ? ` ${f.currency}` : ''}`), m('잉여현금흐름 수익률', fmt(f.fcfYield == null ? null : f.fcfYield * 100, '%', 1)),
    m('ROE', fmt(f.roe == null ? null : f.roe * 100, '%', 1)), m('부채/자기자본', fmt(f.debtToEquity, '%', 1)),
    m('영업이익률', fmt(f.operatingMargin == null ? null : f.operatingMargin * 100, '%', 1)), m('이익 성장률', fmt(f.earningsGrowth == null ? null : f.earningsGrowth * 100, '%', 1)),
  ].join('');
  const technical = [
    m('현재가', fmt(d.lastClose)), m('국면', regKo(d.regime)),
    m('10일 모델 점수', pct0(d.modelScore ?? d.probUp)), m('SMA50/200', `${fmt(d.ma50)} / ${fmt(d.ma200)}`),
    m('RSI(14)', fmt(d.rsi14)), m('실현변동성', fmt(d.realizedVol, '%')),
    m('1년 낙폭', fmt(d.maxDrawdown252d, '%')), m('상대강도', sp(d.relMomentum)),
    m('60일 모멘텀', sp(d.mom63)), m('52주고점 대비', fmt(d.pct52wHigh, '%')),
  ].join('');
  const flags = (d.riskFlags && d.riskFlags.length) ? `<div class="dp-flags">${d.riskFlags.map((f) => `<span class="mflag">${f}</span>`).join('')}</div>` : '';
  const fStatus = Object.keys(f).length
    ? `<div class="dp-source">재무·밸류에이션은 ${f.asOf || '최근'} 현재 스냅샷입니다. 과거 시점 재무나 투자 권고가 아닙니다.</div>`
    : '<div class="dp-source missing">현재 재무 스냅샷을 불러오지 못했습니다. 값을 추정해 채우지 않습니다.</div>';
  popKey = 'tk:' + ticker;
  pop.innerHTML = `<div class="dp-head"><b>${tkName(ticker)}</b> <span class="tk">${ticker}</span> <span class="reg ${regCls(d.regime)}">${regKo(d.regime)}</span></div><div class="dp-sub">기본 정보 · ${f.sector || d.sector || '업종 미분류'}${f.industry ? ` / ${f.industry}` : ''}</div><div class="dp-grid">${valuation}</div>${fStatus}<div class="dp-sub">가격·모델 참고값</div><div class="dp-grid">${technical}</div>${flags}`;
  pop.hidden = false; placePop(target);
};

const show13FPop = (managerId, identifier, target) => {
  const manager = (DATA?.institutionalHoldings13F?.managers || []).find((m) => m.id === managerId);
  const changeRows = Object.values(manager?.changes || {}).flat();
  const row = [...(manager?.topHoldings || []), ...changeRows].find((h) => h.cusip === identifier || h.issuer === identifier);
  if (!manager || !row) return;
  const m = (l, v) => `<div><span>${l}</span><b>${v}</b></div>`;
  const shares = row.shares ?? row.currentShares ?? row.previousShares;
  const value = row.valueUsd ?? row.currentValueUsd ?? row.previousValueUsd;
  popKey = `f13:${managerId}:${identifier}`;
  pop.innerHTML = `<div class="dp-head"><b>${f13Esc(row.issuer)}</b><span class="tk">${f13Esc(row.titleClass)}</span>${f13Option(row)}</div><div class="dp-grid">${m('운용사', f13Esc(manager.name))}${m('CUSIP', f13Esc(row.cusip || '변화 요약에는 미포함'))}${m('공시 평가액', f13Money(value))}${m('보유 주식 수', shares == null ? '—' : Number(shares).toLocaleString('en-US'))}${m('포트폴리오 비중', fmt(row.portfolioWeightPct, '%', 2))}${m('분기말 기준', f13Esc(manager.reportDate))}</div><div class="dp-source">13F 원문에는 PER·PBR·배당률과 현재 티커가 없습니다. 발행사명으로 티커를 추측해 잘못 연결하지 않고 공시 원문 값만 표시합니다.</div>`;
  pop.hidden = false; placePop(target);
};

document.addEventListener('click', (e) => {
  const macroRange = e.target.closest('[data-macro-range]');
  if (macroRange) { e.preventDefault(); setMacroRange(macroRange.dataset.macroRange); return; }
  const macroIndicator = e.target.closest('[data-macro-indicator]');
  if (macroIndicator) { e.preventDefault(); showMacroDialog(macroIndicator.dataset.macroIndicator); return; }
  const ixRange = e.target.closest('[data-index-range]');
  if (ixRange) { e.preventDefault(); setIndexRange(ixRange.dataset.indexRange); return; }
  const ix = e.target.closest('[data-index-symbol]');
  if (ix) { e.preventDefault(); showIndexDialog(ix.dataset.indexSymbol); return; }
  const f13 = e.target.closest('[data-f13-id]');
  if (f13) { e.preventDefault(); e.stopPropagation(); const key = `f13:${f13.dataset.f13Manager}:${f13.dataset.f13Id}`; if (popKey === key && !pop.hidden) return hidePop(); show13FPop(f13.dataset.f13Manager, f13.dataset.f13Id, f13); return; }
  const tk = e.target.closest('[data-tk]');
  if (tk) { e.preventDefault(); e.stopPropagation(); if (popKey === 'tk:' + tk.dataset.tk && !pop.hidden) return hidePop(); showTickerPop(tk.dataset.tk, tk); return; }
  const t = e.target.closest('[data-x]');
  if (t) { e.preventDefault(); e.stopPropagation(); showPop(t.dataset.x, t); return; }
  if (!pop.contains(e.target)) hidePop();
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hidePop(); });
window.addEventListener('scroll', hidePop, { passive: true });

// --- Markdown ---
const md2html = (md) => {
  const L = md.split('\n'); let h = '', inUl = false, inT = false;
  const cU = () => { if (inUl) { h += '</ul>'; inUl = false; } };
  const cT = () => { if (inT) { h += '</tbody></table>'; inT = false; } };
  L.forEach((l) => {
    if (l.startsWith('|') && !l.includes('---')) { cU(); const c = l.split('|').slice(1, -1).map((x) => x.trim()); if (!inT) { h += '<table><tbody>'; inT = true; } h += `<tr>${c.map((x) => `<td>${x}</td>`).join('')}</tr>`; return; }
    if (l.startsWith('|') && l.includes('---')) return; cT();
    if (l.startsWith('## ')) { cU(); h += `<h4>${l.slice(3)}</h4>`; }
    else if (l.startsWith('# ')) { cU(); h += `<h3>${l.slice(2)}</h3>`; }
    else if (l.startsWith('- ')) { if (!inUl) { h += '<ul>'; inUl = true; } h += `<li>${l.slice(2)}</li>`; }
    else if (/^\d+\. /.test(l)) { if (!inUl) { h += '<ul>'; inUl = true; } h += `<li>${l.replace(/^\d+\. /, '')}</li>`; }
    else if (l.trim()) { cU(); h += `<p>${l}</p>`; }
  });
  cU(); cT(); return h.replaceAll('**', '');
};
const loadRules = async () => {
  try { const r = await fetch('docs/investment-philosophy.md', { cache: 'no-store' }); $('#rulesDoc').innerHTML = md2html(await r.text()); }
  catch (e) { $('#rulesDoc').textContent = e.message; }
};

// =========================================================================
// 1. Data & validation status
// =========================================================================
const chip = (label, value, cls = '') => `<div class="schip ${cls}"><span>${label}</span><b>${value}</b></div>`;
const renderStatus = (d) => {
  const p = d.provenance || {}; const m = d.meta || {};
  const mh = d.marketDataHealth || {};
  const dataMode = d.dataMode || p.dataMode || 'unknown';
  const blocked = d.recommendationsBlocked;
  const freshness = blocked ? '안전 차단' : mh.status === 'CURRENT' ? '최신' : mh.status === 'DELAYED' ? '일부 지연' : '확인 필요';
  const trustStatus = blocked ? '안전 차단' : dataMode === 'live' ? '검증 가능' : '실험적 데이터';
  const generated = d.generatedAt ? new Date(d.generatedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) : '—';
  const cue = $('#trustSummaryCue');
  if (cue) cue.textContent = `${trustStatus} · ${modeLabel(dataMode)} · 시장 기준 ${p.marketAsOf || m.latestDataDate || '—'}`;
  $('#statusPanel').innerHTML = `
    <div class="trust-lead ${blocked ? 'bad' : dataMode === 'live' ? 'ok' : 'warn'}"><span>${blocked ? '■' : dataMode === 'live' ? '●' : '▲'}</span><div><b>${trustStatus}</b><small>${blocked ? COPY.blocked : modeLabel(dataMode)}</small></div></div>
    <div class="trust-facts"><div><span>시장 기준일</span><b>${p.marketAsOf || m.latestDataDate || '—'}</b></div><div><span>생성 시각</span><b>${generated}</b></div><div><span>데이터 모드</span><b>${modeLabel(dataMode)}</b></div><div><span>최신 상태</span><b>${freshness}</b></div></div>
    <details class="status-tech"><summary>감사·기술 정보</summary><dl><div><dt>원래 상태</dt><dd>${d.runMode || p.runMode || 'paperTrading'} / ${dataMode}</dd></div><div><dt>빌드</dt><dd>${p.buildCommitSha || '—'}</dd></div><div><dt>스키마</dt><dd>${p.schemaVersion || d.schemaVersion || '—'}</dd></div><div><dt>모델</dt><dd>${p.modelVersion || d.modelVersion || '—'}</dd></div><div><dt>sourceAsOf</dt><dd>${p.sourceAsOf || m.sourceAsOf || '—'}</dd></div><div><dt>커버리지</dt><dd>${m.coveragePct ?? '—'}% / 기준 ${m.coverageFloor ?? 95}%</dd></div></dl></details>`;
};

const largestEntry = (obj) => Object.entries(obj || {}).sort((a, b) => b[1] - a[1])[0];

// --- 1a. Decision hero: the whole answer in one paragraph + six numbers ---
const turnoverLabel = (mp) => (mp.turnoverBasis === 'INITIAL_BUILD'
  ? `신규 구축 ${fmt(mp.turnoverPct, '%', 1)}`
  : fmt(mp.turnoverPct, '%', 1));
const allocMethod = (mp) => ALLOC_METHOD[mp.kellyApplied === true ? 'BLENDED_CONSTRAINED_FRACTIONAL_KELLY' : (mp.baselineMethod || 'CONVICTION_TILTED_RISK_PARITY')]
  || { name: '기준 비중', how: '' };
const renderDecisionHero = (d) => {
  const host = $('#decisionHero'); const mp = d.modelPortfolio || {};
  const r = d.macroRegime || {}; const rb = r.riskBudget || {};
  const blocked = d.recommendationsBlocked || mp.status === 'BLOCKED';
  if (blocked) {
    $('#heroHeadline').textContent = '오늘은 판단을 내지 않습니다';
    host.innerHTML = `<div class="dh-verdict bad"><span class="dh-badge">■ 안전 차단</span><h3>${COPY.blocked}</h3><p>${(d.blockReasons || []).join(' · ') || '데이터 안전 기준 미달'}</p></div>`;
    return;
  }
  const positions = (mp.positions || []).filter((p) => p.modelPortfolioWeightPct > 0);
  const conc = mp.concentration || {};
  const method = allocMethod(mp);
  const equity = 100 - (mp.cashPct ?? 100);
  const sector = largestEntry(mp.sectorExposure);
  $('#heroHeadline').textContent = positions.length
    ? `${positions.length}종목 · 주식 ${equity.toFixed(0)}% · 현금 ${(mp.cashPct ?? 0).toFixed(0)}%`
    : '보유 비중 없음';
  const cue = positions.length ? 'ok' : 'warn';
  const line = positions.length
    ? `리서치 후보 ${mp.selection?.consideredCount ?? '—'}개를 <b>${positions.length}종목</b>으로 좁히고 <b>${method.name}</b>으로 비중을 정했습니다.`
    : '자격을 통과한 종목이 없어 전액 현금입니다.';
  const kellyLine = mp.kellyApplied === true
    ? `Kelly 반영 — 기준 비중 대비 배분 변화 ${fmt(mp.kellyAllocationImpactPct, '%p', 1)}`
    : `Kelly 미적용 — ${COPY.fallback}`;
  host.innerHTML = `
    <div class="dh-verdict ${cue}">
      <span class="dh-badge">${statusLabel(mp.status)}</span>
      <h3>${line}</h3>
      <p>${method.how}</p>
      <p class="dh-kelly ${mp.kellyApplied === true ? '' : 'risk-cue'}">${kellyLine}</p>
    </div>
    <div class="dh-kpis">
      ${chip('주식 비중', fmt(equity, '%', 1))}
      ${chip('현금', fmt(mp.cashPct, '%', 1))}
      ${chip('종목 수', positions.length)}
      ${chip('유효 종목수', conc.effectiveNames ?? '—', 'info')}
      ${chip('최대 업종', sector ? `${sector[0]} ${sector[1]}%` : '—')}
      ${chip('매크로 국면', REGIME_KO[r.regime] || '판정 대기')}
      ${chip('주식 위험예산', `${(rb.equityRangePct || []).join('~') || '—'}%`)}
      ${chip('회전율', turnoverLabel(mp))}
    </div>
    ${(conc.warnings || []).length ? `<div class="dh-warn">${conc.warnings.map((w) => `<span>! ${CONCENTRATION_KO[w] || w}</span>`).join('')}</div>` : ''}`;
};

// --- 1b. The holdings themselves: what is owned and where the case breaks ---
const invalidationLine = (rows, limit = 3) => {
  const all = rows || [];
  if (!all.length) return '';
  const ordered = all.filter((x) => x.state === 'BREACHED').concat(all.filter((x) => x.state !== 'BREACHED'));
  return ordered.slice(0, limit).map((x) =>
    `<span class="inval ${x.state === 'BREACHED' ? 'broken' : ''}"><em>${x.labelKo}</em> ${x.currentKo} → ${x.triggerKo}</span>`).join('');
};
const holdingCard = (p, maxWeight) => {
  const w = p.modelPortfolioWeightPct ?? 0;
  const bar = maxWeight > 0 ? Math.max(4, Math.round((w / maxWeight) * 100)) : 0;
  return `<article class="holding">
    <div class="h-top"><span class="h-rank">${p.convictionRank ?? '—'}</span><div>${tkLink(p.ticker)}<small>${p.region || ''} · ${p.sector || '미분류'}</small></div>${p.entryState ? entryBadge(p.entryState) : ''}</div>
    <div class="h-weight"><b>${fmt(w, '%', 1)}</b><div class="h-bar"><i style="width:${bar}%"></i></div></div>
    <p class="h-thesis">${p.thesisKo || '팩터 근거 요약 없음'}</p>
    <div class="h-facts"><span>${term('conviction', '컨빅션')} <b>${fmt(p.convictionScore, '', 2)}</b></span><span>하방변동 <b>${fmt(p.downsideVolPct, '%', 1)}</b></span><span>알파 <b>${topPct(p.alphaPercentile)}</b></span></div>
    <div class="h-inval"><b>${term('invalidation', '깨지는 지점')}</b>${invalidationLine(p.invalidation) || '<span class="inval">종목별 조건 산출 대기</span>'}</div>
  </article>`;
};
const renderHoldings = (d) => {
  const host = $('#holdingsPanel'); const mp = d.modelPortfolio || {};
  if (d.recommendationsBlocked || mp.status === 'BLOCKED') { host.innerHTML = ''; return; }
  const rows = (mp.positions || []).filter((p) => p.modelPortfolioWeightPct > 0)
    .sort((a, b) => b.modelPortfolioWeightPct - a.modelPortfolioWeightPct);
  if (!rows.length) {
    host.innerHTML = `<div class="status-note warn">보유할 종목이 선정되지 않았습니다. <code>${mp.fallbackReason || 'selection_empty'}</code></div>`;
    return;
  }
  const maxWeight = rows[0].modelPortfolioWeightPct;
  host.innerHTML = rows.map((p) => holdingCard(p, maxWeight)).join('');
};

// --- 3. Selection funnel: candidate -> holding, with every drop reason kept ---
const renderSelection = (d) => {
  const host = $('#selectionPanel'); const mp = d.modelPortfolio || {};
  const sel = mp.selection;
  if (d.recommendationsBlocked || mp.status === 'BLOCKED' || !sel) {
    $('#selectionMeta').textContent = '';
    host.innerHTML = `<div class="status-note info">${d.recommendationsBlocked ? COPY.blocked : '선정 결과가 아직 없습니다.'}</div>`;
    return;
  }
  $('#selectionMeta').textContent = `후보 ${sel.consideredCount} → 자격 ${sel.eligibleCount} → 보유 ${sel.selectedCount} (목표 ${sel.targetNames})`;
  const step = (n, label, value, note) => `<div class="funnel-step"><span class="funnel-n">${n}</span><div><b>${value}</b><span>${label}</span><small>${note}</small></div></div>`;
  const funnel = `<div class="funnel">
    ${step(1, '리서치 후보', sel.consideredCount, '지역별 팩터 슬리브 통과 종목')}
    ${step(2, '자격 통과', sel.eligibleCount, `알파 ${sel.minAlphaPercentile}p 이상 · 진입상태·근거 조건 충족`)}
    ${step(3, '분산 상한', `업종 ${sel.maxNamesPerSector} · 지역 ${sel.maxNamesPerRegion}`, '동일 업종·지역 종목 수 제한')}
    ${step(4, '최종 보유', sel.selectedCount, `컨빅션 순위 상위 ${sel.targetNames}종목까지`)}
  </div>`;
  const rows = (sel.ranking || []).map((r) => {
    const why = r.selected ? '보유' : (r.exclusionCodes || []).map((c) => SELECT_EXCLUSION_KO[c] || c).join(' · ') || '—';
    return `<div class="sel-row ${r.selected ? 'picked' : ''}">
      <span data-label="종목">${tkLink(r.ticker)} <small>${r.region}</small></span>
      <span data-label="업종">${r.sector}</span>
      <span data-label="알파">${topPct(r.alphaPercentile)}</span>
      <span data-label="하방변동">${fmt(r.downsideVolPct, '%', 1)}</span>
      <span data-label="컨빅션"><b>${fmt(r.convictionScore, '', 2)}</b></span>
      <span data-label="결과" class="sel-why">${why}</span>
    </div>`;
  }).join('');
  host.innerHTML = `${funnel}
    <div class="sel-method"><b>${term('conviction', '컨빅션 점수')}</b> ${sel.scoreFormulaKo}<em>${sel.notAForecastKo}</em></div>
    <div class="sel-table"><div class="sel-row sel-head"><span>종목</span><span>업종</span><span>알파</span><span>하방변동</span><span>컨빅션</span><span>결과</span></div>${rows || '<div class="none">순위 데이터 없음</div>'}</div>
    ${sel.shortfall ? `<div class="status-note warn">자격을 통과한 종목이 최소 ${sel.minNames}개에 미치지 못해 남은 비중은 현금으로 둡니다.</div>` : ''}`;
};

// --- 3b. Is the methodology actually switched on? Answer it explicitly. ---
const methodRow = (name, on, detail) => `<div class="ms-row ${on ? 'on' : 'off'}"><span class="ms-dot"></span><div><b>${name}</b><small>${detail}</small></div><em>${on ? '적용' : '미적용'}</em></div>`;
const renderMethodStatus = (d) => {
  const host = $('#methodStatusPanel'); const mp = d.modelPortfolio || {};
  const lt = d.longTerm || {}; const r = d.macroRegime || {};
  const vs = d.validationStatus || {}; const gate = (mp.validation || {}).sampleGate || {};
  const sel = mp.selection;
  const regionCount = Object.keys(lt.regions || {}).length;
  const rows = [
    methodRow('팩터 리서치 (섹터중립 z · 4슬리브)', regionCount > 0,
      regionCount > 0 ? `${regionCount}개 지역을 각각 독립 z-score로 순위화` : '지역 테이블을 만들지 못했습니다'),
    methodRow('진입 타이밍 분리', !!(lt.regions && Object.values(lt.regions).some((b) => (b.researchTable || []).some((x) => x.entry))),
      '장기 팩터 판단과 지금 진입 여부를 별도 상태로 유지'),
    methodRow('매크로 위험예산', !!r.regime,
      r.regime ? `${REGIME_KO[r.regime] || r.regime} · 주식 예산 ${(mp.macroEquityRangePct || []).join('~') || '—'}% → 현금 하한 ${fmt(mp.appliedMinCashPct, '%', 0)} · Kelly 배율 ${fmt(mp.regimeMultiplier, '', 2)}` : '국면 판정 대기'),
    methodRow('종목 집중 (컨빅션 선정)', !!sel,
      sel ? `${sel.consideredCount}개 후보 → ${sel.selectedCount}종목` : '선정 결과 없음'),
    methodRow('Kelly 기대수익 배분', mp.kellyApplied === true,
      mp.kellyApplied === true ? `실측 ledger 기준 · 배분 영향 ${fmt(mp.kellyAllocationImpactPct, '%p', 1)}`
        : `paper ${vs.paperDays ?? 0}/${gate.thresholds?.paperDays ?? 252}일 · 만기 신호 ${vs.maturedSignals ?? 0}/${gate.thresholds?.maturedSignals ?? 100}개 — 최초 검토 가능 ${mp.validation?.earliestReviewDate || '산정 대기'}`),
  ].join('');
  host.innerHTML = `<div class="ms-head"><b>방법론 적용 현황</b><span class="muted">켜져 있는 층과 아직 아닌 층을 그대로 표시합니다</span></div>${rows}`;
};

// --- 3. Opportunity / Warning radars -------------------------------------
// Kept visually and structurally apart from the Core Portfolio: they answer
// "what changed recently", not "what should I hold".
const analogueLine = (a) => {
  if (!a) return '';
  if (!a.sampleSufficient) {
    return `<div class="rd-analogue thin">${term('analogue', '과거 유사 사례')} ${a.matches}건 — 표본이 적어 수치를 표시하지 않습니다</div>`;
  }
  return `<div class="rd-analogue">${term('analogue', '과거 유사 사례')} <b>${a.matches}건</b>
    <span>${a.horizonDays}일 평균 ${sp(a.meanExcessPct)} · 중앙값 ${sp(a.medianExcessPct)}</span>
    <span>양의 초과수익 ${Math.round((a.positiveExcessRatio || 0) * 100)}% · 하위 10% ${sp(a.worstDecileExcessPct)}</span>
    <em>${a.disclaimerKo}</em></div>`;
};
const radarCard = (row, scoreKey) => {
  const tier = row.tier || 'WATCH';
  const cls = RADAR_TIER_CLASS[tier] || 'trans';
  const signals = (row.signalsKo || []).map((s) => `<span class="rd-sig">${s}</span>`).join('');
  const notes = (row.notes || []).map((n) => RADAR_NOTE_KO[n] || n).join(' · ');
  return `<article class="radar-card t-${cls}">
    <div class="rd-top">
      <div>${tkLink(row.ticker)}<small>${row.region || ''} · ${row.sector || '미분류'}</small></div>
      <span class="vbadge v-${cls}">${row.tierKo || RADAR_TIER_KO[tier] || tier}</span>
    </div>
    <div class="rd-score"><b>${fmt(row[scoreKey], '', 1)}</b>
      <span>${row.historicalPercentile != null ? `과거 분포 상위 ${Math.max(1, Math.round(100 - row.historicalPercentile))}%` : '과거 분포 대조 불가'}</span>
      ${row.isCoreHolding ? '<span class="rd-held">보유 종목</span>' : ''}
    </div>
    ${signals ? `<div class="rd-sigs">${signals}</div>` : ''}
    ${notes ? `<p class="rd-note">${notes}</p>` : ''}
    ${analogueLine(row.historicalAnalogues)}
  </article>`;
};
const calibrationBandTable = (bands) => {
  const usable = (bands || []).filter((b) => b.sampleSufficient);
  if (!usable.length) return '';
  const rows = usable.map((b) => `<tr><td>${b.scoreFrom}~${b.scoreTo}</td><td>${b.n}</td>
    <td>${Math.round((b.positiveExcessHitRatio || 0) * 100)}%</td><td>${sp(b.meanExcessPct)}</td>
    <td>${sp(b.medianExcessPct)}</td><td>${sp(b.worstDecileExcessPct)}</td></tr>`).join('');
  return `<details class="rd-calib"><summary>점수 구간별 과거 OOS 실측</summary>
    <table><thead><tr><th>점수</th><th>표본</th><th>양의 초과수익</th><th>평균</th><th>중앙값</th><th>하위 10%</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <p class="muted">표본이 충분한 구간만 표시합니다. 과거 분포이며 미래 수익 보장이 아닙니다.</p></details>`;
};
const renderRadar = (d) => {
  const oppHost = $('#opportunityRadarPanel'); const warnHost = $('#warningRadarPanel');
  if (!oppHost || !warnHost) return;
  const opp = d.opportunityRadar || {}; const warn = d.warningRadar || {};
  const diag = d.radarDiagnostics || {};
  const blocked = d.recommendationsBlocked || opp.blocked || warn.blocked;
  if (blocked) {
    $('#radarMeta').textContent = '안전 차단';
    $('#radarBasis').textContent = COPY.blocked;
    oppHost.innerHTML = `<div class="status-note warn">${COPY.blocked}</div>`;
    warnHost.innerHTML = '';
    return;
  }
  const mlNote = ML_STATUS_KO[opp.mlStatus] || opp.mlStatus || '상태 미상';
  $('#radarMeta').textContent = diag.asOf ? `기준 ${diag.asOf} · 후보 ${diag.candidates ?? '—'}개` : '';
  $('#radarBasis').innerHTML = `${mlNote}. 기회와 경고는 Core Portfolio와 <b>별도 층</b>이며 하나의 점수로 합치지 않습니다.
    ${opp.targetDescriptionKo ? `학습 목표: ${opp.targetDescriptionKo}.` : ''} ${opp.notAGuaranteeKo || ''}`;
  const render = (host, radar, scoreKey, emptyText) => {
    const regions = radar.regions || {};
    const blocks = Object.keys(regions).sort().map((region) => {
      const rows = regions[region] || [];
      if (!rows.length) return '';
      return `<div class="rd-region"><div class="rd-region-h">${region}</div>
        ${rows.map((r) => radarCard(r, scoreKey)).join('')}</div>`;
    }).filter(Boolean).join('');
    host.innerHTML = (blocks || `<div class="status-note info">${emptyText}</div>`)
      + calibrationBandTable(radar.calibrationBands);
  };
  render(oppHost, opp, 'opportunityScore', '최근 두드러진 변화가 감지되지 않았습니다.');
  render(warnHost, warn, 'warningScore', '기존 논리가 깨지는 신호가 감지되지 않았습니다.');
};

// --- 6. Validation Lab: two evidence classes, never merged ----------------
const vlabRow = (label, value, hint = '') =>
  `<div class="vl-row"><span>${label}</span><b>${value}</b>${hint ? `<small>${hint}</small>` : ''}</div>`;
const renderValidationLab = (d) => {
  const host = $('#validationLabPanel');
  if (!host) return;
  const hv = d.historicalValidation || {}; const pv = d.prospectiveValidation || {};
  const ke = d.kellyEvidence || {}; const mp = d.modelPortfolio || {};
  const mc = d.modelComparison || {};
  const activation = ke.activation || {};
  $('#validationLabMeta').textContent =
    `${hv.available ? `과거 OOS ${hv.oosSignals ?? 0}건` : '과거 OOS 없음'} · ${pv.trackingDays ?? 0}일 실시간 추적`;

  const historicalPanel = `<div class="vl-card">
    <div class="vl-h">과거 OOS 검증 <span class="tag">HISTORICAL_OOS</span></div>
    ${hv.available ? `
      ${vlabRow('재현 기간', (hv.replayPeriod || []).filter(Boolean).join(' ~ ') || '—', `${hv.replayFrequency || ''} 그리드 · ${hv.replayDates ?? '—'}개 날짜`)}
      ${vlabRow('OOS 신호', fmt(hv.oosSignals), `고유 날짜 ${hv.uniqueDates ?? '—'}`)}
      ${vlabRow('만기 신호', fmt(hv.maturedSignals), Object.entries(hv.maturedByHorizon || {}).map(([h, n]) => `${h}D ${n}`).join(' · '))}
      ${vlabRow(term('pitquality', 'PIT 커버리지'), fmt(hv.pitCoveragePct, '%', 1), `품질 ${hv.pitQuality || '—'}`)}
      ${vlabRow(term('survivorship', '생존편향'), hv.survivorshipRisk || '—', hv.survivorshipNote || '')}
      ${vlabRow('재무 point-in-time', hv.fundamentalsPointInTime ? '적용' : '미적용 (밸류·퀄리티 슬리브 제외)')}
      ${vlabRow('매크로 vintage', hv.macroPitStatus || '—')}
      ${vlabRow('최종 홀드아웃', hv.finalHoldoutStart || '—', '모델 확정 전까지 튜닝에 사용하지 않음')}
      ${(hv.knownDeviationsFromProduction || []).length ? `<details class="vl-fold"><summary>운영 모델과의 알려진 차이 ${hv.knownDeviationsFromProduction.length}건</summary><ul>${hv.knownDeviationsFromProduction.map((x) => `<li>${x}</li>`).join('')}</ul></details>` : ''}
    ` : `<div class="status-note info">${hv.reason === 'historical_replay_ledger_not_supplied' ? '과거 재현 ledger가 아직 생성되지 않았습니다.' : (hv.reason || '데이터 없음')}</div>`}
    <p class="vl-foot">${hv.notLiveEvidenceKo || ''}</p>
  </div>`;

  const prospectivePanel = `<div class="vl-card">
    <div class="vl-h">실시간 Paper 검증 <span class="tag">PROSPECTIVE_PAPER</span></div>
    ${vlabRow('추적 시작', pv.trackingSince || '—')}
    ${vlabRow('추적 일수', fmt(pv.trackingDays), '신호가 쌓인 기간 — 만기 여부와 무관')}
    ${vlabRow('기록 신호', fmt(pv.signalsRecorded), `고유 날짜 ${pv.uniqueDates ?? '—'}`)}
    ${vlabRow('만기 관측 일수', fmt(pv.maturedObservationDays), '결과가 확정된 구간')}
    ${vlabRow('만기 신호', fmt(pv.maturedSignals), Object.entries(pv.maturedByHorizon || {}).map(([h, n]) => `${h}D ${n}`).join(' · ') || '—')}
    ${vlabRow('비용 차감 초과수익', pv.costAdjustedExcessReturn ?? '—')}
    ${vlabRow('MDD / CVaR', `${pv.MDD ?? '—'} / ${pv.CVaR ?? '—'}`)}
    <p class="vl-foot">${pv.roleKo || ''}</p>
  </div>`;

  const regions = Object.entries(ke.byRegion || {});
  const evidenceRows = regions.map(([region, blob]) => {
    const h = blob.historical || {}; const p = blob.prospective || {}; const post = blob.posterior || {};
    return `<tr><td>${region}</td>
      <td>${h.expectedExcessReturnPct != null ? sp(h.expectedExcessReturnPct) : '—'}<small>${h.effectiveDates ?? 0}일 · w ${h.weight ?? '—'}</small></td>
      <td>${p.expectedExcessReturnPct != null ? sp(p.expectedExcessReturnPct) : '—'}<small>${p.effectiveDates ?? 0}일</small></td>
      <td><b>${sp(post.expectedExcessReturnPct)}</b><small>과거 ${post.historicalWeightPct ?? 0}% · 실시간 ${post.prospectiveWeightPct ?? 0}%</small></td></tr>`;
  }).join('');
  const drift = ke.drift || {};
  const kellyPanel = `<div class="vl-card vl-kelly">
    <div class="vl-h">${term('posterior', 'Kelly 증거 결합')} <span class="tag ${activation.code === 'ACTIVE_VALIDATED' ? 'ok' : ''}">${activation.labelKo || EVIDENCE_STATUS[activation.code] || '검증 근거 없음'}</span></div>
    <p class="vl-lead">${activation.explainKo || 'Kelly 기대수익을 뒷받침할 증거가 아직 없습니다.'}</p>
    ${regions.length ? `<table class="vl-table"><thead><tr><th>지역</th><th>과거 OOS</th><th>실시간</th><th>결합 posterior</th></tr></thead><tbody>${evidenceRows}</tbody></table>`
      : `<div class="status-note info">과거·실시간 어느 쪽에서도 기대수익 근거가 없어 컨빅션 위험가중 비중을 유지합니다.</div>`}
    <div class="vl-grid">
      ${vlabRow('Base Kelly fraction', fmt((mp.baseKellyFraction ?? 0) * 100, '%', 1))}
      ${vlabRow('매크로 조정 후', fmt((mp.appliedKellyFraction ?? 0) * 100, '%', 1))}
      ${vlabRow('실제 배분 영향', mp.kellyApplied === true ? fmt(mp.kellyAllocationImpactPct, '%p', 1) : '미적용')}
      ${vlabRow(term('drift', '성과 괴리'), drift.detected ? `감지 (Kelly ×${drift.kellyMultiplier})` : (drift.detected === false ? '허용 범위' : '표본 부족'), drift.summaryKo || '')}
    </div>
    <p class="vl-foot">${ke.evidenceSeparationKo || ''}</p>
  </div>`;

  const challengers = (mc.challengers || []).map((c) => `<div class="vl-chall">
    <div><b>${c.name}</b><small>${c.descriptionKo || ''}</small></div>
    <span class="tag">${c.statusKo || c.status || '—'}</span>
    ${(c.acceptanceFailures || []).length ? `<em>미달: ${c.acceptanceFailures.join(', ')}</em>` : ''}
    <p class="muted">${c.promotionRuleKo || ''}</p></div>`).join('');
  const comparison = `<div class="vl-card">
    <div class="vl-h">Champion / Challenger</div>
    <div class="vl-chall champion"><div><b>${(mc.champion || {}).name || '—'}</b><small>${(mc.champion || {}).descriptionKo || ''}</small></div><span class="tag ok">운영 중</span></div>
    ${challengers || '<div class="status-note info">비교 중인 challenger가 없습니다.</div>'}
    <p class="vl-foot">${mc.separationKo || ''}</p>
  </div>`;

  host.innerHTML = `<div class="vl-two">${historicalPanel}${prospectivePanel}</div>${kellyPanel}${comparison}`;
};

const renderChanges = (d) => {
  const c = d.changesSincePrior || {}; const host = $('#changeSummary');
  const t = c.opportunityTransitions || {};
  // What is NEW today. Driven by state transitions against the last validated
  // production state, so a name that has been HIGH since Tuesday does not
  // re-announce itself every morning until the alert is ignored.
  const alerts = [];
  if (t.available) {
    const newHigh = (t.newOpportunities || []).filter((x) => x.after !== 'WATCH');
    const newWarn = (t.newWarnings || []).filter((x) => x.after !== 'WATCH');
    if (newHigh.length) alerts.push(`<span class="ca ca-opp">🚨 신규 기회 ${newHigh.length}<em>${newHigh.map((x) => tkName(x.ticker)).join(', ')}</em></span>`);
    if (newWarn.length) alerts.push(`<span class="ca ca-warn">⚠ 신규 경고 ${newWarn.length}<em>${newWarn.map((x) => tkName(x.ticker)).join(', ')}</em></span>`);
  }
  const entryUp = (c.entryStateChanged || []).filter((x) => ENTRY_RANK[x.after] > ENTRY_RANK[x.before]);
  const entryDown = (c.entryStateChanged || []).filter((x) => ENTRY_RANK[x.after] < ENTRY_RANK[x.before]);
  if (entryUp.length) alerts.push(`<span class="ca ca-up">↑ 진입 개선 ${entryUp.length}</span>`);
  if (entryDown.length) alerts.push(`<span class="ca ca-down">↓ 진입 악화 ${entryDown.length}</span>`);
  const holdingChanged = (c.added || []).length || (c.removed || []).length;
  alerts.push(`<span class="ca ca-flat">↔ 보유 ${holdingChanged ? '변경' : '변경 없음'}</span>`);
  const alertBar = alerts.length ? `<div class="change-alerts">${alerts.join('')}</div>` : '';

  if (!c.available || !c.hasChanges) {
    host.innerHTML = `${alertBar}<div class="change-line"><span>→</span><b>${c.available ? COPY.noChange : (c.summaryKo || '이전 운영 상태 비교 대기')}</b></div>`;
    return;
  }
  const bits = [];
  if ((c.added || []).length) bits.push(`신규 ${c.added.map((x) => tkName(x.ticker)).join(', ')}`);
  if ((c.removed || []).length) bits.push(`편출 ${c.removed.map((x) => tkName(x.ticker)).join(', ')}`);
  if ((c.weightIncreased || []).length) bits.push(`비중 증가 ${c.weightIncreased.map((x) => tkName(x.ticker)).join(', ')}`);
  if ((c.weightDecreased || []).length) bits.push(`비중 감소 ${c.weightDecreased.map((x) => tkName(x.ticker)).join(', ')}`);
  if ((c.entryStateChanged || []).length) bits.push(`진입상태 변경 ${c.entryStateChanged.map((x) => tkName(x.ticker)).join(', ')}`);
  if (c.regimeChanged) bits.push(`국면 ${REGIME_KO[c.regimeChanged.before] || c.regimeChanged.before} → ${REGIME_KO[c.regimeChanged.after] || c.regimeChanged.after}`);
  host.innerHTML = `${alertBar}<div class="change-line"><span>↻</span><div><b>이전 실행 대비 주요 변화</b><p>${bits.join(' · ')}</p></div></div>`;
};
const renderOverview = (d) => { renderDecisionHero(d); renderHoldings(d); renderChanges(d); };

// =========================================================================
// 2. Macro regime & risk budget
// =========================================================================
const macroNumber = (v, unit = '') => {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const digits = Math.abs(v) >= 100 ? 0 : 2;
  return `${Number(v).toLocaleString('ko-KR', { maximumFractionDigits: digits })}${unit ? ' ' + unit : ''}`;
};
const trendSvg = (series, references = [], opts = {}) => {
  const width = opts.width || 560, height = opts.height || 150;
  const pad = { l: 42, r: 14, t: 12, b: 25 };
  const clean = (series || []).map((s) => ({
    ...s,
    points: (s.points || []).filter((p) => p && Number.isFinite(Number(p.value)) && p.date),
  })).filter((s) => s.points.length);
  if (!clean.length) return '<div class="chart-none">추이 데이터가 아직 없습니다.</div>';
  const allPoints = clean.flatMap((s) => s.points);
  const times = allPoints.map((p) => new Date(`${p.date}T00:00:00Z`).getTime());
  const values = allPoints.map((p) => Number(p.value)).concat((references || []).map((r) => Number(r.value)).filter(Number.isFinite));
  const minT = Math.min(...times), maxT = Math.max(...times), timeSpan = maxT - minT || 1;
  let minV = Math.min(...values), maxV = Math.max(...values);
  const valueSpan = maxV - minV || Math.max(Math.abs(maxV), 1);
  minV -= valueSpan * 0.12; maxV += valueSpan * 0.12;
  const x = (date) => pad.l + ((new Date(`${date}T00:00:00Z`).getTime() - minT) / timeSpan) * (width - pad.l - pad.r);
  const y = (value) => pad.t + ((maxV - Number(value)) / (maxV - minV || 1)) * (height - pad.t - pad.b);
  const grid = [0, 0.5, 1].map((f) => {
    const yy = pad.t + f * (height - pad.t - pad.b);
    const val = maxV - f * (maxV - minV);
    return `<line x1="${pad.l}" y1="${yy.toFixed(1)}" x2="${width - pad.r}" y2="${yy.toFixed(1)}" class="chart-grid"/><text x="${pad.l - 6}" y="${(yy + 3).toFixed(1)}" text-anchor="end" class="chart-axis">${macroNumber(val)}</text>`;
  }).join('');
  const refLines = (references || []).map((r) => {
    const yy = y(r.value);
    return `<line x1="${pad.l}" y1="${yy.toFixed(1)}" x2="${width - pad.r}" y2="${yy.toFixed(1)}" class="chart-ref"><title>${r.labelKo || r.value}</title></line>`;
  }).join('');
  const lines = clean.map((s, idx) => {
    const points = s.points.map((p) => `${x(p.date).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
    return `<polyline points="${points}" class="chart-line chart-line-${idx}" vector-effect="non-scaling-stroke"><title>${s.label || ''}</title></polyline>`;
  }).join('');
  const first = allPoints.reduce((a, b) => a.date < b.date ? a : b);
  const last = allPoints.reduce((a, b) => a.date > b.date ? a : b);
  const dateLabel = (v) => v ? v.slice(2, 7).replace('-', '.') : '';
  return `<svg class="trend-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${opts.aria || '기간별 추이 차트'}">${grid}${refLines}${lines}<text x="${pad.l}" y="${height - 5}" class="chart-axis">${dateLabel(first.date)}</text><text x="${width - pad.r}" y="${height - 5}" text-anchor="end" class="chart-axis">${dateLabel(last.date)}</text></svg>`;
};
const sliceRecentThreeMonths = (points) => {
  const rows = points || [];
  if (!rows.length) return rows;
  const end = new Date(`${rows[rows.length - 1].date}T00:00:00Z`);
  const cutoff = new Date(end); cutoff.setUTCMonth(cutoff.getUTCMonth() - 3);
  const recent = rows.filter((p) => new Date(`${p.date}T00:00:00Z`) >= cutoff);
  return recent.length >= Math.min(3, rows.length) ? recent : rows.slice(-Math.min(4, rows.length));
};
const indicatorTrend = (i) => {
  const lines = [{ label: i.historyLabelKo || i.displayNameKo, points: sliceRecentThreeMonths(i.history) }];
  if (i.trendHistory && i.trendHistory.length) lines.push({ label: i.trendLabelKo || '추세', points: sliceRecentThreeMonths(i.trendHistory) });
  const legend = lines.filter((x) => x.points.length).map((x, idx) => `<span><i class="chart-key chart-key-${idx}"></i>${x.label}</span>`).join('');
  return `<button type="button" class="indicator-chart" data-macro-indicator="${i.name}" aria-label="${i.displayNameKo || i.name} 최근 3개월 미리보기, 장기 시계열 열기"><span class="mini-range">최근 3개월</span>${trendSvg(lines, i.referenceLines || [], { width: 520, height: 132, aria: `${i.displayNameKo || i.name} 최근 3개월 추이` })}<div class="chart-legend">${legend}</div><span class="macro-open">클릭해 장기 시계열 보기 →</span></button>`;
};
const indicatorCard = (i, axis) => {
  const contribution = i.axisContribution ?? 0;
  const cls = contribution > 0 ? 'bull' : contribution < 0 ? 'bear' : 'trans';
  const stale = i.stale ? '<span class="ax-stale">STALE</span>' : '';
  const context = i.contextOnly ? '<span class="ax-context">확인용 · 점수 미반영</span>' : '';
  const isReturn = i.transformation === 'three_month_price_return';
  const transformed = isReturn && i.transformedValue != null ? i.transformedValue * 100 : i.transformedValue;
  const change = isReturn && i.change != null ? i.change * 100 : i.change;
  return `<article class="ax-signal">
    <div class="ax-signal-top"><div><b>${i.displayNameKo || i.name}</b><small>${i.name}</small></div><span class="reg ${cls}">${axis.ko} ${i.axisContributionKo || (contribution > 0 ? '긍정' : contribution < 0 ? '부정' : '중립')}</span></div>${context}
    <p class="ax-method">${i.transformationKo || i.transformation || '최근 변화'}</p>
    <p class="ax-reading">${i.signalSummaryKo || '세부 판정 설명은 다음 빌드에서 제공됩니다.'}</p>
    ${indicatorTrend(i)}
    <dl class="ax-numbers">
      <div><dt>변환값</dt><dd>${macroNumber(transformed, i.valueUnit)}</dd></div>
      <div><dt>최근 변화</dt><dd>${macroNumber(change, i.changeUnit)}</dd></div>
      ${i.annualized3m != null ? `<div><dt>3개월 연율</dt><dd>${macroNumber(i.annualized3m, '%')}</dd></div>` : ''}
      <div><dt>장기 z</dt><dd>${macroNumber(i.zscore)}</dd></div>
    </dl>
    <details class="indicator-guide">
      <summary>이 지표는 무엇을 뜻하나?</summary>
      <div><p><b>정의</b>${i.guide?.meaningKo || '여러 국면 근거 중 하나로 사용하는 경제 지표입니다.'}</p><p><b>읽는 법</b>${i.guide?.readKo || i.transformationKo || ''}</p><p><b>투자에서</b>${i.guide?.useKo || `${axis.ko} 축의 보조 근거로 봅니다.`}</p><p><b>주의</b>${i.guide?.cautionKo || '단일 지표만으로 시장 방향을 단정하지 않습니다.'}</p></div>
    </details>
    <div class="ax-source"><span>관측 ${i.observationDate || '—'} · 발표시차 ${i.releaseLagBdays ?? '—'}영업일 · 경과 ${i.freshnessDays ?? '—'}일 ${stale}</span>${i.source ? `<a href="${i.source}" target="_blank" rel="noopener">원자료</a>` : ''}</div>
  </article>`;
};
const axisRow = (a, key) => {
  const v = a.value; const dirCls = v == null ? 'trans' : v > 0.15 ? 'bull' : v < -0.15 ? 'bear' : 'trans';
  const w = v == null ? 0 : Math.min(50, Math.abs(v) * 50);
  const direct = key === 'growth' || key === 'inflation';
  const indicators = (a.indicators || []).map((i) => indicatorCard(i, a)).join('') || '<div class="ax-none">사용 가능한 지표가 없습니다.</div>';
  return `<details class="ax-detail" open>
    <summary><div class="ax-row">
      <span class="ax-name">${a.ko}</span>
      <span class="ax-bar"><i class="${v >= 0 ? 'apos' : 'aneg'}" style="${v >= 0 ? 'left:50%' : 'right:50%'};width:${w}%"></i></span>
      <span class="ax-lab reg ${dirCls}">${a.labelKo}</span>
      <span class="ax-conf muted">점수 ${v == null ? '—' : Number(v).toFixed(2)} · 커버 ${Math.round((a.coverage ?? 0) * 100)}% · 신선도 ${Math.round((a.freshness ?? 0) * 100)}% · 합의 ${Math.round((a.agreement ?? 0) * 100)}%</span>
      <span class="ax-toggle">${direct ? '판정에 직접 사용' : '위험예산 보조'} · ${a.nIndicators ?? 0}개${a.nContextIndicators ? ` + 확인용 ${a.nContextIndicators}개` : ''} ▾</span>
    </div></summary>
    <div class="ax-signals">${indicators}</div>
  </details>`;
};
const regimeDecisionCard = (r) => {
  const d = r.regimeDecision || {};
  const g = d.growth || (r.axes || {}).growth || {};
  const i = d.inflation || (r.axes || {}).inflation || {};
  const summary = d.summaryKo || '성장과 물가 축의 방향·신뢰도를 조합해 국면을 판단합니다.';
  return `<div class="regime-decision">
    <div><span class="rb-h">왜 이 국면인가</span><b>${summary}</b></div>
    <div class="decision-axes">
      <span>성장 <b>${g.labelKo || '데이터 부족'} ${g.value == null ? '' : `(${Number(g.value).toFixed(2)})`}</b><em>신뢰 ${Math.round((g.confidence ?? 0) * 100)}%</em></span>
      <span>물가 <b>${i.labelKo || '데이터 부족'} ${i.value == null ? '' : `(${Number(i.value).toFixed(2)})`}</b><em>신뢰 ${Math.round((i.confidence ?? 0) * 100)}%</em></span>
    </div>
    <p>${d.confidenceRuleKo || '국면 신뢰도는 성장·물가 중 낮은 축 신뢰도입니다.'} · 방향 중립구간 ±${d.thresholds?.directionAbsMin ?? 0.15} · 최소 신뢰 ${Math.round((d.thresholds?.minimumConfidence ?? 0.34) * 100)}%</p>
    <small>${d.matrixKo || '성장×물가 조합으로 네 국면을 판정하며, 한 축이 중립이면 전환으로 보류합니다.'}</small>
  </div>`;
};
const regimeGuideCard = (r) => {
  const key = r.regime || 'Transition/Low confidence';
  const g = REGIME_GUIDE[key] || REGIME_GUIDE['Transition/Low confidence'];
  const cell = (regime, growth, inflation) => `<div class="cycle-cell ${key === regime ? 'active' : ''}"><span>${growth} 성장 · ${inflation} 물가</span><b>${REGIME_KO[regime] || regime}</b></div>`;
  return `<div class="regime-guide">
    <div class="rg-copy"><span>지금 국면을 한 문장으로</span><h3>${g.one}</h3><p><b>볼 것</b>${g.watch}</p><p><b>핵심 위험</b>${g.risk}</p></div>
    <div class="cycle-wrap"><div class="cycle-caption">성장 × 물가 국면 지도</div><div class="cycle-grid">${cell('Goldilocks', '가속', '둔화')}${cell('Reflation', '가속', '가속')}${cell('Deflation/Slowdown', '둔화', '둔화')}${cell('Stagflation', '둔화', '가속')}</div><small>강조된 칸이 현재 판정입니다. 신호가 엇갈리면 전환·저신뢰로 보류합니다.</small></div>
  </div>`;
};
const findMacroIndicator = (name) => Object.values(DATA?.macroRegime?.axes || {}).flatMap((a) => a.indicators || []).find((i) => i.name === name);
const macroPulseIndicator = (name, label) => {
  const i = findMacroIndicator(name);
  if (!i) return `<div class="macro-pulse-card missing"><span>${label}</span><b>데이터 대기</b><small>FRED 수집 상태 확인 필요</small></div>`;
  return `<button type="button" class="macro-pulse-card" data-macro-indicator="${name}"><span>${label}</span><b>${macroNumber(i.transformedValue, i.valueUnit)}</b><small>3개월 연율 ${macroNumber(i.annualized3m, '%')} · ${i.observationDate || '—'} 기준</small><em>장기 추이 →</em></button>`;
};
const macroEnvironment = (r) => {
  const e = r.environmentSummary || {};
  const pulse = `${macroPulseIndicator('Headline_CPI', 'Headline CPI · 전년비')}${macroPulseIndicator('Core_CPI', 'Core CPI · 전년비')}${macroPulseIndicator('Headline_PPI', 'Headline PPI · 생산단계')}${macroPulseIndicator('Core_PPI', 'Core PPI · 기조')}`;
  return `<section class="macro-cockpit">
    <div class="macro-cockpit-copy"><span>MACRO ENVIRONMENT</span><h3>${e.headlineKo || '성장·물가·금융여건을 함께 확인합니다.'}</h3><div class="macro-takeaways">${(e.takeawaysKo || []).map((x) => `<p>${x}</p>`).join('')}</div><small>${e.methodKo || ''}</small></div>
    <div class="macro-pulse">${pulse}<div class="macro-pulse-card axis"><span>성장 축</span><b>${r.axes?.growth?.labelKo || '—'}</b><small>점수 ${r.axes?.growth?.value ?? '—'} · 신뢰 ${Math.round((r.axes?.growth?.confidence ?? 0) * 100)}%</small></div><div class="macro-pulse-card axis"><span>금융여건 축</span><b>${r.axes?.financialConditions?.labelKo || '—'}</b><small>점수 ${r.axes?.financialConditions?.value ?? '—'} · 위험예산 보조</small></div></div>
  </section>`;
};
const renderRegime = (r) => {
  const host = $('#regimePanel');
  if (!r) { host.innerHTML = '<div class="none">국면 판정 데이터 없음</div>'; return; }
  $('#regimeMeta').textContent = `${r.asOf ? '기준 ' + r.asOf + ' · ' : ''}지표 ${r.indicatorCount ?? 0}개 · 커버리지 ${Math.round((r.coverage ?? 0) * 100)}%`;
  const rb = r.riskBudget || {};
  const changed = r.changed ? `<span class="chg">← ${REGIME_KO[r.priorRegime] || r.priorRegime}에서 전환</span>` : '';
  const axesHtml = Object.entries(r.axes || {}).map(([key, axis]) => axisRow(axis, key)).join('');
  const support = (r.supporting || []).map((s) => `<span class="ev ev-pos">${s.name}</span>`).join('') || '<span class="muted">—</span>';
  const contra = (r.contradicting || []).map((s) => `<span class="ev ev-neg">${s.name}</span>`).join('') || '<span class="muted">—</span>';
  host.innerHTML = `
    <div class="regime-head">
      <div class="regime-label reg ${r.regime && r.regime.startsWith('Transition') ? 'trans' : (r.regime === 'Goldilocks' || r.regime === 'Reflation') ? 'bull' : 'bear'}">${r.regimeDecision?.displayLabelKo || REGIME_KO[r.regime] || r.regime}</div>
      <div class="regime-conf">국면 판정 신뢰 <b>${Math.round((r.confidence ?? 0) * 100)}%</b> ${changed}</div>
      ${r.note ? `<div class="status-note warn">${r.note}</div>` : ''}
      ${r.pointInTimeLimitations ? `<div class="status-note info">한계: ${r.pointInTimeLimitations}</div>` : ''}
    </div>
    ${macroEnvironment(r)}
    ${regimeGuideCard(r)}
    ${regimeDecisionCard(r)}
    <div class="regime-axes">${axesHtml}</div>
    <div class="regime-lower">
      <div class="regime-budget">
        <div class="rb-h">위험예산 (매크로 레이어 — 개별 알파에 가산하지 않음)</div>
        <div class="rb-row"><span>주식 노출</span><b>${(rb.equityRangePct || []).join('~')}%</b><span>현금</span><b>${(rb.cashRangePct || []).join('~')}%</b></div>
        <div class="rb-tilt muted">스타일 틸트: ${rb.styleTilt || '—'}</div>
      </div>
      <div class="regime-ev"><div><span class="evh">근거</span>${support}</div><div><span class="evh">반대 근거</span>${contra}</div></div>
    </div>`;
};

let ACTIVE_MACRO = null;
let MACRO_RANGE = '10Y';
const MACRO_RANGES = { '1Y': 1, '3Y': 3, '5Y': 5, '10Y': 10, 'MAX': null };
const sliceMacroRange = (points, range) => {
  const rows = points || [];
  if (!rows.length || MACRO_RANGES[range] == null) return rows;
  const end = new Date(`${rows[rows.length - 1].date}T00:00:00Z`);
  const cutoff = new Date(end); cutoff.setUTCFullYear(cutoff.getUTCFullYear() - MACRO_RANGES[range]);
  return rows.filter((p) => new Date(`${p.date}T00:00:00Z`) >= cutoff);
};
const macroDialogMarkup = (i) => {
  const history = sliceMacroRange(i.history, MACRO_RANGE);
  const trend = sliceMacroRange(i.trendHistory, MACRO_RANGE);
  const lines = [{ label: i.historyLabelKo || i.displayNameKo, points: history }];
  if (trend.length) lines.push({ label: i.trendLabelKo || '추세', points: trend });
  const buttons = Object.keys(MACRO_RANGES).map((r) => `<button type="button" data-macro-range="${r}" class="${MACRO_RANGE === r ? 'active' : ''}">${r}</button>`).join('');
  const start = history[0]?.date || '—'; const end = history[history.length - 1]?.date || '—';
  const g = i.guide || {};
  return `<div class="ix-dialog-head"><div><span class="overline">${i.axis || 'MACRO'} · ${i.name}</span><h2>${i.displayNameKo || i.name} · ${MACRO_RANGE}</h2><p>${g.meaningKo || i.transformationKo || ''}</p></div><div class="ix-dialog-quote"><b>${macroNumber(i.transformedValue, i.valueUnit)}</b><span>${i.transformationKo || '최근 값'}</span><small>관측 ${i.observationDate || '—'}</small></div></div>
    <div class="ix-range" aria-label="거시 차트 기간">${buttons}</div>
    <div class="ix-big-chart">${trendSvg(lines, i.referenceLines || [], { width: 900, height: 330, aria: `${i.displayNameKo || i.name} ${MACRO_RANGE} 장기 시계열` })}</div>
    <div class="ix-kpis macro-kpis"><div><span>전년비/변환값</span><b>${macroNumber(i.transformedValue, i.valueUnit)}</b></div><div><span>3개월 연율</span><b>${macroNumber(i.annualized3m, '%')}</b></div><div><span>최근 변화</span><b>${macroNumber(i.change, i.changeUnit)}</b></div><div><span>장기 z</span><b>${macroNumber(i.zscore)}</b></div><div><span>표시 구간</span><b>${start} ~ ${end}</b></div></div>
    <div class="macro-detail-grid"><p><b>읽는 법</b>${g.readKo || i.signalSummaryKo || ''}</p><p><b>투자 환경에서</b>${g.useKo || ''}</p><p><b>주의</b>${g.cautionKo || ''}</p></div>
    <div class="ix-data-note"><span>발표시차 <b>${i.releaseLagBdays ?? '—'}영업일</b></span><span>시계열 <b>${history.length}개 관측치</b></span>${i.source ? `<a href="${i.source}" target="_blank" rel="noopener">FRED 원자료 ↗</a>` : ''}</div>`;
};
const showMacroDialog = (name) => {
  const i = findMacroIndicator(name); const dialog = $('#macroDialog'); const body = $('#macroDialogBody');
  if (!i || !dialog || !body) return;
  ACTIVE_MACRO = i; MACRO_RANGE = '10Y'; body.innerHTML = macroDialogMarkup(i);
  if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '');
};
const setMacroRange = (range) => {
  if (!ACTIVE_MACRO || !(range in MACRO_RANGES)) return;
  MACRO_RANGE = range; const body = $('#macroDialogBody'); if (body) body.innerHTML = macroDialogMarkup(ACTIVE_MACRO);
};

// =========================================================================
// 3. Expert consensus
// =========================================================================
const stanceKo = (s) => s == null ? '—' : s >= 1 ? `강한 긍정 (+${s})` : s > 0 ? `긍정 (+${s})` : s === 0 ? '중립 (0)' : s <= -1 ? `강한 부정 (${s})` : `부정 (${s})`;
const THEME_KO = {
  'AI/Semiconductors': 'AI·반도체', 'US Growth': '미국 성장', 'Rates/Inflation': '금리·물가',
  'Credit Quality': '신용 품질', Korea: '한국 경제',
};
const themeCard = (t) => {
  const agr = { high: ['합의 강함', 'bull'], mixed: ['혼재', 'trans'], low: ['의견 갈림', 'bear'], insufficient: ['1개 기관·합의 불가', 'trans'] }[t.agreement] || ['—', 'trans'];
  const views = (t.views || []).map((v) => `<div class="cv-view"><div><span>${v.institution}${v.sourceType === 'companyIR' ? ' <em class="ir">IR</em>' : ''}</span><small>공식 원문 검토 완료 · ${v.publishedAt ? v.publishedAt.slice(0, 10) : '발행일 미상'}${v.ageDays != null ? ` · ${v.ageDays}일 경과` : ''}</small></div><b>${stanceKo(v.stance)}</b>${v.url ? `<a href="${v.url}" target="_blank" rel="noopener">공식 원문 ↗</a>` : ''}${v.summary ? `<p>${v.summary}</p>` : ''}</div>`).join('');
  return `<div class="cv-card">
    <div class="cv-top"><div><span class="cv-verified">검증 완료</span><b>${THEME_KO[t.theme] || t.theme}</b></div><span class="reg ${agr[1]}">${agr[0]}</span></div>
    <div class="cv-meta">중앙값 스탠스 <b>${stanceKo(t.weightedMedianStance)}</b> · 분산 ${fmt(t.dispersion)} · 기관 ${t.institutionCount}곳</div>
    <div class="cv-views">${views}</div>
    ${t.counterCase ? `<div class="cv-counter">반대 논거: ${t.counterCase}</div>` : ''}
  </div>`;
};
const MISSING_FIELD_KO = { publishedAt: '발행일', verifiedAt: '검증일', stance: '방향 점수', summary: '검증 요약', verified: '검증 승인' };
const awaitingCard = (a) => {
  const missing = a.missingFields || ['publishedAt', 'verifiedAt', 'stance', 'summary', 'verified'];
  const risks = (a.risks || []).map((x) => `<span>${x}</span>`).join('') || '<span>등록 없음</span>';
  const signposts = (a.signposts || []).map((x) => `<span>${x}</span>`).join('') || '<span>등록 없음</span>';
  return `<article class="cv-pending">
    <div class="cv-pending-head"><div><b>${a.institution}</b><small>${a.theme || '주제 미분류'} · ${a.horizon || '기간 미정'}</small></div><span>${a.statusKo || '원문 검증 대기'}</span></div>
    <p class="cv-title">${a.title || '기관 전망 원문'}</p>
    <div class="cv-missing"><b>집계에 넣지 않은 이유</b>${missing.map((x) => `<em>${MISSING_FIELD_KO[x] || x} 없음</em>`).join('')}</div>
    <div class="cv-watch"><div><b>검증할 위험요인</b>${risks}</div><div><b>확인할 지표</b>${signposts}</div></div>
    ${a.url ? `<a class="cv-source" href="${a.url}" target="_blank" rel="noopener">공식 원문 확인 →</a>` : ''}
  </article>`;
};
const renderConsensus = (c) => {
  const host = $('#consensusPanel'); const sec = $('#consensus');
  if (!c) { sec.hidden = true; return; }
  sec.hidden = false;
  const candidates = c.candidateCount ?? (c.awaitingVerification || []).length + (c.verifiedCount || 0) + (c.staleCount || 0);
  $('#consensusMeta').textContent = `원문 검증 완료 ${c.verifiedCount ?? 0}/${candidates}건 · 검토 대기 ${c.awaitingCount ?? (c.awaitingVerification || []).length}건 · 기한 경과 ${c.staleCount ?? 0}건`;
  let html = '';
  if (c.themes && c.themes.length) html += `<div class="cv-method"><b>검증된 공식 전망 ${c.verifiedCount ?? 0}건</b><span>스탠스는 위험자산 관점 -2(방어적)~+2(건설적) 척도입니다. 요약은 원문을 대체하지 않으며, 기관 수가 1곳이면 ‘합의’로 보지 않습니다.</span></div>` + c.themes.map(themeCard).join('');
  else html += `<div class="cv-empty">
    <div><span>검증 커버리지</span><b>${Math.round((c.verificationCoverage ?? 0) * 100)}%</b></div>
    <section><h3>검증된 컨센서스가 아직 없는 이유</h3><p>${c.note || '등록 후보가 모두 원문 검증 전이라 방향을 집계하지 않습니다.'}</p><small>빈 화면이나 수집 오류가 아닙니다. 미검증 자료의 스탠스를 추정하지 않는 안전장치입니다.</small></section>
    <ol>${(c.verificationStepsKo || ['공식 원문과 발행일 확인', '스탠스·요약 기록', 'verified=true 승인', '기관 중복 제거 후 집계']).map((x) => `<li>${x}</li>`).join('')}</ol>
  </div>`;
  if (c.awaitingVerification && c.awaitingVerification.length) {
    html += `<div class="cv-await"><div class="cv-await-title"><b>원문 검토 대기 ${c.awaitingVerification.length}건</b><span>자료가 있다는 사실은 보여주되, 내용을 확인하기 전에는 방향 집계에 넣지 않습니다.</span></div><div class="cv-pending-grid">${c.awaitingVerification.map(awaitingCard).join('')}</div></div>`;
  }
  host.innerHTML = html;
};

// =========================================================================
// 4. SEC 13F institutional disclosure snapshots
// =========================================================================
const f13Esc = (v) => String(v ?? '—').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const f13Money = (v) => {
  if (v == null || Number.isNaN(Number(v))) return '—';
  const n = Number(v); const abs = Math.abs(n);
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(abs >= 1e11 ? 0 : 1)}B`;
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(abs >= 1e8 ? 0 : 1)}M`;
  return `$${Math.round(n).toLocaleString('en-US')}`;
};
const f13Option = (row) => row.putCall ? `<em class="f13-option ${row.putCall.toLowerCase()}">${f13Esc(row.putCall)}</em>` : '';
const f13Holding = (row, managerId) => `<button type="button" class="f13-holding" data-f13-manager="${f13Esc(managerId)}" data-f13-id="${f13Esc(row.cusip || row.issuer)}" aria-label="${f13Esc(row.issuer)} 13F 공시 상세 보기">
  <div><b>${f13Esc(row.issuer)}</b><span>${f13Esc(row.titleClass)} ${f13Option(row)}</span></div>
  <div class="f13-weight"><i style="width:${Math.min(100, Number(row.portfolioWeightPct) || 0)}%"></i></div>
  <strong>${fmt(row.portfolioWeightPct, '%', 1)}</strong>
</button>`;
const F13_CHANGE_KO = { new: '신규', increased: '주식 수 확대', decreased: '주식 수 축소', exited: '공시에서 제외' };
const f13Change = (kind, row, managerId) => {
  const pct = row.shareChangePct == null ? '' : ` ${row.shareChangePct > 0 ? '+' : ''}${row.shareChangePct}%`;
  return `<button type="button" class="f13-change ${kind}" data-f13-manager="${f13Esc(managerId)}" data-f13-id="${f13Esc(row.cusip || row.issuer)}"><i>${F13_CHANGE_KO[kind]}</i><b>${f13Esc(row.issuer)}</b>${f13Option(row)}<em>${pct}</em></button>`;
};
const f13ManagerCard = (m) => {
  if (!['AVAILABLE', 'CACHED_OFFICIAL'].includes(m.status)) return `<article class="f13-card unavailable">
    <div class="f13-head"><div><span>${f13Esc(m.managerKo)}</span><h3>${f13Esc(m.name)}</h3></div><em>원문 확인 불가</em></div>
    <p>${f13Esc(m.noteKo || 'SEC 원문을 불러오지 못해 이전 분기 수치를 대신 표시하지 않습니다.')}</p>
  </article>`;
  const changes = m.changes || {};
  const recency = m.reportRecency === 'OLDER_LAST_AVAILABLE'
    ? '<em class="f13-recency lagged">최근 분기 제출 없음</em>'
    : '<em class="f13-recency">추적군 최신 분기</em>';
  const changeRows = ['new', 'increased', 'decreased', 'exited']
    .flatMap((kind) => (changes[kind] || []).slice(0, 2).map((row) => f13Change(kind, row, m.id))).join('');
  const sourceBadge = m.status === 'CACHED_OFFICIAL' ? '<em class="f13-cache">공식 캐시</em>' : '<em class="f13-live">SEC 확인</em>';
  return `<article class="f13-card ${m.featured ? 'featured' : ''}">
    <div class="f13-head"><div><span>${f13Esc(m.managerKo)} ${sourceBadge}</span><h3>${f13Esc(m.name)}</h3></div><a href="${m.filingUrl}" target="_blank" rel="noopener">SEC 원문 ↗</a></div>
    <div class="f13-dates"><div><b>${f13Esc(m.reportDate)} 기준</b>${recency}</div><span>${f13Esc(m.filingDate)} 제출 · 직전 ${f13Esc(m.previousReportDate)}</span></div>
    <div class="f13-kpis"><div><span>공시 평가액</span><b>${f13Money(m.totalValueUsd)}</b></div><div><span>포지션</span><b>${fmt(m.positionCount)}개</b></div><div><span>상위 5개 집중도</span><b>${fmt(m.top5WeightPct, '%', 1)}</b></div></div>
    <div class="f13-subhead"><b>상위 보유종목</b><span>공시 평가액 비중</span></div>
    <div class="f13-holdings">${(m.topHoldings || []).slice(0, 5).map((row) => f13Holding(row, m.id)).join('') || '<div class="none">보유내역 없음</div>'}</div>
    <div class="f13-subhead"><b>직전 분기 대비</b><span>주식 수 기준</span></div>
    <div class="f13-changes">${changeRows || '<span class="muted">비교 가능한 변화 없음</span>'}</div>
  </article>`;
};
const renderInstitutional13F = (block) => {
  const sec = $('#institutional'); const host = $('#institutionalPanel');
  if (!sec || !host) return;
  const managers = block?.managers || [];
  const available = managers.filter((x) => ['AVAILABLE', 'CACHED_OFFICIAL'].includes(x.status));
  $('#institutionalMeta').textContent = `13F 최신 기준 ${block?.latestReportDate || '—'} · 마지막 확인 ${block?.fetchedAt ? block.fetchedAt.slice(0, 16).replace('T', ' ') + ' UTC' : '—'} · 표시 ${available.length}/${block?.managerCount ?? managers.length}곳 · 실시간 ${block?.liveCount ?? 0} · 공식 캐시 ${block?.cachedCount ?? 0}${block?.laggedManagerCount ? ` · 이전 분기 ${block.laggedManagerCount}곳` : ''}`;
  $('#institutionalCaveat').textContent = block?.limitationKo || '13F는 분기말 기준의 지연 공시이며 실시간 보유내역이 아닙니다.';
  if (!managers.length) {
    host.innerHTML = '<div class="none f13-empty">SEC 13F 원문을 불러오지 못했습니다. 이전 수치를 현재 값처럼 대신 표시하지 않습니다.</div>';
    return;
  }
  host.innerHTML = managers.map(f13ManagerCard).join('');
};
const renderNationalPension = (nps) => {
  const host = $('#npsPanel'); if (!host) return;
  if (!nps || !['AVAILABLE', 'CACHED_OFFICIAL'].includes(nps.status)) { host.innerHTML = `<div class="none nps-empty">${nps?.noteKo || '국민연금 공식 운용 현황을 불러오지 못했습니다.'}</div>`; return; }
  const badge = nps.status === 'CACHED_OFFICIAL' ? '공식 캐시' : '공식 원문 확인';
  const rows = (nps.allocations || []).map((x) => `<div class="nps-allocation"><div><b>${f13Esc(x.labelKo)}</b><span>${fmt(x.valueTrillionKrw, '조 원', 1)}</span></div><div class="nps-bar"><i style="width:${Math.min(100, Number(x.weightPct) || 0)}%"></i></div><strong>${fmt(x.weightPct, '%', 1)}</strong></div>`).join('');
  host.innerHTML = `<section class="nps-card"><div class="nps-head"><div><span>NATIONAL PENSION SERVICE · ${badge}</span><h3>국민연금 전체 기금 자산배분</h3><p>${nps.scopeKo || ''}</p></div><a href="${nps.sourceUrl}" target="_blank" rel="noopener">기금운용본부 원문 ↗</a></div><div class="nps-stats"><div><span>기금 규모</span><b>${fmt(nps.totalFundTrillionKrw, '조 원', 1)}</b></div><div><span>주식 합계</span><b>${fmt(nps.equityWeightPct, '%', 1)}</b></div><div><span>해외주식</span><b>${fmt(nps.overseasEquityWeightPct, '%', 1)}</b></div><div><span>공시 기준</span><b>${nps.asOfLabelKo || nps.asOf || '—'}</b></div></div><div class="nps-allocations">${rows}</div><p class="nps-note">${nps.provisional ? '당해연도 수치는 잠정치입니다. ' : ''}${nps.limitationKo || ''}</p></section>`;
};

// =========================================================================
// 5. Region long-term research + 6. entry states
// =========================================================================
const fBar = (label, v) => `<div class="fb"><span>${label}</span><div class="fb-bar"><i style="width:${v ?? 0}%"></i></div><b>${v != null ? v : '—'}</b></div>`;
const prosCons = (p) => {
  const fp = p.factorPercentiles || {}; const risk = p.risk || {};
  const completeness = p.dataCompleteness ?? p.financialCoverage ?? 0;
  const pros = [], cons = [];
  if (fp.momentum >= 66) pros.push(`모멘텀 상위 (${fp.momentum}p)`);
  if (fp.value >= 66) pros.push(`밸류 매력 (${fp.value}p)`);
  if (fp.quality >= 66) pros.push(`퀄리티 우수 (${fp.quality}p)`);
  if (fp.lowvol >= 66) pros.push(`저변동 (${fp.lowvol}p)`);
  if (p.aboveMA200) pros.push('200일선 위 (추세 확인)');
  if (p.alphaPercentile >= 66) pros.push(`섹터중립 알파 ${topPct(p.alphaPercentile)}`);
  if (p.valueTrap) cons.push('가치함정 신호 (싼데 퀄리티·현금흐름 약함)');
  if (completeness < 0.6) cons.push(`데이터 완전성 낮음 (${Math.round(completeness * 100)}%)`);
  if (!p.aboveMA200) cons.push('200일선 아래 (추세 미확인)');
  if (fp.quality != null && fp.quality <= 33) cons.push(`퀄리티 하위 (${fp.quality}p)`);
  if (risk.maxDD252Pct != null && risk.maxDD252Pct <= -25) cons.push(`최근 낙폭 ${risk.maxDD252Pct}%`);
  if (risk.cvar95Pct != null && risk.cvar95Pct >= 4) cons.push(`꼬리위험 CVaR ${risk.cvar95Pct}%`);
  if ((p.entry || {}).overheatPercentile != null && p.entry.overheatPercentile >= 85) cons.push('유니버스 내 과열');
  return { pros: pros.slice(0, 2), cons: cons.slice(0, 2) };
};
const ltRow = (p, blocked = false, held = false) => {
  const { pros, cons } = prosCons(p);
  const e = blocked ? {} : (p.entry || {}); const risk = p.risk || {};
  const w = blocked ? null : p.modelSleeveWeightPct;
  const evidence = p.evidenceCoverage ?? p.factorCoverage ?? p.confidence ?? 0;
  const completeness = p.dataCompleteness ?? p.financialCoverage ?? 0;
  const sourceQuality = p.sourceQuality ?? 0;
  const empirical = p.empiricalValidationStatus || 'PENDING_PAPER_HISTORY';
  const trust = Math.min(evidence, completeness, sourceQuality);
  const trustLabel = trust >= 0.8 ? '높음' : trust >= 0.6 ? '보통' : '낮음';
  const broken = (p.invalidation || []).filter((x) => x.state === 'BREACHED');
  return `<div class="lt-item ${held ? 'lt-held' : ''}">
    <div class="lt-top"><div>${tkLink(p.ticker)}<span class="muted lt-sec">${p.sectorKo || p.sector || '미분류'}</span></div><div class="lt-state">${held ? '<span class="vbadge v-held">보유</span>' : ''}${viewBadge(p.longTermResearchView)}${e.entryState ? entryBadge(e.entryState) : ''}</div></div>
    <p class="lt-thesis">${p.thesisKo || `알파 ${topPct(p.alphaPercentile)}`}</p>
    <div class="lt-essential"><span>알파 <b>${topPct(p.alphaPercentile)}</b></span><span>슬리브 <b>${w != null ? w + '%' : '—'}</b></span><span>데이터 <b>${trustLabel}</b></span></div>
    ${blocked ? '' : `<div class="lt-inval"><b>${term('invalidation', '깨지는 지점')}</b>${invalidationLine(p.invalidation, 2) || '<span class="inval">조건 산출 대기</span>'}</div>`}
    <details class="lt-details"><summary>근거 · 위험 · 전체 무효화 조건</summary>
      <div class="lt-args"><div class="pro"><b>핵심 근거</b>${(pros.length ? pros : ['확인 가능한 강한 근거 부족']).map((x) => `<span>＋ ${x}</span>`).join('')}</div><div class="con"><b>핵심 위험</b>${(cons.length ? cons : ['뚜렷한 위험 신호 없음']).map((x) => `<span>! ${x}</span>`).join('')}</div></div>
      <div class="lt-bars">${fBar('모멘텀', p.factorPercentiles?.momentum)}${fBar('밸류', p.factorPercentiles?.value)}${fBar('퀄리티', p.factorPercentiles?.quality)}${fBar('저변동', p.factorPercentiles?.lowvol)}</div>
      <div class="lt-risk">변동성 ${fmt(risk.vol252Pct, '%', 0)} · 하방변동 ${fmt(risk.downsideVolPct, '%', 0)} · 최대낙폭 ${fmt(risk.maxDD252Pct, '%', 0)} · CVaR ${fmt(risk.cvar95Pct, '%', 1)} · β ${fmt(risk.beta, '', 2)}</div>
      ${blocked ? '' : `<div class="lt-inval-all">${(p.invalidation || []).map((x) => `<span class="inval ${x.state === 'BREACHED' ? 'broken' : ''}"><em>${x.labelKo}</em> ${x.currentKo} → ${x.triggerKo}</span>`).join('') || '<span class="inval">조건 산출 대기</span>'}${p.invalidationBasisKo ? `<small>기준선: ${p.invalidationBasisKo}</small>` : ''}</div>`}
      <div class="lt-detail-grid"><span>${term('evidence', '근거 커버리지')} <b>${Math.round(evidence * 100)}%</b></span><span>${term('completeness', '데이터 완전성')} <b>${Math.round(completeness * 100)}%</b></span><span>${term('source', '소스 품질')} <b>${Math.round(sourceQuality * 100)}%</b></span><span>실증 상태 <b title="${empirical}">${statusLabel(empirical)}</b></span><span>12-1M <b>${sp(p.mom12_1Pct)}</b></span></div>
      ${!blocked && e.reasons && e.reasons.length ? `<div class="lt-entry">진입 근거: ${e.reasons.join(' · ')}</div>` : ''}
    </details>
    ${broken.length ? `<div class="lt-broken">! 이미 깨진 조건 ${broken.length}건 — ${broken.map((x) => x.labelKo).join(', ')}</div>` : ''}
  </div>`;
};
const renderLongTerm = (d) => {
  const lt = d.longTerm; const sec = $('#watchlist');
  if (!lt || !lt.regions) { sec.hidden = true; return; }
  sec.hidden = false;
  const hm = lt.horizonMonths || [6, 12];
  $('#ltMeta').textContent = `보유 ${hm[0]}~${hm[hm.length - 1]}개월 · ${lt.rebalance || ''} · 재무 커버리지 ${lt.fundamentalsCoverage ?? '—'}%` + (lt.weightsWithheld ? ' · 비중 숨김(차단)' : '');
  const heldSet = new Set(((d.modelPortfolio || {}).positions || []).filter((p) => p.modelPortfolioWeightPct > 0).map((p) => p.ticker));
  const fill = (el, reg) => {
    const r = lt.regions[reg];
    const rows = (r && ((r.picks && r.picks.length) ? r.picks : r.researchTable)) || [];
    let html = d.recommendationsBlocked ? `<div class="status-note info">${COPY.blocked}</div>` : '';
    // Only the next names in line are shown up front; the tail stays one click
    // away so the watchlist cannot drown the decision above it.
    const card = (p) => ltRow(p, d.recommendationsBlocked, heldSet.has(p.ticker));
    if (!rows.length) html += '<div class="none">데이터 부족</div>';
    else {
      html += rows.slice(0, 6).map(card).join('');
      if (rows.length > 6) html += `<details class="lt-more"><summary>나머지 ${rows.length - 6}개 후보 보기</summary><div class="lt-list">${rows.slice(6).map(card).join('')}</div></details>`;
    }
    if (r && r.dataInsufficient && r.dataInsufficient.length) html += `<details class="lt-insuf"><summary>데이터 부족 제외 ${r.dataInsufficient.length}개</summary><p>팩터·재무 기준 미달: ${r.dataInsufficient.slice(0, 8).map((x) => tkName(x.ticker)).join(', ')}${r.dataInsufficient.length > 8 ? ' 외' : ''}</p></details>`;
    $(el).innerHTML = html;
  };
  fill('#ltKR', 'KR'); fill('#ltUS', 'US');
  $('#ltCaveats').textContent = '이 목록은 후보이며 보유 종목이 아닙니다. 실제 보유는 위 모델 포트폴리오의 집중된 종목뿐입니다. 팩터·재무 시점과 실증 검증 한계는 상세 방법론에서 확인할 수 있습니다.';
};

// 6. Auditable model portfolio (risk-weighted base + regional active Kelly)
const renderModelPortfolio = (d) => {
  const mp = d.modelPortfolio; const sec = $('#portfolio'); const host = $('#modelPortfolioPanel');
  if (!mp) { sec.hidden = true; return; }
  sec.hidden = false;
  const status = mp.status || 'SHADOW_INSUFFICIENT_HISTORY';
  const applied = mp.kellyApplied === true;
  const method = allocMethod(mp);
  $('#modelPortfolioMeta').textContent = `${method.name} · ${statusLabel(status)}`;
  if (d.recommendationsBlocked || status === 'BLOCKED') {
    host.innerHTML = `<div class="status-note bad">■ ${COPY.blocked}<details><summary>기술 상태</summary><code>${status}</code></details></div>`;
    return;
  }
  const rows = (mp.positions || []).filter((p) => p.modelPortfolioWeightPct > 0);
  const conc = mp.concentration || {};
  const gate = (mp.validation || {}).sampleGate || {}; const actual = gate.actual || {}; const threshold = gate.thresholds || {};
  const kpis = `<div class="mp-kpis">
    ${chip('배분 방식', method.name, applied ? 'ok' : 'info')}
    ${chip('최종 주식 비중', fmt(100 - (mp.cashPct ?? 100), '%', 1))}
    ${chip('현금 비중', fmt(mp.cashPct, '%', 1))}
    ${chip('종목 수', rows.length)}
    ${chip('유효 종목수', conc.effectiveNames ?? '—', 'info')}
    ${chip('최대 단일 비중', fmt(conc.top1WeightPct, '%', 1))}
    ${chip('예상 변동성', mp.expectedVolPct != null ? `${mp.expectedVolPct}% active` : '—')}
    ${chip('회전율', turnoverLabel(mp))}
  </div>`;
  const dirKo = (v) => ({ INCREASE: '▲ 비중 확대', DECREASE: '▼ 비중 축소', UNCHANGED: '→ 변화 없음', NOT_APPLIED: '— Kelly 미적용' }[v] || '—');
  const table = rows.length ? `<div class="mp-table" role="table"><div class="mp-row mp-head" role="row"><span>종목</span><span>최종 비중</span><span>기준 비중</span><span>${applied ? 'Kelly 조정' : '컨빅션 순위'}</span><span>진입상태</span><span>주요 제약</span></div>${rows.map((p) => {
    const bindingList = (p.bindingConstraints || []).map((x) => x.replaceAll('_', ' ')); const binding = bindingList[0] || '없음';
    const interval = p.expectedReturnIntervalPct || [];
    return `<details class="mp-position"><summary class="mp-row" role="row"><span data-label="종목">${tkLink(p.ticker)} <small>${p.region || ''}</small></span><span data-label="최종 비중"><b>${fmt(p.modelPortfolioWeightPct, '%', 1)}</b></span><span data-label="기준 비중">${fmt(p.riskWeightedWeightPct, '%', 1)}</span><span data-label="${applied ? 'Kelly 조정' : '컨빅션 순위'}" class="kelly-${(p.kellyAdjustment || '').toLowerCase()}">${applied ? dirKo(p.kellyAdjustment) : `${p.convictionRank ?? '—'}위 · ${fmt(p.convictionScore, '', 2)}`}</span><span data-label="진입상태">${p.entryState ? entryBadge(p.entryState) : '—'}</span><span data-label="주요 제약" class="mp-why">${binding}</span></summary>
      <div class="mp-position-detail">
        <div><span>컨빅션 순위</span><b>${p.convictionRank ?? '—'}위 (${fmt(p.convictionScore, '', 2)})</b></div><div><span>하방변동성</span><b>${fmt(p.downsideVolPct, '%', 1)}</b></div><div><span>기대 초과수익</span><b>${p.expectedReturnStatus === 'SHADOW' ? sp(p.expectedExcessReturnPct) : '추정 보류'}</b></div><div><span>표본 / 유효 날짜</span><b>${p.expectedReturnSampleSize || 0} / ${p.expectedReturnEffectiveDates || 0}</b></div><div><span>독립 날짜</span><b>${p.expectedReturnUniqueDates || 0}</b></div><div><span>불확실성</span><b>${interval.length === 2 ? `${interval[0]}~${interval[1]}%` : '표본 부족'}</b></div><div><span>실현 변동성</span><b>${fmt(p.riskLevel, '%', 1)}</b></div><div><span>비제약 Kelly</span><b>${applied ? fmt(p.unconstrainedKellyWeightPct, '%', 1) : '미적용'}</b></div><div><span>제약 Kelly</span><b>${applied ? fmt(p.constrainedKellyWeightPct, '%', 1) : '미적용'}</b></div><div><span>거래비용 추정</span><b>${p.transactionCost ? fmt(p.transactionCost.estimatedCostPct, '%', 2) : '—'}</b></div><div><span>전체 제약</span><b>${bindingList.join(' · ') || '없음'}</b></div>
        <div class="mp-inval"><span>깨지는 지점</span><b>${invalidationLine(p.invalidation, 4) || '조건 산출 대기'}</b></div>
      </div></details>`;
  }).join('')}</div>` : '<div class="none">표시할 종목 비중이 없습니다.</div>';
  const exposure = (title, values) => `<div class="mp-exp"><b>${title}</b>${Object.entries(values || {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<span>${k}<em>${v}%</em></span>`).join('') || '<span>데이터 없음</span>'}</div>`;
  const reason = applied ? '' : `<div class="status-note info"><b>${COPY.fallback}</b><details><summary>기술 사유</summary><code>${mp.fallbackReason || 'kelly_not_activated'}</code></details></div>`;
  const concNote = (conc.warnings || []).length
    ? `<div class="status-note warn"><b>집중도 경고</b><ul>${conc.warnings.map((w) => `<li>${CONCENTRATION_KO[w] || w}</li>`).join('')}</ul></div>` : '';
  const currency = mp.currencyPolicy || {}; const fxWarning = currency.warning ? '<span class="risk-cue">! 환율 위험은 지역 배분 레이어에서만 표시되며 종목 active covariance에는 미반영</span>' : '<span>● 환율 수익률 반영</span>';
  const methodFold = `<details class="mp-method"><summary>배분 규칙 · Kelly 승격 조건 상세</summary><p class="mp-method-lead"><b>${method.name}</b> — ${method.how}</p><div class="mp-method-grid"><div><span>${term('concentration2', '유효 종목수')}</span><b>${conc.effectiveNames ?? '—'} / ${conc.names ?? 0}종목</b></div><div><span>상위 3종목 비중</span><b>${fmt(conc.top3WeightPct, '%', 1)}</b></div><div><span>단일종목 상한</span><b>${fmt((mp.constraints?.maxPositionWeight ?? 0) * 100, '%', 0)}</b></div><div><span>업종 상한</span><b>${fmt((mp.constraints?.maxSectorWeight ?? 0) * 100, '%', 0)}</b></div><div><span>Base Kelly fraction</span><b>${fmt((mp.baseKellyFraction ?? 0) * 100, '%', 1)}</b></div><div><span>매크로 조정 위험배율</span><b>${fmt((mp.appliedKellyFraction ?? 0) * 100, '%', 1)}</b></div><div><span>Kelly 혼합 비율</span><b>${applied ? fmt((mp.kellyBlendWeight ?? 0) * 100, '%', 1) : '미적용'}</b></div><div><span>기준통화 · 환헤지</span><b>${currency.baseCurrency || 'KRW'} · ${currency.fxHedged ? '반영' : '미적용'}</b></div></div><p>${fxWarning}</p><div class="gate-grid"><div><span>Paper days</span><b>${actual.paperDays ?? mp.validation?.currentPaperDays ?? 0} / ${threshold.paperDays ?? '—'}</b></div><div><span>만기 신호</span><b>${actual.maturedSignals ?? mp.validation?.currentMaturedSignals ?? 0} / ${threshold.maturedSignals ?? '—'}</b></div><div><span>유효 날짜</span><b>${actual.effectiveDates ?? mp.validation?.currentEffectiveDates ?? 0} / ${threshold.effectiveDates ?? '—'}</b></div><div><span>관측 날짜</span><b>${actual.uniqueDates ?? mp.validation?.currentUniqueDates ?? 0} / ${threshold.uniqueDates ?? '—'}</b></div><div><span>최초 검토 가능</span><b>${mp.validation?.earliestReviewDate || '산정 대기'}</b></div><div><span>미달 항목</span><b>${(mp.validation?.missing || []).join(', ') || '없음'}</b></div></div><p class="technical-code">기술 상태: ${status} · 표본법: ${gate.method || 'DATE_CLUSTERED_NEWEY_WEST_HAC'}</p></details>`;
  host.innerHTML = `${kpis}${reason}${concNote}${table}${methodFold}<details class="mp-exposure-detail"><summary>지역·업종·테마 노출</summary><div class="mp-exposures">${exposure('지역', mp.regionExposure)}${exposure('업종', mp.sectorExposure)}${exposure('테마', mp.themeExposure)}</div></details>`;
};

// 6. Entry & risk warnings (aggregated)
const renderEntry = (d) => {
  const lt = d.longTerm; const host = $('#entryPanel');
  if (!lt || !lt.regions) { $('#entry').hidden = true; return; }
  $('#entry').hidden = false;
  if (d.recommendationsBlocked) {
    host.innerHTML = `<div class="status-note info">${COPY.entryWithheld}</div>`;
    return;
  }
  const rows = [];
  for (const reg of ['KR', 'US']) {
    const r = lt.regions[reg]; if (!r) continue;
    for (const p of (r.researchTable || [])) rows.push(p);
  }
  const warn = rows.filter((p) => ['WAIT_FOR_PULLBACK', 'EVENT_RISK', 'AVOID'].includes((p.entry || {}).entryState) && p.longTermResearchView !== 'NEGATIVE');
  const buy = rows.filter((p) => (p.entry || {}).entryState === 'ACCUMULATE_GRADUALLY' && p.longTermResearchView === 'POSITIVE');
  const box = (title, arr, empty) => `<div class="entry-col"><div class="col-h">${title}</div>${arr.length ? arr.slice(0, 8).map((p) => `<div class="entry-row">${tkLink(p.ticker)}${viewBadge(p.longTermResearchView)}${entryBadge((p.entry || {}).entryState)}<span class="muted">${((p.entry || {}).reasons || [])[0] || ''}</span></div>`).join('') : `<div class="none">${empty}</div>`}</div>`;
  host.innerHTML = box('장기 긍정 · 지금 분할매수', buy, '해당 종목 없음') +
    box('장기 긍정이나 지금은 대기 (되돌림/이벤트/회피)', warn, '경고 없음');
};

// 6. Concentration
const renderConcentration = (d) => {
  const lt = d.longTerm; const host = $('#concentrationPanel');
  if (!lt || !lt.regions) { $('#concentration').hidden = true; return; }
  $('#concentration').hidden = false;
  const one = (reg) => {
    const r = lt.regions[reg]; if (!r) return `<div><div class="col-h">${reg}</div><div class="none">데이터 없음</div></div>`;
    const exp = r.sectorExposure || {};
    const bars = Object.entries(exp).sort((a, b) => b[1] - a[1]).map(([s, w]) => `<div class="conc-row"><span>${s}</span><div class="conc-bar"><i style="width:${Math.min(100, w * 2)}%"></i></div><b>${w}%</b></div>`).join('') || '<div class="none">슬리브 비중 없음(차단/데이터부족)</div>';
    return `<div><div class="col-h">${reg === 'KR' ? '국내 (KR)' : '국외 (US)'} · 현금 ${r.cashPct != null ? r.cashPct + '%' : '—'}</div>${bars}</div>`;
  };
  host.innerHTML = one('KR') + one('US');
};

// 7. Paper performance
const renderPaper = (d) => {
  const host = $('#paperPanel');
  const pp = d.paperPerformance;
  const vs = d.validationStatus || {};
  if (pp && pp.n) {
    $('#paperMeta').textContent = `누적 ${pp.n}건 · rank IC ${fmt(pp.rankIC)}`;
    host.innerHTML = `<div class="paper-metrics">${Object.entries(pp.byView || {}).map(([v, o]) => `<div class="pm"><span>${(VIEW[v] || [v])[0]}</span><b>${sp((o.meanFwd ?? 0) * 100)}</b><em>n=${o.n}</em></div>`).join('')}</div>`;
  } else {
    $('#paperMeta').textContent = `검증 데이터 축적 중 · paper ${vs.paperDays ?? 0}일 · 만기 신호 ${vs.maturedSignals ?? 0}개`;
    const regionIc = Object.entries(vs.regionIC || {}).map(([region, x]) => `${region} IC ${x.mean ?? '—'} (날짜 ${x.nDates ?? 0}, 종목 ${x.nSignals ?? 0})`).join(' · ') || '지역별 IC 대기';
    host.innerHTML = `<div class="status-note info"><b>${COPY.validationPending}</b><details><summary>검증 지표 상세</summary><p>paper days ${vs.paperDays ?? 0} · 만기 신호 ${vs.maturedSignals ?? 0} · 유효 날짜 ${vs.eligibleDates ?? 0}</p><p>${regionIc}</p><p>비용 차감 초과수익 ${vs.costAdjustedExcessReturn ?? '—'} · MDD ${vs.MDD ?? '—'} · CVaR ${vs.CVaR ?? '—'}</p><p>미달: ${(vs.reasons || ['paper history 누적 중']).join(' · ')}</p></details></div>`;
  }
};

// =========================================================================
// 8. Short-term ML ideas (reference only)
// =========================================================================
const ideaRow = (i) => `
  <div class="idea">
    <div class="idea-top"><strong class="tklink" data-tk="${i.ticker}">${tkName(i.ticker)}</strong>${tkSub(i.ticker)}<span class="reg ${regCls(i.regime)}">${regKo(i.regime)}</span><span class="edge" data-x="prob">참고 신호</span></div>
    <div class="idea-bar"><i style="width:${Math.round(((i.modelScore ?? i.probUp) ?? 0) * 100)}%"></i></div>
    <div class="idea-meta"><span>${term('prob', '모델 점수')} <b>${pct0((i.modelScore ?? i.probUp))}</b></span><span>${term('hold', '재평가')} <b>~${i.holdUntil}</b> (${i.horizon}D)</span></div>
    <div class="idea-why">${i.why || ''}</div>
  </div>`;
const renderIdeas = (d) => {
  if (d.recommendationsBlocked) {
    $('#tradeKR').innerHTML = $('#tradeUS').innerHTML = `<div class="none">${COPY.signalWithheld}</div>`;
    $('#tradeMeta').textContent = '차단 · ' + ((d.blockReasons || []).join(' · ') || '데이터 안전');
  } else {
    const ti = d.tradeIdeas || { KR: [], US: [] };
    $('#tradeMeta').textContent = `참고용 · 10영업일`;
    const fill = (el, arr) => $(el).innerHTML = (arr && arr.length) ? arr.map(ideaRow).join('') : '<div class="none">참고 신호 없음</div>';
    fill('#tradeKR', ti.KR); fill('#tradeUS', ti.US);
  }
  const sc = d.screened || [];
  $('#screenCount').textContent = `· ${sc.length}개`;
  $('#screenTable').innerHTML = `<div class="srow sh"><span>종목</span><span>지역</span><span>${term('prob', '모델 점수')}</span><span>국면</span></div>` +
    sc.map((s) => `<div class="srow" data-key="${(s.ticker + ' ' + tkName(s.ticker)).toLowerCase()}"><span>${tkLink(s.ticker)}</span><span>${s.region}</span><span>${pct0(s.modelScore ?? s.probUp)}</span><span class="reg ${regCls(s.regime)}">${regKo(s.regime)}</span></div>`).join('');
  filterScreen();
};

// --- indices tape ---
const nfmt = (v, d) => (v == null || Number.isNaN(v)) ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const chg = (v, d = 2) => (v == null || Number.isNaN(v)) ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)}%`;
const sparkSvg = (vals, periodReturn) => {
  if (!vals || vals.length < 2) return '';
  const w = 116, h = 30, min = Math.min(...vals), max = Math.max(...vals), span = (max - min) || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1) * w).toFixed(1)},${(h - 2 - (v - min) / span * (h - 4)).toFixed(1)}`).join(' ');
  const up = (periodReturn ?? 0) >= 0;
  return `<svg class="spark ${up ? 'spark-up' : 'spark-down'}" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true"><polyline points="${pts}" fill="none" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
};
let ACTIVE_INDEX = null;
let INDEX_RANGE = '3M';
const INDEX_RANGES = { '1M': 22, '3M': 63, '6M': 126, '1Y': 252 };
const sliceIndexRange = (history, range) => (history || []).slice(-(INDEX_RANGES[range] || INDEX_RANGES['3M']));
const ixFresh = (x) => {
  const cls = x.freshnessStatus === 'CURRENT' ? 'current' : x.freshnessStatus === 'DELAYED' ? 'delayed' : 'stale';
  return `<span class="ix-fresh ${cls}"><i></i>${x.freshnessLabelKo || '상태 미상'} · ${x.asOf || '—'}</span>`;
};
const ixTile = (x) => {
  const d1 = x.chg1dPct; const m3 = x.chg3mPct;
  const d1dir = d1 == null ? '' : d1 >= 0 ? 'pos' : 'neg'; const m3dir = m3 == null ? '' : m3 >= 0 ? 'pos' : 'neg';
  return `<button type="button" class="ix" data-index-symbol="${x.symbol}" aria-label="${x.name} 상세 차트 열기" title="${x.symbol} · ${x.asOf ?? ''} · ${x.source ?? ''}">
    <div class="ix-h"><span class="ix-name">${x.name}</span><span class="ix-reg">${x.region}</span></div>
    <div class="ix-value-label">현재 지수값</div><div class="ix-quote"><span class="ix-last">${nfmt(x.last, x.digits ?? 2)}</span></div>
    <div class="ix-period-row"><span>1일 등락</span><b class="ix-chg ${d1dir}">${trendCue(d1)} ${chg(d1)}</b></div>
    <div class="ix-spark-head"><span>3M · 최근 3개월 추이</span><b class="${m3dir}">${trendCue(m3)} ${chg(m3, 1)}</b></div>${sparkSvg(x.spark, m3)}
    <div class="ix-spark-dates"><span>${x.sparkStartDate || '—'}</span><span>${x.sparkEndDate || x.asOf || '—'}</span></div>
    ${ixFresh(x)}<span class="ix-open">기간별 상세 보기 →</span></button>`;
};
const renderIndices = (d) => {
  const list = d.indices || [];
  if (!list.length) { $('#indexTape').innerHTML = ''; $('#tapeMeta').textContent = ''; return; }
  $('#indexTape').innerHTML = list.map(ixTile).join('');
  const h = d.marketDataHealth || {};
  const status = h.status === 'CURRENT' ? '전체 최신' : h.status === 'DELAYED' ? '일부 지연' : '확인 필요';
  $('#tapeMeta').textContent = `${status} · 최신 ${h.current ?? '—'}/${h.fetched ?? list.length} · 카드 3M, 상세 기본 3M`;
};
const indexDialogMarkup = (x) => {
  const points = sliceIndexRange(x.history, INDEX_RANGE);
  const first = points[0]?.value, last = points[points.length - 1]?.value;
  const rangeChange = first != null && last != null && Number(first) !== 0 ? (Number(last) / Number(first) - 1) * 100 : null;
  const startDate = points[0]?.date || '—'; const endDate = points[points.length - 1]?.date || '—';
  const rangeButtons = Object.keys(INDEX_RANGES).map((r) => `<button type="button" data-index-range="${r}" class="${INDEX_RANGE === r ? 'active' : ''}">${r}</button>`).join('');
  const sourceList = (x.sourcesChecked || [x.source]).filter(Boolean).join(' · ');
  return `<div class="ix-dialog-head"><div><span class="overline">${x.region} · ${x.symbol}</span><h2>${x.name} · ${INDEX_RANGE} 추이</h2><p>${INDEX_GUIDE[x.symbol] || '시장 수준과 추세를 보여주는 주요 지표입니다.'}</p></div><div class="ix-dialog-quote"><b>${nfmt(x.last, x.digits ?? 2)}</b><span class="${(rangeChange ?? 0) >= 0 ? 'pos' : 'neg'}">${trendCue(rangeChange)} ${INDEX_RANGE} ${chg(rangeChange, 1)}</span><small>${startDate} ~ ${endDate}</small></div></div>
    <div class="ix-range" aria-label="차트 기간">${rangeButtons}</div>
    <div class="ix-big-chart">${trendSvg([{ label: x.name, points }], [], { width: 900, height: 300, aria: `${x.name} ${INDEX_RANGE} 가격 추이` })}</div>
    <div class="ix-kpis"><div><span>선택 기간</span><b>${INDEX_RANGE}</b></div><div><span>기간 수익률</span><b class="${(rangeChange ?? 0) >= 0 ? 'pos' : 'neg'}">${trendCue(rangeChange)} ${chg(rangeChange)}</b></div><div><span>시작일</span><b>${startDate}</b></div><div><span>종료일</span><b>${endDate}</b></div><div><span>1일 등락</span><b class="${(x.chg1dPct ?? 0) >= 0 ? 'pos' : 'neg'}">${trendCue(x.chg1dPct)} ${chg(x.chg1dPct)}</b></div></div>
    <div class="ix-data-note">${ixFresh(x)}<span>현재 소스 <b>${x.source || '—'}</b></span><span>교차 확인 <b>${sourceList || '—'}</b></span><span>영업일 지연 <b>${x.freshnessBdays ?? '—'}일</b></span></div>`;
};
const showIndexDialog = (symbol) => {
  const x = (DATA.indices || []).find((row) => row.symbol === symbol);
  const dialog = $('#indexDialog'); const body = $('#indexDialogBody');
  if (!x || !dialog || !body) return;
  ACTIVE_INDEX = x; INDEX_RANGE = '3M';
  body.innerHTML = indexDialogMarkup(x);
  if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '');
};
const setIndexRange = (range) => {
  if (!ACTIVE_INDEX || !INDEX_RANGES[range]) return;
  INDEX_RANGE = range;
  const body = $('#indexDialogBody');
  if (body) body.innerHTML = indexDialogMarkup(ACTIVE_INDEX);
};

// --- direction compass ---
const dirSignal = (s) => `<div class="dsig"><div class="dsig-top"><span class="dsig-name">${s.name}</span><span class="reg ${s.cls}">${s.state}</span></div><div class="dsig-detail">${s.detail || ''}</div></div>`;
const dmRow = (r, winner) => { const cell = (v) => `<span class="${(v ?? 0) >= 0 ? 'pos' : 'neg'}">${chg(v, 1)}</span>`; return `<div class="dm-row ${r.ticker === winner ? 'dm-win' : ''}"><span class="dm-name">${r.ticker === winner ? '★ ' : ''}${r.name} <span class="tk">${r.ticker}</span></span><span>${cell(r.ret3mPct)}</span><span>${cell(r.ret6mPct)}</span><span>${cell(r.ret12mPct)}</span></div>`; };
const renderDirection = (dir) => {
  const sec = $('#direction'); if (!dir) { sec.hidden = true; return; }
  sec.hidden = false;
  $('#dirMeta').textContent = '듀얼 모멘텀 변형 · 변동성 · 추세 · 심리 합성 (참고)';
  const vt = dir.volTarget;
  $('#dirVerdict').innerHTML = `<div class="overline">모델 위험예산 방향</div><div class="dir-stance-row"><span class="dir-stance">${dir.stance}</span><span class="posture-score reg ${dir.stanceCls}">${dir.score}</span></div><div class="gauge"><i class="${dir.stanceCls}" style="width:${dir.score}%"></i></div><p class="dir-read">${dir.headline || ''}</p><div class="alloc"><div class="alloc-bar"><i class="eq" style="width:${dir.equityPct}%"></i><i class="cash" style="width:${dir.cashPct}%"></i></div><div class="alloc-legend"><span><i class="dot dot-eq"></i>주식 ${dir.equityPct}%</span><span><i class="dot dot-cash"></i>현금·방어 ${dir.cashPct}%</span></div></div>`;
  $('#dirSignals').innerHTML = (dir.signals || []).map(dirSignal).join('');
  const dm = dir.dualMomentum; const box = document.querySelector('.dm-box');
  if (!dm || !dm.rows || !dm.rows.length) { if (box) box.hidden = true; }
  else { if (box) box.hidden = false; $('#dualMomTable').innerHTML = `<div class="dm-row dm-h2"><span>자산</span><span>3M</span><span>6M</span><span>12M</span></div>` + dm.rows.map((r) => dmRow(r, dm.winner)).join(''); }
};

// --- rotation ---
const QUAD = { '주도': { cls: 'q-lead', color: 'var(--green)' }, '약화': { cls: 'q-weak', color: 'var(--gold)' }, '개선': { cls: 'q-impr', color: 'var(--accent)' }, '부진': { cls: 'q-lag', color: 'var(--red)' } };
const rrgSvg = (sectors) => {
  const W = 400, H = 300, pad = 10, cx = W / 2, cy = H / 2;
  const maxX = Math.max(2, ...sectors.map((s) => Math.abs(s.rsRatio))) * 1.25, maxY = Math.max(2, ...sectors.map((s) => Math.abs(s.rsMom))) * 1.25;
  const X = (v) => cx + (v / maxX) * (W / 2 - pad), Y = (v) => cy - (v / maxY) * (H / 2 - pad);
  const dots = sectors.map((s) => { const x = X(s.rsRatio), y = Y(s.rsMom), c = (QUAD[s.quadrant] || {}).color || 'var(--muted)'; const anchor = x > W - 60 ? 'end' : 'start'; return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="${c}" fill-opacity="0.9"><title>${s.name} · ${s.quadrant}</title></circle><text x="${(x + (anchor === 'end' ? -7 : 7)).toFixed(1)}" y="${(y + 3.5).toFixed(1)}" text-anchor="${anchor}" class="rrg-lb">${s.name}</text>`; }).join('');
  return `<svg viewBox="0 0 ${W} ${H}" class="rrg"><rect x="${cx}" y="0" width="${cx}" height="${cy}" class="rrg-q rrg-q-lead"/><rect x="${cx}" y="${cy}" width="${cx}" height="${cy}" class="rrg-q rrg-q-weak"/><rect x="0" y="0" width="${cx}" height="${cy}" class="rrg-q rrg-q-impr"/><rect x="0" y="${cy}" width="${cx}" height="${cy}" class="rrg-q rrg-q-lag"/><line x1="0" y1="${cy}" x2="${W}" y2="${cy}" class="rrg-ax"/><line x1="${cx}" y1="0" x2="${cx}" y2="${H}" class="rrg-ax"/>${dots}</svg>`;
};
const rrgChips = (sectors) => sectors.map((s) => `<span class="rchip ${(QUAD[s.quadrant] || {}).cls || ''}">${s.name} <b>${s.quadrant}</b> <em>${chg(s.ret3mPct, 1)}</em></span>`).join('');
const renderRegionRrg = (el, region) => { const host = $(el); if (!region || !region.sectors || !region.sectors.length) { host.innerHTML = '<div class="none">데이터 없음</div>'; return; } host.innerHTML = rrgSvg(region.sectors) + `<div class="rrg-chips">${rrgChips(region.sectors)}</div>`; };
const factorRow = (f) => { const v = f.ex3mPct ?? 0, w = Math.min(50, Math.abs(v) * 6); return `<div class="frow"><span class="f-name">${f.name} <span class="tk">${f.ticker}</span></span><span class="f-bar"><i class="${v >= 0 ? 'fpos' : 'fneg'}" style="${v >= 0 ? 'left:50%' : 'right:50%'};width:${w}%"></i></span><span class="f-nums">3M <b class="${v >= 0 ? 'pos' : 'neg'}">${chg(f.ex3mPct, 1)}</b></span></div>`; };
const renderRotation = (rot) => {
  const sec = $('#rotation'); if (!rot || (!rot.US && !rot.KR && !(rot.factors || []).length)) { sec.hidden = true; return; }
  sec.hidden = false; $('#rotMeta').textContent = `${rot.asOf ? '기준 ' + rot.asOf : ''}`;
  renderRegionRrg('#rrgUS', rot.US); renderRegionRrg('#rrgKR', rot.KR);
  const fp = $('#factorPanel');
  if ((rot.factors || []).length) { fp.hidden = false; $('#factorBars').innerHTML = rot.factors.map(factorRow).join(''); } else fp.hidden = true;
};

// --- flows ---
const flowRow = (f) => `<div class="flow"><span class="flow-tk tklink" data-tk="${f.ticker}">${tkName(f.ticker)}</span><span class="reg ${regCls(f.regime)}">${regKo(f.regime)}</span><span class="flow-surge">거래량 <b>×${fmt(f.volSurge)}</b></span><span class="flow-mom">모멘텀 <b>${sp(f.mom63)}</b></span></div>`;
const renderFlows = (d) => { const fl = d.flows || { KR: [], US: [] }; const fill = (el, arr) => $(el).innerHTML = (arr && arr.length) ? arr.map(flowRow).join('') : '<div class="none">두드러진 자금 유입 없음</div>'; fill('#flowsKR', fl.KR); fill('#flowsUS', fl.US); };

// --- macro / sentiment display panels ---
const region = (title, kpis, badge) => `<div class="region"><div class="region-h"><h4>${title}</h4>${badge || ''}</div><div class="kpi">${kpis}</div></div>`;
const kpiItems = (arr) => (arr || []).map(([l, v, n]) => `<div><span>${l}</span><b>${v}</b><em>${n ?? ''}</em></div>`).join('');
const renderMacro = (m) => {
  if (!m || !m.available) { $('#macroPanel').innerHTML = `<div class="none">${m?.note ?? '매크로 비활성'}</div>`; return; }
  $('#macroPanel').innerHTML = region('국외 (US)', kpiItems(m.US?.indicators)) + region('국내 (KR)', kpiItems(m.KR?.indicators));
};
const sentBadge = (r) => `<span class="reg ${regBadgeCls(r.score)}">${r.fearGreed || r.label} ${r.score}</span>`;
const renderSentiment = (s) => {
  if (!s) { $('#sentimentPanel').innerHTML = '<div class="none">데이터 없음</div>'; return; }
  const one = (title, r) => r ? region(title, kpiItems(r.components), sentBadge(r)) : region(title, '', '');
  $('#sentimentPanel').innerHTML = one('국외 (US)', s.US) + one('국내 (KR)', s.KR);
};

// --- master render ---
const render = (d) => {
  DATA = d; NAMES = d.names || {};
  $('#portfolioName').textContent = d.portfolioName || 'Investment Research';
  const p = d.provenance || {};
  const dataMode = d.dataMode || p.dataMode || (d.seed ? 'seed' : 'live');
  $('#dataStatus').textContent = `· ${modeLabel(dataMode)}`;
  const m = d.meta || {};
  $('#dataMeta').textContent = m.latestDataDate ? `시장 ${m.latestDataDate}` : '';
  if (d.generatedAt) $('#dataGenerated').textContent = '생성 ' + new Date(d.generatedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) + ' KST';
  $('#overviewAsOf').textContent = `시장 기준 ${p.marketAsOf || m.latestDataDate || '—'}`;
  $('#globalDisclaimer').textContent = COPY.disclaimer;
  const sb = $('#staleBanner');
  if (d.recommendationsBlocked || d.stale || d.seed || (d.dataMode && d.dataMode !== 'live')) {
    sb.hidden = false; sb.classList.add('warn');
    sb.innerHTML = `<b>■ ${d.recommendationsBlocked ? '안전 차단' : '데이터 확인 필요'}</b><span>${d.recommendationsBlocked ? '행동성 판단 숨김' : `${modeLabel(dataMode)}입니다.`}${m.latestDataDate ? ' · 기준 ' + m.latestDataDate : ''}</span>`;
  } else { sb.hidden = true; sb.classList.remove('warn'); }
  renderStatus(d);
  renderOverview(d);
  renderSelection(d);
  renderMethodStatus(d);
  renderIndices(d);
  renderRegime(d.macroRegime);
  renderConsensus(d.expertConsensus);
  renderNationalPension(d.nationalPensionService);
  renderInstitutional13F(d.institutionalHoldings13F);
  renderLongTerm(d);
  renderModelPortfolio(d);
  renderRadar(d);
  renderEntry(d);
  renderConcentration(d);
  renderValidationLab(d);
  renderPaper(d);
  renderIdeas(d);
  renderDirection(d.direction);
  renderRotation(d.rotation);
  renderFlows(d);
  renderMacro(d.macro);
  renderSentiment(d.sentiment);
};

const loadData = async (force = false) => {
  const button = $('#refreshData');
  if (button) { button.disabled = true; button.textContent = '확인 중…'; }
  try {
    const url = `data/site-data.json${force ? `?t=${Date.now()}` : ''}`;
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    render(await r.json());
    if (button) button.textContent = '최신 데이터 확인';
  } catch (e) {
    $('#dataStatus').textContent = 'data error: ' + e.message;
    if (button) button.textContent = '다시 확인';
  } finally {
    if (button) button.disabled = false;
  }
};
const filterScreen = () => {
  const q = ($('#screenSearch')?.value || '').trim().toLowerCase();
  const rows = document.querySelectorAll('#screenTable .srow:not(.sh)'); let shown = 0;
  rows.forEach((r) => { const hit = !q || (r.dataset.key || '').includes(q); r.style.display = hit ? '' : 'none'; if (hit) shown++; });
  const empty = $('#screenEmpty'); if (empty) empty.hidden = shown !== 0;
};
$('#screenSearch')?.addEventListener('input', filterScreen);
$('#refreshData')?.addEventListener('click', () => loadData(true));
$('#indexDialogClose')?.addEventListener('click', () => $('#indexDialog')?.close());
$('#indexDialog')?.addEventListener('click', (e) => { if (e.target.id === 'indexDialog') e.target.close(); });
$('#macroDialogClose')?.addEventListener('click', () => $('#macroDialog')?.close());
$('#macroDialog')?.addEventListener('click', (e) => { if (e.target.id === 'macroDialog') e.target.close(); });
document.querySelectorAll('.nav a[href^="#"]').forEach((a) => a.addEventListener('click', (e) => {
  const t = document.querySelector(a.getAttribute('href')); if (!t) return;
  e.preventDefault();
  if (t.tagName === 'DETAILS') t.open = true;
  t.scrollIntoView({ behavior: 'smooth', block: 'start' });
}));
loadRules(); loadData();
window.setInterval(() => loadData(false), 15 * 60 * 1000);
