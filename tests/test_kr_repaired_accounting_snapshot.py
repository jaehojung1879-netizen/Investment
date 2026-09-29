"""Snapshot freeze and semantic-contract enforcement. Synthetic data plus, where the
pinned git object is available, the real frozen shards. No outcome data is read."""
import builtins
import gzip
import json
import os
from pathlib import Path
import random
import subprocess

import pytest

from pipeline import alpha_opportunity_features as AOF
from pipeline import dart_canonical_accounts as CA
from pipeline import dart_derive as DD
from pipeline import dart_fundamentals as DF
from pipeline import historical_store as HS
from pipeline import kr_repaired_accounting_snapshot as K
from scripts import merge_kr_candidate_snapshot as MERGE

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "research_specs/kr-repaired-accounting-snapshot-v1.json").read_text(encoding="utf-8"))


def rec(ticker="000001.KS", year=2016, code="11013", available="2016-05-16", source="DART:fnlttSinglAcntAll:CFS",
        accounts=None, receipts=None):
    return {"id": f"{ticker}:{year}:{code}", "ticker": ticker, "stockCode": ticker[:6], "corpCode": "00000001",
            "fiscalYear": year, "reportCode": code, "availableFrom": available,
            "receiptNos": receipts or [available.replace("-", "") + "000001"], "fsDiv": "CFS", "source": source,
            "accounts": accounts if accounts is not None else {"자산총계": {"amounts": {"thstrm_amount": 10.0}, "statement": "BS"}}}


def write(dirpath, name, rows):
    HS.write_shard(Path(dirpath) / name, rows)


# --- frozen identity ----------------------------------------------------------------
def test_frozen_constants_agree_with_the_manifest_and_the_validated_candidate():
    assert SPEC["frozenSnapshotSha256"] == SPEC["snapshotContentSha256"] == K.FROZEN_CONTENT_SHA256
    assert SPEC["candidateIdentitySha256"] == K.CANDIDATE_SHA256
    v1 = json.loads((ROOT / "research_specs/kr-original-xbrl-value-validation-v1.json").read_text(encoding="utf-8"))
    assert v1["candidate"]["sha256"] == K.CANDIDATE_SHA256 and v1["candidate"]["sourceCommit"] == K.SOURCE_COMMIT
    assert {n: s["gitBlobSha1"] for n, s in SPEC["shards"].items()} == v1["candidate"]["gitBlobSha1"]
    assert K.candidate_identity({n: s["gitBlobSha1"] for n, s in SPEC["shards"].items()}) == K.CANDIDATE_SHA256
    assert sum(s["records"] for s in SPEC["shards"].values()) == SPEC["recordCount"] == 9351
    assert SPEC["coverage"]["distinctIds"] == SPEC["coverage"]["records"] == 9351


def test_pinned_code_is_byte_unchanged():
    for name, blob in SPEC["code"].items():
        assert K.git_blob_sha1((ROOT / name).read_bytes()) == blob, name + " changed: a new snapshot version is required"


def test_regeneration_and_the_real_frozen_shards_match_the_manifest(tmp_path):
    """Runs against the real pinned git object; only skipped when it is absent locally."""
    have = subprocess.run(["git", "cat-file", "-e", K.SOURCE_COMMIT], cwd=ROOT, capture_output=True).returncode == 0
    if not have:
        if os.environ.get("CI"):
            pytest.fail("pinned source commit is not fetched in CI")
        pytest.skip("pinned source commit not present locally")
    dirs = K.materialize_from_git(ROOT, tmp_path)
    manifest = K.build_manifest(dirs["merged"], dirs["canonical"], dirs["xbrl"], ROOT)
    for key in ("candidateIdentitySha256", "snapshotContentSha256", "recordCount", "shards", "inputs", "code",
                "coverage", "coverageByShard"):
        assert json.loads(json.dumps(manifest[key])) == SPEC[key], key
    regen = K.regenerate_and_compare(dirs["canonical"], dirs["xbrl"], dirs["merged"], ROOT)
    assert regen["byteIdentical"] and regen["shardSetEqual"] and regen["mergeReportEqual"]
    assert regen["contentSha256"] == K.FROZEN_CONTENT_SHA256


# --- determinism ----------------------------------------------------------------------
def test_content_hash_is_order_and_compression_independent_and_value_sensitive():
    rows = [rec("000001.KS"), rec("000002.KS"), rec("000003.KS", year=2015, code="11011", available="2016-03-20")]
    shuffled = list(rows)
    random.Random(7).shuffle(shuffled)
    base = K.content_sha256({"dart-2016.jsonl.gz": rows})
    assert base == K.content_sha256({"dart-2016.jsonl.gz": shuffled})
    changed = json.loads(json.dumps(rows))
    changed[0]["accounts"]["자산총계"]["amounts"]["thstrm_amount"] = 10.5
    assert K.content_sha256({"dart-2016.jsonl.gz": changed}) != base
    assert K.content_sha256({"dart-2017.jsonl.gz": rows}) != base


