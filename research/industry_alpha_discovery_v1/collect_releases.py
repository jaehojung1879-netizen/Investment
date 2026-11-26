"""Extend the #356 first-release collection: MOTIE monthly releases back to 2013 and the customs 10-/20-day flashes.

    python -m research.industry_alpha_discovery_v1.collect_releases --raw <private dir> --list <kdi-list.json> [--families ...]

Reuses `research.industry_first_release_v1.collect_kr_trade` (download, MOTIE appendix parser) rather than a second
collector. `--list` is a dump of the KDI Economic Information Center list pages (topics O and P), produced by
`discover_list`; the same public list/view/download links as #356, one request at a time.

Flash releases ("YYYY년 M월 1일 ~ M월 10(20)일 수출입 현황 [잠정치]", 관세청; later issued under 재정경제부) state the
semiconductor change in prose: "(주요품목) 전년동기대비 반도체(331.2%) ... 증가, 승용차(△4.3%) 등 감소". That sentence is
parsed for every item; amounts are images in recent releases and are not read. The stated release time ("보도시점 ...
09:00") is recorded where the PDF carries it.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from research.industry_first_release_v1 import collect_kr_trade as K

HERE = Path(__file__).resolve().parent
FLASH = re.compile(r"^[’'‘]?(\d{2}|\d{4})년\s*(\d{1,2})월\s*1\s*일\s*[~∼～]\s*(\d{1,2})월\s*(10|20)\s*일\s*수출입\s*현황"
                   r"(?:\s*\[잠정치\])?\s+(\S+)\s+(\d{4}\.\d{2}\.\d{2})")
IIP = re.compile(r"^(\d{4})년\s*(\d{1,2})월\s*(?:및\s*\S+\s*)?산업활동동향\s+(통계청|국가데이터처)\s+(\d{4}\.\d{2}\.\d{2})")
PACE = 1.5


def discover_list(out: Path, pages: int = 62) -> None:
    rows = []
    for topic in ("O", "P"):
        for pg in range(1, pages + 1):
            s = K.get(f"{K.BASE}/materialList.do?pg={pg}&pp=100&topic={topic}").decode("utf-8", "ignore")
            for n, t in re.findall(r"materialView\.do\?num=(\d+)[^>]*>(.*?)</a>", s, re.S):
                t = html.unescape(" ".join(re.sub("<[^>]+>", "", t).split()))
                if re.search(r"\d{4}\.\d{2}\.\d{2}", t):
                    rows.append({"topic": topic, "pg": pg, "num": n, "title": t})
            time.sleep(PACE)
    out.write_text(json.dumps(rows, ensure_ascii=False))


def classify(listing: list[dict], since: str = "2013-01", families=("MOTIE", "FLASH10", "FLASH20")) -> list[dict]:
    """MOTIE monthly and customs flash items from a list dump, deduplicated by family and reference period."""
    found = {}
    for r in listing:
        t = r["title"]
        m = K.MOTIE.match(t)
        if m:
            ref = f"{int(m.group(1))}-{int(m.group(2)):02d}"
            found[("MOTIE", ref)] = {"family": "MOTIE", "num": r["num"], "refMonth": ref,
                                     "published": m.groups()[-1].replace(".", "-"), "title": t}
            continue
        m = IIP.match(t)
        if m:
            ref = f"{int(m.group(1))}-{int(m.group(2)):02d}"
            found[("IIP", ref)] = {"family": "IIP", "num": r["num"], "refMonth": ref, "issuer": m.group(3),
                                   "published": m.group(4).replace(".", "-"), "title": t}
            continue
        m = FLASH.match(t)
        if m:
            y = int(m.group(1))
            ref = f"{y + 2000 if y < 100 else y}-{int(m.group(2)):02d}"
            fam = f"FLASH{m.group(4)}"
            found[(fam, ref)] = {"family": fam, "num": r["num"], "refMonth": ref, "issuer": m.group(5),
                                 "published": m.group(6).replace(".", "-"), "title": t}
    return sorted((v for v in found.values() if v["refMonth"] >= since and v["family"] in families),
                  key=lambda v: (v["refMonth"], v["family"]))


NUMP = r"(△\s?)?(\d[\d,]*(?:\.\d+)?)\s*%"


def parse_flash_text(txt: str) -> dict:
    """Item YoY growth stated in the 주요품목 export sentence, the stated release time and day counts."""
    flat = " ".join(txt.split())
    out = {"items": {}, "releaseTime": None, "workingDays": None}
    m = re.search(r"보도시점.{0,40}?(\d{4})\.\s?(\d{1,2})\.\s?(\d{1,2})\.?\s*\(.\)\s*(\d{1,2}:\d{2})", flat)
    if m:
        out["releaseTime"] = m.group(4)
    m = re.search(r"조업일수.{0,40}?\(’?\s?(\d{2})\)\s*([\d.]+)\s*일.{0,10}?\(’?\s?(\d{2})\)\s*([\d.]+)\s*일", flat)
    if m:
        out["workingDays"] = {"prior": float(m.group(2)), "current": float(m.group(4))}
    # the export sentence is the first "(주요품목) 전년동기대비 ..." (the import one comes later); it ends at the
    # next "(주요국가)" or the import section. Older releases lack the parentheses around 주요품목.
    sec = (re.search(r"\(\s*주요\s*품목\s*\)\s*전년\s*동기\s*대비(.{0,600}?)(?:\(\s*주요\s*국가|수입\s*현황)", flat)
           or re.search(r"주요\s*품목\)?\s*전년\s*동기\s*대비(.{0,600}?)(?:주요\s*국가|수입\s*현황)", flat)
           # 2023-07..09: "(주요품목) 승용차(27.2%↑), 반도체(△18.1%↓), ..." with no 전년동기대비, ending at the next bullet
           or re.search(r"\(\s*주요\s*품목\s*\)(.{0,300}?)(?:ㅇ|\(\s*주요\s*국가|수입\s*현황)", flat))
    if sec:
        body = sec.group(1)
        for nm, neg, num in re.findall(r"([가-힣A-Za-z·]+(?:\s[가-힣]+)?)\s*\(\s*" + NUMP + r"\s*[↑↓]?\s*\)", body):
            nm = nm.replace("등", "").strip()
            v = float(num.replace(",", ""))
            out["items"][nm.split()[-1]] = -v if neg else v
    return out


def fetch(item: dict, raw: Path) -> dict:
    """Every attachment (PDF or HWP; #356's fetch_pdf keeps PDFs only, and releases before ~2021 are HWP only)."""
    view = f"{K.BASE}/materialView.do?num={item['num']}&topic=O"
    s = K.get(view).decode("utf-8", "ignore")
    time.sleep(PACE)
    links = re.findall(r'href="(/policy/callDownload\.do\?num=\d+&filenum=(\d+))[^"]*"', s)
    names = re.findall(r">\s*([^<>]+\.(?:pdf|hwp|hwpx|xlsx?))\s*<", s, re.I)
    out = {**item, "viewUrl": view, "files": []}
    for (path, fn), name in zip(links, names or [None] * len(links)):
        body = K.get("https://eiec.kdi.re.kr" + path.split("&dtime")[0], referer=view)
        time.sleep(PACE)
        ext = (name or "x.bin").rsplit(".", 1)[-1].lower()
        dst = raw / f"{item['family']}-{item['refMonth']}-{item['num']}-{fn}.{ext}"
        dst.write_bytes(body)
        out["files"].append({"fileNum": fn, "name": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                             "isPdf": body[:4] == b"%PDF", "local": dst.name})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--list", required=True)
    ap.add_argument("--since", default="2013-01")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--families", default="MOTIE,FLASH10,FLASH20,IIP")
    a = ap.parse_args(argv)
    raw = Path(a.raw)
    raw.mkdir(parents=True, exist_ok=True)
    man_path = raw / "manifest-extension.json"
    manifest = json.loads(man_path.read_text()) if man_path.exists() else []
    manifest = [it for it in manifest if it["files"]]          # retry anything that came back without a file
    have = {(it["family"], it["num"]) for it in manifest}
    todo = [it for it in classify(json.loads(Path(a.list).read_text()), a.since, tuple(a.families.split(",")))
            if (it["family"], it["num"]) not in have]

    def one(it):
        try:
            return fetch(it, raw)
        except Exception as e:  # noqa: BLE001
            return {**it, "files": [], "fetchError": repr(e)}

    with ThreadPoolExecutor(a.workers) as ex:          # a few concurrent requests; each worker still paces itself
        for got in ex.map(one, todo):
            manifest.append(got)
            print(got["family"], got["refMonth"], [f["bytes"] for f in got["files"]], flush=True)
            man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print("downloaded", len(manifest), "releases; parse with parse_all")


if __name__ == "__main__":
    main()
