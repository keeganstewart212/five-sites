# Data dictionary

All data is synthetic. Two files:

- `sites.json`: 40 candidate sites, exported from our site tracker on 2026-09-21.
- `fetch_log.csv`: the log from the job that pulled the source data into the tracker.

## `sites.json`

Each site has:

| Field | Meaning |
|---|---|
| `site_id` | Tracker ID (`S-001`…). Created by whoever first logged the site. |
| `name` | Human name as entered by the business development team. |
| `region` | One of Aldmark, Nordholm, Sveld, Tarrow. |
| `site_type` | brownfield, depot_yard, municipal_land, farm_edge. |
| `grid_ref_km` | Position on the national km grid (x east, y north). |
| `parcel_id` | Land registry parcel identifier. |
| `sources` | Data from the three sources below. A source is `null` if it returned nothing. |
| `field_notes` | Free-text notes from the business development team (see below). |

### Source: `gridmap` (national grid open-data feed)

| Field | Meaning |
|---|---|
| `headroom` | Available connection capacity at the nearest substation. |
| `substation_distance_km` | Straight-line distance to that substation. |
| `data_as_of` | When the grid operator last updated the figure (published quarterly). |
| `fetched_at` | When our job pulled it. |

The national feed aggregates the regional distribution operators' publications. It's the official figure and the one the sponsor will trust.

### Source: `landreg` (land registry)

| Field | Meaning |
|---|---|
| `area_m2` | Parcel area. |
| `flood_zone` | none / low / medium / high. |
| `protected_area` | Whether the parcel is inside a designated nature area. |
| `owner_type` | municipal / private. |
| `record_date` | When the registry record was last updated. Some records are old. |

### Source: `vendor_estimate` (third-party data vendor, trial licence)

| Field | Meaning |
|---|---|
| `headroom_mw_est` | The vendor's modelled headroom estimate, in MW. |
| `band_pct` | The vendor's stated uncertainty (± %). |
| `estimated_at` | When the estimate was produced. |

This is a machine-learning estimate from load profiles, not an official figure. It's available for only some sites. We're on a trial and haven't validated it.

### `field_notes`

A list of notes from the business development team. Each note has a `date`, `author` initials and `text`. Some also have a structured `owner_status` (`loi_signed`, `in_talks`, `not_contacted`, `refused`). Community sentiment is only ever in the free text. Notes were appended by hand, sometimes from memory, sometimes later.

## `fetch_log.csv`

One row per source per site: `timestamp, site_id, source, http_status, message`.

## Known quirks

- Headroom figures come through as the regional operators publish them. Aldmark, Sveld and Tarrow publish in MW. Nordholm publishes in kW, and the national feed doesn't convert.
- The land registry doesn't have every parcel.
