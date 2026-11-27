import csv
import io
import json
from collections import Counter
from hashlib import file_digest
from pathlib import Path
from zipfile import ZipFile

from lxml import html

RAW = Path("raw")
OUT = Path("build")
S1 = Path("s1/Investment-network-pilot.zip")


def write(name, rows, fields=None):
    with (OUT / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def digest(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def sec_match(ticker, accession):
    j = json.loads((RAW / f"sec_submissions_{ticker}.json").read_text())
    r = j["filings"]["recent"]
    if accession not in r["accessionNumber"]:
        return ""
    i = r["accessionNumber"].index(accession)
    assert r["form"][i] == "8-K"
    return r["acceptanceDateTime"][i]


urls = {
    **json.loads((RAW / "official_urls.json").read_text()),
    **json.loads((RAW / "extra_urls.json").read_text()),
}
sec = [
    (
        "MP",
        "sec_mp_20250710",
        "0001193125-25-157310",
        "2025-07-09",
        "2025-07-10",
        "contract_capacity",
        "Critical-minerals program with a DoD counterparty, 10X manufacturing facility; conditional package",
        "Contract price floor, funding and purchase terms are not realized revenue; schedule and economic surprise unresolved",
    ),
    (
        "CE",
        "sec_celp_20251028",
        "0001306830-25-000203",
        "2025-10-28",
        "2025-10-28",
        "intended_closure",
        "Lanaken acetate tow plant; planned second-half 2026 termination subject to consultation",
        "No independent physical interruption in the 2019–2025 window shown",
    ),
    (
        "CULP",
        "sec_culp_20240429",
        "0000950170-24-051289",
        "2024-04-29",
        "2024-05-01",
        "decision_announced",
        "Quebec mattress-fabric wind-down; some capacity planned to move to Stokesdale",
        "Two facilities disclosed as one company plan; weaker demand is endogenous",
    ),
    (
        "AA",
        "sec_alcoa_20250929",
        "0001193125-25-223652",
        "2025-09-29",
        "2025-09-29",
        "permanent_closure_after_curtailment",
        "Kwinana alumina facility fully curtailed since June 2024; closure announcement has distinct information but no second physical stoppage",
        "Group with 2024 curtailment for physical-shock inference",
    ),
    (
        "ROG",
        "sec_rogers_20240606",
        "0000084748-24-000043",
        "2024-06-06",
        "2024-06-06",
        "intended_closure",
        "Evergem advanced circuit materials; China and United States footprint named as mitigation",
        "Intended, conditional cessation; no realized alternative capacity measurement",
    ),
    (
        "REVG",
        "sec_revg_20240125",
        "0000950170-24-009141",
        "2024-01-25",
        "2024-01-29",
        "board_plan",
        "Riverside ENC transit bus manufacturing discontinuation plan",
        "Same filing also covers Collins acquisition/disposition and dividend; separate root evidence needed",
    ),
    (
        "NSYS",
        "sec_nsys_20240515",
        "0001437749-24-017204",
        "2024-05-15",
        "2024-05-16",
        "facility_cost_plan",
        "Space reduction, lease amendment and separately announced consolidation",
        "No independently dated physical disruption or downstream linkage established",
    ),
]
fields = [
    "ticker",
    "source_key",
    "accession",
    "decision_or_agreement_date",
    "observed_public_date",
    "event_type",
    "path_evidence",
    "scope_limitation",
    "sec_acceptance_utc",
    "primary_url",
    "sha256",
]
secrows = []
for row in sec:
    t, key, acc, *_ = row
    p = RAW / (key + ".html")
    assert html.parse(str(p)).getroot() is not None
    secrows.append(dict(zip(fields, [*row, sec_match(t, acc), urls[key], digest(p)])))
write("sec_event_sources.csv", secrows)

cases = [
    (
        "phg_foam_2021",
        "new",
        "FDA medical device",
        "88058|88071",
        "2021-06-14",
        "initiated corrective recall; defect onset unknown",
        "2021-06-14",
        "issuer announcement (date); FDA announcement republished 2021-06-15; recall listings later",
        "2021-07-21",
        "Philips Respironics product and manufacturer as of recall; historic manufacturer link from FDA 510(k) or issuer filing when matched",
        "Sleep and respiratory devices to home users and durable medical equipment providers; separate device classes share foam root",
        "Public notice documents lack of immediate alternatives for some users; replacement schedule not measured",
        "VERIFIED_PRODUCT_CHANNEL",
        "fda_philips_20210614",
        "fda_philips_alternatives",
    ),
    (
        "abbott_sturgis_2022",
        "new",
        "FDA food",
        "89629",
        "2022-02-17",
        "voluntary recall announcement; contamination onset unknown",
        "2022-02-17",
        "company and FDA same date",
        "2022-03-16",
        "Abbott Sturgis manufactured specified formulas; dated earlier nutrition business evidence in issuer SEC records",
        "Sturgis production and products to formula distribution; FDA investigation and shortage response document market channel",
        "FDA used enforcement discretion for alternate suppliers; specialty formulas still limited; response ex post",
        "VERIFIED_PRODUCT_CHANNEL",
        "fda_abbott_20220217",
        "fda_abbott_substitutes",
    ),
    (
        "mdt_hvad_2021",
        "new",
        "FDA medical device",
        "88197",
        "2021-06-03",
        "new sales and distribution stop",
        "2021-06-03",
        "issuer announcement date from newsroom",
        "2021-08-18",
        "HeartWare HVAD previously marketed by Medtronic; prior approval ID FDA P100047",
        "Sales stop affected new implant channel; existing patients are a distinct installed base",
        "Issuer and FDA identify other LVAD options including Abbott HeartMate 3 for new candidates; not instant replacement of implants",
        "VERIFIED_PRODUCT_CHANNEL",
        "hvad_manufacturer",
        "hvad_fda_recommendations",
    ),
    (
        "bd_bactec_supply_2024",
        "new",
        "FDA/CDC product supply",
        "",
        "",
        "physical first date unverified; April/June supply inception not imputed",
        "2024-07-10",
        "CDC and BD public date; 06-11 customer letter is an earlier notification",
        "",
        "BD BACTEC instrument and bottle ecosystem; name of upstream supplier not established",
        "Upstream supplier issue → BD bottles → labs using the instrument system; CDC confirms disruption channel",
        "Same product category does not imply compatibility with installed instruments; inventory or transfers are possible mitigation",
        "VERIFIED_PRODUCT_CHANNEL",
        "cdc_bd_20240710",
        "bd_20240710",
    ),
    (
        "helene_north_cove_2024",
        "S1_overlap",
        "SEC/CDC/FDA product supply",
        "",
        "2024-09-26/2024-09-27",
        "storm and North Cove flood window",
        "2024-09-29",
        "Baxter release date; 09-30 EDGAR acceptance",
        "",
        "Baxter North Cove product categories disclosed before shock in company materials; individual hospital purchasing history unresolved",
        "Baxter IV and peritoneal dialysis supply disruption → hospitals/clinics aggregate; CDC confirms",
        "Conservation and authorized sourcing are mitigation routes; individual substitutions and all participating buyers unverified",
        "VERIFIED_PRODUCT_CHANNEL",
        "baxter_press_20240929",
        "baxter_cdc",
    ),
    (
        "textron_iam_2024",
        "new",
        "BLS/issuer",
        "2024-09-23-684",
        "2024-09-23",
        "BLS work stoppage start",
        "2024-09-21T23:34:00Z",
        "issuer page date September 21 18:34 CDT; earlier untested",
        "",
        "Textron Aviation named operator; component-level pre-exposure pending",
        "Manufacturing interruption bound to company operation; supplier/customer and facility allocation not established",
        "",
        "OPERATOR_ONLY",
        "textron_2024_notice",
        "bls_root",
    ),
    (
        "pratt_iam_2025",
        "new",
        "BLS/union",
        "2025-05-05-707",
        "2025-05-05",
        "BLS work stoppage start",
        "2025-05-04",
        "union vote announcement date",
        "",
        "Pratt & Whitney operator under RTX; independent ID for separate bargaining campaign",
        "Middletown and East Hartford plants named; engine-program/customer exposure unresolved",
        "",
        "OPERATOR_ONLY",
        "pratt_2025_notice",
        "bls_root",
    ),
    (
        "mp_dod_program_2025",
        "new",
        "SEC procurement",
        "0001193125-25-157310",
        "2025-07-09",
        "executed contract date",
        "2025-07-10",
        "SEC acceptance and issuer release",
        "",
        "MP Materials contracting party; proposed 10X capacity and staged obligations",
        "Government-supported demand and capacity program; event not an observed physical interruption",
        "Import concentration is context, ramp timing cannot be assumed from contract terms",
        "CONTRACT_PROGRAM",
        "sec_mp_20250710",
        "sec_mp_capacity",
    ),
]
fields = [
    "common_root_id",
    "novelty",
    "source_route",
    "source_record_ids",
    "occurrence_or_initiation",
    "occurrence_basis",
    "earliest_documented_public_date",
    "public_date_basis",
    "fda_weekly_date",
    "pre_exposure_basis_and_limit",
    "observed_path",
    "substitution_evidence_and_limit",
    "path_grade",
    "primary_url",
    "secondary_url",
]
case_rows = []
for a in cases:
    case_rows.append(dict(zip(fields, [*a[:-2], urls[a[-2]], urls[a[-1]]])))
write("audited_shock_routes.csv", case_rows)

with ZipFile(S1) as z, z.open("derived/bls_work_stoppages_2023_2025.csv") as f:
    bls = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8")))
s1 = {
    "2023-06-22-640": ("WAB", "work stoppage; customer program scope not verified"),
    "2023-06-23-641": ("SPR", "S1 named buyer plus two second-hop 737 MAX paths"),
    "2023-09-15-648": ("F|GM|STLA", "S1 coordinated event; three employers one root"),
    "2024-09-13-683": ("BA", "S1 mixed directions; 737 MAX and supplier scope"),
    "2025-08-04-717": (
        "BA",
        "S1 defense unit; do not attach commercial-plane exposures",
    ),
}
candidate = {
    "2023-10-17-654": "MGM",
    "2023-11-22-660": "HCA",
    "2023-12-07-662": "DHL.DE",
    "2024-07-26-676": "DIS|EA|MSFT|SONY|TTWO|WBD",
    "2024-08-16-677": "T",
    "2024-08-28-681": "KR",
    "2024-09-01-682": "HLT|H|MAR",
    "2024-09-23-684": "TXT",
    "2024-09-23-685": "ARMK",
    "2024-10-18-687": "CVS",
    "2024-12-19-694": "AMZN",
    "2024-12-20-695": "SBUX",
    "2025-02-06-697": "KR",
    "2025-05-05-707": "RTX",
    "2025-06-20-712": "ACI",
    "2025-07-08-714": "RSG",
    "2025-10-30-721": "THC",
    "2025-11-13-722": "SBUX",
}
temp = {}
dates = Counter()
for x in bls:
    k = x["campaign_id"]
    dates[k] += 1
    temp.setdefault(k, x)
joined = []
for k, x in temp.items():
    tickers, evidence = s1.get(
        k,
        (
            candidate.get(k, ""),
            "employer name search lead; verify entities, effective control and affected business",
        ),
    )
    grade = (
        "S1_SCOPE_CARRIED"
        if k in s1
        else ("EMPLOYER_LEAD_ONLY" if tickers else "NO_ISSUER_LINK_ADMITTED")
    )
    joined.append(
        {
            "campaign_id": k,
            "start_date": x["Work stoppage beginning date"],
            "record_count": dates[k],
            "organizations": x["Organizations involved"],
            "union_acronym": x["Union acronym"],
            "industry_code": x["Industry code[1]"],
            "provisional_issuer_reference": tickers,
            "status": grade,
            "scope": evidence if tickers else "",
            "first_public_date": "2024-09-21T23:34:00Z"
            if k == "2024-09-23-684"
            else "2025-05-04"
            if k == "2025-05-05-707"
            else "",
            "official_roster": urls["bls_root"],
        }
    )
write("bls_event_first_91.csv", joined)
print(
    "audited rows",
    len(case_rows),
    Counter(x["path_grade"] for x in case_rows),
    "BLS",
    len(joined),
    Counter(x["status"] for x in joined),
)
