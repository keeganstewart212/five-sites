"""Script 2 (Medium risk): like Script 1, but a land-registry record is required.

Headroom: gridmap, then the vendor estimate (flagged, ±40% accepted). Remaining
gaps get the mean tier across all sites. Sites with no land-registry record are
removed. A newer field note's area is used, but any hint of a protected reserve
removes the site. Duplicate parcels are merged, and the latest note wins.
"""

from sites_core import Policy, run

POLICY = Policy(
    name="Script 2",
    risk="Medium",
    use_vendor=True,
    fill_missing="average",
    require_landreg=True,
    area_override="apply",
    reserve_concern="remove",
    duplicates="merge",
)

if __name__ == "__main__":
    run(POLICY)
