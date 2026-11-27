"""Keyword classification of affected financial items in Item 4.02 bodies (automated, unvalidated beyond #375's 5 manual cases)."""
import json, re, sys, collections
sys.path.insert(0, "."); from guidance_detect import text
CATS = {
 "revenue_recognition": r"revenue recognition|recogni[sz]ed revenue|net sales|revenues? (were|was) (overstated|understated)",
 "net_income_eps": r"net (income|earnings|loss)|earnings per share|\beps\b",
 "cash_flow_classification": r"statements? of cash flows?|operating activities|investing activities|financing activities",
 "balance_sheet_classification": r"balance sheets?|classification of|current liabilit|long-term debt",
 "stock_compensation_options": r"stock option|option grant|measurement date|stock-based compensation",
 "leases": r"\blease(s|hold)?\b accounting|lease accounting",
 "income_tax": r"income tax(es)?|tax provision|deferred tax",
 "inventory_cogs": r"inventor(y|ies)|cost of (goods|sales)",
 "derivatives_hedging": r"derivative|hedg(e|ing)",
 "warrants_spac": r"warrants?",
 "goodwill_impairment": r"goodwill|impairment",
 "reserves_accruals": r"reserves?|accrual",
}
d = json.load(open(sys.argv[1])); docs = {x["accession"]: x for x in json.load(open(sys.argv[2]))}
out = []
for r in d["records"]:
    t = text(open(f"{sys.argv[3]}/{docs[r['accessionNumber']]['sha256']}", "rb").read())
    i = t.lower().find("4.02"); w = t[i:i + 6000] if i >= 0 else t[:6000]
    cats = sorted(c for c, p in CATS.items() if re.search(p, w, re.I))
    auditor = bool(re.search(r"\b(4\.02\(b\)|independent (registered public )?account\w* (advised|notified|informed))", w, re.I))
    out.append({"cik": r["cik"], "accession": r["accessionNumber"], "filingDate": r["filingDate"], "categories": cats, "auditorInitiated402b": auditor, "chars": len(w)})
json.dump(out, open(sys.argv[4], "w"), indent=1)
for label, rows in (("all", out), ("since2014", [x for x in out if x["filingDate"] >= "2014"])):
    c = collections.Counter(k for x in rows for k in x["categories"])
    print(label, len(rows), "no category", sum(not x["categories"] for x in rows), "4.02(b)", sum(x["auditorInitiated402b"] for x in rows), c.most_common())
