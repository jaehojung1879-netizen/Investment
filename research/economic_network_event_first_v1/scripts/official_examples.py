import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

S = {
    "fda_enforcement_definitions": "https://www.fda.gov/safety/enforcement-reports/enforcement-report-information-and-definitions",
    "fda_history": "https://www.fda.gov/safety/enforcement-reports/enforcement-report-history-feature",
    "fda_philips_20210614": "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/philips-issues-recall-notification-mitigate-potential-health-risks-related-sound-abatement-foam",
    "fda_philips_alternatives": "https://www.fda.gov/medical-devices/recalled-philips-ventilators-bipap-machines-and-cpap-machines/fda-activities-related-recalled-philips-ventilators-bipap-machines-and-cpap-machines",
    "fda_abbott_20220217": "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/abbott-voluntarily-recalls-powder-formulas-manufactured-one-plant",
    "fda_abbott_investigation": "https://www.fda.gov/food/outbreaks-foodborne-illness/fda-investigation-cronobacter-infections-powdered-infant-formula-february-2022",
    "fda_abbott_substitutes": "https://www.fda.gov/food/infant-formula-guidance-documents-regulatory-information/enforcement-discretion-manufacturers-increase-infant-formula-supplies",
    "cdc_bd_20240710": "https://www.cdc.gov/locs/php/messages/2024/2024-07-10-impending-shortage-blood-culture-media-bottles.html",
    "bd_20240710": "https://news.bd.com/2024-07-10-BD-Statement-on-Supplier-Issue-Impacting-BD-BACTEC-TM-Blood-Culture-Vials",
    "sec_mp_20250710": "https://www.sec.gov/Archives/edgar/data/1801368/000119312525157310/d43796d8k.htm",
    "sec_mp_capacity": "https://www.sec.gov/Archives/edgar/data/1801368/000119312525157310/d43796dex991.htm",
    "sec_celp_20251028": "https://www.sec.gov/Archives/edgar/data/1306830/000130683025000203/ce-20251028.htm",
    "sec_culp_20240429": "https://www.sec.gov/Archives/edgar/data/723603/000095017024051289/culp-20240429.htm",
    "sec_alcoa_20250929": "https://www.sec.gov/Archives/edgar/data/1675149/000119312525223652/aa-20250929.htm",
    "sec_rogers_20240606": "https://www.sec.gov/Archives/edgar/data/84748/000008474824000043/rog-20240606.htm",
    "sec_revg_20240125": "https://www.sec.gov/Archives/edgar/data/1687221/000095017024009141/revg-20240125.htm",
    "sec_nsys_20240515": "https://www.sec.gov/Archives/edgar/data/722313/000143774924017204/nsys20240515_8k.htm",
}
C = {
    "MP": 1801368,
    "CE": 1306830,
    "CULP": 723603,
    "AA": 1675149,
    "ROG": 84748,
    "REVG": 1687221,
    "NSYS": 722313,
    "PHG": 313216,
    "ABT": 1800,
    "BDX": 10795,
    "BAX": 10456,
    "BA": 12927,
    "SPR": 1364885,
    "RTX": 101829,
    "TXT": 217346,
    "WAB": 943452,
    "MDT": 1613103,
    "SYK": 310764,
    "ZBH": 1136869,
    "BSX": 885725,
    "GEHC": 1932393,
    "TMO": 97745,
    "JNJ": 200406,
    "PODD": 1145197,
    "DXCM": 1093557,
    "RMD": 943819,
    "FMS": 1333141,
    "ICUI": 883984,
    "TMDX": 1756262,
}
S.update(
    {
        f"sec_submissions_{k}": f"https://data.sec.gov/submissions/CIK{c:010d}.json"
        for k, c in C.items()
    }
)


def one(item):
    name, url = item
    ext = ".json" if name.startswith("sec_submissions") else ".html"
    file = Path("raw") / (name + ext)
    if file.exists() and file.stat().st_size > 4000:
        return
    time.sleep(0.4)
    result = subprocess.run(
        ["curl", "-fLsS", "--max-time", "26", "--retry", "1", "-o", str(file), url],
        check=False,
        capture_output=True,
    )
    if result.returncode:
        print(name, result.stderr.decode()[:170], flush=True)
        file.unlink(missing_ok=True)


with ThreadPoolExecutor(3) as ex:
    list(ex.map(one, S.items()))
Path("raw/official_urls.json").write_text(json.dumps(S, indent=2))
print(
    "Acquired",
    sum(
        (
            Path("raw")
            / (n + (".json" if n.startswith("sec_submissions") else ".html"))
        ).exists()
        for n in S
    ),
    "of",
    len(S),
)
