import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

raw = Path("raw")
metadata = json.loads((raw / "fda_download.json").read_text())
sources = {
    "device": [
        "enforcement",
        "recall",
        "510k",
        "classification",
        "registrationlisting",
    ],
    "drug": ["enforcement", "shortages"],
    "food": ["enforcement"],
}
tasks = []
for group, keys in sources.items():
    print(group, list(metadata["results"][group]), flush=True)
    for key in keys:
        record = metadata["results"][group].get(key)
        if not record:
            continue
        for i, p in enumerate(record["partitions"]):
            name = f"fda_{group}_{key}_{i:02d}.zip"
            tasks.append((name, p["file"], p["size_mb"], p.get("display_name")))
        print(
            group,
            key,
            len(record["partitions"]),
            [i for i in tasks if i[0].startswith(f"fda_{group}_{key}_")][:4],
            flush=True,
        )


def fetch(item):
    name, url, *_ = item
    dst = raw / name
    if dst.exists() and dst.stat().st_size > 100:
        return
    r = subprocess.run(
        [
            "curl",
            "-fsSL",
            "--retry",
            "1",
            "--max-time",
            "90",
            "-o",
            str(dst),
            "-w",
            "%{http_code} %{size_download}",
            url,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    print(name, r.stdout, r.stderr[:100], flush=True)
    if r.returncode:
        dst.unlink(missing_ok=True)


with ThreadPoolExecutor(7) as exe:
    list(exe.map(fetch, tasks))
(raw / "fda_acquire_config.json").write_text(json.dumps(tasks, indent=2))
