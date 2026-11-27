"""Screen current FDA action descriptions without treating instructions as execution."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

import ijson

OUT = Path("build")
RAW = Path("raw")
source = list(csv.DictReader((OUT / "fda_device_class_i.csv").open()))
ids = {e["fda_event_id"]: e for e in source}
exposure = list(csv.DictReader((OUT / "fda_issuer_exposure.csv").open()))
focused = {e["fda_event_id"] for e in exposure if e["linked_510k_90d_before"]}

patterns = {
    "distribution_stop_wording": re.compile(
        r"(?:stop|cease|discontinue|suspend|halt)\s+(?:all\s+|further\s+|any\s+|new\s+)?(?:distribution|sale|sales|shipment|shipments|use and distribution)|do not\s+(?:distribute|ship|sell)",
        re.IGNORECASE,
    ),
    "return_or_quarantine_wording": re.compile(
        r"(?:return|quarantine|segregate|isolate|remove from inventory)\b.{0,65}\b(?:product|devices?|lots?|units?|inventory)|\b(?:product|devices?|lots?|units?|inventory)\b.{0,65}\b(?:return|quarantine|segregate|isolate)\b",
        re.IGNORECASE,
    ),
    "field_service_or_update_wording": re.compile(
        r"software (?:upgrade|update|patch)|field (?:correction|service)|on.site (?:repair|service)|label(?:ing)? (?:correct|updat)|replacement label",
        re.IGNORECASE,
    ),
}
present = defaultdict(set)
words = defaultdict(set)
with ZipFile(RAW / "fda_device_recall_00.zip") as z, z.open(z.namelist()[0]) as f:
    for r in ijson.items(f, "results.item"):
        i = r.get("res_event_number")
        if i not in ids or not r.get("action"):
            continue
        text = " ".join(r["action"].split())
        a = str(r.get("cfres_id") or "")
        present[i].add(a)
        for k, p in patterns.items():
            if p.search(text):
                words[i].add(k)
rows = []
for i, e in sorted(ids.items(), key=lambda p: (p[1]["initiation_date"], p[0])):
    rows.append(
        dict(
            fda_event_id=i,
            cluster_90d=e["cluster_90d"],
            initiation_date=e["initiation_date"],
            actions_text_available=bool(present[i]),
            distinct_action_record_ids=len(present[i]),
            **{k: k in words[i] for k in patterns},
            issuer_and_product_candidate=i in focused,
        )
    )
with (OUT / "fda_action_cues.csv").open("w", newline="", encoding="utf-8") as stream:
    w = csv.DictWriter(stream, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
stats = {}
for group, pool in [
    ("class_i_all", rows),
    ("issuer_and_product", [r for r in rows if r["issuer_and_product_candidate"]]),
]:
    stats[group] = dict(
        events=len(pool),
        action_has_text=sum(r["actions_text_available"] for r in pool),
        **{k: len({r["cluster_90d"] for r in pool if r[k]}) for k in patterns},
    )
(OUT / "fda_actions_metrics.json").write_text(json.dumps(stats, indent=2) + "\n")
print(json.dumps(stats, indent=2))