def test_regeneration_from_sources_is_byte_deterministic_and_collisions_raise(tmp_path):
    canonical, xbrl, out1, out2 = (tmp_path / n for n in ("c", "x", "o1", "o2"))
    write(canonical, "dart-2016.jsonl.gz", [rec("000001.KS"), rec("000002.KS")])
    write(canonical, "dart-2015.jsonl.gz", [rec("000001.KS", 2015, "11011", "2016-03-21")])
    write(xbrl, "dart-xbrl-2015.jsonl.gz",
          [rec("000001.KS", 2015, "11013", "2015-05-15", "DART:fnlttXbrl.xml:ORIGINAL")])
    MERGE.merge(out1, canonical, xbrl)
    MERGE.merge(out2, canonical, xbrl)
    for p in sorted(out1.iterdir()):
        assert p.read_bytes() == (out2 / p.name).read_bytes()
    manifest = K.build_manifest(out1, canonical, xbrl, ROOT)
    assert manifest["recordCount"] == 4 and manifest["snapshotContentSha256"] == K.build_manifest(
        out2, canonical, xbrl, ROOT)["snapshotContentSha256"]
    regen = K.regenerate_and_compare(canonical, xbrl, out1, ROOT)
    assert regen["byteIdentical"] and regen["contentSha256"] == manifest["snapshotContentSha256"]
    write(xbrl, "dart-xbrl-2015.jsonl.gz", [rec("000001.KS", 2015, "11011", "2016-03-21", "DART:fnlttXbrl.xml:ORIGINAL")])
    with pytest.raises(ValueError, match="CANDIDATE_SOURCE_COLLISION"):
        MERGE.merge(tmp_path / "o3", canonical, xbrl)


def test_write_shard_keeps_the_first_write_of_an_id(tmp_path):
    first, second = rec(), rec()
    second["accounts"] = {"자산총계": {"amounts": {"thstrm_amount": 99.0}, "statement": "BS"}}
    HS.write_shard(tmp_path / "s.jsonl.gz", [first, second])
    assert K.read_shard(tmp_path / "s.jsonl.gz")[0]["accounts"]["자산총계"]["amounts"]["thstrm_amount"] == 10.0


# --- semantic contract, enforced through the real code ----------------------------------
def test_point_in_time_visibility_is_strictly_earlier_and_receipt_consistent():
    ok = rec(available="2016-05-16")
    later = rec("000002.KS", available="2016-05-17")
    mismatch = rec("000003.KS", available="2016-05-16", receipts=["20160518000001"])
    undated = rec("000004.KS", available="")
    visible = AOF.visible_filings([ok, later, mismatch, undated], "2016-05-17", "KR")
    assert [r["ticker"] for r in visible] == ["000001.KS"]
    assert AOF.visible_filings([ok], "2016-05-16", "KR") == []  # same-day is not visible


def test_receipt_date_comes_from_the_receipt_number_only():
    assert DF.receipt_date("20160516000107") == "2016-05-16"
    assert DF.receipt_date("") is None and DF.receipt_date("2016") is None and DF.receipt_date("20161340000001") is None


def test_period_semantics_flow_columns_and_ttm_rollforward():
    def filing(year, code, statement, amounts):
        return {"fiscalYear": year, "reportCode": code, "accounts": {"당기순이익": {"amounts": amounts, "statement": statement}}}
    q3 = filing(2016, "11014", "CIS", {"thstrm_amount": 3.0, "thstrm_add_amount": 9.0})
    assert DD.cumulative_amount(q3, "당기순이익") == 9.0  # year-to-date, not the quarter
    cf = {"fiscalYear": 2016, "reportCode": "11014", "accounts": {"영업활동현금흐름": {"amounts": {"thstrm_amount": 7.0}, "statement": "CF"}}}
    assert DD.cumulative_amount(cf, "영업활동현금흐름") == 7.0
    annual = filing(2015, "11011", "CIS", {"thstrm_amount": 12.0})
    prior_q3 = filing(2015, "11014", "CIS", {"thstrm_amount": 4.0, "thstrm_add_amount": 8.0})
    by_key = DD.index_filings([q3, annual, prior_q3])
    value, basis = DD.trailing_twelve_months(by_key, 2016, "11014", "당기순이익")
    assert (value, basis) == (12.0 - 8.0 + 9.0, DD.BASIS_ROLLFORWARD)
    assert DD.trailing_twelve_months(DD.index_filings([q3, annual]), 2016, "11014", "당기순이익") == (None, DD.BASIS_INCOMPLETE)
    bs = {"accounts": {"자산총계": {"amounts": {"thstrm_amount": 5.0}}}}
    assert DD.level_amount(bs, "자산총계") == 5.0 and DD.level_amount(bs, "부채총계") is None


