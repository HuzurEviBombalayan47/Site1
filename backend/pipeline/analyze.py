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

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        return json.loads(candidate)

    raise ValueError(
        "Could not extract valid JSON from Gemini response"
    )


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

5. Identify the actual person, company, product, event, location,
object, technology, historical event, or concept being discussed.

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

8. Search queries should be useful for finding real stock footage,
photographs, archival footage, news footage, GIFs, or other relevant media.

9. Prefer concrete nouns and recognizable subjects.

10. Each segment should normally contain 1-4 search queries.

11. Do not invent unrelated visuals merely to make the video look cinematic.

12. If the narration discusses a historical event, search for that
historical event specifically.

13. If the narration discusses a person, search for that person specifically.

14. If the narration discusses a company or product, search for that
company/product specifically.

15. If the narration discusses an abstract concept, translate the concept
into a concrete visual representation related to the narration.

16. The visual should explain or reinforce what is being said,
not merely provide decorative background.

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

        print(
            f"[LLM DEBUG] segment {i} AFTER filter queries="
            f"{seg['search_queries']!r}",
            flush=True,
        )

    return segments


def analyze(
    words,
    duration: float = 60,
    mode: str = "documentary",
    sfx=None,
) -> List[Dict[str, Any]]:
    """
    Compatibility entry point for pipeline/analyze.py.

    Receives AssemblyAI word timings, splits the transcript into
    45-second windows, and sends each window to Gemini.
    """

    if not words:
        return []

    try:
        duration = float(duration)
    except (TypeError, ValueError):
        duration = 60.0

    if duration <= 0:
        return []

    window_size = 45.0
    result = []

    def get_word_start(word):
        try:
            return float(word.get("start", 0))
        except (TypeError, ValueError):
            return 0.0

    start_time = 0.0

    while start_time < duration:

        end_time = min(
            duration,
            start_time + window_size,
        )

        block = [
            word
            for word in words
            if start_time <= get_word_start(word) < end_time
        ]

        narration_parts = []

        for word in block:
            text = str(
                word.get("text", "")
            ).strip()

            if text:
                narration_parts.append(text)

        narration = " ".join(narration_parts).strip()

        if narration:

            try:
                segments = _analyze_window(
                    narration=narration,
                    start=start_time,
                    end=end_time,
                )

            except Exception as exc:

                print(
                    f"[LLM DEBUG] window "
                    f"{start_time:.1f}-{end_time:.1f} failed: "
                    f"{str(exc)[:500]}",
                    flush=True,
                )

                segments = []

            for seg in segments:

                if not isinstance(seg, dict):
                    continue

                try:
                    seg_start = float(
                        seg.get(
                            "start",
                            start_time,
                        )
                    )

                except (TypeError, ValueError):
                    seg_start = start_time

                try:
                    seg_end = float(
                        seg.get(
                            "end",
                            end_time,
                        )
                    )

                except (TypeError, ValueError):
                    seg_end = end_time

                # Gemini sometimes returns times relative
                # to the current analysis window.
                if seg_start < start_time:
                    seg_start += start_time
                    seg_end += start_time

                seg_start = max(
                    start_time,
                    min(
                        seg_start,
                        end_time,
                    ),
                )

                seg_end = max(
                    seg_start,
                    min(
                        seg_end,
                        end_time,
                    ),
                )

                if seg_end <= seg_start:
                    continue

                seg["start"] = round(
                    seg_start,
                    3,
                )

                seg["end"] = round(
                    seg_end,
                    3,
                )

                seg.setdefault(
                    "narration",
                    narration,
                )

                seg.setdefault(
                    "topic",
                    seg.get(
                        "visual_concept"
                    ) or narration[:120],
                )

                seg.setdefault(
                    "visual_concept",
                    seg.get(
                        "topic"
                    ) or narration[:120],
                )

                seg.setdefault(
                    "visual_type",
                    "photo",
                )

                seg.setdefault(
                    "motion",
                    "slow_zoom",
                )

                seg.setdefault(
                    "entities",
                    [],
                )

                seg.setdefault(
                    "importance",
                    0.5,
                )

                seg.setdefault(
                    "visual_priority",
                    0.5,
                )

                seg.setdefault(
                    "reason",
                    "Gemini subject-focused visual plan",
                )

                result.append(seg)

        start_time = end_time

    print(
        f"[LLM DEBUG] analyze() produced "
        f"{len(result)} visual segments",
        flush=True,
    )

    return result= {}
    seen_urls = set()
    seen_asset_keys = set()
    recent_asset_urls = []
    visuals = []
    sfx = []

    for seg in segments:
        segment_duration = (
            seg["end"] - seg["start"]
        )

        number_of_shots = max(
            1,
            min(
                SUBSHOT_MAX,
                round(
                    segment_duration
                    / SUBSHOT_TARGET
                ),
            ),
        )

        kinds = _kinds_for(
            seg.get(
                "visual_type",
                "photo",
            ),
            style,
        )

        queries = [
            query
            for query in (
                seg.get(
                    "search_queries",
                    [],
                )
                or []
            )
            if query
        ]

        assets = []

        if kinds and queries:
            assets = _resolve_multi(
                queries,
                kinds,
                cache,
                diagnostics_search,
                want=max(
                    number_of_shots,
                    4,
                ),
                seen_urls=seen_urls,
                seen_asset_keys=seen_asset_keys,
            )

        if not assets and kinds:
            broad_queries = (
                (seg.get("entities") or [])[:2]
                + [seg.get("topic", "")]
                + GENERIC_QUERIES
            )

            assets = _resolve_multi(
                broad_queries,
                kinds,
                cache,
                diagnostics_search,
                want=4,
                seen_urls=seen_urls,
                seen_asset_keys=seen_asset_keys,
            )

            for asset in assets:
                asset["_generic"] = True

        sub_duration = (
            segment_duration
            / number_of_shots
        )

        for index in range(
            number_of_shots
        ):
            start = (
                seg["start"]
                + index * sub_duration
            )

            if index < number_of_shots - 1:
                end = (
                    seg["start"]
                    + (index + 1)
                    * sub_duration
                )
            else:
                end = seg["end"]

            motion = seg.get(
                "motion",
                "slow_zoom",
            )

            selected_asset = None

            for candidate in assets:
                candidate_url = (
                    candidate.get("url")
                )

                if not candidate_url:
                    continue

                if (
                    candidate_url
                    in recent_asset_urls
                ):
                    continue

                selected_asset = candidate
                break

            if selected_asset:
                effect = _effect_for(
                    motion,
                    index,
                    style,
                    seg.get(
                        "emphasis",
                        False,
                    ),
                )

                if selected_asset.get(
                    "_generic",
                    False,
                ):
                    source = "generic"
                    diagnostics_search[
                        "generic"
                    ] += 1
                else:
                    source = "matched"
                    diagnostics_search[
                        "matched"
                    ] += 1

                visuals.append(
                    _clip(
                        start,
                        end,
                        seg,
                        selected_asset,
                        effect,
                        source,
                    )
                )

                selected_url = (
                    selected_asset.get(
                        "url"
                    )
                )

                if selected_url:
                    recent_asset_urls.append(
                        selected_url
                    )

                    recent_asset_urls = (
                        recent_asset_urls[-3:]
                    )

            else:
                diagnostics_search[
                    "text"
                ] += 1

                visuals.append(
                    _clip(
                        start,
                        end,
                        seg,
                        None,
                        "kenburns",
                        "text",
                    )
                )

        if (
            style != "documentary"
            and seg.get("needs_sfx")
            and seg.get("sfx")
            in sfx_names()
        ):
            sfx.append({
                "id": str(uuid.uuid4()),
                "time": round(
                    seg["start"],
                    3,
                ),
                "name": seg.get("sfx"),
                "volume": 0.9,
            })

    # ========================================================
    # FINAL HARD NO-OVERLAP SANITIZER
    # ========================================================
    # Bütün B-roll timeline'ı burada son kez temizleniyor.
    # Bundan sonra overlap kalmasına izin verilmiyor.
    visuals = _sanitize_visual_timeline(
        visuals,
        duration,
    )

    log("Altyazılar oluşturuluyor...")

    captions = T.build_caption_lines(
        words
    )

    covered = sum(
        clip["end"] - clip["start"]
        for clip in visuals
        if clip["source"]
        in (
            "matched",
            "generic",
        )
    )

    unique_urls = {
        clip["url"]
        for clip in visuals
        if clip["url"]
    }

    pexels_count = sum(
        1
        for clip in visuals
        if clip.get("provider")
        == "pexels"
    )

    giphy_count = sum(
        1
        for clip in visuals
        if clip.get("provider")
        == "giphy"
    )

    durations = [
        clip["end"] - clip["start"]
        for clip in visuals
    ]

    diagnostics = {
        "total_spoken_duration": round(
            duration,
            2,
        ),
        "visual_coverage_pct": (
            round(
                100.0
                * covered
                / duration,
                1,
            )
            if duration
            else 0
        ),
        "num_visual_assets": len(
            visuals
        ),
        "num_unique_assets": len(
            unique_urls
        ),
        "pexels_assets": pexels_count,
        "giphy_assets": giphy_count,
        "matched": diagnostics_search[
            "matched"
        ],
        "generic_fallback": diagnostics_search[
            "generic"
        ],
        "carried_forward": diagnostics_search[
            "carried"
        ],
        "text_fallback": diagnostics_search[
            "text"
        ],
        "failed_searches": diagnostics_search[
            "failed_searches"
        ],
        "empty_searches": diagnostics_search[
            "empty_searches"
        ],
        "total_searches": diagnostics_search[
            "searches"
        ],
        "empty_visual_gaps": diagnostics_search[
            "text"
        ],
        "avg_visual_duration": (
            round(
                sum(durations)
                / len(durations),
                2,
            )
            if durations
            else 0
        ),
    }

    return {
        "duration": round(
            duration,
            3,
        ),
        "canvas": {
            "w": canvas["w"],
            "h": canvas["h"],
            "format": fmt,
            "label": canvas["label"],
        },
        "visuals": visuals,
        "captions": captions,
        "sfx": sfx,
        "music": [],
        "used_llm": used_llm,
        "style": style,
        "diagnostics": diagnostics,
    }
