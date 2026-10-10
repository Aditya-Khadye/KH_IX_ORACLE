"""Find past in-person college hackathons on Devpost to use as training data.

Uses Devpost's public hackathon listing API. Keeps hackathons that:
  * have ended and announced winners
  * were in person (not "Online")
  * are a similar size to Knight Hacks (roughly 150 to 3000 registrations)

Usage:
    python discover.py            # writes data/hackathons.json
"""
import json
import time
from pathlib import Path

import requests

API = "https://devpost.com/api/hackathons"
OUT = Path(__file__).parent / "data" / "hackathons.json"
HEADERS = {"User-Agent": "KnightHacksIX-Oracle (student hackathon project)"}

# Well known in-person student hackathons. Search terms, not exact names.
SEARCH_TERMS = [
    "knight hacks", "shellhacks", "swamphacks", "hackgt", "bitcamp", "hacknc",
    "hackprinceton", "pennapps", "treehacks", "calhacks", "hackmit", "mhacks",
    "boilermake", "hackillinois", "hacktx", "hackrice", "hackumbc", "hacklytics",
    "rowdyhacks", "citrus hack", "hacksc", "lahacks", "sd hacks", "hack the north",
    "uofthacks", "hackbeanpot", "hack@brown", "hacknyu", "hackduke", "vandyhacks",
    "hackuci", "madhacks", "wildhacks", "hackohio", "hackisu", "hoyahacks",
    "technica", "hackru", "hackpsu", "hackutd", "hackathon at ucf", "fiu hackathon",
    "hack@cewit", "dandyhacks", "cruzhacks", "hacksmu", "hackmidwest", "deltahacks",
]

MIN_REG, MAX_REG = 150, 3000


def search(term: str, pages: int = 2):
    out = []
    for page in range(1, pages + 1):
        r = requests.get(
            API,
            params={"search": term, "status[]": "ended", "page": page},
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        hs = r.json().get("hackathons", [])
        if not hs:
            break
        out.extend(hs)
        time.sleep(0.3)
    return out


def keep(h) -> bool:
    loc = (h.get("displayed_location") or {}).get("location", "")
    return (
        h.get("winners_announced")
        and loc.lower() != "online"
        and MIN_REG <= (h.get("registrations_count") or 0) <= MAX_REG
    )


def main():
    seen = {}
    for term in SEARCH_TERMS:
        try:
            for h in search(term):
                if keep(h):
                    seen[h["id"]] = {
                        "id": h["id"],
                        "title": h["title"],
                        "url": h["url"],
                        "gallery": h["submission_gallery_url"],
                        "registrations": h["registrations_count"],
                        "dates": h.get("submission_period_dates"),
                        "location": h["displayed_location"]["location"],
                    }
        except Exception as e:  # keep going if one search fails
            print(f"search failed for {term!r}: {e}")
    hacks = sorted(seen.values(), key=lambda h: h["title"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(hacks, indent=1))
    print(f"kept {len(hacks)} hackathons -> {OUT}")
    for h in hacks:
        print(f"  {h['registrations']:>5}  {h['title']}  ({h['dates']})")


if __name__ == "__main__":
    main()
