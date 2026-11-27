import json
import subprocess
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAW = Path("raw")
BASE = "https://api.usaspending.gov/api/v2/"


def curl(url, out, request=None):
    argv = ["curl", "-fsSL", "--max-time", "40", "-o", str(out), url]
    if request is not None:
        argv += [
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            "@" + str(request),
        ]
    r = subprocess.run(argv, check=False, capture_output=True, text=True)
    if r.returncode:
        print(out, r.returncode, r.stderr[:220], flush=True)
    return r.returncode == 0


code_agency = {
    "NASA": "National Aeronautics and Space Administration",
    "HHS": "Department of Health and Human Services",
    "DOE": "Department of Energy",
}


def agency(item):
    code, name = item
    request = RAW / f"usa_{code}_bulk_request.json"
    response = RAW / f"usa_{code}_bulk_response.json"
    status = RAW / f"usa_{code}_bulk_status.json"
    request.write_text(
        json.dumps(
            {
                "filters": {
                    "prime_award_types": ["A", "B", "C", "D"],
                    "date_type": "action_date",
                    "date_range": {
                        "start_date": "2024-10-01",
                        "end_date": "2024-10-31",
                    },
                    "agencies": [{"type": "awarding", "tier": "toptier", "name": name}],
                },
                "file_format": "csv",
            },
            indent=2,
        )
        + "\n"
    )
    if not curl(BASE + "bulk_download/awards/", response, request):
        return
    b = json.loads(response.read_text())
    print(code, b.get("file_name"), flush=True)
    for _ in range(15):
        if not curl(b["status_url"], status):
            break
        s = json.loads(status.read_text())
        if s.get("status") in {"finished", "success"}:
            url = b["file_url"]
            if urllib.parse.urlparse(url).hostname != "files.usaspending.gov":
                raise ValueError(url)
            result = curl(url, RAW / f"usa_{code}_bulk.zip")
            print(code, "full archive", result, flush=True)
            break
        if s.get("status") in {"failed", "error"}:
            print(code, s, flush=True)
            break
        time.sleep(3)


with ThreadPoolExecutor(3) as ex:
    list(ex.map(agency, code_agency.items()))
