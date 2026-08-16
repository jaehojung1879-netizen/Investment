"""SEC 13F parser and quarter-over-quarter comparison contracts."""
import json

from pipeline import institutional_13f as F13


def _xml(rows):
    body = "".join(
        f"""<infoTable>
          <nameOfIssuer>{name}</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>{cusip}</cusip>
          <value>{value}</value><shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
          {f'<putCall>{put_call}</putCall>' if put_call else ''}
        </infoTable>"""
        for name, cusip, value, shares, put_call in rows
    )
    return f'<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">{body}</informationTable>'.encode()


def test_namespaced_information_table_is_parsed_without_guessing_tickers():
    rows = F13.parse_information_table(_xml([
        ("ALPHA INC", "000000001", 150000000, 1000, None),
        ("BETA INC", "000000002", 25000000, 200, "PUT"),
    ]))
    assert rows[0] == {
        "issuer": "ALPHA INC", "titleClass": "COM", "cusip": "000000001",
        "valueUsd": 150000000, "shares": 1000, "shareType": "SH", "putCall": None,
    }
    assert rows[1]["putCall"] == "PUT"


def test_numeric_sec_attachment_name_is_accepted_as_information_table():
    def fetch_json(_):
        return {"directory": {"item": [
            {"name": "primary_doc.xml", "type": "text.gif"},
            {"name": "56757.xml", "type": "text.gif"},
        ]}}

    filing = {"accessionNumber": "0001193125-26-352200"}
    assert F13._information_table_url("0001067983", filing, fetch_json).endswith("/56757.xml")


def test_manager_snapshot_compares_shares_and_carries_both_dates(monkeypatch):
    submissions = {
        "filings": {"recent": {
            "form": ["13F-HR", "13F-HR", "10-K"],
            "accessionNumber": ["0000000001-26-000002", "0000000001-26-000001", "x"],
            "filingDate": ["2026-08-14", "2026-05-15", "2026-03-01"],
            "reportDate": ["2026-06-30", "2026-03-31", "2025-12-31"],
            "primaryDocument": ["primary_doc.xml", "primary_doc.xml", "x"],
        }}
    }

    def fetch_json(url):
        if "submissions" in url:
            return submissions
        return {"directory": {"item": [{"name": "infotable.xml", "type": "INFORMATION TABLE"}]}}

    current = _xml([
        ("ALPHA INC", "000000001", 200000000, 2000, None),
        ("NEW INC", "000000003", 50000000, 500, None),
    ])
    previous = _xml([
        ("ALPHA INC", "000000001", 90000000, 1000, None),
        ("EXIT INC", "000000004", 40000000, 400, None),
    ])

    def fetch_bytes(url):
        return current if "000000000126000002" in url else previous

    monkeypatch.setattr(F13.time, "sleep", lambda _: None)
    got = F13._build_manager(
        {"id": "test", "name": "Test Manager", "managerKo": "테스트", "cik": "0000000001"},
        fetch_json=fetch_json, fetch_bytes=fetch_bytes,
    )
    assert got["reportDate"] == "2026-06-30"
    assert got["filingDate"] == "2026-08-14"
    assert got["previousReportDate"] == "2026-03-31"
    assert got["totalValueUsd"] == 250000000
    assert got["topHoldings"][0]["portfolioWeightPct"] == 80.0
    assert got["changes"]["increased"][0]["shareChangePct"] == 100.0
    assert got["changes"]["increased"][0]["cusip"] == "000000001"
    assert got["changes"]["new"][0]["issuer"] == "NEW INC"
    assert got["changes"]["exited"][0]["issuer"] == "EXIT INC"


def test_build_marks_an_older_last_available_filing_without_hiding_its_date(tmp_path, monkeypatch):
    registry = tmp_path / "managers.json"
    registry.write_text(json.dumps([{"id": "new"}, {"id": "old"}]), encoding="utf-8")

    def fake_manager(manager):
        report = "2026-06-30" if manager["id"] == "new" else "2025-09-30"
        return {**manager, "status": "AVAILABLE", "reportDate": report}

    monkeypatch.setattr(F13, "_build_manager", fake_manager)
    got = F13.build(registry)
    assert got["latestReportDate"] == "2026-06-30"
    assert got["laggedManagerCount"] == 1
    assert got["managers"][0]["reportRecency"] == "LATEST_TRACKED_QUARTER"
    assert got["managers"][1]["reportRecency"] == "OLDER_LAST_AVAILABLE"


def test_build_uses_dated_official_cache_without_calling_it_live(tmp_path, monkeypatch):
    registry = tmp_path / "managers.json"
    registry.write_text(json.dumps([{"id": "cached", "name": "Cached", "cik": "0000000001"}]), encoding="utf-8")
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({
        "fetchedAt": "2026-05-15T00:00:00+00:00",
        "managers": {"cached": {
            "id": "cached", "name": "Cached", "cik": "0000000001", "status": "AVAILABLE",
            "reportDate": "2026-03-31", "filingDate": "2026-05-10",
            "filingUrl": "https://www.sec.gov/Archives/test.xml", "topHoldings": [],
        }},
    }), encoding="utf-8")
    monkeypatch.setattr(F13, "REGISTRY_PATH", registry)
    monkeypatch.setattr(F13, "_build_manager", lambda _: (_ for _ in ()).throw(TimeoutError()))
    got = F13.build(registry, cache)
    assert got["availableCount"] == 1 and got["liveCount"] == 0 and got["cachedCount"] == 1
    assert got["managers"][0]["status"] == "CACHED_OFFICIAL"
    assert got["managers"][0]["sourceMode"] == "CACHED_SEC"
