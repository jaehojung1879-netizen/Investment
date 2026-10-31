"""Table-form KSIC statements and group-affiliate self rows in retained annual originals: candidates, never admissions.

SOURCE-ONLY. No network, price, return, label or outcome. Reads the public-viewer annual originals the industry
foundation v2 retained (`kr22_repository_originals.load_v2`, every archive and blob re-hashed) for EVERY ever-Top120
issuer, not only the 22 terminated securities, so any rule built on these candidates is measured on the same population
it would be applied to.

Why the frozen v2 template misses these. `scripts/build_kr_industry_membership_v2.CLASSIFICATION` requires an
issuer-subject sentence ("당사는 ... 한국표준산업분류 ... 에 해당") and then a quoted or "에 의한 ... 업" assignment.
A filing that states its classification as a heading line plus a hierarchy table

    (나) 공시대상 사업부문의 구분
    한국표준산업분류 : 응용 소프트웨어 개발 및 공급업 (J58222)
    | 대분류 | 중분류 | 소분류 | 세분류 | 세세분류 |
    | J ...  | 58 ... | 582 ...| 5822 ...| 58222 ... |

has no issuer subject and no assignment verb, so the template cannot match it by construction. Separately, the frozen
v4 crosswalk is keyed by KIND labels, which sit at the KSIC 3-digit (소분류) level; a filing that reports a 5-digit
label is UNKNOWN there unless its own 3-digit row is read.

Two extractors, both with fixed objective criteria and no company-, label- or ticker-specific rule:

* TABLE_FORM_KSIC: a `한국표준산업분류 : <label> (<code>)` line followed, with no other table in between, by a table
  whose header is the level sequence 대분류/중분류/소분류[/세분류[/세세분류]] and whose single body row states
  `<code> <label>` per level. Accepted as internally consistent only if the section letter equals the code's letter,
  each level's digits are the stated code's 2/3/4/5-digit prefix, and the deepest cell equals the stated code and
  label. The 3-digit row's label is looked up EXACTLY in the frozen crosswalk. A filing with more than one statement is
  MULTI_STATEMENT and yields no single-issuer candidate.
* AFFILIATE_SELF_ROW: a group-affiliate table (header has a company-name column and an 업종 column) in `회사의 개요`
  whose name cell equals the filing's own legal name as the same filing states it (`명칭은 '...'`). The 업종 cell is
  free text written for the group table, not a KSIC statement; it is looked up exactly and otherwise stays UNKNOWN.

The KSIC codebook is NOT retained in the repository (v2 `globalTaxonomyEvidence`: fetch 502, effective-date transition
not established), so the hierarchy check is internal to each filing (stated codes and labels agree with each other),
never a check against the official codebook. Every candidate is also passed, unchanged, through
`kr_industry_membership_v2.admit` with a locator that is the exact statement bytes (unique in the source), and compared
with the v4 KIND interval for the same security on the receipt date where v4 has one. Nothing is admitted; the frozen
template and crosswalk are unchanged; the rule change these candidates would need is `industry-admission-rule-proposal.md`.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

from pipeline import kr_industry_membership_v2 as V
from pipeline import kr_industry_membership_v4 as V4

from . import kr22_recovery as K
from . import kr22_repository_originals as R

HERE = Path(__file__).resolve().parent
REPORT = HERE / "kr22-table-ksic-candidates.json"
V4_INTERVALS = Path("data/kr-industry-membership-foundation-v4/state/intervals.json.gz")
CONTRACT = "KR22_TABLE_KSIC_AND_AFFILIATE_SELF_ROW_CANDIDATES_V1"
LEVELS = ("대분류", "중분류", "소분류", "세분류", "세세분류")
DIGITS_AT = {"중분류": 2, "소분류": 3, "세분류": 4, "세세분류": 5}
STATEMENT = re.compile(r"한국표준산업분류\s*[:：]\s*(?P<label>[^()<>]{2,80}?)\s*\(\s*(?P<code>[A-U]\s*\d{2,5})\s*\)")
TABLE = re.compile(r"<TABLE\b.*?</TABLE>", re.S | re.I)
ROW = re.compile(r"<TR\b.*?</TR>", re.S | re.I)
CELL = re.compile(r"<T([HD])\b[^>]*>(.*?)</T[HD]>", re.S | re.I)
LEGAL_NAME = re.compile(r"명칭은\s*(?:[\"'‘“]\s*(?P<quoted>[^\"'’”]{2,60}?)\s*[\"'’”]|"
                        r"(?P<bare>(?:주식회사\s*)?\S{2,30}?(?:\s*주식회사)?)\s*(?:이라고|라고|이고|이며|입니다))")


def norm(text):
    return "".join((text or "").split())


def cell_text(fragment):
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", fragment)).split())


def company_key(name):
    """Legal-form markers and whitespace removed; nothing else (no fuzzy or prefix matching)."""
    return re.sub(r"\(주\)|㈜|주식회사|\(株\)", "", norm(name))


def table_rows(table_html):
    return [[(kind.upper(), cell_text(body)) for kind, body in CELL.findall(row)] for row in ROW.findall(table_html)]


def parse_statements(body):
    """Every table-form KSIC statement in one section: the stated line, the next table, and its consistency checks."""
    out = []
    for m in STATEMENT.finditer(body):
        code = norm(m["code"])
        label = norm(html.unescape(m["label"]))
        nxt = TABLE.search(body, m.end())
        gap = body[m.end():nxt.start()] if nxt else ""
        rec = {"statedCode": code, "statedLabel": label, "statedLevelDigits": len(code) - 1, "levels": [],
               "checks": {}, "locator": None}
        if nxt and "<TABLE" not in gap.upper() and len(cell_text(gap)) <= 40:
            rows = table_rows(nxt.group(0))
            header = [t for k, t in rows[0]] if rows else []
            body_rows = [r for r in rows[1:] if r]
            if header and [norm(h) for h in header] == list(LEVELS[:len(header)]) and len(header) >= 3:
                rec["locator"] = body[m.start():nxt.end()]
                cells = [t for _, t in body_rows[0]] if len(body_rows) == 1 else []
                for name, text in zip(header, cells):
                    cm = re.match(r"^([A-U]|\d{2,5})\s+(.+)$", text)
                    rec["levels"].append({"level": norm(name), "code": cm[1] if cm else None,
                                          "label": norm(cm[2]) if cm else norm(text)})
                rec["checks"] = consistency(rec, header, len(body_rows))
        if not rec["checks"]:
            rec["checks"] = {"hierarchyTableFollows": False}
        out.append(rec)
    return out


def consistency(rec, header, n_body_rows):
    code, levels = rec["statedCode"], rec["levels"]
    letter, digits = code[0], code[1:]
    by = {lv["level"]: lv for lv in levels}
    checks = {"hierarchyTableFollows": True, "singleBodyRow": n_body_rows == 1,
              "allCellsParsed": len(levels) == len(header) and all(lv["code"] for lv in levels),
              "sectionLetterMatches": by.get("대분류", {}).get("code") == letter}
    checks["levelCodesArePrefixesOfStatedCode"] = all(
        lv["code"] == digits[:DIGITS_AT[lv["level"]]] and len(digits) >= DIGITS_AT[lv["level"]]
        for lv in levels if lv["level"] in DIGITS_AT)
    deepest = levels[-1] if levels else {}
    checks["deepestCellEqualsStatement"] = deepest.get("code") == digits and deepest.get("label") == rec["statedLabel"]
    checks["threeDigitRowStated"] = "소분류" in by
    checks["consistent"] = all(checks.values())
    return checks


def affiliate_self_rows(overview_html):
    """Rows of company_overview affiliate tables whose name cell IS the filing's own stated legal name."""
    text = cell_text(overview_html)
    nm = LEGAL_NAME.search(text)
    if not nm:
        return {"legalName": None, "rows": [], "tables": 0}
    stated = nm["quoted"] or nm["bare"]
    own = company_key(stated)
    found, tables = [], 0
    for t in TABLE.finditer(overview_html):
        rows = table_rows(t.group(0))
        if not rows:
            continue
        header = [norm(x) for _, x in rows[0]]
        name_at = [i for i, h in enumerate(header) if "회사명" in h]
        industry_at = [i for i, h in enumerate(header) if "업종" in h]
        if len(name_at) != 1 or len(industry_at) != 1:
            continue
        tables += 1
        for raw_row, cells in zip(ROW.findall(t.group(0))[1:], rows[1:]):
            texts = [x for _, x in cells]
            # A row-spanning group cell on the left shortens later rows, so columns are aligned from the right.
            offset = len(header) - len(texts)
            ni, li = name_at[0] - offset, industry_at[0] - offset
            if offset < 0 or ni < 0 or li < 0:
                continue
            if own and company_key(texts[ni]) == own:
                found.append({"nameCell": texts[ni], "label": texts[li], "locator": raw_row})
    return {"legalName": stated, "rows": found, "tables": tables}


