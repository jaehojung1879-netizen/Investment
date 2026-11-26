"""Table-aware block segmentation of SEC HTML exhibits (stdlib only).

A block is a paragraph or ONE table row whose cells are joined with " | ", so table
structure (metric | low | high) survives the flattening that guidance_detect.text() loses."""
import html as _html
import re
from html.parser import HTMLParser

BREAK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "title"}
CELL = {"td", "th"}


class _P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.buf, self.row, self.cell, self.skip, self.depth = [], [], None, None, 0, 0

    def _flush(self):
        t = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if t:
            self.blocks.append(("p", t))
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "table":
            self._flush(); self.depth += 1
        elif tag == "tr":
            self._flush(); self.row = []
        elif tag in CELL and self.row is not None:
            self.cell = []
        elif tag in BREAK and self.row is None:
            self._flush()

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in CELL and self.row is not None and self.cell is not None:
            c = re.sub(r"\s+", " ", "".join(self.cell)).strip()
            if c:
                self.row.append(c)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            cells = _merge(self.row)
            if cells:
                self.blocks.append(("row", " | ".join(cells)))
            self.row = None
        elif tag == "table":
            self.depth = max(0, self.depth - 1)
        elif tag in BREAK and self.row is None:
            self._flush()

    def handle_data(self, d):
        if self.skip:
            return
        if self.cell is not None:
            self.cell.append(d)
        elif self.row is None:
            self.buf.append(d)

    def close(self):
        super().close(); self._flush()


def _merge(cells):
    """EDGAR splits '$' and ')' / '%' into their own cells; glue them to the number."""
    out = []
    for c in cells:
        if out and (out[-1] in ("$", "(", "($") or c in ("%", ")", "%)", ")%")):
            out[-1] = (out[-1] + c).replace("$ ", "$")
        else:
            out.append(c)
    return out


def blocks(raw: bytes):
    t = raw.decode("utf-8", "replace")
    if "<" not in t[:2000]:   # plain-text exhibit
        return [("p", re.sub(r"\s+", " ", x).strip()) for x in re.split(r"\n\s*\n", t) if x.strip()]
    p = _P()
    p.feed(t); p.close()
    return [(k, _html.unescape(v)) for k, v in p.blocks]


FWD = re.compile(r"(?i)\b(outlook|guidance|expect\w*|anticipat\w*|forecast\w*|project(s|ed|ing)?|target\w*|estimat\w*|plan(s|ned)? to|intend\w*|continu\w+ to (see|believe))\b")
BOILER = re.compile(r"(?i)forward[- ]looking statements|words such as|safe harbor|private securities litigation|risk factors|undue reliance")


def candidates(raw: bytes):
    """Annotation universe: deliberately broader than any extractor.
    Every paragraph with a forward cue and a digit, and every table row of a table
    (or the 25 rows after a block) whose heading mentions outlook/guidance."""
    bl = blocks(raw); out = []; heading_until = -1
    for i, (k, v) in enumerate(bl):
        if re.search(r"(?i)\b(outlook|guidance)\b", v) and not BOILER.search(v) and len(v) < 400:
            heading_until = i + 25
        has_digit = bool(re.search(r"\d", v))
        if not has_digit or BOILER.search(v):
            continue
        if FWD.search(v) or i <= heading_until:
            out.append((i, k, v))
    return bl, out
