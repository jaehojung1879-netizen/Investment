"""Original DART bodies via OpenDART ``document.xml``; parsed by #320's parse_filing.

``document.xml`` returns the filing's original document ZIP. For the 13 fixed
#320 samples the parsed terms are identical to #320's public-viewer bodies
(see ``cohort/data/document-route-crosscheck-v1.json``), so the two routes are
cross-validated at the field level; the raw bytes differ (container markup).

Amendment references are read only from the amendment's OWN stated fields
(KRX form: "정정관련 공시서류" and "정정관련 공시서류제출일"), never inferred
from same issuer / same day.
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile

from ..filings import _value, day, parse_filing, table_rows
from .dart_client import DartClient


class DocumentNotServed(ValueError):
    """OpenDART answered that no original document file exists (status 014)."""


def document_body(client: DartClient, rcept_no: str) -> tuple[bytes, dict]:
    blob, meta = client.get('document.xml', {'rcept_no': rcept_no})
    if meta.get('status') == '014':
        raise DocumentNotServed('DOCUMENT_XML_STATUS_014_FILE_NOT_SERVED')
    if blob[:2] != b'PK':
        raise ValueError('DOCUMENT_NOT_ZIP:' + rcept_no)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = sorted(archive.namelist())
        primary = [n for n in names if n.startswith(rcept_no)] or names
        raw = archive.read(primary[0])
    return raw, {'zipSha256': meta['sha256'], 'zipBytes': meta['bytes'], 'member': primary[0],
                 'members': len(names), 'bodySha256': hashlib.sha256(raw).hexdigest(), 'bodyBytes': len(raw)}


def amendment_reference(raw: bytes) -> dict:
    rows = [r for r in table_rows(raw) if r]
    title = _value(rows, ('정정관련공시서류',))
    first = _value(rows, ('정정관련공시서류제출일',))
    first_day = day(first.replace('.', '-')) if first else None
    reason = _value(rows, ('정정사유',))
    return {'referencedTitle': title, 'referencedFirstFilingDay': first_day,
            'reason': reason, 'status': 'STATED' if title and first_day else 'NOT_STATED_IN_BODY'}


DSD_VALUE_CELL = re.compile(rb'<(/?)T[EU](?=[\s>])', re.I)


def as_table_cells(raw: bytes) -> tuple[bytes, bool]:
    """DART's structured document XML (major-matters forms) carries values in
    ``<TE ACODE=..>`` / ``<TU AUNIT=..>`` elements next to label ``<TD>`` cells. #320's
    table reader sees only td/th, so every B-type value read as missing. Renaming those
    two element names to TD (ASCII-only, encoding untouched) lets the unchanged #320
    label parser read them. The original bytes and their hashes are what is recorded."""
    converted, n = DSD_VALUE_CELL.subn(rb'<\1TD', raw)
    return converted, n > 0


def parse_body(raw: bytes, index_row: dict) -> dict:
    cells, converted = as_table_cells(raw)
    parsed = parse_filing(cells, {k: index_row.get(k) or '' for k in
                                ('rcept_no', 'report_nm', 'corp_code', 'corp_name', 'stock_code', 'rcept_dt', 'rm')})
    parsed.pop('raw_table_rows', None)
    parsed['input_sha256'] = hashlib.sha256(raw).hexdigest()
    parsed['parser_variant'] = 'dart-html-v1' + ('+dsd-te-tu-as-cells-v1' if converted else '')
    parsed['cohort_flags'] = body_flags(cells)
    return parsed


def body_flags(cells: bytes) -> list[str]:
    """Statements the body makes about ITSELF (never inferred from other filings)."""
    rows = [r for r in table_rows(cells) if r]
    flags = []
    title = _value(rows, ('제목',)) or ''
    if '진행사항' in title:
        flags.append('PROGRESS_UPDATE_OF_EARLIER_CONTRACT')
    withheld = _value(rows, ('유보사유',))
    if withheld and withheld.strip() not in ('-', '', '해당사항없음'):
        flags.append('TERMS_WITHHELD_UNTIL_LATER_DISCLOSURE')
    return flags
