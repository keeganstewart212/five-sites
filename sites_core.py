"""Five Sites: shared load -> extract -> score -> display pipeline.

The three scoring scripts (score_high_risk.py, score_medium_risk.py,
score_low_risk.py) share everything here. Each one only defines a `Policy`,
which says how that risk profile treats missing, estimated or unverified data.
The rubric lives in this file, not in a prompt. This module only reads the
source files; it never writes to them.
"""

import csv
import json
from dataclasses import dataclass
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

TOP_N = 5


# ---------------------------------------------------------------- policy

@dataclass(frozen=True)
class Policy:
    name: str
    risk: str                # "High", "Medium", "Low"
    use_vendor: bool         # fall back to the vendor headroom estimate when gridmap is empty
    fill_missing: str        # "average": mean tier across sites · "remove": drop the site
    require_landreg: bool    # no land-registry record -> removed
    area_override: str       # newer note contradicts registry area: "apply" or "remove"
    reserve_concern: str     # newer note says plot may be in a reserve: "flag" or "remove"
    duplicates: str          # sites sharing a parcel_id: "merge" or "remove"


# ---------------------------------------------------------------- rubric

CRITERIA = ["headroom", "distance", "owner_status", "sentiment", "flood_zone", "area"]
WEIGHTS = {"headroom": 30, "distance": 15, "owner_status": 20,
           "sentiment": 10, "flood_zone": 15, "area": 10}
LABELS = {"headroom": "C1", "distance": "C2", "owner_status": "C3",
          "sentiment": "C4", "flood_zone": "C5", "area": "C6"}


def tier_headroom(mw):
    return 5 if mw >= 4 else 3 if mw >= 2 else 1 if mw >= 1 else 0


def tier_distance(km):
    return 5 if km <= 1 else 3 if km <= 3 else 1 if km <= 6 else 0


def tier_area(m2):
    return 5 if m2 >= 1200 else 2 if m2 >= 800 else 0


OWNER_TIERS = {"loi_signed": 5, "in_talks": 3, "not_contacted": 1, "refused": 0}
SENTIMENT_TIERS = {"supportive": 5, "neutral": 3, "opposed": 0}
FLOOD_TIERS = {"none": 5, "low": 4, "medium": 2, "high": 0}


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


def _missing_reason(site_id, source, fetch_errors):
    return fetch_errors.get((site_id, source), "no reason logged")


# ---------------------------------------------------------------- records

def build_record(raw, fetch_errors, extraction):
    """Flatten a raw site plus its verified notes extraction. No policy applied yet."""
    site_id = raw["site_id"]
    sources = raw["sources"]
    gridmap = sources.get("gridmap") or {}
    landreg = sources.get("landreg")
    vendor = sources.get("vendor_estimate") or {}

    headroom_raw = gridmap.get("headroom")
    is_kw = raw["region"] == NORDHOLM_KW_REGION
    gridmap_mw = None
    if headroom_raw is not None:
        gridmap_mw = headroom_raw / KW_PER_MW if is_kw else headroom_raw

    return {
        "site_id": site_id,
        "merged_from": [site_id],
        "name": raw["name"],
        "region": raw["region"],
        "site_type": raw["site_type"],
        "parcel_id": raw["parcel_id"],
        "gridmap_headroom_raw": headroom_raw,
        "gridmap_headroom_unit": ("kW" if is_kw else "MW") if headroom_raw is not None else None,
        "gridmap_headroom_mw": gridmap_mw,
        "distance_km": gridmap.get("substation_distance_km"),
        "gridmap_reason": _missing_reason(site_id, "gridmap", fetch_errors),
        "vendor_headroom_mw": vendor.get("headroom_mw_est"),
        "vendor_band_pct": vendor.get("band_pct"),
        "has_landreg": landreg is not None,
        "landreg_reason": None if landreg else _missing_reason(site_id, "landreg", fetch_errors),
        "registry_area_m2": (landreg or {}).get("area_m2"),
        "flood_zone": (landreg or {}).get("flood_zone"),
        "protected_area": (landreg or {}).get("protected_area"),
        "owner_type": (landreg or {}).get("owner_type"),
        "record_date": (landreg or {}).get("record_date"),
        "owner": extraction["owner_status"],
        "sentiment": extraction["community_sentiment"],
        "area_claim": extraction["area_claim"],
        "reserve_concern": extraction["reserve_concern"],
        "findings": extraction["other_findings"],
        "flags": list(extraction["flags"]),
        "duplicate_group": None,
    }


