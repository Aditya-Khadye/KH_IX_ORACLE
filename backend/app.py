"""Hackathon Oracle API (FastAPI).

Run:
    cd backend
    pip install -r requirements.txt
    uvicorn app:app --reload --port 8000

Endpoints (all return JSON):
    GET  /health
    POST /predict           {"url": "https://devpost.com/software/..."}
                            or {"title": ..., "tagline": ..., "description": ...,
                                "built_with": "python|react", "team_size": 3, "has_video": 1, ...}
    GET  /leaderboard?gallery=https://knight-hacks-ix.devpost.com/project-gallery
    GET  /insights          stats for the "what wins hackathons" charts
    GET  /metrics           validation + Knight Hacks VIII backtest
"""
import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

TRAINING = Path(__file__).resolve().parent.parent / "training"
sys.path.insert(0, str(TRAINING))

from predict import Oracle  # noqa: E402
from scrape import get, parse_project, scrape_gallery  # noqa: E402

app = FastAPI(title="Hackathon Oracle")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

oracle = Oracle(TRAINING / "models")
_leaderboards: dict = {}


class ProjectIn(BaseModel):
    url: Optional[str] = None
    title: Optional[str] = None
    tagline: Optional[str] = ""
    description: Optional[str] = ""
    built_with: Optional[str] = ""  # pipe separated, e.g. "python|react|gemini"
    team_size: Optional[int] = 1
    has_video: Optional[int] = 0
    n_images: Optional[int] = 0
    has_github: Optional[int] = 0
    n_links: Optional[int] = 0
    n_sections: Optional[int] = 0


@app.get("/health")
def health():
    return {"ok": True, "model": oracle.kind}


@app.post("/predict")
def predict(p: ProjectIn):
    if p.url:
        if "devpost.com/software/" not in p.url:
            raise HTTPException(400, "url must be a devpost.com/software/... project page")
        html = get(p.url)
        if not html:
            raise HTTPException(502, "could not fetch that Devpost page")
        row = parse_project(html)
        row["url"] = p.url
    elif p.title:
        row = p.model_dump()
    else:
        raise HTTPException(400, "send either a Devpost url or at least a title")
    return oracle.score(pd.DataFrame([row]))[0]


@app.get("/leaderboard")
def leaderboard(gallery: str, refresh: bool = False):
    """Rank every project in a Devpost gallery by predicted win chance (cached)."""
    if refresh or gallery not in _leaderboards:
        rows = scrape_gallery("Target", gallery)
        if not rows:
            raise HTTPException(404, "no projects found in that gallery (is it public yet?)")
        scored = oracle.score(pd.DataFrame(rows), explain=True, n_similar=1)
        scored.sort(key=lambda r: -r["win_prob"])
        for i, r in enumerate(scored, 1):
            r["rank"] = i
        _leaderboards[gallery] = scored
    return {"gallery": gallery, "projects": _leaderboards[gallery]}


@app.get("/insights")
def insights():
    return json.loads((TRAINING / "models" / "insights.json").read_text())


@app.get("/metrics")
def metrics():
    return json.loads((TRAINING / "models" / "metrics.json").read_text())