def kind_label_on(intervals, ticker, day):
    """v4's own KIND interval for `ticker` covering `day` (open ends included), or None. v4 bytes, not re-derived."""
    for iv in intervals.get(ticker, []):
        if iv.get("status") == "UNKNOWN" or not iv.get("raw_industry_name"):
            continue
        if (iv["start"] is None or iv["start"] <= day) and (iv["end"] is None or day < iv["end"]):
            return {"label": norm(iv["raw_industry_name"]), "group": iv["research_industry_id"], "status": iv["status"]}
    return None


def admit_row(target, ticker, record, section, sources, label, code, locator):
    main = record["responses"][0]
    row = {"security_id": "KRX:" + ticker, "ticker": ticker, "corpCode": target["corpCode"],
           "receipt_no": target["receiptNos"][0], "known_from": target["availableFrom"], "subject_scope": "ISSUER",
           "identity_status": "DATED_ISSUER_SECURITY", "identity_source_sha256": main.get("sha256"),
           "identity_locator": "openCorpInfoNew('" + target["corpCode"] + "',", "source_sha256": section["sha256"],
           "source_locator": locator, "reported_label": label, "reported_code": code,
           "evidence_tier": "DART_EXPLICIT_ISSUER_CLASSIFICATION" if code else "DART_EXPLICIT_ISSUER_LABEL"}
    admitted, reason = V.admit(row, sources, {})
    return admitted is not None, reason


