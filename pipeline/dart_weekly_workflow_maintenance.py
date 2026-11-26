"""Exact, reviewable operational workflow delta; no historical pin is rewritten."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

BASE = "4f4497bcc9e7f9369bf5529225585ad39b0d7725"
WORKFLOW = ".github/workflows/fundamentals.yml"
ORIGINAL_BLOB = "52b54a56ce3f1c016371fa631e670d030af9e8fe"

# All allowed differences from the original workflow. Anything else fails closed.
REPLACEMENTS = (
    ("    - cron: \"40 3 * * *\"\n",
     "    - cron: \"40 3 * * *\"\n    # Weekly raw refresh: Wednesday 04:17 KST, same serialized writer.\n    - cron: \"17 19 * * 2\"\n", 1),
    ("    if: github.event_name == 'schedule' || ((inputs.region == 'both' || inputs.region == 'kr') && !startsWith(inputs.target, 'raw-'))\n",
     "    if: (github.event_name != 'schedule' || github.event.schedule == '40 3 * * *') && (github.event_name == 'schedule' || ((inputs.region == 'both' || inputs.region == 'kr') && !startsWith(inputs.target, 'raw-')))\n", 1),
    ("    if: github.event_name == 'schedule' || ((inputs.region == 'both' || inputs.region == 'us') && !startsWith(inputs.target, 'raw-'))\n",
     "    if: (github.event_name != 'schedule' || github.event.schedule == '40 3 * * *') && (github.event_name == 'schedule' || ((inputs.region == 'both' || inputs.region == 'us') && !startsWith(inputs.target, 'raw-')))\n", 1),
    ("    if: github.event_name == 'workflow_dispatch' && startsWith(inputs.target, 'raw-')\n",
     "    if: (github.event_name == 'schedule' && github.event.schedule == '17 19 * * 2' && github.ref == 'refs/heads/main') || (github.event_name == 'workflow_dispatch' && startsWith(inputs.target, 'raw-'))\n", 1),
    ("      - name: Collect a slice of raw statement rows\n        if: inputs.target == 'raw-statements'\n        env:\n          DART_API_KEY: ${{ secrets.DART }}\n        run: |\n          set -o pipefail\n          python scripts/collect_dart_raw_statements.py raw-work/ledger/fundamentals/kr-raw \\\n            --universe-dir sealed-work/ledger/universe/kr --mode collect \\\n            --years \"${{ inputs.raw_years || '2015,2016,2024,2025,2023,2017,2018,2019,2020,2021,2022,2026' }}\" \\\n            --max-calls \"${{ inputs.max_calls || '1800' }}\" \\\n            --max-minutes \"${{ inputs.max_minutes || '290' }}\" | tee raw.log\n",
     "      - name: Collect a slice of raw statement rows\n        if: (github.event_name == 'schedule' && github.event.schedule == '17 19 * * 2' && github.ref == 'refs/heads/main') || inputs.target == 'raw-statements'\n        env:\n          DART_API_KEY: ${{ secrets.DART }}\n          EVENT_NAME: ${{ github.event_name }}\n          RAW_YEARS: ${{ inputs.raw_years || '2015,2016,2024,2025,2023,2017,2018,2019,2020,2021,2022,2026' }}\n          MAX_CALLS: ${{ inputs.max_calls || '1800' }}\n          MAX_MINUTES: ${{ inputs.max_minutes || '290' }}\n        run: |\n          set -euo pipefail\n          if [ \"$EVENT_NAME\" = schedule ]; then\n            # Require both collector repairs before the scheduled route can write.\n            grep -q '^def prioritize_refresh(' scripts/collect_dart_raw_statements.py\n            grep -q '^def fetch_statement_evidence(' scripts/collect_dart_fundamentals.py\n            year=\"$(date -u +%Y)\"\n            previous=\"$((year - 1))\"\n            month=\"$(date -u +%m)\"\n            case \"$month\" in\n              01|02|03|04) RAW_YEARS=\"$previous,$year\" ;;\n              *) RAW_YEARS=\"$year,$previous\" ;;\n            esac\n            MAX_CALLS=600\n            MAX_MINUTES=120\n          fi\n          python scripts/collect_dart_raw_statements.py raw-work/ledger/fundamentals/kr-raw \\\n            --universe-dir sealed-work/ledger/universe/kr --mode collect \\\n            --years \"$RAW_YEARS\" --max-calls \"$MAX_CALLS\" \\\n            --max-minutes \"$MAX_MINUTES\" | tee raw.log\n", 1),
    ("      - name: Rebuild canonical filings and audit the candidate's coverage\n        if: inputs.target == 'raw-statements'\n",
     "      - name: Rebuild canonical filings and audit the candidate's coverage\n        if: (github.event_name == 'schedule' && github.event.schedule == '17 19 * * 2' && github.ref == 'refs/heads/main') || inputs.target == 'raw-statements'\n        env:\n          EVENT_NAME: ${{ github.event_name }}\n", 1),
    ("          if [ -d raw-work/ledger/fundamentals/kr-xbrl-original ]; then\n",
     "          if [ \"$EVENT_NAME\" != schedule ] && [ -d raw-work/ledger/fundamentals/kr-xbrl-original ]; then\n", 1),
    ("        if: inputs.target == 'raw-statements' || inputs.target == 'raw-xbrl-2015'\n        run: |\n          cd raw-work\n",
     "        if: (github.event_name == 'schedule' && github.event.schedule == '17 19 * * 2' && github.ref == 'refs/heads/main') || inputs.target == 'raw-statements' || inputs.target == 'raw-xbrl-2015'\n        env:\n          EVENT_NAME: ${{ github.event_name }}\n        run: |\n          cd raw-work\n", 1),
    ("          for path in ledger/fundamentals/kr-raw ledger/fundamentals/kr-canonical-v2 \\\n                      ledger/fundamentals/kr-xbrl-original ledger/fundamentals/kr-candidate-merged; do\n            if [ -e \"$path\" ]; then\n              git add \"$path\"\n            fi\n          done\n",
     "          paths=(ledger/fundamentals/kr-raw ledger/fundamentals/kr-canonical-v2)\n          if [ \"$EVENT_NAME\" != schedule ]; then\n            paths+=(ledger/fundamentals/kr-xbrl-original ledger/fundamentals/kr-candidate-merged)\n          fi\n          for path in \"${paths[@]}\"; do\n            if [ -e \"$path\" ]; then\n              git add \"$path\"\n            fi\n          done\n", 1),
)


def variant(original: bytes) -> bytes:
    candidate = original
    for old, new, count in REPLACEMENTS:
        old_bytes, new_bytes = old.encode(), new.encode()
        if candidate.count(old_bytes) != count:
            raise ValueError("DART_WEEKLY_WORKFLOW_BASE_CHANGED")
        candidate = candidate.replace(old_bytes, new_bytes)
    return candidate


def historical_bytes(root: Path) -> bytes:
    """Retrieve exact Git bytes; callers still verify the historical tree digest."""
    original = subprocess.check_output(
        ["git", "--no-replace-objects", "show", BASE + ":" + WORKFLOW], cwd=root)
    git_blob = b"blob " + str(len(original)).encode() + b"\0" + original
    if hashlib.sha1(git_blob, usedforsecurity=False).hexdigest() != ORIGINAL_BLOB:
        raise ValueError("DART_WEEKLY_HISTORICAL_BLOB_CHANGED")
    return original


def original_for_census(root: Path) -> bytes:
    original = historical_bytes(root)
    live = (root / WORKFLOW).read_bytes()
    if live != variant(original):
        raise ValueError("DART_WEEKLY_WORKFLOW_UNREGISTERED_DELTA")
    return original
