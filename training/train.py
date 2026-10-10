"""Train the Hackathon Oracle.

Model design (two stages, so predictions stay explainable):
  1. text model: logistic regression on sentence embeddings of the write-up
     -> one number, "text_score" (how much the project *reads* like past winners)
  2. main model: LightGBM (or logistic regression, whichever validates better) on
     the numeric features + text_score

Validation is grouped by hackathon: we always predict hackathons the model has
never seen, which is exactly the Knight Hacks IX situation.

Outputs:
  models/oracle.joblib      everything the backend needs
  models/metrics.json       validation numbers + Knight Hacks VIII backtest
  models/insights.json      "what wins hackathons" stats for the frontend charts
  models/winners_index.npz  embeddings of past winners for "similar winners"

Usage:
    python train.py
"""
import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from oracle_core import NUMERIC, embed, numeric_features, text_for_embedding

HERE = Path(__file__).parent
DATA = HERE / "data"
MODELS = HERE / "models"
BACKTEST = "Knight Hacks VIII"
SEED = 7


def load():
    path = DATA / "projects.csv"
    if not path.exists():  # fall back to the compressed copy committed to the repo
        path = DATA / "projects.csv.gz"
    df = pd.read_csv(path).drop_duplicates("url").reset_index(drop=True)
    df = df[df["title"].notna()].reset_index(drop=True)
    return df


def get_embeddings(df):
    cache = DATA / "embeddings.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        known = dict(zip(z["urls"], z["emb"]))
        missing = [u for u in df["url"] if u not in known]
    else:
        known, missing = {}, list(df["url"])
    if missing:
        sub = df[df["url"].isin(missing)]
        print(f"embedding {len(sub)} projects...")
        for u, e in zip(sub["url"], embed(text_for_embedding(sub))):
            known[u] = e
        np.savez(cache, urls=np.array(list(known)), emb=np.array(list(known.values())))
    return np.vstack([known[u] for u in df["url"]])


def text_model():
    return LogisticRegression(C=0.5, max_iter=2000, class_weight="balanced")


def oof_text_score(E, y, groups, n_splits=5):
    """Out-of-fold text scores, so stage 2 never sees text scores fit on its own rows."""
    out = np.zeros(len(y))
    for tr, te in GroupKFold(n_splits).split(E, y, groups):
        m = text_model().fit(E[tr], y[tr])
        out[te] = m.predict_proba(E[te])[:, 1]
    return out


def lgb_model():
    return lgb.LGBMClassifier(
        n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=30,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
        class_weight="balanced", random_state=SEED, verbose=-1,
    )


def lr_model():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=2000, class_weight="balanced"))


def fit_stage2(kind, X, y):
    return (lgb_model() if kind == "lgbm" else lr_model()).fit(X, y)


def precision_at_k(df_eval, prob_col="prob"):
    """Per hackathon: of our top-k picks (k = real number of winners), how many really won?"""
    hits, total = 0, 0
    for _, g in df_eval.groupby("hackathon"):
        k = int(g["winner"].sum())
        if k == 0:
            continue
        top = g.nlargest(k, prob_col)
        hits += int(top["winner"].sum())
        total += k
    return hits / total if total else float("nan")


def cross_validate(df, X_num, E, y, groups, kind):
    probs = np.zeros(len(y))
    for tr, te in GroupKFold(5).split(X_num, y, groups):
        ts_tr = oof_text_score(E[tr], y[tr], groups[tr])
        ts_te = text_model().fit(E[tr], y[tr]).predict_proba(E[te])[:, 1]
        Xtr = np.column_stack([X_num[tr], ts_tr])
        Xte = np.column_stack([X_num[te], ts_te])
        probs[te] = fit_stage2(kind, Xtr, y[tr]).predict_proba(Xte)[:, 1]
    ev = df[["hackathon", "winner"]].copy()
    ev["prob"] = probs
    per_hack = [
        roc_auc_score(g["winner"], g["prob"])
        for _, g in ev.groupby("hackathon")
        if 0 < g["winner"].sum() < len(g)
    ]
    return {
        "auc": float(roc_auc_score(y, probs)),
        "mean_auc_per_hackathon": float(np.mean(per_hack)),
        "precision_at_k": float(precision_at_k(ev)),
        "base_rate": float(y.mean()),
    }, probs