def scan(inventory, records, sources, crosswalk, intervals):
    """All retained receipts of all issuers. Returns one row per (receipt, candidate) plus per-receipt status counts."""
    out, status = [], Counter()
    for issuer in inventory:
        tickers = issuer["issuer"].get("tickers") or []
        ticker = next((t for t in tickers if t.endswith("0.KS")), tickers[0] if tickers else None)
        for target in issuer.get("selected", []):
            receipt = target["receiptNos"][0]
            record = records.get(receipt)
            if record is None:
                status["NOT_RETAINED"] += 1
                continue
            stmts, aff = [], {"rows": [], "legalName": None, "tables": 0}
            for section in record.get("sections", []):
                if section["node"]["rcpNo"] != receipt:
                    raise ValueError("LATER_RECEIPT_NODE_REFUSED")
                raw = sources.get(section["sha256"])
                if raw is None:
                    continue
                body = raw.decode("utf-8")
                stmts += [dict(s, section=section["section"], _sec=section) for s in parse_statements(body)]
                if section["section"] == "company_overview":
                    a = affiliate_self_rows(body)
                    aff = dict(a, rows=[dict(r, _sec=section) for r in a["rows"]])
            day = target["availableFrom"]
            kind = kind_label_on(intervals, ticker, day) if ticker else None
            base = {"ticker": ticker, "corpCode": target["corpCode"], "fiscalYear": target["fiscalYear"],
                    "receiptNo": receipt, "knownFrom": day, "kindIntervalOnReceiptDate": kind}
            status["TABLE_FORM_STATEMENTS_%d" % min(len(stmts), 2)] += 1
            for s in stmts:
                three = next((lv for lv in s["levels"] if lv["level"] == "소분류"), None)
                admitted, reason = admit_row(target, ticker, record, s["_sec"], sources, s["statedLabel"],
                                             s["statedCode"], s["locator"]) if s["locator"] else (False, "NO_TABLE_LOCATOR")
                group = V4.research_group(three["label"], crosswalk) if three else None
                out.append({**base, "kind": "TABLE_FORM_KSIC", "section": s["section"],
                            "statementsInReceipt": len(stmts), "statedCode": s["statedCode"],
                            "statedLabel": s["statedLabel"], "levels": s["levels"], "checks": s["checks"],
                            "threeDigitLabel": three["label"] if three else None,
                            "crosswalkGroupOfStatedLabel": V4.research_group(s["statedLabel"], crosswalk),
                            "crosswalkGroupOfThreeDigitRow": group, "admitMechanical": admitted, "admitReason": reason,
                            "agreesWithKind": None if kind is None or not three else three["label"] == kind["label"],
                            "groupAgreesWithKind": None if kind is None or group is None else group == kind["group"]})
            for r in aff["rows"]:
                admitted, reason = admit_row(target, ticker, record, r["_sec"], sources, norm(r["label"]), None,
                                             r["locator"])
                group = V4.research_group(r["label"], crosswalk)
                # A code written into the cell (e.g. 'C2924(건설및광업용기계장비제조업)') is recorded, never expanded:
                # its 3-digit parent would need the KSIC codebook, which the repository does not retain.
                coded = re.match(r"^([A-U]?\d{2,5})\((.+)\)$", norm(r["label"]))
                out.append({**base, "kind": "AFFILIATE_SELF_ROW", "section": "company_overview",
                            "legalNameStated": aff["legalName"], "selfRowsInReceipt": len(aff["rows"]),
                            "nameCell": r["nameCell"], "freeTextLabel": norm(r["label"]),
                            "codeStatedInCell": coded[1] if coded else None,
                            "crosswalkGroup": group, "admitMechanical": admitted, "admitReason": reason,
                            "agreesWithKind": None if kind is None else norm(r["label"]) == kind["label"],
                            "groupAgreesWithKind": None if kind is None or group is None else group == kind["group"]})
            status["AFFILIATE_SELF_ROWS_%d" % min(len(aff["rows"]), 2)] += 1
    return out, status


