"""MCT-v1 input collection. Keeps original bytes, retrieval time, SHA-256, coverage and a PIT label per source.

Reads no outcome: market returns are stored as bytes and only their first/last month is recorded. Reuse first:
Shiller and the ALFRED BAA/GS10 ledgers come from MVMA-v1 (PR #357) and are not re-fetched.

Usage::

    python -m research.market_causal_transmission_v1.collect_inputs
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import io
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RAW = HERE / "data" / "raw"

SOURCES = {
    "JK_SHOCKS_MONTHLY": ("https://raw.githubusercontent.com/marekjarocinski/jkshocks_update_fed_202401/main/"
                          "shocks_fed_jk_m.csv", "jk-shocks-monthly.csv",
                          "Jarocinski-Karadi (2020) FOMC shocks, 2024-01 update; MP_pm/CBI_pm are per-event sign "
                          "classifications of 30-minute rate and S&P 500 surprises (observable right after the event); "
                          "*_median use a full-sample rotation (not real time)."),
    "JK_SHOCKS_EVENTS": ("https://raw.githubusercontent.com/marekjarocinski/jkshocks_update_fed_202401/main/"
                         "shocks_fed_jk_t.csv", "jk-shocks-events.csv", "Same, one row per FOMC event with its timestamp."),
    "BAUER_SWANSON_MPS": ("https://www.frbsf.org/wp-content/uploads/monetary-policy-surprises-data.xlsx",
                          "bauer-swanson-mps.xlsx",
                          "Bauer-Swanson (2023) MPS (observable) and MPS_ORTH (orthogonalised on pre-FOMC data with "
                          "full-sample coefficients: not real time)."),
    "GZ_EBP": ("https://www.federalreserve.gov/econres/notes/feds-notes/ebp_csv.csv", "gz-ebp.csv",
               "Gilchrist-Zakrajsek spread and excess bond premium; the EBP is a full-sample regression residual "
               "(REVISED_HISTORY), used as an outcome/mechanism measure only, never as a real-time signal."),
    "SPF_CPROF_LEVEL": ("https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/"
                        "survey-of-professional-forecasters/data-files/files/median_cprof_level.xlsx",
                        "spf-median-cprof-level.xlsx",
                        "Survey of Professional Forecasters median nominal corporate profit forecasts; forecasts are "
                        "never revised; release date approximated (see protocol)."),
    "SPF_CPROF_GROWTH": ("https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/"
                         "survey-of-professional-forecasters/data-files/files/median_cprof_growth.xlsx",
                         "spf-median-cprof-growth.xlsx", "Same, median annualised growth."),
    "FF_FACTORS_MONTHLY": ("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
                           "F-F_Research_Data_Factors_CSV.zip", "ff-research-data-factors.zip",
                           "Fama-French Mkt-RF and RF (CRSP value-weighted market, month-end to month-end). OUTCOME."),
    "FRED_BAA": ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAA", "fred-BAA.csv",
                 "Moody's seasoned Baa, monthly average; 0 revisions across ALFRED vintages 2005/2011 (MVMA probe)."),
    "FRED_GS10": ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=GS10", "fred-GS10.csv",
                  "10-year Treasury, monthly average; 0 revisions across ALFRED vintages 2005/2011 (MVMA probe)."),
    "FRED_DFII10": ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10", "fred-DFII10.csv",
                    "10-year TIPS real yield, daily, 2003-; market observation. Outcome/mechanism."),
    "FRED_T10YIE": ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10YIE", "fred-T10YIE.csv",
                    "10-year breakeven inflation, daily, 2003-; market observation. Outcome/mechanism."),
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def gz(raw: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as h:
        h.write(raw)
    return buf.getvalue()


def fetch(url: str) -> tuple[int | None, bytes, str | None]:
    """Library default agent first (FRED stalls unknown agents); federalreserve.gov answers a curl-style agent."""
    errors = []
    for headers in ({}, {"User-Agent": "curl/8.5.0"}):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                return r.status, r.read(), r.headers.get("Last-Modified")
        except Exception as exc:  # noqa: BLE001 - a refusal is recorded, not raised
            errors.append(type(exc).__name__ + ": " + str(exc)[:160])
    return None, b"", " | ".join(errors)


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = {"study": "market-causal-transmission-v1", "builtAt": now(), "outcomeReads": 0, "secretsUsed": [],
                "sources": {}}
    for key, (url, name, note) in SOURCES.items():
        retrieved = now()
        status, raw, info = fetch(url)
        entry = {"url": url, "retrievedAt": retrieved, "httpStatus": status, "note": note}
        if status == 200 and raw:
            stored = RAW / (name + ".gz")
            payload = gz(raw)
            stored.write_bytes(payload)
            entry.update({"lastModified": info, "originalSha256": hashlib.sha256(raw).hexdigest(),
                          "originalBytes": len(raw), "stored": str(stored.relative_to(REPO)),
                          "storedSha256": hashlib.sha256(payload).hexdigest()})
        else:
            entry["error"] = info
        manifest["sources"][key] = entry
        print(key, status, file=sys.stderr)
    manifest["reusedFromMvmaV1"] = {
        "shiller": "research/market_valuation_macro_overlay_v1/data/shiller-monthly-20240904.csv",
        "alfredBaaGs10": ["research/market_valuation_macro_overlay_v1/data/alfred-BAA-asof-decisions.csv",
                          "research/market_valuation_macro_overlay_v1/data/alfred-GS10-asof-decisions.csv"]}
    (HERE / "data" / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
