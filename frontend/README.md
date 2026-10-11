# Hackathon Oracle frontend

The frontend is a static, browser-native app. Project entry is a separate first step in the circular orb. Submitting a project starts the smoke-vortex reading animation; after a successful prediction, the orb expands into a glass portal with Results, Leaderboard, What wins, and Accuracy tabs.

## Run locally

Start the backend in one terminal:

```bash
cd backend
uvicorn app:app --reload --port 8000
```

Serve the frontend from another terminal:

```bash
cd frontend
python3 -m http.server 5500
```

Open <http://localhost:5500>. The frontend calls `http://localhost:8000` by default. To use a different backend, add an `api` query parameter, for example:

```text
http://localhost:5500/?api=https://your-backend.example
```

After the project prediction completes, the results portal includes:

- **Results** — see the predicted win chance, contributing signals, and similar past winners.
- **Leaderboard** — rank projects from a Devpost gallery.
- **What wins** — inspect historical win rates and project patterns.
- **Accuracy** — review cross-validation metrics and the Knight Hacks VIII backtest.

The three research views load their data from the backend when first opened. Prediction and gallery scoring require the backend and its model dependencies to be running.
