"""Source-only recovery inventory of the 22 terminated KR securities for the Industry Alpha study.

For each security it measures, from bytes already committed to this repository, what the study would need to keep the
name in an industry cohort with a total-return label:

* a DATE-SPECIFIC INDUSTRY: the v4 membership foundation's own status, plus every self-referential industry statement
  this module can find in the 92 retained terminal-action filings and in the v1 classification observations. A
  statement found here is a CANDIDATE for review, never an admitted membership: the v4 rules (taxonomy version,
  codebook, validity interval, issuer link) still apply, and nothing here changes intervals.json.gz;
* TERMINAL ECONOMICS: type, documented consideration (cash and/or successor shares per old share), successor
  identity, execution confirmation, effective date, amendment chain, failed receipts;
* DISTRIBUTIONS: DART dividend-amount lineage, Yahoo events known, ex-date semantics.

Nothing here reads a price, return, label or outcome, and no network is used. Inputs are named in INPUTS and hashed
into the report.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUTS = {
    "reconstruction": "docs/results/kr-terminal-action-reconstruction-v2.json",
    "corporateActions": "data/kr-terminal-corporate-actions.json",
    "dividendLineage": "docs/results/kr-dividend-amount-lineage-v2.json",
    "v4Audit": "data/kr-industry-membership-foundation-v4/state/audit.json.gz",
    "crosswalk": "research_specs/kr-industry-membership-foundation-v4/crosswalk.json",
    "retainedTerminalDocuments": "data/kr-industry-membership-foundation-v1/retained-terminal-documents.jsonl.gz",
    "classificationObservations": "data/kr-industry-membership-foundation-v1/classification-observations.json",
    "top120": "data/kr-industry-membership-foundation-v1/top120-inputs.json",
    "inputVerification": "research/industry_alpha_next_v1/input-verification.json",
}
STUDY_WINDOW = ("2015-01", "2026-09")
EXECUTION_CONFIRMED = {"CONFIRMED_BY_INDEPENDENT_COMPLETION_EVIDENCE"}

_HEADER = re.compile(r'<COMPANY-NAME AREGCIK="(\d+)">([^<]+)</COMPANY-NAME>')
# A group-affiliate table row: | company | its KSIC industry | corporate registration number |
_AFFILIATE = re.compile(r"\|\s*([^|]{2,60}?)\s*\|\s*([^|]{2,80}?)\s*\|\s*\d{6}-\d{7}\s*\|")
_ROW = re.compile(r"회사명\s*\|\s*([^|]{2,80}?)\s*\|(?:[^|]*\|){0,6}?\s*(?:[가-하]\.\s*)?주요\s*사업(?:의 내용)?\s*\|\s*([^|]{1,160}?)\s*\|")


def _read(root, key):
    path = root / INPUTS[key]
    raw = path.read_bytes()
    data = gzip.decompress(raw) if path.suffix == ".gz" else raw
    return raw, data


def load(root=ROOT):
    out, hashes = {}, {}
    for key in INPUTS:
        raw, data = _read(root, key)
        hashes[key] = hashlib.sha256(raw).hexdigest()
        if key == "retainedTerminalDocuments":
            out[key] = [json.loads(line) for line in data.decode().splitlines() if line.strip()]
        else:
            out[key] = json.loads(data)
    return out, hashes


def normalise_name(text):
    text = text.replace("&cr;", " ")
    text = re.sub(r"\([^)]*[A-Za-z][^)]*\)?", " ", text)      # English names in brackets
    text = re.sub(r"\(주\)|㈜|주식회사|\(가칭\)", " ", text)
    text = re.sub(r"[A-Za-z.,&]+", " ", text)                  # unbracketed English legal names
    return re.sub(r"[\s()]+", "", text)


def normalise_label(text):
    return re.sub(r"\s+", "", text.replace("&cr;", ""))


def clean_document(text):
    text = re.sub(r"<[^>]+>", " | ", text)
    text = re.sub(r"(\s*\|\s*)+", " | ", text)
    return re.sub(r"\s+", " ", text)


def self_names(code, src):
    """The security's own names: its KRX names, and the legal name DART prints on filings whose filer corp code is its
    own (the filing header's AREGCIK). A counterparty's name can never enter this set."""
    names = set(src["top120"]["securities"].get(code, {}).get("names", []))
    corp = None
    for sec in src["reconstruction"]["securities"]:
        if sec["code"] == code:
            names.add(sec.get("krxName") or "")
            corp = sec.get("dartCorpCode")
    for doc in src["retainedTerminalDocuments"]:
        if doc["ticker"] != code or not corp:
            continue
        for member in doc["members"]:
            m = _HEADER.search(member.get("text", ""))
            if m and m.group(1) == corp:
                names.add(m.group(2))
    return {normalise_name(n) for n in names if n}


def industry_candidates(code, src, labels):
    """Self-referential industry statements for one security, each with its source receipt and quote."""
    names = self_names(code, src)
    out = []
    for doc in src["retainedTerminalDocuments"]:
        if doc["ticker"] != code:
            continue
        text = clean_document(" ".join(m.get("text", "") for m in doc["members"]))
        for company, business in _ROW.findall(text):
            if normalise_name(company) in names:
                label = normalise_label(business)
                out.append({"rule": "MAIN_BUSINESS_ROW_NAMING_THE_SECURITY_ITSELF", "receiptNo": doc["receiptNo"],
                            "quote": f"회사명 | {company.strip()} | ... 주요사업 | {business.strip()}",
                            "statedText": business.strip(), "crosswalkGroup": labels.get(label)})
        for company, industry in _AFFILIATE.findall(text):
            if normalise_name(company) in names:
                label = normalise_label(industry)
                out.append({"rule": "GROUP_AFFILIATE_TABLE_ROW_NAMING_THE_SECURITY", "receiptNo": doc["receiptNo"],
                            "quote": f"| {company.strip()} | {industry.strip()} | <registration no.> |",
                            "statedText": industry.strip(), "crosswalkGroup": labels.get(label)})
    obs = src["classificationObservations"]
    for o in obs["annualFilingObservations"] + obs["reportedClassificationFacts"]:
        if o.get("ticker") != code:
            continue
        texts = [m.get("text", "") for m in o.get("classificationMarkers", [])] + [o.get("reportedIndustryLabel") or ""]
        for t in texts:
            hit = [lab for lab in labels if lab in normalise_label(t)]
            if hit:
                out.append({"rule": "KSIC_GROUP_LABEL_IN_THE_SECURITYS_OWN_PERIODIC_FILING", "receiptNo": o["receiptNo"],
                            "fiscalYear": o.get("fiscalYear"), "quote": normalise_label(t)[:200],
                            "statedText": hit[0], "crosswalkGroup": labels[hit[0]],
                            "codeShapedCandidates": o.get("codeShapedCandidates")})
    unique = {}
    for c in out:
        unique.setdefault((c["rule"], c["receiptNo"], c["statedText"]), c)
    return list(unique.values())


def window_member_months(code, src):
    return len(_window_months(code, src))


def _window_months(code, src):
    dates = src["top120"]["securities"].get(code, {}).get("observedTop120Dates", [])
    return sorted(d[:7] for d in dates if STUDY_WINDOW[0] <= d[:7] <= STUDY_WINDOW[1])


def crossing_months(code, src, last_trading, horizon):
    """Member months whose H-session label window (entry = next session after the month's last session) reaches past
    the security's last trading date: only those labels need terminal economics. Calendar-only; no price is read."""
    import pandas as pd

    from pipeline import replay_calendar as RC
    if not last_trading:
        return None
    days = pd.DatetimeIndex(RC.sessions("2014-12-01", "2027-12-31", "KR"))
    month_end = pd.Series(days, index=days).groupby(days.to_period("M")).max()
    out = 0
    for month in _window_months(code, src):
        signal = month_end.get(pd.Period(month, "M"))
        if signal is None:
            continue
        exit_pos = int(days.searchsorted(signal, side="right")) + horizon
        if exit_pos >= len(days) or days[exit_pos] >= pd.Timestamp(last_trading):
            out += 1
    return out


def security_row(sec, src, labels):
    code = sec["code"]
    action = next(a for a in src["corporateActions"]["actions"] if a["oldSecurity"] == code)
    dividends = src["dividendLineage"]["securities"].get(code, {})
    v4 = src["v4Audit"]["absent28"]["perSecurity"].get(code, {})
    components = action.get("considerationComponents") or []
    documented = [c for c in components if c.get("cashAmount") is not None or c.get("sharesPerOldShare") is not None]
    candidates = industry_candidates(code, src, labels)
    completeness = sec["completeness"]
    return {
        "code": code, "name": (src["top120"]["securities"].get(code, {}).get("names") or [sec.get("krxName")])[-1],
        "studyWindowMemberMonths": window_member_months(code, src),
        "lastTradingDate": sec.get("lastTradingDate"),
        "labelWindowCrossesTermination": {f"H{h}": crossing_months(code, src, sec.get("lastTradingDate"), h) for h in (126, 252)},
        "industry": {"v4Status": v4.get("status"), "v4Reason": v4.get("reason"), "admitted": False,
                     "candidates": candidates,
                     "candidateWithCrosswalkGroup": any(c["crosswalkGroup"] for c in candidates)},
        "terminal": {"actionType": action["actionType"], "considerationDocumented": bool(documented),
                     "consideration": [{k: c.get(k) for k in ("type", "cashAmount", "sharesPerOldShare", "successorSecurity")}
                                       for c in components],
                     "successorSecurity": action.get("successorSecurity"),
                     "executionStatus": action.get("executionStatus"),
                     "executionConfirmed": action.get("executionStatus") in EXECUTION_CONFIRMED,
                     "effectiveDate": action.get("effectiveDate"),
                     "amendmentChainStatus": action.get("amendmentChainStatus"),
                     "failedReceipts": len(action.get("failedReceipts") or []),
                     "unresolvedFields": action.get("unresolvedFields") or [],
                     "completeness": {k: completeness[k] for k in ("terminationTypeResolved", "terminalConsiderationResolved",
                                                                   "effectiveDateResolved", "amendmentChainResolved",
                                                                   "terminalActionChainResolved")}},
        "distributions": {"dartAmountLineageEntries": len(dividends.get("amountLineageEntries", [])),
                          "yahooEventsKnown": dividends.get("realYahooDividendEventsKnown"),
                          "dividendLineageResolved": completeness.get("dividendLineageResolved"),
                          "exDateSemanticsResolved": completeness.get("exDateSemanticsResolved")},
    }


def gates(row):
    """The four facts an industry total-return label on this security needs; True only when the evidence is READY."""
    t, d = row["terminal"], row["distributions"]
    return {"industryAdmitted": row["industry"]["admitted"],
            "terminalConsiderationResolved": t["completeness"]["terminalConsiderationResolved"] == "READY",
            "executionConfirmed": t["executionConfirmed"],
            "exDateSemanticsResolved": d["exDateSemanticsResolved"] == "READY"}


def summarise(rows, src):
    n = len(rows)
    inwin = [r for r in rows if r["studyWindowMemberMonths"] > 0]
    def count(pred, subset=rows):
        return sum(1 for r in subset if pred(r))
    g = {k: count(lambda r, k=k: gates(r)[k]) for k in gates(rows[0])}
    actions = Counter(r["terminal"]["actionType"] for r in rows)
    cand_rules = Counter(c["rule"] for r in rows for c in r["industry"]["candidates"])
    return {
        "securities": n,
        "inStudyWindow": len(inwin),
        "studyWindowMemberMonths": sum(r["studyWindowMemberMonths"] for r in rows),
        "studyWindowMemberMonthsCrossCheck": src["inputVerification"]["cohortExclusion"]["terminalLaterMemberDates"],
        "industry": {
            "v4Classified": count(lambda r: r["industry"]["v4Status"] not in (None, "UNKNOWN")),
            "admitted": count(lambda r: r["industry"]["admitted"]),
            "withAnySelfStatementCandidate": count(lambda r: bool(r["industry"]["candidates"])),
            "withCandidateMappedToCrosswalkGroup": count(lambda r: r["industry"]["candidateWithCrosswalkGroup"]),
            "inWindowWithAnyCandidate": count(lambda r: bool(r["industry"]["candidates"]), inwin),
            "inWindowMemberMonthsWithAnyCandidate": sum(r["studyWindowMemberMonths"] for r in inwin if r["industry"]["candidates"]),
            "candidatesByRule": dict(cand_rules),
        },
        "terminal": {
            "actionTypes": dict(actions),
            "typeResolved": count(lambda r: r["terminal"]["actionType"] != "TERMINATION_TYPE_UNRESOLVED"),
            "considerationDocumented": count(lambda r: r["terminal"]["considerationDocumented"]),
            "considerationResolvedReady": g["terminalConsiderationResolved"],
            "executionConfirmed": g["executionConfirmed"],
            "effectiveDateDocumented": count(lambda r: bool(r["terminal"]["effectiveDate"])),
            "amendmentChainReady": count(lambda r: r["terminal"]["amendmentChainStatus"] == "READY"),
            "withFailedReceipts": count(lambda r: r["terminal"]["failedReceipts"] > 0),
            "failedReceiptsTotal": sum(r["terminal"]["failedReceipts"] for r in rows),
            "terminalActionChainReady": count(lambda r: r["terminal"]["completeness"]["terminalActionChainResolved"] == "READY"),
        },
        "distributions": {
            "dividendLineageReady": count(lambda r: r["distributions"]["dividendLineageResolved"] == "READY"),
            "yahooEventsKnownAny": count(lambda r: (r["distributions"]["yahooEventsKnown"] or 0) > 0),
            "exDateSemanticsReady": g["exDateSemanticsResolved"],
        },
        "inStudyWindowGates": {
            k: {"securities": count(lambda r, k=k: gates(r)[k], inwin),
                "memberMonths": sum(r["studyWindowMemberMonths"] for r in inwin if gates(r)[k])}
            for k in gates(rows[0])} | {
            "considerationDocumented": {"securities": count(lambda r: r["terminal"]["considerationDocumented"], inwin),
                                        "memberMonths": sum(r["studyWindowMemberMonths"] for r in inwin
                                                            if r["terminal"]["considerationDocumented"])},
            "dividendLineageReady": {"securities": count(lambda r: r["distributions"]["dividendLineageResolved"] == "READY", inwin),
                                     "memberMonths": sum(r["studyWindowMemberMonths"] for r in inwin
                                                         if r["distributions"]["dividendLineageResolved"] == "READY")}},
        "crossingMemberMonths": {
            h: {"total": sum(r["labelWindowCrossesTermination"][h] or 0 for r in rows),
                "withConsiderationReadyAndExecutionConfirmed": sum(
                    r["labelWindowCrossesTermination"][h] or 0 for r in rows
                    if gates(r)["terminalConsiderationResolved"] and gates(r)["executionConfirmed"]),
                "withConsiderationReady": sum(r["labelWindowCrossesTermination"][h] or 0 for r in rows
                                              if gates(r)["terminalConsiderationResolved"])}
            for h in ("H126", "H252")},
        "eligibleForIndustryTotalReturnLabelToday": count(lambda r: all(gates(r).values())),
        "eligibleIfEveryIndustryCandidateWereAdmittedAndExDateRuleSealed":
            count(lambda r: bool(r["industry"]["candidates"]) and gates(r)["terminalConsiderationResolved"] and gates(r)["executionConfirmed"]),
        "gateCounts": g,
    }


def build(root=ROOT):
    src, hashes = load(root)
    labels = {normalise_label(k): v for k, v in src["crosswalk"]["mapping"].items()}
    rows = [security_row(sec, src, labels) for sec in src["reconstruction"]["securities"]]
    rows.sort(key=lambda r: r["code"])
    return {"schema": "KR22_INDUSTRY_RECOVERY_INVENTORY_V1", "evidenceClass": "SOURCE_INVENTORY_NO_OUTCOME",
            "historicalOutcomesRead": 0, "pricesRead": 0, "networkUsed": False,
            "inputs": {k: {"path": INPUTS[k], "sha256": hashes[k]} for k in INPUTS},
            "summary": summarise(rows, src), "securities": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output")
    args = ap.parse_args(argv)
    text = json.dumps(build(), indent=1, sort_keys=True, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text + "\n")
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
