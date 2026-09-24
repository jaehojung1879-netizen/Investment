from pipeline import dart_ownership_universe as DOU


def test_historical_union_includes_current_and_delisted_securities():
    memberships = {
        "005930.KS": {"region": "KR", "listed": "2013-01-02", "delisted": None},
        "000030.KS": {"region": "KR", "listed": "2014-12-01", "delisted": "2019-03-04"},
    }
    krx = [
        {"ticker": "005930.KS", "name": "삼성전자", "date": "2026-09-01"},
        {"ticker": "000030.KS", "name": "우리은행", "date": "2018-12-01"},
    ]
    dart = [
        {"corpCode": "001", "corpName": "삼성전자", "stockCode": "005930"},
        {"corpCode": "002", "corpName": "우리은행", "stockCode": ""},
    ]
    result = DOU.build_collection_universe(
        memberships=memberships, krx_rows=krx, current_tickers=["005930.KS"],
        dart_directory=dart)
    assert result["securityCount"] == 2
    assert result["issuerCount"] == 2
    assert result["currentUniverseIssuerCount"] == 1
    assert result["historicalOnlyIssuerCount"] == 1
    by_code = {row["corpCode"]: row for row in result["issuers"]}
    assert by_code["002"]["mappingProvenance"][0]["method"] == "DART_CORP_NAME_EXACT_UNIQUE"


def test_ambiguous_or_missing_identity_remains_explicitly_unresolved():
    memberships = {"123456.KS": {"region": "KR", "listed": "2015-01-01", "delisted": None}}
    krx = [{"ticker": "123456.KS", "name": "동명이인", "date": "2016-01-01"}]
    dart = [
        {"corpCode": "001", "corpName": "동명이인", "stockCode": ""},
        {"corpCode": "002", "corpName": "동명이인", "stockCode": ""},
    ]
    result = DOU.build_collection_universe(
        memberships=memberships, krx_rows=krx, current_tickers=[], dart_directory=dart)
    assert result["issuerCount"] == 0
    assert result["unresolvedIdentityCount"] == 1
    assert result["unresolved"][0]["mapping"]["reason"] == "AMBIGUOUS_CORP_NAME"


def test_ticker_at_uses_filing_availability_not_a_future_security_identity():
    securities = [
        {"ticker": "111111.KS", "listed": "2013-01-01", "delisted": "2020-01-01",
         "currentUniverse": False},
        {"ticker": "222222.KS", "listed": "2020-01-01", "delisted": None,
         "currentUniverse": True},
    ]
    assert DOU.ticker_at(securities, "2019-12-31") == "111111.KS"
    assert DOU.ticker_at(securities, "2020-01-02") == "222222.KS"
