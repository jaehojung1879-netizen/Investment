"""Guidance extractor v2: structured (target, metric, basis, unit, low, high, kind) tuples from 8-K EX-99.

Handles the cases v1 (#383) missed: table rows with column roles (GAAP | non-GAAP, Prior | Current,
Forecast | Actual, Low | High), single values ("approximately $5.30"), open ranges ("$9.9+ billion"),
quarter vs fiscal-year targets with the year inferred from the release, and prior-outlook values quoted
next to the new ones ("from $6.09 - $6.40 to $5.65 - $5.85", "compared to a previous range of ...").
kind is CURRENT (issued or reaffirmed in this release) or PRIOR (quoted earlier outlook). Source-only:
reads filing text, never prices. Developed on gold-dev only; gold-test was frozen before this file existed.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import doc_blocks as B  # noqa: E402

ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4}
# Order matters: the first pattern that matches a label wins.
METRICS = [
    ("fcf_margin", r"free cash flow margin"),
    ("free_cash_flow", r"free cash flows?\b"),
    ("eps_growth", r"(eps|earnings per (diluted )?share) growth"),
    ("eps", r"\beps\b|earnings per (diluted |common )?share|(net income|earnings|net loss|net income \(loss\)) per (diluted |common )?share"
            r"|per diluted share|diluted (net )?(income|earnings|loss) per share|net income per share"),
    ("revenue_growth", r"(total |organic )?(revenue|sales) growth|growth in (total )?(revenue|sales)"),
    ("operating_margin", r"operating (profit |income )?margins?"),
    ("ebitda", r"\bebitda(re)?\b"),
    ("gross_margin", r"gross (profit )?margins?"),
    ("opex", r"(?<!non-)(?<!non)\boperating expenses\b"),
    ("operating_income", r"operating (income|profit|earnings)|income from operations"),
    ("capex", r"capital expenditures?|\bcapex\b|capital spending|purchases? of property(,)? (plant )?and equipment|property and equipment, net of proceeds"),
    ("tax_rate", r"(effective |adjusted effective |operating )?tax rate"),
    ("net_income", r"net (income|earnings)(?! per)(?! margin)"),
    ("revenue", r"\b(net |total )?(revenues?|net sales|sales)\b"),
]
NUM = r"\(?-?\$?\s?\(?\d[\d,]*(?:\.\d+)?\)?"
SCALE = r"(?:\s?(billion|million|thousand|bn|mm|b|m)\b)?"
PCT = r"(?:\s?(%|percent|per cent))"
RANGE = re.compile(
    rf"(?P<lo>{NUM}){SCALE}(?P<p1>{PCT})?\s*(?:to|-|–|—|and|through)\s*(?P<hi>{NUM})\s?(?P<s2>billion|million|thousand|bn|mm|b|m)?\b(?P<p2>{PCT})?",
    re.I)
PM = re.compile(rf"(?P<lo>{NUM}){SCALE}\s*(?:±|\+/-|plus or minus)\s*(?P<d>{NUM}){SCALE}", re.I)
POINT = re.compile(rf"(?P<lo>{NUM})(?P<plus>\+)?\s?(?P<s1>billion|million|thousand|bn|mm|b|m)?\b(?P<p1>{PCT})?", re.I)
FWD = re.compile(r"(?i)\b(expect\w*|anticipat\w*|project\w*|forecast\w*|guidance|outlook|target\w*|estimat\w*|plan\w*|will be|should be|range of|between)\b")
PAST = re.compile(r"(?i)\b(was|were|reported|grew|declined|delivered|achieved|generated|increased|decreased|totaled|came in|announced|exceeded|realized|repurchased|returned|ended)\b")
PRIOR_CUE = re.compile(r"(?i)(previous(ly)?|prior|original(ly)?|earlier|last|initial)\s+(announced\s+|issued\s+|provided\s+)?(guidance|outlook|range|forecast|targets?|expectations?)|compared (to|with) (our |its |the )?(previous|prior)|(up|down|lowered|raised|revised|changed|updated|increased|reduced) from|previously|prior to this")
NONGAAP = re.compile(r"(?i)non[- ]gaap|adjusted|\bcore\b|operating (eps|earnings per share)|excluding (specified|special|certain|non-recurring)|as adjusted|ongoing|comparable")
GAAP = re.compile(r"(?i)(?<!non-)(?<!non )\b(u\.s\. )?gaap\b|\breported\b")
DOC_NONGAAP = re.compile(r"(?i)guidance (is )?(provided |presented )?(is )?on an? (adjusted, )?non-gaap basis|provided on a non-gaap basis only|following guidance is provided on an adjusted")
QTR = re.compile(r"(?i)\b(first|second|third|fourth|1st|2nd|3rd|4th)[- ](fiscal[- ])?quarter(?: of)?(?: fiscal)?(?: year)?\s*(?:(20\d\d)|fy\s?'?(\d\d))?|\b([1-4])q\s?'?(\d\d)\b|\bq([1-4])\s?(?:fy)?\s?'?(20\d\d|\d\d)?\b")
YEAR = re.compile(r"(?i)\b(?:(?:full|fiscal)[- ]year|fiscal(?: year)?|calendar(?: year)?|fy)\s*'?(20\d\d|\d\d)\b|\b(20\d\d)\s*(?:full[- ]year|fiscal[- ]year|outlook|guidance|financial (targets|guidance|outlook)|forecast)|\bfy\s?(20\d\d|\d\d)\b|\b(20\d\d)\b")
HEADING = re.compile(r"(?i)\b(outlook|guidance|forecast|targets?)\b")
COL_CURRENT = re.compile(r"(?i)\b(current|updated|revised|new|forecast|guidance|outlook|target|expected|projected|anticipated|april|july|october)\b")
COL_PRIOR = re.compile(r"(?i)\b(prior|previous|original|initial|february|january)\b")
COL_ACTUAL = re.compile(r"(?i)\b(actual|ytd|year to date|results|six months|nine months|three months|twelve months|ended|reported|change|fx neutral|september|december|june|march)\b|\b(19|20)\d\d\b")


def _num(s):
    s = s.replace("$", "").replace(",", "").replace(" ", "")
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-") or s.startswith("(-")
    s = s.strip("()-")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def _scale(tok, default):
    t = (tok or "").lower()
    if t in ("billion", "bn", "b"):
        return 1000.0
    if t in ("million", "mm", "m"):
        return 1.0
    if t == "thousand":
        return 0.001
    return default


def _yy(s):
    if not s:
        return None
    return int(s) if len(s) == 4 else 2000 + int(s)


def metric_of(text):
    t = text.lower()
    for name, pat in METRICS:
        m = re.search(pat, t)
        if m:
            return name, m.start()
    return None, None


def basis_of(text, metric, default):
    if metric in ("ebitda", "free_cash_flow", "fcf_margin"):
        return "non_GAAP"   # definitionally non-GAAP measures
    if NONGAAP.search(text):
        return "non_GAAP"
    if GAAP.search(text):
        return "GAAP"
    if metric in ("revenue", "capex", "opex", "gross_profit") and default == "non_GAAP" and not DOC_DEFAULT_ALL:
        return "unstated"
    return default


DOC_DEFAULT_ALL = False   # set per document when the release declares every guided figure non-GAAP


def unit_for(metric, is_pct, value_text):
    if metric == "gross_margin" and not is_pct and "$" in value_text:
        return "gross_profit", "USD_million"
    if metric in ("eps",):
        return metric, "USD_per_share"
    if is_pct or metric in ("operating_margin", "gross_margin", "tax_rate", "revenue_growth", "eps_growth", "fcf_margin"):
        return metric, "pct"
    return metric, "USD_million"


def target_of(text, ctx):
    q = QTR.search(text)
    y = YEAR.search(text)
    if q:
        g = q.groups()
        n = ORD.get((g[0] or "").lower()) or (int(g[4]) if g[4] else int(g[6]) if g[6] else None)
        yr = _yy(g[2] or g[3] or g[5] or g[7]) or (_yy(next(x for x in y.groups() if x)) if y else None) or ctx.get("next_q_year", {}).get(n) or ctx.get("year")
        explicit = g[2] or g[3] or g[5] or g[7]
        if n and not explicit and n == ctx.get("report_q") and not re.search(r"(?i)\b(expect|guidance|outlook|forecast|project)", text[:q.start()]):
            return None   # the quarter just reported, not a forecast target
        if n and yr:
            return f"Q{n}FY{yr}"
    if y:
        yr = _yy(next(x for x in y.groups() if x))
        if yr and 2000 < yr < 2040:
            return f"FY{yr}"
    if re.search(r"(?i)\b(full[- ]year|fiscal year|for the year|annual)\b", text) and ctx.get("fy_default"):
        return f"FY{ctx['fy_default']}"
    return ctx.get("section_target")


def _values(seg, metric, allow_bare=False):
    """All value expressions in a text segment, in order: (lo, hi, is_pct, start, text)."""
    out, used = [], []
    for rx, kind in ((PM, "pm"), (RANGE, "range"), (POINT, "point")):
        for m in rx.finditer(seg):
            if any(a <= m.start() < b for a, b in used):
                continue
            txt = m.group(0)
            if kind == "pm":
                c, d = _num(m.group("lo")), _num(m.group("d"))
                sc = _scale(m.group(2), 1.0)
                if c is None or d is None:
                    continue
                lo, hi, pct = c * sc - d * _scale(m.group(4), sc), c * sc + d * _scale(m.group(4), sc), False
            elif kind == "range":
                lo, hi = _num(m.group("lo")), _num(m.group("hi"))
                if lo is None or hi is None:
                    continue
                pct = bool(m.group("p1") or m.group("p2"))
                s1 = _scale(m.group(2), None)
                s2 = _scale(m.group("s2"), None)
                sc1 = s1 if s1 is not None else (s2 if s2 is not None else 1.0)
                sc2 = s2 if s2 is not None else sc1
                if metric == "eps" or pct:
                    sc1 = sc2 = 1.0
                lo, hi = lo * sc1, hi * sc2
                if "$" not in txt and not pct and metric not in ("eps",) and s1 is None and s2 is None and max(abs(lo), abs(hi)) < 1:
                    continue
                if "$" not in txt and not pct and all(float(x).is_integer() and 1990 <= x <= 2040 for x in (lo, hi)):
                    continue
                if metric == "eps" and (s1 or s2):
                    continue
                if lo > hi:
                    lo, hi = hi, lo
            else:
                v = _num(m.group("lo"))
                if v is None:
                    continue
                pct = bool(m.group("p1"))
                if "$" not in txt and not pct and m.group("s1") is None and metric != "eps" and not allow_bare:
                    continue   # bare number without $, %, or scale: a count, a year or a footnote
                if re.fullmatch(r"20\d\d", m.group("lo").strip()):
                    continue
                if metric == "eps" and m.group("s1"):
                    continue
                sc = 1.0 if (metric == "eps" or pct) else _scale(m.group("s1"), 1.0)
                lo = v * sc
                hi = None if m.group("plus") else lo
            used.append((m.start(), m.end()))
            out.append((lo, hi, pct, m.start(), txt))
    return sorted(out, key=lambda x: x[3])


def _sentence_tuples(sent, ctx):
    """Pair each metric mention with the value expressions that follow it, until the next metric."""
    out = []
    low = sent.lower()
    spans = []
    for name, pat in METRICS:
        for m in re.finditer(pat, low):
            if any(a <= m.start() < b for a, b, _ in spans):
                continue
            spans.append((m.start(), m.end(), name))
    spans.sort()
    if not spans:
        return out
    for k, (a, b, name) in enumerate(spans):
        end = spans[k + 1][0] if k + 1 < len(spans) else len(sent)
        seg = sent[b:end]
        # a metric immediately followed by another metric (e.g. "revenue, EBITDA and EPS") inherits nothing
        vals = _values(seg, name)
        if not vals:
            pre = sent[(spans[k - 1][1] if k else 0):a]
            pv = _values(pre[-40:], name)
            if pv and FWD.search(sent):
                vals = [pv[-1][:3] + (0, pv[-1][4])]
                seg = pv[-1][4] + " " + seg
            else:
                continue
        qual = re.search(r"([\w\-]+)\s+$", sent[max(0, a - 30):a])
        if name in ("revenue", "operating_income", "operating_margin") and qual and re.search(r"-related$|^[A-Z][a-z]+$", qual.group(1)) \
                and qual.group(1).lower() not in ("total", "net", "organic", "reported", "consolidated", "company", "adjusted", "core", "the", "gaap", "annual", "quarterly", "full-year"):
            continue   # a segment, brand or product line, not the company
        pre_ctx = sent[max(0, a - 120):a]
        tgt = target_of(sent[max(0, a - 160):end], ctx) or ctx.get("block_target") or ctx.get("section_target")
        ctx["block_target"] = tgt
        if not tgt:
            continue
        first_val = vals[0][3]
        basis = basis_of(sent[max(0, a - 60):b + first_val], name, ctx["basis_default"])
        if re.search(r"(?i)\b(headwind|tailwind|impact|benefit|contribution|dilution|accretion)\b", sent[max(0, a - 50):a]):
            continue
        # "from X to Y": X is the prior outlook, Y the new one
        frm = re.search(r"(?i)\bfrom\b", seg)
        for j, (lo, hi, pct, st, txt) in enumerate(vals):
            before = seg[max(0, st - 70):st]
            kind = "CURRENT"
            if PRIOR_CUE.search(before):
                kind = "PRIOR"
            if frm and j == 0 and len(vals) >= 2 and frm.start() < st and re.search(r"(?i)\bto\b", seg[st + len(txt):vals[1][3]]):
                kind = "PRIOR"
            if j > 0 and kind == "CURRENT" and vals[0] is not None and re.search(r"(?i)\b(representing|reflecting|implying|or)\b", seg[vals[j - 1][3]:st]):
                if name == "eps" and pct:
                    m2, u2 = "eps_growth", "pct"
                    out.append((tgt, m2, basis, u2, lo, hi, kind))
                continue
            between = seg[vals[j - 1][3] + len(vals[j - 1][4]):st] if j > 0 else ""
            if j > 0 and kind == "CURRENT" and re.fullmatch(r"(?i)\s*(to|,? and now|, now)\s*", between):
                pass
            elif j > 0 and kind == "CURRENT" and (not re.fullmatch(r"(?i)[\s,]*(and|while|with)[\s\w]{0,25}", between)
                                                 or re.search(r"(?i)[A-Z]{2,}|guidance|outlook|\b(of|for)\b", between)):
                continue   # trailing numbers after the first value are usually assumptions (share counts, etc.)
            metric, unit = unit_for(name, pct, txt)
            if metric in ("eps",) and pct:
                continue
            if metric == "eps" and "$" not in txt and "." not in txt:
                continue
            if re.search(r"(?i)(excluding|including|related to|consisting of|of which)\s*~?$", seg[max(0, st - 25):st].strip()):
                continue
            if unit == "pct" and metric in ("revenue", "eps", "operating_income", "net_income", "capex", "opex", "ebitda", "free_cash_flow"):
                continue
            if PAST.search(pre_ctx[-40:] + seg[:max(0, st)]) and not FWD.search(sent) and not ctx.get("in_outlook"):
                continue
            out.append((tgt, metric, basis, unit, lo, hi, kind))
    return out


def _row_tuples(cells, ctx):
    label = cells[0]
    name, _ = metric_of(label)
    if not name or re.search(r"(?i)^(total )?(revenues|net sales)\s*:?$", label) and len(cells) > 3 and not ctx.get("in_outlook"):
        return []
    roles = ctx.get("col_roles")
    vals_cells = cells[1:]
    out = []
    tgt = target_of(label, ctx) or ctx.get("section_target")
    if not tgt:
        return []
    basis_label = basis_of(label, name, ctx["basis_default"])
    numeric = []
    vals_cells = [re.sub(r"(?i)\((excluding|including|related to|of which|incl\.|excl\.)[^)]*\)", "", c) for c in vals_cells]
    for ci, c in enumerate(vals_cells):
        vs = _values(c, name, allow_bare=bool(re.fullmatch(r"\(?-?[\d,]+(\.\d+)?\)?", c.strip())))
        if not vs:
            if re.search(r"(?i)unchanged|same", c):
                numeric.append((ci, "SAME", c))
            continue
        numeric.append((ci, vs[0], c))
    if not numeric:
        return []
    # Two bare numbers under a "Low | High" / "Guidance Range" header form one range.
    singles = [x for x in numeric if x[1] != "SAME" and x[1][1] is not None and x[1][0] == x[1][1]]
    no_roles = not roles or all(r is None for r in roles)
    if (ctx.get("range_cols") or (no_roles and len(singles) == 2)) and len(singles) >= 2 and len(numeric) == len(singles):
        lo_c, hi_c = singles[-2], singles[-1]
        lo, hi = sorted((lo_c[1][0], hi_c[1][0]))
        metric, unit = unit_for(name, lo_c[1][2], lo_c[2])
        return [(tgt, metric, basis_label, unit, lo * ctx.get("table_scale", 1.0) if unit == "USD_million" and "billion" not in lo_c[2].lower() and "$" not in lo_c[2] else lo,
                 hi * ctx.get("table_scale", 1.0) if unit == "USD_million" and "billion" not in hi_c[2].lower() and "$" not in hi_c[2] else hi, "CURRENT")]
    last_val = None
    for ci, v, c in numeric:
        role = roles[ci] if roles and ci < len(roles) else ("CURRENT" if len(numeric) == 1 else None)
        if role in (None, "ACTUAL"):
            continue
        basis = basis_label
        if role in ("GAAP", "non_GAAP"):
            if len(numeric) == 1:
                basis = basis_label   # one value under a GAAP | non-GAAP header applies to both bases
            else:
                basis = role if basis_label == "unstated" or basis_label == ctx["basis_default"] else basis_label
            role = "CURRENT"
        if v == "SAME":
            if last_val is None:
                continue
            v = last_val
        lo, hi, pct, _, txt = v
        last_val = v
        metric, unit = unit_for(name, pct, txt)
        if unit == "USD_million" and "$" not in txt and not re.search(r"(?i)billion|million", txt):
            lo = lo * ctx.get("table_scale", 1.0)
            hi = hi * ctx.get("table_scale", 1.0) if hi is not None else None
        out.append((tgt, metric, basis, unit, lo, hi, role))
    return out


def _header_roles(cells):
    roles = []
    for c in cells:
        if re.search(r"(?i)non[- ]gaap|adjusted", c):
            roles.append("non_GAAP")
        elif re.search(r"(?i)\bgaap\b", c):
            roles.append("GAAP")
        elif COL_PRIOR.search(c):
            roles.append("PRIOR")
        elif COL_ACTUAL.search(c) and not COL_CURRENT.search(c):
            roles.append("ACTUAL")
        elif COL_CURRENT.search(c):
            roles.append("CURRENT")
        elif re.fullmatch(r"(?i)(q[1-4]|[1-4]q)?[- ]?(fy)?'?\d{2,4}|full year \d{4}", c.strip()):
            roles.append("ACTUAL")
        else:
            roles.append(None)
    return roles


def _is_header(cells):
    """A table header names columns: no money, percent or decimal values, and its first cell is not a metric."""
    rest = " ".join(cells[1:])
    if len(cells) > 1 and metric_of(cells[0])[0]:
        return False
    if re.search(r"\$\s?\d|\d\s?%|\d\.\d|\d,\d{3}|\d\s?(billion|million)", rest + (" " + cells[0] if len(cells) == 1 else "")):
        return False
    return True


def doc_context(bl):
    head = " ".join(v for _, v in bl[:25])[:3000]
    ctx = {"basis_default": "unstated", "next_q_year": {}}
    m = re.search(r"(?i)\b(first|second|third|fourth)[- ]quarter(?: (?:of )?(?:fiscal )?(?:year )?(20\d\d))?(?: and full[- ]year)?(?: (?:fiscal )?(20\d\d))?\s+(?:financial )?results", head)
    yr = None
    if m:
        yr = _yy(m.group(2) or m.group(3))
        q = ORD[m.group(1).lower()]
        ctx["report_q"] = q
        if yr is None:
            y2 = re.search(r"\b(20\d\d)\b", head)
            yr = int(y2.group(1)) if y2 else None
        if yr:
            nq, ny = (q % 4) + 1, yr + (1 if q == 4 else 0)
            ctx["next_q_year"] = {nq: ny}
            for k in range(1, 5):
                ctx["next_q_year"].setdefault(k, ny if k >= nq else ny + 1)
            ctx["year"] = ny
            ctx["fy_default"] = yr + (1 if q == 4 else 0)
    return ctx


def extract(raw: bytes):
    global DOC_DEFAULT_ALL
    bl = B.blocks(raw)
    ctx = doc_context(bl)
    full = " ".join(v for _, v in bl)
    DOC_DEFAULT_ALL = bool(DOC_NONGAAP.search(full))
    if DOC_DEFAULT_ALL:
        ctx["basis_default"] = "non_GAAP"
    out = []
    ttl = 0
    for i, (k, v) in enumerate(bl):
        if B.BOILER.search(v):
            continue
        short = len(v) < 90
        if (short and HEADING.search(v) and "|" not in v and not re.search(r"\d", re.sub(r"\b(19|20)\d\d\b|\bfy\s?\d\d\b|\b[1-4]q\s?\d\d\b", "", v, flags=re.I))
                and not re.search(r"(?i)\b(reports?|announces?|results|today|said|delivered|exceeded|achieved|press release|conference call|webcast)\b", v)):
            ctx["in_outlook"] = True
            ttl = 30
            t = target_of(v, ctx)
            if t:
                ctx["section_target"] = t
            ctx["col_roles"] = None
            ctx["range_cols"] = bool(re.search(r"(?i)range", v))
            if re.search(r"(?i)non[- ]gaap basis|adjusted, non-gaap", v):
                ctx["basis_default"] = "non_GAAP"
            continue
        if ttl > 0:
            ttl -= 1
        else:
            ctx["in_outlook"] = False
            ctx["section_target"] = None
        if k == "row":
            cells = [c.strip() for c in v.split("|")]
            if cells and re.fullmatch(r"[•·o\-–●]", cells[0]):
                k, v = "p", " ".join(cells[1:])
                if len(v) < 90 and HEADING.search(v) and not re.search(r"\$\s?\d|\d\s?%", v):
                    t = target_of(v, ctx)
                    if t:
                        ctx["section_target"] = t
                    ctx["in_outlook"] = True
                    ttl = 30
                    continue
            elif _is_header(cells):
                # header row: column roles, scale, target
                if re.search(r"(?i)in millions|\$ in millions|\(millions", v):
                    ctx["table_scale"] = 1.0
                if re.search(r"(?i)in thousands", v):
                    ctx["table_scale"] = 0.001
                roles = _header_roles(cells)
                if len(cells) > 1 and all(r == "ACTUAL" for r in roles if r is not None) and any(roles):
                    ctx["in_outlook"] = False      # a results table: its columns are periods already reported
                    ctx["section_target"] = None
                    ttl = 0
                if len(cells) == 1:
                    roles = [None]
                if any(roles):
                    # header rows usually lack the label cell
                    ctx["col_roles"] = roles if len(cells) and roles[0] is not None else roles[1:] if roles and roles[0] is None and len(cells) > 1 else roles
                    if roles and roles[0] is not None:
                        ctx["col_roles"] = roles
                ctx["range_cols"] = bool(re.search(r"(?i)\brange\b|\blow\b.*\bhigh\b", v)) or ctx.get("range_cols", False)
                t = target_of(v, ctx)
                if t and HEADING.search(v):
                    ctx["section_target"] = t
                    ctx["in_outlook"] = True
                    ttl = 30
                    if len(cells) == 1:
                        ctx["col_roles"] = None
                continue
            else:
                if ctx.get("in_outlook") or FWD.search(cells[0]):
                    for tup in _row_tuples(cells, ctx):
                        out.append((i, *tup))
                continue
        if not re.search(r"\d", v):
            continue
        ctx["block_target"] = None
        for sent in re.split(r"(?<=[.;])\s+(?=[A-Z•\(])", v):
            if not (FWD.search(sent) or (ctx.get("in_outlook") and len(sent) < 220)):
                continue
            if PAST.search(sent) and not FWD.search(sent):
                continue
            if re.search(r"(?i)does not (include|reflect|assume)|\bexclud(es|ing) the (impact|effect)|not included in", sent):
                continue
            for tup in _sentence_tuples(sent, ctx):
                out.append((i, *tup))
    # The same figure stated once with an explicit basis and once without: keep the explicit one.
    explicit = {(t, m, u, round(lo, 6), None if hi is None else round(hi, 6), kd)
                for _, t, m, bs, u, lo, hi, kd in out if bs != "unstated"}
    out = [x for x in out if not (x[3] == "unstated" and (x[1], x[2], x[4], round(x[5], 6), None if x[6] is None else round(x[6], 6), x[7]) in explicit)]
    seen, res = set(), []
    out = [(i, t, m, bs, u, abs(lo) if m == "capex" else lo, (abs(hi) if hi is not None else None) if m == "capex" else hi, kd) for i, t, m, bs, u, lo, hi, kd in out]
    out = [(i, t, m, bs, u, min(lo, hi) if hi is not None else lo, max(lo, hi) if hi is not None else None, kd) for i, t, m, bs, u, lo, hi, kd in out]
    for i, tgt, metric, basis, unit, lo, hi, kind in out:
        key = (tgt, metric, basis, unit, round(lo, 6), None if hi is None else round(hi, 6), kind)
        if key in seen:
            continue
        seen.add(key)
        res.append({"block": i, "target": tgt, "metric": metric, "basis": basis, "unit": unit,
                    "low": lo, "high": hi, "kind": kind})
    return res
