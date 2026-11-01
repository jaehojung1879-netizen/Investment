"""Read first two SA levels, preserving single-space legacy rows and suppression."""
import re

GROUPS = {
    "primary_metals": r"Primary metals",
    "fabricated_metals": r"Fabricated metal products",
    "machinery": r"Machinery",
    "computers_electronics": r"Computers? and electronic products",
    "electrical_equipment": r"Electrical equipment, appliances,",
    "transportation_equipment": r"Transportation equipment",
}


def parse_table(text, number):
    match = re.search(r"Table\s*" + str(number) + r"\s*\.\s*Value of Manufacturers", text, re.I)
    if not match:
        raise ValueError("TABLE_MISSING")
    tail = text[match.end():]
    end = re.search(r"Table\s*\d+\s*\.", tail)
    block = tail[:end.start()] if end else tail
    if "Seasonally Adjusted" not in block or not re.search(r"[Mm]illions of [Dd]ollars", block):
        raise ValueError("UNITS_OR_SA_HEADER_MISSING")
    rows = block.splitlines()
    out = {}
    for group, label in GROUPS.items():
        hits = [i for i, row in enumerate(rows) if re.match(r"\s*" + label, row, re.I)]
        if len(hits) != 1:
            raise ValueError(group + ":ROW_AMBIGUOUS")
        i = hits[0]
        data = re.sub(r"^\s*" + label, "", rows[i], flags=re.I)
        if group == "electrical_equipment":
            if not re.match(r"\s*and components", rows[i+1], re.I):
                raise ValueError("WRAPPED_LABEL_MISSING")
            data = re.sub(r"^\s*and components", "", rows[i+1], flags=re.I)
        # Strip label footnotes and leaders, not the first data column.
        data = re.sub(r"^[\s\d]*[.…]+[\s.…]*", "", data).strip()
        cells = data.split()
        if len(cells) < 2 or not all(re.fullmatch(r"\d[\d,]*(?:\.\d+)?", c) for c in cells[:2]):
            raise ValueError(group + ":CELL_MISSING_OR_SUPPRESSED")
        pair = [float(c.replace(",", "")) for c in cells[:2]]
        if not all(x > 0 for x in pair):
            raise ValueError(group + ":NONPOSITIVE_LEVEL")
        out[group] = pair
    return out
