"""Replay source diagnostics and conditional valuation cases from preserved inputs."""

import argparse
import calendar
import csv
import hashlib
import io
import json
import re
import statistics
import subprocess
from collections import defaultdict
from dataclasses import replace
from html import unescape
from pathlib import Path
from zipfile import ZipFile

import xlrd
from scipy.integrate import quad
from scipy.optimize import brentq
from scipy.special import ndtr
from scipy.stats import chi2, t

from feasible import Bounds, Product, Scenario, evaluate

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
RESULT = HERE / "results" / "diagnostics.json"
EIA_IDS = {154: "NV", 8902: "AZ"}
EIA_ROW_KEYS = ("plant_id", "state", "operator_id", "prime_mover", "fuel", "year", "month", "net_mwh", "annual_mwh")
USBR_REPORTS = {
    "nov2025_most_probable": "NOV25.pdf",
    "nov2026_minimum": "NOV26_MIN.pdf",
    "nov2026_most_probable_7maf": "NOV26-MP-7MAF.pdf",
}
MONTHS = {abbr: i for i, abbr in enumerate(calendar.month_abbr) if abbr}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest():
    return json.loads((DATA / "sources.json").read_text())


def verify_sources():
    for source in manifest()["preserved"]:
        path = DATA / source["file"]
        if path.stat().st_size != source["bytes"] or sha256(path) != source["sha256"]:
            raise ValueError(f"Source bytes do not match: {path.name}")


def eia_extract(archive, output):
    """The only row selection accesses numeric/identifier fields of two federal plants."""
    import openpyxl

    if sha256(archive) != manifest()["eia923_original_archive"]["sha256"]:
        raise ValueError("EIA ZIP vintage changed")
    with ZipFile(archive) as z:
        files = [n for n in z.namelist() if "Schedules_2_3_4_5_M_12_2025_Final.xlsx" in n]
        if len(files) != 1:
            raise ValueError("EIA generation spreadsheet missing or ambiguous")
        workbook = openpyxl.load_workbook(io.BytesIO(z.read(files[0])), read_only=True, data_only=True)
        try:
            sheet = workbook["Page 1 Generation and Fuel Data"]
            rows = sheet.iter_rows(min_row=6, values_only=True)
            header = next(rows)
            if header[0] != "Plant Id" or header[95] != "Net Generation\n(Megawatthours)":
                raise ValueError("EIA 923 schema changed")
            if tuple(header[79:91]) != tuple(f"Netgen\n{m}" for m in list(calendar.month_name)[1:]):
                raise ValueError("EIA 923 month fields changed")
            records = []
            for row in rows:
                if row[0] not in EIA_IDS:
                    continue
                if (row[6], row[5], row[13], row[14], row[96]) != (EIA_IDS[row[0]], 2518, "HY", "WAT", 2025):
                    raise ValueError("Unexpected Hoover plant / fuel / operator identity")
                if row[3] != f"Hoover Dam ({EIA_IDS[row[0]]})":
                    raise ValueError("Unexpected Hoover plant name")
                for month, net_mwh in enumerate(row[79:91], 1):
                    records.append((row[0], row[6], row[5], row[13], row[14], row[96], month, net_mwh, row[95]))
        finally:
            workbook.close()
    with output.open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(EIA_ROW_KEYS)
        writer.writerows(sorted(records))


