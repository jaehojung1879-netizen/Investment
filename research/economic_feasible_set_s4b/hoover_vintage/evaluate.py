"""Compare vintaged public Hoover forecasts with a fixed seasonal baseline."""

import argparse
import calendar
import csv
import hashlib
import io
import json
import math
import re
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path

from reproduce import physical_energy_cap_gwh

HERE = Path(__file__).resolve().parent
MONTHS = {name: i for i, name in enumerate(calendar.month_abbr) if name}
METHODS = ("prior_season", "official", "volume_scaled", "cap_only")
MAX_HEAD_FT = 590
ROUNDING_KAF = 0.5
ROW = re.compile(
    rf"^\s*(?:([HISTORCAL*])\s+)?({'|'.join(MONTHS)})\s+(\d{{4}})\s+(.+?)\s*$"
)


@dataclass(frozen=True)
class OperatingMonth:
    release_kaf: float
    gross_gwh: float


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report_rows(record):
    path = HERE / record["file"]
    if path.stat().st_size != record["bytes"] or sha(path) != record["sha256"]:
        raise ValueError(f"Archive bytes changed: {path.name}")
    report = subprocess.check_output(["pdftotext", "-layout", str(path), "-"], text=True)
    pages = report.split("\f")
    matches = [
        (page_no, page) for page_no, page in enumerate(pages, 1)
        if re.search(r"Hoover Dam [–-] Lake Mead", page) and "Gross Energy" in page and "MKWH" in page
    ]
    if len(matches) != 1 or matches[0][0] != record["table_page"]:
        raise ValueError(f"Cannot uniquely locate the pinned Hoover gross energy page: {path.name}")
    _, page = matches[0]
    year = record["issue_year"]
    if f"November {year} 24-Month Study" not in page or "Most Probable Inflow" not in page:
        raise ValueError(f"Wrong issue or scenario: {path.name}")
    if record["historical_through"] != f"{year}-10":
        raise ValueError(f"Unexpected November cutoff: {path.name}")
    # Older editions spell HISTORICAL vertically. The newer pinned copies
    # indicate the same November boundary with shading, verified at intake.
    if record["historical_basis"] == "vertical_historical_label":
        expected = "".join(re.findall(r"^\s*([HISTORCAL])\s+[A-Z][a-z]{2}\s+\d{4}", page, re.MULTILINE))
        if expected != "HISTORICAL":
            raise ValueError(f"Missing historical marker: {path.name}")
    if not re.search(r"historical gross energy\s*f\s*i?gures", report, re.IGNORECASE):
        raise ValueError(f"Missing gross generation provenance note: {path.name}")
    if record["issue_day_printed"] and record["issue_day_printed"] not in report:
        raise ValueError(f"Missing exact date receipt: {path.name}")
    result = {}
    for line in page.splitlines():
        row = ROW.fullmatch(line)
        if not row:
            continue
        marker, month, row_year, columns = row.groups()
        fields = columns.split()
        if len(fields) != 10:
            raise ValueError(f"Unexpected value columns in {path.name}: {line}")
        values = [float(field.replace(",", "")) for field in fields]
        key = (int(row_year), MONTHS[month])
        if record["historical_basis"] == "vertical_historical_label" and bool(marker) != (key <= (year, 10)):
            raise ValueError(f"Historical marker conflicts with the November boundary: {path.name} {key}")
        if key in result or not all(math.isfinite(v) for v in values) or min(values[0], values[7]) < 0:
            raise ValueError(f"Duplicate or invalid operating row: {path.name} {key}")
        result[key] = OperatingMonth(release_kaf=values[0], gross_gwh=values[7])
    return result