def backtest(df, X_num, E, y, groups, kind):
    test = (df["hackathon"] == BACKTEST).values
    if test.sum() == 0:
        return None
    tr = ~test
    ts_tr = oof_text_score(E[tr], y[tr], groups[tr])
    ts_te = text_model().fit(E[tr], y[tr]).predict_proba(E[test])[:, 1]
    m = fit_stage2(kind, np.column_stack([X_num[tr], ts_tr]), y[tr])
    p = m.predict_proba(np.column_stack([X_num[test], ts_te]))[:, 1]
    bt = df.loc[test, ["title", "winner", "prizes_won"]].copy()
    bt["prob"] = p
    bt = bt.sort_values("prob", ascending=False).reset_index(drop=True)
    k = int(bt["winner"].sum())
    top10 = bt.head(10)
    return {
        "hackathon": BACKTEST,
        "n_projects": int(len(bt)),
        "n_winners": k,
        "winners_in_our_top_k": int(bt.head(k)["winner"].sum()),
        "winners_in_our_top_10": int(top10["winner"].sum()),
        "random_expected_top_10": round(10 * k / len(bt), 1),
        "auc": float(roc_auc_score(bt["winner"], bt["prob"])),
        "best_overall_rank": next(
            (int(i) + 1 for i, r in bt.iterrows() if "Best Overall" in str(r["prizes_won"])), None
        ),
        "top_10": [
            {"title": r.title, "prob": round(float(r.prob), 3), "actually_won": bool(r.winner),
             "prizes": r.prizes_won if isinstance(r.prizes_won, str) else ""}
            for r in top10.itertuples()
        ],
    }


def insights(df, X_num):
    d = X_num.copy()
    d["winner"] = df["winner"].values
    d["desc_words"] = np.expm1(d["log_desc_words"])

    def rate(mask):
        return round(float(d.loc[mask, "winner"].mean()), 3) if mask.sum() >= 20 else None

    out = {
        "n_projects": int(len(d)),
        "n_hackathons": int(df["hackathon"].nunique()),
        "overall_win_rate": round(float(d["winner"].mean()), 3),
        "video": {"with": rate(d["has_video"] == 1), "without": rate(d["has_video"] == 0)},
        "github": {"with": rate(d["has_github"] == 1), "without": rate(d["has_github"] == 0)},
        "ai": {"uses_ai": rate(d["uses_ai"] == 1), "no_ai": rate(d["uses_ai"] == 0)},
        "hardware": {"uses_hardware": rate(d["uses_hardware"] == 1), "no_hardware": rate(d["uses_hardware"] == 0)},
        "team_size": {str(int(t)): rate(d["team_size"] == t) for t in sorted(d["team_size"].unique())},
        "writeup_length": {},
        "n_tech": {},
    }
    bins = [0, 150, 300, 500, 800, 10**9]
    names = ["<150 words", "150-300", "300-500", "500-800", "800+"]
    for lo, hi, n in zip(bins, bins[1:], names):
        out["writeup_length"][n] = rate((d["desc_words"] >= lo) & (d["desc_words"] < hi))
    for lo, hi, n in [(0, 3, "0-2"), (3, 6, "3-5"), (6, 9, "6-8"), (9, 99, "9+")]:
        out["n_tech"][n] = rate((d["n_tech"] >= lo) & (d["n_tech"] < hi))
    return out


def main():
    MODELS.mkdir(exist_ok=True)
    df = load()
    y = df["winner"].astype(int).values
    groups = df["hackathon"].values
    print(f"{len(df)} projects, {df['hackathon'].nunique()} hackathons, win rate {y.mean():.1%}")

    X_num = numeric_features(df)
    E = get_embeddings(df)

    results = {}
    for kind in ["lr", "lgbm"]:
        results[kind], _ = cross_validate(df, X_num.values, E, y, groups, kind)
        print(kind, results[kind])
    best = max(results, key=lambda k: results[k]["mean_auc_per_hackathon"])
    print("best:", best)

    bt = backtest(df, X_num.values, E, y, groups, best)
    if bt:
        print(json.dumps({k: v for k, v in bt.items() if k != "top_10"}, indent=1))

    # final fit on everything
    text_m = text_model().fit(E, y)
    ts = oof_text_score(E, y, groups)
    X_all = np.column_stack([X_num.values, ts])
    final = fit_stage2(best, X_all, y)

    feature_names = NUMERIC + ["text"]
    joblib.dump(
        {"kind": best, "text_model": text_m, "model": final, "features": feature_names,
         "feature_means": X_all.mean(axis=0), "base_rate": float(y.mean())},
        MODELS / "oracle.joblib",
    )

    wins = df["winner"].values == 1
    np.savez_compressed(
        MODELS / "winners_index.npz",
        emb=E[wins].astype(np.float16),
        title=df.loc[wins, "title"].values,
        hackathon=df.loc[wins, "hackathon"].values,
        prizes=df.loc[wins, "prizes_won"].fillna("").values,
        url=df.loc[wins, "url"].values,
    )

    (MODELS / "metrics.json").write_text(json.dumps(
        {"chosen_model": best, "cross_validation": results, "backtest": bt}, indent=1))
    (MODELS / "insights.json").write_text(json.dumps(insights(df, X_num), indent=1))
    print("saved models/ (oracle.joblib, metrics.json, insights.json, winners_index.npz)")


if __name__ == "__main__":
    main()
