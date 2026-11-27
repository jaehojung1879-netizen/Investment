"""Reconstruct FDA recall source events and compare them with device clearance records."""

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from zipfile import ZipFile

import ijson

RAW = Path("raw")
OUT = Path("build")
BEGIN = "2019-01-01"
END = "2025-12-31"


def archive_results(name):
    with ZipFile(RAW / name) as z, z.open(z.namelist()[0]) as f:
        yield from ijson.items(f, "results.item")


def iso(s):
    s = str(s or "").strip()
    for year, month, day in (
        (s[:4], s[4:6], s[6:]) if len(s) == 8 and s.isdecimal() else ("", "", ""),
        (s[:4], s[5:7], s[8:10]) if re.match(r"^\d{4}-\d\d-\d\d", s) else ("", "", ""),
        (s[6:], s[:2], s[3:5]) if re.fullmatch(r"\d\d/\d\d/\d{4}", s) else ("", "", ""),
    ):
        if year:
            try:
                return date(int(year), int(month), int(day)).isoformat()
            except ValueError:
                pass
    return ""


def norm(s):
    s = (
        unicodedata.normalize("NFKD", str(s or ""))
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    return " ".join(re.findall(r"[a-z0-9]+", s))


def firm(s):
    a = norm(s).split()
    suffixes = {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "company",
        "co",
        "llc",
        "ltd",
        "limited",
        "ag",
        "lp",
        "plc",
    }
    while a and a[-1] in suffixes:
        a.pop()
    return " ".join(a)


def nonempty_min(xs):
    return min((x for x in xs if x), default="")


def joins(xs):
    return "|".join(sorted({str(x) for x in xs if x}))


def write(name, rows, columns=None):
    if not rows and not columns:
        raise ValueError(name)
    with (OUT / name).open("w", newline="", encoding="utf-8") as stream:
        w = csv.DictWriter(stream, fieldnames=columns or list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def recall_number(s):
    m = re.fullmatch(
        r"([A-Z])-([0-9]+)-([0-9]{2}|[0-9]{4})", str(s or "").strip().upper()
    )
    return f"{m[1]}-{int(m[2]):04d}-{m[3][-2:]}" if m else str(s or "").upper()


enf = {}
source_counts = Counter()
skipped_keys = Counter()
for domain in ("device", "drug", "food"):
    for rec in archive_results(f"fda_{domain}_enforcement_00.zip"):
        source_counts[f"{domain}_enforcement_source_rows"] += 1
        start = iso(rec.get("recall_initiation_date"))
        if not BEGIN <= start <= END:
            continue
        source_counts[f"{domain}_enforcement_window_rows"] += 1
        ev = str(rec.get("event_id") or "").strip()
        number = recall_number(rec.get("recall_number"))
        if not ev.isdecimal() or not number:
            skipped_keys[domain] += 1
            continue
        key = domain, ev, number
        e = {
            "domain": domain,
            "event_id": ev,
            "recall_number": number,
            "recalling_firm": rec.get("recalling_firm") or "",
            "firm_key": firm(rec.get("recalling_firm")),
            "initiation": start,
            "weekly_report": iso(rec.get("report_date")),
            "classification_date": iso(rec.get("center_classification_date")),
            "severity": rec.get("classification") or "",
            "reason_fingerprint": hashlib.sha256(
                norm(rec.get("reason_for_recall")).encode()
            ).hexdigest()
            if norm(rec.get("reason_for_recall"))
            else "",
        }
        if key in enf and enf[key] != e:
            raise ValueError(f"Conflicting enforcement record {key}")
        enf[key] = e

device = defaultdict(list)
targets = {(ev, num) for domain, ev, num in enf if domain == "device"}
for r in archive_results("fda_device_recall_00.zip"):
    source_counts["device_recall_source_rows"] += 1
    k = (
        str(r.get("res_event_number") or "").strip(),
        recall_number(r.get("product_res_number")),
    )
    if k not in targets:
        continue
    codes = re.findall(
        r"[A-Z0-9]{3}", str(r.get("product_code") or "").strip().upper().rstrip("-")
    )
    device[k].append(
        {
            "event_date_posted": iso(r.get("event_date_posted")),
            "event_date_initiated": iso(r.get("event_date_initiated")),
            "firm_fei_number": str(r.get("firm_fei_number") or ""),
            "product_codes": codes,
            "clearances": sorted(
                {
                    str(x).strip().upper()
                    for x in r.get("k_numbers") or []
                    if re.fullmatch(r"K\d{6}", str(x).strip().upper())
                }
            ),
            "approvals": sorted(
                {
                    str(x).strip().upper()
                    for x in r.get("pma_numbers") or []
                    if str(x).strip()
                }
            ),
            "root_cause": r.get("root_cause_description") or "",
            "cfres_id": str(r.get("cfres_id") or ""),
        }
    )
source_counts["device_recall_matched_product_keys"] = len(device)

groups = defaultdict(list)
for (domain, ev, num), e in sorted(enf.items()):
    d = device.get((ev, num), []) if domain == "device" else []
    e["device_posted"] = nonempty_min(x["event_date_posted"] for x in d)
    e["device_initiated"] = nonempty_min(x["event_date_initiated"] for x in d)
    e["device_fei"] = joins(x["firm_fei_number"] for x in d)
    e["device_codes"] = joins(y for x in d for y in x["product_codes"])
    e["device_clearances"] = joins(y for x in d for y in x["clearances"])
    e["device_pma_refs"] = joins(y for x in d for y in x["approvals"])
    e["device_root_cause"] = joins(x["root_cause"] for x in d)
    e["device_record_ids"] = joins(x["cfres_id"] for x in d)
    groups[domain, ev].append(e)

events = []
for (domain, ev), rows in sorted(groups.items()):
    start = nonempty_min(r["initiation"] for r in rows)
    dates = {
        k: nonempty_min(x[k] for x in rows)
        for k in ["weekly_report", "device_posted", "classification_date"]
    }
    first_listed = nonempty_min(dates[k] for k in ["weekly_report", "device_posted"])
    severity = min((r["severity"] for r in rows if r["severity"]), default="")
    first_i = nonempty_min(
        r["weekly_report"] for r in rows if r["severity"] == "Class I"
    )
    events.append(
        {
            "domain": domain,
            "fda_event_id": ev,
            "initiation_date": start,
            "severity_eventually": severity,
            "earliest_observed_fda_date": first_listed,
            **dates,
            "first_class_i_weekly_report": first_i,
            "recorded_lag_days": (
                date.fromisoformat(first_listed) - date.fromisoformat(start)
            ).days
            if first_listed
            else "",
            "has_date_before_initiation": str(
                bool(first_listed and first_listed < start)
            ).lower(),
            "distinct_recall_numbers": len(rows),
            "recalling_firms": joins(r["recalling_firm"] for r in rows),
            "firm_keys": joins(r["firm_key"] for r in rows),
            "device_feis": joins(v for r in rows for v in r["device_fei"].split("|")),
            "device_codes": joins(
                v for r in rows for v in r["device_codes"].split("|")
            ),
            "device_clearances": joins(
                v for r in rows for v in r["device_clearances"].split("|")
            ),
            "device_root_causes": joins(
                v for r in rows for v in r["device_root_cause"].split("|")
            ),
            "device_record_ids": joins(
                v for r in rows for v in r["device_record_ids"].split("|")
            ),
            "fingerprints": joins(r["reason_fingerprint"] for r in rows),
        }
    )
events.sort(key=lambda e: (e["initiation_date"], e["domain"], e["fda_event_id"]))
write("fda_event_census.csv", events)
write("fda_product_crosswalk.csv", list(enf.values()))

class_i = [
    e
    for e in events
    if e["domain"] == "device" and e["severity_eventually"] == "Class I"
]
desired_numbers = {k for e in class_i for k in e["device_clearances"].split("|") if k}
desired_codes = {k for e in class_i for k in e["device_codes"].split("|") if k}
clearances = {}
library = defaultdict(dict)

for r in archive_results("fda_device_510k_00.zip"):
    source_counts["device_510k_source_rows"] += 1
    k = str(r.get("k_number") or "")
    code = str(r.get("product_code") or "")
    name = firm(r.get("applicant"))
    dt = iso(r.get("decision_date"))
    se = str(r.get("decision_code") or "") in {
        "SESE",
        "SESK",
        "SESD",
        "SESU",
        "SESP",
        "SESC",
    } or str(r.get("decision_description") or "").startswith("Substantially Equivalent")
    if k in desired_numbers and dt and se:
        clearances[k] = (dt, name, code, str(r.get("applicant") or ""))
    if code in desired_codes and name and dt and se:
        d = library[code]
        if name not in d or dt < d[name]:
            d[name] = dt
for r in archive_results("fda_device_classification_00.zip"):
    source_counts["device_classification_source_rows"] += 1


def roots(rows, gap):
    parents = list(range(len(rows)))

    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    by_signal = {}
    for i, e in enumerate(rows):
        d = date.fromisoformat(e["initiation_date"])
        organizations = {v for v in e["firm_keys"].split("|") if v}
        organizations.update("FEI:" + v for v in e["device_feis"].split("|") if v)
        sig = {("reason", v) for v in e["fingerprints"].split("|") if v}
        sig.update(("clearance", v) for v in e["device_clearances"].split("|") if v)
        for o in sorted(organizations):
            for s in sorted(sig):
                key = o, s
                if key in by_signal:
                    old_i, old_d = by_signal[key]
                    if (d - old_d).days <= gap:
                        left, right = find(old_i), find(i)
                        parents[max(left, right)] = min(left, right)
                by_signal[key] = i, d
    return [rows[find(i)]["fda_event_id"] for i in range(len(rows))]


roots_by_gap = {d: roots(class_i, d) for d in (30, 90, 180)}
candidates = []
for i, r in enumerate(class_i):
    firms = {k for k in r["firm_keys"].split("|") if k}
    nums = {k for k in r["device_clearances"].split("|") if k}
    codes = {k for k in r["device_codes"].split("|") if k}
    start = r["initiation_date"]
    senior = (date.fromisoformat(start) - timedelta(days=90)).isoformat()
    prior = {
        k: clearances[k] for k in nums if k in clearances and clearances[k][0] < start
    }
    explicit = {k: v for k, v in prior.items() if v[1] in firms and v[0] <= senior}
    clear90 = {k: v for k, v in prior.items() if v[0] <= senior}
    legal_clearances = {
        o: sorted(k for k, v in explicit.items() if v[1] == o) for o in sorted(firms)
    }
    alternate = set()
    for c in codes:
        alternate.update(
            n for n, d in library[c].items() if d <= senior and n not in firms
        )
    cfr = r["device_record_ids"].split("|")[0]
    candidates.append(
        {
            **r,
            **{f"cluster_{d}d": rts[i] for d, rts in roots_by_gap.items()},
            "linked_clearances_before_initiation": joins(prior),
            "linked_clearances_90d_before": joins(clear90),
            "exact_firm_linked_clearances_90d_before": joins(explicit),
            "same_firm_clearance_by_legal_name": json.dumps(
                {o: v for o, v in legal_clearances.items() if v},
                sort_keys=True,
                separators=(",", ":"),
            ),
            "earliest_exact_clearance_decision": nonempty_min(
                v[0] for v in explicit.values()
            ),
            "other_legal_applicant_names_same_code_90d_before": len(alternate)
            if codes
            else "",
            "fda_device_record_url": f"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfres/res.cfm?id={cfr}"
            if cfr
            else "",
        }
    )
write("fda_device_class_i.csv", candidates)

shortages = []
for r in archive_results("fda_drug_shortages_00.zip"):
    source_counts["drug_shortages_source_rows"] += 1
    d = iso(r.get("initial_posting_date"))
    if not BEGIN <= d <= END:
        continue
    shortages.append(
        {
            "initial_posting_date": d,
            "update_date": iso(r.get("update_date")),
            "generic_name": r.get("generic_name") or "",
            "package_ndc": r.get("package_ndc") or "",
            "company_name": r.get("company_name") or "",
            "status_current_snapshot": r.get("status") or "",
            "shortage_reason_current_snapshot": r.get("shortage_reason") or "",
        }
    )
write("fda_drug_shortage_listings.csv", shortages)
metrics = {
    "source_counts": dict(source_counts),
    "skipped_missing_keys": dict(skipped_keys),
    "window": [BEGIN, END],
    "distinct_enforcement_product_keys": len(enf),
    "domains": {
        d: {
            "events": sum(e["domain"] == d for e in events),
            "class_i_events": sum(
                e["domain"] == d and e["severity_eventually"] == "Class I"
                for e in events
            ),
            "display_date_missing": sum(
                e["domain"] == d and not e["earliest_observed_fda_date"] for e in events
            ),
            "display_before_start": sum(
                e["domain"] == d and e["has_date_before_initiation"] == "true"
                for e in events
            ),
        }
        for d in ("device", "drug", "food")
    },
    "class_i_candidate_clusters": {
        str(k): len(set(v)) for k, v in roots_by_gap.items()
    },
    "class_i_has_device_post": sum(bool(e["device_posted"]) for e in candidates),
    "class_i_has_device_code": sum(bool(e["device_codes"]) for e in candidates),
    "class_i_has_pre_clearance_90d": sum(
        bool(e["linked_clearances_90d_before"]) for e in candidates
    ),
    "class_i_has_exact_firm_pre_clearance_90d": sum(
        bool(e["exact_firm_linked_clearances_90d_before"]) for e in candidates
    ),
    "class_i_exact_firm_candidate_90d_clusters": len(
        {
            e["cluster_90d"]
            for e in candidates
            if e["exact_firm_linked_clearances_90d_before"]
        }
    ),
    "shortage_candidate_listing_rows": len(shortages),
}
(OUT / "fda_metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
print(json.dumps(metrics, indent=2))