def eligible_candidate(row):
    """The objective candidate criteria the proposal would register. Eligibility is NOT adoption."""
    if row["kind"] == "TABLE_FORM_KSIC":
        return (row["statementsInReceipt"] == 1 and row["checks"].get("consistent") is True and row["admitMechanical"]
                and row["crosswalkGroupOfThreeDigitRow"] is not None)
    return row["selfRowsInReceipt"] == 1 and row["admitMechanical"] and row["crosswalkGroup"] is not None


def agreement(rows, kind):
    sub = [r for r in rows if r["kind"] == kind and eligible_candidate(r)]
    compared = [r for r in sub if r["groupAgreesWithKind"] is not None]
    disagree = [r for r in compared if not r["groupAgreesWithKind"]]
    every = [r for r in rows if r["kind"] == kind and r["agreesWithKind"] is not None]
    return {"allRows": sum(r["kind"] == kind for r in rows),
            "allRowsIssuers": len({r["corpCode"] for r in rows if r["kind"] == kind}),
            "allRowsComparedWithV4KindInterval": len(every),
            "allRowsRawLabelAgreesWithKind": sum(r["agreesWithKind"] is True for r in every),
            "eligibleCandidateRows": len(sub), "issuers": len({r["corpCode"] for r in sub}),
            "comparedWithV4KindInterval": len(compared), "groupAgrees": len(compared) - len(disagree),
            "rawLabelAgrees": sum(r["agreesWithKind"] is True for r in compared),
            "groupDisagreements": [{k: r.get(k) for k in ("ticker", "fiscalYear", "receiptNo", "statedCode",
                                    "threeDigitLabel", "freeTextLabel", "crosswalkGroupOfThreeDigitRow",
                                    "crosswalkGroup", "kindIntervalOnReceiptDate")} for r in disagree]}


