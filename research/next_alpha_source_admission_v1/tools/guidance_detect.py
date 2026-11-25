"""Rule-based guidance detector over SEC EX-99 press releases (source admission only, no prices)."""
import html, json, re, sys
CUE = re.compile(r"\b(outlook|guidance|expects?|expected|anticipates?|forecasts?|projects?|targets?|estimates?)\b", re.I)
PERIOD = re.compile(r"\b((first|second|third|fourth)[- ](fiscal[- ])?quarter|full[- ]year|fiscal[- ](year[- ])?(20\d\d|\d\d)|(calendar|fiscal)\s+20\d\d|20\d\d|next quarter|Q[1-4]\b|FY\s?\d\d)", re.I)
NUM = re.compile(r"(\$\s?\d[\d,.]*\s*(billion|million|thousand)?|\d[\d,.]*\s*(%|percent|basis points|billion|million))\s*(to|and|-|–|—|through)?\s*(\$?\s?\d[\d,.]*)?", re.I)
PAST = re.compile(r"\b(compared (to|with)|versus|vs\.|year[- ]ago|prior[- ]year|increased|decreased|grew|declined|was|were|reported)\b", re.I)
METRIC = {
 "revenue": r"\b(revenue|revenues|net sales|sales|bookings)\b",
 "eps": r"\b(eps|earnings per (diluted )?share|per diluted share|diluted earnings)\b",
 "operating_income": r"\b(operating (income|profit|margin|earnings)|ebit\b|adjusted ebitda|ebitda)\b",
 "gross_margin": r"\bgross margins?\b",
 "capex": r"\b(capital expenditures?|capex|capital spending|capital investments?|property and equipment additions)\b",
 "free_cash_flow": r"\bfree cash flow\b",
 "opex": r"\boperating expenses\b",
 "tax_rate": r"\btax rate\b",
}
VERB = {
 "RAISE": r"\b(rais(e|es|ed|ing)|increas(e|es|ed|ing)|boost(s|ed)?|lift(s|ed)?) (its |the |our )?(full[- ]year |annual |fiscal[- ]year |fiscal 20\d\d |20\d\d )?(financial )?(outlook|guidance|forecast|expectations)\b",
 "LOWER": r"\b(lower(s|ed|ing)? (its |the |our )?(full[- ]year |annual )?(outlook|guidance|forecast)|reduc(es|ed|ing) (its |the |our )?(outlook|guidance|forecast)|cut(s)? (its |the |our )?(outlook|guidance))\b",
 "REAFFIRM": r"\b(reaffirm(s|ed|ing)?|reiterat(e|es|ed|ing)|maintain(s|ed|ing)? (its |the |our )?(full[- ]year |annual )?(outlook|guidance|forecast)|confirm(s|ed|ing)? (its |the |our )?(outlook|guidance))\b",
 "WITHDRAW": r"\b(withdr(aw|ew|awn|aws|awing)|suspend(s|ed|ing)?) (its |the |our )?(previous(ly)? (issued |provided )?|prior |full[- ]year |annual |fiscal[- ]year )?(financial )?(outlook|guidance|forecast)",
 "INITIATE": r"\b(initiat(e|es|ed|ing)|introduc(e|es|ed|ing)|issu(e|es|ed|ing)|provid(es|ed|ing)) (its |the |our )?(initial |first )?(full[- ]year |annual |fiscal[- ]year |20\d\d )?(financial )?(outlook|guidance)\b",
 "NARROW": r"\bnarrow(s|ed|ing)? (its |the |our )?(full[- ]year |annual )?(outlook|guidance|range)",
 "UPDATE": r"\bupdat(e|es|ed|ing) (its |the |our )?(full[- ]year |annual |fiscal[- ]year )?(financial )?(outlook|guidance|forecast)\b",
}
def text(raw):
    t = raw.decode("utf-8", "replace")
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", ". ", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t)
def detect(raw):
    t = text(raw)
    sents = re.split(r"(?<=[.;])\s+(?=[A-Z•\-])", t)
    hits = []
    for s in sents:
        if len(s) > 900 or not CUE.search(s) or not PERIOD.search(s) or not NUM.search(s):
            continue
        if not re.search(r"\b(outlook|guidance|expects?|anticipates?|forecasts?|projects?)\b", s, re.I):
            continue
        hits.append(s)
    for m in re.finditer(r"(?i)\b(20\d\d|fiscal 20\d\d|full[- ]year|business|financial|annual)?\s*(outlook|guidance)\b", t):
        w = t[m.start(): m.start() + 700]
        if re.search(r"(?i)forward-looking|words such as|like .anticipate", w[:250]):
            continue
        if NUM.search(w) and re.search(r"\$\s?\d[\d,.]*\s*(billion|million)?\s*(to|-|–|—|±|\+/-|plus or minus)\s*\$?\s?\d|\d[\d,.]*\s*%?\s*(to|-|–|—)\s*\d[\d,.]*\s*(%|percent)", w) and any(re.search(p, w, re.I) for p in METRIC.values()):
            hits.append("[HEADING] " + w[:600])
    metrics = sorted({m for s in hits for m, p in METRIC.items() if re.search(p, s, re.I)})
    verbs = sorted({v for v, p in VERB.items() if re.search(p, t, re.I)})
    heading = bool(re.search(r"\b(business outlook|financial outlook|guidance|outlook)\b\s*[:.\-]?\s*(for|–|-)?", t, re.I))
    nongaap = any(re.search(r"non[- ]gaap|adjusted", s, re.I) for s in hits)
    gaap = any(re.search(r"\bgaap\b", s, re.I) and not re.search(r"non[- ]gaap", s, re.I) for s in hits)
    return {"chars": len(t), "guidanceSentences": len(hits), "hasNumericGuidance": bool(hits),
            "metrics": metrics, "metricGuidance": bool(hits) and bool(metrics), "verbs": verbs, "outlookHeading": heading,
            "basis": sorted(({"NON_GAAP"} if nongaap else set()) | ({"GAAP"} if gaap else set())), "examples": [h[:300] for h in hits[:3]], "examples_all": hits}
if __name__ == "__main__":
    d = sys.argv[1]; rows = json.load(open(f"{d}/sample.json"))
    for r in rows:
        if r.get("status") == "FETCHED":
            r["detect"] = detect(open(f"{d}/raw/{r['sha256']}", "rb").read())
    json.dump(rows, open(f"{d}/detected.json", "w"), indent=1)
