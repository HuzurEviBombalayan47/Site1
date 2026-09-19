"""LLM provider (Google Gemini, direct API key). Documentary-grade visual planning."""
import os
import json
import re
import requests

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    return key


def _model():
    return os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")


FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-flash-latest"]


def generate(prompt: str, temperature: float = 0.6, max_tokens: int = 16384) -> str:
    import time

    models = [_model()] + [m for m in FALLBACK_MODELS if m != _model()]
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    last_err = None
    for model in models:
        for attempt in range(3):
            try:
                r = requests.post(
                    f"{GEMINI_BASE}/{model}:generateContent",
                    params={"key": _key()},
                    json=body,
                    timeout=180,
                )
                if r.status_code in (503, 429, 500):
                    last_err = f"{r.status_code} on {model}"
                    time.sleep(1.5 * (attempt + 1))
                    continue
                r.raise_for_status()
                data = r.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except requests.exceptions.HTTPError as e:
                last_err = str(e)
                if r.status_code in (503, 429, 500):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
            except Exception as e:
                last_err = str(e)
                time.sleep(1.0)
    raise RuntimeError(f"Gemini generate failed: {last_err}")


def _extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


STYLE_GUIDANCE = {
    "documentary": (
        "Serious documentary / YouTube video-essay. The visuals must SUPPORT and illustrate the narration "
        "like a human editor who deliberately gathered relevant footage. Prefer real people/events, archival "
        "photos, places, documents, and topical cinematic stock footage. NO reaction memes, NO gifs, NO jokes. "
        "Semantic blocks of ~4-8 seconds; change the visual when the MEANING changes, not on every sentence."
    ),
    "normal": (
        "Clean YouTube edit. Prefer relevant real photos and B-roll that match the narration. Occasional reaction "
        "gif only if clearly warranted. Blocks ~3-6 seconds."
    ),
    "fast": (
        "Fast-paced edit, more visual variety, shorter blocks (~2-4s), energetic motion. Some reaction gifs allowed."
    ),
    "shitpost": (
        "Absurd shitpost edit: reaction memes/gifs, unexpected juxtapositions, aggressive zoom on punchlines. "
        "Still keep visuals loosely tied to what is said."
    ),
}

DOC_TYPES = "person, photo, archive, document, place, stock_video, graphic"
VIRAL_TYPES = "person, photo, archive, document, place, stock_video, graphic, reaction"


def _analyze_window(words, win_start, win_end, style, allowed_sfx):
    compact = " ".join(
        f"[{w['text']}|{round(w['start'],2)}]" for w in words
    )
    documentary = style == "documentary"
    types = DOC_TYPES if documentary else VIRAL_TYPES
    sfx_line = (
        "- \"needs_sfx\": boolean (documentary: almost always false). \"sfx\": one of ["
        + allowed_sfx + "] or null."
        if not documentary
        else "- \"needs_sfx\": false. \"sfx\": null."
    )
    reaction_note = (
        "" if documentary else
        "Use visual_type 'reaction' ONLY for a genuinely warranted reaction gif. "
    )
    prompt = f"""You are an expert documentary video editor planning the B-roll for a narration.
STYLE: {STYLE_GUIDANCE.get(style, STYLE_GUIDANCE['documentary'])}

The narration may be in Turkish or any language. Read it, UNDERSTAND the meaning, and produce ENGLISH search
queries for stock/archive footage. Do NOT translate word-for-word: capture the CONCEPT.
Example: narration "Depresyon tohumu ekiliyordu" -> do NOT search "seed"; search concepts like
["depression", "lonely person dark room", "mental health struggle", "sadness silhouette"].

Below are transcript tokens [word|start_seconds] for the window {round(win_start,2)}s..{round(win_end,2)}s:
{compact}

Split THIS window into CONTIGUOUS semantic blocks covering {round(win_start,2)}..{round(win_end,2)} with no gaps/overlaps.
Each block ~4 to 8 seconds (merge sentences about the same idea; split when the idea changes).

For each block return an object:
- "start": number, "end": number (seconds, within the window range)
- "narration": the spoken words in this block
- "topic": what is being explained (short)
- "entities": array of concrete named things (people, places, organizations, events, objects)
- "visual_concept": the single visual idea that best ILLUSTRATES this narration
- "visual_type": one of [{types}]
- "search_queries": array of 2-4 CONCRETE ENGLISH queries, ordered best-first, to find that footage
  (most specific first: real person/event, then place/archive/document, then broader topical cinematic stock)
- "importance": 0..1 (how pivotal this line is)
- "visual_priority": 0..1 (how strongly a specific visual is needed)
- "motion": one of "slow_zoom","pan","static"
- "reason": one sentence: WHY this visual matches this narration
{sfx_line}
{reaction_note}
Return ONLY valid JSON: {{"segments": [ {{...}} ]}}"""
    raw = generate(prompt)
    data = _extract_json(raw)
    return data.get("segments", [])


def analyze(words: list, duration: float, mode: str, sfx_names: list) -> list:
    """Return structured shot-plan segments (absolute times). Chunks long audio."""
    style = mode if mode in STYLE_GUIDANCE else "documentary"
    allowed_sfx = ", ".join(sfx_names)

    if not words:
        return []

    WINDOW = 90.0
    segments = []
    if duration <= WINDOW * 1.4:
        segments = _analyze_window(words, 0.0, duration, style, allowed_sfx)
    else:
        win_start = 0.0
        while win_start < duration - 0.5:
            win_end = min(duration, win_start + WINDOW)
            win_words = [w for w in words if w["start"] >= win_start - 0.01 and w["start"] < win_end]
            if win_words:
                try:
                    segs = _analyze_window(win_words, win_start, win_end, style, allowed_sfx)
                    segments.extend(segs)
                except Exception:
                    pass
            win_start = win_end

    if not segments:
        raise ValueError("LLM returned no segments")
    return segments
