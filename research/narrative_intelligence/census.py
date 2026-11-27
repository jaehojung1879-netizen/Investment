"""Fixed document census and matched evidence-packet diagnostics, no outcome access."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .ledger import day, indexed, number

PILOT = Path(__file__).with_name("census_pilot.json")
PREVIOUS = Path(__file__).with_name("mechanism_pilot.json")
ROOT = Path(__file__).resolve().parents[2]
# Official calendar: eight regular 2025 meetings; meeting -> publication.
CALENDAR = {
    "20250129": "2025-02-19", "20250319": "2025-04-09", "20250507": "2025-05-28",
    "20250618": "2025-07-09", "20250730": "2025-08-20", "20250917": "2025-10-08",
    "20251029": "2025-11-19", "20251210": "2025-12-30",
}
THEMES = {"PASS_THROUGH", "DELAY", "PERSISTENCE", "ONE_TIME", "COST_ABSORPTION",
          "MUTED_EFFECT", "WANING", "DISINFLATION"}
MODALITIES = {"CONTACT_REPORT", "BASELINE", "RISK", "CONDITIONAL", "EXPECTATION", "ATTRIBUTED_OBSERVATION"}
SCOPES = {"DISTRICT_CONTACTS", "PARTICIPANTS", "A_COUPLE", "SEVERAL", "MANY", "SOME", "A_FEW", "MOST"}
MAX_BYTES = 16 * 1024 * 1024


def diagnostics(pilot, previous):
    if (pilot["schema"] != "NARRATIVE_CENSUS_V1"
            or pilot["forecast_registration_authorized"] is not False
            or pilot["market_outcomes_read"] is not False):
        raise ValueError("SCHEMA_OR_AUTHORIZATION")
    clock = day(pilot["as_of"])
    meetings = indexed(pilot["meetings"])
    if set(meetings) != set(CALENDAR):
        raise ValueError("CALENDAR_CENSUS")
    seen = set()
    counts = dict.fromkeys(sorted(THEMES), 0)
    meeting_tags = []
    for key, release in CALENDAR.items():
        item = meetings[key]
        if (item["meeting_end"].replace("-", "") != key or item["publication"] != release
                or not day(item["meeting_end"]) < day(release) <= clock
                or item["url"] != f"https://www.federalreserve.gov/monetarypolicy/fomcminutes{key}.htm"):
            raise ValueError("PUBLICATION_OR_SOURCE")
        if item["raw_sha256"] is not None or not item["locator"] or not item["section"]:
            raise ValueError("SOURCE_PROVENANCE")
        tags = set()
        for claim in item["claims"]:
            if claim["id"] in seen:
                raise ValueError("DUPLICATE_CLAIM")
            seen.add(claim["id"])
            if set(claim) != {"id", "theme", "modality", "scope", "paraphrase"}:
                raise ValueError("CLAIM_SCHEMA")
            if claim["theme"] not in THEMES or claim["modality"] not in MODALITIES or claim["scope"] not in SCOPES:
                raise ValueError("CLAIM_CLASSIFICATION")
            if not claim["paraphrase"].strip():
                raise ValueError("MISSING_TEXT")
            tags.add(claim["theme"])
        for theme in tags:
            counts[theme] += 1
        meeting_tags.append({"id": key, "public": release, "observed_tags": sorted(tags)})
    # Prior pilot values stay unchanged. Match only identical calendar-end target labels.
    releases = indexed(pilot["additional_livingston"] + previous["releases"])
    ordered = sorted(releases.values(), key=lambda x: day(x["publication"]))
    targets = {}
    for row in ordered:
        if day(row["publication"]) > clock:
            raise ValueError("FUTURE_RELEASE")
        if row["stocks"] and (type(row["stock_n"]) is not int or row["stock_n"] <= 0):
            raise ValueError("STOCK_SAMPLE_COUNT")
        for target, value in row["stocks"].items():
            if day(target) <= day(row["publication"]) or number(value) <= 0:
                raise ValueError("INVALID_STOCK_TARGET")
            targets.setdefault(target, []).append({"source": row["id"], "release": row["publication"],
                                                   "value": value, "n": row["stock_n"]})
    same_target = {k: v for k, v in targets.items() if len(v) > 1}
    return {"classification": "EXPLORATORY_AUTHOR_VALIDATION_ONLY",
            "calendar_coverage": len(meetings), "calendar_expected": len(CALENDAR),
            "manual_claims": len(seen), "document_tag_counts": counts,
            "meeting_tags": meeting_tags, "stock_release_count": sum(bool(x["stocks"]) for x in ordered),
            "same_target_paths": same_target,
            "independent_people_count": None, "raw_source_bytes_admitted": 0,
            "forecast_registration_authorized": False, "market_outcomes_read": False}


def matched_packets(*, numeric_facts, mechanisms, as_of):
    """Build the A/B input contrast, not predictions. Date-only conservative cutoff.

    Facts and mechanisms must be source-linked. A missing source or unverified
    clock remains the caller's blocker; this function does not certify PIT.
    """
    cutoff = day(as_of)
    if not numeric_facts or not mechanisms:
        raise ValueError("BOTH_INPUT_CLASSES_REQUIRED")
    seen = set()
    for row in [*numeric_facts, *mechanisms]:
        if not row["id"] or row["id"] in seen or not row["source"] or not row["locator"]:
            raise ValueError("EVIDENCE_IDENTITY")
        seen.add(row["id"])
        if day(row["publication"]) >= cutoff:
            raise ValueError("SAME_DAY_OR_FUTURE_EVIDENCE")
    return {"as_of_date": as_of, "A": {"numeric": numeric_facts},
            "B": {"numeric": numeric_facts, "mechanisms": mechanisms},
            "status": "DESIGN_ONLY_NO_PIT_CERTIFICATION"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def acquire(pilot, out, opener=None):
    """Read fixed official HTML/PDF candidates once, external bytes only.

    Raw receipt is transport evidence, not license, original vintage, or
    admission. Stop on access refusal/rate limit for that host.
    """
    out = Path(out).resolve()
    if out.is_relative_to(ROOT):
        raise ValueError("EXTERNAL_OUTPUT_REQUIRED")
    out.mkdir(parents=True, exist_ok=False)
    opener = opener or build_opener(NoRedirect())
    attempts, blocked = [], set()
    # Fixed allowlist, independent of any edited source manifest.
    urls = [(k, f"https://www.federalreserve.gov/monetarypolicy/fomcminutes{k}.htm", "html")
            for k in CALENDAR]
    urls.extend([
        ("liv23d", "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/livingston-survey/2023/livdec23.pdf", "pdf"),
        ("liv24j", "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/livingston-survey/2024/livjun24.pdf", "pdf"),
    ])
    for key, url, kind in urls:
        host = url.split("/")[2]
        row = {"id": key, "url": url}
        if host in blocked:
            attempts.append({**row, "status": "SKIPPED_AFTER_HOST_REFUSAL"})
            continue
        try:
            req = Request(url, headers={"User-Agent": "Investment research validation/1.0"})
            with opener.open(req, timeout=20) as response:
                if response.status != 200 or response.geturl() != url:
                    raise ValueError("UNEXPECTED_RESPONSE")
                mime = response.headers.get_content_type()
                raw = response.read(MAX_BYTES + 1)
            if not 0 < len(raw) <= MAX_BYTES:
                raise ValueError("INVALID_SIZE")
            if kind == "pdf" and (mime != "application/pdf" or not raw.startswith(b"%PDF-")):
                raise ValueError("INVALID_PDF")
            if kind == "html" and (mime != "text/html" or b"Participants' Views" not in raw.replace(b"&#39;", b"'")
                                   and b"Participants&#x27; Views" not in raw):
                # Strict semantic guard. Legitimate markup variations can be blocked.
                raise ValueError("HTML_SECTION_NOT_VERIFIED")
            dest = out / (key + "." + kind)
            with dest.open("xb") as f:
                f.write(raw)
            attempts.append({**row, "status": "RECEIVED_NOT_PIT_ADMITTED", "path": dest.name,
                             "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                             "retrieved_at": datetime.now(timezone.utc).isoformat()})
        except HTTPError as exc:
            attempts.append({**row, "status": "HTTP_ERROR", "http_status": exc.code})
            if exc.code in (401, 403, 429):
                blocked.add(host)
        except (OSError, URLError, ValueError) as exc:
            attempts.append({**row, "status": "SOURCE_BLOCKED", "error_type": type(exc).__name__})
    result = {"scope": "FIXED_RAW_RETRIEVAL_ONLY", "attempts": attempts,
              "received": sum(x["status"] == "RECEIVED_NOT_PIT_ADMITTED" for x in attempts),
              "pit_admitted": 0, "production_effect": "NONE"}
    (out / "attempts.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire", type=Path)
    args = parser.parse_args()
    data = json.loads(PILOT.read_text(encoding="utf-8"))
    prior = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    result = diagnostics(data, prior)
    if args.acquire:
        result = acquire(data, args.acquire)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
