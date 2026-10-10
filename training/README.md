# Hackathon Oracle: training

Predicts whether a hackathon project will win, trained on real Devpost data.

## Pipeline

```bash
pip install -r requirements.txt

python discover.py   # find past in-person college hackathons -> data/hackathons.json
python scrape.py     # scrape their galleries + project pages -> data/projects.csv
python train.py      # train + validate -> models/
python predict.py https://devpost.com/software/<project>          # score one project
python predict.py --gallery https://<hackathon>.devpost.com/project-gallery   # rank a whole gallery
```

`scrape.py` caches every page in `data/cache/` (gitignored), so re-runs are instant
and we never hit Devpost twice for the same page.

## How the model works

1. **Text score.** Each project's title, tagline and write-up are embedded with an open source
   Hugging Face model (`all-MiniLM-L6-v2`). A logistic regression on those embeddings gives one
   number: how much the project *reads* like past winners.
2. **Main model.** LightGBM or logistic regression (whichever validates better) on simple,
   explainable features plus that text score: write-up length and completeness, demo video,
   screenshots, GitHub link, team size, number of technologies, and tech flags (AI, hardware,
   mobile, game, cloud, web, blockchain).
3. **Explanations.** Per-project feature contributions turn into plain English reasons
   ("having a demo video helps").
4. **Similar winners.** Nearest neighbours among past winning projects (cosine similarity on the
   embeddings), which also drives the "best track" guess.

**Leakage guard:** winners often edit their page to say "we won Best Overall!". Words like
won / winner / prize / 1st place are stripped before training, and the list of prizes won is
never used as a feature.

## Validation

All validation is **grouped by hackathon**: the model is always scored on hackathons it has
never seen, which is exactly the Knight Hacks IX situation.

* `auc`: overall ranking quality (0.5 = coin flip, 1.0 = perfect)
* `precision_at_k`: inside each hackathon, take our top k picks where k is the real number of
  winners. What fraction actually won? Compare against `base_rate` (random guessing).
* `backtest`: train without Knight Hacks VIII, then predict it. How many of last year's real
  winners land in our top 10?

Numbers are written to `models/metrics.json`.
