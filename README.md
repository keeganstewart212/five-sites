# Five Sites

Maren, our venture lead, needs **five shortlisted sites for community batteries** to show a corporate sponsor on Thursday at 9:00. This repo holds a Python script that:

1. loads the 40 candidate sites from `data/sites.json`;
2. uses **Claude** to read each site's free-text field notes and turn them into structured signals, each backed by an exact quote;
3. **calculates a score** for each site with the rubric agreed with the sponsor (the rubric lives in code, not in a prompt);
4. **displays** the ranked results, the top five, and a breakdown of why each site scored the way it did.

The brief is in [`five-sites-by-thursday.md`](five-sites-by-thursday.md). All data is synthetic, and the country (the Republic of Vessmark) is fictional.

> **Status:** planning. `Questions.md` is committed. The scoring script hasn't been written yet, so any section marked _(planned)_ describes what will be built.

## How to run _(planned)_

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=...   # never commit this, and never put it in the page
python score_sites.py
```

The goal is a single command that produces the ranked output. Claude's extractions are cached, so later runs don't call the API again.

## What the script does

### 1. Load and clean the data
- Read `data/sites.json`. Use `data/fetch_log.csv` to explain why a source is missing, for example `404: Parcel not found`.
- Convert **Nordholm headroom from kW to MW**. The national feed passes Nordholm's figures through unconverted.
- Treat `gridmap` as the official source. Only fall back to `vendor_estimate` (±`band_pct`, unvalidated) when gridmap has nothing, and **flag** every site that uses the fallback.

### 2. Extract signals from field notes with Claude
Some of what the rubric needs, such as community sentiment and the latest owner status, only exists in the business development team's free-text notes. The script makes one Anthropic API call per site and gets back structured JSON with:

- `owner_status`: `loi_signed` / `in_talks` / `not_contacted` / `refused` / `unknown`
- `community_sentiment`: `supportive` / `neutral` / `opposed` / `unknown`
- any other findings that should change how the site is scored, such as a newer note that contradicts an older one

Rules:
- **Every signal carries the exact quote it came from.** When the notes don't say, the answer is `unknown`, not a guess.
- The code checks that each quote really appears in the site's notes.
- **Claude reads the notes; the code decides the scores.**
- Prompts live in `prompts/` _(planned)_.

### 3. Score

| # | Criterion | Weight | Tiers (score 0–5) |
|---|---|---|---|
| C1 | Grid headroom at nearest substation | 30 | ≥ 4 MW → 5 · 2–4 → 3 · 1–2 → 1 · < 1 → 0 |
| C2 | Distance to substation | 15 | ≤ 1 km → 5 · ≤ 3 → 3 · ≤ 6 → 1 · > 6 → 0 |
| C3 | Landowner status | 20 | LOI signed → 5 · in talks → 3 · not contacted → 1 · refused → 0 |
| C4 | Council / community sentiment | 10 | supportive → 5 · neutral → 3 · opposed → 0 |
| C5 | Flood zone | 15 | none → 5 · low → 4 · medium → 2 · high → 0 |
| C6 | Usable area (~1,200 m² for 2 MW) | 10 | ≥ 1,200 m² → 5 · 800–1,200 → 2 · < 800 → 0 |

**Site score** = Σ (weight × tier ÷ 5), which runs from 0 to 100.

**Kill rules:**
- The site is inside a protected nature area. This rule comes from the sponsor.
- The site has no land-registry record. This one is our own conservative assumption: without a record, we can't rule out a protected area.

### 4. Display
- A ranked table of every site with its score, highlighting the top five.
- A per-site breakdown: each criterion's raw value, its tier, where the value came from (gridmap, vendor, landreg or notes), and the supporting quote.
- Flags for vendor-estimated headroom, missing data and excluded sites, each with a reason.
- Static output that feeds the one-page summary for Maren _(planned)_.

## Decisions and assumptions

The full reasoning is in [`Questions.md`](Questions.md). The main points:

- **Missing data.** Jonas suggested filling gaps with the dataset average. That's risky, and the choice belongs to the client. The output will show the ranking under three modes:

  | Mode | Approach | Risk |
  |---|---|---|
  | Real data | Leave out sites with missing data | Low |
  | Synthetic | Fill gaps with estimated values and flag them | Medium |
  | Averages | Fill gaps with the dataset average so every site gets a score | High risk / high reward |

- **Vendor fallback.** We accept the vendor's ±40% `band_pct` for the prototype, but flag every site that uses it. A flagged site that reaches the top five gets checked by hand.
- **Units.** Nordholm headroom is always converted from kW to MW.

## Repo layout

```
.
├── five-sites-by-thursday.md   # The brief
├── Questions.md                # Questions, review of Jonas's plan, assumptions
├── data/
│   ├── DATA_DICTIONARY.md      # Field definitions
│   ├── sites.json              # 40 candidate sites (exported 2026-09-21)
│   └── fetch_log.csv           # Log from the source data pull
├── score_sites.py              # (planned) load → extract → score → display
└── prompts/                    # (planned) Claude prompt(s)
```

## Still to deliver
- [x] `Questions.md`, committed before any scoring code
- [ ] Scoring script and Claude extraction
- [ ] Extraction check: hand-check a sample of sites against the model's output
- [ ] One public page Maren can read on her phone, plus `NOTE.md`
- [ ] `AI_LOG.md` and `ai-transcripts/`

**Time spent:** _TBD_
