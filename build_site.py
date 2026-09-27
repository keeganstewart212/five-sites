"""Five Sites: build the static results page into _site/.

Runs the three risk profiles through the same scoring code as the scripts,
keeps each profile's top 5, and writes _site/data.json next to a copy of web/.
The page is fully static: it never calls the Anthropic API or sees the key.
"""

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from extract_notes import extract_all
from score_high_risk import POLICY as HIGH
from score_low_risk import POLICY as LOW
from score_medium_risk import POLICY as MEDIUM
from sites_core import (CRITERIA, LABELS, TOP_N, WEIGHTS, _is_newer, load_fetch_log,
                        load_sites, score_all)

ROOT = Path(__file__).parent
WEB_DIR = ROOT / "web"
OUT_DIR = ROOT / "_site"

PROFILES = [
    {
        "key": "high", "policy": HIGH,
        "title": "Cast the widest net",
        "description": "Every site gets a fair chance: gaps in the data are filled with estimates, "
                       "so hidden gems aren't missed.",
        "risk": "Risk: a site may only look good because of the filled gaps, costing time and money "
                "to evaluate.",
    },
    {
        "key": "medium", "policy": MEDIUM,
        "title": "Balanced shortlist",
        "description": "Estimates are allowed, but every site needs a land-registry record and no "
                       "protected-land doubts.",
        "risk": "Risk: some figures are still estimates, but the deal-breakers are screened out.",
    },
    {
        "key": "low", "policy": LOW,
        "title": "Only what's confirmed",
        "description": "Only sites with complete, verified data. Nothing is estimated.",
        "risk": "Risk: minimal, but strong sites with even one gap are left out.",
    },
]

CRITERION_NAMES = {"headroom": "Grid headroom", "distance": "Distance to substation",
                   "owner_status": "Landowner status", "sentiment": "Community sentiment",
                   "flood_zone": "Flood zone", "area": "Usable area"}


def _badges(r, policy):
    badges = []
    rc = r["reserve_concern"]
    if rc and policy.reserve_concern == "flag" and _is_newer(rc["date"], r["record_date"]):
        badges.append({"label": "Possible protected area", "level": "danger"})
    if not r["has_landreg"]:
        badges.append({"label": "No land-registry record", "level": "danger"})
    if r["criteria"]["headroom"]["source"] == "vendor":
        badges.append({"label": f"Vendor estimate ±{r['vendor_band_pct']}%", "level": "warn"})
    if r["averaged"]:
        n = len(r["averaged"])
        badges.append({"label": f"{n} field{'s' if n > 1 else ''} averaged", "level": "warn"})
    if len(r["merged_from"]) > 1:
        badges.append({"label": "Merged duplicate", "level": "info"})
    if r["criteria"]["area"]["source"] == "notes":
        badges.append({"label": "Area from field note", "level": "info"})
    return badges


def _headroom_text(r):
    c = r["criteria"]["headroom"]
    if c["source"] == "average":
        return None
    text = f"{c['value']:.2f} MW"
    if c["source"] == "gridmap" and r["gridmap_headroom_unit"] == "kW":
        text += f" ({r['gridmap_headroom_raw']:g} kW)"
    return text


def _card(r, policy):
    crit = r["criteria"]
    return {
        "rank": r["rank"],
        "site_id": r["site_id"],
        "name": r["name"],
        "score": round(r["score"], 1),
        "badges": _badges(r, policy),
        "details": {
            "region": r["region"],
            "site_type": r["site_type"].replace("_", " "),
            "parcel_id": r["parcel_id"],
            "owner_type": r["owner_type"],
            "headroom": _headroom_text(r),
            "distance_km": crit["distance"]["value"],
            "flood_zone": crit["flood_zone"]["value"],
            "area_m2": crit["area"]["value"],
            "owner_status": r["owner"],
            "sentiment": r["sentiment"],
        },
        "criteria": [
            {"code": LABELS[c], "name": CRITERION_NAMES[c], "weight": WEIGHTS[c],
             "tier": round(crit[c]["tier"], 2), "points": round(WEIGHTS[c] * crit[c]["tier"] / 5, 1),
             "source": crit[c]["source"]}
            for c in CRITERIA
        ],
        "averaged": r["averaged"],
        "flags": r["flags"],
    }


def build():
    raw_sites = load_sites()
    fetch_errors = load_fetch_log()
    extractions = extract_all(raw_sites)

    failed = [sid for sid, ex in extractions.items() if ex["extraction_failed"]]
    if failed:
        sys.exit(f"Notes extraction failed for {', '.join(failed)}; not publishing a page with "
                 "missing signals. Set ANTHROPIC_API_KEY or refresh data/extractions.json.")

    profiles = []
    for prof in PROFILES:
        policy = prof["policy"]
        rows, _ = score_all(raw_sites, fetch_errors, extractions, policy)
        top = [r for r in rows if r["status"] == "OK"][:TOP_N]
        profiles.append({
            "key": prof["key"],
            "level": policy.risk,
            "title": prof["title"],
            "description": prof["description"],
            "risk": prof["risk"],
            "ranked": sum(r["status"] == "OK" for r in rows),
            "total": len(rows),
            "top": [_card(r, policy) for r in top],
        })

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    shutil.copytree(WEB_DIR, OUT_DIR)
    data = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "profiles": profiles}
    (OUT_DIR / "data.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    print(f"Built {OUT_DIR}/ ({', '.join(p['key'] + ': ' + ' · '.join(c['site_id'] for c in p['top']) for p in profiles)})")


if __name__ == "__main__":
    build()
