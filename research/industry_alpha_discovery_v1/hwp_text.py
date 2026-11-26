"""Minimal HWP 5.0 text extraction (OLE compound file, zlib-deflated BodyText records).

Government press releases before ~2021 are published on the KDI archive only as .hwp. This reads the paragraph text
records (tag 67, HWPTAG_PARA_TEXT) of every BodyText section in order. Table cells are paragraphs, so a table comes
out one cell per line, row by row. Control characters (inline/extended controls occupy 8 UTF-16 units) are dropped.
No layout is reconstructed; parsers that read it are written against this cell-per-line form.
"""
from __future__ import annotations

import html
import re
import struct
import zipfile
import zlib
from pathlib import Path

import olefile

PARA_TEXT = 67
# Control chars that carry 7 extra UTF-16 units of payload (inline and extended controls).
_LONG = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}


def _decode_para(buf: bytes) -> str:
    units = struct.unpack(f"<{len(buf) // 2}H", buf[: len(buf) // 2 * 2])
    out, i = [], 0
    while i < len(units):
        u = units[i]
        if u < 32:
            if u in (10, 13):
                out.append("\n")
            elif u == 9:
                out.append("\t")
            i += 8 if u in _LONG else 1
            continue
        out.append(chr(u))
        i += 1
    return "".join(out)


def section_lines(data: bytes) -> list[str]:
    """Paragraph texts of one decompressed BodyText section, in record order."""
    lines, i = [], 0
    while i + 4 <= len(data):
        h = struct.unpack_from("<I", data, i)[0]
        tag, size = h & 0x3FF, (h >> 20) & 0xFFF
        i += 4
        if size == 0xFFF:
            size = struct.unpack_from("<I", data, i)[0]
            i += 4
        if tag == PARA_TEXT:
            t = _decode_para(data[i:i + size]).strip()
            if t:
                lines.append(t)
        i += size
    return lines


def hwp_lines(path: Path) -> list[str]:
    ole = olefile.OleFileIO(str(path))
    header = ole.openstream("FileHeader").read()
    compressed = bool(header[36] & 1)
    sections = sorted((e for e in ole.listdir() if e[0] == "BodyText"), key=lambda e: int(e[1].replace("Section", "")))
    lines = []
    for sec in sections:
        data = ole.openstream(sec).read()
        lines += section_lines(zlib.decompress(data, -15) if compressed else data)
    return lines


_HWPX_TOKEN = re.compile(r"<hp:p[\s>]|</hp:p>|<hp:t>(.*?)</hp:t>|<hp:t/>", re.S)


def hwpx_lines(path: Path) -> list[str]:
    """HWPX (zipped OWPML): paragraph texts in the same order HWP5 records give them -- a paragraph's own text is
    emitted when its first nested paragraph (a table cell) opens, so table cells follow the text that precedes them."""
    z = zipfile.ZipFile(path)
    names = sorted((n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n)),
                   key=lambda n: int(re.findall(r"\d+", n)[-1]))
    lines: list[str] = []
    for n in names:
        xml = z.read(n).decode("utf-8", "ignore")
        stack: list[list[str]] = []
        for m in _HWPX_TOKEN.finditer(xml):
            tok = m.group(0)
            if tok.startswith("<hp:p"):
                if stack and "".join(stack[-1]).strip():
                    lines.append("".join(stack[-1]).strip())
                    stack[-1].clear()
                stack.append([])
            elif tok == "</hp:p>":
                if stack:
                    t = "".join(stack.pop()).strip()
                    if t:
                        lines.append(t)
            elif m.group(1) is not None and stack:
                stack[-1].append(html.unescape(re.sub(r"<[^>]+>", "", m.group(1))))
    return lines


def any_lines(path: Path) -> list[str]:
    return hwpx_lines(path) if path.suffix.lower() == ".hwpx" else hwp_lines(path)


def hwp_text(path: Path) -> str:
    return "\n".join(any_lines(path))
