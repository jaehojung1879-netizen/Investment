import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

more = {
    "hvad_manufacturer": "https://news.medtronic.com/2021-06-03-Medtronic-to-Stop-Distribution-and-Sale-of-HVAD-TM-System",
    "hvad_fda_recommendations": "https://www.fda.gov/medical-devices/cardiovascular-devices/recommendations-patients-and-health-care-providers-hvad-system",
    "textron_2024_notice": "https://media.txtav.com/241569-textron-aviation-news-update/",
    "pratt_2025_notice": "https://ctaflcio.org/press-room/strike-machinists-pratt-whitney-going-strike",
    "baxter_press_20240929": "https://www.sec.gov/Archives/edgar/data/10456/000162828024041545/bax-20240929xex991.htm",
    "baxter_cdc": "https://www.cdc.gov/healthcare-associated-infections/bulletins/shortage-of-iv-and-peritoneal-dialysis-solutions.html",
    "spirit_press": "https://www.prnewswire.com/news-releases/spirit-aerosystems-to-suspend-factory-operations-301857718.html",
    "bls_root": "https://www.bls.gov/web/wkstp/monthly-listing.htm",
    "fed_uaw": "https://www.federalreserve.gov/econres/notes/feds-notes/tapping-the-brakes-the-effect-of-the-2023-united-auto-workers-strike-on-economic-activity-20240416.html",
    "boeing_offer": "https://boeing.mediaroom.com/Boeing-Historic-Contract-Offer-and-Tentative-Agreement-with-IAM-Districts-751-W24",
    "mp_government": "https://www.defense.gov/News/Releases/Release/Article/4241350/department-of-defense-partners-with-mp-materials-to-strengthen-us-rare-earth/",
    "usa_about_data": "https://www.usaspending.gov/data/about-the-data-download.pdf",
}
raw = Path("raw")


def pull(pair):
    k, v = pair
    p = raw / (k + (".pdf" if v.endswith(".pdf") else ".html"))
    z = subprocess.run(
        ["curl", "-fsSL", "--retry", "1", "--max-time", "18", "-o", str(p), v],
        check=False,
        capture_output=True,
    )
    if z.returncode:
        p.unlink(missing_ok=True)
        print(k, z.stderr.decode()[:160], flush=True)


with ThreadPoolExecutor(6) as ex:
    list(ex.map(pull, more.items()))
(raw / "extra_urls.json").write_text(json.dumps(more, indent=2) + "\n")
