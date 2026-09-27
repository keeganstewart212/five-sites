"""Script 1 (High risk): fair to every site.

Headroom: gridmap, then the vendor estimate (flagged). Any criterion still
missing gets the mean tier across all sites, and each row lists which fields
were averaged. Sites with no land-registry record stay in the list. Newer field
notes are taken at face value for area; a possible reserve is flagged, not
killed. Duplicate parcels are merged, and the latest note wins. Only a
registry protected_area of true kills a site.
"""

from sites_core import Policy, run

POLICY = Policy(
    name="Script 1",
    risk="High",
    use_vendor=True,
    fill_missing="average",
    require_landreg=False,
    area_override="apply",
    reserve_concern="flag",
    duplicates="merge",
)

if __name__ == "__main__":
    run(POLICY)
