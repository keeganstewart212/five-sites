"""Script 3 (Low risk): complete objective data only.

Only gridmap and land-registry values are scored; vendor estimates and averages
are never used. Owner status and sentiment must be backed by a verified quote
from the field notes. A site missing any criterion is removed, and so is any site
where a newer note contradicts the registry (area or reserve) or where the
parcel is logged twice.
"""

from sites_core import Policy, run

POLICY = Policy(
    name="Script 3",
    risk="Low",
    use_vendor=False,
    fill_missing="remove",
    require_landreg=True,
    area_override="remove",
    reserve_concern="remove",
    duplicates="remove",
)

if __name__ == "__main__":
    run(POLICY)
