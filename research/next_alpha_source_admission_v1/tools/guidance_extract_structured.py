"""Extract numeric SEC guidance from the table DOM with auditable abstentions.

The frozen extractors segment cells into row strings. This alternative retains
physical rows, columns, spans, captions and nearby section headings so a value
inherits the headers actually over its column. It handles both metric rows and
transposed metric columns. Ambiguous cells enter a manual review queue.
"""
from __future__ import annotations

import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doc_blocks as legacy_blocks  # noqa: E402
import guidance_extract_v2 as baseline  # noqa: E402


_TEXT_BREAKS = legacy_blocks.BREAK - {"table", "tr"} | {"section", "ul", "ol"}
_CELL_TAGS = {"th", "td"}
_SKIP = {"script", "style", "sup", "ix:hidden", "noscript"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_FORWARD = re.compile(r"\b(?:outlook|guidance|forecast\w*|projected|expected)\b", re.I)
_HISTORICAL = re.compile(
    r"\b(?:actuals?|historical|reported results|financial results|prior year|previous year|last year|"
    r"year.ago|compar(?:ed with|ative)|ytd|year.to.date|(?:months?|years?|quarters?) ended|"
    r"variance|% change|change vs\.?|cash flow statements?|balance sheets?|results of operations|"
    r"statements of (?:operations|income|cash flows))\b", re.I)
_RECONCILIATION = re.compile(r"\b(?:reconcil\w*|adjustments? to|bridge to)\b", re.I)
_NON_TOTAL = re.compile(
    r"\b(?:restructuring|impairment|amortization|acquisition.related|tax effect|stock.based|"
    r"impact|headwinds?|tailwinds?|contribution|dilution|accretion|adjustments? to|segment)\b", re.I)
_PRIOR = re.compile(r"\b(?:previous(?:ly)?|prior|initial|original|earlier|old)\b", re.I)
_CURRENT = re.compile(r"\b(?:current|updated|revised|new|reaffirmed)\b", re.I)
_SCALE = re.compile(r"\b(billions?|millions?|thousands?|bn|mm)\b|\$\s*([bBmMkK])\b", re.I)
_FOREIGN_CURRENCY = re.compile(r"[€£¥]|\b(?:CAD|AUD|EUR|GBP|JPY|CNY|RMB|HKD|KRW)\b|\b(?:C|A|HK)\$", re.I)
_PERCENT_METRICS = {"operating_margin", "gross_margin", "tax_rate", "revenue_growth", "eps_growth", "fcf_margin"}
_NON_GAAP_METRICS = {"ebitda", "free_cash_flow", "fcf_margin"}
_FY = re.compile(r"\b(?:FY|CY|(?:full|fiscal|calendar)[ -]year)\s*['’]?(20\d{2}|\d{2})\b|"
                 r"\b(20\d{2})\s+(?:full|fiscal|calendar)[ -]year\b", re.I)
_YEAR = re.compile(r"\b20\d{2}\b")
_OTHER_INTERVAL = re.compile(
    r"\b(?:half[ -]year|[12][hH]|[hH][12]|(?:first|second) half|"
    r"(?:quarters?|three months?|six months?|nine months?|period)\s+(?:end(?:ed|ing)|to)|"
    r"next quarter|rolling twelve months)\b", re.I)
_DIGITS = r"(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
_VALUE = (rf"\(?\s*(?:USD\s*|US\s*\$\s*|\$\s*)?[-+−]?\s*{_DIGITS}\s*\)?\+?"
          r"(?:\s*(?:billions?|millions?|thousands?|bn|mm|[bBmMkK])\b)?\s*(?:%|percent\b)?")
_AMOUNT = re.compile(rf"(?P<amount>{_VALUE})", re.I)
_RANGE = re.compile(rf"(?:between\s+)?(?P<low>{_VALUE})\s*(?:to|through|and|[-–—−])\s*(?P<high>{_VALUE})", re.I)
_PLUS_MINUS = re.compile(rf"(?P<mid>{_VALUE})\s*(?:±|\+/-|plus or minus)\s*(?P<spread>{_VALUE})", re.I)
_NUMBER = re.compile(rf"[-+−]?\s*{_DIGITS}")
_LEADING_VALUE = re.compile(r"^(?:(?:approximately|approx\.?|about|around|at least)\s+|[~≈]\s*)", re.I)
_MAYBE_VALUE = re.compile(r"(?i)(?:[$€£¥]\s*[+−-]?\s*\d|\d\s*(?:%|(?:percent|billion|million|thousand)\b))")
_SYMBOLS_BEFORE = {"$", "(", "($", "$ (", "−", "-"}
_SYMBOLS_AFTER = {"%", ")", ")%", "%)", "+"}
_HIDDEN_STYLE = re.compile(r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\b", re.I)


def _clean(text):
    return " ".join(text.split())


@dataclass
class _Cell:
    text: str
    header: bool
    rowspan: int
    colspan: int


@dataclass
class _Table:
    context: tuple[str, ...]
    rows: list[list[_Cell]] = field(default_factory=list)
    caption: str = ""
    row: list[_Cell] | None = None
    cell: list[str] | None = None
    cell_meta: tuple = ()
    caption_parts: list[str] | None = None

    def end_cell(self):
        if self.cell is not None:
            self.row.append(_Cell(_clean("".join(self.cell)), *self.cell_meta))
            self.cell = None

    def end_row(self):
        if self.row is not None:
            self.end_cell()
            if self.row:
                self.rows.append(self.row)
            self.row = None

    def end_caption(self):
        if self.caption_parts is not None:
            self.caption = _clean("".join(self.caption_parts))
            self.caption_parts = None


def _span(attributes, name):
    try:
        return max(1, min(256, int(attributes.get(name, 1))))
    except (TypeError, ValueError):
        return 1


class _Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.stack = []
        self.ignore = []
        self.text = []
        self.paragraphs = []

    def _paragraph(self):
        value = _clean("".join(self.text))
        if value:
            self.paragraphs.append(value)
        self.text.clear()

    def handle_starttag(self, tag, attrs):
        if self.ignore:
            if tag not in _VOID:
                self.ignore.append(tag)
            return
        attributes = dict(attrs)
        hidden = ("hidden" in attributes or attributes.get("aria-hidden") == "true"
                  or _HIDDEN_STYLE.search(attributes.get("style") or ""))
        if hidden and tag in _VOID:
            return
        if tag in _SKIP or hidden:
            self.ignore.append(tag)
            return
        if tag == "table":
            self._paragraph()
            table = _Table(tuple(self.paragraphs[-3:]))
            self.tables.append(table)
            self.stack.append(table)
        elif self.stack:
            table = self.stack[-1]
            if tag == "caption":
                table.caption_parts = []
            elif tag == "tr":
                table.end_caption()
                table.end_row()
                table.row = []
            elif tag in _CELL_TAGS:
                table.end_cell()
                if table.row is None:
                    table.row = []
                table.cell = []
                table.cell_meta = (tag == "th", _span(attributes, "rowspan"), _span(attributes, "colspan"))
            elif tag == "br" and table.cell is not None:
                table.cell.append(" ")
        elif tag in _TEXT_BREAKS:
            self._paragraph()

    def handle_endtag(self, tag):
        if self.ignore:
            if tag in self.ignore:
                end = len(self.ignore) - 1 - self.ignore[::-1].index(tag)
                del self.ignore[end:]
            return
        if self.stack:
            table = self.stack[-1]
            if tag in _CELL_TAGS:
                table.end_cell()
            elif tag == "tr":
                table.end_row()
            elif tag == "caption":
                table.end_caption()
            elif tag == "table":
                table.end_row()
                table.end_caption()
                self.stack.pop()
        elif tag in _TEXT_BREAKS:
            self._paragraph()

    def handle_data(self, data):
        if self.ignore:
            return
        if not self.stack:
            self.text.append(data)
        else:
            table = self.stack[-1]
            if table.cell is not None:
                table.cell.append(data)
            elif table.caption_parts is not None:
                table.caption_parts.append(data)

    def close(self):
        super().close()
        for table in self.stack:
            table.end_row()
            table.end_caption()


def _grid(rows):
    """Expand spans into an addressable grid and retain each cell's origin."""
    grid = [dict() for _ in rows]
    for row_index, row in enumerate(rows):
        column = 0
        for cell in row:
            while column in grid[row_index]:
                column += 1
            for row_number in range(row_index, min(len(rows), row_index + cell.rowspan)):
                for col_number in range(column, column + cell.colspan):
                    grid[row_number].setdefault(col_number, (row_index, column, cell))
            column += cell.colspan
    return grid


def _target(text, document):
    quarter = baseline.QTR.search(text)
    explicit_fy = _FY.search(text)
    years = set(_YEAR.findall(text))
    if quarter:
        q = quarter.groups()
        number = baseline.ORD.get((q[0] or "").lower()) or int(q[4] or q[6])
        year = q[2] or q[3] or q[5] or q[7]
        if year is None and explicit_fy:
            year = next(x for x in explicit_fy.groups() if x)
        if year is None and len(years) == 1:
            year = next(iter(years))
        year = baseline._yy(year) if year else document.get("next_q_year", {}).get(number)
        if year is not None:
            return f"Q{number}FY{year}"
        return None
    if _OTHER_INTERVAL.search(text):
        return None
    if explicit_fy:
        year = baseline._yy(next(x for x in explicit_fy.groups() if x))
        prefix = "CY" if re.search(r"\b(?:CY|calendar[ -]year)", explicit_fy.group(), re.I) else "FY"
        return f"{prefix}{year}"
    if len(years) == 1 and re.search(r"\b(?:annual|full[ -]year)\b", text, re.I):
        return f"FY{next(iter(years))}"
    if re.fullmatch(r"\s*20\d{2}\s*", text):
        return f"FY{text.strip()}"
    if len(years) == 1 and _FORWARD.search(text):
        return f"FY{next(iter(years))}"
    if re.search(r"\b(?:full[ -]year|fiscal year|annual)\b", text, re.I) and document.get("fy_default"):
        return f"FY{document['fy_default']}"
    return None


def _basis(text):
    non_gaap = baseline.NONGAAP.search(text)
    gaap = baseline.GAAP.search(text)
    if gaap and non_gaap:
        return None
    return "non_GAAP" if non_gaap else "GAAP" if gaap else None


def _role(text):
    if _HISTORICAL.search(text):
        return "ACTUAL"
    if _PRIOR.search(text):
        return "PRIOR"
    if _CURRENT.search(text) or _FORWARD.search(text):
        return "CURRENT"
    return None


def _metric(text):
    if _NON_TOTAL.search(text):
        return None
    return baseline.metric_of(text)[0]


def _scale(text):
    match = _SCALE.search(text)
    factors = {"billion": 1000.0, "b": 1000.0, "bn": 1000.0, "million": 1.0, "m": 1.0,
               "mm": 1.0, "thousand": 0.001, "k": 0.001}
    return factors[(match[1] or match[2]).lower().rstrip("s")] if match else None


def _amount(text):
    match = _NUMBER.search(text)
    signed = match.group().replace(",", "").replace("−", "-").replace(" ", "")
    value = float(signed)
    if "(" in text and ")" in text:
        value = -abs(value)
    suffix = text[match.end():]
    unit_scale = _scale(text)
    if unit_scale is None:
        short_scale = re.match(r"\s*[+)]*\s*([bmk])\b", suffix, re.I)
        if short_scale:
            unit_scale = {"b": 1000.0, "m": 1.0, "k": 0.001}[short_scale[1].lower()]
    return value, unit_scale


def _value_syntax(text):
    plain = _LEADING_VALUE.sub("", text.strip())
    return _PLUS_MINUS.fullmatch(plain) or _RANGE.fullmatch(plain) or _AMOUNT.fullmatch(plain)


def _numeric(text, metric, context_axes):
    context = " ".join(context_axes)
    match = _value_syntax(text)
    if not match:
        return None
    if _FOREIGN_CURRENCY.search(text + " " + context):
        return None
    parts = match.groupdict()
    numbers = [_amount(value) for value in parts.values()]
    if not all(math.isfinite(value) for value, _ in numbers):
        return None
    is_pct = bool(re.search(r"%|\bpercent\b", text + " " + context, re.I))
    has_money = bool(re.search(r"\$|\bUSD\b", text + " " + context, re.I))
    if metric == "gross_margin" and not is_pct and (has_money or any(scale for _, scale in numbers)):
        metric = "gross_profit"
    if metric in _PERCENT_METRICS:
        if re.search(r"\$|\bUSD\b", text, re.I) or any(scale for _, scale in numbers):
            return None
        unit, default = "pct", 1.0
    elif is_pct and re.search(r"%|\bpercent\b", text, re.I):
        return None
    elif metric == "eps":
        if any(scale for _, scale in numbers):
            return None
        unit, default = "USD_per_share", 1.0
    else:
        unit = "USD_million"
        default = next((scale for _, scale in numbers if scale is not None), None)
        if default is None:
            default = next((scale for axis in context_axes if (scale := _scale(axis)) is not None), None)
        if default is None:
            if not has_money:
                return None
            default = 0.000001
    points = [value * (scale if scale is not None else default) for value, scale in numbers]
    if not all(math.isfinite(value) for value in points):
        return None
    if "mid" in parts:
        low, high = points[0] - abs(points[1]), points[0] + abs(points[1])
    elif "high" in parts:
        low, high = sorted(points)
    else:
        low = points[0]
        open_bound = bool(re.match(r"(?i)^at least\b", text) or re.search(r"\d\s*\+", text))
        high = None if open_bound else low
    if not math.isfinite(low) or (high is not None and not math.isfinite(high)):
        return None
    return metric, unit, low, high


def _visible(row, row_index):
    return [(col, cell) for col, (origin, column, cell) in sorted(row.items())
            if origin == row_index and col == column and cell.text]


def _value_columns(row, row_index):
    visible = _visible(row, row_index)
    values = [(col, cell.text) for col, cell in visible if not cell.header
              and (_value_syntax(cell.text) or (_MAYBE_VALUE.search(cell.text) and not _metric(cell.text)))]
    if values and all(re.fullmatch(r"(?:19|20)\d{2}", text) for _, text in values):
        labels = [cell.text for _, cell in visible if not _value_syntax(cell.text)]
        if not any(_metric(label) or _basis(label) for label in labels):
            return []
    numeric = []
    for col, text in values:
        if col - 1 in row and row[col - 1][2].text in _SYMBOLS_BEFORE:
            text = row[col - 1][2].text + text
        if col + 1 in row and row[col + 1][2].text in _SYMBOLS_AFTER:
            text += row[col + 1][2].text
        numeric.append((col, text))
    return numeric


def _scope(table):
    if table.caption and (_HISTORICAL.search(table.caption) or _RECONCILIATION.search(table.caption)):
        return table.caption
    banners = []
    for row in table.rows:
        cells = [cell.text for cell in row if cell.text]
        if any(_value_syntax(text) for text in cells):
            break
        if len(cells) == 1:
            banners.extend(cells)
    for text in (table.caption, *banners, *reversed(table.context)):
        if not text or len(text) > 220 or legacy_blocks.BOILER.search(text):
            continue
        if _FORWARD.search(text) or _HISTORICAL.search(text) or _RECONCILIATION.search(text):
            return text
    return table.caption


def _header(row, rows, col):
    return tuple(dict.fromkeys(rows[i][col][2].text for i in row if col in rows[i] and rows[i][col][2].text))


def _axis_bound(headers):
    for text in reversed(headers):
        match = re.fullmatch(r"\s*(low(?:er)?|high(?:er)?|min(?:imum)?|max(?:imum)?)(?:[ -]end)?\s*", text, re.I)
        if match:
            return "LOW" if match[1].lower().startswith(("low", "min")) else "HIGH"
    return None


def _resolved_target(local_axes, cell_context, scope, document):
    if any(_OTHER_INTERVAL.search(value) and _target(value, document) is None for value in local_axes):
        return None, "UNRESOLVED_NON_ANNUAL_INTERVAL"
    explicit = {_target(value, {}) for value in local_axes} - {None}
    # A quarter may be a leaf under a fiscal-year column group. Keep the
    # narrower target only when the two headers name the same fiscal year.
    quarters = {value for value in explicit if value.startswith("Q")}
    if len(quarters) == 1 and next(iter(quarters))[2:] in explicit:
        explicit.discard(next(iter(quarters))[2:])
    if len(explicit) > 1:
        return None, "CONFLICTING_TARGET_AXES"
    scope_target = _target(scope, document)
    target = (_target(cell_context, document) if baseline.QTR.search(cell_context) else None
              ) or next(iter(explicit), None) or _target(cell_context, document) or scope_target
    if target is None:
        return None, "MISSING_EXPLICIT_TARGET"
    if scope_target and int(target[-4:]) < int(scope_target[-4:]) and not _FORWARD.search(cell_context):
        return None, "EARLIER_COMPARISON_PERIOD"
    report_q = document.get("report_q")
    if report_q and document.get("year") and "FY" in target:
        report_year = document["year"] - (report_q == 4)
        target_year = int(target[-4:])
        target_q = int(target[1]) if target.startswith("Q") else 4
        if (target_year, target_q) <= (report_year, report_q):
            return None, "REPORTED_PERIOD"
    return target, None


def _fact(table_i, row_i, cols, block, key, low, high, reconciliation):
    target, metric, basis, unit, role = key
    return {"block": block, "target": target, "metric": metric, "basis": basis, "unit": unit,
            "low": round(low, 12), "high": None if high is None else round(high, 12), "kind": role,
            "table_kind": "RECONCILIATION" if reconciliation else "GUIDANCE",
            "source": {"table": table_i, "row": row_i, "columns": cols}}


def _review(queue, table_i, row_i, col, text, reason):
    queue.append({"table": table_i, "row": row_i, "column": col, "text": text, "reason": reason})


def _collect_row(table_i, row_i, grid, headers, numbers, scope, document, block, out, queue):
    row = grid[row_i]
    label_cells = [entry for col, entry in sorted(row.items()) if col < numbers[0][0]]
    labels = tuple(dict.fromkeys(cell.text for _, _, cell in label_cells if cell.text))
    label_text = " ".join(labels)
    if _NON_TOTAL.search(label_text):
        return
    reconciliation = bool(_RECONCILIATION.search(scope))
    pending = defaultdict(dict)
    for column, text in numbers:
        # A spanning numeric cell occurs once. Empty cells stay in the grid so
        # they cannot slide a later actual value under an earlier guidance head.
        heads = _header(headers, grid, column)
        heading = " ".join(heads)
        cell_context = _clean(f"{heading} {label_text}")
        if _NON_TOTAL.search(heading) or _HISTORICAL.search(cell_context):
            continue
        local_forward = bool(_FORWARD.search(cell_context))
        if not local_forward and (not _FORWARD.search(scope) or _HISTORICAL.search(scope)):
            continue
        row_metric, col_metric = _metric(label_text), _metric(heading)
        if row_metric and col_metric and row_metric != col_metric:
            _review(queue, table_i, row_i, column, text, "CONFLICTING_METRIC_AXES")
            continue
        metric = row_metric or col_metric
        if metric is None:
            continue
        roles = {_role(value) for value in (*labels, *heads)}
        # The prior leaf often sits under a parent labelled just "Guidance".
        # An explicit current marker on the other axis is a true conflict.
        if "PRIOR" in roles and _CURRENT.search(cell_context):
            _review(queue, table_i, row_i, column, text, "CONFLICTING_REVISION_ROLES")
            continue
        role = "PRIOR" if "PRIOR" in roles else "CURRENT"
        target, reason = _resolved_target((*labels, *heads), cell_context, scope, document)
        if reason:
            _review(queue, table_i, row_i, column, text, reason)
            continue
        bases = {_basis(value) for value in (*labels, *heads)} - {None}
        if len(bases) > 1:
            _review(queue, table_i, row_i, column, text, "CONFLICTING_ACCOUNTING_BASES")
            continue
        basis = next(iter(bases), None) or _basis(scope) or "unstated"
        if metric in _NON_GAAP_METRICS:
            if basis == "GAAP":
                _review(queue, table_i, row_i, column, text, "CONFLICTING_ACCOUNTING_BASES")
                continue
            basis = "non_GAAP"
        unit_axes = (label_text, heading, scope) if row_metric else (heading, label_text, scope)
        parsed = _numeric(text, metric, unit_axes)
        if parsed is None:
            _review(queue, table_i, row_i, column, text, "UNRESOLVED_NUMERIC_UNIT")
            continue
        metric, unit, low, high = parsed
        key = (target, metric, basis, unit, role)
        bound = _axis_bound(heads)
        if bound:
            if low != high or bound in pending[key]:
                pending[key][bound] = None
            else:
                pending[key][bound] = (column, low)
        else:
            out.append(_fact(table_i, row_i, [column], block, key, low, high, reconciliation))
    for key, bounds in pending.items():
        lo, hi = bounds.get("LOW"), bounds.get("HIGH")
        if lo is None or hi is None or lo[1] > hi[1]:
            _review(queue, table_i, row_i, lo[0] if lo else hi[0] if hi else None,
                    label_text, "MISSING_OR_CONFLICTING_RANGE_BOUND")
        else:
            out.append(_fact(table_i, row_i, [lo[0], hi[0]], block, key, lo[1], hi[1], reconciliation))


def _reconcile_facts(out, queue):
    families = defaultdict(dict)
    for value in out:
        key = tuple(value[field] for field in ("target", "metric", "basis", "unit", "kind"))
        bounds = value["low"], value["high"]
        if bounds not in families[key] or value["table_kind"] == "GUIDANCE":
            families[key][bounds] = value
    for by_bounds in families.values():
        versions = list(by_bounds.values())
        if len(versions) == 1:
            yield versions[0]
            continue
        direct = [value for value in versions if value["table_kind"] == "GUIDANCE"]
        # A reconciliation may show a scenario point from the published range.
        # Keep the published interval and preserve the reconciliation's location.
        if len(direct) == 1 and direct[0]["high"] is not None and direct[0]["low"] < direct[0]["high"]:
            main = direct[0]
            secondary = [value for value in versions if value is not main]
            if all(value["low"] == value["high"] and main["low"] <= value["low"] <= main["high"]
                   for value in secondary):
                yield {**main, "reconciliation_sources": [value["source"] for value in secondary]}
                continue
        for value in versions:
            source = value["source"]
            _review(queue, source["table"], source["row"], source["columns"][0],
                    f"{value['low']} – {value['high']}", "CONFLICTING_VALUES_FOR_TARGET")


def inspect(raw: bytes) -> dict:
    """Return table predictions and source-addressable manual review candidates.

The legacy block index is carried only when the normalized DOM row maps to one
unambiguous legacy block. The table/row/column address always comes from the DOM.
"""
    parser = _Document()
    parser.feed(raw.decode("utf-8", "replace"))
    parser.close()
    base_blocks = legacy_blocks.blocks(raw)
    document = baseline.doc_context(base_blocks)
    counts = Counter(value for kind, value in base_blocks if kind == "row")
    block_index = {value: index for index, (kind, value) in enumerate(base_blocks)
                   if kind == "row" and counts[value] == 1}
    out, queue = [], []
    for table_i, table in enumerate(parser.tables):
        scope = _scope(table)
        grid = _grid(table.rows)
        headers = []
        data_since_header = False
        for row_i, row in enumerate(grid):
            numbers = _value_columns(row, row_i)
            visible = _visible(row, row_i)
            if not numbers:
                if not visible:
                    continue
                if data_since_header and not any(cell.header for _, cell in visible) and not (
                        len(visible) == 1 and (_FORWARD.search(visible[0][1].text)
                                               or _HISTORICAL.search(visible[0][1].text))):
                    continue
                if data_since_header:
                    headers = []
                data_since_header = False
                headers.append(row_i)
                continue
            data_since_header = True
            legacy_row = " | ".join(legacy_blocks._merge([cell.text for _, cell in visible]))
            _collect_row(table_i, row_i, grid, headers, numbers, scope, document,
                         block_index.get(legacy_row), out, queue)

    return {"predictions": list(_reconcile_facts(out, queue)), "needs_review": queue}


def extract(raw: bytes) -> list[dict]:
    return inspect(raw)["predictions"]
