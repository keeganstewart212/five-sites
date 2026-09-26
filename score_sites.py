"""Five Sites: load, clean and display the candidate sites.

Step 1 of the pipeline (load -> extract -> score -> display). This step only
reads the source files; it never writes to them. Cleaning builds new records
and keeps the original values alongside the cleaned ones.
"""

import csv
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

DATA_DIR = Path(__file__).parent / "data"
SITES_PATH = DATA_DIR / "sites.json"
FETCH_LOG_PATH = DATA_DIR / "fetch_log.csv"

# Nordholm's operator publishes headroom in kW and the national feed passes it
# through unconverted. Every other region publishes in MW.
NORDHOLM_KW_REGION = "Nordholm"
KW_PER_MW = 1000


# ---------------------------------------------------------------- load

def load_fetch_log(path=FETCH_LOG_PATH):
    """Return {(site_id, source): "<status> <message>"} for failed fetches only."""
    errors = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["http_status"] != "200":
                errors[(row["site_id"], row["source"])] = f"{row['http_status']} {row['message']}".strip()
    return errors


def load_sites(path=SITES_PATH):
    """Return the raw list of site dicts, exactly as stored in sites.json."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)["sites"]


# ---------------------------------------------------------------- clean

def _missing_reason(site_id, source, fetch_errors):
    return fetch_errors.get((site_id, source), "no reason logged")


def _latest_structured_owner_status(notes):
    """owner_status from the most recent note that has one (by date, not list order)."""
    with_status = [n for n in notes if n.get("owner_status")]
    if not with_status:
        return None, None
    latest = max(with_status, key=lambda n: n["date"])
    return latest["owner_status"], latest["date"]


def clean_site(raw, fetch_errors):
    """Build a new, flat, cleaned record from a raw site. `raw` is only read."""
    site_id = raw["site_id"]
    sources = raw["sources"]
    gridmap = sources.get("gridmap") or {}
    landreg = sources.get("landreg")
    vendor = sources.get("vendor_estimate")
    flags = []

    # C1 headroom: gridmap is official; vendor is the flagged fallback.
    headroom_raw = gridmap.get("headroom")
    if headroom_raw is not None:
        is_kw = raw["region"] == NORDHOLM_KW_REGION
        headroom_raw_unit = "kW" if is_kw else "MW"
        headroom_mw = headroom_raw / KW_PER_MW if is_kw else headroom_raw
        headroom_source = "gridmap"
    elif vendor and vendor.get("headroom_mw_est") is not None:
        headroom_raw = vendor["headroom_mw_est"]
        headroom_raw_unit = "MW"
        headroom_mw = headroom_raw
        headroom_source = "vendor"
        flags.append(f"vendor headroom ±{vendor['band_pct']}% "
                     f"(gridmap: {_missing_reason(site_id, 'gridmap', fetch_errors)})")
    else:
        headroom_raw_unit = headroom_mw = headroom_source = None
        flags.append(f"headroom missing ({_missing_reason(site_id, 'gridmap', fetch_errors)})")

    # C2 distance: only gridmap has it.
    distance_km = gridmap.get("substation_distance_km")
    if distance_km is None:
        flags.append(f"distance missing ({_missing_reason(site_id, 'gridmap', fetch_errors)})")

    # C5 / C6 and the kill rules come from the land registry.
    if landreg is None:
        landreg_reason = _missing_reason(site_id, "landreg", fetch_errors)
        flags.append(f"no land-registry record ({landreg_reason})")
        excluded_reason = f"no land-registry record ({landreg_reason})"
        landreg = {}
    elif landreg.get("protected_area"):
        excluded_reason = "protected area"
    else:
        excluded_reason = None

    notes = raw.get("field_notes") or []
    owner_status, owner_status_date = _latest_structured_owner_status(notes)

    return {
        "site_id": site_id,
        "name": raw["name"],
        "region": raw["region"],
        "site_type": raw["site_type"],
        "headroom_raw": headroom_raw,
        "headroom_raw_unit": headroom_raw_unit,
        "headroom_mw": headroom_mw,
        "headroom_source": headroom_source,
        "distance_km": distance_km,
        "area_m2": landreg.get("area_m2"),
        "flood_zone": landreg.get("flood_zone"),
        "protected_area": landreg.get("protected_area"),
        "owner_type": landreg.get("owner_type"),
        "notes_count": len(notes),
        "owner_status_structured": owner_status,
        "owner_status_date": owner_status_date,
        "excluded_reason": excluded_reason,
        "flags": flags,
    }


# ---------------------------------------------------------------- display

DASH = Text("—", style="dim")


def _cell(value, fmt="{}"):
    return DASH if value is None else Text(fmt.format(value))


def _headroom_cell(r):
    if r["headroom_mw"] is None:
        return DASH
    if r["headroom_source"] == "vendor":
        return Text(f"{r['headroom_mw']:.2f} (vendor)", style="yellow")
    text = f"{r['headroom_mw']:.2f}"
    if r["headroom_raw_unit"] == "kW":
        text += f" ({r['headroom_raw']:g} kW)"
    return Text(text)


def build_table(records):
    table = Table(title="Candidate sites (cleaned, pre-Claude, unscored)", show_lines=False)
    table.add_column("ID", no_wrap=True)
    table.add_column("Name")
    table.add_column("Region")
    table.add_column("Headroom MW", justify="right")
    table.add_column("Dist km", justify="right")
    table.add_column("Area m²", justify="right")
    table.add_column("Flood")
    table.add_column("Owner status\n(notes, pre-Claude)")
    table.add_column("Notes", justify="right")
    table.add_column("Status")
    table.add_column("Flags")

    for r in records:
        excluded = r["excluded_reason"] is not None
        status = (Text(f"EXCLUDED: {r['excluded_reason']}", style="red")
                  if excluded else Text("OK", style="green"))
        table.add_row(
            r["site_id"],
            r["name"],
            r["region"],
            _headroom_cell(r),
            _cell(r["distance_km"], "{:.1f}"),
            _cell(r["area_m2"], "{:,}"),
            _cell(r["flood_zone"]),
            _cell(r["owner_status_structured"]),
            str(r["notes_count"]),
            status,
            Text("\n".join(r["flags"]), style="yellow") if r["flags"] else DASH,
            style="dim" if excluded else None,
        )
    return table


def main():
    fetch_errors = load_fetch_log()
    raw_sites = load_sites()
    records = sorted((clean_site(s, fetch_errors) for s in raw_sites), key=lambda r: r["site_id"])

    console = Console()
    console.print(build_table(records))

    excluded = sum(r["excluded_reason"] is not None for r in records)
    vendor = sum(r["headroom_source"] == "vendor" for r in records)
    no_headroom = sum(r["headroom_mw"] is None for r in records)
    console.print(f"{len(records)} sites · {excluded} excluded · "
                  f"{vendor} vendor-headroom fallback · {no_headroom} no headroom")


if __name__ == "__main__":
    main()
