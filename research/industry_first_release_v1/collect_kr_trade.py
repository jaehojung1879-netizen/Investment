"""Korean monthly export first releases and their later revisions, from the original government press-release PDFs.

    python -m research.industry_first_release_v1.collect_kr_trade --raw <private dir> --since 2023-08 [--parse-only]

Source: KDI Economic Information Center (eiec.kdi.re.kr) "동향자료" list, which republishes each ministry's press release
with the original attachment. Two report families are kept:
  MOTIE  "YYYY년 M월 수출입 동향" (산업통상(자원)부, released on the 1st of the next month): the FIRST public figure.
         Its appendix table "20대 주요 수출 품목 규모 및 증감률" (USD million) carries four columns: the same month a
         year earlier, two months earlier, one month earlier and the reference month. So each release states the
         first figure for month m and the then-current (revised) figures for m-1, m-2 and m-12.
  KCS    "YYYY년 M월 월간 수출입 현황 [확정치]" (관세청, mid-month): the customs final monthly figure (recorded, parsed
         only where its table matches; otherwise kept as raw evidence).
Each PDF is stored outside git with its SHA-256; the committed outputs are the parsed rows and a manifest.
One request at a time, ~1.5 s apart, generic User-Agent. No login, no undocumented endpoint: the list, view and
download URLs are the site's own public links.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "https://eiec.kdi.re.kr/policy"
UA = {"User-Agent": "research audit"}
PACE = 1.5
MOTIE = re.compile(r"^(\d{4})년\s*(\d{1,2})월\s*(?:및\s*(?:상반기|연간)\s*)?수출입\s*동향\s+(산업통상자원부|산업통상부|지식경제부)\s+(\d{4}\.\d{2}\.\d{2})")
KCS = re.compile(r"^(\d{4})년\s*(\d{1,2})월\s*월간\s*수출입\s*현황\s*\[확정치\]\s+관세청\s+(\d{4}\.\d{2}\.\d{2})")


def get(url: str, referer: str | None = None) -> bytes:
    h = dict(UA)
    if referer:
        h["Referer"] = referer
    for k in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=90) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(3 * (k + 1))
    raise err


def list_page(pg: int, topic: str = "O") -> list[tuple[str, str]]:
    s = get(f"{BASE}/materialList.do?pg={pg}&pp=100&topic={topic}").decode("utf-8", "ignore")
    out, seen = [], set()
    for num, t in re.findall(r"materialView\.do\?num=(\d+)[^>]*>(.*?)</a>", s, re.S):
        t = html.unescape(" ".join(re.sub("<[^>]+>", "", t).split()))
        if num in seen or not re.search(r"\d{4}\.\d{2}\.\d{2}", t):
            continue
        seen.add(num)
        out.append((num, t))
    return out


def discover(since: str) -> list[dict]:
    found = []
    for topic in ("O", "P"):
        found += discover_topic(since, topic)
    uniq = {(r["family"], r["refMonth"]): r for r in found}
    return sorted(uniq.values(), key=lambda r: (r["refMonth"], r["family"]))


def discover_topic(since: str, topic: str) -> list[dict]:
    found, pg = [], 1
    while True:
        rows = list_page(pg, topic)
        dates = [re.search(r"(\d{4}\.\d{2}\.\d{2})", t).group(1) for _, t in rows]
        for num, t in rows:
            for fam, rx in (("MOTIE", MOTIE), ("KCS", KCS)):
                m = rx.match(t)
                if m:
                    y, mo = int(m.group(1)), int(m.group(2))
                    found.append({"family": fam, "num": num, "refMonth": f"{y}-{mo:02d}", "published": m.groups()[-1].replace(".", "-"),
                                  "title": t})
        print("page", topic, pg, dates[-1] if dates else None, len(found), flush=True)
        if not dates or dates[-1].replace(".", "-")[:7] < since:
            break
        pg += 1
        time.sleep(PACE)
    return found


def fetch_pdf(item: dict, raw: Path) -> dict:
    view = f"{BASE}/materialView.do?num={item['num']}&topic=O"
    s = get(view).decode("utf-8", "ignore")
    time.sleep(PACE)
    links = re.findall(r'href="(/policy/callDownload\.do\?num=\d+&filenum=(\d+))[^"]*"', s)
    names = re.findall(r">\s*([^<>]+\.(?:pdf|hwp|hwpx|xlsx?))\s*<", s, re.I)
    out = {**item, "viewUrl": view, "files": []}
    for (path, fn), name in zip(links, names or [None] * len(links)):
        if name and not name.lower().endswith(".pdf"):
            continue
        body = get("https://eiec.kdi.re.kr" + path.split("&dtime")[0], referer=view)
        time.sleep(PACE)
        digest = hashlib.sha256(body).hexdigest()
        dst = raw / f"{item['family']}-{item['refMonth']}-{item['num']}-{fn}.pdf"
        dst.write_bytes(body)
        out["files"].append({"fileNum": fn, "name": name, "bytes": len(body), "sha256": digest, "isPdf": body[:4] == b"%PDF",
                             "local": dst.name})
    return out


NUM = r"(△?[\d,]+(?:\.\d+)?)"


def parse_motie(pdf: Path) -> dict | None:
    """The appendix table rows (USD million) of the 20 main items, with the four column month labels."""
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    return parse_motie_text(txt)


def parse_motie_text(txt: str) -> dict | None:
    """Parse the appendix table from pdftotext -layout output (three layouts seen 2023-2026, see tests)."""
    m0 = re.search(r"\d{2}대\s*주요\s*수출\s*품목\s*규모", txt)
    if not m0:
        return None
    block = txt[m0.start():m0.start() + 8000]
    cols = re.findall(r"[’'‘`]\s?(\d{2})\.\s?(\d{1,2})\.?(~\s?\d{1,2})?(?=[.\s월])", block[:1500])
    if len(cols) < 4:
        return None
    n = 5 if len(cols) >= 5 and any(c[2] for c in cols[:5]) else 4
    labels = cols[:n]
    pair = NUM + r"\s*\(?\s*" + NUM + r"\s*\)?"
    rows = {}
    for line in block.splitlines():
        m = re.search(r"(?:^|\s)(\d{1,2})\s+([가-힣A-Za-z·()]+?)\s+" + r"\s*".join([pair] * n), line)
        if not m:
            continue
        g = m.groups()
        series = {}
        for k, (y, mo, rng) in enumerate(labels):
            if rng:                                  # cumulative (e.g. Jan-Jun) column: not a monthly value
                continue
            series[f"20{y}-{int(mo):02d}"] = float(g[2 + 2 * k].replace(",", "").replace("△", "-"))
        rows[g[1]] = series
    months = [f"20{y}-{int(mo):02d}" for y, mo, rng in labels if not rng]
    return {"columns": months, "rows": rows} if rows else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--since", default="2023-08")
    ap.add_argument("--parse-only", action="store_true")
    a = ap.parse_args(argv)
    raw = Path(a.raw)
    raw.mkdir(parents=True, exist_ok=True)
    man_path = raw / "manifest.json"
    if a.parse_only and man_path.exists():
        manifest = json.loads(man_path.read_text())
    else:
        items = discover(a.since)
        manifest = json.loads(man_path.read_text()) if man_path.exists() else []
        have = {it["num"] for it in manifest}
        for it in items:
            if it["refMonth"] < a.since or it["num"] in have:
                continue
            manifest.append(fetch_pdf(it, raw))
            print(it["family"], it["refMonth"], [f["bytes"] for f in manifest[-1]["files"]], flush=True)
        man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    out_rows = []
    for it in manifest:
        if it["family"] != "MOTIE":
            continue
        for f in it["files"]:
            if not f["isPdf"]:
                continue
            p = parse_motie(raw / f["local"])
            if not p:
                continue
            for item, series in p["rows"].items():
                for month, v in series.items():
                    out_rows.append({"family": "MOTIE", "releaseRefMonth": it["refMonth"], "published": it["published"],
                                     "item": item, "valueMonth": month, "valueMusd": v,
                                     "vintage": "FIRST_RELEASE" if month == it["refMonth"] else "LATER_RELEASE",
                                     "pdfSha256": f["sha256"], "num": it["num"]})
            break
    res_dir = HERE / "data"
    res_dir.mkdir(exist_ok=True)
    with open(res_dir / "kr-export-items-by-release.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0]) if out_rows else ["empty"])
        w.writeheader()
        w.writerows(out_rows)
    pub = [{k: it[k] for k in ("family", "num", "refMonth", "published", "title", "viewUrl")} |
           {"files": [{k: f[k] for k in ("fileNum", "name", "bytes", "sha256", "isPdf")} for f in it["files"]]} for it in manifest]
    (res_dir / "source-manifest.json").write_text(json.dumps(pub, ensure_ascii=False, indent=1) + "\n")
    print("rows", len(out_rows), "releases", sum(1 for it in manifest if it["family"] == "MOTIE"))


if __name__ == "__main__":
    main()