def test_missing_accounts_are_none_never_zero():
    assert DD.level_amount({"accounts": {}}, "자산총계") is None
    assert DD.cumulative_amount({"reportCode": "11011", "accounts": {}}, "당기순이익") is None


def test_share_counts_carry_forward_only_from_earlier_filings():
    shares = {(2016, "11012"): 100.0, (2016, "11014"): 300.0}
    value, _ = DD.carried_shares(shares, 2016, "11013")
    assert value is None  # nothing earlier exists; the later 300.0/100.0 must not be used
    value, _ = DD.carried_shares(shares, 2016, "11012")
    assert value == 100.0


def test_four_family_meaning_is_the_ifrs_total_element_never_a_component_or_subtotal():
    rules = CA.ELEMENT_RULES
    contract = SPEC["semanticContract"]["families"]
    for family, account in K.FAMILY_ACCOUNTS.items():
        assert contract[family]["account"] == account
        element = contract[family]["ifrsElement"]
        assert {f"ifrs_{element}", f"ifrs-full_{element}"} == set(rules[account]["elementIds"])
    ids = {i for r in rules.values() for i in r["elementIds"]}
    assert not any("Attributable" in i or i.endswith("CashFlowsFromUsedInOperations") for i in ids)
    assert rules["당기순이익"]["elementStatements"] == ("IS", "CIS") and rules["자산총계"]["statements"] == ("BS",)
    assert rules["영업활동현금흐름"]["statements"] == ("CF",)


def test_component_rows_are_never_totals_and_disagreeing_candidates_are_ambiguous():
    rows = [{"sj_div": "BS", "account_nm": "자산총계", "account_detail": "-", "account_id": "ifrs-full_Assets", "thstrm_amount": "10"},
            {"sj_div": "BS", "account_nm": "자산총계", "account_detail": "segment A", "account_id": "ifrs-full_Assets", "thstrm_amount": "3"}]
    entry, how = CA.resolve_account(rows, "자산총계")
    assert entry["amounts"]["thstrm_amount"] == 10.0
    rows[1]["account_detail"] = "-"
    entry, how = CA.resolve_account(rows, "자산총계")
    assert entry is None and how["rule"] == CA.AMBIGUOUS


def test_contract_facts_recorded_in_the_manifest_match_the_measured_coverage():
    c, contract = SPEC["coverage"], SPEC["semanticContract"]
    assert c["recordsWithMultipleReceipts"] == 0 and c["recordsWithReceiptDateNotEqualToAvailableFrom"] == 2
    assert c["bySourceAndFsDiv"] == {"DART:CFS": 8479, "DART:OFS": 347, "DART:fnlttXbrl.xml:ORIGINAL": 525}
    assert SPEC["provenance"]["sourceComposition"] == {"kr-canonical-v2": 8826, "kr-xbrl-original": 525}
    assert contract["sourcePrecedence"]["rule"].startswith("The two sources are disjoint")


# --- no outcome data, no Alpha execution ---------------------------------------------------
def test_building_a_manifest_opens_no_outcome_or_alpha_path(tmp_path, monkeypatch):
    canonical, xbrl, out = (tmp_path / n for n in ("c", "x", "o"))
    write(canonical, "dart-2016.jsonl.gz", [rec()])
    write(xbrl, "dart-xbrl-2015.jsonl.gz", [rec("000009.KS", 2015, "11013", "2015-05-15", "DART:fnlttXbrl.xml:ORIGINAL")])
    MERGE.merge(out, canonical, xbrl)
    seen = []
    real_open, real_gzip = builtins.open, gzip.open

    def spy(path, *a, **k):
        seen.append(str(path))
        return real_open(path, *a, **k)

    def gzspy(path, *a, **k):
        seen.append(str(path))
        return real_gzip(path, *a, **k)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(gzip, "open", gzspy)
    K.build_manifest(out, canonical, xbrl, ROOT)
    forbidden = ("ledger/historical", "replay", "outcome", "docs/results/alpha", "alpha-opportunity")
    assert not [p for p in seen if any(f in p for f in forbidden)]


def test_snapshot_code_does_not_import_or_reference_alpha_or_outcome_code():
    for name in ("pipeline/kr_repaired_accounting_snapshot.py", "scripts/build_kr_repaired_accounting_snapshot_manifest.py"):
        code = (ROOT / name).read_text(encoding="utf-8")
        for forbidden in ("kelly_portfolio", "portfolio_validation", "replay_valuation", "historical_outcomes",
                          "alpha_opportunity_model", "run_alpha", "workflow_dispatch"):
            assert forbidden not in code, (name, forbidden)


def test_no_workflow_in_this_change_executes_alpha():
    for path in (ROOT / ".github/workflows").glob("*snapshot*"):
        text = path.read_text(encoding="utf-8")
        assert "alpha" not in text.lower(), path.name
