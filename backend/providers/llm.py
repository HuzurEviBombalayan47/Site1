import os
import json
import re
from typing import Any, Dict, List

import requests


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def generate(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    model = GEMINI_MODEL

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent"
        f"?key={GEMINI_API_KEY}"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json",
        },
    }

    response = requests.post(
        url,
        json=payload,
        timeout=120,
    )

    response.raise_for_status()

    data = response.json()

    result_text = data["candidates"][0]["content"]["parts"][0]["text"]

    # DEBUG: Gemini'nin gerçekten ne döndürdüğünü Render loglarında göreceğiz.
    print(
        f"[LLM DEBUG] Gemini model={model} returned {len(result_text)} chars",
        flush=True,
    )
    print(
        f"[LLM DEBUG] Gemini raw response={result_text[:12000]}",
        flush=True,
    )

    return result_text


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()

    # Markdown code fence varsa temizle
    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # İlk JSON object'i bulmaya çalış
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        return json.loads(candidate)

    raise ValueError("Could not extract valid JSON from Gemini response")


def _analyze_window(
    narration: str,
    start: float,
    end: float,
) -> List[Dict[str, Any]]:

    prompt = f"""
You are a professional documentary and YouTube video visual planner.

Analyze the following narration segment and create visual scene instructions.

NARRATION:
{narration}

TIME RANGE:
{start} - {end} seconds

Return ONLY valid JSON.

Required structure:

{{
  "segments": [
    {{
      "start": 0,
      "end": 5,
      "narration": "short description",
      "visual_concept": "specific visual concept",
      "search_queries": [
        "specific subject-focused search query",
        "another specific subject-focused query"
      ]
    }}
  ]
}}

IMPORTANT RULES FOR search_queries:

1. Every search query MUST describe the actual subject of the narration.

2. Do NOT generate generic atmosphere or background queries.

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

4. Do NOT use generic phrases just because they sound cinematic.

5. Instead, identify the actual person, company, product, event, location, object, technology, historical event, or concept being discussed.

6. Example:

Bad:
"cinematic dark background"

Good:
"Steve Jobs introducing first iPhone 2007"
"original iPhone 2007 presentation"
"Apple first iPhone keynote"

7. Another example:

Bad:
"dramatic cinematic footage"

Good:
"factory workers assembling smartphones"
"modern smartphone manufacturing factory"
"electronics production line workers"

8. Search queries should be useful for finding real stock footage, photographs, archival footage, news footage, GIFs, or other relevant media.

9. Prefer concrete nouns and recognizable subjects.

10. Each segment should normally contain 1-4 search queries.

11. Do not invent unrelated visuals merely to make the video look cinematic.

12. If the narration discusses a historical event, search for that historical event specifically.

13. If the narration discusses a person, search for that person specifically.

14. If the narration discusses a company or product, search for that company/product specifically.

15. If the narration discusses an abstract concept, translate the concept into a concrete visual representation related to the narration.

16. The visual should explain or reinforce what is being said, not merely provide decorative background.

Create the JSON now.
"""

    raw = generate(prompt)
    data = _extract_json(raw)

    segments = data.get("segments", [])

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

    # DEBUG: Gemini'den parse edilen sorguları filtrelemeden önce göster.
    print(
        f"[LLM DEBUG] Parsed {len(segments)} segments from Gemini",
        flush=True,
    )

    for i, seg in enumerate(segments):
        queries = seg.get("search_queries") or []

        print(
            f"[LLM DEBUG] segment {i} BEFORE filter queries={queries!r}",
            flush=True,
        )

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

            if q.lower() in banned:
                continue

            cleaned.append(q)

        if not cleaned:
            cleaned = [str(fallback).strip()]

        seg["search_queries"] = cleaned[:4]

        # DEBUG: Filtrelemeden sonra gerçekte ne kaldığını göster.
        print(
            f"[LLM DEBUG] segment {i} AFTER filter queries={seg['search_queries']!r}",
            flush=True,
        )

    return segments


def analyze(
    narration: str,
    start: float = 0,
    end: float = 60,
) -> List[Dict[str, Any]]:

    return _analyze_window(
        narration=narration,
        start=start,
        end=end,
            )
