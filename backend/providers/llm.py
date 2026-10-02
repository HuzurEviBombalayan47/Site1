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
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
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
        text = text[start:end + 1]

    return json.loads(text)


STYLE_GUIDANCE = {
    "documentary": (
        "Serious documentary / YouTube video-essay. The visuals must SUPPORT and illustrate the narration "
        "like a human editor who deliberately gathered relevant footage. Prefer real people/events, archival "
        "photos, places, documents, and topical cinematic stock footage. NO reaction memes, NO gifs, NO jokes. "
        "Sentence-level visual planning: change the visual for each meaningful sentence; do not merge separate "
        "sentences just to reduce the number of visuals."
    ),
    "normal": (
        "Clean YouTube edit. Prefer relevant real photos and B-roll that match the narration. "
        "Occasional reaction gif only if clearly warranted. Blocks ~3-6 seconds."
    ),
    "fast": (
        "Fast-paced edit, more visual variety, shorter blocks (~2-4s), energetic motion. "
        "Some reaction gifs allowed."
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
        f"[{w['text']}|{round(w['start'], 2)}]" for w in words
    )

    documentary = style == "documentary"
    types = DOC_TYPES if documentary else VIRAL_TYPES

    sfx_line = (
        "- \"needs_sfx\": boolean (documentary: almost always false). "
        "\"sfx\": one of [" + allowed_sfx + "] or null."
        if not documentary
        else '- "needs_sfx": false. "sfx": null.'
    )

    reaction_note = (
        ""
        if documentary
        else
        "Use visual_type 'reaction' ONLY for a genuinely warranted reaction gif."
    )

    prompt = f"""You are an expert documentary video editor planning the B-roll for a narration.

STYLE:
{STYLE_GUIDANCE.get(style, STYLE_GUIDANCE["documentary"])}

The narration may be in Turkish or any language.

Read the narration and UNDERSTAND its meaning.

Produce ENGLISH search queries for stock/archive footage.

Do NOT translate word-for-word.
Capture the actual CONCEPT and SUBJECT.

Example:
Narration: "Depresyon tohumu ekiliyordu"

Bad:
["seed", "cinematic dark background"]

Good:
["depression", "lonely person dark room", "mental health struggle", "sadness silhouette"]

IMPORTANT SEARCH QUERY RULES:

1. Every search query MUST describe the actual subject, person, event, place, object, situation, or concept mentioned in THIS sentence/block.

2. NEVER generate generic mood, style, atmosphere, or background-only queries.

3. NEVER use queries such as:
- "cinematic dark background"
- "dark cinematic background"
- "cinematic footage"
- "dark background"
- "moody atmosphere"
- "abstract light"
- "dramatic background"
- "dramatic cinematic footage"
- "cinematic background"
- "beautiful cinematic footage"
- "dark moody background"

4. Do NOT use generic cinematic words as the main subject of a query.

5. If the narration mentions a specific person, event, place, organization, object, historical period, technology, company, or situation, include that specific subject in the query.

6. Prefer queries that would actually return footage or images of WHAT THE NARRATION IS TALKING ABOUT.

7. Use concrete visual subjects rather than emotions alone.

8. If the narration is about an emotional concept, find a concrete visual representation of that concept.

Example:
"People became increasingly isolated."

Good:
["isolated person alone room", "lonely person sitting alone", "social isolation"]

Bad:
["dark background", "moody atmosphere", "cinematic footage"]

Example:
"Steve Jobs introduced the iPhone in 2007."

Good:
["Steve Jobs iPhone 2007", "original iPhone launch 2007", "Steve Jobs keynote 2007"]

Bad:
["cinematic technology background"]

Example:
"İnsanlar fabrikalarda uzun saatler çalışıyordu."

Good:
["factory workers long hours", "industrial workers factory", "workers in factory 1900s"]

Bad:
["cinematic industrial background"]

9. The first query should be the MOST SPECIFIC query.

10. The second and third queries should be useful alternative searches for the SAME SUBJECT.

11. Do not invent unrelated visual subjects just to make a query more cinematic.

Below are transcript tokens [word|start_seconds] for the window
{round(win_start, 2)}s..{round(win_end, 2)}s:

{compact}

Split THIS window into CONTIGUOUS semantic blocks covering
{round(win_start, 2)}..{round(win_end, 2)} with no gaps/overlaps.

Create ONE visual planning block per spoken sentence whenever the sentence
is long enough to visualize.

Do NOT merge separate sentences just because they discuss the same topic.

A very short fragment may be combined with a neighboring sentence only when
it is not independently visualizable.

Typical block duration is ~2 to 6 seconds, but follow the natural sentence
timing and meaning of the narration.

For each sentence/block return an object:

- "start": number, "end": number (seconds, within the window range)
- "narration": the spoken words in this sentence/block
- "topic": what is being explained (short)
- "entities": array of concrete named things (people, places, organizations, events, objects)
- "visual_concept": the single visual idea that best ILLUSTRATES this specific sentence/block
- "visual_type": one of [{types}]
- "search_queries": array of 2-4 CONCRETE ENGLISH search queries

Search queries MUST be specifically about the current sentence/block.

Never use generic cinematic/background queries.

Most specific first:
1. real person/event/object
2. specific place/archive/document
3. broader topical stock footage

- "importance": 0..1 (how pivotal this line is)
- "visual_priority": 0..1 (how strongly a specific visual is needed)
- "motion": one of "slow_zoom", "pan", "static"
- "reason": one sentence explaining WHY this visual matches the narration

{sfx_line}

{reaction_note}

Return ONLY valid JSON:

{{"segments": [{{...}}]}}
"""

    raw = generate(prompt)
    data = _extract_json(raw)

    segments = data.get("segments", [])

    # Generic queries that should never be sent to the media providers.
    banned = {
        "cinematic dark background",
        "dark cinematic background",
        "cinematic footage",
        "dark background",
        "moody atmosphere",
        "abstract light",
        "dramatic background",
        "dramatic cinematic footage",
        "cinematic background",
        "beautiful cinematic footage",
        "dark moody background",
    }

    for seg in segments:
        queries = seg.get("search_queries") or []

        fallback = (
            seg.get("visual_concept")
            or seg.get("topic")
            or seg.get("narration")
            or "documentary subject"
        )

        cleaned = []

        for q in queries:
            q = str(q).strip()

            if not q:
                continue

            # Exact generic query ban
            if q.lower() in banned:
                continue

            cleaned.append(q)

        # If Gemini returned only generic/banned queries,
        # use the actual visual concept instead.
        if not cleaned:
            cleaned = [str(fallback).strip()]

        seg["search_queries"] = cleaned[:4]

    return segments


def analyze(words: list, duration: float, mode: str, sfx_names: list) -> list:
    """Return structured shot-plan segments (absolute times). Chunks long audio."""

    style = mode if mode in STYLE_GUIDANCE else "documentary"
    allowed_sfx = ", ".join(sfx_names)

    if not words:
        return []

    WINDOW = 90.0
    segments = []

    if duration <= WINDOW * 1.4:
        segments = _analyze_window(
            words,
            0.0,
            duration,
            style,
            allowed_sfx,
        )
    else:
        win_start = 0.0

        while win_start < duration - 0.5:
            win_end = min(duration, win_start + WINDOW)

            win_words = [
                w
                for w in words
                if w["start"] >= win_start - 0.01
                and w["start"] < win_end
            ]

            if win_words:
                try:
                    segs = _analyze_window(
                        win_words,
                        win_start,
                        win_end,
                        style,
                        allowed_sfx,
                    )
                    segments.extend(segs)
                except Exception:
                    pass

            win_start = win_end

    if not segments:
        raise ValueError("LLM returned no segments")

    return segments
