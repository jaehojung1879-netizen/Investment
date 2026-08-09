"""Static DOM/rendering contracts for the dependency-free dashboard."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "styles.css").read_text(encoding="utf-8")


def test_market_card_and_dialog_use_explicit_three_month_contract():
    assert "chg3mPct" in APP
    assert "3M · 최근 3개월 추이" in APP
    assert "let INDEX_RANGE = '3M'" in APP
    assert "ACTIVE_INDEX = x; INDEX_RANGE = '3M'" in APP
    assert "'3M': 63" in APP
    assert "sliceIndexRange(x.history, INDEX_RANGE)" in APP
    assert "기간 수익률" in APP and "시작일" in APP and "종료일" in APP


def test_period_button_rerenders_points_and_return_together():
    assert "INDEX_RANGE = range" in APP
    assert "body.innerHTML = indexDialogMarkup(ACTIVE_INDEX)" in APP
    assert "const points = sliceIndexRange(x.history, INDEX_RANGE)" in APP
    assert "const rangeChange =" in APP


def test_technical_statuses_are_mapped_to_korean_user_labels():
    for label in ("검증 데이터 축적 중", "실험적 모델 결과", "Paper 운용 중", "검증 완료", "데이터 부족", "안전 차단"):
        assert label in APP
    assert "statusLabel(status)" in APP
    assert "기술 상태" in APP


def test_fallback_does_not_render_kelly_weights_as_applied():
    assert "const applied = mp.kellyApplied === true" in APP
    assert "applied ? fmt(p.constrainedKellyWeightPct" in APP
    assert "Kelly 미적용" in APP
    assert "COPY.fallback" in APP


def test_decision_first_structure_and_single_global_disclaimer():
    # The page opens on the answer: verdict, then the holdings themselves.
    for element_id in ("decisionHero", "holdingsPanel", "selectionPanel",
                       "methodStatusPanel", "statusPanel", "modelPortfolioPanel"):
        assert f'id="{element_id}"' in HTML
    assert HTML.index('id="decisionHero"') < HTML.index('id="modelPortfolioPanel"')
    assert HTML.index('id="holdingsPanel"') < HTML.index('id="ltKR"')
    assert HTML.count('id="globalDisclaimer"') == 1
    assert APP.count("투자 조언이나 개인화 추천") == 1
    assert "개인화 투자 권고" not in APP


def test_secondary_material_lives_behind_uniform_folds():
    # Everything that is not the decision is one collapsed row, not a section.
    assert HTML.count('class="fold"') >= 8
    assert 'class="fold-grid"' in HTML
    assert ".fold > summary" in CSS
    # The old always-expanded section chrome is gone.
    assert "secondary-summary" not in HTML and "secondary-summary" not in CSS
    assert 'class="section"' not in HTML


def test_invalidation_is_rendered_per_name_from_pipeline_fields():
    # No hardcoded sentence may stand in for a name's own invalidation levels.
    assert "알파가 편출 버퍼 밖으로 밀리거나" not in APP
    assert "invalidationLine(p.invalidation" in APP
    assert "x.currentKo} → ${x.triggerKo}" in APP
    assert "BREACHED" in APP


def test_selection_funnel_and_method_status_are_rendered():
    assert "renderSelection" in APP and "renderMethodStatus" in APP
    assert "SELECT_EXCLUSION_KO" in APP
    assert "scoreFormulaKo" in APP and "notAForecastKo" in APP
    assert "방법론 적용 현황" in APP
    assert "convictionScore" in APP and "effectiveNames" in APP
    assert ".funnel-step" in CSS and ".ms-row" in CSS


def test_mobile_portfolio_is_card_layout_without_wide_minimum():
    assert ".mp-position" in CSS
    assert ".mp-row > span::before" in CSS
    assert "grid-template-columns: repeat(2, minmax(0,1fr))" in CSS
    assert "min-width: 1040px" not in CSS