def kr22_view(rows, report, src):
    """The 22 / 16 securities: every candidate row, eligible or not, and the months it WOULD classify if adopted."""
    corp_to_code = {q["dartCorpCode"]: q["code"] for q in report["requests"]}
    out = []
    for corp, code in sorted(corp_to_code.items(), key=lambda x: x[1]):
        mine = [r for r in rows if r["corpCode"] == corp]
        elig = [r for r in mine if eligible_candidate(r)]
        months = K._window_months(code, src)
        first = min((r["knownFrom"] for r in elig), default=None)
        out.append({"code": code, "corpCode": corp, "candidateRows": len(mine),
                    "tableFormRows": sum(r["kind"] == "TABLE_FORM_KSIC" for r in mine),
                    "affiliateSelfRows": sum(r["kind"] == "AFFILIATE_SELF_ROW" for r in mine),
                    "eligibleCandidateRows": len(elig),
                    "eligibleGroups": sorted({r.get("crosswalkGroupOfThreeDigitRow") or r.get("crosswalkGroup")
                                              for r in elig}),
                    "firstEligibleKnownFrom": first, "windowMemberMonths": len(months),
                    "windowMemberMonthsClassifiedIfAdopted": sum(m > first[:7] for m in months) if first else 0,
                    "rows": [{k: v for k, v in r.items() if k not in ("levels",)} | {"eligibleCandidate": eligible_candidate(r)}
                             for r in mine]})
    return out


def build(root=K.ROOT):
    root = Path(root)
    inventory, records, sources = R.load_v2(root)
    crosswalk = json.loads((root / R.CROSSWALK).read_text())
    intervals = json.loads(gzip.decompress((root / V4_INTERVALS).read_bytes()))
    rows, status = scan(inventory, records, sources, crosswalk, intervals)
    report = json.loads((HERE / "kr22-source-recovery.json").read_text())
    src = K.load(root)[0]
    view = kr22_view(rows, report, src)
    in16 = [s for s in view if s["windowMemberMonths"]]
    summary = {
        "denominator": 22, "inWindowSecurities": len(in16), "issuersScanned": len(inventory),
        "receiptsScanned": sum(status[k] for k in status if k.startswith("TABLE_FORM_STATEMENTS_")),
        "receiptStatus": dict(sorted(status.items())),
        "allIssuers": {"TABLE_FORM_KSIC": agreement(rows, "TABLE_FORM_KSIC"),
                       "AFFILIATE_SELF_ROW": agreement(rows, "AFFILIATE_SELF_ROW"),
                       "tableFormRowsAll": sum(r["kind"] == "TABLE_FORM_KSIC" for r in rows),
                       "tableFormRowsConsistent": sum(r["kind"] == "TABLE_FORM_KSIC" and r["checks"].get("consistent") is True for r in rows),
                       "affiliateSelfRowsAll": sum(r["kind"] == "AFFILIATE_SELF_ROW" for r in rows),
                       "affiliateSelfRowsExactCrosswalk": sum(r["kind"] == "AFFILIATE_SELF_ROW" and r["crosswalkGroup"] is not None for r in rows)},
        "kr22": {"securitiesWithAnyCandidateRow": [s["code"] for s in view if s["candidateRows"]],
                 "securitiesWithEligibleCandidate": [s["code"] for s in view if s["eligibleCandidateRows"]],
                 "windowMemberMonthsAll16": sum(s["windowMemberMonths"] for s in view),
                 "windowMemberMonthsClassifiedIfAdopted": sum(s["windowMemberMonthsClassifiedIfAdopted"] for s in view),
                 "industryAdmitted": {"before": 0, "after": 0}},
        "frozenTemplateChanged": False, "frozenCrosswalkChanged": False,
    }
    return {"contract": CONTRACT, "evidenceClass": "SOURCE_ONLY_CANDIDATES_NOT_ADMISSION", "historicalOutcomesRead": 0,
            "pricesRead": 0, "networkUsed": False, "finalEligibilityVerdict": "DEFERRED_TO_INDEPENDENT_AUDIT",
            "summary": summary, "securities": view,
            "inputs": {"crosswalkSha256": hashlib.sha256((root / R.CROSSWALK).read_bytes()).hexdigest(),
                       "v4IntervalsSha256": hashlib.sha256((root / V4_INTERVALS).read_bytes()).hexdigest(),
                       "v2Receipts": len(records), "v2Sources": len(sources)}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output", default=str(REPORT))
    args = ap.parse_args(argv)
    out = build()
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    json.dump(out["summary"], sys.stdout, ensure_ascii=False, indent=1)
    print()


if __name__ == "__main__":
    main()
