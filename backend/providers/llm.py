"""LLM provider (Google Gemini, direct API key). Modular analysis of transcript."""
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


def generate(prompt: str, temperature: float = 0.8) -> str:
    import time

    models = [_model()] + [m for m in FALLBACK_MODELS if m != _model()]
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 8192},
    }
    last_err = None
    for model in models:
        for attempt in range(3):
            try:
                r = requests.post(
                    f"{GEMINI_BASE}/{model}:generateContent",
                    params={"key": _key()},
                    json=body,
                    timeout=120,
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
                break  # non-retryable -> try next model
            except Exception as e:
                last_err = str(e)
                time.sleep(1.0)
    raise RuntimeError(f"Gemini generate failed: {last_err}")


def _extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    # find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


MODE_GUIDANCE = {
    "normal": "Clean YouTube edit. Prefer relevant real photos/B-roll. Use GIFs/memes sparingly. SFX only on strong punchlines (~1 per 15s). Gentle Ken Burns effects.",
    "fast": "Fast-paced edit. Shorter clips (1.5-2.5s), more visual variety, more transitions. Moderate reaction GIFs and SFX (~1 per 8s). Energetic zoom/pan effects.",
    "shitpost": "Absurd shitpost edit. Heavy use of reaction memes and GIFs, unexpected juxtapositions, aggressive zoom/shake, more frequent SFX (~1 per 5s) at comedic moments. Still respect comedic timing - do NOT put a meme on every second.",
}


def analyze(words: list, duration: float, mode: str, sfx_names: list) -> list:
    """Break transcript into meaning blocks with editing decisions.

    Returns list of segments:
      {start,end,text,topic,entities,visual_type,search_query,effect,needs_sfx,sfx,emphasis}
    """
    # Compact word list to keep prompt small
    compact = " ".join(
        f"[{w['text']}|{round(w['start'],2)}-{round(w['end'],2)}]" for w in words
    )
    allowed_sfx = ", ".join(sfx_names)
    prompt = f"""You are an expert viral video editor building an automatic YouTube-style edit.
Audio duration: {round(duration,2)}s. Edit mode: {mode.upper()}.
Mode guidance: {MODE_GUIDANCE.get(mode, MODE_GUIDANCE['normal'])}

Below is the transcript as tokens [word|start-end] (seconds):
{compact}

Split the speech into CONTIGUOUS meaning blocks (segments) that fully cover 0..{round(duration,2)}s with no gaps or overlaps. Each segment should be ~1.5 to 4 seconds. For every segment decide the best visual to overlay.

For each segment return an object with:
- "start": number (seconds)
- "end": number (seconds)
- "text": the spoken words in this block
- "topic": short description of what is being said
- "entities": array of concrete searchable things (people, objects, places, events)
- "visual_type": one of "image" (real relevant photo/B-roll), "video" (relevant B-roll clip), "gif" (reaction meme / funny gif)
- "search_query": ENGLISH search keywords to find that visual (be concrete; for reaction gifs use expressions like "surprised reaction", "confused", "mind blown")
- "effect": one of "kenburns","zoom_in","zoom_out","pan_left","pan_right","shake"
- "needs_sfx": boolean (only true at genuinely funny/punchy/surprising moments; do NOT overuse)
- "sfx": if needs_sfx true, ONE of [{allowed_sfx}], else null
- "emphasis": boolean (true for punchlines, surprises, irony, exaggeration)

Detect and react to: funny sentences, unexpected words, punchlines, irony, exaggeration, surprising facts, named people/characters, events, objects, meme-associable phrases. On emphasis moments prefer reaction gifs, aggressive zoom/shake and an SFX.

Return ONLY valid JSON in this exact shape:
{{"segments": [ {{...}}, {{...}} ]}}"""

    raw = generate(prompt)
    data = _extract_json(raw)
    segs = data.get("segments", [])
    if not segs:
        raise ValueError("LLM returned no segments")
    return segs
