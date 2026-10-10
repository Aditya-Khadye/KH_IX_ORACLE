# Hackathon Oracle frontend

One static page (`index.html`), no build step. It talks to the backend at `http://localhost:8000`.

```bash
# terminal 1: backend
cd backend && uvicorn app:app --reload --port 8000

# terminal 2: frontend
cd frontend && python3 -m http.server 5500
# open http://localhost:5500
```

Opening `index.html` directly (double click) also works in most browsers.
To point it at a different backend: `http://localhost:5500/?api=https://your-backend-url`

Tabs:
* **Check your odds**: paste a Devpost link (or describe the project) and get a win chance, reasons, similar past winners, best track
* **Leaderboard**: rank every project in a Devpost gallery
* **What wins hackathons**: charts from about 3,500 real projects
* **How accurate is it?**: validation numbers + the Knight Hacks VIII backtest
