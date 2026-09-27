"""Five Sites: read each site's field notes with Claude.

Claude turns the free-text notes into structured signals (owner status,
community sentiment, area / reserve claims, other findings), each carrying the
exact quote it came from. Claude only reads; the scoring scripts decide.

Every quote is checked in code against the notes. A quote that isn't found
verbatim turns its signal into "unknown". The date of each signal comes from
the note that contains the quote, never from the model.

Raw model output is cached in data/extractions.json, keyed by site and by a hash
of the notes, prompt and model, so later runs don't call the API again.
Verification runs on every load, cached or not.
"""

import hashlib
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

ROOT = Path(__file__).parent
PROMPT_PATH = ROOT / "prompts" / "extract_notes.md"
CACHE_PATH = ROOT / "data" / "extractions.json"

MODEL = "claude-opus-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


# ---------------------------------------------------------------- schema

class OwnerStatus(BaseModel):
    value: Literal["loi_signed", "in_talks", "not_contacted", "refused", "unknown"]
    quote: str


class CommunitySentiment(BaseModel):
    value: Literal["supportive", "neutral", "opposed", "unknown"]
    quote: str


class AreaClaim(BaseModel):
    m2: float
    quote: str


class ReserveConcern(BaseModel):
    quote: str


class Finding(BaseModel):
    finding: str
    quote: str


class NotesExtraction(BaseModel):
    owner_status: OwnerStatus
    community_sentiment: CommunitySentiment
    area_claim: AreaClaim | None
    reserve_concern: ReserveConcern | None
    other_findings: list[Finding]


EMPTY_EXTRACTION = {
    "owner_status": {"value": "unknown", "quote": ""},
    "community_sentiment": {"value": "unknown", "quote": ""},
    "area_claim": None,
    "reserve_concern": None,
    "other_findings": [],
}


# ---------------------------------------------------------------- helpers

def latest_structured_owner_status(notes):
    """owner_status from the most recent note that has one (by date, not list order)."""
    with_status = [n for n in notes if n.get("owner_status")]
    if not with_status:
        return None, None
    latest = max(with_status, key=lambda n: n["date"])
    return latest["owner_status"], latest["date"]


def _render_notes(site):
    lines = [f"Site {site['site_id']} ({site['name']})", "", "Notes:"]
    for n in site.get("field_notes") or []:
        header = f"- date: {n['date']} | author: {n['author']}"
        if n.get("owner_status"):
            header += f" | owner_status: {n['owner_status']}"
        lines += [header, f"  text: {n['text']}"]
    return "\n".join(lines)


def _cache_key(site, prompt):
    payload = json.dumps(
        {"model": MODEL, "prompt": prompt, "notes": site.get("field_notes") or []},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _norm(text):
    return " ".join(text.split())


def _note_for_quote(quote, notes):
    """The latest note whose text contains `quote` verbatim (whitespace-normalised)."""
    q = _norm(quote or "")
    if not q:
        return None
    matches = [n for n in notes if q in _norm(n["text"])]
    return max(matches, key=lambda n: n["date"]) if matches else None


# ---------------------------------------------------------------- verify

def verify(raw, notes):
    """Check every quote against the notes; return signals with dates and flags."""
    flags = []

    def signal(name, label):
        s = raw[name]
        if s["value"] == "unknown":
            return {"value": "unknown", "quote": None, "date": None}
        note = _note_for_quote(s["quote"], notes)
        if note is None:
            flags.append(f"{label}: Claude said '{s['value']}' but its quote isn't in the notes; treated as unknown")
            return {"value": "unknown", "quote": None, "date": None}
        return {"value": s["value"], "quote": s["quote"], "date": note["date"]}

    owner = signal("owner_status", "owner status")
    sentiment = signal("community_sentiment", "sentiment")

    structured, structured_date = latest_structured_owner_status(notes)
    if structured and owner["value"] != structured:
        flags.append(f"owner status: Claude read '{owner['value']}', latest structured "
                     f"status is '{structured}' ({structured_date}); check by hand")

    area_claim = None
    if raw.get("area_claim"):
        note = _note_for_quote(raw["area_claim"]["quote"], notes)
        if note:
            area_claim = {"m2": raw["area_claim"]["m2"], "quote": raw["area_claim"]["quote"],
                          "date": note["date"]}
        else:
            flags.append("area claim: quote not found in notes; ignored")

    reserve_concern = None
    if raw.get("reserve_concern"):
        note = _note_for_quote(raw["reserve_concern"]["quote"], notes)
        if note:
            reserve_concern = {"quote": raw["reserve_concern"]["quote"], "date": note["date"]}
        else:
            flags.append("reserve concern: quote not found in notes; ignored")

    findings = []
    for f in raw.get("other_findings") or []:
        note = _note_for_quote(f["quote"], notes)
        if note:
            findings.append({"finding": f["finding"], "quote": f["quote"], "date": note["date"]})
        else:
            flags.append(f"finding '{f['finding']}': quote not found in notes; ignored")

    return {
        "owner_status": owner,
        "community_sentiment": sentiment,
        "area_claim": area_claim,
        "reserve_concern": reserve_concern,
        "other_findings": findings,
        "flags": flags,
    }


# ---------------------------------------------------------------- extract

def _call_claude(client, site, prompt):
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=prompt,
        messages=[{"role": "user", "content": _render_notes(site)}],
        output_format=NotesExtraction,
        betas=[FALLBACK_BETA],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"refused ({response.stop_details})")
    if response.parsed_output is None:
        raise RuntimeError(f"no structured output (stop_reason={response.stop_reason})")
    return response.parsed_output.model_dump()


def _load_cache():
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache):
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                          encoding="utf-8")


def extract_all(raw_sites):
    """Return {site_id: verified extraction} for every site, calling Claude only on cache misses."""
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    cache = _load_cache()
    client = None
    results = {}

    for site in raw_sites:
        site_id = site["site_id"]
        notes = site.get("field_notes") or []
        key = _cache_key(site, prompt)
        extra_flags = []

        if not notes:
            raw = EMPTY_EXTRACTION
        elif cache.get(site_id, {}).get("key") == key:
            raw = cache[site_id]["extraction"]
        else:
            try:
                if client is None:
                    import anthropic
                    client = anthropic.Anthropic()
                print(f"Reading notes for {site_id} with {MODEL}…", file=sys.stderr)
                raw = _call_claude(client, site, prompt)
                cache[site_id] = {"key": key, "model": MODEL, "extraction": raw}
                _save_cache(cache)
            except Exception as e:  # no key, network, refusal: degrade to unknown, loudly
                print(f"WARNING: notes extraction failed for {site_id}: {e}", file=sys.stderr)
                raw = EMPTY_EXTRACTION
                extra_flags.append("notes not read by Claude (extraction failed); C3/C4 unknown")

        verified = verify(raw, notes)
        verified["flags"] = extra_flags + verified["flags"]
        verified["extraction_failed"] = bool(extra_flags)
        results[site_id] = verified

    return results


if __name__ == "__main__":
    from sites_core import load_sites

    for sid, ex in extract_all(load_sites()).items():
        print(sid, json.dumps(ex, ensure_ascii=False))
