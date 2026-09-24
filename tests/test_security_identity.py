"""CUSIP/issuer-name identity resolution: what each confidence level means
and, just as importantly, what it never claims.
"""
from __future__ import annotations

from pipeline import security_identity as ID


# --------------------------------------------------------------------------- #
# Name normalization — a deterministic key, never a spell-checker
# --------------------------------------------------------------------------- #
def test_common_suffixes_are_stripped_repeatedly():
    assert ID.normalize_issuer_name("ALPHA HOLDINGS INC") == "ALPHA"
    assert ID.normalize_issuer_name("Beta Corp") == "BETA"
    assert ID.normalize_issuer_name("Gamma Co Ltd") == "GAMMA"


def test_punctuation_and_case_are_normalized_but_content_is_not_altered():
    assert ID.normalize_issuer_name("O'Reilly Automotive, Inc.") == "O REILLY AUTOMOTIVE"


def test_class_designators_are_stripped():
    assert ID.normalize_issuer_name("XYZ INC CL A") == "XYZ"


def test_two_genuinely_different_names_never_collapse():
    assert ID.normalize_issuer_name("Alpha Inc") != ID.normalize_issuer_name("Alphabet Inc")


# --------------------------------------------------------------------------- #
# Resolution tiers
# --------------------------------------------------------------------------- #
def test_exact_cusip_match_from_a_supplied_map():
    match = ID.resolve_one("000000001", "ALPHA INC",
                           cusip_map={"000000001": "ALPH"})
    assert match.confidence == ID.EXACT_CUSIP_MATCH
    assert match.ticker == "ALPH"


def test_exact_cusip_match_carries_a_point_in_time_risk_unless_the_map_declares_itself_pit():
    unlabelled = ID.resolve_one("000000001", "ALPHA INC", cusip_map={"000000001": "ALPH"})
    assert unlabelled.pointInTimeRisk == ID.RISK_MAP_NOT_KNOWN_PIT

    labelled = ID.resolve_one("000000001", "ALPHA INC", cusip_map={"000000001": "ALPH"},
                              cusip_map_is_point_in_time=True)
    assert labelled.pointInTimeRisk == ID.RISK_NONE


def test_name_fallback_only_fires_when_the_cusip_does_not_match():
    index = {"ALPHA": "ALPH"}
    match = ID.resolve_one("999999999", "Alpha Inc", cusip_map={}, name_index=index)
    assert match.confidence == ID.NAME_FUZZY_MATCH
    assert match.ticker == "ALPH"
    assert match.pointInTimeRisk == ID.RISK_NAME_INDEX_IS_CURRENT


def test_name_fallback_never_outranks_an_exact_cusip_hit():
    index = {"ALPHA": "WRONG"}
    match = ID.resolve_one("000000001", "Alpha Inc",
                           cusip_map={"000000001": "ALPH"}, name_index=index)
    assert match.confidence == ID.EXACT_CUSIP_MATCH and match.ticker == "ALPH"


def test_no_match_anywhere_is_unresolved_never_guessed():
    match = ID.resolve_one("555555555", "Totally Unknown Corp", cusip_map={}, name_index={})
    assert match.confidence == ID.UNRESOLVED
    assert match.ticker is None


# --------------------------------------------------------------------------- #
# build_name_index — ambiguity is dropped, never guessed
# --------------------------------------------------------------------------- #
def test_a_name_shared_by_two_ciks_is_dropped_from_the_index():
    payload = {
        "0": {"cik_str": 1, "ticker": "AAA", "title": "SAME NAME INC"},
        "1": {"cik_str": 2, "ticker": "BBB", "title": "SAME NAME INC"},
        "2": {"cik_str": 3, "ticker": "CCC", "title": "UNIQUE CORP"},
    }
    index = ID.build_name_index(payload)
    assert "SAME NAME" not in index
    assert index["UNIQUE"] == "CCC"


# --------------------------------------------------------------------------- #
# resolve_rows — unresolved rows are listed, never silently dropped
# --------------------------------------------------------------------------- #
def test_unresolved_rows_are_both_kept_and_queued():
    rows = [
        {"CUSIP": "000000001", "issuer": "ALPHA INC", "managerCIK": "1", "reportDate": "2020-01-01"},
        {"CUSIP": "999999999", "issuer": "MYSTERY CORP", "managerCIK": "1", "reportDate": "2020-01-01"},
    ]
    resolved, unresolved = ID.resolve_rows(rows, cusip_map={"000000001": "ALPH"})
    assert len(resolved) == 2, "every row is returned, resolved or not"
    assert resolved[1]["identityConfidence"] == ID.UNRESOLVED
    assert len(unresolved) == 1
    assert unresolved[0]["cusip"] == "999999999"
