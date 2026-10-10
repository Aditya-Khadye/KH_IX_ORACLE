"""Score projects with the trained Oracle and explain why.

Used by the backend, but also runnable on its own:
    python predict.py https://devpost.com/software/some-project
    python predict.py --gallery https://knight-hacks-ix.devpost.com/project-gallery
"""
import argparse
import re
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from oracle_core import LABELS, embed, numeric_features, text_for_embedding

MODELS = Path(__file__).parent / "models"

TRACKS = [
    ("Best Overall", r"overall|grand prize|1st place|first place|best hack"),
    ("Best AI", r"\bai\b|machine learning|artificial intelligence|\bml\b|llm|gemini|openai"),
    ("Best Hardware", r"hardware|embedded|iot|arduino|jetson"),
    ("Best Game", r"\bgame"),
    ("Best Design", r"design|ui|ux|prettiest|figma|adobe"),
    ("Social Impact", r"social good|impact|health|sustainab|climate|education|accessib|for good"),
    ("Best Beginner", r"beginner|first[- ]time|newbie|freshman"),
    ("Fintech", r"fintech|financ|bank|capital one|bny|jpmorgan"),
]


def track_of(prize: str) -> str:
    p = prize.lower()
    for name, pat in TRACKS:
        if re.search(pat, p):
            return name
    return "Sponsor challenge"


class Oracle:
    def __init__(self, models_dir: Path = MODELS):
        b = joblib.load(models_dir / "oracle.joblib")
        self.kind, self.text_model, self.model = b["kind"], b["text_model"], b["model"]
        self.features, self.means = b["features"], b["feature_means"]
        self.base_rate = b["base_rate"]
        w = np.load(models_dir / "winners_index.npz", allow_pickle=True)
        self.w_emb = w["emb"].astype(np.float32)
        self.w_meta = pd.DataFrame({k: w[k] for k in ["title", "hackathon", "prizes", "url"]})

    def _contributions(self, X):
        """Per-feature push toward/away from winning, in log-odds."""
        if self.kind == "lgbm":
            return self.model.predict_proba(X, pred_contrib=True)[:, :-1]
        scaler, lr = self.model[0], self.model[-1]
        return scaler.transform(X) * lr.coef_[0]

    def score(self, df: pd.DataFrame, explain: bool = True, n_similar: int = 3) -> list:
        df = df.reset_index(drop=True).copy()
        if "team_size" not in df and "team_size_page" in df:
            df["team_size"] = df["team_size_page"]
        for col, default in [("n_sections", 0), ("has_video", 0), ("n_images", 0),
                             ("has_github", 0), ("n_links", 0), ("team_size", 1),
                             ("built_with", ""), ("tagline", ""), ("description", "")]:
            if col not in df:
                df[col] = default
        E = embed(text_for_embedding(df))
        text_score = self.text_model.predict_proba(E)[:, 1]
        X = np.column_stack([numeric_features(df).values, text_score])
        probs = self.model.predict_proba(X)[:, 1]
        contrib = self._contributions(X) if explain else None
        sims = E @ self.w_emb.T

        out = []
        for i in range(len(df)):
            item = {
                "title": df.loc[i, "title"],
                "url": df.loc[i].get("url", None),
                "win_prob": round(float(probs[i]), 4),
            }
            if explain:
                order = np.argsort(contrib[i])
                item["top_reasons"] = [
                    {"factor": LABELS.get(self.features[j], self.features[j]),
                     "effect": "helps" if contrib[i, j] > 0 else "hurts",
                     "strength": round(float(abs(contrib[i, j])), 3)}
                    for j in list(order[::-1][:3]) + list(order[:2])
                    if abs(contrib[i, j]) > 1e-6
                ]
                # skip near-identical matches (the project itself, if it's a past winner)
                ranked = [j for j in np.argsort(-sims[i]) if sims[i, j] < 0.98]
                top = np.array(ranked[:n_similar])
                similar = self.w_meta.iloc[top]
                item["similar_winners"] = [
                    {"title": r.title, "hackathon": r.hackathon, "prizes": r.prizes,
                     "url": r.url, "similarity": round(float(sims[i, j]), 3)}
                    for j, r in zip(top, similar.itertuples())
                ]
                tracks = Counter(
                    track_of(p) for ps in self.w_meta.iloc[np.argsort(-sims[i])[:15]]["prizes"]
                    for p in str(ps).split("|") if p
                )
                # most prizes are sponsor prizes, so prefer a named track when one shows up
                named = [(t, c) for t, c in tracks.most_common() if t != "Sponsor challenge"]
                item["best_track"] = named[0][0] if named else "Sponsor challenge"
            out.append(item)
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--gallery")
    args = ap.parse_args()
    from scrape import get, parse_project, scrape_gallery

    oracle = Oracle()
    if args.gallery:
        rows = pd.DataFrame(scrape_gallery("Target", args.gallery))
        res = sorted(oracle.score(rows, explain=False), key=lambda r: -r["win_prob"])
        for rank, r in enumerate(res[:25], 1):
            print(f"{rank:>3}. {r['win_prob']:.1%}  {r['title']}")
    elif args.url:
        row = parse_project(get(args.url))
        row["url"] = args.url
        import json
        print(json.dumps(oracle.score(pd.DataFrame([row]))[0], indent=1))


if __name__ == "__main__":
    main()
