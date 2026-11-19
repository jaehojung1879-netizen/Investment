"""Pure functions for the KR preliminary-earnings source-eligibility audit.

Nothing here reads a price, return, label or model output. Every function is
deterministic and network-free so it can be tested on invented rows.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import date

PRELIM, PNL_CHANGE, GUIDANCE, FORMAL, OTHER = "PRELIM", "PNL_CHANGE", "GUIDANCE", "FORMAL", "OTHER"
_FORMAL_RE = re.compile(r"^(분기보고서|반기보고서|사업보고서)\s*\((\d{4})\.(\d{2})\)")


def parse_ymd(value: str) -> date:
    value = value.replace("-", "")
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def is_amendment(report_nm: str) -> bool:
    """Any bracketed DART prefix ([기재정정], [첨부정정], ...) marks a non-original filing."""
    return report_nm.strip().startswith("[")


def strip_markers(report_nm: str) -> str:
    return re.sub(r"^(\[[^\]]*\])+", "", report_nm.strip()).strip()


def classify(report_nm: str) -> str:
    """Exact report-name patterns only; nothing is inferred from content."""
    name = strip_markers(report_nm)
    if "영업(잠정)실적" in name:
        return PRELIM
    if "매출액또는손익구조" in name:
        return PNL_CHANGE
    if "영업실적등에대한전망" in name:
        return GUIDANCE
    if _FORMAL_RE.match(name):
        return FORMAL
    return OTHER


def quarter_end(year: int, month: int) -> date:
    day = {3: 31, 6: 30, 9: 30, 12: 31}[month]
    return date(year, month, day)


def formal_period(report_nm: str) -> date | None:
    match = _FORMAL_RE.match(strip_markers(report_nm))
    if not match:
        return None
    year, month = int(match.group(2)), int(match.group(3))
    if month not in (3, 6, 9, 12):
        return None
    return quarter_end(year, month)


def previous_quarter_end(receipt: date) -> date:
    """Latest calendar quarter end strictly before ``receipt``."""
    year = receipt.year
    candidates = [quarter_end(y, m) for y in (year - 1, year) for m in (3, 6, 9, 12)]
    return max(c for c in candidates if c < receipt)


def quarters_between(first: date, last: date) -> list[date]:
    out, year = [], first.year
    while True:
        for month in (3, 6, 9, 12):
            q = quarter_end(year, month)
            if q > last:
                return out
            if q >= first:
                out.append(q)
        year += 1


def member_quarters(snapshots: list[dict], quarters: list[date], *, top_rank: int = 120) -> dict[date, set[str]]:
    """Stock codes inside the top ``top_rank`` at the first snapshot strictly after each quarter end."""
    by_date: dict[date, set[str]] = defaultdict(set)
    for row in snapshots:
        rank = row.get("rank")
        if rank is not None and int(rank) <= top_rank:
            by_date[parse_ymd(row["date"])].add(row["code"])
    dates = sorted(by_date)
    out = {}
    for q in quarters:
        later = [d for d in dates if d > q]
        if later:
            out[q] = by_date[later[0]]
    return out


def first_originals(rows: list[dict]) -> dict[tuple[str, date], dict]:
    """Earliest original (non-amendment) disclosure per (family, quarter)."""
    best: dict[tuple[str, date], dict] = {}
    for row in rows:
        if is_amendment(row["report_nm"]):
            continue
        family = classify(row["report_nm"])
        if family == OTHER:
            continue
        receipt = parse_ymd(row["rcept_dt"])
        quarter = formal_period(row["report_nm"]) if family == FORMAL else previous_quarter_end(receipt)
        if quarter is None:
            continue
        key = (family, quarter)
        if key not in best or (row["rcept_dt"], row["rcept_no"]) < (best[key]["rcept_dt"], best[key]["rcept_no"]):
            best[key] = row
    return best


def confirmed_prelims(rows: list[dict], parses: dict[str, dict]) -> dict[date, dict]:
    """Earliest original PRELIM per quarter whose own table states that quarter's earnings.

    A filing on the PRELIM form that states only monthly operating data, or leaves every
    earnings cell blank, is not an earnings disclosure and is not counted."""
    best: dict[date, dict] = {}
    for row in rows:
        if is_amendment(row["report_nm"]) or classify(row["report_nm"]) != PRELIM:
            continue
        parsed = parses.get(row["rcept_no"])
        quarter = stated_quarter(parsed) if parsed else None
        if quarter is None:
            continue
        if quarter not in best or (row["rcept_dt"], row["rcept_no"]) < (best[quarter]["rcept_dt"], best[quarter]["rcept_no"]):
            best[quarter] = row
    return best


def session_count_between(sessions: list[date], start: date, end: date) -> int:
    """Number of sessions s with start < s <= end (negative when end < start)."""
    if end >= start:
        return sum(1 for s in sessions if start < s <= end)
    return -sum(1 for s in sessions if end < s <= start)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def coverage_table(member: dict[date, set[str]], code_to_corp: dict[str, str],
                   firsts_by_corp: dict[str, dict], sessions: list[date],
                   collected: set[str] | None = None) -> dict:
    """Per member issuer-quarter: does a PRELIM precede (or tie) the formal report, and by how much."""
    units = []
    unresolved = Counter()
    uncollected = Counter()
    for quarter, codes in sorted(member.items()):
        corps = set()
        for code in codes:
            corp = code_to_corp.get(code)
            if corp is None:
                unresolved[quarter.year] += 1
                continue
            corps.add(corp)
        for corp in sorted(corps):
            if collected is not None and corp not in collected:
                uncollected[quarter.year] += 1  # collection failed: not counted as an absent disclosure
                continue
            firsts = firsts_by_corp.get(corp, {})
            prelim = firsts.get((PRELIM, quarter))
            formal = firsts.get((FORMAL, quarter))
            pnl = firsts.get((PNL_CHANGE, quarter))
            unit = {"corp": corp, "quarter": quarter.isoformat(), "year": quarter.year,
                    "fiscalQuarterMonth": quarter.month, "hasPrelim": prelim is not None,
                    "hasFormal": formal is not None, "hasPnlChange": pnl is not None}
            if prelim and formal:
                p, f = parse_ymd(prelim["rcept_dt"]), parse_ymd(formal["rcept_dt"])
                unit["leadCalendarDays"] = (f - p).days
                unit["leadSessions"] = session_count_between(sessions, p, f)
                unit["prelimNotAfterFormal"] = p <= f
            elif prelim:
                unit["prelimNotAfterFormal"] = None
            else:
                unit["prelimNotAfterFormal"] = False
            if prelim:
                unit["prelimLagFromQuarterEndDays"] = (parse_ymd(prelim["rcept_dt"]) - quarter).days
            if formal:
                unit["formalLagFromQuarterEndDays"] = (parse_ymd(formal["rcept_dt"]) - quarter).days
            units.append(unit)
    return {"units": units, "unresolvedMemberSecuritiesByYear": dict(sorted(unresolved.items())),
            "uncollectedIssuerQuartersByYear": dict(sorted(uncollected.items()))}


def summarize(units: list[dict]) -> dict:
    def block(rows):
        n = len(rows)
        timely = sum(1 for r in rows if r.get("prelimNotAfterFormal") is True)
        anyp = sum(1 for r in rows if r["hasPrelim"])
        leads = [r["leadSessions"] for r in rows if r.get("prelimNotAfterFormal") is True]
        cal = [r["leadCalendarDays"] for r in rows if r.get("prelimNotAfterFormal") is True]
        return {
            "memberIssuerQuarters": n,
            "withPrelimAny": anyp,
            "withPrelimNotAfterFormal": timely,
            "coveragePct": round(100 * timely / n, 2) if n else None,
            "withFormal": sum(1 for r in rows if r["hasFormal"]),
            "withPnlChange": sum(1 for r in rows if r["hasPnlChange"]),
            "leadSessionsMedian": percentile(leads, 0.5),
            "leadSessionsP25": percentile(leads, 0.25),
            "leadSessionsP75": percentile(leads, 0.75),
            "leadCalendarDaysMedian": percentile(cal, 0.5),
            "sameDayOrLeadLe5Sessions": sum(1 for x in leads if x <= 5),
        }
    by_year = defaultdict(list)
    by_month = defaultdict(list)
    for r in units:
        by_year[r["year"]].append(r)
        by_month[r["fiscalQuarterMonth"]].append(r)
    return {"overall": block(units),
            "byYear": {str(y): block(rows) for y, rows in sorted(by_year.items())},
            "byQuarterEndMonth": {str(m): block(rows) for m, rows in sorted(by_month.items())}}


# --------------------------------------------------------------------------- document parsing
_UNIT_RE = re.compile(r"단위\s*:\s*(조원|억원|백만원|천원|원)")
UNIT_SCALE = {"조원": 1e12, "억원": 1e8, "백만원": 1e6, "천원": 1e3, "원": 1.0}
ITEMS = {
    "revenue": ("매출액", "영업수익", "수익\\(매출액\\)", "순영업수익", "보험영업수익"),
    "operatingIncome": ("영업이익",),
    "netIncome": ("당기순이익",),
}


def html_to_text(markup: str) -> str:
    text = re.sub(r"(?is)<style.*?</style>", " ", markup)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text)


def table_region(text: str) -> str:
    """The first results table: from the provisional-figures notice to the information-provision block."""
    start = text.find("잠정치")
    start = text.find("영업(잠정)실적") if start < 0 else start
    end = text.find("정보제공내역", max(start, 0))
    if start < 0:
        return text[:2500]
    return text[start:end if end > start else start + 2500]


def _number(token: str) -> float | None:
    token = token.strip().replace(",", "").rstrip("%")
    if token in ("", "-", "--"):
        return None
    negative = (token.startswith("(") and token.endswith(")")) or token.startswith("△") or token.startswith("-")
    token = token.strip("()△-")
    try:
        value = float(token)
    except ValueError:
        return None
    return -value if negative else value


def _year(token: str) -> int:
    value = int(token.lstrip("'’`"))
    return 2000 + value if value < 100 else value


_Y = r"(['’`]?\d{4}|['’`]?\d{2})"
_PERIOD_PATTERNS = (
    ("RANGE", re.compile(_Y + r"\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*~\s*" + _Y + r"\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})")),
    ("RANGE_SAME_YEAR", re.compile(_Y + r"\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*~\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})(?!\s*[.\-/]\s*\d)")),
    ("QUARTER", re.compile(_Y + r"\s*(?:년도?|\.|-|Y)?\s*(?:제\s*)?([1-4])\s*(?:/\s*4\s*)?(?:분기|Q)", re.IGNORECASE)),
    ("QUARTER_Q_FIRST", re.compile(_Y + r"\s*[.\-]?\s*Q\s*([1-4])", re.IGNORECASE)),
    ("QUARTER_FY", re.compile(r"FY\s*" + _Y + r"\s*[.\s]*([1-4])\s*(?:분기|Q)", re.IGNORECASE)),
    ("QUARTER_PREFIX", re.compile(r"([1-4])\s*Q\s*" + _Y, re.IGNORECASE)),
    ("ANNUAL", re.compile(_Y + r"\s*(?:년도?|\.)?\s*(?:연간|년간|결산|누적|사업연도|연도|FY)")),
    ("HALF", re.compile(_Y + r"\s*(?:년도?|\.)?\s*(?:상)?반기")),
    ("MONTH", re.compile(_Y + r"\s*(?:년|\.)\s*(\d{1,2})\s*월")),
    ("MONTH_DOT", re.compile(r"\(\s*" + _Y + r"\s*\.\s*(\d{2})\s*\)")),
)


def _period_from_match(kind: str, match: re.Match) -> tuple[int, str, int] | None:
    g = match.groups()
    if kind == "RANGE":
        y1, m1, y2, m2 = _year(g[0]), int(g[1]), _year(g[3]), int(g[4])
        span = (y2 * 12 + m2) - (y1 * 12 + m1) + 1
        label = {1: "MONTH", 3: "QUARTER", 6: "HALF", 9: "YTD9", 12: "ANNUAL"}.get(span)
        return (y2, label, m2) if label and 1 <= m2 <= 12 else None
    if kind == "RANGE_SAME_YEAR":
        y, m1, m2 = _year(g[0]), int(g[1]), int(g[3])
        span = m2 - m1 + 1
        label = {1: "MONTH", 3: "QUARTER", 6: "HALF", 9: "YTD9", 12: "ANNUAL"}.get(span)
        return (y, label, m2) if label and 1 <= m2 <= 12 else None
    if kind in ("QUARTER", "QUARTER_FY", "QUARTER_Q_FIRST"):
        return (_year(g[0]), "QUARTER", 3 * int(g[1]))
    if kind == "QUARTER_PREFIX":
        return (_year(g[1]), "QUARTER", 3 * int(g[0]))
    if kind == "ANNUAL":
        return (_year(g[0]), "ANNUAL", 12)
    if kind == "HALF":
        return (_year(g[0]), "HALF", 6)
    month = int(g[1])
    return (_year(g[0]), "MONTH", month) if 1 <= month <= 12 else None


def period_tokens(descriptor: str) -> list[tuple[int, str, int]]:
    """Every period stated in a column-header descriptor, left to right, overlaps resolved
    in favour of the earliest and then the longest match."""
    found = []
    for kind, pattern in _PERIOD_PATTERNS:
        for match in pattern.finditer(descriptor):
            period = _period_from_match(kind, match)
            if period:
                found.append((match.start(), -(match.end() - match.start()), match.end(), period))
    found.sort()
    out, cursor = [], -1
    for start, _, finish, period in found:
        if start >= cursor:
            out.append(period)
            cursor = finish
    return out


def normalize_period(label: str) -> tuple[int, str, int] | None:
    """One header label -> (year, kind, period-end month); kind QUARTER/ANNUAL/HALF/MONTH/YTD9."""
    if not label or not label.strip():
        return None
    tokens = period_tokens("(" + label.strip() + ")")
    return tokens[0] if tokens else None


def parse_prelim_text(text: str) -> dict:
    """Read current and prior-year figures from the standard 영업(잠정)실적 table.

    Returns ``None`` for any figure the filer left blank ("-") or that cannot be read."""
    region = table_region(text)
    out: dict = {"unit": None, "periodLabel": None, "periodKind": None, "periodYear": None,
                 "periodEndMonth": None, "consolidated": "연결재무제표 기준" in region[:200]
                 or "연결실적" in region[:400] or "연결재무제표기준" in text[:3000]}
    unit = _UNIT_RE.search(region)
    if unit:
        out["unit"] = unit.group(1)
    header_at = region.find("전년동기대비")
    header_at = header_at if header_at >= 0 else 0
    first_item = re.search(r"(매출액|영업수익|영업이익|당해실적)", region[header_at:])
    descriptor = region[header_at:header_at + (first_item.start() if first_item else 200)]
    raw_tokens = period_tokens(descriptor)
    tokens = [t for i, t in enumerate(raw_tokens) if i == 0 or t != raw_tokens[i - 1]]  # label + its date range
    period = tokens[0] if tokens else None
    previous = tokens[1] if len(tokens) > 1 else None
    out["periodLabel"] = descriptor.replace("전년동기대비증감율(%)", "").strip()[:80] or None
    if period:
        out["periodYear"], out["periodKind"], out["periodEndMonth"] = period
    scale = UNIT_SCALE.get(out["unit"]) if out["unit"] else None
    # Since 2025 the form adds a 흑자적자전환여부 (sign-turn) column after each change column:
    # current, previous, change, turn, prior-year, change, turn. Before: current, previous, change, prior-year, change.
    seven_columns = "흑자적자전환" in descriptor
    out["layout"] = "SEVEN_COLUMN_WITH_SIGN_TURN" if seven_columns else "FIVE_COLUMN"
    prior_group = 5 if seven_columns else 4
    for field, labels_for_item in ITEMS.items():
        current = prior_year = None
        for item in labels_for_item:
            pattern = re.compile(item + r"\s*(?:\([^)]*\)\s*)?당해실적\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)")
            match = pattern.search(region)
            if not match:
                continue
            current, prior_year = _number(match.group(1)), _number(match.group(prior_group))
            if (prior_year is None and period and previous and period[1] == "ANNUAL"
                    and previous[1] == "ANNUAL" and previous[0] == period[0] - 1):
                prior_year = _number(match.group(2))  # annual form states the prior year in the 전기 column
            break
        out[field] = current * scale if (current is not None and scale) else None
        out[field + "PriorYear"] = prior_year * scale if (prior_year is not None and scale) else None
    out["earningsStated"] = out["periodKind"] in ("QUARTER", "ANNUAL", "HALF") and (
        out["revenue"] is not None or out["operatingIncome"] is not None)
    return out


def stated_quarter(parsed: dict) -> date | None:
    if not parsed.get("earningsStated") or not parsed.get("periodYear"):
        return None
    if parsed.get("periodEndMonth") not in (3, 6, 9, 12):
        return None
    return quarter_end(parsed["periodYear"], parsed["periodEndMonth"])


def period_label_quarter(label: str | None) -> tuple[int, int] | None:
    period = normalize_period(label) if label else None
    if not period or period[1] == "MONTH":
        return None
    return (period[0], period[2])


# --------------------------------------------------------------------------- minimum effective sample
def mde(sigma: float, n_tercile: int, rho: float, cohorts: float, z_alpha: float = 1.959964, z_power: float = 0.841621) -> float | None:
    """Minimum detectable top-minus-bottom tercile mean difference.

    Two independent tercile means of ``n_tercile`` names, equicorrelation ``rho``
    inside a tercile, averaged over ``cohorts`` independent (non-overlapping) cohorts."""
    if cohorts <= 0 or n_tercile <= 1:
        return None
    se_one = sigma * math.sqrt(2.0 / n_tercile) * math.sqrt(1 + (n_tercile - 1) * rho)
    return (z_alpha + z_power) * se_one / math.sqrt(cohorts)


def cohorts_needed(sigma: float, n_tercile: int, rho: float, target: float) -> float:
    single = mde(sigma, n_tercile, rho, 1.0)
    return (single / target) ** 2


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation with average ranks for ties; None below three pairs or with no variance."""
    if len(xs) < 3:
        return None

    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2.0
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return sxy / (sxx * syy) ** 0.5
