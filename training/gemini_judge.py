"""LLM judge: Gemini reads a project write-up and scores it against a hackathon judging rubric.

This is a feedback layer, separate from the win-probability model. It does NOT change
the Oracle's score (that model is trained and validated on real outcomes; this one isn't yet).

Turned on only when an API key is set:
    export GEMINI_API_KEY=...            # https://aistudio.google.com/apikey
    export GEMINI_MODEL=gemini-flash-lite-latest  # optional; falls back through FALLBACK_MODELS

Run on its own:
    python gemini_judge.py https://devpost.com/software/some-project
"""
import json
import os

import requests

DEFAULT_MODEL = "gemini-flash-lite-latest"  # fast (~1-2s); older 2.5 models are closed to new keys
# tried in order if the chosen model is missing (404), rate limited (429), overloaded or times out
FALLBACK_MODELS = ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-flash-latest"]
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# A typical hackathon judging rubric (Devpost / MLH style). Edit to match the event's official one.
RUBRIC = [
    ("technical_complexity", "Technical complexity", "How hard was this to build? Real engineering vs. a thin wrapper."),
    ("originality", "Originality", "Is the idea new or a fresh take, or a common hackathon project?"),
    ("impact", "Impact / usefulness", "Does it solve a real problem for real people?"),
    ("design", "Design / UX", "Is it polished and easy to use, based on what the write-up shows?"),
    ("presentation", "Presentation", "Is the write-up clear and complete: what it does, how it works, challenges, demo?"),
]

PROMPT = """You are an experienced hackathon judge. Score this Devpost submission against the rubric.
Judge only what the submission shows. If the write-up is thin, the presentation score should be low
and you should say what is missing. Be direct and specific, no generic praise.

Rubric (score each 1 to 10):
{rubric}

Submission
Title: {title}
Tagline: {tagline}
Built with: {built_with}
Team size: {team_size} | Demo video: {video} | GitHub link: {github}
Write-up:
{description}
"""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "scores": {
            "type": "OBJECT",
            "properties": {k: {"type": "INTEGER"} for k, _, _ in RUBRIC},
            "required": [k for k, _, _ in RUBRIC],
        },
        "strengths": {"type": "ARRAY", "items": {"type": "STRING"}},
        "fixes": {"type": "ARRAY", "items": {"type": "STRING"}},
        "verdict": {"type": "STRING"},
    },
    "required": ["scores", "strengths", "fixes", "verdict"],
}


def enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def build_prompt(p: dict) -> str:
    return PROMPT.format(
        rubric="\n".join(f"- {key}: {name}. {desc}" for key, name, desc in RUBRIC),
        title=p.get("title") or "",
        tagline=p.get("tagline") or "",
        built_with=", ".join(t for t in str(p.get("built_with") or "").split("|") if t) or "not listed",
        team_size=p.get("team_size") or p.get("team_size_page") or "unknown",
        video="yes" if p.get("has_video") else "no",
        github="yes" if p.get("has_github") else "no",
        description=(p.get("description") or "(empty)")[:8000],
    )


def judge(p: dict, timeout: int = 20) -> dict:
    """Returns {"available": True, "scores": [...], "overall": x, ...} or {"available": False, "reason": ...}.
    Never raises, so callers can't be broken by the LLM being down."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return {"available": False, "reason": "Set GEMINI_API_KEY to turn on the Gemini judge."}
    chosen = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    models = [chosen] + [m for m in FALLBACK_MODELS if m != chosen]
    body = {
        "contents": [{"role": "user", "parts": [{"text": build_prompt(p)}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
        },
    }
    errors = []
    for model in models:
        try:
            r = requests.post(API_URL.format(model=model), json=body, timeout=timeout,
                              headers={"x-goog-api-key": key, "Content-Type": "application/json"})
            if r.status_code != 200:
                errors.append(f"{model}: HTTP {r.status_code}")
                if r.status_code in (400, 401, 403):  # bad key or request; other models won't help
                    break
                continue
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return parse_response(text, model)
        except Exception as e:  # timeout, network, malformed JSON...
            errors.append(f"{model}: {type(e).__name__}")
    return {"available": False, "reason": "Gemini judge unavailable (" + "; ".join(errors) + ")"}


def parse_response(text: str, model: str = DEFAULT_MODEL) -> dict:
    data = json.loads(text)
    raw = data.get("scores", {})
    scores = []
    for key, name, _ in RUBRIC:
        try:
            v = max(1, min(10, int(raw.get(key))))
        except (TypeError, ValueError):
            continue
        scores.append({"criterion": name, "key": key, "score": v})
    overall = round(sum(s["score"] for s in scores) / len(scores), 1) if scores else None
    return {
        "available": True,
        "model": model,
        "scores": scores,
        "overall": overall,
        "strengths": [str(s) for s in data.get("strengths", [])][:4],
        "fixes": [str(s) for s in data.get("fixes", [])][:4],
        "verdict": str(data.get("verdict", "")),
    }


if __name__ == "__main__":
    import sys

    from scrape import get, parse_project

    row = parse_project(get(sys.argv[1]))
    print(json.dumps(judge(row), indent=1))
