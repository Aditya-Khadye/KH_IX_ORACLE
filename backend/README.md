# Hackathon Oracle API

```bash
cd backend
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
# docs: http://localhost:8000/docs
```

The first request downloads the small open source embedding model (about 90 MB), so give it a minute.
CORS is open, so the frontend can call it from any localhost port.

## Endpoints

### `POST /predict`
Score one project. Send either a Devpost link:
```json
{"url": "https://devpost.com/software/emergent-b2t1fl"}
```
or the raw fields (useful for scoring our own project before it's on Devpost):
```json
{"title": "Market Symphony", "tagline": "...", "description": "...",
 "built_with": "python|react|gemini", "team_size": 2, "has_video": 1, "has_github": 1}
```
Response:
```json
{
  "title": "Emergent",
  "win_prob": 0.65,
  "best_track": "Sponsor challenge",
  "top_reasons": [{"factor": "team size", "effect": "helps", "strength": 0.4}, ...],
  "similar_winners": [{"title": "...", "hackathon": "...", "prizes": "...", "url": "...", "similarity": 0.67}, ...]
}
```

### `GET /leaderboard?gallery=<devpost gallery url>`
Scrapes and ranks every project in a gallery (cached after the first call, add `&refresh=true`
to re-scrape). Each project has the same fields as `/predict` plus `rank`.
Example: `/leaderboard?gallery=https://knight-hacks-vii.devpost.com/project-gallery`

### `GET /insights`
Win rates from about 3,500 real projects for the "What wins hackathons" charts: demo video vs not,
team size, write-up length, number of technologies, AI / hardware, GitHub link.

### `GET /metrics`
Validation numbers and the Knight Hacks VIII backtest (our predicted top 10 vs who actually won).
