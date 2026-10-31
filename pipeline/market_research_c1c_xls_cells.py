"""Minimal, strict, dependency-free reader for the ONE retained issuer `.xls` (KODEX 200 standard-price sheet).

Why it exists: the 3,612-session comparison of the rebuilt as-traded close with the issuer's own close must run in the required
CI, which does not install xlrd (an audit-only dependency elsewhere in this repository). A reader that handled every .xls would be
a framework; this one reads OLE2 + BIFF8 cells of a single worksheet and RAISES on anything it does not understand
(non-FAT workbook streams, more than one worksheet, an unreadable cell record) instead of skipping it.

It cannot make a wrong number look right: a mis-parsed close breaks the session-by-session identity the caller asserts. It is
also compared cell by cell with xlrd where xlrd is installed (`tests/test_market_research_c1c_source_evidence.py`).
"""
from __future__ import annotations

import struct
from pathlib import Path

FREESECT, ENDOFCHAIN = 0xFFFFFFFF, 0xFFFFFFFE
OLE_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")
BOF, EOF_, SST, CONTINUE, LABELSST, NUMBER, RK, MULRK, LABEL = 0x0809, 0x000A, 0x00FC, 0x003C, 0x00FD, 0x0203, 0x027E, 0x00BD, 0x0204


class XlsReadError(ValueError):
    pass


