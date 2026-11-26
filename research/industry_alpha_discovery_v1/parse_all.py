"""Parse every downloaded release into the committed tables. Reads no price.

    python -m research.industry_alpha_discovery_v1.parse_all --raw <dir> --raw-iip <dir>

Outputs (data/):
  motie-items-by-release.csv   release x item x value month: amount (USD mn), the growth rate stated with it, vintage
  customs-flash-items.csv      10-/20-day flash x item: YoY rate stated in the 주요품목 sentence, stated release time
  iip-industry-yoy.csv         산업활동동향 release x industry: production / shipment / inventory YoY (first release)
  parse-log.json               one line per release: format, parse status
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path

from research.industry_alpha_discovery_v1 import parse_motie_hwp as MH
from research.industry_alpha_discovery_v1.collect_releases import parse_flash_text
from research.industry_alpha_discovery_v1.hwp_text import any_lines
from research.industry_first_release_v1 import collect_kr_trade as K

HERE = Path(__file__).resolve().parent


def pdftext(p: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True, check=True).stdout


def parse_motie_pdf(txt: str) -> dict | None:
    """#356's appendix-table parser, keeping the growth rate printed beside every amount."""
    m0 = re.search(r"\d{2}대\s*주요\s*수출\s*품목\s*규모", txt)
    if not m0:
        return None
    block = txt[m0.start():m0.start() + 8000]
    cols = re.findall(r"[’'‘`]\s?(\d{2})\.\s?(\d{1,2})\.?(~\s?\d{1,2})?(?=[.\s월])", block[:1500])
    if len(cols) < 4:
        return None
    n = 5 if len(cols) >= 5 and any(c[2] for c in cols[:5]) else 4
    labels = cols[:n]
    pair = K.NUM + r"\s*\(?\s*" + K.NUM + r"\s*\)?"
    rows = {}
    for line in block.splitlines():
        m = re.search(r"(?:^|\s)(\d{1,2})\s+([가-힣A-Za-z·()]+?)\s+" + r"\s*".join([pair] * n), line)
        if not m:
            continue
        g = m.groups()
        series = {}
        for k, (y, mo, rng) in enumerate(labels):
            if rng:
                continue
            v = float(g[2 + 2 * k].replace(",", "").replace("△", "-"))
            gr = float(g[3 + 2 * k].replace(",", "").replace("△", "-"))
            series[f"20{y}-{int(mo):02d}"] = (v, gr)
        rows[g[1]] = series
    return {"rows": rows} if rows else None


IIP_ROWS = {"SEMI": re.compile(r"^\s*(?:26[1A]\.?\s*)?반도체(?:\s*및\s*부품)?\s"),
            "AUTO": re.compile(r"^\s*(?:30\.?\s*)?자동차(?:\s*및\s*트레일러)?\s"),
            "PETRO": re.compile(r"^\s*(?:19\.?\s*)?석유\s*정제\s"),
            "SHIP": re.compile(r"^\s*(?:31\.?\s*)?기타\s*운송\s*장비\s")}
FLOAT = r"(-?\d[\d,]*\.\d+|-)"