def score_year(issue, months, origin, resolution):
    years = (issue, issue + 1)
    inputs = [(m, origin[years[0], m], origin[years[1], m], resolution[years[1], m]) for m in months]
    prior_release = sum(prior.release_kaf for _, prior, _, _ in inputs)
    if prior_release <= 0:
        raise ValueError(f"Zero historic energy denominator: {issue}")
    output_per_kaf = sum(prior.gross_gwh for _, prior, _, _ in inputs) / prior_release
    rows = []
    for month, prior, projected, actual in inputs:
        upper = physical_energy_cap_gwh(projected.release_kaf + ROUNDING_KAF, MAX_HEAD_FT)
        realized_upper = physical_energy_cap_gwh(actual.release_kaf + ROUNDING_KAF, MAX_HEAD_FT)
        rows.append({
            "origin_year": issue, "target_year": issue + 1, "month": month,
            "prior_release_kaf": prior.release_kaf, "projected_release_kaf": projected.release_kaf,
            "resolved_release_kaf": actual.release_kaf, "realized_gwh": actual.gross_gwh,
            "prior_season": prior.gross_gwh, "official": projected.gross_gwh,
            "volume_scaled": output_per_kaf * projected.release_kaf,
            "cap_only": min(prior.gross_gwh, upper),
            "conditional_cap_gwh": upper, "measured_release_cap_gwh": realized_upper,
            "prior_above_conditional_cap": prior.gross_gwh > upper,
            "actual_above_conditional_cap": actual.gross_gwh > upper,
            "actual_above_measured_release_cap": actual.gross_gwh > realized_upper,
        })
    actual_gwh = sum(row["realized_gwh"] for row in rows)
    forecasts = {key: sum(row[key] for row in rows) for key in METHODS}
    actual_release = sum(row["resolved_release_kaf"] for row in rows)
    projected_release = sum(row["projected_release_kaf"] for row in rows)
    volume_effect = (projected_release - actual_release) * output_per_kaf
    conversion_effect = actual_release * output_per_kaf - actual_gwh
    if not math.isclose(forecasts["volume_scaled"] - actual_gwh, volume_effect + conversion_effect, abs_tol=1e-8):
        raise ValueError(f"Water / conversion arithmetic does not reconcile: {issue}")
    block = {
        "issue_year": issue, "target_year": issue + 1,
        "actual_gwh": round(actual_gwh, 3),
        "forecast_gwh": {k: round(v, 3) for k, v in forecasts.items()},
        "error_gwh": {k: round(v - actual_gwh, 3) for k, v in forecasts.items()},
        "volume_scaled_error_arithmetic_gwh": {
            "forecast_water_delta_at_prior_conversion": round(volume_effect, 3),
            "remaining_actual_conversion_delta": round(conversion_effect, 3),
        },
    }
    return block, rows


def compare_blocks(blocks):
    metrics = {}
    for method in METHODS:
        errors = [block["error_gwh"][method] for block in blocks]
        paired = [abs(block["error_gwh"]["prior_season"]) - abs(block["error_gwh"][method]) for block in blocks]
        wins = [delta > 1e-8 for delta in paired]
        ties = [abs(delta) <= 1e-8 for delta in paired]
        metrics[method] = {
            "mae_gwh": round(statistics.mean(abs(error) for error in errors), 3),
            "mean_signed_error_gwh": round(statistics.mean(errors), 3),
            "mean_absolute_improvement_vs_prior_season_gwh": round(statistics.mean(paired), 3),
            "wins_ties_losses_vs_prior_season": [sum(wins), sum(ties), len(blocks) - sum(wins) - sum(ties)],
        }
    return metrics


def build():
    design_path = HERE / "design.json"
    design = json.loads(design_path.read_text())
    manifest = json.loads((HERE / "sources.json").read_text())
    if sha(design_path) != manifest["design_sha256"]:
        raise ValueError("The scoped development design has changed")
    years = design["origin_years"]
    months = design["target_months"]
    sources = {row["issue_year"]: row for row in manifest["sources"]}
    if len(sources) != len(manifest["sources"]) or set(sources) != set(years + [years[-1] + 1]):
        raise ValueError("Exactly the planned November issues must be accounted for")
    issues = {year: report_rows(row) for year, row in sources.items()}
    blocks, panel, unavailable = [], [], []
    for year in years:
        try:
            block, rows = score_year(year, months, issues[year], issues[year + 1])
        except KeyError as exc:
            unavailable.append({"issue_year": year, "missing_month": list(exc.args[0])})
            continue
        blocks.append(block)
        panel.extend(rows)
    if not blocks:
        raise ValueError("No matched targets")
    result = {
        "status": "EXPLORATORY_AUTHOR_VALIDATION_ONLY",
        "design_sha256": manifest["design_sha256"],
        "intended_year_blocks": len(years),
        "matched_year_blocks": len(blocks),
        "matched_month_rows": len(panel),
        "missing_target_blocks": unavailable,
        "target_is_public_single_basin": True,
        "metrics": compare_blocks(blocks),
        "months_prior_season_clipped": sum(row["prior_above_conditional_cap"] for row in panel),
        "months_actual_above_forecast_volume_cap": sum(row["actual_above_conditional_cap"] for row in panel),
        "months_actual_above_measured_volume_cap": sum(row["actual_above_measured_release_cap"] for row in panel),
        "annual_targets": blocks,
    }
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(panel[0]), lineterminator="\n")
    writer.writeheader()
    for row in panel:
        writer.writerow({key: round(value, 6) if isinstance(value, float) else value for key, value in row.items()})
    forecast_json = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    return {HERE / "results.json": forecast_json, HERE / "observations.csv": output.getvalue()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="replay and compare the saved results without writing")
    args = parser.parse_args()
    for output, computed in build().items():
        if args.check:
            if output.read_text() != computed:
                raise SystemExit(f"{output.name} differs from the archived source replay")
            print(f"Verified {output.name}")
        else:
            output.write_text(computed)


if __name__ == "__main__":
    main()
