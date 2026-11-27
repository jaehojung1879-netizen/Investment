"""Reproduce S4 source diagnostics and identification examples (Python 3.11+)."""

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import xlrd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
RESULT = HERE / "results" / "diagnostics.json"
START, END = date(2010, 1, 1), date(2025, 12, 31)
FIRST_MODEL_DATE = date(2009, 10, 30)
WEEK = timedelta(days=7)
SERIES = {
    "WGIRIP32": ("gross_padd3_kbd", 4, "Gross Inputs into Refineries"),
    "WGIRIP22": ("gross_padd2_kbd", 4, "Gross Inputs into Refineries"),
    "WGIRIP42": ("gross_padd4_kbd", 4, "Gross Inputs into Refineries"),
    "WGTSTP31": ("stock_padd3_kb", 4, "Ending Stocks of Total Gasoline"),
    "WGTSTP11": ("stock_padd1_kb", 4, "Ending Stocks of Total Gasoline"),
    "EMM_EPMR_PTE_R30_DPG": ("retail_padd3_usdgal", 0, "Regular All Formulations Retail Gasoline"),
    "EMM_EPMR_PTE_R10_DPG": ("retail_padd1_usdgal", 0, "Regular All Formulations Retail Gasoline"),
}
MONTHLY = {
    "MBCMXP1P31": "Gasoline Blending Components",
    "MGFMXP1P31": "Finished Motor Gasoline",
}
NOAA_FIELDS = (
    "SEASON", "SID", "NAME", "ISO_TIME", "TRACK_TYPE", "USA_ATCF_ID",
    "USA_LAT", "USA_LON", "USA_RECORD", "USA_STATUS", "USA_WIND",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_noaa(upstream, destination):
    """Archive the relevant agency's fields for every flagged NA landfall."""
    manifest = json.loads((DATA / "source-manifest.json").read_text())
    expected = manifest["noaa_original"]["sha256"]
    if digest(upstream) != expected:
        raise ValueError("NOAA download differs from the archived source vintage")
    with upstream.open(newline="") as source, destination.open("w", newline="") as output:
        reader = csv.DictReader(source)
        next(reader)  # units line
        writer = csv.DictWriter(output, fieldnames=NOAA_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in reader:
            if START.year <= int(row["SEASON"]) <= END.year and row["USA_RECORD"].strip() == "L":
                writer.writerow({key: row[key].strip() for key in NOAA_FIELDS})


def verify_sources():
    manifest = json.loads((DATA / "source-manifest.json").read_text())
    for item in manifest["archived_files"]:
        path = DATA / item["file"]
        if path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
            raise ValueError(f"Source mismatch: {path.name}")


def read_eia(code, title_fragment, weekday=None):
    book = xlrd.open_workbook(str(DATA / f"{code}.xls"), on_demand=True)
    try:
        ws = book.sheet_by_name("Data 1")
        if ws.cell_value(1, 1) != code or title_fragment not in ws.cell_value(2, 1):
            raise ValueError(f"EIA title or series ID mismatch: {code}")
        values = {}
        previous = date.min
        for row in range(3, ws.nrows):
            excel_day, value = ws.row_values(row)
            day = xlrd.xldate_as_datetime(excel_day, book.datemode).date()
            if day <= previous or (weekday is not None and day.weekday() != weekday):
                raise ValueError(f"Date order or weekday error: {code} {day.isoformat()}")
            if not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid observation: {code} {day.isoformat()}")
            values[day] = value
            previous = day
        return values
    finally:
        book.release_resources()


def load_series():
    profiles, series = {}, {}
    for code, (name, weekday, title_fragment) in SERIES.items():
        values = read_eia(code, title_fragment, weekday)
        missing = []
        study_days = sorted(day for day in values if START <= day <= END)
        model_day = FIRST_MODEL_DATE + timedelta(days=(weekday - FIRST_MODEL_DATE.weekday()) % 7)
        while model_day <= END:
            if model_day not in values:
                missing.append(model_day.isoformat())
            model_day += WEEK
        if missing:
            raise ValueError(f"Missing in study window for {code}: {missing}")
        profiles[name] = {
            "series": code,
            "study_weeks": len(study_days),
            "start": study_days[0].isoformat(),
            "end": study_days[-1].isoformat(),
            "missing_weeks_with_warmup": len(missing),
        }
        series[name] = values
    return series, profiles


def monthly_receipts():
    monthly = {}
    expected_months = {(year, month) for year in range(START.year, END.year + 1) for month in range(1, 13)}
    for code, title_fragment in MONTHLY.items():
        series = {(day.year, day.month): value for day, value in read_eia(code, title_fragment).items()
                  if START <= day <= END}
        if series.keys() != expected_months:
            raise ValueError(f"Missing or unexpected months: {code}")
        monthly[code] = series
    return {
        "months_per_series": len(expected_months),
        "source_series": list(MONTHLY),
        "padd3_to_padd1_receipts_kb": {
            f"{year}-{month:02d}": {
                "blending_components": monthly["MBCMXP1P31"][year, month],
                "finished_gasoline": monthly["MGFMXP1P31"][year, month],
            }
            for year in (2017, 2021)
            for month in (7, 8, 9, 10)
        },
    }


def load_storms():
    with (DATA / "noaa-na-landfalls-2010-2025.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    key_fields = ("SID", "ISO_TIME", "USA_LAT", "USA_LON")
    if len({tuple(row[key] for key in key_fields) for row in rows}) != len(rows):
        raise ValueError("Duplicate landfall coordinates/times in projected NOAA source")
    candidates = defaultdict(list)
    for row in rows:
        if row["TRACK_TYPE"] != "main" or row["USA_RECORD"] != "L" or row["USA_STATUS"] != "HU":
            continue
        if not (25.4 <= float(row["USA_LAT"]) <= 31.2 and -98 <= float(row["USA_LON"]) <= -87):
            continue
        landfall = datetime.fromisoformat(row["ISO_TIME"])
        candidates[row["USA_ATCF_ID"]].append(
            (landfall, row["NAME"], float(row["USA_LAT"]), float(row["USA_LON"]), int(row["USA_WIND"]))
        )
    storms = []
    for atcf, readings in candidates.items():
        first, name, lat, lon, wind = min(readings)
        storms.append({
            "atcf_id": atcf, "name": name, "landfall_utc": first.isoformat() + "Z",
            "lat": lat, "lon": lon, "wind_knots": wind, "landfalls_in_box": len(readings),
        })
    return sorted(storms, key=lambda storm: storm["landfall_utc"]), len(rows)


def landfall_day(storm):
    return date.fromisoformat(storm["landfall_utc"][:10])


def clusters(storms, gap):
    """Use transitive consecutive date gaps to avoid counting connected windows twice."""
    blocks = []
    for storm in storms:
        if blocks and (landfall_day(storm) - landfall_day(blocks[-1][-1])).days <= gap:
            blocks[-1].append(storm)
        else:
            blocks.append([storm])
    return blocks


def next_weekday(day, weekday):
    """First named weekday strictly after the date."""
    return day + timedelta(days=(weekday - day.weekday() - 1) % 7 + 1)


def pct_change(new, old):
    return round(100 * (new / old - 1), 6)


def measure_block(block, series):
    first = block[0]
    event_day = landfall_day(first)
    t0 = next_weekday(event_day, 4)
    physical = {key: values for key, values in series.items() if not key.endswith("usdgal")}
    before, current = t0 - WEEK, t0
    row = {
        "atcf_ids": [storm["atcf_id"] for storm in block],
        "storm_names": [storm["name"] for storm in block],
        "week_0": t0.isoformat(),
        "physical_week_path": [
            {"offset": offset, "date": (t0 + offset * WEEK).isoformat(),
             **{key: values[t0 + offset * WEEK] for key, values in physical.items()}}
            for offset in range(-2, 4)
            if len(block) == 1 or t0 + offset * WEEK < landfall_day(block[1])
        ],
        "delta_0_vs_previous_friday": {
            key: values[current] - values[before] for key, values in physical.items()
        },
    }
    for key in ("gross_padd3_kbd", "gross_padd2_kbd", "gross_padd4_kbd"):
        values = physical[key]
        row[f"{key}_change_pct"] = pct_change(values[current], values[before])
    row["recorded_padd3_gasoline_draw_kb"] = max(
        0, -row["delta_0_vs_previous_friday"]["stock_padd3_kb"]
    )

    pre_price = event_day - timedelta(days=(event_day.weekday() - 1) % 7 + 1)
    post_price = next_weekday(event_day, 0)
    row["price_clock"] = {
        "strictly_preceding_monday": pre_price.isoformat(),
        "strictly_following_monday": post_price.isoformat(),
        "next_monday": (post_price + WEEK).isoformat(),
    }
    row["price_usdgal"] = {
        key: [values[day] for day in (pre_price, post_price, post_price + WEEK)]
        for key, values in series.items() if key.endswith("usdgal")
    }
    q = physical["gross_padd3_kbd"]
    x = list(range(-9, -1))
    y = [q[t0 + offset * WEEK] for offset in x]
    line = statistics.linear_regression(x, y)
    row["descriptive_base_t0_kbd"] = {"last_minus_2": q[t0 - 2 * WEEK], "ols_minus_9_to_2": line.intercept}
    row["observed_gross_t0_kbd"] = q[t0]
    return row


def check_archived_gross_inputs(releases, series):
    comparisons = []
    for release in releases:
        weeks = [date.fromisoformat(release[key]) for key in ("current_week", "previous_week")]
        for key in ("gross_padd2_kbd", "gross_padd3_kbd", "gross_padd4_kbd"):
            for week, archived in zip(weeks, release[key], strict=True):
                comparisons.append({
                    "week_ending": week.isoformat(), "series": key, "archived_kbd": archived,
                    "current_kbd": series[key][week],
                })
    return {
        "match": sum(row["archived_kbd"] == row["current_kbd"] for row in comparisons),
        "compared": len(comparisons),
        "weeks_with_first_release_table": len(releases),
        "comparisons": comparisons,
    }


def mathematical_examples(real_q, real_d_inventory):
    # The following are constructed hidden states conditional on two measurements.
    # Amounts in kb/week for the inventory decomposition, kbd for throughput.
    supply = {"available_capacity_kbd": real_q, "desired_inputs_kbd": real_q + 1_000}
    demand = {"available_capacity_kbd": real_q + 1_000, "desired_inputs_kbd": real_q}
    inventory_addition = max(0, real_d_inventory)
    inventory_withdrawal = max(0, -real_d_inventory)
    # Both combinations give the same closed-loop state coefficient.
    k = 0.5
    reduced = [a + b * k for a, b in ((0.4, 0.8), (0.7, 0.2))]
    if not math.isclose(*reduced):
        raise AssertionError("Closed-loop examples must agree")
    # With a known diagonal state matrix and y = x1 + x2, det(O) = a2 - a1.
    observability = {"same_decay_det": 0.8 - 0.8, "distinct_decay_det": 0.9 - 0.8}

    multiple, tax, roic = 2.0, 0.25, 0.12
    g_lo, g_hi, g_cap = 0.02, 0.06, 0.04
    r_lo, r_hi = 0.07, 0.11
    margin_min, margin_max = 0.10, 0.18

    def margin(r, g):
        return multiple * (r - g) / ((1 - tax) * (1 + g) * (1 - g / roic))

    def rate(m, g):
        return g + m * (1 - tax) * (1 + g) * (1 - g / roic) / multiple

    projection = [margin(r_lo, g_hi), margin(r_hi, g_lo)]
    capped = [margin(r_lo, g_cap), margin(r_hi, g_lo)]
    feasible = [max(capped[0], margin_min), min(capped[1], margin_max)]
    if not feasible[0] <= feasible[1]:
        raise AssertionError("Illustrative parameter set unexpectedly empty")
    return {
        "capacity_equivalence_kbd": [supply, demand],
        "inventory_equivalence_kb": [
            {"inflow": inventory_addition + d, "outflow": inventory_withdrawal + d} for d in (0, 2_000)
        ],
        "closed_loop_reduced_coefficients": [round(value, 8) for value in reduced],
        "observability_determinants": {key: round(value, 8) for key, value in observability.items()},
        "dcf": {
            "margin_projection_baseline": projection,
            "margin_projection_with_growth_cap": capped,
            "margin_projection_with_both_caps": feasible,
            "max_compatible_discount_rate_at_growth_cap": rate(margin_max, g_cap),
            "margin_required_at_nine_pct_discount_and_growth_cap": margin(0.09, g_cap),
            "example_fixed_r_9pct": {str(g): margin(0.09, g) for g in (g_lo, g_cap, g_hi)},
        },
    }


def derive():
    verify_sources()
    series, profiles = load_series()
    storms, projected_landfalls = load_storms()
    blocks = clusters(storms, 28)
    measurements = [measure_block(block, series) for block in blocks]
    harvey = next(row for row in measurements if "HARVEY" in row["storm_names"])
    doe = json.loads((DATA / "document-crosscheck.json").read_text())
    count_by_id = {storm["atcf_id"]: storm for storm in storms}
    for item in doe["capacity_snapshots"]:
        if item["atcf_id"] not in count_by_id or item["shut_nameplate_kbd"] <= 0:
            raise ValueError("DOE corroboration missing an eligible physical shock candidate")
    mae = {key: statistics.mean(
        abs(row["descriptive_base_t0_kbd"][key] - row["observed_gross_t0_kbd"]) for row in measurements
    ) for key in ("last_minus_2", "ols_minus_9_to_2")}
    return {
        "status": "EXPLORATORY_CURRENT_VINTAGE",
        "series": profiles,
        "noaa_archive_landfall_rows": projected_landfalls,
        "matched_landfall_rows": sum(storm["landfalls_in_box"] for storm in storms),
        "candidate_storms": storms,
        "cluster_counts_by_max_gap_days": {str(d): len(clusters(storms, d)) for d in (14, 28, 42, 56)},
        "capacity_corroborated_cluster_count": len({
            tuple(row["atcf_ids"]) for row in measurements
            if any(item["atcf_id"] in row["atcf_ids"] for item in doe["capacity_snapshots"])
        }),
        "confirmed_causal_clusters": 0,
        "episodes": measurements,
        "descriptive_benchmark_mae_kbd": mae,
        "gross_input_first_release_spot_check": check_archived_gross_inputs(doe["eia_first_reports"], series),
        "monthly_transport": monthly_receipts(),
        "storm_design_mde_sd_at_normal_80pct": {
            str(n): (1.959964 + 0.841621) / math.sqrt(n) for n in (9, 13, 32, 88)
        },
        "mathematical_examples": mathematical_examples(
            harvey["observed_gross_t0_kbd"], harvey["delta_0_vs_previous_friday"]["stock_padd3_kb"]
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="verify the saved result without writing")
    action.add_argument("--project-noaa", type=Path, help="recreate the projected source from exact NOAA bytes")
    args = parser.parse_args()
    if args.project_noaa:
        project_noaa(args.project_noaa, DATA / "noaa-na-landfalls-2010-2025.csv")
        verify_sources()
        return
    result = json.dumps(derive(), indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.check:
        if RESULT.read_text() != result:
            raise SystemExit(f"Result does not reproduce: {RESULT}")
        print(f"Verified {RESULT.name}")
    else:
        RESULT.write_text(result)


if __name__ == "__main__":
    main()
