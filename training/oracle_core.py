"""Shared feature engineering for training and the backend.

Keep everything that turns a project into model inputs in this one file so
training and serving can never drift apart.
"""
import math
import re

import numpy as np
import pandas as pd

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Words winners often add AFTER winning ("We won Best Overall!"). Strip them so
# the model can't cheat by reading the result off the page.
LEAK_RE = re.compile(
    r"\b(won|winner|winners|winning|1st|2nd|3rd|first place|second place|third place|"
    r"prize|prizes|award|awarded|grand prize)\b",
    re.I,
)

TECH_GROUPS = {
    "uses_ai": ["openai", "gpt", "chatgpt", "gemini", "claude", "anthropic", "llm", "langchain",
                "llama", "huggingface", "hugging-face", "transformers", "pytorch", "tensorflow",
                "scikit-learn", "machine-learning", "ai", "ollama", "groq", "mistral", "cohere",
                "elevenlabs", "whisper", "opencv", "yolo", "vertex-ai", "bedrock"],
    "uses_hardware": ["arduino", "raspberry-pi", "esp32", "jetson", "sensors", "hardware",
                      "3d-printing", "microcontroller", "c", "raspberrypi"],
    "uses_mobile": ["swift", "swiftui", "kotlin", "flutter", "react-native", "android", "ios", "expo"],
    "uses_game": ["unity", "godot", "unreal-engine", "pygame", "c#", "phaser", "three.js"],
    "uses_cloud": ["aws", "google-cloud", "gcp", "azure", "vercel", "firebase", "vultr",
                   "cloudflare", "heroku", "supabase", "docker", "kubernetes"],
    "uses_web": ["react", "next.js", "nextjs", "vue", "svelte", "javascript", "typescript",
                 "html", "css", "tailwind", "node.js", "flask", "fastapi", "django"],
    "uses_blockchain": ["solana", "ethereum", "solidity", "web3", "blockchain"],
}

NUMERIC = [
    "log_desc_words", "n_sections", "n_tech", "team_size", "has_video", "n_images",
    "has_github", "n_links", "tagline_words", "title_words",
] + list(TECH_GROUPS)

# Plain-English labels for explaining predictions.
LABELS = {
    "log_desc_words": "length of the Devpost write-up",
    "n_sections": "how complete the write-up sections are",
    "n_tech": "number of technologies used",
    "team_size": "team size",
    "has_video": "having a demo video",
    "n_images": "number of screenshots",
    "has_github": "linking a GitHub repo",
    "n_links": "number of links (demo, repo, site)",
    "tagline_words": "tagline length",
    "title_words": "title length",
    "uses_ai": "using AI / ML",
    "uses_hardware": "using hardware",
    "uses_mobile": "being a mobile app",
    "uses_game": "being a game",
    "uses_cloud": "using cloud services",
    "uses_web": "being a web app",
    "uses_blockchain": "using blockchain",
    "text": "what the project is about (description content)",
}


def clean_text(s) -> str:
    s = "" if (s is None or (isinstance(s, float) and math.isnan(s))) else str(s)
    return LEAK_RE.sub(" ", s)


def tech_list(built_with) -> list:
    if not isinstance(built_with, str) or not built_with:
        return []
    return [t.strip().lower() for t in built_with.split("|") if t.strip()]


def numeric_features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    desc = df["description"].fillna("").map(clean_text)
    out["log_desc_words"] = np.log1p(desc.str.split().str.len().fillna(0))
    out["n_sections"] = df.get("n_sections", 0)
    techs = df["built_with"].map(tech_list)
    out["n_tech"] = techs.str.len()
    out["team_size"] = df.get("team_size", 1).clip(lower=1, upper=6)
    for col in ["has_video", "n_images", "has_github", "n_links"]:
        out[col] = df.get(col, 0)
    out["n_images"] = out["n_images"].clip(upper=15)
    out["n_links"] = out["n_links"].clip(upper=6)
    out["tagline_words"] = df["tagline"].fillna("").str.split().str.len()
    out["title_words"] = df["title"].fillna("").str.split().str.len()
    for group, kws in TECH_GROUPS.items():
        out[group] = techs.map(lambda ts, kws=kws: int(any(t in kws for t in ts)))
    return out[NUMERIC].fillna(0).astype(float)


def text_for_embedding(df: pd.DataFrame) -> list:
    return (
        df["title"].fillna("") + ". " + df["tagline"].fillna("") + ". "
        + df["description"].fillna("").map(clean_text).str.slice(0, 2000)
    ).tolist()


_model = None


def embed(texts: list) -> np.ndarray:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBED_MODEL)
    return _model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)