def _latest(signals, known):
    """Pick the signal with the latest note date among those that are known."""
    candidates = [s for s in signals if s and known(s)]
    return max(candidates, key=lambda s: s["date"]) if candidates else signals[0]


def _merge_group(group):
    group = sorted(group, key=lambda r: r["site_id"])
    merged = dict(group[0])
    for field in ("gridmap_headroom_raw", "gridmap_headroom_unit", "gridmap_headroom_mw",
                  "distance_km", "vendor_headroom_mw", "vendor_band_pct", "registry_area_m2",
                  "flood_zone", "protected_area", "owner_type", "record_date"):
        if merged[field] is None:
            merged[field] = next((r[field] for r in group if r[field] is not None), None)
    merged["has_landreg"] = any(r["has_landreg"] for r in group)
    merged["protected_area"] = any(r["protected_area"] for r in group)
    merged["site_id"] = " + ".join(r["site_id"] for r in group)
    merged["merged_from"] = [r["site_id"] for r in group]
    merged["name"] = " / ".join(r["name"] for r in group)
    merged["owner"] = _latest([r["owner"] for r in group], lambda s: s["value"] != "unknown")
    merged["sentiment"] = _latest([r["sentiment"] for r in group], lambda s: s["value"] != "unknown")
    merged["area_claim"] = _latest([r["area_claim"] for r in group], lambda s: True)
    merged["reserve_concern"] = _latest([r["reserve_concern"] for r in group], lambda s: True)
    merged["findings"] = [f for r in group for f in r["findings"]]
    merged["flags"] = [f"merged duplicate records on parcel {merged['parcel_id']}; latest note wins"] + \
                      [f for r in group for f in r["flags"]]
    return merged


def handle_duplicates(records, policy):
    """Group sites that share a parcel_id and either merge them or mark them for removal."""
    by_parcel = {}
    for r in records:
        by_parcel.setdefault(r["parcel_id"], []).append(r)

    out = []
    for parcel, group in by_parcel.items():
        if len(group) == 1:
            out.append(group[0])
        elif policy.duplicates == "merge":
            out.append(_merge_group(group))
        else:
            ids = [r["site_id"] for r in group]
            for r in group:
                r["duplicate_group"] = ids
                out.append(r)
    return out


# ---------------------------------------------------------------- score

def _is_newer(note_date, record_date):
    """A note beats the registry only if it's newer (or there's no registry date to compare)."""
    return record_date is None or note_date > record_date


def resolve(rec, policy):
    """Work out each criterion's value, tier and source before any averaging."""
    crit = {}
    reasons = []  # reasons this site is removed, whatever the missing-data rule says

    # C1 headroom: gridmap is official; vendor is the flagged fallback if the policy allows it.
    if rec["gridmap_headroom_mw"] is not None:
        crit["headroom"] = {"value": rec["gridmap_headroom_mw"], "source": "gridmap",
                            "tier": tier_headroom(rec["gridmap_headroom_mw"])}
    elif policy.use_vendor and rec["vendor_headroom_mw"] is not None:
        crit["headroom"] = {"value": rec["vendor_headroom_mw"], "source": "vendor",
                            "tier": tier_headroom(rec["vendor_headroom_mw"])}
        rec["flags"].append(f"headroom is a vendor estimate ±{rec['vendor_band_pct']}% "
                            f"(gridmap: {rec['gridmap_reason']})")
    else:
        crit["headroom"] = None

    # C2 distance: only gridmap has it.
    d = rec["distance_km"]
    crit["distance"] = {"value": d, "source": "gridmap", "tier": tier_distance(d)} if d is not None else None

    # C3 / C4 come from Claude's quote-verified read of the notes.
    o = rec["owner"]
    crit["owner_status"] = ({"value": o["value"], "source": "notes", "tier": OWNER_TIERS[o["value"]]}
                            if o["value"] != "unknown" else None)
    s = rec["sentiment"]
    crit["sentiment"] = ({"value": s["value"], "source": "notes", "tier": SENTIMENT_TIERS[s["value"]]}
                         if s["value"] != "unknown" else None)

    # C5 flood zone: land registry only.
    f = rec["flood_zone"]
    crit["flood_zone"] = {"value": f, "source": "landreg", "tier": FLOOD_TIERS[f]} if f else None

    # C6 area: registry, unless a newer field note contradicts it.
    a = rec["registry_area_m2"]
    crit["area"] = {"value": a, "source": "landreg", "tier": tier_area(a)} if a is not None else None
    claim = rec["area_claim"]
    if claim and claim["m2"] != a:
        if not _is_newer(claim["date"], rec["record_date"]):
            rec["flags"].append(f"note area {claim['m2']:,.0f} m² ({claim['date']}) is older than the "
                                f"registry record ({rec['record_date']}); ignored")
        elif policy.area_override == "apply":
            crit["area"] = {"value": claim["m2"], "source": "notes", "tier": tier_area(claim["m2"])}
            rec["flags"].append(f"area from field note {claim['date']} (registry {a:,} m², "
                                f"{rec['record_date']}): \"{claim['quote']}\"" if a is not None else
                                f"area from field note {claim['date']}: \"{claim['quote']}\"")
        else:
            reasons.append(f"field note {claim['date']} contradicts registry area "
                           f"({claim['m2']:,.0f} vs {a:,} m²)")

    # Possible protected area raised in the notes (the registry flag itself is the kill rule).
    rc = rec["reserve_concern"]
    if rc:
        if not _is_newer(rc["date"], rec["record_date"]):
            rec["flags"].append(f"reserve concern ({rc['date']}) is older than the registry record; ignored")
        elif policy.reserve_concern == "flag":
            rec["flags"].append(f"POSSIBLE PROTECTED AREA, check before shortlisting ({rc['date']}): "
                                f"\"{rc['quote']}\"")
        else:
            reasons.append(f"field note {rc['date']} says plot may be in a protected reserve")

    for fnd in rec["findings"]:
        rec["flags"].append(f"note {fnd['date']}: {fnd['finding']}")

    rec["criteria"] = crit
    rec["policy_reasons"] = reasons
    return rec


