"""MOTIE monthly item table from the cell-per-line text of an HWP release (2013 to ~2021).

The table is titled like "< 13대 품목별 2월 수출실적 >" (13대/15대/20대 varies). Its header names the columns
(prior-year total, months of the current year, a month range, the same month a year earlier ...), then each item row is
the item name, an optional "(증가율)" label, one amount per column (USD million) and one parenthesised growth rate per
column. Months are read from the header labels; annual totals and ranges are skipped, as in #356's PDF parser.
"""
from __future__ import annotations

import re

NUM = re.compile(r"^△?\s?-?[\d,]+(?:\.\d+)?$")
PAREN = re.compile(r"^\(\s*(△|-)?\s*([\d,]+(?:\.\d+)?)\s*\)$")
TITLE = re.compile(r"\d{2}\s*대\s*(?:주요\s*)?품목.*수출")


def _num(t: str) -> float:
    t = t.replace(",", "").replace(" ", "")
    neg = t.startswith("△") or t.startswith("-")
    return -float(t.lstrip("△-")) if neg else float(t.lstrip("△-"))


def _label_month(label: str, ref_year: int, ref_month: int) -> str | None:
    """'2월P' / '’13.2월' / '’12.2' / '12월' -> YYYY-MM; annual totals and ranges -> None."""
    s = label.replace(" ", "").replace("P", "").replace("p", "")
    if re.search(r"[~～∼]|전체|년$|누계|연간|상반기|하반기", s):
        return None
    m = re.match(r"^[’'‘`]?(\d{2})[.년](\d{1,2})월?$", s)
    if m:
        return f"20{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"^(\d{1,2})월$", s)
    if m:
        mo = int(m.group(1))
        y = ref_year if mo <= ref_month else ref_year - 1
        return f"{y}-{mo:02d}"
    return None


def parse(lines: list[str], ref_month: str) -> dict | None:
    """Return {"columns": [YYYY-MM or None ...], "rows": {item: {month: (value, growthPct)}}} or None."""
    ry, rm = int(ref_month[:4]), int(ref_month[5:7])
    for start, line in enumerate(lines):
        if not TITLE.search(line) or "수입" in line:
            continue
        # header: from the title to the first line followed by "(증가율)" or by an amount
        hdr, i = [], start + 1
        while i < len(lines) - 1 and i < start + 40:
            nxt = lines[i + 1].strip()
            if nxt.startswith("(증가율") or NUM.match(nxt.replace(" ", "")):
                break
            hdr.append(lines[i].strip())
            i += 1
        hdr = [h for h in hdr if h and "단위" not in h and h not in ("품목명", "품목", "품 목")]
        bare_year = re.compile(r"^[’'‘`]?(\d{2})(?:년)?$")
        period_word = re.compile(r"^(상반기|하반기|연간|전체|년\s*전체)P?$")
        cols, months, consumed = [], [], set()
        bare_month = re.compile(r"^(\d{1,2})월P?$", re.I)
        for k, h in enumerate(hdr):
            h0 = h.replace(" ", "")
            if k in consumed:
                continue
            if bare_year.match(h0):
                nxt = hdr[k + 1].replace(" ", "") if k + 1 < len(hdr) else ""
                if period_word.match(nxt):                  # '‘14' + '상반기' is one (annual) column
                    cols.append(h0 + nxt)
                    months.append(None)
                    consumed.add(k + 1)
                continue                                    # otherwise a year prefix over the month labels
            if period_word.match(h0):                       # a standalone period column (e.g. this year's 상반기)
                cols.append(h0)
                months.append(None)
                continue
            if re.search(r"\d", h0):
                cols.append(h)
                months.append("BARE" if bare_month.match(h0) else _label_month(h, ry, rm))
        # bare month labels run forward in time: the last one is the reference month; stepping back across
        # January moves to the previous year (prefix cells like '‘21년' '‘22년' can sit together above them)
        bare = [k for k, m in enumerate(months) if m == "BARE"]
        if bare and int(bare_month.match(cols[bare[-1]].replace(" ", "")).group(1)) == rm:
            y, prev = ry, None
            for k in reversed(bare):
                mo = int(bare_month.match(cols[k].replace(" ", "")).group(1))
                if prev is not None and mo > prev:
                    y -= 1
                months[k], prev = f"{y}-{mo:02d}", mo
        else:
            for k in bare:
                months[k] = _label_month(cols[k], ry, rm)
        if f"{ry}-{rm:02d}" not in months:
            continue
        rows, k, pending = {}, i, []
        while k < len(lines) and k < i + 600:
            name = lines[k].strip()
            j = k + 1
            if j < len(lines) and lines[j].strip().startswith("(증가율"):
                j += 1
            vals = []
            while j < len(lines) and NUM.match(lines[j].strip().replace(" ", "")) and len(vals) < len(cols):
                vals.append(_num(lines[j].strip()))
                j += 1
            grs = []
            while j < len(lines) and PAREN.match(lines[j].strip()) and len(grs) < len(cols):
                g = PAREN.match(lines[j].strip())
                grs.append(-float(g.group(2).replace(",", "")) if g.group(1) else float(g.group(2).replace(",", "")))
                j += 1
            if len(vals) == len(cols) and re.search(r"[가-힣]", name):
                # a long item name wraps over several cells ("석유" / "제품"): join the fragments since the last row
                item = re.sub(r"\s+", "", "".join(pending + [name])).lstrip("ㅇ○◦-·")
                pending = []
                rows[item] = {mo: (v, grs[c] if len(grs) == len(cols) else None)
                              for c, (mo, v) in enumerate(zip(months, vals)) if mo}
                k = j
                continue
            if rows and (TITLE.search(name) or name.startswith("<")):
                break
            short_text = re.fullmatch(r"[가-힣A-Za-z·\s]{1,8}", name) is not None
            pending = pending + [name] if (short_text and k > i) else []
            k += 1
        if rows:
            return {"columns": months, "rows": rows}
    return None
