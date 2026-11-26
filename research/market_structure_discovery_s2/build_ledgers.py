"""Build the S2 institutional-trade event ledgers from the collected raw sources.

Outcome-free by construction: no price after an event date, no return, no excess return,
no IC and no NAV is read or written. The only price-derived quantity is the pre-event
average traded value (close x volume) over sessions that END 20 sessions before the
effective date, used as the denominator of the expected-pressure ratio.

Inputs (all under data/):
  kodex200_pdf.jsonl, kosdaq150_pdf.jsonl   KODEX 200 / KODEX KOSDAQ 150 PDF snapshots
  spdji_bodies.jsonl -> results/sp500_change_events_raw.json (parse_spdji.py)
  kofia_credit_balance.json, kofia_market_funds.json  KOFIA FreeSIS
  fed_z1/F51_1_t.csv                         Federal Reserve Z.1 F.223 (equity flows)
  ../../../data/universe-history.json        pinned S&P 500 membership (repository)
  KRX price shards (optional path argument) for the pre-event traded-value denominator
Usage: python build_ledgers.py [krx_price_dir]
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RES = os.path.join(HERE, "results")
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_stock(code: str | None) -> bool:
    return bool(code) and len(code) == 6 and code[0].isdigit() and not code.startswith("KRD")


# --------------------------------------------------------------------------- KR index
def load_pdf(path: str) -> list[dict]:
    snaps = {}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if "error" in r or not r.get("answeredFor") or not r.get("rows"):
            continue
        d = dt.datetime.strptime(r["answeredFor"], "%Y%m%d").date()
        members = {}
        for code, name, q, val, ratio in r["rows"]:
            if is_stock(code):
                members[code] = {"name": name, "q": float(q or 0), "v": float(val or 0),
                                 "w": float(ratio) if ratio not in (None, "") else None}
        snaps[d] = {"date": d, "members": members, "sha256": r["sha256"]}
    return [snaps[k] for k in sorted(snaps)]


def second_thursday(year: int, month: int) -> dt.date:
    d = dt.date(year, month, 8)
    while d.weekday() != 3:
        d += dt.timedelta(days=1)
    return d


def index_ledger(snaps: list[dict], index: str, full_n: int) -> dict:
    counts = [(s["date"], len(s["members"])) for s in snaps]
    full = [d for d, n in counts if n >= full_n]
    start = full[0] if full else None
    events = []
    weight_moves = []
    prev = None
    gaps = []
    for s in snaps:
        if start is None or s["date"] < start:
            continue
        if prev is not None and (s["date"] - prev["date"]).days > 40:
            gaps.append([prev["date"].isoformat(), s["date"].isoformat()])
            prev = s
            continue
        if prev is not None:
            a, b = prev["members"], s["members"]
            adds, drops = sorted(set(b) - set(a)), sorted(set(a) - set(b))
            st = second_thursday(s["date"].year, s["date"].month) if s["date"].month in (6, 12) else None
            # the PDF base date of a regular change is the expiry Thursday in some years and
            # the next session in others; both are accepted and the date is kept as observed
            regular = bool(st and prev["date"] < s["date"] and
                           st - dt.timedelta(days=1) <= s["date"] <= st + dt.timedelta(days=4) and len(adds) >= 3)
            for code in adds:
                events.append({"index": index, "action": "ADD", "code": code, "name": b[code]["name"],
                               "lastAbsent": prev["date"].isoformat(), "firstSeen": s["date"].isoformat(),
                               "intervalDays": (s["date"] - prev["date"]).days,
                               "regularReview": regular, "weightPct": b[code]["w"],
                               "snapshotSha256": s["sha256"]})
            for code in drops:
                events.append({"index": index, "action": "DROP", "code": code, "name": a[code]["name"],
                               "lastSeen": prev["date"].isoformat(), "firstAbsent": s["date"].isoformat(),
                               "intervalDays": (s["date"] - prev["date"]).days,
                               "regularReview": regular, "weightPct": a[code]["w"],
                               "snapshotSha256": s["sha256"]})
            # share-per-CU changes of continuing names, net of a basket-wide rescale
            common = [c for c in a if c in b and a[c]["q"] > 0 and b[c]["q"] > 0]
            if len(common) >= 50:
                rel = {c: b[c]["q"] / a[c]["q"] for c in common}
                med = statistics.median(rel.values())
                for c in common:
                    move = rel[c] / med - 1.0
                    if abs(move) >= 0.10 and (a[c]["w"] or 0) >= 0.05:
                        weight_moves.append({"index": index, "code": c, "name": b[c]["name"],
                                             "from": prev["date"].isoformat(), "to": s["date"].isoformat(),
                                             "relativeShareChange": round(move, 4),
                                             "weightBeforePct": a[c]["w"], "regularReview": regular})
        prev = s
    # An ETF basket can drop a constituent for a few weeks (halt, corporate action) without
    # any index change. A DROP followed by an ADD of the same code within 35 days, or the
    # reverse, is flagged PDF_TEMPORARY_EXCLUSION and excluded from index-event counts.
    by_code = collections.defaultdict(list)
    for e in events:
        by_code[e["code"]].append(e)
    for evs in by_code.values():
        evs.sort(key=lambda x: x.get("firstSeen") or x.get("firstAbsent"))
        for x, y in zip(evs, evs[1:]):
            dx = dt.date.fromisoformat(x.get("firstSeen") or x.get("firstAbsent"))
            dy = dt.date.fromisoformat(y.get("firstSeen") or y.get("firstAbsent"))
            if x["action"] != y["action"] and (dy - dx).days <= 35:
                x["pdfArtifact"] = y["pdfArtifact"] = "PDF_TEMPORARY_EXCLUSION"
    return {"index": index, "snapshots": len(snaps), "fullReplicationFrom": start.isoformat() if start else None,
            "memberCountRange": [min(n for _, n in counts), max(n for _, n in counts)] if counts else None,
            "unobservedGaps": gaps, "events": events, "weightMoves": weight_moves}


def load_traded_value(price_dir: str, codes: set[str]) -> dict:
    """code -> sorted list of (date, close*volume). Pre-event denominator only."""
    out = collections.defaultdict(list)
    if not price_dir or not os.path.isdir(price_dir):
        return {}
    for fn in sorted(os.listdir(price_dir)):
        if not fn.endswith(".jsonl.gz"):
            continue
        with gzip.open(os.path.join(price_dir, fn), "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                code = r["ticker"].split(".")[0]
                if code in codes and r.get("close") and r.get("volume") is not None:
                    out[code].append((r["date"], float(r["close"]) * float(r["volume"])))
    for code in out:
        out[code].sort()
    return out


def pre_event_adv(series: list, event_date: str, gap: int = 20, window: int = 60):
    prior = [v for d, v in series if d < event_date]
    if len(prior) < gap + window // 2:
        return None, 0
    use = prior[: len(prior) - gap][-window:]
    use = [v for v in use if v > 0]
    if len(use) < window // 2:
        return None, len(use)
    return statistics.median(use), len(use)


def attach_pressure(ledger: dict, tv: dict) -> None:
    for e in ledger["events"]:
        date = e.get("firstSeen") or e.get("firstAbsent")
        adv, n = pre_event_adv(tv.get(e["code"], []), date)
        e["preEventMedianTradedValueKrw"] = adv
        e["preEventSessions"] = n
        w = e.get("weightPct")
        # demand (KRW) per 1 trillion KRW of index-tracking AUM, divided by normal traded value:
        # sessions of normal turnover that 1 trillion KRW of passive capital must trade.
        e["pressurePerTrillionAum"] = (w / 100.0 * 1e12 / adv) if (adv and w) else None


def summarize_index(ledger: dict) -> dict:
    artifacts = [e for e in ledger["events"] if e.get("pdfArtifact")]
    ev = [e for e in ledger["events"] if not e.get("pdfArtifact")]
    by = collections.Counter((e["action"], e["regularReview"]) for e in ev)
    dates = sorted({e.get("firstSeen") or e.get("firstAbsent") for e in ev})
    reg_dates = sorted({e.get("firstSeen") or e.get("firstAbsent") for e in ev if e["regularReview"]})
    years = collections.Counter((e.get("firstSeen") or e.get("firstAbsent"))[:4] for e in ev if e["action"] == "ADD")
    pr = [e["pressurePerTrillionAum"] for e in ev if e.get("pressurePerTrillionAum")]
    def q(x, p):
        x = sorted(x)
        return x[min(len(x) - 1, int(p * (len(x) - 1)))] if x else None
    return {"index": ledger["index"], "fullReplicationFrom": ledger["fullReplicationFrom"],
            "snapshots": ledger["snapshots"], "memberCountRange": ledger["memberCountRange"],
            "adds": sum(v for (a, _), v in by.items() if a == "ADD"),
            "drops": sum(v for (a, _), v in by.items() if a == "DROP"),
            "addsRegular": by[("ADD", True)], "addsUnscheduled": by[("ADD", False)],
            "dropsRegular": by[("DROP", True)], "dropsUnscheduled": by[("DROP", False)],
            "distinctEventDates": len(dates), "distinctRegularReviewDates": len(reg_dates),
            "addsByYear": dict(sorted(years.items())),
            "unobservedGapsOver40Days": ledger.get("unobservedGaps"),
            "pdfTemporaryExclusionRowsExcluded": len(artifacts),
            "weightMoves": len(ledger["weightMoves"]),
            "weightMovesRegular": sum(1 for m in ledger["weightMoves"] if m["regularReview"]),
            "pressureEvaluable": len(pr),
            "pressurePerTrillionAumQuantiles": {k: q(pr, p) for k, p in
                                                (("p10", .1), ("p50", .5), ("p90", .9))} if pr else None}


# --------------------------------------------------------------------------- US S&P 500
def sp500_ledger() -> dict:
    raw = json.load(open(os.path.join(RES, "sp500_change_events_raw.json"), encoding="utf-8"))
    rows, seen = [], set()
    for e in raw["events"]:
        released = dt.datetime.fromisoformat(e["releasedEt"])
        for t in e["added"]:
            if (t, "ADD", e["effectiveDate"]) in seen:
                continue
            seen.add((t, "ADD", e["effectiveDate"]))
            rows.append({"ticker": t, "action": "ADD", "announcedEt": e["releasedEt"],
                         "effectiveDate": e["effectiveDate"], "timing": e["timing"], "url": e["url"],
                         "announceToEffectiveDays": (dt.date.fromisoformat(e["effectiveDate"]) - released.date()).days})
        for t in e["removed"]:
            if (t, "DROP", e["effectiveDate"]) in seen:
                continue
            seen.add((t, "DROP", e["effectiveDate"]))
            rows.append({"ticker": t, "action": "DROP", "announcedEt": e["releasedEt"],
                         "effectiveDate": e["effectiveDate"], "timing": e["timing"], "url": e["url"],
                         "announceToEffectiveDays": (dt.date.fromisoformat(e["effectiveDate"]) - released.date()).days})
    # independent check against the repository's pinned membership intervals
    uh = json.load(open(os.path.join(REPO, "data", "universe-history.json"), encoding="utf-8"))
    joins = [(t, v["listed"]) for t, v in uh.items() if v.get("region") == "US" and v["listed"] > "2012-12-27"]
    joins = [(t, d) for t, d in joins if "2013-01-01" <= d <= "2026-11-26"]
    parsed_add = collections.defaultdict(list)
    for r in rows:
        if r["action"] == "ADD":
            parsed_add[r["ticker"]].append(r["effectiveDate"])
    matched = 0
    for t, d in joins:
        # the pinned membership file records a join on its own snapshot date, which lags the
        # effective date by days to months; accept a parsed add 0-130 days before it.
        if any(-7 <= (dt.date.fromisoformat(d) - dt.date.fromisoformat(x)).days <= 130 for x in parsed_add.get(t, [])):
            matched += 1
    eff_dates = sorted({r["effectiveDate"] for r in rows})
    ann_dates = sorted({r["announcedEt"][:10] for r in rows})
    gaps = [r["announceToEffectiveDays"] for r in rows]
    def quarterly(d: str) -> bool:
        x = dt.date.fromisoformat(d)
        if x.month not in (3, 6, 9, 12):
            return False
        f = dt.date(x.year, x.month, 15)
        while f.weekday() != 4:
            f += dt.timedelta(days=1)
        return 0 < (x - f).days <= 4
    summary = {
        "releasesParsed": len(raw["events"]), "clausesUnparsed": len(raw["unparsed"]),
        "adds": sum(r["action"] == "ADD" for r in rows), "drops": sum(r["action"] == "DROP" for r in rows),
        "distinctEffectiveDates": len(eff_dates), "distinctAnnouncementDates": len(ann_dates),
        "addsAtQuarterlyRebalance": sum(r["action"] == "ADD" and quarterly(r["effectiveDate"]) for r in rows),
        "announceToEffectiveDaysMedian": statistics.median(gaps) if gaps else None,
        "announceToEffectiveDaysRange": [min(gaps), max(gaps)] if gaps else None,
        "pinnedMembershipJoins2013to2026": len(joins),
        "pinnedJoinsMatchedByParsedAdd": matched,
        "coverageOfPinnedJoinsPct": round(100 * matched / len(joins), 1) if joins else None,
    }
    return {"summary": summary, "rows": rows, "unparsed": raw["unparsed"]}


# --------------------------------------------------------------------------- KOFIA
def kofia_events() -> dict:
    credit = json.load(open(os.path.join(DATA, "kofia_credit_balance.json"), encoding="utf-8"))
    funds = json.load(open(os.path.join(DATA, "kofia_market_funds.json"), encoding="utf-8"))
    rows = sorted((r for r in funds["rows"] if r["TMPV1"]), key=lambda r: r["TMPV1"])
    # forced-sale (반대매매) episodes: amount above the 99th percentile of the trailing 250
    # sessions of the same series; episodes separated by >= 20 sessions are independent.
    series = [(r["TMPV1"], float(r.get("TMPV6") or 0)) for r in rows]
    flags = []
    for i in range(250, len(series)):
        hist = sorted(v for _, v in series[i - 250:i])
        thr = hist[int(0.99 * (len(hist) - 1))]
        if series[i][1] > thr and series[i][1] > 0:
            flags.append(i)
    episodes, last = [], -999
    for i in flags:
        if i - last >= 20:
            episodes.append(series[i][0])
        last = i
    c = sorted((r for r in credit["rows"] if r["TMPV1"]), key=lambda r: r["TMPV1"])
    nonzero = [r for r in c if r.get("TMPV2")]
    return {
        "creditBalance": {"statCode": credit["statCode"], "sha256": credit["sha256"], "rows": len(c),
                          "firstNonZero": nonzero[0]["TMPV1"] if nonzero else None, "last": c[-1]["TMPV1"]},
        "marketFunds": {"statCode": funds["statCode"], "sha256": funds["sha256"], "rows": len(rows),
                        "first": rows[0]["TMPV1"], "last": rows[-1]["TMPV1"]},
        "forcedSaleSpikeSessions": len(flags),
        "forcedSaleIndependentEpisodes": len(episodes),
        "forcedSaleEpisodeStartDates": episodes,
        "episodesByYear": dict(sorted(collections.Counter(d[:4] for d in episodes).items())),
    }


# --------------------------------------------------------------------------- Z.1
def z1_summary() -> dict:
    path = os.path.join(DATA, "fed_z1", "F51_1_t.csv")
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    head = rows[0]
    want = {"FA653064100.Q": "mutualFunds", "FA563064100.Q": "etfs", "FA153064105.Q": "households",
            "FA263064105.Q": "restOfWorld", "FA593064105.Q": "pensionFunds",
            "FA103164105.Q": "nonfinancialCorporateIssuance"}
    out = {}
    for code, label in want.items():
        if code not in head:
            out[label] = {"code": code, "present": False}
            continue
        j = head.index(code)
        vals = [(r[0], r[j]) for r in rows[1:] if r[j] not in ("ND", "") and float(r[j]) != 0.0]
        out[label] = {"code": code, "present": True, "firstNonZeroQuarter": vals[0][0] if vals else None,
                      "lastQuarter": vals[-1][0] if vals else None, "quarters": len(vals)}
    return {"file": "data/fed_z1/F51_1_t.csv", "sha256": sha256_file(path), "series": out,
            "vintageNote": "Z.1 revises history each release; this file is the 2026Q2 release as fetched, not a PIT vintage."}


def main() -> None:
    price_dir = sys.argv[1] if len(sys.argv) > 1 else ""
    k200 = index_ledger(load_pdf(os.path.join(DATA, "kodex200_pdf.jsonl")), "KOSPI200", 195)
    kq = index_ledger(load_pdf(os.path.join(DATA, "kosdaq150_pdf.jsonl")), "KOSDAQ150", 145)
    codes = {e["code"] for e in k200["events"]}
    tv = load_traded_value(price_dir, codes)
    attach_pressure(k200, tv)
    for e in kq["events"]:
        e["preEventMedianTradedValueKrw"] = None
        e["pressurePerTrillionAum"] = None
        e["pressureNote"] = "KOSDAQ traded value not in the repository's KRX price ledger (KOSPI only)"
    sp = sp500_ledger()
    ledger = {"generatedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "outcomeFree": True,
              "kospi200": k200, "kosdaq150": kq, "sp500": sp}
    with open(os.path.join(RES, "institutional-event-ledger.json"), "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, ensure_ascii=False, indent=1, default=str)
    summary = {"kospi200": summarize_index(k200), "kosdaq150": summarize_index(kq),
               "sp500": sp["summary"], "kofia": kofia_events(), "fedZ1": z1_summary(),
               "pressureDenominatorSource": "signal-history ledger/prices/kr (KOSPI .KS only), sessions ending 20 before the event"
               if tv else "not supplied"}
    with open(os.path.join(RES, "ledger-summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    main()