def tier_averages(records):
    """Mean tier (0–5) per criterion across every site that has a real value for it."""
    avgs = {}
    for c in CRITERIA:
        tiers = [r["criteria"][c]["tier"] for r in records if r["criteria"][c] is not None]
        avgs[c] = sum(tiers) / len(tiers) if tiers else 0
    return avgs


def finalise(rec, policy, avgs):
    """Apply kill / removal rules, fill or reject gaps, and compute the score."""
    reasons = []
    killed = bool(rec["protected_area"])
    if killed:
        reasons.append("protected area (land registry)")
    if rec["duplicate_group"]:
        others = ", ".join(i for i in rec["duplicate_group"] if i != rec["site_id"])
        reasons.append(f"duplicate parcel {rec['parcel_id']} (also {others}); can't tell which record is right")
    if policy.require_landreg and not rec["has_landreg"]:
        reasons.append(f"no land-registry record ({rec['landreg_reason']})")
    reasons += rec["policy_reasons"]

    missing = [c for c in CRITERIA if rec["criteria"][c] is None]
    averaged = []
    if missing and policy.fill_missing == "remove":
        reasons.append("missing " + ", ".join(missing))
    elif missing:
        for c in missing:
            rec["criteria"][c] = {"value": None, "source": "average", "tier": avgs[c]}
            averaged.append(c)

    rec["averaged"] = averaged
    rec["reasons"] = reasons
    rec["status"] = "KILLED" if killed else "REMOVED" if reasons else "OK"
    rec["score"] = (sum(WEIGHTS[c] * rec["criteria"][c]["tier"] / 5 for c in CRITERIA)
                    if rec["status"] == "OK" else None)
    return rec


def score_all(raw_sites, fetch_errors, extractions, policy):
    records = [build_record(s, fetch_errors, extractions[s["site_id"]]) for s in raw_sites]
    records = handle_duplicates(records, policy)
    records = [resolve(r, policy) for r in records]
    avgs = tier_averages(records)
    records = [finalise(r, policy, avgs) for r in records]

    ok = sorted((r for r in records if r["status"] == "OK"), key=lambda r: (-r["score"], r["site_id"]))
    rest = sorted((r for r in records if r["status"] != "OK"), key=lambda r: (r["status"], r["site_id"]))
    for i, r in enumerate(ok, 1):
        r["rank"] = i
    for r in rest:
        r["rank"] = None
    return ok + rest, avgs


# ---------------------------------------------------------------- display

DASH = Text("—", style="dim")


def _cell(value, fmt="{}"):
    return DASH if value is None else Text(fmt.format(value))


def _avg_cell(r, c):
    return Text(f"avg T{r['criteria'][c]['tier']:.1f}", style="magenta")


def _headroom_cell(r):
    c = r["criteria"]["headroom"]
    if c is None:
        return DASH
    if c["source"] == "average":
        return _avg_cell(r, "headroom")
    if c["source"] == "vendor":
        return Text(f"{c['value']:.2f} vendor ±{r['vendor_band_pct']}%", style="yellow")
    text = f"{c['value']:.2f}"
    if r["gridmap_headroom_unit"] == "kW":
        text += f" ({r['gridmap_headroom_raw']:g} kW)"
    return Text(text)


