"""Static DOM/rendering contracts for the dependency-free dashboard."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "styles.css").read_text(encoding="utf-8")


def test_market_card_and_dialog_use_explicit_three_month_contract():
    assert "chg3mPct" in APP
    assert "최근 3개월" in APP
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
    for label in ("기본 비중 제공 중", "성과 보정 시험 중", "성과 보정 반영", "위험 분산 비중", "안전 차단"):
        assert label in APP
    assert "statusLabel(status)" in APP
    assert "기술 상태" in APP


def test_fallback_does_not_render_kelly_weights_as_applied():
    assert "const applied = mp.kellyApplied === true" in APP
    assert "applied ? fmt(p.constrainedKellyWeightPct" in APP
    assert "보정 대기" in APP
    assert "COPY.fallback" in APP


def test_summary_first_structure_and_single_global_disclaimer():
    for element_id in ("statusPanel", "marketSummaryPanel", "researchSummaryPanel", "portfolioSummaryPanel"):
        assert f'id="{element_id}"' in HTML
    assert HTML.count('id="globalDisclaimer"') == 1
    assert APP.count("투자 조언이나 개인화 추천") == 1
    assert "개인화 투자 권고" not in APP


def test_decision_first_copy_and_candidates_are_not_collapsed():
    assert "지금 볼 비중과 투자 후보" in HTML
    assert 'class="decision-card"' in HTML
    assert "현재 모델 비중" in APP and "지금 분할 매수" in APP
    assert "전체 상세 후보 보기" not in HTML
    assert '<div class="cols2 research-columns">' in HTML
    assert "무효화 조건" not in APP
    assert "다시 확인할 때" in APP


def test_methodology_is_a_separate_page():
    method = (ROOT / "methodology.html").read_text(encoding="utf-8")
    method_js = (ROOT / "methodology.js").read_text(encoding="utf-8")
    assert 'href="methodology.html"' in HTML
    assert "업데이트 시간" in method and "성과 확인" in method
    assert "docs/investment-philosophy.md" in method_js


def test_market_dates_explain_exchange_day_and_korea_collection_time():
    assert "미국 거래일" in APP
    assert "한국시간" in APP and "수집" in APP
    assert "미국 종가는 한국시간 다음 날 오전 반영" in APP


def test_mobile_portfolio_is_card_layout_without_wide_minimum():
    assert ".mp-position" in CSS
    assert ".mp-row > span::before" in CSS
    assert "grid-template-columns: repeat(2, minmax(0,1fr))" in CSS
    assert "min-width: 1040px" not in CSS