def _workbook_stream(raw):
    if raw[:8] != OLE_MAGIC:
        raise XlsReadError("NOT_AN_OLE2_FILE")
    sector = 1 << struct.unpack_from("<H", raw, 30)[0]
    n_fat, dir_start, cutoff = struct.unpack_from("<I", raw, 44)[0], struct.unpack_from("<I", raw, 48)[0], struct.unpack_from("<I", raw, 56)[0]
    difat_start, n_difat = struct.unpack_from("<I", raw, 68)[0], struct.unpack_from("<I", raw, 72)[0]

    def sector_bytes(index):
        start = (index + 1) * sector
        if start + sector > len(raw):
            raise XlsReadError("SECTOR_OUT_OF_RANGE")
        return raw[start:start + sector]

    fat_sectors = [s for s in struct.unpack_from("<109I", raw, 76) if s != FREESECT]
    nxt = difat_start
    for _ in range(n_difat):
        block = struct.unpack("<%dI" % (sector // 4), sector_bytes(nxt))
        fat_sectors += [s for s in block[:-1] if s != FREESECT]
        nxt = block[-1]
    fat = []
    for s in fat_sectors[:n_fat]:
        fat += struct.unpack("<%dI" % (sector // 4), sector_bytes(s))

    def chain(start):
        out, seen = [], set()
        while start != ENDOFCHAIN:
            if start in seen or start >= len(fat):
                raise XlsReadError("BAD_SECTOR_CHAIN")
            seen.add(start)
            out.append(start)
            start = fat[start]
        return out

    directory = b"".join(sector_bytes(s) for s in chain(dir_start))
    for off in range(0, len(directory), 128):
        entry = directory[off:off + 128]
        name_len = struct.unpack_from("<H", entry, 64)[0]
        name = entry[:max(name_len - 2, 0)].decode("utf-16-le", "replace")
        if name in ("Workbook", "Book") and entry[66] == 2:
            start, size = struct.unpack_from("<I", entry, 116)[0], struct.unpack_from("<I", entry, 120)[0]
            if size < cutoff:
                raise XlsReadError("MINI_STREAM_WORKBOOK_NOT_SUPPORTED")
            return b"".join(sector_bytes(s) for s in chain(start))[:size]
    raise XlsReadError("NO_WORKBOOK_STREAM")


def _records(stream):
    pos = 0
    while pos + 4 <= len(stream):
        rid, length = struct.unpack_from("<HH", stream, pos)
        yield rid, stream[pos + 4:pos + 4 + length]
        pos += 4 + length


def _shared_strings(parts):
    """SST payload split into [record data, continuation data...]; a string's character run may cross a boundary, where the
    continuation record starts with a fresh one-byte encoding flag."""
    data = parts[0]
    unique = struct.unpack_from("<I", data, 4)[0]
    segments, cursor = parts, 8
    index = 0

    def take(count, wide):
        nonlocal index, cursor
        out = []
        while count:
            avail = (len(segments[index]) - cursor) // (2 if wide else 1)
            if avail == 0:
                index += 1
                cursor = 1
                wide = bool(segments[index][0] & 1)
                continue
            n = min(count, avail)
            chunk = segments[index][cursor:cursor + n * (2 if wide else 1)]
            out.append(chunk.decode("utf-16-le" if wide else "latin-1"))
            cursor += len(chunk)
            count -= n
        return "".join(out)

    def skip(count):
        nonlocal index, cursor
        while count:
            avail = len(segments[index]) - cursor
            if avail == 0:
                index += 1
                cursor = 0
                continue
            n = min(count, avail)
            cursor += n
            count -= n

    def read(fmt):
        nonlocal index, cursor
        size = struct.calcsize(fmt)
        if cursor + size > len(segments[index]):
            raise XlsReadError("SST_FIELD_SPANS_RECORDS")
        value = struct.unpack_from(fmt, segments[index], cursor)[0]
        cursor += size
        return value

    strings = []
    for _ in range(unique):
        if cursor >= len(segments[index]):
            index, cursor = index + 1, 0
        cch = read("<H")
        flags = read("<B")
        runs = read("<H") if flags & 0x08 else 0
        ext = read("<I") if flags & 0x04 else 0
        strings.append(take(cch, bool(flags & 0x01)))
        skip(4 * runs + ext)
    return strings


def _rk(value):
    if value & 2:
        number = float(struct.unpack("<i", struct.pack("<I", value))[0] >> 2)
    else:
        number = struct.unpack("<d", struct.pack("<Q", (value & 0xFFFFFFFC) << 32))[0]
    return number / 100.0 if value & 1 else number


def read_cells(path):
    """{(row, col): str | float} for the single worksheet. Raises on anything not understood."""
    stream = _workbook_stream(Path(path).read_bytes())
    sst_parts, in_sst, strings, worksheets = [], False, None, 0
    cells, pending_label = {}, []
    for rid, data in _records(stream):
        if in_sst and rid == CONTINUE:
            sst_parts.append(data)
            continue
        if in_sst:
            strings, in_sst = _shared_strings(sst_parts), False
        if rid == SST:
            sst_parts, in_sst = [data], True
        elif rid == BOF:
            if struct.unpack_from("<H", data, 2)[0] == 0x0010:
                worksheets += 1
        elif rid == LABELSST:
            row, col, _, isst = struct.unpack_from("<HHHI", data)
            pending_label.append((row, col, isst))
        elif rid == NUMBER:
            row, col = struct.unpack_from("<HH", data)
            cells[(row, col)] = struct.unpack_from("<d", data, 6)[0]
        elif rid == RK:
            row, col, _, value = struct.unpack_from("<HHHI", data)
            cells[(row, col)] = _rk(value)
        elif rid == MULRK:
            row, first = struct.unpack_from("<HH", data)
            count = (len(data) - 6) // 6
            for k in range(count):
                cells[(row, first + k)] = _rk(struct.unpack_from("<I", data, 4 + 6 * k + 2)[0])
        elif rid == LABEL:
            raise XlsReadError("LABEL_RECORD_NOT_SUPPORTED")
    if worksheets != 1:
        raise XlsReadError("EXPECTED_EXACTLY_ONE_WORKSHEET")
    if strings is None and pending_label:
        raise XlsReadError("LABELSST_WITHOUT_SST")
    for row, col, isst in pending_label:
        if isst >= len(strings):
            raise XlsReadError("SST_INDEX_OUT_OF_RANGE")
        cells[(row, col)] = strings[isst]
    return cells