def _value_cell(r, c, fmt="{}"):
    crit = r["criteria"][c]
    if crit is None:
        return DASH
    if crit["source"] == "average":
        return _avg_cell(r, c)
    text = Text(fmt.format(crit["value"]))
    if c == "area" and crit["source"] == "notes":
        text.append(" (note)", style="yellow")
    return text


def _tiers_cell(r):
    parts = []
    for c in CRITERIA:
        crit = r["criteria"][c]
        if crit is None:
            parts.append("—")
        elif crit["source"] == "average":
            parts.append(f"{crit['tier']:.1f}*")
        else:
            parts.append(str(crit["tier"]))
    return Text(" ".join(parts))


def _evidence_cell(r):
    lines = []
    for label, sig in (("C3", r["owner"]), ("C4", r["sentiment"])):
        if sig["value"] != "unknown":
            lines.append(f"{label} {sig['date']}: \"{sig['quote']}\"")
    return Text("\n".join(lines)) if lines else DASH


def _status_cell(r):
    if r["status"] == "OK":
        return Text("OK", style="green")
    return Text(f"{r['status']}: " + "; ".join(r["reasons"]), style="red")


def build_table(rows, policy):
    table = Table(title=f"{policy.name} ({policy.risk} risk): ranked sites", show_lines=True)
    table.add_column("#", justify="right")
    table.add_column("ID", no_wrap=True)
    table.add_column("Name")
    table.add_column("Region")
    table.add_column("Type", no_wrap=True)
    table.add_column("Parcel", no_wrap=True)
    table.add_column("Owner\ntype")
    table.add_column("Headroom MW")
    table.add_column("Dist km", justify="right")
    table.add_column("Owner status")
    table.add_column("Sentiment")
    table.add_column("Flood")
    table.add_column("Area m²", justify="right")
    table.add_column("Tiers\nC1 C2 C3 C4 C5 C6\n(* = average)", no_wrap=True)
    table.add_column("Score", justify="right")
    table.add_column("Avg\n#", justify="right")
    table.add_column("Averaged fields")
    table.add_column("Status", min_width=18)
    table.add_column("Evidence (verified quotes)", min_width=36)
    table.add_column("Flags", min_width=40)

    for r in rows:
        top = r["rank"] is not None and r["rank"] <= TOP_N
        table.add_row(
            Text(str(r["rank"]), style="bold green" if top else "") if r["rank"] else DASH,
            r["site_id"],
            r["name"],
            r["region"],
            r["site_type"],
            r["parcel_id"],
            _cell(r["owner_type"]),
            _headroom_cell(r),
            _value_cell(r, "distance", "{:.1f}"),
            _value_cell(r, "owner_status"),
            _value_cell(r, "sentiment"),
            _value_cell(r, "flood_zone"),
            _value_cell(r, "area", "{:,.0f}"),
            _tiers_cell(r),
            Text(f"{r['score']:.1f}", style="bold" if top else "") if r["score"] is not None else DASH,
            str(len(r["averaged"])) if r["status"] == "OK" else DASH,
            Text(", ".join(r["averaged"]), style="magenta") if r["averaged"] and r["status"] == "OK" else DASH,
            _status_cell(r),
            _evidence_cell(r),
            Text("\n".join(r["flags"]), style="yellow") if r["flags"] else DASH,
            style="dim" if r["status"] != "OK" else None,
        )
    return table


def run(policy):
    """Entry point for the three scoring scripts."""
    from extract_notes import extract_all

    fetch_errors = load_fetch_log()
    raw_sites = load_sites()
    extractions = extract_all(raw_sites)
    rows, avgs = score_all(raw_sites, fetch_errors, extractions, policy)

    console = Console()
    console.print(build_table(rows, policy))

    ok = [r for r in rows if r["status"] == "OK"]
    killed = sum(r["status"] == "KILLED" for r in rows)
    removed = sum(r["status"] == "REMOVED" for r in rows)
    console.print(f"{len(rows)} rows · {len(ok)} ranked · {killed} killed · {removed} removed")
    if policy.fill_missing == "average":
        console.print("Tier averages used for gaps: " +
                      " · ".join(f"{LABELS[c]} {c} {avgs[c]:.2f}" for c in CRITERIA))
    console.print(f"[bold]Top {TOP_N}:[/bold] " +
                  " · ".join(f"{r['site_id']} {r['name']} ({r['score']:.1f})" for r in ok[:TOP_N]))
