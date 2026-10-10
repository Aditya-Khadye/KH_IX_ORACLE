"""Scrape Devpost galleries + project pages into one CSV for training.

Step 1: pick hackathons from data/hackathons.json (made by discover.py)
Step 2: walk each project gallery, collecting project links + the "Winner" badge
Step 3: fetch each project page (cached to disk) and parse features
Output: data/projects.csv

Usage:
    python scrape.py                    # default selection (2023+, 300-1500 regs, max 35 hackathons)
    python scrape.py --gallery https://knight-hacks-ix.devpost.com/project-gallery --out data/kh9.csv
        # scrape one specific gallery (used for live predictions on Sunday)
"""
import argparse
import csv
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).parent
DATA = HERE / "data"
CACHE = DATA / "cache"
HEADERS = {"User-Agent": "KnightHacksIX-Oracle (student hackathon project)"}

# Always include these even if discovery missed them (same event, so most relevant).
EXTRA = [
    {"title": "Knight Hacks VII", "gallery": "https://knight-hacks-vii.devpost.com/project-gallery"},
    {"title": "Knight Hacks VIII", "gallery": "https://knighthacksviii.devpost.com/project-gallery"},
]

session = requests.Session()
session.headers.update(HEADERS)


def get(url: str, delay: float = 0.25) -> str:
    """GET with an on-disk cache so we never scrape the same page twice."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / (hashlib.md5(url.encode()).hexdigest() + ".html")
    if key.exists():
        return key.read_text(errors="ignore")
    for attempt in range(3):
        try:
            r = session.get(url, timeout=25)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            key.write_text(r.text)
            time.sleep(delay)
            return r.text
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
    return ""


def year_of(h) -> int:
    ys = re.findall(r"(\d{4})", h.get("dates") or "")
    return int(ys[-1]) if ys else 0


def pick_hackathons(max_n: int):
    hacks = json.loads((DATA / "hackathons.json").read_text())
    chosen = [h for h in hacks if year_of(h) >= 2023 and 300 <= h["registrations"] <= 1500]
    chosen.sort(key=lambda h: -year_of(h))
    chosen = chosen[:max_n]
    have = {h["gallery"].rstrip("/") for h in chosen}
    for e in EXTRA:
        if e["gallery"].rstrip("/") not in have:
            chosen.append(e)
    return chosen


def walk_gallery(gallery_url: str):
    """Yield (project_url, is_winner, n_members) for every project in a gallery."""
    page = 1
    while True:
        html = get(f"{gallery_url}?page={page}")
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".gallery-item")
        if not items:
            break
        for it in items:
            a = it.select_one("a.link-to-software")
            if not a:
                continue
            yield (
                a["href"],
                bool(it.select_one(".entry-badge .winner")),
                len(it.select(".members .user-profile-link")),
            )
        page += 1
        if page > 60:  # safety stop
            break


def parse_project(html: str) -> dict:
    s = BeautifulSoup(html, "html.parser")
    # read tech tags and links BEFORE removing those blocks from the description
    built_with = "|".join(t.get_text(strip=True).lower() for t in s.select("#built-with .cp-tag"))
    links = [a.get("href", "") for a in s.select(".app-links a")]
    details = s.select_one("#app-details-left")
    text = ""
    headings = []
    if details:
        # drop the "Built With" and "Try it out" blocks from the description text
        for sec in details.select("#built-with, nav.app-links"):
            sec.decompose()
        headings = [h.get_text(strip=True) for h in details.select("h2")]
        text = details.get_text(" ", strip=True)
    tagline = s.select_one("#software-header p")
    prizes = [
        w.parent.get_text(" ", strip=True).replace("Winner ", "", 1)
        for w in s.select("#submissions .winner")
    ]
    return {
        "title": (s.select_one("#app-title") or s.new_tag("x")).get_text(strip=True),
        "tagline": tagline.get_text(strip=True) if tagline else "",
        "description": text,
        "n_sections": len(headings),
        "built_with": built_with,
        "team_size_page": len(s.select("#app-team .software-team-member")),
        "has_video": int(bool(s.select_one('#gallery iframe, iframe[src*="youtube"], iframe[src*="vimeo"]'))),
        "n_images": len(s.select("#gallery img")),
        "has_github": int(any("github.com" in l for l in links)),
        "n_links": len(links),
        "prizes_won": "|".join(prizes),
    }


def scrape_gallery(title: str, gallery: str, workers: int = 8):
    entries = list(walk_gallery(gallery.rstrip("/")))
    print(f"{title}: {len(entries)} projects, {sum(e[1] for e in entries)} winners")

    def one(e):
        url, win, members = e
        html = get(url)
        if not html:
            return None
        row = parse_project(html)
        row.update({"hackathon": title, "url": url, "winner": int(win), "team_size": members or row["team_size_page"]})
        return row

    with ThreadPoolExecutor(workers) as ex:
        return [r for r in ex.map(one, entries) if r]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-hackathons", type=int, default=35)
    ap.add_argument("--gallery", help="scrape just this gallery URL")
    ap.add_argument("--title", default="Target")
    ap.add_argument("--out", default=str(DATA / "projects.csv"))
    args = ap.parse_args()

    if args.gallery:
        hacks = [{"title": args.title, "gallery": args.gallery}]
    else:
        hacks = pick_hackathons(args.max_hackathons)

    rows = []
    for h in hacks:
        try:
            rows += scrape_gallery(h["title"], h["gallery"])
        except Exception as e:
            print(f"  failed {h['title']}: {e}")

    if not rows:
        print("no rows scraped")
        return
    fields = list(rows[0].keys())
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    wins = sum(r["winner"] for r in rows)
    print(f"\nwrote {len(rows)} projects ({wins} winners, {wins / len(rows):.1%}) -> {args.out}")


if __name__ == "__main__":
    main()