def eia_monthly():
    with (DATA / "eia923-hoover-2025.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    by_plant, annual_mwh = defaultdict(dict), {}
    for row in rows:
        plant, month = int(row["plant_id"]), int(row["month"])
        if (
            row["state"] != EIA_IDS[plant] or row["year"] != "2025" or row["operator_id"] != "2518"
            or row["prime_mover"] != "HY" or row["fuel"] != "WAT" or month in by_plant[plant]
        ):
            raise ValueError(f"Inconsistent EIA row: {plant} {month}")
        by_plant[plant][month] = int(row["net_mwh"])
        actual_annual = int(row["annual_mwh"])
        if actual_annual != annual_mwh.setdefault(plant, actual_annual):
            raise ValueError("Unexpected drift in the reported annual row")
    if set(by_plant) != set(EIA_IDS):
        raise ValueError("The facility has two state components")
    for plant, amounts in by_plant.items():
        if set(amounts) != set(range(1, 13)) or sum(amounts.values()) != annual_mwh[plant]:
            raise ValueError(f"Monthly generation does not reconcile: {plant}")
    combined = {month: sum(row[month] for row in by_plant.values()) for month in range(1, 13)}
    return combined, annual_mwh


def pdf(file):
    return subprocess.check_output(["pdftotext", "-layout", str(DATA / file), "-"], text=True)


def html(file):
    return unescape(re.sub(r"<[^>]*>", " ", (DATA / file).read_text(encoding="utf-8", errors="replace")))


def hoover_sheet(file):
    pages = [page for page in pdf(file).split("\f")
             if re.search(r"Hoover Dam [–-] Lake Mead", page) and "Gross Energy" in page]
    if len(pages) != 1:
        raise ValueError(f"Missing or ambiguous Hoover energy table: {file}")
    values = {}
    for line in pages[0].splitlines():
        columns = line.split()
        if not columns or columns[0] not in MONTHS:
            continue
        name, year, *data = columns
        if len(data) != 10 or not year.isdigit():
            raise ValueError(f"Unexpected Hoover table row: {file} {line}")
        key = f"{year}-{MONTHS[name]:02d}"
        if key in values:
            raise ValueError(f"Duplicate Hoover table row: {key}")
        release, _, elevation, _, _, head, capacity, gross, units, specific_energy = map(float, data)
        values[key] = {
            "power_release_kaf": release, "elevation_ft": elevation, "static_head_ft": head,
            "forecast_or_reported_capacity_mw": capacity, "gross_gwh": gross,
            "units_available_pct": units, "specific_kwh_per_af": specific_energy,
        }
    return values


def physical_energy_cap_gwh(power_release_kaf, maximum_head_ft):
    """All reported turbine water at maximum head and 100% conversion."""
    return 1000 * power_release_kaf * 1233.48183754752 * 1000 * 9.80665 * maximum_head_ft * 0.3048 / 3.6e12


def hydro():
    net_mwh, plant_totals = eia_monthly()
    annual = sum(plant_totals.values())
    reports = {key: hoover_sheet(file) for key, file in USBR_REPORTS.items()}
    faq = html("powerfaq.html")
    if not re.search(r"Maximum head.*?590 feet", faq) or "2,080 megawatts" not in faq:
        raise ValueError("Facility design reference changed")
    historical = []
    for month in range(1, 11):
        key = f"2025-{month:02d}"
        measured = reports["nov2025_most_probable"][key]
        cap_gwh = physical_energy_cap_gwh(measured["power_release_kaf"] + 0.5, 590)
        historical.append({
            "month": key, "eia_net_mwh_two_wings": net_mwh[month],
            "usbr_gross_gwh": measured["gross_gwh"], "power_release_kaf": measured["power_release_kaf"],
            "head_ceiling_ft": 590,
            "conditional_ideal_water_to_power_upper_gwh": cap_gwh,
            "within_ideal_energy_upper": net_mwh[month] / 1000 <= cap_gwh,
            "gross_minus_net_gwh": round(measured["gross_gwh"] - net_mwh[month] / 1000, 3),
        })
    projections = {}
    for key in ("nov2026_minimum", "nov2026_most_probable_7maf"):
        rows = reports[key]
        full_year = [rows[f"2027-{i:02d}"] for i in range(1, 13)]
        target = full_year[4:10]  # May through October, one target block
        interpretation_conflicts = []
        for month, row in enumerate(target, 5):
            hours = 24 * calendar.monthrange(2027, month)[1]
            nameplate_only = row["forecast_or_reported_capacity_mw"] * hours / 1000
            if row["gross_gwh"] - 0.05 > nameplate_only + 0.05 * hours / 1000:
                interpretation_conflicts.append({
                    "month": f"2027-{month:02d}", "published_gross_gwh": row["gross_gwh"],
                    "capacity_times_hours_gwh": round(nameplate_only, 4),
                })
        projections[key] = {
            "may_oct_gross_projection_gwh": round(sum(v["gross_gwh"] for v in target), 3),
            "may_oct_power_release_kaf": sum(v["power_release_kaf"] for v in target),
            "may_oct_capacity_mw_range_by_month": [
                min(v["forecast_or_reported_capacity_mw"] for v in target),
                max(v["forecast_or_reported_capacity_mw"] for v in target),
            ],
            "path_quarterly_ideal_upper_gwh": [
                sum(physical_energy_cap_gwh(v["power_release_kaf"] + 0.5, 590) for v in full_year[i:i + 3])
                for i in range(0, 12, 3)
            ],
            "max_27_arithmetic_residual_gwh": round(max(
                abs(v["gross_gwh"] - v["power_release_kaf"] * v["specific_kwh_per_af"] / 1000)
                for v in full_year
            ), 6),
            "gross_exceeds_naive_capacity_times_hours": interpretation_conflicts,
        }
    return {
        "plant_ids": EIA_IDS, "eia_2025_total_net_mwh": annual, "eia_2025_wing_net_mwh": plant_totals,
        "eia_month_count": len(net_mwh), "eia_unique_wing_month_count": len(net_mwh) * len(plant_totals),
        "net_mwh_2025_monthly": net_mwh, "comparable_historical_months": len(historical),
        "within_ideal_water_ceiling_count": sum(row["within_ideal_energy_upper"] for row in historical),
        "historical_diagnostics": historical, "projections": projections,
        "real_market_set": None,
    }


def industrial_fixture():
    return Scenario(
        products=(
            Product(1, 100, (30, 30, 40, 60), (0, 0, 15, 0), (12, 12, 12, 12), Bounds(5, 7), Bounds(3, 4)),
            Product(2, 40, (20, 20, 40, 60), (0, 5, 0, 0), (8, 8, 8, 8), Bounds(8, 10), Bounds(5, 6)),
        ),
        shared_hours=(100, 100, 100, 160), tax=0.25, fixed_opex=Bounds(65, 80),
        depreciation=Bounds(15, 20), maintenance_capex=Bounds(22, 30), growth_capex=Bounds(0, 12),
        incremental_nwc=Bounds(-5, 10), discount=Bounds(0.08, 0.13),
        terminal_growth=Bounds(0.01, 0.035), terminal_roic=Bounds(0.09, 0.16),
        terminal_nopat=Bounds(160, 260),
    )


def synthetic():
    fixture = industrial_fixture()
    conflicting_product = replace(fixture.products[1], demand_floor=(80, 8, 8, 8))
    midpoint = evaluate(fixture, Bounds(0, 100_000))["value_inner_at_midpoints"]
    # The final scenario changes the term assumptions, so this was not certified
    # outside every admissible term structure.
    wider = replace(fixture, discount=Bounds(0.065, 0.13), terminal_growth=Bounds(0.01, 0.045),
                    terminal_nopat=Bounds(150, 320))
    high = Bounds(6500, 6800)
    overlap = Bounds(statistics.mean(midpoint) - 30, statistics.mean(midpoint) + 30)
    pooled = replace(fixture, shared_hours=(300, 300, 300, 480))
    cases = {
        "high_ev_base": (fixture, high),
        "high_ev_wider_terminal": (wider, high),
        "high_ev_wider_capital_structure": (fixture, Bounds(5800, 6900)),
        "low_ev": (fixture, Bounds(200, 300)),
        "overlap_with_witness": (fixture, overlap),
        "impossible_delivery_floor": (replace(fixture, products=(fixture.products[0], conflicting_product)), high),
        "absent_shared_bottleneck": (pooled, high),
        "tight_capacity_changes_gap": (fixture, Bounds(6000, 6050)),
        "relaxed_capacity_loses_gap": (pooled, Bounds(6000, 6050)),
    }
    return {name: {"market_ev": [market.lo, market.hi], **evaluate(s, market)} for name, (s, market) in cases.items()}


def hydro_hybrid(hydro_result):
    cases, alternatives = {}, {}
    for name, projection in hydro_result["projections"].items():
        limits = projection["path_quarterly_ideal_upper_gwh"]
        # Monetary values are invented in million USD. The only observed input
        # to the LP is the conditional operating constraint from USBR.
        fixture = Scenario(
            products=(Product(1, 0, tuple(limits), (0,) * 4, (0,) * 4, Bounds(0.045, 0.085),
                              Bounds(0.010, 0.026)),),
            shared_hours=tuple(limits), tax=0.25, fixed_opex=Bounds(10, 15),
            depreciation=Bounds(7, 11), maintenance_capex=Bounds(10, 18), growth_capex=Bounds(0, 8),
            incremental_nwc=Bounds(-2, 4), discount=Bounds(0.075, 0.12),
            terminal_growth=Bounds(0.0, 0.025), terminal_roic=Bounds(0.07, 0.14),
            terminal_nopat=Bounds(30, 120),
        )
        cases[name] = evaluate(fixture, Bounds(2700, 2850))
        wider_terminal = replace(fixture, discount=Bounds(0.065, 0.12), terminal_nopat=Bounds(30, 160))
        alternatives[name] = evaluate(wider_terminal, Bounds(2700, 2850))
    return {
        "hypothetical_ev_musd": [2700, 2850],
        "conditional_on_two_published_paths": cases,
        "same_physical_paths_wider_monetary_assumptions": alternatives,
    }


def fed_cell(file, month_header):
    source = (DATA / file).read_text(encoding="utf-8")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", source, re.DOTALL | re.IGNORECASE)
    semiconductor = [row for row in rows if ">3344</td>" in row and "Semiconductor" in row]
    if len(semiconductor) != 1:
        raise ValueError(f"Unexpected semiconductor rows: {file}")
    values = re.findall(r'<td headers="([^"]+)">\s*([0-9.]+)\s*</td>', semiconductor[0])
    selected = [float(value) for headers, value in values if month_header in headers.split()]
    if len(selected) != 1:
        raise ValueError(f"Unexpected September columns: {file}")
    return selected[0]


def sector_census():
    records = json.loads((DATA / "census.json").read_text())["sectors"]
    archived = {record["file"] for record in manifest()["preserved"]}
    summary = {}
    for sector, row in records.items():
        routes = row["routes"]
        ok = [all(file in archived for file in route["files"]) for route in routes]
        summary[sector] = {
            "reviewed_routes": len(routes),
            "retrieved_routes": sum(ok),
            "observed_routes": sum(received and route["number_or_record"] for received, route in zip(ok, routes)),
            "public_facility_physical_bridge": row["physical_bridge"],
            "listed_issuer_eligible": row["listed_issuer_eligible"],
        }
    production = fed_cell("fed-ip.htm", "hdr15")
    capacity = fed_cell("fed-cap.htm", "hdr30")
    utilization = fed_cell("fed-util.htm", "hdr31")
    implied = capacity * utilization / 100
    if abs(production - implied) > 0.15:
        raise ValueError("Fed production, capacity and utilization do not reconcile within published rounding")
    with (DATA / "census-transformer.csv").open(newline="") as source:
        shipments = list(csv.DictReader(source))
    if shipments[-1]["observation_date"] != "2024-01-01":
        raise ValueError("Census series vintage differs")
    lead_times = re.search(r"12\s+to\s+30\s+months", html("doe-transformer.htm"))
    fleet = re.search(r"Total Ships\s+(\d+)", pdf("marad-fleet.pdf"))
    faa = re.search(r"increase from ([\d,]+) in 2024 to ([\d,]+) in\s*2045", pdf("faa-forecast.pdf"))
    shortage_reference = re.search(r"made up about\s*63%", pdf("hhs-whitepaper.pdf"))
    if not all((lead_times, fleet, faa, shortage_reference, "510(k) Premarket Notification" in html("fda-pmn.htm"))):
        raise ValueError("Missing sector report anchors")
    worksheet = xlrd.open_workbook(str(DATA / "eia-gross.xls")).sheet_by_name("Data 1")
    if worksheet.cell_value(1, 1) != "WGIRIP32":
        raise ValueError("Unexpected EIA refining series")
    final = re.search(r"Base Charge \(\$\)\.+\s+[\d,]+\s+([\d,]+)", html("wapa-fy26-final.htm"))
    proposal = re.search(r"to remain at \$([\d.]+) million", html("wapa-fy27-proposal.htm"))
    if not final or not proposal:
        raise ValueError("WAPA rate schedule amounts are unverified")
    return {
        "sector_counts": summary,
        "semiconductor_sep_2026": {
            "production_index": production, "capacity_index": capacity, "utilization_pct": utilization,
            "capacity_times_utilization": round(implied, 5),
        },
        "transformer_shipments_2024_thousand_usd": int(shipments[-1]["AIES335311RCTUS"]),
        "transformer_shipments_observations": len(shipments),
        "transformer_2023_doe_lead_time_months": [12, 30],
        "marad_operating_fleet_vessels": int(fleet[1]),
        "faa_fleet_2024_and_2045_forecast": [int(v.replace(",", "")) for v in faa.groups()],
        "example_aspe_shortage_pct_generic_sterile_injectables": 63,
        "wapa_2026_final_base_charge_usd": int(final[1].replace(",", "")),
        "wapa_2027_public_proposal_base_charge_rounded_musd": float(proposal[1]),
    }


def paired_t_power(n, effect):
    df = n - 1
    threshold = t.ppf(0.975, df)
    shift = effect * n ** 0.5
    scale_distribution = chi2(df)

    def rejection_given_scale(draw):
        critical = threshold * (draw / df) ** 0.5
        return (ndtr(shift - critical) + ndtr(-shift - critical)) * scale_distribution.pdf(draw)

    # Condition on the chi-squared denominator. The omitted tail probability
    # is at most 2e-12 and avoids unstable extreme noncentral-t CDFs.
    lo, hi = scale_distribution.ppf([1e-12, 1 - 1e-12])
    return quad(rejection_given_scale, lo, hi, epsabs=1e-9)[0]


def s4a_closeout():
    with (DATA / "s4a-closeout.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    preserved = {row["file"] for row in manifest()["preserved"]}
    if len(rows) != 7 or len({row["cluster"] for row in rows}) != 7:
        raise ValueError("Audit must cover all seven previously pending clusters")
    new_documented = sum(row["observed_shutdown"] == "yes" for row in rows)
    return {
        "document_packets_verified": sum(row["official_file"] in preserved for row in rows),
        "new_documented_shutdown_clusters": new_documented,
        "total_documented_shutdown_clusters": 2 + new_documented,
        "new_clusters_with_quantified_shutdown_nameplate": sum(bool(row["reported_shut_nameplate_kbd"]) for row in rows),
        "new_eligible_structural_clusters": sum(row["facility_day_and_independent_transport_demand"] == "yes" for row in rows),
        "n9_paired_t_mde_sd": round(brentq(lambda d: paired_t_power(9, d) - 0.8, 0, 4), 6),
        "minimum_n_80pct": {str(d): next(n for n in range(2, 1000) if paired_t_power(n, d) >= 0.8) for d in (0.5, 0.3)},
        "decision": "STOP_SOURCE_BLOCKED",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    p.add_argument("--project-eia", type=Path)
    args = p.parse_args()
    if args.project_eia:
        eia_extract(args.project_eia, DATA / "eia923-hoover-2025.csv")
        return
    verify_sources()
    measured = hydro()
    result = json.dumps({
        "evidence_status": "EXPLORATORY_AUTHOR_VALIDATION_ONLY",
        "hydro": measured,
        "synthetic": synthetic(),
        "physical_source_with_synthetic_cashflows": hydro_hybrid(measured),
        "sector_census": sector_census(),
        "s4a_closeout": s4a_closeout(),
    }, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.check:
        if RESULT.read_text() != result:
            raise SystemExit("Reproduction differs from the committed result")
        print(f"Verified {RESULT.name}")
    else:
        RESULT.write_text(result)


if __name__ == "__main__":
    main()
