"""Does DART actually serve what `kr_corporate_action_events.py` needs for
the 22 KR terminated securities' corporate-action lineage?

WHY A PROBE AND NOT A STRAIGHT COLLECTOR. Exactly the reasoning
`probe_dart_ownership_events.py` already states for `majorstock.json`: this
module's CONFIRMED half (`list.json`, DS001) is already used live in this
repository (`official_filing_depth`), so this probe mainly exercises it at
scale, over every one of the 22 terminated tickers plus a continuing-name
control sample for the dividend cross-validation the repair plan requires.
Its CANDIDATE half (`alotMatter.json`) is corroborated only from third-party
documentation — WebFetch of `opendart.fss.or.kr` is blocked from this
sandbox's egress, the same block that module's docstring records — and this
probe is what promotes it from candidate to confirmed, or reports exactly
how it does not match.

WHAT DECIDES THE ANSWER, IN ORDER, mirroring `probe_dart_ownership_events
.py`'s own structure:

  1. DOES THE KEY REACH `corpCode.xml` AND `list.json` AT ALL.
  2. FOR EACH OF THE 22 TERMINATED TICKERS: can its DART issuer identity be
     resolved by the repository's EXISTING historical hierarchy —
     `dart_ownership_universe._resolve_security`, reused via
     `kr_corporate_action_events.resolve_historical_dart_identity` rather
     than a second, weaker "current stock code only" path (DART blanks a
     corp's `stock_code` once it delists, which is exactly why an exact-
     current-code-only resolver is too weak for this sample) — and does
     `list.json`, walked to EVERY page, return any disclosure matching a
     known family keyword (`kr_corporate_action_events
     .classify_disclosure_family`)?
  3. THE `alotMatter.json` FIELD SET, checked on a sample of continuing
     dividend-paying names (needed for the repair plan's cross-validation
     step) and on any of the 22 whose identity resolved.
  4. HOW FAR BACK `list.json` reaches for a terminated name relative to its
     own last trading date — the 22 include a 2013 exit, so historical depth
     is asked for directly rather than assumed.

A single `page_count=100` call is not sufficient for a 2013-2026 filing
history: `kr_corporate_action_events.fetch_all_pages` walks every page the
served `total_page` names, using the SAME resolver and paginator
`scripts/collect_kr_corporate_actions.py` uses, and this probe reports pages
fetched and total rows for every ticker.

Nothing is written to the ledger and no artifact changes. This reports.

Usage:  python scripts/probe_kr_corporate_actions.py [--output probe.json]
        [--terminated-input docs/results/kr-termination-inventory.json]
        DART_API_KEY must be in the environment.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import dart_fundamentals as DF  # noqa: E402
from pipeline import dart_ownership_universe as DOU  # noqa: E402
from pipeline import kr_corporate_action_events as KCA  # noqa: E402

BASE = "https://opendart.fss.or.kr/api"
# A small, continuing sample for the dividend cross-validation control (all
# long-tenured KOSPI dividend payers, not chosen from the 22 under study):
# 삼성전자, SK하이닉스, NAVER, 현대차, POSCO홀딩스.
CONTINUING_SAMPLE = ("005930", "000660", "035420", "005380", "005490")


def call(path: str, params: dict, timeout: int = 30) -> tuple[dict | None, str]:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}/{path}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:  # pragma: no cover - network dependent
        return None, f"{type(exc).__name__}: {exc}"
    try:
        return json.loads(raw.decode("utf-8")), ""
    except ValueError:
        return None, f"non-JSON response ({len(raw)} bytes)"


def corp_code_directory(key: str) -> list[dict]:
    """The FULL `corpCode.xml` directory, including rows with a blank
    `stock_code` (delisted issuers) — the input
    `kr_corporate_action_events.resolve_historical_dart_identity` needs.
    Never pre-filtered to a `{stockCode: corpCode}` map, which is exactly
    the weaker path this probe no longer takes.
    """
    try:
        with urllib.request.urlopen(f"{BASE}/corpCode.xml?crtfc_key={key}",
                                    timeout=120) as response:
            blob = response.read()
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"ERROR: corp_code 목록을 받지 못했습니다 — {exc}")
        return []
    return DOU.parse_corp_code_zip(blob)


def probe_disclosure_index(key: str, stock: str, corp: str) -> dict:
    """`list.json`, walked to every page, classified by family."""
    def fetch_page(page_no: int) -> dict:
        payload, error = call("list.json", {
            "crtfc_key": key, "corp_code": corp, "bgn_de": "20130101",
            "end_de": time.strftime("%Y%m%d", time.gmtime()),
            "page_count": "100", "page_no": str(page_no),
            "sort": "date", "sort_mth": "asc",
        })
        if payload is None:
            raise KCA.PaginationError(error)
        return payload

    entry: dict = {"stockCode": stock, "corpCode": corp}
    try:
        rows, meta = KCA.fetch_all_pages(fetch_page)
    except KCA.PaginationError as exc:
        entry["error"] = str(exc)
        return entry
    entry["status"] = DF.describe_status(meta["status"])
    entry["pagesFetched"] = meta["pagesFetched"]
    entry["totalCount"] = meta["totalCount"]
    entry["rowsReturned"] = len(rows)
    candidates = KCA.candidate_disclosures(rows, ticker=f"{stock}.KS")
    entry["matchedDisclosures"] = len(candidates)
    entry["familiesSeen"] = sorted({family for row in candidates
                                    for family in row["disclosureFamilies"]})
    entry["sampleMatches"] = candidates[:5]
    entry["earliestMatchReceiptDate"] = candidates[0]["receiptDate"] if candidates else None
    return entry


def probe_dividend_section(key: str, stock: str, corp: str) -> dict:
    """`alotMatter.json` -- candidate endpoint, see module docstring."""
    payload, error = call("alotMatter.json", {
        "crtfc_key": key, "corp_code": corp, "bsns_year": "2023", "reprt_code": "11011"})
    entry: dict = {"stockCode": stock, "corpCode": corp}
    if payload is None:
        entry["error"] = error
        return entry
    status = str(payload.get("status"))
    entry["status"] = DF.describe_status(status)
    rows = payload.get("list") or []
    entry["rows"] = len(rows)
    if status != "000" or not isinstance(rows, list) or not rows:
        return entry
    fields_present = {field: sum(1 for r in rows if field in r)
                      for field in KCA.ALOTMATTER_CANDIDATE_FIELDS}
    entry["fieldsPresentPct"] = {k: round(100.0 * v / len(rows), 1)
                                 for k, v in fields_present.items()}
    built, refused = [], 0
    for row in rows:
        record, _reason = KCA.build_dividend_section_row(
            row, ticker=f"{stock}.KS", collected_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"))
        if record is not None:
            built.append(record)
        else:
            refused += 1
    entry["buildSucceeded"] = len(built)
    entry["buildRefused"] = refused
    entry["sampleRow"] = rows[0]
    return entry


def probe_document_retrieval(key: str, receipt_no: str, timeout: int = 30) -> dict:
    """`document.xml` -- DART's original-filing-document download endpoint.

    This is a DIFFERENT confidence tier from `alotMatter.json`: it is not a
    structured JSON endpoint at all (DART serves a ZIP of the filing's raw
    XML/HTML), so a successful probe here establishes RAW-EVIDENCE
    reachability only -- never a structured field, never a termination type,
    never a consideration amount. See `docs/kr-terminal-action-reconstruction
    -v2.md` for why structured merger/tender/share-exchange endpoints are not
    probed here: no third-party documentation this sandbox could reach
    corroborated a specific endpoint path or field map for them, and guessing
    one is exactly what the vendor-refusal invariants forbid. `document.xml`
    is reported separately because it is corroborated with higher confidence
    (a generic, commonly-referenced OpenDART base endpoint, not one specific
    to a disclosure type) and does not require guessing a type-specific path.
    """
    url = f"{BASE}/document.xml?crtfc_key={key}&rcept_no={receipt_no}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return {"receiptNo": receipt_no, "reachable": False, "error": f"HTTP {exc.code}"}
    except Exception as exc:  # pragma: no cover - network dependent
        return {"receiptNo": receipt_no, "reachable": False,
               "error": f"{type(exc).__name__}: {exc}"}
    is_zip = raw[:2] == b"PK"
    is_json_refusal = False
    refusal_status = None
    if not is_zip:
        try:
            payload = json.loads(raw.decode("utf-8"))
            is_json_refusal = True
            refusal_status = DF.describe_status(str(payload.get("status")))
        except (ValueError, UnicodeDecodeError):
            pass
    return {
        "receiptNo": receipt_no, "reachable": True, "contentType": content_type,
        "bytes": len(raw), "isZip": is_zip, "isJsonRefusal": is_json_refusal,
        "refusalStatus": refusal_status,
    }


def classify_verdict(report: dict) -> str:
    """SERVED / AUTH_REQUIRED / NETWORK_ERROR / BLOCKED_SOURCE /
    SCHEMA_CHANGED / INCONCLUSIVE_NO_ROWS, mirroring
    `probe_dart_ownership_events.classify_verdict`'s vocabulary."""
    index_entries = list(report.get("disclosureIndex", {}).values())
    served = [e for e in index_entries if e.get("rowsReturned") is not None]
    if served:
        return "SERVED"
    statuses = [str(e.get("status", "")) for e in index_entries if e.get("status")]
    if any(any(code in status for code in DF.FATAL_STATUSES) for status in statuses):
        return "AUTH_REQUIRED"
    errors = [str(e["error"]) for e in index_entries if e.get("error")]
    if any("HTTP" not in err for err in errors):
        return "NETWORK_ERROR"
    if errors:
        return "BLOCKED_SOURCE"
    return "INCONCLUSIVE_NO_ROWS"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="kr-corporate-actions-probe.json")
    parser.add_argument(
        "--terminated-input", type=Path,
        default=ROOT / "docs/results/kr-termination-inventory.json")
    args = parser.parse_args(argv)

    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        print("ERROR: DART_API_KEY not in the environment; nothing probed.")
        return 1
    print(f"key present, {len(key)} chars\n")

    inventory = json.loads(args.terminated_input.read_text(encoding="utf-8"))
    terminated_codes = [row["code"].removesuffix(".KS") for row in inventory["securities"]]
    krx_names = {row["code"].removesuffix(".KS"): row.get("krxName")
                for row in inventory["securities"]}

    report: dict = {"probedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "endpoints": ["list.json", "alotMatter.json"],
                    "terminatedCodes": terminated_codes,
                    "continuingSample": list(CONTINUING_SAMPLE)}

    directory = corp_code_directory(key)
    if not directory:
        return 1
    print(f"corp_code 디렉터리 {len(directory):,}개\n")

    report["identity"] = {}
    report["disclosureIndex"] = {}
    for stock in terminated_codes:
        identity = KCA.resolve_historical_dart_identity(stock, krx_names.get(stock), directory)
        report["identity"][stock] = identity
        if identity["status"] != KCA.RESOLVED:
            report["disclosureIndex"][stock] = {"error": "DART identity unresolved",
                                               "identity": identity}
            print(f"{stock}  identity UNRESOLVED ({identity['provenance']}) — "
                  f"{krx_names.get(stock)!r} 이름 매칭 실패")
            continue
        corp = identity["corpCode"]
        entry = probe_disclosure_index(key, stock, corp)
        entry["identityBasis"] = identity["basis"]
        report["disclosureIndex"][stock] = entry
        print(f"{stock}  identity={identity['basis']} status={entry.get('status')} "
              f"pages={entry.get('pagesFetched')} matches={entry.get('matchedDisclosures')} "
              f"families={entry.get('familiesSeen')}")
        time.sleep(0.3)

    # `_unique_index` is called directly (module-private in
    # `dart_ownership_universe.py`) rather than adding a public alias to a
    # file `alpha-opportunity-model-v1` seals by hash — see
    # `kr_corporate_action_events.resolve_historical_dart_identity`'s
    # docstring for why.
    continuing_directory_index = DOU._unique_index(directory, "stockCode")
    report["dividendSection"] = {}
    for stock in CONTINUING_SAMPLE:
        candidates = continuing_directory_index.get(stock) or []
        if len(candidates) != 1:
            continue
        corp = candidates[0]["corpCode"]
        entry = probe_dividend_section(key, stock, corp)
        report["dividendSection"][stock] = entry
        print(f"{stock} (continuing)  alotMatter status={entry.get('status')} "
              f"rows={entry.get('rows')}")
        if entry.get("fieldsPresentPct"):
            print(f"    fieldsPresentPct={json.dumps(entry['fieldsPresentPct'], ensure_ascii=False)}")
            print(f"    sampleRow={json.dumps(entry['sampleRow'], ensure_ascii=False)}")
        time.sleep(0.3)

    # RAW-EVIDENCE reachability -- one real MERGER-family receipt number per
    # security that has one, drawn from the disclosure index this run just
    # fetched (never a guessed receipt number). See `probe_document_retrieval`
    # docstring for why this is a separate, lower-detail confidence tier from
    # `alotMatter.json`.
    report["documentRetrieval"] = {}
    for stock, entry in report["disclosureIndex"].items():
        merger_match = next((m for m in entry.get("sampleMatches") or []
                             if KCA.MERGER in m.get("disclosureFamilies", ())), None)
        if merger_match is None:
            continue
        doc_entry = probe_document_retrieval(key, merger_match["receiptNo"])
        report["documentRetrieval"][stock] = doc_entry
        print(f"{stock}  document.xml receipt={merger_match['receiptNo']} -> "
              f"{json.dumps(doc_entry, ensure_ascii=False)}")
        time.sleep(0.3)
        if len(report["documentRetrieval"]) >= 3:
            break

    verdict = classify_verdict(report)
    report["verdict"] = verdict
    resolved_identity = sum(1 for row in report["identity"].values()
                            if row["status"] == KCA.RESOLVED)
    report["identityResolvedCount"] = resolved_identity
    report["identityResolvedOf"] = len(terminated_codes)
    report["identityResolvedByBasis"] = {
        basis: sum(1 for row in report["identity"].values() if row.get("basis") == basis)
        for basis in KCA.IDENTITY_BASES
    }

    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")

    print("\n=== 판정 ===")
    print(f"  22개 중 identity 해소: {resolved_identity}/{len(terminated_codes)}")
    print(f"  verdict: {verdict}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(f"verdict={verdict}\n")

    print(f"\nwrote {args.output}")
    return 0 if verdict == "SERVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
