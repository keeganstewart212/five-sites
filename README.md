# Five Sites: which ranking to trust, and why

Maren, this page explains the three rankings we can show the sponsor. All three use the same rubric (C1 headroom 30 · C2 distance 15 · C3 landowner 20 · C4 community 10 · C5 flood 15 · C6 area 10, scored out of 100). They differ in **how much risk we take on missing, estimated or unverified data**. Pick the one that matches how much risk the sponsor will accept.

Some rules apply in every script:
- A site the land registry marks as a **protected nature area is killed**, whatever its score (S-033).
- **Nordholm headroom is converted from kW to MW.** The national feed doesn't convert it.
- **Claude reads the field notes** to get owner status, community sentiment, and any area or reserve claims. Every signal must carry an exact quote, and the code checks that each quote really appears in the notes. The code does the scoring, not Claude.
- A note can only overrule the land registry **if the note is newer than the registry record**. Otherwise the note is ignored.
- Every site stays in the table. Killed and removed sites are listed after the ranked ones, with the reason in the **Status** column.

## Recorded decisions at a glance

| Rule | Script 1 (High risk) | Script 2 (Medium risk) | Script 3 (Low risk) |
|---|---|---|---|
| Registry says protected (S-033) | Killed | Killed | Killed |
| No land-registry record (S-024, S-036) | Kept, gaps averaged | Removed | Removed |
| Missing values | Vendor estimate, then average | Vendor estimate, then average | Removed |
| Newer note changes area (S-013, ~700 m²) | Use the note | Use the note | Removed |
| Newer note suggests a reserve (S-009) | Flagged only | Removed | Removed |
| Duplicate parcel (S-017 + S-031) | Merged, latest note wins | Merged, latest note wins | Both removed (assumption) |

## Script 1 (High risk): `score_high_risk.py`

**Fair to every site.** It uses gridmap and the land registry first. When gridmap has no headroom, it falls back to the vendor estimate (±40%, flagged). When a value is still missing, it fills the gap with the **average across all sites**. Each row shows how many criteria were averaged (`Avg #`) and which ones (`Averaged fields`).

- A site with no land-registry parcel **stays in the list**. Only an explicit `protected_area: true` removes a site.
- Unverified field notes are taken at face value. S-013's area becomes ~700 m², from a 2026 note that says half the plot was sold.
- S-009 has a note saying part of it may be inside a nature reserve. It **is flagged but not removed**, and it currently ranks #1. It must be checked before it's shown.
- Duplicate records of the same parcel are merged, and the latest note wins. S-017 and S-031 are the same Brekke depot.

**Why use it:** it gives the widest coverage, and a site with great numbers can come out on top even when data is missing.
**The risk:** promising-looking sites may be carried by averages. The client could pick one, pay for an evaluation, and only then find it's unsuitable, which costs time and money. High risk, potentially high reward.

## Script 2 (Medium risk): `score_medium_risk.py`

**Same as Script 1, but a land-registry record is required, and any hint of protected land is discarded.**

- A site without a land-registry parcel is **removed** (S-024, S-036).
- The vendor fallback (±40% uncertainty accepted) and averaging across sites are still used.
- The note's area is used (S-013), but a note suggesting the plot may be in a reserve **removes** the site (S-009). Anything close to the protected-area kill rule is treated as a kill.
- Duplicates are merged, and the latest note wins.

**Why it changed:** the first idea for Script 2 was "gridmap, registry and vendor only, no averaging". But the vendor only estimates headroom. Every site without gridmap data is also missing its substation distance, so without averaging Script 2 would have removed exactly the same sites as Script 3. So we kept Script 1's averaging and made the land-registry record the dividing line.

## Script 3 (Low risk): `score_low_risk.py`

**Complete, objective data only.** It uses only gridmap and the land registry, with no vendor estimates and no averages. Owner status and sentiment must each be backed by a verified quote from the notes.

- A site with **any** missing criterion is removed.
- A site is removed if a newer note contradicts the registry, whether about area (S-013) or a possible reserve (S-009).
- **Duplicates: both records are removed** (S-017, S-031). *Assumption:* we can't tell which of the two records is authoritative, so neither goes forward until someone checks.

**Why use it:** it has the lowest risk to the client, because every number shown comes from an official source.
**The downside:** it drops more than half the list (18 of 40 remain), so it may miss excellent sites that only lack one data point.

## How gaps are averaged (Scripts 1 and 2)

A gap is filled with the **average tier score (0–5)** for that criterion across every site that has a real value, not the average raw value (MW, km, m²). Numerically this changes nothing about the approach. But it tells the right story: we're analysing how sites compare in the data, not claiming a site "has 3.4 MW".

*Still to check with a colleague (Jonas):* the mean is our working assumption. The median, or re-weighting the remaining criteria, may be fairer to sites with gaps. This is a statistics question we'd put to someone stronger in that area before relying on it.

## Open questions for Maren

1. **At what risk tolerance should a site with no land-registry parcel be removed automatically?** Script 1 keeps these sites, and Scripts 2 and 3 remove them. Without a parcel we can't rule out a protected area.
2. **Is ±40% vendor uncertainty acceptable** for headroom, our most heavily weighted criterion?
3. **Should S-009 go to the sponsor at all** before the reserve boundary is checked?

## How to run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # only needed if the notes or prompt change

python score_high_risk.py           # Script 1 (High risk)
python score_medium_risk.py         # Script 2 (Medium risk)
python score_low_risk.py            # Script 3 (Low risk)
```

Claude's reads of the notes are cached in `data/extractions.json`, so the scripts run without an API key. The table is wide, so use a full-width terminal.

## Web page

The public page lets the reader pick a risk profile and then shows that profile's top 5 sites as cards, highest score first. Tap a card to see all of its data. The page is static: `build_site.py` runs the same scoring code as the scripts and writes `_site/data.json` next to the files in `web/`. The page never calls the Anthropic API.

```bash
python build_site.py                      # writes _site/
python -m http.server -d _site 8000       # preview at http://localhost:8000
```

**Hosting (GitHub Pages).** `.github/workflows/pages.yml` rebuilds and deploys the page on every push to `main`. One-time setup:
1. In the repo, go to **Settings → Pages → Source** and choose **GitHub Actions**.
2. Optional: add an `ANTHROPIC_API_KEY` repository secret. It's only needed if the field notes or the prompt change. Otherwise the committed `data/extractions.json` cache is used. The build fails rather than publishing sites whose notes weren't read.

## Files

| File | What it is |
|---|---|
| `score_high_risk.py`, `score_medium_risk.py`, `score_low_risk.py` | The three scripts. Each only sets its risk policy. |
| `sites_core.py` | Shared loading, kW→MW, rubric, averaging, kill/removal rules, table |
| `extract_notes.py`, `prompts/extract_notes.md` | Claude step and its prompt, with quote verification |
| `data/extractions.json` | Cached Claude output, re-verified on every run |
| `build_site.py`, `web/`, `.github/workflows/pages.yml` | Static results page and its GitHub Pages deploy |
| `CREATE_SCRIPT_PROMPT.md` | Original build spec/prompt for the scripts |
| `Questions.md` | Questions and assumptions written before any scoring code |