def parse_iip_pdf(txt: str) -> dict:
    """업종별 생산·출하·재고: the combined table (weight, MoM, YoY x 3) or the three separate tables (2013-style)."""
    out = {}
    lines = txt.splitlines()
    # combined table (one row: P weight, P MoM, P YoY, S weight, S MoM, S YoY, I weight, I MoM, I YoY)
    for i, line in enumerate(lines):
        if re.search(r"업종별\s*생산\s*[·ㆍ․]\s*출하\s*[·ㆍ․]\s*재고(?!\s*증감률)", line):
            for row in lines[i:i + 140]:
                for ind, rx in IIP_ROWS.items():
                    if ind in out or not rx.search(row):
                        continue
                    nums = re.findall(FLOAT, row[rx.search(row).end():])
                    if len(nums) >= 6:
                        f = [None if x == "-" else float(x.replace(",", "")) for x in nums[:9]]
                        out[ind] = {"productionYoy": f[2], "shipmentYoy": f[5], "inventoryYoy": f[8] if len(f) >= 9 else None,
                                    "layout": "COMBINED"}
            if out:
                return out
    # separate tables (2013-2016): "업종별 생산·출하·재고 증감률" pages: production, shipment, inventory in order
    blocks = [i for i, line in enumerate(lines) if re.search(r"업종별\s*생산\s*[·ㆍ․]\s*출하\s*[·ㆍ․]\s*재고\s*증감률", line)]
    found = {ind: [] for ind in IIP_ROWS}
    for b in blocks:
        for row in lines[b:b + 60]:
            for ind, rx in IIP_ROWS.items():
                if rx.search(row):
                    nums = re.findall(FLOAT, row[rx.search(row).end():])
                    found[ind].append([None if x == "-" else float(x.replace(",", "")) for x in nums])
    for ind, rs in found.items():
        if len(rs) >= 3:
            # production / shipment rows: weight, MoM, contrib, YoY, ...; inventory: weight, MoM, contrib, YoY
            out[ind] = {"productionYoy": rs[0][3] if len(rs[0]) > 3 else None,
                        "shipmentYoy": rs[1][3] if len(rs[1]) > 3 else None,
                        "inventoryYoy": rs[2][3] if len(rs[2]) > 3 else None, "layout": "SEPARATE"}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--raw-iip", required=True)
    a = ap.parse_args(argv)
    raw, raw_iip = Path(a.raw), Path(a.raw_iip)
    manifest = json.loads((raw / "manifest-extension.json").read_text())
    manifest += [dict(it, _dir="iip") for it in json.loads((raw_iip / "manifest-extension.json").read_text())]
    motie, flash, iip, log = [], [], [], []
    for it in sorted(manifest, key=lambda x: (x["family"], x["refMonth"])):
        base = raw_iip if it.get("_dir") == "iip" else raw
        status, fmt = "NO_FILE", None
        for f in it["files"]:
            p = base / f["local"]
            ext = p.suffix.lower()
            fmt = ext.lstrip(".")
            try:
                if it["family"] == "MOTIE":
                    if f["isPdf"]:
                        res = parse_motie_pdf(pdftext(p))
                    elif ext in (".hwp", ".hwpx"):
                        hp = MH.parse(any_lines(p), it["refMonth"])
                        res = {"rows": hp["rows"]} if hp else None
                    else:
                        continue
                    if not res:
                        status = "UNPARSED"
                        continue
                    for item, series in res["rows"].items():
                        for month, (v, gr) in series.items():
                            motie.append({"releaseRefMonth": it["refMonth"], "published": it["published"], "item": item,
                                          "valueMonth": month, "valueMusd": v, "statedGrowthPct": gr,
                                          "vintage": "FIRST_RELEASE" if month == it["refMonth"] else "LATER_RELEASE",
                                          "format": fmt, "sha256": f["sha256"], "num": it["num"]})
                    status = "PARSED"
                    break
                if it["family"].startswith("FLASH"):
                    txt = pdftext(p) if f["isPdf"] else ("\n".join(any_lines(p)) if ext in (".hwp", ".hwpx") else "")
                    res = parse_flash_text(txt)
                    if not res["items"]:
                        status = "UNPARSED"
                        continue
                    for nm, v in res["items"].items():
                        flash.append({"family": it["family"], "refMonth": it["refMonth"], "published": it["published"],
                                      "releaseTime": res["releaseTime"], "item": nm, "yoyPct": v,
                                      "workingDaysPrior": (res["workingDays"] or {}).get("prior"),
                                      "workingDaysCurrent": (res["workingDays"] or {}).get("current"),
                                      "format": fmt, "sha256": f["sha256"], "num": it["num"]})
                    status = "PARSED"
                    break
                if it["family"] == "IIP":
                    if not f["isPdf"]:
                        status = "HWP_NOT_PARSED"
                        continue
                    res = parse_iip_pdf(pdftext(p))
                    if "SEMI" not in res:
                        status = "UNPARSED"
                        continue
                    for ind, r in res.items():
                        iip.append({"refMonth": it["refMonth"], "published": it["published"], "industry": ind, **r,
                                    "sha256": f["sha256"], "num": it["num"]})
                    status = "PARSED"
                    break
            except Exception as e:  # noqa: BLE001
                status = f"ERROR {e!r}"[:120]
        log.append({"family": it["family"], "refMonth": it["refMonth"], "published": it["published"], "num": it["num"],
                    "format": fmt, "status": status, "title": it.get("title")})
    d = HERE / "data"
    d.mkdir(exist_ok=True)
    for name, rows in (("motie-items-by-release.csv", motie), ("customs-flash-items.csv", flash),
                       ("iip-industry-yoy.csv", iip)):
        with open(d / name, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["empty"])
            w.writeheader()
            w.writerows(rows)
    (d / "parse-log.json").write_text(json.dumps(log, ensure_ascii=False, indent=0) + "\n")
    pub = [{k: it.get(k) for k in ("family", "num", "refMonth", "published", "title", "viewUrl", "fetchError")} |
           {"files": [{k: f[k] for k in ("fileNum", "name", "bytes", "sha256", "isPdf")} for f in it["files"]]} for it in manifest]
    (d / "source-manifest-extension.json").write_text(json.dumps(pub, ensure_ascii=False, indent=0) + "\n")
    print("motie", len(motie), "flash", len(flash), "iip", len(iip))
    from collections import Counter
    print(Counter((x["family"], x["status"]) for x in log))


if __name__ == "__main__":
    main()
