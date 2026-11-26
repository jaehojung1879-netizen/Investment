"""Network-free source identity and archive-selection checks."""

import io
import json
from urllib.error import HTTPError

import pytest

from research.next_alpha_source_admission_v1.tools import guidance_source_recovery as recovery

ACCESSION = "0001018840-24-000012"
ROW = {"cik": 1018840, "accession": ACCESSION, "ticker": "TEST", "split": "dev"}
HEADER = f"<SEC-DOCUMENT>{ACCESSION}.txt : 20240306\n".encode()


def exhibit(filename, kind="EX-99.1", description="Exhibit 99.1"):
    return (f"<DOCUMENT>\n<TYPE>{kind}\n<FILENAME>{filename}\n<DESCRIPTION>{description}\n"
            "<TEXT>\n<p>source evidence</p>\n</TEXT>\n</DOCUMENT>\n").encode()


class ArchiveReply(io.BytesIO):
    status = 200

    def geturl(self):
        return recovery.url_for(ROW)


def test_archive_source_keeps_exact_section_bytes_and_separate_historical_hash(tmp_path):
    wanted = exhibit("q42023pressrelease.htm")
    other = exhibit("q42023investorpresentation.htm", "EX-99.2", "Investor presentation")
    full = HEADER + wanted + other
    record = recovery.recover({**ROW, "sha256": "0" * 64}, tmp_path,
                              open_url=lambda *_args, **_kwargs: ArchiveReply(full))
    assert record["status"] == "OFFICIAL_ARCHIVE_SECTION"
    assert record["filename"] == "q42023pressrelease.htm"
    assert record["historyVerified"] is False
    assert (tmp_path / "sections" / record["sectionSha256"]).read_bytes() == wanted
    assert not (tmp_path / "sections" / record["registeredHttpSha256"]).exists()
    assert (tmp_path / "submissions" / record["archiveSha256"]).read_bytes() == full


def test_registered_filename_is_required_even_when_another_exhibit_looks_relevant(tmp_path):
    payload = HEADER + exhibit("pressrelease.htm")
    record = recovery.recover({**ROW, "exhibit": "historical.htm"}, tmp_path,
                              open_url=lambda *_args, **_kwargs: ArchiveReply(payload))
    assert record["status"] == "EXHIBIT_UNRESOLVED"
    assert record["selection"] == "REGISTERED_EXHIBIT_ABSENT_OR_DUPLICATED"
    assert not (tmp_path / "sections").exists()


def test_multiple_likely_exhibits_are_unresolved_and_preserved_for_review(tmp_path):
    payload = HEADER + exhibit("q3-press-release.htm") + exhibit("q3b-press-release.htm", "EX-99.2")
    record = recovery.recover(ROW, tmp_path, open_url=lambda *_args, **_kwargs: ArchiveReply(payload))
    assert record["selection"] == "AMBIGUOUS_EX99"
    assert len(record["candidates"]) == 2
    assert (tmp_path / "submissions" / record["archiveSha256"]).exists()
    assert not (tmp_path / "sections").exists()


def test_http_success_does_not_admit_another_accession(tmp_path):
    other = HEADER.replace(ACCESSION.encode(), b"0001018840-24-000013") + exhibit("pressrelease.htm")
    record = recovery.recover(ROW, tmp_path, open_url=lambda *_args, **_kwargs: ArchiveReply(other))
    assert record["status"] == "ARCHIVE_ACCESSION_MISMATCH"
    assert not list(tmp_path.iterdir())


def test_frozen_roster_hash_is_checked_before_any_source_call(tmp_path):
    roster = tmp_path / "roster.json"
    roster.write_text(json.dumps({"documents": [ROW]}), encoding="utf-8")
    with pytest.raises(ValueError, match="ROSTER_SHA256_MISMATCH"):
        recovery.load_roster(roster, "0" * 64)
    assert recovery.load_roster(roster, recovery.digest(roster.read_bytes()))[0] == [ROW]


def test_public_archive_redirect_cannot_escape_the_source_host():
    handler = recovery.SameSECArchive()
    with pytest.raises(HTTPError, match="Off-archive redirect"):
        handler.redirect_request(recovery.Request(recovery.url_for(ROW)), None, 302, "Moved", {},
                                 "https://example.org/redirected")
