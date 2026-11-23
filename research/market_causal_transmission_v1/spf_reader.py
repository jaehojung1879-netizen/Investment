"""Standard-library reader for the preserved SPF workbook (no openpyxl).

CI installs only the registered requirements, which do not include openpyxl. The executed study read the workbook
with openpyxl through `panel.load_spf`; this reader returns the same records from the same preserved bytes, and
`evidence/spf-level-parsed.json` (written with openpyxl) is the fixture both must equal.
"""
from __future__ import annotations

import gzip
import io
import re
import zipfile
from xml.etree import ElementTree as ET

from . import panel as P

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _column(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_rows(raw_xlsx: bytes) -> list[list]:
    with zipfile.ZipFile(io.BytesIO(raw_xlsx)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in sheet.iter(f"{{{NS['m']}}}row"):
        values: dict[int, object] = {}
        for c in row.findall("m:c", NS):
            v = c.find("m:v", NS)
            if v is None:
                continue
            kind = c.get("t")
            if kind == "s":
                values[_column(c.get("r"))] = shared[int(v.text)]
            elif kind in ("e", "str"):
                values[_column(c.get("r"))] = v.text
            else:
                values[_column(c.get("r"))] = float(v.text)
        rows.append([values.get(i) for i in range(max(values) + 1)] if values else [])
    return rows


def load_spf_stdlib() -> list[dict]:
    """Same records as `panel.load_spf`, without openpyxl."""
    rows = read_rows(gzip.decompress((P.RAW / "spf-median-cprof-level.xlsx.gz").read_bytes()))
    head = rows[0]
    out = []
    for r in rows[1:]:
        if not r:
            continue
        rec = dict(zip(head, r + [None] * (len(head) - len(r))))
        vals = {k: (float(rec[k]) if isinstance(rec[k], (int, float)) else None)
                for k in ("CPROF2", "CPROF3", "CPROF5", "CPROF6")}
        out.append({"year": int(rec["YEAR"]), "quarter": int(rec["QUARTER"]), **vals})
    return out
