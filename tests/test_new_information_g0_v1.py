"""Synthetic-only tests. No external API, securities prices, or outcomes."""
from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import patch

import pytest

from research.new_information_g0_v1 import source_probe as g0


def row(receipt="20260501000001", name="주식등의대량보유상황보고서"):
    return {
        "rcept_no": receipt,
        "rcept_dt": receipt[:8],
        "corp_code": "00126380",
        "report_nm": name,
    }


def test_listing_keeps_corrections_and_dedups_receipts():
    a = row()
    b = row("20260502000002", "[기재정정] 주식등의대량보유상황보고서")
    filings = g0.parse_listing({"status": "000", "list": [a, b]})
    assert len(filings) == 2
    assert filings[1]["correction_flag"] is True
    summary = g0.summarize(filings + [filings[0]], truncated=True, detail="D001")
    assert summary["sampled_receipts"] == 2
    assert summary["sampled_firms"] == 1
    assert summary["correction_receipts"] == 1
    assert summary["event_count"] is None
    assert summary["purpose_change_count"] is None
    assert summary["pit_verified_events"] == 0
    assert summary["pages_not_exhausted"] is True


def test_no_data_is_not_an_error_but_bad_status_is():
    assert g0.parse_listing({"status": "013"}) == []
    with pytest.raises(ValueError):
        g0.parse_listing({"status": "020"})
    with pytest.raises(ValueError):
        g0.parse_listing({"status": "000", "list": [row("1")]})


def test_zip_heading_is_only_hint_never_signal():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w") as archive:
        archive.writestr("BODY.XML", "<DOC><TEXT>보유목적: 일반투자</TEXT></DOC>")
    proof = g0.scan_original_zip(buf.getvalue())
    assert proof["has_purpose_text_hint"] is True
    assert proof["confirmed_purpose_switch"] is None
    assert len(proof["sha256"]) == 64
    with pytest.raises(ValueError):
        g0.scan_original_zip(b"not a zip")


def test_live_is_small_and_outcome_blind():
    calls = []
    def fake_request(endpoint, params):
        assert "crtfc_key" in params
        calls.append(endpoint)
        if endpoint == "list.json":
            # The same synthetic filing appears in each bounded window.
            return json.dumps({"status": "000", "total_count": 1,
                               "list": [row()]}).encode()
        raise AssertionError("No docs requested")
    with patch.object(g0, "request_bytes", side_effect=fake_request):
        result = g0.live(key="a"*40, documents_per_detail=0)
    assert calls == ["list.json"]*8
    assert result["no_price_or_outcome_access"] is True
    assert result["results"]["insider"]["purpose_change_count"] is None
    assert result["results"]["ownership_purpose"]["sampled_receipts"] == 1


def test_offline_has_no_network_and_does_not_claim_population(tmp_path):
    fixture = tmp_path / "synthetic.json"
    fixture.write_text(json.dumps({"status": "000", "list": [row()]}))
    data = g0.offline(fixture)
    assert data["sampled_receipts"] == 1
    assert data["pages_not_exhausted"] is True
    with patch.object(g0, "request_bytes", side_effect=AssertionError):
        assert g0.main(["--offline-list", str(fixture),
                        "--output", str(tmp_path / "out.json")]) == 0
